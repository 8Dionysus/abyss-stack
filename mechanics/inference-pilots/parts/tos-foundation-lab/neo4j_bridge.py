#!/usr/bin/env python3
"""Credential-contained Neo4j bridge executed inside the resident rag-api container."""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
import time
from typing import Any


RUN_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{7,95}$")

QUERY_CATALOG = {
    "subject_predicate": """
        MATCH (claim:ToSLabClaim {lab_run: $lab_run, subject_ref: $subject_ref, predicate: $predicate})
              -[:TOS_LAB_HAS_OBJECT {lab_run: $lab_run}]->(object:ToSLabRef {lab_run: $lab_run})
        RETURN collect(DISTINCT claim.claim_id) AS claim_refs,
               collect(DISTINCT object.ref) AS node_refs
    """,
    "claim_family": """
        MATCH (seed:ToSLabClaim {lab_run: $lab_run, claim_id: $seed_claim_ref})
        MATCH (seed)-[:TOS_LAB_ALTERNATIVE_TO*0..4]-(claim:ToSLabClaim {lab_run: $lab_run})
        WITH DISTINCT claim
        OPTIONAL MATCH (claim)-[:TOS_LAB_HAS_SUBJECT {lab_run: $lab_run}]->(subject:ToSLabRef {lab_run: $lab_run})
        OPTIONAL MATCH (claim)-[:TOS_LAB_HAS_OBJECT {lab_run: $lab_run}]->(object:ToSLabRef {lab_run: $lab_run})
        RETURN collect(DISTINCT claim.claim_id) AS claim_refs,
               collect(DISTINCT CASE WHEN subject.ref_kind = 'tos_id' THEN subject.ref END)
                 + collect(DISTINCT CASE WHEN object.ref_kind = 'tos_id' THEN object.ref END) AS node_refs,
               collect(DISTINCT CASE WHEN object.ref_kind = 'literal' THEN object.ref END) AS literal_values
    """,
    "path": """
        MATCH (start:ToSLabRef {lab_run: $lab_run, ref: $start_ref}),
              (finish:ToSLabRef {lab_run: $lab_run, ref: $end_ref})
        MATCH path = shortestPath((start)-[:TOS_LAB_ASSERTS*1..3]->(finish))
        RETURN [relation IN relationships(path) | relation.claim_id] AS claim_refs,
               [node IN nodes(path) | node.ref] AS node_refs
    """,
    "layer_inventory": """
        MATCH (claim:ToSLabClaim {lab_run: $lab_run})
        RETURN [] AS claim_refs, collect(DISTINCT claim.layer) AS node_refs,
               collect({layer: claim.layer, claim_id: claim.claim_id}) AS layer_rows
    """,
    "review_inventory": """
        MATCH (claim:ToSLabClaim {lab_run: $lab_run, review_status: $review_status})
        RETURN collect(DISTINCT claim.claim_id) AS claim_refs, [] AS node_refs
    """,
    "traceability_inventory": """
        MATCH (claim:ToSLabClaim {lab_run: $lab_run})
        OPTIONAL MATCH (claim)-[subject_rel:TOS_LAB_HAS_SUBJECT {lab_run: $lab_run}]->(:ToSLabRef {lab_run: $lab_run})
        OPTIONAL MATCH (claim)-[object_rel:TOS_LAB_HAS_OBJECT {lab_run: $lab_run}]->(:ToSLabRef {lab_run: $lab_run})
        OPTIONAL MATCH (claim)-[maker_rel:TOS_LAB_MADE_BY {lab_run: $lab_run}]->(:ToSLabAgent {lab_run: $lab_run})
        OPTIONAL MATCH (claim)-[event_rel:TOS_LAB_GENERATED_BY {lab_run: $lab_run}]->(:ToSLabRef {lab_run: $lab_run})
        OPTIONAL MATCH (claim)-[evidence_rel:TOS_LAB_HAS_EVIDENCE {lab_run: $lab_run}]->(:ToSLabRef {lab_run: $lab_run})
        WITH claim,
             count(DISTINCT subject_rel) AS subject_count,
             count(DISTINCT object_rel) AS object_count,
             count(DISTINCT maker_rel) AS maker_count,
             count(DISTINCT event_rel) AS event_count,
             count(DISTINCT evidence_rel) AS evidence_count
        OPTIONAL MATCH (:ToSLabRef {lab_run: $lab_run})
                       -[assertion:TOS_LAB_ASSERTS {lab_run: $lab_run, claim_id: claim.claim_id}]->
                       (:ToSLabRef {lab_run: $lab_run})
        WITH claim, subject_count, object_count, maker_count, event_count,
             evidence_count, count(DISTINCT assertion) AS assertion_count
        WHERE claim.canonical_traceable = true
          AND subject_count = 1 AND object_count = 1
          AND maker_count = 1 AND event_count = 1
          AND evidence_count = claim.evidence_count
          AND evidence_count > 0 AND assertion_count = 1
          AND claim.review_status IS NOT NULL AND claim.review_count >= 0
        RETURN collect(DISTINCT claim.claim_id) AS claim_refs, [] AS node_refs
    """,
}


def query_catalog() -> dict[str, str]:
    return {key: " ".join(value.split()) for key, value in sorted(QUERY_CATALOG.items())}


def _credentials() -> tuple[str, str]:
    raw = os.environ.get("NEO4J_AUTH", "")
    if "/" not in raw:
        raise RuntimeError("resident NEO4J_AUTH is unavailable")
    user, password = raw.split("/", 1)
    if not user or not password:
        raise RuntimeError("resident Neo4j credentials are incomplete")
    return user, password


def _consume(session: Any, cypher: str, parameters: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    records = [dict(record) for record in session.run(cypher, parameters)]
    elapsed_ms = (time.perf_counter() - started) * 1000
    return records, elapsed_ms


def _counts(session: Any, lab_run: str) -> dict[str, Any]:
    records, _ = _consume(
        session,
        """
        MATCH (node {lab_run: $lab_run})
        WITH count(node) AS node_count,
             count(CASE WHEN node:ToSLabClaim THEN 1 END) AS claim_count,
             count(CASE WHEN node:ToSLabRef THEN 1 END) AS ref_count,
             count(CASE WHEN node:ToSLabAgent THEN 1 END) AS agent_count
        OPTIONAL MATCH ()-[relation {lab_run: $lab_run}]->()
        RETURN node_count, claim_count, ref_count, agent_count,
               count(relation) AS relationship_count
        """,
        {"lab_run": lab_run},
    )
    if not records:
        return {"node_count": 0, "claim_count": 0, "ref_count": 0, "agent_count": 0, "relationship_count": 0}
    return records[0]


def _cleanup(session: Any, lab_run: str) -> float:
    started = time.perf_counter()
    session.run("MATCH (node {lab_run: $lab_run}) DETACH DELETE node", {"lab_run": lab_run}).consume()
    return time.perf_counter() - started


def _inventory(session: Any, lab_run: str) -> dict[str, Any]:
    node_rows, _ = _consume(
        session,
        """
        MATCH (node {lab_run: $lab_run})
        UNWIND labels(node) AS label
        RETURN label, count(*) AS count ORDER BY label
        """,
        {"lab_run": lab_run},
    )
    relationship_rows, _ = _consume(
        session,
        """
        MATCH ()-[relation {lab_run: $lab_run}]->()
        RETURN type(relation) AS relationship_type, count(*) AS count
        ORDER BY relationship_type
        """,
        {"lab_run": lab_run},
    )
    layer_rows, _ = _consume(
        session,
        """
        MATCH (claim:ToSLabClaim {lab_run: $lab_run})
        RETURN claim.layer AS layer, count(*) AS count ORDER BY layer
        """,
        {"lab_run": lab_run},
    )
    return {
        "node_labels": {str(row["label"]): int(row["count"]) for row in node_rows},
        "relationship_types": {
            str(row["relationship_type"]): int(row["count"]) for row in relationship_rows
        },
        "claim_layers": {str(row["layer"]): int(row["count"]) for row in layer_rows},
    }


def _materialize(session: Any, lab_run: str, rows: list[dict[str, Any]]) -> float:
    started = time.perf_counter()
    session.run(
        """
        UNWIND $rows AS row
        CREATE (claim:ToSLabClaim {
          lab_run: $lab_run,
          claim_id: row.claim_id,
          claim_type: row.claim_type,
          assertion_layer: row.assertion_layer,
          layer: row.layer,
          subject_ref: row.subject_ref,
          predicate: row.predicate,
          object_ref: row.object_ref,
          object_kind: row.object_kind,
          maker_ref: row.maker_ref,
          provenance_event_ref: row.provenance_event_ref,
          evidence_count: row.evidence_count,
          review_status: row.review_status,
          review_count: row.review_count,
          epistemic_status: row.epistemic_status,
          visibility: row.visibility,
          canonical_traceable: row.canonical_traceable,
          payload_json: row.payload_json
        })
        MERGE (subject:ToSLabRef {lab_run: $lab_run, ref: row.subject_ref})
          ON CREATE SET subject.ref_kind = row.subject_kind
        MERGE (object:ToSLabRef {lab_run: $lab_run, ref: row.object_ref})
          ON CREATE SET object.ref_kind = row.object_kind
        MERGE (maker:ToSLabAgent {lab_run: $lab_run, agent_ref: row.maker_ref})
        MERGE (event:ToSLabRef {lab_run: $lab_run, ref: row.provenance_event_ref})
          ON CREATE SET event.ref_kind = 'provenance_event'
        CREATE (claim)-[:TOS_LAB_HAS_SUBJECT {lab_run: $lab_run, claim_id: row.claim_id}]->(subject)
        CREATE (claim)-[:TOS_LAB_HAS_OBJECT {lab_run: $lab_run, claim_id: row.claim_id}]->(object)
        CREATE (claim)-[:TOS_LAB_MADE_BY {lab_run: $lab_run, claim_id: row.claim_id}]->(maker)
        CREATE (claim)-[:TOS_LAB_GENERATED_BY {lab_run: $lab_run, claim_id: row.claim_id}]->(event)
        CREATE (subject)-[:TOS_LAB_ASSERTS {
          lab_run: $lab_run,
          claim_id: row.claim_id,
          predicate: row.predicate,
          layer: row.layer,
          review_status: row.review_status
        }]->(object)
        """,
        {"lab_run": lab_run, "rows": rows},
    ).consume()
    session.run(
        """
        UNWIND $rows AS row
        MATCH (claim:ToSLabClaim {lab_run: $lab_run, claim_id: row.claim_id})
        UNWIND row.evidence_refs AS evidence_ref
        MERGE (evidence:ToSLabRef {lab_run: $lab_run, ref: evidence_ref})
          ON CREATE SET evidence.ref_kind = CASE WHEN evidence_ref STARTS WITH 'ToS/' THEN 'repo_path' ELSE 'tos_id' END
        CREATE (claim)-[:TOS_LAB_HAS_EVIDENCE {lab_run: $lab_run, claim_id: row.claim_id}]->(evidence)
        """,
        {"lab_run": lab_run, "rows": rows},
    ).consume()
    session.run(
        """
        UNWIND $rows AS row
        UNWIND row.alternative_claim_refs AS alternative_ref
        MATCH (claim:ToSLabClaim {lab_run: $lab_run, claim_id: row.claim_id})
        MATCH (alternative:ToSLabClaim {lab_run: $lab_run, claim_id: alternative_ref})
        CREATE (claim)-[:TOS_LAB_ALTERNATIVE_TO {lab_run: $lab_run, claim_id: row.claim_id}]->(alternative)
        """,
        {"lab_run": lab_run, "rows": rows},
    ).consume()
    return time.perf_counter() - started


def _query_parameters(query: dict[str, Any], lab_run: str) -> dict[str, Any]:
    parameters = dict(query.get("parameters", {}))
    parameters["lab_run"] = lab_run
    return parameters


def _normalize_query_record(operation: str, record: dict[str, Any]) -> dict[str, Any]:
    raw_claim_refs = [str(value) for value in record.get("claim_refs", []) if value is not None]
    raw_node_refs = [str(value) for value in record.get("node_refs", []) if value is not None]
    if operation == "path":
        claim_refs = raw_claim_refs
        node_refs = raw_node_refs
    else:
        claim_refs = sorted(set(raw_claim_refs))
        node_refs = sorted(set(raw_node_refs))
    detail: dict[str, Any] = {}
    if operation == "layer_inventory":
        layer_rows = record.get("layer_rows", [])
        counts: dict[str, int] = {}
        for item in layer_rows if isinstance(layer_rows, list) else []:
            if isinstance(item, dict) and isinstance(item.get("layer"), str):
                counts[item["layer"]] = counts.get(item["layer"], 0) + 1
        detail["layer_claim_counts"] = dict(sorted(counts.items()))
    if operation == "claim_family":
        detail["literal_object_values"] = sorted(
            {
                str(value)
                for value in record.get("literal_values", [])
                if value is not None
            }
        )
    return {"claim_refs": claim_refs, "node_refs": node_refs, "detail": detail}


def _execute_frozen_queries(session: Any, lab_run: str, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for query in queries:
        operation = str(query["operation"])
        if operation not in QUERY_CATALOG:
            raise RuntimeError(f"unsupported frozen graph query operation: {operation}")
        if operation == "path" and int(query.get("parameters", {}).get("maximum_claim_hops", 0)) != 3:
            raise RuntimeError("Neo4j bridge freezes the path ceiling at exactly three claim hops")
        parameters = _query_parameters(query, lab_run)
        first_records, first_ms = _consume(session, QUERY_CATALOG[operation], parameters)
        if len(first_records) != 1:
            raise RuntimeError(f"unexpected Neo4j row count for {query['query_id']}: {len(first_records)}")
        warm_latencies: list[float] = []
        for _ in range(5):
            repeated, elapsed = _consume(session, QUERY_CATALOG[operation], parameters)
            if repeated != first_records:
                raise RuntimeError(f"non-deterministic Neo4j answer for {query['query_id']}")
            warm_latencies.append(elapsed)
        normalized = _normalize_query_record(operation, first_records[0])
        results.append(
            {
                "query_id": query["query_id"],
                "operation": operation,
                "returned_claim_refs": normalized["claim_refs"],
                "returned_node_refs": normalized["node_refs"],
                "detail": normalized["detail"],
                "first_query_after_rebuild_ms": first_ms,
                "warm_latency_ms_median_of_5": statistics.median(warm_latencies),
                "warm_latencies_ms": warm_latencies,
            }
        )
    return results


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    import neo4j
    from neo4j import GraphDatabase

    lab_run = str(payload.get("lab_run", ""))
    if not RUN_KEY_RE.fullmatch(lab_run):
        raise RuntimeError("invalid isolated lab_run key")
    user, password = _credentials()
    driver = GraphDatabase.driver("bolt://neo4j:7687", auth=(user, password))
    try:
        driver.verify_connectivity()
        with driver.session(database="neo4j") as session:
            version_rows, _ = _consume(
                session,
                "CALL dbms.components() YIELD name, versions, edition RETURN name, versions[0] AS version, edition",
                {},
            )
            operation = payload.get("operation")
            if operation == "cleanup":
                before = _counts(session, lab_run)
                delete_seconds = _cleanup(session, lab_run)
                after = _counts(session, lab_run)
                return {
                    "ok": True,
                    "operation": "cleanup",
                    "before": before,
                    "after": after,
                    "delete_seconds": delete_seconds,
                    "server": version_rows[0] if version_rows else {},
                    "neo4j_driver_version": neo4j.__version__,
                }
            if operation != "run_lab":
                raise RuntimeError(f"unsupported bridge operation: {operation}")
            rows = payload.get("claims")
            queries = payload.get("queries")
            if not isinstance(rows, list) or len(rows) != 13:
                raise RuntimeError("bridge requires exactly 13 frozen claim rows")
            if not isinstance(queries, list) or len(queries) != 10:
                raise RuntimeError("bridge requires exactly 10 frozen graph queries")
            initial = _counts(session, lab_run)
            if initial["node_count"] != 0 or initial["relationship_count"] != 0:
                raise RuntimeError("isolated Neo4j lab namespace already exists")
            first_build_seconds = _materialize(session, lab_run, rows)
            first = _counts(session, lab_run)
            delete_seconds = _cleanup(session, lab_run)
            after_delete = _counts(session, lab_run)
            if after_delete["node_count"] != 0 or after_delete["relationship_count"] != 0:
                raise RuntimeError("Neo4j lab namespace deletion proof failed")
            rebuild_seconds = _materialize(session, lab_run, rows)
            rebuilt = _counts(session, lab_run)
            rebuilt_inventory = _inventory(session, lab_run)
            query_results = _execute_frozen_queries(session, lab_run, queries)
            retained = _counts(session, lab_run)
            return {
                "ok": True,
                "operation": "run_lab",
                "server": version_rows[0] if version_rows else {},
                "neo4j_driver_version": neo4j.__version__,
                "query_catalog": query_catalog(),
                "lifecycle": {
                    "initial": initial,
                    "first_materialization": first,
                    "first_build_seconds": first_build_seconds,
                    "delete_seconds": delete_seconds,
                    "after_delete": after_delete,
                    "rebuild_seconds": rebuild_seconds,
                    "rebuilt": rebuilt,
                    "rebuilt_inventory": rebuilt_inventory,
                    "retained": retained,
                    "retained_for_manual_review": True,
                },
                "query_results": query_results,
            }
    finally:
        driver.close()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise RuntimeError("bridge input must be a JSON object")
        print(json.dumps(execute(payload), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
