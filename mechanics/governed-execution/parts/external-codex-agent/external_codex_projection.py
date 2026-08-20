#!/usr/bin/env python3
"""Materialize and compare one runtime-owned external-actor workspace.

The owner checkout remains an acceptance surface.  The actor receives a fresh
filesystem projection and a private Git body containing only the exact objects,
index state, and ignore facts needed to reproduce the admitted baseline.  No
source Git directory, remote, alternates file, or source coordinate is retained.
"""

from __future__ import annotations

import hashlib
import json
import ctypes
import errno
import fcntl
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, MutableMapping


PROJECTION_MANIFEST_SCHEMA_VERSION = (
    "abyss_stack_external_codex_actor_workspace_manifest_v2"
)
PROJECTION_DELTA_SCHEMA_VERSION = "abyss_stack_external_codex_actor_delta_v1"
MAX_GIT_OUTPUT_BYTES = 256 * 1024 * 1024
LEGACY_GIT_ABBREV_WIDTHS = tuple(range(4, 65))
PRIVATE_GIT_CONFIG_BYTES = (
    "[core]\n"
    "\trepositoryFormatVersion = 0\n"
    "\tfileMode = true\n"
    "\tbare = false\n"
    "\tlogAllRefUpdates = false\n"
    "\texcludesFile = /dev/null\n"
    "\tfsmonitor = false\n"
    "\thooksPath = /dev/null\n"
    "[gc]\n\tauto = 0\n"
).encode("utf-8")
PRIVATE_GIT_PACK_FILE_PATTERN = re.compile(
    r"objects/pack/pack-[0-9a-f]{40}\.(?:idx|pack|rev)"
)


class ProjectionError(RuntimeError):
    """One fail-closed projection or actor-tree error."""


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_digest(value: Any) -> str:
    return sha256_bytes(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _safe_relative(value: str) -> tuple[str, ...]:
    parts = tuple(value.split("/"))
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or "\0" in value
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ProjectionError("projection contains an unsafe relative path")
    return parts


def _mode(value: os.stat_result) -> int:
    return stat.S_IMODE(value.st_mode)


def _entry_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _git_environment() -> dict[str, str]:
    return {
        "HOME": "/nonexistent",
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
    }


def _source_git_environment(workspace: Path) -> dict[str, str]:
    """Match controller Git probes while neutralizing repository filters."""

    environment = _git_environment() | {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "7",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_KEY_1": "core.fsmonitor",
        "GIT_CONFIG_KEY_2": "core.attributesFile",
        "GIT_CONFIG_KEY_3": "gpg.program",
        "GIT_CONFIG_KEY_4": "gpg.openpgp.program",
        "GIT_CONFIG_KEY_5": "gpg.x509.program",
        "GIT_CONFIG_KEY_6": "gpg.ssh.program",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_VALUE_0": "/dev/null",
        "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_VALUE_2": "/dev/null",
        "GIT_CONFIG_VALUE_3": "/usr/bin/false",
        "GIT_CONFIG_VALUE_4": "/usr/bin/false",
        "GIT_CONFIG_VALUE_5": "/usr/bin/false",
        "GIT_CONFIG_VALUE_6": "/usr/bin/false",
    }
    completed = subprocess.run(
        [
            "/usr/bin/git",
            "--no-optional-locks",
            "-C",
            str(workspace),
            "config",
            "--local",
            "--includes",
            "--name-only",
            "--null",
            "--get-regexp",
            r"^filter\..*\.(clean|smudge|process|required)$",
        ],
        capture_output=True,
        check=False,
        timeout=15,
        env=environment,
    )
    if completed.returncode not in {0, 1}:
        raise ProjectionError("source Git filter configuration could not be inspected")
    try:
        keys = sorted(
            {raw.decode("utf-8") for raw in completed.stdout.split(b"\0") if raw}
        )
    except UnicodeDecodeError as exc:
        raise ProjectionError("source Git filter key is not UTF-8") from exc
    if len(keys) > 128 or any(
        re.fullmatch(r"filter\..+\.(?:clean|smudge|process|required)", key, re.I)
        is None
        for key in keys
    ):
        raise ProjectionError("source Git filter configuration exceeds its bound")
    next_index = int(environment["GIT_CONFIG_COUNT"])
    for key in keys:
        environment[f"GIT_CONFIG_KEY_{next_index}"] = key
        environment[f"GIT_CONFIG_VALUE_{next_index}"] = (
            "false" if key.lower().endswith(".required") else ""
        )
        next_index += 1
    environment["GIT_CONFIG_COUNT"] = str(next_index)
    return environment


def _git(
    workspace: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
    timeout: int = 120,
    environment_overrides: Mapping[str, str] | None = None,
    extra_pass_fds: tuple[int, ...] = (),
) -> bytes:
    pass_fds = extra_pass_fds
    workspace_parts = workspace.parts
    if len(workspace_parts) >= 5 and workspace_parts[:4] == ("/", "proc", "self", "fd"):
        try:
            pass_fds = tuple(sorted({*pass_fds, int(workspace_parts[4])}))
        except ValueError:
            pass
    try:
        completed = subprocess.run(
            ["/usr/bin/git", "--no-optional-locks", "-C", str(workspace), *arguments],
            input=input_bytes,
            capture_output=True,
            check=False,
            timeout=timeout,
            env=_git_environment() | dict(environment_overrides or {}),
            pass_fds=pass_fds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProjectionError("private actor Git construction could not run") from exc
    if completed.returncode != 0:
        raise ProjectionError(
            "private actor Git construction rejected the admitted baseline"
        )
    if len(completed.stdout) > MAX_GIT_OUTPUT_BYTES:
        raise ProjectionError("private actor Git output exceeds its runtime bound")
    return completed.stdout


def _legacy_git_diff_matches(
    workspace: Path,
    expected_digest: Any,
    *,
    environment_overrides: Mapping[str, str],
) -> bool:
    """Recover one bounded pre-canonical Git abbreviation width exactly."""

    if not isinstance(expected_digest, str):
        return False
    for abbrev in LEGACY_GIT_ABBREV_WIDTHS:
        diff_raw = _git(
            workspace,
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--binary",
            f"--abbrev={abbrev}",
            "HEAD",
            "--",
            environment_overrides=environment_overrides,
        )
        if sha256_bytes(diff_raw) == expected_digest:
            return True
    return False


def _sealed_memfd(name: str, raw: bytes) -> int:
    if not hasattr(os, "memfd_create") or not hasattr(os, "MFD_ALLOW_SEALING"):
        raise ProjectionError("sealed private Git inspection is unavailable")
    descriptor = os.memfd_create(
        name,
        os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
    )
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise ProjectionError(
                    "private Git index snapshot could not be written"
                )
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
    except BaseException:
        os.close(descriptor)
        raise


def _private_git_index_semantics(
    workspace: Path,
    index_raw: bytes,
) -> dict[str, str]:
    """Interpret pinned index bytes without consulting the recovered tree."""

    descriptor = _sealed_memfd("aoa-external-actor-recovery-index", index_raw)
    try:
        environment = {"GIT_INDEX_FILE": f"/proc/self/fd/{descriptor}"}
        safe_git_config = (
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
        )
        return {
            "index_stage_sha256": sha256_bytes(
                _git(
                    workspace,
                    *safe_git_config,
                    "ls-files",
                    "--stage",
                    "-z",
                    environment_overrides=environment,
                    extra_pass_fds=(descriptor,),
                )
            ),
            "index_flags_sha256": sha256_bytes(
                _git(
                    workspace,
                    *safe_git_config,
                    "ls-files",
                    "-v",
                    "-z",
                    environment_overrides=environment,
                    extra_pass_fds=(descriptor,),
                )
            ),
        }
    finally:
        os.close(descriptor)


def _read_regular_at(
    parent_fd: int, name: str, relative: str
) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise ProjectionError(
            f"projection source file cannot be opened: {relative}"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ProjectionError(
                f"projection source entry is no longer a regular file: {relative}"
            )
        chunks: list[bytes] = []
        observed_bytes = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            observed_bytes += len(chunk)
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            _entry_identity(before) != _entry_identity(after)
            or observed_bytes != after.st_size
        ):
            raise ProjectionError(
                f"projection source file changed while being read: {relative}"
            )
        return b"".join(chunks), after
    except OSError as exc:
        raise ProjectionError(
            f"projection source file cannot be read: {relative}"
        ) from exc
    finally:
        os.close(descriptor)


def _read_regular_path(path: Path, *, label: str) -> tuple[bytes, os.stat_result]:
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY)
    try:
        return _read_regular_at(parent_fd, path.name, label)
    finally:
        os.close(parent_fd)


def _lexical_symlink_is_internal(relative: str, target: str) -> bool:
    if not target or target.startswith("/") or "\0" in target:
        return False
    parent = PurePosixPath(relative).parent
    parts: list[str] = []
    for part in (parent / target).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return False
            parts.pop()
        else:
            parts.append(part)
    return bool(parts) and ".git" not in parts


def _inventory(
    root: Path,
    *,
    include_git: bool = False,
    descriptor_root: bool = False,
) -> list[dict[str, Any]]:
    """Inventory one actor tree without following links."""

    if (
        not root.is_absolute()
        or (root.is_symlink() and not descriptor_root)
        or not root.is_dir()
    ):
        raise ProjectionError(
            "actor projection root must be an absolute real directory"
        )
    entries: list[dict[str, Any]] = []
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            children = sorted(os.scandir(current), key=lambda item: item.name)
        except FileNotFoundError as exc:
            relative = current.relative_to(root).as_posix()
            raise ProjectionError(
                "actor projection directory disappeared before enumeration: "
                f"{relative}"
            ) from exc
        except OSError as exc:
            raise ProjectionError("actor projection cannot enumerate its tree") from exc
        for child in children:
            relative = Path(child.path).relative_to(root).as_posix()
            _safe_relative(relative)
            if not include_git and relative.split("/", 1)[0] == ".git":
                continue
            try:
                observed = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise ProjectionError(
                    f"actor projection entry cannot be inspected: {relative}"
                ) from exc
            if stat.S_ISREG(observed.st_mode):
                data, after = _read_regular_path(Path(child.path), label=relative)
                if _entry_identity(observed) != _entry_identity(after):
                    raise ProjectionError(
                        f"actor projection file changed while being inventoried: {relative}"
                    )
                entries.append(
                    {
                        "path": relative,
                        "kind": "file",
                        "mode": _mode(observed),
                        "size_bytes": len(data),
                        "sha256": sha256_bytes(data),
                    }
                )
            elif stat.S_ISLNK(observed.st_mode):
                try:
                    target = os.readlink(child.path)
                except OSError as exc:
                    raise ProjectionError(
                        f"actor projection symlink cannot be read: {relative}"
                    ) from exc
                if not include_git and not _lexical_symlink_is_internal(
                    relative, target
                ):
                    raise ProjectionError(
                        f"actor projection symlink target is outside: {relative}"
                    )
                entries.append(
                    {
                        "path": relative,
                        "kind": "symlink",
                        "mode": _mode(observed),
                        "size_bytes": len(target.encode("utf-8")),
                        "sha256": sha256_bytes(target.encode("utf-8")),
                    }
                )
            elif stat.S_ISDIR(observed.st_mode):
                entries.append(
                    {
                        "path": relative,
                        "kind": "directory",
                        "mode": _mode(observed),
                        "size_bytes": 0,
                        "sha256": None,
                    }
                )
                pending.append(Path(child.path))
            else:
                raise ProjectionError(
                    f"actor projection does not admit special entry: {relative}"
                )
    return sorted(entries, key=lambda item: str(item["path"]))


def _private_git_digest(root: Path, *, descriptor_root: bool = False) -> str:
    git_root = root / ".git"
    if git_root.is_symlink() or not git_root.is_dir():
        raise ProjectionError("actor projection has no private Git body")
    return _canonical_digest(
        _inventory(
            git_root,
            include_git=True,
            descriptor_root=descriptor_root,
        )
    )


def build_actor_manifest(
    projection_root: str | Path,
    *,
    source_manifest_digest: str,
    source_git_head: str,
) -> dict[str, Any]:
    root = Path(projection_root).resolve()
    observed = root.stat(follow_symlinks=False)
    return {
        "$schema": "schemas/external-codex-actor-workspace-manifest.schema.json",
        "schema_version": PROJECTION_MANIFEST_SCHEMA_VERSION,
        "projection_kind": "runtime_owned_actor_workspace",
        "workspace_path": str(root),
        "workspace_identity": {
            "st_dev": int(observed.st_dev),
            "st_ino": int(observed.st_ino),
        },
        "source_manifest_digest": source_manifest_digest,
        "source_git_head": source_git_head,
        "private_git_digest": _private_git_digest(root),
        "content_entries": _inventory(root),
    }


def build_actor_manifest_from_descriptor(
    projection_fd: int,
    *,
    workspace_path: str | Path,
    source_manifest_digest: str,
    source_git_head: str,
) -> dict[str, Any]:
    """Inventory the exact open workspace inode later bound into the child."""

    try:
        observed = os.fstat(projection_fd)
    except OSError as exc:
        raise ProjectionError("actor projection descriptor is unavailable") from exc
    if not stat.S_ISDIR(observed.st_mode):
        raise ProjectionError("actor projection descriptor is not a directory")
    descriptor_root = Path(f"/proc/self/fd/{projection_fd}")
    workspace = Path(workspace_path)
    if not workspace.is_absolute():
        raise ProjectionError("actor projection workspace path is not absolute")
    return {
        "$schema": "schemas/external-codex-actor-workspace-manifest.schema.json",
        "schema_version": PROJECTION_MANIFEST_SCHEMA_VERSION,
        "projection_kind": "runtime_owned_actor_workspace",
        "workspace_path": str(workspace),
        "workspace_identity": {
            "st_dev": int(observed.st_dev),
            "st_ino": int(observed.st_ino),
        },
        "source_manifest_digest": source_manifest_digest,
        "source_git_head": source_git_head,
        "private_git_digest": _private_git_digest(
            descriptor_root,
            descriptor_root=True,
        ),
        "content_entries": _inventory(
            descriptor_root,
            descriptor_root=True,
        ),
    }


def build_private_git_admission_manifest(
    projection_root: str | Path,
    *,
    expected_private_git_entries: list[dict[str, Any]] | None = None,
    expected_source_git_head: str | None = None,
    expected_object_ids: set[str] | frozenset[str] | None = None,
    expected_info_exclude: bytes | None = None,
    semantic_workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    """Observe stable private-Git meaning without executing recovered bytes."""

    root = Path(projection_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ProjectionError("actor projection root is unavailable")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(root, flags)
    try:
        observed = os.fstat(descriptor)
        coordinate = root.stat(follow_symlinks=False)
        if not _same_inode(observed, coordinate):
            raise ProjectionError("actor projection coordinate changed")
        descriptor_root = Path(f"/proc/self/fd/{descriptor}")
        full_private_entries = _inventory(
            descriptor_root / ".git",
            include_git=True,
            descriptor_root=True,
        )
        private_entries = [
            entry
            for entry in full_private_entries
            if entry["path"] != "index"
        ]
        if (
            expected_private_git_entries is not None
            and private_entries != expected_private_git_entries
        ):
            raise ProjectionError(
                "actor private Git bytes differ before semantic inspection"
            )
        private_files = {
            str(entry.get("path")): entry
            for entry in full_private_entries
            if entry.get("kind") != "directory"
        }
        required_private_files = {
            "HEAD",
            "config",
            "index",
            "info/exclude",
            "refs/heads/actor-baseline",
        }
        unexpected_private_files = set(private_files) - required_private_files
        pack_files = {
            path
            for path in unexpected_private_files
            if PRIVATE_GIT_PACK_FILE_PATTERN.fullmatch(path)
        }
        if (
            not required_private_files.issubset(private_files)
            or unexpected_private_files != pack_files
            or len([path for path in pack_files if path.endswith(".pack")]) != 1
            or len([path for path in pack_files if path.endswith(".idx")]) != 1
            or len([path for path in pack_files if path.endswith(".rev")]) > 1
            or {
                path.rsplit(".", 1)[0]
                for path in pack_files
            }
            != {next(iter(pack_files)).rsplit(".", 1)[0]}
        ):
            raise ProjectionError(
                "actor private Git topology contains unadmitted metadata"
            )
        config_entries = [
            entry for entry in private_entries if entry.get("path") == "config"
        ]
        if len(config_entries) != 1 or any(
            config_entries[0].get(key) != value
            for key, value in {
                "path": "config",
                "kind": "file",
                "size_bytes": len(PRIVATE_GIT_CONFIG_BYTES),
                "sha256": sha256_bytes(PRIVATE_GIT_CONFIG_BYTES),
            }.items()
        ):
            raise ProjectionError(
                "actor private Git configuration is not the runtime-authored posture"
            )
        if expected_source_git_head is not None:
            expected_head = b"ref: refs/heads/actor-baseline\n"
            expected_ref = (expected_source_git_head + "\n").encode("ascii")
            identity_expectations = {
                "HEAD": expected_head,
                "refs/heads/actor-baseline": expected_ref,
            }
            identity_entries = {
                str(entry.get("path")): entry
                for entry in private_entries
                if entry.get("kind") != "directory"
                and (
                    entry.get("path") == "HEAD"
                    or str(entry.get("path", "")).startswith("refs/")
                )
            }
            if set(identity_entries) != set(identity_expectations) or any(
                identity_entries[path].get("kind") != "file"
                or identity_entries[path].get("size_bytes") != len(raw)
                or identity_entries[path].get("sha256") != sha256_bytes(raw)
                for path, raw in identity_expectations.items()
            ):
                raise ProjectionError(
                    "actor private Git identity differs from the admitted source head"
                )
        if expected_object_ids is not None:
            actual_object_ids = {
                value.decode("ascii")
                for value in _git(
                    descriptor_root,
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "cat-file",
                    "--batch-check=%(objectname)",
                    "--batch-all-objects",
                    environment_overrides={"GIT_NO_REPLACE_OBJECTS": "1"},
                ).splitlines()
                if value
            }
            if actual_object_ids != set(expected_object_ids):
                raise ProjectionError(
                    "actor private Git object closure differs from the admitted source"
                )
            _git(
                descriptor_root,
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "fsck",
                "--strict",
                "--full",
                "--no-reflogs",
                "--no-dangling",
                environment_overrides={"GIT_NO_REPLACE_OBJECTS": "1"},
            )
        if expected_info_exclude is not None:
            exclude_entry = private_files["info/exclude"]
            if (
                exclude_entry.get("kind") != "file"
                or exclude_entry.get("size_bytes") != len(expected_info_exclude)
                or exclude_entry.get("sha256")
                != sha256_bytes(expected_info_exclude)
            ):
                raise ProjectionError(
                    "actor private Git excludes differ from the admitted source"
                )
        index_raw, _ = _read_regular_path(
            descriptor_root / ".git" / "index",
            label=".git/index",
        )
        semantic_root_is_descriptor = semantic_workspace_root is None
        semantic_root = (
            descriptor_root
            if semantic_root_is_descriptor
            else Path(semantic_workspace_root)
        )
        if (
            not semantic_root.is_absolute()
            or (not semantic_root_is_descriptor and semantic_root.is_symlink())
            or not semantic_root.is_dir()
        ):
            raise ProjectionError("private Git semantic workspace is unavailable")
        manifest = {
            "private_git_entries": private_entries,
            "private_git_digest": _canonical_digest(full_private_entries),
            **_private_git_index_semantics(semantic_root, index_raw),
        }
        full_private_entries_after = _inventory(
            descriptor_root / ".git",
            include_git=True,
            descriptor_root=True,
        )
        if full_private_entries_after != full_private_entries:
            raise ProjectionError(
                "actor private Git bytes changed during semantic inspection"
            )
        after = root.stat(follow_symlinks=False)
        if not _same_inode(observed, after):
            raise ProjectionError("actor projection coordinate changed")
        return manifest
    finally:
        os.close(descriptor)


def _open_directory_at(parent_fd: int, name: str, relative: str) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise ProjectionError(
            f"projection source directory cannot be opened: {relative}"
        ) from exc


def _copy_tree_from_descriptor(
    source_fd: int,
    staging: Path,
    *,
    include_git: bool,
) -> None:
    pending: list[tuple[int, str]] = [(os.dup(source_fd), "")]
    directories: list[tuple[Path, int]] = []
    try:
        while pending:
            current_fd, prefix = pending.pop()
            try:
                children = sorted(os.scandir(current_fd), key=lambda item: item.name)
                for child in children:
                    relative = f"{prefix}/{child.name}" if prefix else child.name
                    _safe_relative(relative)
                    if not include_git and relative.split("/", 1)[0] == ".git":
                        continue
                    try:
                        observed = os.stat(
                            child.name,
                            dir_fd=current_fd,
                            follow_symlinks=False,
                        )
                    except OSError as exc:
                        raise ProjectionError(
                            f"source entry disappeared during projection: {relative}"
                        ) from exc
                    target_path = staging.joinpath(*relative.split("/"))
                    if stat.S_ISDIR(observed.st_mode):
                        target_path.mkdir(mode=0o700, parents=False, exist_ok=False)
                        directories.append((target_path, _mode(observed)))
                        pending.append(
                            (
                                _open_directory_at(current_fd, child.name, relative),
                                relative,
                            )
                        )
                    elif stat.S_ISREG(observed.st_mode):
                        data, after = _read_regular_at(current_fd, child.name, relative)
                        if _entry_identity(observed) != _entry_identity(after):
                            raise ProjectionError(
                                f"source file changed during projection: {relative}"
                            )
                        descriptor = os.open(
                            target_path,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                            0o600,
                        )
                        try:
                            offset = 0
                            while offset < len(data):
                                written = os.write(descriptor, data[offset:])
                                if written <= 0:
                                    raise OSError("projection write was incomplete")
                                offset += written
                            os.fsync(descriptor)
                        finally:
                            os.close(descriptor)
                        os.chmod(target_path, _mode(observed), follow_symlinks=False)
                    elif stat.S_ISLNK(observed.st_mode):
                        try:
                            target = os.readlink(child.name, dir_fd=current_fd)
                        except OSError as exc:
                            raise ProjectionError(
                                f"projection symlink cannot be read: {relative}"
                            ) from exc
                        if not include_git and not _lexical_symlink_is_internal(
                            relative, target
                        ):
                            raise ProjectionError(
                                f"projection symlink target is outside: {relative}"
                            )
                        os.symlink(target, target_path)
                    else:
                        raise ProjectionError(
                            f"source special entry is unsupported: {relative}"
                        )
            finally:
                os.close(current_fd)
    except BaseException:
        for descriptor, _ in pending:
            os.close(descriptor)
        raise
    for target_path, mode in sorted(
        directories,
        key=lambda item: len(item[0].parts),
        reverse=True,
    ):
        try:
            os.chmod(target_path, mode, follow_symlinks=False)
        except OSError as exc:
            raise ProjectionError(
                f"cannot preserve projection directory mode: {target_path}"
            ) from exc


def _normalized_source_entries(
    source_manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    entries = source_manifest.get("content_entries")
    if not isinstance(entries, list):
        raise ProjectionError("source manifest has no admitted content entries")
    normalized: list[dict[str, Any]] = []
    for raw in entries:
        if not isinstance(raw, Mapping):
            raise ProjectionError("source manifest content entry is malformed")
        if raw.get("kind") == "missing":
            continue
        normalized.append(
            {
                "path": str(raw.get("path", "")),
                "kind": str(raw.get("kind", "")),
                "mode": raw.get("mode"),
                "size_bytes": raw.get("size_bytes"),
                "sha256": raw.get("sha256"),
            }
        )
    return sorted(normalized, key=lambda item: item["path"])


def _nul_paths(raw: bytes) -> list[str]:
    values: list[str] = []
    for value in raw.split(b"\0"):
        if not value:
            continue
        try:
            relative = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectionError("private actor Git path is not UTF-8") from exc
        _safe_relative(relative)
        values.append(relative)
    return values


def _git_exclude_pattern(relative: str, *, directory: bool) -> str:
    escaped = "".join(
        f"\\{character}" if character in "\\*?[#" else character
        for character in relative
    )
    return f"/{escaped}{'/' if directory else ''}"


def _construct_private_git(
    source: Path,
    staging: Path,
    *,
    source_manifest: Mapping[str, Any],
) -> tuple[frozenset[str], bytes]:
    source_head = str(source_manifest["git_head"])
    index_entries = _git(source, "ls-files", "--stage", "-z")
    object_ids = {source_head}
    for record in index_entries.split(b"\0"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3 or len(fields[1]) != 40:
            raise ProjectionError("source Git index cannot be reproduced safely")
        try:
            path = raw_path.decode("utf-8")
            object_id = fields[1].decode("ascii")
        except UnicodeDecodeError as exc:
            raise ProjectionError(
                "source Git index contains an unsupported path"
            ) from exc
        _safe_relative(path)
        object_ids.add(object_id)
    reachable_object_ids = {
        value.decode("ascii")
        for value in _git(
            source,
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "rev-list",
            "--objects",
            "--no-object-names",
            source_head,
            environment_overrides={"GIT_NO_REPLACE_OBJECTS": "1"},
        ).splitlines()
        if value
    }
    object_ids.update(reachable_object_ids)
    packed = _git(
        source,
        "pack-objects",
        "--stdout",
        "--revs",
        input_bytes=("\n".join(sorted(object_ids)) + "\n").encode("ascii"),
        timeout=300,
    )
    _git(staging, "init", "--quiet")
    _git(
        staging, "index-pack", "--stdin", "--fix-thin", input_bytes=packed, timeout=300
    )
    _git(staging, "update-ref", "refs/heads/actor-baseline", source_head)
    _git(staging, "symbolic-ref", "HEAD", "refs/heads/actor-baseline")
    if index_entries:
        _git(staging, "update-index", "-z", "--index-info", input_bytes=index_entries)
    for raw in source_manifest.get("content_entries", []):
        if not isinstance(raw, Mapping):
            continue
        path = str(raw.get("path", ""))
        flags = raw.get("index_flags", [])
        if "assume_unchanged" in flags:
            _git(staging, "update-index", "--assume-unchanged", "--", path)
        if "skip_worktree" in flags:
            _git(staging, "update-index", "--skip-worktree", "--", path)
    ignored = _nul_paths(
        _git(
            source,
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
        )
    )
    exclude_lines = [
        _git_exclude_pattern(
            relative,
            directory=(staging.joinpath(*relative.split("/")).is_dir()),
        )
        for relative in ignored
    ]
    info = staging / ".git" / "info"
    info.mkdir(mode=0o700, parents=True, exist_ok=True)
    exclude_bytes = (
        "\n".join(exclude_lines) + ("\n" if exclude_lines else "")
    ).encode("utf-8")
    (info / "exclude").write_bytes(exclude_bytes)
    (staging / ".git" / "config").write_bytes(PRIVATE_GIT_CONFIG_BYTES)
    for forbidden in (
        "branches",
        "description",
        "hooks",
        "objects/info/alternates",
        "FETCH_HEAD",
        "logs",
    ):
        candidate = staging / ".git" / forbidden
        if candidate.is_file() or candidate.is_symlink():
            candidate.unlink()
        elif candidate.is_dir():
            _remove_tree(candidate)
    status_raw = _git(
        staging,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    diff_raw = _git(
        staging,
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--binary",
        "--full-index",
        "HEAD",
        "--",
    )
    status_matches = sha256_bytes(status_raw) == source_manifest.get(
        "git_status_porcelain_sha256"
    )
    diff_matches = sha256_bytes(diff_raw) == source_manifest.get(
        "git_diff_binary_sha256"
    )
    if status_matches and not diff_matches:
        source_git_environment = _source_git_environment(source)
        source_full_diff_raw = _git(
            source,
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--binary",
            "--full-index",
            "HEAD",
            "--",
            environment_overrides=source_git_environment,
        )
        diff_matches = (
            _legacy_git_diff_matches(
                source,
                source_manifest.get("git_diff_binary_sha256"),
                environment_overrides=source_git_environment,
            )
            and sha256_bytes(diff_raw) == sha256_bytes(source_full_diff_raw)
        )
    if not status_matches or not diff_matches:
        raise ProjectionError(
            "private actor Git baseline differs from the admitted source"
        )
    source_bytes = str(source).encode("utf-8")
    for entry in _inventory(staging / ".git", include_git=True):
        if entry["kind"] != "file":
            continue
        candidate = staging / ".git" / str(entry["path"])
        raw, _ = _read_regular_path(candidate, label=f".git/{entry['path']}")
        if source_bytes and source_bytes in raw:
            raise ProjectionError("private actor Git body retained a source coordinate")
    return frozenset(object_ids), exclude_bytes


def _remove_tree(root: Path) -> None:
    if root.is_symlink() or root.is_file():
        root.unlink()
        return
    if not root.exists():
        return
    for current, directories, files in os.walk(root, topdown=False, followlinks=False):
        current_path = Path(current)
        try:
            os.chmod(current_path, 0o700, follow_symlinks=False)
        except OSError:
            pass
        for name in files:
            (current_path / name).unlink()
        for name in directories:
            candidate = current_path / name
            if candidate.is_symlink():
                candidate.unlink()
            else:
                try:
                    os.chmod(candidate, 0o700, follow_symlinks=False)
                except OSError:
                    pass
                candidate.rmdir()
    root.rmdir()


def remove_actor_projection(
    projection_root: str | Path,
    *,
    expected_identity: Mapping[str, Any] | None = None,
) -> None:
    """Remove one known runtime-owned projection, including read-only directories."""

    root = Path(projection_root)
    if not root.is_absolute() or root.is_symlink():
        raise ProjectionError("actor projection cleanup target is unsafe")
    if expected_identity is not None:
        try:
            observed = root.stat(follow_symlinks=False)
        except OSError as exc:
            raise ProjectionError(
                "actor projection cleanup coordinate no longer names the published inode"
            ) from exc
        if (
            expected_identity.get("st_dev") != observed.st_dev
            or expected_identity.get("st_ino") != observed.st_ino
        ):
            raise ProjectionError(
                "actor projection cleanup refused a replaced publication coordinate"
            )
    _remove_tree(root)


def _open_publication_parent(target: Path) -> tuple[int, os.stat_result]:
    """Open and pin the exact parent in which one projection is published."""

    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        parent_fd = os.open(target.parent, flags)
    except OSError as exc:
        raise ProjectionError("actor projection parent cannot be pinned") from exc
    observed = os.fstat(parent_fd)
    try:
        path_observed = target.parent.stat(follow_symlinks=False)
    except OSError as exc:
        os.close(parent_fd)
        raise ProjectionError("actor projection parent coordinate changed") from exc
    if not _same_inode(observed, path_observed):
        os.close(parent_fd)
        raise ProjectionError("actor projection parent coordinate changed")
    return parent_fd, observed


def _fresh_staging(parent_fd: int, prefix: str) -> tuple[str, Path, int]:
    """Create one private staging directory relative to the pinned parent."""

    for _ in range(32):
        name = prefix + os.urandom(12).hex()
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        staging = Path(f"/proc/self/fd/{parent_fd}/{name}")
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            staging_fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError:
            _remove_tree(staging)
            raise
        return name, staging, staging_fd
    raise ProjectionError("cannot allocate a fresh actor projection staging directory")


def _publish_staging(
    *,
    parent_fd: int,
    parent_identity: os.stat_result,
    staging_name: str,
    staging_fd: int,
    target: Path,
    publication_state: MutableMapping[str, bool],
) -> None:
    """Publish the pinned staging inode and prove the public name still denotes it."""

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise ProjectionError(
            "non-replacing actor projection publication is unavailable"
        )
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    try:
        result = renameat2(
            parent_fd,
            os.fsencode(staging_name),
            parent_fd,
            os.fsencode(target.name),
            1,  # RENAME_NOREPLACE
        )
        if result != 0:
            failure = ctypes.get_errno()
            if failure == errno.EEXIST:
                raise ProjectionError(
                    "actor projection publication target already exists"
                )
            raise OSError(failure, os.strerror(failure))
        # From this instruction onward the runtime-owned inode is published,
        # even if a later coordinate verification fails.
        publication_state["committed"] = True
        published = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        public_parent = target.parent.stat(follow_symlinks=False)
        public = target.stat(follow_symlinks=False)
    except OSError as exc:
        raise ProjectionError(
            "actor projection publication could not be verified"
        ) from exc
    pinned = os.fstat(staging_fd)
    if (
        not _same_inode(parent_identity, public_parent)
        or not _same_inode(pinned, published)
        or not _same_inode(pinned, public)
    ):
        raise ProjectionError("actor projection publication coordinate was replaced")


def materialize_actor_projection(
    source_workspace: str | Path,
    projection_path: str | Path,
    *,
    source_manifest: Mapping[str, Any],
    source_manifest_digest: str,
    private_git_admission: MutableMapping[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Copy one admitted source tree into a fresh runtime-owned Git workspace."""

    source = Path(source_workspace).resolve(strict=True)
    target = Path(projection_path)
    if not target.is_absolute() or target.is_symlink():
        raise ProjectionError("actor projection path must be absolute and non-symbolic")
    if target.exists():
        raise ProjectionError("actor projection path already exists")
    try:
        target.relative_to(source)
    except ValueError:
        pass
    else:
        raise ProjectionError("actor projection may not be inside the source workspace")
    if not isinstance(source_manifest, Mapping):
        raise ProjectionError("source manifest is unavailable")
    if source_manifest.get("workspace_path") != str(source):
        raise ProjectionError("source manifest names another workspace")
    source_head = str(source_manifest.get("git_head", ""))
    if not source_head:
        raise ProjectionError("source manifest has no exact Git HEAD")
    source_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        source_flags |= os.O_NOFOLLOW
    source_fd = os.open(source, source_flags)
    try:
        observed = os.fstat(source_fd)
        identity = source_manifest.get("workspace_identity", {}).get("root", {})
        if (
            identity.get("st_dev") != observed.st_dev
            or identity.get("st_ino") != observed.st_ino
        ):
            raise ProjectionError("source root identity changed before projection")
        parent_fd, parent_identity = _open_publication_parent(target)
        staging_name = ""
        staging_fd = -1
        publication_state = {"committed": False}
        try:
            staging_name, staging, staging_fd = _fresh_staging(
                parent_fd, ".actor-projection-"
            )
            os.chmod(staging, 0o700)
            _copy_tree_from_descriptor(source_fd, staging, include_git=False)
            if _inventory(staging) != _normalized_source_entries(source_manifest):
                raise ProjectionError(
                    "actor projection bytes differ from the admitted source manifest"
                )
            expected_object_ids, expected_info_exclude = _construct_private_git(
                source,
                staging,
                source_manifest=source_manifest,
            )
            manifest = build_actor_manifest_from_descriptor(
                staging_fd,
                workspace_path=target,
                source_manifest_digest=source_manifest_digest,
                source_git_head=source_head,
            )
            if manifest["content_entries"] != _normalized_source_entries(
                source_manifest
            ):
                raise ProjectionError(
                    "actor projection baseline differs from the admitted source manifest"
                )
            captured_private_git = build_private_git_admission_manifest(
                staging,
                expected_source_git_head=source_head,
                expected_object_ids=expected_object_ids,
                expected_info_exclude=expected_info_exclude,
            )
            if captured_private_git.get("private_git_digest") != manifest.get(
                "private_git_digest"
            ):
                raise ProjectionError(
                    "actor private Git changed before recovery authority capture"
                )
            _publish_staging(
                parent_fd=parent_fd,
                parent_identity=parent_identity,
                staging_name=staging_name,
                staging_fd=staging_fd,
                target=target,
                publication_state=publication_state,
            )
            if private_git_admission is not None:
                private_git_admission.clear()
                private_git_admission.update(captured_private_git or {})
        except BaseException:
            cleanup_name = (
                target.name if publication_state["committed"] else staging_name
            )
            cleanup = Path(f"/proc/self/fd/{parent_fd}/{cleanup_name}")
            try:
                if staging_fd >= 0:
                    expected = os.fstat(staging_fd)
                    cleanup_observed = cleanup.stat(follow_symlinks=False)
                    if _same_inode(expected, cleanup_observed):
                        _remove_tree(cleanup)
            except OSError:
                pass
            raise
        finally:
            if staging_fd >= 0:
                os.close(staging_fd)
            os.close(parent_fd)
    finally:
        os.close(source_fd)
    return target, manifest


def materialize_actor_projection_from_seed(
    seed_path: str | Path,
    projection_path: str | Path,
    *,
    expected_manifest: Mapping[str, Any],
    private_git_admission: MutableMapping[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Clone one exact terminal writer tree for an independent reviewer."""

    seed = Path(seed_path)
    target = Path(projection_path)
    if (
        not seed.is_absolute()
        or seed.is_symlink()
        or not seed.is_dir()
        or not target.is_absolute()
        or target.is_symlink()
        or target.exists()
    ):
        raise ProjectionError("actor projection seed or target is unavailable")
    expected_root = Path(str(expected_manifest.get("workspace_path", "")))
    expected_entries = expected_manifest.get("content_entries")
    if (
        not expected_root.is_absolute()
        or expected_root.resolve() != seed.resolve()
        or expected_manifest.get("projection_kind") != "runtime_owned_actor_workspace"
        or not isinstance(expected_entries, list)
    ):
        raise ProjectionError("actor projection seed manifest is malformed")
    seed_fd = os.open(seed, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parent_fd, parent_identity = _open_publication_parent(target)
        staging_name = ""
        staging_fd = -1
        publication_state = {"committed": False}
        try:
            staging_name, staging, staging_fd = _fresh_staging(
                parent_fd, ".review-projection-"
            )
            os.chmod(staging, 0o700)
            _copy_tree_from_descriptor(seed_fd, staging, include_git=True)
            observed = build_actor_manifest_from_descriptor(
                staging_fd,
                workspace_path=target,
                source_manifest_digest=str(
                    expected_manifest.get("source_manifest_digest", "")
                ),
                source_git_head=str(expected_manifest.get("source_git_head", "")),
            )
            if observed["content_entries"] != expected_entries or observed[
                "private_git_digest"
            ] != expected_manifest.get("private_git_digest"):
                raise ProjectionError(
                    "actor projection seed changed before reviewer materialization"
                )
            captured_private_git = build_private_git_admission_manifest(
                staging,
                expected_source_git_head=str(
                    expected_manifest.get("source_git_head", "")
                ),
            )
            if captured_private_git.get("private_git_digest") != observed.get(
                "private_git_digest"
            ):
                raise ProjectionError(
                    "reviewer private Git changed before recovery authority capture"
                )
            _publish_staging(
                parent_fd=parent_fd,
                parent_identity=parent_identity,
                staging_name=staging_name,
                staging_fd=staging_fd,
                target=target,
                publication_state=publication_state,
            )
            if private_git_admission is not None:
                private_git_admission.clear()
                private_git_admission.update(captured_private_git or {})
        except BaseException:
            cleanup_name = (
                target.name if publication_state["committed"] else staging_name
            )
            cleanup = Path(f"/proc/self/fd/{parent_fd}/{cleanup_name}")
            try:
                if staging_fd >= 0:
                    expected = os.fstat(staging_fd)
                    cleanup_observed = cleanup.stat(follow_symlinks=False)
                    if _same_inode(expected, cleanup_observed):
                        _remove_tree(cleanup)
            except OSError:
                pass
            raise
        finally:
            if staging_fd >= 0:
                os.close(staging_fd)
            os.close(parent_fd)
    finally:
        os.close(seed_fd)
    return target, observed


def compare_actor_manifest(
    baseline: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    before = {
        str(item["path"]): dict(item) for item in baseline.get("content_entries", [])
    }
    after = {
        str(item["path"]): dict(item) for item in current.get("content_entries", [])
    }
    changes: list[dict[str, Any]] = []
    for path in sorted(set(before) | set(after)):
        old = before.get(path)
        new = after.get(path)
        if old == new:
            continue
        if old is None:
            status = "created"
        elif new is None:
            status = "deleted"
        elif old.get("kind") != new.get("kind"):
            status = "type_changed"
        elif old.get("mode") != new.get("mode") and (
            old.get("sha256"),
            old.get("size_bytes"),
        ) == (new.get("sha256"), new.get("size_bytes")):
            status = "mode_changed"
        else:
            status = "modified"
        changes.append({"path": path, "status": status, "before": old, "after": new})
    return changes


def build_actor_delta(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    baseline_digest: str,
    current_digest: str,
    private_git_baseline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    private_git_origin = (
        baseline if private_git_baseline is None else private_git_baseline
    )
    if private_git_origin.get("private_git_digest") != current.get(
        "private_git_digest"
    ):
        raise ProjectionError("actor private Git body changed during execution")
    return {
        "$schema": "schemas/external-codex-actor-delta.schema.json",
        "schema_version": PROJECTION_DELTA_SCHEMA_VERSION,
        "projection_kind": "runtime_owned_actor_workspace",
        "baseline_manifest_digest": baseline_digest,
        "final_manifest_digest": current_digest,
        "changes": compare_actor_manifest(baseline, current),
    }
