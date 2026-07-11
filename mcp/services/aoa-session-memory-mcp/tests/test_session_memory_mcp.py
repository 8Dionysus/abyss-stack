from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from aoa_session_memory_mcp.core import AoASessionMemoryMCPState, CommandOutput
from aoa_session_memory_mcp.server import build_server


VALIDATOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_session_memory_mcp.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_session_memory_mcp_under_test", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validator_help_does_not_run_live_smoke() -> None:
    result = subprocess.run(
        [sys.executable, VALIDATOR_PATH.as_posix(), "--help"],
        cwd=VALIDATOR_PATH.parents[1],
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0
    assert "Validate the aoa-session-memory MCP service" in result.stdout
    assert "usage:" in result.stdout


def test_cli_transport_preflight_reports_schema() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = (VALIDATOR_PATH.parents[1] / "src").as_posix()
    result = subprocess.run(
        [sys.executable, "-m", "aoa_session_memory_mcp.cli", "transport-preflight"],
        cwd=VALIDATOR_PATH.parents[1],
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["schema"] == "aoa_session_memory_mcp_transport_preflight_v1"
    assert payload["mutates"] is False
    assert "direct_tool_transport_status" in payload
    assert "next_action" in payload


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def seed_archive(root: Path) -> Path:
    aoa = root / ".aoa"
    session_dir = aoa / "sessions/2026-05-26__001__session-memory-mcp"
    session_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        aoa / "session-registry.json",
        {
            "sessions": [
                {
                    "session_id": "session-1",
                    "display": {
                        "date": "2026-05-26",
                        "sequence": 1,
                        "label": session_dir.name,
                        "title": "Session memory MCP",
                        "path": session_dir.as_posix(),
                    },
                }
            ]
        },
    )
    write_json(
        session_dir / "session.manifest.json",
        {
            "session_id": "session-1",
            "session_label": session_dir.name,
            "session_title": "Session memory MCP",
            "source": {"cwd": "/srv/AbyssOS"},
            "work_context": "/srv/AbyssOS",
            "archive_status": "indexed",
            "review_status": "provisional",
            "distillation_status": "raw_archived",
            "event_count": 2,
            "segment_count": 1,
            "raw": {
                "path": (session_dir / "raw/session.raw.jsonl").as_posix(),
                "sha256": "0" * 64,
                "blocks_index": (session_dir / "raw/blocks.index.json").as_posix(),
            },
            "raw_blocks": {
                "block_count": 1,
                "blocks": [
                    {
                        "segment_id": "000",
                        "role": "initial-to-latest",
                        "rel": "raw/blocks/000__initial-to-latest.raw.jsonl",
                        "source_range": {"from_line": 1, "to_line": 2},
                    }
                ],
            },
        },
    )
    write_json(
        session_dir / "session.index.json",
        {
            "session_id": "session-1",
            "work_context": "/srv/AbyssOS",
            "segments": [
                {
                    "segment_id": "000",
                    "role": "initial-to-latest",
                    "event_count": 2,
                    "source_range": {"from_line": 1, "to_line": 2},
                }
            ],
        },
    )
    (session_dir / "SESSION.md").write_text("# Session\n", encoding="utf-8")
    raw = session_dir / "raw/session.raw.jsonl"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("{}\n{}\n", encoding="utf-8")
    receipts = session_dir / "hooks/receipts.jsonl"
    receipts.parent.mkdir(parents=True, exist_ok=True)
    receipts.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema_version": 1,
                        "timestamp": "2026-05-26T00:01:00Z",
                        "hook_event_name": "UserPromptSubmit",
                        "ok": True,
                        "session_id": "session-1",
                        "actions": ["hook_event_recorded", "typing_prompt_mirrored", "prompt_hook_light_recorded"],
                        "errors": [],
                        "duration_ms": 42,
                        "typing_bridge": {"ok": True, "adapter": "codex_user_prompt_submit", "returncode": 0},
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "timestamp": "2026-05-26T00:02:00Z",
                        "hook_event_name": "UserPromptSubmit",
                        "ok": True,
                        "session_id": "session-1",
                        "actions": ["hook_event_recorded", "typing_prompt_bridge_failed", "prompt_hook_light_recorded"],
                        "errors": ["IndentationError: unexpected indent"],
                        "duration_ms": 77,
                        "typing_bridge": {
                            "ok": False,
                            "adapter": "codex_user_prompt_submit",
                            "returncode": 1,
                            "stderr_head": "IndentationError: unexpected indent",
                        },
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "timestamp": "2026-05-26T00:03:00Z",
                        "hook_event_name": "Stop",
                        "ok": True,
                        "session_id": "session-1",
                        "actions": ["hook_event_recorded"],
                        "errors": [],
                        "duration_ms": 12,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    write_json(
        aoa / "maps/index.json",
        {
            "schema_version": 1,
            "artifact_type": "agent_atlas_index",
            "generated_at": "2026-05-26T00:00:00Z",
            "axis_count": 2,
            "entry_count": 2,
            "axes": [
                {"axis": "by-mcp", "entry_count": 1, "index": (aoa / "maps/by-mcp/index.json").as_posix()},
                {"axis": "by-skill", "entry_count": 1, "index": (aoa / "maps/by-skill/index.json").as_posix()},
            ],
        },
    )
    entry_path = aoa / "maps/by-mcp/entries/aoa_session_memory_mcp__session.json"
    write_json(
        aoa / "maps/by-mcp/index.json",
        {
            "schema_version": 1,
            "artifact_type": "atlas_axis_index",
            "axis": "by-mcp",
            "entry_count": 1,
            "entries": [
                {
                    "axis": "by-mcp",
                    "route_key": "aoa_session_memory_mcp",
                    "session": session_dir.name,
                    "session_id": "session-1",
                    "confidence": "high",
                    "json": entry_path.as_posix(),
                    "evidence": {"raw_ref": "raw:line:1", "segment_ref": "000__initial-to-latest.md#event-000001"},
                }
            ],
        },
    )
    write_json(entry_path, {"route_key": "aoa_session_memory_mcp", "summary": "test entry"})
    skill_entry_path = aoa / "maps/by-skill/entries/aoa_decision__session.json"
    write_json(
        aoa / "maps/by-skill/index.json",
        {
            "schema_version": 1,
            "artifact_type": "atlas_axis_index",
            "generated_at": "2026-05-26T00:00:00Z",
            "axis": "by-skill",
            "entry_count": 1,
            "entries": [
                {
                    "axis": "by-skill",
                    "route_key": "aoa_decision",
                    "session": session_dir.name,
                    "session_id": "session-1",
                    "confidence": "high",
                    "json": skill_entry_path.as_posix(),
                    "markdown": (aoa / "maps/by-skill/entries/aoa_decision__session.md").as_posix(),
                    "evidence": {
                        "session_ref": (session_dir / "SESSION.md").as_posix(),
                        "raw_ref": "raw:line:2",
                        "segment_ref": "000__initial-to-latest.md#event-000002",
                        "generated_index_ref": (session_dir / "segments/000.index.json").as_posix(),
                    },
                }
            ],
        },
    )
    write_json(skill_entry_path, {"route_key": "aoa_decision", "summary": "test skill entry", "signal_count": 4})
    write_json(
        aoa / "maps/entity-registry.json",
        {
            "schema_version": 1,
            "artifact_type": "entity_registry_snapshot",
            "generated_at": "2026-05-26T00:00:00Z",
            "ok": True,
            "mutates": False,
            "entity_count": 2,
            "counts_by_kind": {"mcp": 1, "skill": 1},
            "counts_by_status": {"active": 2},
            "entries": [
                {
                    "entity_id": "mcp:aoa_session_memory_mcp",
                    "kind": "mcp",
                    "canonical_key": "aoa_session_memory_mcp",
                    "aliases": ["aoa-session-memory-mcp", "mcp:aoa_session_memory_mcp"],
                    "status": "active",
                    "route_layer": "mcp",
                    "route_signal": "mcp:aoa_session_memory_mcp",
                    "source_refs": [{"source_type": "mcp_service", "path": "/tmp/abyss-stack/mcp/services/aoa-session-memory-mcp"}],
                },
                {
                    "entity_id": "skill:aoa_decision",
                    "kind": "skill",
                    "canonical_key": "aoa_decision",
                    "aliases": ["aoa-decision", "skill:aoa_decision"],
                    "status": "active",
                    "route_layer": "skill",
                    "route_signal": "skill:aoa_decision",
                    "source_refs": [{"source_type": "codex_user_skills", "path": "/tmp/.codex/skills/aoa-decision/SKILL.md"}],
                }
            ],
            "truth_status": "generated_entity_registry_navigation_not_source_truth",
        },
    )
    search_db = aoa / "search/aoa-search.sqlite3"
    search_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(search_db))
    try:
        conn.executescript(
            """
            CREATE TABLE documents (
                id TEXT PRIMARY KEY,
                doc_type TEXT,
                session_id TEXT,
                session_label TEXT,
                session_title TEXT,
                session_date TEXT,
                event_type TEXT,
                family TEXT,
                title TEXT,
                segment_ref TEXT,
                segment_index_path TEXT,
                raw_ref TEXT,
                raw_block_ref TEXT,
                manifest_path TEXT,
                freshness_status TEXT,
                stale_reason TEXT
            );
            CREATE TABLE route_terms (
                id INTEGER PRIMARY KEY,
                layer TEXT,
                key TEXT,
                route_signal TEXT
            );
            CREATE TABLE document_routes (
                doc_rowid INTEGER,
                route_id INTEGER
            );
            """
        )
        conn.execute(
            """
            INSERT INTO documents (
                id, doc_type, session_id, session_label, session_title, session_date, event_type, family,
                title, segment_ref, segment_index_path, raw_ref, raw_block_ref, manifest_path,
                freshness_status, stale_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "event:session-1:000:000001",
                "event",
                "session-1",
                session_dir.name,
                "Session memory MCP",
                "2026-05-26",
                "USER_INTENT",
                "communication",
                "User asked for eval route",
                "000__initial-to-latest.md#event-000001",
                (session_dir / "segments/000.index.json").as_posix(),
                "raw:line:1",
                "raw/blocks/000__initial-to-latest.raw.jsonl#L1",
                (session_dir / "session.manifest.json").as_posix(),
                "fresh",
                "",
            ),
        )
        doc_rowid = conn.execute("SELECT rowid FROM documents WHERE id = ?", ("event:session-1:000:000001",)).fetchone()[0]
        for idx, (layer, key) in enumerate(
            [
                ("skill", "aoa_decision"),
                ("eval", "inspect_ai"),
                ("git", "git"),
                ("playbook", "session_audit"),
                ("technique", "entity_routing"),
                ("mechanic", "route_maintenance"),
            ],
            start=1,
        ):
            conn.execute(
                "INSERT INTO route_terms (id, layer, key, route_signal) VALUES (?, ?, ?, ?)",
                (idx, layer, key, f"{layer}:{key}"),
            )
            conn.execute("INSERT INTO document_routes (doc_rowid, route_id) VALUES (?, ?)", (doc_rowid, idx))
        conn.commit()
    finally:
        conn.close()
    write_json(
        aoa / "diagnostics/20260526T000000Z__route-layer-readiness.json",
        {
            "schema_version": 1,
            "artifact_type": "route_layer_readiness",
            "generated_at": "2026-05-26T00:00:00Z",
            "ok": True,
            "selected_count": 1,
            "covered_requirement_count": 22,
            "required_requirement_count": 22,
            "remaining": [],
        },
    )
    write_json(
        aoa / "diagnostics/20260526T000100Z__projection-catchup-catchup.json",
        {
            "schema_version": 1,
            "artifact_type": "session_memory_projection_catchup",
            "generated_at": "2026-05-26T00:01:00Z",
            "ok": True,
            "status": "nothing_to_do",
            "mutates": False,
            "apply": False,
            "profile": "catchup",
            "projection_completeness": {
                "schema_version": 1,
                "artifact_type": "session_memory_projection_completeness",
                "status": "current",
                "plan_only": True,
                "actionable_surface_ids": [],
                "deferred_surface_ids": [],
                "surfaces": {
                    "search_index": {"status": "current", "needs_maintenance": False},
                    "search_shards": {"status": "current", "needs_maintenance": False},
                    "atlas": {"status": "current", "needs_maintenance": False},
                    "entity_registry": {"status": "current", "needs_maintenance": False, "entity_count": 12},
                    "graph": {"status": "current", "needs_maintenance": False},
                    "live_tail": {"status": "current", "needs_maintenance": False},
                },
            },
            "next_route": {
                "id": "verify_projection_status",
                "status": "ready",
                "command": ["python3", "scripts/aoa_session_memory.py", "maintenance-status", "--no-timers"],
            },
        },
    )
    return aoa


PROVIDER_STATUS = {
    "schema_version": 1,
    "artifact_type": "search_provider_status",
    "provider_schema_version": 1,
    "ok": True,
    "default_provider": "portable_sqlite",
    "selected_provider": "portable_sqlite",
    "freshness_mode": "hot",
    "authority_law": ".aoa owns schemas, raw refs, segment refs, and freshness.",
    "providers": {
        "portable_sqlite": {
            "provider": "portable_sqlite",
            "ok": True,
            "status": "ready",
            "document_count": 10,
            "search_schema_version": "13",
            "has_documents": True,
            "has_route_index": True,
            "has_route_terms": True,
            "freshness": {
                "status": "current",
                "checked": True,
                "mode": "hot_persisted_state",
                "dirty_session_count": 0,
                "dirty_session_ids": [],
                "dirty_sessions": [],
            },
        }
    },
}

ROUTE_READINESS_FAST_GATE = {
    "schema_version": 1,
    "artifact_type": "route_layer_readiness",
    "ok": True,
    "target": "all",
    "limit": None,
    "selected_count": 250,
    "covered_requirement_count": 22,
    "required_requirement_count": 22,
    "remaining": [],
}

MAINTENANCE_STATUS = {
    "schema_version": 1,
    "artifact_type": "session_memory_maintenance_status",
    "ok": True,
    "mutates": False,
    "mode": "hot",
    "recommendation": "wait_live_catchup",
    "agent_route": {
        "action": "use_graph_search_for_stable_archive_wait_for_recent_live",
        "can_use_graph_search": True,
        "maintenance_required": False,
        "live_catchup_pending": True,
        "actionable_search_session_count": 0,
        "actionable_graph_source_count": 0,
        "deferred_live_count": 1,
        "raw_or_deep_route": "For claims about very recent live transcripts, wait for catch-up or run a deep check.",
    },
    "search": {
        "status": "current_with_deferred_live_updates",
        "actionable_dirty_session_count": 0,
        "deferred_live_session_count": 1,
    },
    "graph": {
        "status": "current",
        "actionable_count": 0,
        "dirty_count": 0,
        "missing_count": 0,
        "blocked_count": 0,
    },
    "route": {
        "status": "current",
        "needs_index_maintenance": False,
        "needs_graph_maintenance": False,
    },
    "next_actions": [
        {
            "id": "wait_live_catchup",
            "reason": "recent_live_sources_deferred_until_quiet_window",
            "command": ["python3", "scripts/aoa_session_memory.py", "auto-maintenance", "hot", "all", "--apply", "--write-report"],
        }
    ],
    "exact_next_command": "python3 scripts/aoa_session_memory.py auto-maintenance hot all --apply --write-report",
    "operations": {
        "schema_version": 1,
        "artifact_type": "session_memory_operations_summary",
        "mutates": False,
        "warning_count": 2,
        "warnings": [
            {"code": "search_db_large", "severity": "warning", "label": "search_db", "size_human": "13.3 GiB"},
            {"code": "graph_db_large", "severity": "warning", "label": "graph_db", "size_human": "57.2 GiB"},
        ],
        "latest_search_index": {
            "exists": True,
            "ok": True,
            "target": "all",
            "processed_count": 281,
            "document_count": 1630447,
            "elapsed_ms": 3042335,
            "documents_per_second": 535.92,
            "budget_exhausted": False,
        },
            "search_shards": {
                "status": "current",
                "shard_count": 3,
                "materialized_shard_count": 3,
                "raw_text_query_route": "structured shards use monolith fallback for raw-text queries unless materialized with --full-text",
                "latest_materialization": {
                    "exists": True,
                    "ok": True,
                    "status": "current",
                    "target": "2026-06-01__001__что-сейчас-грузит-процессор",
                    "processed_count": 1,
                    "document_count": 3426,
                    "elapsed_ms": 12612,
                    "documents_per_second": 271.65,
                    "sessions_per_second": 0.079,
                    "slow_session_warning_count": 0,
                    "slow_session_threshold_ms": 30000,
                    "slow_sessions": [
                        {
                            "shard": "month/2026-06",
                            "session_id": "019e80e6-9c6f-7600-8e46-cc87b4482a41",
                            "session_label": "2026-06-01__001__что-сейчас-грузит-процессор",
                            "status": "indexed",
                            "raw_text_status": "skipped_structured_projection",
                            "document_count": 3426,
                            "elapsed_ms": 1102,
                            "documents_per_second": 3108.89,
                            "warning": False,
                        }
                    ],
                },
                "fast_path_defaults": {
                    "agent_event_routes": {
                        "default_use_shards": True,
                    "default_projection": "materialized_shard_fanout",
                    "raw_text_query_projection": "monolith_fallback",
                    "raw_text_fallback_dependency_status": "monolith_required_for_raw_text_query",
                    "raw_text_fallback_dependency_next_route": "use the scoped full-text command for repeated literal raw-text queries in the affected shard",
                }
            },
            "raw_text_fallback_dependency": {
                "status": "monolith_required_for_raw_text_query",
                "raw_text_query_support": "monolith_fallback_required",
                "monolith_fallback_db_path": "/srv/AbyssOS/.aoa/search/aoa-search.sqlite3",
                "full_text_shard_count": 0,
                "structured_only_shard_count": 3,
                "unsupported_shard_count": 3,
                "nonmaterialized_shard_count": 0,
                "route_blocked_shard_count": 3,
                "route_blocked_shards": ["month/2026-04", "month/2026-05", "month/2026-06"],
                "scoped_full_text_next_commands": [
                    {
                        "shard": "month/2026-04",
                        "command": "python3 scripts/aoa_session_memory.py search-shards all --aoa-root /srv/AbyssOS/.aoa --shard month/2026-04 --full-text --write-report",
                    },
                    {
                        "shard": "month/2026-05",
                        "command": "python3 scripts/aoa_session_memory.py search-shards all --aoa-root /srv/AbyssOS/.aoa --shard month/2026-05 --full-text --write-report",
                    },
                    {
                        "shard": "month/2026-06",
                        "command": "python3 scripts/aoa_session_memory.py search-shards all --aoa-root /srv/AbyssOS/.aoa --shard month/2026-06 --full-text --write-report",
                    },
                ],
                "global_full_text_next_command": "python3 scripts/aoa_session_memory.py search-shards all --aoa-root /srv/AbyssOS/.aoa --full-text --write-report",
                "quality_tradeoff": "raw-text recall is preserved by monolith fallback until a scoped full-text shard is explicitly materialized.",
                "weight_tradeoff": "structured shards stay slim; full-text shards add FTS and compressed-body weight, so use scoped full-text shards for repeated literal raw-text work.",
                "authority_boundary": "monolith and shards are generated search projections; raw transcript and session indexes remain the evidence authority.",
                "next_route": "use the scoped full-text command for repeated literal raw-text queries in the affected shard",
            },
        },
        "last_successful_auto_maintenance": {
            "hot": {"status": "wait_live_catchup", "elapsed_ms": 2387},
            "catchup": {"status": "nothing_to_do", "elapsed_ms": 3136},
        },
        "recent_problem_job_count": 0,
        "why_maintenance_long": [
            {"reason": "search_index_phase", "phase": "session_bulk_index", "elapsed_ms": 2081000},
            {"reason": "sqlite_index_build", "index": "idx_document_routes_route", "elapsed_ms": 96131},
        ],
        "truth_status": "diagnostic_projection_for_operator_routing_not_archive_truth",
    },
    "mcp_boundary": "MCP may expose this packet read-only; repair/reindex/maintenance commands stay outside MCP.",
}

SEARCH_RESULTS = {
    "schema_version": 1,
    "artifact_type": "search_results",
    "ok": True,
    "result_count": 1,
    "results": [
        {
            "doc_id": "event:session-1:000:000001",
            "doc_type": "event",
            "session_id": "session-1",
            "session_label": "2026-05-26__001__session-memory-mcp",
            "session_date": "2026-05-26",
            "segment_id": "000",
            "event_id": "000001",
            "event_type": "USER_INTENT",
            "family": "communication",
            "conversation_act": "operator_request",
            "session_act": "memory_request",
            "agent_event": "assistant_answer",
            "task_episode_id": "task-0001",
            "route_layers": "|entity|mcp|tool|",
            "route_signals": "|entity:aoa_session_memory_mcp|mcp:aoa_session_memory_mcp|tool:exec_command|",
            "refs": {
                "session": "/tmp/archive/session.manifest.json",
                "segment": "000__initial-to-latest.md#event-000001",
                "raw": "raw:line:1",
            },
            "freshness": {"status": "fresh", "reasons": []},
        }
    ],
}

LITERAL_QUERY_PLAN = {
    "schema_version": 1,
    "artifact_type": "session_memory_literal_query_plan",
    "ok": True,
    "mutates": False,
    "query": "aoa-session-memory-mcp",
    "kind": "mcp",
    "query_shape": {"primary": "entity_anchor", "signals": ["entity_anchor"]},
    "primary_route": {
        "route_id": "entity_usage_chain",
        "reason": "query resolves to a typed operational anchor",
        "estimated_cost": "low",
        "command": "python3 scripts/aoa_session_memory.py usage-chain aoa-session-memory-mcp --kind mcp",
    },
    "ordered_routes": [
        {"route_id": "entity_usage_chain", "estimated_cost": "low"},
        {"route_id": "entity_usage_audit", "estimated_cost": "low"},
        {"route_id": "trace_route", "estimated_cost": "low"},
        {"route_id": "monolith_raw_text_fallback", "estimated_cost": "high"},
    ],
    "cost_profile": {
        "structured_first": True,
        "uses_fts_first": False,
        "monolith_fallback_first": False,
    },
    "route_candidates": [{"layer": "mcp", "key": "aoa_session_memory_mcp", "route_signal": "mcp:aoa_session_memory_mcp"}],
    "authority_boundary": "This planner chooses a cheap first route; raw transcript and segment indexes remain evidence authority.",
}


def literal_query_plan_fixture(query: str) -> dict[str, Any]:
    payload = json.loads(json.dumps(LITERAL_QUERY_PLAN))
    payload["query"] = query
    if "raw_unavailable" in query:
        payload["query_shape"] = {"primary": "error_text", "signals": ["error_text"]}
        payload["primary_route"] = {"route_id": "route_signal_structured_search", "estimated_cost": "low"}
        payload["ordered_routes"] = [
            {"route_id": "route_signal_structured_search", "estimated_cost": "low"},
            {"route_id": "monolith_raw_text_fallback", "estimated_cost": "high"},
        ]
    elif "найди все MCP" in query:
        payload["query_shape"] = {"primary": "entity_class", "signals": ["entity_class"]}
        payload["route_anchor"] = "mcp"
        payload["route_anchor_source"] = "broad_entity_class_query"
        payload["broad_entity_class"] = {"layer": "mcp", "usage_intent": True}
        payload["primary_route"] = {"route_id": "entity_inventory", "estimated_cost": "low"}
        payload["ordered_routes"] = [
            {"route_id": "entity_inventory", "estimated_cost": "low"},
            {"route_id": "entity_registry_class", "estimated_cost": "low"},
            {"route_id": "entity_usage_scenario_audit", "estimated_cost": "medium"},
            {"route_id": "monolith_raw_text_fallback", "estimated_cost": "high"},
        ]
    elif query.startswith("python3 "):
        payload["query_shape"] = {"primary": "command", "signals": ["command"], "command_anchor": "scripts/aoa_session_memory.py"}
        payload["route_anchor"] = "scripts/aoa_session_memory.py"
        payload["route_anchor_source"] = "command_anchor"
        payload["primary_route"] = {"route_id": "command_structured_search", "estimated_cost": "low"}
        payload["ordered_routes"] = [
            {"route_id": "command_structured_search", "estimated_cost": "low"},
            {"route_id": "entity_usage_chain", "estimated_cost": "low"},
            {"route_id": "monolith_raw_text_fallback", "estimated_cost": "high"},
        ]
    return payload

AGENT_RESPONSES = {
    "schema_version": 1,
    "artifact_type": "agent_event_route_results",
    "ok": True,
    "agent_events": ["assistant_answer"],
    "result_count": 1,
    "results": SEARCH_RESULTS["results"],
}

AGENT_WINDOWS = {
    "schema_version": 1,
    "artifact_type": "agent_event_windows",
    "ok": True,
    "window_count": 1,
    "windows": [
        {
            "ok": True,
            "event_id": "000001",
            "events": [
                {"event_id": "000001", "agent_event": "assistant_reasoning_boundary", "raw_ref": "raw:line:1"}
            ],
        }
    ],
}

TASK_EPISODES = {
    "schema_version": 1,
    "artifact_type": "task_episode_route_results",
    "ok": True,
    "result_count": 1,
    "results": [
        {
            "session_id": "session-1",
            "session_label": "2026-05-26__001__session-memory-mcp",
            "episode_id": "task-0001",
            "status": "closed",
            "verification_state": "verified",
            "failure_state": "no_failure_seen",
            "start_user_ref": {"raw_ref": "raw:line:1"},
            "sample_refs": {
                "answers": [
                    {"event_id": "000002", "raw_ref": "raw:line:2", "segment_index": "/tmp/full.index.json"},
                    {"event_id": "000003", "raw_ref": "raw:line:3", "segment_index": "/tmp/full.index.json"},
                ],
                "progress": [
                    {"event_id": "000004", "raw_ref": "raw:line:4"},
                ],
            },
        }
    ],
}

GOAL_LIFECYCLES = {
    "schema_version": 1,
    "artifact_type": "goal_lifecycle_route_results",
    "goal_lifecycle_schema_version": 2,
    "ok": True,
    "target": "all",
    "session": "session-1",
    "goal_id": "goal-0001",
    "status": "complete",
    "event_kind": "goal_completed",
    "selected_goal_lifecycle_count": 1,
    "result_count": 1,
    "results": [
        {
            "schema_version": 2,
            "session_label": "2026-05-26__001__session-memory-mcp",
            "session_id": "session-1",
            "goal_id": "goal-0001",
            "goal_instance_id": "session-1:goal-0001",
            "status": "complete",
            "objective": "Close goal lifecycle routing " * 40,
            "objective_source": "goal_tool_output",
            "observed_goal": {
                "threadId": "session-1",
                "objective": "Observed goal state objective " * 30,
                "status": "complete",
                "createdAt": 1780000000,
                "updatedAt": 1780000100,
            },
            "event_count": 5,
            "event_kinds": ["goal_created", "goal_updated", "goal_completed"],
            "event_ids": ["000002", "000003", "000004", "000005", "000006"],
            "task_episode_ids": ["task-0001"],
            "ambiguity_flags": [],
            "usage": {"tokens_used": 1234, "time_used_seconds": 56},
            "refs": {
                "created": {"raw_ref": "raw:line:2", "segment_ref": "000__initial-to-latest.md#event-000002"},
                "completed": {"raw_ref": "raw:line:6", "segment_ref": "000__initial-to-latest.md#event-000006"},
            },
            "graph_refs": ["graph:node:goal_lifecycle:session-1:goal-0001"],
            "raw_refs": ["raw:line:2", "raw:line:6"],
            "segment_refs": ["000__initial-to-latest.md#event-000002", "000__initial-to-latest.md#event-000006"],
            "state_observations": [
                {
                    "source": "goal_tool_output",
                    "event_id": "000007",
                    "state": {
                        "threadId": "session-1",
                        "objective": "Observed goal state objective " * 30,
                        "status": "complete",
                        "createdAt": 1780000000,
                        "updatedAt": 1780000100,
                    },
                    "refs": {"raw_ref": "raw:line:7", "segment_ref": "000__initial-to-latest.md#event-000007"},
                },
                {
                    "source": "goal_tool_output",
                    "event_id": "000008",
                    "state": {"status": "complete", "updatedAt": 1780000200},
                    "refs": {"raw_ref": "raw:line:8", "segment_ref": "000__initial-to-latest.md#event-000008"},
                },
                {
                    "source": "goal_tool_output",
                    "event_id": "000009",
                    "state": {"status": "complete", "updatedAt": 1780000300},
                    "refs": {"raw_ref": "raw:line:9", "segment_ref": "000__initial-to-latest.md#event-000009"},
                },
            ],
            "usage_observations": [
                {"source": "goal_tool_args", "event_id": "000006", "usage": {"status": "complete"}},
                {
                    "source": "goal_tool_output",
                    "event_id": "000007",
                    "usage": {"goal": {"tokensUsed": 1234, "timeUsedSeconds": 56}},
                    "refs": {"raw_ref": "raw:line:7", "segment_ref": "000__initial-to-latest.md#event-000007"},
                },
                {
                    "source": "goal_tool_output",
                    "event_id": "000008",
                    "usage": {"goal": {"tokensUsed": 1300}},
                    "refs": {"raw_ref": "raw:line:8", "segment_ref": "000__initial-to-latest.md#event-000008"},
                },
            ],
            "sample_events": [
                {"event_kind": "goal_created", "event_id": "000002", "raw_ref": "raw:line:2", "objective": "Create goal with a deliberately long objective " * 20},
                {"event_kind": "goal_updated", "event_id": "000003", "raw_ref": "raw:line:3"},
                {"event_kind": "goal_updated", "event_id": "000004", "raw_ref": "raw:line:4"},
                {"event_kind": "goal_updated", "event_id": "000005", "raw_ref": "raw:line:5"},
                {"event_kind": "goal_completed", "event_id": "000006", "raw_ref": "raw:line:6"},
            ],
            "truth_level": "generated_goal_lifecycle_navigation_not_reviewed_truth",
        }
    ],
}

TRACE_RESULTS = {
    "schema_version": 1,
    "artifact_type": "route_trace",
    "ok": True,
    "anchor": "aoa-session-memory-mcp",
    "route_candidates": [
        {
            "layer": "mcp",
            "key": "aoa_session_memory_mcp",
            "route_signal": "mcp:aoa_session_memory_mcp",
            "axis": "by-mcp",
        }
    ],
    "results": SEARCH_RESULTS["results"],
}

ENTITY_REGISTRY = {
    "schema_version": 1,
    "artifact_type": "entity_registry_snapshot",
    "ok": True,
    "mutates": False,
    "entity_count": 2,
    "entries": [
        {
            "entity_id": "mcp:aoa_session_memory_mcp",
            "kind": "mcp",
            "canonical_key": "aoa_session_memory_mcp",
            "status": "active",
            "route_layer": "mcp",
            "route_signal": "mcp:aoa_session_memory_mcp",
            "source_refs": [{"source_type": "mcp_service", "path": "/tmp/abyss-stack/mcp/services/aoa-session-memory-mcp"}],
        },
        {
            "entity_id": "skill:aoa_decision",
            "kind": "skill",
            "canonical_key": "aoa_decision",
            "status": "active",
            "route_layer": "skill",
            "route_signal": "skill:aoa_decision",
            "source_refs": [{"source_type": "codex_user_skills", "path": "/tmp/.codex/skills/aoa-decision/SKILL.md"}],
        }
    ],
    "truth_status": "generated_entity_registry_navigation_not_source_truth",
}

ENTITY_USAGE_AUDIT = {
    "schema_version": 1,
    "artifact_type": "session_memory_entity_usage_audit",
    "ok": True,
    "anchor": "aoa-session-memory-mcp",
    "kind": "mcp",
    "usage_event_count": 1,
    "consequence_event_count": 1,
    "document_refs": [{"kind": "mentioned_path", "value": "docs/decisions/README.md"}],
    "usage_events": [
        {
            "event_type": "TOOL_CALL",
            "title": "Tool call: aoa_session_memory_search",
            "refs": {"raw": "raw:line:2", "segment": "000__initial-to-latest.md#event-000002"},
        }
    ],
    "consequence_events": [
        {
            "event_type": "TOOL_OUTPUT",
            "relation": "same_correlation_id",
            "refs": {"raw": "raw:line:3", "segment": "000__initial-to-latest.md#event-000003"},
        }
    ],
}

ENTITY_USAGE_CHAIN = {
    "schema_version": 1,
    "artifact_type": "session_memory_entity_usage_chain",
    "ok": True,
    "anchor": "aoa-session-memory-mcp",
    "kind": "mcp",
    "counts": {
        "usage_event_count": 1,
        "consequence_event_count": 1,
        "chain_count": 1,
        "chain_with_result_or_consequence_count": 1,
        "evidence_ref_count": 2,
    },
    "quality": {
        "direct_usage_present": True,
        "result_or_consequence_present": True,
        "raw_or_segment_ref_present": True,
        "skipped_graph_rag_packet": True,
        "skipped_graph_neighborhood": True,
        "skipped_raw_preview_neighborhood": True,
        "noise_flag_count": 0,
    },
    "usage_chain": {
        "entrypoint_events": [],
        "chains": [
            {
                "usage_event": {
                    "event_type": "TOOL_CALL",
                    "title": "Tool call: aoa_session_memory_search",
                    "refs": {"raw": "raw:line:2", "segment": "000__initial-to-latest.md#event-000002"},
                },
                "result_or_consequence_events": [
                    {
                        "event_type": "TOOL_OUTPUT",
                        "relation": "same_correlation_id",
                        "refs": {"raw": "raw:line:3", "segment": "000__initial-to-latest.md#event-000003"},
                    }
                ],
                "result_or_consequence_count": 1,
                "has_result_or_consequence": True,
            }
        ],
    },
    "document_refs": [{"kind": "mentioned_path", "value": "docs/decisions/README.md"}],
    "evidence_refs": [
        {"kind": "raw_line", "value": "raw:line:2"},
        {"kind": "segment_markdown", "value": "000__initial-to-latest.md#event-000002"},
    ],
    "diagnostics": [],
}

ENTITY_USAGE_NEIGHBORHOOD = {
    "schema_version": 1,
    "artifact_type": "session_memory_entity_usage_neighborhood",
    "ok": True,
    "anchor": "aoa-session-memory-mcp",
    "kind": "mcp",
    "quality": {
        "usage_neighborhood_present": True,
        "consequence_present": True,
        "raw_preview_available": True,
        "neighborhood_count": 1,
        "consequence_event_count": 2,
    },
    "neighborhoods": [
        {
            "ok": True,
            "source_usage_event": {
                "event_type": "TOOL_CALL",
                "title": "Tool call: aoa_session_memory_search",
                "raw_preview": {"status": "available", "line": 2, "text": "call search"},
                "refs": {"raw": "raw:line:2", "segment": "000__initial-to-latest.md#event-000002"},
            },
            "local_events": [
                {"offset": 0, "event_type": "TOOL_CALL", "relation": "selected_usage"},
                {"offset": 1, "event_type": "TOOL_OUTPUT", "relation": "same_correlation_id"},
                {"offset": 2, "event_type": "ASSISTANT_MESSAGE", "relation": "consequence_candidate"},
            ],
            "consequence_events": [
                {"offset": 1, "event_type": "TOOL_OUTPUT", "relation": "same_correlation_id"},
                {"offset": 2, "event_type": "ASSISTANT_MESSAGE", "relation": "consequence_candidate"},
            ],
            "document_refs": [{"kind": "mentioned_path", "value": "docs/decisions/README.md"}],
        }
    ],
}

SKILL_EVIDENCE_SUPPORTED_STATES = [
    "selected",
    "procedure_observed",
    "verified",
    "completed",
    "deflected",
    "prompt_visible",
    "skill_read",
    "edited",
    "mentioned",
    "cooccurrence",
]

SKILL_EVIDENCE_SUMMARY = {
    "schema_version": "skill_usage_evidence_v1",
    "candidate_only": True,
    "supported_states": SKILL_EVIDENCE_SUPPORTED_STATES,
    "automatic_candidate_states": [
        "cooccurrence",
        "edited",
        "mentioned",
        "selected",
        "skill_read",
    ],
    "receipt_or_review_states": [
        "completed",
        "deflected",
        "procedure_observed",
        "prompt_visible",
        "verified",
    ],
    "state_counts": {"selected": 1, "skill_read": 1},
    "association_state_counts": {"selected": 1, "skill_read": 2},
    "input_event_count": 3,
    "unique_evidence_event_count": 2,
    "unique_evidence_fact_count": 2,
    "duplicate_evidence_association_count": 1,
    "rejection_edge_states": ["false_correlation"],
    "dimensions": {
        "prompt_visible_candidate_present": False,
        "selection_candidate_present": True,
        "skill_read_candidate_present": True,
        "procedure_candidate_present": False,
        "verification_candidate_present": False,
        "completion_candidate_present": False,
        "deflection_candidate_present": False,
    },
    "dispatch_candidate_present": True,
    "behavioral_candidate_present": False,
    "correlation_rejections": {
        "state": "false_correlation",
        "edge_count": 6,
        "unique_event_count": 6,
    },
    "receipt_or_review_ingestion_available": False,
    "invocation_claim_allowed": False,
    "invocation_claim_blocker": "candidate_states_require_task_episode_correlation_and_owner_review",
    "authority_boundary": (
        "session-memory classifies candidate skill evidence; "
        "skill effectiveness and eval verdicts remain owner-reviewed"
    ),
}

SKILL_USAGE_EVENT = {
    "doc_id": "event:session-skill:000004",
    "source": "portable_sqlite",
    "source_doc_id": "event:session-skill:000004",
    "distance": 0,
    "relation": "selected_usage",
    "role": "usage",
    "session_id": "session-skill",
    "session_label": "2026-07-10__001__skill-evidence",
    "session_date": "2026-07-10",
    "segment_id": "000__initial-to-latest",
    "event_id": "000004",
    "event_type": "FILE_READ",
    "correlation_id": "skill-call",
    "family": "file",
    "phase": "execution",
    "actor": "assistant",
    "action": "inspect_workspace",
    "outcome": "observed",
    "skill_evidence_state": "skill_read",
    "usage_actions": ["read"],
    "primary_usage_action": "read",
    "conversation_act": "assistant_action",
    "session_act": "file_inspection",
    "matched_routes": ["skill:aoa_tdd_slice"],
    "route_signals": ["skill:aoa_tdd_slice"],
    "route_signal_count": 1,
    "route_signals_truncated": False,
    "title": "Read aoa-tdd-slice/SKILL.md",
    "snippet": "bounded skill read",
    "refs": {
        "session": "sessions/skill/session.json",
        "segment": "segments/000.md#event-000004",
        "segment_index": "segments/000.index.json",
        "raw": "raw:line:4",
        "raw_block": "raw:block:4-4",
    },
    "freshness": {"status": "fresh", "basis": "fixture"},
    "content": "PRIVATE RAW TRANSCRIPT BODY MUST NOT CROSS MCP",
}

SKILL_SELECTED_OUTCOME_EVENT = {
    **SKILL_USAGE_EVENT,
    "doc_id": "event:session-skill:000005",
    "source_doc_id": "event:session-skill:000004",
    "distance": 1,
    "relation": "consequence_candidate",
    "role": "outcome",
    "event_id": "000005",
    "event_type": "ASSISTANT_MESSAGE",
    "skill_evidence_state": "selected",
    "usage_actions": ["selected"],
    "primary_usage_action": "selected",
    "title": "Using aoa-tdd-slice for the bounded change",
    "refs": {
        "session": "sessions/skill/session.json",
        "segment": "segments/000.md#event-000005",
        "segment_index": "segments/000.index.json",
        "raw": "raw:line:5",
        "raw_block": "raw:block:5-5",
    },
}

SKILL_FALSE_CORRELATION_EVENTS = [
    {
        **SKILL_USAGE_EVENT,
        "doc_id": f"event:session-skill:rejected-{index}",
        "source_doc_id": "event:session-skill:000004",
        "distance": index + 1,
        "relation": "false_correlation",
        "role": "context",
        "event_id": f"rejected-{index}",
        "event_type": "TOOL_OUTPUT",
        "correlation_id": f"other-call-{index}",
        "source_correlation_id": "skill-call",
        "rejected_correlation_id": f"other-call-{index}",
        "skill_evidence_state": "false_correlation",
        "usage_actions": ["context"],
        "primary_usage_action": "context",
        "title": "Foreign parallel tool output",
        "refs": {
            "session": "sessions/skill/session.json",
            "segment": f"segments/000.md#event-rejected-{index}",
            "segment_index": "segments/000.index.json",
            "raw": f"raw:line:{20 + index}",
            "raw_block": f"raw:block:{20 + index}-{20 + index}",
        },
    }
    for index in range(6)
]

ENTITY_USAGE_SCENARIO_AUDIT = {
    "schema_version": 1,
    "artifact_type": "session_memory_entity_usage_scenario_audit",
    "ok": True,
    "seed": "fixture-random",
    "quality": {
        "sample_count": 2,
        "passed_count": 1,
        "warn_count": 1,
        "failed_count": 0,
        "raw_preview_counts": {"available": 3},
    },
    "samples": [
        {"status": "passed", "candidate": {"kind": "tool", "anchor": "exec_command"}, "usage_event_count": 1},
        {"status": "warn", "candidate": {"kind": "path", "anchor": "docs_decisions_readme_md"}, "usage_event_count": 0},
    ],
}

LIVE_SCENARIO_AUDIT = {
    "schema_version": 1,
    "artifact_type": "session_memory_live_scenario_audit",
    "ok": True,
    "mutates": False,
    "truth_status": "bounded_live_scenario_audit_not_reviewed_truth",
    "seed": "fixture-live",
    "profiles": ["entity_registry_lookup"],
    "parameters": {"sample_size": 2, "recent_days": 90, "limit": 2},
    "quality": {
        "scenario_count": 1,
        "passed_count": 1,
        "warn_count": 0,
        "failed_count": 0,
        "actionable_gap_count": 0,
        "raw_or_segment_ref_scenario_count": 0,
        "first_useful_packet_ms": 150,
    },
    "scenarios": [
        {
            "profile": "entity_registry_lookup",
            "status": "passed",
            "sample_count": 5,
            "failed_count": 0,
            "status_counts": {"active": 1, "observed": 1, "unknown": 1, "stale": 1, "removed": 1},
            "active_lookup_count": 1,
            "observed_lookup_count": 1,
            "unknown_lookup_count": 1,
            "stale_lookup_count": 1,
            "removed_lookup_count": 1,
            "retired_lookup_count": 2,
            "source_ref_count": 4,
            "registered_lookup_count": 4,
            "unregistered_lookup_count": 1,
            "transition_probe_count": 2,
        }
    ],
    "actionable_gaps": [],
}

RETRIEVAL_PACKET = {
    "schema_version": 1,
    "artifact_type": "retrieval_packet",
    "ok": True,
    "recipe": "continue-session",
    "evidence_hits": SEARCH_RESULTS["results"],
    "session": {"session_id": "session-1", "manifest": "/tmp/archive/session.manifest.json"},
}

GRAPH_NEIGHBORHOOD = {
    "schema_version": 1,
    "artifact_type": "session_memory_graph_neighborhood",
    "ok": True,
    "mutates": False,
    "anchor": "aoa-session-memory-mcp",
    "node_count": 3,
    "edge_count": 2,
    "truncated": True,
    "next_command": "python3 scripts/aoa_session_memory.py graph-neighborhood aoa-session-memory-mcp --kind mcp --depth 1 --limit 20 --edge-limit 7",
    "next_expansion_command": "python3 scripts/aoa_session_memory.py graph-neighborhood aoa-session-memory-mcp --kind mcp --depth 2 --limit 40 --edge-limit 14",
    "next_expansion_reason": "increase depth or edge budget only when relation context is still insufficient",
    "nodes": [
        {"id": "route:mcp:mcp:aoa_session_memory_mcp", "type": "mcp", "label": "mcp:aoa_session_memory_mcp"},
        {"id": "event:session-1:000:000001", "type": "event", "title": "debug mcp"},
    ],
    "edges": [{"source": "event:session-1:000:000001", "target": "route:mcp:mcp:aoa_session_memory_mcp", "type": "mentions_route_signal"}],
    "evidence_refs": [
        {
            "session_id": "session-1",
            "segment_id": "000",
            "event_id": "000001",
            "refs": {"raw": "raw:line:1", "segment": "000__initial-to-latest.md#event-000001"},
        }
    ],
    "freshness": {
        "status": "graph_store_stale",
        "warning": "graph store has stale hot-gate state; verify through raw refs",
        "hot_gate_status": "stale",
        "needs_maintenance": True,
        "needs_full_rebuild": False,
        "actionable_graph_source_count": 2531,
        "deferred_live_source_count": 1139,
        "ledger_store_missing_count": 52,
        "latest_maintenance_remaining_count": 2452,
        "hot_gate_diagnostics": ["maintenance_queue_empty_but_ledger_actionable_sources_present"],
        "maintenance_recommendation": {
            "route": "budgeted_graph_maintenance",
            "reason": "graph_store_ledger_mismatch_budgeted_recovery",
            "source_count": 5536,
            "existing_source_count": 5400,
            "actionable_count": 2531,
            "blocked_count": 10,
            "dominant_reason": "ledger_actionable_sources_not_queued",
            "command": "python3 scripts/aoa_session_memory.py graph-maintenance all --apply --batch-limit 25",
            "notes": ["blocked_sources_need_lower_layer_repair"],
        },
    },
}

OPERATIONAL_ROUTE_ROLLUP_QUERY = {
    "schema_version": 1,
    "artifact_type": "session_memory_search_operational_route_rollup_query",
    "ok": True,
    "status": "matched",
    "mutates": False,
    "filters": {
        "query": "exec_command",
        "layer": "tool",
        "key": "",
        "route_signal": "",
        "limit": 3,
        "ref_limit": 2,
    },
    "results": [
        {
            "layer": "tool",
            "key": "exec_command",
            "route_signal": "tool:exec_command",
            "posting_count": 8,
            "session_count": 3,
            "raw_refs": ["raw:line:1"],
            "segment_refs": ["segments/000__initial-to-latest.md#event-000001"],
            "session_ids": ["session-1"],
        }
    ],
    "result_count": 1,
    "quality": {
        "uses_materialized_rollup": True,
        "raw_or_segment_ref_present": True,
        "freshness_status": "current",
        "truncated": False,
    },
    "cost_profile": {
        "uses_materialized_route_rollup": True,
        "resamples_shards": False,
        "opens_monolith": False,
        "uses_fts": False,
        "hydrates_body": False,
        "elapsed_ms": 12,
    },
    "diagnostics": [],
}

OPERATIONAL_DIRECT_EVENT_ROLLUP_QUERY = {
    "schema_version": 1,
    "artifact_type": "session_memory_search_operational_direct_event_rollup_query",
    "ok": True,
    "status": "matched",
    "mutates": False,
    "filters": {
        "query": "",
        "usage_role": "result",
        "event_type": "",
        "session_act": "",
        "layer": "",
        "key": "",
        "route_signal": "",
        "limit": 3,
        "ref_limit": 3,
    },
    "results": [
        {
            "usage_role": "result",
            "event_type": "COMMAND_OUTPUT",
            "session_act": "command_result",
            "posting_count": 8,
            "session_count": 3,
            "raw_refs": ["raw:line:1"],
            "segment_refs": ["segments/000__initial-to-latest.md#event-000001"],
            "session_ids": ["session-1"],
        }
    ],
    "result_count": 1,
    "totals": {
        "matched_group_count": 1,
        "source_direct_event_count": 20,
        "source_direct_event_term_count": 4,
    },
    "quality": {
        "uses_materialized_direct_event_rollup": True,
        "raw_or_segment_ref_present": True,
        "freshness_status": "current",
        "needs_refresh": False,
        "usage_chain_required_for_behavior_proof": True,
    },
    "cost_profile": {
        "uses_materialized_direct_event_rollup": True,
        "resamples_shards": False,
        "opens_monolith": False,
        "uses_fts": False,
        "hydrates_body": False,
        "elapsed_ms": 2,
    },
    "diagnostics": [],
}

GRAPH_TIMELINE = {
    "schema_version": 1,
    "artifact_type": "session_memory_graph_timeline",
    "ok": True,
    "mutates": False,
    "events": GRAPH_NEIGHBORHOOD["nodes"][1:],
    "evidence_refs": GRAPH_NEIGHBORHOOD["evidence_refs"],
}

GRAPH_PATH = {
    "schema_version": 1,
    "artifact_type": "session_memory_graph_shortest_path",
    "ok": True,
    "mutates": False,
    "nodes": GRAPH_NEIGHBORHOOD["nodes"],
    "edges": GRAPH_NEIGHBORHOOD["edges"],
    "evidence_refs": GRAPH_NEIGHBORHOOD["evidence_refs"],
}

GRAPH_BRIDGE = {
    "schema_version": 1,
    "artifact_type": "session_memory_graph_bridge",
    "ok": True,
    "mutates": False,
    "source_anchor": "aoa-session-memory-mcp",
    "target_anchor": "exec_command",
    "kind": "auto",
    "source_kind": "mcp",
    "target_kind": "tool",
    "normalized_entities": {
        "source": {"anchor": "aoa-session-memory-mcp", "kind": "mcp", "route_key": "aoa_session_memory_mcp"},
        "target": {"anchor": "exec_command", "kind": "tool", "route_key": "exec_command"},
    },
    "bridge": {
        "path_found": True,
        "path_length": 1,
        "max_depth": 4,
        "nodes": GRAPH_NEIGHBORHOOD["nodes"],
        "edges": GRAPH_NEIGHBORHOOD["edges"],
        "evidence_refs": GRAPH_NEIGHBORHOOD["evidence_refs"],
        "next_expansion_command": "python3 scripts/aoa_session_memory.py graph-shortest-path aoa-session-memory-mcp exec_command --kind auto --max-depth 5",
    },
    "usage_chain": {
        "source_event_count": 1,
        "target_event_count": 1,
        "source_events": GRAPH_NEIGHBORHOOD["nodes"][1:],
        "target_events": GRAPH_NEIGHBORHOOD["nodes"][1:],
    },
    "evidence_refs": GRAPH_NEIGHBORHOOD["evidence_refs"],
    "quality": {
        "one_short_route": True,
        "path_found": True,
        "path_length": 1,
        "evidence_ref_count": 1,
        "raw_or_segment_ref_present": True,
    },
    "freshness": {
        "status": "graph_store_stale",
        "warning": "graph store has stale hot-gate state; verify through raw refs",
        "dirty_sessions": [{"session_id": "session-1", "raw": "heavy"}],
        "dirty_session_ids": ["session-1"],
        "maintenance_recommendation": {
            "route": "budgeted_graph_maintenance",
            "command": "python3 scripts/aoa_session_memory.py graph-maintenance all --apply --batch-limit 25",
            "internal_plan": ["heavy"] * 20,
        },
    },
    "next_command": "python3 scripts/aoa_session_memory.py graph-bridge aoa-session-memory-mcp exec_command --kind auto --source-kind mcp --target-kind tool --limit 4 --max-depth 4",
    "next_expansion_command": "python3 scripts/aoa_session_memory.py graph-bridge aoa-session-memory-mcp exec_command --kind auto --source-kind mcp --target-kind tool --limit 8 --max-depth 5",
    "next_expansion": [{"id": "shortest_path", "command": "python3 scripts/aoa_session_memory.py graph-shortest-path aoa-session-memory-mcp exec_command --kind auto --max-depth 5"}],
}

GRAPH_COOCCURRENCE = {
    "schema_version": 1,
    "artifact_type": "session_memory_graph_cooccurrence",
    "ok": True,
    "mutates": False,
    "cooccurrences": [{"node": {"type": "tool", "label": "tool:exec_command"}, "count": 1}],
    "evidence_refs": GRAPH_NEIGHBORHOOD["evidence_refs"],
}

GRAPHRAG_PACKET = {
    "schema_version": 1,
    "artifact_type": "session_memory_graphrag_packet",
    "ok": True,
    "mutates": False,
    "query": "aoa-session-memory-mcp",
    "retrieval_modes": {"lexical": "portable_sqlite_fts", "graph": "route_signal_sidecar_or_ephemeral_graph"},
    "evidence_refs": GRAPH_NEIGHBORHOOD["evidence_refs"],
    "freshness": {"graph": {"status": "fresh"}},
}

GRAPH_EVAL = {
    "schema_version": 1,
    "artifact_type": "session_memory_graph_eval",
    "ok": True,
    "mutates": False,
    "results": [
        {
            "id": "mcp_access_plane",
            "lexical_only": {"hit_count": 1},
            "vector_only": {"status": "not_requested"},
            "graph_only": {"evidence_ref_count": 1},
            "hybrid": {"evidence_ref_count": 2, "has_raw_or_segment_refs": True},
            "graphrag": {"ok": True, "evidence_ref_count": 1},
        }
    ],
}

GRAPH_QUALITY_AUDIT = {
    "schema_version": 1,
    "artifact_type": "session_memory_graph_quality_audit",
    "ok": True,
    "mutates": False,
    "anchor_count": 3,
    "sample_count": 3,
    "ready_for_manual_verdict_count": 3,
    "needs_repair_before_verdict_count": 0,
    "retrieval_mode": "graph_neighborhood_plus_lexical_refs",
    "samples": [
        {
            "id": "mcp_access_plane",
            "anchor": "aoa-session-memory-mcp",
            "kind": "mcp",
            "review_status": "ready_for_manual_verdict",
            "quality_flags": [],
            "evidence": {
                "evidence_ref_count": 1,
                "has_raw_ref": True,
                "has_segment_ref": True,
                "has_session_ref": True,
                "sample_refs": [
                    {
                        "has_raw_ref": True,
                        "has_segment_ref": True,
                        "has_session_ref": True,
                        "raw_preview": {"status": "available", "line": 1, "text": "debug mcp"},
                    }
                ],
            },
            "freshness": {"status": "bounded_current"},
        }
    ],
}

LIVE_SCENARIO_CORPUS_CHECK = {
    "schema_version": 1,
    "artifact_type": "session_memory_live_scenario_regression_check",
    "ok": True,
    "mutates": False,
    "truth_status": "reviewed_live_scenario_route_controls_not_memory_truth",
    "corpus_path": "/srv/AbyssOS/.aoa/config/live-scenario-regression-corpus.json",
    "case_count": 1,
    "available_case_count": 3,
    "passed_count": 1,
    "skipped_count": 0,
    "failed_count": 0,
    "actionable_gap_count": 0,
    "actionable_gaps": [],
    "diagnostics": [],
}

LIVE_SCENARIO_CORPUS_INVENTORY = {
    "schema_version": 1,
    "artifact_type": "session_memory_live_scenario_regression_corpus_inventory",
    "ok": True,
    "mutates": False,
    "truth_status": "source_corpus_inventory_not_live_route_proof",
    "corpus_path": "/srv/AbyssOS/.aoa/config/live-scenario-regression-corpus.json",
    "case_count": 3,
    "profile_counts": {"literal_planner": 1, "maintenance_status": 1, "route_rollup_query": 1},
    "cases": [
        {
            "index": 1,
            "id": "literal_planner_route_contract",
            "profiles": ["literal_planner"],
            "exact_check_command": "python3 scripts/aoa_session_memory.py live-scenario-corpus check --case-limit 1 --write-report",
        }
    ],
    "diagnostics": [],
    "next_route": "Run live-scenario-corpus check for regression proof; this inventory is route coverage only.",
}

GRAPH_EXPLAIN = {
    "schema_version": 1,
    "artifact_type": "session_memory_graph_explain_packet",
    "ok": True,
    "mutates": False,
    "intent": "debug aoa-session-memory-mcp",
    "explanation": {"authority": "raw/segment/session refs remain stronger than packet summaries"},
    "evidence_refs": GRAPH_NEIGHBORHOOD["evidence_refs"],
}


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.timeouts: list[tuple[str, float]] = []

    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        command = argv[2]
        args = tuple(argv[3:])
        self.calls.append((command, args))
        self.timeouts.append((command, timeout))
        if command == "search-provider-status":
            payload = PROVIDER_STATUS
        elif command == "route-readiness":
            payload = ROUTE_READINESS_FAST_GATE
        elif command == "maintenance-status":
            payload = MAINTENANCE_STATUS
        elif command == "search-operational-route-rollup-query":
            payload = OPERATIONAL_ROUTE_ROLLUP_QUERY
        elif command == "search-operational-direct-event-rollup-query":
            payload = OPERATIONAL_DIRECT_EVENT_ROLLUP_QUERY
        elif command == "search":
            payload = SEARCH_RESULTS
        elif command == "literal-query-plan":
            query = args[args.index("--query") + 1] if "--query" in args else ""
            payload = literal_query_plan_fixture(query)
        elif command in {"agent-responses", "agent-closeouts", "agent-progress-updates"}:
            payload = AGENT_RESPONSES
        elif command in {"agent-reasoning-windows", "answer-neighborhood"}:
            payload = AGENT_WINDOWS
        elif command == "task-episodes":
            payload = TASK_EPISODES
        elif command == "goal-lifecycles":
            payload = GOAL_LIFECYCLES
        elif command == "trace-route":
            payload = TRACE_RESULTS
        elif command == "entity-registry":
            payload = ENTITY_REGISTRY
        elif command == "entity-usage-audit":
            payload = ENTITY_USAGE_AUDIT
        elif command == "usage-chain":
            payload = ENTITY_USAGE_CHAIN
        elif command == "entity-usage-neighborhood":
            payload = ENTITY_USAGE_NEIGHBORHOOD
        elif command == "entity-usage-scenario-audit":
            payload = ENTITY_USAGE_SCENARIO_AUDIT
        elif command == "live-scenario-audit":
            payload = LIVE_SCENARIO_AUDIT
        elif command == "retrieve":
            payload = RETRIEVAL_PACKET
        elif command == "rehydrate":
            payload = {"schema_version": 1, "artifact_type": "rehydrate_packet", "ok": True}
        elif command == "graph-neighborhood":
            payload = GRAPH_NEIGHBORHOOD
        elif command == "graph-timeline":
            payload = GRAPH_TIMELINE
        elif command == "graph-shortest-path":
            payload = GRAPH_PATH
        elif command == "graph-bridge":
            payload = GRAPH_BRIDGE
        elif command == "graph-cooccurrence":
            payload = GRAPH_COOCCURRENCE
        elif command == "graphrag-packet":
            payload = GRAPHRAG_PACKET
        elif command == "graph-explain-packet":
            payload = GRAPH_EXPLAIN
        elif command == "graph-eval":
            payload = GRAPH_EVAL
        elif command == "graph-quality-audit":
            payload = GRAPH_QUALITY_AUDIT
        elif command == "live-scenario-corpus":
            payload = LIVE_SCENARIO_CORPUS_INVENTORY if args[:1] == ("list",) else LIVE_SCENARIO_CORPUS_CHECK
        else:
            return CommandOutput(argv, 2, "{}", f"unexpected command {command}", 1.0)
        return CommandOutput(argv, 0, json.dumps(payload), "", 1.0)


class SessionProviderTimeoutRunner(FakeRunner):
    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        command = argv[2]
        args = tuple(argv[3:])
        if command == "search-provider-status" and "--session" in args:
            self.calls.append((command, args))
            self.timeouts.append((command, timeout))
            return CommandOutput(argv, 124, "", "command timed out after 60.0s", 60_000.0)
        return super().__call__(argv, timeout)


class SessionProviderSelectorErrorRunner(FakeRunner):
    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        command = argv[2]
        args = tuple(argv[3:])
        if command == "search-provider-status" and "--session" in args:
            self.calls.append((command, args))
            self.timeouts.append((command, timeout))
            payload = {
                "schema_version": 1,
                "artifact_type": "search_provider_status",
                "provider_schema_version": 1,
                "ok": False,
                "default_provider": "portable_sqlite",
                "selected_provider": "portable_sqlite",
                "providers": {
                    "portable_sqlite": {
                        "ok": False,
                        "status": "invalid_session",
                        "diagnostics": ["unknown session selector: bogus"],
                    }
                },
                "diagnostics": ["portable_sqlite:invalid_session"],
            }
            return CommandOutput(argv, 1, json.dumps(payload), "", 1.0)
        return super().__call__(argv, timeout)


class StaleProviderRunner(FakeRunner):
    def __init__(self, *, dirty_session_id: str, dirty_session_label: str) -> None:
        super().__init__()
        self.dirty_session_id = dirty_session_id
        self.dirty_session_label = dirty_session_label

    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        command = argv[2]
        args = tuple(argv[3:])
        if command != "search-provider-status":
            return super().__call__(argv, timeout)
        self.calls.append((command, args))
        self.timeouts.append((command, timeout))
        payload = {
            "schema_version": 1,
            "artifact_type": "search_provider_status",
            "ok": False,
            "providers": {
                "portable_sqlite": {
                    "ok": False,
                    "status": "stale",
                    "freshness": {
                        "status": "stale",
                        "dirty_session_count": 1,
                        "dirty_session_ids": [self.dirty_session_id],
                        "dirty_sessions": [
                            {
                                "session_id": self.dirty_session_id,
                                "session_label": self.dirty_session_label,
                                "session_dir": f"/tmp/.aoa/sessions/{self.dirty_session_label}",
                            }
                        ],
                    },
                }
            },
            "diagnostics": ["portable_sqlite:stale"],
        }
        return CommandOutput(argv, 1, json.dumps(payload), "", 1.0)


class LiveDeferredProviderRunner(FakeRunner):
    def __init__(self, *, dirty_session_id: str, dirty_session_label: str) -> None:
        super().__init__()
        self.dirty_session_id = dirty_session_id
        self.dirty_session_label = dirty_session_label

    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        command = argv[2]
        args = tuple(argv[3:])
        if command != "search-provider-status":
            return super().__call__(argv, timeout)
        self.calls.append((command, args))
        self.timeouts.append((command, timeout))
        payload = {
            "schema_version": 1,
            "artifact_type": "search_provider_status",
            "ok": True,
            "providers": {
                "portable_sqlite": {
                    "ok": True,
                    "status": "ready_with_deferred_live_updates",
                    "freshness": {
                        "status": "current_with_deferred_live_updates",
                        "dirty_session_count": 1,
                        "actionable_dirty_session_count": 0,
                        "deferred_live_session_count": 1,
                        "dirty_session_ids": [self.dirty_session_id],
                        "actionable_dirty_session_ids": [],
                        "dirty_sessions": [
                            {
                                "session_id": self.dirty_session_id,
                                "session_label": self.dirty_session_label,
                                "session_dir": f"/tmp/.aoa/sessions/{self.dirty_session_label}",
                            }
                        ],
                        "actionable_dirty_sessions": [],
                        "deferred_live_sessions": [
                            {
                                "session_id": self.dirty_session_id,
                                "session_label": self.dirty_session_label,
                                "session_dir": f"/tmp/.aoa/sessions/{self.dirty_session_label}",
                                "live_transcript_path": "/tmp/.codex/sessions/2026/06/15/rollout-live.jsonl",
                            }
                        ],
                        "reasons": ["recent_live_projection_updates_deferred"],
                    },
                }
            },
            "diagnostics": [],
        }
        return CommandOutput(argv, 0, json.dumps(payload), "", 1.0)


def state_with_fixture(tmp_path: Path, runner: FakeRunner | None = None) -> AoASessionMemoryMCPState:
    aoa = seed_archive(tmp_path)
    return AoASessionMemoryMCPState.discover(
        workspace_root=tmp_path,
        aoa_root=aoa,
        script_path=aoa / "scripts/aoa_session_memory.py",
        command_runner=runner or FakeRunner(),
        timeout_seconds=2,
    )


def test_latest_session_resolution_uses_registry_updated_at(tmp_path: Path) -> None:
    aoa = seed_archive(tmp_path)
    registry_path = aoa / "session-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["sessions"][0]["updated_at"] = "2026-06-14T00:00:00Z"
    calendar_newer = aoa / "sessions/2026-06-13__005__calendar-newer-but-stale"
    calendar_newer.mkdir(parents=True)
    write_json(
        calendar_newer / "session.manifest.json",
        {
            "session_id": "session-stale",
            "session_label": calendar_newer.name,
            "session_title": "Calendar newer but stale",
            "archive_status": "indexed",
        },
    )
    registry["sessions"].append(
        {
            "session_id": "session-stale",
            "updated_at": "2026-06-13T00:00:00Z",
            "display": {
                "date": "2026-06-13",
                "sequence": 5,
                "label": calendar_newer.name,
                "title": "Calendar newer but stale",
                "path": calendar_newer.as_posix(),
            },
        }
    )
    write_json(registry_path, registry)
    state = AoASessionMemoryMCPState.discover(
        workspace_root=tmp_path,
        aoa_root=aoa,
        script_path=aoa / "scripts/aoa_session_memory.py",
        command_runner=FakeRunner(),
        timeout_seconds=2,
    )

    brief = state.session_brief("latest", max_segments=1)

    assert brief["ok"] is True
    assert brief["session"]["session_id"] == "session-1"


def test_latest_session_resolution_prefers_registry_recency_over_stale_raw_mtime(tmp_path: Path) -> None:
    aoa = seed_archive(tmp_path)
    registry_path = aoa / "session-registry.json"
    active_dir = aoa / "sessions/2026-06-04__003__active-long-session"
    raw_unavailable_dir = aoa / "sessions/2026-06-25__001__raw-unavailable-latest"
    transcript = tmp_path / "rollout-2026-06-04T10-48-00-active.jsonl"
    raw_path = active_dir / "raw/session.raw.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text('{"type":"session_meta"}\n', encoding="utf-8")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text('{"type":"session_meta"}\n', encoding="utf-8")
    os.utime(transcript, (200.0, 200.0))
    os.utime(raw_path, (150.0, 150.0))
    active_dir.mkdir(parents=True, exist_ok=True)
    raw_unavailable_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        active_dir / "session.manifest.json",
        {
            "session_id": "active-long-session",
            "session_label": active_dir.name,
            "session_title": "Active long session",
            "archive_status": "indexed",
            "raw": {
                "path": raw_path.as_posix(),
                "source_path": transcript.as_posix(),
            },
        },
    )
    write_json(
        raw_unavailable_dir / "session.manifest.json",
        {
            "session_id": "raw-unavailable-latest",
            "session_label": raw_unavailable_dir.name,
            "session_title": "Raw unavailable latest",
            "archive_status": "raw_unavailable",
            "raw": {"path": None, "source_path": None},
        },
    )
    write_json(
        registry_path,
        {
            "sessions": [
                {
                    "session_id": "active-long-session",
                    "display": {
                        "date": "2026-06-04",
                        "sequence": 3,
                        "label": active_dir.name,
                        "title": "Active long session",
                        "path": active_dir.as_posix(),
                    },
                    "raw": {
                        "path": raw_path.as_posix(),
                        "source_path": transcript.as_posix(),
                    },
                },
                {
                    "session_id": "raw-unavailable-latest",
                    "display": {
                        "date": "2026-06-25",
                        "sequence": 1,
                        "label": raw_unavailable_dir.name,
                        "title": "Raw unavailable latest",
                        "path": raw_unavailable_dir.as_posix(),
                    },
                    "raw": {"path": None, "source_path": None},
                },
            ]
        },
    )
    state = AoASessionMemoryMCPState.discover(
        workspace_root=tmp_path,
        aoa_root=aoa,
        script_path=aoa / "scripts/aoa_session_memory.py",
        command_runner=FakeRunner(),
        timeout_seconds=2,
    )

    brief = state.session_brief("latest", max_segments=1)

    assert brief["ok"] is True
    assert brief["session"]["session_id"] == "raw-unavailable-latest"


def test_latest_session_resolution_falls_back_to_registry_date_sequence(tmp_path: Path) -> None:
    aoa = seed_archive(tmp_path)
    registry_path = aoa / "session-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    base_manifest_path = aoa / "sessions/2026-05-26__001__session-memory-mcp/session.manifest.json"
    base_manifest = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    base_manifest["raw"] = {"path": None, "source_path": None}
    write_json(base_manifest_path, base_manifest)
    fallback_latest = aoa / "sessions/2026-06-13__005__fallback-latest"
    fallback_latest.mkdir(parents=True)
    write_json(
        fallback_latest / "session.manifest.json",
        {
            "session_id": "session-fallback-latest",
            "session_label": fallback_latest.name,
            "session_title": "Fallback latest",
            "archive_status": "indexed",
        },
    )
    registry["sessions"].append(
        {
            "session_id": "session-fallback-latest",
            "display": {
                "date": "2026-06-13",
                "sequence": 5,
                "label": fallback_latest.name,
                "title": "Fallback latest",
                "path": fallback_latest.as_posix(),
            },
        }
    )
    write_json(registry_path, registry)
    state = AoASessionMemoryMCPState.discover(
        workspace_root=tmp_path,
        aoa_root=aoa,
        script_path=aoa / "scripts/aoa_session_memory.py",
        command_runner=FakeRunner(),
        timeout_seconds=2,
    )

    brief = state.session_brief("latest", max_segments=1)

    assert brief["ok"] is True
    assert brief["session"]["session_id"] == "session-fallback-latest"


def test_status_reads_provider_atlas_and_latest_diagnostics(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)
    status = state.session_memory_status()

    assert status["schema"] == "aoa_session_memory_status_v1"
    assert status["provider"]["ok"] is True
    assert status["provider"]["status_mode"] == "fast_presence_probe"
    assert status["provider"]["providers"]["portable_sqlite"]["freshness"]["checked"] is False
    assert status["atlas"]["entry_count"] == 2
    assert status["runtime"]["source_matches_loaded"] is True
    assert status["runtime"]["reload_required"] is False
    assert status["maintenance_status"]["source"] == "maintenance-status"
    assert status["maintenance_status"]["agent_route"]["action"] == "use_graph_search_for_stable_archive_wait_for_recent_live"
    assert status["maintenance_status"]["search_shards"]["status"] == "current"
    latest_materialization = status["maintenance_status"]["search_shards"]["latest_materialization"]
    assert latest_materialization["target"] == "2026-06-01__001__что-сейчас-грузит-процессор"
    assert latest_materialization["slow_sessions"][0]["session_label"] == "2026-06-01__001__что-сейчас-грузит-процессор"
    assert latest_materialization["slow_sessions"][0]["raw_text_status"] == "skipped_structured_projection"
    assert (
        status["maintenance_status"]["search_shards"]["fast_path_defaults"]["agent_event_routes"][
            "raw_text_fallback_dependency_status"
        ]
        == "monolith_required_for_raw_text_query"
    )
    raw_text_dependency = status["maintenance_status"]["search_shards"]["raw_text_fallback_dependency"]
    assert raw_text_dependency["status"] == "monolith_required_for_raw_text_query"
    assert raw_text_dependency["route_blocked_shards"] == ["month/2026-04", "month/2026-05", "month/2026-06"]
    assert raw_text_dependency["scoped_full_text_next_commands"][0]["shard"] == "month/2026-04"
    assert "--full-text" in raw_text_dependency["scoped_full_text_next_commands"][0]["command"]
    assert raw_text_dependency["authority_boundary"].startswith("monolith and shards are generated search projections")
    assert status["latest_route_readiness"]["reports"][0]["summary"]["ok"] is True
    assert status["readiness_policy"]["provider_status"]["freshness_checked"] is False
    assert status["readiness_policy"]["cached_route_readiness"]["status_field"] == "latest_route_readiness"
    assert status["authority_boundary"]["mutation_posture"].startswith("no write")
    assert not any(call[0] == "search-provider-status" for call in runner.calls)
    assert any(call[0] == "maintenance-status" for call in runner.calls)

    provider_resource = state.read_resource("aoa-session-memory://provider/status")
    assert provider_resource["status_mode"] == "fast_presence_probe"
    assert not any(call[0] == "search-provider-status" for call in runner.calls)


def test_runtime_identity_reports_reload_boundary(tmp_path: Path, monkeypatch: Any) -> None:
    module = sys.modules[AoASessionMemoryMCPState.__module__]
    state = state_with_fixture(tmp_path, FakeRunner())

    fresh = state.runtime_identity()
    assert fresh["source_matches_loaded"] is True
    assert fresh["reload_required"] is False
    assert fresh["implementation_reload_required"] is False
    assert fresh["tool_schema_reload_required"] is False
    assert fresh["loaded_core_path"].endswith("aoa_session_memory_mcp/core.py")
    assert fresh["loaded_server_path"].endswith("aoa_session_memory_mcp/server.py")

    monkeypatch.setattr(module, "MCP_CORE_LOADED_SHA256", "stale-loaded-code")
    stale = state.runtime_identity()

    assert stale["source_matches_loaded"] is False
    assert stale["reload_required"] is True
    assert stale["implementation_reload_required"] is True
    assert stale["tool_schema_reload_required"] is False
    assert "existing tools" in stale["reload_boundary"]
    assert "tool list" in stale["reload_boundary"]

    monkeypatch.setattr(module, "MCP_CORE_LOADED_SHA256", stale["current_core_sha256"])
    monkeypatch.setattr(module, "MCP_SERVER_LOADED_SHA256", "stale-loaded-server")
    stale_schema = state.runtime_identity()

    assert stale_schema["source_matches_loaded"] is False
    assert stale_schema["reload_required"] is True
    assert stale_schema["implementation_reload_required"] is False
    assert stale_schema["tool_schema_reload_required"] is True

    server_source = tmp_path / "server.py"
    server_source.write_text("# fresh server source\n", encoding="utf-8")
    server_hash = module._file_sha256(server_source)
    os.utime(server_source, (2_000_000_000, 2_000_000_000))
    monkeypatch.setattr(module, "MCP_SERVER_SOURCE_PATH", server_source)
    monkeypatch.setattr(module, "MCP_SERVER_LOADED_SHA256", server_hash)
    monkeypatch.setattr(module, "_process_start_epoch", lambda pid: 1_000_000_000.0)
    stale_process = state.runtime_identity()

    assert stale_process["server_source_matches_loaded"] is True
    assert stale_process["process_started_before_server_source"] is True
    assert stale_process["tool_schema_reload_required"] is True
    assert stale_process["reload_required"] is True


def test_status_live_readiness_uses_fast_gate_without_evidence_samples(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    status = state.session_memory_status(include_live=True)

    route_calls = [call for call in runner.calls if call[0] == "route-readiness"]
    assert len(route_calls) == 1
    assert not any(call[0] == "search-provider-status" for call in runner.calls)
    args = route_calls[0][1]
    assert "--limit" not in args
    assert args[args.index("--sample-limit") + 1] == "0"
    assert status["live_route_readiness"]["ok"] is True
    assert status["readiness_policy"]["live_route_readiness"]["limit"] is None
    assert status["readiness_policy"]["live_route_readiness"]["sample_policy"] == "no evidence sample extraction in MCP status"
    audit_command = status["readiness_policy"]["audit_route"]["command"]
    assert "--write-report" in audit_command
    assert tmp_path.as_posix() in audit_command
    assert (tmp_path / ".aoa").as_posix() in audit_command
    assert (tmp_path / ".aoa/scripts/aoa_session_memory.py").as_posix() in audit_command
    assert "/srv/AbyssOS/.aoa" not in audit_command


def test_status_distinguishes_sqlite_graph_store_from_missing_sidecar(tmp_path: Path) -> None:
    aoa = seed_archive(tmp_path)
    sqlite_path = aoa / "graph/graph.sqlite3"
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite_path.write_bytes(b"SQLite live store placeholder")
    write_json(
        aoa / "diagnostics/20260526T000001Z__graph-freshness-gates.json",
        {
            "schema_version": 1,
            "artifact_type": "session_memory_graph_freshness_gates",
            "generated_at": "2026-05-26T00:00:01Z",
            "ok": False,
            "needs_index_maintenance": False,
            "needs_graph_maintenance": True,
            "search_index": {"status": "current"},
            "atlas_index": {"status": "current"},
            "graph_store": {
                "status": "dirty",
                "source_state": {
                    "dirty_count": 7,
                    "missing_count": 2,
                    "blocked_count": 1,
                },
            },
            "diagnostics": [],
        },
    )

    state = AoASessionMemoryMCPState.discover(
        workspace_root=tmp_path,
        aoa_root=aoa,
        script_path=aoa / "scripts/aoa_session_memory.py",
        command_runner=FakeRunner(),
        timeout_seconds=2,
    )
    status = state.session_memory_status()
    plan = state.maintenance_plan()
    graph_resource = state.read_resource("aoa-session-memory://graph/status")

    assert status["graph"]["status"] == "sqlite_live_store_present"
    assert status["graph"]["sidecar_status"] == "not_exported"
    assert status["graph"]["decision_source"] == "maintenance_status"
    assert status["graph"]["maintenance_status"] == "current"
    assert status["graph"]["needs_graph_maintenance"] is False
    assert status["graph"]["needs_index_maintenance"] is False
    assert status["graph"]["cached_freshness_conflicts_with_maintenance"] is True
    assert status["graph"]["freshness"]["graph_status"] == "dirty"
    assert status["graph"]["freshness"]["dirty_count"] == 7
    assert status["graph"]["freshness"]["missing_count"] == 2
    assert "graph_sidecar_not_exported" in status["graph"]["diagnostics"]
    assert graph_resource["decision_source"] == "maintenance_status"
    assert graph_resource["needs_graph_maintenance"] is False
    assert graph_resource["needs_index_maintenance"] is False
    assert plan["artifact_type"] == "session_memory_maintenance_status"
    assert plan["compatibility_tool"] == "aoa_session_maintenance_plan"
    assert plan["preferred_tool"] == "aoa_session_maintenance_status"
    assert plan["agent_route"]["action"] == "use_graph_search_for_stable_archive_wait_for_recent_live"
    assert plan["mcp_access"]["archive_command"] == "maintenance-status"
    assert plan["operations"]["warning_count"] == 2
    assert plan["operations"]["latest_search_index"]["document_count"] == 1630447
    assert plan["operations"]["search_shards"]["raw_text_fallback_dependency"]["route_blocked_shard_count"] == 3
    assert plan["operations"]["why_maintenance_long"][0]["phase"] == "session_bulk_index"
    assert "--no-timers" in [arg for command, args in state.command_runner.calls if command == "maintenance-status" for arg in args]


def test_graph_summary_uses_non_ok_maintenance_packet_for_decisions(tmp_path: Path) -> None:
    aoa = seed_archive(tmp_path)
    sqlite_path = aoa / "graph/graph.sqlite3"
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite_path.write_bytes(b"SQLite live store placeholder")
    write_json(
        aoa / "diagnostics/20260526T000001Z__graph-freshness-gates.json",
        {
            "artifact_type": "session_memory_graph_freshness_gates",
            "ok": True,
            "needs_index_maintenance": False,
            "needs_graph_maintenance": False,
            "graph_store": {"status": "current"},
        },
    )

    class NonOkMaintenanceRunner(FakeRunner):
        def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
            if argv[2] != "maintenance-status":
                return super().__call__(argv, timeout)
            self.calls.append((argv[2], tuple(argv[3:])))
            self.timeouts.append((argv[2], timeout))
            payload = {
                **MAINTENANCE_STATUS,
                "ok": False,
                "graph": {"status": "dirty", "dirty_count": 3, "missing_count": 1, "blocked_count": 0},
                "route": {"status": "dirty", "needs_index_maintenance": True, "needs_graph_maintenance": True},
            }
            return CommandOutput(argv, 0, json.dumps(payload, ensure_ascii=False), "", 1.0)

    state = AoASessionMemoryMCPState.discover(
        workspace_root=tmp_path,
        aoa_root=aoa,
        script_path=aoa / "scripts/aoa_session_memory.py",
        command_runner=NonOkMaintenanceRunner(),
        timeout_seconds=2,
    )

    status = state.session_memory_status()

    assert status["graph"]["decision_source"] == "maintenance_status"
    assert status["graph"]["maintenance_status"] == "dirty"
    assert status["graph"]["needs_graph_maintenance"] is True
    assert status["graph"]["needs_index_maintenance"] is True


def test_projection_status_reads_latest_completeness_without_running_catchup(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    status = state.session_projection_status()

    assert status["schema"] == "aoa_session_memory_projection_status_v1"
    assert status["ok"] is True
    assert status["mutates"] is False
    assert status["source"] == "latest_projection_catchup_diagnostic"
    assert status["projection_completeness"]["status"] == "current"
    assert status["projection_completeness"]["surfaces"]["entity_registry"]["entity_count"] == 12
    assert status["next_operator_route"]["id"] == "verify_projection_status"
    assert status["mcp_access"]["archive_command"] is None
    assert status["mcp_access"]["does_not_run_projection_catchup"] is True
    assert any(call[0] == "maintenance-status" for call in runner.calls)
    assert not any(call[0] == "projection-catchup" for call in runner.calls)

    resource = state.read_resource("aoa-session-memory://projection/status")
    assert resource["projection_completeness"]["surfaces"]["search_index"]["status"] == "current"


def test_projection_status_treats_stale_completeness_as_not_ok(tmp_path: Path) -> None:
    aoa = seed_archive(tmp_path)
    write_json(
        aoa / "diagnostics/20260526T000200Z__projection-catchup-catchup.json",
        {
            "schema_version": 1,
            "artifact_type": "session_memory_projection_catchup",
            "ok": True,
            "projection_completeness": {
                "schema_version": 1,
                "artifact_type": "session_memory_projection_completeness",
                "status": "stale",
                "actionable_surface_ids": ["search_index"],
                "deferred_surface_ids": [],
                "surfaces": {
                    "search_index": {"status": "stale", "needs_maintenance": True},
                    "entity_registry": {"status": "current", "needs_maintenance": False},
                },
            },
        },
    )
    runner = FakeRunner()
    state = AoASessionMemoryMCPState.discover(
        workspace_root=tmp_path,
        aoa_root=aoa,
        script_path=aoa / "scripts/aoa_session_memory.py",
        command_runner=runner,
        timeout_seconds=2,
    )

    status = state.session_projection_status()

    assert status["ok"] is False
    assert status["source"] == "stale_projection_catchup_diagnostic"
    assert status["next_operator_route"]["id"] == "run_projection_catchup_outside_mcp"
    assert status["next_operator_route"]["reason"] == "projection_completeness_stale"
    assert "projection_completeness_stale" in status["diagnostics"]
    assert not any(call[0] == "projection-catchup" for call in runner.calls)


def test_projection_status_flags_legacy_completeness_diagnostic(tmp_path: Path) -> None:
    aoa = seed_archive(tmp_path)
    write_json(
        aoa / "diagnostics/20260526T000200Z__projection-catchup-catchup.json",
        {
            "artifact_type": "session_memory_projection_catchup",
            "ok": True,
            "completeness_check": {
                "freshness_before_after": True,
                "schema_classifier_dirty_detection": "legacy string-only status",
            },
        },
    )
    runner = FakeRunner()
    state = AoASessionMemoryMCPState.discover(
        workspace_root=tmp_path,
        aoa_root=aoa,
        script_path=aoa / "scripts/aoa_session_memory.py",
        command_runner=runner,
        timeout_seconds=2,
    )

    status = state.session_projection_status()

    assert status["ok"] is False
    assert status["source"] == "legacy_projection_catchup_diagnostic"
    assert status["next_operator_route"]["id"] == "run_projection_catchup_outside_mcp"
    assert "projection_completeness_missing_or_legacy" in status["diagnostics"]
    assert not any(call[0] == "projection-catchup" for call in runner.calls)


def test_maintenance_status_delegates_to_archive_status_route(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    payload = state.session_maintenance_status(deep=True, include_timers=False, full=True)

    maintenance_calls = [args for command, args in runner.calls if command == "maintenance-status"]
    assert len(maintenance_calls) == 1
    args = maintenance_calls[0]
    assert args[:3] == ("--deep", "--no-timers", "--full")
    assert args[args.index("--workspace-root") + 1] == tmp_path.as_posix()
    assert args[args.index("--aoa-root") + 1] == (tmp_path / ".aoa").as_posix()
    assert [timeout for command, timeout in runner.timeouts if command == "maintenance-status"] == [60.0]
    assert payload["artifact_type"] == "session_memory_maintenance_status"
    assert payload["mutates"] is False
    assert payload["runtime"]["source_matches_loaded"] is True
    assert payload["runtime"]["reload_required"] is False
    assert payload["mcp_access"]["mutates"] is False
    assert payload["mcp_access"]["runtime_reload_required"] is False
    assert payload["mcp_access"]["response_compacted"] is False
    assert payload["operations"]["mutates"] is False
    assert payload["operations"]["warnings"][0]["code"] == "search_db_large"
    assert payload["operations"]["latest_search_index"]["elapsed_ms"] == 3042335
    assert "maintenance-status --deep --no-timers --full" in payload["mcp_access"]["full_status_route"]
    assert tmp_path.as_posix() in payload["mcp_access"]["full_status_route"]

    resource = state.read_resource("aoa-session-memory://maintenance/status")
    assert resource["artifact_type"] == "session_memory_maintenance_status"
    assert resource["operations"]["recent_problem_job_count"] == 0
    assert any(item["reason"] == "sqlite_index_build" for item in resource["operations"]["why_maintenance_long"])

    surfaces = state.available_surfaces()
    assert "aoa_session_live_scenario_corpus_inventory" in surfaces["tools"]
    assert "aoa-session-memory://maintenance/status" in surfaces["resources"]


def test_operational_route_rollup_query_delegates_to_read_only_archive_route(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    payload = state.session_operational_route_rollup_query(
        "exec_command",
        limit=3,
        ref_limit=2,
    )

    calls = {command: args for command, args in runner.calls}
    args = calls["search-operational-route-rollup-query"]
    assert args[0] == "exec_command"
    assert args[args.index("--layer") + 1] == "tool"
    assert args[args.index("--limit") + 1] == "3"
    assert args[args.index("--ref-limit") + 1] == "2"
    assert "--apply" not in args
    assert "--max-shards" not in args
    assert [timeout for command, timeout in runner.timeouts if command == "search-operational-route-rollup-query"] == [30.0]
    assert payload["artifact_type"] == "session_memory_search_operational_route_rollup_query"
    assert payload["mutates"] is False
    assert payload["quality"]["raw_or_segment_ref_present"] is True
    assert payload["cost_profile"]["resamples_shards"] is False
    assert payload["mcp_access"]["mutates"] is False
    assert payload["mcp_access"]["does_not_materialize_rollup"] is True
    assert payload["mcp_access"]["does_not_resample_shards"] is True


def test_operational_route_rollup_query_allows_explicit_all_layer_query(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    state.session_operational_route_rollup_query("exec_command", layer="")

    calls = {command: args for command, args in runner.calls}
    args = calls["search-operational-route-rollup-query"]
    assert "--layer" not in args


def test_operational_direct_event_rollup_query_delegates_to_read_only_archive_route(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    payload = state.session_operational_direct_event_rollup_query(
        usage_role="result",
        event_type="COMMAND_OUTPUT",
        session_act="command_result",
        limit=3,
        ref_limit=2,
    )

    calls = {command: args for command, args in runner.calls}
    args = calls["search-operational-direct-event-rollup-query"]
    assert args[args.index("--usage-role") + 1] == "result"
    assert args[args.index("--event-type") + 1] == "COMMAND_OUTPUT"
    assert args[args.index("--session-act") + 1] == "command_result"
    assert args[args.index("--limit") + 1] == "3"
    assert args[args.index("--ref-limit") + 1] == "2"
    assert "--apply" not in args
    assert "--max-shards" not in args
    assert [timeout for command, timeout in runner.timeouts if command == "search-operational-direct-event-rollup-query"] == [30.0]
    assert payload["artifact_type"] == "session_memory_search_operational_direct_event_rollup_query"
    assert payload["mutates"] is False
    assert payload["quality"]["raw_or_segment_ref_present"] is True
    assert payload["cost_profile"]["uses_materialized_direct_event_rollup"] is True
    assert payload["cost_profile"]["resamples_shards"] is False
    assert payload["mcp_access"]["mutates"] is False
    assert payload["mcp_access"]["does_not_materialize_rollup"] is True
    assert payload["mcp_access"]["does_not_resample_shards"] is True
    assert payload["mcp_access"]["behavior_proof_route"] == "usage-chain"


def test_trace_and_search_use_allowlisted_archive_commands(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    trace = state.session_trace("aoa-session-memory-mcp", kind="auto", limit=5)
    search = state.session_search("aoa-session-memory", filters={"route_layer": "mcp"}, limit=5)

    assert trace["route_candidates"][0]["route_signal"] == "mcp:aoa_session_memory_mcp"
    assert search["results"][0]["freshness"]["status"] == "fresh"
    assert any(call[0] == "trace-route" for call in runner.calls)
    assert any(call[0] == "search" and "--route-layer" in call[1] for call in runner.calls)


def test_trace_kind_aliases_bridge_entity_registry_and_usage_routes(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    trace = state.session_trace("aoa-session-memory-mcp", kind="mcp_service", limit=5)
    audit = state.session_entity_usage_audit("aoa-session-memory-mcp", kind="mcp_service", limit=5)
    neighborhood = state.session_entity_usage_neighborhood(
        "aoa-session-memory-mcp",
        kind="mcp_service",
        limit=1,
        per_route_limit=1,
        raw_preview_chars=0,
        document_limit=3,
    )
    timeline = state.graph_timeline("aoa_session_memory_search", kind="mcp_tool", limit=5)
    quality = state.graph_quality_audit(
        anchors=[{"id": "session_memory_mcp", "kind": "mcp_service", "anchor": "aoa-session-memory-mcp"}],
        limit=1,
    )

    assert trace["kind"] == "mcp"
    assert trace["requested_kind"] == "mcp_service"
    assert audit["kind"] == "mcp"
    assert audit["requested_kind"] == "mcp_service"
    assert neighborhood["kind"] == "mcp"
    assert neighborhood["requested_kind"] == "mcp_service"
    assert neighborhood["mcp_access"]["selected_route_signal"] == "mcp:aoa_session_memory_mcp"
    assert timeline["kind"] == "tool"
    assert timeline["requested_kind"] == "mcp_tool"
    assert quality["artifact_type"] == "session_memory_graph_quality_audit"

    calls = runner.calls
    trace_args = next(args for command, args in calls if command == "trace-route")
    audit_args = next(args for command, args in calls if command == "entity-usage-audit")
    timeline_args = next(args for command, args in calls if command == "graph-timeline")
    quality_args = next(args for command, args in calls if command == "graph-quality-audit")
    assert trace_args[trace_args.index("--kind") + 1] == "mcp"
    assert audit_args[audit_args.index("--kind") + 1] == "mcp"
    assert timeline_args[timeline_args.index("--kind") + 1] == "tool"
    assert "session_memory_mcp:mcp:aoa-session-memory-mcp" in quality_args


def test_route_only_search_uses_filters_without_text_query(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search("", filters={"route_signal": "tool:exec_command", "doc_type": "event"}, limit=5)

    assert search["results"][0]["freshness"]["status"] == "fresh"
    search_calls = [call for call in runner.calls if call[0] == "search"]
    assert len(search_calls) == 1
    args = search_calls[0][1]
    assert args[args.index("--query") + 1] == ""
    assert args[args.index("--route-signal") + 1] == "tool:exec_command"
    assert args[args.index("--doc-type") + 1] == "event"
    assert "--use-shards" not in args
    assert "--max-shards" not in args


def test_hook_route_search_with_dates_exposes_receipt_timestamp_route(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search(
        "",
        filters={
            "route_signal": "hook:UserPromptSubmit",
            "doc_type": "event",
            "date_from": "2026-05-26",
        },
        limit=5,
    )

    assert search["date_semantics"]["filter_basis"] == "indexed_search_document_or_session_date"
    assert search["date_semantics"]["does_not_filter"] == ["hook_receipt_timestamp"]
    hook_route = search["date_semantics"]["hook_receipts_route"]
    assert hook_route["mcp_tool"] == "aoa_session_hook_receipts"
    assert hook_route["date_filter_basis"] == "hook_receipt_timestamp"
    assert hook_route["args"] == {
        "event_name": "UserPromptSubmit",
        "only_errors": False,
        "date_from": "2026-05-26",
    }
    assert search["mcp_route_plan"]["route_kind"] == "structured_filter_search"
    assert search["mcp_route_plan"]["uses_text_query"] is False
    assert search["mcp_route_plan"]["typed_route_signal"] is True
    assert search["mcp_route_plan"]["structured_filters"] == ["date_from", "doc_type", "route_signal"]
    assert search["mcp_payload_policy"]["mcp_route_plan_exposed"] is True
    assert search["mcp_payload_policy"]["date_semantics_exposed"] is True
    search_calls = [call for call in runner.calls if call[0] == "search"]
    assert len(search_calls) == 1
    args = search_calls[0][1]
    assert args[args.index("--route-signal") + 1] == "hook:UserPromptSubmit"
    assert args[args.index("--date-from") + 1] == "2026-05-26"


def test_search_compacts_heavy_provider_status_for_mcp(tmp_path: Path) -> None:
    class HeavySearchRunner(FakeRunner):
        def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
            command = argv[2]
            if command != "search":
                return super().__call__(argv, timeout)
            self.calls.append((command, tuple(argv[3:])))
            self.timeouts.append((command, timeout))
            payload = {
                **SEARCH_RESULTS,
                "provider": {
                    "selected": "portable_sqlite",
                    "authoritative_result_provider": "portable_sqlite",
                    "status": {
                        "schema_version": 1,
                        "artifact_type": "search_provider_status",
                        "ok": True,
                        "providers": {
                            "portable_sqlite": {
                                "provider": "portable_sqlite",
                                "ok": True,
                                "status": "ready_with_deferred_live_updates",
                                "freshness": {
                                    "status": "current_with_deferred_live_updates",
                                    "dirty_session_count": 2,
                                    "actionable_dirty_session_count": 0,
                                    "deferred_live_session_count": 2,
                                    "dirty_sessions": [
                                        {
                                            "session_id": f"session-{idx}",
                                            "session_label": f"2026-06-{idx:02d}__heavy",
                                            "live_transcript_path": f"/tmp/live-{idx}.jsonl",
                                            "source_fingerprint": "x" * 128,
                                        }
                                        for idx in range(20)
                                    ],
                                },
                                "metadata": {"large": "provider metadata " * 100},
                            }
                        },
                    },
                    "authority_law": ".aoa owns evidence " * 100,
                },
            }
            payload["results"] = [{**SEARCH_RESULTS["results"][0], "body": "raw body " * 200}]
            return CommandOutput(argv, 0, json.dumps(payload), "", 1.0)

    state = state_with_fixture(tmp_path, HeavySearchRunner())

    search = state.session_search("", filters={"route_signal": "tool:exec_command", "doc_type": "event"}, limit=5)
    encoded = json.dumps(search)

    assert search["mcp_payload_policy"]["response_compacted"] is True
    assert search["mcp_access"]["response_compacted"] is True
    assert search["provider"]["status"]["providers"]["portable_sqlite"]["freshness"]["dirty_session_count"] == 2
    assert search["results"][0]["refs"]["raw"] == "raw:line:1"
    assert "body" not in search["results"][0]
    assert "dirty_sessions" not in encoded
    assert "live_transcript_path" not in encoded
    assert "source_fingerprint" not in encoded
    assert "provider metadata " not in encoded
    assert "full_search_route" in search["mcp_access"]
    assert len(encoded) < 5500


def test_search_normalizes_layer_alias_and_explicit_shard_controls(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search(
        "",
        filters={
            "layer": "mcp",
            "route_signal": "mcp:aoa_session_memory_mcp",
            "doc_type": "event",
            "use_shards": True,
            "max_shards": 3,
        },
        limit=5,
    )

    assert search["results"][0]["freshness"]["status"] == "fresh"
    assert not [item for item in search.get("diagnostics", []) if "unsupported filter" in item]
    search_calls = [call for call in runner.calls if call[0] == "search"]
    assert len(search_calls) == 1
    args = search_calls[0][1]
    assert args[args.index("--query") + 1] == ""
    assert args[args.index("--route-layer") + 1] == "mcp"
    assert args[args.index("--route-signal") + 1] == "mcp:aoa_session_memory_mcp"
    assert args[args.index("--doc-type") + 1] == "event"
    assert args[args.index("--max-shards") + 1] == "3"
    assert "--use-shards" in args


def test_literal_query_plan_routes_to_allowlisted_archive_command(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    plan = state.session_literal_query_plan(
        "aoa-session-memory-mcp",
        kind="mcp_service",
        filters={"doc_type": "event", "layer": "mcp", "max_shards": 3},
    )

    assert plan["artifact_type"] == "session_memory_literal_query_plan"
    assert plan["kind"] == "mcp"
    assert plan["requested_kind"] == "mcp_service"
    assert plan["primary_route"]["route_id"] == "entity_usage_chain"
    assert plan["cost_profile"]["structured_first"] is True
    plan_calls = [call for call in runner.calls if call[0] == "literal-query-plan"]
    assert len(plan_calls) == 1
    args = plan_calls[0][1]
    assert args[args.index("--query") + 1] == "aoa-session-memory-mcp"
    assert args[args.index("--kind") + 1] == "mcp"
    assert args[args.index("--doc-type") + 1] == "event"
    assert args[args.index("--route-layer") + 1] == "mcp"
    assert args[args.index("--max-shards") + 1] == "3"
    assert not any(call[0] == "search" for call in runner.calls)


def test_retrieve_unsupported_recipe_returns_structured_diagnostic(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    payload = state.session_retrieve(recipe="review", query="audit decision skill", limit=5, event_limit=8)

    assert payload["ok"] is False
    assert payload["artifact_type"] == "retrieval_packet"
    assert payload["recipe"] == "review"
    assert payload["mcp_access"]["archive_command"] == "retrieve"
    assert payload["mcp_access"]["archive_dispatched"] is False
    assert payload["mcp_access"]["returncode"] is None
    assert payload["authority_boundary"]["mutation_posture"].startswith("no write")
    assert "continue-session" in payload["mcp_known_recipes"]
    assert not any(call[0] == "retrieve" for call in runner.calls)


def test_retrieve_entity_usage_redirects_to_usage_chain(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    payload = state.session_retrieve(
        recipe="entity_usage",
        query="aoa-session-memory-mcp",
        session="session-1",
        limit=5,
        event_limit=4,
    )

    assert payload["ok"] is True
    assert payload["artifact_type"] == "session_memory_entity_usage_chain"
    assert payload["recipe"] == "entity_usage"
    assert payload["retrieval_redirect"]["served_by"] == "aoa_session_entity_usage_chain"
    assert "served by entity-usage-chain retrieval redirect" in payload["diagnostics"]
    assert not any(call[0] == "retrieve" for call in runner.calls)
    usage_calls = [call for call in runner.calls if call[0] == "usage-chain"]
    assert len(usage_calls) == 1
    args = usage_calls[0][1]
    assert args[0] == "aoa-session-memory-mcp"
    assert args[args.index("--kind") + 1] == "auto"
    assert args[args.index("--limit") + 1] == "5"
    assert args[args.index("--per-route-limit") + 1] == "4"
    assert args[args.index("--session") + 1] == "session-1"


def test_generic_search_routes_agent_event_filters_to_fast_agent_route(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search(
        "",
        filters={
            "session": "session-1",
            "doc_type": "event",
            "agent_event": "assistant_final_closeout",
            "task_episode_id": "task-0001",
        },
        limit=3,
    )

    assert search["artifact_type"] == "agent_event_route_results"
    assert search["results"][0]["agent_event"] == "assistant_answer"
    assert "served by MCP agent-event route fast path" in search["diagnostics"]
    assert not any(call[0] == "search" for call in runner.calls)
    calls = {call[0]: call[1] for call in runner.calls}
    args = calls["agent-responses"]
    assert "--use-shards" in args
    assert args[args.index("--max-shards") + 1] == "24"
    assert args[args.index("--session") + 1] == "session-1"
    assert args[args.index("--agent-event") + 1] == "assistant_final_closeout"
    assert args[args.index("--task-episode-id") + 1] == "task-0001"
    assert "--explain" not in args


def test_generic_search_agent_event_fast_path_honors_shard_controls(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search(
        "answer",
        filters={
            "doc_type": "event",
            "agent_event": "assistant_answer",
            "use_shards": False,
            "max_shards": 1,
        },
        limit=3,
    )

    assert search["artifact_type"] == "agent_event_route_results"
    assert "served by MCP agent-event route fast path" in search["diagnostics"]
    assert not any(call[0] == "search" for call in runner.calls)
    calls = {call[0]: call[1] for call in runner.calls}
    args = calls["agent-responses"]
    assert args[args.index("--query") + 1] == "answer"
    assert args[args.index("--agent-event") + 1] == "assistant_answer"
    assert "--use-shards" not in args
    assert "--no-shards" in args
    assert "--max-shards" not in args


def test_unscoped_agent_responses_returns_route_guidance_without_archive_scan(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    payload = state.session_agent_responses(limit=8)

    assert payload["ok"] is False
    assert payload["artifact_type"] == "agent_event_route_guidance"
    assert "unscoped_agent_response_route_requires_query_session_episode_or_event_filter" in payload["diagnostics"]
    assert payload["mcp_access"]["archive_command"] is None
    assert runner.calls == []


def test_agent_event_search_with_ordinary_filters_uses_full_search(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search(
        "",
        filters={
            "session": "session-1",
            "doc_type": "event",
            "agent_event": "open_thread",
            "task_episode_id": "task-0001",
            "route_signal": "mcp:aoa_session_memory_mcp",
            "event_type": "TOOL_CALL",
            "date_from": "2026-06-01",
        },
        limit=3,
    )

    assert search["artifact_type"] == "search_results"
    assert not any(call[0] == "agent-responses" for call in runner.calls)
    search_calls = [call for call in runner.calls if call[0] == "search"]
    assert len(search_calls) == 1
    args = search_calls[0][1]
    assert "--use-shards" not in args
    assert "--max-shards" not in args
    assert args[args.index("--agent-event") + 1] == "assistant_open_thread"
    assert args[args.index("--task-episode-id") + 1] == "task-0001"
    assert args[args.index("--route-signal") + 1] == "mcp:aoa_session_memory_mcp"
    assert args[args.index("--event-type") + 1] == "TOOL_CALL"
    assert args[args.index("--date-from") + 1] == "2026-06-01"


def test_task_episode_route_only_filters_with_ordinary_filters_are_rejected(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search(
        "",
        filters={
            "doc_type": "task_episode",
            "status": "closed",
            "date_from": "2026-06-01",
        },
        limit=3,
    )

    assert search["ok"] is False
    assert search["artifact_type"] == "session_search_filter_error"
    assert search["unsupported_filter_mix"]["ordinary_search_filters"] == ["date_from"]
    assert search["unsupported_filter_mix"]["route_specific_filters"] == ["status"]
    assert not runner.calls


def test_episode_alias_is_preserved_when_agent_route_falls_back_to_search(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search(
        "",
        filters={
            "doc_type": "event",
            "agent_event": "assistant_final_closeout",
            "episode": "task-0001",
            "event_type": "TOOL_CALL",
        },
        limit=3,
    )

    assert search["artifact_type"] == "search_results"
    assert not any(call[0] == "agent-responses" for call in runner.calls)
    search_calls = [call for call in runner.calls if call[0] == "search"]
    assert len(search_calls) == 1
    args = search_calls[0][1]
    assert args[args.index("--agent-event") + 1] == "assistant_final_closeout"
    assert args[args.index("--task-episode-id") + 1] == "task-0001"
    assert args[args.index("--event-type") + 1] == "TOOL_CALL"


def test_generic_search_routes_task_episode_filters_to_fast_episode_route(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search(
        "",
        filters={
            "session": "session-1",
            "doc_type": "task_episode",
            "status": "closed",
            "verification_state": "verified",
        },
        limit=4,
    )

    assert search["artifact_type"] == "task_episode_route_results"
    assert search["results"][0]["episode_id"] == "task-0001"
    assert "served by MCP task-episode route fast path" in search["diagnostics"]
    assert not any(call[0] == "search" for call in runner.calls)
    calls = {call[0]: call[1] for call in runner.calls}
    args = calls["task-episodes"]
    assert args[args.index("--session") + 1] == "session-1"
    assert args[args.index("--status") + 1] == "closed"
    assert args[args.index("--verification-state") + 1] == "verified"


def test_generic_search_routes_goal_lifecycle_filters_to_fast_goal_route(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search(
        "",
        filters={
            "session": "session-1",
            "doc_type": "goal_lifecycle",
            "goal_id": "goal-0001",
            "status": "complete",
            "event_kind": "goal_completed",
        },
        limit=3,
    )

    assert search["artifact_type"] == "goal_lifecycle_route_results"
    assert search["results"][0]["goal_id"] == "goal-0001"
    assert "served by MCP goal-lifecycle route fast path" in search["diagnostics"]
    assert not any(call[0] == "search" for call in runner.calls)
    calls = {call[0]: call[1] for call in runner.calls}
    args = calls["goal-lifecycles"]
    assert args[args.index("--session") + 1] == "session-1"
    assert args[args.index("--goal-id") + 1] == "goal-0001"
    assert args[args.index("--status") + 1] == "complete"
    assert args[args.index("--event-kind") + 1] == "goal_completed"


def test_goal_lifecycle_search_with_agent_filters_uses_full_search(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search(
        "",
        filters={
            "session": "session-1",
            "doc_type": "goal_lifecycle",
            "agent_event": "assistant_final_closeout",
            "task_episode_id": "task-0001",
        },
        limit=3,
    )

    assert search["artifact_type"] == "search_results"
    assert not any(call[0] == "goal-lifecycles" for call in runner.calls)
    search_calls = [call for call in runner.calls if call[0] == "search"]
    assert len(search_calls) == 1
    args = search_calls[0][1]
    assert args[args.index("--doc-type") + 1] == "goal_lifecycle"
    assert args[args.index("--agent-event") + 1] == "assistant_final_closeout"
    assert args[args.index("--task-episode-id") + 1] == "task-0001"


def test_goal_lifecycle_search_with_episode_alias_uses_full_search(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search(
        "",
        filters={
            "session": "session-1",
            "doc_type": "goal_lifecycle",
            "episode": "task-0001",
        },
        limit=3,
    )

    assert search["artifact_type"] == "search_results"
    assert not any(call[0] == "goal-lifecycles" for call in runner.calls)
    search_calls = [call for call in runner.calls if call[0] == "search"]
    assert len(search_calls) == 1
    args = search_calls[0][1]
    assert args[args.index("--doc-type") + 1] == "goal_lifecycle"
    assert args[args.index("--task-episode-id") + 1] == "task-0001"


def test_agent_event_and_task_episode_routes_wrap_archive_cli(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    responses = state.session_agent_responses(
        query="closeout",
        session="session-1",
        agent_events=["assistant_final_closeout"],
        episode="task-0001",
        limit=3,
    )
    progress = state.session_agent_progress_updates(session="session-1", limit=2)
    reasoning = state.session_agent_reasoning_windows(session="session-1", before=1, after=2, limit=1)
    episodes = state.session_task_episodes(session="session-1", status="closed", verification_state="verified", limit=4)
    neighborhood = state.session_answer_neighborhood(session="session-1", agent_events=["assistant_answer"], limit=1)

    assert responses["result_count"] == 1
    assert progress["artifact_type"] == "agent_event_route_results"
    assert reasoning["window_count"] == 1
    assert episodes["results"][0]["episode_id"] == "task-0001"
    assert episodes["mcp_payload_policy"]["response_compacted"] is True
    assert episodes["results"][0]["sample_refs"]["answers"]["ref_count"] == 2
    assert episodes["results"][0]["sample_refs"]["answers"]["omitted_ref_count"] == 1
    assert "segment_index" not in episodes["results"][0]["sample_refs"]["answers"]["refs"][0]
    assert neighborhood["artifact_type"] == "agent_event_windows"
    calls = {call[0]: call[1] for call in runner.calls}
    response_args = calls["agent-responses"]
    assert "--use-shards" in response_args
    assert response_args[response_args.index("--max-shards") + 1] == "24"
    assert response_args[response_args.index("--agent-event") + 1] == "assistant_final_closeout"
    assert response_args[response_args.index("--task-episode-id") + 1] == "task-0001"
    assert "agent-progress-updates" in calls
    assert "agent-reasoning-windows" in calls
    reasoning_args = calls["agent-reasoning-windows"]
    assert "--explain" in reasoning_args
    assert "answer-neighborhood" in calls
    neighborhood_args = calls["answer-neighborhood"]
    assert "--explain" in neighborhood_args
    episode_args = calls["task-episodes"]
    assert episode_args[episode_args.index("--status") + 1] == "closed"
    assert episode_args[episode_args.index("--verification-state") + 1] == "verified"

    runner.calls.clear()
    state.session_agent_reasoning_windows(session="session-1", explain=False)
    state.session_answer_neighborhood(session="session-1", explain=False)
    no_explain_calls = {call[0]: call[1] for call in runner.calls}
    assert "--no-explain" in no_explain_calls["agent-reasoning-windows"]
    assert "--no-explain" in no_explain_calls["answer-neighborhood"]


def test_agent_event_routes_use_sqlite_fast_path_when_live_schema_exists(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)
    conn = sqlite3.connect(state.aoa_root / "search/aoa-search.sqlite3")
    try:
        conn.executescript(
            """
            ALTER TABLE documents ADD COLUMN conversation_act TEXT;
            ALTER TABLE documents ADD COLUMN session_act TEXT;
            ALTER TABLE documents ADD COLUMN agent_event TEXT;
            ALTER TABLE documents ADD COLUMN task_episode_id TEXT;
            ALTER TABLE documents ADD COLUMN route_layers TEXT;
            ALTER TABLE documents ADD COLUMN route_signals TEXT;
            ALTER TABLE documents ADD COLUMN body TEXT;
            CREATE INDEX idx_documents_session_agent_event ON documents(session_label, agent_event);
            CREATE INDEX idx_documents_agent_event ON documents(agent_event);
            """
        )
        conn.execute(
            """
            UPDATE documents
            SET conversation_act = 'assistant_response',
                session_act = 'answer',
                agent_event = 'assistant_answer',
                task_episode_id = 'task-0001',
                route_layers = '|agent_event|',
                route_signals = '|agent_event:assistant_answer|',
                body = 'answer body'
            WHERE id = 'event:session-1:000:000001'
            """
        )
        conn.execute(
            """
            INSERT INTO documents (
                id, doc_type, session_id, session_label, session_title, session_date, event_type, family,
                title, segment_ref, segment_index_path, raw_ref, raw_block_ref, manifest_path,
                freshness_status, stale_reason, conversation_act, session_act, agent_event,
                task_episode_id, route_layers, route_signals, body
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "event:session-1:000:000002",
                "event",
                "session-1",
                "2026-05-26__001__session-memory-mcp",
                "Session memory MCP",
                "2026-05-26",
                "OPEN_THREAD",
                "progress_state",
                "Assistant open thread",
                "000__initial-to-latest.md#event-000002",
                (state.aoa_root / "sessions/2026-05-26__001__session-memory-mcp/segments/000.index.json").as_posix(),
                "raw:line:2",
                "raw/blocks/000__initial-to-latest.raw.jsonl#L2",
                (state.aoa_root / "sessions/2026-05-26__001__session-memory-mcp/session.manifest.json").as_posix(),
                "fresh",
                "",
                "assistant_open_thread",
                "memory_signal",
                "assistant_open_thread",
                "task-0001",
                "|agent_event|decision_thread|",
                "|agent_event:assistant_open_thread|decision_thread:open_thread|",
                "open thread body",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    responses = state.session_agent_responses(session="session-1", limit=3)
    answer_alias = state.session_agent_responses(session="session-1", agent_events=["answer"], limit=3)
    open_thread_alias = state.session_agent_responses(session="session-1", agent_events=["open_thread"], limit=3)
    closeout_final = state.session_agent_responses(session="session-1", closeout_final=True, limit=3)
    search = state.session_search(
        "",
        filters={"session": "session-1", "doc_type": "event", "agent_event": "assistant_answer"},
        limit=3,
    )
    open_thread_search = state.session_search(
        "",
        filters={"session": "session-1", "doc_type": "event", "agent_event": "open_thread"},
        limit=3,
    )
    reasoning = state.session_agent_reasoning_windows(session="session-1", limit=1)
    neighborhood = state.session_answer_neighborhood(session="session-1", limit=1)

    assert responses["source"] == "portable_sqlite_agent_event_fast_path"
    assert responses["result_count"] == 2
    assert {item["agent_event"] for item in responses["results"]} == {"assistant_answer", "assistant_open_thread"}
    assert answer_alias["agent_events"] == ["assistant_answer"]
    assert answer_alias["requested_agent_events"] == ["answer"]
    assert answer_alias["result_count"] == 1
    assert answer_alias["results"][0]["agent_event"] == "assistant_answer"
    assert open_thread_alias["agent_events"] == ["assistant_open_thread"]
    assert open_thread_alias["requested_agent_events"] == ["open_thread"]
    assert open_thread_alias["result_count"] == 1
    assert open_thread_alias["results"][0]["agent_event"] == "assistant_open_thread"
    assert closeout_final["source"] == "portable_sqlite_agent_event_fast_path"
    assert closeout_final["agent_events"] == ["assistant_final_closeout"]
    assert closeout_final["result_count"] == 0
    assert responses["search_projection"]["mode"] == "mcp_sqlite_agent_event_fast_path"
    assert responses["search_projection"]["fallback_route"] == "archive_cli_shard_fanout"
    assert responses["cost_profile"]["lightweight_route"] is True
    assert responses["cost_profile"]["uses_fts"] is False
    assert responses["mcp_access"]["archive_command"] is None
    assert responses["quality"]["ordered_by"] == "sqlite_rowid_desc_agent_event_fast_path"
    assert responses["quality"]["result_count"] == 2
    assert responses["quality"]["agent_event_counts"] == {
        "assistant_answer": 1,
        "assistant_open_thread": 1,
    }
    assert responses["quality"]["freshness_counts"] == {"fresh": 2}
    assert responses["quality"]["source_counts"] == {"mcp_sqlite_projection": 2}
    assert responses["quality"]["conversation_act_counts"] == {
        "assistant_open_thread": 1,
        "assistant_response": 1,
    }
    assert responses["quality"]["raw_ref_present_count"] == 2
    assert responses["quality"]["segment_ref_present_count"] == 2
    assert responses["quality"]["latest_result"]["event_id"] == "000002"
    assert responses["quality"]["latest_result"]["raw"] == "raw:line:2"
    assert search["source"] == "portable_sqlite_agent_event_fast_path"
    assert "served by MCP agent-event route fast path" in search["diagnostics"]
    assert open_thread_search["source"] == "portable_sqlite_agent_event_fast_path"
    assert open_thread_search["agent_events"] == ["assistant_open_thread"]
    assert open_thread_search["requested_agent_events"] == ["open_thread"]
    assert open_thread_search["result_count"] == 1
    assert open_thread_search["results"][0]["agent_event"] == "assistant_open_thread"
    assert reasoning["source"] == "portable_sqlite_agent_event_window_fast_path"
    assert reasoning["search_projection"]["mode"] == "mcp_sqlite_agent_event_fast_path"
    assert reasoning["cost_profile"]["lightweight_route"] is True
    assert reasoning["quality"]["ordered_by"] == "sqlite_rowid_desc_agent_event_fast_path"
    assert neighborhood["source"] == "portable_sqlite_agent_event_window_fast_path"
    assert neighborhood["window_count"] == 1
    assert neighborhood["search_projection"]["mode"] == "mcp_sqlite_agent_event_fast_path"
    assert neighborhood["cost_profile"]["lightweight_route"] is True
    assert neighborhood["quality"]["ordered_by"] == "sqlite_rowid_desc_agent_event_fast_path"
    assert not any(call[0] in {"agent-responses", "answer-neighborhood"} for call in runner.calls)


def test_text_agent_event_route_uses_archive_shard_path_even_when_sqlite_fast_schema_exists(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)
    conn = sqlite3.connect(state.aoa_root / "search/aoa-search.sqlite3")
    try:
        conn.executescript(
            """
            ALTER TABLE documents ADD COLUMN conversation_act TEXT;
            ALTER TABLE documents ADD COLUMN session_act TEXT;
            ALTER TABLE documents ADD COLUMN agent_event TEXT;
            ALTER TABLE documents ADD COLUMN task_episode_id TEXT;
            ALTER TABLE documents ADD COLUMN route_layers TEXT;
            ALTER TABLE documents ADD COLUMN route_signals TEXT;
            ALTER TABLE documents ADD COLUMN body TEXT;
            CREATE INDEX idx_documents_session_agent_event ON documents(session_label, agent_event);
            CREATE INDEX idx_documents_agent_event ON documents(agent_event);
            """
        )
        conn.execute(
            """
            UPDATE documents
            SET agent_event = 'assistant_answer',
                body = 'answer body'
            WHERE id = 'event:session-1:000:000001'
            """
        )
        conn.commit()
    finally:
        conn.close()

    responses = state.session_agent_responses(query="answer", session="session-1", limit=3)

    assert responses["artifact_type"] == "agent_event_route_results"
    calls = {call[0]: call[1] for call in runner.calls}
    args = calls["agent-responses"]
    assert "--use-shards" in args
    assert args[args.index("--max-shards") + 1] == "24"
    assert args[args.index("--query") + 1] == "answer"
    assert args[args.index("--session") + 1] == "session-1"


def test_agent_event_fast_path_accepts_live_agent_event_date_index(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)
    conn = sqlite3.connect(state.aoa_root / "search/aoa-search.sqlite3")
    try:
        conn.executescript(
            """
            ALTER TABLE documents ADD COLUMN conversation_act TEXT;
            ALTER TABLE documents ADD COLUMN session_act TEXT;
            ALTER TABLE documents ADD COLUMN agent_event TEXT;
            ALTER TABLE documents ADD COLUMN task_episode_id TEXT;
            ALTER TABLE documents ADD COLUMN route_layers TEXT;
            ALTER TABLE documents ADD COLUMN route_signals TEXT;
            CREATE INDEX idx_documents_agent_event_date ON documents(agent_event, session_date);
            """
        )
        conn.execute(
            """
            UPDATE documents
            SET conversation_act = 'assistant_final_closeout',
                session_act = 'assistant_closeout',
                agent_event = 'assistant_final_closeout',
                task_episode_id = 'task-0001',
                route_layers = '|agent_event|',
                route_signals = '|agent_event:assistant_final_closeout|'
            WHERE id = 'event:session-1:000:000001'
            """
        )
        conn.commit()
    finally:
        conn.close()

    responses = state.session_agent_responses(closeout_final=True, limit=3)

    assert responses["source"] == "portable_sqlite_agent_event_fast_path"
    assert responses["agent_events"] == ["assistant_final_closeout"]
    assert responses["result_count"] == 1
    assert responses["results"][0]["agent_event"] == "assistant_final_closeout"
    assert runner.calls == []


def test_goal_lifecycle_route_wraps_archive_cli_and_compacts_payload(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    lifecycles = state.session_goal_lifecycles(
        session="session-1",
        goal_id="goal-0001",
        status="complete",
        event_kind="goal_completed",
        limit=4,
        order="chronological",
    )

    assert lifecycles["artifact_type"] == "goal_lifecycle_route_results"
    assert lifecycles["results"][0]["goal_id"] == "goal-0001"
    assert lifecycles["results"][0]["status"] == "complete"
    assert lifecycles["results"][0]["task_episode_ids"] == ["task-0001"]
    assert lifecycles["results"][0]["refs"]["completed"]["raw_ref"] == "raw:line:6"
    assert lifecycles["results"][0]["objective"].endswith("...")
    assert lifecycles["results"][0]["objective_omitted"] is True
    assert lifecycles["results"][0]["objective_chars"] > 320
    assert lifecycles["results"][0]["objective_source"] == "goal_tool_output"
    assert lifecycles["results"][0]["observed_goal"]["objective"].endswith("...")
    assert lifecycles["results"][0]["observed_goal"]["objective_omitted"] is True
    assert lifecycles["results"][0]["observed_goal"]["createdAt"] == 1780000000
    assert len(lifecycles["results"][0]["state_observations"]) == 2
    assert lifecycles["results"][0]["state_observations"][0]["refs"]["raw_ref"] == "raw:line:7"
    assert lifecycles["results"][0]["omitted_state_observation_count"] == 1
    assert len(lifecycles["results"][0]["usage_observations"]) == 2
    assert lifecycles["results"][0]["usage_observations"][1]["refs"]["raw_ref"] == "raw:line:7"
    assert lifecycles["results"][0]["omitted_usage_observation_count"] == 1
    assert len(lifecycles["results"][0]["sample_events"]) == 2
    assert lifecycles["results"][0]["sample_events"][0]["objective"].endswith("...")
    assert lifecycles["results"][0]["sample_events"][0]["objective_omitted"] is True
    assert lifecycles["results"][0]["sample_events"][0]["refs"]["raw_ref"] == "raw:line:2"
    assert lifecycles["results"][0]["sample_events"][1]["refs"]["raw_ref"] == "raw:line:3"
    assert lifecycles["results"][0]["omitted_sample_event_count"] == 3
    assert lifecycles["mcp_payload_policy"]["response_compacted"] is True
    assert lifecycles["mcp_payload_policy"]["sample_events_per_lifecycle"] == 2
    calls = {call[0]: call[1] for call in runner.calls}
    args = calls["goal-lifecycles"]
    assert args[args.index("--session") + 1] == "session-1"
    assert args[args.index("--goal-id") + 1] == "goal-0001"
    assert args[args.index("--status") + 1] == "complete"
    assert args[args.index("--event-kind") + 1] == "goal_completed"
    assert args[args.index("--order") + 1] == "chronological"


def test_goal_lifecycle_route_rejects_invalid_order_before_cli(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    lifecycles = state.session_goal_lifecycles(order="desc")

    assert lifecycles["ok"] is False
    assert lifecycles["artifact_type"] == "goal_lifecycle_route_error"
    assert lifecycles["allowed_order_values"] == ["recent", "chronological"]
    assert lifecycles["mcp_access"]["archive_command"] is None
    assert runner.calls == []


def test_stdio_route_count_summary_allows_empty_route_results() -> None:
    validator = load_validator_module()

    summary = validator._stdio_route_count_summary(
        {"entity_count": 1, "source": "atlas"},
        {"layer": "mcp", "requested_layer": "mcp_service"},
        {"entity_count": 2},
        {"entity_count": 3},
        {"entity_count": 4},
        {"result_count": 5},
        {"result_count": 0, "search_projection": {"mode": "materialized_shard_fanout"}},
        {"ok": True, "result_count": 0},
        {"ok": True, "result_count": 0},
        {"ok": True, "result_count": 0},
        {"ok": True, "window_count": 0},
        {"ok": True, "result_count": 0},
        {"ok": True, "result_count": 0},
        {"ok": True, "window_count": 0},
        {"ok": True, "entity_count": 1},
        {"primary_route": {"route_id": "entity_usage_chain"}, "cost_profile": {"structured_first": True}},
        {"quality": {"usage_event_count": 2, "graph_node_count": 3, "raw_or_segment_ref_present": True}},
        {
            "counts": {"usage_event_count": 2, "chain_with_result_or_consequence_count": 2},
            "first_ref": {"raw_ref": "raw:line:7"},
        },
        {"kind": "mcp", "requested_kind": "mcp_service"},
        {"kind": "agent_event", "outcome_event_count": 2},
        {"node_count": 3, "edge_count": 2},
        {"cooccurrence_count": 4, "evidence_ref_count": 8},
        {"retrieval_redirect": {"served_by": "aoa_session_entity_usage_chain"}},
        {
            "quality": {"scenario_count": 1, "warn_count": 0},
            "scenarios": [
                {
                    "profile": "entity_registry_lookup",
                    "active_lookup_count": 1,
                    "observed_lookup_count": 1,
                    "unknown_lookup_count": 1,
                    "stale_lookup_count": 1,
                    "removed_lookup_count": 1,
                    "transition_probe_count": 2,
                }
            ],
        },
        {"case_count": 1, "actionable_gap_count": 0},
        {"case_count": 3, "truth_status": "source_corpus_inventory_not_live_route_proof"},
        {"recommendation": "use_graph_search"},
        {
            "result_count": 1,
            "quality": {"freshness_status": "current"},
            "cost_profile": {"uses_materialized_direct_event_rollup": True},
        },
        {"ok": True, "projection_completeness": {"status": "current"}},
        tool_count=35,
    )

    assert summary["tool_count"] == 35
    assert summary["inventory_entity_count"] == 1
    assert summary["mcp_service_inventory_layer"] == "mcp"
    assert summary["mcp_service_inventory_requested_layer"] == "mcp_service"
    assert summary["hook_inventory_entity_count"] == 2
    assert summary["tool_inventory_entity_count"] == 3
    assert summary["api_inventory_entity_count"] == 4
    assert summary["open_thread_result_count"] == 5
    assert summary["search_alias_projection_mode"] == "materialized_shard_fanout"
    assert summary["agent_response_count"] == 0
    assert summary["agent_closeout_count"] == 0
    assert summary["agent_progress_count"] == 0
    assert summary["agent_reasoning_window_count"] == 0
    assert summary["task_episode_count"] == 0
    assert summary["goal_lifecycle_count"] == 0
    assert summary["answer_neighborhood_count"] == 0
    assert summary["literal_plan_primary_route"] == "entity_usage_chain"
    assert summary["literal_plan_structured_first"] is True
    assert summary["entity_dossier_usage_count"] == 2
    assert summary["entity_dossier_graph_node_count"] == 3
    assert summary["entity_dossier_raw_or_segment_ref_present"] is True
    assert summary["entity_usage_chain_usage_count"] == 2
    assert summary["entity_usage_chain_success_count"] == 2
    assert summary["entity_usage_chain_first_ref_present"] is True
    assert summary["usage_alias_kind"] == "mcp"
    assert summary["usage_alias_requested_kind"] == "mcp_service"
    assert summary["agent_event_usage_kind"] == "agent_event"
    assert summary["graph_neighborhood_node_count"] == 3
    assert summary["graph_neighborhood_edge_count"] == 2
    assert summary["graph_cooccurrence_count"] == 4
    assert summary["graph_cooccurrence_ref_count"] == 8
    assert summary["live_scenario_count"] == 1
    assert summary["live_scenario_warn_count"] == 0
    assert summary["live_scenario_entity_registry_active_count"] == 1
    assert summary["live_scenario_entity_registry_observed_count"] == 1
    assert summary["live_scenario_entity_registry_unknown_count"] == 1
    assert summary["live_scenario_entity_registry_stale_count"] == 1
    assert summary["live_scenario_entity_registry_removed_count"] == 1
    assert summary["live_scenario_entity_registry_transition_probe_count"] == 2
    assert summary["live_scenario_corpus_case_count"] == 1
    assert summary["live_scenario_corpus_actionable_gap_count"] == 0
    assert summary["live_scenario_corpus_inventory_case_count"] == 3
    assert summary["live_scenario_corpus_inventory_truth_status"] == "source_corpus_inventory_not_live_route_proof"
    assert summary["direct_event_rollup_result_count"] == 1
    assert summary["direct_event_rollup_freshness_status"] == "current"
    assert summary["direct_event_rollup_materialized"] is True
    assert summary["agent_event_usage_outcome_count"] == 2
    assert summary["retrieve_usage_served_by"] == "aoa_session_entity_usage_chain"
    assert summary["maintenance_recommendation"] == "use_graph_search"


def test_validator_requires_literal_and_graph_mcp_tools() -> None:
    validator = load_validator_module()

    assert "aoa_session_literal_query_plan" in validator.REQUIRED_STDIO_SMOKE_TOOLS
    assert "aoa_session_entity_dossier" in validator.REQUIRED_STDIO_SMOKE_TOOLS
    assert "aoa_session_entity_usage_chain" in validator.REQUIRED_STDIO_SMOKE_TOOLS
    assert "aoa_session_route_rollup_query" in validator.REQUIRED_STDIO_SMOKE_TOOLS
    assert "aoa_session_direct_event_rollup_query" in validator.REQUIRED_STDIO_SMOKE_TOOLS
    assert "aoa_session_graph_neighborhood" in validator.REQUIRED_STDIO_SMOKE_TOOLS
    assert "aoa_session_graph_bridge" in validator.REQUIRED_STDIO_SMOKE_TOOLS
    assert "aoa_session_graph_cooccurrence" in validator.REQUIRED_STDIO_SMOKE_TOOLS


def test_validator_search_alias_smoke_is_route_only() -> None:
    validator = load_validator_module()

    arguments = validator._search_alias_smoke_arguments(limit=2)

    assert arguments["query"] == ""
    assert arguments["limit"] == 2
    assert arguments["filters"]["route_signal"] == "mcp:aoa_session_memory_mcp"
    assert arguments["filters"]["doc_type"] == "event"
    assert arguments["filters"]["layer"] == "mcp"
    assert arguments["filters"]["use_shards"] is True


def test_validator_freshness_smoke_selector_skips_stale_latest_for_stable_candidate() -> None:
    validator = load_validator_module()

    class SmokeState:
        def session_freshness_check(self, refs: list[str], session: str = "") -> dict:
            statuses = {
                "latest-stale": "stale",
                "stable-indexed": "current",
            }
            return {
                "ok": True,
                "projection_freshness": {"status": statuses.get(session, "stale")},
                "checks": [{"status": "present", "ref": ref} for ref in refs],
            }

        def session_search(self, query: str, *, filters: dict, limit: int) -> dict:
            assert query == ""
            assert filters == {"doc_type": "session", "archive_status": "indexed"}
            assert limit == 5
            return {
                "results": [
                    {
                        "session_id": "stable-id",
                        "session_label": "stable-indexed",
                        "archive_status": "indexed",
                        "refs": {"session": "/tmp/stable/session.manifest.json"},
                    }
                ]
            }

        def session_brief(self, session: str, max_segments: int) -> dict:
            assert session == "stable-indexed"
            assert max_segments == 2
            return {
                "ok": True,
                "session": {"label": "stable-indexed", "archive_status": "indexed"},
                "refs": {"manifest": "/tmp/stable/session.manifest.json"},
            }

    latest = {
        "ok": True,
        "session": {"label": "latest-stale", "archive_status": "indexed"},
        "refs": {"manifest": "/tmp/latest/session.manifest.json"},
    }

    selected = validator._select_freshness_smoke_brief(SmokeState(), latest)

    assert selected["session"]["label"] == "stable-indexed"


def test_validator_usage_chain_first_ref_accepts_alias_keys() -> None:
    validator = load_validator_module()

    assert validator._has_first_raw_or_segment_ref({"raw_ref": "raw:line:7"}) is True
    assert validator._has_first_raw_or_segment_ref({"segment_ref": "000.md#event-000007"}) is True
    assert validator._has_first_raw_or_segment_ref({"session": "session.manifest.json"}) is False


def test_running_mcp_process_advisory_reports_stale_transports(tmp_path: Path, monkeypatch: Any) -> None:
    validator = load_validator_module()
    repo_root = tmp_path / "aoa-session-memory-mcp"
    for relative in (
        "src/aoa_session_memory_mcp/core.py",
        "src/aoa_session_memory_mcp/server.py",
        "scripts/aoa_session_memory_mcp_server.py",
    ):
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")
        os.utime(path, (2_000.0, 2_000.0))
    monkeypatch.setattr(validator, "REPO_ROOT", repo_root)

    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text("btime 1000\n", encoding="utf-8")
    ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))

    def write_process(pid: str, start_epoch: float) -> None:
        process_dir = proc / pid
        process_dir.mkdir()
        cmdline = b"python3\0.codex/bin/aoa-session-memory-mcp-server.py\0"
        (process_dir / "cmdline").write_bytes(cmdline)
        start_ticks = int((start_epoch - 1000.0) * float(ticks))
        fields = [pid, "(python3)", "S", *(["0"] * 18), str(start_ticks)]
        (process_dir / "stat").write_text(" ".join(fields), encoding="utf-8")

    write_process("101", 1_500.0)
    write_process("102", 2_500.0)

    advisory = validator._running_mcp_process_advisory(proc)

    assert advisory["available"] is True
    assert advisory["process_count"] == 2
    assert advisory["stale_process_count"] == 1
    assert advisory["restart_advisory"] is True
    stale = [item for item in advisory["processes"] if item["started_before_current_source"]]
    assert stale[0]["pid"] == 101


def test_running_mcp_process_advisory_does_not_restart_for_core_only_change(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    validator = load_validator_module()
    repo_root = tmp_path / "aoa-session-memory-mcp"
    mtimes = {
        "src/aoa_session_memory_mcp/core.py": 3_000.0,
        "src/aoa_session_memory_mcp/server.py": 1_000.0,
        "scripts/aoa_session_memory_mcp_server.py": 1_000.0,
    }
    for relative, mtime in mtimes.items():
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")
        os.utime(path, (mtime, mtime))
    monkeypatch.setattr(validator, "REPO_ROOT", repo_root)

    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text("btime 1000\n", encoding="utf-8")
    ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    process_dir = proc / "101"
    process_dir.mkdir()
    process_dir.joinpath("cmdline").write_bytes(b"python3\0.codex/bin/aoa-session-memory-mcp-server.py\0")
    start_ticks = int((2_000.0 - 1000.0) * float(ticks))
    fields = ["101", "(python3)", "S", *(["0"] * 18), str(start_ticks)]
    process_dir.joinpath("stat").write_text(" ".join(fields), encoding="utf-8")

    advisory = validator._running_mcp_process_advisory(proc)

    assert advisory["stale_process_count"] == 0
    assert advisory["restart_advisory"] is False
    assert advisory["processes"][0]["started_before_current_source"] is False
    assert advisory["processes"][0]["started_before_core_auto_reload_source"] is True


def test_running_mcp_process_advisory_handles_missing_procfs(tmp_path: Path) -> None:
    validator = load_validator_module()

    advisory = validator._running_mcp_process_advisory(tmp_path / "missing-proc")

    assert advisory["available"] is False
    assert advisory["reason"] == "procfs_unavailable"


def test_codex_session_advisory_reports_current_stale_transport(tmp_path: Path, monkeypatch: Any) -> None:
    validator = load_validator_module()
    repo_root = tmp_path / "aoa-session-memory-mcp"
    for relative in (
        "src/aoa_session_memory_mcp/core.py",
        "src/aoa_session_memory_mcp/server.py",
        "scripts/aoa_session_memory_mcp_server.py",
    ):
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")
        os.utime(path, (3_000.0, 3_000.0))
    monkeypatch.setattr(validator, "REPO_ROOT", repo_root)

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text("[mcp_servers.aoa_session_memory]\ncommand = \"python3\"\n", encoding="utf-8")
    os.utime(config_path, (2_000.0, 2_000.0))
    monkeypatch.setenv("CODEX_HOME", codex_home.as_posix())

    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text("btime 1000\n", encoding="utf-8")
    ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    current_pid = str(os.getpid())

    def write_process(pid: str, ppid: str, cmdline: list[str], start_epoch: float) -> None:
        process_dir = proc / pid
        process_dir.mkdir()
        process_dir.joinpath("cmdline").write_bytes(b"\0".join(part.encode("utf-8") for part in cmdline) + b"\0")
        process_dir.joinpath("status").write_text(f"Name:\tfixture\nPPid:\t{ppid}\n", encoding="utf-8")
        start_ticks = int((start_epoch - 1000.0) * float(ticks))
        fields = [pid, "(fixture)", "S", *(["0"] * 18), str(start_ticks)]
        process_dir.joinpath("stat").write_text(" ".join(fields), encoding="utf-8")

    write_process(current_pid, "200", ["python", "validate_session_memory_mcp.py"], 3_500.0)
    write_process("200", "1", ["/home/dionysus/.local/bin/codex", "resume"], 1_500.0)
    write_process("201", "1", ["/home/dionysus/.local/bin/codex", "resume"], 3_500.0)
    write_process("301", "201", ["python3", ".codex/bin/aoa-session-memory-mcp-server.py"], 3_600.0)

    advisory = validator._codex_session_advisory(proc)

    assert advisory["available"] is True
    assert advisory["current_codex_process_count"] == 1
    assert advisory["current_session_predates_config"] is True
    assert advisory["current_session_predates_current_source"] is True
    assert advisory["current_session_has_aoa_session_memory_child"] is False
    assert advisory["live_transport_restart_advisory"] is True
    assert advisory["current_codex_processes"][0]["pid"] == 200


def test_codex_session_advisory_treats_config_mtime_as_advisory_when_child_is_fresh(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    validator = load_validator_module()
    repo_root = tmp_path / "aoa-session-memory-mcp"
    for relative in (
        "src/aoa_session_memory_mcp/core.py",
        "src/aoa_session_memory_mcp/server.py",
        "scripts/aoa_session_memory_mcp_server.py",
    ):
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")
        os.utime(path, (1_000.0, 1_000.0))
    monkeypatch.setattr(validator, "REPO_ROOT", repo_root)

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text(
        "[mcp_servers.aoa_session_memory]\ncommand = \"aoa-session-memory-mcp-server\"\n",
        encoding="utf-8",
    )
    os.utime(config_path, (2_000.0, 2_000.0))
    monkeypatch.setenv("CODEX_HOME", codex_home.as_posix())

    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text("btime 1000\n", encoding="utf-8")
    ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    current_pid = str(os.getpid())

    def write_process(pid: str, ppid: str, cmdline: list[str], start_epoch: float) -> None:
        process_dir = proc / pid
        process_dir.mkdir()
        process_dir.joinpath("cmdline").write_bytes(b"\0".join(part.encode("utf-8") for part in cmdline) + b"\0")
        process_dir.joinpath("status").write_text(f"Name:\tfixture\nPPid:\t{ppid}\n", encoding="utf-8")
        start_ticks = int((start_epoch - 1000.0) * float(ticks))
        fields = [pid, "(fixture)", "S", *(["0"] * 18), str(start_ticks)]
        process_dir.joinpath("stat").write_text(" ".join(fields), encoding="utf-8")

    write_process(current_pid, "200", ["python", "validate_session_memory_mcp.py"], 2_100.0)
    write_process("200", "1", ["/home/dionysus/.local/bin/codex", "resume"], 1_500.0)
    write_process("301", "200", ["/home/dionysus/.local/bin/aoa-session-memory-mcp-server"], 1_600.0)

    advisory = validator._codex_session_advisory(proc)

    assert advisory["current_session_predates_config"] is True
    assert advisory["current_session_has_aoa_session_memory_child"] is True
    assert advisory["current_session_has_fresh_aoa_session_memory_child"] is True
    assert advisory["current_session_mcp_child_stale_count"] == 0
    assert advisory["config_reload_advisory"] is True
    assert advisory["live_transport_restart_advisory"] is False


def test_codex_session_advisory_recognizes_installed_server_entrypoint(tmp_path: Path, monkeypatch: Any) -> None:
    validator = load_validator_module()
    repo_root = tmp_path / "aoa-session-memory-mcp"
    source_epoch = time.time() + 1000.0
    for relative in (
        "src/aoa_session_memory_mcp/core.py",
        "src/aoa_session_memory_mcp/server.py",
        "scripts/aoa_session_memory_mcp_server.py",
    ):
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")
        os.utime(path, (source_epoch, source_epoch))
    monkeypatch.setattr(validator, "REPO_ROOT", repo_root)

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text("[mcp_servers.aoa_session_memory]\ncommand = \"aoa-session-memory-mcp-server\"\n", encoding="utf-8")
    os.utime(config_path, (source_epoch + 5.0, source_epoch + 5.0))
    monkeypatch.setenv("CODEX_HOME", codex_home.as_posix())

    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text("btime 1000\n", encoding="utf-8")
    ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    current_pid = str(os.getpid())

    def write_process(pid: str, ppid: str, cmdline: list[str], start_epoch: float) -> None:
        process_dir = proc / pid
        process_dir.mkdir()
        process_dir.joinpath("cmdline").write_bytes(b"\0".join(part.encode("utf-8") for part in cmdline) + b"\0")
        process_dir.joinpath("status").write_text(f"Name:\tfixture\nPPid:\t{ppid}\n", encoding="utf-8")
        start_ticks = int((start_epoch - 1000.0) * float(ticks))
        fields = [pid, "(fixture)", "S", *(["0"] * 18), str(start_ticks)]
        process_dir.joinpath("stat").write_text(" ".join(fields), encoding="utf-8")

    write_process(current_pid, "200", ["python", "validate_session_memory_mcp.py"], source_epoch + 100.0)
    write_process("200", "1", ["/home/dionysus/.local/bin/codex", "app-server"], source_epoch + 110.0)
    write_process("301", "200", ["/home/dionysus/.local/bin/aoa-session-memory-mcp-server"], source_epoch + 120.0)

    advisory = validator._codex_session_advisory(proc)

    assert advisory["current_session_has_aoa_session_memory_child"] is True
    assert advisory["live_transport_restart_advisory"] is False
    assert advisory["current_codex_processes"][0]["aoa_session_memory_child_pids"] == [301]


def test_codex_session_advisory_does_not_restart_for_core_only_change(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    validator = load_validator_module()
    repo_root = tmp_path / "aoa-session-memory-mcp"
    mtimes = {
        "src/aoa_session_memory_mcp/core.py": 3_000.0,
        "src/aoa_session_memory_mcp/server.py": 1_000.0,
        "scripts/aoa_session_memory_mcp_server.py": 1_000.0,
    }
    for relative, mtime in mtimes.items():
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")
        os.utime(path, (mtime, mtime))
    monkeypatch.setattr(validator, "REPO_ROOT", repo_root)

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text(
        "[mcp_servers.aoa_session_memory]\ncommand = \"aoa-session-memory-mcp-server\"\n",
        encoding="utf-8",
    )
    os.utime(config_path, (1_000.0, 1_000.0))
    monkeypatch.setenv("CODEX_HOME", codex_home.as_posix())

    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text("btime 1000\n", encoding="utf-8")
    ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    current_pid = str(os.getpid())

    def write_process(pid: str, ppid: str, cmdline: list[str], start_epoch: float) -> None:
        process_dir = proc / pid
        process_dir.mkdir()
        process_dir.joinpath("cmdline").write_bytes(b"\0".join(part.encode("utf-8") for part in cmdline) + b"\0")
        process_dir.joinpath("status").write_text(f"Name:\tfixture\nPPid:\t{ppid}\n", encoding="utf-8")
        start_ticks = int((start_epoch - 1000.0) * float(ticks))
        fields = [pid, "(fixture)", "S", *(["0"] * 18), str(start_ticks)]
        process_dir.joinpath("stat").write_text(" ".join(fields), encoding="utf-8")

    write_process(current_pid, "200", ["python", "validate_session_memory_mcp.py"], 2_000.0)
    write_process("200", "1", ["/home/dionysus/.local/bin/codex", "resume"], 2_000.0)
    write_process("301", "200", ["/home/dionysus/.local/bin/aoa-session-memory-mcp-server"], 2_000.0)

    advisory = validator._codex_session_advisory(proc)

    assert advisory["current_session_predates_current_source"] is False
    assert advisory["current_session_has_aoa_session_memory_child"] is True
    assert advisory["live_transport_restart_advisory"] is False
    assert advisory["current_codex_processes"][0]["started_before_core_auto_reload_source"] is True


def test_transport_preflight_reports_current_codex_restart_need(tmp_path: Path, monkeypatch: Any) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text(
        "[mcp_servers.aoa_session_memory]\n"
        "command = \"python3\"\n"
        "args = [\".codex/bin/aoa-session-memory-mcp-server.py\"]\n"
        "cwd = \"/srv/AbyssOS\"\n",
        encoding="utf-8",
    )
    os.utime(config_path, (2_000.0, 2_000.0))
    monkeypatch.setenv("CODEX_HOME", codex_home.as_posix())

    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text("btime 1000\n", encoding="utf-8")
    ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    current_pid = str(os.getpid())

    def write_process(pid: str, ppid: str, cmdline: list[str], start_epoch: float) -> None:
        process_dir = proc / pid
        process_dir.mkdir()
        process_dir.joinpath("cmdline").write_bytes(b"\0".join(part.encode("utf-8") for part in cmdline) + b"\0")
        process_dir.joinpath("status").write_text(f"Name:\tfixture\nPPid:\t{ppid}\n", encoding="utf-8")
        start_ticks = int((start_epoch - 1000.0) * float(ticks))
        fields = [pid, "(fixture)", "S", *(["0"] * 18), str(start_ticks)]
        process_dir.joinpath("stat").write_text(" ".join(fields), encoding="utf-8")

    write_process(current_pid, "200", ["python", "pytest"], 3_500.0)
    write_process("200", "1", ["/home/dionysus/.local/bin/codex", "resume"], 1_500.0)
    state = AoASessionMemoryMCPState(
        workspace_root=tmp_path,
        aoa_root=tmp_path / ".aoa",
        script_path=tmp_path / ".aoa/scripts/aoa_session_memory.py",
    )

    preflight = state.session_mcp_transport_preflight(proc_root=proc)

    assert preflight["schema"] == "aoa_session_memory_mcp_transport_preflight_v1"
    assert preflight["ok"] is False
    assert preflight["configured_server"]["configured"] is True
    assert preflight["direct_tool_transport_status"] == "restart_required"
    assert preflight["live_transport_restart_advisory"] is True
    assert preflight["codex_session"]["current_session_has_aoa_session_memory_child"] is False


def test_transport_preflight_treats_config_mtime_as_advisory_when_child_is_fresh(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module = sys.modules[AoASessionMemoryMCPState.__module__]
    package_root = tmp_path / "aoa-session-memory-mcp"
    core_path = package_root / "src" / "aoa_session_memory_mcp" / "core.py"
    server_path = package_root / "src" / "aoa_session_memory_mcp" / "server.py"
    wrapper_path = package_root / "scripts" / "aoa_session_memory_mcp_server.py"
    for path in (core_path, server_path, wrapper_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")
        os.utime(path, (1_000.0, 1_000.0))
    monkeypatch.setattr(module, "MCP_CORE_SOURCE_PATH", core_path)
    monkeypatch.setattr(module, "MCP_SERVER_SOURCE_PATH", server_path)

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text(
        "[mcp_servers.aoa_session_memory]\n"
        "command = \"aoa-session-memory-mcp-server\"\n"
        "cwd = \"/srv/AbyssOS\"\n",
        encoding="utf-8",
    )
    os.utime(config_path, (2_000.0, 2_000.0))
    monkeypatch.setenv("CODEX_HOME", codex_home.as_posix())

    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text("btime 1000\n", encoding="utf-8")
    ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    current_pid = str(os.getpid())

    def write_process(pid: str, ppid: str, cmdline: list[str], start_epoch: float) -> None:
        process_dir = proc / pid
        process_dir.mkdir()
        process_dir.joinpath("cmdline").write_bytes(b"\0".join(part.encode("utf-8") for part in cmdline) + b"\0")
        process_dir.joinpath("status").write_text(f"Name:\tfixture\nPPid:\t{ppid}\n", encoding="utf-8")
        start_ticks = int((start_epoch - 1000.0) * float(ticks))
        fields = [pid, "(fixture)", "S", *(["0"] * 18), str(start_ticks)]
        process_dir.joinpath("stat").write_text(" ".join(fields), encoding="utf-8")

    write_process(current_pid, "200", ["python", "pytest"], 2_100.0)
    write_process("200", "1", ["/home/dionysus/.local/bin/codex", "resume"], 1_500.0)
    write_process("301", "200", ["/home/dionysus/.local/bin/aoa-session-memory-mcp-server"], 1_600.0)
    state = AoASessionMemoryMCPState(
        workspace_root=tmp_path,
        aoa_root=tmp_path / ".aoa",
        script_path=tmp_path / ".aoa/scripts/aoa_session_memory.py",
    )

    preflight = state.session_mcp_transport_preflight(proc_root=proc)

    assert preflight["ok"] is True
    assert preflight["direct_tool_transport_status"] == "attached"
    assert preflight["live_transport_restart_advisory"] is False
    assert preflight["codex_session"]["current_session_predates_config"] is True
    assert preflight["codex_session"]["current_session_has_fresh_aoa_session_memory_child"] is True
    assert preflight["codex_session"]["current_session_mcp_child_stale_count"] == 0
    assert preflight["codex_session"]["config_reload_advisory"] is True


def test_transport_preflight_recognizes_installed_server_entrypoint(tmp_path: Path, monkeypatch: Any) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    source_epoch = time.time() + 1000.0
    config_path = codex_home / "config.toml"
    config_path.write_text(
        "[mcp_servers.aoa_session_memory]\n"
        "command = \"aoa-session-memory-mcp-server\"\n"
        "cwd = \"/srv/AbyssOS\"\n",
        encoding="utf-8",
    )
    os.utime(config_path, (source_epoch + 5.0, source_epoch + 5.0))
    monkeypatch.setenv("CODEX_HOME", codex_home.as_posix())

    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text("btime 1000\n", encoding="utf-8")
    ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    current_pid = str(os.getpid())

    def write_process(pid: str, ppid: str, cmdline: list[str], start_epoch: float) -> None:
        process_dir = proc / pid
        process_dir.mkdir()
        process_dir.joinpath("cmdline").write_bytes(b"\0".join(part.encode("utf-8") for part in cmdline) + b"\0")
        process_dir.joinpath("status").write_text(f"Name:\tfixture\nPPid:\t{ppid}\n", encoding="utf-8")
        start_ticks = int((start_epoch - 1000.0) * float(ticks))
        fields = [pid, "(fixture)", "S", *(["0"] * 18), str(start_ticks)]
        process_dir.joinpath("stat").write_text(" ".join(fields), encoding="utf-8")

    write_process(current_pid, "200", ["python", "pytest"], source_epoch + 100.0)
    write_process("200", "1", ["/home/dionysus/.local/bin/codex", "resume"], source_epoch + 110.0)
    write_process("301", "200", ["/home/dionysus/.local/bin/aoa-session-memory-mcp-server"], source_epoch + 120.0)
    state = AoASessionMemoryMCPState(
        workspace_root=tmp_path,
        aoa_root=tmp_path / ".aoa",
        script_path=tmp_path / ".aoa/scripts/aoa_session_memory.py",
    )

    preflight = state.session_mcp_transport_preflight(proc_root=proc)

    assert preflight["ok"] is True
    assert preflight["direct_tool_transport_status"] == "attached"
    assert preflight["live_transport_restart_advisory"] is False
    assert preflight["codex_session"]["current_session_has_aoa_session_memory_child"] is True
    assert preflight["codex_session"]["current_codex_processes"][0]["aoa_session_memory_child_pids"] == [301]
    assert preflight["running_mcp_processes"]["process_count"] == 1


def test_transport_preflight_does_not_restart_for_core_only_change(tmp_path: Path, monkeypatch: Any) -> None:
    module = sys.modules[AoASessionMemoryMCPState.__module__]
    package_root = tmp_path / "aoa-session-memory-mcp"
    core_path = package_root / "src" / "aoa_session_memory_mcp" / "core.py"
    server_path = package_root / "src" / "aoa_session_memory_mcp" / "server.py"
    wrapper_path = package_root / "scripts" / "aoa_session_memory_mcp_server.py"
    for path, mtime in ((core_path, 3_000.0), (server_path, 1_000.0), (wrapper_path, 1_000.0)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")
        os.utime(path, (mtime, mtime))
    monkeypatch.setattr(module, "MCP_CORE_SOURCE_PATH", core_path)
    monkeypatch.setattr(module, "MCP_SERVER_SOURCE_PATH", server_path)

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text(
        "[mcp_servers.aoa_session_memory]\n"
        "command = \"aoa-session-memory-mcp-server\"\n"
        "cwd = \"/srv/AbyssOS\"\n",
        encoding="utf-8",
    )
    os.utime(config_path, (1_000.0, 1_000.0))
    monkeypatch.setenv("CODEX_HOME", codex_home.as_posix())

    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text("btime 1000\n", encoding="utf-8")
    ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    current_pid = str(os.getpid())

    def write_process(pid: str, ppid: str, cmdline: list[str], start_epoch: float) -> None:
        process_dir = proc / pid
        process_dir.mkdir()
        process_dir.joinpath("cmdline").write_bytes(b"\0".join(part.encode("utf-8") for part in cmdline) + b"\0")
        process_dir.joinpath("status").write_text(f"Name:\tfixture\nPPid:\t{ppid}\n", encoding="utf-8")
        start_ticks = int((start_epoch - 1000.0) * float(ticks))
        fields = [pid, "(fixture)", "S", *(["0"] * 18), str(start_ticks)]
        process_dir.joinpath("stat").write_text(" ".join(fields), encoding="utf-8")

    write_process(current_pid, "200", ["python", "pytest"], 2_000.0)
    write_process("200", "1", ["/home/dionysus/.local/bin/codex", "resume"], 2_000.0)
    write_process("301", "200", ["/home/dionysus/.local/bin/aoa-session-memory-mcp-server"], 2_000.0)
    state = AoASessionMemoryMCPState(
        workspace_root=tmp_path,
        aoa_root=tmp_path / ".aoa",
        script_path=tmp_path / ".aoa/scripts/aoa_session_memory.py",
    )

    preflight = state.session_mcp_transport_preflight(proc_root=proc)

    assert preflight["ok"] is True
    assert preflight["direct_tool_transport_status"] == "attached"
    assert preflight["live_transport_restart_advisory"] is False
    assert preflight["codex_session"]["current_session_predates_current_source"] is False
    assert preflight["codex_session"]["current_codex_processes"][0]["started_before_core_auto_reload_source"] is True
    assert preflight["running_mcp_processes"]["restart_advisory"] is False
    assert preflight["running_mcp_processes"]["processes"][0]["started_before_core_auto_reload_source"] is True


def test_transport_preflight_restarts_for_core_change_when_auto_reload_disabled(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module = sys.modules[AoASessionMemoryMCPState.__module__]
    package_root = tmp_path / "aoa-session-memory-mcp"
    core_path = package_root / "src" / "aoa_session_memory_mcp" / "core.py"
    server_path = package_root / "src" / "aoa_session_memory_mcp" / "server.py"
    wrapper_path = package_root / "scripts" / "aoa_session_memory_mcp_server.py"
    for path, mtime in ((core_path, 3_000.0), (server_path, 1_000.0), (wrapper_path, 1_000.0)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")
        os.utime(path, (mtime, mtime))
    monkeypatch.setattr(module, "MCP_CORE_SOURCE_PATH", core_path)
    monkeypatch.setattr(module, "MCP_SERVER_SOURCE_PATH", server_path)
    monkeypatch.setenv("AOA_SESSION_MEMORY_MCP_AUTO_RELOAD", "0")

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text(
        "[mcp_servers.aoa_session_memory]\n"
        "command = \"aoa-session-memory-mcp-server\"\n"
        "cwd = \"/srv/AbyssOS\"\n",
        encoding="utf-8",
    )
    os.utime(config_path, (1_000.0, 1_000.0))
    monkeypatch.setenv("CODEX_HOME", codex_home.as_posix())

    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text("btime 1000\n", encoding="utf-8")
    ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
    current_pid = str(os.getpid())

    def write_process(pid: str, ppid: str, cmdline: list[str], start_epoch: float) -> None:
        process_dir = proc / pid
        process_dir.mkdir()
        process_dir.joinpath("cmdline").write_bytes(b"\0".join(part.encode("utf-8") for part in cmdline) + b"\0")
        process_dir.joinpath("status").write_text(f"Name:\tfixture\nPPid:\t{ppid}\n", encoding="utf-8")
        start_ticks = int((start_epoch - 1000.0) * float(ticks))
        fields = [pid, "(fixture)", "S", *(["0"] * 18), str(start_ticks)]
        process_dir.joinpath("stat").write_text(" ".join(fields), encoding="utf-8")

    write_process(current_pid, "200", ["python", "pytest"], 2_000.0)
    write_process("200", "1", ["/home/dionysus/.local/bin/codex", "resume"], 2_000.0)
    write_process("301", "200", ["/home/dionysus/.local/bin/aoa-session-memory-mcp-server"], 2_000.0)
    state = AoASessionMemoryMCPState(
        workspace_root=tmp_path,
        aoa_root=tmp_path / ".aoa",
        script_path=tmp_path / ".aoa/scripts/aoa_session_memory.py",
    )

    preflight = state.session_mcp_transport_preflight(proc_root=proc)

    assert preflight["ok"] is False
    assert preflight["core_auto_reload_enabled"] is False
    assert preflight["direct_tool_transport_status"] == "restart_required"
    assert preflight["live_transport_restart_advisory"] is True
    assert preflight["codex_session"]["current_session_predates_current_source"] is True
    assert preflight["running_mcp_processes"]["restart_advisory"] is True
    assert preflight["running_mcp_processes"]["processes"][0]["started_before_current_source"] is True


def test_usage_neighborhood_probe_uses_indexed_candidate_session() -> None:
    validator = load_validator_module()

    class ProbeState:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def session_entity_usage_neighborhood(self, anchor: str, **kwargs: object) -> dict:
            session = str(kwargs.get("session") or "")
            self.calls.append((anchor, session))
            if anchor == "view_image" and session == "route-session":
                return {"ok": True, "neighborhoods": [{"id": "window-1"}], "quality": {"neighborhood_count": 1}}
            return {"ok": True, "neighborhoods": [], "quality": {"neighborhood_count": 0}}

    state = ProbeState()

    anchor, session, neighborhood = validator._select_usage_neighborhood_probe(
        state,
        {"results": [{"session_label": "route-session"}]},
        {"results": [{"session_label": "goal-session"}]},
    )

    assert anchor == "view_image"
    assert session == "route-session"
    assert neighborhood["quality"]["neighborhood_count"] == 1
    assert state.calls == [("view_image", "route-session")]


def test_session_only_search_uses_local_fast_path_without_archive_search(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    search = state.session_search("", filters={"session": "session-1"}, limit=5)

    assert search["ok"] is True
    assert search["provider"]["status"] == "local_session_filter_fast_path"
    assert search["result_count"] == 1
    assert search["results"][0]["doc_type"] == "session"
    assert search["results"][0]["session_id"] == "session-1"
    assert search["results"][0]["refs"]["session"].endswith("session.manifest.json")
    assert "served by MCP local session filter fast path" in search["diagnostics"]
    assert not any(call[0] == "search" for call in runner.calls)


def test_published_tool_schema_allows_route_only_search_and_usage_neighborhood(tmp_path: Path) -> None:
    aoa = seed_archive(tmp_path)
    server = build_server(workspace_root=tmp_path, aoa_root=aoa, script_path=aoa / "scripts/aoa_session_memory.py")

    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    query_schema = tools["aoa_session_search"].inputSchema["properties"]["query"]
    assert query_schema["default"] == ""
    assert "aoa_session_literal_query_plan" in tools
    assert "aoa_session_agent_responses" in tools
    assert "aoa_session_agent_closeouts" in tools
    assert "aoa_session_agent_progress_updates" in tools
    assert "aoa_session_agent_reasoning_windows" in tools
    assert "aoa_session_task_episodes" in tools
    assert "aoa_session_goal_lifecycles" in tools
    assert "aoa_session_answer_neighborhood" in tools
    assert "aoa_session_entity_dossier" in tools
    assert "aoa_session_entity_usage_chain" in tools
    assert "aoa_session_entity_usage_neighborhood" in tools
    assert "aoa_session_hook_receipts" in tools
    assert "aoa_session_entity_inventory" in tools
    assert "aoa_session_entity_registry" in tools
    assert "aoa_session_live_scenario_audit" in tools
    assert "aoa_session_live_scenario_corpus_check" in tools
    assert "aoa_session_live_scenario_corpus_inventory" in tools
    assert "aoa_session_route_rollup_query" in tools
    assert "aoa_session_direct_event_rollup_query" in tools
    assert "aoa_session_projection_status" in tools
    assert "aoa_session_graph_neighborhood" in tools
    assert "aoa_session_graph_timeline" in tools
    assert "aoa_session_graph_shortest_path" in tools
    assert "aoa_session_graph_bridge" in tools
    assert "aoa_session_graph_cooccurrence" in tools
    assert tools["aoa_session_hook_receipts"].inputSchema["properties"]["event_name"]["default"] == "UserPromptSubmit"
    assert tools["aoa_session_entity_inventory"].inputSchema["properties"]["layer"]["default"] == "skill"
    assert tools["aoa_session_entity_registry"].inputSchema["properties"]["kind"]["default"] == "all"
    assert tools["aoa_session_live_scenario_audit"].inputSchema["properties"]["sample_size"]["default"] == 4
    assert tools["aoa_session_live_scenario_corpus_check"].inputSchema["properties"]["case_limit"]["default"] == 0
    assert tools["aoa_session_live_scenario_corpus_inventory"].inputSchema["properties"]["full"]["default"] is False
    assert tools["aoa_session_route_rollup_query"].inputSchema["properties"]["layer"]["default"] == "tool"
    assert tools["aoa_session_route_rollup_query"].inputSchema["properties"]["limit"]["default"] == 12
    assert tools["aoa_session_route_rollup_query"].inputSchema["properties"]["ref_limit"]["default"] == 3
    assert tools["aoa_session_direct_event_rollup_query"].inputSchema["properties"]["usage_role"]["default"] == "result"
    assert tools["aoa_session_direct_event_rollup_query"].inputSchema["properties"]["limit"]["default"] == 12
    assert tools["aoa_session_direct_event_rollup_query"].inputSchema["properties"]["ref_limit"]["default"] == 3
    assert tools["aoa_session_projection_status"].inputSchema["properties"]["include_payload"]["default"] is False
    assert tools["aoa_session_graph_neighborhood"].inputSchema["properties"]["edge_limit"]["default"] is None
    assert tools["aoa_session_entity_usage_chain"].inputSchema["properties"]["limit"]["default"] == 6
    assert tools["aoa_session_entity_usage_chain"].inputSchema["properties"]["per_route_limit"]["default"] == 12
    assert tools["aoa_session_entity_dossier"].inputSchema["properties"]["usage_limit"]["default"] == 4
    assert tools["aoa_session_entity_dossier"].inputSchema["properties"]["graph_edge_limit"]["default"] == 24
    literal_description = tools["aoa_session_literal_query_plan"].description or ""
    dossier_description = tools["aoa_session_entity_dossier"].description or ""
    usage_chain_description = tools["aoa_session_entity_usage_chain"].description or ""
    live_scenario_description = tools["aoa_session_live_scenario_audit"].description or ""
    corpus_inventory_description = tools["aoa_session_live_scenario_corpus_inventory"].description or ""
    route_rollup_description = tools["aoa_session_route_rollup_query"].description or ""
    direct_event_rollup_description = tools["aoa_session_direct_event_rollup_query"].description or ""
    graph_description = tools["aoa_session_graph_neighborhood"].description or ""
    bridge_description = tools["aoa_session_graph_bridge"].description or ""
    assert "literal skill/MCP/hook/tool/API/path/query" in literal_description
    assert "one compact registry, usage, consequence" in dossier_description
    assert "usage-to-consequence chains" in usage_chain_description
    assert "entity registry lookup status probes" in live_scenario_description
    assert "without running them" in corpus_inventory_description
    assert "without maintenance" in route_rollup_description
    assert "without shard resampling" in direct_event_rollup_description
    assert "graph route neighborhood" in graph_description
    assert "skill, MCP, hook, tool" in graph_description
    assert "compact bridge packet" in bridge_description
    assert tools["aoa_session_goal_lifecycles"].inputSchema["properties"]["target"]["default"] == "all"
    goal_order_schema = tools["aoa_session_goal_lifecycles"].inputSchema["properties"]["order"]
    assert goal_order_schema["default"] == "recent"
    rendered_goal_order_schema = json.dumps(goal_order_schema, sort_keys=True)
    assert "recent" in rendered_goal_order_schema
    assert "chronological" in rendered_goal_order_schema


def test_stdio_server_round_trips_tool_call_against_fixture_archive(tmp_path: Path) -> None:
    aoa = seed_archive(tmp_path)
    server_script = Path(__file__).resolve().parents[1] / "scripts" / "aoa_session_memory_mcp_server.py"

    async def run_smoke() -> dict[str, object]:
        env = {
            **os.environ,
            "AOA_WORKSPACE_ROOT": tmp_path.as_posix(),
            "AOA_SESSION_MEMORY_ROOT": aoa.as_posix(),
            "AOA_SESSION_MEMORY_SCRIPT": (aoa / "scripts" / "aoa_session_memory.py").as_posix(),
            "AOA_SESSION_MEMORY_MCP_TIMEOUT": "2",
        }
        params = StdioServerParameters(
            command=sys.executable,
            args=[server_script.as_posix()],
            cwd=Path(__file__).resolve().parents[4].as_posix(),
            env=env,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = {tool.name for tool in (await session.list_tools()).tools}
                result = await session.call_tool(
                    "aoa_session_entity_inventory",
                    {"layer": "skill", "session": "latest", "limit": 3, "sample_limit": 0},
                    read_timeout_seconds=timedelta(seconds=5),
                )
        assert not result.isError
        payload = json.loads(result.content[0].text)
        return {"tools": tools, "payload": payload}

    smoke = asyncio.run(run_smoke())

    assert "aoa_session_entity_inventory" in smoke["tools"]
    assert smoke["payload"]["ok"] is True
    assert smoke["payload"]["entities"][0]["key"] == "aoa_decision"


def test_entity_inventory_prefers_atlas_and_falls_back_to_route_terms(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    skill_inventory = state.session_entity_inventory(layer="skill", limit=5)
    latest_skill_inventory = state.session_entity_inventory(layer="skill", session="latest", limit=5)
    explicit_skill_inventory = state.session_entity_inventory(layer="skill", session="session-1", limit=5)
    mcp_inventory = state.session_entity_inventory(layer="mcp", limit=5)
    mcp_service_inventory = state.session_entity_inventory(layer="mcp_service", limit=5)
    eval_inventory = state.session_entity_inventory(layer="eval", limit=5)
    git_inventory = state.session_entity_inventory(layer="git", limit=5)
    playbook_inventory = state.session_entity_inventory(layer="playbook", limit=5)
    technique_inventory = state.session_entity_inventory(layer="technique", limit=5)
    mechanic_inventory = state.session_entity_inventory(layer="mechanic", limit=5)

    assert skill_inventory["truth_status"] == "session route-signal inventory; not runtime installed inventory"
    assert skill_inventory["source"] == "atlas"
    assert skill_inventory["mcp_access"]["read_only_inventory_route"] is True
    assert skill_inventory["mcp_access"]["runtime_reload_required"] is False
    assert skill_inventory["runtime"]["source_matches_loaded"] is True
    assert skill_inventory["runtime"]["reload_required"] is False
    assert skill_inventory["provider"]["providers"]["portable_sqlite"]["freshness"]["status"] == "current"
    assert skill_inventory["entities"][0]["key"] == "aoa_decision"
    assert skill_inventory["entities"][0]["signal_count"] == 4
    assert skill_inventory["entities"][0]["latest_session_date"] == "2026-05-26"
    assert skill_inventory["entities"][0]["samples"][0]["doc_type"] == "atlas_entry"
    assert skill_inventory["entities"][0]["samples"][0]["session_date"] == "2026-05-26"
    assert skill_inventory["entities"][0]["samples"][0]["refs"]["raw"] == "raw:line:2"
    assert "segment_index" not in skill_inventory["entities"][0]["samples"][0]["refs"]
    assert skill_inventory["route_packet"]["bounded"] is True
    assert skill_inventory["route_packet"]["axis"] == "by-skill"
    assert skill_inventory["route_packet"]["sample_refs"][0]["raw"] == "raw:line:2"
    assert skill_inventory["response_profile"]["sample_shape"] == "compact_refs_only"
    assert skill_inventory["next_expansion"]["mcp_tool"] == "aoa_session_route"
    assert latest_skill_inventory["entities"][0]["key"] == "aoa_decision"
    assert explicit_skill_inventory["entities"][0]["key"] == "aoa_decision"
    assert mcp_inventory["source"] == "atlas"
    assert mcp_inventory["requested_layer"] == "mcp"
    assert mcp_inventory["normalized_layer"] == "mcp"
    assert mcp_inventory["entities"][0]["key"] == "aoa_session_memory_mcp"
    assert mcp_inventory["entities"][0]["latest_session_date"] == "2026-05-26"
    assert mcp_service_inventory["layer"] == "mcp"
    assert mcp_service_inventory["requested_layer"] == "mcp_service"
    assert mcp_service_inventory["normalized_layer"] == "mcp"
    assert mcp_service_inventory["source"] == "atlas"
    assert mcp_service_inventory["entities"] == mcp_inventory["entities"]
    assert eval_inventory["source"] == "portable_sqlite"
    assert eval_inventory["provider"]["providers"]["portable_sqlite"]["freshness"]["status"] == "current"
    assert eval_inventory["entities"][0]["key"] == "inspect_ai"
    assert git_inventory["entities"][0]["key"] == "git"
    assert playbook_inventory["entities"][0]["key"] == "session_audit"
    assert technique_inventory["entities"][0]["key"] == "entity_routing"
    assert mechanic_inventory["entities"][0]["key"] == "route_maintenance"
    provider_calls = [args for command, args in runner.calls if command == "search-provider-status"]
    assert provider_calls
    assert all("--provider" in args for args in provider_calls)


def test_entity_inventory_keeps_wide_atlas_response_bounded(tmp_path: Path) -> None:
    aoa = seed_archive(tmp_path)
    index_path = aoa / "maps/by-skill/index.json"
    entries = []
    long_label = "2026-06-14__999__" + "long-session-title-" * 12
    long_path_prefix = (aoa / "maps/by-skill/entries" / ("deep-" * 20)).as_posix()
    for entity_idx in range(8):
        for sample_idx in range(3):
            entries.append(
                {
                    "axis": "by-skill",
                    "route_key": f"aoa_session_memory_skill_{entity_idx}",
                    "session": f"{long_label}-{entity_idx}-{sample_idx}",
                    "session_id": f"session-{entity_idx}-{sample_idx}",
                    "confidence": "medium",
                    "signal_count": 100 - entity_idx,
                    "json": f"{long_path_prefix}/aoa_session_memory_skill_{entity_idx}_{sample_idx}.json",
                    "markdown": f"{long_path_prefix}/aoa_session_memory_skill_{entity_idx}_{sample_idx}.md",
                    "title": "wide inventory title " + ("with repeated context " * 30),
                    "evidence": {
                        "session_ref": f"/srv/AbyssOS/.aoa/sessions/{long_label}/SESSION.md",
                        "raw_ref": f"raw:line:{1000 + entity_idx * 10 + sample_idx}",
                        "segment_ref": f"999__compaction-to-compaction.md#event-{entity_idx:06d}{sample_idx}",
                        "generated_index_ref": f"/srv/AbyssOS/.aoa/sessions/{long_label}/segments/999__compaction-to-compaction.index.json",
                    },
                }
            )
    write_json(
        index_path,
        {
            "schema_version": 1,
            "artifact_type": "atlas_axis_index",
            "generated_at": "2026-06-14T00:00:00Z",
            "axis": "by-skill",
            "entry_count": len(entries),
            "entries": entries,
        },
    )
    state = AoASessionMemoryMCPState.discover(
        workspace_root=tmp_path,
        aoa_root=aoa,
        script_path=aoa / "scripts/aoa_session_memory.py",
        command_runner=FakeRunner(),
        timeout_seconds=2,
    )

    inventory = state.session_entity_inventory(layer="skill", query="aoa-session-memory", limit=8, sample_limit=3)
    serialized = json.dumps(inventory, ensure_ascii=False)

    assert inventory["ok"] is True
    assert inventory["entity_count"] == 8
    assert inventory["route_packet"]["bounded"] is True
    assert inventory["route_packet"]["sample_ref_count"] == 8
    assert inventory["response_profile"]["sample_count"] == 12
    assert inventory["response_profile"]["sample_omitted_count"] == 12
    assert inventory["next_expansion"]["arguments"]["axis"] == "by-skill"
    assert len(serialized) < 18000
    for entity in inventory["entities"]:
        for sample in entity["samples"]:
            assert "doc_id" not in sample
            assert "segment_index" not in sample["refs"]
            assert "atlas_entry" not in sample["refs"]
            assert "title" not in sample


def test_entity_inventory_reports_runtime_reload_boundary(tmp_path: Path, monkeypatch: Any) -> None:
    module = sys.modules[AoASessionMemoryMCPState.__module__]
    state = state_with_fixture(tmp_path, FakeRunner())

    monkeypatch.setattr(module, "MCP_CORE_LOADED_SHA256", "stale-loaded-code")

    inventory = state.session_entity_inventory(layer="skill", limit=5)

    assert inventory["runtime"]["source_matches_loaded"] is False
    assert inventory["runtime"]["reload_required"] is True
    assert inventory["mcp_access"]["runtime_reload_required"] is True


def test_entity_registry_reads_generated_snapshot_without_archive_command(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    registry = state.session_entity_registry(kind="skill", lookup="aoa-decision", limit=5)
    resource = state.read_resource("aoa-session-memory://entity-lookup/skill/aoa-decision")

    assert registry["artifact_type"] == "entity_registry_snapshot"
    assert registry["entries"][0]["canonical_key"] == "aoa_decision"
    assert registry["source"] == "generated_entity_registry_snapshot"
    assert registry["mcp_access"]["read_only_registry_route"] is True
    assert registry["mcp_access"]["archive_command"] is None
    assert registry["mcp_access"]["write_requires_operator_outside_mcp"] is True
    registry_calls = [args for command, args in runner.calls if command == "entity-registry"]
    assert registry_calls == []
    assert resource["entries"][0]["kind"] == "skill"


def test_entity_registry_preserves_generated_snapshot_failure_status(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)
    registry_path = state.aoa_root / "maps/entity-registry.json"
    snapshot = json.loads(registry_path.read_text(encoding="utf-8"))
    snapshot["ok"] = False
    snapshot["diagnostics"] = ["generated_entity_registry_stale"]
    registry_path.write_text(json.dumps(snapshot), encoding="utf-8")

    registry = state.session_entity_registry(kind="skill", lookup="aoa-decision", limit=5)

    assert registry["ok"] is False
    assert registry["diagnostics"] == ["generated_entity_registry_stale"]
    assert registry["entries"][0]["canonical_key"] == "aoa_decision"


def test_entity_inventory_resolves_relative_atlas_detail_json(tmp_path: Path) -> None:
    aoa = seed_archive(tmp_path)
    index_path = aoa / "maps/by-skill/index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["entries"][0]["json"] = "aoa_decision__session.json"
    write_json(index_path, index)
    state = AoASessionMemoryMCPState.discover(
        workspace_root=tmp_path,
        aoa_root=aoa,
        script_path=aoa / "scripts/aoa_session_memory.py",
        command_runner=FakeRunner(),
        timeout_seconds=2,
    )

    skill_inventory = state.session_entity_inventory(layer="skill", limit=5)

    assert skill_inventory["source"] == "atlas"
    assert skill_inventory["entities"][0]["key"] == "aoa_decision"
    assert skill_inventory["entities"][0]["signal_count"] == 4


def test_freshness_check_resolves_raw_line_refs_with_session_context(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    missing_context = state.session_freshness_check(["raw:line:2"])
    with_context = state.session_freshness_check(["raw:line:2", "raw:line:3"], session="session-1")

    assert missing_context["checks"][0]["status"] == "needs_session_context"
    assert with_context["checks"][0]["status"] == "present"
    assert with_context["checks"][0]["line"] == 2
    assert with_context["checks"][1]["status"] == "missing"
    assert with_context["checks"][1]["line_count"] == 2
    freshness_calls = [args for command, args in runner.calls if command == "search-provider-status"]
    assert "--session" not in freshness_calls[0]
    assert freshness_calls[1][freshness_calls[1].index("--session") + 1] == "2026-05-26__001__session-memory-mcp"
    assert [timeout for command, timeout in runner.timeouts if command == "search-provider-status"] == [60.0, 60.0]


def test_freshness_check_resolves_latest_before_provider_scope(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    freshness = state.session_freshness_check(["raw:line:1"], session="latest")

    freshness_calls = [args for command, args in runner.calls if command == "search-provider-status"]
    assert freshness["checks"][0]["status"] == "present"
    assert freshness_calls[0][freshness_calls[0].index("--session") + 1] == "2026-05-26__001__session-memory-mcp"
    assert "latest" not in freshness_calls[0]


def test_freshness_check_falls_back_to_global_provider_when_session_scope_times_out(tmp_path: Path) -> None:
    runner = SessionProviderTimeoutRunner()
    state = state_with_fixture(tmp_path, runner)

    freshness = state.session_freshness_check(["raw:line:1"], session="session-1")

    freshness_calls = [args for command, args in runner.calls if command == "search-provider-status"]
    assert len(freshness_calls) == 2
    assert "--session" in freshness_calls[0]
    assert "--session" not in freshness_calls[1]
    assert freshness["ok"] is True
    assert freshness["checks"][0]["status"] == "present"
    assert freshness["projection_freshness"]["status"] == "current"
    assert "provider_session_status_failed_using_global_freshness" in freshness["diagnostics"]
    assert freshness["session_provider_fallback"]["ok"] is False
    assert freshness["session_provider_fallback"]["mcp_access"]["archive_command"] == "search-provider-status"


def test_freshness_check_keeps_session_provider_selector_failures_authoritative(tmp_path: Path) -> None:
    runner = SessionProviderSelectorErrorRunner()
    state = state_with_fixture(tmp_path, runner)

    freshness = state.session_freshness_check(["raw:line:1"], session="bogus")

    freshness_calls = [args for command, args in runner.calls if command == "search-provider-status"]
    assert len(freshness_calls) == 1
    assert "--session" in freshness_calls[0]
    assert freshness["ok"] is False
    assert freshness["checks"][0]["status"] == "needs_session_context"
    assert freshness["provider"]["ok"] is False
    assert freshness["provider"]["providers"]["portable_sqlite"]["status"] == "invalid_session"
    assert freshness["session_provider_fallback"] is None
    assert "provider_session_status_failed_authoritative" in freshness["diagnostics"]


def test_freshness_check_rejects_relative_refs_that_escape_aoa_root(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)
    outside_ref = tmp_path / "outside-evidence.json"
    outside_ref.write_text("{}", encoding="utf-8")

    freshness = state.session_freshness_check(["../outside-evidence.json"])
    check = freshness["checks"][0]

    assert freshness["ok"] is False
    assert check["status"] == "invalid"
    assert check["inside_aoa_root"] is False
    assert check["path"] == outside_ref.resolve().as_posix()

    absolute_freshness = state.session_freshness_check([outside_ref.as_posix()])
    absolute_check = absolute_freshness["checks"][0]

    assert absolute_freshness["ok"] is False
    assert absolute_check["status"] == "present"
    assert absolute_check["inside_aoa_root"] is False


def test_freshness_check_keeps_target_refs_ok_when_unrelated_session_is_stale(tmp_path: Path) -> None:
    runner = StaleProviderRunner(dirty_session_id="session-other", dirty_session_label="2026-05-26__002__other")
    state = state_with_fixture(tmp_path, runner)

    freshness = state.session_freshness_check(["raw:line:1"], session="session-1")
    provider_freshness = freshness["provider"]["providers"]["portable_sqlite"]["freshness"]

    assert freshness["ok"] is True
    assert freshness["provider"]["ok"] is False
    assert "dirty_session_ids" not in provider_freshness
    assert "dirty_sessions" not in provider_freshness
    assert provider_freshness["dirty_session_count"] == 1
    assert provider_freshness["dirty_session_samples"][0]["session_id"] == "session-other"
    assert provider_freshness["omitted_fields"] == ["dirty_session_ids", "dirty_sessions"]
    assert freshness["provider"]["mcp_access"]["response_compacted"] is True
    full_freshness_route = freshness["provider"]["mcp_access"]["full_freshness_route"]
    assert tmp_path.as_posix() in full_freshness_route
    assert (tmp_path / ".aoa").as_posix() in full_freshness_route
    assert (tmp_path / ".aoa/scripts/aoa_session_memory.py").as_posix() in full_freshness_route
    assert "/srv/AbyssOS/.aoa" not in full_freshness_route
    assert freshness["projection_freshness"]["status"] == "current_with_global_stale"
    assert "provider_global_stale_target_session_current" in freshness["diagnostics"]


def test_freshness_check_marks_target_live_deferred_without_failing(tmp_path: Path) -> None:
    runner = LiveDeferredProviderRunner(
        dirty_session_id="session-1",
        dirty_session_label="2026-05-26__001__session-memory-mcp",
    )
    state = state_with_fixture(tmp_path, runner)

    freshness = state.session_freshness_check(["raw:line:1"], session="session-1")
    provider_freshness = freshness["provider"]["providers"]["portable_sqlite"]["freshness"]

    assert freshness["ok"] is True
    assert freshness["provider"]["ok"] is True
    assert freshness["provider"]["providers"]["portable_sqlite"]["status"] == "ready_with_deferred_live_updates"
    assert provider_freshness["status"] == "current_with_deferred_live_updates"
    assert provider_freshness["dirty_session_count"] == 1
    assert provider_freshness["actionable_dirty_session_count"] == 0
    assert provider_freshness["deferred_live_session_count"] == 1
    assert provider_freshness["deferred_live_session_samples"][0]["session_id"] == "session-1"
    assert "deferred_live_sessions" in provider_freshness["omitted_fields"]
    assert freshness["projection_freshness"]["status"] == "current_with_deferred_live_updates"
    assert freshness["projection_freshness"]["target_dirty"] is False
    assert freshness["projection_freshness"]["target_deferred_live"] is True
    assert "provider_target_session_deferred_live_update" in freshness["diagnostics"]


def test_freshness_check_fails_when_target_session_projection_is_stale(tmp_path: Path) -> None:
    runner = StaleProviderRunner(
        dirty_session_id="session-1",
        dirty_session_label="2026-05-26__001__session-memory-mcp",
    )
    state = state_with_fixture(tmp_path, runner)

    freshness = state.session_freshness_check(["raw:line:1"], session="session-1")

    assert freshness["ok"] is False
    assert freshness["projection_freshness"]["status"] == "stale"
    assert freshness["projection_freshness"]["target_dirty"] is True


def test_hook_receipts_are_first_class_session_evidence(tmp_path: Path) -> None:
    state = state_with_fixture(tmp_path)

    receipts = state.session_hook_receipts(event_name="UserPromptSubmit", session="session-1", limit=10)
    errors = state.session_hook_receipts(event_name="UserPromptSubmit", session="session-1", only_errors=True)

    assert receipts["schema"] == "aoa_session_memory_hook_receipts_v1"
    assert receipts["ok"] is True
    assert receipts["total_receipt_count"] == 2
    assert receipts["date_semantics"]["filter_basis"] == "hook_receipt_timestamp"
    assert receipts["date_semantics"]["timestamp_fields"] == ["timestamp", "received_at", "generated_at"]
    assert receipts["date_semantics"]["not_session_date"] is True
    assert receipts["summary"]["error_receipt_count"] == 1
    assert receipts["summary"]["typing_bridge_failure_count"] == 1
    assert receipts["summary"]["action_counts"][0]["key"] == "hook_event_recorded"
    assert receipts["receipts"][0]["timestamp"] == "2026-05-26T00:02:00Z"
    assert receipts["receipts"][0]["typing_bridge"]["ok"] is False
    assert receipts["receipts"][0]["refs"]["receipt"].endswith("hooks/receipts.jsonl#L2")
    assert "prompt" not in receipts["receipts"][0]
    assert errors["total_receipt_count"] == 1

    freshness = state.session_freshness_check([receipts["receipts"][0]["refs"]["receipt"]])
    assert freshness["checks"][0]["status"] == "present"


def test_entity_usage_audit_routes_to_allowlisted_archive_command(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    audit = state.session_entity_usage_audit(
        "aoa-session-memory-mcp",
        kind="mcp",
        limit=5,
        per_route_limit=4,
        consequence_window=3,
        document_limit=12,
    )

    assert audit["artifact_type"] == "session_memory_entity_usage_audit"
    assert audit["usage_event_count"] == 1
    assert audit["document_refs"][0]["kind"] == "mentioned_path"
    usage_calls = [call for call in runner.calls if call[0] == "entity-usage-audit"]
    assert len(usage_calls) == 1
    args = usage_calls[0][1]
    assert args[0] == "aoa-session-memory-mcp"
    assert args[args.index("--kind") + 1] == "mcp"
    assert args[args.index("--per-route-limit") + 1] == "4"
    assert args[args.index("--consequence-window") + 1] == "3"
    assert "--full" in args
    assert runner.timeouts[-1] == ("entity-usage-audit", 90.0)

    agent_event_audit = state.session_entity_usage_audit(
        "assistant_answer",
        kind="agent_event",
        limit=2,
        per_route_limit=2,
    )
    assert agent_event_audit["artifact_type"] == "session_memory_entity_usage_audit"
    agent_event_call = [call for call in runner.calls if call[0] == "entity-usage-audit"][-1]
    agent_event_args = agent_event_call[1]
    assert agent_event_args[0] == "assistant_answer"
    assert agent_event_args[agent_event_args.index("--kind") + 1] == "agent_event"

    receipt_audit = state.session_entity_usage_audit("userpromptsubmit", kind="receipt", limit=2)
    error_audit = state.session_entity_usage_audit("test_failure", kind="error", limit=2)
    owner_route_audit = state.session_entity_usage_audit("abyss_stack", kind="owner_route", limit=2)
    next_action_audit = state.session_entity_usage_audit("repair", kind="route_next_action", limit=2)

    assert receipt_audit["artifact_type"] == "session_memory_entity_usage_audit"
    assert error_audit["artifact_type"] == "session_memory_entity_usage_audit"
    assert owner_route_audit["artifact_type"] == "session_memory_entity_usage_audit"
    assert next_action_audit["artifact_type"] == "session_memory_entity_usage_audit"
    recent_usage_calls = [call for call in runner.calls if call[0] == "entity-usage-audit"][-4:]
    assert [call[1][call[1].index("--kind") + 1] for call in recent_usage_calls] == [
        "receipt",
        "error",
        "owner_route",
        "route_next_action",
    ]


def test_entity_usage_chain_routes_to_allowlisted_archive_command(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    chain = state.session_entity_usage_chain(
        "aoa-session-memory-mcp",
        kind="mcp_service",
        limit=5,
        per_route_limit=7,
        consequence_window=4,
        document_limit=9,
        session="session-1",
    )

    assert chain["artifact_type"] == "session_memory_entity_usage_chain"
    assert chain["kind"] == "mcp"
    assert chain["requested_kind"] == "mcp_service"
    assert chain["counts"]["usage_event_count"] == 1
    assert chain["quality"]["skipped_graph_rag_packet"] is True
    assert chain["mcp_access"]["response_compacted"] is True
    assert "full_evidence_route" in chain["mcp_access"]
    usage_calls = [call for call in runner.calls if call[0] == "usage-chain"]
    assert len(usage_calls) == 1
    args = usage_calls[0][1]
    assert args[0] == "aoa-session-memory-mcp"
    assert args[args.index("--kind") + 1] == "mcp"
    assert args[args.index("--limit") + 1] == "5"
    assert args[args.index("--per-route-limit") + 1] == "7"
    assert args[args.index("--consequence-window") + 1] == "4"
    assert args[args.index("--document-limit") + 1] == "9"
    assert args[args.index("--session") + 1] == "session-1"
    assert runner.timeouts[-1] == ("usage-chain", 90.0)


def test_entity_dossier_composes_first_route_packet(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)
    registry_path = state.aoa_root / "maps/entity-registry.json"
    registry_snapshot = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_snapshot["counts_by_kind"]["graph"] = 5
    write_json(registry_path, registry_snapshot)

    dossier = state.session_entity_dossier(
        "aoa-session-memory-mcp",
        kind="mcp_service",
        usage_limit=2,
        neighborhood_limit=1,
        graph_limit=6,
        graph_edge_limit=6,
    )

    assert dossier["artifact_type"] == "session_memory_entity_dossier"
    assert dossier["ok"] is True
    assert dossier["kind"] == "mcp"
    assert dossier["requested_kind"] == "mcp_service"
    assert dossier["normalized_entity"]["route_signal"] == "mcp:aoa_session_memory_mcp"
    assert dossier["source_identity"]["entry"]["entity_id"] == "mcp:aoa_session_memory_mcp"
    assert dossier["usage"]["usage_event_count"] == 1
    assert dossier["consequence_chain"]["usage_consequence_event_count"] == 1
    assert dossier["neighborhood"]["window_count"] == 1
    assert dossier["graph_neighborhood"]["node_count"] == 3
    assert dossier["evidence"]["raw_or_segment_ref_present"] is True
    assert not any(isinstance(ref.get("graph"), int) for ref in dossier["evidence"]["refs"])
    assert dossier["quality"]["one_short_route"] is True
    assert dossier["quality"]["source_identity_present"] is True
    assert "source_identity_not_found_in_generated_entity_registry" not in dossier["noise_flags"]
    assert dossier["mcp_access"]["read_only_composite_route"] is True
    assert dossier["mcp_access"]["source_tools"] == [
        "aoa_session_entity_registry",
        "aoa_session_entity_usage_audit",
        "aoa_session_entity_usage_neighborhood",
        "aoa_session_graph_neighborhood",
    ]
    next_ids = {item["id"] for item in dossier["next_expansion"]}
    assert {"full_usage_audit", "usage_neighborhood", "graph_neighborhood", "source_identity"} <= next_ids
    assert dossier["next_expansion_command"]
    commands = [command for command, _args in runner.calls]
    assert "entity-usage-audit" in commands
    assert "entity-usage-neighborhood" in commands
    assert "graph-neighborhood" in commands


def test_entity_dossier_keeps_usage_neighborhood_fallback_expansion_command(tmp_path: Path) -> None:
    class TimeoutUsageNeighborhoodRunner(FakeRunner):
        def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
            command = argv[2]
            if command == "entity-usage-neighborhood":
                self.calls.append((command, tuple(argv[3:])))
                self.timeouts.append((command, timeout))
                payload = {
                    "schema_version": 1,
                    "artifact_type": "session_memory_entity_usage_neighborhood",
                    "ok": False,
                    "diagnostics": ["fixture timeout"],
                    "mcp_access": {"archive_command": "entity-usage-neighborhood"},
                }
                return CommandOutput(argv, 124, json.dumps(payload), "command timed out", timeout * 1000)
            return super().__call__(argv, timeout)

    runner = TimeoutUsageNeighborhoodRunner()
    state = state_with_fixture(tmp_path, runner)

    dossier = state.session_entity_dossier(
        "aoa-session-memory-mcp",
        kind="mcp",
        usage_limit=2,
        neighborhood_limit=1,
        graph_limit=6,
        graph_edge_limit=6,
    )

    expansion = next(item for item in dossier["next_expansion"] if item["id"] == "usage_neighborhood")
    assert "entity-usage-neighborhood" in expansion["command"]
    assert dossier["neighborhood"]["next_expansion_command"] == expansion["command"]
    assert dossier["neighborhood"]["fallback_reason"] == "archive_route_unavailable"


def test_entity_usage_neighborhood_routes_to_allowlisted_archive_command(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    neighborhood = state.session_entity_usage_neighborhood(
        "aoa-session-memory-mcp",
        kind="mcp",
        limit=3,
        per_route_limit=4,
        before=2,
        after=5,
        raw_preview_chars=320,
        document_limit=12,
    )

    assert neighborhood["artifact_type"] == "session_memory_entity_usage_neighborhood"
    assert neighborhood["quality"]["consequence_present"] is True
    assert neighborhood["neighborhoods"][0]["source_usage_event"]["raw_preview"]["status"] == "available"
    usage_calls = [call for call in runner.calls if call[0] == "entity-usage-neighborhood"]
    assert len(usage_calls) == 1
    args = usage_calls[0][1]
    assert args[0] == "aoa-session-memory-mcp"
    assert args[args.index("--kind") + 1] == "mcp"
    assert args[args.index("--before") + 1] == "2"
    assert args[args.index("--after") + 1] == "5"
    assert args[args.index("--raw-preview-chars") + 1] == "320"
    assert "--full" in args
    assert runner.timeouts[-1] == ("entity-usage-neighborhood", 10.0)


def test_entity_usage_neighborhood_light_probe_uses_search_fast_path(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    neighborhood = state.session_entity_usage_neighborhood(
        "aoa-session-memory-mcp",
        kind="mcp",
        limit=1,
        per_route_limit=1,
        raw_preview_chars=0,
        document_limit=3,
    )

    assert neighborhood["ok"] is True
    assert neighborhood["quality"]["fast_path"] is True
    assert neighborhood["quality"]["usage_neighborhood_present"] is False
    assert neighborhood["quality"]["usage_refs_present"] is True
    assert neighborhood["quality"]["consequence_present"] is None
    assert neighborhood["quality"]["consequence_evaluated"] is False
    assert neighborhood["quality"]["consequence_status"] == "not_loaded_fast_path"
    assert neighborhood["neighborhoods"][0]["source"] == "mcp_search_route_signal_fast_path"
    assert neighborhood["neighborhoods"][0]["source_usage_event"]["event_id"] == "000001"
    assert neighborhood["mcp_access"]["archive_command"] is None
    assert neighborhood["mcp_access"]["selected_route_signal"] == "mcp:aoa_session_memory_mcp"
    assert not [call for call in runner.calls if call[0] == "entity-usage-neighborhood"]
    search_calls = [call for call in runner.calls if call[0] == "search"]
    assert search_calls
    assert search_calls[0][1][search_calls[0][1].index("--route-signal") + 1] == "mcp:aoa_session_memory_mcp"
    assert "--use-shards" not in search_calls[0][1]


def test_usage_route_signal_candidates_strip_registry_anchor_prefix(tmp_path: Path) -> None:
    state = state_with_fixture(tmp_path)

    mcp_candidates = state._usage_route_signal_candidates(
        kind="mcp_service",
        anchor="mcp_service:aoa_decisions_mcp",
    )
    tool_candidates = state._usage_route_signal_candidates(
        kind="mcp_tool",
        anchor="mcp_tool:session_search",
    )

    assert "mcp:aoa_decisions_mcp" in mcp_candidates
    assert "tool:session_search" in tool_candidates


def test_entity_usage_neighborhood_falls_back_to_search_when_archive_route_times_out(tmp_path: Path) -> None:
    class TimeoutUsageRunner(FakeRunner):
        def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
            command = argv[2]
            if command == "entity-usage-neighborhood":
                self.calls.append((command, tuple(argv[3:])))
                self.timeouts.append((command, timeout))
                return CommandOutput(argv, 124, "", "command timed out", timeout * 1000)
            return super().__call__(argv, timeout)

    runner = TimeoutUsageRunner()
    state = state_with_fixture(tmp_path, runner)

    neighborhood = state.session_entity_usage_neighborhood(
        "aoa-session-memory-mcp",
        kind="mcp",
        limit=3,
        per_route_limit=4,
        raw_preview_chars=320,
        document_limit=12,
    )

    assert neighborhood["ok"] is True
    assert neighborhood["quality"]["fast_path"] is True
    assert neighborhood["quality"]["usage_neighborhood_present"] is False
    assert neighborhood["quality"]["consequence_present"] is None
    assert neighborhood["quality"]["consequence_status"] == "not_loaded_fast_path"
    assert neighborhood["mcp_access"]["fallback_reason"] == "archive_route_unavailable"
    assert neighborhood["mcp_access"]["fallback_from"]["returncode"] == 124
    assert neighborhood["mcp_access"]["selected_route_signal"] == "mcp:aoa_session_memory_mcp"
    assert runner.timeouts[0] == ("entity-usage-neighborhood", 10.0)


def test_entity_usage_audit_compacts_heavy_archive_payload_for_mcp(tmp_path: Path) -> None:
    class HeavyUsageRunner(FakeRunner):
        def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
            command = argv[2]
            if command != "entity-usage-audit":
                return super().__call__(argv, timeout)
            self.calls.append((command, tuple(argv[3:])))
            self.timeouts.append((command, timeout))
            long_text = "raw evidence " * 120
            payload = {
                "schema_version": 1,
                "artifact_type": "session_memory_entity_usage_audit",
                "ok": True,
                "anchor": "aoa-session-memory-mcp",
                "kind": "mcp",
                "usage_event_count": 20,
                "consequence_event_count": 20,
                "usage_events": [
                    {
                        "event_id": f"{idx:06d}",
                        "event_type": "TOOL_CALL",
                        "title": long_text,
                        "snippet": long_text,
                        "content": long_text,
                        "refs": {
                            "raw": f"raw:line:{idx}",
                            "segment": f"000__initial-to-latest.md#event-{idx:06d}",
                            "expanded_context": long_text,
                        },
                    }
                    for idx in range(20)
                ],
                "consequence_events": [
                    {
                        "event_id": f"c{idx:06d}",
                        "event_type": "ASSISTANT_MESSAGE",
                        "title": long_text,
                        "content": long_text,
                    }
                    for idx in range(20)
                ],
                "document_refs": [
                    {"kind": "mentioned_path", "value": f"docs/{idx}.md", "preview": long_text}
                    for idx in range(20)
                ],
            }
            return CommandOutput(argv, 0, json.dumps(payload), "", 1.0)

    state = state_with_fixture(tmp_path, HeavyUsageRunner())

    audit = state.session_entity_usage_audit("aoa-session-memory-mcp", kind="mcp", limit=20)
    encoded = json.dumps(audit)

    assert audit["mcp_payload_policy"]["response_compacted"] is True
    assert audit["mcp_payload_policy"]["full_evidence_route"]
    assert audit["mcp_access"]["response_compacted"] is True
    assert audit["usage_event_count"] == 20
    assert len(audit["usage_events"]) == 4
    assert audit["omitted_usage_event_count"] == 16
    assert len(audit["consequence_events"]) == 3
    assert len(audit["document_refs"]) == 2
    assert "content" not in audit["usage_events"][0]
    assert len(audit["usage_events"][0]["title"]) <= 80
    assert "omitted_field_count" not in encoded
    assert len(encoded) < 5500
    assert ("raw evidence " * 20) not in encoded


def test_entity_usage_chain_compacts_heavy_archive_payload_for_mcp(tmp_path: Path) -> None:
    class HeavyChainRunner(FakeRunner):
        def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
            command = argv[2]
            if command != "usage-chain":
                return super().__call__(argv, timeout)
            self.calls.append((command, tuple(argv[3:])))
            self.timeouts.append((command, timeout))
            long_text = "chain raw evidence " * 120
            payload = {
                "schema_version": 1,
                "artifact_type": "session_memory_entity_usage_chain",
                "ok": True,
                "anchor": "aoa-session-memory-mcp",
                "kind": "mcp",
                "counts": {
                    "usage_event_count": 10,
                    "consequence_event_count": 10,
                    "chain_count": 10,
                    "chain_with_result_or_consequence_count": 10,
                },
                "quality": {
                    "direct_usage_present": True,
                    "result_or_consequence_present": True,
                    "raw_or_segment_ref_present": True,
                    "skipped_graph_rag_packet": True,
                    "noise_flag_count": 0,
                },
                "first_ref": {
                    "raw": "raw:line:0",
                    "raw_block": "raw:block:0-4",
                    "segment": "000.md#event-000000",
                    "segment_index": "000.md",
                    "session": "session:000",
                    "content": long_text,
                },
                "usage_chain": {
                    "chains": [
                        {
                            "usage_event": {
                                "event_id": f"{idx:06d}",
                                "event_type": "TOOL_CALL",
                                "title": long_text,
                                "snippet": long_text,
                                "content": long_text,
                                "refs": {"raw": f"raw:line:{idx}", "segment": f"000.md#event-{idx:06d}"},
                            },
                            "result_or_consequence_events": [
                                {
                                    "event_id": f"c{idx:06d}",
                                    "event_type": "COMMAND_OUTPUT",
                                    "title": long_text,
                                    "content": long_text,
                                    "refs": {"raw": f"raw:line:{idx + 100}", "segment": f"000.md#event-c{idx:06d}"},
                                }
                                for _ in range(4)
                            ],
                            "result_or_consequence_count": 4,
                            "has_result_or_consequence": True,
                        }
                        for idx in range(10)
                    ]
                },
                "document_refs": [
                    {"kind": "mentioned_path", "value": f"docs/{idx}.md", "preview": long_text}
                    for idx in range(10)
                ],
                "evidence_refs": [
                    {"kind": "raw_line", "value": f"raw:line:{idx}", "preview": long_text}
                    for idx in range(10)
                ],
            }
            return CommandOutput(argv, 0, json.dumps(payload), "", 1.0)

    state = state_with_fixture(tmp_path, HeavyChainRunner())

    chain = state.session_entity_usage_chain("aoa-session-memory-mcp", kind="mcp", limit=10)
    encoded = json.dumps(chain)

    assert chain["mcp_payload_policy"]["response_compacted"] is True
    assert chain["mcp_access"]["response_compacted"] is True
    assert chain["counts"]["usage_event_count"] == 10
    assert chain["first_ref"] == {
        "raw": "raw:line:0",
        "raw_block": "raw:block:0-4",
        "segment": "000.md#event-000000",
        "segment_index": "000.md",
        "session": "session:000",
    }
    assert len(chain["usage_chain"]["chains"]) == 3
    assert chain["usage_chain"]["omitted_chain_count"] == 7
    assert len(chain["usage_chain"]["chains"][0]["result_or_consequence_events"]) == 2
    assert len(chain["document_refs"]) == 2
    assert len(chain["evidence_refs"]) == 3
    assert "content" not in chain["usage_chain"]["chains"][0]["usage_event"]
    assert len(chain["usage_chain"]["chains"][0]["usage_event"]["title"]) <= 80
    assert "omitted_field_count" not in encoded
    assert len(encoded) < 7000
    assert ("chain raw evidence " * 20) not in encoded


def test_entity_usage_neighborhood_compacts_heavy_archive_payload_for_mcp(tmp_path: Path) -> None:
    class HeavyNeighborhoodRunner(FakeRunner):
        def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
            command = argv[2]
            if command != "entity-usage-neighborhood":
                return super().__call__(argv, timeout)
            self.calls.append((command, tuple(argv[3:])))
            self.timeouts.append((command, timeout))
            long_text = "neighbor evidence " * 120
            payload = {
                "schema_version": 1,
                "artifact_type": "session_memory_entity_usage_neighborhood",
                "ok": True,
                "anchor": "aoa-session-memory-mcp",
                "kind": "mcp",
                "window_count": 10,
                "quality": {
                    "usage_neighborhood_present": True,
                    "consequence_present": True,
                    "raw_preview_available": True,
                },
                "neighborhoods": [
                    {
                        "ok": True,
                        "source_usage_event": {
                            "event_id": f"{idx:06d}",
                            "event_type": "TOOL_CALL",
                            "raw_preview": {"status": "available", "line": idx, "text": long_text},
                            "content": long_text,
                            "refs": {"raw": f"raw:line:{idx}", "segment": f"seg#event-{idx:06d}"},
                        },
                        "local_events": [
                            {"offset": offset, "event_type": "ASSISTANT_MESSAGE", "title": long_text, "content": long_text}
                            for offset in range(14)
                        ],
                        "consequence_events": [
                            {"offset": offset, "event_type": "TOOL_OUTPUT", "title": long_text, "content": long_text}
                            for offset in range(14)
                        ],
                        "document_refs": [
                            {"kind": "mentioned_path", "value": f"docs/{idx}-{doc_idx}.md", "preview": long_text}
                            for doc_idx in range(20)
                        ],
                    }
                    for idx in range(10)
                ],
            }
            return CommandOutput(argv, 0, json.dumps(payload), "", 1.0)

    state = state_with_fixture(tmp_path, HeavyNeighborhoodRunner())

    neighborhood = state.session_entity_usage_neighborhood(
        "aoa-session-memory-mcp",
        kind="mcp",
        limit=10,
        per_route_limit=10,
        raw_preview_chars=600,
    )
    encoded = json.dumps(neighborhood)

    assert neighborhood["mcp_payload_policy"]["response_compacted"] is True
    assert neighborhood["mcp_access"]["response_compacted"] is True
    assert neighborhood["window_count"] == 10
    assert len(neighborhood["neighborhoods"]) == 2
    assert neighborhood["omitted_neighborhood_count"] == 8
    first = neighborhood["neighborhoods"][0]
    assert len(first["local_events"]) == 1
    assert first["omitted_local_events_count"] == 13
    assert len(first["consequence_events"]) == 1
    assert len(first["document_refs"]) == 2
    assert len(first["source_usage_event"]["raw_preview"]["text"]) <= 80
    assert "content" not in first["source_usage_event"]
    assert "omitted_field_count" not in encoded
    assert len(encoded) < 4500
    assert ("neighbor evidence " * 12) not in encoded


def test_skill_evidence_contract_survives_bounded_mcp_compaction(tmp_path: Path) -> None:
    def audit_payload() -> dict:
        return {
            "schema_version": 1,
            "artifact_type": "session_memory_entity_usage_audit",
            "ok": True,
            "mutates": False,
            "truth_status": "session_memory_entity_usage_routes_to_evidence_not_reviewed_truth",
            "anchor": "aoa-tdd-slice",
            "kind": "skill",
            "event_count": 9,
            "usage_event_count": 1,
            "outcome_event_count": 1,
            "consequence_event_count": 1,
            "false_correlation_event_count": 6,
            "false_correlation_edge_count": 6,
            "unique_false_correlation_event_count": 6,
            "usage_events": [SKILL_USAGE_EVENT],
            "outcome_events": [SKILL_SELECTED_OUTCOME_EVENT],
            "consequence_events": [SKILL_SELECTED_OUTCOME_EVENT],
            "false_correlation_events": SKILL_FALSE_CORRELATION_EVENTS,
            "document_refs": [{"kind": "mentioned_path", "value": "skills/aoa-tdd-slice/SKILL.md"}],
            "skill_evidence": SKILL_EVIDENCE_SUMMARY,
            "quality": {
                "skill_dispatch_candidate_present": True,
                "skill_behavioral_candidate_present": False,
                "skill_invocation_claim_allowed": False,
                "false_correlation_event_present": True,
            },
            "raw_transcript": "PRIVATE RAW TRANSCRIPT BODY MUST NOT CROSS MCP",
        }

    def chain_payload() -> dict:
        return {
            "schema_version": 1,
            "artifact_type": "session_memory_entity_usage_chain",
            "ok": True,
            "mutates": False,
            "truth_status": "session_memory_usage_chain_routes_to_evidence_not_reviewed_truth",
            "anchor": "aoa-tdd-slice",
            "kind": "skill",
            "counts": {
                "usage_event_count": 1,
                "outcome_event_count": 1,
                "consequence_event_count": 1,
                "false_correlation_event_count": 6,
                "false_correlation_edge_count": 6,
                "unique_false_correlation_event_count": 6,
                "chain_count": 1,
                "chain_with_result_or_consequence_count": 1,
            },
            "quality": {
                "direct_usage_present": True,
                "skill_dispatch_candidate_present": True,
                "skill_behavioral_candidate_present": False,
                "skill_invocation_claim_allowed": False,
                "false_correlation_event_present": True,
                "raw_or_segment_ref_present": True,
                "skipped_graph_rag_packet": True,
                "noise_flag_count": 1,
            },
            "noise_flags": ["foreign_correlated_results_rejected"],
            "first_ref": {
                "raw": "raw:line:4",
                "segment": "segments/000.md#event-000004",
                "segment_index": "segments/000.index.json",
                "session": "sessions/skill/session.json",
            },
            "usage_chain": {
                "chains": [
                    {
                        "usage_event": SKILL_USAGE_EVENT,
                        "result_or_consequence_events": [SKILL_SELECTED_OUTCOME_EVENT],
                        "result_or_consequence_count": 1,
                        "has_result_or_consequence": True,
                    }
                ],
                "outcome_events": [SKILL_SELECTED_OUTCOME_EVENT],
                "false_correlation_events": SKILL_FALSE_CORRELATION_EVENTS,
            },
            "document_refs": [{"kind": "mentioned_path", "value": "skills/aoa-tdd-slice/SKILL.md"}],
            "evidence_refs": [
                {"kind": "raw_line", "value": "raw:line:4"},
                {"kind": "segment_markdown", "value": "segments/000.md#event-000004"},
            ],
            "skill_evidence": SKILL_EVIDENCE_SUMMARY,
            "usage_action_counts": {"read": 1, "selected": 1},
            "primary_usage_action_counts": {"read": 1, "selected": 1},
            "usage_action_samples": {
                "read": [
                    {
                        "role": "usage",
                        "event_type": "FILE_READ",
                        "session_label": "2026-07-10__001__skill-evidence",
                        "event_id": "000004",
                        "title": "Read aoa-tdd-slice/SKILL.md",
                        "refs": SKILL_USAGE_EVENT["refs"],
                        "content": "PRIVATE RAW TRANSCRIPT BODY MUST NOT CROSS MCP",
                    }
                ],
                "selected": [
                    {
                        "role": "outcome",
                        "event_type": "ASSISTANT_MESSAGE",
                        "session_label": "2026-07-10__001__skill-evidence",
                        "event_id": "000005",
                        "title": "Using aoa-tdd-slice for the bounded change",
                        "refs": SKILL_SELECTED_OUTCOME_EVENT["refs"],
                    }
                ],
            },
            "raw_transcript": "PRIVATE RAW TRANSCRIPT BODY MUST NOT CROSS MCP",
        }

    def neighborhood_payload() -> dict:
        return {
            "schema_version": 1,
            "artifact_type": "session_memory_entity_usage_neighborhood",
            "ok": True,
            "mutates": False,
            "anchor": "aoa-tdd-slice",
            "kind": "skill",
            "window_count": 1,
            "quality": {"usage_neighborhood_present": True, "consequence_present": True},
            "neighborhoods": [
                {
                    "ok": True,
                    "source_usage_event": SKILL_USAGE_EVENT,
                    "local_events": [SKILL_FALSE_CORRELATION_EVENTS[0]],
                    "consequence_events": [SKILL_SELECTED_OUTCOME_EVENT],
                }
            ],
        }

    class SkillEvidenceRunner(FakeRunner):
        def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
            command = argv[2]
            payloads = {
                "entity-usage-audit": audit_payload,
                "usage-chain": chain_payload,
                "entity-usage-neighborhood": neighborhood_payload,
            }
            if command not in payloads:
                return super().__call__(argv, timeout)
            self.calls.append((command, tuple(argv[3:])))
            self.timeouts.append((command, timeout))
            return CommandOutput(argv, 0, json.dumps(payloads[command]()), "", 1.0)

    state = state_with_fixture(tmp_path, SkillEvidenceRunner())
    audit = state.session_entity_usage_audit("aoa-tdd-slice", kind="skill", limit=8)
    chain = state.session_entity_usage_chain("aoa-tdd-slice", kind="skill", limit=8)
    neighborhood = state.session_entity_usage_neighborhood(
        "aoa-tdd-slice",
        kind="skill",
        limit=4,
        per_route_limit=4,
        raw_preview_chars=160,
    )
    dossier = state.session_entity_dossier(
        "aoa-decision",
        kind="skill",
        usage_limit=2,
        neighborhood_limit=1,
        graph_limit=6,
        graph_edge_limit=6,
    )

    assert audit["skill_evidence"] == SKILL_EVIDENCE_SUMMARY
    assert audit["false_correlation_event_count"] == 6
    assert len(audit["false_correlation_events"]) == 3
    assert audit["omitted_false_correlation_event_count"] == 3
    assert audit["usage_events"][0]["skill_evidence_state"] == "skill_read"
    assert audit["outcome_events"][0]["skill_evidence_state"] == "selected"
    audit_rejected = audit["false_correlation_events"][0]
    assert audit_rejected["correlation_id"] == "other-call-0"
    assert audit_rejected["source_correlation_id"] == "skill-call"
    assert audit_rejected["rejected_correlation_id"] == "other-call-0"
    assert audit_rejected["skill_evidence_state"] == "false_correlation"
    assert audit_rejected["refs"]["raw"] == "raw:line:20"

    assert chain["skill_evidence"] == SKILL_EVIDENCE_SUMMARY
    assert chain["skill_evidence"]["supported_states"] == SKILL_EVIDENCE_SUPPORTED_STATES
    assert chain["usage_action_counts"] == {"read": 1, "selected": 1}
    assert chain["primary_usage_action_counts"] == {"read": 1, "selected": 1}
    assert chain["usage_action_samples"]["read"][0]["refs"]["raw"] == "raw:line:4"
    chain_usage = chain["usage_chain"]["chains"][0]["usage_event"]
    assert chain_usage["correlation_id"] == "skill-call"
    assert chain_usage["skill_evidence_state"] == "skill_read"
    assert chain_usage["usage_actions"] == ["read"]
    assert chain_usage["primary_usage_action"] == "read"
    assert chain_usage["refs"]["segment_index"] == "segments/000.index.json"
    assert chain["counts"]["false_correlation_event_count"] == 6
    assert len(chain["usage_chain"]["false_correlation_events"]) == 2
    assert chain["usage_chain"]["false_correlation_event_count"] == 6
    assert chain["usage_chain"]["omitted_false_correlation_event_count"] == 4
    chain_rejected = chain["usage_chain"]["false_correlation_events"][0]
    assert chain_rejected["source_doc_id"] == "event:session-skill:000004"
    assert chain_rejected["source_correlation_id"] == "skill-call"
    assert chain_rejected["rejected_correlation_id"] == "other-call-0"
    assert chain_rejected["skill_evidence_state"] == "false_correlation"
    assert chain_rejected["usage_actions"] == ["context"]
    assert chain_rejected["primary_usage_action"] == "context"

    neighborhood_usage = neighborhood["neighborhoods"][0]["source_usage_event"]
    neighborhood_rejected = neighborhood["neighborhoods"][0]["local_events"][0]
    assert neighborhood_usage["skill_evidence_state"] == "skill_read"
    assert neighborhood_usage["usage_actions"] == ["read"]
    assert neighborhood_rejected["source_correlation_id"] == "skill-call"
    assert neighborhood_rejected["rejected_correlation_id"] == "other-call-0"
    assert neighborhood_rejected["skill_evidence_state"] == "false_correlation"

    assert dossier["usage"]["skill_evidence"] == SKILL_EVIDENCE_SUMMARY
    assert dossier["usage"]["false_correlation_event_count"] == 6
    assert dossier["usage"]["false_correlation_events"][0]["refs"]["raw"] == "raw:line:20"

    for payload in (audit, chain, neighborhood, dossier):
        encoded = json.dumps(payload)
        assert "PRIVATE RAW TRANSCRIPT BODY MUST NOT CROSS MCP" not in encoded
        assert "raw_transcript" not in encoded


def test_usage_action_count_compactor_is_bounded() -> None:
    from aoa_session_memory_mcp import core as core_module

    compact, omitted = core_module._compact_usage_action_counts(
        {f"action_{index}": index for index in range(15)}
    )

    assert len(compact) == core_module.ENTITY_USAGE_ACTION_LIMIT
    assert list(compact) == [f"action_{index}" for index in range(12)]
    assert omitted == 3


def test_entity_usage_scenario_audit_routes_to_allowlisted_archive_command(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    audit = state.session_entity_usage_scenario_audit(
        sample_size=2,
        seed="fixture-random",
        layers=["mcp", "tool"],
        min_postings=2,
        limit=3,
        per_route_limit=4,
        consequence_window=5,
        document_limit=6,
        raw_preview_limit=2,
        full=True,
    )

    assert audit["artifact_type"] == "session_memory_entity_usage_scenario_audit"
    assert audit["quality"]["failed_count"] == 0
    usage_calls = [call for call in runner.calls if call[0] == "entity-usage-scenario-audit"]
    assert len(usage_calls) == 1
    args = usage_calls[0][1]
    assert args[args.index("--seed") + 1] == "fixture-random"
    assert args[args.index("--sample-size") + 1] == "2"
    assert args.count("--layer") == 2
    assert args[args.index("--per-route-limit") + 1] == "4"
    assert args[args.index("--raw-preview-limit") + 1] == "2"
    assert "--full" in args
    assert runner.timeouts[-1] == ("entity-usage-scenario-audit", 90.0)


def test_live_scenario_audit_routes_to_canonical_archive_command(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    audit = state.session_live_scenario_audit(
        seed="fixture-live",
        profiles=[
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
        ],
        sample_size=2,
        recent_days=4000,
        limit=2,
    )

    assert audit["artifact_type"] == "session_memory_live_scenario_audit"
    assert audit["ok"] is True
    assert audit["truth_status"] == "bounded_live_scenario_audit_not_reviewed_truth"
    assert audit["mcp_route"]["canonical_route"] == "scripts/aoa_session_memory.py live-scenario-audit"
    assert audit["mcp_route"]["source_of_truth"] == ".aoa"
    assert "entity_registry_lookup" in audit["mcp_route"]["supported_profiles"]
    assert "stale/removed" in audit["mcp_route"]["entity_registry_lookup_contract"]
    assert audit["parameters"]["limit"] == 2
    assert audit["parameters"]["recent_days"] == 90
    assert audit["quality"]["scenario_count"] == 1
    assert audit["quality"]["failed_count"] == 0
    assert audit["quality"]["actionable_gap_count"] == 0
    assert audit["scenarios"][0]["profile"] == "entity_registry_lookup"
    assert audit["scenarios"][0]["status_counts"]["removed"] == 1
    assert audit["scenarios"][0]["transition_probe_count"] == 2

    assert [command for command, _args in runner.calls] == ["live-scenario-audit"]
    command, args = runner.calls[0]
    assert command == "live-scenario-audit"
    assert args[args.index("--seed") + 1] == "fixture-live"
    assert args[args.index("--sample-size") + 1] == "2"
    assert args[args.index("--recent-days") + 1] == "90"
    assert args[args.index("--limit") + 1] == "2"
    assert args.count("--profile") == 10
    assert "entity_registry_lookup" in args
    assert "route_rollup_query" in args
    assert runner.timeouts[-1] == ("live-scenario-audit", 90.0)


def test_live_scenario_corpus_check_routes_to_archive_corpus(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    payload = state.session_live_scenario_corpus_check(case_limit=1, full=True)

    assert payload["artifact_type"] == "session_memory_live_scenario_regression_check"
    assert payload["ok"] is True
    assert payload["case_count"] == 1
    assert payload["mcp_route"]["canonical_corpus"] == "config/live-scenario-regression-corpus.json"
    assert payload["mcp_route"]["does_not_accept_arbitrary_corpus_path"] is True
    command, args = runner.calls[-1]
    assert command == "live-scenario-corpus"
    assert args[0] == "check"
    assert args[args.index("--case-limit") + 1] == "1"
    assert "--full" in args
    assert runner.timeouts[-1] == ("live-scenario-corpus", 90.0)


def test_live_scenario_corpus_inventory_routes_to_archive_list(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    payload = state.session_live_scenario_corpus_inventory(full=True)

    assert payload["artifact_type"] == "session_memory_live_scenario_regression_corpus_inventory"
    assert payload["ok"] is True
    assert payload["case_count"] == 3
    assert payload["truth_status"] == "source_corpus_inventory_not_live_route_proof"
    assert payload["mcp_route"]["canonical_route"] == "scripts/aoa_session_memory.py live-scenario-corpus list"
    assert payload["mcp_route"]["does_not_run_cases"] is True
    command, args = runner.calls[-1]
    assert command == "live-scenario-corpus"
    assert args[0] == "list"
    assert "--full" in args
    assert runner.timeouts[-1] == ("live-scenario-corpus", 90.0)


def test_live_scenario_audit_preserves_failed_archive_payload(tmp_path: Path) -> None:
    class FailedLiveScenarioRunner(FakeRunner):
        def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
            command = argv[2]
            if command != "live-scenario-audit":
                return super().__call__(argv, timeout)
            self.calls.append((command, tuple(argv[3:])))
            self.timeouts.append((command, timeout))
            payload = {
                "schema_version": 1,
                "artifact_type": "session_memory_live_scenario_audit",
                "ok": False,
                "mutates": False,
                "truth_status": "bounded_live_scenario_audit_not_reviewed_truth",
                "quality": {
                    "scenario_count": 1,
                    "passed_count": 0,
                    "warn_count": 0,
                    "failed_count": 1,
                    "actionable_gap_count": 1,
                },
                "scenarios": [
                    {
                        "profile": "literal_planner",
                        "status": "failed",
                        "failed_count": 4,
                        "primary_route_counts": {"monolith_raw_text_fallback": 4},
                    }
                ],
                "actionable_gaps": [
                    {
                        "profile": "literal_planner",
                        "status": "failed",
                        "reasons": ["literal_planner_used_monolith_fallback_first"],
                    }
                ],
            }
            return CommandOutput(argv, 1, json.dumps(payload), "live scenario failed", 1.0)

    state = state_with_fixture(tmp_path, FailedLiveScenarioRunner())

    audit = state.session_live_scenario_audit(profiles=["literal_planner"], limit=2)

    assert audit["ok"] is False
    assert audit["quality"]["failed_count"] == 1
    assert audit["quality"]["actionable_gap_count"] == 1
    scenario = audit["scenarios"][0]
    assert scenario["status"] == "failed"
    assert scenario["failed_count"] == 4
    assert scenario["primary_route_counts"]["monolith_raw_text_fallback"] == 4
    assert audit["actionable_gaps"][0]["reasons"] == ["literal_planner_used_monolith_fallback_first"]
    assert audit["mcp_access"]["returncode"] == 1
    assert audit["mcp_access"]["stderr"] == "live scenario failed"


def test_route_reads_generated_axis_without_arbitrary_paths(tmp_path: Path) -> None:
    state = state_with_fixture(tmp_path)
    route = state.session_route("mcp", "aoa-session-memory-mcp", include_entry_payloads=True)

    assert route["ok"] is True
    assert route["normalized_key"] == "aoa_session_memory_mcp"
    assert route["match_count"] == 1
    assert route["entry_payloads"][0]["summary"] == "test entry"


def test_brief_is_compact_and_returns_refs(tmp_path: Path) -> None:
    state = state_with_fixture(tmp_path)
    brief = state.session_brief("latest", max_segments=1)

    assert brief["ok"] is True
    assert brief["session"]["session_id"] == "session-1"
    assert brief["refs"]["manifest"].endswith("session.manifest.json")
    assert len(brief["segments"]) == 1


def test_evidence_packet_combines_trace_search_retrieve_and_freshness(tmp_path: Path) -> None:
    state = state_with_fixture(tmp_path)
    packet = state.session_evidence_packet(
        intent="debug aoa-session-memory-mcp",
        anchors=["aoa-session-memory-mcp"],
        limit=4,
    )

    assert packet["schema"] == "aoa_session_memory_evidence_packet_v1"
    assert packet["effective_query"] == "debug aoa-session-memory-mcp"
    assert packet["search_hits"]
    assert packet["route_traces"][0]["route_candidates"]
    assert packet["freshness"]["provider"]["ok"] is True
    assert packet["candidate_posture"].startswith("candidate evidence")


def test_evidence_packet_does_not_fail_session_relative_raw_refs_without_session(
    tmp_path: Path,
) -> None:
    state = state_with_fixture(tmp_path)
    packet = state.session_evidence_packet(
        intent="debug aoa-session-memory-mcp",
        refs=["raw:line:1"],
        limit=4,
    )

    assert packet["freshness"]["ok"] is True
    assert packet["freshness"]["checks"][0]["status"] == "needs_session_context"
    assert packet["freshness"]["checks"][0]["reason"] == (
        "raw line refs are session-relative"
    )


def test_pattern_scan_aggregates_route_signals(tmp_path: Path) -> None:
    state = state_with_fixture(tmp_path)
    scan = state.session_pattern_scan("aoa-session-memory", limit=10)

    assert scan["hit_count"] == 1
    assert scan["aggregates"]["route_signal"][0]["key"] == "entity:aoa_session_memory_mcp"


def test_graph_neighborhood_uses_sqlite_fast_path_for_exact_route_node(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)
    graph_db = state.aoa_root / "graph/graph.sqlite3"
    graph_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(graph_db)
    try:
        conn.executescript(
            """
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE edges (
                id TEXT PRIMARY KEY,
                edge_type TEXT NOT NULL,
                source_node TEXT NOT NULL,
                target_node TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX idx_edges_source ON edges(source_node);
            CREATE INDEX idx_edges_target ON edges(target_node);
            CREATE TABLE node_contribs (
                source_key TEXT NOT NULL,
                node_id TEXT NOT NULL,
                node_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (source_key, node_id)
            );
            CREATE INDEX idx_node_contribs_node ON node_contribs(node_id);
            CREATE TABLE edge_contribs (
                source_key TEXT NOT NULL,
                edge_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                source_node TEXT NOT NULL,
                target_node TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (source_key, edge_id)
            );
            CREATE INDEX idx_edge_contribs_edge ON edge_contribs(edge_id);
            """
        )
        route_node = {
            "id": "route:mcp:mcp:aoa_session_memory_mcp",
            "type": "mcp",
            "label": "mcp:aoa_session_memory_mcp",
            "route_layer": "mcp",
            "route_signal": "mcp:aoa_session_memory_mcp",
        }
        event_node = {"id": "event:session-1:000:000001", "type": "event", "title": "debug mcp"}
        session_node = {"id": "session:session-1", "type": "session", "label": "session-1"}
        conn.executemany(
            "INSERT INTO nodes (id, node_type, payload_json, count) VALUES (?, ?, ?, ?)",
            [
                (route_node["id"], "mcp", json.dumps(route_node), 9),
                (event_node["id"], "event", json.dumps(event_node), 1),
                (session_node["id"], "session", json.dumps(session_node), 3),
            ],
        )
        edge_payloads = [
            (
                "edge:1",
                "mentions_route_signal",
                event_node["id"],
                route_node["id"],
                {
                    "type": "mentions_route_signal",
                    "event_id": "000001",
                    "segment_id": "000",
                    "session_id": "session-1",
                    "evidence_refs": [
                        {
                            "session_id": "session-1",
                            "segment_id": "000",
                            "event_id": "000001",
                            "refs": {"raw": "raw:line:1", "segment": "000__initial-to-latest.md#event-000001"},
                        }
                    ],
                },
                5,
            ),
            (
                "edge:2",
                "session_has_route_signal",
                session_node["id"],
                route_node["id"],
                {"type": "session_has_route_signal", "session_id": "session-1"},
                3,
            ),
            (
                "edge:3",
                "mentions_route_signal",
                "event:session-1:000:000002",
                route_node["id"],
                {"type": "mentions_route_signal", "event_id": "000002"},
                1,
            ),
        ]
        conn.executemany(
            "INSERT INTO edges (id, edge_type, source_node, target_node, payload_json, count) VALUES (?, ?, ?, ?, ?, ?)",
            [(edge_id, edge_type, source, target, json.dumps(payload), count) for edge_id, edge_type, source, target, payload, count in edge_payloads],
        )
        conn.execute(
            "INSERT INTO node_contribs (source_key, node_id, node_type, payload_json, count) VALUES (?, ?, ?, ?, ?)",
            (
                "session:session-1",
                route_node["id"],
                "mcp",
                json.dumps(
                    {
                        "evidence_refs": [
                            {
                                "session_id": "session-1",
                                "refs": {"session": "sessions/2026-05-26__001__session-memory-mcp/session.manifest.json"},
                            }
                        ]
                    }
                ),
                1,
            ),
        )
        conn.execute(
            "INSERT INTO edge_contribs (source_key, edge_id, edge_type, source_node, target_node, payload_json, count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "event:session-1:000:000001",
                "edge:1",
                "mentions_route_signal",
                event_node["id"],
                route_node["id"],
                json.dumps(edge_payloads[0][4]),
                1,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    neighborhood = state.graph_neighborhood("aoa-session-memory-mcp", kind="mcp", depth=1, limit=4, edge_limit=2)

    assert neighborhood["source"] == "mcp_sqlite_graph_fast_path"
    assert neighborhood["quality"]["direct_sqlite_fast_path"] is True
    assert neighborhood["quality"]["raw_or_segment_ref_present"] is True
    assert neighborhood["node_count"] == 3
    assert neighborhood["edge_count"] == 2
    assert neighborhood["omitted_edge_count"] == 1
    assert neighborhood["truncated"] is True
    assert any(str(ref.get("refs", {}).get("session", "")).endswith("session.manifest.json") for ref in neighborhood["evidence_refs"])
    assert any(ref.get("refs", {}).get("raw") == "raw:line:1" for ref in neighborhood["evidence_refs"])
    assert neighborhood["mcp_access"]["archive_command"] is None
    assert "graph-neighborhood" in neighborhood["mcp_access"]["full_graph_route"]
    assert not any(call[0] == "graph-neighborhood" for call in runner.calls)

    deeper = state.graph_neighborhood("aoa-session-memory-mcp", kind="mcp", depth=2, limit=4, edge_limit=2)

    assert deeper.get("source") != "mcp_sqlite_graph_fast_path"
    graph_calls = [call for call in runner.calls if call[0] == "graph-neighborhood"]
    assert graph_calls
    assert graph_calls[-1][1][graph_calls[-1][1].index("--depth") + 1] == "2"


def test_graph_and_graphrag_tools_route_to_allowlisted_archive_commands(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    neighborhood = state.graph_neighborhood("aoa-session-memory-mcp", kind="mcp", depth=2, limit=20, edge_limit=7)
    timeline = state.graph_timeline("aoa-session-memory-mcp", kind="mcp", limit=10)
    path = state.graph_shortest_path("aoa-session-memory-mcp", "exec_command", max_depth=4)
    bridge = state.graph_bridge("aoa-session-memory-mcp", "exec_command", source_kind="mcp", target_kind="tool", limit=4)
    cooccurrence = state.graph_cooccurrence("aoa-session-memory-mcp", kind="mcp", limit=10)
    graphrag = state.graphrag_packet("aoa-session-memory-mcp", anchor="aoa-session-memory-mcp", limit=4)
    explain = state.explain_graph_packet("debug aoa-session-memory-mcp", anchor="aoa-session-memory-mcp", limit=4)
    eval_payload = state.graph_eval(limit=4)
    quality = state.graph_quality_audit(limit=4)

    assert neighborhood["evidence_refs"][0]["refs"]["raw"] == "raw:line:1"
    assert neighborhood["truncated"] is True
    assert neighborhood["next_command"].startswith("python3 scripts/aoa_session_memory.py graph-neighborhood")
    assert neighborhood["next_expansion_command"].startswith(
        "python3 scripts/aoa_session_memory.py graph-neighborhood"
    )
    assert neighborhood["next_expansion_reason"]
    assert neighborhood["freshness"]["status"] == "graph_store_stale"
    assert neighborhood["freshness"]["warning"].startswith("graph store")
    assert neighborhood["freshness"]["actionable_graph_source_count"] == 2531
    assert neighborhood["freshness"]["deferred_live_source_count"] == 1139
    assert neighborhood["freshness"]["ledger_store_missing_count"] == 52
    assert neighborhood["freshness"]["latest_maintenance_remaining_count"] == 2452
    assert neighborhood["freshness"]["hot_gate_diagnostics"] == [
        "maintenance_queue_empty_but_ledger_actionable_sources_present"
    ]
    assert neighborhood["freshness"]["maintenance_recommendation"]["route"] == "budgeted_graph_maintenance"
    assert neighborhood["freshness"]["maintenance_recommendation"]["command"].startswith(
        "python3 scripts/aoa_session_memory.py graph-maintenance"
    )
    assert neighborhood["mcp_payload_policy"]["response_compacted"] is True
    assert neighborhood["mcp_access"]["response_compacted"] is True
    assert timeline["events"][0]["type"] == "event"
    assert timeline["mcp_payload_policy"]["response_compacted"] is True
    assert path["edges"][0]["type"] == "mentions_route_signal"
    assert bridge["artifact_type"] == "session_memory_graph_bridge"
    assert bridge["bridge"]["path_found"] is True
    assert bridge["normalized_entities"]["source"]["kind"] == "mcp"
    assert bridge["normalized_entities"]["target"]["kind"] == "tool"
    assert bridge["quality"]["raw_or_segment_ref_present"] is True
    assert bridge["freshness"]["status"] == "graph_store_stale"
    assert "dirty_sessions" not in bridge["freshness"]
    assert "dirty_session_ids" not in bridge["freshness"]
    assert "internal_plan" not in bridge["freshness"]["maintenance_recommendation"]
    assert bridge["mcp_payload_policy"]["response_compacted"] is True
    assert "graph-bridge" in bridge["mcp_access"]["full_graph_route"]
    assert cooccurrence["cooccurrences"][0]["node"]["type"] == "tool"
    assert graphrag["artifact_type"] == "session_memory_graphrag_packet"
    assert explain["artifact_type"] == "session_memory_graph_explain_packet"
    assert eval_payload["results"][0]["hybrid"]["has_raw_or_segment_refs"] is True
    assert quality["artifact_type"] == "session_memory_graph_quality_audit"
    assert quality["samples"][0]["review_status"] == "ready_for_manual_verdict"
    assert {call[0] for call in runner.calls} >= {
        "graph-neighborhood",
        "graph-timeline",
        "graph-shortest-path",
        "graph-bridge",
        "graph-cooccurrence",
        "graphrag-packet",
        "graph-explain-packet",
        "graph-eval",
        "graph-quality-audit",
    }
    graph_call_args = next(args for command, args in runner.calls if command == "graph-neighborhood")
    assert "--edge-limit" in graph_call_args


def test_graph_packets_are_compact_by_default_without_losing_refs(tmp_path: Path) -> None:
    long_text = "heavy graph evidence " * 80

    class HeavyGraphRunner(FakeRunner):
        def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
            command = argv[2]
            args = tuple(argv[3:])
            self.calls.append((command, args))
            self.timeouts.append((command, timeout))
            if command == "graph-neighborhood":
                evidence_refs = [
                    {
                        "session_id": "session-1",
                        "segment_id": "000",
                        "event_id": f"{idx:06d}",
                        "node_id": f"event:session-1:000:{idx:06d}",
                        "refs": {"raw": f"raw:line:{idx}", "segment": f"seg#event-{idx:06d}"},
                    }
                    for idx in range(30)
                ] + [
                    {
                        "session_id": "session-1",
                        "segment_id": "000",
                        "event_id": "000001",
                        "node_id": "event:session-1:000:000001",
                        "refs": {"raw": "raw:line:1", "segment": "seg#event-000001"},
                    }
                    for _ in range(10)
                ]
                payload = {
                    "schema_version": 1,
                    "artifact_type": "session_memory_graph_neighborhood",
                    "ok": True,
                    "mutates": False,
                    "anchor": "aoa-session-memory-mcp",
                    "node_count": 60,
                    "edge_count": 100,
                    "nodes": [
                        {
                            "id": f"event:session-1:000:{idx:06d}",
                            "type": "event",
                            "title": long_text,
                            "content": long_text,
                            "evidence_refs": [evidence_refs[idx % len(evidence_refs)]],
                        }
                        for idx in range(60)
                    ],
                    "edges": [
                        {
                            "source": f"event:session-1:000:{idx % 60:06d}",
                            "target": "route:mcp:mcp:aoa_session_memory_mcp",
                            "type": "mentions_route_signal",
                            "content": long_text,
                        }
                        for idx in range(100)
                    ],
                    "evidence_refs": evidence_refs,
                    "freshness": {"status": "fresh"},
                }
                return CommandOutput(argv, 0, json.dumps(payload), "", 1.0)
            if command == "graph-timeline":
                payload = {
                    "schema_version": 1,
                    "artifact_type": "session_memory_graph_timeline",
                    "ok": True,
                    "mutates": False,
                    "anchor": "aoa-session-memory-mcp",
                    "events": [
                        {
                            "id": f"event:session-1:000:{idx:06d}",
                            "type": "event",
                            "event_id": f"{idx:06d}",
                            "title": long_text,
                            "content": long_text,
                            "evidence_refs": [
                                {
                                    "session_id": "session-1",
                                    "segment_id": "000",
                                    "event_id": f"{idx:06d}",
                                    "refs": {"raw": f"raw:line:{idx}", "segment": f"seg#event-{idx:06d}"},
                                }
                            ],
                        }
                        for idx in range(60)
                    ],
                    "evidence_refs": [
                        {
                            "session_id": "session-1",
                            "segment_id": "000",
                            "event_id": f"{idx:06d}",
                            "refs": {"raw": f"raw:line:{idx}", "segment": f"seg#event-{idx:06d}"},
                        }
                        for idx in range(60)
                    ],
                }
                return CommandOutput(argv, 0, json.dumps(payload), "", 1.0)
            return super().__call__(argv, timeout)

    runner = HeavyGraphRunner()
    state = state_with_fixture(tmp_path, runner)

    neighborhood = state.graph_neighborhood("aoa-session-memory-mcp", kind="mcp", limit=60, edge_limit=80)
    timeline = state.graph_timeline("aoa-session-memory-mcp", kind="mcp", limit=50)
    encoded = json.dumps({"neighborhood": neighborhood, "timeline": timeline})

    assert neighborhood["mcp_payload_policy"]["response_compacted"] is True
    assert neighborhood["mcp_access"]["response_compacted"] is True
    assert len(neighborhood["nodes"]) == 8
    assert neighborhood["omitted_node_count"] == 52
    assert len(neighborhood["edges"]) == 8
    assert neighborhood["omitted_edge_count"] == 92
    assert len(neighborhood["evidence_refs"]) == 6
    assert neighborhood["evidence_ref_count"] == 40
    assert neighborhood["unique_evidence_ref_count"] == 30
    assert neighborhood["deduplicated_evidence_ref_count"] == 10
    assert neighborhood["omitted_evidence_ref_count"] == 24
    assert neighborhood["nodes"][0]["refs"]["raw"] == "raw:line:0"
    assert "graph-neighborhood" in neighborhood["mcp_access"]["full_graph_route"]

    assert timeline["mcp_payload_policy"]["response_compacted"] is True
    assert len(timeline["events"]) == 8
    assert timeline["omitted_event_count"] == 52
    assert timeline["events"][0]["refs"]["raw"] == "raw:line:0"
    assert "graph-timeline" in timeline["mcp_access"]["full_graph_route"]
    assert "content" not in encoded
    assert "omitted_field_count" not in encoded
    assert len(encoded) < 14000
    graph_call_args = next(args for command, args in runner.calls if command == "graph-neighborhood")
    assert graph_call_args[graph_call_args.index("--edge-limit") + 1] == "80"


def test_read_resource_and_server_build(tmp_path: Path) -> None:
    state = state_with_fixture(tmp_path)
    resource = state.read_resource("aoa-session-memory://route/mcp/aoa-session-memory-mcp")
    graph_resource = state.read_resource("aoa-session-memory://graph/neighborhood/aoa-session-memory-mcp")
    projection_resource = state.read_resource("aoa-session-memory://projection/status")

    assert resource["match_count"] == 1
    assert graph_resource["artifact_type"] == "session_memory_graph_neighborhood"
    assert projection_resource["schema"] == "aoa_session_memory_projection_status_v1"
    assert build_server(workspace_root=tmp_path, aoa_root=tmp_path / ".aoa", script_path=tmp_path / ".aoa/scripts/aoa_session_memory.py") is not None


def test_server_auto_reloads_stale_core_implementation(monkeypatch: Any) -> None:
    import aoa_session_memory_mcp.server as server_module

    fresh_sha = server_module.core_module.MCP_CORE_LOADED_SHA256
    monkeypatch.setattr(server_module.core_module, "MCP_CORE_LOADED_SHA256", "stale-loaded-code")

    assert server_module._core_reload_required() is True

    server_module._reload_core_if_changed()

    assert server_module.core_module.MCP_CORE_LOADED_SHA256 == fresh_sha
    assert server_module._core_reload_required() is False

    importlib.reload(server_module.core_module)
