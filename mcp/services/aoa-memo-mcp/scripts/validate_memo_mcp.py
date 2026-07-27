from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aoa_memo_mcp.core import AoAMemoMCPState  # noqa: E402
from aoa_memo_mcp.server import build_server  # noqa: E402


def main() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "src/aoa_memo_mcp/core.py",
        "src/aoa_memo_mcp/server.py",
        "scripts/aoa_memo_mcp_server.py",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    state = AoAMemoMCPState.discover()
    brief = state.build_brief("Agents-of-Abyss", "validate access plane")
    if brief["local_port"]["present"] and not brief["local_port"]["ready"]:
        raise SystemExit("Agents-of-Abyss memo port exists but is not ready")

    read_server = build_server(policy_family="read")
    candidate_server = build_server(policy_family="candidate")

    async def tool_inventory(server):
        return {
            tool.name: tool.annotations
            for tool in await server.list_tools()
        }

    read_tools = asyncio.run(tool_inventory(read_server))
    candidate_tools = asyncio.run(tool_inventory(candidate_server))
    if set(read_tools) & set(candidate_tools):
        raise SystemExit("memo read and candidate tool catalogs overlap")
    if not read_tools or not candidate_tools:
        raise SystemExit("memo MCP contour tool catalog is empty")
    if any(
        annotations.readOnlyHint is not True
        or annotations.destructiveHint is not False
        for annotations in read_tools.values()
    ):
        raise SystemExit("memo read tool annotations drifted")
    if any(
        annotations.readOnlyHint is not False
        or annotations.destructiveHint is not True
        for annotations in candidate_tools.values()
    ):
        raise SystemExit("memo candidate tool annotations drifted")

    print(
        json.dumps(
            {
                "ok": True,
                "brief_schema": brief["schema"],
                "read_tool_count": len(read_tools),
                "candidate_tool_count": len(candidate_tools),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
