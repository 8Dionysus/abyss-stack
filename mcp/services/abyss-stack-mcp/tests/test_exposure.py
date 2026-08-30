from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest

from abyss_stack_mcp.core import StackMCPError, canonical_json_bytes, sha256_digest
from abyss_stack_mcp.exposure import (
    ExposureInvocationAuthorization,
    ExposureRuntime,
    StackExposurePlan,
    StackExposureTool,
)


NOW = datetime(2026, 8, 26, 5, 0, tzinfo=timezone.utc)


def digest(letter: str) -> str:
    return "sha256:" + letter * 64


def _payload() -> dict:
    tool = StackExposureTool(
        tool_id="knowledge-inspect.inspect-knowledge",
        capability_id="knowledge-inspect",
        primitive_id="inspect-knowledge",
        mcp_name="runtime-inspect",
        effect_class="observe",
        policy_family="read",
        input_schema_ref="owner://aoa-kag/schema/input",
        output_schema_ref="owner://aoa-kag/schema/output",
        schema_digest=digest("c"),
        effect_ceiling="read",
    )
    tools = [tool.model_dump(mode="json")]
    snapshot_body = {
        "schema_version": "aoa_organ_exposure_snapshot_v1",
        "source_digest": digest("e"),
        "tools": tools,
        "visible_tool_ids": [tool.tool_id],
        "rendered_schema_digest": digest("f"),
        "rendered_bytes": len(canonical_json_bytes(tools)),
        "rendered_tokens": 17,
        "token_count_posture": "estimated",
        "token_count_method": "fixture-estimate-v1",
        "observed_at": NOW.isoformat().replace("+00:00", "Z"),
        "expires_at": (NOW + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "refusal_reasons": [],
    }
    snapshot_body["rendered_schema_digest"] = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(tools)).hexdigest()
    )
    snapshot = {
        **snapshot_body,
        "snapshot_id": (
            "sha256:" + hashlib.sha256(canonical_json_bytes(snapshot_body)).hexdigest()
        ),
    }
    payload = {
        "schema_version": "aoa_organ_exposure_plan_v1",
        "plan_id": digest("a"),
        "plan_state": "candidate",
        "execution_authorized": False,
        "activation_authorized": False,
        "feature_enabled": True,
        "baseline_ready": True,
        "request_id": "exposure-request-1",
        "capability": {
            "organ_id": "aoa-kag",
            "capability_id": "knowledge-inspect",
            "qualified_capability_id": "aoa-kag:aoa-kag:knowledge-inspect",
            "owners": {
                "source_owner": "aoa-kag",
                "access_owner": "aoa-kag",
                "control_owner": "aoa-sdk",
                "runtime_owner": "abyss-stack",
                "proof_owner": "aoa-evals",
                "acceptance_owner": "aoa-kag",
            },
            "capability_digest": digest("b"),
            "schema_digest": digest("c"),
            "source_revision": {"revision": "source-1", "digest": digest("e")},
            "freshness": {
                "state": "fresh",
                "source_ref": "owner://aoa-kag/exposure",
                "source_digest": digest("e"),
                "observed_at": NOW.isoformat().replace("+00:00", "Z"),
                "expires_at": (NOW + timedelta(minutes=5))
                .isoformat()
                .replace("+00:00", "Z"),
                "ttl_seconds": 300,
                "provider_watermark": "exposure-1",
                "reason_codes": [],
            },
            "effect_ceiling": "read",
            "approval_ref": None,
            "rollback_route": "owner://aoa-kag/rollback",
        },
        "requested_policy_family": "read",
        "requested_primitive_ids": ["inspect-knowledge"],
        "visible_tools": tools,
        "rendered_snapshot": snapshot,
        "approval_ref": None,
        "rollback_bindings": [],
        "rollback_route": "owner://aoa-kag/rollback",
        "requested_at": NOW.isoformat().replace("+00:00", "Z"),
        "expires_at": (NOW + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "expansion_reasons": ["baseline_gate_satisfied"],
        "refusal_reasons": [],
    }
    unsigned = {key: value for key, value in payload.items() if key != "plan_id"}
    payload["plan_id"] = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    )
    return payload


def _effect_payload() -> dict:
    payload = _payload()
    tool = payload["visible_tools"][0]
    tool.update(
        {
            "tool_id": "knowledge-publish.publish-change",
            "capability_id": "knowledge-publish",
            "primitive_id": "publish-change",
            "mcp_name": "runtime-publish",
            "effect_class": "external_change",
            "policy_family": "external_effect",
            "effect_ceiling": "external_effect",
        }
    )
    capability = payload["capability"]
    capability.update(
        {
            "capability_id": "knowledge-publish",
            "qualified_capability_id": "aoa-kag:aoa-kag:knowledge-publish",
            "effect_ceiling": "external_effect",
        }
    )
    payload["requested_policy_family"] = "external_effect"
    payload["requested_primitive_ids"] = ["publish-change"]
    payload["rollback_bindings"] = [
        {
            "tool_id": "knowledge-publish.publish-change",
            "primitive_id": "publish-change",
            "rollback_route": "owner://rollback/publish",
        }
    ]
    snapshot = payload["rendered_snapshot"]
    snapshot["tools"] = [tool]
    snapshot["visible_tool_ids"] = [tool["tool_id"]]
    snapshot["rendered_bytes"] = len(canonical_json_bytes([tool]))
    snapshot["rendered_schema_digest"] = (
        "sha256:" + hashlib.sha256(canonical_json_bytes([tool])).hexdigest()
    )
    snapshot_unsigned = {
        key: value for key, value in snapshot.items() if key != "snapshot_id"
    }
    snapshot["snapshot_id"] = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(snapshot_unsigned)).hexdigest()
    )
    unsigned = {key: value for key, value in payload.items() if key != "plan_id"}
    payload["plan_id"] = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    )
    return payload


def _redigest_plan(payload: dict) -> dict:
    unsigned = {key: value for key, value in payload.items() if key != "plan_id"}
    payload["plan_id"] = sha256_digest(unsigned)
    return payload


def test_stack_materialization_is_default_off_and_receipt_bound() -> None:
    runtime = ExposureRuntime(clock=lambda: NOW)
    receipt = runtime.materialize(_payload())

    assert receipt.decision == "denied"
    assert "progressive_exposure_disabled" in receipt.reason_codes
    assert "baseline_admission_required" in receipt.reason_codes
    assert receipt.activation_authorized is False
    assert receipt.execution_authorized is False
    assert receipt.receipt_id.startswith("sha256:")
    assert len(runtime.recent_receipts()) == 1


def test_published_plan_schema_accepts_the_sdk_ingress_shape() -> None:
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "progressive-exposure-plan.schema.json"
        ).read_text(encoding="utf-8")
    )

    assert list(jsonschema.Draft202012Validator(schema).iter_errors(_payload())) == []


def test_effect_plan_preserves_primitive_rollback_without_executing_owner_tool() -> (
    None
):
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
    )

    materialization = runtime.materialize(_effect_payload())

    assert materialization.decision == "allowed"
    assert materialization.rollback_bindings[0].rollback_route == (
        "owner://rollback/publish"
    )
    denied = runtime.invoke(
        materialization.receipt_id,
        request_id="effect-invocation",
        caller_id="test-caller",
        tool_id="knowledge-publish.publish-change",
        arguments={"change": "bounded"},
        authorization_ref=None,
    )
    assert denied.decision == "denied"
    assert "non_read_tool_requires_runtime_effect_authority" in denied.reason_codes
    assert "owner_tool_execution_not_owned_by_stack" in denied.reason_codes


def test_admitted_runtime_requires_canonical_baseline_receipt() -> None:
    try:
        ExposureRuntime(
            progressive_exposure_enabled=True,
            baseline_admitted=True,
            baseline_admission_ref="receipt://unrelated/baseline",
            clock=lambda: NOW,
        )
    except ValueError as exc:
        assert "canonical d0 receipt" in str(exc)
    else:
        raise AssertionError("non-canonical baseline admission must fail closed")


def test_non_admitted_runtime_rejects_any_baseline_receipt() -> None:
    secret_ref = "Bearer sk-" + "c" * 48

    with pytest.raises(ValueError, match="non-admitted runtime") as exc_info:
        ExposureRuntime(
            progressive_exposure_enabled=False,
            baseline_admitted=False,
            baseline_admission_ref=secret_ref,
            clock=lambda: NOW,
        )

    assert secret_ref not in str(exc_info.value)


def test_admitted_runtime_requires_explicit_invocation_authority_and_emits_receipts() -> (
    None
):
    emitted: list[dict] = []
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
        receipt_sink=emitted.append,
    )
    materialization = runtime.materialize(_payload())
    assert materialization.decision == "allowed"
    assert materialization.baseline_admission_ref == "receipt://d0/baseline-ready"
    assert materialization.visible_tool_ids == ("knowledge-inspect.inspect-knowledge",)
    assert materialization.rollback_bindings == ()

    denied = runtime.invoke(
        materialization.receipt_id,
        request_id="invoke-denied",
        caller_id="test-caller",
        tool_id="knowledge-inspect.inspect-knowledge",
        arguments={"query": "bounded"},
        authorization_ref=None,
    )
    assert denied.decision == "denied"
    assert "invocation_authorization_required" in denied.reason_codes
    assert "owner_tool_execution_not_owned_by_stack" in denied.reason_codes

    authorization_body = {
        "owner": "aoa-kag",
        "plan_id": _payload()["plan_id"],
        "materialization_receipt_id": materialization.receipt_id,
        "tool_id": "knowledge-inspect.inspect-knowledge",
        "caller_id": "test-caller",
        "issued_at": NOW.isoformat().replace("+00:00", "Z"),
        "expires_at": (NOW + timedelta(minutes=4)).isoformat().replace("+00:00", "Z"),
    }
    authorization_body["authorization_id"] = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(authorization_body)).hexdigest()
    )
    recorded = runtime.invoke(
        materialization.receipt_id,
        request_id="invoke-allowed",
        caller_id="test-caller",
        tool_id="knowledge-inspect.inspect-knowledge",
        arguments={"query": "bounded"},
        authorization_ref=ExposureInvocationAuthorization.model_validate(
            authorization_body
        ),
    )
    assert recorded.decision == "denied"
    assert "owner_tool_execution_not_owned_by_stack" in recorded.reason_codes
    assert recorded.invocation_authorized is False
    assert recorded.runtime_effect_authorized is False
    assert recorded.output_digest is None
    assert recorded.authorization_id == authorization_body["authorization_id"]
    assert len(emitted) == 3

    retained = runtime.recent_receipts()
    retained[-1]["reason_codes"].append("tampered")
    assert "tampered" not in runtime.recent_receipts()[-1]["reason_codes"]


def test_invocation_authorization_owner_and_malformed_request_fail_closed() -> None:
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
    )
    materialization = runtime.materialize(_payload())
    authorization_body = {
        "owner": "unrelated-owner",
        "plan_id": _payload()["plan_id"],
        "materialization_receipt_id": materialization.receipt_id,
        "tool_id": "knowledge-inspect.inspect-knowledge",
        "caller_id": "test-caller",
        "issued_at": NOW.isoformat().replace("+00:00", "Z"),
        "expires_at": (NOW + timedelta(minutes=4)).isoformat().replace("+00:00", "Z"),
    }
    authorization_body["authorization_id"] = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(authorization_body)).hexdigest()
    )
    denied = runtime.invoke(
        materialization.receipt_id,
        request_id="",
        caller_id="test-caller",
        tool_id="knowledge-inspect.inspect-knowledge",
        arguments={"query": "bounded"},
        authorization_ref=authorization_body,
    )
    assert denied.decision == "denied"
    assert "malformed_request_id" in denied.reason_codes
    assert "invocation_authorization_owner_mismatch" in denied.reason_codes
    assert "owner_tool_execution_not_owned_by_stack" in denied.reason_codes


def test_materialization_retains_a_revalidated_plan_snapshot() -> None:
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
    )
    plan = StackExposurePlan.from_sdk_payload(_payload())
    materialization = runtime.materialize(plan)

    plan.capability.owners["access_owner"] = "tampered-owner"
    authorization_body = {
        "owner": "aoa-kag",
        "plan_id": plan.plan_id,
        "materialization_receipt_id": materialization.receipt_id,
        "tool_id": "knowledge-inspect.inspect-knowledge",
        "caller_id": "test-caller",
        "issued_at": NOW.isoformat().replace("+00:00", "Z"),
        "expires_at": (NOW + timedelta(minutes=4)).isoformat().replace("+00:00", "Z"),
    }
    authorization_body["authorization_id"] = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(authorization_body)).hexdigest()
    )

    receipt = runtime.invoke(
        materialization.receipt_id,
        request_id="snapshot-bound",
        caller_id="test-caller",
        tool_id="knowledge-inspect.inspect-knowledge",
        arguments={"query": "bounded"},
        authorization_ref=authorization_body,
    )

    assert "invocation_authorization_owner_mismatch" not in receipt.reason_codes
    assert "owner_tool_execution_not_owned_by_stack" in receipt.reason_codes


def test_non_json_invocation_arguments_emit_a_denial_receipt() -> None:
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
    )
    materialization = runtime.materialize(_payload())

    receipt = runtime.invoke(
        materialization.receipt_id,
        request_id="malformed-arguments",
        caller_id="test-caller",
        tool_id="knowledge-inspect.inspect-knowledge",
        arguments={"query": {"not", "json"}},
        authorization_ref=None,
    )

    assert receipt.decision == "denied"
    assert "malformed_invocation_arguments" in receipt.reason_codes
    assert receipt.input_digest == sha256_digest({})


def test_stale_capability_freshness_is_not_materialized() -> None:
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
    )
    payload = _payload()
    payload["capability"]["freshness"]["state"] = "stale"
    payload["capability"]["freshness"]["reason_codes"] = ["owner_stale"]

    receipt = runtime.materialize(_redigest_plan(payload))

    assert receipt.decision == "denied"
    assert "capability_freshness_not_usable" in receipt.reason_codes


def test_inconsistent_capability_freshness_ttl_is_rejected() -> None:
    payload = _payload()
    payload["capability"]["freshness"]["ttl_seconds"] = 301

    with pytest.raises(Exception, match="failed stack normalization"):
        StackExposurePlan.from_sdk_payload(_redigest_plan(payload))


def test_secret_rollback_route_is_denied_without_receipt_disclosure() -> None:
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
    )
    payload = _effect_payload()
    payload["rollback_bindings"][0]["rollback_route"] = (
        "https://owner.invalid/rollback?token=secret-value"
    )

    receipt = runtime.materialize(_redigest_plan(payload))

    assert receipt.decision == "denied"
    assert "secret_material_rejected" in receipt.reason_codes
    assert receipt.rollback_bindings == ()
    assert "secret-value" not in json.dumps(runtime.recent_receipts())


def test_exposure_runtime_bounds_receipts_and_prunes_expired_plans() -> None:
    now = NOW
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: now,
    )
    materialization = runtime.materialize(_payload())
    for _ in range(300):
        runtime.materialize(_payload())

    assert len(runtime.recent_receipts()) == 256
    now = NOW + timedelta(minutes=6)
    denied = runtime.invoke(
        materialization.receipt_id,
        request_id="after-expiry",
        caller_id="test-caller",
        tool_id="knowledge-inspect.inspect-knowledge",
        arguments={},
        authorization_ref=None,
    )
    assert "materialization_receipt_not_found" in denied.reason_codes


def test_secret_receipt_identifier_is_replaced_before_emission() -> None:
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
    )
    materialization = runtime.materialize(_payload())
    secret_caller = "Bearer sk-" + "a" * 48

    receipt = runtime.invoke(
        materialization.receipt_id,
        request_id="secret-id-case",
        caller_id=secret_caller,
        tool_id="knowledge-inspect.inspect-knowledge",
        arguments={},
        authorization_ref=None,
    )

    assert receipt.caller_id == "invalid-caller-id"
    assert "secret_material_rejected" in receipt.reason_codes
    assert secret_caller not in json.dumps(runtime.recent_receipts())


def test_secret_materialization_identifier_is_replaced_before_emission() -> None:
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
    )
    payload = _payload()
    secret_request = "Bearer sk-" + "b" * 48
    payload["request_id"] = secret_request

    receipt = runtime.materialize(_redigest_plan(payload))

    assert receipt.decision == "denied"
    assert receipt.request_id == "invalid-request-id"
    assert receipt.visible_tool_ids == ()
    assert receipt.rollback_bindings == ()
    assert "secret_material_rejected" in receipt.reason_codes
    assert secret_request not in json.dumps(runtime.recent_receipts())


def test_secret_plan_refusal_reason_is_replaced_before_emission() -> None:
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
    )
    payload = _payload()
    secret_reason = "Bearer sk-" + "d" * 48
    payload["plan_state"] = "blocked"
    payload["requested_primitive_ids"] = []
    payload["visible_tools"] = []
    payload["expansion_reasons"] = []
    payload["refusal_reasons"] = [secret_reason]
    snapshot = payload["rendered_snapshot"]
    snapshot["tools"] = []
    snapshot["visible_tool_ids"] = []
    snapshot["rendered_schema_digest"] = sha256_digest([])
    snapshot["rendered_bytes"] = len(canonical_json_bytes([]))
    snapshot_body = {
        key: value for key, value in snapshot.items() if key != "snapshot_id"
    }
    snapshot["snapshot_id"] = sha256_digest(snapshot_body)

    receipt = runtime.materialize(_redigest_plan(payload))

    assert receipt.decision == "denied"
    assert "candidate_plan_required" in receipt.reason_codes
    assert "secret_material_rejected" in receipt.reason_codes
    assert secret_reason not in receipt.reason_codes
    assert secret_reason not in json.dumps(runtime.recent_receipts())


def test_oversized_plan_is_rejected_before_retention_or_emission() -> None:
    emitted: list[dict] = []
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
        receipt_sink=emitted.append,
    )
    payload = _payload()
    payload["approval_ref"] = {"owner_note": "x" * 1_048_576}

    with pytest.raises(StackMCPError, match="canonical byte limit"):
        runtime.materialize(_redigest_plan(payload))

    assert emitted == []
    assert runtime.recent_receipts() == ()


def test_plan_collection_counts_are_bounded() -> None:
    payload = _payload()
    payload["refusal_reasons"] = ["bounded"] * 257

    with pytest.raises(StackMCPError, match="failed stack normalization"):
        StackExposurePlan.from_sdk_payload(_redigest_plan(payload))


def test_non_json_plan_is_rejected_before_normalization() -> None:
    runtime = ExposureRuntime(clock=lambda: NOW)
    payload = _payload()
    payload["approval_ref"] = {"not_json": object()}

    with pytest.raises(StackMCPError, match="failed stack normalization"):
        runtime.materialize(payload)


def test_malformed_secret_plan_does_not_chain_private_validation_input() -> None:
    secret_value = "Bearer sk-" + "e" * 48
    payload = _payload()
    payload["password"] = secret_value

    with pytest.raises(StackMCPError) as exc_info:
        StackExposurePlan.from_sdk_payload(payload)

    assert exc_info.value.__cause__ is None
    assert secret_value not in str(exc_info.value)


@pytest.mark.parametrize(
    "arguments",
    [
        {"item": "x" * 1_048_576},
        {f"item-{index}": index for index in range(257)},
    ],
)
def test_invocation_arguments_are_bounded_before_hashing(arguments: dict) -> None:
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
    )
    materialization = runtime.materialize(_payload())

    receipt = runtime.invoke(
        materialization.receipt_id,
        request_id="bounded-invocation",
        caller_id="test-caller",
        tool_id="knowledge-inspect.inspect-knowledge",
        arguments=arguments,
        authorization_ref=None,
    )

    assert "invocation_arguments_too_large" in receipt.reason_codes
    assert receipt.input_digest == sha256_digest({})


@pytest.mark.parametrize(
    "authorization_ref",
    [
        {"owner": "x" * 65_536},
        {f"item-{index}": index for index in range(65)},
    ],
)
def test_invocation_authorization_is_bounded_before_validation(
    authorization_ref: dict,
) -> None:
    runtime = ExposureRuntime(
        progressive_exposure_enabled=True,
        baseline_admitted=True,
        baseline_admission_ref="receipt://d0/baseline-ready",
        clock=lambda: NOW,
    )
    materialization = runtime.materialize(_payload())

    receipt = runtime.invoke(
        materialization.receipt_id,
        request_id="bounded-authorization",
        caller_id="test-caller",
        tool_id="knowledge-inspect.inspect-knowledge",
        arguments={},
        authorization_ref=authorization_ref,
    )

    assert "invocation_authorization_too_large" in receipt.reason_codes
    assert receipt.authorization_id is None


def test_stack_normalization_rejects_visible_tool_schema_drift() -> None:
    payload = _payload()
    payload["rendered_snapshot"]["visible_tool_ids"] = ["unexpected"]
    try:
        StackExposurePlan.from_sdk_payload(payload)
    except Exception as exc:
        assert "exposure plan failed stack normalization" in str(exc)
    else:
        raise AssertionError("schema drift must fail closed")


def test_stack_normalization_rejects_plan_id_tampering() -> None:
    payload = _payload()
    payload["expires_at"] = (
        (NOW + timedelta(minutes=4)).isoformat().replace("+00:00", "Z")
    )
    try:
        StackExposurePlan.from_sdk_payload(payload)
    except Exception as exc:
        assert "exposure plan failed stack normalization" in str(exc)
    else:
        raise AssertionError("plan identity drift must fail closed")
