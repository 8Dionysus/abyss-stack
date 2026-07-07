from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .core import AoAKagMCPState


LOGGER = logging.getLogger(__name__)


def build_server(
    workspace_root: str | Path | None = None,
    aoa_kag_root: str | Path | None = None,
    provider_map_path: str | Path | None = None,
    readiness_path: str | Path | None = None,
    coverage_path: str | Path | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = FastMCP("aoa-kag-mcp", json_response=True)

    def current_state() -> AoAKagMCPState:
        return AoAKagMCPState.discover(
            workspace_root=workspace_root,
            aoa_kag_root=aoa_kag_root,
            provider_map_path=provider_map_path,
            readiness_path=readiness_path,
            coverage_path=coverage_path,
        )

    @mcp.tool()
    def aoa_kag_provider_status(repo: str | None = None) -> dict[str, Any]:
        """Return provider-map status for one repo or the whole registry."""
        return current_state().provider_status(repo=repo)

    @mcp.tool()
    def aoa_kag_provider_lookup(repo: str) -> dict[str, Any]:
        """Return one provider or explicit remaining route from the provider map."""
        return current_state().provider_lookup(repo=repo)

    @mcp.tool()
    def aoa_kag_freshness_check(repo: str | None = None) -> dict[str, Any]:
        """Return freshness handles from provider receipts without running validators."""
        return current_state().freshness_check(repo=repo)

    @mcp.tool()
    def aoa_kag_source_return_lookup(
        repo: str,
        local_id: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Return source-return routes for one provider or matching record."""
        return current_state().source_return_lookup(repo=repo, local_id=local_id, path=path)

    @mcp.tool()
    def aoa_kag_generation_route_lookup(repo: str) -> dict[str, Any]:
        """Return source-owned generation route metadata for one provider."""
        return current_state().generation_route_lookup(repo=repo)

    @mcp.tool()
    def aoa_kag_source_index_lookup(repo: str) -> dict[str, Any]:
        """Return compact repo-local source-index metadata for one provider."""
        return current_state().source_index_lookup(repo=repo)

    @mcp.tool()
    def aoa_kag_repo_local_coverage_status(
        repo: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Return repo-local KAG source-index coverage rows."""
        return current_state().repo_local_coverage_status(repo=repo, status=status)

    @mcp.tool()
    def aoa_kag_registry_slice(
        status: str | None = None,
        repo: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Return a bounded provider-map registry slice."""
        return current_state().registry_slice(status=status, repo=repo, limit=limit)

    @mcp.tool()
    def aoa_kag_composition_slice(query: str = "", limit: int = 20) -> dict[str, Any]:
        """Search provider-map fields for a bounded composition packet."""
        return current_state().composition_slice(query=query, limit=limit)

    @mcp.tool()
    def aoa_kag_validation_status(include_provider_homes: bool = False) -> dict[str, Any]:
        """Return provider-map validation posture and optional provider-home presence checks."""
        return current_state().validation_status(include_provider_homes=include_provider_homes)

    @mcp.resource("aoa-kag://registry/provider-map")
    def provider_map_resource() -> str:
        return json.dumps(current_state().provider_map(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-kag://readiness/os-surfaces")
    def os_surfaces_resource() -> str:
        return json.dumps(current_state().read_resource("aoa-kag://readiness/os-surfaces"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-kag://providers/{repo}/manifest")
    def provider_manifest_resource(repo: str) -> str:
        return json.dumps(current_state().read_resource(f"aoa-kag://providers/{repo}/manifest"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-kag://providers/{repo}/records/{record_class}")
    def provider_records_resource(repo: str, record_class: str) -> str:
        return json.dumps(
            current_state().read_resource(f"aoa-kag://providers/{repo}/records/{record_class}"),
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource("aoa-kag://providers/{repo}/generation")
    def provider_generation_resource(repo: str) -> str:
        return json.dumps(
            current_state().read_resource(f"aoa-kag://providers/{repo}/generation"),
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource("aoa-kag://providers/{repo}/source-index")
    def provider_source_index_resource(repo: str) -> str:
        return json.dumps(
            current_state().read_resource(f"aoa-kag://providers/{repo}/source-index"),
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource("aoa-kag://providers/{repo}/repo-local-index")
    def provider_repo_local_index_resource(repo: str) -> str:
        return json.dumps(
            current_state().read_resource(f"aoa-kag://providers/{repo}/repo-local-index"),
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource("aoa-kag://coverage/repo-local-source-indexes")
    def repo_local_source_indexes_resource() -> str:
        return json.dumps(
            current_state().read_resource("aoa-kag://coverage/repo-local-source-indexes"),
            ensure_ascii=False,
            indent=2,
        )

    @mcp.prompt(name="bounded-provider-query")
    def bounded_provider_query(repo: str, question: str) -> str:
        """Prompt route for querying one provider without crossing source ownership."""
        return (
            f"Use aoa_kag_provider_lookup(repo={repo!r}), then "
            f"aoa_kag_source_return_lookup(repo={repo!r}). Answer {question!r} only from returned provider records and source-return surfaces."
        )

    @mcp.prompt(name="source-return-summary")
    def source_return_summary(repo: str) -> str:
        """Prompt route for summarizing owner-return paths."""
        return (
            f"Use aoa_kag_source_return_lookup(repo={repo!r}) and inspect the owner_return_routes before changing meaning."
        )

    @mcp.prompt(name="repo-source-surface-brief")
    def repo_source_surface_brief(repo: str) -> str:
        """Prompt route for reading one repo's KAG source surfaces."""
        return (
            f"Use aoa_kag_generation_route_lookup(repo={repo!r}), "
            f"aoa_kag_source_index_lookup(repo={repo!r}), and "
            f"aoa_kag_source_return_lookup(repo={repo!r}) before summarizing repo-local source surfaces."
        )

    @mcp.prompt(name="cross-repo-relation-preview")
    def cross_repo_relation_preview(query: str) -> str:
        """Prompt route for previewing provider-map relations without claiming graph truth."""
        return (
            f"Use aoa_kag_composition_slice(query={query!r}) for a bounded preview. "
            "Treat results as provider-map routing context, then return to source owners."
        )

    @mcp.prompt(name="runtime-handoff-brief")
    def runtime_handoff_brief() -> str:
        """Prompt route for reading the MCP handoff packet."""
        return (
            "Use aoa_kag_registry_slice(limit=20), aoa_kag_validation_status(include_provider_homes=True), "
            "and aoa-kag://registry/provider-map before editing MCP service behavior."
        )

    LOGGER.info("AoA KAG MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    build_server().run(transport="stdio")
