"""Small, source-local identity binding shared by parity-aware consumers.

The path is only a lookup coordinate.  Authority comes from the caller's
content-addressed contract and the current Git/source observations.  The
module intentionally has no repository imports so projected command surfaces
can load it without a bootstrap or ``sys.path`` dependency.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
from typing import Any, Iterator, Mapping


SCHEMA_VERSION = "abyss_stack_source_identity_v1"
TARGET_ID = "abyss-stack"
SOURCE_IDENTITY_ENV = "AOA_SOURCE_IDENTITY"
SOURCE_README_TITLE = "# abyss-stack"
SOURCE_AGENTS_OWNER_LINE = "Root route card for `abyss-stack`."
SOURCE_AGENTS_SCAN_LINES = 8
IDENTITY_HELPER_SURFACE = "scripts/abyss_stack_source_identity.py"

SHAPE_SURFACES = (
    "AGENTS.md",
    "README.md",
    "CONTRIBUTING.md",
    "scripts/validate_stack.py",
    "docs/install/DEPLOYMENT.md",
)
SOURCE_REQUIRED_DIRS = ("mechanics",)
CONSUMER_SURFACES = {
    "diagnose": "mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py",
    "autonomy-status": "mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py",
    "governed-runner": "mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
}
GIT_SAFE_ENVIRONMENT = {
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_CONFIG_COUNT": "0",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
}
DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
FILE_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


class SourceIdentityError(ValueError):
    """The selected source cannot be bound to the supplied identity."""


class SourceIdentityBinding:
    """Captured source identity and filesystem coordinates for one consumer."""

    __slots__ = ("root", "identity", "device", "inode", "consumer")

    def __init__(
        self,
        *,
        root: Path,
        identity: dict[str, Any],
        device: int,
        inode: int,
        consumer: str,
    ) -> None:
        self.root = root
        self.identity = identity
        self.device = device
        self.inode = inode
        self.consumer = consumer


class SourceSurfaceUse:
    """Descriptor-bound source surface and the directory it belongs to."""

    __slots__ = ("path", "root_path", "pass_fds")

    def __init__(self, *, path: Path, root_path: Path, pass_fds: tuple[int, ...]) -> None:
        self.path = path
        self.root_path = root_path
        self.pass_fds = pass_fds


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == len("sha256:") + 64
        and all(char in "0123456789abcdef" for char in value[len("sha256:") :])
    )


def _is_git_object_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(char in "0123456789abcdef" for char in value)
    )


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceIdentityError("source identity surface path must be non-empty")
    if "\\" in value:
        raise SourceIdentityError("source identity surface path must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise SourceIdentityError(f"unsafe source identity surface path: {value!r}")
    return path.as_posix()


def sanitized_git_environment(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return Git configuration bound to the selected checkout, not the caller."""

    cleaned = dict(os.environ if environment is None else environment)
    for key in tuple(cleaned):
        if key.startswith("GIT_"):
            del cleaned[key]
    cleaned.update(GIT_SAFE_ENVIRONMENT)
    return cleaned


def normalize_root(path: str | Path) -> tuple[Path, os.stat_result]:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        resolved = candidate.resolve(strict=True)
        stat_result = resolved.stat()
    except (OSError, RuntimeError) as exc:
        raise SourceIdentityError(f"source root is not a readable directory: {candidate}") from exc
    if not resolved.is_dir():
        raise SourceIdentityError(f"source root is not a directory: {resolved}")
    return resolved, stat_result


def source_shape(path: str | Path) -> bool:
    try:
        root, _stat_result = normalize_root(path)
    except SourceIdentityError:
        return False
    for relative in SHAPE_SURFACES:
        try:
            surface = _surface_path(root, relative)
        except SourceIdentityError:
            return False
        if not surface.is_file():
            return False
    for relative in SOURCE_REQUIRED_DIRS:
        try:
            required_dir = _surface_path(root, relative)
        except SourceIdentityError:
            return False
        if not required_dir.is_dir():
            return False
    try:
        with (root / "README.md").open(encoding="utf-8") as readme_file:
            readme_title = next(
                (line.strip() for line in readme_file if line.strip()),
                None,
            )
        with (root / "AGENTS.md").open(encoding="utf-8") as agents_file:
            agents_owner_line = any(
                line.rstrip("\r\n") == SOURCE_AGENTS_OWNER_LINE
                for line in list(agents_file)[:SOURCE_AGENTS_SCAN_LINES]
            )
    except (OSError, UnicodeError):
        return False
    return readme_title == SOURCE_README_TITLE and agents_owner_line


def _git_coordinates(root: Path) -> tuple[str, str]:
    git_marker = root / ".git"
    if git_marker.is_symlink() or not (git_marker.is_dir() or git_marker.is_file()):
        raise SourceIdentityError("selected source root must contain local Git metadata")
    environment = sanitized_git_environment()
    try:
        top_level = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
            env=environment,
            text=True,
            timeout=5.0,
        )
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD^{commit}", "HEAD^{tree}"],
            capture_output=True,
            check=False,
            env=environment,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceIdentityError("Git source identity could not be observed") from exc
    if top_level.returncode != 0 or completed.returncode != 0:
        raise SourceIdentityError("Git source identity could not be observed")
    observed_top_level = top_level.stdout.strip()
    try:
        if not observed_top_level or Path(observed_top_level).resolve(strict=True) != root:
            raise SourceIdentityError("Git discovery escaped the selected source root")
    except (OSError, RuntimeError) as exc:
        raise SourceIdentityError("Git source root could not be resolved") from exc
    coordinates = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(coordinates) != 2 or not all(_is_git_object_id(item) for item in coordinates):
        raise SourceIdentityError("Git source identity returned malformed HEAD/tree coordinates")
    return coordinates[0], coordinates[1]


def _surface_path(root: Path, raw_path: str) -> Path:
    relative = _safe_relative_path(raw_path)
    current = root
    for component in PurePosixPath(relative).parts:
        current = current / component
        if current.is_symlink():
            raise SourceIdentityError(f"source identity surface has a symlinked path component: {relative}")
    return current


def _required_surfaces(consumer: str | None) -> tuple[str, ...]:
    if consumer is not None and consumer != "shared" and consumer not in CONSUMER_SURFACES:
        raise SourceIdentityError(f"unknown source identity consumer: {consumer}")
    if consumer in {None, "shared"}:
        return (IDENTITY_HELPER_SURFACE, *CONSUMER_SURFACES.values())
    return (IDENTITY_HELPER_SURFACE, CONSUMER_SURFACES[consumer])


def _require_surfaces(root: Path, consumer: str | None) -> None:
    for relative in _required_surfaces(consumer):
        surface = _surface_path(root, relative)
        if not surface.is_file():
            raise SourceIdentityError(f"source identity requires invoked surface: {relative}")


def _surface_digests(root: Path, paths: tuple[str, ...]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for raw_path in paths:
        relative = _safe_relative_path(raw_path)
        surface = _surface_path(root, relative)
        if not surface.is_file():
            raise SourceIdentityError(f"source identity surface is missing or symlinked: {relative}")
        try:
            digests[relative] = _sha256_bytes(surface.read_bytes())
        except (OSError, UnicodeError) as exc:
            raise SourceIdentityError(f"source identity surface could not be read: {relative}") from exc
    return dict(sorted(digests.items()))


def _identity_body(
    root: Path,
    *,
    consumer: str | None,
    surface_paths: tuple[str, ...] | None,
) -> dict[str, Any]:
    if consumer is not None and consumer != "shared" and consumer not in CONSUMER_SURFACES:
        raise SourceIdentityError(f"unknown source identity consumer: {consumer}")
    selected = list(surface_paths or SHAPE_SURFACES)
    if surface_paths is None:
        for required in _required_surfaces(consumer):
            if required not in selected:
                selected.append(required)
    normalized_paths = tuple(dict.fromkeys(_safe_relative_path(path) for path in selected))
    head, tree = _git_coordinates(root)
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "target_id": TARGET_ID,
        "head": head,
        "tree": tree,
        "surface_digests": _surface_digests(root, normalized_paths),
    }
    if consumer is not None:
        body["consumer"] = consumer
    return body


def make_source_identity(
    root: str | Path,
    *,
    consumer: str | None = None,
    surface_paths: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    normalized_root, _stat_result = normalize_root(root)
    if not source_shape(normalized_root):
        raise SourceIdentityError(f"source root does not match the owner shape: {normalized_root}")
    _require_surfaces(normalized_root, consumer)
    identity_surface_paths = surface_paths
    if surface_paths is not None:
        identity_surface_paths = tuple(
            dict.fromkeys((*surface_paths, *_required_surfaces(consumer)))
        )
    body = _identity_body(
        normalized_root,
        consumer=consumer,
        surface_paths=identity_surface_paths,
    )
    return {**body, "identity_digest": _sha256_bytes(_canonical_bytes(body))}


def _validate_contract_shape(identity: Mapping[str, Any], *, consumer: str) -> dict[str, Any]:
    if consumer not in CONSUMER_SURFACES:
        raise SourceIdentityError(f"unknown invoked source identity consumer: {consumer}")
    if identity.get("schema_version") != SCHEMA_VERSION:
        raise SourceIdentityError("source identity schema version is unsupported")
    if identity.get("target_id") != TARGET_ID:
        raise SourceIdentityError("source identity target_id is not abyss-stack")
    contract_consumer = identity.get("consumer")
    if contract_consumer not in {None, "shared", consumer}:
        raise SourceIdentityError("source identity consumer does not match the invoked mechanic")
    contract_scope = contract_consumer if contract_consumer in {None, "shared"} else consumer
    if not _is_git_object_id(identity.get("head")) or not _is_git_object_id(identity.get("tree")):
        raise SourceIdentityError("source identity requires exact lowercase Git HEAD and tree IDs")
    surface_digests = identity.get("surface_digests")
    if not isinstance(surface_digests, dict) or not surface_digests:
        raise SourceIdentityError("source identity requires selected surface digests")
    normalized_surfaces: dict[str, str] = {}
    for raw_path, digest in surface_digests.items():
        relative = _safe_relative_path(raw_path)
        if not _is_sha256(digest):
            raise SourceIdentityError(f"source identity digest is malformed for {relative}")
        normalized_surfaces[relative] = digest
    for required in SHAPE_SURFACES:
        if required not in normalized_surfaces:
            raise SourceIdentityError(f"source identity omits required surface: {required}")
    for required in _required_surfaces(contract_scope):
        if required not in normalized_surfaces:
            raise SourceIdentityError(f"source identity omits required invoked surface: {required}")
    body = {
        "schema_version": SCHEMA_VERSION,
        "target_id": TARGET_ID,
        "head": identity["head"],
        "tree": identity["tree"],
        "surface_digests": dict(sorted(normalized_surfaces.items())),
    }
    if contract_consumer is not None:
        body["consumer"] = contract_consumer
    if identity.get("identity_digest") != _sha256_bytes(_canonical_bytes(body)):
        raise SourceIdentityError("source identity content seal is invalid")
    return {**body, "identity_digest": identity["identity_digest"]}


def verify_source_identity(
    root: str | Path,
    identity: Mapping[str, Any],
    *,
    consumer: str,
) -> tuple[Path, os.stat_result, dict[str, Any]]:
    normalized_root, stat_result = normalize_root(root)
    if not source_shape(normalized_root):
        raise SourceIdentityError(f"source root does not match the owner shape: {normalized_root}")
    expected = _validate_contract_shape(identity, consumer=consumer)
    contract_scope = expected.get("consumer") if expected.get("consumer") in {None, "shared"} else consumer
    _require_surfaces(normalized_root, contract_scope)
    observed = _identity_body(
        normalized_root,
        consumer=None,
        surface_paths=tuple(expected["surface_digests"]),
    )
    observed_body = dict(observed)
    if "consumer" in expected:
        observed_body["consumer"] = expected["consumer"]
    expected_body = {
        key: value
        for key, value in expected.items()
        if key != "identity_digest"
    }
    if observed_body != expected_body:
        raise SourceIdentityError(
            f"source identity mismatch for {consumer}: expected {expected['head']}/{expected['tree']}"
        )
    return normalized_root, stat_result, expected


def bind_source_root(
    root: str | Path,
    *,
    consumer: str,
    expected_identity: Mapping[str, Any] | None = None,
    current_root: str | Path | None = None,
    allow_source_local: bool = False,
) -> SourceIdentityBinding:
    normalized_root, stat_result = normalize_root(root)
    identity = expected_identity
    if identity is None and allow_source_local and current_root is not None:
        current_normalized, _current_stat = normalize_root(current_root)
        if normalized_root != current_normalized:
            raise SourceIdentityError("foreign source root requires an explicit source identity contract")
        identity = make_source_identity(normalized_root, consumer=consumer)
    if identity is None:
        raise SourceIdentityError("source root requires an explicit source identity contract")
    verified_root, verified_stat, verified_identity = verify_source_identity(
        normalized_root,
        identity,
        consumer=consumer,
    )
    return SourceIdentityBinding(
        root=verified_root,
        identity=verified_identity,
        device=verified_stat.st_dev,
        inode=verified_stat.st_ino,
        consumer=consumer,
    )


def revalidate_source_binding(binding: SourceIdentityBinding) -> Path:
    normalized_root, stat_result, _identity = verify_source_identity(
        binding.root,
        binding.identity,
        consumer=binding.consumer,
    )
    if (
        normalized_root != binding.root
        or stat_result.st_dev != binding.device
        or stat_result.st_ino != binding.inode
    ):
        raise SourceIdentityError("source root path identity changed during use")
    return normalized_root


def _open_pinned_root(binding: SourceIdentityBinding) -> int:
    root_fd: int | None = None
    try:
        root_fd = os.open(binding.root, DIRECTORY_OPEN_FLAGS)
        stat_result = os.fstat(root_fd)
    except OSError as exc:
        if root_fd is not None:
            os.close(root_fd)
        raise SourceIdentityError("source root could not be opened without following symlinks") from exc
    if (
        stat_result.st_dev != binding.device
        or stat_result.st_ino != binding.inode
        or not stat.S_ISDIR(stat_result.st_mode)
    ):
        os.close(root_fd)
        raise SourceIdentityError("source root descriptor identity changed during use")
    return root_fd


def _fd_path(fd: int) -> Path:
    for prefix in (Path("/proc/self/fd"), Path("/dev/fd")):
        candidate = prefix / str(fd)
        if candidate.exists():
            return candidate
    raise SourceIdentityError("descriptor-bound source use requires an fd path")


def _open_relative_fd(root_fd: int, relative: str) -> int:
    parts = PurePosixPath(_safe_relative_path(relative)).parts
    current_fd = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            next_fd = os.open(component, DIRECTORY_OPEN_FLAGS, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return os.open(parts[-1], FILE_OPEN_FLAGS, dir_fd=current_fd)
    except OSError as exc:
        raise SourceIdentityError(f"source identity surface could not be opened: {relative}") from exc
    finally:
        os.close(current_fd)


@contextmanager
def pinned_source_root(
    binding: SourceIdentityBinding,
    *,
    verify_before: bool = True,
    verify_after: bool = True,
) -> Iterator[Path]:
    """Pin the selected root as the process cwd for path-based Git helpers."""

    root_fd = _open_pinned_root(binding)
    try:
        previous_fd = os.open(".", DIRECTORY_OPEN_FLAGS)
    except OSError as exc:
        os.close(root_fd)
        raise SourceIdentityError("current directory could not be pinned") from exc
    try:
        if verify_before:
            revalidate_source_binding(binding)
        os.fchdir(root_fd)
        yield binding.root
        if verify_after:
            revalidate_source_binding(binding)
    finally:
        try:
            os.fchdir(previous_fd)
        finally:
            os.close(previous_fd)
            os.close(root_fd)


@contextmanager
def open_bound_surface(binding: SourceIdentityBinding, relative: str) -> Iterator[SourceSurfaceUse]:
    """Open a sealed source file before use and expose only its inherited fd path."""

    normalized = _safe_relative_path(relative)
    expected_digest = (binding.identity.get("surface_digests") or {}).get(normalized)
    if not _is_sha256(expected_digest):
        raise SourceIdentityError(f"source identity does not seal the requested surface: {normalized}")
    root_fd = _open_pinned_root(binding)
    surface_fd: int | None = None
    try:
        revalidate_source_binding(binding)
        surface_fd = _open_relative_fd(root_fd, normalized)
        surface_stat = os.fstat(surface_fd)
        if not stat.S_ISREG(surface_stat.st_mode):
            raise SourceIdentityError(f"source identity surface is not a regular file: {normalized}")
        with os.fdopen(os.dup(surface_fd), "rb") as surface_file:
            observed_digest = _sha256_bytes(surface_file.read())
        if observed_digest != expected_digest:
            raise SourceIdentityError(f"source identity surface changed before use: {normalized}")
        yield SourceSurfaceUse(
            path=_fd_path(surface_fd),
            root_path=_fd_path(root_fd),
            pass_fds=(root_fd, surface_fd),
        )
        revalidate_source_binding(binding)
    finally:
        if surface_fd is not None:
            os.close(surface_fd)
        os.close(root_fd)


def load_source_identity(reference: str | Path) -> dict[str, Any]:
    path = Path(reference).expanduser()
    if not path.is_absolute():
        raise SourceIdentityError("AOA_SOURCE_IDENTITY must be an absolute receipt path")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceIdentityError("AOA_SOURCE_IDENTITY could not be read as JSON") from exc
    if not isinstance(payload, dict):
        raise SourceIdentityError("AOA_SOURCE_IDENTITY must contain a JSON object")
    return payload


def load_environment_identity() -> dict[str, Any] | None:
    reference = os.environ.get(SOURCE_IDENTITY_ENV)
    if not reference:
        return None
    return load_source_identity(reference)
