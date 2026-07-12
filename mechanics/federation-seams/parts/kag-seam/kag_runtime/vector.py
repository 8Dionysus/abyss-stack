from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, Iterable, Iterator

from .bundle import RetrievalBundle
from .transport import HttpJsonError, JsonHttpClient


SCHEMA_VERSION = "abyss-stack-repo-self-kag-qdrant-v1"
COLLECTION_PREFIX = "aoa_kag_repo_self_"
DEFAULT_ALIAS = "aoa_kag_repo_self_current"
DISTANCES = {
    "cosine": "Cosine",
    "dot": "Dot",
    "euclid": "Euclid",
    "manhattan": "Manhattan",
}


def _batches(records: Iterable[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
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


def _point(document: dict[str, Any], vector: list[float], profile_id: str) -> dict[str, Any]:
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
    response = client.request("GET", "/collections")
    result = response.get("result")
    collections = result.get("collections") if isinstance(result, dict) else None
    if not isinstance(collections, list):
        raise RuntimeError("Qdrant collection inventory is missing")
    keep = {current, previous}
    removed: list[str] = []
    for item in collections:
        name = str(item.get("name", ""))
        if name.startswith(COLLECTION_PREFIX) and name not in keep:
            client.request("DELETE", f"/collections/{name}")
            removed.append(name)
    return sorted(removed)


def materialize(
    bundle: RetrievalBundle,
    *,
    qdrant: JsonHttpClient,
    embeddings: JsonHttpClient,
    alias: str = DEFAULT_ALIAS,
    batch_size: int = 16,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    profile = dict(bundle.manifest["embedding_profile"])
    collection = _collection_name(bundle)
    expected_count = int(bundle.manifest["files"]["documents"]["record_count"])
    existing = _collection(qdrant, collection)
    if existing is not None and _validate_collection(existing, profile) != expected_count:
        qdrant.request("DELETE", f"/collections/{collection}")
        existing = None
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
        embedded = 0
        for documents in _batches(bundle.records("documents"), batch_size):
            vectors = _embedding_vectors(embeddings, documents, profile)
            points = [
                _point(document, vector, str(profile["id"]))
                for document, vector in zip(documents, vectors, strict=True)
            ]
            qdrant.request(
                "PUT",
                f"/collections/{collection}/points?wait=true",
                {"points": points},
            )
            embedded += len(points)
            if progress is not None:
                progress(embedded, expected_count)
        if embedded != expected_count:
            raise RuntimeError(f"Qdrant projection count mismatch: {embedded} != {expected_count}")

    observed = _collection(qdrant, collection)
    if observed is None or _validate_collection(observed, profile) != expected_count:
        raise RuntimeError("Qdrant collection did not reach the expected point count")
    previous = _alias_collection(qdrant, alias)
    if previous != collection:
        _switch_alias(qdrant, alias, collection, previous)
    removed = _cleanup_collections(qdrant, current=collection, previous=previous)
    return {
        "schema_version": SCHEMA_VERSION,
        "collection": collection,
        "alias": alias,
        "point_count": expected_count,
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
    expected = int(bundle.manifest["files"]["documents"]["record_count"])
    if count != expected:
        raise RuntimeError(f"Qdrant point count mismatch: {count} != {expected}")
    active = _alias_collection(qdrant, alias)
    if active != collection:
        raise RuntimeError(f"Qdrant alias {alias} points to {active}, expected {collection}")
    return {
        "schema_version": SCHEMA_VERSION,
        "collection": collection,
        "alias": alias,
        "point_count": count,
        "embedding_profile": profile,
    }
