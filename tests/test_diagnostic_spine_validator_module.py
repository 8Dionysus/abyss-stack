from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.validators import diagnostic_spine


REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC_SURFACE_ROOT = (
    Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces"
)
OVERLAY_ROOT = REPO_ROOT


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(payload))


def copy_current_surface(relative_path: Path, *, into: Path) -> None:
    write_text(into / relative_path, (REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def write_valid_surface(repo_root: Path) -> None:
    for relative_path in (
        Path("README.md"),
        Path("docs") / "operations" / "RUNBOOK.md",
        DIAGNOSTIC_SURFACE_ROOT / "docs" / "DIAGNOSTIC_SPINE.md",
        DIAGNOSTIC_SURFACE_ROOT / "generated" / "diagnostic_surface_catalog.min.json",
        DIAGNOSTIC_SURFACE_ROOT / "schemas" / "diagnostic_target.schema.json",
        DIAGNOSTIC_SURFACE_ROOT / "schemas" / "diagnostic_session.schema.json",
        DIAGNOSTIC_SURFACE_ROOT / "schemas" / "diagnosis_companion.schema.json",
        DIAGNOSTIC_SURFACE_ROOT / "schemas" / "diagnostic_anchor_ref.schema.json",
        DIAGNOSTIC_SURFACE_ROOT / "schemas" / "repair_handoff.schema.json",
        DIAGNOSTIC_SURFACE_ROOT / "schemas" / "reviewed_diagnosis_ref.schema.json",
        DIAGNOSTIC_SURFACE_ROOT / "examples" / "diagnostic_target.min.example.json",
        DIAGNOSTIC_SURFACE_ROOT / "examples" / "diagnostic_session.min.example.json",
        DIAGNOSTIC_SURFACE_ROOT / "examples" / "diagnosis_companion.min.example.json",
        DIAGNOSTIC_SURFACE_ROOT / "examples" / "diagnostic_anchor_ref.min.example.json",
        DIAGNOSTIC_SURFACE_ROOT / "examples" / "repair_handoff.min.example.json",
        DIAGNOSTIC_SURFACE_ROOT / "examples" / "reviewed_diagnosis_ref.min.example.json",
    ):
        copy_current_surface(relative_path, into=repo_root)

    write_text(
        repo_root / ".agents" / "skills" / "abyss-self-diagnostic-spine" / "SKILL.md",
        "# stub\n",
    )


def validate_overlay_skill_surface(
    *,
    errors: list[str],
    skill_path: Path,
    description: str,
    expected_target: str | None = None,
) -> None:
    del expected_target
    if not (OVERLAY_ROOT / skill_path / "SKILL.md").is_file():
        errors.append(f"{skill_path.as_posix()} must be installed as a {description}")


def run_validator(repo_root: Path) -> list[str]:
    global OVERLAY_ROOT
    errors: list[str] = []
    OVERLAY_ROOT = repo_root
    diagnostic_spine.validate_diagnostic_spine_contracts(
        errors,
        root=repo_root,
        overlay_skill_surfaces=((Path(".agents") / "skills" / "abyss-self-diagnostic-spine", "local overlay surface", None),),
        overlay_skill_validator=validate_overlay_skill_surface,
    )
    return errors


def test_current_repo_diagnostic_spine_module_passes() -> None:
    assert run_validator(REPO_ROOT) == []


def test_catalog_surface_order_drift_fails(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    catalog_path = (
        tmp_path
        / DIAGNOSTIC_SURFACE_ROOT
        / "generated"
        / "diagnostic_surface_catalog.min.json"
    )
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["surfaces"] = list(reversed(catalog["surfaces"]))
    write_json(catalog_path, catalog)

    errors = run_validator(tmp_path)

    assert (
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json "
        "surface order must stay aligned with the diagnostic spine"
    ) in errors


def test_repair_handoff_readiness_drift_fails(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    handoff_path = (
        tmp_path
        / DIAGNOSTIC_SURFACE_ROOT
        / "examples"
        / "repair_handoff.min.example.json"
    )
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["handoff_readiness"] = "auto_repaired"
    write_json(handoff_path, handoff)

    errors = run_validator(tmp_path)

    assert "repair handoff example must use a supported handoff_readiness" in errors
