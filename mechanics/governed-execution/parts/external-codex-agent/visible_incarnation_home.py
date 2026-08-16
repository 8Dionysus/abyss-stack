#!/usr/bin/env python3
"""Prepare and enter a Codex home whose default follows one incarnation.

The operator-visible Codex process keeps the ambient user home so existing
sessions and hook trust retain their identity.  Its shell children receive the
incarnation home through Codex's shell environment policy; a plain nested
``codex exec`` therefore keeps the selected model and reasoning effort.
"""

from __future__ import annotations

import argparse
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
                    str(Path(resolved).resolve()),
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
        if executable_digest is None:
            executable_digest = sha256_bytes(
                executable_bytes
                if executable_bytes is not None
                else executable.read_bytes()
            )
        if manifest_digest is None:
            manifest_digest = sha256_bytes(
                manifest_bytes
                if manifest_bytes is not None
                else manifest_path.read_bytes()
            )
    except OSError as exc:
        raise IncarnationHomeError("holder identity inputs could not be hashed") from exc
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
        "runtime": {
            "codex_executable": str(executable),
            "codex_executable_digest": executable_digest,
            "incarnation_manifest": str(manifest_path.resolve()),
            "incarnation_manifest_digest": manifest_digest,
            "model": str(manifest["model_slug"]),
            "reasoning_effort": str(manifest["reasoning_effort"]),
            "ambient_codex_home": str(manifest["ambient_codex_home"]),
            "incarnation_codex_home": str(manifest["codex_home"]),
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
    }
    _write_new_json(receipt_path, receipt, "holder terminal receipt")
    return receipt


def _validate_wake_delivery(
    *,
    wake_receipt_path: Path,
    handoff_path: Path,
    holder_receipt_path: Path,
    closure_receipt_path: Path,
    holder_receipt: dict[str, Any],
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
    try:
        holder_digest = sha256_bytes(holder_receipt_path.read_bytes())
    except OSError as exc:
        raise IncarnationHomeError("holder receipt could not be hashed") from exc
    if responsibility_holder.get("terminal_receipt_sha256") != holder_digest:
        raise IncarnationHomeError("handoff holder receipt digest mismatch")
    if responsibility_holder.get("holder_pid") != holder_receipt["holder"].get("pid"):
        raise IncarnationHomeError("handoff responsibility-holder PID mismatch")
    if responsibility_holder.get("terminal_pid") != holder_receipt["terminal"].get("pid"):
        raise IncarnationHomeError("handoff terminal PID mismatch")
    return wake


def _load_holder_receipt(path: Path) -> dict[str, Any]:
    receipt = _load_json(path, "holder terminal receipt")
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
        or not isinstance(holder.get("argv"), list)
        or not all(isinstance(item, str) for item in holder["argv"])
    ):
        raise IncarnationHomeError("holder terminal receipt is incomplete")
    return receipt


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
    manifest = _regular_file(
        Path(str(runtime["incarnation_manifest"])), "holder incarnation manifest"
    )
    if sha256_bytes(executable.read_bytes()) != runtime.get("codex_executable_digest"):
        raise IncarnationHomeError("holder Codex executable digest has drifted")
    if sha256_bytes(manifest.read_bytes()) != runtime.get("incarnation_manifest_digest"):
        raise IncarnationHomeError("holder incarnation manifest digest has drifted")
    return pid, kitty_pid, _proc_comm(kitty_pid), window_id, dedicated


def command_close(args: argparse.Namespace) -> int:
    handoff_path = _regular_file(Path(args.handoff), "handoff")
    holder_receipt_path = _regular_file(
        Path(args.holder_receipt), "holder terminal receipt"
    )
    closure_receipt_path = Path(args.closure_receipt)
    receipt = _load_holder_receipt(holder_receipt_path)
    _validate_wake_delivery(
        wake_receipt_path=Path(args.wake_receipt),
        handoff_path=handoff_path,
        holder_receipt_path=holder_receipt_path,
        closure_receipt_path=closure_receipt_path,
        holder_receipt=receipt,
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
                if failure is None:
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


def _open_verified_executable(
    executable: Path,
) -> tuple[int, Path, bytes, str]:
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
    expected = "codex-cli " + runtime_version
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
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
            f"Codex runtime version mismatch: expected {expected}, got {observed or '<empty>'}"
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
    executable_fd, executable_fd_path, executable_bytes, executable_digest = (
        _open_verified_executable(executable)
    )
    try:
        _verify_executable_version(
            executable_fd_path,
            str(manifest["runtime_version"]),
            pass_fds=(executable_fd,),
        )
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
        if args.holder_receipt:
            _holder_receipt(
                receipt_path=Path(args.holder_receipt),
                manifest_path=manifest_path,
                manifest=manifest,
                executable=executable,
                argv=exec_argv,
                executable_bytes=executable_bytes,
                executable_digest=executable_digest,
                manifest_bytes=manifest_bytes,
                manifest_digest=manifest_digest,
            )
        os.execve(str(executable_fd_path), exec_argv, environment)
        return 127
    finally:
        os.close(executable_fd)


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
            "the receipt is written immediately before exec"
        ),
    )
    launch.add_argument("codex_arguments", nargs=argparse.REMAINDER)
    launch.set_defaults(handler=command_launch)
    close = subcommands.add_parser("close")
    close.add_argument("--holder-receipt", required=True)
    close.add_argument("--wake-receipt", required=True)
    close.add_argument("--handoff", required=True)
    close.add_argument("--closure-receipt", required=True)
    close.set_defaults(handler=command_close)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "launch" and args.codex_arguments[:1] == ["--"]:
        args.codex_arguments = args.codex_arguments[1:]
    if args.command == "launch" and not args.codex_arguments:
        raise IncarnationHomeError("launch requires Codex arguments after --")
    return int(args.handler(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IncarnationHomeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
