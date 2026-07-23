#!/usr/bin/env python3
"""Execute the deterministic native-structure pilot over a frozen ToS sample.

The runner copies derived text only into the private laboratory run packet. It
never changes Tree of Sophia source records and never treats native extraction
as accepted transcription.
"""

from __future__ import annotations

import hashlib
import json
import platform
import resource
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class NativeStructureError(RuntimeError):
    """Raised when a frozen native-structure run cannot be executed safely."""


class _VisibleTextParser(HTMLParser):
    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "figcaption",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "p",
        "section",
        "table",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._suppressed_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"head", "script", "style"}:
            self._suppressed_depth += 1
        elif tag in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"head", "script", "style"} and self._suppressed_depth:
            self._suppressed_depth -= 1
        elif tag in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._suppressed_depth:
            self._parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._parts).splitlines()]
        return "\n".join(line for line in lines if line) + "\n"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeStructureError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise NativeStructureError(f"{path} must contain a JSON object")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise NativeStructureError(f"cannot read {path}: {exc}") from exc
    for number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise NativeStructureError(f"cannot read {path}:{number}: {exc}") from exc
        if not isinstance(record, dict):
            raise NativeStructureError(f"{path}:{number} must contain a JSON object")
        records.append(record)
    return records


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records)
    path.write_text(body, encoding="utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_xhtml_text(data: bytes) -> str:
    parser = _VisibleTextParser()
    parser.feed(data.decode("utf-8", errors="replace"))
    parser.close()
    return parser.text()


def _tool_version(arguments: tuple[str, ...]) -> str:
    completed = subprocess.run(arguments, check=False, capture_output=True, text=True, timeout=10)
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if completed.returncode != 0 or not combined:
        raise NativeStructureError(f"cannot capture version for {' '.join(arguments)}")
    return combined.splitlines()[0][:240]


def _manifest_index(tree_repo_root: Path) -> dict[str, tuple[dict[str, Any], Path]]:
    source_root = tree_repo_root / "ToS/source-witnesses"
    manifests: dict[str, tuple[dict[str, Any], Path]] = {}
    for path in sorted(source_root.rglob("item.manifest.json")):
        payload = _load_json(path)
        item_id = payload.get("item_id")
        if isinstance(item_id, str):
            if item_id in manifests:
                raise NativeStructureError(f"duplicate item manifest for {item_id}")
            manifests[item_id] = (payload, path)
    return manifests


def _payload_for_group(
    group: dict[str, Any], manifests: dict[str, tuple[dict[str, Any], Path]]
) -> Path:
    item_ref = group.get("item_ref")
    file_ref = group.get("file_ref")
    target = manifests.get(str(item_ref))
    if target is None:
        raise NativeStructureError(f"no manifest for {item_ref}")
    manifest, manifest_path = target
    for payload in manifest.get("payload_files", []):
        if isinstance(payload, dict) and payload.get("file_id") == file_ref:
            source_path = manifest_path.parent / str(payload.get("relative_path"))
            if not source_path.is_file():
                raise NativeStructureError(f"source payload is missing: {source_path}")
            actual = _sha256_file(source_path)
            if actual != payload.get("sha256") or actual != group.get("file_sha256"):
                raise NativeStructureError(f"source payload digest drift for {file_ref}: {actual}")
            return source_path
    raise NativeStructureError(f"manifest {item_ref} has no payload {file_ref}")


def _pdf_page(
    source_path: Path, page: int
) -> tuple[str, dict[str, Any]]:
    command = (
        "pdftotext",
        "-f",
        str(page),
        "-l",
        str(page),
        "-layout",
        "-enc",
        "UTF-8",
        source_path.as_posix(),
        "-",
    )
    started = time.perf_counter()
    completed = subprocess.run(command, check=False, capture_output=True, timeout=120)
    elapsed = time.perf_counter() - started
    text = completed.stdout.decode("utf-8", errors="replace")
    warnings: list[str] = []
    if completed.returncode != 0:
        warnings.append(f"pdftotext-returncode:{completed.returncode}")
    if not text.replace("\f", "").strip():
        warnings.append("no-native-text")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    return text, {
        "method": "pdftotext-layout",
        "command": list(command[:-2]) + ["<immutable-source-payload>", "-"],
        "returncode": completed.returncode,
        "elapsed_seconds": elapsed,
        "stderr_sha256": _sha256_bytes(completed.stderr),
        "stderr_line_count": len(stderr.splitlines()),
        "warnings": warnings,
    }


def _epub_member(
    source_path: Path, member_path: str, expected_sha256: str
) -> tuple[str, dict[str, Any]]:
    started = time.perf_counter()
    try:
        with zipfile.ZipFile(source_path) as archive:
            raw = archive.read(member_path)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise NativeStructureError(f"cannot extract {member_path} from {source_path}: {exc}") from exc
    actual = _sha256_bytes(raw)
    if actual != expected_sha256:
        raise NativeStructureError(
            f"container member digest drift for {member_path}: {actual} != {expected_sha256}"
        )
    text = extract_xhtml_text(raw)
    elapsed = time.perf_counter() - started
    warnings: list[str] = []
    if not text.strip():
        warnings.append("no-native-text")
    return text, {
        "method": "python-zipfile-htmlparser",
        "member_path": member_path,
        "member_sha256": actual,
        "elapsed_seconds": elapsed,
        "warnings": warnings,
    }


def _pdf_inventory(source_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ("pdfinfo", source_path.as_posix()),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    fields: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    return {
        "container": "pdf",
        "returncode": completed.returncode,
        "pages": int(fields["Pages"]) if fields.get("Pages", "").isdigit() else None,
        "page_size": fields.get("Page size"),
        "pdf_version": fields.get("PDF version"),
        "encrypted": fields.get("Encrypted"),
        "metadata": fields,
    }


def _epub_inventory(source_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(source_path) as archive:
        members = archive.infolist()
    return {
        "container": "epub-zip",
        "member_count": len(members),
        "xhtml_member_count": sum(
            item.filename.lower().endswith((".html", ".xhtml")) for item in members
        ),
        "compressed_bytes": sum(item.compress_size for item in members),
        "uncompressed_bytes": sum(item.file_size for item in members),
    }


def _relative(run_root: Path, path: Path) -> str:
    return path.relative_to(run_root).as_posix()


def execute_native_structure(
    run_root: Path,
    tree_repo_root: Path,
    sample_plan_path: Path,
    *,
    invocation: list[str],
) -> dict[str, Any]:
    """Execute frozen Structure A and leave the packet awaiting manual review."""

    run_root = run_root.resolve()
    tree_repo_root = tree_repo_root.resolve()
    sample_plan_path = sample_plan_path.resolve()
    receipt_path = run_root / "run.receipt.json"
    receipt = _load_json(receipt_path)
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if receipt.get("experiment_id") != "tos-structure-recovery-v1" or receipt.get("variant") != "A":
        raise NativeStructureError("native structure runner requires prepared Structure A")
    if receipt.get("status") != "prepared" or preflight.get("decision") != "ready":
        raise NativeStructureError("run must be prepared from a ready preflight")
    if experiment.get("family") != "structure":
        raise NativeStructureError("experiment specification is not a structure experiment")

    sample_plan = _load_json(sample_plan_path)
    if sample_plan.get("status") != "frozen" or sample_plan.get("frozen_before_variant_outputs") is not True:
        raise NativeStructureError("sample plan is not frozen before outputs")
    anchors = {
        record["anchor_id"]: record
        for record in _load_jsonl(sample_plan_path.parent / "anchors.jsonl")
        if isinstance(record.get("anchor_id"), str)
    }
    manifests = _manifest_index(tree_repo_root)
    started_at = _utc_now()
    wall_started = time.perf_counter()
    receipt["status"] = "running"
    receipt["started_at_utc"] = started_at
    _write_json(receipt_path, receipt)

    artifact_refs: list[str] = []
    samples: list[dict[str, Any]] = []
    anchor_map: list[dict[str, Any]] = []
    inventories: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    source_map: list[dict[str, Any]] = []
    try:
        for group in sample_plan.get("source_groups", []):
            if not isinstance(group, dict):
                continue
            source_path = _payload_for_group(group, manifests)
            source_map.append(
                {
                    "item_ref": group["item_ref"],
                    "file_ref": group["file_ref"],
                    "file_sha256": group["file_sha256"],
                    "local_path": source_path.as_posix(),
                    "access": "read-only immutable source payload",
                }
            )
            if source_path.suffix.lower() == ".pdf":
                inventory = _pdf_inventory(source_path)
            elif source_path.suffix.lower() == ".epub":
                inventory = _epub_inventory(source_path)
            else:
                raise NativeStructureError(f"unsupported source format: {source_path}")
            inventory.update(
                {
                    "item_ref": group["item_ref"],
                    "file_ref": group["file_ref"],
                    "file_sha256": group["file_sha256"],
                }
            )
            inventories.append(inventory)

            for sample in group.get("samples", []):
                if not isinstance(sample, dict):
                    continue
                sample_id = str(sample["sample_id"])
                anchor = anchors.get(str(sample["anchor_ref"]))
                if anchor is None:
                    raise NativeStructureError(f"unresolved anchor for {sample_id}")
                selectors = anchor.get("selectors", [])
                page_selector = next(
                    (
                        selector
                        for selector in selectors
                        if isinstance(selector, dict) and selector.get("type") == "page_region"
                    ),
                    None,
                )
                member_selector = next(
                    (
                        selector
                        for selector in selectors
                        if isinstance(selector, dict) and selector.get("type") == "container_member"
                    ),
                    None,
                )
                if isinstance(page_selector, dict):
                    text, method = _pdf_page(source_path, int(page_selector["page"]))
                    unit = {"page": int(page_selector["page"])}
                elif isinstance(member_selector, dict):
                    text, method = _epub_member(
                        source_path,
                        str(member_selector["member_path"]),
                        str(member_selector["member_sha256"]),
                    )
                    unit = {"container_member": str(member_selector["member_path"])}
                else:
                    raise NativeStructureError(f"unsupported selector for {sample_id}")

                text_path = run_root / "raw-output" / f"{sample_id}.txt"
                metadata_path = run_root / "raw-output" / f"{sample_id}.json"
                text_path.write_text(text, encoding="utf-8")
                metadata = {
                    "sample_id": sample_id,
                    "anchor_ref": sample["anchor_ref"],
                    "item_ref": group["item_ref"],
                    "file_ref": group["file_ref"],
                    "source_file_sha256": group["file_sha256"],
                    "unit": unit,
                    "native_text_ref": _relative(run_root, text_path),
                    "native_text_sha256": _sha256_file(text_path),
                    "native_text_bytes": text_path.stat().st_size,
                    "native_text_characters": len(text),
                    "native_text_non_whitespace_characters": len("".join(text.split())),
                    "method": method,
                    "content_status": "unreviewed-native-extraction",
                    "authority_boundary": "not a transcription and not source truth until source-visible human review",
                }
                _write_json(metadata_path, metadata)
                artifact_refs.extend(
                    [_relative(run_root, text_path), _relative(run_root, metadata_path)]
                )
                samples.append(metadata)
                anchor_map.append(
                    {
                        "sample_id": sample_id,
                        "source_anchor_ref": sample["anchor_ref"],
                        "derived_text_ref": _relative(run_root, text_path),
                        "derived_text_sha256": metadata["native_text_sha256"],
                        "resolution_status": "mechanically-resolved-unreviewed",
                    }
                )
                for warning in method.get("warnings", []):
                    warnings.append({"sample_id": sample_id, "warning": str(warning)})

        source_map_path = run_root / "inputs/source-map.json"
        inventory_path = run_root / "raw-output/container-inventory.json"
        anchor_map_path = run_root / "raw-output/anchor-map.jsonl"
        warnings_path = run_root / "raw-output/warnings.json"
        _write_json(
            source_map_path,
            {
                "sample_plan_ref": sample_plan_path.as_posix(),
                "sample_plan_sha256": _sha256_file(sample_plan_path),
                "sources": source_map,
                "visibility": "private-runtime-only",
            },
        )
        _write_json(inventory_path, {"sources": inventories})
        _write_jsonl(anchor_map_path, anchor_map)
        _write_json(warnings_path, {"warnings": warnings})
        artifact_refs.extend(
            [
                _relative(run_root, source_map_path),
                _relative(run_root, inventory_path),
                _relative(run_root, anchor_map_path),
                _relative(run_root, warnings_path),
            ]
        )

        elapsed = time.perf_counter() - wall_started
        artifact_bytes = sum(
            path.stat().st_size
            for path in run_root.rglob("*")
            if path.is_file() and path != receipt_path
        )
        empty_samples = [
            sample["sample_id"]
            for sample in samples
            if sample["native_text_non_whitespace_characters"] == 0
        ]
        metrics = {
            "schema_version": "tos_native_structure_metrics_v1",
            "experiment_id": receipt["experiment_id"],
            "variant": "A",
            "sample_count": len(samples),
            "source_count": len(inventories),
            "wall_seconds": elapsed,
            "units_per_minute": (len(samples) * 60 / elapsed) if elapsed else None,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "artifact_bytes": artifact_bytes,
            "native_nonempty_count": len(samples) - len(empty_samples),
            "native_empty_count": len(empty_samples),
            "native_empty_sample_ids": empty_samples,
            "warning_count": len(warnings),
            "quality": {
                "status": "not-computable",
                "reason": "double-source-visible human gold is not complete",
            },
            "human_cost": {
                "status": "not-measured",
                "reason": "no real human correction pass has occurred",
            },
            "traceability": {
                "mechanical_anchor_resolution": len(anchor_map) / len(samples) if samples else None,
                "content_acceptance": "not-reviewed",
            },
            "authority_boundary": "speed and machine-cost observations only; no content-quality verdict",
        }
        metrics_path = run_root / "metrics/native-structure-summary.json"
        _write_json(metrics_path, metrics)

        version = _tool_version(("pdftotext", "-v"))
        invocation_path = run_root / "receipts/native-structure-invocation.json"
        _write_json(
            invocation_path,
            {
                "captured_at_utc": started_at,
                "argv": invocation,
                "python": platform.python_version(),
                "pdftotext": version,
                "runner_sha256": _sha256_file(Path(__file__)),
                "sample_plan_sha256": _sha256_file(sample_plan_path),
                "source_file_sha256": [source["file_sha256"] for source in source_map],
                "rights_posture": "restricted-source-derived-text-private-runtime-only",
            },
        )
        artifact_refs.append(_relative(run_root, invocation_path))

        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = [sample["sample_id"] for sample in samples]
        receipt["method_revision"] = {
            "implementation": "poppler-utils plus Python standard library HTML parsing",
            "version": version,
            "runtime": f"Python {platform.python_version()}",
            "model": None,
            "artifact_digest": _sha256_file(Path(__file__)),
        }
        receipt["invocation_ref"] = _relative(run_root, invocation_path)
        receipt["artifact_refs"] = sorted(set(artifact_refs))
        receipt["metric_refs"] = [_relative(run_root, metrics_path)]
        receipt["manual_review_refs"] = []
        receipt["errors"] = []
        _write_json(receipt_path, receipt)
        return metrics
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["finished_at_utc"] = _utc_now()
        receipt["errors"] = [str(exc)]
        _write_json(receipt_path, receipt)
        if isinstance(exc, NativeStructureError):
            raise
        raise NativeStructureError(str(exc)) from exc
