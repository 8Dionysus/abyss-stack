#!/usr/bin/env python3
"""Materialize the blind page-triplet interface for real German source review."""

from __future__ import annotations

import html
import json
import struct
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from translation_source import (
    DEFAULT_SHARED_ROOT,
    PACKET_ID_RE,
    TranslationSourceError,
    _artifact_record,
    _canonical_sha256,
    _load_json,
    _manifest_index,
    _pdf_inventory,
    _relative,
    _resolve_payload,
    _rights_snapshot,
    _schema_issues,
    _sha256_bytes,
    _sha256_file,
    _utc_now,
    _within,
    _write_json,
    _write_jsonl,
)


PART_ROOT = Path(__file__).resolve().parent
MANIFEST_SCHEMA_PATH = (
    PART_ROOT / "schemas/translation-source-review-manifest.schema.json"
)
PLAN_SCHEMA_REF = "ToS/contracts/translation-source-review-plan.schema.json"
AUTHORITY_BOUNDARY = (
    "private source-visible interface and blank review templates only; no human "
    "pass, German transcription, translation draft, or source acceptance is implied"
)


class TranslationSourceReviewError(TranslationSourceError):
    """Raised when the page-triplet human-review packet is unsafe or incomplete."""


def _plan_issues(
    tree_repo_root: Path, review_plan_path: Path, plan: dict[str, Any]
) -> list[str]:
    schema_path = tree_repo_root / PLAN_SCHEMA_REF
    try:
        schema = _load_json(schema_path)
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return [f"cannot load Tree of Sophia review-plan contract: {exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[str] = []
    for error in sorted(
        validator.iter_errors(plan), key=lambda item: list(item.absolute_path)
    ):
        location = "".join(f"[{part!r}]" for part in error.absolute_path) or "<root>"
        issues.append(f"{location}: {error.message}")

    if not _within(review_plan_path, tree_repo_root):
        issues.append("review plan escaped the Tree of Sophia repository")
    supersedes = plan.get("supersedes")
    if not isinstance(supersedes, dict):
        return issues
    for ref_key, digest_key in (
        ("v1_plan_ref", "v1_plan_sha256"),
        ("v1_inspection_ref", "v1_inspection_sha256"),
    ):
        target = tree_repo_root / str(supersedes.get(ref_key, ""))
        if not _within(target, tree_repo_root) or not target.is_file():
            issues.append(f"{ref_key} is missing or escaped")
        elif _sha256_file(target) != supersedes.get(digest_key):
            issues.append(f"{digest_key} does not match {ref_key}")
    inspection_path = tree_repo_root / str(supersedes.get("v1_inspection_ref", ""))
    if inspection_path.is_file():
        inspection = _load_json(inspection_path)
        if inspection.get("inspection_id") != supersedes.get("v1_inspection_id"):
            issues.append("v1 inspection identity drifted")
        if inspection.get("promotion_authorized") is not False:
            issues.append("v1 inspection unexpectedly authorizes promotion")

    units = plan.get("units")
    if isinstance(units, list):
        expected_ids = [
            f"tos-translation-source-review-v2-{index:03d}"
            for index in range(1, 31)
        ]
        if [unit.get("review_unit_id") for unit in units if isinstance(unit, dict)] != expected_ids:
            issues.append("review unit IDs are not the exact ordered 001..030 set")
        for unit in units:
            if not isinstance(unit, dict):
                continue
            context = unit.get("visual_context")
            if not isinstance(context, dict):
                continue
            current = context.get("current_pdf_page")
            if (
                not isinstance(current, int)
                or context.get("previous_pdf_page") != current - 1
                or context.get("next_pdf_page") != current + 1
            ):
                issues.append(f"{unit.get('review_unit_id')}: visual context is not a page triplet")
            if unit.get("reuse_v1_candidate") is not False:
                issues.append(f"{unit.get('review_unit_id')}: v1 candidate reuse is forbidden")
            if unit.get("human_source_acceptance") is not False:
                issues.append(f"{unit.get('review_unit_id')}: absent human review was claimed")
    return issues


def _pdftoppm_version(command: Path) -> str:
    completed = subprocess.run(
        (command.as_posix(), "-v"),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    combined = "\n".join(
        part for part in (completed.stdout, completed.stderr) if part
    ).strip()
    if completed.returncode != 0 or not combined:
        raise TranslationSourceReviewError("cannot capture pdftoppm version")
    return combined.splitlines()[0][:240]


def _png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise TranslationSourceReviewError(f"invalid PNG header: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width < 1 or height < 1:
        raise TranslationSourceReviewError(f"invalid PNG dimensions: {path}")
    return width, height


def _render_page(
    command: Path, pdf_path: Path, output_path: Path, page: int
) -> None:
    prefix = output_path.with_suffix("")
    completed = subprocess.run(
        (
            command.as_posix(),
            "-f",
            str(page),
            "-l",
            str(page),
            "-r",
            "180",
            "-png",
            "-singlefile",
            pdf_path.as_posix(),
            prefix.as_posix(),
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise TranslationSourceReviewError(
            f"pdftoppm failed for PDF page {page}: {completed.stderr.strip()[:240]}"
        )
    if not output_path.is_file():
        raise TranslationSourceReviewError(
            f"pdftoppm returned success without expected page artifact {output_path}"
        )
    _png_dimensions(output_path)


def _page_ref(page: int) -> str:
    return f"pages/pdf-page-{page:04d}.png"


def _review_template(
    packet_id: str, unit: dict[str, Any], questions: list[str]
) -> dict[str, Any]:
    context = unit["visual_context"]
    return {
        "schema_version": "tos_translation_source_human_review_template_v2",
        "packet_id": packet_id,
        "review_unit_id": unit["review_unit_id"],
        "context_anchor_ref": unit["context_anchor_ref"],
        "template_status": "awaiting-real-human-input",
        "source_pages": {
            "previous": _page_ref(context["previous_pdf_page"]),
            "current": _page_ref(context["current_pdf_page"]),
            "next": _page_ref(context["next_pdf_page"]),
        },
        "v1_candidate_visible": False,
        "recognized_comparator_visible": False,
        "pass_1": {
            "performed_by_real_human": False,
            "reviewer_ref": None,
            "reviewed_at_utc": None,
            "layout_role": None,
            "begins_on_previous_page": None,
            "continues_on_next_page": None,
            "boundary_start_note": None,
            "boundary_end_note": None,
            "diplomatic_transcription": None,
            "uncertain_glyphs": [],
            "decision": None,
            "notes": [],
        },
        "pass_2": {
            "performed_by_real_human": False,
            "reviewer_ref": None,
            "reviewed_at_utc": None,
            "independent_diplomatic_transcription": None,
            "punctuation_case_orthography_checked": False,
            "boundary_checked": False,
            "lineation_and_page_furniture_checked": False,
            "decision": None,
            "disagreements_with_pass_1": [],
        },
        "source_acceptance": None,
        "questions": questions,
        "authority_boundary": (
            "immutable blank template only; copy to a new review output and record "
            "actual human identity, attestation, source-visible decisions, and time"
        ),
    }


def _workbook_html(
    packet_id: str,
    units: list[dict[str, Any]],
    *,
    pass_number: int,
    questions: list[str],
) -> str:
    if pass_number not in {1, 2}:
        raise TranslationSourceReviewError("workbook pass must be 1 or 2")
    title = (
        "Pass 1: layout, boundary, and diplomatic transcription"
        if pass_number == 1
        else "Pass 2: independent punctuation and boundary verification"
    )
    unit_sections: list[str] = []
    for unit in units:
        context = unit["visual_context"]
        unit_id = html.escape(str(unit["review_unit_id"]))
        pages = []
        for role in ("previous", "current", "next"):
            page = context[f"{role}_pdf_page"]
            role_class = " current" if role == "current" else ""
            pages.append(
                f'<figure class="page{role_class}"><figcaption>{role.title()} PDF page '
                f'{page}</figcaption><a href="../{_page_ref(page)}" target="_blank">'
                f'<img loading="lazy" src="../{_page_ref(page)}" '
                f'alt="{role.title()} source page {page}"></a></figure>'
            )
        if pass_number == 1:
            fields = """
            <label>Layout role
              <select name="layout_role">
                <option value="">Select only after looking</option>
                <option>heading</option><option>section-marker</option>
                <option>prose</option><option>quotation</option>
                <option>continuation</option><option>page-furniture</option>
                <option>uncertain</option>
              </select>
            </label>
            <label><input type="checkbox" name="begins_on_previous_page">
              Target begins on the previous page</label>
            <label><input type="checkbox" name="continues_on_next_page">
              Target continues on the next page</label>
            <label>Exact visible start note<input name="boundary_start_note"></label>
            <label>Exact visible end note<input name="boundary_end_note"></label>
            <label>Diplomatic German transcription
              <textarea name="diplomatic_transcription" rows="6"></textarea>
            </label>
            <label>Uncertain glyphs or joins
              <textarea name="uncertain_glyphs" rows="3"></textarea>
            </label>
            <label>Decision
              <select name="decision"><option value="">Choose</option>
                <option>accept</option><option>accept-with-limits</option>
                <option>reject</option><option>defer</option>
              </select>
            </label>
            """
        else:
            fields = """
            <label>Independent diplomatic German transcription
              <textarea name="independent_diplomatic_transcription" rows="6"></textarea>
            </label>
            <label><input type="checkbox" name="punctuation_case_orthography_checked">
              Punctuation, case, and historical orthography checked</label>
            <label><input type="checkbox" name="boundary_checked">
              Start and end boundary checked across all three pages</label>
            <label><input type="checkbox" name="lineation_and_page_furniture_checked">
              Lineation, hyphenation, and page furniture checked</label>
            <label>Disagreements or uncertainty
              <textarea name="disagreements_with_pass_1" rows="3"></textarea>
            </label>
            <label>Decision
              <select name="decision"><option value="">Choose</option>
                <option>confirm</option><option>revise</option>
                <option>reject</option><option>defer</option>
              </select>
            </label>
            """
        unit_sections.append(
            f'<section class="unit" data-unit="{unit_id}"><h2>{unit_id}</h2>'
            '<p class="blind">The rejected v1 candidate and model route are hidden. '
            'Judge only the visible source triplet.</p>'
            f'<div class="triplet">{"".join(pages)}</div>{fields}</section>'
        )
    question_items = "".join(f"<li>{html.escape(question)}</li>" for question in questions)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(title)}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1500px;margin:auto;padding:1rem;background:#151515;color:#eee}}
h1,h2{{color:#f0d78c}} .notice,.identity,.unit{{border:1px solid #555;border-radius:8px;padding:1rem;margin:1rem 0;background:#202020}}
.triplet{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem;align-items:start}}
.page img{{width:100%;height:auto;background:white}} .page.current{{outline:4px solid #d6a928}}
label{{display:block;margin:.8rem 0}} input[type=text],input:not([type]),select,textarea{{width:100%;box-sizing:border-box;background:#111;color:#eee;border:1px solid #777;padding:.5rem}}
.blind{{color:#bbb}} button{{font-size:1rem;padding:.8rem 1.2rem;background:#d6a928;border:0;border-radius:5px}}
@media(max-width:900px){{.triplet{{grid-template-columns:1fr}}}}
</style></head>
<body>
<h1>{html.escape(title)}</h1>
<div class="notice"><p>Packet: {html.escape(packet_id)}. This is a local worksheet.
It does not submit or accept anything. Export creates a draft JSON file only.
The recognized translation and rejected automatic candidate are absent.</p>
<ol>{question_items}</ol></div>
<div class="identity">
<label>Human reviewer reference<input id="reviewer_ref"></label>
<label><input type="checkbox" id="human_attestation">
I attest that this pass was performed by a real human looking at the source pages.</label>
</div>
{"".join(unit_sections)}
<button type="button" onclick="downloadDraft()">Download pass {pass_number} draft JSON</button>
<script>
function downloadDraft(){{
  const rows=[...document.querySelectorAll('.unit')].map(section=>{{
    const row={{review_unit_id:section.dataset.unit}};
    for(const field of section.querySelectorAll('input,select,textarea')){{
      row[field.name]=field.type==='checkbox'?field.checked:field.value;
    }}
    return row;
  }});
  const payload={{
    schema_version:'tos_translation_source_human_review_draft_v2',
    packet_id:{json.dumps(packet_id)},
    pass_number:{pass_number},
    performed_by_real_human:document.getElementById('human_attestation').checked,
    reviewer_ref:document.getElementById('reviewer_ref').value||null,
    exported_at_utc:new Date().toISOString(),
    rows,
    source_acceptance:null,
    authority_boundary:'downloaded worksheet draft only; independent review validation and adjudication still required'
  }};
  const blob=new Blob([JSON.stringify(payload,null,2)+'\\n'],{{type:'application/json'}});
  const link=document.createElement('a'); link.href=URL.createObjectURL(blob);
  link.download='source-review-pass-{pass_number}.draft.json'; link.click();
  URL.revokeObjectURL(link.href);
}}
</script></body></html>
"""


def verify_translation_source_review_manifest(
    manifest_path: Path,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = _load_json(manifest_path)
    issues = _schema_issues(manifest, MANIFEST_SCHEMA_PATH)
    root = Path(str(manifest.get("artifact_root", ""))).resolve()
    if manifest_path != root / "translation-source-review-manifest.json":
        issues.append("manifest is not at its declared artifact root")

    plan_path = Path(str(manifest.get("review_plan_ref", ""))).resolve()
    if not plan_path.is_file() or _sha256_file(plan_path) != manifest.get(
        "review_plan_sha256"
    ):
        issues.append("review plan is missing or its digest drifted")
        plan: dict[str, Any] = {}
    else:
        plan = _load_json(plan_path)

    page_rows = manifest.get("pages")
    page_by_number: dict[int, dict[str, Any]] = {}
    current_projection: list[dict[str, Any]] = []
    if isinstance(page_rows, list):
        for row in page_rows:
            if not isinstance(row, dict) or not isinstance(row.get("pdf_page"), int):
                continue
            page = row["pdf_page"]
            if page in page_by_number:
                issues.append(f"duplicate rendered PDF page {page}")
            page_by_number[page] = row
            artifact = row.get("artifact", {})
            path = root / str(artifact.get("ref", ""))
            if not _within(path, root) or not path.is_file():
                issues.append(f"missing or escaped render for PDF page {page}")
                continue
            width, height = _png_dimensions(path)
            actual_sha = _sha256_file(path)
            if (
                actual_sha != artifact.get("sha256")
                or path.stat().st_size != artifact.get("bytes")
                or width != row.get("png_width")
                or height != row.get("png_height")
            ):
                issues.append(f"fixity or PNG metadata drift for PDF page {page}")
            current_projection.append(
                {
                    "pdf_page": page,
                    "sha256": actual_sha,
                    "bytes": path.stat().st_size,
                    "png_width": width,
                    "png_height": height,
                }
            )
    if current_projection != sorted(current_projection, key=lambda row: row["pdf_page"]):
        issues.append("rendered pages are not in ascending PDF-page order")
    if _canonical_sha256(current_projection) != manifest.get("page_set_sha256"):
        issues.append("page_set_sha256 does not close over rendered pages")
    if manifest.get("render", {}).get("unique_page_count") != len(page_by_number):
        issues.append("render.unique_page_count does not match page records")

    units = manifest.get("units")
    plan_units = plan.get("units") if isinstance(plan, dict) else None
    if not isinstance(units, list) or not isinstance(plan_units, list):
        units = []
        plan_units = []
    if len(units) != len(plan_units):
        issues.append("manifest units do not close over the review plan")
    for row, plan_unit in zip(units, plan_units, strict=False):
        if not isinstance(row, dict) or not isinstance(plan_unit, dict):
            continue
        context = plan_unit.get("visual_context", {})
        expected = {
            "review_unit_id": plan_unit.get("review_unit_id"),
            "context_anchor_ref": plan_unit.get("context_anchor_ref"),
            "previous_page_ref": _page_ref(context.get("previous_pdf_page")),
            "current_page_ref": _page_ref(context.get("current_pdf_page")),
            "next_page_ref": _page_ref(context.get("next_pdf_page")),
            "v1_candidate_visible": False,
            "review_status": "not-started",
            "human_source_acceptance": False,
        }
        if row != expected:
            issues.append(f"{plan_unit.get('review_unit_id')}: review unit projection drifted")
        for key in ("previous_pdf_page", "current_pdf_page", "next_pdf_page"):
            if context.get(key) not in page_by_number:
                issues.append(f"{plan_unit.get('review_unit_id')}: missing {key} render")

    for key in ("pass_1_workbook", "pass_2_workbook", "review_template"):
        artifact = manifest.get(key)
        if not isinstance(artifact, dict):
            continue
        path = root / str(artifact.get("ref", ""))
        if (
            not _within(path, root)
            or not path.is_file()
            or _sha256_file(path) != artifact.get("sha256")
            or path.stat().st_size != artifact.get("bytes")
        ):
            issues.append(f"fixity drift for {key}")

    template = manifest.get("review_template", {})
    template_path = root / str(template.get("ref", ""))
    if template_path.is_file():
        rows = [
            json.loads(line)
            for line in template_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        if len(rows) != 30:
            issues.append("blank review template must contain exactly 30 rows")
        for row in rows:
            if (
                row.get("pass_1", {}).get("performed_by_real_human") is not False
                or row.get("pass_2", {}).get("performed_by_real_human") is not False
                or row.get("source_acceptance") is not None
            ):
                issues.append("blank review template claims human work")

    receipt_path = root / str(manifest.get("receipt_ref", ""))
    if not _within(receipt_path, root) or not receipt_path.is_file():
        issues.append("review packet receipt is missing or escaped")
    else:
        receipt = _load_json(receipt_path)
        if receipt.get("status") != "awaiting-real-human-source-review":
            issues.append("review packet receipt does not retain the human stop line")
    comparator = manifest.get("recognized_comparator")
    if not isinstance(comparator, dict) or (
        comparator.get("visibility") != "sealed"
        or comparator.get("content_consulted") is not False
        or comparator.get("content_emitted") is not False
    ):
        issues.append("recognized comparator boundary drifted")

    if issues:
        raise TranslationSourceReviewError(
            "invalid translation source review manifest: " + "; ".join(issues)
        )
    return manifest


def materialize_translation_source_review(
    tree_repo_root: Path,
    review_plan_path: Path,
    packet_id: str,
    *,
    shared_root: Path = DEFAULT_SHARED_ROOT,
    pdftoppm: Path = Path("/usr/bin/pdftoppm"),
    pdfinfo: Path = Path("/usr/bin/pdfinfo"),
    invocation: list[str],
) -> dict[str, Any]:
    """Create an immutable 30-unit blind human-review interface."""

    if not PACKET_ID_RE.fullmatch(packet_id):
        raise TranslationSourceReviewError("invalid review packet ID")
    tree_repo_root = tree_repo_root.resolve()
    review_plan_path = review_plan_path.resolve()
    shared_root = shared_root.resolve()
    if not _within(shared_root, DEFAULT_SHARED_ROOT):
        raise TranslationSourceReviewError(
            f"shared review root must stay under {DEFAULT_SHARED_ROOT}"
        )
    packet_root = shared_root / packet_id
    if packet_root.exists():
        raise TranslationSourceReviewError(f"review packet already exists: {packet_root}")

    plan = _load_json(review_plan_path)
    issues = _plan_issues(tree_repo_root, review_plan_path, plan)
    if issues:
        raise TranslationSourceReviewError("invalid source review plan: " + "; ".join(issues))

    packet_root.mkdir(parents=True, exist_ok=False)
    receipt_path = packet_root / "translation-source-review.receipt.json"
    receipt: dict[str, Any] = {
        "schema_version": "tos_translation_source_review_packet_receipt_v1",
        "packet_id": packet_id,
        "status": "running",
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "invocation": invocation,
        "review_plan_ref": review_plan_path.as_posix(),
        "review_plan_sha256": _sha256_file(review_plan_path),
        "runner_sha256": _sha256_file(Path(__file__)),
        "errors": [],
    }
    _write_json(receipt_path, receipt)
    started = time.perf_counter()
    try:
        manifests = _manifest_index(tree_repo_root)
        source_plan = plan["source_witness"]
        visual_plan = plan["visual_witness"]
        source = _resolve_payload(
            tree_repo_root,
            manifests,
            source_plan["item_ref"],
            source_plan["file_ref"],
            source_plan["file_sha256"],
            ".epub",
        )
        visual = _resolve_payload(
            tree_repo_root,
            manifests,
            visual_plan["item_ref"],
            visual_plan["file_ref"],
            visual_plan["file_sha256"],
            ".pdf",
        )
        pdf = _pdf_inventory(pdfinfo, visual["path"])

        with zipfile.ZipFile(source["path"]) as archive:
            names = set(archive.namelist())
            for unit in plan["units"]:
                member = unit["container_member"]
                if member not in names:
                    raise TranslationSourceReviewError(f"EPUB member is missing: {member}")
                if _sha256_bytes(archive.read(member)) != unit["member_sha256"]:
                    raise TranslationSourceReviewError(f"EPUB member digest drift: {member}")

        required_pages = sorted(
            {
                page
                for unit in plan["units"]
                for page in unit["visual_context"].values()
            }
        )
        if required_pages[-1] > pdf["page_count"]:
            raise TranslationSourceReviewError("review plan exceeds visual PDF page count")
        pages_root = packet_root / "pages"
        pages_root.mkdir(parents=True)
        page_rows: list[dict[str, Any]] = []
        page_projection: list[dict[str, Any]] = []
        for page in required_pages:
            output_path = packet_root / _page_ref(page)
            _render_page(pdftoppm, visual["path"], output_path, page)
            width, height = _png_dimensions(output_path)
            artifact = _artifact_record(packet_root, output_path)
            page_rows.append(
                {
                    "pdf_page": page,
                    "artifact": artifact,
                    "png_width": width,
                    "png_height": height,
                }
            )
            page_projection.append(
                {
                    "pdf_page": page,
                    "sha256": artifact["sha256"],
                    "bytes": artifact["bytes"],
                    "png_width": width,
                    "png_height": height,
                }
            )

        questions = list(plan["review_questions"])
        review_rows = [
            _review_template(packet_id, unit, questions) for unit in plan["units"]
        ]
        template_path = packet_root / "reviews/source-review-v2.template.jsonl"
        _write_jsonl(template_path, review_rows)

        pass_1_path = packet_root / "review/pass-1-layout-and-transcription.html"
        pass_2_path = packet_root / "review/pass-2-boundary-verification.html"
        pass_1_path.parent.mkdir(parents=True)
        pass_1_path.write_text(
            _workbook_html(
                packet_id, plan["units"], pass_number=1, questions=questions
            ),
            encoding="utf-8",
        )
        pass_2_path.write_text(
            _workbook_html(
                packet_id, plan["units"], pass_number=2, questions=questions
            ),
            encoding="utf-8",
        )

        unit_rows = []
        for unit in plan["units"]:
            context = unit["visual_context"]
            unit_rows.append(
                {
                    "review_unit_id": unit["review_unit_id"],
                    "context_anchor_ref": unit["context_anchor_ref"],
                    "previous_page_ref": _page_ref(context["previous_pdf_page"]),
                    "current_page_ref": _page_ref(context["current_pdf_page"]),
                    "next_page_ref": _page_ref(context["next_pdf_page"]),
                    "v1_candidate_visible": False,
                    "review_status": "not-started",
                    "human_source_acceptance": False,
                }
            )

        manifest = {
            "schema_version": "tos_translation_source_review_packet_manifest_v1",
            "packet_id": packet_id,
            "experiment_id": "tos-translation-foundation-v1",
            "status": "awaiting-real-human-source-review",
            "created_at_utc": receipt["started_at_utc"],
            "artifact_root": packet_root.as_posix(),
            "review_plan_ref": review_plan_path.as_posix(),
            "review_plan_sha256": receipt["review_plan_sha256"],
            "source_witness": source_plan,
            "visual_witness": {
                **visual_plan,
                "page_count": pdf["page_count"],
            },
            "rights_snapshots": [
                _rights_snapshot(
                    tree_repo_root,
                    source_plan["item_ref"],
                    source_plan["file_ref"],
                    source,
                ),
                _rights_snapshot(
                    tree_repo_root,
                    visual_plan["item_ref"],
                    visual_plan["file_ref"],
                    visual,
                ),
            ],
            "render": {
                "tool": "pdftoppm",
                "tool_version": _pdftoppm_version(pdftoppm),
                "dpi": 180,
                "color_mode": "rgb",
                "format": "png",
                "page_scope": "previous-current-next triplets",
                "unique_page_count": len(page_rows),
            },
            "pages": page_rows,
            "page_set_sha256": _canonical_sha256(page_projection),
            "units": unit_rows,
            "pass_1_workbook": _artifact_record(packet_root, pass_1_path),
            "pass_2_workbook": _artifact_record(packet_root, pass_2_path),
            "review_template": _artifact_record(packet_root, template_path),
            "recognized_comparator": {
                "expression_ref": plan["recognized_comparator"]["expression_ref"],
                "item_ref": plan["recognized_comparator"]["item_ref"],
                "visibility": "sealed",
                "content_consulted": False,
                "content_emitted": False,
            },
            "lanes": {
                "human_only": "awaiting-real-human-source-input",
                "ai_only": "blocked-pending-human-source-acceptance",
                "ai_human": "blocked-pending-independent-drafts",
            },
            "receipt_ref": _relative(packet_root, receipt_path),
            "authority_boundary": AUTHORITY_BOUNDARY,
        }
        manifest_path = packet_root / "translation-source-review-manifest.json"
        _write_json(manifest_path, manifest)

        receipt["status"] = "awaiting-real-human-source-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["wall_seconds"] = time.perf_counter() - started
        receipt["source_member_fixity_count"] = 30
        receipt["rendered_page_count"] = len(page_rows)
        receipt["page_set_sha256"] = manifest["page_set_sha256"]
        receipt["manifest_ref"] = _relative(packet_root, manifest_path)
        receipt["manifest_sha256"] = _sha256_file(manifest_path)
        receipt["errors"] = []
        _write_json(receipt_path, receipt)
        return verify_translation_source_review_manifest(manifest_path)
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)]
        _write_json(receipt_path, receipt)
        if isinstance(exc, TranslationSourceReviewError):
            raise
        raise TranslationSourceReviewError(str(exc)) from exc
