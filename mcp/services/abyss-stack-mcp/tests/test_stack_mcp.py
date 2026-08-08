from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import ValidationError

from abyss_stack_mcp.canary import validate_result_contract
from abyss_stack_mcp.contracts import RuntimeObservation
from abyss_stack_mcp.cli import main as cli_main
from abyss_stack_mcp.audit import (
    MIN_MAX_BYTES,
    PolicyAuditError,
    PolicyAuditJournal,
)
from abyss_stack_mcp.core import (
    ObservationStore,
    StackMCPApplication,
    StackMCPError,
)
from abyss_stack_mcp.server import (
    APPLICATION_VERSION,
    _auth_kwargs,
    _configured_audit_journal,
    _contour,
    _policy_identity,
    build_server,
)
from abyss_stack_mcp.policy import (
    PolicyDeniedError,
    PolicyIdentity,
    StackPolicySeam,
    ToolPolicy,
)
from abyss_stack_mcp.observation import DEFAULT_TARGETS_PATH, _load_targets


NOW = datetime(2026, 7, 26, 5, 0, tzinfo=timezone.utc)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64
DIGEST_F = "sha256:" + "f" * 64
DIGEST_MANIFEST = "sha256:" + "0" * 64
DIGEST_ROLLBACK_MANIFEST = "sha256:" + "1" * 64


def deployment_manifest_ref(digest: str) -> str:
    return (
        "Logs/mcp/deployments/records/"
        + digest.removeprefix("sha256:")
        + ".json"
    )


def evidence(
    name: str,
    *,
    state: str = "exact",
    owner: str = "abyss-stack",
    evidence_ref: str | None = None,
) -> dict:
    ref = {
        "owner": owner,
        "evidence_ref": evidence_ref or f"receipt://runtime/{name}",
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
    effect_classes = {
        "read": ["observe", "derive"],
        "candidate": ["prepare_candidate"],
        "internal_effect": ["apply_runtime"],
        "external_effect": ["external_emit"],
    }[policy_family]
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
        "effect_classes": effect_classes,
        "source": {
            "revision": "source-rev-1",
            "tree_digest": DIGEST_A,
            "expected_sync_tree_digest": DIGEST_E,
            "evidence": evidence("source"),
        },
        "package": {
            "name": f"{organ_id}-mcp",
            "version": "0.1.0",
            "source_revision": "deploy-rev-1",
            "artifact_digest": DIGEST_B,
            "expected_deploy_tree_digest": DIGEST_F,
            "evidence": evidence("package"),
        },
        "deploy": {
            "revision": "deploy-rev-1",
            "tree_digest": DIGEST_C,
            "manifest_ref": deployment_manifest_ref(DIGEST_MANIFEST),
            "manifest_digest": DIGEST_MANIFEST,
            "deployed_at": NOW.isoformat(),
            "evidence": evidence(
                "deploy",
                evidence_ref=deployment_manifest_ref(DIGEST_MANIFEST),
            ),
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
                "registration_ref": f"config://codex/{organ_id}",
                "registered": True,
                "observed_schema_digest": DIGEST_D,
                "observed_protocol_versions": ["2025-11-25"],
                "evidence": evidence(
                    "consumer",
                    evidence_ref=f"config://codex/{organ_id}",
                ),
            }
        ],
        "freshness": {
            "state": "exact",
            "provider_watermark": "kag-owner-watermark-1",
            "observed_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
            "evidence_refs": evidence("freshness")["evidence_refs"],
        },
        "proof": {
            "verdict": "passed",
            "proof_ref": "receipt://runtime/central-proof",
            "evaluated_at": NOW.isoformat(),
            "proved_source_revision": "source-rev-1",
            "proved_source_tree_digest": DIGEST_A,
            "proved_package_digest": DIGEST_B,
            "proved_deploy_revision": "deploy-rev-1",
            "proved_deploy_tree_digest": DIGEST_C,
            "proved_deploy_manifest_digest": DIGEST_MANIFEST,
            "proved_process_identity": f"{organ_id}-mcp/0.1.0",
            "proved_server_schema_digest": DIGEST_D,
            "proved_consumer_registration_ref": f"config://codex/{organ_id}",
            "proved_canary_route": f"runbook://canary/{organ_id}",
            "proved_canary_ref": "receipt://runtime/canary",
            "evidence": evidence("central-proof", owner="aoa-evals"),
        },
        "acceptance": {
            "accepted": True,
            "acceptance_ref": "receipt://runtime/acceptance",
            "accepted_at": NOW.isoformat(),
            "accepted_source_revision": "source-rev-1",
            "accepted_package_digest": DIGEST_B,
            "evidence": evidence("acceptance", owner=organ_id),
        },
        "canary": {
            "succeeded": True,
            "result_grounded": True,
            "canary_route": f"runbook://canary/{organ_id}",
            "canary_ref": "receipt://runtime/canary",
            "evidence": evidence("canary"),
        },
        "rollback": {
            "ready": True,
            "rollback_route": f"runbook://rollback/{organ_id}",
            "last_known_good_consumer_registration_ref": (
                f"config://codex/{organ_id}"
            ),
            "last_known_good_package_digest": DIGEST_B,
            "last_known_good_deploy_revision": "deploy-rev-0",
            "last_known_good_deploy_tree_digest": DIGEST_C,
            "last_known_good_deploy_manifest_ref": (
                deployment_manifest_ref(DIGEST_ROLLBACK_MANIFEST)
            ),
            "last_known_good_deploy_manifest_digest": (
                DIGEST_ROLLBACK_MANIFEST
            ),
            "last_known_good_unit_name": (
                f"aoa-mcp-http@{organ_id}.service"
            ),
            "last_known_good_credential_class": credential_class,
            "last_known_good_executable_ref": (
                f"/srv/AbyssOS/.codex/bin/{organ_id}-mcp-server.py"
            ),
            "last_known_good_process_identity": f"{organ_id}-mcp/0.0.9",
            "last_known_good_canary_route": (
                f"runbook://canary/{organ_id}/last-known-good"
            ),
            "last_known_good_canary_ref": (
                f"receipt://canary/{organ_id}/last-known-good"
            ),
            "proof_ref": "receipt://runtime/rollback",
            "proved_target": {
                "consumer_registration_ref": f"config://codex/{organ_id}",
                "package_digest": DIGEST_B,
                "deploy_revision": "deploy-rev-0",
                "deploy_tree_digest": DIGEST_C,
                "deploy_manifest_ref": deployment_manifest_ref(
                    DIGEST_ROLLBACK_MANIFEST
                ),
                "deploy_manifest_digest": DIGEST_ROLLBACK_MANIFEST,
                "unit_name": f"aoa-mcp-http@{organ_id}.service",
                "credential_class": credential_class,
                "executable_ref": (
                    f"/srv/AbyssOS/.codex/bin/{organ_id}-mcp-server.py"
                ),
                "process_identity": f"{organ_id}-mcp/0.0.9",
                "canary_route": (
                    f"runbook://canary/{organ_id}/last-known-good"
                ),
                "canary_ref": (
                    f"receipt://canary/{organ_id}/last-known-good"
                ),
            },
            "evidence": evidence("rollback", owner="aoa-evals"),
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


def set_proof_event_time(
    payload: dict,
    event_surface: str,
    event_time: str,
) -> None:
    event = payload["subjects"][0][event_surface]
    event[
        {
            "proof": "evaluated_at",
            "acceptance": "accepted_at",
        }[event_surface]
    ] = event_time
    event["evidence"]["observed_at"] = event_time
    event["evidence"]["evidence_refs"][0]["observed_at"] = event_time


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


def policy_seam(
    *,
    max_in_flight: int = 2,
    rate_limit: int = 10,
    timeout_seconds: float = 1.0,
    max_output_bytes: int = 4096,
    audit_journal: PolicyAuditJournal | None = None,
) -> StackPolicySeam:
    return StackPolicySeam(
        owner="abyss-stack",
        policy_family="read",
        expected_scope="abyss-stack-mcp:read",
        tools=(
            ToolPolicy(
                tool_id="stack_runtime_catalog",
                effect_class="observe",
                max_input_bytes=1024,
                max_output_bytes=max_output_bytes,
                timeout_seconds=timeout_seconds,
                filesystem_access="configured_observation_read",
                network_access="none",
                source_to_sink="runtime_observation_to_typed_result",
            ),
        ),
        max_in_flight=max_in_flight,
        rate_limit=rate_limit,
        rate_window_seconds=60,
        clock=lambda: NOW,
        audit_journal=audit_journal,
    )


def policy_identity(scope: str = "abyss-stack-mcp:read") -> PolicyIdentity:
    return PolicyIdentity(
        identity_id="test-consumer",
        auth_mode="bearer",
        scope=scope,
    )


def test_policy_seam_returns_secret_safe_allow_and_deny_receipts() -> None:
    seam = policy_seam()
    result = asyncio.run(
        seam.invoke(
            request_id="request-allowed",
            identity=policy_identity(),
            tool_id="stack_runtime_catalog",
            arguments={"organ_id": "aoa-kag"},
            dispatch=lambda: {
                "metadata": {"contract_version": "test"},
                "owner_payload": {"entries": []},
            },
        )
    )

    receipt = result["metadata"]["policy_receipt"]
    assert receipt["decision"] == "allowed"
    assert receipt["effect_class"] == "observe"
    assert receipt["network_access"] == "none"
    assert receipt["runtime_effect_authorized"] is False
    assert result["metadata"]["content_trust"] == "untrusted_data"
    assert result["metadata"]["instruction_authority"] == "none"
    assert receipt["input_digest"].startswith("sha256:")
    assert receipt["output_digest"].startswith("sha256:")

    secret_value = "sk-proj-" + "a" * 48
    with pytest.raises(PolicyDeniedError) as caught:
        asyncio.run(
            seam.invoke(
                request_id="request-secret",
                identity=policy_identity(),
                tool_id="stack_runtime_catalog",
                arguments={"query": secret_value},
                dispatch=lambda: {},
            )
        )
    assert caught.value.reason_code == "secret_material_rejected"
    assert caught.value.receipt["decision"] == "denied"
    assert secret_value not in str(caught.value)
    assert secret_value not in json.dumps(caught.value.receipt)


def test_policy_identity_does_not_treat_loopback_as_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AOA_MCP_TRANSPORT", "stdio")
    local_identity = _policy_identity("read")
    assert local_identity.auth_mode == "os_process"
    assert local_identity.scope == "abyss-stack-mcp:read"

    monkeypatch.setenv("AOA_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("AOA_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("AOA_MCP_PORT", "5431")
    unauthenticated = _policy_identity("read")
    assert unauthenticated.identity_id == "unverified-http-caller"
    assert unauthenticated.scope == "invalid"


def test_policy_identity_binds_bearer_scope_resource_and_issuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp.server.auth.middleware import auth_context
    from mcp.server.auth.provider import AccessToken

    monkeypatch.setenv("AOA_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("AOA_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("AOA_MCP_PORT", "5431")
    token = AccessToken(
        token="not-serialized-by-policy",
        client_id="abyss-stack-mcp-read-consumer",
        scopes=["abyss-stack-mcp:read"],
        resource="http://127.0.0.1:5431/mcp",
        subject="local-operator",
        claims={"iss": "http://127.0.0.1:5431/"},
    )
    monkeypatch.setattr(auth_context, "get_access_token", lambda: token)

    identity = _policy_identity("read")
    assert identity == PolicyIdentity(
        identity_id="abyss-stack-mcp-read-consumer",
        auth_mode="bearer",
        scope="abyss-stack-mcp:read",
    )

    drifted = token.model_copy(
        update={"resource": "http://127.0.0.1:5433/mcp"}
    )
    monkeypatch.setattr(auth_context, "get_access_token", lambda: drifted)
    assert _policy_identity("read").scope == "invalid"


def test_configured_audit_journal_is_explicit_bounded_and_contour_specific(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABYSS_STACK_MCP_REQUIRE_AUDIT_JOURNAL", "1")
    with pytest.raises(SystemExit, match="requires.*JOURNAL_PATH"):
        _configured_audit_journal("read")

    path = tmp_path / "policy-read.jsonl"
    monkeypatch.setenv("ABYSS_STACK_MCP_AUDIT_JOURNAL_PATH", str(path))
    monkeypatch.setenv(
        "ABYSS_STACK_MCP_AUDIT_MAX_BYTES",
        str(MIN_MAX_BYTES),
    )
    journal = _configured_audit_journal("read")
    assert journal is not None
    assert journal.summary()["policy_family"] == "read"
    assert journal.summary()["max_bytes"] == MIN_MAX_BYTES

    monkeypatch.setenv("ABYSS_STACK_MCP_AUDIT_MAX_BYTES", "unbounded")
    with pytest.raises(SystemExit, match="decimal integer"):
        _configured_audit_journal("read")


def test_managed_auth_fails_before_audit_journal_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    journal_path = tmp_path / "policy-read.jsonl"
    monkeypatch.setenv("AOA_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("AOA_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("AOA_MCP_PORT", "5431")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials))
    monkeypatch.setenv("ABYSS_STACK_MCP_REQUIRE_AUTH_MANIFEST", "1")
    monkeypatch.setenv("ABYSS_STACK_MCP_REQUIRE_AUDIT_JOURNAL", "1")
    monkeypatch.setenv(
        "ABYSS_STACK_MCP_AUDIT_JOURNAL_PATH",
        str(journal_path),
    )

    with pytest.raises(SystemExit, match="read bearer credential"):
        build_server(policy_family="read")
    assert not journal_path.exists()


@pytest.mark.parametrize(
    ("tool_id", "scope", "expected_reason"),
    (
        ("unlisted_runtime_effect", "abyss-stack-mcp:read", "tool_not_allowlisted"),
        ("stack_runtime_catalog", "wrong:scope", "identity_scope_mismatch"),
    ),
)
def test_policy_seam_denies_unlisted_tools_and_wrong_identity_scope(
    tool_id: str,
    scope: str,
    expected_reason: str,
) -> None:
    seam = policy_seam()

    with pytest.raises(PolicyDeniedError) as caught:
        asyncio.run(
            seam.invoke(
                request_id="request-denied",
                identity=policy_identity(scope),
                tool_id=tool_id,
                arguments={},
                dispatch=lambda: {},
            )
        )

    assert caught.value.reason_code == expected_reason
    assert caught.value.receipt["runtime_effect_authorized"] is False
    assert caught.value.receipt["contains_secrets"] is False


def test_policy_seam_turns_application_denial_into_a_bounded_receipt() -> None:
    seam = policy_seam()

    def deny_dispatch() -> dict:
        raise StackMCPError("runtime precondition is not satisfied")

    with pytest.raises(
        PolicyDeniedError,
        match="application_precondition_denied",
    ) as caught:
        asyncio.run(
            seam.invoke(
                request_id="request-application-denied",
                identity=policy_identity(),
                tool_id="stack_runtime_catalog",
                arguments={},
                dispatch=deny_dispatch,
            )
        )

    assert caught.value.receipt["decision"] == "denied"
    assert caught.value.receipt["reason_codes"] == [
        "application_precondition_denied"
    ]


def test_policy_seam_suppresses_unexpected_application_failure_details() -> None:
    seam = policy_seam()
    sensitive_detail = "private-runtime-path-and-value"

    def fail_dispatch() -> dict:
        raise RuntimeError(sensitive_detail)

    with pytest.raises(PolicyDeniedError, match="application_failure") as caught:
        asyncio.run(
            seam.invoke(
                request_id="request-application-failure",
                identity=policy_identity(),
                tool_id="stack_runtime_catalog",
                arguments={},
                dispatch=fail_dispatch,
            )
        )

    assert caught.value.receipt["reason_codes"] == ["application_failure"]
    assert sensitive_detail not in str(caught.value)
    assert sensitive_detail not in json.dumps(caught.value.receipt)


def test_policy_seam_enforces_output_rate_concurrency_and_timeout_limits() -> None:
    output_seam = policy_seam(max_output_bytes=800)
    with pytest.raises(PolicyDeniedError, match="output_size_limit_exceeded"):
        asyncio.run(
            output_seam.invoke(
                request_id="request-output",
                identity=policy_identity(),
                tool_id="stack_runtime_catalog",
                arguments={},
                dispatch=lambda: {"owner_payload": {"value": "x" * 1000}},
            )
        )

    rate_seam = policy_seam(rate_limit=1)
    asyncio.run(
        rate_seam.invoke(
            request_id="request-rate-first",
            identity=policy_identity(),
            tool_id="stack_runtime_catalog",
            arguments={},
            dispatch=lambda: {"owner_payload": {}},
        )
    )
    with pytest.raises(PolicyDeniedError, match="rate_limit_exceeded"):
        asyncio.run(
            rate_seam.invoke(
                request_id="request-rate-second",
                identity=policy_identity(),
                tool_id="stack_runtime_catalog",
                arguments={},
                dispatch=lambda: {"owner_payload": {}},
            )
        )

    timeout_seam = policy_seam(timeout_seconds=0.01)
    with pytest.raises(PolicyDeniedError, match="dispatch_timeout"):
        asyncio.run(
            timeout_seam.invoke(
                request_id="request-timeout",
                identity=policy_identity(),
                tool_id="stack_runtime_catalog",
                arguments={},
                dispatch=lambda: time.sleep(0.05) or {"owner_payload": {}},
            )
        )

    async def concurrency_scenario() -> None:
        seam = policy_seam(max_in_flight=1)
        started = threading.Event()
        release = threading.Event()

        def blocking_dispatch() -> dict:
            started.set()
            release.wait(timeout=2)
            return {"owner_payload": {}}

        first = asyncio.create_task(
            seam.invoke(
                request_id="request-concurrency-first",
                identity=policy_identity(),
                tool_id="stack_runtime_catalog",
                arguments={},
                dispatch=blocking_dispatch,
            )
        )
        assert await asyncio.to_thread(started.wait, 1)
        with pytest.raises(
            PolicyDeniedError,
            match="concurrency_limit_exceeded",
        ):
            await seam.invoke(
                request_id="request-concurrency-second",
                identity=policy_identity(),
                tool_id="stack_runtime_catalog",
                arguments={},
                dispatch=lambda: {"owner_payload": {}},
            )
        release.set()
        await first

    asyncio.run(concurrency_scenario())


def test_policy_seam_propagates_cancellation_and_records_it() -> None:
    async def cancellation_scenario() -> None:
        seam = policy_seam()
        started = threading.Event()
        release = threading.Event()

        def blocking_dispatch() -> dict:
            started.set()
            release.wait(timeout=2)
            return {"owner_payload": {}}

        task = asyncio.create_task(
            seam.invoke(
                request_id="request-cancelled",
                identity=policy_identity(),
                tool_id="stack_runtime_catalog",
                arguments={},
                dispatch=blocking_dispatch,
            )
        )
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        receipt = seam.recent_receipts()[-1]
        assert receipt["decision"] == "cancelled"
        assert receipt["reason_codes"] == ["caller_cancelled"]

    asyncio.run(cancellation_scenario())


def test_policy_audit_journal_persists_secret_free_receipts_across_restart(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "policy-read.jsonl"
    journal = PolicyAuditJournal(
        journal_path,
        owner="abyss-stack",
        policy_family="read",
        clock=lambda: NOW,
    )
    seam = policy_seam(audit_journal=journal)

    allowed = asyncio.run(
        seam.invoke(
            request_id="request-journal-allowed",
            identity=policy_identity(),
            tool_id="stack_runtime_catalog",
            arguments={"organ_id": "aoa-kag"},
            dispatch=lambda: {"owner_payload": {"entries": []}},
        )
    )
    secret_value = "sk-proj-" + "b" * 48
    with pytest.raises(PolicyDeniedError, match="secret_material_rejected"):
        asyncio.run(
            seam.invoke(
                request_id="request-journal-denied",
                identity=policy_identity(),
                tool_id="stack_runtime_catalog",
                arguments={"query": secret_value},
                dispatch=lambda: {},
            )
        )

    async def cancel() -> None:
        started = threading.Event()
        release = threading.Event()

        def dispatch() -> dict:
            started.set()
            release.wait(timeout=2)
            return {"owner_payload": {}}

        task = asyncio.create_task(
            seam.invoke(
                request_id="request-journal-cancelled",
                identity=policy_identity(),
                tool_id="stack_runtime_catalog",
                arguments={},
                dispatch=dispatch,
            )
        )
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()

    asyncio.run(cancel())
    rendered = journal_path.read_text(encoding="utf-8")
    assert secret_value not in rendered
    assert "aoa-kag" not in rendered
    assert allowed["owner_payload"] == {"entries": []}
    assert journal_path.stat().st_mode & 0o777 == 0o600

    restarted = PolicyAuditJournal(
        journal_path,
        owner="abyss-stack",
        policy_family="read",
    )
    summary = restarted.summary()
    assert summary["continuity_state"] == "exact"
    assert summary["records"] == 3
    assert summary["decision_counts"] == {
        "allowed": 1,
        "cancelled": 1,
        "denied": 1,
    }
    assert summary["reason_counts"] == {
        "caller_cancelled": 1,
        "secret_material_rejected": 1,
    }
    assert summary["contains_secrets"] is False
    assert "grounding" in summary["claim_limit"]
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "policy-audit-summary.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(summary)


def test_policy_audit_journal_accepts_orchestration_read_contour(
    tmp_path: Path,
) -> None:
    journal = PolicyAuditJournal(
        tmp_path / "policy-read.jsonl",
        owner="abyss-stack",
        policy_family="read",
        clock=lambda: NOW,
    )
    seam = StackPolicySeam(
        owner="abyss-stack",
        policy_family="read",
        expected_scope="abyss-stack-mcp:read",
        tools=(
            ToolPolicy(
                tool_id="stack_orchestration_inspect",
                effect_class="observe",
                max_input_bytes=4096,
                max_output_bytes=262_144,
                timeout_seconds=3.0,
                filesystem_access=(
                    "configured_observation_and_orchestration_record_read"
                ),
                network_access="none",
                source_to_sink=(
                    "sdk_validated_runtime_record_to_bounded_inspection"
                ),
            ),
        ),
        max_in_flight=2,
        rate_limit=10,
        rate_window_seconds=60,
        clock=lambda: NOW,
        audit_journal=journal,
    )

    result = asyncio.run(
        seam.invoke(
            request_id="request-orchestration-read",
            identity=policy_identity(),
            tool_id="stack_orchestration_inspect",
            arguments={"run_id": DIGEST_A},
            dispatch=lambda: {
                "schema_version": "abyss_stack_cross_organ_inspection_v1",
                "run_id": DIGEST_A,
                "state": "accepted",
            },
        )
    )

    receipt = result["metadata"]["policy_receipt"]
    assert receipt["decision"] == "allowed"
    assert receipt["filesystem_access"] == (
        "configured_observation_and_orchestration_record_read"
    )
    assert receipt["source_to_sink"] == (
        "sdk_validated_runtime_record_to_bounded_inspection"
    )
    assert journal.summary()["records"] == 1


def test_policy_audit_journal_rejects_tamper_partial_records_and_wrong_contour(
    tmp_path: Path,
) -> None:
    path = tmp_path / "policy-read.jsonl"
    journal = PolicyAuditJournal(
        path,
        owner="abyss-stack",
        policy_family="read",
        clock=lambda: NOW,
    )
    seam = policy_seam(audit_journal=journal)
    asyncio.run(
        seam.invoke(
            request_id="request-audit-tamper",
            identity=policy_identity(),
            tool_id="stack_runtime_catalog",
            arguments={},
            dispatch=lambda: {"owner_payload": {}},
        )
    )
    original = path.read_bytes()

    record = json.loads(original)
    record["policy_receipt"]["identity_id"] = "tampered-consumer"
    path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(PolicyAuditError, match="receipt digest"):
        PolicyAuditJournal(
            path,
            owner="abyss-stack",
            policy_family="read",
        )

    path.write_bytes(original[:-1])
    with pytest.raises(PolicyAuditError, match="partial record"):
        PolicyAuditJournal(
            path,
            owner="abyss-stack",
            policy_family="read",
        )

    path.write_bytes(original)
    with pytest.raises(PolicyAuditError, match="continuity"):
        PolicyAuditJournal(
            path,
            owner="abyss-stack",
            policy_family="candidate",
        )


def test_policy_audit_journal_rejects_unsafe_paths_permissions_and_live_drift(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.jsonl"
    target.touch(mode=0o600)
    symlink = tmp_path / "policy-read.jsonl"
    symlink.symlink_to(target)
    with pytest.raises(PolicyAuditError, match="symlink"):
        PolicyAuditJournal(
            symlink,
            owner="abyss-stack",
            policy_family="read",
        )

    target.chmod(0o640)
    with pytest.raises(PolicyAuditError, match="permissions"):
        PolicyAuditJournal(
            target,
            owner="abyss-stack",
            policy_family="read",
        )

    target.chmod(0o600)
    journal = PolicyAuditJournal(
        target,
        owner="abyss-stack",
        policy_family="read",
    )
    with target.open("ab") as handle:
        handle.write(b"{}\n")
    with pytest.raises(PolicyAuditError, match="outside this process"):
        journal.summary()

    replacement_path = tmp_path / "replacement.jsonl"
    replacement_path.touch(mode=0o600)
    replacement = PolicyAuditJournal(
        replacement_path,
        owner="abyss-stack",
        policy_family="read",
    )
    staged = tmp_path / "staged.jsonl"
    staged.touch(mode=0o600)
    staged.replace(replacement_path)
    with pytest.raises(PolicyAuditError, match="identity changed"):
        replacement.summary()


def test_policy_audit_journal_is_thread_safe_and_fails_closed_at_capacity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "policy-read.jsonl"
    journal = PolicyAuditJournal(
        path,
        owner="abyss-stack",
        policy_family="read",
        max_bytes=MIN_MAX_BYTES,
        clock=lambda: NOW,
    )
    seam = policy_seam(audit_journal=journal)
    allowed = asyncio.run(
        seam.invoke(
            request_id="request-audit-template",
            identity=policy_identity(),
            tool_id="stack_runtime_catalog",
            arguments={},
            dispatch=lambda: {"owner_payload": {}},
        )
    )["metadata"]["policy_receipt"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        record_ids = tuple(pool.map(journal.append, [allowed] * 24))
    assert len(set(record_ids)) == 24
    restarted = PolicyAuditJournal(
        path,
        owner="abyss-stack",
        policy_family="read",
        max_bytes=MIN_MAX_BYTES,
    )
    assert restarted.summary()["records"] == 25

    while True:
        before_append = path.read_bytes()
        try:
            restarted.append(allowed)
        except PolicyAuditError as exc:
            assert "capacity is exhausted" in str(exc)
            assert path.read_bytes() == before_append
            break
    final = PolicyAuditJournal(
        path,
        owner="abyss-stack",
        policy_family="read",
        max_bytes=MIN_MAX_BYTES,
    )
    assert final.summary()["remaining_bytes"] >= 0


def test_contract_is_strict_and_policy_effects_are_bounded() -> None:
    payload = observation(subject())
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="extra"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject(policy_family="read", credential_class="read-only"))
    payload["subjects"][0]["effect_classes"] = ["apply_runtime"]
    with pytest.raises(ValidationError, match="exceed"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    duplicate_consumer = json.loads(
        json.dumps(payload["subjects"][0]["consumers"][0])
    )
    duplicate_consumer["consumer_id"] = "duplicate-registration"
    payload["subjects"][0]["consumers"].append(duplicate_consumer)
    with pytest.raises(ValidationError, match="registration refs must be unique"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["source"]["evidence"] = evidence(
        "source",
        state="compatible_drift",
    )
    with pytest.raises(ValidationError, match="usable link requires evidence"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["source"]["evidence"] = evidence(
        "source",
        state="rollback_required",
    )
    with pytest.raises(ValidationError, match="rollback-required link requires"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    freshness = payload["subjects"][0]["freshness"]
    freshness["state"] = "compatible_drift"
    freshness["evidence_refs"] = []
    freshness["reason_codes"] = ["watermark-drift"]
    with pytest.raises(ValidationError, match="usable freshness requires"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    rollback = payload["subjects"][0]["rollback"]
    rollback["last_known_good_process_identity"] = None
    with pytest.raises(ValidationError, match="complete last-known-good contour"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    rollback = payload["subjects"][0]["rollback"]
    rollback["proved_target"]["package_digest"] = DIGEST_A
    with pytest.raises(ValidationError, match="proof target must match"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["process"]["process_identity"] = None
    with pytest.raises(ValidationError, match="active process requires"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["proof"]["proof_ref"] = None
    with pytest.raises(ValidationError, match="passed central proof requires"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["proof"]["evidence"] = evidence(
        "central-proof",
        owner="unrelated-owner",
    )
    with pytest.raises(ValidationError, match="issued by proof_owner"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["acceptance"]["accepted_at"] = (
        NOW - timedelta(seconds=1)
    ).isoformat()
    with pytest.raises(ValidationError, match="cannot precede central proof"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["acceptance"]["acceptance_ref"] = None
    with pytest.raises(ValidationError, match="owner acceptance requires"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["acceptance"]["evidence"] = evidence(
        "acceptance",
        owner="unrelated-owner",
    )
    with pytest.raises(ValidationError, match="issued by acceptance_owner"):
        RuntimeObservation.model_validate(payload)


@pytest.mark.parametrize(
    ("surface", "named_field"),
    (
        ("deploy", "manifest_ref"),
        ("proof", "proof_ref"),
        ("acceptance", "acceptance_ref"),
        ("canary", "canary_ref"),
        ("rollback", "proof_ref"),
    ),
)
def test_usable_named_receipts_must_match_contained_evidence(
    surface: str,
    named_field: str,
) -> None:
    payload = observation(subject())
    if surface == "deploy":
        unbound_digest = "sha256:" + "9" * 64
        payload["subjects"][0][surface]["manifest_digest"] = unbound_digest
        payload["subjects"][0][surface][named_field] = (
            deployment_manifest_ref(unbound_digest)
        )
    else:
        payload["subjects"][0][surface][named_field] = (
            f"receipt://unbound/{surface}"
        )

    with pytest.raises(ValidationError, match="must match contained evidence"):
        RuntimeObservation.model_validate(payload)


def test_deploy_manifest_ref_is_bound_to_manifest_digest() -> None:
    payload = observation(subject())
    payload["subjects"][0]["deploy"]["manifest_ref"] = (
        deployment_manifest_ref(DIGEST_ROLLBACK_MANIFEST)
    )

    with pytest.raises(ValidationError, match="content-addressed manifest record"):
        RuntimeObservation.model_validate(payload)


def test_runtime_chain_requires_package_and_manifest_identity_fields() -> None:
    payload = observation(subject())
    del payload["subjects"][0]["package"]["source_revision"]
    with pytest.raises(ValidationError, match="source_revision"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    del payload["subjects"][0]["deploy"]["manifest_digest"]
    with pytest.raises(ValidationError, match="manifest_digest"):
        RuntimeObservation.model_validate(payload)


def test_registered_consumer_target_must_match_contained_evidence() -> None:
    payload = observation(subject())
    payload["subjects"][0]["consumers"][0]["registration_ref"] = (
        "config://codex/unbound"
    )

    with pytest.raises(ValidationError, match="must match contained evidence"):
        RuntimeObservation.model_validate(payload)


def test_unregistered_rollback_consumer_target_must_match_evidence() -> None:
    payload = observation(subject())
    consumer = payload["subjects"][0]["consumers"][0]
    consumer["registered"] = False
    consumer["observed_schema_digest"] = None
    consumer["observed_protocol_versions"] = []
    consumer["evidence"] = evidence("unrelated-consumer-observation")

    with pytest.raises(ValidationError, match="must match contained evidence"):
        RuntimeObservation.model_validate(payload)


@pytest.mark.parametrize(
    (
        "surface",
        "named_field",
        "owner_field",
        "expected_error",
    ),
    (
        ("proof", "proof_ref", "proof_owner", "issued by proof_owner"),
        (
            "rollback",
            "proof_ref",
            "proof_owner",
            "issued by proof_owner",
        ),
        (
            "acceptance",
            "acceptance_ref",
            "acceptance_owner",
            "issued by acceptance_owner",
        ),
    ),
)
def test_named_receipt_must_be_issued_by_declared_owner(
    surface: str,
    named_field: str,
    owner_field: str,
    expected_error: str,
) -> None:
    payload = observation(subject())
    runtime_subject = payload["subjects"][0]
    event = runtime_subject[surface]
    named_ref = event[named_field]
    declared_owner = runtime_subject["owners"][owner_field]
    event["evidence"]["evidence_refs"][0]["owner"] = "unrelated-owner"
    decoy = evidence(
        f"{surface}-owner-decoy",
        owner=declared_owner,
    )["evidence_refs"][0]
    assert decoy["evidence_ref"] != named_ref
    event["evidence"]["evidence_refs"].append(decoy)

    with pytest.raises(ValidationError, match=expected_error):
        RuntimeObservation.model_validate(payload)


@pytest.mark.parametrize("canary_time_surface", ("link", "evidence"))
def test_central_proof_cannot_predate_its_canary(
    canary_time_surface: str,
) -> None:
    payload = observation(subject())
    canary_evidence = payload["subjects"][0]["canary"]["evidence"]
    if canary_time_surface == "link":
        canary_evidence["observed_at"] = (NOW + timedelta(seconds=1)).isoformat()
    else:
        canary_evidence["evidence_refs"][0]["observed_at"] = (
            NOW + timedelta(seconds=1)
        ).isoformat()

    with pytest.raises(ValidationError, match="cannot precede canary evidence"):
        RuntimeObservation.model_validate(payload)


@pytest.mark.parametrize("canary_time_surface", ("link", "evidence"))
def test_successful_canary_cannot_predate_deployment(
    canary_time_surface: str,
) -> None:
    payload = observation(subject())
    canary_evidence = payload["subjects"][0]["canary"]["evidence"]
    if canary_time_surface == "link":
        canary_evidence["observed_at"] = (
            NOW - timedelta(seconds=1)
        ).isoformat()
    else:
        canary_evidence["evidence_refs"][0]["observed_at"] = (
            NOW - timedelta(seconds=1)
        ).isoformat()

    with pytest.raises(ValidationError, match="cannot precede deployment"):
        RuntimeObservation.model_validate(payload)


@pytest.mark.parametrize(
    ("event_surface", "expected_error"),
    (
        ("proof", "central proof evidence cannot predate"),
        ("acceptance", "owner acceptance evidence cannot predate"),
    ),
)
@pytest.mark.parametrize("evidence_time_surface", ("link", "evidence"))
def test_proof_events_reject_unrelated_old_receipts(
    event_surface: str,
    expected_error: str,
    evidence_time_surface: str,
) -> None:
    payload = observation(subject())
    event_evidence = payload["subjects"][0][event_surface]["evidence"]
    old_receipt_time = (NOW - timedelta(seconds=31)).isoformat()
    if evidence_time_surface == "link":
        event_evidence["observed_at"] = old_receipt_time
    else:
        event_evidence["evidence_refs"][0]["observed_at"] = old_receipt_time

    with pytest.raises(ValidationError, match=expected_error):
        RuntimeObservation.model_validate(payload)


@pytest.mark.parametrize(
    "field_path",
    (
        ("deploy", "manifest_ref"),
        ("consumers", 0, "registration_ref"),
        ("canary", "canary_route"),
        ("rollback", "rollback_route"),
        ("source", "evidence", "evidence_refs", 0, "evidence_ref"),
    ),
)
def test_contract_rejects_whitespace_only_exact_targets(
    field_path: tuple[str | int, ...],
) -> None:
    payload = observation(subject())
    target = payload["subjects"][0]
    for part in field_path[:-1]:
        target = target[part]
    target[field_path[-1]] = " \t\n"

    with pytest.raises(ValidationError, match="pattern"):
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


@pytest.mark.parametrize(
    "secret_key",
    (
        "apiKey",
        "clientSecret",
        "credential",
        "credentials",
        "private.key",
        "refresh token",
        "github_api_key",
        "backupClientSecretValue",
        "passphrase",
        "databasePassphrase",
        "ssh_passphrase",
        "private_key_passphrase",
        "aws_secret_access_key",
    ),
)
def test_observation_store_rejects_separator_and_case_secret_keys_without_value(
    tmp_path: Path,
    secret_key: str,
) -> None:
    secret_value = "unprefixed-sensitive-material"
    payload = observation(subject())
    payload["subjects"][0][secret_key] = secret_value
    path = write_observation(tmp_path / "secret-key.json", payload)

    with pytest.raises(StackMCPError, match="secret-bearing") as caught:
        ObservationStore(path).load()

    assert secret_value not in str(caught.value)


def test_observation_store_redacts_secret_material_from_forbidden_keys(
    tmp_path: Path,
) -> None:
    secret_value = "actual-secret-material"
    secret_key = f"password={secret_value}"
    payload = observation(subject())
    payload["subjects"][0][secret_key] = "blocked-before-contract-validation"
    path = write_observation(tmp_path / "secret-bearing-key.json", payload)

    with pytest.raises(StackMCPError, match="secret-bearing") as caught:
        ObservationStore(path).load()

    assert secret_key not in str(caught.value)
    assert secret_value not in str(caught.value)
    assert "field[" in str(caught.value)


@pytest.mark.parametrize(
    "reference_surface",
    (
        "query",
        "relative-query",
        "userinfo",
        "scheme-relative-userinfo",
        "fragment",
        "fragment-token",
        "secret-value",
        "leading-token",
        "leading-direct",
        "basic-auth",
        "encoded-basic-auth",
        "raw-jwt",
        "encoded-jwt",
        "pem-private-key",
        "embedded-pem-private-key",
        "encoded-pem-private-key",
        "top-level-encoded",
        "nested-value",
        "double-key",
        "path",
        "relative-path",
        "encoded-relative-path",
        "encoded-path",
        "path-token",
        "namespaced-query-key",
        "concatenated-namespaced-query-key",
        "concatenated-suffixed-query-key",
        "suffixed-query-key",
        "namespaced-path-key",
        "bare-assignment",
        "embedded-bare-assignment",
        "namespaced-bare-assignment",
        "concatenated-suffixed-bare-assignment",
        "encoded-bare-assignment",
        "passphrase-query",
        "aws-secret-access-key",
        "aws-presign-credential",
        "aws-presign-security-token",
        "aws-presign-signature",
        "google-presign-credential",
        "google-presign-security-token",
        "google-presign-signature",
        "azure-sas-signature",
        "generic-signed-url-signature",
        "credential-query",
        "credentials-query",
        "unparseable",
    ),
)
def test_observation_store_rejects_credentials_inside_references(
    tmp_path: Path,
    reference_surface: str,
) -> None:
    secret_value = "reference-secret-value"
    payload = observation(subject())
    if reference_surface == "query":
        payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0][
            "evidence_ref"
        ] = f"https://evidence.invalid/report?api_key={secret_value}"
    elif reference_surface == "relative-query":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"receipt?api_key={secret_value}"
        )
    elif reference_surface == "userinfo":
        payload["subjects"][0]["deploy"]["manifest_ref"] = (
            f"https://operator:{secret_value}@deploy.invalid/manifest"
        )
    elif reference_surface == "scheme-relative-userinfo":
        payload["subjects"][0]["deploy"]["manifest_ref"] = (
            f"//operator:{secret_value}@deploy.invalid/manifest"
        )
    elif reference_surface == "fragment":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/receipt#client_secret={secret_value}"
        )
    elif reference_surface == "fragment-token":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/receipt#sk-{secret_value}"
        )
    elif reference_surface == "secret-value":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/receipt?value=sk-{secret_value}"
        )
    elif reference_surface == "leading-token":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/receipt?value=%20sk-{secret_value}"
        )
    elif reference_surface == "leading-direct":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f" Bearer {secret_value}"
        )
    elif reference_surface == "basic-auth":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"  bAsIc {secret_value}"
        )
    elif reference_surface == "encoded-basic-auth":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"Basic%20{secret_value}"
        )
    elif reference_surface == "raw-jwt":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJvcGVyYXRvciIsInNlY3JldCI6InJlZmVyZW5jZSJ9."
            "c2lnbmF0dXJlLW1hdGVyaWFs"
        )
    elif reference_surface == "encoded-jwt":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "eyJhbGciOiJIUzI1NiJ9%2E"
            "eyJzdWIiOiJvcGVyYXRvciJ9%2E"
            "c2lnbmF0dXJlLW1hdGVyaWFs"
        )
    elif reference_surface == "pem-private-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "-----BEGIN PRIVATE KEY-----\n"
            f"{secret_value}\n"
            "-----END PRIVATE KEY-----"
        )
    elif reference_surface == "embedded-pem-private-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "captured material:\n"
            "-----BEGIN EC PRIVATE KEY-----\n"
            f"{secret_value}"
        )
    elif reference_surface == "encoded-pem-private-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "-----BEGIN%20OPENSSH%20PRIVATE%20KEY-----"
            f"%0A{secret_value}"
        )
    elif reference_surface == "top-level-encoded":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "https%3A%2F%2Facceptance.invalid%2Freceipt"
            f"%3Fapi_key%3D{secret_value}"
        )
    elif reference_surface == "nested-value":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "https://acceptance.invalid/receipt?"
            "next=https%3A%2F%2Fhost.invalid%2Freport"
            f"%3Fapi_key%3D{secret_value}"
        )
    elif reference_surface == "double-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/receipt?%2561pi_key={secret_value}"
        )
    elif reference_surface == "path":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report/api_key/{secret_value}"
        )
    elif reference_surface == "relative-path":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"Logs/receipts/password/{secret_value}"
        )
    elif reference_surface == "encoded-relative-path":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"Logs%2Freceipts%2Fpassword%2F{secret_value}"
        )
    elif reference_surface == "encoded-path":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report/%2561pi_key/{secret_value}"
        )
    elif reference_surface == "path-token":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report/sk-{secret_value}"
        )
    elif reference_surface == "namespaced-query-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report?github_api_key={secret_value}"
        )
    elif reference_surface == "concatenated-namespaced-query-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report?githubapikey={secret_value}"
            f"&dbpassword={secret_value}"
        )
    elif reference_surface == "concatenated-suffixed-query-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report?apikeyvalue={secret_value}"
            f"&tokenvalue={secret_value}"
        )
    elif reference_surface == "suffixed-query-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report?api_key_backup={secret_value}"
        )
    elif reference_surface == "namespaced-path-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report/github_api_key/{secret_value}"
        )
    elif reference_surface == "bare-assignment":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"api_key={secret_value}"
        )
    elif reference_surface == "embedded-bare-assignment":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"review receipt carries api_key={secret_value}"
        )
    elif reference_surface == "namespaced-bare-assignment":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"github_api_key:{secret_value}"
        )
    elif reference_surface == "concatenated-suffixed-bare-assignment":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"tokenvalue={secret_value}"
        )
    elif reference_surface == "encoded-bare-assignment":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"github_api_key%3D{secret_value}"
        )
    elif reference_surface == "passphrase-query":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "https://acceptance.invalid/receipt?"
            f"ssh_passphrase={secret_value}"
        )
    elif reference_surface == "aws-secret-access-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "https://acceptance.invalid/receipt?"
            f"aws_secret_access_key={secret_value}"
        )
    elif reference_surface.startswith("aws-presign-"):
        key = {
            "aws-presign-credential": "X-Amz-Credential",
            "aws-presign-security-token": "X-Amz-Security-Token",
            "aws-presign-signature": "X-Amz-Signature",
        }[reference_surface]
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://bucket.s3.amazonaws.com/object?{key}={secret_value}"
        )
    elif reference_surface.startswith("google-presign-"):
        key = {
            "google-presign-credential": "X-Goog-Credential",
            "google-presign-security-token": "X-Goog-Security-Token",
            "google-presign-signature": "X-Goog-Signature",
        }[reference_surface]
        payload["subjects"][0]["deploy"]["manifest_ref"] = (
            f"https://storage.googleapis.com/bucket/object?{key}={secret_value}"
        )
    elif reference_surface in {
        "azure-sas-signature",
        "generic-signed-url-signature",
    }:
        key = {
            "azure-sas-signature": "sig",
            "generic-signed-url-signature": "Signature",
        }[reference_surface]
        payload["subjects"][0]["deploy"]["manifest_ref"] = (
            f"https://storage.invalid/object?{key}={secret_value}"
        )
    elif reference_surface in {"credential-query", "credentials-query"}:
        key = reference_surface.removesuffix("-query")
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/receipt?{key}={secret_value}"
        )
    else:
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://[bad?api_key={secret_value}"
        )
    path = write_observation(tmp_path / f"{reference_surface}.json", payload)

    with pytest.raises(StackMCPError, match="forbidden") as caught:
        ObservationStore(path).load()

    assert secret_value not in str(caught.value)


def test_observation_store_allows_noncredential_substrings_in_reference_keys(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    safe_reference = (
        "https://acceptance.invalid/receipt?"
        "tokenizer=model&passwordless=true&authorizationPolicy=local"
    )
    payload["subjects"][0]["acceptance"]["acceptance_ref"] = safe_reference
    payload["subjects"][0]["acceptance"]["evidence"]["evidence_refs"][0][
        "evidence_ref"
    ] = safe_reference
    path = write_observation(tmp_path / "noncredential-key-substrings.json", payload)

    loaded, _ = ObservationStore(path).load()

    assert loaded.subjects[0].acceptance.acceptance_ref.endswith(
        "tokenizer=model&passwordless=true&authorizationPolicy=local"
    )


def test_observation_store_allows_noncredential_relative_reference_paths(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    safe_reference = "Logs/receipts/passwordless/result.json"
    payload["subjects"][0]["acceptance"]["acceptance_ref"] = safe_reference
    payload["subjects"][0]["acceptance"]["evidence"]["evidence_refs"][0][
        "evidence_ref"
    ] = safe_reference
    path = write_observation(tmp_path / "safe-relative-path.json", payload)

    loaded, _ = ObservationStore(path).load()

    assert loaded.subjects[0].acceptance.acceptance_ref == safe_reference


@pytest.mark.parametrize(
    "token_prefix",
    (
        "glpat-",
        "gloas-",
        "gldt-",
        "glrt-",
        "glrtr-",
        "glcbt-",
        "glptt-",
        "glft-",
        "glimt-",
        "glagent-",
        "glwt-",
        "glsoat-",
        "glffct-",
    ),
)
def test_observation_store_rejects_gitlab_tokens_as_raw_references(
    tmp_path: Path,
    token_prefix: str,
) -> None:
    secret_value = f"{token_prefix}reference-secret-value"
    payload = observation(subject())
    payload["subjects"][0]["acceptance"]["acceptance_ref"] = secret_value
    path = write_observation(tmp_path / f"{token_prefix}reference.json", payload)

    with pytest.raises(StackMCPError, match="forbidden") as caught:
        ObservationStore(path).load()

    assert secret_value not in str(caught.value)


@pytest.mark.parametrize(
    "secret_value",
    (
        "sk-proj-reference-secret-value",
        "ghp_reference-secret-value",
        "gho_reference-secret-value",
        "ghu_reference-secret-value",
        "ghs_reference-secret-value",
        "ghr_reference-secret-value",
        "github_pat_reference-secret-value",
        "glpat-reference-secret-value",
    ),
)
def test_observation_store_rejects_embedded_provider_tokens(
    tmp_path: Path,
    secret_value: str,
) -> None:
    payload = observation(subject())
    payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
        f"runtime receipt {secret_value} captured"
    )
    path = write_observation(tmp_path / "embedded-provider-token.json", payload)

    with pytest.raises(StackMCPError, match="forbidden") as caught:
        ObservationStore(path).load()

    assert secret_value not in str(caught.value)


def test_observation_store_redacts_contract_validation_input_values(
    tmp_path: Path,
) -> None:
    sensitive_value = "unclassified-sensitive-material"
    payload = observation(subject())
    payload["subjects"][0]["unrecognizedField"] = sensitive_value
    path = write_observation(tmp_path / "invalid-contract.json", payload)

    with pytest.raises(StackMCPError, match="contract validation failed") as caught:
        ObservationStore(path).load()

    assert sensitive_value not in str(caught.value)
    assert caught.value.__suppress_context__ is True


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
def test_observation_store_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "observation.fifo"
    os.mkfifo(fifo)

    with pytest.raises(StackMCPError, match="regular file"):
        ObservationStore(fifo).load()


@pytest.mark.parametrize(
    "endpoint_ref",
    (
        "http://localhost:abc/mcp",
        "http://localhost:0/mcp",
        "http://localhost:65536/mcp",
    ),
)
def test_contract_rejects_invalid_http_endpoint_ports(endpoint_ref: str) -> None:
    payload = observation(subject())
    payload["subjects"][0]["endpoint"]["endpoint_ref"] = endpoint_ref

    with pytest.raises(ValidationError, match="invalid port"):
        RuntimeObservation.model_validate(payload)


def test_catalog_is_compact_and_does_not_flatten_health(tmp_path: Path) -> None:
    app = application(tmp_path)
    result = app.catalog()
    payload = result["owner_payload"]
    assert payload["schema_bytes_loaded"] == 0
    assert payload["entries"][0]["organ_id"] == "aoa-kag"
    assert "proof" in payload["entries"][0]["views"]
    assert "acceptance" in payload["entries"][0]["views"]
    assert "healthy" not in json.dumps(result).lower()
    assert result["metadata"]["execution_authorized"] is False
    assert result["metadata"]["applied_state"] == "not_applied"


def test_stack_catalog_matches_its_committed_canary_contract(
    tmp_path: Path,
) -> None:
    app = application(
        tmp_path,
        payload=observation(
            subject(
                "abyss-stack",
                credential_class="abyss-stack-mcp-read",
            )
        ),
    )
    catalog, _ = _load_targets(DEFAULT_TARGETS_PATH)
    target = next(
        item for item in catalog.targets if item.organ_id == "abyss-stack"
    )

    result = app.catalog(
        organ_id="abyss-stack",
        policy_family="read",
        max_results=1,
        byte_budget=8192,
    )

    assert target.canary_contract is not None
    assert validate_result_contract(
        result,
        target.canary_contract,
    ) == (True, (), "abyss_stack_mcp_result_v1")


def test_read_plane_cannot_enumerate_or_inspect_higher_policy_subjects(
    tmp_path: Path,
) -> None:
    payload = observation(
        subject("read-organ", credential_class="read-organ-read"),
        subject(
            "candidate-organ",
            policy_family="candidate",
            credential_class="candidate-organ-candidate",
        ),
        subject(
            "internal-organ",
            policy_family="internal_effect",
            credential_class="internal-organ-effect",
        ),
        subject(
            "external-organ",
            policy_family="external_effect",
            credential_class="external-organ-effect",
        ),
    )
    app = application(tmp_path, payload=payload)

    entries = app.catalog()["owner_payload"]["entries"]
    assert [(entry["organ_id"], entry["policy_family"]) for entry in entries] == [
        ("read-organ", "read")
    ]
    for policy_family in ("candidate", "internal_effect", "external_effect"):
        with pytest.raises(StackMCPError, match="only read-policy"):
            app.catalog(policy_family=policy_family)
        with pytest.raises(StackMCPError, match="only read-policy"):
            app.inspect(f"{policy_family}-organ", policy_family)

    candidate_app = application(
        tmp_path,
        policy_family="candidate",
        payload=payload,
    )
    with pytest.raises(StackMCPError, match="discovery is absent"):
        candidate_app.catalog()
    with pytest.raises(StackMCPError, match="inspection is absent"):
        candidate_app.inspect("read-organ", "read")


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
    assert process["metadata"]["freshness_state"] == "exact"
    assert endpoint["owner_payload"]["observation"]["ready"] is False
    assert endpoint["owner_payload"]["observation"]["evidence"]["state"] == ("blocked")
    assert endpoint["owner_payload"]["observation"][
        "effective_evidence_state"
    ] == ("blocked")
    assert endpoint["metadata"]["freshness_state"] == "blocked"


@pytest.mark.parametrize(
    "view",
    ("process", "proof", "acceptance", "canary", "rollback"),
)
def test_inspection_folds_selected_expired_link_into_freshness(
    tmp_path: Path,
    view: str,
) -> None:
    payload = observation(subject())
    selected_evidence = payload["subjects"][0][view]["evidence"]
    selected_evidence["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    selected_evidence["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    app = application(tmp_path, payload=payload)

    result = app.inspect("aoa-kag", "read", view=view)

    assert result["metadata"]["freshness_state"] == "stale_readable"
    observation_payload = result["owner_payload"]["observation"]
    evidence_payload = observation_payload["evidence"]
    assert evidence_payload["state"] == "exact"
    assert observation_payload["effective_evidence_state"] == "stale_readable"


def test_inspection_folds_snapshot_future_process_link_into_freshness(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    process_evidence = payload["subjects"][0]["process"]["evidence"]
    snapshot_future = (NOW + timedelta(seconds=31)).isoformat()
    process_evidence["observed_at"] = snapshot_future
    process_evidence["evidence_refs"][0]["observed_at"] = snapshot_future
    app = application(tmp_path, payload=payload)

    result = app.inspect("aoa-kag", "read", view="process")

    assert result["metadata"]["freshness_state"] == "blocked"
    observation_payload = result["owner_payload"]["observation"]
    evidence_payload = observation_payload["evidence"]
    assert evidence_payload["state"] == "exact"
    assert observation_payload["effective_evidence_state"] == "blocked"


def test_inspection_blocks_deployment_that_postdates_its_snapshot(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    payload["subjects"][0]["deploy"]["deployed_at"] = (
        NOW + timedelta(seconds=31)
    ).isoformat()
    payload["subjects"][0]["canary"]["succeeded"] = False
    payload["subjects"][0]["proof"]["verdict"] = "unknown"
    payload["subjects"][0]["acceptance"]["accepted"] = False
    app = application(tmp_path, payload=payload)

    identity = app.inspect("aoa-kag", "read", view="identity")
    full = app.inspect("aoa-kag", "read", view="full")

    assert identity["metadata"]["freshness_state"] == "blocked"
    assert identity["owner_payload"]["observation"]["deploy"]["evidence"][
        "state"
    ] == "exact"
    assert identity["owner_payload"]["observation"]["deploy"][
        "effective_evidence_state"
    ] == "blocked"
    assert full["metadata"]["freshness_state"] == "blocked"
    assert full["owner_payload"]["observation"]["effective_link_states"][
        "deploy"
    ] == "blocked"


@pytest.mark.parametrize(
    ("view", "event_field"),
    (
        ("proof", "evaluated_at"),
        ("acceptance", "accepted_at"),
    ),
)
def test_inspection_blocks_decisions_that_postdate_their_snapshot(
    tmp_path: Path,
    view: str,
    event_field: str,
) -> None:
    payload = observation(subject())
    event = payload["subjects"][0][view]
    event[event_field] = (NOW + timedelta(seconds=31)).isoformat()
    receipt_at = (NOW + timedelta(seconds=1)).isoformat()
    event["evidence"]["observed_at"] = receipt_at
    event["evidence"]["evidence_refs"][0]["observed_at"] = receipt_at
    if view == "proof":
        payload["subjects"][0]["acceptance"]["accepted"] = False
    app = application(tmp_path, payload=payload)

    catalog = app.catalog(organ_id="aoa-kag")
    inspected = app.inspect("aoa-kag", "read", view=view)
    full = app.inspect("aoa-kag", "read", view="full")

    assert catalog["owner_payload"]["entries"][0]["link_states"][view] == (
        "blocked"
    )
    assert inspected["metadata"]["freshness_state"] == "blocked"
    assert inspected["owner_payload"]["observation"]["evidence"]["state"] == (
        "exact"
    )
    assert inspected["owner_payload"]["observation"][
        "effective_evidence_state"
    ] == "blocked"
    assert full["metadata"]["freshness_state"] == "blocked"
    assert full["owner_payload"]["observation"]["effective_link_states"][
        view
    ] == "blocked"


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
        "activate",
        expected_observation_digest=digest,
    )
    second = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )
    assert first == second
    plan = first["owner_payload"]["plan"]
    assert plan["execution_authorized"] is False
    assert plan["approval_required_before_execution"] is True
    assert plan["exact_unit_name"] == "aoa-mcp-http@aoa-kag.service"
    assert [step["order"] for step in plan["steps"]] == [1, 2, 3, 4, 5, 6]
    assert plan["steps"][0]["exact_target"] == "aoa-kag-mcp/0.1.0"
    assert plan["steps"][1]["exact_target"] == "receipt://runtime/central-proof"
    assert plan["steps"][2]["exact_target"] == "receipt://runtime/acceptance"
    assert plan["steps"][3]["action"] == "admit-registry-entry"
    assert plan["steps"][3]["exact_target"] == f"abyss-private@{DIGEST_A}"
    assert plan["steps"][4]["exact_target"] == "config://codex/aoa-kag"
    assert plan["steps"][5]["exact_target"] == "runbook://canary/aoa-kag"
    evidence_refs = {
        item["evidence_ref"] for item in plan["precondition_evidence"]
    }
    assert "config://codex/aoa-kag" in evidence_refs
    assert "receipt://runtime/freshness" in evidence_refs
    assert "receipt://runtime/central-proof" in evidence_refs
    assert "receipt://runtime/acceptance" in evidence_refs


def test_activation_verifies_an_already_admitted_registry(tmp_path: Path) -> None:
    payload = observation(subject())
    payload["subjects"][0]["registry"]["registry_state"] = "admitted"
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )

    assert result["owner_payload"]["plan"]["steps"][3]["action"] == (
        "verify-registry-admission"
    )
    assert result["owner_payload"]["plan"]["steps"][3]["exact_target"] == (
        f"abyss-private@{DIGEST_A}"
    )


@pytest.mark.parametrize(
    ("plan_kind", "expected_steps"),
    (
        (
            "sync",
            (
                ("verify-source-revision", "source-rev-1"),
                ("verify-source-tree-digest", DIGEST_A),
                (
                    "preview-config-sync",
                    deployment_manifest_ref(DIGEST_MANIFEST),
                ),
                (
                    "apply-exact-config-sync",
                    deployment_manifest_ref(DIGEST_MANIFEST),
                ),
                ("compare-deployed-digest", DIGEST_E),
            ),
        ),
        (
            "deploy",
            (
                ("verify-package-source-revision", "deploy-rev-1"),
                ("verify-package-digest", DIGEST_B),
                ("stage-exact-package", f"aoa-kag-mcp@{DIGEST_B}"),
                ("deploy-staged-package", f"aoa-kag-mcp@{DIGEST_B}"),
                ("compare-deployed-digest", DIGEST_F),
            ),
        ),
    ),
)
def test_sync_and_deploy_plans_include_exact_transition_steps(
    tmp_path: Path,
    plan_kind: str,
    expected_steps: tuple[tuple[str, str], ...],
) -> None:
    app = application(tmp_path, policy_family="candidate")
    _, digest = app.store.load()

    result = app.prepare_plan(
        "aoa-kag",
        "read",
        plan_kind,
        expected_observation_digest=digest,
    )

    plan = result["owner_payload"]["plan"]
    assert plan["execution_authorized"] is False
    assert plan["postcondition_deploy_tree_digest"] == {
        "sync": DIGEST_E,
        "deploy": DIGEST_F,
    }[plan_kind]
    assert tuple(
        (step["action"], step["exact_target"]) for step in plan["steps"]
    ) == expected_steps


@pytest.mark.parametrize("plan_kind", ("deploy", "activate", "restart"))
def test_runtime_plan_blocks_package_from_another_stack_deploy_revision(
    tmp_path: Path,
    plan_kind: str,
) -> None:
    payload = observation(subject())
    payload["subjects"][0]["package"]["source_revision"] = "source-rev-previous"
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match="package_deploy_revision_mismatch"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            plan_kind,
            expected_observation_digest=digest,
        )


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
    read_app = application(
        tmp_path,
        payload=payload,
    )
    catalog = read_app.catalog()
    assert catalog["owner_payload"]["entries"][0]["link_states"]["source"] == (
        "stale_readable"
    )
    app = application(
        tmp_path,
        policy_family="candidate",
        payload=payload,
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


def test_rollback_plan_accepts_fresh_rollback_required_deploy_links(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    source_evidence = payload["subjects"][0]["source"]["evidence"]
    source_evidence["state"] = "rollback_required"
    source_evidence["reason_codes"] = ["failed-rollout"]
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "rollback",
        expected_observation_digest=digest,
    )
    plan = result["owner_payload"]["plan"]
    assert plan["plan_kind"] == "rollback"
    assert [
        (step["action"], step["exact_target"]) for step in plan["steps"]
    ] == [
        ("deny-discovery", f"abyss-private@{DIGEST_A}"),
        ("deny-activation", "aoa-kag/read"),
        ("verify-rollback-proof", "receipt://runtime/rollback"),
        ("restore-exact-package", DIGEST_B),
        ("restore-deployed-tree", DIGEST_C),
        ("restore-deploy-revision", "deploy-rev-0"),
        (
            "restore-deployment-manifest",
            deployment_manifest_ref(DIGEST_ROLLBACK_MANIFEST),
        ),
        (
            "verify-deployment-manifest-digest",
            DIGEST_ROLLBACK_MANIFEST,
        ),
        ("restore-unit", "aoa-mcp-http@aoa-kag.service"),
        ("restore-credential-class", "aoa-kag-read"),
        (
            "restore-executable",
            "/srv/AbyssOS/.codex/bin/aoa-kag-mcp-server.py",
        ),
        ("restart-restored-process", "aoa-mcp-http@aoa-kag.service"),
        ("verify-process-identity", "aoa-kag-mcp/0.0.9"),
        ("restore-consumer-registration", "config://codex/aoa-kag"),
        (
            "run-grounded-canary",
            "runbook://canary/aoa-kag/last-known-good",
        ),
    ]
    evidence_refs = {
        item["evidence_ref"] for item in plan["precondition_evidence"]
    }
    assert {
        "receipt://runtime/source",
        "receipt://runtime/registry",
        "config://codex/aoa-kag",
        "receipt://runtime/rollback",
    } <= evidence_refs
    assert "receipt://runtime/canary" not in evidence_refs

    payload = observation(subject())
    payload["subjects"][0]["source"]["evidence"] = evidence(
        "source",
        state="blocked",
    )
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="source_identity_not_usable"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "rollback",
            expected_observation_digest=digest,
        )

    payload = observation(subject())
    source_evidence = payload["subjects"][0]["source"]["evidence"]
    source_evidence["state"] = "rollback_required"
    source_evidence["reason_codes"] = ["failed-rollout"]
    source_evidence["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    source_evidence["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="source_identity_not_usable"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "rollback",
            expected_observation_digest=digest,
        )


def test_rollback_can_restore_a_bound_unregistered_consumer(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    consumer = payload["subjects"][0]["consumers"][0]
    consumer["registered"] = False
    consumer["observed_schema_digest"] = None
    consumer["observed_protocol_versions"] = []
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "rollback",
        expected_observation_digest=digest,
    )

    restore = next(
        step
        for step in result["owner_payload"]["plan"]["steps"]
        if step["action"] == "restore-consumer-registration"
    )
    assert restore["exact_target"] == "config://codex/aoa-kag"


@pytest.mark.parametrize(
    ("evidence_path", "expected_blocker"),
    (
        (("registry", "evidence"), "registry_evidence_not_usable"),
        (
            ("consumers", 0, "evidence"),
            "rollback_consumer_evidence_not_usable",
        ),
    ),
)
def test_rollback_plan_requires_fresh_evidence_for_every_step(
    tmp_path: Path,
    evidence_path: tuple[str | int, ...],
    expected_blocker: str,
) -> None:
    payload = observation(subject())
    target = payload["subjects"][0]
    for part in evidence_path:
        target = target[part]
    target["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    target["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match=expected_blocker):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "rollback",
            expected_observation_digest=digest,
        )


@pytest.mark.parametrize("current_canary_failure", ("blocked", "expired"))
def test_rollback_relies_on_lkg_proof_when_current_canary_is_unusable(
    tmp_path: Path,
    current_canary_failure: str,
) -> None:
    payload = observation(subject())
    canary_evidence = payload["subjects"][0]["canary"]["evidence"]
    if current_canary_failure == "blocked":
        canary_evidence["state"] = "blocked"
        canary_evidence["reason_codes"] = ["current-deployment-failed"]
    else:
        canary_evidence["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
        canary_evidence["evidence_refs"][0]["expires_at"] = (
            NOW + timedelta(minutes=1)
        ).isoformat()
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "rollback",
        expected_observation_digest=digest,
    )

    plan = result["owner_payload"]["plan"]
    assert plan["steps"][-1] == {
        "order": 15,
        "action": "run-grounded-canary",
        "exact_target": "runbook://canary/aoa-kag/last-known-good",
        "expected_effect": (
            "prepare run-grounded-canary for operator review"
        ),
        "stop_on": ["unexpected-drift", "precondition-mismatch"],
    }
    evidence_refs = {
        item["evidence_ref"] for item in plan["precondition_evidence"]
    }
    assert "receipt://runtime/rollback" in evidence_refs
    assert "receipt://runtime/canary" not in evidence_refs


def test_restart_plan_requires_and_carries_fresh_canary_evidence(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "restart",
        expected_observation_digest=digest,
    )
    assert "receipt://runtime/canary" in {
        item["evidence_ref"]
        for item in result["owner_payload"]["plan"]["precondition_evidence"]
    }
    assert "receipt://runtime/central-proof" in {
        item["evidence_ref"]
        for item in result["owner_payload"]["plan"]["precondition_evidence"]
    }
    assert "config://codex/aoa-kag" in {
        item["evidence_ref"]
        for item in result["owner_payload"]["plan"]["precondition_evidence"]
    }
    assert result["owner_payload"]["plan"]["steps"][0] == {
        "order": 1,
        "action": "verify-central-proof",
        "exact_target": "receipt://runtime/central-proof",
        "expected_effect": (
            "prepare verify-central-proof for operator review"
        ),
        "stop_on": ["unexpected-drift", "precondition-mismatch"],
    }
    assert result["owner_payload"]["plan"]["steps"][1] == {
        "order": 2,
        "action": "verify-consumer-registration",
        "exact_target": "config://codex/aoa-kag",
        "expected_effect": (
            "prepare verify-consumer-registration for operator review"
        ),
        "stop_on": ["unexpected-drift", "precondition-mismatch"],
    }

    payload = observation(subject())
    payload["subjects"][0]["canary"]["canary_route"] = (
        "runbook://canary/aoa-kag/unproved-restart-route"
    )
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="restart_proof_target_mismatch"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=digest,
        )

    payload = observation(subject())
    canary_evidence = payload["subjects"][0]["canary"]["evidence"]
    canary_evidence["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    canary_evidence["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="canary_evidence_not_usable"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=digest,
        )

    payload = observation(subject())
    payload["subjects"][0]["process"]["active"] = False
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="process_not_active"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=digest,
        )


@pytest.mark.parametrize(
    ("proof_field", "stale_value"),
    (
        ("proved_source_revision", "source-rev-previous"),
        ("proved_source_tree_digest", DIGEST_B),
        ("proved_package_digest", DIGEST_A),
        ("proved_deploy_revision", "deploy-rev-previous"),
        ("proved_deploy_tree_digest", DIGEST_A),
        ("proved_deploy_manifest_digest", DIGEST_ROLLBACK_MANIFEST),
        ("proved_process_identity", "aoa-kag-mcp/previous-process"),
        ("proved_server_schema_digest", DIGEST_A),
        ("proved_consumer_registration_ref", "config://codex/previous"),
    ),
)
def test_restart_plan_binds_central_proof_to_current_runtime_contour(
    tmp_path: Path,
    proof_field: str,
    stale_value: str,
) -> None:
    payload = observation(subject())
    payload["subjects"][0]["proof"][proof_field] = stale_value
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match="restart_proof_target_mismatch"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=digest,
        )


def test_activation_requires_usable_freshness_and_runtime_readiness(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )
    assert result["owner_payload"]["plan"]["plan_kind"] == "activate"

    cases: list[tuple[dict, str]] = []

    payload = observation(subject())
    payload["subjects"][0]["freshness"]["state"] = "blocked"
    payload["subjects"][0]["freshness"]["reason_codes"] = ["provider-blocked"]
    cases.append((payload, "subject_freshness_not_usable"))

    payload = observation(subject())
    payload["subjects"][0]["process"]["active"] = False
    cases.append((payload, "process_not_active"))

    payload = observation(subject())
    payload["subjects"][0]["endpoint"]["ready"] = False
    cases.append((payload, "endpoint_not_ready"))

    payload = observation(subject())
    proof = payload["subjects"][0]["proof"]
    proof["verdict"] = "unknown"
    proof["proof_ref"] = None
    proof["evaluated_at"] = None
    proof["proved_source_revision"] = None
    proof["proved_source_tree_digest"] = None
    proof["proved_package_digest"] = None
    proof["proved_deploy_revision"] = None
    proof["proved_deploy_tree_digest"] = None
    proof["proved_deploy_manifest_digest"] = None
    proof["proved_process_identity"] = None
    proof["proved_server_schema_digest"] = None
    proof["proved_consumer_registration_ref"] = None
    proof["proved_canary_route"] = None
    proof["proved_canary_ref"] = None
    proof["evidence"] = evidence("central-proof", state="unknown")
    cases.append((payload, "central_proof_not_proven"))

    payload = observation(subject())
    payload["subjects"][0]["proof"]["proved_source_tree_digest"] = DIGEST_B
    cases.append((payload, "central_proof_target_mismatch"))

    payload = observation(subject())
    payload["subjects"][0]["proof"]["proved_package_digest"] = DIGEST_A
    cases.append((payload, "central_proof_target_mismatch"))

    payload = observation(subject())
    payload["subjects"][0]["proof"]["proved_deploy_tree_digest"] = DIGEST_A
    cases.append((payload, "central_proof_target_mismatch"))

    payload = observation(subject())
    payload["subjects"][0]["proof"]["proved_deploy_manifest_digest"] = (
        DIGEST_ROLLBACK_MANIFEST
    )
    cases.append((payload, "central_proof_target_mismatch"))

    payload = observation(subject())
    payload["subjects"][0]["proof"]["proved_process_identity"] = (
        "aoa-kag-mcp/previous-process"
    )
    cases.append((payload, "central_proof_target_mismatch"))

    payload = observation(subject())
    payload["subjects"][0]["canary"]["canary_route"] = (
        "runbook://canary/aoa-kag/unproved-route"
    )
    cases.append((payload, "central_proof_target_mismatch"))

    payload = observation(subject())
    proof_evidence = payload["subjects"][0]["proof"]["evidence"]
    proof_evidence["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    proof_evidence["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    cases.append((payload, "central_proof_not_proven"))

    payload = observation(subject())
    acceptance = payload["subjects"][0]["acceptance"]
    acceptance["accepted"] = False
    acceptance["acceptance_ref"] = None
    acceptance["accepted_at"] = None
    acceptance["accepted_source_revision"] = None
    acceptance["accepted_package_digest"] = None
    acceptance["evidence"] = evidence("acceptance", state="unknown")
    cases.append((payload, "owner_acceptance_not_proven"))

    payload = observation(subject())
    payload["subjects"][0]["acceptance"]["accepted_source_revision"] = (
        "different-source-revision"
    )
    cases.append((payload, "owner_acceptance_target_mismatch"))

    payload = observation(subject())
    acceptance_evidence = payload["subjects"][0]["acceptance"]["evidence"]
    acceptance_evidence["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    acceptance_evidence["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    cases.append((payload, "owner_acceptance_not_proven"))

    payload = observation(subject())
    payload["subjects"][0]["canary"]["succeeded"] = False
    cases.append((payload, "canary_not_proven"))

    payload = observation(subject())
    rollback = payload["subjects"][0]["rollback"]
    rollback["ready"] = False
    rollback["last_known_good_package_digest"] = None
    rollback["proof_ref"] = None
    rollback["evidence"] = evidence("rollback", state="unknown")
    cases.append((payload, "rollback_not_proven"))

    for case_index, (case_payload, blocker) in enumerate(cases):
        case_root = tmp_path / f"case-{case_index}"
        case_root.mkdir()
        app = application(
            case_root,
            policy_family="candidate",
            payload=case_payload,
        )
        _, digest = app.store.load()
        with pytest.raises(StackMCPError, match=blocker):
            app.prepare_plan(
                "aoa-kag",
                "read",
                "activate",
                expected_observation_digest=digest,
            )


@pytest.mark.parametrize(
    "link_surface",
    (
        "source",
        "package",
        "deploy",
        "process",
        "endpoint",
        "registry",
        "proof",
        "acceptance",
        "consumer",
        "canary",
        "rollback",
    ),
)
def test_candidate_freshness_folds_required_link_drift(
    tmp_path: Path,
    link_surface: str,
) -> None:
    payload = observation(subject())
    subject_payload = payload["subjects"][0]
    if link_surface == "consumer":
        link = subject_payload["consumers"][0]["evidence"]
    else:
        link = subject_payload[link_surface]["evidence"]
    link["state"] = "compatible_drift"
    link["reason_codes"] = ["fixture-compatible-drift"]

    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )

    assert result["metadata"]["freshness_state"] == "compatible_drift"


@pytest.mark.parametrize("policy_family", ("internal_effect", "external_effect"))
@pytest.mark.parametrize("plan_kind", ("activate", "restart"))
def test_runtime_activation_blocks_effect_planes_until_effect_contracts_exist(
    tmp_path: Path,
    policy_family: str,
    plan_kind: str,
) -> None:
    payload = observation(
        subject(
            organ_id=f"{policy_family}-organ",
            policy_family=policy_family,
            credential_class=f"{policy_family}-credential",
        )
    )
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match="effect_activation_contracts_absent"):
        app.prepare_plan(
            f"{policy_family}-organ",
            policy_family,
            plan_kind,
            expected_observation_digest=digest,
        )


@pytest.mark.parametrize(
    ("consumer_schema", "consumer_protocols"),
    [
        (DIGEST_A, ["2025-11-25"]),
        (DIGEST_D, ["2026-07-28"]),
    ],
)
def test_activation_rejects_incompatible_registered_consumer(
    tmp_path: Path,
    consumer_schema: str,
    consumer_protocols: list[str],
) -> None:
    payload = observation(subject())
    consumer = payload["subjects"][0]["consumers"][0]
    consumer["observed_schema_digest"] = consumer_schema
    consumer["observed_protocol_versions"] = consumer_protocols
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="no_compatible_registered_consumer"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "activate",
            expected_observation_digest=digest,
        )


def test_activation_targets_only_the_selected_compatible_consumer(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    good = payload["subjects"][0]["consumers"][0]
    good["consumer_id"] = "z-compatible"
    good["registration_ref"] = "config://codex/compatible"
    good["evidence"] = evidence(
        "consumer-good",
        evidence_ref="config://codex/compatible",
    )
    payload["subjects"][0]["proof"]["proved_consumer_registration_ref"] = (
        "config://codex/compatible"
    )
    unselected = json.loads(json.dumps(good))
    unselected["consumer_id"] = "a-compatible-unselected"
    unselected["registration_ref"] = "config://codex/compatible-unselected"
    unselected["evidence"] = evidence(
        "consumer-unselected",
        evidence_ref="config://codex/compatible-unselected",
    )
    future = (NOW + timedelta(seconds=31)).isoformat()
    unselected["evidence"]["observed_at"] = future
    unselected["evidence"]["evidence_refs"][0]["observed_at"] = future
    payload["subjects"][0]["consumers"] = [unselected, good]

    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )
    plan = result["owner_payload"]["plan"]
    assert plan["steps"][4]["exact_target"] == "config://codex/compatible"
    evidence_refs = {
        item["evidence_ref"] for item in plan["precondition_evidence"]
    }
    assert "config://codex/compatible" in evidence_refs
    assert "config://codex/compatible-unselected" not in evidence_refs


def test_freshness_reference_expiry_is_stale_and_blocks_plans(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    payload["subjects"][0]["freshness"]["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    read_app = application(tmp_path, payload=payload)
    catalog = read_app.catalog()
    assert catalog["owner_payload"]["entries"][0]["freshness_state"] == (
        "stale_readable"
    )
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="subject_freshness_not_usable"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "activate",
            expected_observation_digest=digest,
        )

    payload = observation(subject())
    freshness = payload["subjects"][0]["freshness"]
    freshness["state"] = "blocked"
    freshness["reason_codes"] = ["provider-blocked"]
    freshness["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    read_app = application(tmp_path, payload=payload)
    assert read_app.catalog()["owner_payload"]["entries"][0]["freshness_state"] == (
        "blocked"
    )


@pytest.mark.parametrize(
    ("future_surface", "state_surface"),
    (
        ("link", "link_states"),
        ("evidence", "link_states"),
        ("freshness", "freshness_state"),
        ("freshness_evidence", "freshness_state"),
    ),
)
def test_read_paths_block_causally_future_evidence(
    tmp_path: Path,
    future_surface: str,
    state_surface: str,
) -> None:
    payload = observation(subject())
    future = (NOW + timedelta(seconds=31)).isoformat()
    subject_payload = payload["subjects"][0]
    if future_surface == "link":
        subject_payload["source"]["evidence"]["observed_at"] = future
    elif future_surface == "evidence":
        subject_payload["source"]["evidence"]["evidence_refs"][0][
            "observed_at"
        ] = future
    elif future_surface == "freshness":
        subject_payload["freshness"]["observed_at"] = future
    else:
        subject_payload["freshness"]["evidence_refs"][0]["observed_at"] = future

    app = application(tmp_path, payload=payload)
    entry = app.catalog()["owner_payload"]["entries"][0]
    if state_surface == "link_states":
        assert entry[state_surface]["source"] == "blocked"
        drift = app.inspect("aoa-kag", "read", view="drift")
        assert drift["owner_payload"]["observation"]["states"]["source"] == (
            "blocked"
        )
    else:
        assert entry[state_surface] == "blocked"
        freshness = app.inspect("aoa-kag", "read", view="freshness")
        assert freshness["owner_payload"]["observation"]["effective_state"] == (
            "blocked"
        )


def test_read_paths_block_future_dated_observation_envelope(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    payload["generated_at"] = (
        NOW + timedelta(minutes=5, seconds=31)
    ).isoformat()
    app = application(tmp_path, payload=payload)

    catalog = app.catalog()
    assert catalog["metadata"]["freshness_state"] == "blocked"
    assert catalog["metadata"]["warnings"] == [
        "runtime-observation-future-dated"
    ]
    assert catalog["owner_payload"]["entries"][0]["freshness_state"] == "blocked"

    freshness = app.inspect("aoa-kag", "read", view="freshness")
    assert freshness["metadata"]["freshness_state"] == "blocked"
    assert freshness["owner_payload"]["observation"]["effective_state"] == "blocked"

    drift = app.inspect("aoa-kag", "read", view="drift")
    assert drift["metadata"]["freshness_state"] == "blocked"
    assert drift["owner_payload"]["observation"]["freshness_state"] == "blocked"


def test_read_paths_downgrade_expired_observation_envelope(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    payload["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    app = application(tmp_path, payload=payload)

    catalog = app.catalog()
    assert catalog["metadata"]["freshness_state"] == "stale_readable"
    assert catalog["metadata"]["warnings"] == ["runtime-observation-expired"]
    assert catalog["owner_payload"]["entries"][0]["freshness_state"] == (
        "stale_readable"
    )

    freshness = app.inspect("aoa-kag", "read", view="freshness")
    assert freshness["metadata"]["freshness_state"] == "stale_readable"
    assert freshness["owner_payload"]["observation"]["effective_state"] == (
        "stale_readable"
    )

    drift = app.inspect("aoa-kag", "read", view="drift")
    assert drift["metadata"]["freshness_state"] == "stale_readable"
    assert drift["owner_payload"]["observation"]["freshness_state"] == (
        "stale_readable"
    )


@pytest.mark.parametrize(
    ("expiry_surface", "expected_expiry"),
    [
        ("link", NOW + timedelta(minutes=7)),
        ("evidence", NOW + timedelta(minutes=8)),
    ],
)
def test_plan_expires_with_its_earliest_precondition(
    tmp_path: Path,
    expiry_surface: str,
    expected_expiry: datetime,
) -> None:
    payload = observation(subject())
    if expiry_surface == "link":
        payload["subjects"][0]["endpoint"]["evidence"]["expires_at"] = (
            expected_expiry.isoformat()
        )
    else:
        payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0][
            "expires_at"
        ] = expected_expiry.isoformat()
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )
    plan_expiry = datetime.fromisoformat(
        result["owner_payload"]["plan"]["expires_at"].replace("Z", "+00:00")
    )
    assert plan_expiry == expected_expiry


@pytest.mark.parametrize(
    "future_surface",
    (
        "observation",
        "deploy",
        "freshness",
        "proof",
        "acceptance",
        "link",
        "evidence",
    ),
)
def test_plan_rejects_timestamps_beyond_bounded_future_skew(
    tmp_path: Path,
    future_surface: str,
) -> None:
    payload = observation(subject())
    future = (NOW + timedelta(minutes=5, seconds=31)).isoformat()
    if future_surface == "observation":
        payload["generated_at"] = future
    elif future_surface == "deploy":
        payload["subjects"][0]["deploy"]["deployed_at"] = future
        canary_evidence = payload["subjects"][0]["canary"]["evidence"]
        canary_evidence["observed_at"] = future
        canary_evidence["evidence_refs"][0]["observed_at"] = future
        set_proof_event_time(payload, "proof", future)
        set_proof_event_time(payload, "acceptance", future)
    elif future_surface == "freshness":
        payload["subjects"][0]["freshness"]["observed_at"] = future
    elif future_surface == "proof":
        set_proof_event_time(payload, "proof", future)
        set_proof_event_time(payload, "acceptance", future)
    elif future_surface == "acceptance":
        set_proof_event_time(payload, "acceptance", future)
    elif future_surface == "link":
        payload["subjects"][0]["source"]["evidence"]["observed_at"] = future
    else:
        payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0][
            "observed_at"
        ] = future
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match="future-dated"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "activate",
            expected_observation_digest=digest,
        )


@pytest.mark.parametrize(
    "post_snapshot_surface",
    ("deploy", "freshness", "proof", "acceptance", "link", "evidence"),
)
def test_plan_rejects_evidence_that_postdates_its_snapshot(
    tmp_path: Path,
    post_snapshot_surface: str,
) -> None:
    payload = observation(subject())
    post_snapshot = (NOW + timedelta(seconds=31)).isoformat()
    if post_snapshot_surface == "deploy":
        payload["subjects"][0]["deploy"]["deployed_at"] = post_snapshot
        canary_evidence = payload["subjects"][0]["canary"]["evidence"]
        canary_evidence["observed_at"] = post_snapshot
        canary_evidence["evidence_refs"][0]["observed_at"] = post_snapshot
        set_proof_event_time(payload, "proof", post_snapshot)
        set_proof_event_time(payload, "acceptance", post_snapshot)
    elif post_snapshot_surface == "freshness":
        payload["subjects"][0]["freshness"]["observed_at"] = post_snapshot
    elif post_snapshot_surface == "proof":
        set_proof_event_time(payload, "proof", post_snapshot)
        set_proof_event_time(payload, "acceptance", post_snapshot)
    elif post_snapshot_surface == "acceptance":
        set_proof_event_time(payload, "acceptance", post_snapshot)
    elif post_snapshot_surface == "link":
        payload["subjects"][0]["source"]["evidence"]["observed_at"] = post_snapshot
    else:
        payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0][
            "observed_at"
        ] = post_snapshot
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match="future-dated"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "activate",
            expected_observation_digest=digest,
        )


def test_plan_allows_observation_within_bounded_future_skew(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    payload["generated_at"] = (
        NOW + timedelta(minutes=5, seconds=30)
    ).isoformat()
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )

    assert result["owner_payload"]["plan"]["plan_kind"] == "activate"


def test_plan_deduplication_retains_earliest_evidence_expiry(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    source_ref = payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0]
    earliest_expiry = NOW + timedelta(minutes=6)
    source_ref["expires_at"] = earliest_expiry.isoformat()
    endpoint_refs = payload["subjects"][0]["endpoint"]["evidence"]["evidence_refs"]
    endpoint_refs[0] = {
        **source_ref,
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
    }
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )
    plan = result["owner_payload"]["plan"]
    retained = [
        item
        for item in plan["precondition_evidence"]
        if item["evidence_ref"] == source_ref["evidence_ref"]
    ]

    assert len(retained) == 1
    assert (
        datetime.fromisoformat(retained[0]["expires_at"].replace("Z", "+00:00"))
        == earliest_expiry
    )
    assert (
        datetime.fromisoformat(plan["expires_at"].replace("Z", "+00:00"))
        == earliest_expiry
    )


def test_plan_rejects_conflicting_duplicate_evidence_timestamps(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    source_ref = payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0]
    endpoint_refs = payload["subjects"][0]["endpoint"]["evidence"]["evidence_refs"]
    endpoint_refs[0] = {
        **source_ref,
        "observed_at": (NOW + timedelta(seconds=1)).isoformat(),
    }
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match="conflicting timestamps"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "activate",
            expected_observation_digest=digest,
        )


def test_read_and_candidate_servers_expose_disjoint_tools(tmp_path: Path) -> None:
    path = write_observation(tmp_path / "observation.json")
    read = build_server(path, policy_family="read")
    candidate = build_server(path, policy_family="candidate")
    assert read._mcp_server.create_initialization_options().server_version == "0.5.1"
    assert (
        candidate._mcp_server.create_initialization_options().server_version
        == "0.5.1"
    )
    read_tools = {tool.name for tool in asyncio.run(read.list_tools())}
    candidate_tools = {tool.name for tool in asyncio.run(candidate.list_tools())}
    assert read_tools == {
        "stack_orchestration_inspect",
        "stack_runtime_catalog",
        "stack_runtime_inspect",
    }
    assert candidate_tools == {"stack_prepare_runtime_plan"}
    read_tool_contracts = {
        tool.name: tool.inputSchema for tool in asyncio.run(read.list_tools())
    }
    catalog_policy = read_tool_contracts["stack_runtime_catalog"]["properties"][
        "policy_family"
    ]
    inspect_policy = read_tool_contracts["stack_runtime_inspect"]["properties"][
        "policy_family"
    ]
    inspect_views = read_tool_contracts["stack_runtime_inspect"]["properties"]["view"][
        "enum"
    ]
    assert catalog_policy["anyOf"][0]["const"] == "read"
    assert inspect_policy["const"] == "read"
    assert "proof" in inspect_views
    assert "acceptance" in inspect_views


def test_stdio_server_round_trips_through_policy_seam(tmp_path: Path) -> None:
    observation_path = write_observation(tmp_path / "observation.json")
    server_script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "abyss_stack_mcp_server.py"
    )

    async def run_smoke() -> dict:
        env = {
            **os.environ,
            "AOA_MCP_TRANSPORT": "stdio",
            "ABYSS_STACK_MCP_POLICY_FAMILY": "read",
            "ABYSS_STACK_MCP_OBSERVATION_PATH": str(observation_path),
        }
        env.pop("ABYSS_STACK_MCP_REQUIRE_AUTH_MANIFEST", None)
        env.pop("CREDENTIALS_DIRECTORY", None)
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(server_script)],
            cwd=str(Path(__file__).resolve().parents[4]),
            env=env,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "stack_runtime_catalog",
                    {"organ_id": "aoa-kag"},
                    read_timeout_seconds=timedelta(seconds=5),
                )
        assert not result.isError
        return json.loads(result.content[0].text)

    payload = asyncio.run(run_smoke())
    receipt = payload["metadata"]["policy_receipt"]
    assert receipt["decision"] == "allowed"
    assert receipt["auth_mode"] == "os_process"
    assert receipt["scope"] == "abyss-stack-mcp:read"
    assert payload["metadata"]["instruction_authority"] == "none"


def test_server_info_fallback_version_matches_package_metadata() -> None:
    package_root = Path(__file__).resolve().parents[1]
    project = tomllib.loads(
        (package_root / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert project["project"]["version"] == APPLICATION_VERSION


@pytest.mark.parametrize("view", ("proof", "acceptance"))
def test_portable_cli_exposes_governed_activation_views(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    view: str,
) -> None:
    path = write_observation(tmp_path / "observation.json")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "abyss-stack-mcp",
            "--observation-path",
            str(path),
            "inspect",
            "aoa-kag",
            "read",
            "--view",
            view,
        ],
    )

    cli_main()

    result = json.loads(capsys.readouterr().out)
    assert result["owner_payload"]["view"] == view


@pytest.mark.parametrize(
    ("arguments", "expected_error"),
    (
        (
            ["inspect", "aoa-kag", "candidate"],
            "invalid choice",
        ),
        (
            [
                "--policy-family",
                "candidate",
                "inspect",
                "aoa-kag",
                "read",
            ],
            "inspect requires --policy-family read",
        ),
        (
            [
                "plan",
                "aoa-kag",
                "read",
                "restart",
                "--expected-observation-digest",
                DIGEST_A,
            ],
            "plan requires --policy-family candidate",
        ),
    ),
)
def test_portable_cli_rejects_cross_contour_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    expected_error: str,
) -> None:
    path = write_observation(tmp_path / "observation.json")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "abyss-stack-mcp",
            "--observation-path",
            str(path),
            *arguments,
        ],
    )

    with pytest.raises(SystemExit) as caught:
        cli_main()

    assert caught.value.code == 2
    assert expected_error in capsys.readouterr().err


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
        5433,
        "ABYSS_STACK_MCP_CANDIDATE_BEARER_TOKEN",
        "abyss-stack-mcp-candidate-bearer-token",
        "abyss-stack-mcp:candidate",
    )
    assert _contour("internal_effect") == (
        5439,
        "ABYSS_STACK_MCP_INTERNAL_EFFECT_BEARER_TOKEN",
        "abyss-stack-mcp-internal-effect-bearer-token",
        "abyss-stack-mcp:internal_effect",
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


def test_managed_startup_rejects_copied_or_equal_contour_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_token = "r" * 64
    candidate_token = "c" * 64
    effect_token = "e" * 64
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    read_path = credentials / "abyss-stack-mcp-read-bearer-token"
    candidate_path = credentials / "abyss-stack-mcp-candidate-bearer-token"
    effect_path = credentials / "abyss-stack-mcp-internal-effect-bearer-token"
    manifest_path = credentials / "abyss-stack-mcp-auth-manifest.json"
    read_path.write_text(read_token, encoding="utf-8")
    candidate_path.write_text(candidate_token, encoding="utf-8")
    effect_path.write_text(effect_token, encoding="utf-8")
    manifest = {
        "candidate_sha256": hashlib.sha256(
            candidate_token.encode("utf-8")
        ).hexdigest(),
        "read_sha256": hashlib.sha256(read_token.encode("utf-8")).hexdigest(),
        "internal_effect_sha256": hashlib.sha256(
            effect_token.encode("utf-8")
        ).hexdigest(),
        "schema_version": "abyss_stack_mcp_auth_manifest_v2",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("AOA_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials))
    monkeypatch.setenv("ABYSS_STACK_MCP_REQUIRE_AUTH_MANIFEST", "1")
    monkeypatch.delenv("ABYSS_STACK_MCP_READ_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("ABYSS_STACK_MCP_CANDIDATE_BEARER_TOKEN", raising=False)
    monkeypatch.delenv(
        "ABYSS_STACK_MCP_INTERNAL_EFFECT_BEARER_TOKEN", raising=False
    )

    assert "auth" in _auth_kwargs("read")
    assert "auth" in _auth_kwargs("candidate")
    assert "auth" in _auth_kwargs("internal_effect")

    candidate_path.write_text(read_token, encoding="utf-8")
    with pytest.raises(SystemExit, match="does not match"):
        _auth_kwargs("candidate")

    manifest["candidate_sha256"] = manifest["read_sha256"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit, match="must be distinct"):
        _auth_kwargs("read")
