#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SRC = SERVICE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aoa_stats_mcp.core import AoAStatsMCPState  # noqa: E402
from aoa_stats_mcp.server import build_server  # noqa: E402


EXPECTED_TOOLS = {
    "stats_catalog",
    "stats_surface_read",
    "stats_boundary_rules",
    "stats_owner_port_read",
    "stats_packet_check",
}


def main() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "pyproject.toml",
        "src/aoa_stats_mcp/_http_auth.py",
        "src/aoa_stats_mcp/cli.py",
        "src/aoa_stats_mcp/core.py",
        "src/aoa_stats_mcp/server.py",
        "scripts/aoa_stats_mcp_server.py",
        "tests/test_stats_mcp.py",
    ]
    missing = [path for path in required if not (SERVICE_ROOT / path).is_file()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    state = AoAStatsMCPState.discover()
    catalog = state.catalog()
    surfaces = catalog.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise SystemExit("aoa-stats catalog returned no surfaces")
    inventory = state.owner_port_read()
    if inventory["owner_count"] < 1:
        raise SystemExit("aoa-stats owner inventory returned no owners")
    if any(owner.get("classification") == "unclassified" for owner in inventory["owners"]):
        raise SystemExit("aoa-stats owner inventory still has unclassified owners")
    central = state.owner_port_read(repo="aoa-stats")
    if central["status"] != "available":
        raise SystemExit("aoa-stats source home is not readable through owner-port access")
    boundary = state.boundary_rules()
    if boundary["source_owner"] != "aoa-stats" or boundary["access_owner"] != "abyss-stack":
        raise SystemExit("stats MCP boundary owners are incorrect")
    first_name = surfaces[0].get("name") if isinstance(surfaces[0], dict) else None
    if not isinstance(first_name, str):
        raise SystemExit("aoa-stats catalog first surface has no name")
    surface = state.surface_read(surface_name=first_name)
    if surface["status"] != "available":
        raise SystemExit(f"catalog surface is not readable: {first_name}")
    compatibility = state.packet_check(contract={}, packet={})
    if compatibility.get("truth_status") != "compatibility_check_only":
        raise SystemExit("public packet reader returned an unexpected truth status")
    if compatibility.get("compatible") is not False:
        raise SystemExit("invalid empty packet was not rejected")

    server = build_server()
    tools = asyncio.run(server.list_tools())
    actual_tools = {tool.name for tool in tools}
    if actual_tools != EXPECTED_TOOLS:
        raise SystemExit(
            f"unexpected stats MCP tool surface: expected={sorted(EXPECTED_TOOLS)} actual={sorted(actual_tools)}"
        )
    for tool in tools:
        annotations = tool.annotations
        if annotations is None or not (
            annotations.read_only_hint is True
            and annotations.destructive_hint is False
            and annotations.idempotent_hint is True
            and annotations.open_world_hint is False
        ):
            raise SystemExit(f"tool is not closed-world read-only: {tool.name}")
    if asyncio.run(server.list_resources()):
        raise SystemExit("unproven stats MCP resources are exposed")
    if asyncio.run(server.list_resource_templates()):
        raise SystemExit("unproven stats MCP resource templates are exposed")
    if asyncio.run(server.list_prompts()):
        raise SystemExit("unproven stats MCP prompts are exposed")

    print(
        json.dumps(
            {
                "ok": True,
                "tool_count": len(actual_tools),
                "surface_count": len(surfaces),
                "owner_count": inventory["owner_count"],
                "packet_reader_truth_status": compatibility["truth_status"],
                "write_tools": 0,
                "resource_count": 0,
                "prompt_count": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
