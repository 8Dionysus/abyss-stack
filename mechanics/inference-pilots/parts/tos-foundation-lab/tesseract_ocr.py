#!/usr/bin/env python3
"""Execute frozen OCR A with Tesseract over the shared visual packet."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import resource
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ocr_render import OcrRenderError, verify_render_manifest, validate_visual_plan
from runtime_manifest import RuntimeManifestError, verify_runtime_manifest


LANGUAGE_MAP = {"de": "deu", "ru": "rus"}
EXPECTED_OUTPUT_EXTENSIONS = {
    "text": ".txt",
    "tsv": ".tsv",
    "hocr": ".hocr",
    "alto": ".xml",
}
TESSERACT_ARGUMENTS = (
    "--oem",
    "1",
    "--psm",
    "3",
    "-c",
    "preserve_interword_spaces=1",
    "-c",
    "hocr_char_boxes=1",
    "txt",
    "tsv",
    "hocr",
    "alto",
)


class TesseractOcrError(RuntimeError):
    """Raised when OCR A cannot preserve the frozen experiment law."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TesseractOcrError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TesseractOcrError(f"{path} must contain a JSON object")
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


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_sha256(payload: object) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _relative(run_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(run_root.resolve()).as_posix()
    except ValueError as exc:
        raise TesseractOcrError(f"artifact escapes run root: {path}") from exc


def _version(command: Path, environment: dict[str, str]) -> str:
    completed = subprocess.run(
        (command.as_posix(), "--version"),
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        env=environment,
    )
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if completed.returncode != 0 or "tesseract 5.5.2" not in combined.lower():
        raise TesseractOcrError(f"unexpected Tesseract identity: {combined[:400]}")
    return combined.splitlines()[0][:240]


def _tsv_diagnostics(path: Path) -> dict[str, Any]:
    confidences: list[float] = []
    words = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                text = str(row.get("text") or "")
                try:
                    confidence = float(str(row.get("conf") or "-1"))
                except ValueError:
                    continue
                if confidence >= 0:
                    confidences.append(confidence)
                    if text.strip():
                        words += 1
    except OSError as exc:
        raise TesseractOcrError(f"cannot inspect TSV {path}: {exc}") from exc
    return {
        "recognized_word_rows": words,
        "confidence_row_count": len(confidences),
        "mean_confidence": statistics.fmean(confidences) if confidences else None,
        "median_confidence": statistics.median(confidences) if confidences else None,
        "diagnostic_boundary": "engine confidence is not source-visible accuracy",
    }


def _output_set_digest(samples: list[dict[str, Any]]) -> str:
    return _canonical_sha256(
        [
            {
                "sample_id": row["sample_id"],
                "render_sha256": row["render_sha256"],
                "outputs": {
                    name: {
                        "sha256": output["sha256"],
                        "bytes": output["bytes"],
                    }
                    for name, output in sorted(row["outputs"].items())
                },
            }
            for row in samples
        ]
    )


def _verify_prepared_run(
    run_root: Path, runtime_manifest_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    receipt = _load_json(run_root / "run.receipt.json")
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if receipt.get("experiment_id") != "tos-ocr-foundation-v1" or receipt.get("variant") != "A":
        raise TesseractOcrError("Tesseract runner requires prepared OCR A")
    if receipt.get("status") != "prepared" or preflight.get("decision") != "ready":
        raise TesseractOcrError("run must be prepared from a ready preflight")
    if experiment.get("family") != "ocr":
        raise TesseractOcrError("experiment specification is not OCR")
    admission = preflight.get("runtime_admission")
    if not isinstance(admission, dict) or admission.get("verified") is not True:
        raise TesseractOcrError("preflight does not contain a verified isolated runtime")
    if Path(str(admission.get("manifest_ref"))).resolve() != runtime_manifest_path.resolve():
        raise TesseractOcrError("runtime manifest differs from the preflighted manifest")
    if _sha256_file(runtime_manifest_path.resolve()) != admission.get("manifest_sha256"):
        raise TesseractOcrError("runtime manifest digest drift after preflight")
    return receipt, experiment, preflight


def execute_tesseract_ocr(
    run_root: Path,
    sample_plan_path: Path,
    render_manifest_path: Path,
    runtime_manifest_path: Path,
    *,
    invocation: list[str],
) -> dict[str, Any]:
    """Run Tesseract A and leave quality awaiting real manual review."""

    run_root = run_root.resolve()
    sample_plan_path = sample_plan_path.resolve()
    render_manifest_path = render_manifest_path.resolve()
    runtime_manifest_path = runtime_manifest_path.resolve()
    receipt_path = run_root / "run.receipt.json"
    receipt, experiment, preflight = _verify_prepared_run(run_root, runtime_manifest_path)
    plan = _load_json(sample_plan_path)
    plan_issues = validate_visual_plan(plan)
    if plan_issues:
        raise TesseractOcrError("invalid frozen visual plan: " + "; ".join(plan_issues))
    try:
        render_manifest = verify_render_manifest(render_manifest_path)
    except OcrRenderError as exc:
        raise TesseractOcrError(str(exc)) from exc
    if render_manifest.get("sample_plan_sha256") != _sha256_file(sample_plan_path):
        raise TesseractOcrError("render packet was built from a different visual plan")
    if render_manifest.get("reference_witness_state") != "sealed-not-consulted":
        raise TesseractOcrError("reference witness seal is not intact")
    try:
        runtime = verify_runtime_manifest(
            runtime_manifest_path,
            experiment_id="tos-ocr-foundation-v1",
            variant="A",
            required_commands=["tesseract"],
        )
    except RuntimeManifestError as exc:
        raise TesseractOcrError(str(exc)) from exc

    command = Path(runtime["commands"]["tesseract"])
    environment = os.environ.copy()
    environment.update({str(key): str(value) for key, value in runtime["environment"].items()})
    environment.update(
        {
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "OMP_THREAD_LIMIT": "4",
            "OMP_NUM_THREADS": "4",
        }
    )
    version = _version(command, environment)
    renders = render_manifest["renders"]
    render_root = Path(render_manifest["artifact_root"])

    started_at = _utc_now()
    wall_started = time.perf_counter()
    receipt["status"] = "running"
    receipt["started_at_utc"] = started_at
    _write_json(receipt_path, receipt)

    artifact_refs: list[str] = []
    samples: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    child_rss_before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    try:
        for render in renders:
            sample_id = str(render["sample_id"])
            language = LANGUAGE_MAP.get(str(render["language"]))
            if language is None:
                raise TesseractOcrError(f"unsupported OCR language for {sample_id}")
            image_path = render_root / str(render["png_ref"])
            if _sha256_file(image_path) != render["png_sha256"]:
                raise TesseractOcrError(f"render drift immediately before OCR: {sample_id}")
            sample_root = run_root / "raw-output" / sample_id
            sample_root.mkdir(parents=True, exist_ok=False)
            output_base = sample_root / sample_id
            arguments = (
                command.as_posix(),
                image_path.as_posix(),
                output_base.as_posix(),
                "-l",
                language,
                *TESSERACT_ARGUMENTS,
            )
            started = time.perf_counter()
            completed = subprocess.run(
                arguments,
                check=False,
                capture_output=True,
                timeout=600,
                env=environment,
            )
            elapsed = time.perf_counter() - started
            if completed.returncode != 0:
                stderr = completed.stderr.decode("utf-8", errors="replace")
                raise TesseractOcrError(
                    f"Tesseract failed for {sample_id} with {completed.returncode}: {stderr[:400]}"
                )
            outputs: dict[str, dict[str, Any]] = {}
            for name, extension in EXPECTED_OUTPUT_EXTENSIONS.items():
                path = output_base.with_suffix(extension)
                if not path.is_file():
                    raise TesseractOcrError(f"Tesseract omitted {name} output for {sample_id}")
                outputs[name] = {
                    "ref": _relative(run_root, path),
                    "sha256": _sha256_file(path),
                    "bytes": path.stat().st_size,
                }
                artifact_refs.append(_relative(run_root, path))
            diagnostics = _tsv_diagnostics(output_base.with_suffix(".tsv"))
            text = output_base.with_suffix(".txt").read_text(encoding="utf-8", errors="replace")
            if not text.strip():
                warnings.append({"sample_id": sample_id, "warning": "empty-recognized-text"})
            stderr_text = completed.stderr.decode("utf-8", errors="replace")
            if stderr_text.strip():
                warnings.append({"sample_id": sample_id, "warning": "tesseract-stderr-nonempty"})
            metadata = {
                "sample_id": sample_id,
                "source_anchor_ref": render["anchor_ref"],
                "item_ref": render["item_ref"],
                "file_ref": render["file_ref"],
                "page": render["page"],
                "language": render["language"],
                "tesseract_language": language,
                "difficulty": render["difficulty"],
                "gold_candidate": render["gold_candidate"],
                "render_ref": render["png_ref"],
                "render_sha256": render["png_sha256"],
                "outputs": outputs,
                "elapsed_seconds": elapsed,
                "returncode": completed.returncode,
                "stdout_sha256": _sha256_bytes(completed.stdout),
                "stderr_sha256": _sha256_bytes(completed.stderr),
                "stderr_line_count": len(stderr_text.splitlines()),
                "recognized_characters": len(text),
                "recognized_non_whitespace_characters": len("".join(text.split())),
                "diagnostics": diagnostics,
                "content_status": "unreviewed-ocr-draft",
                "authority_boundary": "engine output only; not source text or accepted transcription",
            }
            metadata_path = sample_root / "sample.json"
            _write_json(metadata_path, metadata)
            artifact_refs.append(_relative(run_root, metadata_path))
            samples.append(metadata)

        output_manifest = {
            "schema_version": "tos_tesseract_ocr_output_manifest_v1",
            "experiment_id": "tos-ocr-foundation-v1",
            "variant": "A",
            "run_id": receipt["run_id"],
            "sample_plan_sha256": _sha256_file(sample_plan_path),
            "render_manifest_ref": render_manifest_path.as_posix(),
            "render_manifest_sha256": _sha256_file(render_manifest_path),
            "render_id": render_manifest["render_id"],
            "render_set_sha256": render_manifest["render_set_sha256"],
            "runtime_manifest_ref": runtime_manifest_path.as_posix(),
            "runtime_manifest_sha256": _sha256_file(runtime_manifest_path),
            "runtime_artifact_set_sha256": runtime["artifact_set_sha256"],
            "tesseract_version": version,
            "configuration": {
                "arguments_after_language": list(TESSERACT_ARGUMENTS),
                "language_map": LANGUAGE_MAP,
                "locale": "C.UTF-8",
                "omp_thread_limit": 4,
                "preprocessing": "none-outside-the-frozen-render",
            },
            "reference_witness_state": "sealed-not-consulted",
            "samples": samples,
            "recognition_set_sha256": _output_set_digest(samples),
            "quality_status": "blocked-until-double-checked-human-gold",
            "authority_boundary": "reproducible OCR candidate evidence only; no source-text or winner verdict",
        }
        output_manifest_path = run_root / "raw-output/ocr-output-manifest.json"
        _write_json(output_manifest_path, output_manifest)
        artifact_refs.append(_relative(run_root, output_manifest_path))

        warnings_path = run_root / "raw-output/warnings.json"
        _write_json(warnings_path, {"warnings": warnings})
        artifact_refs.append(_relative(run_root, warnings_path))
        elapsed = time.perf_counter() - wall_started
        confidences = [
            sample["diagnostics"]["mean_confidence"]
            for sample in samples
            if sample["diagnostics"]["mean_confidence"] is not None
        ]
        artifact_bytes = sum(
            path.stat().st_size
            for path in run_root.rglob("*")
            if path.is_file() and path != receipt_path
        )
        metrics = {
            "schema_version": "tos_tesseract_ocr_metrics_v1",
            "experiment_id": "tos-ocr-foundation-v1",
            "variant": "A",
            "sample_count": len(samples),
            "source_count": len({sample["item_ref"] for sample in samples}),
            "wall_seconds": elapsed,
            "pages_per_minute": len(samples) * 60 / elapsed if elapsed else None,
            "child_peak_rss_bytes": max(
                child_rss_before,
                resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            )
            * 1024,
            "artifact_bytes": artifact_bytes,
            "empty_text_count": sum(
                sample["recognized_non_whitespace_characters"] == 0 for sample in samples
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
                "mechanical_anchor_resolution": len(samples) / len(renders) if renders else None,
                "content_acceptance": "not-reviewed",
            },
            "authority_boundary": "mechanics, speed, resource, and engine diagnostics only; no OCR quality verdict",
        }
        metrics_path = run_root / "metrics/tesseract-ocr-summary.json"
        _write_json(metrics_path, metrics)

        invocation_path = run_root / "receipts/tesseract-ocr-invocation.json"
        _write_json(
            invocation_path,
            {
                "captured_at_utc": started_at,
                "argv": invocation,
                "python": platform.python_version(),
                "tesseract": version,
                "runner_sha256": _sha256_file(Path(__file__)),
                "sample_plan_sha256": _sha256_file(sample_plan_path),
                "render_manifest_sha256": _sha256_file(render_manifest_path),
                "render_set_sha256": render_manifest["render_set_sha256"],
                "runtime_manifest_sha256": _sha256_file(runtime_manifest_path),
                "runtime_artifact_set_sha256": runtime["artifact_set_sha256"],
                "rights_posture": "restricted-source-derived-text-private-runtime-only",
                "reference_witness_state": "sealed-not-consulted",
            },
        )
        artifact_refs.append(_relative(run_root, invocation_path))

        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = [sample["sample_id"] for sample in samples]
        receipt["method_revision"] = {
            "implementation": experiment["variants"][0]["implementation"],
            "version": version,
            "runtime": runtime["runtime_id"],
            "model": "Fedora tessdata_fast deu/rus 4.1.0-12.fc44",
            "artifact_digest": runtime["artifact_set_sha256"],
        }
        receipt["invocation_ref"] = _relative(run_root, invocation_path)
        receipt["artifact_refs"] = sorted(set(artifact_refs))
        receipt["metric_refs"] = [_relative(run_root, metrics_path)]
        receipt["manual_review_refs"] = []
        receipt["errors"] = []
        _write_json(receipt_path, receipt)
        return metrics
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)]
        _write_json(receipt_path, receipt)
        if isinstance(exc, TesseractOcrError):
            raise
        raise TesseractOcrError(str(exc)) from exc


def compare_tesseract_runs(first_run_root: Path, second_run_root: Path) -> dict[str, Any]:
    """Compare only frozen-input/output identities, excluding timing metadata."""

    first = _load_json(first_run_root.resolve() / "raw-output/ocr-output-manifest.json")
    second = _load_json(second_run_root.resolve() / "raw-output/ocr-output-manifest.json")
    common_fields = (
        "sample_plan_sha256",
        "render_set_sha256",
        "runtime_artifact_set_sha256",
        "tesseract_version",
        "configuration",
    )
    method_differences = [field for field in common_fields if first.get(field) != second.get(field)]
    first_samples = {row["sample_id"]: row for row in first.get("samples", [])}
    second_samples = {row["sample_id"]: row for row in second.get("samples", [])}
    sample_differences: list[dict[str, Any]] = []
    for sample_id in sorted(set(first_samples) | set(second_samples)):
        left = first_samples.get(sample_id)
        right = second_samples.get(sample_id)
        if left is None or right is None:
            sample_differences.append({"sample_id": sample_id, "difference": "missing-sample"})
            continue
        for output_name in sorted(set(left["outputs"]) | set(right["outputs"])):
            left_output = left["outputs"].get(output_name)
            right_output = right["outputs"].get(output_name)
            if left_output is None or right_output is None or (
                left_output.get("sha256"), left_output.get("bytes")
            ) != (right_output.get("sha256"), right_output.get("bytes")):
                sample_differences.append(
                    {"sample_id": sample_id, "difference": "output-digest", "output": output_name}
                )
    identical = not method_differences and not sample_differences
    return {
        "schema_version": "tos_tesseract_ocr_repeat_comparison_v1",
        "first_run_id": first.get("run_id"),
        "second_run_id": second.get("run_id"),
        "method_differences": method_differences,
        "sample_differences": sample_differences,
        "recognition_set_sha256_equal": first.get("recognition_set_sha256")
        == second.get("recognition_set_sha256"),
        "mechanically_identical": identical
        and first.get("recognition_set_sha256") == second.get("recognition_set_sha256"),
        "authority_boundary": "repeatability only; no OCR accuracy or source-text verdict",
    }
