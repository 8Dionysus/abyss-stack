from __future__ import annotations

import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_stack as validate_stack


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ValidateStackParityTests(unittest.TestCase):
    def test_validate_deployed_parity_accepts_matching_synced_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "source"
            deployed_root = root / "runtime" / "Configs"

            write_text(repo_root / "README.md", "# abyss-stack\n")
            write_text(repo_root / "docs" / "DEPLOYMENT.md", "# deployment\n")
            write_text(deployed_root / "README.md", "# abyss-stack\n")
            write_text(deployed_root / "docs" / "DEPLOYMENT.md", "# deployment\n")

            errors: list[str] = []
            with patch.object(validate_stack, "ROOT", repo_root), patch.object(
                validate_stack,
                "SYNC_MANAGED_ITEMS",
                ("README.md", "docs"),
            ):
                validate_stack.validate_deployed_parity(errors, deployed_root)

        self.assertEqual(errors, [])

    def test_validate_deployed_parity_reports_source_deployed_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "source"
            deployed_root = root / "runtime" / "Configs"

            write_text(repo_root / "README.md", "# abyss-stack\n")
            write_text(deployed_root / "README.md", "# drifted\n")

            errors: list[str] = []
            with patch.object(validate_stack, "ROOT", repo_root), patch.object(
                validate_stack,
                "SYNC_MANAGED_ITEMS",
                ("README.md",),
            ):
                validate_stack.validate_deployed_parity(errors, deployed_root)

        self.assertEqual(errors, ["source/deployed drift for synced path: README.md"])

    def test_parity_check_rejects_runtime_configs_mirror_mode(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), patch.object(
            validate_stack,
            "RUNTIME_CONFIGS_MIRROR_MODE",
            True,
        ), patch.object(
            validate_stack,
            "parse_args",
            return_value=argparse.Namespace(
                parity_check=True,
                deployed_configs_root="/srv/AbyssOS/abyss-stack/Configs",
            ),
        ):
            exit_code = validate_stack.main()

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "--parity-check must be run from the canonical source checkout",
            stdout.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
