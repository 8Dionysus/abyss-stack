from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import stat
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest


PART_ROOT = Path(__file__).resolve().parents[1]
if str(PART_ROOT) not in sys.path:
    sys.path.insert(0, str(PART_ROOT))

import human_review_workbench as workbench


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _load_feedback(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _review_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    protocol_name: str,
) -> tuple[Path, Path, dict[str, Any]]:
    allowed_root = tmp_path / "human-review"
    session_dir = allowed_root / f"{protocol_name}-session"
    packet_root = tmp_path / "immutable-packets" / protocol_name
    session_dir.mkdir(parents=True)
    (packet_root / "pages").mkdir(parents=True)

    for role in ("previous", "current", "next"):
        (packet_root / "pages" / f"{role}.png").write_bytes(
            b"\x89PNG\r\n\x1a\n" + role.encode("ascii")
        )

    if protocol_name == "gold":
        protocol = workbench.GOLD_PROTOCOL
        unit_ids = [f"tos-sample-synthetic-{index:03d}" for index in range(15)]
        template_rows = [
            {
                "sample_id": unit_id,
                "source_pages": {
                    role: f"pages/{role}.png"
                    for role in ("previous", "current", "next")
                },
            }
            for unit_id in unit_ids
        ]
        manifest_units = [
            {
                "sample_id": unit_id,
                "group_id": "ocr-antonovsky-2007",
                "language": "de" if index >= 10 else "ru",
                "pdf_page": index + 1,
                "difficulty": "ordinary",
                "strata": ["synthetic"],
            }
            for index, unit_id in enumerate(unit_ids)
        ]
        plan_path = None
    elif protocol_name == "german":
        protocol = workbench.GERMAN_PROTOCOL
        unit_ids = [
            f"tos-translation-source-review-v2-{index:03d}"
            for index in range(1, 31)
        ]
        template_rows = [
            {
                "review_unit_id": unit_id,
                "source_pages": {
                    role: f"pages/{role}.png"
                    for role in ("previous", "current", "next")
                },
            }
            for unit_id in unit_ids
        ]
        manifest_units = [{"review_unit_id": unit_id} for unit_id in unit_ids]
        plan_path = packet_root / "translation-source-review-plan.v2.json"
        _write_json(
            plan_path,
            {
                "units": [
                    {
                        "review_unit_id": unit_id,
                        "visual_context": {
                            "previous_pdf_page": index,
                            "current_pdf_page": index + 1,
                            "next_pdf_page": index + 2,
                        },
                        "layout_posture": "prose-at-page-start",
                        "selection_instruction": (
                            "confirm-visible-complete-prose-unit-without-reusing-v1-text"
                        ),
                    }
                    for index, unit_id in enumerate(unit_ids, start=1)
                ]
            },
        )
    elif protocol_name == "candidate":
        protocol = workbench.OCR_CANDIDATE_PROTOCOL
        unit_ids = [
            f"tos-sample-synthetic-{source:02d}-candidate-{candidate}"
            for source in range(1, 3)
            for candidate in ("a", "b", "c")
        ]
        template_rows = [
            {
                "review_unit_id": unit_id,
                "source_pages": {
                    role: f"pages/{role}.png"
                    for role in ("previous", "current", "next")
                },
            }
            for unit_id in unit_ids
        ]
        manifest_units = []
        for index, unit_id in enumerate(unit_ids):
            source_index = index // 3 + 1
            candidate_position = index % 3 + 1
            candidate_path = packet_root / "candidates" / f"{unit_id}.txt"
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_text(
                f"Synthetic OCR candidate {candidate_position} for page {source_index}.",
                encoding="utf-8",
            )
            manifest_units.append(
                {
                    "review_unit_id": unit_id,
                    "source_sample_id": f"tos-sample-synthetic-{source_index:02d}",
                    "visual_sample_id": f"tos-ocr-sample-synthetic-{source_index:02d}",
                    "source_anchor_ref": f"tos.anchor.synthetic.{source_index:02d}",
                    "group_id": "ocr-antonovsky-2007",
                    "language": "ru",
                    "pdf_page": source_index,
                    "difficulty": "ordinary",
                    "strata": ["synthetic"],
                    "candidate_label": f"Кандидат {chr(65 + candidate_position - 1)}",
                    "candidate_position": candidate_position,
                    "candidate_count_for_source": 3,
                    "candidate_ref": candidate_path.relative_to(packet_root).as_posix(),
                    "candidate_sha256": _sha256(candidate_path),
                    "candidate_bytes": candidate_path.stat().st_size,
                    "source_pages": {
                        role: f"pages/{role}.png"
                        for role in ("previous", "current", "next")
                    },
                }
            )
        plan_path = None
    else:  # pragma: no cover - fixture misuse
        raise AssertionError(f"unknown protocol fixture: {protocol_name}")

    template_path = packet_root / "reviews" / "template.jsonl"
    _write_jsonl(template_path, template_rows)
    manifest: dict[str, Any] = {
        "packet_id": f"synthetic-{protocol_name}-packet",
        "units": manifest_units,
        "review_template": {
            "ref": template_path.relative_to(packet_root).as_posix(),
            "sha256": _sha256(template_path),
        },
    }
    if protocol is workbench.OCR_CANDIDATE_PROTOCOL:
        manifest["unit_count"] = len(unit_ids)
    if plan_path is not None:
        manifest["review_plan_ref"] = plan_path.as_posix()

    manifest_path = packet_root / protocol.manifest_filename
    _write_json(manifest_path, manifest)
    session_payload = {
        "schema_version": f"synthetic_{protocol_name}_session_v1",
        "session_id": f"synthetic-{protocol_name}-session",
        "private_local_only": True,
        "packet": {
            "packet_id": manifest["packet_id"],
            "root": packet_root.as_posix(),
            "manifest_sha256": _sha256(manifest_path),
        },
    }
    if protocol is workbench.OCR_CANDIDATE_PROTOCOL:
        session_payload["protocol_id"] = protocol.protocol_id
    _write_json(session_dir / "review-session.json", session_payload)

    if protocol is workbench.GOLD_PROTOCOL:
        monkeypatch.setattr(
            workbench,
            "verify_human_gold_review_manifest",
            lambda path: manifest
            if path == manifest_path
            else pytest.fail(f"unexpected gold manifest: {path}"),
        )
    elif protocol is workbench.GERMAN_PROTOCOL:
        monkeypatch.setattr(
            workbench,
            "verify_translation_source_review_manifest",
            lambda path: manifest
            if path == manifest_path
            else pytest.fail(f"unexpected German manifest: {path}"),
        )
    else:
        monkeypatch.setattr(
            workbench,
            "verify_ocr_candidate_review_manifest",
            lambda path: manifest
            if path == manifest_path
            else pytest.fail(f"unexpected candidate manifest: {path}"),
        )
    return allowed_root, session_dir, manifest


def _autosave_payload(
    view: dict[str, Any],
    *,
    complete: bool,
) -> dict[str, Any]:
    rows = copy.deepcopy(view["state"]["rows"])
    protocol_id = view["protocol"]["protocol_id"]
    for row in rows:
        values = row["values"]
        if complete and protocol_id == workbench.GOLD_PROTOCOL.protocol_id:
            values.update(
                {
                    "page_and_region_resolved": "yes",
                    "source_legibility": "legible",
                    "diplomatic_transcription": "Synthetic diplomatic page.",
                    "layout_and_reading_order": "Single body region.",
                    "decision": "accept",
                }
            )
        elif (
            complete
            and protocol_id
            in {
                workbench.OCR_CANDIDATE_PROTOCOL_V1.protocol_id,
                workbench.OCR_CANDIDATE_PROTOCOL.protocol_id,
            }
        ):
            values.update(
                {
                    "language_review_scope": "full",
                    "page_and_region_resolved": "yes",
                    "source_legibility": "legible",
                    "text_fidelity": "minor-errors",
                    "completeness": "complete",
                    "structure_and_order": "correct",
                    "error_types": ["spacing"],
                    "decision": "accept-with-limits",
                    "notes": "One spacing error.",
                }
            )
        elif complete:
            values.update(
                {
                    "layout_role": "prose",
                    "begins_on_previous_page": "no",
                    "continues_on_next_page": "no",
                    "boundary_start_note": "First visible word.",
                    "boundary_end_note": "Final visible punctuation.",
                    "diplomatic_transcription": "Also sprach Zarathustra.",
                    "decision": "accept",
                }
            )
        row["active_seconds"] = 12.5
    return {
        "revision": view["state"]["revision"],
        "reviewer_ref": "human:synthetic-reviewer",
        "active_unit_index": 1,
        "rows": rows,
    }


@pytest.mark.parametrize(
    ("protocol_name", "expected_protocol_id", "expected_units"),
    [
        ("gold", workbench.GOLD_PROTOCOL.protocol_id, 15),
        ("german", workbench.GERMAN_PROTOCOL.protocol_id, 30),
        ("candidate", workbench.OCR_CANDIDATE_PROTOCOL.protocol_id, 6),
    ],
)
def test_loads_both_supported_review_protocols(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    protocol_name: str,
    expected_protocol_id: str,
    expected_units: int,
) -> None:
    allowed_root, session_dir, manifest = _review_fixture(
        tmp_path, monkeypatch, protocol_name
    )

    context = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    view = context.public_session()

    assert context.protocol.protocol_id == expected_protocol_id
    assert len(context.units) == expected_units
    assert view["packet"] == {
        "packet_id": manifest["packet_id"],
        "unit_count": expected_units,
    }
    assert view["state"]["status"] == "ready"
    assert view["completion"]["completed_units"] == 0
    assert all(unit["title"] != unit["unit_id"] for unit in view["units"])
    if protocol_name == "gold":
        assert view["units"][0]["title"] == (
            "Антоновский, 2007 · PDF-страница 1"
        )
        page_field = next(
            field
            for field in view["protocol"]["fields"]
            if field["name"] == "page_and_region_resolved"
        )
        assert page_field["label"] == "Показана правильная страница целиком?"
        assert "центральная страница" in page_field["help"]
    elif protocol_name == "german":
        assert view["units"][0]["title"] == (
            "Naumann, 1893 · PDF-страница 2"
        )
    else:
        assert view["units"][0]["title"] == (
            "Антоновский, 2007 · PDF-страница 1"
        )
        assert view["protocol"]["review_mode"] == "candidate-review"
        assert view["protocol"]["candidate_visible"] is True
        assert view["protocol"]["protocol_id"].endswith(".v2")
        assert view["units"][0]["candidate_text"].startswith("Synthetic OCR")
        assert view["units"][0]["candidate_label"] == "Кандидат A"
        fields = {
            field["name"]: field for field in view["protocol"]["fields"]
        }
        assert (
            "mixed-omissions-and-additions",
            "Есть и пропуски, и лишний текст",
        ) in fields["completeness"]["options"]
        assert ("typography", "Курсив или другое выделение") in fields[
            "error_types"
        ]["options"]
        assert fields["typography_annotations"]["kind"] == "span-annotations"
    public_bytes = json.dumps(view, ensure_ascii=False).encode("utf-8")
    assert b"immutable-packets" not in public_bytes
    assert b"recognized_comparator" not in public_bytes
    assert b"v1_candidate" not in public_bytes


def test_rejects_page_asset_that_escapes_the_immutable_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root, session_dir, manifest = _review_fixture(
        tmp_path, monkeypatch, "gold"
    )
    packet_root = Path(
        json.loads((session_dir / "review-session.json").read_text())["packet"][
            "root"
        ]
    )
    template_path = packet_root / manifest["review_template"]["ref"]
    rows = [
        json.loads(line)
        for line in template_path.read_text(encoding="utf-8").splitlines()
    ]
    escaped_page = packet_root.parent / "escaped.png"
    escaped_page.write_bytes(b"\x89PNG\r\n\x1a\nescaped")
    rows[0]["source_pages"]["previous"] = "../escaped.png"
    _write_jsonl(template_path, rows)
    manifest["review_template"]["sha256"] = _sha256(template_path)

    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="invalid previous page",
    ):
        workbench.ReviewContext(
            session_dir, allowed_work_root=allowed_root
        )


def test_rejects_mutable_output_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root, session_dir, _manifest = _review_fixture(
        tmp_path, monkeypatch, "gold"
    )
    escaped_feedback = tmp_path / "escaped-feedback.jsonl"
    (session_dir / "human-review-workbench.feedback.jsonl").symlink_to(
        escaped_feedback
    )

    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="mutable review output is a symlink",
    ):
        workbench.ReviewContext(
            session_dir, allowed_work_root=allowed_root
        )


def test_feedback_screenshot_is_content_addressed_and_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root, session_dir, _manifest = _review_fixture(
        tmp_path, monkeypatch, "gold"
    )
    context = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    screenshot = b"\x89PNG\r\n\x1a\n" + b"source-visible-ui-screenshot"

    response = context.record_feedback(
        {
            "category": "interface-friction",
            "note": "",
            "unit_id": context.unit_ids[0],
            "attachments": [
                {
                    "name": "/tmp/workbench-screen.png",
                    "media_type": "image/png",
                    "data_base64": base64.b64encode(screenshot).decode("ascii"),
                }
            ],
        }
    )

    assert response["recorded"] is True
    assert response["attachment_count"] == 1
    records = _load_feedback(context.feedback_path)
    assert records[0]["schema_version"] == (
        "tos_human_review_workbench_feedback_v2"
    )
    assert records[0]["note"] == ""
    attachment = records[0]["attachments"][0]
    assert attachment["original_name"] == "workbench-screen.png"
    assert attachment["sha256"] == hashlib.sha256(screenshot).hexdigest()
    asset_path = session_dir / attachment["ref"]
    assert asset_path.read_bytes() == screenshot
    assert stat.S_IMODE(asset_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(context.feedback_assets_dir.stat().st_mode) == 0o700


def test_feedback_rejects_mismatched_or_escaped_screenshot_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root, session_dir, _manifest = _review_fixture(
        tmp_path, monkeypatch, "gold"
    )
    context = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="does not match its image type",
    ):
        context.record_feedback(
            {
                "category": "technical-problem",
                "note": "Wrong payload.",
                "attachments": [
                    {
                        "name": "fake.png",
                        "media_type": "image/png",
                        "data_base64": base64.b64encode(b"not-an-image").decode(
                            "ascii"
                        ),
                    }
                ],
            }
        )

    escaped = tmp_path / "escaped-feedback-assets"
    escaped.mkdir()
    context.feedback_assets_dir.symlink_to(escaped, target_is_directory=True)
    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="attachment route is a symlink",
    ):
        context.record_feedback(
            {
                "category": "technical-problem",
                "note": "Symlink route.",
                "attachments": [
                    {
                        "name": "screen.png",
                        "media_type": "image/png",
                        "data_base64": base64.b64encode(
                            b"\x89PNG\r\n\x1a\nscreen"
                        ).decode("ascii"),
                    }
                ],
            }
        )


def _json_request(
    url: str,
    token: str,
    *,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = None
    method = "GET"
    headers = {"X-ToS-Review-Token": token}
    if payload is not None:
        method = "POST"
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url, data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _request_status(request: urllib.request.Request) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_api_autosave_rejects_stale_revision_and_resumes_saved_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root, session_dir, _manifest = _review_fixture(
        tmp_path, monkeypatch, "gold"
    )
    static_root = tmp_path / "static"
    static_root.mkdir()
    (static_root / "index.html").write_text(
        "<html>__WORKBENCH_TOKEN__</html>", encoding="utf-8"
    )
    (static_root / "app.css").write_text("", encoding="utf-8")
    (static_root / "app.js").write_text("", encoding="utf-8")
    monkeypatch.setattr(workbench, "STATIC_ROOT", static_root)

    server, launch_url, context = (
        workbench.create_human_review_workbench_server(
            session_dir,
            allowed_work_root=allowed_root,
        )
    )
    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="already open in another workbench",
    ):
        workbench.create_human_review_workbench_server(
            session_dir,
            allowed_work_root=allowed_root,
        )
    parsed = urlparse(launch_url)
    token = parse_qs(parsed.query)["token"][0]
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _body = _request_status(
            urllib.request.Request(f"{base_url}/api/session")
        )
        assert status == 403
        status, _body = _request_status(
            urllib.request.Request(
                f"{base_url}/api/session",
                headers={
                    "Host": "untrusted.example",
                    "X-ToS-Review-Token": token,
                },
            )
        )
        assert status == 400
        status, _body = _request_status(
            urllib.request.Request(f"{base_url}/api/page/0/current?token=wrong")
        )
        assert status == 403
        status, page_bytes = _request_status(
            urllib.request.Request(
                f"{base_url}/api/page/0/current?token={token}"
            )
        )
        assert status == 200
        assert page_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        status, _body = _request_status(
            urllib.request.Request(
                f"{base_url}/api/feedback",
                data=b'{"category":"other","note":"cross-origin"}',
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://untrusted.example",
                    "X-ToS-Review-Token": token,
                },
            )
        )
        assert status == 400

        status, view = _json_request(f"{base_url}/api/session", token)
        assert status == 200
        payload = _autosave_payload(view, complete=False)
        payload["rows"][0]["values"]["decision"] = "uncertain"
        payload["rows"][0]["values"]["notes"] = "Needs another look."

        status, saved = _json_request(
            f"{base_url}/api/autosave", token, payload=payload
        )
        assert status == 200
        assert saved["state"]["revision"] == 1
        assert saved["state"]["status"] == "in-progress"

        status, conflict = _json_request(
            f"{base_url}/api/autosave", token, payload=payload
        )
        assert status == 409
        assert conflict["error"] == "autosave revision conflict"

        status, incomplete = _json_request(
            f"{base_url}/api/submit",
            token,
            payload={
                "revision": saved["state"]["revision"],
                "performed_by_real_human": True,
            },
        )
        assert status == 422
        assert "submission has incomplete units" in incomplete["error"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    resumed = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    assert resumed.state["revision"] == 1
    assert resumed.state["reviewer_ref"] == "human:synthetic-reviewer"
    assert resumed.state["rows"][0]["values"]["decision"] == "uncertain"
    assert resumed.state["rows"][0]["values"]["notes"] == "Needs another look."
    assert context.autosave_path == resumed.autosave_path


def test_autosave_enforces_protocol_identity_and_monotonic_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root, session_dir, _manifest = _review_fixture(
        tmp_path, monkeypatch, "german"
    )
    context = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    invalid = _autosave_payload(context.public_session(), complete=False)
    invalid["rows"][0]["values"]["layout_role"] = "model-decided-prose"
    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="layout_role is not an allowed protocol value",
    ):
        context.autosave(invalid)

    saved = context.autosave(
        _autosave_payload(context.public_session(), complete=False)
    )
    changed_reviewer = _autosave_payload(saved, complete=False)
    changed_reviewer["reviewer_ref"] = "human:different-reviewer"
    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="reviewer_ref cannot change",
    ):
        context.autosave(changed_reviewer)

    backwards = _autosave_payload(saved, complete=False)
    backwards["rows"][0]["active_seconds"] = 1
    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="active_seconds cannot move backwards",
    ):
        context.autosave(backwards)


def test_candidate_review_respects_language_scope_and_validates_quick_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root, session_dir, _manifest = _review_fixture(
        tmp_path, monkeypatch, "candidate"
    )
    context = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    view = context.public_session()
    payload = _autosave_payload(view, complete=False)
    for row in payload["rows"]:
        row["values"].update(
            {
                "language_review_scope": "visual-only",
                "page_and_region_resolved": "yes",
                "source_legibility": "legible",
                "structure_and_order": "not-assessed",
                "decision": "language-not-assessed",
            }
        )
    saved = context.autosave(payload)

    assert saved["completion"]["completed_units"] == len(context.units)
    assert saved["state"]["rows"][0]["values"]["text_fidelity"] is None
    assert saved["state"]["rows"][0]["values"]["completeness"] is None

    invalid = _autosave_payload(saved, complete=False)
    invalid["rows"][0]["values"]["error_types"] = ["invented-tag"]
    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="unknown or duplicate option",
    ):
        context.autosave(invalid)


def test_candidate_correction_is_prefilled_evidence_not_required_retyping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root, session_dir, _manifest = _review_fixture(
        tmp_path, monkeypatch, "candidate"
    )
    context = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    payload = _autosave_payload(context.public_session(), complete=True)
    first_values = payload["rows"][0]["values"]
    corrected_text = "Synthetic OCR candidate 1 for page 1, corrected."
    italic_start = corrected_text.index("candidate")
    italic_end = italic_start + len("candidate")
    first_values.update(
        {
            "decision": "corrected",
            "completeness": "mixed-omissions-and-additions",
            "error_types": ["spacing", "typography"],
            "corrected_text": corrected_text,
            "typography_annotations": [
                {
                    "kind": "italic",
                    "selectors": [
                        {
                            "type": "TextPositionSelector",
                            "start": italic_start,
                            "end": italic_end,
                        },
                        {
                            "type": "TextQuoteSelector",
                            "exact": "candidate",
                        },
                    ],
                }
            ],
            "notes": None,
        }
    )
    saved = context.autosave(payload)
    frozen = context.submit(
        {
            "revision": saved["state"]["revision"],
            "performed_by_real_human": True,
        }
    )

    assert frozen["state"]["status"] == "submitted-and-frozen"
    draft = json.loads(context.draft_path.read_text(encoding="utf-8"))
    first = draft["rows"][0]
    assert first["decision"] == "corrected"
    assert first["corrected_text"].endswith("corrected.")
    assert first["completeness"] == "mixed-omissions-and-additions"
    assert first["typography_annotations"][0]["selectors"][1]["exact"] == (
        "candidate"
    )
    assert first["candidate_sha256"] == context.units[0]["candidate_sha256"]
    assert "run_id" not in json.dumps(draft)


def test_candidate_typography_selector_must_match_corrected_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root, session_dir, _manifest = _review_fixture(
        tmp_path, monkeypatch, "candidate"
    )
    context = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    payload = _autosave_payload(context.public_session(), complete=True)
    values = payload["rows"][0]["values"]
    values.update(
        {
            "decision": "corrected",
            "corrected_text": "alpha beta",
            "typography_annotations": [
                {
                    "kind": "italic",
                    "selectors": [
                        {
                            "type": "TextPositionSelector",
                            "start": 6,
                            "end": 10,
                        },
                        {
                            "type": "TextQuoteSelector",
                            "exact": "wrong",
                        },
                    ],
                }
            ],
        }
    )
    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="no longer matches corrected_text",
    ):
        context.autosave(payload)


def test_frozen_candidate_v1_remains_byte_compatible_after_v2_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root, session_dir, _manifest = _review_fixture(
        tmp_path, monkeypatch, "candidate"
    )
    session_path = session_dir / "review-session.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    session["protocol_id"] = workbench.OCR_CANDIDATE_PROTOCOL_V1.protocol_id
    _write_json(session_path, session)

    context = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    assert context.protocol is workbench.OCR_CANDIDATE_PROTOCOL_V1
    saved = context.autosave(
        _autosave_payload(context.public_session(), complete=True)
    )
    context.submit(
        {
            "revision": saved["state"]["revision"],
            "performed_by_real_human": True,
        }
    )
    draft_bytes = context.draft_path.read_bytes()
    draft = json.loads(draft_bytes)
    assert draft["schema_version"] == (
        "tos_ocr_candidate_human_review_draft_v1"
    )
    assert "typography_annotations" not in draft["rows"][0]

    stale_control = json.loads(session_path.read_text(encoding="utf-8"))
    stale_control.pop("protocol_id")
    stale_control.pop("review_result")
    stale_control["status"] = "awaiting-real-human-candidate-review"
    stale_control["progress"] = {
        "total_units": len(context.units),
        "completed_units": 0,
    }
    _write_json(session_path, stale_control)
    repaired = workbench.synchronize_human_review_session_control(
        session_dir, allowed_work_root=allowed_root
    )
    assert repaired == {
        "session_id": "synthetic-candidate-session",
        "protocol_id": workbench.OCR_CANDIDATE_PROTOCOL_V1.protocol_id,
        "status": "pass-1-draft-frozen",
        "progress": {
            "total_units": len(context.units),
            "completed_units": len(context.units),
        },
        "changed": True,
        "authority_boundary": (
            "mutable session-control projection synchronized from validated "
            "autosave/draft/receipt; frozen human evidence was not changed"
        ),
    }
    assert context.draft_path.read_bytes() == draft_bytes
    assert (
        workbench.synchronize_human_review_session_control(
            session_dir, allowed_work_root=allowed_root
        )["changed"]
        is False
    )

    resumed = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    assert resumed.protocol is workbench.OCR_CANDIDATE_PROTOCOL_V1
    assert resumed.draft_path.read_bytes() == draft_bytes


def test_resume_rejects_partial_freeze(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root, session_dir, _manifest = _review_fixture(
        tmp_path, monkeypatch, "gold"
    )
    context = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    context.autosave(
        _autosave_payload(context.public_session(), complete=False)
    )
    _write_json(context.receipt_path, {"status": "orphaned-receipt"})

    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="review freeze is partial",
    ):
        workbench.ReviewContext(
            session_dir, allowed_work_root=allowed_root
        )


@pytest.mark.parametrize("protocol_name", ["gold", "german", "candidate"])
def test_complete_submission_freezes_draft_and_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    protocol_name: str,
) -> None:
    allowed_root, session_dir, manifest = _review_fixture(
        tmp_path, monkeypatch, protocol_name
    )
    context = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    saved = context.autosave(
        _autosave_payload(context.public_session(), complete=True)
    )

    frozen = context.submit(
        {
            "revision": saved["state"]["revision"],
            "performed_by_real_human": True,
        }
    )

    assert frozen["state"]["status"] == "submitted-and-frozen"
    assert context.draft_path.is_file()
    assert context.receipt_path.is_file()
    assert stat.S_IMODE(context.draft_path.stat().st_mode) == 0o400
    receipt = json.loads(context.receipt_path.read_text(encoding="utf-8"))
    draft = json.loads(context.draft_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "pass-1-draft-frozen"
    assert receipt["packet_id"] == manifest["packet_id"]
    assert receipt["draft_sha256"] == _sha256(context.draft_path)
    assert receipt["unit_count"] == len(context.units)
    assert draft["performed_by_real_human"] is True
    assert draft["reviewer_ref"] == "human:synthetic-reviewer"
    assert len(draft["rows"]) == len(context.units)
    control = json.loads(
        (session_dir / "review-session.json").read_text(encoding="utf-8")
    )
    assert control["protocol_id"] == context.protocol.protocol_id
    assert control["status"] == "pass-1-draft-frozen"
    assert control["progress"] == {
        "total_units": len(context.units),
        "completed_units": len(context.units),
    }
    assert control["review_result"]["draft_sha256"] == receipt["draft_sha256"]
    assert context.synchronize_session_control() is False

    resumed = workbench.ReviewContext(
        session_dir, allowed_work_root=allowed_root
    )
    assert resumed.state["status"] == "submitted-and-frozen"
    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="submitted review is frozen",
    ):
        resumed.autosave(
            _autosave_payload(resumed.public_session(), complete=True)
        )

    os.chmod(context.draft_path, 0o600)
    context.draft_path.write_text(
        context.draft_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(
        workbench.HumanReviewWorkbenchError,
        match="frozen review draft digest drifted",
    ):
        workbench.ReviewContext(
            session_dir, allowed_work_root=allowed_root
        )
