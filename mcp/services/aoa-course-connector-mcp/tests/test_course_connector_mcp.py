from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aoa_course_connector_mcp.core import AoACourseConnectorMCPState
from aoa_course_connector_mcp.server import build_server


def call(name: str, args: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": "aoa_course_mcp_result_v1",
        "tool": name,
        "arguments": args,
    }
    if name == "list_sources":
        result["catalog"] = {"network_touched": False, "read_only": True}
    elif name in {"source_answer", "sources_answer"}:
        result[name] = {"network_touched": False, "read_only": True}
    return result


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
        owner_call=lambda name, _args: {
            "schema": "aoa_course_connector_readiness_v1",
            "tool": name,
            "network_touched": True,
            "read_only": True,
        },
    )
    with pytest.raises(PermissionError):
        state.status()


def test_owner_readiness_preserves_historical_and_planned_network_facts() -> None:
    state = AoACourseConnectorMCPState(
        Path("/fixture"),
        owner_call=lambda name, _args: {
            "schema": "aoa_course_connector_readiness_v1",
            "tool": name,
            "network_touched": False,
            "read_only": True,
            "sources": {
                "latest_connected_runs": [{"network_touched": True}],
            },
            "connected_source_plan": {
                "network_touched": False,
                "connected_run_plan": {"network_touched": True},
            },
        },
    )

    result = state.status()

    owner_result = result["owner_result"]
    assert owner_result["sources"]["latest_connected_runs"][0][
        "network_touched"
    ] is True
    assert owner_result["connected_source_plan"]["connected_run_plan"][
        "network_touched"
    ] is True
    assert result["network_touched"] is False


def test_current_read_attestation_is_required() -> None:
    state = AoACourseConnectorMCPState(
        Path("/fixture"),
        owner_call=lambda name, _args: {
            "schema": "aoa_course_mcp_result_v1",
            "tool": name,
            "catalog": {"network_touched": False},
        },
    )
    with pytest.raises(PermissionError, match="read_only=true"):
        state.list_sources()


def test_unattested_read_tool_retains_recursive_network_denial() -> None:
    state = AoACourseConnectorMCPState(
        Path("/fixture"),
        owner_call=lambda name, _args: {
            "schema": "aoa_course_mcp_result_v1",
            "tool": name,
            "evidence": {"network_touched": True},
        },
    )
    with pytest.raises(PermissionError, match="current network use"):
        state.evidence_report("bounded query")


def test_owner_tool_identity_mismatch_fails_closed() -> None:
    state = AoACourseConnectorMCPState(
        Path("/fixture"),
        owner_call=lambda _name, _args: {
            "schema": "aoa_course_mcp_result_v1",
            "tool": "sources_answer",
            "catalog": {"network_touched": False, "read_only": True},
        },
    )
    with pytest.raises(RuntimeError, match="tool identity mismatch"):
        state.list_sources()


def test_server_catalog_is_read_only() -> None:
    state = AoACourseConnectorMCPState(Path("/fixture"), owner_call=call)
    server = build_server(state)
    tools = asyncio.run(server.list_tools())
    assert server._mcp_server.version == "0.1.0"
    assert len(tools) == 9
    assert all(tool.annotations.readOnlyHint is True for tool in tools)
    assert all(tool.annotations.openWorldHint is False for tool in tools)
