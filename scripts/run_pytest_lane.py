#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any

import pytest


_FD_RELATIVE_SUPPORT_FUNCTIONS = (
    os.open,
    os.mkdir,
    os.stat,
    os.unlink,
    os.rmdir,
)
_FD_SUPPORT_FUNCTIONS = (os.listdir,)
REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_ENV = "ABYSS_STACK_TEST_SCHEDULER"
PROCESS_WORKER_LIMIT = 4
PROCESS_SHARD_COUNT = 32
SCHEDULERS = ("auto", "serial", "process-4x32-file-aware")

# These conservative weights came from repeated complete-suite trials. They
# affect queue order only: collection, partition membership, and the exact
# final union proof are independent of every hint. Stale hints can therefore
# cost time but cannot hide or add a test.
TEST_DURATION_HINTS = {
    "mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py": 1.5,
    "mechanics/governed-execution/parts/agent-os-adapter/tests/test_agent_os_runtime_bridge.py": 2.5,
    "mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_projection.py": 2.0,
    "mechanics/inference-pilots/parts/tos-foundation-lab/tests/test_tos_foundation_lab.py": 1.0,
    "mcp/services/abyss-stack-mcp/tests/test_canary.py": 1.0,
    "mechanics/governed-execution/parts/governed-runner/tests/test_governed_runner_review_packets.py": 0.7,
    "tests/test_runtime_lifecycle_user_unit.py": 0.5,
    "mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_runtime_install.py": 0.5,
}
DEFAULT_DURATION_HINT = 0.01

PARTITION_MODE_ENV = "ABYSS_STACK_PYTEST_PARTITION_MODE"
PARTITION_BASELINE_ENV = "ABYSS_STACK_PYTEST_PARTITION_BASELINE"
PARTITION_ASSIGNMENT_ENV = "ABYSS_STACK_PYTEST_PARTITION_ASSIGNMENT"
PARTITION_OBSERVED_ENV = "ABYSS_STACK_PYTEST_PARTITION_OBSERVED"
PARTITION_RESULT_ENV = "ABYSS_STACK_PYTEST_PARTITION_RESULT"
PARTITION_MANIFEST_SCHEMA = "abyss-stack-pytest-partition-manifest-v1"
PARTITION_RESULT_SCHEMA = "abyss-stack-pytest-partition-result-v1"
PYTEST_TEMP_ROOT_ENV = "PYTEST_DEBUG_TEMPROOT"
PYTEST_TEMP_PARENT_ENV = "TMPDIR"
PYTEST_TEMP_PREFIX = "abyss-stack-pytest-invocation-"
PYTEST_TEMP_BASETEMP_NAME = "pytest-basetemp"
PYTEST_TEMP_CLEANUP_ATTEMPTS = 3
PYTEST_TEMP_CLEANUP_RETRY_DELAY_SECONDS = 0.05
PYTEST_TEMP_CLEANUP_DIAGNOSTIC_SCHEMA = (
    "abyss-stack-pytest-temp-cleanup-diagnostic-v1"
)
PYTEST_TEMP_CLEANUP_FAILURE_EXIT_CODE = 3
PYTEST_TEMP_CREATION_FAILURE_EXIT_CODE = 2
PYTEST_TEMP_NAME_ATTEMPTS = max(100, int(getattr(tempfile, "TMP_MAX", 100)))


def nodeid_digest(nodeids: list[str]) -> str:
    payload = "\0".join(nodeids).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_manifest(path: Path, nodeids: list[str]) -> None:
    payload = {
        "schema_version": PARTITION_MANIFEST_SCHEMA,
        "count": len(nodeids),
        "digest": nodeid_digest(nodeids),
        "nodeids": nodeids,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def read_manifest(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != PARTITION_MANIFEST_SCHEMA:
        raise ValueError(f"unsupported pytest partition manifest: {path}")
    nodeids = payload.get("nodeids")
    if not isinstance(nodeids, list) or not all(isinstance(item, str) for item in nodeids):
        raise ValueError(f"invalid pytest partition nodeids: {path}")
    if payload.get("count") != len(nodeids):
        raise ValueError(f"pytest partition count mismatch: {path}")
    if payload.get("digest") != nodeid_digest(nodeids):
        raise ValueError(f"pytest partition digest mismatch: {path}")
    if len(nodeids) != len(set(nodeids)):
        raise ValueError(f"duplicate pytest nodeids are not schedulable: {path}")
    return nodeids


def _manifest_path_from_env(name: str) -> Path:
    raw = os.environ.get(name)
    if not raw:
        raise pytest.UsageError(f"missing ${name} for bounded pytest partition")
    return Path(raw)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    mode = os.environ.get(PARTITION_MODE_ENV)
    if not mode:
        return

    nodeids = [item.nodeid for item in items]
    if len(nodeids) != len(set(nodeids)):
        raise pytest.UsageError("duplicate pytest nodeids cannot form an exact partition")

    if mode == "collect":
        write_manifest(_manifest_path_from_env(PARTITION_BASELINE_ENV), nodeids)
        return
    if mode != "shard":
        raise pytest.UsageError(f"unknown bounded pytest partition mode: {mode!r}")

    baseline = read_manifest(_manifest_path_from_env(PARTITION_BASELINE_ENV))
    assignment = read_manifest(_manifest_path_from_env(PARTITION_ASSIGNMENT_ENV))
    if not assignment or not set(assignment).issubset(set(baseline)):
        raise pytest.UsageError("pytest shard assignment is empty or outside the baseline")
    if len(nodeids) != len(assignment) or set(nodeids) != set(assignment):
        raise pytest.UsageError(
            "pytest shard did not collect its explicit assignment exactly once"
        )
    write_manifest(
        _manifest_path_from_env(PARTITION_OBSERVED_ENV),
        nodeids,
    )


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
    if os.environ.get(PARTITION_MODE_ENV) != "shard":
        return
    result_path = _manifest_path_from_env(PARTITION_RESULT_ENV)
    terminal = session.config.pluginmanager.getplugin("terminalreporter")
    stats: dict[str, int] = {}
    if terminal is not None:
        stats = {
            str(key): len(value)
            for key, value in terminal.stats.items()
            if str(key) and isinstance(value, list)
        }
    payload = {
        "schema_version": PARTITION_RESULT_SCHEMA,
        "exitstatus": int(exitstatus),
        "stats": stats,
    }
    result_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def scheduler_plan(requested: str) -> dict[str, Any]:
    if requested not in SCHEDULERS:
        return {
            "ok": False,
            "requested": requested,
            "effective": None,
            "reason": "unknown_scheduler",
            "error": f"unknown scheduler {requested!r}; expected one of {', '.join(SCHEDULERS)}",
        }
    if requested == "serial":
        return {
            "ok": True,
            "requested": requested,
            "effective": "serial",
            "reason": "explicit_serial_rollback",
            "selection_changed": False,
        }
    return {
        "ok": True,
        "requested": requested,
        "effective": "process-4x32-file-aware",
        "reason": "isolated_process_workstealing",
        "worker_limit": PROCESS_WORKER_LIMIT,
        "shard_count": PROCESS_SHARD_COUNT,
        "ordering": "file_aware_duration_hints",
        "selection_proof": "baseline_manifest_exact_union",
        "selection_changed": False,
    }


def _pytest_temp_candidates(parent: Path | None) -> Iterator[Path | None]:
    if parent is not None:
        yield parent
        return

    seen: set[str] = set()
    for environment_name in (PYTEST_TEMP_ROOT_ENV, PYTEST_TEMP_PARENT_ENV):
        raw = os.environ.get(environment_name)
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        key = os.fspath(candidate)
        if key in seen:
            continue
        seen.add(key)
        yield candidate
    yield None


@dataclass(frozen=True)
class _ObjectIdentity:
    device: int
    inode: int
    file_type: int

    @classmethod
    def from_stat(cls, result: os.stat_result) -> _ObjectIdentity:
        return cls(result.st_dev, result.st_ino, stat.S_IFMT(result.st_mode))

    def describe(self) -> str:
        return f"dev={self.device} ino={self.inode} type={self.file_type:o}"


@dataclass(frozen=True)
class _PytestTempNamespaceBinding:
    display_path: Path
    name: str
    parent_fd: int
    parent_identity: _ObjectIdentity
    namespace_fd: int
    namespace_identity: _ObjectIdentity


@dataclass
class _PytestTempNamespaceHandle:
    binding: _PytestTempNamespaceBinding
    removed: bool = False
    _closed_fds: set[int] = field(default_factory=set)

    @property
    def path(self) -> Path:
        return self.binding.display_path

    @property
    def basetemp_path(self) -> Path:
        """Path handed to pytest; pytest may replace this child directory."""
        return self.path / PYTEST_TEMP_BASETEMP_NAME

    @property
    def name(self) -> str:
        return self.binding.name

    @property
    def parent_fd(self) -> int:
        return self.binding.parent_fd

    @property
    def namespace_fd(self) -> int:
        return self.binding.namespace_fd

    @property
    def parent_identity(self) -> _ObjectIdentity:
        return self.binding.parent_identity

    @property
    def namespace_identity(self) -> _ObjectIdentity:
        return self.binding.namespace_identity

    def close(self) -> tuple[str, ...]:
        errors: list[str] = []
        for descriptor in (self.namespace_fd, self.parent_fd):
            if descriptor in self._closed_fds:
                continue
            try:
                os.close(descriptor)
            except OSError as exc:
                errors.append(f"fd={descriptor}: {type(exc).__name__}: {exc}")
            finally:
                self._closed_fds.add(descriptor)
        return tuple(errors)


class PytestTempNamespaceCreationError(OSError):
    """All bounded temporary-parent candidates were unusable."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = tuple(failures)
        super().__init__(
            "unable to create an owner-owned pytest temporary namespace after "
            "trying all candidates: "
            + "; ".join(failures)
        )


class PytestTempNamespaceSupportError(OSError):
    """The platform cannot provide the required fd-relative no-follow ABI."""


def _supports_dir_fd(function: Any) -> bool:
    return function in getattr(os, "supports_dir_fd", ())


def _supports_fd(function: Any) -> bool:
    return function in getattr(os, "supports_fd", ())


def _require_fd_relative_support() -> None:
    missing = [
        function.__name__
        for function in _FD_RELATIVE_SUPPORT_FUNCTIONS
        if not _supports_dir_fd(function)
    ]
    missing_flags = [
        name
        for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_PATH")
        if not hasattr(os, name)
    ]
    missing_fd = [
        function.__name__
        for function in _FD_SUPPORT_FUNCTIONS
        if not _supports_fd(function)
    ]
    if missing or missing_fd or missing_flags:
        details = []
        if missing:
            details.append("dir_fd=" + ",".join(missing))
        if missing_fd:
            details.append("fd=" + ",".join(missing_fd))
        if missing_flags:
            details.append("flags=" + ",".join(missing_flags))
        raise PytestTempNamespaceSupportError(
            "fd-anchored pytest namespace lifecycle is unsupported: "
            + "; ".join(details)
        )


def _cloexec_flag() -> int:
    return getattr(os, "O_CLOEXEC", 0)


def _directory_open_flags() -> int:
    _require_fd_relative_support()
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | _cloexec_flag()


def _identity_matches(
    observed: _ObjectIdentity,
    expected: _ObjectIdentity,
) -> bool:
    return observed == expected


def _require_identity(
    observed: _ObjectIdentity,
    expected: _ObjectIdentity,
    *,
    subject: str,
) -> None:
    if not _identity_matches(observed, expected):
        raise OSError(
            f"pytest cleanup {subject} identity changed: "
            f"expected={expected.describe()} observed={observed.describe()}"
        )


def _stat_entry(parent_fd: int, name: str) -> os.stat_result:
    return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)


def _require_entry(
    parent_fd: int,
    name: str,
    expected: _ObjectIdentity,
) -> os.stat_result:
    observed = _stat_entry(parent_fd, name)
    _require_identity(
        _ObjectIdentity.from_stat(observed),
        expected,
        subject=f"entry {name!r}",
    )
    if expected.file_type != stat.S_IFMT(observed.st_mode):
        raise OSError(f"pytest cleanup entry type changed: {name!r}")
    return observed


def _assert_entry_absent(parent_fd: int, name: str) -> None:
    try:
        _stat_entry(parent_fd, name)
    except FileNotFoundError:
        return
    raise OSError(f"pytest cleanup entry remained after removal: {name!r}")


def _candidate_path(candidate: Path | None) -> Path:
    raw = tempfile.gettempdir() if candidate is None else candidate
    return Path(raw).expanduser().absolute()


def _open_candidate_parent(candidate: Path | None) -> tuple[int, Path, _ObjectIdentity]:
    display_path = _candidate_path(candidate)
    descriptor = os.open(
        os.fspath(display_path),
        _directory_open_flags(),
    )
    try:
        observed = os.fstat(descriptor)
        identity = _ObjectIdentity.from_stat(observed)
        if not stat.S_ISDIR(observed.st_mode):
            raise NotADirectoryError(os.fspath(display_path))
        return descriptor, display_path, identity
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _new_namespace_name(parent_fd: int) -> str:
    names = tempfile._get_candidate_names()
    for _ in range(PYTEST_TEMP_NAME_ATTEMPTS):
        name = f"{PYTEST_TEMP_PREFIX}{next(names)}"
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        return name
    raise FileExistsError(
        f"unable to allocate a unique {PYTEST_TEMP_PREFIX!r} name"
    )


def _create_namespace_in_candidate(
    candidate: Path | None,
) -> _PytestTempNamespaceHandle:
    parent_fd, parent_path, parent_identity = _open_candidate_parent(candidate)
    namespace_fd: int | None = None
    name: str | None = None
    created_identity: _ObjectIdentity | None = None
    handle: _PytestTempNamespaceHandle | None = None
    try:
        name = _new_namespace_name(parent_fd)
        created_stat = _require_entry(
            parent_fd,
            name,
            _ObjectIdentity.from_stat(_stat_entry(parent_fd, name)),
        )
        created_identity = _ObjectIdentity.from_stat(created_stat)
        if not stat.S_ISDIR(created_stat.st_mode):
            raise NotADirectoryError(name)
        namespace_fd = os.open(
            name,
            _directory_open_flags(),
            dir_fd=parent_fd,
        )
        namespace_stat = os.fstat(namespace_fd)
        namespace_identity = _ObjectIdentity.from_stat(namespace_stat)
        _require_identity(
            namespace_identity,
            created_identity,
            subject=f"created namespace {name!r}",
        )
        if not stat.S_ISDIR(namespace_stat.st_mode):
            raise NotADirectoryError(name)
        handle = _PytestTempNamespaceHandle(
            _PytestTempNamespaceBinding(
                display_path=parent_path / name,
                name=name,
                parent_fd=parent_fd,
                parent_identity=parent_identity,
                namespace_fd=namespace_fd,
                namespace_identity=namespace_identity,
            )
        )
        return handle
    except BaseException:
        if namespace_fd is not None:
            try:
                os.close(namespace_fd)
            except OSError:
                pass
        if name is not None and created_identity is not None:
            try:
                _require_entry(parent_fd, name, created_identity)
                os.rmdir(name, dir_fd=parent_fd)
            except OSError:
                pass
        raise
    finally:
        if handle is None:
            try:
                os.close(parent_fd)
            except OSError:
                pass


def _pytest_temp_directory(
    parent: Path | None = None,
) -> _PytestTempNamespaceHandle:
    try:
        _require_fd_relative_support()
    except OSError as exc:
        raise PytestTempNamespaceCreationError([str(exc)]) from exc

    failures: list[str] = []
    last_error: OSError | ValueError | None = None
    for candidate in _pytest_temp_candidates(parent):
        label = "<default tempfile>" if candidate is None else str(candidate)
        try:
            return _create_namespace_in_candidate(candidate)
        except (OSError, ValueError) as exc:
            last_error = exc
            failures.append(f"{label}: {type(exc).__name__}: {exc}")

    error = PytestTempNamespaceCreationError(failures)
    if last_error is None:
        raise error
    raise error from last_error


def _assert_parent_anchor(handle: _PytestTempNamespaceHandle) -> None:
    observed = os.fstat(handle.parent_fd)
    identity = _ObjectIdentity.from_stat(observed)
    if not stat.S_ISDIR(observed.st_mode):
        raise NotADirectoryError("retained pytest temporary parent fd")
    _require_identity(identity, handle.parent_identity, subject="parent fd")


def _assert_namespace_fd(handle: _PytestTempNamespaceHandle) -> os.stat_result:
    observed = os.fstat(handle.namespace_fd)
    identity = _ObjectIdentity.from_stat(observed)
    _require_identity(identity, handle.namespace_identity, subject="namespace fd")
    if not stat.S_ISDIR(observed.st_mode):
        raise NotADirectoryError("retained pytest namespace fd")
    return observed


def _safe_named_chmod_supported() -> bool:
    return os.chmod in getattr(os, "supports_dir_fd", ()) and os.chmod in getattr(
        os,
        "supports_follow_symlinks",
        (),
    )


def _safe_proc_fd_chmod_supported() -> bool:
    return (
        sys.platform.startswith("linux")
        and hasattr(os, "O_PATH")
        and hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
        and Path("/proc/self/fd").is_dir()
    )


def _chmod_open_directory_fd(
    descriptor: int,
    mode: int,
    *,
    force_proc: bool = False,
    parent_fd: int | None = None,
    name: str | None = None,
    expected: _ObjectIdentity | None = None,
) -> None:
    target_mode = mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
    fchmod = getattr(os, "fchmod", None)
    if fchmod is not None and not force_proc:
        fchmod(descriptor, target_mode)
    elif (
        parent_fd is not None
        and name is not None
        and expected is not None
        and _safe_named_chmod_supported()
    ):
        os.chmod(
            name,
            target_mode,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    elif _safe_proc_fd_chmod_supported():
        os.chmod(f"/proc/self/fd/{descriptor}", target_mode)
    else:
        raise PytestTempNamespaceSupportError(
            "no safe no-follow directory permission repair is available"
        )

    after = _ObjectIdentity.from_stat(os.fstat(descriptor))
    if expected is not None:
        _require_identity(after, expected, subject=f"directory {name!r}")


def _make_owned_directory_writable(
    parent_fd: int,
    name: str,
    expected: _ObjectIdentity,
) -> None:
    """Repair only a checked directory entry without following its name."""
    before = _require_entry(parent_fd, name, expected)
    if not stat.S_ISDIR(before.st_mode):
        raise NotADirectoryError(name)

    flags = _directory_open_flags()
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EPERM):
                raise
            if _safe_named_chmod_supported():
                os.chmod(
                    name,
                    before.st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                _require_entry(parent_fd, name, expected)
                return
            if not _safe_proc_fd_chmod_supported():
                raise PytestTempNamespaceSupportError(
                    "mode-000 directory cannot be repaired with a safe "
                    "no-follow operation on this platform"
                ) from exc
            path_flags = (
                os.O_PATH
                | os.O_DIRECTORY
                | os.O_NOFOLLOW
                | _cloexec_flag()
            )
            path_descriptor = os.open(
                name,
                path_flags,
                dir_fd=parent_fd,
            )
            try:
                path_stat = os.fstat(path_descriptor)
                path_identity = _ObjectIdentity.from_stat(path_stat)
                _require_identity(path_identity, expected, subject=f"directory {name!r}")
                if not stat.S_ISDIR(path_stat.st_mode):
                    raise NotADirectoryError(name)
                _chmod_open_directory_fd(
                    path_descriptor,
                    path_stat.st_mode,
                    force_proc=True,
                )
                _require_entry(parent_fd, name, expected)
            finally:
                try:
                    os.close(path_descriptor)
                except OSError:
                    pass
            return

        observed = os.fstat(descriptor)
        identity = _ObjectIdentity.from_stat(observed)
        _require_identity(identity, expected, subject=f"directory {name!r}")
        if not stat.S_ISDIR(observed.st_mode):
            raise NotADirectoryError(name)
        if not all(
            observed.st_mode & bit
            for bit in (stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR)
        ):
            _chmod_open_directory_fd(
                descriptor,
                observed.st_mode,
                parent_fd=parent_fd,
                name=name,
                expected=expected,
            )
            _require_entry(parent_fd, name, expected)
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _open_checked_directory(
    parent_fd: int,
    name: str,
    expected: _ObjectIdentity,
) -> int:
    flags = _directory_open_flags()
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno not in (errno.EACCES, errno.EPERM):
            raise
        _make_owned_directory_writable(parent_fd, name, expected)
        descriptor = os.open(name, flags, dir_fd=parent_fd)

    try:
        observed = os.fstat(descriptor)
        identity = _ObjectIdentity.from_stat(observed)
        _require_identity(identity, expected, subject=f"directory {name!r}")
        if not stat.S_ISDIR(observed.st_mode):
            raise NotADirectoryError(name)
        if not all(
            observed.st_mode & bit
            for bit in (stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR)
        ):
            os.close(descriptor)
            descriptor = -1
            _make_owned_directory_writable(parent_fd, name, expected)
            return _open_checked_directory(parent_fd, name, expected)
        return descriptor
    except BaseException:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _open_entry_identity(
    parent_fd: int,
    name: str,
    expected: _ObjectIdentity,
) -> int | None:
    flags = os.O_PATH | os.O_NOFOLLOW | _cloexec_flag()
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    try:
        observed = os.fstat(descriptor)
        _require_identity(
            _ObjectIdentity.from_stat(observed),
            expected,
            subject=f"entry {name!r}",
        )
        return descriptor
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _remove_directory_contents(directory_fd: int) -> None:
    for name in os.listdir(directory_fd):
        observed = _stat_entry(directory_fd, name)
        expected = _ObjectIdentity.from_stat(observed)
        if stat.S_ISDIR(observed.st_mode):
            child_fd = _open_checked_directory(directory_fd, name, expected)
            try:
                _remove_directory_contents(child_fd)
                child_stat = os.fstat(child_fd)
                _require_identity(
                    _ObjectIdentity.from_stat(child_stat),
                    expected,
                    subject=f"directory {name!r}",
                )
                _require_entry(directory_fd, name, expected)
                os.rmdir(name, dir_fd=directory_fd)
                _assert_entry_absent(directory_fd, name)
            finally:
                try:
                    os.close(child_fd)
                except OSError:
                    pass
            continue

        entry_fd = _open_entry_identity(directory_fd, name, expected)
        try:
            _require_entry(directory_fd, name, expected)
            os.unlink(name, dir_fd=directory_fd)
            _assert_entry_absent(directory_fd, name)
        finally:
            if entry_fd is not None:
                try:
                    os.close(entry_fd)
                except OSError:
                    pass


def _remove_owned_namespace(handle: _PytestTempNamespaceHandle) -> None:
    _assert_parent_anchor(handle)
    root_stat = _assert_namespace_fd(handle)
    _require_entry(handle.parent_fd, handle.name, handle.namespace_identity)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise NotADirectoryError(handle.name)
    if not all(
        root_stat.st_mode & bit
        for bit in (stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR)
    ):
        if getattr(os, "fchmod", None) is None:
            _chmod_open_directory_fd(
                handle.namespace_fd,
                root_stat.st_mode,
                parent_fd=handle.parent_fd,
                name=handle.name,
                expected=handle.namespace_identity,
            )
        else:
            os.fchmod(
                handle.namespace_fd,
                root_stat.st_mode
                | stat.S_IRUSR
                | stat.S_IWUSR
                | stat.S_IXUSR,
            )
    _remove_directory_contents(handle.namespace_fd)
    _assert_namespace_fd(handle)
    _require_entry(handle.parent_fd, handle.name, handle.namespace_identity)
    os.rmdir(handle.name, dir_fd=handle.parent_fd)
    _assert_entry_absent(handle.parent_fd, handle.name)
    handle.removed = True


def _namespace_still_owned(handle: _PytestTempNamespaceHandle) -> bool:
    try:
        _require_entry(handle.parent_fd, handle.name, handle.namespace_identity)
    except FileNotFoundError:
        handle.removed = True
        return False
    return True


def _cleanup_diagnostic_path(namespace: Path) -> Path:
    return namespace.with_name(f".{namespace.name}.cleanup-failed.json")


def _unlink_created_diagnostic(
    handle: _PytestTempNamespaceHandle,
    name: str,
    expected: _ObjectIdentity,
) -> bool:
    try:
        observed = _stat_entry(handle.parent_fd, name)
    except FileNotFoundError:
        return True
    actual = _ObjectIdentity.from_stat(observed)
    if actual != expected or not stat.S_ISREG(observed.st_mode):
        print(
            "[pytest-temp-cleanup-diagnostic-failed] "
            f"refusing to remove changed diagnostic name={name!r}",
            file=sys.stderr,
            flush=True,
        )
        return False
    try:
        os.unlink(name, dir_fd=handle.parent_fd)
        _assert_entry_absent(handle.parent_fd, name)
    except OSError as exc:
        print(
            "[pytest-temp-cleanup-diagnostic-failed] "
            f"unable to remove partial diagnostic name={name!r} error={exc!r}",
            file=sys.stderr,
            flush=True,
        )
        return False
    return True


def _write_cleanup_diagnostic(
    handle: _PytestTempNamespaceHandle,
    failures: list[dict[str, str]],
) -> Path | None:
    diagnostic = _cleanup_diagnostic_path(handle.path)
    name = diagnostic.name
    payload = {
        "schema_version": PYTEST_TEMP_CLEANUP_DIAGNOSTIC_SCHEMA,
        "status": "cleanup_failed",
        "namespace": str(handle.path),
        "parent": str(handle.path.parent),
        "attempts": len(failures),
        "failures": failures,
    }
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _cloexec_flag()
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_BINARY", 0)
    descriptor: int | None = None
    diagnostic_identity: _ObjectIdentity | None = None
    error: BaseException | None = None
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=handle.parent_fd)
        diagnostic_identity = _ObjectIdentity.from_stat(os.fstat(descriptor))
        if not stat.S_ISREG(diagnostic_identity.file_type):
            raise OSError(f"cleanup diagnostic is not a regular file: {name!r}")
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("cleanup diagnostic write was incomplete")
            remaining = remaining[written:]
    except (OSError, AttributeError, NotImplementedError, TypeError, ValueError) as exc:
        error = exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except (OSError, AttributeError, NotImplementedError, TypeError, ValueError) as exc:
                if error is None:
                    error = exc
    if error is not None:
        if diagnostic_identity is not None:
            _unlink_created_diagnostic(handle, name, diagnostic_identity)
        print(
            "[pytest-temp-cleanup-diagnostic-failed] "
            f"namespace={handle.path} error={error!r}",
            file=sys.stderr,
            flush=True,
        )
        return None
    return diagnostic


@dataclass(frozen=True)
class PytestTempCleanupResult:
    namespace: Path
    ok: bool
    attempts: int
    diagnostic: Path | None = None
    errors: tuple[str, ...] = ()


class PytestTempCleanupError(RuntimeError):
    """A runner-owned pytest namespace could not be removed."""

    def __init__(self, result: PytestTempCleanupResult) -> None:
        self.result = result
        diagnostic = (
            f" diagnostic={result.diagnostic}" if result.diagnostic else ""
        )
        errors = f" errors={'; '.join(result.errors)}" if result.errors else ""
        super().__init__(
            "pytest temporary namespace cleanup failed: "
            f"namespace={result.namespace} attempts={result.attempts}"
            f"{diagnostic}{errors}"
        )


def cleanup_pytest_temp_namespace(
    handle: _PytestTempNamespaceHandle,
) -> PytestTempCleanupResult:
    """Remove one namespace through its retained owner handle."""
    failures: list[dict[str, str]] = []
    removed = handle.removed
    attempts = 0
    for attempt in range(1, PYTEST_TEMP_CLEANUP_ATTEMPTS + 1):
        attempts = attempt
        if removed:
            break
        try:
            _remove_owned_namespace(handle)
            removed = True
        except (OSError, ValueError) as exc:
            try:
                removed = not _namespace_still_owned(handle)
            except (OSError, ValueError) as state_error:
                failures.append(
                    {
                        "attempt": str(attempt),
                        "error_type": type(state_error).__name__,
                        "error": str(state_error),
                    }
                )
            failures.append(
                {
                    "attempt": str(attempt),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
        if removed:
            handle.removed = True
            break
        if attempt < PYTEST_TEMP_CLEANUP_ATTEMPTS:
            time.sleep(PYTEST_TEMP_CLEANUP_RETRY_DELAY_SECONDS)

    if removed:
        close_errors = handle.close()
        if close_errors:
            print(
                "[pytest-temp-cleanup-fd-close-failed] "
                f"namespace={handle.path} errors={'; '.join(close_errors)}",
                file=sys.stderr,
                flush=True,
            )
            return PytestTempCleanupResult(
                handle.path,
                False,
                attempts,
                errors=close_errors,
            )
        return PytestTempCleanupResult(handle.path, True, attempts)

    diagnostic = _write_cleanup_diagnostic(handle, failures)
    diagnostic_suffix = f" diagnostic={diagnostic}" if diagnostic else ""
    close_errors = handle.close()
    if close_errors:
        failures.extend(
            {
                "attempt": str(attempts),
                "error_type": "OSError",
                "error": error,
            }
            for error in close_errors
        )
    print(
        "[pytest-temp-cleanup-failed] "
        f"namespace={handle.path} attempts={len(failures)}{diagnostic_suffix}",
        file=sys.stderr,
        flush=True,
    )
    return PytestTempCleanupResult(
        handle.path,
        False,
        len(failures),
        diagnostic,
        close_errors,
    )


@contextmanager
def owned_pytest_temp_namespace(parent: Path | None = None) -> Iterator[Path]:
    """Yield pytest's child basetemp while retaining the owner directory handle."""
    handle = _pytest_temp_directory(parent)
    body_failed = False
    try:
        yield handle.basetemp_path
    except BaseException:
        body_failed = True
        raise
    finally:
        cleanup = cleanup_pytest_temp_namespace(handle)
        if not cleanup.ok and not body_failed:
            raise PytestTempCleanupError(cleanup)


def _assert_no_static_basetemp(args: list[str]) -> None:
    if any(arg == "--basetemp" or arg.startswith("--basetemp=") for arg in args):
        raise ValueError(
            "run_pytest_lane allocates a fresh --basetemp for each invocation"
        )


def build_pytest_command(*, extra_args: list[str], basetemp: Path) -> list[str]:
    _assert_no_static_basetemp(extra_args)
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--basetemp",
        str(basetemp),
        *extra_args,
    ]


def partition_nodeids(nodeids: list[str], *, shard_count: int) -> list[list[str]]:
    if not nodeids:
        return []
    effective_count = min(shard_count, len(nodeids))
    target_items = (len(nodeids) + effective_count - 1) // effective_count
    by_file: dict[str, list[str]] = {}
    for nodeid in nodeids:
        by_file.setdefault(nodeid.split("::", 1)[0], []).append(nodeid)

    units: list[list[str]] = []
    for file_nodeids in by_file.values():
        unit_count = (
            effective_count
            if len(by_file) == 1
            else (len(file_nodeids) + target_items - 1) // target_items
        )
        if unit_count == 1:
            units.append(file_nodeids)
            continue
        ranked = sorted(
            file_nodeids,
            key=lambda nodeid: (
                hashlib.sha256(nodeid.encode("utf-8")).digest(),
                nodeid,
            ),
        )
        ownership = {
            nodeid: position % unit_count for position, nodeid in enumerate(ranked)
        }
        units.extend(
            [
                nodeid
                for nodeid in file_nodeids
                if ownership[nodeid] == unit_index
            ]
            for unit_index in range(unit_count)
        )

    partitions: list[list[str]] = [[] for _ in range(effective_count)]
    loads = [0] * effective_count
    for unit in sorted(units, key=lambda value: (-len(value), value[0])):
        destination = min(range(effective_count), key=lambda index: (loads[index], index))
        partitions[destination].extend(unit)
        loads[destination] += len(unit)
    populated = [partition for partition in partitions if partition]
    return sorted(
        populated,
        key=lambda partition: (
            -sum(
                TEST_DURATION_HINTS.get(
                    nodeid.split("::", 1)[0],
                    DEFAULT_DURATION_HINT,
                )
                for nodeid in partition
            ),
            partition[0],
        ),
    )


def _partition_environment(
    *,
    baseline_path: Path,
    assignment_path: Path | None = None,
    observed_path: Path | None = None,
    result_path: Path | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment[PARTITION_BASELINE_ENV] = str(baseline_path)
    if assignment_path is None:
        environment[PARTITION_MODE_ENV] = "collect"
        for name in (
            PARTITION_ASSIGNMENT_ENV,
            PARTITION_OBSERVED_ENV,
            PARTITION_RESULT_ENV,
        ):
            environment.pop(name, None)
        return environment
    environment[PARTITION_MODE_ENV] = "shard"
    environment[PARTITION_ASSIGNMENT_ENV] = str(assignment_path)
    environment[PARTITION_OBSERVED_ENV] = str(observed_path)
    environment[PARTITION_RESULT_ENV] = str(result_path)
    return environment


def _plugin_command(
    *,
    selection_args: list[str],
    basetemp: Path,
    collect_only: bool = False,
) -> list[str]:
    _assert_no_static_basetemp(selection_args)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--basetemp",
        str(basetemp),
        "-p",
        "scripts.run_pytest_lane",
    ]
    if collect_only:
        command.append("--collect-only")
    command.extend(selection_args)
    return command


def _read_result(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != PARTITION_RESULT_SCHEMA:
        raise ValueError(f"unsupported pytest partition result: {path}")
    if not isinstance(payload.get("exitstatus"), int) or not isinstance(
        payload.get("stats"), dict
    ):
        raise ValueError(f"invalid pytest partition result: {path}")
    return payload


def _replay_failed_shards(
    records: dict[int, dict[str, Any]],
    failed_shards: list[int],
    *,
    shard_count: int,
) -> None:
    for shard_index in failed_shards:
        record = records[shard_index]
        print(
            f"[pytest-failed-shard {shard_index + 1}/{shard_count}]",
            file=sys.stderr,
        )
        print(
            record["log"].read_text(encoding="utf-8"),
            end="",
            file=sys.stderr,
        )
        print(
            "[pytest-failed-shard-result] "
            f"index={shard_index + 1} selected={record['selected']} "
            f"returncode={record['returncode']} "
            f"selection_proof={record['selection_proof']}",
            file=sys.stderr,
            flush=True,
        )


def run_process_worksteal(*, extra_args: list[str]) -> int:
    with tempfile.TemporaryDirectory(
        prefix="abyss-stack-pytest-partitions-",
    ) as temporary_raw:
        temporary = Path(temporary_raw)
        baseline_path = temporary / "baseline.json"
        collect_log = temporary / "collect.log"
        try:
            with owned_pytest_temp_namespace() as collect_basetemp:
                collect_command = _plugin_command(
                    selection_args=extra_args,
                    basetemp=collect_basetemp,
                    collect_only=True,
                )
                collect_started = time.monotonic()
                with collect_log.open("w", encoding="utf-8") as output:
                    collected = subprocess.run(
                        collect_command,
                        cwd=REPO_ROOT,
                        env=_partition_environment(baseline_path=baseline_path),
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        text=True,
                        check=False,
                    )
                collect_elapsed = time.monotonic() - collect_started
        except PytestTempNamespaceCreationError as exc:
            print(f"[error] {exc}", file=sys.stderr, flush=True)
            return PYTEST_TEMP_CREATION_FAILURE_EXIT_CODE
        except PytestTempCleanupError as exc:
            print(f"[error] {exc}", file=sys.stderr, flush=True)
            return PYTEST_TEMP_CLEANUP_FAILURE_EXIT_CODE
        if collected.returncode != 0 or not baseline_path.is_file():
            print(collect_log.read_text(encoding="utf-8"), file=sys.stderr, end="")
            print(
                f"[error] exact pytest collection failed: returncode={collected.returncode}",
                file=sys.stderr,
            )
            return collected.returncode or 2

        try:
            baseline = read_manifest(baseline_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"[error] invalid exact pytest collection: {exc}", file=sys.stderr)
            return 2
        if not baseline:
            print("[error] exact pytest collection selected no tests", file=sys.stderr)
            return 5

        assignments = partition_nodeids(baseline, shard_count=PROCESS_SHARD_COUNT)
        flattened = [nodeid for assignment in assignments for nodeid in assignment]
        if len(flattened) != len(baseline) or set(flattened) != set(baseline):
            print("[error] pytest partition union does not equal the baseline", file=sys.stderr)
            return 2
        print(
            "[pytest-partition] "
            f"collected={len(baseline)} digest={nodeid_digest(baseline)} "
            f"shards={len(assignments)} workers={min(PROCESS_WORKER_LIMIT, len(assignments))} "
            f"collect_seconds={collect_elapsed:.2f} exact_union=true overlap=false",
            flush=True,
        )

        pending: deque[int] = deque(range(len(assignments)))
        active: dict[
            int,
            tuple[subprocess.Popen[str], Any, float, _PytestTempNamespaceHandle],
        ] = {}
        records: dict[int, dict[str, Any]] = {}
        cleanup_failed = False
        try:
            while pending or active:
                while pending and len(active) < PROCESS_WORKER_LIMIT:
                    shard_index = pending.popleft()
                    assignment_path = temporary / f"assignment-{shard_index}.json"
                    observed_path = temporary / f"observed-{shard_index}.json"
                    result_path = temporary / f"result-{shard_index}.json"
                    log_path = temporary / f"shard-{shard_index}.log"
                    write_manifest(assignment_path, assignments[shard_index])
                    temporary_namespace = _pytest_temp_directory()
                    basetemp = temporary_namespace.basetemp_path
                    output: Any = None
                    try:
                        output = log_path.open("w", encoding="utf-8")
                        command = _plugin_command(
                            selection_args=assignments[shard_index],
                            basetemp=basetemp,
                        )
                        process = subprocess.Popen(
                            command,
                            cwd=REPO_ROOT,
                            env=_partition_environment(
                                baseline_path=baseline_path,
                                assignment_path=assignment_path,
                                observed_path=observed_path,
                                result_path=result_path,
                            ),
                            stdout=output,
                            stderr=subprocess.STDOUT,
                            text=True,
                            close_fds=True,
                        )
                    except BaseException:
                        if output is not None:
                            output.close()
                        cleanup_pytest_temp_namespace(temporary_namespace)
                        raise
                    active[shard_index] = (
                        process,
                        output,
                        time.monotonic(),
                        temporary_namespace,
                    )
                    records[shard_index] = {
                        "assignment": assignment_path,
                        "observed": observed_path,
                        "result": result_path,
                        "log": log_path,
                        "command": command,
                        "basetemp": basetemp,
                    }

                completed_any = False
                for shard_index, (
                    process,
                    output,
                    started,
                    temporary_namespace,
                ) in list(active.items()):
                    returncode = process.poll()
                    if returncode is None:
                        continue
                    output.close()
                    cleanup = cleanup_pytest_temp_namespace(temporary_namespace)
                    cleanup_failed = cleanup_failed or not cleanup.ok
                    records[shard_index]["returncode"] = returncode
                    records[shard_index]["elapsed"] = time.monotonic() - started
                    records[shard_index]["cleanup"] = "passed" if cleanup.ok else "failed"
                    if cleanup.diagnostic is not None:
                        records[shard_index]["cleanup_diagnostic"] = str(
                            cleanup.diagnostic
                        )
                    del active[shard_index]
                    completed_any = True
                if not completed_any and active:
                    time.sleep(0.1)
        except BaseException:
            for process, output, _started, _temporary_namespace in active.values():
                process.terminate()
                output.close()
            for process, _output, _started, _temporary_namespace in active.values():
                process.wait()
            for (
                _process,
                _output,
                _started,
                temporary_namespace,
            ) in active.values():
                cleanup_pytest_temp_namespace(temporary_namespace)
            raise

        failed = cleanup_failed
        failed_shards: list[int] = []
        totals: Counter[str] = Counter()
        for shard_index in range(len(assignments)):
            record = records[shard_index]
            print(f"[pytest-shard {shard_index + 1}/{len(assignments)}]")
            print(record["log"].read_text(encoding="utf-8"), end="")
            try:
                observed = read_manifest(record["observed"])
                result = _read_result(record["result"])
                expected = assignments[shard_index]
                if len(observed) != len(expected) or set(observed) != set(expected):
                    raise ValueError("observed selection differs from assignment")
                if int(result["exitstatus"]) != int(record["returncode"]):
                    raise ValueError("pytest exit status differs from process return code")
                totals.update(
                    {str(key): int(value) for key, value in result["stats"].items()}
                )
                proof = "exact"
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                proof = f"invalid:{exc}"
                failed = True
            if int(record["returncode"]) != 0:
                failed = True
            record["selected"] = len(assignments[shard_index])
            record["selection_proof"] = proof
            if proof != "exact" or int(record["returncode"]) != 0:
                failed_shards.append(shard_index)
            print(
                "[pytest-shard-result] "
                f"index={shard_index + 1} selected={len(assignments[shard_index])} "
                f"returncode={record['returncode']} seconds={record['elapsed']:.2f} "
                f"selection_proof={proof} cleanup={record['cleanup']}",
                flush=True,
            )

        print(
            "[pytest-aggregate] "
            f"verdict={'failed' if failed else 'passed'} selected={len(baseline)} "
            f"shards={len(assignments)} outcomes={json.dumps(dict(sorted(totals.items())), sort_keys=True)}",
            flush=True,
        )
        _replay_failed_shards(
            records,
            failed_shards,
            shard_count=len(assignments),
        )
        return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the complete abyss-stack pytest lane with a bounded scheduler."
    )
    parser.add_argument(
        "--scheduler",
        choices=SCHEDULERS,
        default=os.environ.get(SCHEDULER_ENV, "auto"),
        help=(
            "scheduler selection; auto uses bounded process-isolated work stealing "
            f"(default: ${SCHEDULER_ENV} or auto)"
        ),
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="additional pytest arguments after --",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    extra_args = list(args.pytest_args)
    if extra_args[:1] == ["--"]:
        extra_args = extra_args[1:]
    try:
        _assert_no_static_basetemp(extra_args)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr, flush=True)
        return 2

    scheduler = scheduler_plan(args.scheduler)
    if not scheduler["ok"]:
        print(f"[error] {scheduler['error']}", file=sys.stderr, flush=True)
        return 2

    if scheduler["effective"] != "serial" and extra_args:
        if args.scheduler != "auto":
            print(
                "[error] explicit process work stealing admits only the complete "
                "default pytest selection; use serial for targeted arguments",
                file=sys.stderr,
                flush=True,
            )
            return 2
        scheduler = {
            "ok": True,
            "requested": args.scheduler,
            "effective": "serial",
            "reason": "targeted_selection_uses_exact_serial_path",
            "selection_changed": False,
        }

    print(
        "[pytest-scheduler] "
        f"requested={scheduler['requested']} effective={scheduler['effective']} "
        f"reason={scheduler['reason']} selection_changed=false",
        flush=True,
    )
    if scheduler["effective"] == "serial":
        try:
            with owned_pytest_temp_namespace() as basetemp:
                command = build_pytest_command(
                    extra_args=extra_args,
                    basetemp=basetemp,
                )
                print(f"[run] tests: {subprocess.list2cmdline(command)}", flush=True)
                completed = subprocess.run(
                    command,
                    cwd=REPO_ROOT,
                    env=os.environ.copy(),
                    check=False,
                    close_fds=True,
                )
        except PytestTempNamespaceCreationError as exc:
            print(f"[error] {exc}", file=sys.stderr, flush=True)
            return PYTEST_TEMP_CREATION_FAILURE_EXIT_CODE
        except PytestTempCleanupError as exc:
            print(f"[error] {exc}", file=sys.stderr, flush=True)
            return PYTEST_TEMP_CLEANUP_FAILURE_EXIT_CODE
        return completed.returncode
    try:
        return run_process_worksteal(extra_args=extra_args)
    except PytestTempNamespaceCreationError as exc:
        print(f"[error] {exc}", file=sys.stderr, flush=True)
        return PYTEST_TEMP_CREATION_FAILURE_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
