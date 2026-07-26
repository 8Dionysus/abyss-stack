#!/usr/bin/env python3
"""Materialize a private, method-blind OCR candidate review packet."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

from human_gold_review import verify_human_gold_review_manifest
from ocr_render import png_header
from translation_source import (
    PACKET_ID_RE,
    _artifact_record,
    _canonical_sha256,
    _load_json,
    _schema_issues,
    _sha256_file,
    _utc_now,
    _within,
    _write_json,
    _write_jsonl,
)


PART_ROOT = Path(__file__).resolve().parent
MANIFEST_SCHEMA_PATH = (
    PART_ROOT / "schemas/ocr-candidate-review-manifest.schema.json"
)
DEFAULT_SHARED_ROOT = Path(
    "/srv/abyss-machine/storage/artifacts/tree-of-sophia-foundation-lab/"
    "shared-inputs/tos-ocr-candidate-review-v1"
)
DEFAULT_HUMAN_REVIEW_ROOT = Path(
    "/srv/abyss-machine/storage/artifacts/tree-of-sophia-foundation-lab/"
    "human-review"
)
AUTHORITY_BOUNDARY = (
    "private method-blind source-visible OCR candidate review packet; "
    "candidate visibility and a human review draft do not create source truth, "
    "gold, accepted text, a general method ranking, translation, or canon"
)
BLIND_MAP_BOUNDARY = (
    "restricted method-identity map for post-review analysis only; never expose "
    "it through the human-review workbench"
)
ACTIVE_WORKBENCH_PROTOCOL_ID = "tos.human-review.ocr-candidate-pass-1.v2"


class OcrCandidateReviewError(RuntimeError):
    """Raised when candidate review evidence cannot remain fixed and blind."""


def _candidate_output_path(run_root: Path, sample_id: str) -> Path | None:
    candidates = (
        run_root / "raw-output" / sample_id / "recognition.txt",
        run_root / "raw-output" / sample_id / f"{sample_id}.txt",
    )
    for candidate in candidates:
        if candidate.is_file() and _within(candidate, run_root):
            return candidate.resolve()
    return None


def _run_identity(run_root: Path) -> dict[str, Any]:
    root = run_root.resolve()
    if not root.is_dir():
        raise OcrCandidateReviewError(f"candidate run is missing: {root}")
    receipt_path = root / "run.receipt.json"
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise OcrCandidateReviewError(
            f"candidate run has no stable receipt: {root}"
        )
    receipt = _load_json(receipt_path)
    run_id = receipt.get("run_id")
    variant = receipt.get("variant")
    experiment_id = receipt.get("experiment_id")
    if (
        not isinstance(run_id, str)
        or not run_id
        or variant not in {"A", "B", "C"}
        or not isinstance(experiment_id, str)
        or not experiment_id
    ):
        raise OcrCandidateReviewError(
            f"candidate run identity is incomplete: {root}"
        )
    return {
        "root": root,
        "receipt_path": receipt_path.resolve(),
        "receipt_sha256": _sha256_file(receipt_path),
        "run_id": run_id,
        "variant": variant,
        "experiment_id": experiment_id,
        "status": receipt.get("status"),
        "method_revision": receipt.get("method_revision"),
        "sample_ids": tuple(str(value) for value in receipt.get("sample_ids", [])),
    }


def _set_private_modes(root: Path) -> None:
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
    ):
        os.chmod(directory, 0o700)
    for file_path in root.rglob("*"):
        if file_path.is_file():
            os.chmod(file_path, 0o400)
    os.chmod(root, 0o700)


def _candidate_set_sha256(units: Iterable[dict[str, Any]]) -> str:
    return _canonical_sha256(
        [
            {
                "review_unit_id": unit["review_unit_id"],
                "source_sample_id": unit["source_sample_id"],
                "candidate_label": unit["candidate_label"],
                "candidate_sha256": unit["candidate_sha256"],
            }
            for unit in units
        ]
    )


def materialize_ocr_candidate_review(
    human_gold_manifest_path: Path,
    candidate_run_roots: list[Path],
    packet_id: str,
    *,
    languages: tuple[str, ...] = ("ru",),
    shared_root: Path = DEFAULT_SHARED_ROOT,
    invocation: list[str] | None = None,
) -> dict[str, Any]:
    """Freeze source triplets and randomized visible OCR candidates."""

    if not PACKET_ID_RE.fullmatch(packet_id):
        raise OcrCandidateReviewError(
            "packet_id must use lowercase letters, digits, dots, underscores, or dashes"
        )
    normalized_languages = tuple(
        dict.fromkeys(language.strip().lower() for language in languages)
    )
    if (
        not normalized_languages
        or any(
            len(language) not in {2, 3} or not language.isalpha()
            for language in normalized_languages
        )
    ):
        raise OcrCandidateReviewError("at least one ISO-like language code is required")
    if not candidate_run_roots:
        raise OcrCandidateReviewError("at least one candidate run is required")

    source_manifest_path = human_gold_manifest_path.resolve()
    source_manifest = verify_human_gold_review_manifest(source_manifest_path)
    source_root = source_manifest_path.parent
    run_identities = [_run_identity(path) for path in candidate_run_roots]
    experiment_ids = {identity["experiment_id"] for identity in run_identities}
    run_ids = [identity["run_id"] for identity in run_identities]
    variants = [identity["variant"] for identity in run_identities]
    if len(experiment_ids) != 1:
        raise OcrCandidateReviewError(
            "candidate runs must belong to one frozen experiment"
        )
    if len(run_ids) != len(set(run_ids)) or len(variants) != len(set(variants)):
        raise OcrCandidateReviewError(
            "candidate runs must have unique run and variant identities"
        )

    source_units = [
        unit
        for unit in source_manifest.get("units", [])
        if isinstance(unit, dict)
        and str(unit.get("language", "")).lower() in normalized_languages
    ]
    if not source_units:
        raise OcrCandidateReviewError(
            "the selected language scope contains no source units"
        )

    final_root = (shared_root.resolve() / packet_id).resolve()
    if not _within(final_root, shared_root.resolve()):
        raise OcrCandidateReviewError("candidate review packet escaped shared root")
    if final_root.exists():
        raise OcrCandidateReviewError(
            f"candidate review packet already exists: {final_root}"
        )
    shared_root.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{packet_id}.", dir=shared_root.resolve())
    )
    try:
        pages_dir = temporary_root / "pages"
        candidates_dir = temporary_root / "candidates"
        reviews_dir = temporary_root / "reviews"
        restricted_dir = temporary_root / "restricted"
        for directory in (
            pages_dir,
            candidates_dir,
            reviews_dir,
            restricted_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        page_records_by_ref: dict[str, dict[str, Any]] = {}
        source_page_refs: dict[str, dict[str, str]] = {}
        for source_unit in source_units:
            sample_id = str(source_unit["sample_id"])
            source_page_refs[sample_id] = {}
            for role, key in (
                ("previous", "previous_page_ref"),
                ("current", "current_page_ref"),
                ("next", "next_page_ref"),
            ):
                source_page = (source_root / str(source_unit[key])).resolve()
                if (
                    not _within(source_page, source_root)
                    or not source_page.is_file()
                    or source_page.is_symlink()
                ):
                    raise OcrCandidateReviewError(
                        f"{sample_id}: invalid {role} source page"
                    )
                relative_ref = f"pages/{source_page.name}"
                destination = temporary_root / relative_ref
                if not destination.exists():
                    shutil.copyfile(source_page, destination)
                source_page_refs[sample_id][role] = relative_ref
                page_records_by_ref[relative_ref] = _artifact_record(
                    temporary_root, destination
                )

        units: list[dict[str, Any]] = []
        template_rows: list[dict[str, Any]] = []
        blind_entries: list[dict[str, Any]] = []
        randomizer = secrets.SystemRandom()
        for source_unit in source_units:
            visual_sample_id = str(source_unit["visual_sample_id"])
            available: list[tuple[dict[str, Any], Path]] = []
            for identity in run_identities:
                output_path = _candidate_output_path(
                    identity["root"], visual_sample_id
                )
                if output_path is None:
                    continue
                try:
                    text = output_path.read_text(encoding="utf-8")
                except UnicodeDecodeError as exc:
                    raise OcrCandidateReviewError(
                        f"{identity['run_id']}:{visual_sample_id} is not UTF-8"
                    ) from exc
                if not text.strip():
                    continue
                available.append((identity, output_path))
            if not available:
                raise OcrCandidateReviewError(
                    f"no candidate output is available for {visual_sample_id}"
                )
            randomizer.shuffle(available)
            source_sample_id = str(source_unit["sample_id"])
            for position, (identity, output_path) in enumerate(available, start=1):
                candidate_letter = chr(ord("A") + position - 1)
                review_unit_id = (
                    f"{source_sample_id}-candidate-{candidate_letter.lower()}"
                )
                candidate_ref = f"candidates/{review_unit_id}.txt"
                candidate_path = temporary_root / candidate_ref
                shutil.copyfile(output_path, candidate_path)
                candidate_sha256 = _sha256_file(candidate_path)
                candidate_bytes = candidate_path.stat().st_size
                unit = {
                    "review_unit_id": review_unit_id,
                    "source_sample_id": source_sample_id,
                    "visual_sample_id": visual_sample_id,
                    "source_anchor_ref": source_unit["source_anchor_ref"],
                    "group_id": source_unit["group_id"],
                    "language": str(source_unit["language"]).lower(),
                    "pdf_page": int(source_unit["pdf_page"]),
                    "difficulty": source_unit["difficulty"],
                    "strata": list(source_unit.get("strata", [])),
                    "candidate_label": f"Кандидат {candidate_letter}",
                    "candidate_position": position,
                    "candidate_count_for_source": len(available),
                    "candidate_ref": candidate_ref,
                    "candidate_sha256": candidate_sha256,
                    "candidate_bytes": candidate_bytes,
                    "source_pages": dict(source_page_refs[source_sample_id]),
                }
                units.append(unit)
                template_rows.append(
                    {
                        "review_unit_id": review_unit_id,
                        "source_pages": dict(source_page_refs[source_sample_id]),
                    }
                )
                blind_entries.append(
                    {
                        "review_unit_id": review_unit_id,
                        "source_sample_id": source_sample_id,
                        "visual_sample_id": visual_sample_id,
                        "candidate_label": unit["candidate_label"],
                        "candidate_sha256": candidate_sha256,
                        "run_id": identity["run_id"],
                        "variant": identity["variant"],
                        "run_status": identity["status"],
                        "method_revision": identity["method_revision"],
                        "run_receipt_ref": identity["receipt_path"].as_posix(),
                        "run_receipt_sha256": identity["receipt_sha256"],
                        "candidate_source_ref": output_path.as_posix(),
                        "candidate_source_sha256": _sha256_file(output_path),
                    }
                )

        template_path = reviews_dir / "ocr-candidate-review.template.jsonl"
        _write_jsonl(template_path, template_rows)
        blind_map_path = restricted_dir / "blind-map.json"
        _write_json(
            blind_map_path,
            {
                "schema_version": "tos_ocr_candidate_review_blind_map_v1",
                "packet_id": packet_id,
                "created_at_utc": _utc_now(),
                "entries": blind_entries,
                "authority_boundary": BLIND_MAP_BOUNDARY,
            },
        )
        receipt_path = temporary_root / "ocr-candidate-review.receipt.json"
        manifest_path = temporary_root / "ocr-candidate-review-manifest.json"
        manifest: dict[str, Any] = {
            "schema_version": "tos_ocr_candidate_review_manifest_v1",
            "packet_id": packet_id,
            "experiment_id": next(iter(experiment_ids)),
            "created_at_utc": _utc_now(),
            "artifact_root": final_root.as_posix(),
            "status": "awaiting-source-visible-human-review",
            "private_local_only": True,
            "publishable": False,
            "review_mode": "candidate-review",
            "method_identity_visible": False,
            "candidate_text_visible": True,
            "recognized_reference_visible": False,
            "source_packet": {
                "packet_id": source_manifest["packet_id"],
                "manifest_ref": source_manifest_path.as_posix(),
                "manifest_sha256": _sha256_file(source_manifest_path),
            },
            "language_scope": list(normalized_languages),
            "source_count": len(source_units),
            "candidate_run_count": len(run_identities),
            "unit_count": len(units),
            "pages": [
                page_records_by_ref[key] for key in sorted(page_records_by_ref)
            ],
            "units": units,
            "review_template": _artifact_record(
                temporary_root, template_path
            ),
            "blind_map": _artifact_record(temporary_root, blind_map_path),
            "candidate_set_sha256": _candidate_set_sha256(units),
            "receipt_ref": "ocr-candidate-review.receipt.json",
            "authority_boundary": AUTHORITY_BOUNDARY,
        }
        _write_json(manifest_path, manifest)
        _write_json(
            receipt_path,
            {
                "schema_version": "tos_ocr_candidate_review_receipt_v1",
                "packet_id": packet_id,
                "status": "awaiting-source-visible-human-review",
                "created_at_utc": _utc_now(),
                "manifest_ref": "ocr-candidate-review-manifest.json",
                "manifest_sha256": _sha256_file(manifest_path),
                "candidate_set_sha256": manifest["candidate_set_sha256"],
                "source_count": len(source_units),
                "unit_count": len(units),
                "invocation": list(invocation or []),
                "errors": [],
                "authority_boundary": AUTHORITY_BOUNDARY,
            },
        )
        _set_private_modes(temporary_root)
        os.replace(temporary_root, final_root)
    except Exception:
        if temporary_root.exists():
            shutil.rmtree(temporary_root)
        raise

    return verify_ocr_candidate_review_manifest(
        final_root / "ocr-candidate-review-manifest.json"
    )


def verify_ocr_candidate_review_manifest(
    manifest_path: Path,
) -> dict[str, Any]:
    """Verify packet fixity without treating review content as correct."""

    path = manifest_path.resolve()
    manifest = _load_json(path)
    issues = _schema_issues(manifest, MANIFEST_SCHEMA_PATH)
    if issues:
        raise OcrCandidateReviewError(
            "invalid OCR candidate review manifest: " + "; ".join(issues)
        )
    root = path.parent
    if manifest.get("artifact_root") != root.as_posix():
        issues.append("artifact_root does not match the packet directory")

    source_record = manifest["source_packet"]
    source_manifest_path = Path(source_record["manifest_ref"]).resolve()
    if (
        not source_manifest_path.is_file()
        or _sha256_file(source_manifest_path) != source_record["manifest_sha256"]
    ):
        issues.append("source packet manifest is missing or drifted")
    else:
        try:
            source_manifest = verify_human_gold_review_manifest(
                source_manifest_path
            )
            if source_manifest.get("packet_id") != source_record["packet_id"]:
                issues.append("source packet identity drifted")
        except Exception as exc:  # source verifier owns its detailed failure
            issues.append(f"source packet verification failed: {exc}")

    page_refs: set[str] = set()
    for index, artifact in enumerate(manifest["pages"]):
        ref = str(artifact["ref"])
        asset = (root / ref).resolve()
        if (
            ref in page_refs
            or not _within(asset, root)
            or not asset.is_file()
            or asset.is_symlink()
        ):
            issues.append(f"pages[{index}] is duplicate, missing, or escaped")
            continue
        page_refs.add(ref)
        if (
            _sha256_file(asset) != artifact["sha256"]
            or asset.stat().st_size != artifact["bytes"]
        ):
            issues.append(f"pages[{index}] fixity drifted")
        try:
            png_header(asset)
        except Exception as exc:
            issues.append(f"pages[{index}] is not a valid PNG: {exc}")

    units = manifest["units"]
    unit_ids = [str(unit["review_unit_id"]) for unit in units]
    if len(unit_ids) != len(set(unit_ids)):
        issues.append("review unit IDs are not unique")
    if manifest["unit_count"] != len(units):
        issues.append("unit_count drifted")
    if manifest["source_count"] != len(
        {str(unit["source_sample_id"]) for unit in units}
    ):
        issues.append("source_count drifted")

    candidate_refs: set[str] = set()
    grouped_positions: dict[str, list[int]] = {}
    for index, unit in enumerate(units):
        ref = str(unit["candidate_ref"])
        candidate = (root / ref).resolve()
        if (
            ref in candidate_refs
            or not _within(candidate, root)
            or not candidate.is_file()
            or candidate.is_symlink()
        ):
            issues.append(
                f"units[{index}] candidate is duplicate, missing, or escaped"
            )
            continue
        candidate_refs.add(ref)
        if (
            _sha256_file(candidate) != unit["candidate_sha256"]
            or candidate.stat().st_size != unit["candidate_bytes"]
        ):
            issues.append(f"units[{index}] candidate fixity drifted")
        try:
            candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            issues.append(f"units[{index}] candidate is not UTF-8")
        pages = unit["source_pages"]
        if any(str(pages[role]) not in page_refs for role in pages):
            issues.append(f"units[{index}] source page set is unresolved")
        sample_id = str(unit["source_sample_id"])
        grouped_positions.setdefault(sample_id, []).append(
            int(unit["candidate_position"])
        )
        if unit["candidate_count_for_source"] < unit["candidate_position"]:
            issues.append(f"units[{index}] candidate position is inconsistent")
    for sample_id, positions in grouped_positions.items():
        expected = list(range(1, len(positions) + 1))
        if sorted(positions) != expected:
            issues.append(f"{sample_id}: candidate positions are not contiguous")
        declared = {
            int(unit["candidate_count_for_source"])
            for unit in units
            if unit["source_sample_id"] == sample_id
        }
        if declared != {len(positions)}:
            issues.append(f"{sample_id}: candidate count drifted")

    template_record = manifest["review_template"]
    template_path = (root / str(template_record["ref"])).resolve()
    if (
        not _within(template_path, root)
        or not template_path.is_file()
        or template_path.is_symlink()
        or _sha256_file(template_path) != template_record["sha256"]
        or template_path.stat().st_size != template_record["bytes"]
    ):
        issues.append("review template is missing, escaped, or drifted")
        template_rows: list[dict[str, Any]] = []
    else:
        try:
            template_rows = [
                json.loads(line)
                for line in template_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            issues.append(f"review template is unreadable: {exc}")
            template_rows = []
    expected_template_rows = [
        {
            "review_unit_id": unit["review_unit_id"],
            "source_pages": unit["source_pages"],
        }
        for unit in units
    ]
    if template_rows != expected_template_rows:
        issues.append("review template is not the exact ordered blank template")

    blind_record = manifest["blind_map"]
    blind_path = (root / str(blind_record["ref"])).resolve()
    if (
        not _within(blind_path, root)
        or not blind_path.is_file()
        or blind_path.is_symlink()
        or _sha256_file(blind_path) != blind_record["sha256"]
        or blind_path.stat().st_size != blind_record["bytes"]
    ):
        issues.append("blind map is missing, escaped, or drifted")
        blind_map: dict[str, Any] = {}
    else:
        blind_map = _load_json(blind_path)
    blind_entries = blind_map.get("entries", [])
    if (
        blind_map.get("schema_version")
        != "tos_ocr_candidate_review_blind_map_v1"
        or blind_map.get("packet_id") != manifest["packet_id"]
        or blind_map.get("authority_boundary") != BLIND_MAP_BOUNDARY
        or not isinstance(blind_entries, list)
        or [entry.get("review_unit_id") for entry in blind_entries] != unit_ids
    ):
        issues.append("blind map identity or order drifted")
    else:
        if len({entry.get("run_id") for entry in blind_entries}) != manifest[
            "candidate_run_count"
        ]:
            issues.append("candidate_run_count drifted")
        for unit, entry in zip(units, blind_entries, strict=True):
            if (
                entry.get("candidate_label") != unit["candidate_label"]
                or entry.get("candidate_sha256") != unit["candidate_sha256"]
                or entry.get("source_sample_id") != unit["source_sample_id"]
            ):
                issues.append(
                    f"{unit['review_unit_id']}: restricted blind mapping drifted"
                )

    if manifest["candidate_set_sha256"] != _candidate_set_sha256(units):
        issues.append("candidate_set_sha256 drifted")

    receipt_path = (root / str(manifest["receipt_ref"])).resolve()
    if (
        not _within(receipt_path, root)
        or not receipt_path.is_file()
        or receipt_path.is_symlink()
    ):
        issues.append("packet receipt is missing or escaped")
    else:
        receipt = _load_json(receipt_path)
        expected_receipt = {
            "schema_version": "tos_ocr_candidate_review_receipt_v1",
            "packet_id": manifest["packet_id"],
            "status": manifest["status"],
            "manifest_ref": path.name,
            "manifest_sha256": _sha256_file(path),
            "candidate_set_sha256": manifest["candidate_set_sha256"],
            "source_count": manifest["source_count"],
            "unit_count": manifest["unit_count"],
            "authority_boundary": AUTHORITY_BOUNDARY,
        }
        for key, value in expected_receipt.items():
            if receipt.get(key) != value:
                issues.append(f"packet receipt drifted at {key}")
        if receipt.get("errors") != []:
            issues.append("packet receipt carries materialization errors")

    if (
        manifest.get("review_mode") != "candidate-review"
        or manifest.get("method_identity_visible") is not False
        or manifest.get("candidate_text_visible") is not True
        or manifest.get("recognized_reference_visible") is not False
        or manifest.get("authority_boundary") != AUTHORITY_BOUNDARY
    ):
        issues.append("candidate review visibility boundary drifted")
    if issues:
        raise OcrCandidateReviewError(
            "invalid OCR candidate review manifest: " + "; ".join(issues)
        )
    return manifest


def initialize_ocr_candidate_review_session(
    manifest_path: Path,
    session_id: str,
    *,
    review_root: Path = DEFAULT_HUMAN_REVIEW_ROOT,
) -> Path:
    """Create one mutable session shell around a verified candidate packet."""

    if not PACKET_ID_RE.fullmatch(session_id):
        raise OcrCandidateReviewError(
            "session_id must use lowercase letters, digits, dots, underscores, or dashes"
        )
    manifest = verify_ocr_candidate_review_manifest(manifest_path)
    root = review_root.resolve()
    session_dir = (root / session_id).resolve()
    if not _within(session_dir, root):
        raise OcrCandidateReviewError("review session escaped the review root")
    if session_dir.exists():
        raise OcrCandidateReviewError(
            f"review session already exists: {session_dir}"
        )
    session_dir.mkdir(parents=True, mode=0o700)
    session_path = session_dir / "review-session.json"
    _write_json(
        session_path,
        {
            "schema_version": "tos_ocr_candidate_review_session_v1",
            "session_id": session_id,
            "protocol_id": ACTIVE_WORKBENCH_PROTOCOL_ID,
            "created_at_utc": _utc_now(),
            "status": "awaiting-real-human-candidate-review",
            "private_local_only": True,
            "publishable": False,
            "packet": {
                "packet_id": manifest["packet_id"],
                "root": manifest_path.resolve().parent.as_posix(),
                "status": manifest["status"],
                "review_unit_count": manifest["unit_count"],
                "source_count": manifest["source_count"],
                "candidate_run_count": manifest["candidate_run_count"],
                "candidate_set_sha256": manifest["candidate_set_sha256"],
                "manifest_sha256": _sha256_file(manifest_path),
            },
            "progress": {
                "total_units": manifest["unit_count"],
                "completed_units": 0,
            },
            "next_action": (
                "Open the loopback Workbench, compare each visible OCR candidate "
                "with its source page, and record only judgments within the "
                "reviewer's declared language competence."
            ),
            "authority_boundary": AUTHORITY_BOUNDARY,
        },
    )
    os.chmod(session_path, 0o600)
    return session_dir
