"""Small, source-local identity binding shared by parity-aware consumers.

The path is only a lookup coordinate.  Authority comes from the caller's
content-addressed contract and the current Git/source observations.  The
module intentionally has no repository imports so projected command surfaces
can load it without a bootstrap or ``sys.path`` dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any, Mapping


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
        surface = root / relative
        if surface.is_symlink() or not surface.is_file():
            return False
    if any(not (root / relative).is_dir() for relative in SOURCE_REQUIRED_DIRS):
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
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_COUNT": "0",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    try:
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
    if completed.returncode != 0:
        raise SourceIdentityError("Git source identity could not be observed")
    coordinates = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(coordinates) != 2 or not all(_is_git_object_id(item) for item in coordinates):
        raise SourceIdentityError("Git source identity returned malformed HEAD/tree coordinates")
    return coordinates[0], coordinates[1]


def _surface_digests(root: Path, paths: tuple[str, ...]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for raw_path in paths:
        relative = _safe_relative_path(raw_path)
        surface = root / relative
        if surface.is_symlink() or not surface.is_file():
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
    if (root / IDENTITY_HELPER_SURFACE).is_file() and IDENTITY_HELPER_SURFACE not in selected:
        selected.append(IDENTITY_HELPER_SURFACE)
    if surface_paths is None and consumer in {None, "shared"}:
        consumer_surfaces = CONSUMER_SURFACES.values()
    elif surface_paths is None and consumer is not None:
        consumer_surfaces = (CONSUMER_SURFACES[consumer],)
    else:
        consumer_surfaces = ()
    for consumer_surface in consumer_surfaces:
        if (root / consumer_surface).is_file() and consumer_surface not in selected:
            selected.append(consumer_surface)
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
    body = _identity_body(
        normalized_root,
        consumer=consumer,
        surface_paths=surface_paths,
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
    if (
        expected.get("consumer") in {None, "shared", consumer}
        and (normalized_root / CONSUMER_SURFACES[consumer]).is_file()
        and CONSUMER_SURFACES[consumer] not in expected["surface_digests"]
    ):
        raise SourceIdentityError(
            f"source identity omits invoked consumer surface: {CONSUMER_SURFACES[consumer]}"
        )
    if (
        (normalized_root / IDENTITY_HELPER_SURFACE).is_file()
        and IDENTITY_HELPER_SURFACE not in expected["surface_digests"]
    ):
        raise SourceIdentityError(
            f"source identity omits the shared identity helper: {IDENTITY_HELPER_SURFACE}"
        )
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
