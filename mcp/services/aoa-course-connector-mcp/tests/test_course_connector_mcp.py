from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aoa_course_connector_mcp.core import AoACourseConnectorMCPState
from aoa_course_connector_mcp.server import build_server


def call(name: str, args: dict[str, object]) -> dict[str, object]:
    return {"tool": name, "arguments": args, "network_touched": False}


def test_source_refs_are_forced_off() -> None:
    state = AoACourseConnectorMCPState(Path("/fixture"), owner_call=call)
    result = state.list_sources()
    assert result["owner_result"]["arguments"]["include_source_refs"] is False


def test_effect_tool_is_denied() -> None:
    state = AoACourseConnectorMCPState(Path("/fixture"), owner_call=call)
    with pytest.raises(PermissionError):
        state._call("connected_run", {"mode": "fixture"})


def test_owner_network_report_fails_closed() -> None:
    state = AoACourseConnectorMCPState(
        Path("/fixture"),
        owner_call=lambda _name, _args: {"network_touched": True},
    )
    with pytest.raises(PermissionError):
        state.status()


def test_server_catalog_is_read_only() -> None:
    state = AoACourseConnectorMCPState(Path("/fixture"), owner_call=call)
    tools = asyncio.run(build_server(state).list_tools())
    assert len(tools) == 9
    assert all(tool.annotations.readOnlyHint is True for tool in tools)
    assert all(tool.annotations.openWorldHint is False for tool in tools)
