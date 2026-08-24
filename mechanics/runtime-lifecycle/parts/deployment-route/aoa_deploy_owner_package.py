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
RECOVERY_SCHEMA = "abyss_stack_owner_source_activation_recovery_v1"
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

    def __init__(self, code: str, detail: str, context: dict[str, Any] | None = None):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.context = context or {}


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
    # Ignored caches are outside the source identity.  Tracked edits and all
    # non-ignored untracked content remain mutable source and must fail closed.
    return _run_git(repo, "status", "--porcelain=v1", "--untracked-files=all")


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


def _verify_recorded_release(
    release_path: Path,
    expected_ref: str,
    expected_tree: str,
    *,
    label: str,
) -> dict[str, str]:
    """Revalidate a recorded release before treating it as rollback-capable."""

    if not release_path.is_dir():
        raise DeploymentError(f"{label}_missing", f"recorded release is missing: {release_path}")
    try:
        identity = _git_identity(release_path)
    except DeploymentError as exc:
        raise DeploymentError(f"{label}_invalid", f"recorded release is not a Git checkout: {release_path}") from exc
    if _git_status(release_path):
        raise DeploymentError(f"{label}_dirty", f"recorded release is mutable: {release_path}")
    if identity["ref"] != expected_ref:
        raise DeploymentError(
            f"{label}_ref_mismatch",
            f"{release_path} HEAD {identity['ref']} != recorded {expected_ref}",
        )
    if identity["tree"] != expected_tree:
        raise DeploymentError(
            f"{label}_tree_mismatch",
            f"{release_path} tree {identity['tree']} != recorded {expected_tree}",
        )
    _reject_submodules(release_path)
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
            _reject_submodules(destination)
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
    _reject_submodules(target)
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


def _validate_recorded_snapshot(
    snapshot: dict[str, Any],
    release_root: Path,
    *,
    label: str,
) -> Path | None:
    """Validate the path and immutable Git identity recorded in a snapshot."""

    kind = snapshot.get("kind")
    if kind == "absent":
        return None
    if kind != "symlink":
        raise DeploymentError(f"{label}_invalid", "recorded snapshot is not restorable")
    link_text = snapshot.get("link_text")
    if not isinstance(link_text, str) or not link_text:
        raise DeploymentError(f"{label}_invalid", "recorded snapshot lacks link text")
    expected_ref = _validate_commit(str(snapshot.get("source_ref", "")), f"{label}.source_ref")
    expected_tree = _validate_commit(str(snapshot.get("source_tree", "")), f"{label}.source_tree")
    target = _absolute_path(str(snapshot.get("target", "")), f"{label}.target")
    try:
        target.relative_to(release_root.resolve(strict=False))
    except ValueError as exc:
        raise DeploymentError(f"{label}_unmanaged", "recorded target is outside release root") from exc
    _verify_recorded_release(target, expected_ref, expected_tree, label=label)
    return target


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


def _recovery_journal_path(receipt_dir: Path, prepare_operation_id: str) -> Path:
    return receipt_dir / f"activate-{prepare_operation_id}.recovery.json"


def _validate_operation_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise DeploymentError("invalid_operation_id", f"{field} must be a 32-character hexadecimal id")
    return value


def _recovery_reference(path: Path, payload: dict[str, Any]) -> dict[str, str]:
    digest = payload.get("receipt_digest")
    if not isinstance(digest, str):
        raise DeploymentError("recovery_record_invalid", "recovery record lacks receipt digest")
    return {"path": os.fspath(path), "sha256": digest}


def _validate_recovery_payload(payload: dict[str, Any], path: Path) -> None:
    _verify_receipt_digest(payload, "recovery journal")
    if payload.get("schema_version") != RECOVERY_SCHEMA:
        raise DeploymentError("recovery_record_invalid", "unsupported recovery journal schema")
    status = payload.get("status")
    if status not in {"intent_written", "switch_complete", "finalized", "rolled_back"}:
        raise DeploymentError("recovery_record_invalid", "recovery journal has an invalid status")
    _validate_operation_id(payload.get("operation_id"), "recovery operation_id")
    _validate_operation_id(payload.get("prepare_operation_id"), "recovery prepare_operation_id")
    _timestamp(str(payload.get("created_at", "")), "recovery created_at")
    _timestamp(str(payload.get("updated_at", "")), "recovery updated_at")
    if status in {"switch_complete", "finalized"}:
        _timestamp(str(payload.get("switched_at", "")), "recovery switched_at")
    owner_repo = _validate_owner(str(payload.get("owner_repo", "")))
    source = payload.get("source")
    if not isinstance(source, dict) or source.get("dirty") is not False:
        raise DeploymentError("recovery_record_invalid", "recovery journal source is not cleanly bound")
    source_root = _absolute_path(str(source.get("root", "")), "recovery source root")
    source_ref = _validate_commit(str(source.get("ref", "")), "recovery source ref")
    source_tree = _validate_commit(str(source.get("tree", "")), "recovery source tree")
    if not isinstance(payload.get("destination"), str) or not isinstance(payload.get("release_root"), str):
        raise DeploymentError("recovery_record_invalid", "recovery journal lacks destination roots")
    destination = _absolute_path(payload["destination"], "recovery destination")
    release_root = _absolute_path(payload["release_root"], "recovery release root")
    activated_release = _absolute_path(str(payload.get("activated_release", "")), "recovery activated release")
    try:
        activated_release.relative_to(release_root.resolve(strict=False))
    except ValueError as exc:
        raise DeploymentError("recovery_record_invalid", "recovery activated release is unmanaged") from exc
    predecessor = payload.get("predecessor")
    if not isinstance(predecessor, dict):
        raise DeploymentError("recovery_record_invalid", "recovery journal lacks predecessor snapshot")
    _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
    prepare_receipt = payload.get("prepare_receipt")
    if (
        not isinstance(prepare_receipt, dict)
        or not isinstance(prepare_receipt.get("path"), str)
        or not isinstance(prepare_receipt.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", prepare_receipt["sha256"])
    ):
        raise DeploymentError("recovery_record_invalid", "recovery journal lacks prepare receipt binding")
    _absolute_path(prepare_receipt["path"], "recovery prepare receipt")
    admission = payload.get("admission")
    if not isinstance(admission, dict):
        raise DeploymentError("recovery_record_invalid", "recovery journal lacks admission binding")
    for key in ("path", "sha256", "admission_id", "authority_ceiling"):
        if not isinstance(admission.get(key), str) or not admission[key]:
            raise DeploymentError("recovery_record_invalid", f"recovery admission lacks {key}")
    if not re.fullmatch(r"[0-9a-f]{64}", admission["sha256"]):
        raise DeploymentError("recovery_record_invalid", "recovery admission digest is invalid")
    _absolute_path(admission["path"], "recovery admission path")
    if admission["authority_ceiling"] not in ALLOWED_AUTHORITY_CEILINGS:
        raise DeploymentError("recovery_record_invalid", "recovery admission authority is invalid")
    atomicity = payload.get("atomicity")
    if not isinstance(atomicity, dict) or atomicity.get("same_filesystem") is not True:
        raise DeploymentError("recovery_record_invalid", "recovery atomicity is not bound")
    if atomicity.get("switch") != "relative-symlink-os-replace":
        raise DeploymentError("recovery_record_invalid", "recovery switch is not atomic")
    receipt_paths: dict[str, Path] = {}
    for key, prefix in (("activation_receipt_path", "activate"), ("rollback_receipt_path", "rollback")):
        if not isinstance(payload.get(key), str) or not Path(payload[key]).is_absolute():
            raise DeploymentError("recovery_record_invalid", f"recovery journal lacks {key}")
        receipt_paths[key] = _absolute_path(payload[key], f"recovery {key}")
        expected_path = path.parent / f"{prefix}-{payload['operation_id']}.json"
        if receipt_paths[key] != expected_path:
            raise DeploymentError("recovery_record_invalid", f"recovery {key} is not deterministic")
    if source_root == destination or not owner_repo:
        raise DeploymentError("recovery_record_invalid", "recovery source and destination binding is invalid")
    _validate_commit(source_ref, "recovery source ref")
    _validate_commit(source_tree, "recovery source tree")
    if path.name != f"activate-{payload['prepare_operation_id']}.recovery.json":
        raise DeploymentError("recovery_record_invalid", "recovery journal filename is not deterministic")
    if status == "intent_written" and any(
        key in payload for key in ("activation_receipt", "rollback_receipt")
    ):
        raise DeploymentError("recovery_record_invalid", "intent journal cannot contain completed receipt references")
    for key, label in (("activation_receipt", "activation receipt"), ("rollback_receipt", "rollback receipt")):
        if key in payload:
            reference = payload[key]
            if (
                not isinstance(reference, dict)
                or not isinstance(reference.get("path"), str)
                or not isinstance(reference.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", reference["sha256"])
            ):
                raise DeploymentError("recovery_record_invalid", f"recovery {label} reference is invalid")
            if _absolute_path(reference["path"], f"recovery {label} path") != receipt_paths[
                "activation_receipt_path" if key == "activation_receipt" else "rollback_receipt_path"
            ]:
                raise DeploymentError("recovery_record_invalid", f"recovery {label} path is not bound")
    if status == "finalized" and "activation_receipt" not in payload:
        raise DeploymentError("recovery_record_invalid", "finalized recovery lacks activation receipt")
    if status == "rolled_back" and "rollback_receipt" not in payload:
        raise DeploymentError("recovery_record_invalid", "rolled-back recovery lacks rollback receipt")


def _load_recovery_journal(path: Path) -> dict[str, Any]:
    payload, _ = _load_json(path, "recovery journal")
    _validate_recovery_payload(payload, path)
    return payload


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
    _validate_operation_id(payload.get("operation_id"), "prepare operation_id")
    if not isinstance(payload.get("owner_repo"), str):
        raise DeploymentError("prepare_receipt_invalid", "prepare receipt lacks owner_repo")
    _validate_owner(payload["owner_repo"])
    source = payload.get("source")
    if (
        not isinstance(source, dict)
        or source.get("dirty") is not False
        or not isinstance(source.get("root"), str)
    ):
        raise DeploymentError("prepare_receipt_invalid", "prepare receipt source is not cleanly bound")
    _absolute_path(source["root"], "prepare source root")
    _validate_commit(str(source.get("ref", "")), "prepare source ref")
    _validate_commit(str(source.get("tree", "")), "prepare source tree")
    _absolute_path(str(payload.get("destination", "")), "prepare destination")
    release_root = _absolute_path(str(payload.get("release_root", "")), "prepare release root")
    release_path = _absolute_path(str(payload.get("release_path", "")), "prepare release path")
    try:
        release_path.relative_to(release_root.resolve(strict=False))
    except ValueError as exc:
        raise DeploymentError("release_path_unmanaged", "prepared release is outside release root") from exc
    predecessor = payload.get("predecessor")
    if not isinstance(predecessor, dict):
        raise DeploymentError("prepare_receipt_invalid", "prepare receipt lacks predecessor snapshot")
    _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
    admission = payload.get("admission")
    if not isinstance(admission, dict):
        raise DeploymentError("prepare_receipt_invalid", "prepare receipt lacks admission binding")
    for key in ("path", "sha256", "admission_id", "authority_ceiling"):
        if not isinstance(admission.get(key), str) or not admission[key]:
            raise DeploymentError("prepare_receipt_invalid", f"prepare admission lacks {key}")
    if not re.fullmatch(r"[0-9a-f]{64}", admission["sha256"]):
        raise DeploymentError("prepare_receipt_invalid", "prepare admission digest is invalid")
    atomicity = payload.get("atomicity")
    if (
        not isinstance(atomicity, dict)
        or atomicity.get("same_filesystem") is not True
        or atomicity.get("switch") != "relative-symlink-os-replace"
    ):
        raise DeploymentError("prepare_receipt_invalid", "prepare atomicity is not bound")
    if payload.get("claim_ceiling") != "prepared_not_activated":
        raise DeploymentError("prepare_receipt_invalid", "prepare claim ceiling is invalid")
    if not isinstance(payload.get("effects"), list):
        raise DeploymentError("prepare_receipt_invalid", "prepare effects must be a list")
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


def _recovery_required(path: Path, error: DeploymentError) -> DeploymentError:
    return DeploymentError(
        "activation_recovery_required",
        f"activation state may need recovery; use the durable journal {path}: {error.detail}",
        {"recovery_journal": os.fspath(path), "recovery_required": True},
    )


def _new_recovery_payload(
    *,
    operation_id: str,
    prepare_payload: dict[str, Any],
    prepare_path: Path,
    owner_repo: str,
    source_root: Path,
    source_ref: str,
    source_tree: str,
    destination: Path,
    release_root: Path,
    release_path: Path,
    predecessor: dict[str, Any],
    admission: dict[str, Any],
    journal_path: Path,
) -> dict[str, Any]:
    activation_receipt_path = journal_path.with_name(f"activate-{operation_id}.json")
    rollback_receipt_path = journal_path.with_name(f"rollback-{operation_id}.json")
    now = _iso(_utc_now())
    return {
        "schema_version": RECOVERY_SCHEMA,
        "status": "intent_written",
        "operation_id": operation_id,
        "prepare_operation_id": prepare_payload["operation_id"],
        "created_at": now,
        "updated_at": now,
        "owner_repo": owner_repo,
        "prepare_receipt": {
            "path": os.fspath(prepare_path),
            "sha256": prepare_payload["receipt_digest"],
        },
        "source": {
            "root": os.fspath(source_root),
            "ref": source_ref,
            "tree": source_tree,
            "dirty": False,
        },
        "destination": os.fspath(destination),
        "release_root": os.fspath(release_root),
        "activated_release": os.fspath(release_path),
        "predecessor": predecessor,
        "admission": admission,
        "activation_receipt_path": os.fspath(activation_receipt_path),
        "rollback_receipt_path": os.fspath(rollback_receipt_path),
        "atomicity": {
            "same_filesystem": True,
            "switch": "relative-symlink-os-replace",
            "journal": "durable-before-switch",
        },
        "claim_ceiling": "source_activation_recovery_only_no_runtime_claim",
    }


def _activation_payload(
    *,
    operation_id: str,
    prepare_payload: dict[str, Any],
    prepare_path: Path,
    owner_repo: str,
    source_root: Path,
    source_ref: str,
    source_tree: str,
    destination: Path,
    release_root: Path,
    release_path: Path,
    predecessor: dict[str, Any],
    admission: dict[str, Any],
    recovery_path: Path,
    recovery_digest: str,
) -> dict[str, Any]:
    return {
        "schema_version": ACTIVATE_SCHEMA,
        "status": "activated",
        "operation_id": operation_id,
        "activated_at": _iso(_utc_now()),
        "owner_repo": owner_repo,
        "prepare_receipt": {
            "path": os.fspath(prepare_path),
            "sha256": prepare_payload["receipt_digest"],
        },
        "source": {
            "root": os.fspath(source_root),
            "ref": source_ref,
            "tree": source_tree,
            "dirty": False,
        },
        "destination": os.fspath(destination),
        "release_root": os.fspath(release_root),
        "activated_release": os.fspath(release_path),
        "predecessor": predecessor,
        "admission": admission,
        "recovery_journal": {
            "path": os.fspath(recovery_path),
            "sha256": recovery_digest,
        },
        "atomicity": {
            "same_filesystem": True,
            "switch": "relative-symlink-os-replace",
            "destination_identity_checked": True,
            "journal": "durable-before-switch",
        },
        "dependency_posture": "source_only_no_install",
        "effects": ["destination_symlink_replaced"],
        "claim_ceiling": "source_activation_only_no_runtime_claim",
    }


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
        recovery_path = _recovery_journal_path(prepare_path.parent, payload["operation_id"])
        if os.path.lexists(recovery_path):
            raise DeploymentError(
                "recovery_pending",
                f"prepare receipt already has a recovery journal: {recovery_path}",
                {"recovery_journal": os.fspath(recovery_path), "recovery_required": True},
            )
        activation_operation_id = uuid.uuid4().hex
        journal_payload = _new_recovery_payload(
            operation_id=activation_operation_id,
            prepare_payload=payload,
            prepare_path=prepare_path,
            owner_repo=owner_repo,
            source_root=source_root,
            source_ref=source_ref,
            source_tree=source_tree,
            destination=destination,
            release_root=release_root,
            release_path=release_path,
            predecessor=expected,
            admission=admission,
            journal_path=recovery_path,
        )
        try:
            journal = _write_json(recovery_path, journal_payload)
        except DeploymentError as exc:
            if os.path.lexists(recovery_path):
                raise _recovery_required(recovery_path, exc) from exc
            raise
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
            raise _recovery_required(
                recovery_path,
                DeploymentError("atomic_switch_failed", f"{destination}: {exc}"),
            ) from exc
        journal_payload = dict(journal)
        journal_payload.update({"status": "switch_complete", "updated_at": _iso(_utc_now()), "switched_at": _iso(_utc_now())})
        try:
            journal = _write_json(recovery_path, journal_payload)
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
        payload_out = _activation_payload(
            operation_id=activation_operation_id,
            prepare_payload=payload,
            prepare_path=prepare_path,
            owner_repo=owner_repo,
            source_root=source_root,
            source_ref=source_ref,
            source_tree=source_tree,
            destination=destination,
            release_root=release_root,
            release_path=release_path,
            predecessor=expected,
            admission=admission,
            recovery_path=recovery_path,
            recovery_digest=journal["receipt_digest"],
        )
        receipt_dir = prepare_path.parent
        receipt_path = receipt_dir / f"activate-{activation_operation_id}.json"
        try:
            receipt = _write_json(receipt_path, payload_out)
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
        final_journal = dict(journal)
        final_journal.update(
            {
                "status": "finalized",
                "updated_at": _iso(_utc_now()),
                "activation_receipt": _recovery_reference(receipt_path, receipt),
            }
        )
        try:
            _write_json(recovery_path, final_journal)
        except DeploymentError:
            # The activation receipt is already complete.  The journal remains
            # durable and can be finalized idempotently by `recover`.
            pass
        return {"receipt_path": os.fspath(receipt_path), **receipt}


def _load_activation_receipt(path: Path) -> dict[str, Any]:
    payload, _ = _load_json(path, "activation receipt")
    _verify_receipt_digest(payload, "activation receipt")
    if payload.get("schema_version") != ACTIVATE_SCHEMA or payload.get("status") != "activated":
        raise DeploymentError("activation_receipt_invalid", "activation receipt is not rollback-capable")
    _validate_operation_id(payload.get("operation_id"), "activation operation_id")
    owner_repo = _validate_owner(str(payload.get("owner_repo", "")))
    source = payload.get("source")
    if not isinstance(source, dict) or source.get("dirty") is not False:
        raise DeploymentError("activation_receipt_invalid", "activation source is not cleanly bound")
    _absolute_path(str(source.get("root", "")), "activation source root")
    source_ref = _validate_commit(str(source.get("ref", "")), "activation source ref")
    source_tree = _validate_commit(str(source.get("tree", "")), "activation source tree")
    _absolute_path(str(payload.get("destination", "")), "activation destination")
    release_root = _absolute_path(str(payload.get("release_root", "")), "activation release root")
    activated_release = _absolute_path(str(payload.get("activated_release", "")), "activated release")
    try:
        activated_release.relative_to(release_root.resolve(strict=False))
    except ValueError as exc:
        raise DeploymentError("activation_receipt_invalid", "activated release is unmanaged") from exc
    _validate_recorded_snapshot(
        {"kind": "symlink", "link_text": "recorded", "target": os.fspath(activated_release), "source_ref": source_ref, "source_tree": source_tree},
        release_root,
        label="activated_release",
    )
    predecessor = payload.get("predecessor")
    if not isinstance(predecessor, dict):
        raise DeploymentError("activation_receipt_invalid", "activation receipt lacks predecessor snapshot")
    _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
    prepare_receipt = payload.get("prepare_receipt")
    if (
        not isinstance(prepare_receipt, dict)
        or not isinstance(prepare_receipt.get("path"), str)
        or not isinstance(prepare_receipt.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", prepare_receipt["sha256"])
    ):
        raise DeploymentError("activation_receipt_invalid", "activation prepare receipt binding is invalid")
    admission = payload.get("admission")
    if not isinstance(admission, dict):
        raise DeploymentError("activation_receipt_invalid", "activation receipt lacks admission binding")
    for key in ("path", "sha256", "admission_id", "authority_ceiling"):
        if not isinstance(admission.get(key), str) or not admission[key]:
            raise DeploymentError("activation_receipt_invalid", f"activation admission lacks {key}")
    if not re.fullmatch(r"[0-9a-f]{64}", admission["sha256"]):
        raise DeploymentError("activation_receipt_invalid", "activation admission digest is invalid")
    recovery = payload.get("recovery_journal")
    if (
        not isinstance(recovery, dict)
        or not isinstance(recovery.get("path"), str)
        or not isinstance(recovery.get("sha256"), str)
        or not Path(recovery["path"]).is_absolute()
        or not re.fullmatch(r"[0-9a-f]{64}", recovery["sha256"])
    ):
        raise DeploymentError("activation_receipt_invalid", "activation recovery journal binding is invalid")
    atomicity = payload.get("atomicity")
    if (
        not isinstance(atomicity, dict)
        or atomicity.get("same_filesystem") is not True
        or atomicity.get("switch") != "relative-symlink-os-replace"
        or atomicity.get("journal") != "durable-before-switch"
    ):
        raise DeploymentError("activation_receipt_invalid", "activation atomicity is not bound")
    if payload.get("claim_ceiling") != "source_activation_only_no_runtime_claim":
        raise DeploymentError("activation_receipt_invalid", "activation claim ceiling is invalid")
    if owner_repo != str(payload.get("owner_repo")):
        raise DeploymentError("activation_receipt_invalid", "activation owner binding is invalid")
    return payload


def _restore_predecessor(destination: Path, predecessor: dict[str, Any], release_root: Path) -> str | None:
    kind = predecessor.get("kind")
    if kind == "absent":
        if not os.path.lexists(destination):
            raise DeploymentError("destination_missing", f"destination disappeared before rollback: {destination}")
        if not destination.is_symlink():
            raise DeploymentError("destination_not_atomic_switchable", f"destination is not a symlink: {destination}")
        os.unlink(destination)
        _fsync_directory(destination.parent)
        return None
    target = _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
    assert target is not None
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
    source = activation.get("source")
    if not isinstance(source, dict):
        raise DeploymentError("activation_receipt_invalid", "activation receipt lacks source identity")
    source_ref = _validate_commit(str(source.get("ref", "")), "activation source ref")
    source_tree = _validate_commit(str(source.get("tree", "")), "activation source tree")
    predecessor = activation.get("predecessor")
    if not isinstance(predecessor, dict):
        raise DeploymentError("activation_receipt_invalid", "activation receipt lacks predecessor identity")
    lock_path = _lock_path(release_root, owner_repo)
    with _deployment_lock(lock_path):
        fresh_activation = _load_activation_receipt(activation_path)
        if fresh_activation.get("receipt_digest") != activation.get("receipt_digest"):
            raise DeploymentError("activation_receipt_changed", "activation receipt changed after it was read")
        current = _snapshot_destination(destination, release_root)
        expected_current = {
            "kind": "symlink",
            "target": os.fspath(activated_release.resolve(strict=False)),
            "source_ref": source_ref,
            "source_tree": source_tree,
        }
        if current.get("kind") != "symlink" or current.get("target") != expected_current["target"]:
            raise DeploymentError("concurrent_deployment", "destination no longer points to activated release")
        if not _same_snapshot(current, expected_current):
            raise DeploymentError("concurrent_deployment", "activated release identity changed before rollback")
        _verify_recorded_release(
            activated_release,
            source_ref,
            source_tree,
            label="activated_release",
        )
        _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
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
            "recovery_journal": activation["recovery_journal"],
            "atomicity": {
                "same_filesystem": True,
                "switch": "relative-symlink-os-replace",
                "destination_identity_checked": True,
                "predecessor_identity_checked": True,
            },
            "dependency_posture": "source_only_no_install",
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
        recovery_ref = activation.get("recovery_journal")
        if isinstance(recovery_ref, dict) and isinstance(recovery_ref.get("path"), str):
            recovery_path = Path(recovery_ref["path"])
            if os.path.lexists(recovery_path):
                try:
                    journal = _load_recovery_journal(recovery_path)
                    journal.update(
                        {
                            "status": "rolled_back",
                            "updated_at": _iso(_utc_now()),
                            "rollback_receipt": _recovery_reference(receipt_path, receipt_out),
                        }
                    )
                    _write_json(recovery_path, journal)
                except DeploymentError:
                    # The rollback receipt itself is complete; keep the
                    # durable journal for an explicit recovery retry.
                    pass
        return {"receipt_path": os.fspath(receipt_path), **receipt_out}


def _recovery_target_snapshot(journal: dict[str, Any]) -> dict[str, Any]:
    source = journal["source"]
    return {
        "kind": "symlink",
        "target": journal["activated_release"],
        "source_ref": source["ref"],
        "source_tree": source["tree"],
    }


def _recovery_paths(journal: dict[str, Any]) -> tuple[str, Path, Path, Path, Path, Path]:
    owner_repo = _validate_owner(str(journal["owner_repo"]))
    destination = _absolute_path(journal["destination"], "recovery destination")
    release_root = _absolute_path(journal["release_root"], "recovery release root")
    activated_release = _absolute_path(journal["activated_release"], "recovery activated release")
    recovery_path = _absolute_path(journal["_recovery_path"], "recovery journal")
    activation_path = _absolute_path(journal["activation_receipt_path"], "recovery activation receipt")
    return owner_repo, destination, release_root, activated_release, recovery_path, activation_path


def _recovery_activation_receipt(
    *,
    journal: dict[str, Any],
    recovery_path: Path,
) -> dict[str, Any]:
    owner_repo, destination, release_root, activated_release, _, activation_path = _recovery_paths(journal)
    source = journal["source"]
    predecessor = journal["predecessor"]
    admission = journal["admission"]
    return _activation_payload(
        operation_id=journal["operation_id"],
        prepare_payload={
            "operation_id": journal["prepare_operation_id"],
            "receipt_digest": journal["prepare_receipt"]["sha256"],
        },
        prepare_path=Path(journal["prepare_receipt"]["path"]),
        owner_repo=owner_repo,
        source_root=Path(source["root"]),
        source_ref=source["ref"],
        source_tree=source["tree"],
        destination=destination,
        release_root=release_root,
        release_path=activated_release,
        predecessor=predecessor,
        admission=admission,
        recovery_path=recovery_path,
        recovery_digest=journal["receipt_digest"],
    )


def _recover_finalize(recovery_path: Path) -> dict[str, Any]:
    journal = _load_recovery_journal(recovery_path)
    journal["_recovery_path"] = os.fspath(recovery_path)
    owner_repo, destination, release_root, activated_release, _, activation_path = _recovery_paths(journal)
    lock_path = _lock_path(release_root, owner_repo)
    with _deployment_lock(lock_path):
        fresh = _load_recovery_journal(recovery_path)
        fresh["_recovery_path"] = os.fspath(recovery_path)
        if fresh.get("status") == "rolled_back":
            raise DeploymentError("recovery_already_rolled_back", "a rolled-back journal cannot be finalized")
        if os.path.lexists(activation_path):
            activation = _load_activation_receipt(activation_path)
            if activation.get("operation_id") != fresh.get("operation_id"):
                raise DeploymentError("recovery_record_invalid", "activation receipt operation does not match journal")
            finalized = {key: value for key, value in fresh.items() if key != "_recovery_path"}
            finalized.update(
                {
                    "status": "finalized",
                    "updated_at": _iso(_utc_now()),
                    "activation_receipt": _recovery_reference(activation_path, activation),
                }
            )
            try:
                _write_json(recovery_path, finalized)
            except DeploymentError:
                pass
            return {"receipt_path": os.fspath(activation_path), **activation}
        current = _snapshot_destination(destination, release_root)
        expected = _recovery_target_snapshot(fresh)
        if not _same_snapshot(current, expected):
            raise DeploymentError(
                "recovery_state_unrecognized",
                "destination is neither the recorded activated release nor a finalizable state",
            )
        source = fresh["source"]
        _verify_recorded_release(
            activated_release,
            source["ref"],
            source["tree"],
            label="activated_release",
        )
        payload = _recovery_activation_receipt(journal=fresh, recovery_path=recovery_path)
        try:
            receipt = _write_json(activation_path, payload)
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
        finalized = {key: value for key, value in fresh.items() if key != "_recovery_path"}
        finalized.update(
            {
                "status": "finalized",
                "updated_at": _iso(_utc_now()),
                "activation_receipt": _recovery_reference(activation_path, receipt),
            }
        )
        try:
            _write_json(recovery_path, finalized)
        except DeploymentError:
            pass
        return {"receipt_path": os.fspath(activation_path), **receipt}


def _recovery_activation_reference(journal: dict[str, Any], activation_path: Path) -> dict[str, Any]:
    if os.path.lexists(activation_path):
        activation = _load_activation_receipt(activation_path)
        return {
            "path": os.fspath(activation_path),
            "sha256": activation["receipt_digest"],
            "status": "complete",
        }
    return {"path": os.fspath(activation_path), "status": "not_written"}


def _recover_rollback(recovery_path: Path) -> dict[str, Any]:
    journal = _load_recovery_journal(recovery_path)
    journal["_recovery_path"] = os.fspath(recovery_path)
    owner_repo, destination, release_root, activated_release, _, activation_path = _recovery_paths(journal)
    rollback_path = _absolute_path(journal["rollback_receipt_path"], "recovery rollback receipt")
    if journal.get("status") == "rolled_back" and os.path.lexists(rollback_path):
        rollback_receipt = _load_json(rollback_path, "rollback receipt")[0]
        _verify_receipt_digest(rollback_receipt, "rollback receipt")
        return {"receipt_path": os.fspath(rollback_path), **rollback_receipt}
    lock_path = _lock_path(release_root, owner_repo)
    with _deployment_lock(lock_path):
        fresh = _load_recovery_journal(recovery_path)
        fresh["_recovery_path"] = os.fspath(recovery_path)
        if fresh.get("status") == "rolled_back" and os.path.lexists(rollback_path):
            rollback_receipt = _load_json(rollback_path, "rollback receipt")[0]
            _verify_receipt_digest(rollback_receipt, "rollback receipt")
            return {"receipt_path": os.fspath(rollback_path), **rollback_receipt}
        if fresh.get("status") == "rolled_back":
            raise DeploymentError("recovery_record_invalid", "rolled-back journal lacks rollback receipt")
        current = _snapshot_destination(destination, release_root)
        expected_target = _recovery_target_snapshot(fresh)
        predecessor = fresh["predecessor"]
        if _same_snapshot(current, expected_target):
            source = fresh["source"]
            _verify_recorded_release(
                activated_release,
                source["ref"],
                source["tree"],
                label="activated_release",
            )
            _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
            restored = _restore_predecessor(destination, predecessor, release_root)
            identity_checked = True
        elif _same_snapshot(current, predecessor):
            _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
            restored = predecessor.get("target") if predecessor.get("kind") == "symlink" else None
            identity_checked = True
        else:
            raise DeploymentError(
                "recovery_state_unrecognized",
                "destination is neither the recorded activated release nor its predecessor",
            )
        activation_ref = _recovery_activation_reference(fresh, activation_path)
        payload = {
            "schema_version": ROLLBACK_SCHEMA,
            "status": "rolled_back",
            "operation_id": fresh["operation_id"],
            "rolled_back_at": _iso(_utc_now()),
            "owner_repo": owner_repo,
            "activation_receipt": activation_ref,
            "recovery_journal": _recovery_reference(recovery_path, fresh),
            "destination": os.fspath(destination),
            "release_root": os.fspath(release_root),
            "removed_activation": os.fspath(activated_release),
            "restored_predecessor": predecessor,
            "restored_target": restored,
            "atomicity": {
                "same_filesystem": True,
                "switch": "relative-symlink-os-replace",
                "destination_identity_checked": identity_checked,
                "predecessor_identity_checked": True,
            },
            "dependency_posture": "source_only_no_install",
            "effects": [
                "destination_symlink_restored"
                if _same_snapshot(current, expected_target) and restored
                else "destination_removed"
                if _same_snapshot(current, expected_target)
                else "destination_unchanged"
            ],
            "claim_ceiling": "source_activation_rollback_only_no_runtime_claim",
        }
        receipt = _write_json(rollback_path, payload)
        finalized = {key: value for key, value in fresh.items() if key != "_recovery_path"}
        finalized.update(
            {
                "status": "rolled_back",
                "updated_at": _iso(_utc_now()),
                "rollback_receipt": _recovery_reference(rollback_path, receipt),
            }
        )
        try:
            _write_json(recovery_path, finalized)
        except DeploymentError:
            pass
        return {"receipt_path": os.fspath(rollback_path), **receipt}


def recover(args: argparse.Namespace) -> dict[str, Any]:
    recovery_path = _existing_path(args.recovery_journal, "recovery journal")
    if args.action == "finalize":
        return _recover_finalize(recovery_path)
    return _recover_rollback(recovery_path)


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
    recover_parser = commands.add_parser(
        "recover",
        help="deterministically finalize or roll back a durable activation recovery journal",
    )
    _add_path_argument(recover_parser, "--recovery-journal")
    recover_parser.add_argument("--action", choices=("finalize", "rollback"), required=True)
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
            elif args.command == "rollback":
                result = rollback(args)
            else:
                result = recover(args)
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
    if error.context:
        error_payload["recovery"] = error.context
    print(json.dumps(error_payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
