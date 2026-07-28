from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Sequence

from aoa_xda_connector_mcp.core import AoAXDAConnectorMCPState
from aoa_xda_connector_mcp.server import build_server


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
        "evidence_chain": [{"post_id": "xda-1"}],
        "answer_report": {},
        "conflict_report": {},
        "freshness_report": {},
        "applicability_report": {},
        "warning_report": {},
        "network_touched": False,
        "read_only": True,
    }
    return subprocess.CompletedProcess(list(argv), 0, json.dumps(payload), "")


def test_answer_preserves_owner_boundary(tmp_path: Path) -> None:
    state = AoAXDAConnectorMCPState(connector_repo=tmp_path, runner=runner)
    packet = state.answer("recovery warning")
    assert packet["status"] == "ok"
    assert packet["network_touched"] is False
    assert packet["read_only"] is True
    assert packet["evidence_chain"][0]["post_id"] == "xda-1"


def test_server_is_small_and_annotated(tmp_path: Path) -> None:
    server = build_server(
        AoAXDAConnectorMCPState(connector_repo=tmp_path, runner=runner)
    )
    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == {
        "aoa_xda_connector_answer",
        "aoa_xda_connector_query_graph",
        "aoa_xda_connector_source_route",
        "aoa_xda_connector_status",
    }
    assert all(tool.annotations.readOnlyHint is True for tool in tools)
    assert all(tool.annotations.openWorldHint is False for tool in tools)
