#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


LAB_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = LAB_ROOT / "protocol-compatibility-matrix.v1.json"
OBSERVATION_PATH = LAB_ROOT / "fixtures" / "current-pair-observation.json"
OUTPUT_PATH = LAB_ROOT / "generated" / "protocol-lab-status.json"
PRODUCTION_OBSERVATION_PATH = LAB_ROOT / "fixtures" / "codex-0.146.0-production-pair-observation.json"
CODEX_LAB_OBSERVATION_PATH = LAB_ROOT / "fixtures" / "codex-0.147.0-stable-kag-next-lab-2.1.1-observation.json"
STABLE_ROLLBACK_OBSERVATION_PATH = LAB_ROOT / "fixtures" / "codex-0.147.0-stable-kag-post-rollback-observation.json"
TASKS_MATRIX_PATH = LAB_ROOT / "tasks-compatibility-matrix.v1.json"
TASKS_PILOT_PATH = LAB_ROOT / "fixtures" / "tasks-adapter-pilot-20260808.json"
RMCP_TASKS_PAIR_PATH = LAB_ROOT / "fixtures" / "rmcp-3.1.2-tasks-adapter-pair-20260808.json"
INSPECTOR_TASKS_BLOCKER_PATH = LAB_ROOT / "fixtures" / "inspector-2.1.0-tasks-strict-pair-blocked-20260808.json"
LIVE_MODERN_FLEET_PATH = LAB_ROOT / "fixtures" / "live-modern-fleet-20260809.json"
CODEX_TASKS_PRODUCTION_PAIR_PATH = LAB_ROOT / "fixtures" / "codex-tasks-production-pair-20260809.json"
MATRIX_SCHEMA_PATH = LAB_ROOT / "schemas" / "protocol-compatibility-matrix.schema.json"
OBSERVATION_SCHEMA_PATH = LAB_ROOT / "schemas" / "protocol-pair-observation.schema.json"
STATUS_SCHEMA_PATH = LAB_ROOT / "schemas" / "protocol-lab-status.schema.json"
PRODUCTION_OBSERVATION_SCHEMA_PATH = LAB_ROOT / "schemas" / "protocol-production-pair-observation.schema.json"
CODEX_LAB_OBSERVATION_SCHEMA_PATH = LAB_ROOT / "schemas" / "codex-kag-next-stable-observation.schema.json"
STABLE_ROLLBACK_OBSERVATION_SCHEMA_PATH = LAB_ROOT / "schemas" / "stable-kag-post-rollback-current-observation.schema.json"
TASKS_MATRIX_SCHEMA_PATH = LAB_ROOT / "schemas" / "tasks-compatibility-matrix.schema.json"
TASKS_PILOT_SCHEMA_PATH = LAB_ROOT / "schemas" / "tasks-adapter-pilot.schema.json"
RMCP_TASKS_PAIR_SCHEMA_PATH = LAB_ROOT / "schemas" / "rmcp-tasks-adapter-pair.schema.json"
INSPECTOR_TASKS_BLOCKER_SCHEMA_PATH = LAB_ROOT / "schemas" / "inspector-tasks-strict-pair.schema.json"
LIVE_MODERN_FLEET_SCHEMA_PATH = LAB_ROOT / "schemas" / "live-modern-fleet-observation.schema.json"
CODEX_TASKS_PRODUCTION_PAIR_SCHEMA_PATH = LAB_ROOT / "schemas" / "codex-tasks-production-pair.schema.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def validate_payload(payload: dict[str, Any], schema_path: Path) -> None:
    validator = Draft202012Validator(
        load_json(schema_path),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        rendered = "; ".join(
            f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
            for error in errors
        )
        raise ValueError(f"{schema_path.name}: {rendered}")


def _consumer(matrix: dict[str, Any], consumer_id: str) -> dict[str, Any]:
    matches = [
        item for item in matrix["consumer_pairs"] if item["consumer_id"] == consumer_id
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one consumer pair named {consumer_id}")
    return matches[0]


def _passed(observation: dict[str, Any], name: str) -> bool:
    return observation[name]["status"] == "passed"


def build_status(
    matrix: dict[str, Any],
    observation: dict[str, Any],
    production_observation: dict[str, Any] | None = None,
    codex_lab_observation: dict[str, Any] | None = None,
    stable_rollback_observation: dict[str, Any] | None = None,
    tasks_matrix: dict[str, Any] | None = None,
    tasks_pilot: dict[str, Any] | None = None,
    rmcp_tasks_pair: dict[str, Any] | None = None,
    inspector_tasks_blocker: dict[str, Any] | None = None,
    live_modern_fleet: dict[str, Any] | None = None,
    codex_tasks_production_pair: dict[str, Any] | None = None,
) -> dict[str, Any]:
    production_observation = production_observation or load_json(PRODUCTION_OBSERVATION_PATH)
    codex_lab_observation = codex_lab_observation or load_json(CODEX_LAB_OBSERVATION_PATH)
    stable_rollback_observation = stable_rollback_observation or load_json(STABLE_ROLLBACK_OBSERVATION_PATH)
    tasks_matrix = tasks_matrix or load_json(TASKS_MATRIX_PATH)
    tasks_pilot = tasks_pilot or load_json(TASKS_PILOT_PATH)
    rmcp_tasks_pair = rmcp_tasks_pair or load_json(RMCP_TASKS_PAIR_PATH)
    inspector_tasks_blocker = inspector_tasks_blocker or load_json(
        INSPECTOR_TASKS_BLOCKER_PATH
    )
    live_modern_fleet = live_modern_fleet or load_json(LIVE_MODERN_FLEET_PATH)
    codex_tasks_production_pair = codex_tasks_production_pair or load_json(
        CODEX_TASKS_PRODUCTION_PAIR_PATH
    )
    for payload, schema in (
        (matrix, MATRIX_SCHEMA_PATH),
        (observation, OBSERVATION_SCHEMA_PATH),
        (production_observation, PRODUCTION_OBSERVATION_SCHEMA_PATH),
        (codex_lab_observation, CODEX_LAB_OBSERVATION_SCHEMA_PATH),
        (stable_rollback_observation, STABLE_ROLLBACK_OBSERVATION_SCHEMA_PATH),
        (tasks_matrix, TASKS_MATRIX_SCHEMA_PATH),
        (tasks_pilot, TASKS_PILOT_SCHEMA_PATH),
        (rmcp_tasks_pair, RMCP_TASKS_PAIR_SCHEMA_PATH),
        (inspector_tasks_blocker, INSPECTOR_TASKS_BLOCKER_SCHEMA_PATH),
        (live_modern_fleet, LIVE_MODERN_FLEET_SCHEMA_PATH),
        (codex_tasks_production_pair, CODEX_TASKS_PRODUCTION_PAIR_SCHEMA_PATH),
    ):
        validate_payload(payload, schema)
    if observation["matrix_version"] != matrix["schema_version"]:
        raise ValueError("pair observation references a different matrix version")

    gates = matrix["migration_gates"]
    gate_counts = Counter(gate["status"] for gate in gates)
    passed_gate_ids = [gate["gate_id"] for gate in gates if gate["status"] == "passed"]
    remaining_gate_ids = [gate["gate_id"] for gate in gates if gate["status"] != "passed"]
    remaining_core_gate_ids = [gate_id for gate_id in remaining_gate_ids if gate_id != "P1-11"]
    remaining_tasks_gate_ids = [gate_id for gate_id in remaining_gate_ids if gate_id == "P1-11"]

    next_version = matrix["next_spec"]["wire_version"]
    next_sdk = next(
        sdk for sdk in matrix["sdk_lines"] if sdk["sdk_id"] == "python-next"
    )
    candidate_sdk_version = next_sdk["version"]
    next_sdk_ready = any(
        sdk["release_status"] == "stable"
        and sdk["production_allowed"]
        and next_version in sdk["protocol_versions"]
        for sdk in matrix["sdk_lines"]
    )
    production_consumer = _consumer(matrix, "codex-cli-os-abyss")
    lab_consumer = _consumer(matrix, "codex-cli-stable-modern-lab")
    lab_canary_completed = all(
        (
            matrix["next_spec"]["final_published"],
            next_sdk_ready,
            lab_consumer["next_wire_pair_observed"],
            lab_consumer["server_discover_observed"],
            codex_lab_observation["verdict"] == "isolated_stable_pair_passed",
            codex_lab_observation["wire"]["version"] == next_version,
            not codex_lab_observation["consumer"]["production_authority"],
            _passed(observation, "read_only_canary"),
            _passed(observation, "compatibility_aliases"),
            _passed(observation, "dual_support"),
            _passed(observation, "rollback"),
            not matrix["pilot"]["effectful"],
        )
    )
    lab_pair_ready = bool(
        lab_canary_completed
        and observation["official_conformance"]["status"] == "passed"
        and _passed(observation, "abyss_pair_conformance")
        and matrix["pilot"]["state"] == "passed"
    )
    deployment_evidence_current = all(
        (
            live_modern_fleet["mcp_sdk"] == candidate_sdk_version,
            codex_tasks_production_pair["mcp_sdk"] == candidate_sdk_version,
        )
    )
    production_pair_ready = all(
        (
            production_consumer["next_wire_pair_observed"],
            production_consumer["server_discover_observed"],
            observation["official_conformance"]["status"] == "passed",
            _passed(observation, "abyss_pair_conformance"),
            _passed(observation, "read_only_canary"),
            _passed(observation, "compatibility_aliases"),
            _passed(observation, "dual_support"),
            _passed(observation, "rollback"),
            matrix["pilot"]["state"] == "passed",
            not remaining_core_gate_ids,
            live_modern_fleet["verdict"] == "production_modern_only_passed",
            live_modern_fleet["read_fleet"]["production_units"] == 11,
            live_modern_fleet["read_fleet"]["admitted_units"] == 11,
            live_modern_fleet["read_fleet"]["bootstrap_identities"] == 0,
            live_modern_fleet["rollback"]["active_legacy_units"] == 0,
            deployment_evidence_current,
        )
    )
    tasks_extension_allowed = bool(
        production_pair_ready
        and codex_tasks_production_pair["verdict"]
        == "eligible_for_bounded_production"
        and not remaining_tasks_gate_ids
    )
    production_cutover_blockers: list[str] = []
    if not production_consumer["next_wire_pair_observed"]:
        production_cutover_blockers.append("production_modern_pair_not_admitted")
    if observation["official_conformance"]["status"] != "passed":
        production_cutover_blockers.append("current_conformance_fixture_mismatch")
    if observation["abyss_pair_conformance"]["status"] != "passed":
        production_cutover_blockers.append("modern_cancellation_not_propagated")
    if not deployment_evidence_current:
        production_cutover_blockers.append(
            "deployment_bound_evidence_not_refreshed_for_mcp_2_1_1"
        )

    unsigned = {
        "schema_version": "abyss_mcp_protocol_lab_status_v2",
        "evaluated_at": observation["observed_at"],
        "evidence_expires_at": min(
            matrix["expires_at"],
            codex_lab_observation["expires_at"],
        ),
        "matrix_digest": canonical_digest(matrix),
        "observation_digest": canonical_digest(observation),
        "codex_lab_observation_digest": canonical_digest(codex_lab_observation),
        "stable_rollback_observation_digest": canonical_digest(stable_rollback_observation),
        "tasks_matrix_digest": canonical_digest(tasks_matrix),
        "tasks_pilot_digest": canonical_digest(tasks_pilot),
        "rmcp_tasks_pair_digest": canonical_digest(rmcp_tasks_pair),
        "inspector_tasks_blocker_digest": canonical_digest(inspector_tasks_blocker),
        "live_modern_fleet_digest": canonical_digest(live_modern_fleet),
        "codex_tasks_production_pair_digest": canonical_digest(
            codex_tasks_production_pair
        ),
        "tasks_evidence_expires_at": tasks_matrix["expires_at"],
        "production_protocol": matrix["production_protocol"],
        "next_protocol": next_version,
        "next_release_status": matrix["next_spec"]["release_status"],
        "read_only_pilot_allowed": lab_pair_ready,
        "read_only_pilot_completed": lab_canary_completed,
        "core_read_migration_allowed": production_pair_ready,
        "tasks_extension_allowed": tasks_extension_allowed,
        "tasks_extension_maturity": tasks_matrix["extension_maturity"],
        "tasks_reference_consumer": (
            f"{tasks_matrix['reference_pair']['consumer_id']}-"
            f"{tasks_matrix['reference_pair']['version']}"
        ),
        "tasks_reference_pair_passed": (
            rmcp_tasks_pair["verdict"]
            == "released_rmcp_passed_feature_gated_abyss_adapter"
        ),
        "tasks_inspector_strict_pair_blocked": (
            inspector_tasks_blocker["verdict"]
            == "blocked_missing_mcp_name_on_raw_tasks_get"
        ),
        "tasks_codex_consumer_eligible": tasks_extension_allowed,
        "tasks_production_enabled": tasks_matrix["production_tasks_allowed"],
        "tasks_notifications_proven": tasks_pilot["notifications"]["tested"],
        "tasks_blockers": [
            "input_required_update_live_pair_unproved",
            "tasks_notifications_unproved",
            "distributed_poll_limit_unproved",
        ],
        "candidate_protocol_ready": bool(
            matrix["next_spec"]["final_published"]
            and next_sdk_ready
            and lab_consumer["next_wire_pair_observed"]
            and lab_consumer["server_discover_observed"]
            and codex_lab_observation["wire"]["server_discover_observed"]
            and codex_lab_observation["wire"]["version"] == next_version
            and not codex_lab_observation["consumer"]["production_authority"]
        ),
        "internal_effect_protocol_ready": False,
        "candidate_migration_allowed": False,
        "internal_effect_migration_allowed": False,
        "external_effect_migration_allowed": False,
        "stable_registration_retained": matrix["dual_support"]["stable_registration_retained"],
        "authority_move_combined": observation["authority_move_combined"],
        "gate_counts": {
            "passed": gate_counts["passed"],
            "blocked": gate_counts["blocked"],
            "pending": gate_counts["pending"],
        },
        "passed_gate_ids": passed_gate_ids,
        "remaining_gate_ids": remaining_gate_ids,
        "remaining_core_gate_ids": remaining_core_gate_ids,
        "remaining_tasks_gate_ids": remaining_tasks_gate_ids,
        "production_cutover_blockers": production_cutover_blockers,
        "reason_codes": observation["reason_codes"],
        "next_action": (
            "Keep production on its evidenced MCP 2.0.0 deployment; refresh the "
            "deployment-bound 2.1.1 pair, rollback, and Tasks receipts before any "
            "production cutover or non-read admission."
        ),
        "claim_limits": matrix["claim_limits"],
    }
    result = {**unsigned, "status_digest": canonical_digest(unsigned)}
    validate_payload(result, STATUS_SCHEMA_PATH)
    return result


def render() -> str:
    return json.dumps(
        build_status(load_json(MATRIX_PATH), load_json(OBSERVATION_PATH)),
        indent=2,
        ensure_ascii=True,
        sort_keys=True,
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT_PATH.is_file():
            print(f"missing generated protocol lab status: {OUTPUT_PATH}")
            return 1
        if OUTPUT_PATH.read_text(encoding="utf-8") != expected:
            print(f"stale generated protocol lab status: {OUTPUT_PATH}")
            return 1
        return 0
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(expected, encoding="utf-8")
    print(f"[ok] wrote {OUTPUT_PATH.relative_to(LAB_ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
