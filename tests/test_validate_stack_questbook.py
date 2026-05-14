from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_stack as validate_stack


REPO_ROOT = Path(__file__).resolve().parents[1]
RPG_RUNTIME_SURFACE_ROOT = Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime"
RPG_RUNTIME_SCHEMA_ROOT = RPG_RUNTIME_SURFACE_ROOT / "schemas"
RPG_RUNTIME_EXAMPLE_ROOT = RPG_RUNTIME_SURFACE_ROOT / "examples"
RPG_RUNTIME_GENERATED_ROOT = Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime" / "generated"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ValidateStackQuestbookTestCase(unittest.TestCase):
    def write_valid_surface(self, repo_root: Path) -> None:
        for relative_path in (
            Path("QUESTBOOK.md"),
            Path("docs") / "QUESTBOOK_STACK_INTEGRATION.md",
            Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime" / "docs" / "RPG_RUNTIME_FRONTEND_POSTURE.md",
            Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime" / "docs" / "RPG_RUNTIME_COLLECTIONS.md",
            Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime" / "docs" / "RPG_RUNTIME_BUILDERS.md",
            Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime" / "docs" / "RPG_ROUTE_API_SEAM.md",
            Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime" / "docs" / "RPG_FRONTEND_PROJECTION_SEAM.md",
            Path("quests") / "schemas" / "quest.schema.json",
            Path("quests") / "schemas" / "quest_dispatch.schema.json",
            RPG_RUNTIME_SCHEMA_ROOT / "agent_build_snapshot.schema.json",
            RPG_RUNTIME_SCHEMA_ROOT / "reputation_ledger.schema.json",
            RPG_RUNTIME_SCHEMA_ROOT / "quest_run_result.schema.json",
            RPG_RUNTIME_SCHEMA_ROOT / "frontend_projection_bundle.schema.json",
            RPG_RUNTIME_SCHEMA_ROOT / "agent_build_snapshot_collection.schema.json",
            RPG_RUNTIME_SCHEMA_ROOT / "reputation_ledger_collection.schema.json",
            RPG_RUNTIME_SCHEMA_ROOT / "quest_run_result_collection.schema.json",
            RPG_RUNTIME_SCHEMA_ROOT / "frontend_projection_bundle_collection.schema.json",
            Path("quests") / "examples" / "quest_catalog.min.example.json",
            Path("quests") / "examples" / "quest_dispatch.min.example.json",
            RPG_RUNTIME_EXAMPLE_ROOT / "agent_build_snapshot.example.json",
            RPG_RUNTIME_EXAMPLE_ROOT / "reputation_ledger.example.json",
            RPG_RUNTIME_EXAMPLE_ROOT / "quest_run_result.example.json",
            RPG_RUNTIME_EXAMPLE_ROOT / "frontend_projection_bundle.example.json",
            RPG_RUNTIME_GENERATED_ROOT / "agent_build_snapshots.json",
            RPG_RUNTIME_GENERATED_ROOT / "reputation_ledgers.json",
            RPG_RUNTIME_GENERATED_ROOT / "quest_run_results.json",
            RPG_RUNTIME_GENERATED_ROOT / "frontend_projection_bundles.json",
        ):
            write_text(
                repo_root / relative_path,
                (REPO_ROOT / relative_path).read_text(encoding="utf-8"),
            )

        for quest_id in validate_stack.QUEST_IDS:
            relative_path = validate_stack.quest_source_path(quest_id)
            write_text(
                repo_root / relative_path,
                (REPO_ROOT / relative_path).read_text(encoding="utf-8"),
            )

    def validate_surface(self, repo_root: Path) -> list[str]:
        errors: list[str] = []
        with patch.object(validate_stack, "ROOT", repo_root):
            validate_stack.validate_questbook_surface(errors)
        return errors

    def test_valid_questbook_surface_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            self.assertEqual(self.validate_surface(repo_root), [])

    def test_missing_integration_doc_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            (repo_root / "docs" / "QUESTBOOK_STACK_INTEGRATION.md").unlink()
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("docs/QUESTBOOK_STACK_INTEGRATION.md" in error for error in errors)
        )

    def test_missing_quest_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            (repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0003")).unlink()
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("ABYSS-STACK-Q-0003.yaml" in error for error in errors))

    def test_wrong_repo_value_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0002"),
                (repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0002"))
                .read_text(encoding="utf-8")
                .replace("repo: abyss-stack", "repo: aoa-kag"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("repo must equal 'abyss-stack'" in error for error in errors))

    def test_wrong_lane_value_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0002"),
                (repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0002"))
                .read_text(encoding="utf-8")
                .replace("lane: profiles", "lane: stack"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("ABYSS-STACK-Q-0002 lane must equal 'profiles'" in error for error in errors))

    def test_flat_quest_alias_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "quests" / "ABYSS-STACK-Q-0002.yaml",
                (repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0002")).read_text(
                    encoding="utf-8"
                ),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("root quest alias" in error for error in errors))

    def test_id_filename_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0004"),
                (repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0004"))
                .read_text(encoding="utf-8")
                .replace("id: ABYSS-STACK-Q-0004", "id: ABYSS-STACK-Q-9999"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("id must equal 'ABYSS-STACK-Q-0004'" in error for error in errors))

    def test_missing_public_safe_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0001"),
                (repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0001"))
                .read_text(encoding="utf-8")
                .replace("public_safe: true", "public_safe: false"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("public_safe must be true" in error for error in errors))

    def test_closed_quest_reference_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "QUESTBOOK.md",
                (repo_root / "QUESTBOOK.md").read_text(encoding="utf-8")
                + "\n- `ABYSS-STACK-Q-0004` — stale closed quest reference\n",
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("QUESTBOOK.md must not list closed quest id 'ABYSS-STACK-Q-0004'" in error for error in errors))

    def test_human_gate_posture_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0003"),
                (repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0003"))
                .read_text(encoding="utf-8")
                .replace("control_mode: human_gate", "control_mode: codex_supervised"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("ABYSS-STACK-Q-0003 control_mode must stay human_gate" in error for error in errors)
        )

    def test_example_projection_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            payload = json.loads(
                (repo_root / "quests" / "examples" / "quest_dispatch.min.example.json").read_text(
                    encoding="utf-8"
                )
            )
            payload[3]["source_path"] = "quests/ABYSS-STACK-Q-9999.yaml"
            write_text(
                repo_root / "quests" / "examples" / "quest_dispatch.min.example.json",
                json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("quests/examples/quest_dispatch.min.example.json" in error for error in errors)
        )

    def test_missing_rpg_runtime_frontend_posture_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            (
                repo_root
                / "mechanics"
                / "federation-seams"
                / "parts"
                / "rpg-runtime"
                / "docs"
                / "RPG_RUNTIME_FRONTEND_POSTURE.md"
            ).unlink()
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_FRONTEND_POSTURE.md" in error for error in errors)
        )

    def test_runtime_example_schema_version_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / RPG_RUNTIME_EXAMPLE_ROOT / "agent_build_snapshot.example.json",
                (repo_root / RPG_RUNTIME_EXAMPLE_ROOT / "agent_build_snapshot.example.json")
                .read_text(encoding="utf-8")
                .replace(
                    '"schema_version": "agent_build_snapshot_v1"',
                    '"schema_version": "agent_build_snapshot_v999"',
                ),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("mechanics/federation-seams/parts/rpg-runtime/examples/agent_build_snapshot.example.json schema_version must equal 'agent_build_snapshot_v1'" in error for error in errors)
        )

    def test_missing_rpg_runtime_collections_doc_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            (
                repo_root
                / "mechanics"
                / "federation-seams"
                / "parts"
                / "rpg-runtime"
                / "docs"
                / "RPG_RUNTIME_COLLECTIONS.md"
            ).unlink()
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_COLLECTIONS.md" in error for error in errors)
        )

    def test_generated_collection_schema_version_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / RPG_RUNTIME_GENERATED_ROOT / "agent_build_snapshots.json",
                (repo_root / RPG_RUNTIME_GENERATED_ROOT / "agent_build_snapshots.json")
                .read_text(encoding="utf-8")
                .replace(
                    '"schema_version": "agent_build_snapshot_collection_v1"',
                    '"schema_version": "agent_build_snapshot_collection_v999"',
                    1,
                ),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("mechanics/federation-seams/parts/rpg-runtime/generated/agent_build_snapshots.json schema_version must equal 'agent_build_snapshot_collection_v1'" in error for error in errors)
        )

    def test_runtime_projection_anchor_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0006"),
                (repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0006"))
                .read_text(encoding="utf-8")
                .replace("ref: mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_COLLECTIONS.md", "ref: mechanics/federation-seams/parts/rpg-runtime/docs/RPG_ROUTE_API_SEAM.md"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("ABYSS-STACK-Q-0006 must stay anchored to mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_COLLECTIONS.md" in error for error in errors)
        )

    def test_diagnostic_spine_anchor_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0007"),
                (repo_root / validate_stack.quest_source_path("ABYSS-STACK-Q-0007"))
                .read_text(encoding="utf-8")
                .replace("ref: mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md", "ref: mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_COLLECTIONS.md"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("ABYSS-STACK-Q-0007 must stay anchored to mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
