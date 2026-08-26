"""Runtime-owner gate for candidate progressive tool exposure.

The contour is intentionally not registered in the normal MCP server yet.  It
is a source-level, default-off adapter that can be admitted only after the
baseline owner supplies an explicit handoff.  It materializes an exact SDK
plan and can invoke read-only visible tools only when a separate caller
authorization reference is supplied.  It never authorizes effects, admission,
owner acceptance, or proof.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .core import (
    StackMCPError,
    _reject_secret_material,
    canonical_json_bytes,
    sha256_digest,
)


Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
NonEmpty = Annotated[str, Field(min_length=1, max_length=512)]
PolicyFamily = Literal["read", "candidate"]
EffectClass = Literal["observe", "derive", "validate", "prepare_candidate"]
ExposureDecision = Literal["allowed", "denied"]

_POLICY_RANK = {"read": 0, "candidate": 1}
_EFFECT_POLICY = {
    "observe": "read",
    "derive": "read",
    "validate": "read",
    "prepare_candidate": "candidate",
}


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("exposure timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class StrictExposureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StackExposureTool(StrictExposureModel):
    tool_id: NonEmpty
    capability_id: NonEmpty
    primitive_id: NonEmpty
    mcp_name: NonEmpty
    effect_class: EffectClass
    policy_family: PolicyFamily
    input_schema_ref: NonEmpty | None = None
    output_schema_ref: NonEmpty
    schema_digest: Digest
    effect_ceiling: PolicyFamily

    @model_validator(mode="after")
    def validate_tool(self) -> StackExposureTool:
        if self.tool_id != f"{self.capability_id}.{self.primitive_id}":
            raise ValueError("stack exposure tool id is not capability-qualified")
        if self.policy_family != _EFFECT_POLICY[self.effect_class]:
            raise ValueError("stack exposure effect and policy family do not match")
        if _POLICY_RANK[self.policy_family] > _POLICY_RANK[self.effect_ceiling]:
            raise ValueError("stack exposure tool exceeds effect ceiling")
        return self


class StackExposureSnapshot(StrictExposureModel):
    schema_version: Literal["aoa_organ_exposure_snapshot_v1"]
    snapshot_id: Digest
    source_digest: Digest
    tools: tuple[StackExposureTool, ...] = ()
    visible_tool_ids: tuple[NonEmpty, ...] = ()
    rendered_schema_digest: Digest
    rendered_bytes: Annotated[int, Field(ge=0)]
    rendered_tokens: Annotated[int, Field(ge=0)] | None = None
    token_count_posture: Literal[
        "measured", "provider_reported", "estimated", "partial", "unknown", "missing"
    ]
    token_count_method: NonEmpty | None = None
    observed_at: datetime
    expires_at: datetime | None = None
    refusal_reasons: tuple[NonEmpty, ...] = ()

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        return _aware_utc(value)

    @model_validator(mode="after")
    def validate_snapshot(self) -> StackExposureSnapshot:
        if self.visible_tool_ids != tuple(tool.tool_id for tool in self.tools):
            raise ValueError("stack snapshot visible ids do not preserve order")
        rendered = [tool.model_dump(mode="json") for tool in self.tools]
        if self.rendered_bytes != len(canonical_json_bytes(rendered)):
            raise ValueError("stack snapshot byte accounting is inconsistent")
        if self.rendered_schema_digest != _digest(rendered):
            raise ValueError("stack snapshot schema digest is inconsistent")
        unsigned = {
            key: value
            for key, value in self.model_dump(mode="json").items()
            if key != "snapshot_id"
        }
        if self.snapshot_id != _digest(unsigned):
            raise ValueError("stack snapshot id is not content addressed")
        if self.rendered_tokens is None and self.token_count_posture in {
            "measured",
            "provider_reported",
            "estimated",
        }:
            raise ValueError("counted token posture requires a token count")
        if self.rendered_tokens is not None and self.token_count_posture in {
            "unknown",
            "missing",
        }:
            raise ValueError("known token count cannot have unknown posture")
        if self.expires_at is not None and self.expires_at <= self.observed_at:
            raise ValueError("stack snapshot expiry must follow observation")
        return self


class StackExposurePlan(StrictExposureModel):
    """Minimal normalized view of the SDK candidate consumed by stack."""

    schema_version: Literal["aoa_organ_exposure_plan_v1"]
    plan_id: Digest
    plan_state: Literal["blocked", "candidate"]
    execution_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    feature_enabled: bool
    baseline_ready: bool
    request_id: NonEmpty
    organ_id: NonEmpty
    capability_id: NonEmpty
    qualified_capability_id: NonEmpty
    capability_schema_digest: Digest
    requested_policy_family: PolicyFamily
    requested_primitive_ids: tuple[NonEmpty, ...] = ()
    visible_tools: tuple[StackExposureTool, ...] = ()
    rendered_snapshot: StackExposureSnapshot
    rollback_route: NonEmpty
    requested_at: datetime
    expires_at: datetime
    expansion_reasons: tuple[NonEmpty, ...] = ()
    refusal_reasons: tuple[NonEmpty, ...] = ()

    @field_validator("requested_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        result = _aware_utc(value)
        assert result is not None
        return result

    @model_validator(mode="after")
    def validate_plan(self) -> StackExposurePlan:
        if self.expires_at <= self.requested_at:
            raise ValueError("stack exposure plan expiry must follow request")
        if self.visible_tools != self.rendered_snapshot.tools:
            raise ValueError("stack plan and snapshot visible tools differ")
        if self.plan_state == "blocked" and (
            self.visible_tools or self.rendered_snapshot.rendered_bytes != 2
        ):
            raise ValueError("blocked stack plan cannot carry visible schemas")
        if self.plan_state == "candidate" and not self.expansion_reasons:
            raise ValueError("candidate stack plan requires expansion reasons")
        return self

    @classmethod
    def from_sdk_payload(cls, payload: Mapping[str, Any]) -> StackExposurePlan:
        """Normalize the SDK's nested capability binding without importing SDK code."""

        capability = payload.get("capability")
        if not isinstance(capability, Mapping):
            raise StackMCPError("exposure plan capability binding is missing")
        required_capability_keys = {
            "organ_id",
            "capability_id",
            "qualified_capability_id",
            "schema_digest",
            "effect_ceiling",
            "rollback_route",
        }
        if not required_capability_keys.issubset(capability):
            raise StackMCPError("exposure capability binding is incomplete")
        normalized = {
            "schema_version": payload.get("schema_version"),
            "plan_id": payload.get("plan_id"),
            "plan_state": payload.get("plan_state"),
            "execution_authorized": payload.get("execution_authorized", False),
            "activation_authorized": payload.get("activation_authorized", False),
            "feature_enabled": payload.get("feature_enabled", False),
            "baseline_ready": payload.get("baseline_ready", False),
            "request_id": payload.get("request_id"),
            "organ_id": capability.get("organ_id"),
            "capability_id": capability.get("capability_id"),
            "qualified_capability_id": capability.get("qualified_capability_id"),
            "capability_schema_digest": capability.get("schema_digest"),
            "requested_policy_family": payload.get("requested_policy_family"),
            "requested_primitive_ids": payload.get("requested_primitive_ids", ()),
            "visible_tools": payload.get("visible_tools", ()),
            "rendered_snapshot": payload.get("rendered_snapshot"),
            "rollback_route": payload.get("rollback_route") or capability.get("rollback_route"),
            "requested_at": payload.get("requested_at"),
            "expires_at": payload.get("expires_at"),
            "expansion_reasons": payload.get("expansion_reasons", ()),
            "refusal_reasons": payload.get("refusal_reasons", ()),
        }
        try:
            return cls.model_validate(normalized)
        except Exception as exc:
            raise StackMCPError("exposure plan failed stack normalization") from exc


class ExposureMaterializationReceipt(StrictExposureModel):
    schema_version: Literal["abyss_stack_exposure_materialization_receipt_v1"] = (
        "abyss_stack_exposure_materialization_receipt_v1"
    )
    receipt_id: Digest
    request_id: NonEmpty
    plan_id: Digest
    decision: ExposureDecision
    reason_codes: tuple[NonEmpty, ...] = ()
    observed_at: datetime
    expires_at: datetime
    snapshot_id: Digest
    source_digest: Digest
    visible_tool_ids: tuple[NonEmpty, ...] = ()
    visible_bytes: Annotated[int, Field(ge=0)]
    visible_tokens: Annotated[int, Field(ge=0)] | None = None
    baseline_admission_ref: NonEmpty | None = None
    activation_authorized: Literal[False] = False
    execution_authorized: Literal[False] = False
    contains_secrets: Literal[False] = False
    instruction_authority: Literal["none"] = "none"

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        result = _aware_utc(value)
        assert result is not None
        return result

    @model_validator(mode="after")
    def validate_receipt(self) -> ExposureMaterializationReceipt:
        if self.expires_at <= self.observed_at:
            raise ValueError("materialization receipt expiry must follow observation")
        if self.decision == "allowed" and self.reason_codes:
            raise ValueError("allowed materialization cannot carry refusal reasons")
        if self.decision == "denied" and not self.reason_codes:
            raise ValueError("denied materialization requires refusal reasons")
        unsigned = {
            key: value
            for key, value in self.model_dump(mode="json").items()
            if key != "receipt_id"
        }
        if self.receipt_id != _digest(unsigned):
            raise ValueError("materialization receipt id is not content addressed")
        return self


class ExposureInvocationReceipt(StrictExposureModel):
    schema_version: Literal["abyss_stack_exposure_invocation_receipt_v1"] = (
        "abyss_stack_exposure_invocation_receipt_v1"
    )
    receipt_id: Digest
    request_id: NonEmpty
    materialization_receipt_id: Digest
    plan_id: Digest
    tool_id: NonEmpty
    policy_family: PolicyFamily
    effect_class: EffectClass
    decision: ExposureDecision
    reason_codes: tuple[NonEmpty, ...] = ()
    input_digest: Digest
    output_digest: Digest | None = None
    observed_at: datetime
    invocation_authorized: bool = False
    runtime_effect_authorized: Literal[False] = False
    contains_secrets: Literal[False] = False
    instruction_authority: Literal["none"] = "none"

    @field_validator("observed_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        result = _aware_utc(value)
        assert result is not None
        return result

    @model_validator(mode="after")
    def validate_receipt(self) -> ExposureInvocationReceipt:
        if self.decision == "allowed":
            if self.output_digest is None or not self.invocation_authorized:
                raise ValueError("allowed invocation requires authorization and output")
            if self.reason_codes:
                raise ValueError("allowed invocation cannot carry refusal reasons")
        elif self.output_digest is not None or not self.reason_codes:
            raise ValueError("denied invocation receipt shape is invalid")
        unsigned = {
            key: value
            for key, value in self.model_dump(mode="json").items()
            if key != "receipt_id"
        }
        if self.receipt_id != _digest(unsigned):
            raise ValueError("invocation receipt id is not content addressed")
        return self


class ExposureRuntime:
    """Default-off stack-side materialization and invocation gate."""

    def __init__(
        self,
        *,
        progressive_exposure_enabled: bool = False,
        baseline_admitted: bool = False,
        baseline_admission_ref: str | None = None,
        clock: Callable[[], datetime] | None = None,
        receipt_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if baseline_admitted and not baseline_admission_ref:
            raise ValueError("baseline admission requires an owner receipt reference")
        self._enabled = progressive_exposure_enabled
        self._baseline_admitted = baseline_admitted
        self._baseline_admission_ref = baseline_admission_ref
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._receipt_sink = receipt_sink
        self._materializations: dict[str, StackExposurePlan] = {}
        self._receipts: list[dict[str, Any]] = []

    def recent_receipts(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(item) for item in self._receipts)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise StackMCPError("exposure runtime clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _emit(self, receipt: StrictExposureModel) -> None:
        payload = receipt.model_dump(mode="json")
        self._receipts.append(payload)
        if self._receipt_sink is not None:
            self._receipt_sink(dict(payload))

    def materialize(
        self,
        plan: StackExposurePlan | Mapping[str, Any],
    ) -> ExposureMaterializationReceipt:
        normalized = (
            plan
            if isinstance(plan, StackExposurePlan)
            else StackExposurePlan.from_sdk_payload(plan)
        )
        now = self._now()
        reasons: list[str] = []
        if not self._enabled or not normalized.feature_enabled:
            reasons.append("progressive_exposure_disabled")
        if not self._baseline_admitted or not normalized.baseline_ready:
            reasons.append("baseline_admission_required")
        if normalized.plan_state != "candidate":
            reasons.extend(normalized.refusal_reasons or ("candidate_plan_required",))
        if normalized.expires_at <= now:
            reasons.append("exposure_plan_expired")
        if normalized.execution_authorized or normalized.activation_authorized:
            reasons.append("authorization_ceiling_violation")
        decision: ExposureDecision = "allowed" if not reasons else "denied"
        receipt_expires_at = max(normalized.expires_at, now + timedelta(seconds=1))
        receipt_body = {
            "schema_version": "abyss_stack_exposure_materialization_receipt_v1",
            "request_id": normalized.request_id,
            "plan_id": normalized.plan_id,
            "decision": decision,
            "reason_codes": sorted(set(reasons)),
            "observed_at": now.isoformat().replace("+00:00", "Z"),
            "expires_at": receipt_expires_at.isoformat().replace("+00:00", "Z"),
            "snapshot_id": normalized.rendered_snapshot.snapshot_id,
            "source_digest": normalized.rendered_snapshot.source_digest,
            "visible_tool_ids": list(normalized.rendered_snapshot.visible_tool_ids),
            "visible_bytes": normalized.rendered_snapshot.rendered_bytes,
            "visible_tokens": normalized.rendered_snapshot.rendered_tokens,
            "baseline_admission_ref": self._baseline_admission_ref,
            "activation_authorized": False,
            "execution_authorized": False,
            "contains_secrets": False,
            "instruction_authority": "none",
        }
        receipt = ExposureMaterializationReceipt.model_validate(
            {"receipt_id": _digest(receipt_body), **receipt_body}
        )
        if decision == "allowed":
            self._materializations[receipt.receipt_id] = normalized
        self._emit(receipt)
        return receipt
    def invoke(
        self,
        materialization_receipt_id: str,
        *,
        request_id: str,
        tool_id: str,
        arguments: Mapping[str, Any],
        authorization_ref: str | None,
        dispatch: Callable[[], dict[str, Any]] | None,
    ) -> ExposureInvocationReceipt:
        now = self._now()
        plan = self._materializations.get(materialization_receipt_id)
        reasons: list[str] = []
        tool = None
        if plan is None:
            reasons.append("materialization_receipt_not_found")
        else:
            tool = next(
                (item for item in plan.visible_tools if item.tool_id == tool_id),
                None,
            )
            if tool is None:
                reasons.append("tool_not_visible_in_materialization")
            elif tool.effect_class not in {"observe", "derive", "validate"}:
                reasons.append("non_read_tool_requires_runtime_effect_authority")
            if plan.expires_at <= now:
                reasons.append("materialization_expired")
        if not authorization_ref:
            reasons.append("invocation_authorization_required")
        if dispatch is None:
            reasons.append("invocation_dispatch_missing")
        try:
            _reject_secret_material(dict(arguments))
        except StackMCPError:
            reasons.append("secret_material_rejected")
        input_digest = sha256_digest(dict(arguments))
        effect_class: EffectClass = tool.effect_class if tool is not None else "observe"
        policy_family: PolicyFamily = tool.policy_family if tool is not None else "read"
        output_digest: str | None = None
        decision: ExposureDecision = "denied"
        if not reasons and dispatch is not None and tool is not None:
            try:
                result = dispatch()
                if not isinstance(result, dict):
                    reasons.append("invocation_result_invalid")
                else:
                    _reject_secret_material(result)
                    result_bytes = canonical_json_bytes(result)
                    if len(result_bytes) > 262_144:
                        reasons.append("invocation_output_size_limit_exceeded")
                    else:
                        output_digest = sha256_digest(result)
                        decision = "allowed"
            except StackMCPError:
                reasons.append("invocation_result_rejected")
            except Exception:
                reasons.append("invocation_dispatch_failed")
        body = {
            "schema_version": "abyss_stack_exposure_invocation_receipt_v1",
            "request_id": request_id,
            "materialization_receipt_id": materialization_receipt_id,
            "plan_id": plan.plan_id if plan is not None else "sha256:" + "0" * 64,
            "tool_id": tool_id,
            "policy_family": policy_family,
            "effect_class": effect_class,
            "decision": decision,
            "reason_codes": sorted(set(reasons)),
            "input_digest": input_digest,
            "output_digest": output_digest,
            "observed_at": now.isoformat().replace("+00:00", "Z"),
            "invocation_authorized": decision == "allowed",
            "runtime_effect_authorized": False,
            "contains_secrets": False,
            "instruction_authority": "none",
        }
        receipt = ExposureInvocationReceipt.model_validate(
            {"receipt_id": _digest(body), **body}
        )
        self._emit(receipt)
        return receipt
