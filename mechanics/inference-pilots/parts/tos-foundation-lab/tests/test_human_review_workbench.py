from __future__ import annotations

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
    if plan_path is not None:
        manifest["review_plan_ref"] = plan_path.as_posix()

    manifest_path = packet_root / protocol.manifest_filename
    _write_json(manifest_path, manifest)
    _write_json(
        session_dir / "review-session.json",
        {
            "schema_version": f"synthetic_{protocol_name}_session_v1",
            "session_id": f"synthetic-{protocol_name}-session",
            "private_local_only": True,
            "packet": {
                "packet_id": manifest["packet_id"],
                "root": packet_root.as_posix(),
                "manifest_sha256": _sha256(manifest_path),
            },
        },
    )

    if protocol is workbench.GOLD_PROTOCOL:
        monkeypatch.setattr(
            workbench,
            "verify_human_gold_review_manifest",
            lambda path: manifest
            if path == manifest_path
            else pytest.fail(f"unexpected gold manifest: {path}"),
        )
    else:
        monkeypatch.setattr(
            workbench,
            "verify_translation_source_review_manifest",
            lambda path: manifest
            if path == manifest_path
            else pytest.fail(f"unexpected German manifest: {path}"),
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


@pytest.mark.parametrize("protocol_name", ["gold", "german"])
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
    assert receipt["unit_count"] == context.protocol.expected_unit_count
    assert draft["performed_by_real_human"] is True
    assert draft["reviewer_ref"] == "human:synthetic-reviewer"
    assert len(draft["rows"]) == context.protocol.expected_unit_count

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
