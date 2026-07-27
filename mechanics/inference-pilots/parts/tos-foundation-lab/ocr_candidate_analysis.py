#!/usr/bin/env python3
"""Build one private post-reveal analysis from a frozen OCR candidate pass."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from human_review_workbench import (
    DEFAULT_HUMAN_REVIEW_ROOT,
    ReviewContext,
)


ANALYSIS_SCHEMA_VERSION = "tos_ocr_candidate_post_reveal_analysis_v1"
ANALYSIS_RECEIPT_SCHEMA_VERSION = (
    "tos_ocr_candidate_post_reveal_analysis_receipt_v1"
)
ANALYSIS_DIR = Path("post-reveal") / "ocr-candidate-analysis-v1"
ANALYSIS_FILENAME = "analysis.json"
REPORT_FILENAME = "REPORT.md"
RECEIPT_FILENAME = "analysis.receipt.json"
VARIANTS = ("A", "B", "C")
DECISIONS = (
    "accept",
    "accept-with-limits",
    "corrected",
    "reject",
    "uncertain",
    "language-not-assessed",
)
AUTHORITY_BOUNDARY = (
    "private descriptive post-reveal analysis of one source-visible human "
    "candidate-review pass; it does not create source truth, gold, accepted "
    "text, a general method ranking, translation, semantic promotion, or canon"
)


class OcrCandidateAnalysisError(RuntimeError):
    """Raised when post-reveal analysis cannot preserve evidence boundaries."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OcrCandidateAnalysisError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise OcrCandidateAnalysisError(f"JSON object required: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now().astimezone().isoformat()


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def _distribution(values: list[object]) -> dict[str, int]:
    counter = Counter(str(value) for value in values if value is not None)
    return dict(sorted(counter.items()))


def _minute_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "total": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "minimum": 0.0,
            "maximum": 0.0,
        }
    return {
        "total": _round(sum(values), 1),
        "mean": _round(sum(values) / len(values), 2),
        "median": _round(median(values), 2),
        "minimum": _round(min(values), 1),
        "maximum": _round(max(values), 1),
    }


def _ensure_regular_fixed_file(
    path_value: object,
    digest_value: object,
    *,
    label: str,
) -> Path:
    if not isinstance(path_value, str) or not Path(path_value).is_absolute():
        raise OcrCandidateAnalysisError(f"{label} must be an absolute path")
    path = Path(path_value)
    if path.is_symlink() or not path.is_file():
        raise OcrCandidateAnalysisError(f"{label} is missing or is a symlink")
    if not isinstance(digest_value, str) or _sha256_file(path) != digest_value:
        raise OcrCandidateAnalysisError(f"{label} digest drifted")
    return path


def _runtime_metric_records(
    run_root: Path, receipt: dict[str, Any]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    refs = receipt.get("metric_refs", [])
    if not isinstance(refs, list):
        return records
    for ref in refs:
        if not isinstance(ref, str) or not ref.endswith(".json"):
            continue
        path = (run_root / ref).resolve()
        try:
            path.relative_to(run_root)
        except ValueError as exc:
            raise OcrCandidateAnalysisError(
                f"runtime metric escaped run root: {ref}"
            ) from exc
        if path.is_symlink() or not path.is_file():
            continue
        payload = _load_json(path)
        retained_keys = (
            "schema_version",
            "sample_count",
            "source_count",
            "wall_seconds",
            "bridge_seconds",
            "prediction_seconds",
            "pipeline_initialization_seconds",
            "pages_per_minute",
            "child_peak_rss_bytes",
            "artifact_bytes",
            "empty_text_count",
            "warning_count",
            "authority_boundary",
        )
        record = {
            key: copy.deepcopy(payload[key])
            for key in retained_keys
            if key in payload
        }
        record.update(
            {
                "ref": ref,
                "sha256": _sha256_file(path),
            }
        )
        records.append(record)
    return records


def _systemd_resource_summary(
    run_root: Path, receipt: dict[str, Any]
) -> dict[str, Any] | None:
    refs = receipt.get("metric_refs", [])
    if not isinstance(refs, list):
        return None
    for ref in refs:
        if (
            not isinstance(ref, str)
            or not ref.endswith("systemd-final-resource-summary.txt")
        ):
            continue
        path = (run_root / ref).resolve()
        try:
            path.relative_to(run_root)
        except ValueError as exc:
            raise OcrCandidateAnalysisError(
                f"systemd resource summary escaped run root: {ref}"
            ) from exc
        if path.is_symlink() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        match = re.search(
            r"Consumed (?P<cpu>.+?) CPU time over "
            r"(?P<wall>.+?) wall clock time, "
            r"(?P<memory>\S+) memory peak, "
            r"(?P<swap>\S+) memory swap peak\.",
            text,
        )
        if match is None:
            return {
                "ref": ref,
                "sha256": _sha256_file(path),
                "status": "present-unparsed",
            }
        return {
            "ref": ref,
            "sha256": _sha256_file(path),
            "status": "parsed-owner-summary",
            "cpu_time": match.group("cpu"),
            "wall_clock_time": match.group("wall"),
            "memory_peak": match.group("memory"),
            "memory_swap_peak": match.group("swap"),
            "interpretation_boundary": (
                "owner-recorded systemd resource evidence; it does not "
                "establish OCR quality"
            ),
        }
    return None


def _validated_method_record(
    entry: dict[str, Any],
) -> dict[str, Any]:
    variant = entry.get("variant")
    if variant not in VARIANTS:
        raise OcrCandidateAnalysisError(f"unsupported revealed variant: {variant}")
    receipt_path = _ensure_regular_fixed_file(
        entry.get("run_receipt_ref"),
        entry.get("run_receipt_sha256"),
        label=f"variant {variant} run receipt",
    )
    receipt = _load_json(receipt_path)
    expected = {
        "run_id": entry.get("run_id"),
        "variant": variant,
        "status": entry.get("run_status"),
        "method_revision": entry.get("method_revision"),
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise OcrCandidateAnalysisError(
                f"variant {variant} run receipt drifted at {key}"
            )
    started = _parse_datetime(receipt.get("started_at_utc"))
    finished = _parse_datetime(receipt.get("finished_at_utc"))
    elapsed = None
    if started is not None and finished is not None:
        elapsed = _round((finished - started).total_seconds(), 3)
    return {
        "variant": variant,
        "run_id": entry["run_id"],
        "run_status": entry["run_status"],
        "run_receipt_ref": receipt_path.as_posix(),
        "run_receipt_sha256": entry["run_receipt_sha256"],
        "method_revision": copy.deepcopy(entry["method_revision"]),
        "started_at_utc": receipt.get("started_at_utc"),
        "finished_at_utc": receipt.get("finished_at_utc"),
        "receipt_elapsed_seconds": elapsed,
        "sample_count_declared": (
            len(receipt["sample_ids"])
            if isinstance(receipt.get("sample_ids"), list)
            else None
        ),
        "runtime_metrics": _runtime_metric_records(
            receipt_path.parent, receipt
        ),
        "systemd_resource_summary": _systemd_resource_summary(
            receipt_path.parent, receipt
        ),
        "errors": copy.deepcopy(receipt.get("errors", [])),
        "retention_decision": receipt.get("retention_decision"),
    }


def _joined_rows(
    context: ReviewContext,
    draft: dict[str, Any],
    blind_map: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = draft.get("rows")
    entries = blind_map.get("entries")
    units = context.manifest.get("units")
    if not isinstance(rows, list) or not isinstance(entries, list):
        raise OcrCandidateAnalysisError("draft or blind map rows are invalid")
    if not isinstance(units, list):
        raise OcrCandidateAnalysisError("candidate manifest units are invalid")
    expected_ids = [str(unit["review_unit_id"]) for unit in units]
    if [row.get("review_unit_id") for row in rows] != expected_ids:
        raise OcrCandidateAnalysisError("frozen draft order drifted from manifest")
    if [entry.get("review_unit_id") for entry in entries] != expected_ids:
        raise OcrCandidateAnalysisError("blind-map order drifted from manifest")

    joined: list[dict[str, Any]] = []
    methods: dict[str, dict[str, Any]] = {}
    variants_by_source: dict[str, set[str]] = defaultdict(set)
    for unit, row, entry in zip(units, rows, entries, strict=True):
        identity = {
            "review_unit_id": unit["review_unit_id"],
            "source_sample_id": unit["source_sample_id"],
            "visual_sample_id": unit["visual_sample_id"],
            "candidate_label": unit["candidate_label"],
            "candidate_sha256": unit["candidate_sha256"],
        }
        for key, value in identity.items():
            if row.get(key) != value or entry.get(key) != value:
                raise OcrCandidateAnalysisError(
                    f"{unit['review_unit_id']}: identity drifted at {key}"
                )
        candidate_source = _ensure_regular_fixed_file(
            entry.get("candidate_source_ref"),
            entry.get("candidate_source_sha256"),
            label=f"{unit['review_unit_id']} candidate source",
        )
        if entry["candidate_source_sha256"] != unit["candidate_sha256"]:
            raise OcrCandidateAnalysisError(
                f"{unit['review_unit_id']}: candidate source digest disagrees"
            )
        variant = str(entry.get("variant"))
        variants_by_source[str(unit["source_sample_id"])].add(variant)
        method = _validated_method_record(entry)
        previous = methods.get(variant)
        if previous is None:
            methods[variant] = method
        elif previous != method:
            raise OcrCandidateAnalysisError(
                f"variant {variant} maps to inconsistent run evidence"
            )
        joined.append(
            {
                "review_unit_id": unit["review_unit_id"],
                "source_sample_id": unit["source_sample_id"],
                "visual_sample_id": unit["visual_sample_id"],
                "source_anchor_ref": unit["source_anchor_ref"],
                "variant": variant,
                "displayed_label": unit["candidate_label"],
                "display_position": unit["candidate_position"],
                "candidate_sha256": unit["candidate_sha256"],
                "candidate_source_ref": candidate_source.as_posix(),
                "language": row.get("language"),
                "language_review_scope": row.get("language_review_scope"),
                "page_and_region_resolved": row.get(
                    "page_and_region_resolved"
                ),
                "source_legibility": row.get("source_legibility"),
                "text_fidelity": row.get("text_fidelity"),
                "completeness": row.get("completeness"),
                "structure_and_order": row.get("structure_and_order"),
                "error_types": copy.deepcopy(row.get("error_types", [])),
                "decision": row.get("decision"),
                "corrected": row.get("decision") == "corrected",
                "has_note": bool(str(row.get("notes") or "").strip()),
                "elapsed_minutes": float(row.get("elapsed_minutes", 0)),
            }
        )
    for source_id, variants in variants_by_source.items():
        if variants != set(VARIANTS):
            raise OcrCandidateAnalysisError(
                f"{source_id}: revealed variants are not exactly A/B/C"
            )
    if set(methods) != set(VARIANTS):
        raise OcrCandidateAnalysisError("revealed method set is not exactly A/B/C")
    return joined, methods


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    minutes = [float(row["elapsed_minutes"]) for row in rows]
    errors = Counter(
        error
        for row in rows
        for error in row.get("error_types", [])
        if isinstance(error, str)
    )
    return {
        "unit_count": len(rows),
        "decisions": _distribution([row.get("decision") for row in rows]),
        "text_fidelity": _distribution(
            [row.get("text_fidelity") for row in rows]
        ),
        "completeness": _distribution(
            [row.get("completeness") for row in rows]
        ),
        "structure_and_order": _distribution(
            [row.get("structure_and_order") for row in rows]
        ),
        "error_types": dict(sorted(errors.items())),
        "display_positions": _distribution(
            [row.get("display_position") for row in rows]
        ),
        "displayed_labels": _distribution(
            [row.get("displayed_label") for row in rows]
        ),
        "language_review_scope": _distribution(
            [row.get("language_review_scope") for row in rows]
        ),
        "corrected_units": sum(bool(row.get("corrected")) for row in rows),
        "noted_units": sum(bool(row.get("has_note")) for row in rows),
        "active_minutes": _minute_summary(minutes),
    }


def _position_audit(joined: list[dict[str, Any]]) -> dict[str, Any]:
    by_position: dict[str, dict[str, Any]] = {}
    for position in (1, 2, 3):
        rows = [row for row in joined if row["display_position"] == position]
        by_position[str(position)] = {
            "unit_count": len(rows),
            "variants": _distribution([row["variant"] for row in rows]),
            "decisions": _distribution([row["decision"] for row in rows]),
            "text_fidelity": _distribution(
                [row["text_fidelity"] for row in rows]
            ),
            "active_minutes": _minute_summary(
                [float(row["elapsed_minutes"]) for row in rows]
            ),
        }
    per_variant = {
        variant: _distribution(
            [
                row["display_position"]
                for row in joined
                if row["variant"] == variant
            ]
        )
        for variant in VARIANTS
    }
    imbalanced = any(
        max(counts, default=0) - min(counts, default=0) > 1
        for counts in (
            [int(per_variant[variant].get(str(position), 0)) for position in (1, 2, 3)]
            for variant in VARIANTS
        )
    )
    return {
        "status": "imbalanced" if imbalanced else "near-balanced",
        "per_variant": per_variant,
        "by_position": by_position,
        "interpretation": (
            "human active-time and effort comparisons are position-confounded; "
            "do not rank correction cost from this pass"
            if imbalanced
            else "position counts differ by at most one for every variant"
        ),
    }


def _per_source(joined: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in joined:
        grouped[str(row["source_sample_id"])].append(row)
    result: list[dict[str, Any]] = []
    for source_id in sorted(grouped):
        rows = grouped[source_id]
        first = rows[0]
        result.append(
            {
                "source_sample_id": source_id,
                "visual_sample_id": first["visual_sample_id"],
                "source_anchor_ref": first["source_anchor_ref"],
                "assessments": [
                    {
                        key: copy.deepcopy(row[key])
                        for key in (
                            "review_unit_id",
                            "variant",
                            "displayed_label",
                            "display_position",
                            "decision",
                            "text_fidelity",
                            "completeness",
                            "structure_and_order",
                            "error_types",
                            "corrected",
                            "elapsed_minutes",
                        )
                    }
                    for row in sorted(rows, key=lambda item: item["variant"])
                ],
            }
        )
    return result


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _count(summary: dict[str, Any], family: str, key: str) -> int:
    return int(summary[family].get(key, 0))


def _method_name(method: dict[str, Any]) -> str:
    revision = method.get("method_revision", {})
    if not isinstance(revision, dict):
        return method["run_id"]
    return str(revision.get("implementation") or method["run_id"])


def _primary_runtime(method: dict[str, Any]) -> dict[str, Any]:
    metrics = method.get("runtime_metrics", [])
    if isinstance(metrics, list):
        for record in metrics:
            if isinstance(record, dict) and "wall_seconds" in record:
                return record
    return {}


def _render_report(analysis: dict[str, Any]) -> str:
    lines = [
        "# OCR A/B/C: post-reveal analysis",
        "",
        f"- Analysis ID: `{analysis['analysis_id']}`",
        f"- Packet: `{analysis['packet']['packet_id']}`",
        f"- Frozen human draft SHA-256: `{analysis['human_review']['draft_sha256']}`",
        f"- Reviewer: `{analysis['human_review']['reviewer_ref']}`",
        f"- Scope: {analysis['scope']['source_count']} source pages, "
        f"{analysis['scope']['unit_count']} candidate judgments, one human pass",
        "",
        "## Descriptive review results",
        "",
        "| Variant | Revealed method | Run status | Decisions "
        "(accept / limits / corrected / reject / uncertain) | "
        "Text fidelity (exact / minor / major / unusable) | "
        "Complete | Structure correct | Median active min | Positions 1/2/3 |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for variant in VARIANTS:
        summary = analysis["aggregates_by_variant"][variant]
        method = analysis["methods"][variant]
        decisions = " / ".join(
            str(_count(summary, "decisions", key))
            for key in (
                "accept",
                "accept-with-limits",
                "corrected",
                "reject",
                "uncertain",
            )
        )
        fidelity = " / ".join(
            str(_count(summary, "text_fidelity", key))
            for key in ("exact", "minor-errors", "major-errors", "unusable")
        )
        positions = " / ".join(
            str(summary["display_positions"].get(str(position), 0))
            for position in (1, 2, 3)
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    variant,
                    _markdown_cell(_method_name(method)),
                    _markdown_cell(method["run_status"]),
                    decisions,
                    fidelity,
                    str(_count(summary, "completeness", "complete")),
                    str(_count(summary, "structure_and_order", "correct")),
                    str(summary["active_minutes"]["median"]),
                    positions,
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "These are distributions, not a scalar winner score. "
            "`accept-with-limits` and `corrected` are intentionally not ordered.",
            "",
            "## Runtime evidence",
            "",
            "| Variant | Summary sample count | Wall seconds | Pages/min | "
            "Observed child peak RSS | Owner systemd resource summary | "
            "Artifact bytes | Evidence posture |",
            "| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |",
        ]
    )
    for variant in VARIANTS:
        method = analysis["methods"][variant]
        runtime = _primary_runtime(method)
        owner_resource = method.get("systemd_resource_summary")
        if (
            isinstance(owner_resource, dict)
            and owner_resource.get("status") == "parsed-owner-summary"
        ):
            owner_resource_cell = (
                f"wall {owner_resource['wall_clock_time']}; "
                f"memory {owner_resource['memory_peak']}; "
                f"swap {owner_resource['memory_swap_peak']}"
            )
        elif isinstance(owner_resource, dict):
            owner_resource_cell = str(owner_resource.get("status"))
        else:
            owner_resource_cell = "—"
        evidence_posture = (
            "summary metric"
            if runtime
            else "run receipt only; stopped/incomplete evidence remains explicit"
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    variant,
                    str(runtime.get("sample_count", "—")),
                    str(
                        runtime.get(
                            "wall_seconds",
                            method.get("receipt_elapsed_seconds") or "—",
                        )
                    ),
                    str(runtime.get("pages_per_minute", "—")),
                    str(runtime.get("child_peak_rss_bytes", "—")),
                    owner_resource_cell,
                    str(runtime.get("artifact_bytes", "—")),
                    evidence_posture,
                )
            )
            + " |"
        )

    position = analysis["display_position_audit"]
    lines.extend(
        [
            "",
            "## Display-position audit",
            "",
            f"Status: **{position['status']}**.",
            "",
            "| Display position | Variant counts | Total active min | "
            "Median active min |",
            "| ---: | --- | ---: | ---: |",
        ]
    )
    for value in ("1", "2", "3"):
        row = position["by_position"][value]
        variant_counts = ", ".join(
            f"{variant}: {row['variants'].get(variant, 0)}"
            for variant in VARIANTS
        )
        lines.append(
            f"| {value} | {variant_counts} | "
            f"{row['active_minutes']['total']} | "
            f"{row['active_minutes']['median']} |"
        )
    lines.extend(
        [
            "",
            position["interpretation"] + ".",
            "",
            "## Per-source matrix",
            "",
            "| Source sample | A | B | C |",
            "| --- | --- | --- | --- |",
        ]
    )
    for source in analysis["per_source"]:
        cells: dict[str, str] = {}
        for row in source["assessments"]:
            cells[row["variant"]] = (
                f"{row['decision']}; {row['text_fidelity']}; "
                f"{row['completeness']}; {row['structure_and_order']}"
            )
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(source["source_sample_id"]),
                    _markdown_cell(cells["A"]),
                    _markdown_cell(cells["B"]),
                    _markdown_cell(cells["C"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Interpretation boundaries",
            "",
            "- This is one reviewer, one pass, ten source pages, and thirty "
            "candidate judgments.",
            "- There is no accepted independent transcription in this analysis, "
            "so it does not produce CER/WER or source truth.",
            "- Browser active time is observational and, in this packet, "
            "position-confounded; it is not a correction-cost ranking.",
            "- Engine confidence values are not compared across implementations "
            "because their scales are not calibrated to each other.",
            "- A stopped run remains stopped. Good rows from that run do not "
            "erase its recorded failure mode.",
            "- Any promotion requires a separately reviewed Tree of Sophia "
            "handoff with source and provenance authority.",
            "",
            f"Authority boundary: {AUTHORITY_BOUNDARY}.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_private(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    os.chmod(path, 0o600)


def _write_control_projection(
    context: ReviewContext,
    analysis_record: dict[str, Any],
) -> bool:
    control_path = context.session_path
    control = _load_json(control_path)
    projected = copy.deepcopy(control)
    projected["post_reveal_analysis"] = copy.deepcopy(analysis_record)
    projected["next_action"] = (
        "Review the bounded post-reveal report and decide the next balanced "
        "experiment; do not promote a general OCR winner from this pass."
    )
    if projected == control:
        return False
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{control_path.name}.",
        suffix=".tmp",
        dir=control_path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(projected, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, control_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


def _verify_existing_analysis(
    context: ReviewContext,
    output_dir: Path,
    *,
    draft_sha256: str,
) -> dict[str, Any]:
    receipt_path = output_dir / RECEIPT_FILENAME
    analysis_path = output_dir / ANALYSIS_FILENAME
    report_path = output_dir / REPORT_FILENAME
    for path in (receipt_path, analysis_path, report_path):
        if path.is_symlink() or not path.is_file():
            raise OcrCandidateAnalysisError(
                "existing post-reveal analysis is partial or unsafe"
            )
    receipt = _load_json(receipt_path)
    if (
        receipt.get("schema_version") != ANALYSIS_RECEIPT_SCHEMA_VERSION
        or receipt.get("draft_sha256") != draft_sha256
        or receipt.get("analysis_sha256") != _sha256_file(analysis_path)
        or receipt.get("report_sha256") != _sha256_file(report_path)
        or receipt.get("authority_boundary") != AUTHORITY_BOUNDARY
    ):
        raise OcrCandidateAnalysisError("existing post-reveal analysis drifted")
    analysis = _load_json(analysis_path)
    if (
        analysis.get("schema_version") != ANALYSIS_SCHEMA_VERSION
        or analysis.get("authority_boundary") != AUTHORITY_BOUNDARY
    ):
        raise OcrCandidateAnalysisError("existing analysis identity drifted")
    relative = output_dir.relative_to(context.session_dir).as_posix()
    analysis_record = {
        "analysis_id": analysis["analysis_id"],
        "status": analysis["status"],
        "analysis_ref": f"{relative}/{ANALYSIS_FILENAME}",
        "analysis_sha256": receipt["analysis_sha256"],
        "report_ref": f"{relative}/{REPORT_FILENAME}",
        "report_sha256": receipt["report_sha256"],
        "receipt_ref": f"{relative}/{RECEIPT_FILENAME}",
    }
    projection_changed = _write_control_projection(context, analysis_record)
    return {
        "status": analysis["status"],
        "analysis_id": analysis["analysis_id"],
        "analysis_dir": output_dir.as_posix(),
        "changed": projection_changed,
        "reused_existing": True,
        "analysis_sha256": receipt["analysis_sha256"],
        "report_sha256": receipt["report_sha256"],
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def analyze_frozen_ocr_candidate_review(
    session_dir: Path,
    *,
    allowed_work_root: Path = DEFAULT_HUMAN_REVIEW_ROOT,
) -> dict[str, Any]:
    """Join one frozen human pass to its restricted method map."""

    context = ReviewContext(
        session_dir, allowed_work_root=allowed_work_root
    )
    if context.protocol.review_mode != "candidate-review":
        raise OcrCandidateAnalysisError(
            "post-reveal OCR analysis requires a candidate-review session"
        )
    if context.state.get("status") != "submitted-and-frozen":
        raise OcrCandidateAnalysisError(
            "post-reveal OCR analysis requires a frozen human draft"
        )
    draft_sha256 = _sha256_file(context.draft_path)
    output_dir = context.session_dir / ANALYSIS_DIR
    if output_dir.is_symlink():
        raise OcrCandidateAnalysisError("post-reveal output is a symlink")
    if output_dir.exists():
        return _verify_existing_analysis(
            context, output_dir, draft_sha256=draft_sha256
        )

    draft = _load_json(context.draft_path)
    freeze_receipt = _load_json(context.receipt_path)
    blind_record = context.manifest.get("blind_map")
    if not isinstance(blind_record, dict):
        raise OcrCandidateAnalysisError("candidate manifest has no blind map")
    blind_path = (
        context.packet_root / str(blind_record.get("ref", ""))
    ).resolve()
    try:
        blind_path.relative_to(context.packet_root)
    except ValueError as exc:
        raise OcrCandidateAnalysisError("blind map escaped packet") from exc
    if (
        blind_path.is_symlink()
        or not blind_path.is_file()
        or _sha256_file(blind_path) != blind_record.get("sha256")
    ):
        raise OcrCandidateAnalysisError("blind map fixity drifted")
    blind_map = _load_json(blind_path)
    joined, methods = _joined_rows(context, draft, blind_map)

    by_variant = {
        variant: _aggregate_rows(
            [row for row in joined if row["variant"] == variant]
        )
        for variant in VARIANTS
    }
    generated_at = _utc_now()
    analysis_id = (
        f"{context.session.get('session_id')}-ocr-post-reveal-v1"
    )
    analysis = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "status": "bounded-post-reveal-descriptive-analysis",
        "created_at_utc": generated_at,
        "private_local_only": True,
        "publishable": False,
        "packet": {
            "packet_id": context.manifest["packet_id"],
            "manifest_ref": context.manifest_path.as_posix(),
            "manifest_sha256": _sha256_file(context.manifest_path),
            "blind_map_ref": blind_path.as_posix(),
            "blind_map_sha256": _sha256_file(blind_path),
            "candidate_set_sha256": context.manifest.get(
                "candidate_set_sha256"
            ),
        },
        "human_review": {
            "session_id": context.session.get("session_id"),
            "protocol_id": context.protocol.protocol_id,
            "reviewer_ref": draft["reviewer_ref"],
            "performed_by_real_human": draft["performed_by_real_human"],
            "submitted_at_utc": freeze_receipt["submitted_at_utc"],
            "draft_ref": context.draft_path.name,
            "draft_sha256": draft_sha256,
            "freeze_receipt_ref": context.receipt_path.name,
            "freeze_receipt_sha256": _sha256_file(context.receipt_path),
        },
        "scope": {
            "source_count": context.manifest["source_count"],
            "unit_count": len(joined),
            "variant_count": len(methods),
            "variants": list(VARIANTS),
            "human_pass_count": 1,
            "independent_gold_available": False,
        },
        "methods": {variant: methods[variant] for variant in VARIANTS},
        "aggregates_by_variant": by_variant,
        "display_position_audit": _position_audit(joined),
        "per_source": _per_source(joined),
        "interpretation_limits": [
            "one real-human pass only",
            "ten source pages and thirty candidate judgments only",
            "no accepted independent transcription; CER and WER remain blocked",
            "active-time comparison is blocked when display positions are imbalanced",
            "runtime summaries and stopped-run receipts retain their own comparability limits",
            "no general OCR winner or Tree of Sophia content promotion",
        ],
        "authority_boundary": AUTHORITY_BOUNDARY,
    }
    report = _render_report(analysis)

    post_reveal_root = output_dir.parent
    if post_reveal_root.is_symlink():
        raise OcrCandidateAnalysisError("post-reveal root is a symlink")
    post_reveal_root.mkdir(mode=0o700, exist_ok=True)
    temporary_dir = Path(
        tempfile.mkdtemp(
            prefix=".ocr-candidate-analysis-v1.",
            dir=post_reveal_root,
        )
    )
    os.chmod(temporary_dir, 0o700)
    try:
        analysis_path = temporary_dir / ANALYSIS_FILENAME
        report_path = temporary_dir / REPORT_FILENAME
        _write_private(
            analysis_path,
            (
                json.dumps(analysis, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8"),
        )
        _write_private(report_path, report.encode("utf-8"))
        receipt = {
            "schema_version": ANALYSIS_RECEIPT_SCHEMA_VERSION,
            "analysis_id": analysis_id,
            "status": analysis["status"],
            "created_at_utc": generated_at,
            "session_id": context.session.get("session_id"),
            "packet_id": context.manifest["packet_id"],
            "draft_sha256": draft_sha256,
            "freeze_receipt_sha256": _sha256_file(context.receipt_path),
            "manifest_sha256": _sha256_file(context.manifest_path),
            "blind_map_sha256": _sha256_file(blind_path),
            "analysis_ref": ANALYSIS_FILENAME,
            "analysis_sha256": _sha256_file(analysis_path),
            "report_ref": REPORT_FILENAME,
            "report_sha256": _sha256_file(report_path),
            "private_local_only": True,
            "publishable": False,
            "authority_boundary": AUTHORITY_BOUNDARY,
        }
        _write_private(
            temporary_dir / RECEIPT_FILENAME,
            (
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8"),
        )
        os.replace(temporary_dir, output_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise

    relative = output_dir.relative_to(context.session_dir).as_posix()
    analysis_record = {
        "analysis_id": analysis_id,
        "status": analysis["status"],
        "analysis_ref": f"{relative}/{ANALYSIS_FILENAME}",
        "analysis_sha256": receipt["analysis_sha256"],
        "report_ref": f"{relative}/{REPORT_FILENAME}",
        "report_sha256": receipt["report_sha256"],
        "receipt_ref": f"{relative}/{RECEIPT_FILENAME}",
    }
    _write_control_projection(context, analysis_record)
    return {
        "status": analysis["status"],
        "analysis_id": analysis_id,
        "analysis_dir": output_dir.as_posix(),
        "changed": True,
        "reused_existing": False,
        "analysis_sha256": receipt["analysis_sha256"],
        "report_sha256": receipt["report_sha256"],
        "authority_boundary": AUTHORITY_BOUNDARY,
    }
