from __future__ import annotations

import json
import math
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence


CONFIG_SCHEMA_VERSION = "abyss-stack-repo-self-kag-retrieval-eval-v1"


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError("unsupported repo-self KAG retrieval eval config")
    cases = payload.get("semantic_cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("semantic_cases must be a non-empty list")
    required = {"name", "query", "repo", "path", "label"}
    names: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or any(not case.get(key) for key in required):
            raise ValueError(
                "each semantic case must define name, query, repo, path, and label"
            )
        name = str(case["name"])
        if name in names:
            raise ValueError(f"duplicate semantic case name: {name}")
        names.add(name)
    thresholds = payload.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds must be an object")
    for direction in ("minimums", "maximums"):
        values = thresholds.get(direction)
        if not isinstance(values, dict) or not values:
            raise ValueError(f"thresholds.{direction} must be a non-empty object")
        if any(not isinstance(value, (int, float)) for value in values.values()):
            raise ValueError(f"thresholds.{direction} values must be numeric")
    return payload


def reciprocal_rank_fusion(
    lexical: list[dict[str, Any]],
    semantic: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    scores: dict[str, float] = defaultdict(float)
    hits: dict[str, dict[str, Any]] = {}
    for weight, ranking in ((1.0, lexical), (0.5, semantic)):
        for rank, hit in enumerate(ranking, start=1):
            identifier = hit_id(hit)
            scores[identifier] += weight / rank
            hits[identifier] = hit
    ordered = sorted(scores, key=lambda key: (-scores[key], key))
    return [hits[key] for key in ordered[:limit]]


def hit_id(hit: dict[str, Any]) -> str:
    return str(hit.get("payload", {}).get("id") or hit.get("id"))


def grounded(hit: dict[str, Any]) -> bool:
    payload = hit.get("payload", {})
    return all(
        (
            payload.get("repo"),
            payload.get("path") is not None,
            payload.get("locator"),
            payload.get("source_record_ids"),
            payload.get("anchor_ids"),
            payload.get("provenance_ref"),
            payload.get("trust_ref"),
            payload.get("freshness"),
            payload.get("access"),
        )
    )


def case_score(
    name: str,
    query: str,
    relevant: set[str],
    hits: list[dict[str, Any]],
    latency_ms: float,
    *,
    top_k: int = 10,
) -> dict[str, Any]:
    selected = hits[:top_k]
    ranked = list(dict.fromkeys(hit_id(hit) for hit in selected))
    relevant_ranks = [
        index
        for index, identifier in enumerate(ranked, start=1)
        if identifier in relevant
    ]
    recall = len(set(ranked) & relevant) / len(relevant)
    reciprocal_rank = 1.0 / min(relevant_ranks) if relevant_ranks else 0.0
    dcg = sum(1.0 / math.log2(rank + 1) for rank in relevant_ranks)
    ideal = sum(
        1.0 / math.log2(rank + 1) for rank in range(1, min(len(relevant), top_k) + 1)
    )
    return {
        "name": name,
        "query": query,
        "relevant_ids": sorted(relevant),
        "result_ids": ranked,
        f"recall_at_{top_k}": round(recall, 6),
        "mrr": round(reciprocal_rank, 6),
        f"ndcg_at_{top_k}": round(dcg / ideal if ideal else 0.0, 6),
        "groundedness": round(
            sum(grounded(hit) for hit in selected) / len(selected) if selected else 1.0,
            6,
        ),
        "latency_ms": round(latency_ms, 3),
    }


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(cases: list[dict[str, Any]], *, top_k: int = 10) -> dict[str, Any]:
    latencies = [case["latency_ms"] for case in cases]
    return {
        "case_count": len(cases),
        f"recall_at_{top_k}": round(
            statistics.fmean(case[f"recall_at_{top_k}"] for case in cases), 6
        ),
        "mrr": round(statistics.fmean(case["mrr"] for case in cases), 6),
        f"ndcg_at_{top_k}": round(
            statistics.fmean(case[f"ndcg_at_{top_k}"] for case in cases), 6
        ),
        "groundedness": round(
            statistics.fmean(case["groundedness"] for case in cases), 6
        ),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 3),
            "p50": round(_percentile(latencies, 0.50), 3),
            "p95": round(_percentile(latencies, 0.95), 3),
            "max": round(max(latencies), 3),
        },
    }


def canonical_quality(connection: sqlite3.Connection) -> dict[str, Any]:
    node_count, distinct_nodes = connection.execute(
        "SELECT count(*),count(DISTINCT id) FROM nodes"
    ).fetchone()
    relation_count, distinct_relations = connection.execute(
        "SELECT count(*),count(DISTINCT id) FROM relations"
    ).fetchone()
    entity_count, distinct_entities = connection.execute(
        "SELECT count(*),count(DISTINCT id) FROM nodes WHERE node_class='entity'"
    ).fetchone()
    unresolved_entities = connection.execute(
        "SELECT count(*) FROM nodes entity WHERE entity.node_class='entity' AND ("
        "EXISTS (SELECT 1 FROM json_each(entity.payload_json,'$.source_record_ids') source_ref "
        "LEFT JOIN nodes source ON source.id=source_ref.value WHERE source.id IS NULL) OR "
        "EXISTS (SELECT 1 FROM json_each(entity.payload_json,'$.anchor_ids') anchor_ref "
        "LEFT JOIN nodes anchor ON anchor.id=anchor_ref.value WHERE anchor.id IS NULL))"
    ).fetchone()[0]
    unresolved_endpoints = connection.execute(
        "SELECT count(*) FROM relations r "
        "LEFT JOIN nodes source ON source.id=r.from_id "
        "LEFT JOIN nodes target ON target.id=r.to_id "
        "WHERE source.id IS NULL OR target.id IS NULL"
    ).fetchone()[0]
    relation_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(relations)")
    }
    if "evidence_anchor_count" in relation_columns:
        unsupported_query = (
            "SELECT count(*) FROM relations WHERE "
            "evidence_anchor_count=0 OR provenance_ref='' OR trust_ref=''"
        )
    else:
        unsupported_query = (
            "SELECT count(*) FROM relations WHERE "
            "coalesce(json_array_length(json_extract(payload_json,"
            "'$.evidence_anchor_ids')),0)=0 "
            "OR coalesce(json_extract(payload_json,'$.provenance_ref'),'')='' "
            "OR coalesce(json_extract(payload_json,'$.trust_ref'),'')=''"
        )
    unsupported_edges = connection.execute(unsupported_query).fetchone()[0]
    return {
        "node_count": node_count,
        "relation_count": relation_count,
        "entity_count": entity_count,
        "duplicate_node_id_count": node_count - distinct_nodes,
        "duplicate_relation_id_count": relation_count - distinct_relations,
        "duplicate_entity_id_count": entity_count - distinct_entities,
        "entity_resolution_accuracy": round(
            (entity_count - unresolved_entities) / max(entity_count, 1), 6
        ),
        "relation_endpoint_resolution": round(
            (relation_count - unresolved_endpoints) / max(relation_count, 1), 6
        ),
        "unsupported_edge_count": unsupported_edges,
        "unsupported_edge_rate": round(unsupported_edges / max(relation_count, 1), 6),
    }


def exact_targets(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "WITH ranked AS ("
        "SELECT d.*, row_number() OVER (PARTITION BY repo ORDER BY "
        "CASE WHEN path='README.md' THEN 0 WHEN path='AGENTS.md' THEN 1 ELSE 2 END, "
        "path, start_line, id) AS rn FROM documents d WHERE access_scope='public') "
        "SELECT * FROM ranked WHERE rn=1 ORDER BY repo"
    ).fetchall()


def lexical_targets(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "WITH unique_labels AS ("
        "SELECT lower(label) AS normalized FROM documents "
        "WHERE node_class='anchor' AND kind IN ('markdown_heading','python_symbol') "
        "AND length(label) BETWEEN 12 AND 80 GROUP BY lower(label) HAVING count(*)=1), "
        "ranked AS (SELECT d.*, row_number() OVER (PARTITION BY repo ORDER BY "
        "CASE WHEN kind='markdown_heading' THEN 0 ELSE 1 END, length(label), path, id) AS rn "
        "FROM documents d JOIN unique_labels u ON u.normalized=lower(d.label) "
        "WHERE d.access_scope='public' AND instr(d.label, '_')=0) "
        "SELECT * FROM ranked WHERE rn=1 ORDER BY repo"
    ).fetchall()


def semantic_targets(
    connection: sqlite3.Connection,
    cases: Sequence[dict[str, str]],
) -> list[tuple[dict[str, str], set[str]]]:
    resolved: list[tuple[dict[str, str], set[str]]] = []
    for case in cases:
        rows = connection.execute(
            "SELECT id FROM documents WHERE repo=? AND path=? AND label=? "
            "ORDER BY CASE WHEN ltrim(text) GLOB '#*' THEN 0 ELSE 1 END, id LIMIT 1",
            (case["repo"], case["path"], case["label"]),
        ).fetchall()
        if not rows:
            raise RuntimeError(f"semantic target is missing: {case['name']}")
        resolved.append((case, {str(row["id"]) for row in rows}))
    return resolved


def graph_targets(
    connection: sqlite3.Connection,
    *,
    minimum_cases: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        "WITH path_map AS ("
        "SELECT n.id AS source_id, min(d.path) AS path FROM nodes n "
        "JOIN documents d JOIN json_each(d.metadata_json, '$.source_record_ids') j "
        "ON j.value=n.id WHERE n.node_class='artifact' GROUP BY n.id), "
        "candidates AS (SELECT r1.source_repo AS repo, r1.from_id AS source_id, "
        "r1.relation_kind AS k1, r2.relation_kind AS k2, count(DISTINCT r2.to_id) AS targets "
        "FROM relations r1 JOIN relations r2 ON r2.from_id=r1.to_id "
        "JOIN path_map p ON p.source_id=r1.from_id "
        "WHERE r1.relation_kind IN ('defines','represents') "
        "AND r2.relation_kind IN ('calls','references','contains') "
        "GROUP BY r1.source_repo,r1.from_id,r1.relation_kind,r2.relation_kind "
        "HAVING targets BETWEEN 1 AND 5), "
        "ranked AS (SELECT c.*, p.path, row_number() OVER (PARTITION BY c.repo "
        "ORDER BY c.targets,c.source_id,c.k1,c.k2) AS rn FROM candidates c "
        "JOIN path_map p ON p.source_id=c.source_id) "
        "SELECT * FROM ranked WHERE rn=1 ORDER BY repo LIMIT 16"
    ).fetchall()
    cases: list[dict[str, Any]] = []
    for row in rows:
        targets = connection.execute(
            "SELECT DISTINCT r2.to_id FROM relations r1 "
            "JOIN relations r2 ON r2.from_id=r1.to_id "
            "WHERE r1.from_id=? AND r1.relation_kind=? AND r2.relation_kind=? "
            "ORDER BY r2.to_id",
            (row["source_id"], row["k1"], row["k2"]),
        ).fetchall()
        cases.append(
            {
                "name": f"{row['repo']}:{row['k1']}:{row['k2']}",
                "query": f"From {row['path']}, follow {row['k1']} then {row['k2']}",
                "repo": row["repo"],
                "source_id": row["source_id"],
                "path": row["path"],
                "first_relation": row["k1"],
                "second_relation": row["k2"],
                "relevant": {str(target["to_id"]) for target in targets},
            }
        )
    if len(cases) < minimum_cases:
        raise RuntimeError(f"only {len(cases)} graph cases were derivable")
    return cases
