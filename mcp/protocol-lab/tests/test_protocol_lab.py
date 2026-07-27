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
    assert first["gate_counts"] == {"passed": 2, "blocked": 4, "pending": 8}
    assert first["passed_gate_ids"] == ["P1-06", "P1-12"]
    assert first["migration_allowed"] is False
    assert first["read_only_pilot_allowed"] is False
    assert first["tasks_extension_allowed"] is False
    assert first["effectful_migration_allowed"] is False
    assert first["stable_registration_retained"] is True


def test_final_label_alone_cannot_enable_migration(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    candidate = copy.deepcopy(matrix)
    candidate["next_spec"]["final_published"] = True
    candidate["next_spec"]["production_allowed"] = True
    candidate["next_spec"]["release_status"] = "final"

    status = builder.build_status(candidate, observation)

    assert status["migration_allowed"] is False
    assert status["read_only_pilot_allowed"] is False


def test_consumer_literals_are_not_wire_pair_evidence(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    assert matrix["consumer_pairs"][0]["next_protocol_literal_present"] is True

    status = builder.build_status(matrix, observation)

    assert matrix["consumer_pairs"][0]["capability_posture"] == "unknown"
    assert "codex_next_pair_unobserved" in status["reason_codes"]
    assert status["migration_allowed"] is False


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
