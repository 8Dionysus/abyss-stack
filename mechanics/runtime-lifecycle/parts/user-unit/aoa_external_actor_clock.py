#!/usr/bin/env python3
"""Keep a detached Kitty clock owned by a truthful foreground supervisor."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


POLL_SECONDS = 0.1
DEFAULT_LAUNCH_TIMEOUT_SECONDS = 30.0
DEFAULT_CLOSE_TIMEOUT_SECONDS = 15.0
STATUS_SCHEMA = "aoa_external_actor_clock_status_v1"
_STOP_SIGNAL: int | None = None


class ClockSupervisorError(RuntimeError):
    """A clock could not establish or complete its bounded lifecycle."""


def _handle_stop(signum: int, _frame: object) -> None:
    global _STOP_SIGNAL
    _STOP_SIGNAL = signum


def _utc_now() -> str:
    completed = subprocess.run(
        ["/usr/bin/date", "--iso-8601=seconds", "--utc"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _proc_argv(pid: int) -> tuple[str, ...] | None:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    if not raw:
        return None
    return tuple(os.fsdecode(part) for part in raw.split(b"\0") if part)


def _proc_start_ticks(pid: int) -> int | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_bytes()
    except OSError:
        return None
    closing_paren = raw.rfind(b")")
    if closing_paren < 0:
        return None
    fields = raw[closing_paren + 2 :].split()
    if len(fields) <= 19:
        return None
    try:
        return int(fields[19])
    except ValueError:
        return None


def _proc_comm(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _matching_kitties(title: str) -> dict[int, int]:
    matches: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        pid = int(entry.name)
        if _proc_comm(pid) != "kitty":
            continue
        argv = _proc_argv(pid)
        if argv is None or "--detach" not in argv:
            continue
        try:
            title_index = argv.index("--title")
        except ValueError:
            continue
        if title_index + 1 >= len(argv) or argv[title_index + 1] != title:
            continue
        start_ticks = _proc_start_ticks(pid)
        if start_ticks is not None:
            matches[pid] = start_ticks
    return matches


def _identity_live(pid: int, start_ticks: int) -> bool:
    observed = _proc_start_ticks(pid)
    return observed is not None and observed == start_ticks


def _append_error(path: Path, message: str) -> None:
    line = f"{_utc_now()} {message}\n"
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC,
            0o600,
        )
        try:
            os.write(descriptor, line.encode("utf-8"))
        finally:
            os.close(descriptor)
    except OSError as exc:
        print(f"clock error evidence unavailable at {path}: {exc}", file=sys.stderr)
    print(f"clock supervisor: {message}", file=sys.stderr, flush=True)


def _read_status(path: Path) -> int:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ClockSupervisorError(f"clock status cannot be read: {path}") from exc
    values: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    if values.get("schema_version") != STATUS_SCHEMA:
        raise ClockSupervisorError("clock status schema is invalid")
    try:
        result = int(values["runner_exit_status"])
    except (KeyError, ValueError) as exc:
        raise ClockSupervisorError("clock status exit code is invalid") from exc
    if result < 0 or result > 255:
        raise ClockSupervisorError("clock status exit code is outside 0..255")
    return result


def _terminate_kitty(pid: int | None, start_ticks: int | None) -> None:
    if pid is None or start_ticks is None or not _identity_live(pid, start_ticks):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + DEFAULT_CLOSE_TIMEOUT_SECONDS
    while time.monotonic() < deadline and _identity_live(pid, start_ticks):
        time.sleep(POLL_SECONDS)


def _required_environment() -> tuple[str, str, Path, Path]:
    runner = os.environ.get("AOA_CLOCK_RUNNER", "")
    title = os.environ.get("AOA_CLOCK_TITLE", "")
    if not runner or not Path(runner).is_absolute():
        raise ClockSupervisorError("AOA_CLOCK_RUNNER must be an absolute path")
    if not os.access(runner, os.X_OK):
        raise ClockSupervisorError(f"clock runner is not executable: {runner}")
    if not title or any(character in title for character in "\x00\r\n"):
        raise ClockSupervisorError("AOA_CLOCK_TITLE must be non-empty and single-line")
    status = Path(
        os.environ.get("AOA_CLOCK_STATUS_FILE", f"{runner}.systemd-status")
    )
    error = Path(
        os.environ.get("AOA_CLOCK_ERROR_LOG", f"{runner}.systemd-error.log")
    )
    for path, label in ((status, "status"), (error, "error")):
        if not path.is_absolute() or path.is_symlink():
            raise ClockSupervisorError(f"clock {label} path is unsafe: {path}")
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise ClockSupervisorError(f"clock {label} parent is unavailable: {path.parent}")
    if status.exists():
        raise ClockSupervisorError(f"clock status already exists: {status}")
    return runner, title, status, error


def _runner_command() -> str:
    return """set +e
\"$AOA_CLOCK_RUNNER\" 2> >(tee -a -- \"$AOA_CLOCK_ERROR_LOG\" >&2)
runner_rc=$?
umask 077
status_tmp=\"${AOA_CLOCK_STATUS_FILE}.$$\"
if ! {
  printf 'schema_version=%s\\n' 'aoa_external_actor_clock_status_v1'
  printf 'runner_pid=%s\\n' \"$$\"
  printf 'runner_finished_at=%s\\n' \"$(/usr/bin/date --iso-8601=seconds --utc)\"
  printf 'runner_exit_status=%s\\n' \"$runner_rc\"
} >\"$status_tmp\" || ! /usr/bin/mv -f -- \"$status_tmp\" \"$AOA_CLOCK_STATUS_FILE\"; then
  print -u2 -- \"clock status publication failed: $AOA_CLOCK_STATUS_FILE\"
  /usr/bin/rm -f -- \"$status_tmp\"
  exit 125
fi
exit \"$runner_rc\"
"""


def main() -> int:
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)
    runner, title, status_path, error_path = _required_environment()
    baseline = _matching_kitties(title)
    child_environment = dict(os.environ)
    child_environment["AOA_CLOCK_STATUS_FILE"] = str(status_path)
    child_environment["AOA_CLOCK_ERROR_LOG"] = str(error_path)
    child_environment["AOA_CLOCK_RUNNER"] = runner

    print(
        f"clock supervisor: dispatching detached Kitty title={title!r}",
        flush=True,
    )
    try:
        dispatched = subprocess.run(
            [
                "/usr/bin/kitty",
                "--detach",
                "--title",
                title,
                "/usr/bin/zsh",
                "-lc",
                _runner_command(),
            ],
            check=False,
            env=child_environment,
        )
    except OSError as exc:
        _append_error(error_path, f"detached Kitty dispatch failed: {exc}")
        return 127
    if _STOP_SIGNAL is not None:
        for pid, start_ticks in _matching_kitties(title).items():
            if baseline.get(pid) != start_ticks:
                _terminate_kitty(pid, start_ticks)
        return 128 + _STOP_SIGNAL
    if dispatched.returncode != 0:
        _append_error(
            error_path,
            f"detached Kitty dispatch returned {dispatched.returncode}",
        )
        return dispatched.returncode

    kitty_pid: int | None = None
    kitty_start_ticks: int | None = None
    launch_deadline = time.monotonic() + float(
        os.environ.get(
            "AOA_CLOCK_LAUNCH_TIMEOUT_SEC", str(DEFAULT_LAUNCH_TIMEOUT_SECONDS)
        )
    )
    while kitty_pid is None:
        if _STOP_SIGNAL is not None:
            for pid, start_ticks in _matching_kitties(title).items():
                if baseline.get(pid) != start_ticks:
                    _terminate_kitty(pid, start_ticks)
            _append_error(
                error_path,
                f"clock supervisor stopped by signal {_STOP_SIGNAL}",
            )
            return 128 + _STOP_SIGNAL
        matches = _matching_kitties(title)
        new_matches = {
            pid: start
            for pid, start in matches.items()
            if baseline.get(pid) != start
        }
        if len(new_matches) == 1:
            kitty_pid, kitty_start_ticks = next(iter(new_matches.items()))
            print(
                f"clock supervisor: detached Kitty pid={kitty_pid} "
                f"start_ticks={kitty_start_ticks}",
                flush=True,
            )
            break
        if len(new_matches) > 1:
            _append_error(
                error_path,
                f"multiple detached Kitty holders matched title {title!r}: "
                f"{sorted(new_matches)}",
            )
            for pid, start_ticks in new_matches.items():
                _terminate_kitty(pid, start_ticks)
            return 125
        if time.monotonic() >= launch_deadline:
            _append_error(
                error_path,
                f"detached Kitty holder did not appear for title {title!r}",
            )
            return 125
        time.sleep(POLL_SECONDS)

    assert kitty_pid is not None
    assert kitty_start_ticks is not None
    while not status_path.exists():
        if _STOP_SIGNAL is not None:
            _append_error(
                error_path,
                f"clock supervisor stopped by signal {_STOP_SIGNAL}",
            )
            _terminate_kitty(kitty_pid, kitty_start_ticks)
            return 128 + _STOP_SIGNAL
        if not _identity_live(kitty_pid, kitty_start_ticks):
            _append_error(
                error_path,
                "detached Kitty exited before publishing runner status",
            )
            return 125
        time.sleep(POLL_SECONDS)

    try:
        runner_status = _read_status(status_path)
    except ClockSupervisorError as exc:
        _append_error(error_path, str(exc))
        _terminate_kitty(kitty_pid, kitty_start_ticks)
        return 125

    close_deadline = time.monotonic() + float(
        os.environ.get(
            "AOA_CLOCK_CLOSE_TIMEOUT_SEC", str(DEFAULT_CLOSE_TIMEOUT_SECONDS)
        )
    )
    while _identity_live(kitty_pid, kitty_start_ticks):
        if _STOP_SIGNAL is not None:
            _append_error(
                error_path,
                f"clock supervisor stopped by signal {_STOP_SIGNAL}",
            )
            _terminate_kitty(kitty_pid, kitty_start_ticks)
            return 128 + _STOP_SIGNAL
        if time.monotonic() >= close_deadline:
            _append_error(
                error_path,
                "detached Kitty remained live after runner status publication",
            )
            _terminate_kitty(kitty_pid, kitty_start_ticks)
            return 125
        time.sleep(POLL_SECONDS)

    print(
        f"clock supervisor: detached Kitty closed; runner_exit_status={runner_status}",
        flush=True,
    )
    return runner_status


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClockSupervisorError as exc:
        print(f"clock supervisor: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(125) from exc
