#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aoa_course_connector_mcp.core import AoACourseConnectorMCPState  # noqa: E402
from aoa_course_connector_mcp.server import build_server  # noqa: E402


def owner_call(name: str, args: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "aoa_course_mcp_result_v1",
        "tool": name,
        "arguments": args,
        "catalog": {
            "network_touched": False,
            "read_only": True,
        },
    }


def main() -> None:
    state = AoACourseConnectorMCPState(
        connector_repo=Path("/nonexistent-owner-fixture"),
        owner_call=owner_call,
    )
    sources = state.list_sources()
    tools = asyncio.run(build_server(state).list_tools())
    if sources["owner_result"]["arguments"]["include_source_refs"] is not False:
        raise SystemExit("course source refs are not fail-closed")
    if len(tools) != 9 or any(
        tool.annotations.read_only_hint is not True for tool in tools
    ):
        raise SystemExit("course read tool catalog drifted")
    print(json.dumps({"ok": True, "tool_count": len(tools)}, indent=2))


if __name__ == "__main__":
    main()
