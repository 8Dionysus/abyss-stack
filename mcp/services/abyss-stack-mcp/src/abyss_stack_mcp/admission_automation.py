"""Event/backstop orchestration for bounded MCP admission maintenance."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .contracts import Identifier, NonEmpty, StrictModel
from .keeper_specs import build_keeper_specs
from .managed_catalog import build_managed_catalog, publish_catalog, publish_private_json
from .managed_topology import derive_managed_topology
from .observation import RuntimeTargetCatalog
from .preflight import PreflightError, _safe_json
from .preflight_sweep import MCPPreflightSweepStatus, publish_status, run_sweep
from .runtime_overlay import build_runtime_overlay


class KeeperStageOperationalStatus(StrictModel):
    stage: Identifier
    node_id: NonEmpty | None = None
    outcome: Literal["passed", "blocked", "rejected", "revoked"] | None = None
    expires_at: datetime | None = None
    current: bool
    reason_codes: tuple[Identifier, ...]


class KeeperContourStatus(StrictModel):
    organ_id: Identifier
    contour_id: Identifier
    state_id: NonEmpty
    revision: int = Field(ge=1)
    admission_current: bool
    currentness: tuple[NonEmpty, ...]
    blocker_codes: tuple[Identifier, ...]
    next_safe_stage: Identifier | None = None
    transaction_ref: NonEmpty
    evidence_expires_at: datetime | None = None
    last_good_state_ref: NonEmpty | None = None
    last_good_state_digest: NonEmpty | None = None
    full_refresh_cost: int = Field(ge=0)
    planned_refresh_cost: int = Field(ge=0)
    reused_stage_count: int = Field(ge=0)
    refreshed_stage_count: int = Field(ge=0)
    blocked_stage_count: int = Field(ge=0)
    stage_states: tuple[KeeperStageOperationalStatus, ...]


class AdmissionAutomationStatus(StrictModel):
    schema_version: Literal["abyss_mcp_admission_automation_v1"] = (
        "abyss_mcp_admission_automation_v1"
    )
    generated_at: datetime
    overlay_contour_count: int = Field(ge=0)
    overlay_skips: tuple[dict[str, str], ...]
    managed_contour_count: int = Field(ge=0)
    preflight: MCPPreflightSweepStatus
    keepers: tuple[KeeperContourStatus, ...]
    services_started_or_restarted: Literal[False] = False
    registry_mutation_performed: Literal[False] = False
    owner_acceptance_inferred: Literal[False] = False
    proof_verdict_inferred: Literal[False] = False
    task_handle_is_admission_identity: Literal[False] = False
    task_completion_implies_admission: Literal[False] = False
    task_cancellation_erases_evidence: Literal[False] = False
    owner_transaction_survives_task_loss: Literal[True] = True
    next_safe_step: NonEmpty


def run_admission_automation(
    *,
    registry_path: Path,
    deployment_manifest_path: Path,
    runtime_targets_path: Path,
    canary_root: Path,
    deployed_root: Path,
    output_root: Path,
    generated_at: datetime | None = None,
) -> AdmissionAutomationStatus:
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    registry = _safe_json(registry_path, "v2 organ registry")
    deployment = _safe_json(deployment_manifest_path, "deployment manifest")
    targets = RuntimeTargetCatalog.model_validate(
        _safe_json(runtime_targets_path, "runtime targets")
    )
    overlay, skipped = build_runtime_overlay(
        registry,
        deployment,
        targets,
        canary_root=canary_root,
        deployment_manifest_path=deployment_manifest_path,
        generated_at=now,
    )
    overlay_path = output_root / "runtime-overlay.candidate.json"
    publish_private_json(overlay, overlay_path)
    topology = derive_managed_topology(
        overlay,
        deployment,
        deployed_root=deployed_root,
    )
    topology_path = output_root / "managed-topology.json"
    publish_private_json(topology.model_dump(mode="json"), topology_path)
    catalog = build_managed_catalog(
        topology,
        registry_path=registry_path,
        deployment_manifest_path=deployment_manifest_path,
        deployed_root=deployed_root,
    )
    catalog_path = output_root / "managed-contours.json"
    publish_catalog(catalog, catalog_path)
    preflight_root = output_root / "preflight"
    preflight = run_sweep(catalog_path, preflight_root, generated_at=now)
    publish_status(preflight, preflight_root / "current.json")
    spec_status = build_keeper_specs(
        registry,
        catalog,
        output_root=output_root / "keeper",
        generated_at=now,
    )
    keepers = _run_keeper_cycles(
        spec_status.entries,
        output_root=output_root,
        generated_at=now,
    )
    status = AdmissionAutomationStatus(
        generated_at=now,
        overlay_contour_count=len(overlay["contours"]),
        overlay_skips=skipped,
        managed_contour_count=len(catalog.contours),
        preflight=preflight,
        keepers=keepers,
        next_safe_step=(
            "refresh the expired owner registry through owner proof and acceptance"
            if "registry_source_expired" in {
                reason for entry in preflight.entries for reason in entry.reason_codes
            }
            else (
                "repair the first preflight blocker"
                if preflight.blocked_count
                else "refresh owner-issued keeper evidence in dependency order"
            )
        ),
    )
    publish_private_json(status.model_dump(mode="json"), output_root / "current.json")
    return status


def _run_keeper_cycles(
    entries: tuple[Any, ...],
    *,
    output_root: Path,
    generated_at: datetime,
) -> tuple[KeeperContourStatus, ...]:
    try:
        from aoa_sdk.contracts.admission_keeper import AdmissionKeeperSpec
        from aoa_sdk.organs import KeeperEvidenceStore, run_keeper_cycle
    except ImportError as exc:
        raise PreflightError("compatible aoa-sdk Admission Keeper is unavailable") from exc
    statuses: list[KeeperContourStatus] = []
    for entry in entries:
        spec = AdmissionKeeperSpec.model_validate_json(Path(entry.spec_path).read_bytes())
        cycle = run_keeper_cycle(
            spec,
            store=KeeperEvidenceStore(
                output_root / "keeper-state" / entry.organ_id / entry.contour_id
            ),
            generated_at=generated_at,
        )
        statuses.append(
            KeeperContourStatus(
                organ_id=entry.organ_id,
                contour_id=entry.contour_id,
                state_id=cycle.state.state_id,
                revision=cycle.state.revision,
                admission_current=cycle.state.admission_current,
                currentness=cycle.state.currentness,
                blocker_codes=cycle.state.blocker_codes,
                next_safe_stage=cycle.state.next_safe_stage,
                transaction_ref=cycle.transaction_ref,
                evidence_expires_at=min(
                    (
                        stage.expires_at
                        for stage in cycle.state.stages
                        if stage.current and stage.expires_at is not None
                    ),
                    default=None,
                ),
                last_good_state_ref=cycle.state.last_good_state_ref,
                last_good_state_digest=cycle.state.last_good_state_digest,
                full_refresh_cost=cycle.plan.full_refresh_cost,
                planned_refresh_cost=cycle.plan.planned_refresh_cost,
                reused_stage_count=cycle.plan.reused_stage_count,
                refreshed_stage_count=cycle.plan.refreshed_stage_count,
                blocked_stage_count=cycle.plan.blocked_stage_count,
                stage_states=tuple(
                    KeeperStageOperationalStatus.model_validate(
                        stage.model_dump(mode="python")
                    )
                    for stage in cycle.state.stages
                ),
            )
        )
    return tuple(statuses)


def main() -> int:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-admission-automation")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--deployment-manifest", type=Path, required=True)
    parser.add_argument("--runtime-targets", type=Path, required=True)
    parser.add_argument("--canary-root", type=Path, required=True)
    parser.add_argument("--deployed-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        status = run_admission_automation(
            registry_path=args.registry,
            deployment_manifest_path=args.deployment_manifest,
            runtime_targets_path=args.runtime_targets,
            canary_root=args.canary_root,
            deployed_root=args.deployed_root,
            output_root=args.output_root,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(status.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
