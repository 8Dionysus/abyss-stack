#!/usr/bin/env python3
"""Durable subprocess bridge from AoARunner to abyss-stack governed execution."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, Protocol

from pydantic import TypeAdapter

from aoa_sdk.contracts.control_plane import (  # type: ignore[import-untyped]
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRequirement,
    CancelCommand,
    CloseoutBundleRef,
    CommandReceipt,
    ContentRef,
    ControlPlaneContractError,
    EvidenceBundleRef,
    ExecutionEvent,
    ObservedABIRef,
    ObservedSourceRef,
    PauseCommand,
    ProvenanceRef,
    RecoverCommand,
    ResumeCommand,
    RunOutcome,
    RunPlan,
    RunStatus,
    RuntimeCommand,
    RuntimeProfile,
    RuntimeSnapshotObservation,
    SessionHandle,
    StartCommand,
    assert_approval_decision_matches_request,
    assert_approvals_satisfied,
    assert_closeout_bundle_scope,
    assert_runtime_snapshot_observation,
    assert_run_plan_digest,
    canonical_digest,
    command_digest,
    execution_event_digest,
)


ADAPTER_VERSION = "abyss_stack_agent_os_adapter_v1"
PROFILE_SCHEMA_VERSION = "abyss_stack_agent_os_runtime_profile_v1"
BINDING_SCHEMA_VERSION = "abyss_stack_agent_os_binding_v1"
STATE_SCHEMA_VERSION = "abyss_stack_agent_os_runtime_state_v1"
RESPONSE_SCHEMA_VERSION = "abyss_stack_agent_os_bridge_response_v1"
PROFILE_ARTIFACT_REF = (
    "mechanics/governed-execution/parts/agent-os-adapter/runtime-profile.v1.json"
)
PART_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PART_ROOT.parents[3]
PROFILE_PATH = PART_ROOT / "runtime-profile.v1.json"
GOVERNED_RUNNER_PATH = (
    PART_ROOT.parent / "governed-runner" / "aoa_governed_execution.py"
)
MAX_INPUT_BYTES = 16 * 1024 * 1024
ZERO_DIGEST = "sha256:" + "0" * 64

Operation = Literal[
    "observe_snapshot",
    "dispatch",
    "approval_requests",
    "approval_decisions",
    "command_receipts",
    "renew_approvals",
    "apply_approval",
    "status",
    "events",
    "outcome",
    "closeout",
]


class AgentOSBridgeError(RuntimeError):
    """One fail-closed runtime bridge error with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GovernedBackend(Protocol):
    def prepare_run(
        self, request_file: str | Path, **kwargs: Any
    ) -> dict[str, Any]: ...

    def resume_run(self, run_id: str, **kwargs: Any) -> dict[str, Any]: ...

    def load_approval(self, run_dir: Path) -> dict[str, Any]: ...

    def advance_milestone(
        self,
        approval: dict[str, Any],
        *,
        milestone: str,
        status: str,
        notes: str,
    ) -> dict[str, Any]: ...

    def write_json(self, path: Path, payload: dict[str, Any]) -> None: ...

    def approval_artifact(self, run_dir: Path) -> Path: ...


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise AgentOSBridgeError(
            "artifact_unavailable",
            f"cannot read runtime artifact coordinate: {path}",
        ) from exc
    return f"sha256:{digest.hexdigest()}"


def sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def read_artifact_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            payload = handle.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise AgentOSBridgeError(
            "artifact_unavailable",
            f"cannot read runtime artifact coordinate: {path}",
        ) from exc
    if len(payload) > MAX_INPUT_BYTES:
        raise AgentOSBridgeError(
            "artifact_too_large",
            f"runtime artifact exceeds {MAX_INPUT_BYTES} bytes: {path}",
        )
    return payload


def canonical_json_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def load_governed_backend() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "abyss_stack_governed_execution_agent_os",
        GOVERNED_RUNNER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AgentOSBridgeError(
            "governed_backend_unavailable",
            "cannot load the governed execution backend",
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentOSRuntimeBridge:
    """Runtime-owner implementation of the exact C4 adapter contract."""

    def __init__(
        self,
        state_root: str | Path,
        *,
        backend: GovernedBackend | None = None,
        profile_path: str | Path = PROFILE_PATH,
        clock: Callable[[], datetime] = utc_now,
        gate_provider: Callable[[], dict[str, Any]] | None = None,
        advisory_provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        proposal_provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.state_root = Path(state_root)
        if not self.state_root.is_absolute():
            raise AgentOSBridgeError(
                "invalid_state_root",
                "runtime adapter state root must be absolute",
            )
        self.profile_path = Path(profile_path)
        self.profile_descriptor = self._load_profile_descriptor()
        self.backend = backend or load_governed_backend()
        self.clock = clock
        self.gate_provider = gate_provider
        self.advisory_provider = advisory_provider
        self.proposal_provider = proposal_provider
        self._admitted_source_bytes: dict[tuple[str, str], bytes] = {}
        self._admitted_source_paths: dict[tuple[str, str], Path] = {}
        self._admitted_abi_bytes: dict[tuple[str, str], bytes] = {}
        self._admitted_abi_paths: dict[tuple[str, str], Path] = {}

    def invoke(self, operation: Operation, payload: Mapping[str, Any]) -> Any:
        if payload.get("operation") != operation:
            raise AgentOSBridgeError(
                "operation_mismatch",
                "payload operation differs from the invoked operation",
            )
        self._clear_admitted_material()
        plan, session, profile, binding, compatibility = self._validate_envelope(
            payload
        )
        with self._session_lock(session.session_id):
            if operation == "observe_snapshot":
                state = self._load_or_initialize(
                    plan,
                    session,
                    profile,
                    binding,
                )
                observation = self._observe_snapshot(
                    plan,
                    session,
                    profile,
                    binding,
                    observed_not_before=RunStatus.model_validate(
                        state["status"]
                    ).updated_at,
                )
                self._assert_runtime_inputs(
                    plan,
                    binding,
                    compatibility,
                )
                state["last_observation"] = observation.model_dump(mode="json")
                self._save_state(session.session_id, state)
                return observation.model_dump(mode="json")

            state = self._load_bound_state(
                plan,
                session,
                profile,
                binding,
            )
            if operation == "dispatch":
                result = self._dispatch(
                    state,
                    plan,
                    session,
                    profile,
                    binding,
                    compatibility,
                    TypeAdapter(RuntimeCommand).validate_python(payload.get("command")),
                )
                self._save_state(session.session_id, state)
                return result.model_dump(mode="json")
            if operation == "approval_requests":
                return list(state["approval_requests"])
            if operation == "approval_decisions":
                return list(state["approval_decisions"])
            if operation == "command_receipts":
                return [entry["receipt"] for entry in state["commands"]]
            if operation == "renew_approvals":
                requested_at = _aware_from_json(
                    payload.get("requested_at"),
                    "requested_at",
                )
                requests = self._renew_approvals(
                    state,
                    plan,
                    session,
                    profile,
                    compatibility,
                    requested_at,
                )
                self._save_state(session.session_id, state)
                return [item.model_dump(mode="json") for item in requests]
            if operation == "apply_approval":
                status = self._apply_approval(
                    state,
                    plan,
                    session,
                    profile,
                    compatibility,
                    ApprovalDecision.model_validate(payload.get("approval")),
                )
                self._save_state(session.session_id, state)
                return status.model_dump(mode="json")
            if operation == "status":
                return state["status"]
            if operation == "events":
                after_sequence = payload.get("after_sequence")
                if not isinstance(after_sequence, int) or after_sequence < -1:
                    raise AgentOSBridgeError(
                        "invalid_event_cursor",
                        "after_sequence must be an integer at least -1",
                    )
                return [
                    item
                    for item in state["events"]
                    if int(item["sequence"]) > after_sequence
                ]
            if operation == "outcome":
                return state["outcome"]
            if operation == "closeout":
                status = self._closeout(
                    state,
                    plan,
                    session,
                    profile,
                    RunOutcome.model_validate(payload.get("outcome")),
                    CloseoutBundleRef.model_validate(payload.get("bundle")),
                )
                self._save_state(session.session_id, state)
                return status.model_dump(mode="json")
        raise AgentOSBridgeError(
            "unsupported_operation",
            f"unsupported Agent OS bridge operation: {operation}",
        )

    def _load_profile_descriptor(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AgentOSBridgeError(
                "runtime_profile_unavailable",
                "cannot load the runtime profile descriptor",
            ) from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != PROFILE_SCHEMA_VERSION
            or payload.get("adapter_id") != ADAPTER_VERSION
            or payload.get("runtime_owner") != "abyss-stack"
        ):
            raise AgentOSBridgeError(
                "runtime_profile_invalid",
                "runtime profile descriptor identity is invalid",
            )
        return payload

    def _validate_envelope(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[
        RunPlan,
        SessionHandle,
        RuntimeProfile,
        dict[str, Any],
        dict[str, Any],
    ]:
        try:
            plan = RunPlan.model_validate(payload.get("plan"))
            session = SessionHandle.model_validate(payload.get("session"))
            profile = RuntimeProfile.model_validate(payload.get("profile"))
        except Exception as exc:
            raise AgentOSBridgeError(
                "control_plane_payload_invalid",
                "plan, session, or runtime profile violates the SDK contract",
            ) from exc
        binding = payload.get("binding")
        if not isinstance(binding, dict):
            raise AgentOSBridgeError(
                "runtime_binding_invalid",
                "runtime binding must be an object",
            )
        assert_run_plan_digest(plan)
        if (
            session.plan_digest != plan.plan_digest
            or session.snapshot_digest != plan.snapshot.snapshot_digest
            or session.correlation_id != plan.correlation_id
        ):
            raise AgentOSBridgeError(
                "session_plan_mismatch",
                "session does not bind the exact plan",
            )
        if profile != plan.runtime_profile:
            raise AgentOSBridgeError(
                "runtime_profile_mismatch",
                "payload profile differs from the plan runtime profile",
            )
        self._assert_profile(profile)
        self._assert_binding(plan, profile, binding)
        compatibility = self._compatibility_for(plan, binding)
        self._assert_compatibility(plan, binding, compatibility)
        return plan, session, profile, binding, compatibility

    def _assert_profile(self, profile: RuntimeProfile) -> None:
        descriptor = self.profile_descriptor
        expected_provenance = ProvenanceRef(
            owner_repo="abyss-stack",
            artifact_ref=PROFILE_ARTIFACT_REF,
            source_ref=str(descriptor["source_ref"]),
            artifact_digest=sha256_file(self.profile_path),
            schema_ref=str(descriptor["schema_ref"]),
            schema_version=str(descriptor["schema_version"]),
        )
        compared = {
            "profile_id": profile.profile_id,
            "runtime_owner": profile.runtime_owner,
            "adapter_id": profile.adapter_id,
            "adapter_protocol_version": profile.adapter_protocol_version,
            "supported_plan_schema_versions": list(
                profile.supported_plan_schema_versions
            ),
            "supported_event_schema_versions": list(
                profile.supported_event_schema_versions
            ),
            "supported_effect_classes": list(profile.supported_effect_classes),
        }
        expected = {key: descriptor[key] for key in compared}
        if compared != expected or profile.provenance != expected_provenance:
            raise AgentOSBridgeError(
                "runtime_profile_mismatch",
                "runtime profile is not the exact owner descriptor",
            )
        expected_constraints = {
            (str(item["owner_repo"]), str(item["artifact_ref"])): {
                "owner_repo": str(item["owner_repo"]),
                "artifact_ref": str(item["artifact_ref"]),
                "source_ref": str(item["source_ref"]),
                "schema_ref": str(item["schema_ref"]),
                "schema_version": str(item["schema_version"]),
            }
            for item in descriptor["required_constraint_artifacts"]
        }
        actual_constraints = {
            (item.owner_repo, item.artifact_ref): {
                "owner_repo": item.owner_repo,
                "artifact_ref": item.artifact_ref,
                "source_ref": item.source_ref,
                "schema_ref": item.schema_ref,
                "schema_version": item.schema_version,
            }
            for item in profile.constraint_refs
        }
        if actual_constraints != expected_constraints:
            raise AgentOSBridgeError(
                "runtime_constraints_mismatch",
                "runtime profile constraint provenance does not match the owner "
                "descriptor",
            )

    def _assert_binding(
        self,
        plan: RunPlan,
        profile: RuntimeProfile,
        binding: dict[str, Any],
    ) -> None:
        required = {
            "schema_version",
            "binding_id",
            "runtime_owner",
            "adapter_id",
            "plan_digest",
            "scenario_id",
            "playbook_id",
            "request_ref",
            "request_path",
            "source_locations",
            "abi_locations",
            "adapter_contract_ref",
        }
        if set(binding) != required:
            raise AgentOSBridgeError(
                "runtime_binding_invalid",
                "runtime binding fields differ from the v1 contract",
            )
        if (
            binding["schema_version"] != BINDING_SCHEMA_VERSION
            or binding["runtime_owner"] != "abyss-stack"
            or binding["adapter_id"] != ADAPTER_VERSION
            or binding["plan_digest"] != plan.plan_digest
            or binding["scenario_id"] != plan.scenario_binding.scenario.scenario_id
        ):
            raise AgentOSBridgeError(
                "runtime_binding_mismatch",
                "runtime binding identity differs from the exact plan",
            )
        try:
            request_ref = ProvenanceRef.model_validate(binding["request_ref"])
            contract_ref = ProvenanceRef.model_validate(binding["adapter_contract_ref"])
        except Exception as exc:
            raise AgentOSBridgeError(
                "runtime_binding_invalid",
                "runtime binding provenance is invalid",
            ) from exc
        if contract_ref != profile.provenance:
            raise AgentOSBridgeError(
                "runtime_binding_mismatch",
                "runtime binding contract differs from the runtime profile",
            )
        admitted_input_refs = {
            *plan.scenario_binding.input_refs,
            *(
                item.artifact_ref
                for item in plan.scenario_binding.input_artifact_bindings
            ),
        }
        if request_ref not in admitted_input_refs or not any(
            request_ref in step.input_refs for step in plan.steps
        ):
            raise AgentOSBridgeError(
                "runtime_request_unbound",
                "runtime request is not an admitted plan input",
            )
        source_locations = _location_map(
            binding["source_locations"],
            id_field="artifact_ref",
            label="source",
        )
        abi_locations = _location_map(
            binding["abi_locations"],
            id_field="abi_id",
            label="ABI",
        )
        expected_sources = {
            (item.owner_repo, item.artifact_ref) for item in plan.snapshot.source_refs
        }
        expected_abis = {
            (item.owner_repo, item.abi_id) for item in plan.snapshot.abi_refs
        }
        if set(source_locations) != expected_sources:
            raise AgentOSBridgeError(
                "runtime_source_map_mismatch",
                "source locations do not cover the exact plan snapshot",
            )
        if set(abi_locations) != expected_abis:
            raise AgentOSBridgeError(
                "runtime_abi_map_mismatch",
                "ABI locations do not cover the exact plan snapshot",
            )
        request_key = (request_ref.owner_repo, request_ref.artifact_ref)
        request_path = binding["request_path"]
        if (
            not isinstance(request_path, str)
            or not Path(request_path).is_absolute()
            or source_locations[request_key] != request_path
        ):
            raise AgentOSBridgeError(
                "runtime_request_coordinate_mismatch",
                "request path differs from its exact source coordinate",
            )

    def _compatibility_for(
        self,
        plan: RunPlan,
        binding: dict[str, Any],
    ) -> dict[str, Any]:
        matches = [
            item
            for item in self.profile_descriptor["compatibility"]
            if item["scenario_id"] == plan.scenario_binding.scenario.scenario_id
            and item["playbook_id"] == binding["playbook_id"]
        ]
        if len(matches) != 1:
            raise AgentOSBridgeError(
                "unsupported_plan",
                "runtime profile does not admit this scenario/playbook pair",
            )
        return dict(matches[0])

    def _assert_compatibility(
        self,
        plan: RunPlan,
        binding: dict[str, Any],
        compatibility: dict[str, Any],
    ) -> None:
        active_steps = [step.step_id for step in plan.steps]
        if active_steps not in compatibility["accepted_step_sets"]:
            raise AgentOSBridgeError(
                "unsupported_plan_steps",
                "active plan steps do not match an admitted runtime contour",
            )
        allowed_effects = set(plan.runtime_profile.supported_effect_classes)
        if any(step.effect_class not in allowed_effects for step in plan.steps):
            raise AgentOSBridgeError(
                "unsupported_plan_effect",
                "plan contains an effect outside the runtime profile",
            )
        admitted_steps = {
            step_id
            for step_ids in compatibility["accepted_step_sets"]
            for step_id in step_ids
        }
        mapped_steps = {
            step_id
            for step_ids in compatibility["phase_step_map"].values()
            for step_id in step_ids
        }
        expected_effects = compatibility["step_effect_map"]
        if (
            mapped_steps != admitted_steps
            or set(expected_effects) != admitted_steps
        ):
            raise AgentOSBridgeError(
                "runtime_profile_invalid",
                "runtime phase and effect maps must cover the exact admitted steps",
            )
        if {
            step.step_id: step.effect_class for step in plan.steps
        } != {
            step_id: expected_effects[step_id] for step_id in active_steps
        }:
            raise AgentOSBridgeError(
                "unsupported_plan_effect",
                "plan step effects differ from the admitted runtime contour",
            )
        contour = compatibility["owner_contour"]
        abi_matches = [
            item
            for item in plan.snapshot.abi_refs
            if (
                item.owner_repo,
                item.abi_id,
                item.abi_version,
                item.artifact_digest,
            )
            == (
                contour["owner_repo"],
                contour["abi_id"],
                contour["abi_version"],
                contour["artifact_digest"],
            )
        ]
        if len(abi_matches) != 1:
            raise AgentOSBridgeError(
                "owner_contour_mismatch",
                "plan does not pin the admitted playbook contour ABI",
            )
        if (
            plan.scenario_binding.scenario.provenance.owner_repo
            != contour["owner_repo"]
            or plan.scenario_binding.scenario.provenance.source_ref
            != contour["source_ref"]
        ):
            raise AgentOSBridgeError(
                "owner_contour_mismatch",
                "scenario provenance differs from the admitted owner contour",
            )
        approval_operations = set(compatibility["approval_operations"].values())
        actual_operations = {item.operation for item in plan.approval_requirements}
        runtime_approval_requirements = [
            {
                "requirement_id": item.requirement_id,
                "operation": item.operation,
                "risk_class": item.risk_class,
                "applies_to_step_ids": list(item.applies_to_step_ids),
                "required_evidence_refs": [
                    ref.model_dump(mode="json") for ref in item.required_evidence_refs
                ],
                "expires_after_seconds": item.expires_after_seconds,
                "renewable": item.renewable,
            }
            for item in plan.approval_requirements
        ]
        profile_runtime_approval_requirements = [
            {
                "requirement_id": item.requirement_id,
                "operation": item.operation,
                "risk_class": item.risk_class,
                "applies_to_step_ids": list(item.applies_to_step_ids),
                "required_evidence_refs": [
                    ref.model_dump(mode="json")
                    for ref in item.required_evidence_refs
                ],
                "expires_after_seconds": item.expires_after_seconds,
                "renewable": item.renewable,
            }
            for item in plan.runtime_profile.runtime_approval_requirements
        ]
        if (
            actual_operations != approval_operations
            or any(
                item.approval_owner != plan.runtime_profile.provenance
                for item in plan.approval_requirements
            )
            or runtime_approval_requirements
            != compatibility["runtime_approval_requirements"]
            or profile_runtime_approval_requirements
            != compatibility["runtime_approval_requirements"]
        ):
            raise AgentOSBridgeError(
                "approval_mapping_mismatch",
                (
                    "plan differs from the exact governed approval requirements "
                    "for its admitted contour"
                ),
            )
        runtime_evidence_requirements = [
            item.model_dump(mode="json")
            for item in plan.evidence_requirements
            if (
                item.producer_owner == "abyss-stack"
                and item.artifact_binding == "step_output"
            )
        ]
        if (
            runtime_evidence_requirements
            != compatibility["runtime_evidence_requirements"]
        ):
            raise AgentOSBridgeError(
                "runtime_evidence_contract_mismatch",
                "plan runtime evidence requirements differ from the admitted contour",
            )
        admitted_input_evidence_requirements = [
            item.model_dump(mode="json")
            for item in plan.evidence_requirements
            if item.artifact_binding == "scenario_input"
        ]
        if (
            admitted_input_evidence_requirements
            != compatibility["admitted_input_evidence_requirements"]
        ):
            raise AgentOSBridgeError(
                "runtime_input_evidence_contract_mismatch",
                "plan input evidence requirements differ from the admitted contour",
            )
        actual_evidence_requirements = [
            item.model_dump(mode="json") for item in plan.evidence_requirements
        ]
        admitted_evidence_requirements = [
            *compatibility["runtime_evidence_requirements"],
            *compatibility["admitted_input_evidence_requirements"],
        ]
        if sorted(
            json.dumps(item, sort_keys=True, separators=(",", ":"))
            for item in actual_evidence_requirements
        ) != sorted(
            json.dumps(item, sort_keys=True, separators=(",", ":"))
            for item in admitted_evidence_requirements
        ):
            raise AgentOSBridgeError(
                "runtime_evidence_contract_mismatch",
                (
                    "complete plan evidence requirements differ from the "
                    "admitted contour"
                ),
            )
        actual_input_kinds = [
            item.artifact_kind
            for item in plan.scenario_binding.input_artifact_bindings
        ]
        if actual_input_kinds != compatibility["required_input_artifact_kinds"]:
            raise AgentOSBridgeError(
                "runtime_input_contract_mismatch",
                "typed scenario inputs differ from the admitted contour",
            )
        self._assert_runtime_inputs(plan, binding, compatibility)

    def _assert_runtime_inputs(
        self,
        plan: RunPlan,
        binding: dict[str, Any],
        compatibility: dict[str, Any],
    ) -> None:
        lane = str(compatibility["execution_lane"])
        request_ref = ProvenanceRef.model_validate(binding["request_ref"])
        request_key = (request_ref.owner_repo, request_ref.artifact_ref)
        try:
            request = json.loads(
                self._bound_source_bytes(binding, request_key).decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AgentOSBridgeError(
                "runtime_request_unavailable",
                "cannot load the runtime request artifact",
            ) from exc
        if not isinstance(request, dict):
            raise AgentOSBridgeError(
                "runtime_request_mismatch",
                "runtime request must be a JSON object",
            )
        if lane == "governed_repository_change":
            if (
                request.get("playbook_id") != compatibility["playbook_id"]
                or not isinstance(request.get("goal"), str)
                or not request["goal"].strip()
            ):
                raise AgentOSBridgeError(
                    "runtime_request_mismatch",
                    "governed request does not match the admitted playbook",
                )
            return

        inputs = self._load_typed_scenario_inputs(plan, binding)
        primary_kind = str(compatibility["primary_input_artifact_kind"])
        primary = next(
            (
                item.artifact_ref
                for item in plan.scenario_binding.input_artifact_bindings
                if item.artifact_kind == primary_kind
            ),
            None,
        )
        if (
            primary is None
            or ProvenanceRef.model_validate(binding["request_ref"]) != primary
            or inputs.get(primary_kind) != request
        ):
            raise AgentOSBridgeError(
                "runtime_request_mismatch",
                "runtime request is not the admitted primary typed input",
            )
        if lane == "a2a_return_review":
            self._assert_a2a_inputs(inputs)
            return
        if lane == "runtime_degradation_recovery":
            self._assert_runtime_degradation_input(inputs)
            return
        raise AgentOSBridgeError(
            "runtime_profile_invalid",
            f"unsupported execution lane: {lane}",
        )

    def _load_typed_scenario_inputs(
        self,
        plan: RunPlan,
        binding: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        source_locations = _location_map(
            binding["source_locations"],
            id_field="artifact_ref",
            label="source",
        )
        loaded: dict[str, dict[str, Any]] = {}
        for item in plan.scenario_binding.input_artifact_bindings:
            key = (item.artifact_ref.owner_repo, item.artifact_ref.artifact_ref)
            try:
                payload = json.loads(
                    self._bound_source_bytes(
                        binding,
                        key,
                        source_locations=source_locations,
                    ).decode("utf-8")
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AgentOSBridgeError(
                    "runtime_request_unavailable",
                    f"cannot load typed scenario input {item.artifact_kind}",
                ) from exc
            if not isinstance(payload, dict):
                raise AgentOSBridgeError(
                    "runtime_request_mismatch",
                    f"typed scenario input {item.artifact_kind} must be an object",
                )
            loaded[item.artifact_kind] = payload
        return loaded

    @staticmethod
    def _assert_a2a_inputs(inputs: dict[str, dict[str, Any]]) -> None:
        request = inputs["summon_request"]
        decision = inputs["summon_decision"]
        result = inputs["child_task_result"]
        quest_passport = request.get("quest_passport")
        summon_request = request.get("summon_request")
        expected_outputs = request.get("expected_outputs")
        remote_task = result.get("remote_task")
        if (
            not isinstance(quest_passport, dict)
            or not isinstance(quest_passport.get("route_anchor"), str)
            or not quest_passport["route_anchor"].strip()
            or not isinstance(summon_request, dict)
            or not isinstance(summon_request.get("parent_task_id"), str)
            or not summon_request["parent_task_id"].strip()
            or summon_request.get("review_required") is not True
            or not isinstance(expected_outputs, list)
            or not expected_outputs
            or not all(isinstance(item, str) and item for item in expected_outputs)
            or not isinstance(decision.get("allowed"), bool)
            or not isinstance(decision.get("expected_outputs"), list)
            or decision.get("expected_outputs") != expected_outputs
            or decision.get("parent_task_id")
            != summon_request["parent_task_id"]
            or decision.get("summon_request_digest")
            != canonical_json_digest(request)
            or result.get("reviewed") is not True
            or result.get("review_status") != "reviewed"
            or not isinstance(remote_task, dict)
            or not isinstance(remote_task.get("task_id"), str)
            or not remote_task["task_id"].strip()
            or remote_task.get("parent_task_id")
            != summon_request["parent_task_id"]
            or remote_task.get("state")
            not in {"completed", "failed", "cancelled"}
            or not isinstance(remote_task.get("returned_artifacts"), list)
            or not all(
                isinstance(item, str) and bool(item.strip())
                for item in remote_task.get("returned_artifacts", [])
            )
        ):
            raise AgentOSBridgeError(
                "runtime_request_mismatch",
                "A2A inputs do not form one reviewed parent/decision/return chain",
            )

    @staticmethod
    def _assert_runtime_degradation_input(
        inputs: dict[str, dict[str, Any]],
    ) -> None:
        receipt = inputs["owner_runtime_receipt"]
        containment = receipt.get("containment")
        if (
            receipt.get("schema_version") != "service_degradation_receipt_v1"
            or receipt.get("repo") != "abyss-stack"
            or receipt.get("degraded") is not True
            or receipt.get("operator_visible") is not True
            or not isinstance(receipt.get("receipt_id"), str)
            or not receipt["receipt_id"].strip()
            or not isinstance(receipt.get("service"), str)
            or not receipt["service"].strip()
            or not isinstance(containment, dict)
            or not isinstance(containment.get("kind"), str)
            or not isinstance(containment.get("value"), str)
            or not isinstance(receipt.get("evidence_refs"), list)
            or not receipt["evidence_refs"]
        ):
            raise AgentOSBridgeError(
                "runtime_request_mismatch",
                "runtime degradation input is not an operator-visible owner receipt",
            )

    def _observe_snapshot(
        self,
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        binding: dict[str, Any],
        *,
        observed_not_before: datetime | None = None,
    ) -> RuntimeSnapshotObservation:
        source_locations = _location_map(
            binding["source_locations"],
            id_field="artifact_ref",
            label="source",
        )
        abi_locations = _location_map(
            binding["abi_locations"],
            id_field="abi_id",
            label="ABI",
        )
        admitted_sources: dict[tuple[str, str], bytes] = {}
        admitted_source_paths: dict[tuple[str, str], Path] = {}
        observed_sources: list[ObservedSourceRef] = []
        for item in plan.snapshot.source_refs:
            key = (item.owner_repo, item.artifact_ref)
            payload = read_artifact_bytes(Path(source_locations[key]))
            digest = sha256_bytes(payload)
            admitted_sources[key] = payload
            admitted_source_paths[key] = self._materialize_bound_bytes(
                session,
                material_class="source",
                key=key,
                payload=payload,
                digest=digest,
            )
            observed_sources.append(
                ObservedSourceRef(
                    owner_repo=item.owner_repo,
                    artifact_ref=item.artifact_ref,
                    artifact_digest=digest,
                )
            )
        admitted_abis: dict[tuple[str, str], bytes] = {}
        admitted_abi_paths: dict[tuple[str, str], Path] = {}
        observed_abis: list[ObservedABIRef] = []
        for item in plan.snapshot.abi_refs:
            key = (item.owner_repo, item.abi_id)
            payload = read_artifact_bytes(Path(abi_locations[key]))
            digest = sha256_bytes(payload)
            admitted_abis[key] = payload
            admitted_abi_paths[key] = self._materialize_bound_bytes(
                session,
                material_class="abi",
                key=key,
                payload=payload,
                digest=digest,
            )
            observed_abis.append(
                ObservedABIRef(
                    owner_repo=item.owner_repo,
                    abi_id=item.abi_id,
                    abi_version=item.abi_version,
                    artifact_digest=digest,
                )
            )
        self._admitted_source_bytes = admitted_sources
        self._admitted_source_paths = admitted_source_paths
        self._admitted_abi_bytes = admitted_abis
        self._admitted_abi_paths = admitted_abi_paths
        observed_at = max(
            _aware(self.clock(), "runtime clock"),
            session.prepared_at,
            (
                _aware(
                    observed_not_before,
                    "runtime observation lower bound",
                )
                if observed_not_before is not None
                else session.prepared_at
            ),
        )
        token = canonical_json_digest(
            {
                "session_id": session.session_id,
                "snapshot_digest": plan.snapshot.snapshot_digest,
                "observed_at": observed_at.isoformat(),
            }
        )
        return RuntimeSnapshotObservation(
            observation_id=f"abyss-stack-observation:{token.removeprefix('sha256:')}",
            session_id=session.session_id,
            correlation_id=session.correlation_id,
            plan_digest=plan.plan_digest,
            source_refs=tuple(observed_sources),
            abi_refs=tuple(observed_abis),
            observed_at=observed_at,
            observed_by=profile.provenance,
        )

    def _clear_admitted_material(self) -> None:
        self._admitted_source_bytes = {}
        self._admitted_source_paths = {}
        self._admitted_abi_bytes = {}
        self._admitted_abi_paths = {}

    def _materialize_bound_bytes(
        self,
        session: SessionHandle,
        *,
        material_class: Literal["source", "abi"],
        key: tuple[str, str],
        payload: bytes,
        digest: str,
    ) -> Path:
        token = canonical_json_digest(
            {
                "material_class": material_class,
                "owner_repo": key[0],
                "identity": key[1],
                "artifact_digest": digest,
            }
        ).removeprefix("sha256:")
        path = (
            self.state_root
            / "materialized-snapshots"
            / _session_token(session.session_id)
            / material_class
            / f"{token}.bin"
        )
        if path.exists():
            if sha256_file(path) != digest:
                raise AgentOSBridgeError(
                    "materialized_snapshot_mismatch",
                    "existing private runtime materialization differs from "
                    "captured bytes",
                )
            path.chmod(0o400)
            return path
        _atomic_write_bytes(path, payload)
        if sha256_file(path) != digest:
            raise AgentOSBridgeError(
                "materialized_snapshot_mismatch",
                "private runtime materialization differs from captured bytes",
            )
        path.chmod(0o400)
        return path

    def _load_or_initialize(
        self,
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        binding: dict[str, Any],
    ) -> dict[str, Any]:
        state = self._load_state(session.session_id)
        if state is not None:
            self._assert_state_binding(state, plan, session, profile, binding)
            state.setdefault("approval_effects", [])
            state.setdefault("last_governed_interruption", None)
            return state
        status = RunStatus(
            session_id=session.session_id,
            correlation_id=session.correlation_id,
            state="prepared",
            revision=0,
            updated_at=session.prepared_at,
            observed_by=profile.provenance,
        )
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "plan": plan.model_dump(mode="json"),
            "session": session.model_dump(mode="json"),
            "profile": profile.model_dump(mode="json"),
            "binding": binding,
            "status": status.model_dump(mode="json"),
            "events": [],
            "commands": [],
            "rejected_commands": [],
            "approval_requests": [],
            "approval_decisions": [],
            "approval_effects": [],
            "outcome": None,
            "execution_lane": None,
            "governed_run_id": None,
            "governed_start_command": None,
            "last_governed_interruption": None,
            "last_observation": None,
            "runtime_artifact_refs": [],
        }

    def _load_bound_state(
        self,
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        binding: dict[str, Any],
    ) -> dict[str, Any]:
        state = self._load_state(session.session_id)
        if state is None:
            raise AgentOSBridgeError(
                "session_not_observed",
                "observe_snapshot must initialize the runtime session first",
            )
        self._assert_state_binding(state, plan, session, profile, binding)
        state.setdefault("approval_effects", [])
        state.setdefault("last_governed_interruption", None)
        return state

    @staticmethod
    def _assert_state_binding(
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        binding: dict[str, Any],
    ) -> None:
        if (
            state.get("schema_version") != STATE_SCHEMA_VERSION
            or state.get("plan") != plan.model_dump(mode="json")
            or state.get("session") != session.model_dump(mode="json")
            or state.get("profile") != profile.model_dump(mode="json")
            or state.get("binding") != binding
        ):
            raise AgentOSBridgeError(
                "durable_session_binding_mismatch",
                "durable runtime session differs from the exact request",
            )

    def _dispatch(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        binding: dict[str, Any],
        compatibility: dict[str, Any],
        command: RuntimeCommand,
    ) -> CommandReceipt:
        previous = _find_command(state["commands"], command.idempotency_key)
        if previous is not None:
            prior_command = TypeAdapter(RuntimeCommand).validate_python(
                previous["command"]
            )
            prior_receipt = CommandReceipt.model_validate(previous["receipt"])
            if command_digest(prior_command) != command_digest(command):
                return self._rejected_receipt(
                    state,
                    command,
                    profile,
                    "idempotency_payload_mismatch",
                )
            return prior_receipt.model_copy(
                update={"status": "duplicate", "event_refs": ()}
            )
        prior_rejection = _find_command(
            state["rejected_commands"],
            command.idempotency_key,
        )
        if prior_rejection is not None:
            prior_command = TypeAdapter(RuntimeCommand).validate_python(
                prior_rejection["command"]
            )
            if command_digest(prior_command) != command_digest(command):
                return self._rejected_receipt(
                    state,
                    command,
                    profile,
                    "idempotency_payload_mismatch",
                )
            return CommandReceipt.model_validate(prior_rejection["receipt"])

        rejection = self._command_rejection(state, plan, session, command)
        if rejection is not None:
            return self._remember_rejection(
                state,
                command,
                profile,
                rejection,
            )
        if isinstance(command, (StartCommand, ResumeCommand, RecoverCommand)):
            self._refresh_and_assert_snapshot(
                state,
                plan,
                session,
                profile,
                binding,
                compatibility,
            )

        first_event = len(state["events"])
        if isinstance(command, StartCommand):
            rejection = self._start(
                state,
                plan,
                session,
                profile,
                binding,
                compatibility,
                command,
            )
            if rejection is not None:
                return self._remember_rejection(
                    state,
                    command,
                    profile,
                    rejection,
                )
        elif isinstance(command, PauseCommand):
            self._transition(
                state,
                profile,
                state_after="paused",
                trigger="pause",
                at=command.issued_at,
            )
        elif isinstance(command, ResumeCommand):
            assert_approvals_satisfied(
                plan,
                (
                    ApprovalDecision.model_validate(item)
                    for item in state["approval_decisions"]
                ),
                session=session,
                at=command.issued_at,
            )
            self._resume(
                state,
                plan,
                session,
                profile,
                binding,
                compatibility,
                command,
            )
        elif isinstance(command, CancelCommand):
            self._transition(
                state,
                profile,
                state_after="cancelled",
                trigger="cancel",
                at=command.issued_at,
            )
            self._record_outcome(
                state,
                plan,
                session,
                profile,
                execution_status="cancelled",
                failure_codes=(),
                governed_summary=None,
            )
        elif isinstance(command, RecoverCommand):
            return self._remember_rejection(
                state,
                command,
                profile,
                "recovery_not_admitted_by_plan",
            )

        self._emit(
            state,
            profile,
            event_kind="command_ack",
            at=command.issued_at,
            command_id=command.command_id,
            idempotency_key=command.idempotency_key,
        )
        new_events = tuple(
            ExecutionEvent.model_validate(item)
            for item in state["events"][first_event:]
        )
        receipt = CommandReceipt(
            command_id=command.command_id,
            idempotency_key=command.idempotency_key,
            command_digest=command_digest(command),
            session_id=session.session_id,
            status="applied",
            resulting_revision=RunStatus.model_validate(state["status"]).revision,
            event_refs=tuple(_event_ref(item) for item in new_events),
            produced_by=profile.provenance,
        )
        state["commands"].append(
            {
                "command": command.model_dump(mode="json"),
                "receipt": receipt.model_dump(mode="json"),
            }
        )
        return receipt

    @staticmethod
    def _command_rejection(
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        command: RuntimeCommand,
    ) -> str | None:
        status = RunStatus.model_validate(state["status"])
        if (
            command.session_id != session.session_id
            or command.correlation_id != session.correlation_id
            or command.plan_digest != plan.plan_digest
        ):
            return "command_scope_mismatch"
        if command.expected_revision != status.revision:
            return "expected_revision_mismatch"
        if isinstance(command, StartCommand):
            return None if status.state == "prepared" else "start_state_invalid"
        if isinstance(command, PauseCommand):
            return None if status.state == "running" else "pause_state_invalid"
        if isinstance(command, ResumeCommand):
            if status.state != "paused":
                return "resume_state_invalid"
            if any(
                item.get("phase") != "completed"
                for item in state.get("approval_effects", [])
            ):
                return "approval_effect_replay_required"
            if command.resume_after_sequence != status.last_event_sequence:
                return "resume_cursor_mismatch"
            return None
        if isinstance(command, RecoverCommand):
            if status.state != "recoverable_failure":
                return "recover_state_invalid"
            if command.recover_after_sequence != status.recover_from_event_sequence:
                return "recover_cursor_mismatch"
            return None
        if isinstance(command, CancelCommand):
            return (
                None
                if status.state
                in {
                    "prepared",
                    "awaiting_approval",
                    "running",
                    "paused",
                    "recoverable_failure",
                }
                else "cancel_state_invalid"
            )
        return "command_kind_unsupported"

    def _start(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        binding: dict[str, Any],
        compatibility: dict[str, Any],
        command: StartCommand,
    ) -> str | None:
        lane = str(compatibility["execution_lane"])
        state["execution_lane"] = lane
        if lane == "a2a_return_review":
            return self._start_a2a_return_review(
                state,
                plan,
                session,
                profile,
                binding,
                command,
            )
        if lane == "runtime_degradation_recovery":
            return self._start_runtime_degradation_recovery(
                state,
                plan,
                session,
                profile,
                binding,
                command,
            )
        if lane != "governed_repository_change":
            return "execution_lane_unsupported"
        start_binding = {
            "command_id": command.command_id,
            "idempotency_key": command.idempotency_key,
            "command_digest": command_digest(command),
        }
        existing_start = state.get("governed_start_command")
        if existing_start is not None and existing_start != start_binding:
            return "governed_start_command_conflict"
        run_id = state.get("governed_run_id")
        if not isinstance(run_id, str) or not run_id:
            token = hashlib.sha256(
                (
                    f"{session.session_id}\0{command.idempotency_key}"
                ).encode("utf-8")
            ).hexdigest()
            run_id = f"agent-os-{token[:32]}"
            state["governed_run_id"] = run_id
            state["governed_start_command"] = start_binding
            self._save_state(session.session_id, state)
        elif existing_start is None:
            return "governed_start_binding_missing"
        request_ref = ProvenanceRef.model_validate(binding["request_ref"])
        request_key = (request_ref.owner_repo, request_ref.artifact_ref)
        policy_key = self._policy_coordinate()
        policy_path = self._policy_path(plan, binding)
        kwargs: dict[str, Any] = {
            "until": "milestone",
            "policy_path": policy_path,
            "log_root": self._governed_root(),
            "run_id": run_id,
            "request_bytes": self._captured_source_bytes(request_key),
            "policy_bytes": self._captured_source_bytes(policy_key),
        }
        if self.gate_provider is not None:
            kwargs["gate_provider"] = self.gate_provider
        if self.advisory_provider is not None:
            kwargs["advisory_provider"] = self.advisory_provider
        if self.proposal_provider is not None:
            kwargs["proposal_provider"] = self.proposal_provider
        try:
            summary = self.backend.prepare_run(
                str(binding["request_path"]),
                **kwargs,
            )
        except Exception:
            failure_code = "governed_prepare_unavailable"
            self._transition(
                state,
                profile,
                state_after="running",
                trigger="start",
                at=command.issued_at,
            )
            self._transition(
                state,
                profile,
                state_after="failed",
                trigger="runtime_failed",
                at=self.clock(),
                failure_code=failure_code,
            )
            self._record_outcome(
                state,
                plan,
                session,
                profile,
                execution_status="failed",
                failure_codes=(failure_code,),
                governed_summary=None,
            )
            return None
        run_id = summary.get("run_id")
        if (
            summary.get("status") != "paused"
            or summary.get("current_milestone") != "plan_freeze"
            or not isinstance(run_id, str)
            or not run_id
        ):
            failure_code = str(
                summary.get("failure_class") or "governed_prepare_failed"
            )
            self._transition(
                state,
                profile,
                state_after="running",
                trigger="start",
                at=command.issued_at,
            )
            self._transition(
                state,
                profile,
                state_after="failed",
                trigger="runtime_failed",
                at=self._summary_time(summary),
                failure_code=failure_code,
            )
            self._record_outcome(
                state,
                plan,
                session,
                profile,
                execution_status="failed",
                failure_codes=(failure_code,),
                governed_summary=summary,
            )
            return None
        requirement = self._approval_requirement(
            plan,
            compatibility,
            "plan_freeze",
        )
        request = self._build_approval_request(
            state,
            plan,
            session,
            requirement,
            requested_at=max(command.issued_at, self._summary_time(summary)),
        )
        self._transition(
            state,
            profile,
            state_after="awaiting_approval",
            trigger="approval_required",
            at=request.requested_at,
            pending_approval_ids=(requirement.requirement_id,),
        )
        self._store_approval_request(state, profile, request)
        return None

    def _start_a2a_return_review(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        binding: dict[str, Any],
        command: StartCommand,
    ) -> str | None:
        self._transition(
            state,
            profile,
            state_after="running",
            trigger="start",
            at=command.issued_at,
        )
        inputs = self._load_typed_scenario_inputs(plan, binding)
        self._retain_scenario_input_artifacts(state, plan, session)
        request = inputs["summon_request"]
        decision = inputs["summon_decision"]
        child_result = inputs["child_task_result"]
        expected_outputs = list(request["expected_outputs"])
        remote_task = dict(child_result["remote_task"])
        returned_artifacts = list(remote_task["returned_artifacts"])
        complete_return = (
            decision["allowed"] is True
            and set(expected_outputs).issubset(returned_artifacts)
        )
        task_id = str(remote_task["task_id"])
        parent_task_id = str(remote_task["parent_task_id"])
        target = {
            "artifact_kind": "codex_local_target",
            "schema_version": "abyss_stack_agent_os_lane_artifact_v1",
            "session_id": session.session_id,
            "parent_task_id": parent_task_id,
            "child_task_id": task_id,
            "execution_surface": decision.get("execution_surface"),
            "lane": decision.get("lane"),
            "capability_execution_claimed": False,
        }
        return_plan = {
            "artifact_kind": "return_plan",
            "schema_version": "abyss_stack_agent_os_lane_artifact_v1",
            "session_id": session.session_id,
            "parent_task_id": parent_task_id,
            "child_task_id": task_id,
            "decision": "return" if complete_return else "safe_stop",
            "returned_artifacts": returned_artifacts,
            "missing_artifacts": sorted(set(expected_outputs) - set(returned_artifacts)),
            "reviewed_child_result": True,
        }
        checkpoint_plan = {
            "artifact_kind": "checkpoint_bridge_plan",
            "schema_version": "abyss_stack_agent_os_lane_artifact_v1",
            "session_id": session.session_id,
            "parent_task_id": parent_task_id,
            "child_task_id": task_id,
            "review_status": "candidate",
            "anchor_artifacts": returned_artifacts,
            "checkpoint_acceptance_claimed": False,
        }
        eval_packet = {
            "artifact_kind": "a2a_return_eval_packet",
            "schema_version": "abyss_stack_agent_os_lane_artifact_v1",
            "session_id": session.session_id,
            "parent_task_id": parent_task_id,
            "child_task_id": task_id,
            "candidate_status": "unreviewed",
            "eval_verdict_claimed": False,
        }
        dry_run = {
            "artifact_kind": "runtime_closeout_dry_run_receipt",
            "schema_version": "abyss_stack_agent_os_lane_artifact_v1",
            "session_id": session.session_id,
            "parent_task_id": parent_task_id,
            "child_task_id": task_id,
            "complete_return": complete_return,
            "dry_run": True,
            "live_automation": False,
            "closeout_grant_claimed": False,
        }
        for artifact in (
            target,
            return_plan,
            checkpoint_plan,
            eval_packet,
            dry_run,
        ):
            self._write_lane_artifact(state, session, artifact)
        summary = {
            "status": "pass" if complete_return else "fail",
            "execution_lane": "a2a_return_review",
            "parent_task_id": parent_task_id,
            "child_task_id": task_id,
            "returned_artifacts": returned_artifacts,
            "missing_artifacts": return_plan["missing_artifacts"],
            "updated_at": self.clock().isoformat(),
        }
        if complete_return:
            self._transition(
                state,
                profile,
                state_after="completed",
                trigger="runtime_completed",
                at=self.clock(),
            )
            self._record_outcome(
                state,
                plan,
                session,
                profile,
                execution_status="succeeded",
                failure_codes=(),
                governed_summary=summary,
            )
            return None
        failure_code = "a2a_incomplete_return"
        self._transition(
            state,
            profile,
            state_after="failed",
            trigger="runtime_failed",
            at=self.clock(),
            failure_code=failure_code,
        )
        self._record_outcome(
            state,
            plan,
            session,
            profile,
            execution_status="failed",
            failure_codes=(failure_code,),
            governed_summary=summary,
        )
        return None

    def _start_runtime_degradation_recovery(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        binding: dict[str, Any],
        command: StartCommand,
    ) -> str | None:
        self._transition(
            state,
            profile,
            state_after="running",
            trigger="start",
            at=command.issued_at,
        )
        receipt = self._load_typed_scenario_inputs(
            plan,
            binding,
        )["owner_runtime_receipt"]
        self._retain_scenario_input_artifacts(state, plan, session)
        stress_lane = {
            "artifact_kind": "runtime_stress_lane",
            "schema_version": "abyss_stack_agent_os_lane_artifact_v1",
            "session_id": session.session_id,
            "source_receipt_id": receipt["receipt_id"],
            "service": receipt["service"],
            "incident_class": receipt.get("incident_class"),
            "containment": receipt["containment"],
            "degraded": True,
            "mutation_widening_blocked": True,
        }
        reentry_gate = {
            "artifact_kind": "runtime_reentry_gate",
            "schema_version": "abyss_stack_agent_os_lane_artifact_v1",
            "session_id": session.session_id,
            "source_receipt_id": receipt["receipt_id"],
            "service": receipt["service"],
            "status": "held_for_resume",
            "operator_visible": True,
            "evidence_refs": receipt["evidence_refs"],
        }
        self._write_lane_artifact(state, session, stress_lane)
        self._write_lane_artifact(state, session, reentry_gate)
        state["degradation_receipt"] = receipt
        self._transition(
            state,
            profile,
            state_after="paused",
            trigger="pause",
            at=self.clock(),
        )
        return None

    def _resume(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        binding: dict[str, Any],
        compatibility: dict[str, Any],
        command: ResumeCommand,
    ) -> None:
        lane = str(compatibility["execution_lane"])
        if lane == "runtime_degradation_recovery":
            self._resume_runtime_degradation_recovery(
                state,
                plan,
                session,
                profile,
                binding,
                command,
            )
            return
        if lane != "governed_repository_change":
            raise AgentOSBridgeError(
                "resume_lane_invalid",
                f"execution lane {lane} does not admit resume",
            )
        self._transition(
            state,
            profile,
            state_after="running",
            trigger="resume",
            at=command.issued_at,
        )
        try:
            summary = self.backend.resume_run(
                self._governed_run_id(state),
                until="done",
                log_root=self._governed_root(),
                advisory_provider=self.advisory_provider,
                proposal_provider=self.proposal_provider,
            )
        except Exception:
            state["last_governed_interruption"] = {
                "code": "governed_runtime_unavailable",
                "observed_at": self.clock().isoformat(),
            }
            self._transition(
                state,
                profile,
                state_after="paused",
                trigger="pause",
                at=self.clock(),
            )
            return
        if summary.get("status") == "pass":
            state["last_governed_interruption"] = None
            self._transition(
                state,
                profile,
                state_after="completed",
                trigger="runtime_completed",
                at=self._summary_time(summary),
            )
            self._record_outcome(
                state,
                plan,
                session,
                profile,
                execution_status="succeeded",
                failure_codes=(),
                governed_summary=summary,
            )
            return
        if summary.get("status") == "fail":
            state["last_governed_interruption"] = None
            failure_code = str(
                summary.get("failure_class") or "governed_runtime_failed"
            )
            self._transition(
                state,
                profile,
                state_after="failed",
                trigger="runtime_failed",
                at=self._summary_time(summary),
                failure_code=failure_code,
            )
            self._record_outcome(
                state,
                plan,
                session,
                profile,
                execution_status="failed",
                failure_codes=(failure_code,),
                governed_summary=summary,
            )
            return
        state["last_governed_interruption"] = {
            "code": "unexpected_governed_pause",
            "observed_at": self._summary_time(summary).isoformat(),
        }
        self._transition(
            state,
            profile,
            state_after="paused",
            trigger="pause",
            at=self._summary_time(summary),
        )

    def _resume_runtime_degradation_recovery(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        binding: dict[str, Any],
        command: ResumeCommand,
    ) -> None:
        self._transition(
            state,
            profile,
            state_after="running",
            trigger="resume",
            at=command.issued_at,
        )
        receipt = self._load_typed_scenario_inputs(
            plan,
            binding,
        )["owner_runtime_receipt"]
        reentry_gate = {
            "artifact_kind": "runtime_reentry_gate",
            "schema_version": "abyss_stack_agent_os_lane_artifact_v1",
            "session_id": session.session_id,
            "source_receipt_id": receipt["receipt_id"],
            "service": receipt["service"],
            "status": "reentered",
            "operator_visible": True,
            "evidence_refs": receipt["evidence_refs"],
        }
        proof_handoff = {
            "artifact_kind": "proof_handoff_candidate",
            "schema_version": "abyss_stack_agent_os_lane_artifact_v1",
            "session_id": session.session_id,
            "source_receipt_id": receipt["receipt_id"],
            "candidate_status": "unreviewed",
            "eval_verdict_claimed": False,
        }
        closeout = {
            "artifact_kind": "runtime_closeout_receipt",
            "schema_version": "abyss_stack_agent_os_lane_artifact_v1",
            "session_id": session.session_id,
            "source_receipt_id": receipt["receipt_id"],
            "service": receipt["service"],
            "interruption_observed": True,
            "resume_observed": True,
            "reentry_status": "reentered",
            "closeout_grant_claimed": False,
        }
        for artifact in (reentry_gate, proof_handoff, closeout):
            self._write_lane_artifact(state, session, artifact)
        summary = {
            "status": "pass",
            "execution_lane": "runtime_degradation_recovery",
            "source_receipt_id": receipt["receipt_id"],
            "service": receipt["service"],
            "interruption_observed": True,
            "resume_observed": True,
            "updated_at": self.clock().isoformat(),
        }
        self._transition(
            state,
            profile,
            state_after="completed",
            trigger="runtime_completed",
            at=self.clock(),
        )
        self._record_outcome(
            state,
            plan,
            session,
            profile,
            execution_status="succeeded",
            failure_codes=(),
            governed_summary=summary,
        )

    def _apply_approval(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        compatibility: dict[str, Any],
        decision: ApprovalDecision,
    ) -> RunStatus:
        existing = [
            ApprovalDecision.model_validate(item)
            for item in state["approval_decisions"]
            if item["decision_id"] == decision.decision_id
        ]
        if existing:
            if existing != [decision]:
                raise AgentOSBridgeError(
                    "approval_decision_conflict",
                    "approval decision ID was reused with different content",
                )
            effects = [
                item
                for item in state["approval_effects"]
                if item.get("decision_id") == decision.decision_id
            ]
            if not effects:
                return RunStatus.model_validate(state["status"])
            if len(effects) != 1:
                raise AgentOSBridgeError(
                    "approval_effect_journal_invalid",
                    "approval decision has an ambiguous durable effect journal",
                )
            if effects[0].get("phase") == "completed":
                return RunStatus.model_validate(state["status"])
            return self._continue_approval_effect(
                state,
                plan,
                session,
                profile,
                compatibility,
                decision,
                effects[0],
            )
        requests = {
            item["requirement_id"]: ApprovalRequest.model_validate(item)
            for item in state["approval_requests"]
        }
        request = requests.get(decision.requirement_id)
        requirements = {
            item.requirement_id: item for item in plan.approval_requirements
        }
        requirement = requirements.get(decision.requirement_id)
        if request is None or requirement is None:
            raise AgentOSBridgeError(
                "approval_request_missing",
                "approval decision has no current runtime request",
            )
        current_request = (
            ApprovalRequest.model_validate(state["approval_requests"][-1])
            if state["approval_requests"]
            else None
        )
        if current_request is None or current_request.request_id != decision.request_id:
            raise AgentOSBridgeError(
                "approval_request_stale",
                "approval decision does not target the currently pending request",
            )
        if any(
            item["request_id"] == decision.request_id
            for item in state["approval_decisions"]
        ):
            raise AgentOSBridgeError(
                "approval_request_already_decided",
                "current approval request already has a durable decision",
            )
        assert_approval_decision_matches_request(requirement, request, decision)
        milestone = self._milestone_for_operation(
            compatibility,
            requirement.operation,
        )
        status = RunStatus.model_validate(state["status"])
        if milestone == "landing":
            if status.state != "paused" or state["outcome"] is not None:
                raise AgentOSBridgeError(
                    "approval_state_invalid",
                    "landing approval requires a current paused runtime",
                )
        elif (
            status.state != "awaiting_approval"
            or requirement.requirement_id not in status.pending_approval_ids
        ):
            raise AgentOSBridgeError(
                "approval_state_invalid",
                "plan-freeze approval requires the current pending requirement",
            )

        if decision.verdict == "approved" and milestone == "plan_freeze":
            self._refresh_and_assert_snapshot(
                state,
                plan,
                session,
                profile,
                state["binding"],
                compatibility,
            )

        state["approval_decisions"].append(decision.model_dump(mode="json"))
        self._emit(
            state,
            profile,
            event_kind="approval_decision",
            at=decision.decided_at,
            approval_decision_ref=_approval_decision_ref(decision),
        )
        effect = {
            "decision_id": decision.decision_id,
            "milestone": milestone,
            "verdict": decision.verdict,
            "phase": "decision_recorded",
        }
        state["approval_effects"].append(effect)
        self._save_state(session.session_id, state)
        return self._continue_approval_effect(
            state,
            plan,
            session,
            profile,
            compatibility,
            decision,
            effect,
        )

    def _continue_approval_effect(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        compatibility: dict[str, Any],
        decision: ApprovalDecision,
        effect: dict[str, Any],
    ) -> RunStatus:
        milestone = str(effect.get("milestone") or "")
        phase = str(effect.get("phase") or "")
        if (
            effect.get("decision_id") != decision.decision_id
            or effect.get("verdict") != decision.verdict
            or milestone not in {"plan_freeze", "landing"}
        ):
            raise AgentOSBridgeError(
                "approval_effect_journal_invalid",
                "durable approval effect differs from its retained decision",
            )
        if phase == "decision_recorded":
            self._write_governed_approval(
                state,
                milestone=milestone,
                status=(
                    "approved"
                    if decision.verdict == "approved"
                    else "rejected"
                ),
                notes=decision.reason,
            )
            effect["phase"] = "governed_approval_written"
            self._save_state(session.session_id, state)
            phase = "governed_approval_written"
        if decision.verdict == "rejected":
            if phase != "governed_approval_written":
                raise AgentOSBridgeError(
                    "approval_effect_journal_invalid",
                    "rejected approval has an invalid durable effect phase",
                )
            if RunStatus.model_validate(state["status"]).state != "cancelled":
                self._transition(
                    state,
                    profile,
                    state_after="cancelled",
                    trigger="approval_rejected",
                    at=decision.decided_at,
                )
                self._record_outcome(
                    state,
                    plan,
                    session,
                    profile,
                    execution_status="cancelled",
                    failure_codes=(),
                    governed_summary=None,
                )
            effect["phase"] = "completed"
            self._save_state(session.session_id, state)
            return RunStatus.model_validate(state["status"])
        if decision.verdict == "expired":
            if phase != "governed_approval_written":
                raise AgentOSBridgeError(
                    "approval_effect_journal_invalid",
                    "expired approval has an invalid durable effect phase",
                )
            if RunStatus.model_validate(state["status"]).state == "awaiting_approval":
                self._transition(
                    state,
                    profile,
                    state_after="paused",
                    trigger="approval_expired",
                    at=decision.decided_at,
                )
            effect["phase"] = "completed"
            self._save_state(session.session_id, state)
            return RunStatus.model_validate(state["status"])
        if milestone == "landing":
            if phase != "governed_approval_written":
                raise AgentOSBridgeError(
                    "approval_effect_journal_invalid",
                    "landing approval has an invalid durable effect phase",
                )
            effect["phase"] = "completed"
            self._save_state(session.session_id, state)
            return RunStatus.model_validate(state["status"])
        if phase == "governed_approval_written":
            self._transition(
                state,
                profile,
                state_after="running",
                trigger="approval_granted",
                at=decision.decided_at,
            )
            effect["phase"] = "backend_pending"
            self._save_state(session.session_id, state)
            phase = "backend_pending"
        if phase != "backend_pending":
            raise AgentOSBridgeError(
                "approval_effect_journal_invalid",
                "plan-freeze approval has an invalid durable effect phase",
            )
        current = RunStatus.model_validate(state["status"])
        if current.state == "paused":
            self._transition(
                state,
                profile,
                state_after="running",
                trigger="resume",
                at=self.clock(),
            )
            self._save_state(session.session_id, state)
        elif current.state != "running":
            raise AgentOSBridgeError(
                "approval_effect_journal_invalid",
                "pending plan-freeze effect is outside a replayable state",
            )
        try:
            summary = self.backend.resume_run(
                self._governed_run_id(state),
                until="milestone",
                log_root=self._governed_root(),
                advisory_provider=self.advisory_provider,
                proposal_provider=self.proposal_provider,
            )
        except Exception:
            state["last_governed_interruption"] = {
                "code": "governed_preview_unavailable",
                "observed_at": self.clock().isoformat(),
            }
            self._transition(
                state,
                profile,
                state_after="paused",
                trigger="pause",
                at=self.clock(),
            )
            self._save_state(session.session_id, state)
            return RunStatus.model_validate(state["status"])
        state["last_governed_interruption"] = None
        if (
            summary.get("status") == "paused"
            and summary.get("current_milestone") == "landing"
        ):
            landing_requirement = self._approval_requirement(
                plan,
                compatibility,
                "landing",
            )
            request = self._build_approval_request(
                state,
                plan,
                session,
                landing_requirement,
                requested_at=self._summary_time(summary),
            )
            self._transition(
                state,
                profile,
                state_after="paused",
                trigger="pause",
                at=request.requested_at,
            )
            self._store_approval_request(state, profile, request)
            effect["phase"] = "completed"
            self._save_state(session.session_id, state)
            return RunStatus.model_validate(state["status"])
        failure_code = str(summary.get("failure_class") or "governed_preview_failed")
        self._transition(
            state,
            profile,
            state_after="failed",
            trigger="runtime_failed",
            at=self._summary_time(summary),
            failure_code=failure_code,
        )
        self._record_outcome(
            state,
            plan,
            session,
            profile,
            execution_status="failed",
            failure_codes=(failure_code,),
            governed_summary=summary,
        )
        effect["phase"] = "completed"
        self._save_state(session.session_id, state)
        return RunStatus.model_validate(state["status"])

    def _refresh_and_assert_snapshot(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        binding: dict[str, Any],
        compatibility: dict[str, Any],
    ) -> RuntimeSnapshotObservation:
        observation = self._observe_snapshot(
            plan,
            session,
            profile,
            binding,
            observed_not_before=RunStatus.model_validate(
                state["status"]
            ).updated_at,
        )
        self._assert_snapshot_observation(plan, session, observation)
        self._assert_runtime_inputs(plan, binding, compatibility)
        state["last_observation"] = observation.model_dump(mode="json")
        return observation

    @staticmethod
    def _assert_snapshot_observation(
        plan: RunPlan,
        session: SessionHandle,
        observation: RuntimeSnapshotObservation,
    ) -> None:
        try:
            assert_runtime_snapshot_observation(
                plan,
                session,
                observation,
            )
        except ControlPlaneContractError as exc:
            raise AgentOSBridgeError(
                "runtime_snapshot_drift",
                "refreshed runtime snapshot differs from the exact plan; "
                f"stale or spoofed source artifact or ABI: {exc}",
            ) from exc

    def _renew_approvals(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        compatibility: dict[str, Any],
        requested_at: datetime,
    ) -> tuple[ApprovalRequest, ...]:
        status = RunStatus.model_validate(state["status"])
        if status.state not in {"awaiting_approval", "paused"}:
            raise AgentOSBridgeError(
                "approval_renewal_state_invalid",
                "approval renewal requires awaiting_approval or paused",
            )
        current = state["approval_requests"][-1] if state["approval_requests"] else None
        if current is None:
            raise AgentOSBridgeError(
                "approval_request_missing",
                "runtime has no approval request to renew",
            )
        if any(
            item["request_id"] == current["request_id"]
            for item in state["approval_decisions"]
        ):
            raise AgentOSBridgeError(
                "approval_request_already_decided",
                "a decided approval request cannot be renewed",
            )
        requirement_id = str(current["requirement_id"])
        requirement = next(
            (
                item
                for item in plan.approval_requirements
                if item.requirement_id == requirement_id
            ),
            None,
        )
        if requirement is None or not requirement.renewable:
            raise AgentOSBridgeError(
                "approval_not_renewable",
                "current approval requirement is not renewable",
            )
        milestone = self._milestone_for_operation(
            compatibility,
            requirement.operation,
        )
        if milestone not in {"plan_freeze", "landing"}:
            raise AgentOSBridgeError(
                "approval_mapping_mismatch",
                "current approval has no governed milestone",
            )
        request = self._build_approval_request(
            state,
            plan,
            session,
            requirement,
            requested_at=requested_at,
        )
        self._store_approval_request(state, profile, request)
        return tuple(
            ApprovalRequest.model_validate(item)
            for item in state["approval_requests"]
            if item["requirement_id"] == requirement_id
        )[-1:]

    def _closeout(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        outcome: RunOutcome,
        bundle: CloseoutBundleRef,
    ) -> RunStatus:
        current = (
            RunOutcome.model_validate(state["outcome"])
            if state["outcome"] is not None
            else None
        )
        status = RunStatus.model_validate(state["status"])
        if current != outcome:
            raise AgentOSBridgeError(
                "runtime_outcome_mismatch",
                "closeout outcome differs from durable runtime outcome",
            )
        if status.state == "closed":
            if status.closeout_ref != bundle:
                raise AgentOSBridgeError(
                    "closeout_conflict",
                    "runtime session already closed with another bundle",
                )
            return status
        assert_closeout_bundle_scope(plan, session, outcome, bundle)
        self._transition(
            state,
            profile,
            state_after="closed",
            trigger="closeout",
            at=self.clock(),
            closeout_ref=bundle,
        )
        return RunStatus.model_validate(state["status"])

    def _record_outcome(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        profile: RuntimeProfile,
        *,
        execution_status: Literal["succeeded", "failed", "cancelled"],
        failure_codes: tuple[str, ...],
        governed_summary: dict[str, Any] | None,
    ) -> RunOutcome:
        if state["outcome"] is not None:
            return RunOutcome.model_validate(state["outcome"])
        runtime_result_path = self._runtime_result_path(session.session_id)
        result_payload = {
            "schema_version": "abyss_stack_agent_os_runtime_result_v1",
            "session_id": session.session_id,
            "plan_digest": plan.plan_digest,
            "execution_lane": state.get("execution_lane"),
            "governed_run_id": state.get("governed_run_id"),
            "execution_status": execution_status,
            "runtime_summary": governed_summary,
            "governed_summary": (
                governed_summary
                if state.get("execution_lane") == "governed_repository_change"
                else None
            ),
        }
        _atomic_write_json(runtime_result_path, result_payload)
        runtime_result_ref = ProvenanceRef(
            owner_repo="abyss-stack",
            artifact_ref=f"local:{runtime_result_path}",
            source_ref=ADAPTER_VERSION,
            artifact_digest=sha256_file(runtime_result_path),
            schema_ref=(
                "mechanics/governed-execution/parts/agent-os-adapter/"
                "CONTRACT.md#evidence-stop-line"
            ),
            schema_version="abyss_stack_agent_os_runtime_result_v1",
        )
        evidence_refs = self._scenario_input_evidence_refs(plan)
        if governed_summary is not None:
            evidence_ref = self._runtime_evidence_bundle(
                state,
                plan,
                session,
                governed_summary,
            )
            evidence_refs = (*evidence_refs, evidence_ref)
            self._emit(
                state,
                profile,
                event_kind="evidence_emitted",
                at=self.clock(),
                evidence_refs=evidence_refs,
            )
        terminal_state = {
            "succeeded": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
        }[execution_status]
        outcome = RunOutcome(
            outcome_id=f"abyss-stack-outcome:{_session_token(session.session_id)}",
            session_id=session.session_id,
            correlation_id=session.correlation_id,
            plan_digest=plan.plan_digest,
            execution_status=execution_status,
            terminal_state=terminal_state,
            completed_at=self._event_time(state, self.clock()),
            runtime_result_ref=runtime_result_ref,
            evidence_bundle_refs=evidence_refs,
            failure_codes=failure_codes,
        )
        state["outcome"] = outcome.model_dump(mode="json")
        self._emit(
            state,
            profile,
            event_kind="outcome",
            at=outcome.completed_at,
            outcome_ref=_outcome_ref(outcome),
        )
        return outcome

    @staticmethod
    def _scenario_input_evidence_refs(
        plan: RunPlan,
    ) -> tuple[EvidenceBundleRef, ...]:
        inputs = {
            item.artifact_kind: item.artifact_ref
            for item in plan.scenario_binding.input_artifact_bindings
        }
        refs: list[EvidenceBundleRef] = []
        for requirement in plan.evidence_requirements:
            if requirement.artifact_binding != "scenario_input":
                continue
            provenance = inputs.get(requirement.artifact_kind)
            if (
                provenance is None
                or provenance.owner_repo != requirement.producer_owner
            ):
                raise AgentOSBridgeError(
                    "runtime_input_evidence_contract_mismatch",
                    (
                        "scenario input evidence does not retain the declared "
                        f"producer for {requirement.requirement_id}"
                    ),
                )
            refs.append(
                EvidenceBundleRef(
                    ref_id=(
                        "scenario-input-evidence:"
                        f"{requirement.requirement_id}"
                    ),
                    provenance=provenance,
                    satisfies_requirement_ids=(requirement.requirement_id,),
                )
            )
        return tuple(refs)

    def _runtime_evidence_bundle(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        governed_summary: dict[str, Any],
    ) -> EvidenceBundleRef:
        artifacts = list(state["runtime_artifact_refs"])
        governed_run_id = state.get("governed_run_id")
        if isinstance(governed_run_id, str) and governed_run_id:
            governed_run_dir = self._governed_root() / governed_run_id
            if governed_run_dir.exists():
                for path in sorted(governed_run_dir.rglob("*")):
                    if path.is_file():
                        artifacts.append(
                            {
                                "artifact_kind": "governed_run_artifact",
                                "path": str(path.relative_to(governed_run_dir)),
                                "digest": sha256_file(path),
                            }
                        )
        requirement_ids = self._satisfied_runtime_requirement_ids(
            state,
            plan,
            governed_summary,
            artifacts,
        )
        payload = {
            "schema_version": "abyss_stack_agent_os_evidence_bundle_v1",
            "session_id": session.session_id,
            "plan_digest": plan.plan_digest,
            "execution_lane": state.get("execution_lane"),
            "governed_run_id": governed_run_id,
            "satisfies_requirement_ids": requirement_ids,
            "runtime_summary": governed_summary,
            "artifacts": artifacts,
            "boundaries": {
                "runtime_evidence_only": True,
                "eval_verdict": False,
                "memory_receipt": False,
                "checkpoint_acceptance": False,
                "closeout_grant": False,
            },
        }
        path = self._runtime_evidence_path(session.session_id)
        _atomic_write_json(path, payload)
        return EvidenceBundleRef(
            ref_id=f"abyss-stack-evidence:{_session_token(session.session_id)}",
            provenance=ProvenanceRef(
                owner_repo="abyss-stack",
                artifact_ref=f"local:{path}",
                source_ref=ADAPTER_VERSION,
                artifact_digest=sha256_file(path),
                schema_ref=(
                    "mechanics/governed-execution/parts/agent-os-adapter/"
                    "CONTRACT.md#evidence-stop-line"
                ),
                schema_version="abyss_stack_agent_os_evidence_bundle_v1",
            ),
            satisfies_requirement_ids=tuple(requirement_ids),
        )

    @staticmethod
    def _satisfied_runtime_requirement_ids(
        state: dict[str, Any],
        plan: RunPlan,
        governed_summary: dict[str, Any],
        artifacts: list[dict[str, Any]],
    ) -> tuple[str, ...]:
        requirements = [
            item
            for item in plan.evidence_requirements
            if (
                item.producer_owner == "abyss-stack"
                and item.artifact_binding == "step_output"
            )
        ]
        if state.get("execution_lane") != "governed_repository_change":
            produced_kinds = {
                str(item["artifact_kind"])
                for item in artifacts
                if isinstance(item.get("artifact_kind"), str)
            }
            return tuple(
                item.requirement_id
                for item in requirements
                if item.artifact_kind in produced_kinds
            )

        if (
            governed_summary.get("status") != "pass"
            or governed_summary.get("phase") != "completed"
        ):
            return ()
        governed_paths = {
            str(item["path"])
            for item in artifacts
            if (
                item.get("artifact_kind") == "governed_run_artifact"
                and isinstance(item.get("path"), str)
            )
        }
        exact_proofs = {
            "approval_record": {"approval.status.json"},
            "source_map": {
                "policy.snapshot.json",
                "preflight.summary.json",
            },
            "scoped_change_set": {
                "landing.diff",
                "worktree.manifest.json",
            },
            "shareable_summary": {
                "report.md",
                "result.summary.json",
            },
        }

        def produced(artifact_kind: str) -> bool:
            expected = exact_proofs.get(artifact_kind)
            if expected is not None:
                return expected.issubset(governed_paths)
            if artifact_kind == "verification_pack":
                command_seen = any(
                    path.startswith("artifacts/landing-acceptance-")
                    and path.endswith(".command.json")
                    for path in governed_paths
                )
                output_seen = any(
                    path.startswith("artifacts/landing-acceptance-")
                    and path.endswith(".stdout.txt")
                    for path in governed_paths
                )
                return command_seen and output_seen
            return False

        return tuple(
            item.requirement_id
            for item in requirements
            if produced(item.artifact_kind)
        )

    def _write_lane_artifact(
        self,
        state: dict[str, Any],
        session: SessionHandle,
        payload: dict[str, Any],
    ) -> None:
        artifact_kind = payload.get("artifact_kind")
        if not isinstance(artifact_kind, str) or not artifact_kind:
            raise AgentOSBridgeError(
                "runtime_artifact_invalid",
                "lane artifact must declare artifact_kind",
            )
        path = (
            self.state_root
            / "lane-artifacts"
            / _session_token(session.session_id)
            / f"{artifact_kind}.json"
        )
        _atomic_write_json(path, payload)
        retained = [
            item
            for item in state["runtime_artifact_refs"]
            if item.get("artifact_kind") != artifact_kind
        ]
        retained.append(
            {
                "artifact_kind": artifact_kind,
                "path": str(path),
                "digest": sha256_file(path),
            }
        )
        state["runtime_artifact_refs"] = sorted(
            retained,
            key=lambda item: str(item["artifact_kind"]),
        )

    def _retain_scenario_input_artifacts(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
    ) -> None:
        retained = list(state["runtime_artifact_refs"])
        for item in plan.scenario_binding.input_artifact_bindings:
            key = (item.artifact_ref.owner_repo, item.artifact_ref.artifact_ref)
            payload = self._captured_source_bytes(key)
            path = self._captured_source_path(key)
            artifact_kind = f"scenario_input:{item.artifact_kind}"
            retained = [
                existing
                for existing in retained
                if existing.get("artifact_kind") != artifact_kind
            ]
            retained.append(
                {
                    "artifact_kind": artifact_kind,
                    "owner_repo": item.artifact_ref.owner_repo,
                    "artifact_ref": item.artifact_ref.artifact_ref,
                    "path": str(path),
                    "digest": sha256_bytes(payload),
                    "production_claimed": False,
                    "observed_by_runtime": True,
                    "session_id": session.session_id,
                }
            )
        state["runtime_artifact_refs"] = sorted(
            retained,
            key=lambda item: str(item["artifact_kind"]),
        )

    def _build_approval_request(
        self,
        state: dict[str, Any],
        plan: RunPlan,
        session: SessionHandle,
        requirement: ApprovalRequirement,
        *,
        requested_at: datetime,
    ) -> ApprovalRequest:
        generation = 1 + sum(
            1
            for item in state["approval_requests"]
            if item["requirement_id"] == requirement.requirement_id
        )
        requested_at = self._event_time(state, requested_at)
        expires_at = (
            requested_at + timedelta(seconds=requirement.expires_after_seconds)
            if requirement.expires_after_seconds is not None
            else None
        )
        return ApprovalRequest(
            request_id=(
                f"abyss-stack-approval:{session.session_id}:"
                f"{requirement.requirement_id}:{generation}"
            ),
            requirement_id=requirement.requirement_id,
            approval_authority=requirement.approval_owner,
            session_id=session.session_id,
            correlation_id=session.correlation_id,
            plan_digest=plan.plan_digest,
            snapshot_digest=plan.snapshot.snapshot_digest,
            requested_at=requested_at,
            expires_at=expires_at,
            request_provenance=requirement.approval_owner,
        )

    def _store_approval_request(
        self,
        state: dict[str, Any],
        profile: RuntimeProfile,
        request: ApprovalRequest,
    ) -> None:
        state["approval_requests"] = [
            item
            for item in state["approval_requests"]
            if item["requirement_id"] != request.requirement_id
        ]
        state["approval_requests"].append(request.model_dump(mode="json"))
        self._emit(
            state,
            profile,
            event_kind="approval_requested",
            at=request.requested_at,
            approval_request_ref=_approval_request_ref(request),
        )

    @staticmethod
    def _approval_requirement(
        plan: RunPlan,
        compatibility: dict[str, Any],
        milestone: Literal["plan_freeze", "landing"],
    ) -> ApprovalRequirement:
        operation = compatibility["approval_operations"][milestone]
        matches = [
            item for item in plan.approval_requirements if item.operation == operation
        ]
        if len(matches) != 1:
            raise AgentOSBridgeError(
                "approval_mapping_mismatch",
                f"runtime milestone {milestone} lacks one exact requirement",
            )
        return matches[0]

    @staticmethod
    def _milestone_for_operation(
        compatibility: dict[str, Any],
        operation: str,
    ) -> Literal["plan_freeze", "landing"]:
        matches = [
            milestone
            for milestone, expected in compatibility["approval_operations"].items()
            if expected == operation
        ]
        if matches == ["plan_freeze"]:
            return "plan_freeze"
        if matches == ["landing"]:
            return "landing"
        raise AgentOSBridgeError(
            "approval_mapping_mismatch",
            "approval operation has no exact governed milestone",
        )

    def _write_governed_approval(
        self,
        state: dict[str, Any],
        *,
        milestone: str,
        status: str,
        notes: str,
    ) -> None:
        run_dir = self._governed_root() / self._governed_run_id(state)
        approval = self.backend.load_approval(run_dir)
        approval = self.backend.advance_milestone(
            approval,
            milestone=milestone,
            status=status,
            notes=notes,
        )
        self.backend.write_json(
            self.backend.approval_artifact(run_dir),
            approval,
        )

    def _transition(
        self,
        state: dict[str, Any],
        profile: RuntimeProfile,
        *,
        state_after: str,
        trigger: str,
        at: datetime,
        pending_approval_ids: tuple[str, ...] = (),
        failure_code: str | None = None,
        recover_from_event_sequence: int | None = None,
        closeout_ref: CloseoutBundleRef | None = None,
    ) -> None:
        previous = RunStatus.model_validate(state["status"])
        event = self._emit(
            state,
            profile,
            event_kind="state_transition",
            at=at,
            state_before=previous.state,
            state_after=state_after,
            trigger=trigger,
        )
        state["status"] = RunStatus(
            session_id=previous.session_id,
            correlation_id=previous.correlation_id,
            state=state_after,
            revision=previous.revision + 1,
            last_event_sequence=event.sequence,
            pending_approval_ids=pending_approval_ids,
            failure_code=failure_code,
            recover_from_event_sequence=recover_from_event_sequence,
            closeout_ref=closeout_ref,
            updated_at=event.emitted_at,
            observed_by=profile.provenance,
        ).model_dump(mode="json")

    def _emit(
        self,
        state: dict[str, Any],
        profile: RuntimeProfile,
        *,
        event_kind: str,
        at: datetime,
        state_before: str | None = None,
        state_after: str | None = None,
        trigger: str | None = None,
        command_id: str | None = None,
        idempotency_key: str | None = None,
        approval_request_ref: ContentRef | None = None,
        approval_decision_ref: ContentRef | None = None,
        evidence_refs: tuple[EvidenceBundleRef, ...] = (),
        outcome_ref: ContentRef | None = None,
    ) -> ExecutionEvent:
        session = SessionHandle.model_validate(state["session"])
        events = [ExecutionEvent.model_validate(item) for item in state["events"]]
        emitted_at = self._event_time(state, at)
        sequence = len(events)
        event = ExecutionEvent(
            event_id=(
                f"abyss-stack-event:{_session_token(session.session_id)}:{sequence}"
            ),
            event_stream_id=session.event_stream_id,
            session_id=session.session_id,
            correlation_id=session.correlation_id,
            sequence=sequence,
            previous_event_digest=(events[-1].event_digest if events else None),
            event_digest=ZERO_DIGEST,
            event_kind=event_kind,
            emitted_at=emitted_at,
            emitted_by=profile.provenance,
            state_before=state_before,
            state_after=state_after,
            trigger=trigger,
            command_id=command_id,
            idempotency_key=idempotency_key,
            approval_request_ref=approval_request_ref,
            approval_decision_ref=approval_decision_ref,
            evidence_refs=evidence_refs,
            outcome_ref=outcome_ref,
        )
        event = event.model_copy(update={"event_digest": execution_event_digest(event)})
        state["events"].append(event.model_dump(mode="json"))
        previous = RunStatus.model_validate(state["status"])
        state["status"] = previous.model_copy(
            update={
                "last_event_sequence": event.sequence,
                "updated_at": event.emitted_at,
            }
        ).model_dump(mode="json")
        return event

    @staticmethod
    def _event_time(
        state: dict[str, Any],
        value: datetime,
    ) -> datetime:
        value = _aware(value, "runtime event time")
        status = RunStatus.model_validate(state["status"])
        floor = _aware(status.updated_at, "runtime status time")
        if state["events"]:
            floor = max(
                floor,
                _aware(
                    ExecutionEvent.model_validate(state["events"][-1]).emitted_at,
                    "previous runtime event time",
                ),
            )
        return max(value, floor)

    def _summary_time(self, summary: Mapping[str, Any]) -> datetime:
        value = summary.get("updated_at")
        if isinstance(value, str):
            try:
                return _aware(
                    datetime.fromisoformat(value.replace("Z", "+00:00")),
                    "governed summary time",
                )
            except ValueError:
                pass
        fallback = self.clock()
        return _aware(fallback, "runtime clock")

    def _policy_path(
        self,
        plan: RunPlan,
        binding: dict[str, Any],
    ) -> Path:
        key = self._policy_coordinate()
        refs = {
            (item.owner_repo, item.artifact_ref): item
            for item in plan.runtime_profile.constraint_refs
        }
        source_locations = _location_map(
            binding["source_locations"],
            id_field="artifact_ref",
            label="source",
        )
        if key not in refs or key not in source_locations:
            raise AgentOSBridgeError(
                "runtime_policy_unbound",
                "governed policy is absent from the exact plan snapshot",
            )
        return Path(source_locations[key])

    def _policy_coordinate(self) -> tuple[str, str]:
        required = self.profile_descriptor["required_constraint_artifacts"]
        if len(required) != 1:
            raise AgentOSBridgeError(
                "runtime_profile_invalid",
                "v1 requires one governed policy artifact",
            )
        return (
            str(required[0]["owner_repo"]),
            str(required[0]["artifact_ref"]),
        )

    def _bound_source_bytes(
        self,
        binding: dict[str, Any],
        key: tuple[str, str],
        *,
        source_locations: dict[tuple[str, str], str] | None = None,
    ) -> bytes:
        if self._admitted_source_bytes:
            return self._captured_source_bytes(key)
        locations = source_locations or _location_map(
            binding["source_locations"],
            id_field="artifact_ref",
            label="source",
        )
        try:
            path = Path(locations[key])
        except KeyError as exc:
            raise AgentOSBridgeError(
                "runtime_source_map_mismatch",
                "bound source coordinate is absent from the runtime map",
            ) from exc
        return read_artifact_bytes(path)

    def _captured_source_bytes(self, key: tuple[str, str]) -> bytes:
        try:
            return self._admitted_source_bytes[key]
        except KeyError as exc:
            raise AgentOSBridgeError(
                "materialized_snapshot_missing",
                "effectful runtime input lacks captured snapshot bytes",
            ) from exc

    def _captured_source_path(self, key: tuple[str, str]) -> Path:
        try:
            return self._admitted_source_paths[key]
        except KeyError as exc:
            raise AgentOSBridgeError(
                "materialized_snapshot_missing",
                "runtime evidence input lacks a private materialization",
            ) from exc

    def _governed_root(self) -> Path:
        return self.state_root / "governed-runs"

    @staticmethod
    def _governed_run_id(state: dict[str, Any]) -> str:
        run_id = state.get("governed_run_id")
        if not isinstance(run_id, str) or not run_id:
            raise AgentOSBridgeError(
                "governed_run_missing",
                "runtime session has no governed run binding",
            )
        return run_id

    def _rejected_receipt(
        self,
        state: dict[str, Any],
        command: RuntimeCommand,
        profile: RuntimeProfile,
        code: str,
    ) -> CommandReceipt:
        return CommandReceipt(
            command_id=command.command_id,
            idempotency_key=command.idempotency_key,
            command_digest=command_digest(command),
            session_id=command.session_id,
            status="rejected",
            resulting_revision=RunStatus.model_validate(state["status"]).revision,
            rejection_code=code,
            produced_by=profile.provenance,
        )

    def _remember_rejection(
        self,
        state: dict[str, Any],
        command: RuntimeCommand,
        profile: RuntimeProfile,
        code: str,
    ) -> CommandReceipt:
        receipt = self._rejected_receipt(state, command, profile, code)
        state["rejected_commands"].append(
            {
                "command": command.model_dump(mode="json"),
                "receipt": receipt.model_dump(mode="json"),
            }
        )
        return receipt

    def _runtime_result_path(self, session_id: str) -> Path:
        return (
            self.state_root / "runtime-results" / f"{_session_token(session_id)}.json"
        )

    def _runtime_evidence_path(self, session_id: str) -> Path:
        return self.state_root / "evidence" / f"{_session_token(session_id)}.json"

    def _state_path(self, session_id: str) -> Path:
        return self.state_root / "sessions" / f"{_session_token(session_id)}.json"

    def _load_state(self, session_id: str) -> dict[str, Any] | None:
        path = self._state_path(session_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AgentOSBridgeError(
                "durable_state_invalid",
                "cannot read durable runtime session state",
            ) from exc
        if not isinstance(payload, dict):
            raise AgentOSBridgeError(
                "durable_state_invalid",
                "durable runtime state must be an object",
            )
        return payload

    def _save_state(self, session_id: str, state: dict[str, Any]) -> None:
        _atomic_write_json(self._state_path(session_id), state)

    @contextmanager
    def _session_lock(self, session_id: str) -> Iterator[None]:
        lock_dir = self.state_root / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / f"{_session_token(session_id)}.lock"
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _location_map(
    raw: Any,
    *,
    id_field: str,
    label: str,
) -> dict[tuple[str, str], str]:
    if not isinstance(raw, list):
        raise AgentOSBridgeError(
            f"runtime_{label.lower()}_map_invalid",
            f"runtime {label} locations must be an array",
        )
    result: dict[tuple[str, str], str] = {}
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            "owner_repo",
            id_field,
            "local_path",
        }:
            raise AgentOSBridgeError(
                f"runtime_{label.lower()}_map_invalid",
                f"runtime {label} location shape is invalid",
            )
        owner = item["owner_repo"]
        identity = item[id_field]
        local_path = item["local_path"]
        if (
            not isinstance(owner, str)
            or not owner
            or not isinstance(identity, str)
            or not identity
            or not isinstance(local_path, str)
            or not Path(local_path).is_absolute()
        ):
            raise AgentOSBridgeError(
                f"runtime_{label.lower()}_map_invalid",
                f"runtime {label} coordinate is invalid",
            )
        key = (owner, identity)
        if key in result:
            raise AgentOSBridgeError(
                f"runtime_{label.lower()}_map_invalid",
                f"runtime {label} locations contain a duplicate key",
            )
        result[key] = local_path
    return result


def _find_command(
    entries: Iterable[dict[str, Any]],
    idempotency_key: str,
) -> dict[str, Any] | None:
    for entry in entries:
        command = entry.get("command")
        if (
            isinstance(command, dict)
            and command.get("idempotency_key") == idempotency_key
        ):
            return entry
    return None


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AgentOSBridgeError(
            "naive_timestamp",
            f"{field_name} must be timezone-aware",
        )
    return value.astimezone(timezone.utc)


def _aware_from_json(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise AgentOSBridgeError(
            "invalid_timestamp",
            f"{field_name} must be an ISO timestamp",
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AgentOSBridgeError(
            "invalid_timestamp",
            f"{field_name} must be an ISO timestamp",
        ) from exc
    return _aware(parsed, field_name)


def _event_ref(event: ExecutionEvent) -> ContentRef:
    return ContentRef(
        object_id=event.event_id,
        owner_repo=event.emitted_by.owner_repo,
        schema_version=event.schema_version,
        digest=event.event_digest,
    )


def _approval_request_ref(request: ApprovalRequest) -> ContentRef:
    return ContentRef(
        object_id=request.request_id,
        owner_repo=request.request_provenance.owner_repo,
        schema_version=request.schema_version,
        digest=canonical_digest(request),
    )


def _approval_decision_ref(decision: ApprovalDecision) -> ContentRef:
    return ContentRef(
        object_id=decision.decision_id,
        owner_repo=decision.approval_authority.owner_repo,
        schema_version=decision.schema_version,
        digest=canonical_digest(decision),
    )


def _outcome_ref(outcome: RunOutcome) -> ContentRef:
    return ContentRef(
        object_id=outcome.outcome_id,
        owner_repo=outcome.runtime_result_ref.owner_repo,
        schema_version=outcome.schema_version,
        digest=canonical_digest(outcome),
    )


def _session_token(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="abyss-stack Agent OS subprocess runtime bridge"
    )
    parser.add_argument(
        "operation",
        choices=(
            "observe_snapshot",
            "dispatch",
            "approval_requests",
            "approval_decisions",
            "command_receipts",
            "renew_approvals",
            "apply_approval",
            "status",
            "events",
            "outcome",
            "closeout",
        ),
    )
    parser.add_argument("--state-root", required=True)
    return parser


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise AgentOSBridgeError(
            "payload_too_large",
            "Agent OS bridge payload exceeds the v1 limit",
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentOSBridgeError(
            "payload_invalid_json",
            "Agent OS bridge payload is not valid JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise AgentOSBridgeError(
            "payload_invalid",
            "Agent OS bridge payload must be an object",
        )
    return payload


def _write_response(payload: Mapping[str, Any]) -> None:
    sys.stdout.write(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        bridge = AgentOSRuntimeBridge(args.state_root)
        result = bridge.invoke(args.operation, _read_payload())
        _write_response(
            {
                "schema_version": RESPONSE_SCHEMA_VERSION,
                "ok": True,
                "result": result,
            }
        )
    except AgentOSBridgeError as exc:
        _write_response(
            {
                "schema_version": RESPONSE_SCHEMA_VERSION,
                "ok": False,
                "error_code": exc.code,
                "message": str(exc),
            }
        )
    except Exception:
        _write_response(
            {
                "schema_version": RESPONSE_SCHEMA_VERSION,
                "ok": False,
                "error_code": "internal_error",
                "message": "runtime bridge failed closed",
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
