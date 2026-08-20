from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import os
import signal
import shutil
import socket
import stat
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
AOA_UP = (
    REPO_ROOT
    / "mechanics"
    / "runtime-lifecycle"
    / "parts"
    / "start-stop"
    / "aoa_up.sh"
)
AOA_DOWN = (
    REPO_ROOT
    / "mechanics"
    / "runtime-lifecycle"
    / "parts"
    / "start-stop"
    / "aoa_down.sh"
)
STATS_PATH_UNIT = REPO_ROOT / "systemd" / "user" / "aoa-stats-live-refresh.path"
STATS_SERVICE_UNIT = REPO_ROOT / "systemd" / "user" / "aoa-stats-live-refresh.service"
MCP_HTTP_TEMPLATE = REPO_ROOT / "systemd" / "user" / "aoa-mcp-http@.service"
ORGAN_MCP_READ_TEMPLATE = REPO_ROOT / "systemd" / "user" / "aoa-organ-mcp-read@.service"
ORGAN_MCP_READ_BOOTSTRAP_TEMPLATE = (
    REPO_ROOT / "systemd" / "user" / "aoa-organ-mcp-read-bootstrap@.service"
)
MEMO_MCP_CANDIDATE_UNIT = (
    REPO_ROOT / "systemd" / "user" / "aoa-memo-mcp-candidate.service"
)
EVALS_MCP_CANDIDATE_UNIT = (
    REPO_ROOT / "systemd" / "user" / "aoa-evals-mcp-candidate.service"
)
MCP_HTTP_BUNDLE = REPO_ROOT / "systemd" / "user" / "aoa-mcp-http.service"
STACK_MCP_READ_UNIT = REPO_ROOT / "systemd" / "user" / "abyss-stack-mcp-read.service"
STACK_MCP_READ_BOOTSTRAP_UNIT = (
    REPO_ROOT / "systemd" / "user" / "abyss-stack-mcp-read-bootstrap.service"
)
STACK_MCP_CANDIDATE_UNIT = (
    REPO_ROOT / "systemd" / "user" / "abyss-stack-mcp-candidate.service"
)
STACK_MCP_INTERNAL_EFFECT_UNIT = (
    REPO_ROOT / "systemd" / "user" / "abyss-stack-mcp-internal-effect.service"
)
STACK_MCP_OBSERVATION_UNIT = (
    REPO_ROOT / "systemd" / "user" / "abyss-stack-mcp-observation.service"
)
STACK_MCP_OBSERVATION_TIMER = (
    REPO_ROOT / "systemd" / "user" / "abyss-stack-mcp-observation.timer"
)
MCP_ADMISSION_KEEPER_UNIT = (
    REPO_ROOT / "systemd" / "user" / "abyss-mcp-admission-keeper.service"
)
MCP_ADMISSION_KEEPER_PATH = (
    REPO_ROOT / "systemd" / "user" / "abyss-mcp-admission-keeper.path"
)
MCP_MODERN_ADMISSION_REFRESH_UNIT = (
    REPO_ROOT / "systemd" / "user" / "abyss-mcp-modern-admission-refresh.service"
)
MCP_MODERN_ADMISSION_REFRESH_TIMER = (
    REPO_ROOT / "systemd" / "user" / "abyss-mcp-modern-admission-refresh.timer"
)
STACK_MCP_RUNTIME_REPAIR_UNIT = (
    REPO_ROOT / "systemd" / "user" / "abyss-stack-mcp-runtime-repair.service"
)
MCP_PREFLIGHT_SWEEP_UNIT = (
    REPO_ROOT / "systemd" / "user" / "abyss-mcp-preflight-sweep.service"
)
MCP_MODERN_ADMISSION_REFRESH_SCRIPT = (
    REPO_ROOT / "scripts" / "aoa-refresh-modern-mcp-admission"
)
STACK_MCP_RUNTIME_TARGETS = (
    REPO_ROOT
    / "mcp"
    / "services"
    / "abyss-stack-mcp"
    / "src"
    / "abyss_stack_mcp"
    / "runtime-targets.v1.json"
)
MCP_PROTOCOL_WATCH_UNIT = (
    REPO_ROOT / "systemd" / "user" / "abyss-mcp-protocol-watch.service"
)
MCP_PROTOCOL_WATCH_PATH = (
    REPO_ROOT / "systemd" / "user" / "abyss-mcp-protocol-watch.path"
)
MCP_PROTOCOL_WATCH_TIMER = (
    REPO_ROOT / "systemd" / "user" / "abyss-mcp-protocol-watch.timer"
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
OVMS_QUADLET = REPO_ROOT / "systemd" / "user" / "abyss-ovms.container"
OVMS_TCP_SOCKET = REPO_ROOT / "systemd" / "user" / "abyss-ovms.socket"
OVMS_UNIX_SOCKET = REPO_ROOT / "systemd" / "user" / "abyss-ovms-unix.socket"
OVMS_PROXY_UNIT = REPO_ROOT / "systemd" / "user" / "abyss-ovms-proxy.service"
MCP_HTTP_AUTH_BUILDER = (
    REPO_ROOT / "mcp" / "services" / "_shared" / "build_http_auth_vendors.py"
)
MCP_MODERN_RUNTIME_BUILDER = (
    REPO_ROOT / "mcp" / "services" / "_shared" / "build_modern_runtime_vendors.py"
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
    "abyss-stack-mcp-internal-effect-bearer-token",
)
STACK_MCP_CANARY_SIGNING_KEY_NAME = "abyss-stack-mcp-canary-ed25519-private-key.pem"
STACK_MCP_CANARY_PUBLIC_KEY_NAME = "abyss-stack-mcp-canary-ed25519-public-key.pem"
ORGAN_MCP_READ_CREDENTIAL_NAMES = (
    "aoa-decisions-mcp-read-bearer-token",
    "aoa-memo-mcp-read-bearer-token",
    "aoa-evals-mcp-read-bearer-token",
    "aoa-kag-mcp-read-bearer-token",
    "aoa-4pda-connector-mcp-read-bearer-token",
    "aoa-course-connector-mcp-read-bearer-token",
    "aoa-discord-connector-mcp-read-bearer-token",
    "aoa-session-memory-mcp-read-bearer-token",
    "aoa-stackoverflow-connector-mcp-read-bearer-token",
    "aoa-stats-mcp-read-bearer-token",
    "aoa-telegram-connector-mcp-read-bearer-token",
    "aoa-xda-connector-mcp-read-bearer-token",
    "abyss-machine-mcp-read-bearer-token",
    "tos-corpus-mcp-read-bearer-token",
)
ORGAN_MCP_CANDIDATE_CREDENTIAL_NAMES = (
    "aoa-memo-mcp-candidate-bearer-token",
    "aoa-evals-mcp-candidate-bearer-token",
)
CODEX_MCP_READ_CREDENTIAL_NAMES = (
    "aoa-decisions-mcp-read-bearer-token",
    "aoa-memo-mcp-read-bearer-token",
    "aoa-evals-mcp-read-bearer-token",
    "aoa-kag-mcp-read-bearer-token",
    "aoa-4pda-connector-mcp-read-bearer-token",
    "aoa-discord-connector-mcp-read-bearer-token",
    "aoa-session-memory-mcp-read-bearer-token",
    "aoa-stats-mcp-read-bearer-token",
    "aoa-telegram-connector-mcp-read-bearer-token",
    "abyss-machine-mcp-read-bearer-token",
    "abyss-stack-mcp-read-bearer-token",
)
ORGAN_MCP_READ_AUTH_MANIFEST_NAME = "organ-mcp-read-auth-manifest.json"
ORGAN_MCP_CANDIDATE_AUTH_MANIFEST_NAME = "organ-mcp-candidate-auth-manifest.json"
ORGAN_MCP_READ_AUTH = {
    "abyss_machine_mcp": {
        "env": "ABYSS_MACHINE_MCP_READ_BEARER_TOKEN",
        "credential": "abyss-machine-mcp-read-bearer-token",
        "scope": "mcp:abyss-machine:read",
        "client_id": "aoa-loopback-codex:abyss-machine:read",
    },
    "aoa_decisions_mcp": {
        "env": "AOA_DECISIONS_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-decisions-mcp-read-bearer-token",
        "scope": "mcp:aoa-decisions:read",
        "client_id": "aoa-loopback-codex:aoa-decisions:read",
    },
    "aoa_4pda_connector_mcp": {
        "env": "AOA_4PDA_CONNECTOR_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-4pda-connector-mcp-read-bearer-token",
        "scope": "mcp:aoa-4pda-connector:read",
        "client_id": "aoa-loopback-codex:aoa-4pda-connector:read",
    },
    "aoa_course_connector_mcp": {
        "env": "AOA_COURSE_CONNECTOR_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-course-connector-mcp-read-bearer-token",
        "scope": "mcp:aoa-course-connector:read",
        "client_id": "aoa-loopback-codex:aoa-course-connector:read",
    },
    "aoa_discord_connector_mcp": {
        "env": "AOA_DISCORD_CONNECTOR_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-discord-connector-mcp-read-bearer-token",
        "scope": "mcp:aoa-discord-connector:read",
        "client_id": "aoa-loopback-codex:aoa-discord-connector:read",
    },
    "aoa_memo_mcp": {
        "env": "AOA_MEMO_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-memo-mcp-read-bearer-token",
        "scope": "mcp:aoa-memo:read",
        "client_id": "aoa-loopback-codex:aoa-memo:read",
    },
    "aoa_evals_mcp": {
        "env": "AOA_EVALS_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-evals-mcp-read-bearer-token",
        "scope": "mcp:aoa-evals:read",
        "client_id": "aoa-loopback-codex:aoa-evals:read",
    },
    "aoa_kag_mcp": {
        "env": "AOA_KAG_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-kag-mcp-read-bearer-token",
        "scope": "mcp:aoa-kag:read",
        "client_id": "aoa-loopback-codex:aoa-kag:read",
    },
    "aoa_session_memory_mcp": {
        "env": "AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-session-memory-mcp-read-bearer-token",
        "scope": "mcp:aoa-session-memory:read",
        "client_id": "aoa-loopback-codex:aoa-session-memory:read",
    },
    "aoa_stats_mcp": {
        "env": "AOA_STATS_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-stats-mcp-read-bearer-token",
        "scope": "mcp:aoa-stats:read",
        "client_id": "aoa-loopback-codex:aoa-stats:read",
    },
    "aoa_stackoverflow_connector_mcp": {
        "env": "AOA_STACKOVERFLOW_CONNECTOR_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-stackoverflow-connector-mcp-read-bearer-token",
        "scope": "mcp:aoa-stackoverflow-connector:read",
        "client_id": "aoa-loopback-codex:aoa-stackoverflow-connector:read",
    },
    "aoa_telegram_connector_mcp": {
        "env": "AOA_TELEGRAM_CONNECTOR_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-telegram-connector-mcp-read-bearer-token",
        "scope": "mcp:aoa-telegram-connector:read",
        "client_id": "aoa-loopback-codex:aoa-telegram-connector:read",
    },
    "tos_corpus_mcp": {
        "env": "TOS_CORPUS_MCP_READ_BEARER_TOKEN",
        "credential": "tos-corpus-mcp-read-bearer-token",
        "scope": "mcp:tos-corpus:read",
        "client_id": "aoa-loopback-codex:tos-corpus:read",
    },
    "aoa_xda_connector_mcp": {
        "env": "AOA_XDA_CONNECTOR_MCP_READ_BEARER_TOKEN",
        "credential": "aoa-xda-connector-mcp-read-bearer-token",
        "scope": "mcp:aoa-xda-connector:read",
        "client_id": "aoa-loopback-codex:aoa-xda-connector:read",
    },
}
ORGAN_MCP_READ_OWNER_BY_CREDENTIAL = {
    auth["credential"]: module.removesuffix("_mcp").replace("_", "-")
    for module, auth in ORGAN_MCP_READ_AUTH.items()
}
STACK_MCP_AUTH_MANIFEST_NAME = "abyss-stack-mcp-auth-manifest.json"
EXPECTED_STATS_RECEIPT_PATHS = (
    "/srv/AbyssOS/aoa-skills/.aoa/live_receipts/session-harvest-family.jsonl",
    "/srv/AbyssOS/aoa-skills/.aoa/live_receipts/core-skill-applications.jsonl",
    "/srv/AbyssOS/aoa-evals/.aoa/live_receipts/eval-result-receipts.jsonl",
    "/srv/AbyssOS/aoa-playbooks/.aoa/live_receipts/playbook-receipts.jsonl",
    "/srv/AbyssOS/aoa-techniques/.aoa/live_receipts/technique-receipts.jsonl",
    "/srv/AbyssOS/aoa-memo/.aoa/live_receipts/memo-writeback-receipts.jsonl",
    "/srv/AbyssOS/aoa-agents/.aoa/live_receipts/actor-responsibility-execution-receipts.jsonl",
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
    "aoa_course_connector_mcp": ("aoa-course-connector-mcp", 5436),
    "aoa_stackoverflow_connector_mcp": (
        "aoa-stackoverflow-connector-mcp",
        5437,
    ),
    "aoa_xda_connector_mcp": ("aoa-xda-connector-mcp", 5438),
}
EXPECTED_MCP_HTTP_INSTANCES = {
    "aoa-organ-mcp-read@aoa-decisions.service",
    "aoa-organ-mcp-read@aoa-memo.service",
    "aoa-memo-mcp-candidate.service",
    "aoa-organ-mcp-read@aoa-session-memory.service",
    "aoa-organ-mcp-read@abyss-machine.service",
    "aoa-organ-mcp-read@aoa-evals.service",
    "aoa-evals-mcp-candidate.service",
    "aoa-organ-mcp-read@aoa-kag.service",
    "aoa-organ-mcp-read@aoa-stats.service",
    "aoa-organ-mcp-read@aoa-4pda-connector.service",
    "aoa-organ-mcp-read@aoa-course-connector.service",
    "aoa-organ-mcp-read@aoa-discord-connector.service",
    "aoa-organ-mcp-read@aoa-stackoverflow-connector.service",
    "aoa-organ-mcp-read@aoa-telegram-connector.service",
    "aoa-organ-mcp-read@aoa-xda-connector.service",
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

    def configure_http(self, host: str, port: int) -> None:
        self.settings.host = host
        self.settings.port = port


def mcp_environment(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    for name in (
        "AOA_MCP_TRANSPORT",
        "AOA_MCP_HOST",
        "AOA_MCP_PORT",
        "AOA_MCP_HTTP_BEARER_TOKEN",
        "AOA_DECISIONS_MCP_READ_BEARER_TOKEN",
        "AOA_DECISIONS_MCP_INTERNAL_EFFECT_BEARER_TOKEN",
        "AOA_MEMO_MCP_READ_BEARER_TOKEN",
        "AOA_MEMO_MCP_CANDIDATE_BEARER_TOKEN",
        "AOA_EVALS_MCP_READ_BEARER_TOKEN",
        "AOA_EVALS_MCP_CANDIDATE_BEARER_TOKEN",
        "AOA_KAG_MCP_READ_BEARER_TOKEN",
        "AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN",
        "AOA_STATS_MCP_READ_BEARER_TOKEN",
        "ABYSS_MACHINE_MCP_READ_BEARER_TOKEN",
        "TOS_CORPUS_MCP_READ_BEARER_TOKEN",
        "AOA_DECISIONS_MCP_CONTOUR",
        "AOA_MCP_POLICY_FAMILY",
        "AOA_MEMO_MCP_CANDIDATE_ROOTS",
        "AOA_EVALS_MCP_CANDIDATE_ROOTS",
        "CREDENTIALS_DIRECTORY",
    ):
        env.pop(name, None)
    for auth in ORGAN_MCP_READ_AUTH.values():
        env.pop(auth["env"], None)
    env.update(overrides)
    return env


def mcp_server_auth_kwargs(module, package: str):
    if package == "aoa_decisions_mcp":
        return module._contour_http_auth_kwargs("read")
    if package in ORGAN_MCP_READ_AUTH:
        return module._read_http_auth_kwargs()
    return module._http_auth_kwargs(module.DEFAULT_HTTP_PORT)


def mcp_server_token_environment(package: str) -> str:
    return ORGAN_MCP_READ_AUTH.get(package, {}).get(
        "env",
        "AOA_MCP_HTTP_BEARER_TOKEN",
    )


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
            for name in (
                "abyss-ovms.container",
                "abyss-ovms.socket",
                "abyss-ovms-unix.socket",
                "abyss-ovms-proxy.service",
            ):
                (unit_source / name).write_text(
                    "[Unit]\nDescription=test\n", encoding="utf-8"
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

            quadlet_target = root / "xdg-config" / "containers" / "systemd" / "abyss-ovms.container"
            self.assertEqual(os.readlink(quadlet_target), str(unit_source / "abyss-ovms.container"))

    def test_ovms_units_use_native_idle_lifecycle_and_safe_kill_mode(self) -> None:
        quadlet = OVMS_QUADLET.read_text(encoding="utf-8")
        proxy = OVMS_PROXY_UNIT.read_text(encoding="utf-8")
        tcp_socket = OVMS_TCP_SOCKET.read_text(encoding="utf-8")
        unix_socket = OVMS_UNIX_SOCKET.read_text(encoding="utf-8")

        self.assertIn("StopWhenUnneeded=yes", quadlet)
        self.assertIn("Pull=missing", quadlet)
        self.assertIn("Notify=healthy", quadlet)
        self.assertIn("ExecStartPost=/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-ovms-admission release", quadlet)
        self.assertIn("Environment=AOA_OVMS_ADMISSION_WAIT_SEC=120", quadlet)
        self.assertIn("TimeoutStartSec=300", quadlet)
        self.assertEqual(quadlet.count('Authorization: Bearer $${key}'), 2)
        self.assertNotIn("EnvironmentFile=", quadlet)
        self.assertIn(
            "Secret=abyss-ovms-api-key,type=mount,target=/run/secrets/ovms_api_key,uid=5000,gid=5000,mode=0400",
            quadlet,
        )
        self.assertNotIn("Secrets/Configs/ovms_api_key.txt:/run/secrets", quadlet)
        self.assertNotIn("KillMode=none", quadlet + proxy)
        self.assertIn("--exit-idle-time=15min", proxy)
        self.assertIn("ListenStream=127.0.0.1:8200", tcp_socket)
        self.assertIn("ListenStream=%t/abyss-stack/ovms-socket/ovms.sock", unix_socket)
        self.assertIn("SocketMode=0600", unix_socket)

    def test_ovms_up_installs_units_and_cuts_over_before_opening_sockets(self) -> None:
        launcher = AOA_UP.read_text(encoding="utf-8")
        self.assertIn(
            '"${SCRIPTS_DIR}/aoa-install-systemd"\n'
            '  "${SCRIPTS_DIR}/aoa-install-systemd" --provision-ovms-auth',
            launcher,
        )
        self.assertIn("aoa_retire_legacy_ovms", launcher)
        self.assertLess(
            launcher.rindex("aoa_retire_legacy_ovms"),
            launcher.index("systemctl --user start abyss-ovms.socket"),
        )
        self.assertIn("--filter \"label=${compose_label}=ovms\"", launcher)
        self.assertIn("up -d --remove-orphans", launcher)
        self.assertIn("aoa_stop_ovms_units_if_active", launcher)

    def test_ovms_teardown_reconciles_even_when_intel_is_not_selected(self) -> None:
        launcher = AOA_UP.read_text(encoding="utf-8")
        teardown = AOA_DOWN.read_text(encoding="utf-8")
        self.assertIn("else\n  aoa_stop_ovms_units_if_active", launcher)
        self.assertIn("aoa_stop_ovms_units_if_active\naoa_compose down", teardown)
        self.assertNotIn('if [[ "$module" == "31-intel-inference.yml" ]]', teardown)

    def test_ovms_auth_provision_is_rootless_idempotent_and_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            secret_dir = stack_root / "Secrets" / "Configs"
            secret_dir.mkdir(parents=True)
            canonical = secret_dir / "ovms_api_key.txt"
            canonical.write_text("A" * 48 + "\n", encoding="utf-8")
            canonical.chmod(0o644)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state = root / "podman-secret"
            podman = fake_bin / "podman"
            podman.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == secret ]]
case "$2" in
  inspect)
    if [[ "${3:-}" == --showsecret ]]; then
      python3 -I -c 'import json, pathlib, sys; print(json.dumps(pathlib.Path(sys.argv[1]).read_text()))' "$FAKE_PODMAN_SECRET_STATE"
    else
      [[ -f "$FAKE_PODMAN_SECRET_STATE" ]]
    fi
    ;;
  create)
    cp -- "${@: -1}" "$FAKE_PODMAN_SECRET_STATE"
    ;;
  *) exit 64 ;;
esac
""",
                encoding="utf-8",
            )
            podman.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CONFIGS_ROOT": str(root / "configs"),
                    "FAKE_PODMAN_SECRET_STATE": str(state),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                }
            )

            first = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-ovms-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(state.read_text(encoding="utf-8"), canonical.read_text(encoding="utf-8"))
            self.assertEqual(stat.S_IMODE(canonical.stat().st_mode), 0o600)

            second = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-ovms-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("already matches", second.stdout)

            canonical.write_text("B" * 48 + "\n", encoding="utf-8")
            drift = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-ovms-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(drift.returncode, 0)
            self.assertIn("differs from the installed Podman secret", drift.stderr)
            self.assertEqual(state.read_text(encoding="utf-8"), "A" * 48 + "\n")

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
            operation_lock = (
                root
                / "stack"
                / "Services"
                / "abyss-stack-mcp"
                / ".runtime-operation.lock"
            )
            self.assertTrue(operation_lock.is_file())
            self.assertFalse(operation_lock.is_symlink())
            self.assertEqual(operation_lock.stat().st_mode & 0o777, 0o600)
            operation_lock.unlink()
            unsafe_lock_target = root / "unsafe-operation-lock"
            unsafe_lock_target.write_text("unsafe\n", encoding="utf-8")
            operation_lock.symlink_to(unsafe_lock_target)
            unsafe_result = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--all-user-units"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(unsafe_result.returncode, 0)
            self.assertIn(
                "operation lock must be a regular non-symlink file",
                unsafe_result.stderr,
            )

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
                'touch "$RACE_ROOT/ready.$$"\n'
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

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        "organ MCP read credential provisioning intentionally rejects root",
    )
    def test_organ_mcp_read_auth_provisions_owner_distinct_credentials(self) -> None:
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
                [
                    "bash",
                    str(INSTALL_SYSTEMD),
                    "--provision-organ-mcp-read-auth",
                ],
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
                for name in ORGAN_MCP_READ_CREDENTIAL_NAMES
            }
            self.assertEqual(len(set(credentials.values())), len(credentials))
            for name, token in credentials.items():
                with self.subTest(name=name):
                    self.assertRegex(token, r"\A[A-Za-z0-9._~-]{43,512}\Z")
                    self.assertEqual(
                        secret_dir.joinpath(name).stat().st_mode & 0o777,
                        0o600,
                    )
                    self.assertNotIn(token, first.stdout + first.stderr)

            manifest_path = secret_dir / ORGAN_MCP_READ_AUTH_MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest,
                {
                    "credentials": {
                        owner: {
                            "policy_family": "read",
                            "sha256": hashlib.sha256(
                                credentials[credential].encode("utf-8")
                            ).hexdigest(),
                        }
                        for credential, owner in (
                            ORGAN_MCP_READ_OWNER_BY_CREDENTIAL.items()
                        )
                    },
                    "schema_version": "organ_mcp_read_auth_manifest_v1",
                },
            )
            self.assertEqual(manifest_path.stat().st_mode & 0o777, 0o600)
            self.assertIn(
                "refreshed owner-distinct organ MCP read credential manifest",
                first.stdout,
            )

            second = subprocess.run(
                [
                    "bash",
                    str(INSTALL_SYSTEMD),
                    "--provision-organ-mcp-read-auth",
                ],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(
                second.stdout.count("already provisioned"),
                len(ORGAN_MCP_READ_CREDENTIAL_NAMES),
            )
            for name, token in credentials.items():
                self.assertEqual(
                    secret_dir.joinpath(name)
                    .read_text(encoding="utf-8")
                    .removesuffix("\n"),
                    token,
                )

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        "organ MCP candidate credential provisioning intentionally rejects root",
    )
    def test_organ_mcp_candidate_auth_is_distinct_from_every_read_credential(
        self,
    ) -> None:
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

            result = subprocess.run(
                [
                    "bash",
                    str(INSTALL_SYSTEMD),
                    "--provision-organ-mcp-candidate-auth",
                ],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            names = (
                *ORGAN_MCP_READ_CREDENTIAL_NAMES,
                *ORGAN_MCP_CANDIDATE_CREDENTIAL_NAMES,
            )
            credentials = {
                name: (secret_dir / name).read_text(encoding="utf-8").removesuffix("\n")
                for name in names
            }
            self.assertEqual(len(set(credentials.values())), len(names))
            manifest_path = secret_dir / ORGAN_MCP_CANDIDATE_AUTH_MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest,
                {
                    "credentials": {
                        "aoa-evals": {
                            "policy_family": "candidate",
                            "sha256": hashlib.sha256(
                                credentials[
                                    "aoa-evals-mcp-candidate-bearer-token"
                                ].encode("utf-8")
                            ).hexdigest(),
                        },
                        "aoa-memo": {
                            "policy_family": "candidate",
                            "sha256": hashlib.sha256(
                                credentials[
                                    "aoa-memo-mcp-candidate-bearer-token"
                                ].encode("utf-8")
                            ).hexdigest(),
                        },
                    },
                    "schema_version": "organ_mcp_candidate_auth_manifest_v1",
                },
            )
            self.assertEqual(manifest_path.stat().st_mode & 0o777, 0o600)
            for token in credentials.values():
                self.assertNotIn(token, result.stdout + result.stderr)

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        "abyss-stack MCP credential provisioning intentionally rejects root",
    )
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
            manifest_path = secret_dir / STACK_MCP_AUTH_MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest,
                {
                    "candidate_sha256": hashlib.sha256(
                        credentials["abyss-stack-mcp-candidate-bearer-token"].encode(
                            "utf-8"
                        )
                    ).hexdigest(),
                    "read_sha256": hashlib.sha256(
                        credentials["abyss-stack-mcp-read-bearer-token"].encode("utf-8")
                    ).hexdigest(),
                    "internal_effect_sha256": hashlib.sha256(
                        credentials[
                            "abyss-stack-mcp-internal-effect-bearer-token"
                        ].encode("utf-8")
                    ).hexdigest(),
                    "schema_version": "abyss_stack_mcp_auth_manifest_v2",
                },
            )
            self.assertEqual(manifest_path.stat().st_mode & 0o777, 0o600)
            signing_key_path = secret_dir / STACK_MCP_CANARY_SIGNING_KEY_NAME
            self.assertTrue(signing_key_path.is_file())
            self.assertFalse(signing_key_path.is_symlink())
            self.assertEqual(signing_key_path.stat().st_mode & 0o777, 0o600)
            public_key = subprocess.run(
                [
                    "openssl",
                    "pkey",
                    "-in",
                    str(signing_key_path),
                    "-pubout",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(public_key.returncode, 0, public_key.stderr)
            self.assertIn("BEGIN PUBLIC KEY", public_key.stdout)
            pinned_public_key_path = secret_dir / STACK_MCP_CANARY_PUBLIC_KEY_NAME
            self.assertTrue(pinned_public_key_path.is_file())
            self.assertFalse(pinned_public_key_path.is_symlink())
            self.assertEqual(pinned_public_key_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                pinned_public_key_path.read_text(encoding="utf-8"),
                public_key.stdout,
            )
            self.assertNotIn(
                signing_key_path.read_text(encoding="utf-8"),
                first.stdout + first.stderr,
            )
            self.assertIn(
                "provisioned abyss-stack MCP read bearer credential", first.stdout
            )
            self.assertIn(
                "provisioned abyss-stack MCP candidate bearer credential",
                first.stdout,
            )
            self.assertIn(
                "provisioned abyss-stack MCP internal-effect bearer credential",
                first.stdout,
            )
            self.assertIn(
                "provisioned abyss-stack MCP canary signing key",
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
            self.assertEqual(second.stdout.count("already provisioned"), 4)
            self.assertIn(
                "canary public key already pinned",
                second.stdout,
            )
            self.assertIn(
                "refreshed abyss-stack MCP credential separation manifest",
                second.stdout,
            )

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        "abyss-stack MCP credential provisioning intentionally rejects root",
    )
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
                "read, candidate, and internal-effect bearer credentials must be distinct",
                result.stderr,
            )
            self.assertNotIn(shared_token, result.stdout + result.stderr)

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        "abyss-stack MCP credential rotation intentionally rejects root",
    )
    def test_stack_mcp_auth_rotation_is_stopped_secret_safe_and_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            secret_dir = stack_root / "Secrets" / "Configs"
            fake_bin = root / "bin"
            fake_bin.mkdir()
            systemctl = fake_bin / "systemctl"
            systemctl.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'unit="${*: -1}"\n'
                'if [[ "$unit" == "${ABYSS_STACK_MCP_TEST_ACTIVE_UNIT:-}" ]]; then\n'
                "  printf '%s\\n' active\n"
                "else\n"
                "  printf '%s\\n' \"${ABYSS_STACK_MCP_TEST_ACTIVE_STATE:-inactive}\"\n"
                "fi\n",
                encoding="utf-8",
            )
            systemctl.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CONFIGS_ROOT": str(root / "Configs"),
                    "HOME": str(root / "home"),
                    "XDG_CONFIG_HOME": str(root / "xdg-config"),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                }
            )
            provision = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--provision-abyss-stack-mcp-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(provision.returncode, 0, provision.stderr)
            before = {
                name: secret_dir.joinpath(name)
                .read_text(encoding="utf-8")
                .removesuffix("\n")
                for name in STACK_MCP_CREDENTIAL_NAMES
            }

            rotate = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--rotate-abyss-stack-mcp-auth"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(rotate.returncode, 0, rotate.stderr)
            after = {
                name: secret_dir.joinpath(name)
                .read_text(encoding="utf-8")
                .removesuffix("\n")
                for name in STACK_MCP_CREDENTIAL_NAMES
            }
            self.assertEqual(len(set(after.values())), 3)
            for name in STACK_MCP_CREDENTIAL_NAMES:
                self.assertNotEqual(before[name], after[name])
                self.assertNotIn(after[name], rotate.stdout + rotate.stderr)
            manifest = json.loads(
                secret_dir.joinpath(STACK_MCP_AUTH_MANIFEST_NAME).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                manifest["read_sha256"],
                hashlib.sha256(
                    after["abyss-stack-mcp-read-bearer-token"].encode("utf-8")
                ).hexdigest(),
            )
            self.assertEqual(
                manifest["candidate_sha256"],
                hashlib.sha256(
                    after["abyss-stack-mcp-candidate-bearer-token"].encode("utf-8")
                ).hexdigest(),
            )
            self.assertEqual(
                manifest["internal_effect_sha256"],
                hashlib.sha256(
                    after["abyss-stack-mcp-internal-effect-bearer-token"].encode(
                        "utf-8"
                    )
                ).hexdigest(),
            )
            self.assertEqual(
                manifest["schema_version"],
                "abyss_stack_mcp_auth_manifest_v2",
            )
            self.assertIn("managed units remain stopped", rotate.stdout)

            blocked = subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), "--rotate-abyss-stack-mcp-auth"],
                cwd=REPO_ROOT,
                env={
                    **env,
                    "ABYSS_STACK_MCP_TEST_ACTIVE_UNIT": (
                        "abyss-stack-mcp-read-bootstrap.service"
                    ),
                },
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn(
                "refusing credential rotation while "
                "abyss-stack-mcp-read-bootstrap.service is active",
                blocked.stderr,
            )
            for name, token in after.items():
                self.assertEqual(
                    secret_dir.joinpath(name)
                    .read_text(encoding="utf-8")
                    .removesuffix("\n"),
                    token,
                )
                self.assertNotIn(token, blocked.stdout + blocked.stderr)

    def test_stack_mcp_credential_provisioning_is_user_scoped(self) -> None:
        installer = INSTALL_SYSTEMD.read_text(encoding="utf-8")
        self.assertIn(
            "if (((provision_abyss_stack_mcp_auth || "
            "rotate_abyss_stack_mcp_auth) && EUID == 0)); then",
            installer,
        )
        self.assertIn(
            "abyss-stack MCP credential management must run as the target user, "
            "not root",
            installer,
        )

    def test_stack_mcp_runtime_requires_the_released_aoa_sdk(self) -> None:
        installer = INSTALL_SYSTEMD.read_text(encoding="utf-8")
        self.assertIn("import abyss_stack_mcp, aoa_sdk, mcp, pydantic", installer)
        self.assertIn('version("aoa-sdk") == "0.10.2"', installer)

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        "abyss-stack MCP runtime provisioning intentionally rejects root",
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
                '[project]\nname = "abyss-stack-mcp"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            lock_path = service_root / "requirements.lock"
            lock_path.write_text(
                "test-package==1.0.0 \\\n    --hash=sha256:" + ("0" * 64) + "\n",
                encoding="utf-8",
            )
            source_file = service_root / "service.py"
            source_file.write_text("VALUE = 1\n", encoding="utf-8")
            pip_log = root / "pip.log"
            server_log = root / "server.log"
            entrypoint_log = root / "entrypoint.log"
            bootstrap = root / "fake-python"
            bootstrap.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'if [[ "${1:-}" == "-B" && -f "${2:-}" ]]; then\n'
                "  printf 'bytecode-disabled\\n' > "
                '"$ABYSS_STACK_MCP_TEST_ENTRYPOINT_LOG"\n'
                "  exit 0\n"
                "fi\n"
                'if [[ -n "${PYTHONHOME+x}" || '
                '-n "${PYTHONPATH+x}" ]]; then\n'
                "  exit 65\n"
                "fi\n"
                'if [[ "${1:-}" != "-I" ]]; then\n'
                "  exit 66\n"
                "fi\n"
                "shift\n"
                'if [[ "$1" == "-B" && "$2" == "-m" && '
                '"$3" == "abyss_stack_mcp.server" ]]; then\n'
                '  source_lock="${AOA_STACK_ROOT}/Services/'
                'abyss-stack-mcp/.source-projection.lock"\n'
                '  runtime_lock="${AOA_STACK_ROOT}/Services/'
                'abyss-stack-mcp/.runtime-provision.lock"\n'
                "  if /usr/bin/flock --exclusive --nonblock "
                '"$source_lock" /usr/bin/true; then\n'
                "    exit 67\n"
                "  fi\n"
                "  if /usr/bin/flock --exclusive --nonblock "
                '"$runtime_lock" /usr/bin/true; then\n'
                "    exit 68\n"
                "  fi\n"
                "  printf 'verified-and-locked\\n' > "
                '"$ABYSS_STACK_MCP_TEST_SERVER_LOG"\n'
                "  exit 0\n"
                "fi\n"
                'if [[ "$1" == "-m" && "$2" == "venv" ]]; then\n'
                '  target="${!#}"\n'
                '  mkdir -p "$target/bin"\n'
                '  cp "$0" "$target/bin/python"\n'
                '  chmod 0755 "$target/bin/python"\n'
                "  exit 0\n"
                "fi\n"
                'if [[ "$1" == "-m" && "$2" == "pip" ]]; then\n'
                '  printf \'%s\\n\' "$*" >> "$ABYSS_STACK_MCP_TEST_PIP_LOG"\n'
                '  if [[ "${ABYSS_STACK_MCP_TEST_PIP_FAIL:-0}" == 1 && '
                '"$*" == *"--require-hashes"* ]]; then\n'
                '    printf \'pip-require-hashes\\n\' >> '
                '"$ABYSS_STACK_MCP_TEST_EVENT_LOG"\n'
                "    exit 70\n"
                "  fi\n"
                '  if [[ -n "${ABYSS_STACK_MCP_TEST_BLOCK_INSTALL:-}" && '
                '"$*" == *"--require-hashes"* ]]; then\n'
                '    : > "$ABYSS_STACK_MCP_TEST_BLOCK_INSTALL"\n'
                "    sleep 300\n"
                "  fi\n"
                '  if [[ "$*" == *"--require-hashes"* ]]; then\n'
                '    printf \'pip-require-hashes\\n\' >> '
                '"$ABYSS_STACK_MCP_TEST_EVENT_LOG"\n'
                '    package_root="$(dirname "$0")/../lib/python/site-packages/'
                'test_package"\n'
                '    mkdir -p "$package_root"\n'
                "    printf 'VALUE = 1\\n' > \"$package_root/__init__.py\"\n"
                "  fi\n"
                '  if [[ "$*" == *"--no-deps --no-build-isolation"* ]]; then\n'
                '    entrypoint="$(dirname "$0")/abyss-stack-mcp"\n'
                '    printf \'#!%s\\nexit 0\\n\' "$0" > "$entrypoint"\n'
                '    chmod 0755 "$entrypoint"\n'
                "  fi\n"
                '  if [[ -n "${ABYSS_STACK_MCP_TEST_MUTATE_SOURCE_DURING_BUILD:-}" ]]; then\n'
                "    printf 'VALUE = 99\\n' > "
                '"$ABYSS_STACK_MCP_TEST_MUTATE_SOURCE_DURING_BUILD"\n'
                "  fi\n"
                '  if [[ -n "${ABYSS_STACK_MCP_TEST_ACTIVATE_DURING_BUILD:-}" ]]; then\n'
                '    : > "$ABYSS_STACK_MCP_TEST_ACTIVATE_DURING_BUILD"\n'
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                'if [[ "$1" == "-c" ]]; then\n'
                '  if [[ "${ABYSS_STACK_MCP_TEST_IMPORT_FAIL:-0}" == 1 ]]; then\n'
                "    exit 69\n"
                "  fi\n"
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
            fake_mv = fake_bin / "mv"
            fake_mv.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'source_path="${@: -2:1}"\n'
                'target_path="${@: -1}"\n'
                'source_name="$(basename -- "$source_path")"\n'
                'if [[ "${ABYSS_STACK_MCP_TEST_FAIL_ACTIVATION:-0}" == 1 && '
                '"$source_name" == .venv.* && '
                '"$source_name" != .venv.previous.* && '
                '"$target_path" == */venv ]]; then\n'
                "  exit 71\n"
                "fi\n"
                'exec /usr/bin/mv "$@"\n',
                encoding="utf-8",
            )
            fake_mv.chmod(0o755)
            unit_source_dir = stack_root / "Configs" / "systemd" / "user"
            unit_source_dir.mkdir(parents=True)
            unit_target_dir = root / "xdg-config" / "systemd" / "user"
            unit_target_dir.mkdir(parents=True)
            for source_unit in (
                STACK_MCP_READ_UNIT,
                STACK_MCP_READ_BOOTSTRAP_UNIT,
                STACK_MCP_CANDIDATE_UNIT,
                STACK_MCP_INTERNAL_EFFECT_UNIT,
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
            systemctl_log = root / "runtime-events.log"
            systemctl_state = root / "systemctl-state"
            systemctl_state.mkdir()
            systemctl.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'printf \'%s\\n\' "$*" >> "$ABYSS_STACK_MCP_TEST_SYSTEMCTL_LOG"\n'
                'args=("$@")\n'
                'if [[ "${args[0]:-}" == "--user" ]]; then args=("${args[@]:1}"); fi\n'
                'command="${args[0]:-}"\n'
                'unit="${!#}"\n'
                'if [[ "${ABYSS_STACK_MCP_TEST_SYSTEMCTL_FAIL:-0}" == 1 ]]; '
                "then\n"
                "  exit 1\n"
                "fi\n"
                'if [[ "$command" == "list-units" ]]; then\n'
                '  for item in ${ABYSS_STACK_MCP_TEST_ACTIVE_ORGAN_UNITS:-}; do\n'
                "    printf '%s loaded active running test\\n' \"$item\"\n"
                "  done\n"
                "  exit 0\n"
                "fi\n"
                'is_active=0\n'
                'if [[ "${ABYSS_STACK_MCP_TEST_ACTIVE_UNIT:-}" == "$unit" && '
                '! -f "$ABYSS_STACK_MCP_TEST_SYSTEMCTL_STATE/$unit.stopped" ]]; then\n'
                '  is_active=1\n'
                'elif [[ "$unit" == "abyss-stack-mcp-read.service" && '
                '-f "${ABYSS_STACK_MCP_TEST_ACTIVATE_DURING_BUILD:-/nonexistent}" && '
                '! -f "$ABYSS_STACK_MCP_TEST_SYSTEMCTL_STATE/$unit.stopped" ]]; then\n'
                '  is_active=1\n'
                "fi\n"
                'if [[ "$command" == "is-active" ]]; then\n'
                '  ((is_active))\n'
                "  exit\n"
                "fi\n"
                'if [[ "$command" == "stop" ]]; then\n'
                '  for item in "${args[@]:1}"; do\n'
                '    [[ "$item" == *.service ]] || continue\n'
                '    : > "$ABYSS_STACK_MCP_TEST_SYSTEMCTL_STATE/$item.stopped"\n'
                "  done\n"
                "  exit 0\n"
                "fi\n"
                'if [[ "$command" == "start" ]]; then\n'
                '  for item in "${args[@]:1}"; do\n'
                '    [[ "$item" == *.service ]] || continue\n'
                '    rm -f -- "$ABYSS_STACK_MCP_TEST_SYSTEMCTL_STATE/$item.stopped"\n'
                "  done\n"
                "  exit 0\n"
                "fi\n"
                "load_state=loaded\n"
                "active_state=inactive\n"
                'fragment_path="${XDG_CONFIG_HOME}/systemd/user/${unit}"\n'
                'contour="${unit#abyss-stack-mcp-}"\n'
                'contour="${contour%.service}"\n'
                'if [[ "$contour" == "internal-effect" ]]; then '
                "contour=internal_effect; fi\n"
                'if [[ "$contour" == "read-bootstrap" ]]; then '
                "contour=read; fi\n"
                "exec_path=/usr/bin/flock\n"
                'exec_start="/usr/bin/flock --shared --no-fork '
                "${AOA_STACK_ROOT}/Services/abyss-stack-mcp/"
                ".source-projection.lock /usr/bin/flock --shared --no-fork "
                "${AOA_STACK_ROOT}/Services/abyss-stack-mcp/"
                ".runtime-provision.lock /usr/bin/env "
                "${AOA_CONFIGS_ROOT}/scripts/aoa-install-systemd "
                '--launch-verified-abyss-stack-mcp=${contour}"\n'
                'if [[ "$contour" == "candidate" || "$contour" == "internal_effect" ]]; then\n'
                '  exec_start="/usr/bin/flock --shared --no-fork '
                "${AOA_STACK_ROOT}/Services/abyss-stack-mcp/"
                '.runtime-operation.lock ${exec_start}"\n'
                "fi\n"
                'if [[ "${ABYSS_STACK_MCP_TEST_UNLOADED_UNIT:-}" == '
                '"$unit" ]]; then\n'
                "  load_state=not-found\n"
                "  fragment_path=\n"
                "  exec_path=\n"
                "  exec_start=\n"
                "fi\n"
                'if [[ "${ABYSS_STACK_MCP_TEST_STALE_UNIT:-}" == '
                '"$unit" ]]; then\n'
                "  exec_path=/usr/bin/env\n"
                '  exec_start="/usr/bin/env '
                "${AOA_STACK_ROOT}/Services/abyss-stack-mcp/venv/bin/python "
                '-I -B -m abyss_stack_mcp.server"\n'
                "fi\n"
                'if ((is_active)); then\n'
                "  active_state=active\n"
                "fi\n"
                "printf 'LoadState=%s\\n' \"$load_state\"\n"
                "printf 'ActiveState=%s\\n' \"$active_state\"\n"
                "printf 'FragmentPath=%s\\n' \"$fragment_path\"\n"
                'if [[ -n "$exec_start" ]]; then\n'
                "  printf 'ExecStart={ path=%s ; argv[]=%s ; "
                "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; "
                "pid=0 ; code=(null) ; status=0/0 }\\n' "
                '"$exec_path" "$exec_start"\n'
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
                    "ABYSS_STACK_MCP_TEST_SERVER_LOG": str(server_log),
                    "ABYSS_STACK_MCP_TEST_ENTRYPOINT_LOG": str(entrypoint_log),
                    "ABYSS_STACK_MCP_TEST_SYSTEMCTL_LOG": str(systemctl_log),
                    "ABYSS_STACK_MCP_TEST_SYSTEMCTL_STATE": str(systemctl_state),
                    "ABYSS_STACK_MCP_TEST_EVENT_LOG": str(systemctl_log),
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
            verify_command = [
                "bash",
                str(INSTALL_SYSTEMD),
                "--verify-abyss-stack-mcp-runtime",
            ]
            read_verify_command = [
                "bash",
                str(INSTALL_SYSTEMD),
                "--verify-abyss-stack-mcp-runtime=read",
            ]
            candidate_verify_command = [
                "bash",
                str(INSTALL_SYSTEMD),
                "--verify-abyss-stack-mcp-runtime=candidate",
            ]
            repair_eligibility_command = [
                "bash",
                str(INSTALL_SYSTEMD),
                "--verify-abyss-stack-mcp-repair-eligibility",
            ]
            repair_command = [
                "bash",
                str(INSTALL_SYSTEMD),
                "--repair-abyss-stack-mcp-runtime",
            ]

            read_unit_source = unit_source_dir / "abyss-stack-mcp-read.service"
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

            blocked_install_marker = root / "blocked-install"
            blocking = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env={
                    **env,
                    "ABYSS_STACK_MCP_TEST_BLOCK_INSTALL": str(
                        blocked_install_marker
                    ),
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + 5
                while (
                    not blocked_install_marker.exists()
                    and blocking.poll() is None
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.02)
                self.assertTrue(blocked_install_marker.exists())
                staging_root = stack_root / "Services" / "abyss-stack-mcp"
                self.assertTrue(list(staging_root.glob(".venv.*")))
                os.killpg(blocking.pid, signal.SIGTERM)
                blocking.communicate(timeout=5)
            finally:
                if blocking.poll() is None:
                    os.killpg(blocking.pid, signal.SIGKILL)
                    blocking.communicate(timeout=5)
            self.assertEqual(blocking.returncode, 143)
            self.assertEqual(list(staging_root.glob(".venv.*")), [])

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
            runtime_root = stack_root / "Services" / "abyss-stack-mcp"
            marker = venv / ".abyss-stack-mcp-runtime-identity"
            content_marker = venv / ".abyss-stack-mcp-runtime-content-digest"
            runtime_lock = (
                stack_root / "Services" / "abyss-stack-mcp" / ".runtime-provision.lock"
            )
            operation_lock = (
                stack_root / "Services" / "abyss-stack-mcp" / ".runtime-operation.lock"
            )
            rollback_grant = (
                stack_root
                / "Services"
                / "abyss-stack-mcp"
                / ".read-repair-rollback-grant"
            )
            source_projection_lock = (
                stack_root / "Services" / "abyss-stack-mcp" / ".source-projection.lock"
            )
            audit_root = stack_root / "Logs" / "mcp" / "audit"
            read_audit_journal = audit_root / "policy-read.jsonl"
            candidate_audit_journal = audit_root / "policy-candidate.jsonl"
            observation_root = stack_root / "Logs" / "mcp" / "observations"
            observation_path = observation_root / "current.json"
            keeper_inbox_root = (
                stack_root / "Logs" / "mcp" / "admission" / "keeper-inbox"
            )
            admission_root = stack_root / "Logs" / "mcp" / "admission"
            preflight_root = stack_root / "Logs" / "mcp" / "preflight"
            protocol_watch_root = stack_root / "Logs" / "mcp" / "protocol-watch"
            orchestration_root = (
                stack_root / "Logs" / "mcp" / "cross-organ-orchestrations"
            )
            tasks_root = stack_root / "Logs" / "mcp" / "tasks"
            read_tasks_root = tasks_root / "abyss-stack-read"
            effect_root = (
                stack_root
                / "Logs"
                / "mcp"
                / "internal-effects"
                / "read-restart-pilot"
            )
            first_identity = marker.read_text(encoding="utf-8").strip()
            self.assertRegex(first_identity, r"\A[0-9a-f]{64}:[0-9a-f]{64}\Z")
            first_content_digest = content_marker.read_text(encoding="utf-8").strip()
            self.assertRegex(
                first_content_digest,
                r"\A[0-9a-f]{64}\Z",
            )
            self.assertTrue((venv / "bin" / "python").is_file())
            self.assertFalse((venv / "bin" / "python").is_symlink())
            entrypoint = venv / "bin" / "abyss-stack-mcp"
            self.assertEqual(
                entrypoint.read_text(encoding="utf-8").splitlines()[0],
                f"#!{venv}/bin/python -B",
            )
            self.assertNotIn(
                "/.venv.",
                entrypoint.read_text(encoding="utf-8").splitlines()[0],
            )
            direct_entrypoint_env = dict(env)
            direct_entrypoint_env.pop("PYTHONHOME")
            direct_entrypoint_env.pop("PYTHONPATH")
            direct_entrypoint = subprocess.run(
                [str(entrypoint)],
                cwd=REPO_ROOT,
                env=direct_entrypoint_env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                direct_entrypoint.returncode,
                0,
                direct_entrypoint.stderr,
            )
            self.assertEqual(
                entrypoint_log.read_text(encoding="utf-8"),
                "bytecode-disabled\n",
            )
            self.assertTrue(runtime_lock.is_file())
            self.assertEqual(runtime_lock.stat().st_mode & 0o777, 0o600)
            self.assertTrue(operation_lock.is_file())
            self.assertEqual(operation_lock.stat().st_mode & 0o777, 0o600)
            self.assertTrue(source_projection_lock.is_file())
            self.assertEqual(
                source_projection_lock.stat().st_mode & 0o777,
                0o600,
            )
            self.assertEqual(audit_root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(
                read_audit_journal.stat().st_mode & 0o777,
                0o600,
            )
            self.assertEqual(
                candidate_audit_journal.stat().st_mode & 0o777,
                0o600,
            )
            self.assertNotEqual(read_audit_journal, candidate_audit_journal)
            unsafe_grant_target = root / "unsafe-rollback-grant"
            unsafe_grant_target.write_text("unsafe\n", encoding="utf-8")
            rollback_grant.symlink_to(unsafe_grant_target)
            unsafe_grant = subprocess.run(
                repair_eligibility_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(unsafe_grant.returncode, 0)
            self.assertIn(
                "read rollback grant must be a regular non-symlink file",
                unsafe_grant.stderr,
            )
            rollback_grant.unlink()
            rollback_grant.write_text("unsafe\n", encoding="utf-8")
            rollback_grant.chmod(0o644)
            public_grant = subprocess.run(
                repair_eligibility_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(public_grant.returncode, 0)
            self.assertIn(
                "read rollback grant must use mode 0600",
                public_grant.stderr,
            )
            rollback_grant.unlink()
            self.assertEqual(
                observation_root.stat().st_mode & 0o777,
                0o700,
            )
            self.assertEqual(
                keeper_inbox_root.stat().st_mode & 0o777,
                0o700,
            )
            self.assertEqual(
                protocol_watch_root.stat().st_mode & 0o777,
                0o700,
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

            for active_read_unit in (
                "abyss-stack-mcp-read.service",
                "abyss-stack-mcp-read-bootstrap.service",
            ):
                with self.subTest(active_read_unit=active_read_unit):
                    eligible = subprocess.run(
                        repair_eligibility_command,
                        cwd=REPO_ROOT,
                        env={
                            **env,
                            "ABYSS_STACK_MCP_TEST_ACTIVE_UNIT": active_read_unit,
                        },
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(eligible.returncode, 0, eligible.stderr)

            for active_non_read_unit in (
                "abyss-stack-mcp-candidate.service",
                "abyss-stack-mcp-internal-effect.service",
            ):
                with self.subTest(active_non_read_unit=active_non_read_unit):
                    ineligible = subprocess.run(
                        repair_eligibility_command,
                        cwd=REPO_ROOT,
                        env={
                            **env,
                            "ABYSS_STACK_MCP_TEST_ACTIVE_UNIT": active_non_read_unit,
                        },
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(ineligible.returncode, 0)
                    self.assertIn(
                        f"while {active_non_read_unit} is active",
                        ineligible.stderr,
                    )

            source_file.write_text("VALUE = repair_failure\n", encoding="utf-8")
            systemctl_log.write_text("", encoding="utf-8")
            failed_repair = subprocess.run(
                repair_command,
                cwd=REPO_ROOT,
                env={
                    **env,
                    "ABYSS_STACK_MCP_TEST_ACTIVE_UNIT": (
                        "abyss-stack-mcp-read.service"
                    ),
                    "ABYSS_STACK_MCP_TEST_PIP_FAIL": "1",
                },
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(failed_repair.returncode, 0)
            self.assertIn(
                "failed to install the deployed abyss-stack MCP hash-locked "
                "dependency closure",
                failed_repair.stderr,
            )
            failed_repair_events = systemctl_log.read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertIn("pip-require-hashes", failed_repair_events)
            self.assertFalse(
                any(event.startswith("--user stop ") for event in failed_repair_events)
            )
            self.assertFalse(
                (systemctl_state / "abyss-stack-mcp-read.service.stopped").exists()
            )
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), first_identity)

            source_file.write_text("VALUE = post_stop_failure\n", encoding="utf-8")
            systemctl_log.write_text("", encoding="utf-8")
            post_stop_failure = subprocess.run(
                repair_command,
                cwd=REPO_ROOT,
                env={
                    **env,
                    "ABYSS_STACK_MCP_TEST_ACTIVE_UNIT": (
                        "abyss-stack-mcp-read.service"
                    ),
                    "ABYSS_STACK_MCP_TEST_ACTIVE_ORGAN_UNITS": (
                        "aoa-organ-mcp-read@aoa-memo.service"
                    ),
                    "ABYSS_STACK_MCP_TEST_FAIL_ACTIVATION": "1",
                },
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(post_stop_failure.returncode, 0)
            self.assertIn(
                "failed to activate the provisioned abyss-stack MCP runtime",
                post_stop_failure.stderr,
            )
            post_stop_events = systemctl_log.read_text(
                encoding="utf-8"
            ).splitlines()
            post_stop_index = next(
                index
                for index, event in enumerate(post_stop_events)
                if event.startswith("--user stop ")
            )
            restart_index = post_stop_events.index(
                "--user start abyss-stack-mcp-read.service"
            )
            organ_restart_index = post_stop_events.index(
                "--user start aoa-organ-mcp-read@aoa-memo.service"
            )
            self.assertLess(post_stop_index, restart_index)
            self.assertLess(post_stop_index, organ_restart_index)
            self.assertFalse(
                (systemctl_state / "abyss-stack-mcp-read.service.stopped").exists()
            )
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), first_identity)
            self.assertTrue(rollback_grant.is_file())
            self.assertFalse(rollback_grant.is_symlink())
            self.assertEqual(rollback_grant.stat().st_mode & 0o777, 0o600)
            self.assertRegex(
                rollback_grant.read_text(encoding="utf-8").strip(),
                r"\A[0-9a-f]{64}:[0-9a-f]{64}:[0-9a-f]{64}\Z",
            )
            rollback_read = subprocess.run(
                read_verify_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(rollback_read.returncode, 0, rollback_read.stderr)
            for strict_verify_command in (
                verify_command,
                candidate_verify_command,
            ):
                with self.subTest(strict_verify_command=strict_verify_command[-1]):
                    rollback_strict = subprocess.run(
                        strict_verify_command,
                        cwd=REPO_ROOT,
                        env=env,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(rollback_strict.returncode, 0)
                    self.assertIn(
                        "runtime source-and-lock identity mismatch",
                        rollback_strict.stderr,
                    )

            source_file.write_text("VALUE = repair_success\n", encoding="utf-8")
            systemctl_log.write_text("", encoding="utf-8")
            successful_repair = subprocess.run(
                repair_command,
                cwd=REPO_ROOT,
                env={
                    **env,
                    "ABYSS_STACK_MCP_TEST_ACTIVE_UNIT": (
                        "abyss-stack-mcp-read.service"
                    ),
                    "ABYSS_STACK_MCP_TEST_ACTIVE_ORGAN_UNITS": (
                        "aoa-organ-mcp-read@aoa-memo.service"
                    ),
                },
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                successful_repair.returncode,
                0,
                successful_repair.stderr,
            )
            successful_repair_events = systemctl_log.read_text(
                encoding="utf-8"
            ).splitlines()
            build_event = successful_repair_events.index("pip-require-hashes")
            stop_event = next(
                index
                for index, event in enumerate(successful_repair_events)
                if event.startswith("--user stop ")
            )
            self.assertIn(
                "aoa-organ-mcp-read@aoa-memo.service",
                successful_repair_events[stop_event],
            )
            self.assertLess(build_event, stop_event)
            self.assertFalse(rollback_grant.exists())
            self.assertNotEqual(
                marker.read_text(encoding="utf-8").strip(),
                first_identity,
            )
            for stopped_marker in systemctl_state.glob("*.stopped"):
                stopped_marker.unlink()
            source_file.write_text("VALUE = 1\n", encoding="utf-8")
            restored_baseline = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(restored_baseline.returncode, 0, restored_baseline.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), first_identity)

            stale_eligibility = subprocess.run(
                repair_eligibility_command,
                cwd=REPO_ROOT,
                env={
                    **env,
                    "ABYSS_STACK_MCP_TEST_STALE_UNIT": (
                        "abyss-stack-mcp-read.service"
                    ),
                },
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(stale_eligibility.returncode, 0)
            self.assertIn(
                "is not loaded with the lock-aware ExecStart",
                stale_eligibility.stderr,
            )

            for unsafe_runtime_root in (
                observation_root,
                keeper_inbox_root,
                admission_root,
                preflight_root,
                protocol_watch_root,
                orchestration_root,
                read_tasks_root,
                tasks_root,
                effect_root,
                venv,
                runtime_root,
            ):
                with self.subTest(unsafe_runtime_root=unsafe_runtime_root):
                    safe_runtime_root = unsafe_runtime_root.with_name(
                        f"{unsafe_runtime_root.name}.safe"
                    )
                    unsafe_runtime_root.rename(safe_runtime_root)
                    unsafe_runtime_root.symlink_to(
                        safe_runtime_root,
                        target_is_directory=True,
                    )
                    try:
                        unsafe_repair_root = subprocess.run(
                            repair_eligibility_command,
                            cwd=REPO_ROOT,
                            env=env,
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                        self.assertNotEqual(unsafe_repair_root.returncode, 0)
                        self.assertIn(
                            "non-symlink directory",
                            unsafe_repair_root.stderr,
                        )
                    finally:
                        unsafe_runtime_root.unlink()
                        safe_runtime_root.rename(unsafe_runtime_root)

            unsafe_observation_target = root / "unsafe-observation.json"
            unsafe_observation_target.write_text("{}\n", encoding="utf-8")
            observation_path.symlink_to(unsafe_observation_target)
            unsafe_observation = subprocess.run(
                repair_eligibility_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(unsafe_observation.returncode, 0)
            self.assertIn(
                "observation path must be a regular non-symlink file",
                unsafe_observation.stderr,
            )
            observation_path.unlink()

            runtime_python = venv / "bin" / "python"
            runtime_python.unlink()
            runtime_python.symlink_to(bootstrap)
            symlinked_runtime_python = subprocess.run(
                verify_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(symlinked_runtime_python.returncode, 0)
            self.assertIn(
                "runtime Python must be an executable regular non-symlink file",
                symlinked_runtime_python.stderr,
            )
            runtime_python.unlink()
            shutil.copy2(bootstrap, runtime_python)

            with read_audit_journal.open("r+b") as oversized_journal:
                oversized_journal.truncate(33_554_433)
            oversized_repair_eligibility = subprocess.run(
                repair_eligibility_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(oversized_repair_eligibility.returncode, 0)
            self.assertIn(
                "read audit journal exceeds the managed 32 MiB capacity",
                oversized_repair_eligibility.stderr,
            )
            with read_audit_journal.open("r+b") as oversized_journal:
                oversized_journal.truncate(0)

            candidate_audit_journal.unlink()
            unsafe_target = root / "unsafe-audit-target.jsonl"
            unsafe_target.touch(mode=0o600)
            candidate_audit_journal.symlink_to(unsafe_target)
            unsafe_repair_eligibility = subprocess.run(
                repair_eligibility_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(unsafe_repair_eligibility.returncode, 0)
            self.assertIn(
                "candidate audit journal must be a regular non-symlink file",
                unsafe_repair_eligibility.stderr,
            )
            unsafe_audit = subprocess.run(
                verify_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(unsafe_audit.returncode, 0)
            self.assertIn(
                "candidate audit journal must be a regular non-symlink file",
                unsafe_audit.stderr,
            )
            candidate_audit_journal.unlink()
            candidate_audit_journal.touch(mode=0o600)

            candidate_audit_journal.chmod(0o640)
            full_audit_rejects_candidate_drift = subprocess.run(
                verify_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(
                full_audit_rejects_candidate_drift.returncode,
                0,
            )
            self.assertIn(
                "candidate audit journal must have mode 0600",
                full_audit_rejects_candidate_drift.stderr,
            )

            read_contour_verification = subprocess.run(
                [*verify_command[:-1], f"{verify_command[-1]}=read"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                read_contour_verification.returncode,
                0,
                read_contour_verification.stderr,
            )
            candidate_contour_verification = subprocess.run(
                [*verify_command[:-1], f"{verify_command[-1]}=candidate"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(candidate_contour_verification.returncode, 0)
            self.assertIn(
                "candidate audit journal must have mode 0600",
                candidate_contour_verification.stderr,
            )
            candidate_audit_journal.chmod(0o600)

            source_projection_lock.chmod(0o400)
            runtime_lock.chmod(0o400)
            verified = subprocess.run(
                verify_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(verified.stdout, "")

            env["ABYSS_STACK_MCP_POLICY_FAMILY"] = "read"
            mismatched_launch = subprocess.run(
                [
                    "bash",
                    str(INSTALL_SYSTEMD),
                    "--launch-verified-abyss-stack-mcp=candidate",
                ],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(mismatched_launch.returncode, 0)
            self.assertIn(
                "launch contour does not match the policy family",
                mismatched_launch.stderr,
            )

            launched = subprocess.run(
                [
                    "/usr/bin/flock",
                    "--shared",
                    "--no-fork",
                    str(source_projection_lock),
                    "/usr/bin/flock",
                    "--shared",
                    "--no-fork",
                    str(runtime_lock),
                    "/usr/bin/env",
                    str(INSTALL_SYSTEMD),
                    "--launch-verified-abyss-stack-mcp=read",
                ],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(launched.returncode, 0, launched.stderr)
            self.assertEqual(
                server_log.read_text(encoding="utf-8"),
                "verified-and-locked\n",
            )
            source_projection_lock.chmod(0o600)
            runtime_lock.chmod(0o600)

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

            source_file.write_text("VALUE = 2\n", encoding="utf-8")
            source_drift = subprocess.run(
                verify_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(source_drift.returncode, 0)
            self.assertIn(
                "runtime source-and-lock identity mismatch",
                source_drift.stderr,
            )
            source_file.write_text("VALUE = 1\n", encoding="utf-8")

            bootstrap.write_text(
                bootstrap.read_text(encoding="utf-8")
                + "\n# simulated host interpreter update\n",
                encoding="utf-8",
            )
            interpreter_update = subprocess.run(
                verify_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                interpreter_update.returncode,
                0,
                interpreter_update.stderr,
            )

            import_failure = subprocess.run(
                verify_command,
                cwd=REPO_ROOT,
                env={**env, "ABYSS_STACK_MCP_TEST_IMPORT_FAIL": "1"},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(import_failure.returncode, 0)
            self.assertIn(
                "runtime Python dependency/import check failed",
                import_failure.stderr,
            )

            runtime_python.write_text(
                runtime_python.read_text(encoding="utf-8")
                + "\n# simulated measured runtime corruption\n",
                encoding="utf-8",
            )
            runtime_drift = subprocess.run(
                verify_command,
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(runtime_drift.returncode, 0)
            self.assertIn(
                "abyss-stack MCP runtime content digest mismatch",
                runtime_drift.stderr,
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
                "abyss-stack-mcp-read-bootstrap.service",
                "abyss-stack-mcp-candidate.service",
                "abyss-stack-mcp-internal-effect.service",
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
                "cannot inspect the loaded definition for abyss-stack-mcp-read.service",
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
                    "ABYSS_STACK_MCP_TEST_MUTATE_SOURCE_DURING_BUILD": str(source_file),
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

    def test_stack_mcp_runtime_verification_is_read_only_and_standalone(
        self,
    ) -> None:
        result = self.run_install_systemd(
            "--verify-abyss-stack-mcp-runtime",
            "--restart-now",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "runtime verification must be a standalone read-only action",
            result.stderr,
        )

        launch_result = self.run_install_systemd(
            "--launch-verified-abyss-stack-mcp",
            "--restart-now",
        )
        self.assertNotEqual(launch_result.returncode, 0)
        self.assertIn(
            "verified abyss-stack MCP launch must be a standalone unit action",
            launch_result.stderr,
        )

        invalid_contour = self.run_install_systemd(
            "--verify-abyss-stack-mcp-runtime=effect",
        )
        self.assertNotEqual(invalid_contour.returncode, 0)
        self.assertIn(
            "runtime verification contour must be all, read, candidate, or "
            "internal_effect",
            invalid_contour.stderr,
        )

        repair_eligibility = self.run_install_systemd(
            "--verify-abyss-stack-mcp-repair-eligibility",
            "--restart-now",
        )
        self.assertNotEqual(repair_eligibility.returncode, 0)
        self.assertIn(
            "repair eligibility verification must be a standalone read-only action",
            repair_eligibility.stderr,
        )

        repair = self.run_install_systemd(
            "--repair-abyss-stack-mcp-runtime",
            "--restart-now",
        )
        self.assertNotEqual(repair.returncode, 0)
        self.assertIn(
            "runtime repair must be a standalone action",
            repair.stderr,
        )

    def test_stack_mcp_auto_repair_policy_is_explicit_reversible_and_standalone(
        self,
    ) -> None:
        combined = self.run_install_systemd(
            "--enable-abyss-stack-mcp-auto-repair",
            "--all-user-units",
        )
        self.assertNotEqual(combined.returncode, 0)
        self.assertIn(
            "auto-repair policy changes must be standalone actions",
            combined.stderr,
        )

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
            marker = (
                stack_root
                / "Secrets"
                / "Configs"
                / "abyss-stack-mcp-runtime-auto-repair.enabled"
            )

            for expected_fragment in ("enabled", "already enabled"):
                enabled = subprocess.run(
                    [
                        "bash",
                        str(INSTALL_SYSTEMD),
                        "--enable-abyss-stack-mcp-auto-repair",
                    ],
                    cwd=REPO_ROOT,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(enabled.returncode, 0, enabled.stderr)
                self.assertIn(expected_fragment, enabled.stdout)
                self.assertEqual(marker.read_text(encoding="utf-8"), "enabled\n")
                self.assertEqual(marker.stat().st_mode & 0o777, 0o600)

            for expected_fragment in ("disabled", "already disabled"):
                disabled = subprocess.run(
                    [
                        "bash",
                        str(INSTALL_SYSTEMD),
                        "--disable-abyss-stack-mcp-auto-repair",
                    ],
                    cwd=REPO_ROOT,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(disabled.returncode, 0, disabled.stderr)
                self.assertIn(expected_fragment, disabled.stdout)
                self.assertFalse(marker.exists())

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
            stack_read_credential = credential.parent / "abyss-stack-mcp-read-bearer-token"
            stack_read_credential.write_text(
                f"{'s' * 64}\n", encoding="utf-8"
            )
            stack_read_credential.chmod(0o600)
            owner_tokens: list[str] = []
            for index, name in enumerate(
                CODEX_MCP_READ_CREDENTIAL_NAMES
            ):
                owner_token = f"test-owner-{index}-" + (chr(ord("b") + index) * 50)
                owner_tokens.append(owner_token)
                owner_credential = credential.parent / name
                owner_credential.write_text(f"{owner_token}\n", encoding="utf-8")
                owner_credential.chmod(0o600)
            capture_token = root / "captured-token"
            capture_args = root / "captured-args"
            fake_codex = root / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' "
                '"$AOA_DECISIONS_MCP_READ_BEARER_TOKEN" '
                '"$AOA_MEMO_MCP_READ_BEARER_TOKEN" '
                '"$AOA_EVALS_MCP_READ_BEARER_TOKEN" '
                '"$AOA_KAG_MCP_READ_BEARER_TOKEN" '
                '"$AOA_4PDA_CONNECTOR_MCP_READ_BEARER_TOKEN" '
                '"$AOA_DISCORD_CONNECTOR_MCP_READ_BEARER_TOKEN" '
                '"$AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN" '
                '"$AOA_STATS_MCP_READ_BEARER_TOKEN" '
                '"$AOA_TELEGRAM_CONNECTOR_MCP_READ_BEARER_TOKEN" '
                '"$ABYSS_MACHINE_MCP_READ_BEARER_TOKEN" > "$CAPTURE_TOKEN"\n'
                'printf \'%s\\n\' "$ABYSS_STACK_MCP_READ_BEARER_TOKEN" >> "$CAPTURE_TOKEN"\n'
                'printf \'%s\\n\' "$@" > "$CAPTURE_ARGS"\n',
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CODEX_EXECUTABLE": str(fake_codex),
                    "AOA_MCP_READINESS_SKIP": "1",
                    "CAPTURE_TOKEN": str(capture_token),
                    "CAPTURE_ARGS": str(capture_args),
                }
            )
            for environment_name in (
                "AOA_MCP_HTTP_BEARER_TOKEN",
                "AOA_DECISIONS_MCP_READ_BEARER_TOKEN",
                "AOA_MEMO_MCP_READ_BEARER_TOKEN",
                "AOA_MEMO_MCP_CANDIDATE_BEARER_TOKEN",
                "AOA_EVALS_MCP_READ_BEARER_TOKEN",
                "AOA_EVALS_MCP_CANDIDATE_BEARER_TOKEN",
                "AOA_KAG_MCP_READ_BEARER_TOKEN",
                "AOA_4PDA_CONNECTOR_MCP_READ_BEARER_TOKEN",
                "AOA_COURSE_CONNECTOR_MCP_READ_BEARER_TOKEN",
                "AOA_DISCORD_CONNECTOR_MCP_READ_BEARER_TOKEN",
                "AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN",
                "AOA_STACKOVERFLOW_CONNECTOR_MCP_READ_BEARER_TOKEN",
                "AOA_STATS_MCP_READ_BEARER_TOKEN",
                "AOA_TELEGRAM_CONNECTOR_MCP_READ_BEARER_TOKEN",
                "AOA_XDA_CONNECTOR_MCP_READ_BEARER_TOKEN",
                "ABYSS_MACHINE_MCP_READ_BEARER_TOKEN",
                "TOS_CORPUS_MCP_READ_BEARER_TOKEN",
                "ABYSS_STACK_MCP_READ_BEARER_TOKEN",
            ):
                env.pop(environment_name, None)

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
                capture_token.read_text(encoding="utf-8").splitlines(),
                owner_tokens,
            )
            self.assertEqual(
                capture_args.read_text(encoding="utf-8").splitlines(),
                ["--enable", "mcp_2026_07_28", "resume", "test-thread"],
            )
            self.assertNotIn(MCP_HTTP_AUTH_TOKEN, result.stdout + result.stderr)

            env["AOA_MEMO_MCP_READ_BEARER_TOKEN"] = "different-" + ("b" * 54)
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

    def test_mcp_http_codex_client_requests_recovery_without_blocking_exec(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "stack"
            secret_root = stack_root / "Secrets" / "Configs"
            secret_root.mkdir(parents=True)
            for index, name in enumerate(CODEX_MCP_READ_CREDENTIAL_NAMES):
                credential = secret_root / name
                credential.write_text(
                    f"readiness-owner-{index}-" + (chr(ord("b") + index) * 48) + "\n",
                    encoding="utf-8",
                )
                credential.chmod(0o600)

            fake_bin = root / "bin"
            fake_bin.mkdir()
            ready_marker = root / "ready"
            systemctl_log = root / "systemctl.log"
            fake_systemctl = fake_bin / "systemctl"
            fake_systemctl.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$*\" == --user\\ is-active\\ --quiet* ]]; then\n"
                "  [[ -f \"$READINESS_MARKER\" ]]\n"
                "  exit\n"
                "fi\n"
                "if [[ \"$*\" == \"--user start --no-block abyss-mcp-modern-admission-refresh.service\" ]]; then\n"
                "  printf '%s\\n' \"$*\" >> \"$SYSTEMCTL_LOG\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 2\n",
                encoding="utf-8",
            )
            fake_systemctl.chmod(0o755)
            fake_ss = fake_bin / "ss"
            fake_ss.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "[[ -f \"$READINESS_MARKER\" ]]\n"
                "for port in 5420 5421 5422 5423 5424 5425 5426 5427 5428 5430 5431; do\n"
                "  printf 'LISTEN 0 128 127.0.0.1:%s 0.0.0.0:*\\n' \"$port\"\n"
                "done\n",
                encoding="utf-8",
            )
            fake_ss.chmod(0o755)
            executed = root / "executed"
            fake_codex = root / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env bash\n"
                ": > \"$CODEX_EXECUTED\"\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CODEX_EXECUTABLE": str(fake_codex),
                    "CODEX_EXECUTED": str(executed),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "READINESS_MARKER": str(ready_marker),
                    "SYSTEMCTL_LOG": str(systemctl_log),
                }
            )
            for environment_name in (
                *(auth["env"] for auth in ORGAN_MCP_READ_AUTH.values()),
                "ABYSS_STACK_MCP_READ_BEARER_TOKEN",
                "AOA_MCP_READINESS_SKIP",
            ):
                env.pop(environment_name, None)

            for args in (
                ("-C", str(root), "mcp", "list"),
                ("-c", 'model="test"', "--version"),
            ):
                metadata = subprocess.run(
                    [str(MCP_HTTP_CODEX_CLIENT), *args],
                    cwd=REPO_ROOT,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(metadata.returncode, 0, metadata.stderr)
                self.assertFalse(ready_marker.exists())
                self.assertFalse(systemctl_log.exists())

            first = subprocess.run(
                [str(MCP_HTTP_CODEX_CLIENT), "exec", "--", "--help"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue(executed.exists())
            self.assertIn(
                "OS Abyss MCP: read fleet is unavailable; background recovery requested",
                first.stderr,
            )
            self.assertIn("Starting Codex without blocking", first.stderr)
            self.assertEqual(
                systemctl_log.read_text(encoding="utf-8").splitlines(),
                ["--user start --no-block abyss-mcp-modern-admission-refresh.service"],
            )

            second = subprocess.run(
                [str(MCP_HTTP_CODEX_CLIENT), "exec", "health"],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("Starting Codex without blocking", second.stderr)
            self.assertEqual(
                systemctl_log.read_text(encoding="utf-8").splitlines(),
                [
                    "--user start --no-block abyss-mcp-modern-admission-refresh.service",
                    "--user start --no-block abyss-mcp-modern-admission-refresh.service",
                ],
            )

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
            stack_read_credential = credential.parent / "abyss-stack-mcp-read-bearer-token"
            stack_read_credential.write_text(f"{'s' * 64}\n", encoding="utf-8")
            stack_read_credential.chmod(0o600)
            home = root / "home"
            home.mkdir()
            zshrc = home / ".zshrc"
            zshrc.write_text("export KEEP_EXISTING=1\n", encoding="utf-8")
            zshrc.chmod(0o640)
            fake_codex = root / "codex"
            capture_token = root / "captured-token"
            fake_codex.write_text(
                "#!/usr/bin/env bash\n"
                'printf \'%s\' "$ABYSS_STACK_MCP_READ_BEARER_TOKEN" > "$CAPTURE_TOKEN"\n',
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            env = mcp_environment()
            env.update(
                {
                    "AOA_STACK_ROOT": str(stack_root),
                    "AOA_CONFIGS_ROOT": str(configs_root),
                    "HOME": str(home),
                    "AOA_CODEX_EXECUTABLE": str(fake_codex),
                    "AOA_MCP_READINESS_SKIP": "1",
                    "CAPTURE_TOKEN": str(capture_token),
                }
            )
            env.pop("ZDOTDIR", None)
            for environment_name in (
                "AOA_MCP_HTTP_BEARER_TOKEN",
                *(auth["env"] for auth in ORGAN_MCP_READ_AUTH.values()),
                "AOA_MEMO_MCP_CANDIDATE_BEARER_TOKEN",
                "AOA_EVALS_MCP_CANDIDATE_BEARER_TOKEN",
                "ABYSS_STACK_MCP_READ_BEARER_TOKEN",
            ):
                env.pop(environment_name, None)

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
                    capture_token.read_text(encoding="utf-8"), "s" * 64
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
        organ_read_template = ORGAN_MCP_READ_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("RefuseManualStart=yes", template)
        self.assertIn("RefuseManualStop=yes", template)
        self.assertIn("ExecStart=/usr/bin/false", template)
        self.assertNotIn("AOA_MCP_TRANSPORT", template)
        self.assertNotIn("LoadCredential", template)
        self.assertNotIn("/usr/bin/env python3", template)
        self.assertNotIn("[Install]", template)

        self.assertIn(
            "LoadCredential=%i-mcp-read-bearer-token:"
            "/srv/AbyssOS/abyss-stack/Secrets/Configs/"
            "%i-mcp-read-bearer-token",
            organ_read_template,
        )
        self.assertIn(
            "Environment=AOA_MCP_POLICY_FAMILY=read",
            organ_read_template,
        )
        self.assertIn("ProtectSystem=strict", organ_read_template)
        self.assertIn("ProtectHome=read-only", organ_read_template)
        self.assertIn("IPAddressDeny=any", organ_read_template)
        self.assertIn("IPAddressAllow=localhost", organ_read_template)
        self.assertNotIn("ReadWritePaths=", organ_read_template)
        self.assertIn(" -m abyss_stack_mcp.preflight ", organ_read_template)
        self.assertIn(
            "ExecStart=/usr/bin/flock --shared --no-fork "
            "/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/"
            ".runtime-provision.lock "
            "/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/venv/bin/python "
            "-I -B -m abyss_stack_mcp.process_launcher --executable "
            "/srv/AbyssOS/.codex/bin/%i-mcp-server.py",
            organ_read_template,
        )
        self.assertNotIn(
            "Environment=AOA_MCP_HTTP_BEARER_TOKEN",
            organ_read_template,
        )
        self.assertNotIn(str(REPO_ROOT), organ_read_template)

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
        self.assertIn("aoa-organ-mcp-read@.service", managed_units)
        self.assertIn("aoa-organ-mcp-read-bootstrap@.service", managed_units)
        self.assertIn("aoa-memo-mcp-candidate.service", managed_units)
        self.assertIn("aoa-evals-mcp-candidate.service", managed_units)
        self.assertIn("aoa-mcp-http.service", managed_units)
        self.assertIn("abyss-stack-mcp-read-bootstrap.service", managed_units)
        self.assertIn("abyss-stack-mcp-observation.service", managed_units)
        self.assertIn("abyss-stack-mcp-observation.timer", managed_units)
        self.assertIn("abyss-stack-mcp-runtime-repair.service", managed_units)

        memo_candidate = MEMO_MCP_CANDIDATE_UNIT.read_text(encoding="utf-8")
        evals_candidate = EVALS_MCP_CANDIDATE_UNIT.read_text(encoding="utf-8")
        self.assertIn("Environment=AOA_MCP_PORT=5434", memo_candidate)
        self.assertIn("Environment=AOA_MCP_PORT=5435", evals_candidate)
        self.assertIn(
            "LoadCredential=aoa-memo-mcp-candidate-bearer-token:",
            memo_candidate,
        )
        self.assertIn(
            "LoadCredential=aoa-evals-mcp-candidate-bearer-token:",
            evals_candidate,
        )
        for unit in (memo_candidate, evals_candidate):
            self.assertIn(
                "Environment=AOA_MCP_POLICY_FAMILY=candidate",
                unit,
            )
            self.assertIn("ProtectSystem=strict", unit)
            self.assertIn("ProtectHome=read-only", unit)
            self.assertIn("IPAddressDeny=any", unit)
            self.assertIn("IPAddressAllow=localhost", unit)
            self.assertNotIn("ReadWritePaths=/srv/AbyssOS\n", unit)
            self.assertNotIn("abyss_stack_mcp.preflight", unit)
            self.assertNotIn("managed-contours.json", unit)
        self.assertIn(
            "ReadWritePaths=-/srv/AbyssOS/aoa-evals/memo/candidates",
            memo_candidate,
        )
        self.assertNotIn(
            "ReadWritePaths=-/srv/AbyssOS/aoa-memo/memo/objects",
            memo_candidate,
        )
        self.assertIn(
            "ReadWritePaths=-/srv/AbyssOS/aoa-memo/evals/intake",
            evals_candidate,
        )
        self.assertNotIn("evals/suites/*.suite.json", evals_candidate)

    def test_every_direct_shared_venv_consumer_is_swap_serialized(self) -> None:
        runtime_lock = (
            "/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/"
            ".runtime-provision.lock"
        )
        operation_lock = (
            "/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/"
            ".runtime-operation.lock"
        )
        direct_consumers: list[tuple[Path, str]] = []
        for unit_path in sorted((REPO_ROOT / "systemd" / "user").glob("*.service")):
            for line in unit_path.read_text(encoding="utf-8").splitlines():
                if line.startswith(("ExecStart=", "ExecCondition=")) and (
                    "/Services/abyss-stack-mcp/venv/bin/python" in line
                ) and " -I -B -m " in line:
                    direct_consumers.append((unit_path, line))
                    self.assertIn(runtime_lock, line, unit_path.name)

        self.assertGreaterEqual(len(direct_consumers), 8)
        for unit_path in (
            STACK_MCP_OBSERVATION_UNIT,
            MCP_ADMISSION_KEEPER_UNIT,
            MCP_PREFLIGHT_SWEEP_UNIT,
            MEMO_MCP_CANDIDATE_UNIT,
            EVALS_MCP_CANDIDATE_UNIT,
        ):
            unit_text = unit_path.read_text(encoding="utf-8")
            self.assertIn(
                f"ConditionPathExists={operation_lock}",
                unit_text,
                unit_path.name,
            )
            self.assertIn(
                f"ConditionPathExists={runtime_lock}",
                unit_text,
                unit_path.name,
            )
            exec_start = next(
                line
                for line in unit_text.splitlines()
                if line.startswith("ExecStart=")
            )
            self.assertIn(operation_lock, exec_start, unit_path.name)
            self.assertLess(
                exec_start.index(operation_lock),
                exec_start.index(runtime_lock),
            )

        admission_script = MCP_MODERN_ADMISSION_REFRESH_SCRIPT.read_text(
            encoding="utf-8"
        )
        ensure_index = admission_script.index("ensure_stack_runtime_ready\n")
        lock_index = admission_script.index(
            "lock_stack_runtime_consumers\n",
            ensure_index,
        )
        first_post_lock_venv_use = admission_script.index(
            'now_epoch=$(date -u +%s)',
            lock_index,
        )
        self.assertLess(ensure_index, lock_index)
        self.assertLess(lock_index, first_post_lock_venv_use)

    def test_mcp_read_bootstrap_units_are_manual_bounded_and_disjoint(self) -> None:
        organ_production = ORGAN_MCP_READ_TEMPLATE.read_text(encoding="utf-8")
        organ_bootstrap = ORGAN_MCP_READ_BOOTSTRAP_TEMPLATE.read_text(encoding="utf-8")
        stack_production = STACK_MCP_READ_UNIT.read_text(encoding="utf-8")
        stack_bootstrap = STACK_MCP_READ_BOOTSTRAP_UNIT.read_text(encoding="utf-8")

        self.assertIn(
            "Conflicts=aoa-organ-mcp-read-bootstrap@%i.service",
            organ_production,
        )
        self.assertIn(
            "Conflicts=aoa-organ-mcp-read@%i.service",
            organ_bootstrap,
        )
        self.assertIn(
            "Conflicts=abyss-stack-mcp-read-bootstrap.service",
            stack_production,
        )
        self.assertIn(
            "Conflicts=abyss-stack-mcp-read.service",
            stack_bootstrap,
        )

        for production, bootstrap in (
            (organ_production, organ_bootstrap),
            (stack_production, stack_bootstrap),
        ):
            production_lines = production.splitlines()
            bootstrap_lines = bootstrap.splitlines()
            self.assertEqual(
                [line for line in bootstrap_lines if line.startswith("ExecStart=")],
                [line for line in production_lines if line.startswith("ExecStart=")],
            )
            self.assertEqual(
                [
                    line
                    for line in bootstrap_lines
                    if line.startswith("LoadCredential=")
                ],
                [
                    line
                    for line in production_lines
                    if line.startswith("LoadCredential=")
                ],
            )
            self.assertIn("Restart=no", bootstrap_lines)
            self.assertIn("RuntimeMaxSec=30min", bootstrap_lines)
            self.assertNotIn("[Install]", bootstrap_lines)
            self.assertFalse(
                any(line.startswith("WantedBy=") for line in bootstrap_lines)
            )
            self.assertNotIn("abyss_stack_mcp.preflight", bootstrap)
            self.assertNotIn("managed-contours.json", bootstrap)
            self.assertNotIn("organ-registry.v2.source.json", bootstrap)

        self.assertIn("ProtectSystem=strict", organ_bootstrap)
        self.assertIn("ProtectHome=read-only", organ_bootstrap)
        self.assertNotIn("ReadWritePaths=", organ_bootstrap)
        self.assertIn("ProtectSystem=strict", stack_bootstrap)
        self.assertIn("ProtectHome=read-only", stack_bootstrap)
        self.assertIn("IPAddressDeny=any", stack_bootstrap)
        self.assertIn("IPAddressAllow=localhost", stack_bootstrap)

    def test_modern_mcp_expired_recovery_is_exact_two_phase_and_fail_closed(
        self,
    ) -> None:
        script = MCP_MODERN_ADMISSION_REFRESH_SCRIPT.read_text(encoding="utf-8")
        unit = MCP_MODERN_ADMISSION_REFRESH_UNIT.read_text(encoding="utf-8")
        timer = MCP_MODERN_ADMISSION_REFRESH_TIMER.read_text(encoding="utf-8")
        keeper = MCP_ADMISSION_KEEPER_UNIT.read_text(encoding="utf-8")
        preflight = MCP_PREFLIGHT_SWEEP_UNIT.read_text(encoding="utf-8")

        self.assertIn(
            'REBASE_DECISION_REF="owner://abyss-stack/decision/ABYSS-STACK-D-0109"',
            script,
        )
        self.assertIn("registry-rebase-expired-v2", script)
        self.assertIn("organ-registry.v2.expired-predecessor.json", script)
        self.assertIn("predecessor_digest=$(sha256sum", script)
        self.assertIn("live_digest=$(sha256sum", script)
        self.assertIn("trap cleanup_recovery EXIT", script)
        self.assertIn(
            'CANARY_WORKERS="${ABYSS_MCP_CANARY_WORKERS:-3}"', script
        )
        self.assertIn("CANARY_WORKERS < 1", script)
        self.assertIn("CANARY_WORKERS > ${#organs[@]}", script)
        self.assertIn("capture_canary_pair", script)
        self.assertIn("setsid --wait bash -euo pipefail -c", script)
        self.assertIn('kill -TERM -- "-${pid}"', script)
        self.assertIn("canary_worker_pids+=(\"$!\")", script)
        self.assertIn("wait -n -p completed_pid", script)
        self.assertIn("cleanup_canary_workers", script)
        self.assertIn("--process-unit \"$process_unit\"", script)
        self.assertIn("capture_canary_family", script)
        self.assertIn("    bootstrap \\", script)
        self.assertIn("publish_admission \"$RUN/bootstrap-current\"", script)
        self.assertIn("build_preflight bootstrap", script)
        self.assertIn(".preflight.eligible_count == 11", script)
        self.assertIn(".preflight.blocked_count == 0", script)
        self.assertIn("catalog_matches_current_canaries", script)
        self.assertIn(".canary_receipt_id == $receipt_id", script)
        self.assertIn(".canary_observed_at == $observed_at", script)
        self.assertIn("production_admission_reusable=0", script)
        self.assertIn(
            'if [[ "$production_admission_reusable" -eq 1 \\\n'
            '      && "$active_unit_count" -eq 11 ]]; then',
            script,
        )
        self.assertIn(
            'if [[ "$production_admission_reusable" -eq 1 ]]; then\n'
            '    systemctl --user reset-failed "${production_units[@]}"\n'
            "  else\n"
            '    systemctl --user reset-failed "${bootstrap_units[@]}"',
            script,
        )
        self.assertNotIn(
            'if [[ "$minimum_expiry" -gt "$now_epoch" '
            '&& "$registry_expiry" -gt "$now_epoch" ]]; then',
            script,
        )
        self.assertIn("systemctl --user stop \"${bootstrap_units[@]}\"", script)
        self.assertIn("systemctl --user start \"${production_units[@]}\"", script)
        self.assertIn("  production \\", script)
        self.assertIn("build_preflight production", script)
        self.assertIn("report-production.json", script)
        self.assertIn('systemctl --user reset-failed "${production_units[@]}"', script)
        self.assertNotIn(
            "modern MCP production recovery refused while admission is still current",
            script,
        )
        self.assertNotIn("mcp-candidate.service", script)
        self.assertNotIn("mcp-internal-effect.service", script)
        self.assertIn("TimeoutStartSec=20min", unit)
        self.assertNotIn(
            "ConditionPathExists=/srv/AbyssOS/abyss-stack/Services/"
            "abyss-stack-mcp/venv",
            unit,
        )
        self.assertIn(
            "ConditionPathExists=/srv/AbyssOS/abyss-stack/Configs/"
            "mcp/services/abyss-stack-mcp/requirements.lock",
            unit,
        )
        self.assertIn("OnBootSec=1s", timer)
        self.assertIn("OnUnitActiveSec=5min", timer)
        self.assertIn("ensure_stack_runtime_ready", script)
        self.assertIn(
            'RUNTIME_REPAIR_SERVICE="abyss-stack-mcp-runtime-repair.service"',
            script,
        )
        self.assertIn(
            'systemctl --user start "$RUNTIME_REPAIR_SERVICE"',
            script,
        )
        self.assertIn('AUTO_REPAIR_MARKER="$STACK/Secrets/Configs/', script)
        self.assertIn("automatic runtime repair is not explicitly enabled", script)
        self.assertIn(
            'systemctl --user reset-failed "$RUNTIME_REPAIR_SERVICE" \\\n'
            "    >/dev/null 2>&1 || true",
            script,
        )
        repair_start = script.index(
            'systemctl --user start "$RUNTIME_REPAIR_SERVICE"'
        )
        repair_eligibility = script.rindex(
            '"$INSTALL_SYSTEMD" '
            "--verify-abyss-stack-mcp-repair-eligibility",
            0,
            repair_start,
        )
        repair_reset = script.rindex(
            'systemctl --user reset-failed "$RUNTIME_REPAIR_SERVICE"',
            0,
            repair_start,
        )
        self.assertNotIn(
            'systemctl --user stop "${bootstrap_units[@]}" '
            '"${production_units[@]}"',
            script[repair_eligibility:repair_start],
        )
        self.assertLess(repair_reset, repair_start)
        self.assertIn("After=abyss-mcp-modern-admission-refresh.service", keeper)
        self.assertIn("StartLimitIntervalSec=0", keeper)
        self.assertIn(
            "After=abyss-mcp-modern-admission-refresh.service "
            "abyss-mcp-admission-keeper.service",
            preflight,
        )
        self.assertIn("StartLimitIntervalSec=0", preflight)

        cleanup_start = script.index("cleanup_recovery()")
        cleanup_end = script.index("trap cleanup_recovery EXIT")
        cleanup = script[cleanup_start:cleanup_end]
        self.assertIn('if [[ "$production_handoff_started" -eq 1 ]]', cleanup)
        self.assertIn('systemctl --user stop "${production_units[@]}"', cleanup)

        handoff_start = script.index("production_handoff_started=1")
        production_start = script.index(
            'systemctl --user start "${production_units[@]}"', handoff_start
        )
        final_publication = script.index(
            'publish_admission "$RUN/production-current"', production_start
        )
        production_catalog = script.index(
            "build_preflight production", final_publication
        )
        registry_validation = script.index(
            '"$VENV/aoa" organs registry-v2-validate "$REGISTRY"',
            production_catalog,
        )
        handoff_complete = script.index(
            "production_handoff_started=0", registry_validation
        )
        self.assertLess(handoff_start, production_start)
        self.assertLess(production_start, final_publication)
        self.assertLess(final_publication, production_catalog)
        self.assertLess(production_catalog, registry_validation)
        self.assertLess(registry_validation, handoff_complete)

        repair_unit = STACK_MCP_RUNTIME_REPAIR_UNIT.read_text(encoding="utf-8")
        self.assertIn("--repair-abyss-stack-mcp-runtime", repair_unit)
        self.assertIn(
            "ConditionPathExists=/srv/AbyssOS/abyss-stack/Secrets/Configs/"
            "abyss-stack-mcp-runtime-auto-repair.enabled",
            repair_unit,
        )
        self.assertIn("PIP_NO_CACHE_DIR=1", repair_unit)
        self.assertIn("ProtectSystem=strict", repair_unit)
        self.assertIn(
            "ReadWritePaths=/srv/AbyssOS/abyss-stack/Services "
            "/srv/AbyssOS/abyss-stack/Logs/mcp",
            repair_unit,
        )
        self.assertNotIn("[Install]", repair_unit)

    def test_stack_mcp_units_keep_all_contours_disjoint(self) -> None:
        read_unit = STACK_MCP_READ_UNIT.read_text(encoding="utf-8")
        candidate_unit = STACK_MCP_CANDIDATE_UNIT.read_text(encoding="utf-8")
        effect_unit = STACK_MCP_INTERNAL_EFFECT_UNIT.read_text(encoding="utf-8")
        observation_path = (
            "Environment=ABYSS_STACK_MCP_OBSERVATION_PATH="
            "/srv/AbyssOS/abyss-stack/Logs/mcp/observations/current.json"
        )
        deployed_entrypoint_prefix = (
            "ExecStart=/usr/bin/flock --shared --no-fork "
            "/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/"
            ".source-projection.lock /usr/bin/flock --shared --no-fork "
            "/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/"
            ".runtime-provision.lock /usr/bin/env "
            "/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-install-systemd "
            "--launch-verified-abyss-stack-mcp"
        )
        operation_lock_prefix = (
            "ExecStart=/usr/bin/flock --shared --no-fork "
            "/srv/AbyssOS/abyss-stack/Services/abyss-stack-mcp/"
            ".runtime-operation.lock "
        )
        read_deployed_entrypoint = f"{deployed_entrypoint_prefix}=read"
        candidate_deployed_entrypoint = (
            f"{operation_lock_prefix}{deployed_entrypoint_prefix.removeprefix('ExecStart=')}"
            "=candidate"
        )
        effect_deployed_entrypoint = (
            f"{operation_lock_prefix}{deployed_entrypoint_prefix.removeprefix('ExecStart=')}"
            "=internal_effect"
        )
        runtime_condition = (
            "ConditionPathExists=/srv/AbyssOS/abyss-stack/Services/"
            "abyss-stack-mcp/venv/bin/python"
        )
        source_lock_condition = (
            "ConditionPathExists=/srv/AbyssOS/abyss-stack/Services/"
            "abyss-stack-mcp/.source-projection.lock"
        )
        runtime_lock_condition = (
            "ConditionPathExists=/srv/AbyssOS/abyss-stack/Services/"
            "abyss-stack-mcp/.runtime-provision.lock"
        )
        read_audit_path = "/srv/AbyssOS/abyss-stack/Logs/mcp/audit/policy-read.jsonl"
        candidate_audit_path = (
            "/srv/AbyssOS/abyss-stack/Logs/mcp/audit/policy-candidate.jsonl"
        )
        runtime_exec_condition = (
            "ExecCondition=/usr/bin/test -x /srv/AbyssOS/abyss-stack/Services/"
            "abyss-stack-mcp/venv/bin/python"
        )
        runtime_verifier_condition_prefix = (
            "ExecCondition=/srv/AbyssOS/abyss-stack/Configs/scripts/"
            "aoa-install-systemd --verify-abyss-stack-mcp-runtime"
        )
        read_runtime_verifier_condition = f"{runtime_verifier_condition_prefix}=read"
        candidate_runtime_verifier_condition = (
            f"{runtime_verifier_condition_prefix}=candidate"
        )
        effect_runtime_verifier_condition = (
            f"{runtime_verifier_condition_prefix}=internal_effect"
        )
        installer = INSTALL_SYSTEMD.read_text(encoding="utf-8")
        self.assertIn("aoa_launch_verified_abyss_stack_mcp()", installer)
        self.assertIn(
            '"$abyss_stack_mcp_venv/bin/python" \\\n    -I -B -m "$module"',
            installer,
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
        self.assertIn(
            "Environment=ABYSS_STACK_MCP_POLICY_FAMILY=internal_effect",
            effect_unit,
        )
        self.assertIn(observation_path, read_unit)
        self.assertIn(observation_path, candidate_unit)
        self.assertIn(observation_path, effect_unit)
        for unit in (read_unit, candidate_unit, effect_unit):
            self.assertIn(
                "ConditionPathExists=/srv/AbyssOS/abyss-stack/Logs/mcp/"
                "observations/current.json",
                unit,
            )
        self.assertIn("Environment=AOA_MCP_PORT=5431", read_unit)
        self.assertNotIn("Environment=AOA_MCP_PORT=5433", read_unit)
        self.assertIn("Environment=AOA_MCP_PORT=5433", candidate_unit)
        self.assertNotIn("Environment=AOA_MCP_PORT=5431", candidate_unit)
        self.assertIn("Environment=AOA_MCP_PORT=5439", effect_unit)
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
        self.assertIn(
            "LoadCredential=abyss-stack-mcp-internal-effect-bearer-token:",
            effect_unit,
        )
        self.assertIn("LoadCredential=abyss-stack-mcp-read-bearer-token:", effect_unit)
        self.assertNotIn("candidate-bearer-token", effect_unit)
        for unit in (candidate_unit, effect_unit):
            self.assertNotIn("abyss_stack_mcp.preflight", unit)
            self.assertNotIn("managed-contours.json", unit)
        self.assertIn(
            f"ConditionPathExists={read_audit_path}",
            read_unit,
        )
        self.assertIn(
            f"Environment=ABYSS_STACK_MCP_AUDIT_JOURNAL_PATH={read_audit_path}",
            read_unit,
        )
        self.assertIn(f"ReadWritePaths={read_audit_path}", read_unit)
        self.assertIn(
            f"InaccessiblePaths={candidate_audit_path}",
            read_unit,
        )
        self.assertNotIn(f"ReadWritePaths={candidate_audit_path}", read_unit)
        self.assertIn(
            f"ConditionPathExists={candidate_audit_path}",
            candidate_unit,
        )
        self.assertIn(
            f"Environment=ABYSS_STACK_MCP_AUDIT_JOURNAL_PATH={candidate_audit_path}",
            candidate_unit,
        )
        self.assertIn(
            f"ReadWritePaths={candidate_audit_path}",
            candidate_unit,
        )
        self.assertIn(f"InaccessiblePaths={read_audit_path}", candidate_unit)
        self.assertNotIn(f"ReadWritePaths={read_audit_path}", candidate_unit)
        self.assertIn(read_runtime_verifier_condition, read_unit)
        self.assertNotIn(candidate_runtime_verifier_condition, read_unit)
        self.assertIn(candidate_runtime_verifier_condition, candidate_unit)
        self.assertNotIn(read_runtime_verifier_condition, candidate_unit)
        self.assertIn(effect_runtime_verifier_condition, effect_unit)
        audit_verifier = installer.split(
            "aoa_verify_abyss_stack_mcp_audit_journals() {", 1
        )[1].split("\naoa_provision_abyss_stack_mcp_audit_journals() {", 1)[0]
        verifier_preamble, verifier_cases = audit_verifier.split(
            '  case "$contour" in', 1
        )
        internal_effect_case = verifier_cases.split("    internal_effect)", 1)[1].split(
            "      ;;", 1
        )[0]
        self.assertNotIn("abyss_stack_mcp_audit_root", verifier_preamble)
        self.assertNotIn("abyss_stack_mcp_audit_root", internal_effect_case)
        self.assertIn("abyss_stack_mcp_effect_root", internal_effect_case)
        self.assertIn(read_deployed_entrypoint, read_unit)
        self.assertNotIn(operation_lock_prefix, read_unit)
        self.assertNotIn(candidate_deployed_entrypoint, read_unit)
        self.assertIn(candidate_deployed_entrypoint, candidate_unit)
        self.assertNotIn(read_deployed_entrypoint, candidate_unit)
        self.assertIn(effect_deployed_entrypoint, effect_unit)
        for unit in (read_unit, candidate_unit):
            self.assertIn(
                "Environment=ABYSS_STACK_MCP_REQUIRE_AUDIT_JOURNAL=1",
                unit,
            )
        for unit in (read_unit, candidate_unit, effect_unit):
            self.assertIn(
                "Environment=ABYSS_STACK_MCP_REQUIRE_AUTH_MANIFEST=1",
                unit,
            )
            self.assertIn(
                "LoadCredential=abyss-stack-mcp-auth-manifest.json:"
                "/srv/AbyssOS/abyss-stack/Secrets/Configs/"
                "abyss-stack-mcp-auth-manifest.json",
                unit,
            )
            self.assertIn("Environment=AOA_MCP_HOST=127.0.0.1", unit)
            self.assertIn("Environment=PYTHONHOME=", unit)
            self.assertIn("Environment=PYTHONPATH=", unit)
            self.assertIn(runtime_condition, unit)
            self.assertIn(source_lock_condition, unit)
            self.assertIn(runtime_lock_condition, unit)
            self.assertIn(runtime_exec_condition, unit)
            self.assertIn("ProtectSystem=strict", unit)
            self.assertIn("ProtectHome=read-only", unit)
            self.assertIn("IPAddressDeny=any", unit)
            self.assertIn("IPAddressAllow=localhost", unit)
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
        self.assertIn(STACK_MCP_INTERNAL_EFFECT_UNIT.name, managed_units)

    def test_stack_mcp_observation_producer_is_bounded_and_separately_timed(
        self,
    ) -> None:
        unit = STACK_MCP_OBSERVATION_UNIT.read_text(encoding="utf-8")
        timer = STACK_MCP_OBSERVATION_TIMER.read_text(encoding="utf-8")

        self.assertIn("Type=oneshot", unit)
        self.assertIn("-m abyss_stack_mcp.observation", unit)
        self.assertIn(
            "--deployment-manifest "
            "/srv/AbyssOS/abyss-stack/Logs/mcp/deployments/latest.json",
            unit,
        )
        self.assertIn(
            "--registry /srv/AbyssOS/.aoa/organ-access/organ-registry.v2.source.json",
            unit,
        )
        self.assertIn(
            "--output /srv/AbyssOS/abyss-stack/Logs/mcp/observations/current.json",
            unit,
        )
        self.assertIn(
            "ReadWritePaths=/srv/AbyssOS/abyss-stack/Logs/mcp/observations",
            unit,
        )
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("ProtectHome=read-only", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", unit)
        self.assertNotIn("LoadCredential=", unit)
        self.assertNotIn("AF_INET", unit)
        self.assertNotIn(str(REPO_ROOT), unit)

        self.assertIn("OnUnitActiveSec=2min", timer)
        self.assertIn("Persistent=false", timer)
        self.assertIn("Unit=abyss-stack-mcp-observation.service", timer)

    def test_mcp_admission_keeper_consumes_the_provisioned_private_inbox(
        self,
    ) -> None:
        unit = MCP_ADMISSION_KEEPER_UNIT.read_text(encoding="utf-8")
        inbox = "/srv/AbyssOS/abyss-stack/Logs/mcp/admission/keeper-inbox"

        self.assertIn(f"ConditionPathIsDirectory={inbox}", unit)
        self.assertIn(f"--keeper-inbox-root {inbox}", unit)
        self.assertIn(
            "ReadWritePaths=/srv/AbyssOS/abyss-stack/Logs/mcp/admission",
            unit,
        )
        self.assertIn("ProtectSystem=strict", unit)

    def test_mcp_admission_keeper_watches_each_consumed_contour_inbox(self) -> None:
        path_unit = MCP_ADMISSION_KEEPER_PATH.read_text(encoding="utf-8")
        targets = json.loads(STACK_MCP_RUNTIME_TARGETS.read_text(encoding="utf-8"))
        inbox = "/srv/AbyssOS/abyss-stack/Logs/mcp/admission/keeper-inbox"
        expected = {
            f"PathChanged={inbox}/{target['organ_id']}/{target['policy_family']}"
            for target in targets["targets"]
        }
        observed = {
            line
            for line in path_unit.splitlines()
            if line.startswith(f"PathChanged={inbox}/")
        }

        self.assertEqual(expected, observed)

    def test_protocol_watcher_is_removable_private_and_never_a_production_lifecycle_unit(
        self,
    ) -> None:
        unit = MCP_PROTOCOL_WATCH_UNIT.read_text(encoding="utf-8")
        path = MCP_PROTOCOL_WATCH_PATH.read_text(encoding="utf-8")
        timer = MCP_PROTOCOL_WATCH_TIMER.read_text(encoding="utf-8")

        self.assertIn("Type=oneshot", unit)
        self.assertIn("scripts/protocol_watcher.py", unit)
        self.assertIn("--execute", unit)
        self.assertIn(
            "--state-root /srv/AbyssOS/abyss-stack/Logs/mcp/protocol-watch",
            unit,
        )
        self.assertIn(
            "--runtime-config /srv/AbyssOS/abyss-stack/Secrets/Configs/"
            "mcp-protocol-watch-runtime.json",
            unit,
        )
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("ProtectHome=read-only", unit)
        self.assertIn(
            "ReadWritePaths=/srv/AbyssOS/abyss-stack/Logs/mcp/protocol-watch",
            unit,
        )
        self.assertNotIn("systemctl", unit)
        self.assertNotIn("LoadCredential=", unit)
        self.assertIn("PathChanged=%h/.local/bin/codex", path)
        self.assertIn("OnUnitActiveSec=1h", timer)
        self.assertIn("Persistent=false", timer)

        managed_units = {
            line.split("#", 1)[0].strip()
            for line in MANAGED_USER_UNITS.read_text(encoding="utf-8").splitlines()
            if line.split("#", 1)[0].strip()
        }
        self.assertTrue(
            {
                MCP_PROTOCOL_WATCH_UNIT.name,
                MCP_PROTOCOL_WATCH_PATH.name,
                MCP_PROTOCOL_WATCH_TIMER.name,
            }.issubset(managed_units)
        )


class McpLoopbackLifecycleTests(unittest.TestCase):
    def test_release_dependencies_retain_the_tested_mcp_auth_api(self) -> None:
        requirements = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertIn("mcp==2.0.0", requirements.splitlines())

    def test_all_standalone_packages_require_the_tested_mcp_auth_api(self) -> None:
        for directory, _ in MCP_SERVER_PACKAGES.values():
            with self.subTest(directory=directory):
                pyproject = (
                    REPO_ROOT / "mcp" / "services" / directory / "pyproject.toml"
                ).read_text(encoding="utf-8")
                self.assertIn('"mcp==2.0.0",', pyproject)

    def test_generated_http_auth_helpers_are_current(self) -> None:
        result = subprocess.run(
            [sys.executable, str(MCP_HTTP_AUTH_BUILDER), "--check"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generated_modern_runtime_helpers_are_current(self) -> None:
        result = subprocess.run(
            [sys.executable, str(MCP_MODERN_RUNTIME_BUILDER), "--check"],
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
                token_environment = mcp_server_token_environment(package)
                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        **{token_environment: MCP_HTTP_AUTH_TOKEN},
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
                        **{token_environment: MCP_HTTP_AUTH_TOKEN},
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
                        **{token_environment: MCP_HTTP_AUTH_TOKEN},
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
                if package == "aoa_decisions_mcp":
                    run_server.assert_called_once_with(built_server, contour="read")
                else:
                    run_server.assert_called_once_with(built_server)

        self.assertEqual(len(ports), len(MCP_SERVER_PACKAGES))

    def test_all_http_servers_require_and_verify_bearer_auth(self) -> None:
        for package, (directory, expected_port) in MCP_SERVER_PACKAGES.items():
            with self.subTest(package=package):
                module = import_mcp_server(package, directory)
                token_environment = mcp_server_token_environment(package)
                with mock.patch.dict(
                    os.environ,
                    mcp_environment(AOA_MCP_TRANSPORT="streamable-http"),
                    clear=True,
                ):
                    with self.assertRaisesRegex(SystemExit, "bearer authentication"):
                        mcp_server_auth_kwargs(module, package)

                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        **{token_environment: "too-short"},
                    ),
                    clear=True,
                ):
                    with self.assertRaisesRegex(
                        SystemExit, "invalid bearer credential"
                    ):
                        mcp_server_auth_kwargs(module, package)

                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        **{token_environment: MCP_HTTP_AUTH_TOKEN},
                    ),
                    clear=True,
                ):
                    kwargs = mcp_server_auth_kwargs(module, package)

                expected_auth = ORGAN_MCP_READ_AUTH.get(package)
                expected_scope = (
                    expected_auth["scope"] if expected_auth else "mcp:access"
                )
                expected_client_id = (
                    expected_auth["client_id"]
                    if expected_auth
                    else "aoa-loopback-codex"
                )
                self.assertEqual(kwargs["auth"].required_scopes, [expected_scope])
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
                self.assertEqual(access.client_id, expected_client_id)
                self.assertEqual(access.scopes, [expected_scope])

    def test_first_wave_owner_and_effect_credentials_do_not_cross_authenticate(
        self,
    ) -> None:
        packages = {
            package: import_mcp_server(package, MCP_SERVER_PACKAGES[package][0])
            for package in ORGAN_MCP_READ_AUTH
        }
        owner_env_names = {auth["env"] for auth in ORGAN_MCP_READ_AUTH.values()}
        for package, module in packages.items():
            correct_env = ORGAN_MCP_READ_AUTH[package]["env"]
            wrong_env = next(name for name in owner_env_names if name != correct_env)
            with self.subTest(package=package, posture="wrong-owner"):
                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        **{wrong_env: MCP_HTTP_AUTH_TOKEN},
                    ),
                    clear=True,
                ):
                    with self.assertRaisesRegex(
                        SystemExit,
                        "bearer authentication",
                    ):
                        mcp_server_auth_kwargs(module, package)

        decisions = packages["aoa_decisions_mcp"]
        with mock.patch.dict(
            os.environ,
            mcp_environment(
                AOA_MCP_TRANSPORT="streamable-http",
                AOA_DECISIONS_MCP_READ_BEARER_TOKEN=MCP_HTTP_AUTH_TOKEN,
            ),
            clear=True,
        ):
            with self.assertRaisesRegex(SystemExit, "bearer authentication"):
                decisions._contour_http_auth_kwargs("internal_effect")

        with mock.patch.dict(
            os.environ,
            mcp_environment(
                AOA_MCP_TRANSPORT="streamable-http",
                AOA_DECISIONS_MCP_INTERNAL_EFFECT_BEARER_TOKEN=MCP_HTTP_AUTH_TOKEN,
            ),
            clear=True,
        ):
            kwargs = decisions._contour_http_auth_kwargs("internal_effect")
        self.assertEqual(
            kwargs["auth"].required_scopes,
            ["mcp:aoa-decisions:internal-effect"],
        )
        access = asyncio.run(kwargs["token_verifier"].verify_token(MCP_HTTP_AUTH_TOKEN))
        self.assertIsNotNone(access)
        assert access is not None
        self.assertEqual(
            access.client_id,
            "aoa-loopback-codex:aoa-decisions:internal-effect",
        )

    def test_memo_and_evals_candidate_credentials_are_contour_specific(
        self,
    ) -> None:
        cases = (
            (
                "aoa_memo_mcp",
                "aoa-memo-mcp",
                "AOA_MEMO_MCP_READ_BEARER_TOKEN",
                "AOA_MEMO_MCP_CANDIDATE_BEARER_TOKEN",
                "mcp:aoa-memo:candidate",
                "aoa-loopback-codex:aoa-memo:candidate",
            ),
            (
                "aoa_evals_mcp",
                "aoa-evals-mcp",
                "AOA_EVALS_MCP_READ_BEARER_TOKEN",
                "AOA_EVALS_MCP_CANDIDATE_BEARER_TOKEN",
                "mcp:aoa-evals:candidate",
                "aoa-loopback-codex:aoa-evals:candidate",
            ),
        )
        for (
            package,
            directory,
            read_env,
            candidate_env,
            scope,
            client_id,
        ) in cases:
            module = import_mcp_server(package, directory)
            with self.subTest(package=package, posture="read-token-denied"):
                with mock.patch.dict(
                    os.environ,
                    mcp_environment(
                        AOA_MCP_TRANSPORT="streamable-http",
                        **{read_env: MCP_HTTP_AUTH_TOKEN},
                    ),
                    clear=True,
                ):
                    with self.assertRaisesRegex(
                        SystemExit,
                        "bearer authentication",
                    ):
                        module._contour_http_auth_kwargs("candidate")
            with mock.patch.dict(
                os.environ,
                mcp_environment(
                    AOA_MCP_TRANSPORT="streamable-http",
                    **{candidate_env: MCP_HTTP_AUTH_TOKEN},
                ),
                clear=True,
            ):
                kwargs = module._contour_http_auth_kwargs("candidate")
            self.assertEqual(kwargs["auth"].required_scopes, [scope])
            access = asyncio.run(
                kwargs["token_verifier"].verify_token(MCP_HTTP_AUTH_TOKEN)
            )
            self.assertIsNotNone(access)
            assert access is not None
            self.assertEqual(access.client_id, client_id)

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
            AOA_DECISIONS_MCP_READ_BEARER_TOKEN=MCP_HTTP_AUTH_TOKEN,
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
                headers={"MCP-Protocol-Version": "2026-07-28"},
            )
            with self.assertRaises(urllib.error.HTTPError) as missing_auth:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(missing_auth.exception.code, 401)

            wrong_request = urllib.request.Request(
                f"http://127.0.0.1:{port}/mcp",
                data=b"{}",
                method="POST",
                headers={
                    "Authorization": "Bearer wrong-token",
                    "MCP-Protocol-Version": "2026-07-28",
                },
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
                    "MCP-Protocol-Version": "2026-07-28",
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
                    "MCP-Protocol-Version": "2026-07-28",
                },
            )
            with self.assertRaises(urllib.error.HTTPError) as invalid_host:
                urllib.request.urlopen(invalid_host_request, timeout=2)
            self.assertEqual(invalid_host.exception.code, 421)

            async def authenticated_inventory() -> int:
                import httpx

                async with httpx.AsyncClient(
                    headers={
                        "Authorization": f"Bearer {MCP_HTTP_AUTH_TOKEN}",
                        "MCP-Protocol-Version": "2026-07-28",
                        "MCP-Method": "tools/list",
                    }
                ) as http_client:
                    response = await http_client.post(
                        f"http://127.0.0.1:{port}/mcp",
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "tools/list",
                            "params": {
                                "_meta": {
                                    "io.modelcontextprotocol/clientInfo": {
                                        "name": "abyss-stack-unit-test",
                                        "version": "1",
                                    },
                                    "io.modelcontextprotocol/clientCapabilities": {},
                                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                                }
                            },
                        },
                    )
                    response.raise_for_status()
                    return len(response.json()["result"]["tools"])

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
