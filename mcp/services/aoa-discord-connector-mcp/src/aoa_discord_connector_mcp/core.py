"""Read-only MCP access plane for the Discord connector."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SERVICE_NAME = "aoa-discord-connector-mcp"
SOURCE_NAME = "discord"
SOURCE_LABEL = "Discord"
CONNECTOR_REPO_NAME = "aoa-discord-connector"
CONNECTOR_PACKAGE = "aoa_discord_connector"
CONNECTOR_BIN = "aoa-discord"
DEFAULT_CONNECTOR_REPO = Path("/srv/AbyssOS/connectors/aoa-discord-connector")
DEFAULT_RUN = "starter-fixture"
DEFAULT_TIMEOUT_SECONDS = 30.0

STOP_LINES = [
    "Do not expose crawl, materialize, build-index, build-graph, or init as MCP tools.",
    "Do not bypass connector permission reports; permission state is part of answer truth.",
    "Do not treat MCP packets as stronger than connector JSON packets and local evidence receipts.",
    "Do not write generated corpora, indexes, vectors, graphs, caches, or account/session state into abyss-stack.",
]

WRAPPED_COMMANDS = [
    "aoa-discord doctor",
    "aoa-discord storage status",
    "aoa-discord policy check",
    "aoa-discord query-graph",
    "aoa-discord answer",
]


Runner = Callable[[Sequence[str], dict[str, str], float, Path | None], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class CommandOutput:
    """Connector command result normalized for MCP packets."""

    argv: list[str]
    cwd: str | None
    returncode: int
    stdout: str
    stderr: str
    payload: Any

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not isinstance(self.payload, str)


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
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).expanduser()


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _brief_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return {
            "schema": payload.get("schema"),
            "status": payload.get("status"),
            "network_touched": payload.get("network_touched"),
            "read_only": payload.get("read_only"),
        }
    if payload:
        return {"text": str(payload)[:500]}
    return {}


def _compact_command(result: CommandOutput, *, include_payload: bool = True) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "argv": result.argv,
        "cwd": result.cwd,
        "returncode": result.returncode,
        "ok": result.ok,
        "payload_schema": result.payload.get("schema") if isinstance(result.payload, dict) else None,
        "payload_status": result.payload.get("status") if isinstance(result.payload, dict) else None,
        "network_touched": result.payload.get("network_touched") if isinstance(result.payload, dict) else None,
    }
    if include_payload:
        packet["payload"] = result.payload
    else:
        packet["payload"] = _brief_payload(result.payload)
    if result.stderr.strip():
        packet["stderr"] = result.stderr.strip()[:1000]
    return packet


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _boundary_errors(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        errors.append("connector output is not a JSON object")
        return errors
    if _as_bool(payload.get("network_touched")) is not False:
        errors.append("connector packet did not prove network_touched=false")
    if _as_bool(payload.get("read_only")) is not True:
        errors.append("connector packet did not prove read_only=true")
    policy = payload.get("policy")
    if isinstance(policy, dict) and policy.get("internal_search_used") is not False:
        errors.append("connector policy did not prove internal_search_used=false")
    return errors


def _selected_run(run: str | None, default_run: str) -> str:
    if not run or run == "latest":
        return default_run
    return run


@dataclass
class AoADiscordConnectorMCPState:
    """State and command bridge for the Discord connector MCP service."""

    connector_repo: Path | None = None
    connector_bin: str | None = None
    data_root: Path | None = None
    cache_root: Path | None = None
    artifact_root: Path | None = None
    default_run: str = DEFAULT_RUN
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    runner: Runner = _default_runner

    @classmethod
    def discover(cls) -> "AoADiscordConnectorMCPState":
        connector_repo = _env_path("AOA_DISCORD_CONNECTOR_REPO") or DEFAULT_CONNECTOR_REPO
        connector_bin = os.environ.get("AOA_DISCORD_CONNECTOR_BIN") or os.environ.get("AOA_DISCORD_BIN")
        return cls(
            connector_repo=connector_repo,
            connector_bin=connector_bin,
            data_root=_env_path("CONNECTOR_DATA_ROOT"),
            cache_root=_env_path("CONNECTOR_CACHE_ROOT"),
            artifact_root=_env_path("CONNECTOR_ARTIFACT_ROOT"),
            default_run=os.environ.get("AOA_DISCORD_CONNECTOR_RUN", DEFAULT_RUN),
            timeout=_env_float("AOA_DISCORD_CONNECTOR_MCP_TIMEOUT", DEFAULT_TIMEOUT_SECONDS),
        )

    def _base_argv(self) -> list[str]:
        if self.connector_bin:
            return shlex.split(self.connector_bin)
        if self.connector_repo:
            package = self.connector_repo / "src" / CONNECTOR_PACKAGE
            cli = package / "cli.py"
            if cli.exists():
                return [sys.executable, "-m", f"{CONNECTOR_PACKAGE}.cli"]
        return [CONNECTOR_BIN]

    def _command_cwd(self) -> Path | None:
        if self.connector_repo and self.connector_repo.exists():
            return self.connector_repo
        return None

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.connector_repo:
            src = self.connector_repo / "src"
            if src.exists():
                existing = env.get("PYTHONPATH")
                env["PYTHONPATH"] = str(src) if not existing else f"{src}{os.pathsep}{existing}"
        if self.data_root:
            env["CONNECTOR_DATA_ROOT"] = str(self.data_root)
        if self.cache_root:
            env["CONNECTOR_CACHE_ROOT"] = str(self.cache_root)
        if self.artifact_root:
            env["CONNECTOR_ARTIFACT_ROOT"] = str(self.artifact_root)
        return env

    def _run_cli(self, args: Sequence[str]) -> CommandOutput:
        argv = [*self._base_argv(), *args]
        cwd = self._command_cwd()
        try:
            completed = self.runner(argv, self._env(), self.timeout, cwd)
        except FileNotFoundError as exc:
            return CommandOutput(argv=argv, cwd=str(cwd) if cwd else None, returncode=127, stdout="", stderr=str(exc), payload={"status": "error", "error": str(exc)})
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return CommandOutput(
                argv=argv,
                cwd=str(cwd) if cwd else None,
                returncode=124,
                stdout=stdout,
                stderr=stderr or f"timeout after {self.timeout}s",
                payload={"status": "error", "error": f"timeout after {self.timeout}s"},
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
            "schema": "aoa_discord_connector_mcp_source_route_v1",
            "service_name": SERVICE_NAME,
            "source": SOURCE_NAME,
            "connector_repo_name": CONNECTOR_REPO_NAME,
            "connector_repo": str(self.connector_repo) if self.connector_repo else None,
            "connector_bin": self.connector_bin or CONNECTOR_BIN,
            "default_run": self.default_run,
            "read_only": True,
            "network_touched": False,
            "wrapped_commands": WRAPPED_COMMANDS,
            "exposed_tools": [
                "aoa_discord_connector_status",
                "aoa_discord_connector_source_route",
                "aoa_discord_connector_query_graph",
                "aoa_discord_connector_answer",
            ],
            "resources": [
                "aoa-discord://source-route",
                "aoa-discord://status",
            ],
            "permission_modes": ["bot_gateway", "bot_gateway_message_content", "data_package"],
            "stop_lines": STOP_LINES,
            "storage_roots": {
                "data": str(self.data_root) if self.data_root else None,
                "cache": str(self.cache_root) if self.cache_root else None,
                "artifact": str(self.artifact_root) if self.artifact_root else None,
            },
            "env_vars": {
                "connector_repo": "AOA_DISCORD_CONNECTOR_REPO",
                "connector_bin": "AOA_DISCORD_CONNECTOR_BIN",
                "default_run": "AOA_DISCORD_CONNECTOR_RUN",
                "timeout": "AOA_DISCORD_CONNECTOR_MCP_TIMEOUT",
                "data_root": "CONNECTOR_DATA_ROOT",
                "cache_root": "CONNECTOR_CACHE_ROOT",
                "artifact_root": "CONNECTOR_ARTIFACT_ROOT",
            },
            "owner_split": {
                "mcp_owner": f"{SERVICE_NAME} owns MCP tool shape and read-only wrapping.",
                "source_owner": f"{CONNECTOR_REPO_NAME} owns {SOURCE_LABEL} policy, schemas, storage contract, and packet semantics.",
                "runtime_owner": "Abyss host deployment owns local paths and heavy generated state.",
            },
        }

    def status(self) -> dict[str, Any]:
        doctor = self._run_cli(["doctor"])
        storage = self._run_cli(["storage", "status"])
        policy = self._run_cli(["policy", "check"])
        ok = doctor.ok and storage.ok and policy.ok
        return {
            "schema": "aoa_discord_connector_mcp_status_v1",
            "service_name": SERVICE_NAME,
            "status": "ok" if ok else "error",
            "read_only": True,
            "network_touched": False,
            "source_route": self.source_route(),
            "doctor": _compact_command(doctor, include_payload=False),
            "storage": _compact_command(storage, include_payload=False),
            "policy": _compact_command(policy, include_payload=False),
        }

    def answer(self, query: str, *, run: str | None = None, limit: int = 5) -> dict[str, Any]:
        selected_run = _selected_run(run, self.default_run)
        result = self._run_cli(["answer", query, "--run", selected_run, "--limit", str(limit)])
        payload = result.payload if isinstance(result.payload, dict) else {}
        boundary_errors = _boundary_errors(payload)
        if payload.get("schema") not in {"aoa_connector_answer_packet_v1", "aoa_discord_answer_packet_v1"}:
            boundary_errors.append("connector packet schema is not a known answer packet schema")
        return {
            "schema": "aoa_discord_connector_mcp_answer_v1",
            "service_name": SERVICE_NAME,
            "status": "ok" if result.ok and not boundary_errors else "error",
            "query": query,
            "run": selected_run,
            "limit": limit,
            "read_only": True,
            "network_touched": False,
            "source_packet_schema": payload.get("schema"),
            "source_packet_status": payload.get("status"),
            "agent_answer": payload.get("agent_answer"),
            "answers": payload.get("answers", []),
            "evidence_chain": payload.get("evidence_chain", []),
            "permission_report": payload.get("permission_report", {}),
            "answer_report": payload.get("answer_report", {}),
            "conflict_report": payload.get("conflict_report", {}),
            "freshness_report": payload.get("freshness_report", {}),
            "applicability_report": payload.get("applicability_report", {}),
            "warning_report": payload.get("warning_report", {}),
            "policy": payload.get("policy", {}),
            "command": _compact_command(result, include_payload=False),
            "boundary_errors": boundary_errors,
        }

    def query_graph(self, query: str, *, run: str | None = None, limit: int = 5) -> dict[str, Any]:
        selected_run = _selected_run(run, self.default_run)
        result = self._run_cli(["query-graph", query, "--run", selected_run, "--limit", str(limit)])
        payload = result.payload if isinstance(result.payload, dict) else {}
        boundary_errors = _boundary_errors(payload)
        return {
            "schema": "aoa_discord_connector_mcp_query_graph_v1",
            "service_name": SERVICE_NAME,
            "status": "ok" if result.ok and not boundary_errors else "error",
            "query": query,
            "run": selected_run,
            "limit": limit,
            "read_only": True,
            "network_touched": False,
            "source_packet_schema": payload.get("schema"),
            "source_packet_status": payload.get("status"),
            "results": payload.get("results", []),
            "result_count": payload.get("result_count", len(payload.get("results", [])) if isinstance(payload.get("results"), list) else None),
            "permission_report": payload.get("permission_report", {}),
            "graph_report": payload.get("graph_report", {}),
            "policy": payload.get("policy", {}),
            "command": _compact_command(result, include_payload=False),
            "boundary_errors": boundary_errors,
        }

    def read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "aoa-discord://source-route":
            return self.source_route()
        if uri == "aoa-discord://status":
            return self.status()
        raise KeyError(f"unknown aoa-discord connector MCP resource URI: {uri}")
