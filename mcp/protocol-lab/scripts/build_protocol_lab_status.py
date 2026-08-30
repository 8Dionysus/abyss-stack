#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
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
RUNTIME_CONFIG_PATH = LAB_ROOT.parent / "services" / "_shared" / "runtime-config.v1.json"
EXPECTED_CANDIDATE_MCP_ARTIFACT_DIGEST = "sha256:1ef71b1a3cfb3daba29b61d9f280896b35bdc1038474285cc8295071418b01e5"
EXPECTED_PRODUCTION_MCP_ARTIFACT_DIGEST = "sha256:a638c12e432fc0444d263a55db04668cd789437fde33951cc2be491021219601"
EXPECTED_CANDIDATE_MCP_ARTIFACT_DIGESTS = frozenset(
    {
        EXPECTED_CANDIDATE_MCP_ARTIFACT_DIGEST,
        EXPECTED_PRODUCTION_MCP_ARTIFACT_DIGEST,
    }
)
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


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp must be timezone-aware: {value}")
    return parsed.astimezone(UTC)


def _earliest_expiry(*payloads: dict[str, Any]) -> str:
    return min(payload["expires_at"] for payload in payloads)


def _evidence_is_current(payload: dict[str, Any], evaluated_at: str) -> bool:
    return _timestamp(payload["expires_at"]) > _timestamp(evaluated_at)


def _live_fleet_identity_attested(
    payload: dict[str, Any],
    *,
    expected_sdk: str,
    admitted_read_count: int,
) -> bool:
    """Require per-unit identity summary for the candidate fleet only."""

    if payload.get("mcp_sdk") != expected_sdk:
        return False
    read_fleet = payload.get("read_fleet")
    return bool(
        payload.get("mcp_sdk_artifact_digest")
        in EXPECTED_CANDIDATE_MCP_ARTIFACT_DIGESTS
        and isinstance(read_fleet, dict)
        and read_fleet.get("sdk_identity_attested") is True
        and read_fleet.get("sdk_identity_count") == admitted_read_count
        and read_fleet.get("sdk_identity_unique_count") == 1
        and read_fleet.get("runtime_identity_attested") is True
        and read_fleet.get("listener_attested") is True
    )


def _stable_rollback_identity_bound(
    payload: dict[str, Any],
    *,
    expected_sdk: str,
    expected_source_revision: str,
) -> bool:
    """Require candidate rollback evidence to name its contacted serving unit."""

    if payload.get("mcp_sdk") != expected_sdk:
        return False
    binding = payload.get("server_binding")
    if not isinstance(binding, dict):
        return False
    sdk_identity = binding.get("sdk_identity")
    return bool(
        binding.get("binding_method")
        == "configured_codex_endpoint_to_per_unit_fleet_identity"
        and binding.get("organ_id") == "aoa-kag"
        and binding.get("status_entry_observed") is True
        and binding.get("endpoint_matches") is True
        and binding.get("process_identity_matches_fleet") is True
        and binding.get("process_identity_stable") is True
        and binding.get("sdk_identity_matches_fleet") is True
        and binding.get("sdk_identity_stable") is True
        and binding.get("checked_before_and_after_tool_call") is True
        and isinstance(sdk_identity, dict)
        and sdk_identity.get("version") == expected_sdk
        and sdk_identity.get("commit") == expected_source_revision
        and sdk_identity.get("artifact_digest")
        in EXPECTED_CANDIDATE_MCP_ARTIFACT_DIGESTS
        and isinstance(binding.get("runtime_identity_attestation"), dict)
        and binding["runtime_identity_attestation"].get("state") == "passed"
        and binding["runtime_identity_attestation"].get("method")
        == "server_emitted_startup_runtime_identity_header"
        and binding["runtime_identity_attestation"].get("header")
        == "X-Abyss-MCP-Runtime-Identity"
        and binding["runtime_identity_attestation"].get("checked_during_discovery")
        is True
        and isinstance(binding.get("listener_attestation"), dict)
        and binding["listener_attestation"].get("state") == "passed"
        and binding["listener_attestation"].get("method")
        == "proc_net_tcp_listener_inode_owned_by_main_pid"
        and binding["listener_attestation"].get("pid")
        == binding["runtime_identity_attestation"].get("pid")
        and binding["listener_attestation"].get(
            "checked_before_and_after_probe"
        )
        is True
        and isinstance(binding.get("contacted_server_probe"), dict)
        and binding["contacted_server_probe"].get("state") == "passed"
        and binding["contacted_server_probe"].get("method")
        == "direct_modern_server_discover_with_runtime_identity_header"
        and binding["contacted_server_probe"].get("endpoint_ref")
        == binding.get("configured_endpoint_ref")
        and binding["contacted_server_probe"].get("http_status") == 200
        and isinstance(
            binding["contacted_server_probe"].get("runtime_identity_attestation"),
            dict,
        )
        and binding["contacted_server_probe"][
            "runtime_identity_attestation"
        ].get("state")
        == "passed"
        and binding["contacted_server_probe"][
            "runtime_identity_attestation"
        ].get("pid")
        == binding["runtime_identity_attestation"].get("pid")
    )


def _deployment_artifact_identity_current(
    live_modern_fleet: dict[str, Any],
    stable_rollback_observation: dict[str, Any],
    codex_tasks_production_pair: dict[str, Any],
    *,
    expected_sdk: str,
) -> bool:
    """Require one reviewed installation form across artifact-bearing receipts."""

    artifacts: list[str] = []
    for payload in (live_modern_fleet, codex_tasks_production_pair):
        if payload.get("mcp_sdk") != expected_sdk:
            return False
        artifact = payload.get("mcp_sdk_artifact_digest")
        if artifact not in EXPECTED_CANDIDATE_MCP_ARTIFACT_DIGESTS:
            return False
        artifacts.append(artifact)
    if stable_rollback_observation.get("mcp_sdk") != expected_sdk:
        return False
    binding = stable_rollback_observation.get("server_binding")
    sdk_identity = binding.get("sdk_identity") if isinstance(binding, dict) else None
    artifact = sdk_identity.get("artifact_digest") if isinstance(sdk_identity, dict) else None
    if artifact not in EXPECTED_CANDIDATE_MCP_ARTIFACT_DIGESTS:
        return False
    artifacts.append(artifact)
    return len(set(artifacts)) == 1


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
    *,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    evaluated_at = evaluated_at or datetime.now(UTC).isoformat().replace(
        "+00:00", "Z"
    )
    _timestamp(evaluated_at)
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
    runtime_config = load_json(RUNTIME_CONFIG_PATH)
    runtime_sdk = runtime_config["mcp"]["sdk"]
    admitted_read_count = len(runtime_config["deployment"]["client_read_contours"])
    tested_sdk_lock = str(runtime_sdk["tested_lock"])
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
    candidate_sdk_version = tested_sdk_lock
    candidate_sdk_identity = {
        "mcp_sdk": candidate_sdk_version,
        "mcp_sdk_source_revision": str(runtime_sdk["source_revision"]),
    }
    next_sdk_catalog_aligned = bool(
        next_sdk["version"] == candidate_sdk_identity["mcp_sdk"]
        and next_sdk["commit"]
        == candidate_sdk_identity["mcp_sdk_source_revision"]
        and next_sdk["stack_pin"] == candidate_sdk_identity["mcp_sdk"]
    )
    next_sdk_ready = any(
        sdk["release_status"] == "stable"
        and sdk["production_allowed"]
        and next_version in sdk["protocol_versions"]
        for sdk in matrix["sdk_lines"]
    ) and next_sdk_catalog_aligned
    production_consumer = _consumer(matrix, "codex-cli-os-abyss")
    lab_consumer = _consumer(matrix, "codex-cli-stable-modern-lab")
    candidate_evidence = (matrix, codex_lab_observation)
    candidate_evidence_expires_at = _earliest_expiry(*candidate_evidence)
    candidate_evidence_current = all(
        _evidence_is_current(payload, evaluated_at) for payload in candidate_evidence
    )
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
        and candidate_evidence_current
        and observation["official_conformance"]["status"] == "passed"
        and _passed(observation, "abyss_pair_conformance")
        and matrix["pilot"]["state"] == "passed"
    )
    deployment_evidence = (
        stable_rollback_observation,
        tasks_matrix,
        live_modern_fleet,
        codex_tasks_production_pair,
    )
    live_fleet_identity_current = _live_fleet_identity_attested(
        live_modern_fleet,
        expected_sdk=tested_sdk_lock,
        admitted_read_count=admitted_read_count,
    )
    stable_rollback_identity_current = _stable_rollback_identity_bound(
        stable_rollback_observation,
        expected_sdk=tested_sdk_lock,
        expected_source_revision=str(runtime_sdk["source_revision"]),
    )
    deployment_artifact_identity_current = _deployment_artifact_identity_current(
        live_modern_fleet,
        stable_rollback_observation,
        codex_tasks_production_pair,
        expected_sdk=tested_sdk_lock,
    )
    deployment_evidence_expires_at = _earliest_expiry(*deployment_evidence)
    deployment_evidence_current = (
        live_fleet_identity_current
        and stable_rollback_identity_current
        and deployment_artifact_identity_current
        and all(
            (
                payload.get("mcp_sdk") == candidate_sdk_identity["mcp_sdk"]
                and payload.get("mcp_sdk_source_revision")
                == candidate_sdk_identity["mcp_sdk_source_revision"]
                and _evidence_is_current(payload, evaluated_at)
                for payload in deployment_evidence
            )
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
            candidate_evidence_current,
            live_modern_fleet["verdict"] == "production_modern_only_passed",
            live_modern_fleet["read_fleet"]["production_units"] == admitted_read_count,
            live_modern_fleet["read_fleet"]["admitted_units"] == admitted_read_count,
            live_modern_fleet["read_fleet"]["bootstrap_identities"] == 0,
            live_modern_fleet["rollback"]["active_legacy_units"] == 0,
            live_modern_fleet["mcp_sdk"] == tested_sdk_lock,
            codex_tasks_production_pair["mcp_sdk"] == tested_sdk_lock,
            live_fleet_identity_current,
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
    if not candidate_evidence_current:
        production_cutover_blockers.append("candidate_evidence_expired")

    unsigned = {
        "schema_version": "abyss_mcp_protocol_lab_status_v2",
        "evaluated_at": evaluated_at,
        "candidate_evidence_expires_at": candidate_evidence_expires_at,
        "candidate_evidence_current": candidate_evidence_current,
        "deployment_evidence_expires_at": deployment_evidence_expires_at,
        "deployment_evidence_current": deployment_evidence_current,
        "evidence_expires_at": min(
            candidate_evidence_expires_at,
            deployment_evidence_expires_at,
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
            f"Perform a bounded MCP {tested_sdk_lock} core-read rollout; keep "
            "Tasks and non-read authority disabled until their separate evidence "
            "is current."
            if production_pair_ready
            else (
                f"Refresh the deployment-bound MCP {tested_sdk_lock} process, "
                "artifact, rollback, and Tasks receipts before "
                "any production cutover or non-read admission."
            )
        ),
        "claim_limits": matrix["claim_limits"],
    }
    result = {**unsigned, "status_digest": canonical_digest(unsigned)}
    validate_payload(result, STATUS_SCHEMA_PATH)
    return result


def render(*, evaluated_at: str | None = None) -> str:
    """Render the status with an explicit or current build-time evaluation."""

    evaluated_at = evaluated_at or datetime.now(UTC).isoformat().replace(
        "+00:00", "Z"
    )
    return json.dumps(
        build_status(
            load_json(MATRIX_PATH),
            load_json(OBSERVATION_PATH),
            evaluated_at=evaluated_at,
        ),
        indent=2,
        ensure_ascii=True,
        sort_keys=True,
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        if not OUTPUT_PATH.is_file():
            print(f"missing generated protocol lab status: {OUTPUT_PATH}")
            return 1
        try:
            recorded = load_json(OUTPUT_PATH)
            expected = render(evaluated_at=recorded["evaluated_at"])
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            print(f"invalid generated protocol lab status: {OUTPUT_PATH}")
            return 1
        if OUTPUT_PATH.read_text(encoding="utf-8") != expected:
            print(f"stale generated protocol lab status: {OUTPUT_PATH}")
            return 1
        return 0
    expected = render()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(expected, encoding="utf-8")
    print(f"[ok] wrote {OUTPUT_PATH.relative_to(LAB_ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
