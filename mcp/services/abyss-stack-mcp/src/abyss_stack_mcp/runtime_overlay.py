"""Derive a non-admitting v2 runtime identity overlay from exact stack evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .canary import (
    CanaryReceipt,
    CanaryRunnerError,
    _bootstrap_unit_name,
    _fallback_unit_name,
    _read_public_key,
    verify_canary_receipt,
)
from .preflight import PreflightError, _safe_json
from .managed_catalog import publish_private_json
from .observation import (
    ObservationProducerError,
    RuntimeTargetCatalog,
    SystemctlRunner,
    _load_deployment,
    _process_observation,
    _systemctl,
)


DeploymentLoader = Callable[[Path], tuple[dict[str, Any], str]]


def build_runtime_overlay(
    registry: dict[str, Any],
    deployment: dict[str, Any],
    targets: RuntimeTargetCatalog,
    *,
    canary_root: Path,
    canary_public_key_path: Path,
    deployment_manifest_path: Path,
    generated_at: datetime | None = None,
    systemctl_runner: SystemctlRunner = _systemctl,
    deployment_loader: DeploymentLoader = _load_deployment,
) -> tuple[dict[str, Any], tuple[dict[str, str], ...]]:
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        verified_deployment, verified_manifest_id = deployment_loader(
            deployment_manifest_path
        )
    except ObservationProducerError as exc:
        raise PreflightError(str(exc)) from exc
    if verified_deployment != deployment:
        raise PreflightError("deployment payload differs from its verified manifest")
    if verified_deployment.get("manifest_id") != verified_manifest_id:
        raise PreflightError("deployment manifest identity is not content addressed")
    deployment = verified_deployment
    contours: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    try:
        canary_public_key = _read_public_key(canary_public_key_path)
    except CanaryRunnerError as exc:
        raise PreflightError(str(exc)) from exc
    for target in targets.targets:
        contour = _find_contour(
            registry, target.registry_organ_id, target.policy_family
        )
        if contour is None:
            skipped.append(
                {
                    "organ_id": target.registry_organ_id,
                    "contour_id": target.policy_family,
                    "reason_code": "registry_contour_absent",
                }
            )
            continue
        canary_path = canary_root / f"{target.organ_id}.{target.policy_family}.json"
        if not canary_path.is_file() or canary_path.is_symlink():
            skipped.append(
                {
                    "organ_id": target.registry_organ_id,
                    "contour_id": target.policy_family,
                    "reason_code": "canary_evidence_absent",
                }
            )
            continue
        try:
            receipt = CanaryReceipt.model_validate(
                _safe_json(canary_path, "canary receipt")
            )
            verify_canary_receipt(
                receipt,
                canary_public_key,
                checked_at=now,
                require_success=True,
            )
        except (CanaryRunnerError, PreflightError, ValidationError):
            skipped.append(
                {
                    "organ_id": target.registry_organ_id,
                    "contour_id": target.policy_family,
                    "reason_code": "canary_evidence_invalid_or_expired",
                }
            )
            continue
        canary = receipt.model_dump(mode="json")
        service = _deployment_service(deployment, receipt.service_id)
        _require_equal(receipt.organ_id, target.organ_id, "canary organ")
        _require_equal(receipt.policy_family, target.policy_family, "canary contour")
        _require_equal(receipt.endpoint_ref, target.endpoint_ref, "canary endpoint")
        if receipt.protocol_version not in target.protocol_versions:
            raise PreflightError("canary protocol is absent from runtime target")
        _require_equal(
            receipt.deployment_manifest_id,
            deployment.get("manifest_id"),
            "canary deployment manifest",
        )
        _require_equal(
            receipt.deployment_service_id,
            service.get("service_id"),
            "canary deployment service",
        )
        _require_equal(
            receipt.deployment_source_revision,
            service.get("package_source_revision"),
            "canary deployment source",
        )
        _require_equal(
            receipt.deployment_package_digest,
            service.get("package_digest"),
            "canary deployment package",
        )
        _require_equal(
            receipt.deployment_tree_digest,
            service.get("deployed_tree", {}).get("tree_digest"),
            "canary deployed tree",
        )
        _require_equal(
            receipt.deployment_deployed_at.isoformat(),
            _normalized_timestamp(deployment.get("deployed_at")),
            "canary deployment timestamp",
        )
        server_schema_digest = receipt.server_schema_digest
        runtime = contour.get("runtime_identity")
        if not isinstance(runtime, dict):
            raise PreflightError("registry contour runtime identity is absent")
        manifest_id = deployment.get("manifest_id")
        if not isinstance(manifest_id, str):
            raise PreflightError("deployment manifest identity is absent")
        deployed_tree = service.get("deployed_tree")
        if not isinstance(deployed_tree, dict):
            raise PreflightError("deployment tree identity is absent")
        deployment_revision = service.get("package_source_revision")
        if not isinstance(deployment_revision, str):
            raise PreflightError("deployment revision is absent")
        allowed_process_units = {
            target.unit_name,
            _bootstrap_unit_name(target.unit_name),
            _fallback_unit_name(target.unit_name),
        }
        if receipt.process_unit_name not in allowed_process_units:
            raise PreflightError("canary process unit conflicts with runtime target")
        process_target = target.model_copy(
            update={"unit_name": receipt.process_unit_name}
        )
        process = _process_observation(
            process_target,
            observed_at=now,
            expires_at=now + timedelta(minutes=5),
            deployment_revision=deployment_revision,
            runner=systemctl_runner,
        )
        if not process.active or process.process_identity is None:
            raise PreflightError("managed process identity is not exact")
        _require_equal(
            receipt.process_identity,
            process.process_identity,
            "canary process identity",
        )
        record_ref = deployment.get("record_ref")
        if not isinstance(record_ref, str):
            raise PreflightError("immutable deployment record identity is absent")
        contours.append(
            {
                "organ_id": target.registry_organ_id,
                "contour_id": target.policy_family,
                "principal_id": f"{contour['credential_class']}-principal",
                "endpoint": {
                    "adapter_id": f"{service['service_id']}-direct",
                    "adapter_protocol_version": "aoa_organ_adapter_v1",
                    "connection_mode": "direct_owner",
                    "transport": "streamable-http",
                    "endpoint_ref": target.endpoint_ref,
                    "protocol_versions": list(target.protocol_versions),
                    "server_schema_digest": server_schema_digest,
                },
                "runtime_identity": {
                    "source_revision": runtime["source_revision"],
                    "source_tree_digest": runtime.get("source_tree_digest"),
                    "package_name": service["package_name"],
                    "package_version": service["package_version"],
                    "package_digest": service["package_digest"],
                    "deployment_revision": deployment_revision,
                    "deployment_manifest_ref": record_ref,
                    "deployment_manifest_digest": manifest_id,
                    "deployed_tree_digest": deployed_tree["tree_digest"],
                    "process_ref": target.executable_ref,
                    "process_identity": process.process_identity,
                    "dependency_graph_digest": service.get("dependency_lock_digest"),
                },
                "runtime_evidence_refs": [
                    {
                        "owner": "abyss-stack",
                        "evidence_ref": record_ref,
                        "revision": manifest_id,
                        "observed_at": deployment["deployed_at"],
                    },
                    process.evidence.evidence_refs[0].model_dump(
                        mode="json", exclude_none=True
                    ),
                    {
                        "owner": "abyss-stack",
                        "evidence_ref": str(canary_path),
                        "revision": canary["receipt_id"],
                        "observed_at": canary["observed_at"],
                        "expires_at": canary["expires_at"],
                    },
                ],
                "canary_evidence": {
                    "receipt_ref": str(canary_path),
                    "receipt_id": receipt.receipt_id,
                    "observed_at": receipt.observed_at.isoformat(),
                    "expires_at": receipt.expires_at.isoformat(),
                    "deployment_manifest_id": receipt.deployment_manifest_id,
                    "public_key_ref": str(canary_public_key_path),
                },
                "observation_route": target.canary_route,
                "rollback_route": target.rollback_route,
            }
        )
    if not contours:
        raise PreflightError("no registry contour has exact runtime evidence")
    overlay = {
        "schema_version": "aoa_organ_registry_runtime_overlay_v1",
        "overlay_id": "abyss-stack-runtime-evidence-v1",
        "authored_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "owner_decision_ref": "owner://abyss-stack/decision/ABYSS-STACK-D-0107",
        "contours": contours,
        "admission_asserted": False,
        "proof_asserted": False,
        "acceptance_asserted": False,
        "currentness_refreshed": False,
        "contains_secrets": False,
    }
    return overlay, tuple(skipped)


def _find_contour(
    registry: dict[str, Any], organ_id: str, contour_id: str
) -> dict[str, Any] | None:
    for record in registry.get("records", []):
        if isinstance(record, dict) and record.get("organ_id") == organ_id:
            for contour in record.get("contours", []):
                if (
                    isinstance(contour, dict)
                    and contour.get("contour_id") == contour_id
                ):
                    return contour
    return None


def _deployment_service(deployment: dict[str, Any], service_id: Any) -> dict[str, Any]:
    matches = [
        item
        for item in deployment.get("services", [])
        if isinstance(item, dict) and item.get("service_id") == service_id
    ]
    if len(matches) != 1:
        raise PreflightError("canary deployment service is absent or ambiguous")
    return matches[0]


def _require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise PreflightError(f"{label} conflicts with runtime target")


def _normalized_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise PreflightError("deployment timestamp is absent")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise PreflightError("deployment timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PreflightError("deployment timestamp lacks timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-runtime-overlay")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--deployment-manifest", type=Path, required=True)
    parser.add_argument("--runtime-targets", type=Path, required=True)
    parser.add_argument("--canary-root", type=Path, required=True)
    parser.add_argument("--canary-public-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        registry = _safe_json(args.registry, "v2 organ registry")
        deployment = _safe_json(args.deployment_manifest, "deployment manifest")
        targets = RuntimeTargetCatalog.model_validate(
            _safe_json(args.runtime_targets, "runtime targets")
        )
        overlay, skipped = build_runtime_overlay(
            registry,
            deployment,
            targets,
            canary_root=args.canary_root,
            canary_public_key_path=args.canary_public_key,
            deployment_manifest_path=args.deployment_manifest,
        )
        publish_private_json(overlay, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"overlay": overlay, "skipped": skipped}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
