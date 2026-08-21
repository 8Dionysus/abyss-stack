#!/usr/bin/env python3
"""Enter a private mount namespace and attach views to verified directory fds."""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import NoReturn


PAYLOAD_SCHEMA = "abyss_stack_external_codex_mount_launcher_v1"
RUNTIME_PACKAGE_EXECUTION_ROOT = Path(
    "/var/tmp/aoa-external-actor-runtime-package"
)
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
SETUP_READY = b"R"
SETUP_RELEASE = b"1"
SETUP_ATTACHED = b"A"
AT_FDCWD = -100
FSOPEN_CLOEXEC = 0x00000001
FSCONFIG_CMD_CREATE = 6
FSMOUNT_CLOEXEC = 0x00000001
AT_EMPTY_PATH = 0x00001000
AT_RECURSIVE = 0x00008000
OPEN_TREE_CLONE = 0x00000001
OPEN_TREE_CLOEXEC = os.O_CLOEXEC
MOVE_MOUNT_F_EMPTY_PATH = 0x00000004
MOVE_MOUNT_T_EMPTY_PATH = 0x00000040
MOUNT_ATTR_RDONLY = 0x00000001
MS_REC = 16384
MS_PRIVATE = 1 << 18
PR_CAPBSET_DROP = 24
PR_SET_NO_NEW_PRIVS = 38
PR_CAP_AMBIENT = 47
PR_CAP_AMBIENT_CLEAR_ALL = 4
LINUX_CAPABILITY_VERSION_3 = 0x20080522
SYS_OPEN_TREE = 428
SYS_MOVE_MOUNT = 429
SYS_FSOPEN = 430
SYS_FSCONFIG = 431
SYS_FSMOUNT = 432
SYS_MOUNT_SETATTR = 442
SYS_UNSHARE = 272
CLONE_NEWNS = 0x00020000
CLONE_NEWUSER = 0x10000000
IDENTITY_FIELDS = {
    "device": "st_dev",
    "inode": "st_ino",
    "mode": "st_mode",
    "size": "st_size",
    "mtime_ns": "st_mtime_ns",
    "ctime_ns": "st_ctime_ns",
}
REQUIRED_MEMFD_SEALS = (
    fcntl.F_SEAL_SEAL
    | fcntl.F_SEAL_SHRINK
    | fcntl.F_SEAL_GROW
    | fcntl.F_SEAL_WRITE
)


class MountLauncherError(RuntimeError):
    """One fail-closed namespace-launch error safe to expose on stderr."""


class _CapabilityHeader(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]


class _CapabilityData(ctypes.Structure):
    _fields_ = [
        ("effective", ctypes.c_uint32),
        ("permitted", ctypes.c_uint32),
        ("inheritable", ctypes.c_uint32),
    ]


class _MountAttr(ctypes.Structure):
    _fields_ = [
        ("attr_set", ctypes.c_uint64),
        ("attr_clr", ctypes.c_uint64),
        ("propagation", ctypes.c_uint64),
        ("userns_fd", ctypes.c_uint64),
    ]


def _fail(message: str) -> NoReturn:
    print(f"external-codex-mount-launcher: {message}", file=sys.stderr, flush=True)
    raise SystemExit(125)


def _read_payload(descriptor: int) -> dict[str, object]:
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode) or observed.st_size > MAX_PAYLOAD_BYTES:
            raise MountLauncherError("mount payload is not one bounded regular file")
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = os.read(descriptor, MAX_PAYLOAD_BYTES + 1)
        if len(raw) != observed.st_size or len(raw) > MAX_PAYLOAD_BYTES:
            raise MountLauncherError("mount payload changed while being read")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MountLauncherError("mount payload is unavailable or invalid") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "mount_wrapper_fd", "wrapper_argv", "views"}
        or payload.get("schema_version") != PAYLOAD_SCHEMA
        or not isinstance(payload.get("mount_wrapper_fd"), int)
        or not isinstance(payload.get("wrapper_argv"), list)
        or not payload["wrapper_argv"]
        or any(not isinstance(value, str) or not value for value in payload["wrapper_argv"])
        or not isinstance(payload.get("views"), list)
    ):
        raise MountLauncherError("mount payload has an unsupported shape")
    return payload


def _write_user_namespace_maps(libc: ctypes.CDLL) -> None:
    uid = os.getuid()
    gid = os.getgid()
    try:
        _syscall(libc, SYS_UNSHARE, CLONE_NEWUSER)
        Path("/proc/self/setgroups").write_text("deny", encoding="ascii")
        Path("/proc/self/uid_map").write_text(f"{uid} {uid} 1", encoding="ascii")
        Path("/proc/self/gid_map").write_text(f"{gid} {gid} 1", encoding="ascii")
        _syscall(libc, SYS_UNSHARE, CLONE_NEWNS)
    except OSError as exc:
        raise MountLauncherError("cannot enter the private user and mount namespaces") from exc


def _syscall(libc: ctypes.CDLL, number: int, *arguments: object) -> int:
    result = int(libc.syscall(number, *arguments))
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return result


def _make_mounts_private(libc: ctypes.CDLL) -> None:
    if libc.mount(None, b"/", None, MS_REC | MS_PRIVATE, None) != 0:
        error = ctypes.get_errno()
        raise MountLauncherError("cannot make the cloned mount tree private") from OSError(
            error, os.strerror(error)
        )


def _open_view_targets(views: object) -> list[int]:
    assert isinstance(views, list)
    descriptors: list[int] = []
    try:
        for view in views:
            if not isinstance(view, dict) or set(view) not in (
                {"target", "identity", "attachments"},
                {"target", "identity", "attachments", "materialized"},
            ):
                raise MountLauncherError("private view target has an unsupported shape")
            target = Path(str(view["target"]))
            identity = view["identity"]
            attachments = view["attachments"]
            materialized = view.get("materialized", False)
            if (
                not target.is_absolute()
                or not isinstance(identity, dict)
                or set(identity) != set(IDENTITY_FIELDS)
                or any(not isinstance(identity[key], int) for key in IDENTITY_FIELDS)
                or not isinstance(attachments, list)
                or not attachments
                or not isinstance(materialized, bool)
                or (
                    materialized
                    and not target.is_relative_to(RUNTIME_PACKAGE_EXECUTION_ROOT)
                )
            ):
                raise MountLauncherError("private view target identity is invalid")
            attachment_names: set[str] = set()
            for attachment in attachments:
                if (
                    not isinstance(attachment, dict)
                    or not isinstance(attachment["name"], str)
                    or not attachment["name"]
                    or Path(attachment["name"]).name != attachment["name"]
                    or attachment["name"] in {".", ".."}
                    or attachment.get("kind")
                    not in {"file", "directory", "sealed_file", "symlink"}
                    or attachment["name"] in attachment_names
                ):
                    raise MountLauncherError(
                        "private view attachment has an unsupported shape"
                    )
                if attachment["kind"] == "sealed_file":
                    if (
                        set(attachment)
                        != {
                            "name",
                            "kind",
                            "snapshot_fd",
                            "size",
                            "digest",
                            "mode",
                        }
                        or not isinstance(attachment["snapshot_fd"], int)
                        or attachment["snapshot_fd"] < 3
                        or not isinstance(attachment["size"], int)
                        or attachment["size"] < 0
                        or not isinstance(attachment["mode"], int)
                        or attachment["mode"] & ~0o7777
                        or not isinstance(attachment["digest"], str)
                        or not attachment["digest"].startswith("sha256:")
                        or len(attachment["digest"]) != 71
                    ):
                        raise MountLauncherError(
                            "sealed private view attachment is invalid"
                        )
                elif attachment["kind"] == "symlink":
                    if (
                        set(attachment)
                        != {"name", "kind", "source", "identity", "link_target"}
                        or not isinstance(attachment["source"], str)
                        or not Path(attachment["source"]).is_absolute()
                        or not isinstance(attachment["link_target"], str)
                        or not attachment["link_target"]
                        or not isinstance(attachment["identity"], dict)
                        or set(attachment["identity"]) != set(IDENTITY_FIELDS)
                        or any(
                            not isinstance(attachment["identity"][key], int)
                            for key in IDENTITY_FIELDS
                        )
                    ):
                        raise MountLauncherError(
                            "private view symlink attachment identity is invalid"
                        )
                elif (
                    set(attachment) != {"name", "kind", "source", "identity"}
                    or not isinstance(attachment["source"], str)
                    or not Path(attachment["source"]).is_absolute()
                    or not isinstance(attachment["identity"], dict)
                    or set(attachment["identity"]) != set(IDENTITY_FIELDS)
                    or any(
                        not isinstance(attachment["identity"][key], int)
                        for key in IDENTITY_FIELDS
                    )
                ):
                    raise MountLauncherError(
                        "private view attachment identity is invalid"
                    )
                attachment_names.add(attachment["name"])
            flags = os.O_PATH | os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            try:
                descriptor = os.open(target, flags)
            except OSError as exc:
                raise MountLauncherError("cannot open one exact private view target") from exc
            descriptors.append(descriptor)
            observed = os.fstat(descriptor)
            if not stat.S_ISDIR(observed.st_mode) or (
                not materialized
                and any(
                    identity[key] != getattr(observed, field)
                    for key, field in IDENTITY_FIELDS.items()
                )
            ):
                raise MountLauncherError("private view target identity changed")
        return descriptors
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise


def _open_attachment_sources(views: object) -> list[int]:
    assert isinstance(views, list)
    descriptors: list[int] = []
    try:
        for view in views:
            assert isinstance(view, dict)
            attachments = view["attachments"]
            assert isinstance(attachments, list)
            for attachment in attachments:
                assert isinstance(attachment, dict)
                if attachment["kind"] == "sealed_file":
                    descriptor = int(attachment["snapshot_fd"])
                    try:
                        observed = os.fstat(descriptor)
                        seals = fcntl.fcntl(descriptor, fcntl.F_GET_SEALS)
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        digest = hashlib.sha256()
                        observed_bytes = 0
                        while True:
                            chunk = os.read(descriptor, 1024 * 1024)
                            if not chunk:
                                break
                            observed_bytes += len(chunk)
                            digest.update(chunk)
                        os.lseek(descriptor, 0, os.SEEK_SET)
                    except OSError as exc:
                        raise MountLauncherError(
                            "cannot verify one sealed private view attachment"
                        ) from exc
                    if (
                        not stat.S_ISREG(observed.st_mode)
                        or observed.st_size != attachment["size"]
                        or observed_bytes != attachment["size"]
                        or seals & REQUIRED_MEMFD_SEALS != REQUIRED_MEMFD_SEALS
                        or "sha256:" + digest.hexdigest() != attachment["digest"]
                    ):
                        raise MountLauncherError(
                            "sealed private view attachment changed"
                        )
                    descriptors.append(descriptor)
                    attachment["opened_source_fd"] = descriptor
                    continue
                source = Path(str(attachment["source"]))
                identity = attachment["identity"]
                assert isinstance(identity, dict)
                flags = os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW
                if attachment["kind"] == "directory":
                    flags |= os.O_DIRECTORY
                try:
                    descriptor = os.open(source, flags)
                except OSError as exc:
                    raise MountLauncherError(
                        "cannot open one exact private view attachment"
                    ) from exc
                descriptors.append(descriptor)
                observed = os.fstat(descriptor)
                if any(
                    identity[key] != getattr(observed, field)
                    for key, field in IDENTITY_FIELDS.items()
                ):
                    raise MountLauncherError(
                        "private view attachment identity changed"
                    )
                if attachment["kind"] == "symlink" and os.readlink(
                    source
                ) != attachment["link_target"]:
                    raise MountLauncherError("private view symlink target changed")
                attachment["opened_source_fd"] = descriptor
        return descriptors
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise


def _await_setup_release(setup_fd: int) -> None:
    try:
        if os.write(setup_fd, SETUP_READY) != 1:
            raise MountLauncherError("mount setup readiness write was incomplete")
        if os.read(setup_fd, 1) != SETUP_RELEASE:
            raise MountLauncherError("mount setup was not released by its parent")
    except OSError as exc:
        raise MountLauncherError("mount setup handshake failed") from exc


def _mount_private_tmpfs(libc: ctypes.CDLL, target: Path) -> None:
    """Create the runtime-owned package parent inside this mount namespace."""

    flags = os.O_PATH | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        target_fd = os.open(target, flags)
    except OSError as exc:
        raise MountLauncherError(
            "cannot open the runtime package tmpfs parent"
        ) from exc
    filesystem_fd = mount_fd = -1
    try:
        filesystem_fd = _syscall(
            libc,
            SYS_FSOPEN,
            ctypes.c_char_p(b"tmpfs"),
            FSOPEN_CLOEXEC,
        )
        _syscall(
            libc,
            SYS_FSCONFIG,
            filesystem_fd,
            FSCONFIG_CMD_CREATE,
            ctypes.c_void_p(0),
            ctypes.c_void_p(0),
            0,
        )
        mount_fd = _syscall(libc, SYS_FSMOUNT, filesystem_fd, FSMOUNT_CLOEXEC, 0)
        _syscall(
            libc,
            SYS_MOVE_MOUNT,
            mount_fd,
            ctypes.c_char_p(b""),
            target_fd,
            ctypes.c_char_p(b""),
            MOVE_MOUNT_F_EMPTY_PATH | MOVE_MOUNT_T_EMPTY_PATH,
        )
    except OSError as exc:
        raise MountLauncherError(
            "cannot create the runtime package tmpfs parent"
        ) from exc
    finally:
        os.close(target_fd)
        if mount_fd >= 0:
            os.close(mount_fd)
        if filesystem_fd >= 0:
            os.close(filesystem_fd)


def _prepare_materialized_views(libc: ctypes.CDLL, views: object) -> None:
    assert isinstance(views, list)
    materialized_targets = sorted(
        {
            Path(str(view["target"]))
            for view in views
            if isinstance(view, dict) and view.get("materialized", False)
        },
        key=lambda path: (len(path.parts), str(path)),
    )
    if not materialized_targets:
        return
    if any(
        not target.is_relative_to(RUNTIME_PACKAGE_EXECUTION_ROOT)
        for target in materialized_targets
    ):
        raise MountLauncherError(
            "materialized runtime package view is outside its execution coordinate"
        )
    _mount_private_tmpfs(libc, RUNTIME_PACKAGE_EXECUTION_ROOT.parent)
    for target in materialized_targets:
        try:
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise MountLauncherError(
                "cannot create the runtime package execution coordinate"
            ) from exc


def _command_visible_target_descriptor(view: dict[str, object], opened_fd: int) -> int:
    """Reopen the exact command-visible target immediately before attachment."""

    target = Path(str(view["target"]))
    identity = view["identity"]
    assert isinstance(identity, dict)
    flags = os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise MountLauncherError(
            "command-visible private view target became unavailable"
        ) from exc
    try:
        observed = os.fstat(descriptor)
        originally_opened = os.fstat(opened_fd)
        materialized = bool(view.get("materialized", False))
        if (
            not stat.S_ISDIR(observed.st_mode)
            or (
                not materialized
                and any(
                    identity[key] != getattr(observed, field)
                    for key, field in IDENTITY_FIELDS.items()
                )
            )
            or (
                not materialized
                and any(
                    getattr(observed, field) != getattr(originally_opened, field)
                    for field in IDENTITY_FIELDS.values()
                )
            )
        ):
            raise MountLauncherError(
                "command-visible private view target identity changed"
            )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _attach_private_views(
    libc: ctypes.CDLL,
    views: object,
    descriptors: list[int],
) -> None:
    assert isinstance(views, list)
    if len(views) != len(descriptors):
        raise MountLauncherError("private view descriptor count changed")
    for view, target_fd in zip(views, descriptors, strict=True):
        assert isinstance(view, dict)
        attachments = view["attachments"]
        assert isinstance(attachments, list)
        filesystem_fd = mount_fd = -1
        try:
            filesystem_fd = _syscall(
                libc,
                SYS_FSOPEN,
                ctypes.c_char_p(b"tmpfs"),
                FSOPEN_CLOEXEC,
            )
            _syscall(
                libc,
                SYS_FSCONFIG,
                filesystem_fd,
                FSCONFIG_CMD_CREATE,
                ctypes.c_void_p(0),
                ctypes.c_void_p(0),
                0,
            )
            mount_fd = _syscall(libc, SYS_FSMOUNT, filesystem_fd, FSMOUNT_CLOEXEC, 0)
            for attachment in attachments:
                assert isinstance(attachment, dict)
                name = str(attachment["name"])
                kind = str(attachment["kind"])
                source_fd = int(attachment["opened_source_fd"])
                source_stat = os.fstat(source_fd)
                if (
                    kind == "directory" and not stat.S_ISDIR(source_stat.st_mode)
                ) or (kind == "file" and not stat.S_ISREG(source_stat.st_mode)) or (
                    kind == "symlink" and not stat.S_ISLNK(source_stat.st_mode)
                ):
                    raise MountLauncherError(
                        "private view attachment source type changed"
                    )
                if kind == "symlink":
                    os.symlink(
                        str(attachment["link_target"]),
                        name,
                        dir_fd=mount_fd,
                    )
                    continue
                if kind == "directory":
                    os.mkdir(name, mode=0o700, dir_fd=mount_fd)
                else:
                    created_fd = os.open(
                        name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                        0o600,
                        dir_fd=mount_fd,
                    )
                    if kind == "sealed_file":
                        os.fchmod(created_fd, int(attachment["mode"]))
                        digest = hashlib.sha256()
                        observed_bytes = 0
                        os.lseek(source_fd, 0, os.SEEK_SET)
                        while True:
                            chunk = os.read(source_fd, 1024 * 1024)
                            if not chunk:
                                break
                            digest.update(chunk)
                            observed_bytes += len(chunk)
                            offset = 0
                            while offset < len(chunk):
                                written = os.write(created_fd, chunk[offset:])
                                if written <= 0:
                                    raise OSError(
                                        "sealed attachment copy was incomplete"
                                    )
                                offset += written
                        if (
                            observed_bytes != attachment["size"]
                            or "sha256:" + digest.hexdigest()
                            != attachment["digest"]
                        ):
                            raise MountLauncherError(
                                "sealed private view attachment changed during copy"
                            )
                    os.close(created_fd)
                if kind == "sealed_file":
                    continue
                target_flags = os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW
                if kind == "directory":
                    target_flags |= os.O_DIRECTORY
                attachment_target_fd = os.open(
                    name,
                    target_flags,
                    dir_fd=mount_fd,
                )
                source_mount_fd = -1
                try:
                    open_tree_flags = (
                        AT_EMPTY_PATH | OPEN_TREE_CLONE | OPEN_TREE_CLOEXEC
                    )
                    if kind == "directory":
                        open_tree_flags |= AT_RECURSIVE
                    source_mount_fd = _syscall(
                        libc,
                        SYS_OPEN_TREE,
                        source_fd,
                        ctypes.c_char_p(b""),
                        open_tree_flags,
                    )
                    attributes = _MountAttr(MOUNT_ATTR_RDONLY, 0, 0, 0)
                    attribute_flags = AT_EMPTY_PATH
                    if kind == "directory":
                        attribute_flags |= AT_RECURSIVE
                    _syscall(
                        libc,
                        SYS_MOUNT_SETATTR,
                        source_mount_fd,
                        ctypes.c_char_p(b""),
                        attribute_flags,
                        ctypes.byref(attributes),
                        ctypes.sizeof(attributes),
                    )
                    _syscall(
                        libc,
                        SYS_MOVE_MOUNT,
                        source_mount_fd,
                        ctypes.c_char_p(b""),
                        attachment_target_fd,
                        ctypes.c_char_p(b""),
                        MOVE_MOUNT_F_EMPTY_PATH | MOVE_MOUNT_T_EMPTY_PATH,
                    )
                finally:
                    if source_mount_fd >= 0:
                        os.close(source_mount_fd)
                    os.close(attachment_target_fd)
            attributes = _MountAttr(MOUNT_ATTR_RDONLY, 0, 0, 0)
            _syscall(
                libc,
                SYS_MOUNT_SETATTR,
                mount_fd,
                ctypes.c_char_p(b""),
                AT_EMPTY_PATH | AT_RECURSIVE,
                ctypes.byref(attributes),
                ctypes.sizeof(attributes),
            )
            command_target_fd = _command_visible_target_descriptor(view, target_fd)
            live_path_mount_fd = -1
            try:
                live_path_mount_fd = _syscall(
                    libc,
                    SYS_OPEN_TREE,
                    mount_fd,
                    ctypes.c_char_p(b""),
                    AT_EMPTY_PATH
                    | AT_RECURSIVE
                    | OPEN_TREE_CLONE
                    | OPEN_TREE_CLOEXEC,
                )
                # Keep the descriptor-backed view for the historical
                # defense-in-depth contour.  The second attachment preserves
                # its live-path compatibility, but this launcher is not the
                # source-isolation boundary and does not prove protection
                # against a same-UID rename or replacement after attachment.
                _syscall(
                    libc,
                    SYS_MOVE_MOUNT,
                    mount_fd,
                    ctypes.c_char_p(b""),
                    command_target_fd,
                    ctypes.c_char_p(b""),
                    MOVE_MOUNT_F_EMPTY_PATH | MOVE_MOUNT_T_EMPTY_PATH,
                )
                _syscall(
                    libc,
                    SYS_MOVE_MOUNT,
                    live_path_mount_fd,
                    ctypes.c_char_p(b""),
                    AT_FDCWD,
                    ctypes.c_char_p(os.fsencode(str(view["target"]))),
                    MOVE_MOUNT_F_EMPTY_PATH,
                )
            finally:
                if live_path_mount_fd >= 0:
                    os.close(live_path_mount_fd)
                os.close(command_target_fd)
        except OSError as exc:
            raise MountLauncherError(
                "cannot attach a private tmpfs to one exact view target"
            ) from exc
        finally:
            if mount_fd >= 0:
                os.close(mount_fd)
            if filesystem_fd >= 0:
                os.close(filesystem_fd)


def _drop_all_capabilities(libc: ctypes.CDLL) -> None:
    try:
        last_capability = int(
            Path("/proc/sys/kernel/cap_last_cap").read_text(encoding="ascii").strip()
        )
    except (OSError, ValueError) as exc:
        raise MountLauncherError("cannot determine the kernel capability ceiling") from exc
    for capability in range(last_capability + 1):
        if libc.prctl(PR_CAPBSET_DROP, capability, 0, 0, 0) != 0:
            error = ctypes.get_errno()
            raise MountLauncherError("cannot clear the capability bounding set") from OSError(
                error, os.strerror(error)
            )
    header = _CapabilityHeader(LINUX_CAPABILITY_VERSION_3, 0)
    data = (_CapabilityData * 2)()
    if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
        error = ctypes.get_errno()
        raise MountLauncherError("cannot clear process capabilities") from OSError(
            error, os.strerror(error)
        )
    if libc.prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise MountLauncherError("cannot clear ambient capabilities") from OSError(
            error, os.strerror(error)
        )
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise MountLauncherError("cannot set no-new-privileges") from OSError(
            error, os.strerror(error)
        )


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-fd", required=True, type=int)
    parser.add_argument("--setup-fd", required=True, type=int)
    arguments = parser.parse_args(argv)
    if arguments.payload_fd < 3 or arguments.setup_fd < 3:
        parser.error("payload and setup descriptors are required")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = _arguments(sys.argv[1:] if argv is None else argv)
    try:
        if os.uname().machine != "x86_64":
            raise MountLauncherError(
                "descriptor-targeted mount syscalls require the admitted x86_64 host"
            )
        payload = _read_payload(arguments.payload_fd)
        os.close(arguments.payload_fd)
        libc = ctypes.CDLL(None, use_errno=True)
        _write_user_namespace_maps(libc)
        _make_mounts_private(libc)
        _prepare_materialized_views(libc, payload["views"])
        target_descriptors = _open_view_targets(payload["views"])
        source_descriptors = _open_attachment_sources(payload["views"])
        try:
            _await_setup_release(arguments.setup_fd)
            _attach_private_views(libc, payload["views"], target_descriptors)
            if os.write(arguments.setup_fd, SETUP_ATTACHED) != 1:
                raise MountLauncherError(
                    "mount setup attachment confirmation was incomplete"
                )
            os.close(arguments.setup_fd)
        finally:
            for descriptor in target_descriptors:
                os.close(descriptor)
            for descriptor in source_descriptors:
                os.close(descriptor)
        _drop_all_capabilities(libc)
        wrapper_fd = int(payload["mount_wrapper_fd"])
        wrapper_argv = payload["wrapper_argv"]
        assert isinstance(wrapper_argv, list)
        os.execve(f"/proc/self/fd/{wrapper_fd}", wrapper_argv, os.environ)
    except (MountLauncherError, OSError) as exc:
        _fail(str(exc))
    raise AssertionError("verified mount wrapper exec unexpectedly returned")


if __name__ == "__main__":
    raise SystemExit(main())
