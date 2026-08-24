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
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - the owner target is Linux
    fcntl = None  # type: ignore[assignment]

try:
    _LIBC = ctypes.CDLL(None, use_errno=True)
    _RENAMEAT2 = _LIBC.renameat2
    _RENAMEAT2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    _RENAMEAT2.restype = ctypes.c_int
except (AttributeError, OSError):  # pragma: no cover - non-Linux fallback is fail-closed
    _RENAMEAT2 = None


ADMISSION_SCHEMA = "abyss_stack_owner_source_deployment_admission_v1"
PREPARE_SCHEMA = "abyss_stack_owner_source_prepare_receipt_v1"
ACTIVATE_SCHEMA = "abyss_stack_owner_source_activate_receipt_v1"
ROLLBACK_SCHEMA = "abyss_stack_owner_source_rollback_receipt_v1"
RECOVERY_SCHEMA = "abyss_stack_owner_source_activation_recovery_v1"
ERROR_SCHEMA = "abyss_stack_owner_source_deployment_error_v1"
RELEASE_SEAL_SCHEMA = "abyss_stack_owner_source_release_seal_v1"
RELEASE_MANIFEST_SCHEMA = "abyss_stack_owner_source_release_manifest_v1"
RELEASE_BINDING_METHOD = "content-manifest-root-inode-v1"
RELEASE_IGNORED_POLICY = "included_in_manifest"
RELEASE_SYMLINK_POLICY = "record_target_no_follow"
RELEASE_SPECIAL_FILE_POLICY = "reject"
POST_SWITCH_VERIFICATION = "required_before_activation_receipt"
POST_SWITCH_ROLLBACK = "durable-predecessor-restore"
FINALIZATION_METHOD = "atomic-destination-effect-v1"
DESTINATION_CAS_METHOD = "rename-noreplace-displaced-v1"
ACTIVATION_CLAIM_CEILING = "source_activation_event_only_no_current_destination_claim"
RECOVERY_CLAIM_CEILING = "source_activation_event_recovery_only_no_current_destination_claim"
SOURCE_ROUTE_ADMISSION_KIND = "owner_source_deployment_route"
ALLOWED_AUTHORITY_CEILINGS = {
    "disposable-source-package-canary",
    "installed-source-package-activation",
}
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
AT_FDCWD = -100
RENAME_NOREPLACE = 1


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
    seal: dict[str, Any] | None = None,
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
    _verify_release_seal(release_path, expected_ref, expected_tree, seal)
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
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
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
    except OSError as exc:
        raise OSError(f"cannot open directory for fsync: {directory}: {exc}") from exc
    try:
        os.fsync(fd)
    except OSError as exc:
        raise OSError(f"cannot fsync directory: {directory}: {exc}") from exc
    finally:
        os.close(fd)


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Move one path only when the destination is absent, atomically."""

    if _RENAMEAT2 is None:
        raise OSError(errno.ENOTSUP, "renameat2(RENAME_NOREPLACE) is unavailable")
    result = _RENAMEAT2(
        AT_FDCWD,
        os.fsencode(source),
        AT_FDCWD,
        os.fsencode(destination),
        RENAME_NOREPLACE,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), os.fspath(destination))


def _verify_receipt_digest(payload: dict[str, Any], field: str) -> None:
    supplied = payload.get("receipt_digest")
    if not isinstance(supplied, str) or supplied != _digest_payload(payload):
        raise DeploymentError("receipt_digest_mismatch", f"{field} is not self-consistent")


def _release_seal_path(release_path: Path) -> Path:
    return release_path.parent / f".{release_path.name}.seal.json"


def _release_stat_fingerprint(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_mode),
        int(value.st_size),
        int(value.st_mtime_ns),
        int(value.st_ctime_ns),
    )


def _release_root_identity(release_path: Path) -> dict[str, int]:
    try:
        value = os.lstat(release_path)
    except OSError as exc:
        raise DeploymentError("release_seal_invalid", f"cannot stat release root: {release_path}") from exc
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
        raise DeploymentError("release_seal_invalid", f"release root is not a directory: {release_path}")
    return {
        "root_device": int(value.st_dev),
        "root_inode": int(value.st_ino),
        "root_mode": int(stat.S_IMODE(value.st_mode)),
    }


def _hash_release_file(path: Path, expected: os.stat_result) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise DeploymentError("release_manifest_unreadable", f"cannot open release file: {path}") from exc
    try:
        opened = os.fstat(fd)
        if _release_stat_fingerprint(opened) != _release_stat_fingerprint(expected):
            raise DeploymentError("release_manifest_changed", f"release file changed before hashing: {path}")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        closed = os.fstat(fd)
        if _release_stat_fingerprint(closed) != _release_stat_fingerprint(expected):
            raise DeploymentError("release_manifest_changed", f"release file changed while hashing: {path}")
        return digest.hexdigest()
    except OSError as exc:
        raise DeploymentError("release_manifest_unreadable", f"cannot hash release file: {path}") from exc
    finally:
        os.close(fd)


def _release_manifest(release_path: Path) -> tuple[str, int]:
    """Hash every release entry without following symlinks or trusting Git status."""

    entries: list[dict[str, Any]] = []

    def visit(path: Path, relative: str) -> None:
        try:
            before = os.lstat(path)
        except OSError as exc:
            raise DeploymentError("release_manifest_unreadable", f"cannot stat release entry: {path}") from exc
        mode = before.st_mode
        if stat.S_ISLNK(mode):
            try:
                target = os.readlink(path)
                after = os.lstat(path)
            except OSError as exc:
                raise DeploymentError("release_manifest_unreadable", f"cannot read release symlink: {path}") from exc
            if _release_stat_fingerprint(before) != _release_stat_fingerprint(after):
                raise DeploymentError("release_manifest_changed", f"release symlink changed while sealing: {path}")
            entries.append(
                {
                    "kind": "symlink",
                    "path": relative,
                    "target": target,
                }
            )
            return
        if stat.S_ISREG(mode):
            digest = _hash_release_file(path, before)
            try:
                after = os.lstat(path)
            except OSError as exc:
                raise DeploymentError("release_manifest_unreadable", f"cannot restat release file: {path}") from exc
            if _release_stat_fingerprint(before) != _release_stat_fingerprint(after):
                raise DeploymentError("release_manifest_changed", f"release file changed while sealing: {path}")
            entries.append(
                {
                    "kind": "file",
                    "mode": int(stat.S_IMODE(mode)),
                    "mtime_ns": int(before.st_mtime_ns),
                    "path": relative,
                    "sha256": digest,
                    "size": int(before.st_size),
                }
            )
            return
        if stat.S_ISDIR(mode):
            entries.append(
                {
                    "kind": "directory",
                    "mode": int(stat.S_IMODE(mode)),
                    "mtime_ns": int(before.st_mtime_ns),
                    "path": relative,
                }
            )
            try:
                with os.scandir(path) as directory:
                    names = sorted(entry.name for entry in directory)
            except OSError as exc:
                raise DeploymentError("release_manifest_unreadable", f"cannot enumerate release directory: {path}") from exc
            for name in names:
                child_relative = name if relative == "." else f"{relative}/{name}"
                visit(path / name, child_relative)
            try:
                after = os.lstat(path)
            except OSError as exc:
                raise DeploymentError("release_manifest_unreadable", f"cannot restat release directory: {path}") from exc
            if _release_stat_fingerprint(before) != _release_stat_fingerprint(after):
                raise DeploymentError("release_manifest_changed", f"release directory changed while sealing: {path}")
            return
        raise DeploymentError(
            "release_manifest_unsupported_entry",
            f"release contains an unsupported filesystem entry: {path}",
        )

    visit(release_path, ".")
    manifest = {
        "schema_version": RELEASE_MANIFEST_SCHEMA,
        "entries": entries,
        "ignored_policy": RELEASE_IGNORED_POLICY,
        "special_file_policy": RELEASE_SPECIAL_FILE_POLICY,
        "symlink_policy": RELEASE_SYMLINK_POLICY,
    }
    return _digest_payload(manifest), len(entries)


def _release_entries(release_path: Path) -> Iterator[Path]:
    for root, directories, files in os.walk(release_path, topdown=False, followlinks=False):
        for name in files:
            path = Path(root) / name
            if not path.is_symlink():
                yield path
        for name in directories:
            path = Path(root) / name
            if not path.is_symlink():
                yield path


def _set_release_read_only(release_path: Path) -> None:
    for path in _release_entries(release_path):
        mode = stat.S_IMODE(os.lstat(path).st_mode)
        os.chmod(path, mode & ~0o222)
    mode = stat.S_IMODE(os.lstat(release_path).st_mode)
    os.chmod(release_path, mode & ~0o222)


def _assert_release_read_only(release_path: Path) -> None:
    paths = [release_path, *_release_entries(release_path)]
    for path in paths:
        mode = stat.S_IMODE(os.lstat(path).st_mode)
        if mode & 0o222:
            raise DeploymentError(
                "release_not_sealed",
                f"release contains a writable path: {path}",
            )


def _release_seal_reference(
    release_path: Path,
    seal_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "path": os.fspath(_release_seal_path(release_path)),
        "sha256": str(seal_payload["receipt_digest"]),
        "release_path": os.fspath(release_path),
        "source_ref": str(seal_payload["source_ref"]),
        "source_tree": str(seal_payload["source_tree"]),
        "mode": "read_only",
        "root_device": int(seal_payload["root_device"]),
        "root_inode": int(seal_payload["root_inode"]),
        "root_mode": int(seal_payload["root_mode"]),
        "manifest_schema": str(seal_payload["manifest_schema"]),
        "manifest_sha256": str(seal_payload["manifest_sha256"]),
        "manifest_entries": int(seal_payload["manifest_entries"]),
        "ignored_policy": str(seal_payload["ignored_policy"]),
        "symlink_policy": str(seal_payload["symlink_policy"]),
        "special_file_policy": str(seal_payload["special_file_policy"]),
    }


def _verify_release_seal(
    release_path: Path,
    expected_ref: str,
    expected_tree: str,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seal_path = _release_seal_path(release_path)
    payload, _ = _load_json(seal_path, "release seal")
    _verify_receipt_digest(payload, "release seal")
    if payload.get("schema_version") != RELEASE_SEAL_SCHEMA:
        raise DeploymentError("release_seal_invalid", "unsupported release seal schema")
    if payload.get("release_path") != os.fspath(release_path):
        raise DeploymentError("release_seal_invalid", "release seal path is not bound")
    if payload.get("source_ref") != expected_ref or payload.get("source_tree") != expected_tree:
        raise DeploymentError("release_seal_invalid", "release seal Git identity is not bound")
    if payload.get("mode") != "read_only":
        raise DeploymentError("release_seal_invalid", "release seal mode is not read-only")
    root_identity = _release_root_identity(release_path)
    for key in ("root_device", "root_inode", "root_mode"):
        if payload.get(key) != root_identity[key]:
            raise DeploymentError("release_seal_inode_mismatch", "release root inode binding does not match")
    if payload.get("manifest_schema") != RELEASE_MANIFEST_SCHEMA:
        raise DeploymentError("release_seal_invalid", "release manifest schema is not bound")
    if payload.get("ignored_policy") != RELEASE_IGNORED_POLICY:
        raise DeploymentError("release_seal_invalid", "release ignored-content policy is not bound")
    if payload.get("symlink_policy") != RELEASE_SYMLINK_POLICY:
        raise DeploymentError("release_seal_invalid", "release symlink policy is not bound")
    if payload.get("special_file_policy") != RELEASE_SPECIAL_FILE_POLICY:
        raise DeploymentError("release_seal_invalid", "release special-file policy is not bound")
    if reference is not None:
        if reference.get("path") != os.fspath(seal_path):
            raise DeploymentError("release_seal_invalid", "release seal reference path is not bound")
        if reference.get("sha256") != payload.get("receipt_digest"):
            raise DeploymentError("release_seal_invalid", "release seal reference digest does not match")
        if reference.get("release_path") != os.fspath(release_path):
            raise DeploymentError("release_seal_invalid", "release seal reference release is not bound")
        if reference.get("source_ref") != expected_ref or reference.get("source_tree") != expected_tree:
            raise DeploymentError("release_seal_invalid", "release seal reference identity is not bound")
        if reference.get("mode") != "read_only":
            raise DeploymentError("release_seal_invalid", "release seal reference mode is invalid")
        for key in (
            "root_device",
            "root_inode",
            "root_mode",
            "manifest_schema",
            "manifest_sha256",
            "manifest_entries",
            "ignored_policy",
            "symlink_policy",
            "special_file_policy",
        ):
            if reference.get(key) != payload.get(key):
                raise DeploymentError("release_seal_invalid", f"release seal reference {key} does not match")
    _assert_release_read_only(release_path)
    manifest_sha256, manifest_entries = _release_manifest(release_path)
    if payload.get("manifest_sha256") != manifest_sha256 or payload.get("manifest_entries") != manifest_entries:
        raise DeploymentError("release_seal_content_mismatch", "release content manifest does not match its seal")
    if _release_root_identity(release_path) != root_identity:
        raise DeploymentError("release_seal_inode_mismatch", "release root changed while validating its seal")
    _assert_release_read_only(release_path)
    return _release_seal_reference(release_path, payload)


def _seal_release(release_path: Path, source_ref: str, source_tree: str) -> dict[str, Any]:
    _verify_clean_identity(release_path, source_ref, source_tree)
    _set_release_read_only(release_path)
    root_identity = _release_root_identity(release_path)
    manifest_sha256, manifest_entries = _release_manifest(release_path)
    seal_payload = {
        "schema_version": RELEASE_SEAL_SCHEMA,
        "release_path": os.fspath(release_path),
        "source_ref": source_ref,
        "source_tree": source_tree,
        "mode": "read_only",
        **root_identity,
        "manifest_schema": RELEASE_MANIFEST_SCHEMA,
        "manifest_sha256": manifest_sha256,
        "manifest_entries": manifest_entries,
        "ignored_policy": RELEASE_IGNORED_POLICY,
        "symlink_policy": RELEASE_SYMLINK_POLICY,
        "special_file_policy": RELEASE_SPECIAL_FILE_POLICY,
    }
    written = _write_json(_release_seal_path(release_path), seal_payload)
    return _verify_release_seal(release_path, source_ref, source_tree, _release_seal_reference(release_path, written))


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


def _snapshot_destination(
    destination: Path,
    release_root: Path,
    *,
    strict_seal: bool = True,
) -> dict[str, Any]:
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
    try:
        seal = _verify_release_seal(target, identity["ref"], identity["tree"])
    except DeploymentError as exc:
        if strict_seal or exc.code != "receipt_missing":
            raise
        seal = None
    snapshot = {
        "kind": "symlink",
        "link_text": link_text,
        "target": os.fspath(target),
        "source_ref": identity["ref"],
        "source_tree": identity["tree"],
    }
    if seal is not None:
        snapshot["release_seal"] = seal
    return snapshot


def _same_snapshot(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("kind") != right.get("kind"):
        return False
    if left.get("kind") == "absent":
        return True
    return all(
        left.get(key) == right.get(key)
        for key in ("target", "source_ref", "source_tree", "release_seal")
    )


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
    seal = snapshot.get("release_seal")
    if not isinstance(seal, dict):
        raise DeploymentError(f"{label}_invalid", "recorded snapshot lacks release seal")
    _verify_recorded_release(target, expected_ref, expected_tree, label=label, seal=seal)
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


def _receipt_binding(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source")
    predecessor = payload.get("predecessor", payload.get("restored_predecessor"))
    activated_release = payload.get("activated_release", payload.get("removed_activation"))
    release_seal = payload.get("release_seal")
    admission = payload.get("admission")
    if not isinstance(source, dict) or not isinstance(predecessor, dict):
        raise DeploymentError("recovery_record_invalid", "receipt binding lacks source or predecessor")
    if not isinstance(activated_release, str) or not isinstance(release_seal, dict):
        raise DeploymentError("recovery_record_invalid", "receipt binding lacks activated release or seal")
    if not isinstance(admission, dict):
        raise DeploymentError("recovery_record_invalid", "receipt binding lacks admission")
    binding = {
        "operation_id": payload.get("operation_id"),
        "prepare_operation_id": payload.get("prepare_operation_id"),
        "owner_repo": payload.get("owner_repo"),
        "source": source,
        "destination": payload.get("destination"),
        "release_root": payload.get("release_root"),
        "activated_release": activated_release,
        "release_seal": release_seal,
        "predecessor": predecessor,
        "admission": admission,
    }
    destination_owner = payload.get("destination_owner")
    if destination_owner is not None:
        _validate_destination_owner(destination_owner, "receipt destination owner")
        binding["destination_owner"] = destination_owner
    elif payload.get("status") in {
        "activated",
        "switch_complete",
        "finalized",
    } or (payload.get("status") == "rolled_back" and payload.get("destination_owner") is not None):
        raise DeploymentError("recovery_record_invalid", "receipt binding lacks destination owner")
    finalization = payload.get("finalization")
    if finalization is not None:
        _validate_finalization(finalization, "receipt finalization")
        binding["finalization"] = finalization
    return binding


def _recovery_binding_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation_id": payload["operation_id"],
        "prepare_operation_id": payload["prepare_operation_id"],
        "owner_repo": payload["owner_repo"],
        "prepare_receipt": payload["prepare_receipt"],
        "source": payload["source"],
        "destination": payload["destination"],
        "release_root": payload["release_root"],
        "activated_release": payload["activated_release"],
        "release_seal": payload["release_seal"],
        "predecessor": payload["predecessor"],
        "admission": payload["admission"],
        "activation_receipt_path": payload["activation_receipt_path"],
        "rollback_receipt_path": payload["rollback_receipt_path"],
        "atomicity": payload["atomicity"],
        "claim_ceiling": payload["claim_ceiling"],
        "destination_owner": payload.get("destination_owner"),
        "finalization": payload.get("finalization"),
    }


def _recovery_binding_digest(payload: dict[str, Any]) -> str:
    return _digest_payload(_recovery_binding_payload(payload))


def _completed_receipt_reference(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    digest = payload.get("receipt_digest")
    if not isinstance(digest, str):
        raise DeploymentError("recovery_record_invalid", "receipt lacks receipt digest")
    return {
        "path": os.fspath(path),
        "sha256": digest,
        "status": "complete",
        "binding": _receipt_binding(payload),
    }


def _recovery_journal_reference(
    path: Path,
    payload: dict[str, Any],
    *,
    status: str,
) -> dict[str, Any]:
    binding_digest = payload.get("binding_sha256")
    if status == "switch_complete":
        digest = payload.get("switch_complete_sha256")
    elif status == "rollback_switch_complete":
        digest = payload.get("rollback_switch_complete_sha256")
    else:
        digest = payload.get("receipt_digest")
    if not isinstance(digest, str) or not isinstance(binding_digest, str):
        raise DeploymentError("recovery_record_invalid", "recovery journal lacks digest binding")
    return {
        "path": os.fspath(path),
        "sha256": digest,
        "binding_sha256": binding_digest,
        "status": payload["status"],
        "binding": _receipt_binding(payload),
    }


def _validate_journal_reference(
    reference: dict[str, Any],
    journal: dict[str, Any],
    *,
    label: str,
    allowed_statuses: set[str],
) -> None:
    if not isinstance(reference, dict):
        raise DeploymentError("recovery_record_invalid", f"{label} is not an object")
    for key in ("path", "sha256", "binding_sha256", "status", "binding"):
        if key not in reference:
            raise DeploymentError("recovery_record_invalid", f"{label} lacks {key}")
    if not isinstance(reference["path"], str) or not Path(reference["path"]).is_absolute():
        raise DeploymentError("recovery_record_invalid", f"{label} path is not absolute")
    if not re.fullmatch(r"[0-9a-f]{64}", str(reference["sha256"])):
        raise DeploymentError("recovery_record_invalid", f"{label} digest is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(reference["binding_sha256"])):
        raise DeploymentError("recovery_record_invalid", f"{label} binding digest is invalid")
    if reference["binding_sha256"] != journal.get("binding_sha256"):
        raise DeploymentError("recovery_record_invalid", f"{label} binding digest does not match journal")
    if reference["binding"] != _receipt_binding(journal):
        raise DeploymentError("recovery_record_invalid", f"{label} identity binding does not match journal")
    if reference["status"] not in allowed_statuses:
        raise DeploymentError("recovery_record_invalid", f"{label} state is not compatible")
    if reference["status"] == "switch_complete":
        expected_digest = journal.get("switch_complete_sha256")
    elif reference["status"] == "rollback_switch_complete":
        expected_digest = journal.get("rollback_switch_complete_sha256")
    else:
        expected_digest = journal.get("receipt_digest")
    if reference["sha256"] != expected_digest:
        raise DeploymentError("recovery_record_invalid", f"{label} state digest does not match journal")


def _validate_historical_activation_reference(
    reference: dict[str, Any],
    activation: dict[str, Any],
    journal: dict[str, Any],
) -> None:
    """Validate an activation receipt's pre-rollback journal reference.

    Rollback intentionally removes the finalization event from the live
    recovery journal before emitting a rollback receipt.  The activation
    receipt still points at the prior switch-complete state, so validate that
    historical state against a reconstructed binding instead of comparing it
    to the post-rollback journal binding.
    """

    if not isinstance(reference, dict):
        raise DeploymentError("recovery_record_invalid", "activation recovery journal is not an object")
    for key in ("path", "sha256", "binding_sha256", "status", "binding"):
        if key not in reference:
            raise DeploymentError("recovery_record_invalid", f"activation recovery journal lacks {key}")
    if not isinstance(reference["path"], str) or not Path(reference["path"]).is_absolute():
        raise DeploymentError("recovery_record_invalid", "activation recovery journal path is not absolute")
    if not re.fullmatch(r"[0-9a-f]{64}", str(reference["sha256"])):
        raise DeploymentError("recovery_record_invalid", "activation recovery journal digest is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(reference["binding_sha256"])):
        raise DeploymentError("recovery_record_invalid", "activation recovery journal binding digest is invalid")
    if reference["status"] != "switch_complete":
        raise DeploymentError("recovery_record_invalid", "activation recovery journal historical state is invalid")
    activation_binding = _receipt_binding(activation)
    if reference["binding"] != activation_binding:
        raise DeploymentError("recovery_record_invalid", "activation recovery journal historical binding is invalid")
    finalization = activation.get("finalization")
    if not isinstance(finalization, dict):
        raise DeploymentError("recovery_record_invalid", "activation receipt lacks finalization event")
    historical = dict(journal)
    historical["finalization"] = finalization
    historical["binding_sha256"] = _recovery_binding_digest(historical)
    if reference["binding_sha256"] != historical["binding_sha256"]:
        raise DeploymentError("recovery_record_invalid", "activation recovery journal historical binding digest is invalid")
    if reference["sha256"] != _recovery_state_digest(historical, "switch_complete"):
        raise DeploymentError("recovery_record_invalid", "activation recovery journal historical state digest is invalid")


def _validate_completed_receipt_reference(
    reference: dict[str, Any],
    expected_path: Path,
    payload: dict[str, Any],
    *,
    label: str,
) -> None:
    if not isinstance(reference, dict):
        raise DeploymentError("recovery_record_invalid", f"{label} is not an object")
    if reference.get("path") != os.fspath(expected_path):
        raise DeploymentError("recovery_record_invalid", f"{label} path is not deterministic")
    if reference.get("status") != "complete":
        raise DeploymentError("recovery_record_invalid", f"{label} is not complete")
    if reference.get("sha256") != payload.get("receipt_digest"):
        raise DeploymentError("recovery_record_invalid", f"{label} digest does not match receipt")
    if reference.get("binding") != _receipt_binding(payload):
        raise DeploymentError("recovery_record_invalid", f"{label} identity binding does not match receipt")


def _recovery_state_digest(payload: dict[str, Any], status: str) -> str:
    state = {
        "binding_sha256": payload["binding_sha256"],
        "status": status,
        "switched_at": payload.get("switched_at"),
    }
    if status == "rollback_switch_complete":
        state.update(
            {
                "rollback_started_at": payload.get("rollback_started_at"),
                "rollback_switched_at": payload.get("rollback_switched_at"),
            }
        )
    return _digest_payload(state)


def _validate_admission_binding(admission: Any, label: str) -> dict[str, Any]:
    if not isinstance(admission, dict):
        raise DeploymentError("recovery_record_invalid", f"{label} lacks admission binding")
    for key in ("path", "sha256", "admission_id", "authority_ceiling"):
        if not isinstance(admission.get(key), str) or not admission[key]:
            raise DeploymentError("recovery_record_invalid", f"{label} lacks {key}")
    if not re.fullmatch(r"[0-9a-f]{64}", admission["sha256"]):
        raise DeploymentError("recovery_record_invalid", f"{label} digest is invalid")
    _absolute_path(admission["path"], f"{label} path")
    if admission["authority_ceiling"] not in ALLOWED_AUTHORITY_CEILINGS:
        raise DeploymentError("recovery_record_invalid", f"{label} authority is invalid")
    return admission


def _validate_receipt_path_reference(reference: Any, label: str) -> dict[str, Any]:
    if not isinstance(reference, dict):
        raise DeploymentError("recovery_record_invalid", f"{label} is not an object")
    if not isinstance(reference.get("path"), str) or not Path(reference["path"]).is_absolute():
        raise DeploymentError("recovery_record_invalid", f"{label} path is invalid")
    if not isinstance(reference.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", reference["sha256"]):
        raise DeploymentError("recovery_record_invalid", f"{label} digest is invalid")
    return reference


def _validate_destination_owner(owner: Any, label: str) -> dict[str, Any]:
    if not isinstance(owner, dict):
        raise DeploymentError("recovery_record_invalid", f"{label} is not an object")
    for key in ("target", "link_text"):
        if not isinstance(owner.get(key), str) or not owner[key]:
            raise DeploymentError("recovery_record_invalid", f"{label} lacks {key}")
    _absolute_path(owner["target"], f"{label}.target")
    for key in ("device", "inode", "mode"):
        if not isinstance(owner.get(key), int) or owner[key] < 0:
            raise DeploymentError("recovery_record_invalid", f"{label} {key} is invalid")
    if owner["inode"] == 0:
        raise DeploymentError("recovery_record_invalid", f"{label} inode is invalid")
    return owner


def _validate_finalization(finalization: Any, label: str) -> None:
    if not isinstance(finalization, dict):
        raise DeploymentError("recovery_record_invalid", f"{label} is not an object")
    if (
        finalization.get("method") != FINALIZATION_METHOD
        or finalization.get("status") != "committed"
        or finalization.get("effect") != "relative-symlink-os-replace"
        or finalization.get("current_destination_claim") is not False
    ):
        raise DeploymentError("recovery_record_invalid", f"{label} method or status is invalid")
    _timestamp(str(finalization.get("committed_at", "")), f"{label}.committed_at")
    destination = finalization.get("destination")
    _validate_destination_owner(destination, f"{label} destination identity")
    release = finalization.get("release")
    if not isinstance(release, dict):
        raise DeploymentError("recovery_record_invalid", f"{label} lacks release identity")
    if not isinstance(release.get("path"), str) or not Path(release["path"]).is_absolute():
        raise DeploymentError("recovery_record_invalid", f"{label} release path is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(release.get("manifest_sha256", ""))):
        raise DeploymentError("recovery_record_invalid", f"{label} manifest digest is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(release.get("seal_sha256", ""))):
        raise DeploymentError("recovery_record_invalid", f"{label} seal digest is invalid")
    for key in ("root_device", "root_inode"):
        if not isinstance(release.get(key), int) or release[key] < 0:
            raise DeploymentError("recovery_record_invalid", f"{label} release {key} is invalid")
    if release["root_inode"] == 0:
        raise DeploymentError("recovery_record_invalid", f"{label} release root inode is invalid")


def _validate_finalization_binding(
    finalization: Any,
    *,
    destination: Path,
    release_root: Path,
    activated_release: Path,
    release_seal: dict[str, Any],
    label: str,
    destination_owner: dict[str, Any] | None = None,
) -> None:
    _validate_finalization(finalization, label)
    recorded_destination = finalization["destination"]
    if destination_owner is not None:
        _validate_destination_owner(destination_owner, f"{label} destination owner")
        if recorded_destination != destination_owner:
            raise DeploymentError("recovery_record_invalid", f"{label} destination owner is not event-bound")
    expected_target = os.fspath(activated_release.resolve(strict=False))
    expected_link_text = os.path.relpath(activated_release, destination.parent)
    if (
        recorded_destination["target"] != expected_target
        or recorded_destination["link_text"] != expected_link_text
    ):
        raise DeploymentError("recovery_record_invalid", f"{label} destination target is not bound")
    recorded_release = finalization["release"]
    if (
        recorded_release["path"] != os.fspath(activated_release)
        or recorded_release["root_device"] != release_seal.get("root_device")
        or recorded_release["root_inode"] != release_seal.get("root_inode")
        or recorded_release["manifest_sha256"] != release_seal.get("manifest_sha256")
        or recorded_release["seal_sha256"] != release_seal.get("sha256")
    ):
        raise DeploymentError("recovery_record_invalid", f"{label} release identity is not bound")
    try:
        activated_release.relative_to(release_root.resolve(strict=False))
    except ValueError as exc:
        raise DeploymentError("recovery_record_invalid", f"{label} release is unmanaged") from exc


def _validate_activation_receipt_payload(payload: dict[str, Any], path: Path) -> None:
    _verify_receipt_digest(payload, "activation receipt")
    if payload.get("schema_version") != ACTIVATE_SCHEMA or payload.get("status") != "activated":
        raise DeploymentError("activation_receipt_invalid", "activation receipt is not rollback-capable")
    _validate_operation_id(payload.get("operation_id"), "activation operation_id")
    prepare_operation_id = _validate_operation_id(payload.get("prepare_operation_id"), "activation prepare_operation_id")
    _timestamp(str(payload.get("activated_at", "")), "activation activated_at")
    owner_repo = _validate_owner(str(payload.get("owner_repo", "")))
    source = payload.get("source")
    if not isinstance(source, dict) or source.get("dirty") is not False:
        raise DeploymentError("activation_receipt_invalid", "activation source is not cleanly bound")
    source_root = _absolute_path(str(source.get("root", "")), "activation source root")
    source_ref = _validate_commit(str(source.get("ref", "")), "activation source ref")
    source_tree = _validate_commit(str(source.get("tree", "")), "activation source tree")
    destination = _absolute_path(str(payload.get("destination", "")), "activation destination")
    release_root = _absolute_path(str(payload.get("release_root", "")), "activation release root")
    activated_release = _absolute_path(str(payload.get("activated_release", "")), "activated release")
    try:
        activated_release.relative_to(release_root.resolve(strict=False))
    except ValueError as exc:
        raise DeploymentError("activation_receipt_invalid", "activated release is unmanaged") from exc
    release_seal = payload.get("release_seal")
    if not isinstance(release_seal, dict):
        raise DeploymentError("activation_receipt_invalid", "activation receipt lacks release seal")
    _verify_recorded_release(activated_release, source_ref, source_tree, label="activated_release", seal=release_seal)
    destination_owner = _validate_destination_owner(
        payload.get("destination_owner"), "activation destination owner"
    )
    predecessor = payload.get("predecessor")
    if not isinstance(predecessor, dict):
        raise DeploymentError("activation_receipt_invalid", "activation receipt lacks predecessor snapshot")
    _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
    _validate_finalization_binding(
        payload.get("finalization"),
        destination=destination,
        release_root=release_root,
        activated_release=activated_release,
        release_seal=release_seal,
        label="activation finalization",
        destination_owner=destination_owner,
    )
    prepare_reference = _validate_receipt_path_reference(payload.get("prepare_receipt"), "activation prepare receipt")
    expected_prepare_path = path.parent / f"prepare-{prepare_operation_id}.json"
    if Path(prepare_reference["path"]) != expected_prepare_path:
        raise DeploymentError("activation_receipt_invalid", "activation prepare receipt path is not deterministic")
    prepare_payload, _ = _load_prepare_receipt(expected_prepare_path)
    if prepare_reference["sha256"] != prepare_payload.get("receipt_digest"):
        raise DeploymentError("activation_receipt_invalid", "activation prepare receipt digest does not match")
    _validate_admission_binding(payload.get("admission"), "activation admission")
    recovery = payload.get("recovery_journal")
    if not isinstance(recovery, dict):
        raise DeploymentError("activation_receipt_invalid", "activation recovery journal binding is invalid")
    if recovery.get("status") != "switch_complete":
        raise DeploymentError("activation_receipt_invalid", "activation recovery journal is not switch-complete")
    for key in ("path", "sha256", "binding_sha256", "binding"):
        if key not in recovery:
            raise DeploymentError("activation_receipt_invalid", f"activation recovery journal lacks {key}")
    if not isinstance(recovery.get("path"), str) or not Path(recovery["path"]).is_absolute():
        raise DeploymentError("activation_receipt_invalid", "activation recovery journal path is invalid")
    for key in ("sha256", "binding_sha256"):
        if not isinstance(recovery.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", recovery[key]):
            raise DeploymentError("activation_receipt_invalid", "activation recovery journal digest is invalid")
    if recovery.get("binding") != _receipt_binding(payload):
        raise DeploymentError("activation_receipt_invalid", "activation recovery journal identity is not bound")
    expected_recovery_path = path.parent / f"activate-{prepare_operation_id}.recovery.json"
    if Path(recovery["path"]) != expected_recovery_path:
        raise DeploymentError("activation_receipt_invalid", "activation recovery journal path is not deterministic")
    atomicity = payload.get("atomicity")
    if (
        not isinstance(atomicity, dict)
        or atomicity.get("same_filesystem") is not True
        or atomicity.get("switch") != "relative-symlink-os-replace"
        or atomicity.get("journal") != "durable-before-switch"
        or atomicity.get("destination_identity_checked") is not True
        or atomicity.get("release_binding") != RELEASE_BINDING_METHOD
        or atomicity.get("post_switch_verification") != POST_SWITCH_VERIFICATION
        or atomicity.get("post_switch_rollback") != POST_SWITCH_ROLLBACK
        or atomicity.get("finalization") != FINALIZATION_METHOD
    ):
        raise DeploymentError("activation_receipt_invalid", "activation atomicity is not bound")
    if payload.get("claim_ceiling") != ACTIVATION_CLAIM_CEILING:
        raise DeploymentError("activation_receipt_invalid", "activation claim ceiling is invalid")
    if not isinstance(payload.get("effects"), list):
        raise DeploymentError("activation_receipt_invalid", "activation effects must be a list")
    if owner_repo != str(payload.get("owner_repo")) or source_root != Path(source["root"]):
        raise DeploymentError("activation_receipt_invalid", "activation owner/source binding is invalid")
    if destination == release_root:
        raise DeploymentError("activation_receipt_invalid", "activation destination and release root are invalid")


def _validate_rollback_receipt_payload(payload: dict[str, Any], path: Path) -> None:
    _verify_receipt_digest(payload, "rollback receipt")
    if payload.get("schema_version") != ROLLBACK_SCHEMA or payload.get("status") != "rolled_back":
        raise DeploymentError("rollback_receipt_invalid", "rollback receipt is not complete")
    _validate_operation_id(payload.get("operation_id"), "rollback operation_id")
    prepare_operation_id = _validate_operation_id(payload.get("prepare_operation_id"), "rollback prepare_operation_id")
    _timestamp(str(payload.get("rolled_back_at", "")), "rollback rolled_back_at")
    _validate_owner(str(payload.get("owner_repo", "")))
    source = payload.get("source")
    if not isinstance(source, dict) or source.get("dirty") is not False:
        raise DeploymentError("rollback_receipt_invalid", "rollback source is not cleanly bound")
    _absolute_path(str(source.get("root", "")), "rollback source root")
    source_ref = _validate_commit(str(source.get("ref", "")), "rollback source ref")
    source_tree = _validate_commit(str(source.get("tree", "")), "rollback source tree")
    destination = _absolute_path(str(payload.get("destination", "")), "rollback destination")
    release_root = _absolute_path(str(payload.get("release_root", "")), "rollback release root")
    removed_activation = _absolute_path(str(payload.get("removed_activation", "")), "rollback removed activation")
    try:
        removed_activation.relative_to(release_root.resolve(strict=False))
    except ValueError as exc:
        raise DeploymentError("rollback_receipt_invalid", "rollback removed activation is unmanaged") from exc
    release_seal = payload.get("release_seal")
    if not isinstance(release_seal, dict):
        raise DeploymentError("rollback_receipt_invalid", "rollback receipt lacks release seal")
    _verify_recorded_release(removed_activation, source_ref, source_tree, label="removed_activation", seal=release_seal)
    destination_owner = payload.get("destination_owner")
    if destination_owner is not None:
        _validate_destination_owner(destination_owner, "rollback destination owner")
    predecessor = payload.get("restored_predecessor")
    if not isinstance(predecessor, dict):
        raise DeploymentError("rollback_receipt_invalid", "rollback receipt lacks predecessor snapshot")
    _validate_recorded_snapshot(predecessor, release_root, label="restored_predecessor")
    restored_target = payload.get("restored_target")
    if predecessor.get("kind") == "absent":
        if restored_target is not None:
            raise DeploymentError("rollback_receipt_invalid", "absent predecessor must restore a null target")
    elif not isinstance(restored_target, str) or restored_target != predecessor.get("target"):
        raise DeploymentError("rollback_receipt_invalid", "rollback restored target is not predecessor-bound")
    prepare_reference = _validate_receipt_path_reference(payload.get("prepare_receipt"), "rollback prepare receipt")
    expected_prepare_path = path.parent / f"prepare-{prepare_operation_id}.json"
    if Path(prepare_reference["path"]) != expected_prepare_path:
        raise DeploymentError("rollback_receipt_invalid", "rollback prepare receipt path is not deterministic")
    prepare_payload, _ = _load_prepare_receipt(expected_prepare_path)
    if prepare_reference["sha256"] != prepare_payload.get("receipt_digest"):
        raise DeploymentError("rollback_receipt_invalid", "rollback prepare receipt digest does not match")
    _validate_admission_binding(payload.get("admission"), "rollback admission")
    recovery = payload.get("recovery_journal")
    if not isinstance(recovery, dict) or recovery.get("status") != "rollback_switch_complete":
        raise DeploymentError("rollback_receipt_invalid", "rollback recovery journal is not rollback-switch-complete")
    for key in ("path", "sha256", "binding_sha256", "binding"):
        if key not in recovery:
            raise DeploymentError("rollback_receipt_invalid", f"rollback recovery journal lacks {key}")
    if not isinstance(recovery.get("path"), str) or not Path(recovery["path"]).is_absolute():
        raise DeploymentError("rollback_receipt_invalid", "rollback recovery journal path is invalid")
    for key in ("sha256", "binding_sha256"):
        if not isinstance(recovery.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", recovery[key]):
            raise DeploymentError("rollback_receipt_invalid", "rollback recovery journal digest is invalid")
    if recovery.get("binding") != _receipt_binding(payload):
        raise DeploymentError("rollback_receipt_invalid", "rollback recovery journal identity is not bound")
    expected_recovery_path = path.parent / f"activate-{prepare_operation_id}.recovery.json"
    if Path(recovery["path"]) != expected_recovery_path:
        raise DeploymentError("rollback_receipt_invalid", "rollback recovery journal path is not deterministic")
    activation = payload.get("activation_receipt")
    if not isinstance(activation, dict) or not isinstance(activation.get("path"), str):
        raise DeploymentError("rollback_receipt_invalid", "rollback activation reference is invalid")
    if activation.get("status") == "complete":
        if not re.fullmatch(r"[0-9a-f]{64}", str(activation.get("sha256", ""))):
            raise DeploymentError("rollback_receipt_invalid", "rollback activation digest is invalid")
        if not isinstance(activation.get("binding"), dict):
            raise DeploymentError("rollback_receipt_invalid", "rollback activation identity is missing")
    elif activation.get("status") != "not_written":
        raise DeploymentError("rollback_receipt_invalid", "rollback activation reference has invalid status")
    if not Path(activation["path"]).is_absolute():
        raise DeploymentError("rollback_receipt_invalid", "rollback activation reference path is invalid")
    atomicity = payload.get("atomicity")
    if (
        not isinstance(atomicity, dict)
        or atomicity.get("same_filesystem") is not True
        or atomicity.get("switch") != "relative-symlink-os-replace"
        or atomicity.get("destination_identity_checked") is not True
        or atomicity.get("predecessor_identity_checked") is not True
        or atomicity.get("release_binding") != RELEASE_BINDING_METHOD
        or atomicity.get("destination_cas") != DESTINATION_CAS_METHOD
    ):
        raise DeploymentError("rollback_receipt_invalid", "rollback atomicity is not bound")
    if payload.get("claim_ceiling") != "source_activation_rollback_only_no_runtime_claim":
        raise DeploymentError("rollback_receipt_invalid", "rollback claim ceiling is invalid")
    if not isinstance(payload.get("effects"), list):
        raise DeploymentError("rollback_receipt_invalid", "rollback effects must be a list")
    if destination == release_root:
        raise DeploymentError("rollback_receipt_invalid", "rollback destination and release root are invalid")


def _validate_activation_against_journal(
    activation: dict[str, Any],
    activation_path: Path,
    journal: dict[str, Any],
    *,
    require_current: bool,
) -> None:
    if activation.get("operation_id") != journal.get("operation_id"):
        raise DeploymentError("recovery_record_invalid", "activation operation does not match journal")
    if activation.get("prepare_operation_id") != journal.get("prepare_operation_id"):
        raise DeploymentError("recovery_record_invalid", "activation prepare operation does not match journal")
    activation_binding = _receipt_binding(activation)
    journal_binding = _receipt_binding(journal)
    if journal.get("status") in {"rollback_intent", "rollback_switch_complete", "rolled_back"}:
        activation_binding.pop("finalization", None)
    if activation_binding != journal_binding:
        raise DeploymentError("recovery_record_invalid", "activation receipt identity does not match journal")
    if journal.get("status") in {"rollback_intent", "rollback_switch_complete", "rolled_back"}:
        _validate_historical_activation_reference(activation["recovery_journal"], activation, journal)
    else:
        _validate_journal_reference(
            activation["recovery_journal"],
            journal,
            label="activation recovery journal",
            allowed_statuses={"switch_complete"},
        )
    expected_path = _absolute_path(journal["activation_receipt_path"], "recovery activation receipt")
    if activation_path != expected_path:
        raise DeploymentError("recovery_record_invalid", "activation receipt path does not match journal")
    if require_current:
        # The receipt is bound to the historical atomic switch event, not to a
        # later current-path observation.  A superseding writer therefore
        # cannot invalidate the event receipt, and rollback must use the
        # durable destination owner below rather than this finite read.
        _validate_finalization_binding(
            activation["finalization"],
            destination=_absolute_path(journal["destination"], "recovery destination"),
            release_root=_absolute_path(journal["release_root"], "recovery release root"),
            activated_release=_absolute_path(journal["activated_release"], "recovery activated release"),
            release_seal=journal["release_seal"],
            label="activation finalization",
            destination_owner=_validate_destination_owner(
                journal.get("destination_owner"), "recovery destination owner"
            ),
        )
    source = journal["source"]
    _verify_recorded_release(
        _absolute_path(journal["activated_release"], "recovery activated release"),
        source["ref"],
        source["tree"],
        label="activated_release",
        seal=journal["release_seal"],
    )
    _validate_recorded_snapshot(
        journal["predecessor"],
        _absolute_path(journal["release_root"], "recovery release root"),
        label="predecessor",
    )


def _validate_rollback_against_journal(
    rollback: dict[str, Any],
    rollback_path: Path,
    journal: dict[str, Any],
    *,
    require_current: bool,
) -> None:
    if rollback.get("operation_id") != journal.get("operation_id"):
        raise DeploymentError("recovery_record_invalid", "rollback operation does not match journal")
    if rollback.get("prepare_operation_id") != journal.get("prepare_operation_id"):
        raise DeploymentError("recovery_record_invalid", "rollback prepare operation does not match journal")
    if _receipt_binding(rollback) != _receipt_binding(journal):
        raise DeploymentError("recovery_record_invalid", "rollback receipt identity does not match journal")
    _validate_journal_reference(
        rollback["recovery_journal"],
        journal,
        label="rollback recovery journal",
        allowed_statuses={"rollback_switch_complete"},
    )
    expected_path = _absolute_path(journal["rollback_receipt_path"], "recovery rollback receipt")
    if rollback_path != expected_path:
        raise DeploymentError("recovery_record_invalid", "rollback receipt path does not match journal")
    activation = rollback["activation_receipt"]
    activation_path = _absolute_path(activation["path"], "rollback activation receipt")
    if activation.get("status") == "complete":
        activation_payload = _load_activation_receipt(activation_path)
        if activation_payload.get("receipt_digest") != activation.get("sha256"):
            raise DeploymentError("recovery_record_invalid", "rollback activation digest does not match receipt")
        if activation.get("binding") != _receipt_binding(activation_payload):
            raise DeploymentError("recovery_record_invalid", "rollback activation identity does not match receipt")
        _validate_activation_against_journal(activation_payload, activation_path, journal, require_current=False)
    elif activation_path != _absolute_path(journal["activation_receipt_path"], "recovery activation receipt"):
        raise DeploymentError("recovery_record_invalid", "rollback activation absence path is not bound")
    if require_current:
        destination = _absolute_path(journal["destination"], "recovery destination")
        release_root = _absolute_path(journal["release_root"], "recovery release root")
        current = _snapshot_destination(destination, release_root)
        if not _same_snapshot(current, journal["predecessor"]):
            raise DeploymentError("recovery_state_unrecognized", "destination is not the journal's predecessor")


def _validate_recovery_payload(payload: dict[str, Any], path: Path) -> None:
    _verify_receipt_digest(payload, "recovery journal")
    if payload.get("schema_version") != RECOVERY_SCHEMA:
        raise DeploymentError("recovery_record_invalid", "unsupported recovery journal schema")
    status = payload.get("status")
    statuses = {
        "intent_written",
        "switch_complete",
        "finalized",
        "rollback_intent",
        "rollback_switch_complete",
        "rolled_back",
    }
    if status not in statuses:
        raise DeploymentError("recovery_record_invalid", "recovery journal has an invalid status")
    _validate_operation_id(payload.get("operation_id"), "recovery operation_id")
    prepare_operation_id = _validate_operation_id(payload.get("prepare_operation_id"), "recovery prepare_operation_id")
    _timestamp(str(payload.get("created_at", "")), "recovery created_at")
    _timestamp(str(payload.get("updated_at", "")), "recovery updated_at")
    if status in {"switch_complete", "finalized"}:
        _timestamp(str(payload.get("switched_at", "")), "recovery switched_at")
    if status in {"rollback_intent", "rollback_switch_complete", "rolled_back"}:
        _timestamp(str(payload.get("rollback_started_at", "")), "recovery rollback_started_at")
    if status in {"rollback_switch_complete", "rolled_back"}:
        _timestamp(str(payload.get("rollback_switched_at", "")), "recovery rollback_switched_at")
    owner_repo = _validate_owner(str(payload.get("owner_repo", "")))
    source = payload.get("source")
    if not isinstance(source, dict) or source.get("dirty") is not False:
        raise DeploymentError("recovery_record_invalid", "recovery journal source is not cleanly bound")
    source_root = _absolute_path(str(source.get("root", "")), "recovery source root")
    source_ref = _validate_commit(str(source.get("ref", "")), "recovery source ref")
    source_tree = _validate_commit(str(source.get("tree", "")), "recovery source tree")
    destination = _absolute_path(str(payload.get("destination", "")), "recovery destination")
    release_root = _absolute_path(str(payload.get("release_root", "")), "recovery release root")
    activated_release = _absolute_path(str(payload.get("activated_release", "")), "recovery activated release")
    try:
        activated_release.relative_to(release_root.resolve(strict=False))
    except ValueError as exc:
        raise DeploymentError("recovery_record_invalid", "recovery activated release is unmanaged") from exc
    release_seal = payload.get("release_seal")
    if not isinstance(release_seal, dict):
        raise DeploymentError("recovery_record_invalid", "recovery journal lacks release seal")
    _verify_recorded_release(activated_release, source_ref, source_tree, label="activated_release", seal=release_seal)
    destination_owner = None
    if status in {"switch_complete", "finalized"}:
        destination_owner = _validate_destination_owner(
            payload.get("destination_owner"), "recovery destination owner"
        )
    elif payload.get("destination_owner") is not None:
        destination_owner = _validate_destination_owner(
            payload.get("destination_owner"), "recovery destination owner"
        )
    if status in {"rollback_intent", "rollback_switch_complete", "rolled_back"} and "finalization" in payload:
        raise DeploymentError("recovery_record_invalid", "rollback journal retains finalization event")
    if payload.get("finalization") is not None:
        _validate_finalization_binding(
            payload["finalization"],
            destination=destination,
            release_root=release_root,
            activated_release=activated_release,
            release_seal=release_seal,
            label="recovery finalization",
            destination_owner=destination_owner,
        )
    elif status in {"switch_complete", "finalized"}:
        raise DeploymentError("recovery_record_invalid", "finalized journal lacks finalization event")
    predecessor = payload.get("predecessor")
    if not isinstance(predecessor, dict):
        raise DeploymentError("recovery_record_invalid", "recovery journal lacks predecessor snapshot")
    _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
    prepare_receipt = _validate_receipt_path_reference(payload.get("prepare_receipt"), "recovery prepare receipt")
    expected_prepare_path = path.parent / f"prepare-{prepare_operation_id}.json"
    if Path(prepare_receipt["path"]) != expected_prepare_path:
        raise DeploymentError("recovery_record_invalid", "recovery prepare receipt is not deterministic")
    prepare_payload, _ = _load_prepare_receipt(expected_prepare_path)
    if prepare_payload.get("receipt_digest") != prepare_receipt.get("sha256"):
        raise DeploymentError("recovery_record_invalid", "recovery prepare receipt digest does not match")
    if (
        prepare_payload.get("operation_id") != prepare_operation_id
        or prepare_payload.get("owner_repo") != owner_repo
        or prepare_payload.get("source") != source
        or prepare_payload.get("destination") != os.fspath(destination)
        or prepare_payload.get("release_root") != os.fspath(release_root)
        or prepare_payload.get("release_path") != os.fspath(activated_release)
        or prepare_payload.get("release_seal") != release_seal
        or prepare_payload.get("predecessor") != predecessor
        or prepare_payload.get("admission") != payload.get("admission")
    ):
        raise DeploymentError("recovery_record_invalid", "recovery journal is not bound to its prepare receipt")
    admission = _validate_admission_binding(payload.get("admission"), "recovery admission")
    admission_payload, admission_raw = _load_json(Path(admission["path"]), "recovery admission receipt")
    if _digest_bytes(admission_raw) != admission["sha256"]:
        raise DeploymentError("recovery_record_invalid", "recovery admission digest does not match receipt")
    if admission_payload.get("admission_id") != admission["admission_id"]:
        raise DeploymentError("recovery_record_invalid", "recovery admission identity does not match receipt")
    atomicity = payload.get("atomicity")
    if (
        not isinstance(atomicity, dict)
        or atomicity.get("same_filesystem") is not True
        or atomicity.get("switch") != "relative-symlink-os-replace"
        or atomicity.get("journal") != "durable-before-switch"
        or atomicity.get("release_binding") != RELEASE_BINDING_METHOD
        or atomicity.get("finalization") != FINALIZATION_METHOD
    ):
        raise DeploymentError("recovery_record_invalid", "recovery atomicity is not bound")
    if payload.get("claim_ceiling") != RECOVERY_CLAIM_CEILING:
        raise DeploymentError("recovery_record_invalid", "recovery claim ceiling is invalid")
    for key, prefix in (("activation_receipt_path", "activate"), ("rollback_receipt_path", "rollback")):
        if not isinstance(payload.get(key), str) or not Path(payload[key]).is_absolute():
            raise DeploymentError("recovery_record_invalid", f"recovery journal lacks {key}")
        receipt_path = _absolute_path(payload[key], f"recovery {key}")
        expected_path = path.parent / f"{prefix}-{payload['operation_id']}.json"
        if receipt_path != expected_path:
            raise DeploymentError("recovery_record_invalid", f"recovery {key} is not deterministic")
    if path.name != f"activate-{prepare_operation_id}.recovery.json":
        raise DeploymentError("recovery_record_invalid", "recovery journal filename is not deterministic")
    if payload.get("binding_sha256") != _recovery_binding_digest(payload):
        raise DeploymentError("recovery_record_invalid", "recovery journal binding digest is not self-consistent")
    if status in {"switch_complete", "finalized", "rollback_intent", "rollback_switch_complete", "rolled_back"}:
        state_digest = payload.get("switch_complete_sha256")
        if not isinstance(state_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", state_digest):
            raise DeploymentError("recovery_record_invalid", "recovery journal lacks switch state digest")
        if state_digest != _recovery_state_digest(payload, "switch_complete"):
            raise DeploymentError("recovery_record_invalid", "recovery switch state digest is invalid")
    if status in {"rollback_switch_complete", "rolled_back"}:
        rollback_state_digest = payload.get("rollback_switch_complete_sha256")
        if not isinstance(rollback_state_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", rollback_state_digest):
            raise DeploymentError("recovery_record_invalid", "recovery journal lacks rollback state digest")
        if rollback_state_digest != _recovery_state_digest(payload, "rollback_switch_complete"):
            raise DeploymentError("recovery_record_invalid", "recovery rollback state digest is invalid")
    activation_keys = "activation_receipt" in payload
    rollback_keys = "rollback_receipt" in payload
    if status in {"intent_written", "switch_complete", "rollback_intent", "rollback_switch_complete"} and (activation_keys or rollback_keys):
        raise DeploymentError("recovery_record_invalid", f"{status} journal cannot contain completed receipt references")
    activation_path = _absolute_path(payload["activation_receipt_path"], "recovery activation receipt")
    rollback_path = _absolute_path(payload["rollback_receipt_path"], "recovery rollback receipt")
    if status == "finalized":
        if not activation_keys or rollback_keys:
            raise DeploymentError("recovery_record_invalid", "finalized journal has an incompatible receipt state")
        activation = _load_activation_receipt(activation_path)
        _validate_completed_receipt_reference(payload["activation_receipt"], activation_path, activation, label="activation receipt")
        _validate_activation_against_journal(activation, activation_path, payload, require_current=True)
    if status == "rolled_back":
        if not rollback_keys or activation_keys:
            raise DeploymentError("recovery_record_invalid", "rolled-back journal has an incompatible receipt state")
        rollback_payload = _load_rollback_receipt(rollback_path)
        _validate_completed_receipt_reference(payload["rollback_receipt"], rollback_path, rollback_payload, label="rollback receipt")
        _validate_rollback_against_journal(rollback_payload, rollback_path, payload, require_current=True)


def _load_recovery_journal(path: Path) -> dict[str, Any]:
    payload, _ = _load_json(path, "recovery journal")
    _validate_recovery_payload(payload, path)
    return payload


def _remove_release(release_path: Path) -> None:
    seal_path = _release_seal_path(release_path)
    try:
        seal_path.unlink(missing_ok=True)
    except OSError:
        pass
    if release_path.exists() or release_path.is_symlink():
        try:
            for path in _release_entries(release_path):
                mode = stat.S_IMODE(os.lstat(path).st_mode)
                os.chmod(path, mode | 0o222)
            if release_path.exists() and not release_path.is_symlink():
                mode = stat.S_IMODE(os.lstat(release_path).st_mode)
                os.chmod(release_path, mode | 0o222)
            shutil.rmtree(release_path, ignore_errors=True)
        except OSError:
            pass


def _clone_release(
    source_root: Path,
    release_root: Path,
    owner_repo: str,
    source_ref: str,
    source_tree: str,
    operation_id: str,
) -> tuple[Path, dict[str, str]]:
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
        seal = _seal_release(final, source_ref, source_tree)
    except DeploymentError:
        if staging.exists() or os.path.islink(staging):
            shutil.rmtree(staging, ignore_errors=True)
        _remove_release(final)
        raise
    except OSError as exc:
        if staging.exists() or os.path.islink(staging):
            shutil.rmtree(staging, ignore_errors=True)
        _remove_release(final)
        raise DeploymentError("release_stage_failed", f"{release_root}: {exc}") from exc
    return final, seal


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
                "release_binding": RELEASE_BINDING_METHOD,
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
        release_path, release_seal = _clone_release(
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
            "release_seal": release_seal,
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
                "release_binding": RELEASE_BINDING_METHOD,
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
    release_seal = payload.get("release_seal")
    if not isinstance(release_seal, dict):
        raise DeploymentError("prepare_receipt_invalid", "prepare receipt lacks release seal")
    source = payload["source"]
    _verify_recorded_release(
        release_path,
        str(source["ref"]),
        str(source["tree"]),
        label="prepared_release",
        seal=release_seal,
    )
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
        or atomicity.get("release_binding") != RELEASE_BINDING_METHOD
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


def _destination_identity(destination: Path) -> dict[str, Any]:
    if not os.path.lexists(destination):
        raise DeploymentError("destination_missing", f"destination is missing: {destination}")
    if not destination.is_symlink():
        raise DeploymentError("destination_not_atomic_switchable", f"destination is not a symlink: {destination}")
    try:
        value = os.lstat(destination)
        link_text = os.readlink(destination)
    except OSError as exc:
        raise DeploymentError("destination_unreadable", f"cannot inspect destination: {destination}") from exc
    return {
        "device": int(value.st_dev),
        "inode": int(value.st_ino),
        "mode": int(value.st_mode),
        "link_text": link_text,
        "target": os.fspath((destination.parent / link_text).resolve(strict=False)),
    }


def _destination_link_target(destination: Path) -> Path:
    return Path(_destination_identity(destination)["target"])


def _destination_identity_matches(path: Path, expected: dict[str, Any]) -> bool:
    try:
        actual = _destination_identity(path)
    except DeploymentError:
        return False
    return all(actual.get(key) == expected.get(key) for key in ("device", "inode", "mode", "link_text", "target"))


def _temporary_path(destination: Path, suffix: str) -> Path:
    return destination.parent / f".{destination.name}.{uuid.uuid4().hex}.{suffix}"


def _verify_post_switch_state(
    *,
    destination: Path,
    release_root: Path,
    release_path: Path,
    source_ref: str,
    source_tree: str,
    release_seal: dict[str, Any],
) -> None:
    _verify_recorded_release(
        release_path,
        source_ref,
        source_tree,
        label="activated_release",
        seal=release_seal,
    )
    current = _snapshot_destination(destination, release_root)
    expected = {
        "kind": "symlink",
        "target": os.fspath(release_path.resolve(strict=False)),
        "source_ref": source_ref,
        "source_tree": source_tree,
        "release_seal": release_seal,
    }
    if not _same_snapshot(current, expected):
        raise DeploymentError(
            "post_switch_state_invalid",
            "destination does not point at the verified sealed release after switch",
        )


def _finalization_event(
    *,
    destination_owner: dict[str, Any],
    release_path: Path,
    release_seal: dict[str, Any],
) -> dict[str, Any]:
    """Bind receipt eligibility to the successful destination switch event.

    ``destination_owner`` is captured from the temporary symlink before the
    atomic ``os.replace``.  Rename preserves that inode and link text, so the
    record describes the effect performed by this route rather than a later
    read of a mutable destination path.
    """

    owner = _validate_destination_owner(destination_owner, "finalization destination owner")
    return {
        "method": FINALIZATION_METHOD,
        "status": "committed",
        "committed_at": _iso(_utc_now()),
        "effect": "relative-symlink-os-replace",
        "current_destination_claim": False,
        "destination": owner,
        "release": {
            "path": os.fspath(release_path),
            "root_device": release_seal["root_device"],
            "root_inode": release_seal["root_inode"],
            "manifest_sha256": release_seal["manifest_sha256"],
            "seal_sha256": release_seal["sha256"],
        },
    }


def _verify_finalization_integrity(
    *,
    destination: Path,
    release_root: Path,
    release_path: Path,
    source_ref: str,
    source_tree: str,
    release_seal: dict[str, Any],
    destination_owner: dict[str, Any],
) -> None:
    """Reject known drift before publishing the event-bound receipt.

    This is a defensive integrity fence for release/seal drift.  It is not
    the ownership proof: the receipt is already bound to the exact atomic
    switch inode captured before ``os.replace``.  A writer after this fence is
    therefore represented as a later writer, not misclassified as this route's
    destination owner.
    """

    _verify_post_switch_state(
        destination=destination,
        release_root=release_root,
        release_path=release_path,
        source_ref=source_ref,
        source_tree=source_tree,
        release_seal=release_seal,
    )
    current = _snapshot_destination(destination, release_root)
    expected = {
        "kind": "symlink",
        "target": os.fspath(release_path.resolve(strict=False)),
        "source_ref": source_ref,
        "source_tree": source_tree,
        "release_seal": release_seal,
    }
    if not _same_snapshot(current, expected) or not _destination_identity_matches(destination, destination_owner):
        raise DeploymentError(
            "finalization_state_invalid",
            "destination or sealed release drifted before event-bound receipt publication",
        )


def _rollback_after_post_switch_failure(
    *,
    recovery_path: Path,
    journal: dict[str, Any],
    destination: Path,
    release_root: Path,
    release_path: Path,
    predecessor: dict[str, Any],
    failure: DeploymentError,
) -> DeploymentError:
    """Durably remove an unreceipted target after post-switch validation fails."""

    try:
        expected_owner = _validate_destination_owner(
            journal.get("destination_owner"), "rollback destination owner"
        )
        journal = _write_json(recovery_path, _rollback_intent_payload(journal))
        if not _destination_identity_matches(destination, expected_owner):
            raise DeploymentError(
                "concurrent_deployment",
                "destination owner is not the durable activation owner before post-switch rollback",
            )
        _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
        _restore_predecessor(
            destination,
            predecessor,
            release_root,
            expected_owner=expected_owner,
        )
        journal = _write_json(recovery_path, _rollback_switch_complete_payload(journal))
        restored = _snapshot_destination(destination, release_root)
        if not _same_snapshot(restored, predecessor):
            raise DeploymentError(
                "post_switch_rollback_failed",
                "destination does not match its recorded predecessor after rollback",
            )
    except DeploymentError as rollback_error:
        return _recovery_required(
            recovery_path,
            DeploymentError(
                "post_switch_rollback_failed",
                f"{failure.detail}; rollback failed: {rollback_error.detail}",
            ),
        )
    except OSError as exc:
        return _recovery_required(
            recovery_path,
            DeploymentError("post_switch_rollback_failed", f"{failure.detail}; rollback failed: {exc}"),
        )
    return _recovery_required(recovery_path, failure)


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
    payload = {
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
        "release_seal": prepare_payload["release_seal"],
        "predecessor": predecessor,
        "admission": admission,
        "activation_receipt_path": os.fspath(activation_receipt_path),
        "rollback_receipt_path": os.fspath(rollback_receipt_path),
        "atomicity": {
            "same_filesystem": True,
            "switch": "relative-symlink-os-replace",
            "journal": "durable-before-switch",
            "release_binding": RELEASE_BINDING_METHOD,
            "finalization": FINALIZATION_METHOD,
        },
        "claim_ceiling": RECOVERY_CLAIM_CEILING,
    }
    payload["binding_sha256"] = _recovery_binding_digest(payload)
    return payload


def _switch_complete_payload(journal: dict[str, Any]) -> dict[str, Any]:
    payload = dict(journal)
    payload.pop("_recovery_path", None)
    destination_owner = _validate_destination_owner(
        payload.get("destination_owner"), "switch-complete destination owner"
    )
    finalization = payload.get("finalization")
    _validate_finalization(finalization, "switch-complete finalization")
    if finalization["destination"] != destination_owner:
        raise DeploymentError("recovery_record_invalid", "switch-complete finalization owner is not bound")
    payload["status"] = "switch_complete"
    payload["updated_at"] = _iso(_utc_now())
    payload["switched_at"] = payload.get("switched_at") or _iso(_utc_now())
    payload["binding_sha256"] = _recovery_binding_digest(payload)
    payload["switch_complete_sha256"] = _recovery_state_digest(payload, "switch_complete")
    return payload


def _finalization_journal_payload(
    journal: dict[str, Any],
    finalization: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(journal)
    payload.pop("_recovery_path", None)
    _validate_destination_owner(payload.get("destination_owner"), "finalization journal destination owner")
    _validate_finalization(finalization, "finalization journal event")
    payload["finalization"] = finalization
    return _switch_complete_payload(payload)


def _rollback_intent_payload(journal: dict[str, Any]) -> dict[str, Any]:
    payload = dict(journal)
    payload.pop("_recovery_path", None)
    payload.pop("activation_receipt", None)
    payload.pop("rollback_receipt", None)
    payload.pop("finalization", None)
    payload["status"] = "rollback_intent"
    payload["updated_at"] = _iso(_utc_now())
    payload["rollback_started_at"] = payload.get("rollback_started_at") or _iso(_utc_now())
    payload["binding_sha256"] = _recovery_binding_digest(payload)
    payload["switch_complete_sha256"] = _recovery_state_digest(payload, "switch_complete")
    return payload


def _rollback_switch_complete_payload(journal: dict[str, Any]) -> dict[str, Any]:
    payload = dict(journal)
    payload.pop("_recovery_path", None)
    payload.pop("activation_receipt", None)
    payload.pop("rollback_receipt", None)
    payload.pop("finalization", None)
    payload["status"] = "rollback_switch_complete"
    payload["updated_at"] = _iso(_utc_now())
    payload["rollback_started_at"] = payload.get("rollback_started_at") or _iso(_utc_now())
    payload["rollback_switched_at"] = payload.get("rollback_switched_at") or _iso(_utc_now())
    payload["binding_sha256"] = _recovery_binding_digest(payload)
    payload["switch_complete_sha256"] = _recovery_state_digest(payload, "switch_complete")
    payload["rollback_switch_complete_sha256"] = _recovery_state_digest(payload, "rollback_switch_complete")
    return payload


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
    recovery_payload: dict[str, Any],
    finalization: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": ACTIVATE_SCHEMA,
        "status": "activated",
        "operation_id": operation_id,
        "prepare_operation_id": prepare_payload["operation_id"],
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
        "release_seal": prepare_payload["release_seal"],
        "destination_owner": recovery_payload["destination_owner"],
        "predecessor": predecessor,
        "admission": admission,
        "finalization": finalization,
        "recovery_journal": _recovery_journal_reference(
            recovery_path,
            recovery_payload,
            status="switch_complete",
        ),
        "atomicity": {
            "same_filesystem": True,
            "switch": "relative-symlink-os-replace",
            "destination_identity_checked": True,
            "journal": "durable-before-switch",
            "release_binding": RELEASE_BINDING_METHOD,
            "post_switch_verification": POST_SWITCH_VERIFICATION,
            "post_switch_rollback": POST_SWITCH_ROLLBACK,
            "finalization": FINALIZATION_METHOD,
        },
        "dependency_posture": "source_only_no_install",
        "effects": ["destination_symlink_replaced"],
        "claim_ceiling": ACTIVATION_CLAIM_CEILING,
    }


def _finalize_activation(
    *,
    journal: dict[str, Any],
    recovery_path: Path,
    activation_path: Path,
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
) -> dict[str, Any]:
    """Materialize one shared receipt from an event-bound switch journal."""

    if journal.get("status") not in {"switch_complete", "finalized"}:
        raise _recovery_required(
            recovery_path,
            DeploymentError(
                "switch_owner_missing",
                "finalization cannot infer an atomic switch owner from intent_written state",
            ),
        )
    destination_owner = _validate_destination_owner(
        journal.get("destination_owner"), "finalization destination owner"
    )
    finalization = journal.get("finalization")
    _validate_finalization_binding(
        finalization,
        destination=destination,
        release_root=release_root,
        activated_release=release_path,
        release_seal=prepare_payload["release_seal"],
        label="finalization event",
        destination_owner=destination_owner,
    )
    try:
        _verify_finalization_integrity(
            destination=destination,
            release_root=release_root,
            release_path=release_path,
            source_ref=source_ref,
            source_tree=source_tree,
            release_seal=prepare_payload["release_seal"],
            destination_owner=destination_owner,
        )
    except DeploymentError as failure:
        if not os.path.lexists(destination):
            raise _recovery_required(recovery_path, failure) from failure
        raise _rollback_after_post_switch_failure(
            recovery_path=recovery_path,
            journal=journal,
            destination=destination,
            release_root=release_root,
            release_path=release_path,
            predecessor=predecessor,
            failure=failure,
        ) from failure

    journal["_recovery_path"] = os.fspath(recovery_path)
    if os.path.lexists(activation_path):
        try:
            activation = _load_activation_receipt(activation_path)
            _validate_activation_against_journal(activation, activation_path, journal, require_current=True)
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
    else:
        payload_out = _activation_payload(
            operation_id=journal["operation_id"],
            prepare_payload=prepare_payload,
            prepare_path=prepare_path,
            owner_repo=owner_repo,
            source_root=source_root,
            source_ref=source_ref,
            source_tree=source_tree,
            destination=destination,
            release_root=release_root,
            release_path=release_path,
            predecessor=predecessor,
            admission=admission,
            recovery_path=recovery_path,
            recovery_payload=journal,
            finalization=finalization,
        )
        try:
            activation = _write_json(activation_path, payload_out)
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc

    final_journal = {key: value for key, value in journal.items() if key != "_recovery_path"}
    final_journal.update(
        {
            "status": "finalized",
            "updated_at": _iso(_utc_now()),
            "activation_receipt": _completed_receipt_reference(activation_path, activation),
        }
    )
    try:
        _write_json(recovery_path, final_journal)
    except DeploymentError as exc:
        raise _recovery_required(recovery_path, exc) from exc
    return {"receipt_path": os.fspath(activation_path), **activation}


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
        current = _snapshot_destination(destination, release_root, strict_seal=False)
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
        _verify_recorded_release(
            release_path,
            source_ref,
            source_tree,
            label="activated_release",
            seal=payload["release_seal"],
        )
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
        temporary: Path | None = None
        try:
            pre_switch_current = _snapshot_destination(destination, release_root, strict_seal=False)
            if not _same_snapshot(pre_switch_current, expected):
                raise DeploymentError("concurrent_deployment", "destination changed immediately before switch")
            _verify_recorded_release(
                release_path,
                source_ref,
                source_tree,
                label="activated_release",
                seal=payload["release_seal"],
            )
            target_link = os.path.relpath(release_path, destination.parent)
            temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.switch"
            os.symlink(target_link, temporary)
            destination_owner = _destination_identity(temporary)
            os.replace(temporary, destination)
            _fsync_directory(destination.parent)
            journal["destination_owner"] = destination_owner
            journal["finalization"] = _finalization_event(
                destination_owner=destination_owner,
                release_path=release_path,
                release_seal=payload["release_seal"],
            )
            journal = _write_json(
                recovery_path,
                _finalization_journal_payload(journal, journal["finalization"]),
            )
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
        except OSError as exc:
            try:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise _recovery_required(
                recovery_path,
                DeploymentError("atomic_switch_failed", f"{destination}: {exc}"),
            ) from exc
        receipt_path = prepare_path.parent / f"activate-{activation_operation_id}.json"
        return _finalize_activation(
            journal=journal,
            recovery_path=recovery_path,
            activation_path=receipt_path,
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
        )


def _load_activation_receipt(path: Path) -> dict[str, Any]:
    payload, _ = _load_json(path, "activation receipt")
    _validate_activation_receipt_payload(payload, path)
    return payload


def _load_rollback_receipt(path: Path) -> dict[str, Any]:
    payload, _ = _load_json(path, "rollback receipt")
    _validate_rollback_receipt_payload(payload, path)
    return payload


def _restore_predecessor(
    destination: Path,
    predecessor: dict[str, Any],
    release_root: Path,
    *,
    expected_owner: dict[str, Any] | None = None,
) -> str | None:
    """Restore only the destination identity observed by this rollback.

    The destination is first moved to a unique displaced path without
    replacement.  Its inode/link identity is compared there, and a
    predecessor is installed only with RENAME_NOREPLACE.  A changed writer is
    therefore preserved rather than overwritten or unlinked.
    """

    expected_owner = expected_owner or _destination_identity(destination)
    target = _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
    displaced = _temporary_path(destination, "rollback-displaced")
    predecessor_temp: Path | None = None
    keep_displaced = True
    try:
        if target is not None:
            predecessor_temp = _temporary_path(destination, "rollback-predecessor")
            os.symlink(os.path.relpath(target, destination.parent), predecessor_temp)
        try:
            _rename_noreplace(destination, displaced)
        except FileNotFoundError as exc:
            raise DeploymentError("destination_missing", f"destination disappeared before rollback: {destination}") from exc
        except OSError as exc:
            raise DeploymentError("rollback_switch_failed", f"{destination}: {exc}") from exc

        if not _destination_identity_matches(displaced, expected_owner):
            try:
                _rename_noreplace(displaced, destination)
                keep_displaced = False
            except FileExistsError:
                # A newer writer owns the destination.  Leave both that path
                # and the displaced writer untouched for explicit recovery.
                pass
            except OSError as exc:
                raise DeploymentError("rollback_switch_failed", f"cannot restore displaced destination: {exc}") from exc
            raise DeploymentError(
                "concurrent_deployment",
                "destination identity changed before rollback compare-and-swap",
                {"displaced_path": os.fspath(displaced)} if keep_displaced else {},
            )

        if target is None:
            if os.path.lexists(destination):
                os.unlink(displaced)
                keep_displaced = False
                raise DeploymentError(
                    "concurrent_deployment",
                    "destination was replaced before the absent predecessor could be committed",
                )
            os.unlink(displaced)
            keep_displaced = False
            _fsync_directory(destination.parent)
            if os.path.lexists(destination):
                raise DeploymentError(
                    "concurrent_deployment",
                    "destination changed after the absent predecessor compare-and-swap",
                )
            return None

        if os.path.lexists(destination):
            os.unlink(predecessor_temp)  # type: ignore[arg-type]
            predecessor_temp = None
            os.unlink(displaced)
            keep_displaced = False
            raise DeploymentError(
                "concurrent_deployment",
                "destination was replaced before predecessor compare-and-swap",
            )
        try:
            _rename_noreplace(predecessor_temp, destination)  # type: ignore[arg-type]
        except FileExistsError as exc:
            raise DeploymentError(
                "concurrent_deployment",
                "destination was replaced during predecessor compare-and-swap",
            ) from exc
        except OSError as exc:
            raise DeploymentError("rollback_switch_failed", f"{destination}: {exc}") from exc
        predecessor_temp = None
        _fsync_directory(destination.parent)
        try:
            restored = _snapshot_destination(destination, release_root)
        except DeploymentError as exc:
            raise DeploymentError(
                "concurrent_deployment",
                f"destination changed after predecessor compare-and-swap: {exc.detail}",
            ) from exc
        if not _same_snapshot(restored, predecessor):
            raise DeploymentError(
                "concurrent_deployment",
                "destination does not match the predecessor after compare-and-swap",
            )
        os.unlink(displaced)
        keep_displaced = False
        _fsync_directory(destination.parent)
        return os.fspath(target)
    except DeploymentError:
        raise
    except OSError as exc:
        raise DeploymentError("rollback_switch_failed", f"{destination}: {exc}") from exc
    finally:
        if predecessor_temp is not None:
            try:
                predecessor_temp.unlink(missing_ok=True)
            except OSError:
                pass
        if not keep_displaced:
            try:
                displaced.unlink(missing_ok=True)
            except OSError:
                pass


def _rollback_payload(
    *,
    journal: dict[str, Any],
    recovery_path: Path,
    activation_reference: dict[str, Any],
    restored_target: str | None,
) -> dict[str, Any]:
    predecessor = journal["predecessor"]
    return {
        "schema_version": ROLLBACK_SCHEMA,
        "status": "rolled_back",
        "operation_id": journal["operation_id"],
        "prepare_operation_id": journal["prepare_operation_id"],
        "rolled_back_at": _iso(_utc_now()),
        "owner_repo": journal["owner_repo"],
        "activation_receipt": activation_reference,
        "prepare_receipt": journal["prepare_receipt"],
        "source": journal["source"],
        "destination": journal["destination"],
        "release_root": journal["release_root"],
        "removed_activation": journal["activated_release"],
        "release_seal": journal["release_seal"],
        "destination_owner": journal.get("destination_owner"),
        "restored_predecessor": predecessor,
        "restored_target": restored_target,
        "admission": journal["admission"],
        "recovery_journal": _recovery_journal_reference(
            recovery_path,
            journal,
            status="rollback_switch_complete",
        ),
        "atomicity": {
            "same_filesystem": True,
            "switch": "relative-symlink-os-replace",
            "destination_identity_checked": True,
            "predecessor_identity_checked": True,
            "release_binding": RELEASE_BINDING_METHOD,
            "destination_cas": DESTINATION_CAS_METHOD,
        },
        "dependency_posture": "source_only_no_install",
        "effects": ["destination_symlink_restored" if restored_target else "destination_removed"],
        "claim_ceiling": "source_activation_rollback_only_no_runtime_claim",
    }


def rollback(args: argparse.Namespace) -> dict[str, Any]:
    activation_path = _existing_path(args.activation_receipt, "activation receipt")
    activation = _load_activation_receipt(activation_path)
    recovery_reference = activation.get("recovery_journal")
    if not isinstance(recovery_reference, dict) or not isinstance(recovery_reference.get("path"), str):
        raise DeploymentError("activation_receipt_invalid", "activation receipt lacks recovery journal path")
    recovery_path = _absolute_path(recovery_reference["path"], "activation recovery journal")
    journal = _load_recovery_journal(recovery_path)
    journal["_recovery_path"] = os.fspath(recovery_path)
    if journal.get("status") in {"rollback_intent", "rollback_switch_complete", "rolled_back"}:
        raise DeploymentError("recovery_pending", "activation journal is already in rollback recovery")
    _validate_activation_against_journal(activation, activation_path, journal, require_current=False)
    owner_repo = _validate_owner(str(journal["owner_repo"]))
    release_root = _absolute_path(journal["release_root"], "activation release root")
    destination = _absolute_path(journal["destination"], "activation destination")
    lock_path = _lock_path(release_root, owner_repo)
    with _deployment_lock(lock_path):
        fresh = _load_recovery_journal(recovery_path)
        fresh["_recovery_path"] = os.fspath(recovery_path)
        if fresh.get("status") in {"rollback_intent", "rollback_switch_complete", "rolled_back"}:
            raise DeploymentError("recovery_pending", "activation journal is already in rollback recovery")
        fresh_activation = _load_activation_receipt(activation_path)
        _validate_activation_against_journal(fresh_activation, activation_path, fresh, require_current=True)
        intent = _rollback_intent_payload(fresh)
        try:
            journal = _write_json(recovery_path, intent)
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
        journal["_recovery_path"] = os.fspath(recovery_path)
        try:
            expected_owner = _validate_destination_owner(
                journal.get("destination_owner"), "rollback destination owner"
            )
            current = _snapshot_destination(destination, release_root)
            if (
                not _same_snapshot(current, _recovery_target_snapshot(journal))
                or not _destination_identity_matches(destination, expected_owner)
            ):
                raise DeploymentError(
                    "concurrent_deployment",
                    "destination is not the durable activation owner before rollback switch",
                )
            source = journal["source"]
            _verify_recorded_release(
                _absolute_path(journal["activated_release"], "activated release"),
                source["ref"],
                source["tree"],
                label="activated_release",
                seal=journal["release_seal"],
            )
            _validate_recorded_snapshot(journal["predecessor"], release_root, label="predecessor")
            restored = _restore_predecessor(
                destination,
                journal["predecessor"],
                release_root,
                expected_owner=expected_owner,
            )
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
        except OSError as exc:
            raise _recovery_required(
                recovery_path,
                DeploymentError("rollback_switch_failed", f"{destination}: {exc}"),
            ) from exc
        try:
            journal = _write_json(recovery_path, _rollback_switch_complete_payload(journal))
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
        journal["_recovery_path"] = os.fspath(recovery_path)
        activation_reference = _completed_receipt_reference(activation_path, fresh_activation)
        receipt_dir = _absolute_path(args.receipt_dir, "receipt_dir") if args.receipt_dir else activation_path.parent
        receipt_path = receipt_dir / f"rollback-{journal['operation_id']}.json"
        rollback_payload = _rollback_payload(
            journal=journal,
            recovery_path=recovery_path,
            activation_reference=activation_reference,
            restored_target=restored,
        )
        try:
            receipt = _write_json(receipt_path, rollback_payload)
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
        final_journal = {key: value for key, value in journal.items() if key != "_recovery_path"}
        final_journal.pop("activation_receipt", None)
        final_journal.update(
            {
                "status": "rolled_back",
                "updated_at": _iso(_utc_now()),
                "rollback_receipt": _completed_receipt_reference(receipt_path, receipt),
            }
        )
        try:
            _write_json(recovery_path, final_journal)
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
        return {"receipt_path": os.fspath(receipt_path), **receipt}


def _recovery_target_snapshot(journal: dict[str, Any]) -> dict[str, Any]:
    source = journal["source"]
    return {
        "kind": "symlink",
        "target": journal["activated_release"],
        "source_ref": source["ref"],
        "source_tree": source["tree"],
        "release_seal": journal["release_seal"],
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
            "release_seal": journal["release_seal"],
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
        recovery_payload=journal,
        finalization=journal["finalization"],
    )


def _recover_finalize(recovery_path: Path) -> dict[str, Any]:
    journal = _load_recovery_journal(recovery_path)
    journal["_recovery_path"] = os.fspath(recovery_path)
    if journal.get("status") in {"rollback_intent", "rollback_switch_complete", "rolled_back"}:
        raise DeploymentError("recovery_already_rolled_back", "a rollback journal cannot be finalized")
    owner_repo, destination, release_root, activated_release, _, activation_path = _recovery_paths(journal)
    lock_path = _lock_path(release_root, owner_repo)
    with _deployment_lock(lock_path):
        fresh = _load_recovery_journal(recovery_path)
        fresh["_recovery_path"] = os.fspath(recovery_path)
        if fresh.get("status") in {"rollback_intent", "rollback_switch_complete", "rolled_back"}:
            raise DeploymentError("recovery_already_rolled_back", "a rollback journal cannot be finalized")
        if fresh.get("status") == "finalized":
            activation = _load_activation_receipt(activation_path)
            _validate_activation_against_journal(activation, activation_path, fresh, require_current=True)
            return {"receipt_path": os.fspath(activation_path), **activation}
        if fresh.get("status") == "intent_written":
            raise _recovery_required(
                recovery_path,
                DeploymentError(
                    "switch_owner_missing",
                    "recovery finalize cannot infer which destination inode was installed from intent_written state",
                ),
            )
        source = fresh["source"]
        return _finalize_activation(
            journal=fresh,
            recovery_path=recovery_path,
            activation_path=activation_path,
            prepare_payload={
                "operation_id": fresh["prepare_operation_id"],
                "receipt_digest": fresh["prepare_receipt"]["sha256"],
                "release_seal": fresh["release_seal"],
            },
            prepare_path=Path(fresh["prepare_receipt"]["path"]),
            owner_repo=owner_repo,
            source_root=Path(source["root"]),
            source_ref=source["ref"],
            source_tree=source["tree"],
            destination=destination,
            release_root=release_root,
            release_path=activated_release,
            predecessor=fresh["predecessor"],
            admission=fresh["admission"],
        )


def _recovery_activation_reference(journal: dict[str, Any], activation_path: Path) -> dict[str, Any]:
    if os.path.lexists(activation_path):
        activation = _load_activation_receipt(activation_path)
        _validate_activation_against_journal(activation, activation_path, journal, require_current=False)
        return _completed_receipt_reference(activation_path, activation)
    return {"path": os.fspath(activation_path), "status": "not_written"}


def _recover_rollback(recovery_path: Path) -> dict[str, Any]:
    journal = _load_recovery_journal(recovery_path)
    journal["_recovery_path"] = os.fspath(recovery_path)
    owner_repo, destination, release_root, activated_release, _, activation_path = _recovery_paths(journal)
    rollback_path = _absolute_path(journal["rollback_receipt_path"], "recovery rollback receipt")
    if journal.get("status") == "rolled_back":
        rollback_receipt = _load_rollback_receipt(rollback_path)
        return {"receipt_path": os.fspath(rollback_path), **rollback_receipt}
    lock_path = _lock_path(release_root, owner_repo)
    with _deployment_lock(lock_path):
        fresh = _load_recovery_journal(recovery_path)
        fresh["_recovery_path"] = os.fspath(recovery_path)
        if fresh.get("status") == "rolled_back":
            rollback_receipt = _load_rollback_receipt(rollback_path)
            return {"receipt_path": os.fspath(rollback_path), **rollback_receipt}
        if fresh.get("status") not in {
            "intent_written",
            "switch_complete",
            "finalized",
            "rollback_intent",
            "rollback_switch_complete",
        }:
            raise DeploymentError("recovery_record_invalid", "recovery journal cannot be rolled back")
        current = _snapshot_destination(destination, release_root)
        expected_target = _recovery_target_snapshot(fresh)
        predecessor = fresh["predecessor"]
        destination_owner = fresh.get("destination_owner")
        owner_matches = (
            isinstance(destination_owner, dict)
            and _destination_identity_matches(destination, destination_owner)
        )
        target_current = (
            _same_snapshot(current, expected_target)
            and current.get("release_seal") == fresh.get("release_seal")
            and owner_matches
        )
        predecessor_current = _same_snapshot(current, predecessor)
        if not target_current and not predecessor_current:
            raise _recovery_required(
                recovery_path,
                DeploymentError(
                    "recovery_state_unrecognized",
                    "destination is neither the durable activated owner nor its predecessor",
                ),
            )
        if fresh.get("status") == "rollback_switch_complete" and target_current:
            raise DeploymentError(
                "recovery_state_unrecognized",
                "rollback-switch-complete journal points at the activated release",
            )
        if fresh.get("status") not in {"rollback_intent", "rollback_switch_complete"}:
            try:
                fresh = _write_json(recovery_path, _rollback_intent_payload(fresh))
            except DeploymentError as exc:
                raise _recovery_required(recovery_path, exc) from exc
            fresh["_recovery_path"] = os.fspath(recovery_path)
        restored: str | None
        if target_current:
            source = fresh["source"]
            try:
                expected_owner = _validate_destination_owner(
                    fresh.get("destination_owner"), "rollback destination owner"
                )
                _verify_recorded_release(
                    activated_release,
                    source["ref"],
                    source["tree"],
                    label="activated_release",
                    seal=fresh["release_seal"],
                )
                _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
                restored = _restore_predecessor(
                    destination,
                    predecessor,
                    release_root,
                    expected_owner=expected_owner,
                )
            except DeploymentError as exc:
                raise _recovery_required(recovery_path, exc) from exc
            except OSError as exc:
                raise _recovery_required(
                    recovery_path,
                    DeploymentError("rollback_switch_failed", f"{destination}: {exc}"),
                ) from exc
        else:
            _validate_recorded_snapshot(predecessor, release_root, label="predecessor")
            restored = predecessor.get("target") if predecessor.get("kind") == "symlink" else None
        if fresh.get("status") != "rollback_switch_complete":
            try:
                fresh = _write_json(recovery_path, _rollback_switch_complete_payload(fresh))
            except DeploymentError as exc:
                raise _recovery_required(recovery_path, exc) from exc
            fresh["_recovery_path"] = os.fspath(recovery_path)
        activation_reference = _recovery_activation_reference(fresh, activation_path)
        rollback_payload = _rollback_payload(
            journal=fresh,
            recovery_path=recovery_path,
            activation_reference=activation_reference,
            restored_target=restored,
        )
        try:
            receipt = _write_json(rollback_path, rollback_payload)
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
        final_journal = {key: value for key, value in fresh.items() if key != "_recovery_path"}
        final_journal.pop("activation_receipt", None)
        final_journal.update(
            {
                "status": "rolled_back",
                "updated_at": _iso(_utc_now()),
                "rollback_receipt": _completed_receipt_reference(rollback_path, receipt),
            }
        )
        try:
            _write_json(recovery_path, final_journal)
        except DeploymentError as exc:
            raise _recovery_required(recovery_path, exc) from exc
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
