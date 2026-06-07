from __future__ import annotations

import json
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
    write_json(
        aoa / "maps/index.json",
        {
            "schema_version": 1,
            "artifact_type": "agent_atlas_index",
            "generated_at": "2026-05-26T00:00:00Z",
            "axis_count": 1,
            "entry_count": 1,
            "axes": [{"axis": "by-mcp", "entry_count": 1, "index": (aoa / "maps/by-mcp/index.json").as_posix()}],
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

    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        command = argv[2]
        args = tuple(argv[3:])
        self.calls.append((command, args))
        if command == "search-provider-status":
            payload = PROVIDER_STATUS
        elif command == "route-readiness":
            payload = ROUTE_READINESS_FAST_GATE
        elif command == "search":
            payload = SEARCH_RESULTS
        elif command == "trace-route":
            payload = TRACE_RESULTS
        elif command == "entity-usage-audit":
            payload = ENTITY_USAGE_AUDIT
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
    state = state_with_fixture(tmp_path)
    status = state.session_memory_status()

    assert status["schema"] == "aoa_session_memory_status_v1"
    assert status["provider"]["ok"] is True
    assert status["atlas"]["entry_count"] == 1
    assert status["latest_route_readiness"]["reports"][0]["summary"]["ok"] is True
    assert status["readiness_policy"]["cached_route_readiness"]["status_field"] == "latest_route_readiness"
    assert status["authority_boundary"]["mutation_posture"].startswith("no write")


def test_status_live_readiness_uses_fast_gate_without_evidence_samples(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = state_with_fixture(tmp_path, runner)

    status = state.session_memory_status(include_live=True)

    route_calls = [call for call in runner.calls if call[0] == "route-readiness"]
    assert len(route_calls) == 1
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
    assert "graph_sidecar_not_exported" in status["graph"]["diagnostics"]
    assert any("graph-maintenance all" in command for command in plan["allowed_operator_commands"])
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
