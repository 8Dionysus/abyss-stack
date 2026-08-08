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
        "python-mcp-2.0.0-frozen-conformance-observation.json",
        "protocol-frozen-conformance-observation.schema.json",
    ),
    "adapter": (
        "kag-next-cancellable-pair-observation.json",
        "kag-next-cancellable-pair-observation.schema.json",
    ),
    "handle": (
        "kag-handle-pair-current-observation.json",
        "kag-handle-pair-current-observation.schema.json",
    ),
    "cache": (
        "kag-cache-pair-current-observation.json",
        "kag-cache-pair-current-observation.schema.json",
    ),
    "codex_lab": (
        "codex-0.147.0-stable-kag-next-lab-observation.json",
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


def validate(checked_at: datetime | None = None) -> list[str]:
    errors: list[str] = []
    checked_at = checked_at or datetime.now(UTC)
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
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]

    for label, payload in (
        ("protocol compatibility matrix", matrix),
        ("Codex stable modern lab observation", fixtures["codex_lab"]),
        ("stable KAG post-rollback observation", fixtures["stable_rollback"]),
        ("Tasks compatibility matrix", tasks_matrix),
    ):
        expiry = _expiry_error(label, payload, checked_at)
        if expiry is not None:
            errors.append(expiry)
    if status["evidence_expires_at"] != min(
        matrix["expires_at"],
        fixtures["codex_lab"]["expires_at"],
        fixtures["stable_rollback"]["expires_at"],
        tasks_matrix["expires_at"],
    ):
        errors.append("generated status lost the earliest current evidence expiry")

    expected_render = json.dumps(status, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    if not builder.OUTPUT_PATH.is_file() or builder.OUTPUT_PATH.read_text() != expected_render:
        errors.append("generated protocol-lab status is missing or stale")

    if tuple(gate["gate_id"] for gate in matrix["migration_gates"]) != EXPECTED_GATE_IDS:
        errors.append("P1 gates must remain ordered P1-01 through P1-14")
    gate_status = {gate["gate_id"]: gate["status"] for gate in matrix["migration_gates"]}
    if {gate_id for gate_id, state in gate_status.items() if state == "blocked"} != {"P1-11"}:
        errors.append("frozen core conformance and cancellation must pass while Tasks remains separate")
    p113 = next(gate for gate in matrix["migration_gates"] if gate["gate_id"] == "P1-13")
    if p113["evidence_refs"] != [
        "mcp/protocol-lab/fixtures/codex-0.147.0-stable-kag-next-lab-observation.json"
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
        "scripts/run_tasks_adapter_pilot.py",
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
    if sdk_by_id["python-next"]["commit"] != "6f69a3758ebf2ee55ce050f58b470ce11af71133":
        errors.append("Python MCP 2.0.0 pin drifted")
    if sdk_by_id["typescript-next"]["commit"] != "cc4b41617ce3601b1290d67216ea0b194a3cd9ac":
        errors.append("TypeScript MCP 2.0.0 pin drifted")

    conformance = fixtures["conformance"]
    if (
        matrix["official_conformance"]["commit"] != "c321dd32035556e6769d3724a8ee97d87c3faaac"
        or conformance["conformance_harness"]["commit"] != matrix["official_conformance"]["commit"]
        or conformance["requirements_revision"] != "2026-07-28"
        or conformance["directions"]["client"]["scored_scenario_count"] != 32
        or conformance["directions"]["client"]["scored_success_checks"] != 372
        or conformance["directions"]["client"]["scored_failed_checks"] != 0
        or conformance["directions"]["server"]["scored_scenario_count"] != 37
        or conformance["directions"]["server"]["scored_success_checks"] != 119
        or conformance["directions"]["server"]["scored_failed_checks"] != 0
        or conformance["verdict"] != "sdk_pair_passed_frozen_2026_07_28_requirements"
    ):
        errors.append("frozen 2026-07-28 conformance observation drifted")

    stable = _consumer(matrix, "codex-cli")
    lab = _consumer(matrix, "codex-cli-stable-modern-lab")
    if stable["version"] != "0.147.0" or stable["next_wire_pair_observed"] or stable["server_discover_observed"]:
        errors.append("stable Codex must remain a legacy production pair")
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
        or codex_lab["server"]["source_artifacts"]
        != {
            "adapter_harness_sha256": "c2bff51463f47d526993a8096867e88ff1fe4ae47f51d22067bfd301883b1bbb",
            "adapter_package_tree_sha256": "92dc85946802fc917bc832c9ab59d78a08494c5819b2e22abca769223d754cd3",
            "driver_sha256": "7c4d0ea5e0393314cfda5bcb0c59ffb8c34632df19e03f85ba9b933f75e43677",
        }
        or not codex_lab["stable_registration"]["unchanged"]
        or codex_lab["wire"]["tasks_extension_advertised"]
        or codex_lab["wire"]["transport_response_mode"] != "sse_disconnect_cancellable"
        or not all(codex_lab["rollback"].values())
    ):
        errors.append("isolated Codex KAG modern-pair proof drifted")
    if (
        stable_rollback["verdict"] != "stable_production_route_passed_after_lab_rollback"
        or stable_rollback["canary"]["is_error"]
        or not stable_rollback["stable_registration"]["unchanged"]
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
        tasks_matrix["production_tasks_allowed"]
        or not tasks_matrix["core_read_migration_independent"]
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

    handle = fixtures["handle"]
    cache = fixtures["cache"]
    if (
        handle["handle_checks"]["principal_isolation"] != "denied"
        or handle["handle_checks"]["expiry"] != "denied"
        or handle["handle_checks"]["cross_request_replay"] != "denied"
        or handle["handle_checks"]["key_retirement_revocation"] != "denied"
    ):
        errors.append("requestState isolation, expiry, replay or revocation proof drifted")
    if not all(cache["checks"].values()):
        errors.append("private cache TTL, invalidation or removal proof drifted")
    adapter = fixtures["adapter"]
    if (
        adapter["owner_canary"]["freshness_state"] != "current"
        or adapter["pair"]["cancellation"]
        != {
            "client_request_cancelled": True,
            "server_dispatch_cancelled": True,
            "server_dispatch_completed_after_client_cancel": False,
        }
    ):
        errors.append("current owner freshness or cancellation propagation proof drifted")

    if (
        observation["official_conformance"]["status"] != "passed"
        or observation["abyss_pair_conformance"]["status"] != "passed"
        or observation["read_only_canary"]["status"] != "passed"
        or observation["dual_support"]["status"] != "passed"
        or observation["rollback"]["status"] != "passed"
        or observation["tasks_extension"]["status"] != "blocked"
        or observation["verdict"] != "blocked"
    ):
        errors.append("current pair observation lost its bounded pilot/production split")
    if (
        not status["read_only_pilot_allowed"]
        or not status["read_only_pilot_completed"]
        or status["core_read_migration_allowed"]
        or status["tasks_extension_allowed"]
        or status["candidate_migration_allowed"]
        or status["internal_effect_migration_allowed"]
        or status["external_effect_migration_allowed"]
    ):
        errors.append("split migration verdicts no longer match exact evidence")
    if status["remaining_core_gate_ids"] != [] or status["remaining_tasks_gate_ids"] != ["P1-11"]:
        errors.append("Tasks must remain independent from the core-read blocker list")
    if status["production_cutover_blockers"] != [
        "production_modern_pair_not_admitted",
    ]:
        errors.append("production cutover blockers drifted")

    service_pyprojects = sorted((REPO_ROOT / "mcp" / "services").glob("*/pyproject.toml"))
    constraints: list[str] = []
    for path in service_pyprojects:
        match = re.search(r'"mcp>=([^"]+)"', path.read_text())
        if match is not None:
            constraints.append(match.group(1))
    if not constraints or any(value != "1.27.2,<2" for value in constraints):
        errors.append("production stack MCP services must retain mcp>=1.27.2,<2 before cutover")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("MCP protocol lab validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "MCP protocol lab validation passed: frozen core conformance, cancellation, stable "
        "modern read canary and rollback are proven; production admission and Tasks remain "
        "separate gates."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
