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


class Neo4jProjectionStore:
    def __init__(self, settings: TosGraphSettings, status: Neo4jStoreStatus) -> None:
        self.settings = settings
        self.status = status

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
                deleted_counts = session.execute_write(self._delete_corpus_projection)
                session.execute_write(self._merge_corpus_projection, corpus_props)
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
                        session.execute_write(self._merge_corpus_rows, label, rel_type, rows)
                if edge_rows and node_rows:
                    session.execute_write(self._link_corpus_relation_edges, edge_rows)
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
        projection_props = {
            "owner_repo": projection.get("owner_repo"),
            "schema_version": projection.get("schema_version"),
            "surface_kind": projection.get("surface_kind"),
            "schema_ref": projection.get("schema_ref"),
            "projected_at": projected_at,
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
                deleted_counts = session.execute_write(self._delete_philosophy_projection)
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
                    if rows:
                        session.execute_write(self._merge_philosophy_rows, label, rel_type, rows)
                session.execute_write(self._link_philosophy_view_memberships, node_rows, edge_rows)
                for label, rows in (
                    ("TosPhilosophyViewProjection", view_rows),
                    ("TosPhilosophyNodeProjection", node_rows),
                    ("TosPhilosophyEdgeProjection", edge_rows),
                    ("TosPhilosophyClusterProjection", cluster_rows),
                ):
                    if rows:
                        session.execute_write(self._link_philosophy_layer_memberships, label, rows)
                        session.execute_write(self._link_philosophy_source_refs, label, rows)
                if review_packet_rows:
                    session.execute_write(self._link_philosophy_review_packets, review_packet_rows)
                    session.execute_write(
                        self._link_philosophy_source_refs,
                        "TosPhilosophyReviewPacketProjection",
                        review_packet_rows,
                    )
                if layer_rows:
                    session.execute_write(self._link_philosophy_source_refs, "TosPhilosophyLayerProjection", layer_rows)
                if cluster_rows:
                    session.execute_write(self._link_philosophy_cluster_members, cluster_rows)
                if edge_rows:
                    session.execute_write(self._link_philosophy_edges, edge_rows)
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
        }

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
    def _delete_philosophy_projection(tx: Any) -> dict[str, int]:
        record = tx.run(
            """
            MATCH (node)
            WHERE node:TosPhilosophyProjection
               OR node:TosPhilosophyViewProjection
               OR node:TosPhilosophyNodeProjection
               OR node:TosPhilosophyEdgeProjection
               OR node:TosPhilosophySourceRefProjection
               OR node:TosPhilosophyLayerProjection
               OR node:TosPhilosophyClusterProjection
               OR node:TosPhilosophyReviewPacketProjection
            WITH collect(node) AS nodes
            OPTIONAL MATCH (a)-[rel]-(b)
            WHERE a IN nodes OR b IN nodes
            RETURN size(nodes) AS deleted_node_count, count(DISTINCT rel) AS deleted_edge_count
            """
        ).single()
        tx.run(
            """
            MATCH (node)
            WHERE node:TosPhilosophyProjection
               OR node:TosPhilosophyViewProjection
               OR node:TosPhilosophyNodeProjection
               OR node:TosPhilosophyEdgeProjection
               OR node:TosPhilosophySourceRefProjection
               OR node:TosPhilosophyLayerProjection
               OR node:TosPhilosophyClusterProjection
               OR node:TosPhilosophyReviewPacketProjection
            DETACH DELETE node
            """
        ).consume()
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
    def _merge_philosophy_rows(tx: Any, label: str, rel_type: str, rows: list[dict[str, Any]]) -> None:
        query = f"""
        UNWIND $rows AS row
        MATCH (root:TosPhilosophyProjection {{owner_repo: 'Tree-of-Sophia'}})
        MERGE (projection:{label} {{projection_id: row.id}})
        SET projection += row.props
        MERGE (root)-[:{rel_type}]->(projection)
        """
        tx.run(query, rows=rows).consume()

    @staticmethod
    def _link_philosophy_view_memberships(
        tx: Any,
        node_rows: list[dict[str, Any]],
        edge_rows: list[dict[str, Any]],
    ) -> None:
        tx.run(
            """
            UNWIND $node_rows AS row
            UNWIND row.view_ids AS view_id
            MATCH (view:TosPhilosophyViewProjection {projection_id: view_id})
            MATCH (node:TosPhilosophyNodeProjection {projection_id: row.id})
            MERGE (view)-[:PROJECTS_NODE]->(node)
            MERGE (node)-[:IN_VIEW]->(view)
            """,
            node_rows=node_rows,
        ).consume()
        tx.run(
            """
            UNWIND $edge_rows AS row
            UNWIND row.view_ids AS view_id
            MATCH (view:TosPhilosophyViewProjection {projection_id: view_id})
            MATCH (edge:TosPhilosophyEdgeProjection {projection_id: row.id})
            MERGE (view)-[:PROJECTS_EDGE]->(edge)
            MERGE (edge)-[:IN_VIEW]->(view)
            """,
            edge_rows=edge_rows,
        ).consume()

    @staticmethod
    def _link_philosophy_layer_memberships(tx: Any, label: str, rows: list[dict[str, Any]]) -> None:
        query = f"""
        UNWIND $rows AS row
        UNWIND row.graph_layers AS layer_id
        MATCH (projection:{label} {{projection_id: row.id}})
        MATCH (layer:TosPhilosophyLayerProjection {{projection_id: layer_id}})
        MERGE (projection)-[:IN_LAYER]->(layer)
        """
        tx.run(query, rows=rows).consume()

    @staticmethod
    def _link_philosophy_source_refs(tx: Any, label: str, rows: list[dict[str, Any]]) -> None:
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
        MERGE (projection)-[:HAS_SOURCE_REF]->(source)
        """
        tx.run(query, rows=rows).consume()

    @staticmethod
    def _link_philosophy_cluster_members(tx: Any, cluster_rows: list[dict[str, Any]]) -> None:
        tx.run(
            """
            UNWIND $cluster_rows AS row
            MATCH (cluster:TosPhilosophyClusterProjection {projection_id: row.id})
            UNWIND row.member_node_ids AS node_id
            MATCH (node:TosPhilosophyNodeProjection {projection_id: node_id})
            MERGE (cluster)-[:CLUSTERS_NODE]->(node)
            """,
            cluster_rows=cluster_rows,
        ).consume()
        tx.run(
            """
            UNWIND $cluster_rows AS row
            MATCH (cluster:TosPhilosophyClusterProjection {projection_id: row.id})
            UNWIND row.member_edge_ids AS edge_id
            MATCH (edge:TosPhilosophyEdgeProjection {projection_id: edge_id})
            MERGE (cluster)-[:CLUSTERS_EDGE]->(edge)
            """,
            cluster_rows=cluster_rows,
        ).consume()
        tx.run(
            """
            UNWIND $cluster_rows AS row
            MATCH (cluster:TosPhilosophyClusterProjection {projection_id: row.id})
            UNWIND row.view_ids AS view_id
            MATCH (view:TosPhilosophyViewProjection {projection_id: view_id})
            MERGE (view)-[:PROJECTS_CLUSTER]->(cluster)
            MERGE (cluster)-[:IN_VIEW]->(view)
            """,
            cluster_rows=cluster_rows,
        ).consume()

    @staticmethod
    def _link_philosophy_review_packets(tx: Any, review_packet_rows: list[dict[str, Any]]) -> None:
        tx.run(
            """
            UNWIND $review_packet_rows AS row
            MATCH (packet:TosPhilosophyReviewPacketProjection {projection_id: row.id})
            MATCH (view:TosPhilosophyViewProjection {projection_id: row.view_id})
            MERGE (view)-[:HAS_REVIEW_PACKET]->(packet)
            MERGE (packet)-[:REVIEWS_VIEW]->(view)
            """,
            review_packet_rows=review_packet_rows,
        ).consume()

    @staticmethod
    def _link_philosophy_edges(tx: Any, edge_rows: list[dict[str, Any]]) -> None:
        tx.run(
            """
            UNWIND $edge_rows AS edge
            MATCH (projection:TosPhilosophyEdgeProjection {projection_id: edge.id})
            OPTIONAL MATCH (source:TosPhilosophyNodeProjection {projection_id: edge.from_id})
            OPTIONAL MATCH (target:TosPhilosophyNodeProjection {projection_id: edge.to_id})
            FOREACH (_ IN CASE WHEN source IS NULL THEN [] ELSE [1] END |
              MERGE (projection)-[:FROM_NODE]->(source)
            )
            FOREACH (_ IN CASE WHEN target IS NULL THEN [] ELSE [1] END |
              MERGE (projection)-[:TO_NODE]->(target)
            )
            FOREACH (_ IN CASE WHEN source IS NULL OR target IS NULL THEN [] ELSE [1] END |
              MERGE (source)-[rel:TOS_PHILOSOPHY_RELATION {edge_id: edge.id}]->(target)
              SET rel.predicate_id = edge.predicate_id,
                  rel.source_ref = edge.source_ref
            )
            """,
            edge_rows=edge_rows,
        ).consume()
