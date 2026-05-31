#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aoa_session_memory_mcp.core import AoASessionMemoryMCPState  # noqa: E402
from aoa_session_memory_mcp.server import build_server  # noqa: E402


def main() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "src/aoa_session_memory_mcp/core.py",
        "src/aoa_session_memory_mcp/server.py",
        "scripts/aoa_session_memory_mcp_server.py",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    state = AoASessionMemoryMCPState.discover()
    status = state.session_memory_status()
    if not status["provider"].get("ok"):
        raise SystemExit(f"search provider is not ready: {status['provider'].get('diagnostics')}")
    if not status["atlas"].get("root_index_exists"):
        raise SystemExit("atlas root index is missing")
    trace = state.session_trace("aoa-session-memory-mcp", kind="mcp", doc_type="session", limit=5, per_route_limit=3)
    if not trace.get("route_candidates"):
        raise SystemExit("trace-route did not return route candidates")
    search = state.session_search("aoa-session-memory", limit=3)
    if search.get("result_count", 0) <= 0:
        raise SystemExit("session search returned no smoke hits")
    brief = state.session_brief("latest", max_segments=2)
    if not brief.get("ok") or not brief.get("refs", {}).get("manifest"):
        raise SystemExit("latest session brief is not readable")
    freshness = state.session_freshness_check([brief["refs"]["manifest"]])
    if not freshness.get("ok"):
        raise SystemExit(f"freshness check failed: {freshness.get('checks')}")
    server = build_server()
    if server is None:
        raise SystemExit("MCP server did not build")

    print(
        json.dumps(
            {
                "ok": True,
                "aoa_root": status["aoa_root"],
                "provider_ok": status["provider"].get("ok"),
                "atlas_entry_count": status["atlas"].get("entry_count"),
                "trace_candidates": len(trace.get("route_candidates", [])),
                "search_result_count": search.get("result_count"),
                "latest_session": brief.get("session", {}).get("label"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
