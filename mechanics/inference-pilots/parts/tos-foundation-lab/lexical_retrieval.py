#!/usr/bin/env python3
"""Execute the explainable SQLite FTS5 retrieval baseline."""

from __future__ import annotations

import hashlib
import json
import platform
import resource
import sqlite3
import statistics
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LexicalRetrievalError(RuntimeError):
    """Raised when the frozen lexical retrieval run is not executable."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LexicalRetrievalError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise LexicalRetrievalError(f"{path} must contain a JSON object")
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


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _language_for_item(item_ref: str) -> str:
    if ".de-" in item_ref or ".de." in item_ref:
        return "de"
    return "ru"


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _query_rows(connection: sqlite3.Connection, expression: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        rows = connection.execute(
            """
            SELECT sample_id, anchor_ref, language, item_ref, unit,
                   bm25(passages_fts) AS score,
                   snippet(passages_fts, 5, '[', ']', ' … ', 24) AS snippet
              FROM passages_fts
             WHERE passages_fts MATCH ?
             ORDER BY score
             LIMIT ?
            """,
            (expression, limit),
        ).fetchall()
    except sqlite3.Error as exc:
        raise LexicalRetrievalError(f"FTS5 query failed for {expression!r}: {exc}") from exc
    return [
        {
            "rank": index,
            "sample_id": row[0],
            "source_anchor_ref": row[1],
            "language": row[2],
            "item_ref": row[3],
            "unit": json.loads(row[4]),
            "score": row[5],
            "snippet": row[6],
        }
        for index, row in enumerate(rows, start=1)
    ]


def _build_index(database_path: Path, passages: list[dict[str, Any]]) -> float:
    started = time.perf_counter()
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            """
            CREATE VIRTUAL TABLE passages_fts USING fts5(
              sample_id UNINDEXED,
              anchor_ref UNINDEXED,
              language UNINDEXED,
              item_ref UNINDEXED,
              unit UNINDEXED,
              exact_text,
              normalized_text,
              lemma,
              phrase,
              prefix,
              section,
              page,
              edition,
              translation,
              sign_candidate,
              tokenize='unicode61 remove_diacritics 0'
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO passages_fts(
              sample_id, anchor_ref, language, item_ref, unit,
              exact_text, normalized_text, lemma, phrase, prefix,
              section, page, edition, translation, sign_candidate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    passage["sample_id"],
                    passage["anchor_ref"],
                    passage["language"],
                    passage["item_ref"],
                    json.dumps(passage["unit"], ensure_ascii=False, sort_keys=True),
                    passage["exact_text"],
                    passage["normalized_text"],
                    "",
                    "",
                    passage["normalized_text"],
                    "",
                    passage["page"],
                    passage["item_ref"],
                    passage["item_ref"] if passage["language"] == "ru" else "",
                    "",
                )
                for passage in passages
            ],
        )
        connection.execute("INSERT INTO passages_fts(passages_fts) VALUES ('optimize')")
        connection.commit()
    except sqlite3.Error as exc:
        raise LexicalRetrievalError(f"cannot build FTS5 index: {exc}") from exc
    finally:
        connection.close()
    return time.perf_counter() - started


def execute_lexical_retrieval(
    run_root: Path,
    structure_run_root: Path,
    query_plan_path: Path,
    query_content_path: Path,
    *,
    invocation: list[str],
) -> dict[str, Any]:
    """Execute Retrieval A without converting proposed judgments into gold."""

    run_root = run_root.resolve()
    structure_run_root = structure_run_root.resolve()
    query_plan_path = query_plan_path.resolve()
    query_content_path = query_content_path.resolve()
    receipt_path = run_root / "run.receipt.json"
    receipt = _load_json(receipt_path)
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if receipt.get("experiment_id") != "tos-retrieval-foundation-v1" or receipt.get("variant") != "A":
        raise LexicalRetrievalError("lexical runner requires prepared Retrieval A")
    if receipt.get("status") != "prepared" or preflight.get("decision") != "ready":
        raise LexicalRetrievalError("run must be prepared from a ready preflight")
    if experiment.get("family") != "retrieval":
        raise LexicalRetrievalError("experiment specification is not retrieval")

    structure_receipt = _load_json(structure_run_root / "run.receipt.json")
    if (
        structure_receipt.get("experiment_id") != "tos-structure-recovery-v1"
        or structure_receipt.get("variant") != "A"
        or structure_receipt.get("status") != "awaiting-manual-review"
    ):
        raise LexicalRetrievalError("source structure run is not the preserved unpromoted Structure A packet")

    query_plan = _load_json(query_plan_path)
    query_content = _load_json(query_content_path)
    if query_plan.get("frozen_before_variant_outputs") is not True:
        raise LexicalRetrievalError("query plan was not frozen before outputs")
    if _sha256_file(query_content_path) != query_plan.get("query_content_sha256"):
        raise LexicalRetrievalError("local query content digest differs from tracked query plan")
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
        raise LexicalRetrievalError("tracked and local query sets do not contain the same 20 IDs")

    started_at = _utc_now()
    receipt["status"] = "running"
    receipt["started_at_utc"] = started_at
    _write_json(receipt_path, receipt)
    try:
        passages: list[dict[str, Any]] = []
        for metadata_path in sorted((structure_run_root / "raw-output").glob("tos-sample-*.json")):
            metadata = _load_json(metadata_path)
            text_path = structure_run_root / str(metadata.get("native_text_ref"))
            if _sha256_file(text_path) != metadata.get("native_text_sha256"):
                raise LexicalRetrievalError(f"source structure output digest drift: {text_path}")
            text = text_path.read_text(encoding="utf-8")
            item_ref = str(metadata["item_ref"])
            unit = metadata["unit"]
            page = str(unit.get("page") or unit.get("container_member") or "")
            passages.append(
                {
                    "sample_id": metadata["sample_id"],
                    "anchor_ref": metadata["anchor_ref"],
                    "item_ref": item_ref,
                    "language": _language_for_item(item_ref),
                    "unit": unit,
                    "page": page,
                    "exact_text": text,
                    "normalized_text": normalize_text(text),
                    "text_sha256": metadata["native_text_sha256"],
                }
            )
        if len(passages) != 36:
            raise LexicalRetrievalError(f"expected 36 frozen passages, found {len(passages)}")

        database_path = run_root / "raw-output/fts5-index.sqlite3"
        build_seconds = _build_index(database_path, passages)
        result_refs: list[str] = []
        cold_latencies_ms: list[float] = []
        warm_latencies_ms: list[float] = []
        diagnostic_hits = 0
        diagnostic_evaluable = 0
        total_ranked = 0
        for query_id in sorted(content_queries):
            query = content_queries[query_id]
            plan_query = plan_queries[query_id]
            expression = str(query["fts5_query"])

            cold_started = time.perf_counter()
            cold_connection = sqlite3.connect(database_path)
            try:
                rows = _query_rows(cold_connection, expression)
            finally:
                cold_connection.close()
            cold_ms = (time.perf_counter() - cold_started) * 1000
            cold_latencies_ms.append(cold_ms)

            warm_connection = sqlite3.connect(database_path)
            try:
                repeated: list[float] = []
                for _ in range(5):
                    warm_started = time.perf_counter()
                    _query_rows(warm_connection, expression)
                    repeated.append((time.perf_counter() - warm_started) * 1000)
            finally:
                warm_connection.close()
            warm_ms = _median(repeated)
            assert warm_ms is not None
            warm_latencies_ms.append(warm_ms)

            result_anchors = [row["source_anchor_ref"] for row in rows]
            expected = list(plan_query["expected_source_anchor_refs"])
            expected_ranks = {
                anchor: result_anchors.index(anchor) + 1
                for anchor in expected
                if anchor in result_anchors
            }
            behavior = plan_query["expected_behavior"]
            if behavior in {"positive", "hard-negative-identification"}:
                diagnostic_evaluable += 1
                if expected_ranks:
                    diagnostic_hits += 1
            total_ranked += len(rows)
            result_path = run_root / "raw-output/query-results" / f"{query_id}.json"
            _write_json(
                result_path,
                {
                    "query_id": query_id,
                    "query_text": query["text"],
                    "fts5_query": expression,
                    "query_category": plan_query["category"],
                    "query_language": plan_query["query_language"],
                    "intended_target_language": plan_query["intended_target_language"],
                    "expected_behavior": behavior,
                    "model_proposed_expected_source_anchor_refs": expected,
                    "model_proposed_hard_negative_anchor_refs": plan_query["hard_negative_anchor_refs"],
                    "model_proposed_expected_ranks": expected_ranks,
                    "cold_connection_latency_ms": cold_ms,
                    "warm_connection_latency_ms_median_of_5": warm_ms,
                    "results": rows,
                    "judgment_status": "unreviewed-model-proposed-expectations-only",
                    "authority_boundary": "ranked output and advisory diagnostics; no human relevance judgment",
                },
            )
            result_refs.append(result_path.relative_to(run_root).as_posix())

        manifest_path = run_root / "raw-output/index-manifest.json"
        nonempty = sum(bool(passage["normalized_text"]) for passage in passages)
        _write_json(
            manifest_path,
            {
                "schema_version": "tos_fts5_index_manifest_v1",
                "database_ref": database_path.relative_to(run_root).as_posix(),
                "database_sha256": _sha256_file(database_path),
                "source_structure_run_ref": structure_run_root.as_posix(),
                "source_structure_runner_digest": structure_receipt["method_revision"]["artifact_digest"],
                "passage_count": len(passages),
                "nonempty_passage_count": nonempty,
                "field_population": {
                    "exact_form": nonempty,
                    "normalized_form": nonempty,
                    "lemma": 0,
                    "phrase": 0,
                    "prefix_stream": nonempty,
                    "section": 0,
                    "page_or_member": len(passages),
                    "language": len(passages),
                    "edition_or_item": len(passages),
                    "translation_witness": sum(passage["language"] == "ru" for passage in passages),
                    "sign_candidate": 0,
                },
                "known_limits": [
                    "index includes unaccepted native text-layer and auto-OCR outputs",
                    "twelve Antonovsky outline-PDF passages are empty",
                    "lemma, phrase, canonical section, and sign fields are intentionally unpopulated",
                    "source index is a replaceable projection, never the text authority",
                ],
            },
        )

        metrics = {
            "schema_version": "tos_fts5_retrieval_metrics_v1",
            "experiment_id": receipt["experiment_id"],
            "variant": "A",
            "query_count": len(content_queries),
            "passage_count": len(passages),
            "nonempty_passage_count": nonempty,
            "empty_passage_count": len(passages) - nonempty,
            "index_build_seconds": build_seconds,
            "index_bytes": database_path.stat().st_size,
            "connection_cold_latency_ms_median": _median(cold_latencies_ms),
            "warm_latency_ms_median": _median(warm_latencies_ms),
            "ranked_result_count": total_ranked,
            "model_proposed_expected_hit_at_10": {
                "hits": diagnostic_hits,
                "evaluable_queries": diagnostic_evaluable,
                "status": "advisory-nonhuman-not-a-quality-score",
            },
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
                "ranked_results_with_source_anchor": total_ranked,
                "ranked_result_count": total_ranked,
                "status": "mechanically-resolved-unreviewed",
            },
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "authority_boundary": "speed, size, and ranked output only; relevance remains unreviewed",
        }
        metrics_path = run_root / "metrics/fts5-retrieval-summary.json"
        _write_json(metrics_path, metrics)
        invocation_path = run_root / "receipts/fts5-invocation.json"
        _write_json(
            invocation_path,
            {
                "captured_at_utc": started_at,
                "argv": invocation,
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
                "runner_sha256": _sha256_file(Path(__file__)),
                "query_plan_sha256": _sha256_file(query_plan_path),
                "query_content_sha256": _sha256_file(query_content_path),
                "source_structure_run_ref": structure_run_root.as_posix(),
                "rights_posture": "restricted-derived-text-and-query-content-private-runtime-only",
            },
        )

        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = sorted(content_queries)
        receipt["method_revision"] = {
            "implementation": "SQLite FTS5 deterministic lexical baseline",
            "version": f"SQLite {sqlite3.sqlite_version}",
            "runtime": f"Python {platform.python_version()}",
            "model": None,
            "artifact_digest": _sha256_file(Path(__file__)),
        }
        receipt["invocation_ref"] = invocation_path.relative_to(run_root).as_posix()
        receipt["artifact_refs"] = sorted(
            result_refs
            + [
                database_path.relative_to(run_root).as_posix(),
                manifest_path.relative_to(run_root).as_posix(),
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
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)]
        _write_json(receipt_path, receipt)
        if isinstance(exc, LexicalRetrievalError):
            raise
        raise LexicalRetrievalError(str(exc)) from exc
