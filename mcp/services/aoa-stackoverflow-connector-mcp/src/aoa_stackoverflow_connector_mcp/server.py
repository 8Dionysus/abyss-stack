"""FastMCP server for the StackOverflow connector read contour."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ._http_auth import http_auth_kwargs, transport_settings
from .core import AoAStackOverflowConnectorMCPState

LOGGER = logging.getLogger(__name__)
PACKAGE_NAME = "aoa-stackoverflow-connector-mcp"
APPLICATION_VERSION = "0.1.0"
DEFAULT_HTTP_PORT = 5437
READ_TOKEN_ENV = "AOA_STACKOVERFLOW_CONNECTOR_MCP_READ_BEARER_TOKEN"
READ_CREDENTIAL = "aoa-stackoverflow-connector-mcp-read-bearer-token"
READ_SCOPE = "mcp:aoa-stackoverflow-connector:read"
READ_CLIENT_ID = "aoa-loopback-codex:aoa-stackoverflow-connector:read"


def _application_version() -> str:
    return APPLICATION_VERSION


def _bind_server_info_version(mcp: Any) -> None:
    low_level_server = getattr(mcp, "_mcp_server", None)
    if low_level_server is None or not hasattr(low_level_server, "version"):
        raise RuntimeError(
            "the pinned MCP SDK no longer exposes the server identity seam"
        )
    low_level_server.version = _application_version()


def _read_http_auth_kwargs() -> dict[str, Any]:
    return http_auth_kwargs(
        DEFAULT_HTTP_PORT,
        token_env_var=READ_TOKEN_ENV,
        credential_name=READ_CREDENTIAL,
        auth_scope=READ_SCOPE,
        client_id=READ_CLIENT_ID,
    )


def build_server(
    state: AoAStackOverflowConnectorMCPState | None = None,
) -> FastMCP:
    service_state = state or AoAStackOverflowConnectorMCPState.discover()
    mcp = FastMCP(
        "aoa-stackoverflow-connector-mcp",
        json_response=True,
        **_read_http_auth_kwargs(),
    )
    _bind_server_info_version(mcp)
    read_tool = mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
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
    settings = transport_settings(DEFAULT_HTTP_PORT)
    _read_http_auth_kwargs()
    if settings.transport == "stdio":
        server.run(transport="stdio")
        return
    server.settings.host = settings.host
    server.settings.port = settings.port
    server.run(transport="streamable-http")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    LOGGER.info("AoA StackOverflow connector MCP read contour ready")
    _run_server(build_server())
