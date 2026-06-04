from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.validators import machine_fit


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
        Path("BOUNDARIES.md"),
        Path("docs") / "install" / "FIRST_RUN.md",
        Path("docs") / "operations" / "RUNBOOK.md",
        Path("docs") / "runtime" / "PATHS.md",
        Path("docs") / "runtime" / "STORAGE_LAYOUT.md",
        Path("scripts") / "AGENTS.md",
        machine_fit.REFERENCE_PLATFORM_DOC_PATH,
        machine_fit.REFERENCE_PLATFORM_SPEC_PATH,
        machine_fit.HOST_FACTS_SCHEMA_PATH,
        machine_fit.HOST_FACTS_EXAMPLE_PATH,
        machine_fit.MACHINE_FIT_ROOT / "PARTS.md",
        machine_fit.MACHINE_FIT_EXAMPLE_PATH,
        machine_fit.MACHINE_BRIDGE_DOC_PATH,
        machine_fit.MACHINE_BRIDGE_SCHEMA_PATH,
        machine_fit.MACHINE_BRIDGE_EXAMPLE_PATH,
        machine_fit.PLATFORM_ADAPTATION_POLICY_PATH,
        machine_fit.PLATFORM_ADAPTATION_SCHEMA_PATH,
        machine_fit.PLATFORM_ADAPTATION_EXAMPLE_PATH,
        machine_fit.WINDOWS_PERFORMANCE_PATH,
        machine_fit.DOCTOR_DOC_PATH,
        machine_fit.DOCTOR_SCRIPT_PATH,
        machine_fit.AUTONOMY_STATUS_PATH,
        machine_fit.DIAGNOSE_WRAPPER_PATH,
    ):
        copy_current_surface(relative_path, into=repo_root)


def run_all_machine_fit_validators(repo_root: Path) -> list[str]:
    errors: list[str] = []
    machine_fit.validate_reference_platform(errors, root=repo_root)
    machine_fit.validate_machine_bridge(errors, root=repo_root)
    machine_fit.validate_machine_integration_freshness_gates(errors, root=repo_root)
    machine_fit.validate_platform_adaptations(errors, root=repo_root)
    return errors


def test_current_repo_machine_fit_module_passes() -> None:
    assert run_all_machine_fit_validators(REPO_ROOT) == []


def test_machine_bridge_example_must_stay_read_only(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    bridge_path = tmp_path / machine_fit.MACHINE_BRIDGE_EXAMPLE_PATH
    bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
    bridge["contract"]["stack_side_mutates_machine"] = True
    write_json(bridge_path, bridge)

    errors: list[str] = []
    machine_fit.validate_machine_bridge(errors, root=tmp_path)

    assert "machine-bridge public example must keep stack_side_mutates_machine false" in errors


def test_platform_adaptation_example_keeps_exporter_identity(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    adaptation_path = tmp_path / machine_fit.PLATFORM_ADAPTATION_EXAMPLE_PATH
    adaptation = json.loads(adaptation_path.read_text(encoding="utf-8"))
    adaptation["captured_by"] = "scripts/other-tool"
    write_json(adaptation_path, adaptation)

    errors: list[str] = []
    machine_fit.validate_platform_adaptations(errors, root=tmp_path)

    assert "platform-adaptation.public.json.example must use captured_by scripts/aoa-platform-adaptation" in errors


def test_machine_fit_example_keeps_composition_first_profile_set(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    fit_path = tmp_path / machine_fit.MACHINE_FIT_EXAMPLE_PATH
    fit = json.loads(fit_path.read_text(encoding="utf-8"))
    fit["runtime_recommendation"]["preferred_profile_set"] = ["intel-worker"]
    write_json(fit_path, fit)

    errors: list[str] = []
    machine_fit.validate_reference_platform(errors, root=tmp_path)

    assert "machine-fit public example must use the composition-first intel-full profile set" in errors
