from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RETURN_POLICY_SURFACE_ROOT = (
    Path("mechanics") / "governed-execution" / "parts" / "return-policy"
)
RETURN_POLICY_SCHEMA_ROOT = RETURN_POLICY_SURFACE_ROOT / "schemas"
RUNTIME_RETURN_POLICY_SCHEMA_PATH = RETURN_POLICY_SCHEMA_ROOT / "runtime-return-policy.schema.json"
RUNTIME_RETURN_EVENT_SCHEMA_PATH = RETURN_POLICY_SCHEMA_ROOT / "runtime-return-event.schema.json"
RENDER_TRUTH_PATH = (
    Path("mechanics") / "config-projection" / "parts" / "rendering" / "docs" / "RENDER_TRUTH.md"
)


def read_text(root: Path, relative_path: Path) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def read_json(root: Path, relative_path: Path) -> dict[str, Any]:
    payload = json.loads((root / relative_path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def validate_return_runtime_contract(errors: list[str], *, root: Path) -> None:
    templates_readme = read_text(root, Path("config-templates") / "README.md")
    if "Configs/agent-api/" not in templates_readme:
        errors.append("config-templates/README.md must mention Configs/agent-api/")
    if "governed-canary-catalog.json" not in templates_readme:
        errors.append("config-templates/README.md must mention governed-canary-catalog.json")

    deployment_doc = read_text(root, Path("docs") / "install" / "DEPLOYMENT.md")
    if "Configs/agent-api/return-policy.yaml" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention Configs/agent-api/return-policy.yaml")

    first_run_doc = read_text(root, Path("docs") / "install" / "FIRST_RUN.md")
    if "Configs/agent-api/return-policy.yaml" not in first_run_doc:
        errors.append("docs/install/FIRST_RUN.md must mention Configs/agent-api/return-policy.yaml")

    render_truth_doc = read_text(root, RENDER_TRUTH_PATH)
    if "return-policy" not in render_truth_doc:
        errors.append(
            "mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md should mention return-policy mounts when the wrapper is enabled"
        )
    if "aoa-status --autonomy" not in render_truth_doc:
        errors.append("mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md must mention aoa-status --autonomy")
    if "/surface-status" not in render_truth_doc:
        errors.append("mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md must mention /surface-status")

    policy_schema = read_json(root, RUNTIME_RETURN_POLICY_SCHEMA_PATH)
    if policy_schema.get("title") != "abyss-stack runtime return policy":
        errors.append("runtime-return-policy.schema.json must describe abyss-stack runtime return policy")
    policy_surface_type = policy_schema.get("properties", {}).get("surface_type", {})
    if policy_surface_type.get("const") != "runtime_return_policy":
        errors.append("runtime-return-policy.schema.json must pin surface_type.const to runtime_return_policy")

    event_schema = read_json(root, RUNTIME_RETURN_EVENT_SCHEMA_PATH)
    if event_schema.get("title") != "abyss-stack runtime return event":
        errors.append("runtime-return-event.schema.json must describe abyss-stack runtime return event")
    event_surface_type = event_schema.get("properties", {}).get("surface_type", {})
    if event_surface_type.get("const") != "runtime_return_event":
        errors.append("runtime-return-event.schema.json must pin surface_type.const to runtime_return_event")
