#!/usr/bin/env python3
"""Detect MCP pair drift and run a removable, explicitly configured lab suite.

The watcher is deliberately protocol-lab orchestration, not production
lifecycle authority.  A successful run advances only its private last-success
fingerprint.  Production files are measured before and after every suite and
are never written by this process.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


LAB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = LAB_ROOT / "protocol-watch-plan.v1.json"
DEFAULT_STATE_ROOT = LAB_ROOT / "generated" / "protocol-watch"
USER_AGENT = "os-abyss-mcp-protocol-watcher/1"
RUN_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}\.[0-9]{6}Z$")
RETENTION_SCHEMA_VERSION = "abyss_mcp_protocol_watch_retention_v1"
RUN_STATE_SCHEMA_VERSION = "abyss_mcp_protocol_watch_run_state_v1"

# The defaults are intentionally small compared with the observed watcher
# footprint (411 runs and roughly 9.9 GiB, with 1.2--1.6 GiB arriving on a
# busy day).  A successful run keeps compact receipts, while its generated
# homes and step logs are eligible for immediate disposal.  The count, byte,
# and age limits are a second line of defence for compact evidence and failed
# diagnostics.
DEFAULT_RETENTION = {
    "max_successful_runs": 14,
    "max_successful_bytes": 1024 * 1024 * 1024,
    "max_successful_age_seconds": 7 * 24 * 60 * 60,
    "max_failed_runs": 6,
    "max_failed_bytes": 512 * 1024 * 1024,
    "max_failed_age_seconds": 14 * 24 * 60 * 60,
    "retain_failed_diagnostics": 2,
    "max_observations": 64,
    "max_observation_bytes": 16 * 1024 * 1024,
    "max_observation_age_seconds": 30 * 24 * 60 * 60,
    "disposable_roots": ["stable-home", "lab/codex-home", "step-logs"],
    "diagnostic_roots": ["step-logs"],
    "cache_roots": ["stable-home/.tmp/plugins", "lab/codex-home/.tmp/plugins"],
    "receipt_archive_root": "retained-receipts",
    "pin_file": "pinned-runs.json",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _now()).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _digest(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _resolve(base: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else base / path


def _pointer(value: Any, pointer: str) -> Any:
    current = value
    for raw_part in pointer.lstrip("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(pointer)
    return current


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _atomic_json(path: Path, value: dict[str, Any], *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        payload = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    path.chmod(mode)


def _atomic_private_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_json(path, value, mode=0o600)


def _atomic_private_bytes(path: Path, payload: bytes) -> None:
    _atomic_bytes(path, payload, mode=0o600)


def _atomic_bytes(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    path.chmod(mode)


def _immutable_private_json(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    payload = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError(f"immutable observation collision: {path}")
    else:
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
    return _digest(payload)


def _tree_record(base: Path, raw_paths: list[str]) -> dict[str, Any]:
    files: list[dict[str, str]] = []
    for raw in raw_paths:
        path = _resolve(base, raw)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"watched tree member is not a regular non-symlink file: {path}")
        files.append({"path": raw, "sha256": _file_digest(path)})
    return {"files": files, "tree_digest": _digest(files)}


def _command_output(argv: list[str], timeout: int = 30) -> str:
    result = subprocess.run(
        argv,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def _observe_input(
    item: dict[str, Any],
    *,
    base: Path,
    timeout: int,
    urlopen: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    input_id = item["input_id"]
    kind = item["kind"]
    record: dict[str, Any] = {
        "input_id": input_id,
        "kind": kind,
        "required": item["required"],
        "status": "passed",
    }
    try:
        if kind == "file":
            path = _resolve(base, item["path"])
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"not a regular non-symlink file: {path}")
            record["observation"] = {
                "path": item["path"],
                "sha256": _file_digest(path),
                "size_bytes": path.stat().st_size,
            }
        elif kind == "tree":
            record["observation"] = _tree_record(base, item["paths"])
        elif kind == "executable":
            executable = shutil.which(item["command"])
            if executable is None:
                raise ValueError(f"executable not found: {item['command']}")
            path = Path(executable).resolve(strict=True)
            record["observation"] = {
                "resolved_path": str(path),
                "sha256": _file_digest(path),
                "version": _command_output([str(path), *item["probe_argv"]], timeout),
                "features_sha256": _digest(
                    _command_output([str(path), *item["feature_argv"]], timeout).encode()
                ),
            }
        elif kind == "https_json":
            request = urllib.request.Request(
                item["url"],
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            )
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
                payload = json.loads(raw)
                selected = {pointer: _pointer(payload, pointer) for pointer in item["select"]}
                record["observation"] = {
                    "url": item["url"],
                    "selected": selected,
                    "selected_digest": _digest(selected),
                    "response_sha256": _digest(raw),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
        else:
            raise ValueError(f"unsupported input kind: {kind}")
    except Exception as exc:  # bounded into fail-closed watcher evidence
        record["status"] = "blocked"
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def _input_fingerprints(records: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in records:
        observation = item.get("observation") or {}
        if item["kind"] == "https_json":
            identity = observation.get("selected_digest")
        elif item["kind"] == "executable":
            identity = {
                "sha256": observation.get("sha256"),
                "version": observation.get("version"),
                "features_sha256": observation.get("features_sha256"),
            }
        elif item["kind"] == "tree":
            identity = observation.get("tree_digest")
        else:
            identity = observation.get("sha256")
        result[item["input_id"]] = _digest(
            {
                "kind": item["kind"],
                "required": item["required"],
                "status": item["status"],
                "identity": identity,
            }
        )
    return result


def _fingerprint(records: list[dict[str, Any]]) -> str:
    return _digest(_input_fingerprints(records))


def _ttl(plan: dict[str, Any], base: Path, now: datetime) -> dict[str, Any]:
    source = plan["ttl_source"]
    try:
        payload = _read_json(_resolve(base, source["path"]))
        expires_at = datetime.fromisoformat(
            str(_pointer(payload, source["pointer"])).replace("Z", "+00:00")
        )
        remaining = int((expires_at - now).total_seconds())
        return {
            "status": "passed",
            "expires_at": _timestamp(expires_at),
            "remaining_seconds": remaining,
            "lead_seconds": plan["ttl_lead_seconds"],
            "refresh_due": remaining <= plan["ttl_lead_seconds"],
        }
    except Exception as exc:
        return {"status": "blocked", "error": f"{type(exc).__name__}: {exc}", "refresh_due": True}


def _load_protocol_status(plan: dict[str, Any], base: Path) -> dict[str, Any]:
    source = plan["ttl_source"]
    return _read_json(_resolve(base, source["path"]))


def _verdicts(
    protocol_status: dict[str, Any] | None,
    *,
    observation_ready: bool,
) -> dict[str, bool]:
    status = protocol_status or {}
    blockers = set(status.get("production_cutover_blockers", []))
    reasons = set(status.get("reason_codes", []))
    read_allowed = bool(status.get("read_only_pilot_allowed", False))
    core_allowed = bool(status.get("core_read_migration_allowed", False))
    return {
        "compatible_for_lab": observation_ready and read_allowed,
        "eligible_for_read_canary": observation_ready and read_allowed,
        "eligible_for_core_read": observation_ready and core_allowed,
        "blocked_on_conformance": "current_conformance_fixture_mismatch" in blockers,
        "blocked_on_cancellation": "modern_cancellation_not_propagated" in blockers,
        "blocked_on_auth": any("auth" in item for item in blockers),
        "client_extension_capability_absent": "tasks_client_extension_capability_absent" in reasons,
        "production_cutover_allowed": observation_ready and core_allowed,
    }


def _private_secret(path: Path) -> str:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"secret is not a regular non-symlink file: {path}")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError(f"secret must be mode 0600: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if len(value) < 32:
        raise ValueError(f"secret is missing or too short: {path}")
    return value


def _expand(value: str, run_root: Path) -> str:
    return value.replace("{run_root}", str(run_root))


def _measure_paths(raw_paths: list[str], run_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in raw_paths:
        path = Path(_expand(raw, run_root)).expanduser()
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"protected path is not a regular non-symlink file: {path}")
        result[str(path)] = _file_digest(path)
    return result


def _execute_suite(
    runtime: dict[str, Any],
    *,
    run_root: Path,
) -> tuple[bool, bool, list[dict[str, Any]], list[str]]:
    environment = {
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    secret_values: list[str] = []
    failures: list[str] = []
    for name, raw_path in runtime["secret_files"].items():
        value = _private_secret(Path(_expand(raw_path, run_root)).expanduser())
        environment[name] = value
        secret_values.append(value)
    before = _measure_paths(runtime["protected_paths"], run_root)
    step_receipts: list[dict[str, Any]] = []
    suite_passed = True
    for step in runtime["steps"]:
        argv = [_expand(value, run_root) for value in step["argv"]]
        step_environment = dict(environment)
        for name, raw_value in step["environment"].items():
            if any(marker in name for marker in ("TOKEN", "SECRET", "KEY", "CREDENTIAL")):
                raise ValueError(
                    f"step {step['step_id']} must receive secret environment through secret_files"
                )
            step_environment[name] = _expand(raw_value, run_root)
        started = _timestamp()
        try:
            result = subprocess.run(
                argv,
                env=step_environment,
                cwd=run_root,
                capture_output=True,
                timeout=step["timeout_seconds"],
            )
            output = result.stdout + result.stderr
            if any(value.encode() in output for value in secret_values):
                raise RuntimeError("secret material appeared in child output")
            step_log_root = run_root / "step-logs"
            stdout_path = step_log_root / f"{step['step_id']}.stdout"
            stderr_path = step_log_root / f"{step['step_id']}.stderr"
            _atomic_private_bytes(stdout_path, result.stdout)
            _atomic_private_bytes(stderr_path, result.stderr)
            step_receipts.append(
                {
                    "step_id": step["step_id"],
                    "started_at": started,
                    "finished_at": _timestamp(),
                    "argv_sha256": _digest(argv),
                    "returncode": result.returncode,
                    "stdout_sha256": _digest(result.stdout),
                    "stderr_sha256": _digest(result.stderr),
                    "stdout_ref": f"local://{stdout_path}",
                    "stderr_ref": f"local://{stderr_path}",
                }
            )
            if result.returncode != 0:
                suite_passed = False
                failures.append(f"step {step['step_id']} returned {result.returncode}")
                break
        except Exception as exc:
            suite_passed = False
            failures.append(f"step {step['step_id']} failed: {type(exc).__name__}: {exc}")
            break
    after = _measure_paths(runtime["protected_paths"], run_root)
    protected_unchanged = before == after
    if not protected_unchanged:
        suite_passed = False
        failures.append("one or more protected production files changed")
    receipts: list[dict[str, Any]] = step_receipts
    if suite_passed:
        for item in runtime["required_receipts"]:
            path = Path(_expand(item["path"], run_root))
            try:
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    raise ValueError("not a regular non-symlink file")
                if item["visibility"] == "private" and stat.S_IMODE(info.st_mode) != 0o600:
                    raise ValueError("private receipt is not mode 0600")
                encoded = path.read_bytes()
                if any(value.encode() in encoded for value in secret_values):
                    raise ValueError("secret material appeared in receipt")
                receipts.append(
                    {
                        "receipt_id": item["receipt_id"],
                        "visibility": item["visibility"],
                        "path": str(path),
                        "sha256": _digest(encoded),
                        "size_bytes": len(encoded),
                    }
                )
            except Exception as exc:
                suite_passed = False
                failures.append(f"receipt {item['receipt_id']} failed: {type(exc).__name__}: {exc}")
    return suite_passed, protected_unchanged, receipts, failures


def _retention_policy(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a validated policy, keeping older plans source-compatible."""

    raw = plan.get("retention", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("retention policy must be an object")
    unknown = set(raw) - set(DEFAULT_RETENTION)
    if unknown:
        raise ValueError(f"retention contains unsupported keys: {sorted(unknown)}")
    policy = dict(DEFAULT_RETENTION)
    policy.update(raw)
    integer_limits = (
        "max_successful_runs",
        "max_successful_bytes",
        "max_successful_age_seconds",
        "max_failed_runs",
        "max_failed_bytes",
        "max_failed_age_seconds",
        "retain_failed_diagnostics",
        "max_observations",
        "max_observation_bytes",
        "max_observation_age_seconds",
    )
    for name in integer_limits:
        value = policy.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"retention {name} must be a non-negative integer")
    if policy["retain_failed_diagnostics"] > policy["max_failed_runs"]:
        raise ValueError("retention retain_failed_diagnostics exceeds max_failed_runs")
    for name in ("disposable_roots", "diagnostic_roots", "cache_roots"):
        value = policy.get(name)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"retention {name} must be a list of relative paths")
        for item in value:
            if _safe_relative_path(item) is None:
                raise ValueError(f"retention {name} contains an unsafe path: {item}")
        if len(value) != len(set(value)):
            raise ValueError(f"retention {name} contains duplicate paths")
    if not set(policy["diagnostic_roots"]).issubset(set(policy["disposable_roots"])):
        raise ValueError("retention diagnostic_roots must be disposable_roots")
    disposable_paths = [Path(item) for item in policy["disposable_roots"]]
    for raw in policy["cache_roots"]:
        cache_path = Path(raw)
        if not any(
            cache_path == disposable or disposable in cache_path.parents
            for disposable in disposable_paths
        ):
            raise ValueError("retention cache_roots must be inside disposable_roots")
    for name in ("receipt_archive_root", "pin_file"):
        if not isinstance(policy.get(name), str) or _safe_relative_path(policy[name]) is None:
            raise ValueError(f"retention {name} must be a safe relative path")
        if Path(policy[name]).parts[0] in {"runs", "observations"}:
            raise ValueError(f"retention {name} cannot be inside a live evidence root")
    if policy["receipt_archive_root"] == policy["pin_file"]:
        raise ValueError("retention receipt_archive_root and pin_file must differ")
    return policy


@contextmanager
def _state_lock(state_root: Path) -> Iterator[None]:
    """Serialize watcher and retention operations on one private state root."""

    state_root = Path(os.path.abspath(state_root))
    if state_root.is_symlink():
        raise ValueError("state root must not be a symlink")
    if state_root.exists():
        info = state_root.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("state root must be a directory")
        if info.st_uid != os.getuid():
            raise ValueError("state root is not owner-created")
    else:
        state_root.mkdir(parents=True, mode=0o700)
    state_root.chmod(0o700)
    lock_path = state_root / ".lock"
    if lock_path.is_symlink():
        raise ValueError("state lock must not be a symlink")
    if lock_path.exists() and not stat.S_ISREG(lock_path.lstat().st_mode):
        raise ValueError("state lock must be a regular file")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(lock_fd)


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _safe_relative_path(raw: Any) -> Path | None:
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


def _within(path: Path, root: Path) -> bool:
    """Check lexical containment without following a child symlink."""

    try:
        Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(root)))
    except ValueError:
        return False
    return True


def _mount_points() -> set[str]:
    """Return mount points from the host namespace in a comparison-safe form."""

    points: set[str] = set()
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return points
    for line in lines:
        fields = line.split(" - ", 1)[0].split()
        if len(fields) < 5:
            continue
        raw = fields[4]

        def decode(match: re.Match[str]) -> str:
            return chr(int(match.group(1), 8))

        points.add(re.sub(r"\\([0-7]{3})", decode, raw))
    return points


def _mount_boundary_safe(path: Path, root: Path, mount_points: set[str]) -> bool:
    """Check that ``path`` stays on ``root``'s filesystem and mount tree."""

    if not _within(path, root):
        return False
    root_abs = Path(os.path.abspath(root))
    path_abs = Path(os.path.abspath(path))
    try:
        root_info = root_abs.lstat()
        path_info = path_abs.lstat()
        relative = path_abs.relative_to(root_abs)
    except OSError:
        return False
    except ValueError:
        return False
    if path_info.st_dev != root_info.st_dev:
        return False
    current = root_abs
    for part in relative.parts:
        current /= part
        if os.path.abspath(current) in mount_points:
            return False
    return True


def _no_symlink_ancestors(path: Path, root: Path) -> bool:
    """Ensure every path component below ``root`` is a real directory/file."""

    if not _within(path, root):
        return False
    current = Path(os.path.abspath(root))
    try:
        relative = Path(os.path.abspath(path)).relative_to(current)
    except ValueError:
        return False
    for part in relative.parts:
        current /= part
        try:
            if current.is_symlink():
                return False
        except OSError:
            return False
    return True


def _tree_measure(
    path: Path,
    *,
    owner_uid: int | None = None,
    boundary_root: Path | None = None,
) -> dict[str, Any]:
    """Measure a tree without following symlinks and report cleanup safety.

    ``allocated_bytes`` is the storage accounting used by retention guards: it
    sums ``st_blocks * 512`` once per inode.  ``logical_bytes`` remains useful
    for explaining sparse files and is never used as the deletion guard.  A
    mount point, a cross-device child, a symlink root, or a foreign-owned
    inode makes the tree ineligible for automated removal. Child symlinks are
    counted but never followed.
    """

    logical_bytes = 0
    allocated_bytes = 0
    file_count = 0
    safe = True
    reasons: set[str] = set()

    try:
        root_info = path.lstat()
    except OSError as exc:
        return {
            "bytes": 0,
            "logical_bytes": 0,
            "allocated_bytes": 0,
            "files": 0,
            "safe": False,
            "error_class": type(exc).__name__,
        }
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        return {
            "bytes": 0,
            "logical_bytes": 0,
            "allocated_bytes": 0,
            "files": 0,
            "safe": False,
            "error_class": "unsafe_root",
        }
    if owner_uid is not None and root_info.st_uid != owner_uid:
        safe = False
        reasons.add("foreign_owner")
    root_device = root_info.st_dev
    mount_points = _mount_points()
    root_name = os.path.abspath(path)
    if boundary_root is not None and not _mount_boundary_safe(
        path, boundary_root, mount_points
    ):
        safe = False
        reasons.add("mount_boundary")
    if root_name in mount_points:
        safe = False
        reasons.add("mount_boundary")
    if owner_uid is not None and root_info.st_uid != owner_uid:
        return {
            "bytes": max(0, int(root_info.st_blocks)) * 512,
            "logical_bytes": 0,
            "allocated_bytes": max(0, int(root_info.st_blocks)) * 512,
            "files": 0,
            "safe": False,
            "error_class": "foreign_owner",
            "error_classes": ["foreign_owner"],
        }
    seen_inodes: set[tuple[int, int]] = set()

    def account(info: os.stat_result) -> bool:
        nonlocal allocated_bytes, logical_bytes, file_count, safe
        inode = (info.st_dev, info.st_ino)
        if inode in seen_inodes:
            return False
        seen_inodes.add(inode)
        allocated_bytes += max(0, int(info.st_blocks)) * 512
        if stat.S_ISREG(info.st_mode):
            logical_bytes += info.st_size
            file_count += 1
        return True

    account(root_info)

    pending = [] if root_name in mount_points else [path]
    try:
        while pending:
            current = pending.pop()
            current_name = os.path.abspath(current)
            if current_name in mount_points and current_name != root_name:
                safe = False
                reasons.add("mount_boundary")
                continue
            with os.scandir(current) as entries:
                for entry in entries:
                    info = entry.stat(follow_symlinks=False)
                    entry_name = os.path.abspath(entry.path)
                    account(info)
                    if owner_uid is not None and info.st_uid != owner_uid:
                        safe = False
                        reasons.add("foreign_owner")
                    if info.st_dev != root_device:
                        safe = False
                        reasons.add("cross_device")
                    if stat.S_ISLNK(info.st_mode):
                        # Producer-created homes contain links to the managed
                        # Codex binary. They are safe to unlink as entries;
                        # traversal never follows them, and rmtree is required
                        # to provide its own symlink-attack protection.
                        if owner_uid is not None and info.st_uid != owner_uid:
                            safe = False
                            reasons.add("foreign_symlink_owner")
                    elif stat.S_ISDIR(info.st_mode):
                        if entry_name in mount_points:
                            safe = False
                            reasons.add("mount_boundary")
                        elif info.st_dev == root_device:
                            pending.append(Path(entry.path))
                    elif stat.S_ISREG(info.st_mode):
                        pass
                    else:
                        safe = False
                        reasons.add("non_regular")
    except OSError as exc:
        safe = False
        reasons.add(type(exc).__name__)
        return {
            "bytes": allocated_bytes,
            "logical_bytes": logical_bytes,
            "allocated_bytes": allocated_bytes,
            "files": file_count,
            "safe": safe,
            "error_class": sorted(reasons)[0] if reasons else type(exc).__name__,
            "error_classes": sorted(reasons),
        }
    result = {
        "bytes": allocated_bytes,
        "logical_bytes": logical_bytes,
        "allocated_bytes": allocated_bytes,
        "files": file_count,
        "safe": safe,
    }
    if reasons:
        result["error_class"] = sorted(reasons)[0]
        result["error_classes"] = sorted(reasons)
    return result


def _safe_owned_directory(path: Path, *, root: Path, owner_uid: int) -> bool:
    if not _within(path, root) or not _no_symlink_ancestors(path, root) or path == root:
        return False
    try:
        info = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_uid == owner_uid
    )


def _required_receipt_paths(run_root: Path, execution_receipt: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for receipt in execution_receipt.get("receipts", []):
        if not isinstance(receipt, dict):
            continue
        raw_path = receipt.get("path")
        if not isinstance(raw_path, str) or raw_path.startswith(("local://", "private://")):
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = run_root / path
        if _within(path, run_root) and _no_symlink_ancestors(path, run_root):
            absolute = Path(os.path.abspath(path))
            if absolute not in paths:
                paths.append(absolute)
    return paths


def _protected_path(path: Path, protected_paths: list[Path]) -> bool:
    candidate = Path(os.path.abspath(path))
    return any(
        candidate == protected or _within(candidate, protected) or _within(protected, candidate)
        for protected in protected_paths
    )


def _read_regular_json(path: Path) -> dict[str, Any] | None:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            return None
        value = _read_json(path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return value


def _run_record(
    run_dir: Path,
    *,
    policy: dict[str, Any],
    owner_uid: int,
    state_root: Path | None = None,
) -> dict[str, Any] | None:
    """Read only the compact run metadata needed for a retention decision."""

    if not run_dir.is_dir() or run_dir.is_symlink() or RUN_ID_RE.fullmatch(run_dir.name) is None:
        return None
    execution_path = run_dir / "execution-receipt.json"
    execution = _read_regular_json(execution_path)
    run_state = _read_regular_json(run_dir / "run-state.json")
    state = run_state.get("state") if run_state else None
    if state == "running":
        state_name = "running"
    elif execution is None:
        state_name = "unknown"
    else:
        receipt_state = "completed" if bool(execution.get("passed")) else "failed"
        state_name = receipt_state if state in {None, receipt_state} else "unknown"
    boundary_root = state_root or run_dir.parent.parent
    measured = _tree_measure(
        run_dir,
        owner_uid=owner_uid,
        boundary_root=boundary_root,
    )
    finished_at = _parse_timestamp((run_state or {}).get("finished_at"))
    if finished_at is None:
        try:
            finished_at = datetime.strptime(run_dir.name, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=UTC)
        except ValueError:
            finished_at = datetime.fromtimestamp(run_dir.stat().st_mtime, tz=UTC)
    required_paths = _required_receipt_paths(run_dir, execution or {})
    disposable: list[dict[str, Any]] = []
    disposable_errors: list[str] = []
    for raw in policy["disposable_roots"]:
        relative = _safe_relative_path(raw)
        if relative is None:
            continue
        candidate = run_dir / relative
        if not candidate.exists() and not candidate.is_symlink():
            continue
        if not _safe_owned_directory(candidate, root=run_dir, owner_uid=owner_uid):
            disposable_errors.append(f"unsafe:{raw}")
            continue
        if _protected_path(candidate, required_paths):
            disposable_errors.append(f"required:{raw}")
            continue
        candidate_measure = _tree_measure(
            candidate,
            owner_uid=owner_uid,
            boundary_root=boundary_root,
        )
        if not candidate_measure["safe"]:
            disposable_errors.append(f"unsafe:{raw}")
            continue
        disposable.append(
            {
                "relative_path": relative.as_posix(),
                "kind": "diagnostic" if raw in policy["diagnostic_roots"] else "sandbox",
                "bytes": candidate_measure["allocated_bytes"],
                "logical_bytes": candidate_measure["logical_bytes"],
                "allocated_bytes": candidate_measure["allocated_bytes"],
                "files": candidate_measure["files"],
            }
        )
    cache: list[dict[str, Any]] = []
    cache_errors: list[str] = []
    for raw in policy["cache_roots"]:
        relative = _safe_relative_path(raw)
        if relative is None:
            continue
        candidate = run_dir / relative
        if not candidate.exists() and not candidate.is_symlink():
            continue
        if not _safe_owned_directory(candidate, root=run_dir, owner_uid=owner_uid):
            cache_errors.append(f"unsafe:{raw}")
            continue
        cache_measure = _tree_measure(
            candidate,
            owner_uid=owner_uid,
            boundary_root=boundary_root,
        )
        if not cache_measure["safe"]:
            cache_errors.append(f"unsafe:{raw}")
            continue
        cache.append(
            {
                "relative_path": relative.as_posix(),
                "allocated_bytes": cache_measure["allocated_bytes"],
                "logical_bytes": cache_measure["logical_bytes"],
                "files": cache_measure["files"],
            }
        )
    return {
        "run_id": run_dir.name,
        "path": run_dir,
        "state": state_name,
        "passed": bool(execution and execution.get("passed")),
        "finished_at": finished_at,
        "file_count": measured["files"],
        "safe": measured["safe"],
        "execution": execution,
        "run_state": run_state,
        "required_paths": required_paths,
        "disposable": disposable,
        "disposable_errors": disposable_errors,
        "cache": cache,
        "cache_errors": cache_errors,
        "logical_bytes": measured["logical_bytes"],
        "allocated_bytes": measured["allocated_bytes"],
        "compact_logical_bytes": max(
            0,
            measured["logical_bytes"]
            - sum(item["logical_bytes"] for item in disposable),
        ),
        "compact_allocated_bytes": max(
            0,
            measured["allocated_bytes"]
            - sum(item["allocated_bytes"] for item in disposable),
        ),
        # ``total_bytes`` and ``compact_bytes`` retain their historical
        # meaning for callers: they are the allocated-byte figures used as
        # deletion guards.
        "total_bytes": measured["allocated_bytes"],
        "compact_bytes": max(
            0,
            measured["allocated_bytes"]
            - sum(item["allocated_bytes"] for item in disposable),
        ),
    }


def _state_relative(path: Path, state_root: Path) -> str:
    return Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(state_root))).as_posix()


def _run_age_seconds(record: dict[str, Any], now: datetime) -> int:
    return max(0, int((now - record["finished_at"]).total_seconds()))


def _cache_measure_for_path(record: dict[str, Any], relative_path: str) -> tuple[int, int]:
    """Sum measured cache descendants for one disposable operation root."""

    operation_root = record["path"] / relative_path
    return (
        sum(
            item["allocated_bytes"]
            for item in record.get("cache", [])
            if _within(record["path"] / item["relative_path"], operation_root)
        ),
        sum(
            item["logical_bytes"]
            for item in record.get("cache", [])
            if _within(record["path"] / item["relative_path"], operation_root)
        ),
    )


def _load_protected_run_ids(
    state_root: Path,
    policy: dict[str, Any],
) -> tuple[set[str], dict[str, list[str]], list[str]]:
    """Load references that must never be removed by a retention plan."""

    protected: dict[str, list[str]] = {}
    errors: list[str] = []

    last_success_path = state_root / "last-success.json"
    if last_success_path.exists() or last_success_path.is_symlink():
        payload = None
        try:
            info = last_success_path.lstat()
            if (
                not _no_symlink_ancestors(last_success_path, state_root)
                or stat.S_ISLNK(info.st_mode)
                or info.st_uid != os.getuid()
            ):
                raise ValueError
            payload = _read_regular_json(last_success_path)
        except (OSError, ValueError):
            payload = None
        run_id = payload.get("run_id") if payload else None
        if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
            errors.append("last_success_reference_unreadable")
        else:
            protected.setdefault(run_id, []).append("last-success")

    pin_path = state_root / policy["pin_file"]
    if pin_path.exists() or pin_path.is_symlink():
        payload = None
        try:
            info = pin_path.lstat()
            if (
                not _no_symlink_ancestors(pin_path, state_root)
                or stat.S_ISLNK(info.st_mode)
                or info.st_uid != os.getuid()
            ):
                raise ValueError
            payload = _read_regular_json(pin_path)
        except (OSError, ValueError):
            payload = None
        raw_ids: Any = payload.get("run_ids") if payload else None
        if raw_ids is None and payload:
            raw_ids = payload.get("pins")
        if not isinstance(raw_ids, list):
            errors.append("pinned_reference_unreadable")
        else:
            for run_id in raw_ids:
                if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
                    errors.append("pinned_reference_invalid")
                    continue
                protected.setdefault(run_id, []).append("pinned")
    return set(protected), protected, errors


def _current_observation_id(state_root: Path) -> tuple[str | None, str | None]:
    current_path = state_root / "current.json"
    if not current_path.exists() and not current_path.is_symlink():
        return None, None
    payload = _read_regular_json(current_path)
    if payload is None:
        return None, "current_status_unreadable"
    raw_ref = payload.get("private_observation_ref")
    if not isinstance(raw_ref, str) or not raw_ref.startswith("local://"):
        return None, None
    path = Path(os.path.abspath(raw_ref.removeprefix("local://")))
    observations = Path(os.path.abspath(state_root / "observations"))
    if (
        not _within(path, observations)
        or path.parent != observations
        or not _no_symlink_ancestors(path, state_root)
    ):
        return None, "current_observation_reference_outside_root"
    try:
        info = path.lstat()
    except OSError:
        return None, "current_observation_reference_missing"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return None, "current_observation_reference_unsafe"
    if info.st_uid != os.getuid():
        return None, "current_observation_reference_foreign_owner"
    return path.name, None


def _observation_records(state_root: Path, *, owner_uid: int) -> list[dict[str, Any]]:
    observations = state_root / "observations"
    if not observations.is_dir() or observations.is_symlink():
        return []
    try:
        root_info = observations.lstat()
    except OSError:
        return []
    if root_info.st_uid != owner_uid:
        return []
    root_device = root_info.st_dev
    mount_points = _mount_points()
    if not _mount_boundary_safe(observations, state_root, mount_points):
        return []
    records: list[dict[str, Any]] = []
    try:
        entries = sorted(observations.iterdir(), key=lambda path: path.name)
    except OSError:
        return []
    for path in entries:
        if path.suffix != ".json" or path.is_symlink() or not path.is_file():
            continue
        info = path.lstat()
        if (
            info.st_uid != owner_uid
            or info.st_dev != root_device
            or not _mount_boundary_safe(path, state_root, mount_points)
        ):
            continue
        records.append(
            {
                "name": path.name,
                "path": path,
                "bytes": max(0, int(info.st_blocks)) * 512,
                "logical_bytes": info.st_size,
                "allocated_bytes": max(0, int(info.st_blocks)) * 512,
                "observed_at": datetime.fromtimestamp(info.st_mtime, tz=UTC),
            }
        )
    return records


def _archive_manifest_path(archive_dir: Path) -> Path:
    return archive_dir / "archive-manifest.json"


def _valid_archive(
    archive_dir: Path,
    *,
    owner_uid: int,
    state_root: Path | None = None,
) -> dict[str, Any] | None:
    if not archive_dir.is_dir() or archive_dir.is_symlink():
        return None
    manifest = _read_regular_json(_archive_manifest_path(archive_dir))
    if not manifest or manifest.get("schema_version") != RETENTION_SCHEMA_VERSION:
        return None
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
        return None
    compact_entries = manifest.get("compact_receipts")
    if not isinstance(compact_entries, list):
        return None
    for expected_name in ("input-snapshot.json", "execution-receipt.json"):
        matching = [
            item
            for item in compact_entries
            if isinstance(item, dict) and item.get("name") == expected_name
        ]
        if len(matching) != 1:
            return None
        item = matching[0]
        size_bytes = item.get("size_bytes", -1)
        if (
            not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 0
            or not isinstance(item.get("sha256"), str)
        ):
            return None
        receipt = archive_dir / expected_name
        try:
            info = receipt.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISREG(info.st_mode)
                or info.st_uid != owner_uid
                or info.st_size != size_bytes
                or _file_digest(receipt) != item["sha256"]
            ):
                return None
        except (OSError, TypeError, ValueError):
            return None
    required_entries = manifest.get("required_receipts")
    if not isinstance(required_entries, list):
        return None
    required_dir = archive_dir / "required"
    try:
        required_info = required_dir.lstat()
    except OSError:
        return None
    if (
        stat.S_ISLNK(required_info.st_mode)
        or not stat.S_ISDIR(required_info.st_mode)
        or required_info.st_uid != owner_uid
    ):
        return None
    seen_required: set[str] = set()
    for item in required_entries:
        if not isinstance(item, dict):
            return None
        raw_name = item.get("archive_name")
        relative = _safe_relative_path(raw_name)
        if (
            relative is None
            or len(relative.parts) != 2
            or relative.parts[0] != "required"
            or relative.as_posix() in seen_required
            or not isinstance(item.get("size_bytes"), int)
            or isinstance(item.get("size_bytes"), bool)
            or item.get("size_bytes") < 0
            or not isinstance(item.get("sha256"), str)
            or item.get("mode") not in {"0o600", "0o644"}
        ):
            return None
        seen_required.add(relative.as_posix())
        receipt = archive_dir / relative
        try:
            info = receipt.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISREG(info.st_mode)
                or info.st_uid != owner_uid
                or info.st_size != item["size_bytes"]
                or _file_digest(receipt) != item["sha256"]
            ):
                return None
        except (OSError, TypeError, ValueError):
            return None
    boundary_root = state_root or archive_dir.parent.parent
    measured = _tree_measure(
        archive_dir,
        owner_uid=owner_uid,
        boundary_root=boundary_root,
    )
    if not measured["safe"]:
        return None
    finished_at = _parse_timestamp(manifest.get("finished_at"))
    if finished_at is None:
        return None
    return {
        "run_id": run_id,
        "path": archive_dir,
        "state": "archived",
        "passed": bool(manifest.get("passed")),
        "finished_at": finished_at,
        "total_bytes": measured["allocated_bytes"],
        "allocated_bytes": measured["allocated_bytes"],
        "logical_bytes": measured["logical_bytes"],
        "file_count": measured["files"],
        "safe": True,
        "required_count": len(manifest.get("required_receipts", [])),
        "manifest": manifest,
    }


def _archive_records(state_root: Path, policy: dict[str, Any], *, owner_uid: int) -> list[dict[str, Any]]:
    archive_root = state_root / policy["receipt_archive_root"]
    if not archive_root.is_dir() or archive_root.is_symlink():
        return []
    records: list[dict[str, Any]] = []
    try:
        entries = sorted(archive_root.iterdir(), key=lambda path: path.name)
    except OSError:
        return []
    for path in entries:
        if RUN_ID_RE.fullmatch(path.name) is None:
            continue
        record = _valid_archive(path, owner_uid=owner_uid, state_root=state_root)
        if record is not None:
            records.append(record)
    return records


def _archive_run(
    record: dict[str, Any],
    *,
    state_root: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Archive compact receipts and required evidence before run removal."""

    run_root = record["path"]
    archive_root = state_root / policy["receipt_archive_root"]
    archive_dir = archive_root / record["run_id"]
    if archive_dir.exists() or archive_dir.is_symlink():
        if _valid_archive(archive_dir, owner_uid=os.getuid(), state_root=state_root) is None:
            raise ValueError("receipt archive collision or unsafe archive")
        return {"status": "existing", "path": archive_dir}
    if record["state"] not in {"completed", "failed"} or not record["safe"]:
        raise ValueError("run is not a completed safe owner tree")
    if not _safe_owned_directory(run_root, root=run_root.parent, owner_uid=os.getuid()):
        raise ValueError("run root is not a safe owner directory")

    if not _no_symlink_ancestors(archive_root, state_root) or archive_root.is_symlink():
        raise ValueError("receipt archive root must not be a symlink")
    if archive_root.exists():
        archive_info = archive_root.lstat()
        if not stat.S_ISDIR(archive_info.st_mode) or archive_info.st_uid != os.getuid():
            raise ValueError("receipt archive root is not an owner directory")
    archive_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    archive_root.chmod(0o700)
    archive_dir.mkdir(mode=0o700)
    archive_dir.chmod(0o700)
    try:
        compact_files: list[dict[str, Any]] = []
        for name in ("input-snapshot.json", "execution-receipt.json"):
            source = run_root / name
            info = source.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise ValueError(f"compact receipt is not a regular file: {name}")
            payload = source.read_bytes()
            destination = archive_dir / name
            _atomic_private_bytes(destination, payload)
            if destination.read_bytes() != payload:
                raise ValueError(f"compact receipt copy verification failed: {name}")
            compact_files.append(
                {"name": name, "sha256": _digest(payload), "size_bytes": len(payload)}
            )

        required_receipts: list[dict[str, Any]] = []
        required_dir = archive_dir / "required"
        required_dir.mkdir(mode=0o700)
        for index, source in enumerate(record["required_paths"]):
            if not _within(source, run_root):
                raise ValueError("required receipt leaves run root")
            info = source.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise ValueError("required receipt is not a regular file")
            payload = source.read_bytes()
            source_name = source.name or "receipt"
            destination = required_dir / f"{index:03d}-{source_name}"
            mode = 0o644
            for item in (record.get("execution") or {}).get("receipts", []):
                if not isinstance(item, dict):
                    continue
                raw_item_path = item.get("path")
                if not isinstance(raw_item_path, str):
                    continue
                item_path = Path(raw_item_path)
                if not item_path.is_absolute():
                    item_path = run_root / item_path
                if Path(os.path.abspath(item_path)) == source:
                    if item.get("visibility") == "private":
                        mode = 0o600
                    break
            _atomic_bytes(destination, payload, mode=mode)
            if destination.read_bytes() != payload:
                raise ValueError("required receipt copy verification failed")
            required_receipts.append(
                {
                    "source_name": source_name,
                    "archive_name": destination.relative_to(archive_dir).as_posix(),
                    "sha256": _digest(payload),
                    "size_bytes": len(payload),
                    "mode": oct(mode),
                }
            )
        _atomic_private_json(
            _archive_manifest_path(archive_dir),
            {
                "schema_version": RETENTION_SCHEMA_VERSION,
                "run_id": record["run_id"],
                "finished_at": _timestamp(record["finished_at"]),
                "passed": record["passed"],
                "allocated_bytes": record["allocated_bytes"],
                "logical_bytes": record["logical_bytes"],
                "compact_receipts": compact_files,
                "required_receipts": required_receipts,
            },
        )
    except Exception:
        # The source run remains intact if archive verification fails.  The
        # partial archive is deliberately left for the next plan to classify
        # as a collision rather than silently treating it as valid evidence.
        raise
    return {"status": "created", "path": archive_dir}


def _archive_possible(record: dict[str, Any]) -> bool:
    if record["state"] not in {"completed", "failed"} or not record["safe"]:
        return False
    run_root = record["path"]
    for name in ("input-snapshot.json", "execution-receipt.json"):
        path = run_root / name
        if path.is_symlink() or not path.is_file():
            return False
    return all(
        path.is_file() and not path.is_symlink() and _within(path, run_root)
        for path in record["required_paths"]
    )


def _select_retained(
    records: list[dict[str, Any]],
    *,
    protected_ids: set[str],
    forced_ids: set[str],
    max_runs: int,
    max_bytes: int,
    max_age_seconds: int,
    now: datetime,
    byte_key: str = "compact_bytes",
) -> set[str]:
    keep = set(protected_ids) | set(forced_ids)
    total = sum(
        int(record.get(byte_key, record.get("total_bytes", 0)))
        for record in records
        if record["run_id"] in keep
    )
    ordered = sorted(records, key=lambda record: record["finished_at"], reverse=True)
    for record in ordered:
        run_id = record["run_id"]
        if run_id in keep:
            continue
        if len(keep) >= max_runs:
            continue
        if _run_age_seconds(record, now) > max_age_seconds:
            continue
        size = int(record.get(byte_key, record.get("total_bytes", 0)))
        if total + size > max_bytes:
            continue
        keep.add(run_id)
        total += size
    return keep


def _retention_plan(
    state_root: Path,
    plan: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    """Build a private, deterministic dry-run plan without removing anything."""

    policy = _retention_policy(plan)
    owner_uid = os.getuid()
    protected_ids, protected_reasons, protection_errors = _load_protected_run_ids(
        state_root, policy
    )
    current_observation, observation_error = _current_observation_id(state_root)
    if observation_error:
        protection_errors.append(observation_error)

    runs_root = state_root / "runs"
    run_records: list[dict[str, Any]] = []
    unknown_run_count = 0
    if runs_root.is_dir() and not runs_root.is_symlink():
        try:
            entries = sorted(runs_root.iterdir(), key=lambda path: path.name)
        except OSError:
            entries = []
        for path in entries:
            record = _run_record(
                path,
                policy=policy,
                owner_uid=owner_uid,
                state_root=state_root,
            )
            if record is None:
                if path.is_dir() and not path.is_symlink():
                    unknown_run_count += 1
                continue
            record["protected_reasons"] = list(protected_reasons.get(record["run_id"], []))
            run_records.append(record)

    archive_root = state_root / policy["receipt_archive_root"]
    if archive_root.is_symlink() or not _no_symlink_ancestors(archive_root, state_root):
        protection_errors.append("receipt_archive_root_unsafe")
    elif archive_root.exists():
        archive_info = archive_root.lstat()
        if not stat.S_ISDIR(archive_info.st_mode) or archive_info.st_uid != owner_uid:
            protection_errors.append("receipt_archive_root_unsafe")
    archive_records = _archive_records(state_root, policy, owner_uid=owner_uid)
    for record in archive_records:
        record["protected_reasons"] = list(protected_reasons.get(record["run_id"], []))
    known_reference_ids = {
        record["run_id"] for record in run_records + archive_records
    }
    for run_id in protected_ids:
        if run_id not in known_reference_ids:
            protection_errors.append("protected_reference_missing")

    successful = [record for record in run_records if record["state"] == "completed" and record["passed"]]
    failed = [record for record in run_records if record["state"] == "failed"]
    diagnostic_records = sorted(failed, key=lambda record: record["finished_at"], reverse=True)
    diagnostic_ids = {
        record["run_id"] for record in diagnostic_records[: policy["retain_failed_diagnostics"]]
    }
    successful_keep = _select_retained(
        successful,
        protected_ids=protected_ids,
        forced_ids=set(),
        max_runs=policy["max_successful_runs"],
        max_bytes=policy["max_successful_bytes"],
        max_age_seconds=policy["max_successful_age_seconds"],
        now=now,
    )
    failed_keep = _select_retained(
        failed,
        protected_ids=protected_ids,
        forced_ids=diagnostic_ids,
        max_runs=policy["max_failed_runs"],
        max_bytes=policy["max_failed_bytes"],
        max_age_seconds=policy["max_failed_age_seconds"],
        now=now,
        byte_key="total_bytes",
    )

    operations: list[dict[str, Any]] = []
    run_views: list[dict[str, Any]] = []
    for record in sorted(run_records, key=lambda item: item["run_id"]):
        run_id = record["run_id"]
        protected = bool(record["protected_reasons"])
        keep = run_id in (successful_keep | failed_keep)
        run_cache_allocated = sum(
            item["allocated_bytes"] for item in record.get("cache", [])
        )
        run_cache_logical = sum(
            item["logical_bytes"] for item in record.get("cache", [])
        )
        if record["state"] == "running":
            action = "protect_running"
        elif protected:
            action = "protect_reference"
        elif keep:
            action = "keep_compact"
        elif _archive_possible(record):
            action = "archive_and_remove"
            operations.append(
                {
                    "action": "archive_run",
                    "run_id": run_id,
                    "relative_path": _state_relative(record["path"], state_root),
                    "expected_bytes": record["allocated_bytes"],
                    "expected_logical_bytes": record["logical_bytes"],
                    "cache_allocated_bytes": run_cache_allocated,
                    "cache_logical_bytes": run_cache_logical,
                    "reason": "run_retention_limit",
                }
            )
            operations.append(
                {
                    "action": "remove_run",
                    "run_id": run_id,
                    "relative_path": _state_relative(record["path"], state_root),
                    "expected_bytes": record["allocated_bytes"],
                    "expected_logical_bytes": record["logical_bytes"],
                    "cache_allocated_bytes": run_cache_allocated,
                    "cache_logical_bytes": run_cache_logical,
                    "reason": "run_retention_limit_after_receipt_archive",
                }
            )
        else:
            action = "blocked_required_or_unsafe"

        if keep and not protected and not (
            record["state"] == "failed" and run_id in diagnostic_ids
        ):
            for disposable in record["disposable"]:
                operations.append(
                    {
                        "action": "remove_disposable",
                        "run_id": run_id,
                        "relative_path": (
                            f"{_state_relative(record['path'], state_root)}/"
                            f"{disposable['relative_path']}"
                        ),
                        "expected_bytes": disposable["allocated_bytes"],
                        "expected_logical_bytes": disposable["logical_bytes"],
                        "cache_allocated_bytes": _cache_measure_for_path(
                            record, disposable["relative_path"]
                        )[0],
                        "cache_logical_bytes": _cache_measure_for_path(
                            record, disposable["relative_path"]
                        )[1],
                        "reason": f"completed_{disposable['kind']}",
                    }
                )
        run_views.append(
            {
                "run_id": run_id,
                "state": record["state"],
                "passed": record["passed"],
                "finished_at": _timestamp(record["finished_at"]),
                "total_bytes": record["allocated_bytes"],
                "allocated_bytes": record["allocated_bytes"],
                "logical_bytes": record["logical_bytes"],
                "compact_bytes": record["compact_allocated_bytes"],
                "compact_allocated_bytes": record["compact_allocated_bytes"],
                "compact_logical_bytes": record["compact_logical_bytes"],
                "disposable_bytes": sum(
                    item["allocated_bytes"] for item in record["disposable"]
                ),
                "disposable_allocated_bytes": sum(
                    item["allocated_bytes"] for item in record["disposable"]
                ),
                "disposable_logical_bytes": sum(
                    item["logical_bytes"] for item in record["disposable"]
                ),
                "cache": record.get("cache", []),
                "cache_errors": record.get("cache_errors", []),
                "cache_allocated_bytes": run_cache_allocated,
                "cache_logical_bytes": run_cache_logical,
                "disposable": record["disposable"],
                "required_evidence_count": len(record["required_paths"]),
                "protected_reasons": record["protected_reasons"],
                "safe": record["safe"],
                "retention_action": action,
                "disposable_errors": record["disposable_errors"],
            }
        )

    # Existing receipt archives are compact and can be expired independently
    # of the live run root.  A pinned or last-success archive remains forever
    # eligible for reference protection.
    archive_successful = [record for record in archive_records if record["passed"]]
    archive_failed = [record for record in archive_records if not record["passed"]]
    archive_success_keep = _select_retained(
        archive_successful,
        protected_ids=protected_ids,
        forced_ids=set(),
        max_runs=policy["max_successful_runs"],
        max_bytes=policy["max_successful_bytes"],
        max_age_seconds=policy["max_successful_age_seconds"],
        now=now,
        byte_key="total_bytes",
    )
    archive_failed_keep = _select_retained(
        archive_failed,
        protected_ids=protected_ids,
        forced_ids=set(),
        max_runs=policy["max_failed_runs"],
        max_bytes=policy["max_failed_bytes"],
        max_age_seconds=policy["max_failed_age_seconds"],
        now=now,
        byte_key="total_bytes",
    )
    archive_views: list[dict[str, Any]] = []
    for record in sorted(archive_records, key=lambda item: item["run_id"]):
        run_id = record["run_id"]
        protected = bool(record["protected_reasons"])
        keep = run_id in (archive_success_keep | archive_failed_keep)
        action = "protect_reference" if protected else "keep_archive" if keep else "remove_archive"
        if not protected and not keep:
            operations.append(
                {
                    "action": "remove_archive",
                    "run_id": run_id,
                    "relative_path": _state_relative(record["path"], state_root),
                    "expected_bytes": record["allocated_bytes"],
                    "expected_logical_bytes": record["logical_bytes"],
                    "reason": "receipt_archive_retention_limit",
                }
            )
        archive_views.append(
            {
                "run_id": run_id,
                "passed": record["passed"],
                "finished_at": _timestamp(record["finished_at"]),
                "total_bytes": record["allocated_bytes"],
                "allocated_bytes": record["allocated_bytes"],
                "logical_bytes": record["logical_bytes"],
                "required_evidence_count": record["required_count"],
                "protected_reasons": record["protected_reasons"],
                "retention_action": action,
            }
        )

    observations = _observation_records(state_root, owner_uid=owner_uid)
    observation_keep_names = {current_observation} if current_observation else set()
    observation_total = sum(
        item["allocated_bytes"]
        for item in observations
        if item["name"] in observation_keep_names
    )
    for item in sorted(observations, key=lambda value: value["observed_at"], reverse=True):
        if item["name"] in observation_keep_names:
            continue
        if len(observation_keep_names) >= policy["max_observations"]:
            continue
        if max(0, int((now - item["observed_at"]).total_seconds())) > policy["max_observation_age_seconds"]:
            continue
        if observation_total + item["allocated_bytes"] > policy["max_observation_bytes"]:
            continue
        observation_keep_names.add(item["name"])
        observation_total += item["allocated_bytes"]
    observation_views: list[dict[str, Any]] = []
    for item in sorted(observations, key=lambda value: value["name"]):
        keep = item["name"] in observation_keep_names
        if not keep:
            operations.append(
                {
                    "action": "remove_observation",
                    "relative_path": _state_relative(item["path"], state_root),
                    "expected_bytes": item["allocated_bytes"],
                    "expected_logical_bytes": item["logical_bytes"],
                    "reason": "observation_retention_limit",
                }
            )
        observation_views.append(
            {
                "name": item["name"],
                "bytes": item["allocated_bytes"],
                "allocated_bytes": item["allocated_bytes"],
                "logical_bytes": item["logical_bytes"],
                "observed_at": _timestamp(item["observed_at"]),
                "protected": item["name"] == current_observation,
                "retention_action": "keep" if keep else "remove",
            }
        )

    # An unreadable reference collection is fail-closed: report candidates for
    # review, but provide no destructive operation until the reference is fixed.
    if protection_errors:
        operations = []
    operations.sort(
        key=lambda item: {
            "archive_run": 0,
            "remove_disposable": 1,
            "remove_run": 2,
            "remove_observation": 3,
            "remove_archive": 4,
        }.get(item["action"], 9)
    )
    result: dict[str, Any] = {
        "schema_version": RETENTION_SCHEMA_VERSION,
        "generated_at": _timestamp(now),
        "policy": policy,
        "protected_run_ids": sorted(protected_ids),
        "blocked": sorted(set(protection_errors)),
        "runs": run_views,
        "archives": archive_views,
        "observations": observation_views,
        "operations": operations,
        "summary": {
            "runs_scanned": len(run_records),
            "completed_runs": sum(item["state"] == "completed" for item in run_records),
            "failed_runs": len(failed),
            "running_runs": sum(item["state"] == "running" for item in run_records),
            "unknown_run_roots": unknown_run_count,
            "archives_scanned": len(archive_records),
            "observations_scanned": len(observations),
            "disposable_candidate_bytes": sum(
                item["expected_bytes"]
                for item in operations
                if item["action"] == "remove_disposable"
            ),
            "disposable_candidate_allocated_bytes": sum(
                item["expected_bytes"]
                for item in operations
                if item["action"] == "remove_disposable"
            ),
            "disposable_candidate_logical_bytes": sum(
                item.get("expected_logical_bytes", 0)
                for item in operations
                if item["action"] == "remove_disposable"
            ),
            "disposable_candidate_cache_allocated_bytes": sum(
                item.get("cache_allocated_bytes", 0)
                for item in operations
                if item["action"] == "remove_disposable"
            ),
            "disposable_candidate_cache_logical_bytes": sum(
                item.get("cache_logical_bytes", 0)
                for item in operations
                if item["action"] == "remove_disposable"
            ),
            "run_removal_candidate_bytes": sum(
                item["expected_bytes"] for item in operations if item["action"] == "remove_run"
            ),
            "run_removal_candidate_allocated_bytes": sum(
                item["expected_bytes"] for item in operations if item["action"] == "remove_run"
            ),
            "run_removal_candidate_logical_bytes": sum(
                item.get("expected_logical_bytes", 0)
                for item in operations
                if item["action"] == "remove_run"
            ),
            "run_removal_candidate_cache_allocated_bytes": sum(
                item.get("cache_allocated_bytes", 0)
                for item in operations
                if item["action"] == "remove_run"
            ),
            "run_removal_candidate_cache_logical_bytes": sum(
                item.get("cache_logical_bytes", 0)
                for item in operations
                if item["action"] == "remove_run"
            ),
            "observation_removal_candidate_bytes": sum(
                item["expected_bytes"]
                for item in operations
                if item["action"] == "remove_observation"
            ),
            "observation_removal_candidate_allocated_bytes": sum(
                item["expected_bytes"]
                for item in operations
                if item["action"] == "remove_observation"
            ),
            "observation_removal_candidate_logical_bytes": sum(
                item.get("expected_logical_bytes", 0)
                for item in operations
                if item["action"] == "remove_observation"
            ),
            "archive_removal_candidate_bytes": sum(
                item["expected_bytes"]
                for item in operations
                if item["action"] == "remove_archive"
            ),
            "archive_removal_candidate_allocated_bytes": sum(
                item["expected_bytes"]
                for item in operations
                if item["action"] == "remove_archive"
            ),
            "archive_removal_candidate_logical_bytes": sum(
                item.get("expected_logical_bytes", 0)
                for item in operations
                if item["action"] == "remove_archive"
            ),
            "operations": len(operations),
        },
    }
    result["plan_digest"] = _digest(result)
    return result


def _fresh_run_for_operation(
    state_root: Path,
    run_id: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    run_path = state_root / "runs" / run_id
    record = _run_record(
        run_path,
        policy=policy,
        owner_uid=os.getuid(),
        state_root=state_root,
    )
    if record is None or record["state"] not in {"completed", "failed"}:
        raise ValueError("run is missing, running, or not a completed owner run")
    return record


def _apply_retention_operation(
    operation: dict[str, Any],
    *,
    state_root: Path,
    policy: dict[str, Any],
    protected_ids: set[str],
) -> None:
    action = operation["action"]
    run_id = operation.get("run_id")
    if isinstance(run_id, str) and run_id in protected_ids:
        raise ValueError("protected run reference changed during apply")
    expected = int(operation.get("expected_bytes", -1))
    if action == "archive_run":
        record = _fresh_run_for_operation(state_root, run_id, policy)
        if (
            record["allocated_bytes"] != expected
            or record["logical_bytes"]
            != int(operation.get("expected_logical_bytes", record["logical_bytes"]))
        ):
            raise ValueError("run changed since retention plan")
        _archive_run(record, state_root=state_root, policy=policy)
        return
    if action == "remove_disposable":
        record = _fresh_run_for_operation(state_root, run_id, policy)
        relative = Path(operation["relative_path"]).relative_to(Path("runs") / run_id)
        if _safe_relative_path(relative.as_posix()) is None:
            raise ValueError("disposable path is unsafe")
        candidate = record["path"] / relative
        if _protected_path(candidate, record["required_paths"]):
            raise ValueError("disposable path contains required evidence")
        if not _safe_owned_directory(candidate, root=record["path"], owner_uid=os.getuid()):
            raise ValueError("disposable path is not a safe owner directory")
        measured = _tree_measure(
            candidate,
            owner_uid=os.getuid(),
            boundary_root=state_root,
        )
        if (
            not measured["safe"]
            or measured["allocated_bytes"] != expected
            or measured["logical_bytes"]
            != int(operation.get("expected_logical_bytes", measured["logical_bytes"]))
        ):
            raise ValueError("disposable path changed since retention plan")
        if not shutil.rmtree.avoids_symlink_attacks:
            raise ValueError("rmtree lacks symlink-attack protection")
        shutil.rmtree(candidate)
        return
    if action == "remove_run":
        record = _fresh_run_for_operation(state_root, run_id, policy)
        if (
            not record["safe"]
            or record["allocated_bytes"] != expected
            or record["logical_bytes"]
            != int(operation.get("expected_logical_bytes", record["logical_bytes"]))
        ):
            raise ValueError("run changed since retention plan")
        archive_dir = state_root / policy["receipt_archive_root"] / run_id
        if _valid_archive(archive_dir, owner_uid=os.getuid(), state_root=state_root) is None:
            raise ValueError("required receipt archive is missing")
        if not _safe_owned_directory(record["path"], root=record["path"].parent, owner_uid=os.getuid()):
            raise ValueError("run path is not a safe owner directory")
        if not shutil.rmtree.avoids_symlink_attacks:
            raise ValueError("rmtree lacks symlink-attack protection")
        shutil.rmtree(record["path"])
        return
    if action == "remove_archive":
        if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
            raise ValueError("archive run id is unsafe")
        archive_dir = state_root / policy["receipt_archive_root"] / run_id
        record = _valid_archive(archive_dir, owner_uid=os.getuid(), state_root=state_root)
        if record is None or record["allocated_bytes"] != expected:
            raise ValueError("archive changed since retention plan")
        if record["logical_bytes"] != int(
            operation.get("expected_logical_bytes", record["logical_bytes"])
        ):
            raise ValueError("archive changed since retention plan")
        if not shutil.rmtree.avoids_symlink_attacks:
            raise ValueError("rmtree lacks symlink-attack protection")
        shutil.rmtree(archive_dir)
        return
    if action == "remove_observation":
        relative = _safe_relative_path(operation["relative_path"])
        if relative is None or relative.parts[0] != "observations" or len(relative.parts) != 2:
            raise ValueError("observation path is unsafe")
        path = state_root / relative
        current_observation, current_error = _current_observation_id(state_root)
        if current_error:
            raise ValueError(current_error)
        if current_observation == path.name:
            raise ValueError("observation is the current protected reference")
        if not _no_symlink_ancestors(path, state_root):
            raise ValueError("observation path has a symlinked ancestor")
        observations = state_root / "observations"
        observations_info = observations.lstat()
        if (
            stat.S_ISLNK(observations_info.st_mode)
            or not stat.S_ISDIR(observations_info.st_mode)
            or observations_info.st_uid != os.getuid()
            or not _mount_boundary_safe(observations, state_root, _mount_points())
        ):
            raise ValueError("observations root is unsafe")
        info = path.lstat()
        allocated = max(0, int(info.st_blocks)) * 512
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_dev != observations_info.st_dev
            or not _mount_boundary_safe(path, state_root, _mount_points())
            or allocated != expected
            or info.st_size != int(operation.get("expected_logical_bytes", info.st_size))
        ):
            raise ValueError("observation changed since retention plan")
        if info.st_uid != os.getuid():
            raise ValueError("observation is not owner-created")
        path.unlink()
        return
    raise ValueError(f"unsupported retention action: {action}")


def _apply_retention(
    state_root: Path,
    plan: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    retention = _retention_plan(state_root, plan, now=now)
    policy = _retention_policy(plan)
    _, _, protection_errors = _load_protected_run_ids(state_root, policy)
    errors = list(retention.get("blocked", [])) + protection_errors
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    if not errors:
        for operation in retention["operations"]:
            fresh_protected_ids, _, fresh_errors = _load_protected_run_ids(
                state_root, policy
            )
            if fresh_errors:
                errors.extend(fresh_errors)
                break
            try:
                _apply_retention_operation(
                    operation,
                    state_root=state_root,
                    policy=policy,
                    protected_ids=fresh_protected_ids,
                )
            except Exception as exc:
                skipped.append(
                    {
                        "action": operation["action"],
                        "run_id": operation.get("run_id"),
                        "relative_path": operation.get("relative_path"),
                        "error_class": type(exc).__name__,
                    }
                )
            else:
                applied.append(
                    {
                        "action": operation["action"],
                        "run_id": operation.get("run_id"),
                        "relative_path": operation.get("relative_path"),
                    }
                )
    result = {
        "schema_version": RETENTION_SCHEMA_VERSION,
        "applied_at": _timestamp(now),
        "plan_digest": retention["plan_digest"],
        "planned_operations": len(retention["operations"]),
        "applied_operations": len(applied),
        "skipped_operations": len(skipped),
        "errors": sorted(set(errors)),
        "applied": applied,
        "skipped": skipped,
    }
    _atomic_private_json(state_root / "retention-apply.json", result)
    return result


def _status_digest(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "status_digest"}
    return _digest(unsigned)


def _public_safe_status(status: dict[str, Any]) -> dict[str, Any]:
    """Remove machine-local paths and raw errors from the publishable projection."""

    public = dict(status)
    public["private_observation_ref"] = (
        "private://protocol-watch-observation/"
        + status["private_observation_sha256"].removeprefix("sha256:")
    )
    public["inputs"] = [
        {
            "input_id": item["input_id"],
            "kind": item["kind"],
            "required": item["required"],
            "status": item["status"],
            "identity_digest": _digest(item.get("observation", {})),
            **(
                {"error_class": str(item.get("error", "blocked")).split(":", 1)[0]}
                if item["status"] not in {"passed", "skipped"}
                else {}
            ),
        }
        for item in status["inputs"]
    ]
    public["receipts"] = [
        {
            key: value
            for key, value in receipt.items()
            if key
            in {
                "step_id",
                "receipt_id",
                "visibility",
                "returncode",
                "sha256",
                "size_bytes",
                "started_at",
                "finished_at",
                "argv_sha256",
                "stdout_sha256",
                "stderr_sha256",
            }
        }
        for receipt in status["receipts"]
    ]
    failure_codes = [
        f"required_input_blocked:{item['input_id']}"
        for item in status["inputs"]
        if item["required"] and item["status"] != "passed"
    ]
    if status["ttl"].get("status") != "passed":
        failure_codes.append("evidence_ttl_unavailable")
    if status["execution_state"] == "awaiting_runtime_config":
        failure_codes.append("private_runtime_config_unavailable")
    if status["protected_paths_unchanged"] is False:
        failure_codes.append("protected_production_path_changed")
    if status["execution_state"] == "lab_failed":
        failure_codes.append("configured_lab_failed")
    public["failures"] = list(dict.fromkeys(failure_codes))
    if "retention" in status:
        retention = status["retention"]
        public["retention"] = {
            key: retention.get(key)
            for key in (
                "mode",
                "plan_digest",
                "planned_operations",
                "applied_operations",
                "skipped_operations",
            )
            if key in retention
        }
        public["retention"]["errors"] = [
            str(item).split(":", 1)[0]
            for item in retention.get("errors", [])
            if isinstance(item, str)
        ]
    public["status_digest"] = _status_digest(public)
    return public


def run(
    *,
    plan_path: Path,
    state_root: Path,
    runtime_config: Path | None,
    execute: bool,
    offline: bool,
    timeout: int,
    apply_retention: bool = False,
    now: datetime | None = None,
    urlopen: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    observed_now = now or _now()
    plan = _read_json(plan_path)
    base = plan_path.parent
    if plan.get("schema_version") != "abyss_mcp_protocol_watch_plan_v1":
        raise ValueError("unsupported protocol watch plan schema")
    input_ids = [item["input_id"] for item in plan["inputs"]]
    if len(input_ids) != len(set(input_ids)):
        raise ValueError("protocol watch input_id values must be unique")
    policy = _retention_policy(plan)
    state_root = Path(os.path.abspath(state_root))
    if state_root.is_symlink():
        raise ValueError("state root must not be a symlink")
    if state_root.exists():
        state_info = state_root.lstat()
        if not stat.S_ISDIR(state_info.st_mode):
            raise ValueError("state root must be a directory")
        if state_info.st_uid != os.getuid():
            raise ValueError("state root is not owner-created")
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_root.chmod(0o700)
    lock_path = state_root / ".lock"
    if lock_path.is_symlink() or (
        lock_path.exists() and not stat.S_ISREG(lock_path.lstat().st_mode)
    ):
        raise ValueError("state lock must be a regular non-symlink file")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        records: list[dict[str, Any]] = []
        for item in plan["inputs"]:
            if offline and item["kind"] == "https_json":
                records.append(
                    {
                        "input_id": item["input_id"],
                        "kind": item["kind"],
                        "required": item["required"],
                        "status": "blocked" if item["required"] else "skipped",
                        "error": "offline observation requested",
                    }
                )
            else:
                records.append(
                    _observe_input(item, base=base, timeout=timeout, urlopen=urlopen)
                )
        input_fingerprints = _input_fingerprints(records)
        snapshot_digest = _digest(input_fingerprints)
        observation_ready = not any(
            item["required"] and item["status"] != "passed" for item in records
        )
        ttl = _ttl(plan, base, observed_now)
        observation_path = (
            state_root
            / "observations"
            / (
                observed_now.strftime("%Y%m%dT%H%M%S.%fZ")
                + "-"
                + snapshot_digest.removeprefix("sha256:")[:12]
                + ".json"
            )
        )
        observation_sha256 = _immutable_private_json(
            observation_path,
            {
                "schema_version": "abyss_mcp_protocol_watch_observation_v1",
                "plan_id": plan["plan_id"],
                "observed_at": _timestamp(observed_now),
                "input_snapshot_digest": snapshot_digest,
                "input_fingerprints": input_fingerprints,
                "inputs": records,
                "ttl": ttl,
            },
        )
        if ttl["status"] != "passed":
            observation_ready = False
        previous_path = state_root / "last-success.json"
        previous = _read_regular_json(previous_path)
        previous_digest = previous.get("input_snapshot_digest") if previous else None
        trigger_reasons: list[str] = []
        if previous_digest is None:
            trigger_reasons.append("no_successful_baseline")
        elif previous_digest != snapshot_digest:
            previous_inputs = previous.get("input_fingerprints", {})
            for input_id in sorted(set(previous_inputs) | set(input_fingerprints)):
                if previous_inputs.get(input_id) != input_fingerprints.get(input_id):
                    trigger_reasons.append(f"input_changed:{input_id}")
        if ttl.get("refresh_due"):
            trigger_reasons.append("evidence_ttl_due")
        triggered = bool(trigger_reasons)
        failures = [
            f"input {item['input_id']}: {item.get('error', 'blocked')}"
            for item in records
            if item["required"] and item["status"] != "passed"
        ]
        if ttl["status"] != "passed":
            failures.append(f"ttl: {ttl['error']}")
        try:
            protocol_status = _load_protocol_status(plan, base)
        except Exception as exc:
            protocol_status = None
            observation_ready = False
            failures.append(f"protocol status: {type(exc).__name__}: {exc}")
        execution_state = "trigger_pending" if triggered else "no_change"
        run_id: str | None = None
        protected_unchanged: bool | None = None
        receipts: list[dict[str, Any]] = []
        suite_passed = False
        if not observation_ready:
            execution_state = "observation_blocked"
        elif triggered and execute:
            if runtime_config is None or not runtime_config.is_file():
                execution_state = "awaiting_runtime_config"
                failures.append("private runtime config is unavailable")
            else:
                info = runtime_config.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    raise ValueError("runtime config must be a regular non-symlink file")
                if stat.S_IMODE(info.st_mode) != 0o600:
                    raise ValueError("runtime config must be mode 0600")
                runtime = _read_json(runtime_config)
                if runtime.get("schema_version") != "abyss_mcp_protocol_watch_runtime_v1":
                    raise ValueError("unsupported protocol watch runtime schema")
                run_id = observed_now.strftime("%Y%m%dT%H%M%S.%fZ")
                runs_root = state_root / "runs"
                if runs_root.is_symlink() or (
                    runs_root.exists() and not runs_root.is_dir()
                ):
                    raise ValueError("runs root must be a regular owner directory")
                runs_root.mkdir(parents=True, exist_ok=True, mode=0o700)
                runs_root.chmod(0o700)
                run_root = runs_root / run_id
                if run_root.exists() or run_root.is_symlink():
                    raise ValueError("run id already exists")
                run_root.mkdir(parents=True, mode=0o700)
                _atomic_private_json(
                    run_root / "run-state.json",
                    {
                        "schema_version": RUN_STATE_SCHEMA_VERSION,
                        "run_id": run_id,
                        "state": "running",
                        "started_at": _timestamp(observed_now),
                        "finished_at": None,
                        "retention_policy_digest": _digest(policy),
                        "disposable_roots": policy["disposable_roots"],
                        "diagnostic_roots": policy["diagnostic_roots"],
                    },
                )
                _atomic_private_json(
                    run_root / "input-snapshot.json",
                    {
                        "observed_at": _timestamp(observed_now),
                        "input_snapshot_digest": snapshot_digest,
                        "inputs": records,
                        "ttl": ttl,
                    },
                )
                try:
                    suite_passed, protected_unchanged, receipts, suite_failures = _execute_suite(
                        runtime,
                        run_root=run_root,
                    )
                except Exception as exc:
                    suite_passed = False
                    protected_unchanged = None
                    receipts = []
                    suite_failures = [
                        f"suite failed: {type(exc).__name__}: {exc}"
                    ]
                failures.extend(suite_failures)
                execution_state = "lab_passed" if suite_passed else "lab_failed"
                _atomic_private_json(
                    run_root / "execution-receipt.json",
                    {
                        "run_id": run_id,
                        "passed": suite_passed,
                        "protected_paths_unchanged": protected_unchanged,
                        "receipts": receipts,
                        "failures": suite_failures,
                    },
                )
                _atomic_private_json(
                    run_root / "run-state.json",
                    {
                        "schema_version": RUN_STATE_SCHEMA_VERSION,
                        "run_id": run_id,
                        "state": "completed" if suite_passed else "failed",
                        "started_at": _timestamp(observed_now),
                        "finished_at": _timestamp(observed_now),
                        "passed": suite_passed,
                        "retention_policy_digest": _digest(policy),
                        "disposable_roots": policy["disposable_roots"],
                        "diagnostic_roots": policy["diagnostic_roots"],
                    },
                )
        if suite_passed:
            _atomic_private_json(
                previous_path,
                {
                    "schema_version": "abyss_mcp_protocol_watch_success_v1",
                    "accepted_at": _timestamp(observed_now),
                    "input_snapshot_digest": snapshot_digest,
                    "input_fingerprints": input_fingerprints,
                    "run_id": run_id,
                    "receipts": receipts,
                },
            )
        retention_result: dict[str, Any] | None = None
        if apply_retention:
            retention_result = _apply_retention(
                state_root,
                plan,
                now=observed_now,
            )
            retention_status = {
                "mode": "applied",
                "plan_digest": retention_result["plan_digest"],
                "planned_operations": retention_result["planned_operations"],
                "applied_operations": retention_result["applied_operations"],
                "skipped_operations": retention_result["skipped_operations"],
                "errors": retention_result["errors"],
            }
        else:
            retention_status = {
                "mode": "disabled",
                "plan_digest": None,
                "planned_operations": 0,
                "applied_operations": 0,
                "skipped_operations": 0,
                "errors": [],
            }
        status: dict[str, Any] = {
            "schema_version": "abyss_mcp_protocol_watch_status_v1",
            "plan_id": plan["plan_id"],
            "observed_at": _timestamp(observed_now),
            "input_snapshot_digest": snapshot_digest,
            "private_observation_ref": f"local://{observation_path}",
            "private_observation_sha256": observation_sha256,
            "previous_success_digest": previous_digest,
            "observation_ready": observation_ready,
            "triggered": triggered,
            "trigger_reasons": trigger_reasons,
            "execution_state": execution_state,
            "run_id": run_id,
            "inputs": records,
            "ttl": ttl,
            "verdicts": _verdicts(protocol_status, observation_ready=observation_ready),
            "production_automatically_changed": False,
            "protected_paths_unchanged": protected_unchanged,
            "receipts": receipts,
            "failures": failures,
            "claim_limits": plan["claim_limits"],
            "retention": retention_status,
        }
        status["status_digest"] = _status_digest(status)
        _atomic_private_json(state_root / "current.json", status)
        _atomic_json(
            state_root / "public-safe.json",
            _public_safe_status(status),
            mode=0o644,
        )
        return status
    finally:
        os.close(lock_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--apply-retention",
        action="store_true",
        help="apply the configured retention policy after the watcher pass",
    )
    parser.add_argument(
        "--retention-plan",
        action="store_true",
        help="print a private dry-run retention plan without removing anything",
    )
    parser.add_argument(
        "--retention-apply",
        action="store_true",
        help="apply a freshly recomputed retention plan without running the lab",
    )
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    if args.retention_plan and args.retention_apply:
        parser.error("--retention-plan and --retention-apply are mutually exclusive")
    if (args.retention_plan or args.retention_apply) and (
        args.execute or args.apply_retention or args.offline
    ):
        parser.error("retention-only modes cannot be combined with watcher execution")
    # Keep the lexical state-root path so the symlink guard can reject a
    # caller-supplied alias instead of silently resolving it first.
    plan_path = Path(os.path.abspath(args.plan))
    state_root = Path(os.path.abspath(args.state_root))
    if args.retention_plan or args.retention_apply:
        plan = _read_json(plan_path)
        with _state_lock(state_root):
            result = (
                _apply_retention(state_root, plan, now=_now())
                if args.retention_apply
                else _retention_plan(state_root, plan, now=_now())
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if not result.get("blocked") and not result.get("errors") and not result.get("skipped_operations") else 1
    status = run(
        plan_path=plan_path,
        state_root=state_root,
        runtime_config=args.runtime_config.resolve() if args.runtime_config else None,
        execute=args.execute,
        offline=args.offline,
        timeout=args.timeout,
        apply_retention=args.apply_retention,
    )
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0 if (
        status["execution_state"] not in {"observation_blocked", "lab_failed"}
        and not status["retention"]["errors"]
        and not status["retention"]["skipped_operations"]
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
