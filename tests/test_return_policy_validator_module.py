from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.validators import return_policy


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(payload))


def copy_current_surface(relative_path: Path, *, into: Path) -> None:
    write_text(into / relative_path, (REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def write_valid_surface(repo_root: Path) -> None:
    for relative_path in (
        Path("config-templates") / "README.md",
        Path("docs") / "install" / "DEPLOYMENT.md",
        Path("docs") / "install" / "FIRST_RUN.md",
        return_policy.RENDER_TRUTH_PATH,
        return_policy.RUNTIME_RETURN_POLICY_SCHEMA_PATH,
        return_policy.RUNTIME_RETURN_EVENT_SCHEMA_PATH,
    ):
        copy_current_surface(relative_path, into=repo_root)


def run_validator(repo_root: Path) -> list[str]:
    errors: list[str] = []
    return_policy.validate_return_runtime_contract(errors, root=repo_root)
    return errors


def test_current_repo_return_policy_module_passes() -> None:
    assert run_validator(REPO_ROOT) == []


def test_return_policy_schema_surface_type_drift_fails(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    schema_path = tmp_path / return_policy.RUNTIME_RETURN_POLICY_SCHEMA_PATH
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["properties"]["surface_type"]["const"] = "runtime_return_policy_v2"
    write_json(schema_path, schema)

    errors = run_validator(tmp_path)

    assert "runtime-return-policy.schema.json must pin surface_type.const to runtime_return_policy" in errors


def test_render_truth_must_route_autonomy_status(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    render_truth_path = tmp_path / return_policy.RENDER_TRUTH_PATH
    write_text(
        render_truth_path,
        render_truth_path.read_text(encoding="utf-8").replace(
            "aoa-status --autonomy",
            "aoa-status --status",
        ),
    )

    errors = run_validator(tmp_path)

    assert "mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md must mention aoa-status --autonomy" in errors
