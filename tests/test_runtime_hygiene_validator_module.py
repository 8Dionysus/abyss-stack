from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.validators import runtime_hygiene


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_READOUT_ROOT = (
    Path("mechanics") / "runtime-lifecycle" / "parts" / "status-readouts"
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(payload))


def copy_current_surface(relative_path: Path, *, into: Path) -> None:
    write_text(into / relative_path, (REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def write_valid_surface(repo_root: Path) -> None:
    for relative_path in (
        STATUS_READOUT_ROOT / "docs" / "GATEWAY_CACHE_POLICY.md",
        STATUS_READOUT_ROOT / "docs" / "USAGE_BUDGET_POLICY.md",
        Path("mechanics")
        / "diagnostic-spine"
        / "parts"
        / "doctor-readiness"
        / "docs"
        / "LOCAL_OPS_DOCTOR_SPLIT.md",
        Path("docs") / "runtime" / "SERVICE_CATALOG.md",
        Path("docs") / "operations" / "RUNBOOK.md",
        Path("mechanics") / "diagnostic-spine" / "parts" / "doctor-readiness" / "docs" / "DOCTOR.md",
        STATUS_READOUT_ROOT / "schemas" / "runtime-gateway-cache-status.schema.json",
        STATUS_READOUT_ROOT / "schemas" / "runtime-usage-snapshot.schema.json",
        STATUS_READOUT_ROOT / "examples" / "runtime_gateway_cache_status.gateway-local.example.json",
        STATUS_READOUT_ROOT / "examples" / "runtime_usage_snapshot.workhorse-local.example.json",
    ):
        copy_current_surface(relative_path, into=repo_root)


def run_validator(repo_root: Path) -> list[str]:
    errors: list[str] = []
    runtime_hygiene.validate_runtime_hygiene_contracts(errors, root=repo_root)
    return errors


def test_current_repo_runtime_hygiene_module_passes() -> None:
    assert run_validator(REPO_ROOT) == []


def test_cache_schema_top_level_array_fails_cleanly(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    write_text(
        tmp_path / STATUS_READOUT_ROOT / "schemas" / "runtime-gateway-cache-status.schema.json",
        "[]\n",
    )

    errors = run_validator(tmp_path)

    assert (
        "mechanics/runtime-lifecycle/parts/status-readouts/schemas/runtime-gateway-cache-status.schema.json "
        "must contain a top-level JSON object"
    ) in errors


def test_usage_example_billing_language_fails(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    usage_path = (
        tmp_path
        / STATUS_READOUT_ROOT
        / "examples"
        / "runtime_usage_snapshot.workhorse-local.example.json"
    )
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    usage["notes"] = ["billing dashboard drift"]
    write_json(usage_path, usage)

    errors = run_validator(tmp_path)

    assert "runtime usage snapshot example must stay free of billing semantics" in errors
