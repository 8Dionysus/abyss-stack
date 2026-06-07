from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import TosGraphSettings


class ToSCorpusReaderError(RuntimeError):
    """Raised when the ToS corpus index cannot be read honestly."""


def _contains(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return needle in value.lower()
    if isinstance(value, dict):
        return any(_contains(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, needle) for item in value)
    return False


class ToSCorpusReader:
    def __init__(self, settings: TosGraphSettings) -> None:
        self.settings = settings

    @property
    def index_path(self) -> Path:
        return self.settings.corpus_index_path

    def index_exists(self) -> bool:
        return self.index_path.is_file()

    def load_index(self) -> dict[str, Any]:
        if not self.index_exists():
            raise ToSCorpusReaderError(f"missing ToS corpus index: {self.index_path.as_posix()}")
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ToSCorpusReaderError(f"ToS corpus index must be a JSON object: {self.index_path.as_posix()}")
        if payload.get("schema_version") != "tos_corpus_index_v1":
            raise ToSCorpusReaderError("ToS corpus index schema_version must be tos_corpus_index_v1")
        return payload

    def status(self) -> dict[str, Any]:
        if not self.index_exists():
            return {
                "schema": "tos_graph_corpus_status_v1",
                "index_exists": False,
                "index_path": self.index_path.as_posix(),
                "counts": {},
                "graph_views": [],
                "authority_order": [],
                "runtime_projection_boundary": {},
            }
        payload = self.load_index()
        return {
            "schema": "tos_graph_corpus_status_v1",
            "index_exists": True,
            "index_path": self.index_path.as_posix(),
            "counts": payload.get("counts", {}),
            "graph_views": [view.get("view_id") for view in payload.get("graph_views", []) if isinstance(view, dict)],
            "authority_order": payload.get("authority_order", []),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def summary(self) -> dict[str, Any]:
        payload = self.load_index()
        return {
            "schema": "tos_graph_corpus_summary_v1",
            "status": self.status(),
            "counts": payload.get("counts", {}),
            "branches": payload.get("branches", []),
            "graph_views": payload.get("graph_views", []),
            "authority_order": payload.get("authority_order", []),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    def search(self, query: str, limit: int = 20) -> dict[str, Any]:
        payload = self.load_index()
        needle = query.lower().strip()
        results: list[dict[str, Any]] = []
        for collection_name in ("nodes", "resources", "manifests", "branches", "graph_views", "relation_packs"):
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
            "schema": "tos_graph_corpus_search_v1",
            "query": query,
            "result_count": len(results),
            "results": results,
            "authority_note": "Tree-of-Sophia owns corpus meaning; tos-graph is a runtime projection and review surface.",
        }

    def node(self, node_id: str) -> dict[str, Any]:
        payload = self.load_index()
        matches = [node for node in payload.get("nodes", []) if isinstance(node, dict) and node.get("node_id") == node_id]
        related_edges = [
            edge
            for edge in payload.get("relation_edges", [])
            if isinstance(edge, dict) and (edge.get("from_id") == node_id or edge.get("to_id") == node_id)
        ]
        return {
            "schema": "tos_graph_corpus_node_v1",
            "node_id": node_id,
            "matches": matches,
            "related_edges": related_edges,
            "authority_note": "Node authority stays in the source_path named by the ToS index.",
        }

    def relation_pack(self, pack_id: str) -> dict[str, Any]:
        payload = self.load_index()
        packs = [pack for pack in payload.get("relation_packs", []) if isinstance(pack, dict) and pack.get("pack_id") == pack_id]
        edges = [edge for edge in payload.get("relation_edges", []) if isinstance(edge, dict) and edge.get("pack_id") == pack_id]
        return {
            "schema": "tos_graph_corpus_relation_pack_v1",
            "pack_id": pack_id,
            "packs": packs,
            "edges": edges,
            "authority_note": "Relation-pack authority stays in the ToS path named by the pack.",
        }

    def graph_view(self, view_id: str, limit: int = 100) -> dict[str, Any]:
        payload = self.load_index()
        view = next(
            (item for item in payload.get("graph_views", []) if isinstance(item, dict) and item.get("view_id") == view_id),
            None,
        )
        if view is None:
            raise ToSCorpusReaderError(f"unknown ToS graph view: {view_id}")
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
            "schema": "tos_graph_corpus_graph_view_v1",
            "view": view,
            "item_count": len(items),
            "items": items,
            "counts": payload.get("counts", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }
