"""Read-only command bridge for owner-produced XDA connector packets."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SERVICE_NAME = "aoa-xda-connector-mcp"
CONNECTOR_REPO_NAME = "aoa-xda-connector"
CONNECTOR_PACKAGE = "aoa_xda_connector"
CONNECTOR_BIN = "aoa-xda"
DEFAULT_CONNECTOR_REPO = Path("/srv/AbyssOS/connectors/aoa-xda-connector")
DEFAULT_RUN = "starter-fixture"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_QUERY_LENGTH = 500
MAX_LIMIT = 20
RUN_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")

STOP_LINES = [
    "Do not expose crawl, materialize, build-index, build-graph, reindex, or write tools.",
    "Do not call XDA internal search, login, account, conversation, reply, attach, or download routes.",
    "Do not touch the network from MCP status, query, or answer routes.",
    "Do not treat MCP packets as stronger than owner JSON packets, source URLs, and receipts.",
]

Runner = Callable[
    [Sequence[str], dict[str, str], float, Path | None],
    subprocess.CompletedProcess[str],
]


def _default_runner(
    argv: Sequence[str],
    env: dict[str, str],
    timeout: float,
    cwd: Path | None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        env=env,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _json_or_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text.strip()


def _safe_query(query: str) -> str:
    value = str(query or "").strip()
    if not value:
        raise ValueError("query must not be empty")
    if len(value) > MAX_QUERY_LENGTH:
        raise ValueError(f"query must not exceed {MAX_QUERY_LENGTH} characters")
    return value


def _safe_run(run: str | None, default: str) -> str:
    value = str(run or default).strip()
    if not RUN_RE.fullmatch(value):
        raise ValueError("run must be a short connector run token")
    return value


def _safe_limit(limit: int) -> int:
    value = int(limit)
    if value < 1:
        raise ValueError("limit must be positive")
    return min(value, MAX_LIMIT)


@dataclass(frozen=True)
class CommandOutput:
    argv: list[str]
    cwd: str | None
    returncode: int
    stdout: str
    stderr: str
    payload: Any

    @property
    def ok(self) -> bool:
        return (
            self.returncode == 0
            and isinstance(self.payload, dict)
            and self.payload.get("status") != "error"
        )


@dataclass
class AoAXDAConnectorMCPState:
    connector_repo: Path | None = None
    connector_bin: str | None = None
    data_root: Path | None = None
    cache_root: Path | None = None
    artifact_root: Path | None = None
    default_run: str = DEFAULT_RUN
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    runner: Runner = _default_runner

    @classmethod
    def discover(cls) -> "AoAXDAConnectorMCPState":
        repo = os.environ.get("AOA_XDA_CONNECTOR_REPO")
        return cls(
            connector_repo=Path(repo).expanduser() if repo else DEFAULT_CONNECTOR_REPO,
            connector_bin=os.environ.get("AOA_XDA_CONNECTOR_BIN"),
            data_root=_env_path("CONNECTOR_DATA_ROOT"),
            cache_root=_env_path("CONNECTOR_CACHE_ROOT"),
            artifact_root=_env_path("CONNECTOR_ARTIFACT_ROOT"),
            default_run=os.environ.get("AOA_XDA_CONNECTOR_RUN", DEFAULT_RUN),
            timeout=float(
                os.environ.get(
                    "AOA_XDA_CONNECTOR_MCP_TIMEOUT",
                    DEFAULT_TIMEOUT_SECONDS,
                )
            ),
        )

    def _base_argv(self) -> list[str]:
        if self.connector_bin:
            return shlex.split(self.connector_bin)
        if self.connector_repo:
            cli = self.connector_repo / "src" / CONNECTOR_PACKAGE / "cli.py"
            if cli.is_file():
                return [sys.executable, "-m", f"{CONNECTOR_PACKAGE}.cli"]
        return [CONNECTOR_BIN]

    def _cwd(self) -> Path | None:
        return self.connector_repo if self.connector_repo and self.connector_repo.is_dir() else None

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.connector_repo:
            src = self.connector_repo / "src"
            if src.is_dir():
                old = env.get("PYTHONPATH")
                env["PYTHONPATH"] = str(src) if not old else f"{src}{os.pathsep}{old}"
        for name, value in (
            ("CONNECTOR_DATA_ROOT", self.data_root),
            ("CONNECTOR_CACHE_ROOT", self.cache_root),
            ("CONNECTOR_ARTIFACT_ROOT", self.artifact_root),
        ):
            if value:
                env[name] = str(value)
        return env

    def _run(self, args: Sequence[str]) -> CommandOutput:
        argv = [*self._base_argv(), *args]
        cwd = self._cwd()
        try:
            completed = self.runner(argv, self._env(), self.timeout, cwd)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CommandOutput(
                argv=argv,
                cwd=str(cwd) if cwd else None,
                returncode=127,
                stdout="",
                stderr=str(exc),
                payload={"status": "error", "error": str(exc)},
            )
        return CommandOutput(
            argv=argv,
            cwd=str(cwd) if cwd else None,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            payload=_json_or_text(completed.stdout),
        )

    def source_route(self) -> dict[str, Any]:
        return {
            "schema": "aoa_xda_connector_mcp_source_route_v1",
            "service_name": SERVICE_NAME,
            "connector_repo": str(self.connector_repo) if self.connector_repo else None,
            "read_only": True,
            "network_touched": False,
            "wrapped_commands": [
                "aoa-xda doctor",
                "aoa-xda storage status",
                "aoa-xda policy check",
                "aoa-xda query-graph",
                "aoa-xda answer",
            ],
            "withheld_owner_surface": [
                "query-hybrid: owner CLI command is not implemented",
            ],
            "storage_roots": {
                "data": str(self.data_root) if self.data_root else None,
                "cache": str(self.cache_root) if self.cache_root else None,
                "artifact": str(self.artifact_root) if self.artifact_root else None,
            },
            "owner_split": {
                "source_owner": CONNECTOR_REPO_NAME,
                "access_owner": "abyss-stack",
            },
            "stop_lines": STOP_LINES,
        }

    def status(self) -> dict[str, Any]:
        commands = {
            "doctor": self._run(["doctor"]),
            "storage": self._run(["storage", "status"]),
            "policy": self._run(["policy", "check"]),
        }
        return {
            "schema": "aoa_xda_connector_mcp_status_v1",
            "service_name": SERVICE_NAME,
            "status": "ok" if all(item.ok for item in commands.values()) else "degraded",
            "read_only": True,
            "network_touched": False,
            "commands": {
                name: _compact_command(result) for name, result in commands.items()
            },
            "source_route": self.source_route(),
        }

    def answer(self, query: str, run: str | None = None, limit: int = 5) -> dict[str, Any]:
        return self._packet("answer", query, run, limit)

    def query_graph(
        self,
        query: str,
        run: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        return self._packet("query-graph", query, run, limit)

    def _packet(
        self,
        command: str,
        query: str,
        run: str | None,
        limit: int,
    ) -> dict[str, Any]:
        selected_query = _safe_query(query)
        selected_run = _safe_run(run, self.default_run)
        selected_limit = _safe_limit(limit)
        result = self._run(
            [
                command,
                selected_query,
                "--run",
                selected_run,
                "--limit",
                str(selected_limit),
            ]
        )
        payload = result.payload if isinstance(result.payload, dict) else {}
        boundary_errors = _boundary_errors(payload)
        packet = {
            "schema": f"aoa_xda_connector_mcp_{command.replace('-', '_')}_v1",
            "service_name": SERVICE_NAME,
            "status": "ok" if result.ok and not boundary_errors else "error",
            "query": selected_query,
            "run": selected_run,
            "limit": selected_limit,
            "source_packet_schema": payload.get("schema"),
            "source_packet": payload,
            "network_touched": payload.get("network_touched"),
            "read_only": payload.get("read_only"),
            "boundary_errors": boundary_errors,
            "command": _compact_command(result),
        }
        if command == "answer":
            for field in (
                "agent_answer",
                "evidence_chain",
                "answer_report",
                "conflict_report",
                "freshness_report",
                "applicability_report",
                "warning_report",
            ):
                packet[field] = payload.get(field)
        return packet


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else None


def _boundary_errors(payload: dict[str, Any]) -> list[str]:
    errors = []
    if payload.get("network_touched") is not False:
        errors.append("source packet did not prove network_touched=false")
    if payload.get("read_only") is not True:
        errors.append("source packet did not prove read_only=true")
    return errors


def _compact_command(result: CommandOutput) -> dict[str, Any]:
    return {
        "argv": result.argv,
        "cwd": result.cwd,
        "returncode": result.returncode,
        "ok": result.ok,
        "payload_schema": (
            result.payload.get("schema") if isinstance(result.payload, dict) else None
        ),
        "stderr": result.stderr[:1000],
    }
