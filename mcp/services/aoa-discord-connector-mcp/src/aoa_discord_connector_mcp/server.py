"""FastMCP server for the Discord connector access plane."""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from aoa_discord_connector_mcp._http_auth import http_auth_kwargs as _http_auth_kwargs
from aoa_discord_connector_mcp._http_auth import transport_settings as _transport_settings
from aoa_discord_connector_mcp.core import AoADiscordConnectorMCPState

LOGGER = logging.getLogger(__name__)
DEFAULT_HTTP_PORT = 5428


def _run_server(server: Any) -> None:
    settings = _transport_settings(DEFAULT_HTTP_PORT)
    _http_auth_kwargs(DEFAULT_HTTP_PORT)
    if settings.transport == "stdio":
        server.run(transport="stdio")
        return
    assert settings.host is not None
    assert settings.port is not None
    server.settings.host = settings.host
    server.settings.port = settings.port
    server.run(transport="streamable-http")


def build_server(state: AoADiscordConnectorMCPState | None = None) -> FastMCP:
    service_state = state or AoADiscordConnectorMCPState.discover()
    mcp = FastMCP(
        "aoa-discord-connector-mcp",
        json_response=True,
        **_http_auth_kwargs(DEFAULT_HTTP_PORT),
    )

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
    _run_server(build_server())


if __name__ == "__main__":
    main()
