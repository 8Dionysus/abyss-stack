"""FastMCP server for the Discord connector access plane."""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from aoa_discord_connector_mcp.core import AoADiscordConnectorMCPState

LOGGER = logging.getLogger(__name__)


def build_server(state: AoADiscordConnectorMCPState | None = None) -> FastMCP:
    service_state = state or AoADiscordConnectorMCPState.discover()
    mcp = FastMCP("aoa-discord-connector-mcp", json_response=True)

    @mcp.tool()
    def aoa_discord_connector_status() -> dict[str, Any]:
        """Return local Discord connector doctor, storage, and policy status."""

        return service_state.status()

    @mcp.tool()
    def aoa_discord_connector_source_route() -> dict[str, Any]:
        """Return MCP/source ownership and read-only boundary information."""

        return service_state.source_route()

    @mcp.tool()
    def aoa_discord_connector_answer(query: str, run: str = "latest", limit: int = 5) -> dict[str, Any]:
        """Answer from already-built local Discord connector evidence."""

        return service_state.answer(query, run=run, limit=limit)

    @mcp.tool()
    def aoa_discord_connector_query_graph(query: str, run: str = "latest", limit: int = 5) -> dict[str, Any]:
        """Query the already-built local Discord graph/index evidence."""

        return service_state.query_graph(query, run=run, limit=limit)

    @mcp.resource("aoa-discord://source-route")
    def source_route_resource() -> dict[str, Any]:
        return service_state.source_route()

    @mcp.resource("aoa-discord://status")
    def status_resource() -> dict[str, Any]:
        return service_state.status()

    @mcp.prompt(name="discord-answer")
    def discord_answer_prompt(query: str, run: str = "latest") -> str:
        return (
            f"Use aoa_discord_connector_answer(query={query!r}, run={run!r}) first. "
            "Ground the response in evidence_chain, permission_report, answer_report, "
            "freshness_report, applicability_report, and warning_report. "
            "Do not claim the connector performed live network search."
        )

    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    LOGGER.info("AoA Discord connector MCP server ready")
    build_server().run()


if __name__ == "__main__":
    main()
