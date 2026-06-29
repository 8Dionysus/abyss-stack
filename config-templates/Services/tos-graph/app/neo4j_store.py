from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .config import TosGraphSettings


class Neo4jStoreError(RuntimeError):
    """Raised when the Neo4j projection lane cannot complete honestly."""


@dataclass(frozen=True)
class Neo4jStoreStatus:
    configured: bool
    ready: bool
    uri: str | None
    user: str | None
    database: str
    projection_mode: str
    note: str


def describe_neo4j_store(settings: TosGraphSettings) -> Neo4jStoreStatus:
    if not settings.neo4j_uri:
        return Neo4jStoreStatus(
            configured=False,
            ready=False,
            uri=None,
            user=settings.neo4j_user,
            database=settings.neo4j_database,
            projection_mode=settings.projection_mode,
            note="neo4j projection sync is unavailable because TOS_GRAPH_NEO4J_URI is missing; sync requests fall back to preview counts",
        )

    if settings.projection_mode == "preview_only":
        return Neo4jStoreStatus(
            configured=True,
            ready=False,
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            database=settings.neo4j_database,
            projection_mode=settings.projection_mode,
            note="neo4j is configured, but projection mode is preview_only so sync requests stop at dry-run counts",
        )

    if not settings.neo4j_user or not settings.neo4j_password:
        return Neo4jStoreStatus(
            configured=True,
            ready=False,
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            database=settings.neo4j_database,
            projection_mode=settings.projection_mode,
            note="neo4j projection sync is configured but credentials are incomplete; sync requests fall back to preview counts",
        )

    return Neo4jStoreStatus(
        configured=True,
        ready=True,
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        database=settings.neo4j_database,
        projection_mode=settings.projection_mode,
        note="neo4j projection sync is ready; Tree of Sophia remains canonical and Neo4j remains projection-only",
    )


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _list_dump(value: Any) -> str:
    return _json_dump(value if isinstance(value, list) else [])


def _json_load(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


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


def _predicate_allowed(item: dict[str, Any], predicates: set[str]) -> bool:
    if not predicates:
        return True
    predicate = item.get("predicate_id")
    return isinstance(predicate, str) and predicate in predicates


def _chunks(rows: list[dict[str, Any]], size: int = 100) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


ConstraintSpec = tuple[str, str, str]

CORPUS_CONSTRAINTS: tuple[ConstraintSpec, ...] = (
    ("tos_corpus_projection_owner", "TosCorpusProjection", "owner_repo"),
    ("tos_corpus_branch_projection_id", "TosCorpusBranchProjection", "projection_id"),
    ("tos_corpus_manifest_projection_id", "TosCorpusManifestProjection", "projection_id"),
    ("tos_corpus_node_projection_id", "TosCorpusNodeProjection", "projection_id"),
    ("tos_corpus_relation_pack_projection_id", "TosCorpusRelationPackProjection", "projection_id"),
    ("tos_corpus_relation_edge_projection_id", "TosCorpusRelationEdgeProjection", "projection_id"),
    ("tos_corpus_resource_projection_id", "TosCorpusResourceProjection", "projection_id"),
    ("tos_corpus_graph_view_projection_id", "TosCorpusGraphViewProjection", "projection_id"),
)

PHILOSOPHY_CONSTRAINTS: tuple[ConstraintSpec, ...] = (
    ("tos_philosophy_projection_owner", "TosPhilosophyProjection", "owner_repo"),
    ("tos_philosophy_view_projection_id", "TosPhilosophyViewProjection", "projection_id"),
    ("tos_philosophy_node_projection_id", "TosPhilosophyNodeProjection", "projection_id"),
    ("tos_philosophy_edge_projection_id", "TosPhilosophyEdgeProjection", "projection_id"),
    ("tos_philosophy_source_ref_projection_id", "TosPhilosophySourceRefProjection", "projection_id"),
    ("tos_philosophy_layer_projection_id", "TosPhilosophyLayerProjection", "projection_id"),
    ("tos_philosophy_cluster_projection_id", "TosPhilosophyClusterProjection", "projection_id"),
    ("tos_philosophy_review_packet_projection_id", "TosPhilosophyReviewPacketProjection", "projection_id"),
)

PHILOSOPHY_RELATION_TYPES = [
    "PROJECTS_VIEW",
    "PROJECTS_NODE",
    "PROJECTS_EDGE",
    "PROJECTS_LAYER",
    "PROJECTS_CLUSTER",
    "PROJECTS_REVIEW_PACKET",
    "PROJECTS_SOURCE_REF",
    "IN_VIEW",
    "IN_LAYER",
    "HAS_SOURCE_REF",
    "CLUSTERS_NODE",
    "CLUSTERS_EDGE",
    "HAS_REVIEW_PACKET",
    "REVIEWS_VIEW",
    "FROM_NODE",
    "TO_NODE",
    "TOS_PHILOSOPHY_RELATION",
]


class Neo4jProjectionStore:
    def __init__(self, settings: TosGraphSettings, status: Neo4jStoreStatus) -> None:
        self.settings = settings
        self.status = status

    def _execute_philosophy_read(self, query_fn: Any, *args: Any) -> Any:
        if not self.status.ready or not self.settings.neo4j_password:
            raise Neo4jStoreError(self.status.note)

        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )
        try:
            with driver.session(database=self.settings.neo4j_database) as session:
                return session.execute_read(query_fn, *args)
        except Exception as exc:  # pragma: no cover - runtime integration path
            raise Neo4jStoreError(f"neo4j philosophy query failed: {exc}") from exc
        finally:
            driver.close()

    @staticmethod
    def _record_value(record: Any, key: str) -> Any:
        if record is None:
            return None
        if hasattr(record, "get"):
            return record.get(key)
        return record[key]

    @classmethod
    def _payload_from_record(cls, record: Any, key: str = "payload_json") -> dict[str, Any]:
        payload = _json_load(cls._record_value(record, key))
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _payloads_from_result(cls, result: Any, key: str = "payload_json") -> list[dict[str, Any]]:
        rows = result.data() if hasattr(result, "data") else []
        payloads: list[dict[str, Any]] = []
        for row in rows:
            payload = _json_load(row.get(key))
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    @classmethod
    def _runtime_boundary_from_tx(cls, tx: Any) -> dict[str, Any]:
        record = tx.run(
            """
            MATCH (projection:TosPhilosophyProjection {owner_repo: 'Tree-of-Sophia'})
            RETURN projection.runtime_projection_boundary_json AS boundary_json
            LIMIT 1
            """
        ).single()
        boundary = _json_load(cls._record_value(record, "boundary_json"))
        return boundary if isinstance(boundary, dict) else {}

    @staticmethod
    def _bounded_depth(depth: int, *, default: int, maximum: int) -> int:
        try:
            value = int(depth)
        except (TypeError, ValueError):
            return default
        return max(1, min(maximum, value))

    @staticmethod
    def _bounded_limit(limit: int, *, default: int = 240, maximum: int = 2000) -> int:
        try:
            value = int(limit)
        except (TypeError, ValueError):
            return default
        return max(1, min(maximum, value))

    @staticmethod
    def _query_contract(
        *,
        query_kind: str,
        layers: set[str],
        predicates: set[str],
        limit: int,
    ) -> dict[str, Any]:
        return {
            "schema": "tos_graph_philosophy_query_contract_v1",
            "query_kind": query_kind,
            "backend": "neo4j",
            "layers": sorted(layers),
            "predicates": sorted(predicates),
            "limit": limit,
            "guarantees": [
                "bounded read-only packet",
                "Neo4j is projection cache only",
                "Tree-of-Sophia remains source authority",
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
        ][:limit]
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
        ][:limit]
        if not filtered_nodes and not predicates:
            filtered_nodes = [node for node in nodes if _layer_allowed(node, layers)][:limit]
        node_ids = {str(node.get("node_id")) for node in filtered_nodes if isinstance(node.get("node_id"), str)}
        filtered_clusters = [
            cluster
            for cluster in clusters
            if _layer_allowed(cluster, layers)
            and (
                not node_ids
                or bool(set(_string_list(cluster.get("member_node_ids"))) & node_ids)
            )
        ][:limit]
        return filtered_nodes, filtered_edges, filtered_clusters

    def query_philosophy_view_subgraph(
        self,
        view_id: str,
        *,
        layers: set[str] | None = None,
        predicates: set[str] | None = None,
        limit: int = 240,
    ) -> dict[str, Any]:
        limit = self._bounded_limit(limit)
        layer_filter = layers or set()
        predicate_filter = predicates or set()
        packet = self._execute_philosophy_read(self._query_philosophy_view_subgraph_tx, view_id, limit)
        if not packet["view"]:
            raise Neo4jStoreError(f"unknown ToS philosophy graph view in neo4j projection: {view_id}")
        nodes, edges, clusters = self._filter_query_surfaces(
            packet["nodes"],
            packet["edges"],
            packet["clusters"],
            layers=layer_filter,
            predicates=predicate_filter,
            limit=limit,
        )
        return {
            "schema": "tos_graph_philosophy_query_view_v1",
            "query_backend": "neo4j",
            "fallback_reason": None,
            "view_id": view_id,
            "view": packet["view"],
            "query_contract": self._query_contract(
                query_kind="view-subgraph",
                layers=layer_filter,
                predicates=predicate_filter,
                limit=limit,
            ),
            "nodes": nodes,
            "edges": edges,
            "clusters": clusters,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "cluster_count": len(clusters),
            "layers": sorted(layer_filter),
            "predicates": sorted(predicate_filter),
            "limit": limit,
            "source_refs": _source_refs(nodes + edges + clusters),
            "runtime_projection_boundary": packet["runtime_projection_boundary"],
            "authority_note": "Tree-of-Sophia owns graph meaning; Neo4j serves a bounded abyss-stack projection packet.",
        }

    @classmethod
    def _query_philosophy_view_subgraph_tx(cls, tx: Any, view_id: str, limit: int) -> dict[str, Any]:
        view = cls._payload_from_record(
            tx.run(
                """
                MATCH (view:TosPhilosophyViewProjection {projection_id: $view_id})
                RETURN view.payload_json AS payload_json
                LIMIT 1
                """,
                view_id=view_id,
            ).single()
        )
        query_limit = max(limit * 3, limit)
        nodes = cls._payloads_from_result(
            tx.run(
                """
                MATCH (:TosPhilosophyViewProjection {projection_id: $view_id})-[:PROJECTS_NODE]->(node:TosPhilosophyNodeProjection)
                RETURN node.payload_json AS payload_json
                LIMIT $limit
                """,
                view_id=view_id,
                limit=query_limit,
            )
        )
        edges = cls._payloads_from_result(
            tx.run(
                """
                MATCH (:TosPhilosophyViewProjection {projection_id: $view_id})-[:PROJECTS_EDGE]->(edge:TosPhilosophyEdgeProjection)
                RETURN edge.payload_json AS payload_json
                LIMIT $limit
                """,
                view_id=view_id,
                limit=query_limit,
            )
        )
        clusters = cls._payloads_from_result(
            tx.run(
                """
                MATCH (:TosPhilosophyViewProjection {projection_id: $view_id})-[:PROJECTS_CLUSTER]->(cluster:TosPhilosophyClusterProjection)
                RETURN cluster.payload_json AS payload_json
                LIMIT $limit
                """,
                view_id=view_id,
                limit=query_limit,
            )
        )
        return {
            "view": {key: value for key, value in view.items() if key not in {"nodes", "edges"}},
            "nodes": nodes,
            "edges": edges,
            "clusters": clusters,
            "runtime_projection_boundary": cls._runtime_boundary_from_tx(tx),
        }

    def query_philosophy_neighborhood(
        self,
        node_id: str,
        *,
        depth: int = 1,
        layers: set[str] | None = None,
        predicates: set[str] | None = None,
        limit: int = 160,
    ) -> dict[str, Any]:
        limit = self._bounded_limit(limit)
        depth = self._bounded_depth(depth, default=1, maximum=4)
        layer_filter = layers or set()
        predicate_filter = predicates or set()
        packet = self._execute_philosophy_read(self._query_philosophy_neighborhood_tx, node_id, depth, limit)
        if not packet["node"]:
            raise Neo4jStoreError(f"unknown ToS philosophy node in neo4j projection: {node_id}")
        nodes, edges, _clusters = self._filter_query_surfaces(
            packet["nodes"],
            packet["edges"],
            [],
            layers=layer_filter,
            predicates=predicate_filter,
            limit=limit,
        )
        neighbors = [node for node in nodes if node.get("node_id") != node_id]
        return {
            "schema": "tos_graph_philosophy_neighborhood_v1",
            "query_backend": "neo4j",
            "fallback_reason": None,
            "node_id": node_id,
            "node": packet["node"],
            "neighbors": neighbors,
            "edges": edges,
            "depth": depth,
            "layers": sorted(layer_filter),
            "predicates": sorted(predicate_filter),
            "limit": limit,
            "source_refs": _source_refs([packet["node"]] + neighbors + edges),
            "runtime_projection_boundary": packet["runtime_projection_boundary"],
            "authority_note": "Tree-of-Sophia owns graph meaning; Neo4j serves a bounded abyss-stack neighborhood packet.",
        }

    @classmethod
    def _query_philosophy_neighborhood_tx(cls, tx: Any, node_id: str, depth: int, limit: int) -> dict[str, Any]:
        node = cls._payload_from_record(
            tx.run(
                """
                MATCH (node:TosPhilosophyNodeProjection {projection_id: $node_id})
                RETURN node.payload_json AS payload_json
                LIMIT 1
                """,
                node_id=node_id,
            ).single()
        )
        query = f"""
            MATCH (center:TosPhilosophyNodeProjection {{projection_id: $node_id}})
            OPTIONAL MATCH path=(center)-[:TOS_PHILOSOPHY_RELATION*1..{depth}]-(neighbor:TosPhilosophyNodeProjection)
            WITH collect(DISTINCT center.projection_id) + collect(DISTINCT neighbor.projection_id) AS node_ids
            UNWIND node_ids AS projection_id
            WITH DISTINCT projection_id WHERE projection_id IS NOT NULL
            MATCH (node:TosPhilosophyNodeProjection {{projection_id: projection_id}})
            RETURN node.payload_json AS payload_json
            LIMIT $limit
        """
        nodes = cls._payloads_from_result(tx.run(query, node_id=node_id, limit=limit))
        node_ids = sorted({str(item.get("node_id")) for item in nodes if isinstance(item.get("node_id"), str)})
        edges = cls._payloads_from_result(
            tx.run(
                """
                MATCH (edge:TosPhilosophyEdgeProjection)-[:FROM_NODE|TO_NODE]->(node:TosPhilosophyNodeProjection)
                WHERE node.projection_id IN $node_ids
                WITH edge, collect(DISTINCT node.projection_id) AS endpoint_ids
                WHERE size(endpoint_ids) = 2
                RETURN edge.payload_json AS payload_json
                LIMIT $limit
                """,
                node_ids=node_ids,
                limit=limit,
            )
        )
        return {
            "node": node,
            "nodes": nodes,
            "edges": edges,
            "runtime_projection_boundary": cls._runtime_boundary_from_tx(tx),
        }

    def query_philosophy_path(
        self,
        from_id: str,
        to_id: str,
        *,
        layers: set[str] | None = None,
        predicates: set[str] | None = None,
        max_depth: int = 6,
    ) -> dict[str, Any]:
        max_depth = self._bounded_depth(max_depth, default=6, maximum=8)
        layer_filter = layers or set()
        predicate_filter = predicates or set()
        packet = self._execute_philosophy_read(self._query_philosophy_path_tx, from_id, to_id, max_depth)
        nodes, edges, _clusters = self._filter_query_surfaces(
            packet["nodes"],
            packet["edges"],
            [],
            layers=layer_filter,
            predicates=predicate_filter,
            limit=2000,
        )
        found = bool(nodes) and (not predicate_filter or bool(edges))
        return {
            "schema": "tos_graph_philosophy_path_v1",
            "query_backend": "neo4j",
            "fallback_reason": None,
            "from_id": from_id,
            "to_id": to_id,
            "found": found,
            "nodes": nodes if found else [],
            "edges": edges if found else [],
            "max_depth": max_depth,
            "layers": sorted(layer_filter),
            "predicates": sorted(predicate_filter),
            "source_refs": _source_refs((nodes if found else []) + (edges if found else [])),
            "runtime_projection_boundary": packet["runtime_projection_boundary"],
            "authority_note": "Tree-of-Sophia owns graph meaning; Neo4j serves a bounded abyss-stack path packet.",
        }

    @classmethod
    def _query_philosophy_path_tx(cls, tx: Any, from_id: str, to_id: str, max_depth: int) -> dict[str, Any]:
        record = tx.run(
            f"""
            MATCH (source:TosPhilosophyNodeProjection {{projection_id: $from_id}})
            MATCH (target:TosPhilosophyNodeProjection {{projection_id: $to_id}})
            OPTIONAL MATCH path=shortestPath((source)-[:TOS_PHILOSOPHY_RELATION*..{max_depth}]-(target))
            RETURN
              CASE WHEN path IS NULL THEN [] ELSE [node IN nodes(path) | node.payload_json] END AS node_payload_jsons,
              CASE WHEN path IS NULL THEN [] ELSE [rel IN relationships(path) | rel.edge_id] END AS edge_ids
            LIMIT 1
            """,
            from_id=from_id,
            to_id=to_id,
        ).single()
        node_payloads = cls._record_value(record, "node_payload_jsons") or []
        nodes = []
        for raw in node_payloads:
            payload = _json_load(raw)
            if isinstance(payload, dict):
                nodes.append(payload)
        edge_ids = [str(edge_id) for edge_id in (cls._record_value(record, "edge_ids") or []) if edge_id]
        edges = cls._payloads_from_result(
            tx.run(
                """
                UNWIND $edge_ids AS edge_id
                MATCH (edge:TosPhilosophyEdgeProjection {projection_id: edge_id})
                RETURN edge.payload_json AS payload_json
                """,
                edge_ids=edge_ids,
            )
        )
        return {
            "nodes": nodes,
            "edges": edges,
            "runtime_projection_boundary": cls._runtime_boundary_from_tx(tx),
        }

    @staticmethod
    def _ensure_constraints(tx: Any, constraints: tuple[ConstraintSpec, ...]) -> int:
        for name, label, property_name in constraints:
            tx.run(
                f"""
                CREATE CONSTRAINT {name} IF NOT EXISTS
                FOR (node:{label})
                REQUIRE node.{property_name} IS UNIQUE
                """
            ).consume()
        return len(constraints)

    @classmethod
    def _ensure_corpus_constraints(cls, tx: Any) -> int:
        return cls._ensure_constraints(tx, CORPUS_CONSTRAINTS)

    @classmethod
    def _ensure_philosophy_constraints(cls, tx: Any) -> int:
        return cls._ensure_constraints(tx, PHILOSOPHY_CONSTRAINTS)

    @staticmethod
    def _corpus_rows(corpus: dict[str, Any], key: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in corpus.get(key, []):
            if isinstance(item, dict):
                if key == "relation_edges" and item.get("pack_id") and item.get("edge_id"):
                    projection_id = f"{item['pack_id']}::{item['edge_id']}"
                    rows.append({"id": projection_id, "props": item})
                    continue
                projection_id = (
                    item.get("node_id")
                    or item.get("path")
                    or item.get("pack_id")
                    or item.get("edge_id")
                    or item.get("id")
                    or item.get("view_id")
                )
                rows.append({"id": projection_id, "props": item})
        return rows

    def sync_corpus_projection(self, corpus: dict[str, Any]) -> dict[str, Any]:
        if not self.status.ready or not self.settings.neo4j_password:
            raise Neo4jStoreError(self.status.note)

        from neo4j import GraphDatabase

        counts = corpus.get("counts", {})
        projected_at = datetime.now(UTC).isoformat()
        corpus_props = {
            "owner_repo": corpus.get("owner_repo"),
            "schema_version": corpus.get("schema_version"),
            "surface_kind": corpus.get("surface_kind"),
            "schema_ref": corpus.get("schema_ref"),
            "projected_at": projected_at,
            "counts_json": _json_dump(counts),
            "authority_order_json": _json_dump(corpus.get("authority_order", [])),
            "runtime_projection_boundary_json": _json_dump(corpus.get("runtime_projection_boundary", {})),
        }
        branch_rows = self._corpus_rows(corpus, "branches")
        manifest_rows = self._corpus_rows(corpus, "manifests")
        node_rows = self._corpus_rows(corpus, "nodes")
        pack_rows = self._corpus_rows(corpus, "relation_packs")
        edge_rows = self._corpus_rows(corpus, "relation_edges")
        resource_rows = self._corpus_rows(corpus, "resources")
        view_rows = self._corpus_rows(corpus, "graph_views")

        driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )
        try:
            with driver.session(database=self.settings.neo4j_database) as session:
                constraint_count = session.execute_write(self._ensure_corpus_constraints)
                deleted_counts = session.execute_write(
                    self._replace_corpus_projection,
                    corpus_props,
                    branch_rows,
                    manifest_rows,
                    node_rows,
                    pack_rows,
                    edge_rows,
                    resource_rows,
                    view_rows,
                )
        except Exception as exc:  # pragma: no cover - runtime integration path
            raise Neo4jStoreError(f"neo4j corpus sync failed: {exc}") from exc
        finally:
            driver.close()

        return {
            "surface": "ToS/derived-exports/tos_corpus_index.min.json",
            "status": "corpus_synced",
            "node_count": int(counts.get("nodes") or len(node_rows)),
            "edge_count": int(counts.get("relation_edges") or len(edge_rows)),
            "resource_count": int(counts.get("resources") or len(resource_rows)),
            "branch_count": int(counts.get("branches") or len(branch_rows)),
            "projection_target": "neo4j_corpus_projection",
            "note": f"whole-corpus projection synced into neo4j database '{self.settings.neo4j_database}' while Tree of Sophia remained canonical",
            "deleted_node_count": deleted_counts["deleted_node_count"],
            "deleted_edge_count": deleted_counts["deleted_edge_count"],
            "constraint_count": constraint_count,
        }

    @staticmethod
    def _safe_philosophy_props(item: dict[str, Any], id_key: str) -> dict[str, Any]:
        props: dict[str, Any] = {
            "projection_id": item.get(id_key),
            "payload_json": _json_dump(item),
        }
        for key in (
            id_key,
            "label",
            "title",
            "node_type",
            "cluster_kind",
            "member_key",
            "member_value",
            "packet_id",
            "view_id",
            "predicate_id",
            "from_id",
            "to_id",
            "source_ref",
            "route_card",
            "layout_hint",
            "use",
        ):
            if isinstance(item.get(key), (str, int, float, bool)):
                props[key] = item[key]
        if "graph_layers" in item:
            props["graph_layers_json"] = _list_dump(item.get("graph_layers"))
        if "view_ids" in item:
            props["view_ids_json"] = _list_dump(item.get("view_ids"))
        return props

    @classmethod
    def _philosophy_rows(cls, projection: dict[str, Any], key: str, id_key: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in projection.get(key, []):
            if not isinstance(item, dict) or not item.get(id_key):
                continue
            rows.append(
                {
                    "id": item[id_key],
                    "props": cls._safe_philosophy_props(item, id_key),
                    "source_ref": item.get("source_ref"),
                    "source_refs": item.get("source_refs", []),
                    "graph_layers": item.get("graph_layers", []),
                    "view_ids": item.get("view_ids", []),
                    "member_node_ids": item.get("member_node_ids", []),
                    "member_edge_ids": item.get("member_edge_ids", []),
                    "view_id": item.get("view_id"),
                    "from_id": item.get("from_id"),
                    "to_id": item.get("to_id"),
                    "predicate_id": item.get("predicate_id"),
                }
            )
        return rows

    @staticmethod
    def _philosophy_source_rows(projection: dict[str, Any]) -> list[dict[str, Any]]:
        refs: set[str] = set()
        for collection_name in ("views", "nodes", "edges", "clusters", "review_packets", "graph_layers"):
            for item in projection.get(collection_name, []):
                if isinstance(item, dict) and isinstance(item.get("source_ref"), str):
                    refs.add(item["source_ref"])
                if isinstance(item, dict) and isinstance(item.get("source_refs"), list):
                    refs.update(str(ref) for ref in item["source_refs"] if isinstance(ref, str))
        source_refs = projection.get("source_refs", {})
        if isinstance(source_refs, dict):
            refs.update(str(value) for value in source_refs.values() if isinstance(value, str))
        return [{"id": ref, "props": {"projection_id": ref, "source_ref": ref}} for ref in sorted(refs)]

    def sync_philosophy_projection(self, projection: dict[str, Any]) -> dict[str, Any]:
        if not self.status.ready or not self.settings.neo4j_password:
            raise Neo4jStoreError(self.status.note)

        from neo4j import GraphDatabase

        counts = projection.get("counts", {})
        projected_at = datetime.now(UTC).isoformat()
        refresh_id = f"tos-philosophy:{projected_at}"
        projection_props = {
            "owner_repo": projection.get("owner_repo"),
            "schema_version": projection.get("schema_version"),
            "surface_kind": projection.get("surface_kind"),
            "schema_ref": projection.get("schema_ref"),
            "projected_at": projected_at,
            "refresh_id": refresh_id,
            "counts_json": _json_dump(counts),
            "source_refs_json": _json_dump(projection.get("source_refs", {})),
            "snapshot_review_json": _json_dump(projection.get("snapshot_review", {})),
            "runtime_projection_boundary_json": _json_dump(projection.get("runtime_projection_boundary", {})),
        }
        view_rows = self._philosophy_rows(projection, "views", "view_id")
        node_rows = self._philosophy_rows(projection, "nodes", "node_id")
        edge_rows = self._philosophy_rows(projection, "edges", "edge_id")
        layer_rows = self._philosophy_rows(projection, "graph_layers", "layer_id")
        cluster_rows = self._philosophy_rows(projection, "clusters", "cluster_id")
        review_packet_rows = self._philosophy_rows(projection, "review_packets", "packet_id")
        source_rows = self._philosophy_source_rows(projection)

        driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )
        try:
            with driver.session(database=self.settings.neo4j_database) as session:
                constraint_count = session.execute_write(self._ensure_philosophy_constraints)
                session.execute_write(self._merge_philosophy_projection, projection_props)
                for label, rel_type, rows in (
                    ("TosPhilosophyViewProjection", "PROJECTS_VIEW", view_rows),
                    ("TosPhilosophyNodeProjection", "PROJECTS_NODE", node_rows),
                    ("TosPhilosophyEdgeProjection", "PROJECTS_EDGE", edge_rows),
                    ("TosPhilosophyLayerProjection", "PROJECTS_LAYER", layer_rows),
                    ("TosPhilosophyClusterProjection", "PROJECTS_CLUSTER", cluster_rows),
                    ("TosPhilosophyReviewPacketProjection", "PROJECTS_REVIEW_PACKET", review_packet_rows),
                    ("TosPhilosophySourceRefProjection", "PROJECTS_SOURCE_REF", source_rows),
                ):
                    for chunk in _chunks(rows):
                        session.execute_write(self._merge_philosophy_rows, label, rel_type, chunk, refresh_id)
                for chunk in _chunks(node_rows):
                    session.execute_write(self._link_philosophy_view_nodes, chunk, refresh_id)
                for chunk in _chunks(edge_rows):
                    session.execute_write(self._link_philosophy_view_edges, chunk, refresh_id)
                for label, rows in (
                    ("TosPhilosophyViewProjection", view_rows),
                    ("TosPhilosophyNodeProjection", node_rows),
                    ("TosPhilosophyEdgeProjection", edge_rows),
                    ("TosPhilosophyClusterProjection", cluster_rows),
                ):
                    for chunk in _chunks(rows):
                        session.execute_write(self._link_philosophy_layer_memberships, label, chunk, refresh_id)
                        session.execute_write(self._link_philosophy_source_refs, label, chunk, refresh_id)
                for chunk in _chunks(review_packet_rows):
                    session.execute_write(self._link_philosophy_review_packets, chunk, refresh_id)
                    session.execute_write(
                        self._link_philosophy_source_refs,
                        "TosPhilosophyReviewPacketProjection",
                        chunk,
                        refresh_id,
                    )
                for chunk in _chunks(layer_rows):
                    session.execute_write(
                        self._link_philosophy_source_refs,
                        "TosPhilosophyLayerProjection",
                        chunk,
                        refresh_id,
                    )
                for chunk in _chunks(cluster_rows):
                    session.execute_write(self._link_philosophy_cluster_members, chunk, refresh_id)
                for chunk in _chunks(edge_rows):
                    session.execute_write(self._link_philosophy_edges, chunk, refresh_id)
                deleted_counts = session.execute_write(
                    self._delete_stale_philosophy_projection,
                    refresh_id,
                )
        except Exception as exc:  # pragma: no cover - runtime integration path
            raise Neo4jStoreError(f"neo4j philosophy sync failed: {exc}") from exc
        finally:
            driver.close()

        return {
            "surface": "ToS/derived-exports/philosophy_graph_projection.min.json",
            "status": "philosophy_synced",
            "node_count": int(counts.get("nodes") or len(node_rows)),
            "edge_count": int(counts.get("edges") or len(edge_rows)),
            "resource_count": int(counts.get("source_refs") or len(source_rows)),
            "branch_count": int(counts.get("views") or len(view_rows)),
            "projection_target": "neo4j_philosophy_projection",
            "note": f"philosophy projection synced into neo4j database '{self.settings.neo4j_database}' while Tree of Sophia remained canonical",
            "deleted_node_count": deleted_counts["deleted_node_count"],
            "deleted_edge_count": deleted_counts["deleted_edge_count"],
            "constraint_count": constraint_count,
        }

    @staticmethod
    def _replace_corpus_projection(
        tx: Any,
        corpus_props: dict[str, Any],
        branch_rows: list[dict[str, Any]],
        manifest_rows: list[dict[str, Any]],
        node_rows: list[dict[str, Any]],
        pack_rows: list[dict[str, Any]],
        edge_rows: list[dict[str, Any]],
        resource_rows: list[dict[str, Any]],
        view_rows: list[dict[str, Any]],
    ) -> dict[str, int]:
        deleted_counts = Neo4jProjectionStore._delete_corpus_projection(tx)
        Neo4jProjectionStore._merge_corpus_projection(tx, corpus_props)
        for label, rel_type, rows in (
            ("TosCorpusBranchProjection", "PROJECTS_BRANCH", branch_rows),
            ("TosCorpusManifestProjection", "PROJECTS_MANIFEST", manifest_rows),
            ("TosCorpusNodeProjection", "PROJECTS_NODE", node_rows),
            ("TosCorpusRelationPackProjection", "PROJECTS_RELATION_PACK", pack_rows),
            ("TosCorpusRelationEdgeProjection", "PROJECTS_RELATION_EDGE", edge_rows),
            ("TosCorpusResourceProjection", "PROJECTS_RESOURCE", resource_rows),
            ("TosCorpusGraphViewProjection", "PROJECTS_GRAPH_VIEW", view_rows),
        ):
            if rows:
                Neo4jProjectionStore._merge_corpus_rows(tx, label, rel_type, rows)
        if edge_rows and node_rows:
            Neo4jProjectionStore._link_corpus_relation_edges(tx, edge_rows)
        return deleted_counts

    @staticmethod
    def _delete_corpus_projection(tx: Any) -> dict[str, int]:
        record = tx.run(
            """
            MATCH (node)
            WHERE node:TosCorpusBranchProjection
               OR node:TosCorpusManifestProjection
               OR node:TosCorpusNodeProjection
               OR node:TosCorpusRelationPackProjection
               OR node:TosCorpusRelationEdgeProjection
               OR node:TosCorpusResourceProjection
               OR node:TosCorpusGraphViewProjection
               OR node:TosCorpusProjection
            WITH collect(node) AS nodes
            RETURN size(nodes) AS deleted_node_count
            """
        ).single()
        tx.run(
            """
            MATCH (node)
            WHERE node:TosCorpusBranchProjection
               OR node:TosCorpusManifestProjection
               OR node:TosCorpusNodeProjection
               OR node:TosCorpusRelationPackProjection
               OR node:TosCorpusRelationEdgeProjection
               OR node:TosCorpusResourceProjection
               OR node:TosCorpusGraphViewProjection
               OR node:TosCorpusProjection
            DETACH DELETE node
            """
        ).consume()
        return {
            "deleted_node_count": int(record["deleted_node_count"]) if record else 0,
            "deleted_edge_count": 0,
        }

    @staticmethod
    def _merge_corpus_projection(tx: Any, corpus_props: dict[str, Any]) -> None:
        tx.run(
            """
            MERGE (corpus:TosCorpusProjection {owner_repo: $owner_repo})
            SET corpus += $props
            """,
            owner_repo=corpus_props.get("owner_repo") or "Tree-of-Sophia",
            props=corpus_props,
        ).consume()

    @staticmethod
    def _merge_corpus_rows(tx: Any, label: str, rel_type: str, rows: list[dict[str, Any]]) -> None:
        query = f"""
        UNWIND $rows AS row
        MATCH (corpus:TosCorpusProjection {{owner_repo: 'Tree-of-Sophia'}})
        MERGE (projection:{label} {{projection_id: row.id}})
        SET projection += row.props
        MERGE (corpus)-[:{rel_type}]->(projection)
        """
        tx.run(query, rows=rows).consume()

    @staticmethod
    def _link_corpus_relation_edges(tx: Any, edge_rows: list[dict[str, Any]]) -> None:
        tx.run(
            """
            UNWIND $edge_rows AS edge
            MATCH (projection:TosCorpusRelationEdgeProjection {projection_id: edge.id})
            OPTIONAL MATCH (source:TosCorpusNodeProjection {node_id: edge.props.from_id})
            OPTIONAL MATCH (target:TosCorpusNodeProjection {node_id: edge.props.to_id})
            FOREACH (_ IN CASE WHEN source IS NULL THEN [] ELSE [1] END |
              MERGE (projection)-[:FROM_NODE]->(source)
            )
            FOREACH (_ IN CASE WHEN target IS NULL THEN [] ELSE [1] END |
              MERGE (projection)-[:TO_NODE]->(target)
            )
            FOREACH (_ IN CASE WHEN source IS NULL OR target IS NULL THEN [] ELSE [1] END |
              MERGE (source)-[rel:TOS_CORPUS_RELATION {edge_id: edge.props.edge_id, pack_id: edge.props.pack_id}]->(target)
              SET rel.predicate_id = edge.props.predicate_id,
                  rel.authority_layer = edge.props.authority_layer,
                  rel.owner_branch = edge.props.owner_branch,
                  rel.status = edge.props.status
            )
            """,
            edge_rows=edge_rows,
        ).consume()

    @staticmethod
    def _delete_stale_philosophy_projection(tx: Any, refresh_id: str) -> dict[str, int]:
        record = tx.run(
            """
            MATCH ()-[rel]-()
            WHERE type(rel) IN $relation_types
              AND coalesce(rel.refresh_id, '') <> $refresh_id
            WITH collect(DISTINCT rel) AS rels
            FOREACH (rel IN rels | DELETE rel)
            WITH size(rels) AS deleted_edge_count
            MATCH (node)
            WHERE (
                node:TosPhilosophyProjection
                OR node:TosPhilosophyViewProjection
                OR node:TosPhilosophyNodeProjection
                OR node:TosPhilosophyEdgeProjection
                OR node:TosPhilosophySourceRefProjection
                OR node:TosPhilosophyLayerProjection
                OR node:TosPhilosophyClusterProjection
                OR node:TosPhilosophyReviewPacketProjection
            )
              AND coalesce(node.refresh_id, '') <> $refresh_id
            WITH deleted_edge_count, collect(node) AS nodes
            FOREACH (node IN nodes | DETACH DELETE node)
            RETURN size(nodes) AS deleted_node_count, deleted_edge_count AS deleted_edge_count
            """,
            refresh_id=refresh_id,
            relation_types=PHILOSOPHY_RELATION_TYPES,
        ).single()
        return {
            "deleted_node_count": int(record["deleted_node_count"]) if record else 0,
            "deleted_edge_count": int(record["deleted_edge_count"]) if record else 0,
        }

    @staticmethod
    def _merge_philosophy_projection(tx: Any, projection_props: dict[str, Any]) -> None:
        tx.run(
            """
            MERGE (projection:TosPhilosophyProjection {owner_repo: $owner_repo})
            SET projection += $props
            """,
            owner_repo=projection_props.get("owner_repo") or "Tree-of-Sophia",
            props=projection_props,
        ).consume()

    @staticmethod
    def _merge_philosophy_rows(
        tx: Any,
        label: str,
        rel_type: str,
        rows: list[dict[str, Any]],
        refresh_id: str,
    ) -> None:
        query = f"""
        UNWIND $rows AS row
        MATCH (root:TosPhilosophyProjection {{owner_repo: 'Tree-of-Sophia'}})
        MERGE (projection:{label} {{projection_id: row.id}})
        SET projection += row.props
        SET projection.refresh_id = $refresh_id
        MERGE (root)-[rel:{rel_type}]->(projection)
        SET rel.refresh_id = $refresh_id
        """
        tx.run(query, rows=rows, refresh_id=refresh_id).consume()

    @staticmethod
    def _link_philosophy_view_nodes(
        tx: Any,
        node_rows: list[dict[str, Any]],
        refresh_id: str,
    ) -> None:
        tx.run(
            """
            UNWIND $node_rows AS row
            UNWIND row.view_ids AS view_id
            MATCH (view:TosPhilosophyViewProjection {projection_id: view_id})
            MATCH (node:TosPhilosophyNodeProjection {projection_id: row.id})
            MERGE (view)-[projects:PROJECTS_NODE]->(node)
            SET projects.refresh_id = $refresh_id
            MERGE (node)-[in_view:IN_VIEW]->(view)
            SET in_view.refresh_id = $refresh_id
            """,
            node_rows=node_rows,
            refresh_id=refresh_id,
        ).consume()

    @staticmethod
    def _link_philosophy_view_edges(
        tx: Any,
        edge_rows: list[dict[str, Any]],
        refresh_id: str,
    ) -> None:
        tx.run(
            """
            UNWIND $edge_rows AS row
            UNWIND row.view_ids AS view_id
            MATCH (view:TosPhilosophyViewProjection {projection_id: view_id})
            MATCH (edge:TosPhilosophyEdgeProjection {projection_id: row.id})
            MERGE (view)-[projects:PROJECTS_EDGE]->(edge)
            SET projects.refresh_id = $refresh_id
            MERGE (edge)-[in_view:IN_VIEW]->(view)
            SET in_view.refresh_id = $refresh_id
            """,
            edge_rows=edge_rows,
            refresh_id=refresh_id,
        ).consume()

    @staticmethod
    def _link_philosophy_layer_memberships(
        tx: Any,
        label: str,
        rows: list[dict[str, Any]],
        refresh_id: str,
    ) -> None:
        query = f"""
        UNWIND $rows AS row
        UNWIND row.graph_layers AS layer_id
        MATCH (projection:{label} {{projection_id: row.id}})
        MATCH (layer:TosPhilosophyLayerProjection {{projection_id: layer_id}})
        MERGE (projection)-[rel:IN_LAYER]->(layer)
        SET rel.refresh_id = $refresh_id
        """
        tx.run(query, rows=rows, refresh_id=refresh_id).consume()

    @staticmethod
    def _link_philosophy_source_refs(
        tx: Any,
        label: str,
        rows: list[dict[str, Any]],
        refresh_id: str,
    ) -> None:
        query = f"""
        UNWIND $rows AS row
        WITH row, CASE
          WHEN row.source_ref IS NULL THEN row.source_refs
          ELSE row.source_refs + [row.source_ref]
        END AS refs
        UNWIND refs AS source_ref
        WITH row, source_ref WHERE source_ref IS NOT NULL
        MATCH (projection:{label} {{projection_id: row.id}})
        MERGE (source:TosPhilosophySourceRefProjection {{projection_id: source_ref}})
        SET source.source_ref = source_ref
        SET source.refresh_id = $refresh_id
        MERGE (projection)-[rel:HAS_SOURCE_REF]->(source)
        SET rel.refresh_id = $refresh_id
        """
        tx.run(query, rows=rows, refresh_id=refresh_id).consume()

    @staticmethod
    def _link_philosophy_cluster_members(tx: Any, cluster_rows: list[dict[str, Any]], refresh_id: str) -> None:
        tx.run(
            """
            UNWIND $cluster_rows AS row
            MATCH (cluster:TosPhilosophyClusterProjection {projection_id: row.id})
            UNWIND row.member_node_ids AS node_id
            MATCH (node:TosPhilosophyNodeProjection {projection_id: node_id})
            MERGE (cluster)-[rel:CLUSTERS_NODE]->(node)
            SET rel.refresh_id = $refresh_id
            """,
            cluster_rows=cluster_rows,
            refresh_id=refresh_id,
        ).consume()
        tx.run(
            """
            UNWIND $cluster_rows AS row
            MATCH (cluster:TosPhilosophyClusterProjection {projection_id: row.id})
            UNWIND row.member_edge_ids AS edge_id
            MATCH (edge:TosPhilosophyEdgeProjection {projection_id: edge_id})
            MERGE (cluster)-[rel:CLUSTERS_EDGE]->(edge)
            SET rel.refresh_id = $refresh_id
            """,
            cluster_rows=cluster_rows,
            refresh_id=refresh_id,
        ).consume()
        tx.run(
            """
            UNWIND $cluster_rows AS row
            MATCH (cluster:TosPhilosophyClusterProjection {projection_id: row.id})
            UNWIND row.view_ids AS view_id
            MATCH (view:TosPhilosophyViewProjection {projection_id: view_id})
            MERGE (view)-[projects:PROJECTS_CLUSTER]->(cluster)
            SET projects.refresh_id = $refresh_id
            MERGE (cluster)-[in_view:IN_VIEW]->(view)
            SET in_view.refresh_id = $refresh_id
            """,
            cluster_rows=cluster_rows,
            refresh_id=refresh_id,
        ).consume()

    @staticmethod
    def _link_philosophy_review_packets(
        tx: Any,
        review_packet_rows: list[dict[str, Any]],
        refresh_id: str,
    ) -> None:
        tx.run(
            """
            UNWIND $review_packet_rows AS row
            MATCH (packet:TosPhilosophyReviewPacketProjection {projection_id: row.id})
            MATCH (view:TosPhilosophyViewProjection {projection_id: row.view_id})
            MERGE (view)-[has_packet:HAS_REVIEW_PACKET]->(packet)
            SET has_packet.refresh_id = $refresh_id
            MERGE (packet)-[reviews:REVIEWS_VIEW]->(view)
            SET reviews.refresh_id = $refresh_id
            """,
            review_packet_rows=review_packet_rows,
            refresh_id=refresh_id,
        ).consume()

    @staticmethod
    def _link_philosophy_edges(tx: Any, edge_rows: list[dict[str, Any]], refresh_id: str) -> None:
        tx.run(
            """
            UNWIND $edge_rows AS edge
            MATCH (projection:TosPhilosophyEdgeProjection {projection_id: edge.id})
            OPTIONAL MATCH (source:TosPhilosophyNodeProjection {projection_id: edge.from_id})
            OPTIONAL MATCH (target:TosPhilosophyNodeProjection {projection_id: edge.to_id})
            FOREACH (_ IN CASE WHEN source IS NULL THEN [] ELSE [1] END |
              MERGE (projection)-[from_rel:FROM_NODE]->(source)
              SET from_rel.refresh_id = $refresh_id
            )
            FOREACH (_ IN CASE WHEN target IS NULL THEN [] ELSE [1] END |
              MERGE (projection)-[to_rel:TO_NODE]->(target)
              SET to_rel.refresh_id = $refresh_id
            )
            FOREACH (_ IN CASE WHEN source IS NULL OR target IS NULL THEN [] ELSE [1] END |
              MERGE (source)-[rel:TOS_PHILOSOPHY_RELATION {edge_id: edge.id}]->(target)
              SET rel.predicate_id = edge.predicate_id,
                  rel.source_ref = edge.source_ref,
                  rel.refresh_id = $refresh_id
            )
            """,
            edge_rows=edge_rows,
            refresh_id=refresh_id,
        ).consume()
