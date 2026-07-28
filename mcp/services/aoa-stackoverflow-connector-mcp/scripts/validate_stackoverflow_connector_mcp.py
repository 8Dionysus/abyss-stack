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

from aoa_stackoverflow_connector_mcp.core import (  # noqa: E402
    AoAStackOverflowConnectorMCPState,
)
from aoa_stackoverflow_connector_mcp.server import build_server  # noqa: E402


def runner(
    argv: Sequence[str],
    _env: dict[str, str],
    _timeout: float,
    _cwd: Path | None,
) -> subprocess.CompletedProcess[str]:
    payload: dict[str, object] = {
        "schema": "aoa_stackoverflow_status_v1",
        "status": "ok",
        "network_touched": False,
        "read_only": True,
    }
    if "answer" in argv:
        payload.update(
            {
                "schema": "aoa_connector_answer_packet_v1",
                "agent_answer": {"status": "answered"},
                "evidence_chain": [{"question_id": "so-1"}],
                "answer_report": {},
                "conflict_report": {},
                "freshness_report": {},
                "applicability_report": {},
                "warning_report": {},
                "score_signal_report": {"accepted_answer_is_truth": False},
            }
        )
    return subprocess.CompletedProcess(list(argv), 0, json.dumps(payload), "")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = AoAStackOverflowConnectorMCPState(
            connector_repo=Path(tmp),
            runner=runner,
        )
        answer = state.answer("python error")
        tools = asyncio.run(build_server(state).list_tools())
    if answer["status"] != "ok" or len(tools) != 4:
        raise SystemExit("StackOverflow connector MCP validation failed")
    if any(tool.annotations.readOnlyHint is not True for tool in tools):
        raise SystemExit("StackOverflow annotations drifted")
    print(json.dumps({"ok": True, "tool_count": len(tools)}, indent=2))


if __name__ == "__main__":
    main()
