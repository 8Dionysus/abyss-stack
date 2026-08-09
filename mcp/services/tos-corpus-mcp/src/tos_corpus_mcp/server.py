from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ._http_auth import http_auth_kwargs as _http_auth_kwargs
from ._http_auth import transport_settings as _transport_settings
from .core import ToSCorpusMCPState


LOGGER = logging.getLogger(__name__)
PACKAGE_NAME = "tos-corpus-mcp"
APPLICATION_VERSION = "0.2.0"
DEFAULT_HTTP_PORT = 5429
READ_TOKEN_ENV_VAR = "TOS_CORPUS_MCP_READ_BEARER_TOKEN"
READ_CREDENTIAL_NAME = "tos-corpus-mcp-read-bearer-token"
READ_AUTH_SCOPE = "mcp:tos-corpus:read"
READ_CLIENT_ID = "aoa-loopback-codex:tos-corpus:read"


def _application_version() -> str:
    return APPLICATION_VERSION


def _bind_server_info_version(mcp: Any) -> None:
    low_level_server = getattr(mcp, "_mcp_server", None)
    if low_level_server is None or not hasattr(low_level_server, "version"):
        raise RuntimeError(
            "the pinned MCP SDK no longer exposes the server identity seam"
        )
    low_level_server.version = _application_version()


def _read_http_auth_kwargs() -> dict[str, Any]:
    return _http_auth_kwargs(
        DEFAULT_HTTP_PORT,
        token_env_var=READ_TOKEN_ENV_VAR,
        credential_name=READ_CREDENTIAL_NAME,
        auth_scope=READ_AUTH_SCOPE,
        client_id=READ_CLIENT_ID,
    )


def _run_server(server: Any) -> None:
    settings = _transport_settings(DEFAULT_HTTP_PORT)
    _read_http_auth_kwargs()
    if settings.transport == "stdio":
        server.run(transport="stdio")
        return
    assert settings.host is not None
    assert settings.port is not None
    server.configure_http(settings.host, settings.port)
    server.run(transport="streamable-http")


def build_server(
    tos_root: str | Path | None = None,
    index_path: str | Path | None = None,
    philosophy_graph_projection_path: str | Path | None = None,
    philosophy_post_planting_audit_path: str | Path | None = None,
) -> Any:
    try:
        from ._modern_runtime import AbyssMCPServer  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = AbyssMCPServer(
        "tos-corpus-mcp",
        json_response=True,
        **_read_http_auth_kwargs(),
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

    def current_state() -> ToSCorpusMCPState:
        return ToSCorpusMCPState.discover(
            tos_root=tos_root,
            index_path=index_path,
            philosophy_graph_projection_path=philosophy_graph_projection_path,
            philosophy_post_planting_audit_path=philosophy_post_planting_audit_path,
        )

    @read_only_tool
    def tos_corpus_status() -> dict[str, Any]:
        """Return ToS corpus index path, counts, graph views, and authority boundary."""
        return current_state().status()

    @read_only_tool
    def tos_corpus_summary() -> dict[str, Any]:
        """Return a compact whole-corpus summary from the ToS-owned index."""
        return current_state().summary()

    @read_only_tool
    def tos_corpus_search(query: str, limit: int = 20, resource_kind: str | None = None) -> dict[str, Any]:
        """Search nodes, resources, manifests, branches, and graph views in the ToS corpus index."""
        return current_state().search(query=query, limit=limit, resource_kind=resource_kind)

    @read_only_tool
    def tos_corpus_resources(
        resource_kind: str | None = None,
        owner_branch: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List indexed ToS resources with optional kind and owner-branch filters."""
        return current_state().resources(resource_kind=resource_kind, owner_branch=owner_branch, limit=limit)

    @read_only_tool
    def tos_corpus_node(node_id: str) -> dict[str, Any]:
        """Return one indexed ToS node and relation edges connected to it."""
        return current_state().node(node_id=node_id)

    @read_only_tool
    def tos_corpus_relation_pack(pack_id: str) -> dict[str, Any]:
        """Return one indexed ToS relation pack and its edges."""
        return current_state().relation_pack(pack_id=pack_id)

    @read_only_tool
    def tos_corpus_graph_view(view_id: str, limit: int = 100) -> dict[str, Any]:
        """Return a named graph review view over the whole ToS corpus index."""
        return current_state().graph_view(view_id=view_id, limit=limit)

    @read_only_tool
    def tos_corpus_packet(query: str = "", view_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Return a compact task packet with optional search and graph-view context."""
        return current_state().packet(query=query, view_id=view_id, limit=limit)

    @read_only_tool
    def tos_philosophy_graph_status() -> dict[str, Any]:
        """Return ToS philosophy graph projection path, counts, graph views, and authority boundary."""
        return current_state().philosophy_status()

    @read_only_tool
    def tos_philosophy_graph_views() -> dict[str, Any]:
        """List ToS philosophy graph views materialized by the ToS-owned projection export."""
        return current_state().philosophy_views()

    @read_only_tool
    def tos_philosophy_graph_layers() -> dict[str, Any]:
        """Return ToS-owned philosophy graph layers and layer counts for runtime filtering."""
        return current_state().philosophy_layers()

    @read_only_tool
    def tos_philosophy_graph_contracts() -> dict[str, Any]:
        """Return the bounded MCP access contract for ToS philosophy graph packets."""
        return current_state().philosophy_contracts()

    @read_only_tool
    def tos_philosophy_graph_scale_manifest(view_id: str | None = None, layers: list[str] | None = None) -> dict[str, Any]:
        """Return compact row counts and packet routes for ToS philosophy scale projection access."""
        return current_state().philosophy_scale_manifest(view_id=view_id, layers=layers)

    @read_only_tool
    def tos_philosophy_graph_view(view_id: str) -> dict[str, Any]:
        """Return one ToS philosophy graph view packet with projected nodes, edges, and source refs."""
        return current_state().philosophy_view(view_id=view_id)

    @read_only_tool
    def tos_philosophy_graph_clusters(
        view_id: str | None = None,
        cluster_kind: str | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        """Return compact ToS philosophy graph clusters, optionally filtered by view and cluster kind."""
        return current_state().philosophy_clusters(view_id=view_id, cluster_kind=cluster_kind, limit=limit)

    @read_only_tool
    def tos_philosophy_graph_node(node_id: str) -> dict[str, Any]:
        """Return one projected ToS philosophy node and related projected edges."""
        return current_state().philosophy_node(node_id=node_id)

    @read_only_tool
    def tos_philosophy_graph_edge(edge_id: str) -> dict[str, Any]:
        """Return one projected ToS philosophy edge and its endpoint nodes."""
        return current_state().philosophy_edge(edge_id=edge_id)

    @read_only_tool
    def tos_philosophy_graph_neighborhood(
        node_id: str,
        depth: int = 1,
        layers: list[str] | None = None,
        predicates: list[str] | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        """Return the projected neighborhood around one ToS philosophy node."""
        return current_state().philosophy_neighborhood(
            node_id=node_id,
            depth=depth,
            layers=layers,
            predicates=predicates,
            limit=limit,
        )

    @read_only_tool
    def tos_philosophy_graph_path(
        from_id: str,
        to_id: str,
        layers: list[str] | None = None,
        predicates: list[str] | None = None,
        max_depth: int = 6,
    ) -> dict[str, Any]:
        """Return a bounded path packet between two projected ToS philosophy nodes."""
        return current_state().philosophy_path_between(
            from_id=from_id,
            to_id=to_id,
            layers=layers,
            predicates=predicates,
            max_depth=max_depth,
        )

    @read_only_tool
    def tos_philosophy_graph_review_packet(view_id: str = "chronology") -> dict[str, Any]:
        """Return one compact ToS-owned review packet for a philosophy graph lens."""
        return current_state().philosophy_review_packet(view_id=view_id)

    @read_only_tool
    def tos_philosophy_graph_snapshot() -> dict[str, Any]:
        """Return ToS-owned philosophy graph snapshot fingerprints for diff-aware review."""
        return current_state().philosophy_snapshot()

    @read_only_tool
    def tos_philosophy_graph_audit() -> dict[str, Any]:
        """Return the ToS-owned post-planting audit packet when present."""
        return current_state().philosophy_audit()

    @read_only_tool
    def tos_philosophy_graph_unresolved(view_id: str | None = None) -> dict[str, Any]:
        """Return unresolved review surfaces for all philosophy graph lenses or one selected lens."""
        return current_state().philosophy_unresolved(view_id=view_id)

    @read_only_tool
    def tos_philosophy_graph_packet(query: str = "", view_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Return a compact philosophy graph packet for agents with optional search and view context."""
        return current_state().philosophy_packet(query=query, view_id=view_id, limit=limit)

    @read_only_tool
    def tos_philosophy_graph_chronology_packet(limit: int = 20) -> dict[str, Any]:
        """Return the chronology lens packet for formation, fixation, canonization, and dating review."""
        return current_state().philosophy_lens_packet(view_id="chronology", limit=limit)

    @read_only_tool
    def tos_philosophy_graph_source_evidence_packet(limit: int = 20) -> dict[str, Any]:
        """Return the source-evidence lens packet for source refs, confidence, and witness review."""
        return current_state().philosophy_lens_packet(view_id="source-evidence", limit=limit)

    @read_only_tool
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

    @mcp.resource("tos-philosophy://contracts")
    def philosophy_contracts_resource() -> str:
        return current_state().render_resource("tos-philosophy://contracts")

    @mcp.resource("tos-philosophy://scale-manifest")
    def philosophy_scale_manifest_resource() -> str:
        return current_state().render_resource("tos-philosophy://scale-manifest")

    @mcp.resource("tos-philosophy://snapshot")
    def philosophy_snapshot_resource() -> str:
        return current_state().render_resource("tos-philosophy://snapshot")

    @mcp.resource("tos-philosophy://audit")
    def philosophy_audit_resource() -> str:
        return current_state().render_resource("tos-philosophy://audit")

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

    @mcp.resource("tos-philosophy://edge/{edge_id}")
    def philosophy_edge_resource(edge_id: str) -> str:
        return current_state().render_resource(f"tos-philosophy://edge/{edge_id}")

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
    _run_server(build_server())
