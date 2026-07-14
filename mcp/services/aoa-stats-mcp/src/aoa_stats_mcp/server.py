from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

from ._http_auth import http_auth_kwargs as _http_auth_kwargs
from ._http_auth import transport_settings as _transport_settings
from .core import AoAStatsMCPState


LOGGER = logging.getLogger(__name__)
DEFAULT_HTTP_PORT = 5430


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


def build_server(
    workspace_root: str | Path | None = None,
    aoa_stats_root: str | Path | None = None,
    source_roots: Mapping[str, str | Path] | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = FastMCP(
        "aoa-stats-mcp",
        json_response=True,
        **_http_auth_kwargs(DEFAULT_HTTP_PORT),
    )
    read_only_tool = mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )

    def current_state() -> AoAStatsMCPState:
        return AoAStatsMCPState.discover(
            workspace_root=workspace_root,
            aoa_stats_root=aoa_stats_root,
            source_roots=source_roots,
        )

    @read_only_tool
    def stats_catalog() -> dict[str, Any]:
        """Return the active owner-produced catalog of derived stats surfaces."""
        return current_state().catalog()

    @read_only_tool
    def stats_surface_read(
        surface_name: str | None = None,
        surface_ref: str | None = None,
        mode: str = "preview",
        limit: int = 5,
    ) -> dict[str, Any]:
        """Read one catalog-listed derived surface with explicit access posture."""
        return current_state().surface_read(
            surface_name=surface_name,
            surface_ref=surface_ref,
            mode=mode,
            limit=limit,
        )

    @read_only_tool
    def stats_boundary_rules() -> dict[str, Any]:
        """Return compact source-owner refs and authority ceilings for stats reads."""
        return current_state().boundary_rules()

    @read_only_tool
    def stats_owner_port_read(
        repo: str | None = None,
        measurement_id: str | None = None,
    ) -> dict[str, Any]:
        """List known local stats ports or inspect one owner-local definition."""
        return current_state().owner_port_read(
            repo=repo,
            measurement_id=measurement_id,
        )

    @read_only_tool
    def stats_packet_check(
        contract: dict[str, Any],
        packet: dict[str, Any],
    ) -> dict[str, Any]:
        """Check packet compatibility through the public aoa-stats read contract."""
        return current_state().packet_check(contract=contract, packet=packet)

    LOGGER.info("AoA stats MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _run_server(build_server())
