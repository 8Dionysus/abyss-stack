#!/usr/bin/env python3
"""Prepare and enter a Codex home whose default follows one incarnation.

The operator-visible Codex process keeps the ambient user home so existing
sessions and hook trust retain their identity.  Its shell children receive the
incarnation home through Codex's shell environment policy; a plain nested
``codex exec`` therefore keeps the selected model and reasoning effort.
"""

from __future__ import annotations

import argparse
import base64
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


SCHEMA_VERSION = "abyss_stack_codex_incarnation_home_v1"
HOLDER_RECEIPT_SCHEMA_VERSION = "abyss_stack_visible_incarnation_holder_terminal_v1"
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


def _write_exact(path: Path, content: bytes, mode: int) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise IncarnationHomeError(f"refusing to replace non-file: {path}")
        if path.read_bytes() == content:
            path.chmod(mode)
            return
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        temporary.write_bytes(content)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


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

    def redact(match: re.Match[str]) -> str:
        raw_value = match.group("value")
        if raw_value[:1] in {'"', "'"} and raw_value[-1:] == raw_value[:1]:
            raw_value = f"{raw_value[0]}<redacted>{raw_value[0]}"
        else:
            raw_value = "<redacted>"
        return (
            f"{match.group('key_quote')}{match.group('key')}"
            f"{match.group('key_quote')}{match.group('separator')}{raw_value}"
        )

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


def _binding_ref(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IncarnationHomeError(f"terminal binding {label} is missing")
    if any(character in value for character in "\x00\r\n"):
        raise IncarnationHomeError(f"terminal binding {label} contains control text")
    return _safe_projection_string(value, label)


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
    return path


def _validate_socket_parent(path: Path, *, create: bool = False) -> Path:
    parent = path.parent
    if create and not parent.exists():
        parent.mkdir(mode=CONTROL_SOCKET_PARENT_MODE, parents=False)
    if parent.is_symlink() or not parent.is_dir():
        raise IncarnationHomeError(f"control socket parent is not a directory: {parent}")
    try:
        parent_stat = parent.stat()
    except OSError as exc:
        raise IncarnationHomeError(f"control socket parent cannot be inspected: {parent}") from exc
    if parent_stat.st_uid != os.getuid() or stat.S_IMODE(parent_stat.st_mode) & 0o077:
        raise IncarnationHomeError(
            f"control socket parent is not private to the owner: {parent}"
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
    required = (
        "goal_ref",
        "actor_ref",
        "incarnation_ref",
        "session_ref",
        "runtime_state_root",
        "closeout_route",
    )
    values = {key: _binding_ref(context.get(key), key) for key in required}
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


def _load_binding_context(path: Path) -> dict[str, str]:
    context = _load_json(path, "terminal binding context")
    return _validate_binding_context(context)


def _load_binding_context_snapshot(raw: bytes) -> dict[str, str]:
    return _validate_binding_context(
        _decode_json_snapshot(raw, "terminal binding context snapshot")
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
    if source_receipt is not None:
        binding["source_receipt"] = {
            "path": str(source_receipt.resolve()),
            "sha256": source_receipt_digest
            or sha256_bytes(source_receipt.read_bytes()),
        }
    _assert_safe_projection(binding)
    return binding


def _validate_terminal_binding_shape(binding: object) -> dict[str, object]:
    if not isinstance(binding, dict):
        raise IncarnationHomeError("terminal binding is not an object")
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
        _binding_ref(binding.get(key), key)
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
    if set(holder) - {"pid", "start_ticks"}:
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
        isinstance(holder.get(key), int) and holder[key] > 0
        for key in ("pid", "start_ticks")
    ):
        raise IncarnationHomeError("terminal binding holder identity is invalid")
    if not all(
        isinstance(terminal.get(key), int) and terminal[key] > 0
        for key in ("pid", "start_ticks")
    ):
        raise IncarnationHomeError("terminal binding Kitty identity is invalid")
    if not isinstance(terminal.get("window_id"), str) or not re.fullmatch(
        r"[1-9][0-9]*", terminal["window_id"]
    ):
        raise IncarnationHomeError("terminal binding window identity is invalid")
    if not isinstance(terminal.get("tty"), str) or not terminal["tty"]:
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
    if not isinstance(mode, int) or mode & 0o077:
        raise IncarnationHomeError("terminal binding socket mode is not private")
    if not all(
        isinstance(socket_record.get(key), int) and socket_record[key] > 0
        for key in ("device", "inode")
    ):
        raise IncarnationHomeError("terminal binding socket identity is invalid")
    source_receipt = binding.get("source_receipt")
    if source_receipt is not None and (
        not isinstance(source_receipt, dict)
        or set(source_receipt) != {"path", "sha256"}
    ):
        raise IncarnationHomeError("terminal binding source receipt is invalid")
    _assert_safe_projection(binding)
    return binding


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
                        if not isinstance(pid, int) or pid <= 0:
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
                    if isinstance(window.get("pid"), int)
                    else None,
                    "is_active": window.get("is_active") is True,
                    "is_focused": window.get("is_focused") is True,
                    "needs_attention": window.get("needs_attention") is True,
                    "in_alternate_screen": window.get("in_alternate_screen") is True,
                    "foreground_processes": foreground,
                    "tab": {
                        "id": tab.get("id") if isinstance(tab.get("id"), int) else None,
                        "is_active": tab.get("is_active") is True,
                        "is_focused": tab.get("is_focused") is True,
                    },
                    "os_window": {
                        "id": os_window.get("id")
                        if isinstance(os_window.get("id"), int)
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


def _post_exec_argv(
    executable: Path,
    argv: Sequence[str],
    *,
    path: str | None = None,
    executable_bytes: bytes | None = None,
) -> list[str]:
    """Derive Linux's post-exec argv for ELF and shebang-backed commands."""

    if not argv:
        raise IncarnationHomeError("holder argv must not be empty")
    try:
        first_line = (
            executable_bytes if executable_bytes is not None else executable.read_bytes()
        ).splitlines(keepends=True)[0]
    except (IndexError, OSError) as exc:
        raise IncarnationHomeError("Codex executable could not be inspected") from exc
    if not first_line.startswith(b"#!"):
        return list(argv)
    shebang = os.fsdecode(first_line[2:]).strip()
    fields = shebang.split(maxsplit=1)
    if not fields or not fields[0].startswith("/"):
        raise IncarnationHomeError("Codex shebang interpreter is not absolute")
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
            resolved = shutil.which(env_fields[0], path=path or os.environ.get("PATH"))
            if resolved is not None:
                return [
                    # env resolves the command for lookup but preserves the
                    # command token as argv[0] for the re-exec.  Recording the
                    # resolved filesystem path here rejects a valid holder
                    # whose /proc argv starts with the admitted token (for
                    # example, "node").
                    env_fields[0],
                    *env_fields[1:],
                    argv[0],
                    *argv[1:],
                ]
    post_exec = [fields[0]]
    if len(fields) == 2 and fields[1]:
        post_exec.append(fields[1])
    post_exec.append(argv[0])
    post_exec.extend(argv[1:])
    return post_exec


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


def _kitty_dedication(
    *, holder_pid: int, kitty_pid: int, terminal_argv: Sequence[str]
) -> tuple[str, bool]:
    """Prove the Kitty process is the detached, single-window holder terminal."""

    if "--detach" not in terminal_argv:
        raise IncarnationHomeError(
            "holder Kitty terminal is not a detached dedicated process"
        )
    environment = _proc_environ(holder_pid)
    if environment.get("KITTY_PID") != str(kitty_pid):
        raise IncarnationHomeError("holder Kitty window does not bind its Kitty PID")
    window_id = environment.get("KITTY_WINDOW_ID", "")
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
) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise IncarnationHomeError(f"{label} must be an absolute non-symlink path: {path}")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise IncarnationHomeError(f"{label} parent must be a real directory: {parent}")
    payload = canonical_bytes(value) + b"\n"
    fd: int | None = None
    temporary_path: Path | None = None
    try:
        fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".tmp.", dir=str(parent))
        temporary_path = Path(temporary_name)
        os.fchmod(fd, 0o600)
        view = memoryview(payload)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
        if replace:
            if path.is_symlink():
                raise IncarnationHomeError(
                    f"{label} became a symlink before publication: {path}"
                )
            os.replace(temporary_path, path)
        else:
            os.link(temporary_path, path)
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW
        directory_fd = os.open(parent, directory_flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError as exc:
        raise IncarnationHomeError(f"{label} already exists: {path}") from exc
    except OSError as exc:
        raise IncarnationHomeError(f"cannot write {label}: {path}") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _write_new_json(path: Path, value: dict[str, Any], label: str) -> None:
    _write_atomic_json(path, value, label, replace=False)


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
    binding_context: dict[str, str] | None = None,
    control_socket: str | None = None,
    terminal_title: str | None = None,
) -> dict[str, Any]:
    holder_pid = os.getpid()
    holder_parent_pid = os.getppid()
    if holder_parent_pid <= 1:
        raise IncarnationHomeError("visible holder has no usable process parent")
    parent_comm = _proc_comm(holder_parent_pid)
    terminal_pid, terminal_start_ticks, terminal_argv = _kitty_ancestor(holder_pid)
    window_id, dedicated = _kitty_dedication(
        holder_pid=holder_pid,
        kitty_pid=terminal_pid,
        terminal_argv=terminal_argv,
    )
    post_exec_argv = _post_exec_argv(
        executable,
        argv,
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
            "argv": post_exec_argv,
            "argv_digest": sha256_bytes(canonical_bytes(post_exec_argv)),
        },
        "runtime": runtime,
        "terminal": terminal,
    }
    if binding is not None:
        receipt["binding"] = binding
    _write_new_json(receipt_path, receipt, "holder terminal receipt")
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
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
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
    if wake.get("schema_version") != "task_local_actor_wake_receipt_v1":
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
        or not isinstance(terminal.get("pid"), int)
        or not isinstance(terminal.get("start_ticks"), int)
        or not isinstance(terminal.get("argv"), list)
        or not all(isinstance(item, str) for item in terminal["argv"])
        or not isinstance(terminal.get("window_id"), str)
        or not re.fullmatch(r"[1-9][0-9]*", terminal["window_id"])
        or terminal.get("dedicated") is not True
        or not isinstance(holder.get("argv"), list)
        or not all(isinstance(item, str) for item in holder["argv"])
    ):
        raise IncarnationHomeError("holder terminal receipt is incomplete")
    _decode_holder_manifest_snapshot(runtime)
    if "binding" in receipt:
        _validate_terminal_binding_shape(receipt["binding"])
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
        isinstance(value, int) and value > 0
        for value in (pid, start_ticks, parent_pid, parent_start_ticks)
    ):
        raise IncarnationHomeError("holder process identity is invalid")
    if not isinstance(kitty_pid, int) or kitty_pid <= 1:
        raise IncarnationHomeError("holder Kitty identity is invalid")
    if not isinstance(kitty_start_ticks, int) or kitty_start_ticks <= 0:
        raise IncarnationHomeError("holder Kitty identity is invalid")
    expected_argv = holder["argv"]
    if holder.get("argv_digest") != sha256_bytes(canonical_bytes(expected_argv)):
        raise IncarnationHomeError("holder argv digest is invalid")
    return pid, start_ticks, kitty_pid, kitty_start_ticks


def _holder_terminal_identity(
    receipt: dict[str, Any],
) -> tuple[int, int, str, str, bool]:
    holder = receipt["holder"]
    runtime = receipt["runtime"]
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
    observed_argv = _proc_argv(pid)
    expected_argv = holder["argv"]
    if observed_argv != expected_argv:
        raise IncarnationHomeError("holder argv identity has drifted")
    if holder.get("argv_digest") != sha256_bytes(canonical_bytes(expected_argv)):
        raise IncarnationHomeError("holder argv digest is invalid")
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
    return pid, kitty_pid, _proc_comm(kitty_pid), window_id, dedicated


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
        or not isinstance(window_id, (str, int))
        or not isinstance(title, str)
        or not isinstance(tty, str)
        or not all(
            isinstance(value, int) and value > 0
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
        or not isinstance(holder_parent_pid, int)
        or holder_parent_pid <= 0
        or not isinstance(holder_parent_start_ticks, int)
        or holder_parent_start_ticks <= 0
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
    identity_state = "live"
    if holder_state == "drifted" or terminal_state == "drifted":
        identity_state = "stale"
    elif holder_state == "gone" or terminal_state == "gone":
        identity_state = "missing"
    elif identity_state == "live":
        try:
            if _proc_comm(terminal_pid) != "kitty" or not _descends_from(
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
                "comm": "kitty" if terminal_state == "live" else "unknown",
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
    document: dict[str, object] = {
        "schema_version": TERMINAL_BINDING_SCHEMA_VERSION,
        "created_at": _utc_now(),
        "source_receipt": {
            "path": str(source_receipt.resolve()),
            "sha256": source_digest,
        },
        "binding": binding,
        "holder": holder,
        "terminal": terminal,
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
    for key, value in binding_context.items():
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
    if terminal.get("title") != _safe_projection_string(
        terminal_title, "terminal title"
    ):
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
    socket_record = terminal["control_socket"]
    assert isinstance(socket_record, dict)
    _secure_control_socket(
        str(socket_record["address"]),
        harden=False,
        expected_device=socket_record["device"],
        expected_inode=socket_record["inode"],
    )
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


def prepare_home(
    *, ambient_home: Path, realization_path: Path, runtime_root: Path
) -> dict[str, Any]:
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
    fingerprint_value = coordinate.removeprefix("sha256:")
    incarnation_root = runtime_root / f"sha256-{fingerprint_value}"
    codex_home = incarnation_root / "codex-home"
    ambient_identity = _ambient_home_identity(ambient_home)
    if incarnation_root.is_symlink():
        raise IncarnationHomeError("incarnation root may not be a symlink")
    existing_marker = incarnation_root / "incarnation-home.json"
    existing: dict[str, Any] = {}
    if incarnation_root.exists():
        if existing_marker.is_symlink() or not existing_marker.is_file():
            raise IncarnationHomeError(
                "existing incarnation home lacks an ownership marker"
            )
        existing = _load_json(existing_marker, "existing incarnation-home manifest")
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

    # Validate ambient inputs before creating a new content-addressed root. A
    # failed first preparation must not leave an unowned directory that blocks
    # the corrected retry.
    ambient_config = _regular_file(
        ambient_home / "config.toml", "ambient Codex config"
    ).read_bytes()
    config = _bound_config(ambient_config, model_slug, effort)
    shared_sources: list[Path] = []
    for source in sorted(ambient_home.iterdir(), key=lambda item: item.name):
        if source.name in LOCAL_NAMES:
            continue
        if source.is_symlink():
            raise IncarnationHomeError(
                f"ambient shared state entry may not be a symlink: {source}"
            )
        shared_sources.append(source)

    incarnation_root.mkdir(mode=0o700, exist_ok=True)
    codex_home.mkdir(mode=0o700, exist_ok=True)
    if incarnation_root.is_symlink() or codex_home.is_symlink():
        raise IncarnationHomeError("incarnation home may not be a symlink")
    incarnation_root.chmod(0o700)
    codex_home.chmod(0o700)
    for name in ("cache", "log", "tmp", DESCENDANT_BIN_NAME):
        local = codex_home / name
        local.mkdir(mode=0o700, exist_ok=True)
        if local.is_symlink() or not local.is_dir():
            raise IncarnationHomeError(f"actor-local {name} is not a real directory")
        local.chmod(0o700)

    _write_exact(codex_home / "config.toml", config, 0o600)

    previous_shared_names: set[str] = set()
    if incarnation_root.exists() and isinstance(existing.get("shared_state_names"), list):
        previous_shared_names = {
            name
            for name in existing["shared_state_names"]
            if isinstance(name, str) and name not in LOCAL_NAMES and Path(name).name == name
        }
    shared_names: list[str] = []
    for source in shared_sources:
        if source.is_symlink():
            raise IncarnationHomeError(
                f"ambient shared state entry may not be a symlink: {source}"
            )
        target = codex_home / source.name
        if target.is_symlink():
            if target.readlink() != source:
                raise IncarnationHomeError(f"shared state link drift: {target}")
        elif target.exists():
            raise IncarnationHomeError(f"shared state target is not a symlink: {target}")
        else:
            target.symlink_to(source)
        shared_names.append(source.name)

    for name in sorted(previous_shared_names - set(shared_names)):
        target = codex_home / name
        source = ambient_home / name
        if not target.is_symlink() or target.readlink() != source:
            raise IncarnationHomeError(f"obsolete shared state link drift: {target}")
        target.unlink()

    manifest = {
        "schema_version": SCHEMA_VERSION,
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
        "top_level_posture": "ambient-home",
        "child_posture": "incarnation-home-via-shell-environment-policy",
    }
    _write_exact(
        incarnation_root / "incarnation-home.json",
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n",
        0o600,
    )
    return manifest


def _load_manifest_snapshot(
    path: Path, *, snapshot_bytes: bytes | None = None
) -> tuple[dict[str, Any], bytes, str]:
    if snapshot_bytes is None:
        manifest, raw = _load_json_snapshot(path, "incarnation-home manifest")
    else:
        raw = snapshot_bytes
        manifest = _decode_json_snapshot(
            raw, "incarnation-home manifest snapshot"
        )
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise IncarnationHomeError("unsupported incarnation-home manifest")
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
    expected_home = (
        runtime_root
        / (
            "sha256-"
            + _incarnation_coordinate(
                str(realization.get("model_realization_id")), fingerprint
            ).removeprefix("sha256:")
        )
        / "codex-home"
    ).resolve()
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
        entry.name
        for entry in ambient_home.iterdir()
        if entry.name not in LOCAL_NAMES
    )
    if sorted(shared_names) != expected_shared_names:
        raise IncarnationHomeError("shared-state manifest no longer matches ambient home")
    expected_names = set(shared_names) | LOCAL_NAMES
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
            raise IncarnationHomeError(f"shared-state link drift: {target}")
    for name in LOCAL_NAMES - {"config.toml"}:
        local = codex_home / name
        if local.is_symlink() or not local.is_dir():
            raise IncarnationHomeError(f"actor-local {name} is not a real directory")
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
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


def command_payload_launch(args: argparse.Namespace) -> int:
    """Bind the receipt to the exact process that owns the private payload."""

    manifest_path = Path(args.manifest)
    manifest_snapshot_b64 = getattr(args, "manifest_snapshot_b64", None)
    if manifest_snapshot_b64 is None:
        manifest_path = _regular_file(manifest_path, "incarnation-home manifest")
        manifest, manifest_bytes, manifest_digest = _load_manifest_snapshot(
            manifest_path
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
            manifest_path, snapshot_bytes=manifest_bytes
        )
    if manifest_digest != args.manifest_digest:
        raise IncarnationHomeError("payload launch manifest digest drifted")

    binding_context: dict[str, str] | None = None
    binding_context_path = getattr(args, "binding_context", None)
    binding_context_snapshot_b64 = getattr(args, "binding_context_snapshot_b64", None)
    binding_context_digest = getattr(args, "binding_context_digest", None)
    control_socket = getattr(args, "control_socket", None)
    terminal_title = getattr(args, "terminal_title", None)
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
        binding_context = _load_binding_context_snapshot(binding_context_bytes)
    elif binding_context_path is not None:
        binding_context = _load_binding_context(Path(binding_context_path))
    if binding_context is not None and (
        not isinstance(control_socket, str) or not isinstance(terminal_title, str)
    ):
        raise IncarnationHomeError(
            "payload terminal binding lacks control socket or title"
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
    environment["CODEX_HOME"] = str(manifest["ambient_codex_home"])
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
            binding_context=binding_context,
            control_socket=control_socket,
            terminal_title=terminal_title,
        )
    os.execve(str(payload_path), payload_argv, environment)
    return 127


def command_launch(args: argparse.Namespace) -> int:
    terminal_title = getattr(args, "terminal_title", None)
    holder_receipt_argument = getattr(args, "holder_receipt", None)
    binding_context_argument = getattr(args, "binding_context", None)
    if terminal_title and (not holder_receipt_argument or not binding_context_argument):
        raise IncarnationHomeError(
            "canonical visible launch requires --holder-receipt and --binding-context"
        )
    manifest_path = _regular_file(Path(args.manifest), "incarnation-home manifest")
    manifest, manifest_bytes, manifest_digest = _load_manifest_snapshot(manifest_path)
    command = Path(args.codex_executable)
    executable = _resolved_executable(command)
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(manifest["ambient_codex_home"])
    if terminal_title:
        _binding_context_value, binding_context_bytes = _load_json_snapshot(
            Path(binding_context_argument), "terminal binding context"
        )
        binding_context = _load_binding_context_snapshot(binding_context_bytes)
        binding_context_digest = sha256_bytes(binding_context_bytes)
        control_socket = getattr(args, "control_socket", None) or _allocate_control_socket()
        _socket_path(control_socket)
        _validate_socket_parent(_socket_path(control_socket))
        if _socket_path(control_socket).exists() or _socket_path(control_socket).is_symlink():
            raise IncarnationHomeError(
                f"control socket path is already occupied: {control_socket}"
            )
        holder_receipt_path = Path(holder_receipt_argument)
        _require_unoccupied_receipt_path(holder_receipt_path)
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
        launcher_fd: int | None = None
        cleanup_started = False
        launch_candidate: dict[str, Any] | None = None
        launch_accepted = False
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
                "--binding-context-snapshot-b64",
                base64.b64encode(binding_context_bytes).decode("ascii"),
                "--binding-context-digest",
                binding_context_digest,
                "--control-socket",
                control_socket,
                "--terminal-title",
                terminal_title,
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
                                control_socket=control_socket,
                                terminal_title=terminal_title,
                                companion_binding=companion_binding,
                            )
                            _validate_terminal_binding_shape(candidate["binding"])
                            # Keep an exact, launch-admitted receipt available
                            # while the post-exec identity can still be a
                            # transient helper shape.  If admission ultimately
                            # fails, finally must be able to terminate that
                            # exact holder rather than leaving the child live.
                            launch_candidate = candidate
                            _holder_terminal_identity(candidate)
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
            if not launch_accepted and launch_candidate is not None:
                if not _terminate_rejected_visible_launch(launch_candidate):
                    rejected_cleanup_error = IncarnationHomeError(
                        "rejected visible launch holder did not terminate"
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
            )
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


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    subcommands = root.add_subparsers(dest="command", required=True)
    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("--ambient-codex-home", required=True)
    prepare.add_argument("--model-realization", required=True)
    prepare.add_argument("--runtime-root", required=True)
    prepare.set_defaults(handler=command_prepare)
    launch = subcommands.add_parser("launch")
    launch.add_argument("--manifest", required=True)
    launch.add_argument("--codex-executable", required=True)
    launch.add_argument("--terminal-title")
    launch.add_argument("--kitty-executable", default="/usr/bin/kitty")
    launch.add_argument(
        "--holder-receipt",
        help=(
            "non-replacing receipt for this direct responsibility-holder process; "
            "the shebang payload writes it immediately before exec"
        ),
    )
    launch.add_argument(
        "--binding-context",
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
    payload.add_argument("--holder-receipt")
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
    payload.add_argument("codex_arguments", nargs=argparse.REMAINDER)
    payload.set_defaults(handler=command_payload_launch)
    bind = subcommands.add_parser("bind")
    bind.add_argument("--holder-receipt", required=True)
    bind.add_argument("--binding-context", required=True)
    bind.add_argument("--output", required=True)
    bind.set_defaults(handler=command_bind)
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
