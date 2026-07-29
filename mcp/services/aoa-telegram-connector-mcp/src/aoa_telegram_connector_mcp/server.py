"""FastMCP server for the Telegram connector access plane."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, distribution
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from aoa_telegram_connector_mcp._http_auth import http_auth_kwargs as _http_auth_kwargs
from aoa_telegram_connector_mcp._http_auth import transport_settings as _transport_settings
from aoa_telegram_connector_mcp.core import AoATelegramConnectorMCPState

LOGGER = logging.getLogger(__name__)
PACKAGE_NAME = "aoa-telegram-connector-mcp"
SOURCE_FALLBACK_VERSION = "0.2.0"
DEFAULT_HTTP_PORT = 5427
READ_TOKEN_ENV = "AOA_TELEGRAM_CONNECTOR_MCP_READ_BEARER_TOKEN"
READ_CREDENTIAL = "aoa-telegram-connector-mcp-read-bearer-token"
READ_SCOPE = "mcp:aoa-telegram-connector:read"
READ_CLIENT_ID = "aoa-loopback-codex:aoa-telegram-connector:read"


def _application_version() -> str:
    try:
        discovered = distribution(PACKAGE_NAME).metadata.get("Version")
    except PackageNotFoundError:
        return SOURCE_FALLBACK_VERSION
    return (
        discovered.strip()
        if isinstance(discovered, str) and discovered.strip()
        else SOURCE_FALLBACK_VERSION
    )


def _bind_server_info_version(mcp: Any) -> None:
    low_level_server = getattr(mcp, "_mcp_server", None)
    if low_level_server is None or not hasattr(low_level_server, "version"):
        raise RuntimeError(
            "the pinned MCP SDK no longer exposes the server identity seam"
        )
    low_level_server.version = _application_version()


def _read_http_auth_kwargs() -> dict[str, Any]:
    return _http_auth_kwargs(
        DEFAULT_HTTP_PORT,
        token_env_var=READ_TOKEN_ENV,
        credential_name=READ_CREDENTIAL,
        auth_scope=READ_SCOPE,
        client_id=READ_CLIENT_ID,
    )


def _run_server(server: Any) -> None:
    settings = _transport_settings(DEFAULT_HTTP_PORT)
    _read_http_auth_kwargs()
    if settings.transport == "stdio":
        server.run(transport="stdio")
        return
    assert settings.host is not None
    assert settings.port is not None
    server.settings.host = settings.host
    server.settings.port = settings.port
    server.run(transport="streamable-http")


def build_server(state: AoATelegramConnectorMCPState | None = None) -> FastMCP:
    service_state = state or AoATelegramConnectorMCPState.discover()
    mcp = FastMCP(
        "aoa-telegram-connector-mcp",
        json_response=True,
        **_read_http_auth_kwargs(),
    )
    _bind_server_info_version(mcp)
    read_only_tool = mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
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
