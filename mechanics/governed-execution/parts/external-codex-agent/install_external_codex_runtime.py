#!/usr/bin/env python3
"""Install and inspect one content-addressed external-Codex runtime release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Iterator, Sequence


SCHEMA_VERSION = "abyss_stack_external_codex_runtime_install_v1"
ACTIVE_SCHEMA_VERSION = "abyss_stack_external_codex_active_release_v1"
MANIFEST_SCHEMA_VERSION = "abyss_stack_external_codex_release_manifest_v1"
DEFAULT_RUNTIME_ROOT = Path(
    "/srv/abyss-machine/runtimes/abyss-stack/external-codex-agent"
)
DEFAULT_BIN_DIR = Path.home() / ".local/bin"
RUNTIME_FILES = (
    "bind_external_actor_launch.py",
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
OWNER_CONTRACT_FILES = (
    (
        "aoa-agents",
        "skills/aoa-summon/references/summon-request-v3.schema.json",
    ),
    ("aoa-skills", "schemas/task_local_dag_v2.schema.json"),
)
INSTALLER_GIT = "/usr/bin/git"


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


def require_python_executable(path: Path) -> Path:
    candidate = require_regular_file(path.resolve(), "Python executable")
    if not os.access(candidate, os.X_OK):
        raise InstallError(f"Python executable is not executable: {candidate}")
    probe = (
        "import json,platform,sys;"
        "print(json.dumps({'implementation':platform.python_implementation(),"
        "'version':[sys.version_info.major,sys.version_info.minor]},"
        "sort_keys=True,separators=(',',':')))"
    )
    try:
        completed = subprocess.run(
            [str(candidate), "-I", "-c", probe],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError(f"Python executable compatibility probe failed: {candidate}") from exc
    expected = '{"implementation":"CPython","version":[3,11]}'
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise InstallError(f"Python executable compatibility probe failed: {candidate}") from exc
    version = payload.get("version") if isinstance(payload, dict) else None
    if (
        completed.returncode != 0
        or not isinstance(payload, dict)
        or payload.get("implementation") != "CPython"
        or not isinstance(version, list)
        or len(version) != 2
        or not all(isinstance(item, int) for item in version)
        or tuple(version) < (3, 11)
    ):
        raise InstallError(
            "Python executable must be compatible CPython 3.11 or newer: "
            f"{candidate}; expected at least {expected}"
        )
    return candidate


def require_regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise InstallError(f"{label} must be a regular non-symlink file: {path}")
    return path


def _base_installer_git_environment() -> dict[str, str]:
    """Return a fixed environment that cannot inherit Git executable hooks."""

    return {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "3",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_KEY_1": "core.fsmonitor",
        "GIT_CONFIG_KEY_2": "core.attributesFile",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_VALUE_0": "/dev/null",
        "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_VALUE_2": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
        "PATH": "/usr/bin:/bin",
    }


def _source_git_coordinate(root: Path, *args: str) -> str:
    """Read one non-dispatching coordinate with exact Git and no ambient state."""

    try:
        completed = subprocess.run(
            [INSTALLER_GIT, "-C", str(root), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            env=_base_installer_git_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError(f"cannot inspect Git coordinate for {root}: {exc}") from exc
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value:
        raise InstallError(f"cannot inspect Git coordinate for {root}")
    return value


@contextmanager
def _installer_git_snapshot(root: Path) -> Iterator[dict[str, str]]:
    """Expose posture through private Git metadata with no source config race."""

    head = _source_git_coordinate(root, "rev-parse", "--verify", "HEAD")
    object_format = _source_git_coordinate(root, "rev-parse", "--show-object-format")
    expected_length = {"sha1": 40, "sha256": 64}.get(object_format)
    if (
        expected_length is None
        or len(head) != expected_length
        or re.fullmatch(r"[0-9a-f]+", head) is None
    ):
        raise InstallError(f"unsupported Git object identity for {root}")

    index_value = _source_git_coordinate(root, "rev-parse", "--git-path", "index")
    objects_value = _source_git_coordinate(root, "rev-parse", "--git-path", "objects")
    index_path = Path(index_value)
    objects_path = Path(objects_value)
    if not index_path.is_absolute():
        index_path = root / index_path
    if not objects_path.is_absolute():
        objects_path = root / objects_path
    if index_path.is_symlink() or objects_path.is_symlink():
        raise InstallError(f"source Git metadata must not be symlinked for {root}")
    index_path = index_path.resolve()
    objects_path = objects_path.resolve()
    require_regular_file(index_path, "source Git index")
    require_absolute_directory(objects_path, "source Git object directory")
    if "\n" in str(objects_path) or "\r" in str(objects_path):
        raise InstallError("source Git object directory contains a newline")

    with tempfile.TemporaryDirectory(prefix="aoa-external-codex-git-") as temporary:
        git_dir = Path(temporary) / "git"
        (git_dir / "objects/info").mkdir(parents=True, mode=0o700)
        (git_dir / "refs/heads").mkdir(parents=True, mode=0o700)
        shutil.copyfile(index_path, git_dir / "index")
        (git_dir / "HEAD").write_text(head + "\n", encoding="ascii")
        (git_dir / "objects/info/alternates").write_text(
            str(objects_path) + "\n",
            encoding="utf-8",
        )
        config = [
            "[core]",
            f"\trepositoryFormatVersion = {1 if object_format == 'sha256' else 0}",
            "\tbare = false",
            "\tfileMode = true",
            "\thooksPath = /dev/null",
            "\tfsmonitor = false",
            "\tattributesFile = /dev/null",
            "[diff]",
            "\tignoreSubmodules = all",
            "[status]",
            "\tsubmoduleSummary = false",
        ]
        if object_format == "sha256":
            config.extend(("[extensions]", "\tobjectFormat = sha256"))
        (git_dir / "config").write_text("\n".join(config) + "\n", encoding="utf-8")
        environment = _base_installer_git_environment()
        environment.update(
            {
                "GIT_DIR": str(git_dir),
                "GIT_INDEX_FILE": str(git_dir / "index"),
                "GIT_WORK_TREE": str(root),
            }
        )
        yield environment


def git_posture(
    root: Path,
    packaged_files: Iterable[Path] = (),
) -> dict[str, object]:
    packaged_relatives = {
        path.relative_to(root).as_posix()
        for path in packaged_files
    }
    with _installer_git_snapshot(root) as environment:
        def run(*args: str) -> str:
            completed = subprocess.run(
                [INSTALLER_GIT, "-C", str(root), *args],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
                env=environment,
            )
            return completed.stdout.strip()

        try:
            head = run("rev-parse", "HEAD")
            status = run("status", "--porcelain=v1", "--untracked-files=all")
            flagged = subprocess.run(
                [INSTALLER_GIT, "-C", str(root), "ls-files", "-v", "-z"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                env=environment,
            ).stdout
            ignored = subprocess.run(
                [INSTALLER_GIT, "-C", str(root), "check-ignore", "-z", "--stdin"],
                check=False,
                input=b"".join(
                    relative.encode("utf-8") + b"\0"
                    for relative in sorted(packaged_relatives)
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                env=environment,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            detail = ""
            if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
                raw_detail = exc.stderr
                if isinstance(raw_detail, bytes):
                    detail = raw_detail.decode("utf-8", errors="replace").strip()
                else:
                    detail = str(raw_detail).strip()
            suffix = f": {detail}" if detail else ""
            raise InstallError(
                f"cannot inspect Git posture for {root}: {exc}{suffix}"
            ) from exc
    if ignored.returncode not in {0, 1}:
        raise InstallError(
            f"cannot inspect ignored packaged files for {root}: "
            f"{ignored.stderr.decode('utf-8', errors='replace').strip()}"
        )
    index_flagged_paths: list[str] = []
    for record in flagged.split(b"\0"):
        if not record:
            continue
        if len(record) < 3 or record[1:2] != b" ":
            raise InstallError(f"invalid git ls-files record for {root}")
        tag = chr(record[0])
        relative = record[2:].decode("utf-8", errors="surrogateescape")
        if relative in packaged_relatives and (tag.islower() or tag.upper() == "S"):
            index_flagged_paths.append(relative)
    ignored_packaged_paths = [
        record.decode("utf-8", errors="surrogateescape")
        for record in ignored.stdout.split(b"\0")
        if record
    ]
    hidden_posture = sorted(set(index_flagged_paths))
    ignored_posture = sorted(set(ignored_packaged_paths))
    return {
        "root": str(root),
        "head": head,
        "dirty": bool(status or hidden_posture or ignored_posture),
        "status_sha256": sha256_bytes(status.encode("utf-8")),
        "status_entry_count": len(status.splitlines()) if status else 0,
        "packaged_index_flag_count": len(hidden_posture),
        "packaged_index_flags_sha256": sha256_bytes(
            canonical_bytes(hidden_posture)
        ),
        "ignored_packaged_file_count": len(ignored_posture),
        "ignored_packaged_files_sha256": sha256_bytes(
            canonical_bytes(ignored_posture)
        ),
    }


def source_files(
    source_root: Path,
    sdk_root: Path,
    agents_root: Path,
    skills_root: Path,
) -> list[tuple[Path, Path]]:
    part = source_root / "mechanics/governed-execution/parts/external-codex-agent"
    profile_path = require_regular_file(
        part / "runtime-profile.v1.json", "runtime profile"
    )
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstallError("runtime profile is not valid JSON") from exc
    owner_contracts = profile.get("owner_contracts")
    if not isinstance(owner_contracts, dict):
        raise InstallError("runtime profile has no owner_contracts")
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
    owner_roots = {"aoa-agents": agents_root, "aoa-skills": skills_root}
    profile_keys = {
        "aoa-agents": "owner_execution_request_schema",
        "aoa-skills": "task_local_dag_schema",
    }
    for owner, relative in OWNER_CONTRACT_FILES:
        src = require_regular_file(
            owner_roots[owner] / relative,
            f"{owner} contract {relative}",
        )
        contract = owner_contracts.get(profile_keys[owner])
        if not isinstance(contract, dict):
            raise InstallError(f"runtime profile has no pinned {owner} contract")
        if contract.get("owner_repo") != owner or contract.get("artifact_ref") != relative:
            raise InstallError(f"runtime profile {owner} contract coordinate mismatch")
        if contract.get("digest") != sha256_file(src):
            raise InstallError(f"{owner} contract differs from runtime profile pin")
        rows.append((src, Path("owners") / owner / relative))
    return rows


def source_postures(
    files: Sequence[tuple[Path, Path]],
    source_root: Path,
    sdk_root: Path,
    agents_root: Path,
    skills_root: Path,
) -> dict[str, dict[str, object]]:
    roots = {
        "source": source_root,
        "sdk": sdk_root,
        "agents": agents_root,
        "skills": skills_root,
    }
    return {
        label: git_posture(
            root,
            (source for source, _ in files if source.is_relative_to(root)),
        )
        for label, root in roots.items()
    }


def assert_release_inputs_unchanged(
    original_files: Sequence[tuple[Path, Path]],
    current_files: Sequence[tuple[Path, Path]],
    manifest: dict[str, object],
) -> None:
    """Bind the materialized bytes to the exact source coordinates re-observed."""

    coordinates = tuple(
        (str(source), destination.as_posix())
        for source, destination in original_files
    )
    current_coordinates = tuple(
        (str(source), destination.as_posix())
        for source, destination in current_files
    )
    if current_coordinates != coordinates:
        raise InstallError("release input coordinates changed during installation")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise InstallError("release manifest files are invalid")
    rows_by_path = {
        str(row.get("path")): row
        for row in rows
        if isinstance(row, dict)
    }
    for source, destination in current_files:
        require_regular_file(source, f"release source {source}")
        row = rows_by_path.get(destination.as_posix())
        if (
            row is None
            or source.stat().st_size != row.get("size")
            or sha256_file(source) != row.get("sha256")
        ):
            raise InstallError(
                f"release input changed during installation: {source}"
            )


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
release_id = record["release_id"]
if not isinstance(release_id, str) or not release_id.startswith("sha256-") or len(release_id) != 71 or any(character not in "0123456789abcdef" for character in release_id[7:]):
    raise SystemExit(f"external Codex release id is invalid: {{release_id}}")
raw_release_root = Path(record["release_root"])
if raw_release_root.is_symlink() or not raw_release_root.is_dir():
    raise SystemExit(f"external Codex release is unavailable: {{raw_release_root}}")
release_root = raw_release_root.resolve()
releases_root = (RUNTIME_ROOT / "releases").resolve()
try:
    release_root.relative_to(releases_root)
except ValueError as exc:
    raise SystemExit(f"external Codex release escapes runtime root: {{release_root}}") from exc
if release_root.parent != releases_root or release_root.name != release_id:
    raise SystemExit(f"external Codex release coordinate is invalid: {{release_root}}")
entrypoint = release_root / {entrypoint_name!r}
python = Path(record["python_executable"])
if entrypoint.is_symlink() or not entrypoint.is_file():
    raise SystemExit(f"external Codex entrypoint is unavailable: {{entrypoint}}")
os.execv(str(python), [str(python), "-I", "-B", str(entrypoint), *sys.argv[1:]])
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
        "bind-entrypoint.py": entrypoint_text("bind_external_actor_launch.py"),
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
    expected_files = {Path("release-manifest.json")}
    expected_directories: set[Path] = set()
    for row in manifest["files"]:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise InstallError(f"unsafe release path: {relative}")
        expected_files.add(relative)
        expected_directories.update(relative.parents)
        path = require_regular_file(release_root / relative, f"release file {relative}")
        if path.stat().st_size != row["size"] or sha256_file(path) != row["sha256"]:
            raise InstallError(f"release file drift: {relative}")
    expected_directories.discard(Path("."))
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
    if actual_files != expected_files or actual_directories != expected_directories:
        raise InstallError("release manifest closure mismatch")
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
            ("bind-entrypoint.py", "bind_external_actor_launch.py"),
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
    agents_root: Path,
    skills_root: Path,
    runtime_root: Path,
    bin_dir: Path,
    python_executable: Path,
    *,
    allow_dirty_source: bool,
    allow_dirty_sdk: bool,
    allow_dirty_agents: bool,
    allow_dirty_skills: bool,
) -> dict[str, object]:
    source_root = require_absolute_directory(source_root, "abyss-stack source root")
    sdk_root = require_absolute_directory(sdk_root, "aoa-sdk source root")
    agents_root = require_absolute_directory(agents_root, "aoa-agents source root")
    skills_root = require_absolute_directory(skills_root, "aoa-skills source root")
    runtime_root = runtime_root.resolve()
    bin_dir = bin_dir.resolve()
    python_executable = require_python_executable(python_executable)
    files = source_files(source_root, sdk_root, agents_root, skills_root)
    postures = source_postures(
        files,
        source_root,
        sdk_root,
        agents_root,
        skills_root,
    )
    source_posture = postures["source"]
    sdk_posture = postures["sdk"]
    agents_posture = postures["agents"]
    skills_posture = postures["skills"]
    if source_posture["dirty"] and not allow_dirty_source:
        raise InstallError("abyss-stack source is dirty; pass --allow-dirty-source explicitly")
    if sdk_posture["dirty"] and not allow_dirty_sdk:
        raise InstallError("aoa-sdk source is dirty; pass --allow-dirty-sdk explicitly")
    if agents_posture["dirty"] and not allow_dirty_agents:
        raise InstallError(
            "aoa-agents source is dirty; pass --allow-dirty-agents explicitly"
        )
    if skills_posture["dirty"] and not allow_dirty_skills:
        raise InstallError(
            "aoa-skills source is dirty; pass --allow-dirty-skills explicitly"
        )

    manifest = release_manifest(files)
    release_root, created = materialize_release(files, manifest, runtime_root / "releases")
    current_files = source_files(source_root, sdk_root, agents_root, skills_root)
    current_postures = source_postures(
        current_files,
        source_root,
        sdk_root,
        agents_root,
        skills_root,
    )
    if current_postures != postures:
        raise InstallError("source Git posture changed during installation")
    assert_release_inputs_unchanged(files, current_files, manifest)
    previous_active = None
    active_path = runtime_root / "active.json"
    if active_path.exists():
        require_regular_file(active_path, "active release record")
        previous_active = json.loads(active_path.read_text(encoding="utf-8"))

    wrapper_backups: dict[str, str | None] = {}
    wrappers = {
        "aoa-external-codex-agent": "agent-entrypoint.py",
        "aoa-external-actor-bind": "bind-entrypoint.py",
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
        "agents": agents_posture,
        "skills": skills_posture,
        "installed_at": now,
        "previous_release_id": previous_active.get("release_id") if previous_active else None,
        "nonproduction_dirty_source": bool(
            source_posture["dirty"]
            or sdk_posture["dirty"]
            or agents_posture["dirty"]
            or skills_posture["dirty"]
        ),
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
            ) if previous_active else "Remove the three newly created wrappers and active.json after operator review; the immutable release may be retained.",
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
    if (
        not release_id.startswith("sha256-")
        or len(release_id) != 71
        or any(character not in "0123456789abcdef" for character in release_id[7:])
    ):
        raise InstallError("release id must be one exact sha256 content address")
    releases_root = (runtime_root / "releases").resolve()
    release_root = (releases_root / release_id).resolve()
    try:
        release_root.relative_to(releases_root)
    except ValueError as exc:
        raise InstallError("release activation escapes releases root") from exc
    if release_root.parent != releases_root or release_root.name != release_id:
        raise InstallError("release activation coordinate is invalid")
    manifest = verify_release(release_root)
    if manifest["release_id"] != release_id:
        raise InstallError("requested release id differs from verified manifest")
    python_executable = require_python_executable(python_executable)
    active_path = runtime_root / "active.json"
    previous = json.loads(active_path.read_text(encoding="utf-8")) if active_path.exists() else None
    for name, entrypoint in {
        "aoa-external-codex-agent": "agent-entrypoint.py",
        "aoa-external-actor-bind": "bind-entrypoint.py",
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
    python_value = active.get("python_executable")
    if not isinstance(python_value, str):
        raise InstallError("active Python executable is invalid")
    require_python_executable(Path(python_value))
    release_id = active.get("release_id")
    if not isinstance(release_id, str):
        raise InstallError("active release id is invalid")
    raw_release_root = Path(active["release_root"])
    if raw_release_root.is_symlink():
        raise InstallError("active release root must not be a symlink")
    release_root = raw_release_root.resolve()
    releases_root = (runtime_root / "releases").resolve()
    try:
        release_root.relative_to(releases_root)
    except ValueError as exc:
        raise InstallError("active release escapes runtime root") from exc
    if release_root.parent != releases_root or release_root.name != release_id:
        raise InstallError("active release coordinate is invalid")
    manifest = verify_release(release_root)
    if manifest["release_id"] != release_id:
        raise InstallError("active release id differs from verified manifest")
    wrapper_status = {}
    for name, entrypoint in {
        "aoa-external-codex-agent": "agent-entrypoint.py",
        "aoa-external-actor-bind": "bind-entrypoint.py",
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
    install_parser.add_argument("--agents-root", type=Path, required=True)
    install_parser.add_argument("--skills-root", type=Path, required=True)
    install_parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    install_parser.add_argument("--bin-dir", type=Path, default=DEFAULT_BIN_DIR)
    install_parser.add_argument("--python", type=Path, default=Path(sys.executable))
    install_parser.add_argument("--allow-dirty-source", action="store_true")
    install_parser.add_argument("--allow-dirty-sdk", action="store_true")
    install_parser.add_argument("--allow-dirty-agents", action="store_true")
    install_parser.add_argument("--allow-dirty-skills", action="store_true")
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
                args.agents_root,
                args.skills_root,
                args.runtime_root,
                args.bin_dir,
                args.python,
                allow_dirty_source=args.allow_dirty_source,
                allow_dirty_sdk=args.allow_dirty_sdk,
                allow_dirty_agents=args.allow_dirty_agents,
                allow_dirty_skills=args.allow_dirty_skills,
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
