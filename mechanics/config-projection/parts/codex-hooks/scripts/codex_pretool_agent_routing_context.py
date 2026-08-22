#!/usr/bin/env python3
"""Relay one session-owned typed base into an event-keyed route context.

This is a Codex-wire transport helper, not a responsibility classifier.  The
session owner supplies ``AOA_AGENT_TOOL_ROUTING_CONTEXT_BASE``; this command
copies no opaque tool input and adds only the safe coordinates of the current
PreToolUse attempt before the stack adapter consumes the single-use entry.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import uuid


CONTEXT_DIRECTORY_ENV = "AOA_AGENT_TOOL_ROUTING_CONTEXT_DIR"
CONTEXT_BASE_ENV = "AOA_AGENT_TOOL_ROUTING_CONTEXT_BASE"
CONTEXT_SCHEMA_VERSION = "aoa_codex_pretool_agent_routing_context_v2"
CONTEXT_FIELDS = frozenset(
    {
        "schema_version",
        "attempt",
        "goal_ref",
        "current_holder_ref",
        "route_anchor",
        "phase",
        "boundary_state",
        "responsibility_result_ref",
        "local_next_route",
    }
)
ATTEMPT_FIELDS = ("session_id", "turn_id", "tool_use_id", "tool_name")
# Keep the relay narrower than the adapter's fail-closed namespace matcher: an
# unknown future tool must still reach the adapter, but must not create an
# unclaimable context entry that the adapter intentionally does not consume.
RELAY_TOOL_NAMES = frozenset(
    {
        "spawn_agent",
        "Agent",
        "multi_agent_v1send_input",
        "multi_agent_v1resume_agent",
        "multi_agent_v1wait_agent",
        "multi_agent_v1close_agent",
        "send_message",
        "followup_task",
        "wait_agent",
        "list_agents",
        "interrupt_agent",
        "collaborationspawn_agent",
        "collaborationsend_message",
        "collaborationwait_agent",
        "collaborationclose_agent",
        "collaborationresume_agent",
        "collaborationlist_agents",
        "collaborationfollowup_task",
        "collaborationinterrupt_agent",
        "collaborationsend_input",
    }
)
MAX_EVENT_BYTES = 1024 * 1024
MAX_BASE_BYTES = 256 * 1024


def _safe_string(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 512:
        return None
    if any(character in value for character in ("\0", "\r", "\n")):
        return None
    return value


def _attempt(event: dict[str, object]) -> dict[str, str] | None:
    values = {field: _safe_string(event.get(field)) for field in ATTEMPT_FIELDS}
    if any(value is None for value in values.values()):
        return None
    return {
        field: values[field]
        for field in ATTEMPT_FIELDS
        if values[field] is not None
    }


def _attempt_key(attempt: dict[str, str]) -> str:
    encoded = json.dumps(
        attempt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _regular_absolute(value: object, *, directory: bool) -> Path | None:
    if not isinstance(value, str):
        return None
    path = Path(value)
    if not path.is_absolute() or path.is_symlink():
        return None
    if directory and not path.is_dir():
        return None
    if not directory and not path.is_file():
        return None
    return path


def _read_base(path: Path) -> dict[str, object] | None:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BASE_BYTES + 1)
    except OSError:
        return None
    if len(raw) > MAX_BASE_BYTES:
        return None
    try:
        base = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if (
        not isinstance(base, dict)
        or set(base) != CONTEXT_FIELDS
        or base.get("schema_version") != CONTEXT_SCHEMA_VERSION
        or base.get("attempt") != {}
    ):
        return None
    return base


def _write_once(directory: Path, target: Path, payload: bytes) -> bool:
    if target.exists() or target.is_symlink():
        return False
    temporary = directory / f".context.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists() or target.is_symlink():
            temporary.unlink(missing_ok=True)
            return False
        os.replace(temporary, target)
        os.chmod(target, 0o600)
        return True
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def handle_event(event: object, environ: dict[str, str] | None = None) -> dict[str, object]:
    if not isinstance(event, dict) or event.get("hook_event_name") != "PreToolUse":
        return {}
    if event.get("tool_name") not in RELAY_TOOL_NAMES:
        return {}
    attempt = _attempt(event)
    environment = os.environ if environ is None else environ
    directory = _regular_absolute(
        environment.get(CONTEXT_DIRECTORY_ENV),
        directory=True,
    )
    base_path = _regular_absolute(
        environment.get(CONTEXT_BASE_ENV),
        directory=False,
    )
    if attempt is None or directory is None or base_path is None:
        return {}
    base = _read_base(base_path)
    if base is None:
        return {}
    context = dict(base)
    context["attempt"] = attempt
    target = directory / f"attempt-{_attempt_key(attempt)}.json"
    payload = (
        json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    _write_once(directory, target, payload)
    return {}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_EVENT_BYTES + 1)
        if len(raw) > MAX_EVENT_BYTES:
            return 0
        event = json.loads(raw.decode("utf-8"))
        output = handle_event(event)
    except (OSError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        output = {}
    sys.stdout.write(json.dumps(output, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
