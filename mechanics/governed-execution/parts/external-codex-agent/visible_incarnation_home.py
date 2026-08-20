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
TERMINAL_CLOSURE_SCHEMA_VERSION = "abyss_stack_visible_incarnation_terminal_closure_v1"
CLOSURE_RESERVATION_SCHEMA_VERSION = "abyss_stack_visible_incarnation_terminal_closure_reservation_v1"
DESCENDANT_BIN_NAME = ".codex-incarnation-bin"
CODE_MODE_HOST_NAME = "codex-code-mode-host"
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


def _load_json_snapshot(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = _regular_file(path, label).read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IncarnationHomeError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise IncarnationHomeError(f"{label} must be a JSON object")
    return value, raw


def _load_json(path: Path, label: str) -> dict[str, Any]:
    value, _ = _load_json_snapshot(path, label)
    return value


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


def _send_verified_term(pid: int, start_ticks: int) -> bool:
    """Send TERM to the exact holder through a pidfd after rechecking it."""

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
            pidfd_send_signal(pidfd, signal.SIGTERM)
        except ProcessLookupError:
            return False
        return True
    except OSError as exc:
        raise IncarnationHomeError("verified holder TERM delivery failed") from exc
    finally:
        os.close(pidfd)


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
    expected = {
        "schema_version": CLOSURE_RESERVATION_SCHEMA_VERSION,
        "closure_receipt_ref": str(closure_receipt_path.resolve()),
        "handoff_ref": str(handoff_path.resolve()),
        "holder_receipt_ref": str(holder_receipt_path.resolve()),
        "wake_receipt_ref": str(wake_receipt_path.resolve()),
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
            _write_new_json(
                reservation_path,
                {**expected, "reserved_at": _utc_now()},
                "terminal closure reservation",
            )
        recorded = _load_json(
            reservation_path, "terminal closure reservation"
        )
        if any(recorded.get(key) != value for key, value in expected.items()):
            raise IncarnationHomeError("terminal closure reservation identity mismatch")
        completed: dict[str, Any] | None = None
        if closure_receipt_path.exists():
            completed = _load_json(
                closure_receipt_path, "terminal closure receipt"
            )
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
        "terminal": {
            "binding": "kitty_ancestor_at_exec",
            "required_comm": "kitty",
            "pid": terminal_pid,
            "start_ticks": terminal_start_ticks,
            "argv": terminal_argv,
            "window_id": window_id,
            "dedicated": dedicated,
        },
    }
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
) -> dict[str, Any]:
    wake = _load_json(wake_receipt_path, "wake receipt")
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
    try:
        handoff_file = _regular_file(handoff_path, "handoff")
        handoff_bytes = handoff_file.read_bytes()
        handoff_digest = sha256_bytes(handoff_bytes)
        handoff_value = json.loads(handoff_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IncarnationHomeError("cannot read delivered handoff snapshot") from exc
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


def _load_holder_receipt_snapshot(
    path: Path,
) -> tuple[dict[str, Any], bytes, str]:
    receipt, raw = _load_json_snapshot(path, "holder terminal receipt")
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
    executable = _regular_file(
        Path(str(runtime["codex_executable"])), "holder Codex executable"
    )
    if sha256_bytes(executable.read_bytes()) != runtime.get("codex_executable_digest"):
        raise IncarnationHomeError("holder Codex executable digest has drifted")
    companion = runtime.get("codex_companion")
    if companion is not None:
        if not isinstance(companion, dict):
            raise IncarnationHomeError("holder Codex companion binding is incomplete")
        companion_path = companion.get("path")
        companion_digest = companion.get("digest")
        expected_companion = executable.parent / CODE_MODE_HOST_NAME
        expected_companion_relative = expected_companion.relative_to(
            _package_root(executable)
        ).as_posix()
        if (
            companion_path != str(expected_companion)
            or companion.get("relation") != "adjacent_immutable_package"
            or companion.get("package_relative") != expected_companion_relative
            or not isinstance(companion_digest, str)
        ):
            raise IncarnationHomeError("holder Codex companion binding has drifted")
        companion_file = _regular_file(
            expected_companion, "holder Codex companion"
        )
        if sha256_bytes(companion_file.read_bytes()) != companion_digest:
            raise IncarnationHomeError("holder Codex companion digest has drifted")
    manifest_snapshot = _decode_holder_manifest_snapshot(runtime)
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


def command_close(args: argparse.Namespace) -> int:
    handoff_path = _regular_file(Path(args.handoff), "handoff")
    holder_receipt_path = _regular_file(
        Path(args.holder_receipt), "holder terminal receipt"
    )
    closure_receipt_path = Path(args.closure_receipt)
    receipt, holder_receipt_bytes, holder_receipt_digest = (
        _load_holder_receipt_snapshot(holder_receipt_path)
    )
    _validate_wake_delivery(
        wake_receipt_path=Path(args.wake_receipt),
        handoff_path=handoff_path,
        holder_receipt_path=holder_receipt_path,
        closure_receipt_path=closure_receipt_path,
        holder_receipt=receipt,
        holder_receipt_bytes=holder_receipt_bytes,
        holder_receipt_digest=holder_receipt_digest,
    )
    holder_pid, holder_start_ticks, kitty_pid, kitty_start_ticks = (
        _holder_receipt_process_ids(receipt)
    )
    kitty_argv = receipt["terminal"]["argv"]
    kitty_comm = receipt["terminal"].get("required_comm", "kitty")
    kitty_window_id = receipt["terminal"].get("window_id")
    kitty_dedicated = receipt["terminal"].get("dedicated")
    reservation_fd, reservation_path, completed = _reserve_closure_receipt(
        closure_receipt_path=closure_receipt_path,
        handoff_path=handoff_path,
        holder_receipt_path=holder_receipt_path,
        wake_receipt_path=Path(args.wake_receipt),
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
            "wake_receipt_ref": str(Path(args.wake_receipt).resolve()),
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
            "trigger": "wake_bridge_after_confirmed_handoff_delivery",
        }
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
    path: Path,
) -> tuple[dict[str, Any], bytes, str]:
    manifest, raw = _load_json_snapshot(path, "incarnation-home manifest")
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
    """Build a private package snapshot with stable ancestor coordinates."""

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
            for entry in source_dir.iterdir():
                if entry.name == component:
                    continue
                os.symlink(
                    os.fspath(entry),
                    os.fspath(target_dir / entry.name),
                    target_is_directory=entry.is_dir(),
                )
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

    manifest_path = _regular_file(Path(args.manifest), "incarnation-home manifest")
    manifest, manifest_bytes, manifest_digest = _load_manifest_snapshot(manifest_path)
    if manifest_digest != args.manifest_digest:
        raise IncarnationHomeError("payload launch manifest digest drifted")

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
        )
    os.execve(str(payload_path), payload_argv, environment)
    return 127


def command_launch(args: argparse.Namespace) -> int:
    if args.holder_receipt and args.terminal_title:
        raise IncarnationHomeError(
            "holder terminal receipt requires direct exec; it cannot bind a detached Kitty"
        )
    manifest_path = _regular_file(Path(args.manifest), "incarnation-home manifest")
    manifest, manifest_bytes, manifest_digest = _load_manifest_snapshot(manifest_path)
    command = Path(args.codex_executable)
    executable = _resolved_executable(command)
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(manifest["ambient_codex_home"])
    if args.terminal_title:
        _verify_executable_version(executable, str(manifest["runtime_version"]))
        argv = bound_codex_argv(
            codex_executable=command,
            manifest=manifest,
            arguments=args.codex_arguments,
            resolved_executable=executable,
        )
        completed = subprocess.run(
            [args.kitty_executable, "--detach", "--title", args.terminal_title, *argv],
            check=False,
            env=environment,
        )
        return completed.returncode
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
    launch.add_argument("codex_arguments", nargs=argparse.REMAINDER)
    launch.set_defaults(handler=command_launch)
    payload = subcommands.add_parser("payload-launch")
    payload.add_argument("--manifest", required=True)
    payload.add_argument("--holder-receipt")
    payload.add_argument("--codex-executable", required=True)
    payload.add_argument("--payload-executable", required=True)
    payload.add_argument("--manifest-digest", required=True)
    payload.add_argument("--executable-digest", required=True)
    payload.add_argument("--companion-path")
    payload.add_argument("--companion-digest")
    payload.add_argument("--companion-relative")
    payload.add_argument("codex_arguments", nargs=argparse.REMAINDER)
    payload.set_defaults(handler=command_payload_launch)
    close = subcommands.add_parser("close")
    close.add_argument("--holder-receipt", required=True)
    close.add_argument("--wake-receipt", required=True)
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
