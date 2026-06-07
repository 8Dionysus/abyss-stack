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
            note="neo4j corpus sync is unavailable because TOS_GRAPH_NEO4J_URI is missing; sync requests fall back to preview counts",
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
            note="neo4j corpus sync is configured but credentials are incomplete; sync requests fall back to preview counts",
        )

    return Neo4jStoreStatus(
        configured=True,
        ready=True,
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        database=settings.neo4j_database,
        projection_mode=settings.projection_mode,
        note="neo4j corpus projection sync is ready; Tree of Sophia remains canonical and Neo4j remains projection-only",
    )


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


class Neo4jProjectionStore:
    def __init__(self, settings: TosGraphSettings, status: Neo4jStoreStatus) -> None:
        self.settings = settings
        self.status = status

    @staticmethod
    def _corpus_rows(corpus: dict[str, Any], key: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in corpus.get(key, []):
            if isinstance(item, dict):
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
