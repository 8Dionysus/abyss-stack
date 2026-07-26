from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import aoa_sdk
import pytest
import yaml
from aoa_sdk import AoASDK

from aoa_sdk.contracts.control_plane import (
    AgentRef,
    ApprovalDecision,
    CloseoutBundleRef,
    EvalVerdictRef,
    MemoryReceiptRef,
    PlanSnapshot,
    ProvenanceRef,
    ResumeCommand,
    RouteDecision,
    RouteExplanation,
    RouteIntent,
    RunPlan,
    RuntimeProfile,
    ScenarioArtifactBinding,
    ScenarioConditionBinding,
    StartCommand,
    canonical_digest,
)
from aoa_sdk.contracts.evidence_chain import CheckpointReceiptRef
from aoa_sdk.control_plane.evidence_chain import (
    assemble_evidence_chain,
    assert_evidence_chain_complete,
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
    PART_ROOT.parent / "governed-runner" / "tests" / "governed_runner_test_support.py"
)
LIVE_ROUTING_BUNDLE_ENV = "AOA_SDK_ROUTING_BUNDLE_ROOT"
LIVE_CHAIN_CASES: dict[str, dict[str, Any]] = {
    "bounded_change_safe": {
        "objective": (
            "resolve authority among authored generated runtime and installed "
            "sources before a bounded repository change"
        ),
        "selected_candidate_id": (
            "aoa-skills:skill:aoa-knowledge-stewardship"
        ),
        "conditions": {"preview_required": False},
        "playbook_id": "AOA-P-0011",
        "primary_input_artifact_kind": None,
    },
    "a2a_summon_return_checkpoint": {
        "objective": (
            "extract and classify a literal closed reviewed session packet "
            "before a bounded child return checkpoint"
        ),
        "selected_candidate_id": "aoa-skills:skill:aoa-session-harvest",
        "conditions": {
            "a2a_eval_packet_earned": True,
            "memo_writeback_earned": False,
        },
        "playbook_id": "AOA-P-0031",
        "primary_input_artifact_kind": "summon_request",
    },
    "runtime_chaos_recovery": {
        "objective": (
            "decide whether live-session closeout evidence yields one guarded "
            "memo candidate after runtime recovery"
        ),
        "selected_candidate_id": "aoa-skills:skill:aoa-memo-writeback",
        "conditions": {
            "derived_surface_recovery_required": False,
            "proof_handoff_earned": True,
        },
        "playbook_id": "AOA-P-0032",
        "primary_input_artifact_kind": "owner_runtime_receipt",
    },
}


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


def _runtime_profile(
    policy_path: Path,
    *,
    scenario_id: str | None = None,
) -> RuntimeProfile:
    return load_abyss_stack_runtime_profile(
        PROFILE_PATH,
        constraint_locations=(
            RuntimeArtifactLocation(
                owner_repo="abyss-stack",
                artifact_ref=(
                    "config-templates/Configs/agent-api/governed-execution-policy.yaml"
                ),
                local_path=str(policy_path),
            ),
        ),
        scenario_id=scenario_id,
    )


def _provenance(owner: str, artifact_ref: str) -> ProvenanceRef:
    return ProvenanceRef(
        owner_repo=owner,
        artifact_ref=artifact_ref,
        source_ref="abyss-stack-c5-paired-proof",
        artifact_digest=ZERO_DIGEST,
        schema_ref="paired-proof",
        schema_version="v1",
    )


def _rewrite_provenance_digests(
    value: Any,
    digests: dict[tuple[str, str], str],
) -> Any:
    if isinstance(value, list):
        return [_rewrite_provenance_digests(item, digests) for item in value]
    if not isinstance(value, dict):
        return value
    rewritten = {
        key: _rewrite_provenance_digests(item, digests) for key, item in value.items()
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


def _exact_provenance(
    owner_repo: str,
    artifact_ref: str,
    path: Path,
    *,
    source_ref: str,
    schema_ref: str,
    schema_version: str,
) -> ProvenanceRef:
    return ProvenanceRef(
        owner_repo=owner_repo,
        artifact_ref=artifact_ref,
        source_ref=source_ref,
        artifact_digest=_sha256(path),
        schema_ref=schema_ref,
        schema_version=schema_version,
    )


def _git_artifact_bytes(
    sdk: AoASDK,
    provenance: ProvenanceRef,
    relative_path: str,
) -> bytes:
    if len(provenance.source_ref) != 40 or any(
        character not in "0123456789abcdef"
        for character in provenance.source_ref
    ):
        raise AssertionError(
            "an unmaterialized owner source is not pinned to an exact Git OID: "
            f"{provenance.owner_repo}:{provenance.artifact_ref}"
        )
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise AssertionError(f"owner artifact path is not bounded: {relative_path}")
    result = subprocess.run(
        [
            "git",
            "-C",
            str(sdk.workspace.repo_path(provenance.owner_repo)),
            "show",
            f"{provenance.source_ref}:{path.as_posix()}",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise AssertionError(
            "cannot materialize exact pinned owner artifact "
            f"{provenance.owner_repo}:{relative_path}@{provenance.source_ref}: "
            f"{detail or 'git show failed'}"
        )
    return result.stdout


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _materialize_virtual_source(
    root: Path,
    sdk: AoASDK,
    provenance: ProvenanceRef,
    *,
    index: int,
    base_ref: str,
    fragment: str,
) -> Path:
    if (
        provenance.owner_repo == "aoa-skills"
        and base_ref == "generated/capability_graph.json"
        and fragment.startswith("nodes/")
    ):
        node_id = fragment.removeprefix("nodes/")
        node = next(
            (
                item
                for item in sdk.control_plane.snapshot().capability_graph.nodes
                if item.id == node_id
            ),
            None,
        )
        if node is None:
            raise AssertionError(f"pinned capability node is unavailable: {node_id}")
        raw = _canonical_json_bytes(node.model_dump(mode="json"))
    elif (
        provenance.owner_repo == "aoa-skills"
        and base_ref == "capabilities/legacy-skill-migration.yaml"
        and fragment.startswith("entries/")
    ):
        entry_id = fragment.removeprefix("entries/")
        payload = yaml.safe_load(
            _git_artifact_bytes(sdk, provenance, base_ref)
        )
        entries = payload.get("entries") if isinstance(payload, dict) else None
        entry = next(
            (
                item
                for item in entries or ()
                if isinstance(item, dict)
                and item.get("legacy_name") == entry_id
            ),
            None,
        )
        if entry is None:
            raise AssertionError(
                f"pinned capability migration is unavailable: {entry_id}"
            )
        raw = _canonical_json_bytes(entry)
    else:
        raw = _git_artifact_bytes(sdk, provenance, base_ref)

    path = root / "source-snapshot" / f"{index:02d}.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    if _sha256(path) != provenance.artifact_digest:
        raise AssertionError(
            "materialized virtual owner source disagrees with compiler provenance: "
            f"{provenance.owner_repo}:{provenance.artifact_ref}"
        )
    return path


def _materialize_plan_source_paths(
    root: Path,
    sdk: AoASDK,
    plan: RunPlan,
    known_paths: dict[tuple[str, str], Path],
) -> dict[tuple[str, str], Path]:
    installed_package_root = Path(aoa_sdk.__file__).resolve().parent
    paths: dict[tuple[str, str], Path] = {}
    for index, provenance in enumerate(plan.snapshot.source_refs):
        key = (provenance.owner_repo, provenance.artifact_ref)
        path = known_paths.get(key)
        if path is None and provenance.owner_repo == "aoa-sdk":
            prefix = "src/aoa_sdk/"
            if not provenance.artifact_ref.startswith(prefix):
                raise AssertionError(
                    f"installed SDK source coordinate is unsupported: {key}"
                )
            path = installed_package_root / provenance.artifact_ref.removeprefix(
                prefix
            )
        if path is not None:
            if _sha256(path) != provenance.artifact_digest:
                raise AssertionError(
                    f"delivered exact source disagrees with compiler provenance: {key}"
                )
            paths[key] = path
            continue

        base_ref, separator, fragment = provenance.artifact_ref.partition("#")
        repo_path = sdk.workspace.repo_path(provenance.owner_repo)
        live_path = repo_path / base_ref
        if live_path.is_file() and _sha256(live_path) == provenance.artifact_digest:
            paths[key] = live_path
            continue

        paths[key] = _materialize_virtual_source(
            root,
            sdk,
            provenance,
            index=index,
            base_ref=base_ref,
            fragment=fragment if separator else "",
        )

    expected = {
        (item.owner_repo, item.artifact_ref)
        for item in plan.snapshot.source_refs
    }
    if set(paths) != expected:
        raise AssertionError("runtime source delivery does not cover the exact plan")
    return paths


def _live_input_payloads(
    scenario_id: str,
    repo_root: Path,
) -> dict[str, tuple[str, dict[str, Any]]]:
    sdk_root = _sdk_source_root()
    if scenario_id == "bounded_change_safe":
        return {
            "bounded_request": (
                "agent-session",
                SUPPORT.governed_request(repo_root),
            )
        }
    if scenario_id == "a2a_summon_return_checkpoint":
        fixture_path = (
            sdk_root
            / "mechanics"
            / "checkpoint"
            / "parts"
            / "child-task-reentry"
            / "examples"
            / "summon_return_checkpoint_e2e.fixture.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        return {
            "summon_request": ("aoa-summon", fixture["summon_request"]),
            "summon_decision": ("aoa-summon", fixture["summon_decision"]),
            "child_task_result": ("aoa-summon", fixture["child_task_result"]),
        }
    receipt_path = (
        STACK_ROOT
        / "mechanics"
        / "runtime-repair"
        / "parts"
        / "degradation-receipts"
        / "examples"
        / "service-degradation-receipt.timeout-chaos.example.json"
    )
    return {
        "owner_runtime_receipt": (
            "abyss-stack",
            json.loads(receipt_path.read_text(encoding="utf-8")),
        )
    }


def _build_live_control_plane_harness(
    root: Path,
    *,
    scenario_id: str,
) -> tuple[Harness, RouteIntent, RouteDecision, RouteExplanation]:
    case = LIVE_CHAIN_CASES[scenario_id]
    sdk_root = _sdk_source_root()
    installed_module_path = Path(aoa_sdk.__file__).resolve()
    if sdk_root in installed_module_path.parents:
        raise AssertionError(
            f"paired proof imported aoa_sdk from the checkout: {installed_module_path}"
        )
    sdk = AoASDK.from_workspace(sdk_root)
    scenario = sdk.control_plane.scenario_ref(scenario_id)
    known_paths: dict[tuple[str, str], Path] = {}
    repo_root = root / "repo"
    if scenario_id == "bounded_change_safe":
        SUPPORT.init_minimal_repo(repo_root)
    else:
        repo_root.mkdir(parents=True, exist_ok=True)

    input_refs: list[ProvenanceRef] = []
    artifact_bindings: list[ScenarioArtifactBinding] = []
    for artifact_kind, (owner_repo, payload) in _live_input_payloads(
        scenario_id,
        repo_root,
    ).items():
        artifact_ref = (
            f"requests/{scenario_id}.json"
            if scenario_id == "bounded_change_safe"
            else f"artifacts/{scenario_id}/{artifact_kind}.json"
        )
        path = root / artifact_ref
        _write_json(path, payload)
        provenance = _exact_provenance(
            owner_repo,
            artifact_ref,
            path,
            source_ref="agent-os-live-control-plane-proof-v1",
            schema_ref=f"runtime-input:{artifact_kind}",
            schema_version="v1",
        )
        if scenario_id == "bounded_change_safe":
            input_refs.append(provenance)
        else:
            artifact_bindings.append(
                ScenarioArtifactBinding(
                    artifact_kind=artifact_kind,
                    artifact_ref=provenance,
                )
            )
        known_paths[(owner_repo, artifact_ref)] = path

    intent_id = f"intent:agent-os-live:{scenario_id}"
    intent_path = root / "intents" / f"{scenario_id}.json"
    _write_json(
        intent_path,
        {
            "authored_at": NOW.isoformat(),
            "intent_id": intent_id,
            "objective": case["objective"],
            "scenario_id": scenario_id,
        },
    )
    caller = _exact_provenance(
        "agent-session",
        f"intents/{scenario_id}.json",
        intent_path,
        source_ref="agent-os-live-control-plane-proof-v1",
        schema_ref="aoa_control_plane_v1",
        schema_version="aoa_control_plane_v1",
    )
    intent = RouteIntent(
        intent_id=intent_id,
        correlation_id=f"correlation:agent-os-live:{scenario_id}",
        objective=case["objective"],
        requested_by=AgentRef(
            agent_id="agent-os-runtime-integration-caller",
            provenance=caller,
        ),
        scenario=scenario,
        requested_capability_kinds=("skill",),
        context_refs=(
            *input_refs,
            *(item.artifact_ref for item in artifact_bindings),
        ),
        authored_at=NOW,
        provenance=caller,
    )
    decision = sdk.control_plane.resolve(intent)
    assert sdk.control_plane.resolve(intent) == decision
    assert decision.selected_candidate_id == case["selected_candidate_id"]
    explanation = sdk.control_plane.explain(decision)
    assert sdk.control_plane.explain(decision) == explanation

    condition_bindings: list[ScenarioConditionBinding] = []
    for condition_id, value in case["conditions"].items():
        artifact_ref = f"reviews/{scenario_id}/{condition_id}.json"
        path = root / artifact_ref
        _write_json(
            path,
            {
                "condition_id": condition_id,
                "reviewed_value": value,
                "scenario_id": scenario_id,
            },
        )
        provenance = _exact_provenance(
            "agent-session",
            artifact_ref,
            path,
            source_ref="agent-os-live-control-plane-proof-v1",
            schema_ref="reviewed-scenario-condition-v1",
            schema_version="v1",
        )
        condition_bindings.append(
            ScenarioConditionBinding(
                condition_id=condition_id,
                value=value,
                provenance=provenance,
            )
        )
        known_paths[("agent-session", artifact_ref)] = path

    binding_artifact_ref = f"bindings/{scenario_id}.json"
    binding_path = root / binding_artifact_ref
    _write_json(
        binding_path,
        {
            "decision_id": decision.decision_id,
            "scenario_id": scenario_id,
            "selected_candidate_id": decision.selected_candidate_id,
        },
    )
    binding_provenance = _exact_provenance(
        "agent-session",
        binding_artifact_ref,
        binding_path,
        source_ref="agent-os-live-control-plane-proof-v1",
        schema_ref="aoa_control_plane_v1",
        schema_version="aoa_control_plane_v1",
    )
    known_paths[("agent-session", binding_artifact_ref)] = binding_path
    binding = sdk.control_plane.bind_scenario(
        decision,
        scenario_id,
        binding_id=f"scenario-binding:agent-os-live:{scenario_id}",
        provenance=binding_provenance,
        input_refs=tuple(input_refs),
        input_artifact_bindings=tuple(artifact_bindings),
        condition_bindings=tuple(condition_bindings),
    )
    assert (
        sdk.control_plane.bind_scenario(
            decision,
            scenario_id,
            binding_id=f"scenario-binding:agent-os-live:{scenario_id}",
            provenance=binding_provenance,
            input_refs=tuple(input_refs),
            input_artifact_bindings=tuple(artifact_bindings),
            condition_bindings=tuple(condition_bindings),
        )
        == binding
    )

    policy_path = root / "policy.yaml"
    policy = SUPPORT.make_policy()
    if scenario_id == "bounded_change_safe":
        policy["targets"]["abyss-stack"]["default_repo_root"] = str(
            repo_root
        )
    _write_json(policy_path, policy)
    profile = _runtime_profile(
        policy_path,
        scenario_id=scenario_id,
    )
    known_paths[
        (profile.provenance.owner_repo, profile.provenance.artifact_ref)
    ] = PROFILE_PATH
    for constraint in profile.constraint_refs:
        known_paths[(constraint.owner_repo, constraint.artifact_ref)] = policy_path
    plan = sdk.control_plane.compile(decision, binding, profile)
    assert sdk.control_plane.compile(decision, binding, profile) == plan
    assert plan.provenance.source_ref.startswith(
        "aoa_control_plane_plan_compiler_v3@"
    )
    assert plan.decision_ref.digest == canonical_digest(decision)
    assert plan.scenario_binding == binding

    source_paths = _materialize_plan_source_paths(
        root,
        sdk,
        plan,
        known_paths,
    )
    contour_path = (
        installed_module_path.parent
        / "control_plane"
        / "planning"
        / "data"
        / "playbook-plan-contours.v1.json"
    )
    if any(
        _sha256(contour_path) != item.artifact_digest
        for item in plan.snapshot.abi_refs
    ):
        raise AssertionError("installed compiler ABI bytes differ from the run plan")
    primary_kind = case["primary_input_artifact_kind"]
    request_ref = (
        input_refs[0]
        if primary_kind is None
        else next(
            item.artifact_ref
            for item in binding.input_artifact_bindings
            if item.artifact_kind == primary_kind
        )
    )
    runtime_binding = AbyssStackRuntimeBinding(
        binding_id=f"binding:abyss-stack:live-compiler:{scenario_id}",
        plan_digest=plan.plan_digest,
        scenario_id=scenario_id,
        playbook_id=case["playbook_id"],
        request_ref=request_ref,
        request_path=str(
            source_paths[(request_ref.owner_repo, request_ref.artifact_ref)]
        ),
        source_locations=tuple(
            RuntimeArtifactLocation(
                owner_repo=item.owner_repo,
                artifact_ref=item.artifact_ref,
                local_path=str(
                    source_paths[(item.owner_repo, item.artifact_ref)]
                ),
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
        adapter_contract_ref=profile.provenance,
    )
    return (
        Harness(
            root=root,
            repo_root=repo_root,
            plan=plan,
            binding=runtime_binding,
            source_paths=source_paths,
            state_root=root / "agent-os-state",
            backend=CountingBackend(BRIDGE.load_governed_backend()),
        ),
        intent,
        decision,
        explanation,
    )


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
    profile = _runtime_profile(
        policy_path,
        scenario_id="bounded_change_safe",
    )
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
        if (item["owner_repo"], item["artifact_ref"]) == original_profile_key
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


def _rewrite_artifact_coordinate(
    value: Any,
    *,
    old: tuple[str, str],
    new: tuple[str, str],
) -> Any:
    if isinstance(value, list):
        return [
            _rewrite_artifact_coordinate(item, old=old, new=new)
            for item in value
        ]
    if isinstance(value, dict):
        rewritten = {
            key: _rewrite_artifact_coordinate(item, old=old, new=new)
            for key, item in value.items()
        }
        if (
            rewritten.get("owner_repo"),
            rewritten.get("artifact_ref"),
        ) == old:
            rewritten["owner_repo"], rewritten["artifact_ref"] = new
        return rewritten
    return value


def _build_read_only_harness(
    root: Path,
    *,
    scenario_id: str,
    complete_return: bool = True,
    conflicting_return: bool = False,
) -> Harness:
    if not complete_return and conflicting_return:
        raise AssertionError(
            "an A2A return trial must select incomplete or conflicting input"
        )
    sdk_root = _sdk_source_root()
    policy_path = root / "policy.yaml"
    _write_json(policy_path, SUPPORT.make_policy())
    profile = _runtime_profile(
        policy_path,
        scenario_id=scenario_id,
    )
    profile_ref = profile.provenance.model_dump(mode="json")
    constraint_ref = profile.constraint_refs[0].model_dump(mode="json")
    example_name = {
        "a2a_summon_return_checkpoint": "a2a-eval-only.run-plan.json",
        "runtime_chaos_recovery": "runtime-proof-without-reground.run-plan.json",
    }[scenario_id]
    example_path = (
        sdk_root
        / "mechanics"
        / "boundary-bridge"
        / "parts"
        / "plan-compilation-control-plane"
        / "examples"
        / example_name
    )
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    original_profile = payload["runtime_profile"]["provenance"]
    original_profile_key = (
        original_profile["owner_repo"],
        original_profile["artifact_ref"],
    )
    payload["runtime_profile"] = profile.model_dump(mode="json")
    payload["approval_requirements"] = []
    for step in payload["steps"]:
        step["approval_requirement_ids"] = []

    input_payloads: dict[tuple[str, str], dict[str, Any]] = {}
    if scenario_id == "a2a_summon_return_checkpoint":
        fixture_path = (
            sdk_root
            / "mechanics"
            / "checkpoint"
            / "parts"
            / "child-task-reentry"
            / "examples"
            / "summon_return_checkpoint_e2e.fixture.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        child_result = dict(fixture["child_task_result"])
        child_result["remote_task"] = dict(child_result["remote_task"])
        if not complete_return:
            child_result["remote_task"]["returned_artifacts"] = [
                fixture["summon_request"]["expected_outputs"][0]
            ]
        if conflicting_return:
            child_result["remote_task"]["parent_task_id"] = (
                "parent:conflicting-a2a-return"
            )
        for artifact_kind, artifact_payload in (
            ("summon_request", fixture["summon_request"]),
            ("summon_decision", fixture["summon_decision"]),
            ("child_task_result", child_result),
        ):
            old_ref = next(
                item["artifact_ref"]
                for item in payload["scenario_binding"][
                    "input_artifact_bindings"
                ]
                if item["artifact_kind"] == artifact_kind
            )
            old_key = (old_ref["owner_repo"], old_ref["artifact_ref"])
            new_key = ("aoa-summon", old_ref["artifact_ref"])
            payload = _rewrite_artifact_coordinate(
                payload,
                old=old_key,
                new=new_key,
            )
            input_payloads[new_key] = artifact_payload
        for requirement in payload["evidence_requirements"]:
            if requirement["artifact_binding"] == "scenario_input":
                requirement["producer_owner"] = "aoa-summon"
        playbook_id = "AOA-P-0031"
        primary_kind = "summon_request"
    else:
        old_ref = payload["scenario_binding"]["input_artifact_bindings"][0][
            "artifact_ref"
        ]
        old_key = (old_ref["owner_repo"], old_ref["artifact_ref"])
        new_key = ("abyss-stack", old_ref["artifact_ref"])
        payload = _rewrite_artifact_coordinate(
            payload,
            old=old_key,
            new=new_key,
        )
        for requirement in payload["evidence_requirements"]:
            if requirement["requirement_id"] == (
                "evidence:runtime-chaos:owner-receipt"
            ):
                requirement["producer_owner"] = "abyss-stack"
        receipt_path = (
            STACK_ROOT
            / "mechanics"
            / "runtime-repair"
            / "parts"
            / "degradation-receipts"
            / "examples"
            / "service-degradation-receipt.timeout-chaos.example.json"
        )
        input_payloads[new_key] = json.loads(
            receipt_path.read_text(encoding="utf-8")
        )
        playbook_id = "AOA-P-0032"
        primary_kind = "owner_runtime_receipt"

    source_refs = [
        (
            profile_ref
            if (item["owner_repo"], item["artifact_ref"])
            == original_profile_key
            else item
        )
        for item in payload["snapshot"]["source_refs"]
    ]
    source_refs.append(constraint_ref)
    payload["snapshot"]["source_refs"] = source_refs

    paths: dict[tuple[str, str], Path] = {}
    for index, item in enumerate(source_refs):
        key = (item["owner_repo"], item["artifact_ref"])
        if key in input_payloads:
            path = root / "scenario-inputs" / f"{index}.json"
            _write_json(path, input_payloads[key])
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
                    "fixture": "exact read-only runtime snapshot material",
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
    primary_ref = next(
        item.artifact_ref
        for item in plan.scenario_binding.input_artifact_bindings
        if item.artifact_kind == primary_kind
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
        binding_id=f"binding:abyss-stack:{scenario_id}",
        plan_digest=plan.plan_digest,
        scenario_id=scenario_id,
        playbook_id=playbook_id,
        request_ref=primary_ref,
        request_path=str(paths[(primary_ref.owner_repo, primary_ref.artifact_ref)]),
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
    repo_root = root / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    return Harness(
        root=root,
        repo_root=repo_root,
        plan=plan,
        binding=binding,
        source_paths=paths,
        state_root=root / "agent-os-state",
        backend=CountingBackend(BRIDGE.load_governed_backend()),
    )


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

    def adapter(
        self,
        *,
        plan: RunPlan | None = None,
        binding: AbyssStackRuntimeBinding | None = None,
    ) -> AbyssStackRuntimeAdapter:
        selected_plan = plan or self.plan
        selected_binding = binding or self.binding
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
            profile=selected_plan.runtime_profile,
            binding=selected_binding,
            transport=BridgeTransport(bridge),
        )

    def subprocess_adapter(
        self,
        *,
        plan: RunPlan | None = None,
        binding: AbyssStackRuntimeBinding | None = None,
    ) -> AbyssStackRuntimeAdapter:
        selected_plan = plan or self.plan
        selected_binding = binding or self.binding
        environment = {
            **os.environ,
            "PYTHONPATH": "/deliberately/spoofed/aoa-sdk/src",
        }
        return AbyssStackRuntimeAdapter(
            profile=selected_plan.runtime_profile,
            binding=selected_binding,
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


def _close_c5_chain(
    *,
    runner: AoARunner,
    adapter: AbyssStackRuntimeAdapter,
    plan: RunPlan,
    session: Any,
    intent: RouteIntent,
    decision: RouteDecision,
    explanation: RouteExplanation,
    token: str,
) -> None:
    outcome = runner.outcome(session)
    assert outcome is not None
    eval_refs = tuple(
        EvalVerdictRef(
            ref_id=f"eval-verdict:{token}:{item.requirement_id}",
            provenance=_provenance(
                item.eval_owner_ref.owner_repo,
                f"paired-proof/{token}/eval/{item.requirement_id}.json",
            ),
            satisfies_requirement_ids=(item.requirement_id,),
        )
        for item in plan.eval_requirements
    )
    memory_refs = tuple(
        MemoryReceiptRef(
            ref_id=f"memory-receipt:{token}:{item.requirement_id}",
            provenance=_provenance(
                item.memory_owner_ref.owner_repo,
                f"paired-proof/{token}/memo/{item.requirement_id}.json",
            ),
            satisfies_requirement_ids=(item.requirement_id,),
        )
        for item in plan.retention_requirements
    )
    checkpoint_refs = (
        CheckpointReceiptRef(
            ref_id=f"checkpoint-receipt:{token}",
            provenance=_provenance(
                plan.checkpoint_policy.owner.owner_repo,
                f"paired-proof/{token}/checkpoint/reviewed.json",
            ),
            review_status="reviewed",
            covered_step_ids=plan.checkpoint_policy.required_after_step_ids,
            covers_pause=True,
        ),
    )
    closeout_owners = {
        item.owner_ref.owner_repo for item in plan.closeout_requirements
    }
    assert len(closeout_owners) == 1
    closeout_ref = CloseoutBundleRef(
        ref_id=f"closeout-receipt:{token}",
        provenance=_provenance(
            next(iter(closeout_owners)),
            f"paired-proof/{token}/closeout/bundle.json",
        ),
        satisfies_requirement_ids=tuple(
            item.requirement_id for item in plan.closeout_requirements
        ),
    )
    chain = assemble_evidence_chain(
        intent=intent,
        decision=decision,
        explanation=explanation,
        plan=plan,
        session=session,
        events=runner.events(session),
        runtime_outcome=outcome,
        eval_verdict_refs=eval_refs,
        memory_receipt_refs=memory_refs,
        checkpoint_receipt_refs=checkpoint_refs,
        closeout_bundle_ref=closeout_ref,
        assembled_at=NOW + timedelta(seconds=30),
        assembled_by=_provenance(
            "aoa-sdk",
            "src/aoa_sdk/control_plane/evidence_chain.py",
        ),
    )
    assert assert_evidence_chain_complete(chain) == closeout_ref
    assert runner.closeout(session, outcome, chain).state == "closed"
    assert adapter.status(session).closeout_ref == closeout_ref


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
    assert "gamma" in (harness.repo_root / "docs" / "target.md").read_text(
        encoding="utf-8"
    )
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
    assert (
        restored_runner.resume(session, restored_adapter, resume).state == "completed"
    )
    assert harness.backend.prepare_calls == 1
    assert harness.backend.resume_calls == 2


@pytest.mark.skipif(
    LIVE_ROUTING_BUNDLE_ENV not in os.environ,
    reason="live public compiler proof requires an explicit routing bundle",
)
def test_public_compiler_v3_c5_chain_closes_real_governed_runtime(
    tmp_path: Path,
) -> None:
    harness, intent, decision, explanation = _build_live_control_plane_harness(
        tmp_path,
        scenario_id="bounded_change_safe",
    )
    plan = harness.plan
    adapter = harness.adapter()
    runner = AoARunner(clock=lambda: NOW, id_factory=lambda: "real-c5-chain")
    session = runner.prepare(plan)
    start = StartCommand(
        command_id="command:c5:start",
        idempotency_key="idempotency:c5:start",
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        plan_digest=plan.plan_digest,
        expected_revision=0,
        issued_at=NOW + timedelta(seconds=1),
        issued_by=session.prepared_by,
        reason="begin the paired C5 runtime proof",
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
            _decision(freeze_request, decision_id="decision:c5:plan-freeze"),
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
            _decision(landing_request, decision_id="decision:c5:landing"),
        ).state
        == "paused"
    )
    paused = runner.status(session)
    resume = ResumeCommand(
        command_id="command:c5:resume",
        idempotency_key="idempotency:c5:resume",
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        plan_digest=plan.plan_digest,
        expected_revision=paused.revision,
        issued_at=paused.updated_at + timedelta(seconds=1),
        issued_by=session.prepared_by,
        reason="land after both explicit governed approvals",
        resume_after_sequence=paused.last_event_sequence,
    )
    assert runner.resume(session, adapter, resume).state == "completed"
    outcome = runner.outcome(session)
    assert outcome is not None
    assert outcome.eval_verdict_refs == ()
    assert outcome.memory_receipt_refs == ()

    eval_refs = tuple(
        EvalVerdictRef(
            ref_id=f"eval-verdict:{item.requirement_id}",
            provenance=_provenance(
                item.eval_owner_ref.owner_repo,
                f"paired-proof/eval/{item.requirement_id}.json",
            ),
            satisfies_requirement_ids=(item.requirement_id,),
        )
        for item in plan.eval_requirements
    )
    memory_refs = tuple(
        MemoryReceiptRef(
            ref_id=f"memory-receipt:{item.requirement_id}",
            provenance=_provenance(
                item.memory_owner_ref.owner_repo,
                f"paired-proof/memo/{item.requirement_id}.json",
            ),
            satisfies_requirement_ids=(item.requirement_id,),
        )
        for item in plan.retention_requirements
    )
    checkpoint_refs = (
        CheckpointReceiptRef(
            ref_id="checkpoint-receipt:real-c5-chain",
            provenance=_provenance(
                plan.checkpoint_policy.owner.owner_repo,
                "paired-proof/checkpoint/reviewed.json",
            ),
            review_status="reviewed",
            covered_step_ids=plan.checkpoint_policy.required_after_step_ids,
            covers_pause=True,
        ),
    )
    closeout_owners = {item.owner_ref.owner_repo for item in plan.closeout_requirements}
    assert len(closeout_owners) == 1
    closeout_ref = CloseoutBundleRef(
        ref_id="closeout-receipt:real-c5-chain",
        provenance=_provenance(
            next(iter(closeout_owners)),
            "paired-proof/closeout/bundle.json",
        ),
        satisfies_requirement_ids=tuple(
            item.requirement_id for item in plan.closeout_requirements
        ),
    )
    chain = assemble_evidence_chain(
        intent=intent,
        decision=decision,
        explanation=explanation,
        plan=plan,
        session=session,
        events=runner.events(session),
        runtime_outcome=outcome,
        eval_verdict_refs=eval_refs,
        memory_receipt_refs=memory_refs,
        checkpoint_receipt_refs=checkpoint_refs,
        closeout_bundle_ref=closeout_ref,
        assembled_at=NOW + timedelta(seconds=10),
        assembled_by=_provenance(
            "aoa-sdk",
            "src/aoa_sdk/control_plane/evidence_chain.py",
        ),
    )
    assert assert_evidence_chain_complete(chain) == closeout_ref
    assert runner.closeout(session, outcome, chain).state == "closed"
    assert adapter.status(session).closeout_ref == closeout_ref
    assert "gamma" in (harness.repo_root / "docs" / "target.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.skipif(
    LIVE_ROUTING_BUNDLE_ENV not in os.environ,
    reason="live public compiler proof requires an explicit routing bundle",
)
def test_a2a_return_lane_completes_a_public_compiler_v3_c5_chain(
    tmp_path: Path,
) -> None:
    harness, intent, decision, explanation = _build_live_control_plane_harness(
        tmp_path,
        scenario_id="a2a_summon_return_checkpoint",
    )
    plan = harness.plan
    adapter = harness.adapter()
    runner = AoARunner(clock=lambda: NOW, id_factory=lambda: "a2a-return")
    session = runner.prepare(plan)
    start = StartCommand(
        command_id="command:a2a:start",
        idempotency_key="idempotency:a2a:start",
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        plan_digest=plan.plan_digest,
        expected_revision=0,
        issued_at=NOW + timedelta(seconds=1),
        issued_by=session.prepared_by,
        reason="review one owner-bound A2A return",
    )

    assert runner.start(session, adapter, start).state == "completed"
    outcome = runner.outcome(session)
    assert outcome is not None
    assert outcome.execution_status == "succeeded"
    assert outcome.eval_verdict_refs == ()
    assert outcome.memory_receipt_refs == ()
    assert harness.backend.prepare_calls == 0
    assert harness.backend.resume_calls == 0
    runtime_evidence_ref = next(
        item
        for item in outcome.evidence_bundle_refs
        if item.provenance.source_ref == BRIDGE.ADAPTER_VERSION
    )
    evidence_path = Path(
        runtime_evidence_ref.provenance.artifact_ref.removeprefix("local:")
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    artifact_kinds = {
        item["artifact_kind"] for item in evidence["artifacts"]
    }
    assert {
        "scenario_input:summon_request",
        "scenario_input:summon_decision",
        "scenario_input:child_task_result",
        "codex_local_target",
        "return_plan",
        "checkpoint_bridge_plan",
        "a2a_return_eval_packet",
        "runtime_closeout_dry_run_receipt",
    }.issubset(artifact_kinds)
    assert evidence["boundaries"]["eval_verdict"] is False
    _close_c5_chain(
        runner=runner,
        adapter=adapter,
        plan=plan,
        session=session,
        intent=intent,
        decision=decision,
        explanation=explanation,
        token="a2a-return",
    )


def test_a2a_return_lane_fails_closed_on_an_incomplete_reviewed_return(
    tmp_path: Path,
) -> None:
    harness = _build_read_only_harness(
        tmp_path,
        scenario_id="a2a_summon_return_checkpoint",
        complete_return=False,
    )
    adapter = harness.adapter()
    runner = AoARunner(clock=lambda: NOW, id_factory=lambda: "a2a-incomplete")
    session = runner.prepare(harness.plan)
    start = StartCommand(
        command_id="command:a2a-incomplete:start",
        idempotency_key="idempotency:a2a-incomplete:start",
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        plan_digest=harness.plan.plan_digest,
        expected_revision=0,
        issued_at=NOW + timedelta(seconds=1),
        issued_by=session.prepared_by,
        reason="prove an incomplete child return cannot become success",
    )

    assert runner.start(session, adapter, start).state == "failed"
    outcome = runner.outcome(session)
    assert outcome is not None
    assert outcome.execution_status == "failed"
    assert outcome.failure_codes == ("a2a_incomplete_return",)
    assert harness.backend.prepare_calls == 0
    assert harness.backend.resume_calls == 0


def test_a2a_return_lane_rejects_a_conflicting_review_chain(
    tmp_path: Path,
) -> None:
    harness = _build_read_only_harness(
        tmp_path,
        scenario_id="a2a_summon_return_checkpoint",
        conflicting_return=True,
    )
    bridge = BRIDGE.AgentOSRuntimeBridge(
        harness.state_root,
        backend=harness.backend,
        clock=lambda: NOW,
    )
    runner = AoARunner(clock=lambda: NOW, id_factory=lambda: "a2a-conflict")
    session = runner.prepare(harness.plan)

    with pytest.raises(
        BRIDGE.AgentOSBridgeError,
        match="do not form one reviewed parent/decision/return chain",
    ):
        bridge.invoke(
            "observe_snapshot",
            {
                "operation": "observe_snapshot",
                "profile": harness.plan.runtime_profile.model_dump(mode="json"),
                "binding": harness.binding.model_dump(mode="json"),
                "plan": harness.plan.model_dump(mode="json"),
                "session": session.model_dump(mode="json"),
            },
        )
    assert harness.backend.prepare_calls == 0
    assert harness.backend.resume_calls == 0


@pytest.mark.skipif(
    LIVE_ROUTING_BUNDLE_ENV not in os.environ,
    reason="live public compiler proof requires an explicit routing bundle",
)
def test_runtime_degradation_lane_restores_a_public_compiler_v3_c5_chain(
    tmp_path: Path,
) -> None:
    harness, intent, decision, explanation = _build_live_control_plane_harness(
        tmp_path,
        scenario_id="runtime_chaos_recovery",
    )
    plan = harness.plan
    binding = harness.binding
    adapter = harness.adapter()
    runner = AoARunner(clock=lambda: NOW, id_factory=lambda: "runtime-degradation")
    session = runner.prepare(plan)
    start = StartCommand(
        command_id="command:runtime-degradation:start",
        idempotency_key="idempotency:runtime-degradation:start",
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        plan_digest=plan.plan_digest,
        expected_revision=0,
        issued_at=NOW + timedelta(seconds=1),
        issued_by=session.prepared_by,
        reason="enter one owner-receipted degradation lane",
    )

    assert runner.start(session, adapter, start).state == "paused"
    paused = runner.status(session)
    assert any(
        event.trigger == "pause"
        and event.state_after == "paused"
        for event in runner.events(session)
    )
    restored_adapter = harness.subprocess_adapter(
        plan=plan,
        binding=binding,
    )
    restored_runner = AoARunner(clock=lambda: NOW)
    assert (
        restored_runner.restore(plan, session, restored_adapter).state
        == "paused"
    )
    resume = ResumeCommand(
        command_id="command:runtime-degradation:resume",
        idempotency_key="idempotency:runtime-degradation:resume",
        session_id=session.session_id,
        correlation_id=session.correlation_id,
        plan_digest=plan.plan_digest,
        expected_revision=paused.revision,
        issued_at=paused.updated_at + timedelta(seconds=1),
        issued_by=session.prepared_by,
        reason="resume only after the interruption receipt is durable",
        resume_after_sequence=paused.last_event_sequence,
    )
    assert (
        restored_runner.resume(
            session,
            restored_adapter,
            resume,
        ).state
        == "completed"
    )
    assert (
        restored_runner.resume(
            session,
            restored_adapter,
            resume,
        ).state
        == "completed"
    )
    outcome = restored_runner.outcome(session)
    assert outcome is not None
    assert outcome.execution_status == "succeeded"
    assert outcome.eval_verdict_refs == ()
    assert outcome.memory_receipt_refs == ()
    assert harness.backend.prepare_calls == 0
    assert harness.backend.resume_calls == 0
    _close_c5_chain(
        runner=restored_runner,
        adapter=restored_adapter,
        plan=plan,
        session=session,
        intent=intent,
        decision=decision,
        explanation=explanation,
        token="runtime-degradation",
    )


def test_snapshot_drift_blocks_before_governed_execution(
    harness: Harness,
) -> None:
    drift_key = next(key for key in harness.source_paths if key[0] == "aoa-agents")
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
    requirements[-1] = requirements[-1].model_copy(update={"renewable": True})
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
