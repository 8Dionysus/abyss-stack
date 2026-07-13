#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aoa_decisions_mcp.core import AoADecisionsMCPState  # noqa: E402
from aoa_decisions_mcp.server import build_server  # noqa: E402


def main() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "src/aoa_decisions_mcp/core.py",
        "src/aoa_decisions_mcp/server.py",
        "scripts/aoa_decisions_mcp_server.py",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    state = AoADecisionsMCPState.discover()
    status = state.ensure_fresh()
    if status["issue_count"]:
        raise SystemExit(f"workspace decision graph has issues: {status['issue_count']}")
    if int(status.get("decision_surface_count") or 0) < int(status.get("decision_count") or 0):
        raise SystemExit("workspace decision graph is missing decision surface coverage counts")
    if status.get("freshness_scope") != "local_workspace_filesystem":
        raise SystemExit(f"unexpected freshness scope: {status.get('freshness_scope')}")
    if status.get("remote_freshness_checked") is not False:
        raise SystemExit("decision graph must not claim an unperformed remote freshness check")
    if sum(status.get("repo_source_posture_counts", {}).values()) != int(status.get("repo_count") or 0):
        raise SystemExit("decision graph source posture does not cover every repo")
    if len(status.get("source_warnings", [])) != int(status.get("source_warning_repo_count") or 0):
        raise SystemExit("decision graph source warning projection does not match its count")
    packet = state.packet(query="decision graph", limit=3)
    if packet["freshness"].get("cache_status") not in {"fresh", "refreshed"}:
        raise SystemExit(f"unexpected cache status: {packet['freshness'].get('cache_status')}")
    if packet["freshness"]["status"] not in {
        "fresh",
        "refreshed",
        "fresh-with-source-warnings",
        "refreshed-with-source-warnings",
    }:
        raise SystemExit(f"unexpected freshness status: {packet['freshness']['status']}")
    issues = state.issues()
    if issues["summary_issue_count"]:
        raise SystemExit(f"workspace decision graph issue packet is not clean: {issues['summary_issue_count']}")
    symmetry = state.repo_symmetry()
    if not symmetry["repos"]:
        raise SystemExit("workspace decision graph symmetry packet returned no repos")

    server = build_server()
    if server is None:
        raise SystemExit("MCP server did not build")

    print(
        json.dumps(
            {
                "ok": True,
                "status": status["status"],
                "decision_count": status["decision_count"],
                "decision_surface_count": status["decision_surface_count"],
                "source_warning_repo_count": status["source_warning_repo_count"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
