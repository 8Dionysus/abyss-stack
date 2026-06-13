from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from pathlib import Path
import socket
import time
from typing import Any
from urllib import error, request
from urllib.parse import urlsplit, urlunsplit
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


APP_VERSION = "0.1.0"
CONFIG_ROOT = Path(os.getenv("AOA_RAG_CONFIG_ROOT", "/app/config/rag"))
SOURCES_PATH = CONFIG_ROOT / "sources.json"
AGENTIC_GRAPH_PATH = CONFIG_ROOT / "agentic-graph.v1.json"
DAG_JOBS_PATH = CONFIG_ROOT / "dag-jobs.v1.json"

QDRANT_URL = os.getenv("AOA_RAG_QDRANT_URL", "http://qdrant:6333").rstrip("/")
LANGCHAIN_URL = os.getenv("AOA_RAG_LANGCHAIN_URL", "http://langchain-api:5401").rstrip("/")
ROUTE_API_URL = os.getenv("AOA_RAG_ROUTE_API_URL", "http://route-api:5402").rstrip("/")
RERANK_URL = os.getenv("AOA_RAG_RERANK_URL", "http://rerank-api:5405").rstrip("/")
POSTGRES_HOST = os.getenv("AOA_RAG_POSTGRES_HOST") or os.getenv("DB_POSTGRESDB_HOST") or "postgres"
POSTGRES_PORT = int(os.getenv("AOA_RAG_POSTGRES_PORT") or os.getenv("DB_POSTGRESDB_PORT") or "5432")
POSTGRES_DB = os.getenv("AOA_RAG_POSTGRES_DB") or os.getenv("DB_POSTGRESDB_DATABASE") or os.getenv("POSTGRES_DB") or "postgres"
POSTGRES_USER = os.getenv("AOA_RAG_POSTGRES_USER") or os.getenv("DB_POSTGRESDB_USER") or os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("AOA_RAG_POSTGRES_PASSWORD") or os.getenv("DB_POSTGRESDB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
NEO4J_URI = os.getenv("AOA_RAG_NEO4J_URI", "bolt://neo4j:7687")
NEO4J_DATABASE = os.getenv("AOA_RAG_NEO4J_DATABASE", "neo4j")
COLLECTION = os.getenv("AOA_RAG_COLLECTION", "abyss_stack_rag_chunks_v1")
VECTOR_SIZE = int(os.getenv("AOA_RAG_VECTOR_SIZE", "1024"))
MAX_CHUNK_CHARS = int(os.getenv("AOA_RAG_MAX_CHUNK_CHARS", "1800"))
CHUNK_OVERLAP_CHARS = int(os.getenv("AOA_RAG_CHUNK_OVERLAP_CHARS", "180"))
EMBED_BATCH_SIZE = int(os.getenv("AOA_RAG_EMBED_BATCH_SIZE", "8"))
DEFAULT_TOP_K = int(os.getenv("AOA_RAG_DEFAULT_TOP_K", "6"))
HTTP_TIMEOUT = float(os.getenv("AOA_RAG_HTTP_TIMEOUT_S", "45"))


def split_neo4j_auth(raw: str | None) -> tuple[str | None, str | None]:
    if not raw or raw.lower() == "none" or "/" not in raw:
        return None, None
    user, password = raw.split("/", 1)
    return (user or None, password or None)


def safe_url_without_userinfo(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return None
    if not parsed.netloc:
        return None if "@" in raw else raw
    host = parsed.hostname
    if not host:
        return None
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port is not None:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))


_NEO4J_AUTH_USER, _NEO4J_AUTH_PASSWORD = split_neo4j_auth(os.getenv("NEO4J_AUTH"))
NEO4J_USER = os.getenv("AOA_RAG_NEO4J_USER") or _NEO4J_AUTH_USER
NEO4J_PASSWORD = os.getenv("AOA_RAG_NEO4J_PASSWORD") or _NEO4J_AUTH_PASSWORD


def validate_chunk_settings(max_chunk_chars: int, overlap_chars: int) -> None:
    if max_chunk_chars <= 0:
        raise RuntimeError("AOA_RAG_MAX_CHUNK_CHARS must be greater than 0")
    if overlap_chars < 0:
        raise RuntimeError("AOA_RAG_CHUNK_OVERLAP_CHARS must be greater than or equal to 0")
    if overlap_chars >= max_chunk_chars:
        raise RuntimeError("AOA_RAG_CHUNK_OVERLAP_CHARS must be less than AOA_RAG_MAX_CHUNK_CHARS")


validate_chunk_settings(MAX_CHUNK_CHARS, CHUNK_OVERLAP_CHARS)

app = FastAPI(title="Abyss Stack RAG API", version=APP_VERSION)


class IngestSourceRequest(BaseModel):
    source_id: str
    limit_files: int | None = Field(default=None, ge=1, le=2000)
    dry_run: bool = False


class RetrieveRequest(BaseModel):
    query: str
    collection: str | None = None
    source_id: str | None = None
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=50)
    rerank: bool = False


class AnswerRequest(RetrieveRequest):
    max_tokens: int = Field(default=512, ge=64, le=4096)
    temperature: float = Field(default=0.2, ge=0.0, le=1.5)
    abstain_threshold: float = Field(default=0.18, ge=0.0, le=1.0)


def read_json(path: Path, fallback: Any) -> Any:
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"invalid_json:{path.name}:{exc}") from exc


def http_json(method: str, url: str, payload: Any | None = None, timeout: float = HTTP_TIMEOUT) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=exc.code, detail=f"upstream_http_error:{url}:{body}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"upstream_error:{url}:{type(exc).__name__}:{exc}") from exc


def safe_http_json(method: str, url: str, payload: Any | None = None, timeout: float = HTTP_TIMEOUT) -> dict[str, Any]:
    started = time.monotonic()
    try:
        data = http_json(method, url, payload, timeout)
        return {
            "ok": True,
            "url": url,
            "elapsed_ms": round((time.monotonic() - started) * 1000.0, 1),
            "data": data,
        }
    except HTTPException as exc:
        return {
            "ok": False,
            "url": url,
            "elapsed_ms": round((time.monotonic() - started) * 1000.0, 1),
            "error": str(exc.detail),
        }


def tcp_ready(host: str, port: int, timeout: float = 1.5) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {
                "ok": True,
                "host": host,
                "port": port,
                "elapsed_ms": round((time.monotonic() - started) * 1000.0, 1),
            }
    except OSError as exc:
        return {
            "ok": False,
            "host": host,
            "port": port,
            "elapsed_ms": round((time.monotonic() - started) * 1000.0, 1),
            "error": str(exc),
        }


def postgres_semantic_inventory() -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat()
    tcp = tcp_ready(POSTGRES_HOST, POSTGRES_PORT)
    result: dict[str, Any] = {
        "ok": False,
        "generated_at": generated_at,
        "host": POSTGRES_HOST,
        "port": POSTGRES_PORT,
        "database": POSTGRES_DB,
        "tcp_ready": tcp.get("ok"),
        "schema_inventory_present": False,
        "schemas": [],
        "relations": [],
        "relation_count": 0,
        "freshness": {
            "inventory_generated_at": generated_at,
            "postmaster_start_time": None,
            "database_now": None,
        },
        "error": tcp.get("error"),
        "redaction": {
            "raw_rows_stored": False,
            "row_payloads_included": False,
            "credentials_included": False,
            "connection_string_included": False,
        },
    }
    if not tcp.get("ok"):
        return result
    if not POSTGRES_USER or not POSTGRES_PASSWORD:
        result["error"] = "postgres_credentials_not_configured_for_inventory"
        return result
    try:
        import psycopg
    except Exception as exc:
        result["error"] = f"psycopg_unavailable:{type(exc).__name__}:{exc}"
        return result

    try:
        with psycopg.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=3,
        ) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT schema_name
                    FROM information_schema.schemata
                    WHERE schema_name NOT IN ('information_schema', 'pg_catalog')
                      AND schema_name NOT LIKE 'pg_toast%'
                      AND schema_name NOT LIKE 'pg_temp_%'
                      AND schema_name NOT LIKE 'pg_toast_temp_%'
                    ORDER BY schema_name
                    LIMIT 128
                    """
                )
                schemas = [str(row[0]) for row in cur.fetchall()]
                cur.execute(
                    """
                    SELECT table_schema, table_name, table_type
                    FROM information_schema.tables
                    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
                      AND table_schema NOT LIKE 'pg_toast%'
                      AND table_schema NOT LIKE 'pg_temp_%'
                      AND table_schema NOT LIKE 'pg_toast_temp_%'
                    ORDER BY table_schema, table_name
                    LIMIT 512
                    """
                )
                relations = [
                    {"schema": str(row[0]), "name": str(row[1]), "type": str(row[2])}
                    for row in cur.fetchall()
                ]
                cur.execute("SELECT now()::text, pg_postmaster_start_time()::text")
                freshness_row = cur.fetchone()
        result.update(
            {
                "ok": True,
                "schema_inventory_present": True,
                "schemas": schemas,
                "relations": relations,
                "relation_count": len(relations),
                "freshness": {
                    "inventory_generated_at": generated_at,
                    "database_now": str(freshness_row[0]) if freshness_row else None,
                    "postmaster_start_time": str(freshness_row[1]) if freshness_row else None,
                },
                "error": None,
            }
        )
    except Exception as exc:
        result["error"] = f"postgres_inventory_error:{type(exc).__name__}:{exc}"
    return result


def neo4j_semantic_inventory() -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat()
    result: dict[str, Any] = {
        "ok": False,
        "generated_at": generated_at,
        "uri": safe_url_without_userinfo(NEO4J_URI),
        "database": NEO4J_DATABASE,
        "graph_inventory_present": False,
        "labels": [],
        "relationship_types": [],
        "node_count": None,
        "relationship_count": None,
        "freshness": {
            "inventory_generated_at": generated_at,
            "database_now": None,
        },
        "error": None,
        "redaction": {
            "raw_graph_properties_stored": False,
            "node_properties_included": False,
            "relationship_properties_included": False,
            "credentials_included": False,
            "connection_string_included": False,
            "uri_userinfo_redacted": True,
        },
    }
    if not NEO4J_USER or not NEO4J_PASSWORD:
        result["error"] = "neo4j_credentials_not_configured_for_inventory"
        return result
    try:
        from neo4j import GraphDatabase
    except Exception as exc:
        result["error"] = f"neo4j_driver_unavailable:{type(exc).__name__}:{exc}"
        return result

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            labels = [
                str(record["label"])
                for record in session.run("CALL db.labels() YIELD label RETURN label ORDER BY label LIMIT 256")
            ]
            relationship_types = [
                str(record["relationshipType"])
                for record in session.run(
                    "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType LIMIT 256"
                )
            ]
            node_count_record = session.run("MATCH (n) RETURN count(n) AS count").single()
            relationship_count_record = session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()
            now_record = session.run("RETURN datetime() AS now").single()
        result.update(
            {
                "ok": True,
                "graph_inventory_present": True,
                "labels": labels,
                "relationship_types": relationship_types,
                "node_count": int(node_count_record["count"]) if node_count_record else 0,
                "relationship_count": int(relationship_count_record["count"]) if relationship_count_record else 0,
                "freshness": {
                    "inventory_generated_at": generated_at,
                    "database_now": str(now_record["now"]) if now_record else None,
                },
                "error": None,
            }
        )
    except Exception as exc:
        result["error"] = f"neo4j_inventory_error:{type(exc).__name__}:{exc}"
    finally:
        driver.close()
    return result


def semantic_inventory_payload() -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat()
    qdrant_collections = safe_http_json("GET", f"{QDRANT_URL}/collections", timeout=5)
    route_health = safe_http_json("GET", f"{ROUTE_API_URL}/health", timeout=5)
    route_openapi = safe_http_json("GET", f"{ROUTE_API_URL}/openapi.json", timeout=5)
    postgres = postgres_semantic_inventory()
    neo4j = neo4j_semantic_inventory()
    sources = sources_config()
    graph = read_json(AGENTIC_GRAPH_PATH, {"schema": "abyss_stack_agentic_rag_graph_v1", "nodes": [], "edges": []})
    graph_nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    graph_edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    inventory_complete = bool(postgres.get("schema_inventory_present") and neo4j.get("graph_inventory_present"))
    source_entries = sources.get("sources") if isinstance(sources.get("sources"), list) else []
    return {
        "ok": inventory_complete,
        "schema": "abyss_stack_semantic_memory_space_inventory_v1",
        "generated_at": generated_at,
        "postgres": postgres,
        "neo4j": neo4j,
        "rag": {
            "collection": COLLECTION,
            "vector_size": VECTOR_SIZE,
            "qdrant_collections_readable": bool(qdrant_collections.get("ok")),
            "source_count": len(source_entries),
            "source_ids": [str(item.get("id")) for item in source_entries if isinstance(item, dict) and item.get("id")][:128],
            "agentic_graph": {
                "schema": graph.get("schema"),
                "node_count": len(graph_nodes),
                "edge_count": len(graph_edges),
            },
        },
        "route_api": {
            "health_readable": bool(route_health.get("ok")),
            "openapi_readable": bool(route_openapi.get("ok")),
        },
        "semantic_inventory": {
            "stack_owned_postgres_schema_inventory_present": bool(postgres.get("schema_inventory_present")),
            "stack_owned_neo4j_graph_inventory_present": bool(neo4j.get("graph_inventory_present")),
            "inventory_complete": inventory_complete,
        },
        "evidence_refs": [
            {"url": qdrant_collections.get("url"), "ok": qdrant_collections.get("ok"), "probe": "qdrant_collections"},
            {"url": route_health.get("url"), "ok": route_health.get("ok"), "probe": "route_api_health"},
            {"url": route_openapi.get("url"), "ok": route_openapi.get("ok"), "probe": "route_api_openapi"},
            {"url": f"tcp://{POSTGRES_HOST}:{POSTGRES_PORT}", "ok": postgres.get("tcp_ready"), "probe": "postgres_tcp_ready"},
            {
                "url": safe_url_without_userinfo(NEO4J_URI),
                "ok": neo4j.get("graph_inventory_present"),
                "probe": "neo4j_bolt_inventory",
            },
            {"path": str(SOURCES_PATH), "probe": "rag_sources_config"},
            {"path": str(AGENTIC_GRAPH_PATH), "probe": "rag_agentic_graph_config"},
        ],
        "redaction": {
            "raw_database_rows_stored": False,
            "raw_graph_properties_stored": False,
            "raw_source_documents_stored": False,
            "raw_credentials_stored": False,
            "connection_strings_with_credentials_stored": False,
        },
        "policy": {
            "read_only": True,
            "stack_owned": True,
            "host_layer_mutates_stack": False,
            "writes_project_roots": False,
            "raw_private_content": False,
        },
    }


def sources_config() -> dict[str, Any]:
    config = read_json(SOURCES_PATH, {"schema": "abyss_stack_rag_sources_v1", "sources": []})
    if not isinstance(config, dict):
        raise HTTPException(status_code=500, detail="rag sources config must be an object")
    return config


def find_source(source_id: str) -> dict[str, Any]:
    for item in sources_config().get("sources", []):
        if isinstance(item, dict) and item.get("id") == source_id:
            return item
    raise HTTPException(status_code=404, detail=f"unknown_source:{source_id}")


def iter_source_files(source: dict[str, Any], limit: int | None = None) -> list[Path]:
    root = Path(source["root"]).resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"source_root_missing:{root}")

    include_globs = source.get("include_globs") or ["**/*.md"]
    exclude_globs = source.get("exclude_globs") or []
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if not any(fnmatch.fnmatch(rel, pattern) for pattern in include_globs):
            continue
        if any(fnmatch.fnmatch(rel, pattern) for pattern in exclude_globs):
            continue
        files.append(path)
        if limit is not None and len(files) >= limit:
            break
    return files


def chunk_text(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in normalized.split("\n\n") if block.strip()]
    chunks: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = block
        while len(current) > MAX_CHUNK_CHARS:
            head = current[:MAX_CHUNK_CHARS]
            chunks.append(head)
            current = current[MAX_CHUNK_CHARS - CHUNK_OVERLAP_CHARS :]
    if current:
        chunks.append(current)
    return chunks


def point_id(source_id: str, rel_path: str, chunk_index: int, text: str) -> str:
    digest = hashlib.sha256(f"{source_id}\n{rel_path}\n{chunk_index}\n{text}".encode("utf-8")).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def embed_texts(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = http_json("POST", f"{LANGCHAIN_URL}/embeddings", {"input": batch})
        data = response.get("data")
        if not isinstance(data, list):
            raise HTTPException(status_code=502, detail="embedding_response_missing_data")
        for item in data:
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or len(vector) != VECTOR_SIZE:
                raise HTTPException(status_code=502, detail="embedding_vector_shape_mismatch")
            vectors.append(vector)
    return vectors


def ensure_collection(collection: str) -> None:
    try:
        http_json("GET", f"{QDRANT_URL}/collections/{collection}")
        return
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    payload = {"vectors": {"size": VECTOR_SIZE, "distance": "Cosine"}}
    http_json("PUT", f"{QDRANT_URL}/collections/{collection}", payload)


def upsert_points(collection: str, points: list[dict[str, Any]]) -> None:
    if not points:
        return
    http_json("PUT", f"{QDRANT_URL}/collections/{collection}/points?wait=true", {"points": points})


def qdrant_search(collection: str, vector: list[float], top_k: int, source_id: str | None) -> list[dict[str, Any]]:
    payload_filter = None
    if source_id:
        payload_filter = {"must": [{"key": "source_id", "match": {"value": source_id}}]}
    payload: dict[str, Any] = {
        "vector": vector,
        "limit": top_k,
        "with_payload": True,
        "with_vector": False,
    }
    if payload_filter:
        payload["filter"] = payload_filter
    response = http_json("POST", f"{QDRANT_URL}/collections/{collection}/points/search", payload)
    result = response.get("result")
    if not isinstance(result, list):
        raise HTTPException(status_code=502, detail="qdrant_search_missing_result")
    return result


def rerank_hits(query: str, hits: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    documents = []
    for hit in hits:
        payload = hit.get("payload") or {}
        documents.append({"text": payload.get("text", ""), "metadata": payload})
    response = http_json(
        "POST",
        f"{RERANK_URL}/v3/rerank",
        {"query": query, "documents": documents, "top_n": top_k, "return_documents": True},
        timeout=max(HTTP_TIMEOUT, 180),
    )
    ranked = []
    for item in response.get("results", []):
        document = item.get("document") or {}
        metadata = document.get("metadata") or {}
        ranked.append(
            {
                "score": item.get("relevance_score"),
                "text": document.get("text", ""),
                "payload": metadata,
                "rerank": item,
            }
        )
    return ranked


def normalize_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for hit in hits:
        payload = hit.get("payload") or {}
        normalized.append(
            {
                "score": hit.get("score"),
                "id": hit.get("id"),
                "text": payload.get("text", ""),
                "payload": payload,
            }
        )
    return normalized


def build_context(hits: list[dict[str, Any]]) -> str:
    lines = []
    for index, hit in enumerate(hits, start=1):
        payload = hit.get("payload") or {}
        cite = payload.get("source_ref") or payload.get("path") or payload.get("source_id") or f"hit-{index}"
        text = (hit.get("text") or "").strip()
        lines.append(f"[{index}] {cite}\n{text}")
    return "\n\n".join(lines)


@app.get("/health")
def health() -> dict[str, Any]:
    checks: dict[str, Any] = {
        "qdrant": http_json("GET", f"{QDRANT_URL}/collections"),
        "langchain": http_json("GET", f"{LANGCHAIN_URL}/health"),
    }
    try:
        checks["route_api"] = http_json("GET", f"{ROUTE_API_URL}/health")
    except HTTPException as exc:
        checks["route_api"] = {"ok": False, "detail": exc.detail}
    try:
        checks["rerank_api"] = http_json("GET", f"{RERANK_URL}/health")
    except HTTPException as exc:
        checks["rerank_api"] = {"ok": False, "detail": exc.detail}
    return {
        "ok": True,
        "service": "rag-api",
        "version": APP_VERSION,
        "collection": COLLECTION,
        "vector_size": VECTOR_SIZE,
        "sources_config_exists": SOURCES_PATH.is_file(),
        "checks": checks,
    }


@app.get("/sources")
def sources() -> dict[str, Any]:
    return {"ok": True, "data": sources_config()}


@app.get("/dag/jobs")
def dag_jobs() -> dict[str, Any]:
    return {"ok": True, "data": read_json(DAG_JOBS_PATH, {"schema": "abyss_stack_rag_dag_jobs_v1", "jobs": []})}


@app.get("/agentic-rag/graph")
def agentic_graph() -> dict[str, Any]:
    return {"ok": True, "data": read_json(AGENTIC_GRAPH_PATH, {"schema": "abyss_stack_agentic_rag_graph_v1", "nodes": []})}


@app.get("/semantic-inventory")
def semantic_inventory() -> dict[str, Any]:
    return semantic_inventory_payload()


@app.get("/collections")
def collections() -> dict[str, Any]:
    return {"ok": True, "data": http_json("GET", f"{QDRANT_URL}/collections")}


@app.post("/ingest/source")
def ingest_source(req: IngestSourceRequest) -> dict[str, Any]:
    source = find_source(req.source_id)
    files = iter_source_files(source, req.limit_files)
    root = Path(source["root"]).resolve()
    collection = source.get("collection") or COLLECTION
    planned_chunks = 0
    points: list[dict[str, Any]] = []
    started = time.time()

    for path in files:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        chunks = chunk_text(text)
        planned_chunks += len(chunks)
        if req.dry_run:
            continue
        vectors = embed_texts(chunks)
        for index, chunk in enumerate(chunks):
            payload = {
                "schema": "abyss_stack_rag_chunk_v1",
                "source_id": req.source_id,
                "source_owner": source.get("owner", "unknown"),
                "source_ref": f"{req.source_id}:{rel}#chunk-{index}",
                "path": rel,
                "chunk_index": index,
                "text": chunk,
                "text_sha256": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
            }
            points.append({"id": point_id(req.source_id, rel, index, chunk), "vector": vectors[index], "payload": payload})
            if len(points) >= 64:
                ensure_collection(collection)
                upsert_points(collection, points)
                points = []

    if not req.dry_run:
        ensure_collection(collection)
        upsert_points(collection, points)

    return {
        "ok": True,
        "source_id": req.source_id,
        "collection": collection,
        "dry_run": req.dry_run,
        "files": len(files),
        "chunks": planned_chunks,
        "elapsed_sec": round(time.time() - started, 3),
    }


@app.post("/retrieve")
def retrieve(req: RetrieveRequest) -> dict[str, Any]:
    vector = embed_texts([req.query])[0]
    collection = req.collection or COLLECTION
    hits = normalize_hits(qdrant_search(collection, vector, req.top_k, req.source_id))
    if req.rerank and hits:
        hits = rerank_hits(req.query, hits, req.top_k)
    return {"ok": True, "query": req.query, "collection": collection, "hits": hits, "rerank": req.rerank}


@app.post("/answer")
def answer(req: AnswerRequest) -> dict[str, Any]:
    retrieval = retrieve(req)
    return answer_from_retrieval(req, retrieval)


def answer_from_retrieval(req: AnswerRequest, retrieval: dict[str, Any]) -> dict[str, Any]:
    hits = retrieval["hits"]
    if not hits or float(hits[0].get("score") or 0.0) < req.abstain_threshold:
        return {"ok": True, "abstained": True, "reason": "insufficient_retrieval_score", "retrieval": retrieval}
    context = build_context(hits)
    prompt = (
        "Answer using only the cited context. If the context is insufficient, say so.\n\n"
        f"Question:\n{req.query}\n\nContext:\n{context}\n\nAnswer with citations like [1], [2]."
    )
    response = http_json(
        "POST",
        f"{LANGCHAIN_URL}/run",
        {"user_text": prompt, "temperature": req.temperature, "max_tokens": req.max_tokens},
        timeout=max(HTTP_TIMEOUT, 180),
    )
    return {
        "ok": True,
        "abstained": False,
        "answer": response,
        "retrieval": retrieval,
        "trace": {
            "nodes": ["embed_query", "qdrant_search", "optional_rerank", "grounded_answer"],
            "rerank": req.rerank,
        },
    }


@app.post("/agentic-rag/run")
def agentic_rag_run(req: AnswerRequest) -> dict[str, Any]:
    trace: list[dict[str, Any]] = []
    first = retrieve(req)
    trace.append({"node": "retrieve", "hits": len(first["hits"])})
    best_score = float(first["hits"][0].get("score") or 0.0) if first["hits"] else 0.0
    if best_score < req.abstain_threshold:
        rewrite = f"{req.query}\n\nFocus on exact source names, route contracts, service names, and cited docs."
        second_req = RetrieveRequest(
            query=rewrite,
            collection=req.collection,
            source_id=req.source_id,
            top_k=req.top_k,
            rerank=req.rerank,
        )
        second = retrieve(second_req)
        trace.append({"node": "rewrite_query", "reason": "low_score", "previous_best_score": best_score})
        trace.append({"node": "retrieve_after_rewrite", "hits": len(second["hits"])})
        if second["hits"]:
            first = second
    result = answer_from_retrieval(req, first)
    trace.append({"node": "answer", "abstained": result.get("abstained", False)})
    result["agentic_trace"] = trace
    return result
