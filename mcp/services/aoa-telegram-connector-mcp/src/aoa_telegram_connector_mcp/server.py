"""FastMCP server for the Telegram connector access plane."""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from aoa_telegram_connector_mcp.core import AoATelegramConnectorMCPState

LOGGER = logging.getLogger(__name__)
DEFAULT_HTTP_PORT = 5427


def _run_server(server: Any) -> None:
    transport = os.environ.get("AOA_MCP_TRANSPORT", "stdio").strip() or "stdio"
    if transport == "stdio":
        server.run(transport="stdio")
        return
    if transport != "streamable-http":
        raise SystemExit(f"unsupported AOA_MCP_TRANSPORT: {transport}")
    host = os.environ.get("AOA_MCP_HOST", "127.0.0.1").strip()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("AOA_MCP_HOST must remain loopback-only")
    server.settings.host = host
    server.settings.port = int(os.environ.get("AOA_MCP_PORT", DEFAULT_HTTP_PORT))
    server.run(transport="streamable-http")


def build_server(state: AoATelegramConnectorMCPState | None = None) -> FastMCP:
    service_state = state or AoATelegramConnectorMCPState.discover()
    mcp = FastMCP("aoa-telegram-connector-mcp", json_response=True)

    @mcp.tool()
    def aoa_telegram_connector_status() -> dict[str, Any]:
        """Return local Telegram connector doctor, storage, and policy status."""

        return service_state.status()

    @mcp.tool()
    def aoa_telegram_connector_source_route() -> dict[str, Any]:
        """Return MCP/source ownership and read-only boundary information."""

        return service_state.source_route()

    @mcp.tool()
    def aoa_telegram_connector_answer(query: str, run: str = "latest", limit: int = 5) -> dict[str, Any]:
        """Answer from already-built local Telegram connector evidence."""

        return service_state.answer(query, run=run, limit=limit)

    @mcp.tool()
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
