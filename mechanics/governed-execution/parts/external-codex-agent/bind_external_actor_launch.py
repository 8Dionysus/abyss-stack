#!/usr/bin/env python3
"""Bind exact owner-selected artifacts into one non-starting external actor launch."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


PART_ROOT = Path(__file__).resolve().parent
if str(PART_ROOT) not in sys.path:
    sys.path.insert(0, str(PART_ROOT))

from external_codex_agent import (  # noqa: E402
    LAUNCH_SCHEMA_PATH,
    ExternalCodexRuntimeError,
    load_json,
    sha256_bytes,
    validate_json,
)


PROFILE_PATH = PART_ROOT / "runtime-profile.v1.json"
MANIFEST_SCHEMA_PATH = PART_ROOT / "schemas/external-actor-launch-manifest.schema.json"
RESPONSE_SCHEMA_VERSION = "abyss_stack_external_actor_launch_binding_response_v1"
BINDER_GIT = "/usr/bin/git"
COORDINATE_KEYS = (
    "plan",
    "incarnation_binding",
    "model_realization",
    "task",
    "runtime_profile",
    "role_contract",
    "result_schema",
)


class LaunchBindingError(RuntimeError):
    pass


def _regular(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise LaunchBindingError(f"{label} must be an absolute regular non-symlink file")
    return path


def _directory(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise LaunchBindingError(f"{label} must be an absolute real directory")
    return path.resolve()


def _digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _git_head(workspace: Path) -> str:
    environment = {
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
    try:
        completed = subprocess.run(
            [BINDER_GIT, "-C", str(workspace), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LaunchBindingError("cannot inspect exact workspace Git HEAD") from exc
    head = completed.stdout.strip()
    if completed.returncode != 0 or len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise LaunchBindingError("workspace has no exact Git HEAD")
    return head


def _write_exact(path: Path, payload: Mapping[str, Any]) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise LaunchBindingError("output must be an absolute non-symlink path")
    parent = _directory(path.parent, "output parent")
    path = parent / path.name
    raw = (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    try:
        remaining = memoryview(raw)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("short write while binding external actor launch")
            remaining = remaining[written:]
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        path.unlink(missing_ok=True)
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def bind(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = load_json(
        _regular(manifest_path, "launch manifest"),
        label="external actor launch manifest",
    )
    validate_json(
        manifest,
        MANIFEST_SCHEMA_PATH,
        label="external actor launch manifest",
    )
    profile_path = _regular(Path(manifest["artifacts"]["runtime_profile"]), "runtime profile")
    if profile_path.read_bytes() != PROFILE_PATH.read_bytes():
        raise LaunchBindingError("manifest runtime profile is not this binder profile")
    profile = load_json(profile_path, label="runtime profile")

    coordinates: dict[str, dict[str, str]] = {}
    for key in COORDINATE_KEYS:
        path = _regular(Path(manifest["artifacts"][key]), key)
        coordinates[key] = {"path": str(path), "digest": _digest(path)}

    for key in ("owner_execution_request_schema", "task_local_dag_schema"):
        path = _regular(Path(manifest["owner_contract_paths"][key]), key)
        contract = profile["owner_contracts"][key]
        if _digest(path) != contract["digest"]:
            raise LaunchBindingError(f"{key} differs from the runtime-profile-pinned owner bytes")
        coordinates[key] = {
            "path": str(path),
            "digest": contract["digest"],
            "owner_repo": contract["owner_repo"],
            "artifact_ref": contract["artifact_ref"],
            "source_ref": contract["source_ref"],
            "schema_version": contract["schema_version"],
        }

    workspace = _directory(Path(manifest["workspace_path"]), "workspace")
    codex_home = _directory(Path(manifest["codex_home"]), "Codex home")
    codex = _regular(Path(manifest["codex_executable"]), "Codex executable")
    if codex.resolve() != codex:
        raise LaunchBindingError("Codex executable must already be resolved")
    launch = {
        "schema_version": "abyss_stack_external_codex_launch_v1",
        "launch_id": manifest["launch_id"],
        "session_id": manifest["session_id"],
        "admission_class": "owner_contour",
        "owner_admission_identity_mode": "stable_request_ref_v1",
        **coordinates,
        "workspace_path": str(workspace),
        "workspace_expected_head": _git_head(workspace),
        "workspace_initial_posture": manifest["workspace_initial_posture"],
        "workspace_manifest_input_id": manifest["workspace_manifest_input_id"],
        "codex_executable": str(codex),
        "codex_executable_digest": _digest(codex),
        "codex_home": str(codex_home),
        "environment_allowlist": manifest["environment_allowlist"],
    }
    validate_json(launch, LAUNCH_SCHEMA_PATH, label="bound external actor launch")
    _write_exact(output_path, launch)
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "bound": True,
        "started": False,
        "launch_path": str(output_path),
        "launch_digest": _digest(output_path),
        "launch_ref": {
            "object_id": launch["launch_id"],
            "owner_repo": "abyss-stack",
            "schema_version": "abyss_stack_external_codex_launch_v1",
            "digest": _digest(output_path),
        },
        "next_route": "aoa-agents:aoa-summon/form-owner-execution-request",
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = bind(args.manifest, args.output)
    except (LaunchBindingError, ExternalCodexRuntimeError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
