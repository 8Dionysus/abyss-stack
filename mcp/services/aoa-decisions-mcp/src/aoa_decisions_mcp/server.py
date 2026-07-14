from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ._http_auth import http_auth_kwargs as _http_auth_kwargs
from ._http_auth import transport_settings as _transport_settings
from .core import AoADecisionsMCPState

LOGGER = logging.getLogger(__name__)
DEFAULT_HTTP_PORT = 5420


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
    stack_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = FastMCP("aoa-decisions-mcp", json_response=True, **_http_auth_kwargs(DEFAULT_HTTP_PORT))

    def current_state() -> AoADecisionsMCPState:
        return AoADecisionsMCPState.discover(
            workspace_root=workspace_root,
            stack_root=stack_root,
            output_dir=output_dir,
        )

    @mcp.tool()
    def aoa_decisions_status(force_refresh: bool = False) -> dict[str, Any]:
        """Return local cache freshness plus non-fetching repo source posture."""
        return current_state().ensure_fresh(force=force_refresh)

    @mcp.tool()
    def aoa_decisions_summary() -> dict[str, Any]:
        """Return the fresh workspace decision graph summary."""
        return current_state().summary()

    @mcp.tool()
    def aoa_decisions_search(query: str, repo: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Search the local-cache-current decision graph and carry source warnings."""
        return current_state().search(query=query, repo=repo, limit=limit)

    @mcp.tool()
    def aoa_decisions_packet(
        query: str = "",
        repo: str | None = None,
        decision_id: str | None = None,
        path: str | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        """Return a compact local graph packet with explicit source-posture limits."""
        return current_state().packet(
            query=query,
            repo=repo,
            decision_id=decision_id,
            path=path,
            limit=limit,
        )

    @mcp.tool()
    def aoa_decisions_repo(repo: str) -> dict[str, Any]:
        """Return a repo graph slice plus the checkout's full local source posture."""
        return current_state().repo(repo)

    @mcp.tool()
    def aoa_decisions_decision(decision_id: str, repo: str | None = None) -> dict[str, Any]:
        """Return a fresh decision neighborhood."""
        return current_state().decision(decision_id=decision_id, repo=repo)

    @mcp.tool()
    def aoa_decisions_source_surface(source_surface: str, repo: str | None = None, limit: int = 50) -> dict[str, Any]:
        """Return fresh decisions that cite a source surface."""
        return current_state().source_surface(source_surface=source_surface, repo=repo, limit=limit)

    @mcp.tool()
    def aoa_decisions_owner_surface(owner_surface: str, repo: str | None = None, limit: int = 50) -> dict[str, Any]:
        """Return fresh decisions that own or guard an owner surface."""
        return current_state().owner_surface(owner_surface=owner_surface, repo=repo, limit=limit)

    @mcp.tool()
    def aoa_decisions_changed_path(path: str, repo: str | None = None, limit: int = 50) -> dict[str, Any]:
        """Return fresh decisions likely impacted by a changed source path."""
        return current_state().changed_path(path=path, repo=repo, limit=limit)

    @mcp.tool()
    def aoa_decisions_repo_symmetry(repo: str | None = None) -> dict[str, Any]:
        """Return fresh repo decision-lane coverage posture without forcing symmetry."""
        return current_state().repo_symmetry(repo=repo)

    @mcp.tool()
    def aoa_decisions_issues(repo: str | None = None, limit: int = 100) -> dict[str, Any]:
        """Return fresh workspace decision graph issues and unknown-surface findings."""
        return current_state().issues(repo=repo, limit=limit)

    @mcp.tool()
    def aoa_decisions_refresh(force: bool = False) -> dict[str, Any]:
        """Refresh the ignored local workspace decision graph cache."""
        return current_state().ensure_fresh(force=force)

    @mcp.resource("aoa-decisions://status")
    def status_resource() -> str:
        return json.dumps(current_state().ensure_fresh(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-decisions://summary")
    def summary_resource() -> str:
        return json.dumps(current_state().summary(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-decisions://repo/{repo}")
    def repo_resource(repo: str) -> str:
        return json.dumps(current_state().repo(repo), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-decisions://decision/{decision_id}")
    def decision_resource(decision_id: str) -> str:
        return json.dumps(current_state().decision(decision_id), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-decisions://issues")
    def issues_resource() -> str:
        return json.dumps(current_state().issues(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-decisions://issues/{repo}")
    def repo_issues_resource(repo: str) -> str:
        return json.dumps(current_state().issues(repo=repo), ensure_ascii=False, indent=2)

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
            f"Use aoa_decisions_repo(repo={repo!r}) and aoa_decisions_packet(query={intent!r}, repo={repo!r}) "
            "before choosing the next local decision id, template, source surfaces, and supersession links. "
            "If repo source_posture is not clean and aligned, derive the id and current rationale from the "
            "authoritative repo-local source rather than the workspace graph."
        )

    LOGGER.info("AoA decisions MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _run_server(build_server())
