from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator, FormatChecker


PART_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PART_ROOT / "external_codex_continuity_capsule.py"
SCHEMA_PATH = (
    PART_ROOT / "schemas/external-codex-continuity-capsule-reinjection.schema.json"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "external_codex_continuity_capsule_under_test",
        MODULE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CAPSULE = _load_module()


def _digest(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _envelope() -> dict[str, object]:
    tail = "protected tail: exact decision and unresolved obligation"
    tail_digest = "sha256:" + hashlib.sha256(tail.encode("utf-8")).hexdigest()
    posture = {
        "mode": "verbatim_private_tail",
        "portable_tail_policy": "omitted",
        "private_tail_digest": tail_digest,
        "private_tail_bytes": len(tail.encode("utf-8")),
    }
    content = {
        "capsule_id": "case-001",
        "goal": {
            "goal_id": "goal-001",
            "title": "bounded continuity",
            "source_ref": "goal://goal-001",
            "digest": "sha256:" + "2" * 64,
            "content": "preserve exact state",
        },
        "constraints": ["default off"],
        "completed": ["contract shape"],
        "current_work": ["paired validation"],
        "blockers": [],
        "exact_decisions": ["keep protected tail private"],
        "open_obligations": ["run baseline"],
        "evidence_refs": [{"ref": "evidence:001"}],
        "omissions_uncertainty": {"omitted": []},
    }
    source_watermark = {
        "source_ref": "session:001",
        "source_digest": "sha256:" + "1" * 64,
        "generation": 3,
        "observed_at": "2026-08-26T18:30:48Z",
    }
    compaction_event = {
        "event_ref": "event:compaction:001",
        "session_id": "session-001",
        "sequence": 7,
        "occurred_at": "2026-08-26T18:30:48Z",
        "kind": "compaction",
    }
    capsule_digest = _digest(
        {
            "schema_version": "continuity_capsule_v1",
            **content,
            "source_watermark": source_watermark,
            "compaction_event": compaction_event,
            "protected_tail_posture": posture,
        }
    )
    capsule_ref = {
        "object_id": "continuity-capsule:case-001",
        "owner_repo": "aoa-session-memory",
        "schema_version": "continuity_capsule_v1",
        "digest": capsule_digest,
    }

    def materialization(view: str) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": "continuity_capsule_materialization_v1",
            "view": view,
            "capsule_ref": capsule_ref,
            "capsule_digest": capsule_digest,
            "content": content,
            "source_watermark": source_watermark,
            "compaction_event": compaction_event,
            "protected_tail_posture": posture,
        }
        if view == "private":
            payload["protected_tail"] = tail
        payload["view_digest"] = _digest(payload)
        return payload

    return {
        "schema_version": "continuity_capsule_reinjection_v1",
        "capsule_ref": capsule_ref,
        "capsule_digest": capsule_digest,
        "portable_view": materialization("portable"),
        "private_view": materialization("private"),
    }


def test_exact_pair_validates_and_receipt_excludes_private_tail() -> None:
    envelope = _envelope()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
            envelope
        )
    )
    assert errors == []

    validated = CAPSULE.validate_continuity_capsule_reinjection(envelope)
    receipt = CAPSULE.reinjection_event_payload(validated)

    assert receipt["capsule_ref"] == envelope["capsule_ref"]
    assert receipt["portable_view_digest"] == envelope["portable_view"]["view_digest"]
    assert receipt["private_view_digest"] == envelope["private_view"]["view_digest"]
    assert "protected_tail" not in receipt
    assert "protected tail: exact decision" not in json.dumps(receipt)

    model_payload = CAPSULE.model_reinjection_payload(validated)
    assert model_payload["protected_tail"] == (
        "protected tail: exact decision and unresolved obligation"
    )
    assert model_payload["content"] == envelope["private_view"]["content"]
    assert "portable_view" not in model_payload
    assert "private_view" not in model_payload


def test_capsule_content_drift_is_rejected() -> None:
    envelope = _envelope()
    private = envelope["private_view"]
    assert isinstance(private, dict)
    content = private["content"]
    assert isinstance(content, dict)
    content["open_obligations"] = ["changed after materialization"]

    with pytest.raises(CAPSULE.ContinuityCapsuleReinjectionError, match="view digest"):
        CAPSULE.validate_continuity_capsule_reinjection(envelope)


def test_portable_view_cannot_carry_protected_tail() -> None:
    envelope = _envelope()
    portable = envelope["portable_view"]
    assert isinstance(portable, dict)
    portable["protected_tail"] = "must remain private"

    with pytest.raises(
        CAPSULE.ContinuityCapsuleReinjectionError, match="portable_view"
    ):
        CAPSULE.validate_continuity_capsule_reinjection(envelope)


def test_owner_byte_and_list_ceilings_are_enforced() -> None:
    envelope = _envelope()
    portable = envelope["portable_view"]
    private = envelope["private_view"]
    assert isinstance(portable, dict) and isinstance(private, dict)
    for view in (portable, private):
        content = view["content"]
        assert isinstance(content, dict)
        content["constraints"] = ["bounded"] * 257
        unsigned = {key: value for key, value in view.items() if key != "view_digest"}
        view["view_digest"] = _digest(unsigned)

    with pytest.raises(
        CAPSULE.ContinuityCapsuleReinjectionError,
        match="bounded list of strings",
    ):
        CAPSULE.validate_continuity_capsule_reinjection(envelope)


def test_oversized_envelope_is_rejected_before_canonical_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = _envelope()
    private = envelope["private_view"]
    assert isinstance(private, dict)
    private["protected_tail"] = "x" * (CAPSULE.MAX_REINJECTION_BYTES + 1)

    def fail_if_serialized(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("oversized input reached json.dumps")

    monkeypatch.setattr(CAPSULE.json, "dumps", fail_if_serialized)
    with pytest.raises(
        CAPSULE.ContinuityCapsuleReinjectionError,
        match="byte ceiling",
    ):
        CAPSULE.validate_continuity_capsule_reinjection(envelope)


def test_cyclic_envelope_is_rejected_before_copy_or_digest() -> None:
    envelope = _envelope()
    envelope["cycle"] = envelope

    with pytest.raises(
        CAPSULE.ContinuityCapsuleReinjectionError,
        match="cycle",
    ):
        CAPSULE.validate_continuity_capsule_reinjection(envelope)


def test_reinjection_requires_the_exact_sdk_bound_capsule_ref() -> None:
    envelope = _envelope()
    expected_ref = envelope["capsule_ref"]
    assert isinstance(expected_ref, dict)

    validated = CAPSULE.validate_continuity_capsule_binding(
        envelope,
        expected_ref=expected_ref,
    )
    assert validated is not None
    assert validated["capsule_ref"] == expected_ref

    with pytest.raises(
        CAPSULE.ContinuityCapsuleReinjectionError,
        match="omitted",
    ):
        CAPSULE.validate_continuity_capsule_binding(None, expected_ref=expected_ref)
    with pytest.raises(
        CAPSULE.ContinuityCapsuleReinjectionError,
        match="absent from the incarnation binding",
    ):
        CAPSULE.validate_continuity_capsule_binding(envelope, expected_ref=None)

    wrong_ref = dict(expected_ref)
    wrong_ref["object_id"] = "continuity-capsule:different"
    with pytest.raises(
        CAPSULE.ContinuityCapsuleReinjectionError,
        match="differs from the SDK-bound reference",
    ):
        CAPSULE.validate_continuity_capsule_binding(
            envelope,
            expected_ref=wrong_ref,
        )
