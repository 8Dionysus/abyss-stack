#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from abyss_machine_mcp.core import AbyssMachineMCPState  # noqa: E402
from abyss_machine_mcp.server import build_server  # noqa: E402


def main() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "src/abyss_machine_mcp/core.py",
        "src/abyss_machine_mcp/server.py",
        "src/abyss_machine_mcp/cli.py",
        "scripts/abyss_machine_mcp_server.py",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    state = AbyssMachineMCPState.discover(timeout_seconds=15)
    brief = state.machine_brief(profile="fast")
    if brief["authority_boundary"]["mcp_role"] != "stdio read-only access plane over abyss-machine host read models":
        raise SystemExit("authority boundary drifted")
    if brief["constraints"]["mutation_gates"] in (None, []):
        raise SystemExit("machine brief lost mutation gate refs")
    if brief["evidence"]["count"] <= 0:
        raise SystemExit("machine brief lost evidence refs")

    memory = state.surface("memory-pressure")
    if not memory["ok"]:
        raise SystemExit(f"memory pressure surface failed: {memory}")
    typing = state.surface("typing-status")
    if not typing["ok"]:
        raise SystemExit(f"typing status surface failed: {typing}")
    maps = state.machine_maps(axis="by-freshness", query="semantic", limit=4)
    if not maps["ok"]:
        raise SystemExit(f"machine maps surface failed: {maps}")
    packet = state.machine_context_packet(axis="by-eval-packet", reader_profile="proof-context", limit=4)
    if not packet["ok"]:
        raise SystemExit(f"machine context packet surface failed: {packet}")
    if packet.get("packet_schema") not in {"abyss_machine_maps_context_packet_v1", "abyss_machine_maps_packet_v1"}:
        raise SystemExit(f"machine context packet schema drifted: {packet}")
    maps_validate = state.surface("maps-validate")
    if not maps_validate["ok"]:
        raise SystemExit(f"machine maps validator surface failed: {maps_validate}")
    rag = state.machine_rag_trace("validate abyss-machine MCP RAG trace", limit=4, evidence_limit=6)
    if not rag["ok"]:
        raise SystemExit(f"machine RAG trace surface failed: {rag}")
    if rag.get("trace_schema") != "abyss_machine_rag_trace_v1":
        raise SystemExit(f"machine RAG trace schema drifted: {rag}")
    if rag.get("eval", {}).get("ok") is not True:
        raise SystemExit(f"machine RAG trace eval failed: {rag}")
    rag_validate = state.surface("rag-validate")
    if not rag_validate["ok"]:
        raise SystemExit(f"machine RAG validator surface failed: {rag_validate}")
    route = state.machine_route("validate abyss-machine MCP route posture", work_class="heavy", kind="ai")
    if route["mutates"]:
        raise SystemExit("route tool must remain non-mutating")
    if route["route_posture"] != "preflight_only":
        raise SystemExit("route tool posture drifted")

    server = build_server()
    if server is None:
        raise SystemExit("MCP server did not build")

    print(
        json.dumps(
            {
                "ok": True,
                "brief_schema": brief["schema"],
                "bridge_status": brief["machine"]["bridge_status"],
                "evidence_count": brief["evidence"]["count"],
                "memory_surface_ok": memory["ok"],
                "typing_surface_ok": typing["ok"],
                "maps_surface_ok": maps["ok"],
                "maps_result_count": maps["result_count"],
                "context_packet_ok": packet["ok"],
                "context_packet_schema": packet.get("packet_schema"),
                "rag_trace_ok": rag["ok"],
                "rag_trace_schema": rag.get("trace_schema"),
                "rag_eval_ok": rag.get("eval", {}).get("ok"),
                "route_posture": route["route_posture"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
