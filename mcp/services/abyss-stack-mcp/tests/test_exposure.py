from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from abyss_stack_mcp.core import canonical_json_bytes
from abyss_stack_mcp.exposure import (
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
        schema_digest=digest("d"),
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
        "expires_at": (NOW + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
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
    return {
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
            "schema_digest": digest("c"),
            "effect_ceiling": "read",
            "rollback_route": "owner://aoa-kag/rollback",
        },
        "requested_policy_family": "read",
        "requested_primitive_ids": ["inspect-knowledge"],
        "visible_tools": tools,
        "rendered_snapshot": snapshot,
        "rollback_route": "owner://aoa-kag/rollback",
        "requested_at": NOW.isoformat().replace("+00:00", "Z"),
        "expires_at": (NOW + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "expansion_reasons": ["baseline_gate_satisfied"],
        "refusal_reasons": [],
    }


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


def test_admitted_runtime_requires_explicit_invocation_authority_and_emits_receipts() -> None:
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
    assert materialization.visible_tool_ids == (
        "knowledge-inspect.inspect-knowledge",
    )

    denied = runtime.invoke(
        materialization.receipt_id,
        request_id="invoke-denied",
        tool_id="knowledge-inspect.inspect-knowledge",
        arguments={"query": "bounded"},
        authorization_ref=None,
        dispatch=lambda: {"answer": "must-not-run"},
    )
    assert denied.decision == "denied"
    assert "invocation_authorization_required" in denied.reason_codes

    allowed = runtime.invoke(
        materialization.receipt_id,
        request_id="invoke-allowed",
        tool_id="knowledge-inspect.inspect-knowledge",
        arguments={"query": "bounded"},
        authorization_ref="owner://runtime/invocation-approval",
        dispatch=lambda: {"answer": "bounded-result"},
    )
    assert allowed.decision == "allowed"
    assert allowed.invocation_authorized is True
    assert allowed.runtime_effect_authorized is False
    assert allowed.output_digest is not None
    assert len(emitted) == 3


def test_stack_normalization_rejects_visible_tool_schema_drift() -> None:
    payload = _payload()
    payload["rendered_snapshot"]["visible_tool_ids"] = ["unexpected"]
    try:
        StackExposurePlan.from_sdk_payload(payload)
    except Exception as exc:
        assert "exposure plan failed stack normalization" in str(exc)
    else:
        raise AssertionError("schema drift must fail closed")
