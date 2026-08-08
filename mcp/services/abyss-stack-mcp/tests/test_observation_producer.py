from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from abyss_stack_mcp.core import ObservationStore
from abyss_stack_mcp.observation import (
    ObservationProducerError,
    RuntimeTargetCatalog,
    _load_targets,
    _packaged_targets_path,
    _registry_declares_target,
    produce_observation,
)


NOW = datetime(2026, 7, 28, 14, 0, tzinfo=timezone.utc)
STACK_REVISION = "8bcfe0edf7ad499d666207ca2087d8db9df4d7a9"
OWNER_REVISION = "0ff913279868735b41a17aab84c0c89341d7cb77"
PACKAGE_DIGEST = "sha256:" + ("a" * 64)
SCHEMA_DIGEST = "sha256:" + ("d" * 64)


def canonical_digest(value: object) -> str:
    content = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(content).hexdigest()


def write_json(path: Path, value: object, *, mode: int = 0o640) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(mode)
    return path


def test_packaged_target_catalog_uses_physical_venv_path(tmp_path: Path) -> None:
    package = tmp_path / "lib" / "python3.14" / "site-packages" / "abyss_stack_mcp"
    module = package / "observation.py"
    module.parent.mkdir(parents=True)
    module.write_text("# installed module\n", encoding="utf-8")
    catalog = write_json(package / "runtime-targets.v1.json", target_catalog())
    (tmp_path / "lib64").symlink_to("lib", target_is_directory=True)

    derived = _packaged_targets_path(
        tmp_path
        / "lib64"
        / "python3.14"
        / "site-packages"
        / "abyss_stack_mcp"
        / "observation.py"
    )

    assert derived == catalog
    assert not any(
        component.is_symlink()
        for component in tuple(reversed(derived.parents)) + (derived,)
    )
    loaded, _ = _load_targets(derived)
    assert loaded.targets[0].organ_id == "aoa-kag"


def target_catalog() -> dict:
    return {
        "schema_version": "abyss_stack_runtime_targets_v1",
        "targets": [
            {
                "organ_id": "aoa-kag",
                "registry_organ_id": "aoa-kag",
                "service_id": "aoa-kag-mcp",
                "policy_family": "read",
                "unit_name": "aoa-organ-mcp-read@aoa-kag.service",
                "executable_ref": ("/srv/AbyssOS/.codex/bin/aoa-kag-mcp-server.py"),
                "endpoint_ref": "http://127.0.0.1:5425/mcp",
                "protocol_versions": ["2025-11-25"],
                "effect_classes": ["observe"],
                "canary_route": "runbook://mcp-canary/aoa-kag/read",
                "rollback_route": "runbook://mcp-rollback/aoa-kag/read",
            }
        ],
    }


def deployment_manifest() -> dict:
    body = {
        "schema_version": "abyss_stack_mcp_deployment_manifest_v1",
        "digest_scope": "abyss_stack_mcp_deployment_body_v1",
        "provider": "abyss-stack",
        "deployed_at": "2026-07-28T13:55:00Z",
        "contains_secrets": False,
        "source": {
            "owner": "abyss-stack",
            "revision": STACK_REVISION,
            "path": "mcp/services",
            "tree_digest": PACKAGE_DIGEST,
            "file_count": 1,
            "byte_count": 1,
        },
        "deployment": {
            "runtime_owner": "abyss-stack",
            "path": "Configs/mcp/services",
            "sync_delete_mode": False,
            "tree_digest": PACKAGE_DIGEST,
            "file_count": 1,
            "byte_count": 1,
        },
        "services": [
            {
                "service_id": "aoa-kag-mcp",
                "package_name": "aoa-kag-mcp",
                "package_version": "0.1.0",
                "package_source_revision": STACK_REVISION,
                "package_digest": PACKAGE_DIGEST,
                "package_artifact_kind": "source_projection",
                "source_path": "mcp/services/aoa-kag-mcp",
                "deployed_path": "Configs/mcp/services/aoa-kag-mcp",
                "source_tree": {
                    "tree_digest": PACKAGE_DIGEST,
                    "file_count": 1,
                    "byte_count": 1,
                },
                "deployed_tree": {
                    "tree_digest": PACKAGE_DIGEST,
                    "file_count": 1,
                    "byte_count": 1,
                },
                "parity_state": "exact",
                "dependency_lock_digest": None,
                "server_entrypoints": {"aoa-kag-mcp-server": "aoa_kag_mcp.server:main"},
            }
        ],
        "parity_state": "exact",
        "runtime_observation_state": "not_observed",
        "claim_limit": "fixture exact package/deploy parity only",
    }
    manifest_id = canonical_digest(body)
    record_name = manifest_id.removeprefix("sha256:") + ".json"
    return {
        **body,
        "manifest_id": manifest_id,
        "record_ref": f"Logs/mcp/deployments/records/{record_name}",
        "latest_ref": "Logs/mcp/deployments/latest.json",
    }


def registry() -> dict:
    expiry = NOW + timedelta(hours=2)
    return {
        "schema_version": "aoa_organ_registry_source_v1",
        "registry_id": "os-abyss-test-shadow",
        "workspace_owner": "os-abyss",
        "authored_at": NOW.isoformat(),
        "expires_at": expiry.isoformat(),
        "contains_secrets": False,
        "default_admission": "deny",
        "owner_decision_refs": ["decision://ABYSS-STACK-D-0087"],
        "records": [
            {
                "organ_id": "aoa-kag",
                "registry_state": "shadow",
                "owners": {
                    "source_owner": "aoa-kag",
                    "access_owner": "aoa-kag",
                    "runtime_owner": "abyss-stack",
                    "proof_owner": "aoa-evals",
                    "acceptance_owner": "aoa-kag",
                    "control_owner": "aoa-sdk",
                },
                "credential_contours": {
                    "read": "kag-read",
                    "candidate": None,
                    "internal_effect": None,
                    "external_effect": None,
                },
                "revisions": {
                    "source": {
                        "revision": OWNER_REVISION,
                        "digest": None,
                        "schema_digest": None,
                    }
                },
                "maturity": {
                    "declared": {
                        "state": "asserted",
                        "freshness_policy": "fixture",
                        "evidence": {
                            "owner": "aoa-kag",
                            "evidence_ref": "owner://aoa-kag/decision/test",
                            "revision": OWNER_REVISION,
                            "observed_at": NOW.isoformat(),
                            "expires_at": expiry.isoformat(),
                        },
                    }
                },
            }
        ],
    }


def registry_v2() -> dict:
    source = registry()
    record = source["records"][0]
    source["schema_version"] = "aoa_organ_registry_source_v2"
    source["records"] = [
        {
            "organ_id": record["organ_id"],
            "owners": record["owners"],
            "contours": [
                {
                    "contour_id": "read",
                    "policy_family": "read",
                    "credential_class": "kag-read-v2",
                    "registry_state": "shadow",
                    "revisions": record["revisions"],
                    "maturity": record["maturity"],
                }
            ],
        }
    ]
    return source


def write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest = deployment_manifest()
    deployment_root = tmp_path / "deployments"
    latest = write_json(deployment_root / "latest.json", manifest)
    record = deployment_root / "records" / Path(manifest["record_ref"]).name
    write_json(record, manifest)
    registry_path = write_json(tmp_path / "registry.json", registry())
    targets_path = write_json(tmp_path / "targets.json", target_catalog())
    return latest, registry_path, targets_path


def write_v2_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    latest, _, targets_path = write_inputs(tmp_path)
    registry_path = write_json(tmp_path / "registry-v2.json", registry_v2())
    return latest, registry_path, targets_path


def active_systemd(
    command: tuple[str, ...],
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        command,
        0,
        "\n".join(
            (
                "LoadState=loaded",
                "ActiveState=active",
                "MainPID=1234",
                "ExecMainStartTimestampMonotonic=987654",
                (
                    "FragmentPath=/home/test/.config/systemd/user/"
                    "aoa-organ-mcp-read@.service"
                ),
            )
        )
        + "\n",
        "",
    )


def inactive_systemd(
    command: tuple[str, ...],
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        command,
        0,
        "\n".join(
            (
                "LoadState=loaded",
                "ActiveState=inactive",
                "MainPID=0",
                "ExecMainStartTimestampMonotonic=0",
                (
                    "FragmentPath=/home/test/.config/systemd/user/"
                    "aoa-organ-mcp-read@.service"
                ),
            )
        )
        + "\n",
        "",
    )


def test_producer_composes_explicit_live_axes_and_preserves_unknowns(
    tmp_path: Path,
) -> None:
    latest, registry_path, targets_path = write_inputs(tmp_path)
    output = tmp_path / "observations" / "current.json"
    output.parent.mkdir(mode=0o700)

    observation, digest = produce_observation(
        deployment_manifest_path=latest,
        registry_path=registry_path,
        output_path=output,
        targets_path=targets_path,
        overlay_path=tmp_path / "missing-overlay.json",
        clock=lambda: NOW,
        systemctl_runner=active_systemd,
    )

    assert len(observation.subjects) == 1
    subject = observation.subjects[0]
    assert subject.source.revision == OWNER_REVISION
    assert subject.source.evidence.state == "unknown"
    assert subject.package.source_revision == STACK_REVISION
    assert subject.package.evidence.state == "exact"
    assert subject.deploy.evidence.state == "exact"
    assert subject.process.active is True
    assert subject.process.process_identity == (
        "systemd-user:aoa-organ-mcp-read@aoa-kag.service:pid:1234:start:987654"
    )
    assert subject.endpoint.ready is False
    assert subject.endpoint.evidence.reason_codes == ("server-schema-unobserved",)
    assert subject.consumers == ()
    assert subject.freshness.state == "unknown"
    assert subject.proof.verdict == "unknown"
    assert subject.acceptance.accepted is False
    assert subject.canary.succeeded is False
    assert subject.rollback.ready is False
    assert "legacy-shared-contours:excluded" in observation.provider_watermark
    assert stat_mode(output) == 0o600
    loaded, loaded_digest = ObservationStore(output).load()
    assert loaded == observation
    assert loaded_digest == digest


def test_producer_accepts_v2_registry_and_binds_exact_contour(
    tmp_path: Path,
) -> None:
    latest, registry_path, targets_path = write_v2_inputs(tmp_path)
    output = tmp_path / "observations" / "current.json"
    output.parent.mkdir(mode=0o700)

    observation, _ = produce_observation(
        deployment_manifest_path=latest,
        registry_path=registry_path,
        output_path=output,
        targets_path=targets_path,
        overlay_path=None,
        clock=lambda: NOW,
        systemctl_runner=active_systemd,
    )

    subject = observation.subjects[0]
    contour = registry_v2()["records"][0]["contours"][0]
    assert subject.credential_class == "kag-read-v2"
    assert subject.source.revision == OWNER_REVISION
    assert subject.registry.registry_state == "shadow"
    assert subject.registry.registry_digest == canonical_digest(contour)
    assert subject.registry.evidence.evidence_refs[0].evidence_ref.startswith(
        "aoa-sdk-registry:os-abyss-test-shadow:aoa-kag:read:"
    )


def test_v2_registry_rejects_ambiguous_contour_identity(tmp_path: Path) -> None:
    latest, registry_path, targets_path = write_v2_inputs(tmp_path)
    payload = registry_v2()
    payload["records"][0]["contours"].append(
        dict(payload["records"][0]["contours"][0])
    )
    write_json(registry_path, payload)
    output = tmp_path / "observations" / "current.json"
    output.parent.mkdir(mode=0o700)

    with pytest.raises(
        ObservationProducerError,
        match="contour identities are ambiguous",
    ):
        produce_observation(
            deployment_manifest_path=latest,
            registry_path=registry_path,
            output_path=output,
            targets_path=targets_path,
            overlay_path=None,
            clock=lambda: NOW,
            systemctl_runner=active_systemd,
        )


def test_v2_registry_omits_runtime_target_without_matching_contour() -> None:
    payload = registry_v2()
    payload["records"][0]["contours"][0]["contour_id"] = "candidate"
    payload["records"][0]["contours"][0]["policy_family"] = "candidate"
    target = RuntimeTargetCatalog.model_validate(target_catalog()).targets[0]

    assert _registry_declares_target(payload, target) is False


def test_inactive_owner_contour_is_an_exact_process_observation(
    tmp_path: Path,
) -> None:
    latest, registry_path, targets_path = write_inputs(tmp_path)
    output = tmp_path / "observations" / "current.json"
    output.parent.mkdir(mode=0o700)

    observation, _ = produce_observation(
        deployment_manifest_path=latest,
        registry_path=registry_path,
        output_path=output,
        targets_path=targets_path,
        overlay_path=None,
        clock=lambda: NOW,
        systemctl_runner=inactive_systemd,
    )

    process = observation.subjects[0].process
    assert process.active is False
    assert process.process_identity is None
    assert process.evidence.state == "exact"
    assert process.evidence.evidence_refs[0].evidence_ref.endswith(":inactive")
    assert observation.subjects[0].endpoint.evidence.reason_codes == (
        "owner-bounded-process-inactive",
    )


def test_exact_owner_issued_overlay_can_add_endpoint_schema(
    tmp_path: Path,
) -> None:
    latest, registry_path, targets_path = write_inputs(tmp_path)
    output = tmp_path / "observations" / "current.json"
    output.parent.mkdir(mode=0o700)
    overlay = {
        "schema_version": "abyss_stack_runtime_evidence_overlay_v1",
        "generated_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
        "contains_secrets": False,
        "subjects": [
            {
                "organ_id": "aoa-kag",
                "policy_family": "read",
                "endpoint": {
                    "transport": "streamable-http",
                    "endpoint_ref": "http://127.0.0.1:5425/mcp",
                    "protocol_versions": ["2025-11-25"],
                    "ready": True,
                    "server_schema_digest": SCHEMA_DIGEST,
                    "evidence": {
                        "state": "exact",
                        "observed_at": NOW.isoformat(),
                        "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
                        "evidence_refs": [
                            {
                                "owner": "abyss-stack",
                                "evidence_ref": (
                                    "receipt://mcp-canary/aoa-kag/endpoint"
                                ),
                                "revision": STACK_REVISION,
                                "observed_at": NOW.isoformat(),
                                "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
                            }
                        ],
                        "reason_codes": [],
                    },
                },
            }
        ],
    }
    overlay_path = write_json(tmp_path / "overlay.json", overlay)

    observation, _ = produce_observation(
        deployment_manifest_path=latest,
        registry_path=registry_path,
        output_path=output,
        targets_path=targets_path,
        overlay_path=overlay_path,
        clock=lambda: NOW,
        systemctl_runner=active_systemd,
    )

    endpoint = observation.subjects[0].endpoint
    assert endpoint.ready is True
    assert endpoint.server_schema_digest == SCHEMA_DIGEST
    assert endpoint.evidence.state == "exact"


def test_overlay_cannot_self_issue_usable_endpoint_evidence(
    tmp_path: Path,
) -> None:
    latest, registry_path, targets_path = write_inputs(tmp_path)
    output = tmp_path / "observations" / "current.json"
    output.parent.mkdir(mode=0o700)
    overlay = {
        "schema_version": "abyss_stack_runtime_evidence_overlay_v1",
        "generated_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
        "contains_secrets": False,
        "subjects": [
            {
                "organ_id": "aoa-kag",
                "endpoint": {
                    "transport": "streamable-http",
                    "endpoint_ref": "http://127.0.0.1:5425/mcp",
                    "protocol_versions": ["2025-11-25"],
                    "ready": True,
                    "server_schema_digest": SCHEMA_DIGEST,
                    "evidence": {
                        "state": "exact",
                        "observed_at": NOW.isoformat(),
                        "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
                        "evidence_refs": [
                            {
                                "owner": "aoa-kag",
                                "evidence_ref": (
                                    "receipt://mcp-canary/aoa-kag/endpoint"
                                ),
                                "revision": OWNER_REVISION,
                                "observed_at": NOW.isoformat(),
                                "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
                            }
                        ],
                        "reason_codes": [],
                    },
                },
            }
        ],
    }
    overlay_path = write_json(tmp_path / "overlay.json", overlay)

    with pytest.raises(
        ObservationProducerError,
        match="issuing owner",
    ):
        produce_observation(
            deployment_manifest_path=latest,
            registry_path=registry_path,
            output_path=output,
            targets_path=targets_path,
            overlay_path=overlay_path,
            clock=lambda: NOW,
            systemctl_runner=active_systemd,
        )
    assert not output.exists()


def test_successful_canary_requires_runtime_and_owner_grounding_issuers(
    tmp_path: Path,
) -> None:
    latest, registry_path, targets_path = write_inputs(tmp_path)
    output = tmp_path / "observations" / "current.json"
    output.parent.mkdir(mode=0o700)
    runtime_ref = {
        "owner": "abyss-stack",
        "evidence_ref": "receipt://mcp-canary/aoa-kag/call",
        "revision": STACK_REVISION,
        "observed_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
    }
    owner_ref = {
        "owner": "aoa-kag",
        "evidence_ref": "receipt://aoa-kag/grounding-review",
        "revision": OWNER_REVISION,
        "observed_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
    }

    def overlay(refs: list[dict]) -> dict:
        return {
            "schema_version": "abyss_stack_runtime_evidence_overlay_v1",
            "generated_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
            "contains_secrets": False,
            "subjects": [
                {
                    "organ_id": "aoa-kag",
                    "canary": {
                        "succeeded": True,
                        "result_grounded": True,
                        "canary_route": "runbook://mcp-canary/aoa-kag/read",
                        "canary_ref": owner_ref["evidence_ref"],
                        "evidence": {
                            "state": "exact",
                            "observed_at": NOW.isoformat(),
                            "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
                            "evidence_refs": refs,
                            "reason_codes": [],
                        },
                    },
                }
            ],
        }

    stack_only = write_json(
        tmp_path / "stack-only-overlay.json",
        overlay(
            [
                {
                    **runtime_ref,
                    "evidence_ref": owner_ref["evidence_ref"],
                }
            ]
        ),
    )
    with pytest.raises(
        ObservationProducerError,
        match="canary owner grounding",
    ):
        produce_observation(
            deployment_manifest_path=latest,
            registry_path=registry_path,
            output_path=output,
            targets_path=targets_path,
            overlay_path=stack_only,
            clock=lambda: NOW,
            systemctl_runner=active_systemd,
        )

    complete = write_json(
        tmp_path / "complete-overlay.json",
        overlay([runtime_ref, owner_ref]),
    )
    observation, _ = produce_observation(
        deployment_manifest_path=latest,
        registry_path=registry_path,
        output_path=output,
        targets_path=targets_path,
        overlay_path=complete,
        clock=lambda: NOW,
        systemctl_runner=active_systemd,
    )
    assert observation.subjects[0].canary.succeeded is True


def test_last_known_good_canary_requires_explicit_observation_purpose(
    tmp_path: Path,
) -> None:
    latest, registry_path, targets_path = write_inputs(tmp_path)
    output = tmp_path / "observations" / "current.json"
    output.parent.mkdir(mode=0o700)
    expiry = (NOW + timedelta(minutes=30)).isoformat()
    canary_route = "runbook://mcp-canary/aoa-kag/read/last-known-good"
    overlay_path = write_json(
        tmp_path / "lkg-overlay.json",
        {
            "schema_version": "abyss_stack_runtime_evidence_overlay_v1",
            "generated_at": NOW.isoformat(),
            "expires_at": expiry,
            "contains_secrets": False,
            "subjects": [
                {
                    "organ_id": "aoa-kag",
                    "canary": {
                        "succeeded": True,
                        "result_grounded": True,
                        "canary_route": canary_route,
                        "canary_ref": "receipt://aoa-kag/lkg-grounding-review",
                        "evidence": {
                            "state": "exact",
                            "observed_at": NOW.isoformat(),
                            "expires_at": expiry,
                            "evidence_refs": [
                                {
                                    "owner": "abyss-stack",
                                    "evidence_ref": "receipt://mcp-canary/aoa-kag/lkg",
                                    "revision": STACK_REVISION,
                                    "observed_at": NOW.isoformat(),
                                    "expires_at": expiry,
                                },
                                {
                                    "owner": "aoa-kag",
                                    "evidence_ref": (
                                        "receipt://aoa-kag/lkg-grounding-review"
                                    ),
                                    "revision": OWNER_REVISION,
                                    "observed_at": NOW.isoformat(),
                                    "expires_at": expiry,
                                },
                            ],
                            "reason_codes": [],
                        },
                    },
                }
            ],
        },
    )

    with pytest.raises(
        ObservationProducerError,
        match="changed the committed canary route",
    ):
        produce_observation(
            deployment_manifest_path=latest,
            registry_path=registry_path,
            output_path=output,
            targets_path=targets_path,
            overlay_path=overlay_path,
            clock=lambda: NOW,
            systemctl_runner=active_systemd,
        )

    observation, _ = produce_observation(
        deployment_manifest_path=latest,
        registry_path=registry_path,
        output_path=output,
        targets_path=targets_path,
        overlay_path=overlay_path,
        canary_purpose="last-known-good",
        clock=lambda: NOW,
        systemctl_runner=active_systemd,
    )

    assert observation.subjects[0].canary.canary_route == canary_route
    assert observation.subjects[0].canary.succeeded is True


def test_tampered_latest_manifest_and_symlink_target_fail_closed(
    tmp_path: Path,
) -> None:
    latest, registry_path, targets_path = write_inputs(tmp_path)
    output = tmp_path / "observations" / "current.json"
    output.parent.mkdir(mode=0o700)
    tampered = json.loads(latest.read_text(encoding="utf-8"))
    tampered["services"][0]["package_version"] = "9.9.9"
    write_json(latest, tampered)

    with pytest.raises(
        ObservationProducerError,
        match="content address",
    ):
        produce_observation(
            deployment_manifest_path=latest,
            registry_path=registry_path,
            output_path=output,
            targets_path=targets_path,
            overlay_path=None,
            clock=lambda: NOW,
            systemctl_runner=active_systemd,
        )
    assert not output.exists()

    latest, registry_path, targets_path = write_inputs(tmp_path / "second")
    target_link = tmp_path / "targets-link.json"
    target_link.symlink_to(targets_path)
    with pytest.raises(
        ObservationProducerError,
        match="symlink",
    ):
        produce_observation(
            deployment_manifest_path=latest,
            registry_path=registry_path,
            output_path=output,
            targets_path=target_link,
            overlay_path=None,
            clock=lambda: NOW,
            systemctl_runner=active_systemd,
        )


def test_committed_target_catalog_is_owner_and_contour_distinct() -> None:
    catalog_path = (
        Path(__file__).parents[1]
        / "src"
        / "abyss_stack_mcp"
        / "runtime-targets.v1.json"
    )
    catalog = RuntimeTargetCatalog.model_validate_json(
        catalog_path.read_text(encoding="utf-8")
    )

    assert len(catalog.targets) == 15
    assert catalog.targets[0].organ_id == "aoa-kag"
    assert catalog.targets[1].organ_id == "aoa-stats"
    assert catalog.targets[2].organ_id == "aoa-decisions"
    assert all(target.policy_family == "read" for target in catalog.targets)
    assert len({target.unit_name for target in catalog.targets}) == 15
    assert len({target.endpoint_ref for target in catalog.targets}) == 15


def stat_mode(path: Path) -> int:
    return os.stat(path, follow_symlinks=False).st_mode & 0o777
