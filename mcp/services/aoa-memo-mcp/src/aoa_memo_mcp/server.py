from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .core import AoAMemoMCPState

LOGGER = logging.getLogger(__name__)


def build_server(workspace_root: str | Path | None = None) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = FastMCP("aoa-memo-mcp", json_response=True)

    def current_state() -> AoAMemoMCPState:
        return AoAMemoMCPState.discover(workspace_root)

    @mcp.tool()
    def aoa_memo_brief(repo: str, intent: str = "") -> dict[str, Any]:
        """Return a compact memory route brief for a repository or host layer."""
        return current_state().build_brief(repo=repo, intent=intent)

    @mcp.tool()
    def aoa_memo_search(query: str, scope: str = "all", mode: str = "brief") -> dict[str, Any]:
        """Search central memory contracts, local memo ports, and session indexes."""
        return current_state().search(query=query, scope=scope, mode=mode)

    @mcp.tool()
    def aoa_memo_create_candidate(
        repo: str,
        evidence_refs: list[str],
        claim: str,
        source_trust: str = "review_required",
    ) -> dict[str, Any]:
        """Create a local memory candidate under the repo memo port."""
        return current_state().create_candidate(
            repo=repo,
            evidence_refs=evidence_refs,
            claim=claim,
            source_trust=source_trust,
        )

    @mcp.tool()
    def aoa_memo_validate_candidate(path: str) -> dict[str, Any]:
        """Validate a local memory candidate before reviewed intake."""
        return current_state().validate_candidate(path)

    @mcp.resource("aoa-memo://brief/repo/{repo}")
    def brief_resource(repo: str) -> str:
        return json.dumps(current_state().build_brief(repo), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-memo://memory/object/{object_id}")
    def memory_object_resource(object_id: str) -> str:
        return json.dumps(current_state().build_memory_object(object_id), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-memo://session/{session_id}/rehydrate")
    def session_rehydrate_resource(session_id: str) -> str:
        return json.dumps(current_state().build_session_rehydrate(session_id), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-memo://repo/{repo}/local-port-status")
    def local_port_status_resource(repo: str) -> str:
        return json.dumps(current_state().build_local_port_status(repo), ensure_ascii=False, indent=2)

    @mcp.prompt(name="memo-brief")
    def memo_brief(repo: str, intent: str = "") -> str:
        """Prompt route for obtaining a memory brief."""
        return (
            f"Use aoa_memo_brief(repo={repo!r}, intent={intent!r}). "
            "Read the local port status, operation mode, owner note, and validation commands before acting."
        )

    @mcp.prompt(name="memo-intake")
    def memo_intake(repo: str, claim: str) -> str:
        """Prompt route for creating a memory candidate."""
        return (
            f"Create a local candidate for {repo!r} with claim {claim!r}. "
            "Use evidence refs from current files or session archive pointers. "
            "Run aoa_memo_validate_candidate before proposing reviewed intake."
        )

    @mcp.prompt(name="memo-review")
    def memo_review(candidate_path: str) -> str:
        """Prompt route for reviewing a memory candidate."""
        return (
            f"Validate {candidate_path!r}; compare evidence refs against current owner files; "
            "then route to aoa-memo reviewed intake, keep local, or reject."
        )

    @mcp.prompt(name="session-rehydrate")
    def session_rehydrate(session_id: str) -> str:
        """Prompt route for session evidence rehydration."""
        return (
            f"Use aoa-memo://session/{session_id}/rehydrate to get archive pointers. "
            "Inspect AGENTS.md, SESSION.md, manifest, and index before opening raw evidence."
        )

    LOGGER.info("AoA memo MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    build_server().run(transport="stdio")
