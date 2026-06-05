from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .core import AoADecisionsMCPState

LOGGER = logging.getLogger(__name__)


def build_server(
    workspace_root: str | Path | None = None,
    stack_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = FastMCP("aoa-decisions-mcp", json_response=True)

    def current_state() -> AoADecisionsMCPState:
        return AoADecisionsMCPState.discover(
            workspace_root=workspace_root,
            stack_root=stack_root,
            output_dir=output_dir,
        )

    @mcp.tool()
    def aoa_decisions_status(force_refresh: bool = False) -> dict[str, Any]:
        """Return workspace decision graph freshness, auto-refreshing when stale."""
        return current_state().ensure_fresh(force=force_refresh)

    @mcp.tool()
    def aoa_decisions_summary() -> dict[str, Any]:
        """Return the fresh workspace decision graph summary."""
        return current_state().summary()

    @mcp.tool()
    def aoa_decisions_search(query: str, repo: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Search fresh decision graph decision nodes."""
        return current_state().search(query=query, repo=repo, limit=limit)

    @mcp.tool()
    def aoa_decisions_packet(
        query: str = "",
        repo: str | None = None,
        decision_id: str | None = None,
        path: str | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        """Return a compact fresh graph packet for a decision task."""
        return current_state().packet(
            query=query,
            repo=repo,
            decision_id=decision_id,
            path=path,
            limit=limit,
        )

    @mcp.tool()
    def aoa_decisions_repo(repo: str) -> dict[str, Any]:
        """Return a fresh repo-local decision graph slice."""
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
            "Then inspect the repo-local docs/decisions files named in the packet before making source-truth claims."
        )

    @mcp.prompt(name="decision-create")
    def decision_create(repo: str, intent: str) -> str:
        """Prompt route for creating a decision with prior graph context."""
        return (
            f"Use aoa_decisions_repo(repo={repo!r}) and aoa_decisions_packet(query={intent!r}, repo={repo!r}) "
            "before choosing the next local decision id, template, source surfaces, and supersession links."
        )

    LOGGER.info("AoA decisions MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    build_server().run(transport="stdio")
