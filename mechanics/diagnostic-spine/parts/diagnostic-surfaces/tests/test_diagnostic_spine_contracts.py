from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[5]


def load_json(relative_path: str) -> object:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


class DiagnosticSpineContractTests(unittest.TestCase):
    def test_diagnostic_examples_validate_against_schemas(self) -> None:
        schema_pairs = [
            (
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_target.schema.json",
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_target.min.example.json",
            ),
            (
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_session.schema.json",
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_session.min.example.json",
            ),
            (
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnosis_companion.schema.json",
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnosis_companion.min.example.json",
            ),
            (
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_anchor_ref.schema.json",
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_anchor_ref.min.example.json",
            ),
            (
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/repair_handoff.schema.json",
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/repair_handoff.min.example.json",
            ),
            (
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/reviewed_diagnosis_ref.schema.json",
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/reviewed_diagnosis_ref.min.example.json",
            ),
        ]

        for schema_path, example_path in schema_pairs:
            validator = Draft202012Validator(load_json(schema_path))
            validator.validate(load_json(example_path))

    def test_readme_and_runbook_reference_diagnostic_spine_surfaces(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        runbook = (REPO_ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
        spine_doc = (
            REPO_ROOT
            / "mechanics"
            / "diagnostic-spine"
            / "parts"
            / "diagnostic-surfaces"
            / "docs"
            / "DIAGNOSTIC_SPINE.md"
        ).read_text(encoding="utf-8")

        for fragment in [
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_target.schema.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_session.schema.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnosis_companion.schema.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_anchor_ref.schema.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/repair_handoff.schema.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/reviewed_diagnosis_ref.schema.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_target.min.example.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_session.min.example.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnosis_companion.min.example.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_anchor_ref.min.example.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/repair_handoff.min.example.json",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/reviewed_diagnosis_ref.min.example.json",
            "quests/ABYSS-STACK-Q-0007.yaml",
            "scripts/aoa-diagnose",
        ]:
            self.assertIn(fragment, readme)

        self.assertIn("Logs/diagnostics/latest/", runbook)
        self.assertIn("diagnostic_target.json", runbook)
        self.assertIn("diagnostic_session_v1", runbook)
        self.assertIn("diagnosis_companion.json", runbook)
        self.assertIn("last_good.ref.json", runbook)
        self.assertIn("repair_handoff.json", runbook)
        self.assertIn("reviewed_diagnosis.ref.json", runbook)
        self.assertIn("The goal is not a louder doctor.", spine_doc)
        self.assertIn("The diagnostic spine is a read model with memory.", spine_doc)
        self.assertIn("scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest", spine_doc)
        self.assertIn(
            "scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest --write-last-good-ref",
            spine_doc,
        )
        self.assertIn(
            "scripts/aoa-diagnose --preset intel-full --with-reviewed-diagnosis-ref /path/to/reviewed-diagnosis.packet.json --write-latest",
            spine_doc,
        )
        self.assertIn(
            "scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest --write-reviewed-diagnosis-ref",
            spine_doc,
        )
        self.assertIn("`diagnosis_companion_v1`", spine_doc)
        self.assertIn("`diagnostic_anchor_ref_v1`", spine_doc)
        self.assertIn("`repair_handoff_v1`", spine_doc)
        self.assertIn("`reviewed_diagnosis_ref_v1`", spine_doc)
        self.assertIn("`mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json`", spine_doc)
        self.assertIn(".agents/skills/abyss-self-diagnostic-spine", spine_doc)
        self.assertIn("A strong diagnostic spine gives the system self-location before self-assertion.", spine_doc)

    def test_generated_diagnostic_surface_catalog_stays_aligned(self) -> None:
        payload = load_json("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json")

        self.assertEqual(payload["schema_version"], "abyss_stack_diagnostic_surface_catalog_v1")
        self.assertEqual(payload["owner_repo"], "abyss-stack")
        self.assertEqual(payload["surface_kind"], "runtime_surface")
        self.assertEqual(payload["authority_ref"], "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md")
        self.assertEqual(
            [entry["name"] for entry in payload["surfaces"]],
            [
                "diagnostic_target",
                "diagnostic_session",
                "diagnosis_companion",
                "reviewed_diagnosis_ref",
                "repair_handoff",
            ],
        )
