"""Strict stack-owned runtime observation and plan-candidate contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Identifier = Annotated[
    str,
    Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
]
NonEmpty = Annotated[
    str,
    Field(min_length=1, max_length=2048, pattern=r"\S"),
]
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
    "proof",
    "acceptance",
    "canary",
    "rollback",
    "drift",
    "full",
]
PlanKind = Literal["sync", "deploy", "activate", "restart", "rollback"]
MAX_EVENT_EVIDENCE_SKEW = timedelta(seconds=30)


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
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "state": {"enum": ["exact", "compatible_drift"]}
                        },
                        "required": ["state"],
                    },
                    "then": {
                        "properties": {"evidence_refs": {"minItems": 1}},
                    },
                },
                {
                    "if": {
                        "properties": {
                            "state": {
                                "enum": [
                                    "compatible_drift",
                                    "stale_readable",
                                    "blocked",
                                    "unknown",
                                    "rollback_required",
                                ]
                            }
                        },
                        "required": ["state"],
                    },
                    "then": {
                        "properties": {"reason_codes": {"minItems": 1}},
                        "required": ["reason_codes"],
                    },
                },
                {
                    "if": {
                        "properties": {"state": {"const": "rollback_required"}},
                        "required": ["state"],
                    },
                    "then": {
                        "properties": {"evidence_refs": {"minItems": 1}},
                    },
                },
            ]
        },
    )
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
        if self.state == "rollback_required" and not self.evidence_refs:
            raise ValueError("a rollback-required link requires evidence")
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
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"active": {"const": True}},
                        "required": ["active"],
                    },
                    "then": {
                        "properties": {
                            "process_identity": {"type": "string"},
                        },
                        "required": ["process_identity"],
                    },
                }
            ]
        },
    )
    unit_name: UnitName
    executable_ref: NonEmpty
    process_identity: NonEmpty | None = None
    active: bool
    evidence: LinkEvidence

    @model_validator(mode="after")
    def validate_active_identity(self) -> ProcessObservation:
        if self.active and self.process_identity is None:
            raise ValueError("an active process requires an observed process identity")
        return self


class EndpointObservation(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"ready": {"const": True}},
                        "required": ["ready"],
                    },
                    "then": {
                        "properties": {
                            "server_schema_digest": {"type": "string"},
                        },
                        "required": ["server_schema_digest"],
                    },
                }
            ]
        },
    )
    transport: Literal["stdio", "streamable-http"]
    endpoint_ref: NonEmpty
    protocol_versions: Annotated[tuple[NonEmpty, ...], Field(min_length=1)]
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
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError("HTTP endpoint_ref has an invalid port") from exc
            if port is not None and not 1 <= port <= 65_535:
                raise ValueError("HTTP endpoint_ref has an invalid port")
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
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"registered": {"const": True}},
                        "required": ["registered"],
                    },
                    "then": {
                        "properties": {
                            "observed_schema_digest": {"type": "string"},
                            "observed_protocol_versions": {"minItems": 1},
                        },
                        "required": [
                            "observed_schema_digest",
                            "observed_protocol_versions",
                        ],
                    },
                }
            ]
        },
    )
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
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "state": {"enum": ["exact", "compatible_drift"]}
                        },
                        "required": ["state"],
                    },
                    "then": {
                        "properties": {
                            "provider_watermark": {"type": "string"},
                            "evidence_refs": {"minItems": 1},
                        },
                        "required": ["provider_watermark", "evidence_refs"],
                    },
                },
                {
                    "if": {
                        "properties": {
                            "state": {
                                "enum": [
                                    "compatible_drift",
                                    "stale_readable",
                                    "blocked",
                                    "unknown",
                                    "rollback_required",
                                ]
                            }
                        },
                        "required": ["state"],
                    },
                    "then": {
                        "properties": {"reason_codes": {"minItems": 1}},
                        "required": ["reason_codes"],
                    },
                },
            ]
        },
    )
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
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"succeeded": {"const": True}},
                        "required": ["succeeded"],
                    },
                    "then": {
                        "properties": {
                            "result_grounded": {"const": True},
                            "canary_ref": {"type": "string"},
                            "evidence": {
                                "properties": {
                                    "evidence_refs": {"minItems": 1},
                                }
                            },
                        },
                        "required": ["result_grounded", "canary_ref", "evidence"],
                    },
                }
            ]
        },
    )
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


class CentralProofObservation(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"verdict": {"const": "passed"}},
                        "required": ["verdict"],
                    },
                    "then": {
                        "properties": {
                            "proof_ref": {"type": "string"},
                            "evaluated_at": {
                                "type": "string",
                                "format": "date-time",
                            },
                            "proved_source_revision": {"type": "string"},
                            "proved_package_digest": {"type": "string"},
                            "proved_deploy_revision": {"type": "string"},
                            "proved_server_schema_digest": {"type": "string"},
                            "proved_consumer_registration_ref": {
                                "type": "string"
                            },
                            "proved_canary_ref": {"type": "string"},
                            "evidence": {
                                "properties": {
                                    "state": {
                                        "enum": ["exact", "compatible_drift"]
                                    },
                                    "evidence_refs": {"minItems": 1},
                                }
                            },
                        },
                        "required": [
                            "proof_ref",
                            "evaluated_at",
                            "proved_source_revision",
                            "proved_package_digest",
                            "proved_deploy_revision",
                            "proved_server_schema_digest",
                            "proved_consumer_registration_ref",
                            "proved_canary_ref",
                            "evidence",
                        ],
                    },
                }
            ]
        },
    )
    verdict: Literal["passed", "failed", "unknown"]
    proof_ref: NonEmpty | None = None
    evaluated_at: datetime | None = None
    proved_source_revision: NonEmpty | None = None
    proved_package_digest: Digest | None = None
    proved_deploy_revision: NonEmpty | None = None
    proved_server_schema_digest: Digest | None = None
    proved_consumer_registration_ref: NonEmpty | None = None
    proved_canary_ref: NonEmpty | None = None
    evidence: LinkEvidence

    @field_validator("evaluated_at")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        return _aware_utc(value)

    @model_validator(mode="after")
    def validate_proof(self) -> CentralProofObservation:
        proof_contour = (
            self.proof_ref,
            self.evaluated_at,
            self.proved_source_revision,
            self.proved_package_digest,
            self.proved_deploy_revision,
            self.proved_server_schema_digest,
            self.proved_consumer_registration_ref,
            self.proved_canary_ref,
        )
        if self.verdict == "passed" and (
            any(value is None for value in proof_contour)
            or self.evidence.state not in {"exact", "compatible_drift"}
            or not self.evidence.evidence_refs
        ):
            raise ValueError(
                "passed central proof requires an exact target, timestamp, "
                "and evidence"
            )
        if (
            self.verdict == "passed"
            and self.evaluated_at is not None
            and min(
                self.evidence.observed_at,
                *(
                    evidence.observed_at
                    for evidence in self.evidence.evidence_refs
                ),
            )
            < self.evaluated_at - MAX_EVENT_EVIDENCE_SKEW
        ):
            raise ValueError("central proof evidence cannot predate its verdict")
        return self


class OwnerAcceptanceObservation(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"accepted": {"const": True}},
                        "required": ["accepted"],
                    },
                    "then": {
                        "properties": {
                            "acceptance_ref": {"type": "string"},
                            "accepted_at": {"type": "string", "format": "date-time"},
                            "accepted_source_revision": {"type": "string"},
                            "accepted_package_digest": {"type": "string"},
                            "evidence": {
                                "properties": {
                                    "state": {
                                        "enum": ["exact", "compatible_drift"]
                                    },
                                    "evidence_refs": {"minItems": 1},
                                }
                            },
                        },
                        "required": [
                            "acceptance_ref",
                            "accepted_at",
                            "accepted_source_revision",
                            "accepted_package_digest",
                            "evidence",
                        ],
                    },
                }
            ]
        },
    )
    accepted: bool
    acceptance_ref: NonEmpty | None = None
    accepted_at: datetime | None = None
    accepted_source_revision: NonEmpty | None = None
    accepted_package_digest: Digest | None = None
    evidence: LinkEvidence

    @field_validator("accepted_at")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        return _aware_utc(value)

    @model_validator(mode="after")
    def validate_acceptance(self) -> OwnerAcceptanceObservation:
        acceptance_contour = (
            self.acceptance_ref,
            self.accepted_at,
            self.accepted_source_revision,
            self.accepted_package_digest,
        )
        if self.accepted and (
            any(value is None for value in acceptance_contour)
            or self.evidence.state not in {"exact", "compatible_drift"}
            or not self.evidence.evidence_refs
        ):
            raise ValueError(
                "owner acceptance requires an exact target, timestamp, and evidence"
            )
        if (
            self.accepted
            and self.accepted_at is not None
            and min(
                self.evidence.observed_at,
                *(
                    evidence.observed_at
                    for evidence in self.evidence.evidence_refs
                ),
            )
            < self.accepted_at - MAX_EVENT_EVIDENCE_SKEW
        ):
            raise ValueError(
                "owner acceptance evidence cannot predate its decision"
            )
        return self


class RollbackObservation(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"ready": {"const": True}},
                        "required": ["ready"],
                    },
                    "then": {
                        "properties": {
                            "last_known_good_consumer_registration_ref": {
                                "type": "string"
                            },
                            "last_known_good_package_digest": {"type": "string"},
                            "last_known_good_deploy_revision": {"type": "string"},
                            "last_known_good_deploy_tree_digest": {
                                "type": "string"
                            },
                            "last_known_good_unit_name": {"type": "string"},
                            "last_known_good_credential_class": {
                                "type": "string"
                            },
                            "last_known_good_executable_ref": {"type": "string"},
                            "last_known_good_process_identity": {
                                "type": "string"
                            },
                            "proof_ref": {"type": "string"},
                        },
                        "required": [
                            "last_known_good_consumer_registration_ref",
                            "last_known_good_package_digest",
                            "last_known_good_deploy_revision",
                            "last_known_good_deploy_tree_digest",
                            "last_known_good_unit_name",
                            "last_known_good_credential_class",
                            "last_known_good_executable_ref",
                            "last_known_good_process_identity",
                            "proof_ref",
                        ],
                    },
                }
            ]
        },
    )
    ready: bool
    rollback_route: NonEmpty
    last_known_good_consumer_registration_ref: NonEmpty | None = None
    last_known_good_package_digest: Digest | None = None
    last_known_good_deploy_revision: NonEmpty | None = None
    last_known_good_deploy_tree_digest: Digest | None = None
    last_known_good_unit_name: UnitName | None = None
    last_known_good_credential_class: Identifier | None = None
    last_known_good_executable_ref: NonEmpty | None = None
    last_known_good_process_identity: NonEmpty | None = None
    proof_ref: NonEmpty | None = None
    evidence: LinkEvidence

    @model_validator(mode="after")
    def validate_readiness(self) -> RollbackObservation:
        last_known_good_contour = (
            self.last_known_good_consumer_registration_ref,
            self.last_known_good_package_digest,
            self.last_known_good_deploy_revision,
            self.last_known_good_deploy_tree_digest,
            self.last_known_good_unit_name,
            self.last_known_good_credential_class,
            self.last_known_good_executable_ref,
            self.last_known_good_process_identity,
            self.proof_ref,
        )
        if self.ready and any(value is None for value in last_known_good_contour):
            raise ValueError(
                "rollback readiness requires a complete last-known-good contour "
                "and proof"
            )
        return self


class RuntimeSubject(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"policy_family": {"const": "read"}},
                        "required": ["policy_family"],
                    },
                    "then": {
                        "properties": {
                            "effect_classes": {
                                "items": {
                                    "enum": ["observe", "derive", "validate"]
                                }
                            }
                        }
                    },
                },
                {
                    "if": {
                        "properties": {"policy_family": {"const": "candidate"}},
                        "required": ["policy_family"],
                    },
                    "then": {
                        "properties": {
                            "effect_classes": {
                                "items": {"const": "prepare_candidate"}
                            }
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "policy_family": {"const": "internal_effect"}
                        },
                        "required": ["policy_family"],
                    },
                    "then": {
                        "properties": {
                            "effect_classes": {
                                "items": {
                                    "enum": ["apply_runtime", "accept_source"]
                                }
                            }
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "policy_family": {"const": "external_effect"}
                        },
                        "required": ["policy_family"],
                    },
                    "then": {
                        "properties": {
                            "effect_classes": {
                                "items": {
                                    "enum": ["external_emit", "external_change"]
                                }
                            }
                        }
                    },
                },
            ]
        },
    )
    organ_id: Identifier
    policy_family: PolicyFamily
    owners: OwnerRoles
    credential_class: Identifier
    effect_classes: Annotated[
        tuple[
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
        ],
        Field(min_length=1),
    ]
    source: SourceIdentity
    package: PackageIdentity
    deploy: DeployIdentity
    process: ProcessObservation
    endpoint: EndpointObservation
    registry: RegistryObservation
    consumers: tuple[ConsumerObservation, ...]
    freshness: FreshnessObservation
    proof: CentralProofObservation
    acceptance: OwnerAcceptanceObservation
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
        consumer_registration_refs = [
            consumer.registration_ref for consumer in self.consumers
        ]
        if len(consumer_registration_refs) != len(
            set(consumer_registration_refs)
        ):
            raise ValueError(
                "consumer registration refs must be unique within a runtime subject"
            )
        if self.proof.verdict == "passed" and not any(
            evidence.owner == self.owners.proof_owner
            for evidence in self.proof.evidence.evidence_refs
        ):
            raise ValueError("central proof evidence must be issued by proof_owner")
        if self.acceptance.accepted and not any(
            evidence.owner == self.owners.acceptance_owner
            for evidence in self.acceptance.evidence.evidence_refs
        ):
            raise ValueError(
                "owner acceptance evidence must be issued by acceptance_owner"
            )
        if (
            self.canary.succeeded
            and min(
                self.canary.evidence.observed_at,
                *(
                    evidence.observed_at
                    for evidence in self.canary.evidence.evidence_refs
                ),
            )
            < self.deploy.deployed_at
        ):
            raise ValueError("successful canary cannot precede deployment")
        if (
            self.proof.verdict == "passed"
            and self.canary.succeeded
            and self.proof.evaluated_at is not None
            and self.proof.evaluated_at
            < max(
                self.canary.evidence.observed_at,
                *(
                    evidence.observed_at
                    for evidence in self.canary.evidence.evidence_refs
                ),
            )
        ):
            raise ValueError("central proof cannot precede canary evidence")
        if (
            self.proof.verdict == "passed"
            and self.acceptance.accepted
            and self.proof.evaluated_at is not None
            and self.acceptance.accepted_at is not None
            and self.acceptance.accepted_at < self.proof.evaluated_at
        ):
            raise ValueError("owner acceptance cannot precede central proof")
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
    steps: Annotated[tuple[PlanStep, ...], Field(min_length=1)]
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
