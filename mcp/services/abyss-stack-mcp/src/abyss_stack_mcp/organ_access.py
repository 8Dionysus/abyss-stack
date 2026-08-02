"""Owner-authored capability identities for the stack MCP contours."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError, model_validator

from .contracts import Identifier, NonEmpty, StrictModel


READ_CAPABILITY_ID = "runtime-topology-read"
CANDIDATE_CAPABILITY_ID = "stack-access-plan"
INTERNAL_EFFECT_CAPABILITY_ID = "exact-read-restart-pilot"
READ_CREDENTIAL_CLASS = "abyss-stack-read"
CANDIDATE_CREDENTIAL_CLASS = "abyss-stack-candidate"
INTERNAL_EFFECT_CREDENTIAL_CLASS = "abyss-stack-internal-effect"
READ_TOOL_BINDINGS = {
    "runtime-catalog": "stack_runtime_catalog",
    "runtime-inspect": "stack_runtime_inspect",
    "cross-organ-orchestration-inspect": "stack_orchestration_inspect",
}
CANDIDATE_TOOL_BINDINGS = {
    "prepare-runtime-plan": "stack_prepare_runtime_plan",
}
INTERNAL_EFFECT_TOOL_BINDINGS = {
    "execute-approved-read-restart-pilot": (
        "stack_execute_approved_read_restart_pilot"
    ),
}


class StackOrganAccessError(ValueError):
    """The owner capability manifest is unavailable or internally inconsistent."""


class OrganAccessPrimitive(StrictModel):
    primitive_id: Identifier
    mcp_name: Identifier
    kind: Literal["tool"] = "tool"
    effect_class: Literal["observe", "prepare_candidate", "apply_runtime"]
    policy_family: Literal["read", "candidate", "internal_effect"]
    input_schema_ref: NonEmpty
    output_schema_ref: NonEmpty
    idempotency: Literal["read_only", "idempotent"]
    maximum_blast_radius: NonEmpty
    approval_required: bool = False
    annotations_are_security_enforcement: Literal[False] = False
    rollback_route: NonEmpty | None = None

    @model_validator(mode="after")
    def validate_effect_family(self) -> OrganAccessPrimitive:
        expected = {
            "read": "observe",
            "candidate": "prepare_candidate",
            "internal_effect": "apply_runtime",
        }[self.policy_family]
        if self.effect_class != expected:
            raise ValueError("organ primitive effect does not match its policy family")
        if self.policy_family == "read" and self.idempotency != "read_only":
            raise ValueError("read primitive must be read_only")
        if self.policy_family == "candidate" and self.rollback_route is None:
            raise ValueError("candidate primitive requires a rollback route")
        if self.policy_family == "internal_effect":
            if not self.approval_required:
                raise ValueError("internal-effect primitive requires explicit approval")
            if self.rollback_route is None:
                raise ValueError("internal-effect primitive requires a rollback route")
        return self


class OrganAccessCapability(StrictModel):
    capability_id: Identifier
    summary: NonEmpty
    policy_family: Literal["read", "candidate", "internal_effect"]
    credential_class: Identifier
    primitives: Annotated[tuple[OrganAccessPrimitive, ...], Field(min_length=1)]
    owner_payload_schema_ref: NonEmpty
    task_intent_terms: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    eval_refs: tuple[NonEmpty, ...] = ()

    @model_validator(mode="after")
    def validate_capability(self) -> OrganAccessCapability:
        if any(item.policy_family != self.policy_family for item in self.primitives):
            raise ValueError("capability primitives must share one policy family")
        if len({item.primitive_id for item in self.primitives}) != len(self.primitives):
            raise ValueError("capability primitive ids must be unique")
        if len({item.mcp_name for item in self.primitives}) != len(self.primitives):
            raise ValueError("capability MCP names must be unique")
        return self


class StackOrganAccessManifest(StrictModel):
    schema_version: Literal["abyss_stack_mcp_organ_access_v1"] = (
        "abyss_stack_mcp_organ_access_v1"
    )
    organ_id: Literal["abyss-stack"] = "abyss-stack"
    owner_decision_ref: NonEmpty
    capabilities: Annotated[tuple[OrganAccessCapability, ...], Field(min_length=3)]
    contains_secrets: Literal[False] = False
    admission_asserted: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    effect_activation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_contours(self) -> StackOrganAccessManifest:
        by_family = {item.policy_family: item for item in self.capabilities}
        if len(by_family) != len(self.capabilities) or set(by_family) != {
            "read",
            "candidate",
            "internal_effect",
        }:
            raise ValueError(
                "stack organ access requires one read, candidate, and exact "
                "internal-effect contour"
            )
        read = by_family["read"]
        candidate = by_family["candidate"]
        internal_effect = by_family["internal_effect"]
        if (
            read.capability_id != READ_CAPABILITY_ID
            or read.credential_class != READ_CREDENTIAL_CLASS
            or {item.primitive_id: item.mcp_name for item in read.primitives}
            != READ_TOOL_BINDINGS
        ):
            raise ValueError("stack read capability identity drifted")
        if (
            candidate.capability_id != CANDIDATE_CAPABILITY_ID
            or candidate.credential_class != CANDIDATE_CREDENTIAL_CLASS
            or {item.primitive_id: item.mcp_name for item in candidate.primitives}
            != CANDIDATE_TOOL_BINDINGS
        ):
            raise ValueError("stack candidate capability identity drifted")
        if (
            internal_effect.capability_id != INTERNAL_EFFECT_CAPABILITY_ID
            or internal_effect.credential_class != INTERNAL_EFFECT_CREDENTIAL_CLASS
            or {
                item.primitive_id: item.mcp_name
                for item in internal_effect.primitives
            }
            != INTERNAL_EFFECT_TOOL_BINDINGS
        ):
            raise ValueError("stack internal-effect capability identity drifted")
        if len(
            {
                read.credential_class,
                candidate.credential_class,
                internal_effect.credential_class,
            }
        ) != 3:
            raise ValueError("stack contour credentials must remain pairwise distinct")
        return self


def load_organ_access_manifest(path: Path) -> StackOrganAccessManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return StackOrganAccessManifest.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise StackOrganAccessError("stack organ capability manifest is invalid") from exc
