from __future__ import annotations

import importlib
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SYSTEMD = REPO_ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "user-unit" / "aoa_install_systemd.sh"
STATS_PATH_UNIT = REPO_ROOT / "systemd" / "user" / "aoa-stats-live-refresh.path"
STATS_SERVICE_UNIT = REPO_ROOT / "systemd" / "user" / "aoa-stats-live-refresh.service"
MCP_HTTP_TEMPLATE = REPO_ROOT / "systemd" / "user" / "aoa-mcp-http@.service"
MCP_HTTP_BUNDLE = REPO_ROOT / "systemd" / "user" / "aoa-mcp-http.service"
MANAGED_USER_UNITS = REPO_ROOT / "systemd" / "user" / "managed-units.txt"
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
}
EXPECTED_MCP_HTTP_INSTANCES = {
    "aoa-mcp-http@aoa-decisions.service",
    "aoa-mcp-http@aoa-memo.service",
    "aoa-mcp-http@aoa-session-memory.service",
    "aoa-mcp-http@abyss-machine.service",
    "aoa-mcp-http@aoa-evals.service",
    "aoa-mcp-http@aoa-kag.service",
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
    for name in ("AOA_MCP_TRANSPORT", "AOA_MCP_HOST", "AOA_MCP_PORT"):
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

    def test_empty_preset_assignment_fails_before_runtime_selection(self) -> None:
        result = self.run_install_systemd("--preset=")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("preset must not be empty", result.stderr)

    def test_empty_profile_assignment_fails_before_runtime_selection(self) -> None:
        result = self.run_install_systemd("--profile=")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("profile must not be empty", result.stderr)

    def test_aoa_stats_adapter_delegates_source_selection_to_sibling_owner(self) -> None:
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
            for name in ("podman-compose-abyss.service", "masked.service", "linked.service"):
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

    def test_loopback_mcp_units_keep_owner_processes_and_deployed_paths(self) -> None:
        template = MCP_HTTP_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("Environment=AOA_MCP_TRANSPORT=streamable-http", template)
        self.assertIn("Environment=AOA_MCP_HOST=127.0.0.1", template)
        self.assertIn("Environment=AOA_ABYSS_STACK_ROOT=/srv/AbyssOS/abyss-stack/Configs", template)
        self.assertIn("WorkingDirectory=/srv/AbyssOS", template)
        self.assertIn("ExecStart=/usr/bin/env python3 /srv/AbyssOS/.codex/bin/%i-mcp-server.py", template)
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


class McpLoopbackLifecycleTests(unittest.TestCase):
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
                    mcp_environment(AOA_MCP_TRANSPORT="streamable-http"),
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
                    with self.assertRaisesRegex(SystemExit, "unsupported AOA_MCP_TRANSPORT"):
                        module._run_server(DummyServer())

                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        AOA_MCP_HOST="0.0.0.0",
                    ),
                    clear=True,
                ):
                    with self.assertRaisesRegex(SystemExit, "loopback-only"):
                        module._run_server(DummyServer())

                built_server = DummyServer()
                with (
                    mock.patch.object(module, "build_server", return_value=built_server),
                    mock.patch.object(module, "_run_server") as run_server,
                ):
                    module.main()
                run_server.assert_called_once_with(built_server)

        self.assertEqual(len(ports), len(MCP_SERVER_PACKAGES))

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

            self.assertIsNone(process.poll(), "aoa-decisions MCP exited after declaring readiness")
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
