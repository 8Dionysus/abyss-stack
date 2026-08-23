#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
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
_RENAME_NOREPLACE = 1
_QUARANTINE_NAME_PREFIX = ".abyss-stack-pytest-quarantine-"
_QUARANTINE_ENTRY_PREFIX = ".entry-"
_DELETION_ENTRY_PREFIX = ".delete-"
_RECOVERY_ENTRY_PREFIX = ".recovered-"
_PROCESS_DRAIN_POLL_ATTEMPTS = 20
_PROCESS_DRAIN_POLL_DELAY_SECONDS = 0.01
_LIBC_RENAMEAT2: Any | None = None
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
PYTEST_ADDOPTS_ENV = "PYTEST_ADDOPTS"


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


@dataclass(frozen=True)
class _CleanupQuarantine:
    parent_fd: int
    parent_identity: _ObjectIdentity
    name: str
    identity: _ObjectIdentity


@dataclass(frozen=True)
class _QuarantinedEntry:
    parent_fd: int
    name: str
    identity: _ObjectIdentity
    descriptor: int
    recovery_parent_fd: int | None = None


@dataclass(frozen=True)
class _NamespaceLinkState:
    link_count: int
    original_identity_matches: bool
    alternate_name: str | None = None

    @property
    def is_unlinked(self) -> bool:
        return self.link_count == 0

    def describe(self, handle: _PytestTempNamespaceHandle) -> str:
        if self.is_unlinked:
            return (
                "retained pytest namespace inode is unlinked: "
                f"st_nlink={self.link_count}"
            )
        if self.original_identity_matches:
            return (
                "retained pytest namespace inode remains linked under its "
                f"original name {handle.name!r}: st_nlink={self.link_count}"
            )
        if self.alternate_name is not None:
            location = (
                "the exact dev/inode/type was observed under alternate name "
                f"{self.alternate_name!r} in the retained parent"
            )
        else:
            location = (
                "no exact entry was observed in the retained parent; the inode "
                "may have moved elsewhere or changed during lookup"
            )
        return (
            "retained pytest namespace inode remains linked after its original "
            f"name {handle.name!r} changed or disappeared: st_nlink={self.link_count}; "
            f"{location}; no race-safe fd-only directory unlink is available"
        )


@dataclass
class _PytestTempNamespaceHandle:
    binding: _PytestTempNamespaceBinding
    removed: bool = False
    _closed_fds: set[int] = field(default_factory=set)
    _cleanup_quarantine: _CleanupQuarantine | None = None
    _owner_process_groups: set[int] = field(default_factory=set)
    _owner_processes_drained: bool = False

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

    @property
    def cleanup_quarantine(self) -> _CleanupQuarantine | None:
        return self._cleanup_quarantine

    def register_owner_process_group(self, process_id: int) -> None:
        if process_id <= 0 or not hasattr(os, "killpg"):
            raise PytestTempNamespaceSupportError(
                "cannot contain an invocation-owned process group on this platform"
            )
        self._owner_process_groups.add(process_id)
        self._owner_processes_drained = False

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


class PytestTempNamespaceBusyError(OSError):
    """An invocation-owned mutator could not be contained before cleanup."""


class PytestTempNamespaceRaceError(OSError):
    """A quarantine binding changed; retries must preserve every candidate."""


def _supports_dir_fd(function: Any) -> bool:
    return function in getattr(os, "supports_dir_fd", ())


def _supports_fd(function: Any) -> bool:
    return function in getattr(os, "supports_fd", ())


def _renameat2_function() -> Any:
    global _LIBC_RENAMEAT2
    if _LIBC_RENAMEAT2 is not None:
        return _LIBC_RENAMEAT2
    if not sys.platform.startswith("linux"):
        raise PytestTempNamespaceSupportError(
            "atomic no-replace quarantine requires Linux renameat2"
        )
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        function = libc.renameat2
    except (AttributeError, OSError) as exc:
        raise PytestTempNamespaceSupportError(
            "libc does not expose atomic no-replace renameat2"
        ) from exc
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    function.restype = ctypes.c_int
    _LIBC_RENAMEAT2 = function
    return function


def _rename_noreplace(
    source_parent_fd: int,
    source_name: str,
    destination_parent_fd: int,
    destination_name: str,
) -> None:
    function = _renameat2_function()
    result = function(
        source_parent_fd,
        os.fsencode(source_name),
        destination_parent_fd,
        os.fsencode(destination_name),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(
            error_number,
            os.strerror(error_number),
            source_name,
            destination_name,
        )


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
    _renameat2_function()


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _reap_process_group_leader(process_group_id: int) -> None:
    try:
        os.waitpid(process_group_id, os.WNOHANG)
    except (ChildProcessError, OSError):
        pass


def _drain_process_group(process_group_id: int) -> None:
    if not hasattr(os, "killpg") or not hasattr(signal, "SIGTERM"):
        raise PytestTempNamespaceBusyError(
            "cannot contain an invocation-owned process group on this platform"
        )
    for termination_signal in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process_group_id, termination_signal)
        except ProcessLookupError:
            return
        for _ in range(_PROCESS_DRAIN_POLL_ATTEMPTS):
            _reap_process_group_leader(process_group_id)
            if not _process_group_exists(process_group_id):
                return
            time.sleep(_PROCESS_DRAIN_POLL_DELAY_SECONDS)
    if _process_group_exists(process_group_id):
        raise PytestTempNamespaceBusyError(
            f"invocation-owned process group {process_group_id} survived cleanup drain"
        )


def _drain_owner_processes(handle: _PytestTempNamespaceHandle) -> None:
    if handle._owner_processes_drained:
        return
    for process_group_id in tuple(handle._owner_process_groups):
        _drain_process_group(process_group_id)
    handle._owner_processes_drained = True


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


def _new_entry_name(parent_fd: int, prefix: str) -> str:
    names = tempfile._get_candidate_names()
    for _ in range(PYTEST_TEMP_NAME_ATTEMPTS):
        name = f"{prefix}{next(names)}"
        try:
            _stat_entry(parent_fd, name)
        except FileNotFoundError:
            return name
    raise FileExistsError(f"unable to allocate a unique {prefix!r} name")


def _recover_quarantined_entry(
    entry_parent_fd: int,
    entry_name: str,
    source_parent_fd: int,
    source_name: str,
    recovery_parent_fd: int | None = None,
) -> str | None:
    """Restore a raced candidate without replacing a newer source entry."""
    if recovery_parent_fd is not None and recovery_parent_fd != source_parent_fd:
        try:
            recovery_name = _new_entry_name(
                recovery_parent_fd,
                _RECOVERY_ENTRY_PREFIX,
            )
            _rename_noreplace(
                entry_parent_fd,
                entry_name,
                recovery_parent_fd,
                recovery_name,
            )
        except OSError:
            pass
        else:
            return recovery_name
    try:
        _rename_noreplace(
            entry_parent_fd,
            entry_name,
            source_parent_fd,
            source_name,
        )
        return source_name
    except FileExistsError:
        try:
            recovery_name = _new_entry_name(
                source_parent_fd,
                _RECOVERY_ENTRY_PREFIX,
            )
            _rename_noreplace(
                entry_parent_fd,
                entry_name,
                source_parent_fd,
                recovery_name,
            )
        except OSError:
            return None
        return recovery_name
    except OSError:
        return None


def _quarantine_entry(
    source_parent_fd: int,
    source_name: str,
    expected: _ObjectIdentity,
    destination_parent_fd: int,
    *,
    destination_prefix: str,
    recovery_parent_fd: int | None = None,
) -> _QuarantinedEntry:
    """Atomically move one name, then bind the moved object by identity.

    ``renameat2(RENAME_NOREPLACE)`` is the binding operation.  A destination
    collision cannot overwrite anything, and a source replacement is moved
    out of the way only long enough to be identity-checked and restored.  An
    unexpected object is never sent to a destructive helper.
    """
    for _ in range(PYTEST_TEMP_NAME_ATTEMPTS):
        destination_name = _new_entry_name(
            destination_parent_fd,
            destination_prefix,
        )
        try:
            _rename_noreplace(
                source_parent_fd,
                source_name,
                destination_parent_fd,
                destination_name,
            )
        except FileExistsError:
            continue
        try:
            descriptor = _open_entry_identity(
                destination_parent_fd,
                destination_name,
                expected,
            )
        except BaseException as exc:
            recovery_name = _recover_quarantined_entry(
                destination_parent_fd,
                destination_name,
                source_parent_fd,
                source_name,
                recovery_parent_fd,
            )
            location = (
                f" recovered_as={recovery_name!r}"
                if recovery_name is not None
                else " candidate_remains_at_quarantine_name"
            )
            raise PytestTempNamespaceRaceError(
                "pytest cleanup quarantine identity changed for "
                f"{source_name!r}; refusing to delete the candidate;{location}"
            ) from exc
        return _QuarantinedEntry(
            parent_fd=destination_parent_fd,
            name=destination_name,
            identity=expected,
            descriptor=descriptor,
            recovery_parent_fd=recovery_parent_fd,
        )
    raise FileExistsError(
        f"unable to allocate an uncontested quarantine name for {source_name!r}"
    )


def _close_entry_descriptor(entry: _QuarantinedEntry) -> None:
    try:
        os.close(entry.descriptor)
    except OSError:
        pass


def _destroy_bound_entry(
    entry: _QuarantinedEntry,
    *,
    directory: bool,
) -> None:
    """Destroy an identity-checked deletion slot under the owner boundary.

    There is no Linux/Python unlink-by-fd primitive.  The preceding
    ``renameat2(RENAME_NOREPLACE)`` is therefore the binding event; the final
    name is usable only after invocation-owned mutators have been drained and
    while its retained parent remains the authority boundary.  A post-delete
    absence check turns an unexpected concurrent reappearance into visible
    failure, never a retry against a new object.
    """
    try:
        if directory:
            os.rmdir(entry.name, dir_fd=entry.parent_fd)
        else:
            os.unlink(entry.name, dir_fd=entry.parent_fd)
        try:
            _assert_entry_absent(entry.parent_fd, entry.name)
        except (OSError, ValueError) as exc:
            raise PytestTempNamespaceRaceError(
                "pytest cleanup deletion slot remained or changed after "
                f"destruction: {entry.name!r}"
            ) from exc
    except PytestTempNamespaceRaceError:
        raise
    except (OSError, ValueError) as exc:
        raise PytestTempNamespaceRaceError(
            "pytest cleanup could not destroy its identity-bound deletion "
            f"slot: {entry.name!r}"
        ) from exc
    finally:
        _close_entry_descriptor(entry)


def _delete_quarantined_entry(
    entry: _QuarantinedEntry,
    *,
    directory: bool,
) -> None:
    """Stage then delete only a moved entry under its owner-contained parent FD.

    The parent is either the retained namespace FD after the outer namespace
    quarantine or the caller's own newly-created empty namespace during
    creation rollback.  Staging the candidate again means a replacement of
    the source quarantine name cannot become the final deletion target.  The
    final slot is still subject to the documented owner-process containment
    boundary because unlink/rmdir cannot consume a descriptor directly.
    """
    try:
        deletion_slot = _quarantine_entry(
            entry.parent_fd,
            entry.name,
            entry.identity,
            entry.parent_fd,
            destination_prefix=_DELETION_ENTRY_PREFIX,
            recovery_parent_fd=entry.recovery_parent_fd,
        )
        _destroy_bound_entry(deletion_slot, directory=directory)
    except PytestTempNamespaceRaceError:
        raise
    except (OSError, ValueError) as exc:
        raise PytestTempNamespaceRaceError(
            "pytest cleanup could not stage its quarantined entry for "
            f"identity-bound destruction: {entry.name!r}"
        ) from exc
    finally:
        _close_entry_descriptor(entry)


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
                entry = _quarantine_entry(
                    parent_fd,
                    name,
                    created_identity,
                    parent_fd,
                    destination_prefix=_QUARANTINE_ENTRY_PREFIX,
                )
                _delete_quarantined_entry(entry, directory=True)
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


@dataclass
class _DirectoryWalkFrame:
    descriptor: int | None
    identity: _ObjectIdentity
    name: str | None
    parent_fd: int | None
    recovery_parent_fd: int | None
    entries: list[str]
    index: int = 0


def _assert_walk_directory(
    frame: _DirectoryWalkFrame,
    *,
    subject: str,
) -> os.stat_result:
    if frame.descriptor is None:
        raise OSError(f"pytest cleanup lost descriptor for {subject}")
    observed = os.fstat(frame.descriptor)
    _require_identity(
        _ObjectIdentity.from_stat(observed),
        frame.identity,
        subject=subject,
    )
    if not stat.S_ISDIR(observed.st_mode):
        raise NotADirectoryError(subject)
    return observed


def _remove_directory_contents(
    directory_fd: int,
    *,
    quarantine_parent_fd: int,
    recovery_parent_fd: int | None = None,
) -> None:
    root_stat = os.fstat(directory_fd)
    root_identity = _ObjectIdentity.from_stat(root_stat)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise NotADirectoryError("pytest cleanup root")
    frames = [
        _DirectoryWalkFrame(
            descriptor=directory_fd,
            identity=root_identity,
            name=None,
            parent_fd=None,
            recovery_parent_fd=None,
            entries=os.listdir(directory_fd),
        )
    ]
    try:
        while frames:
            frame = frames[-1]
            if frame.index == len(frame.entries):
                finished = frames.pop()
                if finished.name is None:
                    continue
                if finished.descriptor is None:
                    raise OSError(
                        f"pytest cleanup lost directory fd for {finished.name!r}"
                    )
                _assert_walk_directory(
                    finished,
                    subject=f"directory {finished.name!r}",
                )
                if finished.parent_fd is None:
                    raise OSError(
                        f"pytest cleanup lost parent fd for {finished.name!r}"
                    )
                _delete_quarantined_entry(
                    _QuarantinedEntry(
                        parent_fd=finished.parent_fd,
                        name=finished.name,
                        identity=finished.identity,
                        descriptor=finished.descriptor,
                        recovery_parent_fd=finished.recovery_parent_fd,
                    ),
                    directory=True,
                )
                continue

            if frame.descriptor is None:
                raise OSError("pytest cleanup lost current directory fd")
            _assert_walk_directory(
                frame,
                subject=f"directory {frame.name!r}",
            )
            name = frame.entries[frame.index]
            frame.index += 1
            observed = _stat_entry(frame.descriptor, name)
            expected = _ObjectIdentity.from_stat(observed)
            if stat.S_ISDIR(observed.st_mode) and not all(
                observed.st_mode & bit
                for bit in (stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR)
            ):
                _make_owned_directory_writable(
                    frame.descriptor,
                    name,
                    expected,
                )
                observed = _require_entry(frame.descriptor, name, expected)
            quarantined = _quarantine_entry(
                frame.descriptor,
                name,
                expected,
                quarantine_parent_fd,
                destination_prefix=_QUARANTINE_ENTRY_PREFIX,
                recovery_parent_fd=recovery_parent_fd,
            )
            if stat.S_ISDIR(observed.st_mode):
                child_fd: int | None = None
                try:
                    child_fd = _open_checked_directory(
                        quarantine_parent_fd,
                        quarantined.name,
                        expected,
                    )
                    child_entries = os.listdir(child_fd)
                except BaseException:
                    if child_fd is not None:
                        try:
                            os.close(child_fd)
                        except OSError:
                            pass
                    _close_entry_descriptor(quarantined)
                    raise
                if child_fd is None:
                    _close_entry_descriptor(quarantined)
                    raise OSError("pytest cleanup lost quarantined directory fd")
                _close_entry_descriptor(quarantined)
                frames.append(
                    _DirectoryWalkFrame(
                        descriptor=child_fd,
                        identity=expected,
                        name=quarantined.name,
                        parent_fd=quarantine_parent_fd,
                        recovery_parent_fd=quarantined.recovery_parent_fd,
                        entries=child_entries,
                    )
                )
                continue
            _delete_quarantined_entry(quarantined, directory=False)
    except BaseException:
        for frame in frames:
            if frame.name is None or frame.descriptor is None:
                continue
            try:
                os.close(frame.descriptor)
            except OSError:
                pass
        raise


def _find_exact_namespace_name(
    handle: _PytestTempNamespaceHandle,
) -> str | None:
    """Classify one retained inode in its original parent without deleting."""
    for name in os.listdir(handle.parent_fd):
        if name == handle.name:
            continue
        try:
            observed = _stat_entry(handle.parent_fd, name)
        except FileNotFoundError:
            continue
        expected = _ObjectIdentity.from_stat(observed)
        if expected != handle.namespace_identity or not stat.S_ISDIR(observed.st_mode):
            continue

        # The name is only a lookup hint.  Open and fstat the exact object, then
        # revalidate the directory entry immediately.  No destructive operation
        # is allowed to use this name after this classification.
        descriptor = _open_entry_identity(
            handle.parent_fd,
            name,
            handle.namespace_identity,
        )
        try:
            _require_entry(handle.parent_fd, name, handle.namespace_identity)
        except (OSError, ValueError) as exc:
            raise OSError(
                "retained pytest namespace identity lookup raced at "
                f"alternate name {name!r}"
            ) from exc
        finally:
            os.close(descriptor)
        return name
    return None


def _namespace_link_state(
    handle: _PytestTempNamespaceHandle,
) -> _NamespaceLinkState:
    _assert_parent_anchor(handle)
    namespace_stat = _assert_namespace_fd(handle)
    link_count = int(namespace_stat.st_nlink)
    if link_count == 0:
        return _NamespaceLinkState(link_count, False)

    original_identity_matches = False
    try:
        _require_entry(handle.parent_fd, handle.name, handle.namespace_identity)
    except FileNotFoundError:
        pass
    except OSError:
        # A replacement at the original name is not owned.  The exact lookup
        # below may still find the retained inode under a different name.
        pass
    else:
        original_identity_matches = True

    alternate_name = None
    if not original_identity_matches:
        alternate_name = _find_exact_namespace_name(handle)
    return _NamespaceLinkState(
        link_count,
        original_identity_matches,
        alternate_name,
    )


def _repair_namespace_permissions(
    handle: _PytestTempNamespaceHandle,
    root_stat: os.stat_result,
) -> None:
    if all(
        root_stat.st_mode & bit
        for bit in (stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR)
    ):
        return
    if getattr(os, "fchmod", None) is None:
        _chmod_open_directory_fd(handle.namespace_fd, root_stat.st_mode)
    else:
        os.fchmod(
            handle.namespace_fd,
            root_stat.st_mode
            | stat.S_IRUSR
            | stat.S_IWUSR
            | stat.S_IXUSR,
        )


def _assert_cleanup_quarantine(handle: _PytestTempNamespaceHandle) -> None:
    quarantine = handle.cleanup_quarantine
    if quarantine is None:
        raise OSError("pytest cleanup lost its namespace quarantine binding")
    _assert_parent_anchor(handle)
    _require_entry(
        quarantine.parent_fd,
        quarantine.name,
        quarantine.identity,
    )


def _quarantine_outer_namespace(
    handle: _PytestTempNamespaceHandle,
) -> None:
    if handle.cleanup_quarantine is not None:
        _assert_cleanup_quarantine(handle)
        return
    moved = _quarantine_entry(
        handle.parent_fd,
        handle.name,
        handle.namespace_identity,
        handle.parent_fd,
        destination_prefix=_QUARANTINE_NAME_PREFIX,
    )
    _close_entry_descriptor(moved)
    handle._cleanup_quarantine = _CleanupQuarantine(
        parent_fd=handle.parent_fd,
        parent_identity=handle.parent_identity,
        name=moved.name,
        identity=moved.identity,
    )


def _clear_owned_namespace_contents(
    handle: _PytestTempNamespaceHandle,
) -> None:
    """Clear only the retained inode; never resolve its changed directory name."""
    _drain_owner_processes(handle)
    _assert_parent_anchor(handle)
    root_stat = _assert_namespace_fd(handle)
    _repair_namespace_permissions(handle, root_stat)
    _remove_directory_contents(
        handle.namespace_fd,
        quarantine_parent_fd=handle.namespace_fd,
        recovery_parent_fd=handle.parent_fd,
    )


def _remove_owned_namespace(handle: _PytestTempNamespaceHandle) -> None:
    _drain_owner_processes(handle)
    _assert_parent_anchor(handle)
    root_stat = _assert_namespace_fd(handle)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise NotADirectoryError(handle.name)
    if handle.cleanup_quarantine is None:
        _require_entry(handle.parent_fd, handle.name, handle.namespace_identity)
        _quarantine_outer_namespace(handle)
    else:
        _assert_cleanup_quarantine(handle)
    _repair_namespace_permissions(handle, root_stat)
    _remove_directory_contents(
        handle.namespace_fd,
        quarantine_parent_fd=handle.namespace_fd,
        recovery_parent_fd=handle.parent_fd,
    )
    _assert_namespace_fd(handle)
    _assert_cleanup_quarantine(handle)
    quarantine = handle.cleanup_quarantine
    if quarantine is None:
        raise OSError("pytest cleanup lost its namespace quarantine binding")
    try:
        quarantine_descriptor = _open_entry_identity(
            quarantine.parent_fd,
            quarantine.name,
            quarantine.identity,
        )
        _delete_quarantined_entry(
            _QuarantinedEntry(
                parent_fd=quarantine.parent_fd,
                name=quarantine.name,
                identity=quarantine.identity,
                descriptor=quarantine_descriptor,
            ),
            directory=True,
        )
    except (OSError, ValueError) as exc:
        raise PytestTempNamespaceRaceError(
            "pytest cleanup could not stage and remove the owner quarantine "
            f"link without risking a changed object: {quarantine.name!r}"
        ) from exc
    namespace_stat = _assert_namespace_fd(handle)
    if namespace_stat.st_nlink != 0:
        raise OSError(
            "pytest cleanup removed the owner quarantine name but the "
            f"retained inode remains linked: st_nlink={namespace_stat.st_nlink}"
        )
    handle.removed = True


def _namespace_still_owned(handle: _PytestTempNamespaceHandle) -> bool:
    if handle.cleanup_quarantine is not None:
        try:
            _assert_cleanup_quarantine(handle)
        except (OSError, ValueError):
            namespace_stat = _assert_namespace_fd(handle)
            if namespace_stat.st_nlink == 0:
                handle.removed = True
                return False
            raise PytestTempNamespaceRaceError(
                "pytest cleanup lost or changed its owner quarantine link"
            )
        return True
    state = _namespace_link_state(handle)
    if state.is_unlinked:
        handle.removed = True
        return False
    if not state.original_identity_matches:
        raise OSError(state.describe(handle))
    return True


def _cleanup_diagnostic_path(namespace: Path) -> Path:
    return namespace.with_name(f".{namespace.name}.cleanup-failed.json")


def _unlink_created_diagnostic(
    handle: _PytestTempNamespaceHandle,
    name: str,
    expected: _ObjectIdentity,
) -> bool:
    try:
        _drain_owner_processes(handle)
        namespace_stat = _assert_namespace_fd(handle)
        _repair_namespace_permissions(handle, namespace_stat)
        quarantined = _quarantine_entry(
            handle.parent_fd,
            name,
            expected,
            handle.namespace_fd,
            destination_prefix=_QUARANTINE_ENTRY_PREFIX,
        )
        _delete_quarantined_entry(quarantined, directory=False)
    except (OSError, ValueError) as exc:
        print(
            "[pytest-temp-cleanup-diagnostic-failed] "
            f"refusing to remove changed partial diagnostic name={name!r} "
            f"error={exc!r}",
            file=sys.stderr,
            flush=True,
        )
        return False
    return True


def _write_cleanup_diagnostic(
    handle: _PytestTempNamespaceHandle,
    failures: list[dict[str, str]],
    *,
    attempts: int | None = None,
) -> Path | None:
    diagnostic = _cleanup_diagnostic_path(handle.path)
    name = diagnostic.name
    payload = {
        "schema_version": PYTEST_TEMP_CLEANUP_DIAGNOSTIC_SCHEMA,
        "status": "cleanup_failed",
        "namespace": str(handle.path),
        "parent": str(handle.path.parent),
        "attempts": len(failures) if attempts is None else attempts,
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
            failures.append(
                {
                    "attempt": str(attempt),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            if isinstance(
                exc,
                (PytestTempNamespaceBusyError, PytestTempNamespaceRaceError),
            ):
                break
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
                if isinstance(
                    state_error,
                    (PytestTempNamespaceBusyError, PytestTempNamespaceRaceError),
                ):
                    break
                try:
                    _clear_owned_namespace_contents(handle)
                    after_clear = _assert_namespace_fd(handle)
                except (OSError, ValueError) as clear_error:
                    failures.append(
                        {
                            "attempt": str(attempt),
                            "error_type": type(clear_error).__name__,
                            "error": str(clear_error),
                        }
                    )
                    if isinstance(
                        clear_error,
                        (PytestTempNamespaceBusyError, PytestTempNamespaceRaceError),
                    ):
                        break
                else:
                    if after_clear.st_nlink == 0:
                        removed = True
                    else:
                        failures.append(
                            {
                                "attempt": str(attempt),
                                "error_type": "RetainedNamespaceLinked",
                                "error": (
                                    "retained pytest namespace contents were cleared "
                                    "through the retained fd, but its directory link "
                                    "remains; cleanup cannot safely unlink the "
                                    f"remaining inode link (st_nlink={after_clear.st_nlink})"
                                ),
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

    diagnostic = _write_cleanup_diagnostic(handle, failures, attempts=attempts)
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
        f"namespace={handle.path} attempts={attempts}{diagnostic_suffix}",
        file=sys.stderr,
        flush=True,
    )
    errors = tuple(
        f"attempt={failure['attempt']} {failure['error_type']}: {failure['error']}"
        for failure in failures
    ) + close_errors
    return PytestTempCleanupResult(
        handle.path,
        False,
        attempts,
        diagnostic,
        errors,
    )


@contextmanager
def owned_pytest_temp_namespace_handle(
    parent: Path | None = None,
) -> Iterator[_PytestTempNamespaceHandle]:
    """Yield one owner handle and close it through the cleanup lifecycle."""
    handle = _pytest_temp_directory(parent)
    body_failed = False
    try:
        yield handle
    except BaseException:
        body_failed = True
        raise
    finally:
        cleanup = cleanup_pytest_temp_namespace(handle)
        if not cleanup.ok and not body_failed:
            raise PytestTempCleanupError(cleanup)


@contextmanager
def owned_pytest_temp_namespace(parent: Path | None = None) -> Iterator[Path]:
    """Yield pytest's child basetemp while retaining the owner directory handle."""
    with owned_pytest_temp_namespace_handle(parent) as handle:
        yield handle.basetemp_path


class PytestArgumentAuthorityError(ValueError):
    """The runner cannot prove that pytest will use its owned basetemp."""


def _is_addopts_override(args: list[str], index: int) -> bool:
    argument = args[index]
    value: str | None = None
    if argument in {"-o", "--override-ini"}:
        if index + 1 < len(args):
            value = args[index + 1]
    elif argument.startswith("--override-ini="):
        value = argument.partition("=")[2]
    elif argument.startswith("-o") and len(argument) > 2:
        value = argument[2:].lstrip("=")
    if value is None:
        return False
    return value.partition("=")[0].strip().lower() == "addopts"


def _validate_pytest_argument_tokens(
    args: list[str],
    *,
    source: str,
    reject_end_of_options: bool,
) -> None:
    """Validate one token stream before pytest or argparse can expand it.

    Pytest's supported ``@file`` syntax is recursive and expands before its
    option parser sees the resulting tokens.  Reimplementing that parser here
    would create a second, drift-prone authority.  The owner-bound runner
    therefore rejects the expansion surface explicitly and keeps only the
    direct token grammar it can prove.
    """
    for index, argument in enumerate(args):
        if argument == "--basetemp" or argument.startswith("--basetemp="):
            raise PytestArgumentAuthorityError(
                "run_pytest_lane requires a fresh --basetemp owned by the "
                f"runner and rejects {source} argument {index} {argument!r}"
            )
        if argument.startswith("@"):
            raise PytestArgumentAuthorityError(
                "run_pytest_lane cannot prove a fresh --basetemp through "
                f"pytest @argument-file expansion in {source} argument {index}; "
                "argument files are unsupported by the owner-bound lane"
            )
        if reject_end_of_options and argument == "--":
            raise PytestArgumentAuthorityError(
                "run_pytest_lane cannot prove a fresh --basetemp when "
                f"PYTEST_ADDOPTS places an end-of-options marker before the "
                f"runner owner option (at {source} argument {index})"
            )
        if source == "runner arguments" and _is_addopts_override(args, index):
            raise PytestArgumentAuthorityError(
                "run_pytest_lane cannot accept a user addopts override because "
                "pytest config addopts is an argument expansion surface; "
                "the runner owns that setting"
            )


def validate_pytest_argument_authority(
    args: list[str],
    *,
    environment: dict[str, str] | None = None,
) -> None:
    """Prove all caller-controlled pytest argument streams are owner-safe."""
    _validate_pytest_argument_tokens(
        args,
        source="runner arguments",
        reject_end_of_options=False,
    )
    environment = os.environ if environment is None else environment
    raw_addopts = environment.get(PYTEST_ADDOPTS_ENV)
    if not raw_addopts:
        return
    try:
        addopts = shlex.split(raw_addopts)
    except ValueError as exc:
        raise PytestArgumentAuthorityError(
            "run_pytest_lane cannot prove a fresh --basetemp because "
            f"{PYTEST_ADDOPTS_ENV} is not valid shell-style argument text"
        ) from exc
    _validate_pytest_argument_tokens(
        addopts,
        source=PYTEST_ADDOPTS_ENV,
        reject_end_of_options=True,
    )


def _assert_no_static_basetemp(args: list[str]) -> None:
    """Compatibility wrapper for the shared argument-authority validator."""
    _validate_pytest_argument_tokens(
        args,
        source="runner arguments",
        reject_end_of_options=False,
    )


def _pytest_subprocess_environment(args: list[str]) -> dict[str, str]:
    environment = os.environ.copy()
    validate_pytest_argument_authority(args, environment=environment)
    return environment


def build_pytest_command(*, extra_args: list[str], basetemp: Path) -> list[str]:
    validate_pytest_argument_authority(extra_args)
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-o",
        "addopts=",
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
    pytest_args: list[str],
) -> dict[str, str]:
    environment = _pytest_subprocess_environment(pytest_args)
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
    validate_pytest_argument_authority(selection_args)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-o",
        "addopts=",
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
    validate_pytest_argument_authority(extra_args)
    with tempfile.TemporaryDirectory(
        prefix="abyss-stack-pytest-partitions-",
    ) as temporary_raw:
        temporary = Path(temporary_raw)
        baseline_path = temporary / "baseline.json"
        collect_log = temporary / "collect.log"
        try:
            with owned_pytest_temp_namespace_handle() as collect_namespace:
                collect_basetemp = collect_namespace.basetemp_path
                collect_command = _plugin_command(
                    selection_args=extra_args,
                    basetemp=collect_basetemp,
                    collect_only=True,
                )
                collect_started = time.monotonic()
                with collect_log.open("w", encoding="utf-8") as output:
                    collect_process = subprocess.Popen(
                        collect_command,
                        cwd=REPO_ROOT,
                        env=_partition_environment(
                            baseline_path=baseline_path,
                            pytest_args=extra_args,
                        ),
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        text=True,
                        close_fds=True,
                        start_new_session=hasattr(os, "setsid"),
                    )
                    if hasattr(collect_process, "pid") and hasattr(os, "setsid"):
                        collect_namespace.register_owner_process_group(
                            collect_process.pid
                        )
                    collected = subprocess.CompletedProcess(
                        collect_command,
                        collect_process.wait(),
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
                                pytest_args=assignments[shard_index],
                            ),
                            stdout=output,
                            stderr=subprocess.STDOUT,
                            text=True,
                            close_fds=True,
                            start_new_session=hasattr(os, "setsid"),
                        )
                        if hasattr(process, "pid") and hasattr(os, "setsid"):
                            temporary_namespace.register_owner_process_group(
                                process.pid
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
        if cleanup_failed:
            return PYTEST_TEMP_CLEANUP_FAILURE_EXIT_CODE
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
        validate_pytest_argument_authority(extra_args)
    except PytestArgumentAuthorityError as exc:
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
            with owned_pytest_temp_namespace_handle() as temporary_namespace:
                basetemp = temporary_namespace.basetemp_path
                command = build_pytest_command(
                    extra_args=extra_args,
                    basetemp=basetemp,
                )
                print(f"[run] tests: {subprocess.list2cmdline(command)}", flush=True)
                process = subprocess.Popen(
                    command,
                    cwd=REPO_ROOT,
                    env=_pytest_subprocess_environment(extra_args),
                    close_fds=True,
                    start_new_session=hasattr(os, "setsid"),
                )
                if hasattr(process, "pid") and hasattr(os, "setsid"):
                    temporary_namespace.register_owner_process_group(process.pid)
                completed = subprocess.CompletedProcess(command, process.wait())
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
