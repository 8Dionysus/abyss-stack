from __future__ import annotations

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

    server = build_server()
    if server is None:
        raise SystemExit("MCP server did not build")

    print(json.dumps({"ok": True, "brief_schema": brief["schema"]}, indent=2))


if __name__ == "__main__":
    main()
