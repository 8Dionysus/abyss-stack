#!/usr/bin/env python3
"""Prepare and enter a projected Codex home for one incarnation.

The operator-visible Codex process and its shell children use the dedicated
incarnation home through Codex's shell environment policy.  Auth/session
continuity and actor tooling enter through the owner-authored capability-class
registry; ambient operator-control and unknown entries remain denied unless a
subject-bound explicit grant projects one entry.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import ctypes
import fcntl
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


LEGACY_SCHEMA_VERSION = "abyss_stack_codex_incarnation_home_v2"
SCHEMA_VERSION = "abyss_stack_codex_incarnation_home_v3"
SUPPORTED_SCHEMA_VERSIONS = frozenset({LEGACY_SCHEMA_VERSION, SCHEMA_VERSION})
CAPABILITY_PROJECTION_SCHEMA_VERSION = (
    "abyss_stack_codex_capability_projection_v2"
)
CAPABILITY_GRANT_SCHEMA_VERSION = "abyss_stack_codex_capability_grant_v1"
CAPABILITY_CLASS_REGISTRY_SCHEMA_VERSION = (
    "abyss_stack_codex_capability_class_registry_v1"
)
CAPABILITY_CLASS_REGISTRY_NAME = "capability-classes.v1.json"
CAPABILITY_CLASS_REGISTRY_PATH = Path(__file__).resolve().with_name(
    CAPABILITY_CLASS_REGISTRY_NAME
)
CAPABILITY_CLASS_POLICIES = {
    "session_continuity": ("shared_link", False),
    "actor_tooling": ("shared_link", False),
    "operator_control": ("denied", True),
}
CAPABILITY_CLASS_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
CAPABILITY_ENTRY_NAME_PATTERN = re.compile(r"^(?!\.\.?$)[^/]+$")
STAGED_FILE_NAME_PATTERN = re.compile(
    r"^\.(?P<target>[^/]+)\.stage-(?P<token>[0-9a-f]{32})$"
)
STAGED_QUARANTINE_NAME_PATTERN = re.compile(
    r"^\.(?P<stage>\.[^/]+\.stage-[0-9a-f]{32})\.quarantine-[0-9a-f]{32}$"
)
HOLDER_RECEIPT_SCHEMA_VERSION = "abyss_stack_visible_incarnation_holder_terminal_v1"
HOLDER_BINDING_CONTEXT_SCHEMA_VERSION = (
    "abyss_stack_visible_incarnation_holder_binding_context_v1"
)
HOLDER_BINDING_CONTEXT_FIELDS = ("holder_ref", "task_ref", "run_ref")
TERMINAL_BINDING_CONTEXT_FIELDS = (
    "goal_ref",
    "actor_ref",
    "incarnation_ref",
    "session_ref",
    "runtime_state_root",
    "closeout_route",
)
HOLDER_CLAIM_SCHEMA_VERSION = "abyss_stack_visible_incarnation_holder_claim_v1"
HOLDER_CLAIM_FILE_NAME = "holder-claim.json"
PREPARATION_LOCK_FILE_NAME = ".incarnation-home.lock"
PREPARATION_OWNER_FILE_NAME = ".prepare-owner.json"
PREPARATION_OWNER_SCHEMA_VERSION = (
    "abyss_stack_visible_incarnation_prepare_owner_v1"
)
HOLDER_LOSS_REENTRY_SCHEMA_VERSION = (
    "task_local_external_actor_holder_loss_reentry_v1"
)
TERMINAL_JOIN_SCHEMA_VERSION = "abyss_stack_visible_incarnation_terminal_join_v1"
CLOSURE_AUTHORIZATION_SCHEMA_VERSION = (
    "abyss_stack_visible_incarnation_terminal_closure_authorization_v1"
)
TERMINAL_CLOSURE_SCHEMA_VERSION = "abyss_stack_visible_incarnation_terminal_closure_v2"
LEGACY_TERMINAL_CLOSURE_SCHEMA_VERSION = (
    "abyss_stack_visible_incarnation_terminal_closure_v1"
)
CLOSURE_RESERVATION_SCHEMA_VERSION = "abyss_stack_visible_incarnation_terminal_closure_reservation_v2"
LEGACY_CLOSURE_RESERVATION_SCHEMA_VERSION = (
    "abyss_stack_visible_incarnation_terminal_closure_reservation_v1"
)
TERMINAL_BINDING_SCHEMA_VERSION = "abyss_stack_visible_terminal_binding_v1"
DESCENDANT_BIN_NAME = ".codex-incarnation-bin"
CODE_MODE_HOST_NAME = "codex-code-mode-host"
CONTROL_SOCKET_ROOT_NAME = "aoa-external-codex"
CONTROL_SOCKET_MODE = 0o600
CONTROL_SOCKET_PARENT_MODE = 0o700
CONTROL_SOCKET_MAX_LENGTH = 103
VISIBLE_LAUNCH_GATE_SCHEMA_VERSION = "abyss_stack_visible_launch_admission_gate_v1"
VISIBLE_LAUNCH_GATE_WAIT_SECONDS = 15.0
VISIBLE_LAUNCH_GATE_POLL_SECONDS = 0.05
VISIBLE_TERMINAL_BINDING_WAIT_SECONDS = 15.0
VISIBLE_TERMINAL_BINDING_POLL_SECONDS = 0.05
SAFE_PROJECTION_FORBIDDEN_KEYS = frozenset(
    {
        "env",
        "environment",
        "environ",
        "token",
        "tokens",
        "secret",
        "secrets",
        "password",
        "credential",
        "credentials",
        "auth",
        "authorization",
        "bearer",
        "api_key",
        "apikey",
        "cookie",
        "cookies",
    }
)
LOCAL_NAMES = frozenset(
    {"config.toml", "cache", "log", "tmp", DESCENDANT_BIN_NAME}
)
ROOT_KEY_LINE = re.compile(
    r"^\s*(?P<key>model|model_reasoning_effort|\"model\"|\"model_reasoning_effort\")\s*="
)
FEATURE_TABLE_LINE = re.compile(
    r"^\s*\[\s*(?:features|\"features\")\s*\]\s*(?:#.*)?$"
)
FEATURE_KEY_LINE = re.compile(r"^\s*(?:multi_agent|\"multi_agent\")\s*=")
FEATURE_DOTTED_LINE = re.compile(r"^\s*features\.multi_agent\s*=")
FEATURE_INLINE_LINE = re.compile(
    r"^(?P<indent>\s*)(?P<key>features|\"features\")\s*=\s*"
    r"(?P<value>\{.*\})(?P<suffix>\s*(?:#.*)?)$"
)
BOOT_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CREDENTIAL_KEY_PATTERN = (
    r"(?:[A-Za-z0-9]+[_-])*"
    r"(?:access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"auth[_-]?token|session[_-]?token|access[_-]?key|"
    r"secret[_-]?access[_-]?key|private[_-]?key|signing[_-]?key|"
    r"encryption[_-]?key|env|environ|environment|token|tokens|secret|"
    r"secrets|password|credential|credentials|auth|authorization|bearer|"
    r"api[_-]?key|apikey|cookie|cookies|key)"
)
CREDENTIAL_KEY_RE = re.compile(rf"(?i)^{CREDENTIAL_KEY_PATTERN}$")


class IncarnationHomeError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _absolute_directory(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise IncarnationHomeError(f"{label} must be an absolute real directory: {path}")
    return path.resolve()


def _regular_file(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise IncarnationHomeError(f"{label} must be an absolute regular file: {path}")
    return path.resolve()


def _decode_json_snapshot(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IncarnationHomeError(f"cannot decode {label}") from exc
    if not isinstance(value, dict):
        raise IncarnationHomeError(f"{label} must be a JSON object")
    return value


def _load_json_snapshot(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = _regular_file(path, label).read_bytes()
    except OSError as exc:
        raise IncarnationHomeError(f"cannot read {label}: {path}") from exc
    return _decode_json_snapshot(raw, label), raw


def _load_json(path: Path, label: str) -> dict[str, Any]:
    value, _ = _load_json_snapshot(path, label)
    return value


def _assert_file_snapshot(path: Path, expected: bytes, label: str) -> None:
    """Fail closed if a file changed after it was validated."""

    try:
        observed = _regular_file(path, label).read_bytes()
    except (IncarnationHomeError, OSError) as exc:
        raise IncarnationHomeError(f"{label} changed during validation") from exc
    if observed != expected:
        raise IncarnationHomeError(f"{label} changed during validation")


def _assert_file_digest(path: Path, expected: str, label: str) -> bytes:
    """Return the current bytes only when their digest is the expected one."""

    if not SHA256_DIGEST_PATTERN.fullmatch(expected):
        raise IncarnationHomeError(f"{label} digest is invalid")
    try:
        observed = _regular_file(path, label).read_bytes()
    except (IncarnationHomeError, OSError) as exc:
        raise IncarnationHomeError(f"{label} changed during validation") from exc
    if sha256_bytes(observed) != expected:
        raise IncarnationHomeError(f"{label} changed during validation")
    return observed


def _realization(path: Path) -> tuple[dict[str, Any], str, str, str, str]:
    value = _load_json(path, "model realization")
    if value.get("schema_version") != "aoa_model_realization_v1":
        raise IncarnationHomeError("unsupported model realization schema")
    configuration = value.get("configuration")
    if not isinstance(configuration, dict):
        raise IncarnationHomeError("model realization lacks configuration")
    runtime = configuration.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("product") != "codex-cli":
        raise IncarnationHomeError("model realization is not for Codex CLI")
    model_slug = runtime.get("model_slug")
    runtime_version = runtime.get("version")
    realization_id = value.get("model_realization_id")
    effort = configuration.get("reasoning_effort")
    if not isinstance(realization_id, str) or not realization_id.strip():
        raise IncarnationHomeError("model realization lacks model_realization_id")
    if not isinstance(model_slug, str) or not model_slug.strip():
        raise IncarnationHomeError("model realization lacks model_slug")
    if not isinstance(runtime_version, str) or not runtime_version.strip():
        raise IncarnationHomeError("model realization lacks runtime version")
    if not isinstance(effort, str) or not effort.strip():
        raise IncarnationHomeError("model realization lacks reasoning_effort")
    fingerprint = sha256_bytes(canonical_bytes(configuration))
    if value.get("configuration_fingerprint") != fingerprint:
        raise IncarnationHomeError("model realization configuration fingerprint mismatch")
    return value, model_slug, effort, runtime_version, fingerprint


def _root_key_line(text: str, key: str, parsed: dict[str, Any]) -> int | None:
    """Locate one unambiguous assignment in the TOML document root."""

    if key not in parsed:
        return None
    for index, line in enumerate(text.splitlines(keepends=True)):
        stripped = line.lstrip()
        if stripped.startswith("["):
            break
        match = ROOT_KEY_LINE.match(line)
        if match and match.group("key").strip('"') == key:
            return index
    raise IncarnationHomeError(
        f"ambient Codex config has an ambiguous root assignment for {key}"
    )


def _replace_line(lines: list[str], index: int, value: str) -> None:
    line_ending = ""
    if lines[index].endswith("\r\n"):
        line_ending = "\r\n"
    elif lines[index].endswith("\n"):
        line_ending = "\n"
    lines[index] = value + line_ending


def _toml_inline_key(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value
    return json.dumps(value, ensure_ascii=False)


def _toml_inline_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_inline_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(
            f"{_toml_inline_key(str(key))} = {_toml_inline_value(item)}"
            for key, item in value.items()
        ) + " }"
    raise IncarnationHomeError(
        "ambient Codex inline features table contains an unsupported value"
    )


def _bind_multi_agent(text: str) -> str:
    """Force the descendant config to keep the governed transport boundary."""

    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise IncarnationHomeError("ambient Codex config is not valid TOML") from exc
    features = parsed.get("features")
    if features is not None and not isinstance(features, dict):
        raise IncarnationHomeError("ambient Codex features table is not a TOML table")
    lines = text.splitlines(keepends=True)
    features_header: int | None = None
    features_end: int | None = None
    features_active = False
    inline_index: int | None = None
    table_seen = False
    feature_index: int | None = None
    dotted_index: int | None = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("["):
            table_seen = True
            if features_active and features_end is None:
                features_end = index
            features_active = bool(FEATURE_TABLE_LINE.match(line))
            if features_active:
                features_header = index
            continue
        if features_active and FEATURE_KEY_LINE.match(line):
            feature_index = index
        elif not features_active and FEATURE_DOTTED_LINE.match(line):
            dotted_index = index
        elif not table_seen and FEATURE_INLINE_LINE.match(line):
            inline_index = index
    if features_active and features_end is None:
        features_end = len(lines)
    if feature_index is not None:
        _replace_line(lines, feature_index, "multi_agent = false")
    elif features_header is not None and features_end is not None:
        lines.insert(features_end, "multi_agent = false\n")
    elif dotted_index is not None:
        _replace_line(lines, dotted_index, "features.multi_agent = false")
    elif inline_index is not None:
        match = FEATURE_INLINE_LINE.match(lines[inline_index])
        if match is None or not isinstance(features, dict):
            raise IncarnationHomeError(
                "ambient Codex inline features table cannot be safely rebound"
            )
        inline_features = dict(features)
        inline_features["multi_agent"] = False
        _replace_line(
            lines,
            inline_index,
            f"{match.group('indent')}{match.group('key')} = "
            f"{_toml_inline_value(inline_features)}{match.group('suffix')}",
        )
    elif features is None:
        lines.extend(["\n", "[features]\n", "multi_agent = false\n"])
    else:
        raise IncarnationHomeError(
            "ambient Codex features table representation is unsupported"
        )
    return "".join(lines)


def _ambient_home_identity(ambient_home: Path) -> str:
    return sha256_bytes(
        canonical_bytes({"ambient_codex_home": str(ambient_home)})
    )


def _load_capability_class_registry() -> tuple[
    dict[str, str], dict[str, dict[str, Any]], dict[str, Any]
]:
    """Load the authored capability meaning and retain its exact source digest."""

    path = _regular_file(
        CAPABILITY_CLASS_REGISTRY_PATH, "capability-class registry"
    )
    value, raw = _load_json_snapshot(path, "capability-class registry")
    required = {"$schema", "schema_version", "classes", "entries", "unknown"}
    if set(value) != required:
        raise IncarnationHomeError("capability-class registry fields are not exact")
    if value.get("$schema") != "schemas/external-codex-capability-classes.schema.json":
        raise IncarnationHomeError("capability-class registry schema binding is invalid")
    if value.get("schema_version") != CAPABILITY_CLASS_REGISTRY_SCHEMA_VERSION:
        raise IncarnationHomeError("unsupported capability-class registry schema")
    classes = value.get("classes")
    if not isinstance(classes, dict) or not classes:
        raise IncarnationHomeError("capability-class registry classes are invalid")

    definitions: dict[str, dict[str, Any]] = {}
    class_definitions: dict[str, dict[str, Any]] = {}
    class_ids: set[str] = set()
    for capability_class, definition in classes.items():
        if (
            not isinstance(capability_class, str)
            or not isinstance(definition, dict)
            or set(definition) != {"projection", "grantable"}
        ):
            raise IncarnationHomeError(
                "capability-class registry definition is not exact"
            )
        projection = definition.get("projection")
        grantable = definition.get("grantable")
        if (
            not isinstance(capability_class, str)
            or CAPABILITY_CLASS_ID_PATTERN.fullmatch(capability_class) is None
            or capability_class == "unknown"
            or capability_class in class_ids
            or projection not in {"shared_link", "denied"}
            or not isinstance(grantable, bool)
        ):
            raise IncarnationHomeError(
                "capability-class registry definition is invalid"
            )
        expected_policy = CAPABILITY_CLASS_POLICIES.get(capability_class)
        if expected_policy is None:
            expected_policy = ("denied", False)
        if (projection, grantable) != expected_policy:
            raise IncarnationHomeError(
                "capability-class registry policy is not an admitted safe tuple"
            )
        class_ids.add(capability_class)
        class_definitions[capability_class] = {
            "projection": projection,
            "grantable": grantable,
        }

    if not set(CAPABILITY_CLASS_POLICIES).issubset(class_ids):
        raise IncarnationHomeError(
            "capability-class registry omits an admitted canonical class"
        )

    entries = value.get("entries")
    if not isinstance(entries, dict):
        raise IncarnationHomeError("capability-class registry entries are invalid")
    for name, capability_class in entries.items():
        if (
            not isinstance(name, str)
            or CAPABILITY_ENTRY_NAME_PATTERN.fullmatch(name) is None
            or name in {".", ".."}
            or name in LOCAL_NAMES
            or Path(name).name != name
            or not isinstance(capability_class, str)
            or CAPABILITY_CLASS_ID_PATTERN.fullmatch(capability_class) is None
            or capability_class == "unknown"
            or capability_class not in class_definitions
        ):
            raise IncarnationHomeError(
                "capability-class registry entry is invalid"
            )
        class_definition = class_definitions[capability_class]
        definitions[name] = {
            "capability_class": capability_class,
            **class_definition,
        }

    unknown = value.get("unknown")
    if not isinstance(unknown, dict) or set(unknown) != {
        "capability_class",
        "projection",
        "grantable",
    }:
        raise IncarnationHomeError("capability-class registry unknown is invalid")
    if (
        unknown.get("capability_class") != "unknown"
        or unknown.get("projection") != "denied"
        or unknown.get("grantable") is not True
    ):
        raise IncarnationHomeError("capability-class registry unknown is not deny-by-default")
    metadata = {
        "path": str(path),
        "sha256": sha256_bytes(raw),
        "schema_version": str(value["schema_version"]),
    }
    return metadata, definitions, dict(unknown)


def _classify_ambient_entry(
    name: str,
    *,
    definitions: dict[str, dict[str, Any]],
    unknown: dict[str, Any],
) -> dict[str, Any]:
    """Resolve one entry through authored data, with an explicit unknown result."""

    return dict(definitions.get(name, unknown))


def _capability_grant_projection(
    *,
    grant_path: Path,
    ambient_home_identity: str,
    model_realization_id: str,
    incarnation_coordinate: str,
) -> tuple[dict[str, Any], bytes]:
    """Validate one reusable, subject-bound exact-entry projection grant."""

    path = _regular_file(grant_path, "capability grant")
    value, raw = _load_json_snapshot(path, "capability grant")
    if value.get("schema_version") != CAPABILITY_GRANT_SCHEMA_VERSION:
        raise IncarnationHomeError("unsupported capability grant schema")
    required = {
        "$schema",
        "schema_version",
        "grant_id",
        "capability_id",
        "capability_class",
        "ambient_entry",
        "effect",
        "subject",
        "expires_at",
    }
    if set(value) != required:
        raise IncarnationHomeError("capability grant fields are not exact")
    if value.get("$schema") != "schemas/external-codex-capability-grant.schema.json":
        raise IncarnationHomeError("capability grant schema binding is invalid")
    grant_id = value.get("grant_id")
    capability_id = value.get("capability_id")
    capability_class = value.get("capability_class")
    ambient_entry = value.get("ambient_entry")
    effect = value.get("effect")
    expires_at = value.get("expires_at")
    if not all(
        isinstance(item, str) and item.strip()
        for item in (grant_id, capability_id, ambient_entry, expires_at)
    ):
        raise IncarnationHomeError("capability grant identity is invalid")
    if (
        capability_class != "operator_control"
        or effect != "project_shared_link"
        or ambient_entry in LOCAL_NAMES
        or Path(ambient_entry).name != ambient_entry
        or ambient_entry in {"", ".", ".."}
        or capability_id != f"codex.home.{ambient_entry}"
    ):
        raise IncarnationHomeError("capability grant scope is invalid")
    subject = value.get("subject")
    if not isinstance(subject, dict) or set(subject) != {
        "ambient_home_identity",
        "model_realization_id",
        "incarnation_coordinate",
    }:
        raise IncarnationHomeError("capability grant subject is invalid")
    if (
        subject.get("ambient_home_identity") != ambient_home_identity
        or subject.get("model_realization_id") != model_realization_id
        or subject.get("incarnation_coordinate") != incarnation_coordinate
    ):
        raise IncarnationHomeError("capability grant subject does not match incarnation")
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IncarnationHomeError("capability grant expiry is invalid") from exc
    if expiry.tzinfo is None or expiry <= datetime.now(UTC):
        raise IncarnationHomeError("capability grant is stale or expired")
    projection = {
        "grant_id": grant_id,
        "capability_id": capability_id,
        "capability_class": capability_class,
        "ambient_entry": ambient_entry,
        "effect": effect,
        "subject": dict(subject),
        "expires_at": expires_at,
        "path": str(path),
        "sha256": sha256_bytes(raw),
    }
    return projection, raw


def _build_capability_projection(
    *,
    ambient_home: Path,
    ambient_home_identity: str,
    model_realization_id: str,
    incarnation_coordinate: str,
    capability_grants: Sequence[Path] = (),
) -> dict[str, Any]:
    """Build the typed home projection; unknown entries are denied by default."""

    registry, definitions, unknown = _load_capability_class_registry()
    grants_by_entry: dict[str, dict[str, Any]] = {}
    grant_ids: set[str] = set()
    for grant_path in capability_grants:
        grant, _raw = _capability_grant_projection(
            grant_path=Path(grant_path),
            ambient_home_identity=ambient_home_identity,
            model_realization_id=model_realization_id,
            incarnation_coordinate=incarnation_coordinate,
        )
        entry = str(grant["ambient_entry"])
        if entry in grants_by_entry or grant["grant_id"] in grant_ids:
            raise IncarnationHomeError("capability grants contain a duplicate identity")
        grants_by_entry[entry] = grant
        grant_ids.add(str(grant["grant_id"]))

    entries: dict[str, dict[str, Any]] = {}
    for source in sorted(ambient_home.iterdir(), key=lambda item: item.name):
        if source.name in LOCAL_NAMES:
            continue
        if source.is_symlink():
            raise IncarnationHomeError(
                f"ambient capability entry may not be a symlink: {source}"
            )
        classification = _classify_ambient_entry(
            source.name,
            definitions=definitions,
            unknown=unknown,
        )
        grant = grants_by_entry.get(source.name)
        if grant is not None and not classification["grantable"]:
            raise IncarnationHomeError(
                "capability grant targets a non-grantable capability entry"
            )
        projected = grant is not None or classification["projection"] == "shared_link"
        entries[source.name] = {
            "capability_class": (
                "operator_control"
                if grant is not None
                else classification["capability_class"]
            ),
            "projection": "shared_link" if projected else "denied",
            "grantable": classification["grantable"],
            "explicit_grant": (
                None
                if grant is None
                else {
                    key: value
                    for key, value in grant.items()
                    if key != "ambient_entry"
                }
            ),
        }
    entry_names = set(entries)
    if set(grants_by_entry) - entry_names:
        raise IncarnationHomeError(
            "capability grant targets an absent ambient capability entry"
        )
    return {
        "schema_version": CAPABILITY_PROJECTION_SCHEMA_VERSION,
        "default_policy": "deny_ambient_operator_control",
        "capability_class_registry": registry,
        "entries": entries,
    }


def _incarnation_coordinate(realization_id: str, fingerprint: str) -> str:
    """Give equal configurations with different realization identities distinct homes."""

    return sha256_bytes(
        canonical_bytes(
            {
                "configuration_fingerprint": fingerprint,
                "model_realization_id": realization_id,
            }
        )
    )


def _holder_binding_context_coordinate(
    context: dict[str, str], binding_digest: str
) -> str:
    """Derive a home coordinate from one exact typed responsibility context."""

    if SHA256_DIGEST_PATTERN.fullmatch(binding_digest) is None:
        raise IncarnationHomeError("holder binding context digest is invalid")
    identity = {
        "schema_version": context["schema_version"],
        **{
            key: context[key]
            for key in TERMINAL_BINDING_CONTEXT_FIELDS
            + HOLDER_BINDING_CONTEXT_FIELDS
        },
        "binding_digest": binding_digest,
    }
    return sha256_bytes(canonical_bytes(identity))


def _holder_binding_manifest_record(
    context: dict[str, str], binding_digest: str, coordinate: str
) -> dict[str, str]:
    if SHA256_DIGEST_PATTERN.fullmatch(binding_digest) is None:
        raise IncarnationHomeError("holder binding context digest is invalid")
    if SHA256_DIGEST_PATTERN.fullmatch(coordinate) is None:
        raise IncarnationHomeError("holder binding coordinate is invalid")
    return {
        "schema_version": context["schema_version"],
        "binding_digest": binding_digest,
        "coordinate": coordinate,
        **{
            key: context[key]
            for key in ("goal_ref", "actor_ref", "incarnation_ref", "session_ref")
            + ("runtime_state_root", "closeout_route")
            + HOLDER_BINDING_CONTEXT_FIELDS
        },
    }


def _holder_incarnation_root(
    *, runtime_root: Path, incarnation_coordinate: str, holder_coordinate: str | None
) -> Path:
    realization_root = runtime_root / (
        "sha256-" + incarnation_coordinate.removeprefix("sha256:")
    )
    if holder_coordinate is None:
        return realization_root
    if SHA256_DIGEST_PATTERN.fullmatch(holder_coordinate) is None:
        raise IncarnationHomeError("holder binding coordinate is invalid")
    return realization_root / (
        "holder-sha256-" + holder_coordinate.removeprefix("sha256:")
    )


def _ambient_inode_identities(ambient_home: Path) -> set[tuple[int, int]]:
    """Collect ambient inode identities from retained directory entries.

    ``DirEntry.inode()`` is the identity returned by the directory's readdir
    snapshot, so it survives a rename between enumeration and the later stat
    of that name.  The descriptor-relative walk never follows an ambient
    symlink and refuses a replacement directory rather than traversing it.
    """

    try:
        initial = os.lstat(ambient_home)
    except OSError as exc:
        raise IncarnationHomeError(
            f"ambient capability entry cannot be inspected: {ambient_home}"
        ) from exc
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISDIR(initial.st_mode):
        raise IncarnationHomeError(
            f"ambient capability entry is not a real directory: {ambient_home}"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        root_fd = os.open(ambient_home, flags)
    except OSError as exc:
        raise IncarnationHomeError(
            f"ambient capability directory cannot be opened: {ambient_home}"
        ) from exc
    pending: list[tuple[int, os.stat_result]] = []
    try:
        root_opened = os.fstat(root_fd)
        if (
            (root_opened.st_dev, root_opened.st_ino, root_opened.st_mode)
            != (initial.st_dev, initial.st_ino, initial.st_mode)
        ):
            raise IncarnationHomeError(
                f"ambient capability directory changed during safe open: {ambient_home}"
            )
        root_identity = (root_opened.st_dev, root_opened.st_ino)
        identities: set[tuple[int, int]] = {root_identity}
        visited_directories: set[tuple[int, int]] = {root_identity}
        pending.append((root_fd, root_opened))
        root_fd = -1
        while pending:
            descriptor, opened_directory = pending.pop()
            try:
                try:
                    with os.scandir(descriptor) as entries:
                        entries_snapshot = list(entries)
                    after_listing = os.fstat(descriptor)
                except OSError as exc:
                    raise IncarnationHomeError(
                        "ambient capability directory cannot be enumerated"
                    ) from exc
                if (
                    (after_listing.st_dev, after_listing.st_ino, after_listing.st_mode)
                    != (
                        opened_directory.st_dev,
                        opened_directory.st_ino,
                        opened_directory.st_mode,
                    )
                ):
                    raise IncarnationHomeError(
                        "ambient capability directory changed during enumeration"
                    )
                parent_device = after_listing.st_dev
                for entry in entries_snapshot:
                    try:
                        directory_entry_inode = entry.inode()
                        directory_entry_is_directory = entry.is_dir(
                            follow_symlinks=False
                        )
                    except OSError as exc:
                        raise IncarnationHomeError(
                            f"ambient capability entry cannot be inspected: {entry.name}"
                        ) from exc
                    if isinstance(directory_entry_inode, int) and directory_entry_inode > 0:
                        identities.add((parent_device, directory_entry_inode))
                    try:
                        observed = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        # The directory entry identity above is the retained
                        # provenance when the name was renamed away before
                        # stat could inspect it.
                        if directory_entry_is_directory:
                            raise IncarnationHomeError(
                                "ambient capability directory changed during enumeration"
                            )
                        if not isinstance(directory_entry_inode, int) or directory_entry_inode < 1:
                            raise IncarnationHomeError(
                                f"ambient capability entry cannot be inspected: {entry.name}"
                            )
                        continue
                    except OSError as exc:
                        raise IncarnationHomeError(
                            f"ambient capability entry cannot be inspected: {entry.name}"
                        ) from exc
                    observed_identity = (observed.st_dev, observed.st_ino)
                    identities.add(observed_identity)
                    if directory_entry_is_directory != stat.S_ISDIR(observed.st_mode):
                        raise IncarnationHomeError(
                            "ambient capability entry changed during enumeration"
                        )
                    if (
                        directory_entry_is_directory
                        and isinstance(directory_entry_inode, int)
                        and directory_entry_inode > 0
                        and (parent_device, directory_entry_inode)
                        != observed_identity
                    ):
                        raise IncarnationHomeError(
                            "ambient capability directory changed during enumeration"
                        )
                    if not stat.S_ISDIR(observed.st_mode):
                        continue
                    child_flags = (
                        os.O_RDONLY
                        | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_NOFOLLOW", 0)
                        | getattr(os, "O_CLOEXEC", 0)
                    )
                    try:
                        child_fd = os.open(
                            entry.name,
                            child_flags,
                            dir_fd=descriptor,
                        )
                    except FileNotFoundError:
                        continue
                    except OSError as exc:
                        raise IncarnationHomeError(
                            f"ambient capability directory cannot be opened: {entry.name}"
                        ) from exc
                    try:
                        child_opened = os.fstat(child_fd)
                    except OSError as exc:
                        os.close(child_fd)
                        raise IncarnationHomeError(
                            f"ambient capability directory cannot be inspected: {entry.name}"
                        ) from exc
                    child_identity = (child_opened.st_dev, child_opened.st_ino)
                    if (
                        not stat.S_ISDIR(child_opened.st_mode)
                        or child_identity != observed_identity
                    ):
                        os.close(child_fd)
                        continue
                    if child_identity in visited_directories:
                        os.close(child_fd)
                        continue
                    visited_directories.add(child_identity)
                    identities.add(child_identity)
                    pending.append((child_fd, child_opened))
            finally:
                os.close(descriptor)
        try:
            current_root = os.lstat(ambient_home)
        except OSError as exc:
            raise IncarnationHomeError(
                f"ambient capability directory changed during enumeration: {ambient_home}"
            ) from exc
        if (
            (current_root.st_dev, current_root.st_ino, current_root.st_mode)
            != (initial.st_dev, initial.st_ino, initial.st_mode)
        ):
            raise IncarnationHomeError(
                f"ambient capability directory changed during enumeration: {ambient_home}"
            )
        return identities
    finally:
        if root_fd >= 0:
            os.close(root_fd)
        while pending:
            descriptor, _opened = pending.pop()
            os.close(descriptor)


def _entry_identity(path: Path, label: str) -> tuple[int, int] | None:
    """Read one pathname identity without following a symlink or alias."""

    try:
        observed = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise IncarnationHomeError(f"{label} cannot be inspected: {path}") from exc
    return observed.st_dev, observed.st_ino


def _identity_record(identity: tuple[int, int] | None) -> dict[str, int] | None:
    if identity is None:
        return None
    return {"device": identity[0], "inode": identity[1]}


def _identity_from_record(value: object, label: str) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"device", "inode"}:
        raise IncarnationHomeError(f"{label} identity is invalid")
    device = value.get("device")
    inode = value.get("inode")
    if (
        not isinstance(device, int)
        or isinstance(device, bool)
        or device < 0
        or not isinstance(inode, int)
        or isinstance(inode, bool)
        or inode < 1
    ):
        raise IncarnationHomeError(f"{label} identity is invalid")
    return device, inode


def _actor_local_open_flags(observed: os.stat_result) -> int:
    if stat.S_ISDIR(observed.st_mode):
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    else:
        flags = getattr(os, "O_PATH", os.O_RDONLY)
    return flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


def _actor_local_identity_mode(observed: os.stat_result) -> tuple[int, int, int]:
    return observed.st_dev, observed.st_ino, observed.st_mode


def _open_stable_actor_local_path_descriptor(
    target: Path, name: str
) -> tuple[int, os.stat_result, os.stat_result]:
    """Open one path without following a replacement symlink and retain it."""

    try:
        initial = os.lstat(target)
    except OSError as exc:
        raise IncarnationHomeError(
            f"actor-local capability entry cannot be inspected: {target}"
        ) from exc
    if stat.S_ISLNK(initial.st_mode):
        raise IncarnationHomeError(
            f"actor-local capability entry may not be a symlink: {target}"
        )
    try:
        descriptor = os.open(target, _actor_local_open_flags(initial))
    except OSError as exc:
        raise IncarnationHomeError(
            f"actor-local capability entry cannot be opened safely: {target}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        observed = os.lstat(target)
        if (
            _actor_local_identity_mode(opened) != _actor_local_identity_mode(initial)
            or _actor_local_identity_mode(opened) != _actor_local_identity_mode(observed)
        ):
            raise IncarnationHomeError(
                f"actor-local capability entry changed during validation: {name}"
            )
        return descriptor, initial, opened
    except IncarnationHomeError:
        os.close(descriptor)
        raise
    except OSError as exc:
        os.close(descriptor)
        raise IncarnationHomeError(
            f"actor-local capability entry cannot be inspected: {target}"
        ) from exc


def _open_stable_actor_local_child_descriptor(
    parent_fd: int, child_name: str, label: str
) -> tuple[int, os.stat_result, os.stat_result]:
    """Open one directory child relative to a retained parent descriptor."""

    try:
        initial = os.stat(child_name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise IncarnationHomeError(
            f"actor-local capability entry cannot be inspected: {label}"
        ) from exc
    if stat.S_ISLNK(initial.st_mode):
        raise IncarnationHomeError(
            f"actor-local capability entry may not be a symlink: {label}"
        )
    try:
        descriptor = os.open(
            child_name,
            _actor_local_open_flags(initial),
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise IncarnationHomeError(
            f"actor-local capability entry cannot be opened safely: {label}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        observed = os.stat(child_name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            _actor_local_identity_mode(opened) != _actor_local_identity_mode(initial)
            or _actor_local_identity_mode(opened) != _actor_local_identity_mode(observed)
        ):
            raise IncarnationHomeError(
                f"actor-local capability entry changed during validation: {label}"
            )
        return descriptor, initial, opened
    except IncarnationHomeError:
        os.close(descriptor)
        raise
    except OSError as exc:
        os.close(descriptor)
        raise IncarnationHomeError(
            f"actor-local capability entry cannot be inspected: {label}"
        ) from exc


def _revalidate_actor_local_path(
    target: Path,
    descriptor: int,
    initial: os.stat_result,
    label: str,
) -> None:
    try:
        observed = os.lstat(target)
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise IncarnationHomeError(
            f"actor-local capability entry changed during validation: {label}"
        ) from exc
    if (
        _actor_local_identity_mode(opened) != _actor_local_identity_mode(initial)
        or _actor_local_identity_mode(opened) != _actor_local_identity_mode(observed)
    ):
        raise IncarnationHomeError(
            f"actor-local capability entry changed during validation: {label}"
        )


def _revalidate_actor_local_child(
    parent_fd: int,
    child_name: str,
    descriptor: int,
    initial: os.stat_result,
    label: str,
) -> None:
    try:
        observed = os.stat(child_name, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise IncarnationHomeError(
            f"actor-local capability entry changed during validation: {label}"
        ) from exc
    if (
        _actor_local_identity_mode(opened) != _actor_local_identity_mode(initial)
        or _actor_local_identity_mode(opened) != _actor_local_identity_mode(observed)
    ):
        raise IncarnationHomeError(
            f"actor-local capability entry changed during validation: {label}"
        )


def _walk_stable_actor_local_tree(
    target: Path, name: str
) -> list[tuple[str, os.stat_result]]:
    """Walk actor-local state through retained descriptors, not mutable paths."""

    root_fd, root_initial, root_opened = _open_stable_actor_local_path_descriptor(
        target, name
    )
    records: list[tuple[str, os.stat_result]] = []
    visited_directories: set[tuple[int, int]] = set()

    def visit(
        descriptor: int,
        initial: os.stat_result,
        opened: os.stat_result,
        relative: str,
        *,
        parent_fd: int | None,
        child_name: str | None,
    ) -> None:
        try:
            current = os.fstat(descriptor)
            if _actor_local_identity_mode(current) != _actor_local_identity_mode(opened):
                raise IncarnationHomeError(
                    f"actor-local capability entry changed during validation: {relative}"
                )
            records.append((relative, current))
            if stat.S_ISDIR(current.st_mode):
                identity = (current.st_dev, current.st_ino)
                if identity in visited_directories:
                    raise IncarnationHomeError(
                        f"actor-local capability directory is aliased: {relative}"
                    )
                visited_directories.add(identity)
                try:
                    children = sorted(os.listdir(descriptor))
                    after_listing = os.fstat(descriptor)
                except OSError as exc:
                    raise IncarnationHomeError(
                        f"actor-local capability directory cannot be enumerated: {relative}"
                    ) from exc
                if _actor_local_identity_mode(after_listing) != _actor_local_identity_mode(current):
                    raise IncarnationHomeError(
                        f"actor-local capability directory changed during validation: {relative}"
                    )
                for child_name_value in children:
                    child_label = f"{relative}/{child_name_value}"
                    child_fd, child_initial, child_opened = (
                        _open_stable_actor_local_child_descriptor(
                            descriptor, child_name_value, child_label
                        )
                    )
                    visit(
                        child_fd,
                        child_initial,
                        child_opened,
                        child_label,
                        parent_fd=descriptor,
                        child_name=child_name_value,
                    )
            if parent_fd is None:
                _revalidate_actor_local_path(
                    target, descriptor, initial, relative
                )
            else:
                assert child_name is not None
                _revalidate_actor_local_child(
                    parent_fd, child_name, descriptor, initial, relative
                )
        finally:
            os.close(descriptor)

    visit(
        root_fd,
        root_initial,
        root_opened,
        name,
        parent_fd=None,
        child_name=None,
    )
    return records


def _open_stable_actor_local_entry(target: Path, name: str) -> os.stat_result:
    """Open one entry without following a replacement symlink and recheck it."""

    descriptor, _initial, opened = _open_stable_actor_local_path_descriptor(
        target, name
    )
    try:
        return opened
    finally:
        os.close(descriptor)


def _validate_actor_local_entry(
    target: Path,
    name: str,
    *,
    ambient_identities: set[tuple[int, int]] | None = None,
) -> None:
    """Permit only unaliased Codex-owned regular files/directories."""

    ambient_identities = ambient_identities or set()
    for label, observed in _walk_stable_actor_local_tree(target, name):
        identity = (observed.st_dev, observed.st_ino)
        mode = observed.st_mode
        if identity in ambient_identities:
            raise IncarnationHomeError(
                f"actor-local capability entry aliases ambient state: {label}"
            )
        if stat.S_ISREG(mode):
            if observed.st_nlink != 1:
                raise IncarnationHomeError(
                    f"actor-local capability entry is multiply linked: {label}"
                )
        elif not stat.S_ISDIR(mode):
            raise IncarnationHomeError(
                f"actor-local capability entry is not a regular file or directory: {label}"
            )


def _validate_actor_local_entries(
    codex_home: Path,
    names: Sequence[str],
    ambient_home: Path,
    *,
    initially_ambient_identities: set[tuple[int, int]] | None = None,
) -> None:
    ambient_identities = _ambient_inode_identities(ambient_home)
    if initially_ambient_identities is not None:
        # Keep the first ambient classification in force for the complete
        # materialization.  A denied inode can otherwise be moved into the
        # holder home and replaced at its ambient pathname before this final
        # walk, making a severed alias look newly actor-local.
        ambient_identities.update(initially_ambient_identities)
    for name in names:
        target = codex_home / name
        if target.exists() or target.is_symlink():
            _validate_actor_local_entry(
                target,
                name,
                ambient_identities=ambient_identities,
            )


def _local_tree_digest(target: Path, name: str) -> str | None:
    """Digest one local tree's bounded inode topology, never its mutable bytes."""

    if not target.exists() and not target.is_symlink():
        return None
    rows: list[dict[str, object]] = []
    for relative, observed in _walk_stable_actor_local_tree(target, name):
        rows.append(
            {
                "path": relative,
                "device": observed.st_dev,
                "inode": observed.st_ino,
                "mode": stat.S_IMODE(observed.st_mode),
                "kind": "directory" if stat.S_ISDIR(observed.st_mode) else "file",
                "links": observed.st_nlink,
            }
        )
    return sha256_bytes(canonical_bytes(rows))


def _denied_state_provenance(
    *,
    codex_home: Path,
    ambient_home: Path,
    names: Sequence[str],
    initially_ambient_identities: set[tuple[int, int]] | None = None,
) -> dict[str, dict[str, object]]:
    """Record one current identity and one admitted local-tree digest per name."""

    ambient_identities = _ambient_inode_identities(ambient_home)
    if initially_ambient_identities is not None:
        ambient_identities.update(initially_ambient_identities)
    provenance: dict[str, dict[str, object]] = {}
    for name in names:
        target = codex_home / name
        if target.exists() or target.is_symlink():
            _validate_actor_local_entry(
                target,
                name,
                ambient_identities=ambient_identities,
            )
        provenance[name] = {
            "ambient_entry": _identity_record(
                _entry_identity(ambient_home / name, f"ambient denied entry {name}")
            ),
            "local_tree_digest": _local_tree_digest(target, name),
        }
    return provenance


def _validate_denied_state_provenance(
    *,
    manifest: dict[str, Any],
    codex_home: Path,
    ambient_home: Path,
    names: Sequence[str],
    required: bool,
    allow_projection_expansion: bool = False,
) -> None:
    """Reject unknown local state after an ambient denied-entry transition.

    The record is bounded by the current typed denied projection: it stores no
    path/history denylist.  A changed ambient identity is safe only when the
    local tree is the exact tree already admitted by the previous manifest.
    """

    raw = manifest.get("denied_state_provenance")
    if raw is None:
        if required:
            raise IncarnationHomeError(
                "current incarnation-home manifest lacks denied-state provenance"
            )
        return
    if not isinstance(raw, dict) or (
        set(raw) != set(names)
        and (
            not allow_projection_expansion
            or not set(raw) <= set(names)
        )
    ):
        raise IncarnationHomeError("denied-state provenance does not match projection")
    for name in names:
        record = raw.get(name)
        if record is None and allow_projection_expansion:
            continue
        if not isinstance(record, dict) or set(record) != {
            "ambient_entry",
            "local_tree_digest",
        }:
            raise IncarnationHomeError(
                f"denied-state provenance is invalid for {name}"
            )
        previous_ambient = _identity_from_record(
            record.get("ambient_entry"), f"denied-state ambient {name}"
        )
        previous_local = record.get("local_tree_digest")
        if previous_local is not None and (
            not isinstance(previous_local, str)
            or SHA256_DIGEST_PATTERN.fullmatch(previous_local) is None
        ):
            raise IncarnationHomeError(
                f"denied-state local provenance is invalid for {name}"
            )
        current_ambient = _entry_identity(
            ambient_home / name, f"ambient denied entry {name}"
        )
        current_local = _local_tree_digest(codex_home / name, name)
        if current_ambient != previous_ambient and current_local != previous_local:
            raise IncarnationHomeError(
                f"denied-state provenance changed across ambient replacement: {name}"
            )


def _reject_custom_model_provider(parsed: dict[str, Any]) -> None:
    """Fail closed when ambient config selects a provider outside the realization."""

    if "model_provider" in parsed:
        raise IncarnationHomeError(
            "ambient Codex config must not select an unbound model_provider"
        )


def _bound_config(ambient_config: bytes, model_slug: str, effort: str) -> bytes:
    try:
        text = ambient_config.decode("utf-8")
    except UnicodeError as exc:
        raise IncarnationHomeError("ambient Codex config is not UTF-8") from exc
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise IncarnationHomeError("ambient Codex config is not valid TOML") from exc
    _reject_custom_model_provider(parsed)
    model_value = f'model = {json.dumps(model_slug)}'
    effort_value = f'model_reasoning_effort = {json.dumps(effort)}'
    lines = text.splitlines(keepends=True)
    model_index = _root_key_line(text, "model", parsed)
    effort_index = _root_key_line(text, "model_reasoning_effort", parsed)
    if model_index is None:
        lines.insert(0, model_value + "\n")
        if effort_index is not None:
            effort_index += 1
    else:
        _replace_line(lines, model_index, model_value)
    if effort_index is None:
        lines.insert(0, effort_value + "\n")
    else:
        _replace_line(lines, effort_index, effort_value)
    bound = _bind_multi_agent("".join(lines))
    try:
        bound_parsed = tomllib.loads(bound)
    except tomllib.TOMLDecodeError as exc:
        raise IncarnationHomeError(
            "ambient Codex config cannot be safely rebound at the TOML root"
        ) from exc
    if (
        bound_parsed.get("model") != model_slug
        or bound_parsed.get("model_reasoning_effort") != effort
        or not isinstance(bound_parsed.get("features"), dict)
        or bound_parsed["features"].get("multi_agent") is not False
    ):
        raise IncarnationHomeError("ambient Codex config root binding did not take effect")
    return bound.encode("utf-8")


def _open_pinned_parent_directory(path: Path, label: str) -> int:
    """Open and pin one target parent before any file mutation."""

    if not path.is_absolute() or not path.name:
        raise IncarnationHomeError(f"{label} must be an absolute file path: {path}")
    parent = path.parent
    try:
        observed = os.lstat(parent)
    except OSError as exc:
        raise IncarnationHomeError(
            f"{label} parent cannot be inspected: {parent}"
        ) from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise IncarnationHomeError(f"{label} parent must be a real directory: {parent}")
    flags = os.O_RDONLY
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        parent_fd = os.open(parent, flags)
    except OSError as exc:
        raise IncarnationHomeError(
            f"{label} parent cannot be opened safely: {parent}"
        ) from exc
    try:
        opened = os.fstat(parent_fd)
        if (
            (opened.st_dev, opened.st_ino, opened.st_mode)
            != (observed.st_dev, observed.st_ino, observed.st_mode)
        ):
            raise IncarnationHomeError(
                f"{label} parent changed during safe open: {parent}"
            )
        return parent_fd
    except IncarnationHomeError:
        os.close(parent_fd)
        raise
    except OSError as exc:
        os.close(parent_fd)
        raise IncarnationHomeError(
            f"{label} parent cannot be inspected after safe open: {parent}"
        ) from exc


def _open_stable_regular_file_at(
    parent_fd: int,
    name: str,
    *,
    label: str,
    ambient_identities: set[tuple[int, int]],
    writable: bool = False,
) -> tuple[int, os.stat_result]:
    """Open one regular child through a pinned parent and recheck its identity."""

    try:
        initial = os.lstat(name, dir_fd=parent_fd)
    except OSError as exc:
        raise IncarnationHomeError(f"{label} cannot be inspected") from exc
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise IncarnationHomeError(f"{label} is not a regular file")
    flags = (os.O_RDWR if writable else os.O_RDONLY) | getattr(
        os, "O_NOFOLLOW", 0
    ) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise IncarnationHomeError(f"{label} cannot be opened safely") from exc
    try:
        opened = os.fstat(descriptor)
        observed = os.lstat(name, dir_fd=parent_fd)
        if (
            (opened.st_dev, opened.st_ino, opened.st_mode)
            != (initial.st_dev, initial.st_ino, initial.st_mode)
            or (opened.st_dev, opened.st_ino, opened.st_mode)
            != (observed.st_dev, observed.st_ino, observed.st_mode)
            or (opened.st_dev, opened.st_ino) in ambient_identities
            or opened.st_nlink != 1
        ):
            raise IncarnationHomeError(f"{label} changed during safe validation")
        return descriptor, opened
    except IncarnationHomeError:
        os.close(descriptor)
        raise
    except OSError as exc:
        os.close(descriptor)
        raise IncarnationHomeError(f"{label} cannot be revalidated safely") from exc


def _read_descriptor_bytes(descriptor: int, label: str) -> bytes:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except OSError as exc:
        raise IncarnationHomeError(f"{label} cannot be read safely") from exc


def _create_unnameable_temporary_file_at(parent_fd: int, label: str) -> int:
    """Create a temporary inode that has no replaceable source pathname."""

    tmpfile = getattr(os, "O_TMPFILE", 0)
    if not tmpfile:
        raise IncarnationHomeError(
            f"{label} requires an unnameable temporary file boundary"
        )
    flags = tmpfile | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(".", flags, 0o600, dir_fd=parent_fd)
    except OSError as exc:
        raise IncarnationHomeError(
            f"{label} cannot create an unnameable temporary file"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 0:
            raise IncarnationHomeError(
                f"{label} temporary inode is not unnameable"
            )
        return descriptor
    except IncarnationHomeError:
        os.close(descriptor)
        raise
    except OSError as exc:
        os.close(descriptor)
        raise IncarnationHomeError(
            f"{label} temporary inode cannot be validated"
        ) from exc


def _write_descriptor_exact(
    descriptor: int, content: bytes, mode: int, label: str
) -> None:
    """Write one already-admitted descriptor without reopening its pathname."""

    try:
        os.fchmod(descriptor, mode)
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        view = memoryview(content)
        while view:
            view = view[os.write(descriptor, view) :]
        os.fsync(descriptor)
    except OSError as exc:
        raise IncarnationHomeError(f"cannot write admitted file: {label}") from exc


def _revalidate_regular_file_at(
    parent_fd: int,
    name: str,
    descriptor: int,
    initial: os.stat_result,
    *,
    label: str,
    ambient_identities: set[tuple[int, int]],
) -> None:
    """Recheck a retained regular-file descriptor before a name-based effect."""

    try:
        opened = os.fstat(descriptor)
        observed = os.lstat(name, dir_fd=parent_fd)
    except OSError as exc:
        raise IncarnationHomeError(f"{label} changed before mutation") from exc
    if (
        (opened.st_dev, opened.st_ino, opened.st_mode)
        != (initial.st_dev, initial.st_ino, initial.st_mode)
        or (opened.st_dev, opened.st_ino, opened.st_mode)
        != (observed.st_dev, observed.st_ino, observed.st_mode)
        or not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or (opened.st_dev, opened.st_ino) in ambient_identities
    ):
        raise IncarnationHomeError(f"{label} changed before mutation")


def _revalidate_writable_regular_file_at(
    parent_fd: int,
    name: str,
    descriptor: int,
    initial: os.stat_result,
    *,
    label: str,
    ambient_identities: set[tuple[int, int]],
) -> None:
    """Recheck a writable descriptor immediately before its first effect."""

    _revalidate_regular_file_at(
        parent_fd,
        name,
        descriptor,
        initial,
        label=label,
        ambient_identities=ambient_identities,
    )


def _publish_unnameable_file_at(
    parent_fd: int, descriptor: int, name: str, label: str
) -> None:
    """Create the destination link from the admitted descriptor, never its name."""

    try:
        os.link(
            f"/proc/self/fd/{descriptor}",
            name,
            dst_dir_fd=parent_fd,
            follow_symlinks=True,
        )
    except FileExistsError as exc:
        raise IncarnationHomeError(f"{label} already exists") from exc
    except OSError as exc:
        raise IncarnationHomeError(
            f"cannot publish unnameable {label}"
        ) from exc


def _stage_unnameable_file_at(
    parent_fd: int, target_name: str, descriptor: int, label: str
) -> str:
    """Give a fully written anonymous inode one private staging name."""

    for _attempt in range(8):
        staged_name = f".{target_name}.stage-{secrets.token_hex(16)}"
        try:
            os.link(
                f"/proc/self/fd/{descriptor}",
                staged_name,
                dst_dir_fd=parent_fd,
                follow_symlinks=True,
            )
            return staged_name
        except FileExistsError:
            continue
        except OSError as exc:
            raise IncarnationHomeError(
                f"cannot stage unnameable {label}"
            ) from exc
    raise IncarnationHomeError(f"cannot allocate a private staging name for {label}")


def _remove_staged_file_at(
    parent_fd: int, name: str, descriptor: int, label: str
) -> None:
    """Remove only the exact private staging link retained by descriptor.

    The staging name is first moved into a private, newly-created directory.
    The final unlink therefore targets the quarantined inode rather than a
    mutable destination pathname; a replacement at the original name is
    preserved and causes a fail-closed error.
    """

    try:
        observed = os.lstat(name, dir_fd=parent_fd)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise IncarnationHomeError(f"{label} staging entry cannot be inspected") from exc
    try:
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise IncarnationHomeError(f"{label} staging inode cannot be inspected") from exc
    if (
        (observed.st_dev, observed.st_ino, observed.st_mode)
        != (opened.st_dev, opened.st_ino, opened.st_mode)
        or not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
    ):
        raise IncarnationHomeError(f"{label} staging entry changed before cleanup")
    quarantine_name: str | None = None
    quarantine_fd: int | None = None
    quarantine_opened: os.stat_result | None = None
    quarantine_entry_moved = False
    try:
        for _attempt in range(8):
            candidate = f".{name}.quarantine-{secrets.token_hex(16)}"
            try:
                os.mkdir(candidate, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                continue
            quarantine_name = candidate
            break
        if quarantine_name is None:
            raise IncarnationHomeError(
                f"{label} could not allocate a private cleanup directory"
            )
        quarantine_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            quarantine_fd = os.open(
                quarantine_name,
                quarantine_flags,
                dir_fd=parent_fd,
            )
            quarantine_opened = os.fstat(quarantine_fd)
            quarantine_observed = os.lstat(quarantine_name, dir_fd=parent_fd)
            if (
                (quarantine_opened.st_dev, quarantine_opened.st_ino, quarantine_opened.st_mode)
                != (
                    quarantine_observed.st_dev,
                    quarantine_observed.st_ino,
                    quarantine_observed.st_mode,
                )
                or not stat.S_ISDIR(quarantine_opened.st_mode)
            ):
                raise IncarnationHomeError(
                    f"{label} cleanup directory changed during safe open"
                )
            try:
                os.rename(
                    name,
                    name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=quarantine_fd,
                )
            except FileNotFoundError:
                return
            except OSError as exc:
                raise IncarnationHomeError(
                    f"{label} staging entry could not be quarantined"
                ) from exc
            quarantine_entry_moved = True
            quarantined = os.lstat(name, dir_fd=quarantine_fd)
            retained = os.fstat(descriptor)
            if (
                (quarantined.st_dev, quarantined.st_ino, quarantined.st_mode)
                != (retained.st_dev, retained.st_ino, retained.st_mode)
                or not stat.S_ISREG(retained.st_mode)
                or retained.st_nlink != 1
            ):
                raise IncarnationHomeError(
                    f"{label} staging entry changed during quarantine"
                )
            os.unlink(name, dir_fd=quarantine_fd)
            quarantine_entry_moved = False
        except FileNotFoundError:
            if not quarantine_entry_moved:
                return
            raise
    except IncarnationHomeError:
        raise
    except OSError as exc:
        raise IncarnationHomeError(f"{label} staging entry could not be removed") from exc
    finally:
        try:
            if quarantine_name is not None and not quarantine_entry_moved:
                if quarantine_fd is None or quarantine_opened is None:
                    raise IncarnationHomeError(
                        f"{label} cleanup directory was not safely opened"
                    )
                _revalidate_recovery_entry(
                    parent_fd,
                    quarantine_name,
                    quarantine_fd,
                    quarantine_opened,
                    f"{label} cleanup directory",
                )
                try:
                    os.rmdir(quarantine_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise IncarnationHomeError(
                        f"{label} cleanup directory could not be removed"
                    ) from exc
        finally:
            if quarantine_fd is not None:
                os.close(quarantine_fd)


def _recover_abandoned_staged_files(
    codex_home: Path,
    *,
    ambient_identities: set[tuple[int, int]],
) -> None:
    """Remove only inode-validated stages left by an interrupted publication."""

    parent_fd = _open_pinned_parent_directory(
        codex_home / "config.toml", "incarnation Codex home staging recovery"
    )
    changed = False
    try:
        try:
            names = sorted(os.listdir(parent_fd))
        except OSError as exc:
            raise IncarnationHomeError(
                "incarnation Codex home staging entries cannot be enumerated"
            ) from exc
        for name in names:
            match = STAGED_FILE_NAME_PATTERN.fullmatch(name)
            if match is not None:
                if match.group("target") not in LOCAL_NAMES:
                    continue
                try:
                    observed = os.lstat(name, dir_fd=parent_fd)
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise IncarnationHomeError(
                        f"abandoned staging entry cannot be inspected: {name}"
                    ) from exc
                if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
                    raise IncarnationHomeError(
                        f"abandoned staging entry is not an isolated regular file: {name}"
                    )
                descriptor, _opened = _open_stable_regular_file_at(
                    parent_fd,
                    name,
                    label=f"abandoned staging entry {name}",
                    ambient_identities=ambient_identities,
                )
                try:
                    _remove_staged_file_at(
                        parent_fd,
                        name,
                        descriptor,
                        f"abandoned staging entry {name}",
                    )
                    changed = True
                finally:
                    os.close(descriptor)
                continue
            quarantine = STAGED_QUARANTINE_NAME_PATTERN.fullmatch(name)
            if quarantine is None:
                continue
            stage_name = quarantine.group("stage")
            stage_match = STAGED_FILE_NAME_PATTERN.fullmatch(stage_name)
            if stage_match is None or stage_match.group("target") not in LOCAL_NAMES:
                continue
            _recover_staging_quarantine_directory_at(
                parent_fd,
                name,
                stage_name=stage_name,
                ambient_identities=ambient_identities,
            )
            changed = True
        if changed:
            os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _rename_exchange_at(
    parent_fd: int, source_name: str, target_name: str, label: str
) -> None:
    """Atomically exchange two names without unlinking an unvalidated target."""

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except (AttributeError, OSError) as exc:
        raise IncarnationHomeError(
            f"{label} requires atomic exchange support"
        ) from exc
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        parent_fd,
        os.fsencode(source_name),
        parent_fd,
        os.fsencode(target_name),
        0x2,  # Linux renameat2 RENAME_EXCHANGE.
    )
    if result != 0:
        error_number = ctypes.get_errno()
        detail = os.strerror(error_number) if error_number else "unknown error"
        raise IncarnationHomeError(f"{label} atomic exchange failed: {detail}")


def _recover_staging_quarantine_directory_at(
    parent_fd: int,
    name: str,
    *,
    stage_name: str,
    ambient_identities: set[tuple[int, int]],
) -> None:
    """Recover one owner-created quarantine directory without path trust."""

    descriptor, initial, opened = _open_recovery_directory_at(
        parent_fd,
        name,
        f"staging quarantine {name}",
    )
    try:
        try:
            children = sorted(os.listdir(descriptor))
        except OSError as exc:
            raise IncarnationHomeError(
                f"staging quarantine cannot be enumerated: {name}"
            ) from exc
        if any(child != stage_name for child in children):
            raise IncarnationHomeError(
                f"staging quarantine contains an unexpected entry: {name}"
            )
        if children:
            child = children[0]
            child_descriptor, _child_opened = _open_stable_regular_file_at(
                descriptor,
                child,
                label=f"staging quarantine entry {name}/{child}",
                ambient_identities=ambient_identities,
            )
            try:
                _remove_staged_file_at(
                    descriptor,
                    child,
                    child_descriptor,
                    f"staging quarantine entry {name}/{child}",
                )
            finally:
                os.close(child_descriptor)
        _revalidate_recovery_entry(
            parent_fd,
            name,
            descriptor,
            initial,
            f"staging quarantine {name}",
        )
        try:
            os.rmdir(name, dir_fd=parent_fd)
        except OSError as exc:
            raise IncarnationHomeError(
                f"staging quarantine could not be removed: {name}"
            ) from exc
    finally:
        os.close(descriptor)


def _replace_with_staged_file_at(
    *,
    parent_fd: int,
    target_name: str,
    target_descriptor: int,
    target_initial: os.stat_result,
    staged_descriptor: int,
    label: str,
    ambient_identities: set[tuple[int, int]],
) -> None:
    """Atomically publish a fully written replacement after identity rechecks."""

    staged_name: str | None = None
    try:
        staged_name = _stage_unnameable_file_at(
            parent_fd, target_name, staged_descriptor, label
        )
        staged_initial = os.fstat(staged_descriptor)
        _revalidate_regular_file_at(
            parent_fd,
            staged_name,
            staged_descriptor,
            staged_initial,
            label=f"{label} staged file",
            ambient_identities=ambient_identities,
        )
        _revalidate_regular_file_at(
            parent_fd,
            target_name,
            target_descriptor,
            target_initial,
            label=label,
            ambient_identities=ambient_identities,
        )
        _rename_exchange_at(parent_fd, staged_name, target_name, label)
        try:
            published = os.lstat(target_name, dir_fd=parent_fd)
            displaced = os.lstat(staged_name, dir_fd=parent_fd)
            staged = os.fstat(staged_descriptor)
            retained_target = os.fstat(target_descriptor)
        except OSError as exc:
            raise IncarnationHomeError(f"{label} changed after exchange") from exc
        published_matches_stage = (
            (published.st_dev, published.st_ino, published.st_mode)
            == (staged.st_dev, staged.st_ino, staged.st_mode)
            and stat.S_ISREG(staged.st_mode)
            and staged.st_nlink == 1
            and (staged.st_dev, staged.st_ino) not in ambient_identities
        )
        displaced_matches_target = (
            (displaced.st_dev, displaced.st_ino, displaced.st_mode)
            == (
                retained_target.st_dev,
                retained_target.st_ino,
                retained_target.st_mode,
            )
            and stat.S_ISREG(retained_target.st_mode)
        )
        if not (published_matches_stage and displaced_matches_target):
            if published_matches_stage:
                try:
                    _rename_exchange_at(
                        parent_fd,
                        target_name,
                        staged_name,
                        f"{label} rollback",
                    )
                except IncarnationHomeError:
                    staged_name = None
                    raise
                _remove_staged_file_at(
                    parent_fd,
                    staged_name,
                    staged_descriptor,
                    f"{label} rollback staged file",
                )
                staged_name = None
            raise IncarnationHomeError(f"{label} target changed during exchange")
        displaced_name = staged_name
        staged_name = None
        _remove_staged_file_at(
            parent_fd,
            displaced_name,
            target_descriptor,
            f"{label} displaced target",
        )
    finally:
        if staged_name is not None:
            _remove_staged_file_at(
                parent_fd, staged_name, staged_descriptor, f"{label} staged file"
            )


def _write_exact(
    path: Path,
    content: bytes,
    mode: int,
    *,
    ambient_identities: set[tuple[int, int]] | None = None,
) -> None:
    """Publish bytes only after the current target has passed alias admission."""

    ambient_identities = ambient_identities or set()
    parent_fd = _open_pinned_parent_directory(path, "exact file")
    existing_descriptor: int | None = None
    staged_descriptor: int | None = None
    try:
        try:
            existing = os.lstat(path.name, dir_fd=parent_fd)
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise IncarnationHomeError(
                f"refusing to inspect unsafe file path: {path}"
            ) from exc
        if existing is not None:
            existing_descriptor, opened = _open_stable_regular_file_at(
                parent_fd,
                path.name,
                label=f"existing file {path}",
                ambient_identities=ambient_identities,
            )
            try:
                same_content = _read_descriptor_bytes(existing_descriptor, str(path)) == content
                _revalidate_regular_file_at(
                    parent_fd,
                    path.name,
                    existing_descriptor,
                    opened,
                    label=f"existing file {path}",
                    ambient_identities=ambient_identities,
                )
                if same_content and stat.S_IMODE(opened.st_mode) == mode:
                    return
                staged_descriptor = _create_unnameable_temporary_file_at(
                    parent_fd, str(path)
                )
                _write_descriptor_exact(staged_descriptor, content, mode, str(path))
                _replace_with_staged_file_at(
                    parent_fd=parent_fd,
                    target_name=path.name,
                    target_descriptor=existing_descriptor,
                    target_initial=opened,
                    staged_descriptor=staged_descriptor,
                    label=f"existing file {path}",
                    ambient_identities=ambient_identities,
                )
                os.fsync(parent_fd)
                os.close(staged_descriptor)
                staged_descriptor = None
                return
            finally:
                os.close(existing_descriptor)
                existing_descriptor = None
        else:
            staged_descriptor = _create_unnameable_temporary_file_at(
                parent_fd, str(path)
            )
            _write_descriptor_exact(staged_descriptor, content, mode, str(path))
            _publish_unnameable_file_at(
                parent_fd, staged_descriptor, path.name, str(path)
            )
        os.fsync(parent_fd)
    except IncarnationHomeError:
        raise
    except OSError as exc:
        raise IncarnationHomeError(f"cannot safely publish file: {path}") from exc
    finally:
        if existing_descriptor is not None:
            os.close(existing_descriptor)
        if staged_descriptor is not None:
            os.close(staged_descriptor)
        os.close(parent_fd)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _proc_stat_fields(pid: int) -> list[str]:
    if pid <= 0:
        raise IncarnationHomeError(f"process id must be positive: {pid}")
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise IncarnationHomeError(f"cannot read process identity: {pid}") from exc
    closing = raw.rfind(")")
    if closing < 0:
        raise IncarnationHomeError(f"process stat is malformed: {pid}")
    fields = raw[closing + 2 :].split()
    if len(fields) < 20:
        raise IncarnationHomeError(f"process stat is incomplete: {pid}")
    return fields


def _proc_start_ticks(pid: int) -> int:
    try:
        return int(_proc_stat_fields(pid)[19])
    except ValueError as exc:
        raise IncarnationHomeError(f"process start time is malformed: {pid}") from exc


def _proc_boot_id() -> str:
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
            encoding="ascii"
        ).strip()
    except (OSError, UnicodeError) as exc:
        raise IncarnationHomeError("cannot read kernel boot identity") from exc
    if not BOOT_ID_PATTERN.fullmatch(boot_id):
        raise IncarnationHomeError("kernel boot identity is malformed")
    return boot_id


def _proc_identity_is_live(pid: int, start_ticks: int) -> bool:
    try:
        fields = _proc_stat_fields(pid)
        return fields[0] != "Z" and int(fields[19]) == start_ticks
    except (IncarnationHomeError, ValueError):
        return False


def _proc_identity_state(pid: int, start_ticks: int) -> str:
    """Classify one recorded process without confusing exit and PID reuse."""

    try:
        fields = _proc_stat_fields(pid)
    except IncarnationHomeError:
        # A process can disappear between the stat read and this check.  Only
        # a genuinely absent /proc entry is an already-gone identity; any
        # other read failure remains fail-closed.
        if not Path(f"/proc/{pid}").exists():
            return "gone"
        raise
    if fields[0] == "Z":
        return "gone"
    try:
        observed_start_ticks = int(fields[19])
    except ValueError as exc:
        raise IncarnationHomeError(
            f"process start time is malformed: {pid}"
        ) from exc
    if observed_start_ticks != start_ticks:
        return "drifted"
    return "live"


def _wait_for_exact_process_exit(pid: int, start_ticks: int) -> str:
    """Wait for one exact recorded process to leave the live state."""

    state = _proc_identity_state(pid, start_ticks)
    for _ in range(40):
        if state != "live":
            return state
        time.sleep(0.25)
        state = _proc_identity_state(pid, start_ticks)
    return state


def _wait_for_natural_pair_exit(
    *,
    holder_pid: int,
    holder_start_ticks: int,
    kitty_pid: int,
    kitty_start_ticks: int,
    holder_state: str,
    kitty_state: str,
) -> tuple[str, str]:
    """Give a surviving exact identity time to finish natural shutdown."""

    for _ in range(40):
        if holder_state == "gone" and kitty_state == "gone":
            return holder_state, kitty_state
        if holder_state == "drifted" or kitty_state == "drifted":
            return holder_state, kitty_state
        time.sleep(0.25)
        kitty_state = _proc_identity_state(kitty_pid, kitty_start_ticks)
        holder_state = _proc_identity_state(holder_pid, holder_start_ticks)
    return holder_state, kitty_state


def _proc_parent_pid(pid: int) -> int:
    try:
        return int(_proc_stat_fields(pid)[1])
    except ValueError as exc:
        raise IncarnationHomeError(f"process parent is malformed: {pid}") from exc


def _proc_comm(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise IncarnationHomeError(f"cannot read process name: {pid}") from exc


def _proc_argv(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError as exc:
        raise IncarnationHomeError(f"cannot read process argv: {pid}") from exc
    return [os.fsdecode(item) for item in raw.split(b"\0") if item]


def _proc_exe_digest(pid: int) -> str:
    digest = hashlib.sha256()
    try:
        with Path(f"/proc/{pid}/exe").open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise IncarnationHomeError(
            f"cannot read process executable identity: {pid}"
        ) from exc
    return "sha256:" + digest.hexdigest()


def _proc_environ(pid: int) -> dict[str, str]:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError as exc:
        raise IncarnationHomeError(f"cannot read process environment: {pid}") from exc
    environment: dict[str, str] = {}
    for item in raw.split(b"\0"):
        key, separator, value = item.partition(b"=")
        if not separator:
            continue
        environment[os.fsdecode(key)] = os.fsdecode(value)
    return environment


def _proc_children(pid: int) -> list[int]:
    try:
        raw = Path(f"/proc/{pid}/task/{pid}/children").read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise IncarnationHomeError(f"cannot read process children: {pid}") from exc
    try:
        return [int(value) for value in raw.split()]
    except ValueError as exc:
        raise IncarnationHomeError(f"process children are malformed: {pid}") from exc


def _safe_projection_string(value: object, label: str) -> str:
    """Keep human-readable status fields from becoming credential sinks."""

    if not isinstance(value, str):
        raise IncarnationHomeError(f"safe status field is not text: {label}")
    if "\x00" in value:
        raise IncarnationHomeError(f"safe status field contains NUL: {label}")

    credential_pattern = re.compile(
        r"(?i)(?<![A-Za-z0-9_-])"
        r"(?P<key_quote>['\"]?)"
        rf"(?P<key>{CREDENTIAL_KEY_PATTERN})"
        r"(?P=key_quote)(?![A-Za-z0-9_-])"
        r"(?P<separator>\s*[:=]\s*)"
        r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^,;}\]\r\n]+)",
    )
    escaped_credential_pattern = re.compile(
        r"(?i)(?<![A-Za-z0-9_-])"
        r"(?P<key_escape>\\+)(?P<key_quote>['\"])"
        rf"(?P<key>{CREDENTIAL_KEY_PATTERN})"
        r"(?P=key_escape)(?P=key_quote)(?![A-Za-z0-9_-])"
        r"(?P<separator>\s*[:=]\s*)"
        r"(?P<value>"
        r"(?P<value_escape>\\+)(?P<value_quote>['\"])(?:\\.|[^\\])*?"
        r"(?P=value_escape)(?P=value_quote)"
        r"|[^,;}\]\r\n]+)",
    )

    def redact(match: re.Match[str]) -> str:
        raw_value = match.group("value")
        escaped_quoted = re.fullmatch(
            r"(\\+)(['\"])(.*?)(\\+)\2", raw_value, flags=re.DOTALL
        )
        if escaped_quoted is not None:
            raw_value = (
                f"{escaped_quoted.group(1)}{escaped_quoted.group(2)}"
                f"<redacted>{escaped_quoted.group(4)}{escaped_quoted.group(2)}"
            )
        elif raw_value[:1] in {'"', "'"} and raw_value[-1:] == raw_value[:1]:
            raw_value = f"{raw_value[0]}<redacted>{raw_value[0]}"
        else:
            raw_value = "<redacted>"
        return (
            f"{match.groupdict().get('key_escape') or ''}"
            f"{match.group('key_quote')}{match.group('key')}"
            f"{match.groupdict().get('key_escape') or ''}"
            f"{match.group('key_quote')}{match.group('separator')}{raw_value}"
        )

    value = escaped_credential_pattern.sub(redact, value)
    return credential_pattern.sub(redact, value)


def _safe_projection_value(value: object, label: str) -> object:
    """Sanitize every scalar in a validated owner-visible projection."""

    if isinstance(value, str):
        return _safe_projection_string(value, label)
    if isinstance(value, dict):
        return {
            key: _safe_projection_value(nested, f"{label}.{key}")
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [
            _safe_projection_value(nested, f"{label}[{index}]")
            for index, nested in enumerate(value)
        ]
    return value


def _safe_terminal_binding_projection(
    binding: dict[str, object],
) -> dict[str, object]:
    projection = _safe_projection_value(binding, "terminal binding")
    if not isinstance(projection, dict):
        raise IncarnationHomeError("terminal binding projection is not an object")
    _assert_safe_projection(projection)
    return projection


def _assert_safe_projection(value: object) -> None:
    """Defence-in-depth check for every owner-visible Kitty projection."""

    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).casefold().replace("-", "_")
            if (
                normalized_key in SAFE_PROJECTION_FORBIDDEN_KEYS
                or CREDENTIAL_KEY_RE.fullmatch(str(key)) is not None
            ):
                raise IncarnationHomeError(
                    f"unsafe field entered terminal status projection: {key}"
                )
            _assert_safe_projection(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_safe_projection(nested)


def _safe_terminal_title(value: object) -> str:
    """Return the exact redaction-safe title used for Kitty and the binding."""

    title = _safe_projection_string(value, "terminal title")
    if not title.strip():
        raise IncarnationHomeError("visible launch terminal title must not be empty")
    return title


def _binding_ref(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IncarnationHomeError(f"terminal binding {label} is missing")
    if any(character in value for character in "\x00\r\n"):
        raise IncarnationHomeError(f"terminal binding {label} contains control text")
    return _safe_projection_string(value, label)


def _positive_int(value: object, *, minimum: int = 1) -> bool:
    return type(value) is int and value >= minimum


def _safe_source_receipt_path(path: Path) -> str:
    resolved = str(path.resolve())
    if _safe_projection_string(resolved, "source receipt path") != resolved:
        raise IncarnationHomeError(
            "source receipt path contains credential-shaped text"
        )
    return resolved


def _socket_path(address: object, label: str = "control socket") -> Path:
    if not isinstance(address, str) or not address.startswith("unix:"):
        raise IncarnationHomeError(f"{label} must use a unix: address")
    path = Path(address.removeprefix("unix:"))
    if (
        not path.is_absolute()
        or path.is_symlink()
        or not path.parent.is_absolute()
        or len(str(path)) > CONTROL_SOCKET_MAX_LENGTH
    ):
        raise IncarnationHomeError(f"{label} path is not an absolute private socket")
    if _safe_projection_string(os.fspath(path), label) != os.fspath(path):
        raise IncarnationHomeError(f"{label} path contains credential-shaped text")
    return path


def _validate_socket_parent(path: Path, *, create: bool = False) -> Path:
    return _validate_owner_private_parent(path, "control socket", create=create)


def _validate_owner_private_parent(
    path: Path, label: str, *, create: bool = False
) -> Path:
    """Require a path's parent directory to be private to this owner."""

    parent = path.parent
    if create and not parent.exists():
        parent.mkdir(mode=CONTROL_SOCKET_PARENT_MODE, parents=False)
    if parent.is_symlink() or not parent.is_dir():
        raise IncarnationHomeError(f"{label} parent is not a directory: {parent}")
    try:
        parent_stat = parent.stat()
    except OSError as exc:
        raise IncarnationHomeError(
            f"{label} parent cannot be inspected: {parent}"
        ) from exc
    if parent_stat.st_uid != os.getuid() or stat.S_IMODE(parent_stat.st_mode) & 0o077:
        raise IncarnationHomeError(
            f"{label} parent is not private to the owner: {parent}"
        )
    return parent


def _secure_control_socket(
    address: str,
    *,
    require_exists: bool = True,
    harden: bool = False,
    expected_device: int | None = None,
    expected_inode: int | None = None,
) -> dict[str, object]:
    path = _socket_path(address)
    _validate_socket_parent(path)
    if not path.exists():
        if require_exists:
            raise IncarnationHomeError(f"control socket does not exist: {path}")
        return {
            "address": address,
            "path": str(path),
            "mode": None,
            "device": None,
            "inode": None,
        }
    if path.is_symlink():
        raise IncarnationHomeError(f"control socket may not be a symlink: {path}")
    try:
        observed = path.stat()
    except OSError as exc:
        raise IncarnationHomeError(f"control socket cannot be inspected: {path}") from exc
    if not stat.S_ISSOCK(observed.st_mode) or observed.st_uid != os.getuid():
        raise IncarnationHomeError(f"control socket is not an owner socket: {path}")
    if expected_device is not None and observed.st_dev != expected_device:
        raise IncarnationHomeError(f"control socket device identity drifted: {path}")
    if expected_inode is not None and observed.st_ino != expected_inode:
        raise IncarnationHomeError(f"control socket inode identity drifted: {path}")
    if harden:
        try:
            os.chmod(path, CONTROL_SOCKET_MODE)
            observed = path.stat()
        except OSError as exc:
            raise IncarnationHomeError(
                f"control socket permissions cannot be hardened: {path}"
            ) from exc
    mode = stat.S_IMODE(observed.st_mode)
    if mode & 0o077:
        raise IncarnationHomeError(f"control socket permissions are not private: {path}")
    return {
        "address": address,
        "path": str(path),
        "mode": mode,
        "device": observed.st_dev,
        "inode": observed.st_ino,
    }


def _allocate_control_socket() -> str:
    runtime_dir_value = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    runtime_dir = Path(runtime_dir_value)
    if runtime_dir.is_symlink() or not runtime_dir.is_dir():
        raise IncarnationHomeError("XDG runtime directory is not a real directory")
    root = runtime_dir / CONTROL_SOCKET_ROOT_NAME
    if not root.exists():
        root.mkdir(mode=CONTROL_SOCKET_PARENT_MODE)
    _validate_socket_parent(root)
    for _ in range(32):
        path = root / f"kitty-{secrets.token_hex(16)}.sock"
        if not path.exists() and not path.is_symlink():
            return f"unix:{path}"
    raise IncarnationHomeError("could not allocate a unique Kitty control socket")


def _holder_tty(pid: int) -> str:
    try:
        target = os.readlink(f"/proc/{pid}/fd/0")
    except OSError as exc:
        raise IncarnationHomeError(f"holder tty cannot be observed: {pid}") from exc
    if not re.fullmatch(r"/dev/(?:pts/[0-9]+|tty[0-9]+)", target):
        raise IncarnationHomeError(f"holder stdin is not a terminal: {target}")
    return target


def _validate_binding_context(context: dict[str, Any]) -> dict[str, str]:
    required = TERMINAL_BINDING_CONTEXT_FIELDS
    values = {key: _binding_ref(context.get(key), key) for key in required}
    for key in ("schema_version",) + HOLDER_BINDING_CONTEXT_FIELDS:
        if key in context:
            values[key] = _binding_ref(context[key], key)
    runtime_state_root = Path(values["runtime_state_root"])
    if (
        not runtime_state_root.is_absolute()
        or runtime_state_root.is_symlink()
        or not runtime_state_root.is_dir()
    ):
        raise IncarnationHomeError("terminal runtime state root is not a real directory")
    closeout_route = Path(values["closeout_route"])
    if not closeout_route.is_absolute():
        raise IncarnationHomeError("terminal closeout route must be absolute")
    return values


def _validate_holder_binding_context(context: dict[str, Any]) -> dict[str, str]:
    """Require the typed holder/task/run coordinates used for home identity."""

    values = _validate_binding_context(context)
    if values.get("schema_version") != HOLDER_BINDING_CONTEXT_SCHEMA_VERSION:
        raise IncarnationHomeError(
            "holder binding context schema is missing or unsupported"
        )
    for key in HOLDER_BINDING_CONTEXT_FIELDS:
        if key not in values:
            raise IncarnationHomeError(f"holder binding context {key} is missing")
    return values


def _holder_binding_context_input(
    value: Path | dict[str, Any],
) -> tuple[dict[str, str], bytes, str]:
    if isinstance(value, Path):
        context_document, raw = _load_json_snapshot(value, "holder binding context")
    elif isinstance(value, dict):
        context_document = value
        raw = canonical_bytes(value)
    else:
        raise IncarnationHomeError("holder binding context input is invalid")
    context = _validate_holder_binding_context(context_document)
    return context, raw, sha256_bytes(raw)


def _load_binding_context(path: Path) -> dict[str, str]:
    context = _load_json(path, "terminal binding context")
    return _validate_binding_context(context)


def _load_binding_context_snapshot(raw: bytes) -> dict[str, str]:
    return _validate_binding_context(
        _decode_json_snapshot(raw, "terminal binding context snapshot")
    )


def _load_holder_binding_context_snapshot(raw: bytes) -> dict[str, str]:
    return _validate_holder_binding_context(
        _decode_json_snapshot(raw, "holder binding context snapshot")
    )


def _load_holder_loss_reentry(
    path: Path,
    *,
    expected_context: dict[str, str] | None = None,
    expected_holder: tuple[int, int] | None = None,
    expected_terminal: tuple[int, int] | None = None,
) -> tuple[dict[str, Any], bytes, str]:
    """Load the exact task-local evidence that admitted a replacement holder.

    A holder-loss reentry receipt is not itself a canonical visible-holder
    receipt.  It is an immutable admission input for the explicit rebind
    operation below.  Keep that distinction visible and require every
    identity/path/digest relation before a canonical receipt can be derived.
    """

    receipt, raw = _load_json_snapshot(path, "holder-loss reentry receipt")
    if receipt.get("schema_version") != HOLDER_LOSS_REENTRY_SCHEMA_VERSION:
        raise IncarnationHomeError("unsupported holder-loss reentry receipt schema")
    expected_keys = {
        "schema_version",
        "goal_id",
        "actor_id",
        "role",
        "session_id",
        "workspace",
        "duty_ref",
        "duty_sha256",
        "failure_event_ref",
        "failure_event_sha256",
        "prior_holder",
        "current_holder",
        "terminal",
        "continuity",
        "claim_limit",
    }
    if set(receipt) != expected_keys:
        raise IncarnationHomeError("holder-loss reentry receipt fields are not exact")
    for key in ("goal_id", "actor_id", "role", "session_id", "claim_limit"):
        _binding_ref(receipt.get(key), f"holder-loss reentry {key}")
    workspace = _binding_ref(receipt.get("workspace"), "holder-loss reentry workspace")
    if not Path(workspace).is_absolute():
        raise IncarnationHomeError("holder-loss reentry workspace must be absolute")
    if expected_context is not None:
        if receipt["goal_id"] != expected_context["goal_ref"]:
            raise IncarnationHomeError("holder-loss reentry Goal identity disagrees with context")
        if receipt["actor_id"] != expected_context["actor_ref"]:
            raise IncarnationHomeError("holder-loss reentry actor identity disagrees with context")
        if receipt["session_id"] != expected_context["session_ref"]:
            raise IncarnationHomeError("holder-loss reentry session identity disagrees with context")
        context_workspace = expected_context.get("workspace")
        if context_workspace is not None and workspace != context_workspace:
            raise IncarnationHomeError("holder-loss reentry workspace disagrees with context")
    for ref_key, digest_key, label in (
        ("duty_ref", "duty_sha256", "holder-loss duty"),
        ("failure_event_ref", "failure_event_sha256", "holder-loss failure event"),
    ):
        reference = _regular_file(Path(receipt[ref_key]), label)
        digest = receipt[digest_key]
        if not isinstance(digest, str) or SHA256_DIGEST_PATTERN.fullmatch(digest) is None:
            raise IncarnationHomeError(f"{label} digest is invalid")
        if sha256_bytes(reference.read_bytes()) != digest:
            raise IncarnationHomeError(f"{label} digest has drifted")
    prior_holder = receipt["prior_holder"]
    current_holder = receipt["current_holder"]
    terminal = receipt["terminal"]
    continuity = receipt["continuity"]
    if (
        not isinstance(prior_holder, dict)
        or set(prior_holder) != {"pid", "start_ticks", "state"}
        or not _positive_int(prior_holder.get("pid"))
        or not _positive_int(prior_holder.get("start_ticks"))
        or prior_holder.get("state") != "lost_before_return"
    ):
        raise IncarnationHomeError("holder-loss prior-holder evidence is invalid")
    if (
        not isinstance(current_holder, dict)
        or set(current_holder) != {"pid", "start_ticks"}
        or not _positive_int(current_holder.get("pid"))
        or not _positive_int(current_holder.get("start_ticks"))
    ):
        raise IncarnationHomeError("holder-loss current-holder evidence is invalid")
    if expected_holder is not None and (
        current_holder["pid"] != expected_holder[0]
        or current_holder["start_ticks"] != expected_holder[1]
    ):
        raise IncarnationHomeError("holder-loss current-holder identity disagrees")
    if (
        not isinstance(terminal, dict)
        or set(terminal) != {"pid", "start_ticks", "visible", "operator_interactive"}
        or not _positive_int(terminal.get("pid"))
        or not _positive_int(terminal.get("start_ticks"))
        or terminal.get("visible") is not True
        or terminal.get("operator_interactive") is not True
    ):
        raise IncarnationHomeError("holder-loss terminal evidence is invalid")
    if expected_terminal is not None and (
        terminal["pid"] != expected_terminal[0]
        or terminal["start_ticks"] != expected_terminal[1]
    ):
        raise IncarnationHomeError("holder-loss terminal identity disagrees")
    if (
        not isinstance(continuity, dict)
        or continuity
        != {
            "same_actor": True,
            "same_session": True,
            "replacement_physical_incarnation": True,
        }
    ):
        raise IncarnationHomeError("holder-loss continuity evidence is invalid")
    return receipt, raw, sha256_bytes(raw)


def _load_rebind_manifest(
    path: Path,
    *,
    runtime_state_root: Path,
    binding_context: dict[str, str] | None = None,
    binding_context_digest: str | None = None,
) -> tuple[dict[str, Any], bytes, str]:
    """Load and fully revalidate the manifest admitted by a replacement."""

    if not path.resolve().is_relative_to(runtime_state_root.resolve()):
        raise IncarnationHomeError(
            "replacement incarnation manifest is outside the bound runtime state root"
        )
    return _load_manifest_snapshot(
        path,
        binding_context=binding_context,
        binding_context_digest=binding_context_digest,
        require_holder_binding=binding_context is not None,
    )


def _validate_replacement_reentry_binding(
    value: object,
    *,
    holder: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IncarnationHomeError("replacement reentry binding is not an object")
    required = {
        "receipt_ref",
        "receipt_sha256",
        "duty_ref",
        "duty_sha256",
        "failure_event_ref",
        "failure_event_sha256",
        "goal_id",
        "actor_id",
        "session_id",
        "holder_pid",
        "holder_start_ticks",
    }
    if set(value) != required:
        raise IncarnationHomeError("replacement reentry binding fields are not exact")
    reference = _regular_file(Path(value["receipt_ref"]), "replacement reentry receipt")
    digest = value["receipt_sha256"]
    if not isinstance(digest, str) or SHA256_DIGEST_PATTERN.fullmatch(digest) is None:
        raise IncarnationHomeError("replacement reentry receipt digest is invalid")
    if sha256_bytes(reference.read_bytes()) != digest:
        raise IncarnationHomeError("replacement reentry receipt digest has drifted")
    reentry, _raw, _digest = _load_holder_loss_reentry(
        reference,
        expected_holder=(holder.get("pid"), holder.get("start_ticks"))
        if _positive_int(holder.get("pid")) and _positive_int(holder.get("start_ticks"))
        else None,
    )
    for key in ("duty_ref", "duty_sha256", "failure_event_ref", "failure_event_sha256"):
        if value[key] != reentry[key]:
            raise IncarnationHomeError(
                f"replacement reentry binding {key} disagrees with source receipt"
            )
    for key in ("goal_id", "actor_id", "session_id"):
        if value[key] != reentry[key]:
            raise IncarnationHomeError(
                f"replacement reentry binding {key} disagrees with source receipt"
            )
    if value["holder_pid"] != reentry["current_holder"]["pid"] or value[
        "holder_start_ticks"
    ] != reentry["current_holder"]["start_ticks"]:
        raise IncarnationHomeError("replacement reentry holder identity disagrees")
    return value


def _revalidate_bound_holder_identity(holder: dict[str, object]) -> None:
    """Recheck the bound holder identity at the directed-input boundary."""

    holder_pid = holder.get("pid")
    holder_start_ticks = holder.get("start_ticks")
    if not isinstance(holder_pid, int) or not isinstance(holder_start_ticks, int):
        raise IncarnationHomeError("directed input holder identity is invalid")
    if _proc_identity_state(holder_pid, holder_start_ticks) != "live":
        raise IncarnationHomeError(
            "directed input holder process identity is no longer live"
        )
    holder_argv_digest = holder.get("argv_digest")
    if not isinstance(holder_argv_digest, str) or not SHA256_DIGEST_PATTERN.fullmatch(
        holder_argv_digest
    ):
        raise IncarnationHomeError("directed input holder argv identity is invalid")
    if sha256_bytes(canonical_bytes(_proc_argv(holder_pid))) != holder_argv_digest:
        raise IncarnationHomeError("directed input holder argv identity has drifted")
    holder_exe_digest = holder.get("exe_digest")
    if not isinstance(holder_exe_digest, str) or not SHA256_DIGEST_PATTERN.fullmatch(
        holder_exe_digest
    ):
        raise IncarnationHomeError(
            "directed input holder executable identity is invalid"
        )
    if _proc_exe_digest(holder_pid) != holder_exe_digest:
        raise IncarnationHomeError(
            "directed input holder executable identity has drifted"
        )


def _terminal_binding(
    *,
    context: dict[str, str],
    control_socket: str,
    terminal_title: str,
    window_id: str,
    tty: str,
    holder_pid: int,
    holder_start_ticks: int,
    holder_argv_digest: str | None = None,
    holder_exe_digest: str | None = None,
    terminal_pid: int,
    terminal_start_ticks: int,
    source_receipt: Path | None = None,
    source_receipt_digest: str | None = None,
    harden_socket: bool = True,
) -> dict[str, object]:
    socket_record = _secure_control_socket(
        control_socket, harden=harden_socket
    )
    binding: dict[str, object] = {
        "schema_version": TERMINAL_BINDING_SCHEMA_VERSION,
        "boot_id": _proc_boot_id(),
        "goal_ref": context["goal_ref"],
        "actor_ref": context["actor_ref"],
        "incarnation_ref": context["incarnation_ref"],
        "session_ref": context["session_ref"],
        "runtime_state_root": context["runtime_state_root"],
        "closeout_route": context["closeout_route"],
        "holder": {
            "pid": holder_pid,
            "start_ticks": holder_start_ticks,
        },
        "terminal": {
            "pid": terminal_pid,
            "start_ticks": terminal_start_ticks,
            "window_id": window_id,
            "tty": tty,
            "title": _safe_projection_string(terminal_title, "terminal title"),
            "control_socket": socket_record,
        },
        "remote_control": "socket-only",
        "dedicated": True,
    }
    holder_record = binding["holder"]
    assert isinstance(holder_record, dict)
    if holder_argv_digest is not None:
        if not SHA256_DIGEST_PATTERN.fullmatch(holder_argv_digest):
            raise IncarnationHomeError("terminal binding holder argv digest is invalid")
        holder_record["argv_digest"] = holder_argv_digest
    if holder_exe_digest is not None:
        if not SHA256_DIGEST_PATTERN.fullmatch(holder_exe_digest):
            raise IncarnationHomeError("terminal binding holder executable digest is invalid")
        holder_record["exe_digest"] = holder_exe_digest
    if source_receipt is not None:
        binding["source_receipt"] = {
            "path": _safe_source_receipt_path(source_receipt),
            "sha256": source_receipt_digest
            or sha256_bytes(source_receipt.read_bytes()),
        }
    _assert_safe_projection(binding)
    return binding


def _validate_receipt_binding_consistency(
    receipt: dict[str, Any], binding: dict[str, object]
) -> None:
    """Require the embedded binding and top-level receipt to name one target."""

    holder = receipt.get("holder")
    terminal = receipt.get("terminal")
    binding_holder = binding.get("holder")
    binding_terminal = binding.get("terminal")
    if not all(
        isinstance(value, dict)
        for value in (holder, terminal, binding_holder, binding_terminal)
    ):
        raise IncarnationHomeError(
            "embedded terminal binding cannot be cross-checked against receipt identities"
        )
    assert isinstance(holder, dict)
    assert isinstance(terminal, dict)
    assert isinstance(binding_holder, dict)
    assert isinstance(binding_terminal, dict)
    if binding.get("boot_id") != receipt.get("boot_id"):
        raise IncarnationHomeError(
            "embedded terminal binding boot identity disagrees with top-level receipt"
        )
    if any(
        binding_holder.get(key) != holder.get(key)
        for key in ("pid", "start_ticks")
    ):
        raise IncarnationHomeError(
            "embedded terminal binding holder identity disagrees with top-level holder"
        )
    if (
        "argv_digest" in binding_holder
        and binding_holder.get("argv_digest") != holder.get("argv_digest")
    ):
        raise IncarnationHomeError(
            "embedded terminal binding holder argv identity disagrees with top-level holder"
        )
    if (
        "exe_digest" in binding_holder
        and binding_holder.get("exe_digest") != holder.get("exe_digest")
    ):
        raise IncarnationHomeError(
            "embedded terminal binding holder executable identity disagrees with top-level holder"
        )
    if any(
        binding_terminal.get(key) != terminal.get(key)
        for key in (
            "pid",
            "start_ticks",
            "window_id",
            "tty",
            "title",
            "control_socket",
        )
    ):
        raise IncarnationHomeError(
            "embedded terminal binding terminal identity or socket disagrees with top-level terminal"
        )


def _validate_terminal_binding_shape(binding: object) -> dict[str, object]:
    if not isinstance(binding, dict):
        raise IncarnationHomeError("terminal binding is not an object")
    binding = dict(binding)
    unexpected = set(binding) - {
        "schema_version",
        "boot_id",
        "goal_ref",
        "actor_ref",
        "incarnation_ref",
        "session_ref",
        "runtime_state_root",
        "closeout_route",
        "holder",
        "terminal",
        "remote_control",
        "dedicated",
        "source_receipt",
    }
    if unexpected:
        raise IncarnationHomeError(
            f"terminal binding contains unexpected fields: {sorted(unexpected)}"
        )
    if binding.get("schema_version") != TERMINAL_BINDING_SCHEMA_VERSION:
        raise IncarnationHomeError("unsupported terminal binding schema")
    boot_id = binding.get("boot_id")
    if not isinstance(boot_id, str) or not BOOT_ID_PATTERN.fullmatch(boot_id):
        raise IncarnationHomeError("terminal binding boot identity is invalid")
    for key in (
        "goal_ref",
        "actor_ref",
        "incarnation_ref",
        "session_ref",
        "runtime_state_root",
        "closeout_route",
    ):
        binding[key] = _binding_ref(binding.get(key), key)
    state_root = Path(str(binding["runtime_state_root"]))
    if not state_root.is_absolute() or state_root.is_symlink():
        raise IncarnationHomeError("terminal binding runtime state root is invalid")
    closeout_route = Path(str(binding["closeout_route"]))
    if not closeout_route.is_absolute():
        raise IncarnationHomeError("terminal binding closeout route is invalid")
    if binding.get("remote_control") != "socket-only" or binding.get("dedicated") is not True:
        raise IncarnationHomeError("terminal binding control posture is invalid")
    holder = binding.get("holder")
    terminal = binding.get("terminal")
    if not isinstance(holder, dict) or not isinstance(terminal, dict):
        raise IncarnationHomeError("terminal binding process records are missing")
    if set(holder) - {"pid", "start_ticks", "argv_digest", "exe_digest"}:
        raise IncarnationHomeError("terminal binding holder has unexpected fields")
    if set(terminal) - {
        "pid",
        "start_ticks",
        "window_id",
        "tty",
        "title",
        "control_socket",
    }:
        raise IncarnationHomeError("terminal binding terminal has unexpected fields")
    if not all(
        _positive_int(holder.get(key))
        for key in ("pid", "start_ticks")
    ):
        raise IncarnationHomeError("terminal binding holder identity is invalid")
    holder_argv_digest = holder.get("argv_digest")
    if holder_argv_digest is not None and (
        not isinstance(holder_argv_digest, str)
        or SHA256_DIGEST_PATTERN.fullmatch(holder_argv_digest) is None
    ):
        raise IncarnationHomeError("terminal binding holder argv identity is invalid")
    holder_exe_digest = holder.get("exe_digest")
    if holder_exe_digest is not None and (
        not isinstance(holder_exe_digest, str)
        or SHA256_DIGEST_PATTERN.fullmatch(holder_exe_digest) is None
    ):
        raise IncarnationHomeError(
            "terminal binding holder executable identity is invalid"
        )
    if not all(
        _positive_int(terminal.get(key))
        for key in ("pid", "start_ticks")
    ):
        raise IncarnationHomeError("terminal binding Kitty identity is invalid")
    if not isinstance(terminal.get("window_id"), str) or not re.fullmatch(
        r"[1-9][0-9]*", terminal["window_id"]
    ):
        raise IncarnationHomeError("terminal binding window identity is invalid")
    if not isinstance(terminal.get("tty"), str) or re.fullmatch(
        r"/dev/(?:pts/[0-9]+|tty[0-9]+)", terminal["tty"]
    ) is None:
        raise IncarnationHomeError("terminal binding tty is invalid")
    if not isinstance(terminal.get("title"), str):
        raise IncarnationHomeError("terminal binding title is invalid")
    socket_record = terminal.get("control_socket")
    if not isinstance(socket_record, dict):
        raise IncarnationHomeError("terminal binding socket record is missing")
    if set(socket_record) - {"address", "path", "mode", "device", "inode"}:
        raise IncarnationHomeError("terminal binding socket has unexpected fields")
    address = socket_record.get("address")
    path = _socket_path(address)
    if socket_record.get("path") != str(path):
        raise IncarnationHomeError("terminal binding socket path drifted")
    mode = socket_record.get("mode")
    if type(mode) is not int or not 0 <= mode <= 0o700 or mode & 0o077:
        raise IncarnationHomeError("terminal binding socket mode is not private")
    if not all(
        _positive_int(socket_record.get(key))
        for key in ("device", "inode")
    ):
        raise IncarnationHomeError("terminal binding socket identity is invalid")
    source_receipt = binding.get("source_receipt")
    if source_receipt is not None:
        if not isinstance(source_receipt, dict) or set(source_receipt) != {
            "path",
            "sha256",
        }:
            raise IncarnationHomeError("terminal binding source receipt is invalid")
        source_receipt_path = source_receipt.get("path")
        source_receipt_digest = source_receipt.get("sha256")
        if (
            not isinstance(source_receipt_path, str)
            or not Path(source_receipt_path).is_absolute()
            or _safe_projection_string(source_receipt_path, "source receipt path")
            != source_receipt_path
            or not isinstance(source_receipt_digest, str)
            or SHA256_DIGEST_PATTERN.fullmatch(source_receipt_digest) is None
        ):
            raise IncarnationHomeError("terminal binding source receipt is invalid")
        binding["source_receipt"] = {
            "path": source_receipt_path,
            "sha256": source_receipt_digest,
        }
    return _safe_terminal_binding_projection(binding)


def _kitty_ls(
    *,
    kitty_executable: str,
    control_socket: str,
    window_id: str,
    expected_device: int | None = None,
    expected_inode: int | None = None,
) -> list[dict[str, object]]:
    """Query Kitty while never returning its raw, environment-bearing payload."""

    _secure_control_socket(
        control_socket,
        harden=False,
        expected_device=expected_device,
        expected_inode=expected_inode,
    )
    try:
        completed = subprocess.run(
            [
                kitty_executable,
                "@",
                "--to",
                control_socket,
                "ls",
                "--output-format",
                "json",
                "--all-env-vars=no",
                "--match",
                f"id:{window_id}",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IncarnationHomeError("Kitty read-only status query failed") from exc
    if completed.returncode != 0:
        raise IncarnationHomeError("Kitty read-only status query returned an error")
    try:
        payload = json.loads(completed.stdout)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise IncarnationHomeError("Kitty status payload was not valid JSON") from exc
    if not isinstance(payload, list):
        raise IncarnationHomeError("Kitty status payload was not a window list")
    matches: list[dict[str, object]] = []
    for os_window in payload:
        if not isinstance(os_window, dict):
            continue
        tabs = os_window.get("tabs")
        if not isinstance(tabs, list):
            continue
        for tab in tabs:
            if not isinstance(tab, dict) or not isinstance(tab.get("windows"), list):
                continue
            for window in tab["windows"]:
                if not isinstance(window, dict):
                    continue
                if str(window.get("id")) != window_id:
                    continue
                foreground: list[dict[str, object]] = []
                raw_foreground = window.get("foreground_processes")
                if isinstance(raw_foreground, list):
                    for process in raw_foreground:
                        if not isinstance(process, dict):
                            continue
                        pid = process.get("pid")
                        if type(pid) is not int or pid <= 0:
                            continue
                        try:
                            comm = _proc_comm(pid)
                        except IncarnationHomeError:
                            comm = "unknown"
                        process_projection: dict[str, object] = {
                            "pid": pid,
                            "comm": _safe_projection_string(comm, "foreground comm"),
                        }
                        if isinstance(process.get("cwd"), str):
                            process_projection["cwd"] = _safe_projection_string(
                                process["cwd"], "foreground cwd"
                            )
                        foreground.append(process_projection)
                safe_window: dict[str, object] = {
                    "id": window_id,
                    "title": _safe_projection_string(
                        window.get("title", ""), "window title"
                    ),
                    "cwd": _safe_projection_string(window.get("cwd", ""), "window cwd"),
                    "pid": window.get("pid")
                    if type(window.get("pid")) is int and window.get("pid") > 0
                    else None,
                    "is_active": window.get("is_active") is True,
                    "is_focused": window.get("is_focused") is True,
                    "needs_attention": window.get("needs_attention") is True,
                    "in_alternate_screen": window.get("in_alternate_screen") is True,
                    "foreground_processes": foreground,
                    "tab": {
                        "id": tab.get("id")
                        if type(tab.get("id")) is int and tab.get("id") > 0
                        else None,
                        "is_active": tab.get("is_active") is True,
                        "is_focused": tab.get("is_focused") is True,
                    },
                    "os_window": {
                        "id": os_window.get("id")
                        if type(os_window.get("id")) is int
                        and os_window.get("id") > 0
                        else None,
                        "is_active": os_window.get("is_active") is True,
                        "is_focused": os_window.get("is_focused") is True,
                    },
                }
                matches.append(safe_window)
    if len(matches) > 1:
        raise IncarnationHomeError("Kitty control socket matched multiple bound windows")
    _assert_safe_projection(matches)
    return matches


def _descends_from(pid: int, ancestor_pid: int) -> bool:
    cursor = pid
    visited: set[int] = set()
    for _ in range(64):
        if cursor == ancestor_pid:
            return True
        if cursor in visited or cursor <= 1:
            return False
        visited.add(cursor)
        cursor = _proc_parent_pid(cursor)
    return False


POST_EXEC_SHEBANG_LIMIT = 16


def _post_exec_resolution(
    executable: Path,
    argv: Sequence[str],
    *,
    path: str | None = None,
    executable_bytes: bytes | None = None,
) -> tuple[list[str], Path, bytes]:
    """Resolve the complete Linux shebang chain and return its final image."""

    if not argv:
        raise IncarnationHomeError("holder argv must not be empty")
    current_executable = executable
    current_argv = list(argv)
    current_bytes = executable_bytes
    visited: set[Path] = set()
    current_argv0_path: str | None = None
    for _ in range(POST_EXEC_SHEBANG_LIMIT):
        try:
            content = (
                current_bytes
                if current_bytes is not None
                else current_executable.read_bytes()
            )
            first_line = content.splitlines(keepends=True)[0]
        except (IndexError, OSError) as exc:
            raise IncarnationHomeError("Codex executable could not be inspected") from exc
        try:
            identity = current_executable.resolve(strict=False)
        except OSError:
            identity = current_executable.absolute()
        if identity in visited:
            raise IncarnationHomeError("Codex shebang interpreter chain is cyclic")
        visited.add(identity)
        if not first_line.startswith(b"#!"):
            return current_argv, current_executable, content
        shebang = os.fsdecode(first_line[2:]).strip()
        fields = shebang.split(maxsplit=1)
        if not fields or not fields[0].startswith("/"):
            raise IncarnationHomeError("Codex shebang interpreter is not absolute")
        previous_argv = current_argv
        if current_argv0_path is not None:
            # env executes the PATH result but preserves the command token as
            # argv[0].  If that result is itself a shebang (including through
            # a symlink), Linux inserts the exact execve spelling as argv[1];
            # retain it while using the resolved target only for byte reads.
            previous_argv = [current_argv0_path, *current_argv[1:]]
        if fields[0] == "/usr/bin/env" and len(fields) == 2 and fields[1]:
            env_fields = shlex.split(fields[1])
            if env_fields and env_fields[0] in {"-S", "--split-string"}:
                env_fields = env_fields[1:]
            elif len(env_fields) != 1:
                # Without env -S, Linux passes the optional shebang argument as
                # one command-name string; do not invent an interpreter re-exec
                # for an invalid multi-token env command.
                env_fields = []
            if env_fields and not env_fields[0].startswith("-"):
                resolved = shutil.which(
                    env_fields[0],
                    path=path if path is not None else os.environ.get("PATH"),
                )
                if resolved is not None:
                    # env resolves the command for lookup but preserves the
                    # command token as argv[0] for the re-exec.  Recording the
                    # resolved filesystem path here rejects a valid holder
                    # whose /proc argv starts with the admitted token (for
                    # example, "node").
                    current_argv = [
                        env_fields[0],
                        *env_fields[1:],
                        *previous_argv,
                    ]
                    current_executable = _resolved_executable(Path(resolved))
                    current_bytes = None
                    current_argv0_path = resolved
                    continue
        current_argv = [fields[0]]
        if len(fields) == 2 and fields[1]:
            current_argv.append(fields[1])
        current_argv.extend(previous_argv)
        current_executable = _resolved_executable(Path(fields[0]))
        current_bytes = None
        current_argv0_path = None
    raise IncarnationHomeError("Codex shebang interpreter chain is too deep")


def _post_exec_argv(
    executable: Path,
    argv: Sequence[str],
    *,
    path: str | None = None,
    executable_bytes: bytes | None = None,
) -> list[str]:
    """Derive Linux's post-exec argv for ELF and nested shebang commands."""

    post_exec_argv, _final_executable, _final_bytes = _post_exec_resolution(
        executable,
        argv,
        path=path,
        executable_bytes=executable_bytes,
    )
    return post_exec_argv


def _post_exec_executable_digest(
    executable: Path,
    *,
    path: str | None = None,
    executable_bytes: bytes | None = None,
) -> str:
    """Hash the final executable Linux will run after nested shebang resolution."""

    try:
        _post_exec_argv_value, _final_executable, final_bytes = _post_exec_resolution(
            executable,
            [str(executable)],
            path=path,
            executable_bytes=executable_bytes,
        )
        return sha256_bytes(final_bytes)
    except (IncarnationHomeError, OSError) as exc:
        raise IncarnationHomeError(
            "Codex post-exec interpreter could not be hashed"
        ) from exc


def _kitty_ancestor(pid: int) -> tuple[int, int, list[str]]:
    """Return the first exact Kitty ancestor of one visible holder."""

    cursor = pid
    visited: set[int] = set()
    for _ in range(64):
        parent_pid = _proc_parent_pid(cursor)
        if parent_pid <= 1 or parent_pid in visited:
            break
        visited.add(parent_pid)
        parent_comm = _proc_comm(parent_pid)
        if parent_comm == "kitty":
            return parent_pid, _proc_start_ticks(parent_pid), _proc_argv(parent_pid)
        cursor = parent_pid
    raise IncarnationHomeError("visible holder has no Kitty terminal ancestor")


def _validate_kitty_dedication_topology(
    *,
    holder_pid: int,
    kitty_pid: int,
    terminal_argv: Sequence[str],
    window_id: str,
) -> tuple[str, bool]:
    """Validate a detached, single-window Kitty topology from bound evidence."""

    if "--detach" not in terminal_argv:
        raise IncarnationHomeError(
            "holder Kitty terminal is not a detached dedicated process"
        )
    if not re.fullmatch(r"[1-9][0-9]*", window_id):
        raise IncarnationHomeError("holder Kitty window identity is missing")

    cursor = holder_pid
    visited: set[int] = set()
    direct_child: int | None = None
    for _ in range(64):
        parent_pid = _proc_parent_pid(cursor)
        if parent_pid <= 1 or parent_pid in visited:
            break
        if parent_pid == kitty_pid:
            direct_child = cursor
            break
        visited.add(parent_pid)
        cursor = parent_pid
    if direct_child is None:
        raise IncarnationHomeError("holder Kitty window is no longer an ancestor")

    for child_pid in _proc_children(kitty_pid):
        if child_pid == direct_child:
            continue
        # Kitty creates short-lived kitten helper processes for configuration
        # watching and exit cleanup. They are not terminal tabs/windows.
        if _proc_comm(child_pid) == "kitten":
            continue
        raise IncarnationHomeError(
            "holder Kitty process is not dedicated to this responsibility holder"
        )
    return window_id, True


def _kitty_dedication(
    *, holder_pid: int, kitty_pid: int, terminal_argv: Sequence[str]
) -> tuple[str, bool]:
    """Bind Kitty identity from launch-time holder environment and topology."""

    environment = _proc_environ(holder_pid)
    if environment.get("KITTY_PID") != str(kitty_pid):
        raise IncarnationHomeError("holder Kitty window does not bind its Kitty PID")
    window_id = environment.get("KITTY_WINDOW_ID", "")
    return _validate_kitty_dedication_topology(
        holder_pid=holder_pid,
        kitty_pid=kitty_pid,
        terminal_argv=terminal_argv,
        window_id=window_id,
    )


def _kitty_dedication_from_receipt(
    *,
    receipt: dict[str, Any],
    holder_pid: int,
    kitty_pid: int,
    terminal_argv: Sequence[str],
) -> tuple[str, bool]:
    """Revalidate Kitty from immutable launch-time receipt fields after return.

    The holder environment is intentionally not reopened here.  The launch
    receipt already captured the environment-derived window binding and is
    pinned by the holder receipt digest, handoff, and close authorization.
    Current process identity, ancestry, and dedicated-child topology remain
    live checks in ``_validate_kitty_dedication_topology``.
    """

    terminal = receipt.get("terminal")
    if not isinstance(terminal, dict):
        raise IncarnationHomeError("holder Kitty receipt binding is missing")
    if terminal.get("pid") != kitty_pid:
        raise IncarnationHomeError("holder Kitty receipt PID binding has drifted")
    window_id = terminal.get("window_id")
    if not isinstance(window_id, str) or not re.fullmatch(r"[1-9][0-9]*", window_id):
        raise IncarnationHomeError("holder Kitty receipt window identity is invalid")
    if terminal.get("dedicated") is not True:
        raise IncarnationHomeError("holder Kitty receipt dedication proof is missing")
    return _validate_kitty_dedication_topology(
        holder_pid=holder_pid,
        kitty_pid=kitty_pid,
        terminal_argv=terminal_argv,
        window_id=window_id,
    )


def _validate_legacy_holder_process_identity(
    *,
    holder_pid: int,
    holder_start_ticks: int,
    holder_parent_pid: int,
    holder_parent_start_ticks: int,
    holder_parent_comm: str,
    holder_argv: Sequence[str],
    kitty_pid: int,
    kitty_start_ticks: int,
    kitty_argv: Sequence[str],
) -> None:
    """Prove legacy receipt identities before assigning a fresh binding boot."""

    if _proc_start_ticks(holder_pid) != holder_start_ticks:
        raise IncarnationHomeError(
            "legacy holder PID was reused or has drifted"
        )
    if _proc_start_ticks(holder_parent_pid) != holder_parent_start_ticks:
        raise IncarnationHomeError(
            "legacy holder parent PID was reused or has drifted"
        )
    if _proc_parent_pid(holder_pid) != holder_parent_pid:
        raise IncarnationHomeError("legacy holder parent identity has drifted")
    if _proc_comm(holder_parent_pid) != holder_parent_comm:
        raise IncarnationHomeError("legacy holder parent process has drifted")
    if _proc_argv(holder_pid) != list(holder_argv):
        raise IncarnationHomeError("legacy holder argv identity has drifted")
    if _proc_start_ticks(kitty_pid) != kitty_start_ticks:
        raise IncarnationHomeError(
            "legacy holder Kitty PID was reused or has drifted"
        )
    if _proc_comm(kitty_pid) != "kitty":
        raise IncarnationHomeError("legacy holder terminal is not Kitty")
    if _proc_argv(kitty_pid) != list(kitty_argv):
        raise IncarnationHomeError("legacy holder Kitty argv identity has drifted")


def _send_verified_signal(pid: int, start_ticks: int, signal_number: int) -> bool:
    """Send one signal to an exact process identity through a pidfd."""

    pidfd_open = getattr(os, "pidfd_open", None)
    pidfd_send_signal = getattr(signal, "pidfd_send_signal", None)
    if not callable(pidfd_open) or not callable(pidfd_send_signal):
        raise IncarnationHomeError("verified pidfd signaling is unavailable")
    try:
        pidfd = pidfd_open(pid, 0)
    except ProcessLookupError:
        return False
    try:
        if _proc_start_ticks(pid) != start_ticks:
            raise IncarnationHomeError("holder identity changed before signaling")
        try:
            pidfd_send_signal(pidfd, signal_number)
        except ProcessLookupError:
            return False
        return True
    except OSError as exc:
        raise IncarnationHomeError("verified holder TERM delivery failed") from exc
    finally:
        os.close(pidfd)


def _send_verified_term(pid: int, start_ticks: int) -> bool:
    """Send TERM to the exact holder through a pidfd after rechecking it."""

    return _send_verified_signal(pid, start_ticks, signal.SIGTERM)


def _send_verified_kill(pid: int, start_ticks: int) -> bool:
    """Escalate to KILL only after rechecking the exact holder identity."""

    return _send_verified_signal(pid, start_ticks, signal.SIGKILL)


def _write_atomic_json(
    path: Path,
    value: dict[str, Any],
    label: str,
    *,
    replace: bool,
    ambient_identities: set[tuple[int, int]] | None = None,
) -> None:
    payload = canonical_bytes(value) + b"\n"
    ambient_identities = ambient_identities or set()
    parent_fd = _open_pinned_parent_directory(path, label)
    existing_fd: int | None = None
    staged_fd: int | None = None
    try:
        try:
            target = os.lstat(path.name, dir_fd=parent_fd)
        except FileNotFoundError:
            target = None
        if target is not None:
            if not replace:
                raise IncarnationHomeError(f"{label} already exists: {path}")
            existing_fd, opened = _open_stable_regular_file_at(
                parent_fd,
                path.name,
                label=label,
                ambient_identities=ambient_identities,
            )
            try:
                _revalidate_regular_file_at(
                    parent_fd,
                    path.name,
                    existing_fd,
                    opened,
                    label=label,
                    ambient_identities=ambient_identities,
                )
                staged_fd = _create_unnameable_temporary_file_at(parent_fd, label)
                _write_descriptor_exact(staged_fd, payload, 0o600, str(path))
                _replace_with_staged_file_at(
                    parent_fd=parent_fd,
                    target_name=path.name,
                    target_descriptor=existing_fd,
                    target_initial=opened,
                    staged_descriptor=staged_fd,
                    label=label,
                    ambient_identities=ambient_identities,
                )
                os.fsync(parent_fd)
                os.close(staged_fd)
                staged_fd = None
            finally:
                os.close(existing_fd)
                existing_fd = None
        else:
            staged_fd = _create_unnameable_temporary_file_at(parent_fd, label)
            _write_descriptor_exact(staged_fd, payload, 0o600, str(path))
            _publish_unnameable_file_at(parent_fd, staged_fd, path.name, label)
            os.fsync(parent_fd)
    except FileExistsError as exc:
        raise IncarnationHomeError(f"{label} already exists: {path}") from exc
    except OSError as exc:
        raise IncarnationHomeError(f"cannot write {label}: {path}") from exc
    finally:
        if existing_fd is not None:
            os.close(existing_fd)
        if staged_fd is not None:
            os.close(staged_fd)
        os.close(parent_fd)


def _write_new_json(
    path: Path,
    value: dict[str, Any],
    label: str,
    *,
    ambient_identities: set[tuple[int, int]] | None = None,
) -> None:
    _write_atomic_json(
        path,
        value,
        label,
        replace=False,
        ambient_identities=ambient_identities,
    )


def _holder_claim_path(manifest_path: Path) -> Path:
    return manifest_path.with_name(HOLDER_CLAIM_FILE_NAME)


def _reject_claimed_home_repreparation(manifest_path: Path) -> None:
    """Freeze a home as soon as its durable holder claim is published."""

    claim_path = _holder_claim_path(manifest_path)
    try:
        os.lstat(claim_path)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise IncarnationHomeError(
            f"holder claim cannot be inspected before re-preparation: {claim_path}"
        ) from exc
    raise IncarnationHomeError(
        "holder-claimed incarnation home is frozen against re-preparation"
    )


def _reserve_holder_claim(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    manifest_digest: str,
    binding_context_digest: str,
    holder_receipt_path: Path,
    ambient_identities: set[tuple[int, int]] | None = None,
) -> tuple[Path, str]:
    if SHA256_DIGEST_PATTERN.fullmatch(manifest_digest) is None:
        raise IncarnationHomeError("holder claim manifest digest is invalid")
    if SHA256_DIGEST_PATTERN.fullmatch(binding_context_digest) is None:
        raise IncarnationHomeError("holder claim binding context digest is invalid")
    claim_path = _holder_claim_path(manifest_path)
    expected_manifest_path = manifest_path.resolve()
    if claim_path.resolve().parent != expected_manifest_path.parent:
        raise IncarnationHomeError("holder claim path escaped the manifest home")
    _validate_owner_private_parent(claim_path, "holder claim")
    if claim_path.is_symlink() or claim_path.exists():
        raise IncarnationHomeError(
            "incarnation home already has an active or completed holder claim"
        )
    holder_binding = _validate_holder_binding_manifest_record(
        manifest.get("holder_binding")
    )
    if holder_binding["binding_digest"] != binding_context_digest:
        raise IncarnationHomeError("holder claim binding context digest disagrees")
    receipt_ref = _safe_source_receipt_path(holder_receipt_path)
    claim = {
        "schema_version": HOLDER_CLAIM_SCHEMA_VERSION,
        "manifest_path": str(expected_manifest_path),
        "manifest_digest": manifest_digest,
        "holder_binding": holder_binding,
        "holder_receipt": receipt_ref,
        "created_at": _utc_now(),
    }
    _write_new_json(
        claim_path,
        claim,
        "holder claim",
        ambient_identities=ambient_identities,
    )
    try:
        claim_digest = sha256_bytes(claim_path.read_bytes())
    except OSError as exc:
        raise IncarnationHomeError("holder claim could not be hashed") from exc
    return claim_path, claim_digest


def _validate_holder_claim(
    *,
    claim_path: Path,
    claim_digest: str,
    manifest_path: Path,
    manifest: dict[str, Any],
    manifest_digest: str,
    binding_context_digest: str,
    holder_receipt_path: Path,
) -> None:
    claim, raw = _load_json_snapshot(claim_path, "holder claim")
    if sha256_bytes(raw) != claim_digest:
        raise IncarnationHomeError("holder claim digest drifted")
    expected_fields = {
        "schema_version",
        "manifest_path",
        "manifest_digest",
        "holder_binding",
        "holder_receipt",
        "created_at",
    }
    if set(claim) != expected_fields:
        raise IncarnationHomeError("holder claim fields are not exact")
    if claim.get("schema_version") != HOLDER_CLAIM_SCHEMA_VERSION:
        raise IncarnationHomeError("unsupported holder claim schema")
    if not isinstance(claim_digest, str) or SHA256_DIGEST_PATTERN.fullmatch(
        claim_digest
    ) is None:
        raise IncarnationHomeError("holder claim digest is invalid")
    if not isinstance(claim.get("created_at"), str) or not claim["created_at"].strip():
        raise IncarnationHomeError("holder claim creation time is invalid")
    expected_claim = {
        "manifest_path": str(manifest_path.resolve()),
        "manifest_digest": manifest_digest,
        "holder_binding": _validate_holder_binding_manifest_record(
            manifest.get("holder_binding")
        ),
        "holder_receipt": _safe_source_receipt_path(holder_receipt_path),
    }
    if SHA256_DIGEST_PATTERN.fullmatch(manifest_digest) is None:
        raise IncarnationHomeError("holder claim manifest digest is invalid")
    if SHA256_DIGEST_PATTERN.fullmatch(binding_context_digest) is None:
        raise IncarnationHomeError("holder claim binding context digest is invalid")
    for key, expected in expected_claim.items():
        if claim.get(key) != expected:
            raise IncarnationHomeError(f"holder claim {key} disagrees with launch")
    if claim["holder_binding"]["binding_digest"] != binding_context_digest:
        raise IncarnationHomeError("holder claim binding context digest disagrees")


def _reserve_or_transfer_holder_claim(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    manifest_digest: str,
    binding_context_digest: str,
    holder_receipt_path: Path,
    ambient_identities: set[tuple[int, int]] | None = None,
) -> tuple[Path, str]:
    """Reserve a claim, or transfer the exact claim to a replacement receipt."""

    claim_path = _holder_claim_path(manifest_path)
    try:
        observed = os.lstat(claim_path)
    except FileNotFoundError:
        return _reserve_holder_claim(
            manifest_path=manifest_path,
            manifest=manifest,
            manifest_digest=manifest_digest,
            binding_context_digest=binding_context_digest,
            holder_receipt_path=holder_receipt_path,
            ambient_identities=ambient_identities,
        )
    except OSError as exc:
        raise IncarnationHomeError(
            f"holder claim cannot be inspected: {claim_path}"
        ) from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise IncarnationHomeError(
            "incarnation home already has an active or completed holder claim"
        )
    claim, raw = _load_json_snapshot(claim_path, "holder claim")
    claim_digest = sha256_bytes(raw)
    requested_receipt = _safe_source_receipt_path(holder_receipt_path)
    current_receipt = claim.get("holder_receipt")
    if not isinstance(current_receipt, str):
        raise IncarnationHomeError("holder claim holder_receipt is invalid")
    if current_receipt == requested_receipt:
        _validate_holder_claim(
            claim_path=claim_path,
            claim_digest=claim_digest,
            manifest_path=manifest_path,
            manifest=manifest,
            manifest_digest=manifest_digest,
            binding_context_digest=binding_context_digest,
            holder_receipt_path=holder_receipt_path,
        )
        return claim_path, claim_digest
    previous_receipt_path = Path(current_receipt)
    if _safe_source_receipt_path(previous_receipt_path) != current_receipt:
        raise IncarnationHomeError("holder claim holder_receipt is invalid")
    _validate_holder_claim(
        claim_path=claim_path,
        claim_digest=claim_digest,
        manifest_path=manifest_path,
        manifest=manifest,
        manifest_digest=manifest_digest,
        binding_context_digest=binding_context_digest,
        holder_receipt_path=previous_receipt_path,
    )
    transferred = dict(claim)
    transferred["holder_receipt"] = requested_receipt
    _write_atomic_json(
        claim_path,
        transferred,
        "holder claim transfer",
        replace=True,
        ambient_identities=ambient_identities,
    )
    try:
        transferred_raw = _regular_file(claim_path, "holder claim").read_bytes()
    except OSError as exc:
        raise IncarnationHomeError("holder claim transfer could not be hashed") from exc
    return claim_path, sha256_bytes(transferred_raw)


def _stable_regular_file_bytes(
    path: Path,
    label: str,
    *,
    ambient_identities: set[tuple[int, int]],
) -> bytes | None:
    """Read one regular file through a retained, unaliased descriptor."""

    parent_fd = _open_pinned_parent_directory(path, label)
    descriptor: int | None = None
    try:
        try:
            observed = os.lstat(path.name, dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise IncarnationHomeError(f"{label} cannot be inspected") from exc
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
            raise IncarnationHomeError(f"{label} is not a regular file")
        descriptor, opened = _open_stable_regular_file_at(
            parent_fd,
            path.name,
            label=label,
            ambient_identities=ambient_identities,
        )
        raw = _read_descriptor_bytes(descriptor, str(path))
        _revalidate_regular_file_at(
            parent_fd,
            path.name,
            descriptor,
            opened,
            label=label,
            ambient_identities=ambient_identities,
        )
        return raw
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _restore_holder_claim_snapshot(
    *,
    claim_path: Path,
    before_raw: bytes | None,
    after_digest: str,
    ambient_identities: set[tuple[int, int]],
) -> None:
    """Restore a transferred claim only while its published inode is retained."""

    if SHA256_DIGEST_PATTERN.fullmatch(after_digest) is None:
        raise IncarnationHomeError("holder claim rollback digest is invalid")
    parent_fd = _open_pinned_parent_directory(claim_path, "holder claim rollback")
    descriptor: int | None = None
    staged_descriptor: int | None = None
    try:
        try:
            observed = os.lstat(claim_path.name, dir_fd=parent_fd)
        except OSError as exc:
            raise IncarnationHomeError(
                "holder claim rollback target cannot be inspected"
            ) from exc
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
            raise IncarnationHomeError(
                "holder claim rollback target is not a regular file"
            )
        descriptor, opened = _open_stable_regular_file_at(
            parent_fd,
            claim_path.name,
            label="holder claim rollback",
            ambient_identities=ambient_identities,
        )
        current_raw = _read_descriptor_bytes(descriptor, str(claim_path))
        if sha256_bytes(current_raw) != after_digest:
            raise IncarnationHomeError("holder claim changed before rollback")
        _revalidate_regular_file_at(
            parent_fd,
            claim_path.name,
            descriptor,
            opened,
            label="holder claim rollback",
            ambient_identities=ambient_identities,
        )
        if before_raw is None:
            try:
                os.unlink(claim_path.name, dir_fd=parent_fd)
            except OSError as exc:
                raise IncarnationHomeError(
                    "holder claim could not be rolled back"
                ) from exc
        else:
            staged_descriptor = _create_unnameable_temporary_file_at(
                parent_fd, "holder claim rollback"
            )
            _write_descriptor_exact(
                staged_descriptor,
                before_raw,
                0o600,
                "holder claim rollback",
            )
            _replace_with_staged_file_at(
                parent_fd=parent_fd,
                target_name=claim_path.name,
                target_descriptor=descriptor,
                target_initial=opened,
                staged_descriptor=staged_descriptor,
                label="holder claim rollback",
                ambient_identities=ambient_identities,
            )
            os.close(staged_descriptor)
            staged_descriptor = None
        os.fsync(parent_fd)
    finally:
        if staged_descriptor is not None:
            os.close(staged_descriptor)
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _existing_rebind_receipt(
    path: Path,
    expected: dict[str, Any],
    *,
    ambient_identities: set[tuple[int, int]],
) -> dict[str, Any] | None:
    """Accept only the exact canonical receipt as an idempotent retry."""

    raw = _stable_regular_file_bytes(
        path,
        "replacement holder terminal receipt",
        ambient_identities=ambient_identities,
    )
    if raw is None:
        return None
    existing = _decode_json_snapshot(raw, "replacement holder terminal receipt")
    _assert_safe_projection(existing)
    existing, _validated_raw, _digest = _load_holder_receipt_snapshot(
        path,
        snapshot=(existing, raw),
    )
    comparable_existing = dict(existing)
    comparable_expected = dict(expected)
    comparable_existing.pop("created_at", None)
    comparable_expected.pop("created_at", None)
    if comparable_existing != comparable_expected:
        raise IncarnationHomeError(
            "replacement holder terminal receipt already exists with different binding"
        )
    return existing


def _release_holder_claim(
    *, claim_path: Path, claim_digest: str, label: str = "holder claim"
) -> None:
    """Remove only the exact unpublished reservation; uncertainty is retained."""

    try:
        raw = _regular_file(claim_path, label).read_bytes()
    except IncarnationHomeError:
        raise
    if sha256_bytes(raw) != claim_digest:
        raise IncarnationHomeError(f"{label} changed before rollback")
    try:
        claim_path.unlink()
    except OSError as exc:
        raise IncarnationHomeError(f"cannot roll back {label}") from exc


def _write_reservation_json(
    path: Path, value: dict[str, Any], label: str
) -> None:
    _write_atomic_json(path, value, label, replace=True)


def _closure_reservation_path(path: Path) -> Path:
    return path.with_name(path.name + ".reservation.json")


def _closure_reservation_lock_path(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


def _reserve_closure_receipt(
    *,
    closure_receipt_path: Path,
    handoff_path: Path,
    holder_receipt_path: Path,
    wake_receipt_path: Path,
    authorization_path: Path | None = None,
    authorization_kind: str = "wake_delivered",
    evidence_path: Path | None = None,
    authorization_digest: str | None = None,
    evidence_digest: str | None = None,
    allow_legacy_wake_reservation: bool = False,
    holder_pid: int,
    terminal_pid: int,
) -> tuple[int, Path, dict[str, Any] | None]:
    """Reserve a recoverable close attempt before any external signal."""

    if (
        not closure_receipt_path.is_absolute()
        or closure_receipt_path.is_symlink()
    ):
        raise IncarnationHomeError(
            "terminal closure receipt path is invalid: "
            f"{closure_receipt_path}"
        )
    if closure_receipt_path.exists() and not closure_receipt_path.is_file():
        raise IncarnationHomeError(
            "terminal closure receipt path is not a regular file: "
            f"{closure_receipt_path}"
        )
    parent = closure_receipt_path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise IncarnationHomeError(
            "terminal closure receipt parent must be a real directory: "
            f"{parent}"
        )
    reservation_path = _closure_reservation_path(closure_receipt_path)
    if reservation_path.is_symlink():
        raise IncarnationHomeError(
            f"terminal closure reservation may not be a symlink: {reservation_path}"
        )
    if closure_receipt_path.exists() and not reservation_path.exists():
        raise IncarnationHomeError(
            "terminal closure receipt already exists without its reservation: "
            f"{closure_receipt_path}"
        )
    if authorization_kind not in {"wake_delivered", "join_completed"}:
        raise IncarnationHomeError("unsupported terminal closure authorization kind")
    if authorization_path is None:
        authorization_path = wake_receipt_path
    if evidence_path is None:
        evidence_path = wake_receipt_path
    expected = {
        "schema_version": CLOSURE_RESERVATION_SCHEMA_VERSION,
        "closure_receipt_ref": str(closure_receipt_path.resolve()),
        "handoff_ref": str(handoff_path.resolve()),
        "holder_receipt_ref": str(holder_receipt_path.resolve()),
        "authorization_ref": str(authorization_path.resolve()),
        "authorization_kind": authorization_kind,
        "holder_pid": holder_pid,
        "terminal_pid": terminal_pid,
    }
    expected[
        "wake_receipt_ref" if authorization_kind == "wake_delivered" else "join_receipt_ref"
    ] = str(evidence_path.resolve())

    def populate_v2_digests() -> None:
        nonlocal authorization_digest, evidence_digest
        if authorization_digest is None:
            try:
                authorization_digest = sha256_bytes(
                    _regular_file(
                        authorization_path, "terminal closure authorization"
                    ).read_bytes()
                )
            except (IncarnationHomeError, OSError) as exc:
                raise IncarnationHomeError(
                    "terminal closure authorization could not be hashed"
                ) from exc
        if evidence_digest is None:
            try:
                evidence_digest = sha256_bytes(
                    _regular_file(evidence_path, "terminal closure evidence").read_bytes()
                )
            except (IncarnationHomeError, OSError) as exc:
                raise IncarnationHomeError(
                    "terminal closure evidence could not be hashed"
                ) from exc
        if not SHA256_DIGEST_PATTERN.fullmatch(authorization_digest):
            raise IncarnationHomeError("terminal closure authorization digest is invalid")
        if not SHA256_DIGEST_PATTERN.fullmatch(evidence_digest):
            raise IncarnationHomeError("terminal closure evidence digest is invalid")
        expected["authorization_sha256"] = authorization_digest
        expected["evidence_sha256"] = evidence_digest

    legacy_expected = {
        "schema_version": LEGACY_CLOSURE_RESERVATION_SCHEMA_VERSION,
        "closure_receipt_ref": str(closure_receipt_path.resolve()),
        "handoff_ref": str(handoff_path.resolve()),
        "holder_receipt_ref": str(holder_receipt_path.resolve()),
        "wake_receipt_ref": str(evidence_path.resolve()),
        "holder_pid": holder_pid,
        "terminal_pid": terminal_pid,
    }
    lock_path = _closure_reservation_lock_path(closure_receipt_path)
    if lock_path.is_symlink():
        raise IncarnationHomeError(
            f"terminal closure reservation lock may not be a symlink: {lock_path}"
        )
    lock_fd: int | None = None
    try:
        lock_flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            lock_flags |= os.O_NOFOLLOW
        lock_fd = os.open(lock_path, lock_flags, 0o600)
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if not reservation_path.exists():
            populate_v2_digests()
            _write_new_json(
                reservation_path,
                {**expected, "reserved_at": _utc_now()},
                "terminal closure reservation",
            )
        recorded = _load_json(
            reservation_path, "terminal closure reservation"
        )
        if recorded.get("schema_version") == LEGACY_CLOSURE_RESERVATION_SCHEMA_VERSION:
            if (
                not allow_legacy_wake_reservation
                or authorization_kind != "wake_delivered"
                or any(
                    recorded.get(key) != value
                    for key, value in legacy_expected.items()
                )
            ):
                raise IncarnationHomeError(
                    "terminal closure reservation identity mismatch"
                )
        elif recorded.get("schema_version") == CLOSURE_RESERVATION_SCHEMA_VERSION:
            populate_v2_digests()
            if any(recorded.get(key) != value for key, value in expected.items()):
                raise IncarnationHomeError("terminal closure reservation identity mismatch")
        else:
            raise IncarnationHomeError("unsupported terminal closure reservation schema")
        completed: dict[str, Any] | None = None
        if closure_receipt_path.exists():
            completed = _load_json(
                closure_receipt_path, "terminal closure receipt"
            )
            completed_schema = completed.get("schema_version")
            if completed_schema == LEGACY_TERMINAL_CLOSURE_SCHEMA_VERSION:
                if (
                    not allow_legacy_wake_reservation
                    or authorization_kind != "wake_delivered"
                    or recorded.get("schema_version")
                    != LEGACY_CLOSURE_RESERVATION_SCHEMA_VERSION
                ):
                    raise IncarnationHomeError(
                        "legacy terminal closure receipt requires the legacy wake route"
                    )
                legacy_identity = {
                    "handoff_ref": str(handoff_path.resolve()),
                    "holder_receipt_ref": str(holder_receipt_path.resolve()),
                    "wake_receipt_ref": str(evidence_path.resolve()),
                    "reservation_ref": str(reservation_path.resolve()),
                    "route": "abyss_stack_visible_incarnation_runtime",
                    "trigger": "wake_bridge_after_confirmed_handoff_delivery",
                }
                if any(
                    completed.get(key) != value
                    for key, value in legacy_identity.items()
                ):
                    raise IncarnationHomeError(
                        "completed legacy terminal closure identity mismatch"
                    )
            elif completed_schema == TERMINAL_CLOSURE_SCHEMA_VERSION:
                completed_identity = {
                    "handoff_ref": str(handoff_path.resolve()),
                    "holder_receipt_ref": str(holder_receipt_path.resolve()),
                    "authorization_ref": str(authorization_path.resolve()),
                    "authorization_kind": authorization_kind,
                    "authorization_evidence_ref": str(evidence_path.resolve()),
                    "reservation_ref": str(reservation_path.resolve()),
                    "route": "abyss_stack_visible_incarnation_runtime",
                    "trigger": (
                        "wake_bridge_after_confirmed_handoff_delivery"
                        if authorization_kind == "wake_delivered"
                        else "join_after_validated_terminal_return"
                    ),
                }
                if any(
                    completed.get(key) != value
                    for key, value in completed_identity.items()
                ):
                    raise IncarnationHomeError(
                        "completed terminal closure identity mismatch"
                    )
                evidence_key = (
                    "wake_receipt_ref"
                    if authorization_kind == "wake_delivered"
                    else "join_receipt_ref"
                )
                if completed.get(evidence_key) != str(evidence_path.resolve()):
                    raise IncarnationHomeError(
                        "completed terminal closure evidence identity mismatch"
                    )
            else:
                raise IncarnationHomeError("unsupported terminal closure receipt schema")
            if completed.get("reservation_ref") != str(reservation_path.resolve()):
                raise IncarnationHomeError(
                    "completed terminal closure reservation identity mismatch"
                )
            if completed.get("holder", {}).get("pid") != holder_pid:
                raise IncarnationHomeError(
                    "completed terminal closure holder identity mismatch"
                )
            if completed.get("terminal", {}).get("pid") != terminal_pid:
                raise IncarnationHomeError(
                    "completed terminal closure terminal identity mismatch"
                )
            if not isinstance(completed.get("closed"), bool):
                raise IncarnationHomeError(
                    "completed terminal closure status is invalid"
                )
        return lock_fd, reservation_path, completed
    except BaseException:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        raise


def _wait_for_visible_terminal_binding(
    *, holder_pid: int
) -> tuple[int, int, list[str], str, bool]:
    """Wait for the causal Kitty ancestry and dedication handshake to settle."""

    deadline = time.monotonic() + VISIBLE_TERMINAL_BINDING_WAIT_SECONDS
    last_error: IncarnationHomeError | None = None
    while True:
        try:
            terminal_pid, terminal_start_ticks, terminal_argv = _kitty_ancestor(
                holder_pid
            )
            window_id, dedicated = _kitty_dedication(
                holder_pid=holder_pid,
                kitty_pid=terminal_pid,
                terminal_argv=terminal_argv,
            )
            return terminal_pid, terminal_start_ticks, terminal_argv, window_id, dedicated
        except IncarnationHomeError as exc:
            last_error = exc
            if time.monotonic() >= deadline:
                raise IncarnationHomeError(
                    "visible holder terminal binding did not become ready: "
                    f"{last_error}"
                ) from exc
            time.sleep(VISIBLE_TERMINAL_BINDING_POLL_SECONDS)


def _holder_receipt(
    *,
    receipt_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    executable: Path,
    argv: Sequence[str],
    executable_bytes: bytes | None = None,
    executable_digest: str | None = None,
    manifest_bytes: bytes | None = None,
    manifest_digest: str | None = None,
    companion_binding: dict[str, str] | None = None,
    holder_binding: dict[str, str] | None = None,
    binding_context: dict[str, str] | None = None,
    control_socket: str | None = None,
    terminal_title: str | None = None,
) -> dict[str, Any]:
    holder_pid = os.getpid()
    holder_parent_pid = os.getppid()
    if holder_parent_pid <= 1:
        raise IncarnationHomeError("visible holder has no usable process parent")
    parent_comm = _proc_comm(holder_parent_pid)
    (
        terminal_pid,
        terminal_start_ticks,
        terminal_argv,
        window_id,
        dedicated,
    ) = _wait_for_visible_terminal_binding(holder_pid=holder_pid)
    post_exec_argv = _post_exec_argv(
        executable,
        argv,
        path=os.environ.get("PATH"),
        executable_bytes=executable_bytes,
    )
    pre_exec_argv = _proc_argv(holder_pid)
    if not pre_exec_argv:
        raise IncarnationHomeError("holder pre-exec argv is empty")
    pre_exec_exe_digest = _proc_exe_digest(holder_pid)
    post_exec_exe_digest = _post_exec_executable_digest(
        executable,
        path=os.environ.get("PATH"),
        executable_bytes=executable_bytes,
    )
    try:
        if manifest_bytes is None:
            manifest_bytes = manifest_path.read_bytes()
        if executable_digest is None:
            executable_digest = sha256_bytes(
                executable_bytes
                if executable_bytes is not None
                else executable.read_bytes()
            )
        if manifest_digest is None:
            manifest_digest = sha256_bytes(manifest_bytes)
    except OSError as exc:
        raise IncarnationHomeError("holder identity inputs could not be hashed") from exc
    if manifest_bytes is None or sha256_bytes(manifest_bytes) != manifest_digest:
        raise IncarnationHomeError("holder incarnation manifest snapshot digest is invalid")
    runtime = {
        "codex_executable": str(executable),
        "codex_executable_digest": executable_digest,
        "incarnation_manifest": str(manifest_path.resolve()),
        "incarnation_manifest_digest": manifest_digest,
        # The pathname above is provenance only after launch.  The receipt's
        # exact bytes are the holder-bound identity source because preparation
        # may refresh that pathname while this process remains alive.
        "incarnation_manifest_snapshot_b64": base64.b64encode(manifest_bytes).decode(
            "ascii"
        ),
        "model": str(manifest["model_slug"]),
        "reasoning_effort": str(manifest["reasoning_effort"]),
        "ambient_codex_home": str(manifest["ambient_codex_home"]),
        "incarnation_codex_home": str(manifest["codex_home"]),
    }
    if holder_binding is not None:
        runtime["holder_binding"] = _validate_holder_binding_manifest_record(
            holder_binding
        )
    if companion_binding is not None:
        runtime["codex_companion"] = dict(companion_binding)
    _decode_holder_manifest_snapshot(runtime)
    binding: dict[str, object] | None = None
    terminal: dict[str, object] = {
        "binding": "kitty_ancestor_at_exec",
        "required_comm": "kitty",
        "pid": terminal_pid,
        "start_ticks": terminal_start_ticks,
        "argv": terminal_argv,
        "window_id": window_id,
        "dedicated": dedicated,
    }
    if binding_context is not None:
        if control_socket is None or terminal_title is None:
            raise IncarnationHomeError(
                "canonical visible holder binding lacks socket or title"
            )
        tty = _holder_tty(holder_pid)
        binding = _terminal_binding(
            context=binding_context,
            control_socket=control_socket,
            terminal_title=terminal_title,
            window_id=window_id,
            tty=tty,
            holder_pid=holder_pid,
            holder_start_ticks=_proc_start_ticks(holder_pid),
            holder_argv_digest=sha256_bytes(canonical_bytes(post_exec_argv)),
            holder_exe_digest=post_exec_exe_digest,
            terminal_pid=terminal_pid,
            terminal_start_ticks=terminal_start_ticks,
        )
        terminal.update(
            {
                "tty": tty,
                "title": binding["terminal"]["title"],
                "control_socket": binding["terminal"]["control_socket"],
            }
        )
    receipt = {
        "schema_version": HOLDER_RECEIPT_SCHEMA_VERSION,
        "receipt_ref": str(receipt_path.resolve()),
        "created_at": _utc_now(),
        "lifecycle_role": "responsibility_holder",
        "boot_id": _proc_boot_id(),
        "holder": {
            "pid": holder_pid,
            "start_ticks": _proc_start_ticks(holder_pid),
            "parent_pid": holder_parent_pid,
            "parent_start_ticks": _proc_start_ticks(holder_parent_pid),
            "parent_comm": parent_comm,
            "pre_exec_argv": pre_exec_argv,
            "pre_exec_argv_digest": sha256_bytes(canonical_bytes(pre_exec_argv)),
            "pre_exec_exe_digest": pre_exec_exe_digest,
            "argv": post_exec_argv,
            "argv_digest": sha256_bytes(canonical_bytes(post_exec_argv)),
            "exe_digest": post_exec_exe_digest,
        },
        "runtime": runtime,
        "terminal": terminal,
    }
    if binding is not None:
        receipt["binding"] = binding
    _write_new_json(receipt_path, receipt, "holder terminal receipt")
    return receipt


def _rebind_replacement_holder_receipt(
    *,
    receipt_path: Path,
    holder_loss_reentry_path: Path,
    binding_context_path: Path,
    manifest_path: Path,
    codex_executable_path: Path,
) -> dict[str, Any]:
    """Bind a live replacement holder after a pre-return CLI loss.

    This is an explicit recovery adapter for the old direct visible bootstrap.
    It never upgrades the holder-loss receipt by itself: the replacement PID,
    Kitty ancestry, current argv/executable, scoped manifest, and every source
    digest are re-observed before a new canonical holder receipt is published.
    """

    context_document, context_raw = _load_json_snapshot(
        binding_context_path, "terminal binding context"
    )
    context = _validate_holder_binding_context(context_document)
    context_digest = sha256_bytes(context_raw)
    context_workspace = context_document.get("workspace")
    if not isinstance(context_workspace, str) or not Path(context_workspace).is_absolute():
        raise IncarnationHomeError("terminal binding context workspace is invalid")
    context["workspace"] = context_workspace
    reentry, _reentry_raw, reentry_digest = _load_holder_loss_reentry(
        holder_loss_reentry_path,
        expected_context=context,
    )
    holder_pid = reentry["current_holder"]["pid"]
    holder_start_ticks = reentry["current_holder"]["start_ticks"]
    terminal_pid = reentry["terminal"]["pid"]
    terminal_start_ticks = reentry["terminal"]["start_ticks"]
    if not _descends_from(os.getpid(), holder_pid):
        raise IncarnationHomeError(
            "replacement holder rebind must run from the bound holder lineage"
        )
    if _proc_identity_state(holder_pid, holder_start_ticks) != "live":
        raise IncarnationHomeError("replacement holder is not live")
    if _proc_identity_state(terminal_pid, terminal_start_ticks) != "live":
        raise IncarnationHomeError("replacement Kitty terminal is not live")
    if _proc_parent_pid(holder_pid) != terminal_pid:
        raise IncarnationHomeError("replacement holder is not a direct Kitty child")
    if _proc_start_ticks(terminal_pid) != terminal_start_ticks:
        raise IncarnationHomeError("replacement Kitty PID was reused")
    if _proc_comm(terminal_pid) != "kitty":
        raise IncarnationHomeError("replacement terminal is not Kitty")
    observed_terminal_pid, observed_terminal_start_ticks, terminal_argv = _kitty_ancestor(
        holder_pid
    )
    if (
        observed_terminal_pid != terminal_pid
        or observed_terminal_start_ticks != terminal_start_ticks
    ):
        raise IncarnationHomeError("replacement Kitty ancestry disagrees with reentry")
    window_id, dedicated = _kitty_dedication(
        holder_pid=holder_pid,
        kitty_pid=terminal_pid,
        terminal_argv=terminal_argv,
    )
    manifest, manifest_bytes, manifest_digest = _load_rebind_manifest(
        manifest_path,
        runtime_state_root=Path(context["runtime_state_root"]),
        binding_context=context,
        binding_context_digest=context_digest,
    )
    holder_binding = _validate_holder_binding_manifest_record(
        manifest.get("holder_binding")
    )
    executable = _regular_file(codex_executable_path, "replacement Codex executable")
    holder_environment = _proc_environ(holder_pid)
    holder_codex_home = holder_environment.get("CODEX_HOME")
    if holder_codex_home != manifest["codex_home"]:
        raise IncarnationHomeError(
            "replacement holder CODEX_HOME disagrees with its manifest"
        )
    holder_argv = _proc_argv(holder_pid)
    if not holder_argv:
        raise IncarnationHomeError("replacement holder argv is empty")
    _post_exec_argv_value, post_exec_executable, post_exec_bytes = _post_exec_resolution(
        executable,
        [str(executable)],
        path=holder_environment.get("PATH"),
    )
    observed_executable = Path(f"/proc/{holder_pid}/exe").resolve()
    if observed_executable != post_exec_executable.resolve():
        raise IncarnationHomeError(
            "replacement Codex executable path disagrees with live holder"
        )
    executable_digest = sha256_bytes(executable.read_bytes())
    post_exec_executable_digest = sha256_bytes(post_exec_bytes)
    if _proc_exe_digest(holder_pid) != post_exec_executable_digest:
        raise IncarnationHomeError("replacement Codex executable digest has drifted")
    holder_parent_pid = _proc_parent_pid(holder_pid)
    holder_parent_start_ticks = _proc_start_ticks(holder_parent_pid)
    holder_parent_comm = _proc_comm(holder_parent_pid)
    receipt: dict[str, Any] = {
        "schema_version": HOLDER_RECEIPT_SCHEMA_VERSION,
        "receipt_ref": str(receipt_path.resolve()),
        "created_at": _utc_now(),
        "lifecycle_role": "responsibility_holder",
        "boot_id": _proc_boot_id(),
        "holder": {
            "pid": holder_pid,
            "start_ticks": holder_start_ticks,
            "parent_pid": holder_parent_pid,
            "parent_start_ticks": holder_parent_start_ticks,
            "parent_comm": holder_parent_comm,
            "argv": holder_argv,
            "argv_digest": sha256_bytes(canonical_bytes(holder_argv)),
            "exe_digest": post_exec_executable_digest,
        },
        "runtime": {
            "codex_executable": str(executable.resolve()),
            "codex_executable_digest": executable_digest,
            "incarnation_manifest": str(manifest_path.resolve()),
            "incarnation_manifest_digest": manifest_digest,
            "incarnation_manifest_snapshot_b64": base64.b64encode(
                manifest_bytes
            ).decode("ascii"),
            "model": str(manifest["model_slug"]),
            "reasoning_effort": str(manifest["reasoning_effort"]),
            "ambient_codex_home": str(manifest["ambient_codex_home"]),
            "incarnation_codex_home": str(manifest["codex_home"]),
            "holder_binding": holder_binding,
        },
        "terminal": {
            "binding": "kitty_ancestor_at_exec",
            "required_comm": "kitty",
            "pid": terminal_pid,
            "start_ticks": terminal_start_ticks,
            "argv": terminal_argv,
            "window_id": window_id,
            "dedicated": dedicated,
        },
        "replacement_reentry": {
            "receipt_ref": str(holder_loss_reentry_path.resolve()),
            "receipt_sha256": reentry_digest,
            "duty_ref": reentry["duty_ref"],
            "duty_sha256": reentry["duty_sha256"],
            "failure_event_ref": reentry["failure_event_ref"],
            "failure_event_sha256": reentry["failure_event_sha256"],
            "goal_id": reentry["goal_id"],
            "actor_id": reentry["actor_id"],
            "session_id": reentry["session_id"],
            "holder_pid": holder_pid,
            "holder_start_ticks": holder_start_ticks,
        },
    }
    _assert_safe_projection(receipt)
    runtime_root_value = manifest.get("runtime_root")
    ambient_home_value = manifest.get("ambient_codex_home")
    if not isinstance(runtime_root_value, str) or not isinstance(
        ambient_home_value, str
    ):
        raise IncarnationHomeError(
            "replacement holder rebind lacks runtime and ambient roots"
        )
    runtime_root = _absolute_directory(Path(runtime_root_value), "runtime root")
    ambient_home = _absolute_directory(
        Path(ambient_home_value), "ambient Codex home"
    )
    ambient_identities = _ambient_inode_identities(ambient_home)
    claim_path = _holder_claim_path(manifest_path)
    with _incarnation_preparation_lock(runtime_root, ambient_identities):
        existing = _existing_rebind_receipt(
            receipt_path,
            receipt,
            ambient_identities=ambient_identities,
        )
        before_claim_raw = _stable_regular_file_bytes(
            claim_path,
            "holder claim",
            ambient_identities=ambient_identities,
        )
        _claim_path, after_claim_digest = _reserve_holder_claim_for_launch_locked(
            manifest_path=manifest_path,
            manifest=manifest,
            manifest_digest=manifest_digest,
            binding_context_digest=context_digest,
            binding_context=context,
            holder_receipt_path=receipt_path,
            ambient_identities=ambient_identities,
            allow_existing_claim=True,
        )
        if existing is not None:
            return existing
        try:
            _write_new_json(
                receipt_path,
                receipt,
                "replacement holder terminal receipt",
                ambient_identities=ambient_identities,
            )
        except BaseException:
            try:
                _restore_holder_claim_snapshot(
                    claim_path=claim_path,
                    before_raw=before_claim_raw,
                    after_digest=after_claim_digest,
                    ambient_identities=ambient_identities,
                )
            except BaseException as rollback_exc:
                raise IncarnationHomeError(
                    "holder claim rollback became uncertain"
                ) from rollback_exc
            raise
        return receipt


def _decode_holder_manifest_snapshot(runtime: dict[str, Any]) -> bytes | None:
    """Validate and return the immutable manifest snapshot in a holder receipt.

    Receipts written before this field existed remain readable for bounded
    recovery, but every repaired launch writes the snapshot and the live
    closer uses it instead of reopening the mutable preparation pathname.
    """

    encoded = runtime.get("incarnation_manifest_snapshot_b64")
    if encoded is None:
        return None
    if not isinstance(encoded, str) or not encoded:
        raise IncarnationHomeError("holder incarnation manifest snapshot is invalid")
    try:
        snapshot = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError, base64.binascii.Error) as exc:
        raise IncarnationHomeError(
            "holder incarnation manifest snapshot is not valid base64"
        ) from exc
    if not snapshot:
        raise IncarnationHomeError("holder incarnation manifest snapshot is empty")
    if sha256_bytes(snapshot) != runtime.get("incarnation_manifest_digest"):
        raise IncarnationHomeError(
            "holder incarnation manifest snapshot digest has drifted"
        )
    try:
        manifest = json.loads(snapshot.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IncarnationHomeError(
            "holder incarnation manifest snapshot is not valid JSON"
        ) from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        raise IncarnationHomeError("holder incarnation manifest snapshot is unsupported")
    for manifest_key, runtime_key in (
        ("model_slug", "model"),
        ("reasoning_effort", "reasoning_effort"),
        ("ambient_codex_home", "ambient_codex_home"),
        ("codex_home", "incarnation_codex_home"),
    ):
        if manifest.get(manifest_key) != runtime.get(runtime_key):
            raise IncarnationHomeError(
                "holder incarnation manifest snapshot binding has drifted"
            )
    runtime_holder_binding = runtime.get("holder_binding")
    manifest_holder_binding = manifest.get("holder_binding")
    if manifest_holder_binding is not None:
        if runtime_holder_binding is None:
            raise IncarnationHomeError(
                "holder incarnation manifest snapshot holder binding is missing"
            )
        if _validate_holder_binding_manifest_record(
            runtime_holder_binding
        ) != _validate_holder_binding_manifest_record(manifest_holder_binding):
            raise IncarnationHomeError(
                "holder incarnation manifest snapshot holder binding has drifted"
            )
    elif runtime_holder_binding is not None:
        raise IncarnationHomeError(
            "holder incarnation manifest snapshot has an unexpected holder binding"
        )
    else:
        raise IncarnationHomeError(
            "holder incarnation manifest snapshot holder binding is missing"
        )
    return snapshot


def _validate_wake_delivery(
    *,
    wake_receipt_path: Path,
    handoff_path: Path,
    holder_receipt_path: Path,
    closure_receipt_path: Path,
    holder_receipt: dict[str, Any],
    holder_receipt_bytes: bytes | None = None,
    holder_receipt_digest: str | None = None,
    wake_snapshot: tuple[dict[str, Any], bytes] | None = None,
    handoff_snapshot: tuple[dict[str, Any], bytes, str] | None = None,
) -> dict[str, Any]:
    wake = (
        _load_json(wake_receipt_path, "wake receipt")
        if wake_snapshot is None
        else wake_snapshot[0]
    )
    if wake.get("schema_version") not in {
        "task_local_actor_wake_receipt_v1",
        "abyss_stack_external_codex_return_receipt_v1",
    }:
        raise IncarnationHomeError("unsupported wake receipt schema")
    if wake.get("handoff_ref") != str(handoff_path.resolve()):
        raise IncarnationHomeError("wake receipt handoff identity mismatch")
    actions = wake.get("actions")
    observed = wake.get("observed")
    if (
        not isinstance(actions, dict)
        or actions.get("handoff_message_sent") is not True
        or not isinstance(observed, dict)
        or observed.get("handoff_delivery") is not True
    ):
        raise IncarnationHomeError("wake receipt does not prove handoff delivery")
    if wake.get("schema_version") == "abyss_stack_external_codex_return_receipt_v1":
        delivery = wake.get("delivery")
        if not isinstance(delivery, dict) or delivery.get("accepted") is not True:
            raise IncarnationHomeError(
                "canonical return receipt does not prove accepted delivery"
            )
    if handoff_snapshot is None:
        try:
            handoff_file = _regular_file(handoff_path, "handoff")
            handoff_bytes = handoff_file.read_bytes()
            handoff_digest = sha256_bytes(handoff_bytes)
            handoff_value = json.loads(handoff_bytes.decode("utf-8"))
        except (IncarnationHomeError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise IncarnationHomeError("cannot read delivered handoff snapshot") from exc
    else:
        handoff_value, handoff_bytes, handoff_digest = handoff_snapshot
        if sha256_bytes(handoff_bytes) != handoff_digest:
            raise IncarnationHomeError("delivered handoff snapshot digest is invalid")
    if wake.get("handoff_sha256") != handoff_digest:
        raise IncarnationHomeError("wake receipt handoff digest mismatch")
    if not isinstance(handoff_value, dict):
        raise IncarnationHomeError("handoff must be a JSON object")
    runtime = handoff_value.get("runtime")
    responsibility_holder = (
        runtime.get("responsibility_holder") if isinstance(runtime, dict) else None
    )
    if not isinstance(responsibility_holder, dict):
        raise IncarnationHomeError("handoff lacks responsibility-holder binding")
    holder_ref = str(holder_receipt_path.resolve())
    closure_ref = str(closure_receipt_path.resolve())
    if responsibility_holder.get("terminal_receipt") != holder_ref:
        raise IncarnationHomeError("handoff holder receipt identity mismatch")
    if responsibility_holder.get("closure_receipt") != closure_ref:
        raise IncarnationHomeError("handoff closure receipt identity mismatch")
    if holder_receipt_digest is None:
        try:
            holder_receipt_digest = sha256_bytes(
                holder_receipt_bytes
                if holder_receipt_bytes is not None
                else holder_receipt_path.read_bytes()
            )
        except OSError as exc:
            raise IncarnationHomeError("holder receipt could not be hashed") from exc
    if responsibility_holder.get("terminal_receipt_sha256") != holder_receipt_digest:
        raise IncarnationHomeError("handoff holder receipt digest mismatch")
    if responsibility_holder.get("holder_pid") != holder_receipt["holder"].get("pid"):
        raise IncarnationHomeError("handoff responsibility-holder PID mismatch")
    if responsibility_holder.get("terminal_pid") != holder_receipt["terminal"].get("pid"):
        raise IncarnationHomeError("handoff terminal PID mismatch")
    return wake


def _load_handoff_holder_binding(
    *,
    handoff_path: Path,
    holder_receipt_path: Path,
    closure_receipt_path: Path,
    holder_receipt: dict[str, Any],
    holder_receipt_bytes: bytes | None,
    holder_receipt_digest: str | None,
    require_return: bool,
    require_terminal_action: bool,
    handoff_snapshot: tuple[dict[str, Any], bytes, str] | None = None,
) -> tuple[dict[str, Any], bytes, str, dict[str, Any]]:
    """Load one immutable handoff and bind it to the exact holder receipt."""

    if handoff_snapshot is None:
        try:
            handoff_file = _regular_file(handoff_path, "handoff")
            handoff_bytes = handoff_file.read_bytes()
            handoff_digest = sha256_bytes(handoff_bytes)
            handoff_value = json.loads(handoff_bytes.decode("utf-8"))
        except (IncarnationHomeError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise IncarnationHomeError(
                "cannot read terminal return handoff snapshot"
            ) from exc
    else:
        handoff_value, handoff_bytes, handoff_digest = handoff_snapshot
        if sha256_bytes(handoff_bytes) != handoff_digest:
            raise IncarnationHomeError("terminal return handoff snapshot digest is invalid")
    if not isinstance(handoff_value, dict):
        raise IncarnationHomeError("handoff must be a JSON object")
    if require_return and handoff_value.get("responsibility_state") != "returned":
        raise IncarnationHomeError("handoff does not prove a returned responsibility")
    if require_return and handoff_value.get("terminal_status") not in {
        "completed",
        "blocked",
    }:
        raise IncarnationHomeError("handoff terminal status is not a bounded return status")
    runtime = handoff_value.get("runtime")
    responsibility_holder = (
        runtime.get("responsibility_holder") if isinstance(runtime, dict) else None
    )
    if not isinstance(responsibility_holder, dict):
        raise IncarnationHomeError("handoff lacks responsibility-holder binding")
    if require_terminal_action:
        terminal_action = responsibility_holder.get("terminal_action")
        if (
            not isinstance(terminal_action, dict)
            or terminal_action.get("action") != "close_exact_bound_holder"
            or terminal_action.get("required") is not True
        ):
            raise IncarnationHomeError(
                "handoff does not require the exact bound-holder terminal action"
            )
    holder_ref = str(holder_receipt_path.resolve())
    closure_ref = str(closure_receipt_path.resolve())
    if responsibility_holder.get("terminal_receipt") != holder_ref:
        raise IncarnationHomeError("handoff holder receipt identity mismatch")
    if responsibility_holder.get("closure_receipt") != closure_ref:
        raise IncarnationHomeError("handoff closure receipt identity mismatch")
    if holder_receipt_digest is None:
        try:
            holder_receipt_digest = sha256_bytes(
                holder_receipt_bytes
                if holder_receipt_bytes is not None
                else holder_receipt_path.read_bytes()
            )
        except OSError as exc:
            raise IncarnationHomeError("holder receipt could not be hashed") from exc
    if responsibility_holder.get("terminal_receipt_sha256") != holder_receipt_digest:
        raise IncarnationHomeError("handoff holder receipt digest mismatch")
    if responsibility_holder.get("holder_pid") != holder_receipt["holder"].get("pid"):
        raise IncarnationHomeError("handoff responsibility-holder PID mismatch")
    if responsibility_holder.get("terminal_pid") != holder_receipt["terminal"].get("pid"):
        raise IncarnationHomeError("handoff terminal PID mismatch")
    return handoff_value, handoff_bytes, handoff_digest, responsibility_holder


def _validate_join_completion(
    *,
    join_receipt_path: Path,
    handoff_path: Path,
    holder_receipt_path: Path,
    closure_receipt_path: Path,
    holder_receipt: dict[str, Any],
    holder_receipt_bytes: bytes | None = None,
    holder_receipt_digest: str | None = None,
    handoff_snapshot: tuple[dict[str, Any], bytes, str] | None = None,
) -> dict[str, Any]:
    """Validate a non-waking terminal join and its required close action."""

    join = _load_json(join_receipt_path, "terminal join receipt")
    if join.get("schema_version") != TERMINAL_JOIN_SCHEMA_VERSION:
        raise IncarnationHomeError("unsupported terminal join receipt schema")
    if join.get("join_ref") != str(join_receipt_path.resolve()):
        raise IncarnationHomeError("terminal join receipt path identity mismatch")
    return_value = join.get("return")
    if (
        not isinstance(return_value, dict)
        or return_value.get("status") != "returned"
        or return_value.get("validated") is not True
        or return_value.get("owner_acceptance") != "separate"
    ):
        raise IncarnationHomeError("terminal join does not prove a bounded returned responsibility")
    terminal_action = join.get("terminal_action")
    if (
        not isinstance(terminal_action, dict)
        or terminal_action.get("action") != "close_exact_bound_holder"
        or terminal_action.get("required") is not True
    ):
        raise IncarnationHomeError(
            "terminal join does not require the exact bound-holder terminal action"
        )
    _, _, handoff_digest, _ = _load_handoff_holder_binding(
        handoff_path=handoff_path,
        holder_receipt_path=holder_receipt_path,
        closure_receipt_path=closure_receipt_path,
        holder_receipt=holder_receipt,
        holder_receipt_bytes=holder_receipt_bytes,
        holder_receipt_digest=holder_receipt_digest,
        require_return=True,
        require_terminal_action=True,
        handoff_snapshot=handoff_snapshot,
    )
    if join.get("handoff_ref") != str(handoff_path.resolve()):
        raise IncarnationHomeError("terminal join handoff identity mismatch")
    if join.get("handoff_sha256") != handoff_digest:
        raise IncarnationHomeError("terminal join handoff digest mismatch")
    holder_digest = holder_receipt_digest or sha256_bytes(
        holder_receipt_bytes
        if holder_receipt_bytes is not None
        else holder_receipt_path.read_bytes()
    )
    if join.get("holder_receipt_ref") != str(holder_receipt_path.resolve()):
        raise IncarnationHomeError("terminal join holder receipt identity mismatch")
    if join.get("holder_receipt_sha256") != holder_digest:
        raise IncarnationHomeError("terminal join holder receipt digest mismatch")
    if join.get("closure_receipt_ref") != str(closure_receipt_path.resolve()):
        raise IncarnationHomeError("terminal join closure receipt identity mismatch")
    holder_pid, _, kitty_pid, _ = _holder_receipt_process_ids(holder_receipt)
    if join.get("holder_pid") != holder_pid:
        raise IncarnationHomeError("terminal join holder PID mismatch")
    if join.get("terminal_pid") != kitty_pid:
        raise IncarnationHomeError("terminal join terminal PID mismatch")
    return join


def _validate_closure_authorization(
    *,
    authorization_path: Path,
    handoff_path: Path,
    holder_receipt_path: Path,
    closure_receipt_path: Path,
    holder_receipt: dict[str, Any],
    holder_receipt_bytes: bytes,
    holder_receipt_digest: str,
    authorization_snapshot: tuple[dict[str, Any], bytes] | None = None,
    handoff_snapshot: tuple[dict[str, Any], bytes, str] | None = None,
) -> dict[str, Any]:
    """Validate typed wake-delivered or join-completed close authority."""

    authorization = (
        _load_json(authorization_path, "terminal closure authorization")
        if authorization_snapshot is None
        else authorization_snapshot[0]
    )
    if authorization.get("schema_version") != CLOSURE_AUTHORIZATION_SCHEMA_VERSION:
        raise IncarnationHomeError("unsupported terminal closure authorization schema")
    if authorization.get("authorization_ref") != str(authorization_path.resolve()):
        raise IncarnationHomeError("terminal closure authorization path identity mismatch")
    if authorization.get("handoff_ref") != str(handoff_path.resolve()):
        raise IncarnationHomeError("terminal closure authorization handoff identity mismatch")
    if authorization.get("holder_receipt_ref") != str(holder_receipt_path.resolve()):
        raise IncarnationHomeError(
            "terminal closure authorization holder receipt identity mismatch"
        )
    if authorization.get("holder_receipt_sha256") != holder_receipt_digest:
        raise IncarnationHomeError(
            "terminal closure authorization holder receipt digest mismatch"
        )
    if authorization.get("closure_receipt_ref") != str(closure_receipt_path.resolve()):
        raise IncarnationHomeError(
            "terminal closure authorization closure receipt identity mismatch"
        )
    _, _, handoff_digest, _ = _load_handoff_holder_binding(
        handoff_path=handoff_path,
        holder_receipt_path=holder_receipt_path,
        closure_receipt_path=closure_receipt_path,
        holder_receipt=holder_receipt,
        holder_receipt_bytes=holder_receipt_bytes,
        holder_receipt_digest=holder_receipt_digest,
        require_return=True,
        require_terminal_action=True,
        handoff_snapshot=handoff_snapshot,
    )
    if authorization.get("handoff_sha256") != handoff_digest:
        raise IncarnationHomeError(
            "terminal closure authorization handoff digest mismatch"
        )
    if authorization.get("return_status") != "returned":
        raise IncarnationHomeError("terminal closure authorization lacks returned status")
    terminal_action = authorization.get("terminal_action")
    if (
        not isinstance(terminal_action, dict)
        or terminal_action.get("action") != "close_exact_bound_holder"
        or terminal_action.get("required") is not True
        or terminal_action.get("authorized") is not True
    ):
        raise IncarnationHomeError(
            "terminal closure authorization does not authorize the exact bound-holder action"
        )
    holder_pid, _, kitty_pid, _ = _holder_receipt_process_ids(holder_receipt)
    if authorization.get("holder_pid") != holder_pid:
        raise IncarnationHomeError("terminal closure authorization holder PID mismatch")
    if authorization.get("terminal_pid") != kitty_pid:
        raise IncarnationHomeError("terminal closure authorization terminal PID mismatch")
    evidence_ref = authorization.get("evidence_ref")
    evidence_digest = authorization.get("evidence_sha256")
    if not isinstance(evidence_ref, str) or not evidence_ref.startswith("/"):
        raise IncarnationHomeError("terminal closure authorization evidence is incomplete")
    if not isinstance(evidence_digest, str) or not SHA256_DIGEST_PATTERN.fullmatch(
        evidence_digest
    ):
        raise IncarnationHomeError("terminal closure authorization evidence digest is invalid")
    evidence_path = _regular_file(Path(evidence_ref), "terminal closure evidence")
    if sha256_bytes(evidence_path.read_bytes()) != evidence_digest:
        raise IncarnationHomeError(
            "terminal closure authorization evidence digest mismatch"
        )
    kind = authorization.get("authorization_kind")
    if kind == "join_completed":
        if authorization.get("join_receipt_ref") != evidence_ref:
            raise IncarnationHomeError("terminal closure authorization join evidence mismatch")
        _validate_join_completion(
            join_receipt_path=evidence_path,
            handoff_path=handoff_path,
            holder_receipt_path=holder_receipt_path,
            closure_receipt_path=closure_receipt_path,
            holder_receipt=holder_receipt,
            holder_receipt_bytes=holder_receipt_bytes,
            holder_receipt_digest=holder_receipt_digest,
            handoff_snapshot=handoff_snapshot,
        )
    elif kind == "wake_delivered":
        if authorization.get("wake_receipt_ref") != evidence_ref:
            raise IncarnationHomeError("terminal closure authorization wake evidence mismatch")
        _validate_wake_delivery(
            wake_receipt_path=evidence_path,
            handoff_path=handoff_path,
            holder_receipt_path=holder_receipt_path,
            closure_receipt_path=closure_receipt_path,
            holder_receipt=holder_receipt,
            holder_receipt_bytes=holder_receipt_bytes,
            holder_receipt_digest=holder_receipt_digest,
            handoff_snapshot=handoff_snapshot,
        )
    else:
        raise IncarnationHomeError("unsupported terminal closure authorization kind")
    return authorization


def _load_holder_receipt_snapshot(
    path: Path,
    *,
    snapshot: tuple[dict[str, Any], bytes] | None = None,
) -> tuple[dict[str, Any], bytes, str]:
    receipt, raw = snapshot or _load_json_snapshot(path, "holder terminal receipt")
    if receipt.get("schema_version") != HOLDER_RECEIPT_SCHEMA_VERSION:
        raise IncarnationHomeError("unsupported holder terminal receipt schema")
    if receipt.get("receipt_ref") != str(path.resolve()):
        raise IncarnationHomeError("holder receipt path identity mismatch")
    if receipt.get("lifecycle_role") != "responsibility_holder":
        raise IncarnationHomeError("holder receipt is not a responsibility-holder receipt")
    boot_id = receipt.get("boot_id")
    if not isinstance(boot_id, str) or not BOOT_ID_PATTERN.fullmatch(boot_id):
        raise IncarnationHomeError("holder terminal receipt is incomplete")
    holder = receipt.get("holder")
    runtime = receipt.get("runtime")
    terminal = receipt.get("terminal")
    required_holder = {
        "pid",
        "start_ticks",
        "parent_pid",
        "parent_start_ticks",
        "parent_comm",
        "argv",
        "argv_digest",
    }
    required_runtime = {
        "codex_executable",
        "codex_executable_digest",
        "incarnation_manifest",
        "incarnation_manifest_digest",
        "model",
        "reasoning_effort",
        "ambient_codex_home",
        "incarnation_codex_home",
    }
    if (
        not isinstance(holder, dict)
        or not required_holder <= holder.keys()
        or not isinstance(runtime, dict)
        or not required_runtime <= runtime.keys()
        or not isinstance(terminal, dict)
        or terminal.get("binding") != "kitty_ancestor_at_exec"
        or terminal.get("required_comm") != "kitty"
        or not _positive_int(terminal.get("pid"))
        or not _positive_int(terminal.get("start_ticks"))
        or not isinstance(terminal.get("argv"), list)
        or not all(isinstance(item, str) for item in terminal["argv"])
        or not isinstance(terminal.get("window_id"), str)
        or not re.fullmatch(r"[1-9][0-9]*", terminal["window_id"])
        or terminal.get("dedicated") is not True
        or not isinstance(holder.get("argv"), list)
        or not all(isinstance(item, str) for item in holder["argv"])
    ):
        raise IncarnationHomeError("holder terminal receipt is incomplete")
    replacement_reentry = receipt.get("replacement_reentry")
    post_exec_rebound = "exe_digest" in holder and not any(
        key in holder
        for key in ("pre_exec_argv", "pre_exec_argv_digest", "pre_exec_exe_digest")
    )
    if post_exec_rebound and replacement_reentry is None:
        raise IncarnationHomeError(
            "post-exec rebound holder receipt requires replacement_reentry provenance"
        )
    if replacement_reentry is not None:
        _validate_replacement_reentry_binding(
            replacement_reentry,
            holder=holder,
        )
    pre_exec_argv = holder.get("pre_exec_argv")
    pre_exec_argv_digest = holder.get("pre_exec_argv_digest")
    pre_exec_exe_digest = holder.get("pre_exec_exe_digest")
    if (
        pre_exec_argv is not None
        or pre_exec_argv_digest is not None
        or pre_exec_exe_digest is not None
    ):
        if (
            not isinstance(pre_exec_argv, list)
            or not pre_exec_argv
            or not all(isinstance(item, str) for item in pre_exec_argv)
            or not isinstance(pre_exec_argv_digest, str)
            or pre_exec_argv_digest != sha256_bytes(canonical_bytes(pre_exec_argv))
            or not isinstance(pre_exec_exe_digest, str)
            or SHA256_DIGEST_PATTERN.fullmatch(pre_exec_exe_digest) is None
        ):
            raise IncarnationHomeError("holder pre-exec identity is invalid")
    holder_exe_digest = holder.get("exe_digest")
    if holder_exe_digest is not None and (
        not isinstance(holder_exe_digest, str)
        or SHA256_DIGEST_PATTERN.fullmatch(holder_exe_digest) is None
    ):
        raise IncarnationHomeError("holder executable identity is invalid")
    _decode_holder_manifest_snapshot(runtime)
    if "binding" in receipt:
        binding = _validate_terminal_binding_shape(receipt["binding"])
        _validate_receipt_binding_consistency(receipt, binding)
    return receipt, raw, sha256_bytes(raw)


def _load_holder_receipt(path: Path) -> dict[str, Any]:
    return _load_holder_receipt_snapshot(path)[0]


def _holder_receipt_process_ids(
    receipt: dict[str, Any],
) -> tuple[int, int, int, int]:
    boot_id = receipt.get("boot_id")
    if not isinstance(boot_id, str) or not BOOT_ID_PATTERN.fullmatch(boot_id):
        raise IncarnationHomeError("holder kernel boot identity is invalid")
    if boot_id != _proc_boot_id():
        raise IncarnationHomeError("holder kernel boot identity has drifted")
    holder = receipt["holder"]
    terminal = receipt["terminal"]
    pid = holder.get("pid")
    start_ticks = holder.get("start_ticks")
    parent_pid = holder.get("parent_pid")
    parent_start_ticks = holder.get("parent_start_ticks")
    kitty_pid = terminal.get("pid")
    kitty_start_ticks = terminal.get("start_ticks")
    if not all(
        _positive_int(value)
        for value in (pid, start_ticks, parent_pid, parent_start_ticks)
    ):
        raise IncarnationHomeError("holder process identity is invalid")
    if not _positive_int(kitty_pid, minimum=2):
        raise IncarnationHomeError("holder Kitty identity is invalid")
    if not _positive_int(kitty_start_ticks):
        raise IncarnationHomeError("holder Kitty identity is invalid")
    expected_argv = holder["argv"]
    if holder.get("argv_digest") != sha256_bytes(canonical_bytes(expected_argv)):
        raise IncarnationHomeError("holder argv digest is invalid")
    return pid, start_ticks, kitty_pid, kitty_start_ticks


def _holder_terminal_identity(
    receipt: dict[str, Any],
) -> tuple[int, int, str, str, bool]:
    runtime = receipt["runtime"]
    pid, kitty_pid, kitty_comm, window_id, dedicated = _validate_holder_process_identity(
        receipt,
        expected_argv=receipt["holder"]["argv"],
        argv_label="holder",
        receipt_bound_terminal=True,
    )
    # Repaired receipts bind the exact payload digests before the private
    # execution mount is entered.  The recorded host paths are provenance only
    # after launch; reopening them here would make close depend on mutable
    # package lifetime and could strand an otherwise valid holder.
    manifest_snapshot = _decode_holder_manifest_snapshot(runtime)
    executable_path = Path(str(runtime["codex_executable"]))
    executable_digest = runtime.get("codex_executable_digest")
    if (
        not executable_path.is_absolute()
        or executable_path.name in {"", ".", ".."}
        or not isinstance(executable_digest, str)
        or not SHA256_DIGEST_PATTERN.fullmatch(executable_digest)
    ):
        raise IncarnationHomeError("holder Codex executable binding is incomplete")
    if manifest_snapshot is None:
        executable = _regular_file(executable_path, "holder Codex executable")
        if sha256_bytes(executable.read_bytes()) != executable_digest:
            raise IncarnationHomeError("holder Codex executable digest has drifted")
    companion = runtime.get("codex_companion")
    if companion is not None:
        if not isinstance(companion, dict):
            raise IncarnationHomeError("holder Codex companion binding is incomplete")
        companion_path = companion.get("path")
        companion_digest = companion.get("digest")
        expected_companion = executable_path.parent / CODE_MODE_HOST_NAME
        companion_relative = companion.get("package_relative")
        if (
            companion_path != str(expected_companion)
            or companion.get("relation") != "adjacent_immutable_package"
            or not isinstance(companion_relative, str)
            or not companion_relative
            or Path(companion_relative).is_absolute()
            or ".." in Path(companion_relative).parts
            or Path(companion_relative).name != CODE_MODE_HOST_NAME
            or not isinstance(companion_digest, str)
            or not SHA256_DIGEST_PATTERN.fullmatch(companion_digest)
        ):
            raise IncarnationHomeError("holder Codex companion binding has drifted")
        if manifest_snapshot is None:
            expected_companion_relative = expected_companion.relative_to(
                _package_root(executable)
            ).as_posix()
            if companion_relative != expected_companion_relative:
                raise IncarnationHomeError("holder Codex companion binding has drifted")
            companion_file = _regular_file(
                expected_companion, "holder Codex companion"
            )
            if sha256_bytes(companion_file.read_bytes()) != companion_digest:
                raise IncarnationHomeError("holder Codex companion digest has drifted")
    if manifest_snapshot is None:
        # Legacy receipts predate the holder-bound snapshot.  Preserve their
        # old fail-closed behavior; repaired receipts never take this branch.
        manifest = _regular_file(
            Path(str(runtime["incarnation_manifest"])), "holder incarnation manifest"
        )
        if sha256_bytes(manifest.read_bytes()) != runtime.get(
            "incarnation_manifest_digest"
        ):
            raise IncarnationHomeError("holder incarnation manifest digest has drifted")
    return pid, kitty_pid, kitty_comm, window_id, dedicated


def _validate_holder_process_identity(
    receipt: dict[str, Any],
    *,
    expected_argv: Sequence[str],
    argv_label: str,
    expected_exe_digest: str | None = None,
    receipt_bound_terminal: bool = False,
) -> tuple[int, int, str, str, bool]:
    """Validate one exact holder process before or after its payload exec."""

    holder = receipt["holder"]
    terminal = receipt["terminal"]
    pid, start_ticks, kitty_pid, kitty_start_ticks = _holder_receipt_process_ids(
        receipt
    )
    parent_pid = holder["parent_pid"]
    parent_start_ticks = holder["parent_start_ticks"]
    if _proc_start_ticks(pid) != start_ticks:
        raise IncarnationHomeError("holder PID was reused or has drifted")
    if _proc_start_ticks(parent_pid) != parent_start_ticks:
        raise IncarnationHomeError("holder terminal parent PID was reused or has drifted")
    if _proc_parent_pid(pid) != parent_pid:
        raise IncarnationHomeError("holder parent identity has changed")
    if _proc_comm(parent_pid) != holder.get("parent_comm"):
        raise IncarnationHomeError("holder process parent identity has drifted")
    if _proc_argv(pid) != list(expected_argv):
        raise IncarnationHomeError(f"{argv_label} argv identity has drifted")
    if expected_exe_digest is None:
        expected_exe_digest = holder.get("exe_digest")
    if expected_exe_digest is not None:
        if not isinstance(expected_exe_digest, str) or not SHA256_DIGEST_PATTERN.fullmatch(
            expected_exe_digest
        ):
            raise IncarnationHomeError(f"{argv_label} executable identity is invalid")
        if _proc_exe_digest(pid) != expected_exe_digest:
            raise IncarnationHomeError(f"{argv_label} executable identity has drifted")
    if _proc_start_ticks(kitty_pid) != kitty_start_ticks:
        raise IncarnationHomeError("holder Kitty PID was reused or has drifted")
    if _proc_comm(kitty_pid) != "kitty":
        raise IncarnationHomeError("holder terminal is not Kitty")
    if _proc_argv(kitty_pid) != terminal["argv"]:
        raise IncarnationHomeError("holder Kitty argv identity has drifted")
    cursor = pid
    visited: set[int] = set()
    terminal_found = False
    for _ in range(64):
        current_parent_pid = _proc_parent_pid(cursor)
        if current_parent_pid <= 1 or current_parent_pid in visited:
            break
        visited.add(current_parent_pid)
        if current_parent_pid == kitty_pid:
            terminal_found = True
            break
        cursor = current_parent_pid
    if not terminal_found:
        raise IncarnationHomeError("holder Kitty terminal is no longer an ancestor")
    if receipt_bound_terminal:
        window_id, dedicated = _kitty_dedication_from_receipt(
            receipt=receipt,
            holder_pid=pid,
            kitty_pid=kitty_pid,
            terminal_argv=terminal["argv"],
        )
    else:
        window_id, dedicated = _kitty_dedication(
            holder_pid=pid,
            kitty_pid=kitty_pid,
            terminal_argv=terminal["argv"],
        )
    recorded_window_id = terminal.get("window_id")
    if recorded_window_id is not None and recorded_window_id != window_id:
        raise IncarnationHomeError("holder Kitty window identity has drifted")
    if terminal.get("dedicated") is not None and terminal.get("dedicated") is not dedicated:
        raise IncarnationHomeError("holder Kitty dedication proof has drifted")
    return pid, kitty_pid, _proc_comm(kitty_pid), window_id, dedicated


def _holder_pre_exec_identity(
    receipt: dict[str, Any], *, expected_argv: Sequence[str]
) -> tuple[int, int, str, str, bool]:
    """Prove the receipt still belongs to the exact payload helper pre-exec."""

    holder = receipt["holder"]
    recorded_argv = holder.get("pre_exec_argv")
    recorded_digest = holder.get("pre_exec_argv_digest")
    recorded_exe_digest = holder.get("pre_exec_exe_digest")
    if (
        not isinstance(recorded_argv, list)
        or not recorded_argv
        or not all(isinstance(item, str) for item in recorded_argv)
        or not isinstance(recorded_digest, str)
        or recorded_digest != sha256_bytes(canonical_bytes(recorded_argv))
        or not isinstance(recorded_exe_digest, str)
        or SHA256_DIGEST_PATTERN.fullmatch(recorded_exe_digest) is None
    ):
        raise IncarnationHomeError("holder pre-exec identity is missing")
    if recorded_argv != list(expected_argv):
        raise IncarnationHomeError("holder pre-exec helper argv binding has drifted")
    return _validate_holder_process_identity(
        receipt,
        expected_argv=recorded_argv,
        argv_label="holder pre-exec helper",
        expected_exe_digest=recorded_exe_digest,
    )


def _load_terminal_binding_input(
    *,
    binding_path: Path | None,
    holder_receipt_path: Path | None,
    context_path: Path | None,
    harden_socket: bool,
    allow_missing_socket: bool = False,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], Path | None, str | None]:
    if (binding_path is None) == (holder_receipt_path is None):
        raise IncarnationHomeError(
            "provide exactly one terminal binding or holder receipt"
        )
    if binding_path is not None:
        binding_document, raw = _load_json_snapshot(
            binding_path, "terminal binding"
        )
        if binding_document.get("schema_version") != TERMINAL_BINDING_SCHEMA_VERSION:
            raise IncarnationHomeError("unsupported terminal binding schema")
        binding = _validate_terminal_binding_shape(binding_document["binding"])
        holder = binding.get("holder")
        terminal = binding.get("terminal")
        if not isinstance(holder, dict) or not isinstance(terminal, dict):
            raise IncarnationHomeError("terminal binding process records are missing")
        if binding["boot_id"] != _proc_boot_id():
            raise IncarnationHomeError("terminal binding kernel boot identity has drifted")
        socket_record = terminal["control_socket"]
        assert isinstance(socket_record, dict)
        _secure_control_socket(
            str(socket_record["address"]),
            harden=harden_socket,
            require_exists=not allow_missing_socket,
            expected_device=socket_record["device"],
            expected_inode=socket_record["inode"],
        )
        return (
            binding,
            holder,
            terminal,
            binding_path,
            sha256_bytes(raw),
        )

    assert holder_receipt_path is not None
    receipt, raw = _load_json_snapshot(
        holder_receipt_path, "holder terminal receipt"
    )
    source_digest = sha256_bytes(raw)
    schema = receipt.get("schema_version")
    holder = receipt.get("holder")
    terminal = receipt.get("terminal")
    if not isinstance(holder, dict) or not isinstance(terminal, dict):
        raise IncarnationHomeError("holder receipt process records are missing")
    if schema == HOLDER_RECEIPT_SCHEMA_VERSION:
        receipt, raw, source_digest = _load_holder_receipt_snapshot(
            holder_receipt_path, snapshot=(receipt, raw)
        )
        if receipt["boot_id"] != _proc_boot_id():
            raise IncarnationHomeError(
                "holder terminal receipt kernel boot identity has drifted"
            )
        binding_value = receipt.get("binding")
        if binding_value is not None:
            binding = _validate_terminal_binding_shape(binding_value)
            if binding["boot_id"] != receipt["boot_id"]:
                raise IncarnationHomeError(
                    "holder terminal binding boot identity has drifted"
                )
            terminal_binding = binding["terminal"]
            assert isinstance(terminal_binding, dict)
            socket_record = terminal_binding["control_socket"]
            assert isinstance(socket_record, dict)
            _secure_control_socket(
                str(socket_record["address"]),
                harden=harden_socket,
                require_exists=not allow_missing_socket,
                expected_device=socket_record["device"],
                expected_inode=socket_record["inode"],
            )
            return binding, binding["holder"], terminal_binding, holder_receipt_path, source_digest  # type: ignore[return-value]
    elif schema != "task_local_observable_external_cli_holder_v1":
        raise IncarnationHomeError("unsupported holder terminal receipt schema")

    if context_path is None:
        raise IncarnationHomeError(
            "legacy holder receipt requires an explicit terminal binding context"
        )
    context = _load_binding_context(context_path)
    socket_address = terminal.get("listen_on")
    if not isinstance(socket_address, str):
        socket_address = terminal.get("control_socket")
    window_id = terminal.get("kitty_window_id", terminal.get("window_id"))
    title = terminal.get("title", "")
    tty = terminal.get("tty")
    terminal_pid = terminal.get("pid")
    terminal_start_ticks = terminal.get("start_ticks")
    holder_pid = holder.get("pid")
    holder_start_ticks = holder.get("start_ticks")
    if (
        not isinstance(socket_address, str)
        or (
            not isinstance(window_id, str)
            and type(window_id) is not int
        )
        or not isinstance(title, str)
        or not isinstance(tty, str)
        or not all(
            _positive_int(value)
            for value in (
                terminal_pid,
                terminal_start_ticks,
                holder_pid,
                holder_start_ticks,
            )
        )
    ):
        raise IncarnationHomeError("legacy holder receipt lacks a complete binding")
    legacy_argv = terminal.get("argv")
    if not isinstance(legacy_argv, list) or not all(
        isinstance(item, str) for item in legacy_argv
    ):
        raise IncarnationHomeError("legacy holder receipt lacks terminal argv")
    holder_argv = holder.get("argv")
    holder_parent_pid = holder.get("parent_pid")
    holder_parent_start_ticks = holder.get("parent_start_ticks")
    holder_parent_comm = holder.get("parent_comm")
    if (
        not isinstance(holder_argv, list)
        or not all(isinstance(item, str) for item in holder_argv)
        or not _positive_int(holder_parent_pid)
        or not _positive_int(holder_parent_start_ticks)
        or not isinstance(holder_parent_comm, str)
        or not holder_parent_comm
    ):
        raise IncarnationHomeError(
            "legacy holder receipt lacks holder process identity"
        )
    _validate_legacy_holder_process_identity(
        holder_pid=holder_pid,
        holder_start_ticks=holder_start_ticks,
        holder_parent_pid=holder_parent_pid,
        holder_parent_start_ticks=holder_parent_start_ticks,
        holder_parent_comm=holder_parent_comm,
        holder_argv=holder_argv,
        kitty_pid=terminal_pid,
        kitty_start_ticks=terminal_start_ticks,
        kitty_argv=legacy_argv,
    )
    observed_window_id, dedicated = _kitty_dedication(
        holder_pid=holder_pid,
        kitty_pid=terminal_pid,
        terminal_argv=legacy_argv,
    )
    if observed_window_id != str(window_id) or not dedicated:
        raise IncarnationHomeError("legacy holder terminal dedication could not be proved")
    binding = _terminal_binding(
        context=context,
        control_socket=socket_address,
        terminal_title=title,
        window_id=str(window_id),
        tty=tty,
        holder_pid=holder_pid,
        holder_start_ticks=holder_start_ticks,
        holder_argv_digest=sha256_bytes(canonical_bytes(holder_argv)),
        holder_exe_digest=_proc_exe_digest(holder_pid),
        terminal_pid=terminal_pid,
        terminal_start_ticks=terminal_start_ticks,
        source_receipt=holder_receipt_path,
        source_receipt_digest=source_digest,
        harden_socket=harden_socket,
    )
    binding_holder = binding["holder"]
    binding_terminal = binding["terminal"]
    assert isinstance(binding_holder, dict) and isinstance(binding_terminal, dict)
    return binding, binding_holder, binding_terminal, holder_receipt_path, source_digest


def _observe_terminal_binding(
    *,
    binding: dict[str, object],
    holder: dict[str, object],
    terminal: dict[str, object],
    kitty_executable: str,
) -> tuple[dict[str, object], str]:
    holder_pid = holder["pid"]
    holder_start_ticks = holder["start_ticks"]
    terminal_pid = terminal["pid"]
    terminal_start_ticks = terminal["start_ticks"]
    assert isinstance(holder_pid, int) and isinstance(holder_start_ticks, int)
    assert isinstance(terminal_pid, int) and isinstance(terminal_start_ticks, int)
    holder_state = _proc_identity_state(holder_pid, holder_start_ticks)
    terminal_state = _proc_identity_state(terminal_pid, terminal_start_ticks)
    terminal_comm = "unknown"
    identity_state = "live"
    if holder_state == "drifted" or terminal_state == "drifted":
        identity_state = "stale"
    elif holder_state == "gone" or terminal_state == "gone":
        identity_state = "missing"
    if identity_state == "live":
        holder_argv_digest = holder.get("argv_digest")
        if (
            not isinstance(holder_argv_digest, str)
            or SHA256_DIGEST_PATTERN.fullmatch(holder_argv_digest) is None
        ):
            identity_state = "stale"
        else:
            try:
                observed_holder_argv = _proc_argv(holder_pid)
            except IncarnationHomeError:
                holder_state = _proc_identity_state(holder_pid, holder_start_ticks)
                terminal_state = _proc_identity_state(
                    terminal_pid, terminal_start_ticks
                )
                if "drifted" in {holder_state, terminal_state}:
                    identity_state = "stale"
                elif "gone" in {holder_state, terminal_state}:
                    identity_state = "missing"
                else:
                    identity_state = "stale"
            else:
                if sha256_bytes(canonical_bytes(observed_holder_argv)) != holder_argv_digest:
                    identity_state = "stale"

    if identity_state == "live":
        holder_exe_digest = holder.get("exe_digest")
        if (
            not isinstance(holder_exe_digest, str)
            or SHA256_DIGEST_PATTERN.fullmatch(holder_exe_digest) is None
        ):
            identity_state = "stale"
        else:
            try:
                observed_holder_exe_digest = _proc_exe_digest(holder_pid)
            except IncarnationHomeError:
                holder_state = _proc_identity_state(holder_pid, holder_start_ticks)
                terminal_state = _proc_identity_state(
                    terminal_pid, terminal_start_ticks
                )
                if "drifted" in {holder_state, terminal_state}:
                    identity_state = "stale"
                elif "gone" in {holder_state, terminal_state}:
                    identity_state = "missing"
                else:
                    identity_state = "stale"
            else:
                if observed_holder_exe_digest != holder_exe_digest:
                    identity_state = "stale"

    if identity_state == "live":
        try:
            terminal_comm = _proc_comm(terminal_pid)
            if terminal_comm != "kitty" or not _descends_from(
                holder_pid, terminal_pid
            ):
                identity_state = "stale"
        except IncarnationHomeError:
            holder_state = _proc_identity_state(holder_pid, holder_start_ticks)
            terminal_state = _proc_identity_state(terminal_pid, terminal_start_ticks)
            if "drifted" in {holder_state, terminal_state}:
                identity_state = "stale"
            elif "gone" in {holder_state, terminal_state}:
                identity_state = "missing"
            else:
                raise

    kitty_projection: dict[str, object] | None = None
    kitty_query_state = "not_attempted"
    if identity_state == "live":
        try:
            observed_window_id, dedicated = _kitty_dedication(
                holder_pid=holder_pid,
                kitty_pid=terminal_pid,
                terminal_argv=_proc_argv(terminal_pid),
            )
        except IncarnationHomeError:
            holder_state = _proc_identity_state(holder_pid, holder_start_ticks)
            terminal_state = _proc_identity_state(terminal_pid, terminal_start_ticks)
            if "drifted" in {holder_state, terminal_state}:
                identity_state = "stale"
            elif "gone" in {holder_state, terminal_state}:
                identity_state = "missing"
            else:
                identity_state = "stale"
        else:
            if observed_window_id != str(terminal["window_id"]) or not dedicated:
                identity_state = "stale"

    if identity_state == "live":
        socket_record = terminal["control_socket"]
        assert isinstance(socket_record, dict)
        try:
            matches = _kitty_ls(
                kitty_executable=kitty_executable,
                control_socket=str(socket_record["address"]),
                window_id=str(terminal["window_id"]),
                expected_device=socket_record["device"],
                expected_inode=socket_record["inode"],
            )
        except IncarnationHomeError:
            kitty_query_state = "unknown"
        else:
            if matches:
                kitty_projection = matches[0]
                kitty_query_state = "present"
            else:
                kitty_query_state = "missing"
                identity_state = "missing"
    elif identity_state == "missing":
        kitty_query_state = "not_available_after_exit"

    safe_binding = _safe_terminal_binding_projection(binding)
    safe_terminal = safe_binding.get("terminal")
    if not isinstance(safe_terminal, dict):
        raise IncarnationHomeError("terminal binding projection lacks terminal data")
    status: dict[str, object] = {
        "schema_version": TERMINAL_BINDING_SCHEMA_VERSION,
        "observation": {
            "state": identity_state,
            "mode": "read_only",
            "desktop_effect": "none",
            "kitty_query": kitty_query_state,
        },
        "binding": safe_binding,
        "processes": {
            "holder": {
                "pid": holder_pid,
                "start_ticks": holder_start_ticks,
                "state": holder_state,
            },
            "kitty": {
                "pid": terminal_pid,
                "start_ticks": terminal_start_ticks,
                "state": terminal_state,
                "comm": terminal_comm if terminal_state == "live" else "unknown",
            },
        },
        "terminal": {
            "exists": (
                True
                if kitty_query_state == "present"
                else False
                if kitty_query_state in {"missing", "not_available_after_exit"}
                else None
            ),
            "window_id": safe_terminal["window_id"],
            "tty": safe_terminal["tty"],
            "title": safe_terminal["title"],
            "kitty": kitty_projection,
        },
        "compositor": {
            "visibility": "unknown",
            "reason": "owner evidence does not prove compositor visibility",
        },
        "claim_limits": [
            "Kitty control-plane state is observed directly through the bound socket.",
            "Compositor visibility remains unknown.",
            "This read-only observation does not prove A2A responsibility or owner acceptance.",
        ],
    }
    _assert_safe_projection(status)
    return status, identity_state


def _write_terminal_binding(
    *,
    output_path: Path,
    binding: dict[str, object],
    holder: dict[str, object],
    terminal: dict[str, object],
    source_receipt: Path,
    source_digest: str,
) -> dict[str, object]:
    safe_binding = _safe_terminal_binding_projection(binding)
    safe_holder = _safe_projection_value(holder, "terminal binding holder")
    safe_terminal = _safe_projection_value(terminal, "terminal binding terminal")
    if not isinstance(safe_holder, dict) or not isinstance(safe_terminal, dict):
        raise IncarnationHomeError("terminal binding process projection is invalid")
    document: dict[str, object] = {
        "schema_version": TERMINAL_BINDING_SCHEMA_VERSION,
        "created_at": _utc_now(),
        "source_receipt": {
            "path": _safe_source_receipt_path(source_receipt),
            "sha256": source_digest,
        },
        "binding": safe_binding,
        "holder": safe_holder,
        "terminal": safe_terminal,
    }
    _assert_safe_projection(document)
    _write_new_json(output_path, document, "terminal binding")
    return document


def _require_unoccupied_receipt_path(path: Path) -> None:
    """Reject a stale or competing receipt before detached launch."""

    if not path.is_absolute() or path.is_symlink():
        raise IncarnationHomeError(
            f"holder terminal receipt must be an absolute non-symlink path: {path}"
        )
    if path.exists():
        raise IncarnationHomeError(
            f"holder terminal receipt path is already occupied: {path}"
        )
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise IncarnationHomeError(
            f"holder terminal receipt parent must be a real directory: {path.parent}"
        )


def _validate_launch_gate_path(path: Path) -> None:
    """Validate the stable path used for one detached launch admission."""

    if not path.is_absolute() or path.is_symlink():
        raise IncarnationHomeError(
            f"visible launch admission gate must be an absolute non-symlink path: {path}"
        )
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise IncarnationHomeError(
            f"visible launch admission gate parent must be a real directory: {path.parent}"
        )
    _validate_owner_private_parent(path, "visible launch admission gate")


def _require_unoccupied_launch_gate_path(path: Path) -> None:
    """Validate the one-shot parent admission gate before detached launch."""

    _validate_launch_gate_path(path)
    if path.exists():
        raise IncarnationHomeError(
            f"visible launch admission gate is already occupied: {path}"
        )


def _write_visible_launch_gate(
    *,
    gate_path: Path,
    holder_receipt_path: Path,
    token: str,
    decision: str,
) -> None:
    """Publish the parent decision that releases or rejects a detached payload."""

    if decision not in {"admit", "reject"}:
        raise IncarnationHomeError("visible launch admission decision is invalid")
    if not isinstance(token, str) or not token:
        raise IncarnationHomeError("visible launch admission token is invalid")
    _write_new_json(
        gate_path,
        {
            "schema_version": VISIBLE_LAUNCH_GATE_SCHEMA_VERSION,
            "gate_ref": str(gate_path.resolve()),
            "holder_receipt_ref": str(holder_receipt_path.resolve()),
            "token": token,
            "decision": decision,
            "created_at": _utc_now(),
        },
        "visible launch admission gate",
    )


def _load_visible_launch_gate(
    *,
    gate_path: Path,
    holder_receipt_path: Path,
    token: str,
) -> dict[str, Any]:
    """Read back one exact parent admission decision."""

    _validate_launch_gate_path(gate_path)
    if not holder_receipt_path.is_absolute() or holder_receipt_path.is_symlink():
        raise IncarnationHomeError(
            "visible launch admission holder receipt path is not bound"
        )
    if not isinstance(token, str) or not token:
        raise IncarnationHomeError("visible launch admission token is invalid")
    gate, _gate_bytes = _load_json_snapshot(
        gate_path, "visible launch admission gate"
    )
    if gate.get("schema_version") != VISIBLE_LAUNCH_GATE_SCHEMA_VERSION:
        raise IncarnationHomeError("visible launch admission gate schema is unsupported")
    if gate.get("gate_ref") != str(gate_path.resolve()):
        raise IncarnationHomeError("visible launch admission gate path identity drifted")
    if gate.get("holder_receipt_ref") != str(holder_receipt_path.resolve()):
        raise IncarnationHomeError(
            "visible launch admission holder receipt identity drifted"
        )
    if gate.get("token") != token:
        raise IncarnationHomeError("visible launch admission token drifted")
    if gate.get("decision") not in {"admit", "reject"}:
        raise IncarnationHomeError("visible launch admission decision is invalid")
    return gate


def _confirm_visible_launch_admission(
    *,
    gate_path: Path,
    holder_receipt_path: Path,
    token: str,
) -> None:
    """Confirm that the durable parent decision is exactly ``admit``."""

    gate = _load_visible_launch_gate(
        gate_path=gate_path,
        holder_receipt_path=holder_receipt_path,
        token=token,
    )
    if gate.get("decision") != "admit":
        raise IncarnationHomeError("visible launch admission was not confirmed")


def _await_visible_launch_admission(
    *,
    gate_path: Path,
    holder_receipt_path: Path,
    token: str,
) -> None:
    """Wait for bounded parent admission before executing the private payload."""

    _validate_launch_gate_path(gate_path)
    if not holder_receipt_path.is_absolute() or holder_receipt_path.is_symlink():
        raise IncarnationHomeError(
            "visible launch admission holder receipt path is not bound"
        )
    if not isinstance(token, str) or not token:
        raise IncarnationHomeError("visible launch admission token is invalid")
    deadline = time.monotonic() + VISIBLE_LAUNCH_GATE_WAIT_SECONDS
    while True:
        if gate_path.exists() or gate_path.is_symlink():
            gate = _load_visible_launch_gate(
                gate_path=gate_path,
                holder_receipt_path=holder_receipt_path,
                token=token,
            )
            decision = gate.get("decision")
            if decision == "reject":
                raise IncarnationHomeError(
                    "visible launch admission was rejected before payload execution"
                )
            if decision == "admit":
                return
            raise IncarnationHomeError("visible launch admission decision is invalid")
        if time.monotonic() >= deadline:
            raise IncarnationHomeError(
                "visible launch admission timed out before payload execution"
            )
        time.sleep(VISIBLE_LAUNCH_GATE_POLL_SECONDS)


def _validate_visible_launch_receipt(
    *,
    receipt_path: Path,
    receipt: dict[str, Any],
    manifest_path: Path,
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    manifest_digest: str,
    executable: Path,
    executable_digest: str,
    binding_context: dict[str, str],
    holder_binding: dict[str, str],
    control_socket: str,
    terminal_title: str,
    companion_binding: dict[str, str] | None,
) -> dict[str, Any]:
    """Prove that the published receipt belongs to this exact launch."""

    expected_runtime: dict[str, object] = {
        "codex_executable": str(executable),
        "codex_executable_digest": executable_digest,
        "incarnation_manifest": str(manifest_path.resolve()),
        "incarnation_manifest_digest": manifest_digest,
        "incarnation_manifest_snapshot_b64": base64.b64encode(
            manifest_bytes
        ).decode("ascii"),
        "model": str(manifest["model_slug"]),
        "reasoning_effort": str(manifest["reasoning_effort"]),
        "ambient_codex_home": str(manifest["ambient_codex_home"]),
        "incarnation_codex_home": str(manifest["codex_home"]),
        "holder_binding": _validate_holder_binding_manifest_record(holder_binding),
    }
    if receipt.get("receipt_ref") != str(receipt_path.resolve()):
        raise IncarnationHomeError("visible launch receipt path identity drifted")
    runtime = receipt.get("runtime")
    if not isinstance(runtime, dict) or any(
        runtime.get(key) != value for key, value in expected_runtime.items()
    ):
        raise IncarnationHomeError(
            "visible launch receipt runtime identity does not match this launch"
        )
    if companion_binding is None:
        if "codex_companion" in runtime:
            raise IncarnationHomeError(
                "visible launch receipt unexpectedly contains a Codex companion"
            )
    elif runtime.get("codex_companion") != companion_binding:
        raise IncarnationHomeError(
            "visible launch receipt Codex companion identity drifted"
        )

    binding_value = receipt.get("binding")
    binding = _validate_terminal_binding_shape(binding_value)
    _validate_receipt_binding_consistency(receipt, binding)
    for key in TERMINAL_BINDING_CONTEXT_FIELDS:
        value = binding_context[key]
        if binding.get(key) != value:
            raise IncarnationHomeError(
                f"visible launch receipt binding context drifted: {key}"
            )
    terminal = binding["terminal"]
    assert isinstance(terminal, dict)
    socket_record = terminal["control_socket"]
    assert isinstance(socket_record, dict)
    if socket_record.get("address") != control_socket:
        raise IncarnationHomeError(
            "visible launch receipt control socket does not match this launch"
        )
    _secure_control_socket(
        control_socket,
        harden=False,
        expected_device=socket_record["device"],
        expected_inode=socket_record["inode"],
    )
    if terminal.get("title") != _safe_terminal_title(terminal_title):
        raise IncarnationHomeError("visible launch receipt terminal title drifted")
    return receipt


def _terminate_rejected_visible_launch(receipt: dict[str, Any]) -> bool:
    """Stop and confirm the exact holder if launch admission fails."""

    try:
        holder_pid, holder_start_ticks, _kitty_pid, _kitty_start_ticks = (
            _holder_receipt_process_ids(receipt)
        )
        state = _proc_identity_state(holder_pid, holder_start_ticks)
        if state == "gone":
            return True
        if state != "live":
            return False
        _send_verified_term(holder_pid, holder_start_ticks)
        state = _wait_for_exact_process_exit(holder_pid, holder_start_ticks)
        if state == "gone":
            return True
        if state != "live":
            return False
        _send_verified_kill(holder_pid, holder_start_ticks)
        return _wait_for_exact_process_exit(holder_pid, holder_start_ticks) == "gone"
    except IncarnationHomeError:
        return False


def _emit_safe_json(
    value: dict[str, object], *, output_path: Path | None = None, label: str
) -> None:
    _assert_safe_projection(value)
    if output_path is not None:
        _write_new_json(output_path, value, label)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def command_bind(args: argparse.Namespace) -> int:
    holder_receipt_path = _regular_file(
        Path(args.holder_receipt), "holder terminal receipt"
    )
    binding, holder, terminal, source_receipt, source_digest = (
        _load_terminal_binding_input(
            binding_path=None,
            holder_receipt_path=holder_receipt_path,
            context_path=Path(args.binding_context),
            harden_socket=True,
        )
    )
    assert source_receipt is not None and source_digest is not None
    document = _write_terminal_binding(
        output_path=Path(args.output),
        binding=binding,
        holder=holder,
        terminal=terminal,
        source_receipt=source_receipt,
        source_digest=source_digest,
    )
    print(json.dumps(document, ensure_ascii=False, sort_keys=True))
    return 0


def command_rebind(args: argparse.Namespace) -> int:
    receipt = _rebind_replacement_holder_receipt(
        receipt_path=Path(args.output),
        holder_loss_reentry_path=Path(args.holder_loss_reentry),
        binding_context_path=Path(args.binding_context),
        manifest_path=Path(args.manifest),
        codex_executable_path=Path(args.codex_executable),
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


def command_status(args: argparse.Namespace) -> int:
    binding_path = Path(args.binding) if args.binding else None
    holder_receipt_path = (
        Path(args.holder_receipt) if args.holder_receipt else None
    )
    binding, holder, terminal, _source_receipt, _source_digest = (
        _load_terminal_binding_input(
            binding_path=binding_path,
            holder_receipt_path=holder_receipt_path,
            context_path=Path(args.binding_context) if args.binding_context else None,
            harden_socket=False,
            allow_missing_socket=True,
        )
    )
    projection, state = _observe_terminal_binding(
        binding=binding,
        holder=holder,
        terminal=terminal,
        kitty_executable=args.kitty_executable,
    )
    _emit_safe_json(
        projection,
        output_path=Path(args.output) if args.output else None,
        label="terminal status projection",
    )
    kitty_query = projection["observation"]["kitty_query"]
    return 0 if state == "missing" or kitty_query == "present" else 2


def command_send_text(args: argparse.Namespace) -> int:
    binding_path = Path(args.binding) if args.binding else None
    holder_receipt_path = (
        Path(args.holder_receipt) if args.holder_receipt else None
    )
    binding, holder, terminal, _source_receipt, _source_digest = (
        _load_terminal_binding_input(
            binding_path=binding_path,
            holder_receipt_path=holder_receipt_path,
            context_path=Path(args.binding_context) if args.binding_context else None,
            harden_socket=False,
        )
    )
    status, state = _observe_terminal_binding(
        binding=binding,
        holder=holder,
        terminal=terminal,
        kitty_executable=args.kitty_executable,
    )
    if state != "live" or status["observation"]["kitty_query"] != "present":
        raise IncarnationHomeError("directed input requires a live bound terminal")
    terminal_pid = terminal["pid"]
    holder_pid = holder["pid"]
    assert isinstance(terminal_pid, int) and isinstance(holder_pid, int)
    observed_window_id, dedicated = _kitty_dedication(
        holder_pid=holder_pid,
        kitty_pid=terminal_pid,
        terminal_argv=_proc_argv(terminal_pid),
    )
    if observed_window_id != str(terminal["window_id"]) or not dedicated:
        raise IncarnationHomeError(
            "directed input requires a dedicated live bound terminal"
        )
    socket_record = terminal["control_socket"]
    assert isinstance(socket_record, dict)
    _secure_control_socket(
        str(socket_record["address"]),
        harden=False,
        expected_device=socket_record["device"],
        expected_inode=socket_record["inode"],
    )
    _revalidate_bound_holder_identity(holder)
    try:
        completed = subprocess.run(
            [
                args.kitty_executable,
                "@",
                "--to",
                str(socket_record["address"]),
                "send-text",
                "--match",
                f"id:{terminal['window_id']}",
                "--stdin",
            ],
            input=args.text,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IncarnationHomeError("directed terminal input failed") from exc
    if completed.returncode != 0:
        raise IncarnationHomeError("directed terminal input returned an error")
    result = {
        "schema_version": TERMINAL_BINDING_SCHEMA_VERSION,
        "sent": True,
        "target": {
            "window_id": terminal["window_id"],
            "control_socket": socket_record,
        },
        "desktop_effect": "operator-interactive input explicitly requested",
    }
    _assert_safe_projection(result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def command_join(args: argparse.Namespace) -> int:
    """Record a validated non-waking holder return and authorize exact close."""

    handoff_path = _regular_file(Path(args.handoff), "handoff")
    holder_receipt_path = _regular_file(
        Path(args.holder_receipt), "holder terminal receipt"
    )
    join_receipt_path = Path(args.join_receipt)
    authorization_path = Path(args.authorization)
    closure_receipt_path = Path(args.closure_receipt)
    holder_receipt, holder_receipt_bytes, holder_receipt_digest = (
        _load_holder_receipt_snapshot(holder_receipt_path)
    )
    handoff_value, handoff_bytes, handoff_digest, _ = _load_handoff_holder_binding(
        handoff_path=handoff_path,
        holder_receipt_path=holder_receipt_path,
        closure_receipt_path=closure_receipt_path,
        holder_receipt=holder_receipt,
        holder_receipt_bytes=holder_receipt_bytes,
        holder_receipt_digest=holder_receipt_digest,
        require_return=True,
        require_terminal_action=True,
    )
    handoff_snapshot = (handoff_value, handoff_bytes, handoff_digest)
    holder_pid, _, terminal_pid, _ = _holder_receipt_process_ids(holder_receipt)
    join = {
        "schema_version": TERMINAL_JOIN_SCHEMA_VERSION,
        "join_ref": str(join_receipt_path.resolve()),
        "completed_at": _utc_now(),
        "handoff_ref": str(handoff_path.resolve()),
        "handoff_sha256": handoff_digest,
        "holder_receipt_ref": str(holder_receipt_path.resolve()),
        "holder_receipt_sha256": holder_receipt_digest,
        "closure_receipt_ref": str(closure_receipt_path.resolve()),
        "holder_pid": holder_pid,
        "terminal_pid": terminal_pid,
        "return": {
            "status": "returned",
            "validated": True,
            "owner_acceptance": "separate",
        },
        "terminal_action": {
            "action": "close_exact_bound_holder",
            "required": True,
        },
    }
    if authorization_path.exists() and not join_receipt_path.exists():
        raise IncarnationHomeError(
            "terminal closure authorization exists without its join receipt"
        )
    if join_receipt_path.exists():
        existing_join, join_bytes = _load_json_snapshot(
            join_receipt_path, "terminal join receipt"
        )
        if join_bytes != canonical_bytes(existing_join) + b"\n":
            raise IncarnationHomeError(
                "terminal join receipt is not canonically encoded"
            )
        _validate_join_completion(
            join_receipt_path=join_receipt_path,
            handoff_path=handoff_path,
            holder_receipt_path=holder_receipt_path,
            closure_receipt_path=closure_receipt_path,
            holder_receipt=holder_receipt,
            holder_receipt_bytes=holder_receipt_bytes,
            holder_receipt_digest=holder_receipt_digest,
            handoff_snapshot=handoff_snapshot,
        )
        join = existing_join
    else:
        _assert_file_snapshot(handoff_path, handoff_bytes, "handoff")
        _write_new_json(join_receipt_path, join, "terminal join receipt")
        join_bytes = canonical_bytes(join) + b"\n"
    authorization = {
        "schema_version": CLOSURE_AUTHORIZATION_SCHEMA_VERSION,
        "authorization_ref": str(authorization_path.resolve()),
        "authorization_kind": "join_completed",
        "authorized_at": _utc_now(),
        "handoff_ref": str(handoff_path.resolve()),
        "handoff_sha256": handoff_digest,
        "holder_receipt_ref": str(holder_receipt_path.resolve()),
        "holder_receipt_sha256": holder_receipt_digest,
        "closure_receipt_ref": str(closure_receipt_path.resolve()),
        "holder_pid": holder_pid,
        "terminal_pid": terminal_pid,
        "return_status": "returned",
        "terminal_action": {
            "action": "close_exact_bound_holder",
            "required": True,
            "authorized": True,
        },
        "evidence_ref": str(join_receipt_path.resolve()),
        "evidence_sha256": sha256_bytes(join_bytes),
        "join_receipt_ref": str(join_receipt_path.resolve()),
    }
    if authorization_path.exists():
        existing_authorization, authorization_bytes = _load_json_snapshot(
            authorization_path, "terminal closure authorization"
        )
        if authorization_bytes != canonical_bytes(existing_authorization) + b"\n":
            raise IncarnationHomeError(
                "terminal closure authorization is not canonically encoded"
            )
        _validate_closure_authorization(
            authorization_path=authorization_path,
            handoff_path=handoff_path,
            holder_receipt_path=holder_receipt_path,
            closure_receipt_path=closure_receipt_path,
            holder_receipt=holder_receipt,
            holder_receipt_bytes=holder_receipt_bytes,
            holder_receipt_digest=holder_receipt_digest,
            authorization_snapshot=(existing_authorization, authorization_bytes),
            handoff_snapshot=handoff_snapshot,
        )
        if (
            existing_authorization.get("authorization_kind") != "join_completed"
            or existing_authorization.get("evidence_ref")
            != str(join_receipt_path.resolve())
            or existing_authorization.get("join_receipt_ref")
            != str(join_receipt_path.resolve())
            or existing_authorization.get("evidence_sha256")
            != sha256_bytes(join_bytes)
        ):
            raise IncarnationHomeError(
                "terminal closure authorization does not bind the exact join receipt"
            )
        authorization = existing_authorization
    else:
        _assert_file_snapshot(handoff_path, handoff_bytes, "handoff")
        _write_new_json(
            authorization_path, authorization, "terminal closure authorization"
        )
    _assert_file_snapshot(handoff_path, handoff_bytes, "handoff")
    print(json.dumps({"join": join, "authorization": authorization}, sort_keys=True))
    return 0


def command_authorize_close(args: argparse.Namespace) -> int:
    """Convert a new wake-delivery proof into the common close authority."""

    handoff_path = _regular_file(Path(args.handoff), "handoff")
    holder_receipt_path = _regular_file(
        Path(args.holder_receipt), "holder terminal receipt"
    )
    wake_receipt_path = _regular_file(Path(args.wake_receipt), "wake receipt")
    authorization_path = Path(args.authorization)
    closure_receipt_path = Path(args.closure_receipt)
    holder_receipt, holder_receipt_bytes, holder_receipt_digest = (
        _load_holder_receipt_snapshot(holder_receipt_path)
    )
    handoff_value, handoff_bytes, handoff_digest, _ = _load_handoff_holder_binding(
        handoff_path=handoff_path,
        holder_receipt_path=holder_receipt_path,
        closure_receipt_path=closure_receipt_path,
        holder_receipt=holder_receipt,
        holder_receipt_bytes=holder_receipt_bytes,
        holder_receipt_digest=holder_receipt_digest,
        require_return=True,
        require_terminal_action=True,
    )
    handoff_snapshot = (handoff_value, handoff_bytes, handoff_digest)
    wake_value, wake_bytes = _load_json_snapshot(wake_receipt_path, "wake receipt")
    _validate_wake_delivery(
        wake_receipt_path=wake_receipt_path,
        handoff_path=handoff_path,
        holder_receipt_path=holder_receipt_path,
        closure_receipt_path=closure_receipt_path,
        holder_receipt=holder_receipt,
        holder_receipt_bytes=holder_receipt_bytes,
        holder_receipt_digest=holder_receipt_digest,
        wake_snapshot=(wake_value, wake_bytes),
        handoff_snapshot=handoff_snapshot,
    )
    holder_pid, _, terminal_pid, _ = _holder_receipt_process_ids(holder_receipt)
    authorization = {
        "schema_version": CLOSURE_AUTHORIZATION_SCHEMA_VERSION,
        "authorization_ref": str(authorization_path.resolve()),
        "authorization_kind": "wake_delivered",
        "authorized_at": _utc_now(),
        "handoff_ref": str(handoff_path.resolve()),
        "handoff_sha256": handoff_digest,
        "holder_receipt_ref": str(holder_receipt_path.resolve()),
        "holder_receipt_sha256": holder_receipt_digest,
        "closure_receipt_ref": str(closure_receipt_path.resolve()),
        "holder_pid": holder_pid,
        "terminal_pid": terminal_pid,
        "return_status": "returned",
        "terminal_action": {
            "action": "close_exact_bound_holder",
            "required": True,
            "authorized": True,
        },
        "evidence_ref": str(wake_receipt_path.resolve()),
        "evidence_sha256": sha256_bytes(wake_bytes),
        "wake_receipt_ref": str(wake_receipt_path.resolve()),
    }
    _assert_file_snapshot(handoff_path, handoff_bytes, "handoff")
    _write_new_json(
        authorization_path, authorization, "terminal closure authorization"
    )
    print(json.dumps(authorization, ensure_ascii=False, sort_keys=True))
    return 0


def command_close(args: argparse.Namespace) -> int:
    handoff_path = _regular_file(Path(args.handoff), "handoff")
    holder_receipt_path = _regular_file(
        Path(args.holder_receipt), "holder terminal receipt"
    )
    closure_receipt_path = Path(args.closure_receipt)
    receipt, holder_receipt_bytes, holder_receipt_digest = (
        _load_holder_receipt_snapshot(holder_receipt_path)
    )
    authorization_argument = getattr(args, "closure_authorization", None)
    wake_argument = getattr(args, "wake_receipt", None)
    legacy_wake_route = bool(wake_argument and not authorization_argument)
    if authorization_argument:
        authorization_path = _regular_file(
            Path(authorization_argument), "terminal closure authorization"
        )
        authorization_value, authorization_bytes = _load_json_snapshot(
            authorization_path, "terminal closure authorization"
        )
        authorization = _validate_closure_authorization(
            authorization_path=authorization_path,
            handoff_path=handoff_path,
            holder_receipt_path=holder_receipt_path,
            closure_receipt_path=closure_receipt_path,
            holder_receipt=receipt,
            holder_receipt_bytes=holder_receipt_bytes,
            holder_receipt_digest=holder_receipt_digest,
            authorization_snapshot=(authorization_value, authorization_bytes),
        )
    elif wake_argument:
        wake_path = _regular_file(Path(wake_argument), "wake receipt")
        wake_value, wake_bytes = _load_json_snapshot(wake_path, "wake receipt")
        _validate_wake_delivery(
            wake_receipt_path=wake_path,
            handoff_path=handoff_path,
            holder_receipt_path=holder_receipt_path,
            closure_receipt_path=closure_receipt_path,
            holder_receipt=receipt,
            holder_receipt_bytes=holder_receipt_bytes,
            holder_receipt_digest=holder_receipt_digest,
            wake_snapshot=(wake_value, wake_bytes),
        )
        authorization = {
            "authorization_ref": str(wake_path.resolve()),
            "authorization_kind": "wake_delivered",
            "evidence_ref": str(wake_path.resolve()),
            "evidence_sha256": sha256_bytes(wake_bytes),
        }
        authorization_bytes = wake_bytes
    else:
        raise IncarnationHomeError(
            "terminal close requires closure authorization or wake receipt"
        )
    holder_pid, holder_start_ticks, kitty_pid, kitty_start_ticks = (
        _holder_receipt_process_ids(receipt)
    )
    kitty_argv = receipt["terminal"]["argv"]
    kitty_comm = receipt["terminal"].get("required_comm", "kitty")
    kitty_window_id = receipt["terminal"].get("window_id")
    kitty_dedicated = receipt["terminal"].get("dedicated")
    if authorization_argument:
        _assert_file_snapshot(
            authorization_path,
            authorization_bytes,
            "terminal closure authorization",
        )
    evidence_digest = str(authorization["evidence_sha256"])
    _assert_file_digest(
        Path(str(authorization["evidence_ref"])),
        evidence_digest,
        "terminal closure evidence",
    )
    reservation_fd, reservation_path, completed = _reserve_closure_receipt(
        closure_receipt_path=closure_receipt_path,
        handoff_path=handoff_path,
        holder_receipt_path=holder_receipt_path,
        wake_receipt_path=Path(authorization["authorization_ref"]),
        authorization_path=Path(authorization["authorization_ref"]),
        authorization_kind=str(authorization["authorization_kind"]),
        evidence_path=Path(authorization["evidence_ref"]),
        authorization_digest=sha256_bytes(authorization_bytes),
        evidence_digest=evidence_digest,
        allow_legacy_wake_reservation=legacy_wake_route,
        holder_pid=holder_pid,
        terminal_pid=kitty_pid,
    )
    try:
        reservation = _load_json(
            reservation_path, "terminal closure reservation"
        )
    except BaseException:
        fcntl.flock(reservation_fd, fcntl.LOCK_UN)
        os.close(reservation_fd)
        raise
    if completed is not None:
        try:
            if completed.get("closed") is not True:
                raise IncarnationHomeError(
                    "terminal closure receipt records an unclosed close attempt"
                )
            print(json.dumps(completed, ensure_ascii=False, sort_keys=True))
        finally:
            fcntl.flock(reservation_fd, fcntl.LOCK_UN)
            os.close(reservation_fd)
        return 0

    signal_attempted = reservation.get("signal_attempted") is True
    signal_delivery = reservation.get("signal_delivery")
    if signal_delivery not in {
        "not_attempted",
        "confirmed",
        "not_delivered",
        "failed",
        "unknown",
    }:
        signal_delivery = (
            "confirmed"
            if reservation.get("signal_sent") is True
            else "unknown"
            if signal_attempted
            else "not_attempted"
        )
    signal_sent = signal_delivery == "confirmed"
    closed = False
    kitty_gone = False
    holder_gone = False
    identity_state = "unverified"
    failure: IncarnationHomeError | None = None
    try:
        kitty_state = _proc_identity_state(kitty_pid, kitty_start_ticks)
        holder_state = _proc_identity_state(holder_pid, holder_start_ticks)
        kitty_gone = kitty_state == "gone"
        holder_gone = holder_state == "gone"
        if kitty_gone and holder_gone:
            # Delivery was already proven and both exact identities have
            # naturally exited.  This is a successful, non-signaling close;
            # do not require reopening a mutable incarnation marker.
            identity_state = "already_gone"
            closed = True
        elif kitty_state != "live" or holder_state != "live":
            if kitty_gone or holder_gone:
                holder_state, kitty_state = _wait_for_natural_pair_exit(
                    holder_pid=holder_pid,
                    holder_start_ticks=holder_start_ticks,
                    kitty_pid=kitty_pid,
                    kitty_start_ticks=kitty_start_ticks,
                    holder_state=holder_state,
                    kitty_state=kitty_state,
                )
                kitty_gone = kitty_state == "gone"
                holder_gone = holder_state == "gone"
                if kitty_gone and holder_gone:
                    identity_state = "already_gone"
                    closed = True
            if not closed:
                identity_state = (
                    "partial_gone" if (kitty_gone or holder_gone) else "identity_drift"
                )
                failure = IncarnationHomeError(
                    "holder terminal identity was not simultaneously live or already gone"
                )
        else:
            try:
                (
                    holder_pid,
                    kitty_pid,
                    kitty_comm,
                    kitty_window_id,
                    kitty_dedicated,
                ) = _holder_terminal_identity(receipt)
                identity_state = "live"
            except IncarnationHomeError as exc:
                # Re-check the exact recorded identities after a natural
                # exit race.  PID reuse or a surviving process remains a
                # hard failure; only both exact identities being gone may be
                # recorded as already_gone.
                kitty_state = _proc_identity_state(kitty_pid, kitty_start_ticks)
                holder_state = _proc_identity_state(holder_pid, holder_start_ticks)
                kitty_gone = kitty_state == "gone"
                holder_gone = holder_state == "gone"
                if kitty_gone or holder_gone:
                    holder_state, kitty_state = _wait_for_natural_pair_exit(
                        holder_pid=holder_pid,
                        holder_start_ticks=holder_start_ticks,
                        kitty_pid=kitty_pid,
                        kitty_start_ticks=kitty_start_ticks,
                        holder_state=holder_state,
                        kitty_state=kitty_state,
                    )
                    kitty_gone = kitty_state == "gone"
                    holder_gone = holder_state == "gone"
                if kitty_gone and holder_gone:
                    identity_state = "already_gone"
                    closed = True
                else:
                    identity_state = "identity_drift"
                    failure = exc
            if failure is None and not closed:
                if not signal_attempted:
                    reservation = {
                        **reservation,
                        "signal": "TERM",
                        "signal_target": "holder_process",
                        "signal_attempted": True,
                        "signal_attempted_at": _utc_now(),
                        "signal_delivery": "unknown",
                        "signal_sent": False,
                    }
                    # This state transition is durable and locked before the
                    # destructive syscall.  A closer that dies after TERM
                    # cannot be mistaken for a never-attempted retry.
                    _write_reservation_json(
                        reservation_path,
                        reservation,
                        "terminal closure reservation",
                    )
                    signal_attempted = True
                    signal_delivery = "unknown"
                    try:
                        signal_sent = _send_verified_term(
                            holder_pid, holder_start_ticks
                        )
                    except IncarnationHomeError as exc:
                        signal_delivery = "failed"
                        reservation = {
                            **reservation,
                            "signal_delivery": signal_delivery,
                            "signal_sent": False,
                            "signal_observed_at": _utc_now(),
                        }
                        _write_reservation_json(
                            reservation_path,
                            reservation,
                            "terminal closure reservation",
                        )
                        kitty_state = _proc_identity_state(
                            kitty_pid, kitty_start_ticks
                        )
                        holder_state = _proc_identity_state(
                            holder_pid, holder_start_ticks
                        )
                        kitty_gone = kitty_state == "gone"
                        holder_gone = holder_state == "gone"
                        if kitty_gone or holder_gone:
                            holder_state, kitty_state = _wait_for_natural_pair_exit(
                                holder_pid=holder_pid,
                                holder_start_ticks=holder_start_ticks,
                                kitty_pid=kitty_pid,
                                kitty_start_ticks=kitty_start_ticks,
                                holder_state=holder_state,
                                kitty_state=kitty_state,
                            )
                            kitty_gone = kitty_state == "gone"
                            holder_gone = holder_state == "gone"
                        if kitty_gone and holder_gone:
                            identity_state = "already_gone"
                            closed = True
                        else:
                            failure = exc
                    else:
                        signal_delivery = (
                            "confirmed" if signal_sent else "not_delivered"
                        )
                        reservation = {
                            **reservation,
                            "signal_delivery": signal_delivery,
                            "signal_sent": signal_sent,
                            "signal_observed_at": _utc_now(),
                        }
                        _write_reservation_json(
                            reservation_path,
                            reservation,
                            "terminal closure reservation",
                        )
                if (
                    failure is None
                    and not closed
                    and signal_delivery == "not_delivered"
                ):
                    kitty_state = _proc_identity_state(kitty_pid, kitty_start_ticks)
                    holder_state = _proc_identity_state(holder_pid, holder_start_ticks)
                    kitty_gone = kitty_state == "gone"
                    holder_gone = holder_state == "gone"
                    if kitty_gone or holder_gone:
                        holder_state, kitty_state = _wait_for_natural_pair_exit(
                            holder_pid=holder_pid,
                            holder_start_ticks=holder_start_ticks,
                            kitty_pid=kitty_pid,
                            kitty_start_ticks=kitty_start_ticks,
                            holder_state=holder_state,
                            kitty_state=kitty_state,
                        )
                        kitty_gone = kitty_state == "gone"
                        holder_gone = holder_state == "gone"
                    if kitty_gone and holder_gone:
                        identity_state = "already_gone"
                        closed = True
                    else:
                        identity_state = "identity_drift"
                        failure = IncarnationHomeError(
                            "holder exited before verified TERM delivery"
                        )
                if (
                    failure is None
                    and not closed
                    and signal_delivery == "failed"
                ):
                    failure = IncarnationHomeError(
                        "verified holder TERM delivery failed"
                    )
                if failure is None and not closed:
                    for _ in range(40):
                        kitty_state = _proc_identity_state(
                            kitty_pid, kitty_start_ticks
                        )
                        holder_state = _proc_identity_state(
                            holder_pid, holder_start_ticks
                        )
                        kitty_gone = kitty_state == "gone"
                        holder_gone = holder_state == "gone"
                        if kitty_state == "drifted" or holder_state == "drifted":
                            identity_state = "identity_drift"
                            failure = IncarnationHomeError(
                                "holder terminal identity changed during closure"
                            )
                            break
                        if kitty_gone and holder_gone:
                            closed = True
                            break
                        time.sleep(0.25)
                    if not closed:
                        identity_state = "close_unverified"
    finally:
        terminal = {
            "pid": kitty_pid,
            "start_ticks": kitty_start_ticks,
            "comm": kitty_comm,
            "argv": kitty_argv,
            "signal": "TERM",
            "signal_target": "holder_process",
            "signal_attempted": signal_attempted,
            "signal_delivery": signal_delivery,
            "signal_sent": signal_sent,
            "gone": kitty_gone,
        }
        if kitty_window_id is not None:
            terminal["window_id"] = kitty_window_id
        if kitty_dedicated is not None:
            terminal["dedicated"] = kitty_dedicated
        closure = {
            "schema_version": TERMINAL_CLOSURE_SCHEMA_VERSION,
            "handoff_ref": str(handoff_path.resolve()),
            "holder_receipt_ref": str(holder_receipt_path.resolve()),
            "authorization_ref": str(authorization["authorization_ref"]),
            "authorization_kind": str(authorization["authorization_kind"]),
            "authorization_evidence_ref": str(authorization["evidence_ref"]),
            "reservation_ref": str(reservation_path.resolve()),
            "verified_at": _utc_now(),
            "holder": {
                "pid": holder_pid,
                "start_ticks": holder_start_ticks,
                "gone": holder_gone,
            },
            "terminal": terminal,
            "closed": closed,
            "outcome": (
                "already_gone"
                if identity_state == "already_gone"
                else "closed"
                if closed
                else "close_unverified"
            ),
            "identity_state": identity_state,
            "route": "abyss_stack_visible_incarnation_runtime",
            "trigger": (
                "wake_bridge_after_confirmed_handoff_delivery"
                if authorization["authorization_kind"] == "wake_delivered"
                else "join_after_validated_terminal_return"
            ),
        }
        if authorization["authorization_kind"] == "wake_delivered":
            closure["wake_receipt_ref"] = str(authorization["evidence_ref"])
        else:
            closure["join_receipt_ref"] = str(authorization["evidence_ref"])
        try:
            _write_new_json(
                closure_receipt_path,
                closure,
                "terminal closure receipt",
            )
        finally:
            fcntl.flock(reservation_fd, fcntl.LOCK_UN)
            os.close(reservation_fd)
    if not closed:
        if failure is not None:
            raise failure
        raise IncarnationHomeError("holder terminal closure was not observed")
    print(json.dumps(closure, ensure_ascii=False, sort_keys=True))
    return 0


@contextlib.contextmanager
def _incarnation_preparation_lock(
    runtime_root: Path, ambient_identities: set[tuple[int, int]]
) -> Any:
    """Serialize every preparation through the pinned runtime directory."""

    lock_path = runtime_root / PREPARATION_LOCK_FILE_NAME
    parent_fd = _open_pinned_parent_directory(
        lock_path, "incarnation preparation lock"
    )
    directory_locked = False
    lock_fd: int | None = None
    lock_file_locked = False
    try:
        try:
            initial = os.lstat(
                PREPARATION_LOCK_FILE_NAME, dir_fd=parent_fd
            )
        except FileNotFoundError:
            initial = None
        except OSError as exc:
            raise IncarnationHomeError(
                f"incarnation preparation lock cannot be inspected: {lock_path}"
            ) from exc
        if initial is not None and (
            stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode)
        ):
            raise IncarnationHomeError(
                f"incarnation preparation lock is not an isolated regular file: {lock_path}"
            )
        fcntl.flock(parent_fd, fcntl.LOCK_EX)
        directory_locked = True
        try:
            locked_initial = os.lstat(
                PREPARATION_LOCK_FILE_NAME, dir_fd=parent_fd
            )
        except FileNotFoundError:
            locked_initial = None
        except OSError as exc:
            raise IncarnationHomeError(
                f"incarnation preparation lock cannot be inspected after directory lock: {lock_path}"
            ) from exc
        if initial is not None and (
            locked_initial is None
            or (locked_initial.st_dev, locked_initial.st_ino, locked_initial.st_mode)
            != (initial.st_dev, initial.st_ino, initial.st_mode)
        ):
            raise IncarnationHomeError(
                f"incarnation preparation lock changed before acquisition: {lock_path}"
            )
        initial = locked_initial
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        if initial is None:
            flags |= os.O_CREAT | os.O_EXCL
        lock_fd = os.open(
            PREPARATION_LOCK_FILE_NAME,
            flags,
            0o600,
            dir_fd=parent_fd,
        )
        opened = os.fstat(lock_fd)
        observed = os.lstat(PREPARATION_LOCK_FILE_NAME, dir_fd=parent_fd)
        if (
            initial is not None
            and (opened.st_dev, opened.st_ino, opened.st_mode)
            != (initial.st_dev, initial.st_ino, initial.st_mode)
        ) or (
            (opened.st_dev, opened.st_ino, opened.st_mode)
            != (observed.st_dev, observed.st_ino, observed.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) in ambient_identities
        ):
            raise IncarnationHomeError(
                f"incarnation preparation lock is not an isolated regular file: {lock_path}"
            )
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        lock_file_locked = True
        reopened = os.fstat(lock_fd)
        renamed = os.lstat(PREPARATION_LOCK_FILE_NAME, dir_fd=parent_fd)
        if (
            (reopened.st_dev, reopened.st_ino)
            != (opened.st_dev, opened.st_ino)
            or (renamed.st_dev, renamed.st_ino)
            != (opened.st_dev, opened.st_ino)
            or not stat.S_ISREG(reopened.st_mode)
            or reopened.st_nlink != 1
            or (reopened.st_dev, reopened.st_ino) in ambient_identities
            or stat.S_IMODE(reopened.st_mode) != 0o600
        ):
            raise IncarnationHomeError(
                f"incarnation preparation lock changed after acquisition: {lock_path}"
            )
        yield
    except IncarnationHomeError:
        raise
    except OSError as exc:
        raise IncarnationHomeError(
            f"incarnation preparation lock cannot be acquired: {lock_path}"
        ) from exc
    finally:
        if lock_fd is not None and lock_file_locked:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        elif lock_fd is not None:
            os.close(lock_fd)
        if directory_locked:
            try:
                fcntl.flock(parent_fd, fcntl.LOCK_UN)
            finally:
                os.close(parent_fd)
        else:
            os.close(parent_fd)


def _reserve_holder_claim_for_launch_locked(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    manifest_digest: str,
    binding_context_digest: str,
    binding_context: dict[str, str],
    holder_receipt_path: Path,
    ambient_identities: set[tuple[int, int]],
    allow_existing_claim: bool = False,
) -> tuple[Path, str]:
    """Publish or rebind a holder claim while the preparation lock is held."""

    _locked_manifest, _locked_bytes, locked_digest = _load_manifest_snapshot(
        manifest_path,
        binding_context=binding_context,
        binding_context_digest=binding_context_digest,
        require_holder_binding=True,
    )
    if locked_digest != manifest_digest:
        raise IncarnationHomeError(
            "incarnation-home manifest changed before holder claim"
        )
    reserve = (
        _reserve_or_transfer_holder_claim
        if allow_existing_claim
        else _reserve_holder_claim
    )
    return reserve(
        manifest_path=manifest_path,
        manifest=_locked_manifest,
        manifest_digest=manifest_digest,
        binding_context_digest=binding_context_digest,
        holder_receipt_path=holder_receipt_path,
        ambient_identities=ambient_identities,
    )


def _reserve_holder_claim_for_launch(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    manifest_digest: str,
    binding_context_digest: str,
    binding_context: dict[str, str],
    holder_receipt_path: Path,
    allow_existing_claim: bool = False,
) -> tuple[Path, str]:
    """Publish or rebind a holder claim under the preparation serialization boundary."""

    runtime_root_value = manifest.get("runtime_root")
    ambient_home_value = manifest.get("ambient_codex_home")
    if not isinstance(runtime_root_value, str) or not isinstance(
        ambient_home_value, str
    ):
        raise IncarnationHomeError(
            "holder claim launch lock lacks runtime and ambient roots"
        )
    runtime_root = _absolute_directory(Path(runtime_root_value), "runtime root")
    ambient_home = _absolute_directory(
        Path(ambient_home_value), "ambient Codex home"
    )
    ambient_identities = _ambient_inode_identities(ambient_home)
    with _incarnation_preparation_lock(runtime_root, ambient_identities):
        return _reserve_holder_claim_for_launch_locked(
            manifest_path=manifest_path,
            manifest=manifest,
            manifest_digest=manifest_digest,
            binding_context=binding_context,
            binding_context_digest=binding_context_digest,
            holder_receipt_path=holder_receipt_path,
            ambient_identities=ambient_identities,
            allow_existing_claim=allow_existing_claim,
        )


def _preparation_owner_record(
    *,
    ambient_home: Path,
    runtime_root: Path,
    realization_root: Path,
    incarnation_root: Path,
    coordinate: str,
    holder_coordinate: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": PREPARATION_OWNER_SCHEMA_VERSION,
        "owner_token": sha256_bytes(secrets.token_bytes(32)),
        "ambient_home": str(ambient_home),
        "runtime_root": str(runtime_root),
        "realization_root": str(realization_root),
        "incarnation_root": str(incarnation_root),
        "coordinate": coordinate,
        "holder_coordinate": holder_coordinate,
        "pid": os.getpid(),
        "start_ticks": _proc_start_ticks(os.getpid()),
        "created_at": _utc_now(),
    }


def _validate_preparation_owner_record(
    value: object,
    *,
    ambient_home: Path,
    runtime_root: Path,
    realization_root: Path,
    incarnation_root: Path,
    coordinate: str,
    holder_coordinate: str | None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IncarnationHomeError("incarnation preparation owner token is invalid")
    expected_fields = {
        "schema_version",
        "owner_token",
        "ambient_home",
        "runtime_root",
        "realization_root",
        "incarnation_root",
        "coordinate",
        "holder_coordinate",
        "pid",
        "start_ticks",
        "created_at",
    }
    if set(value) != expected_fields:
        raise IncarnationHomeError(
            "incarnation preparation owner token fields are not exact"
        )
    if value.get("schema_version") != PREPARATION_OWNER_SCHEMA_VERSION:
        raise IncarnationHomeError("unsupported incarnation preparation owner token")
    token = value.get("owner_token")
    if not isinstance(token, str) or SHA256_DIGEST_PATTERN.fullmatch(token) is None:
        raise IncarnationHomeError("incarnation preparation owner token digest is invalid")
    if (
        value.get("ambient_home") != str(ambient_home)
        or value.get("runtime_root") != str(runtime_root)
        or value.get("realization_root") != str(realization_root)
        or value.get("incarnation_root") != str(incarnation_root)
        or value.get("coordinate") != coordinate
        or value.get("holder_coordinate") != holder_coordinate
    ):
        raise IncarnationHomeError(
            "incarnation preparation owner token target does not match"
        )
    if (
        not isinstance(value.get("pid"), int)
        or isinstance(value.get("pid"), bool)
        or value["pid"] < 1
        or not isinstance(value.get("start_ticks"), int)
        or isinstance(value.get("start_ticks"), bool)
        or value["start_ticks"] < 1
        or not isinstance(value.get("created_at"), str)
        or not value["created_at"].strip()
    ):
        raise IncarnationHomeError("incarnation preparation owner token identity is invalid")
    return dict(value)


def _open_recovery_directory_at(
    parent_fd: int, name: str, label: str
) -> tuple[int, os.stat_result, os.stat_result]:
    """Open one recovery directory relative to a retained parent descriptor."""

    try:
        initial = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise IncarnationHomeError(
            f"{label} cannot be inspected safely"
        ) from exc
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISDIR(initial.st_mode):
        raise IncarnationHomeError(f"{label} is not a real directory")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise IncarnationHomeError(f"{label} cannot be opened safely") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            _actor_local_identity_mode(opened)
            != _actor_local_identity_mode(initial)
        ):
            raise IncarnationHomeError(f"{label} changed during safe open")
        return descriptor, initial, opened
    except IncarnationHomeError:
        os.close(descriptor)
        raise
    except OSError as exc:
        os.close(descriptor)
        raise IncarnationHomeError(f"{label} cannot be inspected after safe open") from exc


def _revalidate_recovery_entry(
    parent_fd: int,
    name: str,
    descriptor: int,
    initial: os.stat_result,
    label: str,
) -> os.stat_result:
    try:
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise IncarnationHomeError(f"{label} changed during recovery") from exc
    if (
        _actor_local_identity_mode(observed)
        != _actor_local_identity_mode(initial)
        or _actor_local_identity_mode(opened)
        != _actor_local_identity_mode(initial)
    ):
        raise IncarnationHomeError(f"{label} changed during recovery")
    return observed


def _validate_recoverable_entry_at(
    parent_fd: int,
    name: str,
    *,
    ambient_identities: set[tuple[int, int]],
    label: str,
) -> None:
    try:
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise IncarnationHomeError(
            f"stale incarnation preparation entry cannot be inspected: {label}"
        ) from exc
    if stat.S_ISLNK(observed.st_mode):
        return
    identity = (observed.st_dev, observed.st_ino)
    if identity in ambient_identities:
        raise IncarnationHomeError(
            f"stale incarnation preparation aliases ambient state: {label}"
        )
    if stat.S_ISREG(observed.st_mode):
        if observed.st_nlink != 1:
            raise IncarnationHomeError(
                f"stale incarnation preparation entry is multiply linked: {label}"
            )
        return
    if not stat.S_ISDIR(observed.st_mode):
        raise IncarnationHomeError(
            f"stale incarnation preparation contains a special file: {label}"
        )
    descriptor, initial, opened = _open_recovery_directory_at(
        parent_fd, name, label
    )
    try:
        try:
            children = sorted(os.listdir(descriptor))
            after_listing = os.fstat(descriptor)
        except OSError as exc:
            raise IncarnationHomeError(
                f"stale incarnation preparation directory cannot be enumerated: {label}"
            ) from exc
        if _actor_local_identity_mode(after_listing) != _actor_local_identity_mode(opened):
            raise IncarnationHomeError(
                f"stale incarnation preparation directory changed during validation: {label}"
            )
        for child_name in children:
            _validate_recoverable_entry_at(
                descriptor,
                child_name,
                ambient_identities=ambient_identities,
                label=f"{label}/{child_name}",
            )
        _revalidate_recovery_entry(parent_fd, name, descriptor, initial, label)
    finally:
        os.close(descriptor)


def _remove_recoverable_entry_at(
    parent_fd: int,
    name: str,
    *,
    ambient_identities: set[tuple[int, int]],
    label: str,
) -> None:
    try:
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise IncarnationHomeError(
            f"stale incarnation preparation entry changed during recovery: {label}"
        ) from exc
    if stat.S_ISLNK(observed.st_mode):
        try:
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if _actor_local_identity_mode(current) != _actor_local_identity_mode(observed):
                raise IncarnationHomeError(f"{label} changed during recovery")
            os.unlink(name, dir_fd=parent_fd)
        except IncarnationHomeError:
            raise
        except OSError as exc:
            raise IncarnationHomeError(f"{label} could not be removed safely") from exc
        return
    identity = (observed.st_dev, observed.st_ino)
    if identity in ambient_identities:
        raise IncarnationHomeError(
            f"stale incarnation preparation aliases ambient state: {label}"
        )
    if stat.S_ISREG(observed.st_mode):
        if observed.st_nlink != 1:
            raise IncarnationHomeError(
                f"stale incarnation preparation entry is multiply linked: {label}"
            )
        try:
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                _actor_local_identity_mode(current)
                != _actor_local_identity_mode(observed)
                or current.st_nlink != 1
            ):
                raise IncarnationHomeError(f"{label} changed during recovery")
            os.unlink(name, dir_fd=parent_fd)
        except IncarnationHomeError:
            raise
        except OSError as exc:
            raise IncarnationHomeError(f"{label} could not be removed safely") from exc
        return
    if not stat.S_ISDIR(observed.st_mode):
        raise IncarnationHomeError(
            f"stale incarnation preparation contains a special file: {label}"
        )
    descriptor, initial, opened = _open_recovery_directory_at(
        parent_fd, name, label
    )
    try:
        try:
            children = sorted(os.listdir(descriptor))
            after_listing = os.fstat(descriptor)
        except OSError as exc:
            raise IncarnationHomeError(
                f"stale incarnation preparation directory cannot be enumerated: {label}"
            ) from exc
        if _actor_local_identity_mode(after_listing) != _actor_local_identity_mode(opened):
            raise IncarnationHomeError(f"{label} changed during recovery")
        for child_name in children:
            _remove_recoverable_entry_at(
                descriptor,
                child_name,
                ambient_identities=ambient_identities,
                label=f"{label}/{child_name}",
            )
        _revalidate_recovery_entry(parent_fd, name, descriptor, initial, label)
        try:
            os.rmdir(name, dir_fd=parent_fd)
        except OSError as exc:
            raise IncarnationHomeError(f"{label} could not be removed safely") from exc
    finally:
        os.close(descriptor)


def _recover_stale_preparation_root(
    *,
    incarnation_root: Path,
    ambient_home: Path,
    realization_root: Path,
    runtime_root: Path,
    coordinate: str,
    holder_coordinate: str | None,
    ambient_identities: set[tuple[int, int]],
) -> None:
    """Remove one tokened root through a retained inode-bound directory handle."""

    parent_fd = _open_pinned_parent_directory(
        incarnation_root, "stale incarnation preparation root"
    )
    root_fd: int | None = None
    try:
        root_fd, root_initial, root_opened = _open_recovery_directory_at(
            parent_fd,
            incarnation_root.name,
            "stale incarnation preparation root",
        )
        try:
            try:
                marker = os.stat(
                    "incarnation-home.json",
                    dir_fd=root_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                marker = None
            except OSError as exc:
                raise IncarnationHomeError(
                    "published incarnation home marker cannot be inspected safely"
                ) from exc
            if marker is not None:
                raise IncarnationHomeError(
                    "published incarnation home cannot be treated as stale preparation"
                )
            owner_fd, _owner_opened = _open_stable_regular_file_at(
                root_fd,
                PREPARATION_OWNER_FILE_NAME,
                label="incarnation preparation owner token",
                ambient_identities=ambient_identities,
            )
            try:
                owner = _decode_json_snapshot(
                    _read_descriptor_bytes(
                        owner_fd, "incarnation preparation owner token"
                    ),
                    "incarnation preparation owner token",
                )
            finally:
                os.close(owner_fd)
            _validate_preparation_owner_record(
                owner,
                ambient_home=ambient_home,
                runtime_root=runtime_root,
                realization_root=realization_root,
                incarnation_root=incarnation_root,
                coordinate=coordinate,
                holder_coordinate=holder_coordinate,
            )
            try:
                children = sorted(os.listdir(root_fd))
                after_listing = os.fstat(root_fd)
            except OSError as exc:
                raise IncarnationHomeError(
                    "stale incarnation preparation root cannot be enumerated safely"
                ) from exc
            if _actor_local_identity_mode(after_listing) != _actor_local_identity_mode(root_opened):
                raise IncarnationHomeError(
                    "stale incarnation preparation root changed during validation"
                )
            for child_name in children:
                _validate_recoverable_entry_at(
                    root_fd,
                    child_name,
                    ambient_identities=ambient_identities,
                    label=child_name,
                )
            _revalidate_recovery_entry(
                parent_fd,
                incarnation_root.name,
                root_fd,
                root_initial,
                "stale incarnation preparation root",
            )
            for child_name in sorted(os.listdir(root_fd)):
                _remove_recoverable_entry_at(
                    root_fd,
                    child_name,
                    ambient_identities=ambient_identities,
                    label=child_name,
                )
            _revalidate_recovery_entry(
                parent_fd,
                incarnation_root.name,
                root_fd,
                root_initial,
                "stale incarnation preparation root",
            )
            try:
                os.rmdir(incarnation_root.name, dir_fd=parent_fd)
            except OSError as exc:
                raise IncarnationHomeError(
                    "stale incarnation preparation root could not be recovered"
                ) from exc
        finally:
            os.close(root_fd)
            root_fd = None
    finally:
        os.close(parent_fd)


def _remove_empty_directory_if_stable(path: Path, label: str) -> None:
    """Remove an empty directory only through its pinned parent and identity."""

    parent_fd = _open_pinned_parent_directory(path, label)
    descriptor: int | None = None
    try:
        try:
            initial = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise IncarnationHomeError(f"{label} cannot be inspected safely") from exc
        if stat.S_ISLNK(initial.st_mode) or not stat.S_ISDIR(initial.st_mode):
            return
        descriptor, _opened_initial, opened = _open_recovery_directory_at(
            parent_fd, path.name, label
        )
        try:
            try:
                if os.listdir(descriptor):
                    return
            except OSError as exc:
                raise IncarnationHomeError(f"{label} cannot be enumerated safely") from exc
            _revalidate_recovery_entry(parent_fd, path.name, descriptor, initial, label)
            try:
                os.rmdir(path.name, dir_fd=parent_fd)
            except FileNotFoundError:
                return
            except OSError as exc:
                raise IncarnationHomeError(f"{label} could not be removed safely") from exc
        finally:
            os.close(descriptor)
            descriptor = None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _claim_preparation_root(
    *,
    incarnation_root: Path,
    ambient_home: Path,
    realization_root: Path,
    runtime_root: Path,
    coordinate: str,
    holder_coordinate: str | None,
    ambient_identities: set[tuple[int, int]],
    owner_token: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Create a token before materialization, or recover an old tokened root."""

    marker = incarnation_root / "incarnation-home.json"
    if marker.exists() or marker.is_symlink():
        return None
    if incarnation_root.exists():
        if incarnation_root.is_symlink() or not incarnation_root.is_dir():
            raise IncarnationHomeError(
                "unpublished incarnation root is not a real directory"
            )
        _recover_stale_preparation_root(
            incarnation_root=incarnation_root,
            ambient_home=ambient_home,
            realization_root=realization_root,
            runtime_root=runtime_root,
            coordinate=coordinate,
            holder_coordinate=holder_coordinate,
            ambient_identities=ambient_identities,
        )
    incarnation_root.mkdir(mode=0o700, exist_ok=False)
    record = owner_token or _preparation_owner_record(
        ambient_home=ambient_home,
        runtime_root=runtime_root,
        realization_root=realization_root,
        incarnation_root=incarnation_root,
        coordinate=coordinate,
        holder_coordinate=holder_coordinate,
    )
    try:
        _validate_preparation_owner_record(
            record,
            ambient_home=ambient_home,
            runtime_root=runtime_root,
            realization_root=realization_root,
            incarnation_root=incarnation_root,
            coordinate=coordinate,
            holder_coordinate=holder_coordinate,
        )
        _write_new_json(
            incarnation_root / PREPARATION_OWNER_FILE_NAME,
            record,
            "incarnation preparation owner token",
        )
    except BaseException:
        # The root has no published marker and no other attempt can observe it
        # while the runtime preparation lock is held.  Remove only this empty
        # root if token creation itself failed, so the caller never leaves an
        # unowned first-preparation coordinate behind.
        try:
            incarnation_root.rmdir()
        except OSError:
            pass
        raise
    return record


def _finish_preparation_owner(owner: dict[str, Any] | None) -> None:
    if owner is None:
        return
    owner_path = Path(str(owner["incarnation_root"])) / PREPARATION_OWNER_FILE_NAME
    parent_fd = _open_pinned_parent_directory(
        owner_path, "incarnation preparation owner token"
    )
    descriptor: int | None = None
    try:
        try:
            initial = os.lstat(owner_path.name, dir_fd=parent_fd)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise IncarnationHomeError(
                "incarnation preparation owner token cannot be inspected"
            ) from exc
        if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
            return
        descriptor, opened = _open_stable_regular_file_at(
            parent_fd,
            owner_path.name,
            label="incarnation preparation owner token",
            ambient_identities=set(),
        )
        observed = _decode_json_snapshot(
            _read_descriptor_bytes(descriptor, str(owner_path)),
            "incarnation preparation owner token",
        )
        if observed != owner:
            raise IncarnationHomeError(
                "incarnation preparation owner token changed before publication cleanup"
            )
        try:
            _revalidate_regular_file_at(
                parent_fd,
                owner_path.name,
                descriptor,
                opened,
                label="incarnation preparation owner token",
                ambient_identities=set(),
            )
        except IncarnationHomeError as exc:
            raise IncarnationHomeError(
                "incarnation preparation owner token changed before publication cleanup"
            ) from exc
        try:
            os.unlink(owner_path.name, dir_fd=parent_fd)
        except OSError as exc:
            raise IncarnationHomeError(
                "incarnation preparation owner token could not be retired"
            ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _prepare_home_attempt_owner(
    *,
    ambient_home: Path,
    realization_path: Path,
    runtime_root: Path,
    binding_context: Path | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if binding_context is None:
        return None
    try:
        runtime_root = _absolute_directory(runtime_root, "runtime root")
        ambient_home = _absolute_directory(ambient_home, "ambient Codex home")
        realization_path = _regular_file(realization_path, "model realization")
        realization, _model, _effort, _version, fingerprint = _realization(
            realization_path
        )
        context, _raw, context_digest = _holder_binding_context_input(binding_context)
        if Path(context["runtime_state_root"]).resolve() != runtime_root:
            return None
        coordinate = _incarnation_coordinate(
            str(realization.get("model_realization_id")), fingerprint
        )
        holder_coordinate = _holder_binding_context_coordinate(
            context, context_digest
        )
        realization_root = _holder_incarnation_root(
            runtime_root=runtime_root,
            incarnation_coordinate=coordinate,
            holder_coordinate=None,
        )
        incarnation_root = _holder_incarnation_root(
            runtime_root=runtime_root,
            incarnation_coordinate=coordinate,
            holder_coordinate=holder_coordinate,
        )
        return _preparation_owner_record(
            ambient_home=ambient_home,
            runtime_root=runtime_root,
            realization_root=realization_root,
            incarnation_root=incarnation_root,
            coordinate=coordinate,
            holder_coordinate=holder_coordinate,
        )
    except IncarnationHomeError:
        return None


def _prepare_home_impl(
    *,
    ambient_home: Path,
    realization_path: Path,
    runtime_root: Path,
    capability_grants: Sequence[Path] = (),
    binding_context: Path | dict[str, Any] | None = None,
    holder_namespace: str | None = None,
    _owner_token: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if holder_namespace is not None:
        raise IncarnationHomeError(
            "holder namespace is not an identity proof; use a typed holder binding context"
        )
    ambient_home = _absolute_directory(ambient_home, "ambient Codex home")
    runtime_root = _absolute_directory(runtime_root, "runtime root")
    realization_path = _regular_file(realization_path, "model realization")
    if runtime_root == ambient_home or ambient_home in runtime_root.parents:
        raise IncarnationHomeError(
            "runtime root may not be nested under the ambient Codex home"
        )
    realization, model_slug, effort, runtime_version, fingerprint = _realization(
        realization_path
    )
    coordinate = _incarnation_coordinate(
        str(realization.get("model_realization_id")), fingerprint
    )
    holder_context: dict[str, str] | None = None
    holder_context_digest: str | None = None
    holder_coordinate: str | None = None
    if binding_context is not None:
        holder_context, _holder_context_bytes, holder_context_digest = (
            _holder_binding_context_input(binding_context)
        )
        if Path(holder_context["runtime_state_root"]).resolve() != runtime_root:
            raise IncarnationHomeError(
                "holder binding runtime state root does not match runtime root"
            )
        holder_coordinate = _holder_binding_context_coordinate(
            holder_context, holder_context_digest
        )
    realization_root = _holder_incarnation_root(
        runtime_root=runtime_root,
        incarnation_coordinate=coordinate,
        holder_coordinate=None,
    )
    if realization_root.is_symlink():
        raise IncarnationHomeError("realization incarnation root may not be a symlink")
    if holder_coordinate is None and not (
        (realization_root / "incarnation-home.json").is_file()
        and not (realization_root / "incarnation-home.json").is_symlink()
    ):
        raise IncarnationHomeError(
            "typed holder binding context is required for a new incarnation home"
        )
    incarnation_root = _holder_incarnation_root(
        runtime_root=runtime_root,
        incarnation_coordinate=coordinate,
        holder_coordinate=holder_coordinate,
    )
    codex_home = incarnation_root / "codex-home"
    ambient_identity = _ambient_home_identity(ambient_home)
    if incarnation_root.is_symlink():
        raise IncarnationHomeError("incarnation root may not be a symlink")
    existing_marker = incarnation_root / "incarnation-home.json"
    existing: dict[str, Any] = {}
    unpublished_root = False
    if incarnation_root.exists():
        if existing_marker.is_symlink():
            raise IncarnationHomeError(
                "existing incarnation home marker may not be a symlink"
            )
        if not existing_marker.is_file():
            unpublished_root = True
        else:
            existing = _load_json(existing_marker, "existing incarnation-home manifest")
        if unpublished_root:
            pass
        else:
            if existing.get("ambient_codex_home") != str(ambient_home):
                raise IncarnationHomeError(
                    "incarnation home is owned by another ambient Codex home"
                )
            if existing.get("ambient_home_identity") not in {None, ambient_identity}:
                raise IncarnationHomeError("incarnation ambient-home identity drift")
            if existing.get("model_realization_id") not in {
                None,
                realization.get("model_realization_id"),
            }:
                raise IncarnationHomeError("incarnation model realization identity drift")
            if existing.get("codex_home") != str(codex_home):
                raise IncarnationHomeError("incarnation home coordinate drift")
            existing_holder_binding = existing.get("holder_binding")
            if holder_context is None:
                if existing_holder_binding is not None:
                    raise IncarnationHomeError(
                        "typed holder binding context is required for this incarnation home"
                    )
            else:
                if not isinstance(existing_holder_binding, dict):
                    raise IncarnationHomeError(
                        "incarnation home lacks its typed holder binding"
                    )
                if existing_holder_binding.get("coordinate") != holder_coordinate:
                    raise IncarnationHomeError("incarnation holder binding drift")
                if existing_holder_binding.get("binding_digest") != holder_context_digest:
                    raise IncarnationHomeError("incarnation holder binding digest drift")
            _reject_claimed_home_repreparation(existing_marker)

    # Validate ambient inputs before creating a new content-addressed root. A
    # failed first preparation must not leave an unowned directory that blocks
    # the corrected retry.
    ambient_config = _regular_file(
        ambient_home / "config.toml", "ambient Codex config"
    ).read_bytes()
    config = _bound_config(ambient_config, model_slug, effort)
    # This snapshot is the bounded provenance boundary for the complete
    # materialization.  It must be captured before projection and retained
    # even if ambient pathnames are later unlinked and replaced.
    ambient_identities = _ambient_inode_identities(ambient_home)
    capability_projection = _build_capability_projection(
        ambient_home=ambient_home,
        ambient_home_identity=ambient_identity,
        model_realization_id=str(realization.get("model_realization_id")),
        incarnation_coordinate=coordinate,
        capability_grants=capability_grants,
    )
    projected_entries = {
        name: entry
        for name, entry in capability_projection["entries"].items()
        if entry["projection"] == "shared_link"
    }
    shared_names = sorted(projected_entries)
    actor_local_state_names = sorted(
        name
        for name, entry in capability_projection["entries"].items()
        if entry["projection"] == "denied"
    )
    previous_shared_names: set[str] = set()
    if isinstance(existing.get("shared_state_names"), list):
        previous_shared_names = {
            name
            for name in existing["shared_state_names"]
            if isinstance(name, str)
            and name not in LOCAL_NAMES
            and Path(name).name == name
        }
    if isinstance(existing.get("capability_projection"), dict):
        existing_entries = existing["capability_projection"].get("entries", {})
        if isinstance(existing_entries, dict):
            existing_entries_iter = existing_entries.values()
        elif isinstance(existing_entries, list):
            existing_entries_iter = existing_entries
        else:
            existing_entries_iter = ()
        for entry in existing_entries_iter:
            if (
                isinstance(entry, dict)
                and entry.get("projection") == "shared_link"
                and isinstance(entry.get("name"), str)
            ):
                previous_shared_names.add(entry["name"])

    if incarnation_root.exists() and not unpublished_root:
        if incarnation_root.is_symlink() or not incarnation_root.is_dir():
            raise IncarnationHomeError("incarnation root is not a real directory")
        if codex_home.exists() or codex_home.is_symlink():
            observed_home = _open_stable_actor_local_entry(codex_home, "codex-home")
            if not stat.S_ISDIR(observed_home.st_mode):
                raise IncarnationHomeError("incarnation Codex home is not a directory")
            prevalidated_names = [
                name
                for name in sorted(set(actor_local_state_names) | set(LOCAL_NAMES))
                if not (
                    name in previous_shared_names
                    and (codex_home / name).is_symlink()
                    and (codex_home / name).readlink() == ambient_home / name
                )
            ]
            _validate_actor_local_entries(
                codex_home,
                prevalidated_names,
                ambient_home,
                initially_ambient_identities=ambient_identities,
            )
        _validate_denied_state_provenance(
            manifest=existing,
            codex_home=codex_home,
            ambient_home=ambient_home,
            names=actor_local_state_names,
            required=existing.get("schema_version") == SCHEMA_VERSION,
            allow_projection_expansion=True,
        )
    elif not unpublished_root and (codex_home.exists() or codex_home.is_symlink()):
        raise IncarnationHomeError(
            "unpublished incarnation home requires an ownership token"
        )
    for name in sorted(previous_shared_names - set(shared_names)):
        target = codex_home / name
        source = ambient_home / name
        if not target.exists() and not target.is_symlink():
            continue
        if target.is_symlink() and target.readlink() == source:
            continue
        if name in actor_local_state_names:
            _validate_actor_local_entry(
                target,
                name,
                ambient_identities=ambient_identities,
            )
            continue
        raise IncarnationHomeError(
            f"obsolete capability projection link drift: {target}"
        )

    if holder_coordinate is not None:
        realization_root.mkdir(mode=0o700, exist_ok=True)
        if realization_root.is_symlink() or not realization_root.is_dir():
            raise IncarnationHomeError("realization incarnation root is not a real directory")
        realization_root.chmod(0o700)
    active_owner = _claim_preparation_root(
        incarnation_root=incarnation_root,
        ambient_home=ambient_home,
        realization_root=realization_root,
        runtime_root=runtime_root,
        coordinate=coordinate,
        holder_coordinate=holder_coordinate,
        ambient_identities=ambient_identities,
        owner_token=_owner_token,
    )

    codex_home.mkdir(mode=0o700, exist_ok=True)
    if incarnation_root.is_symlink() or codex_home.is_symlink():
        raise IncarnationHomeError("incarnation home may not be a symlink")
    _recover_abandoned_staged_files(
        codex_home,
        ambient_identities=ambient_identities,
    )
    incarnation_root.chmod(0o700)
    codex_home.chmod(0o700)
    for name in ("cache", "log", "tmp", DESCENDANT_BIN_NAME):
        local = codex_home / name
        if local.is_symlink():
            raise IncarnationHomeError(f"actor-local {name} is not a real directory")
        if not local.exists():
            local.mkdir(mode=0o700, exist_ok=False)
        if local.is_symlink() or not local.is_dir():
            raise IncarnationHomeError(f"actor-local {name} is not a real directory")
        local.chmod(0o700)

    _write_exact(
        codex_home / "config.toml",
        config,
        0o600,
        ambient_identities=ambient_identities,
    )

    for name in shared_names:
        source = ambient_home / name
        if source.is_symlink():
            raise IncarnationHomeError(
                f"ambient capability entry may not be a symlink: {source}"
            )
        target = codex_home / source.name
        if target.is_symlink():
            if target.readlink() != source:
                raise IncarnationHomeError(f"capability projection link drift: {target}")
        elif target.exists():
            raise IncarnationHomeError(
                f"capability projection target is not a symlink: {target}"
            )
        else:
            target.symlink_to(source)

    for name in sorted(previous_shared_names - set(shared_names)):
        target = codex_home / name
        source = ambient_home / name
        if not target.exists() and not target.is_symlink():
            continue
        if target.is_symlink() and target.readlink() == source:
            target.unlink()
            continue
        if name in actor_local_state_names:
            _validate_actor_local_entry(
                target,
                name,
                ambient_identities=ambient_identities,
            )
            continue
        if not target.is_symlink():
            raise IncarnationHomeError(
                f"obsolete capability projection link drift: {target}"
            )
        if target.readlink() != source:
            raise IncarnationHomeError(
                f"obsolete capability projection link drift: {target}"
            )

    expected_names = set(shared_names) | set(actor_local_state_names) | LOCAL_NAMES
    for entry in codex_home.iterdir():
        if entry.name not in expected_names:
            raise IncarnationHomeError(
                f"unexpected incarnation-home entry: {entry.name}"
            )
    _validate_actor_local_entries(
        codex_home,
        sorted(set(actor_local_state_names) | set(LOCAL_NAMES)),
        ambient_home,
        initially_ambient_identities=ambient_identities,
    )
    denied_provenance = _denied_state_provenance(
        codex_home=codex_home,
        ambient_home=ambient_home,
        names=actor_local_state_names,
        initially_ambient_identities=ambient_identities,
    )

    manifest = {
        "$schema": "schemas/external-codex-incarnation-home.schema.json",
        "schema_version": (
            SCHEMA_VERSION if holder_context is not None else LEGACY_SCHEMA_VERSION
        ),
        "model_realization_id": realization.get("model_realization_id"),
        "model_realization_ref": str(realization_path),
        "configuration_fingerprint": fingerprint,
        "model_slug": model_slug,
        "reasoning_effort": effort,
        "runtime_version": runtime_version,
        "ambient_codex_home": str(ambient_home),
        "ambient_home_identity": ambient_identity,
        "runtime_root": str(runtime_root),
        "codex_home": str(codex_home),
        "config_digest": sha256_bytes(config),
        "shared_state_names": shared_names,
        "actor_local_state_names": actor_local_state_names,
        "capability_projection": capability_projection,
        "top_level_posture": "incarnation-home",
        "child_posture": "incarnation-home-via-shell-environment-policy",
    }
    if holder_context is not None and holder_context_digest is not None:
        manifest["denied_state_provenance"] = denied_provenance
        manifest["holder_binding"] = _holder_binding_manifest_record(
            holder_context,
            holder_context_digest,
            holder_coordinate or "",
        )
    _write_exact(
        incarnation_root / "incarnation-home.json",
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n",
        0o600,
        ambient_identities=ambient_identities,
    )
    _finish_preparation_owner(active_owner)
    return manifest


def _rollback_unpublished_home(
    *,
    owner_token: dict[str, Any] | None,
) -> None:
    """Remove only the unpublished root carrying this attempt's exact token."""

    if owner_token is None:
        return
    incarnation_root = Path(str(owner_token["incarnation_root"]))
    realization_root = Path(str(owner_token["realization_root"]))
    runtime_root = Path(str(owner_token["runtime_root"]))
    coordinate = str(owner_token["coordinate"])
    holder_coordinate = owner_token.get("holder_coordinate")
    if incarnation_root.is_symlink() or not incarnation_root.is_dir():
        return
    marker = incarnation_root / "incarnation-home.json"
    if marker.exists() or marker.is_symlink():
        return
    owner_path = incarnation_root / PREPARATION_OWNER_FILE_NAME
    owner = _load_json(owner_path, "incarnation preparation owner token")
    _validate_preparation_owner_record(
        owner,
        ambient_home=Path(str(owner_token["ambient_home"])),
        runtime_root=runtime_root,
        realization_root=realization_root,
        incarnation_root=incarnation_root,
        coordinate=coordinate,
        holder_coordinate=holder_coordinate,
    )
    if owner != owner_token:
        raise IncarnationHomeError(
            "failed home preparation is owned by another attempt"
        )
    ambient_identities: set[tuple[int, int]] = set()
    ambient_path = owner_token.get("ambient_home")
    if isinstance(ambient_path, str):
        ambient = Path(ambient_path)
        if ambient.is_dir() and not ambient.is_symlink():
            ambient_identities = _ambient_inode_identities(ambient)
    _recover_stale_preparation_root(
        incarnation_root=incarnation_root,
        ambient_home=Path(str(owner_token["ambient_home"])),
        realization_root=realization_root,
        runtime_root=runtime_root,
        coordinate=coordinate,
        holder_coordinate=holder_coordinate,
        ambient_identities=ambient_identities,
    )
    _remove_empty_directory_if_stable(
        realization_root,
        "failed home preparation realization root",
    )


def prepare_home(
    *,
    ambient_home: Path,
    realization_path: Path,
    runtime_root: Path,
    capability_grants: Sequence[Path] = (),
    binding_context: Path | dict[str, Any] | None = None,
    holder_namespace: str | None = None,
) -> dict[str, Any]:
    """Prepare one home under a stable runtime lock and owner-token rollback."""

    ambient = _absolute_directory(ambient_home, "ambient Codex home")
    runtime = _absolute_directory(runtime_root, "runtime root")
    ambient_identities = _ambient_inode_identities(ambient)
    owner_token = None
    if holder_namespace is None:
        owner_token = _prepare_home_attempt_owner(
            ambient_home=ambient,
            realization_path=realization_path,
            runtime_root=runtime,
            binding_context=binding_context,
        )
    try:
        with _incarnation_preparation_lock(runtime, ambient_identities):
            try:
                return _prepare_home_impl(
                    ambient_home=ambient,
                    realization_path=realization_path,
                    runtime_root=runtime,
                    capability_grants=capability_grants,
                    binding_context=binding_context,
                    holder_namespace=holder_namespace,
                    _owner_token=owner_token,
                )
            except BaseException:
                _rollback_unpublished_home(owner_token=owner_token)
                raise
    except BaseException:
        raise


def _validate_holder_binding_manifest_record(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise IncarnationHomeError("incarnation-home holder binding is not an object")
    expected = {
        "schema_version",
        "binding_digest",
        "coordinate",
        "goal_ref",
        "actor_ref",
        "incarnation_ref",
        "session_ref",
        "runtime_state_root",
        "closeout_route",
        "holder_ref",
        "task_ref",
        "run_ref",
    }
    if set(value) != expected:
        raise IncarnationHomeError(
            "incarnation-home holder binding fields are not exact"
        )
    result = {
        key: _binding_ref(value.get(key), key)
        for key in expected - {"binding_digest", "coordinate"}
    }
    binding_digest = value.get("binding_digest")
    coordinate = value.get("coordinate")
    if not isinstance(binding_digest, str) or SHA256_DIGEST_PATTERN.fullmatch(
        binding_digest
    ) is None:
        raise IncarnationHomeError("incarnation-home holder binding digest is invalid")
    if not isinstance(coordinate, str) or SHA256_DIGEST_PATTERN.fullmatch(
        coordinate
    ) is None:
        raise IncarnationHomeError("incarnation-home holder binding coordinate is invalid")
    result["binding_digest"] = binding_digest
    result["coordinate"] = coordinate
    if result["schema_version"] != HOLDER_BINDING_CONTEXT_SCHEMA_VERSION:
        raise IncarnationHomeError("incarnation-home holder binding schema is invalid")
    expected_coordinate = _holder_binding_context_coordinate(
        result, result["binding_digest"]
    )
    if result["coordinate"] != expected_coordinate:
        raise IncarnationHomeError(
            "incarnation-home holder binding coordinate is not derived from context"
        )
    return result


def _load_manifest_snapshot(
    path: Path,
    *,
    snapshot_bytes: bytes | None = None,
    binding_context: dict[str, str] | None = None,
    binding_context_digest: str | None = None,
    require_holder_binding: bool = False,
) -> tuple[dict[str, Any], bytes, str]:
    if snapshot_bytes is None:
        manifest, raw = _load_json_snapshot(path, "incarnation-home manifest")
    else:
        raw = snapshot_bytes
        manifest = _decode_json_snapshot(
            raw, "incarnation-home manifest snapshot"
        )
    manifest_schema_version = manifest.get("schema_version")
    if manifest_schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise IncarnationHomeError("unsupported incarnation-home manifest")
    if manifest.get("$schema") != "schemas/external-codex-incarnation-home.schema.json":
        raise IncarnationHomeError("incarnation-home manifest schema binding is invalid")
    if manifest_schema_version == LEGACY_SCHEMA_VERSION:
        if require_holder_binding:
            raise IncarnationHomeError(
                "legacy v2 incarnation-home manifest requires migration before canonical launch"
            )
        if "denied_state_provenance" in manifest:
            raise IncarnationHomeError(
                "legacy v2 incarnation-home manifest cannot carry denied-state provenance"
            )
    holder_binding_value = manifest.get("holder_binding")
    if holder_binding_value is None:
        if require_holder_binding or manifest_schema_version == SCHEMA_VERSION:
            raise IncarnationHomeError(
                "incarnation-home manifest lacks a typed holder binding"
            )
        holder_coordinate = manifest.get("holder_namespace_coordinate")
        if holder_coordinate is not None and (
            not isinstance(holder_coordinate, str)
            or SHA256_DIGEST_PATTERN.fullmatch(holder_coordinate) is None
        ):
            raise IncarnationHomeError("legacy holder coordinate is invalid")
        holder_binding: dict[str, str] | None = None
    else:
        holder_binding = _validate_holder_binding_manifest_record(holder_binding_value)
        holder_coordinate = holder_binding["coordinate"]
    if binding_context is not None:
        binding_context = _validate_holder_binding_context(binding_context)
        if binding_context_digest is None:
            binding_context_digest = sha256_bytes(canonical_bytes(binding_context))
        expected_coordinate = _holder_binding_context_coordinate(
            binding_context, binding_context_digest
        )
        if holder_binding is None:
            raise IncarnationHomeError(
                "manifest holder binding is missing for the supplied context"
            )
        expected_binding = _holder_binding_manifest_record(
            binding_context,
            binding_context_digest,
            expected_coordinate,
        )
        if holder_binding != expected_binding:
            raise IncarnationHomeError(
                "incarnation-home manifest holder binding does not match context"
            )
    codex_home = _absolute_directory(Path(str(manifest.get("codex_home"))), "incarnation Codex home")
    ambient_home = _absolute_directory(
        Path(str(manifest.get("ambient_codex_home"))), "ambient Codex home"
    )
    config = _regular_file(codex_home / "config.toml", "incarnation Codex config")
    if sha256_bytes(config.read_bytes()) != manifest.get("config_digest"):
        raise IncarnationHomeError("incarnation Codex config drift")
    if codex_home == ambient_home:
        raise IncarnationHomeError("incarnation and ambient Codex homes must be distinct")
    if manifest.get("ambient_home_identity") != _ambient_home_identity(ambient_home):
        raise IncarnationHomeError("ambient Codex home identity drift")
    runtime_root = _absolute_directory(
        Path(str(manifest.get("runtime_root"))), "runtime root"
    )
    try:
        realization, model_slug, effort, runtime_version, fingerprint = _realization(
            Path(str(manifest.get("model_realization_ref")))
        )
    except IncarnationHomeError:
        raise
    if (
        manifest.get("configuration_fingerprint") != fingerprint
        or manifest.get("model_realization_id")
        != realization.get("model_realization_id")
        or manifest.get("model_slug") != model_slug
        or manifest.get("reasoning_effort") != effort
        or manifest.get("runtime_version") != runtime_version
    ):
        raise IncarnationHomeError("model realization binding drift")
    incarnation_coordinate = _incarnation_coordinate(
        str(realization.get("model_realization_id")), fingerprint
    )
    if binding_context is not None and Path(
        binding_context["runtime_state_root"]
    ).resolve() != runtime_root:
        raise IncarnationHomeError(
            "holder binding runtime state root does not match manifest runtime root"
        )
    realization_root = _holder_incarnation_root(
        runtime_root=runtime_root,
        incarnation_coordinate=incarnation_coordinate,
        holder_coordinate=None,
    )
    expected_root = _holder_incarnation_root(
        runtime_root=runtime_root,
        incarnation_coordinate=incarnation_coordinate,
        holder_coordinate=holder_coordinate,
    )
    if realization_root.is_symlink() or expected_root.is_symlink():
        raise IncarnationHomeError("incarnation root may not be a symlink")
    expected_manifest = expected_root / "incarnation-home.json"
    if path.resolve() != expected_manifest.resolve():
        raise IncarnationHomeError(
            "incarnation-home manifest path is not its derived binding path"
        )
    expected_home = (expected_root / "codex-home").resolve()
    if codex_home != expected_home:
        raise IncarnationHomeError("incarnation Codex home is not derived from realization")
    try:
        scoped_config = tomllib.loads(config.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise IncarnationHomeError("incarnation Codex config is not valid TOML") from exc
    _reject_custom_model_provider(scoped_config)
    try:
        ambient_config = tomllib.loads(
            (ambient_home / "config.toml").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise IncarnationHomeError("ambient Codex config is not valid TOML") from exc
    _reject_custom_model_provider(ambient_config)
    if (
        scoped_config.get("model") != model_slug
        or scoped_config.get("model_reasoning_effort") != effort
        or not isinstance(scoped_config.get("features"), dict)
        or scoped_config["features"].get("multi_agent") is not False
    ):
        raise IncarnationHomeError("scoped Codex config binding drift")
    capability_projection = manifest.get("capability_projection")
    manifest_entries = (
        capability_projection.get("entries")
        if isinstance(capability_projection, dict)
        else None
    )
    manifest_entry_values = (
        manifest_entries.values() if isinstance(manifest_entries, dict) else ()
    )
    expected_capability_projection = _build_capability_projection(
        ambient_home=ambient_home,
        ambient_home_identity=str(manifest.get("ambient_home_identity")),
        model_realization_id=str(realization.get("model_realization_id")),
        incarnation_coordinate=_incarnation_coordinate(
            str(realization.get("model_realization_id")), fingerprint
        ),
        capability_grants=[
            Path(str(grant.get("path")))
            for entry in manifest_entry_values
            if isinstance(entry, dict)
            for grant in [entry.get("explicit_grant")]
            if isinstance(grant, dict) and isinstance(grant.get("path"), str)
        ],
    )
    if capability_projection != expected_capability_projection:
        raise IncarnationHomeError("capability projection drift")

    shared_names = manifest.get("shared_state_names")
    if (
        not isinstance(shared_names, list)
        or any(
            not isinstance(name, str)
            or not name
            or name in {".", ".."}
            or name in LOCAL_NAMES
            or Path(name).name != name
            for name in shared_names
        )
        or len(set(shared_names)) != len(shared_names)
    ):
        raise IncarnationHomeError("shared-state manifest is invalid")
    expected_shared_names = sorted(
        name
        for name, entry in expected_capability_projection["entries"].items()
        if entry["projection"] == "shared_link"
    )
    if sorted(shared_names) != expected_shared_names:
        raise IncarnationHomeError(
            "shared-state manifest no longer matches capability projection"
        )
    expected_actor_local_names = sorted(
        name
        for name, entry in expected_capability_projection["entries"].items()
        if entry["projection"] == "denied"
    )
    actor_local_names = manifest.get("actor_local_state_names")
    if actor_local_names is None:
        if manifest_schema_version == SCHEMA_VERSION:
            raise IncarnationHomeError(
                "current incarnation-home manifest lacks actor-local state names"
            )
        # Pre-repair v2 manifests did not name the derived denied-state set.
        # Recompute it only on the explicitly legacy compatibility route.
        actor_local_names = expected_actor_local_names
    elif (
        not isinstance(actor_local_names, list)
        or any(
            not isinstance(name, str)
            or not name
            or name in {".", ".."}
            or name in LOCAL_NAMES
            or Path(name).name != name
            for name in actor_local_names
        )
        or len(set(actor_local_names)) != len(actor_local_names)
    ):
        raise IncarnationHomeError("actor-local state manifest is invalid")
    if sorted(actor_local_names) != expected_actor_local_names:
        raise IncarnationHomeError(
            "actor-local state manifest no longer matches capability projection"
        )
    _validate_denied_state_provenance(
        manifest=manifest,
        codex_home=codex_home,
        ambient_home=ambient_home,
        names=actor_local_names,
        required=manifest_schema_version == SCHEMA_VERSION,
    )
    expected_names = set(shared_names) | set(actor_local_names) | LOCAL_NAMES
    for entry in codex_home.iterdir():
        if entry.name not in expected_names:
            raise IncarnationHomeError(
                f"unexpected incarnation-home entry: {entry.name}"
            )
    for name in shared_names:
        source = ambient_home / name
        target = codex_home / name
        if (
            not source.exists()
            or source.is_symlink()
            or not target.is_symlink()
            or target.readlink() != source
        ):
            raise IncarnationHomeError(f"capability projection link drift: {target}")
    for name in LOCAL_NAMES - {"config.toml"}:
        local = codex_home / name
        if local.is_symlink() or not local.is_dir():
            raise IncarnationHomeError(f"actor-local {name} is not a real directory")
    _validate_actor_local_entries(
        codex_home,
        sorted(set(actor_local_names) | set(LOCAL_NAMES)),
        ambient_home,
    )
    return manifest, raw, sha256_bytes(raw)


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest, _, _ = _load_manifest_snapshot(path)
    return manifest


def _resolved_executable(codex_executable: Path) -> Path:
    if not codex_executable.is_absolute():
        raise IncarnationHomeError(
            f"Codex executable must be absolute: {codex_executable}"
        )
    try:
        executable = codex_executable.resolve(strict=True)
    except OSError as exc:
        raise IncarnationHomeError(
            f"Codex executable cannot be resolved: {codex_executable}"
        ) from exc
    if not executable.is_file():
        raise IncarnationHomeError(
            f"Codex executable is not a regular file: {codex_executable}"
        )
    if not os.access(executable, os.X_OK):
        raise IncarnationHomeError("Codex executable is not executable")
    return executable


def _remove_named_snapshot(
    snapshot_path: Path,
    *,
    snapshot_dir: Path | None = None,
    snapshot_dir_fd: int | None = None,
) -> None:
    cleanup_dir = snapshot_dir
    if cleanup_dir is not None:
        try:
            if snapshot_dir_fd is not None:
                expected = os.fstat(snapshot_dir_fd)
                observed = os.lstat(cleanup_dir)
                if (
                    not stat.S_ISDIR(expected.st_mode)
                    or not stat.S_ISDIR(observed.st_mode)
                    or (expected.st_dev, expected.st_ino)
                    != (observed.st_dev, observed.st_ino)
                ):
                    return
            if (
                cleanup_dir.is_symlink()
                or not cleanup_dir.is_dir()
                or not cleanup_dir.name.startswith("abyss-stack-codex-package-")
            ):
                return
            snapshot_path.relative_to(cleanup_dir)
            os.chmod(cleanup_dir, 0o700)
        except (OSError, ValueError):
            return
    if cleanup_dir is not None:
        try:
            def remove_tree(root: Path) -> None:
                os.chmod(root, 0o700)
                with os.scandir(root) as entries:
                    for entry in entries:
                        child = Path(entry.path)
                        if entry.is_symlink():
                            child.unlink(missing_ok=True)
                        elif entry.is_dir(follow_symlinks=False):
                            remove_tree(child)
                        else:
                            child.unlink(missing_ok=True)
                os.chmod(root, 0o700)
                root.rmdir()

            remove_tree(cleanup_dir)
        except OSError:
            return
        sync_path = cleanup_dir.parent
    else:
        try:
            snapshot_path.unlink(missing_ok=True)
        except OSError:
            return
        sync_path = snapshot_path.parent
    try:
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW
        directory_fd = os.open(sync_path, directory_flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        pass


def _spawn_named_snapshot_cleanup(
    *,
    snapshot_path: Path,
    snapshot_dir: Path | None = None,
    holder_pid: int,
    holder_start_ticks: int,
    snapshot_fd: int,
    snapshot_component_fds: Sequence[int] = (),
) -> int:
    """Remove one package-relative snapshot after the exact holder exits."""

    try:
        child_pid = os.fork()
    except OSError as exc:
        raise IncarnationHomeError(
            "cannot start named executable snapshot cleanup"
        ) from exc
    if child_pid != 0:
        return child_pid
    try:
        while Path(f"/proc/{holder_pid}").exists():
            try:
                state = _proc_identity_state(holder_pid, holder_start_ticks)
            except IncarnationHomeError:
                time.sleep(0.25)
                continue
            if state != "live":
                break
            time.sleep(0.25)
        cleanup_path = snapshot_path
        cleanup_dir = snapshot_dir
        if snapshot_dir is not None:
            try:
                bound_dir = Path(os.readlink(f"/proc/self/fd/{snapshot_fd}"))
            except OSError:
                bound_dir = snapshot_dir
            if bound_dir.is_absolute() and not str(bound_dir).endswith(" (deleted)"):
                try:
                    relative = snapshot_path.relative_to(snapshot_dir)
                except ValueError:
                    relative = Path(snapshot_path.name)
                cleanup_dir = bound_dir
                cleanup_path = bound_dir / relative
        _remove_named_snapshot(
            cleanup_path,
            snapshot_dir=cleanup_dir,
            snapshot_dir_fd=snapshot_fd if snapshot_dir is not None else None,
        )
    except BaseException:
        pass
    finally:
        for fd in snapshot_component_fds:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.close(snapshot_fd)
        except OSError:
            pass
        os._exit(0)


def _execution_snapshot_root(preferred: Path | None) -> Path:
    root = Path(preferred) if preferred is not None else Path(tempfile.gettempdir())
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise IncarnationHomeError(
            f"shebang snapshot root must be an absolute real directory: {root}"
        )
    try:
        flags = os.statvfs(root).f_flag
    except OSError as exc:
        raise IncarnationHomeError(
            f"shebang snapshot filesystem could not be inspected: {root}"
        ) from exc
    noexec = getattr(os, "ST_NOEXEC", 0)
    if isinstance(noexec, int) and noexec and flags & noexec:
        raise IncarnationHomeError(
            f"shebang snapshot filesystem is mounted noexec: {root}"
        )
    return root


def _package_root(executable: Path) -> Path:
    """Find the nearest package boundary without following a marker link."""

    for candidate in (executable.parent, *executable.parent.parents):
        if candidate == Path("/"):
            break
        marker = candidate / "package.json"
        if marker.is_symlink():
            raise IncarnationHomeError(
                f"package marker may not be a symlink: {marker}"
            )
        if marker.is_file():
            return candidate
    return executable.parent


def _sealed_memfd(name: str, content: bytes, *, mode: int = 0o400) -> int:
    memfd_create = getattr(os, "memfd_create", None)
    allow_sealing = getattr(os, "MFD_ALLOW_SEALING", None)
    add_seals = getattr(fcntl, "F_ADD_SEALS", None)
    seal_write = getattr(fcntl, "F_SEAL_WRITE", None)
    seal_grow = getattr(fcntl, "F_SEAL_GROW", None)
    seal_shrink = getattr(fcntl, "F_SEAL_SHRINK", None)
    seal_seal = getattr(fcntl, "F_SEAL_SEAL", None)
    if (
        not callable(memfd_create)
        or not isinstance(allow_sealing, int)
        or not isinstance(add_seals, int)
        or not all(
            isinstance(value, int)
            for value in (seal_write, seal_grow, seal_shrink, seal_seal)
        )
    ):
        raise IncarnationHomeError(
            "shebang dependency snapshot requires sealed memfd support"
        )
    descriptor: int | None = None
    try:
        descriptor = memfd_create(name, allow_sealing)
        view = memoryview(content)
        while view:
            view = view[os.write(descriptor, view) :]
        os.fsync(descriptor)
        os.fchmod(descriptor, mode)
        fcntl.fcntl(
            descriptor,
            add_seals,
            seal_write | seal_grow | seal_shrink | seal_seal,
        )
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.set_inheritable(descriptor, True)
        return descriptor
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise IncarnationHomeError(
            f"shebang dependency could not be sealed: {name}"
        ) from exc


def _read_verified_regular_file(
    source: Path, *, label: str
) -> tuple[bytes, os.stat_result]:
    """Read one regular file while binding its identity and bytes together."""

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(source, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise IncarnationHomeError(f"{label} is not a regular file: {source}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            stat.S_IMODE(before.st_mode),
        )
        observed_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            stat.S_IMODE(after.st_mode),
        )
        if identity != observed_identity:
            raise IncarnationHomeError(f"{label} changed while reading: {source}")
        return b"".join(chunks), before
    except IncarnationHomeError:
        raise
    except OSError as exc:
        raise IncarnationHomeError(f"{label} could not be read: {source}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _adjacent_code_mode_host(
    executable: Path,
) -> tuple[Path, bytes, dict[str, str]] | None:
    """Return the exact owner-bound companion beside a Codex executable."""

    companion = executable.parent / CODE_MODE_HOST_NAME
    try:
        info = companion.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise IncarnationHomeError(
            f"Codex companion could not be inspected: {companion}"
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise IncarnationHomeError(
            f"Codex companion must be a non-symlink regular file: {companion}"
        )
    if not stat.S_IMODE(info.st_mode) & 0o111:
        raise IncarnationHomeError(f"Codex companion is not executable: {companion}")
    if not os.access(companion, os.X_OK):
        raise IncarnationHomeError(
            f"Codex companion is not executable by the current user: {companion}"
        )
    content, opened_info = _read_verified_regular_file(
        companion, label="Codex companion"
    )
    resolved = companion.resolve(strict=True)
    if (
        opened_info.st_dev != info.st_dev
        or opened_info.st_ino != info.st_ino
        or stat.S_IMODE(opened_info.st_mode) != stat.S_IMODE(info.st_mode)
        or not stat.S_IMODE(opened_info.st_mode) & 0o111
        or resolved.parent != executable.parent
        or resolved.name != CODE_MODE_HOST_NAME
    ):
        raise IncarnationHomeError(
            f"Codex companion identity changed before binding: {companion}"
        )
    return (
        resolved,
        content,
        {
            "path": str(resolved),
            "digest": sha256_bytes(content),
            "relation": "adjacent_immutable_package",
            "package_relative": resolved.relative_to(
                _package_root(executable)
            ).as_posix(),
        },
    )


def _copy_package_file(
    source: Path,
    target: Path,
    *,
    records: dict[Path, tuple[int, int, str, int]],
) -> None:
    source_flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        source_flags |= os.O_NOFOLLOW
    source_fd: int | None = None
    target_fd: int | None = None
    try:
        source_fd = os.open(source, source_flags)
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode):
            raise IncarnationHomeError(
                f"package snapshot source is not a regular file: {source}"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(source_fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(source_fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            stat.S_IMODE(before.st_mode),
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            stat.S_IMODE(after.st_mode),
        ):
            raise IncarnationHomeError(
                f"package snapshot source changed while reading: {source}"
            )
        content = b"".join(chunks)
        target_mode = 0o500 if os.access(source, os.X_OK) else 0o400
        target_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            target_flags |= os.O_NOFOLLOW
        target_fd = os.open(target, target_flags, target_mode)
        view = memoryview(content)
        while view:
            view = view[os.write(target_fd, view) :]
        os.fsync(target_fd)
        os.fchmod(target_fd, target_mode)
        os.fsync(target_fd)
        target_info = os.fstat(target_fd)
        records[target] = (
            target_info.st_dev,
            target_info.st_ino,
            sha256_bytes(content),
            target_mode,
        )
    except IncarnationHomeError:
        raise
    except OSError as exc:
        raise IncarnationHomeError(
            f"package dependency could not be snapshotted: {source}"
        ) from exc
    finally:
        if target_fd is not None:
            os.close(target_fd)
        if source_fd is not None:
            os.close(source_fd)


def _copy_package_tree(
    source: Path,
    target: Path,
    *,
    excluded: Path,
    ignored_source: Path,
    records: dict[Path, tuple[int, int, str, int]],
) -> None:
    """Copy a package subtree without retaining mutable dependency links."""

    if source.is_symlink() or not source.is_dir():
        raise IncarnationHomeError(
            f"package snapshot root is not a real directory: {source}"
        )
    if target.is_symlink():
        raise IncarnationHomeError(
            f"package snapshot target is a symlink: {target}"
        )
    if not target.exists():
        target.mkdir(mode=0o700)
    if not target.is_dir():
        raise IncarnationHomeError(
            f"package snapshot target is not a directory: {target}"
        )
    target_info = os.stat(target, follow_symlinks=False)
    if not stat.S_ISDIR(target_info.st_mode):
        raise IncarnationHomeError(
            f"package snapshot target is not a real directory: {target}"
        )
    records.setdefault(target, (target_info.st_dev, target_info.st_ino, "", 0))
    for entry in sorted(source.iterdir(), key=lambda item: item.name):
        if entry == excluded or entry == ignored_source:
            continue
        target_entry = target / entry.name
        if entry.is_symlink():
            raise IncarnationHomeError(
                f"package dependency may not be a symlink: {entry}"
            )
        if entry.is_dir():
            _copy_package_tree(
                entry,
                target_entry,
                excluded=excluded,
                ignored_source=ignored_source,
                records=records,
            )
        elif entry.is_file():
            _copy_package_file(entry, target_entry, records=records)
        else:
            raise IncarnationHomeError(
                f"package dependency is not a regular file or directory: {entry}"
            )


def _mirror_package_layout(
    *, executable: Path, snapshot_root: Path
) -> tuple[Path, Path, dict[Path, tuple[int, int, str, int]], Path]:
    """Build a private package snapshot with stable ancestor coordinates.

    Only the directory coordinates needed to reach the admitted package are
    created.  Mirroring unrelated siblings as symlinks would retain the
    mutable host ancestor tree inside a frozen snapshot and make cleanup
    depend on unrelated packages and prior snapshots.
    """

    snapshot_dir = Path(
        tempfile.mkdtemp(prefix="abyss-stack-codex-package-", dir=snapshot_root)
    )
    try:
        os.chmod(snapshot_dir, 0o700)
        source_dir = Path("/")
        target_dir = snapshot_dir
        records: dict[Path, tuple[int, int, str, int]] = {}
        package_root = _package_root(executable)
        source_parts = package_root.parts
        if not source_parts or source_parts[0] != "/":
            raise IncarnationHomeError("shebang executable parent must be absolute")
        for component in source_parts[1:]:
            source_dir = source_dir / component
            target_dir = target_dir / component
            target_dir.mkdir(mode=0o700)
        _copy_package_tree(
            source_dir,
            target_dir,
            excluded=executable,
            ignored_source=snapshot_dir,
            records=records,
        )
        return (
            target_dir / executable.relative_to(package_root),
            snapshot_dir,
            records,
            target_dir,
        )
    except BaseException:
        _remove_named_snapshot(
            snapshot_dir / executable.name, snapshot_dir=snapshot_dir
        )
        raise


def _freeze_snapshot_tree(snapshot_dir: Path) -> None:
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    for root, _directories, _files in os.walk(snapshot_dir, followlinks=False):
        directory = Path(root)
        os.chmod(directory, 0o500)
        directory_fd = os.open(directory, directory_flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def _open_snapshot_mount(
    *,
    snapshot_path: Path,
    snapshot_dir: Path,
    package_root: Path,
    records: dict[Path, tuple[int, int, str, int]],
    companion_binding: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Open every copied component and seal every regular file for bwrap."""

    try:
        snapshot_path.relative_to(package_root)
        package_root.relative_to(snapshot_dir)
    except ValueError as exc:
        raise IncarnationHomeError(
            "named executable snapshot package boundary escaped its private mirror"
        ) from exc
    directory_flags = getattr(os, "O_PATH", os.O_RDONLY)
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    file_flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        file_flags |= os.O_NOFOLLOW
    directory_paths: list[Path] = []
    file_fds: list[tuple[Path, int, int]] = []
    try:
        directory_records = sorted(
            (
                (path, identity)
                for path, identity in records.items()
                if identity[2] == "" and path.is_relative_to(package_root)
            ),
            key=lambda item: (len(item[0].parts), os.fspath(item[0])),
        )
        if package_root not in {path for path, _ in directory_records}:
            raise IncarnationHomeError(
                "package snapshot boundary was not recorded as a directory"
            )
        for path, expected in directory_records:
            descriptor = os.open(path, directory_flags)
            observed = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(observed.st_mode)
                or (observed.st_dev, observed.st_ino) != expected[:2]
            ):
                os.close(descriptor)
                raise IncarnationHomeError(
                    f"package snapshot directory changed before binding: {path}"
                )
            os.close(descriptor)
            directory_paths.append(path.relative_to(package_root))

        file_records = sorted(
            (
                (path, identity)
                for path, identity in records.items()
                if identity[2] and path.is_relative_to(package_root)
            ),
            key=lambda item: os.fspath(item[0]),
        )
        for path, expected in file_records:
            source_fd = os.open(path, file_flags)
            try:
                observed = os.fstat(source_fd)
                if (
                    not stat.S_ISREG(observed.st_mode)
                    or (observed.st_dev, observed.st_ino) != expected[:2]
                ):
                    raise IncarnationHomeError(
                        f"package snapshot file changed before binding: {path}"
                    )
                os.lseek(source_fd, 0, os.SEEK_SET)
                chunks: list[bytes] = []
                while True:
                    chunk = os.read(source_fd, 1 << 20)
                    if not chunk:
                        break
                    chunks.append(chunk)
                content = b"".join(chunks)
                if sha256_bytes(content) != expected[2]:
                    raise IncarnationHomeError(
                        f"package snapshot file bytes changed before binding: {path}"
                    )
            finally:
                os.close(source_fd)
            descriptor = _sealed_memfd(
                f"aoa-codex-shebang-{path.name}",
                content,
                mode=expected[3],
            )
            file_fds.append(
                (path.relative_to(package_root), descriptor, expected[3])
            )
        if companion_binding is not None:
            companion_relative = Path(companion_binding["package_relative"])
            if companion_relative.is_absolute() or ".." in companion_relative.parts:
                raise IncarnationHomeError(
                    "Codex companion escaped the executable package boundary"
                )
            copied_companion = package_root / companion_relative
            expected_companion = records.get(copied_companion)
            if expected_companion is None or expected_companion[2] != companion_binding[
                "digest"
            ]:
                raise IncarnationHomeError(
                    "Codex companion bytes were not retained in the package snapshot"
                )
        return {
            "directory_paths": directory_paths,
            "file_fds": file_fds,
            "namespace_root": Path("/var/tmp"),
            "executable_path": Path("/var/tmp")
            / snapshot_path.relative_to(package_root),
            "companion": companion_binding,
        }
    except BaseException:
        for _, descriptor, _ in file_fds:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _memory_package_mount(
    *,
    executable: Path,
    executable_fd: int,
    executable_mode: int,
    companion: Path,
    companion_fd: int,
    companion_mode: int,
    companion_binding: dict[str, str],
) -> dict[str, Any]:
    """Build a private package coordinate from sealed ELF descriptors."""

    package_relative = Path("codex-package")
    executable_relative = package_relative / executable.name
    companion_relative = package_relative / companion.name
    if companion.parent != executable.parent or companion.name != CODE_MODE_HOST_NAME:
        raise IncarnationHomeError("Codex companion is not adjacent to the executable")
    return {
        "directory_paths": [package_relative],
        "file_fds": [
            (executable_relative, executable_fd, executable_mode),
            (companion_relative, companion_fd, companion_mode),
        ],
        "namespace_root": Path("/var/tmp"),
        "executable_path": Path("/var/tmp") / executable_relative,
        "companion": companion_binding,
    }


def _snapshot_bwrap_prefix(snapshot_mount: dict[str, Any]) -> list[str]:
    """Build a mount-namespace prefix with inode-bound package components."""

    bwrap = Path("/usr/bin/bwrap")
    if not bwrap.is_file() or not os.access(bwrap, os.X_OK):
        raise IncarnationHomeError("shebang launch requires /usr/bin/bwrap")
    namespace_root = snapshot_mount["namespace_root"]
    arguments = [
        os.fspath(bwrap),
        "--die-with-parent",
        "--bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--tmpfs",
        os.fspath(namespace_root),
    ]
    for relative in sorted(
        snapshot_mount["directory_paths"],
        key=lambda path: (len(path.parts), os.fspath(path)),
    ):
        if relative == Path("."):
            continue
        arguments.extend(["--dir", os.fspath(namespace_root / relative)])
    for relative, descriptor, mode in snapshot_mount["file_fds"]:
        arguments.extend(
            [
                "--file",
                str(descriptor),
                os.fspath(namespace_root / relative),
                "--chmod",
                f"{mode:04o}",
                os.fspath(namespace_root / relative),
            ]
        )
    arguments.extend(["--remount-ro", os.fspath(namespace_root)])
    return arguments


def _close_snapshot_mount(snapshot_mount: dict[str, Any] | None) -> None:
    if snapshot_mount is None:
        return
    descriptors: set[int] = {
        int(descriptor) for _, descriptor, _ in snapshot_mount["file_fds"]
    }
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _rewind_snapshot_components(snapshot_component_fds: Sequence[int]) -> None:
    for descriptor in snapshot_component_fds:
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
        except OSError as exc:
            raise IncarnationHomeError(
                "shebang snapshot component could not be rewound"
            ) from exc


def _open_verified_executable(
    executable: Path,
    *,
    snapshot_root: Path | None = None,
) -> tuple[int, Path, bytes, str, Path | None, Path | None, dict[str, Any] | None]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    source_fd: int | None = None
    snapshot_fd: int | None = None
    try:
        source_fd = os.open(executable, flags)
        info = os.fstat(source_fd)
        if not stat.S_ISREG(info.st_mode):
            raise IncarnationHomeError(
                f"Codex executable is not a regular file: {executable}"
            )
        os.lseek(source_fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(source_fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        content = b"".join(chunks)
        companion_data = _adjacent_code_mode_host(executable)
        if companion_data is not None:
            rebound_content, rebound_info = _read_verified_regular_file(
                executable, label="Codex executable"
            )
            if (
                rebound_info.st_dev != info.st_dev
                or rebound_info.st_ino != info.st_ino
                or rebound_content != content
            ):
                raise IncarnationHomeError(
                    "Codex executable changed while binding companion"
                )
        else:
            rebound_content, rebound_info = _read_verified_regular_file(
                executable, label="Codex executable"
            )
            if (
                rebound_info.st_dev != info.st_dev
                or rebound_info.st_ino != info.st_ino
                or rebound_content != content
            ):
                raise IncarnationHomeError(
                    "Codex executable changed while binding companion"
                )
            if _adjacent_code_mode_host(executable) is not None:
                raise IncarnationHomeError(
                    "Codex companion appeared while binding executable"
                )
        if content.startswith(b"#!"):
            snapshot_path: Path | None = None
            snapshot_dir: Path | None = None
            snapshot_root_fd: int | None = None
            snapshot_mount: dict[str, Any] | None = None
            try:
                (
                    snapshot_path,
                    snapshot_dir,
                    snapshot_records,
                    snapshot_package_root,
                ) = _mirror_package_layout(
                    executable=executable,
                    snapshot_root=_execution_snapshot_root(snapshot_root),
                )
                snapshot_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    snapshot_flags |= os.O_NOFOLLOW
                snapshot_fd = os.open(snapshot_path, snapshot_flags, 0o500)
                view = memoryview(content)
                while view:
                    view = view[os.write(snapshot_fd, view) :]
                os.fsync(snapshot_fd)
                os.fchmod(snapshot_fd, 0o500)
                os.fsync(snapshot_fd)
                snapshot_info = os.fstat(snapshot_fd)
                snapshot_records[snapshot_path] = (
                    snapshot_info.st_dev,
                    snapshot_info.st_ino,
                    sha256_bytes(content),
                    0o500,
                )
                _freeze_snapshot_tree(snapshot_dir)
                # A shebang interpreter must reopen a named path. Every
                # actual directory from the private mirror root through the
                # launcher's parent is frozen before that reopen, so a normal
                # same-user rename cannot replace the verified final entry.
                os.close(snapshot_fd)
                snapshot_fd = None
                snapshot_fd = os.open(snapshot_path, os.O_RDONLY)
                if hasattr(os, "O_NOFOLLOW"):
                    os.close(snapshot_fd)
                    snapshot_fd = None
                    snapshot_fd = os.open(
                        snapshot_path, os.O_RDONLY | os.O_NOFOLLOW
                    )
                info = os.fstat(snapshot_fd)
                if not stat.S_ISREG(info.st_mode):
                    raise IncarnationHomeError(
                        "named executable snapshot is not a regular file"
                    )
                os.lseek(snapshot_fd, 0, os.SEEK_SET)
                observed: list[bytes] = []
                while True:
                    chunk = os.read(snapshot_fd, 1 << 20)
                    if not chunk:
                        break
                    observed.append(chunk)
                if b"".join(observed) != content:
                    raise IncarnationHomeError(
                        "named executable snapshot bytes changed before exec"
                    )
                snapshot_mount = _open_snapshot_mount(
                    snapshot_path=snapshot_path,
                    snapshot_dir=snapshot_dir,
                    package_root=snapshot_package_root,
                    records=snapshot_records,
                    companion_binding=(
                        companion_data[2] if companion_data is not None else None
                    ),
                )
                directory_flags = os.O_RDONLY
                if hasattr(os, "O_DIRECTORY"):
                    directory_flags |= os.O_DIRECTORY
                if hasattr(os, "O_NOFOLLOW"):
                    directory_flags |= os.O_NOFOLLOW
                snapshot_root_fd = os.open(snapshot_dir, directory_flags)
                os.set_inheritable(snapshot_root_fd, True)
                execution_path = snapshot_mount["executable_path"]
                os.close(snapshot_fd)
                snapshot_fd = None
                return (
                    snapshot_root_fd,
                    execution_path,
                    content,
                    sha256_bytes(content),
                    snapshot_dir,
                    snapshot_path,
                    snapshot_mount,
                )
            except IncarnationHomeError:
                if snapshot_fd is not None:
                    os.close(snapshot_fd)
                    snapshot_fd = None
                if snapshot_root_fd is not None:
                    os.close(snapshot_root_fd)
                    snapshot_root_fd = None
                _close_snapshot_mount(snapshot_mount)
                if snapshot_path is not None:
                    _remove_named_snapshot(
                        snapshot_path, snapshot_dir=snapshot_dir
                    )
                raise
            except OSError as exc:
                if snapshot_fd is not None:
                    os.close(snapshot_fd)
                    snapshot_fd = None
                if snapshot_root_fd is not None:
                    os.close(snapshot_root_fd)
                    snapshot_root_fd = None
                _close_snapshot_mount(snapshot_mount)
                if snapshot_path is not None:
                    _remove_named_snapshot(
                        snapshot_path, snapshot_dir=snapshot_dir
                    )
                raise IncarnationHomeError(
                    "Codex shebang executable could not be snapshotted in a private package mirror"
                ) from exc
        if companion_data is not None:
            companion_path, companion_content, companion_binding = companion_data
            executable_mode = 0o500
            companion_mode = 0o500
            executable_fd = _sealed_memfd(
                "abyss-stack-codex-executable", content, mode=executable_mode
            )
            companion_fd: int | None = None
            try:
                companion_fd = _sealed_memfd(
                    "abyss-stack-codex-code-mode-host",
                    companion_content,
                    mode=companion_mode,
                )
                snapshot_mount = _memory_package_mount(
                    executable=executable,
                    executable_fd=executable_fd,
                    executable_mode=executable_mode,
                    companion=companion_path,
                    companion_fd=companion_fd,
                    companion_mode=companion_mode,
                    companion_binding=companion_binding,
                )
                os.lseek(executable_fd, 0, os.SEEK_SET)
                os.lseek(companion_fd, 0, os.SEEK_SET)
                return (
                    executable_fd,
                    snapshot_mount["executable_path"],
                    content,
                    sha256_bytes(content),
                    None,
                    None,
                    snapshot_mount,
                )
            except BaseException:
                if companion_fd is not None:
                    os.close(companion_fd)
                os.close(executable_fd)
                raise
        memfd_create = getattr(os, "memfd_create", None)
        allow_sealing = getattr(os, "MFD_ALLOW_SEALING", None)
        add_seals = getattr(fcntl, "F_ADD_SEALS", None)
        seal_write = getattr(fcntl, "F_SEAL_WRITE", None)
        seal_grow = getattr(fcntl, "F_SEAL_GROW", None)
        seal_shrink = getattr(fcntl, "F_SEAL_SHRINK", None)
        seal_seal = getattr(fcntl, "F_SEAL_SEAL", None)
        if (
            not callable(memfd_create)
            or not isinstance(allow_sealing, int)
            or not isinstance(add_seals, int)
            or not all(
                isinstance(value, int)
                for value in (seal_write, seal_grow, seal_shrink, seal_seal)
            )
        ):
            raise IncarnationHomeError(
                "sealed executable snapshot is unavailable on this host"
            )
        snapshot_fd = memfd_create(
            "abyss-stack-codex-executable",
            allow_sealing,
        )
        os.fchmod(snapshot_fd, 0o700)
        view = memoryview(content)
        while view:
            view = view[os.write(snapshot_fd, view) :]
        os.fsync(snapshot_fd)
        fcntl.fcntl(
            snapshot_fd,
            add_seals,
            seal_write | seal_grow | seal_shrink | seal_seal,
        )
        # A shebang exec reopens the immutable snapshot through
        # /proc/self/fd/<fd>; keep this descriptor across the interpreter
        # transition instead of relying on Python's non-inheritable default.
        os.set_inheritable(snapshot_fd, True)
        os.lseek(snapshot_fd, 0, os.SEEK_SET)
        return (
            snapshot_fd,
            Path(f"/proc/self/fd/{snapshot_fd}"),
            content,
            sha256_bytes(content),
            None,
            None,
            None,
        )
    except IncarnationHomeError:
        if snapshot_fd is not None:
            os.close(snapshot_fd)
        raise
    except OSError as exc:
        if snapshot_fd is not None:
            os.close(snapshot_fd)
        raise IncarnationHomeError(
            f"Codex executable could not be sealed for immutable exec: {executable}"
        ) from exc
    finally:
        if source_fd is not None:
            os.close(source_fd)


def _inode_exec_argv(
    *, executable_bytes: bytes, executable_fd_path: Path, argv: Sequence[str]
) -> list[str]:
    if not argv:
        raise IncarnationHomeError("Codex executable argv must not be empty")
    if executable_bytes.startswith(b"#!"):
        return [str(executable_fd_path), *argv[1:]]
    return list(argv)


def _verify_executable_version(
    executable: Path, runtime_version: str, *, pass_fds: Sequence[int] = ()
) -> None:
    _verify_command_version(
        [str(executable)], runtime_version, pass_fds=pass_fds
    )


def _verify_command_version(
    command: Sequence[str],
    runtime_version: str,
    *,
    pass_fds: Sequence[int] = (),
) -> None:
    expected = "codex-cli " + runtime_version
    try:
        completed = subprocess.run(
            [*command, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            pass_fds=tuple(pass_fds),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IncarnationHomeError("Codex executable version probe failed") from exc
    observed = completed.stdout.strip()
    if completed.returncode != 0 or observed != expected:
        raise IncarnationHomeError(
            f"Codex runtime version mismatch: expected {expected}, got "
            f"{observed or '<empty>'}; returncode={completed.returncode}; "
            f"stderr={completed.stderr.strip() or '<empty>'}"
        )


def _write_codex_identity_shim(
    *,
    command: Path,
    executable: Path,
    codex_home: Path,
    executable_digest: str | None = None,
) -> Path:
    """Make descendant PATH resolve through a digest-checking command shim."""

    shim = codex_home / DESCENDANT_BIN_NAME / "codex"
    if executable_digest is None:
        try:
            executable_digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        except OSError as exc:
            raise IncarnationHomeError(
                "Codex executable could not be hashed for descendant binding"
            ) from exc
    expected_digest = executable_digest.removeprefix("sha256:")
    command_literal = shlex.quote(str(command))
    content = (
        "#!/bin/sh\n"
        "set -eu\n"
        f"expected_digest={shlex.quote(expected_digest)}\n"
        f"admitted_command={command_literal}\n"
        "observed_digest=$(/usr/bin/sha256sum -- \"$admitted_command\" "
        "| /usr/bin/cut -d ' ' -f 1) || exit 125\n"
        "if [ \"$observed_digest\" != \"$expected_digest\" ]; then\n"
        "  echo 'Codex executable changed after admission' >&2\n"
        "  exit 125\n"
        "fi\n"
        "exec \"$admitted_command\" \"$@\"\n"
    )
    _write_exact(shim, content.encode("utf-8"), 0o700)
    return shim


def _reject_binding_overrides(arguments: Sequence[str]) -> None:
    forbidden = {"-m", "--model", "-c", "--config", "-p", "--profile"}
    for index, argument in enumerate(arguments):
        if (
            argument in forbidden
            or argument.startswith("--model=")
            or argument.startswith("--config=")
            or argument.startswith("--profile=")
            or argument.startswith("-m") and argument != "--"
            or argument.startswith("-c") and argument != "--"
            or argument.startswith("-p") and argument != "--"
            or argument in {"--oss", "--local-provider"}
            or argument.startswith("--local-provider=")
        ):
            raise IncarnationHomeError(
                f"forwarded argument overrides incarnation binding: {argument}"
            )
        if argument in {"--enable", "--disable"} and index + 1 < len(arguments):
                if arguments[index + 1] == "multi_agent":
                    if argument == "--enable":
                        raise IncarnationHomeError(
                            "forwarded arguments override incarnation binding: "
                            "may not re-enable multi_agent"
                        )
        if argument == "--enable=multi_agent":
            raise IncarnationHomeError(
                "forwarded arguments override incarnation binding: "
                "may not re-enable multi_agent"
            )


def bound_codex_argv(
    *,
    codex_executable: Path,
    manifest: dict[str, Any],
    arguments: Sequence[str],
    resolved_executable: Path | None = None,
    executable_digest: str | None = None,
) -> list[str]:
    if not codex_executable.is_absolute() or codex_executable.name != "codex":
        raise IncarnationHomeError(
            "Codex executable command must be an absolute path named codex"
        )
    try:
        command = codex_executable.parent.resolve(strict=True) / "codex"
    except OSError as exc:
        raise IncarnationHomeError(
            f"Codex executable parent cannot be resolved: {codex_executable}"
        ) from exc
    executable = resolved_executable or _resolved_executable(command)
    _reject_binding_overrides(arguments)
    codex_home = str(manifest["codex_home"])
    shim = _write_codex_identity_shim(
        command=command,
        executable=executable,
        codex_home=Path(codex_home),
        executable_digest=executable_digest,
    )
    descendant_path = os.pathsep.join(
        (str(shim.parent), "/usr/local/bin", "/usr/bin", "/bin")
    )
    return [
        str(command),
        "-m",
        str(manifest["model_slug"]),
        "-c",
        f'model_reasoning_effort={json.dumps(str(manifest["reasoning_effort"]))}',
        "-c",
        "shell_environment_policy.set="
        + "{CODEX_HOME="
        + json.dumps(codex_home)
        + ", PATH="
        + json.dumps(descendant_path)
        + "}",
        "--disable",
        "multi_agent",
        *arguments,
    ]


def command_prepare(args: argparse.Namespace) -> int:
    manifest = prepare_home(
        ambient_home=Path(args.ambient_codex_home),
        realization_path=Path(args.model_realization),
        runtime_root=Path(args.runtime_root),
        capability_grants=[Path(path) for path in (args.capability_grant or [])],
        binding_context=Path(args.binding_context),
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


def command_payload_launch(args: argparse.Namespace) -> int:
    """Run a payload and release an unpublished claim if admission fails."""

    claim_state: dict[str, bool] = {}
    try:
        return _command_payload_launch_impl(args, claim_state=claim_state)
    except BaseException:
        if claim_state.get("validated") and not claim_state.get("published"):
            claim_path = Path(args.holder_claim)
            claim_digest = args.holder_claim_digest
            try:
                _release_holder_claim(
                    claim_path=claim_path,
                    claim_digest=claim_digest,
                    label="payload holder claim rollback",
                )
            except BaseException as rollback_exc:
                raise IncarnationHomeError(
                    "payload holder claim rollback became uncertain"
                ) from rollback_exc
        raise


def _command_payload_launch_impl(
    args: argparse.Namespace, *, claim_state: dict[str, bool] | None = None
) -> int:
    """Bind the receipt to the exact process that owns the private payload."""

    manifest_path = Path(args.manifest)
    if not args.holder_receipt:
        raise IncarnationHomeError(
            "canonical payload launch requires a holder receipt"
        )
    binding_context: dict[str, str]
    binding_context_path = getattr(args, "binding_context", None)
    binding_context_snapshot_b64 = getattr(args, "binding_context_snapshot_b64", None)
    binding_context_digest = getattr(args, "binding_context_digest", None)
    if (binding_context_snapshot_b64 is None) != (binding_context_digest is None):
        raise IncarnationHomeError("payload binding context snapshot is incomplete")
    if binding_context_snapshot_b64 is not None:
        if not isinstance(binding_context_snapshot_b64, str) or not isinstance(
            binding_context_digest, str
        ):
            raise IncarnationHomeError("payload binding context snapshot is invalid")
        try:
            binding_context_bytes = base64.b64decode(
                binding_context_snapshot_b64.encode("ascii"), validate=True
            )
        except (UnicodeEncodeError, ValueError, base64.binascii.Error) as exc:
            raise IncarnationHomeError(
                "payload binding context snapshot is not valid base64"
            ) from exc
        if (
            not binding_context_bytes
            or sha256_bytes(binding_context_bytes) != binding_context_digest
        ):
            raise IncarnationHomeError("payload binding context snapshot digest drifted")
        binding_context = _load_holder_binding_context_snapshot(binding_context_bytes)
    elif binding_context_path is not None:
        _context_document, binding_context_bytes = _load_json_snapshot(
            Path(binding_context_path), "holder binding context"
        )
        binding_context = _validate_holder_binding_context(_context_document)
        binding_context_digest = sha256_bytes(binding_context_bytes)
    else:
        raise IncarnationHomeError(
            "canonical payload launch requires a typed holder binding context"
        )
    manifest_snapshot_b64 = getattr(args, "manifest_snapshot_b64", None)
    if manifest_snapshot_b64 is None:
        manifest_path = _regular_file(manifest_path, "incarnation-home manifest")
        manifest, manifest_bytes, manifest_digest = _load_manifest_snapshot(
            manifest_path,
            binding_context=binding_context,
            binding_context_digest=binding_context_digest,
            require_holder_binding=True,
        )
    else:
        if not isinstance(manifest_snapshot_b64, str) or not manifest_snapshot_b64:
            raise IncarnationHomeError(
                "payload launch manifest snapshot is invalid"
            )
        try:
            manifest_bytes = base64.b64decode(
                manifest_snapshot_b64.encode("ascii"), validate=True
            )
        except (UnicodeEncodeError, ValueError, base64.binascii.Error) as exc:
            raise IncarnationHomeError(
                "payload launch manifest snapshot is not valid base64"
            ) from exc
        if not manifest_bytes:
            raise IncarnationHomeError("payload launch manifest snapshot is empty")
        manifest, manifest_bytes, manifest_digest = _load_manifest_snapshot(
            manifest_path,
            snapshot_bytes=manifest_bytes,
            binding_context=binding_context,
            binding_context_digest=binding_context_digest,
            require_holder_binding=True,
        )
    if manifest_digest != args.manifest_digest:
        raise IncarnationHomeError("payload launch manifest digest drifted")

    control_socket = getattr(args, "control_socket", None)
    terminal_title = getattr(args, "terminal_title", None)
    terminal_binding_requested = terminal_title is not None or control_socket is not None
    if terminal_binding_requested and (
        not isinstance(control_socket, str) or not isinstance(terminal_title, str)
    ):
        raise IncarnationHomeError("payload terminal binding lacks control socket or title")
    if terminal_title is not None:
        terminal_title = _safe_terminal_title(terminal_title)
    launch_gate_argument = getattr(args, "launch_gate", None)
    launch_gate_token = getattr(args, "launch_gate_token", None)
    if terminal_title is not None and (
        not isinstance(launch_gate_argument, str)
        or not isinstance(launch_gate_token, str)
        or not launch_gate_token
    ):
        raise IncarnationHomeError(
            "canonical payload launch requires a holder receipt and admission gate"
        )
    claim_argument = getattr(args, "holder_claim", None)
    claim_digest = getattr(args, "holder_claim_digest", None)
    if not isinstance(claim_argument, str) or not isinstance(claim_digest, str):
        raise IncarnationHomeError("canonical payload launch requires a holder claim")
    holder_claim_path = Path(claim_argument)
    _validate_holder_claim(
        claim_path=holder_claim_path,
        claim_digest=claim_digest,
        manifest_path=manifest_path,
        manifest=manifest,
        manifest_digest=manifest_digest,
        binding_context_digest=binding_context_digest,
        holder_receipt_path=Path(args.holder_receipt),
    )
    if claim_state is not None:
        claim_state["validated"] = True
    holder_binding = _validate_holder_binding_manifest_record(
        manifest.get("holder_binding")
    )

    payload_path = _regular_file(
        Path(args.payload_executable), "private payload executable"
    )
    try:
        payload_bytes = payload_path.read_bytes()
    except OSError as exc:
        raise IncarnationHomeError(
            f"private payload executable could not be read: {payload_path}"
        ) from exc
    if sha256_bytes(payload_bytes) != args.executable_digest:
        raise IncarnationHomeError("private payload executable digest drifted")

    executable = Path(args.codex_executable)
    if not executable.is_absolute() or executable.is_symlink():
        raise IncarnationHomeError(
            "payload launch Codex executable must be an absolute real path"
        )
    payload_argv = list(args.codex_arguments)
    if not payload_argv or payload_argv[0] != str(payload_path):
        raise IncarnationHomeError(
            "payload launch argv is not bound to the private executable"
        )
    companion_path_argument = getattr(args, "companion_path", None)
    companion_digest_argument = getattr(args, "companion_digest", None)
    companion_relative_argument = getattr(args, "companion_relative", None)
    if (companion_path_argument is None) != (companion_digest_argument is None):
        raise IncarnationHomeError("payload companion binding is incomplete")
    if companion_path_argument is not None and not isinstance(
        companion_relative_argument, str
    ):
        raise IncarnationHomeError("payload companion relative binding is incomplete")
    # The payload executes from the private package mount.  Reopening the
    # original host companion here would reintroduce the race that the sealed
    # snapshot was meant to close.  The host path and relative coordinate are
    # forwarded as provenance; only the mounted companion bytes are inspected
    # at this boundary.
    detected_companion = _adjacent_code_mode_host(payload_path)
    if companion_path_argument is None:
        if detected_companion is not None:
            raise IncarnationHomeError("payload companion binding is missing")
        companion_binding = None
    else:
        if detected_companion is None:
            raise IncarnationHomeError("payload companion disappeared before receipt")
        _private_companion_path, _companion_bytes, private_companion_binding = (
            detected_companion
        )
        expected_host_companion = executable.parent / CODE_MODE_HOST_NAME
        forwarded_package_relative = Path(companion_relative_argument)
        if (
            forwarded_package_relative.is_absolute()
            or ".." in forwarded_package_relative.parts
            or forwarded_package_relative.name != CODE_MODE_HOST_NAME
        ):
            raise IncarnationHomeError("payload companion provenance is invalid")
        private_package_root = _package_root(payload_path)
        expected_private_relative = (
            companion_relative_argument
            if (private_package_root / "package.json").is_file()
            else CODE_MODE_HOST_NAME
        )
        if (
            str(expected_host_companion) != companion_path_argument
            or private_companion_binding["package_relative"]
            != expected_private_relative
            or private_companion_binding["digest"] != companion_digest_argument
        ):
            raise IncarnationHomeError("payload companion binding drifted")
        companion_binding = {
            "path": companion_path_argument,
            "digest": companion_digest_argument,
            "relation": "adjacent_immutable_package",
            "package_relative": companion_relative_argument,
        }
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(manifest["codex_home"])
    if args.holder_receipt:
        _holder_receipt(
            receipt_path=Path(args.holder_receipt),
            manifest_path=manifest_path,
            manifest=manifest,
            executable=executable,
            argv=payload_argv,
            executable_bytes=payload_bytes,
            executable_digest=args.executable_digest,
            manifest_bytes=manifest_bytes,
            manifest_digest=manifest_digest,
            companion_binding=companion_binding,
            holder_binding=holder_binding,
            binding_context=(binding_context if terminal_title is not None else None),
            control_socket=control_socket,
            terminal_title=terminal_title,
        )
        if claim_state is not None:
            claim_state["published"] = True
        if terminal_title is not None:
            _await_visible_launch_admission(
                gate_path=Path(launch_gate_argument),
                holder_receipt_path=Path(args.holder_receipt),
                token=launch_gate_token,
            )
    os.execve(str(payload_path), payload_argv, environment)
    return 127


def command_launch(args: argparse.Namespace) -> int:
    terminal_title = getattr(args, "terminal_title", None)
    holder_receipt_argument = getattr(args, "holder_receipt", None)
    binding_context_argument = getattr(args, "binding_context", None)
    control_socket_argument = getattr(args, "control_socket", None)
    if terminal_title is not None:
        terminal_title = _safe_terminal_title(terminal_title)
    if terminal_title is None and control_socket_argument is not None:
        raise IncarnationHomeError(
            "visible launch binding options require --terminal-title"
        )
    if not holder_receipt_argument or not binding_context_argument:
        raise IncarnationHomeError(
            "canonical visible launch requires --holder-receipt and a typed --binding-context"
        )
    _binding_context_value, binding_context_bytes = _load_json_snapshot(
        Path(binding_context_argument), "holder binding context"
    )
    binding_context = _validate_holder_binding_context(_binding_context_value)
    binding_context_digest = sha256_bytes(binding_context_bytes)
    manifest_path = _regular_file(Path(args.manifest), "incarnation-home manifest")
    manifest, manifest_bytes, manifest_digest = _load_manifest_snapshot(
        manifest_path,
        binding_context=binding_context,
        binding_context_digest=binding_context_digest,
        require_holder_binding=True,
    )
    holder_binding = _validate_holder_binding_manifest_record(
        manifest.get("holder_binding")
    )
    command = Path(args.codex_executable)
    executable = _resolved_executable(command)
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(manifest["codex_home"])
    holder_receipt_path = Path(holder_receipt_argument)
    _require_unoccupied_receipt_path(holder_receipt_path)
    if terminal_title is not None:
        control_socket = getattr(args, "control_socket", None) or _allocate_control_socket()
        _socket_path(control_socket)
        _validate_socket_parent(_socket_path(control_socket))
        if _socket_path(control_socket).exists() or _socket_path(control_socket).is_symlink():
            raise IncarnationHomeError(
                f"control socket path is already occupied: {control_socket}"
            )
        launch_gate_path = holder_receipt_path.with_name(
            holder_receipt_path.name + ".launch-gate.json"
        )
        _require_unoccupied_launch_gate_path(launch_gate_path)
        launch_gate_token = secrets.token_hex(32)
        holder_claim_path, holder_claim_digest = _reserve_holder_claim_for_launch(
            manifest_path=manifest_path,
            manifest=manifest,
            manifest_digest=manifest_digest,
            binding_context_digest=binding_context_digest,
            binding_context=binding_context,
            holder_receipt_path=holder_receipt_path,
        )
        try:
            (
                executable_fd,
                _executable_fd_path,
                executable_bytes,
                executable_digest,
                executable_snapshot_dir,
                executable_snapshot_path,
                executable_snapshot_mount,
            ) = _open_verified_executable(
                executable,
                snapshot_root=Path(str(manifest["codex_home"])) / "tmp",
            )
        except BaseException:
            _release_holder_claim(
                claim_path=holder_claim_path,
                claim_digest=holder_claim_digest,
            )
            raise
        launcher_fd: int | None = None
        cleanup_started = False
        launch_candidate: dict[str, Any] | None = None
        launch_accepted = False
        launch_gate_published = False
        rejected_cleanup_error: IncarnationHomeError | None = None
        codex_mount = executable_snapshot_mount
        try:
            if codex_mount is None:
                codex_mount = {
                    "directory_paths": [],
                    "file_fds": [(Path("codex"), executable_fd, 0o700)],
                    "namespace_root": Path("/var/tmp"),
                    "executable_path": Path("/var/tmp/codex"),
                    "companion": None,
                }
            launcher_source = Path(__file__).resolve()
            launcher_bytes, _launcher_info = _read_verified_regular_file(
                launcher_source, label="visible payload launcher"
            )
            launcher_fd = _sealed_memfd(
                "abyss-stack-visible-incarnation-home",
                launcher_bytes,
                mode=0o500,
            )
            launcher_relative = Path("aoa-visible-incarnation-home.py")
            if any(
                relative == launcher_relative
                for relative, _descriptor, _mode in codex_mount["file_fds"]
            ):
                raise IncarnationHomeError("visible payload launcher snapshot collided")
            codex_mount["file_fds"].append((launcher_relative, launcher_fd, 0o500))
            snapshot_prefix = _snapshot_bwrap_prefix(codex_mount)
            snapshot_component_fds = [
                int(descriptor)
                for _, descriptor, _ in codex_mount["file_fds"]
            ]
            _verify_command_version(
                [*snapshot_prefix, "--", str(codex_mount["executable_path"])],
                str(manifest["runtime_version"]),
                pass_fds=tuple(snapshot_component_fds),
            )
            _rewind_snapshot_components(snapshot_component_fds)
            argv = bound_codex_argv(
                codex_executable=command,
                manifest=manifest,
                arguments=args.codex_arguments,
                resolved_executable=executable,
                executable_digest=executable_digest,
            )
            launch_argv = [str(codex_mount["executable_path"]), *argv[1:]]
            companion_binding = codex_mount.get("companion")
            payload_script = Path("/var/tmp") / launcher_relative
            payload_argv = [
                sys.executable,
                "-I",
                "-B",
                str(payload_script),
                "payload-launch",
                "--manifest",
                str(manifest_path),
                "--manifest-snapshot-b64",
                base64.b64encode(manifest_bytes).decode("ascii"),
                "--holder-receipt",
                str(Path(holder_receipt_argument)),
                "--holder-claim",
                str(holder_claim_path),
                "--holder-claim-digest",
                str(holder_claim_digest),
                "--binding-context-snapshot-b64",
                base64.b64encode(binding_context_bytes).decode("ascii"),
                "--binding-context-digest",
                binding_context_digest,
                "--control-socket",
                control_socket,
                "--terminal-title",
                terminal_title,
                "--launch-gate",
                str(launch_gate_path),
                "--launch-gate-token",
                launch_gate_token,
                "--codex-executable",
                str(executable),
                "--payload-executable",
                str(codex_mount["executable_path"]),
                "--manifest-digest",
                manifest_digest,
                "--executable-digest",
                executable_digest,
                *(
                    [
                        "--companion-path",
                        companion_binding["path"],
                        "--companion-digest",
                        companion_binding["digest"],
                        "--companion-relative",
                        companion_binding["package_relative"],
                    ]
                    if companion_binding is not None
                    else []
                ),
                "--",
                *launch_argv,
            ]
            completed = subprocess.run(
                [
                    args.kitty_executable,
                    "--detach",
                    "--title",
                    terminal_title,
                    "--listen-on",
                    control_socket,
                    "--override",
                    "allow_remote_control=socket-only",
                    *snapshot_prefix,
                    "--",
                    *payload_argv,
                ],
                check=False,
                env=environment,
                pass_fds=tuple(snapshot_component_fds),
            )
            if completed.returncode != 0:
                return completed.returncode
            receipt: dict[str, Any] | None = None
            for _ in range(100):
                if holder_receipt_path.exists():
                    try:
                        candidate = _load_holder_receipt(holder_receipt_path)
                        if (
                            isinstance(candidate.get("binding"), dict)
                            and candidate["binding"].get("remote_control")
                            == "socket-only"
                        ):
                            candidate = _validate_visible_launch_receipt(
                                receipt_path=holder_receipt_path,
                                receipt=candidate,
                                manifest_path=manifest_path,
                                manifest=manifest,
                                manifest_bytes=manifest_bytes,
                                manifest_digest=manifest_digest,
                                executable=executable,
                                executable_digest=executable_digest,
                                binding_context=binding_context,
                                holder_binding=holder_binding,
                                control_socket=control_socket,
                                terminal_title=terminal_title,
                                companion_binding=companion_binding,
                            )
                            _validate_terminal_binding_shape(candidate["binding"])
                            launch_candidate = candidate
                            _holder_pre_exec_identity(
                                candidate,
                                expected_argv=payload_argv,
                            )
                            receipt = candidate
                            break
                    except IncarnationHomeError:
                        receipt = None
                time.sleep(0.1)
            if receipt is None or not isinstance(receipt.get("binding"), dict):
                raise IncarnationHomeError(
                    "visible launch did not publish a live terminal binding"
                )
            binding = _validate_terminal_binding_shape(receipt["binding"])
            _write_visible_launch_gate(
                gate_path=launch_gate_path,
                holder_receipt_path=holder_receipt_path,
                token=launch_gate_token,
                decision="admit",
            )
            launch_gate_published = True
            _confirm_visible_launch_admission(
                gate_path=launch_gate_path,
                holder_receipt_path=holder_receipt_path,
                token=launch_gate_token,
            )
            post_exec_acknowledged = False
            for _ in range(100):
                try:
                    _holder_terminal_identity(receipt)
                    post_exec_acknowledged = True
                    break
                except IncarnationHomeError:
                    time.sleep(0.1)
            if not post_exec_acknowledged:
                raise IncarnationHomeError(
                    "visible launch did not publish a post-exec identity acknowledgment"
                )
            if executable_snapshot_dir is not None:
                _spawn_named_snapshot_cleanup(
                    snapshot_path=executable_snapshot_path,
                    snapshot_dir=executable_snapshot_dir,
                    holder_pid=receipt["holder"]["pid"],
                    holder_start_ticks=receipt["holder"]["start_ticks"],
                    snapshot_fd=executable_fd,
                    snapshot_component_fds=snapshot_component_fds,
                )
                cleanup_started = True
            _emit_safe_json(
                {
                    "schema_version": TERMINAL_BINDING_SCHEMA_VERSION,
                    "launched": True,
                    "binding": binding,
                },
                label="visible launch binding",
            )
            launch_accepted = True
            return 0
        finally:
            if not launch_gate_published:
                try:
                    _write_visible_launch_gate(
                        gate_path=launch_gate_path,
                        holder_receipt_path=holder_receipt_path,
                        token=launch_gate_token,
                        decision="reject",
                    )
                    launch_gate_published = True
                except IncarnationHomeError:
                    # A missing reject publication is still fail-closed: the
                    # payload has a bounded wait and cannot execute without
                    # an explicit parent admission.
                    pass
            if not launch_accepted and launch_candidate is not None:
                if not _terminate_rejected_visible_launch(launch_candidate):
                    rejected_cleanup_error = IncarnationHomeError(
                        "rejected visible launch holder did not terminate"
                    )
            if (
                holder_claim_path is not None
                and holder_claim_digest is not None
                and not launch_accepted
                and launch_candidate is None
            ):
                _release_holder_claim(
                    claim_path=holder_claim_path,
                    claim_digest=holder_claim_digest,
                )
            if (
                executable_snapshot_dir is not None
                and executable_snapshot_path is not None
                and not cleanup_started
            ):
                _remove_named_snapshot(
                    executable_snapshot_path,
                    snapshot_dir=executable_snapshot_dir,
                    snapshot_dir_fd=executable_fd,
                )
            _close_snapshot_mount(codex_mount)
            if launcher_fd is not None:
                try:
                    os.close(launcher_fd)
                except OSError:
                    pass
            try:
                os.close(executable_fd)
            except OSError:
                pass
            if rejected_cleanup_error is not None:
                raise rejected_cleanup_error
    holder_claim_path, holder_claim_digest = _reserve_holder_claim_for_launch(
        manifest_path=manifest_path,
        manifest=manifest,
        manifest_digest=manifest_digest,
        binding_context_digest=binding_context_digest,
        binding_context=binding_context,
        holder_receipt_path=holder_receipt_path,
    )
    holder_receipt_published = False
    try:
        (
            executable_fd,
            executable_fd_path,
            executable_bytes,
            executable_digest,
            executable_snapshot_dir,
            executable_snapshot_path,
            executable_snapshot_mount,
        ) = _open_verified_executable(
            executable,
            snapshot_root=Path(str(manifest["codex_home"])) / "tmp",
        )
    except BaseException:
        _release_holder_claim(
            claim_path=holder_claim_path,
            claim_digest=holder_claim_digest,
        )
        raise
    snapshot_component_fds: list[int] = []
    cleanup_started = False
    try:
        companion_binding = (
            executable_snapshot_mount.get("companion")
            if executable_snapshot_mount is not None
            else None
        )
        if executable_snapshot_mount is None:
            _verify_executable_version(
                executable_fd_path,
                str(manifest["runtime_version"]),
                pass_fds=(executable_fd,),
            )
        else:
            snapshot_prefix = _snapshot_bwrap_prefix(executable_snapshot_mount)
            snapshot_component_fds = [
                *(
                    int(descriptor)
                    for _, descriptor, _ in executable_snapshot_mount["file_fds"]
                ),
            ]
            _verify_command_version(
                [*snapshot_prefix, "--", str(executable_fd_path)],
                str(manifest["runtime_version"]),
                pass_fds=tuple(snapshot_component_fds),
            )
            _rewind_snapshot_components(snapshot_component_fds)
        argv = bound_codex_argv(
            codex_executable=command,
            manifest=manifest,
            arguments=args.codex_arguments,
            resolved_executable=executable,
            executable_digest=executable_digest,
        )
        exec_argv = _inode_exec_argv(
            executable_bytes=executable_bytes,
            executable_fd_path=executable_fd_path,
            argv=argv,
        )
        launch_path = executable_fd_path
        launch_argv = exec_argv
        if executable_snapshot_mount is not None:
            launch_path = executable_snapshot_mount["executable_path"]
            launch_argv = [str(launch_path), *argv[1:]]
        if args.holder_receipt and executable_snapshot_mount is None:
            _holder_receipt(
                receipt_path=Path(args.holder_receipt),
                manifest_path=manifest_path,
                manifest=manifest,
                executable=executable,
                argv=launch_argv,
                executable_bytes=executable_bytes,
                executable_digest=executable_digest,
                manifest_bytes=manifest_bytes,
                manifest_digest=manifest_digest,
                holder_binding=holder_binding,
            )
            holder_receipt_published = True
        final_argv = launch_argv
        if executable_snapshot_mount is not None and args.holder_receipt:
            # The bwrap monitor is not the responsibility holder.  Its payload
            # helper records its own PID immediately before replacing itself
            # with the private shebang launcher.
            final_argv = [
                sys.executable,
                str(Path(__file__).resolve()),
                "payload-launch",
                "--manifest",
                str(manifest_path),
                "--manifest-snapshot-b64",
                base64.b64encode(manifest_bytes).decode("ascii"),
                "--holder-receipt",
                str(args.holder_receipt),
                "--holder-claim",
                str(holder_claim_path),
                "--holder-claim-digest",
                str(holder_claim_digest),
                "--binding-context-snapshot-b64",
                base64.b64encode(binding_context_bytes).decode("ascii"),
                "--binding-context-digest",
                binding_context_digest,
                "--codex-executable",
                str(executable),
                "--payload-executable",
                str(launch_path),
                "--manifest-digest",
                manifest_digest,
                "--executable-digest",
                executable_digest,
                *(
                    [
                        "--companion-path",
                        companion_binding["path"],
                        "--companion-digest",
                        companion_binding["digest"],
                        "--companion-relative",
                        companion_binding["package_relative"],
                    ]
                    if companion_binding is not None
                    else []
                ),
                "--",
                *launch_argv,
            ]
        if executable_snapshot_dir is not None:
            _spawn_named_snapshot_cleanup(
                snapshot_path=executable_snapshot_path,
                snapshot_dir=executable_snapshot_dir,
                holder_pid=os.getpid(),
                holder_start_ticks=_proc_start_ticks(os.getpid()),
                snapshot_fd=executable_fd,
                snapshot_component_fds=snapshot_component_fds,
            )
            cleanup_started = True
        if executable_snapshot_mount is None:
            os.execve(str(executable_fd_path), launch_argv, environment)
        os.execve(
            snapshot_prefix[0],
            [*snapshot_prefix, "--", *final_argv],
            environment,
        )
        return 127
    finally:
        if (
            executable_snapshot_dir is not None
            and executable_snapshot_path is not None
            and not cleanup_started
        ):
            _remove_named_snapshot(
                executable_snapshot_path,
                snapshot_dir=executable_snapshot_dir,
                snapshot_dir_fd=executable_fd,
            )
        for descriptor in snapshot_component_fds:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.close(executable_fd)
        except OSError:
            pass
        if not holder_receipt_published:
            _release_holder_claim(
                claim_path=holder_claim_path,
                claim_digest=holder_claim_digest,
            )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    subcommands = root.add_subparsers(dest="command", required=True)
    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("--ambient-codex-home", required=True)
    prepare.add_argument("--model-realization", required=True)
    prepare.add_argument("--runtime-root", required=True)
    prepare.add_argument(
        "--binding-context",
        required=True,
        help="typed holder/task/run responsibility context for this home",
    )
    prepare.add_argument(
        "--capability-grant",
        action="append",
        default=[],
        help="owner-authored exact grant for one operator capability entry",
    )
    prepare.set_defaults(handler=command_prepare)
    launch = subcommands.add_parser("launch")
    launch.add_argument("--manifest", required=True)
    launch.add_argument("--codex-executable", required=True)
    launch.add_argument("--terminal-title")
    launch.add_argument("--kitty-executable", default="/usr/bin/kitty")
    launch.add_argument(
        "--holder-receipt",
        required=True,
        help=(
            "non-replacing receipt for this direct responsibility-holder process; "
            "the shebang payload writes it immediately before exec"
        ),
    )
    launch.add_argument(
        "--binding-context",
        required=True,
        help="owner context required for a canonical detached visible holder",
    )
    launch.add_argument(
        "--control-socket",
        help="optional owner-selected unix: Kitty socket; otherwise allocate one",
    )
    launch.add_argument("codex_arguments", nargs=argparse.REMAINDER)
    launch.set_defaults(handler=command_launch)
    payload = subcommands.add_parser("payload-launch")
    payload.add_argument("--manifest", required=True)
    payload.add_argument("--holder-receipt", required=True)
    payload.add_argument("--holder-claim", required=True)
    payload.add_argument("--holder-claim-digest", required=True)
    payload.add_argument("--codex-executable", required=True)
    payload.add_argument("--payload-executable", required=True)
    payload.add_argument("--manifest-digest", required=True)
    payload.add_argument("--manifest-snapshot-b64")
    payload.add_argument("--executable-digest", required=True)
    payload.add_argument("--companion-path")
    payload.add_argument("--companion-digest")
    payload.add_argument("--companion-relative")
    payload.add_argument("--binding-context")
    payload.add_argument("--binding-context-snapshot-b64")
    payload.add_argument("--binding-context-digest")
    payload.add_argument("--control-socket")
    payload.add_argument("--terminal-title")
    payload.add_argument("--launch-gate")
    payload.add_argument("--launch-gate-token")
    payload.add_argument("codex_arguments", nargs=argparse.REMAINDER)
    payload.set_defaults(handler=command_payload_launch)
    bind = subcommands.add_parser("bind")
    bind.add_argument("--holder-receipt", required=True)
    bind.add_argument("--binding-context", required=True)
    bind.add_argument("--output", required=True)
    bind.set_defaults(handler=command_bind)
    rebind = subcommands.add_parser(
        "rebind",
        help=(
            "derive one canonical holder receipt from an exact holder-loss "
            "replacement evidence packet"
        ),
    )
    rebind.add_argument("--holder-loss-reentry", required=True)
    rebind.add_argument("--binding-context", required=True)
    rebind.add_argument("--manifest", required=True)
    rebind.add_argument("--codex-executable", required=True)
    rebind.add_argument("--output", required=True)
    rebind.set_defaults(handler=command_rebind)
    status = subcommands.add_parser("status")
    status.add_argument("--binding")
    status.add_argument("--holder-receipt")
    status.add_argument("--binding-context")
    status.add_argument("--kitty-executable", default="/usr/bin/kitty")
    status.add_argument("--output")
    status.set_defaults(handler=command_status)
    send_text = subcommands.add_parser("send-text")
    send_text.add_argument("--binding")
    send_text.add_argument("--holder-receipt")
    send_text.add_argument("--binding-context")
    send_text.add_argument("--kitty-executable", default="/usr/bin/kitty")
    send_text.add_argument("--text", required=True)
    send_text.set_defaults(handler=command_send_text)
    join = subcommands.add_parser("join")
    join.add_argument("--holder-receipt", required=True)
    join.add_argument("--handoff", required=True)
    join.add_argument("--join-receipt", required=True)
    join.add_argument("--authorization", required=True)
    join.add_argument("--closure-receipt", required=True)
    join.set_defaults(handler=command_join)
    authorize_close = subcommands.add_parser("authorize-close")
    authorize_close.add_argument("--holder-receipt", required=True)
    authorize_close.add_argument("--wake-receipt", required=True)
    authorize_close.add_argument("--handoff", required=True)
    authorize_close.add_argument("--authorization", required=True)
    authorize_close.add_argument("--closure-receipt", required=True)
    authorize_close.set_defaults(handler=command_authorize_close)
    close = subcommands.add_parser("close")
    close.add_argument("--holder-receipt", required=True)
    close_group = close.add_mutually_exclusive_group(required=True)
    close_group.add_argument("--wake-receipt")
    close_group.add_argument("--closure-authorization")
    close.add_argument("--handoff", required=True)
    close.add_argument("--closure-receipt", required=True)
    close.set_defaults(handler=command_close)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if (
        args.command in {"launch", "payload-launch"}
        and args.codex_arguments[:1] == ["--"]
    ):
        args.codex_arguments = args.codex_arguments[1:]
    if args.command in {"launch", "payload-launch"} and not args.codex_arguments:
        raise IncarnationHomeError(
            f"{args.command} requires Codex arguments after --"
        )
    return int(args.handler(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IncarnationHomeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
