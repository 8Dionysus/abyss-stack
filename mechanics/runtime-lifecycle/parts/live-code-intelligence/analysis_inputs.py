"""Bounded, immutable input capture for external code-analysis providers.

This module captures bytes, not admission or normalized observation meaning.
A caller chooses the source/dependency view explicitly. Two complete reads
must agree before a capture may leave this boundary; a later provider consumes
the captured bytes, never a freshly reopened mutable working tree.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Iterator


SCHEMA = "abyss-stack-analysis-input-tree-v1"
_CHUNK_BYTES = 64 * 1024


class AnalysisInputError(ValueError):
    """The declared analysis view cannot be captured exactly within its bounds."""


@dataclass(frozen=True)
class CaptureLimits:
    max_files: int = 12_000
    max_entries: int = 30_000
    max_file_bytes: int = 16 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_depth: int = 64

    def __post_init__(self) -> None:
        for value in vars(self).values():
            if type(value) is not int or value <= 0:
                raise AnalysisInputError("capture limits must be positive integers")
        if self.max_file_bytes > self.max_total_bytes:
            raise AnalysisInputError("per-file limit exceeds total limit")


@dataclass(frozen=True)
class CapturedFile:
    path: str
    content: bytes
    sha256: str


@dataclass(frozen=True)
class CapturedTree:
    root: str
    suffixes: tuple[str, ...] | None
    excluded_names: tuple[str, ...]
    directories: tuple[str, ...]
    files: tuple[CapturedFile, ...]
    digest: str

    @property
    def sources(self) -> dict[str, bytes]:
        return {item.path: item.content for item in self.files}

    def identity(self) -> dict:
        # Return a fresh read model, not a mutable alias into the capture.
        return {
            "schema": SCHEMA, "digest": self.digest, "root": self.root,
            "coverage": "declared_input_view_only",
            "selection": {"suffixes": list(self.suffixes) if self.suffixes is not None else None,
                          "excluded_names": list(self.excluded_names)},
            "directories": list(self.directories),
            "files": [{"path": item.path, "sha256": item.sha256, "bytes": len(item.content)}
                      for item in self.files],
            "claim_limit": "Captured bytes only; not whole-repository completeness, dependency correctness, admission, freshness after capture or proof.",
        }


@dataclass(frozen=True)
class SealedInputTree:
    """Input-only bubblewrap arguments, valid only inside ``seal_tree``.

    These do not form a sandbox or authorize a provider launch. The caller
    still owns MACHINE admission, the complete command/environment/runtime
    binding, namespace isolation, output bounds and lifecycle.
    """

    arguments: tuple[str, ...]
    pass_fds: tuple[int, ...]
    digest: str


def _canonical_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _name(value: object) -> str:
    if (not isinstance(value, str) or not value or value in {".", ".."}
            or any(char in value for char in ("/", "\\", "\x00", ":"))):
        raise AnalysisInputError("input entry name must be canonical")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise AnalysisInputError("input entry name must be UTF-8") from exc
    return value


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _directory(path: Path) -> Iterator[int]:
    if not path.is_absolute() or ".." in path.parts:
        raise AnalysisInputError("input root must be an absolute non-traversing path")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise AnalysisInputError("descriptor-relative no-follow capture is required")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in path.parts[1:]:
            _name(component)
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _capture_pass(
    descriptor: int, *, suffixes: tuple[str, ...] | None, excluded: tuple[str, ...],
    limits: CaptureLimits, keep_bytes: bool,
) -> tuple[tuple[CapturedFile, ...], tuple[str, ...], tuple, int]:
    files: list[CapturedFile] = []
    directories: list[str] = []
    signatures: list[tuple] = []
    entry_count = total_bytes = file_count = 0

    def visit(directory: int, prefix: tuple[str, ...]) -> None:
        nonlocal entry_count, total_bytes, file_count
        if len(prefix) > limits.max_depth:
            raise AnalysisInputError("input directory depth exceeds limit")
        before = os.fstat(directory)
        names: list[str] = []
        with os.scandir(directory) as entries:
            for entry in entries:
                entry_count += 1
                if entry_count > limits.max_entries:
                    raise AnalysisInputError("input entry count exceeds limit")
                if entry.name not in excluded:
                    names.append(_name(entry.name))
        for name in sorted(names):
            relative_parts = (*prefix, name)
            relative = "/".join(relative_parts)
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=directory)
                try:
                    if _signature(os.fstat(child)) != _signature(info):
                        raise AnalysisInputError("input directory changed while opening")
                    directories.append(relative)
                    visit(child, relative_parts)
                finally:
                    os.close(child)
                continue
            if not stat.S_ISREG(info.st_mode):
                raise AnalysisInputError("input view contains a symlink or special file")
            if suffixes is not None and not name.endswith(suffixes):
                continue
            file_count += 1
            if file_count > limits.max_files or info.st_size > limits.max_file_bytes:
                raise AnalysisInputError("input file count or size exceeds limit")
            if total_bytes + info.st_size > limits.max_total_bytes:
                raise AnalysisInputError("input total bytes exceed limit")
            opened = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                             dir_fd=directory)
            try:
                if not stat.S_ISREG(os.fstat(opened).st_mode) or _signature(os.fstat(opened)) != _signature(info):
                    raise AnalysisInputError("input file changed while opening")
                digest = hashlib.sha256()
                chunks: list[bytes] = []
                size = 0
                while chunk := os.read(opened, min(_CHUNK_BYTES, limits.max_file_bytes - size + 1)):
                    size += len(chunk)
                    if size > limits.max_file_bytes or total_bytes + size > limits.max_total_bytes:
                        raise AnalysisInputError("input bytes grew beyond limit")
                    digest.update(chunk)
                    if keep_bytes:
                        chunks.append(chunk)
                if size != info.st_size or _signature(os.fstat(opened)) != _signature(info):
                    raise AnalysisInputError("input file changed while reading")
                total_bytes += size
                signatures.append((relative, _signature(info), digest.hexdigest()))
                files.append(CapturedFile(relative, b"".join(chunks), digest.hexdigest()))
            finally:
                os.close(opened)
        after = os.fstat(directory)
        if _signature(before) != _signature(after):
            raise AnalysisInputError("input directory changed while scanning")
        signatures.append(("/".join(prefix) + "/", _signature(after)))

    visit(descriptor, ())
    return (tuple(sorted(files, key=lambda item: item.path)), tuple(sorted(directories)),
            tuple(sorted(signatures)), total_bytes)


def capture_tree(
    root: str | Path, *, suffixes: tuple[str, ...] | None = None,
    excluded_names: tuple[str, ...] = (), limits: CaptureLimits = CaptureLimits(),
    require_utf8: bool = False,
) -> CapturedTree:
    """Capture the entire declared view; no implicit Git ignores or pip lookup.

    Dependencies should use suffixes=None so metadata and package data stay
    bound as well. An empty dependency tree is meaningful only when that exact
    empty root is the intended resolver input, never a replacement for unknown.
    Directory and content identities are checked again after capture. This
    detects observed drift, not an atomic filesystem-wide snapshot against a
    hostile concurrent writer. Provider launch must use only captured bytes.
    """
    if type(require_utf8) is not bool or not isinstance(limits, CaptureLimits):
        raise AnalysisInputError("invalid capture configuration")
    if not isinstance(excluded_names, tuple):
        raise AnalysisInputError("excluded names must be an explicit tuple")
    excluded = tuple(sorted({_name(name) for name in excluded_names}))
    if suffixes is not None:
        if (not isinstance(suffixes, tuple) or not suffixes
                or any(not isinstance(item, str) or not item.startswith(".")
                       or item == "." or any(char in item for char in "/\\\x00:") for item in suffixes)):
            raise AnalysisInputError("suffixes must be an explicit nonempty extension tuple")
        suffixes = tuple(sorted(set(suffixes)))
    try:
        if not isinstance(root, (str, Path)):
            raise AnalysisInputError("input root must be an absolute path")
        path = Path(root)
        with _directory(path) as descriptor:
            root_identity = _signature(os.fstat(descriptor))
            first = _capture_pass(descriptor, suffixes=suffixes, excluded=excluded,
                                  limits=limits, keep_bytes=True)
            second = _capture_pass(descriptor, suffixes=suffixes, excluded=excluded,
                                   limits=limits, keep_bytes=False)
            if first[1:] != second[1:]:
                raise AnalysisInputError("input view changed between complete reads")
            with _directory(path) as current:
                if _signature(os.fstat(current)) != root_identity:
                    raise AnalysisInputError("input root changed during capture")
        files, directories, _, _ = first
        if require_utf8:
            for item in files:
                item.content.decode("utf-8")
        digest = _canonical_digest({
            "schema": SCHEMA, "suffixes": suffixes, "excluded_names": excluded,
            "directories": directories,
            "files": [(item.path, item.sha256, len(item.content)) for item in files],
        })
        return CapturedTree(str(path), suffixes, excluded, directories, files, digest)
    except AnalysisInputError:
        raise
    except (OSError, UnicodeError) as exc:
        raise AnalysisInputError("unable to capture exact input view") from exc


@contextmanager
def seal_tree(tree: CapturedTree, *, namespace_root: str) -> Iterator[SealedInputTree]:
    """Stage captured bytes as sealed anonymous files, without rereading disk.

    The launch owner may pass the descriptors through to bubblewrap's
    ``--ro-bind-data``. No mutable host directory is mounted by this helper.
    Descriptor exhaustion, unsupported sealing and partial writes fail closed
    and close every descriptor already allocated. No provider is executed.
    """
    import fcntl

    def components(path: str) -> tuple[str, ...]:
        if not isinstance(path, str):
            raise AnalysisInputError("sealed input path must be canonical")
        return tuple(_name(part) for part in path.split("/"))

    if (not isinstance(tree, CapturedTree) or not isinstance(namespace_root, str)
            or not namespace_root.startswith("/") or namespace_root == "/"):
        raise AnalysisInputError("sealed input tree requires an explicit namespace root")
    components(namespace_root[1:])
    if not hasattr(os, "memfd_create") or not hasattr(fcntl, "F_ADD_SEALS"):
        raise AnalysisInputError("sealed anonymous input descriptors are required")
    paths: set[str] = set()
    directories = set(tree.directories)
    if len(directories) != len(tree.directories):
        raise AnalysisInputError("duplicate captured directory")
    for path in (*tree.directories, *(item.path for item in tree.files)):
        parts = components(path)
        if path in paths or any("/".join(parts[:i]) not in directories
                                for i in range(1, len(parts))):
            raise AnalysisInputError("captured input paths conflict or omit a parent")
        paths.add(path)
    for item in tree.files:
        if type(item.content) is not bytes or hashlib.sha256(item.content).hexdigest() != item.sha256:
            raise AnalysisInputError("captured input content identity changed")
    if (tuple(sorted(tree.directories)) != tree.directories
            or tuple(sorted(tree.files, key=lambda item: item.path)) != tree.files
            or _canonical_digest({
                "schema": SCHEMA, "suffixes": tree.suffixes, "excluded_names": tree.excluded_names,
                "directories": tree.directories,
                "files": [(item.path, item.sha256, len(item.content)) for item in tree.files],
            }) != tree.digest):
        raise AnalysisInputError("captured input manifest identity changed")
    descriptors: list[int] = []
    arguments = ["--dir", namespace_root]
    try:
        for path in sorted(tree.directories, key=lambda path: (path.count("/"), path)):
            arguments.extend(("--dir", namespace_root + "/" + path))
        for item in tree.files:
            descriptor = os.memfd_create("code-analysis-input", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            descriptors.append(descriptor)
            remaining = memoryview(item.content)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise AnalysisInputError("unable to stage complete captured input")
                remaining = remaining[written:]
            os.lseek(descriptor, 0, os.SEEK_SET)
            seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
            fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, seals)
            if fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) != seals:
                raise AnalysisInputError("captured input descriptor is not fully sealed")
            arguments.extend(("--ro-bind-data", str(descriptor), namespace_root + "/" + item.path))
    except OSError as exc:
        for descriptor in descriptors:
            os.close(descriptor)
        descriptors.clear()
        raise AnalysisInputError("unable to seal exact captured inputs") from exc
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise
    try:
        yield SealedInputTree(tuple(arguments), tuple(descriptors), tree.digest)
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
