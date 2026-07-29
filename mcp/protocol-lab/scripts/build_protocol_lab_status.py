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
MATRIX_SCHEMA_PATH = (
    LAB_ROOT / "schemas" / "protocol-compatibility-matrix.schema.json"
)
OBSERVATION_SCHEMA_PATH = (
    LAB_ROOT / "schemas" / "protocol-pair-observation.schema.json"
)
STATUS_SCHEMA_PATH = LAB_ROOT / "schemas" / "protocol-lab-status.schema.json"


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


def build_status(
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> dict[str, Any]:
    validate_payload(matrix, MATRIX_SCHEMA_PATH)
    validate_payload(observation, OBSERVATION_SCHEMA_PATH)
    if observation["matrix_version"] != matrix["schema_version"]:
        raise ValueError("pair observation references a different matrix version")

    gates = matrix["migration_gates"]
    gate_counts = Counter(gate["status"] for gate in gates)
    passed_gate_ids = [
        gate["gate_id"] for gate in gates if gate["status"] == "passed"
    ]
    remaining_gate_ids = [
        gate["gate_id"] for gate in gates if gate["status"] != "passed"
    ]
    next_sdk_ready = any(
        sdk["release_status"] == "stable"
        and sdk["production_allowed"]
        and matrix["next_spec"]["wire_version"] in sdk["protocol_versions"]
        for sdk in matrix["sdk_lines"]
    )
    consumer = matrix["consumer_pairs"][0]
    core_pair_ready = all(
        (
            matrix["next_spec"]["final_published"],
            matrix["next_spec"]["production_allowed"],
            next_sdk_ready,
            consumer["next_wire_pair_observed"],
            consumer["server_discover_observed"],
            observation["spec_final_observed"],
            observation["stable_sdk_release_observed"],
            observation["consumer_next_pair_observed"],
            observation["server_discover_observed"],
            observation["stateless_behavior_observed"],
            observation["explicit_handles_observed"],
            observation["trace_cache_metadata_observed"],
            observation["official_conformance"]["status"] == "passed",
            observation["abyss_pair_conformance"]["status"] == "passed",
            observation["compatibility_aliases"]["status"] == "passed",
            observation["dual_support"]["status"] == "passed",
            observation["rollback"]["status"] == "passed",
        )
    )
    read_only_pilot_allowed = (
        core_pair_ready
        and observation["read_only_canary"]["status"] in {"not_run", "passed"}
        and matrix["pilot"]["state"] in {"ready", "running", "passed"}
        and not matrix["pilot"]["effectful"]
    )
    migration_allowed = (
        core_pair_ready
        and observation["read_only_canary"]["status"] == "passed"
        and matrix["pilot"]["state"] == "passed"
        and not remaining_gate_ids
    )
    tasks_extension_allowed = (
        core_pair_ready and observation["tasks_extension"]["status"] == "passed"
    )
    unsigned = {
        "schema_version": "abyss_mcp_protocol_lab_status_v1",
        "evaluated_at": observation["observed_at"],
        "matrix_digest": canonical_digest(matrix),
        "observation_digest": canonical_digest(observation),
        "production_protocol": matrix["production_protocol"],
        "next_protocol": matrix["next_spec"]["wire_version"],
        "next_release_status": matrix["next_spec"]["release_status"],
        "migration_allowed": migration_allowed,
        "read_only_pilot_allowed": read_only_pilot_allowed,
        "tasks_extension_allowed": tasks_extension_allowed,
        "effectful_migration_allowed": False,
        "stable_registration_retained": matrix["dual_support"][
            "stable_registration_retained"
        ],
        "authority_move_combined": observation["authority_move_combined"],
        "gate_counts": {
            "passed": gate_counts["passed"],
            "blocked": gate_counts["blocked"],
            "pending": gate_counts["pending"],
        },
        "passed_gate_ids": passed_gate_ids,
        "remaining_gate_ids": remaining_gate_ids,
        "reason_codes": observation["reason_codes"],
        "next_action": (
            "Keep the next registration disabled; refresh Codex and repeat "
            "the isolated wire probe when consumer support changes."
            if not consumer["next_wire_pair_observed"]
            else (
                "Complete exact-pair conformance, Abyss behavior, canary, and "
                "rollback receipts before migration."
                if not migration_allowed
                else "Keep stable support while the read-only pilot advances."
            )
        ),
        "claim_limits": matrix["claim_limits"],
    }
    result = {
        **unsigned,
        "status_digest": canonical_digest(unsigned),
    }
    validate_payload(result, STATUS_SCHEMA_PATH)
    return result


def render() -> str:
    return (
        json.dumps(
            build_status(
                load_json(MATRIX_PATH),
                load_json(OBSERVATION_PATH),
            ),
            indent=2,
            ensure_ascii=True,
            sort_keys=True,
        )
        + "\n"
    )


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
