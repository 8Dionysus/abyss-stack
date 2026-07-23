#!/usr/bin/env python3
"""Run one offline, language-grouped PaddleOCR pass inside the pinned runtime."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUEST_SCHEMA = "tos_paddle_ocr_bridge_request_v2"
DETECTOR_RESIZE = {"limit_side_len": 960, "limit_type": "max"}
SAMPLE_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
RECOGNIZER_BY_LANGUAGE = {
    "de": "latin_PP-OCRv5_mobile_rec",
    "ru": "eslav_PP-OCRv5_mobile_rec",
}
REQUIRED_MODEL_FILES = ("inference.json", "inference.pdiparams", "inference.yml")


class PaddleOcrBridgeError(RuntimeError):
    """Raised when the runtime bridge cannot preserve its request contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaddleOcrBridgeError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PaddleOcrBridgeError(f"{path} must contain a JSON object")
    return payload


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _write_json(path: Path, payload: object) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
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


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _model_dir(path_value: object, label: str) -> Path:
    path = Path(str(path_value)).resolve()
    if not path.is_dir():
        raise PaddleOcrBridgeError(f"{label} model directory is missing: {path}")
    missing = [name for name in REQUIRED_MODEL_FILES if not (path / name).is_file()]
    if missing:
        raise PaddleOcrBridgeError(f"{label} model directory omits {missing}: {path}")
    return path


def _validate_request(
    request: dict[str, Any],
) -> tuple[Path, Path, dict[str, Path], list[dict[str, Any]], int, dict[str, Any]]:
    if request.get("schema_version") != REQUEST_SCHEMA:
        raise PaddleOcrBridgeError("unexpected bridge request schema")
    output_root = Path(str(request.get("output_root", ""))).resolve()
    if not output_root.is_dir():
        raise PaddleOcrBridgeError(f"bridge output root is missing: {output_root}")
    detector = _model_dir(request.get("detector_dir"), "detector")
    recognizer_values = request.get("recognizer_dirs")
    if not isinstance(recognizer_values, dict):
        raise PaddleOcrBridgeError("recognizer_dirs must be an object")
    recognizers = {
        language: _model_dir(recognizer_values.get(language), f"{language} recognizer")
        for language in RECOGNIZER_BY_LANGUAGE
    }
    cpu_threads = request.get("cpu_threads")
    if not isinstance(cpu_threads, int) or isinstance(cpu_threads, bool) or not 1 <= cpu_threads <= 64:
        raise PaddleOcrBridgeError("cpu_threads must be an integer from 1 to 64")
    samples = request.get("samples")
    if not isinstance(samples, list) or not samples:
        raise PaddleOcrBridgeError("samples must be a nonempty array")
    detector_resize = request.get("detector_resize")
    if detector_resize != DETECTOR_RESIZE:
        raise PaddleOcrBridgeError(
            "detector_resize must explicitly freeze limit_side_len=960 and limit_type=max"
        )
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise PaddleOcrBridgeError(f"samples[{index}] must be an object")
        sample_id = sample.get("sample_id")
        if not isinstance(sample_id, str) or not SAMPLE_ID_RE.fullmatch(sample_id):
            raise PaddleOcrBridgeError(f"unsafe sample_id at samples[{index}]")
        if sample_id in seen:
            raise PaddleOcrBridgeError(f"duplicate sample_id: {sample_id}")
        seen.add(sample_id)
        language = sample.get("language")
        if language not in RECOGNIZER_BY_LANGUAGE:
            raise PaddleOcrBridgeError(f"unsupported sample language: {language}")
        image_path = Path(str(sample.get("image_path", ""))).resolve()
        if not image_path.is_file():
            raise PaddleOcrBridgeError(f"sample image is missing: {image_path}")
        expected_sha256 = sample.get("image_sha256")
        if not isinstance(expected_sha256, str) or _sha256_file(image_path) != expected_sha256:
            raise PaddleOcrBridgeError(f"sample image fixity drift: {sample_id}")
        sample_root = output_root / sample_id
        if not _within(sample_root, output_root) or sample_root.exists():
            raise PaddleOcrBridgeError(f"sample output is unsafe or already exists: {sample_root}")
        normalized.append(
            {
                "sample_id": sample_id,
                "language": language,
                "image_path": image_path,
                "image_sha256": expected_sha256,
            }
        )
    return output_root, detector, recognizers, normalized, cpu_threads, detector_resize


def _region_payload(sample_id: str, result_payload: dict[str, Any]) -> dict[str, Any]:
    texts = result_payload.get("rec_texts")
    scores = result_payload.get("rec_scores")
    polygons = result_payload.get("rec_polys")
    boxes = result_payload.get("rec_boxes")
    if not all(isinstance(value, list) for value in (texts, scores, polygons, boxes)):
        raise PaddleOcrBridgeError(f"PaddleOCR result fields are not arrays: {sample_id}")
    if len({len(texts), len(scores), len(polygons), len(boxes)}) != 1:
        raise PaddleOcrBridgeError(f"PaddleOCR result fields differ in length: {sample_id}")
    regions = [
        {
            "index": index,
            "text": str(text),
            "score": float(score),
            "polygon": polygon,
            "box": box,
        }
        for index, (text, score, polygon, box) in enumerate(
            zip(texts, scores, polygons, boxes, strict=True)
        )
    ]
    semantic_rows = [
        {
            "index": row["index"],
            "text": row["text"],
            "score": row["score"],
            "polygon": row["polygon"],
            "box": row["box"],
        }
        for row in regions
    ]
    return {
        "schema_version": "tos_paddle_ocr_regions_v1",
        "sample_id": sample_id,
        "regions": regions,
        "region_count": len(regions),
        "semantic_sha256": _canonical_sha256(semantic_rows),
        "reading_order": "PaddleOCR emitted order after its pinned detector sort",
        "authority_boundary": "engine polygons, scores, and text only; not accepted transcription",
    }


def _append_progress(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def execute_bridge(request_path: Path) -> dict[str, Any]:
    request_path = request_path.resolve()
    request = _load_json(request_path)
    (
        output_root,
        detector,
        recognizers,
        samples,
        cpu_threads,
        detector_resize,
    ) = _validate_request(request)
    progress_path = output_root / "paddle-ocr-progress.jsonl"
    summary_path = output_root / "paddle-ocr-bridge-summary.json"
    if progress_path.exists() or summary_path.exists():
        raise PaddleOcrBridgeError("bridge progress or summary already exists")

    from paddleocr import PaddleOCR

    started_at = _utc_now()
    wall_started = time.perf_counter()
    pipeline_initialization: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    language_order = list(dict.fromkeys(str(sample["language"]) for sample in samples))
    for language in language_order:
        recognizer_name = RECOGNIZER_BY_LANGUAGE[language]
        initialized = time.perf_counter()
        pipeline = PaddleOCR(
            text_detection_model_name="PP-OCRv5_server_det",
            text_detection_model_dir=detector.as_posix(),
            text_recognition_model_name=recognizer_name,
            text_recognition_model_dir=recognizers[language].as_posix(),
            text_recognition_batch_size=1,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
            engine="paddle_static",
            enable_mkldnn=False,
            cpu_threads=cpu_threads,
            text_det_limit_side_len=detector_resize["limit_side_len"],
            text_det_limit_type=detector_resize["limit_type"],
        )
        initialization_seconds = time.perf_counter() - initialized
        pipeline_initialization.append(
            {
                "language": language,
                "recognizer": recognizer_name,
                "elapsed_seconds": initialization_seconds,
            }
        )
        for sample in (row for row in samples if row["language"] == language):
            sample_id = str(sample["sample_id"])
            sample_root = output_root / sample_id
            sample_root.mkdir(parents=False, exist_ok=False)
            predicted = time.perf_counter()
            results = list(
                pipeline.predict(
                    sample["image_path"].as_posix(),
                    text_det_limit_side_len=detector_resize["limit_side_len"],
                    text_det_limit_type=detector_resize["limit_type"],
                )
            )
            prediction_seconds = time.perf_counter() - predicted
            if len(results) != 1:
                raise PaddleOcrBridgeError(
                    f"PaddleOCR returned {len(results)} results for one image: {sample_id}"
                )
            json_payload = results[0].json
            if not isinstance(json_payload, dict) or not isinstance(json_payload.get("res"), dict):
                raise PaddleOcrBridgeError(f"PaddleOCR result is not a JSON object: {sample_id}")
            raw_result = json_payload["res"]
            regions = _region_payload(sample_id, raw_result)
            texts = [str(value) for value in raw_result["rec_texts"]]
            scores = [float(value) for value in raw_result["rec_scores"]]
            diplomatic_text = "\n".join(texts) + ("\n" if texts else "")

            result_path = sample_root / "paddle-result.json"
            regions_path = sample_root / "regions.json"
            text_path = sample_root / "recognition.txt"
            engine_path = sample_root / "engine.json"
            _write_json(result_path, raw_result)
            _write_json(regions_path, regions)
            _atomic_write_text(text_path, diplomatic_text)
            engine = {
                "schema_version": "tos_paddle_ocr_engine_sample_v1",
                "sample_id": sample_id,
                "language": language,
                "detector": "PP-OCRv5_server_det",
                "recognizer": recognizer_name,
                "image_ref": sample["image_path"].as_posix(),
                "image_sha256": sample["image_sha256"],
                "prediction_seconds": prediction_seconds,
                "pipeline_initialization_seconds": initialization_seconds,
                "region_count": len(texts),
                "recognized_characters": len(diplomatic_text),
                "recognized_non_whitespace_characters": len("".join(diplomatic_text.split())),
                "mean_engine_confidence": statistics.fmean(scores) if scores else None,
                "median_engine_confidence": statistics.median(scores) if scores else None,
                "minimum_engine_confidence": min(scores) if scores else None,
                "maximum_engine_confidence": max(scores) if scores else None,
                "configuration": {
                    "device": "cpu",
                    "engine": "paddle_static",
                    "enable_mkldnn": False,
                    "cpu_threads": cpu_threads,
                    "text_recognition_batch_size": 1,
                    "text_det_limit_side_len": detector_resize["limit_side_len"],
                    "text_det_limit_type": detector_resize["limit_type"],
                    "document_orientation": False,
                    "document_unwarping": False,
                    "textline_orientation": False,
                    "preprocessing": "none-outside-the-frozen-render",
                },
                "confidence_boundary": "engine confidence is not source-visible accuracy",
            }
            _write_json(engine_path, engine)
            progress = {
                "completed_at_utc": _utc_now(),
                "sample_id": sample_id,
                "language": language,
                "recognizer": recognizer_name,
                "prediction_seconds": prediction_seconds,
                "region_count": len(texts),
                "result_sha256": _sha256_file(result_path),
                "regions_sha256": _sha256_file(regions_path),
                "regions_semantic_sha256": regions["semantic_sha256"],
                "text_sha256": _sha256_file(text_path),
                "engine_sha256": _sha256_file(engine_path),
            }
            _append_progress(progress_path, progress)
            completed.append(progress)
        del pipeline
        gc.collect()

    summary = {
        "schema_version": "tos_paddle_ocr_bridge_summary_v1",
        "started_at_utc": started_at,
        "finished_at_utc": _utc_now(),
        "request_ref": request_path.as_posix(),
        "request_sha256": _sha256_file(request_path),
        "sample_count": len(completed),
        "sample_ids": [row["sample_id"] for row in completed],
        "language_order": language_order,
        "pipeline_initialization": pipeline_initialization,
        "wall_seconds": time.perf_counter() - wall_started,
        "configuration": {
            "device": "cpu",
            "engine": "paddle_static",
            "enable_mkldnn": False,
            "cpu_threads": cpu_threads,
            "text_recognition_batch_size": 1,
            "text_det_limit_side_len": detector_resize["limit_side_len"],
            "text_det_limit_type": detector_resize["limit_type"],
            "network": "offline-enforced-by-runtime-wrapper",
        },
        "authority_boundary": "runtime OCR mechanics only; no content or quality acceptance",
    }
    _write_json(summary_path, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = execute_bridge(args.request)
    except PaddleOcrBridgeError as exc:
        print(f"[error] {exc}", file=os.sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
