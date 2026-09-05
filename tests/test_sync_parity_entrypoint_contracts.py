from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
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
MCP_DEPLOYMENT_MANIFEST = (
    SYNC_CONFIGS.parent
    / "scripts"
    / "mcp_deployment_manifest.py"
)
PROTOCOL_WATCH_FILES = (
    "mcp/protocol-lab/CONTRACT.md",
    "mcp/protocol-lab/README.md",
    "mcp/protocol-lab/VALIDATION.md",
    "mcp/protocol-lab/protocol-watch-plan.v1.json",
    "mcp/protocol-lab/schemas/protocol-watch-plan.schema.json",
    "mcp/protocol-lab/schemas/protocol-watch-status.schema.json",
    "mcp/protocol-lab/scripts/protocol_watcher.py",
    "mcp/protocol-lab/scripts/validate_protocol_lab.py",
    "mcp/protocol-lab/tests/test_protocol_watcher.py",
    "systemd/user/README.md",
    "systemd/user/abyss-mcp-protocol-watch.service",
)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def protocol_watch_source_fixture(root: Path) -> Path:
    source = root / "source"
    backend = (
        source
        / "mechanics"
        / "config-projection"
        / "parts"
        / "sync"
        / SYNC_CONFIGS.name
    )
    backend.parent.mkdir(parents=True)
    shutil.copyfile(SYNC_CONFIGS, backend)
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "scripts" / "aoa-lib.sh", scripts / "aoa-lib.sh")
    for relative in PROTOCOL_WATCH_FILES:
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, destination)
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Abyss Test"],
        cwd=source,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "abyss-test@example.invalid"],
        cwd=source,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "protocol watch fixture"],
        cwd=source,
        check=True,
    )
    return source


def protocol_watch_runtime_fixture(root: Path) -> tuple[Path, Path, Path]:
    runtime = root / "runtime"
    configs = runtime / "Configs"
    state = runtime / "Logs" / "mcp" / "protocol-watch"
    configs.mkdir(parents=True)
    state.mkdir(parents=True)
    write_text(state / ".lock", "")
    return runtime, configs, state


class SyncParityEntrypointContractsTests(unittest.TestCase):
    def test_protocol_watch_only_preview_is_bounded_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = protocol_watch_source_fixture(root)
            runtime, configs, state = protocol_watch_runtime_fixture(root)
            lock = state / ".lock"
            before_lock = (lock.stat().st_mode & 0o777, lock.stat().st_mtime_ns)
            env = os.environ.copy()
            env["AOA_STACK_ROOT"] = str(runtime)
            env["AOA_CONFIGS_ROOT"] = str(configs)

            result = subprocess.run(
                ["bash", str(source / "mechanics/config-projection/parts/sync/aoa_sync_configs.sh"), "--protocol-watch-only", "--dry-run"],
                cwd=source,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("protocol-watch-only files: 11", result.stdout)
            self.assertIn("protocol-watch-only preview complete; no files changed", result.stdout)
            self.assertEqual(
                sorted(path.relative_to(configs).as_posix() for path in configs.rglob("*")),
                [],
            )
            self.assertEqual(
                (lock.stat().st_mode & 0o777, lock.stat().st_mtime_ns),
                before_lock,
            )
            self.assertFalse((state / "deployments").exists())

    def test_protocol_watch_only_apply_syncs_exact_files_and_preserves_core_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = protocol_watch_source_fixture(root)
            runtime, configs, _state = protocol_watch_runtime_fixture(root)
            core_file = configs / "mcp" / "services" / "core" / "server.py"
            write_text(core_file, "core runtime remains untouched\n")
            core_before = core_file.read_bytes()
            env = os.environ.copy()
            env["AOA_STACK_ROOT"] = str(runtime)
            env["AOA_CONFIGS_ROOT"] = str(configs)

            result = subprocess.run(
                ["bash", str(source / "mechanics/config-projection/parts/sync/aoa_sync_configs.sh"), "--protocol-watch-only"],
                cwd=source,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("whole-stack projection claim: false", result.stdout)
            for relative in PROTOCOL_WATCH_FILES:
                self.assertEqual(
                    (configs / relative).read_bytes(),
                    (source / relative).read_bytes(),
                    relative,
                )
            self.assertEqual(core_file.read_bytes(), core_before)
            latest = (
                runtime
                / "Logs"
                / "mcp"
                / "protocol-watch"
                / "deployments"
                / "latest.json"
            )
            payload = json.loads(latest.read_text(encoding="utf-8"))
            self.assertEqual(payload["scope"], "protocol-watch-only")
            self.assertFalse(payload["whole_stack_projection_claim"])
            self.assertEqual(
                {item["path"] for item in payload["files"]},
                set(PROTOCOL_WATCH_FILES),
            )
            for item in payload["files"]:
                self.assertEqual(item["source_sha256"], item["deployed_sha256"])
            self.assertEqual(len(list(latest.parent.glob("records/*.json"))), 1)

    def test_protocol_watch_only_fails_when_watcher_holds_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = protocol_watch_source_fixture(root)
            runtime, configs, state = protocol_watch_runtime_fixture(root)
            lock = state / ".lock"
            env = os.environ.copy()
            env["AOA_STACK_ROOT"] = str(runtime)
            env["AOA_CONFIGS_ROOT"] = str(configs)
            lock_holder = subprocess.Popen(
                [
                    "/usr/bin/flock",
                    "--exclusive",
                    str(lock),
                    sys.executable,
                    "-c",
                    "import sys; print('locked', flush=True); sys.stdin.buffer.read()",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertIsNotNone(lock_holder.stdout)
            self.assertEqual(lock_holder.stdout.readline().strip(), "locked")
            try:
                result = subprocess.run(
                    ["bash", str(source / "mechanics/config-projection/parts/sync/aoa_sync_configs.sh"), "--protocol-watch-only"],
                    cwd=source,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("protocol watcher is active", result.stderr)
                self.assertFalse((configs / "mcp" / "protocol-lab").exists())
            finally:
                self.assertIsNotNone(lock_holder.stdin)
                lock_holder.stdin.close()
                self.assertEqual(lock_holder.wait(timeout=5), 0)
                lock_holder.stdout.close()
                lock_holder.stderr.close()

    def test_protocol_watch_only_rejects_dirty_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = protocol_watch_source_fixture(root)
            runtime, configs, _state = protocol_watch_runtime_fixture(root)
            write_text(source / "untracked-dirty-file", "must block\n")
            env = os.environ.copy()
            env["AOA_STACK_ROOT"] = str(runtime)
            env["AOA_CONFIGS_ROOT"] = str(configs)

            result = subprocess.run(
                ["bash", str(source / "mechanics/config-projection/parts/sync/aoa_sync_configs.sh"), "--protocol-watch-only", "--dry-run"],
                cwd=source,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("source worktree must be clean", result.stderr)
            self.assertFalse((configs / "mcp" / "protocol-lab").exists())

    def test_mcp_sync_fails_closed_while_runtime_provisioning_holds_lock(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            configs = root / "Configs"
            projection_lock = (
                root
                / "Services"
                / "abyss-stack-mcp"
                / ".source-projection.lock"
            )
            write_text(projection_lock, "")
            env = os.environ.copy()
            env["AOA_STACK_ROOT"] = str(root)
            env["AOA_CONFIGS_ROOT"] = str(configs)
            lock_holder = subprocess.Popen(
                [
                    "/usr/bin/flock",
                    "--exclusive",
                    str(projection_lock),
                    sys.executable,
                    "-c",
                    (
                        "import sys; "
                        "print('locked', flush=True); "
                        "sys.stdin.buffer.read()"
                    ),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertIsNotNone(lock_holder.stdout)
            self.assertEqual(lock_holder.stdout.readline().strip(), "locked")
            try:
                result = subprocess.run(
                    ["bash", str(SYNC_CONFIGS), "--item", "mcp"],
                    cwd=REPO_ROOT,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "runtime provisioning holds the source projection lock",
                    result.stderr,
                )
                self.assertFalse((configs / "mcp").exists())
            finally:
                self.assertIsNotNone(lock_holder.stdin)
                lock_holder.stdin.close()
                self.assertEqual(lock_holder.wait(timeout=5), 0)
                lock_holder.stdout.close()
                lock_holder.stderr.close()

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
            manifest_builder = (
                backend.parent
                / "scripts"
                / MCP_DEPLOYMENT_MANIFEST.name
            )
            manifest_builder.parent.mkdir(parents=True)
            shutil.copyfile(MCP_DEPLOYMENT_MANIFEST, manifest_builder)
            aoa_lib = source / "scripts" / "aoa-lib.sh"
            aoa_lib.parent.mkdir(parents=True)
            shutil.copyfile(REPO_ROOT / "scripts" / "aoa-lib.sh", aoa_lib)
            service = source / "mcp" / "services" / "example-mcp"
            write_text(
                service / "pyproject.toml",
                """\
[project]
name = "example-mcp"
version = "0.1.0"

[project.scripts]
example-mcp-server = "example_mcp.server:main"
""",
            )
            write_text(
                service / "src" / "example_mcp" / "server.py",
                "print('source')\n",
            )
            write_text(service / "__pycache__" / "server.pyc", "cache\n")
            write_text(service / ".pytest_cache" / "marker", "cache\n")
            write_text(service / ".mypy_cache" / "marker", "cache\n")
            write_text(service / ".ruff_cache" / "marker", "cache\n")
            write_text(service / ".coverage", "cache\n")
            subprocess.run(
                ["git", "init", "-q"],
                cwd=source,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Abyss Test"],
                cwd=source,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "abyss-test@example.invalid"],
                cwd=source,
                check=True,
            )
            subprocess.run(["git", "add", "."], cwd=source, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "fixture"],
                cwd=source,
                check=True,
            )

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
            deployed_service = configs / "mcp" / "services" / "example-mcp"
            self.assertTrue(
                (deployed_service / "src" / "example_mcp" / "server.py").is_file()
            )
            self.assertFalse((deployed_service / "__pycache__").exists())
            self.assertFalse((deployed_service / ".pytest_cache").exists())
            self.assertFalse((deployed_service / ".mypy_cache").exists())
            self.assertFalse((deployed_service / ".ruff_cache").exists())
            self.assertFalse((deployed_service / ".coverage").exists())
            projection_lock = (
                root
                / "runtime"
                / "Services"
                / "abyss-stack-mcp"
                / ".source-projection.lock"
            )
            self.assertTrue(projection_lock.is_file())
            self.assertEqual(projection_lock.stat().st_mode & 0o777, 0o600)
            latest_manifest = (
                root
                / "runtime"
                / "Logs"
                / "mcp"
                / "deployments"
                / "latest.json"
            )
            self.assertTrue(latest_manifest.is_file())
            payload = json.loads(latest_manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["parity_state"], "exact")
            self.assertEqual(payload["runtime_observation_state"], "not_observed")
            self.assertEqual(payload["services"][0]["service_id"], "example-mcp")

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
