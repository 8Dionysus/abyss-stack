#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aoa_xda_connector_mcp.core import AoAXDAConnectorMCPState  # noqa: E402
from aoa_xda_connector_mcp.server import build_server  # noqa: E402


def fake_runner(
    argv: Sequence[str],
    _env: dict[str, str],
    _timeout: float,
    _cwd: Path | None,
) -> subprocess.CompletedProcess[str]:
    payload: dict[str, object] = {
        "schema": "aoa_xda_status_v1",
        "status": "ok",
        "network_touched": False,
        "read_only": True,
    }
    if "answer" in argv:
        payload.update(
            {
                "schema": "aoa_connector_answer_packet_v1",
                "agent_answer": {"status": "answered"},
                "evidence_chain": [{"post_id": "xda-1"}],
                "answer_report": {"answer_status": "answered"},
                "conflict_report": {"status": "no_conflict"},
                "freshness_report": {"status": "current"},
                "applicability_report": {"status": "applicable"},
                "warning_report": {"status": "none"},
            }
        )
    return subprocess.CompletedProcess(list(argv), 0, json.dumps(payload), "")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "aoa-xda-connector"
        (repo / "src" / "aoa_xda_connector").mkdir(parents=True)
        state = AoAXDAConnectorMCPState(connector_repo=repo, runner=fake_runner)
        answer = state.answer("fastboot recovery warning")
        server = build_server(state)
        tools = asyncio.run(server.list_tools())
    if answer["status"] != "ok" or len(tools) != 4:
        raise SystemExit("XDA connector MCP validation failed")
    if any(tool.annotations.readOnlyHint is not True for tool in tools):
        raise SystemExit("XDA connector MCP annotations drifted")
    print(json.dumps({"ok": True, "tool_count": len(tools)}, indent=2))


if __name__ == "__main__":
    main()
