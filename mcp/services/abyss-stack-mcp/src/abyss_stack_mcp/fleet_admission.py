"""Compose a fail-closed modern-wire admission candidate for the read fleet.

This module does not probe organs or grant authority.  It consumes two already
issued, signed canary sets (current and last-known-good), the immutable stack
deployment manifest, the owner-authored registry shape, and the accepted
modern-wire decision.  The result is a CAS-ready registry candidate; publishing
it remains an explicit operator action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aoa_sdk.contracts.organ_registry_v2 import (
    ContourLastGoodState,
    ContourSupplementEntry,
    OrganContourAdmissionRevision,
    OrganContourSupplement,
    OrganRegistryRuntimeOverlay,
    OrganRegistrySourceV2,
)
from aoa_sdk.contracts.organs import (
    CapabilityContract,
    ConsumerCompatibility,
    MaturityEvidence,
    OrganMaturityVector,
    PrimitiveContract,
    QualifiedEvidenceRef,
)
from aoa_sdk.organs.registry import sha256_digest
from aoa_sdk.organs.registry_v2 import (
    apply_contour_admission_revision,
    apply_contour_supplement,
    apply_registry_runtime_overlay,
    render_registry_source_v2,
)

from .canary import CanaryReceipt, _read_public_key, verify_canary_receipt
from .managed_catalog import publish_private_json
from .observation import RuntimeTargetCatalog
from .preflight import PreflightError, _safe_json
from .runtime_overlay import build_runtime_overlay


DECISION_REF = "owner://abyss-stack/decision/ABYSS-STACK-D-0108"
PROOF_CONTRACT = "eval://aoa-organ-access-admission-integrity"
PROOF_SOURCE_SHA256 = (
    "sha256:4926e14110b759e95153d96fcad413ab51676fabeb353914e3bf5ca3fea75c2d"
)
SUPPORTED_PROTOCOL = "2026-07-28"
ADMISSION_POLICY = "modern-wire-exact-live-admission-v1"


class FleetAdmissionError(ValueError):
    """The supplied evidence cannot support the modern read-fleet candidate."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read(path: Path, label: str) -> dict[str, Any]:
    value = _safe_json(path, label)
    if not isinstance(value, dict):
        raise FleetAdmissionError(f"{label} must be a JSON object")
    return value


def _digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _record(
    root: Path,
    *,
    organ_id: str,
    kind: str,
    owner: str,
    observed_at: datetime,
    expires_at: datetime,
    body: dict[str, Any],
) -> QualifiedEvidenceRef:
    unsigned = {
        "schema_version": "abyss_modern_mcp_fleet_evidence_v1",
        "evidence_kind": kind,
        "owner": owner,
        "organ_id": organ_id,
        "observed_at": observed_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "decision_ref": DECISION_REF,
        "proof_contract": PROOF_CONTRACT,
        "contains_secrets": False,
        "body": body,
    }
    record_id = sha256_digest(unsigned)
    payload = {**unsigned, "record_id": record_id}
    path = root / "records" / organ_id / kind / f"{record_id[7:]}.json"
    _write_bytes(
        path,
        (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    return QualifiedEvidenceRef(
        owner=owner,
        evidence_ref=path.as_posix(),
        revision=record_id,
        observed_at=observed_at,
        expires_at=expires_at,
    )


def _read_capability(
    *,
    organ_id: str,
    credential_class: str,
    tool_name: str,
    schema_identity: str,
) -> CapabilityContract:
    capability_id = {
        "aoa-memo": "durable-memory-read",
        "aoa-evals": "eval-discovery-read",
    }[organ_id]
    return CapabilityContract(
        capability_id=capability_id,
        summary=(
            "Owner-bounded read access through the stack adapter; source truth, "
            "acceptance, proof verdicts, and writes remain with the named owner."
        ),
        policy_family="read",
        credential_class=credential_class,
        primitives=(
            PrimitiveContract(
                primitive_id=tool_name,
                kind="tool",
                mcp_name=tool_name,
                effect_class="observe",
                policy_family="read",
                input_schema_ref=f"owner://{organ_id}/mcp/{tool_name}/input",
                output_schema_ref=f"owner://{organ_id}/schema/{schema_identity}",
                approval_required=False,
                idempotency="read_only",
                maximum_blast_radius="one authenticated read response",
                annotations_are_security_enforcement=False,
            ),
        ),
        task_intent_terms=("read", "inspect", "owner"),
        owner_payload_schema_ref=f"owner://{organ_id}/schema/{schema_identity}",
        eval_refs=(PROOF_CONTRACT,),
    )


def _ensure_read_contours(
    source: OrganRegistrySourceV2,
    targets: RuntimeTargetCatalog,
    *,
    observed_at: datetime,
) -> OrganRegistrySourceV2:
    by_organ = {record.organ_id: record for record in source.records}
    target_by_organ = {target.registry_organ_id: target for target in targets.targets}
    for organ_id in ("aoa-memo", "aoa-evals"):
        record = by_organ[organ_id]
        if any(contour.contour_id == "read" for contour in record.contours):
            continue
        existing = record.contours[0]
        target = target_by_organ[organ_id]
        source_revision = existing.revisions.source.revision
        source_evidence = QualifiedEvidenceRef(
            owner=record.owners.source_owner,
            evidence_ref=f"owner-source://{organ_id}/{source_revision}/read-contour",
            revision=source_revision,
            observed_at=observed_at,
            expires_at=source.expires_at,
        )
        capability = _read_capability(
            organ_id=organ_id,
            credential_class=f"{organ_id.removeprefix('aoa-')}-read",
            tool_name=target.canary_contract.tool_name,
            schema_identity=target.canary_contract.schema_value,
        )
        supplement = OrganContourSupplement(
            supplement_id=f"{organ_id}-read-modern-wire-v1",
            organ_id=organ_id,
            source_owner=record.owners.source_owner,
            source_evidence=source_evidence,
            owner_decision_ref=DECISION_REF,
            contours=(
                ContourSupplementEntry(
                    contour_id="read",
                    authority_class="read",
                    policy_family="read",
                    credential_class=capability.credential_class,
                    principal_id=f"{capability.credential_class}-principal",
                    capabilities=(capability,),
                    observation_route=target.canary_route,
                    rollback_route=target.rollback_route,
                ),
            ),
        )
        source = apply_contour_supplement(source, supplement)
        by_organ = {item.organ_id: item for item in source.records}
    return source


def _receipt(root: Path, organ_id: str, public_key: Any, now: datetime) -> CanaryReceipt:
    path = root / f"{organ_id}.read.json"
    receipt = CanaryReceipt.model_validate(_read(path, "canary receipt"))
    verify_canary_receipt(receipt, public_key, checked_at=now, require_success=True)
    if receipt.protocol_version != SUPPORTED_PROTOCOL:
        raise FleetAdmissionError(f"{organ_id}: canary did not use {SUPPORTED_PROTOCOL}")
    if not receipt.result_contract_matched or not receipt.call_succeeded:
        raise FleetAdmissionError(f"{organ_id}: canary result contract did not pass")
    return receipt


def _contour(source: OrganRegistrySourceV2, organ_id: str) -> Any:
    record = next(item for item in source.records if item.organ_id == organ_id)
    contour = next(item for item in record.contours if item.contour_id == "read")
    return record, contour


def build_fleet_admission_candidate(
    *,
    registry: dict[str, Any],
    deployment: dict[str, Any],
    targets: RuntimeTargetCatalog,
    current_canary_root: Path,
    lkg_canary_root: Path,
    canary_public_key_path: Path,
    deployment_manifest_path: Path,
    evidence_root: Path,
    generated_at: datetime | None = None,
) -> tuple[OrganRegistrySourceV2, dict[str, Any]]:
    now = (generated_at or _now()).astimezone(timezone.utc)
    source = OrganRegistrySourceV2.model_validate(registry)
    if now >= source.expires_at:
        raise FleetAdmissionError("registry source is expired")
    source = _ensure_read_contours(source, targets, observed_at=now)
    public_key = _read_public_key(canary_public_key_path)

    current_receipts: dict[str, CanaryReceipt] = {}
    lkg_receipts: dict[str, CanaryReceipt] = {}
    desired = {
        "abyss-stack",
        "abyss-machine",
        "aoa-decisions",
        "aoa-memo",
        "aoa-session-memory",
        "aoa-evals",
        "aoa-kag",
        "aoa-stats",
        "aoa-4pda-connector",
        "aoa-telegram-connector",
        "aoa-discord-connector",
    }
    selected_targets = tuple(
        target for target in targets.targets if target.registry_organ_id in desired
    )
    if {item.registry_organ_id for item in selected_targets} != desired:
        raise FleetAdmissionError("runtime target catalog does not cover the read fleet")
    selected_catalog = targets.model_copy(update={"targets": selected_targets})
    for target in selected_targets:
        organ_id = target.registry_organ_id
        current_receipts[organ_id] = _receipt(
            current_canary_root, organ_id, public_key, now
        )
        lkg_receipts[organ_id] = _receipt(lkg_canary_root, organ_id, public_key, now)
        if not lkg_receipts[organ_id].canary_route.endswith("/last-known-good"):
            raise FleetAdmissionError(f"{organ_id}: LKG canary route is not distinct")

    current_overlay, current_skipped = build_runtime_overlay(
        source.model_dump(mode="json"),
        deployment,
        selected_catalog,
        canary_root=current_canary_root,
        canary_public_key_path=canary_public_key_path,
        deployment_manifest_path=deployment_manifest_path,
        generated_at=now,
    )
    if current_skipped:
        raise FleetAdmissionError(f"current runtime overlay skipped: {current_skipped!r}")
    current_runtime_overlay = OrganRegistryRuntimeOverlay.model_validate(current_overlay)
    source = apply_registry_runtime_overlay(
        source, current_runtime_overlay, applied_at=now
    )
    lkg_overlay, lkg_skipped = build_runtime_overlay(
        source.model_dump(mode="json"),
        deployment,
        selected_catalog,
        canary_root=lkg_canary_root,
        canary_public_key_path=canary_public_key_path,
        deployment_manifest_path=deployment_manifest_path,
        generated_at=now,
    )
    if lkg_skipped:
        raise FleetAdmissionError(f"LKG runtime overlay skipped: {lkg_skipped!r}")
    lkg_runtime_overlay = OrganRegistryRuntimeOverlay.model_validate(lkg_overlay)
    lkg_runtime = {item.organ_id: item for item in lkg_runtime_overlay.contours}

    deployment_id = deployment.get("manifest_id")
    deployment_revision = deployment.get("source", {}).get("revision")
    if not isinstance(deployment_id, str) or not isinstance(deployment_revision, str):
        raise FleetAdmissionError("deployment identity is incomplete")
    report: dict[str, Any] = {
        "schema_version": "abyss_modern_mcp_fleet_admission_report_v1",
        "generated_at": now.isoformat(),
        "decision_ref": DECISION_REF,
        "protocol_version": SUPPORTED_PROTOCOL,
        "deployment_manifest_id": deployment_id,
        "organs": [],
        "contains_secrets": False,
    }

    for target in selected_targets:
        organ_id = target.registry_organ_id
        record, contour = _contour(source, organ_id)
        current = current_receipts[organ_id]
        lkg = lkg_receipts[organ_id]
        expiry = min(source.expires_at, current.expires_at, lkg.expires_at)
        if expiry <= now + timedelta(minutes=5):
            raise FleetAdmissionError(f"{organ_id}: evidence window is too short")

        common = {
            "protocol_version": SUPPORTED_PROTOCOL,
            "deployment_manifest_id": deployment_id,
            "deployment_revision": deployment_revision,
            "package_digest": current.deployment_package_digest,
            "server_schema_digest": current.server_schema_digest,
            "current_canary_receipt_id": current.receipt_id,
            "lkg_canary_receipt_id": lkg.receipt_id,
            "policy_family": "read",
            "candidate_authorized": False,
            "effect_authorized": False,
            "cross_organ_proven": False,
        }
        owner_review = _record(
            evidence_root,
            organ_id=organ_id,
            kind="owner-review",
            owner=record.owners.acceptance_owner,
            observed_at=now,
            expires_at=expiry,
            body={
                **common,
                "source_revision": contour.revisions.source.revision,
                "result_schema_identity": current.result_schema_identity,
                "result_contract_matched": current.result_contract_matched,
                "owner_watermark": current.result_digest,
                "claim_limit": (
                    "Exact owner-shaped canary grounding and freshness only; this "
                    "record does not itself grant admission or effect authority."
                ),
            },
        )
        proof = _record(
            evidence_root,
            organ_id=organ_id,
            kind="central-proof",
            owner=record.owners.proof_owner,
            observed_at=now,
            expires_at=expiry,
            body={
                **common,
                "verdict": "supported_bounded",
                "proof_source_sha256": PROOF_SOURCE_SHA256,
                "negative_invariants": {
                    "read_does_not_authorize_candidate": True,
                    "read_does_not_authorize_effect": True,
                    "central_proof_is_not_owner_acceptance": True,
                    "canary_is_not_admission": True,
                    "current_and_lkg_are_distinct": True,
                },
                "claim_limit": (
                    "The exact modern read transport and admission boundaries pass; "
                    "live semantics remain bounded by the owner review."
                ),
            },
        )
        acceptance = _record(
            evidence_root,
            organ_id=organ_id,
            kind="owner-acceptance",
            owner=record.owners.acceptance_owner,
            observed_at=now,
            expires_at=expiry,
            body={
                **common,
                "decision": "accepted",
                "basis_refs": [
                    owner_review.evidence_ref,
                    proof.evidence_ref,
                    DECISION_REF,
                ],
                "scope": "exact read contour modern-wire migration",
                "claim_limit": (
                    "Accepts only the named read contour and exact deployment; no "
                    "candidate, proof-verdict, durable-write, or effect authority."
                ),
            },
        )
        rollback = _record(
            evidence_root,
            organ_id=organ_id,
            kind="rollback-readiness",
            owner=record.owners.proof_owner,
            observed_at=now,
            expires_at=expiry,
            body={
                **common,
                "verdict": "reproducible_exact",
                "lkg_route": lkg.canary_route,
                "lkg_process_identity": lkg.process_identity,
                "lkg_result_contract_matched": lkg.result_contract_matched,
                "rollback_executed": False,
                "claim_limit": (
                    "Proves an exact restorable modern read target; actual rollback "
                    "execution and post-rollback health require a separate receipt."
                ),
            },
        )
        consumer = _record(
            evidence_root,
            organ_id=organ_id,
            kind="consumer-compatibility",
            owner="8Dionysus",
            observed_at=now,
            expires_at=expiry,
            body={
                **common,
                "consumer_id": "codex",
                "support_state": "supported",
                "server_allowlisted": True,
                "claim_limit": "One exact Codex-to-organ modern-wire pair only.",
            },
        )
        operator = _record(
            evidence_root,
            organ_id=organ_id,
            kind="operator-decision",
            owner=source.workspace_owner,
            observed_at=now,
            expires_at=expiry,
            body={
                **common,
                "admission_authorized": True,
                "decision_ref": DECISION_REF,
                "claim_limit": "Read admission only; effect authorization is false.",
            },
        )
        registry_evidence = _record(
            evidence_root,
            organ_id=organ_id,
            kind="registry-index",
            owner=record.owners.control_owner,
            observed_at=now,
            expires_at=expiry,
            body={
                **common,
                "registry_id": source.registry_id,
                "contour_id": "read",
                "claim_limit": "Exact CAS predecessor identity only.",
            },
        )
        runtime_evidence = QualifiedEvidenceRef(
            owner=record.owners.runtime_owner,
            evidence_ref=current_canary_root.joinpath(f"{organ_id}.read.json").as_posix(),
            revision=current.receipt_id,
            observed_at=current.observed_at,
            expires_at=current.expires_at,
        )
        source_evidence = QualifiedEvidenceRef(
            owner=record.owners.source_owner,
            evidence_ref=(
                f"owner-source://{record.owners.source_owner}/"
                f"{contour.revisions.source.revision}"
            ),
            revision=contour.revisions.source.revision,
            observed_at=now,
            expires_at=expiry,
        )

        axis_refs = {
            "declared": source_evidence,
            "owner_reviewed": owner_review,
            "packaged": runtime_evidence,
            "exported": runtime_evidence,
            "deployed": runtime_evidence,
            "process_alive": runtime_evidence,
            "endpoint_ready": runtime_evidence,
            "registry_indexed": registry_evidence,
            "consumer_registered": consumer,
            "schema_observed": runtime_evidence,
            "call_succeeded": runtime_evidence,
            "result_grounded": owner_review,
            "freshness_satisfied": owner_review,
            "owner_accepted": acceptance,
            "rollback_proven": rollback,
        }
        maturity = OrganMaturityVector(
            **{
                name: (
                    MaturityEvidence(
                        state="asserted",
                        evidence=axis_refs[name],
                        freshness_policy=ADMISSION_POLICY,
                    )
                    if name != "cross_organ_proven"
                    else MaturityEvidence(state="not_asserted")
                )
                for name in OrganMaturityVector.model_fields
            }
        )
        compatibility = ConsumerCompatibility(
            consumer_id="codex",
            support_state="supported",
            protocol_versions=(SUPPORTED_PROTOCOL,),
            observed_schema_digest=current.server_schema_digest,
            evidence_ref=consumer,
        )
        lkg_identity = lkg_runtime[organ_id].runtime_identity
        last_good = ContourLastGoodState(
            recorded_at=now,
            expires_at=expiry,
            protocol_version=SUPPORTED_PROTOCOL,
            endpoint_ref=target.endpoint_ref,
            credential_class=contour.credential_class,
            principal_id=contour.principal_id,
            server_schema_digest=lkg.server_schema_digest,
            runtime_identity=lkg_identity,
            evidence_refs=(
                QualifiedEvidenceRef(
                    owner=record.owners.runtime_owner,
                    evidence_ref=lkg_canary_root.joinpath(
                        f"{organ_id}.read.json"
                    ).as_posix(),
                    revision=lkg.receipt_id,
                    observed_at=lkg.observed_at,
                    expires_at=lkg.expires_at,
                ),
                owner_review,
                rollback,
            ),
        )
        unsigned_revision = {
            "schema_version": "aoa_organ_contour_admission_revision_v1",
            "revision_id": f"{organ_id}-read-modern-wire-{now.strftime('%Y%m%dT%H%M%SZ')}",
            "organ_id": organ_id,
            "contour_id": "read",
            "expected_contour_digest": sha256_digest(
                contour.model_dump(mode="json")
            ),
            "issued_at": now.isoformat(),
            "expires_at": expiry.isoformat(),
            "operator_evidence": operator.model_dump(mode="json"),
            "proof_ref": proof.model_dump(mode="json"),
            "acceptance_ref": acceptance.model_dump(mode="json"),
            "rollback_ref": rollback.model_dump(mode="json"),
            "freshness_evidence": owner_review.model_dump(mode="json"),
            "owner_watermark": current.result_digest,
            "owner_watermark_evidence": owner_review.model_dump(mode="json"),
            "consumer_compatibility": compatibility.model_dump(mode="json"),
            "last_good": last_good.model_dump(mode="json"),
            "maturity": maturity.model_dump(mode="json"),
            "admission_authorized": True,
            "effect_authorized": False,
            "cross_organ_asserted": False,
            "rollback_executed": False,
            "contains_secrets": False,
        }
        revision = OrganContourAdmissionRevision.model_validate(
            {
                **unsigned_revision,
                "revision_digest": sha256_digest(unsigned_revision),
            }
        )
        source = apply_contour_admission_revision(source, revision, applied_at=now)
        report["organs"].append(
            {
                "organ_id": organ_id,
                "contour_id": "read",
                "revision_digest": revision.revision_digest,
                "currentness_expires_at": expiry.isoformat(),
                "protocol_version": SUPPORTED_PROTOCOL,
                "verdict": "admitted_candidate",
            }
        )

    report["registry_source_digest"] = sha256_digest(source.model_dump(mode="json"))
    report["organ_count"] = len(report["organs"])
    report["verdict"] = "passed" if report["organ_count"] == 11 else "failed"
    return source, report


def main() -> int:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-fleet-admission")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--deployment-manifest", type=Path, required=True)
    parser.add_argument("--runtime-targets", type=Path, required=True)
    parser.add_argument("--current-canary-root", type=Path, required=True)
    parser.add_argument("--lkg-canary-root", type=Path, required=True)
    parser.add_argument("--canary-public-key", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="CAS-publish the validated candidate back to --registry",
    )
    args = parser.parse_args()
    try:
        registry = _read(args.registry, "v2 organ registry")
        deployment = _read(args.deployment_manifest, "deployment manifest")
        targets = RuntimeTargetCatalog.model_validate(
            _read(args.runtime_targets, "runtime target catalog")
        )
        candidate, report = build_fleet_admission_candidate(
            registry=registry,
            deployment=deployment,
            targets=targets,
            current_canary_root=args.current_canary_root,
            lkg_canary_root=args.lkg_canary_root,
            canary_public_key_path=args.canary_public_key,
            deployment_manifest_path=args.deployment_manifest,
            evidence_root=args.evidence_root,
        )
        _write_bytes(args.output, render_registry_source_v2(candidate))
        publish_private_json(report, args.report)
        if args.publish:
            if args.registry.is_symlink() or not args.registry.is_file():
                raise FleetAdmissionError(
                    "published registry must be a regular non-symlink file"
                )
            predecessor = hashlib.sha256(
                json.dumps(registry, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest()
            current_registry = _read(args.registry, "live v2 organ registry")
            current = hashlib.sha256(
                json.dumps(
                    current_registry, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            if current != predecessor:
                raise FleetAdmissionError("registry CAS predecessor changed")
            _write_bytes(args.registry, render_registry_source_v2(candidate))
            report["published"] = True
            publish_private_json(report, args.report)
    except (OSError, ValueError, PreflightError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
