from __future__ import annotations

import copy
import importlib.util
import json
import sys
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


def _load_runtime_catalog() -> Any:
    path = LAB_ROOT / "scripts" / "runtime_catalog.py"
    spec = importlib.util.spec_from_file_location(
        "runtime_catalog_under_test",
        path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_tasks_runner() -> Any:
    runner_path = LAB_ROOT / "scripts" / "run_codex_stack_tasks_pair.py"
    scripts_path = str(runner_path.parent)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    spec = importlib.util.spec_from_file_location(
        "codex_stack_tasks_pair_under_test",
        runner_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_live_fleet_runner() -> Any:
    runner_path = LAB_ROOT / "scripts" / "run_live_modern_read_fleet.py"
    scripts_path = str(runner_path.parent)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    spec = importlib.util.spec_from_file_location(
        "live_modern_read_fleet_under_test",
        runner_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_kag_next_runner() -> Any:
    runner_path = LAB_ROOT / "scripts" / "run_codex_kag_next_lab.py"
    import_paths = [
        str(LAB_ROOT / "scripts"),
        str(LAB_ROOT.parent / "services" / "aoa-kag-mcp" / "src"),
    ]
    for path in reversed(import_paths):
        if path not in sys.path:
            sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location(
        "codex_kag_next_lab_under_test",
        runner_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_identity_does_not_accept_an_old_major_two_patch_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_catalog = _load_runtime_catalog()

    class Completed:
        stdout = '{"mcp": "2.0.0", "mcp-types": "2.1.1"}\n'

    monkeypatch.setattr(runtime_catalog.subprocess, "run", lambda *args, **kwargs: Completed())
    identity = runtime_catalog.runtime_identity(
        Path("/opt/mcp/bin/python"),
        {
            "distribution": "mcp",
            "companion_distribution": "mcp-types",
            "tested_lock": "2.1.1",
        },
    )

    assert identity["exact_pair"] is False
    assert identity["expected"] == {"mcp": "2.1.1", "mcp-types": "2.1.1"}


def test_codex_client_uses_declared_recovery_rows_when_admission_is_empty() -> None:
    runtime_catalog = _load_runtime_catalog()
    catalog = runtime_catalog.load_runtime_catalog()

    declared = runtime_catalog.declared_client_read_entries(catalog)
    projected = runtime_catalog.client_read_entries(catalog, {"records": []})

    assert projected == declared
    assert len(projected) == len(
        catalog["deployment"]["client_read_contours"]
    )
    with pytest.raises(
        runtime_catalog.RuntimeCatalogError,
        match="no admitted read contours",
    ):
        runtime_catalog.admitted_read_entries(catalog, {"records": []})


@pytest.mark.parametrize(
    "registry_payload",
    (
        "{",
        "[]",
        '{"records": {}}',
    ),
)
def test_codex_client_settings_degrade_malformed_registry_to_declared_rows(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    registry_payload: str,
) -> None:
    runtime_catalog = _load_runtime_catalog()
    catalog = runtime_catalog.load_runtime_catalog()
    stack_root = tmp_path / "abyss-stack"
    registry = runtime_catalog.registry_path(catalog, stack_root)
    registry.parent.mkdir(parents=True)
    registry.write_text(registry_payload, encoding="utf-8")

    _feature, _recovery, rows = runtime_catalog.codex_client_settings(
        catalog,
        stack_root,
    )

    assert len(rows) == len(catalog["deployment"]["client_read_contours"])
    assert "using declared recovery rows" in capsys.readouterr().err


def test_codex_client_settings_degrade_unreadable_registry_to_declared_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime_catalog = _load_runtime_catalog()
    catalog = runtime_catalog.load_runtime_catalog()
    stack_root = tmp_path / "abyss-stack"
    registry = runtime_catalog.registry_path(catalog, stack_root)
    registry.parent.mkdir(parents=True)
    registry.write_text('{"records": []}', encoding="utf-8")
    original_read_text = Path.read_text

    def deny_registry_read(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == registry:
            raise PermissionError("registry read denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_registry_read)

    _feature, _recovery, rows = runtime_catalog.codex_client_settings(
        catalog,
        stack_root,
    )

    assert len(rows) == len(catalog["deployment"]["client_read_contours"])
    assert "using declared recovery rows" in capsys.readouterr().err


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
    evaluated_at = "2026-08-30T06:00:00Z"
    first = builder.build_status(matrix, observation, evaluated_at=evaluated_at)
    second = builder.build_status(
        copy.deepcopy(matrix),
        copy.deepcopy(observation),
        evaluated_at=evaluated_at,
    )

    assert first == second
    assert first["evidence_expires_at"] == "2026-08-15T08:33:46.547214Z"
    assert first["candidate_evidence_expires_at"] == "2026-09-06T01:51:50.099097Z"
    assert first["candidate_evidence_current"] is True
    assert first["deployment_evidence_expires_at"] == "2026-08-15T08:33:46.547214Z"
    assert first["deployment_evidence_current"] is False
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


def test_build_status_defaults_to_current_evaluation_time(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 30, 6, 0, tzinfo=tz)

    monkeypatch.setattr(builder, "datetime", _Clock)
    status = builder.build_status(matrix, observation)

    assert status["evaluated_at"] == "2026-08-30T06:00:00Z"


def test_next_action_changes_when_core_read_migration_is_admitted(
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
    stable_rollback = _load(
        LAB_ROOT
        / "fixtures"
        / "codex-0.147.0-stable-kag-post-rollback-observation.json"
    )
    tasks_matrix = _load(LAB_ROOT / "tasks-compatibility-matrix.v1.json")
    candidate_commit = "0921d94a74db900dccd2d534842aa7b6160542d2"
    for payload in (deployment, tasks_pair, stable_rollback, tasks_matrix):
        payload["mcp_sdk"] = "2.1.1"
        payload["mcp_sdk_source_revision"] = candidate_commit
        payload["expires_at"] = "2026-09-05T07:32:30.866342Z"
    deployment["mcp_sdk_artifact_digest"] = builder.EXPECTED_PRODUCTION_MCP_ARTIFACT_DIGEST
    deployment["read_fleet"].update(
        {
            "sdk_identity_attested": True,
            "sdk_identity_count": 11,
            "sdk_identity_unique_count": 1,
            "runtime_identity_attested": True,
            "listener_attested": True,
        }
    )
    tasks_pair["mcp_sdk_artifact_digest"] = builder.EXPECTED_PRODUCTION_MCP_ARTIFACT_DIGEST
    tasks_pair["runtime_observation_digest"] = "sha256:" + ("a" * 64)
    tasks_pair["runtime_process_id"] = 4321
    stable_rollback["server_binding"] = {
        "binding_method": "configured_codex_endpoint_to_per_unit_fleet_identity",
        "organ_id": "aoa-kag",
        "unit": "aoa-organ-mcp-read@aoa-kag.service",
        "fleet_endpoint_ref": "http://127.0.0.1:5425/mcp",
        "configured_endpoint_ref": "http://127.0.0.1:5425/mcp",
        "status_endpoint_ref": "http://127.0.0.1:5425/mcp",
        "status_entry_observed": True,
        "endpoint_matches": True,
        "fleet_process_identity": "systemd-user:aoa-kag:pid:1234:start:1",
        "process_identity_before": "systemd-user:aoa-kag:pid:1234:start:1",
        "process_identity_after": "systemd-user:aoa-kag:pid:1234:start:1",
        "process_identity_matches_fleet": True,
        "process_identity_stable": True,
        "python_executable_realpath": "/srv/abyss-machine/runtimes/python/bin/python",
        "sdk_identity": {
            "version": "2.1.1",
            "commit": candidate_commit,
            "artifact_digest": builder.EXPECTED_PRODUCTION_MCP_ARTIFACT_DIGEST,
            "mcp_distribution_digest": "sha256:" + ("a" * 64),
            "mcp_types_distribution_digest": "sha256:" + ("b" * 64),
        },
        "runtime_identity_attestation": {
            "state": "passed",
            "method": "server_emitted_startup_runtime_identity_header",
            "header": "X-Abyss-MCP-Runtime-Identity",
            "pid": 1234,
            "checked_during_discovery": True,
        },
        "listener_attestation": {
            "state": "passed",
            "method": "proc_net_tcp_listener_inode_owned_by_main_pid",
            "port": 5425,
            "pid": 1234,
            "socket_inodes": ["12345"],
            "checked_before_and_after_probe": True,
        },
        "contacted_server_probe": {
            "state": "passed",
            "method": "direct_modern_server_discover_with_runtime_identity_header",
            "endpoint_ref": "http://127.0.0.1:5425/mcp",
            "http_status": 200,
            "runtime_identity_attestation": {
                "state": "passed",
                "method": "server_emitted_startup_runtime_identity_header",
                "header": "X-Abyss-MCP-Runtime-Identity",
                "pid": 1234,
                "checked_during_discovery": True,
            },
        },
        "sdk_identity_matches_fleet": True,
        "sdk_identity_stable": True,
        "checked_before_and_after_tool_call": True,
    }
    status = builder.build_status(
        candidate,
        pair,
        stable_rollback_observation=stable_rollback,
        tasks_matrix=tasks_matrix,
        live_modern_fleet=deployment,
        codex_tasks_production_pair=tasks_pair,
        evaluated_at="2026-09-04T07:32:30.866342Z",
    )

    assert status["core_read_migration_allowed"] is True
    assert status["next_action"].startswith("Perform a bounded MCP 2.1.1 core-read")


def test_render_binds_status_to_the_recorded_evaluation_time(builder: Any) -> None:
    evaluated_at = "2026-08-30T06:00:00Z"
    rendered = json.loads(builder.render(evaluated_at=evaluated_at))
    expected = builder.build_status(
        _load(builder.MATRIX_PATH),
        _load(builder.OBSERVATION_PATH),
        evaluated_at=evaluated_at,
    )

    assert rendered == expected
    assert rendered["evaluated_at"] == evaluated_at


def test_expired_candidate_evidence_blocks_lab_pair_and_migration(
    builder: Any,
    matrix: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    status = builder.build_status(
        copy.deepcopy(matrix),
        copy.deepcopy(observation),
        evaluated_at="2026-09-06T01:51:50.099097Z",
    )

    assert status["candidate_evidence_current"] is False
    assert status["read_only_pilot_allowed"] is False
    assert status["core_read_migration_allowed"] is False
    assert "candidate_evidence_expired" in status["production_cutover_blockers"]


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


def test_codex_tasks_receipt_uses_the_serving_server_identity() -> None:
    runner = _load_tasks_runner()
    artifact_digest = "sha256:" + ("b" * 64)
    observation_digest = "sha256:" + ("a" * 64)
    terminal = {
        "result": {
            "structuredContent": {
                "metadata": {
                    "mcp_sdk": "2.1.1",
                    "mcp_sdk_source_revision": "0921d94a74db900dccd2d534842aa7b6160542d2",
                    "mcp_sdk_artifact_digest": artifact_digest,
                    "observation_digest": observation_digest,
                    "mcp_sdk_process_id": 4321,
                    "mcp_sdk_runtime_attestation": {
                        "state": "passed",
                        "method": "process_startup_sdk_identity_snapshot",
                        "pid": 4321,
                    },
                }
            }
        }
    }

    assert runner.server_runtime_identity(terminal) == (
        "2.1.1",
        "0921d94a74db900dccd2d534842aa7b6160542d2",
        artifact_digest,
        observation_digest,
    )
    with pytest.raises(RuntimeError, match="serving MCP task result"):
        runner.server_runtime_identity({"result": {}})


def test_tasks_production_schema_requires_new_runtime_identity_fields(
    builder: Any,
) -> None:
    schema_path = LAB_ROOT / "schemas" / "codex-tasks-production-pair.schema.json"
    historical = _load(
        LAB_ROOT / "fixtures" / "codex-tasks-production-pair-20260809.json"
    )
    builder.validate_payload(historical, schema_path)

    candidate = copy.deepcopy(historical)
    candidate["mcp_sdk"] = "2.1.1"
    candidate["mcp_sdk_source_revision"] = (
        "0921d94a74db900dccd2d534842aa7b6160542d2"
    )
    candidate["mcp_sdk_artifact_digest"] = "sha256:" + ("b" * 64)
    with pytest.raises(ValueError, match="runtime_observation_digest"):
        builder.validate_payload(candidate, schema_path)

    candidate["runtime_observation_digest"] = "sha256:" + ("a" * 64)
    with pytest.raises(ValueError, match="runtime_process_id"):
        builder.validate_payload(candidate, schema_path)
    candidate["runtime_process_id"] = 4321
    builder.validate_payload(candidate, schema_path)


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
        "artifact_digest": "sha256:1ef71b1a3cfb3daba29b61d9f280896b35bdc1038474285cc8295071418b01e5",
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
    assert codex["server"]["python_mcp_artifact_digest"] == (
        "sha256:1ef71b1a3cfb3daba29b61d9f280896b35bdc1038474285cc8295071418b01e5"
    )
    assert codex["server"]["source_revisions"] == {
        "abyss_stack": "b8bb0bdb4f4984c7338adddf606e7d3509ff6d0b",
        "aoa_kag": "578e4cea9a04b76a881bde240d5479efceea4926",
    }
    assert codex["consumer"]["production_authority"] is False


def test_live_fleet_accepts_only_reviewed_sdk_identities() -> None:
    runner = _load_live_fleet_runner()
    registry = {
        "admitted_read_count": 1,
        "protocol_versions": ["2026-07-28"],
        "bootstrap_identity_count": 0,
    }
    def row(sdk: str, artifact: str) -> dict[str, Any]:
        result = {
            "organ_id": "abyss-stack",
            "mcp_sdk": sdk,
            "mcp_sdk_source_revision": runner.MCP_SDK_SOURCE_REVISIONS[sdk],
            "mcp_sdk_artifact_digest": artifact,
            "sdk_attestation": {"state": "passed"},
        }
        if sdk == "2.1.1":
            result.update(
                {
                    "main_pid": 1,
                    "endpoint_ref": "http://127.0.0.1:5431/mcp",
                    "runtime_identity_attestation": {
                        "state": "passed",
                        "method": "server_emitted_startup_runtime_identity_header",
                        "header": "X-Abyss-MCP-Runtime-Identity",
                        "pid": 1,
                        "checked_during_discovery": True,
                    },
                    "listener_attestation": {
                        "state": "passed",
                        "method": "proc_net_tcp_listener_inode_owned_by_main_pid",
                        "port": 5431,
                        "pid": 1,
                        "socket_inodes": ["12345"],
                        "checked_before_and_after_probe": True,
                    },
                }
            )
        return result

    historical = row("2.0.0", "sha256:" + ("a" * 64))
    candidate = row(
        "2.1.1",
        "sha256:a638c12e432fc0444d263a55db04668cd789437fde33951cc2be491021219601",
    )
    assert runner._fleet_verdict("2.0.0", registry, [historical], True) == "passed"
    assert runner._fleet_verdict("2.1.1", registry, [candidate], True) == "passed"
    assert runner._fleet_verdict("2.2.0", registry, [candidate], True) == "failed"
    assert runner._fleet_verdict("2.1.1", registry, [candidate], False) == "failed"


def test_live_fleet_binds_candidate_identity_to_the_answering_process() -> None:
    runner = _load_live_fleet_runner()
    sdk = {
        "version": "2.1.1",
        "commit": runner.MCP_SDK_SOURCE_REVISIONS["2.1.1"],
        "artifact_digest": "sha256:a638c12e432fc0444d263a55db04668cd789437fde33951cc2be491021219601",
        "mcp_distribution_digest": "sha256:" + ("a" * 64),
        "mcp_types_distribution_digest": "sha256:" + ("b" * 64),
    }
    before = {"main_pid": 4321}
    headers = {
        "X-Abyss-MCP-Runtime-Identity": json.dumps({**sdk, "pid": 4321}),
    }

    attestation = runner._server_runtime_identity_attestation(
        headers,
        before,
        sdk,
        "aoa-kag",
    )

    assert attestation == {
        "state": "passed",
        "method": "server_emitted_startup_runtime_identity_header",
        "header": "X-Abyss-MCP-Runtime-Identity",
        "pid": 4321,
        "checked_during_discovery": True,
    }
    with pytest.raises(RuntimeError, match="does not match"):
        runner._server_runtime_identity_attestation(
            {"x-abyss-mcp-runtime-identity": json.dumps({**sdk, "pid": 4322})},
            before,
            sdk,
            "aoa-kag",
        )
    with pytest.raises(RuntimeError, match="omitted"):
        runner._server_runtime_identity_attestation({}, before, sdk, "aoa-kag")


def test_live_fleet_rejects_nonuniform_or_unattested_unit_identity() -> None:
    runner = _load_live_fleet_runner()
    registry = {
        "admitted_read_count": 2,
        "protocol_versions": ["2026-07-28"],
        "bootstrap_identity_count": 0,
    }
    first = {
        "mcp_sdk": "2.1.1",
        "mcp_sdk_source_revision": runner.MCP_SDK_SOURCE_REVISIONS["2.1.1"],
        "mcp_sdk_artifact_digest": "sha256:" + ("b" * 64),
        "sdk_attestation": {"state": "passed"},
    }
    second = copy.deepcopy(first)
    second["mcp_sdk_artifact_digest"] = "sha256:" + ("c" * 64)
    assert runner._fleet_verdict("2.1.1", registry, [first, second], True) == "failed"

    missing = copy.deepcopy(first)
    missing["sdk_attestation"] = None
    assert runner._fleet_verdict("2.1.1", registry, [missing], True) == "failed"


def test_candidate_deployment_receipt_requires_per_unit_identity_summary(tmp_path: Path) -> None:
    runner = _load_kag_next_runner()
    historical = _load(LAB_ROOT / "fixtures" / "live-modern-fleet-20260809.json")
    historical_path = tmp_path / "historical.json"
    historical_path.write_text(json.dumps(historical), encoding="utf-8")
    assert runner._deployment_sdk_identity(historical_path) == (
        "2.0.0",
        "6f69a3758ebf2ee55ce050f58b470ce11af71133",
    )

    candidate = copy.deepcopy(historical)
    candidate["mcp_sdk"] = "2.1.1"
    candidate["mcp_sdk_source_revision"] = "0921d94a74db900dccd2d534842aa7b6160542d2"
    candidate["mcp_sdk_artifact_digest"] = runner.EXPECTED_PYTHON_MCP_ARTIFACT_DIGEST
    candidate["read_fleet"] = {
        **candidate["read_fleet"],
        "sdk_identity_attested": True,
        "sdk_identity_count": 11,
        "sdk_identity_unique_count": 1,
        "runtime_identity_attested": True,
        "listener_attested": True,
    }
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    assert runner._deployment_sdk_identity(candidate_path) == (
        "2.1.1",
        "0921d94a74db900dccd2d534842aa7b6160542d2",
    )

    del candidate["read_fleet"]["sdk_identity_attested"]
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    with pytest.raises(RuntimeError, match="per-unit SDK attestation"):
        runner._deployment_sdk_identity(candidate_path)


def test_candidate_stable_canary_requires_raw_aoa_kag_fleet_binding(tmp_path: Path) -> None:
    runner = _load_kag_next_runner()
    historical = _load(LAB_ROOT / "fixtures" / "live-modern-fleet-20260809.json")
    candidate = copy.deepcopy(historical)
    candidate.update(
        {
            "mcp_sdk": "2.1.1",
            "mcp_sdk_source_revision": runner.MCP_SDK_SOURCE_REVISIONS["2.1.1"],
            "mcp_sdk_artifact_digest": runner.EXPECTED_PYTHON_MCP_ARTIFACT_DIGEST,
        }
    )
    candidate["read_fleet"] = {
        **candidate["read_fleet"],
        "sdk_identity_attested": True,
        "sdk_identity_count": 11,
        "sdk_identity_unique_count": 1,
        "runtime_identity_attested": True,
        "listener_attested": True,
    }
    receipt_path = tmp_path / "candidate.json"
    receipt_path.write_text(json.dumps(candidate), encoding="utf-8")

    with pytest.raises(RuntimeError, match="raw per-unit live-fleet"):
        runner._deployment_fleet_unit(receipt_path, "2.1.1", "aoa-kag")

    candidate["servers"] = [
        {
            "organ_id": "aoa-kag",
            "unit": "aoa-organ-mcp-read@aoa-kag.service",
            "endpoint_ref": "http://127.0.0.1:5425/mcp",
            "main_pid": 1234,
            "process_identity": "systemd-user:aoa-kag:pid:1234:start:1",
            "python_executable": "/srv/abyss-machine/runtimes/python/bin/python",
            "python_executable_realpath": "/srv/abyss-machine/runtimes/python/bin/python",
            "mcp_sdk": "2.1.1",
            "mcp_sdk_source_revision": runner.MCP_SDK_SOURCE_REVISIONS["2.1.1"],
            "mcp_sdk_artifact_digest": runner.EXPECTED_PYTHON_MCP_ARTIFACT_DIGEST,
            "mcp_sdk_distribution_digests": {
                "mcp": "sha256:" + ("a" * 64),
                "mcp-types": "sha256:" + ("b" * 64),
            },
            "sdk_attestation": {
                "state": "passed",
                "checked_before_and_after_probe": True,
            },
            "runtime_identity_attestation": {
                "state": "passed",
                "method": "server_emitted_startup_runtime_identity_header",
                "header": "X-Abyss-MCP-Runtime-Identity",
                "pid": 1234,
                "checked_during_discovery": True,
            },
            "listener_attestation": {
                "state": "passed",
                "method": "proc_net_tcp_listener_inode_owned_by_main_pid",
                "port": 5425,
                "pid": 1234,
                "socket_inodes": ["12345"],
                "checked_before_and_after_probe": True,
            },
        }
    ]
    receipt_path.write_text(json.dumps(candidate), encoding="utf-8")
    assert runner._deployment_fleet_unit(receipt_path, "2.1.1", "aoa-kag")["organ_id"] == "aoa-kag"


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
    stable_rollback = _load(
        LAB_ROOT / "fixtures" / "codex-0.147.0-stable-kag-post-rollback-observation.json"
    )
    tasks_matrix = _load(LAB_ROOT / "tasks-compatibility-matrix.v1.json")
    deployment["mcp_sdk"] = "2.1.1"
    deployment["mcp_sdk_artifact_digest"] = builder.EXPECTED_PRODUCTION_MCP_ARTIFACT_DIGEST
    deployment["read_fleet"].update(
        {
            "sdk_identity_attested": True,
            "sdk_identity_count": 11,
            "sdk_identity_unique_count": 1,
            "runtime_identity_attested": True,
            "listener_attested": True,
        }
    )
    tasks_pair["mcp_sdk"] = "2.1.1"
    tasks_pair["mcp_sdk_artifact_digest"] = builder.EXPECTED_PRODUCTION_MCP_ARTIFACT_DIGEST
    tasks_pair["runtime_observation_digest"] = "sha256:" + ("a" * 64)
    tasks_pair["runtime_process_id"] = 4321

    stale = builder.build_status(
        candidate,
        pair,
        stable_rollback_observation=stable_rollback,
        tasks_matrix=tasks_matrix,
        live_modern_fleet=deployment,
        codex_tasks_production_pair=tasks_pair,
    )
    assert stale["deployment_evidence_current"] is False
    assert stale["core_read_migration_allowed"] is False

    future = "2026-09-05T07:32:30.866342Z"
    for payload in (deployment, tasks_pair, stable_rollback, tasks_matrix):
        payload["expires_at"] = future
    still_stale = builder.build_status(
        candidate,
        pair,
        stable_rollback_observation=stable_rollback,
        tasks_matrix=tasks_matrix,
        live_modern_fleet=deployment,
        codex_tasks_production_pair=tasks_pair,
    )
    assert still_stale["deployment_evidence_current"] is False
    assert still_stale["core_read_migration_allowed"] is False

    candidate_commit = "0921d94a74db900dccd2d534842aa7b6160542d2"
    stable_rollback["server_binding"] = {
        "binding_method": "configured_codex_endpoint_to_per_unit_fleet_identity",
        "organ_id": "aoa-kag",
        "unit": "aoa-organ-mcp-read@aoa-kag.service",
        "fleet_endpoint_ref": "http://127.0.0.1:5425/mcp",
        "configured_endpoint_ref": "http://127.0.0.1:5425/mcp",
        "status_endpoint_ref": None,
        "status_entry_observed": True,
        "endpoint_matches": True,
        "fleet_process_identity": "systemd-user:aoa-kag:pid:1234:start:1",
        "process_identity_before": "systemd-user:aoa-kag:pid:1234:start:1",
        "process_identity_after": "systemd-user:aoa-kag:pid:1234:start:1",
        "process_identity_matches_fleet": True,
        "process_identity_stable": True,
        "python_executable_realpath": "/srv/abyss-machine/runtimes/python/bin/python",
        "sdk_identity": {
            "version": "2.1.1",
            "commit": candidate_commit,
            "artifact_digest": builder.EXPECTED_PRODUCTION_MCP_ARTIFACT_DIGEST,
            "mcp_distribution_digest": "sha256:" + ("a" * 64),
            "mcp_types_distribution_digest": "sha256:" + ("b" * 64),
        },
        "sdk_identity_matches_fleet": True,
        "sdk_identity_stable": True,
        "checked_before_and_after_tool_call": True,
        "runtime_identity_attestation": {
            "state": "passed",
            "method": "server_emitted_startup_runtime_identity_header",
            "header": "X-Abyss-MCP-Runtime-Identity",
            "pid": 1234,
            "checked_during_discovery": True,
        },
        "listener_attestation": {
            "state": "passed",
            "method": "proc_net_tcp_listener_inode_owned_by_main_pid",
            "port": 5425,
            "pid": 1234,
            "socket_inodes": ["12345"],
            "checked_before_and_after_probe": True,
        },
        "contacted_server_probe": {
            "state": "passed",
            "method": "direct_modern_server_discover_with_runtime_identity_header",
            "endpoint_ref": "http://127.0.0.1:5425/mcp",
            "http_status": 200,
            "runtime_identity_attestation": {
                "state": "passed",
                "method": "server_emitted_startup_runtime_identity_header",
                "header": "X-Abyss-MCP-Runtime-Identity",
                "pid": 1234,
                "checked_during_discovery": True,
            },
        },
    }
    for payload in (deployment, tasks_pair, stable_rollback, tasks_matrix):
        payload["mcp_sdk"] = "2.1.1"
        payload["mcp_sdk_source_revision"] = candidate_commit
    admitted = builder.build_status(
        candidate,
        pair,
        stable_rollback_observation=stable_rollback,
        tasks_matrix=tasks_matrix,
        live_modern_fleet=deployment,
        codex_tasks_production_pair=tasks_pair,
        evaluated_at="2026-09-04T07:32:30.866342Z",
    )
    assert admitted["deployment_evidence_current"] is True
    assert admitted["core_read_migration_allowed"] is True
    assert admitted["read_only_pilot_allowed"] is True
    assert admitted["internal_effect_migration_allowed"] is False

    expired = builder.build_status(
        candidate,
        pair,
        stable_rollback_observation=stable_rollback,
        tasks_matrix=tasks_matrix,
        live_modern_fleet=deployment,
        codex_tasks_production_pair=tasks_pair,
        evaluated_at="2026-09-06T07:32:30.866342Z",
    )
    assert expired["deployment_evidence_current"] is False
    assert expired["core_read_migration_allowed"] is False

    pair["rollback"]["status"] = "failed"
    rejected = builder.build_status(
        candidate,
        pair,
        stable_rollback_observation=stable_rollback,
        tasks_matrix=tasks_matrix,
        live_modern_fleet=deployment,
        codex_tasks_production_pair=tasks_pair,
    )
    assert rejected["core_read_migration_allowed"] is False
    assert rejected["read_only_pilot_allowed"] is False
