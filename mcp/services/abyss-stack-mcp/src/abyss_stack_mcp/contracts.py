"""Strict stack-owned runtime observation and plan-candidate contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Identifier = Annotated[
    str,
    Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
]
NonEmpty = Annotated[str, Field(min_length=1, max_length=2048)]
Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
UnitName = Annotated[
    str,
    Field(
        min_length=3,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.@-]*\.(service|socket)$",
    ),
]
LinkState = Literal[
    "exact",
    "compatible_drift",
    "stale_readable",
    "blocked",
    "unknown",
    "rollback_required",
]
PolicyFamily = Literal["read", "candidate", "internal_effect", "external_effect"]
ObservationView = Literal[
    "identity",
    "parity",
    "process",
    "endpoint",
    "registry",
    "consumer",
    "schema",
    "freshness",
    "canary",
    "rollback",
    "drift",
    "full",
]
PlanKind = Literal["sync", "deploy", "activate", "restart", "rollback"]


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceRef(StrictModel):
    owner: Identifier
    evidence_ref: NonEmpty
    revision: NonEmpty
    observed_at: datetime
    expires_at: datetime | None = None

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        return _aware_utc(value)

    @model_validator(mode="after")
    def validate_expiry(self) -> EvidenceRef:
        if self.expires_at is not None and self.expires_at <= self.observed_at:
            raise ValueError("evidence expiry must follow observation")
        return self


class LinkEvidence(StrictModel):
    state: LinkState
    observed_at: datetime
    expires_at: datetime | None = None
    evidence_refs: tuple[EvidenceRef, ...]
    reason_codes: tuple[Identifier, ...] = ()

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        return _aware_utc(value)

    @model_validator(mode="after")
    def validate_link(self) -> LinkEvidence:
        if self.expires_at is not None and self.expires_at <= self.observed_at:
            raise ValueError("link expiry must follow observation")
        if self.state in {"exact", "compatible_drift"} and not self.evidence_refs:
            raise ValueError("a usable link requires evidence")
        if self.state != "exact" and not self.reason_codes:
            raise ValueError("a non-exact link requires reason codes")
        return self


class OwnerRoles(StrictModel):
    source_owner: Identifier
    access_owner: Identifier
    runtime_owner: Literal["abyss-stack"] = "abyss-stack"
    proof_owner: Identifier
    acceptance_owner: Identifier


class SourceIdentity(StrictModel):
    revision: NonEmpty
    tree_digest: Digest
    evidence: LinkEvidence


class PackageIdentity(StrictModel):
    name: Identifier
    version: NonEmpty
    artifact_digest: Digest
    evidence: LinkEvidence


class DeployIdentity(StrictModel):
    revision: NonEmpty
    tree_digest: Digest
    manifest_ref: NonEmpty
    deployed_at: datetime
    evidence: LinkEvidence

    @field_validator("deployed_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        result = _aware_utc(value)
        assert result is not None
        return result


class ProcessObservation(StrictModel):
    unit_name: UnitName
    executable_ref: NonEmpty
    process_identity: NonEmpty | None = None
    active: bool
    evidence: LinkEvidence


class EndpointObservation(StrictModel):
    transport: Literal["stdio", "streamable-http"]
    endpoint_ref: NonEmpty
    protocol_versions: tuple[NonEmpty, ...]
    ready: bool
    server_schema_digest: Digest | None = None
    evidence: LinkEvidence

    @model_validator(mode="after")
    def validate_endpoint(self) -> EndpointObservation:
        if not self.protocol_versions:
            raise ValueError("endpoint protocol_versions cannot be empty")
        if self.transport == "streamable-http":
            parsed = urlsplit(self.endpoint_ref)
            if parsed.scheme not in {"http", "https"}:
                raise ValueError("HTTP endpoint_ref must be an absolute URL")
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("stack MCP observations are loopback-only")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("HTTP endpoint_ref cannot contain user information")
            if parsed.query or parsed.fragment:
                raise ValueError("HTTP endpoint_ref cannot contain query or fragment")
        if self.ready and self.server_schema_digest is None:
            raise ValueError("a ready endpoint requires an observed schema digest")
        return self


class RegistryObservation(StrictModel):
    registry_id: Identifier
    registry_digest: Digest
    registry_state: Literal[
        "declared",
        "package_candidate",
        "deploy_candidate",
        "shadow",
        "admitted",
        "suspended",
        "deprecated",
        "retired",
    ]
    evidence: LinkEvidence


class ConsumerObservation(StrictModel):
    consumer_id: Identifier
    registration_ref: NonEmpty
    registered: bool
    observed_schema_digest: Digest | None = None
    observed_protocol_versions: tuple[NonEmpty, ...] = ()
    evidence: LinkEvidence

    @model_validator(mode="after")
    def validate_registration(self) -> ConsumerObservation:
        if self.registered and (
            self.observed_schema_digest is None or not self.observed_protocol_versions
        ):
            raise ValueError(
                "a registered consumer requires schema and protocol observations"
            )
        return self


class FreshnessObservation(StrictModel):
    state: LinkState
    provider_watermark: NonEmpty | None = None
    observed_at: datetime
    expires_at: datetime
    evidence_refs: tuple[EvidenceRef, ...]
    reason_codes: tuple[Identifier, ...] = ()

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        result = _aware_utc(value)
        assert result is not None
        return result

    @model_validator(mode="after")
    def validate_freshness(self) -> FreshnessObservation:
        if self.expires_at <= self.observed_at:
            raise ValueError("freshness expiry must follow observation")
        if self.state in {"exact", "compatible_drift"}:
            if self.provider_watermark is None or not self.evidence_refs:
                raise ValueError(
                    "usable freshness requires provider watermark and evidence"
                )
        if self.state != "exact" and not self.reason_codes:
            raise ValueError("non-exact freshness requires reason codes")
        return self


class CanaryObservation(StrictModel):
    succeeded: bool
    result_grounded: bool
    canary_route: NonEmpty
    canary_ref: NonEmpty | None = None
    evidence: LinkEvidence

    @model_validator(mode="after")
    def validate_success(self) -> CanaryObservation:
        if self.succeeded and (
            not self.result_grounded
            or self.canary_ref is None
            or not self.evidence.evidence_refs
        ):
            raise ValueError(
                "successful canary requires grounded result and evidence ref"
            )
        return self


class RollbackObservation(StrictModel):
    ready: bool
    rollback_route: NonEmpty
    last_known_good_package_digest: Digest | None = None
    proof_ref: NonEmpty | None = None
    evidence: LinkEvidence

    @model_validator(mode="after")
    def validate_readiness(self) -> RollbackObservation:
        if self.ready and (
            self.last_known_good_package_digest is None or self.proof_ref is None
        ):
            raise ValueError(
                "rollback readiness requires last-known-good identity and proof"
            )
        return self


class RuntimeSubject(StrictModel):
    organ_id: Identifier
    policy_family: PolicyFamily
    owners: OwnerRoles
    credential_class: Identifier
    effect_classes: tuple[
        Literal[
            "observe",
            "derive",
            "validate",
            "prepare_candidate",
            "apply_runtime",
            "accept_source",
            "external_emit",
            "external_change",
        ],
        ...,
    ]
    source: SourceIdentity
    package: PackageIdentity
    deploy: DeployIdentity
    process: ProcessObservation
    endpoint: EndpointObservation
    registry: RegistryObservation
    consumers: tuple[ConsumerObservation, ...]
    freshness: FreshnessObservation
    canary: CanaryObservation
    rollback: RollbackObservation

    @model_validator(mode="after")
    def validate_plane(self) -> RuntimeSubject:
        allowed = {
            "read": {"observe", "derive", "validate"},
            "candidate": {"prepare_candidate"},
            "internal_effect": {"apply_runtime", "accept_source"},
            "external_effect": {"external_emit", "external_change"},
        }[self.policy_family]
        if not self.effect_classes or not set(self.effect_classes).issubset(allowed):
            raise ValueError("effect classes exceed the declared policy plane")
        consumer_ids = [consumer.consumer_id for consumer in self.consumers]
        if len(consumer_ids) != len(set(consumer_ids)):
            raise ValueError("consumer ids must be unique within a runtime subject")
        return self


class RuntimeObservation(StrictModel):
    schema_version: Literal["abyss_stack_runtime_observation_v1"] = (
        "abyss_stack_runtime_observation_v1"
    )
    provider: Literal["abyss-stack"] = "abyss-stack"
    provider_watermark: NonEmpty
    generated_at: datetime
    expires_at: datetime
    contains_secrets: Literal[False] = False
    subjects: tuple[RuntimeSubject, ...]

    @field_validator("generated_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        result = _aware_utc(value)
        assert result is not None
        return result

    @model_validator(mode="after")
    def validate_observation(self) -> RuntimeObservation:
        if self.expires_at <= self.generated_at:
            raise ValueError("observation expiry must follow generation")
        keys = [(subject.organ_id, subject.policy_family) for subject in self.subjects]
        if len(keys) != len(set(keys)):
            raise ValueError("organ and policy-family pairs must be unique")
        contours = [subject.credential_class for subject in self.subjects]
        if len(contours) != len(set(contours)):
            raise ValueError("credential classes cannot be shared across planes")
        return self


class PlanStep(StrictModel):
    order: Annotated[int, Field(ge=1, le=32)]
    action: Identifier
    exact_target: NonEmpty
    expected_effect: NonEmpty
    stop_on: tuple[Identifier, ...]


class RuntimePlanCandidate(StrictModel):
    schema_version: Literal["abyss_stack_runtime_plan_candidate_v1"] = (
        "abyss_stack_runtime_plan_candidate_v1"
    )
    plan_id: Digest
    plan_kind: PlanKind
    policy_family: Literal["candidate"] = "candidate"
    effect_class: Literal["prepare_candidate"] = "prepare_candidate"
    execution_authorized: Literal[False] = False
    approval_required_before_execution: Literal[True] = True
    target_organ_id: Identifier
    target_policy_family: PolicyFamily
    expected_observation_digest: Digest
    source_revision: NonEmpty
    package_digest: Digest
    deployed_revision: NonEmpty
    exact_unit_name: UnitName
    precondition_evidence: tuple[EvidenceRef, ...]
    steps: tuple[PlanStep, ...]
    rollback_route: NonEmpty
    created_at: datetime
    expires_at: datetime

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        result = _aware_utc(value)
        assert result is not None
        return result

    @model_validator(mode="after")
    def validate_plan(self) -> RuntimePlanCandidate:
        if self.expires_at <= self.created_at:
            raise ValueError("plan expiry must follow creation")
        if not self.steps:
            raise ValueError("a plan requires bounded steps")
        if [step.order for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("plan step order must be contiguous")
        unsigned = self.model_dump(mode="json", exclude={"plan_id"})
        expected = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    unsigned,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        )
        if self.plan_id != expected:
            raise ValueError("plan_id must address the exact plan content")
        return self
