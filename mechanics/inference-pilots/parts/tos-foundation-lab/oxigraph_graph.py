#!/usr/bin/env python3
"""Execute the isolated Graph C RDF projection through pinned PyOxigraph."""

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
from oxigraph_bridge import query_catalog


class OxigraphGraphError(RuntimeError):
    """Raised when the frozen RDF projection is not executable."""


LAB_RUN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{7,95}$")
BRIDGE_PATH = Path(__file__).with_name("oxigraph_bridge.py")
ALLOWED_RUNTIME_ROOT = Path("/srv/abyss-machine/runtimes")
EXPECTED_PYOXIGRAPH_VERSION = "0.5.9"
EXPECTED_LICENSE = "MIT OR Apache-2.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OxigraphGraphError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise OxigraphGraphError(f"{path} must contain a JSON object")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise OxigraphGraphError(f"cannot read {path}: {exc}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise OxigraphGraphError(f"cannot parse {path}:{line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise OxigraphGraphError(f"{path}:{line_number} must contain a JSON object")
        records.append(record)
    return records


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _ref_kind(ref: object) -> str:
    if isinstance(ref, str) and ref.startswith("tos."):
        return "tos_id"
    if isinstance(ref, str) and ref.startswith("ToS/"):
        return "repo_path"
    return "literal"


def projection_row(claim: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    """Build a claim-first RDF input row without interpreting claim content."""

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
    }


def _runtime_fingerprint(runtime_python: Path, runtime_manifest: Path) -> dict[str, Any]:
    runtime_python = runtime_python.absolute()
    runtime_manifest = runtime_manifest.absolute()
    runtime_root = runtime_python.parent.parent
    if not runtime_root.resolve().is_relative_to(ALLOWED_RUNTIME_ROOT.resolve()):
        raise OxigraphGraphError("PyOxigraph interpreter is outside the host runtime root")
    if runtime_python != runtime_root / "bin/python":
        raise OxigraphGraphError("PyOxigraph interpreter must be the runtime-owned bin/python")
    if not runtime_python.is_file() or not (runtime_python.stat().st_mode & 0o111):
        raise OxigraphGraphError("PyOxigraph runtime interpreter is unavailable")
    manifest = _load_json(runtime_manifest)
    if Path(str(manifest.get("runtime_root", ""))).resolve() != runtime_root.resolve():
        raise OxigraphGraphError("runtime manifest does not own the supplied interpreter")
    if runtime_manifest.resolve() != (runtime_root / "runtime-manifest.json").resolve():
        raise OxigraphGraphError("runtime manifest must be the runtime-owned manifest path")
    package = manifest.get("package")
    if not isinstance(package, dict) or package.get("version") != EXPECTED_PYOXIGRAPH_VERSION:
        raise OxigraphGraphError("runtime manifest does not pin PyOxigraph 0.5.9")
    if package.get("license_expression") != EXPECTED_LICENSE:
        raise OxigraphGraphError("runtime manifest license expression differs from the reviewed license")
    probe = subprocess.run(
        (
            runtime_python.as_posix(),
            "-c",
            "import importlib.metadata,json,platform,pyoxigraph; "
            "m=importlib.metadata.metadata('pyoxigraph'); "
            "print(json.dumps({'python':platform.python_version(),'pyoxigraph':pyoxigraph.__version__,"
            "'license':m.get('License-Expression') or m.get('License'),'module':pyoxigraph.__file__}))",
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if probe.returncode != 0:
        raise OxigraphGraphError(f"cannot probe PyOxigraph runtime: {probe.stderr.strip()[:500]}")
    try:
        observed = json.loads(probe.stdout)
    except json.JSONDecodeError as exc:
        raise OxigraphGraphError("PyOxigraph runtime probe returned non-JSON") from exc
    if observed.get("pyoxigraph") != EXPECTED_PYOXIGRAPH_VERSION:
        raise OxigraphGraphError("installed PyOxigraph version differs from 0.5.9")
    if observed.get("license") != EXPECTED_LICENSE:
        raise OxigraphGraphError("installed PyOxigraph metadata license differs from review")
    return {
        **observed,
        "interpreter": runtime_python.as_posix(),
        "runtime_manifest": runtime_manifest.as_posix(),
        "runtime_manifest_sha256": _sha256_file(runtime_manifest),
        "wheel_sha256": package.get("wheel_sha256"),
        "source_revision": package.get("source_revision"),
        "release_date": package.get("release_date"),
    }


def _run_bridge(
    payload: dict[str, Any],
    *,
    runtime_python: Path,
    timeout: float = 300.0,
) -> dict[str, Any]:
    bridge_source = BRIDGE_PATH.read_text(encoding="utf-8")
    completed = subprocess.run(
        (runtime_python.as_posix(), "-c", bridge_source),
        input=json.dumps(payload, ensure_ascii=False),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    try:
        response = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise OxigraphGraphError(
            f"Oxigraph bridge returned non-JSON; stderr={completed.stderr.strip()[:1000]}"
        ) from exc
    if not isinstance(response, dict):
        raise OxigraphGraphError("Oxigraph bridge returned non-object JSON")
    if completed.returncode != 0 or response.get("ok") is not True:
        raise OxigraphGraphError(
            f"Oxigraph bridge failed: {response.get('error_type')}: {response.get('error')}"
        )
    return response


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _safe_remove_store(store_path: Path, run_root: Path) -> None:
    store_path = store_path.resolve()
    expected_parent = (run_root / "derived-store").resolve()
    if store_path.parent != expected_parent or store_path.name != "oxigraph":
        raise OxigraphGraphError("refusing to delete a non-canonical Oxigraph store path")
    if store_path.exists():
        shutil.rmtree(store_path)


def _semantic_query_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "query_id": result.get("query_id"),
            "operation": result.get("operation"),
            "returned_claim_refs": result.get("returned_claim_refs"),
            "returned_node_refs": result.get("returned_node_refs"),
            "detail": result.get("detail"),
        }
        for result in results
    ]


def execute_oxigraph_graph(
    run_root: Path,
    tree_repo_root: Path,
    claim_set_path: Path,
    query_plan_path: Path,
    runtime_python_path: Path,
    runtime_manifest_path: Path,
    *,
    lab_run: str,
    invocation: list[str],
) -> dict[str, Any]:
    """Execute Graph C as an isolated named-graph RDF dataset."""

    run_root = run_root.resolve()
    tree_repo_root = tree_repo_root.resolve()
    claim_set_path = claim_set_path.resolve()
    query_plan_path = query_plan_path.resolve()
    # Keep the venv-owned lexical path: resolving bin/python follows the normal
    # venv symlink to /usr/bin and would erase runtime ownership information.
    runtime_python_path = runtime_python_path.absolute()
    runtime_manifest_path = runtime_manifest_path.resolve()
    if not LAB_RUN_RE.fullmatch(lab_run):
        raise OxigraphGraphError("lab-run must be a unique lowercase RDF dataset key")
    receipt_path = run_root / "run.receipt.json"
    receipt = _load_json(receipt_path)
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if receipt.get("experiment_id") != "tos-graph-projection-v1" or receipt.get("variant") != "C":
        raise OxigraphGraphError("Oxigraph graph runner requires prepared Graph C")
    if receipt.get("status") != "prepared" or preflight.get("decision") != "ready":
        raise OxigraphGraphError("run must be prepared from a ready preflight")
    if experiment.get("family") != "graph":
        raise OxigraphGraphError("experiment specification is not graph")

    query_plan = _load_json(query_plan_path)
    if query_plan.get("frozen_before_variant_outputs") is not True:
        raise OxigraphGraphError("graph query plan was not frozen before outputs")
    if _sha256_file(claim_set_path) != query_plan.get("claim_set_sha256"):
        raise OxigraphGraphError("claim-set digest differs from frozen graph query plan")
    claims = _load_jsonl(claim_set_path)
    queries = query_plan.get("queries")
    if len(claims) != 13:
        raise OxigraphGraphError(f"expected 13 frozen claims, found {len(claims)}")
    if not isinstance(queries, list) or len(queries) != 10:
        raise OxigraphGraphError("graph query plan must contain 10 frozen questions")
    build_claim_index(claims)
    reference_index = build_reference_index(tree_repo_root, claim_set_path, claims)
    traces = [_trace_record(claim, tree_repo_root, reference_index) for claim in claims]
    if not all(trace.get("traceable") is True for trace in traces):
        raise OxigraphGraphError("canonical owner-reference trace closure failed before projection")
    projection_rows = [
        projection_row(claim, trace) for claim, trace in zip(claims, traces, strict=True)
    ]
    runtime = _runtime_fingerprint(runtime_python_path, runtime_manifest_path)

    store_path = run_root / "derived-store/oxigraph"
    if store_path.exists():
        raise OxigraphGraphError("run-local Oxigraph store already exists before execution")
    bridge_payload = {
        "lab_run": lab_run,
        "run_root": run_root.as_posix(),
        "store_path": store_path.as_posix(),
        "claims": projection_rows,
        "queries": queries,
    }
    started_at = _utc_now()
    started = time.perf_counter()
    receipt["status"] = "running"
    receipt["started_at_utc"] = started_at
    _write_json(receipt_path, receipt)
    try:
        initial_absent = not store_path.exists()
        first = _run_bridge(bridge_payload, runtime_python=runtime_python_path)
        first_inventory = first.get("inventory")
        first_queries = first.get("query_results")
        first_nquads = first.get("canonical_nquads")
        if not isinstance(first_inventory, dict) or not isinstance(first_queries, list):
            raise OxigraphGraphError("first Oxigraph build omitted inventory or query results")
        if not isinstance(first_nquads, str):
            raise OxigraphGraphError("first Oxigraph build omitted canonical N-Quads")
        first_dataset_path = run_root / "raw-output/dataset-first.nq"
        _write_text(first_dataset_path, first_nquads)

        delete_started = time.perf_counter()
        _safe_remove_store(store_path, run_root)
        deletion_seconds = time.perf_counter() - delete_started
        after_delete_absent = not store_path.exists()
        if not after_delete_absent:
            raise OxigraphGraphError("Oxigraph deletion proof failed")

        rebuilt = _run_bridge(bridge_payload, runtime_python=runtime_python_path)
        rebuilt_inventory = rebuilt.get("inventory")
        rebuilt_queries = rebuilt.get("query_results")
        rebuilt_nquads = rebuilt.get("canonical_nquads")
        if not isinstance(rebuilt_inventory, dict) or not isinstance(rebuilt_queries, list):
            raise OxigraphGraphError("rebuilt Oxigraph store omitted inventory or query results")
        if not isinstance(rebuilt_nquads, str):
            raise OxigraphGraphError("rebuilt Oxigraph store omitted canonical N-Quads")
        if first_inventory != rebuilt_inventory:
            raise OxigraphGraphError("first and rebuilt Oxigraph inventories differ")
        if _semantic_query_results(first_queries) != _semantic_query_results(rebuilt_queries):
            raise OxigraphGraphError("first and rebuilt Oxigraph query answers differ")
        if _sha256_text(first_nquads) != _sha256_text(rebuilt_nquads):
            raise OxigraphGraphError("first and rebuilt canonical RDF datasets differ")
        rebuilt_dataset_path = run_root / "raw-output/dataset-rebuilt.nq"
        _write_text(rebuilt_dataset_path, rebuilt_nquads)

        expected_layers = {
            "bibliographic": 4,
            "textual": 2,
            "provenance": 3,
            "interpretive": 4,
        }
        expected_inventory = {
            "claim_count": 13,
            "claim_graph_count": 13,
            "manifest_graph_count": 1,
            "named_graph_count": 14,
            "direct_assertion_count": 13,
            "evidence_statement_count": 25,
            "alternative_statement_count": 4,
            "literal_object_claim_count": 2,
            "claim_layers": expected_layers,
        }
        for key, expected in expected_inventory.items():
            if rebuilt_inventory.get(key) != expected:
                raise OxigraphGraphError(
                    f"Oxigraph inventory {key} differs: {rebuilt_inventory.get(key)!r} != {expected!r}"
                )

        query_by_id = {
            str(query["query_id"]): query for query in queries if isinstance(query, dict)
        }
        query_refs: list[str] = []
        first_latencies_ms: list[float] = []
        warm_latencies_ms: list[float] = []
        expectation_matches = 0
        traceable_claim_refs: list[str] = []
        for result in rebuilt_queries:
            query_id = str(result.get("query_id"))
            if query_id not in query_by_id:
                raise OxigraphGraphError("Oxigraph returned an unknown frozen query result")
            query = query_by_id[query_id]
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
            first_latencies_ms.append(float(result["first_query_ms"]))
            warm_latencies_ms.append(float(result["warm_latency_ms_median_of_5"]))
            output_path = run_root / "raw-output/query-results" / f"{query_id}.json"
            _write_json(
                output_path,
                {
                    "query_id": query_id,
                    "question": query["question"],
                    "operation": query["operation"],
                    "parameters": query["parameters"],
                    "returned_claim_refs": returned_claims,
                    "returned_node_refs": returned_nodes,
                    "detail": result.get("detail", {}),
                    "first_query_after_rebuild_ms": result["first_query_ms"],
                    "warm_latency_ms_median_of_5": result["warm_latency_ms_median_of_5"],
                    "model_proposed_expected_claim_refs": expected_claims,
                    "model_proposed_expected_node_refs": expected_nodes,
                    "model_proposed_expectation_match": expectation_match,
                    "judgment_status": "unreviewed-model-proposed-expectations-only",
                    "authority_boundary": "Oxigraph SPARQL output only; no human answer or claim acceptance",
                },
            )
            query_refs.append(output_path.relative_to(run_root).as_posix())
        if len(rebuilt_queries) != 10:
            raise OxigraphGraphError("Oxigraph did not return exactly 10 frozen query results")
        if len(traceable_claim_refs) != 13:
            raise OxigraphGraphError("Oxigraph trace closure did not return all 13 claims")

        projected_claims_path = run_root / "raw-output/projected-claims.jsonl"
        _write_jsonl(projected_claims_path, projection_rows)
        trace_path = run_root / "raw-output/edge-trace.jsonl"
        _write_jsonl(trace_path, traces)
        catalog_path = run_root / "raw-output/sparql-query-catalog.json"
        _write_json(
            catalog_path,
            {
                "schema_version": "tos_oxigraph_sparql_catalog_v1",
                "queries": rebuilt.get("query_catalog"),
                "catalog_sha256": hashlib.sha256(
                    _canonical_json(query_catalog()).encode("utf-8")
                ).hexdigest(),
                "path_method": "SPARQL claim-edge inventory followed by bounded deterministic BFS",
                "authority_boundary": "reproducible SPARQL mechanics, not answer truth",
            },
        )
        runtime_path = run_root / "receipts/oxigraph-runtime.json"
        _write_json(
            runtime_path,
            {
                "schema_version": "tos_oxigraph_runtime_receipt_v1",
                "captured_at_utc": started_at,
                **runtime,
                "runner_bridge_sha256": _sha256_file(BRIDGE_PATH),
                "license_review_status": "verified-for-bounded-research",
                "system_python_mutated": False,
            },
        )
        manifest_path = run_root / "raw-output/oxigraph-projection-manifest.json"
        _write_json(
            manifest_path,
            {
                "schema_version": "tos_oxigraph_claim_projection_manifest_v1",
                "lab_run": lab_run,
                "claim_set_sha256": _sha256_file(claim_set_path),
                "query_plan_sha256": _sha256_file(query_plan_path),
                "claim_count": len(claims),
                "reference_index_count": len(reference_index),
                "canonical_traceable_claim_count": sum(trace["traceable"] for trace in traces),
                "inventory": rebuilt_inventory,
                "mapping": rebuilt.get("mapping"),
                "literal_object_claim_refs": sorted(
                    row["claim_id"] for row in projection_rows if row["object_kind"] == "literal"
                ),
                "known_limits": [
                    "all projected claims remain unreviewed laboratory inputs",
                    "explicit claim resources and named graphs are a mapping choice, not an ontology verdict",
                    "RDF-star is deliberately not used as the claim authority model",
                    "the disk store is a replaceable derived projection and never claim authority",
                ],
            },
        )
        lifecycle_path = run_root / "receipts/oxigraph-store-lifecycle.json"
        store_bytes = _directory_bytes(store_path)
        lifecycle = {
            "schema_version": "tos_oxigraph_store_lifecycle_v1",
            "lab_run": lab_run,
            "initial_absent": initial_absent,
            "first_materialization": first_inventory,
            "first_build_seconds": first["build_seconds"],
            "first_dataset_sha256": _sha256_text(first_nquads),
            "deletion_seconds": deletion_seconds,
            "after_delete_absent": after_delete_absent,
            "rebuilt": rebuilt_inventory,
            "rebuild_seconds": rebuilt["build_seconds"],
            "rebuilt_dataset_sha256": _sha256_text(rebuilt_nquads),
            "retained": rebuilt_inventory,
            "retained_store_bytes": store_bytes,
            "retained_for_manual_review": True,
            "authority_boundary": "isolated replaceable RDF projection; Tree of Sophia remains owner",
        }
        _write_json(lifecycle_path, lifecycle)
        invocation_path = run_root / "receipts/oxigraph-invocation.json"
        _write_json(
            invocation_path,
            {
                "captured_at_utc": started_at,
                "argv": invocation,
                "host_python": platform.python_version(),
                "runner_sha256": _sha256_file(Path(__file__)),
                "bridge_sha256": _sha256_file(BRIDGE_PATH),
                "runtime_manifest_sha256": runtime["runtime_manifest_sha256"],
                "claim_set_sha256": _sha256_file(claim_set_path),
                "query_plan_sha256": _sha256_file(query_plan_path),
                "lab_run": lab_run,
                "rights_posture": "tracked metadata and claims only; no source payload bytes projected",
            },
        )

        projection_artifact_bytes = sum(
            path.stat().st_size
            for path in run_root.rglob("*")
            if path.is_file() and not path.is_relative_to(store_path) and path != receipt_path
        )
        metrics = {
            "schema_version": "tos_oxigraph_graph_metrics_v1",
            "experiment_id": receipt["experiment_id"],
            "variant": "C",
            "claim_count": len(claims),
            "query_count": len(queries),
            "layer_claim_counts": expected_layers,
            "first_materialization_seconds": first["build_seconds"],
            "deletion_seconds": deletion_seconds,
            "rebuild_seconds": rebuilt["build_seconds"],
            "first_query_after_rebuild_latency_ms": first_latencies_ms[0],
            "all_first_query_latency_ms_median": statistics.median(first_latencies_ms),
            "warm_query_latency_ms_median": statistics.median(warm_latencies_ms),
            "projection_artifact_bytes": projection_artifact_bytes,
            "isolated_store_bytes": store_bytes,
            "canonical_nquads_bytes": len(rebuilt_nquads.encode("utf-8")),
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
            "store_lifecycle": {
                "delete_and_rebuild_proven": True,
                "canonical_dataset_digest_stable": True,
                "retained_for_manual_review": True,
            },
            "total_runner_seconds": time.perf_counter() - started,
            "host_runner_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "runtime_ref": runtime_path.relative_to(run_root).as_posix(),
            "authority_boundary": "projection, SPARQL, and trace mechanics only; claim truth remains unreviewed",
        }
        metrics_path = run_root / "metrics/oxigraph-graph-summary.json"
        _write_json(metrics_path, metrics)

        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = sorted(query_by_id)
        receipt["method_revision"] = {
            "implementation": "explicit claim resources in one named RDF graph per claim",
            "version": f"PyOxigraph {runtime['pyoxigraph']}",
            "runtime": f"Python {runtime['python']} isolated disk Store",
            "model": None,
            "artifact_digest": _sha256_file(Path(__file__)),
        }
        receipt["invocation_ref"] = invocation_path.relative_to(run_root).as_posix()
        receipt["artifact_refs"] = sorted(
            query_refs
            + [
                first_dataset_path.relative_to(run_root).as_posix(),
                rebuilt_dataset_path.relative_to(run_root).as_posix(),
                projected_claims_path.relative_to(run_root).as_posix(),
                trace_path.relative_to(run_root).as_posix(),
                catalog_path.relative_to(run_root).as_posix(),
                runtime_path.relative_to(run_root).as_posix(),
                manifest_path.relative_to(run_root).as_posix(),
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
            _safe_remove_store(store_path, run_root)
        except Exception as cleanup_exc:  # preserve the primary failure
            cleanup_error = str(cleanup_exc)
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)] + (
            [f"store cleanup failed: {cleanup_error}"] if cleanup_error else []
        )
        _write_json(receipt_path, receipt)
        if isinstance(exc, OxigraphGraphError):
            raise
        raise OxigraphGraphError(str(exc)) from exc
