"""Derive private managed-contour topology from exact runtime overlay evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .managed_catalog import (
    ManagedContourTopology,
    ManagedContourTopologyEntry,
    publish_private_json,
)
from .canary import _bootstrap_unit_name, _fallback_unit_name
from .preflight import PreflightError, _bundle_digest, _safe_json, _sha256_file
from ._runtime_config import PATH_CONFIG


def _organ_read_unit_exec_start_binding(deployed_root: Path) -> str:
    runtime_root = PATH_CONFIG.stack_services_root(deployed_root) / "abyss-stack-mcp"
    return (
        "ExecStart=/usr/bin/flock --shared --no-fork "
        f"{runtime_root}/.runtime-provision.lock "
        f"{runtime_root}/venv/bin/python -I -B -m "
        "abyss_stack_mcp.process_launcher --executable "
        f"{PATH_CONFIG.stack_codex_executable('%i', deployed_root.parent)}"
    )


def _managed_unit_template_path(
    deployed_root: Path,
    production_unit_name: str,
    observed_unit_name: str,
) -> Path:
    unit_root = PATH_CONFIG.stack_configs_root(deployed_root) / "systemd/user"
    if production_unit_name == "abyss-stack-mcp-read.service":
        paths = {
            production_unit_name: unit_root / "abyss-stack-mcp-read.service",
            _bootstrap_unit_name(production_unit_name): (
                unit_root / "abyss-stack-mcp-read-bootstrap.service"
            ),
            _fallback_unit_name(production_unit_name): (
                unit_root / "abyss-stack-mcp-read-fallback.service"
            ),
        }
    elif production_unit_name.startswith("aoa-organ-mcp-read@"):
        paths = {
            production_unit_name: unit_root / "aoa-organ-mcp-read@.service",
            _bootstrap_unit_name(production_unit_name): (
                unit_root / "aoa-organ-mcp-read-bootstrap@.service"
            ),
            _fallback_unit_name(production_unit_name): (
                unit_root / "aoa-organ-mcp-read-fallback@.service"
            ),
        }
    else:
        raise PreflightError("managed production unit is unsupported")
    try:
        return paths[observed_unit_name]
    except KeyError as exc:
        raise PreflightError("managed canary unit is outside recovery bounds") from exc


def derive_managed_topology(
    overlay: dict[str, Any],
    deployment: dict[str, Any],
    *,
    deployed_root: Path,
) -> ManagedContourTopology:
    entries: list[ManagedContourTopologyEntry] = []
    for contour in overlay.get("contours", []):
        if not isinstance(contour, dict):
            raise PreflightError("runtime overlay contour must be an object")
        runtime = contour.get("runtime_identity")
        endpoint = contour.get("endpoint")
        canary = contour.get("canary_evidence")
        if (
            not isinstance(runtime, dict)
            or not isinstance(endpoint, dict)
            or not isinstance(canary, dict)
        ):
            raise PreflightError("runtime overlay contour is incomplete")
        service = _deployment_service(deployment, runtime.get("package_name"))
        package_root = _bounded_package_root(deployed_root, service)
        schema_paths = _schema_bundle_paths(package_root)
        validator = _owner_validator(package_root)
        organ_id = _required(contour, "organ_id")
        contour_id = _required(contour, "contour_id")
        policy = _required_from_registry_style(contour, contour_id)
        process_ref = _required(runtime, "process_ref")
        canary_receipt_path = _required(canary, "receipt_ref")
        canary_receipt = _safe_json(Path(canary_receipt_path), "canary receipt")
        if canary_receipt.get("receipt_id") != _required(canary, "receipt_id"):
            raise PreflightError("managed canary receipt identity changed")
        canary_process_unit_name = _required(
            canary_receipt, "process_unit_name"
        )
        executable = Path(process_ref)
        if not executable.is_file() or not executable.exists():
            raise PreflightError("managed executable is unavailable")
        resolved_executable = executable.resolve(strict=True)
        if resolved_executable.is_symlink() or not resolved_executable.is_file():
            raise PreflightError("managed executable target is unsafe")
        if organ_id == "abyss-stack":
            binding_id = f"abyss-stack-{contour_id}"
            unit_name = f"abyss-stack-mcp-{contour_id}.service"
            unit_path = _managed_unit_template_path(
                deployed_root, unit_name, canary_process_unit_name
            )
            credential_name = f"abyss-stack-mcp-{policy.replace('_', '-')}-bearer-token"
            auth_manifest = PATH_CONFIG.stack_secrets_root(deployed_root) / (
                "abyss-stack-mcp-auth-manifest.json"
            )
            auth_key = policy
            required_environment = {"ABYSS_STACK_MCP_POLICY_FAMILY": policy}
            unit_credential_binding = (
                f"LoadCredential={credential_name}:"
                f"{PATH_CONFIG.stack_secrets_root(deployed_root) / credential_name}"
            )
            expected_executable = str(
                PATH_CONFIG.stack_services_root(deployed_root)
                / "abyss-stack-mcp/venv/bin/python"
            )
            if process_ref != expected_executable:
                raise PreflightError(
                    "stack unit executable conflicts with its launcher"
                )
            unit_exec_start_binding = (
                "ExecStart=/usr/bin/flock --shared --no-fork "
                f"{PATH_CONFIG.stack_services_root(deployed_root) / 'abyss-stack-mcp'}/.source-projection.lock "
                "/usr/bin/flock --shared --no-fork "
                f"{PATH_CONFIG.stack_services_root(deployed_root) / 'abyss-stack-mcp'}/.runtime-provision.lock "
                f"/usr/bin/env {PATH_CONFIG.stack_configs_root(deployed_root) / 'scripts' / 'aoa-install-systemd'} "
                f"--launch-verified-abyss-stack-mcp={policy}"
            )
        else:
            instance = "tos-corpus" if organ_id == "tree-of-sophia" else organ_id
            binding_id = f"{instance}-{contour_id}"
            unit_name = f"aoa-organ-mcp-{contour_id}@{instance}.service"
            unit_path = _managed_unit_template_path(
                deployed_root, unit_name, canary_process_unit_name
            )
            credential_name = f"{instance}-mcp-{policy.replace('_', '-')}-bearer-token"
            auth_manifest = PATH_CONFIG.stack_secrets_root(deployed_root) / (
                "organ-mcp-read-auth-manifest.json"
            )
            auth_key = instance
            required_environment = {"AOA_MCP_POLICY_FAMILY": policy}
            unit_credential_binding = (
                "LoadCredential=%i-mcp-read-bearer-token:"
                f"{PATH_CONFIG.stack_secrets_root(deployed_root)}/%i-mcp-read-bearer-token"
            )
            expected_executable = str(
                PATH_CONFIG.stack_codex_executable(instance, deployed_root.parent)
            )
            if process_ref != expected_executable:
                raise PreflightError(
                    "organ unit executable conflicts with its instance template"
                )
            unit_exec_start_binding = _organ_read_unit_exec_start_binding(
                deployed_root
            )
        dependency_lock = package_root / "requirements.lock"
        entries.append(
            ManagedContourTopologyEntry(
                binding_id=binding_id,
                organ_id=organ_id,
                contour_id=contour_id,
                service_id=service["service_id"],
                unit_name=unit_name,
                unit_path=str(unit_path),
                endpoint_ref=_required(endpoint, "endpoint_ref"),
                protocol_version=_single_protocol(endpoint),
                credential_path=str(
                    PATH_CONFIG.stack_secrets_root(deployed_root) / credential_name
                ),
                auth_manifest_path=str(auth_manifest),
                auth_manifest_key=auth_key,
                executable_path=process_ref,
                executable_resolved_path=str(resolved_executable),
                executable_digest=_sha256_file(resolved_executable),
                schema_paths=tuple(str(item) for item in schema_paths),
                schema_bundle_digest=_bundle_digest(schema_paths),
                dependency_lock_path=(
                    str(dependency_lock) if dependency_lock.is_file() else None
                ),
                owner_validator_path=str(validator),
                owner_validator_digest=_sha256_file(validator),
                required_environment=required_environment,
                unit_credential_binding=unit_credential_binding,
                unit_exec_start_binding=unit_exec_start_binding,
                canary_receipt_path=canary_receipt_path,
                canary_receipt_id=_required(canary, "receipt_id"),
                canary_process_unit_name=canary_process_unit_name,
                canary_observed_at=_required(canary, "observed_at"),
                canary_expires_at=_required(canary, "expires_at"),
                canary_deployment_manifest_id=_required(
                    canary, "deployment_manifest_id"
                ),
                canary_public_key_path=_required(canary, "public_key_ref"),
                allowed_registry_states=("shadow", "admitted"),
            )
        )
    if not entries:
        raise PreflightError("runtime overlay has no managed contours")
    return ManagedContourTopology(contours=tuple(entries))


def _deployment_service(
    deployment: dict[str, Any], package_name: Any
) -> dict[str, Any]:
    matches = [
        item
        for item in deployment.get("services", [])
        if isinstance(item, dict) and item.get("package_name") == package_name
    ]
    if len(matches) != 1:
        raise PreflightError("runtime overlay package is absent or ambiguous")
    return matches[0]


def _bounded_package_root(root: Path, service: dict[str, Any]) -> Path:
    absolute_root = root.absolute()
    relative = Path(_required(service, "deployed_path"))
    candidate = (absolute_root / relative).absolute()
    if absolute_root not in candidate.parents:
        raise PreflightError("managed package path escapes deployed root")
    if candidate.is_symlink() or not candidate.is_dir():
        raise PreflightError("managed package path is unavailable")
    return candidate


def _schema_bundle_paths(package_root: Path) -> tuple[Path, ...]:
    selected: set[Path] = {package_root / "pyproject.toml"}
    selected.update(package_root.glob("schemas/*.json"))
    selected.update(package_root.glob("organ-access*.json"))
    selected.update(package_root.glob("src/**/organ_access.py"))
    selected.update(package_root.glob("src/**/server.py"))
    paths = tuple(sorted(selected, key=str))
    if not paths or any(path.is_symlink() or not path.is_file() for path in paths):
        raise PreflightError("managed schema bundle is incomplete")
    return paths


def _owner_validator(package_root: Path) -> Path:
    matches = sorted(package_root.glob("scripts/validate*_mcp.py"))
    if len(matches) != 1 or matches[0].is_symlink() or not matches[0].is_file():
        raise PreflightError("managed package owner validator is absent or ambiguous")
    return matches[0]


def _required(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise PreflightError(f"managed topology lacks {key}")
    return value


def _required_from_registry_style(contour: dict[str, Any], contour_id: str) -> str:
    if contour_id == "internal-effect":
        return "internal_effect"
    return contour_id


def _single_protocol(endpoint: dict[str, Any]) -> str:
    values = endpoint.get("protocol_versions")
    if (
        not isinstance(values, list)
        or len(values) != 1
        or not isinstance(values[0], str)
    ):
        raise PreflightError("managed endpoint must bind one protocol version")
    return values[0]


def main() -> int:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-managed-topology")
    parser.add_argument("--runtime-overlay", type=Path, required=True)
    parser.add_argument("--deployment-manifest", type=Path, required=True)
    parser.add_argument("--deployed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        topology = derive_managed_topology(
            _safe_json(args.runtime_overlay, "runtime overlay"),
            _safe_json(args.deployment_manifest, "deployment manifest"),
            deployed_root=args.deployed_root,
        )
        publish_private_json(topology.model_dump(mode="json"), args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(topology.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
