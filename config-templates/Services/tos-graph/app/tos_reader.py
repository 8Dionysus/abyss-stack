from __future__ import annotations

import csv
import hashlib
import json
from functools import cached_property
from pathlib import Path
from typing import Any


class ToSReaderError(RuntimeError):
    """Raised when the requested ToS route or payload cannot be loaded."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_label(payload: dict[str, Any]) -> str:
    for key in ("canonical_label", "source_anchor", "distilled_thesis", "node_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unnamed-node"


class ToSReader:
    def __init__(self, tos_root: Path, route_default: str) -> None:
        self.tos_root = tos_root
        self.route_default = route_default

    @property
    def tree_root(self) -> Path:
        return self.tos_root / "tree"

    @property
    def relations_root(self) -> Path:
        return self.tree_root / "relations"

    @property
    def source_root(self) -> Path:
        return self.tree_root / "source"

    def route_or_default(self, route: str | None) -> str:
        return route or self.route_default

    def route_edges_path(self, route: str) -> Path:
        return self.relations_root / route / "edges.csv"

    def route_source_node_path(self, route: str) -> Path:
        return self.source_root / route / "node.json"

    def assert_route_exists(self, route: str) -> None:
        if not self.route_edges_path(route).exists():
            raise ToSReaderError(f"unknown route: {route}")

    @cached_property
    def node_index(self) -> dict[str, tuple[dict[str, Any], Path]]:
        index: dict[str, tuple[dict[str, Any], Path]] = {}
        for path in self.tree_root.rglob("node.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            node_id = payload.get("node_id")
            if isinstance(node_id, str) and node_id:
                index[node_id] = (payload, path)
        return index

    @cached_property
    def edge_index(self) -> dict[str, tuple[dict[str, str], Path, str]]:
        index: dict[str, tuple[dict[str, str], Path, str]] = {}
        for path in self.relations_root.rglob("edges.csv"):
            route = path.parent.relative_to(self.relations_root).as_posix()
            with path.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    edge_id = row.get("edge_id")
                    if edge_id:
                        index[edge_id] = (row, path, route)
        return index

    def load_source_node(self, route: str) -> tuple[dict[str, Any] | None, Path | None]:
        source_path = self.route_source_node_path(route)
        if not source_path.exists():
            return None, None
        return json.loads(source_path.read_text(encoding="utf-8")), source_path

    def load_route_edges(self, route: str) -> tuple[list[dict[str, str]], Path]:
        path = self.route_edges_path(route)
        if not path.exists():
            raise ToSReaderError(f"missing relation pack for route: {route}")
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return rows, path

    def summarize_node(self, payload: dict[str, Any], path: Path, route: str) -> dict[str, Any]:
        return {
            "node_id": payload.get("node_id"),
            "node_type": payload.get("node_type"),
            "canonical_label": _canonical_label(payload),
            "source_anchor": payload.get("source_anchor"),
            "key_terms": payload.get("key_terms", []),
            "distilled_thesis": payload.get("distilled_thesis"),
            "interpretation_layers": payload.get("interpretation_layers", []),
            "relations": payload.get("relations", []),
            "language_witnesses": payload.get("language_witnesses", []),
            "translation_tensions": payload.get("translation_tensions", []),
            "route_path": route,
            "source_file_path": path.as_posix(),
            "source_file_sha256": _sha256(path),
            "raw_payload": payload,
        }

    def summarize_edge(self, row: dict[str, str], path: Path, route: str) -> dict[str, Any]:
        enriched = dict(row)
        enriched["route_path"] = route
        enriched["source_file_path"] = path.as_posix()
        enriched["source_file_sha256"] = _sha256(path)
        return enriched

    def list_routes(self) -> list[dict[str, Any]]:
        routes: list[dict[str, Any]] = []
        for path in sorted(self.relations_root.rglob("edges.csv")):
            route = path.parent.relative_to(self.relations_root).as_posix()
            with path.open("r", encoding="utf-8", newline="") as handle:
                edge_count = sum(1 for _ in csv.DictReader(handle))
            source_payload, _ = self.load_source_node(route)
            routes.append(
                {
                    "route": route,
                    "label": _canonical_label(source_payload) if source_payload else route,
                    "edge_count": edge_count,
                    "has_source_node": source_payload is not None,
                    "selected": route == self.route_default,
                }
            )
        return routes

    def get_route_graph(self, route: str | None = None) -> dict[str, Any]:
        selected_route = self.route_or_default(route)
        self.assert_route_exists(selected_route)
        edges, edge_path = self.load_route_edges(selected_route)
        source_payload, source_path = self.load_source_node(selected_route)

        node_ids: set[str] = set()
        for edge in edges:
            for key in ("from_id", "to_id"):
                value = edge.get(key)
                if value:
                    node_ids.add(value)
        if source_payload and isinstance(source_payload.get("node_id"), str):
            node_ids.add(source_payload["node_id"])

        nodes: list[dict[str, Any]] = []
        missing_nodes: list[str] = []
        for node_id in sorted(node_ids):
            payload_and_path = self.node_index.get(node_id)
            if payload_and_path is None:
                missing_nodes.append(node_id)
                continue
            payload, path = payload_and_path
            nodes.append(self.summarize_node(payload, path, selected_route))

        source_node = (
            self.summarize_node(source_payload, source_path, selected_route)
            if source_payload and source_path
            else None
        )
        return {
            "route": selected_route,
            "source_node": source_node,
            "nodes": nodes,
            "edges": [self.summarize_edge(edge, edge_path, selected_route) for edge in edges],
            "diagnostics": {
                "missing_nodes": missing_nodes,
                "edge_file": edge_path.as_posix(),
                "edge_file_sha256": _sha256(edge_path),
            },
        }

    def get_route_tree(self, route: str | None = None) -> dict[str, Any]:
        graph = self.get_route_graph(route)
        family_counts: dict[str, int] = {}
        for node in graph["nodes"]:
            family = str(node.get("node_type") or "unknown")
            family_counts[family] = family_counts.get(family, 0) + 1
        return {
            "route": graph["route"],
            "source_node": graph["source_node"],
            "family_counts": dict(sorted(family_counts.items())),
            "edge_count": len(graph["edges"]),
            "node_count": len(graph["nodes"]),
        }

    def get_node(self, node_id: str) -> dict[str, Any]:
        payload_and_path = self.node_index.get(node_id)
        if payload_and_path is None:
            raise ToSReaderError(f"unknown node: {node_id}")
        payload, path = payload_and_path
        return self.summarize_node(payload, path, self.route_default)

    def get_edge(self, edge_id: str) -> dict[str, Any]:
        payload = self.edge_index.get(edge_id)
        if payload is None:
            raise ToSReaderError(f"unknown edge: {edge_id}")
        row, path, route = payload
        return self.summarize_edge(row, path, route)
