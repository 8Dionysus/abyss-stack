from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import TosGraphSettings


SCALE_EXPORT_COLUMNS = {
    "nodes": [
        "id",
        "label",
        "label_original",
        "label_ru",
        "label_en",
        "kind",
        "view_ids",
        "graph_layers",
        "source_ref",
        "source_refs",
        "properties",
    ],
    "edges": [
        "id",
        "source",
        "target",
        "predicate",
        "label",
        "view_ids",
        "graph_layers",
        "source_ref",
        "source_refs",
        "properties",
    ],
    "clusters": [
        "id",
        "label",
        "label_original",
        "label_ru",
        "label_en",
        "kind",
        "member_count",
        "edge_count",
        "view_ids",
        "graph_layers",
        "source_ref",
        "source_refs",
        "properties",
    ],
    "cluster-node-memberships": [
        "cluster_id",
        "node_id",
        "cluster_kind",
        "cluster_label",
        "view_ids",
        "graph_layers",
        "source_ref",
    ],
    "cluster-edge-memberships": [
        "cluster_id",
        "edge_id",
        "cluster_kind",
        "cluster_label",
        "view_ids",
        "graph_layers",
        "source_ref",
    ],
}


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


def _json_cell(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _multilingual_label(item: dict[str, Any], language: str) -> str:
    multilingual = item.get("multilingual")
    if not isinstance(multilingual, dict):
        return "" if language == "original" else str(item.get("label") or "")
    labels = multilingual.get("label")
    if not isinstance(labels, dict):
        return "" if language == "original" else str(item.get("label") or "")
    value = labels.get(language)
    if value is None:
        return ""
    return str(value)


def _layer_allowed(item: dict[str, Any], layers: set[str]) -> bool:
    if not layers:
        return True
    item_layers = item.get("graph_layers")
    if not isinstance(item_layers, list):
        return False
    return bool(set(str(layer) for layer in item_layers) & layers)


def _predicate_allowed(item: dict[str, Any], predicates: set[str]) -> bool:
    if not predicates:
        return True
    predicate = item.get("predicate_id")
    return isinstance(predicate, str) and predicate in predicates


def _unique_values(items: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({str(item[key]) for item in items if isinstance(item.get(key), str) and item.get(key)})


class ToSPhilosophyProjectionReader:
    def __init__(self, settings: TosGraphSettings) -> None:
        self.settings = settings

    @property
    def projection_path(self) -> Path:
        return self.settings.philosophy_graph_projection_path

    @property
    def audit_path(self) -> Path:
        return self.settings.philosophy_post_planting_audit_path

    def projection_exists(self) -> bool:
        return self.projection_path.is_file()

    def audit_exists(self) -> bool:
        return self.audit_path.is_file()

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

    def load_audit(self) -> dict[str, Any]:
        if not self.audit_exists():
            raise ToSPhilosophyReaderError(f"missing ToS philosophy post-planting audit: {self.audit_path.as_posix()}")
        payload = json.loads(self.audit_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ToSPhilosophyReaderError(
                f"ToS philosophy post-planting audit must be a JSON object: {self.audit_path.as_posix()}"
            )
        if payload.get("schema_version") != "tos_philosophy_post_planting_audit_v1":
            raise ToSPhilosophyReaderError(
                "ToS philosophy post-planting audit schema_version must be tos_philosophy_post_planting_audit_v1"
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
            "snapshot_review": payload.get("snapshot_review", {}),
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
        clusters = self._clusters_for_payload(payload, view_id=view_id, limit=40)
        return {
            "schema": "tos_graph_philosophy_view_v1",
            "view": view,
            "subgraph_contract": self._view_subgraph_contract(payload, view, nodes, edges, clusters),
            "nodes": nodes,
            "edges": edges,
            "clusters": clusters,
            "review_packet": self.review_packet(view_id),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "source_refs": sorted(set(view.get("source_refs", []) + _source_refs(nodes + edges))),
            "counts": payload.get("counts", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    @staticmethod
    def _view_subgraph_contract(
        payload: dict[str, Any],
        view: dict[str, Any],
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        clusters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        source_refs = payload.get("source_refs", {}) if isinstance(payload.get("source_refs"), dict) else {}
        node_ids = {str(node.get("node_id")) for node in nodes if isinstance(node.get("node_id"), str)}
        edge_endpoint_ids = {
            str(endpoint)
            for edge in edges
            for endpoint in (edge.get("from_id"), edge.get("to_id"))
            if isinstance(endpoint, str) and endpoint
        }
        dangling_endpoint_ids = sorted(edge_endpoint_ids - node_ids)
        return {
            "schema": "tos_graph_philosophy_subgraph_contract_v1",
            "view_id": view.get("view_id"),
            "route_card": view.get("route_card"),
            "layout_hint": view.get("layout_hint"),
            "graph_layers": _string_list(view.get("graph_layers")),
            "node_kinds": _unique_values(nodes, "node_type"),
            "edge_predicates": _unique_values(edges, "predicate_id"),
            "cluster_kinds": _unique_values(clusters, "cluster_kind"),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "cluster_count": len(clusters),
            "source_ref_count": len(_source_refs(nodes + edges + clusters)),
            "dangling_endpoint_ids": dangling_endpoint_ids,
            "source_view_contract_ref": source_refs.get("source_view_contract_ref"),
            "runtime_contract": (
                "View responses are source-owned subgraphs selected by Tree-of-Sophia; "
                "tos-graph may filter, render, and import them as projection data only."
            ),
        }

    def contracts(self) -> dict[str, Any]:
        payload = self.load_projection()
        views = [view for view in payload.get("views", []) if isinstance(view, dict)]
        nodes = [node for node in payload.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in payload.get("edges", []) if isinstance(edge, dict)]
        clusters = [cluster for cluster in payload.get("clusters", []) if isinstance(cluster, dict)]
        review_packets = [packet for packet in payload.get("review_packets", []) if isinstance(packet, dict)]
        source_refs = payload.get("source_refs", {}) if isinstance(payload.get("source_refs"), dict) else {}
        review_packet_fields = sorted({key for packet in review_packets for key in packet.keys()})
        view_contracts = []
        for view in views:
            view_nodes = [node for node in view.get("nodes", []) if isinstance(node, dict)]
            view_edges = [edge for edge in view.get("edges", []) if isinstance(edge, dict)]
            view_clusters = self._clusters_for_payload(payload, view_id=str(view.get("view_id") or ""), limit=1_000_000)
            view_contracts.append(self._view_subgraph_contract(payload, view, view_nodes, view_edges, view_clusters))
        return {
            "schema": "tos_graph_philosophy_contracts_v1",
            "source_contract_refs": {
                key: value for key, value in source_refs.items() if isinstance(value, str) and value
            },
            "runtime_contract": {
                "runtime_owner": "abyss-stack",
                "source_owner": "Tree-of-Sophia",
                "projection_surfaces": [
                    "api/philosophy/views",
                    "api/philosophy/views/{view_id}",
                    "api/philosophy/scale-export",
                    "api/philosophy/project/sync",
                ],
                "contract_limits": [
                    "does not promote candidate rows into canon",
                    "does not make Neo4j or UI state source authority",
                    "does not write back to Tree-of-Sophia",
                ],
                "expected_refresh": "rebuild Tree-of-Sophia derived exports, then refresh tos-graph projection",
            },
            "views": view_contracts,
            "node_kinds": _unique_values(nodes, "node_type"),
            "edge_predicates": _unique_values(edges, "predicate_id"),
            "graph_layers": _unique_values(
                [layer for layer in payload.get("graph_layers", []) if isinstance(layer, dict)],
                "layer_id",
            ),
            "cluster_kinds": _unique_values(clusters, "cluster_kind"),
            "review_packet_fields": review_packet_fields,
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
        }

    @staticmethod
    def _query_contract(
        *,
        query_kind: str,
        layers: set[str],
        predicates: set[str],
        limit: int,
        backend: str,
    ) -> dict[str, Any]:
        return {
            "schema": "tos_graph_philosophy_query_contract_v1",
            "query_kind": query_kind,
            "backend": backend,
            "layers": sorted(layers),
            "predicates": sorted(predicates),
            "limit": max(limit, 0),
            "guarantees": [
                "bounded read-only packet",
                "Tree-of-Sophia remains source authority",
                "Neo4j and JSON readers are projection surfaces",
            ],
        }

    @staticmethod
    def _filter_query_surfaces(
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        clusters: list[dict[str, Any]],
        *,
        layers: set[str],
        predicates: set[str],
        limit: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        filtered_edges = [
            edge
            for edge in edges
            if _layer_allowed(edge, layers) and _predicate_allowed(edge, predicates)
        ][: max(limit, 0)]
        endpoint_ids = {
            endpoint
            for edge in filtered_edges
            for endpoint in (edge.get("from_id"), edge.get("to_id"))
            if isinstance(endpoint, str)
        }
        filtered_nodes = [
            node
            for node in nodes
            if _layer_allowed(node, layers) and (not endpoint_ids or node.get("node_id") in endpoint_ids)
        ][: max(limit, 0)]
        if not filtered_nodes and not predicates:
            filtered_nodes = [node for node in nodes if _layer_allowed(node, layers)][: max(limit, 0)]
        node_ids = {str(node.get("node_id")) for node in filtered_nodes if isinstance(node.get("node_id"), str)}
        filtered_clusters = [
            cluster
            for cluster in clusters
            if _layer_allowed(cluster, layers)
            and (
                not node_ids
                or bool(set(_string_list(cluster.get("member_node_ids"))) & node_ids)
            )
        ][: max(limit, 0)]
        return filtered_nodes, filtered_edges, filtered_clusters

    def query_view(
        self,
        view_id: str,
        *,
        layers: set[str] | None = None,
        predicates: set[str] | None = None,
        limit: int = 240,
        query_backend: str = "json",
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        payload = self.load_projection()
        view = next(
            (item for item in payload.get("views", []) if isinstance(item, dict) and item.get("view_id") == view_id),
            None,
        )
        if view is None:
            raise ToSPhilosophyReaderError(f"unknown ToS philosophy graph view: {view_id}")
        layer_filter = layers or set()
        predicate_filter = predicates or set()
        nodes = [node for node in view.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in view.get("edges", []) if isinstance(edge, dict)]
        clusters = self._clusters_for_payload(payload, view_id=view_id, limit=1_000_000)
        nodes, edges, clusters = self._filter_query_surfaces(
            nodes,
            edges,
            clusters,
            layers=layer_filter,
            predicates=predicate_filter,
            limit=limit,
        )
        return {
            "schema": "tos_graph_philosophy_query_view_v1",
            "query_backend": query_backend,
            "fallback_reason": fallback_reason,
            "view_id": view_id,
            "view": {
                key: value
                for key, value in view.items()
                if key not in {"nodes", "edges"}
            },
            "query_contract": self._query_contract(
                query_kind="view-subgraph",
                layers=layer_filter,
                predicates=predicate_filter,
                limit=limit,
                backend=query_backend,
            ),
            "nodes": nodes,
            "edges": edges,
            "clusters": clusters,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "cluster_count": len(clusters),
            "layers": sorted(layer_filter),
            "predicates": sorted(predicate_filter),
            "limit": max(limit, 0),
            "source_refs": _source_refs(nodes + edges + clusters),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
            "authority_note": "Tree-of-Sophia owns graph meaning; this query packet is an abyss-stack runtime projection.",
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

    def scale_export_manifest(self, view_id: str | None = None, layers: set[str] | None = None) -> dict[str, Any]:
        layer_filter = layers or set()
        tables = {
            table_name: {
                "columns": SCALE_EXPORT_COLUMNS[table_name],
                "row_count": len(self.scale_export_table(table_name, view_id=view_id, layers=layer_filter)),
                "formats": ["csv", "jsonl"],
            }
            for table_name in SCALE_EXPORT_COLUMNS
        }
        return {
            "schema": "tos_graph_philosophy_scale_export_manifest_v1",
            "view_id": view_id,
            "layers": sorted(layer_filter),
            "tables": tables,
            "source_projection_ref": self.projection_path.as_posix(),
            "runtime_projection_boundary": self.status().get("runtime_projection_boundary", {}),
            "authority_note": (
                "Tree-of-Sophia owns graph meaning and source_refs; tos-graph only streams "
                "viewer-ready tables for large graph tools."
            ),
        }

    def scale_export_bundle(self, view_id: str | None = None, layers: set[str] | None = None) -> dict[str, Any]:
        layer_filter = layers or set()
        tables = {
            table_name: self.scale_export_table(table_name, view_id=view_id, layers=layer_filter)
            for table_name in SCALE_EXPORT_COLUMNS
        }
        return {
            "schema": "tos_graph_philosophy_scale_export_bundle_v1",
            "manifest": self.scale_export_manifest(view_id=view_id, layers=layer_filter),
            "tables": tables,
            "row_counts": {table_name: len(rows) for table_name, rows in tables.items()},
        }

    def scale_export_table(
        self,
        table_name: str,
        *,
        view_id: str | None = None,
        layers: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        if table_name not in SCALE_EXPORT_COLUMNS:
            raise ToSPhilosophyReaderError(f"unknown ToS philosophy scale export table: {table_name}")
        payload = self.load_projection()
        layer_filter = layers or set()
        nodes, edges, clusters = self._scale_export_surfaces(payload, view_id=view_id, layers=layer_filter)
        if table_name == "nodes":
            return [self._scale_node_row(node) for node in nodes]
        if table_name == "edges":
            return [self._scale_edge_row(edge) for edge in edges]
        if table_name == "clusters":
            return [self._scale_cluster_row(cluster) for cluster in clusters]
        if table_name == "cluster-node-memberships":
            return [
                self._scale_cluster_membership_row(cluster, node_id=node_id)
                for cluster in clusters
                for node_id in _string_list(cluster.get("member_node_ids"))
            ]
        if table_name == "cluster-edge-memberships":
            return [
                self._scale_cluster_membership_row(cluster, edge_id=edge_id)
                for cluster in clusters
                for edge_id in _string_list(cluster.get("member_edge_ids"))
            ]
        raise ToSPhilosophyReaderError(f"unknown ToS philosophy scale export table: {table_name}")

    def _scale_export_surfaces(
        self,
        payload: dict[str, Any],
        *,
        view_id: str | None,
        layers: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        if view_id:
            view = next(
                (item for item in payload.get("views", []) if isinstance(item, dict) and item.get("view_id") == view_id),
                None,
            )
            if view is None:
                raise ToSPhilosophyReaderError(f"unknown ToS philosophy graph view: {view_id}")
            nodes = [node for node in view.get("nodes", []) if isinstance(node, dict) and _layer_allowed(node, layers)]
            edges = [edge for edge in view.get("edges", []) if isinstance(edge, dict) and _layer_allowed(edge, layers)]
            clusters = self._clusters_for_payload(payload, view_id=view_id, limit=1_000_000)
            clusters = [cluster for cluster in clusters if _layer_allowed(cluster, layers)]
            return nodes, edges, clusters
        nodes = [node for node in payload.get("nodes", []) if isinstance(node, dict) and _layer_allowed(node, layers)]
        edges = [edge for edge in payload.get("edges", []) if isinstance(edge, dict) and _layer_allowed(edge, layers)]
        clusters = [cluster for cluster in payload.get("clusters", []) if isinstance(cluster, dict) and _layer_allowed(cluster, layers)]
        return nodes, edges, clusters

    @staticmethod
    def _pipe_cell(value: Any) -> str:
        return "|".join(_string_list(value))

    @classmethod
    def _scale_node_row(cls, node: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(node.get("node_id") or ""),
            "label": str(node.get("label") or node.get("node_id") or ""),
            "label_original": _multilingual_label(node, "original"),
            "label_ru": _multilingual_label(node, "ru"),
            "label_en": _multilingual_label(node, "en"),
            "kind": str(node.get("node_type") or ""),
            "view_ids": cls._pipe_cell(node.get("view_ids")),
            "graph_layers": cls._pipe_cell(node.get("graph_layers")),
            "source_ref": str(node.get("source_ref") or ""),
            "source_refs": _json_cell(node.get("source_refs") or _source_refs([node])),
            "properties": _json_cell(node.get("properties")),
        }

    @classmethod
    def _scale_edge_row(cls, edge: dict[str, Any]) -> dict[str, Any]:
        predicate = str(edge.get("predicate_id") or "")
        return {
            "id": str(edge.get("edge_id") or ""),
            "source": str(edge.get("from_id") or ""),
            "target": str(edge.get("to_id") or ""),
            "predicate": predicate,
            "label": predicate.replace("_", " ").replace("-", " "),
            "view_ids": cls._pipe_cell(edge.get("view_ids")),
            "graph_layers": cls._pipe_cell(edge.get("graph_layers")),
            "source_ref": str(edge.get("source_ref") or ""),
            "source_refs": _json_cell(edge.get("source_refs") or _source_refs([edge])),
            "properties": _json_cell(edge.get("properties")),
        }

    @classmethod
    def _scale_cluster_row(cls, cluster: dict[str, Any]) -> dict[str, Any]:
        properties = cluster.get("properties") if isinstance(cluster.get("properties"), dict) else {}
        return {
            "id": str(cluster.get("cluster_id") or ""),
            "label": str(cluster.get("label") or cluster.get("cluster_id") or ""),
            "label_original": _multilingual_label(cluster, "original"),
            "label_ru": _multilingual_label(cluster, "ru"),
            "label_en": _multilingual_label(cluster, "en"),
            "kind": str(cluster.get("cluster_kind") or ""),
            "member_count": str(properties.get("member_count") or len(_string_list(cluster.get("member_node_ids")))),
            "edge_count": str(properties.get("edge_count") or len(_string_list(cluster.get("member_edge_ids")))),
            "view_ids": cls._pipe_cell(cluster.get("view_ids")),
            "graph_layers": cls._pipe_cell(cluster.get("graph_layers")),
            "source_ref": str(cluster.get("source_ref") or ""),
            "source_refs": _json_cell(cluster.get("source_refs") or _source_refs([cluster])),
            "properties": _json_cell(properties),
        }

    @classmethod
    def _scale_cluster_membership_row(
        cls,
        cluster: dict[str, Any],
        *,
        node_id: str | None = None,
        edge_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "cluster_id": str(cluster.get("cluster_id") or ""),
            "node_id": node_id or "",
            "edge_id": edge_id or "",
            "cluster_kind": str(cluster.get("cluster_kind") or ""),
            "cluster_label": str(cluster.get("label") or ""),
            "view_ids": cls._pipe_cell(cluster.get("view_ids")),
            "graph_layers": cls._pipe_cell(cluster.get("graph_layers")),
            "source_ref": str(cluster.get("source_ref") or ""),
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

    def snapshot(self) -> dict[str, Any]:
        payload = self.load_projection()
        return {
            "schema": "tos_graph_philosophy_snapshot_v1",
            "snapshot_review": payload.get("snapshot_review", {}),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
            "authority_note": "Tree-of-Sophia owns snapshot semantics; tos-graph serves fingerprints for review and diff routing.",
        }

    def audit(self) -> dict[str, Any]:
        if not self.audit_exists():
            return {
                "schema": "tos_graph_philosophy_audit_v1",
                "audit_exists": False,
                "audit_path": self.audit_path.as_posix(),
                "audit": {},
                "authority_note": "Tree-of-Sophia has not published the post-planting audit at this runtime path.",
            }
        return {
            "schema": "tos_graph_philosophy_audit_v1",
            "audit_exists": True,
            "audit_path": self.audit_path.as_posix(),
            "audit": self.load_audit(),
            "authority_note": "Tree-of-Sophia owns the audit; tos-graph serves it for operator review.",
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

    def edge(self, edge_id: str) -> dict[str, Any]:
        payload = self.load_projection()
        edge = next(
            (item for item in payload.get("edges", []) if isinstance(item, dict) and item.get("edge_id") == edge_id),
            None,
        )
        if edge is None:
            raise ToSPhilosophyReaderError(f"unknown ToS philosophy edge: {edge_id}")
        endpoint_ids = {str(edge.get("from_id") or ""), str(edge.get("to_id") or "")}
        endpoints = [
            node
            for node in payload.get("nodes", [])
            if isinstance(node, dict) and str(node.get("node_id") or "") in endpoint_ids
        ]
        views = [
            {
                "view_id": view.get("view_id"),
                "title": view.get("title"),
                "layout_hint": view.get("layout_hint"),
                "graph_layers": view.get("graph_layers", []),
            }
            for view in payload.get("views", [])
            if isinstance(view, dict) and view.get("view_id") in set(edge.get("view_ids", []))
        ]
        return {
            "schema": "tos_graph_philosophy_edge_v1",
            "edge_id": edge_id,
            "edge": edge,
            "endpoints": endpoints,
            "views": views,
            "source_refs": _source_refs([edge] + endpoints),
            "authority_note": "Tree-of-Sophia owns the edge source_ref; tos-graph only serves this projection packet.",
        }

    def neighborhood(
        self,
        node_id: str,
        depth: int = 1,
        layers: set[str] | None = None,
        limit: int = 120,
        predicates: set[str] | None = None,
        query_backend: str = "json",
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        node_packet = self.node(node_id)
        payload = self.load_projection()
        layer_filter = layers or set()
        predicate_filter = predicates or set()
        all_edges = [
            edge
            for edge in payload.get("edges", [])
            if isinstance(edge, dict)
            and _layer_allowed(edge, layer_filter)
            and _predicate_allowed(edge, predicate_filter)
        ]
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
            "query_backend": query_backend,
            "fallback_reason": fallback_reason,
            "node_id": node_id,
            "node": node_packet["node"],
            "neighbors": neighbors,
            "edges": selected_edges,
            "depth": max(depth, 1),
            "layers": sorted(layer_filter),
            "predicates": sorted(predicate_filter),
            "limit": max(limit, 0),
            "source_refs": _source_refs([node_packet["node"]] + neighbors + selected_edges),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
            "authority_note": "Tree-of-Sophia owns graph meaning; this neighborhood is an abyss-stack runtime projection packet.",
        }

    def path_between(
        self,
        from_id: str,
        to_id: str,
        *,
        layers: set[str] | None = None,
        predicates: set[str] | None = None,
        max_depth: int = 6,
        query_backend: str = "json",
        fallback_reason: str | None = None,
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
        predicate_filter = predicates or set()
        adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for edge in payload.get("edges", []):
            if (
                not isinstance(edge, dict)
                or not _layer_allowed(edge, layer_filter)
                or not _predicate_allowed(edge, predicate_filter)
            ):
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
            "query_backend": query_backend,
            "fallback_reason": fallback_reason,
            "from_id": from_id,
            "to_id": to_id,
            "found": bool(found_nodes),
            "layers": sorted(layer_filter),
            "predicates": sorted(predicate_filter),
            "max_depth": max_depth,
            "nodes": path_nodes_payload,
            "edges": found_edges,
            "source_refs": _source_refs(path_nodes_payload + found_edges),
            "runtime_projection_boundary": payload.get("runtime_projection_boundary", {}),
            "authority_note": "Tree-of-Sophia owns graph meaning; this path is an abyss-stack runtime projection packet.",
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
