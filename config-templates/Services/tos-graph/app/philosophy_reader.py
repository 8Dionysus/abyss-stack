from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import TosGraphSettings


class ToSPhilosophyReaderError(RuntimeError):
    """Raised when the ToS philosophy graph projection cannot be read honestly."""


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


class ToSPhilosophyProjectionReader:
    def __init__(self, settings: TosGraphSettings) -> None:
        self.settings = settings

    @property
    def projection_path(self) -> Path:
        return self.settings.philosophy_graph_projection_path

    def projection_exists(self) -> bool:
        return self.projection_path.is_file()

    def load_projection(self) -> dict[str, Any]:
        if not self.projection_exists():
            raise ToSPhilosophyReaderError(f"missing ToS philosophy graph projection: {self.projection_path.as_posix()}")
        payload = json.loads(self.projection_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ToSPhilosophyReaderError(
                f"ToS philosophy graph projection must be a JSON object: {self.projection_path.as_posix()}"
            )
        if payload.get("schema_version") != "tos_philosophy_graph_projection_v1":
            raise ToSPhilosophyReaderError(
                "ToS philosophy graph projection schema_version must be tos_philosophy_graph_projection_v1"
            )
        return payload

    def status(self) -> dict[str, Any]:
        if not self.projection_exists():
            return {
                "schema": "tos_graph_philosophy_status_v1",
                "projection_exists": False,
                "projection_path": self.projection_path.as_posix(),
                "atlas_projection_path": self.settings.philosophy_atlas_projection_path.as_posix(),
                "graph_views_path": self.settings.philosophy_graph_views_path.as_posix(),
                "counts": {},
                "views": [],
                "graph_layers": [],
                "runtime_projection_boundary": {
                    "runtime_owner": "abyss-stack",
                    "missing_state": "ToS has not installed philosophy_graph_projection.min.json at this runtime path",
                },
            }
        payload = self.load_projection()
        return {
            "schema": "tos_graph_philosophy_status_v1",
            "projection_exists": True,
            "projection_path": self.projection_path.as_posix(),
            "atlas_projection_path": self.settings.philosophy_atlas_projection_path.as_posix(),
            "graph_views_path": self.settings.philosophy_graph_views_path.as_posix(),
            "counts": payload.get("counts", {}),
            "views": [view.get("view_id") for view in payload.get("views", []) if isinstance(view, dict)],
            "graph_layers": [
                layer.get("layer_id")
                for layer in payload.get("graph_layers", [])
                if isinstance(layer, dict) and layer.get("layer_id")
            ],
            "visibility_model": payload.get("visibility_model", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def views(self) -> dict[str, Any]:
        payload = self.load_projection()
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
            "schema": "tos_graph_philosophy_views_v1",
            "views": views,
            "counts": payload.get("counts", {}),
            "graph_layers": payload.get("graph_layers", []),
            "layer_counts": payload.get("layer_counts", []),
            "visibility_model": payload.get("visibility_model", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def view(self, view_id: str) -> dict[str, Any]:
        payload = self.load_projection()
        view = next(
            (item for item in payload.get("views", []) if isinstance(item, dict) and item.get("view_id") == view_id),
            None,
        )
        if view is None:
            raise ToSPhilosophyReaderError(f"unknown ToS philosophy graph view: {view_id}")
        nodes = [node for node in view.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in view.get("edges", []) if isinstance(edge, dict)]
        return {
            "schema": "tos_graph_philosophy_view_v1",
            "view": view,
            "nodes": nodes,
            "edges": edges,
            "clusters": self._clusters_for_payload(payload, view_id=view_id, limit=40),
            "review_packet": self.review_packet(view_id),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "source_refs": sorted(set(view.get("source_refs", []) + _source_refs(nodes + edges))),
            "counts": payload.get("counts", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    @staticmethod
    def _clusters_for_payload(
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

    def layers(self) -> dict[str, Any]:
        payload = self.load_projection()
        return {
            "schema": "tos_graph_philosophy_layers_v1",
            "graph_layers": payload.get("graph_layers", []),
            "layer_counts": payload.get("layer_counts", []),
            "visibility_model": payload.get("visibility_model", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def clusters(self, view_id: str | None = None, cluster_kind: str | None = None, limit: int = 80) -> dict[str, Any]:
        payload = self.load_projection()
        clusters = self._clusters_for_payload(payload, view_id=view_id, cluster_kind=cluster_kind, limit=limit)
        return {
            "schema": "tos_graph_philosophy_clusters_v1",
            "view_id": view_id,
            "cluster_kind": cluster_kind,
            "clusters": clusters,
            "cluster_count": len(clusters),
            "counts": payload.get("counts", {}),
            "source_refs": _source_refs(clusters),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def review_packet(self, view_id: str) -> dict[str, Any]:
        payload = self.load_projection()
        packet = next(
            (
                item
                for item in payload.get("review_packets", [])
                if isinstance(item, dict) and item.get("view_id") == view_id
            ),
            None,
        )
        if packet is None:
            raise ToSPhilosophyReaderError(f"unknown ToS philosophy review packet view: {view_id}")
        return {
            "schema": "tos_graph_philosophy_review_packet_v1",
            "packet": packet,
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
            "authority_note": "Tree-of-Sophia owns review packet semantics; tos-graph serves the compact access packet.",
        }

    def unresolved(self, view_id: str | None = None) -> dict[str, Any]:
        payload = self.load_projection()
        surfaces = [item for item in payload.get("unresolved_review_surfaces", []) if isinstance(item, dict)]
        if view_id:
            packet = self.review_packet(view_id)["packet"]
            surfaces = [item for item in packet.get("unresolved_diagnostics", []) if isinstance(item, dict)]
        return {
            "schema": "tos_graph_philosophy_unresolved_v1",
            "view_id": view_id,
            "unresolved": surfaces,
            "unresolved_count": len(surfaces),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def node(self, node_id: str) -> dict[str, Any]:
        payload = self.load_projection()
        node = next(
            (item for item in payload.get("nodes", []) if isinstance(item, dict) and item.get("node_id") == node_id),
            None,
        )
        if node is None:
            raise ToSPhilosophyReaderError(f"unknown ToS philosophy node: {node_id}")
        related_edges = [
            edge
            for edge in payload.get("edges", [])
            if isinstance(edge, dict) and (edge.get("from_id") == node_id or edge.get("to_id") == node_id)
        ]
        views = [
            {
                "view_id": view.get("view_id"),
                "title": view.get("title"),
                "layout_hint": view.get("layout_hint"),
                "graph_layers": view.get("graph_layers", []),
            }
            for view in payload.get("views", [])
            if isinstance(view, dict) and view.get("view_id") in set(node.get("view_ids", []))
        ]
        return {
            "schema": "tos_graph_philosophy_node_v1",
            "node_id": node_id,
            "node": node,
            "related_edges": related_edges,
            "views": views,
            "source_refs": _source_refs([node] + related_edges),
            "authority_note": "Tree-of-Sophia owns the source_ref surfaces; tos-graph only serves this projection packet.",
        }

    def neighborhood(self, node_id: str, depth: int = 1, layers: set[str] | None = None, limit: int = 120) -> dict[str, Any]:
        node_packet = self.node(node_id)
        payload = self.load_projection()
        layer_filter = layers or set()
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
        selected_edges = selected_edges[:limit]
        neighbor_ids = selected_ids - {node_id}
        neighbors = [
            node
            for node in payload.get("nodes", [])
            if isinstance(node, dict) and node.get("node_id") in neighbor_ids and _layer_allowed(node, layer_filter)
        ][:limit]
        return {
            "schema": "tos_graph_philosophy_neighborhood_v1",
            "node": node_packet["node"],
            "neighbors": neighbors,
            "edges": selected_edges,
            "depth": max(depth, 1),
            "layers": sorted(layer_filter),
            "source_refs": _source_refs([node_packet["node"]] + neighbors + selected_edges),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def path_between(
        self,
        from_id: str,
        to_id: str,
        *,
        layers: set[str] | None = None,
        max_depth: int = 6,
    ) -> dict[str, Any]:
        payload = self.load_projection()
        nodes_by_id = {
            str(node.get("node_id")): node
            for node in payload.get("nodes", [])
            if isinstance(node, dict) and isinstance(node.get("node_id"), str)
        }
        if from_id not in nodes_by_id:
            raise ToSPhilosophyReaderError(f"unknown ToS philosophy node: {from_id}")
        if to_id not in nodes_by_id:
            raise ToSPhilosophyReaderError(f"unknown ToS philosophy node: {to_id}")
        layer_filter = layers or set()
        adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for edge in payload.get("edges", []):
            if not isinstance(edge, dict) or not _layer_allowed(edge, layer_filter):
                continue
            left = str(edge.get("from_id") or "")
            right = str(edge.get("to_id") or "")
            adjacency.setdefault(left, []).append((right, edge))
            adjacency.setdefault(right, []).append((left, edge))

        queue: list[tuple[str, list[str], list[dict[str, Any]]]] = [(from_id, [from_id], [])]
        seen = {from_id}
        found_nodes: list[str] = []
        found_edges: list[dict[str, Any]] = []
        while queue:
            current, path_nodes, path_edges = queue.pop(0)
            if current == to_id:
                found_nodes = path_nodes
                found_edges = path_edges
                break
            if len(path_edges) >= max_depth:
                continue
            for neighbor, edge in adjacency.get(current, []):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, [*path_nodes, neighbor], [*path_edges, edge]))

        path_nodes_payload = [nodes_by_id[node_id] for node_id in found_nodes]
        return {
            "schema": "tos_graph_philosophy_path_v1",
            "from_id": from_id,
            "to_id": to_id,
            "found": bool(found_nodes),
            "layers": sorted(layer_filter),
            "max_depth": max_depth,
            "nodes": path_nodes_payload,
            "edges": found_edges,
            "source_refs": _source_refs(path_nodes_payload + found_edges),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def search(self, query: str, limit: int = 40) -> dict[str, Any]:
        payload = self.load_projection()
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
                    return self._search_payload(query, results)
        return self._search_payload(query, results)

    @staticmethod
    def _search_payload(query: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "schema": "tos_graph_philosophy_search_v1",
            "query": query,
            "result_count": len(results),
            "results": results,
            "authority_note": "Tree-of-Sophia owns philosophy meaning; tos-graph serves a runtime projection only.",
        }

    def packet(self, query: str = "", view_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        payload = self.load_projection()
        view_packet = self.view(view_id) if view_id else None
        search_packet = self.search(query=query, limit=limit) if query else {"result_count": 0, "results": []}
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
            "schema": "tos_graph_philosophy_packet_v1",
            "query": query,
            "view_id": view_id,
            "result_count": search_packet["result_count"],
            "results": search_packet["results"],
            "view": compact_view,
            "counts": payload.get("counts", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
            "authority_note": "This packet is an access aid; ToS remains source authority and Neo4j/UI/MCP remain projections.",
        }
