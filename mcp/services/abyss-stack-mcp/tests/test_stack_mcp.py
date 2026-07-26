from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from abyss_stack_mcp.contracts import RuntimeObservation
from abyss_stack_mcp.core import (
    ObservationStore,
    StackMCPApplication,
    StackMCPError,
)
from abyss_stack_mcp.server import _auth_kwargs, _contour, build_server


NOW = datetime(2026, 7, 26, 5, 0, tzinfo=timezone.utc)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64


def evidence(name: str, *, state: str = "exact") -> dict:
    ref = {
        "owner": "abyss-stack",
        "evidence_ref": f"receipt://runtime/{name}",
        "revision": "stack-rev-1",
        "observed_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
    }
    return {
        "state": state,
        "observed_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
        "evidence_refs": [ref] if state == "exact" else [],
        "reason_codes": [] if state == "exact" else ["fixture-drift"],
    }


def subject(
    organ_id: str = "aoa-kag",
    *,
    policy_family: str = "read",
    credential_class: str = "aoa-kag-read",
) -> dict:
    return {
        "organ_id": organ_id,
        "policy_family": policy_family,
        "owners": {
            "source_owner": organ_id,
            "access_owner": organ_id,
            "runtime_owner": "abyss-stack",
            "proof_owner": "aoa-evals",
            "acceptance_owner": organ_id,
        },
        "credential_class": credential_class,
        "effect_classes": (
            ["prepare_candidate"]
            if policy_family == "candidate"
            else ["observe", "derive"]
        ),
        "source": {
            "revision": "source-rev-1",
            "tree_digest": DIGEST_A,
            "evidence": evidence("source"),
        },
        "package": {
            "name": f"{organ_id}-mcp",
            "version": "0.1.0",
            "artifact_digest": DIGEST_B,
            "evidence": evidence("package"),
        },
        "deploy": {
            "revision": "deploy-rev-1",
            "tree_digest": DIGEST_C,
            "manifest_ref": f"receipt://deploy/{organ_id}",
            "deployed_at": NOW.isoformat(),
            "evidence": evidence("deploy"),
        },
        "process": {
            "unit_name": f"aoa-mcp-http@{organ_id}.service",
            "executable_ref": f"/srv/AbyssOS/.codex/bin/{organ_id}-mcp-server.py",
            "process_identity": f"{organ_id}-mcp/0.1.0",
            "active": True,
            "evidence": evidence("process"),
        },
        "endpoint": {
            "transport": "streamable-http",
            "endpoint_ref": "http://127.0.0.1:5425/mcp",
            "protocol_versions": ["2025-11-25"],
            "ready": True,
            "server_schema_digest": DIGEST_D,
            "evidence": evidence("endpoint"),
        },
        "registry": {
            "registry_id": "abyss-private",
            "registry_digest": DIGEST_A,
            "registry_state": "shadow",
            "evidence": evidence("registry"),
        },
        "consumers": [
            {
                "consumer_id": "codex-main",
                "registration_ref": "config://codex/aoa-kag",
                "registered": True,
                "observed_schema_digest": DIGEST_D,
                "observed_protocol_versions": ["2025-11-25"],
                "evidence": evidence("consumer"),
            }
        ],
        "freshness": {
            "state": "exact",
            "provider_watermark": "kag-owner-watermark-1",
            "observed_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
            "evidence_refs": evidence("freshness")["evidence_refs"],
        },
        "canary": {
            "succeeded": True,
            "result_grounded": True,
            "canary_route": f"runbook://canary/{organ_id}",
            "canary_ref": f"receipt://canary/{organ_id}",
            "evidence": evidence("canary"),
        },
        "rollback": {
            "ready": True,
            "rollback_route": f"runbook://rollback/{organ_id}",
            "last_known_good_package_digest": DIGEST_B,
            "proof_ref": f"receipt://rollback/{organ_id}",
            "evidence": evidence("rollback"),
        },
    }


def observation(*subjects: dict) -> dict:
    return {
        "schema_version": "abyss_stack_runtime_observation_v1",
        "provider": "abyss-stack",
        "provider_watermark": "stack-runtime-observation-1",
        "generated_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "contains_secrets": False,
        "subjects": list(subjects or (subject(),)),
    }


def write_observation(path: Path, payload: dict | None = None) -> Path:
    path.write_text(
        json.dumps(payload or observation(subject()), indent=2),
        encoding="utf-8",
    )
    return path


def application(
    tmp_path: Path,
    *,
    policy_family: str = "read",
    payload: dict | None = None,
) -> StackMCPApplication:
    path = write_observation(tmp_path / "observation.json", payload)
    return StackMCPApplication(
        ObservationStore(path),
        policy_family=policy_family,
        clock=lambda: NOW + timedelta(minutes=5),
    )


def test_contract_is_strict_and_policy_effects_are_bounded() -> None:
    payload = observation(subject())
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="extra"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject(policy_family="read", credential_class="read-only"))
    payload["subjects"][0]["effect_classes"] = ["apply_runtime"]
    with pytest.raises(ValidationError, match="exceed"):
        RuntimeObservation.model_validate(payload)


def test_observation_store_rejects_secrets_symlinks_and_oversize(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    payload["subjects"][0]["credential_material"] = "not-allowed"
    path = write_observation(tmp_path / "secret.json", payload)
    with pytest.raises(StackMCPError, match="secret-bearing"):
        ObservationStore(path).load()

    real = write_observation(tmp_path / "real.json")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(StackMCPError, match="regular file"):
        ObservationStore(link).load()

    large = tmp_path / "large.json"
    large.write_text(" " * (2 * 1024 * 1024 + 1), encoding="utf-8")
    with pytest.raises(StackMCPError, match="2 MiB"):
        ObservationStore(large).load()

    payload = observation(subject())
    payload["subjects"][0]["endpoint"]["endpoint_ref"] = (
        "http://user:password@127.0.0.1:5425/mcp"
    )
    with pytest.raises(ValidationError, match="user information"):
        RuntimeObservation.model_validate(payload)


def test_catalog_is_compact_and_does_not_flatten_health(tmp_path: Path) -> None:
    app = application(tmp_path)
    result = app.catalog()
    payload = result["owner_payload"]
    assert payload["schema_bytes_loaded"] == 0
    assert payload["entries"][0]["organ_id"] == "aoa-kag"
    assert "healthy" not in json.dumps(result).lower()
    assert result["metadata"]["execution_authorized"] is False
    assert result["metadata"]["applied_state"] == "not_applied"


def test_inspection_keeps_process_endpoint_freshness_independent(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    payload["subjects"][0]["endpoint"]["ready"] = False
    payload["subjects"][0]["endpoint"]["server_schema_digest"] = None
    payload["subjects"][0]["endpoint"]["evidence"] = evidence(
        "endpoint",
        state="blocked",
    )
    app = application(tmp_path, payload=payload)
    process = app.inspect("aoa-kag", "read", view="process")
    endpoint = app.inspect("aoa-kag", "read", view="endpoint")
    assert process["owner_payload"]["observation"]["active"] is True
    assert endpoint["owner_payload"]["observation"]["ready"] is False
    assert endpoint["owner_payload"]["observation"]["evidence"]["state"] == ("blocked")


def test_read_process_has_no_plan_capability(tmp_path: Path) -> None:
    app = application(tmp_path)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="absent from the read process"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=digest,
        )


def test_candidate_plan_is_content_addressed_and_never_authorized(
    tmp_path: Path,
) -> None:
    app = application(tmp_path, policy_family="candidate")
    _, digest = app.store.load()
    first = app.prepare_plan(
        "aoa-kag",
        "read",
        "restart",
        expected_observation_digest=digest,
    )
    second = app.prepare_plan(
        "aoa-kag",
        "read",
        "restart",
        expected_observation_digest=digest,
    )
    assert first == second
    plan = first["owner_payload"]["plan"]
    assert plan["execution_authorized"] is False
    assert plan["approval_required_before_execution"] is True
    assert plan["exact_unit_name"] == "aoa-mcp-http@aoa-kag.service"
    assert [step["order"] for step in plan["steps"]] == [1, 2, 3]
    evidence_refs = {
        item["evidence_ref"] for item in plan["precondition_evidence"]
    }
    assert "receipt://runtime/consumer" in evidence_refs
    assert "receipt://runtime/freshness" in evidence_refs


def test_candidate_plan_denies_drift_expiry_and_unproven_rollback(
    tmp_path: Path,
) -> None:
    app = application(tmp_path, policy_family="candidate")
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="digest drift"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=DIGEST_A,
        )

    payload = observation(subject())
    source_evidence = payload["subjects"][0]["source"]["evidence"]
    source_evidence["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    source_evidence["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    app = application(
        tmp_path,
        policy_family="candidate",
        payload=payload,
    )
    catalog = app.catalog()
    assert catalog["owner_payload"]["entries"][0]["link_states"]["source"] == (
        "stale_readable"
    )
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="source_identity_not_usable"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=digest,
        )

    payload = observation(subject())
    payload["subjects"][0]["rollback"]["ready"] = False
    payload["subjects"][0]["rollback"]["last_known_good_package_digest"] = None
    payload["subjects"][0]["rollback"]["proof_ref"] = None
    payload["subjects"][0]["rollback"]["evidence"] = evidence(
        "rollback",
        state="unknown",
    )
    app = application(
        tmp_path,
        policy_family="candidate",
        payload=payload,
    )
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="rollback_not_proven"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "rollback",
            expected_observation_digest=digest,
        )

    payload = observation(subject())
    payload["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    app = application(
        tmp_path,
        policy_family="candidate",
        payload=payload,
    )
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="expired runtime observation"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=digest,
        )


def test_read_and_candidate_servers_expose_disjoint_tools(tmp_path: Path) -> None:
    path = write_observation(tmp_path / "observation.json")
    read = build_server(path, policy_family="read")
    candidate = build_server(path, policy_family="candidate")
    read_tools = {tool.name for tool in asyncio.run(read.list_tools())}
    candidate_tools = {tool.name for tool in asyncio.run(candidate.list_tools())}
    assert read_tools == {"stack_runtime_catalog", "stack_runtime_inspect"}
    assert candidate_tools == {"stack_prepare_runtime_plan"}


def test_policy_contours_use_distinct_ports_credentials_and_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _contour("read") == (
        5431,
        "ABYSS_STACK_MCP_READ_BEARER_TOKEN",
        "abyss-stack-mcp-read-bearer-token",
        "abyss-stack-mcp:read",
    )
    assert _contour("candidate") == (
        5432,
        "ABYSS_STACK_MCP_CANDIDATE_BEARER_TOKEN",
        "abyss-stack-mcp-candidate-bearer-token",
        "abyss-stack-mcp:candidate",
    )
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / "aoa-mcp-http-bearer-token").write_text(
        "a" * 64,
        encoding="utf-8",
    )
    monkeypatch.setenv("AOA_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials))
    monkeypatch.delenv("ABYSS_STACK_MCP_READ_BEARER_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="abyss-stack-mcp-read-bearer-token"):
        _auth_kwargs("read")

    (credentials / "abyss-stack-mcp-read-bearer-token").write_text(
        "r" * 64,
        encoding="utf-8",
    )
    assert "auth" in _auth_kwargs("read")
    with pytest.raises(
        SystemExit,
        match="abyss-stack-mcp-candidate-bearer-token",
    ):
        _auth_kwargs("candidate")

    (credentials / "abyss-stack-mcp-candidate-bearer-token").write_text(
        "c" * 64,
        encoding="utf-8",
    )
    assert "auth" in _auth_kwargs("candidate")
