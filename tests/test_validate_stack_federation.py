from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_stack as validate_stack


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ValidateStackFederationRequiredFilesTests(unittest.TestCase):
    def validate_surface(self, repo_root: Path) -> list[str]:
        errors: list[str] = []
        with patch.object(validate_stack, "ROOT", repo_root):
            validate_stack.validate_federation_required_files(errors)
        return errors

    def write_valid_surface(self, repo_root: Path) -> None:
        for relative_path in validate_stack.FEDERATION_REQUIRED_RUNTIME_INPUTS:
            source_path = REPO_ROOT / relative_path
            write_text(repo_root / relative_path, source_path.read_text(encoding="utf-8"))

    def test_current_repo_federation_required_files_pass(self) -> None:
        errors: list[str] = []
        validate_stack.validate_federation_required_files(errors)
        self.assertEqual(errors, [])

    def test_missing_runtime_template_index_contract_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            aoa_evals_path = (
                repo_root / "config-templates" / "Configs" / "federation" / "aoa-evals.yaml"
            )
            write_text(
                aoa_evals_path,
                aoa_evals_path
                .read_text(encoding="utf-8")
                .replace("  - generated/runtime_candidate_template_index.min.json\n", ""),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("generated/runtime_candidate_template_index.min.json" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
