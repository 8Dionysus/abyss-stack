from __future__ import annotations

import math
import time
from collections.abc import Callable
from itertools import islice
from typing import Any, Iterable, Iterator

from .bundle import RetrievalBundle
from .transport import HttpJsonError, JsonHttpClient


SCHEMA_VERSION = "abyss-stack-repo-self-kag-qdrant-v3"
COLLECTION_PREFIX = "aoa_kag_repo_self_"
DEFAULT_ALIAS = "aoa_kag_repo_self_current"
DEFAULT_EMBEDDING_BATCH_SIZE = 1
PAYLOAD_INDEXES = {
    "repo": "keyword",
    "node_class": "keyword",
    "kind": "keyword",
    "document_role": "keyword",
    "surface_state": "keyword",
    "access.scope": "keyword",
}
DISTANCES = {
    "cosine": "Cosine",
    "dot": "Dot",
    "euclid": "Euclid",
    "manhattan": "Manhattan",
}
TRANSIENT_EMBEDDING_STATUSES = {0, 429, 500, 502, 503, 504}
EMBEDDING_RETRY_DELAYS = (1.0, 2.0, 4.0)


def _batches(
    records: Iterable[dict[str, Any]], size: int
) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for record in records:
        batch.append(record)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _normalize(vector: list[Any], mode: str, dimensions: int) -> list[float]:
    if len(vector) != dimensions:
        raise RuntimeError(
            f"embedding dimension mismatch: observed {len(vector)}, expected {dimensions}"
        )
    values = [float(item) for item in vector]
    if any(not math.isfinite(item) for item in values):
        raise RuntimeError("embedding vector contains a non-finite value")
    if mode == "l2":
        norm = math.sqrt(sum(item * item for item in values))
        if norm == 0:
            raise RuntimeError("embedding vector has zero norm")
        values = [item / norm for item in values]
    return values


def _embedding_vectors(
    client: JsonHttpClient,
    documents: list[dict[str, Any]],
    profile: dict[str, Any],
) -> list[list[float]]:
    response = client.request(
        "POST",
        "/embeddings",
        {
            "input": [str(document["text"]) for document in documents],
            "model": str(profile["model"]),
        },
    )
    if response.get("model") != profile["model"]:
        raise RuntimeError(
            f"embedding model mismatch: {response.get('model')} != {profile['model']}"
        )
    data = response.get("data")
    if not isinstance(data, list) or len(data) != len(documents):
        raise RuntimeError("embedding response batch size mismatch")
    ordered = sorted(data, key=lambda item: int(item.get("index", -1)))
    dimensions = int(profile["dimensions"])
    return [
        _normalize(item.get("embedding", []), str(profile["normalization"]), dimensions)
        for item in ordered
    ]


def _embedding_vectors_resilient(
    client: JsonHttpClient,
    documents: list[dict[str, Any]],
    profile: dict[str, Any],
) -> list[list[float]]:
    last_error: HttpJsonError | None = None
    for delay in (0.0, *EMBEDDING_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            return _embedding_vectors(client, documents, profile)
        except HttpJsonError as exc:
            if exc.status not in TRANSIENT_EMBEDDING_STATUSES:
                raise
            last_error = exc
    if len(documents) == 1:
        assert last_error is not None
        raise last_error
    midpoint = len(documents) // 2
    return [
        *_embedding_vectors_resilient(client, documents[:midpoint], profile),
        *_embedding_vectors_resilient(client, documents[midpoint:], profile),
    ]


def _embedding_vectors_batched(
    client: JsonHttpClient,
    documents: list[dict[str, Any]],
    profile: dict[str, Any],
    batch_size: int,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for batch in _batches(documents, batch_size):
        vectors.extend(_embedding_vectors_resilient(client, batch, profile))
    return vectors


def _point(
    document: dict[str, Any], vector: list[float], profile_id: str
) -> dict[str, Any]:
    payload_keys = (
        "id",
        "version_id",
        "repo",
        "namespace",
        "node_id",
        "node_class",
        "kind",
        "label",
        "path",
        "locator",
        "text",
        "text_digest",
        "document_role",
        "surface_state",
        "source_record_ids",
        "source_version_ids",
        "anchor_ids",
        "access",
        "abi",
        "signs",
        "provenance_ref",
        "temporal_ref",
        "trust_ref",
        "freshness",
    )
    payload = {key: document[key] for key in payload_keys}
    payload["embedding_profile_id"] = profile_id
    return {
        "id": str(document["vector_point_id"]),
        "vector": vector,
        "payload": payload,
    }


def _collection_name(bundle: RetrievalBundle) -> str:
    return f"{COLLECTION_PREFIX}{bundle.projection_digest[:20]}"


def _collection(client: JsonHttpClient, name: str) -> dict[str, Any] | None:
    try:
        return client.request("GET", f"/collections/{name}")
    except HttpJsonError as exc:
        if exc.status == 404:
            return None
        raise


def _point_count(response: dict[str, Any]) -> int:
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Qdrant collection response is missing result")
    return int(result.get("points_count") or 0)


def _validate_collection(
    response: dict[str, Any],
    profile: dict[str, Any],
) -> int:
    result = response.get("result")
    config = result.get("config") if isinstance(result, dict) else None
    params = config.get("params") if isinstance(config, dict) else None
    vectors = params.get("vectors") if isinstance(params, dict) else None
    if not isinstance(vectors, dict):
        raise RuntimeError("Qdrant collection vector config is missing")
    expected_distance = DISTANCES[str(profile["distance"])]
    if int(vectors.get("size") or 0) != int(profile["dimensions"]):
        raise RuntimeError("Qdrant collection vector dimensions mismatch")
    if vectors.get("distance") != expected_distance:
        raise RuntimeError("Qdrant collection distance mismatch")
    return _point_count(response)


def _ensure_payload_indexes(client: JsonHttpClient, collection: str) -> None:
    observed = _collection(client, collection)
    if observed is None:
        raise RuntimeError(f"missing Qdrant collection: {collection}")
    result = observed.get("result")
    schema = result.get("payload_schema") if isinstance(result, dict) else None
    schema = schema if isinstance(schema, dict) else {}
    for field, data_type in PAYLOAD_INDEXES.items():
        entry = schema.get(field)
        if isinstance(entry, dict) and entry.get("data_type") == data_type:
            continue
        client.request(
            "PUT",
            f"/collections/{collection}/index?wait=true",
            {"field_name": field, "field_schema": data_type},
        )


def _validate_payload_indexes(response: dict[str, Any]) -> None:
    result = response.get("result")
    schema = result.get("payload_schema") if isinstance(result, dict) else None
    if not isinstance(schema, dict):
        raise RuntimeError("Qdrant collection payload schema is missing")
    observed = {
        field: entry.get("data_type") if isinstance(entry, dict) else None
        for field, entry in schema.items()
    }
    missing = {
        field: data_type
        for field, data_type in PAYLOAD_INDEXES.items()
        if observed.get(field) != data_type
    }
    if missing:
        raise RuntimeError(f"Qdrant payload indexes mismatch: {missing}")


def _reusable_vectors(
    client: JsonHttpClient,
    collection: str | None,
    documents: list[dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, list[float]]:
    if not collection or not documents:
        return {}
    try:
        response = client.request(
            "POST",
            f"/collections/{collection}/points",
            {
                "ids": [str(document["vector_point_id"]) for document in documents],
                "with_payload": True,
                "with_vector": True,
            },
        )
    except HttpJsonError as exc:
        if exc.status == 404:
            return {}
        raise
    records = response.get("result")
    if not isinstance(records, list):
        raise RuntimeError("Qdrant point retrieval response is missing result")
    documents_by_point = {
        str(document["vector_point_id"]): document for document in documents
    }
    reusable: dict[str, list[float]] = {}
    for record in records:
        point_id = str(record.get("id", ""))
        document = documents_by_point.get(point_id)
        payload = record.get("payload")
        raw_vector = record.get("vector")
        if (
            document is None
            or not isinstance(payload, dict)
            or not isinstance(raw_vector, list)
            or payload.get("text_digest") != document["text_digest"]
            or payload.get("embedding_profile_id") != profile["id"]
        ):
            continue
        reusable[point_id] = _normalize(
            raw_vector,
            str(profile["normalization"]),
            int(profile["dimensions"]),
        )
    return reusable


def _alias_collection(client: JsonHttpClient, alias: str) -> str | None:
    response = client.request("GET", "/aliases")
    result = response.get("result")
    aliases = result.get("aliases") if isinstance(result, dict) else None
    if not isinstance(aliases, list):
        raise RuntimeError("Qdrant alias inventory is missing")
    for item in aliases:
        if item.get("alias_name") == alias:
            return str(item.get("collection_name"))
    return None


def _switch_alias(
    client: JsonHttpClient,
    alias: str,
    collection: str,
    previous: str | None,
) -> None:
    actions: list[dict[str, Any]] = []
    if previous:
        actions.append({"delete_alias": {"alias_name": alias}})
    actions.append(
        {"create_alias": {"collection_name": collection, "alias_name": alias}}
    )
    client.request("POST", "/collections/aliases", {"actions": actions})


def _cleanup_collections(
    client: JsonHttpClient,
    *,
    current: str,
    previous: str | None,
) -> list[str]:
    if (
        not previous
        or previous == current
        or not previous.startswith(COLLECTION_PREFIX)
    ):
        return []
    response = client.request("GET", "/aliases")
    result = response.get("result")
    aliases = result.get("aliases") if isinstance(result, dict) else None
    if not isinstance(aliases, list):
        raise RuntimeError("Qdrant alias inventory is missing")
    referenced = {
        str(item.get("collection_name") or "")
        for item in aliases
        if isinstance(item, dict)
    }
    if previous in referenced:
        return []
    client.request("DELETE", f"/collections/{previous}")
    return [previous]


def materialize(
    bundle: RetrievalBundle,
    *,
    qdrant: JsonHttpClient,
    embeddings: JsonHttpClient,
    alias: str = DEFAULT_ALIAS,
    batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    profile = dict(bundle.manifest["embedding_profile"])
    collection = _collection_name(bundle)
    expected_count = int(bundle.manifest["files"]["documents"]["record_count"])
    previous = _alias_collection(qdrant, alias)
    existing = _collection(qdrant, collection)
    embedded = 0
    if existing is not None:
        try:
            embedded = _validate_collection(existing, profile)
        except RuntimeError:
            qdrant.request("DELETE", f"/collections/{collection}")
            existing = None
        else:
            if embedded > expected_count:
                qdrant.request("DELETE", f"/collections/{collection}")
                existing = None
                embedded = 0
    if existing is None:
        qdrant.request(
            "PUT",
            f"/collections/{collection}",
            {
                "vectors": {
                    "size": int(profile["dimensions"]),
                    "distance": DISTANCES[str(profile["distance"])],
                    "on_disk": True,
                },
                "on_disk_payload": True,
                "hnsw_config": {"on_disk": True},
            },
        )
    _ensure_payload_indexes(qdrant, collection)
    resumed_from = embedded
    reused = 0
    newly_embedded = 0
    if progress is not None and embedded:
        progress(embedded, expected_count)
    if embedded < expected_count:
        remaining = islice(bundle.records("documents"), embedded, None)
        source_batch_size = max(batch_size, 256) if previous else batch_size
        for documents in _batches(remaining, source_batch_size):
            reusable = _reusable_vectors(qdrant, previous, documents, profile)
            changed = [
                document
                for document in documents
                if str(document["vector_point_id"]) not in reusable
            ]
            changed_vectors = (
                _embedding_vectors_batched(
                    embeddings,
                    changed,
                    profile,
                    batch_size,
                )
                if changed
                else []
            )
            vectors_by_point = {
                str(document["vector_point_id"]): vector
                for document, vector in zip(changed, changed_vectors, strict=True)
            }
            vectors_by_point.update(reusable)
            points = [
                _point(
                    document,
                    vectors_by_point[str(document["vector_point_id"])],
                    str(profile["id"]),
                )
                for document in documents
            ]
            qdrant.request(
                "PUT",
                f"/collections/{collection}/points?wait=true",
                {"points": points},
            )
            reused += len(reusable)
            newly_embedded += len(changed)
            embedded += len(points)
            if progress is not None:
                progress(embedded, expected_count)
    if embedded != expected_count:
        raise RuntimeError(
            f"Qdrant projection count mismatch: {embedded} != {expected_count}"
        )

    observed = _collection(qdrant, collection)
    if observed is None or _validate_collection(observed, profile) != expected_count:
        raise RuntimeError("Qdrant collection did not reach the expected point count")
    _validate_payload_indexes(observed)
    if previous != collection:
        _switch_alias(qdrant, alias, collection, previous)
    removed = _cleanup_collections(qdrant, current=collection, previous=previous)
    return {
        "schema_version": SCHEMA_VERSION,
        "collection": collection,
        "alias": alias,
        "point_count": expected_count,
        "resumed_from_point_count": resumed_from,
        "reused_point_count": reused,
        "embedded_point_count": newly_embedded,
        "embedding_profile": profile,
        "previous_collection": previous,
        "removed_collections": removed,
    }


def check(
    bundle: RetrievalBundle,
    *,
    qdrant: JsonHttpClient,
    alias: str = DEFAULT_ALIAS,
) -> dict[str, Any]:
    collection = _collection_name(bundle)
    profile = dict(bundle.manifest["embedding_profile"])
    observed = _collection(qdrant, collection)
    if observed is None:
        raise RuntimeError(f"missing Qdrant collection: {collection}")
    count = _validate_collection(observed, profile)
    _validate_payload_indexes(observed)
    expected = int(bundle.manifest["files"]["documents"]["record_count"])
    if count != expected:
        raise RuntimeError(f"Qdrant point count mismatch: {count} != {expected}")
    active = _alias_collection(qdrant, alias)
    if active != collection:
        raise RuntimeError(
            f"Qdrant alias {alias} points to {active}, expected {collection}"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "collection": collection,
        "alias": alias,
        "point_count": count,
        "embedding_profile": profile,
    }


def active_collection(
    qdrant: JsonHttpClient,
    alias: str = DEFAULT_ALIAS,
) -> str:
    collection = _alias_collection(qdrant, alias)
    if not collection:
        raise RuntimeError(f"Qdrant alias is missing: {alias}")
    return collection


def search(
    query: str,
    *,
    qdrant: JsonHttpClient,
    embeddings: JsonHttpClient,
    profile: dict[str, Any],
    collection: str | None = None,
    alias: str = DEFAULT_ALIAS,
    repo: str | None = None,
    node_class: str | None = None,
    kind: str | None = None,
    path: str | None = None,
    document_role: str | None = None,
    surface_state: str | None = None,
    access_scopes: tuple[str, ...] = ("public",),
    offset: int = 0,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    instructed_query = (
        "Instruct: Retrieve the OS Abyss repository evidence that best answers the query.\n"
        f"Query: {query}"
    )
    query_vector = _embedding_vectors(
        embeddings,
        [{"text": instructed_query}],
        profile,
    )[0]
    payload: dict[str, Any] = {
        "query": query_vector,
        "limit": limit,
        "offset": offset,
        "with_payload": True,
    }
    conditions: list[dict[str, Any]] = []
    scopes = tuple(dict.fromkeys(access_scopes))
    if not scopes:
        return [], (time.perf_counter() - started) * 1000
    if len(scopes) == 1:
        conditions.append({"key": "access.scope", "match": {"value": scopes[0]}})
    else:
        conditions.append({"key": "access.scope", "match": {"any": list(scopes)}})
    if repo:
        conditions.append({"key": "repo", "match": {"value": repo}})
    if node_class:
        conditions.append({"key": "node_class", "match": {"value": node_class}})
    if kind:
        conditions.append({"key": "kind", "match": {"value": kind}})
    if path:
        conditions.append({"key": "path", "match": {"value": path}})
    if document_role:
        conditions.append({"key": "document_role", "match": {"value": document_role}})
    if surface_state:
        conditions.append({"key": "surface_state", "match": {"value": surface_state}})
    payload["filter"] = {"must": conditions}
    if not document_role:
        payload["filter"]["must_not"] = [
            {
                "key": "document_role",
                "match": {"value": "evaluation_fixture"},
            }
        ]
    selected_collection = collection or active_collection(qdrant, alias)
    response = qdrant.request(
        "POST",
        f"/collections/{selected_collection}/points/query",
        payload,
    )
    result = response.get("result")
    points = result.get("points") if isinstance(result, dict) else None
    if not isinstance(points, list):
        raise RuntimeError("Qdrant query response is missing points")
    return points, (time.perf_counter() - started) * 1000
