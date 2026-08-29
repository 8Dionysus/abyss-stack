from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ._http_auth import http_auth_kwargs as _http_auth_kwargs
from ._http_auth import transport_settings as _transport_settings
from .core import AoA4PDAConnectorMCPState


LOGGER = logging.getLogger(__name__)
PACKAGE_NAME = "aoa-4pda-connector-mcp"
APPLICATION_VERSION = "0.2.0"
DEFAULT_HTTP_PORT = 5426
READ_TOKEN_ENV = "AOA_4PDA_CONNECTOR_MCP_READ_BEARER_TOKEN"
READ_CREDENTIAL = "aoa-4pda-connector-mcp-read-bearer-token"
READ_SCOPE = "mcp:aoa-4pda-connector:read"
READ_CLIENT_ID = "aoa-loopback-codex:aoa-4pda-connector:read"


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
    server.configure_http(settings.host, settings.port)
    server.run(transport="streamable-http")


def build_server(
    connector_repo: str | Path | None = None,
    connector_bin: str | None = None,
    data_root: str | Path | None = None,
    cache_root: str | Path | None = None,
    artifact_root: str | Path | None = None,
    default_run: str | None = None,
) -> Any:
    try:
        from ._modern_runtime import AbyssMCPServer  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = AbyssMCPServer(
        "aoa-4pda-connector-mcp",
        json_response=True,
        **_read_http_auth_kwargs(),
    )
    _bind_server_info_version(mcp)
    read_only_tool = mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )

    def current_state() -> AoA4PDAConnectorMCPState:
        return AoA4PDAConnectorMCPState.discover(
            connector_repo=connector_repo,
            connector_bin=connector_bin,
            data_root=data_root,
            cache_root=cache_root,
            artifact_root=artifact_root,
            default_run=default_run,
        )

    @read_only_tool
    def aoa_4pda_connector_status(run: str = "latest") -> dict[str, Any]:
        """Return connector CLI, storage, readiness, and source-route status."""
        return current_state().status(run=run)

    @read_only_tool
    def aoa_4pda_connector_source_route() -> dict[str, Any]:
        """Return owner boundaries, env vars, wrapped commands, and stop lines."""
        return current_state().source_route()

    @read_only_tool
    def aoa_4pda_connector_answer(query: str, run: str = "latest", limit: int = 5) -> dict[str, Any]:
        """Return a compact local answer packet preserving source evidence fields."""
        return current_state().answer(query=query, run=run, limit=limit)

    @read_only_tool
    def aoa_4pda_connector_query_graph(query: str, run: str = "latest", limit: int = 5) -> dict[str, Any]:
        """Return a local graph-aware query packet from the connector CLI."""
        return current_state().query_graph(query=query, run=run, limit=limit)

    @read_only_tool
    def aoa_4pda_connector_query_hybrid(query: str, run: str = "latest", limit: int = 5) -> dict[str, Any]:
        """Return a local hybrid query packet from the connector CLI."""
        return current_state().query_hybrid(query=query, run=run, limit=limit)

    @mcp.resource("aoa-4pda://source-route")
    def source_route_resource() -> str:
        return json.dumps(current_state().source_route(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-4pda://status")
    def status_resource() -> str:
        return json.dumps(current_state().status(), ensure_ascii=False, indent=2)

    @mcp.prompt(name="4pda-answer")
    def answer_prompt(query: str, run: str = "latest") -> str:
        """Prompt route for answering with local 4PDA connector evidence."""
        return (
            f"Use aoa_4pda_connector_answer(query={query!r}, run={run!r}) first. "
            "Treat agent_answer as the cited brief and inspect evidence_chain, nuance_report, "
            "answer_report, conflict_report, freshness_report, applicability_report, "
            "warning_report, source URLs, post ids, and claim ids before making stronger claims."
        )

    LOGGER.info("AoA 4PDA connector MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _run_server(build_server())
