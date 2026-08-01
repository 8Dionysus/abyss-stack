#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parents[1]
BUILDER_PATH = LAB_ROOT / "scripts" / "build_protocol_lab_status.py"
WIRE_OBSERVATION_PATH = (
    LAB_ROOT / "fixtures" / "codex-0.146.0-wire-observation.json"
)
WIRE_OBSERVATION_SCHEMA_PATH = (
    LAB_ROOT / "schemas" / "protocol-consumer-wire-observation.schema.json"
)
PRODUCTION_OBSERVATION_PATH = (
    LAB_ROOT / "fixtures" / "codex-0.146.0-production-pair-observation.json"
)
PRODUCTION_OBSERVATION_SCHEMA_PATH = (
    LAB_ROOT / "schemas" / "protocol-production-pair-observation.schema.json"
)
CONFORMANCE_OBSERVATION_PATH = (
    LAB_ROOT / "fixtures" / "python-mcp-2.0.0-conformance-observation.json"
)
CONFORMANCE_OBSERVATION_SCHEMA_PATH = (
    LAB_ROOT / "schemas" / "protocol-conformance-observation.schema.json"
)
KAG_PAIR_OBSERVATION_PATH = (
    LAB_ROOT / "fixtures" / "kag-next-pair-observation.json"
)
KAG_PAIR_OBSERVATION_SCHEMA_PATH = (
    LAB_ROOT / "schemas" / "kag-next-pair-observation.schema.json"
)
KAG_HANDLE_OBSERVATION_PATH = (
    LAB_ROOT / "fixtures" / "kag-handle-pair-observation.json"
)
KAG_HANDLE_OBSERVATION_SCHEMA_PATH = (
    LAB_ROOT / "schemas" / "kag-handle-pair-observation.schema.json"
)
KAG_CACHE_OBSERVATION_PATH = (
    LAB_ROOT / "fixtures" / "kag-cache-pair-observation.json"
)
KAG_CACHE_OBSERVATION_SCHEMA_PATH = (
    LAB_ROOT / "schemas" / "kag-cache-pair-observation.schema.json"
)
EXPECTED_GATE_IDS = tuple(f"P1-{index:02d}" for index in range(1, 15))


def _load_builder() -> Any:
    spec = importlib.util.spec_from_file_location("protocol_lab_builder", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load protocol lab builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> list[str]:
    errors: list[str] = []
    builder = _load_builder()
    matrix = _load(builder.MATRIX_PATH)
    observation = _load(builder.OBSERVATION_PATH)
    wire_observation = _load(WIRE_OBSERVATION_PATH)
    production_observation = _load(PRODUCTION_OBSERVATION_PATH)
    conformance_observation = _load(CONFORMANCE_OBSERVATION_PATH)
    kag_pair_observation = _load(KAG_PAIR_OBSERVATION_PATH)
    kag_handle_observation = _load(KAG_HANDLE_OBSERVATION_PATH)
    kag_cache_observation = _load(KAG_CACHE_OBSERVATION_PATH)
    try:
        builder.validate_payload(
            wire_observation,
            WIRE_OBSERVATION_SCHEMA_PATH,
        )
        builder.validate_payload(
            production_observation,
            PRODUCTION_OBSERVATION_SCHEMA_PATH,
        )
        builder.validate_payload(
            conformance_observation,
            CONFORMANCE_OBSERVATION_SCHEMA_PATH,
        )
        builder.validate_payload(
            kag_pair_observation,
            KAG_PAIR_OBSERVATION_SCHEMA_PATH,
        )
        builder.validate_payload(
            kag_handle_observation,
            KAG_HANDLE_OBSERVATION_SCHEMA_PATH,
        )
        builder.validate_payload(
            kag_cache_observation,
            KAG_CACHE_OBSERVATION_SCHEMA_PATH,
        )
        status = builder.build_status(matrix, observation)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]

    expected_render = json.dumps(
        status,
        indent=2,
        ensure_ascii=True,
        sort_keys=True,
    ) + "\n"
    if (
        not builder.OUTPUT_PATH.is_file()
        or builder.OUTPUT_PATH.read_text(encoding="utf-8") != expected_render
    ):
        errors.append("generated protocol-lab status is missing or stale")

    gate_ids = tuple(gate["gate_id"] for gate in matrix["migration_gates"])
    if gate_ids != EXPECTED_GATE_IDS:
        errors.append("P1 gates must be exactly ordered P1-01 through P1-14")
    next_spec = matrix["next_spec"]
    if next_spec != {
        "commit": "5f5440bb26a62e2cf3440b92da5a667efa03b267",
        "final_published": True,
        "production_allowed": True,
        "release_label": "2026-07-28",
        "release_status": "final",
        "source": (
            "https://github.com/modelcontextprotocol/modelcontextprotocol/"
            "releases/tag/2026-07-28"
        ),
        "tag": "2026-07-28",
        "wire_version": "2026-07-28",
    }:
        errors.append("final 2026-07-28 specification pin drifted")
    if matrix["stable_spec"] != {
        "commit": "38c84e9f93ad191d9eb26d92b945d17bd0efcaf3",
        "final_published": True,
        "production_allowed": True,
        "release_label": "2025-11-25",
        "release_status": "final",
        "source": (
            "https://github.com/modelcontextprotocol/modelcontextprotocol/"
            "releases/tag/2025-11-25"
        ),
        "tag": "2025-11-25",
        "wire_version": "2025-11-25",
    } or matrix["production_protocol"] != "2025-11-25":
        errors.append("production 2025-11-25 specification pin drifted")
    if status["migration_allowed"] or status["read_only_pilot_allowed"]:
        errors.append("observed legacy Codex pair must block next-protocol migration")
    if status["effectful_migration_allowed"]:
        errors.append("P1 must never migrate effectful organs in the first pilot")
    if not status["stable_registration_retained"]:
        errors.append("dual support must retain the stable registration")
    if status["authority_move_combined"]:
        errors.append("protocol migration cannot combine an authority move")

    pilot = matrix["pilot"]
    if (
        pilot["policy_family"] != "read"
        or pilot["effectful"]
        or pilot["stable_registration"] == pilot["next_lab_registration"]
        or pilot["next_lab_registration_enabled"]
    ):
        errors.append("pilot must remain read-only, separate, and disabled")

    sdk_by_id = {sdk["sdk_id"]: sdk for sdk in matrix["sdk_lines"]}
    python_next = sdk_by_id["python-next"]
    if (
        python_next["version"] != "2.0.0"
        or python_next["commit"]
        != "6f69a3758ebf2ee55ce050f58b470ce11af71133"
        or python_next["release_status"] != "stable"
        or not python_next["production_allowed"]
        or next_spec["wire_version"] not in python_next["protocol_versions"]
    ):
        errors.append("Python MCP 2.0.0 next-protocol pin drifted")
    typescript_next = sdk_by_id["typescript-next"]
    if (
        typescript_next["version"] != "2.0.0"
        or typescript_next["commit"]
        != "cc4b41617ce3601b1290d67216ea0b194a3cd9ac"
        or typescript_next["release_status"] != "stable"
        or not typescript_next["production_allowed"]
        or next_spec["wire_version"] not in typescript_next["protocol_versions"]
    ):
        errors.append("TypeScript MCP 2.0.0 next-protocol pin drifted")
    python_stable = next(
        sdk for sdk in matrix["sdk_lines"] if sdk["sdk_id"] == "python-stable"
    )
    if (
        python_stable["version"] != "1.29.0"
        or python_stable["commit"]
        != "98b7159cb89274964055d2c016e3360a551280d0"
        or python_stable["stack_pin"] != "1.27.2"
        or python_stable["stack_pin_status"] != "compatible_maintenance_drift"
    ):
        errors.append("Python stable and exact stack-pin drift are not recorded")

    service_pyprojects = sorted(
        (REPO_ROOT / "mcp" / "services").glob("*/pyproject.toml")
    )
    mcp_constraints: list[str] = []
    for path in service_pyprojects:
        text = path.read_text(encoding="utf-8")
        match = re.search(r'"mcp>=([^"]+)"', text)
        if match is not None:
            mcp_constraints.append(match.group(1))
    if not mcp_constraints or any(value != "1.27.2,<2" for value in mcp_constraints):
        errors.append("all stack MCP service constraints must retain mcp>=1.27.2,<2")
    lock = (
        REPO_ROOT
        / "mcp"
        / "services"
        / "abyss-stack-mcp"
        / "requirements.lock"
    ).read_text(encoding="utf-8")
    if "mcp==1.27.2 \\" not in lock:
        errors.append("abyss-stack-mcp lock must retain exact mcp 1.27.2")

    consumer = matrix["consumer_pairs"][0]
    if (
        consumer["next_wire_pair_observed"]
        or consumer["server_discover_observed"]
        or consumer["tasks_wire_pair_observed"]
        or consumer["capability_posture"] != "blocked"
    ):
        errors.append("Codex next-era capability must reflect the observed legacy pair")
    if not consumer["stable_pair_observed"]:
        errors.append("Codex legacy pair observation must remain recorded")
    if consumer["production_protocol_versions_observed"] != ["2025-11-25"]:
        errors.append("Codex production pair must record exact 2025-11-25 support")
    if consumer["isolated_next_sdk_fallback_protocol"] != "2025-06-18":
        errors.append("Codex next-SDK fallback wire must remain independently recorded")
    if not consumer["next_protocol_literal_present"]:
        errors.append("matrix must retain the observed Codex next-version literal")
    if (
        production_observation["consumer"]["version"] != consumer["version"]
        or production_observation["registration"]["wire_protocol_versions"]
        != consumer["production_protocol_versions_observed"]
        or production_observation["registration"]["schema_digest"]
        != "sha256:f873485d8aa3a0b8871e64e24a0da7a1b0ea2ca4af1e7f9fc09d0fb3f457f844"
        or production_observation["call"]["is_error"]
        or production_observation["secrets_included"]
        or production_observation["verdict"] != "production_pair_observed"
        or production_observation["private_source_receipt"]["digest"]
        != "sha256:f69ddc72c69184cfb8413f6f237518e7d336c9eecbce7344000de739761482ca"
    ):
        errors.append("public-safe Codex production-pair derivative drifted")

    if (
        wire_observation["consumer"]["version"] != consumer["version"]
        or wire_observation["wire_protocol_offered"]
        != consumer["isolated_next_sdk_fallback_protocol"]
        or wire_observation["wire_protocol_selected"]
        != consumer["isolated_next_sdk_fallback_protocol"]
        or wire_observation["method_sequence"][0] != "initialize"
        or wire_observation["server_discover_observed"]
        or wire_observation["next_wire_pair_observed"]
        or wire_observation["verdict"] != "legacy_pair_observed"
        or not wire_observation["isolated_codex_home"]
        or wire_observation["global_codex_config_mutated"]
    ):
        errors.append("Codex wire observation no longer proves the isolated legacy pair")
    if (
        wire_observation["raw_transcript"]["sha256"]
        != "376a2030eada931b9bfa26dd61443b8dc1da985a17ae85d8facf5d1f8f3499dc"
        or wire_observation["probe"]["mcp_python_wheel_sha256"]
        != "1cb4c75d2d2c7b8c1d756355e5d82a39f2822cc7f13e22a2051d7ca3592349d6"
    ):
        errors.append("wire probe content pins drifted")

    if observation["verdict"] != "blocked" or not observation["reason_codes"]:
        errors.append("current post-final pair observation must be explicitly blocked")
    if observation["receipt_refs"] == []:
        errors.append("current observation must cite final and wire evidence")
    if (
        not observation["spec_final_observed"]
        or not observation["stable_sdk_release_observed"]
        or observation["consumer_next_pair_observed"]
        or not observation["server_discover_observed"]
        or not observation["stateless_behavior_observed"]
    ):
        errors.append(
            "pair observation must distinguish adapter evidence from Codex wire readiness"
        )
    conformance = matrix["official_conformance"]
    if (
        conformance["version"] != "0.2.0-alpha.10"
        or conformance["commit"]
        != "a9896553900a2ef61787b57adfcbbe936a8ab1f9"
        or not conformance["next_suite_executed"]
        or conformance["receipt_refs"]
        != [
            "mcp/protocol-lab/fixtures/"
            "python-mcp-2.0.0-conformance-observation.json"
        ]
        or conformance["latest_public_release"]
        != {
            "commit": "21a9a2febd7100d7c17ac1021ee7f2ed9f66a1e0",
            "next_protocol_scenarios_observed": False,
            "published_at": "2026-03-27T18:47:47Z",
            "version": "v0.1.16",
        }
    ):
        errors.append("official conformance exact SDK-pair posture drifted")
    if (
        conformance_observation["spec_version"] != next_spec["wire_version"]
        or conformance_observation["verdict"] != "sdk_pair_passed"
        or conformance_observation["directions"]["server"]["scenario_count"] != 40
        or conformance_observation["directions"]["server"]["success_checks"] != 114
        or conformance_observation["directions"]["client"]["scenario_count"] != 32
        or conformance_observation["directions"]["client"]["success_checks"] != 371
        or conformance_observation["directions"]["server"]["failed_checks"]
        or conformance_observation["directions"]["client"]["failed_checks"]
        or conformance_observation["directions"]["server"][
            "expected_failure_baseline_entries"
        ]
        or conformance_observation["directions"]["client"][
            "expected_failure_baseline_entries"
        ]
    ):
        errors.append("official conformance receipt counts or scope drifted")
    if observation["official_conformance"] != {
        "reason": (
            "The exact Python MCP 2.0.0 client and server fixtures passed 371 "
            "and 114 official checks respectively at wire 2026-07-28; this is "
            "SDK-level proof, not Codex proof."
        ),
        "receipt_refs": [
            "mcp/protocol-lab/fixtures/"
            "python-mcp-2.0.0-conformance-observation.json"
        ],
        "status": "passed",
    }:
        errors.append("pair observation lost the bounded SDK conformance result")
    if (
        kag_pair_observation["python_sdk"]["commit"]
        != python_next["commit"]
        or kag_pair_observation["pair"]["wire_version"]
        != next_spec["wire_version"]
        or not kag_pair_observation["pair"]["server_discover_observed"]
        or kag_pair_observation["pair"]["session_header_observed"]
        or kag_pair_observation["pair"][
            "server_request_backchannel_observed"
        ]
        or kag_pair_observation["pair"]["trace_sent"]
        != kag_pair_observation["pair"]["trace_observed"]
        or kag_pair_observation["pair"]["cache"]
        != {
            "repeat_tools_list_wire_fetches": 1,
            "scope": "private",
            "ttl_ms": 30000,
        }
        or not kag_pair_observation["stable_registration"]["unchanged"]
        or kag_pair_observation["owner_canary"]["projection_exact_state"]
        != "current"
        or kag_pair_observation["owner_canary"]["freshness_state"]
        != "source_unavailable"
        or kag_pair_observation["verdict"] != "adapter_pair_passed"
    ):
        errors.append("isolated KAG next-pair receipt drifted")
    if (
        kag_handle_observation["python_sdk"]["commit"]
        != python_next["commit"]
        or kag_handle_observation["wire_version"]
        != next_spec["wire_version"]
        or kag_handle_observation["handle_contract"]["principal_binding"]
        != ["client_id", "issuer", "subject"]
        or not kag_handle_observation["handle_contract"][
            "bearer_verified_each_request"
        ]
        or kag_handle_observation["handle_contract"]["raw_tokens_recorded"]
        or kag_handle_observation["handle_checks"]["principal_isolation"]
        != "denied"
        or kag_handle_observation["handle_checks"]["expiry"] != "denied"
        or kag_handle_observation["handle_checks"]["cross_request_replay"]
        != "denied"
        or kag_handle_observation["handle_checks"]["same_request_replay"]
        != "allowed_read_only_idempotent"
        or not kag_handle_observation["handle_checks"][
            "same_request_result_unchanged"
        ]
        or kag_handle_observation["handle_checks"][
            "key_retirement_revocation"
        ]
        != "denied"
        or kag_handle_observation["handle_checks"]["tamper"] != "denied"
        or not kag_handle_observation["stable_registration_unchanged"]
        or kag_handle_observation["verdict"] != "handle_pair_passed"
    ):
        errors.append("isolated KAG explicit-handle receipt drifted")
    if (
        kag_cache_observation["python_sdk"]["commit"]
        != python_next["commit"]
        or kag_cache_observation["wire_version"]
        != next_spec["wire_version"]
        or kag_cache_observation["cache"]
        != {
            "scope": "private",
            "ttl_ms": 30000,
            "within_ttl_repeat_server_fetches": 1,
        }
        or not all(kag_cache_observation["checks"].values())
        or kag_cache_observation["inventories"]["initial"]
        != ["kag_discover"]
        or kag_cache_observation["inventories"]["after_explicit_refresh"]
        != ["kag_discover"]
        or not kag_cache_observation["stable_registration_unchanged"]
        or kag_cache_observation["verdict"] != "cache_pair_passed"
    ):
        errors.append("isolated KAG cache-behavior receipt drifted")
    if observation["abyss_pair_conformance"] != {
        "reason": (
            "The isolated Python MCP 2.0.0 KAG adapter passed the Abyss pair "
            "harness; this adapter-level result does not prove Codex "
            "next-wire support."
        ),
        "receipt_refs": [
            "mcp/protocol-lab/fixtures/kag-next-pair-observation.json"
        ],
        "status": "passed",
    }:
        errors.append("pair observation lost bounded Abyss adapter conformance")
    if (
        not observation["trace_cache_metadata_observed"]
        or not observation["explicit_handles_observed"]
        or observation["read_only_canary"]["status"] != "blocked"
        or observation["tasks_extension"]["status"] != "blocked"
        or observation["dual_support"]["status"] != "blocked"
        or observation["rollback"]["status"] != "blocked"
    ):
        errors.append("unproved handles, cache, Tasks, canary, or rollback escaped")
    for check_name in (
        "official_conformance",
        "abyss_pair_conformance",
        "read_only_canary",
        "dual_support",
        "rollback",
    ):
        check = observation[check_name]
        if check["status"] == "passed" and not check["receipt_refs"]:
            errors.append(f"{check_name} cannot pass without runtime receipts")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("MCP protocol lab validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "MCP protocol lab validation passed: final spec and SDKs are pinned; "
        "the observed legacy Codex pair blocks migration."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
