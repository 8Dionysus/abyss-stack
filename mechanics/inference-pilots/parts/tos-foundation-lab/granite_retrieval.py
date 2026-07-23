#!/usr/bin/env python3
"""Execute frozen Retrieval C with Granite R2 through isolated OpenVINO."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import resource
import shutil
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from semantic_retrieval import _expected_ranks, _load_passages, _load_queries


class GraniteRetrievalError(RuntimeError):
    """Raised when the frozen independent Retrieval C route is not executable."""


MODEL_ID = "ibm-granite/granite-embedding-311m-multilingual-r2"
MODEL_REVISION = "44399559930365213510b1ee2eb15ded83374f0e"
MODEL_LICENSE = "Apache-2.0"
VECTOR_SIZE = 768
TOP_K = 10
BATCH_SIZE = 6
MAX_LENGTH = 512
EXPECTED_TOKENIZERS_VERSION = "0.23.1"
EXPECTED_OPENVINO_PREFIX = "2026.2"
BRIDGE_PATH = Path(__file__).with_name("granite_embedding_bridge.py")
ALLOWED_RUNTIME_ROOT = Path("/srv/abyss-machine/runtimes")
ALLOWED_CACHE_ROOT = Path("/srv/abyss-machine/cache/ai/huggingface")
INDEX_RELATIVE_PATH = Path("derived-index/granite-r2-vectors.json")
EXPECTED_MODEL_FILES = (
    "1_Pooling/config.json",
    "README.md",
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "openvino/openvino_model_qint8_quantized.bin",
    "openvino/openvino_model_qint8_quantized.xml",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)
KNOWN_FILE_SHA256 = {
    "openvino/openvino_model_qint8_quantized.bin": (
        "19cd99b8657e8f86529ce05384194b1bf3dbde94fd48a571a832344c119c27bc"
    ),
    "tokenizer.json": "0087c868b33bad550a78a08d19798cfd7f713cde4f020803b8f51f405503e15f",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraniteRetrievalError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise GraniteRetrievalError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_canonical_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(payload) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_fingerprint(snapshot_path: Path) -> dict[str, Any]:
    snapshot_path = snapshot_path.absolute()
    resolved_snapshot = snapshot_path.resolve()
    if not resolved_snapshot.is_relative_to(ALLOWED_CACHE_ROOT.resolve()):
        raise GraniteRetrievalError("model snapshot is outside the host Hugging Face cache")
    if snapshot_path.name != MODEL_REVISION:
        raise GraniteRetrievalError("model snapshot path does not end in the frozen repository revision")
    actual_files = sorted(
        path.relative_to(snapshot_path).as_posix()
        for path in snapshot_path.rglob("*")
        if path.is_file()
    )
    if actual_files != sorted(EXPECTED_MODEL_FILES):
        raise GraniteRetrievalError(
            "model snapshot does not contain exactly the admitted artifact subset"
        )
    artifacts: list[dict[str, Any]] = []
    for relative in EXPECTED_MODEL_FILES:
        path = snapshot_path / relative
        resolved = path.resolve()
        if not resolved.is_relative_to(ALLOWED_CACHE_ROOT.resolve()):
            raise GraniteRetrievalError(f"model artifact escapes the host cache: {relative}")
        digest = _sha256_file(path)
        expected_digest = KNOWN_FILE_SHA256.get(relative)
        if expected_digest and digest != expected_digest:
            raise GraniteRetrievalError(f"model artifact digest differs from admission: {relative}")
        artifacts.append(
            {
                "relative_path": relative,
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
    return {
        "model_id": MODEL_ID,
        "repository_revision": MODEL_REVISION,
        "license": MODEL_LICENSE,
        "snapshot_path": snapshot_path.as_posix(),
        "artifact_count": len(artifacts),
        "artifact_bytes": sum(record["bytes"] for record in artifacts),
        "artifacts": artifacts,
        "full_repository_downloaded": False,
        "remote_code_executed": False,
    }


def _runtime_fingerprint(
    runtime_python: Path,
    runtime_manifest: Path,
    model_snapshot: Path,
) -> dict[str, Any]:
    # Preserve lexical venv ownership: resolving bin/python follows its normal
    # symlink to /usr/bin and would erase the versioned runtime root.
    runtime_python = runtime_python.absolute()
    runtime_manifest = runtime_manifest.absolute()
    runtime_root = runtime_python.parent.parent
    if not runtime_root.resolve().is_relative_to(ALLOWED_RUNTIME_ROOT.resolve()):
        raise GraniteRetrievalError("runtime interpreter is outside the host runtime root")
    if runtime_python != runtime_root / "bin/python":
        raise GraniteRetrievalError("runtime interpreter must be the runtime-owned bin/python")
    if not runtime_python.is_file() or not (runtime_python.stat().st_mode & 0o111):
        raise GraniteRetrievalError("runtime interpreter is unavailable")
    if runtime_manifest != runtime_root / "runtime-manifest.json" or not runtime_manifest.is_file():
        raise GraniteRetrievalError("runtime manifest must be the runtime-owned manifest")
    manifest = _load_json(runtime_manifest)
    if Path(str(manifest.get("runtime_root", ""))).resolve() != runtime_root.resolve():
        raise GraniteRetrievalError("runtime manifest does not own the supplied interpreter")
    model = manifest.get("model")
    if not isinstance(model, dict):
        raise GraniteRetrievalError("runtime manifest has no model record")
    if model.get("model_id") != MODEL_ID or model.get("repository_revision") != MODEL_REVISION:
        raise GraniteRetrievalError("runtime manifest model identity differs from the frozen method")
    if Path(str(model.get("snapshot_path", ""))).resolve() != model_snapshot.resolve():
        raise GraniteRetrievalError("runtime manifest snapshot path differs from the supplied model")
    if model.get("license") != MODEL_LICENSE:
        raise GraniteRetrievalError("runtime manifest model license differs from admission")
    if manifest.get("system_python_mutated") is not False:
        raise GraniteRetrievalError("runtime manifest does not attest system Python isolation")

    probe = subprocess.run(
        (
            runtime_python.as_posix(),
            "-c",
            "import json,numpy,openvino,platform,tokenizers; "
            "print(json.dumps({'python':platform.python_version(),'numpy':numpy.__version__,"
            "'openvino':openvino.__version__,'openvino_module':openvino.__file__,"
            "'tokenizers':tokenizers.__version__,'tokenizers_module':tokenizers.__file__}))",
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if probe.returncode != 0:
        raise GraniteRetrievalError(f"cannot probe Granite runtime: {probe.stderr.strip()[:500]}")
    try:
        observed = json.loads(probe.stdout)
    except json.JSONDecodeError as exc:
        raise GraniteRetrievalError("Granite runtime probe returned non-JSON") from exc
    if observed.get("tokenizers") != EXPECTED_TOKENIZERS_VERSION:
        raise GraniteRetrievalError("installed tokenizer runtime differs from the pinned version")
    if not str(observed.get("openvino", "")).startswith(EXPECTED_OPENVINO_PREFIX):
        raise GraniteRetrievalError("OpenVINO runtime differs from the reviewed 2026.2 family")
    tokenizers_module = Path(str(observed.get("tokenizers_module", ""))).resolve()
    if not tokenizers_module.is_relative_to(runtime_root.resolve()):
        raise GraniteRetrievalError("tokenizers was not loaded from the isolated runtime")
    return {
        **observed,
        "interpreter": runtime_python.as_posix(),
        "runtime_root": runtime_root.as_posix(),
        "runtime_manifest": runtime_manifest.as_posix(),
        "runtime_manifest_sha256": _sha256_file(runtime_manifest),
        "system_site_packages_used_for_openvino": True,
    }


def _run_bridge(
    payload: dict[str, Any],
    *,
    runtime_python: Path,
    timeout: float = 1800.0,
) -> dict[str, Any]:
    bridge_source = BRIDGE_PATH.read_text(encoding="utf-8")
    completed = subprocess.run(
        (runtime_python.absolute().as_posix(), "-c", bridge_source),
        input=json.dumps(payload, ensure_ascii=False),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    try:
        response = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise GraniteRetrievalError(
            f"Granite bridge returned non-JSON; stderr={completed.stderr.strip()[:1000]}"
        ) from exc
    if not isinstance(response, dict):
        raise GraniteRetrievalError("Granite bridge returned non-object JSON")
    if completed.returncode != 0 or response.get("ok") is not True:
        raise GraniteRetrievalError(
            f"Granite bridge failed: {response.get('error_type')}: {response.get('error')}"
        )
    return response


def _safe_remove_index(index_path: Path, run_root: Path) -> None:
    expected = (run_root / INDEX_RELATIVE_PATH).resolve()
    if index_path.resolve() != expected:
        raise GraniteRetrievalError("refusing to delete a non-canonical Retrieval C index path")
    if index_path.exists():
        index_path.unlink()


def _vector_map(
    records: object,
    expected_ids: list[str],
) -> dict[str, list[float]]:
    if not isinstance(records, list):
        raise GraniteRetrievalError("embedding bridge omitted vector records")
    result: dict[str, list[float]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise GraniteRetrievalError("embedding bridge returned an invalid vector record")
        vector = record.get("vector")
        if (
            not isinstance(vector, list)
            or len(vector) != VECTOR_SIZE
            or not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in vector)
        ):
            raise GraniteRetrievalError("embedding bridge returned an invalid vector")
        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if not math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5):
            raise GraniteRetrievalError("embedding bridge vector is not L2-normalized")
        result[record["id"]] = [float(value) for value in vector]
    if sorted(result) != sorted(expected_ids):
        raise GraniteRetrievalError("embedding bridge vector identities differ from frozen inputs")
    return result


def _rank_passages(
    query_vector: list[float],
    passages: list[dict[str, Any]],
    passage_vectors: dict[str, list[float]],
    *,
    top_k: int = TOP_K,
) -> list[dict[str, Any]]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for passage in passages:
        vector = passage_vectors[str(passage["sample_id"])]
        score = sum(left * right for left, right in zip(query_vector, vector, strict=True))
        if not math.isfinite(score):
            raise GraniteRetrievalError("cosine ranking produced a non-finite score")
        scored.append((score, passage))
    scored.sort(key=lambda item: (-item[0], str(item[1]["source_anchor_ref"])))
    return [
        {
            "rank": rank,
            "score": score,
            "sample_id": passage["sample_id"],
            "source_anchor_ref": passage["source_anchor_ref"],
            "item_ref": passage["item_ref"],
            "language": passage["language"],
            "unit": passage["unit"],
            "text_sha256": passage["text_sha256"],
            "text": passage["text"],
        }
        for rank, (score, passage) in enumerate(scored[:top_k], start=1)
    ]


def execute_granite_retrieval(
    run_root: Path,
    structure_run_root: Path,
    query_plan_path: Path,
    query_content_path: Path,
    runtime_python_path: Path,
    runtime_manifest_path: Path,
    model_snapshot_path: Path,
    *,
    invocation: list[str],
) -> dict[str, Any]:
    """Execute independent Retrieval C without assigning relevance truth."""

    run_root = run_root.resolve()
    structure_run_root = structure_run_root.resolve()
    query_plan_path = query_plan_path.resolve()
    query_content_path = query_content_path.resolve()
    runtime_python_path = runtime_python_path.absolute()
    runtime_manifest_path = runtime_manifest_path.absolute()
    model_snapshot_path = model_snapshot_path.absolute()
    receipt_path = run_root / "run.receipt.json"
    receipt = _load_json(receipt_path)
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if receipt.get("experiment_id") != "tos-retrieval-foundation-v1" or receipt.get(
        "variant"
    ) != "C":
        raise GraniteRetrievalError("Granite runner requires prepared Retrieval C")
    if receipt.get("status") != "prepared" or preflight.get("decision") != "ready":
        raise GraniteRetrievalError("run must be prepared from a ready preflight")
    if experiment.get("family") != "retrieval":
        raise GraniteRetrievalError("experiment specification is not retrieval")
    variant = next(
        (
            item
            for item in experiment.get("variants", [])
            if isinstance(item, dict) and item.get("label") == "C"
        ),
        None,
    )
    if not isinstance(variant, dict) or variant.get("model") != MODEL_ID:
        raise GraniteRetrievalError("prepared experiment does not freeze the admitted Granite model")
    if MODEL_REVISION not in str(variant.get("version_posture", "")):
        raise GraniteRetrievalError("prepared experiment does not freeze the admitted model revision")

    passages, structure_receipt = _load_passages(structure_run_root)
    plan_queries, content_queries = _load_queries(query_plan_path, query_content_path)
    nonempty_passages = [passage for passage in passages if passage["text"].strip()]
    if len(nonempty_passages) != 24:
        raise GraniteRetrievalError(
            f"expected 24 nonempty passages and 12 preserved coverage gaps, found {len(nonempty_passages)}"
        )

    started_at = _utc_now()
    started = time.perf_counter()
    receipt["status"] = "running"
    receipt["started_at_utc"] = started_at
    _write_json(receipt_path, receipt)
    index_path = run_root / INDEX_RELATIVE_PATH
    try:
        runtime = _runtime_fingerprint(
            runtime_python_path,
            runtime_manifest_path,
            model_snapshot_path,
        )
        model = _model_fingerprint(model_snapshot_path)
        passage_ids = [str(passage["sample_id"]) for passage in nonempty_passages]
        query_ids = sorted(content_queries)
        bridge = _run_bridge(
            {
                "operation": "encode-frozen-retrieval",
                "model_xml": (
                    model_snapshot_path / "openvino/openvino_model_qint8_quantized.xml"
                ).as_posix(),
                "tokenizer_json": (model_snapshot_path / "tokenizer.json").as_posix(),
                "device": "CPU",
                "batch_size": BATCH_SIZE,
                "max_length": MAX_LENGTH,
                "passages": [
                    {"id": passage["sample_id"], "text": passage["text"]}
                    for passage in nonempty_passages
                ],
                "queries": [
                    {"id": query_id, "text": str(content_queries[query_id]["text"])}
                    for query_id in query_ids
                ],
            },
            runtime_python=runtime_python_path,
        )
        first_passage_vectors = _vector_map(bridge.get("first_passages"), passage_ids)
        rebuilt_passage_vectors = _vector_map(bridge.get("rebuilt_passages"), passage_ids)
        first_query_vectors = _vector_map(bridge.get("first_queries"), query_ids)
        warm_query_vectors = _vector_map(bridge.get("warm_queries"), query_ids)
        if first_passage_vectors != rebuilt_passage_vectors:
            raise GraniteRetrievalError("first and repeated passage vectors differ")

        index_payload = {
            "schema_version": "tos_granite_r2_vector_index_v1",
            "model_id": MODEL_ID,
            "repository_revision": MODEL_REVISION,
            "vector_dimension": VECTOR_SIZE,
            "pooling": "CLS",
            "normalization": "L2",
            "distance": "cosine-via-normalized-dot-product",
            "passages": [
                {
                    "sample_id": passage["sample_id"],
                    "source_anchor_ref": passage["source_anchor_ref"],
                    "item_ref": passage["item_ref"],
                    "language": passage["language"],
                    "unit": passage["unit"],
                    "text_sha256": passage["text_sha256"],
                    "vector": first_passage_vectors[str(passage["sample_id"])],
                }
                for passage in nonempty_passages
            ],
            "authority_boundary": "rebuildable local projection; source text and relevance remain external",
        }
        initial_absent = not index_path.exists()
        if not initial_absent:
            raise GraniteRetrievalError("run-local Granite index already exists before execution")
        first_write_started = time.perf_counter()
        _write_canonical_json(index_path, index_payload)
        first_write_seconds = time.perf_counter() - first_write_started
        first_index_sha256 = _sha256_file(index_path)
        first_index_bytes = index_path.stat().st_size

        delete_started = time.perf_counter()
        _safe_remove_index(index_path, run_root)
        deletion_seconds = time.perf_counter() - delete_started
        absent_after_delete = not index_path.exists()
        if not absent_after_delete:
            raise GraniteRetrievalError("Granite index deletion proof failed")

        rebuilt_payload = json.loads(_canonical_json(index_payload))
        for passage in rebuilt_payload["passages"]:
            passage["vector"] = rebuilt_passage_vectors[str(passage["sample_id"])]
        rebuild_started = time.perf_counter()
        _write_canonical_json(index_path, rebuilt_payload)
        rebuild_write_seconds = time.perf_counter() - rebuild_started
        rebuilt_index_sha256 = _sha256_file(index_path)
        rebuilt_index_bytes = index_path.stat().st_size
        if first_index_sha256 != rebuilt_index_sha256 or first_index_bytes != rebuilt_index_bytes:
            raise GraniteRetrievalError("first and rebuilt Granite indexes differ")

        first_query_latencies = bridge["timing"]["first_query_encoding"]["latencies_ms"]
        warm_query_latencies = bridge["timing"]["warm_query_encoding"]["latencies_ms"]
        if len(first_query_latencies) != len(query_ids) or len(warm_query_latencies) != len(
            query_ids
        ):
            raise GraniteRetrievalError("bridge query timing identities differ from the query set")

        result_refs: list[str] = []
        ranking_latencies_ms: list[float] = []
        warm_ranking_latencies_ms: list[float] = []
        expectation_hits = 0
        evaluable_queries = 0
        hard_negative_presence = 0
        hard_negative_slots = 0
        stable_rankings = 0
        cross_lingual = {"queries": 0, "model_proposed_expected_hits": 0}
        for position, query_id in enumerate(query_ids):
            plan_query = plan_queries[query_id]
            query = content_queries[query_id]
            rank_started = time.perf_counter()
            results = _rank_passages(
                first_query_vectors[query_id], nonempty_passages, first_passage_vectors
            )
            rank_ms = (time.perf_counter() - rank_started) * 1000
            warm_rank_started = time.perf_counter()
            warm_results = _rank_passages(
                warm_query_vectors[query_id], nonempty_passages, rebuilt_passage_vectors
            )
            warm_rank_ms = (time.perf_counter() - warm_rank_started) * 1000
            ranking_latencies_ms.append(rank_ms)
            warm_ranking_latencies_ms.append(warm_rank_ms)
            anchors = [str(result["source_anchor_ref"]) for result in results]
            warm_anchors = [str(result["source_anchor_ref"]) for result in warm_results]
            ranking_stable = anchors == warm_anchors
            stable_rankings += ranking_stable
            expected = list(plan_query["expected_source_anchor_refs"])
            hard_negatives = list(plan_query["hard_negative_anchor_refs"])
            expected_ranks = _expected_ranks(expected, anchors)
            if plan_query["expected_behavior"] != "coverage-failure":
                evaluable_queries += 1
                expectation_hits += bool(expected_ranks)
            if plan_query["category"] == "cross-lingual":
                cross_lingual["queries"] += 1
                cross_lingual["model_proposed_expected_hits"] += bool(expected_ranks)
            hard_negative_slots += len(hard_negatives)
            hard_negative_presence += sum(anchor in anchors for anchor in hard_negatives)
            result_path = run_root / "raw-output/query-results" / f"{query_id}.json"
            _write_json(
                result_path,
                {
                    "query_id": query_id,
                    "query_text": str(query["text"]),
                    "query_category": plan_query["category"],
                    "query_language": plan_query["query_language"],
                    "intended_target_language": plan_query["intended_target_language"],
                    "expected_behavior": plan_query["expected_behavior"],
                    "model_proposed_expected_source_anchor_refs": expected,
                    "model_proposed_hard_negative_anchor_refs": hard_negatives,
                    "model_proposed_expected_ranks": expected_ranks,
                    "query_embedding_latency_ms": first_query_latencies[position],
                    "warm_query_embedding_latency_ms": warm_query_latencies[position],
                    "ranking_latency_ms": rank_ms,
                    "warm_ranking_latency_ms": warm_rank_ms,
                    "result_anchor_refs": anchors,
                    "warm_result_anchor_refs": warm_anchors,
                    "ranking_stable_across_repeat": ranking_stable,
                    "results": results,
                    "judgment_status": "unreviewed-model-proposed-expectations-only",
                    "authority_boundary": "rankings and advisory diagnostics; no human relevance judgment",
                },
            )
            result_refs.append(result_path.relative_to(run_root).as_posix())

        passage_manifest_path = run_root / "inputs/source-passage-manifest.json"
        _write_json(
            passage_manifest_path,
            {
                "schema_version": "tos_granite_passage_manifest_v1",
                "source_structure_run_ref": structure_run_root.as_posix(),
                "source_structure_runner_digest": structure_receipt["method_revision"][
                    "artifact_digest"
                ],
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
                "authority_boundary": "digest inventory only; source text remains in Structure A",
            },
        )
        runtime_path = run_root / "receipts/granite-runtime-and-model.json"
        _write_json(
            runtime_path,
            {
                "schema_version": "tos_granite_runtime_and_model_v1",
                "captured_at_utc": started_at,
                "runtime": runtime,
                "model": model,
                "bridge_runtime": bridge["runtime"],
                "model_io": bridge["model_io"],
                "network_used_during_inference": False,
                "remote_code_executed": False,
                "authority_boundary": "runtime and artifact identity only; no retrieval quality claim",
            },
        )
        embedding_path = run_root / "receipts/granite-embedding.json"
        _write_json(
            embedding_path,
            {
                "schema_version": "tos_granite_embedding_receipt_v1",
                "model_id": MODEL_ID,
                "repository_revision": MODEL_REVISION,
                "passage_count": len(nonempty_passages),
                "query_count": len(query_ids),
                "vector_dimension": VECTOR_SIZE,
                "batch_size": BATCH_SIZE,
                "max_length": MAX_LENGTH,
                "pooling": "CLS",
                "normalization": "L2",
                "timing": bridge["timing"],
                "bridge_peak_rss_bytes": bridge["bridge_peak_rss_bytes"],
                "input_policy": "identical raw nonempty Structure A text and frozen query content used by A/B",
                "authority_boundary": "vectors are replaceable projections; no semantic or relevance acceptance",
            },
        )
        lifecycle_path = run_root / "receipts/granite-index-lifecycle.json"
        _write_json(
            lifecycle_path,
            {
                "schema_version": "tos_granite_index_lifecycle_v1",
                "index_ref": INDEX_RELATIVE_PATH.as_posix(),
                "initial_absent": initial_absent,
                "first_materialization": {
                    "write_seconds": first_write_seconds,
                    "bytes": first_index_bytes,
                    "sha256": first_index_sha256,
                    "passage_count": len(nonempty_passages),
                },
                "deletion_proof": {
                    "delete_seconds": deletion_seconds,
                    "absent_after_delete": absent_after_delete,
                },
                "rebuild": {
                    "write_seconds": rebuild_write_seconds,
                    "bytes": rebuilt_index_bytes,
                    "sha256": rebuilt_index_sha256,
                    "passage_count": len(nonempty_passages),
                },
                "digest_stable": first_index_sha256 == rebuilt_index_sha256,
                "retained_for_manual_review": True,
                "authority_boundary": "isolated rebuildable vector projection; never source authority",
            },
        )
        invocation_path = run_root / "receipts/granite-invocation.json"
        _write_json(
            invocation_path,
            {
                "captured_at_utc": started_at,
                "argv": invocation,
                "host_python": platform.python_version(),
                "runner_sha256": _sha256_file(Path(__file__)),
                "bridge_sha256": _sha256_file(BRIDGE_PATH),
                "runtime_manifest_sha256": runtime["runtime_manifest_sha256"],
                "model_revision": MODEL_REVISION,
                "model_artifact_count": model["artifact_count"],
                "model_artifact_bytes": model["artifact_bytes"],
                "structure_run_receipt_sha256": _sha256_file(
                    structure_run_root / "run.receipt.json"
                ),
                "query_plan_sha256": _sha256_file(query_plan_path),
                "query_content_sha256": _sha256_file(query_content_path),
                "network_posture": "model and query execution local-only",
            },
        )

        packet_bytes = sum(
            path.stat().st_size
            for path in run_root.rglob("*")
            if path.is_file() and path != receipt_path
        )
        first_end_to_end = [
            float(embed) + rank
            for embed, rank in zip(first_query_latencies, ranking_latencies_ms, strict=True)
        ]
        warm_end_to_end = [
            float(embed) + rank
            for embed, rank in zip(
                warm_query_latencies, warm_ranking_latencies_ms, strict=True
            )
        ]
        metrics = {
            "schema_version": "tos_granite_retrieval_metrics_v1",
            "experiment_id": receipt["experiment_id"],
            "variant": "C",
            "query_count": len(query_ids),
            "passage_count": len(passages),
            "indexed_passage_count": len(nonempty_passages),
            "empty_passage_count": len(passages) - len(nonempty_passages),
            "model_read_seconds": bridge["timing"]["model_read_seconds"],
            "model_compile_seconds": bridge["timing"]["model_compile_seconds"],
            "first_passage_embedding_seconds": bridge["timing"][
                "first_passage_encoding"
            ]["total_seconds"],
            "repeated_passage_embedding_seconds": bridge["timing"][
                "rebuilt_passage_encoding"
            ]["total_seconds"],
            "first_query_end_to_end_latency_ms_median": statistics.median(first_end_to_end),
            "warm_query_end_to_end_latency_ms_median": statistics.median(warm_end_to_end),
            "index_bytes": rebuilt_index_bytes,
            "packet_bytes": packet_bytes,
            "model_artifact_bytes": model["artifact_bytes"],
            "bridge_peak_rss_bytes": bridge["bridge_peak_rss_bytes"],
            "host_runner_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * 1024,
            "repeat_ranking_stability": {
                "stable_queries": stable_rankings,
                "queries": len(query_ids),
                "status": "mechanical-repeat-only-not-relevance",
            },
            "model_proposed_target_presence": {
                "queries_with_expected_anchor": expectation_hits,
                "evaluable_queries": evaluable_queries,
                "status": "advisory-nonhuman-not-a-quality-score",
            },
            "model_proposed_hard_negative_presence": {
                "present": hard_negative_presence,
                "declared_slots": hard_negative_slots,
                "status": "advisory-nonhuman-not-a-false-positive-rate",
            },
            "cross_lingual": {
                **cross_lingual,
                "status": "model-proposed-target-presence-only",
            },
            "quality": {
                "ndcg_at_10": None,
                "hard_negative_error_rate": None,
                "reason": "human relevance judgments have not started",
            },
            "human_cost": {
                "judgment_minutes": None,
                "correction_minutes": None,
                "reason": "no real human relevance review has occurred",
            },
            "traceability": {
                "source_anchored_ranked_results": len(query_ids) * TOP_K,
                "ranked_results": len(query_ids) * TOP_K,
                "status": "mechanically-resolved-unreviewed",
            },
            "index_lifecycle": {
                "delete_and_rebuild_proven": True,
                "digest_stable": True,
                "retained_for_manual_review": True,
            },
            "total_runner_seconds": time.perf_counter() - started,
            "authority_boundary": "quality fields are null until human source-visible relevance review",
        }
        metrics_path = run_root / "metrics/granite-retrieval-summary.json"
        _write_json(metrics_path, metrics)

        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = sorted(
            {str(passage["sample_id"]) for passage in passages} | set(query_ids)
        )
        receipt["method_revision"] = {
            "implementation": "Granite R2 CLS+L2 OpenVINO embeddings with local cosine projection",
            "version": MODEL_REVISION,
            "runtime": f"OpenVINO {runtime['openvino']} CPU; tokenizers {runtime['tokenizers']}",
            "model": MODEL_ID,
            "artifact_digest": _sha256_file(Path(__file__)),
        }
        receipt["invocation_ref"] = invocation_path.relative_to(run_root).as_posix()
        receipt["artifact_refs"] = sorted(
            result_refs
            + [
                index_path.relative_to(run_root).as_posix(),
                passage_manifest_path.relative_to(run_root).as_posix(),
                runtime_path.relative_to(run_root).as_posix(),
                embedding_path.relative_to(run_root).as_posix(),
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
        try:
            _safe_remove_index(index_path, run_root)
        except Exception as cleanup_exc:  # preserve the primary failure
            cleanup_error = str(cleanup_exc)
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)] + (
            [f"index cleanup failed: {cleanup_error}"] if cleanup_error else []
        )
        _write_json(receipt_path, receipt)
        if isinstance(exc, GraniteRetrievalError):
            raise
        raise GraniteRetrievalError(str(exc)) from exc
