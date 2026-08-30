#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parents[1]
BUILDER_PATH = LAB_ROOT / "scripts" / "build_protocol_lab_status.py"
WATCH_PLAN_PATH = LAB_ROOT / "protocol-watch-plan.v1.json"
WATCH_PLAN_SCHEMA_PATH = LAB_ROOT / "schemas" / "protocol-watch-plan.schema.json"
TASKS_MATRIX_PATH = LAB_ROOT / "tasks-compatibility-matrix.v1.json"
TASKS_MATRIX_SCHEMA_PATH = LAB_ROOT / "schemas" / "tasks-compatibility-matrix.schema.json"
EXPECTED_GATE_IDS = tuple(f"P1-{index:02d}" for index in range(1, 15))
EXPECTED_PYTHON_MCP_VERSION = "2.1.1"
EXPECTED_PYTHON_MCP_COMMIT = "0921d94a74db900dccd2d534842aa7b6160542d2"
EXPECTED_PYTHON_MCP_ARTIFACT_DIGEST = "sha256:1ef71b1a3cfb3daba29b61d9f280896b35bdc1038474285cc8295071418b01e5"
EXPECTED_DEPLOYMENT_MCP_VERSION = "2.0.0"
EXPECTED_DEPLOYMENT_MCP_COMMIT = "6f69a3758ebf2ee55ce050f58b470ce11af71133"
EXPECTED_AOA_KAG_COMMIT = "578e4cea9a04b76a881bde240d5479efceea4926"
EXPECTED_KAG_CANONICAL_SOURCE_DIGEST = "5aeb7b89dce54b414281f5390c8cc063f59bb75d02b28e1a014da2d96701e164"
EXPECTED_STACK_SOURCE_COMMIT = "cbb387567b193cd75762894fd77e192d2bf5cb80"
FIXTURES = {
    "wire": (
        "codex-0.146.0-wire-observation.json",
        "protocol-consumer-wire-observation.schema.json",
    ),
    "production": (
        "codex-0.146.0-production-pair-observation.json",
        "protocol-production-pair-observation.schema.json",
    ),
    "conformance": (
        "python-mcp-2.1.1-frozen-conformance-observation.json",
        "protocol-frozen-conformance-observation.schema.json",
    ),
    "adapter": (
        "kag-next-cancellable-pair-2.1.1-observation.json",
        "kag-next-cancellable-pair-observation.schema.json",
    ),
    "handle": (
        "kag-handle-pair-2.1.1-current-observation.json",
        "kag-handle-pair-current-observation.schema.json",
    ),
    "cache": (
        "kag-cache-pair-2.1.1-current-observation.json",
        "kag-cache-pair-current-observation.schema.json",
    ),
    "codex_lab": (
        "codex-0.147.0-stable-kag-next-lab-2.1.1-observation.json",
        "codex-kag-next-stable-observation.schema.json",
    ),
    "stable_rollback": (
        "codex-0.147.0-stable-kag-post-rollback-observation.json",
        "stable-kag-post-rollback-current-observation.schema.json",
    ),
    "watch_run": (
        "protocol-watch-run-verdict-20260808.json",
        "protocol-watch-run-verdict.schema.json",
    ),
    "tasks_pilot": (
        "tasks-adapter-pilot-20260808.json",
        "tasks-adapter-pilot.schema.json",
    ),
    "rmcp_tasks_pair": (
        "rmcp-3.1.2-tasks-adapter-pair-20260808.json",
        "rmcp-tasks-adapter-pair.schema.json",
    ),
    "inspector_tasks_blocker": (
        "inspector-2.1.0-tasks-strict-pair-blocked-20260808.json",
        "inspector-tasks-strict-pair.schema.json",
    ),
    "live_modern_fleet": (
        "live-modern-fleet-20260809.json",
        "live-modern-fleet-observation.schema.json",
    ),
    "codex_tasks_production_pair": (
        "codex-tasks-production-pair-20260809.json",
        "codex-tasks-production-pair.schema.json",
    ),
}


def _load_builder() -> Any:
    spec = importlib.util.spec_from_file_location("protocol_lab_builder", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load protocol lab builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _expiry_error(label: str, payload: dict[str, Any], checked_at: datetime) -> str | None:
    expires_at = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    if expires_at <= checked_at:
        return f"{label} expired at {payload['expires_at']}; refresh is required"
    return None


def _consumer(matrix: dict[str, Any], consumer_id: str) -> dict[str, Any]:
    rows = [item for item in matrix["consumer_pairs"] if item["consumer_id"] == consumer_id]
    if len(rows) != 1:
        raise ValueError(f"expected exactly one consumer row for {consumer_id}")
    return rows[0]


def _live_fleet_identity_attested(payload: dict[str, Any]) -> bool:
    """Require candidate fleet evidence to summarize every serving unit."""

    if payload.get("mcp_sdk") != EXPECTED_PYTHON_MCP_VERSION:
        return True
    read_fleet = payload.get("read_fleet")
    return bool(
        payload.get("mcp_sdk_artifact_digest") == EXPECTED_PYTHON_MCP_ARTIFACT_DIGEST
        and isinstance(read_fleet, dict)
        and read_fleet.get("sdk_identity_attested") is True
        and read_fleet.get("sdk_identity_count") == 11
        and read_fleet.get("sdk_identity_unique_count") == 1
    )


def validate(checked_at: datetime | None = None) -> list[str]:
    errors: list[str] = []
    checked_at = checked_at or datetime.now(UTC)
    evaluated_at = checked_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    builder = _load_builder()
    matrix = _load(builder.MATRIX_PATH)
    tasks_matrix = _load(TASKS_MATRIX_PATH)
    observation = _load(builder.OBSERVATION_PATH)
    watch_plan = _load(WATCH_PLAN_PATH)
    fixtures: dict[str, dict[str, Any]] = {}
    try:
        builder.validate_payload(watch_plan, WATCH_PLAN_SCHEMA_PATH)
        builder.validate_payload(tasks_matrix, TASKS_MATRIX_SCHEMA_PATH)
        for name, (fixture_name, schema_name) in FIXTURES.items():
            payload = _load(LAB_ROOT / "fixtures" / fixture_name)
            builder.validate_payload(payload, LAB_ROOT / "schemas" / schema_name)
            fixtures[name] = payload
        status = builder.build_status(
            matrix,
            observation,
            fixtures["production"],
            fixtures["codex_lab"],
            fixtures["stable_rollback"],
            tasks_matrix,
            fixtures["tasks_pilot"],
            fixtures["rmcp_tasks_pair"],
            fixtures["inspector_tasks_blocker"],
            fixtures["live_modern_fleet"],
            fixtures["codex_tasks_production_pair"],
            evaluated_at=evaluated_at,
        )
        generated_status = builder.load_json(builder.OUTPUT_PATH)
        rendered_status = builder.build_status(
            matrix,
            observation,
            fixtures["production"],
            fixtures["codex_lab"],
            fixtures["stable_rollback"],
            tasks_matrix,
            fixtures["tasks_pilot"],
            fixtures["rmcp_tasks_pair"],
            fixtures["inspector_tasks_blocker"],
            fixtures["live_modern_fleet"],
            fixtures["codex_tasks_production_pair"],
            evaluated_at=generated_status["evaluated_at"],
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]

    for label, payload in (
        ("protocol compatibility matrix", matrix),
        ("Codex stable modern lab observation", fixtures["codex_lab"]),
    ):
        expiry = _expiry_error(label, payload, checked_at)
        if expiry is not None:
            errors.append(expiry)
    expected_candidate_expiry = min(
        matrix["expires_at"],
        fixtures["codex_lab"]["expires_at"],
    )
    expected_deployment_expiry = min(
        fixtures["stable_rollback"]["expires_at"],
        tasks_matrix["expires_at"],
        fixtures["live_modern_fleet"]["expires_at"],
        fixtures["codex_tasks_production_pair"]["expires_at"],
    )
    if status["candidate_evidence_expires_at"] != expected_candidate_expiry:
        errors.append("generated status lost the earliest candidate evidence expiry")
    if status["deployment_evidence_expires_at"] != expected_deployment_expiry:
        errors.append("generated status lost a deployment-bound evidence expiry")
    if status["evidence_expires_at"] != min(
        expected_candidate_expiry,
        expected_deployment_expiry,
    ):
        errors.append("generated status lost the overall earliest evidence expiry")

    expected_render = json.dumps(
        rendered_status,
        indent=2,
        ensure_ascii=True,
        sort_keys=True,
    ) + "\n"
    if not builder.OUTPUT_PATH.is_file() or builder.OUTPUT_PATH.read_text() != expected_render:
        errors.append("generated protocol-lab status is missing or stale")
    for field in (
        "candidate_evidence_current",
        "deployment_evidence_current",
        "core_read_migration_allowed",
        "tasks_extension_allowed",
        "tasks_codex_consumer_eligible",
        "production_cutover_blockers",
    ):
        if generated_status.get(field) != status.get(field):
            errors.append(
                "generated protocol-lab status is not current for "
                f"{field}"
            )

    if tuple(gate["gate_id"] for gate in matrix["migration_gates"]) != EXPECTED_GATE_IDS:
        errors.append("P1 gates must remain ordered P1-01 through P1-14")
    gate_status = {gate["gate_id"]: gate["status"] for gate in matrix["migration_gates"]}
    if any(state != "passed" for state in gate_status.values()):
        errors.append("all P1 compatibility gates must pass for their stated evidence")
    p113 = next(gate for gate in matrix["migration_gates"] if gate["gate_id"] == "P1-13")
    if p113["evidence_refs"] != [
        "mcp/protocol-lab/fixtures/codex-0.147.0-stable-kag-next-lab-2.1.1-observation.json"
    ]:
        errors.append("P1-13 text and evidence must bind the actual modern Codex canary")

    watch_ids = [item["input_id"] for item in watch_plan["inputs"]]
    if len(watch_ids) != len(set(watch_ids)):
        errors.append("protocol watcher input IDs must be unique")
    expected_watch_ids = {
        "codex-consumer",
        "codex-registry-latest",
        "mcp-spec-latest",
        "python-sdk-latest",
        "typescript-sdk-latest",
        "go-sdk-latest",
        "rust-sdk-latest",
        "csharp-sdk-latest",
        "inspector-latest",
        "conformance-main",
        "protocol-contract",
        "protocol-status",
    }
    if set(watch_ids) != expected_watch_ids:
        errors.append("protocol watcher lost an exact local or upstream refresh input")
    watch_by_id = {item["input_id"]: item for item in watch_plan["inputs"]}
    tasks_watch_paths = {
        "tasks-compatibility-matrix.v1.json",
        "fixtures/tasks-adapter-pilot-20260808.json",
        "fixtures/rmcp-3.1.2-tasks-adapter-pair-20260808.json",
        "fixtures/inspector-2.1.0-tasks-strict-pair-blocked-20260808.json",
        "fixtures/codex-tasks-production-pair-20260809.json",
        "fixtures/live-modern-fleet-20260809.json",
        "scripts/run_tasks_adapter_pilot.py",
        "scripts/run_codex_stack_tasks_pair.py",
        "scripts/run_live_modern_read_fleet.py",
        "scripts/run_live_nonread_protocol.py",
        "scripts/run_rust_tasks_adapter_pair.py",
        "scripts/run_inspector_tasks_adapter_pair.py",
    }
    if not tasks_watch_paths.issubset(set(watch_by_id["protocol-contract"]["paths"])):
        errors.append("protocol watcher lost a Tasks matrix, pair fixture, or runner")
    if watch_plan["ttl_source"] != {
        "path": "generated/protocol-lab-status.json",
        "pointer": "/evidence_expires_at",
    }:
        errors.append("protocol watcher must consume the derived earliest evidence expiry")

    next_spec = matrix["next_spec"]
    if next_spec != {
        "commit": "5f5440bb26a62e2cf3440b92da5a667efa03b267",
        "final_published": True,
        "production_allowed": True,
        "release_label": "2026-07-28",
        "release_status": "final",
        "source": "https://github.com/modelcontextprotocol/modelcontextprotocol/releases/tag/2026-07-28",
        "tag": "2026-07-28",
        "wire_version": "2026-07-28",
    }:
        errors.append("final 2026-07-28 specification pin drifted")
    sdk_by_id = {sdk["sdk_id"]: sdk for sdk in matrix["sdk_lines"]}
    candidate_identity = (
        sdk_by_id["python-next"]["version"],
        sdk_by_id["python-next"]["commit"],
    )
    historical_identity = (
        EXPECTED_DEPLOYMENT_MCP_VERSION,
        EXPECTED_DEPLOYMENT_MCP_COMMIT,
    )
    if (
        sdk_by_id["python-next"]["commit"] != EXPECTED_PYTHON_MCP_COMMIT
        or sdk_by_id["python-next"]["version"] != EXPECTED_PYTHON_MCP_VERSION
        or sdk_by_id["python-next"]["stack_pin"] != EXPECTED_PYTHON_MCP_VERSION
    ):
        errors.append("Python MCP 2.1.1 pin drifted")
    if sdk_by_id["typescript-next"]["commit"] != "cc4b41617ce3601b1290d67216ea0b194a3cd9ac":
        errors.append("TypeScript MCP 2.0.0 pin drifted")

    conformance = fixtures["conformance"]
    if (
        matrix["official_conformance"]["commit"] != "c321dd32035556e6769d3724a8ee97d87c3faaac"
        or conformance["conformance_harness"]["commit"] != matrix["official_conformance"]["commit"]
        or conformance["python_sdk"]["commit"] != EXPECTED_PYTHON_MCP_COMMIT
        or conformance["python_sdk"]["version"] != EXPECTED_PYTHON_MCP_VERSION
        or conformance["python_sdk"]["artifact_digest"] != EXPECTED_PYTHON_MCP_ARTIFACT_DIGEST
        or conformance["requirements_revision"] != "2026-07-28"
        or conformance["directions"]["client"]["scored_scenario_count"] != 32
        or conformance["directions"]["client"]["scored_success_checks"] != 372
        or conformance["directions"]["client"]["scored_failed_checks"] != 0
        or conformance["directions"]["server"]["scored_scenario_count"] != 37
        or conformance["directions"]["server"]["scored_success_checks"] != 119
        or conformance["directions"]["server"]["scored_failed_checks"] != 0
        or conformance["verdict"] != "sdk_pair_passed_frozen_2026_07_28_requirements"
    ):
        errors.append("frozen 2026-07-28 conformance observation for MCP 2.1.1 drifted")

    production = _consumer(matrix, "codex-cli-os-abyss")
    stable = _consumer(matrix, "codex-cli")
    lab = _consumer(matrix, "codex-cli-stable-modern-lab")
    if (
        production["version"] != "0.147.0-abyss.2"
        or not production["next_wire_pair_observed"]
        or not production["server_discover_observed"]
        or not production["tasks_wire_pair_observed"]
        or production["production_protocol_versions_observed"] != ["2026-07-28"]
    ):
        errors.append("OS Abyss Codex production modern pair facts drifted")
    if stable["version"] != "0.147.0" or stable["next_wire_pair_observed"] or stable["server_discover_observed"]:
        errors.append("upstream Codex fallback row drifted")
    if (
        lab["version"] != "0.147.0"
        or not lab["next_wire_pair_observed"]
        or not lab["server_discover_observed"]
        or lab["tasks_wire_pair_observed"]
    ):
        errors.append("stable Codex modern lab pair facts drifted")

    codex_lab = fixtures["codex_lab"]
    stable_rollback = fixtures["stable_rollback"]
    watch_run = fixtures["watch_run"]
    tasks_pilot = fixtures["tasks_pilot"]
    rmcp_tasks_pair = fixtures["rmcp_tasks_pair"]
    inspector_tasks_blocker = fixtures["inspector_tasks_blocker"]
    live_modern_fleet = fixtures["live_modern_fleet"]
    codex_tasks_production_pair = fixtures["codex_tasks_production_pair"]
    if (
        codex_lab["wire"]["version"] != "2026-07-28"
        or not codex_lab["wire"]["server_discover_observed"]
        or codex_lab["wire"]["initialize_observed"]
        or codex_lab["wire"]["mcp_session_id_observed"]
        or codex_lab["wire"]["trace_sent"] != codex_lab["wire"]["trace_observed"]
        or codex_lab["wire"]["tool_inventory"] != ["kag_discover"]
        or codex_lab["wire"]["wrong_bearer_http_status"] != 401
        or codex_lab["wire"]["input_limit_bytes"] != 16384
        or codex_lab["wire"]["output_limit_bytes"] != 262144
        or codex_lab["wire"]["oversized_input_denied_code"] != -32602
        or codex_lab["server"]["python_mcp_version"] != EXPECTED_PYTHON_MCP_VERSION
        or codex_lab["server"]["python_mcp_commit"] != EXPECTED_PYTHON_MCP_COMMIT
        or codex_lab["server"]["python_mcp_artifact_digest"]
        != EXPECTED_PYTHON_MCP_ARTIFACT_DIGEST
        or codex_lab["server"]["source_revisions"]["abyss_stack"]
        != EXPECTED_STACK_SOURCE_COMMIT
        or codex_lab["server"]["source_revisions"]["aoa_kag"]
        != EXPECTED_AOA_KAG_COMMIT
        or codex_lab["server"]["source_artifacts"]
        != {
            "adapter_harness_sha256": "3dc4b78352072340e3677ae50ceb94a25671e00e5e1ff8dfbf4407f85f8e8f56",
            "adapter_package_tree_sha256": "ac7f2a70de13a69d14f5b43b0ffd01f9f797112e5929f6008b2cae0357210078",
            "driver_sha256": "d7dae0ae03795c9041413ca0662809411ca8106b7ce991e673ab603878c33b66",
        }
        or not codex_lab["stable_registration"]["unchanged"]
        or codex_lab["wire"]["tasks_extension_advertised"]
        or codex_lab["wire"]["transport_response_mode"] != "sse_disconnect_cancellable"
        or not all(codex_lab["rollback"].values())
    ):
        errors.append("isolated Codex KAG modern-pair proof drifted")
    if (
        stable_rollback["verdict"] != "stable_production_route_passed_after_lab_rollback"
        or (
            stable_rollback["mcp_sdk"],
            stable_rollback["mcp_sdk_source_revision"],
        )
        not in {candidate_identity, historical_identity}
        or stable_rollback["canary"]["is_error"]
        or not stable_rollback["stable_registration"]["unchanged"]
        or not builder._stable_rollback_identity_bound(stable_rollback)
        or stable_rollback["secrets_included"]
    ):
        errors.append("stable post-rollback canary proof drifted")
    if (
        watch_run["verdict"] != "compatible_for_lab_and_read_canary"
        or not watch_run["facts"]["frozen_core_conformance_passed"]
        or not watch_run["facts"]["modern_cancellation_propagated"]
        or not watch_run["facts"]["stable_modern_codex_lab_passed"]
        or not watch_run["facts"]["stable_post_rollback_canary_passed"]
        or not watch_run["facts"]["client_extension_capability_absent"]
        or watch_run["facts"]["production_cutover_allowed"]
    ):
        errors.append("orchestrated protocol watcher run verdict drifted")
    task_cases = {item["case"]: item for item in tasks_pilot["cases"]}
    expected_task_cases = {
        "short_sync_fallback",
        "long_task_poll_complete",
        "jsonrpc_failure_inlined",
        "input_required_partial_duplicate_resume",
        "cooperative_cancellation",
        "cancellation_completion_race",
        "worker_and_client_restart_resume",
        "ttl_expiry_and_cleanup",
        "wrong_principal_and_unknown_are_indistinguishable",
        "quota_rate_and_payload_policy",
        "useful_read_only_owner_diagnostic",
    }
    if (
        set(task_cases) != expected_task_cases
        or tasks_pilot["case_count"] != len(task_cases)
        or not tasks_pilot["all_cases_passed"]
        or not all(item["passed"] for item in task_cases.values())
        or tasks_pilot["production_enabled"]
        or tasks_pilot["codex_consumer_used"]
        or tasks_pilot["notifications"]["tested"]
        or not tasks_pilot["owner_pilot"]["resumed_after_adapter_restart"]
        or tasks_pilot["owner_pilot"]["owner_rerun_count"] != 0
    ):
        errors.append("bounded Tasks adapter pilot evidence drifted")
    tasks_by_id = {item["consumer_id"]: item for item in tasks_matrix["consumers"]}
    expected_tasks_consumers = {
        "codex-cli-os-abyss",
        "codex-cli",
        "mcp-inspector",
        "python-sdk",
        "typescript-sdk",
        "go-sdk",
        "rust-rmcp",
        "csharp-sdk",
        "ext-tasks-reference",
    }
    if set(tasks_by_id) != expected_tasks_consumers:
        errors.append("Tasks compatibility matrix lost an exact consumer row")
    elif (
        not tasks_matrix["production_tasks_allowed"]
        or not tasks_matrix["core_read_migration_independent"]
        or tasks_by_id["codex-cli-os-abyss"]["features"]["advertisement"] != "wire_pass"
        or tasks_by_id["codex-cli-os-abyss"]["features"]["tasks_cancel"] != "wire_pass"
        or tasks_by_id["codex-cli-os-abyss"]["verdict"]
        != "eligible_for_bounded_production"
        or tasks_by_id["codex-cli"]["features"]["advertisement"] != "wire_absent"
        or tasks_by_id["codex-cli"]["verdict"] != "ineligible"
        or tasks_by_id["mcp-inspector"]["features"]["tasks_get"] != "wire_blocked"
        or tasks_by_id["mcp-inspector"]["verdict"] != "blocked"
        or tasks_by_id["rust-rmcp"]["features"]["tasks_get"] != "wire_pass"
        or tasks_by_id["rust-rmcp"]["verdict"]
        != "eligible_for_isolated_reference_pilots"
        or tasks_by_id["csharp-sdk"]["verdict"] != "source_supported_unpaired"
    ):
        errors.append("Tasks compatibility verdicts drifted from exact pair evidence")
    if (
        rmcp_tasks_pair["verdict"]
        != "released_rmcp_passed_feature_gated_abyss_adapter"
        or not all(rmcp_tasks_pair["wire"].values())
        or rmcp_tasks_pair["adapter"]["production_enabled"]
        or rmcp_tasks_pair["owner_result"]["owner_rerun_count"] != 0
        or inspector_tasks_blocker["verdict"]
        != "blocked_missing_mcp_name_on_raw_tasks_get"
        or inspector_tasks_blocker["strict_pair"]["mcp_name_on_tasks_get"]
        or inspector_tasks_blocker["adapter_response"]
        != {
            "error_code": -32020,
            "http_status": 400,
            "strict_boundary_retained": True,
        }
    ):
        errors.append("reference-client Tasks pair or Inspector blocker drifted")
    if (
        live_modern_fleet["verdict"] != "production_modern_only_passed"
        or live_modern_fleet["read_fleet"]["production_units"] != 11
        or live_modern_fleet["read_fleet"]["admitted_units"] != 11
        or live_modern_fleet["read_fleet"]["bootstrap_identities"] != 0
        or not live_modern_fleet["read_fleet"]["legacy_initialize_denied"]
        or live_modern_fleet["rollback"]["active_legacy_units"] != 0
    ):
        errors.append("live modern-only production fleet evidence drifted")
    if not _live_fleet_identity_attested(live_modern_fleet):
        errors.append("live modern fleet candidate lacks per-unit SDK artifact attestation")
    deployment_identities = {
        (payload["mcp_sdk"], payload["mcp_sdk_source_revision"])
        for payload in (
            stable_rollback,
            live_modern_fleet,
            codex_tasks_production_pair,
            tasks_matrix,
        )
    }
    if not deployment_identities.issubset({candidate_identity, historical_identity}):
        errors.append(
            "deployment-bound production receipts must use the candidate or retained historical MCP identity"
        )
    elif len(deployment_identities) != 1:
        errors.append(
            "deployment-bound production receipts must share one exact MCP identity during a refresh"
        )
    if (
        codex_tasks_production_pair["verdict"] != "eligible_for_bounded_production"
        or not codex_tasks_production_pair["production_pair"]
        or not codex_tasks_production_pair["lifecycle"]["create_passed"]
        or not codex_tasks_production_pair["lifecycle"]["get_completed_passed"]
        or not codex_tasks_production_pair["lifecycle"]["cancel_acknowledged"]
        or not codex_tasks_production_pair["lifecycle"]["get_cancelled_passed"]
        or codex_tasks_production_pair["lifecycle"]["update_input_required_live_pair"]
        or codex_tasks_production_pair["lifecycle"]["notifications_proven"]
    ):
        errors.append("bounded Codex Tasks production pair evidence drifted")

    handle = fixtures["handle"]
    cache = fixtures["cache"]
    if (
        handle["handle_checks"]["principal_isolation"] != "denied"
        or handle["handle_checks"]["expiry"] != "denied"
        or handle["handle_checks"]["cross_request_replay"] != "denied"
        or handle["handle_checks"]["key_retirement_revocation"] != "denied"
    ):
        errors.append("requestState isolation, expiry, replay or revocation proof drifted")
    if (
        handle["python_sdk"]
        != {
            "artifact_digest": EXPECTED_PYTHON_MCP_ARTIFACT_DIGEST,
            "commit": EXPECTED_PYTHON_MCP_COMMIT,
            "version": EXPECTED_PYTHON_MCP_VERSION,
        }
        or handle["source_revisions"]["abyss_stack"] != EXPECTED_STACK_SOURCE_COMMIT
        or handle["source_revisions"]["aoa_kag"] != EXPECTED_AOA_KAG_COMMIT
    ):
        errors.append("MCP 2.1.1 requestState receipt is not bound to its source revisions")
    if not all(cache["checks"].values()):
        errors.append("private cache TTL, invalidation or removal proof drifted")
    if (
        cache["python_sdk"]
        != {
            "artifact_digest": EXPECTED_PYTHON_MCP_ARTIFACT_DIGEST,
            "commit": EXPECTED_PYTHON_MCP_COMMIT,
            "version": EXPECTED_PYTHON_MCP_VERSION,
        }
        or cache["source_revisions"]["abyss_stack"] != EXPECTED_STACK_SOURCE_COMMIT
        or cache["source_revisions"]["aoa_kag"] != EXPECTED_AOA_KAG_COMMIT
    ):
        errors.append("MCP 2.1.1 cache receipt is not bound to its source revisions")
    adapter = fixtures["adapter"]
    if (
        adapter["owner_canary"]["freshness_state"]
        not in {"current", "canonical_only"}
        or adapter["owner_canary"]["projection_exact_state"] != "current"
        or adapter["owner_canary"]["canonical_source_digest"]
        != EXPECTED_KAG_CANONICAL_SOURCE_DIGEST
        or adapter["pair"]["cancellation"]
        != {
            "client_request_cancelled": True,
            "server_dispatch_cancelled": True,
            "server_dispatch_completed_after_client_cancel": False,
        }
    ):
        errors.append("current owner freshness or cancellation propagation proof drifted")
    if (
        adapter["python_sdk"]
        != {
            "artifact_digest": EXPECTED_PYTHON_MCP_ARTIFACT_DIGEST,
            "commit": EXPECTED_PYTHON_MCP_COMMIT,
            "version": EXPECTED_PYTHON_MCP_VERSION,
        }
        or adapter["source_revisions"]["abyss_stack"] != EXPECTED_STACK_SOURCE_COMMIT
        or adapter["source_revisions"]["aoa_kag"] != EXPECTED_AOA_KAG_COMMIT
    ):
        errors.append("MCP 2.1.1 adapter receipt is not bound to its source revisions")

    if (
        observation["official_conformance"]["status"] != "passed"
        or observation["abyss_pair_conformance"]["status"] != "passed"
        or observation["read_only_canary"]["status"] != "passed"
        or observation["dual_support"]["status"] != "passed"
        or observation["rollback"]["status"] != "passed"
        or observation["tasks_extension"]["status"] != "passed"
        or observation["verdict"] != "passed"
    ):
        errors.append("current pair observation lost its bounded pilot/production split")
    remaining_core_gate_ids = {
        gate["gate_id"]
        for gate in matrix["migration_gates"]
        if gate["gate_id"] != "P1-11" and gate["status"] != "passed"
    }
    remaining_tasks_gate_ids = {
        gate["gate_id"]
        for gate in matrix["migration_gates"]
        if gate["gate_id"] == "P1-11" and gate["status"] != "passed"
    }
    expected_core_read_migration = all(
        (
            production["next_wire_pair_observed"],
            production["server_discover_observed"],
            observation["official_conformance"]["status"] == "passed",
            observation["abyss_pair_conformance"]["status"] == "passed",
            observation["read_only_canary"]["status"] == "passed",
            observation["compatibility_aliases"]["status"] == "passed",
            observation["dual_support"]["status"] == "passed",
            observation["rollback"]["status"] == "passed",
            matrix["pilot"]["state"] == "passed",
            not remaining_core_gate_ids,
            live_modern_fleet["verdict"] == "production_modern_only_passed",
            live_modern_fleet["read_fleet"]["production_units"] == 11,
            live_modern_fleet["read_fleet"]["admitted_units"] == 11,
            live_modern_fleet["read_fleet"]["bootstrap_identities"] == 0,
            live_modern_fleet["rollback"]["active_legacy_units"] == 0,
            _live_fleet_identity_attested(live_modern_fleet),
            status["candidate_evidence_current"],
            status["deployment_evidence_current"],
        )
    )
    expected_tasks_extension = bool(
        expected_core_read_migration
        and codex_tasks_production_pair["verdict"]
        == "eligible_for_bounded_production"
        and not remaining_tasks_gate_ids
    )
    if (
        not status["read_only_pilot_allowed"]
        or not status["read_only_pilot_completed"]
        or status["core_read_migration_allowed"]
        != expected_core_read_migration
        or status["tasks_extension_allowed"] != expected_tasks_extension
        or not status["candidate_protocol_ready"]
        or status["internal_effect_protocol_ready"]
        or status["candidate_migration_allowed"]
        or status["internal_effect_migration_allowed"]
        or status["external_effect_migration_allowed"]
    ):
        errors.append("split migration verdicts no longer match exact evidence")
    if status["remaining_core_gate_ids"] or status["remaining_tasks_gate_ids"]:
        errors.append("completed core-read and bounded Tasks gates must have no remainder")
    expected_production_cutover_blockers: list[str] = []
    if not production["next_wire_pair_observed"]:
        expected_production_cutover_blockers.append("production_modern_pair_not_admitted")
    if observation["official_conformance"]["status"] != "passed":
        expected_production_cutover_blockers.append("current_conformance_fixture_mismatch")
    if observation["abyss_pair_conformance"]["status"] != "passed":
        expected_production_cutover_blockers.append("modern_cancellation_not_propagated")
    if not status["deployment_evidence_current"]:
        expected_production_cutover_blockers.append(
            "deployment_bound_evidence_not_refreshed_for_mcp_2_1_1"
        )
    if not status["candidate_evidence_current"]:
        expected_production_cutover_blockers.append("candidate_evidence_expired")
    if status["production_cutover_blockers"] != expected_production_cutover_blockers:
        errors.append("production cutover blockers no longer match exact evidence")

    service_pyprojects = sorted((REPO_ROOT / "mcp" / "services").glob("*/pyproject.toml"))
    constraints: list[str] = []
    for path in service_pyprojects:
        match = re.search(r'"mcp==([^"]+)"', path.read_text())
        if match is not None:
            constraints.append(match.group(1))
    if not constraints or any(value != EXPECTED_PYTHON_MCP_VERSION for value in constraints):
        errors.append("all stack MCP service packages must pin exact mcp==2.1.1")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("MCP protocol lab validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "MCP protocol lab validation passed: the isolated MCP 2.1.1 candidate is "
        "source-bound, deployment-bound MCP 2.0.0 evidence is retained, and cutover "
        "remains fail-closed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
