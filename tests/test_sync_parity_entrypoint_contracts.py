from __future__ import annotations

import argparse
import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_stack as validate_stack
from scripts.validators import sync_parity


REPO_ROOT = Path(__file__).resolve().parents[1]
SYNC_CONFIGS = (
    REPO_ROOT
    / "mechanics"
    / "config-projection"
    / "parts"
    / "sync"
    / "aoa_sync_configs.sh"
)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class SyncParityEntrypointContractsTests(unittest.TestCase):
    def test_sync_subset_supports_non_mutating_preview_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            configs = Path(tmpdir) / "Configs"
            configs.mkdir()
            env = os.environ.copy()
            env["AOA_STACK_ROOT"] = str(Path(tmpdir) / "runtime")
            env["AOA_CONFIGS_ROOT"] = str(configs)

            preview = subprocess.run(
                ["bash", str(SYNC_CONFIGS), "--dry-run", "--item", "README.md"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertFalse((configs / "README.md").exists())
            self.assertIn("dry-run: enabled", preview.stdout)
            self.assertIn("selected items: README.md", preview.stdout)
            self.assertIn("no files changed", preview.stdout)

            applied = subprocess.run(
                ["bash", str(SYNC_CONFIGS), "--item=README.md"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(
                (configs / "README.md").read_bytes(),
                (REPO_ROOT / "README.md").read_bytes(),
            )

    def test_sync_subset_rejects_unknown_managed_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            configs = Path(tmpdir) / "Configs"
            configs.mkdir()
            env = os.environ.copy()
            env["AOA_STACK_ROOT"] = str(Path(tmpdir) / "runtime")
            env["AOA_CONFIGS_ROOT"] = str(configs)

            result = subprocess.run(
                ["bash", str(SYNC_CONFIGS), "--item", "Secrets"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown sync item: Secrets", result.stderr)

    def test_sync_projection_excludes_generated_cache_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            backend = source / "mechanics" / "config-projection" / "parts" / "sync" / SYNC_CONFIGS.name
            backend.parent.mkdir(parents=True)
            shutil.copyfile(SYNC_CONFIGS, backend)
            aoa_lib = source / "scripts" / "aoa-lib.sh"
            aoa_lib.parent.mkdir(parents=True)
            shutil.copyfile(REPO_ROOT / "scripts" / "aoa-lib.sh", aoa_lib)
            write_text(source / "mcp" / "owner" / "server.py", "print('source')\n")
            write_text(source / "mcp" / "owner" / "__pycache__" / "server.pyc", "cache\n")
            write_text(source / "mcp" / "owner" / ".pytest_cache" / "marker", "cache\n")
            write_text(source / "mcp" / "owner" / ".mypy_cache" / "marker", "cache\n")
            write_text(source / "mcp" / "owner" / ".ruff_cache" / "marker", "cache\n")
            write_text(source / "mcp" / "owner" / ".coverage", "cache\n")

            configs = root / "runtime" / "Configs"
            env = os.environ.copy()
            env["AOA_STACK_ROOT"] = str(root / "runtime")
            env["AOA_CONFIGS_ROOT"] = str(configs)
            result = subprocess.run(
                ["bash", str(backend), "--item", "mcp"],
                cwd=source,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((configs / "mcp" / "owner" / "server.py").is_file())
            self.assertFalse((configs / "mcp" / "owner" / "__pycache__").exists())
            self.assertFalse((configs / "mcp" / "owner" / ".pytest_cache").exists())
            self.assertFalse((configs / "mcp" / "owner" / ".mypy_cache").exists())
            self.assertFalse((configs / "mcp" / "owner" / ".ruff_cache").exists())
            self.assertFalse((configs / "mcp" / "owner" / ".coverage").exists())

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
            sync_parity.validate_deployed_parity(
                errors,
                root=repo_root,
                deployed_root=deployed_root,
                sync_file_iter_func=lambda: sync_parity.iter_sync_managed_files(
                    root=repo_root,
                    sync_managed_items=("README.md", "docs"),
                    ignored_parts=sync_parity.PARITY_IGNORED_PARTS,
                    ignored_suffixes=sync_parity.PARITY_IGNORED_SUFFIXES,
                ),
            )

        self.assertEqual(errors, [])

    def test_validate_deployed_parity_reports_source_deployed_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "source"
            deployed_root = root / "runtime" / "Configs"

            write_text(repo_root / "README.md", "# abyss-stack\n")
            write_text(deployed_root / "README.md", "# drifted\n")

            errors: list[str] = []
            sync_parity.validate_deployed_parity(
                errors,
                root=repo_root,
                deployed_root=deployed_root,
                sync_file_iter_func=lambda: sync_parity.iter_sync_managed_files(
                    root=repo_root,
                    sync_managed_items=("README.md",),
                    ignored_parts=sync_parity.PARITY_IGNORED_PARTS,
                    ignored_suffixes=sync_parity.PARITY_IGNORED_SUFFIXES,
                ),
            )

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
