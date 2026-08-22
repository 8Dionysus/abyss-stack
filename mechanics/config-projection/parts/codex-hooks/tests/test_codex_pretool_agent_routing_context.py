from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat

from jsonschema import Draft202012Validator


PART_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PART_ROOT / "scripts" / "codex_pretool_agent_routing_context.py"
FRAGMENT_PATH = PART_ROOT / "config" / "abyss-stack-agent-tool-routing-context.fragment.json"
SCHEMA_PATH = PART_ROOT / "schemas" / "codex-pretool-agent-routing-context.schema.json"

SPEC = importlib.util.spec_from_file_location("codex_pretool_agent_routing_context", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
RELAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELAY)


def base() -> dict[str, object]:
    return {
        "attempt": {},
        "boundary_state": "unresolved",
        "current_holder_ref": {
            "digest": "sha256:" + "1" * 64,
            "object_id": "holder:test",
            "owner_repo": "codex-goal",
            "schema_version": "holder-v1",
        },
        "goal_ref": {
            "digest": "sha256:" + "2" * 64,
            "object_id": "goal:test",
            "owner_repo": "codex-goal",
            "schema_version": "goal-v1",
        },
        "local_next_route": None,
        "phase": "initial",
        "responsibility_result_ref": None,
        "route_anchor": "goal:test",
        "schema_version": "aoa_codex_pretool_agent_routing_context_v2",
    }


def event() -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "session-test",
        "turn_id": "turn-test",
        "tool_use_id": "tool-test",
        "tool_name": "spawn_agent",
        "tool_input": {"opaque": "must-not-be-copied"},
    }


def context_path(directory: Path, attempt: dict[str, str]) -> Path:
    return directory / f"attempt-{RELAY._attempt_key(attempt)}.json"


def test_relay_materializes_one_event_keyed_context_without_tool_input(tmp_path: Path) -> None:
    directory = tmp_path / "contexts"
    directory.mkdir()
    base_path = tmp_path / "base.json"
    base_path.write_text(json.dumps(base()), encoding="utf-8")
    environment = {
        RELAY.CONTEXT_DIRECTORY_ENV: str(directory),
        RELAY.CONTEXT_BASE_ENV: str(base_path),
    }

    assert RELAY.handle_event(event(), environment) == {}
    attempt = {field: event()[field] for field in RELAY.ATTEMPT_FIELDS}
    target = context_path(directory, attempt)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    context = json.loads(target.read_text(encoding="utf-8"))
    assert context["attempt"] == attempt
    assert "tool_input" not in context

    original = target.read_bytes()
    assert RELAY.handle_event(event(), environment) == {}
    assert target.read_bytes() == original


def test_relay_fails_closed_without_mutating_context_for_bad_base(tmp_path: Path) -> None:
    directory = tmp_path / "contexts"
    directory.mkdir()
    base_path = tmp_path / "base.json"
    bad_base = base()
    bad_base["attempt"] = {"stale": True}
    base_path.write_text(json.dumps(bad_base), encoding="utf-8")

    assert RELAY.handle_event(
        event(),
        {
            RELAY.CONTEXT_DIRECTORY_ENV: str(directory),
            RELAY.CONTEXT_BASE_ENV: str(base_path),
        },
    ) == {}
    assert list(directory.iterdir()) == []


def test_relay_fragment_and_schema_are_source_valid() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    complete = base()
    complete["attempt"] = {
        "session_id": "session-test",
        "turn_id": "turn-test",
        "tool_use_id": "tool-test",
        "tool_name": "spawn_agent",
    }
    Draft202012Validator(schema).validate(complete)
    fragment = json.loads(FRAGMENT_PATH.read_text(encoding="utf-8"))
    assert fragment["fragment_id"] == "abyss-stack:agent-tool-routing-context-relay:v1"
    assert fragment["bindings"] == [
        "AOA_CODEX_AGENT_ROUTING_CONTEXT_RELAY",
        "AOA_CODEX_AGENT_ROUTING_CONTEXT_DIR",
    ]


def test_relay_source_has_no_task_or_role_identity_constants() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "019fbb8a-e084-7e73-9a98-647a1dd76985",
        "gpt-5.6-luna",
        "/home/dionysus/src/.worktrees",
        "aoa-external-actors-goal",
    ):
        assert forbidden not in source
