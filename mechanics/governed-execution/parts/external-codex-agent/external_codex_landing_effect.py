#!/usr/bin/env python3
"""Default-deny admission for provider-neutral governed landing effects.

This module is deliberately narrower than the external Codex command
observer.  A grant proves that one owner-authorized effect scope may be
considered by a future effect executor; it does not make model-issued shell,
Git, provider, or network commands safe.  The current runtime profile keeps
all external effects disabled, so ordinary command observation remains the
runtime-wide ten-effect forbidden closure.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker


PART_ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = (
    PART_ROOT
    / "schemas/external-codex-governed-landing-effect-grant.schema.json"
)
SCHEMA_VERSION = "abyss_stack_external_codex_governed_landing_effect_grant_v1"
CAPABILITY_ID = "governed_git_landing_v1"
ZERO_DIGEST = "sha256:" + "0" * 64
MAX_GRANT_BYTES = 256 * 1024
GIT_EXECUTABLE = "/usr/bin/git"
GIT_REF_VALIDATION_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
}
LANDING_EFFECTS = frozenset({"commit", "push", "pull_request", "merge"})
RUNTIME_WIDE_FORBIDDEN_EFFECTS = frozenset(
    {
        *LANDING_EFFECTS,
        "tag",
        "release",
        "publication",
        "service_mutation",
        "secret_access",
        "global_config_mutation",
    }
)


class LandingEffectGrantError(ValueError):
    """A landing grant failed a typed admission boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (
        MemoryError,
        RecursionError,
        TypeError,
        UnicodeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise LandingEffectGrantError(
            "landing_effect_grant_not_json", "grant is not canonical JSON data"
        ) from exc


def _bounded_canonical_bytes(value: object, *, limit: int) -> bytes:
    """Canonicalize JSON data without materializing more than the bound."""

    encoder = json.JSONEncoder(
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in encoder.iterencode(value):
            remaining = limit - total
            if len(chunk) > remaining:
                raise LandingEffectGrantError(
                    "landing_effect_grant_too_large",
                    "grant mapping exceeds the bounded admission size",
                )
            encoded = chunk.encode("utf-8")
            if len(encoded) > remaining:
                raise LandingEffectGrantError(
                    "landing_effect_grant_too_large",
                    "grant mapping exceeds the bounded admission size",
                )
            chunks.append(encoded)
            total += len(encoded)
    except LandingEffectGrantError:
        raise
    except (
        MemoryError,
        RecursionError,
        TypeError,
        UnicodeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise LandingEffectGrantError(
            "landing_effect_grant_not_json", "grant is not canonical JSON data"
        ) from exc
    return b"".join(chunks)


def _digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for key, value in pairs:
        if key in parsed:
            raise LandingEffectGrantError(
                "landing_effect_grant_duplicate_key",
                f"grant artifact contains duplicate JSON member: {key}",
            )
        parsed[key] = value
    return parsed


def _parse_json_bytes(raw: bytes) -> object:
    text = raw.decode("utf-8")
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except LandingEffectGrantError:
        raise
    except json.JSONDecodeError:
        raise
    except ValueError as exc:
        # CPython raises a plain ValueError when an integer exceeds its
        # configured digit limit, even though the input is being parsed as
        # JSON.  Keep every parser failure on the existing JSONDecodeError
        # path so callers retain their typed artifact/request denial.
        raise json.JSONDecodeError("invalid JSON value", text, 0) from exc


def _copy_json(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        copied = json.loads(json.dumps(value, ensure_ascii=False))
    except (
        MemoryError,
        RecursionError,
        TypeError,
        UnicodeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise LandingEffectGrantError(
            "landing_effect_grant_not_json", "grant is not canonical JSON data"
        ) from exc
    if not isinstance(copied, dict):
        raise LandingEffectGrantError(
            "landing_effect_grant_not_json", "grant is not a JSON object"
        )
    return copied


def _same_json(left: object, right: object) -> bool:
    return _canonical_bytes(left) == _canonical_bytes(right)


def _semantic_grant_digest(grant: Mapping[str, Any]) -> str:
    """Hash the grant with its self-referential artifact digest zeroed."""

    candidate = _copy_json(grant)
    candidate["grant_ref"]["artifact_digest"] = ZERO_DIGEST
    return _digest_bytes(_canonical_bytes(candidate))


def _parse_time(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise LandingEffectGrantError(
            "landing_effect_grant_time_invalid", f"{label} is not an RFC3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LandingEffectGrantError(
            "landing_effect_grant_time_invalid", f"{label} is not an RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise LandingEffectGrantError(
            "landing_effect_grant_time_invalid", f"{label} has no timezone"
        )
    try:
        return parsed.astimezone(UTC)
    except OverflowError as exc:
        raise LandingEffectGrantError(
            "landing_effect_grant_time_invalid", f"{label} is outside the UTC datetime range"
        ) from exc


def _now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        raise LandingEffectGrantError(
            "landing_effect_grant_time_invalid", "admission time has no timezone"
        )
    try:
        return value.astimezone(UTC)
    except OverflowError as exc:
        raise LandingEffectGrantError(
            "landing_effect_grant_time_invalid",
            "admission time is outside the UTC datetime range",
        ) from exc


def _schema_errors(grant: Mapping[str, Any]) -> list[str]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LandingEffectGrantError(
            "landing_effect_grant_schema_unavailable",
            "landing-effect grant schema cannot be read",
        ) from exc
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return sorted(
        error.message for error in validator.iter_errors(grant)
    )


def _is_valid_git_ref(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        result = subprocess.run(
            [GIT_EXECUTABLE, "check-ref-format", value],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            env=GIT_REF_VALIDATION_ENV,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _validate_target_refs(grant: Mapping[str, Any]) -> None:
    target = grant["target"]
    ref_fields = (
        ("target.branch", "branch"),
    ) if target["kind"] == "branch" else (
        ("target.base_branch", "base_branch"),
        ("target.head_branch", "head_branch"),
    )
    for label, field in ref_fields:
        if not _is_valid_git_ref(target[field]):
            raise LandingEffectGrantError(
                "landing_effect_grant_target_invalid",
                f"{label} is not a valid Git ref",
            )


def _read_grant_bytes(grant_path: Path) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(grant_path, flags)
    except OSError as exc:
        raise LandingEffectGrantError(
            "landing_effect_grant_unavailable",
            "grant path could not be opened as a regular file",
        ) from exc
    try:
        try:
            metadata = os.fstat(descriptor)
        except OSError as exc:
            raise LandingEffectGrantError(
                "landing_effect_grant_unavailable",
                "grant descriptor could not be inspected",
            ) from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise LandingEffectGrantError(
                "landing_effect_grant_unavailable",
                "grant descriptor is not a regular file",
            )
        if metadata.st_size > MAX_GRANT_BYTES:
            raise LandingEffectGrantError(
                "landing_effect_grant_too_large",
                "grant artifact exceeds the bounded admission size",
            )
        chunks = bytearray()
        while len(chunks) <= MAX_GRANT_BYTES:
            try:
                chunk = os.read(
                    descriptor,
                    min(64 * 1024, MAX_GRANT_BYTES + 1 - len(chunks)),
                )
            except OSError as exc:
                raise LandingEffectGrantError(
                    "landing_effect_grant_unavailable",
                    "grant bytes could not be read from the opened descriptor",
                ) from exc
            if not chunk:
                break
            chunks.extend(chunk)
            if len(chunks) > MAX_GRANT_BYTES:
                raise LandingEffectGrantError(
                    "landing_effect_grant_too_large",
                    "grant artifact exceeds the bounded admission size",
                )
        return bytes(chunks)
    finally:
        os.close(descriptor)


def validate_landing_effect_grant(grant: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and copy a grant document without admitting its scope."""

    if not isinstance(grant, Mapping):
        raise LandingEffectGrantError(
            "landing_effect_grant_schema_invalid", "grant must be a JSON object"
        )
    copied = _copy_json(grant)
    errors = _schema_errors(copied)
    if errors:
        raise LandingEffectGrantError(
            "landing_effect_grant_schema_invalid", errors[0]
        )
    if copied["schema_version"] != SCHEMA_VERSION:
        raise LandingEffectGrantError(
            "landing_effect_grant_schema_invalid", "grant schema version is unsupported"
        )
    if copied["capability_id"] != CAPABILITY_ID:
        raise LandingEffectGrantError(
            "landing_effect_grant_capability_invalid",
            "grant capability is not governed Git landing",
        )
    grant_ref = copied["grant_ref"]
    if grant_ref["owner_repo"] != "abyss-stack":
        raise LandingEffectGrantError(
            "landing_effect_grant_ref_invalid", "grant_ref is not owned by abyss-stack"
        )
    if grant_ref["schema_version"] != SCHEMA_VERSION:
        raise LandingEffectGrantError(
            "landing_effect_grant_ref_invalid", "grant_ref does not name this ABI"
        )
    if grant_ref["schema_ref"] != (
        "schemas/external-codex-governed-landing-effect-grant.schema.json"
    ):
        raise LandingEffectGrantError(
            "landing_effect_grant_ref_invalid", "grant_ref schema coordinate is not exact"
        )
    _validate_target_refs(copied)
    if grant_ref["artifact_digest"] != _semantic_grant_digest(copied):
        raise LandingEffectGrantError(
            "landing_effect_grant_ref_invalid",
            "grant_ref.artifact_digest is not the exact semantic grant digest",
        )
    if copied["review"]["required"] is not True:
        raise LandingEffectGrantError(
            "landing_effect_grant_review_invalid", "landing effects require independent review"
        )
    holder_identity = (
        copied["holder_ref"]["owner_repo"],
        copied["holder_ref"]["artifact_ref"],
    )
    reviewer_identity = (
        copied["review"]["reviewer_ref"]["owner_repo"],
        copied["review"]["reviewer_ref"]["artifact_ref"],
    )
    if holder_identity == reviewer_identity:
        raise LandingEffectGrantError(
            "landing_effect_grant_review_invalid",
            "reviewer identity must differ from holder identity",
        )
    if copied["return_posture"]["status"] != "review_required":
        raise LandingEffectGrantError(
            "landing_effect_grant_return_invalid", "landing effects require reviewed return"
        )
    issued = _parse_time(copied["issued_at"], label="issued_at")
    expires = _parse_time(copied["expires_at"], label="expires_at")
    if expires <= issued:
        raise LandingEffectGrantError(
            "landing_effect_grant_time_invalid", "expires_at must be after issued_at"
        )
    return copied


def load_landing_effect_grant(
    path: str | Path,
    *,
    expected_digest: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Load one exact descriptor-bound grant and verify its byte identity."""

    grant_path = Path(path)
    if not grant_path.is_absolute():
        raise LandingEffectGrantError(
            "landing_effect_grant_unavailable",
            "grant path must be absolute",
        )
    if expected_digest is None:
        raise LandingEffectGrantError(
            "landing_effect_grant_artifact_unbound",
            "loading a grant requires an independent expected artifact digest",
        )
    try:
        raw = _read_grant_bytes(grant_path)
        value = _parse_json_bytes(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise LandingEffectGrantError(
            "landing_effect_grant_unavailable", "grant bytes are not readable JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise LandingEffectGrantError(
            "landing_effect_grant_schema_invalid", "grant must be a JSON object"
        )
    grant = validate_landing_effect_grant(value)
    actual_digest = _digest_bytes(raw)
    if expected_digest != actual_digest:
        raise LandingEffectGrantError(
            "landing_effect_grant_artifact_drift",
            "grant bytes differ from the expected artifact digest",
        )
    return grant, raw


def _expected_effects(request: Mapping[str, Any]) -> set[str]:
    if "effect" in request:
        effect = request["effect"]
        if not isinstance(effect, str) or effect not in LANDING_EFFECTS:
            raise LandingEffectGrantError(
                "landing_effect_request_invalid", "requested effect is not a landing effect"
            )
        effects = {effect}
        if "allowed_effects" in request:
            values = request["allowed_effects"]
            if not isinstance(values, list) or values != [effect]:
                raise LandingEffectGrantError(
                    "landing_effect_grant_scope_wider",
                    "single-effect request contradicts its allowed_effects set",
                )
        return effects
    values = request.get("allowed_effects")
    if not isinstance(values, list) or not values or any(
        not isinstance(value, str) or value not in LANDING_EFFECTS for value in values
    ):
        raise LandingEffectGrantError(
            "landing_effect_request_invalid", "request has no exact landing-effect set"
        )
    if len(values) != len(set(values)):
        raise LandingEffectGrantError(
            "landing_effect_request_invalid", "request landing effects are not unique"
        )
    return set(values)


def admit_landing_effect_grant(
    grant: Mapping[str, Any] | None,
    request: Mapping[str, Any],
    *,
    grant_raw: bytes | None = None,
    expected_artifact_digest: str | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Admit one exact grant against one exact Goal/holder/target request.

    The request is intentionally explicit.  A caller that omits any of the
    Goal, holder, repository, target, effect, review, or return bindings is
    rejected instead of receiving a wildcard match.  A grant with a broader
    effect set is rejected as wider authority, even when it contains the
    requested effect.
    """

    if not isinstance(request, Mapping):
        raise LandingEffectGrantError(
            "landing_effect_request_invalid", "request must be a JSON object"
        )
    try:
        request_raw = _bounded_canonical_bytes(request, limit=MAX_GRANT_BYTES)
    except LandingEffectGrantError as exc:
        code = (
            "landing_effect_request_too_large"
            if exc.code == "landing_effect_grant_too_large"
            else "landing_effect_request_invalid"
        )
        raise LandingEffectGrantError(
            code, "request is not bounded canonical JSON"
        ) from exc
    try:
        normalized_request = _parse_json_bytes(request_raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise LandingEffectGrantError(
            "landing_effect_request_invalid", "request is not bounded canonical JSON"
        ) from exc
    if not isinstance(normalized_request, Mapping):
        raise LandingEffectGrantError(
            "landing_effect_request_invalid", "request must be a JSON object"
        )
    request = normalized_request
    allowed_request_keys = {
        "goal_ref",
        "holder_ref",
        "repository",
        "target",
        "review",
        "return_posture",
        "effect",
        "allowed_effects",
    }
    if set(request) - allowed_request_keys:
        raise LandingEffectGrantError(
            "landing_effect_request_invalid", "request contains unknown fields"
        )
    if grant is None:
        raise LandingEffectGrantError(
            "landing_effect_grant_absent", "no landing-effect grant was supplied"
        )
    if not isinstance(grant_raw, bytes):
        # Preserve the normalized direct-mapping errors for callers that have
        # not supplied an artifact, while still bounding the untrusted object
        # before schema validation can copy and hash it.
        if not isinstance(grant, Mapping):
            raise LandingEffectGrantError(
                "landing_effect_grant_schema_invalid", "grant must be a JSON object"
            )
        _bounded_canonical_bytes(grant, limit=MAX_GRANT_BYTES)
        validate_landing_effect_grant(grant)
        raise LandingEffectGrantError(
            "landing_effect_grant_artifact_unbound",
            "exact grant admission requires the owner artifact bytes",
        )
    if len(grant_raw) > MAX_GRANT_BYTES:
        raise LandingEffectGrantError(
            "landing_effect_grant_too_large",
            "grant artifact exceeds the bounded admission size",
        )
    try:
        parsed = _parse_json_bytes(grant_raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise LandingEffectGrantError(
            "landing_effect_grant_artifact_invalid", "grant artifact is not UTF-8 JSON"
        ) from exc
    if not isinstance(parsed, Mapping):
        raise LandingEffectGrantError(
            "landing_effect_grant_artifact_invalid", "grant artifact is not a JSON object"
        )
    admitted = validate_landing_effect_grant(parsed)
    actual_digest = _digest_bytes(grant_raw)
    if expected_artifact_digest is None:
        raise LandingEffectGrantError(
            "landing_effect_grant_artifact_unbound",
            "exact grant admission requires an independent expected artifact digest",
        )
    if expected_artifact_digest != actual_digest:
        raise LandingEffectGrantError(
            "landing_effect_grant_artifact_drift",
            "grant artifact differs from the expected digest",
        )
    if not isinstance(grant, Mapping):
        raise LandingEffectGrantError(
            "landing_effect_grant_schema_invalid", "grant must be a JSON object"
        )
    if _bounded_canonical_bytes(grant, limit=MAX_GRANT_BYTES) != _canonical_bytes(parsed):
        raise LandingEffectGrantError(
            "landing_effect_grant_artifact_mismatch",
            "grant mapping differs from its supplied artifact bytes",
        )
    semantic_digest = admitted["grant_ref"]["artifact_digest"]

    required_bindings = (
        "goal_ref",
        "holder_ref",
        "repository",
        "target",
        "review",
        "return_posture",
    )
    if any(key not in request for key in required_bindings):
        raise LandingEffectGrantError(
            "landing_effect_request_incomplete",
            "request must bind Goal, holder, repository, target, review, and return",
        )
    for key in required_bindings:
        if not _same_json(admitted[key], request[key]):
            raise LandingEffectGrantError(
                "landing_effect_grant_binding_mismatch",
                f"grant {key} binding differs from the exact request",
            )
    requested_effects = _expected_effects(request)
    granted_effects = set(admitted["allowed_effects"])
    if granted_effects != requested_effects:
        code = (
            "landing_effect_grant_scope_wider"
            if not granted_effects.issubset(requested_effects)
            else "landing_effect_grant_scope_narrower"
        )
        raise LandingEffectGrantError(
            code, "grant allowed_effects is not the exact requested effect set"
        )
    if admitted["review"]["status"] != "approved":
        raise LandingEffectGrantError(
            "landing_effect_grant_review_pending",
            "independent review has not approved the landing grant",
        )
    now = _now(at)
    issued = _parse_time(admitted["issued_at"], label="issued_at")
    expires = _parse_time(admitted["expires_at"], label="expires_at")
    if issued > now:
        raise LandingEffectGrantError(
            "landing_effect_grant_not_yet_valid", "grant issued_at is in the future"
        )
    if expires <= now:
        raise LandingEffectGrantError(
            "landing_effect_grant_stale", "grant expires_at is not in the future"
        )
    result = _copy_json(admitted)
    result["admission"] = {
        "status": "admitted",
        "artifact_digest": semantic_digest,
        "artifact_bytes_digest": actual_digest,
        "evaluated_at": now.isoformat().replace("+00:00", "Z"),
        "effects": sorted(granted_effects),
    }
    return result


def landing_effect_grant_allows(
    grant: Mapping[str, Any] | None,
    request: Mapping[str, Any],
    *,
    grant_raw: bytes | None = None,
    expected_artifact_digest: str | None = None,
    at: datetime | None = None,
) -> bool:
    """Return whether the exact grant can be admitted; default is False."""

    try:
        admit_landing_effect_grant(
            grant,
            request,
            grant_raw=grant_raw,
            expected_artifact_digest=expected_artifact_digest,
            at=at,
        )
    except LandingEffectGrantError:
        return False
    except (MemoryError, RecursionError, TypeError, ValueError, OverflowError):
        # A malformed Mapping is still a denied boolean admission result.
        return False
    return True


__all__ = [
    "CAPABILITY_ID",
    "LANDING_EFFECTS",
    "LandingEffectGrantError",
    "RUNTIME_WIDE_FORBIDDEN_EFFECTS",
    "SCHEMA_PATH",
    "SCHEMA_VERSION",
    "admit_landing_effect_grant",
    "landing_effect_grant_allows",
    "load_landing_effect_grant",
    "validate_landing_effect_grant",
]
