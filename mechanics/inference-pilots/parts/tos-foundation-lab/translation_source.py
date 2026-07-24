#!/usr/bin/env python3
"""Freeze the pre-translation German source-review packet.

This stage resolves the exact OCR-derived EPUB members selected by Tree of
Sophia, verifies the sibling scan PDF, and prepares blank human-review
surfaces.  It deliberately does not read a recognized translation, run a
translation model, or promote automated OCR to accepted German text.
"""

from __future__ import annotations

import hashlib
import json
import re
import resource
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from native_structure import extract_xhtml_text


PART_ROOT = Path(__file__).resolve().parent
MANIFEST_SCHEMA_PATH = PART_ROOT / "schemas/translation-source-manifest.schema.json"
INSPECTION_SCHEMA_PATH = (
    PART_ROOT / "schemas/translation-source-model-inspection.schema.json"
)
DEFAULT_SHARED_ROOT = Path(
    "/srv/abyss-machine/storage/artifacts/tree-of-sophia-foundation-lab/"
    "shared-inputs/tos-translation-foundation-v1"
)
PACKET_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
MEMBER_RE = re.compile(r"^EPUB/page_([0-9]+)\.html$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
TERMINAL_PUNCTUATION = frozenset(".?!")
SENTENCE_CLOSERS = frozenset('"\'»“”’)]}')

AUTHORITY_BOUNDARY = (
    "mechanically verified private source-review input only; automated EPUB OCR, "
    "sentence boundaries, EPUB-to-PDF mapping, and German transcription remain "
    "unaccepted until real source-visible human review"
)


class TranslationSourceError(RuntimeError):
    """Raised when the pre-translation source packet cannot be frozen safely."""


class _FirstBodyParagraphParser(HTMLParser):
    """Collect visible text from the first paragraph inside ``body`` only."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._body_depth = 0
        self._paragraph_depth = 0
        self._suppressed_depth = 0
        self._complete = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag == "body":
            self._body_depth += 1
            return
        if not self._body_depth or self._complete:
            return
        if tag in {"script", "style"}:
            self._suppressed_depth += 1
        elif tag == "p" and self._paragraph_depth == 0:
            self._paragraph_depth = 1
        elif self._paragraph_depth and tag == "br":
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "body":
            self._body_depth = max(0, self._body_depth - 1)
            return
        if not self._body_depth or self._complete:
            return
        if tag in {"script", "style"} and self._suppressed_depth:
            self._suppressed_depth -= 1
        elif tag == "p" and self._paragraph_depth:
            self._paragraph_depth = 0
            self._complete = True

    def handle_data(self, data: str) -> None:
        if self._paragraph_depth and not self._suppressed_depth and not self._complete:
            self._parts.append(data)

    def text(self) -> str:
        return " ".join("".join(self._parts).split())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TranslationSourceError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TranslationSourceError(f"{path} must contain a JSON object")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TranslationSourceError(f"cannot read {path}: {exc}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise TranslationSourceError(f"{path}:{line_number} is unexpectedly blank")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TranslationSourceError(f"cannot read {path}:{line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise TranslationSourceError(f"{path}:{line_number} must contain a JSON object")
        records.append(record)
    return records


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    path.write_text(body, encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def extract_first_body_paragraph(data: bytes) -> str:
    parser = _FirstBodyParagraphParser()
    parser.feed(data.decode("utf-8", errors="replace"))
    parser.close()
    return parser.text()


def first_complete_sentence(text: str) -> str:
    """Return a transparent punctuation-based candidate, never an accepted boundary."""

    normalized = " ".join(text.split())
    for index, character in enumerate(normalized):
        if character not in TERMINAL_PUNCTUATION:
            continue
        end = index + 1
        while end < len(normalized) and normalized[end] in SENTENCE_CLOSERS:
            end += 1
        if end < len(normalized) and not normalized[end].isspace():
            continue
        candidate = normalized[:end].strip()
        if any(letter.isalpha() for letter in candidate):
            return candidate
    raise TranslationSourceError("first body paragraph has no complete punctuation boundary")


def _surface_key(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).casefold().split())


def mechanical_candidate_hazards(
    candidate: str, structural_context: str
) -> dict[str, Any]:
    """Expose cheap warning signals without pretending to review the candidate."""

    normalized = " ".join(candidate.split())
    if not normalized:
        raise TranslationSourceError("cannot characterize an empty sentence candidate")
    tokens = normalized.split()
    first = normalized[0]
    return {
        "status": "software-advisory-not-review",
        "candidate_character_count": len(normalized),
        "candidate_token_count": len(tokens),
        "starts_with_lowercase": first.isalpha() and first.islower(),
        "starts_with_nonletter": not first.isalpha(),
        "short_candidate": len(tokens) <= 6 or len(normalized) <= 40,
        "matches_structural_context_surface": (
            _surface_key(normalized) == _surface_key(structural_context)
        ),
        "page_start_boundary_unverified": True,
        "requires_source_visible_review": True,
    }


def _schema_issues(
    payload: object, schema_path: Path = MANIFEST_SCHEMA_PATH
) -> list[str]:
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[str] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path)):
        location = "".join(f"[{part!r}]" for part in error.absolute_path) or "<root>"
        issues.append(f"{location}: {error.message}")
    return issues


def validate_translation_plan(plan: dict[str, Any]) -> list[str]:
    """Enforce the pre-draft and sealed-comparator boundary owned by this stage."""

    issues: list[str] = []
    expected_scalars = {
        "schema_version": "tos_translation_sample_plan_v1",
        "source_language": "de",
        "target_language": "ru",
        "status": "frozen",
        "frozen_before_drafts": True,
        "fragment_count": 30,
        "review_status": "unreviewed",
    }
    for key, expected in expected_scalars.items():
        if plan.get(key) != expected:
            issues.append(f"{key} must remain {expected!r} before source review")

    selector = plan.get("selector_method")
    expected_selector = {
        "unit": "first_complete_sentence_in_body-p-1",
        "segmentation": "tos-local-sentence-segmentation-v1",
        "selector_status": "proposed_until_source_visible_human_acceptance",
    }
    if selector != expected_selector:
        issues.append("selector_method drifted from the frozen software-proposal boundary")

    comparator = plan.get("recognized_comparator")
    allowed_comparator_keys = {
        "expression_ref",
        "item_ref",
        "visibility",
        "anchor_resolution_status",
        "reveal_stage",
    }
    if not isinstance(comparator, dict):
        issues.append("recognized_comparator must be an object")
    else:
        if set(comparator) != allowed_comparator_keys:
            issues.append("recognized_comparator must contain metadata only, never content references")
        if comparator.get("visibility") != "sealed":
            issues.append("recognized comparator is not sealed")
        if comparator.get("anchor_resolution_status") != "not_started":
            issues.append("recognized comparator anchors must remain unresolved")
        if comparator.get("reveal_stage") != (
            "after_human_ai_and_ai-human_independent_drafts_are_frozen"
        ):
            issues.append("recognized comparator reveal stage drifted")

    lanes = plan.get("lanes")
    expected_lanes = {
        "human_only": "not_started",
        "ai_only": "not_started",
        "ai_human": "not_started",
        "recognized_comparator": "sealed",
    }
    if lanes != expected_lanes:
        issues.append("translation lanes must all remain unstarted with the comparator sealed")

    fragments = plan.get("fragments")
    if not isinstance(fragments, list) or len(fragments) != 30:
        issues.append("translation plan must contain exactly 30 fragments")
        return issues
    ids: list[object] = []
    members: list[object] = []
    anchors: list[object] = []
    for index, fragment in enumerate(fragments, start=1):
        location = f"fragments[{index - 1}]"
        if not isinstance(fragment, dict):
            issues.append(f"{location} must be an object")
            continue
        expected_id = f"tos-translation-fragment-{index:03d}"
        if fragment.get("fragment_id") != expected_id:
            issues.append(f"{location}.fragment_id must be {expected_id}")
        ids.append(fragment.get("fragment_id"))
        members.append(fragment.get("container_member"))
        anchors.append(fragment.get("source_anchor_ref"))
        member_match = MEMBER_RE.fullmatch(str(fragment.get("container_member", "")))
        if member_match is None:
            issues.append(f"{location}.container_member is invalid")
        elif int(member_match.group(1)) != fragment.get("page_member_index"):
            issues.append(f"{location}.page_member_index does not match its member path")
        if not SHA256_RE.fullmatch(str(fragment.get("member_sha256", ""))):
            issues.append(f"{location}.member_sha256 is invalid")
        if fragment.get("source_transcription_status") != "not_started":
            issues.append(f"{location} already claims source transcription progress")
        if fragment.get("human_source_acceptance") is not False:
            issues.append(f"{location} must not claim absent human source acceptance")
    if len(set(ids)) != 30 or len(set(members)) != 30 or len(set(anchors)) != 30:
        issues.append("fragment IDs, EPUB members, and source anchors must each be unique")
    return issues


def _validate_anchors(plan: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    fragments = plan.get("fragments", [])
    if len(records) != 30:
        return ["translation anchor set must contain exactly 30 records"]
    by_id = {record.get("anchor_id"): record for record in records}
    if len(by_id) != 30 or None in by_id:
        issues.append("translation anchor IDs must be unique and non-null")
    for fragment in fragments:
        if not isinstance(fragment, dict):
            continue
        fragment_id = str(fragment.get("fragment_id"))
        anchor = by_id.get(fragment.get("source_anchor_ref"))
        if not isinstance(anchor, dict):
            issues.append(f"{fragment_id}: source anchor is unresolved")
            continue
        for key, plan_key in (
            ("item_id", "source_item_ref"),
            ("file_id", "source_file_ref"),
            ("file_sha256", "source_file_sha256"),
        ):
            if anchor.get(key) != plan.get(plan_key):
                issues.append(f"{fragment_id}: anchor {key} drifted from the plan")
        if anchor.get("status") != "proposed" or anchor.get("review_ref") is not None:
            issues.append(f"{fragment_id}: anchor must remain proposed and unreviewed")
        selectors = anchor.get("selectors")
        if not isinstance(selectors, list) or len(selectors) != 2:
            issues.append(f"{fragment_id}: anchor must contain exactly member and structural selectors")
            continue
        member = next(
            (
                selector
                for selector in selectors
                if isinstance(selector, dict) and selector.get("type") == "container_member"
            ),
            None,
        )
        structural = next(
            (
                selector
                for selector in selectors
                if isinstance(selector, dict) and selector.get("type") == "structural"
            ),
            None,
        )
        if not isinstance(member, dict) or (
            member.get("member_path") != fragment.get("container_member")
            or member.get("member_sha256") != fragment.get("member_sha256")
        ):
            issues.append(f"{fragment_id}: member selector drifted from the frozen fragment")
        if not isinstance(structural, dict) or structural != {
            "type": "structural",
            "path": ["html", "body", "p:nth-of-type(1)", "sentence:nth-of-type(1)"],
            "scheme": "tos-local-sentence-segmentation-v1",
        }:
            issues.append(f"{fragment_id}: structural selector drifted")
        method = anchor.get("selector_method")
        if not isinstance(method, dict) or (
            method.get("maker_type") != "model"
            or method.get("method") != "first-complete-sentence candidate selection"
        ):
            issues.append(f"{fragment_id}: selector maker/method boundary drifted")
    return issues


def _manifest_index(tree_repo_root: Path) -> dict[str, tuple[dict[str, Any], Path]]:
    source_root = tree_repo_root / "ToS/source-witnesses"
    manifests: dict[str, tuple[dict[str, Any], Path]] = {}
    for path in sorted(source_root.rglob("item.manifest.json")):
        manifest = _load_json(path)
        item_id = manifest.get("item_id")
        if not isinstance(item_id, str):
            continue
        if item_id in manifests:
            raise TranslationSourceError(f"duplicate item manifest for {item_id}")
        manifests[item_id] = (manifest, path)
    return manifests


def _resolve_payload(
    tree_repo_root: Path,
    manifests: dict[str, tuple[dict[str, Any], Path]],
    item_ref: str,
    file_ref: str,
    expected_sha256: str,
    expected_suffix: str,
) -> dict[str, Any]:
    target = manifests.get(item_ref)
    if target is None:
        raise TranslationSourceError(f"no item manifest for {item_ref}")
    manifest, manifest_path = target
    for payload in manifest.get("payload_files", []):
        if not isinstance(payload, dict) or payload.get("file_id") != file_ref:
            continue
        source_path = (manifest_path.parent / str(payload.get("relative_path"))).resolve()
        if not source_path.is_file() or source_path.suffix.lower() != expected_suffix:
            raise TranslationSourceError(f"expected {expected_suffix} source payload is missing: {source_path}")
        actual = _sha256_file(source_path)
        if actual != expected_sha256 or actual != payload.get("sha256"):
            raise TranslationSourceError(f"source payload digest drift for {file_ref}: {actual}")
        rights_ref = manifest.get("rights_ref")
        if not isinstance(rights_ref, str):
            raise TranslationSourceError(f"item manifest has no rights_ref: {item_ref}")
        rights_path = (tree_repo_root / rights_ref).resolve()
        if not _within(rights_path, tree_repo_root) or not rights_path.is_file():
            raise TranslationSourceError(f"rights record is missing or escaped: {rights_ref}")
        rights = _load_json(rights_path)
        scopes = rights.get("scope_refs")
        if not isinstance(scopes, list) or item_ref not in scopes or file_ref not in scopes:
            raise TranslationSourceError(f"rights record does not cover {item_ref} and {file_ref}")
        return {
            "path": source_path,
            "manifest_path": manifest_path.resolve(),
            "manifest_sha256": _sha256_file(manifest_path),
            "rights_path": rights_path,
            "rights_sha256": _sha256_file(rights_path),
            "rights": rights,
            "bytes": source_path.stat().st_size,
        }
    raise TranslationSourceError(f"item {item_ref} has no payload {file_ref}")


def _rights_snapshot(
    tree_repo_root: Path, item_ref: str, file_ref: str, resolved: dict[str, Any]
) -> dict[str, Any]:
    rights = resolved["rights"]
    return {
        "item_ref": item_ref,
        "file_ref": file_ref,
        "rights_id": rights.get("rights_id"),
        "rights_ref": resolved["rights_path"].relative_to(tree_repo_root).as_posix(),
        "rights_sha256": resolved["rights_sha256"],
        "assessment_status": rights.get("assessment_status"),
        "review_status": rights.get("review_status"),
        "visibility": rights.get("visibility"),
        "redistribution_posture": rights.get("redistribution_posture"),
        "derivative_posture": rights.get("derivative_posture"),
    }


def _pdf_inventory(pdfinfo: Path, source_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        (pdfinfo.as_posix(), source_path.as_posix()),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise TranslationSourceError(
            f"pdfinfo failed for visual witness: {completed.stderr.strip()[:240]}"
        )
    fields: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    if not fields.get("Pages", "").isdigit() or int(fields["Pages"]) < 1:
        raise TranslationSourceError("pdfinfo did not report a valid visual-witness page count")
    version_run = subprocess.run(
        (pdfinfo.as_posix(), "-v"),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    combined = "\n".join(
        part for part in (version_run.stdout, version_run.stderr) if part
    ).strip()
    if version_run.returncode != 0 or not combined:
        raise TranslationSourceError("cannot capture pdfinfo version")
    return {
        "page_count": int(fields["Pages"]),
        "pdfinfo_version": combined.splitlines()[0][:240],
        "encrypted": fields.get("Encrypted"),
        "page_size": fields.get("Page size"),
    }


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _artifact_record(root: Path, path: Path) -> dict[str, Any]:
    return {
        "ref": _relative(root, path),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _review_template(
    packet_id: str,
    fragment: dict[str, Any],
    visual_file_sha256: str,
    visual_page: int,
    artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "tos_translation_source_review_template_v1",
        "packet_id": packet_id,
        "fragment_id": fragment["fragment_id"],
        "source_anchor_ref": fragment["source_anchor_ref"],
        "template_status": "awaiting-real-human-input",
        "comparator_visibility": "sealed",
        "source_evidence": {
            "epub_member": fragment["container_member"],
            "epub_member_sha256": fragment["member_sha256"],
            "automated_full_page_text_ref": artifacts["full_page"]["ref"],
            "automated_first_body_paragraph_ref": artifacts["paragraph"]["ref"],
            "automated_sentence_candidate_ref": artifacts["candidate"]["ref"],
            "visual_pdf_file_sha256": visual_file_sha256,
            "visual_pdf_page_proposal": visual_page,
            "visual_mapping_status": "proposed-unverified",
        },
        "pass_1": {
            "performed_by_real_human": False,
            "reviewer_ref": None,
            "reviewed_at_utc": None,
            "visual_mapping_accepted": None,
            "sentence_boundary_accepted": None,
            "exact_transcription_ref": None,
            "uncertain_glyphs": [],
            "correction_notes": [],
        },
        "pass_2": {
            "performed_by_real_human": False,
            "reviewer_ref": None,
            "reviewed_at_utc": None,
            "punctuation_case_orthography_checked": False,
            "boundary_checked": False,
            "lineation_and_page_furniture_checked": False,
            "disagreements_with_pass_1": [],
        },
        "source_acceptance": None,
        "questions": [
            "Does the proposed PDF page show the same source page as the selected EPUB member?",
            "Does the candidate begin and end at the exact first complete sentence in body p1?",
            "What is the exact German spelling, capitalization, punctuation, and historical orthography?",
            "Which glyphs remain visually uncertain and must not be guessed?",
            "Did OCR furniture, page numbers, line breaks, or hyphenation enter the candidate?",
            "Does a separate second pass confirm punctuation, boundary, and transcription?",
        ],
        "authority_boundary": (
            "this is an immutable blank worksheet template, not a human review receipt; "
            "copy it to a review output and record actual human identity and evidence"
        ),
    }


def _read_aloud_template(packet_id: str, fragment: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "tos_translation_read_aloud_template_v1",
        "packet_id": packet_id,
        "fragment_id": fragment["fragment_id"],
        "template_status": "blocked-until-source-transcription-human-double-checked",
        "performed_by_user": False,
        "reviewer_ref": None,
        "reviewed_at_utc": None,
        "accepted_source_transcription_ref": None,
        "observations": {
            "rhythm": None,
            "breath_and_pause": None,
            "stress_and_repetition": None,
            "spoken_strangeness": None,
            "sound_or_sign_recurrence": None,
            "notes": None,
        },
        "authority_boundary": (
            "personal spoken-experience layer only; it remains separate from source "
            "transcription acceptance and general philological review"
        ),
    }


def verify_translation_source_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = _load_json(manifest_path)
    issues = _schema_issues(manifest)
    root = Path(str(manifest.get("artifact_root", ""))).resolve()
    if manifest_path != root / "translation-source-manifest.json":
        issues.append("manifest is not located at its declared artifact root")

    fragments = manifest.get("fragments")
    if isinstance(fragments, list):
        current_set: list[dict[str, Any]] = []
        for fragment in fragments:
            if not isinstance(fragment, dict):
                continue
            artifact_payloads: dict[str, str] = {}
            for key in ("full_page_text", "first_body_paragraph", "sentence_candidate"):
                record = fragment.get(key)
                if not isinstance(record, dict):
                    continue
                path = root / str(record.get("ref", ""))
                if not _within(path, root) or not path.is_file():
                    issues.append(f"{fragment.get('fragment_id')}: missing or escaped {key}")
                    continue
                actual = _sha256_file(path)
                if actual != record.get("sha256") or path.stat().st_size != record.get("bytes"):
                    issues.append(f"{fragment.get('fragment_id')}: fixity drift for {key}")
                artifact_payloads[key] = path.read_text(encoding="utf-8").strip()
            full_page = artifact_payloads.get("full_page_text")
            paragraph = artifact_payloads.get("first_body_paragraph")
            candidate = artifact_payloads.get("sentence_candidate")
            if full_page is not None and paragraph is not None and paragraph not in full_page:
                issues.append(f"{fragment.get('fragment_id')}: first paragraph is not in full page text")
            if paragraph is not None and candidate is not None:
                try:
                    recomputed = first_complete_sentence(paragraph)
                except TranslationSourceError as exc:
                    issues.append(f"{fragment.get('fragment_id')}: {exc}")
                else:
                    if candidate != recomputed:
                        issues.append(f"{fragment.get('fragment_id')}: sentence candidate drifted")
                    hazards = fragment.get("mechanical_hazard_signals")
                    if isinstance(hazards, dict) and hazards != mechanical_candidate_hazards(
                        candidate, str(fragment.get("structural_context", ""))
                    ):
                        issues.append(
                            f"{fragment.get('fragment_id')}: mechanical hazard signals drifted"
                        )
            if fragment.get("visual_pdf_page_proposal") != fragment.get("page_member_index", 0) + 1:
                issues.append(f"{fragment.get('fragment_id')}: visual page proposal drifted")
            current_set.append(
                {
                    "fragment_id": fragment.get("fragment_id"),
                    "member_sha256": fragment.get("member_sha256"),
                    "full_page_text_sha256": (
                        fragment.get("full_page_text", {}).get("sha256")
                        if isinstance(fragment.get("full_page_text"), dict)
                        else None
                    ),
                    "first_body_paragraph_sha256": (
                        fragment.get("first_body_paragraph", {}).get("sha256")
                        if isinstance(fragment.get("first_body_paragraph"), dict)
                        else None
                    ),
                    "sentence_candidate_sha256": (
                        fragment.get("sentence_candidate", {}).get("sha256")
                        if isinstance(fragment.get("sentence_candidate"), dict)
                        else None
                    ),
                    "visual_pdf_page_proposal": fragment.get("visual_pdf_page_proposal"),
                }
            )
        if _canonical_sha256(current_set) != manifest.get("candidate_set_sha256"):
            issues.append("candidate_set_sha256 does not close over current fragment rows")

    for key in ("source_review_template", "read_aloud_template", "metrics"):
        record = manifest.get(key)
        if not isinstance(record, dict):
            continue
        path = root / str(record.get("ref", ""))
        if not _within(path, root) or not path.is_file():
            issues.append(f"missing or escaped {key}")
            continue
        if _sha256_file(path) != record.get("sha256") or path.stat().st_size != record.get("bytes"):
            issues.append(f"fixity drift for {key}")

    receipt_ref = manifest.get("receipt_ref")
    receipt_path = root / str(receipt_ref or "")
    if not _within(receipt_path, root) or not receipt_path.is_file():
        issues.append("source packet receipt is missing or escaped")
    else:
        receipt = _load_json(receipt_path)
        if receipt.get("packet_id") != manifest.get("packet_id"):
            issues.append("source packet receipt packet_id drifted")
        if receipt.get("status") != "awaiting-source-visible-human-review":
            issues.append("source packet receipt does not retain the human-review boundary")

    comparator = manifest.get("recognized_comparator")
    if not isinstance(comparator, dict) or comparator.get("visibility") != "sealed":
        issues.append("recognized comparator is not sealed in the packet")
    elif comparator.get("content_consulted") is not False or comparator.get("content_emitted") is not False:
        issues.append("packet claims recognized comparator content access")

    if issues:
        raise TranslationSourceError("invalid translation source manifest: " + "; ".join(issues))
    return manifest


def verify_translation_source_inspection(
    inspection_path: Path, manifest_path: Path
) -> dict[str, Any]:
    """Verify one advisory source-visible selector inspection against its packet."""

    inspection_path = inspection_path.resolve()
    manifest_path = manifest_path.resolve()
    manifest = verify_translation_source_manifest(manifest_path)
    inspection = _load_json(inspection_path)
    issues = _schema_issues(inspection, INSPECTION_SCHEMA_PATH)

    source_packet = inspection.get("source_packet")
    if not isinstance(source_packet, dict):
        source_packet = {}
    expected_packet_fields = {
        "packet_id": manifest.get("packet_id"),
        "manifest_sha256": _sha256_file(manifest_path),
        "candidate_set_sha256": manifest.get("candidate_set_sha256"),
        "sample_plan_sha256": manifest.get("sample_plan_sha256"),
    }
    for key, expected in expected_packet_fields.items():
        if source_packet.get(key) != expected:
            issues.append(f"source_packet.{key} does not match the frozen source packet")

    visual_review = inspection.get("visual_review")
    if not isinstance(visual_review, dict) or visual_review.get(
        "visual_witness_sha256"
    ) != manifest.get("visual_witness", {}).get("file_sha256"):
        issues.append("visual_review does not identify the source packet's visual witness")

    expected_lanes = {
        key: manifest.get("lanes", {}).get(key)
        for key in ("human_only", "ai_only", "ai_human")
    }
    if inspection.get("translation_lanes") != expected_lanes:
        issues.append("translation lanes drifted from the source packet boundary")
    if inspection.get("recognized_comparator_visibility") != manifest.get(
        "recognized_comparator", {}
    ).get("visibility"):
        issues.append("recognized comparator visibility drifted")

    records = inspection.get("records")
    manifest_rows = manifest.get("fragments")
    if not isinstance(records, list) or not isinstance(manifest_rows, list):
        records = []
        manifest_rows = []
    if len(records) != len(manifest_rows):
        issues.append("inspection record count does not match the source packet")

    decision_counts = {
        "accept_with_limits": 0,
        "reject": 0,
        "uncertain": 0,
        "abstain": 0,
    }
    failure_mode_counts = {
        "heading_selected": 0,
        "page_start_tail": 0,
        "ocr_contamination": 0,
        "boundary_uncertain": 0,
        "usable_only_with_limits": 0,
    }
    seen_ids: set[object] = set()
    for index, (record, fragment) in enumerate(zip(records, manifest_rows, strict=False)):
        if not isinstance(record, dict) or not isinstance(fragment, dict):
            continue
        fragment_id = fragment.get("fragment_id")
        if record.get("fragment_id") in seen_ids:
            issues.append(f"records[{index}] repeats fragment_id {record.get('fragment_id')}")
        seen_ids.add(record.get("fragment_id"))
        expected_fields = {
            "fragment_id": fragment_id,
            "source_anchor_ref": fragment.get("source_anchor_ref"),
            "visual_pdf_page": fragment.get("visual_pdf_page_proposal"),
            "sentence_candidate_ref": fragment.get("sentence_candidate", {}).get("ref"),
            "sentence_candidate_sha256": fragment.get("sentence_candidate", {}).get(
                "sha256"
            ),
        }
        for key, expected in expected_fields.items():
            if record.get(key) != expected:
                issues.append(f"records[{index}].{key} drifted from {fragment_id}")

        decision = record.get("decision")
        decision_key = {
            "accept-with-limits": "accept_with_limits",
            "reject": "reject",
            "uncertain": "uncertain",
            "abstain": "abstain",
        }.get(decision)
        if decision_key is not None:
            decision_counts[decision_key] += 1
        signals = record.get("signals")
        signal_set = set(signals) if isinstance(signals, list) else set()
        if "visual-page-correspondence-observed" not in signal_set:
            issues.append(f"{fragment_id}: exhaustive visual inspection lacks page correspondence")
        if decision == "accept-with-limits" and (
            "sentence-boundary-visually-plausible" not in signal_set
        ):
            issues.append(f"{fragment_id}: limited acceptance lacks a plausible boundary signal")
        if decision == "reject" and not signal_set.intersection(
            {"heading-selected", "page-start-tail", "ocr-contamination"}
        ):
            issues.append(f"{fragment_id}: rejection lacks an observed failure mode")
        if decision == "uncertain" and not signal_set.intersection(
            {"page-start-boundary-unverified", "transcription-uncertain"}
        ):
            issues.append(f"{fragment_id}: uncertainty lacks an uncertainty signal")

        failure_mode_counts["heading_selected"] += int("heading-selected" in signal_set)
        failure_mode_counts["page_start_tail"] += int("page-start-tail" in signal_set)
        failure_mode_counts["ocr_contamination"] += int("ocr-contamination" in signal_set)
        failure_mode_counts["boundary_uncertain"] += int(
            "page-start-boundary-unverified" in signal_set
        )
        failure_mode_counts["usable_only_with_limits"] += int(
            decision == "accept-with-limits"
        )

    summary = inspection.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    if summary.get("record_count") != len(records):
        issues.append("summary.record_count does not match inspection records")
    if summary.get("decision_counts") != decision_counts:
        issues.append("summary.decision_counts does not match inspection records")
    if summary.get("failure_mode_counts") != failure_mode_counts:
        issues.append("summary.failure_mode_counts does not match inspection signals")
    if sum(decision_counts.values()) != len(records):
        issues.append("not every inspection record has a recognized decision")

    if issues:
        raise TranslationSourceError(
            "invalid translation source model inspection: " + "; ".join(issues)
        )
    return inspection


def materialize_translation_source(
    tree_repo_root: Path,
    sample_plan_path: Path,
    anchors_path: Path,
    packet_id: str,
    visual_item_ref: str,
    visual_file_ref: str,
    visual_file_sha256: str,
    *,
    shared_root: Path = DEFAULT_SHARED_ROOT,
    pdfinfo: Path = Path("/usr/bin/pdfinfo"),
    invocation: list[str],
) -> dict[str, Any]:
    """Materialize and verify one immutable pre-translation source packet."""

    if not PACKET_ID_RE.fullmatch(packet_id):
        raise TranslationSourceError(
            "packet-id must use lowercase letters, digits, dot, underscore, and hyphen"
        )
    if not SHA256_RE.fullmatch(visual_file_sha256):
        raise TranslationSourceError("visual-file-sha256 must be a lowercase SHA-256 digest")
    tree_repo_root = tree_repo_root.resolve()
    sample_plan_path = sample_plan_path.resolve()
    anchors_path = anchors_path.resolve()
    shared_root = shared_root.resolve()
    if not _within(shared_root, DEFAULT_SHARED_ROOT):
        raise TranslationSourceError(f"shared source root must stay under {DEFAULT_SHARED_ROOT}")
    packet_root = shared_root / packet_id
    if packet_root.exists():
        raise TranslationSourceError(f"source packet path already exists: {packet_root}")

    plan = _load_json(sample_plan_path)
    plan_issues = validate_translation_plan(plan)
    anchors = _load_jsonl(anchors_path)
    plan_issues.extend(_validate_anchors(plan, anchors))
    comparator = plan.get("recognized_comparator", {})
    if visual_item_ref == comparator.get("item_ref"):
        plan_issues.append("visual witness cannot be the sealed recognized comparator")
    if plan_issues:
        raise TranslationSourceError("invalid frozen translation plan: " + "; ".join(plan_issues))

    packet_root.mkdir(parents=True, exist_ok=False)
    receipt_path = packet_root / "translation-source.receipt.json"
    receipt: dict[str, Any] = {
        "schema_version": "tos_translation_source_packet_receipt_v1",
        "packet_id": packet_id,
        "status": "running",
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "invocation": invocation,
        "sample_plan_ref": sample_plan_path.as_posix(),
        "sample_plan_sha256": _sha256_file(sample_plan_path),
        "anchors_ref": anchors_path.as_posix(),
        "anchors_sha256": _sha256_file(anchors_path),
        "runner_sha256": _sha256_file(Path(__file__)),
        "errors": [],
    }
    _write_json(receipt_path, receipt)
    started = time.perf_counter()

    try:
        manifests = _manifest_index(tree_repo_root)
        source = _resolve_payload(
            tree_repo_root,
            manifests,
            str(plan["source_item_ref"]),
            str(plan["source_file_ref"]),
            str(plan["source_file_sha256"]),
            ".epub",
        )
        visual = _resolve_payload(
            tree_repo_root,
            manifests,
            visual_item_ref,
            visual_file_ref,
            visual_file_sha256,
            ".pdf",
        )
        pdf = _pdf_inventory(pdfinfo, visual["path"])

        fragment_rows: list[dict[str, Any]] = []
        review_templates: list[dict[str, Any]] = []
        read_aloud_templates: list[dict[str, Any]] = []
        with zipfile.ZipFile(source["path"]) as archive:
            archive_members = set(archive.namelist())
            for fragment in plan["fragments"]:
                member_path = str(fragment["container_member"])
                if member_path not in archive_members:
                    raise TranslationSourceError(f"EPUB member is missing: {member_path}")
                raw = archive.read(member_path)
                member_sha256 = _sha256_bytes(raw)
                if member_sha256 != fragment["member_sha256"]:
                    raise TranslationSourceError(
                        f"EPUB member digest drift for {member_path}: {member_sha256}"
                    )
                full_page = extract_xhtml_text(raw)
                paragraph = extract_first_body_paragraph(raw)
                if not full_page.strip() or not paragraph:
                    raise TranslationSourceError(f"empty visible source extraction for {member_path}")
                candidate = first_complete_sentence(paragraph)

                fragment_id = str(fragment["fragment_id"])
                full_page_path = packet_root / "derived/full-page" / f"{fragment_id}.txt"
                paragraph_path = (
                    packet_root / "derived/first-body-paragraph" / f"{fragment_id}.txt"
                )
                candidate_path = (
                    packet_root / "derived/sentence-candidates" / f"{fragment_id}.txt"
                )
                _write_text(full_page_path, full_page)
                _write_text(paragraph_path, paragraph)
                _write_text(candidate_path, candidate)
                artifacts = {
                    "full_page": _artifact_record(packet_root, full_page_path),
                    "paragraph": _artifact_record(packet_root, paragraph_path),
                    "candidate": _artifact_record(packet_root, candidate_path),
                }
                visual_page = int(fragment["page_member_index"]) + 1
                if visual_page > int(pdf["page_count"]):
                    raise TranslationSourceError(
                        f"visual page proposal {visual_page} exceeds PDF page count for {fragment_id}"
                    )
                row = {
                    "fragment_id": fragment_id,
                    "source_anchor_ref": fragment["source_anchor_ref"],
                    "container_member": member_path,
                    "member_sha256": member_sha256,
                    "page_member_index": fragment["page_member_index"],
                    "printed_page": fragment["printed_page"],
                    "structural_context": fragment["structural_context"],
                    "strata": fragment["strata"],
                    "analysis_tags": fragment["analysis_tags"],
                    "full_page_text": artifacts["full_page"],
                    "first_body_paragraph": artifacts["paragraph"],
                    "sentence_candidate": artifacts["candidate"],
                    "mechanical_hazard_signals": mechanical_candidate_hazards(
                        candidate, str(fragment["structural_context"])
                    ),
                    "selector_method": "tos-local-sentence-segmentation-v1",
                    "selector_maker_type": "software",
                    "candidate_status": "software-proposal-unreviewed",
                    "source_transcription_status": "not-started",
                    "human_source_acceptance": False,
                    "visual_pdf_page_proposal": visual_page,
                    "visual_mapping_status": "proposed-unverified",
                }
                fragment_rows.append(row)
                review_templates.append(
                    _review_template(
                        packet_id,
                        fragment,
                        visual_file_sha256,
                        visual_page,
                        artifacts,
                    )
                )
                read_aloud_templates.append(_read_aloud_template(packet_id, fragment))

        review_path = packet_root / "reviews/source-review.template.jsonl"
        read_aloud_path = packet_root / "reviews/read-aloud.template.jsonl"
        _write_jsonl(review_path, review_templates)
        _write_jsonl(read_aloud_path, read_aloud_templates)
        review_record = _artifact_record(packet_root, review_path)
        read_aloud_record = _artifact_record(packet_root, read_aloud_path)

        candidate_projection = [
            {
                "fragment_id": row["fragment_id"],
                "member_sha256": row["member_sha256"],
                "full_page_text_sha256": row["full_page_text"]["sha256"],
                "first_body_paragraph_sha256": row["first_body_paragraph"]["sha256"],
                "sentence_candidate_sha256": row["sentence_candidate"]["sha256"],
                "visual_pdf_page_proposal": row["visual_pdf_page_proposal"],
            }
            for row in fragment_rows
        ]
        elapsed = time.perf_counter() - started
        derived_bytes = sum(
            path.stat().st_size
            for path in packet_root.rglob("*")
            if path.is_file() and path != receipt_path
        )
        metrics = {
            "schema_version": "tos_translation_source_packet_metrics_v1",
            "packet_id": packet_id,
            "fragment_count": len(fragment_rows),
            "wall_seconds": elapsed,
            "fragments_per_second": len(fragment_rows) / elapsed if elapsed else None,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "source_payload_bytes": source["bytes"] + visual["bytes"],
            "derived_artifact_bytes_before_manifest": derived_bytes,
            "mechanical_member_fixity_count": len(fragment_rows),
            "mechanical_candidate_count": len(fragment_rows),
            "quality": {
                "status": "not-computable",
                "reason": "no source-visible human transcription or boundary acceptance exists",
            },
            "human_cost": {
                "status": "not-measured",
                "reason": "blank templates were prepared but no real human pass occurred",
            },
            "authority_boundary": AUTHORITY_BOUNDARY,
        }
        metrics_path = packet_root / "metrics/source-preparation.json"
        _write_json(metrics_path, metrics)
        metrics_record = _artifact_record(packet_root, metrics_path)

        manifest = {
            "schema_version": "tos_translation_source_packet_manifest_v1",
            "packet_id": packet_id,
            "experiment_id": "tos-translation-foundation-v1",
            "status": "awaiting-source-visible-human-review",
            "created_at_utc": receipt["started_at_utc"],
            "artifact_root": packet_root.as_posix(),
            "sample_plan_ref": sample_plan_path.as_posix(),
            "sample_plan_sha256": receipt["sample_plan_sha256"],
            "anchors_ref": anchors_path.as_posix(),
            "anchors_sha256": receipt["anchors_sha256"],
            "source_witness": {
                "item_ref": plan["source_item_ref"],
                "file_ref": plan["source_file_ref"],
                "file_sha256": plan["source_file_sha256"],
                "local_path": source["path"].as_posix(),
                "item_manifest_ref": source["manifest_path"].relative_to(
                    tree_repo_root
                ).as_posix(),
                "item_manifest_sha256": source["manifest_sha256"],
                "container": "epub-zip",
                "role": "automatic-ocr-derivative-not-source-truth",
            },
            "visual_witness": {
                "item_ref": visual_item_ref,
                "file_ref": visual_file_ref,
                "file_sha256": visual_file_sha256,
                "local_path": visual["path"].as_posix(),
                "item_manifest_ref": visual["manifest_path"].relative_to(
                    tree_repo_root
                ).as_posix(),
                "item_manifest_sha256": visual["manifest_sha256"],
                "container": "pdf",
                "role": "source-visible-scan-witness",
                "page_count": pdf["page_count"],
                "pdfinfo_version": pdf["pdfinfo_version"],
                "page_mapping": {
                    "method": "epub-page-member-index-plus-one",
                    "offset": 1,
                    "status": "proposed-unverified",
                },
            },
            "rights_snapshots": [
                _rights_snapshot(
                    tree_repo_root,
                    str(plan["source_item_ref"]),
                    str(plan["source_file_ref"]),
                    source,
                ),
                _rights_snapshot(
                    tree_repo_root,
                    visual_item_ref,
                    visual_file_ref,
                    visual,
                ),
            ],
            "selector_method": {
                "plan_scheme": "tos-local-sentence-segmentation-v1",
                "implementation": "first-body-p punctuation-boundary software proposal",
                "maker_type": "software",
                "status": "unreviewed",
            },
            "recognized_comparator": {
                "expression_ref": comparator["expression_ref"],
                "item_ref": comparator["item_ref"],
                "visibility": "sealed",
                "content_consulted": False,
                "content_emitted": False,
                "reveal_stage": comparator["reveal_stage"],
            },
            "lanes": {
                "human_only": "awaiting-real-human-source-input",
                "ai_only": "blocked-pending-human-source-acceptance",
                "ai_human": "blocked-pending-independent-drafts",
                "recognized_comparator": "sealed",
            },
            "fragment_count": len(fragment_rows),
            "fragments": fragment_rows,
            "candidate_set_sha256": _canonical_sha256(candidate_projection),
            "source_review_template": review_record,
            "read_aloud_template": read_aloud_record,
            "metrics": metrics_record,
            "receipt_ref": _relative(packet_root, receipt_path),
            "authority_boundary": AUTHORITY_BOUNDARY,
        }
        manifest_path = packet_root / "translation-source-manifest.json"
        _write_json(manifest_path, manifest)

        receipt["status"] = "awaiting-source-visible-human-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["source_file_sha256"] = plan["source_file_sha256"]
        receipt["visual_file_sha256"] = visual_file_sha256
        receipt["fragment_count"] = len(fragment_rows)
        receipt["candidate_set_sha256"] = manifest["candidate_set_sha256"]
        receipt["manifest_ref"] = _relative(packet_root, manifest_path)
        receipt["manifest_sha256"] = _sha256_file(manifest_path)
        receipt["errors"] = []
        _write_json(receipt_path, receipt)
        return verify_translation_source_manifest(manifest_path)
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)]
        _write_json(receipt_path, receipt)
        if isinstance(exc, TranslationSourceError):
            raise
        raise TranslationSourceError(str(exc)) from exc
