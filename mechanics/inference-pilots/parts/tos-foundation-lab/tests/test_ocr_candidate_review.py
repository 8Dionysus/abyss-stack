from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest


PART_ROOT = Path(__file__).resolve().parents[1]
if str(PART_ROOT) not in sys.path:
    sys.path.insert(0, str(PART_ROOT))

import ocr_candidate_review as candidate_review


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _png_header_bytes(width: int = 20, height: int = 30) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


def _source_packet(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "source-packet"
    pages = root / "pages"
    pages.mkdir(parents=True)
    units: list[dict[str, Any]] = []
    for source_index, language in ((1, "ru"), (2, "ru"), (3, "de")):
        page_refs: dict[str, str] = {}
        for offset, role in ((-1, "previous"), (0, "current"), (1, "next")):
            page = max(1, source_index * 10 + offset)
            ref = f"pages/source-{source_index:02d}-{role}.png"
            (root / ref).write_bytes(_png_header_bytes(page, page + 1))
            page_refs[role] = ref
        units.append(
            {
                "sample_id": f"tos-sample-source-{source_index:02d}",
                "visual_sample_id": f"tos-ocr-sample-source-{source_index:02d}",
                "source_anchor_ref": f"tos.anchor.source.{source_index:02d}",
                "group_id": "ocr-antonovsky-2007",
                "language": language,
                "pdf_page": source_index * 10,
                "difficulty": "ordinary",
                "strata": ["synthetic"],
                "previous_page_ref": page_refs["previous"],
                "current_page_ref": page_refs["current"],
                "next_page_ref": page_refs["next"],
            }
        )
    manifest_path = root / "human-gold-review-manifest.json"
    _write_json(
        manifest_path,
        {
            "packet_id": "synthetic-source-packet",
            "units": units,
        },
    )
    return manifest_path, {
        "packet_id": "synthetic-source-packet",
        "units": units,
    }


def _candidate_runs(
    tmp_path: Path, source_manifest: dict[str, Any]
) -> list[Path]:
    roots: list[Path] = []
    for variant in ("A", "B", "C"):
        run_id = f"synthetic-ocr-{variant.lower()}-run"
        root = tmp_path / "runs" / variant
        sample_ids = [
            str(unit["visual_sample_id"]) for unit in source_manifest["units"]
        ]
        _write_json(
            root / "run.receipt.json",
            {
                "schema_version": "synthetic_run_receipt_v1",
                "experiment_id": "tos-ocr-foundation-v1",
                "run_id": run_id,
                "variant": variant,
                "status": "stopped" if variant == "B" else "awaiting-manual-review",
                "method_revision": {"synthetic": variant},
                "sample_ids": sample_ids,
            },
        )
        for sample_id in sample_ids:
            output = root / "raw-output" / sample_id / "recognition.txt"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                f"{variant}: visible OCR for {sample_id}.\n",
                encoding="utf-8",
            )
        roots.append(root)
    return roots


def test_materializes_blind_candidate_packet_and_private_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path, source_manifest = _source_packet(tmp_path)
    monkeypatch.setattr(
        candidate_review,
        "verify_human_gold_review_manifest",
        lambda path: source_manifest
        if path == source_path
        else pytest.fail(f"unexpected source packet: {path}"),
    )
    run_roots = _candidate_runs(tmp_path, source_manifest)
    shared_root = tmp_path / "shared"

    manifest = candidate_review.materialize_ocr_candidate_review(
        source_path,
        run_roots,
        "synthetic-candidate-review",
        languages=("ru",),
        shared_root=shared_root,
        invocation=["synthetic-test"],
    )

    packet_root = shared_root / "synthetic-candidate-review"
    manifest_path = packet_root / "ocr-candidate-review-manifest.json"
    assert manifest["source_count"] == 2
    assert manifest["candidate_run_count"] == 3
    assert manifest["unit_count"] == 6
    assert manifest["language_scope"] == ["ru"]
    assert manifest["method_identity_visible"] is False
    assert manifest["candidate_text_visible"] is True
    assert stat.S_IMODE(packet_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o400
    public_manifest = json.dumps(manifest)
    for variant in ("a", "b", "c"):
        assert f"synthetic-ocr-{variant}-run" not in public_manifest

    blind_map = json.loads(
        (packet_root / manifest["blind_map"]["ref"]).read_text(encoding="utf-8")
    )
    assert len(blind_map["entries"]) == 6
    assert {entry["variant"] for entry in blind_map["entries"]} == {
        "A",
        "B",
        "C",
    }

    session_dir = candidate_review.initialize_ocr_candidate_review_session(
        manifest_path,
        "synthetic-candidate-session",
        review_root=tmp_path / "human-review",
    )
    session = json.loads(
        (session_dir / "review-session.json").read_text(encoding="utf-8")
    )
    assert session["packet"]["candidate_set_sha256"] == manifest[
        "candidate_set_sha256"
    ]
    assert session["status"] == "awaiting-real-human-candidate-review"
    assert stat.S_IMODE(session_dir.stat().st_mode) == 0o700


def test_candidate_packet_verifier_detects_candidate_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path, source_manifest = _source_packet(tmp_path)
    monkeypatch.setattr(
        candidate_review,
        "verify_human_gold_review_manifest",
        lambda path: source_manifest,
    )
    manifest = candidate_review.materialize_ocr_candidate_review(
        source_path,
        _candidate_runs(tmp_path, source_manifest),
        "synthetic-candidate-drift",
        languages=("ru",),
        shared_root=tmp_path / "shared",
    )
    packet_root = tmp_path / "shared" / "synthetic-candidate-drift"
    candidate_path = packet_root / manifest["units"][0]["candidate_ref"]
    os.chmod(candidate_path, 0o600)
    candidate_path.write_text(
        candidate_path.read_text(encoding="utf-8") + "drift",
        encoding="utf-8",
    )

    with pytest.raises(
        candidate_review.OcrCandidateReviewError,
        match="candidate fixity drifted",
    ):
        candidate_review.verify_ocr_candidate_review_manifest(
            packet_root / "ocr-candidate-review-manifest.json"
        )
