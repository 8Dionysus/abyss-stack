from __future__ import annotations

from typing import Any

from .neo4j_store import Neo4jStoreStatus
from .tos_reader import ToSReader


class PreviewProjector:
    def __init__(self, reader: ToSReader, neo4j_status: Neo4jStoreStatus) -> None:
        self.reader = reader
        self.neo4j_status = neo4j_status

    def sync_route_preview(self, route: str | None = None) -> dict[str, Any]:
        graph = self.reader.get_route_graph(route)
        return {
            "route": graph["route"],
            "status": "preview_only",
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "projection_target": "neo4j" if self.neo4j_status.configured else "neo4j_deferred",
            "note": self.neo4j_status.note,
        }
