"""MCP 2.x server for the StackOverflow connector read contour."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import ToolAnnotations

from ._http_auth import http_auth_config
from ._modern_runtime import ModernMCPServer, run_server
from ._runtime_config import SERVICE_CONFIG
from .core import AoAStackOverflowConnectorMCPState

LOGGER = logging.getLogger(__name__)


def _read_http_auth_config() -> Any:
    contour = SERVICE_CONFIG.contour("read")
    return http_auth_config(contour.port, **contour.auth.as_kwargs())


def build_server(
    state: AoAStackOverflowConnectorMCPState | None = None,
) -> ModernMCPServer:
    service_state = state or AoAStackOverflowConnectorMCPState.discover()
    mcp = ModernMCPServer(
        SERVICE_CONFIG.server_name("read"),
        version=SERVICE_CONFIG.package_version,
        **_read_http_auth_config().server_kwargs,
    )
    read_tool = mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )

    @read_tool
    def aoa_stackoverflow_connector_status() -> dict[str, Any]:
        """Inspect local connector and storage posture without network access."""
        return service_state.status()

    @read_tool
    def aoa_stackoverflow_connector_source_route() -> dict[str, Any]:
        """Return ownership, wrapped commands, and stop lines."""
        return service_state.source_route()

    @read_tool
    def aoa_stackoverflow_connector_query_graph(
        query: str,
        run: str = "starter-fixture",
        limit: int = 5,
    ) -> dict[str, Any]:
        """Query already-built local StackOverflow graph evidence."""
        return service_state.query_graph(query, run, limit)

    @read_tool
    def aoa_stackoverflow_connector_answer(
        query: str,
        run: str = "starter-fixture",
        limit: int = 5,
    ) -> dict[str, Any]:
        """Return an owner-produced local StackOverflow answer packet."""
        return service_state.answer(query, run, limit)

    @mcp.resource("aoa-stackoverflow://source-route")
    def source_route_resource() -> str:
        return json.dumps(service_state.source_route(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-stackoverflow://status")
    def status_resource() -> str:
        return json.dumps(service_state.status(), ensure_ascii=False, indent=2)

    @mcp.prompt(name="stackoverflow-answer")
    def answer_prompt(query: str, run: str = "starter-fixture") -> str:
        return (
            f"Use aoa_stackoverflow_connector_answer(query={query!r}, run={run!r}). "
            "Inspect evidence, conflicts, freshness, applicability, warnings, and "
            "score signals; accepted-answer and score signals are not truth."
        )
    return mcp


def _run_server(server: Any) -> None:
    run_server(server, _read_http_auth_config())


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    LOGGER.info("AoA StackOverflow connector MCP read contour ready")
    _run_server(build_server())
