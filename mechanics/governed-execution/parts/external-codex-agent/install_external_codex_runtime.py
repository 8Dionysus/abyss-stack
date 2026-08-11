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
import struct
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Iterator, Sequence


SCHEMA_VERSION = "abyss_stack_external_codex_runtime_install_v1"
ACTIVE_SCHEMA_VERSION = "abyss_stack_external_codex_active_release_v1"
STAGED_SCHEMA_VERSION = "abyss_stack_external_codex_staged_release_v1"
MANIFEST_SCHEMA_VERSION = "abyss_stack_external_codex_release_manifest_v1"
ARTIFACT_GATE_SCHEMA_VERSION = "abyss_machine_artifact_trust_gate_v1"
ARTIFACT_CLASS = "runtime_or_container_artifact"
ARTIFACT_CONSUMER_INTENT = "runtime_canary"
ARTIFACT_SOURCE_REPO = "abyss-stack"
ARTIFACT_TRUST_ROOT_MODE = "host_managed"
ARTIFACT_BUNDLE_MANIFEST_REF = (
    "manifests/artifact_bundles/abyss_stack_external_codex_agent.bundle.json"
)
ARTIFACT_SUBJECT_ROLE = "external_codex_agent_release_manifest"
ARTIFACT_REQUIRED_CONTROLS = frozenset(
    {"abi_signature", "sbom", "slsa_in_toto", "sigstore_cosign"}
)
DEFAULT_RUNTIME_ROOT = Path(
    "/srv/abyss-machine/runtimes/abyss-stack/external-codex-agent"
)
DEFAULT_BIN_DIR = Path.home() / ".local/bin"
RUNTIME_FILES = (
    "bind_external_actor_launch.py",
    "external_codex_agent.py",
    "external_codex_mount_launcher.py",
    "external_codex_projection.py",
    "external_codex_static_bootstrap.S",
    "external_codex_supervisor.py",
    "prepare_landing_study.py",
    "runtime-profile.v1.json",
)
SDK_CONTRACT_FILES = (
    "mechanics/boundary-bridge/parts/agent-incarnation-binding/schemas/agent-incarnation-binding.schema.json",
    "mechanics/boundary-bridge/parts/agent-incarnation-binding/schemas/agent-incarnation-binding-v2.schema.json",
    "mechanics/checkpoint/parts/child-task-reentry/schemas/summon-request-v4.schema.json",
    "mechanics/checkpoint/parts/child-task-reentry/schemas/summon-result-v4.schema.json",
)
OWNER_CONTRACT_FILES = (
    (
        "aoa-agents",
        "skills/aoa-summon/references/summon-request-v4.schema.json",
    ),
    ("aoa-skills", "schemas/task_local_dag_v2.schema.json"),
)
INSTALLER_GIT = "/usr/bin/git"
SHARED_INDEX_MAX_BYTES = 512 * 1024 * 1024
WRAPPER_BOOTSTRAP_PYTHON = Path("/usr/bin/python3")
BWRAP_EXECUTABLE = Path("/usr/bin/bwrap")
WRAPPER_COMPILER = Path("/usr/bin/cc")
WRAPPER_MATERIAL_ROOT = Path("wrapper-bootstrap-materials")
WRAPPER_MATERIAL_RUNTIME_ROOT = Path("/__aoa_external_codex_runtime__")
WRAPPER_MATERIAL_ACTIVE_PATH = WRAPPER_MATERIAL_RUNTIME_ROOT / "active.json"


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


def _descriptor_sha256(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return "sha256:" + digest.hexdigest()


def require_python_executable(path: Path) -> tuple[Path, dict[str, object]]:
    candidate = require_regular_file(path.resolve(), "Python executable")
    if not os.access(candidate, os.X_OK):
        raise InstallError(f"Python executable is not executable: {candidate}")
    probe = (
        "import json,os,platform,sys;"
        "executable=os.stat('/proc/self/exe');"
        "print(json.dumps({'implementation':platform.python_implementation(),"
        "'version':[sys.version_info.major,sys.version_info.minor],"
        "'executable_device':executable.st_dev,"
        "'executable_inode':executable.st_ino},"
        "sort_keys=True,separators=(',',':')))"
    )
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise InstallError(f"Python executable cannot be opened safely: {candidate}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise InstallError(f"Python executable is not a regular file: {candidate}")
        if metadata.st_mode & 0o111 == 0:
            raise InstallError(f"Python executable is not executable: {candidate}")
        elf_magic = os.pread(descriptor, 4, 0)
        if elf_magic != b"\x7fELF":
            raise InstallError(
                "Python executable must be a direct CPython ELF executable, "
                f"not a script or interpreter shim: {candidate}"
            )
        identity = {
            "sha256": _descriptor_sha256(descriptor),
            "size": metadata.st_size,
            "device": metadata.st_dev,
            "inode": metadata.st_ino,
        }
        try:
            completed = subprocess.run(
                [f"/proc/self/fd/{descriptor}", "-I", "-c", probe],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                pass_fds=(descriptor,),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InstallError(
                f"Python executable compatibility probe failed: {candidate}"
            ) from exc
    finally:
        os.close(descriptor)
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
        or payload.get("executable_device") != identity["device"]
        or payload.get("executable_inode") != identity["inode"]
    ):
        raise InstallError(
            "Python executable must be a direct compatible CPython 3.11 or newer: "
            f"{candidate}; expected at least {expected}"
        )
    return candidate, identity


def assert_python_identity_unchanged(
    path: Path,
    expected_identity: dict[str, object],
) -> None:
    try:
        _, observed_identity = require_python_executable(path)
    except InstallError as exc:
        raise InstallError("Python executable identity changed before activation") from exc
    if observed_identity != expected_identity:
        raise InstallError("Python executable identity changed before activation")


def require_snapshot_runtime() -> Path:
    candidate = require_regular_file(
        BWRAP_EXECUTABLE.resolve(),
        "bubblewrap snapshot runtime",
    )
    if not os.access(candidate, os.X_OK):
        raise InstallError(f"bubblewrap snapshot runtime is not executable: {candidate}")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise InstallError(
            f"bubblewrap snapshot runtime cannot be opened safely: {candidate}"
        ) from exc
    data_descriptor = os.memfd_create("aoa-bwrap-admission", os.MFD_CLOEXEC)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o111 == 0:
            raise InstallError(f"bubblewrap snapshot runtime is invalid: {candidate}")
        os.write(data_descriptor, b"verified\n")
        os.lseek(data_descriptor, 0, os.SEEK_SET)
        try:
            completed = subprocess.run(
                [
                    f"/proc/self/fd/{descriptor}",
                    "--bind",
                    "/",
                    "/",
                    "--tmpfs",
                    "/tmp",
                    "--perms",
                    "0444",
                    "--ro-bind-data",
                    str(data_descriptor),
                    "/tmp/aoa-external-codex-bwrap-probe",
                    "--",
                    "/usr/bin/test",
                    "-r",
                    "/tmp/aoa-external-codex-bwrap-probe",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                pass_fds=(descriptor, data_descriptor),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InstallError(
                f"bubblewrap snapshot runtime compatibility probe failed: {candidate}"
            ) from exc
    finally:
        os.close(data_descriptor)
        os.close(descriptor)
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        suffix = f": {detail}" if detail else ""
        raise InstallError(
            f"bubblewrap snapshot runtime compatibility probe failed: {candidate}{suffix}"
        )
    return candidate


def validate_static_wrapper(raw: bytes) -> None:
    if len(raw) < 64 or raw[:6] != b"\x7fELF\x02\x01":
        raise InstallError("external Codex static bootstrap is not ELF64 little-endian")
    executable_type, machine = struct.unpack_from("<HH", raw, 16)
    if executable_type != 2 or machine != 62:
        raise InstallError("external Codex static bootstrap must be x86_64 ET_EXEC")
    program_offset = struct.unpack_from("<Q", raw, 32)[0]
    program_size, program_count = struct.unpack_from("<HH", raw, 54)
    if program_size < 56 or program_count == 0:
        raise InstallError("external Codex static bootstrap program table is invalid")
    if program_offset + program_size * program_count > len(raw):
        raise InstallError("external Codex static bootstrap program table is truncated")
    for index in range(program_count):
        program_type = struct.unpack_from(
            "<I",
            raw,
            program_offset + index * program_size,
        )[0]
        if program_type == 2:
            raise InstallError(
                "external Codex static bootstrap must not contain PT_DYNAMIC"
            )
        if program_type == 3:
            raise InstallError(
                "external Codex static bootstrap must not contain PT_INTERP"
            )


def build_static_wrapper(source_path: Path | None = None) -> bytes:
    source = require_regular_file(
        source_path
        if source_path is not None
        else Path(__file__).resolve().parent / "external_codex_static_bootstrap.S",
        "external Codex static bootstrap source",
    )
    compiler = require_regular_file(
        WRAPPER_COMPILER.resolve(),
        "external Codex static bootstrap compiler",
    )
    if not os.access(compiler, os.X_OK):
        raise InstallError(f"external Codex static bootstrap compiler is not executable: {compiler}")
    with tempfile.TemporaryDirectory(prefix="aoa-external-codex-bootstrap-") as temporary:
        output = Path(temporary) / "bootstrap"
        try:
            completed = subprocess.run(
                [
                    str(compiler),
                    "-nostdlib",
                    "-static",
                    "-Wl,--build-id=none",
                    "-Wl,-z,noexecstack",
                    "-Wl,-s",
                    "-o",
                    str(output),
                    str(source),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
                env={
                    "HOME": "/nonexistent",
                    "LANG": "C.UTF-8",
                    "PATH": "/usr/bin:/bin",
                },
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InstallError("cannot build external Codex static bootstrap") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip()
            suffix = f": {detail}" if detail else ""
            raise InstallError(f"cannot build external Codex static bootstrap{suffix}")
        raw = require_regular_file(
            output,
            "built external Codex static bootstrap",
        ).read_bytes()
    validate_static_wrapper(raw)
    return raw


def static_wrapper_for_release(release_root: Path) -> bytes:
    packaged_source = release_root / "runtime/external_codex_static_bootstrap.S"
    if packaged_source.exists() or packaged_source.is_symlink():
        return build_static_wrapper(packaged_source)
    # Compatibility rollback for release manifests created before the static
    # launcher source entered the packaged runtime closure.
    return build_static_wrapper()


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


def _copy_verified_shared_index(
    root: Path,
    git_dir: Path,
    *,
    object_format: str,
    expected_length: int,
) -> None:
    """Verify and copy one split-index backing inode without reopening it."""

    try:
        completed = subprocess.run(
            [INSTALLER_GIT, "-C", str(root), "rev-parse", "--shared-index-path"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            env=_base_installer_git_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError(f"cannot inspect shared Git index for {root}: {exc}") from exc
    value = completed.stdout.strip()
    if completed.returncode != 0:
        raise InstallError(f"cannot inspect shared Git index for {root}")
    if not value:
        return
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    shared_name = candidate.name
    shared_digest = shared_name.removeprefix("sharedindex.")
    if (
        not shared_name.startswith("sharedindex.")
        or len(shared_digest) != expected_length
        or re.fullmatch(r"[0-9a-f]+", shared_digest) is None
    ):
        raise InstallError(f"invalid source shared Git index name for {root}")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(candidate, flags)
        metadata = os.fstat(descriptor)
        digest_size = expected_length // 2
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size <= digest_size
            or metadata.st_size > SHARED_INDEX_MAX_BYTES
        ):
            raise InstallError(f"invalid source shared Git index file for {root}")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise InstallError(f"source shared Git index changed while reading {root}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise InstallError(f"source shared Git index changed while reading {root}")
        payload = b"".join(chunks)
        content, footer = payload[:-digest_size], payload[-digest_size:]
        computed = hashlib.new(object_format, content).digest()
        if computed != footer or computed.hex() != shared_digest:
            raise InstallError(f"source shared Git index digest mismatch for {root}")

        destination = git_dir / shared_name
        output = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o400,
        )
        try:
            remaining_payload = memoryview(payload)
            while remaining_payload:
                written = os.write(output, remaining_payload)
                if written <= 0:
                    raise OSError("short write while copying shared Git index")
                remaining_payload = remaining_payload[written:]
            os.fsync(output)
        finally:
            os.close(output)
    except OSError as exc:
        raise InstallError(f"cannot copy source shared Git index for {root}: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


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
        _copy_verified_shared_index(
            root,
            git_dir,
            object_format=object_format,
            expected_length=expected_length,
        )
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
    return f'''#!/bin/false
from __future__ import annotations
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(os.environ["AOA_EXTERNAL_CODEX_VERIFIED_RELEASE_ROOT"])
SDK = ROOT / "sdk/src"
TARGET = ROOT / "runtime/{target}"
sys.path.insert(0, str(SDK))
sys.argv[0] = str(TARGET)
runpy.run_path(str(TARGET), run_name="__main__")
'''


def wrapper_bootstrap_text(
    active_path: Path,
    entrypoint_name: str,
) -> str:
    # The wrapper's isolated bootstrap is stable across runtime-interpreter
    # changes. It reads the interpreter only from the atomically published
    # active record, so staged wrapper replacement remains callable before and
    # after that single publication point.
    bootstrap = '''from __future__ import annotations
import fcntl
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

ACTIVE = Path(__AOA_ACTIVE_PATH__)
RUNTIME_ROOT = Path(__AOA_RUNTIME_ROOT__)
ENTRYPOINT_NAME = __AOA_ENTRYPOINT_NAME__
BWRAP = Path("/usr/bin/bwrap")

FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
DIRECTORY_FLAGS = FILE_FLAGS | os.O_DIRECTORY

def read_all(descriptor, maximum=None):
    chunks = []
    total = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if maximum is not None and total > maximum:
            raise SystemExit("external Codex control file exceeds its size limit")
        chunks.append(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return b"".join(chunks)

def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

def sealed_memfd(name, raw):
    descriptor = os.memfd_create(name, os.MFD_ALLOW_SEALING)
    offset = 0
    while offset < len(raw):
        offset += os.write(descriptor, raw[offset:])
    os.fchmod(descriptor, 0o500)
    fcntl.fcntl(
        descriptor,
        fcntl.F_ADD_SEALS,
        fcntl.F_SEAL_WRITE
        | fcntl.F_SEAL_GROW
        | fcntl.F_SEAL_SHRINK
        | fcntl.F_SEAL_SEAL,
    )
    os.lseek(descriptor, 0, os.SEEK_SET)
    return descriptor

def open_regular_at(root_descriptor, relative):
    path = Path(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise SystemExit(f"external Codex release path is unsafe: {relative}")
    directory_descriptor = os.dup(root_descriptor)
    try:
        for component in path.parts[:-1]:
            child_descriptor = os.open(
                component,
                DIRECTORY_FLAGS,
                dir_fd=directory_descriptor,
            )
            child_metadata = os.fstat(child_descriptor)
            if not stat.S_ISDIR(child_metadata.st_mode):
                os.close(child_descriptor)
                raise SystemExit(
                    f"external Codex release directory is invalid: {relative}"
                )
            os.close(directory_descriptor)
            directory_descriptor = child_descriptor
        descriptor = os.open(
            path.parts[-1],
            FILE_FLAGS,
            dir_fd=directory_descriptor,
        )
    finally:
        os.close(directory_descriptor)
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise SystemExit(f"external Codex release file is invalid: {relative}")
    return descriptor, metadata

def release_closure(root_descriptor):
    files = set()
    directories = set()
    pending = [(os.dup(root_descriptor), Path("."))]
    while pending:
        directory_descriptor, relative_root = pending.pop()
        try:
            for name in os.listdir(directory_descriptor):
                metadata = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                relative = (
                    Path(name)
                    if relative_root == Path(".")
                    else relative_root / name
                )
                if stat.S_ISREG(metadata.st_mode):
                    files.add(relative)
                elif stat.S_ISDIR(metadata.st_mode):
                    child_descriptor = os.open(
                        name,
                        DIRECTORY_FLAGS,
                        dir_fd=directory_descriptor,
                    )
                    child_metadata = os.fstat(child_descriptor)
                    if not stat.S_ISDIR(child_metadata.st_mode):
                        os.close(child_descriptor)
                        raise SystemExit(
                            f"external Codex release directory drifted: {relative}"
                        )
                    directories.add(relative)
                    pending.append((child_descriptor, relative))
                else:
                    raise SystemExit(
                        f"external Codex release entry is invalid: {relative}"
                    )
        finally:
            os.close(directory_descriptor)
    return files, directories

try:
    active_descriptor = os.open(ACTIVE, FILE_FLAGS)
except OSError as exc:
    raise SystemExit(
        f"external Codex active release is unavailable: {ACTIVE}"
    ) from exc
try:
    active_metadata = os.fstat(active_descriptor)
    if not stat.S_ISREG(active_metadata.st_mode):
        raise SystemExit(f"external Codex active release is invalid: {ACTIVE}")
    record = json.loads(read_all(active_descriptor, 1024 * 1024))
finally:
    os.close(active_descriptor)
if (
    not isinstance(record, dict)
    or record.get("schema_version")
    != "abyss_stack_external_codex_active_release_v1"
):
    raise SystemExit("external Codex active release schema is invalid")
python_value = record.get("python_executable")
python_identity = record.get("python_identity")
if not isinstance(python_value, str) or not isinstance(python_identity, dict):
    raise SystemExit("external Codex active interpreter is invalid")
runtime_python = Path(python_value)
if not runtime_python.is_absolute():
    raise SystemExit(f"external Codex active interpreter is unavailable: {runtime_python}")
release_id = record["release_id"]
if not isinstance(release_id, str) or not release_id.startswith("sha256-") or len(release_id) != 71 or any(character not in "0123456789abcdef" for character in release_id[7:]):
    raise SystemExit(f"external Codex release id is invalid: {release_id}")
raw_release_root = Path(record["release_root"])
if raw_release_root.is_symlink() or not raw_release_root.is_dir():
    raise SystemExit(f"external Codex release is unavailable: {raw_release_root}")
release_root = raw_release_root.resolve()
releases_root = (RUNTIME_ROOT / "releases").resolve()
try:
    release_root.relative_to(releases_root)
except ValueError as exc:
    raise SystemExit(f"external Codex release escapes runtime root: {release_root}") from exc
if release_root.parent != releases_root or release_root.name != release_id:
    raise SystemExit(f"external Codex release coordinate is invalid: {release_root}")
try:
    release_descriptor = os.open(release_root, DIRECTORY_FLAGS)
except OSError as exc:
    raise SystemExit(f"external Codex release is unavailable: {release_root}") from exc
release_metadata = os.fstat(release_descriptor)
if not stat.S_ISDIR(release_metadata.st_mode):
    os.close(release_descriptor)
    raise SystemExit(f"external Codex release is invalid: {release_root}")

manifest_descriptor, _ = open_regular_at(
    release_descriptor,
    "release-manifest.json",
)
try:
    manifest_raw = read_all(manifest_descriptor, 16 * 1024 * 1024)
    manifest = json.loads(manifest_raw)
finally:
    os.close(manifest_descriptor)
if not isinstance(manifest, dict):
    os.close(release_descriptor)
    raise SystemExit("external Codex release manifest is invalid")
rows = manifest.get("files")
identity = {
    "schema_version": "abyss_stack_external_codex_release_manifest_v1",
    "files": rows,
}
expected_digest = digest(canonical(identity))
if (
    manifest.get("schema_version") != identity["schema_version"]
    or manifest.get("release_digest") != expected_digest
    or manifest.get("release_id") != expected_digest.replace("sha256:", "sha256-")
    or record.get("release_digest") != expected_digest
    or manifest.get("release_id") != release_id
    or not isinstance(rows, list)
):
    os.close(release_descriptor)
    raise SystemExit("external Codex release manifest identity is invalid")

expected_files = {Path("release-manifest.json")}
expected_directories = set()
snapshot_descriptors = [
    (
        Path("release-manifest.json"),
        sealed_memfd("aoa-external-codex-release-manifest", manifest_raw),
    )
]
entrypoint_present = False
for row in rows:
    if not isinstance(row, dict):
        os.close(release_descriptor)
        raise SystemExit("external Codex release manifest row is invalid")
    relative = Path(str(row.get("path", "")))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        os.close(release_descriptor)
        raise SystemExit(f"external Codex release path is unsafe: {relative}")
    if relative in expected_files:
        os.close(release_descriptor)
        raise SystemExit(f"external Codex release path is duplicated: {relative}")
    expected_files.add(relative)
    expected_directories.update(relative.parents)
    descriptor, metadata = open_regular_at(release_descriptor, relative)
    raw = read_all(descriptor)
    if metadata.st_size != row.get("size") or digest(raw) != row.get("sha256"):
        os.close(descriptor)
        os.close(release_descriptor)
        raise SystemExit(f"external Codex release file drift: {relative}")
    snapshot_descriptors.append(
        (
            relative,
            sealed_memfd("aoa-external-codex-release-file", raw),
        )
    )
    if relative == Path(ENTRYPOINT_NAME):
        entrypoint_present = True
    os.close(descriptor)
expected_directories.discard(Path("."))
actual_files, actual_directories = release_closure(release_descriptor)
if (
    actual_files != expected_files
    or actual_directories != expected_directories
    or not entrypoint_present
):
    os.close(release_descriptor)
    raise SystemExit("external Codex release manifest closure mismatch")

try:
    python_descriptor = os.open(runtime_python, FILE_FLAGS)
except OSError as exc:
    os.close(release_descriptor)
    raise SystemExit(
        f"external Codex active interpreter is unavailable: {runtime_python}"
    ) from exc
python_metadata = os.fstat(python_descriptor)
python_raw = read_all(python_descriptor)
observed_python_identity = {
    "sha256": digest(python_raw),
    "size": python_metadata.st_size,
    "device": python_metadata.st_dev,
    "inode": python_metadata.st_ino,
}
if (
    not stat.S_ISREG(python_metadata.st_mode)
    or python_metadata.st_mode & 0o111 == 0
    or observed_python_identity != python_identity
):
    os.close(python_descriptor)
    os.close(release_descriptor)
    raise SystemExit("external Codex active interpreter identity drift")
verified_python_descriptor = sealed_memfd(
    "aoa-external-codex-python",
    python_raw,
)
os.close(python_descriptor)

try:
    bwrap_descriptor = os.open(BWRAP, FILE_FLAGS)
except OSError as exc:
    os.close(release_descriptor)
    raise SystemExit(
        f"external Codex snapshot runtime is unavailable: {BWRAP}"
    ) from exc
bwrap_metadata = os.fstat(bwrap_descriptor)
if not stat.S_ISREG(bwrap_metadata.st_mode) or bwrap_metadata.st_mode & 0o111 == 0:
    os.close(bwrap_descriptor)
    os.close(release_descriptor)
    raise SystemExit(f"external Codex snapshot runtime is invalid: {BWRAP}")
verified_bwrap_descriptor = sealed_memfd(
    "aoa-external-codex-bwrap",
    read_all(bwrap_descriptor),
)
os.close(bwrap_descriptor)
if os.execve not in os.supports_fd:
    os.close(verified_bwrap_descriptor)
    os.close(verified_python_descriptor)
    os.close(release_descriptor)
    raise SystemExit("external Codex host cannot execute a verified snapshot runtime")

snapshot_parent = Path("/mnt")
snapshot_root = snapshot_parent / "aoa-external-codex-release"
snapshot_python = snapshot_root / ".verified-python"
snapshot_bootstrap = (
    "from pathlib import Path\\n"
    "import os\\n"
    "import runpy\\n"
    "import sys\\n"
    "runtime_python = Path(sys.argv[1])\\n"
    "entrypoint = Path(sys.argv[2])\\n"
    "running = os.stat('/proc/self/exe')\\n"
    "admitted = runtime_python.stat()\\n"
    "if (running.st_dev, running.st_ino) != (admitted.st_dev, admitted.st_ino):\\n"
    "    raise SystemExit('external Codex runtime interpreter delegated after admission')\\n"
    "sys.argv = [str(entrypoint), *sys.argv[3:]]\\n"
    "runpy.run_path(str(entrypoint), run_name='__main__')\\n"
)
bwrap_arguments = [
    str(BWRAP),
    "--die-with-parent",
    "--bind",
    "/",
    "/",
    "--dev",
    "/dev",
    "--tmpfs",
    str(snapshot_parent),
    "--dir",
    str(snapshot_root),
]
for relative in sorted(expected_directories, key=lambda item: (len(item.parts), str(item))):
    bwrap_arguments.extend(("--dir", str(snapshot_root / relative)))
for relative, descriptor in sorted(snapshot_descriptors, key=lambda item: str(item[0])):
    os.set_inheritable(descriptor, True)
    bwrap_arguments.extend(
        (
            "--perms",
            "0444",
            "--ro-bind-data",
            str(descriptor),
            str(snapshot_root / relative),
        )
    )
os.set_inheritable(verified_python_descriptor, True)
bwrap_arguments.extend(
    (
        "--perms",
        "0500",
        "--ro-bind-data",
        str(verified_python_descriptor),
        str(snapshot_python),
        "--remount-ro",
        str(snapshot_parent),
        "--",
        str(snapshot_python),
        "-I",
        "-B",
        "-c",
        snapshot_bootstrap,
        str(snapshot_python),
        str(snapshot_root / ENTRYPOINT_NAME),
        *sys.argv[1:],
    )
)
os.set_inheritable(verified_bwrap_descriptor, True)
environment = dict(os.environ)
environment["AOA_EXTERNAL_CODEX_VERIFIED_RELEASE_ROOT"] = str(snapshot_root)
os.close(release_descriptor)
os.execve(
    verified_bwrap_descriptor,
    bwrap_arguments,
    environment,
)
'''
    replacements = {
        "__AOA_ACTIVE_PATH__": repr(str(active_path)),
        "__AOA_RUNTIME_ROOT__": repr(str(active_path.parent)),
        "__AOA_ENTRYPOINT_NAME__": repr(entrypoint_name),
    }
    for marker, value in replacements.items():
        if bootstrap.count(marker) != 1:
            raise InstallError(f"external Codex wrapper marker is invalid: {marker}")
        bootstrap = bootstrap.replace(marker, value)
    return "#!/bin/false\n" + bootstrap


def wrapper_paths(bin_dir: Path, name: str) -> tuple[Path, Path]:
    launcher = bin_dir / name
    companion = Path(str(launcher) + ".bootstrap.py")
    return launcher, companion


def wrapper_material_path(release_root: Path, entrypoint_name: str) -> Path:
    return release_root / WRAPPER_MATERIAL_ROOT / f"{entrypoint_name}.bootstrap.py"


def wrapper_material_text(entrypoint_name: str) -> str:
    return wrapper_bootstrap_text(WRAPPER_MATERIAL_ACTIVE_PATH, entrypoint_name)


def wrapper_bootstrap_for_release(
    release_root: Path,
    active_path: Path,
    entrypoint_name: str,
) -> bytes:
    material_path = wrapper_material_path(release_root, entrypoint_name)
    if not material_path.exists():
        # Historical releases predate content-addressed wrapper materials.
        # Keep them rollback-callable, but every newly staged release carries
        # and executes its exact admitted bootstrap material.
        return wrapper_bootstrap_text(active_path, entrypoint_name).encode("utf-8")
    material = require_regular_file(
        material_path,
        f"wrapper bootstrap material {entrypoint_name}",
    ).read_text(encoding="utf-8")
    replacements = {
        repr(str(WRAPPER_MATERIAL_ACTIVE_PATH)): repr(str(active_path)),
        repr(str(WRAPPER_MATERIAL_RUNTIME_ROOT)): repr(str(active_path.parent)),
    }
    for marker, value in replacements.items():
        if material.count(marker) != 1:
            raise InstallError(
                f"release wrapper material marker is invalid: {entrypoint_name}"
            )
        material = material.replace(marker, value)
    return material.encode("utf-8")


def publish_wrappers(
    bin_dir: Path,
    runtime_root: Path,
    release_root: Path,
    active_path: Path,
    wrappers: dict[str, str],
    static_launcher: bytes,
) -> dict[str, str | None]:
    backups: dict[str, str | None] = {}
    for name, entrypoint in wrappers.items():
        launcher, companion = wrapper_paths(bin_dir, name)
        companion_raw = wrapper_bootstrap_for_release(
            release_root, active_path, entrypoint
        )
        for key, path, expected, mode in (
            (f"{name}.bootstrap.py", companion, companion_raw, 0o444),
            (name, launcher, static_launcher, 0o755),
        ):
            if (
                path.exists()
                and not path.is_symlink()
                and path.read_bytes() == expected
                and stat.S_IMODE(path.stat().st_mode) == mode
            ):
                backups[key] = None
                continue
            backups[key] = backup_existing_wrapper(path, runtime_root)
            atomic_write(path, expected, mode)
    return backups


def wrapper_status_rows(
    bin_dir: Path,
    release_root: Path,
    active_path: Path,
    wrappers: dict[str, str],
    static_launcher: bytes,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for name, entrypoint in wrappers.items():
        launcher, companion = wrapper_paths(bin_dir, name)
        launcher = require_regular_file(launcher, f"wrapper {name}")
        companion = require_regular_file(
            companion,
            f"wrapper bootstrap {name}",
        )
        expected_companion = wrapper_bootstrap_for_release(
            release_root, active_path, entrypoint
        )
        launcher_current = (
            launcher.read_bytes() == static_launcher
            and stat.S_IMODE(launcher.stat().st_mode) == 0o755
        )
        companion_current = (
            companion.read_bytes() == expected_companion
            and stat.S_IMODE(companion.stat().st_mode) == 0o444
        )
        result[name] = {
            "path": str(launcher),
            "digest": sha256_file(launcher),
            "bootstrap_path": str(companion),
            "bootstrap_digest": sha256_file(companion),
            "current": launcher_current and companion_current,
        }
        if not result[name]["current"]:
            raise InstallError(f"wrapper drift: {launcher}")
    return result


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
    for entrypoint_name in entrypoints:
        raw = wrapper_material_text(entrypoint_name).encode("utf-8")
        rows.append(
            {
                "path": (
                    WRAPPER_MATERIAL_ROOT / f"{entrypoint_name}.bootstrap.py"
                ).as_posix(),
                "sha256": sha256_bytes(raw),
                "size": len(raw),
            }
        )
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
            os.chmod(path, 0o444)
        for entrypoint_name in (
            "agent-entrypoint.py",
            "bind-entrypoint.py",
            "study-entrypoint.py",
        ):
            path = staging / WRAPPER_MATERIAL_ROOT / f"{entrypoint_name}.bootstrap.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                wrapper_material_text(entrypoint_name),
                encoding="utf-8",
                newline="\n",
            )
            os.chmod(path, 0o444)
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


def prepare_release(
    source_root: Path,
    sdk_root: Path,
    agents_root: Path,
    skills_root: Path,
    runtime_root: Path,
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
    python_executable, python_identity = require_python_executable(
        python_executable
    )
    require_python_executable(WRAPPER_BOOTSTRAP_PYTHON)
    require_snapshot_runtime()
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
    verify_release(release_root)
    assert_python_identity_unchanged(python_executable, python_identity)
    return {
        "release_root": release_root,
        "release_created": created,
        "manifest": manifest,
        "source": source_posture,
        "sdk": sdk_posture,
        "agents": agents_posture,
        "skills": skills_posture,
        "python_executable": python_executable,
        "python_identity": python_identity,
    }


def stage(
    source_root: Path,
    sdk_root: Path,
    agents_root: Path,
    skills_root: Path,
    runtime_root: Path,
    python_executable: Path,
    *,
    allow_dirty_source: bool,
    allow_dirty_sdk: bool,
    allow_dirty_agents: bool,
    allow_dirty_skills: bool,
) -> dict[str, object]:
    runtime_root = runtime_root.resolve()
    prepared = prepare_release(
        source_root,
        sdk_root,
        agents_root,
        skills_root,
        runtime_root,
        python_executable,
        allow_dirty_source=allow_dirty_source,
        allow_dirty_sdk=allow_dirty_sdk,
        allow_dirty_agents=allow_dirty_agents,
        allow_dirty_skills=allow_dirty_skills,
    )
    manifest = prepared["manifest"]
    release_root = prepared["release_root"]
    if not isinstance(manifest, dict) or not isinstance(release_root, Path):
        raise InstallError("prepared release result is invalid")
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    dirty = any(
        bool(prepared[name].get("dirty"))
        for name in ("source", "sdk", "agents", "skills")
        if isinstance(prepared[name], dict)
    )
    staged = {
        "schema_version": STAGED_SCHEMA_VERSION,
        "release_id": manifest["release_id"],
        "release_digest": manifest["release_digest"],
        "release_root": str(release_root),
        "python_executable": str(prepared["python_executable"]),
        "python_identity": prepared["python_identity"],
        "source": prepared["source"],
        "sdk": prepared["sdk"],
        "agents": prepared["agents"],
        "skills": prepared["skills"],
        "staged_at": now,
        "nonproduction_dirty_source": dirty,
    }
    staged_path = runtime_root / "staged" / f"{manifest['release_id']}.json"
    atomic_write(
        staged_path,
        (json.dumps(staged, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        ),
        0o444,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": "stage",
        "staged": staged,
        "staged_record": str(staged_path),
        "release_created": prepared["release_created"],
    }


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
    runtime_root = runtime_root.resolve()
    bin_dir = bin_dir.resolve()
    prepared = prepare_release(
        source_root,
        sdk_root,
        agents_root,
        skills_root,
        runtime_root,
        python_executable,
        allow_dirty_source=allow_dirty_source,
        allow_dirty_sdk=allow_dirty_sdk,
        allow_dirty_agents=allow_dirty_agents,
        allow_dirty_skills=allow_dirty_skills,
    )
    manifest = prepared["manifest"]
    release_root = prepared["release_root"]
    python_executable = prepared["python_executable"]
    python_identity = prepared["python_identity"]
    source_posture = prepared["source"]
    sdk_posture = prepared["sdk"]
    agents_posture = prepared["agents"]
    skills_posture = prepared["skills"]
    created = bool(prepared["release_created"])
    if (
        not isinstance(manifest, dict)
        or not isinstance(release_root, Path)
        or not isinstance(python_executable, Path)
        or not isinstance(python_identity, dict)
        or not all(
            isinstance(posture, dict)
            for posture in (
                source_posture,
                sdk_posture,
                agents_posture,
                skills_posture,
            )
        )
    ):
        raise InstallError("prepared release result is invalid")
    previous_active = None
    active_path = runtime_root / "active.json"
    if active_path.exists():
        require_regular_file(active_path, "active release record")
        previous_active = json.loads(active_path.read_text(encoding="utf-8"))

    wrappers = {
        "aoa-external-codex-agent": "agent-entrypoint.py",
        "aoa-external-actor-bind": "bind-entrypoint.py",
        "aoa-external-codex-study": "study-entrypoint.py",
    }
    wrapper_backups = publish_wrappers(
        bin_dir,
        runtime_root,
        release_root,
        active_path,
        wrappers,
        static_wrapper_for_release(release_root),
    )

    verify_release(release_root)
    assert_python_identity_unchanged(python_executable, python_identity)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    active = {
        "schema_version": ACTIVE_SCHEMA_VERSION,
        "release_id": manifest["release_id"],
        "release_digest": manifest["release_digest"],
        "release_root": str(release_root),
        "python_executable": str(python_executable),
        "python_identity": python_identity,
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
        "wrappers": {name: str(wrapper_paths(bin_dir, name)[0]) for name in wrappers},
        "wrapper_bootstraps": {
            name: str(wrapper_paths(bin_dir, name)[1]) for name in wrappers
        },
        "wrapper_backups": wrapper_backups,
        "rollback": {
            "command": (
                f"{source_root}/mechanics/governed-execution/parts/"
                "external-codex-agent/install_external_codex_runtime.py activate "
                f"--runtime-root {runtime_root} --bin-dir {bin_dir} "
                f"--release-id {previous_active.get('release_id')}"
            ) if previous_active else "Remove the three newly created launcher/companion pairs and active.json after operator review; the immutable release may be retained.",
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


def release_artifact_subject_digest(release_root: Path) -> str:
    manifest_path = require_regular_file(
        release_root / "release-manifest.json",
        "release manifest",
    )
    digest = sha256_file(manifest_path)
    entry = {
        "path": "release-manifest.json",
        "role": ARTIFACT_SUBJECT_ROLE,
        "bytes": manifest_path.stat().st_size,
        "sha256": digest,
        "sha256_hex": digest.removeprefix("sha256:"),
    }
    return sha256_bytes(canonical_bytes([entry]))


def require_release_id(release_id: str) -> str:
    if (
        not release_id.startswith("sha256-")
        or len(release_id) != 71
        or any(character not in "0123456789abcdef" for character in release_id[7:])
    ):
        raise InstallError("release id must be one exact sha256 content address")
    return release_id


def staged_release(runtime_root: Path, release_id: str) -> dict[str, object]:
    require_release_id(release_id)
    path = require_regular_file(
        runtime_root / "staged" / f"{release_id}.json",
        "staged release record",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != STAGED_SCHEMA_VERSION:
        raise InstallError("staged release schema mismatch")
    if payload.get("release_id") != release_id:
        raise InstallError("staged release id mismatch")
    if payload.get("nonproduction_dirty_source") is not False:
        raise InstallError("artifact-admitted activation requires clean staged sources")
    for owner in ("source", "sdk", "agents", "skills"):
        posture = payload.get(owner)
        if not isinstance(posture, dict) or posture.get("dirty") is not False:
            raise InstallError(
                f"artifact-admitted activation requires a clean staged {owner} posture"
            )
    source = payload.get("source")
    if not isinstance(source, dict):
        raise InstallError("staged abyss-stack source posture is missing")
    source_ref = source.get("head")
    if (
        not isinstance(source_ref, str)
        or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", source_ref) is None
    ):
        raise InstallError("staged abyss-stack source ref is not one exact commit")
    return payload


def artifact_gate_admission(
    abyss_machine_executable: Path,
    registry_dir: Path,
    release_root: Path,
    source_ref: str,
) -> dict[str, object]:
    if not abyss_machine_executable.is_absolute():
        raise InstallError("abyss-machine artifact gate executable must be absolute")
    executable = require_regular_file(
        abyss_machine_executable,
        "abyss-machine artifact gate executable",
    ).resolve()
    if not os.access(executable, os.X_OK):
        raise InstallError(
            f"abyss-machine artifact gate executable is not executable: {executable}"
        )
    registry_dir = require_absolute_directory(registry_dir, "artifact registry")
    subject_digest = release_artifact_subject_digest(release_root)
    command = [
        str(executable),
        "artifacts",
        "trust-gate",
        "--registry-dir",
        str(registry_dir),
        "--artifact-class",
        ARTIFACT_CLASS,
        "--consumer-intent",
        ARTIFACT_CONSUMER_INTENT,
        "--source-repo",
        ARTIFACT_SOURCE_REPO,
        "--source-ref",
        source_ref,
        "--trust-root-mode",
        ARTIFACT_TRUST_ROOT_MODE,
        "--subject-digest",
        subject_digest,
        "--json",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            env={
                "HOME": "/nonexistent",
                "LANG": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
            },
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError("abyss-machine artifact trust gate could not run") from exc
    try:
        gate = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise InstallError("abyss-machine artifact trust gate returned invalid JSON") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or str(gate.get("error") or "denied")
        raise InstallError(f"abyss-machine artifact trust gate failed: {detail}")
    if not isinstance(gate, dict):
        raise InstallError("abyss-machine artifact trust gate returned a non-object")
    decision = gate.get("decision")
    record = gate.get("record")
    inspected = gate.get("inspected_claims")
    if not isinstance(decision, dict) or not isinstance(record, dict):
        raise InstallError("artifact trust gate omitted decision or record evidence")
    if not isinstance(inspected, dict):
        raise InstallError("artifact trust gate omitted inspected claims")
    if (
        gate.get("schema") != ARTIFACT_GATE_SCHEMA_VERSION
        or gate.get("ok") is not True
        or gate.get("verdict") not in {"allow", "warn"}
        or decision.get("allow") is not True
        or decision.get("verdict") != gate.get("verdict")
        or decision.get("consumer_intent") != ARTIFACT_CONSUMER_INTENT
        or decision.get("blockers") != []
        or decision.get("manual_review") != []
        or gate.get("blockers") != []
        or gate.get("manual_review") != []
    ):
        raise InstallError("artifact trust gate did not admit runtime_canary activation")
    expected_record_id = record.get("record_id")
    registry_latest = inspected.get("registry_latest")
    subject_identity = inspected.get("subject_identity")
    source_claim = inspected.get("source")
    trust_root = inspected.get("trust_root")
    subject_store = inspected.get("artifact_subject_store")
    verification = inspected.get("verification")
    if not all(
        isinstance(value, dict)
        for value in (
            registry_latest,
            subject_identity,
            source_claim,
            trust_root,
            subject_store,
            verification,
        )
    ):
        raise InstallError("artifact trust gate inspected claims are incomplete")
    required_controls = set(record.get("required_controls") or [])
    verified_controls = set(record.get("verified_controls") or [])
    record_subject_digest = record.get("subject_digest")
    record_id_payload = {
        "artifact_class": ARTIFACT_CLASS,
        "subject_digest": record_subject_digest,
        "bundle_manifest_ref": ARTIFACT_BUNDLE_MANIFEST_REF,
    }
    computed_record_id = sha256_bytes(canonical_bytes(record_id_payload))
    if (
        gate.get("artifact_class") != ARTIFACT_CLASS
        or gate.get("consumer_intent") != ARTIFACT_CONSUMER_INTENT
        or gate.get("subject_digest") != subject_digest
        or gate.get("record_id") != expected_record_id
        or gate.get("latest_record_id") != expected_record_id
        or record.get("artifact_class") != ARTIFACT_CLASS
        or record.get("artifact_subjects_digest") != subject_digest
        or record.get("bundle_manifest_ref") != ARTIFACT_BUNDLE_MANIFEST_REF
        or record.get("source_repo") != ARTIFACT_SOURCE_REPO
        or record.get("source_ref") != source_ref
        or record.get("trust_root_mode") != ARTIFACT_TRUST_ROOT_MODE
        or record.get("lifecycle_state") != "manually-verified"
        or record.get("latest_eligible") is not True
        or record.get("terminal_state") is not False
        or record.get("verification_ok") is not True
        or not ARTIFACT_REQUIRED_CONTROLS.issubset(required_controls)
        or not ARTIFACT_REQUIRED_CONTROLS.issubset(verified_controls)
        or expected_record_id != computed_record_id
        or registry_latest.get("selected_record_is_latest") is not True
        or subject_identity.get("subject_digest_matched") is not True
        or source_claim.get("source_repo_matched") is not True
        or source_claim.get("source_ref_matched") is not True
        or trust_root.get("trust_root_mode_matched") is not True
        or subject_store.get("ok") is not True
        or subject_store.get("aggregate_digest") != subject_digest
        or verification.get("ok") is not True
    ):
        raise InstallError("artifact trust gate evidence does not bind the staged release")
    return {
        "schema_version": "abyss_stack_external_codex_artifact_admission_v1",
        "gate": gate,
        "gate_command": command,
        "release_manifest_sha256": sha256_file(
            release_root / "release-manifest.json"
        ),
        "artifact_subjects_digest": subject_digest,
        "source_repo": ARTIFACT_SOURCE_REPO,
        "source_ref": source_ref,
    }


def activate(
    runtime_root: Path,
    bin_dir: Path,
    release_id: str,
    python_executable: Path,
    *,
    artifact_admission: dict[str, object] | None = None,
    staged: dict[str, object] | None = None,
) -> dict[str, object]:
    runtime_root = runtime_root.resolve()
    require_release_id(release_id)
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
    python_executable, python_identity = require_python_executable(
        python_executable
    )
    require_python_executable(WRAPPER_BOOTSTRAP_PYTHON)
    require_snapshot_runtime()
    verify_release(release_root)
    assert_python_identity_unchanged(python_executable, python_identity)
    active_path = runtime_root / "active.json"
    previous = json.loads(active_path.read_text(encoding="utf-8")) if active_path.exists() else None
    wrappers = {
        "aoa-external-codex-agent": "agent-entrypoint.py",
        "aoa-external-actor-bind": "bind-entrypoint.py",
        "aoa-external-codex-study": "study-entrypoint.py",
    }
    publish_wrappers(
        bin_dir.resolve(),
        runtime_root,
        release_root,
        active_path,
        wrappers,
        static_wrapper_for_release(release_root),
    )
    verify_release(release_root)
    assert_python_identity_unchanged(python_executable, python_identity)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    active = {
        "schema_version": ACTIVE_SCHEMA_VERSION,
        "release_id": release_id,
        "release_digest": manifest["release_digest"],
        "release_root": str(release_root),
        "python_executable": str(python_executable),
        "python_identity": python_identity,
        "source": staged.get("source") if staged else None,
        "sdk": staged.get("sdk") if staged else None,
        "agents": staged.get("agents") if staged else None,
        "skills": staged.get("skills") if staged else None,
        "installed_at": now,
        "previous_release_id": previous.get("release_id") if previous else None,
        "nonproduction_dirty_source": (
            staged.get("nonproduction_dirty_source") if staged else True
        ),
        "artifact_admission": artifact_admission,
    }
    atomic_write(
        active_path,
        (json.dumps(active, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        0o644,
    )
    return {"schema_version": SCHEMA_VERSION, "operation": "activate", "active": active}


def activate_admitted(
    runtime_root: Path,
    bin_dir: Path,
    release_id: str,
    python_executable: Path,
    abyss_machine_executable: Path,
    registry_dir: Path,
) -> dict[str, object]:
    runtime_root = runtime_root.resolve()
    staged = staged_release(runtime_root, release_id)
    release_root = Path(str(staged.get("release_root") or ""))
    expected_root = (runtime_root / "releases" / release_id).resolve()
    if release_root != expected_root:
        raise InstallError("staged release root does not match the activation target")
    manifest = verify_release(release_root)
    if (
        manifest.get("release_id") != staged.get("release_id")
        or manifest.get("release_digest") != staged.get("release_digest")
    ):
        raise InstallError("staged release record differs from its verified manifest")
    staged_python = staged.get("python_executable")
    if (
        not isinstance(staged_python, str)
        or python_executable.resolve() != Path(staged_python)
    ):
        raise InstallError("activation Python differs from the staged interpreter")
    source = staged.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("head"), str):
        raise InstallError("staged source ref is missing")
    admission = artifact_gate_admission(
        abyss_machine_executable,
        registry_dir,
        release_root,
        source["head"],
    )
    result = activate(
        runtime_root,
        bin_dir,
        release_id,
        python_executable,
        artifact_admission=admission,
        staged=staged,
    )
    result["operation"] = "activate-admitted"
    return result


def recorded_artifact_admission_status(
    active: dict[str, object],
    release_root: Path,
) -> dict[str, object]:
    admission = active.get("artifact_admission")
    if admission is None:
        return {"status": "not_recorded", "admitted": False}
    if not isinstance(admission, dict):
        raise InstallError("active artifact admission is invalid")
    gate = admission.get("gate")
    source = active.get("source")
    if not isinstance(gate, dict) or not isinstance(source, dict):
        raise InstallError("active artifact admission lost gate or source evidence")
    record = gate.get("record")
    if not isinstance(record, dict):
        raise InstallError("active artifact admission lost registry record evidence")
    expected_subject_digest = release_artifact_subject_digest(release_root)
    expected_manifest_digest = sha256_file(release_root / "release-manifest.json")
    source_ref = source.get("head")
    record_id_payload = {
        "artifact_class": ARTIFACT_CLASS,
        "subject_digest": record.get("subject_digest"),
        "bundle_manifest_ref": ARTIFACT_BUNDLE_MANIFEST_REF,
    }
    expected_record_id = sha256_bytes(canonical_bytes(record_id_payload))
    if (
        admission.get("schema_version")
        != "abyss_stack_external_codex_artifact_admission_v1"
        or admission.get("artifact_subjects_digest") != expected_subject_digest
        or admission.get("release_manifest_sha256") != expected_manifest_digest
        or admission.get("source_repo") != ARTIFACT_SOURCE_REPO
        or admission.get("source_ref") != source_ref
        or gate.get("schema") != ARTIFACT_GATE_SCHEMA_VERSION
        or gate.get("ok") is not True
        or gate.get("verdict") not in {"allow", "warn"}
        or gate.get("artifact_class") != ARTIFACT_CLASS
        or gate.get("consumer_intent") != ARTIFACT_CONSUMER_INTENT
        or gate.get("subject_digest") != expected_subject_digest
        or gate.get("record_id") != expected_record_id
        or gate.get("latest_record_id") != expected_record_id
        or record.get("record_id") != expected_record_id
        or record.get("artifact_subjects_digest") != expected_subject_digest
        or record.get("source_repo") != ARTIFACT_SOURCE_REPO
        or record.get("source_ref") != source_ref
        or record.get("trust_root_mode") != ARTIFACT_TRUST_ROOT_MODE
        or record.get("terminal_state") is not False
    ):
        raise InstallError("active artifact admission differs from the verified release")
    return {
        "status": "recorded_and_bound",
        "admitted": True,
        "verdict": gate.get("verdict"),
        "record_id": expected_record_id,
        "artifact_subjects_digest": expected_subject_digest,
        "source_ref": source_ref,
        "warnings": gate.get("warnings") or [],
    }


def status(runtime_root: Path, bin_dir: Path) -> dict[str, object]:
    runtime_root = runtime_root.resolve()
    active_path = require_regular_file(runtime_root / "active.json", "active release record")
    active = json.loads(active_path.read_text(encoding="utf-8"))
    if active.get("schema_version") != ACTIVE_SCHEMA_VERSION:
        raise InstallError("active release schema mismatch")
    python_value = active.get("python_executable")
    if not isinstance(python_value, str):
        raise InstallError("active Python executable is invalid")
    try:
        _, observed_python_identity = require_python_executable(Path(python_value))
    except InstallError as exc:
        raise InstallError(
            f"active Python executable identity drift: {exc}"
        ) from exc
    if active.get("python_identity") != observed_python_identity:
        raise InstallError("active Python executable identity drift")
    require_python_executable(WRAPPER_BOOTSTRAP_PYTHON)
    require_snapshot_runtime()
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
    artifact_admission = recorded_artifact_admission_status(active, release_root)
    wrappers = {
        "aoa-external-codex-agent": "agent-entrypoint.py",
        "aoa-external-actor-bind": "bind-entrypoint.py",
        "aoa-external-codex-study": "study-entrypoint.py",
    }
    wrapper_status = wrapper_status_rows(
        bin_dir.resolve(),
        release_root,
        active_path,
        wrappers,
        static_wrapper_for_release(release_root),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": "status",
        "healthy": True,
        "active": active,
        "manifest": manifest,
        "artifact_admission": artifact_admission,
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
    stage_parser = subparsers.add_parser("stage")
    stage_parser.add_argument("--source-root", type=Path, required=True)
    stage_parser.add_argument("--sdk-root", type=Path, required=True)
    stage_parser.add_argument("--agents-root", type=Path, required=True)
    stage_parser.add_argument("--skills-root", type=Path, required=True)
    stage_parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    stage_parser.add_argument("--python", type=Path, default=Path(sys.executable))
    stage_parser.add_argument("--allow-dirty-source", action="store_true")
    stage_parser.add_argument("--allow-dirty-sdk", action="store_true")
    stage_parser.add_argument("--allow-dirty-agents", action="store_true")
    stage_parser.add_argument("--allow-dirty-skills", action="store_true")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    status_parser.add_argument("--bin-dir", type=Path, default=DEFAULT_BIN_DIR)
    activate_parser = subparsers.add_parser("activate")
    activate_parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    activate_parser.add_argument("--bin-dir", type=Path, default=DEFAULT_BIN_DIR)
    activate_parser.add_argument("--release-id", required=True)
    activate_parser.add_argument("--python", type=Path, default=Path(sys.executable))
    admitted_parser = subparsers.add_parser("activate-admitted")
    admitted_parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    admitted_parser.add_argument("--bin-dir", type=Path, default=DEFAULT_BIN_DIR)
    admitted_parser.add_argument("--release-id", required=True)
    admitted_parser.add_argument("--python", type=Path, default=Path(sys.executable))
    admitted_parser.add_argument("--abyss-machine", type=Path, required=True)
    admitted_parser.add_argument("--artifact-registry-dir", type=Path, required=True)
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
        elif args.command == "stage":
            payload = stage(
                args.source_root,
                args.sdk_root,
                args.agents_root,
                args.skills_root,
                args.runtime_root,
                args.python,
                allow_dirty_source=args.allow_dirty_source,
                allow_dirty_sdk=args.allow_dirty_sdk,
                allow_dirty_agents=args.allow_dirty_agents,
                allow_dirty_skills=args.allow_dirty_skills,
            )
        elif args.command == "activate":
            payload = activate(args.runtime_root, args.bin_dir, args.release_id, args.python)
        elif args.command == "activate-admitted":
            payload = activate_admitted(
                args.runtime_root,
                args.bin_dir,
                args.release_id,
                args.python,
                args.abyss_machine,
                args.artifact_registry_dir,
            )
        else:
            payload = status(args.runtime_root, args.bin_dir)
    except (InstallError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, "result": payload}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
