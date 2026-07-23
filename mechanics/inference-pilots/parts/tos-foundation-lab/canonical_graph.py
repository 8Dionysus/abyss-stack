#!/usr/bin/env python3
"""Execute the canonical claim-record graph baseline without a graph database."""

from __future__ import annotations

import hashlib
import json
import platform
import resource
import statistics
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CanonicalGraphError(RuntimeError):
    """Raised when the frozen canonical graph run is not executable."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalGraphError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CanonicalGraphError(f"{path} must contain a JSON object")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CanonicalGraphError(f"cannot read {path}: {exc}") from exc
    records: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CanonicalGraphError(f"cannot parse {path}:{number}: {exc}") from exc
        if not isinstance(record, dict):
            raise CanonicalGraphError(f"{path}:{number} must contain a JSON object")
        records.append(record)
    return records


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    path.write_text(text, encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def graph_layer(claim: dict[str, Any]) -> str:
    claim_type = claim.get("claim_type")
    if claim_type == "bibliographic":
        return "bibliographic"
    if claim_type in {"textual", "linguistic"}:
        return "textual"
    if claim_type in {"translation", "semantic", "lived_witness", "canon"}:
        return "interpretive"
    return "provenance"


def build_claim_index(claims: list[dict[str, Any]]) -> dict[str, Any]:
    by_id: dict[str, dict[str, Any]] = {}
    by_subject_predicate: dict[tuple[str, str], list[str]] = defaultdict(list)
    by_layer: dict[str, list[str]] = defaultdict(list)
    by_review: dict[str, list[str]] = defaultdict(list)
    reverse_alternatives: dict[str, set[str]] = defaultdict(set)

    for claim in claims:
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or claim_id in by_id:
            raise CanonicalGraphError(f"duplicate or invalid claim_id: {claim_id}")
        by_id[claim_id] = claim
        subject = claim.get("subject_ref")
        predicate = claim.get("predicate")
        if isinstance(subject, str) and isinstance(predicate, str):
            by_subject_predicate[(subject, predicate)].append(claim_id)
        by_layer[graph_layer(claim)].append(claim_id)
        review_status = str(claim.get("review_status"))
        by_review[review_status].append(claim_id)
        for alternative in claim.get("alternative_claim_refs", []):
            if isinstance(alternative, str):
                reverse_alternatives[alternative].add(claim_id)

    for claim_id, claim in by_id.items():
        for alternative in claim.get("alternative_claim_refs", []):
            if alternative not in by_id:
                raise CanonicalGraphError(
                    f"claim {claim_id} references absent alternative {alternative}"
                )

    return {
        "by_id": by_id,
        "by_subject_predicate": {
            key: sorted(value) for key, value in by_subject_predicate.items()
        },
        "by_layer": {key: sorted(value) for key, value in by_layer.items()},
        "by_review": {key: sorted(value) for key, value in by_review.items()},
        "reverse_alternatives": reverse_alternatives,
    }


def build_reference_index(
    tree_repo_root: Path,
    claim_set_path: Path,
    claims: list[dict[str, Any]],
) -> dict[str, str]:
    """Index owner IDs to tracked ToS records without reading payload bytes."""

    tree_repo_root = tree_repo_root.resolve()
    source_root = tree_repo_root / "ToS/source-witnesses"
    if not source_root.is_dir():
        raise CanonicalGraphError(f"Tree of Sophia source-witness owner is absent: {source_root}")
    try:
        claim_set_ref = claim_set_path.resolve().relative_to(tree_repo_root).as_posix()
    except ValueError as exc:
        raise CanonicalGraphError("claim set must stay inside the Tree of Sophia repository") from exc

    references: dict[str, str] = {}

    def register(ref: object, path: Path) -> None:
        if not isinstance(ref, str):
            return
        location = path.resolve().relative_to(tree_repo_root).as_posix()
        previous = references.get(ref)
        if previous is not None and previous != location:
            raise CanonicalGraphError(
                f"owner reference {ref} appears in both {previous} and {location}"
            )
        references[ref] = location

    for claim in claims:
        claim_id = claim.get("claim_id")
        if isinstance(claim_id, str):
            references[claim_id] = claim_set_ref

    json_names = {
        "work.json",
        "expression.json",
        "edition.json",
        "collection.json",
        "item.json",
        "rights.json",
    }
    for path in sorted(source_root.rglob("*.json")):
        if path.name not in json_names or "local-content" in path.parts:
            continue
        payload = _load_json(path)
        register(payload.get("record_id"), path)
        register(payload.get("rights_id"), path)

    jsonl_names = {
        "provenance.jsonl",
        "graph-provenance.jsonl",
        "anchors.jsonl",
        "translation-anchors.jsonl",
        "membership-claims.jsonl",
    }
    for path in sorted(source_root.rglob("*.jsonl")):
        if path.name not in jsonl_names or path.resolve() == claim_set_path.resolve():
            continue
        for record in _load_jsonl(path):
            for field in ("event_id", "anchor_id", "claim_id"):
                register(record.get(field), path)
    return dict(sorted(references.items()))


def _resolve_reference(
    ref: str,
    tree_repo_root: Path,
    reference_index: dict[str, str],
) -> dict[str, Any]:
    if ref.startswith("ToS/"):
        path = (tree_repo_root / ref).resolve()
        try:
            path.relative_to(tree_repo_root.resolve())
        except ValueError:
            return {"ref": ref, "kind": "repo_path", "resolved": False, "location": None}
        return {
            "ref": ref,
            "kind": "repo_path",
            "resolved": path.is_file(),
            "location": ref if path.is_file() else None,
        }
    if ref.startswith("tos."):
        location = reference_index.get(ref)
        return {
            "ref": ref,
            "kind": "tos_id",
            "resolved": location is not None,
            "location": location,
        }
    return {"ref": ref, "kind": "untyped", "resolved": False, "location": None}


def _claim_nodes(claims: list[dict[str, Any]]) -> list[str]:
    nodes: set[str] = set()
    for claim in claims:
        for value in (claim.get("subject_ref"), claim.get("object")):
            if isinstance(value, str) and value.startswith("tos."):
                nodes.add(value)
    return sorted(nodes)


def _claim_family(seed: str, index: dict[str, Any]) -> list[str]:
    by_id = index["by_id"]
    if seed not in by_id:
        raise CanonicalGraphError(f"claim-family seed is absent: {seed}")
    seen: set[str] = set()
    queue: deque[str] = deque([seed])
    while queue:
        claim_id = queue.popleft()
        if claim_id in seen:
            continue
        seen.add(claim_id)
        claim = by_id[claim_id]
        neighbors = set(claim.get("alternative_claim_refs", []))
        neighbors.update(index["reverse_alternatives"].get(claim_id, set()))
        queue.extend(sorted(neighbors - seen))
    return sorted(seen)


def _claim_path(
    start_ref: str,
    end_ref: str,
    maximum_claim_hops: int,
    claims: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for claim in claims:
        subject = claim.get("subject_ref")
        target = claim.get("object")
        claim_id = claim.get("claim_id")
        if (
            isinstance(subject, str)
            and isinstance(target, str)
            and target.startswith("tos.")
            and isinstance(claim_id, str)
        ):
            adjacency[subject].append((target, claim_id))
    for edges in adjacency.values():
        edges.sort(key=lambda edge: (edge[0], edge[1]))

    queue: deque[tuple[str, list[str], list[str]]] = deque([(start_ref, [start_ref], [])])
    best_depth: dict[str, int] = {start_ref: 0}
    while queue:
        node, node_path, claim_path = queue.popleft()
        if node == end_ref:
            return claim_path, node_path
        if len(claim_path) >= maximum_claim_hops:
            continue
        for target, claim_id in adjacency.get(node, []):
            depth = len(claim_path) + 1
            if best_depth.get(target, maximum_claim_hops + 1) < depth:
                continue
            best_depth[target] = depth
            queue.append((target, [*node_path, target], [*claim_path, claim_id]))
    return [], []


def _trace_record(
    claim: dict[str, Any],
    tree_repo_root: Path,
    reference_index: dict[str, str],
) -> dict[str, Any]:
    maker = claim.get("maker")
    reviews = claim.get("reviews")
    subject_ref = claim.get("subject_ref")
    object_value = claim.get("object")
    provenance_ref = claim.get("provenance_event_ref")
    evidence_refs = claim.get("evidence_refs")
    subject_resolution = (
        _resolve_reference(subject_ref, tree_repo_root, reference_index)
        if isinstance(subject_ref, str)
        else {"ref": subject_ref, "kind": "invalid", "resolved": False, "location": None}
    )
    if isinstance(object_value, str) and object_value.startswith("tos."):
        object_resolution = _resolve_reference(object_value, tree_repo_root, reference_index)
    else:
        object_resolution = {
            "ref": object_value,
            "kind": "literal",
            "resolved": object_value is not None,
            "location": None,
        }
    provenance_resolution = (
        _resolve_reference(provenance_ref, tree_repo_root, reference_index)
        if isinstance(provenance_ref, str)
        else {"ref": provenance_ref, "kind": "invalid", "resolved": False, "location": None}
    )
    evidence_resolutions = [
        _resolve_reference(ref, tree_repo_root, reference_index)
        for ref in evidence_refs or []
        if isinstance(ref, str)
    ]
    traceable = bool(
        isinstance(claim.get("claim_id"), str)
        and isinstance(subject_ref, str)
        and isinstance(claim.get("predicate"), str)
        and isinstance(evidence_refs, list)
        and evidence_refs
        and isinstance(maker, dict)
        and isinstance(maker.get("agent_ref"), str)
        and isinstance(provenance_ref, str)
        and isinstance(claim.get("review_status"), str)
        and isinstance(reviews, list)
        and subject_resolution["resolved"]
        and object_resolution["resolved"]
        and provenance_resolution["resolved"]
        and len(evidence_resolutions) == len(evidence_refs)
        and all(item["resolved"] for item in evidence_resolutions)
    )
    return {
        "claim_ref": claim.get("claim_id"),
        "graph_layer": graph_layer(claim),
        "subject_ref": subject_ref,
        "predicate": claim.get("predicate"),
        "object": object_value,
        "maker": maker,
        "provenance_event_ref": provenance_ref,
        "evidence_refs": evidence_refs,
        "resolution": {
            "subject": subject_resolution,
            "object": object_resolution,
            "provenance_event": provenance_resolution,
            "evidence": evidence_resolutions,
        },
        "review_status": claim.get("review_status"),
        "review_count": len(reviews) if isinstance(reviews, list) else None,
        "traceable": traceable,
        "authority_boundary": "trace closure and review-state visibility, not claim truth",
    }


def execute_query(
    query: dict[str, Any],
    claims: list[dict[str, Any]],
    index: dict[str, Any],
    tree_repo_root: Path,
    reference_index: dict[str, str],
) -> dict[str, Any]:
    operation = query["operation"]
    parameters = query["parameters"]
    returned_claim_refs: list[str]
    returned_node_refs: list[str]
    detail: dict[str, Any] = {}

    if operation == "subject_predicate":
        key = (str(parameters["subject_ref"]), str(parameters["predicate"]))
        returned_claim_refs = list(index["by_subject_predicate"].get(key, []))
        returned_node_refs = _claim_nodes([index["by_id"][ref] for ref in returned_claim_refs])
        returned_node_refs = [ref for ref in returned_node_refs if ref != key[0]]
    elif operation == "claim_family":
        returned_claim_refs = _claim_family(str(parameters["seed_claim_ref"]), index)
        returned_node_refs = _claim_nodes([index["by_id"][ref] for ref in returned_claim_refs])
    elif operation == "path":
        returned_claim_refs, returned_node_refs = _claim_path(
            str(parameters["start_ref"]),
            str(parameters["end_ref"]),
            int(parameters["maximum_claim_hops"]),
            claims,
        )
    elif operation == "layer_inventory":
        returned_claim_refs = []
        returned_node_refs = sorted(index["by_layer"])
        detail["layer_claim_refs"] = index["by_layer"]
    elif operation == "review_inventory":
        review_status = str(parameters["review_status"])
        returned_claim_refs = list(index["by_review"].get(review_status, []))
        returned_node_refs = []
        detail["review_status"] = review_status
    elif operation == "traceability_inventory":
        traces = [
            _trace_record(claim, tree_repo_root, reference_index) for claim in claims
        ]
        returned_claim_refs = sorted(
            str(trace["claim_ref"]) for trace in traces if trace["traceable"]
        )
        returned_node_refs = []
        detail["traceable_claim_count"] = len(returned_claim_refs)
        detail["untraceable_claim_refs"] = sorted(
            str(trace["claim_ref"]) for trace in traces if not trace["traceable"]
        )
    else:
        raise CanonicalGraphError(f"unsupported graph query operation: {operation}")

    expected_claims = sorted(query["expected_claim_refs"])
    expected_nodes = sorted(query["expected_node_refs"])
    return {
        "query_id": query["query_id"],
        "question": query["question"],
        "operation": operation,
        "parameters": parameters,
        "returned_claim_refs": returned_claim_refs,
        "returned_node_refs": returned_node_refs,
        "detail": detail,
        "model_proposed_expected_claim_refs": expected_claims,
        "model_proposed_expected_node_refs": expected_nodes,
        "model_proposed_expectation_match": (
            sorted(returned_claim_refs) == expected_claims
            and sorted(returned_node_refs) == expected_nodes
        ),
        "judgment_status": "unreviewed-model-proposed-expectations-only",
        "authority_boundary": "deterministic query output only; no human answer or claim acceptance",
    }


def execute_canonical_graph(
    run_root: Path,
    tree_repo_root: Path,
    claim_set_path: Path,
    query_plan_path: Path,
    *,
    invocation: list[str],
) -> dict[str, Any]:
    """Execute Graph A over one frozen claim and query set."""

    run_root = run_root.resolve()
    tree_repo_root = tree_repo_root.resolve()
    claim_set_path = claim_set_path.resolve()
    query_plan_path = query_plan_path.resolve()
    receipt_path = run_root / "run.receipt.json"
    receipt = _load_json(receipt_path)
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if receipt.get("experiment_id") != "tos-graph-projection-v1" or receipt.get("variant") != "A":
        raise CanonicalGraphError("canonical graph runner requires prepared Graph A")
    if receipt.get("status") != "prepared" or preflight.get("decision") != "ready":
        raise CanonicalGraphError("run must be prepared from a ready preflight")
    if experiment.get("family") != "graph":
        raise CanonicalGraphError("experiment specification is not graph")

    query_plan = _load_json(query_plan_path)
    if query_plan.get("frozen_before_variant_outputs") is not True:
        raise CanonicalGraphError("graph query plan was not frozen before outputs")
    if _sha256_file(claim_set_path) != query_plan.get("claim_set_sha256"):
        raise CanonicalGraphError("claim-set digest differs from frozen graph query plan")
    claims = _load_jsonl(claim_set_path)
    if len(claims) != 13:
        raise CanonicalGraphError(f"expected 13 frozen claims, found {len(claims)}")
    queries = query_plan.get("queries")
    if not isinstance(queries, list) or len(queries) != 10:
        raise CanonicalGraphError("graph query plan must contain 10 frozen questions")
    predicates = {str(claim.get("predicate")) for claim in claims}
    if predicates != set(query_plan.get("allowed_predicates", [])):
        raise CanonicalGraphError("claim predicates differ from frozen allowlist")

    started_at = _utc_now()
    receipt["status"] = "running"
    receipt["started_at_utc"] = started_at
    _write_json(receipt_path, receipt)
    try:
        build_started = time.perf_counter()
        index = build_claim_index(claims)
        reference_index = build_reference_index(tree_repo_root, claim_set_path, claims)
        build_seconds = time.perf_counter() - build_started

        canonical_path = run_root / "raw-output/canonical-claims.jsonl"
        _write_jsonl(canonical_path, claims)
        trace_records = [
            _trace_record(claim, tree_repo_root, reference_index) for claim in claims
        ]
        trace_path = run_root / "raw-output/edge-trace.jsonl"
        _write_jsonl(trace_path, trace_records)
        index_path = run_root / "raw-output/claim-index.json"
        _write_json(
            index_path,
            {
                "schema_version": "tos_canonical_claim_index_v1",
                "claim_set_sha256": _sha256_file(claim_set_path),
                "claim_count": len(claims),
                "claim_refs_by_layer": index["by_layer"],
                "claim_refs_by_review_status": index["by_review"],
                "predicate_inventory": sorted(predicates),
                "known_limits": [
                    "all claims are unreviewed laboratory inputs",
                    "literal objects and identity references remain typed only by their claim records",
                    "this baseline is not a graph database or canonical promotion surface",
                ],
            },
        )
        reference_index_path = run_root / "raw-output/reference-index.json"
        _write_json(
            reference_index_path,
            {
                "schema_version": "tos_owner_reference_index_v1",
                "tree_repo_root": tree_repo_root.as_posix(),
                "reference_count": len(reference_index),
                "references": reference_index,
                "authority_boundary": "tracked owner-path resolution only; no content or claim acceptance",
            },
        )

        query_result_refs: list[str] = []
        query_latencies_ms: list[float] = []
        expectation_matches = 0
        for query in sorted(queries, key=lambda item: item["query_id"]):
            repeated: list[float] = []
            result: dict[str, Any] | None = None
            for _ in range(5):
                query_started = time.perf_counter()
                result = execute_query(
                    query,
                    claims,
                    index,
                    tree_repo_root,
                    reference_index,
                )
                repeated.append((time.perf_counter() - query_started) * 1000)
            assert result is not None
            result["warm_latency_ms_median_of_5"] = statistics.median(repeated)
            query_latencies_ms.append(result["warm_latency_ms_median_of_5"])
            expectation_matches += int(result["model_proposed_expectation_match"])
            result_path = run_root / "raw-output/query-results" / f"{query['query_id']}.json"
            _write_json(result_path, result)
            query_result_refs.append(result_path.relative_to(run_root).as_posix())

        traceable_count = sum(bool(record["traceable"]) for record in trace_records)
        layer_counts = {
            layer: len(index["by_layer"].get(layer, []))
            for layer in ("bibliographic", "textual", "provenance", "interpretive")
        }
        raw_output_bytes = sum(
            path.stat().st_size for path in (run_root / "raw-output").rglob("*") if path.is_file()
        )
        metrics = {
            "schema_version": "tos_canonical_graph_metrics_v1",
            "experiment_id": receipt["experiment_id"],
            "variant": "A",
            "claim_count": len(claims),
            "query_count": len(queries),
            "layer_claim_counts": layer_counts,
            "index_build_seconds": build_seconds,
            "warm_query_latency_ms_median": statistics.median(query_latencies_ms),
            "store_bytes": raw_output_bytes,
            "model_proposed_query_expectation_match": {
                "matches": expectation_matches,
                "queries": len(queries),
                "status": "advisory-nonhuman-not-a-quality-score",
            },
            "quality": {
                "query_answer_correctness": None,
                "competing_claim_survival": None,
                "reason": "human graph-answer and competing-claim review has not started",
            },
            "human_cost": {
                "trace_review_minutes": None,
                "reason": "no real human edge audit has occurred",
            },
            "traceability": {
                "traceable_claim_edges": traceable_count,
                "claim_edges": len(claims),
                "status": "mechanically-resolved-unreviewed",
            },
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "authority_boundary": "query, layer, and trace mechanics only; claim truth remains unreviewed",
        }
        metrics_path = run_root / "metrics/canonical-graph-summary.json"
        _write_json(metrics_path, metrics)
        invocation_path = run_root / "receipts/canonical-graph-invocation.json"
        _write_json(
            invocation_path,
            {
                "captured_at_utc": started_at,
                "argv": invocation,
                "python": platform.python_version(),
                "runner_sha256": _sha256_file(Path(__file__)),
                "claim_set_sha256": _sha256_file(claim_set_path),
                "query_plan_sha256": _sha256_file(query_plan_path),
                "tree_repo_root": tree_repo_root.as_posix(),
                "owner_reference_count": len(reference_index),
                "rights_posture": "metadata-and-unreviewed-claim-projection-local-runtime-only",
            },
        )

        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = sorted(query["query_id"] for query in queries)
        receipt["method_revision"] = {
            "implementation": "deterministic canonical claim query with live ToS owner-reference resolution",
            "version": "2",
            "runtime": f"Python {platform.python_version()}",
            "model": None,
            "artifact_digest": _sha256_file(Path(__file__)),
        }
        receipt["invocation_ref"] = invocation_path.relative_to(run_root).as_posix()
        receipt["artifact_refs"] = sorted(
            query_result_refs
            + [
                canonical_path.relative_to(run_root).as_posix(),
                trace_path.relative_to(run_root).as_posix(),
                index_path.relative_to(run_root).as_posix(),
                reference_index_path.relative_to(run_root).as_posix(),
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
        if isinstance(exc, CanonicalGraphError):
            raise
        raise CanonicalGraphError(str(exc)) from exc
