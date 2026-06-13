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
    route_only = state.session_search("", filters={"route_signal": "tool:view_image", "doc_type": "event"}, limit=3)
    if route_only.get("result_count", 0) <= 0:
        raise SystemExit("route-only session search returned no smoke hits")
    skill_inventory = state.session_entity_inventory(layer="skill", limit=5)
    if not skill_inventory.get("ok") or skill_inventory.get("entity_count", 0) <= 0:
        raise SystemExit(f"skill entity inventory failed: {skill_inventory.get('diagnostics')}")
    git_inventory = state.session_entity_inventory(layer="git", limit=5)
    if not git_inventory.get("ok") or git_inventory.get("entity_count", 0) <= 0:
        raise SystemExit(f"git entity inventory failed: {git_inventory.get('diagnostics')}")
    hook_receipts = state.session_hook_receipts(event_name="UserPromptSubmit", limit=5)
    if not hook_receipts.get("ok"):
        raise SystemExit(f"hook receipts surface failed: {hook_receipts.get('diagnostics')}")
    neighborhood = state.session_entity_usage_neighborhood(
        "view_image",
        kind="tool",
        limit=1,
        per_route_limit=3,
        before=1,
        after=3,
        raw_preview_chars=240,
    )
    if not neighborhood.get("ok") or not neighborhood.get("neighborhoods"):
        raise SystemExit(f"usage neighborhood returned no evidence windows: {neighborhood.get('diagnostics')}")
    brief = state.session_brief("latest", max_segments=2)
    if not brief.get("ok") or not brief.get("refs", {}).get("manifest"):
        raise SystemExit("latest session brief is not readable")
    latest_session = brief.get("session", {}).get("label") or "latest"
    session_only = state.session_search("", filters={"session": latest_session}, limit=1)
    if session_only.get("result_count", 0) <= 0 or session_only.get("provider", {}).get("status") != "local_session_filter_fast_path":
        raise SystemExit(f"session-only search fast path failed: {session_only.get('diagnostics')}")
    freshness_refs = [brief["refs"]["manifest"]]
    raw_path = Path(brief["refs"]["manifest"]).parent / "raw" / "session.raw.jsonl"
    raw_checked = raw_path.exists()
    if raw_checked:
        freshness_refs.append("raw:line:1")
    freshness = state.session_freshness_check(freshness_refs, session=latest_session)
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
                "route_only_result_count": route_only.get("result_count"),
                "skill_inventory_count": skill_inventory.get("entity_count"),
                "git_inventory_count": git_inventory.get("entity_count"),
                "session_only_result_count": session_only.get("result_count"),
                "hook_receipt_count": hook_receipts.get("total_receipt_count"),
                "hook_receipt_error_count": hook_receipts.get("summary", {}).get("error_receipt_count"),
                "usage_neighborhood_count": neighborhood.get("quality", {}).get("neighborhood_count"),
                "latest_session": latest_session,
                "raw_line_freshness_checked": raw_checked,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
