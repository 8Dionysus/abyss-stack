"""Exact runtime-image capture and sealed staging, never execution admission.

The expected manifest must come from the caller's separately verified owner
evidence. Self-consistency is not authority. Unlike analysis inputs, a runtime
image preserves executable modes and explicitly declared internal file links.
No mutable directory or pathname is used when staging a captured image.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Iterator

from analysis_inputs import AnalysisInputError, _directory, _name, _signature


SCHEMA = "abyss-stack-code-runtime-image-v1"
_CHUNK = 64 * 1024
# The supported namespace launcher's total ceiling is 9000 arguments, including
# --args input. Reserve headroom; callers still check their whole composed plan.
MAX_IMAGE_MOUNT_ARGUMENTS = 8000


class RuntimeImageError(ValueError):
    """Runtime bytes, layout or modes do not match the declared bounded image."""


@dataclass(frozen=True)
class RuntimeLimits:
    # Separate from source capture and the existing LSP contract. Bundled Node
    # exceeds the source per-file bound; an npm closure can exceed 4096 files.
    max_entries: int = 12_000
    max_file_bytes: int = 128 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_depth: int = 64

    def __post_init__(self) -> None:
        if (any(type(value) is not int or value <= 0 for value in vars(self).values())
                or self.max_file_bytes > self.max_total_bytes):
            raise RuntimeImageError("runtime bounds must be positive, consistent integers")


@dataclass(frozen=True)
class RuntimeImage:
    root: str
    manifest_bytes: bytes
    files: tuple[tuple[str, bytes], ...]
    digest: str

    def manifest(self) -> dict:
        return json.loads(self.manifest_bytes)


@dataclass(frozen=True)
class SealedRuntimeImage:
    arguments: tuple[str, ...]
    pass_fds: tuple[int, ...]
    digest: str


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _relative(value: object) -> tuple[str, ...]:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 4096:
        raise RuntimeImageError("runtime path must be bounded UTF-8")
    return tuple(_name(component) for component in value.split("/"))


def _link_destination(path: str, target: object) -> str:
    if (not isinstance(target, str) or not target or target.startswith("/")
            or len(target.encode("utf-8")) > 4096):
        raise RuntimeImageError("runtime link must have a bounded relative target")
    parts = list(_relative(path)[:-1])
    named_component_seen = False
    for component in target.split("/"):
        if component == "..":
            if not parts or named_component_seen:
                raise RuntimeImageError("runtime link escapes image")
            parts.pop()
        else:
            parts.append(_name(component))
            named_component_seen = True
    return "/".join(parts)


def _manifest(value: object, limits: RuntimeLimits) -> dict:
    if not isinstance(limits, RuntimeLimits):
        raise RuntimeImageError("explicit runtime limits required")
    if (not isinstance(value, dict) or set(value) != {"schema", "entries"}
            or value.get("schema") != SCHEMA or not isinstance(value.get("entries"), list)):
        raise RuntimeImageError("exact runtime manifest schema required")
    if len(value["entries"]) > limits.max_entries:
        raise RuntimeImageError("runtime entry count exceeds limit")
    paths: dict[str, dict] = {}
    total = 0
    for item in value["entries"]:
        if not isinstance(item, dict):
            raise RuntimeImageError("runtime entries must be objects")
        kind = item.get("kind")
        extra = {"file": {"bytes", "sha256"}, "directory": set(), "symlink": {"target"}}
        if (kind not in extra or set(item) != {"path", "kind", "mode"} | extra[kind]):
            raise RuntimeImageError("exact runtime entry schema required")
        path = item["path"]
        parts = _relative(path)
        if path in paths or len(parts) > limits.max_depth:
            raise RuntimeImageError("duplicate or too deep runtime entry")
        modes = {"file": {0o644, 0o755}, "directory": {0o755}, "symlink": {0o777}}
        if type(item["mode"]) is not int or item["mode"] not in modes[kind]:
            raise RuntimeImageError("unsafe or unsupported runtime mode")
        if kind == "file":
            size, digest = item["bytes"], item["sha256"]
            if (type(size) is not int or not 0 <= size <= limits.max_file_bytes
                    or not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)):
                raise RuntimeImageError("invalid runtime file size or digest")
            total += size
            if total > limits.max_total_bytes:
                raise RuntimeImageError("runtime total bytes exceed limit")
        elif kind == "symlink":
            _link_destination(path, item["target"])
        paths[path] = dict(item)
    for path, item in paths.items():
        parts = path.split("/")
        for length in range(1, len(parts)):
            if paths.get("/".join(parts[:length]), {}).get("kind") != "directory":
                raise RuntimeImageError("runtime parent is missing or is not a directory")
        if item["kind"] == "symlink":
            # No link chains, loops, directory links or links to missing bytes.
            if paths.get(_link_destination(path, item["target"]), {}).get("kind") != "file":
                raise RuntimeImageError("runtime link must point directly to an image file")
    return {"schema": SCHEMA, "entries": [paths[path] for path in sorted(paths)]}


def _scan(descriptor: int, limits: RuntimeLimits) -> dict[str, tuple]:
    result: dict[str, tuple] = {}

    def visit(directory: int, prefix: tuple[str, ...]) -> None:
        before = _signature(os.fstat(directory))
        with os.scandir(directory) as entries:
            for entry in entries:
                if len(result) >= limits.max_entries:
                    raise RuntimeImageError("runtime entry count exceeds limit")
                parts = (*prefix, _name(entry.name))
                if len(parts) > limits.max_depth:
                    raise RuntimeImageError("runtime directory depth exceeds limit")
                path = "/".join(parts)
                info = os.stat(entry.name, dir_fd=directory, follow_symlinks=False)
                mode = stat.S_IMODE(info.st_mode)
                if stat.S_ISDIR(info.st_mode):
                    result[path] = ("directory", mode, _signature(info), "")
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                    dir_fd=directory)
                    try:
                        if _signature(os.fstat(child)) != _signature(info):
                            raise RuntimeImageError("runtime directory changed while opening")
                        visit(child, parts)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    result[path] = ("file", mode, _signature(info), "")
                elif stat.S_ISLNK(info.st_mode):
                    target = os.readlink(entry.name, dir_fd=directory)
                    if _signature(os.stat(entry.name, dir_fd=directory, follow_symlinks=False)) != _signature(info):
                        raise RuntimeImageError("runtime link changed while reading")
                    result[path] = ("symlink", mode, _signature(info), target)
                else:
                    raise RuntimeImageError("runtime image contains a hard link or special file")
        if _signature(os.fstat(directory)) != before:
            raise RuntimeImageError("runtime directory changed while scanning")

    visit(descriptor, ())
    return result


def _read_file(root: int, item: dict, signature: tuple) -> bytes:
    descriptor = os.dup(root)
    try:
        for component in item["path"].split("/")[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        opened = os.open(item["path"].split("/")[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=descriptor)
        try:
            before = os.fstat(opened)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or _signature(before) != signature or before.st_size != item["bytes"]):
                raise RuntimeImageError("runtime file identity or size changed")
            chunks: list[bytes] = []
            size = 0
            while chunk := os.read(opened, min(_CHUNK, item["bytes"] - size + 1)):
                size += len(chunk)
                if size > item["bytes"]:
                    raise RuntimeImageError("runtime file grew beyond declared size")
                chunks.append(chunk)
            content = b"".join(chunks)
            after = os.fstat(opened)
            if (size != item["bytes"] or after.st_nlink != 1
                    or _signature(after) != signature
                    or hashlib.sha256(content).hexdigest() != item["sha256"]):
                raise RuntimeImageError("runtime file content changed or digest mismatch")
            return content
        finally:
            os.close(opened)
    finally:
        os.close(descriptor)


def capture_runtime_tree(
    root: str | Path, *, expected: dict, limits: RuntimeLimits = RuntimeLimits(),
) -> RuntimeImage:
    """Capture exactly one complete declared layout, without following links.

    Hashes/modes come from expected owner evidence, not a manifest learned from
    the mutable tree. Layout/stat scans bracket bounded reads; observed drift
    fails. Captured bytes remain fixed even if the host tree later changes.
    This is not an atomic hostile-writer snapshot or an admission verdict.
    """
    try:
        manifest = _manifest(expected, limits)
        if not isinstance(root, (str, Path)):
            raise RuntimeImageError("runtime root must be an absolute path")
        path = Path(root)
        with _directory(path) as descriptor:
            initial = _signature(os.fstat(descriptor))
            layout = _scan(descriptor, limits)
            if set(layout) != {item["path"] for item in manifest["entries"]}:
                raise RuntimeImageError("runtime image path set differs from expected manifest")
            files = []
            for item in manifest["entries"]:
                kind, mode, signature, target = layout[item["path"]]
                if (kind != item["kind"] or mode != item["mode"]
                        or target != item.get("target", "")):
                    raise RuntimeImageError("runtime image type, mode or link target differs")
                if kind == "file":
                    files.append((item["path"], _read_file(descriptor, item, signature)))
            if _scan(descriptor, limits) != layout or _signature(os.fstat(descriptor)) != initial:
                raise RuntimeImageError("runtime image changed during capture")
            with _directory(path) as current:
                if _signature(os.fstat(current)) != initial:
                    raise RuntimeImageError("runtime root changed during capture")
        raw = _canonical(manifest)
        return RuntimeImage(str(path), raw, tuple(files), hashlib.sha256(raw).hexdigest())
    except RuntimeImageError:
        raise
    except (OSError, UnicodeError, TypeError, AnalysisInputError) as exc:
        raise RuntimeImageError("unable to capture exact runtime image") from exc


@contextmanager
def seal_runtime_tree(
    image: RuntimeImage, *, namespace_root: str, limits: RuntimeLimits = RuntimeLimits(),
) -> Iterator[SealedRuntimeImage]:
    """Stage only sealed bytes, modes, directories and internal file links.

    Arguments alone are not a sandbox: the launch owner must isolate processes,
    network, environment and outputs, remount directory/link parents read-only,
    authenticate the exact full execution contract and enforce its bounds.
    """
    import fcntl

    descriptors: list[int] = []
    try:
        if (not isinstance(image, RuntimeImage) or type(image.manifest_bytes) is not bytes
                or not isinstance(namespace_root, str) or not namespace_root.startswith("/")):
            raise RuntimeImageError("captured runtime image and absolute namespace root required")
        _relative(namespace_root[1:])
        manifest = _manifest(image.manifest(), limits)
        if (image.manifest_bytes != _canonical(manifest)
                or hashlib.sha256(image.manifest_bytes).hexdigest() != image.digest):
            raise RuntimeImageError("runtime manifest identity changed")
        expected_files = [item for item in manifest["entries"] if item["kind"] == "file"]
        if (not isinstance(image.files, tuple) or len(image.files) != len(expected_files)):
            raise RuntimeImageError("captured runtime file set changed")
        mount_arguments = 4 + sum({"file": 5, "directory": 4, "symlink": 3}[item["kind"]]
                                  for item in manifest["entries"])
        if mount_arguments > MAX_IMAGE_MOUNT_ARGUMENTS:
            raise RuntimeImageError("runtime image exceeds per-file mount argument budget; compact staging required")
        for pair, item in zip(image.files, expected_files, strict=True):
            if (not isinstance(pair, tuple) or len(pair) != 2 or pair[0] != item["path"]
                    or type(pair[1]) is not bytes or len(pair[1]) != item["bytes"]
                    or hashlib.sha256(pair[1]).hexdigest() != item["sha256"]):
                raise RuntimeImageError("captured runtime bytes changed")
        if not hasattr(os, "memfd_create") or not hasattr(fcntl, "F_ADD_SEALS"):
            raise RuntimeImageError("sealed anonymous runtime descriptors required")
        # Do not silently raise a process or host resource limit. Leave space
        # for the caller's pipes/launcher and fail before staging large bytes.
        # Concurrent descriptor allocation may still fail later; cleanup below
        # covers that race. This is a preflight, not a reservation.
        import resource

        soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        if (soft_limit != resource.RLIM_INFINITY
                and len(os.listdir("/proc/self/fd")) + len(expected_files) + 16 > soft_limit):
            raise RuntimeImageError("insufficient caller-owned runtime descriptor budget")
        arguments = ["--perms", "0755", "--dir", namespace_root]
        directories = sorted((item for item in manifest["entries"] if item["kind"] == "directory"),
                             key=lambda item: (item["path"].count("/"), item["path"]))
        for item in directories:
            arguments.extend(("--perms", format(item["mode"], "04o"), "--dir", namespace_root + "/" + item["path"]))
        for (_, content), item in zip(image.files, expected_files, strict=True):
            descriptor = os.memfd_create("code-runtime-image", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            descriptors.append(descriptor)
            remaining = memoryview(content)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise RuntimeImageError("unable to stage complete runtime bytes")
                remaining = remaining[written:]
            os.fchmod(descriptor, item["mode"])
            seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
            fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, seals)
            if fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) != seals:
                raise RuntimeImageError("runtime descriptor is not fully sealed")
            os.lseek(descriptor, 0, os.SEEK_SET)
            arguments.extend(("--perms", format(item["mode"], "04o"), "--ro-bind-data", str(descriptor),
                              namespace_root + "/" + item["path"]))
        for item in manifest["entries"]:
            if item["kind"] == "symlink":
                arguments.extend(("--symlink", item["target"], namespace_root + "/" + item["path"]))
        sealed = SealedRuntimeImage(tuple(arguments), tuple(descriptors), image.digest)
    except (OSError, UnicodeError, TypeError, ValueError, AnalysisInputError) as exc:
        for descriptor in descriptors:
            os.close(descriptor)
        if isinstance(exc, RuntimeImageError):
            raise
        raise RuntimeImageError("unable to seal exact runtime image") from exc
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise
    try:
        yield sealed
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
