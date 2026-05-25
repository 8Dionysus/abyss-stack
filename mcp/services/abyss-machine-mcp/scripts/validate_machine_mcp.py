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
                "route_posture": route["route_posture"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
