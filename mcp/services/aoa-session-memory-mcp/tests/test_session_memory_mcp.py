from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sqlite3
import sys
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
            "entity_count": 1,
            "counts_by_kind": {"skill": 1},
            "counts_by_status": {"active": 1},
            "entries": [
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
    "goal_lifecycle_schema_version": 1,
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
            "schema_version": 1,
            "session_label": "2026-05-26__001__session-memory-mcp",
            "session_id": "session-1",
            "goal_id": "goal-0001",
            "goal_instance_id": "session-1:goal-0001",
            "status": "complete",
            "objective": "Close goal lifecycle routing " * 40,
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
    "entity_count": 1,
    "entries": [
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
    "freshness": {"status": "fresh"},
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
        elif command == "search":
            payload = SEARCH_RESULTS
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
        elif command == "entity-usage-neighborhood":
            payload = ENTITY_USAGE_NEIGHBORHOOD
        elif command == "entity-usage-scenario-audit":
            payload = ENTITY_USAGE_SCENARIO_AUDIT
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
        else:
            return CommandOutput(argv, 2, "{}", f"unexpected command {command}", 1.0)
        return CommandOutput(argv, 0, json.dumps(payload), "", 1.0)


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


def test_latest_session_resolution_prefers_live_transcript_activity(tmp_path: Path) -> None:
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
    assert brief["session"]["session_id"] == "active-long-session"


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
    assert fresh["loaded_core_path"].endswith("aoa_session_memory_mcp/core.py")

    monkeypatch.setattr(module, "MCP_CORE_LOADED_SHA256", "stale-loaded-code")
    stale = state.runtime_identity()

    assert stale["source_matches_loaded"] is False
    assert stale["reload_required"] is True
    assert "MCP process is restarted" in stale["reload_boundary"]


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
    assert payload["mcp_access"]["mutates"] is False
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
    assert "aoa-session-memory://maintenance/status" in surfaces["resources"]


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


def test_retrieve_entity_usage_redirects_to_usage_audit(tmp_path: Path) -> None:
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
    assert payload["artifact_type"] == "session_memory_entity_usage_audit"
    assert payload["recipe"] == "entity_usage"
    assert payload["retrieval_redirect"]["served_by"] == "aoa_session_entity_usage_audit"
    assert "served by entity-usage-audit retrieval redirect" in payload["diagnostics"]
    assert not any(call[0] == "retrieve" for call in runner.calls)
    usage_calls = [call for call in runner.calls if call[0] == "entity-usage-audit"]
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
            "agent_event": "assistant_final_closeout",
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
    assert args[args.index("--agent-event") + 1] == "assistant_final_closeout"
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
    assert "answer-neighborhood" in calls
    episode_args = calls["task-episodes"]
    assert episode_args[episode_args.index("--status") + 1] == "closed"
    assert episode_args[episode_args.index("--verification-state") + 1] == "verified"


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
    assert responses["search_projection"]["mode"] == "mcp_sqlite_agent_event_fast_path"
    assert responses["search_projection"]["fallback_route"] == "archive_cli_shard_fanout"
    assert responses["cost_profile"]["lightweight_route"] is True
    assert responses["cost_profile"]["uses_fts"] is False
    assert responses["mcp_access"]["archive_command"] is None
    assert search["source"] == "portable_sqlite_agent_event_fast_path"
    assert "served by MCP agent-event route fast path" in search["diagnostics"]
    assert open_thread_search["source"] == "portable_sqlite_agent_event_fast_path"
    assert open_thread_search["agent_events"] == ["assistant_open_thread"]
    assert open_thread_search["requested_agent_events"] == ["open_thread"]
    assert open_thread_search["result_count"] == 1
    assert open_thread_search["results"][0]["agent_event"] == "assistant_open_thread"
    assert neighborhood["source"] == "portable_sqlite_agent_event_window_fast_path"
    assert neighborhood["window_count"] == 1
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
    assert len(lifecycles["results"][0]["sample_events"]) == 2
    assert lifecycles["results"][0]["sample_events"][0]["objective"].endswith("...")
    assert lifecycles["results"][0]["sample_events"][0]["objective_omitted"] is True
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
        {"kind": "mcp", "requested_kind": "mcp_service"},
        {"kind": "agent_event", "outcome_event_count": 2},
        {"retrieval_redirect": {"served_by": "aoa_session_entity_usage_audit"}},
        {"recommendation": "use_graph_search"},
        tool_count=30,
    )

    assert summary["tool_count"] == 30
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
    assert summary["usage_alias_kind"] == "mcp"
    assert summary["usage_alias_requested_kind"] == "mcp_service"
    assert summary["agent_event_usage_kind"] == "agent_event"
    assert summary["agent_event_usage_outcome_count"] == 2
    assert summary["retrieve_usage_served_by"] == "aoa_session_entity_usage_audit"
    assert summary["maintenance_recommendation"] == "use_graph_search"


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
    assert "aoa_session_agent_responses" in tools
    assert "aoa_session_agent_closeouts" in tools
    assert "aoa_session_agent_progress_updates" in tools
    assert "aoa_session_agent_reasoning_windows" in tools
    assert "aoa_session_task_episodes" in tools
    assert "aoa_session_goal_lifecycles" in tools
    assert "aoa_session_answer_neighborhood" in tools
    assert "aoa_session_entity_usage_neighborhood" in tools
    assert "aoa_session_hook_receipts" in tools
    assert "aoa_session_entity_inventory" in tools
    assert "aoa_session_entity_registry" in tools
    assert tools["aoa_session_hook_receipts"].inputSchema["properties"]["event_name"]["default"] == "UserPromptSubmit"
    assert tools["aoa_session_entity_inventory"].inputSchema["properties"]["layer"]["default"] == "skill"
    assert tools["aoa_session_entity_registry"].inputSchema["properties"]["kind"]["default"] == "all"
    assert tools["aoa_session_goal_lifecycles"].inputSchema["properties"]["target"]["default"] == "all"
    assert tools["aoa_session_goal_lifecycles"].inputSchema["properties"]["order"]["default"] == "recent"


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


def test_graph_and_graphrag_tools_route_to_allowlisted_archive_commands(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    neighborhood = state.graph_neighborhood("aoa-session-memory-mcp", kind="mcp", depth=2, limit=20)
    timeline = state.graph_timeline("aoa-session-memory-mcp", kind="mcp", limit=10)
    path = state.graph_shortest_path("aoa-session-memory-mcp", "exec_command", max_depth=4)
    cooccurrence = state.graph_cooccurrence("aoa-session-memory-mcp", kind="mcp", limit=10)
    graphrag = state.graphrag_packet("aoa-session-memory-mcp", anchor="aoa-session-memory-mcp", limit=4)
    explain = state.explain_graph_packet("debug aoa-session-memory-mcp", anchor="aoa-session-memory-mcp", limit=4)
    eval_payload = state.graph_eval(limit=4)
    quality = state.graph_quality_audit(limit=4)

    assert neighborhood["evidence_refs"][0]["refs"]["raw"] == "raw:line:1"
    assert timeline["events"][0]["type"] == "event"
    assert path["edges"][0]["type"] == "mentions_route_signal"
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
        "graph-cooccurrence",
        "graphrag-packet",
        "graph-explain-packet",
        "graph-eval",
        "graph-quality-audit",
    }


def test_read_resource_and_server_build(tmp_path: Path) -> None:
    state = state_with_fixture(tmp_path)
    resource = state.read_resource("aoa-session-memory://route/mcp/aoa-session-memory-mcp")
    graph_resource = state.read_resource("aoa-session-memory://graph/neighborhood/aoa-session-memory-mcp")

    assert resource["match_count"] == 1
    assert graph_resource["artifact_type"] == "session_memory_graph_neighborhood"
    assert build_server(workspace_root=tmp_path, aoa_root=tmp_path / ".aoa", script_path=tmp_path / ".aoa/scripts/aoa_session_memory.py") is not None
