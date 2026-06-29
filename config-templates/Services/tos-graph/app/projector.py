from __future__ import annotations

from typing import Any

from .corpus_reader import ToSCorpusReader
from .neo4j_store import Neo4jProjectionStore, Neo4jStoreStatus
from .philosophy_reader import ToSPhilosophyProjectionReader


class CorpusProjector:
    def __init__(self, reader: ToSCorpusReader, neo4j_status: Neo4jStoreStatus, neo4j_store: Neo4jProjectionStore) -> None:
        self.reader = reader
        self.neo4j_status = neo4j_status
        self.neo4j_store = neo4j_store

    def _preview_sync(self, corpus: dict[str, Any]) -> dict[str, Any]:
        counts = corpus.get("counts", {})
        return {
            "surface": "ToS/derived-exports/tos_corpus_index.min.json",
            "status": "preview_only",
            "node_count": int(counts.get("nodes") or 0),
            "edge_count": int(counts.get("relation_edges") or 0),
            "resource_count": int(counts.get("resources") or 0),
            "branch_count": int(counts.get("branches") or 0),
            "projection_target": "neo4j_preview" if self.neo4j_status.configured else "neo4j_deferred",
            "note": self.neo4j_status.note,
            "deleted_node_count": None,
            "deleted_edge_count": None,
        }

    def sync_corpus(self) -> dict[str, Any]:
        corpus = self.reader.load_index()
        if not self.neo4j_status.ready:
            return self._preview_sync(corpus)

        return self.neo4j_store.sync_corpus_projection(corpus)


class PhilosophyProjector:
    def __init__(
        self,
        reader: ToSPhilosophyProjectionReader,
        neo4j_status: Neo4jStoreStatus,
        neo4j_store: Neo4jProjectionStore,
    ) -> None:
        self.reader = reader
        self.neo4j_status = neo4j_status
        self.neo4j_store = neo4j_store

    def _preview_sync(self, projection: dict[str, Any], scale_export_row_counts: dict[str, int]) -> dict[str, Any]:
        counts = projection.get("counts", {})
        return {
            "surface": "ToS/derived-exports/philosophy_graph_projection.min.json",
            "status": "preview_only",
            "node_count": int(counts.get("nodes") or 0),
            "edge_count": int(counts.get("edges") or 0),
            "resource_count": int(counts.get("source_refs") or 0),
            "branch_count": int(counts.get("views") or 0),
            "projection_target": "neo4j_philosophy_preview" if self.neo4j_status.configured else "neo4j_deferred",
            "note": self.neo4j_status.note,
            "deleted_node_count": None,
            "deleted_edge_count": None,
            "constraint_count": None,
            "scale_export_row_counts": scale_export_row_counts,
        }

    def sync_philosophy(self) -> dict[str, Any]:
        projection = self.reader.load_projection()
        scale_export = self.reader.scale_export_bundle()
        if not self.neo4j_status.ready:
            return self._preview_sync(projection, scale_export["row_counts"])

        result = self.neo4j_store.sync_philosophy_projection(projection)
        result["scale_export_row_counts"] = scale_export["row_counts"]
        return result
