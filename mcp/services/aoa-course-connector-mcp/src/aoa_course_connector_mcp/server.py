"""Authenticated FastMCP read contour for aoa-course-connector."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ._http_auth import http_auth_kwargs, transport_settings
from .core import AoACourseConnectorMCPState

LOGGER = logging.getLogger(__name__)
PACKAGE_NAME = "aoa-course-connector-mcp"
APPLICATION_VERSION = "0.1.0"
DEFAULT_HTTP_PORT = 5436
READ_TOKEN_ENV = "AOA_COURSE_CONNECTOR_MCP_READ_BEARER_TOKEN"
READ_CREDENTIAL = "aoa-course-connector-mcp-read-bearer-token"
READ_SCOPE = "mcp:aoa-course-connector:read"
READ_CLIENT_ID = "aoa-loopback-codex:aoa-course-connector:read"


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
    state: AoACourseConnectorMCPState | None = None,
) -> FastMCP:
    service_state = state or AoACourseConnectorMCPState.discover()
    mcp = FastMCP(
        "aoa-course-connector-mcp",
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
    def aoa_course_connector_status() -> dict[str, object]:
        """Inspect owner readiness without running a connected source."""
        return service_state.status()

    @read_tool
    def aoa_course_connector_source_route() -> dict[str, object]:
        """Return owner/API split and the exact excluded effect surfaces."""
        return service_state.source_route()

    @read_tool
    def aoa_course_connector_list_sources(
        source_ids: list[str] | None = None,
        include_disabled: bool = False,
    ) -> dict[str, object]:
        """List configured sources without exposing source refs."""
        return service_state.list_sources(source_ids, include_disabled)

    @read_tool
    def aoa_course_connector_source_answer(
        query: str,
        source_id: str | None = None,
        limit: int = 5,
    ) -> dict[str, object]:
        """Answer from one selected local query-ready source."""
        return service_state.source_answer(query, source_id, limit)

    @read_tool
    def aoa_course_connector_sources_answer(
        query: str,
        source_ids: list[str] | None = None,
        source_limit: int = 10,
        limit: int = 5,
    ) -> dict[str, object]:
        """Answer across selected local query-ready sources."""
        return service_state.sources_answer(
            query,
            source_ids,
            source_limit,
            limit,
        )

    @read_tool
    def aoa_course_connector_lesson_context(
        query: str,
        run: str = "starter-fixture",
        limit: int = 5,
    ) -> dict[str, object]:
        """Return local lesson and graph context."""
        return service_state.lesson_context(query, run, limit)

    @read_tool
    def aoa_course_connector_graph_neighbors(
        node_id: str,
        run: str = "starter-fixture",
        limit: int = 20,
    ) -> dict[str, object]:
        """Read a bounded local course graph neighborhood."""
        return service_state.graph_neighbors(node_id, run, limit)

    @read_tool
    def aoa_course_connector_freshness_report(
        run: str = "starter-fixture",
    ) -> dict[str, object]:
        """Read owner freshness state for one local run."""
        return service_state.freshness_report(run)

    @read_tool
    def aoa_course_connector_evidence_report(
        query: str,
        run: str = "starter-fixture",
        limit: int = 5,
    ) -> dict[str, object]:
        """Read owner evidence, authority, and freshness reports."""
        return service_state.evidence_report(query, run, limit)

    @mcp.resource("aoa-course://source-route")
    def source_route_resource() -> str:
        return json.dumps(service_state.source_route(), ensure_ascii=False, indent=2)

    @mcp.prompt(name="course-source-answer")
    def source_answer_prompt(query: str) -> str:
        return (
            f"Use aoa_course_connector_source_answer(query={query!r}). "
            "Keep each source evidence chain separate and do not request connected_run."
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
    LOGGER.info("AoA course connector MCP read contour ready")
    _run_server(build_server())
