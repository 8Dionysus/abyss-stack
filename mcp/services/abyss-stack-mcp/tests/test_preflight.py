from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from abyss_stack_mcp.preflight import (
    ManagedContourCatalog,
    ManagedContourBinding,
    _bundle_digest,
    _sha256_file,
    _tree_digest,
    run_preflight,
)
from abyss_stack_mcp.preflight_sweep import run_sweep
from abyss_stack_mcp.managed_catalog import (
    ManagedContourTopology,
    ManagedContourTopologyEntry,
    build_managed_catalog,
    publish_catalog,
)
from abyss_stack_mcp.keeper_specs import build_keeper_specs
from abyss_stack_mcp.admission_automation import (
    AdmissionAutomationStatus,
    KeeperContourStatus,
    KeeperStageOperationalStatus,
)
from abyss_stack_mcp.system_status import build_system_status


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def _write(path: Path, payload: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    os.chmod(path, mode)


def _json(path: Path, payload: dict) -> None:
    _write(path, json.dumps(payload, sort_keys=True) + "\n")


def _fixture(tmp_path: Path) -> ManagedContourBinding:
    deployed = tmp_path / "Configs/mcp/services/demo-mcp"
    _write(deployed / "pyproject.toml", "[project]\nname='demo-mcp'\nversion='1.0'\n")
    tree_digest = _tree_digest(deployed)
    schema = tmp_path / "Configs/mcp/services/demo-mcp/schema.json"
    _write(schema, '{"type":"object"}\n')
    # The schema is part of the deployed tree; recompute after writing it.
    tree_digest = _tree_digest(deployed)
    schema_digest = _bundle_digest((schema,))

    credential = tmp_path / "Secrets/demo-read-token"
    _write(credential, "secret-value\n")
    auth_manifest = tmp_path / "Secrets/read-auth.json"
    _json(
        auth_manifest,
        {
            "credentials": {
                "demo": {
                    "policy_family": "read",
                    "sha256": hashlib.sha256(b"secret-value").hexdigest(),
                }
            }
        },
    )
    executable = tmp_path / "bin/demo-server"
    _write(executable, "#!/bin/sh\nexit 0\n", 0o755)
    validator = tmp_path / "owners/demo/validate.py"
    _write(validator, "print('valid')\n")
    unit = tmp_path / "systemd/demo.service"
    _write(
        unit,
        "[Service]\n"
        "Environment=AOA_MCP_POLICY_FAMILY=read\n"
        f"LoadCredential=demo:{credential}\n",
    )

    manifest_path = tmp_path / "Logs/deployments/latest.json"
    manifest_id = "sha256:" + "1" * 64
    manifest = {
        "manifest_id": manifest_id,
        "parity_state": "exact",
        "source": {"revision": "a" * 40},
        "services": [
            {
                "service_id": "demo-mcp",
                "package_name": "demo-mcp",
                "package_version": "1.0",
                "package_source_revision": "a" * 40,
                "package_digest": tree_digest,
                "deployed_path": "Configs/mcp/services/demo-mcp",
                "deployed_tree": {"tree_digest": tree_digest},
                "dependency_lock_digest": None,
            }
        ],
    }
    _json(manifest_path, manifest)

    registry_path = tmp_path / "registry.json"
    _json(
        registry_path,
        {
            "schema_version": "aoa_organ_registry_source_v2",
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
            "records": [
                {
                    "organ_id": "demo-organ",
                    "contours": [
                        {
                            "contour_id": "read",
                            "registry_state": "admitted",
                            "authority_class": "read",
                            "policy_family": "read",
                            "credential_class": "demo-read",
                            "principal_id": "demo-read-principal",
                            "allowlist": ["demo_read"],
                            "endpoint": {
                                "endpoint_ref": "http://127.0.0.1:5999/mcp",
                                "protocol_versions": ["2025-11-25"],
                                "server_schema_digest": schema_digest,
                            },
                            "runtime_identity": {
                                "package_name": "demo-mcp",
                                "package_version": "1.0",
                                "package_digest": tree_digest,
                                "deployment_revision": "a" * 40,
                                "deployment_manifest_digest": manifest_id,
                                "deployed_tree_digest": tree_digest,
                            },
                            "observation_route": "owner://demo/runtime/observation/read",
                            "rollback_route": "owner://demo/runtime/rollback/read",
                        }
                    ],
                }
            ],
        },
    )
    return ManagedContourBinding(
        binding_id="demo-read",
        organ_id="demo-organ",
        contour_id="read",
        policy_family="read",
        authority_class="read",
        service_id="demo-mcp",
        unit_name="demo.service",
        unit_path=str(unit),
        endpoint_ref="http://127.0.0.1:5999/mcp",
        protocol_version="2025-11-25",
        credential_class="demo-read",
        principal_id="demo-read-principal",
        credential_path=str(credential),
        auth_manifest_path=str(auth_manifest),
        auth_manifest_key="demo",
        executable_path=str(executable),
        executable_resolved_path=str(executable),
        executable_digest=_sha256_file(executable),
        deployment_manifest_path=str(manifest_path),
        deployed_root=str(tmp_path),
        registry_path=str(registry_path),
        schema_paths=(str(schema),),
        schema_bundle_digest=schema_digest,
        server_schema_digest=schema_digest,
        owner_validator_path=str(validator),
        owner_validator_digest=_sha256_file(validator),
        observation_route="owner://demo/runtime/observation/read",
        rollback_route="owner://demo/runtime/rollback/read",
        required_environment={"AOA_MCP_POLICY_FAMILY": "read"},
        unit_credential_binding=f"LoadCredential=demo:{credential}",
        allowed_mcp_names=("demo_read",),
    )


def test_preflight_passes_exact_identity_and_blocks_deployed_drift(tmp_path: Path) -> None:
    binding = _fixture(tmp_path)
    exact = run_preflight(binding, checked_at=NOW)
    assert exact.eligible_to_start
    assert exact.reason_codes == ()

    package_file = Path(binding.deployed_root) / "Configs/mcp/services/demo-mcp/pyproject.toml"
    package_file.write_text("[project]\nname='demo-mcp'\nversion='drift'\n", encoding="utf-8")
    drifted = run_preflight(binding, checked_at=NOW)
    assert not drifted.eligible_to_start
    assert "deployed_tree_digest_mismatch" in drifted.reason_codes
    assert "required_deployed_tree_digest_mismatch" in drifted.reason_codes
    assert not drifted.restart_loop_allowed
    check = next(item for item in drifted.checks if item.check_id == "deployed-tree")
    assert check.expected_identity != check.observed_identity


def test_preflight_blocks_expired_registry_and_symlink_credential(tmp_path: Path) -> None:
    binding = _fixture(tmp_path)
    registry_path = Path(binding.registry_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["expires_at"] = (NOW - timedelta(seconds=1)).isoformat()
    _json(registry_path, registry)
    credential = Path(binding.credential_path)
    target = credential.with_name("actual-token")
    credential.rename(target)
    credential.symlink_to(target)

    report = run_preflight(binding, checked_at=NOW)
    assert not report.eligible_to_start
    assert "registry_source_expired" in report.reason_codes
    assert "credential_file_unsafe" in report.reason_codes
    assert "credential_identity_mismatch" in report.reason_codes


def test_preflight_sweep_persists_bounded_status_and_detects_change(tmp_path: Path) -> None:
    binding = _fixture(tmp_path)
    catalog_path = tmp_path / "catalog.json"
    catalog = ManagedContourCatalog(contours=(binding,))
    _json(catalog_path, catalog.model_dump(mode="json"))
    output = tmp_path / "preflight"

    first = run_sweep(catalog_path, output, generated_at=NOW)
    assert first.all_eligible
    assert (output / "reports/demo-read.json").is_file()

    Path(binding.owner_validator_path).write_text("print('drift')\n", encoding="utf-8")
    second = run_sweep(
        catalog_path,
        output,
        generated_at=NOW + timedelta(seconds=1),
    )
    assert not second.all_eligible
    assert second.blocked_count == 1
    assert "owner_validator_digest_mismatch" in second.entries[0].reason_codes


def test_managed_catalog_is_derived_from_exact_owner_and_runtime_inputs(
    tmp_path: Path,
) -> None:
    binding = _fixture(tmp_path)
    topology = ManagedContourTopology(
        contours=(
            ManagedContourTopologyEntry(
                binding_id=binding.binding_id,
                organ_id=binding.organ_id,
                contour_id=binding.contour_id,
                service_id=binding.service_id,
                unit_name=binding.unit_name,
                unit_path=binding.unit_path,
                endpoint_ref=binding.endpoint_ref,
                protocol_version=binding.protocol_version,
                credential_path=binding.credential_path,
                auth_manifest_path=binding.auth_manifest_path,
                auth_manifest_key=binding.auth_manifest_key,
                executable_path=binding.executable_path,
                executable_resolved_path=binding.executable_resolved_path,
                executable_digest=binding.executable_digest,
                schema_paths=binding.schema_paths,
                schema_bundle_digest=binding.schema_bundle_digest,
                owner_validator_path=binding.owner_validator_path,
                owner_validator_digest=binding.owner_validator_digest,
                required_environment=binding.required_environment,
                unit_credential_binding=binding.unit_credential_binding,
            ),
        )
    )
    catalog = build_managed_catalog(
        topology,
        registry_path=Path(binding.registry_path),
        deployment_manifest_path=Path(binding.deployment_manifest_path),
        deployed_root=Path(binding.deployed_root),
    )
    assert catalog.contours[0] == binding

    output = tmp_path / "private/catalog.json"
    publish_catalog(catalog, output)
    assert ManagedContourCatalog.model_validate_json(output.read_text()) == catalog
    assert output.stat().st_mode & 0o777 == 0o600


def test_keeper_specs_bind_full_chain_and_fail_closed_expired_registry(
    tmp_path: Path,
) -> None:
    binding = _fixture(tmp_path)
    registry_path = Path(binding.registry_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["registry_id"] = "demo-private"
    registry["workspace_owner"] = "operator"
    registry["authored_at"] = (NOW - timedelta(hours=2)).isoformat()
    registry["expires_at"] = (NOW - timedelta(hours=1)).isoformat()
    registry["records"][0]["owners"] = {
        "source_owner": "demo-organ",
        "access_owner": "demo-organ",
        "runtime_owner": "abyss-stack",
        "control_owner": "aoa-sdk",
        "proof_owner": "aoa-evals",
        "acceptance_owner": "demo-organ",
    }
    catalog = ManagedContourCatalog(contours=(binding,))
    status = build_keeper_specs(
        registry,
        catalog,
        output_root=tmp_path / "keeper",
        generated_at=NOW,
    )
    assert status.entries[0].already_expired
    spec = json.loads(Path(status.entries[0].spec_path).read_text(encoding="utf-8"))
    assert [item["stage"] for item in spec["stages"]] == [
        "owner_source",
        "package",
        "deployment",
        "process",
        "endpoint",
        "credential",
        "schema",
        "authenticated_canary",
        "owner_grounding",
        "central_proof",
        "owner_acceptance",
        "rollback",
        "registry_admission",
        "consumer_observation",
    ]
    assert not next(
        item for item in spec["stages"] if item["stage"] == "central_proof"
    )["automatic_execution_allowed"]
    assert spec["spec_id"] == "sha256:" + "0" * 64


def test_system_status_keeps_runtime_admission_owner_protocol_and_tasks_distinct(
    tmp_path: Path,
) -> None:
    binding = _fixture(tmp_path)
    catalog = ManagedContourCatalog(contours=(binding,))
    catalog_path = tmp_path / "managed-contours.json"
    publish_catalog(catalog, catalog_path)
    preflight = run_sweep(catalog_path, tmp_path / "preflight", generated_at=NOW)
    keeper = KeeperContourStatus(
        organ_id=binding.organ_id,
        contour_id=binding.contour_id,
        state_id="sha256:" + "1" * 64,
        revision=2,
        admission_current=False,
        currentness=("live", "observed", "blocked", "last_good"),
        blocker_codes=("owner_acceptance_missing",),
        next_safe_stage="owner_acceptance",
        transaction_ref="owner://aoa-sdk/admission/demo-read",
        evidence_expires_at=NOW + timedelta(minutes=20),
        last_good_state_ref="owner://aoa-sdk/admission/demo-read/last-good",
        last_good_state_digest="sha256:" + "2" * 64,
        full_refresh_cost=100,
        planned_refresh_cost=20,
        reused_stage_count=12,
        refreshed_stage_count=1,
        blocked_stage_count=1,
        stage_states=(
            KeeperStageOperationalStatus(
                stage="process",
                node_id="sha256:" + "3" * 64,
                outcome="passed",
                expires_at=NOW + timedelta(minutes=30),
                current=True,
                reason_codes=(),
            ),
        ),
    )
    admission = AdmissionAutomationStatus(
        generated_at=NOW,
        overlay_contour_count=1,
        overlay_skips=(),
        managed_contour_count=1,
        preflight=preflight,
        keepers=(keeper,),
        next_safe_step="refresh owner acceptance",
    )
    protocol = {
        "schema_version": "abyss_mcp_protocol_lab_status_v2",
        "production_protocol": "2025-11-25",
        "next_protocol": "2026-07-28",
        "core_read_migration_allowed": False,
        "tasks_extension_allowed": False,
        "tasks_reference_consumer": "rust-rmcp-3.1.2",
        "tasks_reference_pair_passed": True,
        "tasks_inspector_strict_pair_blocked": True,
        "tasks_codex_consumer_eligible": False,
        "tasks_evidence_expires_at": (NOW + timedelta(days=7)).isoformat(),
        "tasks_blockers": ["codex_tasks_capability_absent"],
        "status_digest": "sha256:" + "4" * 64,
    }
    task_status = {
        "schema_version": "aoa_owner_task_store_status_v1",
        "observed_at": NOW.isoformat(),
        "record_count": 2,
        "active_count": 1,
        "status_counts": {
            "working": 1,
            "input_required": 0,
            "completed": 1,
            "failed": 0,
            "cancelled": 0,
            "expired": 0,
        },
        "outstanding_input_count": 0,
        "pending_cancellation_count": 1,
        "expired_unpersisted_count": 0,
        "orphan_candidate_count": 1,
        "orphan_after_seconds": 300,
        "orphan_candidate_basis": "pending_cancellation_without_terminal_transition",
        "oldest_active_updated_at": NOW.isoformat(),
        "next_expiry_at": (NOW + timedelta(hours=1)).isoformat(),
        "quota": {
            "maximum_active_tasks": 256,
            "maximum_active_tasks_per_principal": 32,
            "active_tasks": 1,
            "maximum_observed_active_per_principal": 1,
            "global_remaining": 255,
        },
        "contains_task_identifiers": False,
        "contains_principal_identifiers": False,
        "owner_execution_inferred": False,
        "admission_inferred": False,
    }
    registry = json.loads(Path(binding.registry_path).read_text(encoding="utf-8"))

    status = build_system_status(
        admission=admission,
        catalog=catalog,
        registry=registry,
        protocol=protocol,
        tasks=task_status,
        generated_at=NOW,
    )

    contour = status.contours[0]
    assert contour.runtime.live_state == "observed"
    assert contour.runtime.source_runtime_parity == "exact"
    assert contour.admission.admission_current is False
    assert contour.admission.cost_weight_not_planned == 80
    assert contour.owner.owner_watermark_state == "unobserved"
    assert status.tasks.active_count == 1
    assert status.tasks.orphan_candidate_count == 1
    assert status.tasks.task_completion_implies_admission is False
    assert status.protocol.tasks_reference_pair_passed is True
    assert status.operational_health_admission_owner_truth_collapsed is False
