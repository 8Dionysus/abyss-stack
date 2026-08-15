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
import tomllib
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "abyss_stack_codex_incarnation_home_v1"
LOCAL_NAMES = frozenset({"config.toml", "cache", "log", "tmp"})
ROOT_KEY_LINE = re.compile(
    r"^\s*(?P<key>model|model_reasoning_effort|\"model\"|\"model_reasoning_effort\")\s*="
)
FEATURE_TABLE_LINE = re.compile(r"^\s*\[\s*features\s*\]\s*(?:#.*)?$")
FEATURE_KEY_LINE = re.compile(r"^\s*(?:multi_agent|\"multi_agent\")\s*=")
FEATURE_DOTTED_LINE = re.compile(r"^\s*features\.multi_agent\s*=")


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


def _realization(path: Path) -> tuple[dict[str, Any], str, str, str, str]:
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
    runtime_version = runtime.get("version")
    realization_id = value.get("model_realization_id")
    effort = configuration.get("reasoning_effort")
    if not isinstance(realization_id, str) or not realization_id.strip():
        raise IncarnationHomeError("model realization lacks model_realization_id")
    if not isinstance(model_slug, str) or not model_slug.strip():
        raise IncarnationHomeError("model realization lacks model_slug")
    if not isinstance(runtime_version, str) or not runtime_version.strip():
        raise IncarnationHomeError("model realization lacks runtime version")
    if not isinstance(effort, str) or not effort.strip():
        raise IncarnationHomeError("model realization lacks reasoning_effort")
    fingerprint = sha256_bytes(canonical_bytes(configuration))
    if value.get("configuration_fingerprint") != fingerprint:
        raise IncarnationHomeError("model realization configuration fingerprint mismatch")
    return value, model_slug, effort, runtime_version, fingerprint


def _root_key_line(text: str, key: str, parsed: dict[str, Any]) -> int | None:
    """Locate one unambiguous assignment in the TOML document root."""

    if key not in parsed:
        return None
    for index, line in enumerate(text.splitlines(keepends=True)):
        stripped = line.lstrip()
        if stripped.startswith("["):
            break
        match = ROOT_KEY_LINE.match(line)
        if match and match.group("key").strip('"') == key:
            return index
    raise IncarnationHomeError(
        f"ambient Codex config has an ambiguous root assignment for {key}"
    )


def _replace_line(lines: list[str], index: int, value: str) -> None:
    line_ending = ""
    if lines[index].endswith("\r\n"):
        line_ending = "\r\n"
    elif lines[index].endswith("\n"):
        line_ending = "\n"
    lines[index] = value + line_ending


def _bind_multi_agent(text: str) -> str:
    """Force the descendant config to keep the governed transport boundary."""

    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise IncarnationHomeError("ambient Codex config is not valid TOML") from exc
    features = parsed.get("features")
    if features is not None and not isinstance(features, dict):
        raise IncarnationHomeError("ambient Codex features table is not a TOML table")
    lines = text.splitlines(keepends=True)
    table_header: int | None = None
    table_end: int | None = None
    feature_index: int | None = None
    dotted_index: int | None = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("["):
            if table_header is not None and table_end is None:
                table_end = index
            table_header = index if FEATURE_TABLE_LINE.match(line) else None
            continue
        if table_header is not None and FEATURE_KEY_LINE.match(line):
            feature_index = index
        elif table_header is None and FEATURE_DOTTED_LINE.match(line):
            dotted_index = index
    if table_header is not None and table_end is None:
        table_end = len(lines)
    if feature_index is not None:
        _replace_line(lines, feature_index, "multi_agent = false")
    elif table_header is not None and table_end is not None:
        lines.insert(table_end, "multi_agent = false\n")
    elif dotted_index is not None:
        _replace_line(lines, dotted_index, "features.multi_agent = false")
    elif features is None:
        lines.extend(["\n", "[features]\n", "multi_agent = false\n"])
    else:
        lines.insert(0, "features.multi_agent = false\n")
    return "".join(lines)


def _ambient_home_identity(ambient_home: Path) -> str:
    return sha256_bytes(
        canonical_bytes({"ambient_codex_home": str(ambient_home)})
    )


def _bound_config(ambient_config: bytes, model_slug: str, effort: str) -> bytes:
    try:
        text = ambient_config.decode("utf-8")
    except UnicodeError as exc:
        raise IncarnationHomeError("ambient Codex config is not UTF-8") from exc
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise IncarnationHomeError("ambient Codex config is not valid TOML") from exc
    model_value = f'model = {json.dumps(model_slug)}'
    effort_value = f'model_reasoning_effort = {json.dumps(effort)}'
    lines = text.splitlines(keepends=True)
    model_index = _root_key_line(text, "model", parsed)
    effort_index = _root_key_line(text, "model_reasoning_effort", parsed)
    if model_index is None:
        lines.insert(0, model_value + "\n")
        if effort_index is not None:
            effort_index += 1
    else:
        _replace_line(lines, model_index, model_value)
    if effort_index is None:
        lines.insert(0, effort_value + "\n")
    else:
        _replace_line(lines, effort_index, effort_value)
    bound = _bind_multi_agent("".join(lines))
    try:
        bound_parsed = tomllib.loads(bound)
    except tomllib.TOMLDecodeError as exc:
        raise IncarnationHomeError(
            "ambient Codex config cannot be safely rebound at the TOML root"
        ) from exc
    if (
        bound_parsed.get("model") != model_slug
        or bound_parsed.get("model_reasoning_effort") != effort
        or not isinstance(bound_parsed.get("features"), dict)
        or bound_parsed["features"].get("multi_agent") is not False
    ):
        raise IncarnationHomeError("ambient Codex config root binding did not take effect")
    return bound.encode("utf-8")


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
    if runtime_root == ambient_home or ambient_home in runtime_root.parents:
        raise IncarnationHomeError(
            "runtime root may not be nested under the ambient Codex home"
        )
    realization, model_slug, effort, runtime_version, fingerprint = _realization(
        realization_path
    )
    fingerprint_value = fingerprint.removeprefix("sha256:")
    incarnation_root = runtime_root / f"sha256-{fingerprint_value}"
    codex_home = incarnation_root / "codex-home"
    ambient_identity = _ambient_home_identity(ambient_home)
    if incarnation_root.is_symlink():
        raise IncarnationHomeError("incarnation root may not be a symlink")
    existing_marker = incarnation_root / "incarnation-home.json"
    if incarnation_root.exists():
        if existing_marker.is_symlink() or not existing_marker.is_file():
            raise IncarnationHomeError(
                "existing incarnation home lacks an ownership marker"
            )
        existing = _load_json(existing_marker, "existing incarnation-home manifest")
        if existing.get("ambient_codex_home") != str(ambient_home):
            raise IncarnationHomeError(
                "incarnation home is owned by another ambient Codex home"
            )
        if existing.get("ambient_home_identity") not in {None, ambient_identity}:
            raise IncarnationHomeError("incarnation ambient-home identity drift")
        if existing.get("codex_home") != str(codex_home):
            raise IncarnationHomeError("incarnation home coordinate drift")
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
        "runtime_version": runtime_version,
        "ambient_codex_home": str(ambient_home),
        "ambient_home_identity": ambient_identity,
        "runtime_root": str(runtime_root),
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
    if manifest.get("ambient_home_identity") != _ambient_home_identity(ambient_home):
        raise IncarnationHomeError("ambient Codex home identity drift")
    runtime_root = _absolute_directory(
        Path(str(manifest.get("runtime_root"))), "runtime root"
    )
    try:
        realization, model_slug, effort, runtime_version, fingerprint = _realization(
            Path(str(manifest.get("model_realization_ref")))
        )
    except IncarnationHomeError:
        raise
    if (
        manifest.get("configuration_fingerprint") != fingerprint
        or manifest.get("model_realization_id")
        != realization.get("model_realization_id")
        or manifest.get("model_slug") != model_slug
        or manifest.get("reasoning_effort") != effort
        or manifest.get("runtime_version") != runtime_version
    ):
        raise IncarnationHomeError("model realization binding drift")
    expected_home = (
        runtime_root / f"sha256-{fingerprint.removeprefix('sha256:')}" / "codex-home"
    ).resolve()
    if codex_home != expected_home:
        raise IncarnationHomeError("incarnation Codex home is not derived from realization")
    try:
        scoped_config = tomllib.loads(config.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise IncarnationHomeError("incarnation Codex config is not valid TOML") from exc
    if (
        scoped_config.get("model") != model_slug
        or scoped_config.get("model_reasoning_effort") != effort
        or not isinstance(scoped_config.get("features"), dict)
        or scoped_config["features"].get("multi_agent") is not False
    ):
        raise IncarnationHomeError("scoped Codex config binding drift")
    shared_names = manifest.get("shared_state_names")
    if (
        not isinstance(shared_names, list)
        or any(
            not isinstance(name, str)
            or not name
            or name in {".", ".."}
            or name in LOCAL_NAMES
            or Path(name).name != name
            for name in shared_names
        )
        or len(set(shared_names)) != len(shared_names)
    ):
        raise IncarnationHomeError("shared-state manifest is invalid")
    expected_shared_names = sorted(
        entry.name
        for entry in ambient_home.iterdir()
        if entry.name not in LOCAL_NAMES
    )
    if sorted(shared_names) != expected_shared_names:
        raise IncarnationHomeError("shared-state manifest no longer matches ambient home")
    expected_names = set(shared_names) | LOCAL_NAMES
    for entry in codex_home.iterdir():
        if entry.name not in expected_names:
            raise IncarnationHomeError(
                f"unexpected incarnation-home entry: {entry.name}"
            )
    for name in shared_names:
        source = ambient_home / name
        target = codex_home / name
        if (
            not source.exists()
            or source.is_symlink()
            or not target.is_symlink()
            or target.readlink() != source
        ):
            raise IncarnationHomeError(f"shared-state link drift: {target}")
    for name in LOCAL_NAMES - {"config.toml"}:
        local = codex_home / name
        if local.is_symlink() or not local.is_dir():
            raise IncarnationHomeError(f"actor-local {name} is not a real directory")
    return manifest


def _resolved_executable(codex_executable: Path) -> Path:
    if not codex_executable.is_absolute():
        raise IncarnationHomeError(
            f"Codex executable must be absolute: {codex_executable}"
        )
    try:
        executable = codex_executable.resolve(strict=True)
    except OSError as exc:
        raise IncarnationHomeError(
            f"Codex executable cannot be resolved: {codex_executable}"
        ) from exc
    if not executable.is_file():
        raise IncarnationHomeError(
            f"Codex executable is not a regular file: {codex_executable}"
        )
    if not os.access(executable, os.X_OK):
        raise IncarnationHomeError("Codex executable is not executable")
    return executable


def _verify_executable_version(executable: Path, runtime_version: str) -> None:
    expected = "codex-cli " + runtime_version
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IncarnationHomeError("Codex executable version probe failed") from exc
    observed = completed.stdout.strip()
    if completed.returncode != 0 or observed != expected:
        raise IncarnationHomeError(
            f"Codex runtime version mismatch: expected {expected}, got {observed or '<empty>'}"
        )


def _reject_binding_overrides(arguments: Sequence[str]) -> None:
    forbidden = {"-m", "--model", "-c", "--config", "-p", "--profile"}
    for index, argument in enumerate(arguments):
        if (
            argument in forbidden
            or argument.startswith("--model=")
            or argument.startswith("--config=")
            or argument.startswith("--profile=")
            or argument.startswith("-m") and argument != "--"
            or argument.startswith("-c") and argument != "--"
            or argument.startswith("-p") and argument != "--"
            or argument in {"--oss", "--local-provider"}
            or argument.startswith("--local-provider=")
        ):
            raise IncarnationHomeError(
                f"forwarded argument overrides incarnation binding: {argument}"
            )
        if argument in {"--enable", "--disable"} and index + 1 < len(arguments):
                if arguments[index + 1] == "multi_agent":
                    if argument == "--enable":
                        raise IncarnationHomeError(
                            "forwarded arguments override incarnation binding: "
                            "may not re-enable multi_agent"
                        )
        if argument == "--enable=multi_agent":
            raise IncarnationHomeError(
                "forwarded arguments override incarnation binding: "
                "may not re-enable multi_agent"
            )


def bound_codex_argv(
    *, codex_executable: Path, manifest: dict[str, Any], arguments: Sequence[str]
) -> list[str]:
    executable = _resolved_executable(codex_executable)
    _reject_binding_overrides(arguments)
    if executable.name != "codex" or (executable.parent / "codex").resolve() != executable:
        raise IncarnationHomeError(
            "Codex executable must be named codex so descendants can inherit the exact runtime"
        )
    codex_home = str(manifest["codex_home"])
    descendant_path = os.pathsep.join(
        (str(executable.parent), "/usr/local/bin", "/usr/bin", "/bin")
    )
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
        + ", PATH="
        + json.dumps(descendant_path)
        + "}",
        "--disable",
        "multi_agent",
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
    executable = _resolved_executable(Path(args.codex_executable))
    _verify_executable_version(executable, str(manifest["runtime_version"]))
    argv = bound_codex_argv(
        codex_executable=executable,
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
