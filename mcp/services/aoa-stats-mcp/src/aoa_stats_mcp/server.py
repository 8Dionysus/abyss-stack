from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

from ._http_auth import http_auth_config
from ._runtime_config import SERVICE_CONFIG
from .core import AoAStatsMCPState


LOGGER = logging.getLogger(__name__)
def _run_server(server: Any) -> None:
    from ._modern_runtime import run_server

    run_server(server, _read_http_auth_config())


def _read_http_auth_config() -> Any:
    contour = SERVICE_CONFIG.contour("read")
    return http_auth_config(contour.port, **contour.auth.as_kwargs())


def build_server(
    workspace_root: str | Path | None = None,
    aoa_stats_root: str | Path | None = None,
    source_roots: Mapping[str, str | Path] | None = None,
) -> Any:
    try:
        from ._modern_runtime import ModernMCPServer  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'mcp'. Install with: python -m pip install -e ."
        ) from exc

    mcp = ModernMCPServer(
        SERVICE_CONFIG.server_name("read"),
        version=SERVICE_CONFIG.package_version,
        **_read_http_auth_config().server_kwargs,
    )
    read_only_tool = mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
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
