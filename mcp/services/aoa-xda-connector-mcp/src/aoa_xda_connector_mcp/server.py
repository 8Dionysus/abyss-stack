"""FastMCP server for the XDA connector read contour."""

from __future__ import annotations

import json
import logging
from importlib.metadata import PackageNotFoundError, distribution
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ._http_auth import http_auth_kwargs, transport_settings
from .core import AoAXDAConnectorMCPState

LOGGER = logging.getLogger(__name__)
PACKAGE_NAME = "aoa-xda-connector-mcp"
SOURCE_FALLBACK_VERSION = "0.1.0"
DEFAULT_HTTP_PORT = 5438
READ_TOKEN_ENV = "AOA_XDA_CONNECTOR_MCP_READ_BEARER_TOKEN"
READ_CREDENTIAL = "aoa-xda-connector-mcp-read-bearer-token"
READ_SCOPE = "mcp:aoa-xda-connector:read"
READ_CLIENT_ID = "aoa-loopback-codex:aoa-xda-connector:read"


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
    return http_auth_kwargs(
        DEFAULT_HTTP_PORT,
        token_env_var=READ_TOKEN_ENV,
        credential_name=READ_CREDENTIAL,
        auth_scope=READ_SCOPE,
        client_id=READ_CLIENT_ID,
    )


def build_server(state: AoAXDAConnectorMCPState | None = None) -> FastMCP:
    service_state = state or AoAXDAConnectorMCPState.discover()
    mcp = FastMCP(
        "aoa-xda-connector-mcp",
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
    def aoa_xda_connector_status() -> dict[str, Any]:
        """Inspect local XDA connector and storage posture without network access."""
        return service_state.status()

    @read_tool
    def aoa_xda_connector_source_route() -> dict[str, Any]:
        """Return source/access ownership, wrapped commands, and stop lines."""
        return service_state.source_route()

    @read_tool
    def aoa_xda_connector_query_graph(
        query: str,
        run: str = "starter-fixture",
        limit: int = 5,
    ) -> dict[str, Any]:
        """Query already-built local XDA graph evidence."""
        return service_state.query_graph(query, run, limit)

    @read_tool
    def aoa_xda_connector_answer(
        query: str,
        run: str = "starter-fixture",
        limit: int = 5,
    ) -> dict[str, Any]:
        """Return an owner-produced local XDA answer packet."""
        return service_state.answer(query, run, limit)

    @mcp.resource("aoa-xda://source-route")
    def source_route_resource() -> str:
        return json.dumps(service_state.source_route(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-xda://status")
    def status_resource() -> str:
        return json.dumps(service_state.status(), ensure_ascii=False, indent=2)

    @mcp.prompt(name="xda-answer")
    def answer_prompt(query: str, run: str = "starter-fixture") -> str:
        return (
            f"Use aoa_xda_connector_answer(query={query!r}, run={run!r}). "
            "Inspect evidence_chain, conflicts, freshness, applicability, warnings, "
            "source URLs, post ids, and limitations before making a stronger claim."
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
    LOGGER.info("AoA XDA connector MCP read contour ready")
    _run_server(build_server())
