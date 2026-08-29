from __future__ import annotations

import copy
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest


LAB_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = LAB_ROOT / "scripts" / "build_protocol_lab_status.py"
VALIDATOR_PATH = LAB_ROOT / "scripts" / "validate_protocol_lab.py"


def _load_builder() -> Any:
    spec = importlib.util.spec_from_file_location(
        "protocol_lab_builder_under_test",
        BUILDER_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "protocol_lab_validator_under_test",
        VALIDATOR_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def builder() -> Any:
    return _load_builder()


@pytest.fixture
def matrix(builder: Any) -> dict[str, Any]:
    return _load(builder.MATRIX_PATH)


@pytest.fixture
def observation(builder: Any) -> dict[str, Any]:
    return _load(builder.OBSERVATION_PATH)


def test_current_status_is_deterministic_and_keeps_deployment_cutover_blocked(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    first = builder.build_status(matrix, observation)
    second = builder.build_status(copy.deepcopy(matrix), copy.deepcopy(observation))

    assert first == second
    assert first["evidence_expires_at"] > first["tasks_evidence_expires_at"]
    assert first["gate_counts"] == {"passed": 14, "blocked": 0, "pending": 0}
    assert first["passed_gate_ids"] == [f"P1-{index:02d}" for index in range(1, 15)]
    assert first["core_read_migration_allowed"] is False
    assert first["read_only_pilot_allowed"] is True
    assert first["read_only_pilot_completed"] is True
    assert first["tasks_extension_allowed"] is False
    assert first["tasks_evidence_expires_at"] == "2026-08-16T13:53:36.813735Z"
    assert first["tasks_reference_consumer"] == "rust-rmcp-3.1.2"
    assert first["tasks_reference_pair_passed"] is True
    assert first["tasks_inspector_strict_pair_blocked"] is True
    assert first["tasks_codex_consumer_eligible"] is False
    assert first["tasks_production_enabled"] is True
    assert first["tasks_blockers"] == [
        "input_required_update_live_pair_unproved",
        "tasks_notifications_unproved",
        "distributed_poll_limit_unproved",
    ]
    assert first["candidate_protocol_ready"] is True
    assert first["internal_effect_protocol_ready"] is False
    assert first["candidate_migration_allowed"] is False
    assert first["internal_effect_migration_allowed"] is False
    assert first["external_effect_migration_allowed"] is False
    assert first["remaining_core_gate_ids"] == []
    assert first["remaining_tasks_gate_ids"] == []
    assert first["production_cutover_blockers"] == [
        "deployment_bound_evidence_not_refreshed_for_mcp_2_1_1"
    ]
    assert first["stable_registration_retained"] is True


def test_final_spec_and_stable_sdks_are_part_of_admitted_migration(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    status = builder.build_status(copy.deepcopy(matrix), observation)

    assert status["core_read_migration_allowed"] is False
    assert status["read_only_pilot_allowed"] is True


def test_production_consumer_is_bound_to_wire_pair_evidence(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    consumer = next(
        item for item in matrix["consumer_pairs"]
        if item["consumer_id"] == "codex-cli-os-abyss"
    )
    assert consumer["next_protocol_literal_present"] is True

    status = builder.build_status(matrix, observation)

    assert consumer["capability_posture"] == "supported"
    assert "production_modern_pair_not_admitted" not in status["reason_codes"]
    assert status["core_read_migration_allowed"] is False
    assert "deployment_bound_evidence_not_refreshed_for_mcp_2_1_1" in status[
        "production_cutover_blockers"
    ]


def test_codex_wire_receipt_proves_legacy_pair_only(builder: Any) -> None:
    wire_observation_path = (
        LAB_ROOT / "fixtures" / "codex-0.146.0-wire-observation.json"
    )
    wire_schema_path = (
        LAB_ROOT / "schemas" / "protocol-consumer-wire-observation.schema.json"
    )
    wire_observation = _load(wire_observation_path)

    builder.validate_payload(wire_observation, wire_schema_path)

    assert wire_observation["wire_protocol_offered"] == "2025-06-18"
    assert wire_observation["wire_protocol_selected"] == "2025-06-18"
    assert wire_observation["method_sequence"][0] == "initialize"
    assert wire_observation["server_discover_observed"] is False
    assert wire_observation["next_wire_pair_observed"] is False
    assert wire_observation["global_codex_config_mutated"] is False


def test_production_pair_is_distinct_from_next_sdk_fallback(
    matrix: dict[str, Any],
) -> None:
    consumer = next(
        item for item in matrix["consumer_pairs"]
        if item["consumer_id"] == "codex-cli-os-abyss"
    )

    assert matrix["production_protocol"] == "2026-07-28"
    assert matrix["stable_spec"]["wire_version"] == "2025-11-25"
    assert consumer["production_protocol_versions_observed"] == ["2026-07-28"]
    assert consumer["isolated_next_sdk_fallback_protocol"] == "2026-07-28"


def test_production_pair_receipt_is_public_safe_and_bounded(builder: Any) -> None:
    receipt_path = (
        LAB_ROOT / "fixtures" / "codex-0.146.0-production-pair-observation.json"
    )
    schema_path = (
        LAB_ROOT / "schemas" / "protocol-production-pair-observation.schema.json"
    )
    receipt = _load(receipt_path)

    builder.validate_payload(receipt, schema_path)

    assert receipt["registration"]["wire_protocol_versions"] == ["2025-11-25"]
    assert receipt["call"]["is_error"] is False
    assert receipt["secrets_included"] is False
    assert "does not prove a 2026-07-28" in " ".join(receipt["claim_limits"])


def test_expired_production_pair_receipt_is_rejected() -> None:
    validator = _load_validator()
    receipt = _load(
        LAB_ROOT / "fixtures" / "codex-0.146.0-production-pair-observation.json"
    )
    expires_at = datetime.fromisoformat(
        receipt["expires_at"].replace("Z", "+00:00")
    )

    error = validator._expiry_error(
        "Codex production-pair observation",
        receipt,
        expires_at + timedelta(seconds=1),
    )

    assert error == (
        "Codex production-pair observation expired at "
        f"{receipt['expires_at']}; refresh is required"
    )


def test_official_frozen_conformance_receipt_is_sdk_scoped(builder: Any) -> None:
    conformance_path = (
        LAB_ROOT / "fixtures" / "python-mcp-2.0.0-frozen-conformance-observation.json"
    )
    conformance_schema_path = (
        LAB_ROOT / "schemas" / "protocol-frozen-conformance-observation.schema.json"
    )
    conformance = _load(conformance_path)

    builder.validate_payload(conformance, conformance_schema_path)

    assert conformance["spec_version"] == "2026-07-28"
    assert conformance["requirements_revision"] == "2026-07-28"
    assert conformance["directions"]["server"]["scored_success_checks"] == 119
    assert conformance["directions"]["client"]["scored_success_checks"] == 372
    assert conformance["directions"]["server"]["scored_failed_checks"] == 0
    assert conformance["directions"]["client"]["scored_failed_checks"] == 0
    assert conformance["verdict"] == "sdk_pair_passed_frozen_2026_07_28_requirements"
    assert "Codex" in " ".join(conformance["claim_limits"])


def test_mcp_211_candidate_receipts_are_source_bound(builder: Any) -> None:
    candidates = {
        "python-mcp-2.1.1-frozen-conformance-observation.json":
            "protocol-frozen-conformance-observation.schema.json",
        "kag-next-cancellable-pair-2.1.1-observation.json":
            "kag-next-cancellable-pair-observation.schema.json",
        "kag-handle-pair-2.1.1-current-observation.json":
            "kag-handle-pair-current-observation.schema.json",
        "kag-cache-pair-2.1.1-current-observation.json":
            "kag-cache-pair-current-observation.schema.json",
        "codex-0.147.0-stable-kag-next-lab-2.1.1-observation.json":
            "codex-kag-next-stable-observation.schema.json",
    }

    for fixture_name, schema_name in candidates.items():
        receipt = _load(LAB_ROOT / "fixtures" / fixture_name)
        builder.validate_payload(receipt, LAB_ROOT / "schemas" / schema_name)

    conformance = _load(
        LAB_ROOT / "fixtures" / "python-mcp-2.1.1-frozen-conformance-observation.json"
    )
    assert conformance["python_sdk"] == {
        "commit": "0921d94a74db900dccd2d534842aa7b6160542d2",
        "source_checkout_clean": True,
        "version": "2.1.1",
    }
    assert conformance["directions"]["client"]["visibility"]["failed_checks"] == 9

    codex = _load(
        LAB_ROOT
        / "fixtures"
        / "codex-0.147.0-stable-kag-next-lab-2.1.1-observation.json"
    )
    assert codex["server"]["python_mcp_version"] == "2.1.1"
    assert codex["server"]["source_revisions"] == {
        "abyss_stack": "c22ec7626d07ec66ff32569a2cc1b1b82e45f7b4",
        "aoa_kag": "578e4cea9a04b76a881bde240d5479efceea4926",
    }
    assert codex["consumer"]["production_authority"] is False


def test_kag_next_cancellable_pair_is_adapter_scoped(builder: Any) -> None:
    pair_path = LAB_ROOT / "fixtures" / "kag-next-cancellable-pair-observation.json"
    pair_schema_path = (
        LAB_ROOT / "schemas" / "kag-next-cancellable-pair-observation.schema.json"
    )
    pair = _load(pair_path)

    builder.validate_payload(pair, pair_schema_path)

    assert pair["pair"]["wire_version"] == "2026-07-28"
    assert pair["pair"]["server_discover_observed"] is True
    assert pair["pair"]["session_header_observed"] is False
    assert pair["pair"]["server_request_backchannel_observed"] is False
    assert pair["pair"]["cache"]["repeat_tools_list_wire_fetches"] == 1
    assert pair["pair"]["trace_sent"] == pair["pair"]["trace_observed"]
    assert pair["stable_registration"]["unchanged"] is True
    assert pair["owner_canary"]["projection_exact_state"] == "current"
    assert pair["owner_canary"]["freshness_state"] == "current"
    assert pair["pair"]["cancellation"] == {
        "client_request_cancelled": True,
        "server_dispatch_cancelled": True,
        "server_dispatch_completed_after_client_cancel": False,
    }
    assert "Codex" in " ".join(pair["claim_limits"])


def test_kag_request_state_handles_are_read_scoped(builder: Any) -> None:
    handle_path = (
        LAB_ROOT / "fixtures" / "kag-handle-pair-current-observation.json"
    )
    handle_schema_path = (
        LAB_ROOT / "schemas" / "kag-handle-pair-current-observation.schema.json"
    )
    handle = _load(handle_path)

    builder.validate_payload(handle, handle_schema_path)

    assert handle["handle_contract"]["opaque"] is True
    assert handle["handle_contract"]["plaintext_observed_on_wire"] is False
    assert handle["handle_contract"]["principal_binding"] == [
        "client_id",
        "issuer",
        "subject",
    ]
    assert handle["handle_checks"]["principal_isolation"] == "denied"
    assert handle["handle_checks"]["expiry"] == "denied"
    assert handle["handle_checks"]["cross_request_replay"] == "denied"
    assert (
        handle["handle_checks"]["same_request_replay"]
        == "allowed_read_only_idempotent"
    )
    assert handle["handle_checks"]["key_retirement_revocation"] == "denied"
    assert "Effectful" in " ".join(handle["claim_limits"])


def test_kag_catalog_cache_is_bounded_and_non_authoritative(
    builder: Any,
) -> None:
    cache_path = LAB_ROOT / "fixtures" / "kag-cache-pair-current-observation.json"
    cache_schema_path = (
        LAB_ROOT / "schemas" / "kag-cache-pair-current-observation.schema.json"
    )
    cache = _load(cache_path)

    builder.validate_payload(cache, cache_schema_path)

    assert cache["cache"] == {
        "scope": "private",
        "ttl_ms": 30000,
        "within_ttl_repeat_server_fetches": 1,
    }
    assert cache["checks"]["subscription_addition_invalidation"] is True
    assert cache["checks"]["subscription_removal_revocation"] is True
    assert cache["checks"]["ttl_expiry_refetch"] is True
    assert cache["checks"]["no_subscription_no_replay"] is True
    assert cache["checks"]["stale_catalog_cannot_authorize_removed_tool"]
    assert cache["inventories"]["stale_after_removal"] == [
        "kag_discover",
        "kag_stale_probe",
    ]
    assert cache["inventories"]["after_explicit_refresh"] == [
        "kag_discover"
    ]
    assert "never grants tool authorization" in " ".join(
        cache["claim_limits"]
    )


def test_tasks_adapter_pilot_is_feature_gated_and_bounded(builder: Any) -> None:
    receipt_path = LAB_ROOT / "fixtures" / "tasks-adapter-pilot-20260808.json"
    schema_path = LAB_ROOT / "schemas" / "tasks-adapter-pilot.schema.json"
    receipt = _load(receipt_path)

    builder.validate_payload(receipt, schema_path)

    assert receipt["protocol_version"] == "2026-07-28"
    assert receipt["extension_id"] == "io.modelcontextprotocol/tasks"
    assert receipt["adapter_feature_gate_enabled"] is True
    assert receipt["production_enabled"] is False
    assert receipt["codex_consumer_used"] is False
    assert receipt["all_cases_passed"] is True
    assert receipt["case_count"] == 11
    assert receipt["notifications"]["tested"] is False
    assert receipt["owner_pilot"]["resumed_after_adapter_restart"] is True
    assert receipt["owner_pilot"]["owner_rerun_count"] == 0
    assert "does not imply repair" in " ".join(receipt["claim_limits"])


def test_tasks_compatibility_matrix_keeps_pair_evidence_distinct(builder: Any) -> None:
    matrix = _load(LAB_ROOT / "tasks-compatibility-matrix.v1.json")
    schema = LAB_ROOT / "schemas" / "tasks-compatibility-matrix.schema.json"
    builder.validate_payload(matrix, schema)
    rows = {item["consumer_id"]: item for item in matrix["consumers"]}

    assert matrix["production_tasks_allowed"] is True
    assert matrix["core_read_migration_independent"] is True
    assert rows["codex-cli-os-abyss"]["features"]["advertisement"] == "wire_pass"
    assert rows["codex-cli-os-abyss"]["features"]["tasks_cancel"] == "wire_pass"
    assert rows["codex-cli-os-abyss"]["verdict"] == "eligible_for_bounded_production"
    assert rows["codex-cli"]["features"]["advertisement"] == "wire_absent"
    assert rows["mcp-inspector"]["features"]["create_task"] == "wire_pass"
    assert rows["mcp-inspector"]["features"]["tasks_get"] == "wire_blocked"
    assert rows["rust-rmcp"]["features"]["tasks_get"] == "wire_pass"
    assert rows["csharp-sdk"]["verdict"] == "source_supported_unpaired"
    assert rows["ext-tasks-reference"]["verdict"] == "reference_only"


def test_reference_tasks_pair_and_strict_inspector_blocker_are_bounded(
    builder: Any,
) -> None:
    rmcp = _load(
        LAB_ROOT / "fixtures" / "rmcp-3.1.2-tasks-adapter-pair-20260808.json"
    )
    inspector = _load(
        LAB_ROOT
        / "fixtures"
        / "inspector-2.1.0-tasks-strict-pair-blocked-20260808.json"
    )
    builder.validate_payload(
        rmcp,
        LAB_ROOT / "schemas" / "rmcp-tasks-adapter-pair.schema.json",
    )
    builder.validate_payload(
        inspector,
        LAB_ROOT / "schemas" / "inspector-tasks-strict-pair.schema.json",
    )

    assert all(rmcp["wire"].values())
    assert rmcp["adapter"]["production_enabled"] is False
    assert rmcp["owner_result"]["owner_rerun_count"] == 0
    assert inspector["strict_pair"]["mcp_name_on_tasks_get"] is False
    assert inspector["adapter_response"] == {
        "error_code": -32020,
        "http_status": 400,
        "strict_boundary_retained": True,
    }


def test_effectful_first_pilot_is_schema_rejected(
    builder: Any,
    matrix: dict[str, Any],
) -> None:
    candidate = copy.deepcopy(matrix)
    candidate["pilot"]["effectful"] = True

    with pytest.raises(ValueError, match="False was expected"):
        builder.validate_payload(candidate, builder.MATRIX_SCHEMA_PATH)


def test_deployment_receipts_must_match_candidate_sdk_for_migration(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    candidate = copy.deepcopy(matrix)
    pair = copy.deepcopy(observation)
    deployment = _load(LAB_ROOT / "fixtures" / "live-modern-fleet-20260809.json")
    tasks_pair = _load(
        LAB_ROOT / "fixtures" / "codex-tasks-production-pair-20260809.json"
    )
    deployment["mcp_sdk"] = "2.1.1"
    tasks_pair["mcp_sdk"] = "2.1.1"

    admitted = builder.build_status(
        candidate,
        pair,
        live_modern_fleet=deployment,
        codex_tasks_production_pair=tasks_pair,
    )
    assert admitted["core_read_migration_allowed"] is True
    assert admitted["read_only_pilot_allowed"] is True
    assert admitted["internal_effect_migration_allowed"] is False

    pair["rollback"]["status"] = "failed"
    rejected = builder.build_status(
        candidate,
        pair,
        live_modern_fleet=deployment,
        codex_tasks_production_pair=tasks_pair,
    )
    assert rejected["core_read_migration_allowed"] is False
    assert rejected["read_only_pilot_allowed"] is False
