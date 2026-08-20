#!/usr/bin/env python3
"""Execute the resident OVMS/Qdrant/Qwen3 semantic retrieval variant."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import resource
import shutil
import statistics
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SemanticRetrievalError(RuntimeError):
    """Raised when the frozen resident semantic run is not executable."""


class LocalHttpError(SemanticRetrievalError):
    """Bounded localhost API failure with its HTTP status preserved."""

    def __init__(self, status: int, url: str, detail: str) -> None:
        super().__init__(f"localhost API {status} for {url}: {detail}")
        self.status = status
        self.url = url


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
COLLECTION_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{7,95}$")
EMBEDDING_MODEL = "qwen3-embed-0.6b-int8-ov"
RERANK_MODEL = "qwen3-reranker-0.6b-int8-ov"
VECTOR_SIZE = 1024
TOP_K = 10
EMBED_BATCH_SIZE = 6
# The OVMS health route is socket-activated and may include the bounded
# admission wait plus the cold container/model startup window.
OVMS_COLD_START_TIMEOUT_S = 600


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SemanticRetrievalError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SemanticRetrievalError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _language_for_item(item_ref: str) -> str:
    if ".de-" in item_ref or ".de." in item_ref:
        return "de"
    return "ru"


def _validate_local_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in LOCAL_HOSTS:
        raise SemanticRetrievalError(f"restricted content route must stay on localhost: {url}")
    return url.rstrip("/")


def _http_json(
    method: str,
    url: str,
    payload: object | None = None,
    *,
    timeout: float = 240.0,
) -> dict[str, Any]:
    _validate_local_url(url)
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise LocalHttpError(exc.code, url, detail) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SemanticRetrievalError(f"localhost API request failed for {url}: {exc}") from exc
    if not raw:
        return {}
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SemanticRetrievalError(f"localhost API returned non-JSON for {url}") from exc
    if not isinstance(result, dict):
        raise SemanticRetrievalError(f"localhost API returned non-object JSON for {url}")
    return result


def _collection_info(qdrant_url: str, collection: str) -> dict[str, Any] | None:
    try:
        response = _http_json("GET", f"{qdrant_url}/collections/{collection}", timeout=30)
    except LocalHttpError as exc:
        if exc.status == 404:
            return None
        raise
    result = response.get("result")
    if not isinstance(result, dict):
        raise SemanticRetrievalError("Qdrant collection response has no result object")
    return result


def _create_collection(qdrant_url: str, collection: str) -> float:
    started = time.perf_counter()
    response = _http_json(
        "PUT",
        f"{qdrant_url}/collections/{collection}",
        {"vectors": {"size": VECTOR_SIZE, "distance": "Cosine"}},
        timeout=60,
    )
    if response.get("status") != "ok":
        raise SemanticRetrievalError(f"Qdrant collection creation failed: {response}")
    return time.perf_counter() - started


def _delete_collection(qdrant_url: str, collection: str) -> float:
    started = time.perf_counter()
    response = _http_json("DELETE", f"{qdrant_url}/collections/{collection}", timeout=60)
    if response.get("status") != "ok":
        raise SemanticRetrievalError(f"Qdrant collection deletion failed: {response}")
    return time.perf_counter() - started


def _point_id(sample_id: str, anchor_ref: str, text_sha256: str) -> str:
    digest = hashlib.sha256(f"{sample_id}\n{anchor_ref}\n{text_sha256}".encode("utf-8")).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def _upsert_points(qdrant_url: str, collection: str, points: list[dict[str, Any]]) -> float:
    started = time.perf_counter()
    response = _http_json(
        "PUT",
        f"{qdrant_url}/collections/{collection}/points?wait=true",
        {"points": points},
        timeout=180,
    )
    if response.get("status") != "ok":
        raise SemanticRetrievalError(f"Qdrant point upsert failed: {response}")
    return time.perf_counter() - started


def _container_fingerprint(name: str, source_path: str | None = None) -> dict[str, Any]:
    podman = shutil.which("podman")
    if podman is None:
        raise SemanticRetrievalError("podman is required to fingerprint resident services")
    completed = subprocess.run(
        (
            podman,
            "inspect",
            "--format",
            "{{.ImageName}}\n{{.Image}}\n{{.State.StartedAt}}",
            name,
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise SemanticRetrievalError(f"cannot inspect resident container {name}: {completed.stderr.strip()}")
    lines = completed.stdout.splitlines()
    if len(lines) != 3:
        raise SemanticRetrievalError(f"unexpected inspect output for resident container {name}")
    result: dict[str, Any] = {
        "container": name,
        "image_name": lines[0],
        "image_id": lines[1],
        "started_at": lines[2],
        "source_path": source_path,
        "source_sha256": None,
    }
    if source_path:
        source = subprocess.run(
            (podman, "exec", name, "sha256sum", source_path),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if source.returncode != 0:
            raise SemanticRetrievalError(
                f"cannot hash live service source {name}:{source_path}: {source.stderr.strip()}"
            )
        digest = source.stdout.split(maxsplit=1)[0]
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise SemanticRetrievalError(f"invalid live source digest for {name}:{source_path}")
        result["source_sha256"] = digest
    return result


def _model_artifact(
    model_id: str,
    config_path: Path,
    xml_path: Path,
    bin_path: Path,
    *,
    revision_metadata_path: Path | None = None,
) -> dict[str, Any]:
    for path in (config_path, xml_path, bin_path):
        if not path.is_file():
            raise SemanticRetrievalError(f"model artifact is missing: {path}")
    revision = None
    if revision_metadata_path and revision_metadata_path.is_file():
        first_line = revision_metadata_path.read_text(encoding="utf-8").splitlines()[0].strip()
        if re.fullmatch(r"[a-f0-9]{40,64}", first_line):
            revision = first_line
    return {
        "model_id": model_id,
        "source_revision": revision,
        "source_revision_status": "captured" if revision else "unavailable-file-digests-authoritative",
        "artifacts": [
            {"path": config_path.as_posix(), "bytes": config_path.stat().st_size, "sha256": _sha256_file(config_path)},
            {"path": xml_path.as_posix(), "bytes": xml_path.stat().st_size, "sha256": _sha256_file(xml_path)},
            {"path": bin_path.as_posix(), "bytes": bin_path.stat().st_size, "sha256": _sha256_file(bin_path)},
        ],
    }


def _load_passages(structure_run_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    structure_receipt = _load_json(structure_run_root / "run.receipt.json")
    if (
        structure_receipt.get("experiment_id") != "tos-structure-recovery-v1"
        or structure_receipt.get("variant") != "A"
        or structure_receipt.get("status") != "awaiting-manual-review"
    ):
        raise SemanticRetrievalError(
            "source structure run is not the preserved unpromoted Structure A packet"
        )
    passages: list[dict[str, Any]] = []
    for metadata_path in sorted((structure_run_root / "raw-output").glob("tos-sample-*.json")):
        metadata = _load_json(metadata_path)
        text_path = structure_run_root / str(metadata.get("native_text_ref"))
        if _sha256_file(text_path) != metadata.get("native_text_sha256"):
            raise SemanticRetrievalError(f"source structure output digest drift: {text_path}")
        text = text_path.read_text(encoding="utf-8")
        item_ref = str(metadata["item_ref"])
        unit = metadata["unit"]
        passages.append(
            {
                "sample_id": metadata["sample_id"],
                "source_anchor_ref": metadata["anchor_ref"],
                "item_ref": item_ref,
                "language": _language_for_item(item_ref),
                "unit": unit,
                "page_or_member": str(unit.get("page") or unit.get("container_member") or ""),
                "text": text,
                "text_sha256": metadata["native_text_sha256"],
            }
        )
    if len(passages) != 36:
        raise SemanticRetrievalError(f"expected 36 frozen passages, found {len(passages)}")
    return passages, structure_receipt


def _load_queries(
    query_plan_path: Path, query_content_path: Path
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    query_plan = _load_json(query_plan_path)
    query_content = _load_json(query_content_path)
    if query_plan.get("frozen_before_variant_outputs") is not True:
        raise SemanticRetrievalError("query plan was not frozen before outputs")
    if _sha256_file(query_content_path) != query_plan.get("query_content_sha256"):
        raise SemanticRetrievalError("local query content digest differs from tracked query plan")
    plan_queries = {
        query["query_id"]: query
        for query in query_plan.get("queries", [])
        if isinstance(query, dict) and isinstance(query.get("query_id"), str)
    }
    content_queries = {
        query["query_id"]: query
        for query in query_content.get("queries", [])
        if isinstance(query, dict) and isinstance(query.get("query_id"), str)
    }
    if set(plan_queries) != set(content_queries) or len(plan_queries) != 20:
        raise SemanticRetrievalError("tracked and local query sets do not contain the same 20 IDs")
    return plan_queries, content_queries


def _embed_passages(
    langchain_url: str, passages: list[dict[str, Any]]
) -> tuple[list[list[float]], dict[str, Any]]:
    vectors: list[list[float]] = []
    latencies_ms: list[float] = []
    providers: set[str] = set()
    models: set[str] = set()
    for start in range(0, len(passages), EMBED_BATCH_SIZE):
        batch = passages[start : start + EMBED_BATCH_SIZE]
        before = time.perf_counter()
        response = _http_json(
            "POST",
            f"{langchain_url}/embeddings",
            {"model": EMBEDDING_MODEL, "input": [passage["text"] for passage in batch]},
            timeout=240,
        )
        latencies_ms.append((time.perf_counter() - before) * 1000)
        provider = response.get("provider")
        model = response.get("model")
        if isinstance(provider, str):
            providers.add(provider)
        if isinstance(model, str):
            models.add(model)
        data = response.get("data")
        if not isinstance(data, list) or len(data) != len(batch):
            raise SemanticRetrievalError("embedding response batch shape mismatch")
        for item in sorted(data, key=lambda value: value.get("index", -1) if isinstance(value, dict) else -1):
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or len(vector) != VECTOR_SIZE:
                raise SemanticRetrievalError("embedding vector dimension mismatch")
            if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in vector):
                raise SemanticRetrievalError("embedding vector contains a non-finite value")
            if not any(float(value) != 0.0 for value in vector):
                raise SemanticRetrievalError("embedding vector has zero norm")
            vectors.append([float(value) for value in vector])
    if providers != {"ovms"} or models != {EMBEDDING_MODEL}:
        raise SemanticRetrievalError(
            f"unexpected embedding route: providers={sorted(providers)}, models={sorted(models)}"
        )
    return vectors, {
        "schema_version": "tos_resident_embedding_receipt_v1",
        "provider": "ovms",
        "model": EMBEDDING_MODEL,
        "vector_size": VECTOR_SIZE,
        "input_count": len(passages),
        "batch_size": EMBED_BATCH_SIZE,
        "batch_count": len(latencies_ms),
        "batch_latencies_ms": latencies_ms,
        "total_embedding_seconds": sum(latencies_ms) / 1000,
        "input_policy": "raw nonempty Structure A passage text; no query-derived labels or accepted-gold fields",
        "authority_boundary": "vectors are replaceable local projections of unaccepted source text",
    }


def _points(passages: list[dict[str, Any]], vectors: list[list[float]]) -> list[dict[str, Any]]:
    if len(passages) != len(vectors):
        raise SemanticRetrievalError("passage/vector count mismatch")
    return [
        {
            "id": _point_id(passage["sample_id"], passage["source_anchor_ref"], passage["text_sha256"]),
            "vector": vector,
            "payload": passage,
        }
        for passage, vector in zip(passages, vectors, strict=True)
    ]


def _retrieve(rag_url: str, collection: str, query: str, *, rerank: bool) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = _http_json(
        "POST",
        f"{rag_url}/retrieve",
        {"query": query, "collection": collection, "top_k": TOP_K, "rerank": rerank},
        timeout=300,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    if response.get("ok") is not True or response.get("collection") != collection:
        raise SemanticRetrievalError(f"unexpected RAG retrieval response: {response}")
    hits = response.get("hits")
    if not isinstance(hits, list):
        raise SemanticRetrievalError("RAG retrieval response has no hit list")
    return response, elapsed_ms


def _validate_hits(
    hits: list[dict[str, Any]], passage_by_anchor: dict[str, dict[str, Any]]
) -> list[str]:
    anchors: list[str] = []
    for hit in hits:
        if not isinstance(hit, dict):
            raise SemanticRetrievalError("retrieval hit is not an object")
        payload = hit.get("payload")
        if not isinstance(payload, dict):
            raise SemanticRetrievalError("retrieval hit has no source payload")
        anchor = payload.get("source_anchor_ref")
        if not isinstance(anchor, str) or anchor not in passage_by_anchor:
            raise SemanticRetrievalError(f"retrieval hit has unresolved source anchor: {anchor}")
        source = passage_by_anchor[anchor]
        text = hit.get("text")
        if not isinstance(text, str) or _sha256_text(text) != source["text_sha256"]:
            raise SemanticRetrievalError(f"retrieval text does not resolve to source digest: {anchor}")
        if payload.get("text_sha256") != source["text_sha256"]:
            raise SemanticRetrievalError(f"retrieval payload digest drift: {anchor}")
        anchors.append(anchor)
    return anchors


def _expected_ranks(expected: list[str], anchors: list[str]) -> dict[str, int]:
    return {anchor: anchors.index(anchor) + 1 for anchor in expected if anchor in anchors}


def _snapshot_size(qdrant_url: str, collection: str) -> dict[str, Any]:
    response = _http_json("POST", f"{qdrant_url}/collections/{collection}/snapshots", timeout=180)
    result = response.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("name"), str):
        raise SemanticRetrievalError(f"Qdrant snapshot creation failed: {response}")
    name = result["name"]
    deletion = _http_json(
        "DELETE",
        f"{qdrant_url}/collections/{collection}/snapshots/{urllib.parse.quote(name, safe='')}",
        timeout=60,
    )
    snapshots = _http_json("GET", f"{qdrant_url}/collections/{collection}/snapshots", timeout=60)
    remaining = snapshots.get("result")
    if deletion.get("status") != "ok" or not isinstance(remaining, list):
        raise SemanticRetrievalError("Qdrant snapshot deletion proof failed")
    if any(isinstance(item, dict) and item.get("name") == name for item in remaining):
        raise SemanticRetrievalError("Qdrant snapshot still exists after deletion")
    return {
        "name": name,
        "size_bytes": result.get("size"),
        "checksum": result.get("checksum"),
        "creation_time": result.get("creation_time"),
        "deleted_after_measurement": True,
    }


def execute_semantic_retrieval(
    run_root: Path,
    structure_run_root: Path,
    query_plan_path: Path,
    query_content_path: Path,
    *,
    collection: str,
    invocation: list[str],
    langchain_url: str = "http://127.0.0.1:5403",
    rag_url: str = "http://127.0.0.1:5406",
    rerank_url: str = "http://127.0.0.1:5405",
    qdrant_url: str = "http://127.0.0.1:6333",
    ovms_url: str = "http://127.0.0.1:8200",
    ovms_config_path: Path = Path("/srv/AbyssOS/abyss-stack/Configs/ovms/config.json"),
    embedding_model_root: Path = Path(
        "/srv/AbyssOS/abyss-stack/Models/ovms/OpenVINO/Qwen3-Embedding-0.6B-int8-ov"
    ),
    rerank_model_root: Path = Path("/srv/abyss-machine/cache/ai/qwen3-reranker-0.6b-int8-ov"),
) -> dict[str, Any]:
    """Execute Retrieval B while keeping every result mechanically source anchored."""

    run_root = run_root.resolve()
    structure_run_root = structure_run_root.resolve()
    query_plan_path = query_plan_path.resolve()
    query_content_path = query_content_path.resolve()
    langchain_url = _validate_local_url(langchain_url)
    rag_url = _validate_local_url(rag_url)
    rerank_url = _validate_local_url(rerank_url)
    qdrant_url = _validate_local_url(qdrant_url)
    ovms_url = _validate_local_url(ovms_url)
    if not COLLECTION_RE.fullmatch(collection):
        raise SemanticRetrievalError("collection must be a unique lowercase laboratory identifier")

    receipt_path = run_root / "run.receipt.json"
    receipt = _load_json(receipt_path)
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if receipt.get("experiment_id") != "tos-retrieval-foundation-v1" or receipt.get("variant") != "B":
        raise SemanticRetrievalError("semantic runner requires prepared Retrieval B")
    if receipt.get("status") != "prepared" or preflight.get("decision") != "ready":
        raise SemanticRetrievalError("run must be prepared from a ready preflight")
    if experiment.get("family") != "retrieval":
        raise SemanticRetrievalError("experiment specification is not retrieval")

    passages, structure_receipt = _load_passages(structure_run_root)
    plan_queries, content_queries = _load_queries(query_plan_path, query_content_path)
    nonempty_passages = [passage for passage in passages if passage["text"].strip()]
    if len(nonempty_passages) != 24:
        raise SemanticRetrievalError(
            f"expected 24 nonempty passages and 12 preserved coverage gaps, found {len(nonempty_passages)}"
        )
    passage_by_anchor = {passage["source_anchor_ref"]: passage for passage in nonempty_passages}

    started_at = _utc_now()
    run_started = time.perf_counter()
    receipt["status"] = "running"
    receipt["started_at_utc"] = started_at
    _write_json(receipt_path, receipt)
    collection_created = False
    try:
        services_before = {
            "langchain": _http_json("GET", f"{langchain_url}/health", timeout=30),
            "rag": _http_json("GET", f"{rag_url}/health", timeout=30),
            "rerank": _http_json("GET", f"{rerank_url}/health", timeout=30),
            "qdrant_collections": _http_json("GET", f"{qdrant_url}/collections", timeout=30),
            "ovms_live": _http_json(
                "GET",
                f"{ovms_url}/v2/health/live",
                timeout=OVMS_COLD_START_TIMEOUT_S,
            ),
        }
        if services_before["langchain"].get("embeddings_provider") != "ovms":
            raise SemanticRetrievalError("live langchain embedding provider is not OVMS")
        if services_before["rerank"].get("model") != RERANK_MODEL:
            raise SemanticRetrievalError("live reranker model does not match frozen variant")
        if services_before["rerank"].get("fake_mode") is not False:
            raise SemanticRetrievalError("live reranker is not a real-model route")
        if services_before["rag"].get("vector_size") != VECTOR_SIZE:
            raise SemanticRetrievalError("live RAG vector size does not match frozen variant")
        if _collection_info(qdrant_url, collection) is not None:
            raise SemanticRetrievalError(f"isolated collection already exists: {collection}")

        container_receipt = {
            "langchain-api": _container_fingerprint("langchain-api", "/app/app/main.py"),
            "rag-api": _container_fingerprint("rag-api", "/app/app/main.py"),
            "rerank-api": _container_fingerprint("rerank-api", "/app/app/main.py"),
            "qdrant": _container_fingerprint("abyss_qdrant_1"),
            "ovms": _container_fingerprint("ovms"),
        }
        model_receipt = {
            "embedding": _model_artifact(
                EMBEDDING_MODEL,
                embedding_model_root / "config.json",
                embedding_model_root / "openvino_model.xml",
                embedding_model_root / "openvino_model.bin",
            ),
            "reranker": _model_artifact(
                RERANK_MODEL,
                rerank_model_root / "config.json",
                rerank_model_root / "openvino_model.xml",
                rerank_model_root / "openvino_model.bin",
                revision_metadata_path=(
                    rerank_model_root / ".cache/huggingface/download/config.json.metadata"
                ),
            ),
            "ovms_config": {
                "path": ovms_config_path.as_posix(),
                "bytes": ovms_config_path.stat().st_size,
                "sha256": _sha256_file(ovms_config_path),
            },
        }

        vectors, embedding_receipt = _embed_passages(langchain_url, nonempty_passages)
        points = _points(nonempty_passages, vectors)
        first_create_seconds = _create_collection(qdrant_url, collection)
        collection_created = True
        first_upsert_seconds = _upsert_points(qdrant_url, collection, points)
        first_info = _collection_info(qdrant_url, collection)
        if first_info is None or first_info.get("points_count") != len(points):
            raise SemanticRetrievalError("first Qdrant materialization point count mismatch")

        delete_seconds = _delete_collection(qdrant_url, collection)
        collection_created = False
        absent_after_delete = _collection_info(qdrant_url, collection) is None
        if not absent_after_delete:
            raise SemanticRetrievalError("collection still exists after deletion proof")

        rebuild_create_seconds = _create_collection(qdrant_url, collection)
        collection_created = True
        rebuild_upsert_seconds = _upsert_points(qdrant_url, collection, points)
        rebuilt_info = _collection_info(qdrant_url, collection)
        if rebuilt_info is None or rebuilt_info.get("points_count") != len(points):
            raise SemanticRetrievalError("rebuilt Qdrant collection point count mismatch")

        lifecycle = {
            "schema_version": "tos_qdrant_collection_lifecycle_v1",
            "collection": collection,
            "absent_before_run": True,
            "first_materialization": {
                "create_seconds": first_create_seconds,
                "upsert_seconds": first_upsert_seconds,
                "points_count": first_info.get("points_count"),
            },
            "deletion_proof": {
                "delete_seconds": delete_seconds,
                "absent_after_delete": absent_after_delete,
            },
            "rebuild": {
                "create_seconds": rebuild_create_seconds,
                "upsert_seconds": rebuild_upsert_seconds,
                "points_count": rebuilt_info.get("points_count"),
            },
            "retained_for_manual_review": True,
            "authority_boundary": "isolated replaceable vector projection; never a source-text authority",
        }

        first_query_id = sorted(content_queries)[0]
        cold_response, cold_latency_ms = _retrieve(
            rag_url,
            collection,
            str(content_queries[first_query_id]["text"]),
            rerank=True,
        )
        cold_anchors = _validate_hits(cold_response["hits"], passage_by_anchor)
        cold_probe_path = run_root / "raw-output/cold-query-probe.json"
        _write_json(
            cold_probe_path,
            {
                "query_id": first_query_id,
                "reranker_loaded_before_probe": services_before["rerank"].get("loaded"),
                "cold_status": (
                    "genuine-cold-reranker-load"
                    if services_before["rerank"].get("loaded") is False
                    else "not-proven-cold-reranker-was-already-loaded"
                ),
                "end_to_end_latency_ms": cold_latency_ms,
                "result_source_anchor_refs": cold_anchors,
                "response": cold_response,
                "authority_boundary": "cold-route timing and ranked output only; no relevance judgment",
            },
        )

        result_refs: list[str] = []
        dense_latencies_ms: list[float] = []
        reranked_latencies_ms: list[float] = []
        dense_hits = 0
        reranked_hits = 0
        evaluable_queries = 0
        dense_hard_negative_presence = 0
        reranked_hard_negative_presence = 0
        hard_negative_slots = 0
        cross_lingual: dict[str, int] = {
            "queries": 0,
            "dense_expected_hits": 0,
            "reranked_expected_hits": 0,
        }
        dense_ranked_count = 0
        reranked_ranked_count = 0
        for query_id in sorted(content_queries):
            query = content_queries[query_id]
            plan_query = plan_queries[query_id]
            query_text = str(query["text"])
            dense_response, dense_ms = _retrieve(
                rag_url, collection, query_text, rerank=False
            )
            reranked_response, reranked_ms = _retrieve(
                rag_url, collection, query_text, rerank=True
            )
            dense_latencies_ms.append(dense_ms)
            reranked_latencies_ms.append(reranked_ms)
            dense_anchors = _validate_hits(dense_response["hits"], passage_by_anchor)
            reranked_anchors = _validate_hits(reranked_response["hits"], passage_by_anchor)
            dense_ranked_count += len(dense_anchors)
            reranked_ranked_count += len(reranked_anchors)
            expected = list(plan_query["expected_source_anchor_refs"])
            hard_negatives = list(plan_query["hard_negative_anchor_refs"])
            dense_expected_ranks = _expected_ranks(expected, dense_anchors)
            reranked_expected_ranks = _expected_ranks(expected, reranked_anchors)
            if plan_query["expected_behavior"] != "coverage-failure":
                evaluable_queries += 1
                dense_hits += bool(dense_expected_ranks)
                reranked_hits += bool(reranked_expected_ranks)
            if plan_query["category"] == "cross-lingual":
                cross_lingual["queries"] += 1
                cross_lingual["dense_expected_hits"] += bool(dense_expected_ranks)
                cross_lingual["reranked_expected_hits"] += bool(reranked_expected_ranks)
            hard_negative_slots += len(hard_negatives)
            dense_hard_negative_presence += sum(anchor in dense_anchors for anchor in hard_negatives)
            reranked_hard_negative_presence += sum(anchor in reranked_anchors for anchor in hard_negatives)

            result_path = run_root / "raw-output/query-results" / f"{query_id}.json"
            _write_json(
                result_path,
                {
                    "query_id": query_id,
                    "query_text": query_text,
                    "query_category": plan_query["category"],
                    "query_language": plan_query["query_language"],
                    "intended_target_language": plan_query["intended_target_language"],
                    "expected_behavior": plan_query["expected_behavior"],
                    "model_proposed_expected_source_anchor_refs": expected,
                    "model_proposed_hard_negative_anchor_refs": hard_negatives,
                    "dense_expected_ranks": dense_expected_ranks,
                    "reranked_expected_ranks": reranked_expected_ranks,
                    "dense_latency_ms": dense_ms,
                    "reranked_end_to_end_latency_ms": reranked_ms,
                    "dense_results": dense_response["hits"],
                    "reranked_results": reranked_response["hits"],
                    "judgment_status": "unreviewed-model-proposed-expectations-only",
                    "authority_boundary": "rankings and advisory diagnostics; no human relevance judgment",
                },
            )
            result_refs.append(result_path.relative_to(run_root).as_posix())

        snapshot = _snapshot_size(qdrant_url, collection)
        services_after = {
            "langchain": _http_json("GET", f"{langchain_url}/health", timeout=30),
            "rag": _http_json("GET", f"{rag_url}/health", timeout=30),
            "rerank": _http_json("GET", f"{rerank_url}/health", timeout=30),
            "collection": _collection_info(qdrant_url, collection),
        }
        if not isinstance(services_after["collection"], dict) or services_after["collection"].get(
            "points_count"
        ) != len(points):
            raise SemanticRetrievalError("retained collection failed final point-count check")

        passage_manifest_path = run_root / "inputs/source-passage-manifest.json"
        _write_json(
            passage_manifest_path,
            {
                "schema_version": "tos_semantic_passage_manifest_v1",
                "source_structure_run_ref": structure_run_root.as_posix(),
                "source_structure_runner_digest": structure_receipt["method_revision"]["artifact_digest"],
                "passage_count": len(passages),
                "indexed_passage_count": len(nonempty_passages),
                "empty_passage_count": len(passages) - len(nonempty_passages),
                "passages": [
                    {
                        "sample_id": passage["sample_id"],
                        "source_anchor_ref": passage["source_anchor_ref"],
                        "item_ref": passage["item_ref"],
                        "language": passage["language"],
                        "unit": passage["unit"],
                        "text_sha256": passage["text_sha256"],
                        "indexed": bool(passage["text"].strip()),
                    }
                    for passage in passages
                ],
                "source_text_bytes_copied_here": False,
                "authority_boundary": "digest inventory only; source text remains in the preserved Structure A packet",
            },
        )
        embedding_path = run_root / "receipts/embedding.json"
        _write_json(embedding_path, embedding_receipt)
        service_path = run_root / "receipts/resident-services-and-models.json"
        _write_json(
            service_path,
            {
                "schema_version": "tos_resident_semantic_services_v1",
                "captured_at_utc": started_at,
                "urls": {
                    "langchain": langchain_url,
                    "rag": rag_url,
                    "rerank": rerank_url,
                    "qdrant": qdrant_url,
                    "ovms": ovms_url,
                },
                "containers": container_receipt,
                "models": model_receipt,
                "health_before": services_before,
                "health_after": services_after,
                "network_posture": "localhost-only",
            },
        )
        lifecycle_path = run_root / "receipts/qdrant-collection-lifecycle.json"
        lifecycle["snapshot_measurement"] = snapshot
        _write_json(lifecycle_path, lifecycle)

        metrics = {
            "schema_version": "tos_resident_semantic_retrieval_metrics_v1",
            "experiment_id": receipt["experiment_id"],
            "variant": "B",
            "query_count": len(content_queries),
            "passage_count": len(passages),
            "indexed_passage_count": len(nonempty_passages),
            "empty_passage_count": len(passages) - len(nonempty_passages),
            "embedding_seconds": embedding_receipt["total_embedding_seconds"],
            "first_materialization_seconds": first_create_seconds + first_upsert_seconds,
            "rebuild_seconds": rebuild_create_seconds + rebuild_upsert_seconds,
            "snapshot_bytes": snapshot.get("size_bytes"),
            "logical_vector_bytes_float32": len(points) * VECTOR_SIZE * 4,
            "cold_reranked_end_to_end_latency_ms": cold_latency_ms,
            "cold_status": (
                "genuine-cold-reranker-load"
                if services_before["rerank"].get("loaded") is False
                else "not-proven-cold-reranker-was-already-loaded"
            ),
            "warm_dense_latency_ms_median": _median(dense_latencies_ms),
            "warm_reranked_end_to_end_latency_ms_median": _median(reranked_latencies_ms),
            "dense_ranked_result_count": dense_ranked_count,
            "reranked_result_count": reranked_ranked_count,
            "model_proposed_expected_hit_at_10": {
                "dense_hits": dense_hits,
                "reranked_hits": reranked_hits,
                "evaluable_queries": evaluable_queries,
                "status": "advisory-nonhuman-not-a-quality-score",
            },
            "model_proposed_hard_negative_presence_at_10": {
                "dense_presence": dense_hard_negative_presence,
                "reranked_presence": reranked_hard_negative_presence,
                "declared_slots": hard_negative_slots,
                "status": "advisory-presence-not-manual-error-rate",
            },
            "cross_lingual_advisory": cross_lingual,
            "quality": {
                "ndcg_at_10": None,
                "hard_negative_error_rate": None,
                "reason": "human graded relevance judgments have not started",
            },
            "human_cost": {
                "judgment_minutes": None,
                "reason": "no real human adjudication has occurred",
            },
            "traceability": {
                "dense_results_with_resolved_source_anchor": dense_ranked_count,
                "dense_ranked_result_count": dense_ranked_count,
                "reranked_results_with_resolved_source_anchor": reranked_ranked_count,
                "reranked_result_count": reranked_ranked_count,
                "status": "mechanically-resolved-unreviewed",
            },
            "collection_lifecycle": {
                "delete_and_rebuild_proven": True,
                "retained_for_manual_review": True,
            },
            "total_runner_seconds": time.perf_counter() - run_started,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "authority_boundary": "speed, storage, and ranked output only; relevance remains unreviewed",
        }
        metrics_path = run_root / "metrics/resident-semantic-retrieval-summary.json"
        _write_json(metrics_path, metrics)
        invocation_path = run_root / "receipts/resident-semantic-invocation.json"
        _write_json(
            invocation_path,
            {
                "captured_at_utc": started_at,
                "argv": invocation,
                "python": platform.python_version(),
                "runner_sha256": _sha256_file(Path(__file__)),
                "query_plan_sha256": _sha256_file(query_plan_path),
                "query_content_sha256": _sha256_file(query_content_path),
                "source_structure_run_ref": structure_run_root.as_posix(),
                "collection": collection,
                "rights_posture": "restricted-derived-text-and-query-content-private-localhost-runtime-only",
            },
        )

        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = sorted(content_queries)
        receipt["method_revision"] = {
            "implementation": "resident abyss-stack OVMS embeddings, isolated Qdrant, RAG API, and Qwen3 reranker",
            "version": (
                f"rag={container_receipt['rag-api']['image_id'][:12]};"
                f"qdrant={container_receipt['qdrant']['image_id'][:12]};"
                f"rerank={container_receipt['rerank-api']['image_id'][:12]}"
            ),
            "runtime": f"Python {platform.python_version()} plus resident OpenVINO services",
            "model": f"{EMBEDDING_MODEL} + {RERANK_MODEL}",
            "artifact_digest": _sha256_file(Path(__file__)),
        }
        receipt["invocation_ref"] = invocation_path.relative_to(run_root).as_posix()
        receipt["artifact_refs"] = sorted(
            result_refs
            + [
                cold_probe_path.relative_to(run_root).as_posix(),
                passage_manifest_path.relative_to(run_root).as_posix(),
                embedding_path.relative_to(run_root).as_posix(),
                service_path.relative_to(run_root).as_posix(),
                lifecycle_path.relative_to(run_root).as_posix(),
                invocation_path.relative_to(run_root).as_posix(),
            ]
        )
        receipt["metric_refs"] = [metrics_path.relative_to(run_root).as_posix()]
        receipt["manual_review_refs"] = []
        receipt["model_inspection_refs"] = []
        receipt["errors"] = []
        _write_json(receipt_path, receipt)
        return metrics
    except Exception as exc:
        cleanup_error = None
        if collection_created:
            try:
                _delete_collection(qdrant_url, collection)
            except Exception as cleanup_exc:  # preserve the primary failure
                cleanup_error = str(cleanup_exc)
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)] + ([f"collection cleanup failed: {cleanup_error}"] if cleanup_error else [])
        _write_json(receipt_path, receipt)
        if isinstance(exc, SemanticRetrievalError):
            raise
        raise SemanticRetrievalError(str(exc)) from exc
