#!/usr/bin/env python3
"""Build the stack runtime-target projection from the shared MCP catalog.

The source manifest contains only stable canary and rollback contracts. Host
paths, ports, units, owner identities, protocol versions, and rollout cohort
membership are derived from the central runtime catalog so a component update
has one edit point and one generated projection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SHARED_ROOT = SERVICE_ROOT.parent / "_shared"
SOURCE_PATH = SERVICE_ROOT / "runtime-targets.source.v1.json"
DEFAULT_OUTPUT = SERVICE_ROOT / "src" / "abyss_stack_mcp" / "runtime-targets.v1.json"

if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from runtime_config import load_catalog, raw_config  # noqa: E402


SOURCE_SCHEMA_VERSION = "abyss_stack_runtime_target_source_v1"
TARGET_SCHEMA_VERSION = "abyss_stack_runtime_targets_v1"
SOURCE_KEYS = {
    "service_id",
    "policy_family",
    "effect_classes",
    "consumer_evidence_owners",
    "canary_route",
    "canary_contract",
    "rollback_route",
}
REQUIRED_SOURCE_KEYS = {
    "service_id",
    "effect_classes",
    "canary_route",
    "canary_contract",
    "rollback_route",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def bootstrap_source(*, source: Path, generated: Path) -> None:
    """Extract the reviewed stable half once during the migration."""

    if source.exists():
        raise FileExistsError(f"runtime target source already exists: {source}")
    current = _read_json(generated)
    targets = current.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("existing runtime target projection has no targets")
    source_targets: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("runtime target projection contains a non-object")
        stable = {key: target[key] for key in SOURCE_KEYS if key in target}
        if REQUIRED_SOURCE_KEYS - set(stable):
            raise ValueError("runtime target projection has an incomplete canary source")
        source_targets.append(stable)
    payload = {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "targets": source_targets,
    }
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_targets(source: Path) -> list[dict[str, Any]]:
    payload = _read_json(source)
    if payload.get("schema_version") != SOURCE_SCHEMA_VERSION:
        raise ValueError("runtime target source schema version is unsupported")
    targets = payload.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("runtime target source has no targets")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("runtime target source contains a non-object")
        unknown = set(target) - SOURCE_KEYS
        if unknown:
            raise ValueError(
                f"runtime target source contains unsupported keys: {sorted(unknown)}"
            )
        missing = REQUIRED_SOURCE_KEYS - set(target)
        if missing:
            raise ValueError(f"runtime target source lacks {sorted(missing)}")
        service_id = target.get("service_id")
        if not isinstance(service_id, str) or not service_id:
            raise ValueError("runtime target source service identity is invalid")
        if service_id in seen:
            raise ValueError(f"runtime target source duplicates service: {service_id}")
        seen.add(service_id)
        result.append(target)
    return result


def _executable_ref(raw: dict[str, Any], catalog: Any, service: Any) -> str:
    paths = raw["paths"]
    deployment = raw["deployment"]
    if service.runtime_executable_mode == "workspace_codex":
        relative = paths["stack_codex_executable_relative_to_workspace_template"].format(
            instance=service.read_unit_instance
        )
        return f"${{{paths['workspace_env_var']}}}/{relative}"
    if service.runtime_executable_mode == "stack_venv":
        relative = deployment["runtime_python_relative_template"].format(
            service_id=service.service_id
        )
        return f"${{{paths['stack_root_env_var']}}}/{relative}"
    raise ValueError(
        f"unsupported runtime executable mode: {service.runtime_executable_mode}"
    )


def render(*, source: Path) -> dict[str, Any]:
    catalog = load_catalog()
    raw = raw_config()
    source_targets = _source_targets(source)
    services = catalog.services
    source_ids = {item["service_id"] for item in source_targets}
    if source_ids != set(services):
        raise ValueError("runtime target source and MCP catalog service sets differ")
    admitted_service_ids = {
        str(item["service_id"])
        for item in raw["deployment"]["client_read_contours"]
    }
    targets: list[dict[str, Any]] = []
    for source_target in source_targets:
        service_id = str(source_target["service_id"])
        service = services[service_id]
        contour = service.contour("read")
        host = catalog.transport.default_host
        url_host = f"[{host}]" if ":" in host else host
        target = {
            "organ_id": service.organ_id,
            "registry_organ_id": service.registry_organ_id,
            "service_id": service_id,
            "policy_family": str(source_target.get("policy_family", "read")),
            "unit_name": service.read_unit_name(service.organ_id),
            "executable_ref": _executable_ref(raw, catalog, service),
            "endpoint_ref": (
                f"http://{url_host}:{contour.port}"
                f"{catalog.transport.streamable_http_path}"
            ),
            "protocol_versions": [catalog.transport.protocol_version],
            "effect_classes": source_target["effect_classes"],
            "canary_route": source_target["canary_route"],
            "canary_contract": source_target["canary_contract"],
            "rollback_route": source_target["rollback_route"],
            "rollout_cohort": (
                "admitted-read"
                if service_id in admitted_service_ids
                else "package-only-shadow"
            ),
        }
        if "consumer_evidence_owners" in source_target:
            target["consumer_evidence_owners"] = source_target[
                "consumer_evidence_owners"
            ]
        targets.append(target)
    return {"schema_version": TARGET_SCHEMA_VERSION, "targets": targets}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap-source", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.bootstrap_source:
        bootstrap_source(source=args.source, generated=args.output)
        return 0
    expected = json.dumps(render(source=args.source), indent=2, sort_keys=True) + "\n"
    if args.check:
        actual = args.output.read_text(encoding="utf-8")
        if actual != expected:
            raise SystemExit(f"generated runtime targets are stale: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
