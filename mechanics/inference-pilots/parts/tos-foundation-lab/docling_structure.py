#!/usr/bin/env python3
"""Execute frozen Structure B through the exact local Docling runtime."""

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

from runtime_manifest import RuntimeManifestError, verify_runtime_manifest


EXPECTED_RUNTIME_ID = "docling-2.115.0-heron-8f39ad3-cpu"
EXPECTED_SOFTWARE_SHA256 = {
    "docling": "1a3d9bdf2f82610e97085a1a1b53cf259d1bd7aff97651ff2decc3b2b105123c",
    "docling-layout-heron": "00333a43451945aaf89db8ca9c0a17e75d1537c17db60fdb91aa95f4c7929e0c",
}
TESSERACT_LANGUAGE_BY_BCP47 = {
    "de": "deu",
    "ru": "rus",
}
BRIDGE_NAME = "docling_structure_bridge.py"
BRIDGE_REQUEST_SCHEMA = "tos_docling_structure_bridge_request_v1"
CONFIGURATION = {
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


class DoclingStructureError(RuntimeError):
    """Raised when Structure B cannot preserve its frozen experiment law."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DoclingStructureError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DoclingStructureError(f"{path} must contain a JSON object")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DoclingStructureError(f"cannot read {path}: {exc}") from exc
    for number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DoclingStructureError(f"cannot read {path}:{number}: {exc}") from exc
        if not isinstance(record, dict):
            raise DoclingStructureError(f"{path}:{number} must contain an object")
        records.append(record)
    return records


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise DoclingStructureError(f"artifact escapes run root: {path}") from exc


def _verify_prepared_run(
    run_root: Path, runtime_manifest_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = _load_json(run_root / "run.receipt.json")
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if (
        receipt.get("experiment_id") != "tos-structure-recovery-v1"
        or receipt.get("variant") != "B"
        or receipt.get("status") != "prepared"
        or experiment.get("family") != "structure"
        or preflight.get("decision") != "ready"
    ):
        raise DoclingStructureError("Structure B requires one ready prepared run")
    admission = preflight.get("runtime_admission")
    if (
        not isinstance(admission, dict)
        or admission.get("verified") is not True
        or Path(str(admission.get("manifest_ref"))).resolve()
        != runtime_manifest_path.resolve()
        or admission.get("manifest_sha256") != _sha256_file(runtime_manifest_path)
    ):
        raise DoclingStructureError("runtime differs from the preflighted admission")
    return receipt, experiment


def _verify_runtime(
    runtime_manifest_path: Path,
) -> tuple[dict[str, Any], Path, Path]:
    try:
        runtime = verify_runtime_manifest(
            runtime_manifest_path,
            experiment_id="tos-structure-recovery-v1",
            variant="B",
            required_commands=["docling", "python", "tesseract"],
        )
    except RuntimeManifestError as exc:
        raise DoclingStructureError(str(exc)) from exc
    if runtime.get("runtime_id") != EXPECTED_RUNTIME_ID:
        raise DoclingStructureError("unexpected Docling runtime identity")
    software = {
        str(row.get("name")): row
        for row in runtime.get("software", [])
        if isinstance(row, dict)
    }
    for name, digest in EXPECTED_SOFTWARE_SHA256.items():
        if software.get(name, {}).get("source_sha256") != digest:
            raise DoclingStructureError(f"runtime software identity drift: {name}")
    runtime_root = Path(runtime["runtime_root"])
    model_dir = runtime_root / "models/docling-project--docling-layout-heron"
    tessdata_dir = runtime_root / "vendor/tesseract/usr/share/tesseract/tessdata"
    if (
        _sha256_file(model_dir / "model.safetensors")
        != EXPECTED_SOFTWARE_SHA256["docling-layout-heron"]
        or not (tessdata_dir / "deu.traineddata").is_file()
        or not (tessdata_dir / "rus.traineddata").is_file()
    ):
        raise DoclingStructureError("runtime model or Tesseract data closure drift")
    return runtime, model_dir, tessdata_dir


def _manifest_index(tree_repo_root: Path) -> dict[str, tuple[dict[str, Any], Path]]:
    manifests: dict[str, tuple[dict[str, Any], Path]] = {}
    for path in sorted((tree_repo_root / "ToS/source-witnesses").rglob("item.manifest.json")):
        payload = _load_json(path)
        item_id = payload.get("item_id")
        if isinstance(item_id, str):
            if item_id in manifests:
                raise DoclingStructureError(f"duplicate item manifest: {item_id}")
            manifests[item_id] = (payload, path)
    return manifests


def _corpus_record_index(
    tree_repo_root: Path,
    *,
    filename: str,
    record_type: str,
) -> dict[str, tuple[dict[str, Any], Path]]:
    records: dict[str, tuple[dict[str, Any], Path]] = {}
    for path in sorted((tree_repo_root / "ToS/source-witnesses").rglob(filename)):
        payload = _load_json(path)
        record_id = payload.get("record_id")
        if payload.get("record_type") != record_type or not isinstance(record_id, str):
            raise DoclingStructureError(
                f"{path} is not one typed {record_type} corpus record"
            )
        if record_id in records:
            raise DoclingStructureError(f"duplicate {record_type} record: {record_id}")
        records[record_id] = (payload, path)
    return records


def _ocr_language_for_group(
    group: dict[str, Any],
    manifests: dict[str, tuple[dict[str, Any], Path]],
    editions: dict[str, tuple[dict[str, Any], Path]],
    expressions: dict[str, tuple[dict[str, Any], Path]],
    tree_repo_root: Path,
) -> tuple[str, dict[str, Any]]:
    item_ref = str(group.get("item_ref"))
    manifest_target = manifests.get(item_ref)
    if manifest_target is None:
        raise DoclingStructureError(f"unresolved item for OCR language: {item_ref}")
    manifest, manifest_path = manifest_target
    embodiment_ref = manifest.get("embodiment_ref")
    if not isinstance(embodiment_ref, str):
        raise DoclingStructureError(f"item has no typed embodiment: {item_ref}")
    edition_target = editions.get(embodiment_ref)
    if edition_target is None:
        raise DoclingStructureError(
            f"item embodiment is not a tracked edition: {embodiment_ref}"
        )
    edition, edition_path = edition_target
    expression_refs = edition.get("embodies_expression_refs")
    if (
        not isinstance(expression_refs, list)
        or not expression_refs
        or any(not isinstance(ref, str) for ref in expression_refs)
    ):
        raise DoclingStructureError(
            f"edition has no typed expression closure: {embodiment_ref}"
        )
    expression_records: list[tuple[str, dict[str, Any], Path]] = []
    for expression_ref in expression_refs:
        expression_target = expressions.get(expression_ref)
        if expression_target is None:
            raise DoclingStructureError(
                f"edition expression is unresolved: {expression_ref}"
            )
        expression, expression_path = expression_target
        expression_records.append((expression_ref, expression, expression_path))
    languages = {
        str(expression.get("language"))
        for _, expression, _ in expression_records
        if isinstance(expression.get("language"), str)
    }
    if len(languages) != 1 or len(expression_records) != len(expression_refs):
        raise DoclingStructureError(
            f"edition OCR language is absent or ambiguous: {embodiment_ref}"
        )
    language = next(iter(languages))
    tesseract_language = TESSERACT_LANGUAGE_BY_BCP47.get(language)
    if tesseract_language is None:
        raise DoclingStructureError(
            f"unsupported tracked OCR language {language}: {embodiment_ref}"
        )
    evidence = {
        "resolution_method": (
            "item-manifest-embodiment-to-edition-expression-language"
        ),
        "item_ref": item_ref,
        "item_manifest_ref": manifest_path.relative_to(tree_repo_root).as_posix(),
        "embodiment_ref": embodiment_ref,
        "edition_record_ref": edition_path.relative_to(tree_repo_root).as_posix(),
        "expression_refs": expression_refs,
        "expression_record_refs": [
            path.relative_to(tree_repo_root).as_posix()
            for _, _, path in expression_records
        ],
        "bcp47_language": language,
        "tesseract_language": tesseract_language,
    }
    return tesseract_language, evidence


def _payload_for_group(
    group: dict[str, Any],
    manifests: dict[str, tuple[dict[str, Any], Path]],
) -> Path:
    target = manifests.get(str(group.get("item_ref")))
    if target is None:
        raise DoclingStructureError(f"unresolved item: {group.get('item_ref')}")
    manifest, manifest_path = target
    for payload in manifest.get("payload_files", []):
        if isinstance(payload, dict) and payload.get("file_id") == group.get("file_ref"):
            source = manifest_path.parent / str(payload.get("relative_path"))
            if (
                not source.is_file()
                or _sha256_file(source) != payload.get("sha256")
                or payload.get("sha256") != group.get("file_sha256")
            ):
                raise DoclingStructureError(
                    f"source payload fixity drift: {group.get('file_ref')}"
                )
            return source.resolve()
    raise DoclingStructureError(f"unresolved file: {group.get('file_ref')}")


def _selected_samples(
    sample_plan: dict[str, Any],
    selected_sample_ids: list[str] | None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows = [
        (group, sample)
        for group in sample_plan.get("source_groups", [])
        if isinstance(group, dict)
        for sample in group.get("samples", [])
        if isinstance(sample, dict)
    ]
    if selected_sample_ids is None:
        return rows
    if len(selected_sample_ids) != len(set(selected_sample_ids)):
        raise DoclingStructureError("diagnostic sample IDs must be unique")
    available = {str(sample["sample_id"]) for _, sample in rows}
    missing = sorted(set(selected_sample_ids) - available)
    if missing:
        raise DoclingStructureError("sample plan omits requested samples: " + ", ".join(missing))
    selected = set(selected_sample_ids)
    return [
        (group, sample)
        for group, sample in rows
        if str(sample["sample_id"]) in selected
    ]


def _execute_docling_structure(
    run_root: Path,
    tree_repo_root: Path,
    sample_plan_path: Path,
    runtime_manifest_path: Path,
    *,
    invocation: list[str],
    selected_sample_ids: list[str] | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    tree_repo_root = tree_repo_root.resolve()
    sample_plan_path = sample_plan_path.resolve()
    runtime_manifest_path = runtime_manifest_path.resolve()
    receipt_path = run_root / "run.receipt.json"
    receipt, experiment = _verify_prepared_run(run_root, runtime_manifest_path)
    runtime, model_dir, tessdata_dir = _verify_runtime(runtime_manifest_path)
    sample_plan = _load_json(sample_plan_path)
    if (
        sample_plan.get("status") != "frozen"
        or sample_plan.get("frozen_before_variant_outputs") is not True
    ):
        raise DoclingStructureError("sample plan is not output-blind and frozen")
    anchors = {
        str(row["anchor_id"]): row
        for row in _load_jsonl(sample_plan_path.parent / "anchors.jsonl")
        if isinstance(row.get("anchor_id"), str)
    }
    manifests = _manifest_index(tree_repo_root)
    editions = _corpus_record_index(
        tree_repo_root,
        filename="edition.json",
        record_type="edition",
    )
    expressions = _corpus_record_index(
        tree_repo_root,
        filename="expression.json",
        record_type="expression",
    )
    active = _selected_samples(sample_plan, selected_sample_ids)
    source_paths: dict[str, Path] = {}
    request_samples: list[dict[str, Any]] = []
    anchor_map: list[dict[str, Any]] = []
    source_map: dict[str, dict[str, Any]] = {}
    for group, sample in active:
        file_ref = str(group["file_ref"])
        source = source_paths.setdefault(file_ref, _payload_for_group(group, manifests))
        language, language_evidence = _ocr_language_for_group(
            group,
            manifests,
            editions,
            expressions,
            tree_repo_root,
        )
        source_map[file_ref] = {
            "item_ref": group["item_ref"],
            "file_ref": file_ref,
            "file_sha256": group["file_sha256"],
            "local_path": source.as_posix(),
            "access": "read-only immutable source payload",
            "ocr_language_resolution": language_evidence,
        }
        sample_id = str(sample["sample_id"])
        anchor = anchors.get(str(sample.get("anchor_ref")))
        if anchor is None:
            raise DoclingStructureError(f"unresolved anchor: {sample_id}")
        selectors = anchor.get("selectors", [])
        page = next(
            (
                row
                for row in selectors
                if isinstance(row, dict) and row.get("type") == "page_region"
            ),
            None,
        )
        member = next(
            (
                row
                for row in selectors
                if isinstance(row, dict) and row.get("type") == "container_member"
            ),
            None,
        )
        base = {
            "sample_id": sample_id,
            "source_path": source.as_posix(),
            "source_sha256": group["file_sha256"],
        }
        if isinstance(page, dict):
            request_samples.append(
                {
                    **base,
                    "source_kind": "pdf-page",
                    "page": int(page["page"]),
                    "language": language,
                }
            )
            unit = {"page": int(page["page"])}
        elif isinstance(member, dict):
            request_samples.append(
                {
                    **base,
                    "source_kind": "epub-xhtml",
                    "member_path": str(member["member_path"]),
                    "member_sha256": str(member["member_sha256"]),
                }
            )
            unit = {"container_member": str(member["member_path"])}
        else:
            raise DoclingStructureError(f"unsupported source selector: {sample_id}")
        anchor_map.append(
            {
                "sample_id": sample_id,
                "source_anchor_ref": sample["anchor_ref"],
                "source_unit": unit,
                "ordered_blocks_ref": f"raw-output/{sample_id}/ordered-blocks.json",
                "resolution_status": "mechanically-resolved-unreviewed",
            }
        )

    raw_root = run_root / "raw-output"
    request_path = run_root / "receipts/docling-structure-request.json"
    request = {
        "schema_version": BRIDGE_REQUEST_SCHEMA,
        "experiment_id": "tos-structure-recovery-v1",
        "variant": "B",
        "output_root": raw_root.as_posix(),
        "model_dir": model_dir.as_posix(),
        "tesseract_command": runtime["commands"]["tesseract"],
        "tessdata_dir": tessdata_dir.as_posix(),
        "configuration": CONFIGURATION,
        "samples": request_samples,
    }
    _write_json(request_path, request)
    source_map_path = run_root / "inputs/source-map.json"
    _write_json(
        source_map_path,
        {
            "sample_plan_ref": sample_plan_path.as_posix(),
            "sample_plan_sha256": _sha256_file(sample_plan_path),
            "sources": list(source_map.values()),
            "visibility": "private-runtime-only",
        },
    )
    anchor_map_path = raw_root / "anchor-map.jsonl"
    _write_jsonl(anchor_map_path, anchor_map)
    bridge = Path(__file__).resolve().with_name(BRIDGE_NAME)
    invocation_path = run_root / "receipts/docling-structure-invocation.json"
    invocation_receipt = {
        "captured_at_utc": _utc_now(),
        "argv": invocation,
        "runner_sha256": _sha256_file(Path(__file__)),
        "bridge_sha256": _sha256_file(bridge),
        "bridge_request_sha256": _sha256_file(request_path),
        "sample_plan_ref": sample_plan_path.as_posix(),
        "sample_plan_sha256": _sha256_file(sample_plan_path),
        "runtime_manifest_ref": runtime_manifest_path.as_posix(),
        "runtime_manifest_sha256": _sha256_file(runtime_manifest_path),
        "runtime_artifact_set_sha256": runtime["artifact_set_sha256"],
        "execution_scope": (
            "frozen-thirty-six-unit-set"
            if selected_sample_ids is None
            else "diagnostic-frozen-subset"
        ),
        "selected_sample_ids": [row["sample_id"] for row in request_samples],
        "quality_metrics_allowed": False,
        "rights_posture": "restricted-source-derived-output-private-runtime-only",
    }
    _write_json(invocation_path, invocation_receipt)
    variant = next(row for row in experiment["variants"] if row["label"] == "B")
    receipt["status"] = "running"
    receipt["started_at_utc"] = invocation_receipt["captured_at_utc"]
    receipt["method_revision"] = {
        "implementation": variant["implementation"],
        "version": "Docling 2.115.0; Heron pinned revision; CPU-only",
        "runtime": runtime["runtime_id"],
        "model": variant["model"],
        "artifact_digest": runtime["artifact_set_sha256"],
    }
    receipt["invocation_ref"] = _relative(run_root, invocation_path)
    receipt["artifact_refs"] = [
        _relative(run_root, request_path),
        _relative(run_root, source_map_path),
        _relative(run_root, anchor_map_path),
    ]
    _write_json(receipt_path, receipt)

    environment = os.environ.copy()
    environment.update({str(key): str(value) for key, value in runtime["environment"].items()})
    environment.update(
        {
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "OMP_NUM_THREADS": str(CONFIGURATION["threads"]),
            "MKL_NUM_THREADS": str(CONFIGURATION["threads"]),
            "OPENBLAS_NUM_THREADS": str(CONFIGURATION["threads"]),
            "NUMEXPR_NUM_THREADS": str(CONFIGURATION["threads"]),
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
            text=True,
            env=environment,
            timeout=int(variant.get("timeout_seconds", 10800)),
        )
        child_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        stderr_path = run_root / "receipts/docling-structure.stderr.txt"
        stdout_path = run_root / "receipts/docling-structure.stdout.txt"
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        if completed.returncode:
            raise DoclingStructureError(
                f"Docling bridge failed ({completed.returncode}): {completed.stderr[-1600:]}"
            )
        summary_path = raw_root / "docling-structure-bridge-summary.json"
        summary = _load_json(summary_path)
        expected_ids = [row["sample_id"] for row in request_samples]
        if (
            summary.get("sample_ids") != expected_ids
            or summary.get("sample_count") != len(expected_ids)
            or summary.get("configuration") != CONFIGURATION
        ):
            raise DoclingStructureError("Docling bridge summary closure drift")
        wall_seconds = time.perf_counter() - started
        artifact_bytes = sum(
            path.stat().st_size
            for path in run_root.rglob("*")
            if path.is_file() and path != receipt_path
        )
        metrics = {
            "schema_version": "tos_docling_structure_metrics_v1",
            "experiment_id": "tos-structure-recovery-v1",
            "variant": "B",
            "execution_scope": invocation_receipt["execution_scope"],
            "sample_count": len(expected_ids),
            "source_count": len(source_map),
            "wall_seconds": wall_seconds,
            "units_per_minute": len(expected_ids) * 60 / wall_seconds if wall_seconds else None,
            "child_user_cpu_seconds": child_after.ru_utime - child_before.ru_utime,
            "child_system_cpu_seconds": child_after.ru_stime - child_before.ru_stime,
            "child_peak_rss_bytes": child_after.ru_maxrss * 1024,
            "artifact_bytes": artifact_bytes,
            "branch_counts": summary["branch_counts"],
            "partial_success_count": summary["partial_success_count"],
            "quality": {
                "status": "not-computable",
                "reason": "double-source-visible human structural gold is not complete",
            },
            "human_cost": {
                "status": "not-measured",
                "reason": "no real human structural correction pass has occurred",
            },
            "traceability": {
                "mechanical_anchor_resolution": (
                    len(anchor_map) / len(expected_ids) if expected_ids else None
                ),
                "content_acceptance": "not-reviewed",
            },
            "authority_boundary": "speed and machine-cost observations only; no content-quality verdict",
        }
        metrics_path = run_root / "metrics/docling-structure-summary.json"
        _write_json(metrics_path, metrics)
        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = expected_ids
        receipt["artifact_refs"] = sorted(
            set(
                receipt["artifact_refs"]
                + [
                    _relative(run_root, path)
                    for path in run_root.rglob("*")
                    if path.is_file()
                    and path != receipt_path
                    and "metrics" not in path.relative_to(run_root).parts
                ]
            )
        )
        receipt["metric_refs"] = [_relative(run_root, metrics_path)]
        receipt["manual_review_refs"] = []
        receipt["errors"] = []
        _write_json(receipt_path, receipt)
        return metrics
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)]
        receipt["artifact_refs"] = sorted(
            set(
                receipt.get("artifact_refs", [])
                + [
                    _relative(run_root, path)
                    for path in run_root.rglob("*")
                    if path.is_file() and path != receipt_path
                ]
            )
        )
        _write_json(receipt_path, receipt)
        if isinstance(exc, DoclingStructureError):
            raise
        raise DoclingStructureError(str(exc)) from exc


def execute_docling_structure(
    run_root: Path,
    tree_repo_root: Path,
    sample_plan_path: Path,
    runtime_manifest_path: Path,
    *,
    invocation: list[str],
    selected_sample_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Execute Structure B and never leave a preparation failure marked prepared."""
    run_root = run_root.resolve()
    receipt_path = run_root / "run.receipt.json"
    try:
        return _execute_docling_structure(
            run_root,
            tree_repo_root,
            sample_plan_path,
            runtime_manifest_path,
            invocation=invocation,
            selected_sample_ids=selected_sample_ids,
        )
    except Exception as exc:
        try:
            receipt = _load_json(receipt_path)
            if receipt.get("status") in {"prepared", "running"}:
                receipt["status"] = "failed"
                receipt["finished_at_utc"] = _utc_now()
                receipt["retention_decision"] = "retain"
                receipt["errors"] = [str(exc)]
                receipt["artifact_refs"] = sorted(
                    set(
                        receipt.get("artifact_refs", [])
                        + [
                            _relative(run_root, path)
                            for path in run_root.rglob("*")
                            if path.is_file() and path != receipt_path
                        ]
                    )
                )
                _write_json(receipt_path, receipt)
        except Exception as receipt_exc:
            raise DoclingStructureError(
                f"{exc}; additionally failed to close run receipt: {receipt_exc}"
            ) from exc
        if isinstance(exc, DoclingStructureError):
            raise
        raise DoclingStructureError(str(exc)) from exc
