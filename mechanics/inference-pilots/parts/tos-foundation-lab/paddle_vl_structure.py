#!/usr/bin/env python3
"""Execute frozen Structure C over output-blind rendered ToS pages."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ocr_render import OcrRenderError, validate_visual_plan, verify_render_manifest
from runtime_manifest import RuntimeManifestError, verify_runtime_manifest


EXPECTED_RUNTIME_ID = "paddleocr-vl-1.6-structure-ocr-cpu"
EXPECTED_SOFTWARE_SHA256 = {
    "paddleocr": "c0f0a81ad4112727f30c6fcf986ac0ef6a120d31ee0991a01fae0357ee32d338",
    "paddlex": "f1678bf650bbaccfd8f0d4e49d0ae631b4685c829fdae6e802ccd90d4fcb9a7f",
    "paddlepaddle-cpu": "9016fc497213e1101261684321fbb31ef5960019ef39cb07ded27bc70e2a9858",
    "PaddleOCR-VL-1.6": "85a479d506a11e724e7285d395c551be69f41dbc16b6342d3cacfb189aed71db",
    "PP-DocLayoutV3": "70bd316b0582769ec968829fd1feb1a6a58b7c941b938327e551b6b12b45c137",
}
BRIDGE_NAME = "paddle_vl_structure_bridge.py"
BRIDGE_REQUEST_SCHEMA = "tos_paddle_vl_structure_bridge_request_v1"
SELECTION_SCHEMA = Path(__file__).resolve().with_name("schemas") / "structure-vlm-selection.schema.json"
CONFIGURATION = {
    "pipeline_version": "v1.6",
    "device": "cpu",
    "use_doc_orientation_classify": False,
    "use_doc_unwarping": False,
    "use_layout_detection": True,
    "use_chart_recognition": False,
    "use_seal_recognition": False,
    "use_ocr_for_image_block": False,
    "format_block_content": True,
    "merge_layout_blocks": True,
    "markdown_ignore_labels": [],
    "use_queues": False,
    "max_pixels": 1003520,
    "max_new_tokens": 4096,
    "temperature": 0.0,
}
RETAIN_EVIDENCE_DECISION = "retain"


class PaddleVlStructureError(RuntimeError):
    """Raised when Structure C cannot preserve its frozen experiment law."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaddleVlStructureError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PaddleVlStructureError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: object) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PaddleVlStructureError(f"artifact escapes run root: {path}") from exc


def _schema_issues(payload: object, schema_path: Path) -> list[str]:
    schema = _load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{list(error.absolute_path)}: {error.message}"
        for error in validator.iter_errors(payload)
    ]


def _verify_prepared_run(
    run_root: Path, runtime_manifest_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = _load_json(run_root / "run.receipt.json")
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if (
        receipt.get("experiment_id") != "tos-structure-recovery-v1"
        or receipt.get("variant") != "C"
        or receipt.get("status") != "prepared"
        or preflight.get("decision") != "ready"
    ):
        raise PaddleVlStructureError("Structure C requires one prepared, ready C run")
    admission = preflight.get("runtime_admission")
    if (
        not isinstance(admission, dict)
        or admission.get("verified") is not True
        or Path(str(admission.get("manifest_ref"))).resolve()
        != runtime_manifest_path.resolve()
        or admission.get("manifest_sha256") != _sha256_file(runtime_manifest_path)
    ):
        raise PaddleVlStructureError("runtime differs from the preflighted admission")
    return receipt, experiment


def _verify_runtime(path: Path) -> tuple[dict[str, Any], Path, Path]:
    try:
        runtime = verify_runtime_manifest(
            path,
            experiment_id="tos-structure-recovery-v1",
            variant="C",
            required_commands=["paddleocr", "python"],
        )
    except RuntimeManifestError as exc:
        raise PaddleVlStructureError(str(exc)) from exc
    if runtime.get("runtime_id") != EXPECTED_RUNTIME_ID:
        raise PaddleVlStructureError(f"unexpected runtime: {runtime.get('runtime_id')}")
    software = {
        str(row.get("name")): row
        for row in runtime.get("software", [])
        if isinstance(row, dict)
    }
    for name, digest in EXPECTED_SOFTWARE_SHA256.items():
        if software.get(name, {}).get("source_sha256") != digest:
            raise PaddleVlStructureError(f"runtime software/model drift: {name}")
    root = path.resolve().parent
    vl_model = root / "models-structure/paddleocr-vl-1.6"
    layout_model = root / "models-structure/pp-doclayout-v3"
    return runtime, vl_model, layout_model


def _selected_rows(
    selection: dict[str, Any], selected_sample_ids: list[str] | None
) -> list[dict[str, Any]]:
    rows = [row for row in selection["samples"] if isinstance(row, dict)]
    if selected_sample_ids is None:
        return rows
    if not selected_sample_ids or len(selected_sample_ids) != len(set(selected_sample_ids)):
        raise PaddleVlStructureError("diagnostic selected sample IDs must be nonempty and unique")
    available = {str(row["sample_id"]) for row in rows}
    missing = sorted(set(selected_sample_ids) - available)
    if missing:
        raise PaddleVlStructureError("selection omits requested samples: " + ", ".join(missing))
    selected = set(selected_sample_ids)
    return [row for row in rows if row["sample_id"] in selected]


def _all_artifacts(run_root: Path) -> list[str]:
    return sorted(
        _relative(run_root, path)
        for relative in ("raw-output", "metrics", "receipts")
        for path in (run_root / relative).rglob("*")
        if path.is_file() and path.name != "preflight.json"
    )


def execute_paddle_vl_structure(
    run_root: Path,
    visual_plan_path: Path,
    render_manifest_path: Path,
    selection_path: Path,
    runtime_manifest_path: Path,
    *,
    invocation: list[str],
    selected_sample_ids: list[str] | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    paths = [
        visual_plan_path.resolve(),
        render_manifest_path.resolve(),
        selection_path.resolve(),
        runtime_manifest_path.resolve(),
    ]
    visual_plan_path, render_manifest_path, selection_path, runtime_manifest_path = paths
    receipt_path = run_root / "run.receipt.json"
    receipt, experiment = _verify_prepared_run(run_root, runtime_manifest_path)
    runtime, vl_model, layout_model = _verify_runtime(runtime_manifest_path)

    selection = _load_json(selection_path)
    selection_issues = _schema_issues(selection, SELECTION_SCHEMA)
    if selection_issues:
        raise PaddleVlStructureError("invalid frozen selection: " + "; ".join(selection_issues))
    visual_plan = _load_json(visual_plan_path)
    plan_issues = validate_visual_plan(visual_plan)
    if plan_issues:
        raise PaddleVlStructureError("invalid visual plan: " + "; ".join(plan_issues))
    if _sha256_file(visual_plan_path) != selection["source_plan_sha256"]:
        raise PaddleVlStructureError("selection source plan digest drift")
    try:
        render_manifest = verify_render_manifest(render_manifest_path)
    except OcrRenderError as exc:
        raise PaddleVlStructureError(str(exc)) from exc
    if (
        _sha256_file(render_manifest_path) != selection["render_manifest_sha256"]
        or render_manifest["render_set_sha256"] != selection["render_set_sha256"]
        or render_manifest["sample_plan_sha256"] != _sha256_file(visual_plan_path)
    ):
        raise PaddleVlStructureError("selection/render closure drift")

    visual_samples = {
        str(sample["sample_id"]): sample
        for group in visual_plan["source_groups"]
        for sample in group["samples"]
    }
    renders = {
        str(row["sample_id"]): row for row in render_manifest["renders"]
    }
    active = _selected_rows(selection, selected_sample_ids)
    render_root = Path(render_manifest["artifact_root"])
    request_samples: list[dict[str, Any]] = []
    enriched: dict[str, dict[str, Any]] = {}
    for selected in active:
        sample_id = str(selected["sample_id"])
        visual = visual_samples.get(sample_id)
        render = renders.get(sample_id)
        if (
            visual is None
            or render is None
            or visual.get("source_sample_id") != selected.get("source_sample_id")
            or visual.get("group_id") not in {None, selected.get("group_id")}
        ):
            raise PaddleVlStructureError(f"selection projection drift: {sample_id}")
        image = render_root / str(render["png_ref"])
        if _sha256_file(image) != render["png_sha256"]:
            raise PaddleVlStructureError(f"render byte drift: {sample_id}")
        request_samples.append(
            {
                "sample_id": sample_id,
                "image_path": image.as_posix(),
                "image_sha256": render["png_sha256"],
            }
        )
        enriched[sample_id] = {
            "selection": selected,
            "visual": visual,
            "render": render,
        }

    raw_root = run_root / "raw-output"
    request_path = run_root / "receipts/paddle-vl-structure-request.json"
    request = {
        "schema_version": BRIDGE_REQUEST_SCHEMA,
        "experiment_id": "tos-structure-recovery-v1",
        "variant": "C",
        "output_root": raw_root.as_posix(),
        "vl_model_dir": vl_model.as_posix(),
        "layout_model_dir": layout_model.as_posix(),
        "configuration": CONFIGURATION,
        "samples": request_samples,
    }
    _write_json(request_path, request)
    bridge = Path(__file__).resolve().with_name(BRIDGE_NAME)
    invocation_path = run_root / "receipts/paddle-vl-structure-invocation.json"
    invocation_receipt = {
        "captured_at_utc": _utc_now(),
        "argv": invocation,
        "runner_sha256": _sha256_file(Path(__file__)),
        "bridge_sha256": _sha256_file(bridge),
        "bridge_request_sha256": _sha256_file(request_path),
        "selection_ref": selection_path.as_posix(),
        "selection_sha256": _sha256_file(selection_path),
        "visual_plan_ref": visual_plan_path.as_posix(),
        "visual_plan_sha256": _sha256_file(visual_plan_path),
        "render_manifest_ref": render_manifest_path.as_posix(),
        "render_manifest_sha256": _sha256_file(render_manifest_path),
        "render_set_sha256": render_manifest["render_set_sha256"],
        "runtime_manifest_ref": runtime_manifest_path.as_posix(),
        "runtime_manifest_sha256": _sha256_file(runtime_manifest_path),
        "runtime_artifact_set_sha256": runtime["artifact_set_sha256"],
        "execution_scope": "frozen-twelve-page-set" if selected_sample_ids is None else "diagnostic-frozen-subset",
        "selected_sample_ids": [row["sample_id"] for row in active],
        "quality_metrics_allowed": False,
        "rights_posture": "restricted-source-derived-output-private-runtime-only",
    }
    _write_json(invocation_path, invocation_receipt)
    variant = next(row for row in experiment["variants"] if row["label"] == "C")
    receipt["status"] = "running"
    receipt["started_at_utc"] = invocation_receipt["captured_at_utc"]
    receipt["method_revision"] = {
        "implementation": variant["implementation"],
        "version": "PaddleOCR 3.7.0; PaddleX 3.7.2; PaddlePaddle 3.3.1; PaddleOCR-VL 1.6 native CPU",
        "runtime": runtime["runtime_id"],
        "model": variant["model"],
        "artifact_digest": runtime["artifact_set_sha256"],
    }
    receipt["invocation_ref"] = _relative(run_root, invocation_path)
    receipt["artifact_refs"] = [_relative(run_root, request_path)]
    _write_json(receipt_path, receipt)

    environment = os.environ.copy()
    environment.update({str(key): str(value) for key, value in runtime["environment"].items()})
    environment.update(
        {
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "4"),
            "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS", "4"),
            "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS", "4"),
            "NUMEXPR_NUM_THREADS": os.environ.get("NUMEXPR_NUM_THREADS", "4"),
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    started = time.perf_counter()
    child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        completed = subprocess.run(
            (
                runtime["commands"]["python"],
                bridge.as_posix(),
                "--request",
                request_path.as_posix(),
            ),
            check=False,
            capture_output=True,
            timeout=10800,
            env=environment,
        )
        stdout_path = run_root / "receipts/paddle-vl-structure.stdout.txt"
        stderr_path = run_root / "receipts/paddle-vl-structure.stderr.txt"
        stdout_path.write_bytes(completed.stdout)
        stderr_path.write_bytes(completed.stderr)
        stderr_text = completed.stderr.decode("utf-8", errors="replace")
        if completed.returncode:
            raise PaddleVlStructureError(
                f"bridge failed ({completed.returncode}); see {_relative(run_root, stderr_path)}"
            )
        summary = _load_json(raw_root / "paddle-vl-structure-bridge-summary.json")
        progress = [
            json.loads(line)
            for line in (raw_root / "paddle-vl-structure-progress.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        if summary.get("sample_ids") != [row["sample_id"] for row in active]:
            raise PaddleVlStructureError("bridge completed a different selection")
        progress_by_id = {
            str(row["sample_id"]): row
            for row in progress
            if row.get("event") == "sample_completed"
            and isinstance(row.get("sample_id"), str)
        }
        samples: list[dict[str, Any]] = []
        warnings: list[dict[str, str]] = []
        if "`temperature` is currently not supported" in stderr_text:
            warnings.append(
                {
                    "sample_id": "*",
                    "warning": "temperature-control-unsupported-by-local-model-and-ignored",
                }
            )
        for selected in active:
            sample_id = str(selected["sample_id"])
            source = enriched[sample_id]
            sample_root = raw_root / sample_id
            blocks = _load_json(sample_root / "ordered-blocks.json")
            engine = _load_json(sample_root / "engine.json")
            row = {
                "sample_id": sample_id,
                "source_sample_id": selected["source_sample_id"],
                "selection_lane": selected["lane"],
                "group_id": selected["group_id"],
                "source_anchor_ref": source["render"]["anchor_ref"],
                "item_ref": source["render"]["item_ref"],
                "file_ref": source["render"]["file_ref"],
                "page": source["render"]["page"],
                "language": source["render"]["language"],
                "render_ref": source["render"]["png_ref"],
                "render_sha256": source["render"]["png_sha256"],
                "outputs": {
                    name: {
                        "ref": _relative(run_root, sample_root / filename),
                        "sha256": _sha256_file(sample_root / filename),
                        "bytes": (sample_root / filename).stat().st_size,
                    }
                    for name, filename in (
                        ("raw", "paddle-vl-result.json"),
                        ("blocks", "ordered-blocks.json"),
                        ("markdown", "document.md"),
                        ("engine", "engine.json"),
                    )
                },
                "block_count": blocks["block_count"],
                "nonempty_block_count": engine["nonempty_block_count"],
                "prediction_seconds": engine["prediction_seconds"],
                "content_status": "unreviewed-structure-draft",
                "authority_boundary": "engine output only; not accepted source structure",
            }
            if not row["nonempty_block_count"]:
                warnings.append({"sample_id": sample_id, "warning": "empty-structure-output"})
            if progress_by_id.get(sample_id, {}).get("blocks_sha256") != row["outputs"]["blocks"]["sha256"]:
                raise PaddleVlStructureError(f"bridge progress digest drift: {sample_id}")
            samples.append(row)
        output_manifest = {
            "schema_version": "tos_paddle_vl_structure_output_manifest_v1",
            "experiment_id": "tos-structure-recovery-v1",
            "variant": "C",
            "run_id": receipt["run_id"],
            "execution_scope": invocation_receipt["execution_scope"],
            "selection_sha256": invocation_receipt["selection_sha256"],
            "render_set_sha256": render_manifest["render_set_sha256"],
            "runtime_artifact_set_sha256": runtime["artifact_set_sha256"],
            "configuration": CONFIGURATION,
            "samples": samples,
            "output_set_sha256": _canonical_sha256(
                [
                    {
                        "sample_id": row["sample_id"],
                        "render_sha256": row["render_sha256"],
                        "blocks_sha256": row["outputs"]["blocks"]["sha256"],
                        "markdown_sha256": row["outputs"]["markdown"]["sha256"],
                    }
                    for row in samples
                ]
            ),
            "quality_status": "not-computed-awaiting-double-source-visible-human-structure-gold",
            "authority_boundary": "reproducible challenger evidence only; no structure winner verdict",
        }
        manifest_path = raw_root / "paddle-vl-structure-output-manifest.json"
        warnings_path = raw_root / "warnings.json"
        _write_json(manifest_path, output_manifest)
        _write_json(warnings_path, {"warnings": warnings})
        elapsed = time.perf_counter() - started
        child = resource.getrusage(resource.RUSAGE_CHILDREN)
        metrics = {
            "schema_version": "tos_paddle_vl_structure_metrics_v1",
            "experiment_id": "tos-structure-recovery-v1",
            "variant": "C",
            "execution_scope": invocation_receipt["execution_scope"],
            "sample_count": len(samples),
            "wall_seconds": elapsed,
            "units_per_minute": len(samples) * 60 / elapsed if elapsed else None,
            "initialization_seconds": summary["initialization_seconds"],
            "prediction_seconds": summary["prediction_seconds"],
            "child_peak_rss_bytes": child.ru_maxrss * 1024,
            "child_user_cpu_seconds": child.ru_utime - child_before.ru_utime,
            "child_system_cpu_seconds": child.ru_stime - child_before.ru_stime,
            "artifact_bytes": sum(
                path.stat().st_size for path in run_root.rglob("*") if path.is_file()
            ),
            "block_count": sum(int(row["block_count"]) for row in samples),
            "empty_output_count": sum(not int(row["nonempty_block_count"]) for row in samples),
            "warning_count": len(warnings),
            "quality": {
                "structural_f1": None,
                "reading_order_error": None,
                "anchor_resolution": None,
                "reason": "human structural gold and correction pass are not complete",
            },
            "human_cost": {
                "repair_minutes_per_unit": None,
                "reason": "no real human repair timing has been recorded",
            },
            "authority_boundary": "mechanical speed/cost only; quality and acceptance remain human-owned",
        }
        metrics_path = run_root / "metrics/metrics.json"
        _write_json(metrics_path, metrics)
        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = [row["sample_id"] for row in samples]
        receipt["artifact_refs"] = _all_artifacts(run_root)
        receipt["metric_refs"] = [_relative(run_root, metrics_path)]
        receipt["errors"] = [row["warning"] for row in warnings]
        receipt["retention_decision"] = RETAIN_EVIDENCE_DECISION
        _write_json(receipt_path, receipt)
        return metrics
    except BaseException as exc:
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["artifact_refs"] = _all_artifacts(run_root)
        receipt["errors"] = [f"{type(exc).__name__}: {exc}"]
        receipt["retention_decision"] = RETAIN_EVIDENCE_DECISION
        _write_json(receipt_path, receipt)
        raise
