from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_nested_agents.py"
SPEC = importlib.util.spec_from_file_location("validate_nested_agents", SCRIPT_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_minimal_required_tree(repo_root: Path) -> None:
    _write(repo_root / "AGENTS.md", "# AGENTS.md\nRoot guidance.\n")
    for rel_path, snippets in validator.REQUIRED_AGENTS_DOCS.items():
        _write(
            repo_root / rel_path,
            "# AGENTS.md\n"
            + "\n".join(f"Reference: {snippet}" for snippet in snippets)
            + "\n",
        )


class ValidateNestedAgentsTests(unittest.TestCase):
    def test_minimal_required_tree_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _write_minimal_required_tree(repo_root)
            result = validator.validate(repo_root)
            self.assertEqual((), result.issues)

    def test_missing_root_agents_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = validator.validate(Path(tmp))
            self.assertIn("AGENTS.md: root guidance file is missing", result.issues)

    def test_missing_required_doc_fails_when_required_docs_exist(self) -> None:
        if not validator.REQUIRED_AGENTS_DOCS:
            self.skipTest("repository has no required nested AGENTS.md docs yet")
        first_rel = next(iter(validator.REQUIRED_AGENTS_DOCS))
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _write_minimal_required_tree(repo_root)
            (repo_root / first_rel).unlink()
            result = validator.validate(repo_root)
            self.assertTrue(any(first_rel in issue for issue in result.issues))

    def test_missing_required_snippet_fails_when_required_docs_exist(self) -> None:
        if not validator.REQUIRED_AGENTS_DOCS:
            self.skipTest("repository has no required nested AGENTS.md docs yet")
        first_rel = next(iter(validator.REQUIRED_AGENTS_DOCS))
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _write_minimal_required_tree(repo_root)
            _write(repo_root / first_rel, "# AGENTS.md\nToo thin.\n")
            result = validator.validate(repo_root)
            self.assertTrue(any(first_rel in issue and "missing required snippet" in issue for issue in result.issues))

    def test_advisory_can_become_strict(self) -> None:
        if not validator.ADVISORY_AGENT_DIRS:
            self.skipTest("repository has no advisory AGENTS.md candidates")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _write_minimal_required_tree(repo_root)
            (repo_root / validator.ADVISORY_AGENT_DIRS[0]).mkdir(parents=True, exist_ok=True)
            result = validator.validate(repo_root, strict_advisory=True)
            self.assertTrue(any("high-risk directory" in issue for issue in result.issues))

    def test_known_legacy_archive_agents_are_classified_not_untracked(self) -> None:
        if not validator.LEGACY_ARCHIVE_AGENTS_DOCS:
            self.skipTest("repository has no legacy archive AGENTS.md docs")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _write_minimal_required_tree(repo_root)
            _write(
                repo_root / validator.LEGACY_ARCHIVE_AGENTS_DOCS[0],
                "# AGENTS.md\nLegacy archive route card.\n",
            )

            result = validator.validate(repo_root, fail_on_untracked=True)

            self.assertEqual((), result.issues)
            self.assertEqual((), result.warnings)

    def test_new_unmodeled_agents_still_warns_and_can_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _write_minimal_required_tree(repo_root)
            _write(repo_root / "mechanics/new-surface/AGENTS.md", "# AGENTS.md\nNew surface.\n")

            result = validator.validate(repo_root)
            strict_result = validator.validate(repo_root, fail_on_untracked=True)

            self.assertTrue(any("mechanics/new-surface/AGENTS.md" in warning for warning in result.warnings))
            self.assertTrue(any("mechanics/new-surface/AGENTS.md" in issue for issue in strict_result.issues))

    def test_inherited_chain_budget_covers_unmodeled_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _write_minimal_required_tree(repo_root)
            rel_path = "mcp/services/new-surface/AGENTS.md"
            for parent in ("AGENTS.md", "mcp/AGENTS.md", "mcp/services/AGENTS.md"):
                path = repo_root / parent
                _write(path, path.read_text(encoding="utf-8") + ("parent route\n" * 900))
            _write(repo_root / rel_path, "# AGENTS.md\nLocal delta.\n")

            chain = validator.inherited_agents_chain(
                rel_path,
                validator.discover_nested_agents(repo_root) | {"AGENTS.md"},
            )
            self.assertTrue(
                all(
                    (repo_root / path).stat().st_size
                    < validator.AGENTS_CHAIN_BUDGET_BYTES
                    for path in chain
                )
            )

            result = validator.validate(repo_root)

            self.assertTrue(
                any(
                    rel_path in issue and "inherited AGENTS chain" in issue
                    for issue in result.issues
                )
            )


if __name__ == "__main__":
    unittest.main()
