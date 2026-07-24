#!/usr/bin/env python3
"""Run the pinned local PaddleOCR-VL structure challenger inside its runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUEST_SCHEMA = "tos_paddle_vl_structure_bridge_request_v1"
SAMPLE_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class PaddleVlStructureBridgeError(RuntimeError):
    """Raised when Structure C cannot preserve its local bridge contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaddleVlStructureBridgeError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PaddleVlStructureBridgeError(f"{path} must contain a JSON object")
    return payload


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _write_json(path: Path, payload: object) -> None:
    _atomic_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _validate_request(
    request: dict[str, Any],
) -> tuple[Path, Path, Path, list[dict[str, Any]], dict[str, Any]]:
    if request.get("schema_version") != REQUEST_SCHEMA:
        raise PaddleVlStructureBridgeError("unexpected bridge request schema")
    output_root = Path(str(request.get("output_root", ""))).resolve()
    if not output_root.is_dir():
        raise PaddleVlStructureBridgeError(f"output root is missing: {output_root}")
    vl_model = Path(str(request.get("vl_model_dir", ""))).resolve()
    layout_model = Path(str(request.get("layout_model_dir", ""))).resolve()
    for model, files in (
        (vl_model, ("model.safetensors", "config.json", "tokenizer.json")),
        (layout_model, ("inference.pdiparams", "inference.json", "inference.yml")),
    ):
        if not model.is_dir() or any(not (model / name).is_file() for name in files):
            raise PaddleVlStructureBridgeError(f"incomplete model directory: {model}")
    config = request.get("configuration")
    expected_config = {
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
    if config != expected_config:
        raise PaddleVlStructureBridgeError("Structure C configuration drift")
    samples = request.get("samples")
    if not isinstance(samples, list) or not samples:
        raise PaddleVlStructureBridgeError("samples must be a nonempty array")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(samples):
        if not isinstance(row, dict):
            raise PaddleVlStructureBridgeError(f"samples[{index}] is not an object")
        sample_id = row.get("sample_id")
        if (
            not isinstance(sample_id, str)
            or not SAMPLE_ID_RE.fullmatch(sample_id)
            or sample_id in seen
        ):
            raise PaddleVlStructureBridgeError(f"unsafe or duplicate sample_id: {sample_id}")
        seen.add(sample_id)
        image = Path(str(row.get("image_path", ""))).resolve()
        if not image.is_file() or _sha256_file(image) != row.get("image_sha256"):
            raise PaddleVlStructureBridgeError(f"sample image fixity drift: {sample_id}")
        sample_root = output_root / sample_id
        if not _within(sample_root, output_root) or sample_root.exists():
            raise PaddleVlStructureBridgeError(f"unsafe sample output: {sample_root}")
        normalized.append(
            {
                "sample_id": sample_id,
                "image_path": image,
                "image_sha256": row["image_sha256"],
            }
        )
    return output_root, vl_model, layout_model, normalized, expected_config


def _append_progress(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute_bridge(request_path: Path) -> dict[str, Any]:
    request_path = request_path.resolve()
    request = _load_json(request_path)
    output_root, vl_model, layout_model, samples, config = _validate_request(request)
    progress_path = output_root / "paddle-vl-structure-progress.jsonl"
    summary_path = output_root / "paddle-vl-structure-bridge-summary.json"
    if progress_path.exists() or summary_path.exists():
        raise PaddleVlStructureBridgeError("bridge progress or summary already exists")

    from paddleocr import PaddleOCRVL

    started_at = _utc_now()
    wall_started = time.perf_counter()
    _append_progress(
        progress_path,
        {
            "event": "pipeline_initialization_started",
            "at_utc": started_at,
            "sample_count": len(samples),
        },
    )
    initialized = time.perf_counter()
    pipeline = PaddleOCRVL(
        pipeline_version=config["pipeline_version"],
        layout_detection_model_name="PP-DocLayoutV3",
        layout_detection_model_dir=layout_model.as_posix(),
        vl_rec_model_name="PaddleOCR-VL-1.6-0.9B",
        vl_rec_model_dir=vl_model.as_posix(),
        vl_rec_backend="native",
        device=config["device"],
        use_doc_orientation_classify=config["use_doc_orientation_classify"],
        use_doc_unwarping=config["use_doc_unwarping"],
        use_layout_detection=config["use_layout_detection"],
        use_chart_recognition=config["use_chart_recognition"],
        use_seal_recognition=config["use_seal_recognition"],
        use_ocr_for_image_block=config["use_ocr_for_image_block"],
        format_block_content=config["format_block_content"],
        merge_layout_blocks=config["merge_layout_blocks"],
        markdown_ignore_labels=config["markdown_ignore_labels"],
        use_queues=config["use_queues"],
    )
    initialization_seconds = time.perf_counter() - initialized
    _append_progress(
        progress_path,
        {
            "event": "pipeline_initialization_completed",
            "at_utc": _utc_now(),
            "initialization_seconds": initialization_seconds,
            "sample_count": len(samples),
        },
    )
    completed: list[dict[str, Any]] = []
    for sample in samples:
        sample_id = sample["sample_id"]
        sample_root = output_root / sample_id
        sample_root.mkdir()
        _append_progress(
            progress_path,
            {
                "event": "sample_prediction_started",
                "at_utc": _utc_now(),
                "sample_id": sample_id,
                "completed_count": len(completed),
                "sample_count": len(samples),
            },
        )
        predicted = time.perf_counter()
        results = list(
            pipeline.predict(
                sample["image_path"].as_posix(),
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_layout_detection=True,
                use_chart_recognition=False,
                use_seal_recognition=False,
                use_ocr_for_image_block=False,
                format_block_content=True,
                merge_layout_blocks=True,
                markdown_ignore_labels=[],
                use_queues=False,
                max_pixels=config["max_pixels"],
                max_new_tokens=config["max_new_tokens"],
                temperature=config["temperature"],
            )
        )
        prediction_seconds = time.perf_counter() - predicted
        if len(results) != 1:
            raise PaddleVlStructureBridgeError(
                f"PaddleOCR-VL returned {len(results)} results for {sample_id}"
            )
        payload = results[0].json
        if not isinstance(payload, dict) or not isinstance(payload.get("res"), dict):
            raise PaddleVlStructureBridgeError(f"invalid PaddleOCR-VL JSON: {sample_id}")
        raw = payload["res"]
        blocks = raw.get("parsing_res_list")
        if not isinstance(blocks, list):
            raise PaddleVlStructureBridgeError(f"missing parsing_res_list: {sample_id}")
        normalized_blocks = [
            {
                "index": index,
                "label": str(block.get("block_label", "")),
                "content": str(block.get("block_content", "")),
                "bbox": block.get("block_bbox"),
                "polygon": block.get("block_polygon_points"),
                "engine_order": block.get("block_order"),
                "engine_block_id": block.get("block_id"),
                "engine_group_id": block.get("group_id"),
            }
            for index, block in enumerate(blocks)
            if isinstance(block, dict)
        ]
        markdown = results[0].markdown
        markdown_text = (
            str(markdown.get("markdown_texts", ""))
            if isinstance(markdown, dict)
            else ""
        )
        raw_path = sample_root / "paddle-vl-result.json"
        blocks_path = sample_root / "ordered-blocks.json"
        markdown_path = sample_root / "document.md"
        engine_path = sample_root / "engine.json"
        _write_json(raw_path, raw)
        _write_json(
            blocks_path,
            {
                "schema_version": "tos_paddle_vl_ordered_blocks_v1",
                "sample_id": sample_id,
                "blocks": normalized_blocks,
                "block_count": len(normalized_blocks),
                "authority_boundary": "engine-emitted blocks and order only; not accepted structure",
            },
        )
        _atomic_text(markdown_path, markdown_text)
        _write_json(
            engine_path,
            {
                "schema_version": "tos_paddle_vl_structure_engine_sample_v1",
                "sample_id": sample_id,
                "image_ref": sample["image_path"].as_posix(),
                "image_sha256": sample["image_sha256"],
                "prediction_seconds": prediction_seconds,
                "pipeline_initialization_seconds": initialization_seconds,
                "block_count": len(normalized_blocks),
                "nonempty_block_count": sum(bool(row["content"].strip()) for row in normalized_blocks),
                "configuration": config,
                "authority_boundary": "mechanical diagnostic only; not a quality verdict",
            },
        )
        progress = {
            "event": "sample_completed",
            "completed_at_utc": _utc_now(),
            "sample_id": sample_id,
            "completed_count": len(completed) + 1,
            "sample_count": len(samples),
            "prediction_seconds": prediction_seconds,
            "block_count": len(normalized_blocks),
            "raw_sha256": _sha256_file(raw_path),
            "blocks_sha256": _sha256_file(blocks_path),
            "markdown_sha256": _sha256_file(markdown_path),
            "engine_sha256": _sha256_file(engine_path),
        }
        _append_progress(progress_path, progress)
        completed.append(progress)

    summary_started = _utc_now()
    _append_progress(
        progress_path,
        {
            "event": "bridge_summary_started",
            "at_utc": summary_started,
            "completed_count": len(completed),
            "sample_count": len(samples),
        },
    )
    summary = {
        "schema_version": "tos_paddle_vl_structure_bridge_summary_v1",
        "started_at_utc": started_at,
        "finished_at_utc": _utc_now(),
        "request_ref": request_path.as_posix(),
        "request_sha256": _sha256_file(request_path),
        "sample_count": len(completed),
        "sample_ids": [row["sample_id"] for row in completed],
        "initialization_seconds": initialization_seconds,
        "prediction_seconds": sum(float(row["prediction_seconds"]) for row in completed),
        "wall_seconds": time.perf_counter() - wall_started,
        "configuration": config,
        "authority_boundary": "runtime structure mechanics only; no content or quality acceptance",
    }
    _write_json(summary_path, summary)
    _append_progress(
        progress_path,
        {
            "event": "bridge_completed",
            "at_utc": _utc_now(),
            "completed_count": len(completed),
            "sample_count": len(samples),
            "summary_sha256": _sha256_file(summary_path),
        },
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = execute_bridge(args.request)
    except PaddleVlStructureBridgeError as exc:
        print(f"[error] {exc}", file=os.sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
