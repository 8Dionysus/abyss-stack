from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from aoa_sdk.contracts.control_plane import (
    ApprovalDecision,
    PlanSnapshot,
    ResumeCommand,
    RunPlan,
    RuntimeProfile,
    StartCommand,
    canonical_digest,
)
from aoa_sdk.control_plane.runner import AoARunner
from aoa_sdk.runtime_adapters import (
    AbyssStackRuntimeAdapter,
    AbyssStackRuntimeBinding,
    AbyssStackSubprocessTransport,
    RuntimeABILocation,
    RuntimeArtifactLocation,
    load_abyss_stack_runtime_profile,
)


pytestmark = pytest.mark.skipif(
    "AOA_SDK_SOURCE_ROOT" not in os.environ,
    reason="paired source proof requires AOA_SDK_SOURCE_ROOT",
)

NOW = datetime(2099, 7, 26, 19, 30, tzinfo=timezone.utc)
ZERO_DIGEST = "sha256:" + "0" * 64
PART_ROOT = Path(__file__).resolve().parents[1]
STACK_ROOT = Path(__file__).resolve().parents[5]
PROFILE_PATH = PART_ROOT / "runtime-profile.v1.json"
BRIDGE_PATH = PART_ROOT / "aoa_agent_os_runtime.py"
BRIDGE_EXECUTABLE = STACK_ROOT / "scripts" / "aoa-agent-os-runtime"
SUPPORT_PATH = (
    PART_ROOT.parent
    / "governed-runner"
    / "tests"
    / "governed_runner_test_support.py"
)


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load test dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BRIDGE = _load_module("abyss_stack_agent_os_runtime_under_test", BRIDGE_PATH)
SUPPORT = _load_module("abyss_stack_governed_runner_support", SUPPORT_PATH)


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _runtime_profile(policy_path: Path) -> RuntimeProfile:
    return load_abyss_stack_runtime_profile(
        PROFILE_PATH,
        constraint_locations=(
            RuntimeArtifactLocation(
                owner_repo="abyss-stack",
                artifact_ref=(
                    "config-templates/Configs/agent-api/"
                    "governed-execution-policy.yaml"
                ),
                local_path=str(policy_path),
            ),
        ),
    )


def _rewrite_provenance_digests(
    value: Any,
    digests: dict[tuple[str, str], str],
) -> Any:
    if isinstance(value, list):
        return [
            _rewrite_provenance_digests(item, digests)
            for item in value
        ]
    if not isinstance(value, dict):
        return value
    rewritten = {
        key: _rewrite_provenance_digests(item, digests)
        for key, item in value.items()
    }
    owner = rewritten.get("owner_repo")
    artifact = rewritten.get("artifact_ref")
    if isinstance(owner, str) and isinstance(artifact, str):
        digest = digests.get((owner, artifact))
        if digest is not None and "artifact_digest" in rewritten:
            rewritten["artifact_digest"] = digest
    return rewritten


def _sdk_source_root() -> Path:
    root = Path(os.environ["AOA_SDK_SOURCE_ROOT"]).resolve()
    if not (root / "src" / "aoa_sdk").is_dir():
        raise AssertionError("AOA_SDK_SOURCE_ROOT is not an aoa-sdk checkout")
    return root


def _build_plan_and_binding(
    root: Path,
    *,
    request_path: Path,
    policy_path: Path,
) -> tuple[RunPlan, AbyssStackRuntimeBinding, dict[tuple[str, str], Path]]:
    sdk_root = _sdk_source_root()
    example_path = (
        sdk_root
        / "mechanics"
        / "boundary-bridge"
        / "parts"
        / "plan-compilation-control-plane"
        / "examples"
        / "bounded-preview-pruned.run-plan.json"
    )
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    profile = _runtime_profile(policy_path)
    profile_ref = profile.provenance.model_dump(mode="json")
    constraint_ref = profile.constraint_refs[0].model_dump(mode="json")
    payload["runtime_profile"] = profile.model_dump(mode="json")
    payload["approval_requirements"] = [
        {
            "requirement_id": "approval:abyss-stack:plan-freeze",
            "approval_owner": profile_ref,
            "operation": "abyss-stack:governed-execution:plan-freeze",
            "risk_class": "repo_mutation",
            "applies_to_step_ids": ["mutate"],
            "required_evidence_refs": [],
            "expires_after_seconds": None,
            "renewable": False,
        },
        {
            "requirement_id": "approval:abyss-stack:landing",
            "approval_owner": profile_ref,
            "operation": "abyss-stack:governed-execution:landing",
            "risk_class": "repo_mutation",
            "applies_to_step_ids": ["mutate"],
            "required_evidence_refs": [],
            "expires_after_seconds": None,
            "renewable": False,
        },
    ]
    for step in payload["steps"]:
        step["approval_requirement_ids"] = (
            [
                "approval:abyss-stack:plan-freeze",
                "approval:abyss-stack:landing",
            ]
            if step["step_id"] == "mutate"
            else []
        )

    original_profile_key = ("abyss-stack", "runtime/agent-os/profile.json")
    source_refs = [
        profile_ref
        if (item["owner_repo"], item["artifact_ref"])
        == original_profile_key
        else item
        for item in payload["snapshot"]["source_refs"]
    ]
    source_refs.append(constraint_ref)
    payload["snapshot"]["source_refs"] = source_refs

    paths: dict[tuple[str, str], Path] = {}
    for index, item in enumerate(source_refs):
        key = (item["owner_repo"], item["artifact_ref"])
        if key == (
            "fixture-requester",
            "requests/bounded_change_safe.json",
        ):
            path = request_path
        elif key == (
            profile.provenance.owner_repo,
            profile.provenance.artifact_ref,
        ):
            path = PROFILE_PATH
        elif key == (
            profile.constraint_refs[0].owner_repo,
            profile.constraint_refs[0].artifact_ref,
        ):
            path = policy_path
        else:
            path = root / "source-material" / f"source-{index}.json"
            _write_json(
                path,
                {
                    "owner_repo": key[0],
                    "artifact_ref": key[1],
                    "fixture": "exact runtime snapshot material",
                },
            )
        if key in paths:
            raise AssertionError(f"duplicate source coordinate: {key}")
        paths[key] = path

    digests = {key: _sha256(path) for key, path in paths.items()}
    payload = _rewrite_provenance_digests(payload, digests)
    snapshot_payload = payload["snapshot"]
    snapshot_payload["snapshot_digest"] = ZERO_DIGEST
    snapshot = PlanSnapshot.model_validate(snapshot_payload)
    snapshot = snapshot.model_copy(
        update={
            "snapshot_digest": canonical_digest(
                snapshot,
                exclude={"snapshot_digest"},
            )
        }
    )
    payload["snapshot"] = snapshot.model_dump(mode="json")
    payload["plan_digest"] = ZERO_DIGEST
    plan = RunPlan.model_validate(payload)
    plan = plan.model_copy(
        update={
            "plan_digest": canonical_digest(
                plan,
                exclude={"plan_digest"},
            )
        }
    )

    request_ref = next(
        item
        for item in plan.scenario_binding.input_refs
        if item.artifact_ref == "requests/bounded_change_safe.json"
    )
    contour_path = (
        sdk_root
        / "src"
        / "aoa_sdk"
        / "control_plane"
        / "planning"
        / "data"
        / "playbook-plan-contours.v1.json"
    )
    binding = AbyssStackRuntimeBinding(
        binding_id="binding:abyss-stack:real-governed-run",
        plan_digest=plan.plan_digest,
        scenario_id=plan.scenario_binding.scenario.scenario_id,
        playbook_id="AOA-P-0011",
        request_ref=request_ref,
        request_path=str(request_path),
        source_locations=tuple(
            RuntimeArtifactLocation(
                owner_repo=item.owner_repo,
                artifact_ref=item.artifact_ref,
                local_path=str(paths[(item.owner_repo, item.artifact_ref)]),
            )
            for item in plan.snapshot.source_refs
        ),
        abi_locations=tuple(
            RuntimeABILocation(
                owner_repo=item.owner_repo,
                abi_id=item.abi_id,
                local_path=str(contour_path),
            )
            for item in plan.snapshot.abi_refs
        ),
        adapter_contract_ref=plan.runtime_profile.provenance,
    )
    return plan, binding, paths


class CountingBackend:
    def __init__(self, backend: ModuleType) -> None:
        self.backend = backend
        self.prepare_calls = 0
        self.resume_calls = 0

    def prepare_run(
        self,
        request_file: str | Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.prepare_calls += 1
        return self.backend.prepare_run(request_file, **kwargs)

    def resume_run(
        self,
        run_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.resume_calls += 1
        return self.backend.resume_run(run_id, **kwargs)

    def load_approval(self, run_dir: Path) -> dict[str, Any]:
        return self.backend.load_approval(run_dir)

    def advance_milestone(
        self,
        approval: dict[str, Any],
        *,
        milestone: str,
        status: str,
        notes: str,
    ) -> dict[str, Any]:
        return self.backend.advance_milestone(
            approval,
            milestone=milestone,
            status=status,
            notes=notes,
        )

    def write_json(self, path: Path, payload: dict[str, Any]) -> None:
        self.backend.write_json(path, payload)

    def approval_artifact(self, run_dir: Path) -> Path:
        return self.backend.approval_artifact(run_dir)


class BridgeTransport:
    def __init__(self, bridge: Any) -> None:
        self.bridge = bridge

    def invoke(self, operation: str, payload: dict[str, Any]) -> Any:
        return self.bridge.invoke(operation, payload)


@dataclass
class Harness:
    root: Path
    repo_root: Path
    plan: RunPlan
    binding: AbyssStackRuntimeBinding
    source_paths: dict[tuple[str, str], Path]
    state_root: Path
    backend: CountingBackend

    def adapter(self) -> AbyssStackRuntimeAdapter:
        bridge = BRIDGE.AgentOSRuntimeBridge(
            self.state_root,
            backend=self.backend,
            clock=lambda: NOW,
            gate_provider=lambda: {
                "overall_status": "pass",
                "truth_status": {
                    "control_plane": {
                        "source_authored": True,
                        "deployed": True,
                        "trial_proven": True,
                        "live_available": True,
                        "notes": [],
                    }
                },
            },
            advisory_provider=lambda request: {
                "playbook_id": request["playbook_id"],
                "playbook": {
                    "playbook_id": request["playbook_id"],
                    "title": "bounded-change-safe",
                    "summary": "paired adapter proof",
                },
            },
            proposal_provider=lambda _context: {
                "provider": "fixture",
                "selected_target_file": "docs/target.md",
                "spec": {
                    "mode": "exact_replace",
                    "target_file": "docs/target.md",
                    "old_text": "beta",
                    "new_text": "gamma",
                },
                "candidate_files": ["docs/target.md"],
                "target_prompt": "",
                "edit_prompt": "",
                "target_answer": '{"target_file":"docs/target.md"}',
                "edit_answer": (
                    '{"mode":"exact_replace","target_file":"docs/target.md",'
                    '"old_text":"beta","new_text":"gamma"}'
                ),
                "notes": [],
            },
        )
        return AbyssStackRuntimeAdapter(
            profile=self.plan.runtime_profile,
            binding=self.binding,
            transport=BridgeTransport(bridge),
        )

    def subprocess_adapter(self) -> AbyssStackRuntimeAdapter:
        environment = {
            **os.environ,
            "PYTHONPATH": "/deliberately/spoofed/aoa-sdk/src",
        }
        return AbyssStackRuntimeAdapter(
            profile=self.plan.runtime_profile,
            binding=self.binding,
            transport=AbyssStackSubprocessTransport(
                BRIDGE_EXECUTABLE,
                state_root=self.state_root,
                python_interpreter=Path(sys.executable),
                environment=environment,
            ),
        )


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    repo_root = tmp_path / "repo"
    SUPPORT.init_minimal_repo(repo_root)
    policy = SUPPORT.make_policy()
    policy["targets"]["abyss-stack"]["default_repo_root"] = str(repo_root)
    policy_path = tmp_path / "policy.yaml"
    _write_json(policy_path, policy)
    request_path = tmp_path / "request.json"
    _write_json(request_path, SUPPORT.governed_request(repo_root))
    plan, binding, source_paths = _build_plan_and_binding(
        tmp_path,
        request_path=request_path,
        policy_path=policy_path,
    )
    return Harness(
        root=tmp_path,
        repo_root=repo_root,
        plan=plan,
        binding=binding,
        source_paths=source_paths,
        state_root=tmp_path / "agent-os-state",
        backend=CountingBackend(BRIDGE.load_governed_backend()),
    )


def _decision(
    request: Any,
    *,
    decision_id: str,
) -> ApprovalDecision:
    return ApprovalDecision(
        decision_id=decision_id,
        request_id=request.request_id,
        requirement_id=request.requirement_id,
        session_id=request.session_id,
        correlation_id=request.correlation_id,
        plan_digest=request.plan_digest,
        snapshot_digest=request.snapshot_digest,
        verdict="approved",
        approval_authority=request.approval_authority,
        decided_by=request.approval_authority,
        decided_at=request.requested_at + timedelta(seconds=1),
        reason="explicitly approved in the paired runtime proof",
    )


def test_runner_drives_real_governed_execution_and_restores_exactly(
    harness: Harness,
) -> None:
    adapter = harness.adapter()
    runner = AoARunner(clock=lambda: NOW, id_factory=lambda: "real-governed-run")
    session = runner.prepare(harness.plan)
    start = StartCommand(
        command_id="command:start",
        idempotency_key="idempotency:start",
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        plan_digest=harness.plan.plan_digest,
        expected_revision=0,
        issued_at=NOW + timedelta(seconds=1),
        issued_by=session.prepared_by,
        reason="begin the paired runtime proof",
    )

    assert runner.start(session, adapter, start).state == "awaiting_approval"
    freeze_request = next(
        request
        for request in runner.approval_requests(session)
        if request.requirement_id == "approval:abyss-stack:plan-freeze"
    )
    assert (
        runner.approve(
            session,
            _decision(freeze_request, decision_id="decision:plan-freeze"),
        ).state
        == "paused"
    )
    landing_request = next(
        request
        for request in runner.approval_requests(session)
        if request.requirement_id == "approval:abyss-stack:landing"
    )
    assert (
        runner.approve(
            session,
            _decision(landing_request, decision_id="decision:landing"),
        ).state
        == "paused"
    )
    paused = runner.status(session)
    resume = ResumeCommand(
        command_id="command:resume",
        idempotency_key="idempotency:resume",
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        plan_digest=harness.plan.plan_digest,
        expected_revision=paused.revision,
        issued_at=paused.updated_at + timedelta(seconds=1),
        issued_by=session.prepared_by,
        reason="land after the explicit landing approval",
        resume_after_sequence=paused.last_event_sequence,
    )
    assert runner.resume(session, adapter, resume).state == "completed"
    assert "gamma" in (
        harness.repo_root / "docs" / "target.md"
    ).read_text(encoding="utf-8")
    outcome = runner.outcome(session)
    assert outcome is not None
    assert outcome.execution_status == "succeeded"
    assert len(outcome.evidence_bundle_refs) == 1
    assert harness.backend.prepare_calls == 1
    assert harness.backend.resume_calls == 2

    restored_adapter = harness.subprocess_adapter()
    restored_runner = AoARunner(clock=lambda: NOW)
    assert (
        restored_runner.restore(
            harness.plan,
            session,
            restored_adapter,
        ).state
        == "completed"
    )
    assert restored_runner.outcome(session) == outcome
    assert restored_runner.resume(session, restored_adapter, resume).state == "completed"
    assert harness.backend.prepare_calls == 1
    assert harness.backend.resume_calls == 2


def test_snapshot_drift_blocks_before_governed_execution(
    harness: Harness,
) -> None:
    drift_key = next(
        key
        for key in harness.source_paths
        if key[0] == "aoa-agents"
    )
    harness.source_paths[drift_key].write_text(
        '{"drift":true}\n',
        encoding="utf-8",
    )
    adapter = harness.adapter()
    runner = AoARunner(clock=lambda: NOW, id_factory=lambda: "drifted-run")
    session = runner.prepare(harness.plan)
    command = StartCommand(
        command_id="command:start-drifted",
        idempotency_key="idempotency:start-drifted",
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        plan_digest=harness.plan.plan_digest,
        expected_revision=0,
        issued_at=NOW + timedelta(seconds=1),
        issued_by=session.prepared_by,
        reason="prove source drift fails before execution",
    )

    with pytest.raises(Exception, match="stale or spoofed source artifact"):
        runner.start(session, adapter, command)
    assert harness.backend.prepare_calls == 0
    assert harness.backend.resume_calls == 0


def test_runtime_rejects_caller_added_stack_evidence_claim(
    harness: Harness,
) -> None:
    extra_requirement = harness.plan.evidence_requirements[0].model_copy(
        update={
            "requirement_id": "evidence:caller-added:spoofed-stack-claim",
        }
    )
    spoofed_plan = harness.plan.model_copy(
        update={
            "evidence_requirements": (
                *harness.plan.evidence_requirements,
                extra_requirement,
            ),
            "plan_digest": ZERO_DIGEST,
        }
    )
    spoofed_plan = spoofed_plan.model_copy(
        update={
            "plan_digest": canonical_digest(
                spoofed_plan,
                exclude={"plan_digest"},
            )
        }
    )
    binding = harness.binding.model_copy(
        update={"plan_digest": spoofed_plan.plan_digest}
    )
    bridge = BRIDGE.AgentOSRuntimeBridge(
        harness.state_root,
        backend=harness.backend,
        clock=lambda: NOW,
    )
    runner = AoARunner(clock=lambda: NOW, id_factory=lambda: "spoofed-evidence")
    session = runner.prepare(spoofed_plan)

    with pytest.raises(
        BRIDGE.AgentOSBridgeError,
        match="runtime evidence requirements differ",
    ):
        bridge.invoke(
            "observe_snapshot",
            {
                "operation": "observe_snapshot",
                "profile": spoofed_plan.runtime_profile.model_dump(mode="json"),
                "binding": binding.model_dump(mode="json"),
                "plan": spoofed_plan.model_dump(mode="json"),
                "session": session.model_dump(mode="json"),
            },
        )
    assert harness.backend.prepare_calls == 0
    assert harness.backend.resume_calls == 0


def test_runtime_rejects_weakened_approval_requirement(
    harness: Harness,
) -> None:
    requirements = list(harness.plan.approval_requirements)
    requirements[-1] = requirements[-1].model_copy(
        update={"renewable": True}
    )
    weakened_plan = harness.plan.model_copy(
        update={
            "approval_requirements": tuple(requirements),
            "plan_digest": ZERO_DIGEST,
        }
    )
    weakened_plan = weakened_plan.model_copy(
        update={
            "plan_digest": canonical_digest(
                weakened_plan,
                exclude={"plan_digest"},
            )
        }
    )
    binding = harness.binding.model_copy(
        update={"plan_digest": weakened_plan.plan_digest}
    )
    bridge = BRIDGE.AgentOSRuntimeBridge(
        harness.state_root,
        backend=harness.backend,
        clock=lambda: NOW,
    )
    runner = AoARunner(clock=lambda: NOW, id_factory=lambda: "weakened-approval")
    session = runner.prepare(weakened_plan)

    with pytest.raises(
        BRIDGE.AgentOSBridgeError,
        match="exact governed approval requirements",
    ):
        bridge.invoke(
            "observe_snapshot",
            {
                "operation": "observe_snapshot",
                "profile": weakened_plan.runtime_profile.model_dump(mode="json"),
                "binding": binding.model_dump(mode="json"),
                "plan": weakened_plan.model_dump(mode="json"),
                "session": session.model_dump(mode="json"),
            },
        )
    assert harness.backend.prepare_calls == 0
    assert harness.backend.resume_calls == 0


def test_runtime_rejects_resume_that_bypasses_plan_freeze_approval(
    harness: Harness,
) -> None:
    adapter = harness.adapter()
    runner = AoARunner(clock=lambda: NOW, id_factory=lambda: "bypass-run")
    session = runner.prepare(harness.plan)
    start = StartCommand(
        command_id="command:start-bypass",
        idempotency_key="idempotency:start-bypass",
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        plan_digest=harness.plan.plan_digest,
        expected_revision=0,
        issued_at=NOW + timedelta(seconds=1),
        issued_by=session.prepared_by,
        reason="reach the first governed approval boundary",
    )
    awaiting = runner.start(session, adapter, start)
    forged_resume = ResumeCommand(
        command_id="command:resume-without-approval",
        idempotency_key="idempotency:resume-without-approval",
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        plan_digest=harness.plan.plan_digest,
        expected_revision=awaiting.revision,
        issued_at=awaiting.updated_at + timedelta(seconds=1),
        issued_by=session.prepared_by,
        reason="prove the owner runtime rejects approval bypass",
        resume_after_sequence=awaiting.last_event_sequence,
    )

    receipt = adapter.dispatch(harness.plan, session, forged_resume)
    assert receipt.status == "rejected"
    assert receipt.rejection_code == "resume_state_invalid"
    assert adapter.status(session).state == "awaiting_approval"
    assert harness.backend.prepare_calls == 1
    assert harness.backend.resume_calls == 0
