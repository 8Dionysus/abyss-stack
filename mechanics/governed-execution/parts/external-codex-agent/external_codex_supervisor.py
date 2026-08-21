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
import fcntl
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
from typing import Callable, NoReturn


PR_SET_PDEATHSIG = 1
PR_SET_CHILD_SUBREAPER = 36
SUPERVISOR_SETUP_FAILED = 125
SUPERVISOR_CLEANUP_INCOMPLETE = 126
POLL_INTERVAL_SECONDS = 0.05
ADOPTED_REAP_INTERVAL_SECONDS = 1.0
MAX_EXECUTABLE_BYTES = 512 * 1024 * 1024
MAX_MASK_BYTES = 2 * 1024 * 1024
# The admitted package contains large immutable helper binaries (notably the
# code-mode host and ripgrep).  Keep the ordinary actor-mask bound narrow while
# giving the profile-pinned package members their own bounded snapshot limit.
MAX_RUNTIME_PACKAGE_MEMBER_BYTES = 128 * 1024 * 1024
MAX_MOUNT_LAUNCHER_BYTES = 2 * 1024 * 1024
IDENTITY_DISCOVERY_TIMEOUT_SECONDS = 5.0
MOUNT_SETUP_TIMEOUT_SECONDS = 5.0
MOUNT_LAUNCHER_PATH = Path(__file__).resolve().with_name(
    "external_codex_mount_launcher.py"
)
ACTOR_WORKSPACE_COORDINATE = Path("/tmp/aoa-external-actor-workspace")
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


def _sealed_verified_file_snapshot(
    path: str,
    expected_digest: str,
    *,
    label: str,
    maximum_bytes: int,
) -> tuple[int, os.stat_result]:
    """Copy verified bytes into a sealed memfd before returning authority."""

    source = Path(path)
    if (
        not source.is_absolute()
        or source.resolve() != source
        or not expected_digest.startswith("sha256:")
        or len(expected_digest) != 71
    ):
        raise SupervisorError(f"{label} identity is invalid")
    source_descriptor = snapshot_descriptor = -1
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        source_descriptor = os.open(source, flags)
        before = os.fstat(source_descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SupervisorError(f"{label} is not a regular file")
        snapshot_descriptor = os.memfd_create(
            "external-codex-mask-snapshot",
            os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
        )
        digest = hashlib.sha256()
        observed_bytes = 0
        while True:
            chunk = os.read(source_descriptor, 1024 * 1024)
            if not chunk:
                break
            observed_bytes += len(chunk)
            if observed_bytes > maximum_bytes:
                raise SupervisorError(f"{label} exceeds the digest limit")
            digest.update(chunk)
            offset = 0
            while offset < len(chunk):
                written = os.write(snapshot_descriptor, chunk[offset:])
                if written <= 0:
                    raise OSError("mount mask snapshot write was incomplete")
                offset += written
        after = os.fstat(source_descriptor)
        identity_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(getattr(before, field) != getattr(after, field) for field in identity_fields):
            raise SupervisorError(f"{label} changed while being snapshotted")
        if observed_bytes != after.st_size:
            raise SupervisorError(f"{label} size changed while being snapshotted")
        actual_digest = "sha256:" + digest.hexdigest()
        if actual_digest != expected_digest:
            raise SupervisorError(f"{label} digest changed before use")
        os.lseek(snapshot_descriptor, 0, os.SEEK_SET)
        fcntl.fcntl(
            snapshot_descriptor,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE,
        )
        result = snapshot_descriptor
        snapshot_descriptor = -1
        return result, after
    except OSError as exc:
        raise SupervisorError(f"cannot snapshot the exact {label}") from exc
    finally:
        if source_descriptor >= 0:
            os.close(source_descriptor)
        if snapshot_descriptor >= 0:
            os.close(snapshot_descriptor)


def _path_digest(path: Path, *, maximum_bytes: int) -> str:
    try:
        observed = path.stat()
        if not stat.S_ISREG(observed.st_mode) or observed.st_size > maximum_bytes:
            raise SupervisorError("verified launcher input is not one bounded file")
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise SupervisorError("cannot digest one verified launcher input") from exc


def _sealed_payload_descriptor(payload: dict[str, object]) -> int:
    raw = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(raw) > MAX_MASK_BYTES:
        raise SupervisorError("mount launcher payload exceeds its bound")
    try:
        descriptor = os.memfd_create(
            "external-codex-mount-launch",
            os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
        )
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise OSError("mount payload write was incomplete")
            offset += written
        os.lseek(descriptor, 0, os.SEEK_SET)
        fcntl.fcntl(
            descriptor,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE,
        )
        return descriptor
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise SupervisorError("cannot seal the mount launcher payload") from exc


def _await_mount_setup(
    process: subprocess.Popen[bytes],
    setup_fd: int,
    *,
    setup_callback: Callable[[], None] | None,
) -> None:
    try:
        readable, _, _ = select.select(
            [setup_fd],
            [],
            [],
            MOUNT_SETUP_TIMEOUT_SECONDS,
        )
        if not readable or os.read(setup_fd, 1) != b"R":
            raise SupervisorError("private mount launcher did not become ready")
        if setup_callback is not None:
            setup_callback()
        if os.write(setup_fd, b"1") != 1:
            raise SupervisorError("private mount launcher release was incomplete")
        readable, _, _ = select.select(
            [setup_fd],
            [],
            [],
            MOUNT_SETUP_TIMEOUT_SECONDS,
        )
        if not readable or os.read(setup_fd, 1) != b"A":
            raise SupervisorError("private mount launcher did not attach exact views")
    except BaseException as exc:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        if isinstance(exc, SupervisorError):
            raise
        if isinstance(exc, (OSError, RuntimeError)):
            raise SupervisorError("private mount launcher setup failed") from exc
        raise


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
            if not isinstance(entry, dict):
                raise SupervisorError("private directory entry has an unsupported shape")
            kind = entry.get("kind")
            expected_keys = (
                {"source", "target", "kind", "identity", "link_target"}
                if kind == "symlink"
                else {"source", "target", "kind", "identity"}
            )
            source_value = entry.get("source")
            target_value = entry.get("target")
            identity = entry.get("identity")
            if (
                set(entry) != expected_keys
                or not isinstance(source_value, str)
                or not isinstance(target_value, str)
                or not isinstance(identity, dict)
                or not source_value.startswith("/")
                or not target_value.startswith("/")
                or kind not in {"file", "directory", "symlink"}
                or (
                    kind == "symlink"
                    and (
                        not isinstance(entry.get("link_target"), str)
                        or not entry["link_target"]
                    )
                )
            ):
                raise SupervisorError("private directory entry identity is invalid")
            source = Path(source_value)
            entry_target = Path(target_value)
            if (
                entry_target.parent != target
                or entry_target.name != source.name
                or entry_target in entry_targets
            ):
                raise SupervisorError("private directory entry identity is invalid")
            entry_targets.add(entry_target)
        views.append(view)
    if not views:
        raise SupervisorError("private directory views are absent")
    return tuple(
        sorted(
            views,
            key=lambda view: (
                len(Path(str(view["target"])).parts),
                str(view["target"]),
            ),
        )
    )


def _launch_verified_command(
    command: list[str],
    expected_digest: str,
    *,
    mount_wrapper: str | None = None,
    mount_wrapper_digest: str | None = None,
    mount_launcher_digest: str | None = None,
    private_directory_views: tuple[dict[str, object], ...] = (),
    read_only_masks: tuple[tuple[str, str, str], ...] = (),
    runtime_package_mask: bool = False,
    mount_setup_callback: Callable[[], None] | None = None,
    workspace_fd: int | None = None,
    workspace_coordinate: str | None = None,
) -> tuple[subprocess.Popen[bytes], int | None]:
    """Execute the digest-verified open file, not a later pathname lookup."""

    descriptor, executable_stat = _sealed_verified_file_snapshot(
        command[0],
        expected_digest,
        label="Codex executable",
        maximum_bytes=MAX_EXECUTABLE_BYTES,
    )
    if mount_wrapper is None and workspace_fd is None:
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
    has_private_views = bool(private_directory_views or read_only_masks)
    if (
        mount_wrapper_digest is None
        or mount_launcher_digest is None
        or (workspace_fd is None and not has_private_views)
        or bool(private_directory_views) != bool(read_only_masks)
    ):
        os.close(descriptor)
        raise SupervisorError("mount wrapper configuration is incomplete")
    if workspace_fd is not None:
        try:
            workspace_stat = os.fstat(workspace_fd)
        except OSError as exc:
            os.close(descriptor)
            raise SupervisorError("actor workspace descriptor is unavailable") from exc
        if (
            not stat.S_ISDIR(workspace_stat.st_mode)
            or workspace_coordinate != str(ACTOR_WORKSPACE_COORDINATE)
        ):
            os.close(descriptor)
            raise SupervisorError("actor workspace descriptor binding is invalid")
    wrapper_descriptor, _ = _open_verified_file(
        mount_wrapper,
        mount_wrapper_digest,
        label="mount wrapper executable",
        maximum_bytes=MAX_EXECUTABLE_BYTES,
    )
    launcher_descriptor, _ = _open_verified_file(
        str(MOUNT_LAUNCHER_PATH),
        mount_launcher_digest,
        label="mount namespace launcher",
        maximum_bytes=MAX_MOUNT_LAUNCHER_BYTES,
    )
    python_executable = Path(sys.executable).resolve()
    python_descriptor, _ = _open_verified_file(
        str(python_executable),
        _path_digest(python_executable, maximum_bytes=MAX_EXECUTABLE_BYTES),
        label="mount launcher Python executable",
        maximum_bytes=MAX_EXECUTABLE_BYTES,
    )
    mask_descriptors: list[int] = []
    view_descriptors: list[int] = []
    mount_descriptor = -1
    payload_descriptor = -1
    setup_parent_fd = -1
    setup_child_fd = -1
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
        ]
        if workspace_fd is not None:
            wrapper_command.extend(
                (
                    "--tmpfs",
                    "/tmp",
                    "--dir",
                    str(ACTOR_WORKSPACE_COORDINATE),
                    "--bind-fd",
                    str(workspace_fd),
                    str(ACTOR_WORKSPACE_COORDINATE),
                    "--chdir",
                    str(ACTOR_WORKSPACE_COORDINATE),
                )
            )
        view_targets: set[Path] = set()
        launcher_views: list[dict[str, object]] = []
        for view in private_directory_views:
            view_target = Path(str(view["target"]))
            view_targets.add(view_target)
            launcher_view = {
                "target": str(view_target),
                "identity": view["identity"],
                "attachments": [],
            }
            launcher_views.append(launcher_view)
            launcher_attachments = launcher_view["attachments"]
            assert isinstance(launcher_attachments, list)
            entries = view["entries"]
            assert isinstance(entries, list)
            for entry in entries:
                assert isinstance(entry, dict)
                source = Path(str(entry["source"]))
                target = Path(str(entry["target"]))
                kind = str(entry["kind"])
                flags = os.O_PATH | os.O_CLOEXEC
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
                    or (kind == "symlink" and not stat.S_ISLNK(entry_stat.st_mode))
                    or not _private_view_identity_matches(entry_stat, entry["identity"])
                    or (
                        kind == "symlink"
                        and os.readlink(source) != entry["link_target"]
                    )
                ):
                    raise SupervisorError("private directory view entry changed")
                launcher_attachment = {
                    "name": target.name,
                    "kind": kind,
                    "source": str(source),
                    "identity": entry["identity"],
                }
                if kind == "symlink":
                    launcher_attachment["link_target"] = entry["link_target"]
                launcher_attachments.append(launcher_attachment)
        command_target = Path(command[0])
        command_view = next(
            (
                item
                for item in launcher_views
                if item["target"] == str(command_target.parent)
            ),
            None,
        )
        if runtime_package_mask and command_view is not None:
            command_attachments = command_view["attachments"]
            assert isinstance(command_attachments, list)
            command_attachments[:] = [
                item
                for item in command_attachments
                if item.get("name") != command_target.name
            ]
            command_attachments.append(
                {
                    "name": command_target.name,
                    "kind": "sealed_file",
                    "snapshot_fd": descriptor,
                    "size": executable_stat.st_size,
                    "digest": expected_digest,
                    "mode": executable_stat.st_mode & 0o7777,
                }
            )
        else:
            mount_descriptor, _ = _open_verified_file(
                command[0],
                expected_digest,
                label="Codex mount executable",
                maximum_bytes=MAX_EXECUTABLE_BYTES,
            )
            wrapper_command.extend(
                ("--ro-bind-fd", str(mount_descriptor), command[0])
            )
        for source, target, digest in read_only_masks:
            if (
                not Path(target).is_absolute()
                or Path(target).parent not in view_targets
            ):
                raise SupervisorError("mount mask target is not absolute")
            if runtime_package_mask and Path(source) == Path(command[0]):
                verified_mask_descriptor = descriptor
                verified_mask_stat = executable_stat
            else:
                verified_mask_descriptor, verified_mask_stat = (
                    _sealed_verified_file_snapshot(
                        source,
                        digest,
                        label="mount mask source",
                        maximum_bytes=(
                            MAX_RUNTIME_PACKAGE_MEMBER_BYTES
                            if runtime_package_mask
                            else MAX_MASK_BYTES
                        ),
                    )
                )
                mask_descriptors.append(verified_mask_descriptor)
            mask_descriptor = verified_mask_descriptor
            launcher_view = next(
                item
                for item in launcher_views
                if item["target"] == str(Path(target).parent)
            )
            launcher_attachments = launcher_view["attachments"]
            assert isinstance(launcher_attachments, list)
            launcher_attachments.append(
                {
                    "name": Path(target).name,
                    "kind": "sealed_file",
                    "snapshot_fd": mask_descriptor,
                    "size": verified_mask_stat.st_size,
                    "digest": digest,
                    "mode": verified_mask_stat.st_mode & 0o7777,
                }
            )
        wrapper_command.extend(("--", *command))
        payload_descriptor = _sealed_payload_descriptor(
            {
                "schema_version": "abyss_stack_external_codex_mount_launcher_v1",
                "mount_wrapper_fd": wrapper_descriptor,
                "wrapper_argv": wrapper_command,
                "views": launcher_views,
            }
        )
        setup_parent_socket, setup_child_socket = socket.socketpair(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )
        setup_parent_fd = setup_parent_socket.detach()
        setup_child_fd = setup_child_socket.detach()
        process = subprocess.Popen(
            [
                str(python_executable),
                "-I",
                "-B",
                "-S",
                f"/proc/self/fd/{launcher_descriptor}",
                "--payload-fd",
                str(payload_descriptor),
                "--setup-fd",
                str(setup_child_fd),
            ],
            executable=f"/proc/self/fd/{python_descriptor}",
            pass_fds=(
                descriptor,
                wrapper_descriptor,
                launcher_descriptor,
                python_descriptor,
                payload_descriptor,
                setup_child_fd,
                gate_read_fd,
                gate_write_fd,
                *mask_descriptors,
                *((mount_descriptor,) if mount_descriptor >= 0 else ()),
                *((workspace_fd,) if workspace_fd is not None else ()),
            ),
        )
        os.close(setup_child_fd)
        setup_child_fd = -1
        _await_mount_setup(
            process,
            setup_parent_fd,
            setup_callback=mount_setup_callback,
        )
        os.close(setup_parent_fd)
        setup_parent_fd = -1
        os.close(gate_read_fd)
        gate_read_fd = -1
        return process, gate_write_fd
    except OSError as exc:
        if gate_write_fd >= 0:
            os.close(gate_write_fd)
            gate_write_fd = -1
        raise SupervisorError("Codex launch failed") from exc
    except SupervisorError:
        if gate_write_fd >= 0:
            os.close(gate_write_fd)
            gate_write_fd = -1
        raise
    finally:
        os.close(descriptor)
        if mount_descriptor >= 0:
            os.close(mount_descriptor)
        os.close(wrapper_descriptor)
        os.close(launcher_descriptor)
        os.close(python_descriptor)
        if payload_descriptor >= 0:
            os.close(payload_descriptor)
        if setup_parent_fd >= 0:
            os.close(setup_parent_fd)
        if setup_child_fd >= 0:
            os.close(setup_child_fd)
        for mask_descriptor in mask_descriptors:
            os.close(mask_descriptor)
        for view_descriptor in view_descriptors:
            os.close(view_descriptor)
        if workspace_fd is not None:
            os.close(workspace_fd)
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
    parser.add_argument("--mount-launcher-digest")
    parser.add_argument("--runtime-package-mask", action="store_true")
    parser.add_argument("--workspace-fd", type=int)
    parser.add_argument("--workspace-coordinate")
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
        ) if (
            arguments.mount_wrapper is not None
            and arguments.private_directory_view
        ) else ()
    except SupervisorError as exc:
        parser.error(str(exc))
    if (
        arguments.parent_pid <= 1
        or not arguments.command
        or (
            arguments.identity_file is not None
            and not arguments.identity_file.is_absolute()
        )
        or sum(
            value is None
            for value in (
                arguments.mount_wrapper,
                arguments.mount_wrapper_digest,
                arguments.mount_launcher_digest,
            )
        )
        not in {0, 3}
        or (arguments.read_only_mask and arguments.mount_wrapper is None)
        or (
            arguments.runtime_package_mask
            and (arguments.mount_wrapper is None or not arguments.read_only_mask)
        )
        or (arguments.private_directory_view and arguments.mount_wrapper is None)
        or (
            arguments.mount_wrapper is not None
            and not arguments.private_directory_views
            and arguments.workspace_fd is None
        )
        or ((arguments.workspace_fd is None) != (arguments.workspace_coordinate is None))
        or (
            arguments.workspace_fd is not None
            and (
                arguments.workspace_fd < 3
                or arguments.workspace_coordinate != str(ACTOR_WORKSPACE_COORDINATE)
                or arguments.mount_wrapper is None
            )
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
                mount_launcher_digest=arguments.mount_launcher_digest,
                private_directory_views=arguments.private_directory_views,
                read_only_masks=tuple(tuple(item) for item in arguments.read_only_mask),
                runtime_package_mask=arguments.runtime_package_mask,
                workspace_fd=arguments.workspace_fd,
                workspace_coordinate=arguments.workspace_coordinate,
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
