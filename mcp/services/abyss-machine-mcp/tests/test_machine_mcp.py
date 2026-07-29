from __future__ import annotations

import asyncio
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
    ("stack-bridge", "latest", "--json"): STACK_BRIDGE,
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
    ("resource", "plan", "--class", "heavy", "--kind", "ai", "--no-write", "--json"): {
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
    ("maps", "paths", "--json"): {
        "schema": "abyss_machine_maps_paths_v1",
        "ok": True,
        "root": "/var/lib/abyss-machine/maps",
        "axes": [{"axis": "by-freshness"}, {"axis": "by-eval-packet"}],
    },
    ("maps", "policy", "--json"): {
        "schema": "abyss_machine_maps_policy_v1",
        "version": "0.8.83",
        "axes": [{"axis": "by-freshness"}, {"axis": "by-eval-packet"}],
        "policy": {"automatic_action": False, "automatic_response": False},
    },
    ("maps", "query", "--axis", "by-freshness", "--query", "semantic", "--json"): {
        "schema": "abyss_machine_maps_query_v1",
        "ok": True,
        "summary": {"results": 2, "axes_searched": 1},
        "truth_status": "generated_route_signal_not_source_truth",
        "results": [
            {
                "id": "by-freshness:semantic-ready",
                "axis": "by-freshness",
                "label": "semantic_ready",
                "route": "Open nervous semantic readiness",
                "truth_status": "generated_route_signal_not_source_truth",
                "evidence_refs": [{"path": "/var/lib/abyss-machine/nervous/indexes/semantic/latest.json"}],
            },
            {
                "id": "by-freshness:semantic-stale",
                "axis": "by-freshness",
                "label": "semantic_stale",
                "route": "Run semantic maintenance",
                "truth_status": "generated_route_signal_not_source_truth",
                "evidence_refs": [{"path": "/var/lib/abyss-machine/nervous/indexes/semantic/maintain/latest.json"}],
            },
        ],
    },
    ("maps", "query", "--axis", "by-eval-packet", "--json"): {
        "schema": "abyss_machine_maps_query_v1",
        "ok": True,
        "summary": {"results": 1, "axes_searched": 1},
        "truth_status": "generated_route_signal_not_source_truth",
        "results": [
            {
                "id": "by-eval-packet:proof-context-route",
                "axis": "by-eval-packet",
                "label": "proof-context route",
                "route": "Boundary context only",
                "truth_status": "generated_route_signal_not_source_truth",
                "evidence_refs": [{"path": "/etc/abyss-machine/MAPS.md"}],
            }
        ],
    },
    ("maps", "packet", "--axis", "by-eval-packet", "--reader-profile", "proof-context", "--limit", "4", "--json"): {
        "schema": "abyss_machine_maps_context_packet_v1",
        "ok": True,
        "packet_id": "maps-packet:test",
        "truth_status": "generated_route_signal_not_source_truth",
        "reader_profile": "proof-context",
        "profile_route": {
            "reader_role": "agent using bounded proof context",
            "purpose": "host/runtime evidence lens",
            "acceptance": "boundary context only",
        },
        "summary": {
            "entries": 1,
            "available_results": 1,
            "evidence_refs": 1,
            "automatic_action": False,
            "proof_verdict": False,
        },
        "entries": [
            {
                "id": "by-eval-packet:proof-context-route",
                "axis": "by-eval-packet",
                "label": "proof-context route",
                "truth_status": "generated_route_signal_not_source_truth",
                "evidence_refs": [{"path": "/etc/abyss-machine/MAPS.md"}],
            }
        ],
        "evidence_refs": [{"path": "/etc/abyss-machine/MAPS.md"}],
    },
    ("maps", "validate", "--json"): {
        "schema": "abyss_machine_maps_validate_v1",
        "ok": True,
        "summary": {"status": "ok", "fails": 0, "warnings": 0, "checks": 12},
    },
    (
        "rag",
        "trace",
        "--query",
        "machine RAG trace loop",
        "--axis",
        "by-rag-run",
        "--reader-profile",
        "retrieval-context",
        "--limit",
        "4",
        "--evidence-limit",
        "6",
        "--json",
    ): {
        "schema": "abyss_machine_rag_trace_v1",
        "ok": True,
        "trace_id": "rag-trace:test",
        "truth_status": "generated_trace_not_source_truth",
        "summary": {
            "packet_entries": 2,
            "evidence_opened": 2,
            "automatic_action": False,
            "memory_writeback": False,
            "proof_verdict": False,
        },
        "answer": {
            "schema": "abyss_machine_rag_answer_v1",
            "answer_type": "deterministic_evidence_route_trace",
            "non_claims": ["not a proof verdict", "not reviewed memory", "not KAG truth", "not delivery into AoA organs"],
        },
        "eval": {
            "schema": "abyss_machine_rag_eval_v1",
            "ok": True,
            "summary": {"status": "ok", "fails": 0, "warnings": 0, "checks": 6},
        },
        "evidence_snapshots": [
            {"path": "/var/lib/abyss-machine/nervous/retrieval/latest.json", "status": "json_summary"},
            {"path": "/var/lib/abyss-machine/rag/traces/latest.json", "status": "json_summary"},
        ],
    },
    ("rag", "latest", "--json"): {
        "schema": "abyss_machine_rag_trace_v1",
        "ok": True,
        "trace_id": "rag-trace:test",
        "summary": {"packet_entries": 2, "evidence_opened": 2},
    },
    ("rag", "validate", "--json"): {
        "schema": "abyss_machine_rag_validate_v1",
        "ok": True,
        "summary": {"status": "ok", "fails": 0, "warnings": 0, "checks": 9},
    },
    ("artifacts", "requirements", "--artifact-class", "public_source_seed", "--json"): {
        "schema": "abyss_machine_artifact_requirements_v1",
        "ok": True,
        "summary": {"artifact_classes": 1},
        "rows": [{"artifact_class": "public_source_seed", "controls": {"required": ["abi_signature"]}}],
    },
    (
        "artifacts",
        "producer-profiles",
        "--require-command-resolution",
        "--artifact-class",
        "public_source_seed",
        "--json",
    ): {
        "schema": "abyss_machine_artifact_producer_profiles_v1",
        "ok": True,
        "summary": {"profiles": 1, "command_resolution_checked": True},
        "rows": [{"owner_repo": "abyss-machine", "artifact_classes": ["public_source_seed"]}],
    },
    ("artifacts", "affected", "--artifact-class", "public_source_seed", "--json"): {
        "schema": "abyss_machine_artifacts_affected_v1",
        "ok": True,
        "summary": {"artifact_classes": 1, "affected": 0},
        "rows": [{"artifact_class": "public_source_seed", "freshness": "fresh"}],
    },
    (
        "artifacts",
        "affected",
        "--artifact-class",
        "public_source_seed",
        "--source-repo",
        "abyss-machine",
        "--source-ref",
        "source-refresh:main-abc123+dirty-deadbeef",
        "--json",
    ): {
        "schema": "abyss_machine_artifacts_affected_v1",
        "ok": True,
        "summary": {"artifact_classes": 1, "affected": 0},
        "changed_source_repo": "abyss-machine",
        "changed_source_ref": "source-refresh:main-abc123+dirty-deadbeef",
        "rows": [{"artifact_class": "public_source_seed", "freshness": "fresh"}],
    },
    ("artifacts", "trust-coverage", "--json"): {
        "schema": "abyss_machine_artifacts_trust_coverage_v1",
        "ok": True,
        "summary": {"artifact_classes": 21, "fully_covered": 20, "deferred_with_real_blocker": 1},
    },
    (
        "artifacts",
        "trust-coverage",
        "--source-repo",
        "abyss-machine",
        "--source-ref",
        "source-refresh:main-abc123+dirty-deadbeef",
        "--json",
    ): {
        "schema": "abyss_machine_artifacts_trust_coverage_v1",
        "ok": True,
        "source_context": {
            "requested_source_repo": "abyss-machine",
            "requested_source_ref": "source-refresh:main-abc123+dirty-deadbeef",
        },
        "summary": {"artifact_classes": 21, "fully_covered": 20, "deferred_with_real_blocker": 1},
    },
    (
        "artifacts",
        "trust-coverage",
        "--source-root",
        "/tmp/abyss/abyss-machine",
        "--source-repo",
        "abyss-machine",
        "--source-ref",
        "source-refresh:main-abc123+dirty-deadbeef",
        "--json",
    ): {
        "schema": "abyss_machine_artifacts_trust_coverage_v1",
        "ok": True,
        "source_context": {
            "public_seed_root": "/tmp/abyss/abyss-machine",
            "requested_source_repo": "abyss-machine",
            "requested_source_ref": "source-refresh:main-abc123+dirty-deadbeef",
        },
        "summary": {"artifact_classes": 21, "fully_covered": 20, "deferred_with_real_blocker": 1},
    },
    (
        "artifacts",
        "trust-gate",
        "--artifact-class",
        "public_media_export",
        "--consumer-intent",
        "release_consumer",
        "--json",
    ): {
        "schema": "abyss_machine_artifact_trust_gate_v1",
        "ok": True,
        "artifact_class": "public_media_export",
        "consumer_intent": "release_consumer",
        "verdict": "warn",
        "summary": {"verdict": "warn", "reasons": 1},
        "reasons": ["C2PA credential onboarding is pre-organization"],
    },
    (
        "artifacts",
        "registry-latest",
        "--artifact-class",
        "public_source_seed",
        "--consumer-intent",
        "agent",
        "--json",
    ): {
        "schema": "abyss_machine_artifact_registry_latest_v1",
        "ok": True,
        "artifact_class": "public_source_seed",
        "latest": {"record_id": "sha256:test"},
    },
    (
        "artifacts",
        "scenarios",
        "--registry-dir",
        "/var/lib/abyss-machine/artifacts/bundle-registry",
        "--json",
    ): {
        "schema": "abyss_machine_artifact_scenarios_v1",
        "ok": True,
        "summary": {"scenarios": 8},
    },
    ("artifacts", "validate", "--json"): {
        "schema": "abyss_machine_artifacts_validate_v1",
        "ok": True,
        "summary": {"status": "warn", "fails": 0, "warnings": 2},
    },
}


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.timeouts: list[tuple[tuple[str, ...], float]] = []

    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        key = tuple(argv[1:])
        self.calls.append(key)
        self.timeouts.append((key, timeout))
        payload = PAYLOADS.get(key)
        if payload is None:
            return CommandOutput(argv=argv, returncode=2, stdout="{}", stderr=f"unexpected command: {key}", elapsed_ms=1.0)
        return CommandOutput(argv=argv, returncode=0, stdout=json.dumps(payload), stderr="", elapsed_ms=1.0)


class NonJsonRunner(FakeRunner):
    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        key = tuple(argv[1:])
        self.calls.append(key)
        if key == ("memory", "pressure", "--json"):
            return CommandOutput(
                argv=argv,
                returncode=0,
                stdout="warning: changed output shape\nnot-json",
                stderr="",
                elapsed_ms=1.0,
            )
        return super().__call__(argv, timeout)


class MemoryPressureWatchRunner(FakeRunner):
    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        key = tuple(argv[1:])
        self.calls.append(key)
        if key == ("memory", "pressure", "--json"):
            return CommandOutput(
                argv=argv,
                returncode=1,
                stdout=json.dumps({
                    "schema": "abyss_machine_memory_pressure_v1",
                    "ok": False,
                    "summary": {"class": "watch", "swap_used_percent": 12.0},
                    "reasons": ["swap_used_percent=12.0>watch"],
                }),
                stderr="",
                elapsed_ms=1.0,
            )
        return super().__call__(argv, timeout)


class ArtifactManualReviewRunner(FakeRunner):
    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        key = tuple(argv[1:])
        self.calls.append(key)
        self.timeouts.append((key, timeout))
        if key == ("artifacts", "trust-coverage", "--json"):
            return CommandOutput(
                argv=argv,
                returncode=1,
                stdout=json.dumps({
                    "schema": "abyss_machine_artifacts_trust_coverage_v1",
                    "ok": False,
                    "summary": {
                        "artifact_classes": 21,
                        "fully_covered": 18,
                        "deferred_with_real_blocker": 3,
                    },
                }),
                stderr="",
                elapsed_ms=1.0,
            )
        return super().__call__(argv, timeout)


class ArtifactValidateFailureRunner(FakeRunner):
    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        key = tuple(argv[1:])
        self.calls.append(key)
        self.timeouts.append((key, timeout))
        if key == ("artifacts", "validate", "--json"):
            return CommandOutput(
                argv=argv,
                returncode=1,
                stdout=json.dumps({
                    "schema": "abyss_machine_artifacts_validate_v1",
                    "ok": False,
                    "summary": {"status": "fail", "fails": 1, "warnings": 0},
                }),
                stderr="artifact trust validation failed",
                elapsed_ms=1.0,
            )
        return super().__call__(argv, timeout)


class CoverageSourceContextUnsupportedRunner(FakeRunner):
    def __call__(self, argv: list[str], timeout: float) -> CommandOutput:
        key = tuple(argv[1:])
        self.calls.append(key)
        self.timeouts.append((key, timeout))
        if key == (
            "artifacts",
            "trust-coverage",
            "--source-repo",
            "abyss-machine",
            "--source-ref",
            "source-refresh:main-abc123+dirty-deadbeef",
            "--json",
        ):
            return CommandOutput(
                argv=argv,
                returncode=2,
                stdout="",
                stderr=(
                    "abyss-machine: error: unrecognized arguments: --source-repo abyss-machine "
                    "--source-ref source-refresh:main-abc123+dirty-deadbeef"
                ),
                elapsed_ms=1.0,
            )
        return super().__call__(argv, timeout)


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
    assert brief["authority_boundary"]["exposure"] == (
        "stdio-default; optional authenticated loopback streamable-http"
    )
    assert any(
        "local transport service topology" in item
        for layer in brief["owner_layers"]
        if layer["layer"] == "abyss-stack"
        for item in layer["owns"]
    )
    assert runner.calls.count(("stack-bridge", "latest", "--json")) == 1


def test_surface_allowlist_rejects_arbitrary_command() -> None:
    state = state_with_fake()

    with pytest.raises(ValueError):
        state.surface("shell")

    with pytest.raises(ValueError):
        state.surface("artifacts")


def test_route_is_preflight_only_and_uses_allowlisted_surfaces() -> None:
    runner = FakeRunner()
    state = state_with_fake(runner)
    route = state.machine_route("start bounded local AI work", work_class="heavy", kind="ai")

    assert route["mutates"] is False
    assert route["route_posture"] == "preflight_only"
    assert (
        "resource",
        "plan",
        "--class",
        "heavy",
        "--kind",
        "ai",
        "--no-write",
        "--json",
    ) in runner.calls
    assert ("memory", "plan", "--json") in runner.calls
    assert ("processes", "game-guard", "--json") not in runner.calls


def test_read_resource_and_effectful_recall_denial() -> None:
    runner = FakeRunner()
    state = state_with_fake(runner)

    resource = state.read_resource("abyss-machine://surface/memory-pressure")
    assert resource["surface"] == "memory-pressure"
    assert resource["ok"] is True

    with pytest.raises(ValueError, match="persists an evidence pack"):
        state.recall("swap pressure")
    assert not any(call[:2] == ("nervous", "recall") for call in runner.calls)


def test_surface_fails_closed_when_json_payload_is_unparsable() -> None:
    state = state_with_fake(NonJsonRunner())

    result = state.surface("memory-pressure")

    assert result["returncode"] == 0
    assert result["payload_parse_ok"] is False
    assert result["ok"] is False
    assert result["payload_summary"] is None


def test_memory_pressure_watch_is_a_readable_surface_not_transport_failure() -> None:
    state = state_with_fake(MemoryPressureWatchRunner())

    result = state.surface("memory-pressure")

    assert result["returncode"] == 1
    assert result["payload_parse_ok"] is True
    assert result["payload_ok"] is False
    assert result["ok"] is True
    assert result["payload_summary"]["class"] == "watch"


def test_effectful_artifact_diagnostics_are_denied_before_dispatch() -> None:
    runner = ArtifactManualReviewRunner()
    state = state_with_fake(runner)

    for surface in (
        "artifact-trust-coverage",
        "artifact-trust-validate",
        "artifact-trust-requirements",
        "artifact-trust-producer-profiles",
        "artifact-trust-affected",
        "artifact-trust-scenarios",
    ):
        with pytest.raises(ValueError, match="effectful and unavailable"):
            state.surface(surface)
    assert runner.calls == []


def test_maps_tool_queries_axis_as_route_signals() -> None:
    runner = FakeRunner()
    state = state_with_fake(runner)
    maps = state.machine_maps(axis="by-freshness", query="semantic", limit=1)

    assert maps["schema"] == "abyss_machine_mcp_maps_v1"
    assert maps["ok"] is True
    assert maps["truth_status"] == "generated_route_signal_not_source_truth"
    assert maps["result_count"] == 2
    assert len(maps["results"]) == 1
    assert maps["results"][0]["label"] == "semantic_ready"
    assert ("maps", "query", "--axis", "by-freshness", "--query", "semantic", "--json") in runner.calls


def test_maps_resource_and_surfaces_are_allowlisted() -> None:
    state = state_with_fake()

    paths = state.surface("maps-paths")
    assert paths["payload_schema"] == "abyss_machine_maps_paths_v1"

    policy = state.surface("maps-policy")
    assert policy["payload_schema"] == "abyss_machine_maps_policy_v1"

    with pytest.raises(ValueError, match="effectful and unavailable"):
        state.surface("maps-validate")

    resource = state.read_resource("abyss-machine://maps/by-eval-packet")
    assert resource["axis"] == "by-eval-packet"
    assert resource["result_count"] == 1


def test_artifact_trust_surfaces_are_allowlisted_and_typed() -> None:
    runner = FakeRunner()
    state = state_with_fake(runner)

    gate = state.surface(
        "artifact-trust-gate",
        artifact_class="public_media_export",
        consumer_intent="release_consumer",
    )
    assert gate["payload_schema"] == "abyss_machine_artifact_trust_gate_v1"
    assert gate["payload_summary"]["verdict"] == "warn"
    assert gate["effect"] == "read"
    assert gate["persistent_writes"] is False

    latest = state.surface("artifact-trust-registry-latest", artifact_class="public_source_seed")
    assert latest["payload_schema"] == "abyss_machine_artifact_registry_latest_v1"

    assert (
        "artifacts",
        "trust-gate",
        "--artifact-class",
        "public_media_export",
        "--consumer-intent",
        "release_consumer",
        "--json",
    ) in runner.calls
    assert (
        (
            "artifacts",
            "trust-gate",
            "--artifact-class",
            "public_media_export",
            "--consumer-intent",
            "release_consumer",
            "--json",
        ),
        45.0,
    ) in runner.timeouts


def test_artifact_trust_surfaces_reject_unsafe_or_incomplete_parameters() -> None:
    state = state_with_fake()

    with pytest.raises(ValueError):
        state.surface("artifact-trust-gate")

    with pytest.raises(ValueError):
        state.surface("artifact-trust-registry-latest")

    with pytest.raises(ValueError, match="effectful and unavailable"):
        state.surface("artifact-trust-requirements", artifact_class="../private")

    with pytest.raises(ValueError, match="effectful and unavailable"):
        state.surface("artifact-trust-affected", source_ref="source-refresh:main;rm -rf /")

    with pytest.raises(ValueError, match="effectful and unavailable"):
        state.surface("artifact-trust-coverage", source_root="/etc")


def test_context_packet_wraps_host_owned_packet() -> None:
    runner = FakeRunner()
    state = state_with_fake(runner)
    packet = state.machine_context_packet(axis="by-eval-packet", reader_profile="proof-context", limit=4)

    assert packet["schema"] == "abyss_machine_mcp_context_packet_v1"
    assert packet["ok"] is True
    assert packet["packet_schema"] == "abyss_machine_maps_context_packet_v1"
    assert packet["packet_truth_status"] == "generated_route_signal_not_source_truth"
    assert packet["summary"]["entries"] == 1
    assert packet["profile_route"]["reader_role"] == "agent using bounded proof context"
    assert ("maps", "packet", "--axis", "by-eval-packet", "--reader-profile", "proof-context", "--limit", "4", "--json") in runner.calls


def test_rag_latest_is_readable_but_trace_and_validate_are_denied() -> None:
    runner = FakeRunner()
    state = state_with_fake(runner)

    resource = state.read_resource("abyss-machine://rag")
    assert resource["payload_schema"] == "abyss_machine_rag_trace_v1"

    with pytest.raises(ValueError, match="persists generated trace"):
        state.machine_rag_trace("machine RAG trace loop", limit=4, evidence_limit=6)
    with pytest.raises(ValueError, match="effectful and unavailable"):
        state.surface("rag-validate")
    assert not any(call[:2] == ("rag", "trace") for call in runner.calls)


def test_surface_catalog_and_server_expose_only_read_routes() -> None:
    state = state_with_fake()
    catalog = state.available_surfaces()

    assert catalog["policy_family"] == "read"
    assert catalog["count"] == len(catalog["surfaces"])
    assert all(item["effect"] == "read" for item in catalog["surfaces"])
    assert all(item["persistent_writes"] is False for item in catalog["surfaces"])
    assert "nervous-recall" in catalog["withdrawn_effectful_surfaces"]
    assert "artifact-trust-coverage" in catalog["withdrawn_effectful_surfaces"]

    server = build_server(workspace_root="/tmp/abyss", command_runner=FakeRunner())
    tools = {tool.name for tool in asyncio.run(server.list_tools())}
    assert "abyss_machine_surfaces" in tools
    assert "abyss_machine_recall" not in tools
    assert "abyss_machine_rag_trace" not in tools


def test_server_builds_with_fake_runner() -> None:
    server = build_server(workspace_root="/tmp/abyss", command_runner=FakeRunner())

    assert server is not None
    assert server._mcp_server.version == "0.2.0"
