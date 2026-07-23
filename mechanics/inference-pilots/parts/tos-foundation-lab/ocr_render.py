#!/usr/bin/env python3
"""Materialize one shared, digest-frozen visual packet for OCR A/B/C.

The renderer reads immutable ToS PDF witnesses and writes only private runtime
artifacts. It does not consult embedded OCR, EPUB text, or any contestant
output, and it never rewrites a source item.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


PART_ROOT = Path(__file__).resolve().parent
RENDER_SCHEMA_PATH = PART_ROOT / "schemas/ocr-render-manifest.schema.json"
DEFAULT_SHARED_ROOT = Path(
    "/srv/abyss-machine/storage/artifacts/tree-of-sophia-foundation-lab/"
    "shared-inputs/tos-ocr-foundation-v1"
)
RENDER_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class OcrRenderError(RuntimeError):
    """Raised when shared OCR pixels cannot be frozen safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OcrRenderError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise OcrRenderError(f"{path} must contain a JSON object")
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


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def png_header(path: Path) -> dict[str, int | str]:
    """Read the fixed PNG signature and IHDR without an image dependency."""

    data = path.read_bytes()[:33]
    if len(data) < 33 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise OcrRenderError(f"not a valid PNG IHDR: {path}")
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    bit_depth = data[24]
    color_type = data[25]
    if width <= 0 or height <= 0:
        raise OcrRenderError(f"invalid PNG dimensions: {path}")
    color_space = {0: "grayscale", 2: "rgb", 3: "indexed", 4: "grayscale-alpha", 6: "rgba"}.get(
        color_type, "unknown"
    )
    return {
        "width_pixels": width,
        "height_pixels": height,
        "bit_depth": bit_depth,
        "png_color_type": color_type,
        "color_space": color_space,
    }


def _schema_issues(payload: object) -> list[str]:
    schema = _load_json(RENDER_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[str] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path)):
        location = "".join(f"[{part!r}]" for part in error.absolute_path) or "<root>"
        issues.append(f"{location}: {error.message}")
    return issues


def validate_visual_plan(plan: dict[str, Any]) -> list[str]:
    """Check the experiment-relevant laws without claiming ToS schema ownership."""

    issues: list[str] = []
    if plan.get("schema_version") != "tos_ocr_visual_sample_plan_v1":
        issues.append("unexpected visual plan schema_version")
    if plan.get("status") != "frozen" or plan.get("frozen_before_variant_outputs") is not True:
        issues.append("visual plan was not frozen before contestant outputs")
    projection = plan.get("projection_law", {})
    if not isinstance(projection, dict) or projection.get("output_blind") is not True:
        issues.append("visual plan is not output-blind")
    render = plan.get("render_specification", {})
    expected = {
        "renderer": "poppler-pdftoppm",
        "renderer_version": "26.01.0",
        "command": "pdftoppm -f PAGE -l PAGE -singlefile -r 300 -png INPUT OUTPUT_PREFIX",
        "page_index_origin": 1,
        "resolution_dpi": 300,
        "output_format": "png",
        "color_space": "rgb",
        "full_page": True,
        "preserve_source_orientation": True,
        "shared_render_rule": "all_ocr_variants_consume_the_same_digest_frozen_png_bytes",
        "render_status_at_plan_freeze": "not_started",
    }
    if not isinstance(render, dict):
        issues.append("render_specification must be an object")
    else:
        for key, value in expected.items():
            if render.get(key) != value:
                issues.append(f"render_specification.{key} drifted")
        preprocessing = render.get("preprocessing")
        if not isinstance(preprocessing, dict) or set(preprocessing.values()) != {False}:
            issues.append("all primary render preprocessing switches must be false")
    reveal = plan.get("reference_witness_reveal_law", {})
    if not isinstance(reveal, dict) or reveal.get("state") != "sealed" or reveal.get("may_seed_drafts") is not False:
        issues.append("reference witnesses are not sealed from draft generation")
    gold = plan.get("gold_gate", {})
    if not isinstance(gold, dict) or gold.get("human_gold_materialized") is not False:
        issues.append("this renderer expects the declared pre-gold state")
    groups = plan.get("source_groups")
    if not isinstance(groups, list) or len(groups) != 3:
        issues.append("visual plan must contain exactly three source groups")
        return issues
    samples: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            issues.append("source group must be an object")
            continue
        group_samples = group.get("samples")
        if group.get("sample_count") != 12 or not isinstance(group_samples, list) or len(group_samples) != 12:
            issues.append(f"{group.get('group_id')}: expected exactly 12 samples")
            continue
        samples.extend(sample for sample in group_samples if isinstance(sample, dict))
    sample_ids = [sample.get("sample_id") for sample in samples]
    if len(samples) != 36 or len(set(sample_ids)) != 36:
        issues.append("visual plan must contain 36 unique samples")
    if sum(bool(sample.get("gold_candidate")) for sample in samples) != 15:
        issues.append("visual plan must retain five gold candidates per source")
    return issues


def _manifest_index(tree_repo_root: Path) -> dict[str, tuple[dict[str, Any], Path]]:
    source_root = tree_repo_root / "ToS/source-witnesses"
    manifests: dict[str, tuple[dict[str, Any], Path]] = {}
    for path in sorted(source_root.rglob("item.manifest.json")):
        payload = _load_json(path)
        item_id = payload.get("item_id")
        if isinstance(item_id, str):
            if item_id in manifests:
                raise OcrRenderError(f"duplicate item manifest for {item_id}")
            manifests[item_id] = (payload, path)
    return manifests


def _payload_for_group(
    group: dict[str, Any], manifests: dict[str, tuple[dict[str, Any], Path]]
) -> Path:
    item_ref = str(group.get("item_ref"))
    file_ref = group.get("file_ref")
    target = manifests.get(item_ref)
    if target is None:
        raise OcrRenderError(f"no item manifest for {item_ref}")
    manifest, manifest_path = target
    for payload in manifest.get("payload_files", []):
        if isinstance(payload, dict) and payload.get("file_id") == file_ref:
            source_path = manifest_path.parent / str(payload.get("relative_path"))
            if not source_path.is_file() or source_path.suffix.lower() != ".pdf":
                raise OcrRenderError(f"visual source PDF is missing: {source_path}")
            actual = _sha256_file(source_path)
            expected = str(group.get("file_sha256"))
            if actual != expected or actual != payload.get("sha256"):
                raise OcrRenderError(f"source payload digest drift for {file_ref}: {actual}")
            return source_path
    raise OcrRenderError(f"item {item_ref} has no payload {file_ref}")


def _pdftoppm_version(command: Path) -> str:
    completed = subprocess.run(
        (command.as_posix(), "-v"), check=False, capture_output=True, text=True, timeout=10
    )
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    match = re.search(r"pdftoppm version ([0-9.]+)", combined)
    if completed.returncode != 0 or match is None:
        raise OcrRenderError(f"cannot resolve pdftoppm version: {combined[:240]}")
    return match.group(1)


def _render_set_digest(renders: list[dict[str, Any]]) -> str:
    return _canonical_sha256(
        [
            {
                "sample_id": row["sample_id"],
                "png_sha256": row["png_sha256"],
                "png_bytes": row["png_bytes"],
                "width_pixels": row["width_pixels"],
                "height_pixels": row["height_pixels"],
            }
            for row in renders
        ]
    )


def verify_render_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path.resolve())
    issues = _schema_issues(manifest)
    artifact_root = Path(str(manifest.get("artifact_root", ""))).resolve()
    renders = manifest.get("renders", [])
    if isinstance(renders, list):
        for row in renders:
            if not isinstance(row, dict):
                continue
            path = artifact_root / str(row.get("png_ref", ""))
            if not _within(path, artifact_root) or not path.is_file():
                issues.append(f"missing or escaped render for {row.get('sample_id')}")
                continue
            actual = _sha256_file(path)
            if actual != row.get("png_sha256") or path.stat().st_size != row.get("png_bytes"):
                issues.append(f"render fixity drift for {row.get('sample_id')}")
            try:
                header = png_header(path)
            except OcrRenderError as exc:
                issues.append(str(exc))
            else:
                for key in ("width_pixels", "height_pixels", "bit_depth", "png_color_type", "color_space"):
                    if header[key] != row.get(key):
                        issues.append(f"render header drift for {row.get('sample_id')}: {key}")
        if all(isinstance(row, dict) for row in renders):
            if _render_set_digest(renders) != manifest.get("render_set_sha256"):
                issues.append("render_set_sha256 does not close over current render rows")
    if issues:
        raise OcrRenderError("invalid OCR render manifest: " + "; ".join(issues))
    return manifest


def materialize_ocr_render(
    tree_repo_root: Path,
    sample_plan_path: Path,
    render_id: str,
    *,
    shared_root: Path = DEFAULT_SHARED_ROOT,
    pdftoppm: Path = Path("/usr/bin/pdftoppm"),
    tree_local_manifest: Path | None = None,
    invocation: list[str],
) -> dict[str, Any]:
    """Render all frozen pages once and return the validated manifest."""

    if not RENDER_ID_RE.fullmatch(render_id):
        raise OcrRenderError("render-id must use lowercase letters, digits, dot, underscore, and hyphen")
    tree_repo_root = tree_repo_root.resolve()
    sample_plan_path = sample_plan_path.resolve()
    shared_root = shared_root.resolve()
    if not _within(shared_root, DEFAULT_SHARED_ROOT):
        raise OcrRenderError(f"shared render root must stay under {DEFAULT_SHARED_ROOT}")
    render_root = shared_root / render_id
    if render_root.exists():
        raise OcrRenderError(f"render path already exists: {render_root}")

    plan = _load_json(sample_plan_path)
    plan_issues = validate_visual_plan(plan)
    if plan_issues:
        raise OcrRenderError("invalid frozen visual plan: " + "; ".join(plan_issues))
    expected_local = tree_repo_root / str(plan["render_specification"]["render_manifest_ref"])
    if tree_local_manifest is not None and tree_local_manifest.resolve() != expected_local.resolve():
        raise OcrRenderError(f"tree-local manifest must match the frozen plan route: {expected_local}")
    if tree_local_manifest is not None and tree_local_manifest.exists():
        raise OcrRenderError(f"tree-local render manifest already exists: {tree_local_manifest}")

    renderer_version = _pdftoppm_version(pdftoppm)
    if renderer_version != plan["render_specification"]["renderer_version"]:
        raise OcrRenderError(
            f"pdftoppm version drift: {renderer_version} != {plan['render_specification']['renderer_version']}"
        )

    render_root.mkdir(parents=True, exist_ok=False)
    pages_root = render_root / "pages"
    pages_root.mkdir()
    receipt_path = render_root / "render.receipt.json"
    receipt: dict[str, Any] = {
        "schema_version": "tos_ocr_render_receipt_v1",
        "render_id": render_id,
        "status": "running",
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "sample_plan_ref": sample_plan_path.as_posix(),
        "sample_plan_sha256": _sha256_file(sample_plan_path),
        "invocation": invocation,
        "errors": [],
    }
    _write_json(receipt_path, receipt)

    try:
        manifests = _manifest_index(tree_repo_root)
        source_files: list[dict[str, Any]] = []
        renders: list[dict[str, Any]] = []
        for group in plan["source_groups"]:
            source_path = _payload_for_group(group, manifests)
            source_files.append(
                {
                    "group_id": group["group_id"],
                    "item_ref": group["item_ref"],
                    "file_ref": group["file_ref"],
                    "file_sha256": group["file_sha256"],
                    "language": group["language"],
                    "local_path": source_path.as_posix(),
                }
            )
            for sample in group["samples"]:
                output_prefix = pages_root / str(sample["sample_id"])
                output_path = output_prefix.with_suffix(".png")
                command = (
                    pdftoppm.as_posix(),
                    "-f",
                    str(sample["page"]),
                    "-l",
                    str(sample["page"]),
                    "-singlefile",
                    "-r",
                    "300",
                    "-png",
                    source_path.as_posix(),
                    output_prefix.as_posix(),
                )
                started = time.perf_counter()
                completed = subprocess.run(command, check=False, capture_output=True, timeout=300)
                elapsed = time.perf_counter() - started
                if completed.returncode != 0 or not output_path.is_file():
                    stderr = completed.stderr.decode("utf-8", errors="replace")
                    raise OcrRenderError(
                        f"pdftoppm failed for {sample['sample_id']} with {completed.returncode}: {stderr[:300]}"
                    )
                header = png_header(output_path)
                if header["bit_depth"] != 8 or header["png_color_type"] != 2 or header["color_space"] != "rgb":
                    raise OcrRenderError(
                        f"render is not 8-bit RGB for {sample['sample_id']}: {header}"
                    )
                renders.append(
                    {
                        "sample_id": sample["sample_id"],
                        "group_id": group["group_id"],
                        "item_ref": group["item_ref"],
                        "file_ref": group["file_ref"],
                        "source_file_sha256": group["file_sha256"],
                        "anchor_ref": sample["anchor_ref"],
                        "language": group["language"],
                        "page": sample["page"],
                        "difficulty": sample["difficulty"],
                        "gold_candidate": sample["gold_candidate"],
                        "png_ref": output_path.relative_to(render_root).as_posix(),
                        "png_sha256": _sha256_file(output_path),
                        "png_bytes": output_path.stat().st_size,
                        **header,
                        "elapsed_seconds": elapsed,
                        "stderr_sha256": _sha256_bytes(completed.stderr),
                    }
                )

        manifest = {
            "schema_version": "tos_ocr_render_manifest_v1",
            "render_id": render_id,
            "experiment_id": "tos-ocr-foundation-v1",
            "status": "frozen",
            "created_at_utc": _utc_now(),
            "sample_plan_ref": sample_plan_path.as_posix(),
            "sample_plan_sha256": _sha256_file(sample_plan_path),
            "renderer": "poppler-pdftoppm",
            "renderer_version": renderer_version,
            "render_specification": {
                "resolution_dpi": 300,
                "output_format": "png",
                "color_space": "rgb",
                "full_page": True,
                "preserve_source_orientation": True,
                "preprocessing": dict(plan["render_specification"]["preprocessing"]),
                "command_template": plan["render_specification"]["command"],
            },
            "artifact_root": render_root.as_posix(),
            "source_files": source_files,
            "renders": renders,
            "render_set_sha256": _render_set_digest(renders),
            "sample_count": len(renders),
            "total_png_bytes": sum(row["png_bytes"] for row in renders),
            "reference_witness_state": "sealed-not-consulted",
            "authority_boundary": "frozen shared pixels and mechanical provenance only; no OCR, source-text, or quality verdict",
        }
        issues = _schema_issues(manifest)
        if issues:
            raise OcrRenderError("generated render manifest is invalid: " + "; ".join(issues))
        manifest_path = render_root / "render-manifest.v1.json"
        _write_json(manifest_path, manifest)
        verify_render_manifest(manifest_path)
        if tree_local_manifest is not None:
            tree_local_manifest.parent.mkdir(parents=True, exist_ok=True)
            tree_local_manifest.write_bytes(manifest_path.read_bytes())
        receipt.update(
            {
                "status": "frozen",
                "finished_at_utc": _utc_now(),
                "manifest_ref": manifest_path.as_posix(),
                "manifest_sha256": _sha256_file(manifest_path),
                "render_set_sha256": manifest["render_set_sha256"],
                "sample_count": len(renders),
            }
        )
        _write_json(receipt_path, receipt)
        return manifest
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)]
        _write_json(receipt_path, receipt)
        if isinstance(exc, OcrRenderError):
            raise
        raise OcrRenderError(str(exc)) from exc
