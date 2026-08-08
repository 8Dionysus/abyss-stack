"""Bounded MCP operations read model without collapsing authority axes."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .admission_automation import AdmissionAutomationStatus, KeeperContourStatus
from .contracts import Digest, Identifier, NonEmpty, StrictModel
from .managed_catalog import publish_private_json
from .preflight import ManagedContourBinding, ManagedContourCatalog, PreflightError, _safe_json


class RuntimeStatusAxis(StrictModel):
    live_state: Literal["observed", "blocked", "unobserved"]
    live_evidence_ref: NonEmpty | None = None
    source_runtime_parity: Literal["exact", "blocked"]
    preflight_eligible: bool
    blocker_codes: tuple[Identifier, ...]
    active_protocol: NonEmpty
    next_protocol: NonEmpty
    credential_class: Identifier
    credential_generation: NonEmpty | None = None
    credential_generation_state: Literal["observed", "unobserved"]
    schema_digest: Digest


class AdmissionStatusAxis(StrictModel):
    admission_current: bool
    currentness: tuple[NonEmpty, ...]
    evidence_expires_at: datetime | None = None
    last_good_present: bool
    last_good_state_ref: NonEmpty | None = None
    last_good_state_digest: Digest | None = None
    blocker_codes: tuple[Identifier, ...]
    refresh_transaction_ref: NonEmpty
    full_refresh_cost: int = Field(ge=0)
    planned_refresh_cost: int = Field(ge=0)
    cost_weight_not_planned: int = Field(ge=0)
    reused_stage_count: int = Field(ge=0)
    refreshed_stage_count: int = Field(ge=0)
    blocked_stage_count: int = Field(ge=0)
    next_safe_step: NonEmpty


class OwnerStatusAxis(StrictModel):
    owner_watermark: NonEmpty | None = None
    owner_watermark_state: Literal["observed", "unobserved"]
    owner_truth_inferred: Literal[False] = False
    owner_acceptance_inferred: Literal[False] = False


class ContourSystemStatus(StrictModel):
    organ_id: Identifier
    contour_id: Identifier
    runtime: RuntimeStatusAxis
    admission: AdmissionStatusAxis
    owner: OwnerStatusAxis


class ProtocolSystemStatus(StrictModel):
    production_protocol: NonEmpty
    next_protocol: NonEmpty
    core_read_migration_allowed: bool
    tasks_extension_allowed: bool
    tasks_reference_consumer: NonEmpty
    tasks_reference_pair_passed: bool
    tasks_inspector_strict_pair_blocked: bool
    tasks_codex_consumer_eligible: bool
    tasks_evidence_expires_at: datetime
    blocker_codes: tuple[Identifier, ...]
    status_digest: Digest


class TaskQuotaSystemStatus(StrictModel):
    maximum_active_tasks: int = Field(ge=1)
    maximum_active_tasks_per_principal: int = Field(ge=1)
    active_tasks: int = Field(ge=0)
    maximum_observed_active_per_principal: int = Field(ge=0)
    global_remaining: int = Field(ge=0)


class TaskSystemStatus(StrictModel):
    schema_version: Literal["aoa_owner_task_store_status_v1"]
    observed_at: datetime
    record_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    status_counts: dict[str, int]
    outstanding_input_count: int = Field(ge=0)
    pending_cancellation_count: int = Field(ge=0)
    expired_unpersisted_count: int = Field(ge=0)
    orphan_candidate_count: int = Field(ge=0)
    orphan_after_seconds: int = Field(ge=60)
    orphan_candidate_basis: Literal[
        "pending_cancellation_without_terminal_transition"
    ]
    oldest_active_updated_at: datetime | None = None
    next_expiry_at: datetime | None = None
    quota: TaskQuotaSystemStatus
    task_handle_is_admission_identity: Literal[False] = False
    task_completion_implies_admission: Literal[False] = False
    task_cancellation_erases_evidence: Literal[False] = False
    owner_transaction_survives_task_loss: Literal[True] = True
    contains_task_identifiers: Literal[False] = False
    contains_principal_identifiers: Literal[False] = False
    owner_execution_inferred: Literal[False] = False
    admission_inferred: Literal[False] = False

    @model_validator(mode="after")
    def validate_aggregate(self) -> "TaskSystemStatus":
        expected = {
            "working",
            "input_required",
            "completed",
            "failed",
            "cancelled",
            "expired",
        }
        if set(self.status_counts) != expected:
            raise ValueError("task status projection requires every bounded state")
        if any(value < 0 for value in self.status_counts.values()):
            raise ValueError("task status counts cannot be negative")
        if sum(self.status_counts.values()) != self.record_count:
            raise ValueError("task status counts must equal record count")
        if self.quota.active_tasks != self.active_count:
            raise ValueError("task quota active count must match the projection")
        return self


class MCPSystemStatus(StrictModel):
    schema_version: Literal["abyss_mcp_system_status_v1"] = "abyss_mcp_system_status_v1"
    status_id: Digest
    generated_at: datetime
    contours: tuple[ContourSystemStatus, ...]
    protocol: ProtocolSystemStatus
    tasks: TaskSystemStatus
    operational_health_admission_owner_truth_collapsed: Literal[False] = False
    services_started_or_restarted: Literal[False] = False
    registry_mutation_performed: Literal[False] = False
    next_safe_step: NonEmpty
    claim_limits: tuple[NonEmpty, ...]


def build_system_status(
    *,
    admission: AdmissionAutomationStatus,
    catalog: ManagedContourCatalog,
    registry: dict[str, Any],
    protocol: dict[str, Any],
    tasks: dict[str, Any],
    generated_at: datetime | None = None,
) -> MCPSystemStatus:
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    _validate_protocol_status(protocol)
    task_axis = TaskSystemStatus.model_validate(
        {
            **tasks,
            "task_handle_is_admission_identity": False,
            "task_completion_implies_admission": False,
            "task_cancellation_erases_evidence": False,
            "owner_transaction_survives_task_loss": True,
        }
    )
    preflight = {
        (entry.organ_id, entry.contour_id): entry for entry in admission.preflight.entries
    }
    keepers = {(entry.organ_id, entry.contour_id): entry for entry in admission.keepers}
    contours: list[ContourSystemStatus] = []
    for binding in sorted(catalog.contours, key=lambda item: item.binding_id):
        identity = (binding.organ_id, binding.contour_id)
        if identity not in preflight or identity not in keepers:
            raise PreflightError("system status inputs disagree on managed contour identity")
        registry_contour = _registry_contour(registry, *identity)
        contours.append(
            _contour_status(
                binding,
                preflight[identity],
                keepers[identity],
                registry_contour,
                protocol,
            )
        )
    if set(preflight) != set(keepers) or set(preflight) != {
        (item.organ_id, item.contour_id) for item in catalog.contours
    }:
        raise PreflightError("system status refuses partial contour coverage")
    protocol_axis = ProtocolSystemStatus(
        production_protocol=protocol["production_protocol"],
        next_protocol=protocol["next_protocol"],
        core_read_migration_allowed=protocol["core_read_migration_allowed"],
        tasks_extension_allowed=protocol["tasks_extension_allowed"],
        tasks_reference_consumer=protocol["tasks_reference_consumer"],
        tasks_reference_pair_passed=protocol["tasks_reference_pair_passed"],
        tasks_inspector_strict_pair_blocked=protocol[
            "tasks_inspector_strict_pair_blocked"
        ],
        tasks_codex_consumer_eligible=protocol["tasks_codex_consumer_eligible"],
        tasks_evidence_expires_at=protocol["tasks_evidence_expires_at"],
        blocker_codes=tuple(protocol["tasks_blockers"]),
        status_digest=protocol["status_digest"],
    )
    first_blocked = next(
        (
            item
            for item in contours
            if item.runtime.blocker_codes or item.admission.blocker_codes
        ),
        None,
    )
    unsigned = {
        "generated_at": now.isoformat(),
        "contours": [item.model_dump(mode="json") for item in contours],
        "protocol": protocol_axis.model_dump(mode="json"),
        "tasks": task_axis.model_dump(mode="json"),
    }
    return MCPSystemStatus(
        status_id=_digest(unsigned),
        generated_at=now,
        contours=tuple(contours),
        protocol=protocol_axis,
        tasks=task_axis,
        next_safe_step=(
            first_blocked.admission.next_safe_step
            if first_blocked is not None
            else admission.next_safe_step
        ),
        claim_limits=(
            "Runtime health, source/runtime parity, admission, owner truth, protocol compatibility, and Tasks operations remain separate axes.",
            "An observed process or completed task does not imply current admission, owner acceptance, proof, or effect authority.",
            "Credential generation remains unobserved unless an owner/runtime contract supplies it explicitly.",
            "This private read model starts no service, mutates no registry, and issues no owner or proof verdict.",
        ),
    )


def _contour_status(
    binding: ManagedContourBinding,
    preflight: Any,
    keeper: KeeperContourStatus,
    registry_contour: dict[str, Any],
    protocol: dict[str, Any],
) -> ContourSystemStatus:
    process_stage = next(
        (item for item in keeper.stage_states if item.stage == "process"), None
    )
    if process_stage is None or process_stage.outcome is None:
        live_state: Literal["observed", "blocked", "unobserved"] = "unobserved"
    elif process_stage.current and process_stage.outcome == "passed":
        live_state = "observed"
    else:
        live_state = "blocked"
    blockers = tuple(dict.fromkeys((*preflight.reason_codes, *keeper.blocker_codes)))
    owner_watermark = registry_contour.get("owner_watermark")
    credential_generation = registry_contour.get("credential_generation")
    next_safe_step = (
        f"refresh keeper stage {keeper.next_safe_stage}"
        if keeper.next_safe_stage is not None
        else (
            "repair the first contour blocker"
            if blockers
            else "retain independent contour observation and admission renewal"
        )
    )
    return ContourSystemStatus(
        organ_id=binding.organ_id,
        contour_id=binding.contour_id,
        runtime=RuntimeStatusAxis(
            live_state=live_state,
            live_evidence_ref=process_stage.node_id if process_stage else None,
            source_runtime_parity=("exact" if preflight.eligible_to_start else "blocked"),
            preflight_eligible=preflight.eligible_to_start,
            blocker_codes=preflight.reason_codes,
            active_protocol=binding.protocol_version,
            next_protocol=protocol["next_protocol"],
            credential_class=binding.credential_class,
            credential_generation=credential_generation,
            credential_generation_state=(
                "observed" if credential_generation is not None else "unobserved"
            ),
            schema_digest=binding.server_schema_digest,
        ),
        admission=AdmissionStatusAxis(
            admission_current=keeper.admission_current,
            currentness=keeper.currentness,
            evidence_expires_at=keeper.evidence_expires_at,
            last_good_present=keeper.last_good_state_ref is not None,
            last_good_state_ref=keeper.last_good_state_ref,
            last_good_state_digest=keeper.last_good_state_digest,
            blocker_codes=blockers,
            refresh_transaction_ref=keeper.transaction_ref,
            full_refresh_cost=keeper.full_refresh_cost,
            planned_refresh_cost=keeper.planned_refresh_cost,
            cost_weight_not_planned=max(
                keeper.full_refresh_cost - keeper.planned_refresh_cost, 0
            ),
            reused_stage_count=keeper.reused_stage_count,
            refreshed_stage_count=keeper.refreshed_stage_count,
            blocked_stage_count=keeper.blocked_stage_count,
            next_safe_step=next_safe_step,
        ),
        owner=OwnerStatusAxis(
            owner_watermark=owner_watermark,
            owner_watermark_state=(
                "observed" if owner_watermark is not None else "unobserved"
            ),
        ),
    )


def _registry_contour(
    registry: dict[str, Any], organ_id: str, contour_id: str
) -> dict[str, Any]:
    for record in registry.get("records", []):
        if isinstance(record, dict) and record.get("organ_id") == organ_id:
            for contour in record.get("contours", []):
                if isinstance(contour, dict) and contour.get("contour_id") == contour_id:
                    return contour
    raise PreflightError("system status contour is absent from the owner registry")


def _validate_protocol_status(protocol: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "production_protocol",
        "next_protocol",
        "core_read_migration_allowed",
        "tasks_extension_allowed",
        "tasks_reference_consumer",
        "tasks_reference_pair_passed",
        "tasks_inspector_strict_pair_blocked",
        "tasks_codex_consumer_eligible",
        "tasks_evidence_expires_at",
        "tasks_blockers",
        "status_digest",
    }
    if protocol.get("schema_version") != "abyss_mcp_protocol_lab_status_v2":
        raise PreflightError("unsupported protocol status schema")
    if not required.issubset(protocol):
        raise PreflightError("protocol status lacks a required bounded field")


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def main() -> int:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-system-status")
    parser.add_argument("--admission-status", type=Path, required=True)
    parser.add_argument("--managed-catalog", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--protocol-status", type=Path, required=True)
    parser.add_argument("--task-store", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--orphan-after-seconds", type=int, default=300)
    args = parser.parse_args()
    try:
        from aoa_sdk.organs import FileTaskStore

        status = build_system_status(
            admission=AdmissionAutomationStatus.model_validate(
                _safe_json(args.admission_status, "admission automation status")
            ),
            catalog=ManagedContourCatalog.model_validate(
                _safe_json(args.managed_catalog, "managed contour catalog")
            ),
            registry=_safe_json(args.registry, "v2 organ registry"),
            protocol=_safe_json(args.protocol_status, "protocol lab status"),
            tasks=FileTaskStore(args.task_store)
            .status(orphan_after_seconds=args.orphan_after_seconds)
            .model_dump(mode="json"),
        )
        publish_private_json(status.model_dump(mode="json"), args.output)
    except (ImportError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(status.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
