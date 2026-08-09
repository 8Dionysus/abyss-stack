"""Compose one operator-authorized v2 contour admission revision from exact evidence."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa_sdk.contracts.organ_admission import AdmissionDecisionReceipt
from aoa_sdk.contracts.organ_registry_v2 import (
    ContourLastGoodState,
    ContourRuntimeIdentity,
    OrganContourAdmissionRevision,
    OrganRegistrySourceV2,
)
from aoa_sdk.contracts.organs import (
    ConsumerCompatibility,
    MaturityEvidence,
    OrganMaturityVector,
    QualifiedEvidenceRef,
)
from aoa_sdk.organs.registry import sha256_digest
from aoa_sdk.organs.admission import OrganAdmissionError, assert_admission_decision
from pydantic import ValidationError

from .contracts import LinkEvidence, RuntimeObservation
from .core import _reject_secret_material
from .observation import (
    MAX_OVERLAY_FUTURE_SKEW,
    ObservationProducerError,
    _read_json,
    _write_atomic,
)
from .process_launcher import PROCESS_EXECUTABLE_FD


class AdmissionRevisionError(ObservationProducerError):
    """The supplied live evidence cannot support one v2 admission revision."""


MAX_PROCESS_EXECUTABLE_BYTES = 16 * 1024 * 1024
KAG_PRODUCTION_UNIT = "aoa-organ-mcp-read@aoa-kag.service"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _one_ref(link: LinkEvidence, owner: str, label: str) -> QualifiedEvidenceRef:
    matches = [item for item in link.evidence_refs if item.owner == owner]
    if link.state != "exact" or len(matches) != 1:
        raise AdmissionRevisionError(f"{label} lacks one exact {owner} evidence ref")
    return QualifiedEvidenceRef.model_validate(matches[0].model_dump(mode="json"))


def _link_expiries(link: LinkEvidence, label: str) -> list[datetime]:
    if link.state != "exact" or link.expires_at is None or not link.evidence_refs:
        raise AdmissionRevisionError(f"{label} is not exact and expiring")
    values = [link.expires_at]
    for item in link.evidence_refs:
        if item.expires_at is None:
            raise AdmissionRevisionError(f"{label} evidence is not expiring")
        values.append(item.expires_at)
    return values


def _subject(observation: RuntimeObservation) -> Any:
    matches = [
        item
        for item in observation.subjects
        if item.organ_id == "aoa-kag" and item.policy_family == "read"
    ]
    if len(matches) != 1:
        raise AdmissionRevisionError("observation lacks one exact KAG read contour")
    return matches[0]


def _require_production_process(subject: Any, label: str) -> None:
    if (
        subject.process.unit_name != KAG_PRODUCTION_UNIT
        or re.fullmatch(
            rf"systemd-user:{re.escape(KAG_PRODUCTION_UNIT)}:pid:[1-9][0-9]*:start:[1-9][0-9]*",
            subject.process.process_identity or "",
        )
        is None
    ):
        raise AdmissionRevisionError(
            f"{label} evidence is not bound to the production process"
        )


def _registry_runtime_matches(current: Any, contour: Any) -> bool:
    identity = contour.runtime_identity
    return (
        current.source.revision == identity.source_revision
        and current.source.tree_digest == identity.source_tree_digest
        and current.package.name == identity.package_name
        and current.package.version == identity.package_version
        and current.package.artifact_digest == identity.package_digest
        and current.package.source_revision == identity.deployment_revision
        and current.deploy.revision == identity.deployment_revision
        and current.deploy.manifest_ref == identity.deployment_manifest_ref
        and current.deploy.manifest_digest == identity.deployment_manifest_digest
        and current.deploy.tree_digest == identity.deployed_tree_digest
        and current.process.executable_ref == identity.process_ref
        and current.process.process_identity == identity.process_identity
        and current.endpoint.endpoint_ref == contour.endpoint.endpoint_ref
        and current.endpoint.server_schema_digest
        == contour.endpoint.server_schema_digest
    )


def _proof_and_acceptance_match_current(current: Any, consumer: Any) -> bool:
    proof = current.proof
    acceptance = current.acceptance
    return (
        proof.proved_source_revision == current.source.revision
        and proof.proved_source_tree_digest == current.source.tree_digest
        and proof.proved_package_digest == current.package.artifact_digest
        and current.package.source_revision == current.deploy.revision
        and proof.proved_deploy_revision == current.deploy.revision
        and proof.proved_deploy_tree_digest == current.deploy.tree_digest
        and proof.proved_deploy_manifest_digest == current.deploy.manifest_digest
        and proof.proved_process_identity == current.process.process_identity
        and proof.proved_server_schema_digest == current.endpoint.server_schema_digest
        and proof.proved_consumer_registration_ref == consumer.registration_ref
        and proof.proved_canary_route == current.canary.canary_route
        and proof.proved_canary_ref == current.canary.canary_ref
        and acceptance.accepted_source_revision == current.source.revision
        and acceptance.accepted_package_digest == current.package.artifact_digest
    )


ProcessExecutableDigest = Callable[[str, Path, str], str]


def _proc_start_ticks(pid: int) -> int:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields = raw[raw.rfind(")") + 2 :].split()
        return int(fields[19])
    except (IndexError, OSError, ValueError) as exc:
        raise AdmissionRevisionError(
            "live process start identity is unavailable"
        ) from exc


def _process_backed_executable_digest(
    process_identity: str,
    executable_ref: Path,
    unit_name: str,
    *,
    launch_fd: int = PROCESS_EXECUTABLE_FD,
) -> str:
    match = re.fullmatch(
        rf"systemd-user:{re.escape(unit_name)}:pid:([1-9][0-9]*):start:([1-9][0-9]*)",
        process_identity,
    )
    if match is None:
        raise AdmissionRevisionError("live process identity is not exact")
    pid = int(match.group(1))
    systemd_start_us = int(match.group(2))
    ticks_per_second = os.sysconf("SC_CLK_TCK")
    start_ticks_before = _proc_start_ticks(pid)
    proc_start_us = start_ticks_before * 1_000_000 // ticks_per_second
    if abs(proc_start_us - systemd_start_us) > (1_000_000 // ticks_per_second) + 1:
        raise AdmissionRevisionError("live process start identity changed")
    fd_ref = Path(f"/proc/{pid}/fd/{launch_fd}")
    try:
        target = os.readlink(fd_ref)
    except OSError as exc:
        raise AdmissionRevisionError(
            "process-backed executable evidence is unavailable"
        ) from exc
    expected = executable_ref.expanduser().absolute().as_posix()
    if target not in {expected, expected + " (deleted)"}:
        raise AdmissionRevisionError(
            "process-backed executable differs from the managed executable"
        )
    try:
        descriptor = os.open(fd_ref, os.O_RDONLY | os.O_CLOEXEC)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise AdmissionRevisionError(
                    "process-backed executable is not a regular file"
                )
            digest = hashlib.sha256()
            total = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                total += len(chunk)
                if total > MAX_PROCESS_EXECUTABLE_BYTES:
                    raise AdmissionRevisionError(
                        "process-backed executable exceeds its bounded size"
                    )
                digest.update(chunk)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise AdmissionRevisionError("process-backed executable is unreadable") from exc
    if _proc_start_ticks(pid) != start_ticks_before:
        raise AdmissionRevisionError("live process changed during executable proof")
    return "sha256:" + digest.hexdigest()


def _lkg_matches_rollback_target(
    lkg: Any,
    current: Any,
    *,
    process_executable_digest: ProcessExecutableDigest,
) -> bool:
    target = current.rollback.proved_target
    if target is None:
        return False
    matching_consumers = [
        consumer
        for consumer in lkg.consumers
        if consumer.registered
        and consumer.registration_ref == target.consumer_registration_ref
        and consumer.observed_schema_digest == lkg.endpoint.server_schema_digest
        and set(consumer.observed_protocol_versions)
        & set(lkg.endpoint.protocol_versions)
        and consumer.evidence.state == "exact"
    ]
    live_process_identity = lkg.process.process_identity or ""
    exact_live_process = re.fullmatch(
        rf"systemd-user:{re.escape(target.unit_name)}:pid:[1-9][0-9]*:start:[1-9][0-9]*",
        live_process_identity,
    )
    exact_stable_target = re.fullmatch(
        rf"systemd-user:{re.escape(target.unit_name)}:executable:(sha256:[0-9a-f]{{64}})",
        target.process_identity,
    )
    process_target_matches = live_process_identity == target.process_identity
    if not process_target_matches and exact_live_process and exact_stable_target:
        try:
            observed_executable_digest = process_executable_digest(
                live_process_identity,
                Path(lkg.process.executable_ref),
                target.unit_name,
            )
        except (OSError, ValueError):
            return False
        process_target_matches = (
            observed_executable_digest == exact_stable_target.group(1)
        )
    return (
        len(matching_consumers) == 1
        and process_target_matches
        and (
            lkg.package.artifact_digest == target.package_digest
            and lkg.package.source_revision == target.deploy_revision
            and lkg.deploy.revision == target.deploy_revision
            and lkg.deploy.tree_digest == target.deploy_tree_digest
            and lkg.deploy.manifest_ref == target.deploy_manifest_ref
            and lkg.deploy.manifest_digest == target.deploy_manifest_digest
            and lkg.process.unit_name == target.unit_name
            and lkg.credential_class == target.credential_class
            and lkg.process.executable_ref == target.executable_ref
            and lkg.canary.canary_route == target.canary_route
            and lkg.canary.canary_ref == target.canary_ref
        )
    )


def compose_admission_revision(
    *,
    registry_path: Path,
    observation_path: Path,
    lkg_observation_path: Path,
    operator_decision_path: Path,
    clock: Any = _now,
    process_executable_digest: ProcessExecutableDigest = (
        _process_backed_executable_digest
    ),
) -> OrganContourAdmissionRevision:
    registry_payload, _ = _read_json(registry_path, "v2 organ registry")
    observation_payload, _ = _read_json(observation_path, "current observation")
    lkg_payload, _ = _read_json(lkg_observation_path, "LKG observation")
    decision_payload, _ = _read_json(operator_decision_path, "operator decision")
    for payload in (
        registry_payload,
        observation_payload,
        lkg_payload,
        decision_payload,
    ):
        _reject_secret_material(payload)
    try:
        registry = OrganRegistrySourceV2.model_validate(registry_payload)
        observation = RuntimeObservation.model_validate(observation_payload)
        lkg_observation = RuntimeObservation.model_validate(lkg_payload)
        decision = AdmissionDecisionReceipt.model_validate(decision_payload)
    except ValidationError as exc:
        raise AdmissionRevisionError(
            "admission input failed its owner contract"
        ) from exc
    try:
        assert_admission_decision(decision)
    except OrganAdmissionError as exc:
        raise AdmissionRevisionError(
            "operator decision content address is invalid"
        ) from exc
    records = [item for item in registry.records if item.organ_id == "aoa-kag"]
    if len(records) != 1:
        raise AdmissionRevisionError("registry lacks one KAG organ")
    record = records[0]
    contours = [item for item in record.contours if item.contour_id == "read"]
    if len(contours) != 1:
        raise AdmissionRevisionError("registry lacks one KAG read contour")
    contour = contours[0]
    contour_digest = sha256_digest(contour.model_dump(mode="json"))
    if contour.registry_state != "shadow" or contour.endpoint is None:
        raise AdmissionRevisionError("only a shadow contour can be proposed")
    if (
        decision.decision_kind != "operator"
        or decision.decision != "accepted"
        or decision.issuer != registry.workspace_owner
        or decision.candidate_id != contour_digest
        or decision.decision_artifact_digest != contour_digest
        or decision.registry_mutation_performed is not False
    ):
        raise AdmissionRevisionError(
            "operator decision does not bind the shadow contour"
        )
    current = _subject(observation)
    lkg = _subject(lkg_observation)
    _require_production_process(current, "current")
    _require_production_process(lkg, "last-known-good")
    now = clock().astimezone(timezone.utc)
    if (
        observation.generated_at > now + MAX_OVERLAY_FUTURE_SKEW
        or lkg_observation.generated_at > now + MAX_OVERLAY_FUTURE_SKEW
        or observation.expires_at <= now
        or lkg_observation.expires_at <= now
        or decision.decided_at > now + MAX_OVERLAY_FUTURE_SKEW
        or decision.expires_at <= now
    ):
        raise AdmissionRevisionError("admission inputs are not current")
    expected_owners = record.owners.model_dump(mode="json")
    observed_owners = current.owners.model_dump(mode="json")
    observed_owners["control_owner"] = record.owners.control_owner
    if observed_owners != expected_owners:
        raise AdmissionRevisionError("runtime owners differ from registry owners")
    if (
        current.registry.registry_digest != contour_digest
        or lkg.registry.registry_digest != contour_digest
        or not _registry_runtime_matches(current, contour)
    ):
        raise AdmissionRevisionError("live evidence differs from the registry contour")
    if (
        not current.process.active
        or not current.endpoint.ready
        or current.freshness.state != "exact"
        or current.freshness.provider_watermark is None
        or not current.canary.succeeded
        or not current.canary.result_grounded
        or current.canary.canary_route != contour.observation_route
        or current.canary.canary_ref is None
        or current.proof.verdict != "passed"
        or not current.acceptance.accepted
        or not current.rollback.ready
    ):
        raise AdmissionRevisionError("current contour admission axes are incomplete")
    expected_lkg_route = contour.observation_route + "/last-known-good"
    if (
        not lkg.process.active
        or not lkg.endpoint.ready
        or lkg.freshness.state != "exact"
        or not lkg.canary.succeeded
        or not lkg.canary.result_grounded
        or lkg.canary.canary_route != expected_lkg_route
        or lkg.canary.canary_ref is None
        or lkg.canary.canary_ref == current.canary.canary_ref
    ):
        raise AdmissionRevisionError(
            "last-known-good contour is not exact and distinct"
        )
    consumers = [
        item
        for item in current.consumers
        if item.registered
        and item.observed_schema_digest == current.endpoint.server_schema_digest
        and set(item.observed_protocol_versions)
        & set(current.endpoint.protocol_versions)
        and item.evidence.state == "exact"
    ]
    if len(consumers) != 1:
        raise AdmissionRevisionError("current contour lacks one compatible consumer")
    consumer = consumers[0]
    if not _proof_and_acceptance_match_current(current, consumer):
        raise AdmissionRevisionError(
            "proof or owner acceptance targets a different current contour"
        )
    if not _lkg_matches_rollback_target(
        lkg,
        current,
        process_executable_digest=process_executable_digest,
    ):
        raise AdmissionRevisionError(
            "last-known-good observation differs from the rollback proof target"
        )
    consumer_ref = _one_ref(consumer.evidence, "8Dionysus", "consumer")
    source_ref = _one_ref(current.source.evidence, record.owners.source_owner, "source")
    runtime_ref = _one_ref(
        current.deploy.evidence, record.owners.runtime_owner, "deploy"
    )
    process_ref = _one_ref(
        current.process.evidence, record.owners.runtime_owner, "process"
    )
    endpoint_ref = _one_ref(
        current.endpoint.evidence, record.owners.runtime_owner, "endpoint"
    )
    registry_ref = _one_ref(
        current.registry.evidence, record.owners.control_owner, "registry"
    )
    canary_ref = _one_ref(
        current.canary.evidence, record.owners.runtime_owner, "canary"
    )
    freshness_ref = _one_ref(
        current.freshness, record.owners.acceptance_owner, "freshness"
    )
    proof_ref = _one_ref(current.proof.evidence, record.owners.proof_owner, "proof")
    acceptance_ref = _one_ref(
        current.acceptance.evidence,
        record.owners.acceptance_owner,
        "acceptance",
    )
    rollback_ref = _one_ref(
        current.rollback.evidence, record.owners.proof_owner, "rollback"
    )
    lkg_stack_ref = _one_ref(
        lkg.canary.evidence, record.owners.runtime_owner, "LKG canary"
    )
    lkg_owner_ref = _one_ref(
        lkg.canary.evidence, record.owners.acceptance_owner, "LKG review"
    )
    operator_ref = QualifiedEvidenceRef(
        owner=decision.issuer,
        evidence_ref=operator_decision_path.expanduser().absolute().as_posix(),
        revision=decision.decision_id,
        observed_at=decision.decided_at,
        expires_at=decision.expires_at,
    )
    axis_refs = {
        "declared": source_ref,
        "owner_reviewed": freshness_ref,
        "packaged": runtime_ref,
        "exported": runtime_ref,
        "deployed": runtime_ref,
        "process_alive": process_ref,
        "endpoint_ready": endpoint_ref,
        "registry_indexed": registry_ref,
        "consumer_registered": consumer_ref,
        "schema_observed": canary_ref,
        "call_succeeded": canary_ref,
        "result_grounded": freshness_ref,
        "freshness_satisfied": freshness_ref,
        "owner_accepted": acceptance_ref,
        "rollback_proven": rollback_ref,
    }
    maturity = OrganMaturityVector(
        **{
            name: (
                MaturityEvidence(state="not_asserted")
                if name == "cross_organ_proven"
                else MaturityEvidence(
                    state="asserted",
                    evidence=axis_refs[name],
                    freshness_policy="exact-live-admission-evidence-v1",
                )
            )
            for name in OrganMaturityVector.model_fields
        }
    )
    compatible = ConsumerCompatibility(
        consumer_id=consumer.consumer_id,
        support_state="supported",
        protocol_versions=consumer.observed_protocol_versions,
        observed_schema_digest=consumer.observed_schema_digest,
        evidence_ref=consumer_ref,
    )
    lkg_runtime = ContourRuntimeIdentity(
        source_revision=lkg.source.revision,
        source_tree_digest=lkg.source.tree_digest,
        package_name=lkg.package.name,
        package_version=lkg.package.version,
        package_digest=lkg.package.artifact_digest,
        deployment_revision=lkg.deploy.revision,
        deployment_manifest_ref=lkg.deploy.manifest_ref,
        deployment_manifest_digest=lkg.deploy.manifest_digest,
        deployed_tree_digest=lkg.deploy.tree_digest,
        process_ref=lkg.process.executable_ref,
        process_identity=lkg.process.process_identity,
    )
    expiry_links = (
        current.source.evidence,
        current.package.evidence,
        current.deploy.evidence,
        current.process.evidence,
        current.endpoint.evidence,
        current.registry.evidence,
        current.freshness,
        current.canary.evidence,
        current.proof.evidence,
        current.acceptance.evidence,
        current.rollback.evidence,
        consumer.evidence,
        lkg.canary.evidence,
    )
    expiries = [
        registry.expires_at,
        observation.expires_at,
        lkg_observation.expires_at,
        decision.expires_at,
    ]
    for index, link in enumerate(expiry_links):
        expiries.extend(_link_expiries(link, f"admission link {index}"))
    expires_at = min(expiries)
    last_good = ContourLastGoodState(
        recorded_at=lkg.canary.evidence.observed_at,
        expires_at=expires_at,
        protocol_version=lkg.endpoint.protocol_versions[0],
        endpoint_ref=lkg.endpoint.endpoint_ref,
        credential_class=contour.credential_class,
        principal_id=contour.principal_id,
        server_schema_digest=lkg.endpoint.server_schema_digest,
        runtime_identity=lkg_runtime,
        evidence_refs=(lkg_stack_ref, lkg_owner_ref, rollback_ref),
    )
    body: dict[str, Any] = {
        "schema_version": "aoa_organ_contour_admission_revision_v1",
        "revision_id": f"{record.organ_id}-{contour.contour_id}-admission",
        "organ_id": record.organ_id,
        "contour_id": contour.contour_id,
        "expected_contour_digest": contour_digest,
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "operator_evidence": operator_ref.model_dump(mode="json"),
        "proof_ref": proof_ref.model_dump(mode="json"),
        "acceptance_ref": acceptance_ref.model_dump(mode="json"),
        "rollback_ref": rollback_ref.model_dump(mode="json"),
        "freshness_evidence": freshness_ref.model_dump(mode="json"),
        "owner_watermark": current.freshness.provider_watermark,
        "owner_watermark_evidence": freshness_ref.model_dump(mode="json"),
        "consumer_compatibility": compatible.model_dump(mode="json"),
        "last_good": last_good.model_dump(mode="json"),
        "maturity": maturity.model_dump(mode="json"),
        "admission_authorized": True,
        "effect_authorized": False,
        "cross_organ_asserted": False,
        "rollback_executed": False,
        "contains_secrets": False,
    }
    body["revision_digest"] = "sha256:" + ("0" * 64)
    normalized = OrganContourAdmissionRevision.model_validate(body)
    revision_digest = sha256_digest(
        normalized.model_dump(mode="json", exclude={"revision_digest"})
    )
    return normalized.model_copy(update={"revision_digest": revision_digest})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--lkg-observation", type=Path, required=True)
    parser.add_argument("--operator-decision", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        revision = compose_admission_revision(
            registry_path=args.registry,
            observation_path=args.observation,
            lkg_observation_path=args.lkg_observation,
            operator_decision_path=args.operator_decision,
        )
        _write_atomic(args.output, revision.model_dump(mode="json"))
    except (AdmissionRevisionError, OSError, KeyError) as exc:
        print(f"contour admission revision: {exc}", file=__import__("sys").stderr)
        return 1
    print(f"output={args.output.expanduser().absolute()}")
    print(f"revision_digest={revision.revision_digest}")
    print("admission_authorized=true")
    print("effect_authorized=false")
    print("registry_mutated=false")
    print("contains_secrets=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
