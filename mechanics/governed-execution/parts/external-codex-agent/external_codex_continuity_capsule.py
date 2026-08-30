"""Provider-neutral validation for one opt-in continuity-capsule reinjection.

The session-memory owner creates the canonical capsule and its views.  The
runtime owner only admits an exact, already-materialized pair and records a
non-sensitive receipt.  This module intentionally has no provider or model
dependency and never treats the envelope as owner truth.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any


CONTINUITY_CAPSULE_REINJECTION_SCHEMA_VERSION = "continuity_capsule_reinjection_v1"
CAPSULE_SCHEMA_VERSION = "continuity_capsule_v1"
MATERIALIZATION_SCHEMA_VERSION = "continuity_capsule_materialization_v1"
CAPSULE_OWNER_REPO = "aoa-session-memory"
CAPSULE_REF_PREFIX = "continuity-capsule:"
MAX_STRING_LENGTH = 65_536
MAX_LIST_ITEMS = 256
MAX_EVIDENCE_REFS = 512
MAX_PROTECTED_TAIL_BYTES = 512 * 1024
MAX_CAPSULE_BYTES = 1024 * 1024
MAX_MATERIALIZATION_BYTES = MAX_CAPSULE_BYTES + MAX_PROTECTED_TAIL_BYTES + 64 * 1024
MAX_REINJECTION_BYTES = 2 * MAX_MATERIALIZATION_BYTES + 64 * 1024
MAX_JSON_ITEMS = 4096
MAX_JSON_DEPTH = 32
CAPSULE_CONTENT_FIELDS = (
    "capsule_id",
    "goal",
    "constraints",
    "completed",
    "current_work",
    "blockers",
    "exact_decisions",
    "open_obligations",
    "evidence_refs",
    "omissions_uncertainty",
)


class ContinuityCapsuleReinjectionError(ValueError):
    """Raised when the runtime envelope is not an exact capsule pair."""


def _bounded_json_preflight(value: Any) -> None:
    """Bound the full JSON graph before canonical serialization or copying."""

    estimated_bytes = 0
    observed_items = 0
    active_containers: set[int] = set()

    def add_bytes(amount: int) -> None:
        nonlocal estimated_bytes
        estimated_bytes += amount
        if estimated_bytes > MAX_REINJECTION_BYTES:
            raise ContinuityCapsuleReinjectionError(
                "continuity reinjection envelope exceeds its byte ceiling"
            )

    def add_items(amount: int) -> None:
        nonlocal observed_items
        observed_items += amount
        if observed_items > MAX_JSON_ITEMS:
            raise ContinuityCapsuleReinjectionError(
                "continuity reinjection envelope exceeds its item ceiling"
            )

    def visit(item: Any, depth: int) -> None:
        if depth > MAX_JSON_DEPTH:
            raise ContinuityCapsuleReinjectionError(
                "continuity reinjection envelope exceeds its depth ceiling"
            )
        if item is None:
            add_bytes(4)
        elif isinstance(item, bool):
            add_bytes(4 if item else 5)
        elif isinstance(item, int):
            bit_length = abs(item).bit_length()
            decimal_digits_upper_bound = (bit_length * 30103) // 100000 + 2
            add_bytes(decimal_digits_upper_bound + (1 if item < 0 else 0))
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ContinuityCapsuleReinjectionError(
                    "continuity payload must contain finite JSON numbers"
                )
            add_bytes(32)
        elif isinstance(item, str):
            add_bytes(2)
            for character in item:
                codepoint = ord(character)
                if character in {'"', "\\", "\b", "\f", "\n", "\r", "\t"}:
                    add_bytes(2)
                elif codepoint < 0x20 or codepoint > 0x7F:
                    if 0xD800 <= codepoint <= 0xDFFF:
                        raise ContinuityCapsuleReinjectionError(
                            "continuity payload contains an invalid surrogate"
                        )
                    add_bytes(6 if codepoint <= 0xFFFF else 12)
                else:
                    add_bytes(1)
        elif isinstance(item, Mapping):
            identity = id(item)
            if identity in active_containers:
                raise ContinuityCapsuleReinjectionError(
                    "continuity payload contains a cycle"
                )
            add_items(len(item))
            active_containers.add(identity)
            add_bytes(2 + max(0, len(item) - 1))
            try:
                for key, nested in item.items():
                    if not isinstance(key, str):
                        raise ContinuityCapsuleReinjectionError(
                            "continuity payload keys must be strings"
                        )
                    visit(key, depth + 1)
                    add_bytes(1)
                    visit(nested, depth + 1)
            finally:
                active_containers.remove(identity)
        elif isinstance(item, (list, tuple)):
            identity = id(item)
            if identity in active_containers:
                raise ContinuityCapsuleReinjectionError(
                    "continuity payload contains a cycle"
                )
            add_items(len(item))
            active_containers.add(identity)
            add_bytes(2 + max(0, len(item) - 1))
            try:
                for nested in item:
                    visit(nested, depth + 1)
            finally:
                active_containers.remove(identity)
        else:
            raise ContinuityCapsuleReinjectionError(
                "continuity payload must be canonical JSON"
            )

    visit(value, 0)


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        rendered = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ContinuityCapsuleReinjectionError(
            "continuity payload must be canonical JSON"
        ) from exc
    return rendered.encode("utf-8")


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = _canonical_bytes(payload)
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContinuityCapsuleReinjectionError(f"{label} must be an object")
    return value


def _require_non_empty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContinuityCapsuleReinjectionError(f"{label} must be a non-empty string")
    if len(value) > MAX_STRING_LENGTH:
        raise ContinuityCapsuleReinjectionError(
            f"{label} exceeds the supported string length"
        )
    return value


def _require_string_list(value: Any, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
        raise ContinuityCapsuleReinjectionError(
            f"{label} must be a bounded list of strings"
        )
    for index, item in enumerate(value):
        _require_non_empty_string(item, label=f"{label}[{index}]")
    return tuple(value)


def _require_timestamp(value: Any, *, label: str) -> str:
    text = _require_non_empty_string(value, label=label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContinuityCapsuleReinjectionError(
            f"{label} must be an RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContinuityCapsuleReinjectionError(f"{label} must include a timezone")
    return text


def _require_digest(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ContinuityCapsuleReinjectionError(
            f"{label} must be a lowercase sha256 digest"
        )
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    *,
    label: str,
) -> None:
    if set(value) != expected:
        raise ContinuityCapsuleReinjectionError(
            f"{label} has an unexpected or missing field"
        )


def _validate_ref(value: Any, *, digest: str, label: str) -> dict[str, Any]:
    ref = dict(_require_mapping(value, label=label))
    _require_exact_keys(
        ref,
        {"object_id", "owner_repo", "schema_version", "digest"},
        label=label,
    )
    object_id = _require_non_empty_string(ref["object_id"], label=f"{label}.object_id")
    if not object_id.startswith(CAPSULE_REF_PREFIX):
        raise ContinuityCapsuleReinjectionError(
            f"{label}.object_id has the wrong prefix"
        )
    if ref["owner_repo"] != CAPSULE_OWNER_REPO:
        raise ContinuityCapsuleReinjectionError(
            f"{label}.owner_repo is not the session-memory owner"
        )
    if ref["schema_version"] != CAPSULE_SCHEMA_VERSION:
        raise ContinuityCapsuleReinjectionError(
            f"{label}.schema_version is not the capsule schema"
        )
    if _require_digest(ref["digest"], label=f"{label}.digest") != digest:
        raise ContinuityCapsuleReinjectionError(
            f"{label} is not bound to the envelope capsule digest"
        )
    return ref


def _validate_posture(value: Any, *, label: str) -> dict[str, Any]:
    posture = dict(_require_mapping(value, label=label))
    _require_exact_keys(
        posture,
        {
            "mode",
            "portable_tail_policy",
            "private_tail_digest",
            "private_tail_bytes",
        },
        label=label,
    )
    if posture["mode"] != "verbatim_private_tail":
        raise ContinuityCapsuleReinjectionError(
            f"{label}.mode must preserve the verbatim private tail"
        )
    if posture["portable_tail_policy"] != "omitted":
        raise ContinuityCapsuleReinjectionError(
            f"{label}.portable_tail_policy must omit the tail"
        )
    _require_digest(
        posture["private_tail_digest"], label=f"{label}.private_tail_digest"
    )
    if (
        not isinstance(posture["private_tail_bytes"], int)
        or posture["private_tail_bytes"] < 0
        or isinstance(posture["private_tail_bytes"], bool)
        or posture["private_tail_bytes"] > MAX_PROTECTED_TAIL_BYTES
    ):
        raise ContinuityCapsuleReinjectionError(
            f"{label}.private_tail_bytes must be non-negative"
        )
    return posture


def _validate_view(
    value: Any,
    *,
    expected_view: str,
    capsule_ref: Mapping[str, Any],
    capsule_digest: str,
) -> dict[str, Any]:
    view = dict(_require_mapping(value, label=f"{expected_view}_view"))
    required = {
        "schema_version",
        "view",
        "capsule_ref",
        "capsule_digest",
        "content",
        "source_watermark",
        "compaction_event",
        "protected_tail_posture",
        "view_digest",
    }
    if expected_view == "private":
        required.add("protected_tail")
    _require_exact_keys(view, required, label=f"{expected_view}_view")
    if view["schema_version"] != MATERIALIZATION_SCHEMA_VERSION:
        raise ContinuityCapsuleReinjectionError(
            f"{expected_view}_view has the wrong materialization schema"
        )
    if view["view"] != expected_view:
        raise ContinuityCapsuleReinjectionError(
            f"{expected_view}_view has the wrong view marker"
        )
    view_ref = _validate_ref(
        view["capsule_ref"],
        digest=capsule_digest,
        label=f"{expected_view}_view.capsule_ref",
    )
    if view_ref != dict(capsule_ref):
        raise ContinuityCapsuleReinjectionError(
            f"{expected_view}_view changes the exact capsule reference"
        )
    if view["capsule_digest"] != capsule_digest:
        raise ContinuityCapsuleReinjectionError(
            f"{expected_view}_view changes the exact capsule digest"
        )
    content = dict(
        _require_mapping(view["content"], label=f"{expected_view}_view.content")
    )
    if set(content) != set(CAPSULE_CONTENT_FIELDS):
        raise ContinuityCapsuleReinjectionError(
            f"{expected_view}_view.content does not preserve capsule fields"
        )
    _require_non_empty_string(content["capsule_id"], label="content.capsule_id")
    goal = _require_mapping(content["goal"], label="content.goal")
    for field in ("goal_id", "title", "source_ref", "content"):
        _require_non_empty_string(goal.get(field), label=f"content.goal.{field}")
    _require_digest(goal.get("digest"), label="content.goal.digest")
    for field in (
        "constraints",
        "completed",
        "current_work",
        "blockers",
        "exact_decisions",
        "open_obligations",
    ):
        _require_string_list(content[field], label=f"content.{field}")
    evidence_refs = content["evidence_refs"]
    if not isinstance(evidence_refs, list) or len(evidence_refs) > MAX_EVIDENCE_REFS:
        raise ContinuityCapsuleReinjectionError(
            "content.evidence_refs must be a bounded list"
        )
    for index, item in enumerate(evidence_refs):
        if not isinstance(item, Mapping) or not item:
            raise ContinuityCapsuleReinjectionError(
                f"content.evidence_refs[{index}] must be a non-empty object"
            )
    _require_mapping(
        content["omissions_uncertainty"], label="content.omissions_uncertainty"
    )
    source_watermark = _require_mapping(
        view["source_watermark"], label=f"{expected_view}_view.source_watermark"
    )
    _require_non_empty_string(
        source_watermark.get("source_ref"), label="source_watermark.source_ref"
    )
    _require_digest(
        source_watermark.get("source_digest"), label="source_watermark.source_digest"
    )
    generation = source_watermark.get("generation")
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 0
    ):
        raise ContinuityCapsuleReinjectionError(
            "source_watermark.generation must be a non-negative integer"
        )
    _require_timestamp(
        source_watermark.get("observed_at"), label="source_watermark.observed_at"
    )
    compaction_event = _require_mapping(
        view["compaction_event"], label=f"{expected_view}_view.compaction_event"
    )
    for field in ("event_ref", "session_id"):
        _require_non_empty_string(
            compaction_event.get(field), label=f"compaction_event.{field}"
        )
    sequence = compaction_event.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ContinuityCapsuleReinjectionError(
            "compaction_event.sequence must be a non-negative integer"
        )
    _require_timestamp(
        compaction_event.get("occurred_at"), label="compaction_event.occurred_at"
    )
    if compaction_event.get("kind") != "compaction":
        raise ContinuityCapsuleReinjectionError(
            "compaction_event.kind must be compaction"
        )
    posture = _validate_posture(
        view["protected_tail_posture"],
        label=f"{expected_view}_view.protected_tail_posture",
    )
    if expected_view == "portable":
        if "protected_tail" in view:
            raise ContinuityCapsuleReinjectionError(
                "portable_view must not contain protected_tail"
            )
    else:
        tail = view["protected_tail"]
        if not isinstance(tail, str):
            raise ContinuityCapsuleReinjectionError(
                "private_view.protected_tail must be a UTF-8 string"
            )
        try:
            tail_raw = tail.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ContinuityCapsuleReinjectionError(
                "private_view.protected_tail must be valid UTF-8"
            ) from exc
        if len(tail_raw) > MAX_PROTECTED_TAIL_BYTES:
            raise ContinuityCapsuleReinjectionError(
                "private_view.protected_tail exceeds its byte ceiling"
            )
        tail_digest = "sha256:" + hashlib.sha256(tail_raw).hexdigest()
        if tail_digest != posture["private_tail_digest"]:
            raise ContinuityCapsuleReinjectionError(
                "private_view.protected_tail does not match its protected-tail digest"
            )
        if len(tail_raw) != posture["private_tail_bytes"]:
            raise ContinuityCapsuleReinjectionError(
                "private_view.protected_tail does not match its byte count"
            )
    view_digest = _require_digest(
        view["view_digest"], label=f"{expected_view}_view.view_digest"
    )
    if (
        _canonical_digest({key: view[key] for key in view if key != "view_digest"})
        != view_digest
    ):
        raise ContinuityCapsuleReinjectionError(
            f"{expected_view}_view digest does not match its content"
        )
    if len(_canonical_bytes(view)) > MAX_MATERIALIZATION_BYTES:
        raise ContinuityCapsuleReinjectionError(
            f"{expected_view}_view exceeds its byte ceiling"
        )
    return view


def validate_continuity_capsule_reinjection(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and return a copy of one exact portable/private pair."""

    _bounded_json_preflight(value)
    envelope = dict(_require_mapping(value, label="continuity_capsule"))
    _require_exact_keys(
        envelope,
        {
            "schema_version",
            "capsule_ref",
            "capsule_digest",
            "portable_view",
            "private_view",
        },
        label="continuity_capsule",
    )
    if envelope["schema_version"] != CONTINUITY_CAPSULE_REINJECTION_SCHEMA_VERSION:
        raise ContinuityCapsuleReinjectionError(
            "unsupported continuity-capsule reinjection schema"
        )
    capsule_digest = _require_digest(
        envelope["capsule_digest"],
        label="continuity_capsule.capsule_digest",
    )
    capsule_ref = _validate_ref(
        envelope["capsule_ref"],
        digest=capsule_digest,
        label="continuity_capsule.capsule_ref",
    )
    portable = _validate_view(
        envelope["portable_view"],
        expected_view="portable",
        capsule_ref=capsule_ref,
        capsule_digest=capsule_digest,
    )
    private = _validate_view(
        envelope["private_view"],
        expected_view="private",
        capsule_ref=capsule_ref,
        capsule_digest=capsule_digest,
    )
    canonical_payload = {
        "schema_version": CAPSULE_SCHEMA_VERSION,
        **portable["content"],
        "source_watermark": portable["source_watermark"],
        "compaction_event": portable["compaction_event"],
        "protected_tail_posture": portable["protected_tail_posture"],
    }
    if _canonical_digest(canonical_payload) != capsule_digest:
        raise ContinuityCapsuleReinjectionError(
            "continuity capsule digest does not match its materialized content"
        )
    for field in (
        "content",
        "source_watermark",
        "compaction_event",
        "protected_tail_posture",
    ):
        if portable[field] != private[field]:
            raise ContinuityCapsuleReinjectionError(
                f"portable_view and private_view disagree on {field}"
            )
    capsule_id = str(portable["content"]["capsule_id"])
    if capsule_ref["object_id"] != f"{CAPSULE_REF_PREFIX}{capsule_id}":
        raise ContinuityCapsuleReinjectionError(
            "capsule reference object id does not match capsule_id"
        )
    if len(_canonical_bytes(canonical_payload)) > MAX_CAPSULE_BYTES:
        raise ContinuityCapsuleReinjectionError(
            "continuity capsule exceeds its byte ceiling"
        )
    if len(_canonical_bytes(envelope)) > MAX_REINJECTION_BYTES:
        raise ContinuityCapsuleReinjectionError(
            "continuity reinjection envelope exceeds its byte ceiling"
        )
    return copy.deepcopy(envelope)


def model_reinjection_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project one exact private view without duplicating portable content."""

    envelope = validate_continuity_capsule_reinjection(value)
    private = envelope["private_view"]
    return {
        "schema_version": CONTINUITY_CAPSULE_REINJECTION_SCHEMA_VERSION,
        "capsule_ref": copy.deepcopy(envelope["capsule_ref"]),
        "capsule_digest": envelope["capsule_digest"],
        "portable_view_digest": envelope["portable_view"]["view_digest"],
        "private_view_digest": private["view_digest"],
        "content": copy.deepcopy(private["content"]),
        "source_watermark": copy.deepcopy(private["source_watermark"]),
        "compaction_event": copy.deepcopy(private["compaction_event"]),
        "protected_tail_posture": copy.deepcopy(private["protected_tail_posture"]),
        "protected_tail": private["protected_tail"],
    }


def reinjection_event_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a receipt payload that proves admission without exposing tail bytes."""

    envelope = validate_continuity_capsule_reinjection(value)
    private = envelope["private_view"]
    posture = private["protected_tail_posture"]
    return {
        "capsule_ref": copy.deepcopy(envelope["capsule_ref"]),
        "capsule_digest": envelope["capsule_digest"],
        "portable_view_digest": envelope["portable_view"]["view_digest"],
        "private_view_digest": private["view_digest"],
        "source_watermark": copy.deepcopy(private["source_watermark"]),
        "compaction_event": copy.deepcopy(private["compaction_event"]),
        "protected_tail_posture": {
            "mode": posture["mode"],
            "portable_tail_policy": posture["portable_tail_policy"],
            "private_tail_digest": posture["private_tail_digest"],
            "private_tail_bytes": posture["private_tail_bytes"],
        },
    }


__all__ = [
    "CONTINUITY_CAPSULE_REINJECTION_SCHEMA_VERSION",
    "ContinuityCapsuleReinjectionError",
    "model_reinjection_payload",
    "reinjection_event_payload",
    "validate_continuity_capsule_reinjection",
]
