"""Bubblewrap backend and PID-1 namespace supervisor for process containment.

This file is both loaded by the host-side adapter and executed inside the
private namespace.  It intentionally uses only the standard library.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


RECEIPT_PREFIX = "__ABYSS_CONTAINMENT_RECEIPT_V1__"
READY_PREFIX = "__ABYSS_CONTAINMENT_READY_V1__"
STATUS_CODES = {
    "completed": 0,
    "containment_unsupported": 125,
    "recovery_required": 126,
    "infrastructure_failure": 127,
}
PRIVATE_TMP_PATHS = ("/tmp", "/var/tmp", "/dev/shm")
FORBIDDEN_ENVIRONMENT = (
    "TMPDIR",
    "TEMP",
    "TMP",
    "PYTEST_DEBUG_TEMPROOT",
    "PYTEST_ADDOPTS",
    "PYTHONPYCACHEPREFIX",
)
PR_SET_DUMPABLE = 4
PR_SET_NO_NEW_PRIVS = 38
PR_SET_CHILD_SUBREAPER = 36
PR_GET_DUMPABLE = 3
PR_GET_NO_NEW_PRIVS = 39


class AdmissionError(RuntimeError):
    pass


class ExportError(RuntimeError):
    pass


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _call_prctl(option: int, argument: int) -> None:
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
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _query_prctl(option: int) -> int:
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
    value = prctl(option, 0, 0, 0, 0)
    if value < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return int(value)


def _set_namespace_security() -> None:
    _call_prctl(PR_SET_DUMPABLE, 0)
    _call_prctl(PR_SET_NO_NEW_PRIVS, 1)
    _call_prctl(PR_SET_CHILD_SUBREAPER, 1)


def _security_evidence() -> dict[str, int]:
    return {
        "dumpable": _query_prctl(PR_GET_DUMPABLE),
        "no_new_privs": _query_prctl(PR_GET_NO_NEW_PRIVS),
    }


def _mapping_evidence() -> dict[str, str]:
    evidence: dict[str, str] = {}
    for name in ("uid_map", "gid_map"):
        path = Path("/proc/self") / name
        value = path.read_text(encoding="ascii").strip()
        if not value or not any(part.isdigit() and int(part) > 0 for part in value.split()):
            raise OSError(95, f"{name} is empty or unmapped")
        evidence[name] = value
    return evidence


def _namespace_identity() -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for name in ("user", "pid", "mnt"):
        path = Path("/proc/self/ns") / name
        stat_result = path.stat()
        result[name] = {"device": stat_result.st_dev, "inode": stat_result.st_ino}
    return result


def _mount_evidence() -> dict[str, dict[str, object]]:
    wanted = ("/proc", "/tmp", "/var/tmp", "/dev/shm")
    evidence: dict[str, dict[str, object]] = {}
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {path: {"error": str(exc)} for path in wanted}
    for path in wanted:
        matches: list[dict[str, object]] = []
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[4] != path or "-" not in fields:
                continue
            separator = fields.index("-")
            matches.append(
                {
                    "mount_id": int(fields[0]),
                    "parent_id": int(fields[1]),
                    "mount_point": fields[4],
                    "filesystem": fields[separator + 1],
                    "source": fields[separator + 2],
                    "options": fields[5],
                }
            )
        evidence[path] = {"matches": matches, "private_expected": True}
    return evidence


def _children_snapshot() -> list[int]:
    try:
        raw = Path("/proc/1/task/1/children").read_text(encoding="ascii")
    except OSError as exc:
        raise RuntimeError(f"cannot inspect PID-1 children: {exc}") from exc
    return [int(value) for value in raw.split() if value.isdigit()]


def _process_starttime(pid: int) -> int | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").split()
        return int(fields[21])
    except (OSError, ValueError, IndexError):
        return None


def _reap_nonblocking(reaped: list[dict[str, object]]) -> bool:
    try:
        children = _children_snapshot()
    except RuntimeError:
        children = []
    starttimes = {pid: _process_starttime(pid) for pid in children}
    had_child = False
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return had_child
        except InterruptedError:
            continue
        if pid == 0:
            return had_child
        had_child = True
        reaped.append(
            {
                "pid": pid,
                "starttime": starttimes.get(pid),
                "status": status,
            }
        )


def _broadcast(signum: int) -> None:
    try:
        os.kill(-1, signum)
    except ProcessLookupError:
        # This is only a signal-delivery observation.  Drain proof still uses
        # waitpid and the PID-1 children list below.
        pass


def _drain_children(
    reaped: list[dict[str, object]],
    *,
    timeout: float,
    grace: float,
) -> tuple[bool, bool]:
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        _reap_nonblocking(reaped)
        children = _children_snapshot()
        if not children:
            try:
                os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return True, False
        if time.monotonic() >= deadline:
            break
        select.select([], [], [], 0.01)

    _broadcast(signal.SIGTERM)
    grace_deadline = time.monotonic() + max(0.0, grace)
    while time.monotonic() < grace_deadline:
        _reap_nonblocking(reaped)
        if not _children_snapshot():
            try:
                os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return True, True
        select.select([], [], [], 0.01)

    _broadcast(signal.SIGKILL)
    kill_deadline = time.monotonic() + max(0.1, grace)
    while time.monotonic() < kill_deadline:
        _reap_nonblocking(reaped)
        if not _children_snapshot():
            try:
                os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return True, True
        select.select([], [], [], 0.01)
    _reap_nonblocking(reaped)
    return not _children_snapshot(), True


def _exit_code(status: int) -> int:
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 127


def _hidden_residue() -> list[str]:
    found: list[str] = []
    for root in PRIVATE_TMP_PATHS:
        root_path = Path(root)
        if not root_path.exists():
            continue
        try:
            for path in root_path.rglob("*"):
                if path.name.startswith((".entry-", ".recovered-", ".delete-")):
                    found.append(str(path))
        except OSError:
            found.append(f"{root}:enumeration-error")
    return found


def _emit_receipt(receipt: Mapping[str, object]) -> None:
    sys.stderr.write(RECEIPT_PREFIX + json.dumps(receipt, sort_keys=True) + "\n")
    sys.stderr.flush()


def _validate_mount_evidence(evidence: Mapping[str, Mapping[str, object]]) -> None:
    expected = {"/proc": "proc", "/tmp": "tmpfs", "/var/tmp": "tmpfs", "/dev/shm": "tmpfs"}
    for path, filesystem in expected.items():
        matches = evidence.get(path, {}).get("matches", [])
        if not isinstance(matches, list) or not any(
            isinstance(item, dict) and item.get("filesystem") == filesystem
            for item in matches
        ):
            raise OSError(95, f"required private {filesystem} mount missing at {path}")


def _namespace_init(argv: Sequence[str]) -> int:
    if not argv or argv[0] != "--namespace-init":
        return 2
    remaining = list(argv[1:])
    admission_fd = 0
    if len(remaining) >= 2 and remaining[0] == "--admission-fd":
        try:
            admission_fd = int(remaining[1])
        except ValueError:
            return 2
        remaining = remaining[2:]
    command = remaining
    if not command:
        return 2
    try:
        _set_namespace_security()
        security_evidence = _security_evidence()
        if security_evidence != {"dumpable": 0, "no_new_privs": 1}:
            raise OSError(95, f"namespace security posture is not admitted: {security_evidence}")
        mapping_evidence = _mapping_evidence()
        namespace_identity = _namespace_identity()
        mount_evidence = _mount_evidence()
        _validate_mount_evidence(mount_evidence)
    except (OSError, RuntimeError) as exc:
        _emit_receipt(
            {
                "schema_version": "abyss-stack-process-containment-v1",
                "status": "containment_unsupported",
                "command_started": False,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        )
        return STATUS_CODES["containment_unsupported"]

    reaped: list[dict[str, object]] = []
    main_pid: int | None = None
    main_starttime: int | None = None
    main_status: int | None = None
    interrupted = {"value": False}
    admission_released = {"value": False}

    def handle_signal(signum: int, _frame: object) -> None:
        interrupted["value"] = True
        # Before admission is released there is no user process to stop.  In
        # particular, broadcasting SIGTERM from PID 1 here can signal the
        # launcher itself through the namespace-wide broadcast and prevent
        # the fail-closed receipt from being emitted.  The host-side pidfd
        # signal is the admission revocation; the drain broadcast is only
        # needed once a command has actually been started.
        if main_pid is not None:
            _broadcast(signum)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    try:
        sys.stderr.write(READY_PREFIX + "\n")
        sys.stderr.flush()
        while not admission_released["value"]:
            if interrupted["value"]:
                _emit_receipt(
                    {
                        "schema_version": "abyss-stack-process-containment-v1",
                        "status": "containment_unsupported",
                        "command_started": False,
                        "namespace_init_pid": 1,
                        "namespace_init_starttime": _process_starttime(1),
                        "namespace_identity": namespace_identity,
                        "security_evidence": security_evidence,
                        "mapping_evidence": mapping_evidence,
                        "mount_evidence": mount_evidence,
                        "drain_complete": True,
                        "live_descendants": [],
                    }
                )
                return STATUS_CODES["containment_unsupported"]
            try:
                decision = os.read(admission_fd, 1)
            except InterruptedError:
                continue
            if decision != b"R":
                _emit_receipt(
                    {
                        "schema_version": "abyss-stack-process-containment-v1",
                        "status": "containment_unsupported",
                        "command_started": False,
                        "namespace_init_pid": 1,
                        "namespace_init_starttime": _process_starttime(1),
                        "namespace_identity": namespace_identity,
                        "security_evidence": security_evidence,
                        "mapping_evidence": mapping_evidence,
                        "mount_evidence": mount_evidence,
                        "drain_complete": True,
                        "live_descendants": [],
                        "error": {
                            "type": "AdmissionRevoked",
                            "message": "host admission was not released",
                        },
                    }
                )
                return STATUS_CODES["containment_unsupported"]
            admission_released["value"] = True
        try:
            os.close(admission_fd)
        except OSError:
            pass
        main_pid = os.fork()
        if main_pid == 0:
            try:
                _set_namespace_security()
                os.execvpe(command[0], command, os.environ.copy())
            except BaseException as exc:
                sys.stderr.write(f"namespace child exec failed: {exc}\n")
                os._exit(127)
        main_starttime = _process_starttime(main_pid)
        while main_status is None:
            try:
                pid, status = os.waitpid(main_pid, 0)
            except InterruptedError:
                continue
            if pid == main_pid:
                main_status = status
        drained, forced = _drain_children(
            reaped,
            timeout=float(os.environ.get("ABYSS_CONTAINMENT_DRAIN_TIMEOUT", "5")),
            grace=float(os.environ.get("ABYSS_CONTAINMENT_DRAIN_GRACE", "1")),
        )
        residue = _hidden_residue()
        status = "completed" if drained and not residue else "infrastructure_failure"
        receipt = {
            "schema_version": "abyss-stack-process-containment-v1",
            "status": status,
            "command_started": True,
            "namespace_init_pid": 1,
            "namespace_init_starttime": _process_starttime(1),
            "namespace_identity": namespace_identity,
            "security_evidence": security_evidence,
            "mapping_evidence": mapping_evidence,
            "mount_evidence": mount_evidence,
            "main_pid": main_pid,
            "main_starttime": main_starttime,
            "main_returncode": _exit_code(main_status),
            "drain_complete": drained,
            "forced_drain": forced,
            "reaped_descendants": reaped,
            "live_descendants": _children_snapshot(),
            "hidden_residue": residue,
            "storage_reclaim": "namespace_teardown_only",
            "host_path_deletion_authority": False,
            "numeric_pgid_authority": False,
            "interrupted": interrupted["value"],
        }
        _emit_receipt(receipt)
        return _exit_code(main_status) if status == "completed" else STATUS_CODES["infrastructure_failure"]
    except BaseException as exc:
        _broadcast(signal.SIGKILL)
        _drain_children(reaped, timeout=0.2, grace=0.2)
        _emit_receipt(
            {
                "schema_version": "abyss-stack-process-containment-v1",
                "status": "infrastructure_failure",
                "command_started": main_pid is not None,
                "namespace_identity": namespace_identity,
                "security_evidence": security_evidence,
                "mapping_evidence": mapping_evidence,
                "drain_complete": False,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        )
        return STATUS_CODES["infrastructure_failure"]


def _validate_path(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise AdmissionError(f"{label} is not readable: {path}: {exc}") from exc
    if not resolved.is_dir():
        raise AdmissionError(f"{label} must be a directory: {path}")
    return resolved


def _validate_guest_root(guest: str, label: str) -> None:
    guest_path = Path(guest)
    if not guest.startswith("/") or ".." in guest_path.parts or guest == "/":
        raise AdmissionError(f"{label} guest root is unsafe: {guest}")
    if guest in {"/proc", "/dev", "/tmp", "/var/tmp", "/dev/shm"}:
        raise AdmissionError(f"{label} overlaps private containment mount: {guest}")


def _validate_kernel_capabilities() -> None:
    if not hasattr(os, "pidfd_open") or not hasattr(os, "waitid") or not hasattr(os, "P_PIDFD"):
        raise AdmissionError("pidfd_lifecycle_unavailable")
    if not hasattr(signal, "pidfd_send_signal"):
        raise AdmissionError("pidfd_signal_unavailable")
    for path, label in (("/proc/self/uid_map", "user_mapping"), ("/proc/self/gid_map", "group_mapping")):
        try:
            content = Path(path).read_text(encoding="ascii").strip()
        except OSError as exc:
            raise AdmissionError(f"{label}_unavailable:{exc}") from exc
        if not content or not any(part.isdigit() and int(part) > 0 for part in content.split()):
            raise AdmissionError(f"{label}_empty")


def _host_boot_id() -> str:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError as exc:
        raise AdmissionError(f"host_boot_id_unavailable:{exc}") from exc
    if not value:
        raise AdmissionError("host_boot_id_empty")
    return value


def _validate_spec(spec: Any) -> dict[str, object]:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        raise AdmissionError("linux_namespace_profile_required")
    _validate_kernel_capabilities()
    source = spec.source_root
    source_host = _validate_path(Path(source.host), "source_root")
    _validate_guest_root(str(source.guest), "source_root")
    roots: list[dict[str, str]] = [
        {"host": str(source_host), "guest": str(source.guest)},
    ]
    guest_roots = {str(source.guest)}
    for item in spec.runtime_roots:
        host = _validate_path(Path(item.host), "runtime_root")
        guest = str(item.guest)
        _validate_guest_root(guest, "runtime")
        if guest in guest_roots:
            raise AdmissionError(f"duplicate guest root: {guest}")
        guest_roots.add(guest)
        roots.append({"host": str(host), "guest": guest})
    if not str(spec.cwd).startswith("/") or ".." in Path(spec.cwd).parts:
        raise AdmissionError(f"guest cwd is unsafe: {spec.cwd}")
    if not spec.command or not str(spec.command[0]).startswith("/"):
        raise AdmissionError("command must use an absolute guest executable")
    if any("\x00" in str(argument) for argument in spec.command):
        raise AdmissionError("command_contains_nul")
    environment = {str(key): str(value) for key, value in spec.environment.items()}
    forbidden = sorted(set(environment).intersection(FORBIDDEN_ENVIRONMENT))
    if forbidden:
        raise AdmissionError("external_redirection:" + ",".join(forbidden))
    if any("\x00" in value for value in environment.values()):
        raise AdmissionError("environment_contains_nul")
    if any("\x00" in key or not key or "=" in key for key in environment):
        raise AdmissionError("environment_key_invalid")
    if not Path("/proc").is_dir():
        raise AdmissionError("procfs_unavailable")
    host_boot_id = _host_boot_id()
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise AdmissionError("bubblewrap_unavailable")
    bwrap_path = Path(bwrap).resolve(strict=True)
    if not os.access(bwrap_path, os.X_OK):
        raise AdmissionError("bubblewrap_not_executable")
    try:
        bwrap_version = subprocess.run(
            [str(bwrap_path), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise AdmissionError(f"bubblewrap_probe_failed:{exc}") from exc
    try:
        bwrap_help = subprocess.run(
            [str(bwrap_path), "--help"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise AdmissionError(f"bubblewrap_feature_probe_failed:{exc}") from exc
    required_flags = (
        "--unshare-user",
        "--unshare-pid",
        "--as-pid-1",
        "--ro-bind",
        "--tmpfs",
        "--proc",
        "--disable-userns",
    )
    missing_flags = [flag for flag in required_flags if flag not in bwrap_help]
    if missing_flags:
        raise AdmissionError("bubblewrap_features_missing:" + ",".join(missing_flags))
    fd_targets: dict[str, str] = {}
    try:
        for raw_fd in sorted(os.listdir("/proc/self/fd"), key=lambda value: int(value) if value.isdigit() else -1):
            if not raw_fd.isdigit():
                continue
            fd = int(raw_fd)
            if fd <= 2:
                continue
            try:
                inheritable = os.get_inheritable(fd)
                if not inheritable:
                    continue
                fd_targets[raw_fd] = os.readlink(f"/proc/self/fd/{raw_fd}")
            except OSError as exc:
                if exc.errno in (2, 9):
                    # The descriptor disappeared between the directory
                    # snapshot and readlink; it is not an inherited handle.
                    continue
                raise AdmissionError(f"inherited_fd_unreadable:{raw_fd}:{exc}") from exc
    except OSError as exc:
        raise AdmissionError(f"inherited_fd_probe_failed:{exc}") from exc
    if fd_targets:
        raise AdmissionError("undeclared_inherited_fds:" + ",".join(sorted(fd_targets)))
    backend_digest = _sha256_file(bwrap_path)
    command_digest = hashlib.sha256(
        _json_bytes([str(argument) for argument in spec.command])
    ).hexdigest()
    environment_digest = hashlib.sha256(_json_bytes(environment)).hexdigest()
    profile = {
        "profile_id": str(spec.profile_id),
        "source_root": roots[0],
        "runtime_roots": roots[1:],
        "cwd": str(spec.cwd),
        "private_tmp_paths": list(PRIVATE_TMP_PATHS),
        "backend": "bubblewrap",
        "backend_version": bwrap_version,
        "backend_digest": backend_digest,
        "environment_keys": sorted(environment),
        "command_digest": command_digest,
        "environment_digest": environment_digest,
        "host_boot_id": host_boot_id,
        "required_capabilities": [
            "user_namespace",
            "pid_namespace",
            "mount_namespace",
            "private_tmpfs",
            "private_procfs",
            "pidfd_wait",
            "pidfd_signal",
            "uid_gid_mapping",
        ],
    }
    profile_digest = hashlib.sha256(_json_bytes(profile)).hexdigest()
    return {
        "bwrap": str(bwrap_path),
        "bwrap_version": bwrap_version,
        "backend_digest": backend_digest,
        "profile": profile,
        "profile_digest": profile_digest,
        "command_digest": command_digest,
        "environment_digest": environment_digest,
        "host_boot_id": host_boot_id,
        "environment": environment,
        "roots": roots,
    }


def _guest_parent_dirs(paths: Iterable[str]) -> list[str]:
    dirs = {"/"}
    for raw in paths:
        current = Path(raw)
        for parent in [current, *current.parents]:
            value = str(parent)
            dirs.add(value)
            if value == "/":
                break
    return sorted(dirs, key=lambda value: (value.count("/"), value))


def _build_command(admission: Mapping[str, object], spec: Any) -> list[str]:
    bwrap = str(admission["bwrap"])
    profile = admission["profile"]
    assert isinstance(profile, dict)
    command = [
        bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--uid",
        "0",
        "--gid",
        "0",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--disable-userns",
        "--assert-userns-disabled",
        "--as-pid-1",
        "--cap-drop",
        "ALL",
        "--clearenv",
    ]
    roots = [profile["source_root"], *profile["runtime_roots"]]
    assert all(isinstance(root, dict) for root in roots)
    guest_paths = [str(root["guest"]) for root in roots]
    guest_paths.extend(PRIVATE_TMP_PATHS)
    guest_paths.extend(("/proc", "/dev", "/workspace", "/tmp/home", "/tmp/xdg-cache", "/tmp/xdg-config", "/tmp/xdg-data", "/tmp/xdg-runtime"))
    for directory in _guest_parent_dirs(guest_paths):
        if directory != "/":
            command.extend(("--dir", directory))
    for root in roots:
        command.extend(("--ro-bind", str(root["host"]), str(root["guest"])))
    command.extend(("--proc", "/proc", "--dev", "/dev"))
    for path in ("/tmp", "/var/tmp", "/dev/shm", "/tmp/home", "/tmp/xdg-cache", "/tmp/xdg-config", "/tmp/xdg-data", "/tmp/xdg-runtime"):
        command.extend(("--tmpfs", path))
    command.extend(("--chdir", str(spec.cwd)))
    env = dict(admission["environment"])
    env.update(
        {
            "HOME": "/tmp/home",
            "TMPDIR": "/tmp",
            "TEMP": "/tmp",
            "TMP": "/tmp",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "ABYSS_CONTAINMENT_ACTIVE": "1",
            "XDG_CACHE_HOME": "/tmp/xdg-cache",
            "XDG_CONFIG_HOME": "/tmp/xdg-config",
            "XDG_DATA_HOME": "/tmp/xdg-data",
            "XDG_RUNTIME_DIR": "/tmp/xdg-runtime",
            "ABYSS_CONTAINMENT_DRAIN_TIMEOUT": str(spec.drain_timeout_seconds),
            "ABYSS_CONTAINMENT_DRAIN_GRACE": str(spec.termination_grace_seconds),
        }
    )
    for key, value in sorted(env.items()):
        command.extend(("--setenv", key, value))
    command.extend(
        (
            "--",
            str(spec.command[0]),
            str(LAUNCHER_PATH_IN_GUEST(spec, admission)),
            "--namespace-init",
            *[str(item) for item in spec.command],
        )
    )
    return command


def LAUNCHER_PATH_IN_GUEST(spec: Any, admission: Mapping[str, object]) -> str:
    source = admission["profile"]["source_root"]
    assert isinstance(source, dict)
    guest_root = str(source["guest"])
    relative = Path(__file__).resolve().relative_to(Path(source["host"]))
    return str(Path(guest_root) / relative)


def _read_starttime(pid: int) -> int | None:
    return _process_starttime(pid)


def _host_namespace_init_identity(parent_pid: int) -> dict[str, object] | None:
    """Find the host identity of bwrap's private PID-1 child.

    ``Popen.pid`` is bubblewrap's host-side controller.  With ``--unshare-pid``
    the process that is PID 1 in the private namespace is a child of that
    controller and has a different host PID.  Admission must probe that child;
    probing the controller would inspect the host-facing wrapper and would
    either miss the namespace boundary or reject every supported host.

    The numeric child PID is only a procfs lookup coordinate.  The returned
    identity is bound to the controller's child relation, a start-time value,
    and a pidfd capability probe; it is never used as lifecycle authority.
    """

    try:
        children_path = Path(f"/proc/{parent_pid}/task/{parent_pid}/children")
        child_pids = [
            int(value)
            for value in children_path.read_text(encoding="ascii").split()
            if value.isdigit()
        ]
    except (OSError, ValueError):
        return None

    candidates: list[dict[str, object]] = []
    for child_pid in child_pids:
        try:
            status = Path(f"/proc/{child_pid}/status").read_text(encoding="ascii")
        except OSError:
            continue
        nspid_line = next(
            (line for line in status.splitlines() if line.startswith("NSpid:")),
            None,
        )
        if nspid_line is None:
            continue
        nspids = nspid_line.split()[1:]
        if not nspids or nspids[-1] != "1":
            continue
        starttime = _read_starttime(child_pid)
        if starttime is None:
            continue
        try:
            pidfd = os.pidfd_open(child_pid)
        except OSError:
            continue
        else:
            os.close(pidfd)
        candidates.append(
            {
                "pid": child_pid,
                "starttime": starttime,
                "pidfd": True,
                "authority": "parent-child+starttime",
                "numeric_pid_authority": False,
            }
        )
    if len(candidates) != 1:
        return None
    return candidates[0]


def _read_receipt(stderr: bytes) -> tuple[dict[str, object] | None, bytes]:
    lines = stderr.splitlines(keepends=True)
    receipt: dict[str, object] | None = None
    visible: list[bytes] = []
    for line in lines:
        if line.startswith(RECEIPT_PREFIX.encode()):
            try:
                receipt = json.loads(line[len(RECEIPT_PREFIX) :].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                receipt = {"status": "infrastructure_failure", "diagnostic": "invalid_receipt"}
        elif not line.startswith(READY_PREFIX.encode()):
            visible.append(line)
    return receipt, b"".join(visible)


def _pidfd_signal(pidfd: int, signum: int) -> None:
    sender = getattr(signal, "pidfd_send_signal", None)
    if sender is None:
        raise OSError(95, "pidfd signal support unavailable")
    sender(pidfd, signum)


def _read_line_fd(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        if chunk == b"\n":
            return b"".join(chunks)


def _waitid_returncode(info: Any) -> int:
    # waitid(P_PIDFD, ...) returns the exit status in si_status for exited
    # children and the terminating signal for signalled children.  The
    # pidfd, rather than the numeric PID, is the wait authority.
    if getattr(info, "si_code", None) == getattr(os, "CLD_EXITED", 1):
        return int(info.si_status)
    return -int(info.si_status)


def _collect_by_pidfd(
    process: subprocess.Popen[bytes],
    pidfd: int,
    *,
    first_stderr: bytes,
    admission_byte: bytes,
) -> tuple[bytes, bytes, int]:
    if process.stdin is not None:
        stdin = process.stdin
        try:
            if admission_byte:
                stdin.write(admission_byte)
                stdin.flush()
        finally:
            stdin.close()
        process.stdin = None

    raw_streams: dict[int, Any] = {}
    stdout_fd: int | None = None
    stderr_fd: int | None = None
    if process.stdout is not None:
        stdout_fd = process.stdout.fileno()
        raw = process.stdout.detach()
        raw_streams[raw.fileno()] = raw
    if process.stderr is not None:
        stderr_fd = process.stderr.fileno()
        raw = process.stderr.detach()
        raw_streams[raw.fileno()] = raw
    pipe_fds: dict[int, bytearray] = {}
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    poller = select.poll()
    for fd in (stdout_fd, stderr_fd):
        if fd is not None:
            pipe_fds[fd] = bytearray()
            poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
    poller.register(pidfd, select.POLLIN | select.POLLHUP | select.POLLERR)
    pidfd_returncode: int | None = None
    while pipe_fds or pidfd_returncode is None:
        events = poller.poll()
        for fd, event in events:
            if fd == pidfd:
                try:
                    info = os.waitid(os.P_PIDFD, pidfd, os.WEXITED)
                except ChildProcessError as exc:
                    raise RuntimeError(f"pidfd wait lost child identity: {exc}") from exc
                if info is not None:
                    pidfd_returncode = _waitid_returncode(info)
                    poller.unregister(pidfd)
                continue
            if fd not in pipe_fds:
                continue
            payload = os.read(fd, 64 * 1024)
            if payload:
                pipe_fds[fd].extend(payload)
                if fd == stdout_fd:
                    stdout_buffer.extend(payload)
                elif fd == stderr_fd:
                    stderr_buffer.extend(payload)
            else:
                poller.unregister(fd)
                del pipe_fds[fd]
                raw = raw_streams.pop(fd, None)
                if raw is not None:
                    raw.close()
                else:
                    os.close(fd)
    for raw in raw_streams.values():
        raw.close()
    return bytes(stdout_buffer), first_stderr + bytes(stderr_buffer), int(pidfd_returncode)


def _same_uid_admission_probe(host_pid: int) -> dict[str, object]:
    """Probe proc/root/fd and namespace access from the invoking UID."""

    checks: dict[str, dict[str, object]] = {}

    def record(name: str, action: Any) -> None:
        try:
            value = action()
            checks[name] = {"accessible": True, "value": value}
        except OSError as exc:
            checks[name] = {
                "accessible": False,
                "errno": exc.errno,
                "error": exc.strerror or str(exc),
            }

    record("proc_root", lambda: os.stat(f"/proc/{host_pid}/root").st_ino)
    record("proc_fd", lambda: tuple(sorted(os.listdir(f"/proc/{host_pid}/fd"))))
    for namespace in ("user", "pid", "mnt"):
        path = f"/proc/{host_pid}/ns/{namespace}"

        def probe_setns(path: str = path) -> dict[str, object]:
            fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
            try:
                child = os.fork()
                if child == 0:
                    libc = ctypes.CDLL(None, use_errno=True)
                    setns = libc.setns
                    setns.argtypes = [ctypes.c_int, ctypes.c_int]
                    setns.restype = ctypes.c_int
                    os._exit(0 if setns(fd, 0) == 0 else 1)
                _, status = os.waitpid(child, 0)
                return {
                    "fd_opened": True,
                    "setns_succeeded": os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0,
                }
            finally:
                os.close(fd)

        record(f"setns_{namespace}", probe_setns)

    violations: list[str] = []
    for name, value in checks.items():
        nested = value.get("value")
        if value.get("accessible") is True or (
            isinstance(nested, dict) and nested.get("fd_opened") is True
        ):
            violations.append(name)
    return {"checks": checks, "supported": not violations, "violations": violations}


def _export(
    spec: Any,
    *,
    stdout: bytes,
    stderr: bytes,
    receipt: Mapping[str, object],
    result: Mapping[str, object],
) -> None:
    root = spec.export_root
    if root is None:
        return
    root = Path(root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        (root / "stdout.log").write_bytes(stdout)
        (root / "stderr.log").write_bytes(stderr)
        (root / "invocation-receipt.json").write_text(
            json.dumps({**result, "receipt": receipt}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ExportError(f"explicit export failed at {root}: {exc}") from exc


def _print_stream(stream: Any, payload: bytes) -> None:
    if not payload:
        return
    try:
        stream.buffer.write(payload)
        stream.buffer.flush()
    except AttributeError:
        stream.write(payload.decode("utf-8", errors="replace"))
        stream.flush()


def run_contained(spec: Any, *, result_factory: Any | None = None):
    if result_factory is None:
        try:
            from contained_invocation import ContainmentResult  # type: ignore
        except ImportError as exc:
            raise RuntimeError("result_factory is required when launcher is loaded directly") from exc
        result_factory = ContainmentResult

    try:
        admission = _validate_spec(spec)
    except AdmissionError as exc:
        result = result_factory(
            status="containment_unsupported",
            returncode=STATUS_CODES["containment_unsupported"],
            command_started=False,
            diagnostics=[{"code": str(exc), "command_started": False}],
        )
        print(json.dumps({"status": result.status, "reason": str(exc), "command_started": False}), file=sys.stderr)
        return result

    invocation_id = hashlib.sha256(
        _json_bytes(
            {
                "profile_digest": admission["profile_digest"],
                "pid": os.getpid(),
                "time_ns": time.time_ns(),
            }
        )
    ).hexdigest()[:32]
    command = _build_command(admission, spec)
    try:
        pidfd: int | None = None
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
        try:
            pidfd = os.pidfd_open(process.pid)
            host_identity = {
                "pid": process.pid,
                "starttime": _read_starttime(process.pid),
                "pidfd": True,
                "authority": "pidfd+starttime",
                "numeric_pid_authority": False,
            }
            first_stderr = _read_line_fd(process.stderr.fileno()) if process.stderr is not None else b""
            namespace_init_host_identity = _host_namespace_init_identity(process.pid)
            host_identity["namespace_init_host_identity"] = namespace_init_host_identity
            same_uid: dict[str, object] = {
                "checks": {},
                "supported": False,
                "violations": [
                    "host_starttime_missing"
                    if host_identity["starttime"] is None
                    else "namespace_init_host_identity_missing"
                ],
                "target": namespace_init_host_identity,
            }
            admission_byte = b""
            if (
                first_stderr.startswith(READY_PREFIX.encode())
                and host_identity["starttime"] is not None
                and namespace_init_host_identity is not None
            ):
                try:
                    same_uid = _same_uid_admission_probe(
                        int(namespace_init_host_identity["pid"])
                    )
                    same_uid["target"] = namespace_init_host_identity
                except (OSError, RuntimeError) as exc:
                    same_uid = {
                        "checks": {},
                        "supported": False,
                        "violations": [f"probe_error:{type(exc).__name__}:{exc}"],
                        "target": namespace_init_host_identity,
                    }
                if same_uid.get("supported") is True:
                    admission_byte = b"R"
            else:
                admission_byte = b""
            stdout, stderr, returncode = _collect_by_pidfd(
                process,
                pidfd,
                first_stderr=first_stderr,
                admission_byte=admission_byte,
            )
            process.returncode = returncode
        finally:
            if pidfd is not None:
                os.close(pidfd)
    except (OSError, subprocess.SubprocessError) as exc:
        result = result_factory(
            status="infrastructure_failure",
            returncode=STATUS_CODES["infrastructure_failure"],
            command_started=False,
            diagnostics=[{"code": "backend_launch_failed", "message": str(exc)}],
        )
        print(json.dumps({"status": result.status, "reason": str(exc), "command_started": False}), file=sys.stderr)
        return result

    receipt, visible_stderr = _read_receipt(stderr)
    visible_stdout = stdout
    _print_stream(sys.stdout, visible_stdout)
    _print_stream(sys.stderr, visible_stderr)
    if receipt is None:
        ready_seen = first_stderr.startswith(READY_PREFIX.encode())
        status = "infrastructure_failure" if ready_seen else "containment_unsupported"
        code = STATUS_CODES[status]
        command_started = ready_seen
        result = result_factory(
            status=status,
            returncode=code,
            command_started=command_started,
            diagnostics=[{"code": "missing_namespace_receipt", "command_started": command_started}],
            export_root=str(spec.export_root) if spec.export_root else None,
        )
        print(
            json.dumps(
                {
                    "status": result.status,
                    "reason": "missing_namespace_receipt",
                    "command_started": command_started,
                }
            ),
            file=sys.stderr,
        )
        return result

    status = str(receipt.get("status", "infrastructure_failure"))
    command_started = bool(receipt.get("command_started", False))
    result_payload = {
        "schema_version": "abyss-stack-process-containment-v1",
        "status": status,
        "invocation_id": invocation_id,
        "profile_digest": admission["profile_digest"],
        "command_digest": admission["command_digest"],
        "environment_digest": admission["environment_digest"],
        "host_boot_id": admission["host_boot_id"],
        "backend": {
            "name": "bubblewrap",
            "version": admission["bwrap_version"],
            "digest": admission["backend_digest"],
        },
        "host_identity": host_identity,
        "command_started": command_started,
        "same_uid_admission": same_uid,
        "source_runtime_roots": admission["roots"],
        "receipt": receipt,
    }
    try:
        _export(spec, stdout=visible_stdout, stderr=visible_stderr, receipt=receipt, result=result_payload)
    except ExportError as exc:
        root = Path(spec.export_root) if spec.export_root else None
        if root is not None:
            try:
                root.mkdir(parents=True, exist_ok=True)
                (root / "recovery-required.json").write_text(
                    json.dumps(
                        {
                            "schema_version": "abyss-stack-process-containment-recovery-v1",
                            "status": "recovery_required",
                            "reason": str(exc),
                            "invocation": result_payload,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
        result_payload["status"] = "recovery_required"
        result_payload["diagnostic"] = str(exc)
        result_payload["recovery_lease"] = {
            "status": "recovery_required",
            "owner_controlled": True,
            "export_root": str(spec.export_root) if spec.export_root else None,
            "namespace_teardown_complete": True,
            "hidden_residue": receipt.get("hidden_residue", []),
            "manual_action": "owner-retry-explicit-export",
        }
        status = "recovery_required"
        returncode = STATUS_CODES["recovery_required"]

    result = result_factory(
        status=status,
        returncode=returncode,
        command_started=command_started,
        receipt=result_payload,
        diagnostics=[] if status == "completed" else [{"code": status}],
        export_root=str(spec.export_root) if spec.export_root else None,
    )
    print(json.dumps({"status": status, "invocation_id": invocation_id, "returncode": returncode}), file=sys.stderr)
    return result


if __name__ == "__main__":
    raise SystemExit(_namespace_init(sys.argv[1:]))
