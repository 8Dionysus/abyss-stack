from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from ._http_auth import http_auth_kwargs as _http_auth_kwargs
from ._http_auth import transport_settings as _transport_settings
from .core import AoADecisionsMCPState

LOGGER = logging.getLogger(__name__)
PACKAGE_NAME = "aoa-decisions-mcp"
APPLICATION_VERSION = "0.2.0"
DEFAULT_HTTP_PORT = 5420
SUPPORTED_CONTOURS = frozenset({"read", "internal_effect"})
CONTOUR_AUTH = {
    "read": {
        "token_env_var": "AOA_DECISIONS_MCP_READ_BEARER_TOKEN",
        "credential_name": "aoa-decisions-mcp-read-bearer-token",
        "auth_scope": "mcp:aoa-decisions:read",
        "client_id": "aoa-loopback-codex:aoa-decisions:read",
    },
    "internal_effect": {
        "token_env_var": "AOA_DECISIONS_MCP_INTERNAL_EFFECT_BEARER_TOKEN",
        "credential_name": "aoa-decisions-mcp-internal-effect-bearer-token",
        "auth_scope": "mcp:aoa-decisions:internal-effect",
        "client_id": "aoa-loopback-codex:aoa-decisions:internal-effect",
    },
}


def _application_version() -> str:
    return APPLICATION_VERSION


def _bind_server_info_version(mcp: Any) -> None:
    low_level_server = getattr(mcp, "_mcp_server", None)
    if low_level_server is None or not hasattr(low_level_server, "version"):
        raise RuntimeError(
            "the pinned MCP SDK no longer exposes the server identity seam"
        )
    low_level_server.version = _application_version()


def _contour_http_auth_kwargs(contour: str) -> dict[str, Any]:
    try:
        auth = CONTOUR_AUTH[contour]
    except KeyError as exc:
        raise ValueError(
            f"unsupported decisions MCP contour {contour!r}; "
            f"expected one of {sorted(SUPPORTED_CONTOURS)}"
        ) from exc
    return _http_auth_kwargs(DEFAULT_HTTP_PORT, **auth)


def _run_server(server: Any, *, contour: str = "read") -> None:
    settings = _transport_settings(DEFAULT_HTTP_PORT)
    _contour_http_auth_kwargs(contour)
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
    stack_root: str | Path | None = None,
    output_dir: str | Path | None = None,
    contour: str = "read",
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'mcp'. Install with: python -m pip install -e ."
        ) from exc

    if contour not in SUPPORTED_CONTOURS:
        raise ValueError(
            f"unsupported decisions MCP contour {contour!r}; "
            f"expected one of {sorted(SUPPORTED_CONTOURS)}"
        )

    mcp = FastMCP(
        f"aoa-decisions-mcp-{contour.replace('_', '-')}",
        json_response=True,
        **_contour_http_auth_kwargs(contour),
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

    def current_state() -> AoADecisionsMCPState:
        return AoADecisionsMCPState.discover(
            workspace_root=workspace_root,
            stack_root=stack_root,
            output_dir=output_dir,
            cache_write_allowed=contour == "internal_effect",
        )

    @read_only_tool
    def aoa_decisions_status() -> dict[str, Any]:
        """Inspect local cache readiness without creating or refreshing files."""
        return current_state().cache_posture()

    if contour == "internal_effect":

        @mcp.tool()
        def aoa_decisions_refresh(force: bool = False) -> dict[str, Any]:
            """Refresh the ignored local graph cache in the internal-effect contour."""
            return current_state().ensure_fresh(force=force)

    if contour == "read":

        @read_only_tool
        def aoa_decisions_summary() -> dict[str, Any]:
            """Return the existing locally fresh workspace decision graph summary."""
            return current_state().summary()

        @read_only_tool
        def aoa_decisions_search(
            query: str, repo: str | None = None, limit: int = 20
        ) -> dict[str, Any]:
            """Search the existing locally fresh graph and carry source warnings."""
            return current_state().search(query=query, repo=repo, limit=limit)

        @read_only_tool
        def aoa_decisions_packet(
            query: str = "",
            repo: str | None = None,
            decision_id: str | None = None,
            path: str | None = None,
            limit: int = 12,
        ) -> dict[str, Any]:
            """Return a compact locally fresh graph packet with explicit limits."""
            return current_state().packet(
                query=query,
                repo=repo,
                decision_id=decision_id,
                path=path,
                limit=limit,
            )

        @read_only_tool
        def aoa_decisions_repo(repo: str) -> dict[str, Any]:
            """Return a repo graph slice plus the checkout's local source posture."""
            return current_state().repo(repo)

        @read_only_tool
        def aoa_decisions_decision(
            decision_id: str, repo: str | None = None
        ) -> dict[str, Any]:
            """Return a locally fresh decision neighborhood."""
            return current_state().decision(decision_id=decision_id, repo=repo)

        @read_only_tool
        def aoa_decisions_source_surface(
            source_surface: str,
            repo: str | None = None,
            limit: int = 50,
        ) -> dict[str, Any]:
            """Return locally fresh decisions that cite a source surface."""
            return current_state().source_surface(
                source_surface=source_surface, repo=repo, limit=limit
            )

        @read_only_tool
        def aoa_decisions_owner_surface(
            owner_surface: str,
            repo: str | None = None,
            limit: int = 50,
        ) -> dict[str, Any]:
            """Return locally fresh decisions that own or guard an owner surface."""
            return current_state().owner_surface(
                owner_surface=owner_surface, repo=repo, limit=limit
            )

        @read_only_tool
        def aoa_decisions_changed_path(
            path: str,
            repo: str | None = None,
            limit: int = 50,
        ) -> dict[str, Any]:
            """Return locally fresh decisions likely impacted by a changed path."""
            return current_state().changed_path(path=path, repo=repo, limit=limit)

        @read_only_tool
        def aoa_decisions_repo_symmetry(repo: str | None = None) -> dict[str, Any]:
            """Return locally fresh decision-lane coverage without forced symmetry."""
            return current_state().repo_symmetry(repo=repo)

        @read_only_tool
        def aoa_decisions_issues(
            repo: str | None = None, limit: int = 100
        ) -> dict[str, Any]:
            """Return locally fresh graph issues and unknown-surface findings."""
            return current_state().issues(repo=repo, limit=limit)

        @mcp.resource("aoa-decisions://status")
        def status_resource() -> str:
            return json.dumps(
                current_state().cache_posture(), ensure_ascii=False, indent=2
            )

        @mcp.resource("aoa-decisions://summary")
        def summary_resource() -> str:
            return json.dumps(current_state().summary(), ensure_ascii=False, indent=2)

        @mcp.resource("aoa-decisions://repo/{repo}")
        def repo_resource(repo: str) -> str:
            return json.dumps(current_state().repo(repo), ensure_ascii=False, indent=2)

        @mcp.resource("aoa-decisions://decision/{decision_id}")
        def decision_resource(decision_id: str) -> str:
            return json.dumps(
                current_state().decision(decision_id), ensure_ascii=False, indent=2
            )

        @mcp.resource("aoa-decisions://issues")
        def issues_resource() -> str:
            return json.dumps(current_state().issues(), ensure_ascii=False, indent=2)

        @mcp.resource("aoa-decisions://issues/{repo}")
        def repo_issues_resource(repo: str) -> str:
            return json.dumps(
                current_state().issues(repo=repo), ensure_ascii=False, indent=2
            )

        @mcp.prompt(name="decision-find")
        def decision_find(query: str) -> str:
            """Prompt route for finding prior decision rationale."""
            return (
                f"Use aoa_decisions_packet(query={query!r}) first. "
                "Inspect its source warnings, then inspect the repo-local docs/decisions files named in the packet "
                "before making source-truth claims. A cache-fresh packet is not remote-fresh proof."
            )

        @mcp.prompt(name="decision-create")
        def decision_create(repo: str, intent: str) -> str:
            """Prompt route for creating a decision with prior graph context."""
            return (
                f"Use aoa_decisions_repo(repo={repo!r}) and "
                f"aoa_decisions_packet(query={intent!r}, repo={repo!r}) "
                "before choosing the next local decision id, template, source surfaces, and supersession links. "
                "If repo source_posture is not clean and aligned, derive the id and current rationale from the "
                "authoritative repo-local source rather than the workspace graph."
            )

    LOGGER.info("AoA decisions MCP server ready: contour=%s", contour)
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    contour = os.environ.get("AOA_DECISIONS_MCP_CONTOUR", "read")
    _run_server(build_server(contour=contour), contour=contour)
