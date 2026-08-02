#!/usr/bin/env python3
"""Install and inspect one content-addressed external-Codex runtime release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Sequence


SCHEMA_VERSION = "abyss_stack_external_codex_runtime_install_v1"
ACTIVE_SCHEMA_VERSION = "abyss_stack_external_codex_active_release_v1"
MANIFEST_SCHEMA_VERSION = "abyss_stack_external_codex_release_manifest_v1"
DEFAULT_RUNTIME_ROOT = Path(
    "/srv/abyss-machine/runtimes/abyss-stack/external-codex-agent"
)
DEFAULT_BIN_DIR = Path.home() / ".local/bin"
RUNTIME_FILES = (
    "external_codex_agent.py",
    "external_codex_supervisor.py",
    "prepare_landing_study.py",
    "runtime-profile.v1.json",
)
SDK_CONTRACT_FILES = (
    "mechanics/boundary-bridge/parts/agent-incarnation-binding/schemas/agent-incarnation-binding.schema.json",
    "mechanics/checkpoint/parts/child-task-reentry/schemas/summon-request-v4.schema.json",
    "mechanics/checkpoint/parts/child-task-reentry/schemas/summon-result-v4.schema.json",
)


class InstallError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def require_absolute_directory(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise InstallError(f"{label} must be absolute: {path}")
    if path.is_symlink() or not path.is_dir():
        raise InstallError(f"{label} must be a real directory: {path}")
    return path.resolve()


def require_regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise InstallError(f"{label} must be a regular non-symlink file: {path}")
    return path


def git_posture(root: Path) -> dict[str, object]:
    def run(*args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return completed.stdout.strip()

    try:
        head = run("rev-parse", "HEAD")
        status = run("status", "--porcelain=v1", "--untracked-files=all")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InstallError(f"cannot inspect Git posture for {root}: {exc}") from exc
    return {
        "root": str(root),
        "head": head,
        "dirty": bool(status),
        "status_sha256": sha256_bytes(status.encode("utf-8")),
        "status_entry_count": len(status.splitlines()) if status else 0,
    }


def source_files(source_root: Path, sdk_root: Path) -> list[tuple[Path, Path]]:
    part = source_root / "mechanics/governed-execution/parts/external-codex-agent"
    rows: list[tuple[Path, Path]] = []
    for name in RUNTIME_FILES:
        src = require_regular_file(part / name, f"runtime source {name}")
        rows.append((src, Path("runtime") / name))
    schema_root = require_absolute_directory(part / "schemas", "runtime schema root")
    schemas = sorted(schema_root.glob("*.schema.json"))
    if not schemas:
        raise InstallError("runtime schema root contains no schemas")
    for src in schemas:
        require_regular_file(src, f"runtime schema {src.name}")
        rows.append((src, Path("runtime/schemas") / src.name))

    package_root = require_absolute_directory(sdk_root / "src/aoa_sdk", "aoa_sdk package")
    sdk_files = sorted(
        path
        for path in package_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )
    if not any(path.relative_to(package_root) == Path("contracts/incarnation.py") for path in sdk_files):
        raise InstallError("aoa_sdk package lacks contracts/incarnation.py")
    for src in sdk_files:
        require_regular_file(src, f"aoa_sdk source {src}")
        rows.append((src, Path("sdk/src/aoa_sdk") / src.relative_to(package_root)))
    for relative in SDK_CONTRACT_FILES:
        src = require_regular_file(sdk_root / relative, f"aoa_sdk contract {relative}")
        rows.append((src, Path("sdk") / relative))
    return rows


def entrypoint_text(target: str) -> str:
    return f'''#!/usr/bin/env python3
from __future__ import annotations
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SDK = ROOT / "sdk/src"
TARGET = ROOT / "runtime/{target}"
sys.path.insert(0, str(SDK))
sys.argv[0] = str(TARGET)
runpy.run_path(str(TARGET), run_name="__main__")
'''


def wrapper_text(active_path: Path, entrypoint_name: str) -> str:
    return f'''#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

ACTIVE = Path({str(active_path)!r})
RUNTIME_ROOT = Path({str(active_path.parent)!r})
if ACTIVE.is_symlink() or not ACTIVE.is_file():
    raise SystemExit(f"external Codex active release is unavailable: {{ACTIVE}}")
record = json.loads(ACTIVE.read_text(encoding="utf-8"))
release_root = Path(record["release_root"])
try:
    release_root.relative_to(RUNTIME_ROOT / "releases")
except ValueError as exc:
    raise SystemExit(f"external Codex release escapes runtime root: {{release_root}}") from exc
entrypoint = release_root / {entrypoint_name!r}
python = Path(record["python_executable"])
if release_root.is_symlink() or not release_root.is_dir():
    raise SystemExit(f"external Codex release is unavailable: {{release_root}}")
if entrypoint.is_symlink() or not entrypoint.is_file():
    raise SystemExit(f"external Codex entrypoint is unavailable: {{entrypoint}}")
os.execv(str(python), [str(python), "-I", str(entrypoint), *sys.argv[1:]])
'''


def release_manifest(files: Iterable[tuple[Path, Path]]) -> dict[str, object]:
    rows = [
        {
            "path": destination.as_posix(),
            "sha256": sha256_file(source),
            "size": source.stat().st_size,
        }
        for source, destination in files
    ]
    entrypoints = {
        "agent-entrypoint.py": entrypoint_text("external_codex_agent.py"),
        "study-entrypoint.py": entrypoint_text("prepare_landing_study.py"),
    }
    for path, text in entrypoints.items():
        raw = text.encode("utf-8")
        rows.append({"path": path, "sha256": sha256_bytes(raw), "size": len(raw)})
    rows.sort(key=lambda row: str(row["path"]))
    identity = {"schema_version": MANIFEST_SCHEMA_VERSION, "files": rows}
    digest = sha256_bytes(canonical_bytes(identity))
    return {
        **identity,
        "release_id": digest.replace("sha256:", "sha256-"),
        "release_digest": digest,
    }


def atomic_write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise InstallError(f"write parent must not be a symlink: {path.parent}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def verify_release(release_root: Path) -> dict[str, object]:
    require_absolute_directory(release_root, "release root")
    manifest_path = require_regular_file(release_root / "release-manifest.json", "release manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise InstallError("release manifest schema mismatch")
    identity = {"schema_version": MANIFEST_SCHEMA_VERSION, "files": manifest.get("files")}
    expected = sha256_bytes(canonical_bytes(identity))
    if manifest.get("release_digest") != expected:
        raise InstallError("release manifest digest mismatch")
    if manifest.get("release_id") != expected.replace("sha256:", "sha256-"):
        raise InstallError("release id mismatch")
    for row in manifest["files"]:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise InstallError(f"unsafe release path: {relative}")
        path = require_regular_file(release_root / relative, f"release file {relative}")
        if path.stat().st_size != row["size"] or sha256_file(path) != row["sha256"]:
            raise InstallError(f"release file drift: {relative}")
    return manifest


def materialize_release(
    files: list[tuple[Path, Path]],
    manifest: dict[str, object],
    releases_root: Path,
) -> tuple[Path, bool]:
    release_root = releases_root / str(manifest["release_id"])
    if release_root.exists():
        verify_release(release_root)
        return release_root, False
    releases_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=releases_root))
    try:
        for source, relative in files:
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target, follow_symlinks=False)
            os.chmod(target, 0o444)
        for name, target in (
            ("agent-entrypoint.py", "external_codex_agent.py"),
            ("study-entrypoint.py", "prepare_landing_study.py"),
        ):
            path = staging / name
            path.write_text(entrypoint_text(target), encoding="utf-8", newline="\n")
            os.chmod(path, 0o555)
        manifest_path = staging / "release-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.chmod(manifest_path, 0o444)
        verify_release(staging.resolve())
        os.replace(staging, release_root)
        for directory, _, _ in os.walk(release_root, topdown=False):
            os.chmod(directory, 0o555)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return release_root, True


def backup_existing_wrapper(path: Path, runtime_root: Path) -> str | None:
    if not path.exists() and not path.is_symlink():
        return None
    require_regular_file(path, "existing wrapper")
    digest = sha256_file(path)
    backup = runtime_root / "wrapper-backups" / f"{digest.removeprefix('sha256:')}-{path.name}"
    if not backup.exists():
        atomic_write(backup, path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
    return str(backup)


def install(
    source_root: Path,
    sdk_root: Path,
    runtime_root: Path,
    bin_dir: Path,
    python_executable: Path,
    *,
    allow_dirty_source: bool,
    allow_dirty_sdk: bool,
) -> dict[str, object]:
    source_root = require_absolute_directory(source_root, "abyss-stack source root")
    sdk_root = require_absolute_directory(sdk_root, "aoa-sdk source root")
    runtime_root = runtime_root.resolve()
    bin_dir = bin_dir.resolve()
    python_executable = require_regular_file(python_executable.resolve(), "Python executable")
    source_posture = git_posture(source_root)
    sdk_posture = git_posture(sdk_root)
    if source_posture["dirty"] and not allow_dirty_source:
        raise InstallError("abyss-stack source is dirty; pass --allow-dirty-source explicitly")
    if sdk_posture["dirty"] and not allow_dirty_sdk:
        raise InstallError("aoa-sdk source is dirty; pass --allow-dirty-sdk explicitly")

    files = source_files(source_root, sdk_root)
    manifest = release_manifest(files)
    release_root, created = materialize_release(files, manifest, runtime_root / "releases")
    previous_active = None
    active_path = runtime_root / "active.json"
    if active_path.exists():
        require_regular_file(active_path, "active release record")
        previous_active = json.loads(active_path.read_text(encoding="utf-8"))

    wrapper_backups: dict[str, str | None] = {}
    wrappers = {
        "aoa-external-codex-agent": "agent-entrypoint.py",
        "aoa-external-codex-study": "study-entrypoint.py",
    }
    for name, entrypoint in wrappers.items():
        path = bin_dir / name
        expected = wrapper_text(active_path, entrypoint).encode("utf-8")
        if path.exists() and not path.is_symlink() and path.read_bytes() == expected:
            wrapper_backups[name] = None
            continue
        wrapper_backups[name] = backup_existing_wrapper(path, runtime_root)
        atomic_write(path, expected, 0o755)

    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    active = {
        "schema_version": ACTIVE_SCHEMA_VERSION,
        "release_id": manifest["release_id"],
        "release_digest": manifest["release_digest"],
        "release_root": str(release_root),
        "python_executable": str(python_executable),
        "source": source_posture,
        "sdk": sdk_posture,
        "installed_at": now,
        "previous_release_id": previous_active.get("release_id") if previous_active else None,
        "nonproduction_dirty_source": bool(source_posture["dirty"] or sdk_posture["dirty"]),
    }
    atomic_write(
        active_path,
        (json.dumps(active, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        0o644,
    )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "operation": "install",
        "active": active,
        "release_created": created,
        "previous_active": previous_active,
        "wrappers": {name: str(bin_dir / name) for name in wrappers},
        "wrapper_backups": wrapper_backups,
        "rollback": {
            "command": (
                f"{source_root}/mechanics/governed-execution/parts/"
                "external-codex-agent/install_external_codex_runtime.py activate "
                f"--runtime-root {runtime_root} --bin-dir {bin_dir} "
                f"--release-id {previous_active.get('release_id')}"
            ) if previous_active else "Remove the two newly created wrappers and active.json after operator review; the immutable release may be retained.",
        },
    }
    receipts = runtime_root / "receipts"
    receipt_name = f"{now.replace(':', '').replace('-', '')}-{manifest['release_id']}.json"
    atomic_write(
        receipts / receipt_name,
        (json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        0o444,
    )
    return receipt


def activate(
    runtime_root: Path,
    bin_dir: Path,
    release_id: str,
    python_executable: Path,
) -> dict[str, object]:
    runtime_root = runtime_root.resolve()
    release_root = runtime_root / "releases" / release_id
    manifest = verify_release(release_root)
    python_executable = require_regular_file(python_executable.resolve(), "Python executable")
    active_path = runtime_root / "active.json"
    previous = json.loads(active_path.read_text(encoding="utf-8")) if active_path.exists() else None
    for name, entrypoint in {
        "aoa-external-codex-agent": "agent-entrypoint.py",
        "aoa-external-codex-study": "study-entrypoint.py",
    }.items():
        atomic_write(
            bin_dir.resolve() / name,
            wrapper_text(active_path, entrypoint).encode("utf-8"),
            0o755,
        )
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    active = {
        "schema_version": ACTIVE_SCHEMA_VERSION,
        "release_id": release_id,
        "release_digest": manifest["release_digest"],
        "release_root": str(release_root),
        "python_executable": str(python_executable),
        "source": None,
        "sdk": None,
        "installed_at": now,
        "previous_release_id": previous.get("release_id") if previous else None,
        "nonproduction_dirty_source": True,
    }
    atomic_write(
        active_path,
        (json.dumps(active, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        0o644,
    )
    return {"schema_version": SCHEMA_VERSION, "operation": "activate", "active": active}


def status(runtime_root: Path, bin_dir: Path) -> dict[str, object]:
    runtime_root = runtime_root.resolve()
    active_path = require_regular_file(runtime_root / "active.json", "active release record")
    active = json.loads(active_path.read_text(encoding="utf-8"))
    if active.get("schema_version") != ACTIVE_SCHEMA_VERSION:
        raise InstallError("active release schema mismatch")
    release_root = Path(active["release_root"])
    try:
        release_root.relative_to(runtime_root / "releases")
    except ValueError as exc:
        raise InstallError("active release escapes runtime root") from exc
    manifest = verify_release(release_root)
    wrapper_status = {}
    for name, entrypoint in {
        "aoa-external-codex-agent": "agent-entrypoint.py",
        "aoa-external-codex-study": "study-entrypoint.py",
    }.items():
        path = require_regular_file(bin_dir.resolve() / name, f"wrapper {name}")
        expected = wrapper_text(active_path, entrypoint).encode("utf-8")
        wrapper_status[name] = {
            "path": str(path),
            "digest": sha256_file(path),
            "current": path.read_bytes() == expected,
        }
        if not wrapper_status[name]["current"]:
            raise InstallError(f"wrapper drift: {path}")
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": "status",
        "healthy": True,
        "active": active,
        "manifest": manifest,
        "wrappers": wrapper_status,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--source-root", type=Path, required=True)
    install_parser.add_argument("--sdk-root", type=Path, required=True)
    install_parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    install_parser.add_argument("--bin-dir", type=Path, default=DEFAULT_BIN_DIR)
    install_parser.add_argument("--python", type=Path, default=Path(sys.executable))
    install_parser.add_argument("--allow-dirty-source", action="store_true")
    install_parser.add_argument("--allow-dirty-sdk", action="store_true")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    status_parser.add_argument("--bin-dir", type=Path, default=DEFAULT_BIN_DIR)
    activate_parser = subparsers.add_parser("activate")
    activate_parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    activate_parser.add_argument("--bin-dir", type=Path, default=DEFAULT_BIN_DIR)
    activate_parser.add_argument("--release-id", required=True)
    activate_parser.add_argument("--python", type=Path, default=Path(sys.executable))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "install":
            payload = install(
                args.source_root,
                args.sdk_root,
                args.runtime_root,
                args.bin_dir,
                args.python,
                allow_dirty_source=args.allow_dirty_source,
                allow_dirty_sdk=args.allow_dirty_sdk,
            )
        elif args.command == "activate":
            payload = activate(args.runtime_root, args.bin_dir, args.release_id, args.python)
        else:
            payload = status(args.runtime_root, args.bin_dir)
    except (InstallError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, "result": payload}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
