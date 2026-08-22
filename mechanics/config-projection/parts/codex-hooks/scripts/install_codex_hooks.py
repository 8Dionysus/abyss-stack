#!/usr/bin/env python3
"""Install the stack Codex agent-routing hooks from one exact source commit.

The installer owns only source materialization and native hook composition.  It
does not choose a route, classify responsibility, establish Codex trust, or
claim live hook health.  The active hook commands point at an immutable release
under the deployed runtime's isolated Codex home; the session owner supplies
the typed base through ``AOA_AGENT_TOOL_ROUTING_CONTEXT_BASE``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any


RELEASE_SCHEMA_VERSION = "abyss_codex_hooks_release_v1"
INSTALL_SCHEMA_VERSION = "abyss_codex_hooks_install_receipt_v1"
RELEASE_FILES = (
    "scripts/codex_pretool_agent_routing.py",
    "scripts/codex_pretool_agent_routing_context.py",
    "scripts/install_codex_hooks.py",
    "scripts/render_codex_hooks.py",
    "config/abyss-stack-agent-tool-routing.fragment.json",
    "config/abyss-stack-agent-tool-routing-context.fragment.json",
    "schemas/codex-pretool-agent-routing-context.schema.json",
)
PYTHON_RELEASE_FILES = {
    "scripts/codex_pretool_agent_routing.py",
    "scripts/codex_pretool_agent_routing_context.py",
    "scripts/install_codex_hooks.py",
    "scripts/render_codex_hooks.py",
}


class InstallError(ValueError):
    """A source, release, or installation contract failed closed."""


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def rendered_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise InstallError(f"cannot read {path}") from exc


def _require_absolute_directory(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise InstallError(f"{label} must be an existing non-symlink directory")
    return path.resolve()


def _absolute_without_dereference(path: Path, label: str) -> Path:
    """Make a path absolute without hiding a symlink at its final component."""
    absolute = path if path.is_absolute() else path.absolute()
    if absolute.is_symlink():
        raise InstallError(f"{label} must not be a symlink")
    return absolute


def _require_regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise InstallError(f"{label} must be a regular non-symlink file")
    return path


def _ensure_directory(path: Path, label: str, *, mode: int = 0o700) -> Path:
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise InstallError(f"{label} must be a non-symlink directory")
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    os.chmod(path, mode)
    return path


def _atomic_write(path: Path, payload: bytes, *, mode: int) -> None:
    if path.parent.is_symlink():
        raise InstallError(f"write parent must not be a symlink: {path.parent}")
    _ensure_directory(path.parent, "write parent")
    temporary: Path | None = None
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _source_commit(source_root: Path) -> str:
    source_root = _require_absolute_directory(source_root, "source root")
    try:
        top_level = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(source_root), "status", "--porcelain=v1", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InstallError("source root is not a readable Git checkout") from exc
    if Path(top_level).resolve() != source_root:
        raise InstallError("source root must be the exact Git checkout root")
    if not len(commit) == 40 or any(character not in "0123456789abcdef" for character in commit):
        raise InstallError("source root did not provide one exact commit")
    if status:
        raise InstallError("source root must be clean before hook installation")
    return commit


def _source_files(source_root: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for relative_text in RELEASE_FILES:
        relative = Path(relative_text)
        path = _require_regular_file(source_root / "mechanics/config-projection/parts/codex-hooks" / relative, f"source file {relative_text}")
        paths[relative_text] = path
    return paths


def build_manifest(source_root: Path, source_commit: str) -> dict[str, Any]:
    files = _source_files(source_root)
    rows = []
    for relative_text, path in files.items():
        raw = path.read_bytes()
        rows.append(
            {
                "path": relative_text,
                "sha256": sha256_bytes(raw),
                "size": len(raw),
            }
        )
    rows.sort(key=lambda row: row["path"])
    identity = {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "source": {
            "repository": "abyss-stack",
            "commit": source_commit,
        },
        "files": rows,
    }
    digest = sha256_bytes(canonical_bytes(identity))
    return {
        **identity,
        "release_id": digest.replace("sha256:", "sha256-"),
        "release_digest": digest,
    }


def _release_files(manifest: dict[str, Any]) -> set[Path]:
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise InstallError("release manifest files are invalid")
    expected: set[Path] = set()
    for row in files:
        if not isinstance(row, dict):
            raise InstallError("release manifest file row is invalid")
        relative = Path(str(row.get("path", "")))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise InstallError(f"unsafe release path: {relative}")
        if relative in expected:
            raise InstallError(f"duplicate release path: {relative}")
        if not isinstance(row.get("sha256"), str) or not isinstance(row.get("size"), int):
            raise InstallError(f"release file metadata is invalid: {relative}")
        expected.add(relative)
    return expected


def verify_release(release_root: Path) -> dict[str, Any]:
    release_root = _require_absolute_directory(release_root, "release root")
    manifest_path = _require_regular_file(release_root / "release-manifest.json", "release manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError("release manifest is unreadable") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != RELEASE_SCHEMA_VERSION:
        raise InstallError("release manifest schema mismatch")
    source = manifest.get("source")
    if (
        not isinstance(source, dict)
        or source.get("repository") != "abyss-stack"
        or not isinstance(source.get("commit"), str)
    ):
        raise InstallError("release source identity is invalid")
    files = _release_files(manifest)
    identity = {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "source": source,
        "files": manifest["files"],
    }
    expected_digest = sha256_bytes(canonical_bytes(identity))
    if manifest.get("release_digest") != expected_digest:
        raise InstallError("release manifest digest mismatch")
    if manifest.get("release_id") != expected_digest.replace("sha256:", "sha256-"):
        raise InstallError("release id mismatch")

    expected_entries = files | {Path("release-manifest.json")}
    actual_files: set[Path] = set()
    actual_directories: set[Path] = set()
    for path in release_root.rglob("*"):
        relative = path.relative_to(release_root)
        if path.is_symlink():
            raise InstallError(f"release contains a symbolic link: {relative}")
        if path.is_file():
            actual_files.add(relative)
        elif path.is_dir():
            actual_directories.add(relative)
        else:
            raise InstallError(f"release contains an unsupported entry: {relative}")
    expected_directories: set[Path] = set()
    for relative in expected_entries:
        expected_directories.update(relative.parents)
    expected_directories.discard(Path("."))
    if actual_files != expected_entries or actual_directories != expected_directories:
        raise InstallError("release manifest closure mismatch")
    rows_by_path = {Path(row["path"]): row for row in manifest["files"]}
    for relative, row in rows_by_path.items():
        path = _require_regular_file(release_root / relative, f"release file {relative}")
        if path.stat().st_size != row["size"] or sha256_file(path) != row["sha256"]:
            raise InstallError(f"release file drift: {relative}")
    return manifest


def materialize_release(
    source_root: Path,
    install_root: Path,
    source_commit: str,
) -> tuple[Path, dict[str, Any], bool]:
    manifest = build_manifest(source_root, source_commit)
    releases_root = _ensure_directory(install_root / "releases", "release root")
    release_root = releases_root / str(manifest["release_id"])
    if release_root.exists():
        return release_root, verify_release(release_root), False

    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=releases_root))
    try:
        source_paths = _source_files(source_root)
        for relative_text, source_path in source_paths.items():
            target = staging / relative_text
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target, follow_symlinks=False)
            os.chmod(target, 0o755 if relative_text in PYTHON_RELEASE_FILES else 0o644)
        manifest_path = staging / "release-manifest.json"
        manifest_path.write_bytes(rendered_bytes(manifest))
        os.chmod(manifest_path, 0o644)
        verify_release(staging.resolve())
        os.chmod(staging, 0o700)
        os.replace(staging, release_root)
        for directory, _, _ in os.walk(release_root, topdown=False):
            os.chmod(directory, 0o700)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return release_root, manifest, True


def _load_renderer(source_root: Path) -> Any:
    path = source_root / "mechanics/config-projection/parts/codex-hooks/scripts/render_codex_hooks.py"
    spec = importlib.util.spec_from_file_location("abyss_stack_codex_hook_renderer", path)
    if spec is None or spec.loader is None:
        raise InstallError("Codex hook renderer could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _restore_target(renderer: Any, target: Path, previous_bytes: bytes | None, previous_mode: int | None) -> None:
    if previous_bytes is None:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        return
    renderer.atomic_private_write(target, previous_bytes, mode=previous_mode or 0o600)


def _restore_file(
    path: Path,
    previous_bytes: bytes | None,
    previous_mode: int | None,
) -> None:
    if previous_bytes is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    _atomic_write(path, previous_bytes, mode=previous_mode or 0o600)


def install(
    *,
    source_root: Path,
    install_root: Path,
    native_fragment: Path,
    target: Path,
    context_directory: Path,
    sdk_source_root: Path,
    composition_receipt: Path,
    backup_directory: Path,
) -> dict[str, Any]:
    source_root = _require_absolute_directory(source_root, "source root")
    install_root = _absolute_without_dereference(install_root, "install root")
    if not install_root.is_absolute():
        raise InstallError("install root must be an absolute non-symlink path")
    native_fragment = _require_regular_file(native_fragment, "native hook fragment")
    target = _absolute_without_dereference(target, "Codex hooks target")
    composition_receipt = _absolute_without_dereference(
        composition_receipt,
        "composition receipt",
    )
    backup_directory = _absolute_without_dereference(backup_directory, "hook backup directory")
    sdk_source_root = _require_absolute_directory(sdk_source_root, "aoa-sdk source root")
    if not (sdk_source_root / "src" / "aoa_sdk").is_dir():
        raise InstallError("aoa-sdk source root has no src/aoa_sdk package")
    if not target.parent.is_dir() or target.is_symlink():
        raise InstallError("Codex hooks target must have an existing non-symlink parent")
    if composition_receipt.is_symlink():
        raise InstallError("composition receipt must not be a symlink")
    _ensure_directory(composition_receipt.parent, "composition receipt directory")
    context_directory = _ensure_directory(
        _absolute_without_dereference(context_directory, "agent-tool routing context directory"),
        "agent-tool routing context directory",
    )

    source_commit = _source_commit(source_root)
    release_root, manifest, release_created = materialize_release(
        source_root,
        install_root,
        source_commit,
    )
    renderer = _load_renderer(source_root)
    native_bytes = native_fragment.read_bytes()
    previous_bytes: bytes | None = None
    previous_mode: int | None = None
    if target.exists():
        if not target.is_file():
            raise InstallError("Codex hooks target must be a regular file")
        previous_bytes = target.read_bytes()
        previous_mode = stat.S_IMODE(target.stat().st_mode)

    context_fragment = release_root / "config/abyss-stack-agent-tool-routing-context.fragment.json"
    agent_fragment = release_root / "config/abyss-stack-agent-tool-routing.fragment.json"
    relay_script = release_root / "scripts/codex_pretool_agent_routing_context.py"
    adapter_script = release_root / "scripts/codex_pretool_agent_routing.py"
    bindings = {
        "AOA_CODEX_AGENT_ROUTING_CONTEXT_RELAY": str(relay_script),
        "AOA_CODEX_AGENT_ROUTING_CONTEXT_DIR": str(context_directory),
        "AOA_CODEX_AGENT_ROUTING_HOOK": str(adapter_script),
        "AOA_CODEX_AGENT_ROUTING_SDK_SOURCE_ROOT": str(sdk_source_root),
    }
    output, fragments, binding_digests = renderer.compose(
        [native_fragment, context_fragment, agent_fragment],
        bindings,
    )
    _ensure_directory(backup_directory, "hook backup directory")
    try:
        composition = renderer.install_composition(
            output=output,
            fragments=fragments,
            binding_digests=binding_digests,
            target=target,
            receipt_path=composition_receipt,
            backup_dir=backup_directory,
        )
    except Exception:
        raise

    active_path = install_root / "active.json"
    if active_path.is_symlink():
        raise InstallError("active install receipt must not be a symlink")
    if active_path.exists() and not active_path.is_file():
        raise InstallError("active install receipt must be a regular file")
    previous_active_bytes = active_path.read_bytes() if active_path.is_file() else None
    previous_active_mode = stat.S_IMODE(active_path.stat().st_mode) if active_path.is_file() else None
    receipt_dir = _ensure_directory(install_root / "receipts", "install receipt directory")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt_path = receipt_dir / f"{timestamp}-{manifest['release_id']}.json"
    active = {
        "schema_version": INSTALL_SCHEMA_VERSION,
        "operation": "install",
        "installed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "repository": "abyss-stack",
            "commit": source_commit,
        },
        "release": {
            "release_id": manifest["release_id"],
            "release_digest": manifest["release_digest"],
            "release_root": str(release_root),
            "created": release_created,
        },
        "target": {
            "path": str(target),
            "digest": sha256_file(target),
            "mode": f"{stat.S_IMODE(target.stat().st_mode):04o}",
        },
        "composition": {
            "receipt": str(composition_receipt),
            "receipt_digest": sha256_file(composition_receipt),
            "native_fragment_digest": sha256_bytes(native_bytes),
            "event_count": composition["output"]["event_count"],
            "group_count": composition["output"]["group_count"],
            "handler_count": composition["output"]["handler_count"],
        },
        "runtime_bindings": {
            "context_directory_ref": sha256_bytes(str(context_directory).encode("utf-8")),
            "sdk_source_root_ref": sha256_bytes(str(sdk_source_root).encode("utf-8")),
            "typed_base_environment": "AOA_AGENT_TOOL_ROUTING_CONTEXT_BASE",
        },
        "rollback": {
            "composition_backup_directory": str(backup_directory),
            "previous_target_digest": sha256_bytes(previous_bytes) if previous_bytes is not None else None,
            "previous_target_mode": f"{previous_mode:04o}" if previous_mode is not None else None,
        },
        "authority": {
            "source_identity": True,
            "native_composition": True,
            "hook_semantics": False,
            "codex_trust": False,
            "runtime_health": False,
            "owner_classification": False,
            "live_proof": False,
            "goal_acceptance": False,
        },
    }
    try:
        _atomic_write(active_path, rendered_bytes(active), mode=0o600)
        _atomic_write(receipt_path, rendered_bytes(active), mode=0o600)
    except BaseException:
        _restore_target(renderer, target, previous_bytes, previous_mode)
        _restore_file(active_path, previous_active_bytes, previous_active_mode)
        try:
            composition_receipt.unlink()
        except OSError:
            pass
        raise
    return {
        "active": active,
        "active_path": str(active_path),
        "install_receipt": str(receipt_path),
        "composition_receipt": str(composition_receipt),
        "release_root": str(release_root),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install durable abyss-stack Codex agent-routing hooks.")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--native-fragment", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--context-directory", type=Path, required=True)
    parser.add_argument("--sdk-source-root", type=Path, required=True)
    parser.add_argument("--composition-receipt", type=Path, required=True)
    parser.add_argument("--backup-directory", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = install(
            source_root=args.source_root.absolute(),
            install_root=args.install_root,
            native_fragment=args.native_fragment.absolute(),
            target=args.target,
            context_directory=args.context_directory,
            sdk_source_root=args.sdk_source_root.absolute(),
            composition_receipt=args.composition_receipt,
            backup_directory=args.backup_directory,
        )
    except (InstallError, OSError, RuntimeError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
