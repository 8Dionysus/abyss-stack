from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
import threading
import time

from jsonschema import Draft202012Validator


PART_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PART_ROOT / "scripts" / "codex_pretool_agent_routing.py"
FRAGMENT_PATH = PART_ROOT / "config" / "abyss-stack-agent-tool-routing.fragment.json"
CONTEXT_SCHEMA_PATH = (
    PART_ROOT / "schemas" / "codex-pretool-agent-routing-context.schema.json"
)

spec = importlib.util.spec_from_file_location("codex_pretool_agent_routing", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
ADAPTER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ADAPTER)


def _ref(object_id: str, owner_repo: str, schema_version: str) -> dict[str, str]:
    return {
        "object_id": object_id,
        "owner_repo": owner_repo,
        "schema_version": schema_version,
        "digest": "sha256:" + "a" * 64,
    }


def context(boundary_state: str = "unresolved") -> dict[str, object]:
    result = None
    local_next_route = None
    if boundary_state == "independent":
        result = _ref("obligation:fixture", "aoa-agents", "agent-obligation-v1")
    elif boundary_state == "not_independent":
        result = _ref(
            "classification:fixture",
            "aoa-agents",
            "responsibility-classification-v1",
        )
        local_next_route = "codex_local"
    return {
        "schema_version": ADAPTER.CONTEXT_SCHEMA_VERSION,
        "attempt": {
            "session_id": "session-fixture",
            "turn_id": "turn-fixture",
            "tool_use_id": "call-fixture",
            "tool_name": "spawn_agent",
        },
        "goal_ref": _ref("goal:fixture", "codex-goal", "goal-v1"),
        "current_holder_ref": _ref(
            "holder:fixture",
            "codex-goal",
            "holder-v1",
        ),
        "route_anchor": "goal:fixture",
        "phase": "initial",
        "boundary_state": boundary_state,
        "responsibility_result_ref": result,
        "local_next_route": local_next_route,
    }


def event(tool_name: str = "spawn_agent") -> dict[str, object]:
    return {
        "cwd": str(Path.cwd()),
        "hook_event_name": "PreToolUse",
        "session_id": "session-fixture",
        "turn_id": "turn-fixture",
        "tool_input": {
            "message": "opaque tool arguments must not cross the adapter output",
            "task_name": "fixture",
        },
        "tool_name": tool_name,
        "tool_use_id": "call-fixture",
    }


def context_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "routing-contexts"
    directory.mkdir(exist_ok=True)
    return directory


def context_file_path(
    tmp_path: Path,
    event_value: dict[str, object] | None = None,
) -> Path:
    current_event = event() if event_value is None else event_value
    return context_directory(tmp_path) / (
        f"{ADAPTER.CONTEXT_FILE_PREFIX}"
        f"{ADAPTER._attempt_identity_digest(current_event)}.json"
    )


def environment(tmp_path: Path) -> dict[str, str]:
    import aoa_sdk

    sdk_root = Path(aoa_sdk.__file__).resolve().parents[2]
    return {
        ADAPTER.CONTEXT_DIRECTORY_ENV: str(context_directory(tmp_path)),
        "AOA_AGENT_TOOL_ROUTING_WORKSPACE_ROOT": str(tmp_path),
        "AOA_SDK_SOURCE_ROOT": str(sdk_root),
    }


def write_context(
    tmp_path: Path,
    payload: dict[str, object],
    event_value: dict[str, object] | None = None,
) -> Path:
    path = context_file_path(tmp_path, event_value)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_exact_codex_agent_tool_routes_to_sdk_before_execution(tmp_path: Path) -> None:
    context_path = write_context(tmp_path, context())

    output = ADAPTER.handle_event(
        event(),
        environ=environment(tmp_path),
    )

    hook_output = output["hookSpecificOutput"]
    assert hook_output["permissionDecision"] == "deny"
    assert "status=awaiting_classification" in hook_output["permissionDecisionReason"]
    assert "next_owner=aoa-agents-skills" in hook_output["permissionDecisionReason"]
    assert "opaque tool arguments" not in json.dumps(output)


def test_context_claim_waits_for_concurrent_relay(tmp_path: Path) -> None:
    def produce_context() -> None:
        time.sleep(0.05)
        write_context(tmp_path, context())

    producer = threading.Thread(target=produce_context)
    producer.start()
    try:
        output = ADAPTER.handle_event(
            event(),
            environ=environment(tmp_path),
        )
    finally:
        producer.join()

    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "status=awaiting_classification" in reason


def test_independent_result_blocks_with_role_first_direction(tmp_path: Path) -> None:
    context_path = write_context(tmp_path, context("independent"))

    output = ADAPTER.handle_event(
        event(),
        environ=environment(tmp_path),
    )

    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "status=owner_route" in reason
    assert "next_owner=aoa-agents-skills" in reason


def test_typed_not_independent_allows_only_sdk_compatibility_posture(
    tmp_path: Path,
) -> None:
    context_path = write_context(tmp_path, context("not_independent"))

    assert ADAPTER.handle_event(
        event(),
        environ=environment(tmp_path),
    ) == {}

    assert not list(context_directory(tmp_path).glob("*.consumed.*"))

    reused = ADAPTER.handle_event(
        event(),
        environ=environment(tmp_path),
    )
    assert reused["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "for this tool call is unavailable" in reused["hookSpecificOutput"][
        "permissionDecisionReason"
    ]

    context_path.write_text(json.dumps(context("not_independent")), encoding="utf-8")
    assert ADAPTER.handle_event(
        event(),
        environ=environment(tmp_path),
    ) == {}


def test_context_is_claimed_before_reading_when_producer_refreshes_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context_path = write_context(tmp_path, context())
    original_read_json_file = ADAPTER._read_json_file

    def read_claimed_path(path_value: str, *, label: str, maximum: int):
        claimed_path = Path(path_value)
        assert ".consumed." in claimed_path.name
        context_path.write_text(
            json.dumps(context("independent")),
            encoding="utf-8",
        )
        return original_read_json_file(
            path_value,
            label=label,
            maximum=maximum,
        )

    monkeypatch.setattr(ADAPTER, "_read_json_file", read_claimed_path)
    output = ADAPTER.handle_event(
        event(),
        environ=environment(tmp_path),
    )

    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "status=awaiting_classification" in reason
    assert json.loads(context_path.read_text(encoding="utf-8"))["boundary_state"] == (
        "independent"
    )
    assert not list(context_directory(tmp_path).glob("*.consumed.*"))


def test_context_authorization_must_bind_to_the_winning_tool_call(
    tmp_path: Path,
) -> None:
    payload = context("not_independent")
    attempt = payload["attempt"]
    assert isinstance(attempt, dict)
    attempt["tool_use_id"] = "different-call"
    context_path = write_context(tmp_path, payload)

    output = ADAPTER.handle_event(
        event(),
        environ=environment(tmp_path),
    )

    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "does not bind to this tool call" in reason
    assert "different-call" not in json.dumps(output)


def test_context_claim_is_keyed_to_the_current_tool_call(tmp_path: Path) -> None:
    other_event = event("collaborationsend_message")
    other_payload = context("not_independent")
    other_attempt = other_payload["attempt"]
    assert isinstance(other_attempt, dict)
    other_attempt["tool_name"] = "collaborationsend_message"
    other_path = write_context(tmp_path, other_payload, other_event)

    output = ADAPTER.handle_event(
        event(),
        environ=environment(tmp_path),
    )

    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "for this tool call is unavailable" in reason
    assert other_path.is_file()


def test_oversized_context_fails_closed_after_bounded_read(tmp_path: Path) -> None:
    context_path = context_file_path(tmp_path)
    context_path.write_bytes(b"{" + b"x" * ADAPTER.MAX_CONTEXT_BYTES)

    output = ADAPTER.handle_event(
        event(),
        environ=environment(tmp_path),
    )

    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "typed route context is too large" in reason
    assert not list(context_directory(tmp_path).glob("*.consumed.*"))


def test_selected_sdk_root_must_contain_the_imported_package(
    tmp_path: Path,
) -> None:
    context_path = write_context(tmp_path, context())
    invalid_sdk_root = tmp_path / "sdk-without-package"
    (invalid_sdk_root / "src").mkdir(parents=True)

    output = ADAPTER.handle_event(
        event(),
        environ={
            **environment(tmp_path),
            "AOA_SDK_SOURCE_ROOT": str(invalid_sdk_root),
        },
    )

    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "no aoa_sdk package" in output["hookSpecificOutput"][
        "permissionDecisionReason"
    ]


def test_non_agent_tool_passes_without_route_context() -> None:
    assert ADAPTER.handle_event(
        event("Bash"),
        environ={},
    ) == {}


def test_workspace_root_uses_event_cwd_over_ambient_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    event_workspace = tmp_path / "event-workspace"
    ambient_workspace = tmp_path / "ambient-workspace"
    ambient_federation = tmp_path / "ambient-federation"
    event_workspace.mkdir()
    ambient_workspace.mkdir()
    ambient_federation.mkdir()
    monkeypatch.setenv(
        "AOA_AGENT_TOOL_ROUTING_WORKSPACE_ROOT",
        str(ambient_workspace),
    )
    monkeypatch.setenv("AOA_SDK_FEDERATION_ROOT", str(ambient_federation))
    attempted_event = event()
    attempted_event["cwd"] = str(event_workspace)

    assert ADAPTER._workspace_root(attempted_event) == event_workspace


def test_missing_context_fails_closed_without_inventing_identity(
    tmp_path: Path,
) -> None:
    output = ADAPTER.handle_event(
        event(),
        environ={
            "AOA_AGENT_TOOL_ROUTING_WORKSPACE_ROOT": str(tmp_path),
        },
    )

    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "typed Goal/current-holder route context is unavailable" in reason
    assert "session-fixture" not in json.dumps(output)
    assert "turn-fixture" not in json.dumps(output)


def test_unknown_agent_tool_does_not_bypass_the_adapter() -> None:
    output = ADAPTER.handle_event(event("collaboration_future_tool"), environ={})
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Unknown Codex agent-tool identity" in output["hookSpecificOutput"][
        "permissionDecisionReason"
    ]


def test_canonical_and_flattened_codex_agent_names_are_agent_tools() -> None:
    expected = {
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
    assert expected == set(ADAPTER.CODEX_AGENT_TOOL_NAMES)
    assert all(ADAPTER._tool_class(name) == "agent" for name in expected)
    assert ADAPTER._tool_class("multi_agent_v2future_tool") == "unknown-agent"


def test_context_schema_and_fragment_are_source_valid() -> None:
    context_schema = json.loads(CONTEXT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(context_schema)
    Draft202012Validator(context_schema).validate(context())

    fragment = json.loads(FRAGMENT_PATH.read_text(encoding="utf-8"))
    matcher = fragment["hooks"]["PreToolUse"][0]["matcher"]
    assert matcher == (
        "^(?:Agent|spawn_agent|(?:multi_agent_|collaboration)[A-Za-z0-9_]+|"
        "send_message|followup_task|wait_agent|list_agents|interrupt_agent)$"
    )
    assert re.fullmatch(matcher, "multi_agent_v2future_tool")
    assert re.fullmatch(matcher, "collaborationfuture_tool")
    assert not re.fullmatch(matcher, "Bash")
    assert fragment["bindings"] == [
        "AOA_CODEX_AGENT_ROUTING_HOOK",
        "AOA_CODEX_AGENT_ROUTING_CONTEXT_DIR",
        "AOA_CODEX_AGENT_ROUTING_SDK_SOURCE_ROOT",
    ]


def test_reusable_source_has_no_task_or_model_identity_constants() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "019fbb8a-e084-7e73-9a98-647a1dd76985",
        "gpt-5.6-luna",
        "/home/dionysus/src/.worktrees",
        "aoa-external-actors-goal",
    ):
        assert forbidden not in source
    assert len(ADAPTER.CODEX_AGENT_TOOL_NAMES) > 1
