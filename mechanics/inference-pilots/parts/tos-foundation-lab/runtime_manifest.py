#!/usr/bin/env python3
"""Verify exact, removable host-managed runtimes admitted to the ToS lab."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


PART_ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = PART_ROOT / "schemas/runtime-manifest.schema.json"
RUNTIME_OWNER_ROOT = Path("/srv/abyss-machine/runtimes/tree-of-sophia-foundation-lab")
MANIFEST_NAME = "runtime-manifest.json"
SECRET_KEY_MARKERS = ("AUTH", "KEY", "PASSWORD", "SECRET", "TOKEN")


class RuntimeManifestError(RuntimeError):
    """Raised when a runtime does not prove identity, fixity, or containment."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeManifestError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeManifestError(f"{path} must contain a JSON object")
    return payload


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def artifact_identity(path: Path) -> tuple[str, str, int]:
    if path.is_symlink():
        target = os.readlink(path)
        return "symlink", _sha256_bytes(target.encode("utf-8")), len(target.encode("utf-8"))
    if path.is_file():
        return "file", _sha256_file(path), path.stat().st_size
    raise RuntimeManifestError(f"runtime artifact is neither file nor symlink: {path}")


def artifact_set_sha256(artifacts: list[dict[str, Any]]) -> str:
    rows = [
        {
            "relative_path": row["relative_path"],
            "kind": row["kind"],
            "sha256": row["sha256"],
            "bytes": row["bytes"],
            "role": row["role"],
        }
        for row in sorted(artifacts, key=lambda item: str(item["relative_path"]))
    ]
    body = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def inventory_runtime(runtime_root: Path, roles: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Inventory every file/link except the self-describing manifest."""

    runtime_root = runtime_root.resolve()
    role_map = roles or {}
    artifacts: list[dict[str, Any]] = []
    for path in sorted(runtime_root.rglob("*")):
        if path.name == MANIFEST_NAME and path.parent == runtime_root:
            continue
        if not (path.is_file() or path.is_symlink()):
            continue
        relative = path.relative_to(runtime_root).as_posix()
        kind, digest, byte_count = artifact_identity(path)
        artifacts.append(
            {
                "relative_path": relative,
                "kind": kind,
                "sha256": digest,
                "bytes": byte_count,
                "role": role_map.get(relative, "runtime-dependency"),
            }
        )
    return artifacts


def _schema_issues(payload: object) -> list[str]:
    schema = _load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[str] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path)):
        location = "".join(f"[{part!r}]" for part in error.absolute_path) or "<root>"
        issues.append(f"{location}: {error.message}")
    return issues


def verify_runtime_manifest(
    manifest_path: Path,
    *,
    experiment_id: str | None = None,
    variant: str | None = None,
    required_commands: list[str] | None = None,
) -> dict[str, Any]:
    """Verify schema, owner containment, exact tree closure, and executables."""

    manifest_path = manifest_path.resolve()
    manifest = _load_json(manifest_path)
    issues = _schema_issues(manifest)
    runtime_root = Path(str(manifest.get("runtime_root", ""))).resolve()
    if not _within(runtime_root, RUNTIME_OWNER_ROOT):
        issues.append(f"runtime_root escapes owner root {RUNTIME_OWNER_ROOT}")
    if manifest_path != runtime_root / MANIFEST_NAME:
        issues.append(f"manifest must be {runtime_root / MANIFEST_NAME}")
    if experiment_id is not None and manifest.get("experiment_id") != experiment_id:
        issues.append("runtime experiment_id does not match requested experiment")
    if variant is not None and manifest.get("variant") != variant:
        issues.append("runtime variant does not match requested variant")
    removal = manifest.get("removal_route", {})
    if not isinstance(removal, dict) or removal.get("target") != runtime_root.as_posix():
        issues.append("removal target must be the exact runtime_root")

    environment = manifest.get("environment", {})
    if isinstance(environment, dict):
        secret_keys = [
            key
            for key in environment
            if any(marker in str(key).upper() for marker in SECRET_KEY_MARKERS)
        ]
        if secret_keys:
            issues.append("runtime environment must not contain secret-bearing keys")

    listed = manifest.get("artifacts", [])
    if isinstance(listed, list) and all(isinstance(row, dict) for row in listed):
        actual = inventory_runtime(runtime_root) if runtime_root.is_dir() else []
        actual_by_path = {row["relative_path"]: row for row in actual}
        listed_by_path = {str(row.get("relative_path")): row for row in listed}
        if len(listed_by_path) != len(listed):
            issues.append("runtime artifact paths are not unique")
        missing = sorted(set(listed_by_path) - set(actual_by_path))
        extra = sorted(set(actual_by_path) - set(listed_by_path))
        if missing:
            issues.append(f"listed runtime artifacts missing: {missing[:5]}")
        if extra:
            issues.append(f"unlisted runtime artifacts present: {extra[:5]}")
        for relative in sorted(set(listed_by_path) & set(actual_by_path)):
            expected = listed_by_path[relative]
            observed = actual_by_path[relative]
            for key in ("kind", "sha256", "bytes"):
                if expected.get(key) != observed.get(key):
                    issues.append(f"runtime artifact drift: {relative} {key}")
            artifact_path = runtime_root / relative
            if observed.get("kind") == "symlink" and not _within(artifact_path, runtime_root):
                issues.append(f"runtime symlink escapes owner tree: {relative}")
        if artifact_set_sha256(listed) != manifest.get("artifact_set_sha256"):
            issues.append("artifact_set_sha256 does not close over listed runtime artifacts")
        if sum(int(row.get("bytes", 0)) for row in listed) != manifest.get("runtime_bytes"):
            issues.append("runtime_bytes does not equal inventoried artifact bytes")

    commands = manifest.get("commands", {})
    required = required_commands or []
    if not isinstance(commands, dict):
        commands = {}
    for name in required:
        path_value = commands.get(name)
        if not isinstance(path_value, str):
            issues.append(f"runtime omits required command {name}")
            continue
        command_path = Path(path_value)
        if not _within(command_path, runtime_root):
            issues.append(f"runtime command escapes root: {name}")
        elif not command_path.is_file() or not os.access(command_path, os.X_OK):
            issues.append(f"runtime command is not executable: {name}")

    for ref in manifest.get("source_receipt_refs", []):
        if isinstance(ref, str) and ref.startswith("/") and not Path(ref).is_file():
            issues.append(f"runtime source receipt is missing: {ref}")
    if issues:
        raise RuntimeManifestError("invalid runtime manifest: " + "; ".join(issues))
    return manifest
