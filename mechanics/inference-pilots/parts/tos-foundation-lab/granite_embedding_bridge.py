#!/usr/bin/env python3
"""Runtime-side bridge for the pinned Granite R2 OpenVINO embedding lane.

The host runner sends one JSON object on stdin and receives one JSON object on
stdout. Heavy runtime imports stay inside the isolated interpreter. This file
does not download models, execute remote code, or assign retrieval relevance.
"""

from __future__ import annotations

import json
import math
import resource
import sys
import time
from pathlib import Path
from typing import Any


def _rounded_normalized_rows(values: Any) -> list[list[float]]:
    """Return stable unit rows while rejecting zero or non-finite vectors."""

    if isinstance(values, (str, bytes)):
        raise ValueError("expected a two-dimensional embedding matrix")
    try:
        raw_rows = []
        for source_row in values:
            if isinstance(source_row, (str, bytes)):
                raise TypeError
            raw_rows.append(list(source_row))
    except TypeError as exc:
        raise ValueError("expected a two-dimensional embedding matrix") from exc
    if not raw_rows:
        raise ValueError("expected a non-empty two-dimensional embedding matrix")
    width = len(raw_rows[0])
    if width == 0 or any(len(row) != width for row in raw_rows):
        raise ValueError("expected a rectangular two-dimensional embedding matrix")

    normalized: list[list[float]] = []
    for raw_row in raw_rows:
        try:
            row = [float(value) for value in raw_row]
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("embedding output contains non-numeric values") from exc
        if not all(math.isfinite(value) for value in row):
            raise ValueError("embedding output contains non-finite or zero-norm rows")
        norm = math.hypot(*row)
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError("embedding output contains non-finite or zero-norm rows")
        normalized.append([round(value / norm, 9) for value in row])
    return normalized


def _io_record(port: Any) -> dict[str, Any]:
    names = sorted(str(name) for name in port.get_names())
    return {
        "names": names,
        "element_type": str(port.get_element_type()),
        "partial_shape": str(port.get_partial_shape()),
    }


def _encode_batch(
    compiled_model: Any,
    tokenizer: Any,
    texts: list[str],
) -> tuple[list[list[float]], list[int]]:
    import numpy as np

    encodings = tokenizer.encode_batch(texts)
    input_ids = np.asarray([encoding.ids for encoding in encodings], dtype=np.int64)
    attention_mask = np.asarray(
        [encoding.attention_mask for encoding in encodings], dtype=np.int64
    )
    outputs = compiled_model({"input_ids": input_ids, "attention_mask": attention_mask})
    hidden = outputs[compiled_model.output(0)]
    if hidden.ndim != 3 or hidden.shape[0] != len(texts) or hidden.shape[2] != 768:
        raise ValueError(f"unexpected last_hidden_state shape: {hidden.shape}")
    vectors = _rounded_normalized_rows(hidden[:, 0, :])
    token_counts = [sum(encoding.attention_mask) for encoding in encodings]
    return vectors, token_counts


def _encode_batches(
    compiled_model: Any,
    tokenizer: Any,
    rows: list[dict[str, Any]],
    *,
    batch_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    encoded: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    token_counts: list[int] = []
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        before = time.perf_counter()
        vectors, counts = _encode_batch(
            compiled_model,
            tokenizer,
            [str(row["text"]) for row in batch],
        )
        latencies_ms.append((time.perf_counter() - before) * 1000)
        token_counts.extend(counts)
        for row, vector, token_count in zip(batch, vectors, counts, strict=True):
            encoded.append(
                {
                    "id": str(row["id"]),
                    "vector": vector,
                    "token_count": token_count,
                }
            )
    return encoded, {
        "batch_size": batch_size,
        "batch_count": len(latencies_ms),
        "batch_latencies_ms": latencies_ms,
        "total_seconds": sum(latencies_ms) / 1000,
        "token_count_min": min(token_counts) if token_counts else 0,
        "token_count_max": max(token_counts) if token_counts else 0,
        "token_count_total": sum(token_counts),
    }


def _encode_queries(
    compiled_model: Any,
    tokenizer: Any,
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    encoded: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    for row in rows:
        before = time.perf_counter()
        vectors, counts = _encode_batch(compiled_model, tokenizer, [str(row["text"])])
        latencies_ms.append((time.perf_counter() - before) * 1000)
        encoded.append(
            {
                "id": str(row["id"]),
                "vector": vectors[0],
                "token_count": counts[0],
            }
        )
    return encoded, {
        "latencies_ms": latencies_ms,
        "total_seconds": sum(latencies_ms) / 1000,
    }


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    import openvino
    import tokenizers
    from openvino import Core
    from tokenizers import Tokenizer

    if payload.get("operation") != "encode-frozen-retrieval":
        raise ValueError("unsupported bridge operation")
    model_xml = Path(str(payload["model_xml"]))
    tokenizer_path = Path(str(payload["tokenizer_json"]))
    passages = payload.get("passages")
    queries = payload.get("queries")
    batch_size = int(payload.get("batch_size", 6))
    max_length = int(payload.get("max_length", 512))
    device = str(payload.get("device", "CPU"))
    if not model_xml.is_file() or not tokenizer_path.is_file():
        raise ValueError("model IR or tokenizer file is missing")
    if not isinstance(passages, list) or not passages:
        raise ValueError("passages must be a non-empty list")
    if not isinstance(queries, list) or not queries:
        raise ValueError("queries must be a non-empty list")
    if batch_size < 1 or batch_size > 32 or max_length < 8 or max_length > 32768:
        raise ValueError("batch size or maximum length is outside the frozen bounds")

    tokenizer = Tokenizer.from_file(tokenizer_path.as_posix())
    tokenizer.enable_truncation(max_length=max_length, strategy="longest_first")
    tokenizer.enable_padding(
        direction="right",
        pad_id=0,
        pad_type_id=0,
        pad_token="<pad>",
    )

    core = Core()
    read_started = time.perf_counter()
    model = core.read_model(model_xml.as_posix())
    read_seconds = time.perf_counter() - read_started
    input_names = {name for port in model.inputs for name in port.get_names()}
    output_names = {name for port in model.outputs for name in port.get_names()}
    if input_names != {"input_ids", "attention_mask"}:
        raise ValueError(f"unexpected model inputs: {sorted(input_names)}")
    if "last_hidden_state" not in output_names or len(model.outputs) != 1:
        raise ValueError(f"unexpected model outputs: {sorted(output_names)}")

    compile_started = time.perf_counter()
    compiled = core.compile_model(
        model,
        device,
        {
            "INFERENCE_NUM_THREADS": 4,
        },
    )
    compile_seconds = time.perf_counter() - compile_started

    first_passages, first_passage_metrics = _encode_batches(
        compiled, tokenizer, passages, batch_size=batch_size
    )
    rebuilt_passages, rebuilt_passage_metrics = _encode_batches(
        compiled, tokenizer, passages, batch_size=batch_size
    )
    first_queries, first_query_metrics = _encode_queries(compiled, tokenizer, queries)
    warm_queries, warm_query_metrics = _encode_queries(compiled, tokenizer, queries)

    if first_passages != rebuilt_passages:
        raise ValueError("first and repeated passage vectors differ after stable rounding")

    return {
        "ok": True,
        "schema_version": "tos_granite_embedding_bridge_v1",
        "runtime": {
            "python": sys.version.split()[0],
            "openvino": openvino.__version__,
            "numpy": np.__version__,
            "tokenizers": tokenizers.__version__,
            "device": device,
            "available_devices": list(core.available_devices),
        },
        "model_io": {
            "inputs": [_io_record(port) for port in model.inputs],
            "outputs": [_io_record(port) for port in model.outputs],
            "pooling": "last_hidden_state[:,0,:]",
            "normalization": "L2",
            "vector_dimension": 768,
            "max_length": max_length,
        },
        "timing": {
            "model_read_seconds": read_seconds,
            "model_compile_seconds": compile_seconds,
            "first_passage_encoding": first_passage_metrics,
            "rebuilt_passage_encoding": rebuilt_passage_metrics,
            "first_query_encoding": first_query_metrics,
            "warm_query_encoding": warm_query_metrics,
        },
        "first_passages": first_passages,
        "rebuilt_passages": rebuilt_passages,
        "first_queries": first_queries,
        "warm_queries": warm_queries,
        "bridge_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "authority_boundary": "embedding mechanics only; no retrieval relevance or semantic acceptance",
    }


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object")
        result = execute(payload)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
