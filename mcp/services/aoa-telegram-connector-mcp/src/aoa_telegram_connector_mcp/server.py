"""MCP 2.x server for the Telegram connector access plane."""

from __future__ import annotations

import logging
from typing import Any

from mcp.types import ToolAnnotations

from aoa_telegram_connector_mcp._http_auth import http_auth_config
from aoa_telegram_connector_mcp._modern_runtime import ModernMCPServer, run_server
from aoa_telegram_connector_mcp._runtime_config import SERVICE_CONFIG
from aoa_telegram_connector_mcp.core import AoATelegramConnectorMCPState

LOGGER = logging.getLogger(__name__)


def _read_http_auth_config() -> Any:
    contour = SERVICE_CONFIG.contour("read")
    return http_auth_config(contour.port, **contour.auth.as_kwargs())


def _run_server(server: Any) -> None:
    run_server(server, _read_http_auth_config())


def build_server(state: AoATelegramConnectorMCPState | None = None) -> ModernMCPServer:
    service_state = state or AoATelegramConnectorMCPState.discover()
    mcp = ModernMCPServer(
        SERVICE_CONFIG.server_name("read"),
        version=SERVICE_CONFIG.package_version,
        **_read_http_auth_config().server_kwargs,
    )
    read_only_tool = mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )

    @read_only_tool
    def aoa_telegram_connector_status() -> dict[str, Any]:
        """Return local Telegram connector doctor, storage, and policy status."""

        return service_state.status()

    @read_only_tool
    def aoa_telegram_connector_source_route() -> dict[str, Any]:
        """Return MCP/source ownership and read-only boundary information."""

        return service_state.source_route()

    @read_only_tool
    def aoa_telegram_connector_answer(query: str, run: str = "latest", limit: int = 5) -> dict[str, Any]:
        """Answer from already-built local Telegram connector evidence."""

        return service_state.answer(query, run=run, limit=limit)

    @read_only_tool
    def aoa_telegram_connector_query_graph(query: str, run: str = "latest", limit: int = 5) -> dict[str, Any]:
        """Query the already-built local Telegram graph/index evidence."""

        return service_state.query_graph(query, run=run, limit=limit)

    @mcp.resource("aoa-telegram://source-route")
    def source_route_resource() -> dict[str, Any]:
        return service_state.source_route()

    @mcp.resource("aoa-telegram://status")
    def status_resource() -> dict[str, Any]:
        return service_state.status()

    @mcp.prompt(name="telegram-answer")
    def telegram_answer_prompt(query: str, run: str = "latest") -> str:
        return (
            f"Use aoa_telegram_connector_answer(query={query!r}, run={run!r}) first. "
            "Ground the response in evidence_chain, permission_report, answer_report, "
            "freshness_report, applicability_report, and warning_report. "
            "Do not claim the connector performed live network search."
        )

    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    LOGGER.info("AoA Telegram connector MCP server ready")
    _run_server(build_server())


if __name__ == "__main__":
    main()
