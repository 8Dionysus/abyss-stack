from __future__ import annotations

from typing import Any

from .neo4j_store import Neo4jProjectionStore, Neo4jStoreStatus
from .tos_reader import ToSReader


class RouteProjector:
    def __init__(self, reader: ToSReader, neo4j_status: Neo4jStoreStatus, neo4j_store: Neo4jProjectionStore) -> None:
        self.reader = reader
        self.neo4j_status = neo4j_status
        self.neo4j_store = neo4j_store

    def _preview_sync(self, graph: dict[str, Any]) -> dict[str, Any]:
        return {
            "route": graph["route"],
            "status": "preview_only",
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "projection_target": "neo4j_preview" if self.neo4j_status.configured else "neo4j_deferred",
            "note": self.neo4j_status.note,
            "deleted_node_count": None,
            "deleted_edge_count": None,
        }

    def sync_route(self, route: str | None = None) -> dict[str, Any]:
        graph = self.reader.get_route_graph(route)
        if not self.neo4j_status.ready:
            return self._preview_sync(graph)

        route_entry = next(
            (entry for entry in self.reader.list_routes() if entry["route"] == graph["route"]),
            None,
        )
        route_label = route_entry["label"] if route_entry else graph["route"]
        return self.neo4j_store.sync_route_projection(graph, route_label)
