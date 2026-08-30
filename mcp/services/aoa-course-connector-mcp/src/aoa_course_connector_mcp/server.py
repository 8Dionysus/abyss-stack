"""Authenticated MCP 2.x read contour for aoa-course-connector."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import ToolAnnotations

from ._http_auth import http_auth_config
from ._modern_runtime import ModernMCPServer, run_server
from ._runtime_config import SERVICE_CONFIG
from .core import AoACourseConnectorMCPState

LOGGER = logging.getLogger(__name__)


def _read_http_auth_config() -> Any:
    contour = SERVICE_CONFIG.contour("read")
    return http_auth_config(contour.port, **contour.auth.as_kwargs())


def build_server(
    state: AoACourseConnectorMCPState | None = None,
) -> ModernMCPServer:
    service_state = state or AoACourseConnectorMCPState.discover()
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
    run_server(server, _read_http_auth_config())


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    LOGGER.info("AoA course connector MCP read contour ready")
    _run_server(build_server())
