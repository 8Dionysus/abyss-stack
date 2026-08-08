"""Derive a non-admitting v2 runtime identity overlay from exact stack evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .preflight import PreflightError, _safe_json
from .managed_catalog import publish_private_json
from .observation import RuntimeTargetCatalog


def build_runtime_overlay(
    registry: dict[str, Any],
    deployment: dict[str, Any],
    targets: RuntimeTargetCatalog,
    *,
    canary_root: Path,
    deployment_manifest_path: Path,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], tuple[dict[str, str], ...]]:
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    contours: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for target in targets.targets:
        contour = _find_contour(registry, target.registry_organ_id, target.policy_family)
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
        canary = _safe_json(canary_path, "canary receipt")
        service = _deployment_service(deployment, canary.get("service_id"))
        _require_equal(canary.get("organ_id"), target.organ_id, "canary organ")
        _require_equal(canary.get("policy_family"), target.policy_family, "canary contour")
        _require_equal(canary.get("endpoint_ref"), target.endpoint_ref, "canary endpoint")
        if canary.get("protocol_version") not in target.protocol_versions:
            raise PreflightError("canary protocol is absent from runtime target")
        server_schema_digest = canary.get("server_schema_digest")
        if not isinstance(server_schema_digest, str):
            raise PreflightError("canary server schema digest is absent")
        runtime = contour.get("runtime_identity")
        if not isinstance(runtime, dict):
            raise PreflightError("registry contour runtime identity is absent")
        manifest_id = deployment.get("manifest_id")
        if not isinstance(manifest_id, str):
            raise PreflightError("deployment manifest identity is absent")
        deployed_tree = service.get("deployed_tree")
        if not isinstance(deployed_tree, dict):
            raise PreflightError("deployment tree identity is absent")
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
                    "deployment_revision": service["package_source_revision"],
                    "deployment_manifest_ref": str(deployment_manifest_path),
                    "deployment_manifest_digest": manifest_id,
                    "deployed_tree_digest": deployed_tree["tree_digest"],
                    "process_ref": target.executable_ref,
                    "process_identity": (
                        f"{canary['server_name']}/{canary['server_version']}"
                    ),
                    "dependency_graph_digest": service.get("dependency_lock_digest"),
                },
                "runtime_evidence_refs": [
                    {
                        "owner": "abyss-stack",
                        "evidence_ref": str(deployment_manifest_path),
                        "revision": manifest_id,
                        "observed_at": deployment["deployed_at"],
                    },
                    {
                        "owner": "abyss-stack",
                        "evidence_ref": str(canary_path),
                        "revision": canary["receipt_id"],
                        "observed_at": canary["observed_at"],
                        "expires_at": canary["expires_at"],
                    },
                ],
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
                if isinstance(contour, dict) and contour.get("contour_id") == contour_id:
                    return contour
    return None


def _deployment_service(
    deployment: dict[str, Any], service_id: Any
) -> dict[str, Any]:
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-runtime-overlay")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--deployment-manifest", type=Path, required=True)
    parser.add_argument("--runtime-targets", type=Path, required=True)
    parser.add_argument("--canary-root", type=Path, required=True)
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
            deployment_manifest_path=args.deployment_manifest,
        )
        publish_private_json(overlay, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"overlay": overlay, "skipped": skipped}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
