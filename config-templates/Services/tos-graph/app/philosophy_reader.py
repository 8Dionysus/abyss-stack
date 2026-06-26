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
    return sorted(refs)


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
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def views(self) -> dict[str, Any]:
        payload = self.load_projection()
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
                    "source_ref": view.get("source_ref"),
                    "route_card": view.get("route_card"),
                }
            )
        return {
            "schema": "tos_graph_philosophy_views_v1",
            "views": views,
            "counts": payload.get("counts", {}),
            "graph_layers": payload.get("graph_layers", []),
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
            "node_count": len(nodes),
            "edge_count": len(edges),
            "source_refs": sorted(set(view.get("source_refs", []) + _source_refs(nodes + edges))),
            "counts": payload.get("counts", {}),
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

    def neighborhood(self, node_id: str) -> dict[str, Any]:
        node_packet = self.node(node_id)
        payload = self.load_projection()
        related_edges = node_packet["related_edges"]
        neighbor_ids = {
            str(edge.get("from_id"))
            for edge in related_edges
            if edge.get("from_id") != node_id
        } | {
            str(edge.get("to_id"))
            for edge in related_edges
            if edge.get("to_id") != node_id
        }
        neighbors = [
            node
            for node in payload.get("nodes", [])
            if isinstance(node, dict) and node.get("node_id") in neighbor_ids
        ]
        return {
            "schema": "tos_graph_philosophy_neighborhood_v1",
            "node": node_packet["node"],
            "neighbors": neighbors,
            "edges": related_edges,
            "source_refs": _source_refs([node_packet["node"]] + neighbors + related_edges),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def search(self, query: str, limit: int = 40) -> dict[str, Any]:
        payload = self.load_projection()
        needle = query.lower().strip()
        results: list[dict[str, Any]] = []
        for collection_name in ("views", "nodes", "edges", "graph_layers"):
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
