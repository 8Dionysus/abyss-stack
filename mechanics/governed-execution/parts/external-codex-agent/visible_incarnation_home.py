#!/usr/bin/env python3
"""Prepare and enter a Codex home whose default follows one incarnation.

The operator-visible Codex process keeps the ambient user home so existing
sessions and hook trust retain their identity.  Its shell children receive the
incarnation home through Codex's shell environment policy; a plain nested
``codex exec`` therefore keeps the selected model and reasoning effort.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "abyss_stack_codex_incarnation_home_v1"
LOCAL_NAMES = frozenset({"config.toml", "cache", "log", "tmp"})
MODEL_LINE = re.compile(r"(?m)^model\s*=.*$")
EFFORT_LINE = re.compile(r"(?m)^model_reasoning_effort\s*=.*$")


class IncarnationHomeError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _absolute_directory(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise IncarnationHomeError(f"{label} must be an absolute real directory: {path}")
    return path.resolve()


def _regular_file(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise IncarnationHomeError(f"{label} must be an absolute regular file: {path}")
    return path.resolve()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_regular_file(path, label).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IncarnationHomeError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise IncarnationHomeError(f"{label} must be a JSON object")
    return value


def _realization(path: Path) -> tuple[dict[str, Any], str, str, str]:
    value = _load_json(path, "model realization")
    if value.get("schema_version") != "aoa_model_realization_v1":
        raise IncarnationHomeError("unsupported model realization schema")
    configuration = value.get("configuration")
    if not isinstance(configuration, dict):
        raise IncarnationHomeError("model realization lacks configuration")
    runtime = configuration.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("product") != "codex-cli":
        raise IncarnationHomeError("model realization is not for Codex CLI")
    model_slug = runtime.get("model_slug")
    effort = configuration.get("reasoning_effort")
    if not isinstance(model_slug, str) or not model_slug.strip():
        raise IncarnationHomeError("model realization lacks model_slug")
    if not isinstance(effort, str) or not effort.strip():
        raise IncarnationHomeError("model realization lacks reasoning_effort")
    fingerprint = sha256_bytes(canonical_bytes(configuration))
    if value.get("configuration_fingerprint") != fingerprint:
        raise IncarnationHomeError("model realization configuration fingerprint mismatch")
    return value, model_slug, effort, fingerprint


def _bound_config(ambient_config: bytes, model_slug: str, effort: str) -> bytes:
    try:
        text = ambient_config.decode("utf-8")
    except UnicodeError as exc:
        raise IncarnationHomeError("ambient Codex config is not UTF-8") from exc
    model_value = f'model = {json.dumps(model_slug)}'
    effort_value = f'model_reasoning_effort = {json.dumps(effort)}'
    if MODEL_LINE.search(text):
        text = MODEL_LINE.sub(model_value, text, count=1)
    else:
        text = model_value + "\n" + text
    if EFFORT_LINE.search(text):
        text = EFFORT_LINE.sub(effort_value, text, count=1)
    else:
        text = effort_value + "\n" + text
    return text.encode("utf-8")


def _write_exact(path: Path, content: bytes, mode: int) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise IncarnationHomeError(f"refusing to replace non-file: {path}")
        if path.read_bytes() == content:
            path.chmod(mode)
            return
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        temporary.write_bytes(content)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare_home(
    *, ambient_home: Path, realization_path: Path, runtime_root: Path
) -> dict[str, Any]:
    ambient_home = _absolute_directory(ambient_home, "ambient Codex home")
    runtime_root = _absolute_directory(runtime_root, "runtime root")
    realization_path = _regular_file(realization_path, "model realization")
    realization, model_slug, effort, fingerprint = _realization(realization_path)
    fingerprint_value = fingerprint.removeprefix("sha256:")
    incarnation_root = runtime_root / f"sha256-{fingerprint_value}"
    codex_home = incarnation_root / "codex-home"
    incarnation_root.mkdir(mode=0o700, exist_ok=True)
    codex_home.mkdir(mode=0o700, exist_ok=True)
    if incarnation_root.is_symlink() or codex_home.is_symlink():
        raise IncarnationHomeError("incarnation home may not be a symlink")
    incarnation_root.chmod(0o700)
    codex_home.chmod(0o700)
    for name in ("cache", "log", "tmp"):
        local = codex_home / name
        local.mkdir(mode=0o700, exist_ok=True)
        if local.is_symlink() or not local.is_dir():
            raise IncarnationHomeError(f"actor-local {name} is not a real directory")
        local.chmod(0o700)

    ambient_config = _regular_file(
        ambient_home / "config.toml", "ambient Codex config"
    ).read_bytes()
    config = _bound_config(ambient_config, model_slug, effort)
    _write_exact(codex_home / "config.toml", config, 0o600)

    shared_names: list[str] = []
    for source in sorted(ambient_home.iterdir(), key=lambda item: item.name):
        if source.name in LOCAL_NAMES:
            continue
        target = codex_home / source.name
        if target.is_symlink():
            if target.readlink() != source:
                raise IncarnationHomeError(f"shared state link drift: {target}")
        elif target.exists():
            raise IncarnationHomeError(f"shared state target is not a symlink: {target}")
        else:
            target.symlink_to(source)
        shared_names.append(source.name)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_realization_id": realization.get("model_realization_id"),
        "model_realization_ref": str(realization_path),
        "configuration_fingerprint": fingerprint,
        "model_slug": model_slug,
        "reasoning_effort": effort,
        "ambient_codex_home": str(ambient_home),
        "codex_home": str(codex_home),
        "config_digest": sha256_bytes(config),
        "shared_state_names": shared_names,
        "top_level_posture": "ambient-home",
        "child_posture": "incarnation-home-via-shell-environment-policy",
    }
    _write_exact(
        incarnation_root / "incarnation-home.json",
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n",
        0o600,
    )
    return manifest


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest = _load_json(path, "incarnation-home manifest")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise IncarnationHomeError("unsupported incarnation-home manifest")
    codex_home = _absolute_directory(Path(str(manifest.get("codex_home"))), "incarnation Codex home")
    ambient_home = _absolute_directory(
        Path(str(manifest.get("ambient_codex_home"))), "ambient Codex home"
    )
    config = _regular_file(codex_home / "config.toml", "incarnation Codex config")
    if sha256_bytes(config.read_bytes()) != manifest.get("config_digest"):
        raise IncarnationHomeError("incarnation Codex config drift")
    if codex_home == ambient_home:
        raise IncarnationHomeError("incarnation and ambient Codex homes must be distinct")
    return manifest


def bound_codex_argv(
    *, codex_executable: Path, manifest: dict[str, Any], arguments: Sequence[str]
) -> list[str]:
    executable = _regular_file(codex_executable, "Codex executable")
    if not os.access(executable, os.X_OK):
        raise IncarnationHomeError("Codex executable is not executable")
    codex_home = str(manifest["codex_home"])
    return [
        str(executable),
        "-m",
        str(manifest["model_slug"]),
        "-c",
        f'model_reasoning_effort={json.dumps(str(manifest["reasoning_effort"]))}',
        "-c",
        "shell_environment_policy.set="
        + "{CODEX_HOME="
        + json.dumps(codex_home)
        + "}",
        *arguments,
    ]


def command_prepare(args: argparse.Namespace) -> int:
    manifest = prepare_home(
        ambient_home=Path(args.ambient_codex_home),
        realization_path=Path(args.model_realization),
        runtime_root=Path(args.runtime_root),
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


def command_launch(args: argparse.Namespace) -> int:
    manifest = _load_manifest(Path(args.manifest))
    argv = bound_codex_argv(
        codex_executable=Path(args.codex_executable),
        manifest=manifest,
        arguments=args.codex_arguments,
    )
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(manifest["ambient_codex_home"])
    if args.terminal_title:
        completed = subprocess.run(
            [args.kitty_executable, "--detach", "--title", args.terminal_title, *argv],
            check=False,
            env=environment,
        )
        return completed.returncode
    os.execvpe(argv[0], argv, environment)
    return 127


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    subcommands = root.add_subparsers(dest="command", required=True)
    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("--ambient-codex-home", required=True)
    prepare.add_argument("--model-realization", required=True)
    prepare.add_argument("--runtime-root", required=True)
    prepare.set_defaults(handler=command_prepare)
    launch = subcommands.add_parser("launch")
    launch.add_argument("--manifest", required=True)
    launch.add_argument("--codex-executable", required=True)
    launch.add_argument("--terminal-title")
    launch.add_argument("--kitty-executable", default="/usr/bin/kitty")
    launch.add_argument("codex_arguments", nargs=argparse.REMAINDER)
    launch.set_defaults(handler=command_launch)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "launch" and args.codex_arguments[:1] == ["--"]:
        args.codex_arguments = args.codex_arguments[1:]
    if args.command == "launch" and not args.codex_arguments:
        raise IncarnationHomeError("launch requires Codex arguments after --")
    return int(args.handler(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IncarnationHomeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
