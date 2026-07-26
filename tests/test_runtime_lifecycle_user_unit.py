from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SYSTEMD = (
    REPO_ROOT
    / "mechanics"
    / "runtime-lifecycle"
    / "parts"
    / "user-unit"
    / "aoa_install_systemd.sh"
)
STATS_PATH_UNIT = REPO_ROOT / "systemd" / "user" / "aoa-stats-live-refresh.path"
STATS_SERVICE_UNIT = REPO_ROOT / "systemd" / "user" / "aoa-stats-live-refresh.service"
MCP_HTTP_TEMPLATE = REPO_ROOT / "systemd" / "user" / "aoa-mcp-http@.service"
MCP_HTTP_BUNDLE = REPO_ROOT / "systemd" / "user" / "aoa-mcp-http.service"
STACK_MCP_READ_UNIT = REPO_ROOT / "systemd" / "user" / "abyss-stack-mcp-read.service"
STACK_MCP_CANDIDATE_UNIT = (
    REPO_ROOT / "systemd" / "user" / "abyss-stack-mcp-candidate.service"
)
STACK_RUNTIME_UNIT = REPO_ROOT / "systemd" / "user" / "podman-compose-abyss.service"
STACK_RUNTIME_DROPIN = (
    REPO_ROOT
    / "systemd"
    / "user"
    / "podman-compose-abyss.service.d"
    / "99-runtime-lifecycle.conf"
)
GEMMA_DIGEST_UNIT = REPO_ROOT / "systemd" / "user" / "abyss-gemma4-spark-digest.service"
STORAGE_MONITOR_UNIT = REPO_ROOT / "systemd" / "user" / "abyss-storage-monitor.service"
MANAGED_USER_UNITS = REPO_ROOT / "systemd" / "user" / "managed-units.txt"
MCP_HTTP_AUTH_BUILDER = (
    REPO_ROOT / "mcp" / "services" / "_shared" / "build_http_auth_vendors.py"
)
MCP_HTTP_CODEX_CLIENT = (
    REPO_ROOT / "mcp" / "services" / "_shared" / "codex_http_client.sh"
)
MCP_HTTP_AUTH_TOKEN = "test-only-" + ("a" * 54)
MCP_HTTP_CREDENTIAL_NAME = "aoa-mcp-http-bearer-token"
MCP_HTTP_SECRET_RELATIVE = Path("Secrets") / "Configs" / MCP_HTTP_CREDENTIAL_NAME
STACK_MCP_CREDENTIAL_NAMES = (
    "abyss-stack-mcp-read-bearer-token",
    "abyss-stack-mcp-candidate-bearer-token",
)
EXPECTED_STATS_RECEIPT_PATHS = (
    "/srv/AbyssOS/aoa-skills/.aoa/live_receipts/session-harvest-family.jsonl",
    "/srv/AbyssOS/aoa-skills/.aoa/live_receipts/core-skill-applications.jsonl",
    "/srv/AbyssOS/aoa-evals/.aoa/live_receipts/eval-result-receipts.jsonl",
    "/srv/AbyssOS/aoa-playbooks/.aoa/live_receipts/playbook-receipts.jsonl",
    "/srv/AbyssOS/aoa-techniques/.aoa/live_receipts/technique-receipts.jsonl",
    "/srv/AbyssOS/aoa-memo/.aoa/live_receipts/memo-writeback-receipts.jsonl",
)
MCP_SERVER_PACKAGES = {
    "aoa_decisions_mcp": ("aoa-decisions-mcp", 5420),
    "aoa_memo_mcp": ("aoa-memo-mcp", 5421),
    "aoa_session_memory_mcp": ("aoa-session-memory-mcp", 5422),
    "abyss_machine_mcp": ("abyss-machine-mcp", 5423),
    "aoa_evals_mcp": ("aoa-evals-mcp", 5424),
    "aoa_kag_mcp": ("aoa-kag-mcp", 5425),
    "aoa_4pda_connector_mcp": ("aoa-4pda-connector-mcp", 5426),
    "aoa_telegram_connector_mcp": ("aoa-telegram-connector-mcp", 5427),
    "aoa_discord_connector_mcp": ("aoa-discord-connector-mcp", 5428),
    "tos_corpus_mcp": ("tos-corpus-mcp", 5429),
    "aoa_stats_mcp": ("aoa-stats-mcp", 5430),
}
EXPECTED_MCP_HTTP_INSTANCES = {
    "aoa-mcp-http@aoa-decisions.service",
    "aoa-mcp-http@aoa-memo.service",
    "aoa-mcp-http@aoa-session-memory.service",
    "aoa-mcp-http@abyss-machine.service",
    "aoa-mcp-http@aoa-evals.service",
    "aoa-mcp-http@aoa-kag.service",
    "aoa-mcp-http@aoa-stats.service",
    "aoa-mcp-http@aoa-4pda-connector.service",
    "aoa-mcp-http@aoa-telegram-connector.service",
    "aoa-mcp-http@aoa-discord-connector.service",
}


class DummySettings:
    host = "unset"
    port = -1


class DummyServer:
    def __init__(self) -> None:
        self.settings = DummySettings()
        self.transports: list[str] = []

    def run(self, *, transport: str) -> None:
        self.transports.append(transport)


def mcp_environment(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    for name in (
        "AOA_MCP_TRANSPORT",
        "AOA_MCP_HOST",
        "AOA_MCP_PORT",
        "AOA_MCP_HTTP_BEARER_TOKEN",
        "CREDENTIALS_DIRECTORY",
    ):
        env.pop(name, None)
    env.update(overrides)
    return env


def import_mcp_server(package: str, directory: str):
    source_root = REPO_ROOT / "mcp" / "services" / directory / "src"
    source_root_text = str(source_root)
    if source_root_text not in sys.path:
        sys.path.insert(0, source_root_text)
    return importlib.import_module(f"{package}.server")


class RuntimeLifecycleUserUnitTests(unittest.TestCase):
    def run_install_systemd(self, *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env = os.environ.copy()
            env["AOA_STACK_ROOT"] = str(root / "stack")
            env["AOA_CONFIGS_ROOT"] = str(root / "Configs")
            env["HOME"] = str(root / "home")
            env["XDG_CONFIG_HOME"] = str(root / "xdg-config")
            return subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), *args],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_stack_launcher_preserves_container_runtime_helpers(self) -> None:
        unit = STACK_RUNTIME_UNIT.read_text(encoding="utf-8")
        dropin = STACK_RUNTIME_DROPIN.read_text(encoding="utf-8")

        self.assertIn("Delegate=yes", unit)
        self.assertIn("KillMode=process", unit)
        self.assertIn("TimeoutStopFailureMode=terminate", unit)
        self.assertIn(
            "ExecStop=/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-down",
            unit,
        )
        self.assertIn("Delegate=yes", dropin)
        self.assertIn("KillMode=process", dropin)
        self.assertIn("TimeoutStopFailureMode=terminate", dropin)

    def test_installer_links_source_managed_runtime_lifecycle_dropin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            configs = root / "Configs"
            unit_source = configs / "systemd" / "user"
            unit_source.mkdir(parents=True)
            (unit_source / "podman-compose-abyss.service").write_text(
                "[Service]\nType=oneshot\nExecStart=/usr/bin/true\n",
                encoding="utf-8",
            )
            dropin_source = unit_source / "podman-compose-abyss.service.d"
            dropin_source.mkdir()
            lifecycle_source = dropin_source / "99-runtime-lifecycle.conf"
            lifecycle_source.write_text(
                "[Service]\nKillMode=process\nTimeoutStopFailureMode=terminate\n",
                encoding="utf-8",
            )
            fake_bin = root / "bin"
            fake_bin.mkdir()
            systemctl = fake_bin / "systemctl"
            systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            systemctl.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(root / "stack"),
                    "AOA_CONFIGS_ROOT": str(configs),
                    "HOME": str(root / "home"),
                    "XDG_CONFIG_HOME": str(root / "xdg-config"),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                }
            )

            result = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD)],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            lifecycle_target = (
                root
                / "xdg-config"
                / "systemd"
                / "user"
                / "podman-compose-abyss.service.d"
                / "99-runtime-lifecycle.conf"
            )
            self.assertEqual(os.readlink(lifecycle_target), str(lifecycle_source))

    def test_gemma_digest_reserves_background_model_wake(self) -> None:
        unit = GEMMA_DIGEST_UNIT.read_text(encoding="utf-8")
        exec_start = next(
            line.removeprefix("ExecStart=")
            for line in unit.splitlines()
            if line.startswith("ExecStart=")
        )

        self.assertTrue(
            exec_start.startswith("/usr/local/bin/abyss-machine resource launch ")
        )
        self.assertIn("--memory-demand-mib 2048", exec_start)
        self.assertIn(
            "--demand-key abyss-stack:llama-cpp:gemma4-e2b-background-wake", exec_start
        )
        self.assertIn("--demand-owner abyss-stack", exec_start)
        self.assertIn("--success-on-block", exec_start)
        self.assertTrue(
            exec_start.endswith(
                "-- /srv/abyss-machine/tools/abyss-gemma4-spark-resident digest --limit 3 --json"
            )
        )

    def test_storage_monitor_reserves_measured_startup_memory(self) -> None:
        unit = STORAGE_MONITOR_UNIT.read_text(encoding="utf-8")
        exec_start = next(
            line.removeprefix("ExecStart=")
            for line in unit.splitlines()
            if line.startswith("ExecStart=")
        )

        self.assertTrue(
            exec_start.startswith("/usr/local/bin/abyss-machine resource launch ")
        )
        self.assertIn("--memory-demand-mib 2048", exec_start)
        self.assertIn("--demand-key abyss-machine:storage-monitor:hourly", exec_start)
        self.assertIn("--demand-owner abyss-machine-storage", exec_start)
        self.assertIn("--estimate-source measured-systemd-unit-p99", exec_start)
        self.assertIn("--estimate-confidence high", exec_start)
        self.assertIn("--success-on-block", exec_start)
        self.assertTrue(
            exec_start.endswith(
                "-- /usr/local/bin/abyss-machine storage monitor --json"
            )
        )
        self.assertNotIn("MemoryHigh=", unit)
        self.assertNotIn("MemoryMax=", unit)

    def test_empty_preset_assignment_fails_before_runtime_selection(self) -> None:
        result = self.run_install_systemd("--preset=")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("preset must not be empty", result.stderr)

    def test_empty_profile_assignment_fails_before_runtime_selection(self) -> None:
        result = self.run_install_systemd("--profile=")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("profile must not be empty", result.stderr)

    def test_aoa_stats_adapter_delegates_source_selection_to_sibling_owner(
        self,
    ) -> None:
        path_unit = STATS_PATH_UNIT.read_text(encoding="utf-8")
        receipt_paths = tuple(
            line.removeprefix("PathModified=")
            for line in path_unit.splitlines()
            if line.startswith("PathModified=")
        )
        self.assertEqual(receipt_paths, EXPECTED_STATS_RECEIPT_PATHS)
        self.assertNotIn("runtime-wave-closeouts.jsonl", path_unit)

        service_unit = STATS_SERVICE_UNIT.read_text(encoding="utf-8")
        exec_start = next(
            line.removeprefix("ExecStart=")
            for line in service_unit.splitlines()
            if line.startswith("ExecStart=")
        )
        self.assertEqual(
            exec_start,
            "/usr/bin/env python3 /srv/AbyssOS/aoa-stats/scripts/refresh_live_stats.py",
        )
        self.assertIn("WorkingDirectory=/srv/AbyssOS/aoa-stats", service_unit)
        self.assertNotIn("--registry", service_unit)
        self.assertNotIn(str(REPO_ROOT), service_unit)

    def test_all_user_units_preserves_existing_mask(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            configs = root / "Configs"
            unit_source = configs / "systemd" / "user"
            unit_source.mkdir(parents=True)
            for name in (
                "podman-compose-abyss.service",
                "masked.service",
                "linked.service",
            ):
                (unit_source / name).write_text(
                    "[Service]\nType=oneshot\nExecStart=/usr/bin/true\n",
                    encoding="utf-8",
                )
            (unit_source / "managed-units.txt").write_text(
                "masked.service\nlinked.service\n",
                encoding="utf-8",
            )
            target_dir = root / "xdg-config" / "systemd" / "user"
            target_dir.mkdir(parents=True)
            (target_dir / "masked.service").symlink_to("/dev/null")
            fake_bin = root / "bin"
            fake_bin.mkdir()
            systemctl = fake_bin / "systemctl"
            systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            systemctl.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(root / "stack"),
                    "AOA_CONFIGS_ROOT": str(configs),
                    "HOME": str(root / "home"),
                    "XDG_CONFIG_HOME": str(root / "xdg-config"),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                }
            )

            result = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--all-user-units"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(os.readlink(target_dir / "masked.service"), "/dev/null")
            self.assertEqual(
                os.readlink(target_dir / "linked.service"),
                str(unit_source / "linked.service"),
            )
            self.assertIn("preserving masked user unit", result.stdout)

    def test_mcp_http_auth_provision_is_explicit_idempotent_and_secret_safe(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            secret_dir = stack_root / "Secrets" / "Configs"
            secret_dir.mkdir(parents=True, mode=0o750)
            secret_dir.chmod(0o750)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CONFIGS_ROOT": str(root / "Configs"),
                    "HOME": str(root / "home"),
                    "XDG_CONFIG_HOME": str(root / "xdg-config"),
                }
            )
            first = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-mcp-http-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            token_path = stack_root / MCP_HTTP_SECRET_RELATIVE
            token = token_path.read_text(encoding="utf-8").removesuffix("\n")
            self.assertRegex(token, r"\A[A-Za-z0-9._~-]{43,512}\Z")
            self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(secret_dir.stat().st_mode & 0o777, 0o750)
            self.assertNotIn(token, first.stdout + first.stderr)
            self.assertIn("provisioned MCP HTTP bearer credential", first.stdout)
            self.assertNotIn("unit linked", first.stdout)

            second = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-mcp-http-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(
                token_path.read_text(encoding="utf-8").removesuffix("\n"), token
            )
            self.assertNotIn(token, second.stdout + second.stderr)
            self.assertIn("already provisioned", second.stdout)

    def test_mcp_http_auth_concurrent_first_write_keeps_one_valid_winner(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            race_root = root / "race"
            race_root.mkdir()
            fake_bin = root / "bin"
            fake_bin.mkdir()
            python = fake_bin / "python3"
            python.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "touch \"$RACE_ROOT/ready.$$\"\n"
                "while (( $(find \"$RACE_ROOT\" -maxdepth 1 -name 'ready.*' "
                "-type f | wc -l) < 2 )); do\n"
                "  sleep 0.01\n"
                "done\n"
                "printf 'race-%s-' \"$$\"\n"
                "printf '%050d\\n' 0\n",
                encoding="utf-8",
            )
            python.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CONFIGS_ROOT": str(root / "Configs"),
                    "HOME": str(root / "home"),
                    "XDG_CONFIG_HOME": str(root / "xdg-config"),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "RACE_ROOT": str(race_root),
                }
            )
            command = [
                "bash",
                str(INSTALL_SYSTEMD),
                "--provision-mcp-http-auth",
            ]
            processes = [
                subprocess.Popen(
                    command,
                    cwd=REPO_ROOT,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(2)
            ]
            results = [process.communicate(timeout=10) for process in processes]

            for process, (stdout, stderr) in zip(processes, results, strict=True):
                self.assertEqual(process.returncode, 0, stderr)
                self.assertNotIn("race-", stderr)
                self.assertNotRegex(stdout, r"race-[0-9]+-")
            token_path = stack_root / MCP_HTTP_SECRET_RELATIVE
            token = token_path.read_text(encoding="utf-8").removesuffix("\n")
            self.assertRegex(token, r"\A[A-Za-z0-9._~-]{43,512}\Z")
            self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)
            combined_stdout = "".join(stdout for stdout, _ in results)
            self.assertEqual(combined_stdout.count("already provisioned"), 1)
            provisioned_without_already = [
                line
                for line in combined_stdout.splitlines()
                if "provisioned MCP HTTP bearer credential" in line
                and "already" not in line
            ]
            self.assertEqual(len(provisioned_without_already), 1)

    def test_stack_mcp_auth_provisions_distinct_secret_safe_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            secret_dir = stack_root / "Secrets" / "Configs"
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CONFIGS_ROOT": str(root / "Configs"),
                    "HOME": str(root / "home"),
                    "XDG_CONFIG_HOME": str(root / "xdg-config"),
                }
            )

            first = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-abyss-stack-mcp-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(first.returncode, 0, first.stderr)
            credentials = {
                name: secret_dir.joinpath(name)
                .read_text(encoding="utf-8")
                .removesuffix("\n")
                for name in STACK_MCP_CREDENTIAL_NAMES
            }
            self.assertEqual(len(set(credentials.values())), len(credentials))
            self.assertEqual(secret_dir.stat().st_mode & 0o777, 0o700)
            for name, token in credentials.items():
                with self.subTest(name=name):
                    path = secret_dir / name
                    self.assertRegex(token, r"\A[A-Za-z0-9._~-]{43,512}\Z")
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                    self.assertNotIn(token, first.stdout + first.stderr)
            self.assertIn(
                "provisioned abyss-stack MCP read bearer credential", first.stdout
            )
            self.assertIn(
                "provisioned abyss-stack MCP candidate bearer credential",
                first.stdout,
            )
            self.assertNotIn("unit linked", first.stdout)

            second = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-abyss-stack-mcp-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(second.returncode, 0, second.stderr)
            for name, token in credentials.items():
                with self.subTest(name=name):
                    self.assertEqual(
                        secret_dir.joinpath(name)
                        .read_text(encoding="utf-8")
                        .removesuffix("\n"),
                        token,
                    )
                    self.assertNotIn(token, second.stdout + second.stderr)
            self.assertEqual(second.stdout.count("already provisioned"), 2)

    def test_stack_mcp_auth_rejects_matching_contour_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            secret_dir = stack_root / "Secrets" / "Configs"
            secret_dir.mkdir(parents=True, mode=0o700)
            shared_token = "same-contour-token-" + ("a" * 48)
            for name in STACK_MCP_CREDENTIAL_NAMES:
                credential = secret_dir / name
                credential.write_text(shared_token + "\n", encoding="utf-8")
                credential.chmod(0o600)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CONFIGS_ROOT": str(root / "Configs"),
                    "HOME": str(root / "home"),
                    "XDG_CONFIG_HOME": str(root / "xdg-config"),
                }
            )

            result = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-abyss-stack-mcp-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "read and candidate bearer credentials must be distinct",
                result.stderr,
            )
            self.assertNotIn(shared_token, result.stdout + result.stderr)

    def test_stack_mcp_credential_provisioning_is_user_scoped(self) -> None:
        installer = INSTALL_SYSTEMD.read_text(encoding="utf-8")
        self.assertIn(
            "if ((provision_abyss_stack_mcp_auth && EUID == 0)); then",
            installer,
        )
        self.assertIn(
            "abyss-stack MCP credential provisioning must run as the target user, "
            "not root",
            installer,
        )

    def test_stack_mcp_runtime_provision_is_explicit_and_source_addressed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            service_root = (
                stack_root / "Configs" / "mcp" / "services" / "abyss-stack-mcp"
            )
            service_root.mkdir(parents=True)
            (service_root / "pyproject.toml").write_text(
                "[project]\nname = \"abyss-stack-mcp\"\nversion = \"0.1.0\"\n",
                encoding="utf-8",
            )
            lock_path = service_root / "requirements.lock"
            lock_path.write_text(
                "test-package==1.0.0 \\\n"
                "    --hash=sha256:"
                + ("0" * 64)
                + "\n",
                encoding="utf-8",
            )
            source_file = service_root / "service.py"
            source_file.write_text("VALUE = 1\n", encoding="utf-8")
            pip_log = root / "pip.log"
            bootstrap = root / "fake-python"
            bootstrap.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ -n \"${PYTHONHOME+x}\" || "
                "-n \"${PYTHONPATH+x}\" ]]; then\n"
                "  exit 65\n"
                "fi\n"
                "if [[ \"${1:-}\" != \"-I\" ]]; then\n"
                "  exit 66\n"
                "fi\n"
                "shift\n"
                "if [[ \"$1\" == \"-m\" && \"$2\" == \"venv\" ]]; then\n"
                "  mkdir -p \"$3/bin\"\n"
                "  ln -s \"$0\" \"$3/bin/python\"\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$1\" == \"-m\" && \"$2\" == \"pip\" ]]; then\n"
                "  printf '%s\\n' \"$*\" >> \"$ABYSS_STACK_MCP_TEST_PIP_LOG\"\n"
                "  if [[ \"$*\" == *\"--require-hashes\"* ]]; then\n"
                "    package_root=\"$(dirname \"$0\")/../lib/python/site-packages/"
                "test_package\"\n"
                "    mkdir -p \"$package_root\"\n"
                "    printf 'VALUE = 1\\n' > \"$package_root/__init__.py\"\n"
                "  fi\n"
                "  if [[ \"$*\" == *\"--no-deps --no-build-isolation\"* ]]; then\n"
                "    entrypoint=\"$(dirname \"$0\")/abyss-stack-mcp\"\n"
                "    printf '#!%s\\nexit 0\\n' \"$0\" > \"$entrypoint\"\n"
                "    chmod 0755 \"$entrypoint\"\n"
                "  fi\n"
                "  if [[ -n \"${ABYSS_STACK_MCP_TEST_MUTATE_SOURCE_DURING_BUILD:-}\" ]]; then\n"
                "    printf 'VALUE = 99\\n' > "
                "\"$ABYSS_STACK_MCP_TEST_MUTATE_SOURCE_DURING_BUILD\"\n"
                "  fi\n"
                "  if [[ -n \"${ABYSS_STACK_MCP_TEST_ACTIVATE_DURING_BUILD:-}\" ]]; then\n"
                "    : > \"$ABYSS_STACK_MCP_TEST_ACTIVATE_DURING_BUILD\"\n"
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$1\" == \"-c\" ]]; then\n"
                "  exit 0\n"
                "fi\n"
                "exit 64\n",
                encoding="utf-8",
            )
            bootstrap.chmod(0o755)
            bootstrap_link = root / "fake-python-link"
            bootstrap_link.symlink_to(bootstrap)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            unit_source_dir = stack_root / "Configs" / "systemd" / "user"
            unit_source_dir.mkdir(parents=True)
            unit_target_dir = root / "xdg-config" / "systemd" / "user"
            unit_target_dir.mkdir(parents=True)
            for source_unit in (
                STACK_MCP_READ_UNIT,
                STACK_MCP_CANDIDATE_UNIT,
            ):
                source_path = unit_source_dir / source_unit.name
                source_path.write_text(
                    source_unit.read_text(encoding="utf-8").replace(
                        "/srv/AbyssOS/abyss-stack",
                        str(stack_root),
                    ),
                    encoding="utf-8",
                )
                (unit_target_dir / source_unit.name).symlink_to(source_path)
            systemctl = fake_bin / "systemctl"
            systemctl.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "unit=\"${!#}\"\n"
                "if [[ \"${ABYSS_STACK_MCP_TEST_SYSTEMCTL_FAIL:-0}\" == 1 ]]; "
                "then\n"
                "  exit 1\n"
                "fi\n"
                "load_state=loaded\n"
                "active_state=inactive\n"
                "fragment_path=\"${XDG_CONFIG_HOME}/systemd/user/${unit}\"\n"
                "exec_path=/usr/bin/flock\n"
                "exec_start=\"/usr/bin/flock --shared --no-fork "
                "${AOA_STACK_ROOT}/Services/abyss-stack-mcp/"
                ".runtime-provision.lock /usr/bin/env "
                "${AOA_STACK_ROOT}/Services/abyss-stack-mcp/venv/bin/python "
                "-I -B -m abyss_stack_mcp.server\"\n"
                "if [[ \"${ABYSS_STACK_MCP_TEST_UNLOADED_UNIT:-}\" == "
                "\"$unit\" ]]; then\n"
                "  load_state=not-found\n"
                "  fragment_path=\n"
                "  exec_path=\n"
                "  exec_start=\n"
                "fi\n"
                "if [[ \"${ABYSS_STACK_MCP_TEST_STALE_UNIT:-}\" == "
                "\"$unit\" ]]; then\n"
                "  exec_path=/usr/bin/env\n"
                "  exec_start=\"/usr/bin/env "
                "${AOA_STACK_ROOT}/Services/abyss-stack-mcp/venv/bin/python "
                "-I -B -m abyss_stack_mcp.server\"\n"
                "fi\n"
                "if [[ \"${ABYSS_STACK_MCP_TEST_ACTIVE_UNIT:-}\" == "
                "\"$unit\" ]]; then\n"
                "  active_state=active\n"
                "elif [[ \"$unit\" == \"abyss-stack-mcp-read.service\" && "
                "-f \"${ABYSS_STACK_MCP_TEST_ACTIVATE_DURING_BUILD:-"
                "/nonexistent}\" ]]; then\n"
                "  active_state=active\n"
                "fi\n"
                "printf 'LoadState=%s\\n' \"$load_state\"\n"
                "printf 'ActiveState=%s\\n' \"$active_state\"\n"
                "printf 'FragmentPath=%s\\n' \"$fragment_path\"\n"
                "if [[ -n \"$exec_start\" ]]; then\n"
                "  printf 'ExecStart={ path=%s ; argv[]=%s ; "
                "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; "
                "pid=0 ; code=(null) ; status=0/0 }\\n' "
                "\"$exec_path\" \"$exec_start\"\n"
                "else\n"
                "  printf 'ExecStart=\\n'\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            systemctl.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CONFIGS_ROOT": str(stack_root / "Configs"),
                    "ABYSS_STACK_MCP_BOOTSTRAP_PYTHON": str(bootstrap_link),
                    "ABYSS_STACK_MCP_TEST_PIP_LOG": str(pip_log),
                    "HOME": str(root / "home"),
                    "XDG_CONFIG_HOME": str(root / "xdg-config"),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "PYTHONHOME": str(root / "hostile-python-home"),
                    "PYTHONPATH": str(root / "hostile-python-path"),
                }
            )
            command = [
                "bash",
                str(INSTALL_SYSTEMD),
                "--provision-abyss-stack-mcp-runtime",
            ]

            read_unit_source = (
                unit_source_dir / "abyss-stack-mcp-read.service"
            )
            lock_aware_source = read_unit_source.read_text(encoding="utf-8")
            read_unit_source.write_text(
                lock_aware_source.replace(
                    "ExecStart=/usr/bin/flock --shared --no-fork ",
                    "ExecStart=/usr/bin/env ",
                ),
                encoding="utf-8",
            )
            stale_source = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(stale_source.returncode, 0)
            self.assertIn(
                "managed source unit is not lock-aware",
                stale_source.stderr,
            )
            self.assertFalse(pip_log.exists())
            read_unit_source.write_text(
                lock_aware_source,
                encoding="utf-8",
            )

            for environment_key, expected_error in (
                (
                    "ABYSS_STACK_MCP_TEST_UNLOADED_UNIT",
                    "is not loaded; link and reload managed user units",
                ),
                (
                    "ABYSS_STACK_MCP_TEST_STALE_UNIT",
                    "is not loaded with the lock-aware ExecStart",
                ),
            ):
                with self.subTest(environment_key=environment_key):
                    missing_prerequisite = subprocess.run(
                        command,
                        cwd=REPO_ROOT,
                        env={
                            **env,
                            environment_key: "abyss-stack-mcp-read.service",
                        },
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(missing_prerequisite.returncode, 0)
                    self.assertIn(
                        expected_error,
                        missing_prerequisite.stderr,
                    )
                    self.assertFalse(pip_log.exists())

            first = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            venv = stack_root / "Services" / "abyss-stack-mcp" / "venv"
            marker = venv / ".abyss-stack-mcp-runtime-identity"
            content_marker = (
                venv / ".abyss-stack-mcp-runtime-content-digest"
            )
            runtime_lock = (
                stack_root
                / "Services"
                / "abyss-stack-mcp"
                / ".runtime-provision.lock"
            )
            source_projection_lock = (
                stack_root
                / "Services"
                / "abyss-stack-mcp"
                / ".source-projection.lock"
            )
            first_identity = marker.read_text(encoding="utf-8").strip()
            self.assertRegex(first_identity, r"\A[0-9a-f]{64}:[0-9a-f]{64}\Z")
            first_content_digest = content_marker.read_text(
                encoding="utf-8"
            ).strip()
            self.assertRegex(
                first_content_digest,
                r"\A[0-9a-f]{64}\Z",
            )
            self.assertTrue((venv / "bin" / "python").is_file())
            self.assertTrue((venv / "bin" / "python").is_symlink())
            self.assertEqual(
                (venv / "bin" / "python").resolve(),
                bootstrap.resolve(),
            )
            entrypoint = venv / "bin" / "abyss-stack-mcp"
            self.assertEqual(
                entrypoint.read_text(encoding="utf-8").splitlines()[0],
                f"#!{venv}/bin/python",
            )
            self.assertNotIn(
                "/.venv.",
                entrypoint.read_text(encoding="utf-8").splitlines()[0],
            )
            self.assertTrue(runtime_lock.is_file())
            self.assertEqual(runtime_lock.stat().st_mode & 0o777, 0o600)
            self.assertTrue(source_projection_lock.is_file())
            self.assertEqual(
                source_projection_lock.stat().st_mode & 0o777,
                0o600,
            )
            self.assertIn("provisioned abyss-stack MCP runtime", first.stdout)
            self.assertNotIn("unit linked", first.stdout)
            pip_calls = pip_log.read_text(encoding="utf-8").splitlines()
            self.assertTrue(
                any(
                    "--require-hashes -r " in line
                    and "/.source-snapshot/requirements.lock" in line
                    for line in pip_calls
                )
            )
            self.assertTrue(
                any(
                    "--no-deps --no-build-isolation " in line
                    and line.endswith("/.source-snapshot")
                    for line in pip_calls
                )
            )
            self.assertTrue(all(str(service_root) not in line for line in pip_calls))

            second = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("already provisioned", second.stdout)
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                first_identity,
            )

            bootstrap.write_text(
                bootstrap.read_text(encoding="utf-8")
                + "\n# simulated host interpreter update\n",
                encoding="utf-8",
            )
            interpreter_rebuilt = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                interpreter_rebuilt.returncode,
                0,
                interpreter_rebuilt.stderr,
            )
            self.assertIn(
                "provisioned abyss-stack MCP runtime",
                interpreter_rebuilt.stdout,
            )
            self.assertNotIn("already provisioned", interpreter_rebuilt.stdout)
            self.assertNotEqual(
                content_marker.read_text(encoding="utf-8").strip(),
                first_content_digest,
            )
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                first_identity,
            )

            installed_dependency = (
                venv
                / "lib"
                / "python"
                / "site-packages"
                / "test_package"
                / "__init__.py"
            )
            installed_dependency.write_text(
                "VALUE = 'tampered'\n",
                encoding="utf-8",
            )
            pip_log_before_tamper = pip_log.read_text(encoding="utf-8")
            rebuilt = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
            self.assertIn("provisioned abyss-stack MCP runtime", rebuilt.stdout)
            self.assertNotIn("already provisioned", rebuilt.stdout)
            self.assertNotEqual(
                pip_log.read_text(encoding="utf-8"),
                pip_log_before_tamper,
            )
            self.assertEqual(
                installed_dependency.read_text(encoding="utf-8"),
                "VALUE = 1\n",
            )
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                first_identity,
            )

            source_file.write_text("VALUE = 2\n", encoding="utf-8")
            pip_log_before_block = pip_log.read_text(encoding="utf-8")
            source_lock_holder = subprocess.Popen(
                [
                    "/usr/bin/flock",
                    "--exclusive",
                    str(source_projection_lock),
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
            self.assertIsNotNone(source_lock_holder.stdout)
            self.assertEqual(
                source_lock_holder.stdout.readline().strip(),
                "locked",
            )
            source_locked = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(source_locked.returncode, 0)
            self.assertIn(
                "source projection lock",
                source_locked.stderr,
            )
            self.assertEqual(
                pip_log.read_text(encoding="utf-8"),
                pip_log_before_block,
            )
            self.assertIsNotNone(source_lock_holder.stdin)
            source_lock_holder.stdin.close()
            self.assertEqual(source_lock_holder.wait(timeout=5), 0)
            source_lock_holder.stdout.close()
            source_lock_holder.stderr.close()

            lock_holder = subprocess.Popen(
                [
                    "/usr/bin/flock",
                    "--shared",
                    str(runtime_lock),
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
            locked = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(locked.returncode, 0)
            self.assertIn("holds the runtime lock", locked.stderr)
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                first_identity,
            )
            self.assertEqual(
                pip_log.read_text(encoding="utf-8"),
                pip_log_before_block,
            )
            self.assertIsNotNone(lock_holder.stdin)
            lock_holder.stdin.close()
            self.assertEqual(lock_holder.wait(timeout=5), 0)
            lock_holder.stdout.close()
            lock_holder.stderr.close()

            for active_unit in (
                "abyss-stack-mcp-read.service",
                "abyss-stack-mcp-candidate.service",
            ):
                with self.subTest(active_unit=active_unit):
                    blocked = subprocess.run(
                        command,
                        cwd=REPO_ROOT,
                        env={
                            **env,
                            "ABYSS_STACK_MCP_TEST_ACTIVE_UNIT": active_unit,
                        },
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(blocked.returncode, 0)
                    self.assertIn(
                        f"while {active_unit} is active",
                        blocked.stderr,
                    )
                    self.assertEqual(
                        marker.read_text(encoding="utf-8").strip(),
                        first_identity,
                    )
                    self.assertEqual(
                        pip_log.read_text(encoding="utf-8"),
                        pip_log_before_block,
                    )

            unobservable = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env={
                    **env,
                    "ABYSS_STACK_MCP_TEST_SYSTEMCTL_FAIL": "1",
                },
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(unobservable.returncode, 0)
            self.assertIn(
                "cannot inspect the loaded definition for "
                "abyss-stack-mcp-read.service",
                unobservable.stderr,
            )
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                first_identity,
            )
            self.assertEqual(
                pip_log.read_text(encoding="utf-8"),
                pip_log_before_block,
            )

            activation_signal = root / "activate-during-build"
            raced = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env={
                    **env,
                    "ABYSS_STACK_MCP_TEST_ACTIVATE_DURING_BUILD": str(
                        activation_signal
                    ),
                },
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(raced.returncode, 0)
            self.assertIn(
                "while abyss-stack-mcp-read.service is active",
                raced.stderr,
            )
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                first_identity,
            )
            self.assertNotEqual(
                pip_log.read_text(encoding="utf-8"),
                pip_log_before_block,
            )
            activation_signal.unlink()

            pip_log_before_source_race = pip_log.read_text(encoding="utf-8")
            source_raced = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env={
                    **env,
                    "ABYSS_STACK_MCP_TEST_MUTATE_SOURCE_DURING_BUILD": str(
                        source_file
                    ),
                },
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(source_raced.returncode, 0)
            self.assertIn(
                "package changed during runtime provisioning",
                source_raced.stderr,
            )
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                first_identity,
            )
            self.assertNotEqual(
                pip_log.read_text(encoding="utf-8"),
                pip_log_before_source_race,
            )
            source_file.write_text("VALUE = 2\n", encoding="utf-8")

            third = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertIn("provisioned abyss-stack MCP runtime", third.stdout)
            self.assertNotEqual(
                marker.read_text(encoding="utf-8").strip(),
                first_identity,
            )

    def test_stack_mcp_runtime_provision_rejects_combined_unit_linking(
        self,
    ) -> None:
        result = self.run_install_systemd(
            "--all-user-units",
            "--provision-abyss-stack-mcp-runtime",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "link lock-aware user units in a separate transaction",
            result.stderr,
        )

    def test_mcp_http_auth_provision_creates_a_private_secret_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CONFIGS_ROOT": str(root / "Configs"),
                    "HOME": str(root / "home"),
                    "XDG_CONFIG_HOME": str(root / "xdg-config"),
                }
            )

            result = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-mcp-http-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            secret_dir = stack_root / "Secrets" / "Configs"
            token_path = stack_root / MCP_HTTP_SECRET_RELATIVE
            self.assertEqual(secret_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)

    def test_mcp_http_auth_provision_rejects_symlinked_secret_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            secrets_root = stack_root / "Secrets"
            secrets_root.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            secret_dir = secrets_root / "Configs"
            secret_dir.symlink_to(outside, target_is_directory=True)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CONFIGS_ROOT": str(root / "Configs"),
                    "HOME": str(root / "home"),
                    "XDG_CONFIG_HOME": str(root / "xdg-config"),
                }
            )

            symlinked_root = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-mcp-http-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(symlinked_root.returncode, 0)
            self.assertIn(
                "secret root must be a directory, not a symlink", symlinked_root.stderr
            )
            self.assertFalse(outside.joinpath(MCP_HTTP_CREDENTIAL_NAME).exists())

            secret_dir.unlink()
            secret_dir.mkdir()
            outside_token = outside / "existing-token"
            outside_token.write_text(MCP_HTTP_AUTH_TOKEN, encoding="utf-8")
            secret_dir.joinpath(MCP_HTTP_CREDENTIAL_NAME).symlink_to(outside_token)

            symlinked_token = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-mcp-http-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(symlinked_token.returncode, 0)
            self.assertIn("regular non-symlink file", symlinked_token.stderr)
            self.assertEqual(
                outside_token.read_text(encoding="utf-8"), MCP_HTTP_AUTH_TOKEN
            )

    def test_mcp_http_codex_client_scopes_bearer_to_execed_codex(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            credential = stack_root / MCP_HTTP_SECRET_RELATIVE
            credential.parent.mkdir(parents=True)
            credential.write_text(f"{MCP_HTTP_AUTH_TOKEN}\n", encoding="utf-8")
            credential.chmod(0o600)
            capture_token = root / "captured-token"
            capture_args = root / "captured-args"
            fake_codex = root / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env bash\n"
                'printf \'%s\' "$AOA_MCP_HTTP_BEARER_TOKEN" > "$CAPTURE_TOKEN"\n'
                'printf \'%s\\n\' "$@" > "$CAPTURE_ARGS"\n',
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CODEX_EXECUTABLE": str(fake_codex),
                    "CAPTURE_TOKEN": str(capture_token),
                    "CAPTURE_ARGS": str(capture_args),
                }
            )
            env.pop("AOA_MCP_HTTP_BEARER_TOKEN", None)

            result = subprocess.run(
                [str(MCP_HTTP_CODEX_CLIENT), "resume", "test-thread"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                capture_token.read_text(encoding="utf-8"), MCP_HTTP_AUTH_TOKEN
            )
            self.assertEqual(
                capture_args.read_text(encoding="utf-8").splitlines(),
                ["resume", "test-thread"],
            )
            self.assertNotIn(MCP_HTTP_AUTH_TOKEN, result.stdout + result.stderr)

            env["AOA_MCP_HTTP_BEARER_TOKEN"] = "different-" + ("b" * 54)
            conflict = subprocess.run(
                [str(MCP_HTTP_CODEX_CLIENT), "--version"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(conflict.returncode, 0)
            self.assertIn("conflicts", conflict.stderr)
            self.assertNotIn(MCP_HTTP_AUTH_TOKEN, conflict.stdout + conflict.stderr)

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        "MCP HTTP Codex client installs are user-scoped",
    )
    def test_mcp_http_codex_client_install_is_idempotent_and_removable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            configs_root = root / "Configs"
            deployed_launcher = (
                configs_root / "mcp" / "services" / "_shared" / "codex_http_client.sh"
            )
            deployed_launcher.parent.mkdir(parents=True)
            deployed_launcher.write_bytes(MCP_HTTP_CODEX_CLIENT.read_bytes())
            deployed_launcher.chmod(0o755)
            credential = stack_root / MCP_HTTP_SECRET_RELATIVE
            credential.parent.mkdir(parents=True)
            credential.write_text(f"{MCP_HTTP_AUTH_TOKEN}\n", encoding="utf-8")
            credential.chmod(0o600)
            home = root / "home"
            home.mkdir()
            zshrc = home / ".zshrc"
            zshrc.write_text("export KEEP_EXISTING=1\n", encoding="utf-8")
            zshrc.chmod(0o640)
            fake_codex = root / "codex"
            capture_token = root / "captured-token"
            fake_codex.write_text(
                "#!/usr/bin/env bash\n"
                'printf \'%s\' "$AOA_MCP_HTTP_BEARER_TOKEN" > "$CAPTURE_TOKEN"\n',
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CONFIGS_ROOT": str(configs_root),
                    "HOME": str(home),
                    "AOA_CODEX_EXECUTABLE": str(fake_codex),
                    "CAPTURE_TOKEN": str(capture_token),
                }
            )
            env.pop("ZDOTDIR", None)
            env.pop("AOA_MCP_HTTP_BEARER_TOKEN", None)

            first = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--install-mcp-http-codex-client"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            first_zshrc = zshrc.read_text(encoding="utf-8")
            self.assertEqual(
                first_zshrc.count("abyss-stack MCP HTTP Codex client >>>"), 1
            )
            self.assertIn(str(deployed_launcher), first_zshrc)
            self.assertIn("export KEEP_EXISTING=1", first_zshrc)
            self.assertNotIn(
                MCP_HTTP_AUTH_TOKEN, first_zshrc + first.stdout + first.stderr
            )
            self.assertEqual(zshrc.stat().st_mode & 0o777, 0o640)

            second = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--install-mcp-http-codex-client"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(zshrc.read_text(encoding="utf-8"), first_zshrc)

            zsh = shutil.which("zsh")
            if zsh is not None:
                syntax = subprocess.run(
                    [zsh, "-n", str(zshrc)],
                    cwd=REPO_ROOT,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(syntax.returncode, 0, syntax.stderr)
                launch = subprocess.run(
                    [zsh, "-dfc", 'source "$HOME/.zshrc"; codex --version'],
                    cwd=REPO_ROOT,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(launch.returncode, 0, launch.stderr)
                self.assertEqual(
                    capture_token.read_text(encoding="utf-8"), MCP_HTTP_AUTH_TOKEN
                )

            remove = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--remove-mcp-http-codex-client"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(remove.returncode, 0, remove.stderr)
            removed_zshrc = zshrc.read_text(encoding="utf-8")
            self.assertEqual(removed_zshrc, "export KEEP_EXISTING=1\n")
            self.assertNotIn("MCP HTTP Codex client", removed_zshrc)
            self.assertEqual(zshrc.stat().st_mode & 0o777, 0o640)

    def test_loopback_mcp_units_keep_owner_processes_and_deployed_paths(self) -> None:
        template = MCP_HTTP_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("Environment=AOA_MCP_TRANSPORT=streamable-http", template)
        self.assertIn("Environment=AOA_MCP_HOST=127.0.0.1", template)
        self.assertIn(
            "LoadCredential=aoa-mcp-http-bearer-token:/srv/AbyssOS/abyss-stack/Secrets/Configs/aoa-mcp-http-bearer-token",
            template,
        )
        self.assertNotIn("Environment=AOA_MCP_HTTP_BEARER_TOKEN", template)
        self.assertIn(
            "Environment=AOA_ABYSS_STACK_ROOT=/srv/AbyssOS/abyss-stack/Configs",
            template,
        )
        self.assertIn("WorkingDirectory=/srv/AbyssOS", template)
        self.assertIn(
            "ExecStart=/usr/bin/env python3 /srv/AbyssOS/.codex/bin/%i-mcp-server.py",
            template,
        )
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", template)
        self.assertIn("Restart=on-failure", template)
        self.assertNotIn(str(REPO_ROOT), template)

        bundle = MCP_HTTP_BUNDLE.read_text(encoding="utf-8")
        wants = {
            line.removeprefix("Wants=")
            for line in bundle.splitlines()
            if line.startswith("Wants=")
        }
        self.assertEqual(wants, EXPECTED_MCP_HTTP_INSTANCES)
        self.assertIn("Type=oneshot", bundle)
        self.assertIn("RemainAfterExit=yes", bundle)

        managed_units = {
            line.split("#", 1)[0].strip()
            for line in MANAGED_USER_UNITS.read_text(encoding="utf-8").splitlines()
            if line.split("#", 1)[0].strip()
        }
        self.assertIn("aoa-mcp-http@.service", managed_units)
        self.assertIn("aoa-mcp-http.service", managed_units)

    def test_stack_mcp_units_keep_read_and_candidate_contours_disjoint(self) -> None:
        read_unit = STACK_MCP_READ_UNIT.read_text(encoding="utf-8")
        candidate_unit = STACK_MCP_CANDIDATE_UNIT.read_text(encoding="utf-8")
        observation_path = (
            "Environment=ABYSS_STACK_MCP_OBSERVATION_PATH="
            "/srv/AbyssOS/abyss-stack/Logs/mcp/organ-runtime-observation.json"
        )
        deployed_entrypoint = (
            "ExecStart=/usr/bin/flock --shared --no-fork "
            "/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/"
            ".runtime-provision.lock /usr/bin/env "
            "/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/venv/bin/python "
            "-I -B -m abyss_stack_mcp.server"
        )
        runtime_condition = (
            "ConditionPathExists=/srv/AbyssOS/abyss-stack/Services/"
            "abyss-stack-mcp/venv/bin/python"
        )
        runtime_exec_condition = (
            "ExecCondition=/usr/bin/test -x /srv/AbyssOS/abyss-stack/Services/"
            "abyss-stack-mcp/venv/bin/python"
        )

        self.assertIn("Environment=ABYSS_STACK_MCP_POLICY_FAMILY=read", read_unit)
        self.assertNotIn(
            "Environment=ABYSS_STACK_MCP_POLICY_FAMILY=candidate", read_unit
        )
        self.assertIn(
            "Environment=ABYSS_STACK_MCP_POLICY_FAMILY=candidate", candidate_unit
        )
        self.assertNotIn(
            "Environment=ABYSS_STACK_MCP_POLICY_FAMILY=read", candidate_unit
        )
        self.assertIn(observation_path, read_unit)
        self.assertIn(observation_path, candidate_unit)
        self.assertIn("Environment=AOA_MCP_PORT=5431", read_unit)
        self.assertNotIn("Environment=AOA_MCP_PORT=5433", read_unit)
        self.assertIn("Environment=AOA_MCP_PORT=5433", candidate_unit)
        self.assertNotIn("Environment=AOA_MCP_PORT=5431", candidate_unit)
        self.assertIn(
            "LoadCredential=abyss-stack-mcp-read-bearer-token:"
            "/srv/AbyssOS/abyss-stack/Secrets/Configs/"
            "abyss-stack-mcp-read-bearer-token",
            read_unit,
        )
        self.assertNotIn("candidate-bearer-token", read_unit)
        self.assertIn(
            "LoadCredential=abyss-stack-mcp-candidate-bearer-token:"
            "/srv/AbyssOS/abyss-stack/Secrets/Configs/"
            "abyss-stack-mcp-candidate-bearer-token",
            candidate_unit,
        )
        self.assertNotIn("read-bearer-token", candidate_unit)
        for unit in (read_unit, candidate_unit):
            self.assertIn("Environment=AOA_MCP_HOST=127.0.0.1", unit)
            self.assertIn("Environment=PYTHONHOME=", unit)
            self.assertIn("Environment=PYTHONPATH=", unit)
            self.assertIn("/venv/bin/python -I -B -m abyss_stack_mcp.server", unit)
            self.assertIn(runtime_condition, unit)
            self.assertIn(runtime_exec_condition, unit)
            self.assertIn(deployed_entrypoint, unit)
            self.assertNotIn(
                "/Configs/mcp/services/abyss-stack-mcp/scripts/"
                "abyss_stack_mcp_server.py",
                unit,
            )
            self.assertIn("NoNewPrivileges=yes", unit)
            self.assertNotIn("Environment=AOA_MCP_HTTP_BEARER_TOKEN", unit)
            self.assertNotIn(str(REPO_ROOT), unit)

        managed_units = {
            line.split("#", 1)[0].strip()
            for line in MANAGED_USER_UNITS.read_text(encoding="utf-8").splitlines()
            if line.split("#", 1)[0].strip()
        }
        self.assertIn(STACK_MCP_READ_UNIT.name, managed_units)
        self.assertIn(STACK_MCP_CANDIDATE_UNIT.name, managed_units)


class McpLoopbackLifecycleTests(unittest.TestCase):
    def test_all_standalone_packages_require_the_tested_mcp_auth_api(self) -> None:
        for directory, _ in MCP_SERVER_PACKAGES.values():
            with self.subTest(directory=directory):
                pyproject = (
                    REPO_ROOT / "mcp" / "services" / directory / "pyproject.toml"
                ).read_text(encoding="utf-8")
                self.assertIn('"mcp>=1.27.2,<2",', pyproject)

    def test_generated_http_auth_helpers_are_current(self) -> None:
        result = subprocess.run(
            [sys.executable, str(MCP_HTTP_AUTH_BUILDER), "--check"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_servers_share_the_guarded_transport_contract(self) -> None:
        ports: set[int] = set()
        for package, (directory, expected_port) in MCP_SERVER_PACKAGES.items():
            with self.subTest(package=package):
                module = import_mcp_server(package, directory)
                self.assertEqual(module.DEFAULT_HTTP_PORT, expected_port)
                ports.add(module.DEFAULT_HTTP_PORT)

                server = DummyServer()
                with mock.patch.dict(os.environ, mcp_environment(), clear=True):
                    module._run_server(server)
                self.assertEqual(server.transports, ["stdio"])

                server = DummyServer()
                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        AOA_MCP_HTTP_BEARER_TOKEN=MCP_HTTP_AUTH_TOKEN,
                    ),
                    clear=True,
                ):
                    module._run_server(server)
                self.assertEqual(server.transports, ["streamable-http"])
                self.assertEqual(server.settings.host, "127.0.0.1")
                self.assertEqual(server.settings.port, expected_port)

                server = DummyServer()
                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        AOA_MCP_HOST="localhost",
                        AOA_MCP_PORT="6543",
                        AOA_MCP_HTTP_BEARER_TOKEN=MCP_HTTP_AUTH_TOKEN,
                    ),
                    clear=True,
                ):
                    module._run_server(server)
                self.assertEqual(server.settings.host, "localhost")
                self.assertEqual(server.settings.port, 6543)

                with mock.patch.dict(
                    os.environ,
                    mcp_environment(AOA_MCP_TRANSPORT="websocket"),
                    clear=True,
                ):
                    with self.assertRaisesRegex(
                        SystemExit, "unsupported AOA_MCP_TRANSPORT"
                    ):
                        module._run_server(DummyServer())

                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        AOA_MCP_HOST="0.0.0.0",
                        AOA_MCP_HTTP_BEARER_TOKEN=MCP_HTTP_AUTH_TOKEN,
                    ),
                    clear=True,
                ):
                    with self.assertRaisesRegex(SystemExit, "loopback-only"):
                        module._run_server(DummyServer())

                built_server = DummyServer()
                with (
                    mock.patch.object(
                        module, "build_server", return_value=built_server
                    ),
                    mock.patch.object(module, "_run_server") as run_server,
                ):
                    module.main()
                run_server.assert_called_once_with(built_server)

        self.assertEqual(len(ports), len(MCP_SERVER_PACKAGES))

    def test_all_http_servers_require_and_verify_bearer_auth(self) -> None:
        for package, (directory, expected_port) in MCP_SERVER_PACKAGES.items():
            with self.subTest(package=package):
                module = import_mcp_server(package, directory)
                with mock.patch.dict(
                    os.environ,
                    mcp_environment(AOA_MCP_TRANSPORT="streamable-http"),
                    clear=True,
                ):
                    with self.assertRaisesRegex(SystemExit, "bearer authentication"):
                        module._http_auth_kwargs(expected_port)

                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        AOA_MCP_HTTP_BEARER_TOKEN="too-short",
                    ),
                    clear=True,
                ):
                    with self.assertRaisesRegex(
                        SystemExit, "invalid bearer credential"
                    ):
                        module._http_auth_kwargs(expected_port)

                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        AOA_MCP_HTTP_BEARER_TOKEN=MCP_HTTP_AUTH_TOKEN,
                    ),
                    clear=True,
                ):
                    kwargs = module._http_auth_kwargs(expected_port)

                self.assertEqual(kwargs["auth"].required_scopes, ["mcp:access"])
                security = kwargs["transport_security"]
                self.assertTrue(security.enable_dns_rebinding_protection)
                self.assertEqual(
                    security.allowed_hosts,
                    [
                        f"127.0.0.1:{expected_port}",
                        f"localhost:{expected_port}",
                        f"[::1]:{expected_port}",
                    ],
                )
                verifier = kwargs["token_verifier"]
                self.assertIsNone(asyncio.run(verifier.verify_token("wrong-token")))
                access = asyncio.run(verifier.verify_token(MCP_HTTP_AUTH_TOKEN))
                self.assertIsNotNone(access)
                assert access is not None
                self.assertEqual(access.client_id, "aoa-loopback-codex")
                self.assertEqual(access.scopes, ["mcp:access"])

    def test_http_auth_accepts_systemd_credential_and_rejects_conflict(self) -> None:
        module = import_mcp_server("aoa_decisions_mcp", "aoa-decisions-mcp")
        with tempfile.TemporaryDirectory() as tmpdir:
            credential_dir = Path(tmpdir)
            credential_dir.joinpath(MCP_HTTP_CREDENTIAL_NAME).write_text(
                MCP_HTTP_AUTH_TOKEN + "\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                mcp_environment(
                    AOA_MCP_TRANSPORT="streamable-http",
                    CREDENTIALS_DIRECTORY=str(credential_dir),
                ),
                clear=True,
            ):
                kwargs = module._http_auth_kwargs(module.DEFAULT_HTTP_PORT)
            access = asyncio.run(
                kwargs["token_verifier"].verify_token(MCP_HTTP_AUTH_TOKEN)
            )
            self.assertIsNotNone(access)

            with mock.patch.dict(
                os.environ,
                mcp_environment(
                    AOA_MCP_TRANSPORT="streamable-http",
                    AOA_MCP_HTTP_BEARER_TOKEN="different-" + ("b" * 54),
                    CREDENTIALS_DIRECTORY=str(credential_dir),
                ),
                clear=True,
            ):
                with self.assertRaisesRegex(
                    SystemExit, "conflicting bearer credentials"
                ):
                    module._http_auth_kwargs(module.DEFAULT_HTTP_PORT)

            with mock.patch.dict(
                os.environ,
                mcp_environment(
                    AOA_MCP_TRANSPORT="streamable-http",
                    AOA_MCP_HTTP_BEARER_TOKEN="too-short",
                    CREDENTIALS_DIRECTORY=str(credential_dir),
                ),
                clear=True,
            ):
                with self.assertRaisesRegex(SystemExit, "invalid bearer credential"):
                    module._http_auth_kwargs(module.DEFAULT_HTTP_PORT)

    def test_http_auth_rejects_symlinked_systemd_credential(self) -> None:
        module = import_mcp_server("aoa_decisions_mcp", "aoa-decisions-mcp")
        with tempfile.TemporaryDirectory() as tmpdir:
            credential_dir = Path(tmpdir)
            target = credential_dir / "outside-token"
            target.write_text(MCP_HTTP_AUTH_TOKEN, encoding="utf-8")
            credential_dir.joinpath(MCP_HTTP_CREDENTIAL_NAME).symlink_to(target)

            with mock.patch.dict(
                os.environ,
                mcp_environment(
                    AOA_MCP_TRANSPORT="streamable-http",
                    CREDENTIALS_DIRECTORY=str(credential_dir),
                ),
                clear=True,
            ):
                with self.assertRaisesRegex(SystemExit, "regular non-symlink"):
                    module._http_auth_kwargs(module.DEFAULT_HTTP_PORT)

    def test_http_transport_rejects_invalid_port(self) -> None:
        module = import_mcp_server("aoa_decisions_mcp", "aoa-decisions-mcp")
        for value in ("zero", "0", "65536"):
            with self.subTest(value=value):
                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        AOA_MCP_PORT=value,
                        AOA_MCP_HTTP_BEARER_TOKEN=MCP_HTTP_AUTH_TOKEN,
                    ),
                    clear=True,
                ):
                    with self.assertRaisesRegex(SystemExit, "AOA_MCP_PORT"):
                        module._run_server(DummyServer())

    def test_decisions_http_entrypoint_fails_closed_without_bearer(self) -> None:
        script = (
            REPO_ROOT
            / "mcp"
            / "services"
            / "aoa-decisions-mcp"
            / "scripts"
            / "aoa_decisions_mcp_server.py"
        )
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=REPO_ROOT,
            env=mcp_environment(AOA_MCP_TRANSPORT="streamable-http"),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bearer authentication", result.stderr)

    def test_decisions_http_entrypoint_stays_alive_on_loopback(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        script = (
            REPO_ROOT
            / "mcp"
            / "services"
            / "aoa-decisions-mcp"
            / "scripts"
            / "aoa_decisions_mcp_server.py"
        )
        env = mcp_environment(
            AOA_MCP_TRANSPORT="streamable-http",
            AOA_MCP_HOST="127.0.0.1",
            AOA_MCP_PORT=str(port),
            AOA_MCP_HTTP_BEARER_TOKEN=MCP_HTTP_AUTH_TOKEN,
        )
        process = subprocess.Popen(
            [sys.executable, str(script)],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                self.fail("aoa-decisions MCP did not bind its loopback HTTP port")

            self.assertIsNone(
                process.poll(), "aoa-decisions MCP exited after declaring readiness"
            )
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass

            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/mcp",
                data=b"{}",
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as missing_auth:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(missing_auth.exception.code, 401)

            wrong_request = urllib.request.Request(
                f"http://127.0.0.1:{port}/mcp",
                data=b"{}",
                method="POST",
                headers={"Authorization": "Bearer wrong-token"},
            )
            with self.assertRaises(urllib.error.HTTPError) as wrong_auth:
                urllib.request.urlopen(wrong_request, timeout=2)
            self.assertEqual(wrong_auth.exception.code, 401)

            invalid_origin_request = urllib.request.Request(
                f"http://127.0.0.1:{port}/mcp",
                data=b"{}",
                method="POST",
                headers={
                    "Authorization": f"Bearer {MCP_HTTP_AUTH_TOKEN}",
                    "Content-Type": "application/json",
                    "Origin": "https://untrusted.example",
                },
            )
            with self.assertRaises(urllib.error.HTTPError) as invalid_origin:
                urllib.request.urlopen(invalid_origin_request, timeout=2)
            self.assertEqual(invalid_origin.exception.code, 403)

            invalid_host_request = urllib.request.Request(
                f"http://127.0.0.1:{port}/mcp",
                data=b"{}",
                method="POST",
                headers={
                    "Authorization": f"Bearer {MCP_HTTP_AUTH_TOKEN}",
                    "Content-Type": "application/json",
                    "Host": "untrusted.example",
                },
            )
            with self.assertRaises(urllib.error.HTTPError) as invalid_host:
                urllib.request.urlopen(invalid_host_request, timeout=2)
            self.assertEqual(invalid_host.exception.code, 421)

            async def authenticated_inventory() -> int:
                import httpx
                from mcp import ClientSession
                from mcp.client.streamable_http import streamable_http_client

                async with httpx.AsyncClient(
                    headers={"Authorization": f"Bearer {MCP_HTTP_AUTH_TOKEN}"}
                ) as http_client:
                    async with streamable_http_client(
                        f"http://127.0.0.1:{port}/mcp",
                        http_client=http_client,
                    ) as (read_stream, write_stream, _):
                        async with ClientSession(read_stream, write_stream) as session:
                            await session.initialize()
                            tools = await session.list_tools()
                            return len(tools.tools)

            self.assertGreater(asyncio.run(authenticated_inventory()), 0)
        finally:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
        self.assertNotIn(MCP_HTTP_AUTH_TOKEN, stdout + stderr)


if __name__ == "__main__":
    unittest.main()
