#!/usr/bin/env python3
"""Bounded Linux descendant supervisor for one external Codex invocation.

The worker launches this process as the attempt session leader.  The supervisor
is a Linux child subreaper and asks the kernel for ``SIGTERM`` if its exact
worker parent dies.  It deliberately does not create another PID or network
namespace: Codex must remain free to construct its own bubblewrap sandbox.
When repository configuration must be hidden, the supervisor may add one
filesystem-only bubblewrap parent around Codex.  Rootless bubblewrap implements
that contour with user and mount namespaces; it adds no process or network
policy and does not replace the separately identified Codex process in the
durable receipt.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import select
import signal
import socket
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn


PR_SET_PDEATHSIG = 1
PR_SET_CHILD_SUBREAPER = 36
SUPERVISOR_SETUP_FAILED = 125
SUPERVISOR_CLEANUP_INCOMPLETE = 126
POLL_INTERVAL_SECONDS = 0.05
ADOPTED_REAP_INTERVAL_SECONDS = 1.0
MAX_EXECUTABLE_BYTES = 512 * 1024 * 1024
MAX_MASK_BYTES = 2 * 1024 * 1024
IDENTITY_DISCOVERY_TIMEOUT_SECONDS = 5.0
PRIVATE_VIEW_IDENTITY_FIELDS = {
    "device": "st_dev",
    "inode": "st_ino",
    "mode": "st_mode",
    "size": "st_size",
    "mtime_ns": "st_mtime_ns",
    "ctime_ns": "st_ctime_ns",
}

_termination_signal: int | None = None
_child_state_changed = True


class SupervisorError(RuntimeError):
    """One process-containment failure safe to expose on stderr."""


def _open_verified_file(
    path: str,
    expected_digest: str,
    *,
    label: str,
    maximum_bytes: int,
) -> tuple[int, os.stat_result]:
    """Open and hash one exact regular inode for later descriptor-bound use."""

    executable = Path(path)
    if (
        not executable.is_absolute()
        or executable.resolve() != executable
        or not expected_digest.startswith("sha256:")
        or len(expected_digest) != 71
    ):
        raise SupervisorError(f"{label} identity is invalid")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(executable, flags)
    except OSError as exc:
        raise SupervisorError(f"cannot open the exact {label}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SupervisorError(f"{label} is not a regular file")
        digest = hashlib.sha256()
        observed_bytes = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            observed_bytes += len(chunk)
            if observed_bytes > maximum_bytes:
                raise SupervisorError(f"{label} exceeds the digest limit")
            digest.update(chunk)
        after = os.fstat(descriptor)
        identity_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(getattr(before, field) != getattr(after, field) for field in identity_fields):
            raise SupervisorError(f"{label} changed while being verified")
        actual_digest = "sha256:" + digest.hexdigest()
        if actual_digest != expected_digest:
            raise SupervisorError(f"{label} digest changed before use")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, after
    except BaseException:
        os.close(descriptor)
        raise


def _open_verified_executable(path: str, expected_digest: str) -> int:
    """Compatibility helper used by focused verifier tests."""

    descriptor, _ = _open_verified_file(
        path,
        expected_digest,
        label="Codex executable",
        maximum_bytes=MAX_EXECUTABLE_BYTES,
    )
    return descriptor


def _private_view_identity_matches(
    observed: os.stat_result,
    expected: object,
) -> bool:
    return isinstance(expected, dict) and set(expected) == set(
        PRIVATE_VIEW_IDENTITY_FIELDS
    ) and all(
        isinstance(expected[key], int)
        and expected[key] == getattr(observed, field)
        for key, field in PRIVATE_VIEW_IDENTITY_FIELDS.items()
    )


def _validated_private_directory_views(
    raw_views: list[str],
) -> tuple[dict[str, object], ...]:
    views: list[dict[str, object]] = []
    targets: set[Path] = set()
    for raw in raw_views:
        try:
            view = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SupervisorError("private directory view is invalid JSON") from exc
        if not isinstance(view, dict) or set(view) != {
            "target",
            "identity",
            "entries",
        }:
            raise SupervisorError("private directory view has an unsupported shape")
        target = Path(str(view["target"]))
        entries = view["entries"]
        if (
            not target.is_absolute()
            or target in targets
            or not isinstance(entries, list)
            or not isinstance(view["identity"], dict)
        ):
            raise SupervisorError("private directory view identity is invalid")
        targets.add(target)
        entry_targets: set[Path] = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {
                "source",
                "target",
                "kind",
                "identity",
            }:
                raise SupervisorError("private directory entry has an unsupported shape")
            source = Path(str(entry["source"]))
            entry_target = Path(str(entry["target"]))
            if (
                not source.is_absolute()
                or entry_target.parent != target
                or entry_target.name != source.name
                or entry_target in entry_targets
                or entry["kind"] not in {"file", "directory"}
                or not isinstance(entry["identity"], dict)
            ):
                raise SupervisorError("private directory entry identity is invalid")
            entry_targets.add(entry_target)
        views.append(view)
    if not views:
        raise SupervisorError("private directory views are absent")
    return tuple(
        sorted(views, key=lambda view: (len(Path(str(view["target"])).parts), str(view["target"])))
    )


def _launch_verified_command(
    command: list[str],
    expected_digest: str,
    *,
    mount_wrapper: str | None = None,
    mount_wrapper_digest: str | None = None,
    private_directory_views: tuple[dict[str, object], ...] = (),
    read_only_masks: tuple[tuple[str, str, str], ...] = (),
) -> tuple[subprocess.Popen[bytes], int | None]:
    """Execute the digest-verified open file, not a later pathname lookup."""

    descriptor, _ = _open_verified_file(
        command[0],
        expected_digest,
        label="Codex executable",
        maximum_bytes=MAX_EXECUTABLE_BYTES,
    )
    if mount_wrapper is None:
        try:
            process = subprocess.Popen(
                command,
                executable=f"/proc/self/fd/{descriptor}",
                pass_fds=(descriptor,),
            )
            return process, None
        except OSError as exc:
            raise SupervisorError("Codex launch failed") from exc
        finally:
            os.close(descriptor)
    if (
        mount_wrapper_digest is None
        or not private_directory_views
        or not read_only_masks
    ):
        os.close(descriptor)
        raise SupervisorError("mount wrapper configuration is incomplete")
    wrapper_descriptor, _ = _open_verified_file(
        mount_wrapper,
        mount_wrapper_digest,
        label="mount wrapper executable",
        maximum_bytes=MAX_EXECUTABLE_BYTES,
    )
    mask_descriptors: list[int] = []
    view_descriptors: list[int] = []
    gate_read_socket, gate_write_socket = socket.socketpair(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )
    gate_read_fd = gate_read_socket.detach()
    gate_write_fd = gate_write_socket.detach()
    try:
        wrapper_command = [
            mount_wrapper,
            "--die-with-parent",
            "--dev-bind",
            "/",
            "/",
            "--block-fd",
            str(gate_read_fd),
            # Keep the peer endpoint inside bwrap itself.  If the supervisor
            # dies or closes its duplicate before an explicit release byte,
            # the blocked endpoint therefore cannot observe EOF as success.
            "--sync-fd",
            str(gate_write_fd),
            "--ro-bind-fd",
            str(descriptor),
            command[0],
        ]
        view_targets: set[Path] = set()
        for view in private_directory_views:
            view_target = Path(str(view["target"]))
            try:
                view_stat = view_target.lstat()
            except OSError as exc:
                raise SupervisorError("private directory view became unavailable") from exc
            if (
                view_target.is_symlink()
                or not stat.S_ISDIR(view_stat.st_mode)
                or not _private_view_identity_matches(view_stat, view["identity"])
            ):
                raise SupervisorError("private directory view identity changed")
            view_targets.add(view_target)
            wrapper_command.extend(("--tmpfs", str(view_target)))
            entries = view["entries"]
            assert isinstance(entries, list)
            for entry in entries:
                assert isinstance(entry, dict)
                source = Path(str(entry["source"]))
                target = Path(str(entry["target"]))
                kind = str(entry["kind"])
                flags = os.O_RDONLY | os.O_CLOEXEC
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                if kind == "directory" and hasattr(os, "O_DIRECTORY"):
                    flags |= os.O_DIRECTORY
                try:
                    entry_descriptor = os.open(source, flags)
                except OSError as exc:
                    raise SupervisorError(
                        "cannot open a private directory view entry"
                    ) from exc
                view_descriptors.append(entry_descriptor)
                entry_stat = os.fstat(entry_descriptor)
                if (
                    (kind == "directory" and not stat.S_ISDIR(entry_stat.st_mode))
                    or (kind == "file" and not stat.S_ISREG(entry_stat.st_mode))
                    or not _private_view_identity_matches(
                        entry_stat,
                        entry["identity"],
                    )
                ):
                    raise SupervisorError("private directory view entry changed")
                wrapper_command.extend(
                    ("--ro-bind-fd", str(entry_descriptor), str(target))
                )
        for source, target, digest in read_only_masks:
            if (
                not Path(target).is_absolute()
                or Path(target).parent not in view_targets
            ):
                raise SupervisorError("mount mask target is not absolute")
            mask_descriptor, _ = _open_verified_file(
                source,
                digest,
                label="mount mask source",
                maximum_bytes=MAX_MASK_BYTES,
            )
            mask_descriptors.append(mask_descriptor)
            wrapper_command.extend(
                ("--ro-bind-data", str(mask_descriptor), target)
            )
        wrapper_command.extend(("--", *command))
        process = subprocess.Popen(
            wrapper_command,
            executable=f"/proc/self/fd/{wrapper_descriptor}",
            pass_fds=(
                descriptor,
                wrapper_descriptor,
                gate_read_fd,
                gate_write_fd,
                *view_descriptors,
                *mask_descriptors,
            ),
        )
        os.close(gate_read_fd)
        gate_read_fd = -1
        return process, gate_write_fd
    except OSError as exc:
        os.close(gate_write_fd)
        raise SupervisorError("Codex launch failed") from exc
    except SupervisorError:
        os.close(gate_write_fd)
        raise
    finally:
        os.close(descriptor)
        os.close(wrapper_descriptor)
        for mask_descriptor in mask_descriptors:
            os.close(mask_descriptor)
        for view_descriptor in view_descriptors:
            os.close(view_descriptor)
        if gate_read_fd >= 0:
            os.close(gate_read_fd)


def _release_launch_gate(gate_write_fd: int, *, parent_pid: int) -> None:
    """Release a mount-gated child only while the exact worker parent is alive."""

    if _termination_signal is not None or os.getppid() != parent_pid:
        raise SupervisorError("worker parent died before launch gate release")
    try:
        written = os.write(gate_write_fd, b"1")
        if written != 1:
            raise SupervisorError("mount wrapper launch gate write was incomplete")
    except OSError as exc:
        raise SupervisorError("mount wrapper launch gate failed") from exc
    os.close(gate_write_fd)


def _abort_gated_launch(
    process: subprocess.Popen[bytes],
    gate_write_fd: int | None,
    *,
    term_timeout_seconds: float,
    kill_timeout_seconds: float,
) -> bool:
    """Close a failed launch gate only after every descendant is gone.

    The wrapper also retains its peer endpoint through ``--sync-fd``.  Thus an
    abnormal supervisor exit cannot turn descriptor EOF into a release even if
    kernel cleanup cannot be confirmed within the bounded attempt.
    """

    cleanup_complete = _cleanup_descendants(
        process,
        term_timeout_seconds=term_timeout_seconds,
        kill_timeout_seconds=kill_timeout_seconds,
    )
    if cleanup_complete and gate_write_fd is not None:
        os.close(gate_write_fd)
    return cleanup_complete


@dataclass(frozen=True)
class ProcessIdentity:
    """The procfs identity needed to resist PID reuse during cleanup."""

    pid: int
    parent_pid: int
    state: str
    start_ticks: int
    depth: int = 0


def _request_termination(signum: int, _frame: object) -> None:
    global _termination_signal
    if _termination_signal is None:
        _termination_signal = signum


def _request_child_reap(_signum: int, _frame: object) -> None:
    global _child_state_changed
    _child_state_changed = True


def _fail(message: str, exit_code: int) -> NoReturn:
    print(f"external-codex-supervisor: {message}", file=sys.stderr, flush=True)
    raise SystemExit(exit_code)


def _prctl(option: int, argument: int) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    prctl.restype = ctypes.c_int
    if prctl(option, argument, 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise SupervisorError(os.strerror(error_number))


def _proc_identity(pid: int) -> ProcessIdentity | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = raw.rfind(")")
        if close < 0:
            return None
        fields = raw[close + 2 :].split()
        return ProcessIdentity(
            pid=pid,
            state=fields[0],
            parent_pid=int(fields[1]),
            start_ticks=int(fields[19]),
        )
    except (OSError, IndexError, ValueError):
        return None


def _process_table() -> dict[int, ProcessIdentity]:
    try:
        entries = tuple(Path("/proc").iterdir())
    except OSError as exc:
        raise SupervisorError("cannot enumerate Linux procfs") from exc
    table: dict[int, ProcessIdentity] = {}
    for entry in entries:
        if not entry.name.isdigit():
            continue
        identity = _proc_identity(int(entry.name))
        if identity is not None:
            table[identity.pid] = identity
    return table


def _descendants(supervisor_pid: int) -> dict[int, ProcessIdentity]:
    table = _process_table()
    depths = {supervisor_pid: 0}
    changed = True
    while changed:
        changed = False
        for pid, identity in table.items():
            if pid in depths or identity.parent_pid not in depths:
                continue
            depths[pid] = depths[identity.parent_pid] + 1
            changed = True
    return {
        pid: ProcessIdentity(
            pid=identity.pid,
            parent_pid=identity.parent_pid,
            state=identity.state,
            start_ticks=identity.start_ticks,
            depth=depths[pid],
        )
        for pid, identity in table.items()
        if pid in depths and pid != supervisor_pid
    }


def _identity_matches(identity: ProcessIdentity) -> bool:
    current = _proc_identity(identity.pid)
    return (
        current is not None
        and current.start_ticks == identity.start_ticks
        and current.state != "Z"
    )


def _signal_descendants(
    descendants: dict[int, ProcessIdentity],
    signum: int,
) -> bool:
    successful = True
    for identity in sorted(
        descendants.values(),
        key=lambda item: (item.depth, item.pid),
        reverse=True,
    ):
        if not _identity_matches(identity):
            continue
        try:
            os.kill(identity.pid, signum)
        except ProcessLookupError:
            continue
        except PermissionError:
            successful = False
    return successful


def _reap_adopted_children(supervisor_pid: int, codex_pid: int | None) -> None:
    if supervisor_pid != os.getpid():
        raise SupervisorError("adopted-child reap identity differs from supervisor")
    while True:
        try:
            child = os.waitid(
                os.P_ALL,
                0,
                os.WEXITED | os.WNOHANG | os.WNOWAIT,
            )
        except ChildProcessError:
            return
        if child is None or child.si_pid == 0 or child.si_pid == codex_pid:
            return
        try:
            os.waitpid(child.si_pid, os.WNOHANG)
        except ChildProcessError:
            continue


def _consume_child_state_change() -> bool:
    global _child_state_changed
    changed = _child_state_changed
    _child_state_changed = False
    return changed


def _drain_signal_pipe(read_fd: int) -> None:
    while True:
        try:
            if not os.read(read_fd, 4096):
                return
        except BlockingIOError:
            return


def _wait_for_signal_or_timeout(read_fd: int, timeout_seconds: float) -> None:
    readable, _, _ = select.select([read_fd], [], [], timeout_seconds)
    if readable:
        _drain_signal_pipe(read_fd)


def _wait_for_codex(
    process: subprocess.Popen[bytes],
    *,
    signal_read_fd: int,
) -> int | None:
    """Wait on signal notifications with a bounded procfs-reap fallback."""

    next_periodic_reap = time.monotonic()
    while _termination_signal is None:
        codex_return_code = process.poll()
        if codex_return_code is not None:
            return codex_return_code
        now = time.monotonic()
        if _consume_child_state_change() or now >= next_periodic_reap:
            _reap_adopted_children(os.getpid(), process.pid)
            next_periodic_reap = now + ADOPTED_REAP_INTERVAL_SECONDS
        _wait_for_signal_or_timeout(
            signal_read_fd,
            max(0.0, next_periodic_reap - time.monotonic()),
        )
    return None


def _wait_for_cleanup(
    process: subprocess.Popen[bytes],
    *,
    deadline: float,
    signum_for_new_descendants: int,
) -> bool:
    supervisor_pid = os.getpid()
    while True:
        process.poll()
        _reap_adopted_children(
            supervisor_pid,
            process.pid if process.returncode is None else None,
        )
        descendants = _descendants(supervisor_pid)
        live = {
            pid: identity
            for pid, identity in descendants.items()
            if identity.state != "Z"
        }
        if not live and process.poll() is not None:
            _reap_adopted_children(supervisor_pid, None)
            return not _descendants(supervisor_pid)
        if live and not _signal_descendants(live, signum_for_new_descendants):
            return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_INTERVAL_SECONDS)


def _cleanup_descendants(
    process: subprocess.Popen[bytes],
    *,
    term_timeout_seconds: float,
    kill_timeout_seconds: float,
) -> bool:
    try:
        descendants = _descendants(os.getpid())
        term_signals_ok = _signal_descendants(descendants, signal.SIGTERM)
        if term_signals_ok and _wait_for_cleanup(
            process,
            deadline=time.monotonic() + term_timeout_seconds,
            signum_for_new_descendants=signal.SIGTERM,
        ):
            return True
        descendants = _descendants(os.getpid())
        kill_signals_ok = _signal_descendants(descendants, signal.SIGKILL)
        return kill_signals_ok and _wait_for_cleanup(
            process,
            deadline=time.monotonic() + kill_timeout_seconds,
            signum_for_new_descendants=signal.SIGKILL,
        )
    except SupervisorError:
        return False


def _bounded_timeout(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be numeric") from exc
    if parsed < 0 or parsed > 60:
        raise argparse.ArgumentTypeError("timeout must be between 0 and 60 seconds")
    return parsed


def _write_process_identity_receipt(
    path: Path,
    process: subprocess.Popen[bytes],
    *,
    gated_mount_child: bool = False,
) -> None:
    """Publish exact supervisor, launcher, and Codex identities."""

    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise SupervisorError("process identity receipt path is not fresh and absolute")
    supervisor = _proc_identity(os.getpid())
    launcher = _proc_identity(process.pid)
    if (
        supervisor is None
        or launcher is None
        or launcher.parent_pid != supervisor.pid
        or supervisor.state == "Z"
        or launcher.state == "Z"
    ):
        raise SupervisorError("cannot bind exact supervisor and launcher identities")
    codex: ProcessIdentity | None = launcher if not gated_mount_child else None
    deadline = time.monotonic() + IDENTITY_DISCOVERY_TIMEOUT_SECONDS
    while codex is None:
        descendants = _descendants(supervisor.pid)
        matches = [
            identity
            for identity in descendants.values()
            if identity.parent_pid == launcher.pid and identity.state != "Z"
        ]
        if len(matches) == 1:
            codex = matches[0]
            break
        if len(matches) > 1:
            raise SupervisorError("mount launcher created multiple gated command children")
        if process.poll() is not None or time.monotonic() >= deadline:
            raise SupervisorError("cannot identify the exact Codex descendant")
        time.sleep(0.01)
    payload = {
        "schema_version": "abyss_stack_external_codex_process_identity_v2",
        "supervisor_pid": supervisor.pid,
        "supervisor_start_ticks": supervisor.start_ticks,
        "launcher_pid": launcher.pid,
        "launcher_start_ticks": launcher.start_ticks,
        "codex_pid": codex.pid,
        "codex_start_ticks": codex.start_ticks,
    }
    encoded = (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(temporary, flags, 0o400)
        try:
            remaining = memoryview(encoded)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("short process identity receipt write")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        directory_flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        directory_descriptor = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise SupervisorError("cannot publish process identity receipt") from exc


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument(
        "--term-timeout-seconds",
        type=_bounded_timeout,
        required=True,
    )
    parser.add_argument(
        "--kill-timeout-seconds",
        type=_bounded_timeout,
        required=True,
    )
    parser.add_argument("--identity-file", type=Path)
    parser.add_argument("--executable-digest", required=True)
    parser.add_argument("--mount-wrapper")
    parser.add_argument("--mount-wrapper-digest")
    parser.add_argument(
        "--private-directory-view",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--read-only-mask",
        nargs=3,
        action="append",
        default=[],
        metavar=("SOURCE", "TARGET", "DIGEST"),
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args(argv)
    if arguments.command[:1] == ["--"]:
        arguments.command = arguments.command[1:]
    try:
        arguments.private_directory_views = _validated_private_directory_views(
            arguments.private_directory_view
        ) if arguments.mount_wrapper is not None else ()
    except SupervisorError as exc:
        parser.error(str(exc))
    if (
        arguments.parent_pid <= 1
        or not arguments.command
        or (
            arguments.identity_file is not None
            and not arguments.identity_file.is_absolute()
        )
        or ((arguments.mount_wrapper is None) != (arguments.mount_wrapper_digest is None))
        or (arguments.read_only_mask and arguments.mount_wrapper is None)
        or (arguments.private_directory_view and arguments.mount_wrapper is None)
        or (
            arguments.mount_wrapper is not None
            and not arguments.private_directory_views
        )
        or any(
            not Path(source).is_absolute() or not Path(target).is_absolute()
            for source, target, _digest in arguments.read_only_mask
        )
    ):
        parser.error("an exact parent PID and command are required")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = _arguments(sys.argv[1:] if argv is None else argv)
    try:
        signal_read_fd, signal_write_fd = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError as exc:
        _fail(f"signal wakeup pipe setup failed: {exc}", SUPERVISOR_SETUP_FAILED)
    previous_wakeup_fd = -1
    wakeup_installed = False
    try:
        previous_wakeup_fd = signal.set_wakeup_fd(
            signal_write_fd,
            warn_on_full_buffer=False,
        )
        wakeup_installed = True
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(signum, _request_termination)
        signal.signal(signal.SIGCHLD, _request_child_reap)
        if os.getppid() != arguments.parent_pid:
            _fail("worker parent identity differs before setup", SUPERVISOR_SETUP_FAILED)
        try:
            _prctl(PR_SET_CHILD_SUBREAPER, 1)
            _prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
        except SupervisorError as exc:
            _fail(f"Linux prctl setup failed: {exc}", SUPERVISOR_SETUP_FAILED)
        if os.getppid() != arguments.parent_pid or _termination_signal is not None:
            _fail("worker parent died during setup", SUPERVISOR_SETUP_FAILED)
        try:
            process, gate_write_fd = _launch_verified_command(
                arguments.command,
                arguments.executable_digest,
                mount_wrapper=arguments.mount_wrapper,
                mount_wrapper_digest=arguments.mount_wrapper_digest,
                private_directory_views=arguments.private_directory_views,
                read_only_masks=tuple(tuple(item) for item in arguments.read_only_mask),
            )
        except SupervisorError as exc:
            _fail(str(exc), SUPERVISOR_SETUP_FAILED)
        if arguments.identity_file is not None:
            try:
                _write_process_identity_receipt(
                    arguments.identity_file,
                    process,
                    gated_mount_child=gate_write_fd is not None,
                )
            except SupervisorError as exc:
                if not _abort_gated_launch(
                    process,
                    gate_write_fd,
                    term_timeout_seconds=arguments.term_timeout_seconds,
                    kill_timeout_seconds=arguments.kill_timeout_seconds,
                ):
                    print(
                        "external-codex-supervisor: descendant cleanup remained "
                        "incomplete while aborting identity publication",
                        file=sys.stderr,
                        flush=True,
                    )
                    return SUPERVISOR_CLEANUP_INCOMPLETE
                _fail(str(exc), SUPERVISOR_SETUP_FAILED)
        if gate_write_fd is not None:
            try:
                _release_launch_gate(
                    gate_write_fd,
                    parent_pid=arguments.parent_pid,
                )
            except SupervisorError as exc:
                if not _abort_gated_launch(
                    process,
                    gate_write_fd,
                    term_timeout_seconds=arguments.term_timeout_seconds,
                    kill_timeout_seconds=arguments.kill_timeout_seconds,
                ):
                    print(
                        "external-codex-supervisor: descendant cleanup remained "
                        "incomplete while aborting launch gate",
                        file=sys.stderr,
                        flush=True,
                    )
                    return SUPERVISOR_CLEANUP_INCOMPLETE
                _fail(str(exc), SUPERVISOR_SETUP_FAILED)

        codex_return_code = _wait_for_codex(
            process,
            signal_read_fd=signal_read_fd,
        )
        termination_signal = _termination_signal
        if not _cleanup_descendants(
            process,
            term_timeout_seconds=arguments.term_timeout_seconds,
            kill_timeout_seconds=arguments.kill_timeout_seconds,
        ):
            print(
                "external-codex-supervisor: descendant cleanup remained incomplete",
                file=sys.stderr,
                flush=True,
            )
            return SUPERVISOR_CLEANUP_INCOMPLETE
        if termination_signal is not None:
            return 128 + termination_signal
        assert codex_return_code is not None
        return codex_return_code
    finally:
        if wakeup_installed:
            signal.set_wakeup_fd(previous_wakeup_fd)
        os.close(signal_read_fd)
        os.close(signal_write_fd)


if __name__ == "__main__":
    raise SystemExit(main())
