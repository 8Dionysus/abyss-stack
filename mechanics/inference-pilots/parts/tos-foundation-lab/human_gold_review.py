#!/usr/bin/env python3
"""Materialize and gate the private 15-page source-visible human gold packet."""

from __future__ import annotations

import html
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ocr_render import OcrRenderError, _pdftoppm_version, png_header, verify_render_manifest
from translation_source import (
    PACKET_ID_RE,
    _artifact_record,
    _canonical_sha256,
    _load_json,
    _pdf_inventory,
    _relative,
    _schema_issues,
    _sha256_file,
    _utc_now,
    _within,
    _write_json,
    _write_jsonl,
)


PART_ROOT = Path(__file__).resolve().parent
MANIFEST_SCHEMA_PATH = PART_ROOT / "schemas/human-gold-review-manifest.schema.json"
RECORD_SCHEMA_PATH = PART_ROOT / "schemas/human-gold-review-record.schema.json"
DEFAULT_SHARED_ROOT = Path(
    "/srv/abyss-machine/storage/artifacts/tree-of-sophia-foundation-lab/"
    "shared-inputs/tos-human-gold-foundation-v1"
)
AUTHORITY_BOUNDARY = (
    "private source-visible interface and blank two-pass review template only; "
    "no human transcription, OCR quality, structure quality, or gold acceptance "
    "is implied"
)
RECORD_AUTHORITY_BOUNDARY = (
    "record shape and attestations do not prove transcription correctness; "
    "acceptance requires two real source-visible human passes and explicit "
    "adjudication"
)


class HumanGoldReviewError(OcrRenderError):
    """Raised when the human-gold interface is unsafe, incomplete, or drifted."""


def _load_and_validate(path: Path, schema_path: Path, label: str) -> dict[str, Any]:
    payload = _load_json(path)
    issues = _schema_issues(payload, schema_path)
    if issues:
        raise HumanGoldReviewError(f"invalid {label}: " + "; ".join(issues))
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise HumanGoldReviewError(f"cannot read {path}: {exc}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line:
            raise HumanGoldReviewError(f"{path}:{line_number} is unexpectedly blank")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HumanGoldReviewError(f"cannot read {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise HumanGoldReviewError(f"{path}:{line_number} must contain an object")
        rows.append(row)
    return rows


def _record_issues(row: dict[str, Any]) -> list[str]:
    schema = _load_json(RECORD_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[str] = []
    for error in sorted(
        validator.iter_errors(row), key=lambda item: list(item.absolute_path)
    ):
        location = "".join(f"[{part!r}]" for part in error.absolute_path) or "<root>"
        issues.append(f"{location}: {error.message}")
    return issues


def _page_ref(group_id: str, page: int) -> str:
    return f"pages/{group_id}-p{page:04d}.png"


def _render_page(
    pdftoppm: Path, source_path: Path, output_path: Path, page: int
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_prefix = output_path.with_suffix("")
    command = (
        pdftoppm.as_posix(),
        "-f",
        str(page),
        "-l",
        str(page),
        "-singlefile",
        "-r",
        "300",
        "-png",
        source_path.as_posix(),
        output_prefix.as_posix(),
    )
    completed = subprocess.run(
        command, check=False, capture_output=True, timeout=300
    )
    if completed.returncode != 0 or not output_path.is_file():
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise HumanGoldReviewError(
            f"pdftoppm failed for {source_path.name} page {page} with "
            f"{completed.returncode}: {stderr[:300]}"
        )
    header = png_header(output_path)
    if (
        header["bit_depth"] != 8
        or header["png_color_type"] != 2
        or header["color_space"] != "rgb"
    ):
        raise HumanGoldReviewError(
            f"human-review render is not 8-bit RGB for page {page}: {header}"
        )


def _source_units(
    gold_status: dict[str, Any],
    visual_plan: dict[str, Any],
    render_manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gold_units = gold_status.get("units")
    if not isinstance(gold_units, list) or len(gold_units) != 15:
        raise HumanGoldReviewError("gold status must contain exactly 15 units")
    if gold_status.get("set_status") != "candidate":
        raise HumanGoldReviewError("gold status is no longer at the candidate stop line")
    for row in gold_units:
        if (
            not isinstance(row, dict)
            or row.get("gold_status") != "candidate"
            or row.get("content_sha256") is not None
            or row.get("human_pass_1", {}).get("status") != "not_started"
            or row.get("human_pass_2", {}).get("status") != "not_started"
        ):
            raise HumanGoldReviewError(
                "gold status unexpectedly claims content or human review"
            )

    visual_by_source: dict[str, dict[str, Any]] = {}
    source_groups: dict[str, dict[str, Any]] = {}
    for group in visual_plan.get("source_groups", []):
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("group_id", ""))
        source_groups[group_id] = group
        for sample in group.get("samples", []):
            if not isinstance(sample, dict) or sample.get("gold_candidate") is not True:
                continue
            source_sample_id = str(sample.get("source_sample_id", ""))
            if source_sample_id in visual_by_source:
                raise HumanGoldReviewError(
                    f"duplicate visual projection for {source_sample_id}"
                )
            visual_by_source[source_sample_id] = {
                **sample,
                "group_id": group_id,
                "language": group.get("language"),
                "item_ref": group.get("item_ref"),
                "file_ref": group.get("file_ref"),
                "file_sha256": group.get("file_sha256"),
            }
    gold_ids = [str(row.get("sample_id", "")) for row in gold_units]
    if set(gold_ids) != set(visual_by_source) or len(visual_by_source) != 15:
        raise HumanGoldReviewError(
            "visual gold projections do not close over the exact 15 gold-status units"
        )

    render_by_sample = {
        str(row.get("sample_id")): row
        for row in render_manifest.get("renders", [])
        if isinstance(row, dict)
    }
    units: list[dict[str, Any]] = []
    for gold in gold_units:
        sample_id = str(gold["sample_id"])
        visual = visual_by_source[sample_id]
        visual_sample_id = str(visual["sample_id"])
        render = render_by_sample.get(visual_sample_id)
        if render is None:
            raise HumanGoldReviewError(
                f"frozen render is missing for {visual_sample_id}"
            )
        expected_pairs = {
            "group_id": visual["group_id"],
            "anchor_ref": visual["anchor_ref"],
            "page": visual["page"],
            "language": visual["language"],
            "gold_candidate": True,
        }
        for key, expected in expected_pairs.items():
            if render.get(key) != expected:
                raise HumanGoldReviewError(
                    f"{visual_sample_id}: frozen render drifted at {key}"
                )
        units.append(
            {
                "sample_id": sample_id,
                "source_anchor_ref": gold["anchor_ref"],
                "content_ref": gold["content_ref"],
                "visual_sample_id": visual_sample_id,
                "visual_anchor_ref": visual["anchor_ref"],
                "group_id": visual["group_id"],
                "language": visual["language"],
                "pdf_page": visual["page"],
                "difficulty": visual["difficulty"],
                "strata": visual["strata"],
                "projection_change": visual["projection_change"],
                "projection_note": visual.get("projection_note"),
                "frozen_png_ref": render["png_ref"],
                "frozen_png_sha256": render["png_sha256"],
                "frozen_png_bytes": render["png_bytes"],
                "frozen_width": render["width_pixels"],
                "frozen_height": render["height_pixels"],
            }
        )
    if len({row["visual_sample_id"] for row in units}) != 15:
        raise HumanGoldReviewError("visual sample IDs are not unique")
    return units, [source_groups[key] for key in sorted(source_groups)]


def _blank_record(packet_id: str, unit: dict[str, Any]) -> dict[str, Any]:
    page = int(unit["pdf_page"])
    group_id = str(unit["group_id"])
    return {
        "schema_version": "tos_human_gold_review_record_v1",
        "packet_id": packet_id,
        "sample_id": unit["sample_id"],
        "source_anchor_ref": unit["source_anchor_ref"],
        "visual_sample_id": unit["visual_sample_id"],
        "visual_anchor_ref": unit["visual_anchor_ref"],
        "source_pages": {
            "previous": _page_ref(group_id, page - 1),
            "current": _page_ref(group_id, page),
            "next": _page_ref(group_id, page + 1),
        },
        "model_outputs_visible": False,
        "embedded_or_reference_ocr_visible": False,
        "recognized_translation_visible": False,
        "pass_1": {
            "performed_by_real_human": False,
            "reviewer_ref": None,
            "reviewed_at_utc": None,
            "source_visible": False,
            "source_file_digest_verified": False,
            "page_and_region_resolved": None,
            "source_legibility": None,
            "diplomatic_transcription": None,
            "layout_and_reading_order": None,
            "unresolved_glyphs": [],
            "source_damage_or_ambiguity": None,
            "decision": None,
            "elapsed_minutes": None,
            "notes": [],
        },
        "pass_2": {
            "performed_by_real_human": False,
            "reviewer_ref": None,
            "reviewed_at_utc": None,
            "source_visible": False,
            "source_file_digest_verified": False,
            "independent_from_pass_1_attested": False,
            "pass_1_visible_during_review": False,
            "independent_diplomatic_transcription": None,
            "punctuation_and_case_checked": False,
            "hyphenation_and_page_boundary_checked": False,
            "lineation_and_reading_order_checked": False,
            "page_furniture_checked": False,
            "unresolved_glyphs_checked": False,
            "decision": None,
            "disagreements_with_pass_1": [],
            "elapsed_minutes": None,
            "notes": [],
        },
        "adjudication": {
            "decision": None,
            "diplomatic_transcription": None,
            "adjudicator_ref": None,
            "adjudicated_at_utc": None,
            "correction_minutes": None,
            "error_ledger_refs": [],
            "rationale": None,
        },
        "human_gold_status": "candidate",
        "authority_boundary": RECORD_AUTHORITY_BOUNDARY,
    }


def _workbook_html(
    packet_id: str, units: list[dict[str, Any]], *, pass_number: int
) -> str:
    if pass_number not in {1, 2}:
        raise HumanGoldReviewError("workbook pass must be 1 or 2")
    if pass_number == 1:
        title = "Pass 1: independent diplomatic page transcription"
        warning = (
            "Judge only the source images. OCR A/B/C outputs, embedded OCR, "
            "earlier transcriptions, and recognized translations are absent."
        )
    else:
        title = "Pass 2: independent source-visible double check"
        warning = (
            "Re-transcribe from the source images without opening pass 1. "
            "Pass 1 must remain hidden until both drafts are frozen."
        )
    sections: list[str] = []
    for unit in units:
        sample_id = html.escape(str(unit["sample_id"]))
        visual_sample_id = html.escape(str(unit["visual_sample_id"]))
        group_id = str(unit["group_id"])
        page = int(unit["pdf_page"])
        figures: list[str] = []
        for role, page_number in (
            ("previous", page - 1),
            ("current", page),
            ("next", page + 1),
        ):
            page_ref = _page_ref(group_id, page_number)
            role_class = " current" if role == "current" else ""
            figures.append(
                f'<figure class="page{role_class}"><figcaption>{role.title()} '
                f'PDF page {page_number}</figcaption><a href="../{page_ref}" '
                f'target="_blank"><img loading="lazy" src="../{page_ref}" '
                f'alt="{role.title()} source page {page_number}"></a></figure>'
            )
        if pass_number == 1:
            fields = """
            <label><input type="checkbox" name="source_visible">
              Source images remained visible during transcription</label>
            <label><input type="checkbox" name="source_file_digest_verified">
              Declared source-file digest checked against the packet manifest</label>
            <label>Page and region resolve
              <select name="page_and_region_resolved"><option value="">Choose</option>
                <option>yes</option><option>no</option><option>uncertain</option>
              </select>
            </label>
            <label>Source legibility
              <select name="source_legibility"><option value="">Choose</option>
                <option>legible</option><option>partly-legible</option>
                <option>illegible</option><option>uncertain</option>
              </select>
            </label>
            <label>Diplomatic transcription of the complete center page
              <textarea name="diplomatic_transcription" rows="18"></textarea>
            </label>
            <label>Layout and reading order
              <textarea name="layout_and_reading_order" rows="5"></textarea>
            </label>
            <label>Unresolved glyphs with line/region coordinates
              <textarea name="unresolved_glyphs" rows="4"></textarea>
            </label>
            <label>Source damage or ambiguity
              <textarea name="source_damage_or_ambiguity" rows="3"></textarea>
            </label>
            <label>Decision
              <select name="decision"><option value="">Choose</option>
                <option>accept</option><option>accept-with-limits</option>
                <option>reject</option><option>uncertain</option>
                <option>abstain</option>
              </select>
            </label>
            <label>Elapsed human minutes<input type="number" min="0" step="0.1"
              name="elapsed_minutes"></label>
            <label>Notes<textarea name="notes" rows="3"></textarea></label>
            """
        else:
            fields = """
            <label><input type="checkbox" name="source_visible">
              Source images remained visible during the independent pass</label>
            <label><input type="checkbox" name="source_file_digest_verified">
              Declared source-file digest checked against the packet manifest</label>
            <label><input type="checkbox" name="independent_from_pass_1_attested">
              This pass was completed independently from pass 1</label>
            <label><input type="checkbox" name="pass_1_visible_during_review">
              Pass 1 was visible during this review (must remain unchecked)</label>
            <label>Independent diplomatic transcription
              <textarea name="independent_diplomatic_transcription" rows="18"></textarea>
            </label>
            <label><input type="checkbox" name="punctuation_and_case_checked">
              Punctuation and capitalization checked</label>
            <label><input type="checkbox" name="hyphenation_and_page_boundary_checked">
              Hyphenation and both page boundaries checked</label>
            <label><input type="checkbox" name="lineation_and_reading_order_checked">
              Lineation and reading order checked</label>
            <label><input type="checkbox" name="page_furniture_checked">
              Header, footer, line numbers, and scan furniture checked</label>
            <label><input type="checkbox" name="unresolved_glyphs_checked">
              Unresolved glyphs and coordinates checked</label>
            <label>Decision
              <select name="decision"><option value="">Choose</option>
                <option>confirm</option><option>revise</option>
                <option>reject</option><option>uncertain</option>
                <option>abstain</option>
              </select>
            </label>
            <label>Disagreements or uncertainties
              <textarea name="disagreements_with_pass_1" rows="4"></textarea>
            </label>
            <label>Elapsed human minutes<input type="number" min="0" step="0.1"
              name="elapsed_minutes"></label>
            <label>Notes<textarea name="notes" rows="3"></textarea></label>
            """
        sections.append(
            f'<section class="unit" data-unit="{sample_id}"><h2>{sample_id}</h2>'
            f'<p class="blind">Visual unit: {visual_sample_id}; language: '
            f'{html.escape(str(unit["language"]))}. {html.escape(warning)}</p>'
            f'<div class="triplet">{"".join(figures)}</div>{fields}</section>'
        )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(title)}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1600px;margin:auto;padding:1rem;background:#151515;color:#eee}}
h1,h2{{color:#f0d78c}} .notice,.identity,.unit{{border:1px solid #555;border-radius:8px;padding:1rem;margin:1rem 0;background:#202020}}
.triplet{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem;align-items:start}}
.page img{{width:100%;height:auto;background:white}} .page.current{{outline:4px solid #d6a928}}
label{{display:block;margin:.8rem 0}} input[type=text],input[type=number],input:not([type]),select,textarea{{width:100%;box-sizing:border-box;background:#111;color:#eee;border:1px solid #777;padding:.5rem}}
input[type=checkbox]{{width:auto}} .blind{{color:#bbb}} button{{font-size:1rem;padding:.8rem 1.2rem;background:#d6a928;border:0;border-radius:5px}}
@media(max-width:900px){{.triplet{{grid-template-columns:1fr}}}}
</style></head>
<body>
<h1>{html.escape(title)}</h1>
<div class="notice"><p>Packet: {html.escape(packet_id)}. This local workbook
does not submit, accept, or promote anything. Export creates a draft JSON file.
The center page is the frozen OCR contestant input; adjacent pages are context
rendered from the same digest-verified source PDF at the same 300 DPI.</p>
<p>{html.escape(warning)}</p></div>
<div class="identity">
<label>Human reviewer reference<input id="reviewer_ref"></label>
<label><input type="checkbox" id="human_attestation">
I attest that this pass was performed by a real human looking at the source pages.</label>
</div>
{"".join(sections)}
<button type="button" onclick="downloadDraft()">Download pass {pass_number} draft JSON</button>
<script>
function splitLines(value){{return value.split(/\\r?\\n/).map(v=>v.trim()).filter(Boolean);}}
function downloadDraft(){{
  const rows=[...document.querySelectorAll('.unit')].map(section=>{{
    const row={{sample_id:section.dataset.unit}};
    for(const field of section.querySelectorAll('input,select,textarea')){{
      let value=field.type==='checkbox'?field.checked:field.value;
      if(['unresolved_glyphs','notes','disagreements_with_pass_1'].includes(field.name)){{
        value=splitLines(value);
      }} else if(field.name==='elapsed_minutes'){{
        value=value===''?null:Number(value);
      }}
      row[field.name]=value;
    }}
    return row;
  }});
  const payload={{
    schema_version:'tos_human_gold_review_draft_v1',
    packet_id:{json.dumps(packet_id)},
    pass_number:{pass_number},
    performed_by_real_human:document.getElementById('human_attestation').checked,
    reviewer_ref:document.getElementById('reviewer_ref').value||null,
    exported_at_utc:new Date().toISOString(),
    rows,
    authority_boundary:'downloaded worksheet draft only; independent review and adjudication still required'
  }};
  const blob=new Blob([JSON.stringify(payload,null,2)+'\\n'],{{type:'application/json'}});
  const link=document.createElement('a'); link.href=URL.createObjectURL(blob);
  link.download='human-gold-pass-{pass_number}.draft.json'; link.click();
  URL.revokeObjectURL(link.href);
}}
</script></body></html>
"""


def verify_human_gold_review_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = _load_json(manifest_path)
    issues = _schema_issues(manifest, MANIFEST_SCHEMA_PATH)
    root = Path(str(manifest.get("artifact_root", ""))).resolve()
    tree_repo_root = Path(str(manifest.get("tree_repo_root", ""))).resolve()
    if manifest_path != root / "human-gold-review-manifest.json":
        issues.append("manifest is not at its declared artifact root")

    references = (
        ("gold_status_ref", "gold_status_sha256"),
        ("visual_plan_ref", "visual_plan_sha256"),
        ("render_manifest_ref", "render_manifest_sha256"),
    )
    reference_payloads: dict[str, dict[str, Any]] = {}
    for ref_key, digest_key in references:
        path = Path(str(manifest.get(ref_key, ""))).resolve()
        if not _within(path, tree_repo_root) or not path.is_file():
            issues.append(f"{ref_key} is missing or escaped the Tree repository")
            continue
        if _sha256_file(path) != manifest.get(digest_key):
            issues.append(f"{digest_key} does not match {ref_key}")
            continue
        reference_payloads[ref_key] = _load_json(path)

    render_manifest: dict[str, Any] = {}
    render_path = Path(str(manifest.get("render_manifest_ref", ""))).resolve()
    if render_path.is_file():
        try:
            render_manifest = verify_render_manifest(render_path)
        except OcrRenderError as exc:
            issues.append(str(exc))
    if render_manifest and render_manifest.get("render_set_sha256") != manifest.get(
        "render_set_sha256"
    ):
        issues.append("render_set_sha256 drifted")

    gold_status = reference_payloads.get("gold_status_ref", {})
    visual_plan = reference_payloads.get("visual_plan_ref", {})
    expected_units: list[dict[str, Any]] = []
    if gold_status and visual_plan and render_manifest:
        try:
            expected_units, _groups = _source_units(
                gold_status, visual_plan, render_manifest
            )
        except HumanGoldReviewError as exc:
            issues.append(str(exc))

    manifest_source_rows = [
        row for row in manifest.get("source_files", []) if isinstance(row, dict)
    ]
    source_by_group = {
        str(row.get("group_id")): row for row in manifest_source_rows
    }
    expected_group_ids = {str(row["group_id"]) for row in expected_units}
    expected_source_by_group = {
        str(row.get("group_id")): row
        for row in render_manifest.get("source_files", [])
        if isinstance(row, dict) and str(row.get("group_id")) in expected_group_ids
    }
    if len(source_by_group) != len(manifest_source_rows):
        issues.append("source_files contains duplicate group IDs")
    if set(source_by_group) != expected_group_ids:
        issues.append("source_files does not close over the exact gold source groups")
    if set(expected_source_by_group) != expected_group_ids:
        issues.append("frozen render manifest does not close over the gold source groups")
    for group_id in sorted(expected_group_ids):
        row = source_by_group.get(group_id)
        expected_source = expected_source_by_group.get(group_id)
        if row is None or expected_source is None:
            continue
        path = Path(str(row.get("local_path", ""))).resolve()
        if (
            not _within(path, tree_repo_root)
            or not path.is_file()
            or _sha256_file(path) != row.get("file_sha256")
        ):
            issues.append(f"source file missing, escaped, or drifted for {group_id}")
            continue
        for key in ("item_ref", "file_ref", "file_sha256", "language"):
            if row.get(key) != expected_source.get(key):
                issues.append(f"source identity drifted at {key} for {group_id}")
        expected_path = Path(str(expected_source.get("local_path", ""))).resolve()
        if path != expected_path:
            issues.append(f"source local_path drifted for {group_id}")

    page_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    current_projection: list[dict[str, Any]] = []
    for row in manifest.get("pages", []):
        if not isinstance(row, dict):
            continue
        key = (str(row.get("group_id", "")), int(row.get("pdf_page", 0)))
        if key in page_by_key:
            issues.append(f"duplicate context render {key}")
        page_by_key[key] = row
        artifact = row.get("artifact", {})
        path = root / str(artifact.get("ref", ""))
        if artifact.get("ref") != _page_ref(key[0], key[1]):
            issues.append(f"context render ref drifted for {key}")
        if not _within(path, root) or not path.is_file():
            issues.append(f"missing or escaped context render {key}")
            continue
        header = png_header(path)
        actual_sha = _sha256_file(path)
        if (
            actual_sha != artifact.get("sha256")
            or path.stat().st_size != artifact.get("bytes")
            or header["width_pixels"] != row.get("png_width")
            or header["height_pixels"] != row.get("png_height")
            or header["bit_depth"] != 8
            or header["png_color_type"] != 2
        ):
            issues.append(f"fixity or PNG metadata drift for context render {key}")
        frozen_sha = row.get("frozen_render_sha256")
        if row.get("is_frozen_center_page") is True and actual_sha != frozen_sha:
            issues.append(f"center page no longer matches frozen OCR input for {key}")
        if row.get("is_frozen_center_page") is False and frozen_sha is not None:
            issues.append(f"non-center context page unexpectedly carries a frozen hash for {key}")
        current_projection.append(
            {
                "group_id": key[0],
                "pdf_page": key[1],
                "sha256": actual_sha,
                "bytes": path.stat().st_size,
                "png_width": header["width_pixels"],
                "png_height": header["height_pixels"],
                "is_frozen_center_page": row.get("is_frozen_center_page"),
                "frozen_render_sha256": frozen_sha,
            }
        )
    current_projection.sort(key=lambda row: (row["group_id"], row["pdf_page"]))
    expected_page_keys = {
        (str(row["group_id"]), int(row["pdf_page"]) + offset)
        for row in expected_units
        for offset in (-1, 0, 1)
    }
    if set(page_by_key) != expected_page_keys:
        issues.append("context pages do not equal the exact required page set")
    expected_centers = {
        (str(row["group_id"]), int(row["pdf_page"])): row
        for row in expected_units
    }
    actual_center_keys = {
        key
        for key, row in page_by_key.items()
        if row.get("is_frozen_center_page") is True
    }
    if actual_center_keys != set(expected_centers):
        issues.append("frozen center-page set does not equal the exact 15 gold units")
    for key, expected in expected_centers.items():
        center = page_by_key.get(key)
        if center is None:
            continue
        artifact = center.get("artifact", {})
        if (
            center.get("is_frozen_center_page") is not True
            or center.get("frozen_render_sha256") != expected["frozen_png_sha256"]
            or artifact.get("sha256") != expected["frozen_png_sha256"]
            or artifact.get("bytes") != expected["frozen_png_bytes"]
            or center.get("png_width") != expected["frozen_width"]
            or center.get("png_height") != expected["frozen_height"]
        ):
            issues.append(f"frozen center identity drifted for {key}")
    if _canonical_sha256(current_projection) != manifest.get("page_set_sha256"):
        issues.append("page_set_sha256 does not close over current context pages")
    if manifest.get("context_render", {}).get("unique_page_count") != len(page_by_key):
        issues.append("context_render.unique_page_count does not match page records")

    manifest_units = manifest.get("units")
    if not isinstance(manifest_units, list) or len(manifest_units) != len(expected_units):
        issues.append("manifest units do not close over the exact 15 gold candidates")
        manifest_units = []
    for row, expected in zip(manifest_units, expected_units, strict=False):
        page = int(expected["pdf_page"])
        group_id = str(expected["group_id"])
        projected = {
            key: expected[key]
            for key in (
                "sample_id",
                "source_anchor_ref",
                "content_ref",
                "visual_sample_id",
                "visual_anchor_ref",
                "group_id",
                "language",
                "pdf_page",
                "difficulty",
                "strata",
                "projection_change",
                "projection_note",
            )
        }
        projected.update(
            {
                "previous_page_ref": _page_ref(group_id, page - 1),
                "current_page_ref": _page_ref(group_id, page),
                "next_page_ref": _page_ref(group_id, page + 1),
                "review_status": "not-started",
                "human_gold_status": "candidate",
            }
        )
        if row != projected:
            issues.append(f"{expected['sample_id']}: unit projection drifted")
        for context_page in (page - 1, page, page + 1):
            if (group_id, context_page) not in page_by_key:
                issues.append(
                    f"{expected['sample_id']}: missing context page {context_page}"
                )

    for key in ("pass_1_workbook", "pass_2_workbook", "review_template"):
        artifact = manifest.get(key, {})
        path = root / str(artifact.get("ref", ""))
        if (
            not _within(path, root)
            or not path.is_file()
            or _sha256_file(path) != artifact.get("sha256")
            or path.stat().st_size != artifact.get("bytes")
        ):
            issues.append(f"fixity drift for {key}")
    if expected_units:
        expected_workbooks = {
            "pass_1_workbook": _workbook_html(
                str(manifest.get("packet_id", "")), expected_units, pass_number=1
            ),
            "pass_2_workbook": _workbook_html(
                str(manifest.get("packet_id", "")), expected_units, pass_number=2
            ),
        }
        for key, expected_html in expected_workbooks.items():
            artifact = manifest.get(key, {})
            path = root / str(artifact.get("ref", ""))
            if path.is_file() and path.read_text(encoding="utf-8") != expected_html:
                issues.append(f"{key} is not the deterministic blind workbook")

    template_path = root / str(manifest.get("review_template", {}).get("ref", ""))
    template_rows: list[dict[str, Any]] = []
    if template_path.is_file():
        try:
            template_rows = _load_jsonl(template_path)
        except HumanGoldReviewError as exc:
            issues.append(str(exc))
    if len(template_rows) != 15:
        issues.append("blank review template must contain exactly 15 rows")
    expected_ids = [str(row.get("sample_id")) for row in manifest_units]
    if [str(row.get("sample_id")) for row in template_rows] != expected_ids:
        issues.append("blank review template order drifted")
    expected_blank_rows = [
        _blank_record(str(manifest.get("packet_id", "")), unit)
        for unit in expected_units
    ]
    for index, row in enumerate(template_rows):
        row_issues = _record_issues(row)
        issues.extend(f"template[{index}]: {issue}" for issue in row_issues)
        if index < len(expected_blank_rows) and row != expected_blank_rows[index]:
            issues.append(f"template[{index}] drifted from the exact blank record")
        if (
            row.get("pass_1", {}).get("performed_by_real_human") is not False
            or row.get("pass_2", {}).get("performed_by_real_human") is not False
            or row.get("adjudication", {}).get("decision") is not None
            or row.get("human_gold_status") != "candidate"
        ):
            issues.append(f"template[{index}] claims human work or gold")

    receipt_path = root / str(manifest.get("receipt_ref", ""))
    if not _within(receipt_path, root) or not receipt_path.is_file():
        issues.append("review packet receipt is missing or escaped")
    else:
        receipt = _load_json(receipt_path)
        if receipt.get("status") != "awaiting-real-human-double-check":
            issues.append("receipt does not retain the human stop line")
        if receipt.get("packet_id") != manifest.get("packet_id"):
            issues.append("receipt packet identity drifted")
        if receipt.get("manifest_ref") != _relative(root, manifest_path):
            issues.append("receipt manifest_ref drifted")
        if receipt.get("manifest_sha256") != _sha256_file(manifest_path):
            issues.append("receipt manifest_sha256 drifted")
        if receipt.get("page_set_sha256") != manifest.get("page_set_sha256"):
            issues.append("receipt page_set_sha256 drifted")
        if receipt.get("review_unit_count") != 15:
            issues.append("receipt review-unit count drifted")
        if receipt.get("rendered_context_page_count") != len(page_by_key):
            issues.append("receipt context-page count drifted")
        if receipt.get("errors") != []:
            issues.append("receipt carries materialization errors")

    if (
        manifest.get("model_outputs_visible") is not False
        or manifest.get("embedded_or_reference_ocr_visible") is not False
        or manifest.get("recognized_translation_visible") is not False
    ):
        issues.append("blind human-gold boundary drifted")
    if issues:
        raise HumanGoldReviewError(
            "invalid human gold review manifest: " + "; ".join(issues)
        )
    return manifest


def inspect_human_gold_readiness(
    manifest_path: Path, human_review_output: Path | None = None
) -> dict[str, Any]:
    manifest = verify_human_gold_review_manifest(manifest_path)
    expected_units = manifest["units"]
    records: list[dict[str, Any]] = []
    output_sha256: str | None = None
    if human_review_output is not None:
        output_path = human_review_output.resolve()
        records = _load_jsonl(output_path)
        output_sha256 = _sha256_file(output_path)
    if records and len(records) != 15:
        raise HumanGoldReviewError(
            "human review output must contain exactly 15 ordered records"
        )
    expected_ids = [row["sample_id"] for row in expected_units]
    if records and [row.get("sample_id") for row in records] != expected_ids:
        raise HumanGoldReviewError(
            "human review output does not preserve the exact 15-unit order"
        )

    pass_1_complete = 0
    pass_2_complete = 0
    accepted = 0
    unresolved_ids: list[str] = []
    for expected, row in zip(expected_units, records, strict=False):
        row_issues = _record_issues(row)
        if row_issues:
            raise HumanGoldReviewError(
                f"{expected['sample_id']}: invalid review record: "
                + "; ".join(row_issues)
            )
        static_expected = {
            "packet_id": manifest["packet_id"],
            "sample_id": expected["sample_id"],
            "source_anchor_ref": expected["source_anchor_ref"],
            "visual_sample_id": expected["visual_sample_id"],
            "visual_anchor_ref": expected["visual_anchor_ref"],
            "model_outputs_visible": False,
            "embedded_or_reference_ocr_visible": False,
            "recognized_translation_visible": False,
            "source_pages": {
                "previous": expected["previous_page_ref"],
                "current": expected["current_page_ref"],
                "next": expected["next_page_ref"],
            },
        }
        if any(row.get(key) != value for key, value in static_expected.items()):
            raise HumanGoldReviewError(
                f"{expected['sample_id']}: static source identity drifted"
            )
        p1 = row["pass_1"]
        p2 = row["pass_2"]
        adjudication = row["adjudication"]
        p1_ok = all(
            (
                p1["performed_by_real_human"] is True,
                bool(p1["reviewer_ref"]),
                bool(p1["reviewed_at_utc"]),
                p1["source_visible"] is True,
                p1["source_file_digest_verified"] is True,
                p1["page_and_region_resolved"] == "yes",
                p1["source_legibility"] in {"legible", "partly-legible"},
                bool(p1["diplomatic_transcription"]),
                bool(p1["layout_and_reading_order"]),
                p1["decision"] in {"accept", "accept-with-limits"},
                p1["elapsed_minutes"] is not None,
            )
        )
        if p1_ok:
            pass_1_complete += 1
        p2_ok = all(
            (
                p2["performed_by_real_human"] is True,
                bool(p2["reviewer_ref"]),
                bool(p2["reviewed_at_utc"]),
                p2["source_visible"] is True,
                p2["source_file_digest_verified"] is True,
                p2["independent_from_pass_1_attested"] is True,
                p2["pass_1_visible_during_review"] is False,
                bool(p2["independent_diplomatic_transcription"]),
                p2["punctuation_and_case_checked"] is True,
                p2["hyphenation_and_page_boundary_checked"] is True,
                p2["lineation_and_reading_order_checked"] is True,
                p2["page_furniture_checked"] is True,
                p2["unresolved_glyphs_checked"] is True,
                p2["decision"] in {"confirm", "revise"},
                p2["elapsed_minutes"] is not None,
                p2["reviewer_ref"] != p1["reviewer_ref"],
            )
        )
        if p2_ok:
            pass_2_complete += 1
        accepted_row = all(
            (
                p1_ok,
                p2_ok,
                adjudication["decision"] == "accept",
                bool(adjudication["diplomatic_transcription"]),
                bool(adjudication["adjudicator_ref"]),
                bool(adjudication["adjudicated_at_utc"]),
                adjudication["correction_minutes"] is not None,
                bool(adjudication["rationale"]),
                (
                    bool(adjudication["error_ledger_refs"])
                    if (
                        p1["decision"] == "accept-with-limits"
                        or p2["decision"] == "revise"
                    )
                    else True
                ),
                row["human_gold_status"] == "human-double-checked",
            )
        )
        if accepted_row:
            accepted += 1
        else:
            unresolved_ids.append(expected["sample_id"])

    blocked_reasons: list[str] = []
    if pass_1_complete != 15:
        blocked_reasons.append(f"real_human_pass_1_incomplete:{15 - pass_1_complete}")
    if pass_2_complete != 15:
        blocked_reasons.append(
            f"independent_real_human_pass_2_incomplete:{15 - pass_2_complete}"
        )
    if accepted != 15:
        blocked_reasons.append(f"human_gold_acceptance_incomplete:{15 - accepted}")
    decision = "ready-for-manual-metric-adjudication" if accepted == 15 else "blocked"
    return {
        "schema_version": "tos_human_gold_readiness_v1",
        "generated_at_utc": _utc_now(),
        "packet_id": manifest["packet_id"],
        "manifest_ref": manifest_path.resolve().as_posix(),
        "manifest_sha256": _sha256_file(manifest_path.resolve()),
        "review_output_ref": (
            human_review_output.resolve().as_posix()
            if human_review_output is not None
            else None
        ),
        "review_output_sha256": output_sha256,
        "record_count": len(records),
        "pass_1_complete": pass_1_complete,
        "pass_2_complete": pass_2_complete,
        "accepted_human_gold_units": accepted,
        "unresolved_sample_ids": unresolved_ids,
        "blocked_reasons": blocked_reasons,
        "decision": decision,
        "allowed_next_actions": (
            [
                "manually-recompute-one-ocr-metric",
                "blind-grade-ocr-a-b-c",
                "manually-grade-structure-reading-order",
            ]
            if decision != "blocked"
            else [
                "complete-real-human-pass-1",
                "complete-independent-real-human-pass-2",
                "adjudicate-disagreements-and-errors",
            ]
        ),
        "authority_boundary": (
            "this gate verifies identities, attestations, ordering, fixity, and "
            "declared completion only; it cannot prove transcription correctness "
            "or replace source-visible human inspection"
        ),
    }


def materialize_human_gold_review(
    tree_repo_root: Path,
    gold_status_path: Path,
    visual_plan_path: Path,
    render_manifest_path: Path,
    packet_id: str,
    *,
    shared_root: Path = DEFAULT_SHARED_ROOT,
    pdftoppm: Path = Path("/usr/bin/pdftoppm"),
    pdfinfo: Path = Path("/usr/bin/pdfinfo"),
    invocation: list[str],
) -> dict[str, Any]:
    if not PACKET_ID_RE.fullmatch(packet_id):
        raise HumanGoldReviewError(
            "packet-id must use lowercase letters, digits, dot, underscore, and hyphen"
        )
    tree_repo_root = tree_repo_root.resolve()
    gold_status_path = gold_status_path.resolve()
    visual_plan_path = visual_plan_path.resolve()
    render_manifest_path = render_manifest_path.resolve()
    for path, label in (
        (gold_status_path, "gold status"),
        (visual_plan_path, "visual plan"),
        (render_manifest_path, "render manifest"),
    ):
        if not _within(path, tree_repo_root) or not path.is_file():
            raise HumanGoldReviewError(
                f"{label} is missing or escaped the Tree repository: {path}"
            )

    gold_status = _load_and_validate(
        gold_status_path,
        tree_repo_root / "ToS/contracts/manual-gold-status.schema.json",
        "Tree manual gold status",
    )
    visual_plan = _load_and_validate(
        visual_plan_path,
        tree_repo_root / "ToS/contracts/ocr-visual-sample-plan.schema.json",
        "Tree OCR visual sample plan",
    )
    render_manifest = verify_render_manifest(render_manifest_path)
    units, source_groups = _source_units(gold_status, visual_plan, render_manifest)

    packet_root = (shared_root.resolve() / packet_id).resolve()
    if not _within(packet_root, shared_root.resolve()):
        raise HumanGoldReviewError("packet root escaped the declared shared root")
    packet_root.mkdir(parents=True, exist_ok=False)
    receipt_path = packet_root / "human-gold-review.receipt.json"
    receipt: dict[str, Any] = {
        "schema_version": "tos_human_gold_review_packet_receipt_v1",
        "packet_id": packet_id,
        "status": "running",
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "invocation": invocation,
        "gold_status_ref": gold_status_path.as_posix(),
        "gold_status_sha256": _sha256_file(gold_status_path),
        "visual_plan_ref": visual_plan_path.as_posix(),
        "visual_plan_sha256": _sha256_file(visual_plan_path),
        "render_manifest_ref": render_manifest_path.as_posix(),
        "render_manifest_sha256": _sha256_file(render_manifest_path),
        "runner_sha256": _sha256_file(Path(__file__)),
        "errors": [],
    }
    _write_json(receipt_path, receipt)
    started = time.perf_counter()
    try:
        manifest_sources = {
            str(row["group_id"]): row for row in render_manifest["source_files"]
        }
        source_files: list[dict[str, Any]] = []
        source_paths: dict[str, Path] = {}
        source_page_counts: dict[str, int] = {}
        for group in source_groups:
            group_id = str(group["group_id"])
            source = manifest_sources.get(group_id)
            if source is None:
                raise HumanGoldReviewError(
                    f"render manifest lacks source file for {group_id}"
                )
            for key in ("item_ref", "file_ref", "file_sha256", "language"):
                if source.get(key) != group.get(key):
                    raise HumanGoldReviewError(
                        f"{group_id}: source identity drifted at {key}"
                    )
            source_path = Path(str(source["local_path"])).resolve()
            if (
                not _within(source_path, tree_repo_root)
                or not source_path.is_file()
                or _sha256_file(source_path) != group["file_sha256"]
            ):
                raise HumanGoldReviewError(
                    f"{group_id}: source payload missing, escaped, or drifted"
                )
            source_paths[group_id] = source_path
            source_page_counts[group_id] = _pdf_inventory(
                pdfinfo, source_path
            )["page_count"]
            source_files.append(
                {
                    "group_id": group_id,
                    "item_ref": group["item_ref"],
                    "file_ref": group["file_ref"],
                    "file_sha256": group["file_sha256"],
                    "language": group["language"],
                    "local_path": source_path.as_posix(),
                }
            )

        frozen_by_key = {
            (str(row["group_id"]), int(row["page"])): row
            for row in render_manifest["renders"]
            if row.get("gold_candidate") is True
        }
        required_pages = sorted(
            {
                (str(unit["group_id"]), int(unit["pdf_page"]) + offset)
                for unit in units
                for offset in (-1, 0, 1)
            }
        )
        page_rows: list[dict[str, Any]] = []
        page_projection: list[dict[str, Any]] = []
        for group_id, page in required_pages:
            if page < 1 or page > source_page_counts[group_id]:
                raise HumanGoldReviewError(
                    f"context page outside source PDF: {group_id} page {page}"
                )
            output_path = packet_root / _page_ref(group_id, page)
            _render_page(pdftoppm, source_paths[group_id], output_path, page)
            header = png_header(output_path)
            artifact = _artifact_record(packet_root, output_path)
            frozen = frozen_by_key.get((group_id, page))
            frozen_sha = frozen["png_sha256"] if frozen is not None else None
            if frozen is not None and (
                artifact["sha256"] != frozen_sha
                or artifact["bytes"] != frozen["png_bytes"]
                or header["width_pixels"] != frozen["width_pixels"]
                or header["height_pixels"] != frozen["height_pixels"]
            ):
                raise HumanGoldReviewError(
                    f"center page rerender does not match frozen OCR input: "
                    f"{group_id} page {page}"
                )
            row = {
                "group_id": group_id,
                "pdf_page": page,
                "artifact": artifact,
                "png_width": header["width_pixels"],
                "png_height": header["height_pixels"],
                "is_frozen_center_page": frozen is not None,
                "frozen_render_sha256": frozen_sha,
            }
            page_rows.append(row)
            page_projection.append(
                {
                    "group_id": group_id,
                    "pdf_page": page,
                    "sha256": artifact["sha256"],
                    "bytes": artifact["bytes"],
                    "png_width": header["width_pixels"],
                    "png_height": header["height_pixels"],
                    "is_frozen_center_page": frozen is not None,
                    "frozen_render_sha256": frozen_sha,
                }
            )

        blank_rows = [_blank_record(packet_id, unit) for unit in units]
        for index, row in enumerate(blank_rows):
            issues = _record_issues(row)
            if issues:
                raise HumanGoldReviewError(
                    f"generated blank record {index} is invalid: " + "; ".join(issues)
                )
        template_path = packet_root / "reviews/human-gold-review.template.jsonl"
        _write_jsonl(template_path, blank_rows)

        pass_1_path = packet_root / "review/pass-1-diplomatic-transcription.html"
        pass_2_path = packet_root / "review/pass-2-independent-double-check.html"
        pass_1_path.parent.mkdir(parents=True)
        pass_1_path.write_text(
            _workbook_html(packet_id, units, pass_number=1), encoding="utf-8"
        )
        pass_2_path.write_text(
            _workbook_html(packet_id, units, pass_number=2), encoding="utf-8"
        )

        manifest_units = []
        for unit in units:
            page = int(unit["pdf_page"])
            group_id = str(unit["group_id"])
            manifest_units.append(
                {
                    key: unit[key]
                    for key in (
                        "sample_id",
                        "source_anchor_ref",
                        "content_ref",
                        "visual_sample_id",
                        "visual_anchor_ref",
                        "group_id",
                        "language",
                        "pdf_page",
                        "difficulty",
                        "strata",
                        "projection_change",
                        "projection_note",
                    )
                }
                | {
                    "previous_page_ref": _page_ref(group_id, page - 1),
                    "current_page_ref": _page_ref(group_id, page),
                    "next_page_ref": _page_ref(group_id, page + 1),
                    "review_status": "not-started",
                    "human_gold_status": "candidate",
                }
            )
        manifest = {
            "schema_version": "tos_human_gold_review_packet_manifest_v1",
            "packet_id": packet_id,
            "experiment_id": "tos-ocr-foundation-v1",
            "status": "awaiting-real-human-double-check",
            "created_at_utc": receipt["started_at_utc"],
            "artifact_root": packet_root.as_posix(),
            "tree_repo_root": tree_repo_root.as_posix(),
            "content_visibility": "private-local-only",
            "gold_status_ref": gold_status_path.as_posix(),
            "gold_status_sha256": receipt["gold_status_sha256"],
            "visual_plan_ref": visual_plan_path.as_posix(),
            "visual_plan_sha256": receipt["visual_plan_sha256"],
            "render_manifest_ref": render_manifest_path.as_posix(),
            "render_manifest_sha256": receipt["render_manifest_sha256"],
            "render_set_sha256": render_manifest["render_set_sha256"],
            "source_files": source_files,
            "context_render": {
                "tool": "pdftoppm",
                "tool_version": _pdftoppm_version(pdftoppm),
                "dpi": 300,
                "color_mode": "rgb",
                "page_scope": (
                    "previous-current-next around 15 frozen gold candidates"
                ),
                "unique_page_count": len(page_rows),
            },
            "pages": page_rows,
            "page_set_sha256": _canonical_sha256(page_projection),
            "units": manifest_units,
            "pass_1_workbook": _artifact_record(packet_root, pass_1_path),
            "pass_2_workbook": _artifact_record(packet_root, pass_2_path),
            "review_template": _artifact_record(packet_root, template_path),
            "model_outputs_visible": False,
            "embedded_or_reference_ocr_visible": False,
            "recognized_translation_visible": False,
            "receipt_ref": _relative(packet_root, receipt_path),
            "authority_boundary": AUTHORITY_BOUNDARY,
        }
        manifest_path = packet_root / "human-gold-review-manifest.json"
        _write_json(manifest_path, manifest)

        receipt["status"] = "awaiting-real-human-double-check"
        receipt["finished_at_utc"] = _utc_now()
        receipt["wall_seconds"] = time.perf_counter() - started
        receipt["review_unit_count"] = len(units)
        receipt["rendered_context_page_count"] = len(page_rows)
        receipt["page_set_sha256"] = manifest["page_set_sha256"]
        receipt["manifest_ref"] = _relative(packet_root, manifest_path)
        receipt["manifest_sha256"] = _sha256_file(manifest_path)
        receipt["errors"] = []
        _write_json(receipt_path, receipt)
        return verify_human_gold_review_manifest(manifest_path)
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)]
        _write_json(receipt_path, receipt)
        if isinstance(exc, HumanGoldReviewError):
            raise
        raise HumanGoldReviewError(str(exc)) from exc
