#!/usr/bin/env python3
"""Execute the isolated resident Neo4j property-graph projection variant."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import resource
import shutil
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from canonical_graph import (
    _trace_record,
    build_claim_index,
    build_reference_index,
    graph_layer,
)
from neo4j_bridge import query_catalog


class Neo4jGraphError(RuntimeError):
    """Raised when the frozen Neo4j graph projection is not executable."""


LAB_RUN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{7,95}$")
BRIDGE_PATH = Path(__file__).with_name("neo4j_bridge.py")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Neo4jGraphError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Neo4jGraphError(f"{path} must contain a JSON object")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Neo4jGraphError(f"cannot read {path}: {exc}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Neo4jGraphError(f"cannot parse {path}:{line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise Neo4jGraphError(f"{path}:{line_number} must contain a JSON object")
        records.append(record)
    return records


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _ref_kind(ref: object) -> str:
    if isinstance(ref, str) and ref.startswith("tos."):
        return "tos_id"
    if isinstance(ref, str) and ref.startswith("ToS/"):
        return "repo_path"
    return "literal"


def projection_row(claim: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    maker = claim.get("maker") if isinstance(claim.get("maker"), dict) else {}
    evidence_refs = [str(ref) for ref in claim.get("evidence_refs", []) if isinstance(ref, str)]
    alternatives = [
        str(ref) for ref in claim.get("alternative_claim_refs", []) if isinstance(ref, str)
    ]
    reviews = claim.get("reviews") if isinstance(claim.get("reviews"), list) else []
    object_value = claim.get("object")
    return {
        "claim_id": str(claim["claim_id"]),
        "claim_type": str(claim["claim_type"]),
        "assertion_layer": str(claim["assertion_layer"]),
        "layer": graph_layer(claim),
        "subject_ref": str(claim["subject_ref"]),
        "subject_kind": _ref_kind(claim["subject_ref"]),
        "predicate": str(claim["predicate"]),
        "object_ref": str(object_value),
        "object_kind": _ref_kind(object_value),
        "maker_ref": str(maker.get("agent_ref")),
        "provenance_event_ref": str(claim["provenance_event_ref"]),
        "evidence_refs": evidence_refs,
        "evidence_count": len(evidence_refs),
        "alternative_claim_refs": alternatives,
        "review_status": str(claim["review_status"]),
        "review_count": len(reviews),
        "epistemic_status": str(claim["epistemic_status"]),
        "visibility": str(claim["visibility"]),
        "canonical_traceable": bool(trace.get("traceable")),
        "payload_json": _canonical_json(claim),
    }


def _run_bridge(payload: dict[str, Any], *, timeout: float = 300.0) -> dict[str, Any]:
    podman = shutil.which("podman")
    if podman is None:
        raise Neo4jGraphError("podman is required for the credential-contained Neo4j bridge")
    bridge_source = BRIDGE_PATH.read_text(encoding="utf-8")
    completed = subprocess.run(
        (podman, "exec", "-i", "rag-api", "python", "-c", bridge_source),
        input=json.dumps(payload, ensure_ascii=False),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    try:
        response = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise Neo4jGraphError(
            f"Neo4j bridge returned non-JSON; stderr={completed.stderr.strip()[:1000]}"
        ) from exc
    if not isinstance(response, dict):
        raise Neo4jGraphError("Neo4j bridge returned non-object JSON")
    if completed.returncode != 0 or response.get("ok") is not True:
        raise Neo4jGraphError(
            f"Neo4j bridge failed: {response.get('error_type')}: {response.get('error')}"
        )
    return response


def _container_fingerprint(name: str) -> dict[str, Any]:
    podman = shutil.which("podman")
    if podman is None:
        raise Neo4jGraphError("podman is required to fingerprint resident services")
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
        raise Neo4jGraphError(f"cannot inspect {name}: {completed.stderr.strip()}")
    lines = completed.stdout.splitlines()
    if len(lines) != 3:
        raise Neo4jGraphError(f"unexpected inspect output for {name}")
    return {
        "container": name,
        "image_name": lines[0],
        "image_id": lines[1],
        "started_at": lines[2],
    }


def _container_stats(name: str) -> dict[str, Any]:
    podman = shutil.which("podman")
    if podman is None:
        return {"available": False}
    completed = subprocess.run(
        (
            podman,
            "stats",
            "--no-stream",
            "--format",
            "{{.CPU}}|{{.MemUsage}}|{{.MemPerc}}|{{.BlockInput}}|{{.BlockOutput}}",
            name,
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        return {"available": False, "reason": completed.stderr.strip()[:500]}
    fields = completed.stdout.strip().split("|")
    if len(fields) != 5:
        return {"available": False, "reason": "unexpected podman stats shape"}
    return {
        "available": True,
        "cpu": fields[0],
        "memory_usage": fields[1],
        "memory_percent": fields[2],
        "block_input": fields[3],
        "block_output": fields[4],
        "measurement_boundary": "resident whole-container snapshot, not isolated incremental lab cost",
    }


def execute_neo4j_graph(
    run_root: Path,
    tree_repo_root: Path,
    claim_set_path: Path,
    query_plan_path: Path,
    *,
    lab_run: str,
    invocation: list[str],
) -> dict[str, Any]:
    """Execute Graph B in an isolated property namespace inside resident Neo4j."""

    run_root = run_root.resolve()
    tree_repo_root = tree_repo_root.resolve()
    claim_set_path = claim_set_path.resolve()
    query_plan_path = query_plan_path.resolve()
    if not LAB_RUN_RE.fullmatch(lab_run):
        raise Neo4jGraphError("lab-run must be a unique lowercase Neo4j namespace key")
    receipt_path = run_root / "run.receipt.json"
    receipt = _load_json(receipt_path)
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if receipt.get("experiment_id") != "tos-graph-projection-v1" or receipt.get("variant") != "B":
        raise Neo4jGraphError("Neo4j graph runner requires prepared Graph B")
    if receipt.get("status") != "prepared" or preflight.get("decision") != "ready":
        raise Neo4jGraphError("run must be prepared from a ready preflight")
    if experiment.get("family") != "graph":
        raise Neo4jGraphError("experiment specification is not graph")

    query_plan = _load_json(query_plan_path)
    if query_plan.get("frozen_before_variant_outputs") is not True:
        raise Neo4jGraphError("graph query plan was not frozen before outputs")
    if _sha256_file(claim_set_path) != query_plan.get("claim_set_sha256"):
        raise Neo4jGraphError("claim-set digest differs from frozen graph query plan")
    claims = _load_jsonl(claim_set_path)
    queries = query_plan.get("queries")
    if len(claims) != 13:
        raise Neo4jGraphError(f"expected 13 frozen claims, found {len(claims)}")
    if not isinstance(queries, list) or len(queries) != 10:
        raise Neo4jGraphError("graph query plan must contain 10 frozen questions")
    build_claim_index(claims)
    reference_index = build_reference_index(tree_repo_root, claim_set_path, claims)
    traces = [_trace_record(claim, tree_repo_root, reference_index) for claim in claims]
    if not all(trace.get("traceable") is True for trace in traces):
        raise Neo4jGraphError("canonical owner-reference trace closure failed before projection")
    projection_rows = [
        projection_row(claim, trace) for claim, trace in zip(claims, traces, strict=True)
    ]

    started_at = _utc_now()
    started = time.perf_counter()
    receipt["status"] = "running"
    receipt["started_at_utc"] = started_at
    _write_json(receipt_path, receipt)
    try:
        stats_before = _container_stats("abyss_neo4j_1")
        bridge_result = _run_bridge(
            {
                "operation": "run_lab",
                "lab_run": lab_run,
                "claims": projection_rows,
                "queries": queries,
            }
        )
        lifecycle = bridge_result.get("lifecycle")
        bridge_queries = bridge_result.get("query_results")
        if not isinstance(lifecycle, dict) or not isinstance(bridge_queries, list):
            raise Neo4jGraphError("Neo4j bridge omitted lifecycle or query results")
        initial = lifecycle.get("initial", {})
        after_delete = lifecycle.get("after_delete", {})
        first_counts = lifecycle.get("first_materialization", {})
        rebuilt_counts = lifecycle.get("rebuilt", {})
        retained_counts = lifecycle.get("retained", {})
        if initial.get("node_count") != 0 or initial.get("relationship_count") != 0:
            raise Neo4jGraphError("Neo4j namespace was not absent before import")
        if after_delete.get("node_count") != 0 or after_delete.get("relationship_count") != 0:
            raise Neo4jGraphError("Neo4j namespace deletion proof failed")
        if first_counts != rebuilt_counts or rebuilt_counts != retained_counts:
            raise Neo4jGraphError("Neo4j first, rebuilt, and retained counts differ")
        if rebuilt_counts.get("claim_count") != len(claims):
            raise Neo4jGraphError("Neo4j rebuilt claim count differs from frozen claim set")

        expected_layers = {"bibliographic": 4, "textual": 2, "provenance": 3, "interpretive": 4}
        inventory = lifecycle.get("rebuilt_inventory", {})
        if inventory.get("claim_layers") != expected_layers:
            raise Neo4jGraphError(
                f"Neo4j layer inventory differs from frozen layers: {inventory.get('claim_layers')}"
            )
        required_relationship_types = {
            "TOS_LAB_ALTERNATIVE_TO",
            "TOS_LAB_ASSERTS",
            "TOS_LAB_GENERATED_BY",
            "TOS_LAB_HAS_EVIDENCE",
            "TOS_LAB_HAS_OBJECT",
            "TOS_LAB_HAS_SUBJECT",
            "TOS_LAB_MADE_BY",
        }
        observed_relationship_types = set(inventory.get("relationship_types", {}))
        if observed_relationship_types != required_relationship_types:
            raise Neo4jGraphError("Neo4j relationship type inventory is incomplete or unexpected")

        query_by_id = {
            str(query["query_id"]): query for query in queries if isinstance(query, dict)
        }
        query_refs: list[str] = []
        warm_latencies_ms: list[float] = []
        first_latencies_ms: list[float] = []
        expectation_matches = 0
        traceable_claim_refs: list[str] = []
        for result in bridge_queries:
            if not isinstance(result, dict) or result.get("query_id") not in query_by_id:
                raise Neo4jGraphError("Neo4j returned an unknown frozen query result")
            query = query_by_id[str(result["query_id"])]
            returned_claims = list(result.get("returned_claim_refs", []))
            returned_nodes = list(result.get("returned_node_refs", []))
            expected_claims = list(query["expected_claim_refs"])
            expected_nodes = list(query["expected_node_refs"])
            expectation_match = (
                sorted(returned_claims) == sorted(expected_claims)
                and sorted(returned_nodes) == sorted(expected_nodes)
            )
            expectation_matches += expectation_match
            if query["operation"] == "traceability_inventory":
                traceable_claim_refs = sorted(returned_claims)
            first_latencies_ms.append(float(result["first_query_after_rebuild_ms"]))
            warm_latencies_ms.append(float(result["warm_latency_ms_median_of_5"]))
            output_path = run_root / "raw-output/query-results" / f"{query['query_id']}.json"
            _write_json(
                output_path,
                {
                    "query_id": query["query_id"],
                    "question": query["question"],
                    "operation": query["operation"],
                    "parameters": query["parameters"],
                    "returned_claim_refs": returned_claims,
                    "returned_node_refs": returned_nodes,
                    "detail": result.get("detail", {}),
                    "first_query_after_rebuild_ms": result["first_query_after_rebuild_ms"],
                    "warm_latency_ms_median_of_5": result["warm_latency_ms_median_of_5"],
                    "model_proposed_expected_claim_refs": expected_claims,
                    "model_proposed_expected_node_refs": expected_nodes,
                    "model_proposed_expectation_match": expectation_match,
                    "judgment_status": "unreviewed-model-proposed-expectations-only",
                    "authority_boundary": "Neo4j query output only; no human answer or claim acceptance",
                },
            )
            query_refs.append(output_path.relative_to(run_root).as_posix())
        if len(bridge_queries) != 10:
            raise Neo4jGraphError("Neo4j did not return exactly 10 frozen query results")
        if len(traceable_claim_refs) != 13:
            raise Neo4jGraphError("Neo4j relationship trace closure did not return all 13 claims")

        projected_claims_path = run_root / "raw-output/projected-claims.jsonl"
        _write_jsonl(projected_claims_path, projection_rows)
        trace_path = run_root / "raw-output/edge-trace.jsonl"
        _write_jsonl(trace_path, traces)
        query_catalog_path = run_root / "raw-output/cypher-query-catalog.json"
        _write_json(
            query_catalog_path,
            {
                "schema_version": "tos_neo4j_query_catalog_v1",
                "queries": bridge_result.get("query_catalog"),
                "bridge_catalog_sha256": hashlib.sha256(
                    _canonical_json(query_catalog()).encode("utf-8")
                ).hexdigest(),
                "authority_boundary": "reproducible Cypher mechanics, not answer truth",
            },
        )
        lifecycle_path = run_root / "receipts/neo4j-namespace-lifecycle.json"
        _write_json(
            lifecycle_path,
            {
                "schema_version": "tos_neo4j_namespace_lifecycle_v1",
                "lab_run": lab_run,
                **lifecycle,
                "authority_boundary": "isolated replaceable database projection; Tree of Sophia remains owner",
            },
        )
        stats_after = _container_stats("abyss_neo4j_1")
        service_path = run_root / "receipts/neo4j-service.json"
        neo4j_container = _container_fingerprint("abyss_neo4j_1")
        bridge_container = _container_fingerprint("rag-api")
        _write_json(
            service_path,
            {
                "schema_version": "tos_neo4j_service_receipt_v1",
                "captured_at_utc": started_at,
                "neo4j_container": neo4j_container,
                "credential_bridge_container": bridge_container,
                "server": bridge_result.get("server"),
                "neo4j_driver_version": bridge_result.get("neo4j_driver_version"),
                "bridge_sha256": _sha256_file(BRIDGE_PATH),
                "stats_before": stats_before,
                "stats_after": stats_after,
                "credentials_persisted_in_artifacts": False,
                "credential_boundary": "credentials stayed inside the resident rag-api container environment",
            },
        )
        manifest_path = run_root / "raw-output/neo4j-import-manifest.json"
        _write_json(
            manifest_path,
            {
                "schema_version": "tos_neo4j_claim_projection_manifest_v1",
                "lab_run": lab_run,
                "claim_set_sha256": _sha256_file(claim_set_path),
                "query_plan_sha256": _sha256_file(query_plan_path),
                "claim_count": len(claims),
                "reference_index_count": len(reference_index),
                "canonical_traceable_claim_count": sum(trace["traceable"] for trace in traces),
                "counts": retained_counts,
                "inventory": inventory,
                "literal_object_claim_refs": sorted(
                    row["claim_id"] for row in projection_rows if row["object_kind"] == "literal"
                ),
                "known_limits": [
                    "all projected claims remain unreviewed laboratory inputs",
                    "Neo4j Community shares one database, so isolation uses a unique lab_run property and lab-only labels",
                    "exact incremental database bytes are unavailable in the shared resident store",
                    "database relationships are replaceable projections and never claim authority",
                ],
            },
        )

        artifact_bytes = sum(
            path.stat().st_size
            for path in run_root.rglob("*")
            if path.is_file() and path != receipt_path
        )
        metrics = {
            "schema_version": "tos_neo4j_graph_metrics_v1",
            "experiment_id": receipt["experiment_id"],
            "variant": "B",
            "claim_count": len(claims),
            "query_count": len(queries),
            "layer_claim_counts": expected_layers,
            "first_materialization_seconds": lifecycle["first_build_seconds"],
            "deletion_seconds": lifecycle["delete_seconds"],
            "rebuild_seconds": lifecycle["rebuild_seconds"],
            "first_query_after_rebuild_latency_ms": first_latencies_ms[0],
            "all_first_query_latency_ms_median": statistics.median(first_latencies_ms),
            "warm_query_latency_ms_median": statistics.median(warm_latencies_ms),
            "projection_artifact_bytes": artifact_bytes,
            "shared_database_incremental_bytes": None,
            "shared_database_incremental_bytes_reason": "Neo4j Community resident database is shared; exact lab-only store bytes are not exposed",
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
                "traceable_claim_edges": len(traceable_claim_refs),
                "claim_edges": len(claims),
                "status": "mechanically-resolved-unreviewed",
            },
            "competing_claim_families": {
                "mechanically_preserved": 2,
                "declared": 2,
                "status": "query-visible-unreviewed",
            },
            "namespace_lifecycle": {
                "delete_and_rebuild_proven": True,
                "retained_for_manual_review": True,
            },
            "total_runner_seconds": time.perf_counter() - started,
            "host_runner_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "resident_service_cost_ref": service_path.relative_to(run_root).as_posix(),
            "authority_boundary": "projection, query, and trace mechanics only; claim truth remains unreviewed",
        }
        metrics_path = run_root / "metrics/neo4j-graph-summary.json"
        _write_json(metrics_path, metrics)
        invocation_path = run_root / "receipts/neo4j-invocation.json"
        _write_json(
            invocation_path,
            {
                "captured_at_utc": started_at,
                "argv": invocation,
                "python": platform.python_version(),
                "runner_sha256": _sha256_file(Path(__file__)),
                "bridge_sha256": _sha256_file(BRIDGE_PATH),
                "claim_set_sha256": _sha256_file(claim_set_path),
                "query_plan_sha256": _sha256_file(query_plan_path),
                "lab_run": lab_run,
                "rights_posture": "tracked metadata and claims only; no source payload bytes projected",
            },
        )

        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = sorted(query_by_id)
        receipt["method_revision"] = {
            "implementation": "isolated claim-first property projection in resident Neo4j",
            "version": f"Neo4j {bridge_result.get('server', {}).get('version')}",
            "runtime": (
                f"Python {platform.python_version()} host runner + "
                f"neo4j-driver {bridge_result.get('neo4j_driver_version')} credential bridge"
            ),
            "model": None,
            "artifact_digest": _sha256_file(Path(__file__)),
        }
        receipt["invocation_ref"] = invocation_path.relative_to(run_root).as_posix()
        receipt["artifact_refs"] = sorted(
            query_refs
            + [
                projected_claims_path.relative_to(run_root).as_posix(),
                trace_path.relative_to(run_root).as_posix(),
                query_catalog_path.relative_to(run_root).as_posix(),
                lifecycle_path.relative_to(run_root).as_posix(),
                service_path.relative_to(run_root).as_posix(),
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
        cleanup_error = None
        try:
            _run_bridge({"operation": "cleanup", "lab_run": lab_run}, timeout=120)
        except Exception as cleanup_exc:  # preserve the primary failure
            cleanup_error = str(cleanup_exc)
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)] + ([f"namespace cleanup failed: {cleanup_error}"] if cleanup_error else [])
        _write_json(receipt_path, receipt)
        if isinstance(exc, Neo4jGraphError):
            raise
        raise Neo4jGraphError(str(exc)) from exc
