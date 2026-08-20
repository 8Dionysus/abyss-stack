from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from abyss_stack_mcp.canary import (
    CanaryDeploymentBinding,
    CanaryInventoryCounts,
    CanaryProbeResult,
    build_receipt,
)
from abyss_stack_mcp.observation import (
    RuntimeCanaryContract,
    RuntimeTarget,
    RuntimeTargetCatalog,
)
from abyss_stack_mcp.preflight import (
    ManagedContourCatalog,
    ManagedContourBinding,
    PreflightError,
    _bundle_digest,
    _sha256_file,
    _tree_digest,
    run_preflight,
)
from abyss_stack_mcp.runtime_overlay import build_runtime_overlay
from abyss_stack_mcp.preflight_sweep import run_sweep
from abyss_stack_mcp.managed_catalog import (
    ManagedContourTopology,
    ManagedContourTopologyEntry,
    build_managed_catalog,
    publish_catalog,
)
from abyss_stack_mcp.managed_topology import (
    _managed_unit_template_path,
    _organ_read_unit_exec_start_binding,
)
from abyss_stack_mcp.keeper_specs import build_keeper_specs
from abyss_stack_mcp.admission_automation import (
    AdmissionAutomationStatus,
    KeeperContourStatus,
    KeeperStageOperationalStatus,
    _keeper_inbox_paths,
    _run_keeper_cycles,
)
from abyss_stack_mcp.system_status import build_system_status


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
SIGNING_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def test_organ_managed_topology_exec_binding_matches_runtime_unit() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    unit = repo_root / "systemd/user/aoa-organ-mcp-read@.service"
    exec_start_lines = tuple(
        line
        for line in unit.read_text(encoding="utf-8").splitlines()
        if line.startswith("ExecStart=")
    )

    assert exec_start_lines == (
        _organ_read_unit_exec_start_binding(Path("/srv/AbyssOS/abyss-stack")),
    )


@pytest.mark.parametrize(
    ("production_unit", "observed_unit", "template"),
    (
        (
            "aoa-organ-mcp-read@demo.service",
            "aoa-organ-mcp-read@demo.service",
            "aoa-organ-mcp-read@.service",
        ),
        (
            "aoa-organ-mcp-read@demo.service",
            "aoa-organ-mcp-read-bootstrap@demo.service",
            "aoa-organ-mcp-read-bootstrap@.service",
        ),
        (
            "aoa-organ-mcp-read@demo.service",
            "aoa-organ-mcp-read-fallback@demo.service",
            "aoa-organ-mcp-read-fallback@.service",
        ),
        (
            "abyss-stack-mcp-read.service",
            "abyss-stack-mcp-read-fallback.service",
            "abyss-stack-mcp-read-fallback.service",
        ),
    ),
)
def test_managed_topology_selects_observed_canary_template(
    production_unit: str,
    observed_unit: str,
    template: str,
) -> None:
    root = Path("/srv/AbyssOS/abyss-stack")
    assert _managed_unit_template_path(root, production_unit, observed_unit) == (
        root / "Configs/systemd/user" / template
    )


def _write(path: Path, payload: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    os.chmod(path, mode)


def _json(path: Path, payload: dict) -> None:
    _write(path, json.dumps(payload, sort_keys=True) + "\n")


def _fixture(
    tmp_path: Path,
    *,
    receipt_process_unit_name: str = "aoa-organ-mcp-read@demo.service",
    receipt_process_identity: str = (
        "systemd-user:aoa-organ-mcp-read@demo.service:pid:321:start:654"
    ),
) -> ManagedContourBinding:
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
        f"LoadCredential=demo:{credential}\n"
        f"ExecStart={executable}\n",
    )

    manifest_path = tmp_path / "Logs/deployments/latest.json"
    manifest_id = "sha256:" + "1" * 64
    manifest = {
        "manifest_id": manifest_id,
        "parity_state": "exact",
        "deployed_at": (NOW - timedelta(minutes=2)).isoformat(),
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
    canary_contract = RuntimeCanaryContract(
        tool_name="demo_read",
        arguments={},
        schema_pointer="/schema_version",
        schema_value="demo-v1",
        required_pointers=("/value",),
    )
    target = RuntimeTarget(
        organ_id="demo-organ",
        registry_organ_id="demo-organ",
        service_id="demo-mcp",
        unit_name="aoa-organ-mcp-read@demo.service",
        executable_ref=str(executable),
        endpoint_ref="http://127.0.0.1:5999/mcp",
        protocol_versions=("2025-11-25",),
        effect_classes=("observe",),
        canary_route="runbook://demo/read",
        canary_contract=canary_contract,
        rollback_route="runbook://demo/rollback/read",
    )
    deployment = CanaryDeploymentBinding(
        manifest_id=manifest_id,
        service_id="demo-mcp",
        package_source_revision="a" * 40,
        package_digest=tree_digest,
        deployed_tree_digest=tree_digest,
        deployed_at=NOW - timedelta(minutes=2),
    )
    receipt = build_receipt(
        target=target,
        contract=canary_contract,
        probe=CanaryProbeResult(
            protocol_version="2025-11-25",
            server_name="demo-mcp",
            server_version="1.0",
            server_schema_digest=schema_digest,
            selected_tool_schema_digest="sha256:" + "2" * 64,
            inventory_counts=CanaryInventoryCounts(
                tools=1, resources=0, resource_templates=0, prompts=0
            ),
            call_succeeded=True,
            result={"schema_version": "demo-v1", "value": "ok"},
            call_latency_ms=1,
            total_latency_ms=2,
        ),
        observed_at=NOW - timedelta(minutes=1),
        ttl_seconds=3600,
        signing_key=SIGNING_KEY,
        deployment=deployment,
        process_identity=receipt_process_identity,
        process_unit_name=receipt_process_unit_name,
    )
    canary_path = tmp_path / "Logs/canaries/latest/demo-organ.read.json"
    _json(canary_path, receipt.model_dump(mode="json"))
    public_key_path = tmp_path / "Secrets/canary-public.pem"
    public_key_path.write_bytes(
        SIGNING_KEY.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    public_key_path.chmod(0o600)
    return ManagedContourBinding(
        binding_id="demo-read",
        organ_id="demo-organ",
        contour_id="read",
        policy_family="read",
        authority_class="read",
        service_id="demo-mcp",
        unit_name="aoa-organ-mcp-read@demo.service",
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
        unit_exec_start_binding=f"ExecStart={executable}",
        canary_receipt_path=str(canary_path),
        canary_receipt_id=receipt.receipt_id,
        canary_process_unit_name=receipt_process_unit_name,
        canary_observed_at=receipt.observed_at,
        canary_expires_at=receipt.expires_at,
        canary_deployment_manifest_id=receipt.deployment_manifest_id,
        canary_public_key_path=str(public_key_path),
        allowed_mcp_names=("demo_read",),
    )


def test_preflight_passes_exact_identity_and_blocks_deployed_drift(
    tmp_path: Path,
) -> None:
    binding = _fixture(tmp_path)
    exact = run_preflight(binding, checked_at=NOW)
    assert exact.eligible_to_start
    assert exact.reason_codes == ()

    package_file = (
        Path(binding.deployed_root) / "Configs/mcp/services/demo-mcp/pyproject.toml"
    )
    package_file.write_text(
        "[project]\nname='demo-mcp'\nversion='drift'\n", encoding="utf-8"
    )
    drifted = run_preflight(binding, checked_at=NOW)
    assert not drifted.eligible_to_start
    assert "deployed_tree_digest_mismatch" in drifted.reason_codes
    assert "required_deployed_tree_digest_mismatch" in drifted.reason_codes
    assert not drifted.restart_loop_allowed
    check = next(item for item in drifted.checks if item.check_id == "deployed-tree")
    assert check.expected_identity != check.observed_identity


def test_preflight_blocks_expired_registry_and_symlink_credential(
    tmp_path: Path,
) -> None:
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


def test_preflight_revalidates_canary_ttl_on_every_start(tmp_path: Path) -> None:
    binding = _fixture(tmp_path)

    report = run_preflight(binding, checked_at=binding.canary_expires_at)

    assert not report.eligible_to_start
    assert "canary_receipt_invalid_or_expired" in report.reason_codes
    assert not report.restart_loop_allowed


def test_preflight_reports_missing_canary_as_machine_readable_block(
    tmp_path: Path,
) -> None:
    binding = _fixture(tmp_path)
    Path(binding.canary_receipt_path).unlink()

    report = run_preflight(binding, checked_at=NOW)

    assert not report.eligible_to_start
    assert "canary_receipt_invalid_or_expired" in report.reason_codes


def test_preflight_requires_one_exact_exec_start_binding(tmp_path: Path) -> None:
    binding = _fixture(tmp_path)
    unit_path = Path(binding.unit_path)
    unit_path.write_text(
        unit_path.read_text(encoding="utf-8") + "ExecStart=/tmp/unreviewed-server\n",
        encoding="utf-8",
    )

    report = run_preflight(binding, checked_at=NOW)

    assert not report.eligible_to_start
    assert "unit_exec_start_binding_mismatch" in report.reason_codes


def test_preflight_rejects_canary_from_predecessor_deployment(tmp_path: Path) -> None:
    binding = _fixture(tmp_path)
    manifest_path = Path(binding.deployment_manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["manifest_id"] = "sha256:" + "9" * 64
    _json(manifest_path, manifest)

    report = run_preflight(binding, checked_at=NOW)

    assert not report.eligible_to_start
    assert "canary_deployment_mismatch" in report.reason_codes
    assert "catalog_canary_deployment_mismatch" in report.reason_codes


def test_runtime_overlay_binds_authenticated_canary_to_exact_deployment(
    tmp_path: Path,
) -> None:
    binding = _fixture(tmp_path)
    registry = json.loads(Path(binding.registry_path).read_text(encoding="utf-8"))
    registry["records"][0]["contours"][0]["runtime_identity"]["source_revision"] = (
        "a" * 40
    )
    deployment_path = Path(binding.deployment_manifest_path)
    deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
    deployment["record_ref"] = (
        "Logs/mcp/deployments/records/"
        + deployment["manifest_id"].removeprefix("sha256:")
        + ".json"
    )
    target = RuntimeTarget(
        organ_id=binding.organ_id,
        registry_organ_id=binding.organ_id,
        service_id=binding.service_id,
        unit_name=binding.unit_name,
        executable_ref=binding.executable_path,
        endpoint_ref=binding.endpoint_ref,
        protocol_versions=(binding.protocol_version,),
        effect_classes=("observe",),
        canary_route="runbook://demo/read",
        canary_contract=RuntimeCanaryContract(
            tool_name="demo_read",
            arguments={},
            schema_pointer="/schema_version",
            schema_value="demo-v1",
            required_pointers=("/value",),
        ),
        rollback_route="runbook://demo/rollback/read",
    )

    def process_runner(command: tuple[str, ...]) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "LoadState=loaded\n"
                "ActiveState=active\n"
                "MainPID=321\n"
                "ExecMainStartTimestampMonotonic=654\n"
                "FragmentPath=/tmp/demo.service\n"
            ),
        )

    overlay, skipped = build_runtime_overlay(
        registry,
        deployment,
        RuntimeTargetCatalog(targets=(target,)),
        canary_root=Path(binding.canary_receipt_path).parent,
        canary_public_key_path=Path(binding.canary_public_key_path),
        deployment_manifest_path=deployment_path,
        generated_at=NOW,
        systemctl_runner=process_runner,
        deployment_loader=lambda path: (deployment, deployment["manifest_id"]),
    )

    assert skipped == ()
    assert overlay["contours"][0]["canary_evidence"]["receipt_id"] == (
        binding.canary_receipt_id
    )
    runtime_identity = overlay["contours"][0]["runtime_identity"]
    assert runtime_identity["deployment_manifest_ref"] == deployment["record_ref"]
    assert runtime_identity["process_identity"] == (
        f"systemd-user:{binding.unit_name}:pid:321:start:654"
    )

    deployment["services"][0]["package_digest"] = "sha256:" + "8" * 64
    with pytest.raises(PreflightError, match="canary deployment package"):
        build_runtime_overlay(
            registry,
            deployment,
            RuntimeTargetCatalog(targets=(target,)),
            canary_root=Path(binding.canary_receipt_path).parent,
            canary_public_key_path=Path(binding.canary_public_key_path),
            deployment_manifest_path=deployment_path,
            generated_at=NOW,
            systemctl_runner=process_runner,
            deployment_loader=lambda path: (deployment, deployment["manifest_id"]),
        )

    verified_deployment = json.loads(json.dumps(deployment))
    verified_deployment["record_ref"] = "different-immutable-record.json"
    with pytest.raises(PreflightError, match="verified manifest"):
        build_runtime_overlay(
            registry,
            deployment,
            RuntimeTargetCatalog(targets=(target,)),
            canary_root=Path(binding.canary_receipt_path).parent,
            canary_public_key_path=Path(binding.canary_public_key_path),
            deployment_manifest_path=deployment_path,
            generated_at=NOW,
            systemctl_runner=process_runner,
            deployment_loader=lambda path: (
                verified_deployment,
                verified_deployment["manifest_id"],
            ),
        )


def test_runtime_overlay_rejects_unobserved_managed_process(tmp_path: Path) -> None:
    binding = _fixture(tmp_path)
    registry = json.loads(Path(binding.registry_path).read_text(encoding="utf-8"))
    deployment_path = Path(binding.deployment_manifest_path)
    deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
    deployment["record_ref"] = (
        "Logs/mcp/deployments/records/"
        + deployment["manifest_id"].removeprefix("sha256:")
        + ".json"
    )
    target = RuntimeTarget(
        organ_id=binding.organ_id,
        registry_organ_id=binding.organ_id,
        service_id=binding.service_id,
        unit_name=binding.unit_name,
        executable_ref=binding.executable_path,
        endpoint_ref=binding.endpoint_ref,
        protocol_versions=(binding.protocol_version,),
        effect_classes=("observe",),
        canary_route="runbook://demo/read",
        canary_contract=RuntimeCanaryContract(
            tool_name="demo_read",
            arguments={},
            schema_pointer="/schema_version",
            schema_value="demo-v1",
            required_pointers=("/value",),
        ),
        rollback_route="runbook://demo/rollback/read",
    )

    def inactive_runner(command: tuple[str, ...]) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "LoadState=loaded\n"
                "ActiveState=inactive\n"
                "MainPID=0\n"
                "ExecMainStartTimestampMonotonic=0\n"
                "FragmentPath=/tmp/demo.service\n"
            ),
        )

    with pytest.raises(PreflightError, match="managed process identity is not exact"):
        build_runtime_overlay(
            registry,
            deployment,
            RuntimeTargetCatalog(targets=(target,)),
            canary_root=Path(binding.canary_receipt_path).parent,
            canary_public_key_path=Path(binding.canary_public_key_path),
            deployment_manifest_path=deployment_path,
            generated_at=NOW,
            systemctl_runner=inactive_runner,
            deployment_loader=lambda path: (deployment, deployment["manifest_id"]),
        )


@pytest.mark.parametrize(
    "recovery_unit",
    (
        "aoa-organ-mcp-read-bootstrap@demo.service",
        "aoa-organ-mcp-read-fallback@demo.service",
    ),
)
def test_recovery_canary_builds_preflight_catalog_before_production_start(
    tmp_path: Path,
    recovery_unit: str,
) -> None:
    recovery_identity = f"systemd-user:{recovery_unit}:pid:777:start:888"
    binding = _fixture(
        tmp_path,
        receipt_process_unit_name=recovery_unit,
        receipt_process_identity=recovery_identity,
    )
    assert run_preflight(binding, checked_at=NOW).eligible_to_start
    registry = json.loads(Path(binding.registry_path).read_text(encoding="utf-8"))
    registry["records"][0]["contours"][0]["runtime_identity"]["source_revision"] = (
        "a" * 40
    )
    deployment_path = Path(binding.deployment_manifest_path)
    deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
    deployment["record_ref"] = (
        "Logs/mcp/deployments/records/"
        + deployment["manifest_id"].removeprefix("sha256:")
        + ".json"
    )
    target = RuntimeTarget(
        organ_id=binding.organ_id,
        registry_organ_id=binding.organ_id,
        service_id=binding.service_id,
        unit_name=binding.unit_name,
        executable_ref=binding.executable_path,
        endpoint_ref=binding.endpoint_ref,
        protocol_versions=(binding.protocol_version,),
        effect_classes=("observe",),
        canary_route="runbook://demo/read",
        rollback_route="runbook://demo/rollback/read",
    )

    def recovery_runner(command: tuple[str, ...]) -> SimpleNamespace:
        assert recovery_unit in command
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "LoadState=loaded\nActiveState=active\nMainPID=777\n"
                "ExecMainStartTimestampMonotonic=888\n"
                "FragmentPath=/tmp/demo-recovery.service\n"
            ),
        )

    overlay, skipped = build_runtime_overlay(
        registry,
        deployment,
        RuntimeTargetCatalog(targets=(target,)),
        canary_root=Path(binding.canary_receipt_path).parent,
        canary_public_key_path=Path(binding.canary_public_key_path),
        deployment_manifest_path=deployment_path,
        generated_at=NOW,
        systemctl_runner=recovery_runner,
        deployment_loader=lambda path: (deployment, deployment["manifest_id"]),
    )

    assert skipped == ()
    assert overlay["contours"][0]["runtime_identity"]["process_identity"] == (
        recovery_identity
    )


def test_recovery_preflight_rejects_stale_fallback_template(tmp_path: Path) -> None:
    fallback_unit = "aoa-organ-mcp-read-fallback@demo.service"
    binding = _fixture(
        tmp_path,
        receipt_process_unit_name=fallback_unit,
        receipt_process_identity=(
            f"systemd-user:{fallback_unit}:pid:777:start:888"
        ),
    )
    fallback_template = tmp_path / "systemd/aoa-organ-mcp-read-fallback@.service"
    _write(
        fallback_template,
        "[Service]\n"
        "Environment=AOA_MCP_POLICY_FAMILY=read\n"
        f"LoadCredential=demo:{binding.credential_path}\n"
        "ExecStart=/tmp/stale-unserialized-server\n",
    )
    recovery_binding = binding.model_copy(
        update={
            "unit_path": str(fallback_template),
            "canary_process_unit_name": fallback_unit,
        }
    )

    report = run_preflight(recovery_binding, checked_at=NOW)

    assert not report.eligible_to_start
    assert "unit_exec_start_binding_mismatch" in report.reason_codes


def test_runtime_overlay_rejects_canary_from_predecessor_process(
    tmp_path: Path,
) -> None:
    binding = _fixture(tmp_path)
    registry = json.loads(Path(binding.registry_path).read_text(encoding="utf-8"))
    registry["records"][0]["contours"][0]["runtime_identity"]["source_revision"] = (
        "a" * 40
    )
    deployment_path = Path(binding.deployment_manifest_path)
    deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
    deployment["record_ref"] = (
        "Logs/mcp/deployments/records/"
        + deployment["manifest_id"].removeprefix("sha256:")
        + ".json"
    )
    target = RuntimeTarget(
        organ_id=binding.organ_id,
        registry_organ_id=binding.organ_id,
        service_id=binding.service_id,
        unit_name=binding.unit_name,
        executable_ref=binding.executable_path,
        endpoint_ref=binding.endpoint_ref,
        protocol_versions=(binding.protocol_version,),
        effect_classes=("observe",),
        canary_route="runbook://demo/read",
        rollback_route="runbook://demo/rollback/read",
    )

    def replacement_process(command: tuple[str, ...]) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "LoadState=loaded\nActiveState=active\nMainPID=322\n"
                "ExecMainStartTimestampMonotonic=655\n"
                "FragmentPath=/tmp/demo.service\n"
            ),
        )

    with pytest.raises(PreflightError, match="canary process identity"):
        build_runtime_overlay(
            registry,
            deployment,
            RuntimeTargetCatalog(targets=(target,)),
            canary_root=Path(binding.canary_receipt_path).parent,
            canary_public_key_path=Path(binding.canary_public_key_path),
            deployment_manifest_path=deployment_path,
            generated_at=NOW,
            systemctl_runner=replacement_process,
            deployment_loader=lambda path: (deployment, deployment["manifest_id"]),
        )


def test_runtime_overlay_skips_malformed_sibling_canary(tmp_path: Path) -> None:
    binding = _fixture(tmp_path)
    registry = json.loads(Path(binding.registry_path).read_text(encoding="utf-8"))
    registry["records"][0]["contours"][0]["runtime_identity"]["source_revision"] = (
        "a" * 40
    )
    deployment_path = Path(binding.deployment_manifest_path)
    deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
    deployment["record_ref"] = (
        "Logs/mcp/deployments/records/"
        + deployment["manifest_id"].removeprefix("sha256:")
        + ".json"
    )
    base = RuntimeTarget(
        organ_id=binding.organ_id,
        registry_organ_id=binding.organ_id,
        service_id=binding.service_id,
        unit_name=binding.unit_name,
        executable_ref=binding.executable_path,
        endpoint_ref=binding.endpoint_ref,
        protocol_versions=(binding.protocol_version,),
        effect_classes=("observe",),
        canary_route="runbook://demo/read",
        rollback_route="runbook://demo/rollback/read",
    )
    sibling = base.model_copy(
        update={
            "organ_id": "broken-organ",
            "registry_organ_id": "broken-organ",
            "service_id": "broken-mcp",
            "unit_name": "broken.service",
            "endpoint_ref": "http://127.0.0.1:5998/mcp",
        }
    )
    sibling_contour = json.loads(json.dumps(registry["records"][0]))
    sibling_contour["organ_id"] = "broken-organ"
    registry["records"].append(sibling_contour)
    malformed = Path(binding.canary_receipt_path).parent / "broken-organ.read.json"
    _write(malformed, "{truncated")

    def process_runner(command: tuple[str, ...]) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "LoadState=loaded\nActiveState=active\nMainPID=321\n"
                "ExecMainStartTimestampMonotonic=654\nFragmentPath=/tmp/demo.service\n"
            ),
        )

    overlay, skipped = build_runtime_overlay(
        registry,
        deployment,
        RuntimeTargetCatalog(targets=(base, sibling)),
        canary_root=Path(binding.canary_receipt_path).parent,
        canary_public_key_path=Path(binding.canary_public_key_path),
        deployment_manifest_path=deployment_path,
        generated_at=NOW,
        systemctl_runner=process_runner,
        deployment_loader=lambda path: (deployment, deployment["manifest_id"]),
    )

    assert len(overlay["contours"]) == 1
    assert skipped == (
        {
            "organ_id": "broken-organ",
            "contour_id": "read",
            "reason_code": "canary_evidence_invalid_or_expired",
        },
    )


def test_preflight_sweep_persists_bounded_status_and_detects_change(
    tmp_path: Path,
) -> None:
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
                unit_exec_start_binding=binding.unit_exec_start_binding,
                canary_receipt_path=binding.canary_receipt_path,
                canary_receipt_id=binding.canary_receipt_id,
                canary_process_unit_name=binding.canary_process_unit_name,
                canary_observed_at=binding.canary_observed_at,
                canary_expires_at=binding.canary_expires_at,
                canary_deployment_manifest_id=(binding.canary_deployment_manifest_id),
                canary_public_key_path=binding.canary_public_key_path,
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


def test_keeper_inbox_imports_once_and_reuses_unchanged_owner_evidence(
    tmp_path: Path,
) -> None:
    from aoa_sdk.contracts.admission_keeper import (
        AdmissionEvidenceNodeStatement,
        AdmissionKeeperSpec,
        KeeperStageSpec,
    )
    from aoa_sdk.contracts.control_plane import canonical_digest
    from aoa_sdk.contracts.organs import QualifiedEvidenceRef
    from aoa_sdk.organs import materialize_evidence_node, materialize_keeper_spec

    stages = (
        KeeperStageSpec(
            stage="owner_source",
            owner="demo-organ",
            validator_ref="owner://demo-organ/source-validator",
            validator_revision="source-v1",
            validator_schema_digest="sha256:" + "1" * 64,
            subject_digest="sha256:" + "2" * 64,
            maximum_age_seconds=300,
            cost_weight=5,
        ),
        KeeperStageSpec(
            stage="package",
            owner="abyss-stack",
            validator_ref="owner://abyss-stack/package-validator",
            validator_revision="package-v1",
            validator_schema_digest="sha256:" + "3" * 64,
            subject_digest="sha256:" + "4" * 64,
            dependency_stages=("owner_source",),
            maximum_age_seconds=300,
            cost_weight=10,
        ),
    )
    spec = materialize_keeper_spec(
        AdmissionKeeperSpec(
            spec_id="sha256:" + "0" * 64,
            organ_id="demo-organ",
            contour_id="read",
            transaction_ref="owner://operator/admission/demo-read",
            registry_anchor_digest="sha256:" + "5" * 64,
            target_record_digest="sha256:" + "6" * 64,
            authored_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=30),
            stages=stages,
        )
    )
    nodes = []
    for stage in stages:
        dependencies = () if not nodes else (nodes[-1].node_id,)
        statement = AdmissionEvidenceNodeStatement(
            spec_id=spec.spec_id,
            organ_id=spec.organ_id,
            contour_id=spec.contour_id,
            stage=stage.stage,
            stage_spec_digest=canonical_digest(stage),
            dependency_node_ids=dependencies,
            owner=stage.owner,
            subject_digest=stage.subject_digest,
            receipt=QualifiedEvidenceRef(
                owner=stage.owner,
                evidence_ref=f"owner://{stage.owner}/receipt/{stage.stage}",
                revision=f"{stage.stage}-v1",
                observed_at=NOW - timedelta(seconds=10),
                expires_at=NOW + timedelta(minutes=20),
            ),
            observed_at=NOW - timedelta(seconds=10),
            expires_at=NOW + timedelta(minutes=20),
            outcome="passed",
        )
        nodes.append(materialize_evidence_node(statement, spec, nodes))

    spec_path = tmp_path / "spec.json"
    _json(spec_path, spec.model_dump(mode="json"))
    inbox = tmp_path / "inbox" / "demo-organ" / "read"
    for index, node in enumerate(nodes):
        _json(inbox / f"{index:02d}.json", node.model_dump(mode="json"))
    entry = SimpleNamespace(
        organ_id="demo-organ",
        contour_id="read",
        spec_path=str(spec_path),
    )

    first = _run_keeper_cycles(
        (entry,),
        output_root=tmp_path / "runtime",
        inbox_root=tmp_path / "inbox",
        generated_at=NOW,
    )[0]
    second = _run_keeper_cycles(
        (entry,),
        output_root=tmp_path / "runtime",
        inbox_root=tmp_path / "inbox",
        generated_at=NOW + timedelta(seconds=10),
    )[0]

    assert first.imported_node_count == 2
    assert second.imported_node_count == 0
    assert second.reused_stage_count == 2
    assert second.planned_refresh_cost == 0
    assert second.refresh_cost_avoided == second.full_refresh_cost == 15
    assert second.revision == first.revision + 1


def test_keeper_inbox_rejects_symlink_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(PreflightError, match="non-symlink directory"):
        _keeper_inbox_paths(linked, organ_id="demo", contour_id="read")


def test_keeper_inbox_rejects_symlinked_organ_directory(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    outside = tmp_path / "outside"
    (outside / "read").mkdir(parents=True)
    (inbox / "demo").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PreflightError, match="organ inbox"):
        _keeper_inbox_paths(inbox, organ_id="demo", contour_id="read")


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
