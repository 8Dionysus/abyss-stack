from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse


DEFAULT_WORKSPACE_ROOT = Path("/srv/AbyssOS")
DEFAULT_TIMEOUT_SECONDS = 20.0
LIVE_READINESS_LIMIT: int | None = None
LIVE_READINESS_SAMPLE_LIMIT = 0

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
    "skill",
    "tool",
}
ALLOWED_DOC_TYPES = {"all", "session", "segment", "event", "incident"}
ALLOWED_SEARCH_DOC_TYPES = {"session", "segment", "event", "incident"}
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
    "route_layer": "--route-layer",
    "route_signal": "--route-signal",
    "archive_status": "--archive-status",
    "freshness_status": "--freshness-status",
    "date_from": "--date-from",
    "date_to": "--date-to",
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
    "tool",
    "mcp",
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
]


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


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).casefold() in {"1", "true", "yes", "on"}


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


def _compact_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": hit.get("doc_id"),
        "doc_type": hit.get("doc_type"),
        "session_id": hit.get("session_id"),
        "session_label": hit.get("session_label"),
        "session_title": hit.get("session_title"),
        "event_type": hit.get("event_type"),
        "family": hit.get("family"),
        "conversation_act": hit.get("conversation_act"),
        "session_act": hit.get("session_act"),
        "route_layers": hit.get("route_layers"),
        "route_signals": hit.get("route_signals"),
        "title": hit.get("title"),
        "snippet": hit.get("snippet"),
        "refs": hit.get("refs"),
        "freshness": hit.get("freshness"),
        "matched_routes": hit.get("matched_routes"),
    }


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
                "aoa_session_trace",
                "aoa_session_entity_usage_audit",
                "aoa_session_entity_usage_scenario_audit",
                "aoa_session_route",
                "aoa_session_brief",
                "aoa_session_retrieve",
                "aoa_session_evidence_packet",
                "aoa_session_freshness_check",
                "aoa_session_pattern_scan",
                "aoa_session_latest_diagnostics",
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
            "route_layers": ROUTE_LAYERS,
            "authority_boundary": self.authority_boundary(),
        }

    def _archive_command(self, command: str, args: list[str] | None = None, *, allow_nonzero_json: bool = False) -> dict[str, Any]:
        argv = [
            self.python_bin,
            self.script_path.as_posix(),
            command,
            *(args or []),
            "--workspace-root",
            self.workspace_root.as_posix(),
            "--aoa-root",
            self.aoa_root.as_posix(),
        ]
        output = self.command_runner(argv, self.timeout_seconds)
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
            "stderr": output.stderr.strip()[:1000],
            "authority_boundary": "MCP output routes to .aoa refs; it is not reviewed truth.",
        }
        return payload

    def readiness_policy(self, include_live: bool = False) -> dict[str, Any]:
        return {
            "schema": "aoa_session_memory_readiness_policy_v1",
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
                "command": "python3 /srv/AbyssOS/.aoa/scripts/aoa_session_memory.py route-readiness all --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa --write-report",
            },
            "authority_boundary": "MCP status is a read-only route companion; .aoa diagnostics and raw refs remain stronger evidence.",
        }

    def session_memory_status(self, include_live: bool = False) -> dict[str, Any]:
        provider = self._archive_command("search-provider-status", ["--provider", "all"])
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
        text = _ensure_short_text(query, "query")
        filters = filters or {}
        args = ["--query", text, "--limit", str(_coerce_limit(limit, 20, 100))]
        diagnostics: list[str] = []
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
        for key in sorted(set(filters) - set(SEARCH_FILTER_FLAGS) - {"provider", "explain"}):
            diagnostics.append(f"ignored unsupported filter {key!r}")
        if _as_bool(filters.get("explain"), default=True):
            args.append("--explain")
        payload = self._archive_command("search", args)
        if diagnostics:
            payload.setdefault("diagnostics", []).extend(diagnostics)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

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
        if kind not in ALLOWED_TRACE_KINDS:
            raise ValueError(f"unsupported trace kind: {kind}")
        if doc_type not in ALLOWED_DOC_TYPES:
            raise ValueError(f"unsupported doc_type: {doc_type}")
        args = [
            anchor_text,
            "--kind",
            kind,
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
        if kind not in ALLOWED_TRACE_KINDS:
            raise ValueError(f"unsupported trace kind: {kind}")
        args = [
            anchor_text,
            "--kind",
            kind,
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
        payload = self._archive_command("entity-usage-audit", args, allow_nonzero_json=True)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

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
        payload = self._archive_command("entity-usage-scenario-audit", args, allow_nonzero_json=True)
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
        if recipe not in ALLOWED_RETRIEVAL_RECIPES:
            raise ValueError(f"unsupported retrieval recipe: {recipe}")
        args = [recipe, "--limit", str(_coerce_limit(limit, 8, 50)), "--event-limit", str(_coerce_limit(event_limit, 12, 60))]
        if query:
            args.extend(["--query", _ensure_short_text(query, "query")])
        if session:
            args.extend(["--session", _safe_selector(session, "session")])
        payload = self._archive_command("retrieve", args)
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

    def session_freshness_check(self, refs: list[str] | None = None) -> dict[str, Any]:
        refs = refs or []
        provider = self._archive_command("search-provider-status", ["--provider", "portable_sqlite"])
        checks = [self._check_ref(ref) for ref in refs[:100]]
        return {
            "schema": "aoa_session_memory_freshness_check_v1",
            "ok": bool(provider.get("ok")) and not any(check["status"] == "missing" for check in checks),
            "mutates": False,
            "provider": provider,
            "ref_count": len(refs),
            "checks": checks,
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

    def maintenance_plan(self) -> dict[str, Any]:
        status = self.session_memory_status(include_live=False)
        provider = status.get("provider", {})
        atlas = status.get("atlas", {})
        graph = status.get("graph", {})
        latest_readiness = status.get("latest_route_readiness", {})
        return {
            "schema": "aoa_session_memory_maintenance_plan_v1",
            "ok": True,
            "mutates": False,
            "posture": "plan_only",
            "current_status": {
                "provider_ok": provider.get("ok"),
                "default_provider": provider.get("default_provider"),
                "atlas_entry_count": atlas.get("entry_count"),
                "graph_node_count": graph.get("node_count"),
                "graph_edge_count": graph.get("edge_count"),
                "graph_status": graph.get("status"),
                "latest_route_readiness_ok": (latest_readiness.get("reports") or [{}])[0].get("summary", {}).get("ok")
                if latest_readiness.get("reports")
                else None,
            },
            "allowed_operator_commands": [
                "python3 /srv/AbyssOS/.aoa/scripts/aoa_session_memory.py index-maintenance --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa",
                "python3 /srv/AbyssOS/.aoa/scripts/aoa_session_memory.py route-readiness all --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa --write-report",
                "python3 /srv/AbyssOS/.aoa/scripts/aoa_session_memory.py search-provider-status --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa --write-report",
                "python3 /srv/AbyssOS/.aoa/scripts/aoa_session_memory.py graph-maintenance all --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa --apply --batch-limit 3 --write-report",
                "python3 /srv/AbyssOS/.aoa/scripts/aoa_session_memory.py graph-quality-audit --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa --write-report",
            ],
            "offline_operator_commands": [
                "python3 /srv/AbyssOS/.aoa/scripts/aoa_session_memory.py graph-build all --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa --write --force-large-export",
                "python3 /srv/AbyssOS/.aoa/scripts/aoa_session_memory.py graph-maintenance all --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa --apply --export-sidecar --write-report",
            ],
            "mcp_stop_line": "This MCP reports the plan only; run maintenance outside MCP with explicit operator intent.",
            "authority_boundary": self.authority_boundary(),
        }

    def graph_neighborhood(self, anchor: str, kind: str = "auto", depth: int = 1, limit: int = 40) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        if kind not in ALLOWED_TRACE_KINDS:
            raise ValueError(f"unsupported graph kind: {kind}")
        args = [
            anchor_text,
            "--kind",
            kind,
            "--depth",
            str(_coerce_limit(depth, 1, 3)),
            "--limit",
            str(_coerce_limit(limit, 40, 200)),
        ]
        payload = self._archive_command("graph-neighborhood", args)
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def graph_timeline(self, anchor: str, kind: str = "auto", limit: int = 40) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        if kind not in ALLOWED_TRACE_KINDS:
            raise ValueError(f"unsupported graph kind: {kind}")
        payload = self._archive_command(
            "graph-timeline",
            [anchor_text, "--kind", kind, "--limit", str(_coerce_limit(limit, 40, 200))],
        )
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def graph_shortest_path(self, source: str, target: str, kind: str = "auto", max_depth: int = 4) -> dict[str, Any]:
        source_text = _ensure_short_text(source, "source")
        target_text = _ensure_short_text(target, "target")
        if kind not in ALLOWED_TRACE_KINDS:
            raise ValueError(f"unsupported graph kind: {kind}")
        payload = self._archive_command(
            "graph-shortest-path",
            [source_text, target_text, "--kind", kind, "--max-depth", str(_coerce_limit(max_depth, 4, 8))],
        )
        payload.setdefault("authority_boundary", self.authority_boundary())
        return payload

    def graph_cooccurrence(self, anchor: str, kind: str = "auto", limit: int = 30) -> dict[str, Any]:
        anchor_text = _ensure_short_text(anchor, "anchor")
        if kind not in ALLOWED_TRACE_KINDS:
            raise ValueError(f"unsupported graph kind: {kind}")
        payload = self._archive_command(
            "graph-cooccurrence",
            [anchor_text, "--kind", kind, "--limit", str(_coerce_limit(limit, 30, 100))],
        )
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
                kind = str(item.get("kind") or "auto")
                if kind not in ALLOWED_TRACE_KINDS:
                    raise ValueError(f"unsupported graph quality kind: {kind}")
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
            return self._archive_command("search-provider-status", ["--provider", "all"])
        if netloc == "readiness" and parts == ["route-layer"]:
            return self.latest_diagnostics("route-layer-readiness", limit=1)
        if netloc == "diagnostics" and len(parts) >= 2 and parts[0] == "latest":
            return self.latest_diagnostics(parts[1], limit=5)
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
                }
            return {"status": "missing", "index_path": index_path.as_posix()}
        return {
            "status": "present",
            "index_path": index_path.as_posix(),
            "generated_at": index.get("generated_at"),
            "truth_status": index.get("truth_status"),
            "node_count": index.get("node_count"),
            "edge_count": index.get("edge_count"),
            "node_type_counts": index.get("node_type_counts", {}),
            "edge_type_counts": index.get("edge_type_counts", {}),
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

    def _resolve_session_dir(self, session: str) -> Path | None:
        selector = (session or "latest").strip()
        sessions = self._registry_sessions()
        if selector == "latest":
            if sessions:
                latest = sorted(sessions, key=self._session_sort_key)[-1]
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

    def _session_sort_key(self, item: dict[str, Any]) -> tuple[str, int, str]:
        display = item.get("display") if isinstance(item.get("display"), dict) else {}
        return (
            str(display.get("date") or item.get("date") or ""),
            int(display.get("sequence") or item.get("sequence") or 0),
            str(display.get("label") or item.get("session_id") or ""),
        )

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

    def _check_ref(self, ref: str) -> dict[str, Any]:
        value = str(ref or "").strip()
        if not value:
            return {"ref": ref, "status": "invalid", "reason": "empty ref"}
        if "\x00" in value:
            return {"ref": ref, "status": "invalid", "reason": "NUL byte"}
        path_part = value.split("#", 1)[0]
        if path_part.startswith("raw:line:"):
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
            if candidate.exists():
                return {"ref": value, "status": "present", "path": candidate.as_posix(), "inside_aoa_root": True}
        return {"ref": value, "status": "unknown", "reason": "relative or symbolic ref requires session context"}

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
