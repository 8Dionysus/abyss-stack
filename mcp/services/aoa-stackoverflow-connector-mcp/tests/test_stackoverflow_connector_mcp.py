from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Sequence

from aoa_stackoverflow_connector_mcp.core import (
    AoAStackOverflowConnectorMCPState,
)
from aoa_stackoverflow_connector_mcp.server import build_server


def runner(
    argv: Sequence[str],
    _env: dict[str, str],
    _timeout: float,
    _cwd: Path | None,
) -> subprocess.CompletedProcess[str]:
    payload = {
        "schema": "aoa_connector_answer_packet_v1",
        "status": "ok",
        "agent_answer": {"status": "answered"},
        "evidence_chain": [{"question_id": "so-1"}],
        "answer_report": {},
        "conflict_report": {},
        "freshness_report": {},
        "applicability_report": {},
        "warning_report": {},
        "score_signal_report": {"accepted_answer_is_truth": False},
        "network_touched": False,
        "read_only": True,
    }
    return subprocess.CompletedProcess(list(argv), 0, json.dumps(payload), "")


def test_answer_preserves_score_signal_boundary(tmp_path: Path) -> None:
    state = AoAStackOverflowConnectorMCPState(
        connector_repo=tmp_path,
        runner=runner,
    )
    packet = state.answer("python error")
    assert packet["status"] == "ok"
    assert packet["score_signal_report"]["accepted_answer_is_truth"] is False


def test_server_is_small_and_annotated(tmp_path: Path) -> None:
    state = AoAStackOverflowConnectorMCPState(
        connector_repo=tmp_path,
        runner=runner,
    )
    server = build_server(state)
    tools = asyncio.run(server.list_tools())
    assert server._mcp_server.version == "0.1.0"
    assert len(tools) == 4
    assert all(tool.annotations.read_only_hint is True for tool in tools)
    assert all(tool.annotations.open_world_hint is False for tool in tools)
