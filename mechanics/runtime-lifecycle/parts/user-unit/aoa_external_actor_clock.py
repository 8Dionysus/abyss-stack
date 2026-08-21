#!/usr/bin/env python3
"""Keep a detached Kitty clock owned by a truthful foreground supervisor."""

from __future__ import annotations

import os
import math
import signal
import subprocess
import sys
import time
from pathlib import Path


POLL_SECONDS = 0.1
DEFAULT_LAUNCH_TIMEOUT_SECONDS = 30.0
DEFAULT_CLOSE_TIMEOUT_SECONDS = 15.0
STOP_CLEANUP_TIMEOUT_SECONDS = 10.0
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


def _terminate_kitty(
    pid: int | None,
    start_ticks: int | None,
    close_timeout_seconds: float = DEFAULT_CLOSE_TIMEOUT_SECONDS,
    close_deadline: float | None = None,
) -> None:
    if pid is None or start_ticks is None or not _identity_live(pid, start_ticks):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = (
        close_deadline
        if close_deadline is not None
        else time.monotonic() + close_timeout_seconds
    )
    while time.monotonic() < deadline and _identity_live(pid, start_ticks):
        time.sleep(POLL_SECONDS)


def _stop_cleanup_deadline(close_timeout_seconds: float) -> float:
    return time.monotonic() + min(
        close_timeout_seconds,
        STOP_CLEANUP_TIMEOUT_SECONDS,
    )


def _finite_timeout(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ClockSupervisorError(f"{name} must be a finite positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ClockSupervisorError(f"{name} must be a finite positive number")
    return value


def _validate_evidence_path(path: Path, label: str) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise ClockSupervisorError(f"clock {label} path is unsafe: {path}")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ClockSupervisorError(f"clock {label} parent is unavailable: {path.parent}")


def _configuration_error_path() -> Path | None:
    raw_error = os.environ.get("AOA_CLOCK_ERROR_LOG", "")
    if not raw_error:
        return None
    error = Path(raw_error)
    try:
        _validate_evidence_path(error, "error")
    except ClockSupervisorError:
        return None
    if error.exists():
        if not error.is_file():
            return None
    raw_status = os.environ.get("AOA_CLOCK_STATUS_FILE", "")
    if raw_status:
        status = Path(raw_status)
        try:
            if status.resolve(strict=False) == error.resolve(strict=False):
                return None
        except OSError:
            return None
    try:
        _check_error_log(error)
    except ClockSupervisorError:
        return None
    return error


def _check_error_log(path: Path) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC,
            0o600,
        )
        os.fchmod(descriptor, 0o600)
    except OSError as exc:
        raise ClockSupervisorError(f"clock error path is not append-writable: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _write_marker(path: Path, content: str) -> None:
    temporary = Path(f"{path}.{os.getpid()}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            0o600,
        )
        payload = content.encode("utf-8")
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, path)
    except OSError as exc:
        raise ClockSupervisorError(f"clock marker publication failed: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
        except OSError as exc:
            raise ClockSupervisorError(
                f"clock marker temporary cleanup failed: {temporary}"
            ) from exc


def _required_environment() -> tuple[str, str, Path, Path, Path, Path, float, float]:
    runner = os.environ.get("AOA_CLOCK_RUNNER", "")
    title = os.environ.get("AOA_CLOCK_TITLE", "")
    if not runner or not Path(runner).is_absolute():
        raise ClockSupervisorError("AOA_CLOCK_RUNNER must be an absolute path")
    if not os.access(runner, os.X_OK):
        raise ClockSupervisorError(f"clock runner is not executable: {runner}")
    if not title or any(character in title for character in "\x00\r\n"):
        raise ClockSupervisorError("AOA_CLOCK_TITLE must be non-empty and single-line")
    status_value = os.environ.get("AOA_CLOCK_STATUS_FILE", "")
    error_value = os.environ.get("AOA_CLOCK_ERROR_LOG", "")
    if not status_value or not error_value:
        raise ClockSupervisorError(
            "AOA_CLOCK_STATUS_FILE and AOA_CLOCK_ERROR_LOG must be explicit runtime paths"
        )
    status = Path(status_value)
    error = Path(error_value)
    for path, label in ((status, "status"), (error, "error")):
        _validate_evidence_path(path, label)
    if status.resolve(strict=False) == error.resolve(strict=False):
        raise ClockSupervisorError("clock status and error paths must be distinct")
    if status.exists():
        raise ClockSupervisorError(f"clock status already exists: {status}")
    if error.exists() and not error.is_file():
        raise ClockSupervisorError(f"clock error path is not a regular file: {error}")
    _check_error_log(error)
    ready = Path(f"{status}.holder-ready")
    captured = Path(f"{status}.holder-captured")
    for path, label in ((ready, "holder-ready"), (captured, "holder-captured")):
        _validate_evidence_path(path, label)
        if path.exists():
            raise ClockSupervisorError(f"clock {label} marker already exists: {path}")
    evidence_paths = {
        status.resolve(strict=False),
        error.resolve(strict=False),
        ready.resolve(strict=False),
        captured.resolve(strict=False),
    }
    if len(evidence_paths) != 4:
        raise ClockSupervisorError("clock evidence paths must be distinct")
    launch_timeout = _finite_timeout(
        "AOA_CLOCK_LAUNCH_TIMEOUT_SEC", DEFAULT_LAUNCH_TIMEOUT_SECONDS
    )
    close_timeout = _finite_timeout(
        "AOA_CLOCK_CLOSE_TIMEOUT_SEC", DEFAULT_CLOSE_TIMEOUT_SECONDS
    )
    return runner, title, status, error, ready, captured, launch_timeout, close_timeout


def _runner_command() -> str:
    return """set +e
umask 077
ready_tmp="${AOA_CLOCK_HOLDER_READY_FILE}.$$"
if ! {
  printf 'holder_pid=%s\\n' "$$"
} >"$ready_tmp" || ! /usr/bin/mv -f -- "$ready_tmp" "$AOA_CLOCK_HOLDER_READY_FILE"; then
  print -u2 -- "clock holder handshake publication failed: $AOA_CLOCK_HOLDER_READY_FILE"
  /usr/bin/rm -f -- "$ready_tmp"
  exit 125
fi
while [[ ! -e "$AOA_CLOCK_HOLDER_CAPTURED_FILE" ]]; do
  /usr/bin/sleep 0.05
done
runner_stderr_tmp=\"${AOA_CLOCK_ERROR_LOG}.runner.$$\"
if ! ( set -o noclobber; : >\"$runner_stderr_tmp\" ); then
  print -u2 -- \"clock runner stderr staging failed: $runner_stderr_tmp\"
  exit 125
fi
\"$AOA_CLOCK_RUNNER\" 2>\"$runner_stderr_tmp\"
runner_rc=$?
logging_rc=0
if ! /usr/bin/tee -a -- \"$AOA_CLOCK_ERROR_LOG\" <\"$runner_stderr_tmp\" >&2; then
  logging_rc=125
fi
if ! /usr/bin/rm -f -- \"$runner_stderr_tmp\"; then
  logging_rc=125
fi
if (( logging_rc != 0 )); then
  runner_rc=125
fi
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
    try:
        (
            runner,
            title,
            status_path,
            error_path,
            ready_path,
            captured_path,
            launch_timeout,
            close_timeout,
        ) = _required_environment()
    except ClockSupervisorError as exc:
        error_path = _configuration_error_path()
        if error_path is not None:
            _append_error(error_path, str(exc))
        raise
    baseline = _matching_kitties(title)
    child_environment = dict(os.environ)
    child_environment["AOA_CLOCK_STATUS_FILE"] = str(status_path)
    child_environment["AOA_CLOCK_ERROR_LOG"] = str(error_path)
    child_environment["AOA_CLOCK_RUNNER"] = runner
    child_environment["AOA_CLOCK_HOLDER_READY_FILE"] = str(ready_path)
    child_environment["AOA_CLOCK_HOLDER_CAPTURED_FILE"] = str(captured_path)

    launch_deadline = time.monotonic() + launch_timeout
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
            timeout=max(POLL_SECONDS, launch_deadline - time.monotonic()),
        )
    except subprocess.TimeoutExpired as exc:
        _append_error(
            error_path,
            f"detached Kitty dispatch exceeded launch timeout {launch_timeout}: {exc}",
        )
        for pid, start_ticks in _matching_kitties(title).items():
            if baseline.get(pid) != start_ticks:
                _terminate_kitty(pid, start_ticks, close_timeout)
        return 125
    except OSError as exc:
        _append_error(error_path, f"detached Kitty dispatch failed: {exc}")
        return 127
    if _STOP_SIGNAL is not None:
        stop_deadline = _stop_cleanup_deadline(close_timeout)
        for pid, start_ticks in _matching_kitties(title).items():
            if baseline.get(pid) != start_ticks:
                _terminate_kitty(
                    pid,
                    start_ticks,
                    close_deadline=stop_deadline,
                )
        return 0
    if dispatched.returncode != 0:
        _append_error(
            error_path,
            f"detached Kitty dispatch returned {dispatched.returncode}",
        )
        return dispatched.returncode

    kitty_pid: int | None = None
    kitty_start_ticks: int | None = None
    while kitty_pid is None:
        if _STOP_SIGNAL is not None:
            stop_deadline = _stop_cleanup_deadline(close_timeout)
            for pid, start_ticks in _matching_kitties(title).items():
                if baseline.get(pid) != start_ticks:
                    _terminate_kitty(
                        pid,
                        start_ticks,
                        close_deadline=stop_deadline,
                    )
            _append_error(
                error_path,
                f"clock supervisor stopped by signal {_STOP_SIGNAL}",
            )
            return 0
        matches = _matching_kitties(title)
        new_matches = {
            pid: start
            for pid, start in matches.items()
            if baseline.get(pid) != start
        }
        if len(new_matches) == 1:
            candidate_pid, candidate_start_ticks = next(iter(new_matches.items()))
            while not ready_path.exists():
                if _STOP_SIGNAL is not None:
                    _terminate_kitty(
                        candidate_pid,
                        candidate_start_ticks,
                        close_deadline=_stop_cleanup_deadline(close_timeout),
                    )
                    _append_error(
                        error_path,
                        f"clock supervisor stopped by signal {_STOP_SIGNAL}",
                    )
                    return 0
                if not _identity_live(candidate_pid, candidate_start_ticks):
                    _append_error(
                        error_path,
                        "detached Kitty exited before holder handshake",
                    )
                    return 125
                if time.monotonic() >= launch_deadline:
                    _append_error(
                        error_path,
                        f"detached Kitty holder did not complete handshake for title {title!r}",
                    )
                    _terminate_kitty(candidate_pid, candidate_start_ticks, close_timeout)
                    return 125
                time.sleep(POLL_SECONDS)
            try:
                _write_marker(
                    captured_path,
                    f"kitty_pid={candidate_pid}\nkitty_start_ticks={candidate_start_ticks}\n",
                )
            except ClockSupervisorError as exc:
                _append_error(error_path, str(exc))
                _terminate_kitty(candidate_pid, candidate_start_ticks, close_timeout)
                return 125
            kitty_pid, kitty_start_ticks = candidate_pid, candidate_start_ticks
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
            ambiguity_deadline = time.monotonic() + close_timeout
            for pid, start_ticks in new_matches.items():
                _terminate_kitty(
                    pid,
                    start_ticks,
                    close_deadline=ambiguity_deadline,
                )
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
            _terminate_kitty(
                kitty_pid,
                kitty_start_ticks,
                close_deadline=_stop_cleanup_deadline(close_timeout),
            )
            return 0
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
        _terminate_kitty(kitty_pid, kitty_start_ticks, close_timeout)
        return 125

    close_deadline = time.monotonic() + close_timeout
    while _identity_live(kitty_pid, kitty_start_ticks):
        if _STOP_SIGNAL is not None:
            _append_error(
                error_path,
                f"clock supervisor stopped by signal {_STOP_SIGNAL}",
            )
            _terminate_kitty(
                kitty_pid,
                kitty_start_ticks,
                close_deadline=_stop_cleanup_deadline(close_timeout),
            )
            return 0
        if time.monotonic() >= close_deadline:
            _append_error(
                error_path,
                "detached Kitty remained live after runner status publication",
            )
            _terminate_kitty(
                kitty_pid,
                kitty_start_ticks,
                close_deadline=close_deadline,
            )
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
