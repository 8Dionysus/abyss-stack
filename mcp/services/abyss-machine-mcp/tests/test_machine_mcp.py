from __future__ import annotations

import json
from typing import Any

import pytest

from abyss_machine_mcp.core import AbyssMachineMCPState, CommandOutput
from abyss_machine_mcp.server import build_server


STACK_BRIDGE = {
    "schema": "abyss_machine_stack_bridge_v1",
    "ok": True,
    "status": "ready",
    "generated_at": "2026-05-25T00:00:00Z",
    "latest": "/var/lib/abyss-machine/stack-bridge/latest.json",
    "summary": {
        "layers": 4,
        "refs": 5,
        "required_missing": 0,
        "schema_mismatches": 0,
    },
    "protected_roots": [
        {
            "path": "/home/dionysus/src/abyss-stack",
            "owner": "abyss_stack",
            "status": "protected_read_only",
        }
    ],
    "handoff_rules": ["Read cited latest files before making claims."],
    "non_claims": ["This bridge does not write to abyss-stack."],
    "commands": {
        "safe_read": ["abyss-machine stack-bridge --json"],
        "mutation_gates": ["abyss-machine changes preflight --intent TEXT --surface SURFACE --json"],
    },
    "refs": {
        "machine": {
            "bridge": {
                "path": "/etc/abyss-machine/bridge.json",
                "exists": True,
                "ok": True,
                "schema": "abyss_machine_bridge_v1",
                "truth_level": "contract",
                "generated_at": "2026-05-25T00:00:00Z",
            },
            "changes": {
                "path": "/var/lib/abyss-machine/changes/index.json",
                "exists": True,
                "ok": True,
                "schema": "abyss_machine_changes_index_v1",
                "truth_level": "change_ledger",
                "summary": {"active_records": 1},
            },
        },
        "memory": {
            "pressure": {
                "path": "/var/lib/abyss-machine/memory/latest.json",
                "exists": True,
                "ok": True,
                "schema": "abyss_machine_memory_pressure_v1",
                "truth_level": "latest_memory_pressure",
                "summary": {"class": "ok", "swap_used_percent": 2.0},
            }
        },
        "typing": {
            "status": {
                "path": "/var/lib/abyss-machine/typing/latest.json",
                "exists": True,
                "ok": True,
                "schema": "abyss_machine_typing_status_v1",
                "truth_level": "typing_intake_status",
            }
        },
    },
}

PAYLOADS: dict[tuple[str, ...], dict[str, Any]] = {
    ("stack-bridge", "--json"): STACK_BRIDGE,
    ("memory", "pressure", "--json"): {
        "schema": "abyss_machine_memory_pressure_v1",
        "ok": True,
        "generated_at": "2026-05-25T00:00:01Z",
        "summary": {"class": "ok", "swap_used_percent": 2.0},
    },
    ("typing", "status", "--json"): {
        "schema": "abyss_machine_typing_status_v1",
        "ok": True,
        "generated_at": "2026-05-25T00:00:02Z",
        "summary": {"sources": 3, "status": "ready"},
    },
    ("resource", "plan", "--class", "heavy", "--kind", "ai", "--json"): {
        "schema": "abyss_machine_resource_plan_v1",
        "ok": True,
        "summary": {"decision": "allow_with_observation", "class": "heavy", "kind": "ai"},
    },
    ("memory", "plan", "--json"): {
        "schema": "abyss_machine_memory_plan_v1",
        "ok": True,
        "summary": {"decision": "allow", "route": "observe"},
    },
    ("processes", "game-guard", "--json"): {
        "schema": "abyss_machine_game_guard_v1",
        "ok": True,
        "summary": {"active_game_processes": 0},
    },
    ("nervous", "recall", "--mode", "hybrid", "--query", "swap pressure", "--json"): {
        "schema": "abyss_machine_nervous_retrieval_pack_v1",
        "ok": True,
        "summary": {"evidence_items": 2},
    },
}


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        key = tuple(argv[1:])
        self.calls.append(key)
        payload = PAYLOADS.get(key)
        if payload is None:
            return CommandOutput(argv=argv, returncode=2, stdout="{}", stderr=f"unexpected command: {key}", elapsed_ms=1.0)
        return CommandOutput(argv=argv, returncode=0, stdout=json.dumps(payload), stderr="", elapsed_ms=1.0)


def state_with_fake(runner: FakeRunner | None = None) -> AbyssMachineMCPState:
    return AbyssMachineMCPState.discover(
        workspace_root="/tmp/abyss",
        abyss_machine_bin="abyss-machine",
        command_runner=runner or FakeRunner(),
        timeout_seconds=2,
    )


def test_fast_brief_returns_owner_constraints_and_evidence() -> None:
    runner = FakeRunner()
    state = state_with_fake(runner)
    brief = state.machine_brief(evidence_limit=2)

    assert brief["schema"] == "abyss_machine_mcp_brief_v1"
    assert brief["machine"]["bridge_status"] == "ready"
    assert brief["constraints"]["mutation_gates"]
    assert brief["evidence"]["count"] == 2
    assert brief["owner_layers"][0]["layer"] == "abyss-machine"
    assert brief["authority_boundary"]["mutation_posture"].startswith("no write")
    assert runner.calls.count(("stack-bridge", "--json")) == 1


def test_surface_allowlist_rejects_arbitrary_command() -> None:
    state = state_with_fake()

    with pytest.raises(ValueError):
        state.surface("shell")


def test_route_is_preflight_only_and_uses_allowlisted_surfaces() -> None:
    runner = FakeRunner()
    state = state_with_fake(runner)
    route = state.machine_route("start bounded local AI work", work_class="heavy", kind="ai")

    assert route["mutates"] is False
    assert route["route_posture"] == "preflight_only"
    assert ("resource", "plan", "--class", "heavy", "--kind", "ai", "--json") in runner.calls
    assert ("memory", "plan", "--json") in runner.calls
    assert ("processes", "game-guard", "--json") in runner.calls


def test_read_resource_and_recall() -> None:
    state = state_with_fake()

    resource = state.read_resource("abyss-machine://surface/memory-pressure")
    assert resource["surface"] == "memory-pressure"
    assert resource["ok"] is True

    recall = state.recall("swap pressure")
    assert recall["surface"] == "nervous-recall"
    assert recall["payload_schema"] == "abyss_machine_nervous_retrieval_pack_v1"


def test_server_builds_with_fake_runner() -> None:
    server = build_server(workspace_root="/tmp/abyss", command_runner=FakeRunner())

    assert server is not None
