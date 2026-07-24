#!/usr/bin/env python3
"""Run the pinned offline Docling Structure B bridge inside its runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any


REQUEST_SCHEMA = "tos_docling_structure_bridge_request_v1"
SAMPLE_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class DoclingStructureBridgeError(RuntimeError):
    """Raised when the Structure B bridge cannot preserve its frozen contract."""


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DoclingStructureBridgeError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DoclingStructureBridgeError(f"{path} must contain a JSON object")
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


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def _append_progress(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _expected_configuration() -> dict[str, Any]:
    return {
        "docling_version": "2.115.0",
        "layout_repository": "docling-project/docling-layout-heron",
        "layout_revision": "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8",
        "device": "cpu",
        "threads": 4,
        "enable_remote_services": False,
        "allow_external_plugins": False,
        "do_table_structure": False,
        "do_code_enrichment": False,
        "do_formula_enrichment": False,
        "do_picture_classification": False,
        "do_picture_description": False,
        "do_chart_extraction": False,
        "generate_page_images": False,
        "generate_picture_images": False,
        "generate_table_images": False,
        "native_text_min_non_whitespace": 1,
        "tesseract_force_full_page_ocr": True,
        "document_timeout_seconds": 600.0,
    }


def _validate_request(
    request: dict[str, Any],
) -> tuple[
    Path,
    Path,
    Path,
    Path,
    list[dict[str, Any]],
    dict[str, Any],
]:
    if request.get("schema_version") != REQUEST_SCHEMA:
        raise DoclingStructureBridgeError("unexpected bridge request schema")
    output_root = Path(str(request.get("output_root", ""))).resolve()
    model_dir = Path(str(request.get("model_dir", ""))).resolve()
    tesseract_command = Path(str(request.get("tesseract_command", ""))).resolve()
    tessdata_dir = Path(str(request.get("tessdata_dir", ""))).resolve()
    if not output_root.is_dir():
        raise DoclingStructureBridgeError(f"output root is missing: {output_root}")
    for required in ("model.safetensors", "config.json", "preprocessor_config.json"):
        if not (model_dir / required).is_file():
            raise DoclingStructureBridgeError(f"incomplete Heron model directory: {required}")
    if not tesseract_command.is_file() or not os.access(tesseract_command, os.X_OK):
        raise DoclingStructureBridgeError("Tesseract command is missing or not executable")
    if not tessdata_dir.is_dir():
        raise DoclingStructureBridgeError("Tesseract data directory is missing")
    config = request.get("configuration")
    expected = _expected_configuration()
    if config != expected:
        raise DoclingStructureBridgeError("Structure B configuration drift")
    samples = request.get("samples")
    if not isinstance(samples, list) or not samples:
        raise DoclingStructureBridgeError("samples must be a nonempty array")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(samples):
        if not isinstance(row, dict):
            raise DoclingStructureBridgeError(f"samples[{index}] is not an object")
        sample_id = row.get("sample_id")
        if (
            not isinstance(sample_id, str)
            or not SAMPLE_ID_RE.fullmatch(sample_id)
            or sample_id in seen
        ):
            raise DoclingStructureBridgeError(f"unsafe or duplicate sample_id: {sample_id}")
        seen.add(sample_id)
        source = Path(str(row.get("source_path", ""))).resolve()
        if not source.is_file() or _sha256_file(source) != row.get("source_sha256"):
            raise DoclingStructureBridgeError(f"source fixity drift: {sample_id}")
        source_kind = row.get("source_kind")
        if source_kind == "pdf-page":
            page = row.get("page")
            language = row.get("language")
            if (
                not isinstance(page, int)
                or page < 1
                or language not in {"deu", "rus"}
                or not (tessdata_dir / f"{language}.traineddata").is_file()
            ):
                raise DoclingStructureBridgeError(f"invalid PDF unit: {sample_id}")
            unit = {"page": page, "language": language}
        elif source_kind == "epub-xhtml":
            member_path = row.get("member_path")
            member_sha256 = row.get("member_sha256")
            if (
                not isinstance(member_path, str)
                or not member_path
                or not isinstance(member_sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", member_sha256)
            ):
                raise DoclingStructureBridgeError(f"invalid EPUB unit: {sample_id}")
            unit = {
                "member_path": member_path,
                "member_sha256": member_sha256,
            }
        else:
            raise DoclingStructureBridgeError(f"unsupported source kind: {sample_id}")
        sample_root = output_root / sample_id
        if not _within(sample_root, output_root) or sample_root.exists():
            raise DoclingStructureBridgeError(f"unsafe sample output: {sample_root}")
        normalized.append(
            {
                "sample_id": sample_id,
                "source_path": source,
                "source_sha256": row["source_sha256"],
                "source_kind": source_kind,
                **unit,
            }
        )
    return (
        output_root,
        model_dir,
        tesseract_command,
        tessdata_dir,
        normalized,
        expected,
    )


def _native_pdf_text(path: Path, page_number: int) -> str:
    import pypdfium2

    document = pypdfium2.PdfDocument(path.as_posix())
    try:
        if page_number > len(document):
            raise DoclingStructureBridgeError(
                f"PDF has no page {page_number}: {path.name}"
            )
        page = document[page_number - 1]
        try:
            text_page = page.get_textpage()
            try:
                return str(text_page.get_text_range())
            finally:
                text_page.close()
        finally:
            page.close()
    finally:
        document.close()


def _normalized_blocks(document: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for order, (item, level) in enumerate(
        document.iterate_items(with_groups=True, traverse_pictures=True)
    ):
        serialized = item.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        label = getattr(item, "label", None)
        blocks.append(
            {
                "order": order,
                "depth": level,
                "self_ref": serialized.get("self_ref"),
                "label": getattr(label, "value", label),
                "text": getattr(item, "text", None),
                "provenance": serialized.get("prov", []),
                "item": serialized,
            }
        )
    return blocks


def _conversion_errors(result: Any) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for error in getattr(result, "errors", []):
        if hasattr(error, "model_dump"):
            errors.append(error.model_dump(mode="json", by_alias=True, exclude_none=True))
        else:
            errors.append({"message": str(error)})
    return errors


def execute_bridge(request_path: Path) -> dict[str, Any]:
    request_path = request_path.resolve()
    request = _load_json(request_path)
    (
        output_root,
        model_dir,
        tesseract_command,
        tessdata_dir,
        samples,
        config,
    ) = _validate_request(request)

    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import (
        ConversionStatus,
        DocumentStream,
        InputFormat,
    )
    from docling.datamodel.layout_model_specs import LayoutModelConfig
    from docling.datamodel.pipeline_options import (
        LayoutOptions,
        PdfPipelineOptions,
        TesseractCliOcrOptions,
    )
    from docling.document_converter import (
        DocumentConverter,
        HTMLFormatOption,
        PdfFormatOption,
    )

    layout_spec = LayoutModelConfig(
        name="docling_layout_heron",
        repo_id=config["layout_repository"],
        revision=config["layout_revision"],
        model_path="",
    )

    def pdf_options(*, do_ocr: bool, language: str) -> PdfPipelineOptions:
        return PdfPipelineOptions(
            artifacts_path=model_dir.parent,
            accelerator_options=AcceleratorOptions(
                device=config["device"],
                num_threads=config["threads"],
            ),
            enable_remote_services=config["enable_remote_services"],
            allow_external_plugins=config["allow_external_plugins"],
            do_table_structure=config["do_table_structure"],
            do_ocr=do_ocr,
            force_backend_text=not do_ocr,
            do_code_enrichment=config["do_code_enrichment"],
            do_formula_enrichment=config["do_formula_enrichment"],
            do_picture_classification=config["do_picture_classification"],
            do_picture_description=config["do_picture_description"],
            do_chart_extraction=config["do_chart_extraction"],
            generate_page_images=config["generate_page_images"],
            generate_picture_images=config["generate_picture_images"],
            generate_table_images=config["generate_table_images"],
            document_timeout=config["document_timeout_seconds"],
            layout_options=LayoutOptions(model_spec=layout_spec),
            ocr_options=TesseractCliOcrOptions(
                lang=[language],
                force_full_page_ocr=config["tesseract_force_full_page_ocr"],
                tesseract_cmd=tesseract_command.as_posix(),
                path=tessdata_dir.as_posix(),
            ),
        )

    native_pdf_converter: DocumentConverter | None = None
    ocr_pdf_converters: dict[str, DocumentConverter] = {}
    html_converter = DocumentConverter(
        allowed_formats=[InputFormat.HTML],
        format_options={InputFormat.HTML: HTMLFormatOption()},
    )

    progress_path = output_root / "docling-structure-progress.jsonl"
    summary_path = output_root / "docling-structure-bridge-summary.json"
    if progress_path.exists() or summary_path.exists():
        raise DoclingStructureBridgeError("bridge progress or summary already exists")

    started_at = _utc_now()
    wall_started = time.perf_counter()
    completed: list[dict[str, Any]] = []
    for sample in samples:
        sample_started = time.perf_counter()
        sample_id = sample["sample_id"]
        sample_root = output_root / sample_id
        sample_root.mkdir()
        native_probe: dict[str, Any] | None = None
        if sample["source_kind"] == "pdf-page":
            native_text = _native_pdf_text(sample["source_path"], sample["page"])
            native_characters = len("".join(native_text.split()))
            usable = native_characters >= config["native_text_min_non_whitespace"]
            native_probe = {
                "method": "pypdfium2-textpage",
                "non_whitespace_characters": native_characters,
                "text_sha256": _sha256_bytes(native_text.encode("utf-8")),
                "usable": usable,
                "minimum_non_whitespace": config["native_text_min_non_whitespace"],
            }
            if usable:
                if native_pdf_converter is None:
                    native_pdf_converter = DocumentConverter(
                        allowed_formats=[InputFormat.PDF],
                        format_options={
                            InputFormat.PDF: PdfFormatOption(
                                pipeline_options=pdf_options(
                                    do_ocr=False,
                                    language=sample["language"],
                                )
                            )
                        },
                    )
                converter = native_pdf_converter
                branch = "programmatic-text-plus-heron-layout"
            else:
                language = sample["language"]
                if language not in ocr_pdf_converters:
                    ocr_pdf_converters[language] = DocumentConverter(
                        allowed_formats=[InputFormat.PDF],
                        format_options={
                            InputFormat.PDF: PdfFormatOption(
                                pipeline_options=pdf_options(
                                    do_ocr=True,
                                    language=language,
                                )
                            )
                        },
                    )
                converter = ocr_pdf_converters[language]
                branch = "tesseract-full-page-fallback-plus-heron-layout"
            result = converter.convert(
                sample["source_path"],
                page_range=(sample["page"], sample["page"]),
                max_file_size=sample["source_path"].stat().st_size,
            )
            source_unit = {"page": sample["page"]}
        else:
            try:
                with zipfile.ZipFile(sample["source_path"]) as archive:
                    raw_member = archive.read(sample["member_path"])
            except (OSError, KeyError, zipfile.BadZipFile) as exc:
                raise DoclingStructureBridgeError(
                    f"cannot read EPUB member for {sample_id}: {exc}"
                ) from exc
            if _sha256_bytes(raw_member) != sample["member_sha256"]:
                raise DoclingStructureBridgeError(
                    f"EPUB member fixity drift: {sample_id}"
                )
            result = html_converter.convert(
                DocumentStream(
                    name=f"{sample_id}.html",
                    stream=BytesIO(raw_member),
                )
            )
            branch = "exact-epub-xhtml-simple-pipeline"
            source_unit = {
                "container_member": sample["member_path"],
                "member_sha256": sample["member_sha256"],
            }

        status = getattr(result.status, "value", str(result.status))
        errors = _conversion_errors(result)
        if result.status not in {
            ConversionStatus.SUCCESS,
            ConversionStatus.PARTIAL_SUCCESS,
        }:
            raise DoclingStructureBridgeError(
                f"Docling conversion failed for {sample_id}: {status}: {errors}"
            )
        document = result.document
        docling_json = document.export_to_dict(
            coord_precision=6,
            confid_precision=6,
        )
        markdown = document.export_to_markdown(
            traverse_pictures=True,
            page_break_placeholder="<!-- source-unit-page-break -->",
        )
        blocks = _normalized_blocks(document)
        document_path = sample_root / "docling-document.json"
        markdown_path = sample_root / "document.md"
        blocks_path = sample_root / "ordered-blocks.json"
        engine_path = sample_root / "engine.json"
        _write_json(document_path, docling_json)
        _atomic_text(markdown_path, markdown)
        _write_json(
            blocks_path,
            {
                "schema_version": "tos_docling_ordered_blocks_v1",
                "sample_id": sample_id,
                "blocks": blocks,
                "block_count": len(blocks),
                "authority_boundary": "Docling-emitted hierarchy and order only; not accepted structure",
            },
        )
        _write_json(
            engine_path,
            {
                "schema_version": "tos_docling_structure_engine_sample_v1",
                "sample_id": sample_id,
                "source_kind": sample["source_kind"],
                "source_unit": source_unit,
                "branch": branch,
                "conversion_status": status,
                "conversion_errors": errors,
                "native_text_probe": native_probe,
                "block_count": len(blocks),
                "nonempty_text_block_count": sum(
                    isinstance(row["text"], str) and bool(row["text"].strip())
                    for row in blocks
                ),
                "elapsed_seconds": time.perf_counter() - sample_started,
                "configuration": config,
                "authority_boundary": "mechanical diagnostic only; not a quality verdict",
            },
        )
        progress = {
            "completed_at_utc": _utc_now(),
            "sample_id": sample_id,
            "branch": branch,
            "conversion_status": status,
            "block_count": len(blocks),
            "elapsed_seconds": time.perf_counter() - sample_started,
            "document_sha256": _sha256_file(document_path),
            "markdown_sha256": _sha256_file(markdown_path),
            "blocks_sha256": _sha256_file(blocks_path),
            "engine_sha256": _sha256_file(engine_path),
        }
        _append_progress(progress_path, progress)
        completed.append(progress)

    summary = {
        "schema_version": "tos_docling_structure_bridge_summary_v1",
        "started_at_utc": started_at,
        "finished_at_utc": _utc_now(),
        "request_ref": request_path.as_posix(),
        "request_sha256": _sha256_file(request_path),
        "sample_count": len(completed),
        "sample_ids": [row["sample_id"] for row in completed],
        "branch_counts": {
            branch: sum(row["branch"] == branch for row in completed)
            for branch in sorted({row["branch"] for row in completed})
        },
        "partial_success_count": sum(
            row["conversion_status"] == "partial_success" for row in completed
        ),
        "wall_seconds": time.perf_counter() - wall_started,
        "configuration": config,
        "authority_boundary": "runtime structure mechanics only; no content or quality acceptance",
    }
    _write_json(summary_path, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = execute_bridge(args.request)
    except DoclingStructureBridgeError as exc:
        print(f"[error] {exc}", file=os.sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
