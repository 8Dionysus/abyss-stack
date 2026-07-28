#!/usr/bin/env python3
"""Build and publish an exact, public-safe MCP deployment receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "abyss_stack_mcp_deployment_manifest_v1"
DIGEST_SCOPE = "abyss_stack_mcp_deployment_body_v1"
SOURCE_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }
)
IGNORED_FILE_NAMES = frozenset({".coverage"})
IGNORED_FILE_SUFFIXES = frozenset({".pyc"})


class ManifestError(ValueError):
    """Raised when an exact deployment receipt cannot be produced."""


@dataclass(frozen=True)
class TreeIdentity:
    digest: str
    file_count: int
    byte_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "tree_digest": self.digest,
            "file_count": self.file_count,
            "byte_count": self.byte_count,
        }


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _absolute_without_symlink_components(path: Path, label: str) -> Path:
    absolute = path.expanduser().absolute()
    components = tuple(reversed(absolute.parents)) + (absolute,)
    for component in components:
        if component.exists() or component.is_symlink():
            if component.is_symlink():
                raise ManifestError(
                    f"{label} cannot traverse a symlink: {component}"
                )
    return absolute


def _require_directory(path: Path, label: str) -> Path:
    absolute = _absolute_without_symlink_components(path, label)
    if not absolute.is_dir():
        raise ManifestError(f"{label} must be a non-symlink directory: {path}")
    return absolute


def _ignored(relative: Path) -> bool:
    return (
        any(part in IGNORED_DIRECTORY_NAMES for part in relative.parts)
        or relative.name in IGNORED_FILE_NAMES
        or relative.suffix in IGNORED_FILE_SUFFIXES
        or relative.name.endswith(".egg-info")
    )


def tree_identity(root: Path) -> TreeIdentity:
    resolved_root = _require_directory(root, "tree root")
    records: list[dict[str, Any]] = []
    total_bytes = 0

    for directory, directory_names, file_names in os.walk(
        resolved_root,
        topdown=True,
        followlinks=False,
    ):
        current = Path(directory)
        retained_directories: list[str] = []
        for name in sorted(directory_names):
            candidate = current / name
            relative = candidate.relative_to(resolved_root)
            if _ignored(relative):
                continue
            if candidate.is_symlink():
                raise ManifestError(
                    f"deployment trees cannot contain directory symlinks: {relative}"
                )
            if not candidate.is_dir():
                raise ManifestError(
                    f"deployment tree entry is not a directory: {relative}"
                )
            retained_directories.append(name)
        directory_names[:] = retained_directories

        for name in sorted(file_names):
            candidate = current / name
            relative = candidate.relative_to(resolved_root)
            if _ignored(relative):
                continue
            if candidate.is_symlink():
                raise ManifestError(
                    f"deployment trees cannot contain file symlinks: {relative}"
                )
            if not candidate.is_file():
                raise ManifestError(
                    f"deployment tree entry is not a regular file: {relative}"
                )
            metadata = candidate.stat()
            total_bytes += metadata.st_size
            records.append(
                {
                    "path": relative.as_posix(),
                    "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                    "size": metadata.st_size,
                    "sha256": _sha256_file(candidate),
                }
            )

    records.sort(key=lambda item: item["path"])
    return TreeIdentity(
        digest=_sha256_bytes(_canonical_bytes(records)),
        file_count=len(records),
        byte_count=total_bytes,
    )


def _parse_deployed_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ManifestError("--deployed-at must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ManifestError("--deployed-at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_project(path: Path) -> tuple[str, str, dict[str, str]]:
    if path.is_symlink() or not path.is_file():
        raise ManifestError(f"service pyproject must be a regular file: {path}")
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(f"unable to parse service pyproject: {path}") from exc
    project = payload.get("project")
    if not isinstance(project, dict):
        raise ManifestError(f"service pyproject lacks [project]: {path}")
    name = project.get("name")
    version = project.get("version")
    scripts = project.get("scripts", {})
    if not isinstance(name, str) or not name.strip():
        raise ManifestError(f"service package name is missing: {path}")
    if not isinstance(version, str) or not version.strip():
        raise ManifestError(f"service package version is missing: {path}")
    if not isinstance(scripts, dict) or not all(
        isinstance(key, str)
        and key.strip()
        and isinstance(target, str)
        and target.strip()
        for key, target in scripts.items()
    ):
        raise ManifestError(f"service scripts must be a string mapping: {path}")
    return (
        name.strip(),
        version.strip(),
        {key: scripts[key] for key in sorted(scripts)},
    )


def _service_entries(
    source_services: Path,
    deployed_services: Path,
    source_revision: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    service_roots = sorted(
        path.parent
        for path in source_services.glob("*/pyproject.toml")
        if path.is_file() and not path.is_symlink()
    )
    if not service_roots:
        raise ManifestError("no MCP service packages were discovered")

    for source_service in service_roots:
        service_id = source_service.name
        deployed_service = deployed_services / service_id
        _require_directory(deployed_service, f"deployed service {service_id}")
        source_identity = tree_identity(source_service)
        deployed_identity = tree_identity(deployed_service)
        if source_identity != deployed_identity:
            raise ManifestError(
                f"MCP service deployment drift: {service_id}: "
                f"source={source_identity.digest} "
                f"deployed={deployed_identity.digest}"
            )
        package_name, package_version, entrypoints = _load_project(
            source_service / "pyproject.toml"
        )
        deployed_name, deployed_version, deployed_entrypoints = _load_project(
            deployed_service / "pyproject.toml"
        )
        if (
            package_name,
            package_version,
            entrypoints,
        ) != (
            deployed_name,
            deployed_version,
            deployed_entrypoints,
        ):
            raise ManifestError(
                f"MCP package metadata drift after deployment: {service_id}"
            )
        lock_path = source_service / "requirements.lock"
        lock_digest = (
            _sha256_file(lock_path)
            if lock_path.is_file() and not lock_path.is_symlink()
            else None
        )
        entries.append(
            {
                "service_id": service_id,
                "package_name": package_name,
                "package_version": package_version,
                "package_source_revision": source_revision,
                "package_artifact_kind": "source_projection",
                "package_digest": source_identity.digest,
                "dependency_lock_digest": lock_digest,
                "server_entrypoints": entrypoints,
                "source_path": f"mcp/services/{service_id}",
                "deployed_path": f"Configs/mcp/services/{service_id}",
                "source_tree": source_identity.as_dict(),
                "deployed_tree": deployed_identity.as_dict(),
                "parity_state": "exact",
            }
        )
    return entries


def build_manifest(
    *,
    source_root: Path,
    deployed_root: Path,
    source_revision: str,
    deployed_at: datetime,
    delete_mode: bool,
) -> dict[str, Any]:
    source_root = _require_directory(source_root, "source root")
    deployed_root = _require_directory(deployed_root, "deployed Configs root")
    if SOURCE_REVISION_PATTERN.fullmatch(source_revision) is None:
        raise ManifestError("source revision must be one exact lowercase Git SHA")

    source_services = _require_directory(
        source_root / "mcp" / "services",
        "source MCP services root",
    )
    deployed_services = _require_directory(
        deployed_root / "mcp" / "services",
        "deployed MCP services root",
    )
    source_tree = tree_identity(source_services)
    deployed_tree = tree_identity(deployed_services)
    if source_tree != deployed_tree:
        raise ManifestError(
            "MCP services projection is not exact: "
            f"source={source_tree.digest} deployed={deployed_tree.digest}"
        )

    body = {
        "schema_version": SCHEMA_VERSION,
        "digest_scope": DIGEST_SCOPE,
        "provider": "abyss-stack",
        "deployed_at": _timestamp(deployed_at),
        "contains_secrets": False,
        "source": {
            "owner": "abyss-stack",
            "revision": source_revision,
            "path": "mcp/services",
            **source_tree.as_dict(),
        },
        "deployment": {
            "runtime_owner": "abyss-stack",
            "path": "Configs/mcp/services",
            "sync_delete_mode": delete_mode,
            **deployed_tree.as_dict(),
        },
        "services": _service_entries(
            source_services,
            deployed_services,
            source_revision,
        ),
        "parity_state": "exact",
        "runtime_observation_state": "not_observed",
        "claim_limit": (
            "This receipt proves exact source-to-Configs MCP package bytes for "
            "one clean source revision. It does not prove a process, endpoint, "
            "registry entry, consumer schema, live call, grounded result, "
            "owner acceptance, admission, or rollback."
        ),
    }
    manifest_id = _sha256_bytes(_canonical_bytes(body))
    record_name = manifest_id.removeprefix("sha256:") + ".json"
    return {
        **body,
        "manifest_id": manifest_id,
        "record_ref": f"Logs/mcp/deployments/records/{record_name}",
        "latest_ref": "Logs/mcp/deployments/latest.json",
    }


def verify_git_source_snapshot(
    source_root: Path,
    source_revision: str,
) -> None:
    source_root = _require_directory(source_root, "source root")
    if SOURCE_REVISION_PATTERN.fullmatch(source_revision) is None:
        raise ManifestError("source revision must be one exact lowercase Git SHA")

    def git_output(*arguments: str) -> str:
        try:
            completed = subprocess.run(
                ("git", "-C", str(source_root), *arguments),
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise ManifestError("git is required for source verification") from exc
        if completed.returncode != 0:
            raise ManifestError(
                "unable to verify the Git source snapshot"
            )
        return completed.stdout.strip()

    observed_revision = git_output("rev-parse", "--verify", "HEAD")
    if observed_revision != source_revision:
        raise ManifestError(
            "Git source revision changed during deployment manifest creation"
        )
    if git_output(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ):
        raise ManifestError(
            "Git source worktree changed during deployment manifest creation"
        )


def verify_manifest_id(payload: dict[str, Any]) -> None:
    unsigned = {
        key: value
        for key, value in payload.items()
        if key not in {"manifest_id", "record_ref", "latest_ref"}
    }
    expected = _sha256_bytes(_canonical_bytes(unsigned))
    if payload.get("manifest_id") != expected:
        raise ManifestError("deployment manifest content address is invalid")
    expected_record = (
        "Logs/mcp/deployments/records/"
        + expected.removeprefix("sha256:")
        + ".json"
    )
    if payload.get("record_ref") != expected_record:
        raise ManifestError("deployment manifest record_ref is invalid")
    if payload.get("latest_ref") != "Logs/mcp/deployments/latest.json":
        raise ManifestError("deployment manifest latest_ref is invalid")


def _write_atomic(path: Path, content: bytes, mode: int) -> None:
    parent = _absolute_without_symlink_components(
        path.parent,
        "manifest parent",
    )
    parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    _require_directory(parent, "manifest parent")
    path = parent / path.name
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise ManifestError(f"manifest target must be a regular file: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def publish_manifest(payload: dict[str, Any], output_root: Path) -> tuple[Path, Path]:
    verify_manifest_id(payload)
    output_root = _absolute_without_symlink_components(
        output_root,
        "manifest output root",
    )
    if output_root.exists():
        _require_directory(output_root, "manifest output root")
    else:
        output_root.mkdir(parents=True, mode=0o750)
        _require_directory(output_root, "manifest output root")
    records = output_root / "records"
    records.mkdir(mode=0o750, exist_ok=True)
    _require_directory(records, "manifest record root")

    content = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    record = records / Path(str(payload["record_ref"])).name
    if record.exists():
        if record.is_symlink() or not record.is_file():
            raise ManifestError("existing deployment record is not a regular file")
        if record.read_bytes() != content:
            raise ManifestError("content-addressed deployment record conflicts")
    else:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(record, flags, 0o640)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            record.unlink(missing_ok=True)
            raise

    latest = output_root / "latest.json"
    _write_atomic(latest, content, 0o640)
    return record, latest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--deployed-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--deployed-at")
    parser.add_argument("--delete-mode", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        verify_git_source_snapshot(
            args.source_root,
            args.source_revision,
        )
        payload = build_manifest(
            source_root=args.source_root,
            deployed_root=args.deployed_root,
            source_revision=args.source_revision,
            deployed_at=_parse_deployed_at(args.deployed_at),
            delete_mode=args.delete_mode,
        )
        verify_git_source_snapshot(
            args.source_root,
            args.source_revision,
        )
        verify_manifest_id(payload)
        if args.check_only:
            result = {
                "manifest_id": payload["manifest_id"],
                "parity_state": payload["parity_state"],
                "published": False,
                "service_count": len(payload["services"]),
            }
        else:
            record, latest = publish_manifest(payload, args.output_root)
            result = {
                "manifest_id": payload["manifest_id"],
                "parity_state": payload["parity_state"],
                "published": True,
                "record_path": str(record),
                "latest_path": str(latest),
                "service_count": len(payload["services"]),
            }
    except (ManifestError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
