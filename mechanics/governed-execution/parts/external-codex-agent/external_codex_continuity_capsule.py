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
from collections.abc import Mapping
from typing import Any


CONTINUITY_CAPSULE_REINJECTION_SCHEMA_VERSION = (
    "continuity_capsule_reinjection_v1"
)
CAPSULE_SCHEMA_VERSION = "continuity_capsule_v1"
MATERIALIZATION_SCHEMA_VERSION = "continuity_capsule_materialization_v1"
CAPSULE_OWNER_REPO = "aoa-session-memory"
CAPSULE_REF_PREFIX = "continuity-capsule:"
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


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContinuityCapsuleReinjectionError(f"{label} must be an object")
    return value


def _require_non_empty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContinuityCapsuleReinjectionError(
            f"{label} must be a non-empty string"
        )
    return value


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
    _require_digest(posture["private_tail_digest"], label=f"{label}.private_tail_digest")
    if not isinstance(posture["private_tail_bytes"], int) or posture[
        "private_tail_bytes"
    ] < 0:
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
    content = dict(_require_mapping(view["content"], label=f"{expected_view}_view.content"))
    if set(content) != set(CAPSULE_CONTENT_FIELDS):
        raise ContinuityCapsuleReinjectionError(
            f"{expected_view}_view.content does not preserve capsule fields"
        )
    _require_mapping(
        view["source_watermark"],
        label=f"{expected_view}_view.source_watermark",
    )
    _require_mapping(
        view["compaction_event"],
        label=f"{expected_view}_view.compaction_event",
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
        tail_digest = "sha256:" + hashlib.sha256(tail.encode("utf-8")).hexdigest()
        if tail_digest != posture["private_tail_digest"]:
            raise ContinuityCapsuleReinjectionError(
                "private_view.protected_tail does not match its protected-tail digest"
            )
        if len(tail.encode("utf-8")) != posture["private_tail_bytes"]:
            raise ContinuityCapsuleReinjectionError(
                "private_view.protected_tail does not match its byte count"
            )
    view_digest = _require_digest(view["view_digest"], label=f"{expected_view}_view.view_digest")
    if _canonical_digest(
        {key: view[key] for key in view if key != "view_digest"}
    ) != view_digest:
        raise ContinuityCapsuleReinjectionError(
            f"{expected_view}_view digest does not match its content"
        )
    return view


def validate_continuity_capsule_reinjection(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and return a copy of one exact portable/private pair."""

    envelope = dict(_require_mapping(value, label="continuity_capsule"))
    _require_exact_keys(
        envelope,
        {"schema_version", "capsule_ref", "capsule_digest", "portable_view", "private_view"},
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
    for field in ("content", "source_watermark", "compaction_event", "protected_tail_posture"):
        if portable[field] != private[field]:
            raise ContinuityCapsuleReinjectionError(
                f"portable_view and private_view disagree on {field}"
            )
    return copy.deepcopy(envelope)


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
    "reinjection_event_payload",
    "validate_continuity_capsule_reinjection",
]
