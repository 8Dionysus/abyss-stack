#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sqlite3
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from kag_runtime import evaluation, exact, graph, vector
from kag_runtime.bundle import write_json_atomic
from kag_runtime.transport import JsonHttpClient


PART_ROOT = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = PART_ROOT / "config" / "repo-self-retrieval-eval.json"
STACK_ROOT = Path(os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack"))
SQLITE_PATH = STACK_ROOT / "Knowledge/kag/repo-self/exact/repo-self.sqlite3"
QDRANT_URL = os.environ.get("AOA_KAG_QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_ALIAS = "aoa_kag_repo_self_current"
EMBEDDING_URL = os.environ.get("AOA_KAG_EMBEDDING_URL", "http://127.0.0.1:5403")
EMBEDDING_MODEL = "qwen3-embed-0.6b-int8-ov"
NEO4J_URL = os.environ.get("AOA_KAG_NEO4J_HTTP_URL", "http://127.0.0.1:7474")
NEO4J_DATABASE = os.environ.get("AOA_KAG_NEO4J_DATABASE", "neo4j")
HTTP_TIMEOUT = 180.0
TOP_K = 10
EXPECTED_OWNER_COUNT = 24
MIN_GRAPH_CASES = 12
SEMANTIC_CASES: tuple[dict[str, str], ...] = ()
THRESHOLD_MINIMUMS: dict[str, float] = {}
THRESHOLD_MAXIMUMS: dict[str, float] = {}
EMBEDDING_PROFILE: dict[str, Any] = {}
EMBEDDINGS: JsonHttpClient | None = None
QDRANT: JsonHttpClient | None = None
GRAPH: graph.Neo4jProjection | None = None
GRAPH_OWNER_SLICE_STATE: dict[str, Any] = {}


def now() -> str:
    return datetime.now(UTC).isoformat()


load_config = evaluation.load_config


def dotenv_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def neo4j_headers() -> dict[str, str]:
    env = dotenv_values(STACK_ROOT / "Secrets/Configs/stack.env")
    user = os.environ.get("AOA_KAG_NEO4J_USER") or env.get("AOA_RAG_NEO4J_USER")
    password = os.environ.get("AOA_KAG_NEO4J_PASSWORD") or env.get(
        "AOA_RAG_NEO4J_PASSWORD"
    )
    auth = os.environ.get("AOA_KAG_NEO4J_AUTH") or env.get("NEO4J_AUTH", "")
    if (not user or not password) and "/" in auth:
        user, password = auth.split("/", 1)
    if not user or not password:
        raise RuntimeError("Neo4j credentials are unavailable")
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def client_headers(env_name: str) -> dict[str, str]:
    value = os.environ.get(env_name)
    return {"api-key": value} if value else {}


def qdrant_collection() -> str:
    if QDRANT is None:
        raise RuntimeError("Qdrant client is unavailable")
    return vector.active_collection(QDRANT, QDRANT_ALIAS)


def vector_search(
    query: str,
    collection: str,
    *,
    repo: str | None = None,
    kind: str | None = None,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], float]:
    if QDRANT is None or EMBEDDINGS is None:
        raise RuntimeError("vector retrieval clients are unavailable")
    return vector.search(
        query,
        qdrant=QDRANT,
        embeddings=EMBEDDINGS,
        profile=EMBEDDING_PROFILE,
        collection=collection,
        alias=QDRANT_ALIAS,
        repo=repo,
        kind=kind,
        limit=limit or TOP_K,
    )


def lexical_search(
    connection: sqlite3.Connection,
    query: str,
    *,
    repo: str | None = None,
    kind: str | None = None,
    operator: str = "AND",
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], float]:
    return exact.search_lexical(
        connection,
        query,
        repo=repo,
        kind=kind,
        operator=operator,
        limit=limit or TOP_K,
    )


def exact_search(
    connection: sqlite3.Connection,
    query: str,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], float]:
    return exact.search_exact(connection, query, limit=limit or TOP_K)


def filter_search(
    connection: sqlite3.Connection,
    target: sqlite3.Row,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], float]:
    return exact.search_filter(
        connection,
        repo=str(target["repo"]),
        path=str(target["path"]),
        node_class=str(target["node_class"]),
        kind=str(target["kind"]),
        limit=limit or TOP_K,
    )


hit_id = evaluation.hit_id
grounded = evaluation.grounded
canonical_quality = evaluation.canonical_quality
exact_targets = evaluation.exact_targets
lexical_targets = evaluation.lexical_targets


def reciprocal_rank_fusion(
    lexical: list[dict[str, Any]],
    semantic: list[dict[str, Any]],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return evaluation.reciprocal_rank_fusion(
        lexical,
        semantic,
        limit=limit or TOP_K,
    )


def case_score(
    name: str,
    query: str,
    relevant: set[str],
    hits: list[dict[str, Any]],
    latency_ms: float,
) -> dict[str, Any]:
    return evaluation.case_score(
        name,
        query,
        relevant,
        hits,
        latency_ms,
        top_k=TOP_K,
    )


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return evaluation.summarize(cases, top_k=TOP_K)


def semantic_targets(
    connection: sqlite3.Connection,
) -> list[tuple[dict[str, str], set[str]]]:
    return evaluation.semantic_targets(connection, SEMANTIC_CASES)


def graph_targets(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return evaluation.graph_targets(
        connection,
        minimum_cases=MIN_GRAPH_CASES,
    )


def graph_search(
    case: dict[str, Any],
    projection: str,
) -> tuple[list[dict[str, Any]], float, float]:
    if GRAPH is None:
        raise RuntimeError("Neo4j projection client is unavailable")
    return graph.search_multihop(
        graph=GRAPH,
        projection=projection,
        owner_slice_state=GRAPH_OWNER_SLICE_STATE,
        source_id=case["source_id"],
        first_relation=case["first_relation"],
        second_relation=case["second_relation"],
        source_path=case["path"],
        limit=TOP_K,
    )


def evaluate(connection: sqlite3.Connection, *, config_digest: str) -> dict[str, Any]:
    started_at = now()
    metadata = dict(connection.execute("SELECT key,value FROM metadata"))
    projection = metadata["projection_digest"]
    collection = qdrant_collection()
    routes: dict[str, list[dict[str, Any]]] = defaultdict(list)

    owner_targets = exact_targets(connection)
    for target in owner_targets:
        relevant = {str(target["id"])}
        hits, latency = exact_search(connection, str(target["id"]))
        routes["exact"].append(
            case_score(
                str(target["repo"]),
                str(target["id"]),
                relevant,
                hits,
                latency,
            )
        )
        hits, latency = filter_search(connection, target)
        routes["filter"].append(
            case_score(
                str(target["repo"]),
                str(target["path"]),
                relevant,
                hits,
                latency,
            )
        )

    lexical_cases = lexical_targets(connection)
    for target in lexical_cases:
        relevant = {str(target["id"])}
        lexical, lexical_latency = lexical_search(
            connection,
            str(target["label"]),
            repo=str(target["repo"]),
            kind=str(target["kind"]),
        )
        vector, vector_latency = vector_search(
            str(target["label"]),
            collection,
            repo=str(target["repo"]),
            kind=str(target["kind"]),
        )
        hybrid = reciprocal_rank_fusion(lexical, vector)
        routes["lexical_known_item"].append(
            case_score(
                str(target["repo"]),
                str(target["label"]),
                relevant,
                lexical,
                lexical_latency,
            )
        )
        routes["vector_known_item"].append(
            case_score(
                str(target["repo"]),
                str(target["label"]),
                relevant,
                vector,
                vector_latency,
            )
        )
        routes["hybrid_known_item"].append(
            case_score(
                str(target["repo"]),
                str(target["label"]),
                relevant,
                hybrid,
                lexical_latency + vector_latency,
            )
        )

    for case, relevant in semantic_targets(connection):
        lexical, lexical_latency = lexical_search(
            connection,
            case["query"],
            repo=case["repo"],
            kind="markdown_heading",
            operator="OR",
        )
        vector, vector_latency = vector_search(
            case["query"],
            collection,
            repo=case["repo"],
            kind="markdown_heading",
        )
        hybrid = reciprocal_rank_fusion(lexical, vector)
        routes["lexical_semantic"].append(
            case_score(
                case["name"],
                case["query"],
                relevant,
                lexical,
                lexical_latency,
            )
        )
        routes["vector_semantic"].append(
            case_score(
                case["name"],
                case["query"],
                relevant,
                vector,
                vector_latency,
            )
        )
        routes["hybrid_semantic"].append(
            case_score(
                case["name"],
                case["query"],
                relevant,
                hybrid,
                lexical_latency + vector_latency,
            )
        )

    chain_completeness: list[float] = []
    graph_text_baseline: list[dict[str, Any]] = []
    for case in graph_targets(connection):
        graph_hits, graph_latency, completeness = graph_search(case, projection)
        chain_completeness.append(completeness)
        routes["graph_multihop"].append(
            case_score(
                case["name"],
                case["query"],
                case["relevant"],
                graph_hits,
                graph_latency,
            )
        )
        lexical, lexical_latency = lexical_search(
            connection,
            case["query"],
            repo=case["repo"],
            operator="OR",
        )
        vector, vector_latency = vector_search(
            case["query"],
            collection,
            repo=case["repo"],
        )
        hybrid = reciprocal_rank_fusion(lexical, vector)
        graph_text_baseline.append(
            case_score(
                case["name"],
                case["query"],
                case["relevant"],
                hybrid,
                lexical_latency + vector_latency,
            )
        )
    routes["hybrid_multihop_baseline"] = graph_text_baseline

    summaries = {name: summarize(cases) for name, cases in routes.items()}
    quality = canonical_quality(connection)
    graph_completeness = round(statistics.fmean(chain_completeness), 6)
    graph_advantage = round(
        summaries["graph_multihop"]["recall_at_10"]
        - summaries["hybrid_multihop_baseline"]["recall_at_10"],
        6,
    )
    duplicate_id_rate = round(
        (
            quality["duplicate_node_id_count"]
            + quality["duplicate_relation_id_count"]
            + quality["duplicate_entity_id_count"]
        )
        / max(quality["node_count"] + quality["relation_count"], 1),
        6,
    )
    observed_metrics = {
        "exact_recall_at_10": summaries["exact"]["recall_at_10"],
        "filter_recall_at_10": summaries["filter"]["recall_at_10"],
        "lexical_known_item_recall_at_10": summaries["lexical_known_item"][
            "recall_at_10"
        ],
        "vector_semantic_recall_at_10": summaries["vector_semantic"]["recall_at_10"],
        "hybrid_semantic_recall_at_10": summaries["hybrid_semantic"]["recall_at_10"],
        "graph_multihop_recall_at_10": summaries["graph_multihop"]["recall_at_10"],
        "graph_evidence_chain_completeness": graph_completeness,
        "graph_recall_advantage": graph_advantage,
        "retrieval_groundedness": min(
            summary["groundedness"] for summary in summaries.values()
        ),
        "entity_resolution_accuracy": quality["entity_resolution_accuracy"],
        "duplicate_id_rate": duplicate_id_rate,
        "relation_endpoint_resolution": quality["relation_endpoint_resolution"],
        "unsupported_edge_rate": quality["unsupported_edge_rate"],
    }
    threshold_results = {
        name: observed_metrics[name] >= minimum
        for name, minimum in THRESHOLD_MINIMUMS.items()
    }
    threshold_results.update(
        {
            name: observed_metrics[name] <= maximum
            for name, maximum in THRESHOLD_MAXIMUMS.items()
        }
    )
    threshold_results["owner_coverage"] = (
        len(owner_targets) == EXPECTED_OWNER_COUNT
        and len(lexical_cases) == EXPECTED_OWNER_COUNT
    )
    status = "passed" if all(threshold_results.values()) else "failed"
    return {
        "schema_version": "abyss-stack-repo-self-kag-retrieval-eval-v1",
        "status": status,
        "started_at": started_at,
        "completed_at": now(),
        "config_identity": {
            "schema_version": "abyss-stack-repo-self-kag-retrieval-eval-v1",
            "sha256": config_digest,
        },
        "bundle_identity": {
            "bundle_digest": metadata["bundle_digest"],
            "projection_digest": projection,
            "federation_digest": metadata["federation_digest"],
        },
        "runtime": {
            "exact": {"schema": metadata["schema_version"], "path": str(SQLITE_PATH)},
            "lexical": {"engine": "SQLite FTS5", "ranking": "BM25"},
            "vector": {
                "collection": collection,
                "alias": QDRANT_ALIAS,
                "embedding_profile": json.loads(metadata["embedding_profile"]),
            },
            "hybrid": {
                "fusion": "weighted-reciprocal-rank-fusion",
                "rank_constant": 0,
                "route_weights": {"lexical": 1.0, "vector": 0.5},
            },
            "graph": {
                "engine": "Neo4j",
                "database": NEO4J_DATABASE,
                "projection_digest": projection,
            },
        },
        "inventory": {
            "owners": len(owner_targets),
            "exact_cases": len(routes["exact"]),
            "filter_cases": len(routes["filter"]),
            "lexical_cases": len(routes["lexical_known_item"]),
            "semantic_cases": len(routes["vector_semantic"]),
            "multihop_cases": len(routes["graph_multihop"]),
        },
        "summaries": summaries,
        "graph_evidence_chain_completeness": graph_completeness,
        "graph_recall_advantage": graph_advantage,
        "canonical_quality": quality,
        "observed_metrics": observed_metrics,
        "threshold_limits": {
            "minimums": THRESHOLD_MINIMUMS,
            "maximums": THRESHOLD_MAXIMUMS,
        },
        "thresholds": threshold_results,
        "cases": dict(routes),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate live OS Abyss repo-self KAG retrieval projections."
    )
    parser.add_argument("--stack-root", type=Path, default=STACK_ROOT)
    parser.add_argument("--sqlite-path", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--embedding-url", default=EMBEDDING_URL)
    parser.add_argument("--embedding-model")
    parser.add_argument("--qdrant-url", default=QDRANT_URL)
    parser.add_argument("--qdrant-alias", default=QDRANT_ALIAS)
    parser.add_argument("--neo4j-url", default=NEO4J_URL)
    parser.add_argument("--neo4j-database", default=NEO4J_DATABASE)
    parser.add_argument("--http-timeout", type=float, default=HTTP_TIMEOUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    global EMBEDDING_PROFILE
    global EMBEDDINGS
    global EMBEDDING_MODEL
    global EMBEDDING_URL
    global EXPECTED_OWNER_COUNT
    global GRAPH
    global GRAPH_OWNER_SLICE_STATE
    global HTTP_TIMEOUT
    global MIN_GRAPH_CASES
    global NEO4J_DATABASE
    global NEO4J_URL
    global QDRANT_ALIAS
    global QDRANT
    global QDRANT_URL
    global SEMANTIC_CASES
    global SQLITE_PATH
    global STACK_ROOT
    global THRESHOLD_MAXIMUMS
    global THRESHOLD_MINIMUMS
    global TOP_K

    args = build_parser().parse_args(argv)
    STACK_ROOT = args.stack_root.resolve()
    SQLITE_PATH = (
        args.sqlite_path.resolve()
        if args.sqlite_path
        else STACK_ROOT / "Knowledge/kag/repo-self/exact/repo-self.sqlite3"
    )
    config_path = args.config.resolve()
    config = load_config(config_path)
    TOP_K = int(config.get("top_k", 10))
    EXPECTED_OWNER_COUNT = int(config["expected_owner_count"])
    MIN_GRAPH_CASES = int(config["minimum_graph_cases"])
    SEMANTIC_CASES = tuple(config["semantic_cases"])
    THRESHOLD_MINIMUMS = {
        str(name): float(value)
        for name, value in config["thresholds"]["minimums"].items()
    }
    THRESHOLD_MAXIMUMS = {
        str(name): float(value)
        for name, value in config["thresholds"]["maximums"].items()
    }
    EMBEDDING_URL = args.embedding_url.rstrip("/")
    QDRANT_URL = args.qdrant_url.rstrip("/")
    QDRANT_ALIAS = args.qdrant_alias
    NEO4J_URL = args.neo4j_url.rstrip("/")
    NEO4J_DATABASE = args.neo4j_database
    HTTP_TIMEOUT = args.http_timeout

    connection = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        metadata = dict(connection.execute("SELECT key,value FROM metadata"))
        EMBEDDING_PROFILE = json.loads(metadata["embedding_profile"])
        EMBEDDING_MODEL = args.embedding_model or str(EMBEDDING_PROFILE["model"])
        EMBEDDING_PROFILE["model"] = EMBEDDING_MODEL
        EMBEDDINGS = JsonHttpClient(
            EMBEDDING_URL,
            headers=client_headers("AOA_KAG_EMBEDDING_API_KEY"),
            timeout=HTTP_TIMEOUT,
        )
        QDRANT = JsonHttpClient(
            QDRANT_URL,
            headers=client_headers("AOA_KAG_QDRANT_API_KEY"),
            timeout=HTTP_TIMEOUT,
        )
        GRAPH = graph.Neo4jProjection(
            JsonHttpClient(
                NEO4J_URL,
                headers=neo4j_headers(),
                timeout=HTTP_TIMEOUT,
            ),
            NEO4J_DATABASE,
        )
        GRAPH_OWNER_SLICE_STATE = graph.read_owner_slice_state(
            STACK_ROOT / "Knowledge/kag/repo-self/graph/owner-slices.json"
        )
        report = evaluate(
            connection,
            config_digest=hashlib.sha256(config_path.read_bytes()).hexdigest(),
        )
    finally:
        connection.close()

    output: Path | None = None
    if not args.check:
        projection = report["bundle_identity"]["projection_digest"]
        output = (
            STACK_ROOT
            / "Knowledge/kag/repo-self/receipts"
            / projection
            / "retrieval-eval.json"
        )
        write_json_atomic(output, report)
        current_path = STACK_ROOT / "Knowledge/kag/repo-self/current.json"
        current = json.loads(current_path.read_text(encoding="utf-8"))
        current_projection = current.get("projection_identity", {}).get(
            "content_digest"
        )
        if current_projection != projection:
            raise RuntimeError(
                "current runtime projection changed during retrieval eval"
            )
        current.setdefault("targets", {})["retrieval_eval"] = {
            "status": report["status"],
            "receipt": str(output),
            "completed_at": report["completed_at"],
            "result": {
                "summaries": report["summaries"],
                "graph_recall_advantage": report["graph_recall_advantage"],
            },
        }
        write_json_atomic(current_path, current)

    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(output) if output else None,
                "summaries": report["summaries"],
                "thresholds": report["thresholds"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
