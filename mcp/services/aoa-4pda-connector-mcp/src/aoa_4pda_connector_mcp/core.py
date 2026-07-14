from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SERVICE_NAME = "aoa-4pda-connector-mcp"
DEFAULT_CONNECTOR_REPO = Path("/srv/AbyssOS/connectors/aoa-4pda-connector")
DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_QUERY_LENGTH = 500
MAX_LIMIT = 20

STOP_LINES = [
    "Do not expose crawl, refresh-build, materialize, reindex, seed-edit, or write tools.",
    "Do not touch the network from status, query, or answer routes.",
    "Do not call 4PDA internal search, private/account, QMS, post, attach, download, or login routes.",
    "Do not commit corpora, raw captures, indexes, vectors, graphs, receipts, sqlite, parquet, qdrant, lancedb, or caches.",
    "Do not treat MCP packets as stronger than aoa-4pda connector JSON packets and source URLs.",
]

WRAPPED_COMMANDS = [
    "aoa-4pda doctor",
    "aoa-4pda storage status",
    "aoa-4pda ready",
    "aoa-4pda query-graph",
    "aoa-4pda query-hybrid",
    "aoa-4pda answer",
]

RUN_TOKEN_RE = __import__("re").compile(r"^[A-Za-z0-9_.:-]{1,160}$")


@dataclass(slots=True)
class CommandOutput:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: float
    cwd: str | None = None


CommandRunner = Callable[[list[str], float, Mapping[str, str], Path | None], CommandOutput]


def _default_runner(argv: list[str], timeout: float, env: Mapping[str, str], cwd: Path | None) -> CommandOutput:
    start = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=dict(env),
            cwd=str(cwd) if cwd is not None else None,
        )
        return CommandOutput(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed_ms=round((time.monotonic() - start) * 1000, 1),
            cwd=str(cwd) if cwd is not None else None,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandOutput(
            argv=argv,
            returncode=124,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=f"command timed out after {timeout}s",
            elapsed_ms=round((time.monotonic() - start) * 1000, 1),
            cwd=str(cwd) if cwd is not None else None,
        )
    except OSError as exc:
        return CommandOutput(
            argv=argv,
            returncode=127,
            stdout="",
            stderr=str(exc),
            elapsed_ms=round((time.monotonic() - start) * 1000, 1),
            cwd=str(cwd) if cwd is not None else None,
        )


def _read_json(stdout: str) -> Any:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _as_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    return Path(value).expanduser().resolve()


def _safe_query(query: str) -> str:
    value = str(query or "").strip()
    if not value:
        raise ValueError("query must not be empty")
    if len(value) > MAX_QUERY_LENGTH:
        raise ValueError(f"query is too long; keep it under {MAX_QUERY_LENGTH} characters")
    return value


def _safe_run(run: str | None, default_run: str) -> str:
    value = str(run or default_run or "latest").strip()
    if not value:
        value = "latest"
    if not RUN_TOKEN_RE.fullmatch(value):
        raise ValueError(f"run must be a short run id token, got: {value!r}")
    return value


def _safe_limit(limit: int | None) -> int:
    try:
        value = int(limit or 5)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if value <= 0:
        return 5
    return min(value, MAX_LIMIT)


def _payload_status(payload: Any) -> str | None:
    if isinstance(payload, dict):
        status = payload.get("status")
        if isinstance(status, str):
            return status
    return None


def _command_ok(result: dict[str, Any]) -> bool:
    if result.get("returncode") != 0:
        return False
    payload = result.get("payload")
    if not isinstance(payload, dict):
        return False
    return payload.get("status") != "error"


def _storage_root_payload(path: Path | None) -> str | None:
    return path.as_posix() if path is not None else None


def _compact_ready(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    keys = (
        "schema",
        "status",
        "ready",
        "run",
        "target_status",
        "counts",
        "storage_mode",
        "storage_roots",
        "network_touched",
        "next_actions",
    )
    return {key: payload.get(key) for key in keys if key in payload}


def _payload_brief(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload.get(key)
        for key in ("schema", "status", "answer_id", "packet_id", "query", "network_touched")
        if key in payload
    }


def _compact_command(result: dict[str, Any], *, ready: bool = False, include_payload: bool = True) -> dict[str, Any]:
    payload = result.get("payload")
    return {
        "ok": result.get("ok"),
        "returncode": result.get("returncode"),
        "elapsed_ms": result.get("elapsed_ms"),
        "payload_schema": result.get("payload_schema"),
        "payload_status": _payload_status(payload),
        "payload": _compact_ready(payload) if ready else (payload if include_payload else _payload_brief(payload)),
        "stderr": result.get("stderr") or "",
    }


@dataclass(slots=True)
class AoA4PDAConnectorMCPState:
    connector_repo: Path | None
    connector_bin: str | None = None
    data_root: Path | None = None
    cache_root: Path | None = None
    artifact_root: Path | None = None
    default_run: str = "latest"
    command_runner: CommandRunner = _default_runner
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def discover(
        cls,
        connector_repo: str | Path | None = None,
        connector_bin: str | None = None,
        data_root: str | Path | None = None,
        cache_root: str | Path | None = None,
        artifact_root: str | Path | None = None,
        default_run: str | None = None,
        command_runner: CommandRunner | None = None,
        timeout_seconds: float | None = None,
    ) -> "AoA4PDAConnectorMCPState":
        env = os.environ
        repo_value = connector_repo or env.get("AOA_4PDA_CONNECTOR_REPO") or DEFAULT_CONNECTOR_REPO
        return cls(
            connector_repo=_as_path(repo_value),
            connector_bin=connector_bin or env.get("AOA_4PDA_CONNECTOR_BIN") or env.get("AOA_4PDA_BIN"),
            data_root=_as_path(data_root or env.get("CONNECTOR_DATA_ROOT")),
            cache_root=_as_path(cache_root or env.get("CONNECTOR_CACHE_ROOT")),
            artifact_root=_as_path(artifact_root or env.get("CONNECTOR_ARTIFACT_ROOT")),
            default_run=str(default_run or env.get("AOA_4PDA_CONNECTOR_RUN") or "latest"),
            command_runner=command_runner or _default_runner,
            timeout_seconds=float(timeout_seconds or env.get("AOA_4PDA_CONNECTOR_MCP_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
        )

    def _repo_src(self) -> Path | None:
        if self.connector_repo is None:
            return None
        src = self.connector_repo / "src"
        package = src / "aoa_4pda_connector"
        return src if package.is_dir() else None

    def _base_argv(self) -> list[str]:
        if self.connector_bin:
            return shlex.split(self.connector_bin)
        if self._repo_src() is not None:
            return [sys.executable, "-m", "aoa_4pda_connector.cli"]
        return ["aoa-4pda"]

    def _cwd(self) -> Path | None:
        if self.connector_repo is not None and self.connector_repo.is_dir():
            return self.connector_repo
        return None

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        repo_src = self._repo_src()
        if repo_src is not None:
            previous = env.get("PYTHONPATH")
            env["PYTHONPATH"] = repo_src.as_posix() if not previous else repo_src.as_posix() + os.pathsep + previous
        if self.data_root is not None:
            env["CONNECTOR_DATA_ROOT"] = self.data_root.as_posix()
        if self.cache_root is not None:
            env["CONNECTOR_CACHE_ROOT"] = self.cache_root.as_posix()
        if self.artifact_root is not None:
            env["CONNECTOR_ARTIFACT_ROOT"] = self.artifact_root.as_posix()
        return env

    def _run_cli(self, args: list[str]) -> dict[str, Any]:
        argv = [*self._base_argv(), *args]
        output = self.command_runner(argv, self.timeout_seconds, self._env(), self._cwd())
        payload = _read_json(output.stdout)
        result = {
            "schema": "aoa_4pda_connector_mcp_command_v1",
            "ok": output.returncode == 0 and isinstance(payload, dict) and payload.get("status") != "error",
            "argv": output.argv,
            "cwd": output.cwd,
            "returncode": output.returncode,
            "elapsed_ms": output.elapsed_ms,
            "stderr": output.stderr,
            "payload_schema": payload.get("schema") if isinstance(payload, dict) else None,
            "payload": payload,
        }
        return result

    def source_route(self) -> dict[str, Any]:
        return {
            "schema": "aoa_4pda_connector_mcp_source_route_v1",
            "service_name": SERVICE_NAME,
            "connector_repo": self.connector_repo.as_posix() if self.connector_repo is not None else None,
            "connector_repo_exists": bool(self.connector_repo and self.connector_repo.is_dir()),
            "connector_command": self._base_argv(),
            "storage_roots": {
                "CONNECTOR_DATA_ROOT": _storage_root_payload(self.data_root),
                "CONNECTOR_CACHE_ROOT": _storage_root_payload(self.cache_root),
                "CONNECTOR_ARTIFACT_ROOT": _storage_root_payload(self.artifact_root),
            },
            "env_vars": [
                "AOA_4PDA_CONNECTOR_REPO",
                "AOA_4PDA_CONNECTOR_BIN",
                "AOA_4PDA_CONNECTOR_RUN",
                "CONNECTOR_DATA_ROOT",
                "CONNECTOR_CACHE_ROOT",
                "CONNECTOR_ARTIFACT_ROOT",
            ],
            "wrapped_commands": WRAPPED_COMMANDS,
            "mcp_surface": ["status", "source_route", "query_graph", "query_hybrid", "answer"],
            "read_only": True,
            "network_touched": False,
            "exposure": "stdio-default; optional loopback streamable-http",
            "owner_split": {
                "source_owner": "aoa-4pda-connector owns 4PDA policy, CLI, schemas, storage contract, answer packet semantics, and generated packet truth.",
                "runtime_owner": "abyss-stack owns the runnable MCP service package, local transport route, stack validation, and deployment posture.",
            },
            "stop_lines": STOP_LINES,
        }

    def status(self, run: str | None = None) -> dict[str, Any]:
        selected_run = _safe_run(run, self.default_run)
        doctor = self._run_cli(["doctor"])
        storage = self._run_cli(["storage", "status"])
        ready = self._run_cli(["ready", "--run", selected_run])
        return {
            "schema": "aoa_4pda_connector_mcp_status_v1",
            "service_name": SERVICE_NAME,
            "status": "ok" if _command_ok(doctor) and _command_ok(storage) else "degraded",
            "run": selected_run,
            "source_route": self.source_route(),
            "doctor": _compact_command(doctor),
            "storage": _compact_command(storage),
            "ready": _compact_command(ready, ready=True),
            "read_only": True,
            "network_touched": False,
        }

    def answer(self, query: str, run: str | None = None, limit: int | None = 5) -> dict[str, Any]:
        selected_query = _safe_query(query)
        selected_run = _safe_run(run, self.default_run)
        selected_limit = _safe_limit(limit)
        command = self._run_cli(["answer", selected_query, "--run", selected_run, "--limit", str(selected_limit)])
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        boundary_errors: list[str] = []
        if payload.get("schema") != "aoa_4pda_answer_packet_v1":
            boundary_errors.append("source packet schema is not aoa_4pda_answer_packet_v1")
        if payload.get("network_touched") is not False:
            boundary_errors.append("source answer packet did not preserve network_touched=false")
        if payload.get("read_only") is not True:
            boundary_errors.append("source answer packet did not preserve read_only=true")

        return {
            "schema": "aoa_4pda_connector_mcp_answer_v1",
            "service_name": SERVICE_NAME,
            "status": "ok" if command["ok"] and not boundary_errors else "error",
            "query": selected_query,
            "run": selected_run,
            "limit": selected_limit,
            "source_packet_schema": payload.get("schema"),
            "source_packet_id": payload.get("answer_id"),
            "agent_answer": payload.get("agent_answer", {}),
            "evidence_chain": payload.get("evidence_chain", []),
            "nuance_report": payload.get("nuance_report", {}),
            "answer_report": payload.get("answer_report", {}),
            "conflict_report": payload.get("conflict_report", {}),
            "freshness_report": payload.get("freshness_report", {}),
            "applicability_report": payload.get("applicability_report", {}),
            "warning_report": payload.get("warning_report", {}),
            "answers": payload.get("answers", []),
            "query_report": payload.get("query_report", {}),
            "policy": payload.get("policy", {}),
            "network_touched": payload.get("network_touched"),
            "boundary_errors": boundary_errors,
            "command": _compact_command(command, include_payload=False),
            "read_only": True,
            "source_read_only": payload.get("read_only"),
        }

    def query_graph(self, query: str, run: str | None = None, limit: int | None = 5) -> dict[str, Any]:
        return self._query("query-graph", query=query, run=run, limit=limit)

    def query_hybrid(self, query: str, run: str | None = None, limit: int | None = 5) -> dict[str, Any]:
        return self._query("query-hybrid", query=query, run=run, limit=limit)

    def _query(self, command_name: str, *, query: str, run: str | None, limit: int | None) -> dict[str, Any]:
        selected_query = _safe_query(query)
        selected_run = _safe_run(run, self.default_run)
        selected_limit = _safe_limit(limit)
        command = self._run_cli([command_name, selected_query, "--run", selected_run, "--limit", str(selected_limit)])
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        network_touched = payload.get("network_touched")
        boundary_errors = [] if network_touched is False else ["source query packet did not preserve network_touched=false"]
        return {
            "schema": "aoa_4pda_connector_mcp_query_v1",
            "service_name": SERVICE_NAME,
            "status": "ok" if command["ok"] and not boundary_errors else "error",
            "query_kind": command_name,
            "query": selected_query,
            "run": selected_run,
            "limit": selected_limit,
            "source_packet_schema": payload.get("schema"),
            "source_packet": payload,
            "network_touched": network_touched,
            "boundary_errors": boundary_errors,
            "command": _compact_command(command, include_payload=False),
            "read_only": True,
        }

    def read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "aoa-4pda://source-route":
            return self.source_route()
        if uri == "aoa-4pda://status":
            return self.status()
        raise KeyError(f"unknown aoa-4pda connector MCP resource URI: {uri}")

    def render_resource(self, uri: str) -> str:
        return json.dumps(self.read_resource(uri), ensure_ascii=False, indent=2, sort_keys=True)
