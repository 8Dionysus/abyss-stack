#!/usr/bin/env python3
"""Execute frozen OCR C with pinned offline PaddleOCR models."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import signal
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ocr_render import OcrRenderError, validate_visual_plan, verify_render_manifest
from runtime_manifest import RuntimeManifestError, verify_runtime_manifest


EXPECTED_RUNTIME_ID = "paddleocr-3.7.0-paddlex-3.7.2-paddle-3.3.1-cpu"
EXPECTED_PADDLEOCR_VERSION = "3.7.0"
EXPECTED_PADDLEX_VERSION = "3.7.2"
EXPECTED_PADDLEPADDLE_VERSION = "3.3.1"
EXPECTED_SOFTWARE_SHA256 = {
    "paddleocr": "c0f0a81ad4112727f30c6fcf986ac0ef6a120d31ee0991a01fae0357ee32d338",
    "paddlex": "f1678bf650bbaccfd8f0d4e49d0ae631b4685c829fdae6e802ccd90d4fcb9a7f",
    "paddlepaddle-cpu": "9016fc497213e1101261684321fbb31ef5960019ef39cb07ded27bc70e2a9858",
    "PP-OCRv5_server_det": "22a33e0ba6a21425ea4192da03bf4395c9a0c67902bd924b7328fc859073045d",
    "latin_PP-OCRv5_mobile_rec": "b23105a6a1ea38e32a97c5a0ddc7e8a9bbf541d8e47421e2c99e9ccabe29509c",
    "eslav_PP-OCRv5_mobile_rec": "b9f70da0ca2bbc4d4cb7ba406a2d023061178437d6a930f07c8ca18c6c591839",
}
MODEL_BY_LANGUAGE = {
    "de": "latin_PP-OCRv5_mobile_rec",
    "ru": "eslav_PP-OCRv5_mobile_rec",
}
BRIDGE_NAME = "paddle_ocr_bridge.py"
BRIDGE_REQUEST_SCHEMA = "tos_paddle_ocr_bridge_request_v2"
DETECTOR_RESIZE = {"limit_side_len": 960, "limit_type": "max"}


class PaddleOcrError(RuntimeError):
    """Raised when OCR C cannot preserve the frozen experiment law."""


class PaddleOcrStop(PaddleOcrError):
    """Raised when OCR C is externally stopped with partial evidence retained."""


def _stop_on_sigterm(signum: int, _frame: object) -> None:
    try:
        name = signal.Signals(signum).name
    except ValueError:
        name = str(signum)
    raise PaddleOcrStop(f"external stop signal received: {name}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaddleOcrError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PaddleOcrError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: object) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _relative(run_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(run_root.resolve()).as_posix()
    except ValueError as exc:
        raise PaddleOcrError(f"artifact escapes run root: {path}") from exc


def _file_record(
    run_root: Path,
    path: Path,
    *,
    canonical_sha256: str | None = None,
) -> dict[str, Any]:
    if not path.is_file():
        raise PaddleOcrError(f"expected OCR C artifact is missing: {path}")
    record: dict[str, Any] = {
        "ref": _relative(run_root, path),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }
    if canonical_sha256 is not None:
        record["canonical_sha256"] = canonical_sha256
    return record


def _existing_artifact_refs(run_root: Path) -> list[str]:
    refs: list[str] = []
    for relative_root in ("raw-output", "metrics"):
        root = run_root / relative_root
        if root.is_dir():
            refs.extend(_relative(run_root, path) for path in root.rglob("*") if path.is_file())
    receipts_root = run_root / "receipts"
    if receipts_root.is_dir():
        refs.extend(
            _relative(run_root, path)
            for path in receipts_root.glob("paddle-ocr-*")
            if path.is_file()
        )
        refs.extend(
            _relative(run_root, path)
            for path in receipts_root.glob("resource-owner-*.json")
            if path.is_file()
        )
    return sorted(set(refs))


def _partial_sample_ids(run_root: Path, completed_sample_ids: list[str]) -> list[str]:
    raw_root = run_root / "raw-output"
    if not raw_root.is_dir():
        return []
    completed = set(completed_sample_ids)
    return sorted(
        path.name
        for path in raw_root.iterdir()
        if path.is_dir()
        and path.name not in completed
        and any(child.is_file() for child in path.rglob("*"))
    )


def _finalize_aborted_receipt(
    run_root: Path,
    receipt_path: Path,
    receipt: dict[str, Any],
    samples: list[dict[str, Any]],
    artifact_refs: list[str],
    *,
    status: str,
    error: str,
) -> None:
    if status not in {"failed", "stopped"}:
        raise ValueError(f"unsupported aborted status: {status}")
    completed = [str(sample["sample_id"]) for sample in samples]
    partial = _partial_sample_ids(run_root, completed)
    errors = [error]
    if partial:
        errors.append("partial-output-sample-ids: " + ", ".join(partial))
    receipt["status"] = status
    receipt["finished_at_utc"] = _utc_now()
    receipt["sample_ids"] = completed
    receipt["artifact_refs"] = sorted(
        set(artifact_refs + _existing_artifact_refs(run_root))
    )
    receipt["errors"] = errors
    _write_json(receipt_path, receipt)


def _verify_prepared_run(
    run_root: Path,
    runtime_manifest_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = _load_json(run_root / "run.receipt.json")
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if receipt.get("experiment_id") != "tos-ocr-foundation-v1" or receipt.get("variant") != "C":
        raise PaddleOcrError("PaddleOCR runner requires prepared OCR C")
    if receipt.get("status") != "prepared" or preflight.get("decision") != "ready":
        raise PaddleOcrError("run must be prepared from a ready preflight")
    if experiment.get("family") != "ocr":
        raise PaddleOcrError("experiment specification is not OCR")
    admission = preflight.get("runtime_admission")
    if not isinstance(admission, dict) or admission.get("verified") is not True:
        raise PaddleOcrError("preflight does not contain a verified isolated runtime")
    if Path(str(admission.get("manifest_ref"))).resolve() != runtime_manifest_path.resolve():
        raise PaddleOcrError("runtime manifest differs from the preflighted manifest")
    if _sha256_file(runtime_manifest_path) != admission.get("manifest_sha256"):
        raise PaddleOcrError("runtime manifest digest drift after preflight")
    return receipt, experiment


def _verify_runtime_identity(runtime_manifest_path: Path) -> tuple[dict[str, Any], Path, dict[str, Path]]:
    try:
        runtime = verify_runtime_manifest(
            runtime_manifest_path,
            experiment_id="tos-ocr-foundation-v1",
            variant="C",
            required_commands=["paddleocr", "python"],
        )
    except RuntimeManifestError as exc:
        raise PaddleOcrError(str(exc)) from exc
    if runtime.get("runtime_id") != EXPECTED_RUNTIME_ID:
        raise PaddleOcrError(f"unexpected OCR C runtime_id: {runtime.get('runtime_id')}")
    software = {
        str(row.get("name")): row
        for row in runtime.get("software", [])
        if isinstance(row, dict)
    }
    for name, digest in EXPECTED_SOFTWARE_SHA256.items():
        row = software.get(name)
        if row is None or row.get("source_sha256") != digest:
            raise PaddleOcrError(f"runtime software/model identity drift: {name}")
    expected_versions = {
        "paddleocr": EXPECTED_PADDLEOCR_VERSION,
        "paddlex": EXPECTED_PADDLEX_VERSION,
        "paddlepaddle-cpu": EXPECTED_PADDLEPADDLE_VERSION,
    }
    for name, version in expected_versions.items():
        if software[name].get("version") != version:
            raise PaddleOcrError(f"runtime software version drift: {name}")
    runtime_root = runtime_manifest_path.resolve().parent
    detector = runtime_root / "models/PP-OCRv5_server_det"
    recognizers = {
        language: runtime_root / "models" / model_name
        for language, model_name in MODEL_BY_LANGUAGE.items()
    }
    for label, model_dir in {"detector": detector, **recognizers}.items():
        for filename in ("inference.json", "inference.pdiparams", "inference.yml"):
            path = model_dir / filename
            if not path.is_file():
                raise PaddleOcrError(f"runtime {label} model omits {filename}")
    return runtime, detector, recognizers


def _write_bridge_logs(run_root: Path, stdout: bytes, stderr: bytes) -> dict[str, dict[str, Any]]:
    stdout_path = run_root / "receipts/paddle-ocr-bridge.stdout.txt"
    stderr_path = run_root / "receipts/paddle-ocr-bridge.stderr.txt"
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    return {
        "stdout": _file_record(run_root, stdout_path),
        "stderr": _file_record(run_root, stderr_path),
    }


def _run_bridge(
    run_root: Path,
    arguments: list[str],
    environment: dict[str, str],
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    process = subprocess.Popen(
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        process.terminate()
        try:
            tail_stdout, tail_stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            tail_stdout, tail_stderr = process.communicate()
        stdout = (exc.stdout or b"") + (tail_stdout or b"")
        stderr = (exc.stderr or b"") + (tail_stderr or b"")
    except BaseException:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        _write_bridge_logs(run_root, stdout or b"", stderr or b"")
        raise
    logs = _write_bridge_logs(run_root, stdout, stderr)
    return {
        "argv": arguments,
        "returncode": process.returncode,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": time.perf_counter() - started,
        "stdout": logs["stdout"],
        "stderr": logs["stderr"],
        "stdout_line_count": len(stdout.decode("utf-8", errors="replace").splitlines()),
        "stderr_line_count": len(stderr.decode("utf-8", errors="replace").splitlines()),
    }


def _load_progress(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise PaddleOcrError(f"progress row {line_number} is not an object")
                rows.append(row)
    except (OSError, json.JSONDecodeError) as exc:
        raise PaddleOcrError(f"cannot read PaddleOCR progress {path}: {exc}") from exc
    ids = [row.get("sample_id") for row in rows]
    if len(ids) != len(set(ids)):
        raise PaddleOcrError("PaddleOCR progress contains duplicate sample IDs")
    return rows


def _semantic_output_set_digest(samples: list[dict[str, Any]]) -> str:
    return _canonical_sha256(
        [
            {
                "sample_id": sample["sample_id"],
                "render_sha256": sample["render_sha256"],
                "text_sha256": sample["outputs"]["diplomatic_text"]["sha256"],
                "regions_semantic_sha256": sample["outputs"]["regions"]["canonical_sha256"],
            }
            for sample in samples
        ]
    )


def _raw_output_set_digest(samples: list[dict[str, Any]]) -> str:
    return _canonical_sha256(
        [
            {
                "sample_id": sample["sample_id"],
                "paddle_result_sha256": sample["outputs"]["paddle_result"]["sha256"],
                "paddle_result_bytes": sample["outputs"]["paddle_result"]["bytes"],
            }
            for sample in samples
        ]
    )


def _select_renders(
    renders: list[dict[str, Any]], selected_sample_ids: list[str] | None
) -> list[dict[str, Any]]:
    if selected_sample_ids is None:
        return list(renders)
    if not selected_sample_ids:
        raise PaddleOcrError("selected sample IDs must be nonempty when supplied")
    if len(selected_sample_ids) != len(set(selected_sample_ids)):
        raise PaddleOcrError("selected sample IDs contain duplicates")
    available = {str(render["sample_id"]) for render in renders}
    missing = sorted(set(selected_sample_ids) - available)
    if missing:
        raise PaddleOcrError("selected sample IDs are absent from frozen renders: " + ", ".join(missing))
    selected = set(selected_sample_ids)
    return [render for render in renders if str(render["sample_id"]) in selected]


def _verify_detector_resize_configuration(configuration: object, label: str) -> None:
    if not isinstance(configuration, dict):
        raise PaddleOcrError(f"{label} configuration is not an object")
    observed = {
        "limit_side_len": configuration.get("text_det_limit_side_len"),
        "limit_type": configuration.get("text_det_limit_type"),
    }
    if observed != DETECTOR_RESIZE:
        raise PaddleOcrError(
            f"{label} detector resize drift: expected {DETECTOR_RESIZE}, observed {observed}"
        )


def execute_paddle_ocr(
    run_root: Path,
    sample_plan_path: Path,
    render_manifest_path: Path,
    runtime_manifest_path: Path,
    *,
    invocation: list[str],
    selected_sample_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run OCR C while keeping all content claims behind manual source review."""

    run_root = run_root.resolve()
    sample_plan_path = sample_plan_path.resolve()
    render_manifest_path = render_manifest_path.resolve()
    runtime_manifest_path = runtime_manifest_path.resolve()
    receipt_path = run_root / "run.receipt.json"
    receipt, experiment = _verify_prepared_run(run_root, runtime_manifest_path)
    plan = _load_json(sample_plan_path)
    issues = validate_visual_plan(plan)
    if issues:
        raise PaddleOcrError("invalid frozen visual plan: " + "; ".join(issues))
    try:
        render_manifest = verify_render_manifest(render_manifest_path)
    except OcrRenderError as exc:
        raise PaddleOcrError(str(exc)) from exc
    if render_manifest.get("sample_plan_sha256") != _sha256_file(sample_plan_path):
        raise PaddleOcrError("render packet was built from a different visual plan")
    if render_manifest.get("reference_witness_state") != "sealed-not-consulted":
        raise PaddleOcrError("reference witness seal is not intact")
    runtime, detector, recognizers = _verify_runtime_identity(runtime_manifest_path)

    cpu_threads_text = os.environ.get("OMP_NUM_THREADS", "1")
    try:
        cpu_threads = int(cpu_threads_text)
    except ValueError as exc:
        raise PaddleOcrError(f"invalid OMP_NUM_THREADS: {cpu_threads_text}") from exc
    if not 1 <= cpu_threads <= 64:
        raise PaddleOcrError(f"OMP_NUM_THREADS outside supported range: {cpu_threads}")
    runtime_python = Path(runtime["commands"]["python"])
    bridge_path = Path(__file__).resolve().with_name(BRIDGE_NAME)
    if not bridge_path.is_file():
        raise PaddleOcrError(f"PaddleOCR bridge is missing: {bridge_path}")
    environment = os.environ.copy()
    environment.update({str(key): str(value) for key, value in runtime["environment"].items()})
    environment.update(
        {
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "OMP_NUM_THREADS": str(cpu_threads),
            "MKL_NUM_THREADS": str(cpu_threads),
            "OPENBLAS_NUM_THREADS": str(cpu_threads),
            "NUMEXPR_NUM_THREADS": str(cpu_threads),
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    renders = render_manifest["renders"]
    active_renders = _select_renders(renders, selected_sample_ids)
    render_root = Path(render_manifest["artifact_root"])
    raw_root = run_root / "raw-output"
    raw_root.mkdir(parents=True, exist_ok=True)
    request_path = run_root / "receipts/paddle-ocr-bridge-request.json"
    request_samples = []
    render_by_id: dict[str, dict[str, Any]] = {}
    for render in active_renders:
        sample_id = str(render["sample_id"])
        language = str(render["language"])
        if language not in MODEL_BY_LANGUAGE:
            raise PaddleOcrError(f"unsupported OCR C language: {language}")
        image_path = render_root / str(render["png_ref"])
        if _sha256_file(image_path) != render["png_sha256"]:
            raise PaddleOcrError(f"render drift immediately before OCR: {sample_id}")
        request_samples.append(
            {
                "sample_id": sample_id,
                "language": language,
                "image_path": image_path.as_posix(),
                "image_sha256": render["png_sha256"],
            }
        )
        render_by_id[sample_id] = render
    request = {
        "schema_version": BRIDGE_REQUEST_SCHEMA,
        "experiment_id": "tos-ocr-foundation-v1",
        "variant": "C",
        "output_root": raw_root.as_posix(),
        "detector_dir": detector.as_posix(),
        "recognizer_dirs": {
            language: path.as_posix() for language, path in recognizers.items()
        },
        "cpu_threads": cpu_threads,
        "detector_resize": DETECTOR_RESIZE,
        "samples": request_samples,
        "reference_witness_state": "sealed-not-consulted",
        "execution_scope": (
            "full-frozen-visual-packet"
            if selected_sample_ids is None
            else "bounded-selected-frozen-pages"
        ),
        "selected_sample_ids": [str(render["sample_id"]) for render in active_renders],
    }
    _write_json(request_path, request)

    started_at = _utc_now()
    wall_started = time.perf_counter()
    variant = next(row for row in experiment["variants"] if row["label"] == "C")
    invocation_path = run_root / "receipts/paddle-ocr-invocation.json"
    invocation_receipt = {
        "captured_at_utc": started_at,
        "argv": invocation,
        "python": platform.python_version(),
        "paddleocr": EXPECTED_PADDLEOCR_VERSION,
        "paddlex": EXPECTED_PADDLEX_VERSION,
        "paddlepaddle": EXPECTED_PADDLEPADDLE_VERSION,
        "runner_sha256": _sha256_file(Path(__file__)),
        "bridge_sha256": _sha256_file(bridge_path),
        "bridge_request_sha256": _sha256_file(request_path),
        "sample_plan_sha256": _sha256_file(sample_plan_path),
        "render_manifest_sha256": _sha256_file(render_manifest_path),
        "render_set_sha256": render_manifest["render_set_sha256"],
        "runtime_manifest_sha256": _sha256_file(runtime_manifest_path),
        "runtime_artifact_set_sha256": runtime["artifact_set_sha256"],
        "software_source_sha256": EXPECTED_SOFTWARE_SHA256,
        "rights_posture": "restricted-source-derived-text-private-runtime-only",
        "reference_witness_state": "sealed-not-consulted",
        "execution_scope": (
            "full-frozen-visual-packet"
            if selected_sample_ids is None
            else "bounded-selected-frozen-pages"
        ),
        "selected_sample_ids": [str(render["sample_id"]) for render in active_renders],
    }
    _write_json(invocation_path, invocation_receipt)
    artifact_refs = _existing_artifact_refs(run_root)
    receipt["status"] = "running"
    receipt["started_at_utc"] = started_at
    receipt["method_revision"] = {
        "implementation": variant["implementation"],
        "version": (
            f"PaddleOCR {EXPECTED_PADDLEOCR_VERSION}; PaddleX {EXPECTED_PADDLEX_VERSION}; "
            f"PaddlePaddle {EXPECTED_PADDLEPADDLE_VERSION}; paddle_static; MKLDNN disabled; "
            "detector resize 960/max"
        ),
        "runtime": runtime["runtime_id"],
        "model": "PP-OCRv5 server detector + Latin/East-Slavic mobile recognizers",
        "artifact_digest": runtime["artifact_set_sha256"],
    }
    receipt["invocation_ref"] = _relative(run_root, invocation_path)
    receipt["artifact_refs"] = sorted(artifact_refs)
    _write_json(receipt_path, receipt)

    samples: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    previous_sigterm_handler = signal.signal(signal.SIGTERM, _stop_on_sigterm)
    child_usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        bridge_step = _run_bridge(
            run_root,
            [runtime_python.as_posix(), bridge_path.as_posix(), "--request", request_path.as_posix()],
            environment,
            timeout_seconds=7200,
        )
        artifact_refs.extend(
            [bridge_step["stdout"]["ref"], bridge_step["stderr"]["ref"]]
        )
        if bridge_step["returncode"] != 0 or bridge_step["timed_out"]:
            raise PaddleOcrError(
                "PaddleOCR bridge failed: "
                f"returncode={bridge_step['returncode']} timed_out={bridge_step['timed_out']} "
                f"stderr={bridge_step['stderr']['ref']}"
            )
        progress_path = raw_root / "paddle-ocr-progress.jsonl"
        summary_path = raw_root / "paddle-ocr-bridge-summary.json"
        progress = _load_progress(progress_path)
        bridge_summary = _load_json(summary_path)
        _verify_detector_resize_configuration(
            bridge_summary.get("configuration"), "bridge summary"
        )
        progress_by_id = {str(row["sample_id"]): row for row in progress}
        if set(progress_by_id) != set(render_by_id):
            raise PaddleOcrError("PaddleOCR bridge did not complete the frozen sample set")
        if bridge_summary.get("sample_count") != len(active_renders):
            raise PaddleOcrError("PaddleOCR bridge summary sample count drift")
        artifact_refs.extend(
            [_relative(run_root, progress_path), _relative(run_root, summary_path)]
        )
        if bridge_step["stderr"]["bytes"]:
            warnings.append({"sample_id": "run", "warning": "paddle-bridge-stderr-nonempty"})

        for render in active_renders:
            sample_id = str(render["sample_id"])
            sample_root = raw_root / sample_id
            result_path = sample_root / "paddle-result.json"
            regions_path = sample_root / "regions.json"
            text_path = sample_root / "recognition.txt"
            engine_path = sample_root / "engine.json"
            regions = _load_json(regions_path)
            engine = _load_json(engine_path)
            _verify_detector_resize_configuration(
                engine.get("configuration"), f"engine sample {sample_id}"
            )
            progress_row = progress_by_id[sample_id]
            if engine.get("image_sha256") != render["png_sha256"]:
                raise PaddleOcrError(f"engine/render fixity drift: {sample_id}")
            if regions.get("semantic_sha256") != progress_row.get("regions_semantic_sha256"):
                raise PaddleOcrError(f"region semantic digest drift: {sample_id}")
            if _sha256_file(result_path) != progress_row.get("result_sha256"):
                raise PaddleOcrError(f"raw Paddle result digest drift: {sample_id}")
            if _sha256_file(text_path) != progress_row.get("text_sha256"):
                raise PaddleOcrError(f"Paddle text digest drift: {sample_id}")
            outputs = {
                "paddle_result": _file_record(run_root, result_path),
                "regions": _file_record(
                    run_root,
                    regions_path,
                    canonical_sha256=str(regions["semantic_sha256"]),
                ),
                "diplomatic_text": _file_record(run_root, text_path),
                "engine": _file_record(run_root, engine_path),
            }
            artifact_refs.extend(output["ref"] for output in outputs.values())
            if engine.get("recognized_non_whitespace_characters") == 0:
                warnings.append({"sample_id": sample_id, "warning": "empty-recognized-text"})
            metadata = {
                "sample_id": sample_id,
                "source_anchor_ref": render["anchor_ref"],
                "item_ref": render["item_ref"],
                "file_ref": render["file_ref"],
                "page": render["page"],
                "language": render["language"],
                "recognizer": MODEL_BY_LANGUAGE[str(render["language"])],
                "difficulty": render["difficulty"],
                "gold_candidate": render["gold_candidate"],
                "render_ref": render["png_ref"],
                "render_sha256": render["png_sha256"],
                "outputs": outputs,
                "diagnostics": engine,
                "content_status": "unreviewed-ocr-draft",
                "authority_boundary": "engine output only; not source text or accepted transcription",
            }
            metadata_path = sample_root / "sample.json"
            _write_json(metadata_path, metadata)
            artifact_refs.append(_relative(run_root, metadata_path))
            samples.append(metadata)
            receipt["sample_ids"] = [sample["sample_id"] for sample in samples]
            receipt["artifact_refs"] = sorted(set(artifact_refs))
            _write_json(receipt_path, receipt)

        output_manifest = {
            "schema_version": "tos_paddle_ocr_output_manifest_v1",
            "experiment_id": "tos-ocr-foundation-v1",
            "variant": "C",
            "run_id": receipt["run_id"],
            "sample_plan_sha256": _sha256_file(sample_plan_path),
            "render_manifest_ref": render_manifest_path.as_posix(),
            "render_manifest_sha256": _sha256_file(render_manifest_path),
            "render_id": render_manifest["render_id"],
            "render_set_sha256": render_manifest["render_set_sha256"],
            "runtime_manifest_ref": runtime_manifest_path.as_posix(),
            "runtime_manifest_sha256": _sha256_file(runtime_manifest_path),
            "runtime_artifact_set_sha256": runtime["artifact_set_sha256"],
            "versions": {
                "paddleocr": EXPECTED_PADDLEOCR_VERSION,
                "paddlex": EXPECTED_PADDLEX_VERSION,
                "paddlepaddle": EXPECTED_PADDLEPADDLE_VERSION,
            },
            "models": {
                name: {"source_sha256": digest}
                for name, digest in EXPECTED_SOFTWARE_SHA256.items()
                if name.startswith("PP-") or name.startswith("latin_") or name.startswith("eslav_")
            },
            "configuration": bridge_summary["configuration"],
            "language_order": bridge_summary["language_order"],
            "pipeline_initialization": bridge_summary["pipeline_initialization"],
            "bridge_sha256": _sha256_file(bridge_path),
            "reference_witness_state": "sealed-not-consulted",
            "execution_scope": invocation_receipt["execution_scope"],
            "selected_sample_ids": invocation_receipt["selected_sample_ids"],
            "samples": samples,
            "semantic_output_set_sha256": _semantic_output_set_digest(samples),
            "raw_output_set_sha256": _raw_output_set_digest(samples),
            "quality_status": "blocked-until-double-checked-human-gold",
            "authority_boundary": "reproducible OCR candidate evidence only; no source-text or winner verdict",
        }
        output_manifest_path = raw_root / "paddle-ocr-output-manifest.json"
        _write_json(output_manifest_path, output_manifest)
        artifact_refs.append(_relative(run_root, output_manifest_path))
        warnings_path = raw_root / "warnings.json"
        _write_json(warnings_path, {"warnings": warnings})
        artifact_refs.append(_relative(run_root, warnings_path))

        elapsed = time.perf_counter() - wall_started
        child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        confidences = [
            float(sample["diagnostics"]["mean_engine_confidence"])
            for sample in samples
            if sample["diagnostics"].get("mean_engine_confidence") is not None
        ]
        artifact_bytes = sum(
            path.stat().st_size
            for path in run_root.rglob("*")
            if path.is_file() and path != receipt_path
        )
        metrics = {
            "schema_version": "tos_paddle_ocr_metrics_v1",
            "experiment_id": "tos-ocr-foundation-v1",
            "variant": "C",
            "sample_count": len(samples),
            "source_count": len({sample["item_ref"] for sample in samples}),
            "wall_seconds": elapsed,
            "pages_per_minute": len(samples) * 60 / elapsed if elapsed else None,
            "bridge_seconds": bridge_step["elapsed_seconds"],
            "pipeline_initialization_seconds": sum(
                float(row["elapsed_seconds"])
                for row in bridge_summary["pipeline_initialization"]
            ),
            "prediction_seconds": sum(
                float(sample["diagnostics"]["prediction_seconds"]) for sample in samples
            ),
            "child_peak_rss_bytes": max(child_usage_before.ru_maxrss, child_usage.ru_maxrss) * 1024,
            "child_peak_rss_boundary": "maximum observed child RSS on Linux, not aggregate memory",
            "child_user_cpu_seconds": child_usage.ru_utime - child_usage_before.ru_utime,
            "child_system_cpu_seconds": child_usage.ru_stime - child_usage_before.ru_stime,
            "artifact_bytes": artifact_bytes,
            "region_count": sum(int(sample["diagnostics"]["region_count"]) for sample in samples),
            "empty_text_count": sum(
                int(sample["diagnostics"]["recognized_non_whitespace_characters"]) == 0
                for sample in samples
            ),
            "warning_count": len(warnings),
            "mean_engine_confidence_across_pages": statistics.fmean(confidences)
            if confidences
            else None,
            "quality": {
                "cer": None,
                "wer": None,
                "reading_order_error": None,
                "status": "blocked-until-double-checked-human-gold",
            },
            "human_cost": {
                "correction_time_seconds": None,
                "status": "not-measured-no-human-pass",
            },
            "traceability": {
                "mechanical_anchor_resolution": (
                    len(samples) / len(active_renders) if active_renders else None
                ),
                "content_acceptance": "not-reviewed",
            },
            "authority_boundary": "mechanics, speed, resource, and engine diagnostics only; no OCR quality verdict",
        }
        metrics_path = run_root / "metrics/paddle-ocr-summary.json"
        _write_json(metrics_path, metrics)
        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = [sample["sample_id"] for sample in samples]
        receipt["artifact_refs"] = sorted(set(artifact_refs))
        receipt["metric_refs"] = [_relative(run_root, metrics_path)]
        receipt["manual_review_refs"] = []
        receipt["errors"] = []
        _write_json(receipt_path, receipt)
        return metrics
    except (PaddleOcrStop, KeyboardInterrupt) as exc:
        reason = str(exc) or "operator keyboard interrupt"
        _finalize_aborted_receipt(
            run_root,
            receipt_path,
            receipt,
            samples,
            artifact_refs,
            status="stopped",
            error=f"stopped: {reason}",
        )
        raise PaddleOcrError(f"OCR C stopped: {reason}") from exc
    except Exception as exc:
        _finalize_aborted_receipt(
            run_root,
            receipt_path,
            receipt,
            samples,
            artifact_refs,
            status="failed",
            error=str(exc),
        )
        if isinstance(exc, PaddleOcrError):
            raise
        raise PaddleOcrError(str(exc)) from exc
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)


def compare_paddle_ocr_runs(first_run_root: Path, second_run_root: Path) -> dict[str, Any]:
    """Compare semantic OCR C output while exposing raw Paddle JSON drift."""

    manifest_name = "raw-output/paddle-ocr-output-manifest.json"
    first = _load_json(first_run_root.resolve() / manifest_name)
    second = _load_json(second_run_root.resolve() / manifest_name)
    common_fields = (
        "sample_plan_sha256",
        "render_set_sha256",
        "runtime_artifact_set_sha256",
        "versions",
        "models",
        "configuration",
        "language_order",
        "bridge_sha256",
    )
    method_differences = [field for field in common_fields if first.get(field) != second.get(field)]
    first_samples = {row["sample_id"]: row for row in first.get("samples", [])}
    second_samples = {row["sample_id"]: row for row in second.get("samples", [])}
    semantic_differences: list[dict[str, Any]] = []
    raw_byte_differences: list[dict[str, Any]] = []
    for sample_id in sorted(set(first_samples) | set(second_samples)):
        left = first_samples.get(sample_id)
        right = second_samples.get(sample_id)
        if left is None or right is None:
            semantic_differences.append({"sample_id": sample_id, "difference": "missing-sample"})
            raw_byte_differences.append({"sample_id": sample_id, "difference": "missing-sample"})
            continue
        for output_name in ("diplomatic_text", "regions"):
            left_output = left["outputs"].get(output_name)
            right_output = right["outputs"].get(output_name)
            key = "canonical_sha256" if output_name == "regions" else "sha256"
            if left_output is None or right_output is None or left_output.get(key) != right_output.get(key):
                semantic_differences.append(
                    {"sample_id": sample_id, "difference": "semantic-output-digest", "output": output_name}
                )
        left_raw = left["outputs"].get("paddle_result")
        right_raw = right["outputs"].get("paddle_result")
        if left_raw is None or right_raw is None or (
            left_raw.get("sha256"), left_raw.get("bytes")
        ) != (right_raw.get("sha256"), right_raw.get("bytes")):
            raw_byte_differences.append(
                {"sample_id": sample_id, "difference": "raw-paddle-result-byte-digest"}
            )
    semantic_set_equal = first.get("semantic_output_set_sha256") == second.get(
        "semantic_output_set_sha256"
    )
    raw_set_equal = first.get("raw_output_set_sha256") == second.get("raw_output_set_sha256")
    mechanically_identical = not method_differences and not semantic_differences and semantic_set_equal
    return {
        "schema_version": "tos_paddle_ocr_repeat_comparison_v1",
        "first_run_id": first.get("run_id"),
        "second_run_id": second.get("run_id"),
        "method_differences": method_differences,
        "semantic_differences": semantic_differences,
        "raw_byte_differences": raw_byte_differences,
        "semantic_output_set_sha256_equal": semantic_set_equal,
        "raw_output_set_sha256_equal": raw_set_equal,
        "mechanically_identical": mechanically_identical,
        "raw_byte_identical": not raw_byte_differences and raw_set_equal,
        "nondeterminism_boundary": (
            "mechanically_identical uses exact recognized text plus canonical ordered region text, "
            "score, polygon, and box values; timing-bearing engine receipts are excluded"
        ),
        "authority_boundary": "repeatability only; no OCR accuracy or source-text verdict",
    }
