"""Runtime-owner gate for candidate progressive tool exposure.

The contour is intentionally not registered in the normal MCP server yet. It
is a source-level, default-off adapter that can be admitted only after the
baseline owner supplies an explicit handoff. It materializes an exact SDK
plan and records invocation requests, but never proxies an owner tool. Owner
services own invocation; this package owns only bounded observation,
non-executing candidate materialization, and secret-free receipts.
"""

from __future__ import annotations

import copy
import hashlib
import math
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

from .core import (
    StackMCPError,
    _reject_secret_material,
    canonical_json_bytes,
    sha256_digest,
)


Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
NonEmpty = Annotated[str, Field(min_length=1, max_length=512)]
PolicyFamily = Literal["read", "candidate", "internal_effect", "external_effect"]
EffectClass = Literal[
    "observe",
    "derive",
    "validate",
    "prepare_candidate",
    "apply_runtime",
    "accept_source",
    "external_emit",
    "external_change",
]
ExposureDecision = Literal["allowed", "denied"]
ExposureFreshnessState = Literal[
    "fresh",
    "stale",
    "expired",
    "unknown",
    "missing",
    "partial",
    "estimated",
    "provider_reported",
]

_POLICY_RANK = {
    "read": 0,
    "candidate": 1,
    "internal_effect": 2,
    "external_effect": 3,
}
_EFFECT_POLICY = {
    "observe": "read",
    "derive": "read",
    "validate": "read",
    "prepare_candidate": "candidate",
    "apply_runtime": "internal_effect",
    "accept_source": "internal_effect",
    "external_emit": "external_effect",
    "external_change": "external_effect",
}
MAX_CANDIDATE_TTL = timedelta(minutes=10)
MAX_FUTURE_CLOCK_SKEW = timedelta(seconds=30)
MAX_RETAINED_EXPOSURE_RECEIPTS = 256
MAX_RETAINED_MATERIALIZATIONS = 256
MAX_EXPOSURE_PLAN_BYTES = 1_048_576
MAX_EXPOSURE_COLLECTION_ITEMS = 256
MAX_EXPOSURE_MAPPING_ITEMS = 64
MAX_INVOCATION_ARGUMENT_BYTES = 1_048_576
MAX_INVOCATION_ARGUMENT_ITEMS = 256
MAX_INVOCATION_AUTHORIZATION_BYTES = 65_536
MAX_INVOCATION_AUTHORIZATION_ITEMS = 64
MAX_EXPOSURE_JSON_DEPTH = 32
ZERO_DIGEST = "sha256:" + "0" * 64
BASELINE_ADMISSION_REF = "receipt://d0/baseline-ready"
CLAIM_LIMIT = (
    "This candidate records deterministic disclosure identity and visibility "
    "accounting only. It does not authorize activation, execute a tool, prove "
    "runtime reachability, establish owner acceptance, or issue central proof."
)


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("exposure timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _receipt_identifier_status(value: Any) -> Literal["valid", "malformed", "secret"]:
    if not isinstance(value, str) or not 1 <= len(value) <= 512:
        return "malformed"
    try:
        _reject_secret_material(value)
    except StackMCPError:
        return "secret"
    return "valid"


class _ExposurePayloadTooLarge(ValueError):
    pass


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(nested) for key, nested in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(nested) for nested in value]
    return value


FrozenJSONMapping = Annotated[
    Mapping[str, Any],
    PlainSerializer(_thaw_json, return_type=dict[str, Any], when_used="json"),
]


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(nested) for key, nested in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(nested) for nested in value)
    return value


def _bounded_json_preflight(
    value: Any,
    *,
    max_bytes: int,
    max_items: int,
) -> None:
    """Reject oversized JSON before constructing its complete serialization."""

    estimated_bytes = 0
    active_containers: set[int] = set()

    def add(amount: int) -> None:
        nonlocal estimated_bytes
        estimated_bytes += amount
        if estimated_bytes > max_bytes:
            raise _ExposurePayloadTooLarge("exposure JSON exceeds byte ceiling")

    def visit(item: Any, depth: int) -> None:
        if depth > MAX_EXPOSURE_JSON_DEPTH:
            raise _ExposurePayloadTooLarge("exposure JSON exceeds depth ceiling")
        if item is None:
            add(4)
        elif isinstance(item, bool):
            add(4 if item else 5)
        elif isinstance(item, int):
            bit_length = abs(item).bit_length()
            decimal_digits_upper_bound = (bit_length * 30103) // 100000 + 2
            add(decimal_digits_upper_bound + (1 if item < 0 else 0))
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise TypeError("exposure JSON contains a non-finite float")
            add(32)
        elif isinstance(item, str):
            add(2)
            for character in item:
                codepoint = ord(character)
                if character in {'"', "\\", "\b", "\f", "\n", "\r", "\t"}:
                    add(2)
                elif codepoint < 0x20:
                    add(6)
                elif codepoint <= 0x7F:
                    add(1)
                elif codepoint <= 0x7FF:
                    add(2)
                elif 0xD800 <= codepoint <= 0xDFFF:
                    raise TypeError("exposure JSON contains an invalid surrogate")
                elif codepoint <= 0xFFFF:
                    add(3)
                else:
                    add(4)
        elif isinstance(item, Mapping):
            if len(item) > max_items:
                raise _ExposurePayloadTooLarge(
                    "exposure JSON exceeds mapping item ceiling"
                )
            identity = id(item)
            if identity in active_containers:
                raise TypeError("exposure JSON contains a cycle")
            active_containers.add(identity)
            add(2 + max(0, len(item) - 1))
            try:
                for key, nested in item.items():
                    if not isinstance(key, str):
                        raise TypeError("exposure JSON mapping keys must be strings")
                    visit(key, depth + 1)
                    add(1)
                    visit(nested, depth + 1)
            finally:
                active_containers.remove(identity)
        elif isinstance(item, (list, tuple)):
            if len(item) > max_items:
                raise _ExposurePayloadTooLarge(
                    "exposure JSON exceeds collection item ceiling"
                )
            identity = id(item)
            if identity in active_containers:
                raise TypeError("exposure JSON contains a cycle")
            active_containers.add(identity)
            add(2 + max(0, len(item) - 1))
            try:
                for nested in item:
                    visit(nested, depth + 1)
            finally:
                active_containers.remove(identity)
        else:
            raise TypeError("exposure value is not JSON-compatible")

    visit(value, 0)


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
    tools: Annotated[
        tuple[StackExposureTool, ...], Field(max_length=MAX_EXPOSURE_COLLECTION_ITEMS)
    ] = ()
    visible_tool_ids: Annotated[
        tuple[NonEmpty, ...], Field(max_length=MAX_EXPOSURE_COLLECTION_ITEMS)
    ] = ()
    rendered_schema_digest: Digest
    rendered_bytes: Annotated[int, Field(ge=0)]
    rendered_tokens: Annotated[int, Field(ge=0)] | None = None
    token_count_posture: Literal[
        "measured", "provider_reported", "estimated", "partial", "unknown", "missing"
    ]
    token_count_method: NonEmpty | None = None
    observed_at: datetime
    expires_at: datetime
    refusal_reasons: Annotated[
        tuple[NonEmpty, ...], Field(max_length=MAX_EXPOSURE_COLLECTION_ITEMS)
    ] = ()

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
        if self.expires_at <= self.observed_at:
            raise ValueError("stack snapshot expiry must follow observation")
        return self


class ExposureRollbackBinding(StrictExposureModel):
    tool_id: NonEmpty
    primitive_id: NonEmpty
    rollback_route: NonEmpty


class StackExposureFreshness(StrictExposureModel):
    state: ExposureFreshnessState
    source_ref: NonEmpty
    source_digest: Digest
    observed_at: datetime
    expires_at: datetime | None = None
    ttl_seconds: Annotated[int | None, Field(ge=0)] = None
    provider_watermark: NonEmpty | None = None
    reason_codes: Annotated[
        tuple[NonEmpty, ...], Field(max_length=MAX_EXPOSURE_COLLECTION_ITEMS)
    ] = ()

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        return _aware_utc(value)

    @model_validator(mode="after")
    def validate_freshness(self) -> StackExposureFreshness:
        if self.expires_at is not None and self.expires_at <= self.observed_at:
            raise ValueError("stack exposure freshness expiry must follow observation")
        if self.state in {"fresh", "provider_reported"} and self.expires_at is None:
            raise ValueError("usable stack exposure freshness requires an expiry")
        if self.state != "fresh" and not self.reason_codes:
            raise ValueError("non-fresh stack exposure state requires reason codes")
        if self.expires_at is None:
            if self.ttl_seconds is not None:
                raise ValueError("freshness TTL requires an expiry")
        else:
            expected_ttl = int((self.expires_at - self.observed_at).total_seconds())
            if self.ttl_seconds != expected_ttl:
                raise ValueError("stack exposure freshness TTL is inconsistent")
        return self


class StackExposureCapabilityBinding(StrictExposureModel):
    """Nested capability identity carried by the SDK plan ingress."""

    organ_id: NonEmpty
    capability_id: NonEmpty
    qualified_capability_id: NonEmpty
    owners: Annotated[FrozenJSONMapping, Field(max_length=MAX_EXPOSURE_MAPPING_ITEMS)]
    capability_digest: Digest
    schema_digest: Digest
    source_revision: Annotated[
        FrozenJSONMapping, Field(max_length=MAX_EXPOSURE_MAPPING_ITEMS)
    ]
    freshness: StackExposureFreshness
    effect_ceiling: PolicyFamily
    approval_ref: Annotated[
        FrozenJSONMapping | None, Field(max_length=MAX_EXPOSURE_MAPPING_ITEMS)
    ] = None
    rollback_route: NonEmpty

    @model_validator(mode="after")
    def validate_identity(self) -> StackExposureCapabilityBinding:
        source_owner = self.owners.get("source_owner")
        if not isinstance(source_owner, str) or self.qualified_capability_id != (
            f"{source_owner}:{self.organ_id}:{self.capability_id}"
        ):
            raise ValueError("stack capability binding is not owner-qualified")
        object.__setattr__(self, "owners", _freeze_json(self.owners))
        object.__setattr__(self, "source_revision", _freeze_json(self.source_revision))
        object.__setattr__(self, "approval_ref", _freeze_json(self.approval_ref))
        return self


class StackExposurePlan(StrictExposureModel):
    """The nested SDK candidate shape consumed by stack."""

    schema_version: Literal["aoa_organ_exposure_plan_v1"]
    plan_id: Digest
    plan_state: Literal["blocked", "candidate"]
    execution_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    feature_enabled: bool
    baseline_ready: bool
    request_id: NonEmpty
    capability: StackExposureCapabilityBinding
    requested_policy_family: PolicyFamily
    requested_primitive_ids: Annotated[
        tuple[NonEmpty, ...], Field(max_length=MAX_EXPOSURE_COLLECTION_ITEMS)
    ] = ()
    visible_tools: Annotated[
        tuple[StackExposureTool, ...], Field(max_length=MAX_EXPOSURE_COLLECTION_ITEMS)
    ] = ()
    rendered_snapshot: StackExposureSnapshot
    approval_ref: Annotated[
        FrozenJSONMapping | None, Field(max_length=MAX_EXPOSURE_MAPPING_ITEMS)
    ] = None
    rollback_bindings: Annotated[
        tuple[ExposureRollbackBinding, ...],
        Field(max_length=MAX_EXPOSURE_COLLECTION_ITEMS),
    ] = ()
    rollback_route: NonEmpty
    requested_at: datetime
    expires_at: datetime
    expansion_reasons: Annotated[
        tuple[NonEmpty, ...], Field(max_length=MAX_EXPOSURE_COLLECTION_ITEMS)
    ] = ()
    refusal_reasons: Annotated[
        tuple[NonEmpty, ...], Field(max_length=MAX_EXPOSURE_COLLECTION_ITEMS)
    ] = ()
    claim_limit: Literal[CLAIM_LIMIT] = CLAIM_LIMIT

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
        if len(set(self.requested_primitive_ids)) != len(self.requested_primitive_ids):
            raise ValueError("stack plan requested primitive ids must be unique")
        if (
            _POLICY_RANK[self.requested_policy_family]
            > _POLICY_RANK[self.capability.effect_ceiling]
        ):
            raise ValueError("stack plan exceeds the capability effect ceiling")
        if self.visible_tools != self.rendered_snapshot.tools:
            raise ValueError("stack plan and snapshot visible tools differ")
        if self.rendered_snapshot.expires_at > self.expires_at:
            raise ValueError("stack snapshot outlives exposure plan")
        if self.rollback_route != self.capability.rollback_route:
            raise ValueError("stack plan rollback route is not capability-bound")
        for tool in self.visible_tools:
            if tool.capability_id != self.capability.capability_id:
                raise ValueError("stack plan visible tool capability is not bound")
            if tool.schema_digest != self.capability.schema_digest:
                raise ValueError(
                    "stack plan visible tool schema is not capability-bound"
                )
            if (
                _POLICY_RANK[tool.policy_family]
                > _POLICY_RANK[self.requested_policy_family]
            ):
                raise ValueError("stack plan visible tool exceeds requested policy")
        freshness_source_digest = self.capability.freshness.source_digest
        if self.rendered_snapshot.source_digest != freshness_source_digest:
            raise ValueError("stack snapshot source is not capability-bound")
        visible_primitives = tuple(tool.primitive_id for tool in self.visible_tools)
        expected_rollback_tools = tuple(
            (tool.tool_id, tool.primitive_id)
            for tool in self.visible_tools
            if tool.policy_family != "read"
        )
        actual_rollback_tools = tuple(
            (binding.tool_id, binding.primitive_id)
            for binding in self.rollback_bindings
        )
        if actual_rollback_tools != expected_rollback_tools:
            raise ValueError(
                "stack rollback bindings must preserve every effectful visible tool"
            )
        if (
            self.plan_state == "candidate"
            and visible_primitives != self.requested_primitive_ids
        ):
            raise ValueError(
                "stack plan visible tools do not match requested selection"
            )
        if self.plan_state == "blocked" and (
            self.visible_tools or self.rendered_snapshot.rendered_bytes != 2
        ):
            raise ValueError("blocked stack plan cannot carry visible schemas")
        if self.plan_state == "candidate" and not self.expansion_reasons:
            raise ValueError("candidate stack plan requires expansion reasons")
        object.__setattr__(self, "approval_ref", _freeze_json(self.approval_ref))
        unsigned = {
            key: value
            for key, value in self.model_dump(mode="json").items()
            if key not in {"plan_id", "claim_limit"}
        }
        if self.plan_id != _digest(unsigned):
            raise ValueError("stack exposure plan id is not content addressed")
        return self

    @classmethod
    def from_sdk_payload(cls, payload: Mapping[str, Any]) -> StackExposurePlan:
        """Validate the published nested SDK payload without importing SDK code."""

        try:
            _bounded_json_preflight(
                payload,
                max_bytes=MAX_EXPOSURE_PLAN_BYTES,
                max_items=MAX_EXPOSURE_COLLECTION_ITEMS,
            )
            if len(canonical_json_bytes(payload)) > MAX_EXPOSURE_PLAN_BYTES:
                raise _ExposurePayloadTooLarge
            return cls.model_validate(payload)
        except _ExposurePayloadTooLarge:
            raise StackMCPError("exposure plan exceeds canonical byte limit") from None
        except Exception:
            # Pydantic ValidationError values can retain the rejected input.
            # Never chain that private payload into the public runtime error.
            raise StackMCPError("exposure plan failed stack normalization") from None


class ExposureInvocationAuthorization(StrictExposureModel):
    """Exact external authorization for a request that stack will not execute."""

    authorization_id: Digest
    owner: NonEmpty
    plan_id: Digest
    materialization_receipt_id: Digest
    tool_id: NonEmpty
    caller_id: NonEmpty
    issued_at: datetime
    expires_at: datetime

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        result = _aware_utc(value)
        assert result is not None
        return result

    @model_validator(mode="after")
    def validate_authorization(self) -> ExposureInvocationAuthorization:
        if self.expires_at <= self.issued_at:
            raise ValueError("invocation authorization expiry must follow issue time")
        unsigned = {
            key: value
            for key, value in self.model_dump(mode="json").items()
            if key != "authorization_id"
        }
        if self.authorization_id != _digest(unsigned):
            raise ValueError("invocation authorization is not content addressed")
        return self


class ExposureMaterializationReceipt(StrictExposureModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"decision": {"const": "allowed"}},
                        "required": ["decision"],
                    },
                    "then": {
                        "properties": {
                            "baseline_admission_ref": {
                                "const": BASELINE_ADMISSION_REF
                            }
                        },
                        "required": ["baseline_admission_ref"],
                    },
                }
            ]
        },
    )
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
    rollback_bindings: tuple[ExposureRollbackBinding, ...] = ()
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
        if self.decision == "allowed":
            if self.reason_codes:
                raise ValueError("allowed materialization cannot carry refusal reasons")
            if self.baseline_admission_ref != BASELINE_ADMISSION_REF:
                raise ValueError(
                    "allowed materialization requires the canonical d0 receipt"
                )
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
    caller_id: NonEmpty
    materialization_receipt_id: Digest
    plan_id: Digest
    tool_id: NonEmpty
    policy_family: PolicyFamily
    effect_class: EffectClass
    decision: Literal["denied"] = "denied"
    reason_codes: tuple[NonEmpty, ...] = ()
    input_digest: Digest
    output_digest: Literal[None] = None
    authorization_id: Digest | None = None
    observed_at: datetime
    invocation_authorized: Literal[False] = False
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
        if not self.reason_codes:
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
        if baseline_admitted:
            if baseline_admission_ref != BASELINE_ADMISSION_REF:
                raise ValueError("baseline admission requires the canonical d0 receipt")
        elif baseline_admission_ref is not None:
            raise ValueError(
                "a non-admitted runtime cannot carry a baseline admission receipt"
            )
        self._enabled = progressive_exposure_enabled
        self._baseline_admitted = baseline_admitted
        self._baseline_admission_ref = baseline_admission_ref
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._receipt_sink = receipt_sink
        self._materializations: dict[str, StackExposurePlan] = {}
        self._receipts: list[dict[str, Any]] = []

    def recent_receipts(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(item) for item in self._receipts)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise StackMCPError("exposure runtime clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _emit(self, receipt: StrictExposureModel) -> None:
        payload = receipt.model_dump(mode="json")
        self._receipts.append(copy.deepcopy(payload))
        if len(self._receipts) > MAX_RETAINED_EXPOSURE_RECEIPTS:
            del self._receipts[:-MAX_RETAINED_EXPOSURE_RECEIPTS]
        if self._receipt_sink is not None:
            self._receipt_sink(copy.deepcopy(payload))

    def _prune_materializations(self, now: datetime) -> None:
        expired = [
            receipt_id
            for receipt_id, plan in self._materializations.items()
            if plan.expires_at <= now or plan.rendered_snapshot.expires_at <= now
        ]
        for receipt_id in expired:
            del self._materializations[receipt_id]

    def materialize(
        self,
        plan: StackExposurePlan | Mapping[str, Any],
    ) -> ExposureMaterializationReceipt:
        raw_plan_source = (
            plan.model_dump(mode="json")
            if isinstance(plan, StackExposurePlan)
            else plan
        )
        try:
            _bounded_json_preflight(
                raw_plan_source,
                max_bytes=MAX_EXPOSURE_PLAN_BYTES,
                max_items=MAX_EXPOSURE_COLLECTION_ITEMS,
            )
            raw_plan_bytes = canonical_json_bytes(raw_plan_source)
        except _ExposurePayloadTooLarge:
            raise StackMCPError("exposure plan exceeds canonical byte limit") from None
        except (TypeError, ValueError):
            raise StackMCPError("exposure plan failed stack normalization") from None
        if len(raw_plan_bytes) > MAX_EXPOSURE_PLAN_BYTES:
            raise StackMCPError("exposure plan exceeds canonical byte limit")
        raw_plan = copy.deepcopy(raw_plan_source)
        normalized = StackExposurePlan.from_sdk_payload(raw_plan)
        now = self._now()
        self._prune_materializations(now)
        reasons: list[str] = []
        plan_refusal_reasons: tuple[str, ...] = ()
        if not self._enabled or not normalized.feature_enabled:
            reasons.append("progressive_exposure_disabled")
        if not self._baseline_admitted or not normalized.baseline_ready:
            reasons.append("baseline_admission_required")
        if normalized.plan_state != "candidate":
            reasons.append("candidate_plan_required")
            plan_refusal_reasons = normalized.refusal_reasons
        if normalized.expires_at <= now:
            reasons.append("exposure_plan_expired")
        if normalized.requested_at > now + MAX_FUTURE_CLOCK_SKEW:
            reasons.append("exposure_request_from_future")
        if normalized.expires_at - normalized.requested_at > MAX_CANDIDATE_TTL:
            reasons.append("exposure_candidate_ttl_exceeded")
        if normalized.rendered_snapshot.observed_at > now + MAX_FUTURE_CLOCK_SKEW:
            reasons.append("exposure_snapshot_from_future")
        if normalized.rendered_snapshot.expires_at <= now:
            reasons.append("exposure_snapshot_expired")
        if (
            normalized.rendered_snapshot.expires_at
            - normalized.rendered_snapshot.observed_at
            > MAX_CANDIDATE_TTL
        ):
            reasons.append("exposure_snapshot_ttl_exceeded")
        freshness = normalized.capability.freshness
        if freshness.state not in {"fresh", "provider_reported"}:
            reasons.append("capability_freshness_not_usable")
        if freshness.observed_at > now + MAX_FUTURE_CLOCK_SKEW:
            reasons.append("capability_freshness_from_future")
        if freshness.expires_at is None or freshness.expires_at <= now:
            reasons.append("capability_freshness_expired")
        elif normalized.expires_at > freshness.expires_at:
            reasons.append("exposure_plan_outlives_capability_freshness")
        if normalized.execution_authorized or normalized.activation_authorized:
            reasons.append("authorization_ceiling_violation")
        try:
            _reject_secret_material(normalized.model_dump(mode="json"))
        except StackMCPError:
            reasons.append("secret_material_rejected")
        else:
            reasons.extend(plan_refusal_reasons)
        decision: ExposureDecision = "allowed" if not reasons else "denied"
        secret_rejected = "secret_material_rejected" in reasons
        receipt_expires_at = max(normalized.expires_at, now + timedelta(seconds=1))
        receipt_body = {
            "schema_version": "abyss_stack_exposure_materialization_receipt_v1",
            "request_id": (
                normalized.request_id if not secret_rejected else "invalid-request-id"
            ),
            "plan_id": normalized.plan_id,
            "decision": decision,
            "reason_codes": sorted(set(reasons)),
            "observed_at": now.isoformat().replace("+00:00", "Z"),
            "expires_at": receipt_expires_at.isoformat().replace("+00:00", "Z"),
            "snapshot_id": normalized.rendered_snapshot.snapshot_id,
            "source_digest": normalized.rendered_snapshot.source_digest,
            "visible_tool_ids": (
                list(normalized.rendered_snapshot.visible_tool_ids)
                if not secret_rejected
                else []
            ),
            "visible_bytes": normalized.rendered_snapshot.rendered_bytes,
            "visible_tokens": normalized.rendered_snapshot.rendered_tokens,
            "rollback_bindings": (
                [
                    binding.model_dump(mode="json")
                    for binding in normalized.rollback_bindings
                ]
                if not secret_rejected
                else []
            ),
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
            while len(self._materializations) >= MAX_RETAINED_MATERIALIZATIONS:
                del self._materializations[next(iter(self._materializations))]
            self._materializations[receipt.receipt_id] = normalized
        self._emit(receipt)
        return receipt

    def invoke(
        self,
        materialization_receipt_id: str,
        *,
        request_id: str,
        caller_id: str,
        tool_id: str,
        arguments: Mapping[str, Any],
        authorization_ref: ExposureInvocationAuthorization | Mapping[str, Any] | None,
    ) -> ExposureInvocationReceipt:
        """Record an invocation request; owner-tool execution is out of scope."""

        now = self._now()
        self._prune_materializations(now)
        request_id_status = _receipt_identifier_status(request_id)
        caller_id_status = _receipt_identifier_status(caller_id)
        tool_id_status = _receipt_identifier_status(tool_id)
        valid_request_id = request_id_status == "valid"
        valid_caller_id = caller_id_status == "valid"
        valid_tool_id = tool_id_status == "valid"
        valid_materialization_id = (
            isinstance(materialization_receipt_id, str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", materialization_receipt_id)
            is not None
        )
        receipt_request_id = request_id if valid_request_id else "invalid-request-id"
        receipt_caller_id = caller_id if valid_caller_id else "invalid-caller-id"
        receipt_tool_id = tool_id if valid_tool_id else "invalid-tool-id"
        receipt_materialization_id = (
            materialization_receipt_id if valid_materialization_id else ZERO_DIGEST
        )
        if not valid_request_id:
            reasons: list[str] = ["malformed_request_id"]
        else:
            reasons = []
        if not valid_caller_id:
            reasons.append("malformed_caller_id")
        if not valid_tool_id:
            reasons.append("malformed_tool_id")
        if not valid_materialization_id:
            reasons.append("malformed_materialization_receipt_id")
        if "secret" in {request_id_status, caller_id_status, tool_id_status}:
            reasons.append("secret_material_rejected")
        plan = self._materializations.get(receipt_materialization_id)
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
            if plan.rendered_snapshot.expires_at <= now:
                reasons.append("materialization_snapshot_expired")
        authorization: ExposureInvocationAuthorization | None = None
        if authorization_ref is None:
            reasons.append("invocation_authorization_required")
        else:
            try:
                raw_authorization = (
                    authorization_ref.model_dump(mode="json")
                    if isinstance(authorization_ref, ExposureInvocationAuthorization)
                    else authorization_ref
                )
                _bounded_json_preflight(
                    raw_authorization,
                    max_bytes=MAX_INVOCATION_AUTHORIZATION_BYTES,
                    max_items=MAX_INVOCATION_AUTHORIZATION_ITEMS,
                )
                if (
                    len(canonical_json_bytes(raw_authorization))
                    > MAX_INVOCATION_AUTHORIZATION_BYTES
                ):
                    raise _ExposurePayloadTooLarge
                authorization = ExposureInvocationAuthorization.model_validate(
                    raw_authorization
                )
            except _ExposurePayloadTooLarge:
                reasons.append("invocation_authorization_too_large")
            except Exception:
                reasons.append("invocation_authorization_invalid")
            if authorization is not None:
                if plan is None or authorization.plan_id != plan.plan_id:
                    reasons.append("invocation_authorization_plan_mismatch")
                if (
                    authorization.materialization_receipt_id
                    != receipt_materialization_id
                ):
                    reasons.append("invocation_authorization_materialization_mismatch")
                if authorization.tool_id != receipt_tool_id:
                    reasons.append("invocation_authorization_tool_mismatch")
                if authorization.caller_id != receipt_caller_id:
                    reasons.append("invocation_authorization_caller_mismatch")
                if plan is None or authorization.owner != plan.capability.owners.get(
                    "access_owner"
                ):
                    reasons.append("invocation_authorization_owner_mismatch")
                if authorization.issued_at > now + MAX_FUTURE_CLOCK_SKEW:
                    reasons.append("invocation_authorization_from_future")
                if authorization.expires_at <= now:
                    reasons.append("invocation_authorization_expired")
                if plan is not None and authorization.expires_at > plan.expires_at:
                    reasons.append("invocation_authorization_outlives_plan")
        normalized_arguments: dict[str, Any] = {}
        input_digest = sha256_digest(normalized_arguments)
        try:
            _bounded_json_preflight(
                arguments,
                max_bytes=MAX_INVOCATION_ARGUMENT_BYTES,
                max_items=MAX_INVOCATION_ARGUMENT_ITEMS,
            )
            candidate_arguments = (
                arguments if isinstance(arguments, dict) else dict(arguments)
            )
            argument_bytes = canonical_json_bytes(candidate_arguments)
            if len(argument_bytes) > MAX_INVOCATION_ARGUMENT_BYTES:
                reasons.append("invocation_arguments_too_large")
            else:
                _reject_secret_material(candidate_arguments)
                normalized_arguments = dict(candidate_arguments)
                input_digest = sha256_digest(normalized_arguments)
        except _ExposurePayloadTooLarge:
            reasons.append("invocation_arguments_too_large")
        except StackMCPError:
            reasons.append("secret_material_rejected")
        except Exception:
            reasons.append("malformed_invocation_arguments")
        effect_class: EffectClass = tool.effect_class if tool is not None else "observe"
        policy_family: PolicyFamily = tool.policy_family if tool is not None else "read"
        output_digest: str | None = None
        reasons.append("owner_tool_execution_not_owned_by_stack")
        decision: ExposureDecision = "denied"
        body = {
            "schema_version": "abyss_stack_exposure_invocation_receipt_v1",
            "request_id": receipt_request_id,
            "caller_id": receipt_caller_id,
            "materialization_receipt_id": receipt_materialization_id,
            "plan_id": plan.plan_id if plan is not None else ZERO_DIGEST,
            "tool_id": receipt_tool_id,
            "policy_family": policy_family,
            "effect_class": effect_class,
            "decision": decision,
            "reason_codes": sorted(set(reasons)),
            "input_digest": input_digest,
            "output_digest": output_digest,
            "authorization_id": (
                authorization.authorization_id if authorization is not None else None
            ),
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
