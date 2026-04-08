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
            note="neo4j route sync is unavailable because TOS_GRAPH_NEO4J_URI is missing; sync requests fall back to preview counts",
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
            note="neo4j route sync is configured but credentials are incomplete; sync requests fall back to preview counts",
        )

    return Neo4jStoreStatus(
        configured=True,
        ready=True,
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        database=settings.neo4j_database,
        projection_mode=settings.projection_mode,
        note="neo4j route-scoped projection sync is ready; Tree of Sophia remains canonical and Neo4j remains projection-only",
    )


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


class Neo4jProjectionStore:
    def __init__(self, settings: TosGraphSettings, status: Neo4jStoreStatus) -> None:
        self.settings = settings
        self.status = status

    def _node_rows(self, graph: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for node in graph.get("nodes", []):
            rows.append(
                {
                    "node_id": node.get("node_id"),
                    "props": {
                        "route_path": graph["route"],
                        "node_id": node.get("node_id"),
                        "node_type": node.get("node_type") or "unknown",
                        "canonical_label": node.get("canonical_label"),
                        "source_anchor": node.get("source_anchor"),
                        "distilled_thesis": node.get("distilled_thesis"),
                        "source_file_path": node.get("source_file_path"),
                        "source_file_sha256": node.get("source_file_sha256"),
                        "key_terms_json": _json_dump(node.get("key_terms", [])),
                        "interpretation_layers_json": _json_dump(node.get("interpretation_layers", [])),
                        "relations_json": _json_dump(node.get("relations", [])),
                        "language_witnesses_json": _json_dump(node.get("language_witnesses", [])),
                        "translation_tensions_json": _json_dump(node.get("translation_tensions", [])),
                        "raw_payload_json": _json_dump(node.get("raw_payload", {})),
                    },
                }
            )
        return rows

    def _edge_rows(self, graph: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for edge in graph.get("edges", []):
            rows.append(
                {
                    "edge_id": edge.get("edge_id"),
                    "from_id": edge.get("from_id"),
                    "to_id": edge.get("to_id"),
                    "props": {
                        "route_path": graph["route"],
                        "edge_id": edge.get("edge_id"),
                        "edge_kind": edge.get("edge_kind"),
                        "from_id": edge.get("from_id"),
                        "predicate_id": edge.get("predicate_id"),
                        "to_id": edge.get("to_id"),
                        "layer": edge.get("layer"),
                        "anchor_mode": edge.get("anchor_mode"),
                        "anchor_start_secondary": edge.get("anchor_start_secondary"),
                        "anchor_end_secondary": edge.get("anchor_end_secondary"),
                        "anchor_segment_ids": edge.get("anchor_segment_ids"),
                        "witness_scope": edge.get("witness_scope"),
                        "connectivity_role": edge.get("connectivity_role"),
                        "confidence": edge.get("confidence"),
                        "note": edge.get("note"),
                        "source_file_path": edge.get("source_file_path"),
                        "source_file_sha256": edge.get("source_file_sha256"),
                    },
                    "rel_props": {
                        "route_path": graph["route"],
                        "edge_id": edge.get("edge_id"),
                        "predicate_id": edge.get("predicate_id"),
                        "edge_kind": edge.get("edge_kind"),
                        "layer": edge.get("layer"),
                        "anchor_mode": edge.get("anchor_mode"),
                        "witness_scope": edge.get("witness_scope"),
                        "connectivity_role": edge.get("connectivity_role"),
                        "confidence": edge.get("confidence"),
                        "note": edge.get("note"),
                    },
                }
            )
        return rows

    def sync_route_projection(self, graph: dict[str, Any], route_label: str) -> dict[str, Any]:
        if not self.status.ready or not self.settings.neo4j_password:
            raise Neo4jStoreError(self.status.note)

        from neo4j import GraphDatabase

        route = graph["route"]
        source_node = graph.get("source_node") or {}
        diagnostics = graph.get("diagnostics", {})
        projected_at = datetime.now(UTC).isoformat()
        route_props = {
            "route": route,
            "label": route_label,
            "projection_mode": self.status.projection_mode,
            "source_node_id": source_node.get("node_id"),
            "source_canonical_label": source_node.get("canonical_label"),
            "node_count": len(graph.get("nodes", [])),
            "edge_count": len(graph.get("edges", [])),
            "missing_nodes_json": _json_dump(diagnostics.get("missing_nodes", [])),
            "edge_file": diagnostics.get("edge_file"),
            "edge_file_sha256": diagnostics.get("edge_file_sha256"),
            "projected_at": projected_at,
        }
        node_rows = self._node_rows(graph)
        edge_rows = self._edge_rows(graph)

        driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )
        try:
            with driver.session(database=self.settings.neo4j_database) as session:
                deleted_counts = session.execute_write(self._delete_route_projection, route)
                session.execute_write(self._merge_route, route, route_props)
                if node_rows:
                    session.execute_write(self._merge_nodes, route, node_rows)
                if edge_rows:
                    session.execute_write(self._merge_edges, route, edge_rows)
        except Exception as exc:  # pragma: no cover - runtime integration path
            raise Neo4jStoreError(f"neo4j route sync failed for {route}: {exc}") from exc
        finally:
            driver.close()

        return {
            "route": route,
            "status": "route_synced",
            "node_count": len(node_rows),
            "edge_count": len(edge_rows),
            "projection_target": "neo4j_route_projection",
            "note": f"route-scoped projection synced into neo4j database '{self.settings.neo4j_database}' while ToS canon remained read-only",
            "deleted_node_count": deleted_counts["deleted_node_count"],
            "deleted_edge_count": deleted_counts["deleted_edge_count"],
        }

    @staticmethod
    def _delete_route_projection(tx: Any, route: str) -> dict[str, int]:
        record = tx.run(
            """
            MATCH (route:TosRouteProjection {route: $route})
            OPTIONAL MATCH (route)-[:PROJECTS_NODE]->(node:TosNodeProjection)
            WITH route, count(node) AS deleted_node_count
            OPTIONAL MATCH (route)-[:PROJECTS_EDGE]->(edge:TosEdgeProjection)
            RETURN deleted_node_count, count(edge) AS deleted_edge_count
            """,
            route=route,
        ).single()

        tx.run(
            """
            MATCH (route:TosRouteProjection {route: $route})
            OPTIONAL MATCH (route)-[:PROJECTS_EDGE]->(edge:TosEdgeProjection)
            DETACH DELETE edge
            """,
            route=route,
        ).consume()
        tx.run(
            """
            MATCH (route:TosRouteProjection {route: $route})
            OPTIONAL MATCH (route)-[:PROJECTS_NODE]->(node:TosNodeProjection)
            DETACH DELETE node
            """,
            route=route,
        ).consume()

        return {
            "deleted_node_count": int(record["deleted_node_count"]) if record else 0,
            "deleted_edge_count": int(record["deleted_edge_count"]) if record else 0,
        }

    @staticmethod
    def _merge_route(tx: Any, route: str, route_props: dict[str, Any]) -> None:
        tx.run(
            """
            MERGE (route:TosRouteProjection {route: $route})
            SET route += $route_props
            """,
            route=route,
            route_props=route_props,
        ).consume()

    @staticmethod
    def _merge_nodes(tx: Any, route: str, node_rows: list[dict[str, Any]]) -> None:
        tx.run(
            """
            UNWIND $node_rows AS node
            MATCH (route:TosRouteProjection {route: $route})
            MERGE (projection:TosNodeProjection {route_path: $route, node_id: node.node_id})
            SET projection += node.props
            MERGE (route)-[:PROJECTS_NODE]->(projection)
            FOREACH (_ IN CASE WHEN route.source_node_id = node.node_id THEN [1] ELSE [] END |
              MERGE (route)-[:SOURCE_NODE]->(projection)
            )
            """,
            route=route,
            node_rows=node_rows,
        ).consume()

    @staticmethod
    def _merge_edges(tx: Any, route: str, edge_rows: list[dict[str, Any]]) -> None:
        tx.run(
            """
            UNWIND $edge_rows AS edge
            MATCH (route:TosRouteProjection {route: $route})
            MERGE (projection:TosEdgeProjection {route_path: $route, edge_id: edge.edge_id})
            SET projection += edge.props
            MERGE (route)-[:PROJECTS_EDGE]->(projection)
            WITH route, projection, edge
            OPTIONAL MATCH (source:TosNodeProjection {route_path: $route, node_id: edge.from_id})
            OPTIONAL MATCH (target:TosNodeProjection {route_path: $route, node_id: edge.to_id})
            FOREACH (_ IN CASE WHEN source IS NULL OR target IS NULL THEN [] ELSE [1] END |
              MERGE (source)-[rel:TOS_RELATION {route_path: $route, edge_id: edge.edge_id}]->(target)
              SET rel += edge.rel_props
            )
            FOREACH (_ IN CASE WHEN source IS NULL THEN [] ELSE [1] END |
              MERGE (projection)-[:FROM_NODE]->(source)
            )
            FOREACH (_ IN CASE WHEN target IS NULL THEN [] ELSE [1] END |
              MERGE (projection)-[:TO_NODE]->(target)
            )
            """,
            route=route,
            edge_rows=edge_rows,
        ).consume()
