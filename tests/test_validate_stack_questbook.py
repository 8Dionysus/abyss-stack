from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_stack as validate_stack


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ValidateStackQuestbookTestCase(unittest.TestCase):
    def write_valid_surface(self, repo_root: Path) -> None:
        for relative_path in (
            Path("QUESTBOOK.md"),
            Path("docs") / "QUESTBOOK_STACK_INTEGRATION.md",
            Path("docs") / "RPG_RUNTIME_FRONTEND_POSTURE.md",
            Path("schemas") / "quest.schema.json",
            Path("schemas") / "quest_dispatch.schema.json",
            Path("schemas") / "agent_build_snapshot.schema.json",
            Path("schemas") / "reputation_ledger.schema.json",
            Path("schemas") / "quest_run_result.schema.json",
            Path("schemas") / "frontend_projection_bundle.schema.json",
            Path("examples") / "quest_catalog.min.example.json",
            Path("examples") / "quest_dispatch.min.example.json",
            Path("examples") / "agent_build_snapshot.example.json",
            Path("examples") / "reputation_ledger.example.json",
            Path("examples") / "quest_run_result.example.json",
            Path("examples") / "frontend_projection_bundle.example.json",
        ):
            write_text(
                repo_root / relative_path,
                (REPO_ROOT / relative_path).read_text(encoding="utf-8"),
            )

        for quest_id in validate_stack.QUEST_IDS:
            relative_path = Path("quests") / f"{quest_id}.yaml"
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
            (repo_root / "quests" / "ABYSS-STACK-Q-0003.yaml").unlink()
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("ABYSS-STACK-Q-0003.yaml" in error for error in errors))

    def test_wrong_repo_value_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "quests" / "ABYSS-STACK-Q-0002.yaml",
                (repo_root / "quests" / "ABYSS-STACK-Q-0002.yaml")
                .read_text(encoding="utf-8")
                .replace("repo: abyss-stack", "repo: aoa-kag"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("repo must equal 'abyss-stack'" in error for error in errors))

    def test_id_filename_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "quests" / "ABYSS-STACK-Q-0004.yaml",
                (repo_root / "quests" / "ABYSS-STACK-Q-0004.yaml")
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
                repo_root / "quests" / "ABYSS-STACK-Q-0001.yaml",
                (repo_root / "quests" / "ABYSS-STACK-Q-0001.yaml")
                .read_text(encoding="utf-8")
                .replace("public_safe: true", "public_safe: false"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("public_safe must be true" in error for error in errors))

    def test_missing_tracked_quest_reference_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "QUESTBOOK.md",
                (repo_root / "QUESTBOOK.md")
                .read_text(encoding="utf-8")
                .replace("`ABYSS-STACK-Q-0004`", "`ABYSS-STACK-Q-XXXX`"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("ABYSS-STACK-Q-0004" in error for error in errors))

    def test_human_gate_posture_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "quests" / "ABYSS-STACK-Q-0003.yaml",
                (repo_root / "quests" / "ABYSS-STACK-Q-0003.yaml")
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
                (repo_root / "examples" / "quest_dispatch.min.example.json").read_text(
                    encoding="utf-8"
                )
            )
            payload[3]["source_path"] = "quests/ABYSS-STACK-Q-9999.yaml"
            write_text(
                repo_root / "examples" / "quest_dispatch.min.example.json",
                json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("examples/quest_dispatch.min.example.json" in error for error in errors)
        )

    def test_missing_rpg_runtime_frontend_posture_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            (repo_root / "docs" / "RPG_RUNTIME_FRONTEND_POSTURE.md").unlink()
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("docs/RPG_RUNTIME_FRONTEND_POSTURE.md" in error for error in errors)
        )

    def test_runtime_example_schema_version_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "examples" / "agent_build_snapshot.example.json",
                (repo_root / "examples" / "agent_build_snapshot.example.json")
                .read_text(encoding="utf-8")
                .replace(
                    '"schema_version": "agent_build_snapshot_v1"',
                    '"schema_version": "agent_build_snapshot_v999"',
                ),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("examples/agent_build_snapshot.example.json schema_version must equal 'agent_build_snapshot_v1'" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
