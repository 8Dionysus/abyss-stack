from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .core import AoAMemoMCPState

LOGGER = logging.getLogger(__name__)
DEFAULT_HTTP_PORT = 5421


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
        kind: str = "route",
        family: str = "memory-access",
        scope: str = "repo",
        source_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a local memory candidate under the repo memo port."""
        return current_state().create_candidate(
            repo=repo,
            evidence_refs=evidence_refs,
            claim=claim,
            source_trust=source_trust,
            kind=kind,
            family=family,
            scope=scope,
            source_refs=source_refs,
        )

    @mcp.tool()
    def aoa_memo_validate_candidate(path: str) -> dict[str, Any]:
        """Validate a local memory candidate before reviewed intake."""
        return current_state().validate_candidate(path)

    @mcp.tool()
    def aoa_memo_build_port_index(repo: str, write: bool = False, check: bool = False) -> dict[str, Any]:
        """Build or check the generated local memo port index."""
        return current_state().build_port_index(repo=repo, write=write, check=check)

    @mcp.tool()
    def aoa_memo_validate_port(repo: str) -> dict[str, Any]:
        """Validate a local memo port contract, packets, and generated index."""
        return current_state().validate_port(repo)

    @mcp.tool()
    def aoa_memo_prepare_intake_packet(
        repo: str,
        candidate_refs: list[str],
        receipt_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Prepare a reviewed-intake export packet from local candidates."""
        return current_state().prepare_intake_packet(repo=repo, candidate_refs=candidate_refs, receipt_refs=receipt_refs)

    @mcp.tool()
    def aoa_memo_review_intake(path: str) -> dict[str, Any]:
        """Check a local reviewed-intake export and write a forwarding receipt."""
        return current_state().review_intake(path)

    @mcp.tool()
    def aoa_memo_pending_exports(repo: str) -> dict[str, Any]:
        """List local reviewed-intake exports and their landing readiness."""
        return current_state().list_pending_exports(repo)

    @mcp.tool()
    def aoa_memo_landing_plan(
        repo: str,
        export_ref: str,
        object_kind: str = "decision",
        slug: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        reviewed_at: str | None = None,
        run_dry_run: bool = False,
    ) -> dict[str, Any]:
        """Prepare or dry-run an aoa-memo landing plan without durable write."""
        return current_state().build_landing_plan(
            repo=repo,
            export_ref=export_ref,
            object_kind=object_kind,
            slug=slug,
            title=title,
            summary=summary,
            reviewed_at=reviewed_at,
            run_dry_run=run_dry_run,
        )

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

    @mcp.resource("aoa-memo://repo/{repo}/memo-port-index")
    def memo_port_index_resource(repo: str) -> str:
        return json.dumps(current_state().build_port_index(repo), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-memo://repo/{repo}/memo-open-items")
    def memo_open_items_resource(repo: str) -> str:
        return json.dumps(current_state().read_resource(f"aoa-memo://repo/{repo}/memo-open-items"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-memo://repo/{repo}/pending-exports")
    def pending_exports_resource(repo: str) -> str:
        return json.dumps(current_state().list_pending_exports(repo), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-memo://repo/{repo}/memo-vocabulary")
    def memo_vocabulary_resource(repo: str) -> str:
        return json.dumps(current_state().build_memo_port_vocabulary(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-memo://intake/{packet_id}/review")
    def intake_review_resource(packet_id: str) -> str:
        return json.dumps(current_state().find_intake_review(packet_id), ensure_ascii=False, indent=2)

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
            "Run aoa_memo_validate_candidate, aoa_memo_prepare_intake_packet, and aoa_memo_review_intake as a forwarding check before proposing durable aoa-memo landing."
        )

    @mcp.prompt(name="memo-review")
    def memo_review(candidate_path: str) -> str:
        """Prompt route for checking a memory candidate before forwarding."""
        return (
            f"Validate {candidate_path!r}; compare evidence refs against current owner files; "
            "then prepare/check an intake packet, keep local, or reject. MCP forwarding checks are not durable memory review."
        )

    @mcp.prompt(name="memo-landing-plan")
    def memo_landing_plan(repo: str, export_ref: str) -> str:
        """Prompt route for planning reviewed aoa-memo landing."""
        return (
            f"Use aoa_memo_pending_exports(repo={repo!r}), then "
            f"aoa_memo_landing_plan(repo={repo!r}, export_ref={export_ref!r}, run_dry_run=True). "
            "Inspect readiness and dry-run output; durable landing still requires an aoa-memo source patch and validators."
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
    _run_server(build_server())
