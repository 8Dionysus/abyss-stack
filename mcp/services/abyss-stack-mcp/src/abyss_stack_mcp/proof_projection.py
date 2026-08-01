"""Project an aoa-evals bounded review only onto its exact live target."""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .contracts import CentralProofObservation, EvidenceRef, LinkEvidence, RuntimeObservation
from .core import _reject_secret_material
from .observation import (
    MAX_OVERLAY_FUTURE_SKEW,
    ObservationProducerError,
    RuntimeEvidenceOverlay,
    RuntimeEvidenceOverlaySubject,
    _digest,
    _parse_timestamp,
    _read_json,
    _write_atomic,
)


EXPECTED_EVAL_NAME = "aoa-organ-access-admission-integrity"
EXPECTED_EVAL_REF = f"evals/boundary/{EXPECTED_EVAL_NAME}/EVAL.md"
EXPECTED_MANIFEST_REF = f"evals/boundary/{EXPECTED_EVAL_NAME}/eval.yaml"
EXPECTED_PACKET_SCHEMA_REF = (
    f"evals/boundary/{EXPECTED_EVAL_NAME}/"
    "schemas/organ-access-proof-packet.schema.json"
)
REQUIRED_ASSERTED_AXES = {
    "declared": "source_declaration",
    "packaged": "package_receipt",
    "exported": "export_receipt",
    "deployed": "deploy_receipt",
    "process_alive": "process_observation",
    "endpoint_ready": "endpoint_probe",
    "registry_indexed": "registry_observation",
    "consumer_registered": "consumer_registration",
    "schema_observed": "consumer_schema_observation",
    "call_succeeded": "call_receipt",
    "result_grounded": "owner_grounding_review",
    "freshness_satisfied": "freshness_review",
}
FORBIDDEN_ASSERTED_AXES = {
    "owner_accepted",
    "cross_organ_proven",
    "rollback_proven",
}


class CentralProofProjectionError(ObservationProducerError):
    """The bounded eval result cannot support an exact central-proof overlay."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _file_digest(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CentralProofProjectionError("eval source contract is unavailable") from exc


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CentralProofProjectionError(f"{label} must be an object")
    return value


def _asserted_axis(packet: dict[str, Any], name: str) -> dict[str, Any]:
    maturity = _require_mapping(packet.get("maturity"), "packet maturity")
    axis = _require_mapping(maturity.get(name), f"packet {name} axis")
    if axis.get("state") != "asserted":
        raise CentralProofProjectionError(f"packet {name} axis is not asserted")
    if axis.get("evidence_kind") != REQUIRED_ASSERTED_AXES[name]:
        raise CentralProofProjectionError(f"packet {name} evidence kind differs")
    if not all(
        isinstance(axis.get(field), str) and axis[field]
        for field in ("observed_at", "evidence_ref", "revision")
    ):
        raise CentralProofProjectionError(f"packet {name} evidence is incomplete")
    if not axis.get("expires_at") and not axis.get("freshness_policy"):
        raise CentralProofProjectionError(f"packet {name} freshness is absent")
    return axis


def _ref_base(value: str) -> str:
    return value.split("#", 1)[0]


def _validate_review(
    review: dict[str, Any],
    packet: dict[str, Any],
    *,
    packet_path: Path,
    eval_root: Path,
) -> datetime:
    required = {
        "schema_version": "aoa_organ_access_packet_review_v1",
        "eval_name": EXPECTED_EVAL_NAME,
        "bundle_status": "bounded",
        "verdict": "supported_bounded",
        "central_proof_asserted": True,
        "owner_acceptance_inferred": False,
        "admission_change_authorized": False,
        "higher_effect_authorized": False,
        "cross_organ_benefit_asserted": False,
        "rollback_proven": False,
    }
    if any(review.get(field) != value for field, value in required.items()):
        raise CentralProofProjectionError(
            "aoa-evals review does not assert the bounded proof contract"
        )
    if review.get("actual_effects") not in ([], ()):
        raise CentralProofProjectionError("aoa-evals review reports actual effects")
    packet_review = _require_mapping(review.get("packet"), "review packet binding")
    if (
        packet_review.get("packet_ref")
        != packet_path.expanduser().absolute().as_posix()
        or packet_review.get("packet_digest") != _digest(packet)
        or packet_review.get("packet_id") != packet.get("packet_id")
        or packet_review.get("organ_id") != packet.get("organ_id")
        or packet_review.get("capability_id") != packet.get("capability_id")
        or packet_review.get("result_verdict")
        != _require_mapping(packet.get("result"), "packet result").get("verdict")
    ):
        raise CentralProofProjectionError("aoa-evals review names a different packet")
    validation = _require_mapping(
        review.get("packet_validation"), "review packet validation"
    )
    if validation.get("accepted_by_source_contract") is not True or validation.get(
        "issues"
    ) not in ([], ()):
        raise CentralProofProjectionError("aoa-evals packet validation did not pass")
    suite = _require_mapping(review.get("negative_suite"), "review negative suite")
    if (
        suite.get("verdict") != "supports bounded claim"
        or suite.get("failed_count") != 0
        or not isinstance(suite.get("scenario_count"), int)
        or suite["scenario_count"] < 1
        or suite.get("passed_count") != suite.get("scenario_count")
    ):
        raise CentralProofProjectionError("aoa-evals negative suite did not pass")
    source = _require_mapping(review.get("source_contract"), "review source contract")
    expected_sources = {
        "eval_ref": EXPECTED_EVAL_REF,
        "eval_digest": _file_digest(eval_root / "EVAL.md"),
        "manifest_ref": EXPECTED_MANIFEST_REF,
        "manifest_digest": _file_digest(eval_root / "eval.yaml"),
        "packet_schema_ref": EXPECTED_PACKET_SCHEMA_REF,
        "packet_schema_digest": _file_digest(
            eval_root / "schemas" / "organ-access-proof-packet.schema.json"
        ),
    }
    if source != expected_sources:
        raise CentralProofProjectionError("aoa-evals source contract digest differs")
    return _parse_timestamp(review.get("reviewed_at"), "reviewed_at")


def _validate_packet_target(
    packet: dict[str, Any],
    subject: Any,
) -> Any:
    if (
        packet.get("schema_version") != "organ_access_proof_packet_v1"
        or packet.get("organ_id") != subject.organ_id
        or packet.get("policy_plane") != subject.policy_family
    ):
        raise CentralProofProjectionError("packet does not name the live contour")
    owners = _require_mapping(packet.get("owners"), "packet owners")
    expected_owners = {
        "source": subject.owners.source_owner,
        "access": subject.owners.access_owner,
        "control": "aoa-sdk",
        "runtime": subject.owners.runtime_owner,
        "proof": subject.owners.proof_owner,
        "acceptance": subject.owners.acceptance_owner,
    }
    if owners != expected_owners or subject.owners.proof_owner != "aoa-evals":
        raise CentralProofProjectionError("packet owner roles differ from live owners")
    revisions = _require_mapping(packet.get("revisions"), "packet revisions")
    expected_revisions = {
        "source": "source:" + subject.source.revision,
        "package": "package:" + subject.package.artifact_digest,
        "deploy": "deploy:" + subject.deploy.manifest_digest,
        "consumer_schema": "consumer-schema:" + subject.endpoint.server_schema_digest,
    }
    if revisions != expected_revisions:
        raise CentralProofProjectionError("packet revisions differ from live identities")
    if (
        subject.source.evidence.state != "exact"
        or subject.package.evidence.state != "exact"
        or subject.deploy.evidence.state != "exact"
        or not subject.process.active
        or subject.process.evidence.state != "exact"
        or not subject.endpoint.ready
        or subject.endpoint.evidence.state != "exact"
        or subject.freshness.state != "exact"
        or not subject.canary.succeeded
        or not subject.canary.result_grounded
        or subject.canary.canary_ref is None
        or subject.canary.evidence.state != "exact"
    ):
        raise CentralProofProjectionError("live contour is not exact and grounded")

    axes = {name: _asserted_axis(packet, name) for name in REQUIRED_ASSERTED_AXES}
    maturity = _require_mapping(packet.get("maturity"), "packet maturity")
    for name in FORBIDDEN_ASSERTED_AXES:
        if _require_mapping(maturity.get(name), f"packet {name} axis").get(
            "state"
        ) == "asserted":
            raise CentralProofProjectionError(
                f"pre-acceptance packet cannot assert {name}"
            )
    if axes["declared"]["revision"] != expected_revisions["source"]:
        raise CentralProofProjectionError("packet declaration revision differs")
    for name in ("packaged", "exported"):
        if axes[name]["revision"] != expected_revisions["package"]:
            raise CentralProofProjectionError(f"packet {name} revision differs")
    for name in (
        "deployed",
        "process_alive",
        "endpoint_ready",
        "registry_indexed",
        "call_succeeded",
        "freshness_satisfied",
    ):
        if axes[name]["revision"] != expected_revisions["deploy"]:
            raise CentralProofProjectionError(f"packet {name} revision differs")
    for name in ("consumer_registered", "schema_observed"):
        if axes[name]["revision"] != expected_revisions["consumer_schema"]:
            raise CentralProofProjectionError(f"packet {name} revision differs")
    if axes["result_grounded"]["revision"] != expected_revisions["source"]:
        raise CentralProofProjectionError("packet grounding revision differs")

    registration_ref = axes["consumer_registered"]["evidence_ref"]
    compatible = [
        consumer
        for consumer in subject.consumers
        if consumer.registered
        and consumer.registration_ref == registration_ref
        and consumer.observed_schema_digest == subject.endpoint.server_schema_digest
        and bool(
            set(consumer.observed_protocol_versions)
            & set(subject.endpoint.protocol_versions)
        )
        and consumer.evidence.state == "exact"
        and any(
            evidence.evidence_ref == registration_ref
            for evidence in consumer.evidence.evidence_refs
        )
    ]
    if len(compatible) != 1:
        raise CentralProofProjectionError(
            "packet consumer registration is not one exact compatible consumer"
        )
    if _ref_base(axes["call_succeeded"]["evidence_ref"]) != subject.canary.canary_ref:
        raise CentralProofProjectionError("packet call receipt differs from canary")
    if _ref_base(axes["schema_observed"]["evidence_ref"]) != subject.canary.canary_ref:
        raise CentralProofProjectionError("packet schema receipt differs from canary")
    owner_review_refs = {
        evidence.evidence_ref
        for evidence in subject.canary.evidence.evidence_refs
        if evidence.owner == subject.owners.acceptance_owner
    }
    if _ref_base(axes["result_grounded"]["evidence_ref"]) not in owner_review_refs:
        raise CentralProofProjectionError("packet grounding review differs from canary")
    if _ref_base(axes["freshness_satisfied"]["evidence_ref"]) not in owner_review_refs:
        raise CentralProofProjectionError("packet freshness review differs from canary")
    return compatible[0]


def _effective_expiry(
    packet: dict[str, Any],
    observation: RuntimeObservation,
    subject: Any,
) -> datetime:
    expiries = [observation.expires_at]
    links = (
        subject.source.evidence,
        subject.package.evidence,
        subject.deploy.evidence,
        subject.process.evidence,
        subject.endpoint.evidence,
        subject.freshness,
        subject.canary.evidence,
    )
    for link in links:
        if link.expires_at is not None:
            expiries.append(link.expires_at)
        expiries.extend(
            evidence.expires_at
            for evidence in link.evidence_refs
            if evidence.expires_at is not None
        )
    for name in REQUIRED_ASSERTED_AXES:
        axis = _asserted_axis(packet, name)
        if axis.get("expires_at"):
            expiries.append(_parse_timestamp(axis["expires_at"], f"{name} expires_at"))
    return min(expiries)


def project_central_proof(
    *,
    review_path: Path,
    packet_path: Path,
    observation_path: Path,
    eval_root: Path,
    record_root: Path,
    output_path: Path | None = None,
    clock: Callable[[], datetime] = _now,
) -> tuple[RuntimeEvidenceOverlay, str, Path]:
    review, _ = _read_json(review_path, "aoa-evals proof review")
    packet, _ = _read_json(packet_path, "organ access proof packet")
    observation_payload, _ = _read_json(observation_path, "runtime observation")
    for payload in (review, packet, observation_payload):
        _reject_secret_material(payload)
    try:
        observation = RuntimeObservation.model_validate(observation_payload)
    except ValidationError as exc:
        raise CentralProofProjectionError(
            "runtime observation failed contract validation"
        ) from exc
    now = clock().astimezone(timezone.utc)
    if observation.expires_at <= now:
        raise CentralProofProjectionError("runtime observation is expired")
    evaluated_at = _validate_review(
        review,
        packet,
        packet_path=packet_path,
        eval_root=eval_root,
    )
    if evaluated_at > now + MAX_OVERLAY_FUTURE_SKEW:
        raise CentralProofProjectionError("aoa-evals review is causally future-dated")
    matches = [
        subject
        for subject in observation.subjects
        if subject.organ_id == packet.get("organ_id")
        and subject.policy_family == packet.get("policy_plane")
    ]
    if len(matches) != 1:
        raise CentralProofProjectionError("runtime observation lacks one exact subject")
    subject = matches[0]
    consumer = _validate_packet_target(packet, subject)
    expiry = _effective_expiry(packet, observation, subject)
    if expiry <= now:
        raise CentralProofProjectionError("central proof target evidence is expired")

    proof_digest = _digest(review)
    proof_record = (
        record_root.expanduser().absolute()
        / subject.organ_id
        / (proof_digest.removeprefix("sha256:") + ".json")
    )
    proof_record.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    proof_record.parent.chmod(0o700)
    if proof_record.exists():
        existing, _ = _read_json(proof_record, "immutable central proof record")
        if existing != review:
            raise CentralProofProjectionError("central proof record content conflicts")
    else:
        _write_atomic(proof_record, review)
    proof_ref = proof_record.as_posix()
    evidence = LinkEvidence(
        state="exact",
        observed_at=evaluated_at,
        expires_at=expiry,
        evidence_refs=(
            EvidenceRef(
                owner="aoa-evals",
                evidence_ref=proof_ref,
                revision=proof_digest,
                observed_at=evaluated_at,
                expires_at=expiry,
            ),
        ),
    )
    proof = CentralProofObservation(
        verdict="passed",
        proof_ref=proof_ref,
        evaluated_at=evaluated_at,
        proved_source_revision=subject.source.revision,
        proved_source_tree_digest=subject.source.tree_digest,
        proved_package_digest=subject.package.artifact_digest,
        proved_deploy_revision=subject.deploy.revision,
        proved_deploy_tree_digest=subject.deploy.tree_digest,
        proved_deploy_manifest_digest=subject.deploy.manifest_digest,
        proved_process_identity=subject.process.process_identity,
        proved_server_schema_digest=subject.endpoint.server_schema_digest,
        proved_consumer_registration_ref=consumer.registration_ref,
        proved_canary_route=subject.canary.canary_route,
        proved_canary_ref=subject.canary.canary_ref,
        evidence=evidence,
    )
    overlay = RuntimeEvidenceOverlay(
        generated_at=evaluated_at,
        expires_at=expiry,
        contains_secrets=False,
        subjects=(
            RuntimeEvidenceOverlaySubject(
                organ_id=subject.organ_id,
                policy_family=subject.policy_family,
                proof=proof,
            ),
        ),
    )
    payload = overlay.model_dump(mode="json")
    _reject_secret_material(payload)
    overlay_digest = _digest(payload)
    if output_path is not None:
        _write_atomic(output_path, payload)
    return overlay, overlay_digest, proof_record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--record-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        overlay, digest, record = project_central_proof(
            review_path=args.review,
            packet_path=args.packet,
            observation_path=args.observation,
            eval_root=args.eval_root,
            record_root=args.record_root,
            output_path=args.output,
        )
    except CentralProofProjectionError as exc:
        print(f"central proof projection: {exc}", file=__import__("sys").stderr)
        return 1
    print(f"output={args.output.expanduser().absolute()}")
    print(f"overlay_digest={digest}")
    print(f"proof_record={record}")
    print(f"proof_ref={overlay.subjects[0].proof.proof_ref}")
    print("verdict=passed")
    print("owner_accepted=false")
    print("admission_authorized=false")
    print("contains_secrets=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
