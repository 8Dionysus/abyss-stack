from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shlex
import sqlite3
import subprocess
import tomllib
import time
import datetime as dt
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _source_mtime_epoch(*paths: Path) -> float | None:
    mtimes = []
    for path in paths:
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes) if mtimes else None


def _core_auto_reload_enabled() -> bool:
    value = os.environ.get("AOA_SESSION_MEMORY_MCP_AUTO_RELOAD", "1").strip().casefold()
    return value not in {"0", "false", "no", "off"}


def _linux_boot_epoch(proc_root: Path = Path("/proc")) -> float | None:
    try:
        for line in (proc_root / "stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except OSError:
        return None
    return None


def _process_start_epoch(pid: int, *, proc_root: Path = Path("/proc"), boot_epoch: float | None = None) -> float | None:
    if boot_epoch is None:
        boot_epoch = _linux_boot_epoch(proc_root)
    if boot_epoch is None:
        return None
    try:
        stat_text = (proc_root / str(pid) / "stat").read_text(encoding="utf-8")
        ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
        start_ticks = int(stat_text.split()[21])
    except (OSError, ValueError, IndexError):
        return None
    return boot_epoch + (start_ticks / float(ticks))


def _proc_cmdline(pid: int, *, proc_root: Path = Path("/proc")) -> list[str]:
    try:
        data = (proc_root / str(pid) / "cmdline").read_bytes()
    except OSError:
        return []
    return [part.decode("utf-8", errors="replace") for part in data.split(b"\0") if part]


def _proc_ppid(pid: int, *, proc_root: Path = Path("/proc")) -> int | None:
    try:
        for line in (proc_root / str(pid) / "status").read_text(encoding="utf-8").splitlines():
            if line.startswith("PPid:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _proc_cwd(pid: int, *, proc_root: Path = Path("/proc")) -> str:
    try:
        return (proc_root / str(pid) / "cwd").resolve().as_posix()
    except OSError:
        return ""


SESSION_MEMORY_MCP_SERVER_BASENAMES = {
    "aoa-session-memory-mcp-server",
    "aoa-session-memory-mcp-server.py",
    "aoa_session_memory_mcp_server.py",
}


def _is_session_memory_mcp_server_cmdline(cmdline: list[str]) -> bool:
    for part in cmdline:
        if Path(part).name in SESSION_MEMORY_MCP_SERVER_BASENAMES:
            return True
        if part == "aoa_session_memory_mcp.server":
            return True
    return False


def _codex_config_path() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser().resolve() / "config.toml"
    return Path.home() / ".codex" / "config.toml"


MCP_CORE_SOURCE_PATH = Path(__file__).resolve()
MCP_SERVER_SOURCE_PATH = MCP_CORE_SOURCE_PATH.with_name("server.py")
MCP_CORE_LOADED_AT_EPOCH = time.time()
MCP_CORE_LOADED_SHA256 = _file_sha256(MCP_CORE_SOURCE_PATH)
# Preserve the server-wrapper hash across core auto-reloads; tool schemas are
# registered by the already-running server process and need a process restart.
MCP_SERVER_LOADED_SHA256 = globals().get("MCP_SERVER_LOADED_SHA256") or _file_sha256(MCP_SERVER_SOURCE_PATH)

DEFAULT_WORKSPACE_ROOT = Path("/srv/AbyssOS")
DEFAULT_TIMEOUT_SECONDS = 20.0
HTTP_BEARER_TOKEN_ENV_VAR = "AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN"
HTTP_BEARER_CREDENTIAL_NAME = "aoa-session-memory-mcp-read-bearer-token"
HTTP_BEARER_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9._~-]{43,512}")
MCP_ARCHIVE_READ_COMMANDS = frozenset(
    {
        "agent-closeouts",
        "agent-progress-updates",
        "agent-reasoning-windows",
        "agent-responses",
        "answer-neighborhood",
        "entity-usage-audit",
        "entity-usage-neighborhood",
        "entity-usage-scenario-audit",
        "goal-lifecycles",
        "literal-query-plan",
        "live-scenario-audit",
        "live-scenario-corpus",
        "maintenance-status",
        "rehydrate",
        "retrieve",
        "route-readiness",
        "search",
        "search-operational-direct-event-rollup-query",
        "search-operational-route-rollup-query",
        "search-provider-status",
        "task-episodes",
        "trace-route",
        "usage-chain",
    }
)
MCP_ARCHIVE_FORBIDDEN_FLAG_PREFIXES = (
    "--apply",
    "--refresh-host",
    "--refresh-state",
    "--write",
)
STATUS_TIMEOUT_SECONDS = 60.0
SEARCH_TIMEOUT_SECONDS = 60.0
EVIDENCE_PACKET_TIMEOUT_SECONDS = 90.0
DEFAULT_SEARCH_MAX_SHARDS = 24
USAGE_NEIGHBORHOOD_TIMEOUT_SECONDS = 20.0
ROUTE_ROLLUP_QUERY_TIMEOUT_SECONDS = 30.0
DIRECT_EVENT_ROLLUP_QUERY_TIMEOUT_SECONDS = 30.0
LIVE_READINESS_LIMIT: int | None = None
LIVE_READINESS_SAMPLE_LIMIT = 0
PROVIDER_DIRTY_SESSION_SAMPLE_LIMIT = 5
GOAL_LIFECYCLE_OBJECTIVE_PREVIEW_CHARS = 320
GOAL_LIFECYCLE_SAMPLE_OBJECTIVE_PREVIEW_CHARS = 220
GOAL_LIFECYCLE_SAMPLE_EVENT_LIMIT = 2
GOAL_LIFECYCLE_OBSERVATION_LIMIT = 2
ENTITY_USAGE_AUDIT_SAMPLE_LIMIT = 4
ENTITY_USAGE_CONSEQUENCE_SAMPLE_LIMIT = 3
ENTITY_USAGE_CHAIN_SAMPLE_LIMIT = 3
ENTITY_USAGE_CHAIN_CONSEQUENCE_SAMPLE_LIMIT = 2
ENTITY_USAGE_NEIGHBORHOOD_SAMPLE_LIMIT = 2
ENTITY_USAGE_LOCAL_EVENT_SAMPLE_LIMIT = 1
ENTITY_USAGE_DOCUMENT_REF_SAMPLE_LIMIT = 2
ENTITY_USAGE_TEXT_PREVIEW_CHARS = 80
ENTITY_USAGE_ACTION_LIMIT = 12
ENTITY_USAGE_ACTION_SAMPLE_LIMIT = 3
ENTITY_USAGE_ACTION_SEMANTIC_PRIORITY = (
    "selected",
    "loaded",
    "completed",
    "verified",
    "procedure_observed",
    "deflected",
    "failed",
    "repaired",
    "validated",
    "edited",
    "called",
    "used",
    "observed",
    "configured",
    "read",
)
ENTITY_USAGE_WEAK_ACTION_PRIORITY = (
    "skill_read",
    "prompt_visible",
    "mentioned",
    "cooccurrence",
    "context",
)
SKILL_EVIDENCE_STATE_LIST_LIMIT = 16
ENTITY_DOSSIER_USAGE_LIMIT = 4
ENTITY_DOSSIER_NEIGHBORHOOD_LIMIT = 2
ENTITY_DOSSIER_GRAPH_LIMIT = 12
ENTITY_DOSSIER_GRAPH_EDGE_LIMIT = 24
ENTITY_DOSSIER_EVIDENCE_REF_LIMIT = 10
GRAPH_NODE_SAMPLE_LIMIT = 8
GRAPH_EDGE_SAMPLE_LIMIT = 8
GRAPH_EVENT_SAMPLE_LIMIT = 8
GRAPH_EVIDENCE_REF_SAMPLE_LIMIT = 6
GRAPH_ITEM_TEXT_PREVIEW_CHARS = 64
GRAPH_ROUTE_TERM_SHARD_LIMIT = 12
GRAPH_ROUTE_TERM_MATCH_LIMIT = 48
GRAPH_SQLITE_EDGE_BUDGET_MAX = 400
INVENTORY_SAMPLE_LABEL_CHARS = 64
INVENTORY_TOTAL_SAMPLE_LIMIT = 12


def _http_bearer_auth_state() -> dict[str, Any]:
    environment_value = os.environ.get(HTTP_BEARER_TOKEN_ENV_VAR)
    environment_available = environment_value is not None
    environment_valid = bool(
        environment_value is not None
        and HTTP_BEARER_TOKEN_PATTERN.fullmatch(environment_value)
    )

    owner_context = os.environ.get("AOA_MCP_TRANSPORT", "").strip() == "streamable-http"
    systemd_available = False
    systemd_readable = False
    systemd_valid = False
    systemd_value: str | None = None
    if owner_context:
        credential_dir = os.environ.get("CREDENTIALS_DIRECTORY", "").strip()
        if credential_dir:
            credential_path = Path(credential_dir) / HTTP_BEARER_CREDENTIAL_NAME
            systemd_available = credential_path.is_file() and not credential_path.is_symlink()
            if systemd_available:
                try:
                    systemd_value = credential_path.read_text(encoding="utf-8").removesuffix("\n")
                except (OSError, UnicodeError):
                    systemd_value = None
                systemd_readable = systemd_value is not None
                systemd_valid = bool(
                    systemd_value is not None
                    and HTTP_BEARER_TOKEN_PATTERN.fullmatch(systemd_value)
                )

    sources_conflict = False
    if owner_context and environment_valid and systemd_valid:
        assert environment_value is not None
        assert systemd_value is not None
        # Valid credentials are URL-safe ASCII, so UTF-8 cannot expose an
        # encoding-dependent failure or the credential value.
        sources_conflict = not hmac.compare_digest(
            environment_value.encode("utf-8"),
            systemd_value.encode("utf-8"),
        )
    environment_ready = bool(environment_available and environment_valid)
    systemd_ready = bool(systemd_available and systemd_readable and systemd_valid)
    all_present_sources_valid = bool(
        (not environment_available or environment_valid)
        and (not systemd_available or systemd_ready)
    )
    owner_ready = bool(
        owner_context
        and all_present_sources_valid
        and not sources_conflict
        and (environment_ready or systemd_ready)
    )
    return {
        "execution_context": "shared_http_owner" if owner_context else "client_or_cli",
        "environment": {
            "available": environment_available,
            "valid": environment_valid,
            "ready": environment_ready,
        },
        "systemd_credential": {
            "observable": owner_context,
            "available": systemd_available if owner_context else None,
            "readable": systemd_readable if owner_context else None,
            "valid": systemd_valid if owner_context else None,
            "ready": systemd_ready if owner_context else None,
        },
        "sources_conflict": sources_conflict,
        "ready": owner_ready if owner_context else environment_ready,
    }


def _http_bearer_next_action(configured_server: dict[str, Any]) -> str:
    authentication = configured_server.get("authentication")
    if (
        isinstance(authentication, dict)
        and authentication.get("execution_context") == "shared_http_owner"
    ):
        return (
            "Correct or provision the shared HTTP owner's environment/systemd bearer sources, "
            "then restart that owner without printing either credential."
        )
    return (
        "Make the configured bearer credential available to the Codex process through "
        "AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN without printing it."
    )

ALLOWED_TRACE_KINDS = {
    "auto",
    "decision",
    "entity",
    "error",
    "external",
    "failure",
    "git",
    "github",
    "goal",
    "hook",
    "receipt",
    "mcp",
    "owner_route",
    "path",
    "api",
    "plugin",
    "agent",
    "agent_event",
    "script",
    "validator",
    "test",
    "eval",
    "git",
    "playbook",
    "route_next_action",
    "technique",
    "mechanic",
    "graph",
    "memory",
    "skill",
    "tool",
}
TRACE_KIND_ALIASES = {
    "mcp_service": "mcp",
    "mcp_services": "mcp",
    "mcp_tool": "tool",
    "mcp_tools": "tool",
    "failure_mode": "error",
    "hook_health": "receipt",
    "route": "owner_route",
}
ALLOWED_DOC_TYPES = {"all", "session", "segment", "event", "incident", "task_episode", "goal_lifecycle", "entity_registry"}
ALLOWED_SEARCH_DOC_TYPES = {"session", "segment", "event", "incident", "task_episode", "goal_lifecycle", "entity_registry"}
DEFAULT_GRAPH_QUALITY_ANCHORS = [
    "mcp:aoa_session_memory_mcp",
    "skill:aoa-memo-writeback",
    "tool:apply_patch",
]
ALLOWED_RETRIEVAL_RECIPES = {
    "continue-session",
    "continue-techniques-session",
    "hook-failure",
    "manual-review",
    "naming-candidate",
    "process-lessons",
    "repeated-errors",
}
ENTITY_USAGE_RETRIEVAL_RECIPES = {"entity-usage", "entity_usage", "entity-usage-chain", "entity_usage_chain", "entity-usage-audit", "entity_usage_audit"}
SUPPORTED_LIVE_SCENARIO_PROFILES = [
    "entity_registry_lookup",
    "entity_dossier",
    "entity_usage",
    "hook_failure",
    "goal_lifecycle",
    "agent_closeout",
    "literal_planner",
    "graph_neighborhood",
    "graph_bridge",
    "route_rollup_query",
]
SEARCH_FILTER_ALIASES = {
    "layer": "route_layer",
}
SEARCH_CONTROL_FILTERS = {"use_shards", "max_shards"}
REQUESTED_AGENT_EVENT_FILTER = "_requested_agent_event"
SEARCH_FILTER_FLAGS = {
    "session": "--session",
    "doc_type": "--doc-type",
    "event_type": "--event-type",
    "family": "--family",
    "outcome": "--outcome",
    "conversation_act": "--conversation-act",
    "session_act": "--session-act",
    "agent_event": "--agent-event",
    "task_episode_id": "--task-episode-id",
    "route_layer": "--route-layer",
    "route_signal": "--route-signal",
    "archive_status": "--archive-status",
    "freshness_status": "--freshness-status",
    "date_from": "--date-from",
    "date_to": "--date-to",
}
AGENT_ROUTE_SEARCH_FILTERS = {
    "closeout_final",
    "event_kind",
    "episode",
    "failure_state",
    "goal_id",
    "status",
    "verification_state",
}
AGENT_ROUTE_ONLY_SEARCH_FILTERS = {
    "closeout_final",
    "event_kind",
    "failure_state",
    "goal_id",
    "status",
    "verification_state",
}
AGENT_ROUTE_FAST_PATH_FILTERS = {
    "agent_event",
    "doc_type",
    "session",
    "task_episode_id",
}
STOP_LINES = [
    "Do not replace raw transcript evidence with MCP summaries.",
    "Do not write, repair, reindex, relabel, export, distill, or promote session memory from this MCP.",
    "Do not treat generated atlas/search/readiness output as reviewed truth.",
    "Do not expose bulk raw transcript payloads by default.",
    "Do not bind HTTP beyond loopback or bypass the source-owned MCP lifecycle decision.",
]
ROUTE_LAYERS = [
    "scope_contract",
    "authority_surface",
    "entity",
    "path",
    "skill",
    "tool",
    "mcp",
    "hook",
    "api",
    "plugin",
    "agent",
    "script",
    "validator",
    "test",
    "eval",
    "git",
    "playbook",
    "technique",
    "mechanic",
    "graph",
    "memory",
    "hook_health",
    "goal",
    "verification_state",
    "decision_thread",
    "failure_mode",
    "memory_provenance",
    "freshness_drift",
    "owner_route",
    "runtime_environment",
    "mutation_surface",
    "correlation",
    "confidence",
    "access_boundary",
    "resource_profile",
    "operator_preference",
    "agent_event",
]
INVENTORY_LAYER_TO_AXIS = {
    "skill": "by-skill",
    "mcp": "by-mcp",
    "hook": "by-hook",
    "tool": "by-tool",
    "api": "by-api",
    "plugin": "by-plugin",
    "agent": "by-agent",
    "script": "by-script",
    "validator": "by-validator",
    "test": "by-test",
    "eval": "by-eval",
    "git": "by-git",
    "playbook": "by-playbook",
    "technique": "by-technique",
    "mechanic": "by-mechanic",
    "graph": "by-graph",
    "memory": "by-memory-entity",
    "agent_event": "by-agent-event",
}
INVENTORY_INPUT_LAYER_TO_ROUTE_LAYER = {
    "skills": "skill",
    "mcp_service": "mcp",
    "mcp_services": "mcp",
    "mcps": "mcp",
    "hooks": "hook",
    "tools": "tool",
    "apis": "api",
    "plugins": "plugin",
    "agents": "agent",
    "scripts": "script",
    "validators": "validator",
    "tests": "test",
    "evals": "eval",
    "git_tools": "git",
    "playbooks": "playbook",
    "techniques": "technique",
    "mechanics": "mechanic",
    "graphs": "graph",
    "memories": "memory",
    "goals": "goal",
}
AGENT_EVENT_DEFAULTS_BY_ROUTE = {
    "agent-closeouts": ["assistant_closeout", "assistant_verification_report"],
    "agent-progress-updates": ["assistant_progress_update"],
    "agent-reasoning-windows": ["assistant_reasoning_boundary", "assistant_reasoning"],
    "answer-neighborhood": ["assistant_answer", "assistant_closeout", "assistant_verification_report"],
}
AGENT_EVENT_ROUTE_ALIASES = {
    "answer": "assistant_answer",
    "assistant_answer": "assistant_answer",
    "response": "assistant_answer",
    "assistant_response": "assistant_answer",
    "open_thread": "assistant_open_thread",
    "assistant_open_thread": "assistant_open_thread",
    "thread": "assistant_open_thread",
    "remaining_gap": "assistant_open_thread",
    "final": "assistant_final_closeout",
    "closeout": "assistant_final_closeout",
    "final_closeout": "assistant_final_closeout",
    "assistant_final_closeout": "assistant_final_closeout",
    "reasoning": "assistant_reasoning_boundary",
    "reasoning_boundary": "assistant_reasoning_boundary",
    "reasoning_window": "assistant_reasoning_boundary",
    "assistant_reasoning_boundary": "assistant_reasoning_boundary",
    "plan": "assistant_plan",
    "assistant_plan": "assistant_plan",
    "progress": "assistant_progress_update",
    "progress_update": "assistant_progress_update",
    "assistant_progress_update": "assistant_progress_update",
    "verification": "assistant_verification_report",
    "verification_report": "assistant_verification_report",
    "assistant_verification_report": "assistant_verification_report",
    "decision": "assistant_decision",
    "assistant_decision": "assistant_decision",
    "assumption": "assistant_assumption",
    "assistant_assumption": "assistant_assumption",
    "checkpoint": "assistant_checkpoint",
    "assistant_checkpoint": "assistant_checkpoint",
    "blocker": "assistant_blocker_report",
    "blocked": "assistant_blocker_report",
    "assistant_blocker_report": "assistant_blocker_report",
    "handoff": "assistant_handoff_or_resume",
    "resume": "assistant_handoff_or_resume",
    "assistant_handoff_or_resume": "assistant_handoff_or_resume",
    "correction": "assistant_correction_ack",
    "correction_ack": "assistant_correction_ack",
    "assistant_correction_ack": "assistant_correction_ack",
    "process_lesson": "assistant_process_lesson",
    "assistant_process_lesson": "assistant_process_lesson",
}


@dataclass(slots=True)
class CommandOutput:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: float


CommandRunner = Callable[[list[str], float], CommandOutput]


def _default_runner(argv: list[str], timeout_seconds: float) -> CommandOutput:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return CommandOutput(
            argv=argv,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandOutput(
            argv=argv,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"command timed out after {timeout_seconds}s",
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _coerce_limit(value: int | None, default: int, maximum: int) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _coerce_bounded_int(value: int | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).casefold() in {"1", "true", "yes", "on"}


def _filter_is_active(value: Any) -> bool:
    return value not in (None, "", "any", False)


def _ensure_short_text(value: str, field: str, limit: int = 600) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} is too long; keep MCP calls focused")
    if "\x00" in text:
        raise ValueError(f"{field} contains an invalid NUL byte")
    return text


def _bounded_string(value: Any, limit: int) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _safe_selector(value: str, field: str, limit: int = 160) -> str:
    text = _ensure_short_text(value, field, limit=limit)
    if not re.fullmatch(r"[A-Za-z0-9А-Яа-я_.:/@#,+ -]+", text):
        raise ValueError(f"{field} contains unsupported characters")
    return text


def _route_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _normalize_trace_kind(kind: str | None) -> str:
    normalized = _route_key(str(kind or "auto")) or "auto"
    return TRACE_KIND_ALIASES.get(normalized, normalized)


def _explicit_route_signal_parts(value: str) -> tuple[str, str, str] | None:
    layer_text, separator, key_text = value.partition(":")
    if not separator:
        return None
    layer = _normalize_trace_kind(layer_text)
    key = _route_key(key_text)
    if layer not in ALLOWED_TRACE_KINDS - {"auto"} or not key:
        return None
    return layer, key, f"{layer}:{key}"


def _requested_trace_kind_key(kind: str | None) -> str:
    return _route_key(str(kind or "auto")) or "auto"


def _coerce_trace_kind(kind: str | None, *, error_label: str = "trace kind") -> str:
    normalized = _normalize_trace_kind(kind)
    if normalized not in ALLOWED_TRACE_KINDS:
        requested = str(kind or "auto").strip() or "auto"
        raise ValueError(f"unsupported {error_label}: {requested}")
    return normalized


def _annotate_trace_kind_payload(payload: dict[str, Any], *, requested_kind: str | None, normalized_kind: str) -> dict[str, Any]:
    requested = _requested_trace_kind_key(requested_kind)
    payload.setdefault("kind", normalized_kind)
    if requested != normalized_kind:
        payload.setdefault("requested_kind", requested)
    return payload


def _normalize_agent_event_class(value: str | None) -> str:
    slug = _route_key(str(value or ""))
    if not slug:
        return ""
    return AGENT_EVENT_ROUTE_ALIASES.get(slug, slug)


def _normalize_agent_event_classes(values: list[str] | None, *, default: list[str] | None = None) -> tuple[list[str], list[str]]:
    requested = [str(item) for item in (values or []) if str(item or "").strip()]
    classes: list[str] = []
    for item in requested:
        normalized = _normalize_agent_event_class(item)
        if normalized and normalized not in classes:
            classes.append(normalized)
    if not classes and default:
        classes = list(default)
    return classes, requested


def _normalize_search_filters(filters: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalized = dict(filters)
    diagnostics: list[str] = []
    for alias, canonical in SEARCH_FILTER_ALIASES.items():
        alias_value = normalized.get(alias)
        if alias_value in (None, ""):
            continue
        canonical_value = normalized.get(canonical)
        if canonical_value in (None, ""):
            normalized[canonical] = alias_value
        elif canonical_value != alias_value:
            diagnostics.append(
                f"ignored filter alias {alias!r}={alias_value!r}; using {canonical!r}={canonical_value!r}"
            )
        normalized.pop(alias, None)
    agent_event_value = normalized.get("agent_event")
    if agent_event_value not in (None, ""):
        normalized_events, requested_events = _normalize_agent_event_classes(
            _split_filter_values(agent_event_value)
        )
        if normalized_events:
            normalized["agent_event"] = ",".join(normalized_events)
            if requested_events != normalized_events:
                normalized[REQUESTED_AGENT_EVENT_FILTER] = ",".join(requested_events)
                diagnostics.append(
                    "normalized agent_event aliases: "
                    + ",".join(requested_events)
                    + " -> "
                    + ",".join(normalized_events)
                )
    return normalized, diagnostics


def _annotate_agent_event_payload(payload: dict[str, Any], *, requested: list[str], normalized: list[str]) -> dict[str, Any]:
    payload.setdefault("agent_events", normalized)
    if requested and requested != normalized:
        payload.setdefault("requested_agent_events", requested)
    return payload


def _session_date_from_label(value: Any) -> str | None:
    match = re.search(r"(?:^|[^0-9])(20\d{2}-\d{2}-\d{2})(?=$|[^0-9])", str(value or ""))
    return match.group(1) if match else None


def _session_date_from_entry(entry: dict[str, Any]) -> str | None:
    return str(entry.get("session_date") or "").strip() or _session_date_from_label(entry.get("session"))


def _normalize_axis(axis: str) -> str:
    text = _ensure_short_text(axis, "axis", limit=80).casefold().replace("_", "-")
    return text if text.startswith("by-") else f"by-{text}"


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _split_pipe(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [part for part in value.strip("|").split("|") if part]


def _split_filter_values(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _parse_iso_time(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text = f"{text}T00:00:00+00:00"
    elif text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _compact_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": hit.get("doc_id"),
        "doc_type": hit.get("doc_type"),
        "session_id": hit.get("session_id"),
        "session_label": hit.get("session_label"),
        "session_title": hit.get("session_title"),
        "session_date": hit.get("session_date"),
        "segment_id": hit.get("segment_id"),
        "event_id": hit.get("event_id"),
        "event_type": hit.get("event_type"),
        "family": hit.get("family"),
        "conversation_act": hit.get("conversation_act"),
        "session_act": hit.get("session_act"),
        "agent_event": hit.get("agent_event"),
        "task_episode_id": hit.get("task_episode_id"),
        "route_layers": hit.get("route_layers"),
        "route_signals": hit.get("route_signals"),
        "title": hit.get("title"),
        "snippet": hit.get("snippet"),
        "refs": hit.get("refs"),
        "freshness": hit.get("freshness"),
        "matched_routes": hit.get("matched_routes"),
    }


def _compact_search_provider(provider: Any) -> dict[str, Any]:
    if not isinstance(provider, dict):
        return {}
    compact: dict[str, Any] = {
        key: provider.get(key)
        for key in (
            "selected",
            "authoritative_result_provider",
            "accelerator_provider",
            "accelerator_status",
        )
        if provider.get(key) not in (None, "", [], {})
    }
    status = provider.get("status")
    if isinstance(status, dict):
        compact["status"] = _compact_usage_provider_status(status)
    elif status not in (None, "", [], {}):
        compact["status"] = status
    for key in ("semantic_overlay", "local_rerank"):
        value = provider.get(key)
        if isinstance(value, dict):
            compact[key] = {
                subkey: value.get(subkey)
                for subkey in ("ok", "status", "provider", "mode")
                if value.get(subkey) not in (None, "", [], {})
            }
        elif value not in (None, "", [], {}):
            compact[key] = value
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _compact_search_projection(projection: Any) -> dict[str, Any]:
    if not isinstance(projection, dict):
        return {}
    return {
        key: projection.get(key)
        for key in (
            "mode",
            "fallback_mode",
            "source",
            "provider",
            "uses_shards",
            "max_shards",
            "fallback_route",
            "next_expansion_command",
        )
        if projection.get(key) not in (None, "", [], {})
    }


def _hook_event_from_search_filters(filters: dict[str, Any]) -> tuple[bool, str]:
    route_layers = [item.casefold() for item in _split_filter_values(filters.get("route_layer"))]
    hook_route = "hook" in route_layers
    hook_event = ""
    for signal in _split_filter_values(filters.get("route_signal")):
        if signal.casefold().startswith("hook:"):
            hook_route = True
            hook_event = signal.split(":", 1)[1].strip()
            break
    return hook_route, hook_event


def _search_date_semantics(filters: dict[str, Any]) -> dict[str, Any]:
    date_filters = {
        key: str(filters.get(key)).strip()
        for key in ("date_from", "date_to")
        if filters.get(key) not in (None, "")
    }
    if not date_filters:
        return {}
    semantics: dict[str, Any] = {
        "filter_basis": "indexed_search_document_or_session_date",
        "date_filters": date_filters,
        "does_not_filter": ["hook_receipt_timestamp"],
        "authority_boundary": (
            "Search date filters constrain the generated .aoa search read model; "
            "raw/segment evidence and hook receipt timestamps remain separate evidence routes."
        ),
    }
    hook_route, hook_event = _hook_event_from_search_filters(filters)
    if hook_route:
        hook_args: dict[str, Any] = {
            "event_name": hook_event or "UserPromptSubmit",
            "only_errors": False,
        }
        if date_filters.get("date_from"):
            hook_args["date_from"] = date_filters["date_from"]
        semantics["hook_receipts_route"] = {
            "mcp_tool": "aoa_session_hook_receipts",
            "why": "Use this route when the date question is about hooks/receipts.jsonl receipt timestamps.",
            "args": hook_args,
            "date_filter_basis": "hook_receipt_timestamp",
        }
        if date_filters.get("date_to"):
            semantics["hook_receipts_route"]["date_to_supported"] = False
            semantics["hook_receipts_route"]["date_to_note"] = (
                "aoa_session_hook_receipts currently exposes date_from only; use a bounded raw receipt ref "
                "inspection if an upper timestamp bound is required."
            )
    return semantics


def _hook_receipt_date_semantics(date_from: str) -> dict[str, Any]:
    semantics: dict[str, Any] = {
        "filter_basis": "hook_receipt_timestamp",
        "timestamp_fields": ["timestamp", "received_at", "generated_at"],
        "not_session_date": True,
        "search_date_filter_note": (
            "aoa_session_search date_from/date_to filter indexed search document/session dates, "
            "not hooks/receipts.jsonl receipt timestamps."
        ),
    }
    if date_from:
        semantics["date_filters"] = {"date_from": date_from}
    return semantics


def _search_mcp_route_plan(payload: dict[str, Any], *, filters: dict[str, Any], full_route: str) -> dict[str, Any]:
    text = str(payload.get("query") or payload.get("normalized_query") or "").strip()
    active_filters = {
        key: str(value).strip()
        for key, value in filters.items()
        if key in SEARCH_FILTER_FLAGS and value not in (None, "")
    }
    if not text and not active_filters:
        return {}
    projection = payload.get("search_projection")
    archive_projection_mode = projection.get("mode") if isinstance(projection, dict) else None
    cost_profile = payload.get("cost_profile")
    plan: dict[str, Any] = {
        "route_kind": "structured_filter_search" if active_filters and not text else "text_search",
        "uses_text_query": bool(text),
        "structured_filters": sorted(active_filters),
        "archive_projection_mode": archive_projection_mode,
        "lightweight_route": (cost_profile or {}).get("lightweight_route") if isinstance(cost_profile, dict) else None,
        "next_expansion": "full_search_route",
        "full_search_route": full_route,
    }
    if active_filters.get("route_signal"):
        plan["typed_route_signal"] = True
    if plan["route_kind"] == "structured_filter_search" and archive_projection_mode == "monolith_fallback":
        plan["projection_note"] = (
            "Archive projection mode is provider metadata; this MCP call used structured filters "
            "and did not run a broad literal text query."
        )
    return {key: value for key, value in plan.items() if value not in (None, "", [], {})}


def _compact_search_payload(payload: dict[str, Any], *, full_route: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    search_filters = filters or {}
    passthrough_keys = (
        "schema_version",
        "artifact_type",
        "search_schema_version",
        "generated_at",
        "ok",
        "query",
        "normalized_query",
        "index_generated_at",
        "aoa_root",
        "result_count",
        "diagnostics",
        "cost_profile",
    )
    for key in passthrough_keys:
        if payload.get(key) not in (None, "", [], {}):
            compact[key] = payload.get(key)
    search_projection = _compact_search_projection(payload.get("search_projection"))
    if search_projection:
        compact["search_projection"] = search_projection
    provider = _compact_search_provider(payload.get("provider"))
    if provider:
        compact["provider"] = provider
    results = payload.get("results")
    if isinstance(results, list):
        compact["results"] = [_compact_hit(hit) for hit in results if isinstance(hit, dict)]
        compact["result_count"] = payload.get("result_count", len(results))
    route_plan = _search_mcp_route_plan(payload, filters=search_filters, full_route=full_route)
    if route_plan:
        compact["mcp_route_plan"] = route_plan
    date_semantics = _search_date_semantics(search_filters)
    if date_semantics:
        compact["date_semantics"] = date_semantics
    mcp_access = dict(payload.get("mcp_access")) if isinstance(payload.get("mcp_access"), dict) else {}
    mcp_access.update(
        {
            "response_compacted": True,
            "full_search_route": full_route,
            "authority_boundary": "MCP returns compact search hits and provider summary; raw/segment evidence remains authoritative.",
        }
    )
    compact["mcp_access"] = mcp_access
    compact["mcp_payload_policy"] = {
        "response_compacted": True,
        "result_count": compact.get("result_count", 0),
        "provider_summary_compacted": bool(provider),
        "full_search_route": full_route,
        "mcp_route_plan_exposed": bool(route_plan),
        "date_semantics_exposed": bool(date_semantics),
    }
    compact["authority_boundary"] = "MCP returns compact search hits and provider summary; raw/segment evidence remains authoritative."
    return compact


def _compact_episode_ref(ref: Any) -> dict[str, Any]:
    if not isinstance(ref, dict):
        return {"ref": str(ref)}
    keys = (
        "event_id",
        "line",
        "raw_ref",
        "segment_id",
        "segment_ref",
        "event_type",
        "source_type",
        "conversation_act",
        "session_act",
        "agent_event",
    )
    return {key: ref.get(key) for key in keys if ref.get(key) not in (None, "", [])}


def _compact_episode_sample_refs(sample_refs: Any, *, per_bucket_limit: int = 1) -> dict[str, Any]:
    if not isinstance(sample_refs, dict):
        return {}
    compact: dict[str, Any] = {}
    for bucket, refs in sample_refs.items():
        if not isinstance(refs, list):
            continue
        selected = [_compact_episode_ref(ref) for ref in refs[:per_bucket_limit]]
        compact[str(bucket)] = {
            "refs": selected,
            "ref_count": len(refs),
            "omitted_ref_count": max(0, len(refs) - len(selected)),
        }
    return compact


def _compact_task_episode(episode: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in (
        "session_id",
        "session_label",
        "episode_id",
        "status",
        "confidence",
        "verification_state",
        "failure_state",
        "ambiguity_flags",
        "transition",
        "event_range",
        "counts",
        "truth_level",
    ):
        if key in episode:
            compact[key] = episode.get(key)
    if isinstance(episode.get("start_user_ref"), dict):
        compact["start_user_ref"] = _compact_episode_ref(episode["start_user_ref"])
    if isinstance(episode.get("sample_refs"), dict):
        compact["sample_refs"] = _compact_episode_sample_refs(episode["sample_refs"], per_bucket_limit=1)
    return compact


def _bounded_text(value: Any, *, limit: int) -> tuple[str, int, bool]:
    text = str(value or "")
    if len(text) <= limit:
        return text, len(text), False
    return text[: max(0, limit - 3)].rstrip() + "...", len(text), True


def _compact_goal_event(event: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: event.get(key)
        for key in (
            "schema_version",
            "event_id",
            "kind",
            "tool_name",
            "tool_namespace",
            "objective",
            "status_arg",
            "usage",
            "timestamp",
            "line",
            "task_episode_id",
            "route_signals",
        )
        if event.get(key) not in (None, "", [], {})
    }
    refs = _compact_episode_ref(event)
    if isinstance(event.get("refs"), dict):
        refs = {**refs, **_compact_episode_ref(event["refs"])}
    if refs:
        compact["refs"] = refs
    if "objective" in compact:
        preview, chars, omitted = _bounded_text(
            compact.get("objective"),
            limit=GOAL_LIFECYCLE_SAMPLE_OBJECTIVE_PREVIEW_CHARS,
        )
        compact["objective"] = preview
        compact["objective_chars"] = chars
        compact["objective_omitted"] = omitted
    return compact


def _compact_goal_lifecycle(lifecycle: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: lifecycle.get(key)
        for key in (
            "schema_version",
            "session_label",
            "session_id",
            "goal_id",
            "goal_instance_id",
            "status",
            "event_count",
            "event_kinds",
            "event_ids",
            "task_episode_ids",
            "ambiguity_flags",
            "usage",
            "objective_source",
            "truth_level",
        )
        if lifecycle.get(key) not in (None, "", [], {})
    }
    if "objective" in compact:
        preview, chars, omitted = _bounded_text(
            compact.get("objective"),
            limit=GOAL_LIFECYCLE_OBJECTIVE_PREVIEW_CHARS,
        )
        compact["objective"] = preview
        compact["objective_chars"] = chars
        compact["objective_omitted"] = omitted
    elif "objective" in lifecycle:
        preview, chars, omitted = _bounded_text(
            lifecycle.get("objective"),
            limit=GOAL_LIFECYCLE_OBJECTIVE_PREVIEW_CHARS,
        )
        compact["objective"] = preview
        compact["objective_chars"] = chars
        compact["objective_omitted"] = omitted
    refs = lifecycle.get("refs")
    if isinstance(refs, dict):
        compact["refs"] = {
            key: _compact_episode_ref(value)
            for key, value in refs.items()
            if isinstance(value, dict) and _compact_episode_ref(value)
        }
    observed_goal = lifecycle.get("observed_goal")
    if isinstance(observed_goal, dict):
        compact_goal = _compact_goal_state(observed_goal)
        if compact_goal:
            compact["observed_goal"] = compact_goal
    state_observations = lifecycle.get("state_observations")
    if isinstance(state_observations, list):
        compact["state_observations"] = [
            compacted
            for item in state_observations[:GOAL_LIFECYCLE_OBSERVATION_LIMIT]
            if isinstance(item, dict)
            for compacted in [_compact_goal_state_observation(item)]
            if compacted
        ]
        compact["omitted_state_observation_count"] = max(0, len(state_observations) - GOAL_LIFECYCLE_OBSERVATION_LIMIT)
    usage_observations = lifecycle.get("usage_observations")
    if isinstance(usage_observations, list):
        compact["usage_observations"] = [
            compacted
            for item in usage_observations[:GOAL_LIFECYCLE_OBSERVATION_LIMIT]
            if isinstance(item, dict)
            for compacted in [_compact_goal_usage_observation(item)]
            if compacted
        ]
        compact["omitted_usage_observation_count"] = max(0, len(usage_observations) - GOAL_LIFECYCLE_OBSERVATION_LIMIT)
    for key, limit in (("raw_refs", 8), ("segment_refs", 4), ("graph_refs", 8)):
        values = lifecycle.get(key)
        if isinstance(values, list):
            compact[key] = values[:limit]
            compact[f"omitted_{key}_count"] = max(0, len(values) - limit)
    sample_events = compact.get("sample_events")
    if not isinstance(sample_events, list):
        sample_events = lifecycle.get("sample_events")
    if isinstance(sample_events, list):
        compact["sample_events"] = [
            _compact_goal_event(event)
            for event in sample_events[:GOAL_LIFECYCLE_SAMPLE_EVENT_LIMIT]
            if isinstance(event, dict)
        ]
        compact["omitted_sample_event_count"] = max(0, len(sample_events) - GOAL_LIFECYCLE_SAMPLE_EVENT_LIMIT)
    return compact


def _compact_goal_state(state: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in ("threadId", "status", "createdAt", "updatedAt"):
        if state.get(key) not in (None, "", [], {}):
            compact[key] = state.get(key)
    if state.get("objective") not in (None, "", [], {}):
        preview, chars, omitted = _bounded_text(
            state.get("objective"),
            limit=GOAL_LIFECYCLE_OBJECTIVE_PREVIEW_CHARS,
        )
        compact["objective"] = preview
        compact["objective_chars"] = chars
        compact["objective_omitted"] = omitted
    return compact


def _compact_goal_state_observation(observation: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: observation.get(key)
        for key in ("source", "event_id")
        if observation.get(key) not in (None, "", [], {})
    }
    state = observation.get("state")
    if isinstance(state, dict):
        compact_state = _compact_goal_state(state)
        if compact_state:
            compact["state"] = compact_state
    refs = observation.get("refs")
    if isinstance(refs, dict):
        compact_ref = _compact_episode_ref(refs)
        if compact_ref:
            compact["refs"] = compact_ref
    return compact


def _compact_goal_usage_observation(observation: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: observation.get(key)
        for key in ("source", "event_id")
        if observation.get(key) not in (None, "", [], {})
    }
    usage = observation.get("usage")
    if isinstance(usage, dict):
        compact_usage = _compact_usage_mapping(usage)
        if compact_usage:
            compact["usage"] = compact_usage
    refs = observation.get("refs")
    if isinstance(refs, dict):
        compact_ref = _compact_episode_ref(refs)
        if compact_ref:
            compact["refs"] = compact_ref
    return compact


def _compact_usage_scalar(value: Any, *, limit: int = ENTITY_USAGE_TEXT_PREVIEW_CHARS) -> Any:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, (bool, int, float)):
        return value
    return _bounded_string(value, limit)


def _compact_usage_list(value: Any, *, limit: int = 4, text_limit: int = ENTITY_USAGE_TEXT_PREVIEW_CHARS) -> list[Any]:
    if not isinstance(value, list):
        return []
    compact: list[Any] = []
    for item in value[:limit]:
        if isinstance(item, dict):
            compact.append(_compact_usage_mapping(item, text_limit=text_limit))
        elif isinstance(item, list):
            compact.append(_compact_usage_list(item, limit=limit, text_limit=text_limit))
        else:
            scalar = _compact_usage_scalar(item, limit=text_limit)
            if scalar not in (None, "", [], {}):
                compact.append(scalar)
    return compact


def _compact_usage_mapping(
    value: Any,
    *,
    allowed_keys: tuple[str, ...] | None = None,
    text_limit: int = ENTITY_USAGE_TEXT_PREVIEW_CHARS,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        scalar = _compact_usage_scalar(value, limit=text_limit)
        return {"value": scalar} if scalar not in (None, "", [], {}) else {}
    keys = allowed_keys or tuple(value.keys())
    compact: dict[str, Any] = {}
    omitted: list[str] = []
    for key in keys:
        if key not in value:
            continue
        item = value.get(key)
        if item in (None, "", [], {}):
            continue
        if isinstance(item, dict):
            nested = _compact_usage_mapping(item, text_limit=text_limit)
            if nested:
                compact[key] = nested
        elif isinstance(item, list):
            nested_list = _compact_usage_list(item, limit=4, text_limit=text_limit)
            if nested_list:
                compact[key] = nested_list
                if len(item) > len(nested_list):
                    compact[f"omitted_{key}_count"] = len(item) - len(nested_list)
        else:
            scalar = _compact_usage_scalar(item, limit=text_limit)
            if scalar not in (None, "", [], {}):
                compact[key] = scalar
    for key in value.keys():
        if key not in keys and value.get(key) not in (None, "", [], {}):
            omitted.append(str(key))
    if omitted:
        compact["omitted_field_count"] = len(omitted)
    return compact


def _compact_usage_freshness(freshness: Any) -> dict[str, Any]:
    if not isinstance(freshness, dict):
        return {}
    return {
        key: freshness.get(key)
        for key in (
            "status",
            "basis",
            "live_verification",
            "segment_index_live_check",
            "target_dirty",
            "target_deferred_live",
        )
        if freshness.get(key) not in (None, "", [], {})
    }


def _compact_usage_refs(refs: Any) -> dict[str, Any]:
    return _compact_usage_mapping(
        refs,
        allowed_keys=(
            "raw",
            "raw_ref",
            "raw_block",
            "segment",
            "segment_ref",
            "segment_index",
            "session",
            "session_ref",
            "graph",
            "graph_ref",
            "line",
            "value",
            "kind",
        ),
    )


def _compact_first_ref(ref: Any) -> dict[str, Any]:
    return _without_omitted_field_counts(
        _compact_usage_mapping(
            ref,
            allowed_keys=(
                "raw",
                "raw_ref",
                "raw_block",
                "segment",
                "segment_ref",
                "segment_index",
                "session",
                "session_ref",
                "line",
                "value",
                "kind",
            ),
        )
    )


def _without_omitted_field_counts(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_omitted_field_counts(item)
            for key, item in value.items()
            if key != "omitted_field_count"
        }
    if isinstance(value, list):
        return [_without_omitted_field_counts(item) for item in value]
    return value


def _compact_skill_evidence(evidence: Any) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return {}
    compact: dict[str, Any] = {}
    for key in (
        "schema_version",
        "candidate_only",
        "input_event_count",
        "unique_evidence_event_count",
        "unique_evidence_fact_count",
        "duplicate_evidence_association_count",
        "structured_skill_selection_event_count",
        "task_episode_link_event_count",
        "task_episode_ref_count",
        "dispatch_candidate_present",
        "behavioral_candidate_present",
        "receipt_or_review_ingestion_available",
        "invocation_claim_allowed",
        "invocation_claim_blocker",
        "authority_boundary",
    ):
        scalar = _compact_usage_scalar(evidence.get(key), limit=220)
        if scalar not in (None, "", [], {}):
            compact[key] = scalar
    for key in (
        "supported_states",
        "automatic_candidate_states",
        "receipt_or_review_states",
        "rejection_edge_states",
    ):
        values = evidence.get(key)
        selected = _compact_usage_list(
            values,
            limit=SKILL_EVIDENCE_STATE_LIST_LIMIT,
            text_limit=80,
        )
        if selected:
            compact[key] = selected
            if isinstance(values, list) and len(values) > len(selected):
                compact[f"omitted_{key}_count"] = len(values) - len(selected)
    for key in (
        "state_counts",
        "association_state_counts",
        "dimensions",
        "correlation_rejections",
    ):
        value = _compact_usage_mapping(evidence.get(key), text_limit=120)
        if value:
            compact[key] = _without_omitted_field_counts(value)
    task_episode_refs = evidence.get("task_episode_refs")
    if isinstance(task_episode_refs, list):
        valid_task_episode_refs: list[dict[str, Any]] = []
        for ref in task_episode_refs:
            item = _compact_usage_mapping(
                ref,
                allowed_keys=("session_id", "session_label", "task_episode_id"),
                text_limit=120,
            )
            item = _without_omitted_field_counts(item)
            if item.get("task_episode_id") and (item.get("session_id") or item.get("session_label")):
                valid_task_episode_refs.append(item)
        selected_task_episode_refs = valid_task_episode_refs[:ENTITY_USAGE_ACTION_LIMIT]
        if selected_task_episode_refs:
            compact["task_episode_refs"] = selected_task_episode_refs
        source_ref_count = evidence.get("task_episode_ref_count")
        nonnegative_source_ref_count = (
            max(0, int(source_ref_count))
            if isinstance(source_ref_count, int) and not isinstance(source_ref_count, bool)
            else 0
        )
        total_ref_count = max(nonnegative_source_ref_count, len(task_episode_refs))
        compact["task_episode_ref_count"] = total_ref_count
        omitted_ref_count = max(0, total_ref_count - len(selected_task_episode_refs))
        if omitted_ref_count:
            compact["omitted_task_episode_ref_count"] = omitted_ref_count
        compact["task_episode_refs_truncated"] = bool(
            evidence.get("task_episode_refs_truncated")
        ) or omitted_ref_count > 0
    elif isinstance(evidence.get("task_episode_refs_truncated"), bool):
        compact["task_episode_refs_truncated"] = evidence["task_episode_refs_truncated"]
    return compact


def _usage_action_semantic_sort_key(action: str) -> tuple[int, int, str]:
    try:
        return (0, ENTITY_USAGE_ACTION_SEMANTIC_PRIORITY.index(action), action)
    except ValueError:
        pass
    try:
        return (2, ENTITY_USAGE_WEAK_ACTION_PRIORITY.index(action), action)
    except ValueError:
        return (1, 0, action)


def _compact_usage_action_counts(value: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(value, dict):
        return {}, 0
    compact: dict[str, Any] = {}
    valid_items: list[tuple[str, str, Any]] = []
    for key, count in value.items():
        action = _bounded_string(key, 80)
        if not action or not isinstance(count, (bool, int, float)):
            continue
        valid_items.append((action, str(key), count))
    unique_items: list[tuple[str, Any]] = []
    seen_actions: set[str] = set()
    for action, _raw_key, count in sorted(
        valid_items,
        key=lambda item: (*_usage_action_semantic_sort_key(item[0]), item[1]),
    ):
        if action in seen_actions:
            continue
        seen_actions.add(action)
        unique_items.append((action, count))
    for action, count in unique_items[:ENTITY_USAGE_ACTION_LIMIT]:
        compact[action] = count
    return compact, max(0, len(valid_items) - len(compact))


def _compact_usage_action_samples(
    value: Any,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int], int]:
    if not isinstance(value, dict):
        return {}, {}, 0
    compact: dict[str, list[dict[str, Any]]] = {}
    omitted: dict[str, int] = {}
    valid_items: list[tuple[str, str, list[Any]]] = []
    for key, samples in value.items():
        if not isinstance(samples, list):
            continue
        action = _bounded_string(key, 80)
        if not action:
            continue
        valid_items.append((action, str(key), samples))
    unique_items: list[tuple[str, list[Any]]] = []
    seen_actions: set[str] = set()
    for action, _raw_key, samples in sorted(
        valid_items,
        key=lambda item: (*_usage_action_semantic_sort_key(item[0]), item[1]),
    ):
        if action in seen_actions:
            continue
        seen_actions.add(action)
        unique_items.append((action, samples))
    retained_items = unique_items[:ENTITY_USAGE_ACTION_LIMIT]
    for action, samples in retained_items:
        selected: list[dict[str, Any]] = []
        for sample in samples[:ENTITY_USAGE_ACTION_SAMPLE_LIMIT]:
            if not isinstance(sample, dict):
                continue
            item = _compact_usage_mapping(
                sample,
                allowed_keys=(
                    "role",
                    "event_type",
                    "session_id",
                    "session_label",
                    "event_id",
                    "title",
                ),
            )
            refs = _compact_usage_refs(sample.get("refs"))
            if refs:
                item["refs"] = refs
            item = _without_omitted_field_counts(item)
            if item:
                selected.append(item)
        if selected:
            compact[action] = selected
        if len(samples) > len(selected):
            omitted[action] = len(samples) - len(selected)
    return compact, omitted, max(0, len(valid_items) - len(retained_items))


def _compact_graph_freshness(freshness: Any) -> dict[str, Any]:
    if not isinstance(freshness, dict):
        return {}
    compact = {
        key: freshness.get(key)
        for key in (
            "status",
            "checked",
            "read_model",
            "warning",
            "graph_source",
            "graph_generated_at",
            "search_index_generated_at",
            "basis",
            "live_verification",
            "target_dirty",
            "target_deferred_live",
            "hot_gate_status",
            "needs_maintenance",
            "needs_full_rebuild",
            "actionable_graph_source_count",
            "actionable_count",
            "deferred_live_source_count",
            "ledger_store_missing_count",
            "latest_maintenance_remaining_count",
            "blocked_source_count",
        )
        if freshness.get(key) not in (None, "", [], {})
    }
    for key in ("diagnostics", "hot_gate_diagnostics"):
        diagnostics = _compact_usage_list(freshness.get(key), limit=4, text_limit=GRAPH_ITEM_TEXT_PREVIEW_CHARS)
        if diagnostics:
            compact[key] = diagnostics
            source_len = len(freshness.get(key)) if isinstance(freshness.get(key), list) else 0
            if source_len > len(diagnostics):
                compact[f"omitted_{key}_count"] = source_len - len(diagnostics)
    recommendation = _compact_usage_mapping(
        freshness.get("maintenance_recommendation"),
        allowed_keys=(
            "route",
            "reason",
            "source_count",
            "existing_source_count",
            "actionable_count",
            "deferred_live_source_count",
            "blocked_count",
            "dominant_reason",
            "command",
            "notes",
        ),
        text_limit=220,
    )
    if recommendation:
        compact["maintenance_recommendation"] = _without_omitted_field_counts(recommendation)
    return compact


def _compact_graph_ref(ref: Any) -> dict[str, Any]:
    if not isinstance(ref, dict):
        scalar = _compact_usage_scalar(ref, limit=GRAPH_ITEM_TEXT_PREVIEW_CHARS)
        return {"ref": scalar} if scalar not in (None, "", [], {}) else {}
    compact = _compact_usage_mapping(
        ref,
        allowed_keys=(
            "session_id",
            "session_label",
            "segment_id",
            "event_id",
            "node_id",
            "edge_id",
            "line",
            "source",
            "target",
            "type",
            "raw",
            "raw_ref",
            "segment",
            "segment_ref",
            "session",
            "graph",
            "graph_ref",
            "refs",
        ),
        text_limit=GRAPH_ITEM_TEXT_PREVIEW_CHARS,
    )
    refs = _compact_usage_refs(ref.get("refs"))
    if refs:
        compact["refs"] = refs
    return _without_omitted_field_counts(compact)


def _graph_ref_dedupe_key(ref: dict[str, Any]) -> str:
    keys = (
        "session_id",
        "session_label",
        "segment_id",
        "event_id",
        "node_id",
        "edge_id",
        "line",
        "source",
        "target",
        "type",
        "raw",
        "raw_ref",
        "segment",
        "segment_ref",
        "session",
        "graph",
        "graph_ref",
    )
    parts: list[str] = []
    for key in keys:
        value = ref.get(key)
        if value not in (None, "", [], {}):
            parts.append(f"{key}={value}")
    refs = ref.get("refs")
    if isinstance(refs, dict):
        for key in ("raw", "raw_ref", "segment", "segment_ref", "session", "graph", "graph_ref"):
            value = refs.get(key)
            if value not in (None, "", [], {}):
                parts.append(f"refs.{key}={value}")
    if parts:
        return "|".join(parts)
    return json.dumps(ref, sort_keys=True, ensure_ascii=True, default=str)


def _compact_graph_refs(refs: Any, *, limit: int = GRAPH_EVIDENCE_REF_SAMPLE_LIMIT) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not isinstance(refs, list):
        return [], {"evidence_ref_count": 0, "omitted_evidence_ref_count": 0, "deduplicated_evidence_ref_count": 0}
    compact_refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_count = 0
    for ref in refs:
        compact = _compact_graph_ref(ref)
        if not compact:
            continue
        key = _graph_ref_dedupe_key(compact)
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        compact_refs.append(compact)
    selected = compact_refs[:limit]
    return selected, {
        "evidence_ref_count": len(refs),
        "unique_evidence_ref_count": len(compact_refs),
        "omitted_evidence_ref_count": max(0, len(compact_refs) - len(selected)),
        "deduplicated_evidence_ref_count": duplicate_count,
    }


def _compact_graph_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        scalar = _compact_usage_scalar(item, limit=GRAPH_ITEM_TEXT_PREVIEW_CHARS)
        return {"value": scalar} if scalar not in (None, "", [], {}) else {}
    compact = _compact_usage_mapping(
        item,
        allowed_keys=(
            "id",
            "type",
            "label",
            "title",
            "source",
            "target",
            "kind",
            "anchor",
            "canonical_key",
            "route_layer",
            "route_signal",
            "route_signals",
            "matched_routes",
            "session_id",
            "session_label",
            "session_title",
            "session_date",
            "segment_id",
            "event_id",
            "event_type",
            "source_type",
            "role",
            "family",
            "phase",
            "actor",
            "action",
            "object",
            "outcome",
            "conversation_act",
            "session_act",
            "agent_event",
            "task_episode_id",
            "timestamp",
            "line",
            "relation",
            "offset",
            "correlation_id",
            "status",
            "confidence",
            "count",
            "weight",
            "refs",
            "freshness",
            "route_signal_count",
            "registered_entity_edge_count",
            "route_signal_edge_count",
        ),
        text_limit=GRAPH_ITEM_TEXT_PREVIEW_CHARS,
    )
    refs = _compact_usage_refs(item.get("refs"))
    if refs:
        compact["refs"] = refs
    evidence_refs, ref_meta = _compact_graph_refs(item.get("evidence_refs"), limit=1)
    if evidence_refs:
        compact["evidence_ref_count"] = ref_meta["evidence_ref_count"]
        if "refs" not in compact:
            compact["refs"] = evidence_refs[0].get("refs") or evidence_refs[0]
    if isinstance(item.get("freshness"), dict):
        compact["freshness"] = _compact_graph_freshness(item.get("freshness"))
    compact = _without_omitted_field_counts(compact)
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _compact_graph_sequence(items: Any, *, limit: int) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(items, list):
        return [], 0
    selected = [_compact_graph_item(item) for item in items[:limit]]
    compact = [item for item in selected if item]
    return compact, max(0, len(items) - len(compact))


def _compact_graph_payload(
    payload: dict[str, Any],
    *,
    full_route: str,
    event_limit: int | None = None,
    node_limit: int = GRAPH_NODE_SAMPLE_LIMIT,
    edge_limit: int = GRAPH_EDGE_SAMPLE_LIMIT,
) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    passthrough_keys = (
        "schema_version",
        "artifact_type",
        "generated_at",
        "ok",
        "mutates",
        "anchor",
        "kind",
        "requested_kind",
        "source",
        "target",
        "source_anchor",
        "target_anchor",
        "max_depth",
        "depth",
        "path_found",
        "distance",
        "node_count",
        "edge_count",
        "event_count",
        "cooccurrence_count",
        "truncated",
        "next_command",
        "next_expansion_command",
        "next_expansion_reason",
        "quality",
        "freshness",
        "provider",
        "parameters",
        "diagnostics",
    )
    for key in passthrough_keys:
        if payload.get(key) not in (None, "", [], {}):
            compact[key] = payload.get(key)
    if isinstance(payload.get("freshness"), dict):
        compact["freshness"] = _compact_graph_freshness(payload.get("freshness"))
    if isinstance(payload.get("provider"), dict):
        compact["provider"] = _compact_usage_provider_status(payload["provider"])

    effective_event_limit = _coerce_limit(event_limit, GRAPH_EVENT_SAMPLE_LIMIT, GRAPH_EVENT_SAMPLE_LIMIT)
    nodes, omitted_nodes = _compact_graph_sequence(payload.get("nodes"), limit=node_limit)
    if nodes:
        compact["nodes"] = nodes
        compact["node_count"] = payload.get("node_count", len(payload.get("nodes", [])))
        compact["omitted_node_count"] = max(omitted_nodes, int(payload.get("omitted_node_count") or 0))
    edges, omitted_edges = _compact_graph_sequence(payload.get("edges"), limit=edge_limit)
    if edges:
        compact["edges"] = edges
        compact["edge_count"] = payload.get("edge_count", len(payload.get("edges", [])))
        compact["omitted_edge_count"] = max(omitted_edges, int(payload.get("omitted_edge_count") or 0))
    events, omitted_events = _compact_graph_sequence(payload.get("events"), limit=effective_event_limit)
    if events:
        compact["events"] = events
        compact["event_count"] = payload.get("event_count", len(payload.get("events", [])))
        compact["omitted_event_count"] = omitted_events
    cooccurrences = payload.get("cooccurrences")
    if isinstance(cooccurrences, list):
        selected = [_compact_usage_mapping(item, text_limit=GRAPH_ITEM_TEXT_PREVIEW_CHARS) for item in cooccurrences[:node_limit]]
        compact["cooccurrences"] = [item for item in selected if item]
        compact["cooccurrence_count"] = payload.get("cooccurrence_count", len(cooccurrences))
        compact["omitted_cooccurrence_count"] = max(0, len(cooccurrences) - len(compact["cooccurrences"]))

    evidence_refs, ref_meta = _compact_graph_refs(payload.get("evidence_refs"), limit=GRAPH_EVIDENCE_REF_SAMPLE_LIMIT)
    if evidence_refs:
        compact["evidence_refs"] = evidence_refs
    for key, value in ref_meta.items():
        if value:
            compact[key] = value

    mcp_access = dict(payload.get("mcp_access")) if isinstance(payload.get("mcp_access"), dict) else {}
    mcp_access.update(
        {
            "response_compacted": True,
            "full_graph_route": full_route,
            "authority_boundary": "MCP returns compact graph topology and refs; raw/segment evidence remains authoritative.",
        }
    )
    compact["mcp_access"] = mcp_access
    compact["mcp_payload_policy"] = {
        "response_compacted": True,
        "node_sample_limit": node_limit,
        "edge_sample_limit": edge_limit,
        "event_sample_limit": effective_event_limit,
        "evidence_ref_sample_limit": GRAPH_EVIDENCE_REF_SAMPLE_LIMIT,
        "text_preview_chars": GRAPH_ITEM_TEXT_PREVIEW_CHARS,
        "full_graph_route": full_route,
    }
    compact["authority_boundary"] = "MCP returns compact graph topology and refs; raw/segment evidence remains authoritative."
    return compact


def _compact_graph_bridge_payload(payload: dict[str, Any], *, full_route: str) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in (
        "schema_version",
        "artifact_type",
        "generated_at",
        "ok",
        "mutates",
        "source",
        "source_anchor",
        "target_anchor",
        "kind",
        "requested_kind",
        "source_kind",
        "target_kind",
        "max_depth",
        "parameters",
        "truth_status",
        "next_route",
        "next_command",
        "next_expansion_command",
        "next_expansion_reason",
        "quality",
        "freshness",
        "noise_flags",
        "diagnostics",
    ):
        if payload.get(key) not in (None, "", [], {}):
            compact[key] = payload.get(key)
    if isinstance(payload.get("freshness"), dict):
        compact["freshness"] = _compact_graph_freshness(payload.get("freshness"))
    if isinstance(payload.get("normalized_entities"), dict):
        compact["normalized_entities"] = payload["normalized_entities"]

    bridge = payload.get("bridge") if isinstance(payload.get("bridge"), dict) else {}
    if bridge:
        bridge_nodes, omitted_bridge_nodes = _compact_graph_sequence(bridge.get("nodes"), limit=GRAPH_NODE_SAMPLE_LIMIT)
        bridge_edges, omitted_bridge_edges = _compact_graph_sequence(bridge.get("edges"), limit=GRAPH_EDGE_SAMPLE_LIMIT)
        bridge_refs, bridge_ref_meta = _compact_graph_refs(bridge.get("evidence_refs"), limit=GRAPH_EVIDENCE_REF_SAMPLE_LIMIT)
        compact["bridge"] = {
            key: bridge.get(key)
            for key in ("path_found", "path_length", "max_depth", "next_expansion_command")
            if bridge.get(key) not in (None, "", [], {})
        }
        if bridge_nodes:
            compact["bridge"]["nodes"] = bridge_nodes
            compact["bridge"]["omitted_node_count"] = omitted_bridge_nodes
        if bridge_edges:
            compact["bridge"]["edges"] = bridge_edges
            compact["bridge"]["omitted_edge_count"] = omitted_bridge_edges
        if bridge_refs:
            compact["bridge"]["evidence_refs"] = bridge_refs
        if bridge_ref_meta.get("evidence_ref_count"):
            compact["bridge"]["evidence_ref_count"] = bridge_ref_meta["evidence_ref_count"]

    usage_chain = payload.get("usage_chain") if isinstance(payload.get("usage_chain"), dict) else {}
    if usage_chain:
        source_events, omitted_source_events = _compact_graph_sequence(usage_chain.get("source_events"), limit=GRAPH_EVENT_SAMPLE_LIMIT)
        target_events, omitted_target_events = _compact_graph_sequence(usage_chain.get("target_events"), limit=GRAPH_EVENT_SAMPLE_LIMIT)
        compact["usage_chain"] = {
            "source_event_count": usage_chain.get("source_event_count"),
            "target_event_count": usage_chain.get("target_event_count"),
        }
        if source_events:
            compact["usage_chain"]["source_events"] = source_events
            compact["usage_chain"]["omitted_source_event_count"] = omitted_source_events
        if target_events:
            compact["usage_chain"]["target_events"] = target_events
            compact["usage_chain"]["omitted_target_event_count"] = omitted_target_events

    evidence_refs, ref_meta = _compact_graph_refs(payload.get("evidence_refs"), limit=GRAPH_EVIDENCE_REF_SAMPLE_LIMIT)
    if evidence_refs:
        compact["evidence_refs"] = evidence_refs
    for key, value in ref_meta.items():
        if value:
            compact[key] = value

    mcp_access = dict(payload.get("mcp_access")) if isinstance(payload.get("mcp_access"), dict) else {}
    mcp_access.update(
        {
            "response_compacted": True,
            "full_graph_route": full_route,
            "authority_boundary": "MCP returns compact graph bridge refs; raw/segment evidence remains authoritative.",
        }
    )
    compact["mcp_access"] = mcp_access
    compact["mcp_payload_policy"] = {
        "response_compacted": True,
        "node_sample_limit": GRAPH_NODE_SAMPLE_LIMIT,
        "edge_sample_limit": GRAPH_EDGE_SAMPLE_LIMIT,
        "event_sample_limit": GRAPH_EVENT_SAMPLE_LIMIT,
        "evidence_ref_sample_limit": GRAPH_EVIDENCE_REF_SAMPLE_LIMIT,
        "text_preview_chars": GRAPH_ITEM_TEXT_PREVIEW_CHARS,
        "full_graph_route": full_route,
    }
    compact["authority_boundary"] = "MCP returns compact graph bridge topology and refs; raw/segment evidence remains authoritative."
    return compact


def _compact_usage_provider_status(provider: Any) -> dict[str, Any]:
    if not isinstance(provider, dict):
        return {}
    compact = {
        key: provider.get(key)
        for key in (
            "schema_version",
            "artifact_type",
            "ok",
            "status",
            "recommendation",
        )
        if provider.get(key) not in (None, "", [], {})
    }
    providers = provider.get("providers")
    if isinstance(providers, dict):
        compact_providers: dict[str, Any] = {}
        for name, value in providers.items():
            if not isinstance(value, dict):
                continue
            provider_summary = {
                key: value.get(key)
                for key in ("ok", "status", "source", "provider")
                if value.get(key) not in (None, "", [], {})
            }
            freshness = value.get("freshness")
            if isinstance(freshness, dict):
                provider_summary["freshness"] = {
                    key: freshness.get(key)
                    for key in (
                        "status",
                        "dirty_session_count",
                        "actionable_dirty_session_count",
                        "deferred_live_session_count",
                        "missing_session_count",
                    )
                    if freshness.get(key) not in (None, "", [], {})
                }
            if provider_summary:
                compact_providers[str(name)] = provider_summary
        if compact_providers:
            compact["providers"] = compact_providers
    return compact


def _compact_document_ref(ref: Any) -> dict[str, Any]:
    return _without_omitted_field_counts(
        _compact_usage_mapping(
            ref,
            allowed_keys=(
                "kind",
                "value",
                "path",
                "repo",
                "ref",
                "raw",
                "segment",
                "session",
                "route_signal",
                "canonical_key",
                "source_type",
                "title",
            ),
        )
    )


def _compact_raw_preview(preview: Any) -> dict[str, Any]:
    compact = _compact_usage_mapping(
        preview,
        allowed_keys=("status", "line", "path", "text", "reason"),
        text_limit=ENTITY_USAGE_TEXT_PREVIEW_CHARS,
    )
    if "text" in compact:
        compact["text_preview_chars"] = ENTITY_USAGE_TEXT_PREVIEW_CHARS
    return _without_omitted_field_counts(compact)


def _compact_usage_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        scalar = _compact_usage_scalar(event)
        return {"value": scalar} if scalar not in (None, "", [], {}) else {}
    compact = _compact_usage_mapping(
        event,
        allowed_keys=(
            "doc_id",
            "source",
            "source_doc_id",
            "distance",
            "event_id",
            "event_type",
            "source_type",
            "role",
            "family",
            "phase",
            "actor",
            "action",
            "conversation_act",
            "session_act",
            "agent_event",
            "task_episode_id",
            "title",
            "snippet",
            "session_id",
            "session_label",
            "session_title",
            "session_date",
            "segment_id",
            "route_layers",
            "route_signals",
            "matched_routes",
            "relation",
            "offset",
            "correlation_id",
            "source_correlation_id",
            "rejected_correlation_id",
            "status",
            "outcome",
            "skill_evidence_state",
            "usage_actions",
            "primary_usage_action",
            "route_signal_count",
            "route_signals_truncated",
            "matched_routes_truncated",
            "refs",
            "raw_preview",
            "document_refs",
        ),
    )
    usage_actions = _compact_usage_list(
        event.get("usage_actions"),
        limit=ENTITY_USAGE_ACTION_LIMIT,
        text_limit=80,
    )
    if usage_actions:
        compact["usage_actions"] = usage_actions
        source_usage_actions = event.get("usage_actions")
        if isinstance(source_usage_actions, list) and len(source_usage_actions) > len(usage_actions):
            compact["omitted_usage_action_count"] = len(source_usage_actions) - len(usage_actions)
    freshness = _compact_usage_freshness(event.get("freshness"))
    if freshness:
        compact["freshness"] = freshness
    refs = _compact_usage_refs(event.get("refs"))
    if refs:
        compact["refs"] = refs
    raw_preview = _compact_raw_preview(event.get("raw_preview"))
    if raw_preview:
        compact["raw_preview"] = raw_preview
    document_refs = event.get("document_refs")
    if isinstance(document_refs, list):
        selected = [_compact_document_ref(ref) for ref in document_refs[:ENTITY_USAGE_DOCUMENT_REF_SAMPLE_LIMIT]]
        compact["document_refs"] = [ref for ref in selected if ref]
        compact["document_ref_count"] = len(document_refs)
        compact["omitted_document_ref_count"] = max(0, len(document_refs) - len(compact["document_refs"]))
    compact = _without_omitted_field_counts(compact)
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _compact_usage_neighborhood(neighborhood: Any) -> dict[str, Any]:
    if not isinstance(neighborhood, dict):
        return _compact_usage_event(neighborhood)
    compact = _compact_usage_mapping(
        neighborhood,
        allowed_keys=("ok", "source", "quality", "refs"),
    )
    freshness = _compact_usage_freshness(neighborhood.get("freshness"))
    if freshness:
        compact["freshness"] = freshness
    if isinstance(neighborhood.get("source_usage_event"), dict):
        compact["source_usage_event"] = _compact_usage_event(neighborhood["source_usage_event"])
    for key in ("local_events", "consequence_events"):
        events = neighborhood.get(key)
        if isinstance(events, list):
            selected = [_compact_usage_event(event) for event in events[:ENTITY_USAGE_LOCAL_EVENT_SAMPLE_LIMIT]]
            compact[key] = [event for event in selected if event]
            compact[f"{key}_count"] = len(events)
            compact[f"omitted_{key}_count"] = max(0, len(events) - len(compact[key]))
    document_refs = neighborhood.get("document_refs")
    if isinstance(document_refs, list):
        selected_refs = [_compact_document_ref(ref) for ref in document_refs[:ENTITY_USAGE_DOCUMENT_REF_SAMPLE_LIMIT]]
        compact["document_refs"] = [ref for ref in selected_refs if ref]
        compact["document_ref_count"] = len(document_refs)
        compact["omitted_document_ref_count"] = max(0, len(document_refs) - len(compact["document_refs"]))
    compact = _without_omitted_field_counts(compact)
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _compact_entity_usage_audit_payload(payload: dict[str, Any], *, full_route: str) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    passthrough_keys = (
        "schema_version",
        "artifact_type",
        "generated_at",
        "ok",
        "mutates",
        "source",
        "truth_status",
        "anchor",
        "kind",
        "requested_kind",
        "session",
        "event_count",
        "entrypoint_event_count",
        "usage_event_count",
        "result_event_count",
        "outcome_event_count",
        "context_event_count",
        "consequence_event_count",
        "false_correlation_event_count",
        "false_correlation_edge_count",
        "unique_false_correlation_event_count",
        "document_ref_count",
        "quality",
        "diagnostics",
        "provider",
        "next_expansion_command",
        "next_expansion_reason",
    )
    for key in passthrough_keys:
        if payload.get(key) not in (None, "", [], {}):
            compact[key] = payload.get(key)
    if isinstance(payload.get("provider"), dict):
        compact["provider"] = _compact_usage_provider_status(payload["provider"])
    skill_evidence = _compact_skill_evidence(payload.get("skill_evidence"))
    if skill_evidence:
        compact["skill_evidence"] = skill_evidence
    for key, sample_limit in (
        ("entrypoint_events", ENTITY_USAGE_AUDIT_SAMPLE_LIMIT),
        ("usage_events", ENTITY_USAGE_AUDIT_SAMPLE_LIMIT),
        ("result_events", ENTITY_USAGE_CONSEQUENCE_SAMPLE_LIMIT),
        ("outcome_events", ENTITY_USAGE_CONSEQUENCE_SAMPLE_LIMIT),
        ("context_events", ENTITY_USAGE_CONSEQUENCE_SAMPLE_LIMIT),
        ("consequence_events", ENTITY_USAGE_CONSEQUENCE_SAMPLE_LIMIT),
        ("false_correlation_events", ENTITY_USAGE_CONSEQUENCE_SAMPLE_LIMIT),
    ):
        events = payload.get(key)
        if not isinstance(events, list):
            continue
        selected = [_compact_usage_event(event) for event in events[:sample_limit]]
        compact[key] = [event for event in selected if event]
        event_count_key = f"{key[:-1]}_count"
        compact[event_count_key] = payload.get(event_count_key, len(events))
        compact[f"omitted_{event_count_key}"] = max(0, len(events) - len(compact[key]))
    document_refs = payload.get("document_refs")
    if isinstance(document_refs, list):
        selected_refs = [_compact_document_ref(ref) for ref in document_refs[:ENTITY_USAGE_DOCUMENT_REF_SAMPLE_LIMIT]]
        compact["document_refs"] = [ref for ref in selected_refs if ref]
        compact["document_ref_count"] = payload.get("document_ref_count", len(document_refs))
        compact["omitted_document_ref_count"] = max(0, len(document_refs) - len(compact["document_refs"]))
    mcp_access = dict(payload.get("mcp_access")) if isinstance(payload.get("mcp_access"), dict) else {}
    mcp_access.update(
        {
            "response_compacted": True,
            "full_evidence_route": full_route,
            "authority_boundary": "MCP returns compact refs and samples; raw/segment evidence remains authoritative.",
        }
    )
    compact["mcp_access"] = mcp_access
    compact["mcp_payload_policy"] = {
        "response_compacted": True,
        "usage_event_sample_limit": ENTITY_USAGE_AUDIT_SAMPLE_LIMIT,
        "consequence_event_sample_limit": ENTITY_USAGE_CONSEQUENCE_SAMPLE_LIMIT,
        "false_correlation_event_sample_limit": ENTITY_USAGE_CONSEQUENCE_SAMPLE_LIMIT,
        "skill_evidence_state_list_limit": SKILL_EVIDENCE_STATE_LIST_LIMIT,
        "document_ref_sample_limit": ENTITY_USAGE_DOCUMENT_REF_SAMPLE_LIMIT,
        "text_preview_chars": ENTITY_USAGE_TEXT_PREVIEW_CHARS,
        "full_evidence_route": full_route,
    }
    compact["authority_boundary"] = "MCP returns compact refs and samples; raw/segment evidence remains authoritative."
    return compact


def _compact_entity_usage_chain_payload(payload: dict[str, Any], *, full_route: str) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    passthrough_keys = (
        "schema_version",
        "artifact_type",
        "generated_at",
        "ok",
        "mutates",
        "truth_status",
        "anchor",
        "kind",
        "requested_kind",
        "session",
        "normalized_entity",
        "counts",
        "quality",
        "freshness",
        "noise_flags",
        "next_expansion_command",
        "performance_contract",
        "diagnostics",
    )
    for key in passthrough_keys:
        if payload.get(key) not in (None, "", [], {}):
            compact[key] = payload.get(key)
    first_ref = _compact_first_ref(payload.get("first_ref"))
    if first_ref:
        compact["first_ref"] = first_ref
    skill_evidence = _compact_skill_evidence(payload.get("skill_evidence"))
    if skill_evidence:
        compact["skill_evidence"] = skill_evidence
    for key in ("usage_action_counts", "primary_usage_action_counts"):
        counts, omitted_count = _compact_usage_action_counts(payload.get(key))
        if counts:
            compact[key] = counts
        if omitted_count:
            compact[f"omitted_{key.removesuffix('_counts')}_count"] = omitted_count
    (
        usage_action_samples,
        omitted_action_samples,
        omitted_action_sample_buckets,
    ) = _compact_usage_action_samples(payload.get("usage_action_samples"))
    if usage_action_samples:
        compact["usage_action_samples"] = usage_action_samples
    if omitted_action_samples:
        compact["omitted_usage_action_sample_counts"] = omitted_action_samples
    if omitted_action_sample_buckets:
        compact["omitted_usage_action_sample_bucket_count"] = omitted_action_sample_buckets
    usage_chain = payload.get("usage_chain") if isinstance(payload.get("usage_chain"), dict) else {}
    compact_chain: dict[str, Any] = {}
    entrypoints = usage_chain.get("entrypoint_events")
    if isinstance(entrypoints, list):
        selected = [_compact_usage_event(event) for event in entrypoints[:ENTITY_USAGE_CHAIN_SAMPLE_LIMIT]]
        compact_chain["entrypoint_events"] = [event for event in selected if event]
        compact_chain["entrypoint_event_count"] = len(entrypoints)
        compact_chain["omitted_entrypoint_event_count"] = max(0, len(entrypoints) - len(compact_chain["entrypoint_events"]))
    chains = usage_chain.get("chains")
    if isinstance(chains, list):
        selected_chains: list[dict[str, Any]] = []
        for chain in chains[:ENTITY_USAGE_CHAIN_SAMPLE_LIMIT]:
            if not isinstance(chain, dict):
                continue
            compact_item: dict[str, Any] = {
                key: chain.get(key)
                for key in ("result_or_consequence_count", "has_result_or_consequence")
                if chain.get(key) not in (None, "", [], {})
            }
            if isinstance(chain.get("usage_event"), dict):
                compact_item["usage_event"] = _compact_usage_event(chain["usage_event"])
            result_events = chain.get("result_or_consequence_events")
            if isinstance(result_events, list):
                selected_results = [
                    _compact_usage_event(event)
                    for event in result_events[:ENTITY_USAGE_CHAIN_CONSEQUENCE_SAMPLE_LIMIT]
                ]
                compact_item["result_or_consequence_events"] = [event for event in selected_results if event]
                compact_item["omitted_result_or_consequence_event_count"] = max(
                    0,
                    len(result_events) - len(compact_item["result_or_consequence_events"]),
                )
            selected_chains.append(compact_item)
        compact_chain["chains"] = selected_chains
        compact_chain["chain_count"] = len(chains)
        compact_chain["omitted_chain_count"] = max(0, len(chains) - len(selected_chains))
    for key in (
        "unmatched_consequence_events",
        "result_events",
        "outcome_events",
        "false_correlation_events",
        "context_events",
    ):
        events = usage_chain.get(key)
        if isinstance(events, list):
            selected = [_compact_usage_event(event) for event in events[:ENTITY_USAGE_CHAIN_CONSEQUENCE_SAMPLE_LIMIT]]
            compact_chain[key] = [event for event in selected if event]
            if key == "false_correlation_events":
                compact_chain["false_correlation_event_count"] = len(events)
                compact_chain["omitted_false_correlation_event_count"] = max(
                    0,
                    len(events) - len(compact_chain[key]),
                )
            else:
                compact_chain[f"{key}_count"] = len(events)
                compact_chain[f"omitted_{key}_count"] = max(0, len(events) - len(compact_chain[key]))
    if compact_chain:
        compact["usage_chain"] = _without_omitted_field_counts(compact_chain)
    for key, limit in (
        ("document_refs", ENTITY_USAGE_DOCUMENT_REF_SAMPLE_LIMIT),
        ("evidence_refs", ENTITY_USAGE_CONSEQUENCE_SAMPLE_LIMIT),
        ("route_candidates", ENTITY_USAGE_DOCUMENT_REF_SAMPLE_LIMIT),
        ("sessions", ENTITY_USAGE_DOCUMENT_REF_SAMPLE_LIMIT),
    ):
        values = payload.get(key)
        if isinstance(values, list):
            selected = [_compact_usage_mapping(item) for item in values[:limit]]
            compact[key] = [_without_omitted_field_counts(item) for item in selected if item]
            compact[f"{key}_count"] = len(values)
            compact[f"omitted_{key}_count"] = max(0, len(values) - len(compact[key]))
    next_expansion = payload.get("next_expansion")
    if isinstance(next_expansion, list):
        selected = [_compact_usage_mapping(item, text_limit=160) for item in next_expansion[:4]]
        compact["next_expansion"] = [_without_omitted_field_counts(item) for item in selected if item]
        compact["next_expansion_count"] = len(next_expansion)
    mcp_access = dict(payload.get("mcp_access")) if isinstance(payload.get("mcp_access"), dict) else {}
    mcp_access.update(
        {
            "response_compacted": True,
            "full_evidence_route": full_route,
            "authority_boundary": "MCP returns compact usage-chain refs and samples; raw/segment evidence remains authoritative.",
        }
    )
    compact["mcp_access"] = mcp_access
    compact["mcp_payload_policy"] = {
        "response_compacted": True,
        "chain_sample_limit": ENTITY_USAGE_CHAIN_SAMPLE_LIMIT,
        "chain_consequence_sample_limit": ENTITY_USAGE_CHAIN_CONSEQUENCE_SAMPLE_LIMIT,
        "document_ref_sample_limit": ENTITY_USAGE_DOCUMENT_REF_SAMPLE_LIMIT,
        "evidence_ref_sample_limit": ENTITY_USAGE_CONSEQUENCE_SAMPLE_LIMIT,
        "false_correlation_event_sample_limit": ENTITY_USAGE_CHAIN_CONSEQUENCE_SAMPLE_LIMIT,
        "usage_action_bucket_limit": ENTITY_USAGE_ACTION_LIMIT,
        "usage_action_sample_limit_per_action": ENTITY_USAGE_ACTION_SAMPLE_LIMIT,
        "skill_evidence_state_list_limit": SKILL_EVIDENCE_STATE_LIST_LIMIT,
        "text_preview_chars": ENTITY_USAGE_TEXT_PREVIEW_CHARS,
        "full_evidence_route": full_route,
    }
    compact["authority_boundary"] = "MCP returns compact usage-chain refs and samples; raw/segment evidence remains authoritative."
    return compact


def _compact_entity_usage_neighborhood_payload(payload: dict[str, Any], *, full_route: str) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    passthrough_keys = (
        "schema_version",
        "artifact_type",
        "generated_at",
        "ok",
        "mutates",
        "anchor",
        "kind",
        "requested_kind",
        "session",
        "window_count",
        "quality",
        "route_attempts",
        "provider",
        "parameters",
        "diagnostics",
    )
    for key in passthrough_keys:
        if payload.get(key) not in (None, "", [], {}):
            compact[key] = payload.get(key)
    if isinstance(payload.get("provider"), dict):
        compact["provider"] = _compact_usage_provider_status(payload["provider"])
    neighborhoods = payload.get("neighborhoods")
    if isinstance(neighborhoods, list):
        selected = [
            _compact_usage_neighborhood(neighborhood)
            for neighborhood in neighborhoods[:ENTITY_USAGE_NEIGHBORHOOD_SAMPLE_LIMIT]
        ]
        compact["neighborhoods"] = [neighborhood for neighborhood in selected if neighborhood]
        compact["window_count"] = payload.get("window_count", len(neighborhoods))
        compact["omitted_neighborhood_count"] = max(0, len(neighborhoods) - len(compact["neighborhoods"]))
    mcp_access = dict(payload.get("mcp_access")) if isinstance(payload.get("mcp_access"), dict) else {}
    mcp_access.update(
        {
            "response_compacted": True,
            "full_evidence_route": full_route,
            "authority_boundary": "MCP returns compact refs and samples; raw/segment evidence remains authoritative.",
        }
    )
    compact["mcp_access"] = mcp_access
    compact["mcp_payload_policy"] = {
        "response_compacted": True,
        "neighborhood_sample_limit": ENTITY_USAGE_NEIGHBORHOOD_SAMPLE_LIMIT,
        "local_event_sample_limit": ENTITY_USAGE_LOCAL_EVENT_SAMPLE_LIMIT,
        "document_ref_sample_limit": ENTITY_USAGE_DOCUMENT_REF_SAMPLE_LIMIT,
        "text_preview_chars": ENTITY_USAGE_TEXT_PREVIEW_CHARS,
        "full_evidence_route": full_route,
    }
    compact["authority_boundary"] = "MCP returns compact refs and samples; raw/segment evidence remains authoritative."
    return compact


def _compact_entity_registry_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    compact = _compact_usage_mapping(
        entry,
        allowed_keys=(
            "entity_id",
            "kind",
            "canonical_key",
            "status",
            "route_layer",
            "route_signal",
            "owner",
            "source_surface",
            "source",
            "truth_status",
        ),
    )
    aliases = entry.get("aliases")
    if isinstance(aliases, list):
        compact["aliases"] = [str(item) for item in aliases[:5] if item not in (None, "")]
        compact["alias_count"] = len(aliases)
    source_refs = entry.get("source_refs")
    if isinstance(source_refs, list):
        selected_refs = [_compact_document_ref(ref) for ref in source_refs[:ENTITY_USAGE_DOCUMENT_REF_SAMPLE_LIMIT]]
        compact["source_refs"] = [ref for ref in selected_refs if ref]
        compact["source_ref_count"] = len(source_refs)
    return _without_omitted_field_counts({key: value for key, value in compact.items() if value not in (None, "", [], {})})


def _first_registry_entry(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return {}
    for entry in entries:
        compact = _compact_entity_registry_entry(entry)
        if compact:
            return compact
    return {}


def _payload_int(payload: Any, key: str, default: int = 0) -> int:
    if not isinstance(payload, dict):
        return default
    value = payload.get(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _direct_ref_bundle(item: dict[str, Any]) -> dict[str, Any]:
    bundle: dict[str, Any] = {}
    refs = _compact_usage_refs(item.get("refs"))
    if refs:
        bundle.update(refs)
    document_ref_targets = {
        "raw_line": "raw",
        "raw_block": "raw",
        "segment_markdown": "segment",
        "segment_index": "segment",
        "session_manifest": "session",
    }
    document_ref_target = document_ref_targets.get(str(item.get("kind") or ""))
    document_ref_value = item.get("value")
    if (
        document_ref_target
        and isinstance(document_ref_value, str)
        and document_ref_value
        and document_ref_target not in bundle
    ):
        bundle[document_ref_target] = document_ref_value
    aliases = (
        ("raw", "raw_ref"),
        ("raw", "raw"),
        ("segment", "segment_ref"),
        ("segment", "segment"),
        ("session", "session_ref"),
        ("session", "session"),
        ("graph", "graph_ref"),
        ("graph", "graph"),
    )
    for target, source in aliases:
        value = item.get(source)
        if isinstance(value, str) and value and target not in bundle:
            bundle[target] = value
    for key in ("session_id", "session_label", "segment_id", "event_id", "line", "kind", "value"):
        value = item.get(key)
        if value not in (None, "", [], {}):
            bundle[key] = value
    return _without_omitted_field_counts({key: value for key, value in bundle.items() if value not in (None, "", [], {})})


def _collect_evidence_refs(payloads: list[tuple[str, Any]], *, limit: int = ENTITY_DOSSIER_EVIDENCE_REF_LIMIT) -> dict[str, Any]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    evidence_first_keys = (
        "refs",
        "first_ref",
        "document_refs",
        "evidence_refs",
        "usage_events",
        "entrypoint_events",
        "result_events",
        "outcome_events",
        "consequence_events",
        "neighborhoods",
        "source_usage_event",
        "local_events",
    )

    def add_ref(source_packet: str, bundle: dict[str, Any]) -> None:
        if len(refs) >= limit:
            return
        if not bundle:
            return
        if not any(bundle.get(key) for key in ("raw", "raw_ref", "segment", "segment_ref", "session", "session_ref", "graph", "graph_ref")):
            return
        key = json.dumps(bundle, sort_keys=True, ensure_ascii=True, default=str)
        if key in seen:
            return
        seen.add(key)
        refs.append({"source_packet": source_packet, **bundle})

    for source_packet, payload in payloads:
        queue: deque[Any] = deque([payload])
        visited = 0
        while queue and len(refs) < limit and visited < 600:
            value = queue.popleft()
            visited += 1
            if isinstance(value, dict):
                add_ref(source_packet, _direct_ref_bundle(value))
                prioritized = [
                    value[key]
                    for key in evidence_first_keys
                    if key in value
                ]
                remaining = [
                    child
                    for key, child in value.items()
                    if key not in evidence_first_keys
                ]
                queue.extendleft(reversed(remaining))
                queue.extendleft(reversed(prioritized))
            elif isinstance(value, list):
                queue.extendleft(reversed(value))
    return {
        "refs": refs,
        "ref_count": len(refs),
        "raw_or_segment_ref_present": any(ref.get("raw") or ref.get("raw_ref") or ref.get("segment") or ref.get("segment_ref") for ref in refs),
        "truncated": len(refs) >= limit,
    }


def _compact_dossier_usage(payload: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: payload.get(key)
        for key in (
            "ok",
            "event_count",
            "entrypoint_event_count",
            "usage_event_count",
            "result_event_count",
            "outcome_event_count",
            "context_event_count",
            "consequence_event_count",
            "false_correlation_event_count",
            "false_correlation_edge_count",
            "unique_false_correlation_event_count",
            "document_ref_count",
            "quality",
            "provider",
            "diagnostics",
        )
        if payload.get(key) not in (None, "", [], {})
    }
    skill_evidence = _compact_skill_evidence(payload.get("skill_evidence"))
    if skill_evidence:
        compact["skill_evidence"] = skill_evidence
    for key in (
        "entrypoint_events",
        "usage_events",
        "result_events",
        "outcome_events",
        "context_events",
        "consequence_events",
        "false_correlation_events",
        "document_refs",
    ):
        if payload.get(key) not in (None, "", [], {}):
            compact[key] = payload.get(key)
    for key in tuple(payload):
        if key.startswith("omitted_") and key.endswith("_event_count"):
            compact[key] = payload[key]
    mcp_access = payload.get("mcp_access") if isinstance(payload.get("mcp_access"), dict) else {}
    for key in ("full_evidence_route", "response_compacted"):
        if mcp_access.get(key) not in (None, "", [], {}):
            compact[key] = mcp_access.get(key)
    return _without_omitted_field_counts(compact)


def _compact_dossier_neighborhood(payload: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: payload.get(key)
        for key in ("ok", "window_count", "quality", "provider", "parameters", "diagnostics", "neighborhoods")
        if payload.get(key) not in (None, "", [], {})
    }
    mcp_access = payload.get("mcp_access") if isinstance(payload.get("mcp_access"), dict) else {}
    for key in (
        "full_evidence_route",
        "next_expansion_command",
        "response_compacted",
        "fallback_reason",
        "selected_route_signal",
    ):
        if mcp_access.get(key) not in (None, "", [], {}):
            compact[key] = mcp_access.get(key)
    return _without_omitted_field_counts(compact)


def _compact_dossier_graph(payload: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: payload.get(key)
        for key in (
            "ok",
            "source",
            "node_count",
            "edge_count",
            "truncated",
            "omitted_node_count",
            "omitted_edge_count",
            "nodes",
            "edges",
            "evidence_refs",
            "evidence_ref_count",
            "unique_evidence_ref_count",
            "omitted_evidence_ref_count",
            "quality",
            "freshness",
            "provider",
            "next_expansion_command",
            "next_expansion_reason",
            "diagnostics",
        )
        if payload.get(key) not in (None, "", [], {})
    }
    mcp_access = payload.get("mcp_access") if isinstance(payload.get("mcp_access"), dict) else {}
    for key in (
        "full_graph_route",
        "response_compacted",
        "read_model",
        "deep_archive_fallback_executed",
        "deep_archive_fallback_deferred",
    ):
        if mcp_access.get(key) not in (None, "", [], {}):
            compact[key] = mcp_access.get(key)
    return _without_omitted_field_counts(compact)


def _compact_diagnostic(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "diagnostic": "unreadable"}
    remaining = payload.get("remaining")
    if isinstance(remaining, list):
        remaining_summary = [
            {"id": item.get("id"), "title": item.get("title"), "missing_layers": item.get("missing_layers", [])}
            for item in remaining[:8]
            if isinstance(item, dict)
        ]
    else:
        remaining_summary = []
    return {
        "schema_version": payload.get("schema_version"),
        "artifact_type": payload.get("artifact_type"),
        "generated_at": payload.get("generated_at"),
        "ok": payload.get("ok"),
        "target": payload.get("target"),
        "selected_count": payload.get("selected_count"),
        "covered_requirement_count": payload.get("covered_requirement_count"),
        "required_requirement_count": payload.get("required_requirement_count"),
        "diagnostics": payload.get("diagnostics", []),
        "remaining": remaining_summary,
    }


def _compact_dirty_session_sample(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"session_id": str(item)}
    keys = (
        "session_id",
        "session_label",
        "session_dir",
        "status",
        "reason",
        "reasons",
        "dirty_reasons",
        "stale_reasons",
        "source_fingerprint_changed",
        "route_signal_classifier_version_changed",
        "updated_at",
        "index_generated_at",
    )
    return {key: item.get(key) for key in keys if key in item}


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _compact_provider_freshness_for_mcp(freshness: dict[str, Any], *, sample_limit: int) -> dict[str, Any]:
    keys = (
        "status",
        "checked",
        "scope",
        "selected_session_state_count",
        "indexed_session_state_count",
        "dirty_session_count",
        "actionable_dirty_session_count",
        "deferred_live_session_count",
        "current_session_count",
        "indexed_session_count",
        "missing_session_count",
        "stale_session_count",
        "live_defer_quiet_seconds",
        "latest_source_mtime",
        "db_mtime",
        "reason",
        "reasons",
        "diagnostics",
    )
    compact = {key: freshness.get(key) for key in keys if key in freshness}
    dirty_sessions = freshness.get("dirty_sessions")
    dirty_ids = freshness.get("dirty_session_ids")
    samples: list[dict[str, Any]] = []
    if isinstance(dirty_sessions, list):
        samples.extend(_compact_dirty_session_sample(item) for item in dirty_sessions[:sample_limit])
    elif isinstance(dirty_ids, list):
        samples.extend({"session_id": str(item)} for item in dirty_ids[:sample_limit])

    if samples:
        dirty_count = _safe_int(freshness.get("dirty_session_count"))
        if dirty_count is None:
            dirty_count = len(dirty_sessions) if isinstance(dirty_sessions, list) else len(samples)
        compact["dirty_session_samples"] = samples
        compact["dirty_session_sample_count"] = len(samples)
        compact["omitted_dirty_session_count"] = max(0, dirty_count - len(samples))
    deferred_live_sessions = freshness.get("deferred_live_sessions")
    if isinstance(deferred_live_sessions, list):
        deferred_samples = [_compact_dirty_session_sample(item) for item in deferred_live_sessions[:sample_limit]]
        if deferred_samples:
            deferred_count = _safe_int(freshness.get("deferred_live_session_count"))
            if deferred_count is None:
                deferred_count = len(deferred_live_sessions)
            compact["deferred_live_session_samples"] = deferred_samples
            compact["deferred_live_session_sample_count"] = len(deferred_samples)
            compact["omitted_deferred_live_session_count"] = max(0, deferred_count - len(deferred_samples))
    if "dirty_session_ids" in freshness or "dirty_sessions" in freshness:
        omitted = ["dirty_session_ids", "dirty_sessions"]
        if "actionable_dirty_session_ids" in freshness:
            omitted.append("actionable_dirty_session_ids")
        if "actionable_dirty_sessions" in freshness:
            omitted.append("actionable_dirty_sessions")
        if "deferred_live_sessions" in freshness:
            omitted.append("deferred_live_sessions")
        compact["omitted_fields"] = omitted
    return compact


def _compact_provider_status_for_mcp(
    provider: dict[str, Any],
    *,
    full_freshness_route: str | None = None,
) -> dict[str, Any]:
    top_keys = (
        "schema_version",
        "artifact_type",
        "provider_schema_version",
        "generated_at",
        "ok",
        "aoa_root",
        "config_path",
        "default_provider",
        "authority_law",
        "selected_provider",
        "status_mode",
        "diagnostics",
    )
    provider_keys = (
        "provider",
        "ok",
        "status",
        "db_path",
        "index_generated_at",
        "search_schema_version",
        "expected_search_schema_version",
        "document_count",
        "route_index_count",
        "has_documents",
        "has_route_index",
        "has_route_terms",
        "count_mode",
        "diagnostics",
    )
    compact = {key: provider.get(key) for key in top_keys if key in provider}
    providers = provider.get("providers")
    if isinstance(providers, dict):
        compact_providers: dict[str, Any] = {}
        for name, value in providers.items():
            if not isinstance(value, dict):
                compact_providers[str(name)] = value
                continue
            compact_provider = {key: value.get(key) for key in provider_keys if key in value}
            freshness = value.get("freshness")
            if isinstance(freshness, dict):
                compact_provider["freshness"] = _compact_provider_freshness_for_mcp(
                    freshness,
                    sample_limit=PROVIDER_DIRTY_SESSION_SAMPLE_LIMIT,
                )
            compact_providers[str(name)] = compact_provider
        compact["providers"] = compact_providers

    mcp_access = provider.get("mcp_access")
    if isinstance(mcp_access, dict):
        compact["mcp_access"] = dict(mcp_access)
    else:
        compact["mcp_access"] = {
            "mutates": False,
            "archive_command": "search-provider-status",
            "authority_boundary": "MCP output routes to .aoa refs; it is not reviewed truth.",
        }
    compact["mcp_access"]["response_compacted"] = True
    compact["mcp_access"]["omitted_fields"] = [
        "providers.*.freshness.dirty_session_ids",
        "providers.*.freshness.dirty_sessions",
        "providers.*.freshness.actionable_dirty_session_ids",
        "providers.*.freshness.actionable_dirty_sessions",
        "providers.*.freshness.deferred_live_sessions",
    ]
    if full_freshness_route is not None:
        compact["mcp_access"]["full_freshness_route"] = full_freshness_route
    return compact


def _session_provider_status_allows_global_fallback(provider: dict[str, Any]) -> bool:
    mcp_access = provider.get("mcp_access")
    if isinstance(mcp_access, dict):
        if mcp_access.get("returncode") == 124:
            return True
        stderr = str(mcp_access.get("stderr") or "").lower()
        if "timed out" in stderr or "timeout" in stderr or "unavailable" in stderr:
            return True

    values: list[str] = []
    for key in ("status", "reason"):
        value = provider.get(key)
        if isinstance(value, str):
            values.append(value)
    diagnostics = provider.get("diagnostics")
    if isinstance(diagnostics, list):
        values.extend(str(item) for item in diagnostics if isinstance(item, (str, int, float)))
    providers = provider.get("providers")
    if isinstance(providers, dict):
        for item in providers.values():
            if not isinstance(item, dict):
                continue
            for key in ("status", "reason"):
                value = item.get(key)
                if isinstance(value, str):
                    values.append(value)
            provider_diagnostics = item.get("diagnostics")
            if isinstance(provider_diagnostics, list):
                values.extend(str(entry) for entry in provider_diagnostics if isinstance(entry, (str, int, float)))

    haystack = " ".join(values).lower()
    return "timed out" in haystack or "timeout" in haystack or "unavailable" in haystack


@dataclass(slots=True)
class AoASessionMemoryMCPState:
    workspace_root: Path
    aoa_root: Path
    script_path: Path
    python_bin: str = "python3"
    command_runner: CommandRunner = _default_runner
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def discover(
        cls,
        workspace_root: str | Path | None = None,
        aoa_root: str | Path | None = None,
        script_path: str | Path | None = None,
        command_runner: CommandRunner | None = None,
        timeout_seconds: float | None = None,
        python_bin: str | None = None,
    ) -> "AoASessionMemoryMCPState":
        root = Path(
            workspace_root
            or os.environ.get("AOA_WORKSPACE_ROOT")
            or DEFAULT_WORKSPACE_ROOT
        ).expanduser().resolve()
        archive = Path(
            aoa_root
            or os.environ.get("AOA_SESSION_MEMORY_ROOT")
            or root / ".aoa"
        ).expanduser().resolve()
        script = Path(
            script_path
            or os.environ.get("AOA_SESSION_MEMORY_SCRIPT")
            or archive / "scripts" / "aoa_session_memory.py"
        ).expanduser().resolve()
        return cls(
            workspace_root=root,
            aoa_root=archive,
            script_path=script,
            python_bin=python_bin or os.environ.get("PYTHON") or "python3",
            command_runner=command_runner or _default_runner,
            timeout_seconds=float(timeout_seconds or os.environ.get("AOA_SESSION_MEMORY_MCP_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
        )

    def authority_boundary(self) -> dict[str, Any]:
        return {
            "schema": "aoa_session_memory_mcp_authority_boundary_v1",
            "mcp_role": "local read-only access plane over .aoa session evidence, search, atlas, and diagnostics",
            "service_owner": "abyss-stack owns the runnable MCP package only",
            "stronger_owners": [
                ".aoa raw transcript archive and generated indexes",
                ".aoa route-signal classifier, maps, search provider status, and diagnostics",
                "aoa-memo for durable reviewed memory",
                "owning source repositories for source truth",
                "operator intent and authorization",
            ],
            "source_hierarchy": [
                "raw transcript JSONL and raw source metadata",
                "session manifest and raw block ledger",
                "segment Markdown and segment indexes",
                "session.index.json, registry, atlas maps, search index, diagnostics",
                "MCP compact route/evidence packets",
            ],
            "exposure": "stdio-default; optional authenticated loopback streamable-http",
            "mutation_posture": "no write, no repair, no reindex, no relabel, no distillation, no promotion",
            "stop_lines": STOP_LINES,
        }

    def available_surfaces(self) -> dict[str, Any]:
        return {
            "schema": "aoa_session_memory_mcp_surface_catalog_v1",
            "mutates": False,
            "route_model": "anchor/query/intent -> route candidates -> evidence refs -> freshness/readiness -> next action",
            "tools": [
                "aoa_session_memory_status",
                "aoa_session_transport_preflight",
                "aoa_session_search",
                "aoa_session_agent_responses",
                "aoa_session_agent_closeouts",
                "aoa_session_agent_progress_updates",
                "aoa_session_agent_reasoning_windows",
                "aoa_session_task_episodes",
                "aoa_session_goal_lifecycles",
                "aoa_session_answer_neighborhood",
                "aoa_session_trace",
                "aoa_session_entity_dossier",
                "aoa_session_entity_usage_chain",
                "aoa_session_entity_usage_audit",
                "aoa_session_entity_usage_neighborhood",
                "aoa_session_entity_usage_scenario_audit",
                "aoa_session_route",
                "aoa_session_brief",
                "aoa_session_retrieve",
                "aoa_session_evidence_packet",
                "aoa_session_freshness_check",
                "aoa_session_pattern_scan",
                "aoa_session_entity_inventory",
                "aoa_session_entity_registry",
                "aoa_session_hook_receipts",
                "aoa_session_live_scenario_corpus_check",
                "aoa_session_live_scenario_corpus_inventory",
                "aoa_session_latest_diagnostics",
                "aoa_session_maintenance_status",
                "aoa_session_maintenance_plan",
                "aoa_session_projection_status",
                "aoa_session_graph_neighborhood",
                "aoa_session_graph_timeline",
                "aoa_session_graph_shortest_path",
                "aoa_session_graph_cooccurrence",
                "aoa_session_graphrag_packet",
                "aoa_session_explain_graph_packet",
                "aoa_session_graph_eval",
                "aoa_session_graph_quality_audit",
            ],
            "resources": [
                "aoa-session-memory://status",
                "aoa-session-memory://surfaces",
                "aoa-session-memory://provider/status",
                "aoa-session-memory://maintenance/status",
                "aoa-session-memory://projection/status",
                "aoa-session-memory://readiness/route-layer",
                "aoa-session-memory://diagnostics/latest/{kind}",
                "aoa-session-memory://entities/{layer}",
                "aoa-session-memory://entity-registry/{kind}",
                "aoa-session-memory://entity-lookup/{kind}/{anchor}",
                "aoa-session-memory://session/{session}/brief",
                "aoa-session-memory://session/{session}/manifest",
                "aoa-session-memory://session/{session}/index",
                "aoa-session-memory://session/{session}/rehydrate",
                "aoa-session-memory://route/{axis}/{key}",
                "aoa-session-memory://trace/{anchor}",
                "aoa-session-memory://hooks/receipts/{event_name}",
                "aoa-session-memory://graph/status",
                "aoa-session-memory://graph/neighborhood/{anchor}",
            ],
            "route_layers": ROUTE_LAYERS,
            "authority_boundary": self.authority_boundary(),
        }

    def runtime_identity(self) -> dict[str, Any]:
        current_core_sha256 = _file_sha256(MCP_CORE_SOURCE_PATH)
        current_server_sha256 = _file_sha256(MCP_SERVER_SOURCE_PATH)
        core_source_matches_loaded = bool(
            current_core_sha256
            and MCP_CORE_LOADED_SHA256
            and current_core_sha256 == MCP_CORE_LOADED_SHA256
        )
        server_source_matches_loaded = bool(
            current_server_sha256
            and MCP_SERVER_LOADED_SHA256
            and current_server_sha256 == MCP_SERVER_LOADED_SHA256
        )
        pid = os.getpid()
        process_started_at_epoch = _process_start_epoch(pid)
        server_source_mtime_epoch = _source_mtime_epoch(MCP_SERVER_SOURCE_PATH)
        process_started_before_server_source = bool(
            process_started_at_epoch is not None
            and server_source_mtime_epoch is not None
            and process_started_at_epoch < server_source_mtime_epoch
        )
        tool_schema_reload_required = (not server_source_matches_loaded) or process_started_before_server_source
        source_matches_loaded = core_source_matches_loaded and server_source_matches_loaded and not process_started_before_server_source
        return {
            "schema": "aoa_session_memory_mcp_runtime_identity_v1",
            "pid": pid,
            "process_started_at_epoch": process_started_at_epoch,
            "loaded_at_epoch": MCP_CORE_LOADED_AT_EPOCH,
            "loaded_core_path": MCP_CORE_SOURCE_PATH.as_posix(),
            "loaded_core_sha256": MCP_CORE_LOADED_SHA256,
            "current_core_sha256": current_core_sha256,
            "loaded_server_path": MCP_SERVER_SOURCE_PATH.as_posix(),
            "loaded_server_sha256": MCP_SERVER_LOADED_SHA256,
            "current_server_sha256": current_server_sha256,
            "server_source_mtime_epoch": server_source_mtime_epoch,
            "process_started_before_server_source": process_started_before_server_source,
            "core_source_matches_loaded": core_source_matches_loaded,
            "server_source_matches_loaded": server_source_matches_loaded,
            "source_matches_loaded": source_matches_loaded,
            "implementation_reload_required": not core_source_matches_loaded,
            "tool_schema_reload_required": tool_schema_reload_required,
            "reload_required": not source_matches_loaded,
            "reload_boundary": (
                "MCP core implementation can auto-reload for existing tools; restart the Codex MCP "
                "process when the tool list, schemas, import path, or server wrapper changes."
            ),
        }

    def session_mcp_transport_preflight(self, proc_root: Path = Path("/proc")) -> dict[str, Any]:
        package_root = MCP_CORE_SOURCE_PATH.parents[2]
        core_auto_reload_enabled = _core_auto_reload_enabled()
        restart_required_sources = [
            MCP_SERVER_SOURCE_PATH,
            package_root / "scripts" / "aoa_session_memory_mcp_server.py",
        ]
        if not core_auto_reload_enabled:
            restart_required_sources.append(MCP_CORE_SOURCE_PATH)
        restart_source_mtime = max((path.stat().st_mtime for path in restart_required_sources if path.exists()), default=0.0)
        core_auto_reload_source_mtime = _source_mtime_epoch(MCP_CORE_SOURCE_PATH) or 0.0
        config_path = _codex_config_path()
        config_mtime = config_path.stat().st_mtime if config_path.exists() else 0.0
        configured_server: dict[str, Any] = {"configured": False, "config_path": config_path.as_posix()}
        if config_path.exists():
            try:
                config = tomllib.loads(config_path.read_text(encoding="utf-8"))
                server = (config.get("mcp_servers") or {}).get("aoa_session_memory") or {}
                raw_url = server.get("url") if isinstance(server.get("url"), str) else ""
                try:
                    parsed_url = urlparse(raw_url) if raw_url else None
                    url_host = parsed_url.hostname if parsed_url is not None else None
                    url_port = parsed_url.port if parsed_url is not None else None
                    url_path = parsed_url.path if parsed_url is not None else ""
                except ValueError:
                    parsed_url = None
                    url_host = None
                    url_port = None
                    url_path = ""
                http_boundary_valid = bool(
                    parsed_url is not None
                    and parsed_url.scheme in {"http", "https"}
                    and url_host in {"127.0.0.1", "localhost", "::1"}
                    and url_path.rstrip("/") == "/mcp"
                    and parsed_url.username is None
                    and parsed_url.password is None
                    and not parsed_url.query
                    and not parsed_url.fragment
                )
                if parsed_url is not None and url_host is not None:
                    display_host = f"[{url_host}]" if ":" in url_host else url_host
                    display_url = f"{parsed_url.scheme}://{display_host}"
                    if url_port is not None:
                        display_url += f":{url_port}"
                    display_url += url_path
                else:
                    display_url = None
                transport = "streamable-http" if raw_url else "stdio"
                raw_bearer_env_var = server.get("bearer_token_env_var")
                bearer_configured = bool(
                    raw_url and raw_bearer_env_var == HTTP_BEARER_TOKEN_ENV_VAR
                )
                bearer_state = _http_bearer_auth_state()
                bearer_ready = bool(bearer_configured and bearer_state["ready"])
                configured = bool(server) and (
                    not raw_url or (http_boundary_valid and bearer_configured)
                )
                configured_server.update(
                    {
                        "configured": configured,
                        "transport": transport,
                        "url": display_url,
                        "loopback_boundary_valid": http_boundary_valid if raw_url else None,
                        "command": server.get("command"),
                        "args": server.get("args") if isinstance(server.get("args"), list) else [],
                        "cwd": server.get("cwd"),
                    }
                )
                if raw_url:
                    configured_server["authentication"] = {
                        "mode": "bearer_env",
                        "env_var": (
                            raw_bearer_env_var
                            if isinstance(raw_bearer_env_var, str)
                            else None
                        ),
                        "configured": bearer_configured,
                        "execution_context": bearer_state["execution_context"],
                        "environment": bearer_state["environment"],
                        "systemd_credential": bearer_state["systemd_credential"],
                        "sources_conflict": bearer_state["sources_conflict"],
                        "ready": bearer_ready,
                    }
                if raw_url and not http_boundary_valid:
                    configured_server["diagnostics"] = ["http_endpoint_must_be_loopback_mcp"]
                elif raw_url and raw_bearer_env_var is None:
                    configured_server["diagnostics"] = ["http_bearer_token_env_var_required"]
                elif raw_url and not bearer_configured:
                    configured_server["diagnostics"] = ["http_bearer_token_env_var_invalid"]
                elif raw_url and bearer_state["execution_context"] == "shared_http_owner" and bearer_state["sources_conflict"]:
                    configured_server["diagnostics"] = ["http_owner_credential_conflict"]
                elif raw_url and bearer_state["execution_context"] == "shared_http_owner" and not (
                    bearer_state["environment"]["available"]
                    or bearer_state["systemd_credential"]["available"]
                ):
                    configured_server["diagnostics"] = ["http_owner_credential_unavailable"]
                elif raw_url and bearer_state["execution_context"] == "shared_http_owner" and not bearer_state["ready"]:
                    configured_server["diagnostics"] = ["http_owner_credential_invalid"]
                elif raw_url and not bearer_state["environment"]["available"]:
                    configured_server["diagnostics"] = ["http_client_credential_unavailable"]
                elif raw_url and not bearer_state["environment"]["valid"]:
                    configured_server["diagnostics"] = ["http_client_credential_invalid"]
            except (OSError, tomllib.TOMLDecodeError) as exc:
                configured_server.update({"configured": False, "diagnostics": [f"config_read_error:{exc}"]})

        if not proc_root.is_dir():
            return {
                "schema": "aoa_session_memory_mcp_transport_preflight_v1",
                "ok": bool(
                    configured_server.get("configured")
                    and (
                        configured_server.get("transport") != "streamable-http"
                        or configured_server.get("authentication", {}).get("ready") is True
                    )
                ),
                "mutates": False,
                "configured_server": configured_server,
                "runtime": self.runtime_identity(),
                "codex_session": {"available": False, "reason": "procfs_unavailable"},
                "running_mcp_processes": {"available": False, "reason": "procfs_unavailable"},
                "direct_tool_transport_status": (
                    "http_auth_unavailable"
                    if configured_server.get("transport") == "streamable-http"
                    and configured_server.get("configured") is True
                    and configured_server.get("authentication", {}).get("ready") is not True
                    else "unknown"
                ),
                "next_action": (
                    _http_bearer_next_action(configured_server)
                    if configured_server.get("transport") == "streamable-http"
                    and configured_server.get("configured") is True
                    and configured_server.get("authentication", {}).get("ready") is not True
                    else "Use the configured transport's owner check before treating mcp__aoa_session_memory calls as proof."
                ),
                "authority_boundary": self.authority_boundary(),
            }

        boot_epoch = _linux_boot_epoch(proc_root)
        ancestor_pids: set[int] = set()
        parent = os.getpid()
        while parent:
            ancestor_pids.add(parent)
            next_parent = _proc_ppid(parent, proc_root=proc_root)
            if not next_parent or next_parent == parent:
                break
            parent = next_parent

        mcp_children_by_parent: dict[int, list[int]] = {}
        mcp_processes: list[dict[str, Any]] = []
        codex_processes: list[dict[str, Any]] = []
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            cmdline = _proc_cmdline(pid, proc_root=proc_root)
            if not cmdline:
                continue
            started_at_epoch = _process_start_epoch(pid, proc_root=proc_root, boot_epoch=boot_epoch)
            if _is_session_memory_mcp_server_cmdline(cmdline):
                ppid = _proc_ppid(pid, proc_root=proc_root)
                if ppid is not None:
                    mcp_children_by_parent.setdefault(ppid, []).append(pid)
                mcp_processes.append(
                    {
                        "pid": pid,
                        "ppid": ppid,
                        "cwd": _proc_cwd(pid, proc_root=proc_root),
                        "cmdline": cmdline,
                        "started_at_epoch": started_at_epoch,
                        "started_before_current_source": bool(
                            started_at_epoch is not None
                            and restart_source_mtime
                            and started_at_epoch < restart_source_mtime
                        ),
                        "started_before_core_auto_reload_source": bool(
                            started_at_epoch is not None
                            and core_auto_reload_source_mtime
                            and started_at_epoch < core_auto_reload_source_mtime
                        ),
                    }
                )
                continue
            joined = " ".join(cmdline)
            if "codex" not in joined or "resume" not in joined:
                continue
            codex_processes.append(
                {
                    "pid": pid,
                    "ppid": _proc_ppid(pid, proc_root=proc_root),
                    "cwd": _proc_cwd(pid, proc_root=proc_root),
                    "cmdline": cmdline,
                    "started_at_epoch": started_at_epoch,
                    "is_current_process_ancestor": pid in ancestor_pids,
                    "started_before_config": bool(started_at_epoch is not None and config_mtime and started_at_epoch < config_mtime),
                    "started_before_current_source": bool(
                        started_at_epoch is not None and restart_source_mtime and started_at_epoch < restart_source_mtime
                    ),
                    "started_before_core_auto_reload_source": bool(
                        started_at_epoch is not None
                        and core_auto_reload_source_mtime
                        and started_at_epoch < core_auto_reload_source_mtime
                    ),
                }
            )

        for process in codex_processes:
            child_pids = sorted(mcp_children_by_parent.get(process["pid"], []))
            process["aoa_session_memory_child_pids"] = child_pids
            process["has_aoa_session_memory_child"] = bool(child_pids)

        current_codex = [process for process in codex_processes if process["is_current_process_ancestor"]]
        current_predates_config = any(process["started_before_config"] for process in current_codex)
        current_predates_source = any(process["started_before_current_source"] for process in current_codex)
        current_has_mcp_child = any(process["has_aoa_session_memory_child"] for process in current_codex)
        mcp_process_by_pid = {process["pid"]: process for process in mcp_processes}
        current_mcp_child_processes = [
            mcp_process_by_pid[pid]
            for process in current_codex
            for pid in process.get("aoa_session_memory_child_pids", [])
            if pid in mcp_process_by_pid
        ]
        current_mcp_child_count = len(current_mcp_child_processes)
        current_stale_mcp_child_count = sum(
            1 for process in current_mcp_child_processes if process.get("started_before_current_source")
        )
        current_has_fresh_mcp_child = bool(
            current_mcp_child_processes and current_stale_mcp_child_count < current_mcp_child_count
        )
        configured = bool(configured_server.get("configured"))
        configured_transport = str(configured_server.get("transport") or "stdio")
        shared_http = configured_transport == "streamable-http"
        http_auth_ready = bool(
            configured_server.get("authentication", {}).get("ready")
        )
        config_reload_advisory = bool(
            current_codex
            and configured
            and not shared_http
            and current_predates_config
            and current_has_fresh_mcp_child
        )
        stale_mcp_process_count = sum(1 for process in mcp_processes if process["started_before_current_source"])
        fresh_mcp_process_count = len(mcp_processes) - stale_mcp_process_count
        if shared_http and not configured:
            direct_status = "invalid_http_config"
            live_transport_restart_advisory = False
            direct_ok = False
            next_action = "Keep aoa_session_memory on an authenticated local process route or a loopback-only /mcp URL."
        elif shared_http and not http_auth_ready:
            direct_status = "http_auth_unavailable"
            live_transport_restart_advisory = False
            direct_ok = False
            next_action = _http_bearer_next_action(configured_server)
        elif shared_http and not mcp_processes:
            direct_status = "shared_http_unavailable"
            live_transport_restart_advisory = True
            direct_ok = False
            next_action = (
                "Check or start the shared HTTP owner outside MCP, then retry; "
                "this read-only preflight does not mutate service lifecycle."
            )
        elif shared_http and not fresh_mcp_process_count:
            direct_status = "restart_required"
            live_transport_restart_advisory = True
            direct_ok = False
            next_action = (
                "Restart the shared HTTP owner after source/deployed parity, then retry "
                "mcp__aoa_session_memory before using its packet as current proof."
            )
        elif shared_http:
            direct_status = "attached_shared_http"
            live_transport_restart_advisory = False
            direct_ok = True
            next_action = (
                "Use mcp__aoa_session_memory tools; the loopback shared owner is intentionally "
                "external to the Codex process tree."
            )
        else:
            live_transport_restart_advisory = bool(
                current_codex
                and configured
                and not current_has_fresh_mcp_child
            )
            direct_ok = configured and not live_transport_restart_advisory
        if not shared_http and live_transport_restart_advisory:
            direct_status = "restart_required"
            next_action = (
                "Restart the Codex/MCP process before using mcp__aoa_session_memory; "
                "configured stdio may still be used as a source health proof."
            )
        elif not shared_http and configured and current_codex and current_has_fresh_mcp_child:
            direct_status = "attached"
            if config_reload_advisory:
                next_action = (
                    "Use mcp__aoa_session_memory tools; restart only if this task depends on newly changed "
                    "Codex MCP config rather than the attached live server."
                )
            else:
                next_action = "Use mcp__aoa_session_memory tools, then expand to raw/segment refs when claims matter."
        elif not shared_http and not current_codex:
            direct_status = "not_in_codex_process"
            next_action = "Use this as a CLI preflight; run configured stdio smoke for server proof or call MCP from a fresh Codex session."
        elif not shared_http:
            direct_status = "not_configured_or_not_spawned"
            next_action = "Check Codex MCP config and restart Codex before using direct mcp__aoa_session_memory calls."

        return {
            "schema": "aoa_session_memory_mcp_transport_preflight_v1",
            "ok": direct_ok,
            "mutates": False,
            "configured_server": configured_server,
            "runtime": self.runtime_identity(),
            "source_mtime_epoch": restart_source_mtime or None,
            "restart_required_source_mtime_epoch": restart_source_mtime or None,
            "core_auto_reload_enabled": core_auto_reload_enabled,
            "core_auto_reload_source_mtime_epoch": core_auto_reload_source_mtime or None,
            "config_mtime_epoch": config_mtime or None,
            "direct_tool_transport_status": direct_status,
            "live_transport_restart_advisory": live_transport_restart_advisory,
            "codex_session": {
                "available": True,
                "current_codex_process_count": len(current_codex),
                "current_session_predates_config": current_predates_config,
                "current_session_predates_current_source": current_predates_source,
                "current_session_has_aoa_session_memory_child": current_has_mcp_child,
                "current_session_mcp_child_count": current_mcp_child_count,
                "current_session_mcp_child_stale_count": current_stale_mcp_child_count,
                "current_session_has_fresh_aoa_session_memory_child": current_has_fresh_mcp_child,
                "config_reload_advisory": config_reload_advisory,
                "current_codex_processes": current_codex[:6],
                "processes": codex_processes[:12],
                "omitted_process_count": max(0, len(codex_processes) - 12),
            },
            "running_mcp_processes": {
                "available": True,
                "process_count": len(mcp_processes),
                "stale_process_count": stale_mcp_process_count,
                "fresh_process_count": fresh_mcp_process_count,
                "restart_advisory": bool(stale_mcp_process_count),
                "processes": mcp_processes[:12],
                "omitted_process_count": max(0, len(mcp_processes) - 12),
            },
            "configured_stdio_check_route": "python mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py",
            "configured_transport_check_route": (
                "systemctl --user status aoa-organ-mcp-read@aoa-session-memory.service"
                if shared_http
                else "python mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py"
            ),
            "next_action": next_action,
            "authority_boundary": self.authority_boundary(),
        }

    def _archive_command(
        self,
        command: str,
        args: list[str] | None = None,
        *,
        allow_nonzero_json: bool = False,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if command not in MCP_ARCHIVE_READ_COMMANDS:
            raise ValueError(
                f"archive command is not in the MCP read allowlist: {command}"
            )
        for argument in args or []:
            if any(
                argument.startswith(prefix)
                for prefix in MCP_ARCHIVE_FORBIDDEN_FLAG_PREFIXES
            ):
                raise ValueError(
                    f"persistent archive flag is forbidden through MCP: {argument}"
                )
        argv = self._archive_argv(command, args)
        effective_timeout = float(timeout_seconds if timeout_seconds is not None else self.timeout_seconds)
        output = self.command_runner(argv, effective_timeout)
        try:
            payload: Any = json.loads(output.stdout)
        except json.JSONDecodeError:
            payload = {
                "ok": False,
                "artifact_type": "aoa_session_memory_command_error",
                "diagnostics": ["command did not return JSON"],
                "stdout_preview": output.stdout[:1000],
            }
        if not isinstance(payload, dict):
            payload = {"ok": False, "payload": payload, "diagnostics": ["command returned non-object JSON"]}
        if output.returncode != 0 and not allow_nonzero_json:
            payload.setdefault("ok", False)
        payload["mcp_access"] = {
            "mutates": False,
            "archive_command": command,
            "returncode": output.returncode,
            "elapsed_ms": round(output.elapsed_ms, 2),
            "timeout_seconds": effective_timeout,
            "stderr": output.stderr.strip()[:1000],
            "authority_boundary": "MCP output routes to .aoa refs; it is not reviewed truth.",
        }
        return payload

    def _archive_argv(self, command: str, args: list[str] | None = None) -> list[str]:
        return [
            self.python_bin,
            self.script_path.as_posix(),
            command,
            *(args or []),
            "--workspace-root",
            self.workspace_root.as_posix(),
            "--aoa-root",
            self.aoa_root.as_posix(),
        ]

    def _archive_command_line(self, command: str, args: list[str] | None = None) -> str:
        return shlex.join(self._archive_argv(command, args))

    def _resource_admitted_archive_route(
        self,
        command: str,
        args: list[str],
        *,
        workload_class: str,
        activity: str = "foreground",
    ) -> dict[str, Any]:
        owner_command = self._archive_argv(command, args)
        demand_key = f"aoa-session-memory:{_route_key(command)}"
        latency = "interactive" if activity == "foreground" else "balanced"
        launch_argv = [
            "abyss-machine",
            "resource",
            "launch",
            "--class",
            workload_class,
            "--kind",
            "indexing",
            "--latency",
            latency,
            "--activity",
            activity,
            "--demand-key",
            demand_key,
            "--demand-owner",
            "aoa-session-memory",
            "--json",
            "--",
            *owner_command,
        ]
        return {
            "owner": "aoa-session-memory",
            "activity": activity,
            "importance_source": "owner_declared_request_context",
            "pressure_facts_assign_importance": False,
            "class": workload_class,
            "kind": "indexing",
            "latency": latency,
            "demand_key": demand_key,
            "demand_owner": "aoa-session-memory",
            "new_processes_only": True,
            "required_host_capability": {
                "command": "abyss-machine resource launch",
                "owner_activity_flag": "--activity",
                "activation_order": "host_capability_before_mcp_route",
            },
            "owner_command": shlex.join(owner_command),
            "launch_command": shlex.join(launch_argv),
        }

    def _compact_portable_provider_status(self) -> dict[str, Any]:
        args = ["--provider", "portable_sqlite"]
        payload = self._archive_command(
            "search-provider-status",
            args,
            allow_nonzero_json=True,
            timeout_seconds=max(self.timeout_seconds, STATUS_TIMEOUT_SECONDS),
        )
        return _compact_provider_status_for_mcp(
            payload,
            full_freshness_route=self._archive_command_line("search-provider-status", args),
        )

    def _sqlite_table_exists(self, conn: sqlite3.Connection, name: str) -> bool:
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1", (name,)).fetchone()
        return row is not None

    def _sqlite_table_columns(self, conn: sqlite3.Connection, name: str) -> set[str]:
        try:
            return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}
        except sqlite3.Error:
            return set()

    def _sqlite_index_names(self, conn: sqlite3.Connection, table: str) -> set[str]:
        try:
            return {str(row[1]) for row in conn.execute(f"PRAGMA index_list({table})").fetchall()}
        except sqlite3.Error:
            return set()

    def _search_provider_status_fast(self) -> dict[str, Any]:
        db_path = self.aoa_root / "search" / "aoa-search.sqlite3"
        config = _read_json(self.aoa_root / "config" / "search-providers.json")
        config = config if isinstance(config, dict) else {}
        default_provider = str(config.get("default_provider") or "portable_sqlite")
        authority_law = config.get("authority_law")
        base: dict[str, Any] = {
            "schema_version": 1,
            "artifact_type": "search_provider_status",
            "provider_schema_version": 1,
            "generated_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
            "aoa_root": self.aoa_root.as_posix(),
            "config_path": (self.aoa_root / "config" / "search-providers.json").as_posix(),
            "default_provider": default_provider,
            "authority_law": authority_law,
            "selected_provider": "portable_sqlite",
            "status_mode": "fast_presence_probe",
            "diagnostics": [],
            "mcp_access": {
                "mutates": False,
                "archive_command": None,
                "read_model": db_path.as_posix(),
                "authority_boundary": "MCP status reads fixed .aoa search read-model presence; full freshness stays in explicit diagnostics/freshness routes.",
            },
        }
        if not db_path.is_file():
            provider = {
                "provider": "portable_sqlite",
                "ok": False,
                "status": "missing",
                "db_path": db_path.as_posix(),
                "count_mode": "not_counted_fast",
                "freshness": {"status": "not_checked", "checked": False},
                "diagnostics": ["search index missing; run search-index"],
            }
            base["ok"] = False
            base["providers"] = {"portable_sqlite": provider}
            base["diagnostics"] = ["portable_sqlite:missing"]
            return base

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, timeout=0.5)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA busy_timeout = 500")
            meta = {
                str(row["key"]): row["value"]
                for row in conn.execute("SELECT key, value FROM meta").fetchall()
            } if self._sqlite_table_exists(conn, "meta") else {}
            has_documents = self._sqlite_table_exists(conn, "documents") and bool(
                conn.execute("SELECT 1 FROM documents LIMIT 1").fetchone()
            )
            has_routes = self._sqlite_table_exists(conn, "document_routes") and bool(
                conn.execute("SELECT 1 FROM document_routes LIMIT 1").fetchone()
            )
            has_route_terms = self._sqlite_table_exists(conn, "route_terms") and bool(
                conn.execute("SELECT 1 FROM route_terms LIMIT 1").fetchone()
            )
        except sqlite3.Error as exc:
            provider = {
                "provider": "portable_sqlite",
                "ok": False,
                "status": "sqlite_error",
                "db_path": db_path.as_posix(),
                "count_mode": "not_counted_fast",
                "freshness": {"status": "not_checked", "checked": False},
                "diagnostics": [f"sqlite_error:{exc}"],
            }
            base["ok"] = False
            base["providers"] = {"portable_sqlite": provider}
            base["diagnostics"] = [f"portable_sqlite:{provider['status']}"]
            return base
        finally:
            if conn is not None:
                conn.close()

        diagnostics: list[str] = []
        if not has_documents:
            diagnostics.append("search index has no documents")
        if has_documents and not has_routes:
            diagnostics.append("search_route_index_empty")
        if has_routes and not has_route_terms:
            diagnostics.append("search_route_terms_empty")
        ok = bool(has_documents and not diagnostics)
        provider = {
            "provider": "portable_sqlite",
            "ok": ok,
            "status": "ready" if ok else ("empty" if not has_documents else "stale"),
            "db_path": db_path.as_posix(),
            "index_generated_at": meta.get("generated_at"),
            "search_schema_version": meta.get("schema_version"),
            "has_documents": has_documents,
            "has_route_index": has_routes,
            "has_route_terms": has_route_terms,
            "count_mode": "not_counted_fast",
            "freshness": {
                "status": "not_checked",
                "checked": False,
                "reason": "MCP status uses fast presence probe; use aoa_session_freshness_check or search-provider-status for freshness.",
            },
            "diagnostics": diagnostics,
        }
        base["ok"] = ok
        base["providers"] = {"portable_sqlite": provider}
        base["diagnostics"] = [] if ok else [f"portable_sqlite:{provider['status']}"]
        return base

    def readiness_policy(self, include_live: bool = False) -> dict[str, Any]:
        return {
            "schema": "aoa_session_memory_readiness_policy_v1",
            "provider_status": {
                "status_field": "provider",
                "mode": "fast_presence_probe",
                "freshness_checked": False,
                "freshness_route": "aoa_session_freshness_check or explicit .aoa search-provider-status",
            },
            "cached_route_readiness": {
                "source": "latest .aoa route-layer-readiness diagnostic",
                "role": "cached audit summary with stronger evidence refs in .aoa diagnostics",
                "status_field": "latest_route_readiness",
            },
            "live_route_readiness": {
                "enabled": include_live,
                "role": "fast full-archive health gate for frequent MCP status calls",
                "command": "route-readiness",
                "limit": LIVE_READINESS_LIMIT,
                "sample_limit": LIVE_READINESS_SAMPLE_LIMIT,
                "sample_policy": "no evidence sample extraction in MCP status",
                "timeout_seconds": self.timeout_seconds,
                "status_field": "live_route_readiness",
            },
            "audit_route": {
                "role": "full evidence-bearing readiness remains an explicit operator/audit route outside status",
                "command": self._archive_command_line("route-readiness", ["all", "--write-report"]),
            },
            "authority_boundary": "MCP status is a read-only route companion; .aoa diagnostics and raw refs remain stronger evidence.",
        }

    def session_memory_status(self, include_live: bool = False) -> dict[str, Any]:
        status_timeout = max(self.timeout_seconds, STATUS_TIMEOUT_SECONDS)
        provider = self._search_provider_status_fast()
        atlas = self._atlas_summary()
        diagnostics = self.latest_diagnostics(kind="route-layer-readiness", limit=1)
        maintenance = self._maintenance_summary_for_status()
        live_readiness = None
        if include_live:
            live_args = ["all", "--sample-limit", str(LIVE_READINESS_SAMPLE_LIMIT)]
            if LIVE_READINESS_LIMIT is not None:
                live_args.extend(["--limit", str(LIVE_READINESS_LIMIT)])
            live_readiness = self._archive_command(
                "route-readiness",
                live_args,
                allow_nonzero_json=True,
                timeout_seconds=status_timeout,
            )
        return {
            "schema": "aoa_session_memory_status_v1",
            "ok": bool(provider.get("ok")) and atlas.get("root_index_exists", False),
            "mutates": False,
            "workspace_root": self.workspace_root.as_posix(),
            "aoa_root": self.aoa_root.as_posix(),
            "script_path": self.script_path.as_posix(),
            "runtime": self.runtime_identity(),
            "provider": provider,
            "atlas": atlas,
            "graph": self._graph_summary(maintenance),
            "maintenance_status": maintenance,
            "latest_route_readiness": diagnostics,
            "live_route_readiness": live_readiness,
            "readiness_policy": self.readiness_policy(include_live=include_live),
            "authority_boundary": self.authority_boundary(),
        }

    def session_search(self, query: str, filters: dict[str, Any] | None = None, limit: int = 20) -> dict[str, Any]:
        filters, diagnostics = _normalize_search_filters(filters or {})
        text = str(query or "").strip()
        active_filters = {
            key: value
            for key, value in filters.items()
            if key in SEARCH_FILTER_FLAGS and value not in (None, "")
        }
        supported_extra = (
            {"provider", "explain", REQUESTED_AGENT_EVENT_FILTER}
            | SEARCH_CONTROL_FILTERS
            | AGENT_ROUTE_SEARCH_FILTERS
        )
        for key in sorted(set(filters) - set(SEARCH_FILTER_FLAGS) - supported_extra):
            diagnostics.append(f"ignored unsupported filter {key!r}")
        if text:
            text = _ensure_short_text(text, "query")
        elif not active_filters:
            raise ValueError("query or at least one search filter is required")
        agent_route_payload = self._agent_route_filter_search(
            query=text,
            filters=filters,
            active_filters=active_filters,
            limit=limit,
            diagnostics=diagnostics,
        )
        if agent_route_payload is not None:
            return agent_route_payload
        elif self._can_use_local_session_filter_search(active_filters):
            return self._local_session_filter_search(filters=filters, limit=limit, diagnostics=diagnostics)
        args = ["--query", text, "--limit", str(_coerce_limit(limit, 20, 100))]
        use_shards = _as_bool(filters.get("use_shards"), default=bool(text))
        if use_shards:
            max_shards = _coerce_bounded_int(filters.get("max_shards"), DEFAULT_SEARCH_MAX_SHARDS, 1, DEFAULT_SEARCH_MAX_SHARDS)
            args.extend(["--use-shards", "--max-shards", str(max_shards)])
        provider = filters.get("provider")
        if provider:
            args.extend(["--provider", _safe_selector(str(provider), "provider", limit=64)])
        for key, flag in SEARCH_FILTER_FLAGS.items():
            value = filters.get(key)
            if value in (None, ""):
                continue
            if key == "doc_type" and str(value) not in ALLOWED_SEARCH_DOC_TYPES:
                diagnostics.append(f"ignored unsupported doc_type={value!r}")
                continue
            args.extend([flag, _safe_selector(str(value), key)])
        episode = filters.get("episode")
        if episode not in (None, "") and filters.get("task_episode_id") in (None, ""):
            args.extend(["--task-episode-id", _safe_selector(str(episode), "episode")])
        if _as_bool(filters.get("explain"), default=True):
            args.append("--explain")
        payload = self._archive_command(
            "search",
            args,
            timeout_seconds=max(self.timeout_seconds, SEARCH_TIMEOUT_SECONDS),
        )
        if diagnostics:
            payload.setdefault("diagnostics", []).extend(diagnostics)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return _compact_search_payload(payload, full_route=self._archive_command_line("search", args), filters=filters)

    def session_literal_query_plan(
        self,
        query: str = "",
        kind: str = "auto",
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        filters, diagnostics = _normalize_search_filters(filters or {})
        text = str(query or "").strip()
        if text:
            text = _ensure_short_text(text, "query")
        route_kind = _coerce_trace_kind(kind, error_label="literal query kind")
        supported_filters = {
            "session",
            "doc_type",
            "route_layer",
            "route_signal",
            "agent_event",
            "usage_role",
            "task_episode_id",
            "episode",
            "date_from",
            "date_to",
            "max_shards",
            "query_timeout_ms",
            REQUESTED_AGENT_EVENT_FILTER,
        }
        for key in sorted(set(filters) - supported_filters):
            diagnostics.append(f"ignored unsupported filter {key!r}")
        args = ["--query", text, "--kind", route_kind]
        for key, flag in (
            ("session", "--session"),
            ("doc_type", "--doc-type"),
            ("route_layer", "--route-layer"),
            ("route_signal", "--route-signal"),
            ("agent_event", "--agent-event"),
            ("usage_role", "--usage-role"),
            ("task_episode_id", "--task-episode-id"),
            ("date_from", "--date-from"),
            ("date_to", "--date-to"),
        ):
            value = filters.get(key)
            if value in (None, ""):
                continue
            if key == "doc_type" and str(value) not in ALLOWED_SEARCH_DOC_TYPES:
                diagnostics.append(f"ignored unsupported doc_type={value!r}")
                continue
            args.extend([flag, _safe_selector(str(value), key)])
        episode = filters.get("episode")
        if episode not in (None, "") and filters.get("task_episode_id") in (None, ""):
            args.extend(["--task-episode-id", _safe_selector(str(episode), "episode")])
        max_shards = _coerce_bounded_int(filters.get("max_shards"), DEFAULT_SEARCH_MAX_SHARDS, 1, DEFAULT_SEARCH_MAX_SHARDS)
        args.extend(["--max-shards", str(max_shards)])
        query_timeout_ms = filters.get("query_timeout_ms")
        if query_timeout_ms not in (None, ""):
            args.extend(["--query-timeout-ms", str(_coerce_bounded_int(query_timeout_ms, 250, 0, 300_000))])
        payload = self._archive_command(
            "literal-query-plan",
            args,
            timeout_seconds=max(self.timeout_seconds, SEARCH_TIMEOUT_SECONDS),
        )
        if diagnostics:
            payload.setdefault("diagnostics", []).extend(diagnostics)
        _annotate_trace_kind_payload(payload, requested_kind=kind, normalized_kind=route_kind)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def _agent_route_filter_search(
        self,
        *,
        query: str,
        filters: dict[str, Any],
        active_filters: dict[str, Any],
        limit: int,
        diagnostics: list[str],
    ) -> dict[str, Any] | None:
        doc_type = str(active_filters.get("doc_type") or "")
        session = str(active_filters.get("session") or "")
        episode = str(active_filters.get("task_episode_id") or filters.get("episode") or "")
        unsupported_fast_filters = set(active_filters) - AGENT_ROUTE_FAST_PATH_FILTERS
        if unsupported_fast_filters:
            route_only_filters = sorted(
                key
                for key in AGENT_ROUTE_ONLY_SEARCH_FILTERS
                if _filter_is_active(filters.get(key))
            )
            if route_only_filters:
                return {
                    "ok": False,
                    "artifact_type": "session_search_filter_error",
                    "diagnostics": [
                        *diagnostics,
                        "agent-route fast path cannot preserve ordinary search filters "
                        "while also applying route-specific filters; narrow the request or use the "
                        "dedicated route tool",
                    ],
                    "unsupported_filter_mix": {
                        "ordinary_search_filters": sorted(unsupported_fast_filters),
                        "route_specific_filters": route_only_filters,
                    },
                    "mcp_access": {
                        "mutates": False,
                        "archive_command": None,
                        "authority_boundary": "MCP rejected a mixed filter request rather than silently broadening search.",
                    },
                    "authority_boundary": self.authority_boundary(),
                }
            return None

        if doc_type == "task_episode" and not query and not active_filters.get("agent_event"):
            payload = self.session_task_episodes(
                target=session or "all",
                session=session,
                episode=episode,
                status=str(filters.get("status") or ""),
                verification_state=str(filters.get("verification_state") or ""),
                failure_state=str(filters.get("failure_state") or ""),
                limit=limit,
            )
            payload.setdefault("diagnostics", []).extend(
                [*diagnostics, "served by MCP task-episode route fast path"]
            )
            return payload

        if (
            doc_type == "goal_lifecycle"
            and not query
            and not episode
            and "agent_event" not in active_filters
            and "task_episode_id" not in active_filters
        ):
            payload = self.session_goal_lifecycles(
                target=session or "all",
                session=session,
                goal_id=str(filters.get("goal_id") or ""),
                status=str(filters.get("status") or ""),
                event_kind=str(filters.get("event_kind") or ""),
                limit=limit,
            )
            payload.setdefault("diagnostics", []).extend(
                [*diagnostics, "served by MCP goal-lifecycle route fast path"]
            )
            return payload

        if "agent_event" not in active_filters and "task_episode_id" not in active_filters:
            return None
        if doc_type not in ("", "all", "event"):
            return None

        payload = self.session_agent_responses(
            query=query,
            session=session,
            agent_events=_split_filter_values(
                filters.get(REQUESTED_AGENT_EVENT_FILTER) or active_filters.get("agent_event")
            ),
            episode=episode,
            closeout_final=_as_bool(filters.get("closeout_final"), default=False),
            verification_state=str(filters.get("verification_state") or "any"),
            failure_state=str(filters.get("failure_state") or "any"),
            limit=limit,
            provider=str(filters.get("provider") or "portable_sqlite"),
            explain=_as_bool(filters.get("explain"), default=False),
            use_shards=_as_bool(filters.get("use_shards"), default=True),
            max_shards=_coerce_bounded_int(
                filters.get("max_shards"),
                DEFAULT_SEARCH_MAX_SHARDS,
                1,
                DEFAULT_SEARCH_MAX_SHARDS,
            ),
        )
        payload.setdefault("diagnostics", []).extend(
            [*diagnostics, "served by MCP agent-event route fast path"]
        )
        return payload

    def session_agent_responses(
        self,
        query: str = "",
        session: str = "",
        agent_events: list[str] | None = None,
        episode: str = "",
        closeout_final: bool = False,
        verification_state: str = "any",
        failure_state: str = "any",
        limit: int = 20,
        provider: str = "portable_sqlite",
        explain: bool = True,
        use_shards: bool = True,
        max_shards: int = DEFAULT_SEARCH_MAX_SHARDS,
    ) -> dict[str, Any]:
        text = str(query or "").strip()
        if text:
            text = _ensure_short_text(text, "query")
        normalized_agent_events, requested_agent_events = _normalize_agent_event_classes(agent_events)
        scoped = bool(
            text
            or session
            or episode
            or closeout_final
            or normalized_agent_events
            or verification_state != "any"
            or failure_state != "any"
        )
        if not scoped:
            return {
                "schema_version": 1,
                "artifact_type": "agent_event_route_guidance",
                "ok": False,
                "mutates": False,
                "diagnostics": [
                    "unscoped_agent_response_route_requires_query_session_episode_or_event_filter"
                ],
                "next_route": (
                    "Provide a session, query, episode, or agent_event filter before using "
                    "agent-responses over the full archive. Use aoa_session_search or "
                    "aoa_session_task_episodes to narrow the evidence route first."
                ),
                "mcp_access": {
                    "mutates": False,
                    "archive_command": None,
                    "authority_boundary": (
                        "MCP returns route guidance only; no archive scan was started."
                    ),
            },
                "authority_boundary": self.authority_boundary(),
            }
        fast_agent_events = list(normalized_agent_events)
        if closeout_final and not fast_agent_events:
            fast_agent_events = ["assistant_final_closeout"]
        args = [
            "--query",
            text,
            "--limit",
            str(_coerce_limit(limit, 20, 100)),
            "--provider",
            _safe_selector(provider, "provider", limit=64),
        ]
        if use_shards:
            args.extend(
                [
                    "--use-shards",
                    "--max-shards",
                    str(_coerce_bounded_int(max_shards, DEFAULT_SEARCH_MAX_SHARDS, 1, DEFAULT_SEARCH_MAX_SHARDS)),
                ]
            )
        else:
            args.append("--no-shards")
        if session:
            args.extend(["--session", _safe_selector(session, "session")])
        if episode:
            args.extend(["--task-episode-id", _safe_selector(episode, "episode", limit=80)])
        for agent_event in normalized_agent_events:
            args.extend(["--agent-event", _safe_selector(str(agent_event), "agent_event", limit=100)])
        if closeout_final:
            args.append("--closeout-final")
        if verification_state != "any":
            args.extend(["--verification-state", _safe_selector(verification_state, "verification_state", limit=32)])
        if failure_state != "any":
            args.extend(["--failure-state", _safe_selector(failure_state, "failure_state", limit=32)])
        if explain:
            args.append("--explain")
        if verification_state == "any" and failure_state == "any":
            fast_payload = self._agent_event_sqlite_fast_path(
                command="agent-responses",
                query=text,
                session=session,
                episode=episode,
                agent_events=fast_agent_events,
                requested_agent_events=requested_agent_events,
                limit=_coerce_limit(limit, 20, 100),
                archive_args=args,
            )
            if fast_payload is not None:
                return fast_payload
        payload = self._archive_command("agent-responses", args, allow_nonzero_json=True)
        _annotate_agent_event_payload(payload, requested=requested_agent_events, normalized=normalized_agent_events or payload.get("agent_events", []))
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def session_agent_closeouts(
        self,
        query: str = "",
        session: str = "",
        episode: str = "",
        limit: int = 20,
        provider: str = "portable_sqlite",
        explain: bool = True,
    ) -> dict[str, Any]:
        return self._simple_agent_event_route(
            command="agent-closeouts",
            query=query,
            session=session,
            episode=episode,
            limit=limit,
            provider=provider,
            explain=explain,
        )

    def session_agent_progress_updates(
        self,
        query: str = "",
        session: str = "",
        episode: str = "",
        limit: int = 20,
        provider: str = "portable_sqlite",
        explain: bool = True,
    ) -> dict[str, Any]:
        return self._simple_agent_event_route(
            command="agent-progress-updates",
            query=query,
            session=session,
            episode=episode,
            limit=limit,
            provider=provider,
            explain=explain,
        )

    def _simple_agent_event_route(
        self,
        *,
        command: str,
        query: str = "",
        session: str = "",
        episode: str = "",
        limit: int = 20,
        provider: str = "portable_sqlite",
        explain: bool = True,
    ) -> dict[str, Any]:
        text = str(query or "").strip()
        if text:
            text = _ensure_short_text(text, "query")
        args = [
            "--query",
            text,
            "--limit",
            str(_coerce_limit(limit, 20, 100)),
            "--provider",
            _safe_selector(provider, "provider", limit=64),
            "--use-shards",
            "--max-shards",
            str(DEFAULT_SEARCH_MAX_SHARDS),
        ]
        if session:
            args.extend(["--session", _safe_selector(session, "session")])
        if episode:
            args.extend(["--task-episode-id", _safe_selector(episode, "episode", limit=80)])
        if explain:
            args.append("--explain")
        fast_payload = self._agent_event_sqlite_fast_path(
            command=command,
            query=text,
            session=session,
            episode=episode,
            agent_events=AGENT_EVENT_DEFAULTS_BY_ROUTE.get(command, []),
            limit=_coerce_limit(limit, 20, 100),
            archive_args=args,
        )
        if fast_payload is not None:
            return fast_payload
        payload = self._archive_command(command, args, allow_nonzero_json=True)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def _agent_event_sqlite_fast_path(
        self,
        *,
        command: str,
        query: str,
        session: str,
        episode: str,
        agent_events: list[str],
        limit: int,
        archive_args: list[str],
        requested_agent_events: list[str] | None = None,
    ) -> dict[str, Any] | None:
        explicit_agent_events, normalized_requested = _normalize_agent_event_classes(agent_events)
        requested_events = list(requested_agent_events or normalized_requested)
        if not (session or episode or query or explicit_agent_events):
            return None
        if query:
            return None
        db_path = self.aoa_root / "search" / "aoa-search.sqlite3"
        if not db_path.is_file():
            return None
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(
                f"{db_path.resolve().as_uri()}?mode=ro",
                uri=True,
            )
            conn.execute("PRAGMA query_only = ON")
            conn.row_factory = sqlite3.Row
            if not self._sqlite_table_exists(conn, "documents"):
                return None
            columns = self._sqlite_table_columns(conn, "documents")
            if "agent_event" not in columns:
                return None
            filters = ["doc_type = 'event'"]
            params: list[Any] = []
            table_expr = "documents"
            order_expr = "rowid DESC"
            ordered_by = "sqlite_rowid_desc_agent_event_fast_path"
            indexes = self._sqlite_index_names(conn, "documents")
            session_dir = self._resolve_session_dir(session) if session else None
            if session:
                if "session_label" not in columns:
                    return None
                if "idx_documents_session_agent_event" in indexes:
                    table_expr = "documents INDEXED BY idx_documents_session_agent_event"
                elif "idx_documents_event_session_agent_date" in indexes:
                    table_expr = "documents INDEXED BY idx_documents_event_session_agent_date"
                    order_expr = "session_date DESC, rowid DESC"
                    ordered_by = "sqlite_session_date_rowid_desc_agent_event_fast_path"
                elif "idx_documents_session" in indexes:
                    table_expr = "documents INDEXED BY idx_documents_session"
                else:
                    return None
                filters.append("session_label = ?")
                params.append(session_dir.name if session_dir is not None else session)
            elif explicit_agent_events and "agent_event" in columns:
                if "idx_documents_agent_event" in indexes:
                    table_expr = "documents INDEXED BY idx_documents_agent_event"
                elif "idx_documents_agent_event_date" in indexes:
                    table_expr = "documents INDEXED BY idx_documents_agent_event_date"
                    order_expr = "session_date DESC, rowid DESC"
                    ordered_by = "sqlite_session_date_rowid_desc_agent_event_fast_path"
                else:
                    return None
            if episode and "task_episode_id" in columns:
                filters.append("task_episode_id = ?")
                params.append(episode)
            elif episode:
                return None
            if explicit_agent_events:
                placeholders = ", ".join("?" for _ in explicit_agent_events)
                filters.append(f"agent_event IN ({placeholders})")
                params.extend(explicit_agent_events)
            elif command in AGENT_EVENT_DEFAULTS_BY_ROUTE:
                defaults = AGENT_EVENT_DEFAULTS_BY_ROUTE[command]
                placeholders = ", ".join("?" for _ in defaults)
                filters.append(f"agent_event IN ({placeholders})")
                params.extend(defaults)
            else:
                filters.append("agent_event IS NOT NULL AND agent_event != ''")
            if query:
                searchable_columns = [name for name in ("title", "body") if name in columns]
                if not searchable_columns:
                    return None
                filters.append(
                    "("
                    + " OR ".join(f"LOWER(COALESCE({name}, '')) LIKE ?" for name in searchable_columns)
                    + ")"
                )
                params.extend([f"%{query.casefold()}%" for _ in searchable_columns])

            def select_expr(name: str) -> str:
                return f"{name} AS {name}" if name in columns else f"NULL AS {name}"

            rows = conn.execute(
                f"""
                SELECT
                    rowid AS rowid,
                    id AS id,
                    doc_type AS doc_type,
                    {select_expr("session_id")},
                    {select_expr("session_label")},
                    {select_expr("session_title")},
                    {select_expr("session_date")},
                    {select_expr("event_type")},
                    {select_expr("family")},
                    {select_expr("conversation_act")},
                    {select_expr("session_act")},
                    {select_expr("agent_event")},
                    {select_expr("task_episode_id")},
                    {select_expr("route_layers")},
                    {select_expr("route_signals")},
                    {select_expr("title")},
                    {select_expr("segment_ref")},
                    {select_expr("segment_index_path")},
                    {select_expr("raw_ref")},
                    {select_expr("raw_block_ref")},
                    {select_expr("manifest_path")},
                    {select_expr("freshness_status")},
                    {select_expr("stale_reason")}
                FROM {table_expr}
                WHERE {" AND ".join(filters)}
                ORDER BY {order_expr}
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
        except sqlite3.Error:
            return None
        finally:
            if conn is not None:
                conn.close()
        results = [self._agent_event_hit_from_sqlite_row(row) for row in rows]
        quality = self._agent_event_sqlite_quality_summary(results, ordered_by=ordered_by)
        return {
            "schema_version": 1,
            "artifact_type": "agent_event_route_results",
            "ok": True,
            "mutates": False,
            "source": "portable_sqlite_agent_event_fast_path",
            "command": command,
            "query": query,
            "session": session or None,
            "episode": episode or None,
            "agent_events": explicit_agent_events or AGENT_EVENT_DEFAULTS_BY_ROUTE.get(command, []),
            **(
                {"requested_agent_events": requested_events}
                if requested_events and requested_events != (explicit_agent_events or AGENT_EVENT_DEFAULTS_BY_ROUTE.get(command, []))
                else {}
            ),
            "result_count": len(results),
            "results": results,
            "quality": quality,
            "search_projection": {
                "mode": "mcp_sqlite_agent_event_fast_path",
                "read_model": db_path.as_posix(),
                "fallback_route": "archive_cli_shard_fanout",
                "next_expansion_command": self._archive_command_line(command, archive_args),
            },
            "cost_profile": {
                "lightweight_route": True,
                "structured_route_filter": True,
                "uses_fts": False,
                "hydrates_body": False,
                "semantic_preview": False,
                "uses_shards": False,
            },
            "provider": {
                "selected": "portable_sqlite",
                "status": "mcp_sqlite_agent_event_fast_path",
                "db_path": db_path.as_posix(),
            },
            "diagnostics": ["served by MCP SQLite agent-event fast path"],
            "mcp_access": {
                "mutates": False,
                "archive_command": None,
                "read_model": db_path.as_posix(),
                "next_expansion_command": self._archive_command_line(command, archive_args),
                "authority_boundary": "MCP fast path reads generated search projection; raw transcript refs remain authoritative.",
            },
            "authority_boundary": self.authority_boundary(),
        }

    def _agent_event_sqlite_quality_summary(
        self,
        results: list[dict[str, Any]],
        *,
        ordered_by: str,
    ) -> dict[str, Any]:
        agent_event_counts: Counter[str] = Counter()
        freshness_counts: Counter[str] = Counter()
        source_counts: Counter[str] = Counter()
        conversation_act_counts: Counter[str] = Counter()
        event_type_counts: Counter[str] = Counter()
        raw_ref_present_count = 0
        segment_ref_present_count = 0
        for item in results:
            agent_event_counts[str(item.get("agent_event") or "unknown")] += 1
            conversation_act = str(item.get("conversation_act") or "unknown")
            event_type = str(item.get("event_type") or "unknown")
            conversation_act_counts[conversation_act] += 1
            event_type_counts[event_type] += 1
            source_counts["mcp_sqlite_projection"] += 1
            freshness = item.get("freshness") if isinstance(item.get("freshness"), dict) else {}
            status = str(freshness.get("status") or "unverifiable")
            if status == "fresh":
                freshness_bucket = "fresh"
            elif status in {"stale", "not_current", "dirty", "missing"} or status.startswith("stale"):
                freshness_bucket = "stale"
            else:
                freshness_bucket = "unverifiable"
            freshness_counts[freshness_bucket] += 1
            refs = item.get("refs") if isinstance(item.get("refs"), dict) else {}
            if refs.get("raw"):
                raw_ref_present_count += 1
            if refs.get("segment"):
                segment_ref_present_count += 1
        latest = results[0] if results else {}
        latest_refs = latest.get("refs") if isinstance(latest.get("refs"), dict) else {}
        latest_event_id = ""
        latest_segment_id = ""
        doc_id = str(latest.get("doc_id") or "")
        match = re.search(r":([^:]+):([^:]+)$", doc_id)
        if match:
            latest_segment_id = match.group(1)
            latest_event_id = match.group(2)
        latest_freshness = latest.get("freshness") if isinstance(latest.get("freshness"), dict) else {}
        return {
            "result_count": len(results),
            "ordered_by": ordered_by,
            "query_rank_active": False,
            "agent_event_counts": dict(sorted(agent_event_counts.items())),
            "freshness_counts": dict(sorted(freshness_counts.items())),
            "fresh_result_count": freshness_counts.get("fresh", 0),
            "stale_result_count": freshness_counts.get("stale", 0),
            "unverifiable_result_count": freshness_counts.get("unverifiable", 0),
            "stale_result_present": freshness_counts.get("stale", 0) > 0,
            "source_counts": dict(sorted(source_counts.items())),
            "conversation_act_counts": dict(sorted(conversation_act_counts.items())),
            "event_type_counts": dict(sorted(event_type_counts.items())),
            "raw_ref_present_count": raw_ref_present_count,
            "segment_ref_present_count": segment_ref_present_count,
            "latest_result": {
                "doc_id": latest.get("doc_id"),
                "event_id": latest_event_id,
                "segment_id": latest_segment_id,
                "agent_event": latest.get("agent_event"),
                "freshness": latest_freshness.get("status"),
                "raw": latest_refs.get("raw"),
                "segment": latest_refs.get("segment"),
            }
            if latest
            else {},
        }

    def _agent_event_hit_from_sqlite_row(self, row: sqlite3.Row) -> dict[str, Any]:
        refs = {
            "session": row["manifest_path"],
            "segment": row["segment_ref"],
            "segment_index": row["segment_index_path"],
            "raw": row["raw_ref"],
            "raw_block": row["raw_block_ref"],
        }
        return {
            "doc_id": row["id"],
            "doc_type": row["doc_type"],
            "session_id": row["session_id"],
            "session_label": row["session_label"],
            "session_title": row["session_title"],
            "session_date": row["session_date"],
            "event_type": row["event_type"],
            "family": row["family"],
            "conversation_act": row["conversation_act"],
            "session_act": row["session_act"],
            "agent_event": row["agent_event"],
            "task_episode_id": row["task_episode_id"],
            "route_layers": row["route_layers"],
            "route_signals": row["route_signals"],
            "title": row["title"],
            "refs": {key: value for key, value in refs.items() if value},
            "freshness": {
                "status": row["freshness_status"],
                "reasons": [row["stale_reason"]] if row["stale_reason"] else [],
            },
        }

    def session_agent_reasoning_windows(
        self,
        query: str = "",
        session: str = "",
        episode: str = "",
        limit: int = 10,
        before: int = 3,
        after: int = 6,
        provider: str = "portable_sqlite",
        explain: bool = True,
    ) -> dict[str, Any]:
        return self._agent_event_window_route(
            command="agent-reasoning-windows",
            query=query,
            session=session,
            episode=episode,
            limit=limit,
            before=before,
            after=after,
            provider=provider,
            explain=explain,
        )

    def session_answer_neighborhood(
        self,
        query: str = "",
        session: str = "",
        agent_events: list[str] | None = None,
        episode: str = "",
        limit: int = 10,
        before: int = 3,
        after: int = 6,
        provider: str = "portable_sqlite",
        explain: bool = True,
    ) -> dict[str, Any]:
        return self._agent_event_window_route(
            command="answer-neighborhood",
            query=query,
            session=session,
            episode=episode,
            agent_events=agent_events,
            limit=limit,
            before=before,
            after=after,
            provider=provider,
            explain=explain,
        )

    def _agent_event_window_route(
        self,
        *,
        command: str,
        query: str = "",
        session: str = "",
        episode: str = "",
        agent_events: list[str] | None = None,
        limit: int = 10,
        before: int = 3,
        after: int = 6,
        provider: str = "portable_sqlite",
        explain: bool = True,
    ) -> dict[str, Any]:
        text = str(query or "").strip()
        if text:
            text = _ensure_short_text(text, "query")
        args = [
            "--query",
            text,
            "--limit",
            str(_coerce_limit(limit, 10, 50)),
            "--before",
            str(_coerce_bounded_int(before, 3, 0, 24)),
            "--after",
            str(_coerce_bounded_int(after, 6, 0, 48)),
            "--provider",
            _safe_selector(provider, "provider", limit=64),
            "--use-shards",
            "--max-shards",
            str(DEFAULT_SEARCH_MAX_SHARDS),
        ]
        if session:
            args.extend(["--session", _safe_selector(session, "session")])
        if episode:
            args.extend(["--task-episode-id", _safe_selector(episode, "episode", limit=80)])
        args.append("--explain" if explain else "--no-explain")
        normalized_agent_events, requested_agent_events = _normalize_agent_event_classes(agent_events, default=AGENT_EVENT_DEFAULTS_BY_ROUTE.get(command, []))
        if command != "agent-reasoning-windows":
            for agent_event in normalized_agent_events:
                args.extend(["--agent-event", _safe_selector(str(agent_event), "agent_event", limit=100)])
        fast_payload = self._agent_event_sqlite_fast_path(
            command=command,
            query=text,
            session=session,
            episode=episode,
            agent_events=normalized_agent_events,
            requested_agent_events=requested_agent_events,
            limit=_coerce_limit(limit, 10, 50),
            archive_args=args,
        )
        if fast_payload is not None:
            return self._agent_event_window_fast_path_payload(
                command=command,
                source_payload=fast_payload,
                before=_coerce_bounded_int(before, 3, 0, 24),
                after=_coerce_bounded_int(after, 6, 0, 48),
            )
        payload = self._archive_command(command, args, allow_nonzero_json=True)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def _agent_event_window_fast_path_payload(
        self,
        *,
        command: str,
        source_payload: dict[str, Any],
        before: int,
        after: int,
    ) -> dict[str, Any]:
        results = source_payload.get("results") if isinstance(source_payload.get("results"), list) else []
        windows = [
            {
                "ok": True,
                "source": "portable_sqlite_agent_event_window_fast_path",
                "center_event": result,
                "events": [result],
                "refs": result.get("refs") if isinstance(result, dict) else {},
                "freshness": result.get("freshness") if isinstance(result, dict) else None,
            }
            for result in results
            if isinstance(result, dict)
        ]
        return {
            "schema_version": 1,
            "artifact_type": "agent_event_windows",
            "ok": True,
            "mutates": False,
            "source": "portable_sqlite_agent_event_window_fast_path",
            "command": command,
            "window_count": len(windows),
            "windows": windows,
            "parameters": {"before": before, "after": after},
            "provider": source_payload.get("provider"),
            "cost_profile": source_payload.get("cost_profile"),
            "search_projection": source_payload.get("search_projection"),
            "quality": source_payload.get("quality"),
            "diagnostics": [
                "served by MCP SQLite agent-event window fast path",
                "fast path returns center refs only; use next_expansion_command for raw before/after windows",
            ],
            "mcp_access": source_payload.get("mcp_access", {}),
            "authority_boundary": self.authority_boundary(),
        }

    def session_task_episodes(
        self,
        target: str = "all",
        session: str = "",
        episode: str = "",
        status: str = "",
        verification_state: str = "",
        failure_state: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        args = [_safe_selector(target or "all", "target", limit=160), "--limit", str(_coerce_limit(limit, 20, 100))]
        if session:
            args.extend(["--session", _safe_selector(session, "session")])
        if episode:
            args.extend(["--task-episode-id", _safe_selector(episode, "episode", limit=80)])
        if status:
            args.extend(["--status", _safe_selector(status, "status", limit=32)])
        if verification_state:
            args.extend(["--verification-state", _safe_selector(verification_state, "verification_state", limit=32)])
        if failure_state:
            args.extend(["--failure-state", _safe_selector(failure_state, "failure_state", limit=32)])
        payload = self._archive_command("task-episodes", args, allow_nonzero_json=True)
        results = payload.get("results")
        if isinstance(results, list):
            payload["results"] = [_compact_task_episode(item) for item in results if isinstance(item, dict)]
            payload["mcp_payload_policy"] = {
                "response_compacted": True,
                "sample_refs_per_bucket": 1,
                "full_refs_route": "Use .aoa task-episodes CLI or session.index.json for full generated episode refs.",
            }
            mcp_access = payload.get("mcp_access")
            if isinstance(mcp_access, dict):
                mcp_access["response_compacted"] = True
                mcp_access["full_refs_route"] = payload["mcp_payload_policy"]["full_refs_route"]
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def session_goal_lifecycles(
        self,
        target: str = "all",
        session: str = "",
        goal_id: str = "",
        status: str = "",
        event_kind: str = "",
        limit: int = 20,
        order: str = "recent",
    ) -> dict[str, Any]:
        if order not in {"recent", "chronological"}:
            return {
                "schema_version": 1,
                "artifact_type": "goal_lifecycle_route_error",
                "ok": False,
                "mutates": False,
                "diagnostics": [
                    "invalid order; expected one of: recent, chronological"
                ],
                "received_order": order,
                "allowed_order_values": ["recent", "chronological"],
                "mcp_access": {
                    "mutates": False,
                    "archive_command": None,
                    "authority_boundary": "MCP rejected invalid route parameters before invoking the archive CLI.",
                },
                "authority_boundary": self.authority_boundary(),
            }
        args = [_safe_selector(target or "all", "target", limit=160), "--limit", str(_coerce_limit(limit, 20, 100))]
        if session:
            args.extend(["--session", _safe_selector(session, "session")])
        if goal_id:
            args.extend(["--goal-id", _safe_selector(goal_id, "goal_id", limit=80)])
        if status:
            args.extend(["--status", _safe_selector(status, "status", limit=32)])
        if event_kind:
            args.extend(["--event-kind", _safe_selector(event_kind, "event_kind", limit=80)])
        if order:
            args.extend(["--order", _safe_selector(order, "order", limit=32)])
        payload = self._archive_command("goal-lifecycles", args, allow_nonzero_json=True)
        if isinstance(payload.get("provider"), dict):
            payload["provider"] = _compact_provider_status_for_mcp(payload["provider"])
        results = payload.get("results")
        if isinstance(results, list):
            payload["results"] = [_compact_goal_lifecycle(item) for item in results if isinstance(item, dict)]
            payload["mcp_payload_policy"] = {
                "response_compacted": True,
                "sample_events_per_lifecycle": GOAL_LIFECYCLE_SAMPLE_EVENT_LIMIT,
                "objective_preview_chars": GOAL_LIFECYCLE_OBJECTIVE_PREVIEW_CHARS,
                "full_refs_route": "Use .aoa goal-lifecycles CLI or session.index.json for full generated lifecycle refs.",
            }
            mcp_access = payload.get("mcp_access")
            if isinstance(mcp_access, dict):
                mcp_access["response_compacted"] = True
                mcp_access["full_refs_route"] = payload["mcp_payload_policy"]["full_refs_route"]
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def _can_use_local_session_filter_search(self, active_filters: dict[str, Any]) -> bool:
        if "session" not in active_filters:
            return False
        allowed = {"session", "doc_type"}
        if set(active_filters) - allowed:
            return False
        doc_type = active_filters.get("doc_type")
        return doc_type in (None, "", "session")

    def _local_session_filter_search(
        self,
        filters: dict[str, Any],
        limit: int,
        diagnostics: list[str] | None = None,
    ) -> dict[str, Any]:
        selector = _safe_selector(str(filters.get("session") or ""), "session")
        include_explain = _as_bool(filters.get("explain"), default=True)
        provider = str(filters.get("provider") or "portable_sqlite")
        limit = _coerce_limit(limit, 20, 100)
        session_dir = self._resolve_session_dir(selector)
        payload = {
            "schema_version": 1,
            "artifact_type": "search_results",
            "search_schema_version": "mcp-local-session-filter",
            "ok": True,
            "query": "",
            "normalized_query": "",
            "result_count": 0,
            "results": [],
            "provider": {
                "selected": provider,
                "authoritative_result_provider": "mcp_local_session_filter",
                "status": "local_session_filter_fast_path",
                "authority_law": ".aoa refs remain authoritative; MCP local session filter only routes to existing session evidence.",
            },
            "diagnostics": list(diagnostics or []),
            "mcp_access": {
                "mutates": False,
                "archive_command": None,
                "authority_boundary": "MCP local session filter routes to .aoa refs without invoking full archive search.",
            },
            "authority_boundary": self.authority_boundary(),
        }
        if session_dir is None:
            payload["diagnostics"].append(f"session filter did not resolve: {selector}")
            return payload
        manifest_path = session_dir / "session.manifest.json"
        index_path = session_dir / "session.index.json"
        manifest = _read_json(manifest_path)
        index = _read_json(index_path)
        if not isinstance(manifest, dict):
            payload["ok"] = False
            payload["diagnostics"].append(f"session manifest missing or invalid: {manifest_path}")
            return payload
        if not isinstance(index, dict):
            index = {}
        display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
        source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
        raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
        session_id = str(manifest.get("session_id") or index.get("session_id") or "")
        label = str(manifest.get("session_label") or display.get("label") or session_dir.name)
        title = str(manifest.get("session_title") or display.get("title") or "")
        session_date = str(display.get("date") or self._date_from_session_label(label) or "")
        result = {
            "rank": 0.0,
            "doc_id": f"session:{session_id or label}",
            "doc_type": "session",
            "session_id": session_id,
            "session_label": label,
            "session_title": title,
            "session_date": session_date,
            "cwd": source.get("cwd") or manifest.get("cwd") or index.get("work_context"),
            "archive_status": manifest.get("archive_status"),
            "review_status": manifest.get("review_status"),
            "distillation_status": manifest.get("distillation_status"),
            "event_count": manifest.get("event_count") or index.get("event_count"),
            "segment_count": manifest.get("segment_count") or index.get("segment_count"),
            "title": title or label,
            "snippet": " ".join(part for part in [label, title] if part)[:600],
            "refs": {
                "session": manifest_path.as_posix(),
                "session_index": index_path.as_posix(),
                "session_md": (session_dir / "SESSION.md").as_posix(),
                "raw": raw.get("path"),
                "raw_sha256": raw.get("sha256"),
                "blocks_index": raw.get("blocks_index"),
            },
            "freshness": {
                "status": "present",
                "reasons": ["local_session_filter_fast_path"],
            },
        }
        if include_explain:
            result["explain"] = {
                "query": "",
                "matched_document_layer": "session",
                "fast_path": "mcp_local_session_filter",
                "session_selector": selector,
                "routing_fields": {
                    "session_id": session_id,
                    "session_label": label,
                    "session_title": title,
                },
            }
        payload["result_count"] = 1 if limit >= 1 else 0
        payload["results"] = [result] if limit >= 1 else []
        payload["diagnostics"].append("served by MCP local session filter fast path")
        return payload

    def _date_from_session_label(self, label: str) -> str:
        match = re.match(r"(\d{4}-\d{2}-\d{2})", label)
        return match.group(1) if match else ""

    def session_trace(
        self,
        anchor: str,
        kind: str = "auto",
        limit: int = 20,
        per_route_limit: int = 10,
        session: str = "",
        doc_type: str = "session",
        explain: bool = True,
    ) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        route_kind = _coerce_trace_kind(kind)
        if doc_type not in ALLOWED_DOC_TYPES:
            raise ValueError(f"unsupported doc_type: {doc_type}")
        args = [
            anchor_text,
            "--kind",
            route_kind,
            "--limit",
            str(_coerce_limit(limit, 20, 100)),
            "--per-route-limit",
            str(_coerce_limit(per_route_limit, 10, 50)),
            "--doc-type",
            doc_type,
            "--full",
        ]
        if session:
            args.extend(["--session", _safe_selector(session, "session")])
        if explain:
            args.append("--explain")
        payload = self._archive_command("trace-route", args)
        _annotate_trace_kind_payload(payload, requested_kind=kind, normalized_kind=route_kind)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def session_entity_usage_audit(
        self,
        anchor: str,
        kind: str = "auto",
        limit: int = 20,
        per_route_limit: int = 20,
        consequence_window: int = 8,
        document_limit: int = 60,
        session: str = "",
        full: bool = False,
    ) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        route_kind = _coerce_trace_kind(kind)
        args = [
            anchor_text,
            "--kind",
            route_kind,
            "--limit",
            str(_coerce_limit(limit, 20, 200)),
            "--per-route-limit",
            str(_coerce_limit(per_route_limit, 20, 100)),
            "--consequence-window",
            str(_coerce_limit(consequence_window, 8, 24)),
            "--document-limit",
            str(_coerce_limit(document_limit, 60, 200)),
            "--full",
        ]
        if session:
            args.extend(["--session", _safe_selector(session, "session")])
        full_route = self._archive_command_line("entity-usage-audit", args)
        if route_kind == "agent_event":
            normalized_events, requested_events = _normalize_agent_event_classes([anchor_text])
            fast_payload = self._agent_event_sqlite_fast_path(
                command="entity-usage-audit",
                query="",
                session=session,
                episode="",
                agent_events=normalized_events,
                requested_agent_events=requested_events,
                limit=min(_coerce_limit(limit, 20, 200), 100),
                archive_args=args,
            )
            admission = self._resource_admitted_archive_route(
                "entity-usage-audit",
                args,
                workload_class="medium",
            )
            events = [
                {**event, "role": "outcome", "relation": "classified_agent_event_occurrence"}
                for event in (fast_payload or {}).get("results", [])
                if isinstance(event, dict)
            ]
            fast_quality = (fast_payload or {}).get("quality")
            payload = {
                "schema_version": 1,
                "artifact_type": "session_memory_entity_usage_audit",
                "ok": fast_payload is not None,
                "mutates": False,
                "source": (
                    "mcp_sqlite_agent_event_usage_audit"
                    if fast_payload is not None
                    else "mcp_bounded_agent_event_usage_deferred"
                ),
                "truth_status": "session_memory_entity_usage_routes_to_evidence_not_reviewed_truth",
                "anchor": anchor_text,
                "kind": route_kind,
                "requested_kind": kind,
                "session": session or None,
                "event_count": len(events),
                "entrypoint_event_count": 0,
                "usage_event_count": 0,
                "result_event_count": 0,
                "outcome_event_count": len(events),
                "context_event_count": 0,
                "consequence_event_count": 0,
                "outcome_events": events,
                "quality": {
                    **(fast_quality if isinstance(fast_quality, dict) else {}),
                    "route": "bounded_agent_event_sqlite_projection",
                    "direct_sqlite_fast_path": fast_payload is not None,
                    "event_class_occurrence_not_entity_causality": True,
                    "deep_archive_fallback_executed": False,
                },
                "diagnostics": (
                    list(fast_payload.get("diagnostics", []))
                    if fast_payload is not None
                    else ["bounded_agent_event_projection_unavailable_deep_archive_fallback_deferred"]
                ),
                "provider": (fast_payload or {}).get("provider", {}),
                "next_expansion_command": admission["launch_command"],
                "next_expansion_reason": (
                    "Run the owner usage-audit command only when the bounded event-class occurrences are insufficient."
                ),
                "mcp_access": {
                    "mutates": False,
                    "archive_command": None,
                    "read_model": ((fast_payload or {}).get("mcp_access") or {}).get("read_model"),
                    "deep_archive_fallback_executed": False,
                    "deep_archive_fallback_deferred": fast_payload is None,
                    "owner_admission_required_for_expansion": True,
                    "owner_admission": admission,
                },
                "authority_boundary": self.authority_boundary(),
            }
            return _compact_entity_usage_audit_payload(payload, full_route=full_route)
        payload = self._archive_command(
            "entity-usage-audit",
            args,
            allow_nonzero_json=True,
            timeout_seconds=max(self.timeout_seconds, EVIDENCE_PACKET_TIMEOUT_SECONDS),
        )
        _annotate_trace_kind_payload(payload, requested_kind=kind, normalized_kind=route_kind)
        payload.setdefault("authority_boundary", self.authority_boundary())
        mcp_access = payload.get("mcp_access")
        if isinstance(mcp_access, dict):
            mcp_access["full_evidence_route"] = full_route
            mcp_access["response_compacted"] = not full
        if full:
            return payload
        return _compact_entity_usage_audit_payload(payload, full_route=full_route)

    def session_entity_usage_chain(
        self,
        anchor: str,
        kind: str = "auto",
        limit: int = 6,
        per_route_limit: int = 12,
        consequence_window: int = 6,
        document_limit: int = 24,
        session: str = "",
        full: bool = False,
    ) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        route_kind = _coerce_trace_kind(kind)
        base_args = [
            anchor_text,
            "--kind",
            route_kind,
            "--limit",
            str(_coerce_limit(limit, 6, 50)),
            "--per-route-limit",
            str(_coerce_limit(per_route_limit, 12, 100)),
            "--consequence-window",
            str(_coerce_limit(consequence_window, 6, 24)),
            "--document-limit",
            str(_coerce_limit(document_limit, 24, 100)),
        ]
        if session:
            base_args.extend(["--session", _safe_selector(session, "session")])
        full_args = [*base_args, "--full"]
        run_args = full_args if full else base_args
        full_route = self._archive_command_line("usage-chain", full_args)
        payload = self._archive_command(
            "usage-chain",
            run_args,
            allow_nonzero_json=True,
            timeout_seconds=max(self.timeout_seconds, EVIDENCE_PACKET_TIMEOUT_SECONDS),
        )
        _annotate_trace_kind_payload(payload, requested_kind=kind, normalized_kind=route_kind)
        payload.setdefault("authority_boundary", self.authority_boundary())
        mcp_access = payload.get("mcp_access")
        if isinstance(mcp_access, dict):
            mcp_access["full_evidence_route"] = full_route
            mcp_access["response_compacted"] = not full
        if full:
            return payload
        return _compact_entity_usage_chain_payload(payload, full_route=full_route)

    def session_entity_usage_neighborhood(
        self,
        anchor: str,
        kind: str = "auto",
        limit: int = 6,
        per_route_limit: int = 20,
        before: int = 3,
        after: int = 8,
        raw_preview_chars: int = 600,
        document_limit: int = 80,
        session: str = "",
        full: bool = False,
    ) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        route_kind = _coerce_trace_kind(kind)
        selected_limit = _coerce_limit(limit, 6, 40)
        selected_per_route_limit = _coerce_limit(per_route_limit, 20, 100)
        selected_before = _coerce_bounded_int(before, 3, 0, 24)
        selected_after = _coerce_limit(after, 8, 48)
        selected_raw_preview_chars = _coerce_bounded_int(raw_preview_chars, 600, 0, 2000)
        selected_document_limit = _coerce_limit(document_limit, 80, 200)
        args = [
            anchor_text,
            "--kind",
            route_kind,
            "--limit",
            str(selected_limit),
            "--per-route-limit",
            str(selected_per_route_limit),
            "--before",
            str(selected_before),
            "--after",
            str(selected_after),
            "--raw-preview-chars",
            str(selected_raw_preview_chars),
            "--document-limit",
            str(selected_document_limit),
            "--full",
        ]
        if session:
            args.extend(["--session", _safe_selector(session, "session")])
        if (
            not full
            and selected_raw_preview_chars == 0
            and selected_limit <= 3
            and selected_per_route_limit <= 3
            and selected_document_limit <= 10
        ):
            return self._usage_neighborhood_search_fast_path(
                anchor=anchor_text,
                kind=route_kind,
                requested_kind=kind,
                limit=selected_limit,
                per_route_limit=selected_per_route_limit,
                before=selected_before,
                after=selected_after,
                raw_preview_chars=selected_raw_preview_chars,
                document_limit=selected_document_limit,
                session=session,
                deep_args=args,
                reason="lightweight_mcp_probe",
            )
        full_route = self._archive_command_line("entity-usage-neighborhood", args)
        payload = self._archive_command(
            "entity-usage-neighborhood",
            args,
            allow_nonzero_json=True,
            timeout_seconds=min(max(self.timeout_seconds, 10.0), USAGE_NEIGHBORHOOD_TIMEOUT_SECONDS),
        )
        _annotate_trace_kind_payload(payload, requested_kind=kind, normalized_kind=route_kind)
        payload.setdefault("authority_boundary", self.authority_boundary())
        mcp_access = payload.get("mcp_access")
        if isinstance(mcp_access, dict):
            mcp_access["full_evidence_route"] = full_route
            mcp_access["response_compacted"] = not full
        if not payload.get("ok") or not payload.get("neighborhoods"):
            return self._usage_neighborhood_search_fast_path(
                anchor=anchor_text,
                kind=route_kind,
                requested_kind=kind,
                limit=selected_limit,
                per_route_limit=selected_per_route_limit,
                before=selected_before,
                after=selected_after,
                raw_preview_chars=selected_raw_preview_chars,
                document_limit=selected_document_limit,
                session=session,
                deep_args=args,
                reason="archive_route_unavailable",
                archive_payload=payload,
            )
        if full:
            return payload
        return _compact_entity_usage_neighborhood_payload(payload, full_route=full_route)

    def session_entity_dossier(
        self,
        anchor: str,
        kind: str = "auto",
        session: str = "",
        usage_limit: int = ENTITY_DOSSIER_USAGE_LIMIT,
        neighborhood_limit: int = ENTITY_DOSSIER_NEIGHBORHOOD_LIMIT,
        graph_limit: int = ENTITY_DOSSIER_GRAPH_LIMIT,
        graph_edge_limit: int = ENTITY_DOSSIER_GRAPH_EDGE_LIMIT,
    ) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        route_kind = _coerce_trace_kind(kind)
        selected_usage_limit = _coerce_limit(usage_limit, ENTITY_DOSSIER_USAGE_LIMIT, 40)
        selected_neighborhood_limit = _coerce_limit(neighborhood_limit, ENTITY_DOSSIER_NEIGHBORHOOD_LIMIT, 12)
        selected_graph_limit = _coerce_limit(graph_limit, ENTITY_DOSSIER_GRAPH_LIMIT, 80)
        selected_graph_edge_limit = _coerce_limit(graph_edge_limit, ENTITY_DOSSIER_GRAPH_EDGE_LIMIT, 240)
        safe_session = _safe_selector(session, "session") if session else ""
        registry_kind = route_kind if route_kind != "auto" else "all"
        route_key = _route_key(anchor_text)

        registry = self.session_entity_registry(kind=registry_kind, lookup=anchor_text, limit=5)
        usage = self.session_entity_usage_audit(
            anchor_text,
            kind=route_kind,
            limit=selected_usage_limit,
            per_route_limit=max(2, selected_usage_limit),
            consequence_window=6,
            document_limit=24,
            session=safe_session,
            full=False,
        )
        neighborhood = self.session_entity_usage_neighborhood(
            anchor_text,
            kind=route_kind,
            limit=selected_neighborhood_limit,
            per_route_limit=max(3, selected_usage_limit),
            before=2,
            after=6,
            raw_preview_chars=160,
            document_limit=24,
            session=safe_session,
            full=False,
        )
        graph = self.graph_neighborhood(
            anchor_text,
            kind=route_kind,
            depth=1,
            limit=selected_graph_limit,
            edge_limit=selected_graph_edge_limit,
        )

        source_entry = _first_registry_entry(registry)
        inferred_route_signal = source_entry.get("route_signal")
        if not inferred_route_signal and route_kind != "auto" and route_key:
            inferred_route_signal = f"{route_kind}:{route_key}"
        evidence = _collect_evidence_refs(
            [
                ("entity_registry", registry),
                ("entity_usage_audit", usage),
                ("entity_usage_neighborhood", neighborhood),
                ("graph_neighborhood", graph),
            ],
            limit=ENTITY_DOSSIER_EVIDENCE_REF_LIMIT,
        )
        usage_count = _payload_int(usage, "usage_event_count")
        consequence_count = _payload_int(usage, "consequence_event_count")
        window_count = _payload_int(neighborhood, "window_count")
        graph_node_count = _payload_int(graph, "node_count")
        graph_edge_count = _payload_int(graph, "edge_count")
        noise_flags: list[str] = []
        if not source_entry:
            noise_flags.append("source_identity_not_found_in_generated_entity_registry")
        if usage_count <= 0:
            noise_flags.append("no_usage_events_returned_by_usage_audit")
        if consequence_count <= 0:
            noise_flags.append("no_consequence_events_returned_by_usage_audit")
        if not evidence["raw_or_segment_ref_present"]:
            noise_flags.append("no_raw_or_segment_refs_in_compact_packet")
        graph_freshness = graph.get("freshness") if isinstance(graph.get("freshness"), dict) else {}
        if graph_freshness.get("needs_maintenance") or graph_freshness.get("status") in {"stale", "graph_store_stale"}:
            noise_flags.append("graph_freshness_requires_attention")

        usage_mcp_access = usage.get("mcp_access") if isinstance(usage.get("mcp_access"), dict) else {}
        neighborhood_mcp_access = neighborhood.get("mcp_access") if isinstance(neighborhood.get("mcp_access"), dict) else {}
        graph_mcp_access = graph.get("mcp_access") if isinstance(graph.get("mcp_access"), dict) else {}
        if graph_mcp_access.get("deep_archive_fallback_deferred"):
            noise_flags.append("graph_neighborhood_deep_expansion_deferred")
        next_expansion = [
            {
                "id": "full_usage_audit",
                "tool": "aoa_session_entity_usage_audit",
                "command": usage_mcp_access.get("full_evidence_route"),
                "use_when": "usage/consequence samples are insufficient or exact event refs need expansion",
            },
            {
                "id": "usage_neighborhood",
                "tool": "aoa_session_entity_usage_neighborhood",
                "command": neighborhood_mcp_access.get("full_evidence_route")
                or neighborhood_mcp_access.get("next_expansion_command"),
                "use_when": "before/after event windows or local consequence chains need inspection",
            },
            {
                "id": "graph_neighborhood",
                "tool": "aoa_session_graph_neighborhood",
                "command": graph.get("next_expansion_command") or graph_mcp_access.get("full_graph_route"),
                "use_when": "relation topology or adjacent operational anchors matter",
            },
            {
                "id": "source_identity",
                "tool": "aoa_session_entity_registry",
                "command": None,
                "use_when": "source surface identity or installed/known entity status matters",
            },
        ]
        next_expansion = [item for item in next_expansion if item.get("tool") or item.get("command")]
        packet = {
            "schema_version": 1,
            "artifact_type": "session_memory_entity_dossier",
            "ok": any(payload.get("ok") for payload in (registry, usage, neighborhood, graph) if isinstance(payload, dict)),
            "mutates": False,
            "anchor": anchor_text,
            "kind": route_kind,
            "requested_kind": kind,
            "session": safe_session,
            "normalized_entity": {
                "anchor": anchor_text,
                "route_key": route_key,
                "kind": route_kind,
                "requested_kind": kind,
                "route_signal": inferred_route_signal,
                "source_entity_id": source_entry.get("entity_id"),
                "canonical_key": source_entry.get("canonical_key") or route_key,
            },
            "source_identity": {
                "registry_status": registry.get("truth_status"),
                "registry_entity_count": registry.get("entity_count"),
                "registry_total_entity_count": registry.get("total_entity_count"),
                "registry_generated_at": registry.get("generated_at"),
                "entry": source_entry,
                "next_route": registry.get("next_route"),
            },
            "usage": _compact_dossier_usage(usage),
            "consequence_chain": {
                "usage_consequence_event_count": consequence_count,
                "neighborhood_window_count": window_count,
                "usage_consequence_events": usage.get("consequence_events", []),
                "neighborhoods": neighborhood.get("neighborhoods", []),
            },
            "neighborhood": _compact_dossier_neighborhood(neighborhood),
            "graph_neighborhood": _compact_dossier_graph(graph),
            "evidence": evidence,
            "freshness": {
                "registry_generated_at": registry.get("generated_at"),
                "usage_provider": usage.get("provider"),
                "neighborhood_provider": neighborhood.get("provider"),
                "graph": graph_freshness,
            },
            "quality": {
                "source_identity_present": bool(source_entry),
                "usage_event_count": usage_count,
                "consequence_event_count": consequence_count,
                "neighborhood_window_count": window_count,
                "graph_node_count": graph_node_count,
                "graph_edge_count": graph_edge_count,
                "raw_or_segment_ref_present": evidence["raw_or_segment_ref_present"],
                "noise_flag_count": len(noise_flags),
                "one_short_route": True,
            },
            "noise_flags": noise_flags,
            "next_expansion": next_expansion,
            "next_expansion_command": next((item.get("command") for item in next_expansion if item.get("command")), None),
            "mcp_access": {
                "mutates": False,
                "source_tools": [
                    "aoa_session_entity_registry",
                    "aoa_session_entity_usage_audit",
                    "aoa_session_entity_usage_neighborhood",
                    "aoa_session_graph_neighborhood",
                ],
                "response_compacted": True,
                "read_only_composite_route": True,
                "authority_boundary": "MCP composes compact route packets; .aoa raw/segment refs and owner source surfaces remain stronger.",
            },
            "authority_boundary": self.authority_boundary(),
        }
        return _without_omitted_field_counts(packet)

    def _usage_neighborhood_search_fast_path(
        self,
        *,
        anchor: str,
        kind: str,
        requested_kind: str | None = None,
        limit: int,
        per_route_limit: int,
        before: int,
        after: int,
        raw_preview_chars: int,
        document_limit: int,
        session: str,
        deep_args: list[str],
        reason: str,
        archive_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        route_attempts: list[dict[str, Any]] = []
        selected_hits: list[dict[str, Any]] = []
        selected_signal = None
        provider: dict[str, Any] | None = None
        search_limit = max(1, min(limit * max(1, per_route_limit), 20))
        for signal in self._usage_route_signal_candidates(kind=kind, anchor=anchor):
            filters = {"route_signal": signal, "doc_type": "event"}
            if session:
                filters["session"] = session
            search = self.session_search("", filters=filters, limit=search_limit)
            route_attempts.append(
                {
                    "route_signal": signal,
                    "ok": search.get("ok"),
                    "result_count": search.get("result_count", 0),
                    "provider_status": search.get("provider", {}).get("status")
                    if isinstance(search.get("provider"), dict)
                    else None,
                    "diagnostics": search.get("diagnostics", [])[:3]
                    if isinstance(search.get("diagnostics"), list)
                    else [],
                }
            )
            results = search.get("results") if isinstance(search.get("results"), list) else []
            selected_hits = [hit for hit in results if isinstance(hit, dict)]
            if search.get("ok") and selected_hits:
                selected_signal = signal
                provider = search.get("provider") if isinstance(search.get("provider"), dict) else None
                break

        neighborhoods = []
        for hit in selected_hits[:limit]:
            compact = _compact_hit(hit)
            source_event = {
                key: compact.get(key)
                for key in (
                    "doc_id",
                    "doc_type",
                    "session_id",
                    "session_label",
                    "session_title",
                    "session_date",
                    "segment_id",
                    "event_id",
                    "event_type",
                    "conversation_act",
                    "session_act",
                    "agent_event",
                    "task_episode_id",
                    "title",
                    "refs",
                    "freshness",
                    "route_signals",
                    "matched_routes",
                )
                if compact.get(key) not in (None, "", [], {})
            }
            source_event["raw_preview"] = {
                "status": "not_loaded",
                "reason": "mcp_search_fast_path",
            }
            neighborhoods.append(
                {
                    "ok": True,
                    "source": "mcp_search_route_signal_fast_path",
                    "source_usage_event": source_event,
                    "local_events": [],
                    "consequence_events": [],
                    "refs": compact.get("refs") or {},
                    "freshness": compact.get("freshness"),
                }
            )

        diagnostics = [f"served by MCP search-backed usage neighborhood fast path: {reason}"]
        if not neighborhoods:
            diagnostics.append("usage neighborhood fast path found no route-signal hits")
        if archive_payload is not None:
            diagnostics.extend(
                str(item)
                for item in archive_payload.get("diagnostics", [])
                if item
            )
        mcp_access = {
            "mutates": False,
            "archive_command": None,
            "fast_path": True,
            "fallback_reason": reason,
            "selected_route_signal": selected_signal,
            "next_expansion_command": self._archive_command_line("entity-usage-neighborhood", deep_args),
            "authority_boundary": "MCP fast path returns generated search refs; raw evidence remains authoritative.",
        }
        if archive_payload is not None:
            mcp_access["fallback_from"] = archive_payload.get("mcp_access", {})
        return {
            "schema_version": 1,
            "artifact_type": "session_memory_entity_usage_neighborhood",
            "ok": bool(neighborhoods),
            "mutates": False,
            "anchor": anchor,
            "kind": kind,
            **(
                {"requested_kind": _requested_trace_kind_key(requested_kind)}
                if requested_kind and _requested_trace_kind_key(requested_kind) != kind
                else {}
            ),
            "session": session or None,
            "window_count": len(neighborhoods),
            "neighborhoods": neighborhoods,
            "quality": {
                "usage_neighborhood_present": False,
                "usage_refs_present": bool(neighborhoods),
                "consequence_present": None,
                "consequence_evaluated": False,
                "consequence_status": "not_loaded_fast_path",
                "raw_preview_available": False,
                "neighborhood_count": len(neighborhoods),
                "local_event_count": 0,
                "consequence_event_count": 0,
                "fast_path": True,
            },
            "route_attempts": route_attempts,
            "provider": provider,
            "parameters": {
                "limit": limit,
                "per_route_limit": per_route_limit,
                "before": before,
                "after": after,
                "raw_preview_chars": raw_preview_chars,
                "document_limit": document_limit,
            },
            "diagnostics": diagnostics,
            "mcp_access": mcp_access,
            "authority_boundary": self.authority_boundary(),
        }

    def _usage_route_signal_candidates(self, *, kind: str, anchor: str) -> list[str]:
        anchor_text = str(anchor or "").strip()
        normalized_anchor = _route_key(anchor_text)
        normalized_kind = _normalize_trace_kind(kind or "auto")
        candidates: list[str] = []
        if ":" in anchor_text:
            candidates.append(anchor_text)
            prefix, _, value = anchor_text.partition(":")
            normalized_value = _route_key(value)
            normalized_prefix_kind = _normalize_trace_kind(prefix)
            if prefix and normalized_value:
                candidates.append(f"{_route_key(prefix)}:{normalized_value}")
            if normalized_prefix_kind and normalized_prefix_kind != "auto" and normalized_value:
                candidates.append(f"{normalized_prefix_kind}:{normalized_value}")
        if normalized_kind and normalized_kind != "auto" and normalized_anchor:
            candidates.append(f"{normalized_kind}:{normalized_anchor}")
            candidates.append(f"{normalized_kind}:{anchor_text}")
        elif normalized_anchor:
            for layer in (
                "tool",
                "mcp",
                "skill",
                "hook",
                "api",
                "plugin",
                "script",
                "validator",
                "test",
                "eval",
                "git",
                "playbook",
                "technique",
                "mechanic",
                "graph",
                "memory",
                "agent",
            ):
                candidates.append(f"{layer}:{normalized_anchor}")
        return list(dict.fromkeys(candidate for candidate in candidates if candidate and not candidate.endswith(":")))

    def session_entity_usage_scenario_audit(
        self,
        sample_size: int = 8,
        seed: str = "entity-usage-scenario-audit",
        layers: list[str] | None = None,
        min_postings: int = 1,
        limit: int = 8,
        per_route_limit: int = 8,
        consequence_window: int = 4,
        document_limit: int = 24,
        raw_preview_limit: int = 3,
        full: bool = False,
    ) -> dict[str, Any]:
        seed_text = _ensure_short_text(seed, "seed", limit=120)
        args = [
            "--seed",
            seed_text,
            "--sample-size",
            str(_coerce_limit(sample_size, 8, 50)),
            "--min-postings",
            str(_coerce_limit(min_postings, 1, 1000000)),
            "--limit",
            str(_coerce_limit(limit, 8, 50)),
            "--per-route-limit",
            str(_coerce_limit(per_route_limit, 8, 50)),
            "--consequence-window",
            str(_coerce_limit(consequence_window, 4, 24)),
            "--document-limit",
            str(_coerce_limit(document_limit, 24, 100)),
            "--raw-preview-limit",
            str(_coerce_limit(raw_preview_limit, 3, 20)),
        ]
        for layer in layers or []:
            args.extend(["--layer", _safe_selector(str(layer), "layer", limit=80)])
        if full:
            args.append("--full")
        payload = self._archive_command(
            "entity-usage-scenario-audit",
            args,
            allow_nonzero_json=True,
            timeout_seconds=max(self.timeout_seconds, EVIDENCE_PACKET_TIMEOUT_SECONDS),
        )
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def session_live_scenario_audit(
        self,
        seed: str = "live-scenario-audit",
        profiles: list[str] | None = None,
        sample_size: int = 4,
        recent_days: int = 7,
        limit: int = 3,
    ) -> dict[str, Any]:
        args = [
            "--seed",
            _ensure_short_text(seed, "seed", limit=120),
            "--sample-size",
            str(_coerce_limit(sample_size, 4, 12)),
            "--recent-days",
            str(_coerce_limit(recent_days, 7, 90)),
            "--limit",
            str(_coerce_limit(limit, 3, 10)),
        ]
        for profile in profiles or []:
            args.extend(["--profile", _safe_selector(str(profile), "profile", limit=80)])
        payload = self._archive_command(
            "live-scenario-audit",
            args,
            allow_nonzero_json=True,
            timeout_seconds=max(self.timeout_seconds, EVIDENCE_PACKET_TIMEOUT_SECONDS),
        )
        payload.setdefault("authority_boundary", self.authority_boundary())
        payload.setdefault(
            "mcp_route",
            {
                "canonical_route": "scripts/aoa_session_memory.py live-scenario-audit",
                "source_of_truth": ".aoa",
                "supported_profiles": SUPPORTED_LIVE_SCENARIO_PROFILES,
                "entity_registry_lookup_contract": (
                    "Checks active, observed, unknown, stale, and removed entity lookup status routing; "
                    "stale/removed probes are temporary previous-snapshot transitions and do not mutate the live archive."
                ),
                "next_route": "Use aoa_session_live_scenario_corpus_check when the result should be treated as a regression gate.",
            },
        )
        return payload

    def session_live_scenario_corpus_check(
        self,
        case_limit: int = 0,
        full: bool = False,
    ) -> dict[str, Any]:
        args = [
            "check",
            "--case-limit",
            str(_coerce_bounded_int(case_limit, 0, 0, 50)),
        ]
        if full:
            args.append("--full")
        payload = self._archive_command(
            "live-scenario-corpus",
            args,
            allow_nonzero_json=True,
            timeout_seconds=max(self.timeout_seconds, EVIDENCE_PACKET_TIMEOUT_SECONDS),
        )
        payload.setdefault("authority_boundary", self.authority_boundary())
        payload.setdefault(
            "mcp_route",
            {
                "canonical_corpus": "config/live-scenario-regression-corpus.json",
                "does_not_accept_arbitrary_corpus_path": True,
                "next_route": "Use full=true only when per-case observed route summaries are needed.",
            },
        )
        return payload

    def session_live_scenario_corpus_inventory(
        self,
        full: bool = False,
    ) -> dict[str, Any]:
        args = ["list"]
        if full:
            args.append("--full")
        payload = self._archive_command(
            "live-scenario-corpus",
            args,
            allow_nonzero_json=True,
            timeout_seconds=max(self.timeout_seconds, EVIDENCE_PACKET_TIMEOUT_SECONDS),
        )
        payload.setdefault("authority_boundary", self.authority_boundary())
        payload.setdefault(
            "mcp_route",
            {
                "canonical_corpus": "config/live-scenario-regression-corpus.json",
                "canonical_route": "scripts/aoa_session_memory.py live-scenario-corpus list",
                "does_not_run_cases": True,
                "next_route": "Use aoa_session_live_scenario_corpus_check for live regression proof.",
            },
        )
        return payload

    def session_retrieve(
        self,
        recipe: str = "continue-session",
        query: str = "",
        session: str = "",
        limit: int = 8,
        event_limit: int = 12,
    ) -> dict[str, Any]:
        recipe_text = _safe_selector(recipe, "recipe", limit=120)
        if _route_key(recipe_text) in ENTITY_USAGE_RETRIEVAL_RECIPES:
            if not str(query or "").strip():
                payload = {
                    "schema_version": 1,
                    "artifact_type": "retrieval_packet",
                    "ok": False,
                    "recipe": recipe_text,
                    "diagnostics": ["entity-usage retrieval requires query as the entity anchor"],
                    "mcp_access": {
                        "mutates": False,
                        "archive_command": "usage-chain",
                        "archive_dispatched": False,
                        "returncode": None,
                        "elapsed_ms": 0,
                        "timeout_seconds": self.timeout_seconds,
                        "stderr": "",
                        "authority_boundary": "MCP output routes to .aoa refs; it is not reviewed truth.",
                        "reason": "missing entity anchor",
                    },
                }
                payload.setdefault("authority_boundary", self.authority_boundary())
                return payload
            payload = self.session_entity_usage_chain(
                anchor=_ensure_short_text(query, "query"),
                kind="auto",
                limit=_coerce_limit(limit, 8, 50),
                per_route_limit=_coerce_limit(event_limit, 12, 60),
                session=session,
            )
            payload["recipe"] = recipe_text
            payload["retrieval_redirect"] = {
                "requested_recipe": recipe_text,
                "served_by": "aoa_session_entity_usage_chain",
                "reason": "entity usage is served by the compact read-only MCP usage-chain fast path, not a retrieve archive recipe",
            }
            payload.setdefault("diagnostics", []).append("served by entity-usage-chain retrieval redirect")
            return payload
        if recipe_text not in ALLOWED_RETRIEVAL_RECIPES:
            payload = {
                "schema_version": 1,
                "artifact_type": "retrieval_packet",
                "ok": False,
                "recipe": recipe_text,
                "diagnostics": [f"unsupported retrieval recipe for MCP access: {recipe_text}"],
                "mcp_known_recipes": sorted(ALLOWED_RETRIEVAL_RECIPES),
                "mcp_access": {
                    "mutates": False,
                    "archive_command": "retrieve",
                    "archive_dispatched": False,
                    "returncode": None,
                    "elapsed_ms": 0,
                    "timeout_seconds": self.timeout_seconds,
                    "stderr": "",
                    "authority_boundary": "MCP output routes to .aoa refs; it is not reviewed truth.",
                    "reason": "recipe is not in the MCP retrieval allowlist",
                },
            }
            payload.setdefault("authority_boundary", self.authority_boundary())
            return payload
        args = [recipe_text, "--limit", str(_coerce_limit(limit, 8, 50)), "--event-limit", str(_coerce_limit(event_limit, 12, 60))]
        if query:
            args.extend(["--query", _ensure_short_text(query, "query")])
        if session:
            args.extend(["--session", _safe_selector(session, "session")])
        payload = self._archive_command("retrieve", args, allow_nonzero_json=True)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def session_route(self, axis: str, key: str = "", limit: int = 20, include_entry_payloads: bool = False) -> dict[str, Any]:
        axis_name = _normalize_axis(axis)
        limit = _coerce_limit(limit, 20, 100)
        index_path = self.aoa_root / "maps" / axis_name / "index.json"
        index = _read_json(index_path)
        if not isinstance(index, dict):
            return {
                "schema": "aoa_session_memory_route_v1",
                "ok": False,
                "axis": axis_name,
                "diagnostics": [f"axis index not found or invalid: {index_path}"],
                "authority_boundary": self.authority_boundary(),
            }
        entries = [entry for entry in index.get("entries", []) if isinstance(entry, dict)]
        normalized_key = _route_key(key) if key else ""
        if normalized_key:
            exact = [entry for entry in entries if str(entry.get("route_key") or "") == normalized_key]
            matches = exact or [entry for entry in entries if normalized_key in str(entry.get("route_key") or "")]
        else:
            matches = entries
        selected = matches[:limit]
        entry_payloads = []
        if include_entry_payloads:
            for entry in selected[:20]:
                payload = self._read_map_entry_payload(axis_name, entry.get("json"))
                if payload is not None:
                    entry_payloads.append(payload)
        return {
            "schema": "aoa_session_memory_route_v1",
            "ok": True,
            "mutates": False,
            "axis": axis_name,
            "key": key,
            "normalized_key": normalized_key,
            "entry_count": index.get("entry_count", len(entries)),
            "match_count": len(matches),
            "entries": selected,
            "entry_payloads": entry_payloads,
            "index_path": index_path.as_posix(),
            "authority_boundary": self.authority_boundary(),
        }

    def session_brief(self, session: str = "latest", max_segments: int = 5) -> dict[str, Any]:
        session_dir = self._resolve_session_dir(session)
        if session_dir is None:
            return {
                "schema": "aoa_session_memory_brief_v1",
                "ok": False,
                "session": session,
                "diagnostics": ["session not found"],
                "authority_boundary": self.authority_boundary(),
            }
        manifest_path = session_dir / "session.manifest.json"
        index_path = session_dir / "session.index.json"
        manifest = _read_json(manifest_path)
        index = _read_json(index_path)
        if not isinstance(manifest, dict):
            manifest = {}
        if not isinstance(index, dict):
            index = {}
        display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
        source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
        raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
        raw_blocks = manifest.get("raw_blocks") if isinstance(manifest.get("raw_blocks"), dict) else {}
        blocks = raw_blocks.get("blocks") if isinstance(raw_blocks.get("blocks"), list) else []
        segments = self._segment_preview(index=index, manifest=manifest, limit=_coerce_limit(max_segments, 5, 30))
        return {
            "schema": "aoa_session_memory_brief_v1",
            "ok": True,
            "mutates": False,
            "session": {
                "session_id": manifest.get("session_id") or index.get("session_id"),
                "label": manifest.get("session_label") or display.get("label") or session_dir.name,
                "title": manifest.get("session_title") or display.get("title"),
                "path": session_dir.as_posix(),
                "cwd": source.get("cwd") or manifest.get("cwd") or index.get("work_context"),
                "work_context": manifest.get("work_context") or index.get("work_context") or source.get("cwd"),
                "archive_status": manifest.get("archive_status"),
                "review_status": manifest.get("review_status"),
                "distillation_status": manifest.get("distillation_status"),
                "event_count": manifest.get("event_count") or index.get("event_count"),
                "segment_count": manifest.get("segment_count") or index.get("segment_count"),
            },
            "refs": {
                "manifest": manifest_path.as_posix(),
                "index": index_path.as_posix(),
                "session_md": (session_dir / "SESSION.md").as_posix(),
                "raw": raw.get("path"),
                "raw_sha256": raw.get("sha256"),
                "blocks_index": raw.get("blocks_index") or raw_blocks.get("index"),
                "compaction_events": raw.get("compaction_events") or raw_blocks.get("compaction_events"),
            },
            "compaction": {
                "block_count": raw_blocks.get("block_count") or len(blocks),
                "latest_block": blocks[-1] if blocks else None,
            },
            "segments": segments,
            "read_order": [
                "session.manifest.json",
                "session.index.json",
                "relevant segment index",
                "relevant segment markdown",
                "raw refs only when exact verification is needed",
            ],
            "authority_boundary": self.authority_boundary(),
        }

    def session_evidence_packet(
        self,
        intent: str,
        query: str = "",
        anchors: list[str] | None = None,
        refs: list[str] | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        intent_text = _ensure_short_text(intent, "intent")
        limit = _coerce_limit(limit, 8, 30)
        query_text = query.strip() or intent_text
        trace_results = []
        for anchor in (anchors or [])[:5]:
            trace_results.append(self.session_trace(anchor=anchor, limit=limit, per_route_limit=5))
        search = self.session_search(query_text, filters={"explain": True}, limit=limit) if query_text else None
        effective_query = query_text
        if isinstance(search, dict) and int(search.get("result_count") or 0) == 0 and anchors:
            effective_query = anchors[0]
            search = self.session_search(effective_query, filters={"explain": True}, limit=limit)
        retrieve = (
            self.session_retrieve(recipe="continue-session", query=effective_query, limit=min(limit, 12), event_limit=8)
            if isinstance(search, dict) and int(search.get("result_count") or 0) > 0
            else None
        )
        freshness = self.session_freshness_check(refs or self._refs_from_payloads([search, retrieve, *trace_results]))
        return {
            "schema": "aoa_session_memory_evidence_packet_v1",
            "ok": True,
            "mutates": False,
            "intent": intent_text,
            "query": query_text,
            "effective_query": effective_query,
            "anchors": anchors or [],
            "candidate_posture": "candidate evidence for review; not a verdict and not durable memory",
            "search_hits": [] if not isinstance(search, dict) else [_compact_hit(hit) for hit in search.get("results", [])[:limit] if isinstance(hit, dict)],
            "retrieval_packet": retrieve,
            "route_traces": trace_results,
            "freshness": freshness,
            "next_routes": [
                "read returned raw_ref / segment_ref / session_ref before making claims",
                "use aoa-memo reviewed intake only after evidence is checked",
                "repair stale index or raw mismatch outside MCP if freshness_check reports missing refs",
            ],
            "authority_boundary": self.authority_boundary(),
        }

    def _session_identity_values(self, session_dir: Path | None, session: str = "") -> set[str]:
        values = {str(session).strip()} if str(session or "").strip() else set()
        if session_dir is None:
            return {value for value in values if value}
        values.add(session_dir.name)
        values.add(session_dir.as_posix())
        manifest = _read_json(session_dir / "session.manifest.json")
        if isinstance(manifest, dict):
            for key in ("session_id", "session_label", "session_title"):
                value = manifest.get(key)
                if value:
                    values.add(str(value))
            display = manifest.get("display")
            if isinstance(display, dict):
                for key in ("label", "title", "path", "archive_path", "navigation_path"):
                    value = display.get(key)
                    if value:
                        values.add(str(value))
        return {value for value in values if value}

    def _target_projection_freshness(
        self,
        provider: dict[str, Any],
        *,
        session_dir: Path | None,
        session: str = "",
    ) -> dict[str, Any]:
        providers = provider.get("providers") if isinstance(provider.get("providers"), dict) else {}
        portable = providers.get("portable_sqlite") if isinstance(providers.get("portable_sqlite"), dict) else {}
        freshness = portable.get("freshness") if isinstance(portable.get("freshness"), dict) else {}
        provider_status = str(portable.get("status") or "")

        if session_dir is None:
            return {
                "status": "not_checked",
                "target_dirty": None,
                "provider_status": provider_status or None,
                "reason": "session context not provided",
            }
        if not freshness:
            status = "current" if bool(portable.get("ok")) and provider_status in ("", "ready") else "unknown"
            return {
                "status": status,
                "target_dirty": False if status == "current" else None,
                "provider_status": provider_status or None,
                "reason": "provider did not return per-session freshness",
            }

        def session_values_from(*, ids_key: str, sessions_key: str) -> set[str]:
            values = {str(value) for value in freshness.get(ids_key, []) if value}
            for item in freshness.get(sessions_key, []) if isinstance(freshness.get(sessions_key), list) else []:
                if not isinstance(item, dict):
                    continue
                for key in ("session_id", "session_label", "session_dir"):
                    value = item.get(key)
                    if value:
                        values.add(str(value))
            return values

        target_values = self._session_identity_values(session_dir, session)
        has_actionable_fields = "actionable_dirty_session_ids" in freshness or "actionable_dirty_sessions" in freshness
        dirty_values = (
            session_values_from(ids_key="actionable_dirty_session_ids", sessions_key="actionable_dirty_sessions")
            if has_actionable_fields
            else session_values_from(ids_key="dirty_session_ids", sessions_key="dirty_sessions")
        )
        deferred_values = session_values_from(ids_key="", sessions_key="deferred_live_sessions")
        for item in freshness.get("dirty_sessions", []) if isinstance(freshness.get("dirty_sessions"), list) else []:
            if not isinstance(item, dict):
                continue
            for key in ("session_id", "session_label", "session_dir"):
                value = item.get(key)
                if value:
                    if not has_actionable_fields:
                        dirty_values.add(str(value))

        target_dirty = bool(target_values & dirty_values)
        target_deferred_live = bool(target_values & deferred_values)
        if target_dirty:
            status = "stale"
        elif target_deferred_live:
            status = "current_with_deferred_live_updates"
        elif str(freshness.get("status") or "") == "stale":
            status = "current_with_global_stale"
        elif str(freshness.get("status") or "") == "current_with_deferred_live_updates":
            status = "current_with_global_deferred_live_updates"
        elif str(freshness.get("status") or "") == "current":
            status = "current"
        else:
            status = "unknown"
        return {
            "status": status,
            "target_dirty": target_dirty,
            "target_deferred_live": target_deferred_live,
            "provider_status": provider_status or None,
            "global_status": freshness.get("status"),
            "dirty_session_count": freshness.get("dirty_session_count"),
            "actionable_dirty_session_count": freshness.get("actionable_dirty_session_count"),
            "deferred_live_session_count": freshness.get("deferred_live_session_count"),
            "target_values_checked": sorted(target_values)[:8],
        }

    def session_freshness_check(self, refs: list[str] | None = None, session: str = "") -> dict[str, Any]:
        refs = refs or []
        session_dir = self._resolve_session_dir(session) if session else None
        provider_session = session_dir.name if session_dir is not None else session
        provider_args = ["--provider", "portable_sqlite"]
        if provider_session:
            provider_args.extend(["--session", _safe_selector(provider_session, "session")])
        provider_full = self._archive_command(
            "search-provider-status",
            provider_args,
            timeout_seconds=max(self.timeout_seconds, STATUS_TIMEOUT_SECONDS),
        )
        diagnostics = []
        session_provider_fallback: dict[str, Any] | None = None
        if (
            provider_session
            and not provider_full.get("ok")
            and _session_provider_status_allows_global_fallback(provider_full)
        ):
            global_provider_args = ["--provider", "portable_sqlite"]
            global_provider = self._archive_command(
                "search-provider-status",
                global_provider_args,
                timeout_seconds=max(self.timeout_seconds, STATUS_TIMEOUT_SECONDS),
            )
            if global_provider.get("ok"):
                session_provider_fallback = _compact_provider_status_for_mcp(
                    provider_full,
                    full_freshness_route=self._archive_command_line("search-provider-status", provider_args),
                )
                provider_full = global_provider
                provider_args = global_provider_args
                diagnostics.append("provider_session_status_failed_using_global_freshness")
        elif provider_session and not provider_full.get("ok"):
            diagnostics.append("provider_session_status_failed_authoritative")
        checks = [self._check_ref(ref, session_dir=session_dir) for ref in refs[:100]]
        projection_freshness = self._target_projection_freshness(
            provider_full,
            session_dir=session_dir,
            session=session,
        )
        ref_failed = any(
            check["status"] not in {"present", "needs_session_context"}
            or check.get("inside_aoa_root") is False
            for check in checks
        )
        provider_allows_ref_check = bool(provider_full.get("ok")) or projection_freshness.get("status") == "current_with_global_stale"
        if projection_freshness.get("status") == "current_with_global_stale":
            diagnostics.append("provider_global_stale_target_session_current")
        elif projection_freshness.get("status") == "current_with_global_deferred_live_updates":
            diagnostics.append("provider_global_deferred_live_updates_target_session_current")
        elif projection_freshness.get("status") == "current_with_deferred_live_updates":
            diagnostics.append("provider_target_session_deferred_live_update")
        return {
            "schema": "aoa_session_memory_freshness_check_v1",
            "ok": provider_allows_ref_check and not ref_failed,
            "mutates": False,
            "provider": _compact_provider_status_for_mcp(
                provider_full,
                full_freshness_route=self._archive_command_line("search-provider-status", provider_args),
            ),
            "projection_freshness": projection_freshness,
            "ref_count": len(refs),
            "session": session or None,
            "checks": checks,
            "diagnostics": diagnostics,
            "session_provider_fallback": session_provider_fallback,
            "authority_boundary": self.authority_boundary(),
        }

    def session_pattern_scan(self, pattern: str, filters: dict[str, Any] | None = None, limit: int = 50) -> dict[str, Any]:
        search = self.session_search(pattern, filters=filters or {"explain": True}, limit=_coerce_limit(limit, 50, 100))
        hits = [hit for hit in search.get("results", []) if isinstance(hit, dict)]
        aggregates: dict[str, dict[str, int]] = {
            "event_type": {},
            "family": {},
            "conversation_act": {},
            "session_act": {},
            "route_layer": {},
            "route_signal": {},
            "session": {},
        }
        for hit in hits:
            self._bump(aggregates["event_type"], hit.get("event_type"))
            self._bump(aggregates["family"], hit.get("family"))
            self._bump(aggregates["conversation_act"], hit.get("conversation_act"))
            self._bump(aggregates["session_act"], hit.get("session_act"))
            self._bump(aggregates["session"], hit.get("session_label") or hit.get("session_id"))
            for layer in _split_pipe(hit.get("route_layers")):
                self._bump(aggregates["route_layer"], layer)
            for signal in _split_pipe(hit.get("route_signals")):
                self._bump(aggregates["route_signal"], signal)
        return {
            "schema": "aoa_session_memory_pattern_scan_v1",
            "ok": bool(search.get("ok")),
            "mutates": False,
            "pattern": pattern,
            "hit_count": len(hits),
            "aggregates": {key: self._top_counts(value) for key, value in aggregates.items()},
            "sample_hits": [_compact_hit(hit) for hit in hits[:12]],
            "search": search,
            "authority_boundary": self.authority_boundary(),
        }

    def session_entity_inventory(
        self,
        layer: str = "skill",
        query: str = "",
        session: str = "",
        limit: int = 50,
        sample_limit: int = 2,
    ) -> dict[str, Any]:
        input_layer_key = _safe_selector(str(layer or "skill"), "layer", limit=80)
        layer_key = INVENTORY_INPUT_LAYER_TO_ROUTE_LAYER.get(input_layer_key, input_layer_key)
        if layer_key not in ROUTE_LAYERS:
            raise ValueError(f"unsupported inventory layer: {layer_key}")
        selected_limit = _coerce_limit(limit, 50, 200)
        selected_sample_limit = _coerce_bounded_int(sample_limit, 2, 0, 5)
        query_text = str(query or "").strip()
        if query_text:
            query_text = _ensure_short_text(query_text, "query", limit=120)
        provider = self._compact_portable_provider_status()
        atlas_inventory = self._atlas_entity_inventory(
            layer_key=layer_key,
            query_text=query_text,
            session=session,
            limit=selected_limit,
            sample_limit=selected_sample_limit,
        )
        if atlas_inventory is not None:
            self._annotate_entity_inventory_payload(
                atlas_inventory,
                provider=provider,
                requested_layer=input_layer_key,
                normalized_layer=layer_key,
            )
            return atlas_inventory
        db_path = self.aoa_root / "search" / "aoa-search.sqlite3"
        if not db_path.is_file():
            payload = {
                "schema": "aoa_session_memory_entity_inventory_v1",
                "ok": False,
                "mutates": False,
                "layer": layer_key,
                "source": "portable_sqlite",
                "entity_count": 0,
                "entities": [],
                "diagnostics": [f"search db missing: {db_path}"],
                "truth_status": "session route-signal inventory; not runtime installed inventory",
                "authority_boundary": self.authority_boundary(),
            }
            self._annotate_entity_inventory_payload(
                payload,
                provider=provider,
                requested_layer=input_layer_key,
                normalized_layer=layer_key,
            )
            return payload
        filters = ["route_terms.layer = ?"]
        params: list[Any] = [layer_key]
        if query_text:
            like = f"%{_route_key(query_text)}%"
            filters.append("(route_terms.key LIKE ? OR route_terms.route_signal LIKE ?)")
            params.extend([like, like])
        if session:
            selectors = self._session_selector_terms(session)
            session_filters = []
            for selector in selectors:
                session_filters.append("(documents.session_id = ? OR documents.session_label LIKE ? OR documents.session_title LIKE ?)")
                params.extend([selector, f"%{selector}%", f"%{selector}%"])
            filters.append("(" + " OR ".join(session_filters) + ")")
        where = " AND ".join(filters)
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(
                f"{db_path.resolve().as_uri()}?mode=ro",
                uri=True,
            )
            conn.execute("PRAGMA query_only = ON")
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT
                    route_terms.key AS entity_key,
                    route_terms.route_signal AS route_signal,
                    COUNT(*) AS signal_count,
                    COUNT(DISTINCT documents.session_id) AS session_count,
                    MAX(documents.session_date) AS latest_session_date
                FROM route_terms
                JOIN document_routes ON document_routes.route_id = route_terms.id
                JOIN documents ON documents.rowid = document_routes.doc_rowid
                WHERE {where}
                GROUP BY route_terms.key, route_terms.route_signal
                ORDER BY signal_count DESC, session_count DESC, entity_key ASC
                LIMIT ?
                """,
                [*params, selected_limit],
            ).fetchall()
            entities: list[dict[str, Any]] = []
            for row in rows:
                samples = []
                if selected_sample_limit:
                    sample_rows = conn.execute(
                        f"""
                        SELECT
                            documents.id,
                            documents.doc_type,
                            documents.session_id,
                            documents.session_label,
                            documents.session_title,
                            documents.session_date,
                            documents.event_type,
                            documents.family,
                            documents.title,
                            documents.segment_ref,
                            documents.segment_index_path,
                            documents.raw_ref,
                            documents.raw_block_ref,
                            documents.manifest_path,
                            documents.freshness_status,
                            documents.stale_reason
                        FROM route_terms
                        JOIN document_routes ON document_routes.route_id = route_terms.id
                        JOIN documents ON documents.rowid = document_routes.doc_rowid
                        WHERE {where} AND route_terms.key = ?
                        ORDER BY documents.session_date DESC, documents.rowid DESC
                        LIMIT ?
                        """,
                        [*params, row["entity_key"], selected_sample_limit],
                    ).fetchall()
                    samples = [self._inventory_sample_from_row(sample) for sample in sample_rows]
                entities.append(
                    {
                        "key": row["entity_key"],
                        "route_signal": row["route_signal"],
                        "signal_count": int(row["signal_count"] or 0),
                        "session_count": int(row["session_count"] or 0),
                        "latest_session_date": row["latest_session_date"],
                        "samples": samples,
                    }
                )
            omitted_samples = self._bound_inventory_entity_samples(entities)
        except sqlite3.Error as exc:
            payload = {
                "schema": "aoa_session_memory_entity_inventory_v1",
                "ok": False,
                "mutates": False,
                "layer": layer_key,
                "source": "portable_sqlite",
                "entity_count": 0,
                "entities": [],
                "diagnostics": [f"sqlite_error:{exc}"],
                "truth_status": "session route-signal inventory; not runtime installed inventory",
                "authority_boundary": self.authority_boundary(),
            }
            self._annotate_entity_inventory_payload(
                payload,
                provider=provider,
                requested_layer=input_layer_key,
                normalized_layer=layer_key,
            )
            return payload
        finally:
            if conn is not None:
                conn.close()
        payload = {
            "schema": "aoa_session_memory_entity_inventory_v1",
            "ok": True,
            "mutates": False,
            "layer": layer_key,
            "query": query_text,
            "session": session or None,
            "source": "portable_sqlite",
            "entity_count": len(entities),
            "entities": entities,
            "sample_omitted_count": omitted_samples,
            "diagnostics": [],
            "truth_status": "session route-signal inventory; not runtime installed inventory",
            "authority_boundary": self.authority_boundary(),
        }
        self._annotate_entity_inventory_payload(
            payload,
            provider=provider,
            requested_layer=input_layer_key,
            normalized_layer=layer_key,
        )
        return payload

    def _annotate_entity_inventory_payload(
        self,
        payload: dict[str, Any],
        *,
        provider: dict[str, Any],
        requested_layer: str,
        normalized_layer: str,
    ) -> None:
        payload.setdefault("layer", normalized_layer)
        payload["requested_layer"] = requested_layer
        payload["normalized_layer"] = normalized_layer
        payload["runtime"] = self.runtime_identity()
        payload["provider"] = provider
        self._annotate_inventory_route_packet(payload, normalized_layer=normalized_layer)
        payload["mcp_access"] = {
            "mutates": False,
            "archive_command": None,
            "read_only_inventory_route": True,
            "provider_status_route": provider.get("mcp_access", {}).get("full_freshness_route")
            if isinstance(provider.get("mcp_access"), dict)
            else provider.get("full_freshness_route"),
            "authority_boundary": "MCP inventory reads generated atlas/search route indexes; raw transcript refs remain authoritative.",
            "runtime_reload_required": payload["runtime"].get("reload_required"),
        }
        if payload.get("next_expansion"):
            payload["mcp_access"]["next_expansion"] = payload["next_expansion"]

    def _annotate_inventory_route_packet(self, payload: dict[str, Any], *, normalized_layer: str) -> None:
        entities = payload.get("entities") if isinstance(payload.get("entities"), list) else []
        axis = INVENTORY_LAYER_TO_AXIS.get(normalized_layer)
        top_key = ""
        if entities and isinstance(entities[0], dict):
            top_key = str(entities[0].get("key") or "").strip()
        query_key = _route_key(str(payload.get("query") or ""))
        expansion_key = query_key or top_key
        sample_ref_packets: list[dict[str, Any]] = []
        sample_count = 0
        signal_count = 0
        session_count = 0
        latest_session_date: str | None = None
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            try:
                signal_count += int(entity.get("signal_count") or 0)
            except (TypeError, ValueError):
                pass
            try:
                session_count += int(entity.get("session_count") or 0)
            except (TypeError, ValueError):
                pass
            entity_date = entity.get("latest_session_date")
            if entity_date and (latest_session_date is None or str(entity_date) > latest_session_date):
                latest_session_date = str(entity_date)
            samples = entity.get("samples") if isinstance(entity.get("samples"), list) else []
            sample_count += len(samples)
            for sample in samples[:1]:
                if not isinstance(sample, dict):
                    continue
                refs = sample.get("refs") if isinstance(sample.get("refs"), dict) else {}
                packet = {
                    "entity": entity.get("key"),
                    "session_id": sample.get("session_id"),
                    "session_label": _bounded_string(sample.get("session_label"), INVENTORY_SAMPLE_LABEL_CHARS),
                    "session_date": sample.get("session_date"),
                    "raw": refs.get("raw"),
                    "segment": refs.get("segment"),
                }
                sample_ref_packets.append({key: value for key, value in packet.items() if value not in (None, "", [], {})})
                if len(sample_ref_packets) >= 12:
                    break
            if len(sample_ref_packets) >= 12:
                break
        next_expansion: dict[str, Any]
        if axis:
            route_args = {
                "axis": axis,
                "key": expansion_key,
                "limit": max(20, min(100, len(entities) or 20)),
                "include_entry_payloads": True,
            }
            next_expansion = {
                "mcp_tool": "aoa_session_route",
                "arguments": route_args,
                "command": (
                    "aoa_session_route("
                    f"axis={axis!r}, key={expansion_key!r}, "
                    f"limit={route_args['limit']!r}, include_entry_payloads=True)"
                ),
            }
        else:
            route_signal = f"{normalized_layer}:{expansion_key}" if expansion_key else ""
            filters = {"route_layer": normalized_layer}
            if route_signal:
                filters["route_signal"] = route_signal
            next_expansion = {
                "mcp_tool": "aoa_session_search",
                "arguments": {"query": "", "filters": filters, "limit": 20},
                "command": f"aoa_session_search(query='', filters={filters!r}, limit=20)",
            }
        payload["route_packet"] = {
            "bounded": True,
            "source": payload.get("source"),
            "layer": normalized_layer,
            "axis": axis,
            "query": payload.get("query") or "",
            "session": payload.get("session"),
            "returned_entity_count": len(entities),
            "sample_ref_count": len(sample_ref_packets),
            "aggregate_signal_count": signal_count,
            "aggregate_session_count": session_count,
            "latest_session_date": latest_session_date,
            "sample_refs": sample_ref_packets,
        }
        payload["response_profile"] = {
            "bounded_mcp_packet": True,
            "sample_shape": "compact_refs_only",
            "raw_text_loaded": False,
            "entry_payloads_loaded": False,
            "sample_count": sample_count,
            "sample_omitted_count": int(payload.get("sample_omitted_count") or 0),
            "sample_budget": INVENTORY_TOTAL_SAMPLE_LIMIT,
            "next_expansion_required_for_entry_payloads": True,
        }
        payload["next_expansion"] = next_expansion
        payload["next_expansion_command"] = next_expansion.get("command")

    def session_entity_registry(
        self,
        kind: str = "all",
        query: str = "",
        lookup: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        kind_key = _safe_selector(str(kind or "all"), "kind", limit=80)
        query_text = str(query or "").strip()
        lookup_text = str(lookup or "").strip()
        selected_limit = _coerce_limit(limit, 50, 500)
        payload = self._entity_registry_snapshot(kind_key=kind_key, query_text=query_text, lookup_text=lookup_text, limit=selected_limit)
        payload["authority_boundary"] = self.authority_boundary()
        payload["mcp_access"] = {
            "mutates": False,
            "archive_command": None,
            "read_model": (self.aoa_root / "maps" / "entity-registry.json").as_posix(),
            "read_only_registry_route": True,
            "write_route": self._archive_command_line("entity-registry", ["--kind", kind_key, "--write"]),
            "write_requires_operator_outside_mcp": True,
            "timeout_risk_avoided": "MCP reads the generated registry snapshot directly; refresh/write stays outside MCP.",
        }
        return payload

    def _entity_registry_snapshot(self, *, kind_key: str, query_text: str, lookup_text: str, limit: int) -> dict[str, Any]:
        path = self.aoa_root / "maps" / "entity-registry.json"
        snapshot = _read_json(path)
        if not isinstance(snapshot, dict):
            return {
                "schema_version": 1,
                "artifact_type": "entity_registry_snapshot",
                "ok": False,
                "mutates": False,
                "registry_path": path.as_posix(),
                "kind": kind_key,
                "query": query_text,
                "lookup": lookup_text,
                "total_entity_count": 0,
                "entity_count": 0,
                "entries": [],
                "diagnostics": ["entity_registry_snapshot_missing"],
                "truth_status": "generated_entity_registry_navigation_not_source_truth",
            }
        entries = snapshot.get("entries") if isinstance(snapshot.get("entries"), list) else []
        selected: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if not self._entity_registry_kind_matches(str(entry.get("kind") or ""), kind_key):
                continue
            if query_text and not self._entity_registry_query_matches(entry, query_text):
                continue
            if lookup_text and not self._entity_registry_lookup_matches(entry, lookup_text):
                continue
            selected.append(entry)
            if len(selected) >= limit:
                break
        kind_counts = Counter(str(item.get("kind") or "unknown") for item in selected if isinstance(item, dict))
        status_counts = Counter(str(item.get("status") or "unknown") for item in selected if isinstance(item, dict))
        return {
            "schema_version": snapshot.get("schema_version", 1),
            "artifact_type": "entity_registry_snapshot",
            "generated_at": snapshot.get("generated_at"),
            "generated_at_epoch": snapshot.get("generated_at_epoch"),
            "ok": bool(snapshot.get("ok", True)),
            "mutates": False,
            "aoa_root": self.aoa_root.as_posix(),
            "registry_path": path.as_posix(),
            "source": "generated_entity_registry_snapshot",
            "source_surfaces": snapshot.get("source_surfaces", []),
            "source_truth_surfaces": snapshot.get("source_truth_surfaces", []),
            "total_entity_count": snapshot.get("entity_count", len(entries)),
            "entity_count": len(selected),
            "counts_by_kind": dict(sorted(kind_counts.items())),
            "counts_by_status": dict(sorted(status_counts.items())),
            "snapshot_counts_by_kind": snapshot.get("counts_by_kind", {}),
            "snapshot_counts_by_status": snapshot.get("counts_by_status", {}),
            "query": query_text,
            "lookup": lookup_text,
            "kind": kind_key,
            "entries": selected,
            "diagnostics": snapshot.get("diagnostics", []) if isinstance(snapshot.get("diagnostics"), list) else [],
            "next_route": snapshot.get("next_route") or "Use trace-route/search/graph/entity-usage-audit for observed use; open source_refs for source truth.",
            "truth_status": snapshot.get("truth_status") or "generated_entity_registry_navigation_not_source_truth",
        }

    def _entity_registry_kind_matches(self, entry_kind: str, kind_key: str) -> bool:
        normalized_kind = _route_key(kind_key)
        normalized_entry = _route_key(entry_kind)
        if normalized_kind in {"all", "any", "entity", "entities"}:
            return True
        if normalized_kind == "mcp":
            return normalized_entry.startswith("mcp")
        return normalized_entry == normalized_kind

    def _entity_registry_query_matches(self, entry: dict[str, Any], query_text: str) -> bool:
        needle = query_text.casefold()
        haystacks = [
            entry.get("entity_id"),
            entry.get("canonical_key"),
            entry.get("route_signal"),
            entry.get("owner"),
            entry.get("source_surface"),
            *(entry.get("aliases") if isinstance(entry.get("aliases"), list) else []),
        ]
        return any(needle in str(value or "").casefold() for value in haystacks)

    def _entity_registry_lookup_matches(self, entry: dict[str, Any], lookup_text: str) -> bool:
        needle = lookup_text.casefold()
        normalized = _route_key(lookup_text)
        aliases = entry.get("aliases") if isinstance(entry.get("aliases"), list) else []
        candidates = [
            entry.get("entity_id"),
            entry.get("canonical_key"),
            entry.get("route_signal"),
            *aliases,
        ]
        return any(needle == str(value or "").casefold() or normalized == _route_key(str(value or "")) for value in candidates)

    def _atlas_entity_inventory(
        self,
        *,
        layer_key: str,
        query_text: str,
        session: str,
        limit: int,
        sample_limit: int,
    ) -> dict[str, Any] | None:
        axis = INVENTORY_LAYER_TO_AXIS.get(layer_key)
        if not axis:
            return None
        index_path = self.aoa_root / "maps" / axis / "index.json"
        if not index_path.is_file():
            return None
        payload = _read_json(index_path)
        if not isinstance(payload, dict):
            return {
                "schema": "aoa_session_memory_entity_inventory_v1",
                "ok": False,
                "mutates": False,
                "layer": layer_key,
                "query": query_text,
                "session": session or None,
                "source": "atlas",
                "atlas_index": index_path.as_posix(),
                "entity_count": 0,
                "entities": [],
                "diagnostics": [f"atlas index unreadable: {index_path}"],
                "truth_status": "session route-signal inventory; not runtime installed inventory",
                "authority_boundary": self.authority_boundary(),
            }
        entries = payload.get("entries")
        if not isinstance(entries, list):
            entries = []
        query_key = _route_key(query_text) if query_text else ""
        session_selectors = self._session_selector_terms(session) if session else []
        aggregates: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            route_key = str(entry.get("route_key") or "").strip()
            if not route_key:
                continue
            normalized_key = _route_key(route_key)
            route_signal = f"{layer_key}:{normalized_key or route_key}"
            if query_key and query_key not in normalized_key and query_key not in _route_key(route_signal):
                continue
            session_id = str(entry.get("session_id") or "").strip()
            session_label = str(entry.get("session") or "").strip()
            if session_selectors:
                comparable = " ".join([session_id, session_label]).casefold()
                if not any(selector.casefold() in comparable for selector in session_selectors):
                    continue
            detail_entry: dict[str, Any] | None = None
            signal_count = int(entry.get("signal_count") or 0)
            if signal_count <= 0 and entry.get("json"):
                detail = self._read_map_entry_payload(axis, entry.get("json"))
                if isinstance(detail, dict):
                    detail_entry = {**entry, **detail}
                    signal_count = int(detail.get("signal_count") or 0)
            bucket = aggregates.setdefault(
                normalized_key or route_key,
                {
                    "key": normalized_key or route_key,
                    "route_signal": route_signal,
                    "signal_count": 0,
                    "sessions": set(),
                    "latest_session_date": None,
                    "samples": [],
                },
            )
            bucket["signal_count"] += max(signal_count, 1)
            if session_id:
                bucket["sessions"].add(session_id)
            elif session_label:
                bucket["sessions"].add(session_label)
            session_date = _session_date_from_entry(detail_entry or entry)
            if session_date and (bucket["latest_session_date"] is None or session_date > bucket["latest_session_date"]):
                bucket["latest_session_date"] = session_date
            if len(bucket["samples"]) < sample_limit:
                bucket["samples"].append(self._inventory_sample_from_atlas_entry(detail_entry or entry))
        entities = sorted(
            aggregates.values(),
            key=lambda item: (-int(item["signal_count"]), -len(item["sessions"]), str(item["key"])),
        )[:limit]
        cleaned_entities = [
            {
                "key": item["key"],
                "route_signal": item["route_signal"],
                "signal_count": int(item["signal_count"]),
                "session_count": len(item["sessions"]),
                "latest_session_date": item["latest_session_date"],
                "samples": item["samples"],
            }
            for item in entities
        ]
        omitted_samples = self._bound_inventory_entity_samples(cleaned_entities)
        return {
            "schema": "aoa_session_memory_entity_inventory_v1",
            "ok": True,
            "mutates": False,
            "layer": layer_key,
            "query": query_text,
            "session": session or None,
            "source": "atlas",
            "atlas_axis": axis,
            "atlas_index": index_path.as_posix(),
            "atlas_generated_at": payload.get("generated_at"),
            "entity_count": len(cleaned_entities),
            "entities": cleaned_entities,
            "sample_omitted_count": omitted_samples,
            "diagnostics": [],
            "truth_status": "session route-signal inventory; not runtime installed inventory",
            "authority_boundary": self.authority_boundary(),
        }

    def _bound_inventory_entity_samples(self, entities: list[dict[str, Any]]) -> int:
        sample_lists = [entity.get("samples") if isinstance(entity.get("samples"), list) else [] for entity in entities]
        total = sum(len(samples) for samples in sample_lists)
        if total <= INVENTORY_TOTAL_SAMPLE_LIMIT:
            return 0
        keep_counts = [0 for _ in sample_lists]
        remaining = INVENTORY_TOTAL_SAMPLE_LIMIT
        for idx, samples in enumerate(sample_lists):
            if remaining <= 0:
                break
            if samples:
                keep_counts[idx] = 1
                remaining -= 1
        while remaining > 0:
            progressed = False
            for idx, samples in enumerate(sample_lists):
                if remaining <= 0:
                    break
                if len(samples) > keep_counts[idx]:
                    keep_counts[idx] += 1
                    remaining -= 1
                    progressed = True
            if not progressed:
                break
        for entity, keep_count in zip(entities, keep_counts):
            samples = entity.get("samples") if isinstance(entity.get("samples"), list) else []
            entity["samples"] = samples[:keep_count]
        return max(0, total - sum(keep_counts))

    def _inventory_sample_from_atlas_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
        refs = {
            "segment": evidence.get("segment_ref"),
            "raw": evidence.get("raw_ref"),
        }
        sample = {
            "doc_type": "atlas_entry",
            "session_id": entry.get("session_id"),
            "session_label": _bounded_string(entry.get("session"), INVENTORY_SAMPLE_LABEL_CHARS),
            "session_date": _session_date_from_entry(entry),
            "event_type": entry.get("event_type"),
            "family": entry.get("family"),
            "confidence": entry.get("confidence"),
            "refs": {key: value for key, value in refs.items() if value},
            "freshness": {"status": "atlas_generated", "reasons": []},
        }
        return {key: value for key, value in sample.items() if value not in (None, "", [], {})}

    def _inventory_sample_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        refs = {
            "segment": row["segment_ref"],
            "raw": row["raw_ref"],
            "raw_block": row["raw_block_ref"],
        }
        sample = {
            "doc_type": row["doc_type"],
            "session_id": row["session_id"],
            "session_label": _bounded_string(row["session_label"], INVENTORY_SAMPLE_LABEL_CHARS),
            "session_date": row["session_date"],
            "event_type": row["event_type"],
            "family": row["family"],
            "refs": {key: value for key, value in refs.items() if value},
            "freshness": {
                "status": row["freshness_status"],
                "reasons": [row["stale_reason"]] if row["stale_reason"] else [],
            },
        }
        return {key: value for key, value in sample.items() if value not in (None, "", [], {})}

    def session_hook_receipts(
        self,
        event_name: str = "UserPromptSubmit",
        session: str = "",
        date_from: str = "",
        only_errors: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        event_filter = str(event_name or "").strip()
        if event_filter:
            event_filter = _safe_selector(event_filter, "event_name", limit=80)
        if session:
            session = _safe_selector(session, "session", limit=180)
        from_time = _parse_iso_time(date_from) if date_from else None
        if date_from and from_time is None:
            raise ValueError("date_from must be ISO-8601 date or timestamp")
        selected_limit = _coerce_limit(limit, 50, 500)
        session_dirs = self._receipt_session_dirs(session)
        diagnostics: list[str] = []
        if session and not session_dirs:
            diagnostics.append("session not found")

        matches: list[dict[str, Any]] = []
        hook_counts: dict[str, int] = {}
        action_counts: dict[str, int] = {}
        session_counts: dict[str, int] = {}
        durations: list[float] = []
        parse_error_count = 0
        scanned_line_count = 0
        scanned_receipt_files = 0

        for session_dir in session_dirs:
            receipt_path = session_dir / "hooks" / "receipts.jsonl"
            if not receipt_path.is_file():
                continue
            scanned_receipt_files += 1
            manifest = _read_json(session_dir / "session.manifest.json")
            if not isinstance(manifest, dict):
                manifest = {}
            display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
            session_id = str(manifest.get("session_id") or session_dir.name)
            session_label = str(manifest.get("session_label") or display.get("label") or session_dir.name)
            session_title = manifest.get("session_title") or display.get("title")
            try:
                handle = receipt_path.open("r", encoding="utf-8")
            except OSError as exc:
                diagnostics.append(f"could not read receipts for {session_label}: {exc}")
                continue
            with handle:
                for line_number, line in enumerate(handle, start=1):
                    scanned_line_count += 1
                    try:
                        receipt = json.loads(line)
                    except json.JSONDecodeError:
                        parse_error_count += 1
                        continue
                    if not isinstance(receipt, dict):
                        parse_error_count += 1
                        continue
                    hook_event = str(
                        receipt.get("hook_event_name")
                        or receipt.get("event_name")
                        or (receipt.get("payload") if isinstance(receipt.get("payload"), dict) else {}).get("hook_event_name")
                        or ""
                    )
                    if event_filter and hook_event.casefold() != event_filter.casefold():
                        continue
                    timestamp = receipt.get("timestamp") or receipt.get("received_at") or receipt.get("generated_at")
                    parsed_time = _parse_iso_time(timestamp)
                    if from_time is not None and (parsed_time is None or parsed_time < from_time):
                        continue
                    errors = receipt.get("errors") if isinstance(receipt.get("errors"), list) else []
                    actions = receipt.get("actions") if isinstance(receipt.get("actions"), list) else []
                    typing_bridge = receipt.get("typing_bridge") if isinstance(receipt.get("typing_bridge"), dict) else {}
                    hard_failed = receipt.get("ok") is False
                    typing_bridge_failed = typing_bridge.get("ok") is False
                    error_like = hard_failed or typing_bridge_failed or bool(errors)
                    if only_errors and not error_like:
                        continue

                    duration = receipt.get("duration_ms") if isinstance(receipt.get("duration_ms"), (int, float)) else None
                    if duration is not None:
                        durations.append(float(duration))
                    self._bump(hook_counts, hook_event or "unknown")
                    self._bump(session_counts, session_label)
                    for action in actions:
                        self._bump(action_counts, action)
                    matches.append(
                        {
                            "timestamp": timestamp,
                            "_parsed_timestamp": parsed_time.isoformat() if parsed_time is not None else "",
                            "hook_event_name": hook_event or None,
                            "ok": receipt.get("ok"),
                            "session_id": session_id,
                            "session_label": session_label,
                            "session_title": session_title,
                            "actions": [str(action) for action in actions],
                            "error_count": len(errors),
                            "errors": [str(error)[:1000] for error in errors[:5]],
                            "duration_ms": duration,
                            "typing_bridge": {
                                "ok": typing_bridge.get("ok"),
                                "status": typing_bridge.get("status"),
                                "adapter": typing_bridge.get("adapter"),
                                "returncode": typing_bridge.get("returncode"),
                                "typing_status": typing_bridge.get("typing_status"),
                                "capture_gate_decision": typing_bridge.get("capture_gate_decision"),
                                "stderr_head": str(typing_bridge.get("stderr_head") or "")[:1000] or None,
                            }
                            if typing_bridge
                            else None,
                            "refs": {
                                "session": (session_dir / "session.manifest.json").as_posix(),
                                "receipt": f"{receipt_path.as_posix()}#L{line_number}",
                            },
                        }
                    )

        matches.sort(key=lambda item: (str(item.get("_parsed_timestamp") or ""), str(item.get("session_label") or "")), reverse=True)
        for item in matches:
            item.pop("_parsed_timestamp", None)
        error_receipt_count = sum(1 for item in matches if item.get("ok") is False or int(item.get("error_count") or 0) > 0 or (item.get("typing_bridge") or {}).get("ok") is False)
        hard_failure_count = sum(1 for item in matches if item.get("ok") is False)
        typing_bridge_failure_count = sum(1 for item in matches if (item.get("typing_bridge") or {}).get("ok") is False)
        duration_summary = {
            "count": len(durations),
            "min_ms": round(min(durations), 2) if durations else None,
            "avg_ms": round(sum(durations) / len(durations), 2) if durations else None,
            "max_ms": round(max(durations), 2) if durations else None,
        }
        return {
            "schema": "aoa_session_memory_hook_receipts_v1",
            "ok": not bool(session and not session_dirs),
            "mutates": False,
            "event_name": event_filter or None,
            "session": session or None,
            "date_from": date_from or None,
            "date_semantics": _hook_receipt_date_semantics(date_from),
            "only_errors": only_errors,
            "scanned_receipt_files": scanned_receipt_files,
            "scanned_line_count": scanned_line_count,
            "parse_error_count": parse_error_count,
            "total_receipt_count": len(matches),
            "returned_receipt_count": min(len(matches), selected_limit),
            "summary": {
                "error_receipt_count": error_receipt_count,
                "hard_failure_count": hard_failure_count,
                "typing_bridge_failure_count": typing_bridge_failure_count,
                "hook_event_counts": self._top_counts(hook_counts),
                "action_counts": self._top_counts(action_counts),
                "session_counts": self._top_counts(session_counts),
                "duration_ms": duration_summary,
            },
            "receipts": matches[:selected_limit],
            "diagnostics": diagnostics,
            "truth_status": "hook receipt evidence; not generated search or graph truth",
            "authority_boundary": self.authority_boundary(),
        }

    def latest_diagnostics(self, kind: str = "route-layer-readiness", limit: int = 5, include_payload: bool = False) -> dict[str, Any]:
        safe_kind = _route_key(kind).replace("_", "-")
        patterns = [f"*{safe_kind}*.json"]
        if safe_kind == "route-readiness":
            patterns.append("*route-layer-readiness*.json")
        diagnostics_dir = self.aoa_root / "diagnostics"
        paths: list[Path] = []
        for pattern in patterns:
            paths.extend(diagnostics_dir.glob(pattern))
        unique_paths = sorted(set(paths), key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
        selected = unique_paths[: _coerce_limit(limit, 5, 25)]
        reports = []
        for path in selected:
            payload = _read_json(path)
            reports.append(
                {
                    "path": path.as_posix(),
                    "mtime": path.stat().st_mtime if path.exists() else None,
                    "summary": _compact_diagnostic(payload),
                    "payload": payload if include_payload else None,
                }
            )
        return {
            "schema": "aoa_session_memory_latest_diagnostics_v1",
            "ok": bool(reports),
            "mutates": False,
            "kind": kind,
            "diagnostics_dir": diagnostics_dir.as_posix(),
            "count": len(reports),
            "reports": reports,
            "authority_boundary": self.authority_boundary(),
        }

    def session_maintenance_status(
        self,
        *,
        deep: bool = False,
        include_timers: bool = True,
        full: bool = False,
    ) -> dict[str, Any]:
        args: list[str] = []
        if deep:
            args.append("--deep")
        if not include_timers:
            args.append("--no-timers")
        if full:
            args.append("--full")
        payload = self._archive_command(
            "maintenance-status",
            args,
            allow_nonzero_json=True,
            timeout_seconds=max(self.timeout_seconds, STATUS_TIMEOUT_SECONDS),
        )
        payload.setdefault("mutates", False)
        payload.setdefault("runtime", self.runtime_identity())
        payload.setdefault("authority_boundary", self.authority_boundary())
        mcp_access = payload.get("mcp_access")
        if isinstance(mcp_access, dict):
            mcp_access["response_compacted"] = not full
            mcp_access["full_status_route"] = self._archive_command_line("maintenance-status", [*args, "--full"] if not full else args)
            runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
            mcp_access["runtime_reload_required"] = runtime.get("reload_required")
        return payload

    def session_operational_route_rollup_query(
        self,
        query: str = "",
        *,
        layer: str = "tool",
        key: str = "",
        route_signal: str = "",
        limit: int = 12,
        ref_limit: int = 3,
    ) -> dict[str, Any]:
        args: list[str] = []
        text = str(query or "").strip()
        if text:
            args.append(_safe_selector(text, "query", limit=160))
        for flag, value, field in (
            ("--layer", layer, "layer"),
            ("--key", key, "key"),
            ("--route-signal", route_signal, "route_signal"),
        ):
            if value:
                args.extend([flag, _safe_selector(str(value), field, limit=160)])
        args.extend(
            [
                "--limit",
                str(_coerce_limit(limit, 12, 100)),
                "--ref-limit",
                str(_coerce_bounded_int(ref_limit, 3, 0, 25)),
            ]
        )
        payload = self._archive_command(
            "search-operational-route-rollup-query",
            args,
            allow_nonzero_json=True,
            timeout_seconds=max(self.timeout_seconds, ROUTE_ROLLUP_QUERY_TIMEOUT_SECONDS),
        )
        payload.setdefault("mutates", False)
        payload.setdefault("authority_boundary", self.authority_boundary())
        mcp_access = payload.get("mcp_access")
        if isinstance(mcp_access, dict):
            mcp_access["response_compacted"] = True
            mcp_access["does_not_materialize_rollup"] = True
            mcp_access["does_not_resample_shards"] = True
            mcp_access["full_route"] = self._archive_command_line("search-operational-route-rollup-query", args)
        return payload

    def session_operational_direct_event_rollup_query(
        self,
        query: str = "",
        *,
        usage_role: str = "result",
        event_type: str = "",
        session_act: str = "",
        layer: str = "",
        key: str = "",
        route_signal: str = "",
        limit: int = 12,
        ref_limit: int = 3,
    ) -> dict[str, Any]:
        args: list[str] = []
        text = str(query or "").strip()
        if text:
            args.append(_safe_selector(text, "query", limit=160))
        for flag, value, field in (
            ("--usage-role", usage_role, "usage_role"),
            ("--event-type", event_type, "event_type"),
            ("--session-act", session_act, "session_act"),
            ("--layer", layer, "layer"),
            ("--key", key, "key"),
            ("--route-signal", route_signal, "route_signal"),
        ):
            if value:
                args.extend([flag, _safe_selector(str(value), field, limit=160)])
        args.extend(
            [
                "--limit",
                str(_coerce_limit(limit, 12, 100)),
                "--ref-limit",
                str(_coerce_bounded_int(ref_limit, 3, 0, 25)),
            ]
        )
        payload = self._archive_command(
            "search-operational-direct-event-rollup-query",
            args,
            allow_nonzero_json=True,
            timeout_seconds=max(self.timeout_seconds, DIRECT_EVENT_ROLLUP_QUERY_TIMEOUT_SECONDS),
        )
        payload.setdefault("mutates", False)
        payload.setdefault("authority_boundary", self.authority_boundary())
        mcp_access = payload.get("mcp_access")
        if isinstance(mcp_access, dict):
            mcp_access["response_compacted"] = True
            mcp_access["does_not_materialize_rollup"] = True
            mcp_access["does_not_resample_shards"] = True
            mcp_access["does_not_open_monolith"] = True
            mcp_access["does_not_use_fts"] = True
            mcp_access["does_not_hydrate_body"] = True
            mcp_access["behavior_proof_route"] = "usage-chain"
            mcp_access["full_route"] = self._archive_command_line("search-operational-direct-event-rollup-query", args)
        return payload

    def _maintenance_summary_for_status(self) -> dict[str, Any]:
        payload = self.session_maintenance_status(include_timers=False, full=False)
        mcp_access = payload.get("mcp_access") if isinstance(payload.get("mcp_access"), dict) else {}
        if payload.get("artifact_type") != "session_memory_maintenance_status":
            return {
                "ok": False,
                "source": "maintenance-status",
                "diagnostics": payload.get("diagnostics", ["maintenance-status returned unexpected payload"]),
                "mcp_access": {
                    "elapsed_ms": mcp_access.get("elapsed_ms"),
                    "returncode": mcp_access.get("returncode"),
                },
            }
        agent_route = payload.get("agent_route") if isinstance(payload.get("agent_route"), dict) else {}
        search = payload.get("search") if isinstance(payload.get("search"), dict) else {}
        graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
        route = payload.get("route") if isinstance(payload.get("route"), dict) else {}
        entity_registry = payload.get("entity_registry") if isinstance(payload.get("entity_registry"), dict) else {}
        operations = payload.get("operations") if isinstance(payload.get("operations"), dict) else {}
        search_shards = operations.get("search_shards") if isinstance(operations.get("search_shards"), dict) else {}
        raw_text_fallback = (
            search_shards.get("raw_text_fallback_dependency")
            if isinstance(search_shards.get("raw_text_fallback_dependency"), dict)
            else {}
        )
        fast_path_defaults = (
            search_shards.get("fast_path_defaults")
            if isinstance(search_shards.get("fast_path_defaults"), dict)
            else {}
        )
        agent_event_fast_path = (
            fast_path_defaults.get("agent_event_routes")
            if isinstance(fast_path_defaults.get("agent_event_routes"), dict)
            else {}
        )
        latest_materialization = (
            search_shards.get("latest_materialization")
            if isinstance(search_shards.get("latest_materialization"), dict)
            else {}
        )
        latest_slow_sessions = (
            latest_materialization.get("slow_sessions")
            if isinstance(latest_materialization.get("slow_sessions"), list)
            else []
        )
        return {
            "ok": bool(payload.get("ok")),
            "source": "maintenance-status",
            "generated_at": payload.get("generated_at"),
            "recommendation": payload.get("recommendation"),
            "agent_route": {
                "action": agent_route.get("action"),
                "can_use_graph_search": agent_route.get("can_use_graph_search"),
                "maintenance_required": agent_route.get("maintenance_required"),
                "live_catchup_pending": agent_route.get("live_catchup_pending"),
                "deferred_live_count": agent_route.get("deferred_live_count"),
                "raw_or_deep_route": agent_route.get("raw_or_deep_route"),
            },
            "search": {
                "status": search.get("status"),
                "actionable_dirty_session_count": search.get("actionable_dirty_session_count"),
                "deferred_live_session_count": search.get("deferred_live_session_count"),
            },
            "graph": {
                "status": graph.get("status"),
                "needs_maintenance": graph.get("needs_maintenance"),
                "dirty_count": graph.get("dirty_count"),
                "missing_count": graph.get("missing_count"),
                "blocked_count": graph.get("blocked_count"),
                "actionable_count": graph.get("actionable_count"),
            },
            "route": {
                "status": route.get("status"),
                "needs_index_maintenance": route.get("needs_index_maintenance"),
                "needs_graph_maintenance": route.get("needs_graph_maintenance"),
            },
            "entity_registry": {
                "status": entity_registry.get("status"),
                "entity_count": entity_registry.get("entity_count"),
            },
            "search_shards": {
                "status": search_shards.get("status"),
                "shard_count": search_shards.get("shard_count"),
                "materialized_shard_count": search_shards.get("materialized_shard_count"),
                "raw_text_query_route": search_shards.get("raw_text_query_route"),
                "latest_materialization": {
                    "exists": latest_materialization.get("exists"),
                    "ok": latest_materialization.get("ok"),
                    "status": latest_materialization.get("status"),
                    "target": latest_materialization.get("target"),
                    "requested_shard": latest_materialization.get("requested_shard"),
                    "processed_count": latest_materialization.get("processed_count"),
                    "document_count": latest_materialization.get("document_count"),
                    "elapsed_ms": latest_materialization.get("elapsed_ms"),
                    "documents_per_second": latest_materialization.get("documents_per_second"),
                    "sessions_per_second": latest_materialization.get("sessions_per_second"),
                    "slow_session_warning_count": latest_materialization.get("slow_session_warning_count"),
                    "slow_session_threshold_ms": latest_materialization.get("slow_session_threshold_ms"),
                    "slow_sessions": [
                        {
                            key: item.get(key)
                            for key in (
                                "shard",
                                "session_id",
                                "session_label",
                                "status",
                                "raw_text_status",
                                "document_count",
                                "elapsed_ms",
                                "documents_per_second",
                                "warning",
                            )
                            if isinstance(item, dict) and key in item
                        }
                        for item in latest_slow_sessions[:4]
                        if isinstance(item, dict)
                    ],
                },
                "fast_path_defaults": {
                    "agent_event_routes": {
                        "default_use_shards": agent_event_fast_path.get("default_use_shards"),
                        "default_projection": agent_event_fast_path.get("default_projection"),
                        "raw_text_query_projection": agent_event_fast_path.get("raw_text_query_projection"),
                        "raw_text_fallback_dependency_status": agent_event_fast_path.get("raw_text_fallback_dependency_status"),
                        "raw_text_fallback_dependency_next_route": agent_event_fast_path.get("raw_text_fallback_dependency_next_route"),
                    }
                },
                "raw_text_fallback_dependency": {
                    "status": raw_text_fallback.get("status"),
                    "raw_text_query_support": raw_text_fallback.get("raw_text_query_support"),
                    "monolith_fallback_db_path": raw_text_fallback.get("monolith_fallback_db_path"),
                    "full_text_shard_count": raw_text_fallback.get("full_text_shard_count"),
                    "structured_only_shard_count": raw_text_fallback.get("structured_only_shard_count"),
                    "unsupported_shard_count": raw_text_fallback.get("unsupported_shard_count"),
                    "nonmaterialized_shard_count": raw_text_fallback.get("nonmaterialized_shard_count"),
                    "route_blocked_shard_count": raw_text_fallback.get("route_blocked_shard_count"),
                    "route_blocked_shards": raw_text_fallback.get("route_blocked_shards", [])[:8]
                    if isinstance(raw_text_fallback.get("route_blocked_shards"), list)
                    else [],
                    "scoped_full_text_next_commands": raw_text_fallback.get("scoped_full_text_next_commands", [])[:3]
                    if isinstance(raw_text_fallback.get("scoped_full_text_next_commands"), list)
                    else [],
                    "global_full_text_next_command": raw_text_fallback.get("global_full_text_next_command"),
                    "quality_tradeoff": raw_text_fallback.get("quality_tradeoff"),
                    "weight_tradeoff": raw_text_fallback.get("weight_tradeoff"),
                    "authority_boundary": raw_text_fallback.get("authority_boundary"),
                    "next_route": raw_text_fallback.get("next_route"),
                },
            },
            "next_actions": payload.get("next_actions", [])[:3] if isinstance(payload.get("next_actions"), list) else [],
            "exact_next_command": payload.get("exact_next_command"),
            "mcp_access": {
                "elapsed_ms": mcp_access.get("elapsed_ms"),
                "returncode": mcp_access.get("returncode"),
            },
            "truth_status": "canonical_hot_maintenance_summary_for_agent_routing",
        }

    def maintenance_plan(self) -> dict[str, Any]:
        payload = self.session_maintenance_status(include_timers=False)
        payload["compatibility_tool"] = "aoa_session_maintenance_plan"
        payload["preferred_tool"] = "aoa_session_maintenance_status"
        return payload

    def session_projection_status(self, include_payload: bool = False) -> dict[str, Any]:
        diagnostics = self.latest_diagnostics(kind="projection-catchup", limit=1, include_payload=True)
        reports = diagnostics.get("reports") if isinstance(diagnostics.get("reports"), list) else []
        latest = reports[0] if reports and isinstance(reports[0], dict) else {}
        latest_payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else {}
        completeness = latest_payload.get("projection_completeness")
        if not isinstance(completeness, dict):
            completeness = latest_payload.get("completeness_check") if isinstance(latest_payload.get("completeness_check"), dict) else {}
        completeness_has_current_schema = (
            isinstance(completeness, dict)
            and completeness.get("artifact_type") == "session_memory_projection_completeness"
            and isinstance(completeness.get("surfaces"), dict)
        )
        completeness_current = (
            completeness_has_current_schema
            and completeness.get("status") == "current"
            and not completeness.get("actionable_surface_ids")
            and not completeness.get("deferred_surface_ids")
            and all(
                isinstance(surface, dict)
                and surface.get("status") == "current"
                and surface.get("needs_maintenance") is not True
                for surface in completeness.get("surfaces", {}).values()
            )
        )
        next_route = latest_payload.get("next_route") if isinstance(latest_payload.get("next_route"), dict) else {}
        maintenance = self._maintenance_summary_for_status()
        refresh_route = {
            "id": "run_projection_catchup_outside_mcp",
            "status": "needed",
            "reason": (
                "projection_completeness_stale"
                if completeness_has_current_schema
                else "projection_completeness_missing_or_legacy"
            ),
            "command": self._archive_argv("projection-catchup", ["all", "--write-report"]),
        }
        payload = {
            "schema": "aoa_session_memory_projection_status_v1",
            "ok": completeness_current,
            "mutates": False,
            "source": (
                "latest_projection_catchup_diagnostic"
                if completeness_current
                else (
                    "stale_projection_catchup_diagnostic"
                    if completeness_has_current_schema
                    else ("legacy_projection_catchup_diagnostic" if completeness else "missing_projection_catchup_diagnostic")
                )
            ),
            "projection_completeness": completeness,
            "latest_projection_catchup": {
                "path": latest.get("path"),
                "mtime": latest.get("mtime"),
                "summary": latest.get("summary"),
                "payload": latest_payload if include_payload else None,
            },
            "current_maintenance": maintenance,
            "next_operator_route": next_route if completeness_current and next_route else refresh_route,
            "diagnostics": [] if completeness_current else [refresh_route["reason"]],
            "mcp_access": {
                "mutates": False,
                "archive_command": None,
                "read_only": True,
                "does_not_run_projection_catchup": True,
                "writer_route_stays_outside_mcp": True,
                "elapsed_ms": (maintenance.get("mcp_access") or {}).get("elapsed_ms") if isinstance(maintenance.get("mcp_access"), dict) else None,
            },
            "authority_boundary": self.authority_boundary(),
        }
        return payload

    def graph_neighborhood(
        self,
        anchor: str,
        kind: str = "auto",
        depth: int = 1,
        limit: int = 40,
        edge_limit: int | None = None,
    ) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        route_kind = _coerce_trace_kind(kind, error_label="graph kind")
        bounded_depth = _coerce_limit(depth, 1, 3)
        bounded_limit = _coerce_limit(limit, 40, 200)
        args = [
            anchor_text,
            "--kind",
            route_kind,
            "--depth",
            str(bounded_depth),
            "--limit",
            str(bounded_limit),
        ]
        bounded_edge_limit = GRAPH_EDGE_SAMPLE_LIMIT
        if edge_limit is not None:
            bounded_edge_limit = _coerce_limit(edge_limit, 40, 2000)
            args.extend(["--edge-limit", str(bounded_edge_limit)])
        full_route = self._archive_command_line("graph-neighborhood", args)
        fast_payload = self._graph_neighborhood_sqlite_fast_path(
            anchor=anchor_text,
            kind=route_kind,
            depth=bounded_depth,
            limit=bounded_limit,
            edge_limit=bounded_edge_limit,
            full_route=full_route,
        )
        if fast_payload is not None:
            return _compact_graph_payload(
                fast_payload,
                full_route=full_route,
                node_limit=min(bounded_limit, GRAPH_NODE_SAMPLE_LIMIT),
                edge_limit=min(bounded_edge_limit, GRAPH_EDGE_SAMPLE_LIMIT),
            )
        admission = self._resource_admitted_archive_route(
            "graph-neighborhood",
            args,
            workload_class="medium",
        )
        payload = self._graph_neighborhood_deferred_payload(
            anchor=anchor_text,
            requested_kind=kind,
            kind=route_kind,
            depth=bounded_depth,
            limit=bounded_limit,
            edge_limit=bounded_edge_limit,
            full_route=full_route,
            admission=admission,
        )
        return _compact_graph_payload(
            payload,
            full_route=full_route,
            node_limit=min(bounded_limit, GRAPH_NODE_SAMPLE_LIMIT),
            edge_limit=min(bounded_edge_limit, GRAPH_EDGE_SAMPLE_LIMIT),
        )

    def _graph_neighborhood_deferred_payload(
        self,
        *,
        anchor: str,
        requested_kind: str,
        kind: str,
        depth: int,
        limit: int,
        edge_limit: int,
        full_route: str,
        admission: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "schema_version": 1,
            "artifact_type": "session_memory_graph_neighborhood",
            "ok": False,
            "mutates": False,
            "anchor": anchor,
            "kind": kind,
            "requested_kind": requested_kind,
            "depth": depth,
            "parameters": {
                "limit": limit,
                "edge_limit": edge_limit,
            },
            "source": "mcp_bounded_graph_deferred",
            "node_count": 0,
            "edge_count": 0,
            "nodes": [],
            "edges": [],
            "evidence_refs": [],
            "freshness": {
                "status": "bounded_graph_route_unresolved",
                "checked": False,
            },
            "quality": {
                "route": "indexed_graph_only",
                "direct_sqlite_fast_path": False,
                "deep_archive_fallback_executed": False,
            },
            "diagnostics": ["bounded_graph_route_unresolved_deep_archive_fallback_deferred"],
            "next_expansion_command": str((admission or {}).get("launch_command") or full_route),
            "next_expansion_reason": (
                "The compact MCP route found no indexed graph node. Run the named archive command "
                "outside MCP through owner-aware resource admission when deep expansion is justified."
            ),
            "mcp_access": {
                "mutates": False,
                "archive_command": None,
                "deep_archive_fallback_executed": False,
                "deep_archive_fallback_deferred": True,
                "owner_admission_required": bool(admission),
                "full_graph_route": full_route,
                "authority_boundary": "MCP stays on bounded read models; deep archive expansion requires owner admission.",
            },
            "authority_boundary": self.authority_boundary(),
        }
        if admission:
            payload["mcp_access"]["owner_admission"] = admission
        return payload

    def _graph_neighborhood_read_error_payload(
        self,
        *,
        anchor: str,
        kind: str,
        depth: int,
        limit: int,
        edge_limit: int,
        full_route: str,
        db_path: Path,
        reason: str,
    ) -> dict[str, Any]:
        maintenance_route = self._archive_command_line("maintenance-status", [])
        payload = self._graph_neighborhood_deferred_payload(
            anchor=anchor,
            requested_kind=kind,
            kind=kind,
            depth=depth,
            limit=limit,
            edge_limit=edge_limit,
            full_route=full_route,
        )
        payload.update(
            {
                "source": "mcp_graph_read_model_error",
                "freshness": {
                    "status": "graph_store_read_failed",
                    "checked": True,
                    "read_model": db_path.as_posix(),
                },
                "quality": {
                    "route": "generated_graph_read_model",
                    "direct_sqlite_fast_path": False,
                    "deep_archive_fallback_executed": False,
                },
                "diagnostics": [f"graph_store_read_failed:{reason}"],
                "next_expansion_command": maintenance_route,
                "next_expansion_reason": (
                    "Inspect generated graph health before retrying the bounded read or requesting "
                    "owner-admitted deep expansion."
                ),
            }
        )
        payload["mcp_access"].update(
            {
                "read_model": db_path.as_posix(),
                "read_model_read_failed": True,
                "maintenance_status_route": maintenance_route,
                "authority_boundary": "MCP reports the generated read-model failure; graph repair remains outside MCP.",
            }
        )
        return payload

    def _graph_neighborhood_node_candidates(self, *, anchor: str, kind: str) -> list[str]:
        if anchor.startswith("route:") or anchor.startswith("event:") or anchor.startswith("session:") or anchor.startswith("segment:"):
            return [anchor]
        explicit_route = _explicit_route_signal_parts(anchor)
        key = explicit_route[1] if explicit_route else _route_key(anchor)
        if not key:
            return []
        kinds = [explicit_route[0]] if explicit_route else [kind]
        if kind == "auto":
            kinds.extend(["mcp", "skill", "tool", "hook", "api", "script", "validator", "test", "eval", "graph", "memory", "goal", "git"])
        elif kind not in kinds:
            kinds.append(kind)
        candidates = [f"route:{explicit_route[0]}:{explicit_route[2]}"] if explicit_route else []
        for route_kind in dict.fromkeys(kinds):
            route_key = _route_key(route_kind)
            if not route_key:
                continue
            candidates.append(f"route:{route_key}:{route_key}:{key}")
            candidates.append(f"route:{route_key}:entity:entity_{key}")
        return list(dict.fromkeys(candidates))

    def _graph_route_term_db_paths(self) -> list[Path]:
        shard_root = self.aoa_root / "search" / "shards"
        try:
            resolved_root = shard_root.resolve(strict=True)
        except OSError:
            return []
        candidates: list[Path] = []
        catalog = _read_json(self.aoa_root / "search" / "catalog.json")
        entries = catalog.get("shards") if isinstance(catalog, dict) and isinstance(catalog.get("shards"), list) else []
        for entry in reversed(entries):
            if not isinstance(entry, dict):
                continue
            raw_path = entry.get("shard_db_path")
            if not raw_path:
                continue
            path = Path(str(raw_path))
            if not path.is_absolute():
                path = self.aoa_root / path
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(resolved_root)
            except (OSError, ValueError):
                continue
            if resolved.is_file() and resolved not in candidates:
                candidates.append(resolved)
        if not candidates:
            for path in sorted(shard_root.glob("*/aoa-search.sqlite3"), reverse=True):
                try:
                    resolved = path.resolve(strict=True)
                    resolved.relative_to(resolved_root)
                except (OSError, ValueError):
                    continue
                if resolved.is_file() and resolved not in candidates:
                    candidates.append(resolved)
        return candidates[:GRAPH_ROUTE_TERM_SHARD_LIMIT]

    def _graph_route_term_node_candidates(self, *, anchor: str, kind: str) -> tuple[list[str], dict[str, Any]]:
        explicit_route = _explicit_route_signal_parts(anchor)
        anchor_key = explicit_route[1] if explicit_route else _route_key(anchor)
        if len(anchor_key) < 3:
            return [], {
                "strategy": "sharded_route_terms",
                "status": "anchor_too_short",
                "requested_key": anchor_key,
                "matched_route_term_count": 0,
            }
        namespace_prefixes = (
            "",
            "aoa_session_",
            "aoa_session_memory_",
            "aoa_session_memory_mcp_",
            "aoa_session_memory_mcp_aoa_session_",
        )
        base_keys = [anchor_key]
        for prefix in namespace_prefixes[1:]:
            if anchor_key.startswith(prefix):
                stripped = anchor_key[len(prefix) :]
                if stripped:
                    base_keys.append(stripped)
        candidate_keys: list[str] = []
        for base_key in base_keys:
            for prefix in namespace_prefixes:
                candidate = f"{prefix}{base_key}"
                if candidate not in candidate_keys:
                    candidate_keys.append(candidate)
        route_layers = [explicit_route[0] if explicit_route else kind, kind, "entity", "tool", "mcp_tool", "mcp", "skill", "script", "hook", "command", "api"]
        candidate_signals = [explicit_route[2]] if explicit_route else []
        candidate_signals.extend(
            f"{layer}:{key}"
            for layer in route_layers
            if layer not in {"", "auto", "all"}
            for key in candidate_keys
        )
        candidate_signals = list(dict.fromkeys(candidate_signals))[:GRAPH_ROUTE_TERM_MATCH_LIMIT]
        node_ids: list[str] = []
        matches: list[dict[str, str]] = []
        checked_paths: list[str] = []
        diagnostics: list[str] = []
        for db_path in self._graph_route_term_db_paths():
            conn: sqlite3.Connection | None = None
            try:
                conn = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True, timeout=0.25)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA query_only = ON")
                conn.execute("PRAGMA busy_timeout = 250")
                if not self._sqlite_table_exists(conn, "route_terms"):
                    continue
                checked_paths.append(db_path.as_posix())
                remaining = max(1, GRAPH_ROUTE_TERM_MATCH_LIMIT - len(node_ids))
                placeholders = ", ".join("?" for _ in candidate_signals)
                rows = conn.execute(
                    f"""
                    SELECT layer, key, route_signal
                    FROM route_terms
                    WHERE route_signal IN ({placeholders})
                    ORDER BY
                      CASE WHEN layer = ? THEN 0 WHEN layer = 'entity' THEN 1 ELSE 2 END,
                      CASE WHEN key = ? THEN 0 ELSE 1 END,
                      LENGTH(key),
                      key
                    LIMIT ?
                    """,
                    (*candidate_signals, kind, anchor_key, remaining),
                ).fetchall()
                for row in rows:
                    layer = str(row["layer"] or "")
                    key = str(row["key"] or "")
                    signal = str(row["route_signal"] or "")
                    if not layer or not key or not signal:
                        continue
                    node_id = f"route:{layer}:{signal}"
                    if node_id in node_ids:
                        continue
                    node_ids.append(node_id)
                    if len(matches) < 12:
                        matches.append({"layer": layer, "key": key, "route_signal": signal})
                    if len(node_ids) >= GRAPH_ROUTE_TERM_MATCH_LIMIT:
                        break
            except sqlite3.Error as exc:
                diagnostics.append(f"route_terms_read_failed:{db_path.name}:{exc.__class__.__name__}")
            finally:
                if conn is not None:
                    conn.close()
            if len(node_ids) >= GRAPH_ROUTE_TERM_MATCH_LIMIT:
                break
        return node_ids, {
            "strategy": "sharded_route_terms",
            "status": "matched" if node_ids else "no_match",
            "requested_key": anchor_key,
            "candidate_route_signal_count": len(candidate_signals),
            "matched_route_term_count": len(node_ids),
            "matched_route_terms": matches,
            "checked_read_models": checked_paths,
            "diagnostics": diagnostics,
        }

    def _loads_graph_payload(self, value: Any) -> dict[str, Any]:
        if not value:
            return {}
        try:
            payload = json.loads(str(value))
        except (TypeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _graph_sqlite_row_payload(self, row: sqlite3.Row, *, kind: str) -> dict[str, Any]:
        payload = self._loads_graph_payload(row["payload_json"])
        result = {
            "id": row["id"],
            "type": payload.get("type") or payload.get("node_type") or kind,
            "count": row["count"],
            **payload,
        }
        result.setdefault("id", row["id"])
        result.setdefault("type", kind)
        result.setdefault("count", row["count"])
        return result

    def _graph_sqlite_edge_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = self._loads_graph_payload(row["payload_json"])
        result = {
            "id": row["id"],
            "type": payload.get("type") or row["edge_type"],
            "source": row["source_node"],
            "target": row["target_node"],
            "count": row["count"],
            **payload,
        }
        result.setdefault("id", row["id"])
        result.setdefault("type", row["edge_type"])
        result.setdefault("source", row["source_node"])
        result.setdefault("target", row["target_node"])
        result.setdefault("count", row["count"])
        return result

    def _graph_sqlite_evidence_refs(self, conn: sqlite3.Connection, *, node_ids: list[str], edge_ids: list[str], limit: int = 50) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        if node_ids and self._sqlite_table_exists(conn, "node_contribs"):
            placeholders = ", ".join("?" for _ in node_ids)
            for row in conn.execute(
                f"""
                SELECT payload_json
                FROM node_contribs
                WHERE node_id IN ({placeholders})
                LIMIT ?
                """,
                [*node_ids, limit],
            ).fetchall():
                payload = self._loads_graph_payload(row["payload_json"])
                payload_refs = payload.get("evidence_refs")
                if isinstance(payload_refs, list):
                    refs.extend(ref for ref in payload_refs if isinstance(ref, dict))
                    if len(refs) >= limit:
                        return refs[:limit]
        if edge_ids and self._sqlite_table_exists(conn, "edge_contribs"):
            placeholders = ", ".join("?" for _ in edge_ids)
            for row in conn.execute(
                f"""
                SELECT payload_json
                FROM edge_contribs
                WHERE edge_id IN ({placeholders})
                LIMIT ?
                """,
                [*edge_ids, limit],
            ).fetchall():
                payload = self._loads_graph_payload(row["payload_json"])
                payload_refs = payload.get("evidence_refs")
                if isinstance(payload_refs, list):
                    refs.extend(ref for ref in payload_refs if isinstance(ref, dict))
                    if len(refs) >= limit:
                        return refs[:limit]
        return refs[:limit]

    def _graph_neighborhood_sqlite_fast_path(
        self,
        *,
        anchor: str,
        kind: str,
        depth: int,
        limit: int,
        edge_limit: int,
        full_route: str,
    ) -> dict[str, Any] | None:
        db_path = self.aoa_root / "graph" / "graph.sqlite3"
        if not db_path.is_file():
            return None
        candidates = self._graph_neighborhood_node_candidates(anchor=anchor, kind=kind)
        if not candidates:
            return None
        conn: sqlite3.Connection | None = None
        route_term_resolution: dict[str, Any] = {
            "strategy": "synthetic_exact_candidates",
            "status": "not_needed",
            "matched_route_term_count": 0,
        }
        edge_query_truncated = False
        omitted_node_count = 0
        omitted_edge_count = 0
        try:
            conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, timeout=0.5)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA busy_timeout = 500")
            if not self._sqlite_table_exists(conn, "nodes") or not self._sqlite_table_exists(conn, "edges"):
                return self._graph_neighborhood_read_error_payload(
                    anchor=anchor,
                    kind=kind,
                    depth=depth,
                    limit=limit,
                    edge_limit=edge_limit,
                    full_route=full_route,
                    db_path=db_path,
                    reason="missing_required_schema",
                )

            def start_rows_for(node_ids: list[str]) -> list[sqlite3.Row]:
                if not node_ids:
                    return []
                placeholders = ", ".join("?" for _ in node_ids)
                return conn.execute(
                    f"""
                    SELECT id, node_type, payload_json, count
                    FROM nodes
                    WHERE id IN ({placeholders})
                    LIMIT ?
                    """,
                    [*node_ids, min(max(1, limit), 20)],
                ).fetchall()

            start_rows = start_rows_for(candidates)
            if not start_rows:
                route_term_candidates, route_term_resolution = self._graph_route_term_node_candidates(
                    anchor=anchor,
                    kind=kind,
                )
                candidates = list(dict.fromkeys([*candidates, *route_term_candidates]))
                start_rows = start_rows_for(candidates)
            if not start_rows:
                return None
            start_ids = [str(row["id"]) for row in start_rows]
            node_limit = max(1, min(limit, 200))
            edge_budget = max(1, min(edge_limit, GRAPH_SQLITE_EDGE_BUDGET_MAX))
            queue: deque[tuple[str, int]] = deque()
            queued_ids: set[str] = set()
            for node_id in start_ids:
                if len(queue) >= node_limit:
                    omitted_node_count += 1
                    continue
                queue.append((node_id, 0))
                queued_ids.add(node_id)
            selected_node_ids: list[str] = []
            selected_node_set: set[str] = set()
            selected_edge_rows: list[sqlite3.Row] = []
            seen_edge_ids: set[str] = set()
            while queue and len(selected_node_ids) < node_limit:
                node_id, distance = queue.popleft()
                if node_id in selected_node_set:
                    continue
                selected_node_ids.append(node_id)
                selected_node_set.add(node_id)
                if distance >= depth:
                    continue
                if len(selected_edge_rows) >= edge_budget:
                    edge_query_truncated = True
                    continue
                fetched: list[sqlite3.Row] = []
                local_edge_ids: set[str] = set()
                for column in ("source_node", "target_node"):
                    rows = conn.execute(
                        f"""
                        SELECT id, edge_type, source_node, target_node, payload_json, count
                        FROM edges
                        WHERE {column} = ?
                        ORDER BY count DESC, id
                        LIMIT ?
                        """,
                        (node_id, edge_budget + 1),
                    ).fetchall()
                    if len(rows) > edge_budget:
                        edge_query_truncated = True
                    for row in rows:
                        edge_id = str(row["id"])
                        if edge_id in local_edge_ids:
                            continue
                        local_edge_ids.add(edge_id)
                        fetched.append(row)
                fetched.sort(key=lambda row: (-int(row["count"] or 0), str(row["id"])))
                for row in fetched:
                    edge_id = str(row["id"])
                    if edge_id in seen_edge_ids:
                        continue
                    seen_edge_ids.add(edge_id)
                    if len(selected_edge_rows) >= edge_budget:
                        omitted_edge_count += 1
                        edge_query_truncated = True
                        continue
                    selected_edge_rows.append(row)
                    neighbor = str(row["target_node"] if str(row["source_node"]) == node_id else row["source_node"])
                    if neighbor in selected_node_set or neighbor in queued_ids:
                        continue
                    if len(selected_node_ids) + len(queue) >= node_limit:
                        omitted_node_count += 1
                        continue
                    queue.append((neighbor, distance + 1))
                    queued_ids.add(neighbor)

            omitted_node_count += len(queue)
            node_placeholders = ", ".join("?" for _ in selected_node_ids)
            node_rows = conn.execute(
                f"""
                SELECT id, node_type, payload_json, count
                FROM nodes
                WHERE id IN ({node_placeholders})
                """,
                selected_node_ids,
            ).fetchall()
            node_by_id = {str(row["id"]): row for row in node_rows}
            ordered_nodes = [self._graph_sqlite_row_payload(node_by_id[node_id], kind=kind) for node_id in selected_node_ids if node_id in node_by_id]
            edges = [self._graph_sqlite_edge_payload(row) for row in selected_edge_rows]
            evidence_refs = self._graph_sqlite_evidence_refs(
                conn,
                node_ids=selected_node_ids,
                edge_ids=[str(row["id"]) for row in selected_edge_rows],
            )
        except (OSError, sqlite3.Error) as exc:
            return self._graph_neighborhood_read_error_payload(
                anchor=anchor,
                kind=kind,
                depth=depth,
                limit=limit,
                edge_limit=edge_limit,
                full_route=full_route,
                db_path=db_path,
                reason=exc.__class__.__name__,
            )
        finally:
            if conn is not None:
                conn.close()
        payload = {
            "schema_version": 1,
            "artifact_type": "session_memory_graph_neighborhood",
            "ok": True,
            "mutates": False,
            "anchor": anchor,
            "kind": kind,
            "depth": depth,
            "source": "mcp_sqlite_graph_fast_path",
            "resolved": {
                "start_node_ids": start_ids,
                "resolver_strategy": (
                    route_term_resolution.get("strategy")
                    if route_term_resolution.get("status") == "matched"
                    else "synthetic_exact_candidates"
                ),
            },
            "node_count": len(selected_node_ids),
            "edge_count": len(selected_edge_rows),
            "truncated": bool(edge_query_truncated or omitted_node_count or omitted_edge_count),
            "omitted_node_count": omitted_node_count,
            "omitted_edge_count": omitted_edge_count,
            "nodes": ordered_nodes,
            "edges": edges,
            "evidence_refs": evidence_refs,
            "freshness": {
                "status": "graph_store_read_model",
                "checked": False,
                "read_model": db_path.as_posix(),
            },
            "provider": {
                "selected": "sqlite_graph_store",
                "status": "mcp_sqlite_graph_fast_path",
                "db_path": db_path.as_posix(),
            },
            "quality": {
                "route": "resolved_graph_nodes_then_indexed_bounded_bfs",
                "start_node_count": len(start_ids),
                "direct_sqlite_fast_path": True,
                "requested_depth": depth,
                "route_term_resolution": route_term_resolution,
                "deep_archive_fallback_executed": False,
                "raw_or_segment_ref_present": any(
                    isinstance(ref.get("refs"), dict) and (ref["refs"].get("raw") or ref["refs"].get("segment"))
                    for ref in evidence_refs
                    if isinstance(ref, dict)
                ),
            },
            "next_expansion_command": full_route,
            "next_expansion_reason": "raise graph limit/edge_limit or run archive graph-neighborhood for a deeper relation walk",
            "mcp_access": {
                "mutates": False,
                "archive_command": None,
                "read_model": db_path.as_posix(),
                "response_compacted": True,
                "next_expansion_command": full_route,
                "deep_archive_fallback_executed": False,
                "route_term_resolution": route_term_resolution,
                "authority_boundary": "MCP fast path reads generated graph store; raw/segment evidence remains authoritative.",
            },
        }
        return payload

    def _deferred_graph_route_payload(
        self,
        *,
        artifact_type: str,
        full_route: str,
        reason: str,
        source: str = "mcp_bounded_graph_deferred",
        identity: dict[str, Any] | None = None,
        admission: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "schema_version": 1,
            "artifact_type": artifact_type,
            "ok": False,
            "mutates": False,
            "source": source,
            **(identity or {}),
            "freshness": {
                "status": "bounded_graph_route_deferred",
                "checked": False,
            },
            "quality": {
                "route": "bounded_read_models_only",
                "deep_archive_fallback_executed": False,
            },
            "diagnostics": ["hidden_deep_archive_work_deferred_from_mcp"],
            "next_expansion_command": str((admission or {}).get("launch_command") or full_route),
            "next_expansion_reason": reason,
            "mcp_access": {
                "mutates": False,
                "archive_command": None,
                "deep_archive_fallback_executed": False,
                "deep_archive_fallback_deferred": True,
                "owner_admission_required": bool(admission),
                "full_graph_route": full_route,
                "authority_boundary": (
                    "MCP stays on bounded read models; deep graph expansion requires owner-aware resource admission."
                ),
            },
            "authority_boundary": self.authority_boundary(),
        }
        if admission:
            payload["mcp_access"]["owner_admission"] = admission
        return payload

    def _graph_sqlite_event_routes(
        self,
        graph: dict[str, Any],
        *,
        event_limit: int,
        route_limit: int = 0,
    ) -> dict[str, Any] | None:
        start_ids = [str(node_id) for node_id in (graph.get("resolved") or {}).get("start_node_ids", []) if node_id]
        if not start_ids:
            return None
        db_path = self.aoa_root / "graph" / "graph.sqlite3"
        selected_event_limit = max(1, min(event_limit, 200))
        selected_route_limit = max(0, min(route_limit, 100))
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, timeout=0.5)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA busy_timeout = 500")

            def edges_for(node_ids: list[str], budget: int) -> tuple[list[sqlite3.Row], bool]:
                placeholders = ", ".join("?" for _ in node_ids)
                rows: list[sqlite3.Row] = []
                seen: set[str] = set()
                truncated = False
                for column in ("source_node", "target_node"):
                    fetched = conn.execute(
                        f"""
                        SELECT id, edge_type, source_node, target_node, payload_json, count
                        FROM edges
                        WHERE edge_type = ? AND {column} IN ({placeholders})
                        ORDER BY count DESC, id
                        LIMIT ?
                        """,
                        ["mentions_route_signal", *node_ids, budget + 1],
                    ).fetchall()
                    if len(fetched) > budget:
                        truncated = True
                    for row in fetched:
                        edge_id = str(row["id"])
                        if edge_id in seen:
                            continue
                        seen.add(edge_id)
                        if len(rows) >= budget:
                            truncated = True
                            break
                        rows.append(row)
                return rows, truncated

            direct_budget = min(max(selected_event_limit * 4, 32), GRAPH_SQLITE_EDGE_BUDGET_MAX)
            direct_edges, direct_truncated = edges_for(start_ids, direct_budget)
            candidate_event_ids = list(
                dict.fromkeys(
                    neighbor
                    for row in direct_edges
                    for neighbor in [
                        str(row["target_node"] if str(row["source_node"]) in start_ids else row["source_node"])
                    ]
                    if neighbor.startswith("event:")
                )
            )
            event_rows: list[sqlite3.Row] = []
            if candidate_event_ids:
                placeholders = ", ".join("?" for _ in candidate_event_ids)
                event_rows = conn.execute(
                    f"""
                    SELECT id, node_type, payload_json, count
                    FROM nodes
                    WHERE id IN ({placeholders}) AND node_type = 'event'
                    """,
                    candidate_event_ids,
                ).fetchall()
            event_by_id = {str(row["id"]): row for row in event_rows}
            event_pairs = [
                (node_id, self._graph_sqlite_row_payload(event_by_id[node_id], kind="event"))
                for node_id in candidate_event_ids
                if node_id in event_by_id
            ]
            event_pairs.sort(
                key=lambda item: (
                    str(item[1].get("timestamp") or ""),
                    str(item[1].get("session_label") or ""),
                    str(item[1].get("event_id") or item[0]),
                )
            )
            selected_event_pairs = event_pairs[:selected_event_limit]
            event_ids = [node_id for node_id, _event in selected_event_pairs]
            events = [event for _node_id, event in selected_event_pairs]

            related_edges: list[sqlite3.Row] = []
            related_truncated = False
            cooccurrences: list[dict[str, Any]] = []
            if selected_route_limit and event_ids:
                related_budget = min(max(selected_event_limit * 8, 64), GRAPH_SQLITE_EDGE_BUDGET_MAX)
                related_edges, related_truncated = edges_for(event_ids, related_budget)
                event_id_set = set(event_ids)
                event_to_routes: dict[str, set[str]] = {}
                route_ids: set[str] = set()
                for row in related_edges:
                    source_id = str(row["source_node"])
                    target_id = str(row["target_node"])
                    if source_id in event_id_set and target_id.startswith("route:"):
                        event_to_routes.setdefault(source_id, set()).add(target_id)
                        route_ids.add(target_id)
                    if target_id in event_id_set and source_id.startswith("route:"):
                        event_to_routes.setdefault(target_id, set()).add(source_id)
                        route_ids.add(source_id)
                route_ids.difference_update(start_ids)
                route_by_id: dict[str, dict[str, Any]] = {}
                if route_ids:
                    placeholders = ", ".join("?" for _ in route_ids)
                    route_rows = conn.execute(
                        f"""
                        SELECT id, node_type, payload_json, count
                        FROM nodes
                        WHERE id IN ({placeholders})
                        """,
                        list(route_ids),
                    ).fetchall()
                    route_by_id = {
                        str(row["id"]): self._graph_sqlite_row_payload(row, kind=str(row["node_type"]))
                        for row in route_rows
                    }
                counts: Counter[str] = Counter(
                    route_id
                    for event_id in event_ids
                    for route_id in event_to_routes.get(event_id, set())
                    if route_id in route_by_id
                )
                ranked = sorted(
                    counts.items(),
                    key=lambda item: (-item[1], -int(route_by_id[item[0]].get("count") or 0), item[0]),
                )[:selected_route_limit]
                cooccurrences = [
                    {"node": route_by_id[node_id], "count": count}
                    for node_id, count in ranked
                ]

            evidence_refs = self._graph_sqlite_evidence_refs(
                conn,
                node_ids=event_ids,
                edge_ids=[str(row["id"]) for row in [*direct_edges, *related_edges]],
            )
            return {
                "ok": True,
                "start_node_ids": start_ids,
                "event_ids": event_ids,
                "events": events,
                "cooccurrences": cooccurrences,
                "evidence_refs": evidence_refs,
                "truncated": bool(
                    direct_truncated
                    or related_truncated
                    or len(candidate_event_ids) > len(event_ids)
                ),
            }
        except (OSError, sqlite3.Error) as exc:
            return {"ok": False, "read_error": exc.__class__.__name__}
        finally:
            if conn is not None:
                conn.close()

    def graph_timeline(self, anchor: str, kind: str = "auto", limit: int = 40) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        route_kind = _coerce_trace_kind(kind, error_label="graph kind")
        bounded_limit = _coerce_limit(limit, 40, 200)
        args = [anchor_text, "--kind", route_kind, "--limit", str(bounded_limit)]
        full_route = self._archive_command_line("graph-timeline", args)
        admission = self._resource_admitted_archive_route(
            "graph-timeline",
            args,
            workload_class="medium",
        )
        graph = self._graph_neighborhood_sqlite_fast_path(
            anchor=anchor_text,
            kind=route_kind,
            depth=0,
            limit=20,
            edge_limit=1,
            full_route=full_route,
        )
        if graph is None:
            payload = self._deferred_graph_route_payload(
                artifact_type="session_memory_graph_timeline",
                full_route=full_route,
                reason=(
                    "The exact anchor was not available in the bounded graph store. Run the named timeline command "
                    "outside MCP through owner-aware resource admission when deeper ordering evidence is justified."
                ),
                identity={"anchor": anchor_text, "kind": route_kind, "requested_kind": kind},
                admission=admission,
            )
            return _compact_graph_payload(payload, full_route=full_route, event_limit=min(bounded_limit, GRAPH_EVENT_SAMPLE_LIMIT))
        if graph.get("ok") is False:
            payload = dict(graph)
            payload.update(
                {
                    "artifact_type": "session_memory_graph_timeline",
                    "anchor": anchor_text,
                    "kind": route_kind,
                    "requested_kind": kind,
                }
            )
            return _compact_graph_payload(payload, full_route=full_route, event_limit=min(bounded_limit, GRAPH_EVENT_SAMPLE_LIMIT))

        direct = self._graph_sqlite_event_routes(graph, event_limit=bounded_limit)
        if direct is None:
            payload = self._deferred_graph_route_payload(
                artifact_type="session_memory_graph_timeline",
                full_route=full_route,
                reason=(
                    "The indexed anchor could not be resolved into direct event routes. Run the named timeline "
                    "command through owner-aware resource admission when deeper ordering evidence is justified."
                ),
                identity={"anchor": anchor_text, "kind": route_kind, "requested_kind": kind},
                admission=admission,
            )
            return _compact_graph_payload(payload, full_route=full_route, event_limit=min(bounded_limit, GRAPH_EVENT_SAMPLE_LIMIT))
        if direct.get("ok") is False:
            payload = self._graph_neighborhood_read_error_payload(
                anchor=anchor_text,
                kind=route_kind,
                depth=0,
                limit=20,
                edge_limit=1,
                full_route=full_route,
                db_path=self.aoa_root / "graph" / "graph.sqlite3",
                reason=str(direct.get("read_error") or "unknown_read_error"),
            )
            payload.update({"artifact_type": "session_memory_graph_timeline", "requested_kind": kind})
            return _compact_graph_payload(payload, full_route=full_route, event_limit=min(bounded_limit, GRAPH_EVENT_SAMPLE_LIMIT))

        events = list(direct.get("events", []))
        events.sort(
            key=lambda node: (
                str(node.get("timestamp") or ""),
                str(node.get("session_label") or node.get("session_id") or ""),
                _safe_int(node.get("line")) or 0,
                str(node.get("event_id") or node.get("id") or ""),
            )
        )
        payload = {
            "schema_version": 1,
            "artifact_type": "session_memory_graph_timeline",
            "ok": True,
            "mutates": False,
            "anchor": anchor_text,
            "kind": route_kind,
            "requested_kind": kind,
            "source": "mcp_sqlite_graph_timeline",
            "event_count": len(events),
            "events": events[:bounded_limit],
            "evidence_refs": direct.get("evidence_refs", []),
            "freshness": graph.get("freshness", {}),
            "quality": {
                "route": "resolved_anchor_then_indexed_direct_event_edges",
                "direct_sqlite_fast_path": True,
                "truncated": bool(direct.get("truncated")),
                "deep_archive_fallback_executed": False,
            },
            "next_expansion_command": admission["launch_command"],
            "next_expansion_reason": "Run the owner command only when more event ordering evidence is needed.",
            "mcp_access": {
                "mutates": False,
                "archive_command": None,
                "read_model": (graph.get("provider") or {}).get("db_path"),
                "deep_archive_fallback_executed": False,
                "owner_admission_required_for_expansion": True,
                "owner_admission": admission,
            },
            "authority_boundary": self.authority_boundary(),
        }
        return _compact_graph_payload(
            payload,
            full_route=full_route,
            event_limit=min(bounded_limit, GRAPH_EVENT_SAMPLE_LIMIT),
        )

    def graph_shortest_path(self, source: str, target: str, kind: str = "auto", max_depth: int = 4) -> dict[str, Any]:
        source_text = _ensure_short_text(source, "source")
        target_text = _ensure_short_text(target, "target")
        route_kind = _coerce_trace_kind(kind, error_label="graph kind")
        bounded_depth = _coerce_limit(max_depth, 4, 8)
        args = [source_text, target_text, "--kind", route_kind, "--max-depth", str(bounded_depth)]
        full_route = self._archive_command_line("graph-shortest-path", args)
        admission = self._resource_admitted_archive_route(
            "graph-shortest-path",
            args,
            workload_class="heavy",
        )
        payload = self._deferred_graph_route_payload(
            artifact_type="session_memory_graph_shortest_path",
            full_route=full_route,
            source="mcp_owner_admission_deferred",
            reason=(
                "Shortest-path traversal can fault broad graph pages under memory pressure. Run the named owner "
                "command through resource admission; use graph-neighborhood for compact MCP topology."
            ),
            identity={
                "source_anchor": source_text,
                "target_anchor": target_text,
                "kind": route_kind,
                "requested_kind": kind,
                "max_depth": bounded_depth,
                "path_found": False,
                "distance": None,
            },
            admission=admission,
        )
        return _compact_graph_payload(payload, full_route=full_route)

    def graph_bridge(
        self,
        source: str,
        target: str,
        kind: str = "auto",
        source_kind: str = "auto",
        target_kind: str = "auto",
        max_depth: int = 4,
        limit: int = 8,
    ) -> dict[str, Any]:
        source_text = _ensure_short_text(source, "source")
        target_text = _ensure_short_text(target, "target")
        route_kind = _coerce_trace_kind(kind, error_label="graph kind")
        selected_source_kind = _coerce_trace_kind(source_kind or route_kind, error_label="source graph kind")
        selected_target_kind = _coerce_trace_kind(target_kind or route_kind, error_label="target graph kind")
        selected_max_depth = _coerce_limit(max_depth, 4, 8)
        selected_limit = _coerce_limit(limit, 8, 30)
        args = [
            source_text,
            target_text,
            "--kind",
            route_kind,
            "--source-kind",
            selected_source_kind,
            "--target-kind",
            selected_target_kind,
            "--max-depth",
            str(selected_max_depth),
            "--limit",
            str(selected_limit),
        ]
        full_route = self._archive_command_line("graph-bridge", args)
        admission = self._resource_admitted_archive_route(
            "graph-bridge",
            args,
            workload_class="heavy",
        )
        payload = self._deferred_graph_route_payload(
            artifact_type="session_memory_graph_bridge",
            full_route=full_route,
            source="mcp_owner_admission_deferred",
            reason=(
                "Bridge assembly combines path traversal and timeline expansion. Run the named owner command through "
                "resource admission; use graph-neighborhood or graph-timeline for compact MCP evidence."
            ),
            identity={
                "source_anchor": source_text,
                "target_anchor": target_text,
                "kind": route_kind,
                "requested_kind": kind,
                "source_kind": selected_source_kind,
                "target_kind": selected_target_kind,
                "max_depth": selected_max_depth,
                "parameters": {"limit": selected_limit},
            },
            admission=admission,
        )
        return _compact_graph_bridge_payload(payload, full_route=full_route)

    def graph_cooccurrence(self, anchor: str, kind: str = "auto", limit: int = 30) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        route_kind = _coerce_trace_kind(kind, error_label="graph kind")
        bounded_limit = _coerce_limit(limit, 30, 100)
        args = [anchor_text, "--kind", route_kind, "--limit", str(bounded_limit)]
        full_route = self._archive_command_line("graph-cooccurrence", args)
        admission = self._resource_admitted_archive_route(
            "graph-cooccurrence",
            args,
            workload_class="medium",
        )
        graph = self._graph_neighborhood_sqlite_fast_path(
            anchor=anchor_text,
            kind=route_kind,
            depth=0,
            limit=20,
            edge_limit=1,
            full_route=full_route,
        )
        if graph is None:
            payload = self._deferred_graph_route_payload(
                artifact_type="session_memory_graph_cooccurrence",
                full_route=full_route,
                reason=(
                    "The exact anchor was unavailable in the bounded graph store. Run the named cooccurrence command "
                    "outside MCP through owner-aware resource admission when deeper aggregation is justified."
                ),
                identity={"anchor": anchor_text, "kind": route_kind, "requested_kind": kind},
                admission=admission,
            )
            return _compact_graph_payload(payload, full_route=full_route)
        if graph.get("ok") is False:
            payload = dict(graph)
            payload.update(
                {
                    "artifact_type": "session_memory_graph_cooccurrence",
                    "anchor": anchor_text,
                    "kind": route_kind,
                    "requested_kind": kind,
                }
            )
            return _compact_graph_payload(payload, full_route=full_route)

        direct = self._graph_sqlite_event_routes(
            graph,
            event_limit=min(max(bounded_limit * 8, 64), 200),
            route_limit=bounded_limit,
        )
        if direct is None:
            payload = self._deferred_graph_route_payload(
                artifact_type="session_memory_graph_cooccurrence",
                full_route=full_route,
                reason=(
                    "The indexed anchor could not be resolved into direct event routes. Run the named cooccurrence "
                    "command through owner-aware resource admission when deeper aggregation is justified."
                ),
                identity={"anchor": anchor_text, "kind": route_kind, "requested_kind": kind},
                admission=admission,
            )
            return _compact_graph_payload(payload, full_route=full_route)
        if direct.get("ok") is False:
            payload = self._graph_neighborhood_read_error_payload(
                anchor=anchor_text,
                kind=route_kind,
                depth=0,
                limit=20,
                edge_limit=1,
                full_route=full_route,
                db_path=self.aoa_root / "graph" / "graph.sqlite3",
                reason=str(direct.get("read_error") or "unknown_read_error"),
            )
            payload.update({"artifact_type": "session_memory_graph_cooccurrence", "requested_kind": kind})
            return _compact_graph_payload(payload, full_route=full_route)

        cooccurrences = list(direct.get("cooccurrences", []))
        payload = {
            "schema_version": 1,
            "artifact_type": "session_memory_graph_cooccurrence",
            "ok": True,
            "mutates": False,
            "anchor": anchor_text,
            "kind": route_kind,
            "requested_kind": kind,
            "source": "mcp_sqlite_graph_cooccurrence",
            "cooccurrence_count": len(cooccurrences),
            "cooccurrences": cooccurrences,
            "evidence_refs": direct.get("evidence_refs", []),
            "freshness": graph.get("freshness", {}),
            "quality": {
                "route": "resolved_anchor_then_two_hop_event_route_aggregation",
                "direct_sqlite_fast_path": True,
                "anchor_event_count": len(direct.get("event_ids", [])),
                "truncated": bool(direct.get("truncated")),
                "deep_archive_fallback_executed": False,
            },
            "next_expansion_command": admission["launch_command"],
            "next_expansion_reason": "Run the owner command only when the bounded cooccurrence sample is insufficient.",
            "mcp_access": {
                "mutates": False,
                "archive_command": None,
                "read_model": (graph.get("provider") or {}).get("db_path"),
                "deep_archive_fallback_executed": False,
                "owner_admission_required_for_expansion": True,
                "owner_admission": admission,
            },
            "authority_boundary": self.authority_boundary(),
        }
        return _compact_graph_payload(payload, full_route=full_route)

    def graphrag_packet(
        self,
        query: str,
        anchor: str = "",
        mode: str = "hybrid",
        limit: int = 8,
        include_semantic_context: bool = False,
        rerank_local: bool = False,
    ) -> dict[str, Any]:
        query_text = _ensure_short_text(query or anchor, "query")
        args = [
            "--query",
            query_text,
            "--mode",
            _safe_selector(mode or "hybrid", "mode", limit=80),
            "--limit",
            str(_coerce_limit(limit, 8, 50)),
        ]
        if anchor:
            args.extend(["--anchor", _ensure_short_text(anchor, "anchor")])
        if include_semantic_context:
            args.append("--include-semantic-context")
        if rerank_local:
            args.append("--rerank-local")
        full_route = self._archive_command_line("graphrag-packet", args)
        admission = self._resource_admitted_archive_route(
            "graphrag-packet",
            args,
            workload_class="heavy",
        )
        payload = self._deferred_graph_route_payload(
            artifact_type="session_memory_graphrag_packet",
            full_route=full_route,
            source="mcp_owner_admission_deferred",
            reason=(
                "GraphRAG may combine broad lexical, graph, semantic, and rerank work. Run the named owner command "
                "outside MCP through owner-aware resource admission."
            ),
            identity={
                "query": query_text,
                "anchor": _ensure_short_text(anchor, "anchor") if anchor else "",
                "mode": _safe_selector(mode or "hybrid", "mode", limit=80),
                "parameters": {
                    "limit": _coerce_limit(limit, 8, 50),
                    "include_semantic_context": bool(include_semantic_context),
                    "rerank_local": bool(rerank_local),
                },
            },
            admission=admission,
        )
        bounded_anchor = anchor or query_text
        bounded_graph = self.graph_neighborhood(bounded_anchor, depth=1, limit=min(_coerce_limit(limit, 8, 50), 8), edge_limit=8)
        if bounded_graph.get("ok"):
            payload["bounded_graph"] = bounded_graph
        return payload

    def graph_eval(self, limit: int = 6, include_semantic_context: bool = False, rerank_local: bool = False) -> dict[str, Any]:
        args = ["--limit", str(_coerce_limit(limit, 6, 30))]
        if include_semantic_context:
            args.append("--include-semantic-context")
        if rerank_local:
            args.append("--rerank-local")
        full_route = self._archive_command_line("graph-eval", args)
        admission = self._resource_admitted_archive_route(
            "graph-eval",
            args,
            workload_class="heavy",
        )
        return self._deferred_graph_route_payload(
            artifact_type="session_memory_graph_eval",
            full_route=full_route,
            source="mcp_owner_admission_deferred",
            reason=(
                "Graph evaluation is batch analytical work, not a compact MCP read. Run the named owner command "
                "outside MCP through owner-aware resource admission."
            ),
            identity={
                "parameters": {
                    "limit": _coerce_limit(limit, 6, 30),
                    "include_semantic_context": bool(include_semantic_context),
                    "rerank_local": bool(rerank_local),
                }
            },
            admission=admission,
        )

    def graph_quality_audit(
        self,
        limit: int = 4,
        sample_ref_limit: int = 2,
        anchors: list[Any] | None = None,
        full_graphrag: bool = False,
    ) -> dict[str, Any]:
        selected = anchors or DEFAULT_GRAPH_QUALITY_ANCHORS
        args = [
            "--limit",
            str(_coerce_limit(limit, 4, 20)),
            "--sample-ref-limit",
            str(_coerce_limit(sample_ref_limit, 2, 6)),
        ]
        for item in selected[:8]:
            if isinstance(item, dict):
                anchor = _ensure_short_text(str(item.get("anchor") or item.get("query") or ""), "anchor")
                kind = _coerce_trace_kind(str(item.get("kind") or "auto"), error_label="graph quality kind")
                anchor_id = _safe_selector(str(item.get("id") or ""), "anchor_id", limit=80) if item.get("id") else ""
                args.extend(["--anchor", f"{anchor_id}:{kind}:{anchor}" if anchor_id else f"{kind}:{anchor}"])
                continue
            args.extend(["--anchor", _ensure_short_text(str(item), "anchor")])
        if full_graphrag:
            args.append("--full-graphrag")
        full_route = self._archive_command_line("graph-quality-audit", args)
        admission = self._resource_admitted_archive_route(
            "graph-quality-audit",
            args,
            workload_class="heavy",
        )
        return self._deferred_graph_route_payload(
            artifact_type="session_memory_graph_quality_audit",
            full_route=full_route,
            source="mcp_owner_admission_deferred",
            reason=(
                "Graph quality audit is multi-anchor analytical work. Run the named owner command outside MCP "
                "through owner-aware resource admission."
            ),
            identity={
                "parameters": {
                    "limit": _coerce_limit(limit, 4, 20),
                    "sample_ref_limit": _coerce_limit(sample_ref_limit, 2, 6),
                    "anchor_count": len(selected[:8]),
                    "full_graphrag": bool(full_graphrag),
                }
            },
            admission=admission,
        )

    def explain_graph_packet(self, intent: str, anchor: str = "", query: str = "", limit: int = 8) -> dict[str, Any]:
        intent_text = _ensure_short_text(intent or query or anchor, "intent")
        args = [intent_text, "--limit", str(_coerce_limit(limit, 8, 50))]
        if anchor:
            args.extend(["--anchor", _ensure_short_text(anchor, "anchor")])
        if query:
            args.extend(["--query", _ensure_short_text(query, "query")])
        full_route = self._archive_command_line("graph-explain-packet", args)
        admission = self._resource_admitted_archive_route(
            "graph-explain-packet",
            args,
            workload_class="heavy",
        )
        payload = self._deferred_graph_route_payload(
            artifact_type="session_memory_graph_explain_packet",
            full_route=full_route,
            source="mcp_owner_admission_deferred",
            reason=(
                "Graph explanation may expand lexical and graph evidence. Run the named owner command outside MCP "
                "through owner-aware resource admission when the bounded graph packet is insufficient."
            ),
            identity={
                "intent": intent_text,
                "anchor": _ensure_short_text(anchor, "anchor") if anchor else "",
                "query": _ensure_short_text(query, "query") if query else "",
                "parameters": {"limit": _coerce_limit(limit, 8, 50)},
            },
            admission=admission,
        )
        bounded_anchor = anchor or query or intent_text
        bounded_graph = self.graph_neighborhood(bounded_anchor, depth=1, limit=min(_coerce_limit(limit, 8, 50), 8), edge_limit=8)
        if bounded_graph.get("ok"):
            payload["bounded_graph"] = bounded_graph
        return payload

    def read_resource(self, uri: str) -> dict[str, Any]:
        parsed = urlparse(uri)
        if parsed.scheme != "aoa-session-memory":
            raise ValueError(f"unsupported resource scheme: {parsed.scheme}")
        netloc = unquote(parsed.netloc)
        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
        if netloc == "status":
            return self.session_memory_status()
        if netloc == "surfaces":
            return self.available_surfaces()
        if netloc == "provider" and parts == ["status"]:
            return self._search_provider_status_fast()
        if netloc == "maintenance" and parts == ["status"]:
            return self.session_maintenance_status(include_timers=False)
        if netloc == "projection" and parts == ["status"]:
            return self.session_projection_status()
        if netloc == "readiness" and parts == ["route-layer"]:
            return self.latest_diagnostics("route-layer-readiness", limit=1)
        if netloc == "diagnostics" and len(parts) >= 2 and parts[0] == "latest":
            return self.latest_diagnostics(parts[1], limit=5)
        if netloc == "hooks" and parts and parts[0] == "receipts":
            event_name = parts[1] if len(parts) > 1 else "UserPromptSubmit"
            return self.session_hook_receipts(event_name=event_name, limit=50)
        if netloc == "entities" and parts:
            return self.session_entity_inventory(layer=parts[0], limit=50, sample_limit=2)
        if netloc == "entity-registry":
            kind = parts[0] if parts else "all"
            query = "/".join(parts[1:]) if len(parts) > 1 else ""
            return self.session_entity_registry(kind=kind, query=query, limit=50)
        if netloc == "entity-lookup" and len(parts) >= 2:
            return self.session_entity_registry(kind=parts[0], lookup="/".join(parts[1:]), limit=10)
        if netloc == "session" and len(parts) >= 2:
            session = parts[0]
            if parts[1] == "brief":
                return self.session_brief(session)
            if parts[1] == "manifest":
                return self._read_session_file(session, "session.manifest.json")
            if parts[1] == "index":
                return self._read_session_file(session, "session.index.json")
            if parts[1] == "rehydrate":
                return self._archive_command("rehydrate", [session, "--max-events", "20"])
        if netloc == "route" and parts:
            axis = parts[0]
            key = parts[1] if len(parts) > 1 else ""
            return self.session_route(axis, key)
        if netloc == "trace" and parts:
            return self.session_trace("/".join(parts), limit=12, per_route_limit=5)
        if netloc == "graph" and parts:
            if parts[0] == "status":
                return self._graph_summary(self.session_maintenance_status(include_timers=False))
            if parts[0] == "neighborhood" and len(parts) >= 2:
                return self.graph_neighborhood("/".join(parts[1:]), limit=40)
            if parts[0] == "timeline" and len(parts) >= 2:
                return self.graph_timeline("/".join(parts[1:]), limit=40)
        raise ValueError(f"unsupported aoa-session-memory resource: {uri}")

    def _atlas_summary(self) -> dict[str, Any]:
        index_path = self.aoa_root / "maps" / "index.json"
        index = _read_json(index_path)
        if not isinstance(index, dict):
            return {"root_index_exists": False, "index_path": index_path.as_posix()}
        axes = index.get("axes") if isinstance(index.get("axes"), list) else []
        return {
            "root_index_exists": True,
            "index_path": index_path.as_posix(),
            "generated_at": index.get("generated_at"),
            "axis_count": index.get("axis_count") or len(axes),
            "entry_count": index.get("entry_count"),
            "axes": axes[:60],
        }

    def _graph_summary(self, maintenance: dict[str, Any] | None = None) -> dict[str, Any]:
        index_path = self.aoa_root / "graph" / "index.json"
        sqlite_path = self.aoa_root / "graph" / "graph.sqlite3"
        freshness = self._latest_graph_freshness_summary()
        maintenance = maintenance if isinstance(maintenance, dict) else {}
        maintenance_graph = maintenance.get("graph") if isinstance(maintenance.get("graph"), dict) else {}
        maintenance_route = maintenance.get("route") if isinstance(maintenance.get("route"), dict) else {}
        has_maintenance_verdict = bool(maintenance_graph or maintenance_route)
        decision_source = "maintenance_status" if has_maintenance_verdict else "cached_graph_freshness_diagnostic"
        needs_graph_maintenance = (
            maintenance_route.get("needs_graph_maintenance")
            if has_maintenance_verdict and maintenance_route.get("needs_graph_maintenance") is not None
            else freshness.get("needs_graph_maintenance")
        )
        needs_index_maintenance = (
            maintenance_route.get("needs_index_maintenance")
            if has_maintenance_verdict and maintenance_route.get("needs_index_maintenance") is not None
            else freshness.get("needs_index_maintenance")
        )
        maintenance_status = maintenance_graph.get("status") if has_maintenance_verdict else None
        diagnostic_conflict = (
            has_maintenance_verdict
            and freshness.get("checked")
            and freshness.get("needs_graph_maintenance") is True
            and needs_graph_maintenance is False
        )
        index = _read_json(index_path)
        if not isinstance(index, dict):
            if sqlite_path.is_file():
                return {
                    "status": "sqlite_live_store_present",
                    "db_path": sqlite_path.as_posix(),
                    "db_mtime": sqlite_path.stat().st_mtime,
                    "sidecar_status": "not_exported",
                    "index_path": index_path.as_posix(),
                    "diagnostics": ["graph_sidecar_not_exported"],
                    "freshness": freshness,
                    "freshness_source": "cached_graph_freshness_diagnostic",
                    "decision_source": decision_source,
                    "maintenance_status": maintenance_status,
                    "cached_freshness_conflicts_with_maintenance": diagnostic_conflict,
                    "needs_graph_maintenance": needs_graph_maintenance,
                    "needs_index_maintenance": needs_index_maintenance,
                }
            return {
                "status": "missing",
                "index_path": index_path.as_posix(),
                "freshness": freshness,
                "freshness_source": "cached_graph_freshness_diagnostic",
                "decision_source": decision_source,
                "maintenance_status": maintenance_status,
                "cached_freshness_conflicts_with_maintenance": diagnostic_conflict,
                "needs_graph_maintenance": needs_graph_maintenance,
                "needs_index_maintenance": needs_index_maintenance,
            }
        return {
            "status": "present",
            "index_path": index_path.as_posix(),
            "generated_at": index.get("generated_at"),
            "truth_status": index.get("truth_status"),
            "node_count": index.get("node_count"),
            "edge_count": index.get("edge_count"),
            "node_type_counts": index.get("node_type_counts", {}),
            "edge_type_counts": index.get("edge_type_counts", {}),
            "freshness": freshness,
            "freshness_source": "cached_graph_freshness_diagnostic",
            "decision_source": decision_source,
            "maintenance_status": maintenance_status,
            "cached_freshness_conflicts_with_maintenance": diagnostic_conflict,
            "needs_graph_maintenance": needs_graph_maintenance,
            "needs_index_maintenance": needs_index_maintenance,
        }

    def _latest_graph_freshness_summary(self) -> dict[str, Any]:
        latest = self.latest_diagnostics("graph-freshness-gates", limit=1, include_payload=True)
        reports = latest.get("reports") if isinstance(latest.get("reports"), list) else []
        report = reports[0] if reports and isinstance(reports[0], dict) else {}
        payload = report.get("payload") if isinstance(report.get("payload"), dict) else {}
        graph_store = payload.get("graph_store") if isinstance(payload.get("graph_store"), dict) else {}
        source_state = graph_store.get("source_state") if isinstance(graph_store.get("source_state"), dict) else {}
        return {
            "checked": bool(payload),
            "report": report.get("path"),
            "generated_at": payload.get("generated_at"),
            "ok": payload.get("ok"),
            "search_status": (payload.get("search_index") or {}).get("status") if isinstance(payload.get("search_index"), dict) else None,
            "atlas_status": (payload.get("atlas_index") or {}).get("status") if isinstance(payload.get("atlas_index"), dict) else None,
            "graph_status": graph_store.get("status"),
            "needs_index_maintenance": payload.get("needs_index_maintenance"),
            "needs_graph_maintenance": payload.get("needs_graph_maintenance"),
            "dirty_count": source_state.get("dirty_count"),
            "missing_count": source_state.get("missing_count"),
            "blocked_count": source_state.get("blocked_count"),
            "diagnostics": payload.get("diagnostics", []) if isinstance(payload.get("diagnostics"), list) else [],
            "authority": "latest diagnostic summary; run graph-freshness-check outside MCP for live truth",
        }

    def _read_map_entry_payload(self, axis_name: str, json_path: Any) -> Any:
        if not isinstance(json_path, str) or not json_path:
            return None
        path = Path(json_path)
        if not path.is_absolute():
            path = self.aoa_root / "maps" / axis_name / "entries" / path
        if not _is_under(path, self.aoa_root / "maps" / axis_name):
            return None
        return _read_json(path)

    def _registry_sessions(self) -> list[dict[str, Any]]:
        payload = _read_json(self.aoa_root / "session-registry.json")
        sessions = payload.get("sessions") if isinstance(payload, dict) else None
        return [item for item in sessions if isinstance(item, dict)] if isinstance(sessions, list) else []

    def _session_selector_terms(self, session: str) -> list[str]:
        selector = _safe_selector(session, "session", limit=180)
        terms = [selector] if selector else []
        session_dir = self._resolve_session_dir(selector) if selector else None
        if session_dir is not None:
            manifest = _read_json(session_dir / "session.manifest.json")
            display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
            for value in (
                manifest.get("session_id"),
                manifest.get("session_label"),
                manifest.get("session_title"),
                display.get("label"),
                display.get("title"),
                session_dir.name,
                session_dir.as_posix(),
            ):
                text = str(value or "").strip()
                if text and text not in terms:
                    terms.append(text)
        return terms

    def _resolve_session_dir(self, session: str) -> Path | None:
        selector = (session or "latest").strip()
        sessions = self._registry_sessions()
        if selector == "latest":
            if sessions:
                latest = sorted(sessions, key=self._session_recency_key, reverse=True)[0]
                return self._session_path_from_registry(latest)
            dirs = sorted((self.aoa_root / "sessions").glob("*"))
            return dirs[-1] if dirs else None
        lowered = selector.casefold()
        for item in sessions:
            values = [str(item.get("session_id") or "")]
            display = item.get("display")
            if isinstance(display, dict):
                values.extend(str(display.get(key) or "") for key in ("label", "title", "path", "archive_path", "navigation_path"))
            values.extend(str(item.get(key) or "") for key in ("session_label", "session_title", "path"))
            if any(lowered in value.casefold() for value in values):
                return self._session_path_from_registry(item)
        direct = self.aoa_root / "sessions" / selector
        return direct if direct.exists() else None

    def _receipt_session_dirs(self, session: str = "") -> list[Path]:
        if session:
            session_dir = self._resolve_session_dir(session)
            return [session_dir] if session_dir is not None and session_dir.exists() else []
        sessions_root = self.aoa_root / "sessions"
        if not sessions_root.exists():
            return []
        return sorted(path for path in sessions_root.iterdir() if path.is_dir())

    def _session_sort_key(self, item: dict[str, Any]) -> tuple[str, int, str]:
        display = item.get("display") if isinstance(item.get("display"), dict) else {}
        return (
            str(display.get("date") or item.get("date") or ""),
            int(display.get("sequence") or item.get("sequence") or 0),
            str(display.get("label") or item.get("session_id") or ""),
        )

    def _session_activity_mtime(self, item: dict[str, Any]) -> float:
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
        candidates = [
            item.get("transcript_path"),
            raw.get("source_path"),
            raw.get("path"),
        ]
        session_path = self._session_path_from_registry(item)
        if session_path is not None:
            manifest = _read_json(session_path / "session.manifest.json")
            manifest = manifest if isinstance(manifest, dict) else {}
            manifest_raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
            candidates.extend(
                [
                    manifest.get("transcript_path"),
                    manifest_raw.get("source_path"),
                    manifest_raw.get("path"),
                ]
            )
        newest = 0.0
        for candidate in candidates:
            if not candidate:
                continue
            try:
                path = Path(str(candidate)).expanduser()
                if path.is_file():
                    newest = max(newest, path.stat().st_mtime)
            except OSError:
                continue
        return newest

    def _session_recency_key(self, item: dict[str, Any]) -> tuple[str, int, str, float]:
        date, sequence, label = self._session_sort_key(item)
        return (str(item.get("updated_at") or date), sequence, label, self._session_activity_mtime(item))

    def _session_path_from_registry(self, item: dict[str, Any]) -> Path | None:
        display = item.get("display") if isinstance(item.get("display"), dict) else {}
        path = display.get("path") or display.get("archive_path") or display.get("navigation_path") or item.get("path")
        if path:
            return Path(str(path))
        label = display.get("label") or item.get("session_label")
        return self.aoa_root / "sessions" / str(label) if label else None

    def _segment_preview(self, index: dict[str, Any], manifest: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        for key in ("segments_preview", "segments"):
            value = index.get(key)
            if isinstance(value, list):
                return [item for item in value[:limit] if isinstance(item, dict)]
        value = manifest.get("segments_preview")
        if isinstance(value, list):
            return [item for item in value[:limit] if isinstance(item, dict)]
        raw_blocks = manifest.get("raw_blocks") if isinstance(manifest.get("raw_blocks"), dict) else {}
        blocks = raw_blocks.get("blocks") if isinstance(raw_blocks.get("blocks"), list) else []
        return [
            {
                "segment_id": block.get("segment_id"),
                "role": block.get("role"),
                "source_range": block.get("source_range"),
                "raw_block": block.get("rel") or block.get("path"),
            }
            for block in blocks[:limit]
            if isinstance(block, dict)
        ]

    def _read_session_file(self, session: str, filename: str) -> dict[str, Any]:
        session_dir = self._resolve_session_dir(session)
        if session_dir is None:
            return {"ok": False, "diagnostics": ["session not found"], "authority_boundary": self.authority_boundary()}
        path = session_dir / filename
        payload = _read_json(path)
        return {
            "schema": "aoa_session_memory_resource_file_v1",
            "ok": payload is not None,
            "path": path.as_posix(),
            "payload": payload,
            "authority_boundary": self.authority_boundary(),
        }

    def _refs_from_payloads(self, payloads: list[Any]) -> list[str]:
        refs: list[str] = []
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            for key in ("results", "evidence_hits"):
                for hit in payload.get(key, []) if isinstance(payload.get(key), list) else []:
                    if not isinstance(hit, dict):
                        continue
                    hit_refs = hit.get("refs")
                    if isinstance(hit_refs, dict):
                        refs.extend(str(value) for value in hit_refs.values() if value)
            session = payload.get("session")
            if isinstance(session, dict):
                for key in ("manifest", "raw_path"):
                    if session.get(key):
                        refs.append(str(session[key]))
        return list(dict.fromkeys(refs))

    def _check_ref(self, ref: str, *, session_dir: Path | None = None) -> dict[str, Any]:
        value = str(ref or "").strip()
        if not value:
            return {"ref": ref, "status": "invalid", "reason": "empty ref"}
        if "\x00" in value:
            return {"ref": ref, "status": "invalid", "reason": "NUL byte"}
        path_part = value.split("#", 1)[0]
        if path_part.startswith("raw:line:"):
            if session_dir is not None:
                return self._check_raw_line_ref(value, session_dir=session_dir)
            return {"ref": value, "status": "needs_session_context", "reason": "raw line refs are session-relative"}
        if path_part.startswith("session:"):
            session_dir = self._resolve_session_dir(path_part.removeprefix("session:"))
            return {
                "ref": value,
                "status": "present" if session_dir and session_dir.exists() else "missing",
                "path": session_dir.as_posix() if session_dir else None,
            }
        path = Path(path_part)
        if path.is_absolute():
            exists = path.exists()
            return {
                "ref": value,
                "status": "present" if exists else "missing",
                "path": path.as_posix(),
                "inside_aoa_root": _is_under(path, self.aoa_root) if exists else path.as_posix().startswith(self.aoa_root.as_posix()),
            }
        relative_candidates = [self.aoa_root / path_part, self.aoa_root / "sessions" / path_part]
        for candidate in relative_candidates:
            resolved = candidate.resolve()
            if candidate.exists() and not _is_under(resolved, self.aoa_root):
                return {
                    "ref": value,
                    "status": "invalid",
                    "path": resolved.as_posix(),
                    "inside_aoa_root": False,
                    "reason": "relative ref escapes aoa root",
                }
            if candidate.exists():
                return {"ref": value, "status": "present", "path": resolved.as_posix(), "inside_aoa_root": True}
        return {"ref": value, "status": "unknown", "reason": "relative or symbolic ref requires session context"}

    def _check_raw_line_ref(self, ref: str, *, session_dir: Path) -> dict[str, Any]:
        line_text = ref.split("#", 1)[0].removeprefix("raw:line:")
        try:
            line_number = int(line_text)
        except ValueError:
            return {"ref": ref, "status": "invalid", "reason": "raw line ref must end with an integer"}
        raw_path = session_dir / "raw" / "session.raw.jsonl"
        if not raw_path.exists():
            return {"ref": ref, "status": "missing", "path": raw_path.as_posix(), "reason": "session raw file missing"}
        if line_number < 1:
            return {"ref": ref, "status": "invalid", "path": raw_path.as_posix(), "reason": "raw line must be positive"}
        line_count = 0
        with raw_path.open("r", encoding="utf-8") as handle:
            for line_count, _line in enumerate(handle, start=1):
                if line_count >= line_number:
                    break
        return {
            "ref": ref,
            "status": "present" if line_count >= line_number else "missing",
            "path": raw_path.as_posix(),
            "line": line_number,
            "line_count": line_count,
            "inside_aoa_root": _is_under(raw_path, self.aoa_root),
        }

    def _bump(self, bucket: dict[str, int], value: Any) -> None:
        if value in (None, ""):
            return
        key = str(value)
        bucket[key] = bucket.get(key, 0) + 1

    def _top_counts(self, bucket: dict[str, int], limit: int = 12) -> list[dict[str, Any]]:
        return [
            {"key": key, "count": count}
            for key, count in sorted(bucket.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]
