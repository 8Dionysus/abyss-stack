from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from aoa_session_memory_mcp.core import AoASessionMemoryMCPState, CommandOutput
from aoa_session_memory_mcp.server import build_server


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
                    "signal_count": 4,
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
    write_json(skill_entry_path, {"route_key": "aoa_decision", "summary": "test skill entry"})
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
    "ok": True,
    "default_provider": "portable_sqlite",
    "providers": {"portable_sqlite": {"ok": True, "status": "ready", "document_count": 10}},
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
        elif command == "search":
            payload = SEARCH_RESULTS
        elif command in {"agent-responses", "agent-closeouts", "agent-progress-updates"}:
            payload = AGENT_RESPONSES
        elif command in {"agent-reasoning-windows", "answer-neighborhood"}:
            payload = AGENT_WINDOWS
        elif command == "task-episodes":
            payload = TASK_EPISODES
        elif command == "trace-route":
            payload = TRACE_RESULTS
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


def state_with_fixture(tmp_path: Path, runner: FakeRunner | None = None) -> AoASessionMemoryMCPState:
    aoa = seed_archive(tmp_path)
    return AoASessionMemoryMCPState.discover(
        workspace_root=tmp_path,
        aoa_root=aoa,
        script_path=aoa / "scripts/aoa_session_memory.py",
        command_runner=runner or FakeRunner(),
        timeout_seconds=2,
    )


def test_status_reads_provider_atlas_and_latest_diagnostics(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)
    status = state.session_memory_status()

    assert status["schema"] == "aoa_session_memory_status_v1"
    assert status["provider"]["ok"] is True
    assert status["provider"]["status_mode"] == "fast_presence_probe"
    assert status["provider"]["providers"]["portable_sqlite"]["freshness"]["checked"] is False
    assert status["atlas"]["entry_count"] == 2
    assert status["latest_route_readiness"]["reports"][0]["summary"]["ok"] is True
    assert status["readiness_policy"]["provider_status"]["freshness_checked"] is False
    assert status["readiness_policy"]["cached_route_readiness"]["status_field"] == "latest_route_readiness"
    assert status["authority_boundary"]["mutation_posture"].startswith("no write")
    assert not any(call[0] == "search-provider-status" for call in runner.calls)

    provider_resource = state.read_resource("aoa-session-memory://provider/status")
    assert provider_resource["status_mode"] == "fast_presence_probe"
    assert not any(call[0] == "search-provider-status" for call in runner.calls)


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
    assert "--write-report" in status["readiness_policy"]["audit_route"]["command"]


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
    assert status["graph"]["needs_graph_maintenance"] is True
    assert status["graph"]["freshness"]["graph_status"] == "dirty"
    assert status["graph"]["freshness"]["dirty_count"] == 7
    assert status["graph"]["freshness"]["missing_count"] == 2
    assert "graph_sidecar_not_exported" in status["graph"]["diagnostics"]
    assert plan["current_status"]["needs_graph_maintenance"] is True
    assert plan["current_status"]["graph_dirty_count"] == 7
    assert plan["current_status"]["graph_missing_count"] == 2
    assert any("auto-maintenance hot" in command for command in plan["allowed_operator_commands"])
    assert any("auto-maintenance backlog" in command for command in plan["allowed_operator_commands"])
    assert any("graph-maintenance all" in command for command in plan["allowed_operator_commands"])
    assert plan["maintenance_lanes"]["deep"].startswith("offline full-depth")
    assert any("force-large-export" in command for command in plan["offline_operator_commands"])


def test_trace_and_search_use_allowlisted_archive_commands(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    trace = state.session_trace("aoa-session-memory-mcp", kind="auto", limit=5)
    search = state.session_search("aoa-session-memory", filters={"route_layer": "mcp"}, limit=5)

    assert trace["route_candidates"][0]["route_signal"] == "mcp:aoa_session_memory_mcp"
    assert search["results"][0]["freshness"]["status"] == "fresh"
    assert any(call[0] == "trace-route" for call in runner.calls)
    assert any(call[0] == "search" and "--route-layer" in call[1] for call in runner.calls)


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
    assert args[args.index("--session") + 1] == "session-1"
    assert args[args.index("--agent-event") + 1] == "assistant_final_closeout"
    assert args[args.index("--task-episode-id") + 1] == "task-0001"
    assert "--explain" not in args


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
    assert neighborhood["artifact_type"] == "agent_event_windows"
    calls = {call[0]: call[1] for call in runner.calls}
    response_args = calls["agent-responses"]
    assert response_args[response_args.index("--agent-event") + 1] == "assistant_final_closeout"
    assert response_args[response_args.index("--task-episode-id") + 1] == "task-0001"
    assert "agent-progress-updates" in calls
    assert "agent-reasoning-windows" in calls
    assert "answer-neighborhood" in calls
    episode_args = calls["task-episodes"]
    assert episode_args[episode_args.index("--status") + 1] == "closed"
    assert episode_args[episode_args.index("--verification-state") + 1] == "verified"


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
    assert "aoa_session_answer_neighborhood" in tools
    assert "aoa_session_entity_usage_neighborhood" in tools
    assert "aoa_session_hook_receipts" in tools
    assert "aoa_session_entity_inventory" in tools
    assert tools["aoa_session_hook_receipts"].inputSchema["properties"]["event_name"]["default"] == "UserPromptSubmit"
    assert tools["aoa_session_entity_inventory"].inputSchema["properties"]["layer"]["default"] == "skill"


def test_entity_inventory_prefers_atlas_and_falls_back_to_route_terms(tmp_path: Path) -> None:
    state = state_with_fixture(tmp_path)

    skill_inventory = state.session_entity_inventory(layer="skill", limit=5)
    eval_inventory = state.session_entity_inventory(layer="eval", limit=5)
    git_inventory = state.session_entity_inventory(layer="git", limit=5)
    playbook_inventory = state.session_entity_inventory(layer="playbook", limit=5)
    technique_inventory = state.session_entity_inventory(layer="technique", limit=5)
    mechanic_inventory = state.session_entity_inventory(layer="mechanic", limit=5)

    assert skill_inventory["truth_status"] == "session route-signal inventory; not runtime installed inventory"
    assert skill_inventory["source"] == "atlas"
    assert skill_inventory["entities"][0]["key"] == "aoa_decision"
    assert skill_inventory["entities"][0]["signal_count"] == 4
    assert skill_inventory["entities"][0]["samples"][0]["doc_type"] == "atlas_entry"
    assert skill_inventory["entities"][0]["samples"][0]["refs"]["raw"] == "raw:line:2"
    assert eval_inventory["source"] == "portable_sqlite"
    assert eval_inventory["entities"][0]["key"] == "inspect_ai"
    assert git_inventory["entities"][0]["key"] == "git"
    assert playbook_inventory["entities"][0]["key"] == "session_audit"
    assert technique_inventory["entities"][0]["key"] == "entity_routing"
    assert mechanic_inventory["entities"][0]["key"] == "route_maintenance"


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
    assert [timeout for command, timeout in runner.timeouts if command == "search-provider-status"] == [60.0, 60.0]


def test_freshness_check_keeps_target_refs_ok_when_unrelated_session_is_stale(tmp_path: Path) -> None:
    runner = StaleProviderRunner(dirty_session_id="session-other", dirty_session_label="2026-05-26__002__other")
    state = state_with_fixture(tmp_path, runner)

    freshness = state.session_freshness_check(["raw:line:1"], session="session-1")

    assert freshness["ok"] is True
    assert freshness["provider"]["ok"] is False
    assert freshness["projection_freshness"]["status"] == "current_with_global_stale"
    assert "provider_global_stale_target_session_current" in freshness["diagnostics"]


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
    assert runner.timeouts[-1] == ("entity-usage-neighborhood", 90.0)


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
