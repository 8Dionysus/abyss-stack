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
        "python-mcp-2.0.0-conformance-observation.json",
        "protocol-conformance-observation.schema.json",
    ),
    "adapter": (
        "kag-next-pair-observation.json",
        "kag-next-pair-observation.schema.json",
    ),
    "handle": (
        "kag-handle-pair-observation.json",
        "kag-handle-pair-observation.schema.json",
    ),
    "cache": (
        "kag-cache-pair-observation.json",
        "kag-cache-pair-observation.schema.json",
    ),
    "codex_lab": (
        "codex-0.147.0-alpha.4-kag-next-lab-observation.json",
        "codex-kag-next-lab-observation.schema.json",
    ),
    "stable_rollback": (
        "codex-0.146.0-stable-kag-post-rollback-observation.json",
        "stable-kag-post-rollback-observation.schema.json",
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
    observation = _load(builder.OBSERVATION_PATH)
    fixtures: dict[str, dict[str, Any]] = {}
    try:
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
        ("Codex prerelease lab observation", fixtures["codex_lab"]),
        ("stable KAG post-rollback observation", fixtures["stable_rollback"]),
    ):
        expiry = _expiry_error(label, payload, checked_at)
        if expiry is not None:
            errors.append(expiry)
    if status["evidence_expires_at"] != min(
        matrix["expires_at"],
        fixtures["codex_lab"]["expires_at"],
        fixtures["stable_rollback"]["expires_at"],
    ):
        errors.append("generated status lost the earliest current evidence expiry")

    expected_render = json.dumps(status, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    if not builder.OUTPUT_PATH.is_file() or builder.OUTPUT_PATH.read_text() != expected_render:
        errors.append("generated protocol-lab status is missing or stale")

    if tuple(gate["gate_id"] for gate in matrix["migration_gates"]) != EXPECTED_GATE_IDS:
        errors.append("P1 gates must remain ordered P1-01 through P1-14")
    gate_status = {gate["gate_id"]: gate["status"] for gate in matrix["migration_gates"]}
    if {gate_id for gate_id, state in gate_status.items() if state == "blocked"} != {"P1-04", "P1-05", "P1-11"}:
        errors.append("current conformance, cancellation pair proof, and Tasks must remain blocked")
    p113 = next(gate for gate in matrix["migration_gates"] if gate["gate_id"] == "P1-13")
    if p113["evidence_refs"] != [
        "mcp/protocol-lab/fixtures/codex-0.147.0-alpha.4-kag-next-lab-observation.json"
    ]:
        errors.append("P1-13 text and evidence must bind the actual modern Codex canary")

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
        matrix["official_conformance"]["commit"] != "81eb1c3edaed87d7fd585d7b80186da7a2960660"
        or conformance["conformance_harness"]["commit"] != matrix["official_conformance"]["commit"]
        or conformance["directions"]["client"]["scenario_count"] != 33
        or conformance["directions"]["client"]["success_checks"] != 372
        or conformance["directions"]["client"]["failed_checks"] != 2
        or conformance["directions"]["client"]["failure_ids"]
        != [
            "json-schema-2020-12-client-echo-completed",
            "json-schema-2020-12-client-tool-found",
        ]
        or conformance["directions"]["server"]["scenario_count"] != 20
        or conformance["directions"]["server"]["success_checks"] != 40
        or conformance["directions"]["server"]["failed_checks"] != 0
        or conformance["verdict"] != "sdk_pair_blocked_current_harness_fixture_mismatch"
    ):
        errors.append("current conformance observation or its explicit blocker drifted")

    stable = _consumer(matrix, "codex-cli")
    lab = _consumer(matrix, "codex-cli-prerelease-lab")
    if stable["version"] != "0.146.0" or stable["next_wire_pair_observed"] or stable["server_discover_observed"]:
        errors.append("stable Codex must remain a legacy production pair")
    if (
        lab["version"] != "0.147.0-alpha.4"
        or not lab["next_wire_pair_observed"]
        or not lab["server_discover_observed"]
        or lab["tasks_wire_pair_observed"]
    ):
        errors.append("prerelease Codex lab pair facts drifted")

    codex_lab = fixtures["codex_lab"]
    stable_rollback = fixtures["stable_rollback"]
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
            "adapter_harness_sha256": "530066f8098b28f188fff6c2af87a63f0f7bfd6f145f96e018311b019a0b362c",
            "adapter_package_tree_sha256": "92dc85946802fc917bc832c9ab59d78a08494c5819b2e22abca769223d754cd3",
            "driver_sha256": "7c272928384bc1d9afb0ad3c0492808d25cc7c0a00a863805be378e9db8fb4dd",
        }
        or not codex_lab["stable_registration"]["unchanged"]
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
            "server_dispatch_cancelled": False,
            "server_dispatch_completed_after_client_cancel": True,
        }
    ):
        errors.append("current owner freshness or cancellation negative proof drifted")

    if (
        observation["official_conformance"]["status"] != "blocked"
        or observation["abyss_pair_conformance"]["status"] != "blocked"
        or observation["read_only_canary"]["status"] != "passed"
        or observation["dual_support"]["status"] != "passed"
        or observation["rollback"]["status"] != "passed"
        or observation["tasks_extension"]["status"] != "blocked"
        or observation["verdict"] != "blocked"
    ):
        errors.append("current pair observation lost its bounded pilot/production split")
    if (
        status["read_only_pilot_allowed"]
        or not status["read_only_pilot_completed"]
        or status["core_read_migration_allowed"]
        or status["tasks_extension_allowed"]
        or status["candidate_migration_allowed"]
        or status["internal_effect_migration_allowed"]
        or status["external_effect_migration_allowed"]
    ):
        errors.append("split migration verdicts no longer match exact evidence")
    if status["remaining_core_gate_ids"] != ["P1-04", "P1-05"] or status["remaining_tasks_gate_ids"] != ["P1-11"]:
        errors.append("Tasks must remain independent from the core-read blocker list")
    if status["production_cutover_blockers"] != [
        "stable_codex_modern_pair_unavailable",
        "current_conformance_fixture_mismatch",
        "modern_cancellation_not_propagated",
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
        "MCP protocol lab validation passed: the prerelease registered read canary and rollback "
        "are proven; current conformance, cancellation propagation, and production-eligible "
        "Codex still block core migration."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
