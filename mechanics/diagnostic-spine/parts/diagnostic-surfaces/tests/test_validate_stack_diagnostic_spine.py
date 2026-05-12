from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_stack as validate_stack


REPO_ROOT = Path(__file__).resolve().parents[5]


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ValidateStackDiagnosticSpineTests(unittest.TestCase):
    def write_valid_surface(self, repo_root: Path) -> None:
        for relative_path in (
            Path("README.md"),
            Path("docs") / "DIAGNOSTIC_SPINE.md",
            Path("docs") / "RUNBOOK.md",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "generated" / "diagnostic_surface_catalog.min.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "diagnostic_target.schema.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "diagnostic_session.schema.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "diagnosis_companion.schema.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "diagnostic_anchor_ref.schema.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "repair_handoff.schema.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "reviewed_diagnosis_ref.schema.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "diagnostic_target.min.example.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "diagnostic_session.min.example.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "diagnosis_companion.min.example.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "diagnostic_anchor_ref.min.example.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "repair_handoff.min.example.json",
            Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "reviewed_diagnosis_ref.min.example.json",
        ):
            write_text(
                repo_root / relative_path,
                (REPO_ROOT / relative_path).read_text(encoding="utf-8"),
            )
        write_text(
            repo_root / ".agents" / "skills" / "abyss-self-diagnostic-spine" / "SKILL.md",
            "# stub\n",
        )

    def validate_surface(self, repo_root: Path) -> list[str]:
        errors: list[str] = []
        with patch.object(validate_stack, "ROOT", repo_root):
            validate_stack.validate_diagnostic_spine_contracts(errors)
        return errors

    def test_current_repo_diagnostic_spine_contracts_pass(self) -> None:
        errors: list[str] = []
        validate_stack.validate_diagnostic_spine_contracts(errors)
        self.assertEqual(errors, [])

    def test_missing_diagnostic_doc_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            (repo_root / "docs" / "DIAGNOSTIC_SPINE.md").unlink()
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("docs/DIAGNOSTIC_SPINE.md" in error for error in errors))

    def test_missing_diagnostic_surface_catalog_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            (
                repo_root
                / "mechanics"
                / "diagnostic-spine"
                / "parts"
                / "diagnostic-surfaces"
                / "generated"
                / "diagnostic_surface_catalog.min.json"
            ).unlink()
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json" in error for error in errors))

    def test_session_example_exit_class_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root
                / "mechanics"
                / "diagnostic-spine"
                / "parts"
                / "diagnostic-surfaces"
                / "examples"
                / "diagnostic_session.min.example.json",
                (
                    repo_root
                    / "mechanics"
                    / "diagnostic-spine"
                    / "parts"
                    / "diagnostic-surfaces"
                    / "examples"
                    / "diagnostic_session.min.example.json"
                )
                .read_text(encoding="utf-8")
                .replace(
                    '"exit_class": "repairable_under_governance"',
                    '"exit_class": "mystery_mode"',
                ),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("diagnostic session example must use a supported exit_class" in error for error in errors))

    def test_missing_local_overlay_skill_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            (repo_root / ".agents" / "skills" / "abyss-self-diagnostic-spine" / "SKILL.md").unlink()
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any(".agents/skills/abyss-self-diagnostic-spine" in error for error in errors)
        )
