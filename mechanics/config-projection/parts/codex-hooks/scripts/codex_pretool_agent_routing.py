#!/usr/bin/env python3
"""Project Codex 0.148.0 agent-tool attempts into the typed SDK route.

This command is a Codex-wire adapter only.  It recognizes the current
``collaboration`` tool namespace, obtains an explicitly supplied typed route
context, asks ``aoa-sdk`` for the next-owner posture, and reflects that
posture as a PreToolUse allow or deny.  It never classifies responsibility or
selects a role, model, runtime, workspace, or actor.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import sys
from typing import Any, Mapping
import uuid


CONTEXT_SCHEMA_VERSION = "aoa_codex_pretool_agent_routing_context_v2"
CODEX_PRE_TOOL_EVENT = "PreToolUse"
CODEX_AGENT_TOOL_NAMESPACE = "collaboration"
CONTEXT_DIRECTORY_ENV = "AOA_AGENT_TOOL_ROUTING_CONTEXT_DIR"
CONTEXT_FILE_PREFIX = "attempt-"
ATTEMPT_IDENTITY_FIELDS = ("session_id", "turn_id", "tool_use_id", "tool_name")
MAX_EVENT_BYTES = 1024 * 1024
MAX_CONTEXT_BYTES = 256 * 1024
INTERNAL_TIMEOUT_SECONDS = 5.0

# These are Codex 0.148.0's hook-facing agent-tool names. ``spawn_agent`` is
# special-cased by Codex even when the underlying tool is namespaced; the
# remaining v1 names are flattened and v2 names are already unnamespaced.
# ``collaboration*`` values are retained as compatibility identities observed
# in the installed 0.148.0 binary. The matcher and this set stay explicit so
# a new or misspelled name cannot silently become an unrelated tool.
CODEX_AGENT_TOOL_NAMES = frozenset(
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


class AdapterError(ValueError):
    """A malformed or unavailable adapter input."""


class AdapterTimeout(AdapterError):
    """The bounded inner route expired before it could return a decision."""


def _raise_timeout(_signum: int, _frame: Any) -> None:
    raise AdapterTimeout("inner route timeout; denied before Codex hook timeout")


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": CODEX_PRE_TOOL_EVENT,
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _required_string(value: Any, label: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise AdapterError(f"missing or invalid {label}")
    if any(character in value for character in ("\0", "\r", "\n")):
        raise AdapterError(f"invalid {label}")
    return value


def _read_json_file(path_value: str, *, label: str, maximum: int) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise AdapterError(f"{label} is not a regular absolute file")
    try:
        with path.open("rb") as stream:
            raw = stream.read(maximum + 1)
    except OSError as exc:
        raise AdapterError(f"{label} is unreadable") from exc
    if len(raw) > maximum:
        raise AdapterError(f"{label} is too large")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"{label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise AdapterError(f"{label} must be a JSON object")
    return payload


def _tool_class(tool_name: Any) -> str:
    if not isinstance(tool_name, str) or not tool_name:
        return "malformed"
    if tool_name in CODEX_AGENT_TOOL_NAMES:
        return "agent"
    if tool_name.startswith(CODEX_AGENT_TOOL_NAMESPACE) or tool_name.startswith(
        "multi_agent_"
    ):
        return "unknown-agent"
    return "other"


def _load_sdk(environ: Mapping[str, str]) -> tuple[Any, Any, Any, Any, Any]:
    source_root = environ.get("AOA_SDK_SOURCE_ROOT")
    source_path: Path | None = None
    if source_root:
        source_path = Path(source_root).expanduser()
        if not source_path.is_absolute() or not source_path.is_dir():
            raise AdapterError("AOA_SDK_SOURCE_ROOT is unavailable")
        src_path = source_path / "src"
        if not src_path.is_dir():
            raise AdapterError("AOA_SDK_SOURCE_ROOT has no src directory")
        if not (src_path / "aoa_sdk").is_dir():
            raise AdapterError("AOA_SDK_SOURCE_ROOT has no aoa_sdk package")
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))
    try:
        import aoa_sdk
        import aoa_sdk.control_plane as control_plane_module
        import aoa_sdk.contracts.agent_tool_routing as agent_tool_routing_module
        import aoa_sdk.workspace.discovery as workspace_discovery_module
        from aoa_sdk.control_plane import ControlPlaneAPI, default_agent_tool_routing_provenance
        from aoa_sdk.contracts.agent_tool_routing import AgentToolRoutingIntent
        from aoa_sdk.workspace.discovery import Workspace
    except (ImportError, ModuleNotFoundError) as exc:
        raise AdapterError("aoa-sdk is unavailable") from exc
    if source_path is not None:
        source_package = (source_path / "src" / "aoa_sdk").resolve()
        module_files = (
            getattr(aoa_sdk, "__file__", None),
            getattr(control_plane_module, "__file__", None),
            getattr(agent_tool_routing_module, "__file__", None),
            getattr(workspace_discovery_module, "__file__", None),
        )
        try:
            resolved_files = tuple(Path(value).resolve() for value in module_files)
        except (TypeError, ValueError, OSError) as exc:
            raise AdapterError("selected aoa-sdk modules have no valid source files") from exc
        if any(
            not file_path.is_relative_to(source_package)
            for file_path in resolved_files
        ):
            raise AdapterError("imported aoa-sdk modules escaped AOA_SDK_SOURCE_ROOT")
    return (
        ControlPlaneAPI,
        default_agent_tool_routing_provenance,
        AgentToolRoutingIntent,
        Workspace,
        source_root,
    )


def _attempt_identity_coordinates(
    source: Mapping[str, Any],
    *,
    label_prefix: str = "",
) -> dict[str, str]:
    return {
        label: _required_string(
            source.get(label),
            f"{label_prefix}{label}",
        )
        for label in ATTEMPT_IDENTITY_FIELDS
    }


def _attempt_identity_digest(event: Mapping[str, Any]) -> str:
    coordinates = _attempt_identity_coordinates(event)
    encoded = json.dumps(
        coordinates,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _claim_context(
    environ: Mapping[str, str],
    event: Mapping[str, Any],
) -> dict[str, Any]:
    directory_value = environ.get(CONTEXT_DIRECTORY_ENV)
    if not directory_value:
        raise AdapterError("typed Goal/current-holder route context is unavailable")
    directory = Path(directory_value)
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise AdapterError("typed route context directory is unavailable")
    path = directory / (
        f"{CONTEXT_FILE_PREFIX}{_attempt_identity_digest(event)}.json"
    )
    if path.is_symlink() or not path.is_file():
        raise AdapterError("typed route context for this tool call is unavailable")

    # Claim only the event-keyed directory entry before reading it.  A producer
    # may refresh a later attempt concurrently, but a different event has a
    # different key and cannot have its context consumed by this call.
    claimed_path = path.with_name(f"{path.name}.consumed.{uuid.uuid4().hex}")
    try:
        path.rename(claimed_path)
    except OSError as exc:
        raise AdapterError("typed route context could not be consumed safely") from exc
    try:
        context = _read_json_file(
            str(claimed_path),
            label="typed route context",
            maximum=MAX_CONTEXT_BYTES,
        )
        if set(context) != CONTEXT_FIELDS:
            raise AdapterError("typed route context fields are not exact")
        if context.get("schema_version") != CONTEXT_SCHEMA_VERSION:
            raise AdapterError("typed route context schema is unsupported")
    except Exception:
        try:
            claimed_path.unlink()
        except OSError as cleanup_exc:
            raise AdapterError(
                "claimed typed route context could not be removed safely"
            ) from cleanup_exc
        raise
    try:
        claimed_path.unlink()
    except OSError as exc:
        raise AdapterError("claimed typed route context could not be removed safely") from exc
    return context


def _verify_attempt_binding(
    event: Mapping[str, Any],
    context: Mapping[str, Any],
) -> None:
    attempt = context.get("attempt")
    if not isinstance(attempt, dict) or set(attempt) != set(ATTEMPT_IDENTITY_FIELDS):
        raise AdapterError("typed route context attempt identity is not exact")
    expected = _attempt_identity_coordinates(attempt, label_prefix="context ")
    actual = _attempt_identity_coordinates(event)
    for label in ATTEMPT_IDENTITY_FIELDS:
        if expected[label] != actual[label]:
            raise AdapterError(
                f"typed route context does not bind to this tool call ({label})"
            )


def _build_intent(
    event: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    intent_class: Any,
    provenance_factory: Any,
) -> Any:
    session_id = _required_string(event.get("session_id"), "session_id")
    turn_id = _required_string(event.get("turn_id"), "turn_id")
    tool_use_id = _required_string(event.get("tool_use_id"), "tool_use_id")
    if "tool_input" not in event:
        raise AdapterError("missing tool_input")

    event_digest = hashlib.sha256(
        "\0".join((session_id, turn_id, tool_use_id)).encode("utf-8")
    ).hexdigest()
    try:
        return intent_class(
            intent_id=f"codex-pretool:{event_digest}",
            correlation_id=f"codex-pretool:{session_id}:{turn_id}:{tool_use_id}",
            goal_ref=context["goal_ref"],
            current_holder_ref=context["current_holder_ref"],
            route_anchor=context["route_anchor"],
            phase=context["phase"],
            agent_tool_requested=True,
            boundary_state=context["boundary_state"],
            responsibility_result_ref=context["responsibility_result_ref"],
            local_next_route=context["local_next_route"],
            provenance=provenance_factory(),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AdapterError("typed route context failed SDK validation") from exc


def _workspace_root(event: Mapping[str, Any]) -> Path:
    # The attempted Codex event is the only workspace authority.  Ambient
    # routing/federation variables can belong to another checkout and must not
    # redirect this attempt's SDK discovery.
    value = event.get("cwd")
    if not isinstance(value, str) or not value:
        raise AdapterError("SDK workspace root is unavailable")
    root = Path(value).expanduser()
    if not root.is_absolute() or not root.is_dir():
        raise AdapterError("SDK workspace root is unavailable")
    return root


def route_agent_tool_event(
    event: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Route one valid Codex agent-tool event and return native hook output."""

    environment = os.environ if environ is None else environ
    tool_name = event.get("tool_name")
    classification = _tool_class(tool_name)
    if classification == "other":
        return {}
    if classification == "malformed":
        return _deny(
            "Codex PreToolUse input has no tool identity; the agent-routing adapter "
            "did not invent one and blocked the call safely."
        )
    if event.get("hook_event_name") != CODEX_PRE_TOOL_EVENT:
        return _deny("Codex PreToolUse event identity is invalid; call blocked safely.")
    if classification == "unknown-agent":
        return _deny(
            "Unknown Codex agent-tool identity; the adapter cannot prove "
            "the wire contract and blocked the call safely."
        )

    try:
        context = _claim_context(environment, event)
        _verify_attempt_binding(event, context)
        (
            control_plane_api,
            provenance_factory,
            intent_class,
            workspace_class,
            _source_root,
        ) = _load_sdk(environment)
        intent = _build_intent(
            event,
            context,
            intent_class=intent_class,
            provenance_factory=provenance_factory,
        )
        workspace = workspace_class.discover(_workspace_root(event))
        decision = control_plane_api(workspace).pre_tool_route(intent)
    except AdapterError as exc:
        return _deny(
            "Codex agent-tool call blocked before execution: "
            f"{exc}. Present the typed responsibility boundary through "
            "aoa-agents-skills before retrying."
        )
    except Exception as exc:  # pragma: no cover - defensive hook boundary
        return _deny(
            "Codex agent-tool call blocked before execution because the typed "
            f"SDK route was unavailable ({type(exc).__name__}); no identity was "
            "invented. Present the responsibility boundary through "
            "aoa-agents-skills before retrying."
        )

    if (
        decision.status == "compatibility_local"
        and decision.dispatch_posture == "allow_codex_local_after_classification"
        and decision.built_in_codex_agent == "deferred_until_classified"
    ):
        return {}

    if decision.status in {"awaiting_classification", "owner_route"}:
        return _deny(
            "Codex agent-tool call blocked before execution by aoa-sdk "
            f"pre_tool_route: status={decision.status}; "
            f"next_owner={decision.next_owner}; "
            f"dispatch={decision.dispatch_posture}. Present the typed "
            "responsibility boundary through the owner's role-first entry "
            "before retrying."
        )

    return _deny(
        "Codex agent-tool call blocked before execution because aoa-sdk returned "
        f"an unsupported pre_tool_route posture: status={decision.status}; "
        f"dispatch={decision.dispatch_posture}."
    )


def handle_event(
    event: Any,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not isinstance(event, dict):
        return _deny(
            "Codex PreToolUse input is not an object; the agent-routing adapter "
            "did not invent identity and blocked the call safely."
        )
    return route_agent_tool_event(event, environ=environ)


def main() -> int:
    timer_available = hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")
    previous_handler: Any = None
    if timer_available:
        previous_handler = signal.signal(
            signal.SIGALRM,
            _raise_timeout,
        )
        signal.setitimer(signal.ITIMER_REAL, INTERNAL_TIMEOUT_SECONDS)
    try:
        raw = sys.stdin.buffer.read(MAX_EVENT_BYTES + 1)
        if len(raw) > MAX_EVENT_BYTES:
            raise AdapterError("Codex PreToolUse input is too large")
        event = json.loads(raw.decode("utf-8"))
        output = handle_event(event)
    except (AdapterError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        output = _deny(
            "Codex PreToolUse input could not be validated; the agent-routing "
            f"adapter blocked the call safely ({type(exc).__name__})."
        )
    except Exception as exc:  # pragma: no cover - process boundary fallback
        output = _deny(
            "Codex PreToolUse adapter failed closed before execution "
            f"({type(exc).__name__})."
        )
    finally:
        if timer_available:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
    sys.stdout.write(json.dumps(output, sort_keys=True, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
