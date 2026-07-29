from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


LAB_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = LAB_ROOT / "scripts" / "build_protocol_lab_status.py"


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


def test_current_status_is_deterministic_and_blocks_migration(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    first = builder.build_status(matrix, observation)
    second = builder.build_status(copy.deepcopy(matrix), copy.deepcopy(observation))

    assert first == second
    assert first["gate_counts"] == {"passed": 10, "blocked": 4, "pending": 0}
    assert first["passed_gate_ids"] == [
        "P1-01",
        "P1-02",
        "P1-04",
        "P1-05",
        "P1-06",
        "P1-07",
        "P1-08",
        "P1-09",
        "P1-10",
        "P1-12",
    ]
    assert first["migration_allowed"] is False
    assert first["read_only_pilot_allowed"] is False
    assert first["tasks_extension_allowed"] is False
    assert first["effectful_migration_allowed"] is False
    assert first["stable_registration_retained"] is True


def test_final_spec_and_stable_sdks_cannot_enable_migration(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    status = builder.build_status(copy.deepcopy(matrix), observation)

    assert status["migration_allowed"] is False
    assert status["read_only_pilot_allowed"] is False


def test_consumer_literals_are_not_wire_pair_evidence(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    assert matrix["consumer_pairs"][0]["next_protocol_literal_present"] is True

    status = builder.build_status(matrix, observation)

    assert matrix["consumer_pairs"][0]["capability_posture"] == "blocked"
    assert "codex_next_pair_blocked" in status["reason_codes"]
    assert status["migration_allowed"] is False


def test_codex_wire_receipt_proves_legacy_pair_only(builder: Any) -> None:
    wire_observation_path = (
        LAB_ROOT / "fixtures" / "codex-0.145.0-wire-observation.json"
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


def test_official_conformance_receipt_is_sdk_scoped(builder: Any) -> None:
    conformance_path = (
        LAB_ROOT / "fixtures" / "python-mcp-2.0.0-conformance-observation.json"
    )
    conformance_schema_path = (
        LAB_ROOT / "schemas" / "protocol-conformance-observation.schema.json"
    )
    conformance = _load(conformance_path)

    builder.validate_payload(conformance, conformance_schema_path)

    assert conformance["spec_version"] == "2026-07-28"
    assert conformance["directions"]["server"]["success_checks"] == 114
    assert conformance["directions"]["client"]["success_checks"] == 371
    assert conformance["directions"]["server"]["failed_checks"] == 0
    assert conformance["directions"]["client"]["failed_checks"] == 0
    assert "Codex" in " ".join(conformance["claim_limits"])


def test_kag_next_pair_is_adapter_scoped(builder: Any) -> None:
    pair_path = LAB_ROOT / "fixtures" / "kag-next-pair-observation.json"
    pair_schema_path = (
        LAB_ROOT / "schemas" / "kag-next-pair-observation.schema.json"
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
    assert pair["owner_canary"]["freshness_state"] == "source_unavailable"
    assert "Codex" in " ".join(pair["claim_limits"])


def test_kag_request_state_handles_are_read_scoped(builder: Any) -> None:
    handle_path = (
        LAB_ROOT / "fixtures" / "kag-handle-pair-observation.json"
    )
    handle_schema_path = (
        LAB_ROOT / "schemas" / "kag-handle-pair-observation.schema.json"
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
    cache_path = LAB_ROOT / "fixtures" / "kag-cache-pair-observation.json"
    cache_schema_path = (
        LAB_ROOT / "schemas" / "kag-cache-pair-observation.schema.json"
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


def test_effectful_first_pilot_is_schema_rejected(
    builder: Any,
    matrix: dict[str, Any],
) -> None:
    candidate = copy.deepcopy(matrix)
    candidate["pilot"]["effectful"] = True

    with pytest.raises(ValueError, match="False was expected"):
        builder.validate_payload(candidate, builder.MATRIX_SCHEMA_PATH)


def test_all_core_and_runtime_receipts_are_required_for_migration(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    candidate = copy.deepcopy(matrix)
    pair = copy.deepcopy(observation)
    candidate["next_spec"].update(
        {
            "final_published": True,
            "production_allowed": True,
            "release_status": "final",
        }
    )
    next_sdk = next(
        sdk for sdk in candidate["sdk_lines"] if sdk["sdk_id"] == "python-next"
    )
    next_sdk["release_status"] = "stable"
    next_sdk["production_allowed"] = True
    consumer = candidate["consumer_pairs"][0]
    consumer["capability_posture"] = "supported"
    consumer["next_wire_pair_observed"] = True
    consumer["server_discover_observed"] = True
    candidate["pilot"]["state"] = "passed"
    for gate in candidate["migration_gates"]:
        gate["status"] = "passed"

    pair.update(
        {
            "consumer_next_pair_observed": True,
            "explicit_handles_observed": True,
            "server_discover_observed": True,
            "spec_final_observed": True,
            "stable_sdk_release_observed": True,
            "stateless_behavior_observed": True,
            "trace_cache_metadata_observed": True,
            "verdict": "passed",
        }
    )
    for check_name in (
        "official_conformance",
        "abyss_pair_conformance",
        "read_only_canary",
        "dual_support",
        "rollback",
    ):
        pair[check_name]["status"] = "passed"
        pair[check_name]["receipt_refs"] = [f"receipts/{check_name}.json"]

    admitted = builder.build_status(candidate, pair)
    assert admitted["migration_allowed"] is True
    assert admitted["read_only_pilot_allowed"] is True
    assert admitted["effectful_migration_allowed"] is False

    pair["rollback"]["status"] = "failed"
    rejected = builder.build_status(candidate, pair)
    assert rejected["migration_allowed"] is False
    assert rejected["read_only_pilot_allowed"] is False
