#!/usr/bin/env python3
"""Compose independently owned Codex command-hook fragments."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any


FRAGMENT_SCHEMA_VERSION = "abyss_codex_hooks_fragment_v0"
RECEIPT_SCHEMA_VERSION = "abyss_codex_hooks_composition_receipt_v0"
EVENT_ORDER = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SubagentStart",
    "SubagentStop",
    "Stop",
    "SessionEnd",
)
SUPPORTED_EVENTS = set(EVENT_ORDER)
MATCHER_EVENTS = {
    "SessionStart",
    "SessionEnd",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SubagentStart",
    "SubagentStop",
}
HANDLER_FIELDS = {
    "type",
    "command",
    "commandWindows",
    "timeout",
    "statusMessage",
    "additionalContextLimit",
}
PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
BINDING_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
SAFE_ABSOLUTE_BINDING_PATTERN = re.compile(
    r"^/[A-Za-z0-9._@+:-]+(?:/[A-Za-z0-9._@+:-]+)*$"
)


class CompositionError(ValueError):
    pass


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def rendered_json(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_text(payload: str) -> str:
    return sha256_bytes(payload.encode("utf-8"))


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_bindings(values: list[str]) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for index, value in enumerate(values):
        if "=" not in value:
            raise CompositionError(f"binding {index} must use NAME=VALUE")
        name, binding_value = value.split("=", 1)
        if not BINDING_NAME_PATTERN.fullmatch(name):
            raise CompositionError(f"binding {index} has an invalid name")
        if name in bindings:
            raise CompositionError(f"binding {name} is duplicated")
        if (
            not Path(binding_value).is_absolute()
            or not SAFE_ABSOLUTE_BINDING_PATTERN.fullmatch(binding_value)
        ):
            raise CompositionError(
                f"binding {name} must be a safe absolute path without whitespace"
            )
        bindings[name] = binding_value
    return bindings


def load_json_bytes(path: Path, index: int) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise CompositionError(f"fragment {index} is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise CompositionError(f"fragment {index} must be a JSON object")
    return raw, payload


def validate_identifier(value: Any, label: str, index: int) -> str:
    pattern = (
        r"[A-Za-z0-9._:+/-]+"
        if label == "fragment_id"
        else r"[A-Za-z0-9._-]+"
    )
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 160
        or not re.fullmatch(pattern, value)
    ):
        raise CompositionError(f"fragment {index} has invalid {label}")
    return value


def placeholders_in_hooks(hooks: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            handlers = group.get("hooks")
            if not isinstance(handlers, list):
                continue
            for handler in handlers:
                if not isinstance(handler, dict):
                    continue
                for field in ("command", "commandWindows"):
                    value = handler.get(field)
                    if isinstance(value, str):
                        found.update(PLACEHOLDER_PATTERN.findall(value))
    return found


def substitute_command(value: str, bindings: dict[str, str]) -> str:
    def replacement(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in bindings:
            raise CompositionError(f"binding {name} is required")
        return bindings[name]

    result = PLACEHOLDER_PATTERN.sub(replacement, value)
    if PLACEHOLDER_PATTERN.search(result):
        raise CompositionError("unresolved binding remains in hook command")
    return result


def bind_hooks(
    hooks: dict[str, Any],
    declared_bindings: set[str],
    bindings: dict[str, str],
) -> dict[str, Any]:
    found = placeholders_in_hooks(hooks)
    if found != declared_bindings:
        missing_declarations = sorted(found - declared_bindings)
        unused_declarations = sorted(declared_bindings - found)
        detail: list[str] = []
        if missing_declarations:
            detail.append("undeclared placeholders " + ", ".join(missing_declarations))
        if unused_declarations:
            detail.append("unused declarations " + ", ".join(unused_declarations))
        raise CompositionError("; ".join(detail))
    missing_values = sorted(declared_bindings - set(bindings))
    if missing_values:
        raise CompositionError(
            "missing binding values " + ", ".join(missing_values)
        )

    bound = json.loads(json.dumps(hooks))
    for groups in bound.values():
        for group in groups:
            for handler in group["hooks"]:
                for field in ("command", "commandWindows"):
                    value = handler.get(field)
                    if isinstance(value, str):
                        handler[field] = substitute_command(value, bindings)
    return bound


def validate_handler(
    event_name: str,
    handler: Any,
    *,
    fragment_index: int,
    group_index: int,
    handler_index: int,
) -> dict[str, Any]:
    label = (
        f"fragment {fragment_index} {event_name} "
        f"group {group_index} handler {handler_index}"
    )
    if not isinstance(handler, dict):
        raise CompositionError(f"{label} must be an object")
    unsupported = sorted(set(handler) - HANDLER_FIELDS)
    if unsupported:
        raise CompositionError(f"{label} has unsupported fields: {', '.join(unsupported)}")
    if handler.get("type") != "command":
        raise CompositionError(f"{label} must be a command hook")
    command = handler.get("command")
    if (
        not isinstance(command, str)
        or not command
        or any(character in command for character in ("\0", "\r", "\n"))
    ):
        raise CompositionError(f"{label} has an invalid command")
    command_windows = handler.get("commandWindows")
    if command_windows is not None and (
        not isinstance(command_windows, str)
        or not command_windows
        or any(character in command_windows for character in ("\0", "\r", "\n"))
    ):
        raise CompositionError(f"{label} has an invalid commandWindows")
    timeout = handler.get("timeout")
    if timeout is not None and (
        isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 1 <= timeout <= 600
    ):
        raise CompositionError(f"{label} has an invalid timeout")
    if event_name == "SessionEnd" and timeout is not None and timeout > 3:
        raise CompositionError(f"{label} exceeds the SessionEnd timeout ceiling")
    status = handler.get("statusMessage")
    if status is not None and (
        not isinstance(status, str)
        or not status
        or len(status) > 200
        or "\n" in status
        or "\r" in status
    ):
        raise CompositionError(f"{label} has an invalid statusMessage")
    context_limit = handler.get("additionalContextLimit")
    if context_limit is not None and (
        isinstance(context_limit, bool)
        or not isinstance(context_limit, int)
        or context_limit < 0
    ):
        raise CompositionError(f"{label} has an invalid additionalContextLimit")
    return handler


def validate_hooks(hooks: Any, fragment_index: int) -> dict[str, Any]:
    if not isinstance(hooks, dict) or not hooks:
        raise CompositionError(f"fragment {fragment_index} hooks must be a non-empty object")
    unsupported_events = sorted(set(hooks) - SUPPORTED_EVENTS)
    if unsupported_events:
        raise CompositionError(
            f"fragment {fragment_index} has unsupported events: "
            + ", ".join(unsupported_events)
        )

    for event_name, groups in hooks.items():
        if not isinstance(groups, list) or not groups:
            raise CompositionError(
                f"fragment {fragment_index} {event_name} must have hook groups"
            )
        for group_index, group in enumerate(groups):
            label = f"fragment {fragment_index} {event_name} group {group_index}"
            if not isinstance(group, dict):
                raise CompositionError(f"{label} must be an object")
            if set(group) - {"matcher", "hooks"}:
                raise CompositionError(f"{label} has unsupported fields")
            matcher = group.get("matcher")
            if matcher is not None:
                if event_name not in MATCHER_EVENTS:
                    raise CompositionError(
                        f"{label} cannot use a matcher for this Codex event"
                    )
                if not isinstance(matcher, str) or not matcher:
                    raise CompositionError(f"{label} has an invalid matcher")
                try:
                    re.compile(matcher)
                except re.error as exc:
                    raise CompositionError(f"{label} has an invalid matcher regex") from exc
            handlers = group.get("hooks")
            if not isinstance(handlers, list) or not handlers:
                raise CompositionError(f"{label} must contain handlers")
            for handler_index, handler in enumerate(handlers):
                validate_handler(
                    event_name,
                    handler,
                    fragment_index=fragment_index,
                    group_index=group_index,
                    handler_index=handler_index,
                )
    return hooks


def normalize_fragment(
    path: Path,
    index: int,
    bindings: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], set[str]]:
    raw, payload = load_json_bytes(path, index)
    source_digest = sha256_bytes(raw)
    if payload.get("schema_version") == FRAGMENT_SCHEMA_VERSION:
        required = {
            "schema_version",
            "fragment_id",
            "owner",
            "mode",
            "description",
            "bindings",
            "hooks",
        }
        if set(payload) != required:
            raise CompositionError(
                f"fragment {index} envelope fields do not match the contract"
            )
        fragment_id = validate_identifier(payload.get("fragment_id"), "fragment_id", index)
        owner = validate_identifier(payload.get("owner"), "owner", index)
        mode = validate_identifier(payload.get("mode"), "mode", index)
        description = payload.get("description")
        if not isinstance(description, str) or not description or len(description) > 500:
            raise CompositionError(f"fragment {index} has invalid description")
        declared = payload.get("bindings")
        if (
            not isinstance(declared, list)
            or not all(
                isinstance(name, str) and BINDING_NAME_PATTERN.fullmatch(name)
                for name in declared
            )
            or len(set(declared)) != len(declared)
        ):
            raise CompositionError(f"fragment {index} has invalid bindings")
        declared_set = set(declared)
        raw_hooks = payload.get("hooks")
        if not isinstance(raw_hooks, dict):
            raise CompositionError(f"fragment {index} hooks must be an object")
        validate_hooks(raw_hooks, index)
        hooks = bind_hooks(raw_hooks, declared_set, bindings)
        used_bindings = declared_set
    else:
        if set(payload) - {"description", "hooks"} or "hooks" not in payload:
            raise CompositionError(
                f"fragment {index} is neither a native config nor an owner envelope"
            )
        hooks = payload["hooks"]
        if placeholders_in_hooks(hooks if isinstance(hooks, dict) else {}):
            raise CompositionError(
                f"fragment {index} native config contains unresolved placeholders"
            )
        fragment_id = f"native-config:{index}"
        owner = "external-native"
        mode = "standalone"
        used_bindings = set()

    validate_hooks(hooks, index)
    metadata = {
        "input_index": index,
        "fragment_id": fragment_id,
        "owner": owner,
        "mode": mode,
        "source_digest": source_digest,
    }
    return hooks, metadata, used_bindings


def compose(
    fragment_paths: list[Path],
    bindings: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    if not fragment_paths:
        raise CompositionError("at least one fragment is required")

    merged: dict[str, list[dict[str, Any]]] = {}
    metadata: list[dict[str, Any]] = []
    used_bindings: set[str] = set()
    seen_handlers: set[tuple[str, str, str, str]] = set()

    for index, path in enumerate(fragment_paths):
        hooks, fragment_metadata, fragment_bindings = normalize_fragment(
            path,
            index,
            bindings,
        )
        metadata.append(fragment_metadata)
        used_bindings.update(fragment_bindings)
        for event_name, groups in hooks.items():
            destination = merged.setdefault(event_name, [])
            for group in groups:
                matcher = str(group.get("matcher", ""))
                for handler in group["hooks"]:
                    duplicate_key = (
                        event_name,
                        matcher,
                        handler["command"],
                        str(handler.get("commandWindows", "")),
                    )
                    if duplicate_key in seen_handlers:
                        raise CompositionError(
                            f"exact duplicate command handler in {event_name}"
                        )
                    seen_handlers.add(duplicate_key)
                destination.append(group)

    unused_bindings = sorted(set(bindings) - used_bindings)
    if unused_bindings:
        raise CompositionError("unused binding values " + ", ".join(unused_bindings))

    ordered_hooks = {
        event_name: merged[event_name]
        for event_name in EVENT_ORDER
        if event_name in merged
    }
    output = {
        "description": (
            "Composed Codex command hooks from independent owner fragments. "
            "Composition does not transfer hook semantics or authority."
        ),
        "hooks": ordered_hooks,
    }
    binding_digests = {
        name: sha256_text(value)
        for name, value in sorted(bindings.items())
    }
    return output, metadata, binding_digests


def count_output(output: dict[str, Any]) -> dict[str, int]:
    hooks = output["hooks"]
    return {
        "event_count": len(hooks),
        "group_count": sum(len(groups) for groups in hooks.values()),
        "handler_count": sum(
            len(group["hooks"])
            for groups in hooks.values()
            for group in groups
        ),
    }


def receipt_digest(receipt: dict[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receipt_digest", None)
    return sha256_text(canonical_json(payload))


def build_receipt(
    *,
    output_bytes: bytes,
    fragments: list[dict[str, Any]],
    binding_digests: dict[str, str],
    target: Path,
    target_changed: bool,
    previous_bytes: bytes | None,
    backup_name: str | None,
    backup_bytes: bytes | None,
    output: dict[str, Any],
) -> dict[str, Any]:
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "created_at": now_utc(),
        "fragments": fragments,
        "bindings": binding_digests,
        "output": {
            "digest": sha256_bytes(output_bytes),
            **count_output(output),
        },
        "target_ref": sha256_text(str(target.resolve(strict=False))),
        "target_changed": target_changed,
        "previous_output_digest": (
            sha256_bytes(previous_bytes) if previous_bytes is not None else None
        ),
        "backup_name": backup_name,
        "backup_digest": (
            sha256_bytes(backup_bytes) if backup_bytes is not None else None
        ),
        "authority": {
            "hook_semantics": False,
            "codex_trust": False,
            "runtime_health": False,
            "memory_use": False,
            "outcome": False,
            "benefit": False,
        },
        "receipt_digest": "",
    }
    receipt["receipt_digest"] = receipt_digest(receipt)
    return receipt


def fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_private_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    if not path.parent.is_dir():
        raise CompositionError("output parent directory does not exist")
    if path.is_symlink():
        raise CompositionError("refusing to replace a symlink")
    temporary = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    file_fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        with os.fdopen(file_fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
        fsync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def ensure_private_directory(path: Path) -> None:
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise CompositionError("backup target must be a real directory")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def existing_target(path: Path) -> tuple[bytes | None, int | None]:
    if path.is_symlink():
        raise CompositionError("refusing to replace a symlink target")
    if not path.exists():
        return None, None
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode):
        raise CompositionError("hook target must be a regular file")
    return path.read_bytes(), stat.S_IMODE(mode)


def install_composition(
    *,
    output: dict[str, Any],
    fragments: list[dict[str, Any]],
    binding_digests: dict[str, str],
    target: Path,
    receipt_path: Path,
    backup_dir: Path | None,
) -> dict[str, Any]:
    if target.resolve(strict=False) == receipt_path.resolve(strict=False):
        raise CompositionError("target and receipt paths must differ")
    if not target.parent.is_dir() or not receipt_path.parent.is_dir():
        raise CompositionError("target and receipt parent directories must exist")
    if receipt_path.is_symlink():
        raise CompositionError("refusing to replace a symlink receipt")

    output_bytes = rendered_json(output)
    previous_bytes, previous_mode = existing_target(target)
    target_changed = (
        previous_bytes != output_bytes
        or (previous_mode is not None and previous_mode != 0o600)
    )
    backup_name: str | None = None
    backup_bytes: bytes | None = None

    if target_changed and previous_bytes is not None:
        destination = backup_dir or target.parent / ".abyss-hooks-backups"
        ensure_private_directory(destination)
        digest_prefix = sha256_bytes(previous_bytes).removeprefix("sha256:")[:12]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_name = (
            f"{target.name}.{timestamp}.{digest_prefix}.{os.getpid()}.backup"
        )
        backup_path = destination / backup_name
        if backup_path.exists() or backup_path.is_symlink():
            raise CompositionError("backup collision")
        atomic_private_write(backup_path, previous_bytes)
        backup_bytes = previous_bytes

    if target_changed:
        atomic_private_write(target, output_bytes)

    receipt = build_receipt(
        output_bytes=output_bytes,
        fragments=fragments,
        binding_digests=binding_digests,
        target=target,
        target_changed=target_changed,
        previous_bytes=previous_bytes,
        backup_name=backup_name,
        backup_bytes=backup_bytes,
        output=output,
    )
    try:
        atomic_private_write(
            receipt_path,
            rendered_json(receipt),
        )
    except BaseException:
        if target_changed:
            if previous_bytes is None:
                try:
                    target.unlink()
                    fsync_directory(target.parent)
                except OSError:
                    pass
            else:
                atomic_private_write(
                    target,
                    previous_bytes,
                    mode=previous_mode or 0o600,
                )
        raise
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compose independent Codex command-hook fragments.",
    )
    parser.add_argument(
        "--fragment",
        action="append",
        type=Path,
        required=True,
        help="native hook config or owner fragment; repeat in desired order",
    )
    parser.add_argument(
        "--binding",
        action="append",
        default=[],
        help="safe absolute-path binding NAME=VALUE; repeat as needed",
    )
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--check-output", type=Path)
    destination.add_argument("--write", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.write is not None and args.receipt is None:
            raise CompositionError("--write requires --receipt")
        if args.write is None and (args.receipt is not None or args.backup_dir is not None):
            raise CompositionError("--receipt and --backup-dir require --write")

        bindings = parse_bindings(args.binding)
        output, fragments, binding_digests = compose(args.fragment, bindings)
        output_bytes = rendered_json(output)

        if args.check_output is not None:
            try:
                current = args.check_output.read_bytes()
            except OSError:
                print("[stale] composed Codex hook output is missing", file=sys.stderr)
                return 1
            if current != output_bytes:
                print("[stale] composed Codex hook output differs", file=sys.stderr)
                return 1
            print("[ok] composed Codex hook output is exact")
            return 0

        if args.write is not None:
            install_composition(
                output=output,
                fragments=fragments,
                binding_digests=binding_digests,
                target=args.write,
                receipt_path=args.receipt,
                backup_dir=args.backup_dir,
            )
            print("[ok] composed Codex hooks atomically")
            return 0

        sys.stdout.buffer.write(output_bytes)
        return 0
    except CompositionError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
