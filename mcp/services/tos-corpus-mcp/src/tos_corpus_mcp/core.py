from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_TOS_ROOT = Path("/srv/AbyssOS/Tree-of-Sophia")
INDEX_RELATIVE_PATH = Path("ToS/derived-exports/tos_corpus_index.min.json")


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


@dataclass(slots=True)
class ToSCorpusMCPState:
    tos_root: Path
    index_path: Path

    @classmethod
    def discover(
        cls,
        tos_root: str | Path | None = None,
        index_path: str | Path | None = None,
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
        return cls(tos_root=root, index_path=index.resolve())

    def index_exists(self) -> bool:
        return self.index_path.is_file()

    def index(self) -> dict[str, Any]:
        return _read_json(self.index_path)

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
        raise KeyError(f"unknown ToS corpus resource URI: {uri}")

    def render_resource(self, uri: str) -> str:
        return json.dumps(self.read_resource(uri), ensure_ascii=False, indent=2, sort_keys=True)
