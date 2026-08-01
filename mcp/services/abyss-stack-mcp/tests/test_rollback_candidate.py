from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from abyss_stack_mcp.observation import (
    RuntimeCanaryContract,
    RuntimeTarget,
    RuntimeTargetCatalog,
    _digest,
)
from abyss_stack_mcp.rollback_candidate import (
    RollbackCandidateError,
    build_rollback_candidate,
    write_candidate,
)
from test_stack_mcp import NOW, observation, subject


REVISION = "1" * 40
PACKAGE_DIGEST = "sha256:" + "2" * 64


def _write(path: Path, payload: dict, *, mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(mode)
    return path


def _inputs(tmp_path: Path) -> dict[str, Path]:
    executable = tmp_path / "bin" / "aoa-kag-mcp-server.py"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    executable.chmod(0o755)
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    credential = secret_dir / "aoa-kag-mcp-read-bearer-token"
    credential.write_text("private-test-value\n", encoding="utf-8")
    credential.chmod(0o600)

    live = subject()
    live["package"]["artifact_digest"] = PACKAGE_DIGEST
    live["package"]["expected_deploy_tree_digest"] = PACKAGE_DIGEST
    live["package"]["source_revision"] = REVISION
    live["deploy"]["revision"] = REVISION
    live["deploy"]["tree_digest"] = PACKAGE_DIGEST
    live["process"]["executable_ref"] = executable.as_posix()
    live["canary"]["canary_route"] = (
        "runbook://mcp-canary/aoa-kag/read/last-known-good"
    )
    live["canary"]["canary_ref"] = (
        "/private/rollback-canaries/records/aoa-kag/lkg.json"
    )
    live["canary"]["evidence"]["evidence_refs"] = [
        {
            "owner": "abyss-stack",
            "evidence_ref": live["canary"]["canary_ref"],
            "revision": "sha256:" + "3" * 64,
            "observed_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        },
        {
            "owner": "aoa-kag",
            "evidence_ref": "/private/owner-review.json",
            "revision": "sha256:" + "4" * 64,
            "observed_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        },
    ]
    live["process"]["unit_name"] = "aoa-organ-mcp-read@aoa-kag.service"
    record = {
        "organ_id": "aoa-kag",
        "credential_contours": {"read": "kag-read"},
    }
    live["registry"]["registry_digest"] = _digest(record)
    registry_path = _write(
        tmp_path / "registry.json",
        {"records": [record], "contains_secrets": False},
    )

    manifest_body = {
        "schema_version": "abyss_stack_mcp_deployment_manifest_v1",
        "digest_scope": "abyss_stack_mcp_deployment_body_v1",
        "provider": "abyss-stack",
        "deployed_at": NOW.isoformat(),
        "contains_secrets": False,
        "source": {"revision": REVISION},
        "deployment": {},
        "services": [
            {
                "service_id": "aoa-kag-mcp",
                "package_digest": PACKAGE_DIGEST,
                "package_source_revision": REVISION,
                "deployed_path": "Configs/mcp/services/aoa-kag-mcp",
                "source_tree": {
                    "tree_digest": PACKAGE_DIGEST,
                    "file_count": 5,
                    "byte_count": 100,
                },
                "deployed_tree": {
                    "tree_digest": PACKAGE_DIGEST,
                    "file_count": 5,
                    "byte_count": 100,
                },
            }
        ],
        "parity_state": "exact",
        "runtime_observation_state": "not_observed",
        "claim_limit": "bounded deployment fixture",
    }
    manifest_id = _digest(manifest_body)
    record_ref = (
        "Logs/mcp/deployments/records/"
        + manifest_id.removeprefix("sha256:")
        + ".json"
    )
    manifest = {
        **manifest_body,
        "manifest_id": manifest_id,
        "record_ref": record_ref,
        "latest_ref": "Logs/mcp/deployments/latest.json",
    }
    live["deploy"]["manifest_digest"] = manifest_id
    live["deploy"]["manifest_ref"] = record_ref
    live["deploy"]["evidence"]["evidence_refs"] = [
        {
            "owner": "abyss-stack",
            "evidence_ref": record_ref,
            "revision": REVISION,
            "observed_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        }
    ]
    manifest_path = _write(tmp_path / record_ref, manifest, mode=0o640)
    observation_path = _write(tmp_path / "observation.json", observation(live))

    target = RuntimeTarget(
        organ_id="aoa-kag",
        registry_organ_id="aoa-kag",
        service_id="aoa-kag-mcp",
        unit_name="aoa-organ-mcp-read@aoa-kag.service",
        executable_ref=executable.as_posix(),
        endpoint_ref="http://127.0.0.1:5425/mcp",
        protocol_versions=("2025-11-25",),
        effect_classes=("observe",),
        canary_route="runbook://mcp-canary/aoa-kag/read",
        canary_contract=RuntimeCanaryContract(
            tool_name="kag_discover",
            arguments={},
            schema_pointer="/schema_version",
            schema_value="aoa-kag-mcp-capabilities-v1",
            required_pointers=("/owners",),
        ),
        rollback_route="runbook://mcp-rollback/aoa-kag/read",
    )
    targets_path = _write(
        tmp_path / "targets.json",
        RuntimeTargetCatalog(targets=(target,)).model_dump(mode="json"),
        mode=0o640,
    )
    return {
        "observation": observation_path,
        "manifest": manifest_path,
        "registry": registry_path,
        "targets": targets_path,
        "secret_dir": secret_dir,
        "runtime_root": tmp_path,
        "source_root": tmp_path / "source",
    }


def _build(paths: dict[str, Path]) -> dict:
    return build_rollback_candidate(
        observation_path=paths["observation"],
        deployment_record_path=paths["manifest"],
        registry_path=paths["registry"],
        consumer_id="codex-main",
        targets_path=paths["targets"],
        stack_source_root=paths["source_root"],
        stack_runtime_root=paths["runtime_root"],
        secret_dir=paths["secret_dir"],
        clock=lambda: NOW + timedelta(minutes=1),
        git_identity=lambda *_: (PACKAGE_DIGEST, 5, 100),
        deployed_identity=lambda *_: (PACKAGE_DIGEST, 5, 100),
    )


def test_materializes_exact_non_executing_lkg_candidate(tmp_path: Path) -> None:
    candidate = _build(_inputs(tmp_path))
    unsigned = dict(candidate)
    claimed = unsigned.pop("candidate_id")
    output = tmp_path / "out" / "candidate.json"
    output.parent.mkdir(mode=0o700)
    write_candidate(candidate, output)

    assert claimed == _digest(unsigned)
    assert candidate["last_known_good"]["canary_route"].endswith(
        "/last-known-good"
    )
    assert candidate["checks"]["runtime_effect_executed"] is False
    assert candidate["execution_authorized"] is False
    assert candidate["admission_authorized"] is False
    assert output.stat().st_mode & 0o777 == 0o600


def test_rejects_current_canary_as_lkg(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    payload = json.loads(paths["observation"].read_text(encoding="utf-8"))
    payload["subjects"][0]["canary"]["canary_route"] = (
        "runbook://mcp-canary/aoa-kag/read"
    )
    _write(paths["observation"], payload)

    with pytest.raises(RollbackCandidateError, match="distinct grounded LKG"):
        _build(paths)


def test_rejects_manifest_target_drift(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    payload = json.loads(paths["observation"].read_text(encoding="utf-8"))
    payload["subjects"][0]["deploy"]["tree_digest"] = "sha256:" + "9" * 64
    _write(paths["observation"], payload)

    with pytest.raises(RollbackCandidateError, match="differs from the live LKG"):
        _build(paths)
