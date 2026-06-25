from __future__ import annotations

import json
import os
import re
import shlex
import sqlite3
import subprocess
import time
import datetime as dt
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse


DEFAULT_WORKSPACE_ROOT = Path("/srv/AbyssOS")
DEFAULT_TIMEOUT_SECONDS = 20.0
STATUS_TIMEOUT_SECONDS = 60.0
SEARCH_TIMEOUT_SECONDS = 60.0
EVIDENCE_PACKET_TIMEOUT_SECONDS = 90.0
DEFAULT_SEARCH_MAX_SHARDS = 24
USAGE_NEIGHBORHOOD_TIMEOUT_SECONDS = 20.0
LIVE_READINESS_LIMIT: int | None = None
LIVE_READINESS_SAMPLE_LIMIT = 0
PROVIDER_DIRTY_SESSION_SAMPLE_LIMIT = 5
GOAL_LIFECYCLE_OBJECTIVE_PREVIEW_CHARS = 320
GOAL_LIFECYCLE_SAMPLE_OBJECTIVE_PREVIEW_CHARS = 220
GOAL_LIFECYCLE_SAMPLE_EVENT_LIMIT = 2

ALLOWED_TRACE_KINDS = {
    "auto",
    "decision",
    "entity",
    "external",
    "failure",
    "git",
    "github",
    "goal",
    "hook",
    "mcp",
    "path",
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
    "skill",
    "tool",
}
TRACE_KIND_ALIASES = {
    "mcp_service": "mcp",
    "mcp_services": "mcp",
    "mcp_tool": "tool",
    "mcp_tools": "tool",
}
ALLOWED_DOC_TYPES = {"all", "session", "segment", "event", "incident", "task_episode", "goal_lifecycle", "entity_registry"}
ALLOWED_SEARCH_DOC_TYPES = {"session", "segment", "event", "incident", "task_episode", "goal_lifecycle", "entity_registry"}
DEFAULT_GRAPH_QUALITY_ANCHORS = [
    "mcp:aoa-session-memory-mcp",
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
    "Do not widen beyond stdio without a later decision.",
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
    compact = dict(event)
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
    compact = dict(lifecycle)
    if "objective" in compact:
        preview, chars, omitted = _bounded_text(
            compact.get("objective"),
            limit=GOAL_LIFECYCLE_OBJECTIVE_PREVIEW_CHARS,
        )
        compact["objective"] = preview
        compact["objective_chars"] = chars
        compact["objective_omitted"] = omitted
    sample_events = compact.get("sample_events")
    if isinstance(sample_events, list):
        compact["sample_events"] = [
            _compact_goal_event(event)
            for event in sample_events[:GOAL_LIFECYCLE_SAMPLE_EVENT_LIMIT]
            if isinstance(event, dict)
        ]
        compact["omitted_sample_event_count"] = max(0, len(sample_events) - GOAL_LIFECYCLE_SAMPLE_EVENT_LIMIT)
    return compact


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
            "mcp_role": "stdio read-only access plane over .aoa session evidence, search, atlas, and diagnostics",
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
            "exposure": "stdio-only",
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
                "aoa_session_search",
                "aoa_session_agent_responses",
                "aoa_session_agent_closeouts",
                "aoa_session_agent_progress_updates",
                "aoa_session_agent_reasoning_windows",
                "aoa_session_task_episodes",
                "aoa_session_goal_lifecycles",
                "aoa_session_answer_neighborhood",
                "aoa_session_trace",
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
                "aoa_session_latest_diagnostics",
                "aoa_session_maintenance_status",
                "aoa_session_maintenance_plan",
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

    def _archive_command(
        self,
        command: str,
        args: list[str] | None = None,
        *,
        allow_nonzero_json: bool = False,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
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

    def _sqlite_table_exists(self, conn: sqlite3.Connection, name: str) -> bool:
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1", (name,)).fetchone()
        return row is not None

    def _sqlite_table_columns(self, conn: sqlite3.Connection, name: str) -> set[str]:
        try:
            return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}
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
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
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
            "provider": provider,
            "atlas": atlas,
            "graph": self._graph_summary(),
            "latest_route_readiness": diagnostics,
            "live_route_readiness": live_readiness,
            "readiness_policy": self.readiness_policy(include_live=include_live),
            "authority_boundary": self.authority_boundary(),
        }

    def session_search(self, query: str, filters: dict[str, Any] | None = None, limit: int = 20) -> dict[str, Any]:
        filters = filters or {}
        text = str(query or "").strip()
        active_filters = {
            key: value
            for key, value in filters.items()
            if key in SEARCH_FILTER_FLAGS and value not in (None, "")
        }
        diagnostics: list[str] = []
        supported_extra = {"provider", "explain"} | AGENT_ROUTE_SEARCH_FILTERS
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
        if text:
            args.extend(["--use-shards", "--max-shards", str(DEFAULT_SEARCH_MAX_SHARDS)])
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
            agent_events=_split_filter_values(active_filters.get("agent_event")),
            episode=episode,
            closeout_final=_as_bool(filters.get("closeout_final"), default=False),
            verification_state=str(filters.get("verification_state") or "any"),
            failure_state=str(filters.get("failure_state") or "any"),
            limit=limit,
            provider=str(filters.get("provider") or "portable_sqlite"),
            explain=_as_bool(filters.get("explain"), default=False),
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
        if not closeout_final and verification_state == "any" and failure_state == "any":
            fast_payload = self._agent_event_sqlite_fast_path(
                command="agent-responses",
                query=text,
                session=session,
                episode=episode,
                agent_events=normalized_agent_events,
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
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            if not self._sqlite_table_exists(conn, "documents"):
                return None
            columns = self._sqlite_table_columns(conn, "documents")
            if "agent_event" not in columns:
                return None
            filters = ["doc_type = 'event'"]
            params: list[Any] = []
            table_expr = "documents"
            session_dir = self._resolve_session_dir(session) if session else None
            if session:
                if "session_label" not in columns:
                    return None
                table_expr = "documents INDEXED BY idx_documents_session_agent_event"
                filters.append("session_label = ?")
                params.append(session_dir.name if session_dir is not None else session)
            elif explicit_agent_events and "agent_event" in columns:
                table_expr = "documents INDEXED BY idx_documents_agent_event"
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
                ORDER BY rowid DESC
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
        payload = self._archive_command(
            "entity-usage-audit",
            args,
            allow_nonzero_json=True,
            timeout_seconds=max(self.timeout_seconds, EVIDENCE_PACKET_TIMEOUT_SECONDS),
        )
        _annotate_trace_kind_payload(payload, requested_kind=kind, normalized_kind=route_kind)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

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
            selected_raw_preview_chars == 0
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
        payload = self._archive_command(
            "entity-usage-neighborhood",
            args,
            allow_nonzero_json=True,
            timeout_seconds=min(max(self.timeout_seconds, 10.0), USAGE_NEIGHBORHOOD_TIMEOUT_SECONDS),
        )
        _annotate_trace_kind_payload(payload, requested_kind=kind, normalized_kind=route_kind)
        payload.setdefault("authority_boundary", self.authority_boundary())
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
        return payload

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
            if prefix and normalized_value:
                candidates.append(f"{_route_key(prefix)}:{normalized_value}")
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

    def session_retrieve(
        self,
        recipe: str = "continue-session",
        query: str = "",
        session: str = "",
        limit: int = 8,
        event_limit: int = 12,
    ) -> dict[str, Any]:
        recipe_text = _safe_selector(recipe, "recipe", limit=120)
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
        diagnostics = []
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
        atlas_inventory = self._atlas_entity_inventory(
            layer_key=layer_key,
            query_text=query_text,
            session=session,
            limit=selected_limit,
            sample_limit=selected_sample_limit,
        )
        if atlas_inventory is not None:
            return atlas_inventory
        db_path = self.aoa_root / "search" / "aoa-search.sqlite3"
        if not db_path.is_file():
            return {
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
            conn = sqlite3.connect(str(db_path))
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
        except sqlite3.Error as exc:
            return {
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
        finally:
            if conn is not None:
                conn.close()
        return {
            "schema": "aoa_session_memory_entity_inventory_v1",
            "ok": True,
            "mutates": False,
            "layer": layer_key,
            "query": query_text,
            "session": session or None,
            "source": "portable_sqlite",
            "entity_count": len(entities),
            "entities": entities,
            "diagnostics": [],
            "truth_status": "session route-signal inventory; not runtime installed inventory",
            "authority_boundary": self.authority_boundary(),
        }

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
            "ok": True,
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
            "diagnostics": [],
            "truth_status": "session route-signal inventory; not runtime installed inventory",
            "authority_boundary": self.authority_boundary(),
        }

    def _inventory_sample_from_atlas_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
        refs = {
            "session": evidence.get("session_ref"),
            "segment": evidence.get("segment_ref"),
            "segment_index": evidence.get("generated_index_ref"),
            "raw": evidence.get("raw_ref"),
            "atlas_entry": entry.get("json"),
            "atlas_markdown": entry.get("markdown"),
        }
        return {
            "doc_id": entry.get("entry_id") or entry.get("json"),
            "doc_type": "atlas_entry",
            "session_id": entry.get("session_id"),
            "session_label": entry.get("session"),
            "session_title": entry.get("session_title"),
            "session_date": _session_date_from_entry(entry),
            "event_type": entry.get("event_type"),
            "family": entry.get("family"),
            "title": entry.get("title") or entry.get("summary"),
            "confidence": entry.get("confidence"),
            "refs": {key: value for key, value in refs.items() if value},
            "freshness": {"status": "atlas_generated", "reasons": []},
        }

    def _inventory_sample_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
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
            "title": row["title"],
            "refs": {key: value for key, value in refs.items() if value},
            "freshness": {
                "status": row["freshness_status"],
                "reasons": [row["stale_reason"]] if row["stale_reason"] else [],
            },
        }

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
        payload.setdefault("authority_boundary", self.authority_boundary())
        mcp_access = payload.get("mcp_access")
        if isinstance(mcp_access, dict):
            mcp_access["response_compacted"] = not full
            mcp_access["full_status_route"] = self._archive_command_line("maintenance-status", [*args, "--full"] if not full else args)
        return payload

    def maintenance_plan(self) -> dict[str, Any]:
        payload = self.session_maintenance_status(include_timers=False)
        payload["compatibility_tool"] = "aoa_session_maintenance_plan"
        payload["preferred_tool"] = "aoa_session_maintenance_status"
        return payload

    def graph_neighborhood(self, anchor: str, kind: str = "auto", depth: int = 1, limit: int = 40) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        route_kind = _coerce_trace_kind(kind, error_label="graph kind")
        args = [
            anchor_text,
            "--kind",
            route_kind,
            "--depth",
            str(_coerce_limit(depth, 1, 3)),
            "--limit",
            str(_coerce_limit(limit, 40, 200)),
        ]
        payload = self._archive_command("graph-neighborhood", args)
        _annotate_trace_kind_payload(payload, requested_kind=kind, normalized_kind=route_kind)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def graph_timeline(self, anchor: str, kind: str = "auto", limit: int = 40) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        route_kind = _coerce_trace_kind(kind, error_label="graph kind")
        payload = self._archive_command(
            "graph-timeline",
            [anchor_text, "--kind", route_kind, "--limit", str(_coerce_limit(limit, 40, 200))],
        )
        _annotate_trace_kind_payload(payload, requested_kind=kind, normalized_kind=route_kind)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def graph_shortest_path(self, source: str, target: str, kind: str = "auto", max_depth: int = 4) -> dict[str, Any]:
        source_text = _ensure_short_text(source, "source")
        target_text = _ensure_short_text(target, "target")
        route_kind = _coerce_trace_kind(kind, error_label="graph kind")
        payload = self._archive_command(
            "graph-shortest-path",
            [source_text, target_text, "--kind", route_kind, "--max-depth", str(_coerce_limit(max_depth, 4, 8))],
        )
        _annotate_trace_kind_payload(payload, requested_kind=kind, normalized_kind=route_kind)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def graph_cooccurrence(self, anchor: str, kind: str = "auto", limit: int = 30) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        route_kind = _coerce_trace_kind(kind, error_label="graph kind")
        payload = self._archive_command(
            "graph-cooccurrence",
            [anchor_text, "--kind", route_kind, "--limit", str(_coerce_limit(limit, 30, 100))],
        )
        _annotate_trace_kind_payload(payload, requested_kind=kind, normalized_kind=route_kind)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

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
        payload = self._archive_command("graphrag-packet", args)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def graph_eval(self, limit: int = 6, include_semantic_context: bool = False, rerank_local: bool = False) -> dict[str, Any]:
        args = ["--limit", str(_coerce_limit(limit, 6, 30))]
        if include_semantic_context:
            args.append("--include-semantic-context")
        if rerank_local:
            args.append("--rerank-local")
        payload = self._archive_command("graph-eval", args)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

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
        payload = self._archive_command("graph-quality-audit", args, allow_nonzero_json=True)
        payload.setdefault("authority_boundary", self.authority_boundary())
        payload.setdefault("mcp_note", "MCP defaults to a bounded anchor sample; run the CLI graph-quality-audit for a full default sweep.")
        return payload

    def explain_graph_packet(self, intent: str, anchor: str = "", query: str = "", limit: int = 8) -> dict[str, Any]:
        intent_text = _ensure_short_text(intent or query or anchor, "intent")
        args = [intent_text, "--limit", str(_coerce_limit(limit, 8, 50))]
        if anchor:
            args.extend(["--anchor", _ensure_short_text(anchor, "anchor")])
        if query:
            args.extend(["--query", _ensure_short_text(query, "query")])
        payload = self._archive_command("graph-explain-packet", args)
        payload.setdefault("authority_boundary", self.authority_boundary())
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
                return self._graph_summary()
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

    def _graph_summary(self) -> dict[str, Any]:
        index_path = self.aoa_root / "graph" / "index.json"
        sqlite_path = self.aoa_root / "graph" / "graph.sqlite3"
        freshness = self._latest_graph_freshness_summary()
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
                    "needs_graph_maintenance": freshness.get("needs_graph_maintenance"),
                    "needs_index_maintenance": freshness.get("needs_index_maintenance"),
                }
            return {
                "status": "missing",
                "index_path": index_path.as_posix(),
                "freshness": freshness,
                "needs_graph_maintenance": freshness.get("needs_graph_maintenance"),
                "needs_index_maintenance": freshness.get("needs_index_maintenance"),
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
            "needs_graph_maintenance": freshness.get("needs_graph_maintenance"),
            "needs_index_maintenance": freshness.get("needs_index_maintenance"),
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

    def _session_recency_key(self, item: dict[str, Any]) -> tuple[str, int, str]:
        date, sequence, label = self._session_sort_key(item)
        return (str(item.get("updated_at") or date), sequence, label)

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
