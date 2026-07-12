from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any, Iterable, Iterator

from .bundle import RetrievalBundle, canonical_json
from .transport import JsonHttpClient


SCHEMA_VERSION = "abyss-stack-repo-self-kag-neo4j-v1"


def _batches(records: Iterable[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for record in records:
        batch.append(record)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class Neo4jProjection:
    def __init__(self, client: JsonHttpClient, database: str = "neo4j") -> None:
        self.client = client
        self.database = database

    def execute(
        self,
        statement: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[list[Any]]:
        response = self.client.request(
            "POST",
            f"/db/{self.database}/tx/commit",
            {
                "statements": [
                    {
                        "statement": statement,
                        "parameters": parameters or {},
                        "resultDataContents": ["row"],
                    }
                ]
            },
        )
        errors = response.get("errors")
        if isinstance(errors, list) and errors:
            message = "; ".join(str(item.get("message", item)) for item in errors)
            raise RuntimeError(f"Neo4j transaction failed: {message}")
        results = response.get("results")
        if not isinstance(results, list) or not results:
            return []
        data = results[0].get("data", [])
        return [item.get("row", []) for item in data if isinstance(item, dict)]

    def scalar(self, statement: str, parameters: dict[str, Any]) -> Any:
        rows = self.execute(statement, parameters)
        if not rows or not rows[0]:
            return None
        return rows[0][0]


def _owner_row(record: dict[str, Any]) -> dict[str, Any]:
    repo = record["repo"]
    return {
        "repo": str(repo["name"]),
        "namespace": str(repo["namespace"]),
        "owner_type": str(repo["owner_type"]),
        "git_ref": str(repo["git_ref"]),
        "source_index_digest": str(record["source_index_digest"]),
        "node_counts_json": canonical_json(record["node_counts"]),
        "relation_count": int(record["relation_count"]),
    }


def _node_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record["id"]),
        "repo": str(record["repo"]),
        "namespace": str(record["namespace"]),
        "node_class": str(record["node_class"]),
        "kind": str(record["kind"]),
        "source_record_ids": list(record["source_record_ids"]),
        "anchor_ids": list(record["anchor_ids"]),
        "access_scope": str(record["access_scope"]),
    }


def _relation_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record["id"]),
        "relation_kind": str(record["relation_kind"]),
        "from_id": str(record["from_id"]),
        "to_id": str(record["to_id"]),
        "source_repo": str(record["source_repo"]),
        "target_repo": str(record["target_repo"]),
        "scope": str(record["scope"]),
        "evidence_anchor_ids": list(record["evidence_anchor_ids"]),
        "evidence_class": str(record["evidence_class"]),
        "confidence": float(record["confidence"]),
        "temporal_ref": str(record["temporal_ref"]),
        "provenance_ref": str(record["provenance_ref"]),
        "trust_ref": str(record["trust_ref"]),
    }


def _external_row(record: dict[str, Any]) -> dict[str, Any]:
    identifier = hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()
    return {
        "id": f"external:{identifier}",
        "source_repo": str(record["source_repo"]),
        "source_anchor_id": str(record["source_anchor_id"]),
        "target_repo": str(record.get("target_repo", "")),
        "target_ref": str(record["target_ref"]),
        "reference_kind": str(record["reference_kind"]),
    }


def _current_digest(graph: Neo4jProjection) -> str | None:
    value = graph.scalar(
        "MATCH (p:AoAKagProjection {name: 'repo-self-current'}) RETURN p.current_digest",
        {},
    )
    return str(value) if value else None


def materialize(
    bundle: RetrievalBundle,
    *,
    graph: Neo4jProjection,
    batch_size: int = 1000,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    projection = bundle.projection_digest
    previous = _current_digest(graph)
    graph.execute(
        "CREATE INDEX aoa_kag_node_identity IF NOT EXISTS "
        "FOR (n:AoAKagNode) ON (n.projection_digest, n.id)"
    )
    graph.execute(
        "CREATE INDEX aoa_kag_owner_identity IF NOT EXISTS "
        "FOR (n:AoAKagOwner) ON (n.projection_digest, n.repo)"
    )

    totals = {
        key: int(bundle.manifest["files"][key]["record_count"])
        for key in ("owners", "nodes", "relations", "external_references")
    }
    completed = 0
    for batch in _batches((_owner_row(item) for item in bundle.records("owners")), batch_size):
        graph.execute(
            "UNWIND $rows AS row "
            "MERGE (o:AoAKagOwner {projection_digest: $projection, repo: row.repo}) "
            "SET o.namespace = row.namespace, o.owner_type = row.owner_type, "
            "o.git_ref = row.git_ref, o.source_index_digest = row.source_index_digest, "
            "o.node_counts_json = row.node_counts_json, o.relation_count = row.relation_count",
            {"projection": projection, "rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress("owners", completed, totals["owners"])

    completed = 0
    for batch in _batches((_node_row(item) for item in bundle.records("nodes")), batch_size):
        graph.execute(
            "UNWIND $rows AS row "
            "MERGE (n:AoAKagNode {projection_digest: $projection, id: row.id}) "
            "SET n.repo = row.repo, n.namespace = row.namespace, "
            "n.node_class = row.node_class, n.kind = row.kind, "
            "n.source_record_ids = row.source_record_ids, n.anchor_ids = row.anchor_ids, "
            "n.access_scope = row.access_scope "
            "WITH n, row "
            "MATCH (o:AoAKagOwner {projection_digest: $projection, repo: row.repo}) "
            "MERGE (n)-[:AOA_KAG_OWNED_BY {projection_digest: $projection}]->(o)",
            {"projection": projection, "rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress("nodes", completed, totals["nodes"])

    completed = 0
    for batch in _batches(
        (_relation_row(item) for item in bundle.records("relations")),
        batch_size,
    ):
        graph.execute(
            "UNWIND $rows AS row "
            "MATCH (source:AoAKagNode {projection_digest: $projection, id: row.from_id}) "
            "MATCH (target:AoAKagNode {projection_digest: $projection, id: row.to_id}) "
            "MERGE (source)-[r:AOA_KAG_RELATION {projection_digest: $projection, id: row.id}]->(target) "
            "SET r.relation_kind = row.relation_kind, r.source_repo = row.source_repo, "
            "r.target_repo = row.target_repo, r.scope = row.scope, "
            "r.evidence_anchor_ids = row.evidence_anchor_ids, "
            "r.evidence_class = row.evidence_class, r.confidence = row.confidence, "
            "r.temporal_ref = row.temporal_ref, r.provenance_ref = row.provenance_ref, "
            "r.trust_ref = row.trust_ref",
            {"projection": projection, "rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress("relations", completed, totals["relations"])

    completed = 0
    for batch in _batches(
        (_external_row(item) for item in bundle.records("external_references")),
        batch_size,
    ):
        graph.execute(
            "UNWIND $rows AS row "
            "MATCH (source:AoAKagNode {projection_digest: $projection, id: row.source_anchor_id}) "
            "MERGE (target:AoAKagExternal {projection_digest: $projection, id: row.id}) "
            "SET target.target_repo = row.target_repo, target.target_ref = row.target_ref, "
            "target.reference_kind = row.reference_kind "
            "MERGE (source)-[r:AOA_KAG_EXTERNAL_REFERENCE "
            "{projection_digest: $projection, id: row.id}]->(target) "
            "SET r.source_repo = row.source_repo, r.reference_kind = row.reference_kind",
            {"projection": projection, "rows": batch},
        )
        completed += len(batch)
        if progress is not None:
            progress(
                "external_references",
                completed,
                totals["external_references"],
            )

    expected = {
        key: int(bundle.manifest["files"][key]["record_count"])
        for key in ("owners", "nodes", "relations", "external_references")
    }
    observed = _counts(graph, projection)
    if observed != expected:
        raise RuntimeError(f"Neo4j projection counts mismatch: {observed} != {expected}")

    graph.execute(
        "MERGE (p:AoAKagProjection {name: 'repo-self-current'}) "
        "SET p.previous_digest = p.current_digest, p.current_digest = $projection, "
        "p.bundle_digest = $bundle, p.federation_digest = $federation, "
        "p.owner_count = $owners, p.node_count = $nodes, "
        "p.relation_count = $relations, p.external_reference_count = $external",
        {
            "projection": projection,
            "bundle": bundle.bundle_digest,
            "federation": bundle.federation_digest,
            "owners": expected["owners"],
            "nodes": expected["nodes"],
            "relations": expected["relations"],
            "external": expected["external_references"],
        },
    )
    keep = [item for item in (projection, previous) if item]
    graph.execute(
        "MATCH (n) WHERE (n:AoAKagOwner OR n:AoAKagNode OR n:AoAKagExternal) "
        "AND n.projection_digest IS NOT NULL AND NOT n.projection_digest IN $keep "
        "DETACH DELETE n",
        {"keep": keep},
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "database": graph.database,
        "projection_digest": projection,
        "previous_projection_digest": previous,
        "counts": observed,
    }


def _counts(graph: Neo4jProjection, projection: str) -> dict[str, int]:
    queries = {
        "owners": "MATCH (n:AoAKagOwner {projection_digest: $projection}) RETURN count(n)",
        "nodes": "MATCH (n:AoAKagNode {projection_digest: $projection}) RETURN count(n)",
        "relations": "MATCH ()-[r:AOA_KAG_RELATION {projection_digest: $projection}]->() RETURN count(r)",
        "external_references": "MATCH ()-[r:AOA_KAG_EXTERNAL_REFERENCE {projection_digest: $projection}]->() RETURN count(r)",
    }
    return {
        key: int(graph.scalar(query, {"projection": projection}) or 0)
        for key, query in queries.items()
    }


def check(bundle: RetrievalBundle, *, graph: Neo4jProjection) -> dict[str, Any]:
    projection = bundle.projection_digest
    current = _current_digest(graph)
    if current != projection:
        raise RuntimeError(f"Neo4j current projection is {current}, expected {projection}")
    counts = _counts(graph, projection)
    expected = {
        key: int(bundle.manifest["files"][key]["record_count"])
        for key in counts
    }
    if counts != expected:
        raise RuntimeError(f"Neo4j projection counts mismatch: {counts} != {expected}")
    return {
        "schema_version": SCHEMA_VERSION,
        "database": graph.database,
        "projection_digest": projection,
        "counts": counts,
    }
