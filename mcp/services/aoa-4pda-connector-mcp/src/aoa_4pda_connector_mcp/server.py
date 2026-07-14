from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .core import AoA4PDAConnectorMCPState


LOGGER = logging.getLogger(__name__)
DEFAULT_HTTP_PORT = 5426


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


def build_server(
    connector_repo: str | Path | None = None,
    connector_bin: str | None = None,
    data_root: str | Path | None = None,
    cache_root: str | Path | None = None,
    artifact_root: str | Path | None = None,
    default_run: str | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = FastMCP("aoa-4pda-connector-mcp", json_response=True)

    def current_state() -> AoA4PDAConnectorMCPState:
        return AoA4PDAConnectorMCPState.discover(
            connector_repo=connector_repo,
            connector_bin=connector_bin,
            data_root=data_root,
            cache_root=cache_root,
            artifact_root=artifact_root,
            default_run=default_run,
        )

    @mcp.tool()
    def aoa_4pda_connector_status(run: str = "latest") -> dict[str, Any]:
        """Return connector CLI, storage, readiness, and source-route status."""
        return current_state().status(run=run)

    @mcp.tool()
    def aoa_4pda_connector_source_route() -> dict[str, Any]:
        """Return owner boundaries, env vars, wrapped commands, and stop lines."""
        return current_state().source_route()

    @mcp.tool()
    def aoa_4pda_connector_answer(query: str, run: str = "latest", limit: int = 5) -> dict[str, Any]:
        """Return a compact local answer packet preserving source evidence fields."""
        return current_state().answer(query=query, run=run, limit=limit)

    @mcp.tool()
    def aoa_4pda_connector_query_graph(query: str, run: str = "latest", limit: int = 5) -> dict[str, Any]:
        """Return a local graph-aware query packet from the connector CLI."""
        return current_state().query_graph(query=query, run=run, limit=limit)

    @mcp.tool()
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
