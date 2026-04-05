from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_stack as validate_stack


class ValidateStackRequiredFilesTests(unittest.TestCase):
    def test_current_repo_required_files_pass(self) -> None:
        errors: list[str] = []
        validate_stack.validate_required_files(errors)
        self.assertEqual(errors, [])

    def test_missing_aoa_browser_template_files_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            existing = repo_root / "config-templates" / "Services" / "aoa-browser" / "Dockerfile"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text("FROM scratch\n", encoding="utf-8")
            missing = repo_root / "config-templates" / "Services" / "aoa-browser" / "app.py"

            required_files = {existing, missing}
            errors: list[str] = []
            with patch.object(validate_stack, "ROOT", repo_root):
                with patch.object(validate_stack, "REQUIRED_FILES", required_files):
                    validate_stack.validate_required_files(errors)

        self.assertEqual(
            errors,
            ["missing required file: config-templates/Services/aoa-browser/app.py"],
        )
