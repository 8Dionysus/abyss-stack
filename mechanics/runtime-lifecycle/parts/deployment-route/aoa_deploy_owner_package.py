#!/usr/bin/env python3
"""Prepare, atomically activate, and roll back an owner-source release.

This route is deliberately narrower than an artifact installer.  An external
admission receipt binds an exact clean Git commit/tree to a destination; this
module then stages a self-contained Git release and switches one destination
symlink.  It never installs dependencies, syncs Configs, starts services, or
claims live/runtime/semantic acceptance.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - the owner target is Linux
    fcntl = None  # type: ignore[assignment]


ADMISSION_SCHEMA = "abyss_stack_owner_source_deployment_admission_v1"
PREPARE_SCHEMA = "abyss_stack_owner_source_prepare_receipt_v1"
ACTIVATE_SCHEMA = "abyss_stack_owner_source_activate_receipt_v1"
ROLLBACK_SCHEMA = "abyss_stack_owner_source_rollback_receipt_v1"
ERROR_SCHEMA = "abyss_stack_owner_source_deployment_error_v1"
SOURCE_ROUTE_ADMISSION_KIND = "owner_source_deployment_route"
ALLOWED_AUTHORITY_CEILINGS = {
    "disposable-source-package-canary",
    "installed-source-package-activation",
}
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class DeploymentError(RuntimeError):
    """A fail-closed, machine-readable route rejection."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        {key: value for key, value in payload.items() if key != "receipt_digest"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise DeploymentError("invalid_timestamp", f"{field} must be an ISO-8601 string")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DeploymentError("invalid_timestamp", f"{field} is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DeploymentError("invalid_timestamp", f"{field} must carry a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _absolute_path(value: str | Path, field: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise DeploymentError("path_not_absolute", f"{field} must be absolute: {path}")
    return Path(os.path.abspath(os.fspath(path)))


def _existing_path(value: str | Path, field: str) -> Path:
    path = _absolute_path(value, field)
    if not path.exists():
        raise DeploymentError("path_missing", f"{field} does not exist: {path}")
    return path.resolve()


def _validate_owner(owner_repo: str) -> str:
    if not OWNER_RE.fullmatch(owner_repo):
        raise DeploymentError("invalid_owner_repo", f"unsafe owner repo name: {owner_repo!r}")
    return owner_repo


def _validate_commit(value: str, field: str) -> str:
    if not isinstance(value, str) or not SHA1_RE.fullmatch(value):
        raise DeploymentError("invalid_git_identity", f"{field} must be a 40-character SHA-1")
    return value


def _run_git(repo: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise DeploymentError("git_unavailable", str(exc)) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise DeploymentError("git_command_failed", f"git {' '.join(args)}: {detail[-800:]}")
    return completed.stdout.strip()


def _git_status(repo: Path) -> str:
    return _run_git(repo, "status", "--porcelain=v1", "--untracked-files=all", "--ignored")


def _git_identity(repo: Path) -> dict[str, str]:
    if not (repo / ".git").exists():
        raise DeploymentError("not_git_checkout", f"not a Git checkout: {repo}")
    root = Path(_run_git(repo, "rev-parse", "--show-toplevel")).resolve()
    if root != repo.resolve():
        raise DeploymentError("git_root_mismatch", f"Git root is {root}, expected {repo.resolve()}")
    head = _run_git(repo, "rev-parse", "HEAD")
    tree = _run_git(repo, "rev-parse", "HEAD^{tree}")
    return {"ref": _validate_commit(head, "HEAD"), "tree": _validate_commit(tree, "tree")}


def _reject_submodules(repo: Path) -> None:
    listing = _run_git(repo, "ls-tree", "-r", "HEAD")
    for line in listing.splitlines():
        fields = line.split(None, 3)
        if fields and fields[0] == "160000":
            raise DeploymentError("submodules_not_supported", f"submodule entry in {repo}")


def _verify_clean_identity(repo: Path, expected_ref: str, expected_tree: str) -> dict[str, str]:
    if _git_status(repo):
        raise DeploymentError("dirty_source", f"Git checkout is dirty: {repo}")
    identity = _git_identity(repo)
    if identity["ref"] != expected_ref:
        raise DeploymentError(
            "source_ref_mismatch",
            f"{repo} HEAD {identity['ref']} != requested {expected_ref}",
        )
    if identity["tree"] != expected_tree:
        raise DeploymentError(
            "source_tree_mismatch",
            f"{repo} tree {identity['tree']} != requested {expected_tree}",
        )
    _reject_submodules(repo)
    return identity


def _load_json(path: Path, field: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except FileNotFoundError as exc:
        raise DeploymentError("receipt_missing", f"{field} does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeploymentError("invalid_json", f"cannot read {field}: {path}") from exc
    if not isinstance(payload, dict):
        raise DeploymentError("invalid_json_shape", f"{field} must be a JSON object")
    return payload, raw


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path = _absolute_path(path, "receipt path")
    with_digest = dict(payload)
    with_digest["receipt_digest"] = _digest_payload(with_digest)
    data = json.dumps(
        with_digest,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        os.chmod(temporary, 0o600)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise DeploymentError("receipt_write_failed", f"{path}: {exc}") from exc
    return with_digest


def _fsync_directory(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _verify_receipt_digest(payload: dict[str, Any], field: str) -> None:
    supplied = payload.get("receipt_digest")
    if not isinstance(supplied, str) or supplied != _digest_payload(payload):
        raise DeploymentError("receipt_digest_mismatch", f"{field} is not self-consistent")


def _canonical_admission_path(value: str, field: str) -> str:
    return os.path.abspath(os.fspath(_absolute_path(value, field)))


def _load_admission(
    path: Path,
    *,
    owner_repo: str,
    source_root: Path,
    source_ref: str,
    source_tree: str,
    destination: Path,
) -> tuple[dict[str, Any], str]:
    payload, raw = _load_json(path, "admission receipt")
    if payload.get("schema_version") != ADMISSION_SCHEMA:
        raise DeploymentError("admission_schema_mismatch", "unsupported admission schema")
    if payload.get("admission_kind") != SOURCE_ROUTE_ADMISSION_KIND:
        raise DeploymentError("admission_kind_mismatch", "admission is not for the owner-source route")
    if payload.get("status") != "admitted":
        raise DeploymentError("admission_not_admitted", "admission status is not admitted")
    for key in ("admission_id", "admission_ref", "owner_repo", "source_root", "source_ref", "source_tree", "destination", "authority_ceiling", "issued_at", "expires_at"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise DeploymentError("admission_field_missing", f"admission field is missing: {key}")
    if payload["owner_repo"] != owner_repo:
        raise DeploymentError("admission_owner_mismatch", "admission owner does not match request")
    if _canonical_admission_path(payload["source_root"], "admission source_root") != os.fspath(source_root):
        raise DeploymentError("admission_source_mismatch", "admission source root does not match request")
    if _canonical_admission_path(payload["destination"], "admission destination") != os.fspath(destination):
        raise DeploymentError("admission_destination_mismatch", "admission destination does not match request")
    if payload["source_ref"] != source_ref or payload["source_tree"] != source_tree:
        raise DeploymentError("admission_identity_mismatch", "admission Git identity does not match request")
    if payload["authority_ceiling"] not in ALLOWED_AUTHORITY_CEILINGS:
        raise DeploymentError("admission_authority_invalid", "unknown admission authority ceiling")
    issued = _timestamp(payload["issued_at"], "issued_at")
    expires = _timestamp(payload["expires_at"], "expires_at")
    now = _utc_now()
    if expires <= issued or now >= expires:
        raise DeploymentError("admission_stale", "admission receipt is expired")
    if issued > now + timedelta(minutes=5):
        raise DeploymentError("admission_from_future", "admission receipt is not yet valid")
    return payload, _digest_bytes(raw)


def _default_release_root(destination: Path, owner_repo: str) -> Path:
    return destination.parent / ".abyss-stack-owner-deploy" / owner_repo / "releases"


def _default_receipt_dir(destination: Path, owner_repo: str) -> Path:
    return destination.parent / ".abyss-stack-owner-deploy" / owner_repo / "receipts"


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        if candidate == candidate.parent:
            raise DeploymentError("path_parent_missing", f"no existing parent for {path}")
        candidate = candidate.parent
    return candidate.resolve()


def _ensure_route_paths(destination: Path, release_root: Path, receipt_dir: Path) -> None:
    if not destination.parent.is_dir():
        raise DeploymentError("destination_parent_missing", f"destination parent is missing: {destination.parent}")
    if release_root.exists() and release_root.is_symlink():
        raise DeploymentError("release_root_symlink", f"release root must not be a symlink: {release_root}")
    if release_root.exists() and not release_root.is_dir():
        raise DeploymentError("release_root_not_directory", f"release root is not a directory: {release_root}")
    source_root = _nearest_existing_parent(release_root.parent)
    destination_parent = destination.parent.resolve()
    if source_root.stat().st_dev != destination_parent.stat().st_dev:
        raise DeploymentError("cross_device_route", "release staging and destination switch are on different filesystems")
    if receipt_dir.exists() and receipt_dir.is_symlink():
        raise DeploymentError("receipt_dir_symlink", f"receipt directory must not be a symlink: {receipt_dir}")
    if receipt_dir.exists() and not receipt_dir.is_dir():
        raise DeploymentError("receipt_dir_not_directory", f"receipt directory is not a directory: {receipt_dir}")


def _assert_not_nested(path: Path, parent: Path, code: str, label: str) -> None:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return
    raise DeploymentError(code, f"{label} may not be inside {parent}")


def _snapshot_destination(destination: Path, release_root: Path) -> dict[str, Any]:
    if not os.path.lexists(destination):
        return {"kind": "absent"}
    if not destination.is_symlink():
        if destination.is_dir() and (destination / ".git").exists():
            _git_identity(destination)
            if _git_status(destination):
                raise DeploymentError("dirty_destination", f"destination checkout is dirty: {destination}")
        raise DeploymentError(
            "destination_not_atomic_switchable",
            f"destination must be absent or a managed symlink: {destination}",
        )
    link_text = os.readlink(destination)
    target = (destination.parent / link_text).resolve(strict=False)
    if not target.is_dir():
        raise DeploymentError("destination_dangling", f"destination symlink target is missing: {target}")
    release_root_resolved = release_root.resolve(strict=False)
    try:
        target.relative_to(release_root_resolved)
    except ValueError as exc:
        raise DeploymentError("unmanaged_destination", f"destination target is outside release root: {target}") from exc
    identity = _git_identity(target)
    if _git_status(target):
        raise DeploymentError("dirty_destination", f"release checkout is dirty: {target}")
    return {
        "kind": "symlink",
        "link_text": link_text,
        "target": os.fspath(target),
        "source_ref": identity["ref"],
        "source_tree": identity["tree"],
    }


def _same_snapshot(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("kind") != right.get("kind"):
        return False
    if left.get("kind") == "absent":
        return True
    return all(left.get(key) == right.get(key) for key in ("target", "source_ref", "source_tree"))


def _lock_path(release_root: Path, owner_repo: str) -> Path:
    return release_root.parent / f".{owner_repo}.deployment.lock"


@contextmanager
def _deployment_lock(path: Path) -> Iterator[None]:
    if fcntl is None:
        raise DeploymentError("locking_unavailable", "fcntl locking is unavailable on this platform")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise DeploymentError("lock_open_failed", f"{path}: {exc}") from exc
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise DeploymentError("concurrent_deployment", f"deployment lock is held: {path}") from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _staging_paths(release_root: Path, owner_repo: str) -> list[Path]:
    parent = release_root.parent
    if not parent.exists():
        return []
    return sorted(parent.glob(f".{owner_repo}-*-staging"))


def _preflight_common(
    *,
    owner_repo: str,
    source_root: Path,
    source_ref: str,
    source_tree: str,
    destination: Path,
    release_root: Path,
    receipt_dir: Path,
    admission_receipt: Path,
) -> tuple[dict[str, str], dict[str, Any], str, dict[str, Any]]:
    _validate_owner(owner_repo)
    source_ref = _validate_commit(source_ref, "source_ref")
    source_tree = _validate_commit(source_tree, "source_tree")
    source_root = _existing_path(source_root, "source_root")
    if not source_root.is_dir():
        raise DeploymentError("source_not_directory", f"source root is not a directory: {source_root}")
    destination = _absolute_path(destination, "destination")
    release_root = _absolute_path(release_root, "release_root")
    receipt_dir = _absolute_path(receipt_dir, "receipt_dir")
    admission_receipt = _existing_path(admission_receipt, "admission receipt")
    if destination == source_root:
        raise DeploymentError("destination_is_source", "destination may not equal source root")
    _assert_not_nested(destination, source_root, "destination_inside_source", "destination")
    _assert_not_nested(release_root, source_root, "release_root_inside_source", "release root")
    _assert_not_nested(receipt_dir, source_root, "receipt_dir_inside_source", "receipt directory")
    _ensure_route_paths(destination, release_root, receipt_dir)
    source_identity = _verify_clean_identity(source_root, source_ref, source_tree)
    admission, admission_digest = _load_admission(
        admission_receipt,
        owner_repo=owner_repo,
        source_root=source_root,
        source_ref=source_ref,
        source_tree=source_tree,
        destination=destination,
    )
    predecessor = _snapshot_destination(destination, release_root)
    if _staging_paths(release_root, owner_repo):
        raise DeploymentError("incomplete_staging", "unclaimed staging directory exists")
    return source_identity, admission, admission_digest, predecessor


def _prepare_receipt_path(receipt_dir: Path, operation_id: str) -> Path:
    return receipt_dir / f"prepare-{operation_id}.json"


def _clone_release(source_root: Path, release_root: Path, owner_repo: str, source_ref: str, source_tree: str, operation_id: str) -> Path:
    release_root.mkdir(parents=True, exist_ok=True)
    staging = release_root.parent / f".{owner_repo}-{operation_id}-staging"
    final = release_root / f"{source_ref}-{source_tree[:12]}-{operation_id}"
    if staging.exists() or os.path.lexists(staging):
        raise DeploymentError("incomplete_staging", f"staging path already exists: {staging}")
    if final.exists() or os.path.lexists(final):
        raise DeploymentError("release_collision", f"release path already exists: {final}")
    try:
        try:
            completed = subprocess.run(
                ["git", "clone", "--no-local", "--no-checkout", os.fspath(source_root), os.fspath(staging)],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise DeploymentError("git_unavailable", str(exc)) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "git clone failed"
            raise DeploymentError("git_clone_failed", detail[-800:])
        _run_git(staging, "checkout", "--detach", source_ref)
        if (staging / ".git" / "objects" / "info" / "alternates").exists():
            raise DeploymentError("source_coupled_release", "release clone still uses an object-store alternate")
        _verify_clean_identity(staging, source_ref, source_tree)
        os.replace(staging, final)
        _fsync_directory(release_root)
    except DeploymentError:
        if staging.exists() or os.path.islink(staging):
            shutil.rmtree(staging, ignore_errors=True)
        raise
    except OSError as exc:
        if staging.exists() or os.path.islink(staging):
            shutil.rmtree(staging, ignore_errors=True)
        raise DeploymentError("release_stage_failed", f"{release_root}: {exc}") from exc
    return final


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    owner_repo = _validate_owner(args.owner_repo)
    destination = _absolute_path(args.destination, "destination")
    release_root = _absolute_path(args.release_root, "release_root") if args.release_root else _default_release_root(destination, owner_repo)
    receipt_dir = _absolute_path(args.receipt_dir, "receipt_dir") if args.receipt_dir else _default_receipt_dir(destination, owner_repo)
    source_root = _absolute_path(args.source_root, "source_root")
    admission_receipt = _absolute_path(args.admission_receipt, "admission receipt")
    operation_id = uuid.uuid4().hex
    source_identity, admission, admission_digest, predecessor = _preflight_common(
        owner_repo=owner_repo,
        source_root=source_root,
        source_ref=args.source_ref,
        source_tree=args.source_tree,
        destination=destination,
        release_root=release_root,
        receipt_dir=receipt_dir,
        admission_receipt=admission_receipt,
    )
    if args.dry_run:
        return {
            "schema_version": PREPARE_SCHEMA,
            "status": "dry_run",
            "operation_id": operation_id,
            "owner_repo": owner_repo,
            "source": {"root": os.fspath(source_root), **source_identity, "dirty": False},
            "destination": os.fspath(destination),
            "release_root": os.fspath(release_root),
            "predecessor": predecessor,
            "admission": {
                "path": os.fspath(admission_receipt),
                "sha256": admission_digest,
                "admission_id": admission["admission_id"],
                "authority_ceiling": admission["authority_ceiling"],
            },
            "atomicity": {
                "same_filesystem": True,
                "staging": "self-contained-git-clone",
                "switch": "relative-symlink-os-replace",
            },
            "dependency_posture": "source_only_no_install",
            "effects": [],
            "claim_ceiling": "preflight_only",
        }
    lock_path = _lock_path(release_root, owner_repo)
    with _deployment_lock(lock_path):
        # Re-run every identity-sensitive check while holding the lock.
        source_identity, admission, admission_digest, predecessor = _preflight_common(
            owner_repo=owner_repo,
            source_root=source_root,
            source_ref=args.source_ref,
            source_tree=args.source_tree,
            destination=destination,
            release_root=release_root,
            receipt_dir=receipt_dir,
            admission_receipt=admission_receipt,
        )
        release_path = _clone_release(
            source_root,
            release_root,
            owner_repo,
            args.source_ref,
            args.source_tree,
            operation_id,
        )
        now = _utc_now()
        admission_expires = _timestamp(admission["expires_at"], "expires_at")
        plan_expires = min(admission_expires, now + timedelta(seconds=args.plan_ttl_seconds))
        payload = {
            "schema_version": PREPARE_SCHEMA,
            "status": "prepared",
            "operation_id": operation_id,
            "prepared_at": _iso(now),
            "expires_at": _iso(plan_expires),
            "owner_repo": owner_repo,
            "source": {"root": os.fspath(source_root), **source_identity, "dirty": False},
            "destination": os.fspath(destination),
            "release_root": os.fspath(release_root),
            "release_path": os.fspath(release_path),
            "predecessor": predecessor,
            "admission": {
                "path": os.fspath(admission_receipt),
                "sha256": admission_digest,
                "admission_id": admission["admission_id"],
                "authority_ceiling": admission["authority_ceiling"],
            },
            "atomicity": {
                "same_filesystem": True,
                "staging": "self-contained-git-clone",
                "switch": "relative-symlink-os-replace",
            },
            "dependency_posture": "source_only_no_install",
            "effects": ["release_directory_created"],
            "claim_ceiling": "prepared_not_activated",
        }
        receipt_path = _prepare_receipt_path(receipt_dir, operation_id)
        receipt = _write_json(receipt_path, payload)
        return {"receipt_path": os.fspath(receipt_path), **receipt}


def _load_prepare_receipt(path: Path) -> tuple[dict[str, Any], Path]:
    payload, _ = _load_json(path, "prepare receipt")
    _verify_receipt_digest(payload, "prepare receipt")
    if payload.get("schema_version") != PREPARE_SCHEMA or payload.get("status") != "prepared":
        raise DeploymentError("prepare_receipt_invalid", "prepare receipt is not activatable")
    return payload, path


def _prepare_paths(payload: dict[str, Any]) -> tuple[str, Path, Path, Path, Path, Path]:
    owner_repo = _validate_owner(str(payload.get("owner_repo", "")))
    source = payload.get("source")
    admission = payload.get("admission")
    if not isinstance(source, dict) or not isinstance(admission, dict):
        raise DeploymentError("prepare_receipt_invalid", "prepare receipt lacks source/admission objects")
    source_root = _absolute_path(str(source.get("root", "")), "prepare source root")
    destination = _absolute_path(str(payload.get("destination", "")), "prepare destination")
    release_root = _absolute_path(str(payload.get("release_root", "")), "prepare release root")
    release_path = _absolute_path(str(payload.get("release_path", "")), "prepare release path")
    admission_path = _absolute_path(str(admission.get("path", "")), "prepare admission path")
    try:
        release_path.relative_to(release_root)
    except ValueError as exc:
        raise DeploymentError("release_path_unmanaged", "prepared release is outside release root") from exc
    return owner_repo, source_root, destination, release_root, release_path, admission_path


def _verify_prepare_fresh(payload: dict[str, Any]) -> None:
    expires = _timestamp(str(payload.get("expires_at", "")), "prepare expires_at")
    if _utc_now() >= expires:
        raise DeploymentError("prepare_receipt_stale", "prepare receipt has expired")


def activate(args: argparse.Namespace) -> dict[str, Any]:
    prepare_path = _existing_path(args.prepare_receipt, "prepare receipt")
    payload, _ = _load_prepare_receipt(prepare_path)
    _verify_prepare_fresh(payload)
    owner_repo, source_root, destination, release_root, release_path, admission_path = _prepare_paths(payload)
    source = payload["source"]
    admission = payload["admission"]
    source_ref = _validate_commit(str(source.get("ref", "")), "prepare source ref")
    source_tree = _validate_commit(str(source.get("tree", "")), "prepare source tree")
    _ensure_route_paths(destination, release_root, prepare_path.parent)
    lock_path = _lock_path(release_root, owner_repo)
    with _deployment_lock(lock_path):
        fresh_payload, _ = _load_prepare_receipt(prepare_path)
        if fresh_payload["receipt_digest"] != payload["receipt_digest"]:
            raise DeploymentError("prepare_receipt_changed", "prepare receipt changed after it was read")
        current = _snapshot_destination(destination, release_root)
        expected = payload.get("predecessor")
        if not isinstance(expected, dict) or not _same_snapshot(current, expected):
            raise DeploymentError("concurrent_deployment", "destination changed after prepare")
        admission_now, admission_digest = _load_admission(
            admission_path,
            owner_repo=owner_repo,
            source_root=source_root.resolve(),
            source_ref=source_ref,
            source_tree=source_tree,
            destination=destination,
        )
        if admission_digest != admission.get("sha256"):
            raise DeploymentError("admission_changed", "admission receipt digest changed after prepare")
        if admission_now["admission_id"] != admission.get("admission_id"):
            raise DeploymentError("admission_changed", "admission identity changed after prepare")
        if admission_digest != admission.get("sha256"):
            raise DeploymentError("admission_changed", "admission receipt digest changed after prepare")
        _verify_clean_identity(release_path, source_ref, source_tree)
        try:
            target_link = os.path.relpath(release_path, destination.parent)
            temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.switch"
            os.symlink(target_link, temporary)
            os.replace(temporary, destination)
            _fsync_directory(destination.parent)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)  # type: ignore[union-attr]
            except (OSError, UnboundLocalError):
                pass
            raise DeploymentError("atomic_switch_failed", f"{destination}: {exc}") from exc
        now = _utc_now()
        payload_out = {
            "schema_version": ACTIVATE_SCHEMA,
            "status": "activated",
            "operation_id": uuid.uuid4().hex,
            "activated_at": _iso(now),
            "owner_repo": owner_repo,
            "prepare_receipt": {
                "path": os.fspath(prepare_path),
                "sha256": payload["receipt_digest"],
            },
            "source": {"root": os.fspath(source_root), "ref": source_ref, "tree": source_tree, "dirty": False},
            "destination": os.fspath(destination),
            "release_root": os.fspath(release_root),
            "activated_release": os.fspath(release_path),
            "predecessor": expected,
            "admission": admission,
            "atomicity": {
                "same_filesystem": True,
                "switch": "relative-symlink-os-replace",
                "destination_identity_checked": True,
            },
            "dependency_posture": "source_only_no_install",
            "effects": ["destination_symlink_replaced"],
            "claim_ceiling": "source_activation_only_no_runtime_claim",
        }
        receipt_dir = prepare_path.parent
        receipt_path = receipt_dir / f"activate-{payload['operation_id']}.json"
        receipt = _write_json(receipt_path, payload_out)
        return {"receipt_path": os.fspath(receipt_path), **receipt}


def _load_activation_receipt(path: Path) -> dict[str, Any]:
    payload, _ = _load_json(path, "activation receipt")
    _verify_receipt_digest(payload, "activation receipt")
    if payload.get("schema_version") != ACTIVATE_SCHEMA or payload.get("status") != "activated":
        raise DeploymentError("activation_receipt_invalid", "activation receipt is not rollback-capable")
    return payload


def _restore_predecessor(destination: Path, predecessor: dict[str, Any], release_root: Path) -> str | None:
    kind = predecessor.get("kind")
    if kind == "absent":
        os.unlink(destination)
        _fsync_directory(destination.parent)
        return None
    if kind != "symlink":
        raise DeploymentError("predecessor_invalid", "predecessor identity is not restorable")
    target = _absolute_path(str(predecessor.get("target", "")), "predecessor target")
    try:
        target.relative_to(release_root.resolve(strict=False))
    except ValueError as exc:
        raise DeploymentError("predecessor_unmanaged", "predecessor target is outside release root") from exc
    if not target.is_dir():
        raise DeploymentError("predecessor_missing", f"predecessor release is missing: {target}")
    temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.rollback"
    try:
        os.symlink(os.path.relpath(target, destination.parent), temporary)
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise DeploymentError("rollback_switch_failed", f"{destination}: {exc}") from exc
    return os.fspath(target)


def rollback(args: argparse.Namespace) -> dict[str, Any]:
    activation_path = _existing_path(args.activation_receipt, "activation receipt")
    activation = _load_activation_receipt(activation_path)
    owner_repo = _validate_owner(str(activation.get("owner_repo", "")))
    destination = _absolute_path(str(activation.get("destination", "")), "activation destination")
    release_root = _absolute_path(str(activation.get("release_root", "")), "activation release root")
    activated_release = _absolute_path(str(activation.get("activated_release", "")), "activated release")
    predecessor = activation.get("predecessor")
    if not isinstance(predecessor, dict):
        raise DeploymentError("activation_receipt_invalid", "activation receipt lacks predecessor identity")
    lock_path = _lock_path(release_root, owner_repo)
    with _deployment_lock(lock_path):
        fresh_activation, _ = _load_json(activation_path, "activation receipt")
        _verify_receipt_digest(fresh_activation, "activation receipt")
        if fresh_activation.get("receipt_digest") != activation.get("receipt_digest"):
            raise DeploymentError("activation_receipt_changed", "activation receipt changed after it was read")
        current = _snapshot_destination(destination, release_root)
        expected_current = {
            "kind": "symlink",
            "target": os.fspath(activated_release.resolve(strict=False)),
        }
        if current.get("kind") != "symlink" or current.get("target") != expected_current["target"]:
            raise DeploymentError("concurrent_deployment", "destination no longer points to activated release")
        restored = _restore_predecessor(destination, predecessor, release_root)
        payload = {
            "schema_version": ROLLBACK_SCHEMA,
            "status": "rolled_back",
            "operation_id": uuid.uuid4().hex,
            "rolled_back_at": _iso(_utc_now()),
            "owner_repo": owner_repo,
            "activation_receipt": {
                "path": os.fspath(activation_path),
                "sha256": activation["receipt_digest"],
            },
            "destination": os.fspath(destination),
            "release_root": os.fspath(release_root),
            "removed_activation": os.fspath(activated_release),
            "restored_predecessor": predecessor,
            "restored_target": restored,
            "effects": ["destination_symlink_restored" if restored else "destination_removed"],
            "claim_ceiling": "source_activation_rollback_only_no_runtime_claim",
        }
        receipt_dir = (
            _absolute_path(args.receipt_dir, "receipt_dir")
            if args.receipt_dir
            else activation_path.parent
        )
        receipt_path = receipt_dir / f"rollback-{activation['operation_id']}.json"
        receipt_out = _write_json(receipt_path, payload)
        return {"receipt_path": os.fspath(receipt_path), **receipt_out}


def _add_path_argument(parser: argparse.ArgumentParser, name: str, *, required: bool = True) -> None:
    parser.add_argument(name, required=required)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Source-only owner release prepare/activate/rollback route."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare", help="preflight and stage an immutable source release")
    prepare_parser.add_argument("--owner-repo", required=True)
    _add_path_argument(prepare_parser, "--source-root")
    prepare_parser.add_argument("--source-ref", required=True)
    prepare_parser.add_argument("--source-tree", required=True)
    _add_path_argument(prepare_parser, "--destination")
    _add_path_argument(prepare_parser, "--admission-receipt")
    _add_path_argument(prepare_parser, "--release-root", required=False)
    _add_path_argument(prepare_parser, "--receipt-dir", required=False)
    prepare_parser.add_argument("--plan-ttl-seconds", type=int, default=3600)
    prepare_parser.add_argument("--dry-run", action="store_true")

    activate_parser = commands.add_parser("activate", help="atomically switch the prepared destination symlink")
    _add_path_argument(activate_parser, "--prepare-receipt")

    rollback_parser = commands.add_parser("rollback", help="atomically restore the prepared predecessor")
    _add_path_argument(rollback_parser, "--activation-receipt")
    _add_path_argument(rollback_parser, "--receipt-dir", required=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if getattr(args, "plan_ttl_seconds", 1) <= 0:
        error = DeploymentError("invalid_plan_ttl", "plan TTL must be positive")
    else:
        try:
            if args.command == "prepare":
                result = prepare(args)
            elif args.command == "activate":
                result = activate(args)
            else:
                result = rollback(args)
        except DeploymentError as exc:
            error = exc
        else:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
            return 0
    error_payload = {
        "schema_version": ERROR_SCHEMA,
        "status": "rejected",
        "error": {"code": error.code, "detail": error.detail},
    }
    print(json.dumps(error_payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
