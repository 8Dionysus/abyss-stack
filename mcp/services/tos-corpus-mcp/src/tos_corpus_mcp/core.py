from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_TOS_ROOT = Path("/srv/AbyssOS/Tree-of-Sophia")
INDEX_RELATIVE_PATH = Path("ToS/derived-exports/tos_corpus_index.min.json")
PHILOSOPHY_PROJECTION_RELATIVE_PATH = Path("ToS/derived-exports/philosophy_graph_projection.min.json")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"ToS corpus index is not a JSON object: {path}")
    return payload


def _contains(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return needle in value.lower()
    if isinstance(value, dict):
        return any(_contains(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, needle) for item in value)
    return False


def _source_refs(items: list[dict[str, Any]]) -> list[str]:
    refs = {
        str(item.get("source_ref"))
        for item in items
        if isinstance(item.get("source_ref"), str) and item.get("source_ref")
    }
    for item in items:
        if isinstance(item.get("source_refs"), list):
            refs.update(str(ref) for ref in item["source_refs"] if isinstance(ref, str) and ref)
    return sorted(refs)


def _layer_allowed(item: dict[str, Any], layers: set[str]) -> bool:
    if not layers:
        return True
    item_layers = item.get("graph_layers")
    if not isinstance(item_layers, list):
        return False
    return bool(set(str(layer) for layer in item_layers) & layers)


@dataclass(slots=True)
class ToSCorpusMCPState:
    tos_root: Path
    index_path: Path
    philosophy_graph_projection_path: Path

    @classmethod
    def discover(
        cls,
        tos_root: str | Path | None = None,
        index_path: str | Path | None = None,
        philosophy_graph_projection_path: str | Path | None = None,
    ) -> "ToSCorpusMCPState":
        root = Path(
            tos_root
            or os.environ.get("AOA_TOS_ROOT")
            or os.environ.get("TOS_ROOT")
            or DEFAULT_TOS_ROOT
        ).expanduser().resolve()
        index = Path(
            index_path
            or os.environ.get("TOS_CORPUS_INDEX_PATH")
            or root / INDEX_RELATIVE_PATH
        ).expanduser()
        if not index.is_absolute():
            index = root / index
        philosophy_projection = Path(
            philosophy_graph_projection_path
            or os.environ.get("TOS_PHILOSOPHY_GRAPH_PROJECTION_PATH")
            or root / PHILOSOPHY_PROJECTION_RELATIVE_PATH
        ).expanduser()
        if not philosophy_projection.is_absolute():
            philosophy_projection = root / philosophy_projection
        return cls(
            tos_root=root,
            index_path=index.resolve(),
            philosophy_graph_projection_path=philosophy_projection.resolve(),
        )

    def index_exists(self) -> bool:
        return self.index_path.is_file()

    def index(self) -> dict[str, Any]:
        return _read_json(self.index_path)

    def philosophy_projection_exists(self) -> bool:
        return self.philosophy_graph_projection_path.is_file()

    def philosophy_projection(self) -> dict[str, Any]:
        payload = _read_json(self.philosophy_graph_projection_path)
        if payload.get("schema_version") != "tos_philosophy_graph_projection_v1":
            raise RuntimeError("ToS philosophy graph projection schema_version must be tos_philosophy_graph_projection_v1")
        return payload

    def status(self) -> dict[str, Any]:
        exists = self.index_exists()
        payload = self.index() if exists else {}
        return {
            "schema": "tos_corpus_mcp_status_v1",
            "index_exists": exists,
            "tos_root": self.tos_root.as_posix(),
            "index_path": self.index_path.as_posix(),
            "owner_repo": payload.get("owner_repo"),
            "surface_kind": payload.get("surface_kind"),
            "counts": payload.get("counts", {}),
            "graph_views": [view.get("view_id") for view in payload.get("graph_views", []) if isinstance(view, dict)],
            "authority_order": payload.get("authority_order", []),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def summary(self) -> dict[str, Any]:
        payload = self.index()
        return {
            "schema": "tos_corpus_mcp_summary_v1",
            "status": self.status(),
            "counts": payload.get("counts", {}),
            "branches": payload.get("branches", []),
            "graph_views": payload.get("graph_views", []),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
            "authority_order": payload.get("authority_order", []),
        }

    def search(self, query: str, limit: int = 20, resource_kind: str | None = None) -> dict[str, Any]:
        payload = self.index()
        needle = query.lower().strip()
        results: list[dict[str, Any]] = []
        for collection_name in ("nodes", "resources", "manifests", "branches", "graph_views"):
            for item in payload.get(collection_name, []):
                if not isinstance(item, dict):
                    continue
                if resource_kind and item.get("resource_kind") != resource_kind:
                    continue
                if needle and not _contains(item, needle):
                    continue
                results.append({"collection": collection_name, "item": item})
                if len(results) >= limit:
                    return self._search_payload(query, resource_kind, results)
        return self._search_payload(query, resource_kind, results)

    def _search_payload(
        self,
        query: str,
        resource_kind: str | None,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "schema": "tos_corpus_mcp_search_v1",
            "query": query,
            "resource_kind": resource_kind,
            "result_count": len(results),
            "results": results,
            "authority_note": "Tree-of-Sophia owns corpus meaning; this MCP packet is an abyss-stack access-plane view.",
        }

    def resources(
        self,
        resource_kind: str | None = None,
        owner_branch: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        payload = self.index()
        items = []
        for resource in payload.get("resources", []):
            if not isinstance(resource, dict):
                continue
            if resource_kind and resource.get("resource_kind") != resource_kind:
                continue
            if owner_branch and resource.get("owner_branch") != owner_branch:
                continue
            items.append(resource)
            if len(items) >= limit:
                break
        return {
            "schema": "tos_corpus_mcp_resources_v1",
            "resource_kind": resource_kind,
            "owner_branch": owner_branch,
            "count": len(items),
            "resources": items,
            "authority_order": payload.get("authority_order", []),
        }

    def node(self, node_id: str) -> dict[str, Any]:
        payload = self.index()
        matches = [
            node
            for node in payload.get("nodes", [])
            if isinstance(node, dict) and node.get("node_id") == node_id
        ]
        related_edges = [
            edge
            for edge in payload.get("relation_edges", [])
            if isinstance(edge, dict) and (edge.get("from_id") == node_id or edge.get("to_id") == node_id)
        ]
        return {
            "schema": "tos_corpus_mcp_node_v1",
            "node_id": node_id,
            "matches": matches,
            "related_edges": related_edges,
            "authority_note": "Node authority stays in the source_path named by the index.",
        }

    def relation_pack(self, pack_id: str) -> dict[str, Any]:
        payload = self.index()
        packs = [
            pack
            for pack in payload.get("relation_packs", [])
            if isinstance(pack, dict) and pack.get("pack_id") == pack_id
        ]
        edges = [
            edge
            for edge in payload.get("relation_edges", [])
            if isinstance(edge, dict) and edge.get("pack_id") == pack_id
        ]
        return {
            "schema": "tos_corpus_mcp_relation_pack_v1",
            "pack_id": pack_id,
            "packs": packs,
            "edges": edges,
            "authority_note": "Relation-pack authority stays in the ToS path named by the pack.",
        }

    def graph_view(self, view_id: str, limit: int = 100) -> dict[str, Any]:
        payload = self.index()
        view = next(
            (item for item in payload.get("graph_views", []) if isinstance(item, dict) and item.get("view_id") == view_id),
            None,
        )
        if view is None:
            raise KeyError(f"unknown ToS graph view: {view_id}")
        if view_id == "corpus-topology":
            items = payload.get("branches", [])[:limit]
        elif view_id == "route-graph":
            items = payload.get("relation_packs", [])[:limit]
        elif view_id == "node-neighborhood":
            items = payload.get("nodes", [])[:limit]
        elif view_id == "provenance-dag":
            items = [
                resource
                for resource in payload.get("resources", [])
                if isinstance(resource, dict)
                and resource.get("owner_branch") in {"ToS/source-witnesses", "ToS/research-packets", "ToS/candidate-intake", "ToS/canon"}
            ][:limit]
        elif view_id == "promotion-flow":
            items = [
                edge
                for edge in payload.get("relation_edges", [])
                if isinstance(edge, dict) and edge.get("owner_branch") == "ToS/candidate-intake"
            ][:limit]
        else:
            items = payload.get("resources", [])[:limit]
        return {
            "schema": "tos_corpus_mcp_graph_view_v1",
            "view": view,
            "item_count": len(items),
            "items": items,
            "counts": payload.get("counts", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def packet(self, query: str = "", view_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        payload = self.index()
        search = self.search(query=query, limit=limit) if query else {"result_count": 0, "results": []}
        view_packet = self.graph_view(view_id, limit=limit) if view_id else None
        return {
            "schema": "tos_corpus_mcp_packet_v1",
            "query": query,
            "view_id": view_id,
            "result_count": search["result_count"],
            "results": search["results"],
            "view": view_packet,
            "counts": payload.get("counts", {}),
            "authority_order": payload.get("authority_order", []),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def philosophy_status(self) -> dict[str, Any]:
        exists = self.philosophy_projection_exists()
        payload = self.philosophy_projection() if exists else {}
        return {
            "schema": "tos_philosophy_mcp_status_v1",
            "projection_exists": exists,
            "tos_root": self.tos_root.as_posix(),
            "projection_path": self.philosophy_graph_projection_path.as_posix(),
            "owner_repo": payload.get("owner_repo"),
            "surface_kind": payload.get("surface_kind"),
            "counts": payload.get("counts", {}),
            "views": [view.get("view_id") for view in payload.get("views", []) if isinstance(view, dict)],
            "graph_layers": [
                layer.get("layer_id")
                for layer in payload.get("graph_layers", [])
                if isinstance(layer, dict) and layer.get("layer_id")
            ],
            "visibility_model": payload.get("visibility_model", {}),
            "runtime_projection_boundary": payload.get(
                "runtime_projection_boundary",
                {
                    "runtime_owner": "abyss-stack",
                    "missing_state": "ToS philosophy graph projection is not present at this MCP path",
                },
            ),
            "authority_note": "Tree-of-Sophia owns philosophy meaning; this MCP packet is an abyss-stack access aid.",
        }

    def philosophy_views(self) -> dict[str, Any]:
        payload = self.philosophy_projection()
        clusters_by_view: dict[str, int] = {}
        for cluster in payload.get("clusters", []):
            if not isinstance(cluster, dict):
                continue
            for view_id in cluster.get("view_ids", []):
                clusters_by_view[str(view_id)] = clusters_by_view.get(str(view_id), 0) + 1
        views = []
        for view in payload.get("views", []):
            if not isinstance(view, dict):
                continue
            views.append(
                {
                    "view_id": view.get("view_id"),
                    "title": view.get("title"),
                    "layout_hint": view.get("layout_hint"),
                    "graph_layers": view.get("graph_layers", []),
                    "node_count": len(view.get("nodes", [])) if isinstance(view.get("nodes"), list) else 0,
                    "edge_count": len(view.get("edges", [])) if isinstance(view.get("edges"), list) else 0,
                    "cluster_count": clusters_by_view.get(str(view.get("view_id")), 0),
                    "review_intent": view.get("review_intent"),
                    "collapse_rule": view.get("collapse_rule", {}),
                    "source_ref": view.get("source_ref"),
                    "route_card": view.get("route_card"),
                }
            )
        return {
            "schema": "tos_philosophy_mcp_views_v1",
            "views": views,
            "counts": payload.get("counts", {}),
            "graph_layers": payload.get("graph_layers", []),
            "layer_counts": payload.get("layer_counts", []),
            "visibility_model": payload.get("visibility_model", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def philosophy_view(self, view_id: str) -> dict[str, Any]:
        payload = self.philosophy_projection()
        view = next(
            (item for item in payload.get("views", []) if isinstance(item, dict) and item.get("view_id") == view_id),
            None,
        )
        if view is None:
            raise KeyError(f"unknown ToS philosophy graph view: {view_id}")
        return {
            "schema": "tos_philosophy_mcp_view_v1",
            "view": view,
            "node_count": len(view.get("nodes", [])) if isinstance(view.get("nodes"), list) else 0,
            "edge_count": len(view.get("edges", [])) if isinstance(view.get("edges"), list) else 0,
            "nodes": view.get("nodes", []),
            "edges": view.get("edges", []),
            "clusters": self._philosophy_clusters_for_payload(payload, view_id=view_id, limit=40),
            "review_packet": self.philosophy_review_packet(view_id),
            "source_refs": view.get("source_refs", []),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    @staticmethod
    def _philosophy_clusters_for_payload(
        payload: dict[str, Any],
        *,
        view_id: str | None = None,
        cluster_kind: str | None = None,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        clusters: list[dict[str, Any]] = []
        for cluster in payload.get("clusters", []):
            if not isinstance(cluster, dict):
                continue
            if view_id and view_id not in set(cluster.get("view_ids", [])):
                continue
            if cluster_kind and cluster.get("cluster_kind") != cluster_kind:
                continue
            clusters.append(cluster)
        clusters.sort(key=lambda item: (str(item.get("cluster_kind") or ""), str(item.get("label") or "")))
        return clusters[: max(limit, 0)]

    def philosophy_layers(self) -> dict[str, Any]:
        payload = self.philosophy_projection()
        return {
            "schema": "tos_philosophy_mcp_layers_v1",
            "graph_layers": payload.get("graph_layers", []),
            "layer_counts": payload.get("layer_counts", []),
            "visibility_model": payload.get("visibility_model", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def philosophy_clusters(
        self,
        view_id: str | None = None,
        cluster_kind: str | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        payload = self.philosophy_projection()
        clusters = self._philosophy_clusters_for_payload(
            payload,
            view_id=view_id,
            cluster_kind=cluster_kind,
            limit=limit,
        )
        return {
            "schema": "tos_philosophy_mcp_clusters_v1",
            "view_id": view_id,
            "cluster_kind": cluster_kind,
            "clusters": clusters,
            "cluster_count": len(clusters),
            "counts": payload.get("counts", {}),
            "source_refs": _source_refs(clusters),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def philosophy_review_packet(self, view_id: str = "chronology") -> dict[str, Any]:
        payload = self.philosophy_projection()
        packet = next(
            (
                item
                for item in payload.get("review_packets", [])
                if isinstance(item, dict) and item.get("view_id") == view_id
            ),
            None,
        )
        if packet is None:
            raise KeyError(f"unknown ToS philosophy review packet view: {view_id}")
        return {
            "schema": "tos_philosophy_mcp_review_packet_v1",
            "packet": packet,
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
            "authority_note": "Tree-of-Sophia owns review packet semantics; MCP serves the compact access packet.",
        }

    def philosophy_unresolved(self, view_id: str | None = None) -> dict[str, Any]:
        payload = self.philosophy_projection()
        surfaces = [item for item in payload.get("unresolved_review_surfaces", []) if isinstance(item, dict)]
        if view_id:
            surfaces = [
                item
                for item in self.philosophy_review_packet(view_id)["packet"].get("unresolved_diagnostics", [])
                if isinstance(item, dict)
            ]
        return {
            "schema": "tos_philosophy_mcp_unresolved_v1",
            "view_id": view_id,
            "unresolved": surfaces,
            "unresolved_count": len(surfaces),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def philosophy_node(self, node_id: str) -> dict[str, Any]:
        payload = self.philosophy_projection()
        node = next(
            (item for item in payload.get("nodes", []) if isinstance(item, dict) and item.get("node_id") == node_id),
            None,
        )
        if node is None:
            raise KeyError(f"unknown ToS philosophy node: {node_id}")
        related_edges = [
            edge
            for edge in payload.get("edges", [])
            if isinstance(edge, dict) and (edge.get("from_id") == node_id or edge.get("to_id") == node_id)
        ]
        return {
            "schema": "tos_philosophy_mcp_node_v1",
            "node_id": node_id,
            "node": node,
            "related_edges": related_edges,
            "authority_note": "Node source_ref stays authoritative in Tree-of-Sophia; MCP exposes an access packet only.",
        }

    def philosophy_neighborhood(
        self,
        node_id: str,
        depth: int = 1,
        layers: list[str] | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        node_packet = self.philosophy_node(node_id)
        payload = self.philosophy_projection()
        layer_filter = set(layers or [])
        all_edges = [edge for edge in payload.get("edges", []) if isinstance(edge, dict) and _layer_allowed(edge, layer_filter)]
        selected_ids = {node_id}
        frontier = {node_id}
        selected_edges: list[dict[str, Any]] = []
        for _ in range(max(depth, 1)):
            next_frontier: set[str] = set()
            for edge in all_edges:
                from_id = str(edge.get("from_id") or "")
                to_id = str(edge.get("to_id") or "")
                if from_id not in frontier and to_id not in frontier:
                    continue
                selected_edges.append(edge)
                if from_id not in selected_ids:
                    next_frontier.add(from_id)
                if to_id not in selected_ids:
                    next_frontier.add(to_id)
            selected_ids.update(next_frontier)
            frontier = next_frontier
            if not frontier or len(selected_ids) >= limit:
                break
        neighbor_ids = selected_ids - {node_id}
        neighbors = [
            node
            for node in payload.get("nodes", [])
            if isinstance(node, dict) and node.get("node_id") in neighbor_ids and _layer_allowed(node, layer_filter)
        ][:limit]
        return {
            "schema": "tos_philosophy_mcp_neighborhood_v1",
            "node": node_packet["node"],
            "neighbors": neighbors,
            "edges": selected_edges[:limit],
            "depth": max(depth, 1),
            "layers": sorted(layer_filter),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def philosophy_search(self, query: str, limit: int = 20) -> dict[str, Any]:
        payload = self.philosophy_projection()
        needle = query.lower().strip()
        results: list[dict[str, Any]] = []
        for collection_name in ("views", "nodes", "edges", "clusters", "review_packets", "graph_layers"):
            for item in payload.get(collection_name, []):
                if not isinstance(item, dict):
                    continue
                if needle and not _contains(item, needle):
                    continue
                results.append({"collection": collection_name, "item": item})
                if len(results) >= limit:
                    return self._philosophy_search_payload(query, results)
        return self._philosophy_search_payload(query, results)

    @staticmethod
    def _philosophy_search_payload(query: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "schema": "tos_philosophy_mcp_search_v1",
            "query": query,
            "result_count": len(results),
            "results": results,
            "authority_note": "Tree-of-Sophia owns philosophy meaning; this MCP search result is an access-plane packet.",
        }

    def philosophy_packet(self, query: str = "", view_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        payload = self.philosophy_projection()
        search = self.philosophy_search(query=query, limit=limit) if query else {"result_count": 0, "results": []}
        view_packet = self.philosophy_view(view_id) if view_id else None
        compact_view = None
        if view_packet:
            compact_view = {
                "view": view_packet["view"],
                "nodes": view_packet["nodes"][:limit],
                "edges": view_packet["edges"][:limit],
                "clusters": view_packet.get("clusters", [])[:limit],
                "review_packet": view_packet.get("review_packet"),
                "source_refs": view_packet["source_refs"],
            }
        return {
            "schema": "tos_philosophy_mcp_packet_v1",
            "query": query,
            "view_id": view_id,
            "result_count": search["result_count"],
            "results": search["results"],
            "view": compact_view,
            "counts": payload.get("counts", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
            "authority_note": "Packets are access aids; ToS owns meaning and Neo4j/UI/MCP remain projections.",
        }

    def philosophy_lens_packet(self, view_id: str, limit: int = 20) -> dict[str, Any]:
        packet = self.philosophy_packet(view_id=view_id, limit=limit)
        review = self.philosophy_review_packet(view_id)
        return {
            "schema": "tos_philosophy_mcp_lens_packet_v1",
            "view_id": view_id,
            "packet": packet,
            "review_packet": review["packet"],
            "authority_note": "Lens packets are compact review slices; ToS source_ref surfaces remain authoritative.",
        }

    def read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "tos-corpus://status":
            return self.status()
        if uri == "tos-corpus://summary":
            return self.summary()
        if uri == "tos-corpus://graph-views":
            payload = self.index()
            return {"schema": "tos_corpus_mcp_graph_views_v1", "graph_views": payload.get("graph_views", [])}
        prefix = "tos-corpus://graph-view/"
        if uri.startswith(prefix):
            return self.graph_view(uri.removeprefix(prefix))
        if uri == "tos-philosophy://status":
            return self.philosophy_status()
        if uri == "tos-philosophy://views":
            return self.philosophy_views()
        if uri == "tos-philosophy://layers":
            return self.philosophy_layers()
        if uri == "tos-philosophy://clusters":
            return self.philosophy_clusters()
        if uri == "tos-philosophy://unresolved":
            return self.philosophy_unresolved()
        philosophy_view_prefix = "tos-philosophy://view/"
        if uri.startswith(philosophy_view_prefix):
            return self.philosophy_view(uri.removeprefix(philosophy_view_prefix))
        philosophy_review_prefix = "tos-philosophy://review-packet/"
        if uri.startswith(philosophy_review_prefix):
            return self.philosophy_review_packet(uri.removeprefix(philosophy_review_prefix))
        philosophy_lens_prefix = "tos-philosophy://lens/"
        if uri.startswith(philosophy_lens_prefix):
            return self.philosophy_lens_packet(uri.removeprefix(philosophy_lens_prefix))
        raise KeyError(f"unknown ToS corpus resource URI: {uri}")

    def render_resource(self, uri: str) -> str:
        return json.dumps(self.read_resource(uri), ensure_ascii=False, indent=2, sort_keys=True)
