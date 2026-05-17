from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib import error, request

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
COLLECTION = os.getenv("AOA_RAG_COLLECTION", "abyss_stack_rag_chunks_v1")
VECTOR_SIZE = int(os.getenv("AOA_RAG_VECTOR_SIZE", "1024"))
MAX_CHUNK_CHARS = int(os.getenv("AOA_RAG_MAX_CHUNK_CHARS", "1800"))
CHUNK_OVERLAP_CHARS = int(os.getenv("AOA_RAG_CHUNK_OVERLAP_CHARS", "180"))
EMBED_BATCH_SIZE = int(os.getenv("AOA_RAG_EMBED_BATCH_SIZE", "8"))
DEFAULT_TOP_K = int(os.getenv("AOA_RAG_DEFAULT_TOP_K", "6"))
HTTP_TIMEOUT = float(os.getenv("AOA_RAG_HTTP_TIMEOUT_S", "45"))


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
