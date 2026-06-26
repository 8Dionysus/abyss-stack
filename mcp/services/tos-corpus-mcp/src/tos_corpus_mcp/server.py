from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .core import ToSCorpusMCPState


LOGGER = logging.getLogger(__name__)


def build_server(
    tos_root: str | Path | None = None,
    index_path: str | Path | None = None,
    philosophy_graph_projection_path: str | Path | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = FastMCP("tos-corpus-mcp", json_response=True)

    def current_state() -> ToSCorpusMCPState:
        return ToSCorpusMCPState.discover(
            tos_root=tos_root,
            index_path=index_path,
            philosophy_graph_projection_path=philosophy_graph_projection_path,
        )

    @mcp.tool()
    def tos_corpus_status() -> dict[str, Any]:
        """Return ToS corpus index path, counts, graph views, and authority boundary."""
        return current_state().status()

    @mcp.tool()
    def tos_corpus_summary() -> dict[str, Any]:
        """Return a compact whole-corpus summary from the ToS-owned index."""
        return current_state().summary()

    @mcp.tool()
    def tos_corpus_search(query: str, limit: int = 20, resource_kind: str | None = None) -> dict[str, Any]:
        """Search nodes, resources, manifests, branches, and graph views in the ToS corpus index."""
        return current_state().search(query=query, limit=limit, resource_kind=resource_kind)

    @mcp.tool()
    def tos_corpus_resources(
        resource_kind: str | None = None,
        owner_branch: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List indexed ToS resources with optional kind and owner-branch filters."""
        return current_state().resources(resource_kind=resource_kind, owner_branch=owner_branch, limit=limit)

    @mcp.tool()
    def tos_corpus_node(node_id: str) -> dict[str, Any]:
        """Return one indexed ToS node and relation edges connected to it."""
        return current_state().node(node_id=node_id)

    @mcp.tool()
    def tos_corpus_relation_pack(pack_id: str) -> dict[str, Any]:
        """Return one indexed ToS relation pack and its edges."""
        return current_state().relation_pack(pack_id=pack_id)

    @mcp.tool()
    def tos_corpus_graph_view(view_id: str, limit: int = 100) -> dict[str, Any]:
        """Return a named graph review view over the whole ToS corpus index."""
        return current_state().graph_view(view_id=view_id, limit=limit)

    @mcp.tool()
    def tos_corpus_packet(query: str = "", view_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Return a compact task packet with optional search and graph-view context."""
        return current_state().packet(query=query, view_id=view_id, limit=limit)

    @mcp.tool()
    def tos_philosophy_graph_status() -> dict[str, Any]:
        """Return ToS philosophy graph projection path, counts, graph views, and authority boundary."""
        return current_state().philosophy_status()

    @mcp.tool()
    def tos_philosophy_graph_views() -> dict[str, Any]:
        """List ToS philosophy graph views materialized by the ToS-owned projection export."""
        return current_state().philosophy_views()

    @mcp.tool()
    def tos_philosophy_graph_layers() -> dict[str, Any]:
        """Return ToS-owned philosophy graph layers and layer counts for runtime filtering."""
        return current_state().philosophy_layers()

    @mcp.tool()
    def tos_philosophy_graph_view(view_id: str) -> dict[str, Any]:
        """Return one ToS philosophy graph view packet with projected nodes, edges, and source refs."""
        return current_state().philosophy_view(view_id=view_id)

    @mcp.tool()
    def tos_philosophy_graph_clusters(
        view_id: str | None = None,
        cluster_kind: str | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        """Return compact ToS philosophy graph clusters, optionally filtered by view and cluster kind."""
        return current_state().philosophy_clusters(view_id=view_id, cluster_kind=cluster_kind, limit=limit)

    @mcp.tool()
    def tos_philosophy_graph_node(node_id: str) -> dict[str, Any]:
        """Return one projected ToS philosophy node and related projected edges."""
        return current_state().philosophy_node(node_id=node_id)

    @mcp.tool()
    def tos_philosophy_graph_neighborhood(
        node_id: str,
        depth: int = 1,
        layers: list[str] | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        """Return the projected neighborhood around one ToS philosophy node."""
        return current_state().philosophy_neighborhood(node_id=node_id, depth=depth, layers=layers, limit=limit)

    @mcp.tool()
    def tos_philosophy_graph_review_packet(view_id: str = "chronology") -> dict[str, Any]:
        """Return one compact ToS-owned review packet for a philosophy graph lens."""
        return current_state().philosophy_review_packet(view_id=view_id)

    @mcp.tool()
    def tos_philosophy_graph_unresolved(view_id: str | None = None) -> dict[str, Any]:
        """Return unresolved review surfaces for all philosophy graph lenses or one selected lens."""
        return current_state().philosophy_unresolved(view_id=view_id)

    @mcp.tool()
    def tos_philosophy_graph_packet(query: str = "", view_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Return a compact philosophy graph packet for agents with optional search and view context."""
        return current_state().philosophy_packet(query=query, view_id=view_id, limit=limit)

    @mcp.tool()
    def tos_philosophy_graph_chronology_packet(limit: int = 20) -> dict[str, Any]:
        """Return the chronology lens packet for formation, fixation, canonization, and dating review."""
        return current_state().philosophy_lens_packet(view_id="chronology", limit=limit)

    @mcp.tool()
    def tos_philosophy_graph_source_evidence_packet(limit: int = 20) -> dict[str, Any]:
        """Return the source-evidence lens packet for source refs, confidence, and witness review."""
        return current_state().philosophy_lens_packet(view_id="source-evidence", limit=limit)

    @mcp.tool()
    def tos_philosophy_graph_concept_lineage_packet(limit: int = 20) -> dict[str, Any]:
        """Return the concept-lineage lens packet for concept/problem pressure and lineage review."""
        return current_state().philosophy_lens_packet(view_id="concept-lineage", limit=limit)

    @mcp.resource("tos-corpus://status")
    def status_resource() -> str:
        return json.dumps(current_state().status(), ensure_ascii=False, indent=2)

    @mcp.resource("tos-corpus://summary")
    def summary_resource() -> str:
        return json.dumps(current_state().summary(), ensure_ascii=False, indent=2)

    @mcp.resource("tos-corpus://graph-views")
    def graph_views_resource() -> str:
        return current_state().render_resource("tos-corpus://graph-views")

    @mcp.resource("tos-corpus://graph-view/{view_id}")
    def graph_view_resource(view_id: str) -> str:
        return current_state().render_resource(f"tos-corpus://graph-view/{view_id}")

    @mcp.resource("tos-philosophy://status")
    def philosophy_status_resource() -> str:
        return current_state().render_resource("tos-philosophy://status")

    @mcp.resource("tos-philosophy://views")
    def philosophy_views_resource() -> str:
        return current_state().render_resource("tos-philosophy://views")

    @mcp.resource("tos-philosophy://layers")
    def philosophy_layers_resource() -> str:
        return current_state().render_resource("tos-philosophy://layers")

    @mcp.resource("tos-philosophy://clusters")
    def philosophy_clusters_resource() -> str:
        return current_state().render_resource("tos-philosophy://clusters")

    @mcp.resource("tos-philosophy://unresolved")
    def philosophy_unresolved_resource() -> str:
        return current_state().render_resource("tos-philosophy://unresolved")

    @mcp.resource("tos-philosophy://view/{view_id}")
    def philosophy_view_resource(view_id: str) -> str:
        return current_state().render_resource(f"tos-philosophy://view/{view_id}")

    @mcp.resource("tos-philosophy://review-packet/{view_id}")
    def philosophy_review_packet_resource(view_id: str) -> str:
        return current_state().render_resource(f"tos-philosophy://review-packet/{view_id}")

    @mcp.resource("tos-philosophy://lens/{view_id}")
    def philosophy_lens_resource(view_id: str) -> str:
        return current_state().render_resource(f"tos-philosophy://lens/{view_id}")

    @mcp.prompt(name="tos-corpus-review")
    def tos_corpus_review(view_id: str = "corpus-topology", query: str = "") -> str:
        """Prompt route for reviewing ToS corpus graph context."""
        return (
            f"Use tos_corpus_status(), then tos_corpus_packet(query={query!r}, view_id={view_id!r}). "
            "Treat Tree-of-Sophia paths returned by the packet as source authority; treat MCP and runtime projection as access surfaces only."
        )

    @mcp.prompt(name="tos-philosophy-graph-review")
    def tos_philosophy_graph_review(view_id: str = "chronology", query: str = "") -> str:
        """Prompt route for reviewing ToS philosophy graph projection context."""
        return (
            f"Use tos_philosophy_graph_status(), tos_philosophy_graph_layers(), "
            f"tos_philosophy_graph_review_packet(view_id={view_id!r}), then "
            f"tos_philosophy_graph_packet(query={query!r}, view_id={view_id!r}). "
            "Treat ToS source_ref values as meaning authority; treat MCP, UI, and Neo4j as projection/access surfaces only."
        )

    LOGGER.info("ToS corpus MCP server ready")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    build_server().run(transport="stdio")
