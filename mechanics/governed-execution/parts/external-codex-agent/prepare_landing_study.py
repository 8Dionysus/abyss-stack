#!/usr/bin/env python3
"""Prepare fixed-input external Codex landing-track launch packets.

This script never starts Codex.  It either materializes one exact workspace
manifest or compiles writer launch packets through the packaged aoa-sdk C2
contour and post-C2 AgentIncarnationBinding.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


PART_ROOT = Path(__file__).resolve().parent
SDK_SOURCE_ROOT = os.environ.get("AOA_SDK_SOURCE_ROOT")
if SDK_SOURCE_ROOT:
    sdk_src = Path(SDK_SOURCE_ROOT).resolve() / "src"
    if str(sdk_src) not in sys.path:
        sys.path.insert(0, str(sdk_src))
if str(PART_ROOT) not in sys.path:
    sys.path.insert(0, str(PART_ROOT))

import aoa_sdk as aoa_sdk_package  # noqa: E402
from aoa_sdk.a2a.rebase import (  # noqa: E402
    QuestPassport,
    SummonIntent,
    assess_summon,
    build_summon_request_payload,
    build_summon_result_payload,
)
from aoa_sdk.contracts.control_plane import (  # noqa: E402
    AgentRef,
    CapabilityRef,
    ContentRef,
    ProvenanceRef,
    RouteCandidate,
    RouteDecision,
    RunPlan,
    RuntimeProfile,
    ScenarioArtifactBinding,
    ScenarioBinding,
    ScenarioConditionBinding,
    ScenarioRef,
    canonical_digest,
)
from aoa_sdk.control_plane import (  # noqa: E402
    AgentIncarnationBinding,
    AgentIncarnationBindingV2,
    ContinuationObligation,
    IncarnationPermissionPosture,
    IncarnationStopCondition,
    IncarnationToolProfile,
    IncarnationUsageMetering,
    WakeCondition,
    WakeEscalationPolicy,
    assert_agent_incarnation_binding_matches_plan,
    build_agent_incarnation_binding,
    load_model_realization_ref,
)
from aoa_sdk.control_plane.planning import (  # noqa: E402
    compile_run_plan,
    load_plan_compilation_snapshot,
)
from aoa_sdk.runtime_adapters import (  # noqa: E402
    load_abyss_stack_external_codex_runtime_profile,
)
from external_codex_agent import (  # noqa: E402
    PROJECTION_STATE_SCHEMA_VERSIONS,
    STATE_SCHEMA_PATH,
    ExternalCodexRuntime,
    ExternalCodexRuntimeError,
    _relative_path_is_allowed,
    assert_workspace_manifest,
    build_workspace_manifest,
    load_json,
    sha256_bytes,
    validate_runtime_package_binding,
    validate_json,
    verify_review_state_seal,
)


PROFILE_PATH = PART_ROOT / "runtime-profile.v1.json"
REPORT_SCHEMA_PATH = PART_ROOT / "schemas/external-codex-report.schema.json"
LAUNCH_SCHEMA_PATH = PART_ROOT / "schemas/external-codex-launch.schema.json"
TASK_SCHEMA_PATH = PART_ROOT / "schemas/external-codex-task.schema.json"
RESULT_SCHEMA_PATH = PART_ROOT / "schemas/external-codex-result.schema.json"
PREPARATION_SCHEMA_PATH = (
    PART_ROOT / "schemas/external-codex-study-preparation.schema.json"
)
REVIEW_PREPARATION_SCHEMA_PATH = (
    PART_ROOT / "schemas/external-codex-review-preparation.schema.json"
)
WORKSPACE_MANIFEST_SCHEMA_REF = (
    "mechanics/governed-execution/parts/external-codex-agent/"
    "schemas/external-codex-workspace-manifest.schema.json"
)
WORKSPACE_MANIFEST_SCHEMA_PATH = (
    PART_ROOT / "schemas/external-codex-workspace-manifest.schema.json"
)
LEGACY_WORKSPACE_MANIFEST_EVIDENCE_SCHEMA_REF = (
    "mechanics/governed-execution/parts/external-codex-agent/"
    "schemas/external-codex-workspace-manifest-legacy-evidence.schema.json"
)
LEGACY_WORKSPACE_MANIFEST_EVIDENCE_SCHEMA_PATH = (
    PART_ROOT
    / "schemas/external-codex-workspace-manifest-legacy-evidence.schema.json"
)
LEGACY_WORKSPACE_MANIFEST_EVIDENCE_SCHEMA_VERSION = (
    "abyss_stack_external_codex_workspace_manifest_legacy_evidence_v1"
)
LEGACY_WORKSPACE_MANIFEST_OWNER_RECEIPT_SCHEMA_REF = (
    "mechanics/governed-execution/parts/external-codex-agent/"
    "schemas/external-codex-workspace-manifest-legacy-owner-receipt.schema.json"
)
LEGACY_WORKSPACE_MANIFEST_OWNER_RECEIPT_SCHEMA_PATH = (
    PART_ROOT
    / "schemas/external-codex-workspace-manifest-legacy-owner-receipt.schema.json"
)
LEGACY_WORKSPACE_MANIFEST_OWNER_RECEIPT_SCHEMA_VERSION = (
    "abyss_stack_external_codex_workspace_manifest_legacy_owner_receipt_v1"
)
LANDING_EFFECT_GRANT_SCHEMA_REF = (
    "mechanics/governed-execution/parts/external-codex-agent/"
    "schemas/external-codex-governed-landing-effect-grant.schema.json"
)
LANDING_EFFECT_GRANT_SCHEMA_PATH = PART_ROOT / Path(
    "schemas/external-codex-governed-landing-effect-grant.schema.json"
)
LANDING_EFFECT_GRANT_SCHEMA_VERSION = (
    "abyss_stack_external_codex_governed_landing_effect_grant_v1"
)
WORKSPACE_MANIFEST_SCHEMA_VERSION = (
    "abyss_stack_external_codex_workspace_manifest_v1"
)
ACTOR_MANIFEST_SCHEMA_REF = (
    "mechanics/governed-execution/parts/external-codex-agent/"
    "schemas/external-codex-actor-workspace-manifest.schema.json"
)
ACTOR_MANIFEST_SCHEMA_PATH = (
    PART_ROOT / "schemas/external-codex-actor-workspace-manifest.schema.json"
)
ACTOR_DELTA_SCHEMA_REF = (
    "mechanics/governed-execution/parts/external-codex-agent/"
    "schemas/external-codex-actor-delta.schema.json"
)
ACTOR_DELTA_SCHEMA_PATH = (
    PART_ROOT / "schemas/external-codex-actor-delta.schema.json"
)
REVIEW_STATE_SEAL_SCHEMA_PATH = (
    PART_ROOT / "schemas/external-codex-review-state-seal.schema.json"
)
SDK_SUMMON_REQUEST_SCHEMA_RELATIVE_PATH = Path(
    "mechanics/checkpoint/parts/child-task-reentry/schemas/"
    "summon-request-v4.schema.json"
)
SDK_SUMMON_RESULT_SCHEMA_RELATIVE_PATH = Path(
    "mechanics/checkpoint/parts/child-task-reentry/schemas/"
    "summon-result-v4.schema.json"
)
SDK_SUMMON_REQUEST_SCHEMA_VERSION = "urn:aoa-sdk:a2a:summon-request:v4"
SDK_SUMMON_RESULT_SCHEMA_VERSION = "urn:aoa-sdk:a2a:summon-result:v4"
A2A_SCENARIO_ID = "a2a_summon_return_checkpoint"
BOUNDED_CHANGE_SCENARIO_ID = "bounded_change_safe"
READINESS_PACKET_VERSION = "aoa_models_landing_readiness_packet_v2"
LANDING_TRACK_PACKET_VERSION = "aoa_models_landing_track_packet_v1"


TASK_ROUTE_POLICIES = {
    "landing_readiness": {
        "role_id": "reviewer",
        "effect_class": "read_only",
        "review_required": True,
        "scenario_id": A2A_SCENARIO_ID,
        "capability_id": "mode.verification.contract",
    },
    "landing_preparation": {
        "role_id": "coder",
        "effect_class": "repo_mutation",
        "review_required": True,
        "scenario_id": BOUNDED_CHANGE_SCENARIO_ID,
        "capability_id": "workflow.operations.repository-change",
    },
    "landing_closeout": {
        "role_id": "reviewer",
        "effect_class": "read_only",
        "review_required": True,
        "scenario_id": A2A_SCENARIO_ID,
        "capability_id": "mode.verification.contract",
    },
    "landing_ambiguity_stop": {
        "role_id": "reviewer",
        "effect_class": "read_only",
        "review_required": False,
        "scenario_id": A2A_SCENARIO_ID,
        "capability_id": "mode.knowledge.authority-map",
    },
}
ZERO_DIGEST = "sha256:" + "0" * 64


class StudyPreparationError(RuntimeError):
    """One study source, workspace, or delivery invariant failed."""


def _reviewer_semantics(writer_task_family: str) -> tuple[str, str]:
    """Preserve landing compatibility while giving other duties honest names."""

    if writer_task_family.startswith("landing"):
        return "landing_review", "independent_landing_review"
    return f"{writer_task_family}_review", "independent_actor_review"


def _task_route_policy(packet: Mapping[str, Any]) -> dict[str, Any]:
    policy = TASK_ROUTE_POLICIES.get(str(packet.get("task_family")))
    if policy is None:
        raise StudyPreparationError("study packet task family is unsupported")
    return dict(policy)


def _expected_route(packet: Mapping[str, Any]) -> str:
    effect_lane = (
        "workspace_write"
        if packet.get("allowed_effect_class") == "repo_mutation"
        else "read_only"
    )
    return f"{packet['task_family']}/{effect_lane}/external_codex_agent"


def _aoa_sdk_import_coordinates(aoa_sdk_root: Path) -> tuple[dict[str, str], ...]:
    """Validate and return every currently loaded SDK module/search path."""

    expected_package_root = (aoa_sdk_root.resolve() / "src" / "aoa_sdk").resolve()
    coordinates = {
        "aoa_sdk package": Path(inspect.getfile(aoa_sdk_package)).resolve(),
        "compile_run_plan": Path(inspect.getfile(compile_run_plan)).resolve(),
    }
    for module_name, module in sorted(sys.modules.items()):
        if module_name != "aoa_sdk" and not module_name.startswith("aoa_sdk."):
            continue
        module_file = getattr(module, "__file__", None)
        if isinstance(module_file, str):
            coordinates[f"module {module_name}"] = Path(module_file).resolve()
        module_paths = getattr(module, "__path__", ())
        for index, module_path in enumerate(module_paths):
            coordinates[f"module {module_name} path {index}"] = Path(
                module_path
            ).resolve()
    for label, coordinate in coordinates.items():
        try:
            coordinate.relative_to(expected_package_root)
        except ValueError as exc:
            raise StudyPreparationError(
                f"{label} was imported from {coordinate}, outside exact "
                f"--aoa-sdk-root {aoa_sdk_root}"
            ) from exc
    return tuple(
        {"label": label, "path": str(coordinate)}
        for label, coordinate in sorted(coordinates.items())
    )


def _assert_aoa_sdk_import_root(aoa_sdk_root: Path) -> None:
    """Bind compiled plan bytes to the exact SDK source root named by the caller."""

    _aoa_sdk_import_coordinates(aoa_sdk_root)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _value_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(raw)


def _write_exact(path: Path, payload: bytes) -> None:
    if not path.is_absolute():
        raise StudyPreparationError(f"output path must be absolute: {path}")
    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise StudyPreparationError(f"existing output has different bytes: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if path.exists():
            path.unlink()
        raise


def _file_digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _raw_hex_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise StudyPreparationError(f"path is outside owner root {root}: {path}") from exc


def _owner_relative_from_named_root(path: Path, owner_root_name: str) -> str:
    """Return an owner-relative ref without guessing a checkout outside the path."""

    location = path.resolve()
    for candidate in (location.parent, *location.parents):
        if candidate.name == owner_root_name:
            return _safe_relative(candidate, location)
    raise StudyPreparationError(
        f"owner path is not beneath a {owner_root_name} root: {location}"
    )


def _owner_root_from_named_path(path: Path, owner_root_name: str) -> Path:
    """Return the exact named owner root already present in an admitted path."""

    location = path.resolve()
    for candidate in (location.parent, *location.parents):
        if candidate.name == owner_root_name:
            return candidate
    raise StudyPreparationError(
        f"owner path is not beneath a {owner_root_name} root: {location}"
    )


def _reviewer_capability_ref(
    reviewer_role_path: Path,
    *,
    owner_source_ref: str,
    existing_plan_refs: Sequence[CapabilityRef] = (),
) -> CapabilityRef:
    """Bind one reviewer to an owner pack or exact request-bound plan capability."""

    role = load_json(reviewer_role_path, label="reviewer role contract")
    capability_relative = role.get("capability_pack_ref")
    if not isinstance(capability_relative, str) or not capability_relative:
        unique_existing = tuple(dict.fromkeys(existing_plan_refs))
        if len(unique_existing) == 1:
            return unique_existing[0]
        raise StudyPreparationError(
            "reviewer role names no exact capability pack and its canonical request and scenario do not bind one unique capability"
        )
    owner_root = _owner_root_from_named_path(reviewer_role_path, "aoa-agents")
    capability_path = _resolve_owner_path(owner_root, capability_relative)
    capability = load_json(capability_path, label="reviewer capability pack")
    capability_id = capability.get("id")
    if (
        capability.get("$schema")
        != "https://aoa-agents/schemas/capability-pack.schema.json"
        or not isinstance(capability_id, str)
        or not capability_id
    ):
        raise StudyPreparationError("reviewer capability pack is invalid")
    return CapabilityRef(
        capability_id=capability_id,
        capability_kind="capability_pack",
        provenance=_file_ref(
            owner="aoa-agents",
            artifact_ref=capability_relative,
            path=capability_path,
            source_ref=f"{owner_source_ref}@{_file_digest(capability_path)}",
            schema_ref="schemas/capability-pack.schema.json",
            schema_version="aoa_agent_capability_pack_v1",
        ),
    )


def _resolve_owner_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    _safe_relative(root, path)
    if not path.is_file():
        raise StudyPreparationError(f"owner source is unavailable: {path}")
    return path


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(root), *args],
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise StudyPreparationError(
            f"git {' '.join(args)} failed in {root}: "
            + completed.stderr.decode("utf-8", errors="replace").strip()
        )
    return completed.stdout


def _git_head(root: Path) -> str:
    value = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    if len(value) not in {40, 64} or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise StudyPreparationError(f"invalid Git HEAD in {root}")
    return value


def _source_ref(root: Path, path: Path) -> str:
    head = _git_head(root)
    return f"{head}@{_file_digest(path)}"


def _file_ref(
    *,
    owner: str,
    artifact_ref: str,
    path: Path,
    source_ref: str,
    schema_ref: str,
    schema_version: str,
) -> ProvenanceRef:
    return ProvenanceRef(
        owner_repo=owner,
        artifact_ref=artifact_ref,
        source_ref=source_ref,
        artifact_digest=_file_digest(path),
        schema_ref=schema_ref,
        schema_version=schema_version,
    )


def _landing_effect_schema_refs() -> tuple[
    ProvenanceRef, ProvenanceRef, ProvenanceRef, ProvenanceRef
]:
    """Bind the exact landing, migration-evidence, and owner-receipt schemas."""

    grant_ref = _file_ref(
        owner="abyss-stack",
        artifact_ref=LANDING_EFFECT_GRANT_SCHEMA_REF,
        path=LANDING_EFFECT_GRANT_SCHEMA_PATH,
        source_ref=(
            "uncommitted-runtime-source@"
            + _file_digest(LANDING_EFFECT_GRANT_SCHEMA_PATH)
        ),
        schema_ref="https://json-schema.org/draft/2020-12/schema",
        schema_version=LANDING_EFFECT_GRANT_SCHEMA_VERSION,
    )
    workspace_ref = _file_ref(
        owner="abyss-stack",
        artifact_ref=WORKSPACE_MANIFEST_SCHEMA_REF,
        path=WORKSPACE_MANIFEST_SCHEMA_PATH,
        source_ref=(
            "uncommitted-runtime-source@"
            + _file_digest(WORKSPACE_MANIFEST_SCHEMA_PATH)
        ),
        schema_ref="https://json-schema.org/draft/2020-12/schema",
        schema_version=WORKSPACE_MANIFEST_SCHEMA_VERSION,
    )
    legacy_evidence_ref = _file_ref(
        owner="abyss-stack",
        artifact_ref=LEGACY_WORKSPACE_MANIFEST_EVIDENCE_SCHEMA_REF,
        path=LEGACY_WORKSPACE_MANIFEST_EVIDENCE_SCHEMA_PATH,
        source_ref=(
            "uncommitted-runtime-source@"
            + _file_digest(LEGACY_WORKSPACE_MANIFEST_EVIDENCE_SCHEMA_PATH)
        ),
        schema_ref="https://json-schema.org/draft/2020-12/schema",
        schema_version=LEGACY_WORKSPACE_MANIFEST_EVIDENCE_SCHEMA_VERSION,
    )
    legacy_owner_receipt_ref = _file_ref(
        owner="abyss-stack",
        artifact_ref=LEGACY_WORKSPACE_MANIFEST_OWNER_RECEIPT_SCHEMA_REF,
        path=LEGACY_WORKSPACE_MANIFEST_OWNER_RECEIPT_SCHEMA_PATH,
        source_ref=(
            "uncommitted-runtime-source@"
            + _file_digest(LEGACY_WORKSPACE_MANIFEST_OWNER_RECEIPT_SCHEMA_PATH)
        ),
        schema_ref="https://json-schema.org/draft/2020-12/schema",
        schema_version=LEGACY_WORKSPACE_MANIFEST_OWNER_RECEIPT_SCHEMA_VERSION,
    )
    return grant_ref, workspace_ref, legacy_evidence_ref, legacy_owner_receipt_ref


def _generated_ref(
    *,
    owner: str,
    artifact_ref: str,
    raw: bytes,
    source_ref: str,
    schema_ref: str,
    schema_version: str,
) -> ProvenanceRef:
    return ProvenanceRef(
        owner_repo=owner,
        artifact_ref=artifact_ref,
        source_ref=source_ref,
        artifact_digest=sha256_bytes(raw),
        schema_ref=schema_ref,
        schema_version=schema_version,
    )


def _sdk_a2a_schema_refs(
    aoa_sdk_root: Path,
) -> tuple[Path, ProvenanceRef, Path, ProvenanceRef]:
    """Resolve the exact SDK v4 request/result schemas used by one preparation."""

    coordinates = (
        (
            SDK_SUMMON_REQUEST_SCHEMA_RELATIVE_PATH,
            SDK_SUMMON_REQUEST_SCHEMA_VERSION,
        ),
        (
            SDK_SUMMON_RESULT_SCHEMA_RELATIVE_PATH,
            SDK_SUMMON_RESULT_SCHEMA_VERSION,
        ),
    )
    resolved: list[tuple[Path, ProvenanceRef]] = []
    for relative, schema_version in coordinates:
        path = (aoa_sdk_root / relative).resolve()
        if not path.is_file() or path.is_symlink():
            raise StudyPreparationError(
                f"exact aoa-sdk A2A schema is unavailable: {path}"
            )
        schema = load_json(path, label=f"aoa-sdk schema {relative.name}")
        if schema.get("$id") != schema_version:
            raise StudyPreparationError(
                f"aoa-sdk A2A schema identity differs from {schema_version}: {path}"
            )
        resolved.append(
            (
                path,
                _file_ref(
                    owner="aoa-sdk",
                    artifact_ref=relative.as_posix(),
                    path=path,
                    source_ref=f"uncommitted-sdk-source@{_file_digest(path)}",
                    schema_ref="https://json-schema.org/draft/2020-12/schema",
                    schema_version=schema_version,
                ),
            )
        )
    request, result = resolved
    return request[0], request[1], result[0], result[1]


def _writer_summon_decision_ref(
    *,
    plan: RunPlan,
    task_request_ref: ProvenanceRef,
    writer_summon_ref: ProvenanceRef,
    allow_mixed_binding: bool = False,
) -> ProvenanceRef:
    """Resolve summon responsibility from either A2A or domain scenario ABI."""

    typed_requests = [
        item.artifact_ref
        for item in plan.scenario_binding.input_artifact_bindings
        if item.artifact_kind == "summon_request"
    ]
    typed_decisions = [
        item.artifact_ref
        for item in plan.scenario_binding.input_artifact_bindings
        if item.artifact_kind == "summon_decision"
    ]
    if typed_requests or typed_decisions:
        if typed_requests != [writer_summon_ref] or len(typed_decisions) > 1:
            raise StudyPreparationError(
                "writer plan does not bind one exact canonical summon request/decision"
            )
        if typed_decisions:
            return typed_decisions[0]
        if not allow_mixed_binding:
            raise StudyPreparationError(
                "writer plan does not bind one exact canonical summon request/decision"
            )

    generic_requests = [
        item for item in plan.scenario_binding.input_refs if item == writer_summon_ref
    ]
    generic_decisions = [
        item
        for item in plan.scenario_binding.input_refs
        if item.schema_version == SDK_SUMMON_RESULT_SCHEMA_VERSION
        and item.schema_ref
        == SDK_SUMMON_RESULT_SCHEMA_RELATIVE_PATH.as_posix()
    ]
    if (
        task_request_ref != writer_summon_ref
        or generic_requests != [writer_summon_ref]
        or len(generic_decisions) != 1
    ):
        raise StudyPreparationError(
            "writer plan does not bind one exact canonical summon request/decision"
        )
    return generic_decisions[0]


def _build_canonical_summon_artifacts(
    *,
    output_root: Path,
    artifact_prefix: str,
    source_ref: str,
    request_schema_path: Path,
    request_schema_ref: ProvenanceRef,
    result_schema_path: Path,
    result_schema_ref: ProvenanceRef,
    difficulty: str,
    risk: str,
    delegate_tier: str,
    route_anchor: str,
    desired_role: str,
    child_agent_id: str,
    capability_refs: Sequence[str],
    expected_outputs: Sequence[str],
    parent_task_id: str,
    session_ref: str,
    audit_refs: Sequence[str],
    playbook_ref: str,
    review_required: bool,
    workspace_root: Path,
    reviewed_artifact_path: str | None = None,
) -> dict[str, Any]:
    """Build, validate, write, and provenance-bind one SDK v4 summon pair."""

    passport = QuestPassport(
        difficulty=difficulty,  # type: ignore[arg-type]
        risk=risk,  # type: ignore[arg-type]
        control_mode="codex_supervised",
        delegate_tier=delegate_tier,
        route_anchor=route_anchor,
        expected_artifacts=list(expected_outputs),
        self_agent=False,
    )
    intent = SummonIntent(
        desired_role=desired_role,
        child_agent_id=child_agent_id,
        capability_refs=list(capability_refs),
        expected_outputs=list(expected_outputs),
        parent_task_id=parent_task_id,
        session_ref=session_ref,
        reviewed_artifact_path=reviewed_artifact_path,
        audit_refs=list(audit_refs),
        playbook_ref=playbook_ref,
        review_required=review_required,
        transport_preference="codex_local",
        require_progression=False,
        workspace_root=str(workspace_root),
    )
    request = build_summon_request_payload(
        passport,
        intent,
        expected_outputs=expected_outputs,
        reviewed_artifact_path=reviewed_artifact_path,
        audit_refs=audit_refs,
    )
    validate_json(request, request_schema_path, label="canonical SDK summon request")
    request_raw = _json_bytes(request)
    request_path = output_root / "summon-request.json"
    _write_exact(request_path, request_raw)
    request_ref = _generated_ref(
        owner="abyss-stack",
        artifact_ref=f"{artifact_prefix}/summon-request.json",
        raw=request_raw,
        source_ref=source_ref,
        schema_ref=request_schema_ref.artifact_ref,
        schema_version=SDK_SUMMON_REQUEST_SCHEMA_VERSION,
    )

    decision = assess_summon(passport, intent)
    if (
        not decision.allowed
        or decision.execution_surface != "codex_local"
        or decision.expected_outputs != list(expected_outputs)
    ):
        raise StudyPreparationError(
            "canonical SDK summon assessment did not admit the exact local child request"
        )
    decision_payload = build_summon_result_payload(decision)
    validate_json(
        decision_payload,
        result_schema_path,
        label="canonical SDK summon decision",
    )
    decision_raw = _json_bytes(decision_payload)
    decision_path = output_root / "summon-decision.json"
    _write_exact(decision_path, decision_raw)
    decision_ref = _generated_ref(
        owner="abyss-stack",
        artifact_ref=f"{artifact_prefix}/summon-decision.json",
        raw=decision_raw,
        source_ref=request_ref.artifact_digest,
        schema_ref=result_schema_ref.artifact_ref,
        schema_version=SDK_SUMMON_RESULT_SCHEMA_VERSION,
    )
    return {
        "request_path": request_path,
        "request_ref": request_ref,
        "decision_path": decision_path,
        "decision_ref": decision_ref,
    }


def _load_packet(path: Path) -> dict[str, Any]:
    try:
        packet = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise StudyPreparationError(f"study packet is invalid: {path}") from exc
    required = {
        "schema_version",
        "model_study_id",
        "task_family",
        "role_id",
        "role_contract_ref",
        "parent_task_id",
        "target_owner",
        "return_owner",
        "allowed_effect_class",
        "allowed_paths",
        "authority_scope",
        "objective",
        "from_status",
        "target_status",
        "approval_posture",
        "rollback_reentry_route",
        "ambiguity_policy",
        "review_required",
        "done_state",
        "expected_artifacts",
        "forbidden_effects",
        "rubric",
        "usage_metering",
        "validation_commands",
    }
    optional = {"source_evidence_paths", "indirect_command_policy"}
    if not required.issubset(packet) or set(packet) - required - optional:
        raise StudyPreparationError(
            "study packet fields differ from the fixed v1 contract: "
            f"missing={sorted(required - set(packet))}, "
            f"extra={sorted(set(packet) - required - optional)}"
        )
    packet.setdefault("source_evidence_paths", list(packet["allowed_paths"]))
    indirect_command_policy = packet.get("indirect_command_policy", "fail_closed")
    if indirect_command_policy not in {"fail_closed", "sandbox_confined"}:
        raise StudyPreparationError(
            "study packet indirect_command_policy is unsupported"
        )
    packet_version = packet["schema_version"]
    if packet_version not in {
        READINESS_PACKET_VERSION,
        LANDING_TRACK_PACKET_VERSION,
    }:
        raise StudyPreparationError("study packet schema version is unsupported")
    policy = _task_route_policy(packet)
    if (
        packet["role_id"] != policy["role_id"]
        or packet["allowed_effect_class"] != policy["effect_class"]
        or packet["review_required"] != policy["review_required"]
        or packet["ambiguity_policy"] not in {"escalate", "stop"}
        or packet["target_owner"] != packet["return_owner"]
    ):
        raise StudyPreparationError(
            "study packet exceeds its fixed landing-track role/effect route"
        )
    if (
        packet_version == READINESS_PACKET_VERSION
        and packet["task_family"] != "landing_readiness"
    ):
        raise StudyPreparationError(
            "legacy readiness packet may carry landing_readiness only"
        )
    if (
        packet_version == LANDING_TRACK_PACKET_VERSION
        and packet["task_family"] == "landing_readiness"
    ):
        raise StudyPreparationError(
            "landing_readiness remains on its exact v2 packet contract"
        )
    for key in (
        "allowed_paths",
        "source_evidence_paths",
        "authority_scope",
        "done_state",
        "expected_artifacts",
        "forbidden_effects",
        "rubric",
    ):
        value = packet[key]
        if not isinstance(value, list) or not value or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise StudyPreparationError(f"study packet {key} must be non-empty strings")
    if packet_version == READINESS_PACKET_VERSION:
        required_review_paths = {
            ".github",
            "CHANGELOG.md",
            "DESIGN.AGENTS.md",
            "docs",
            "mechanics",
            "scripts",
            "tests",
        }
        if not required_review_paths.issubset(set(packet["allowed_paths"])):
            raise StudyPreparationError(
                "readiness packet omits required CI, test, change-history, "
                "or owner-guidance scope"
            )
    required_stop_effects = {
        "commit",
        "push",
        "pull_request",
        "merge",
        "tag",
        "release",
        "publication",
        "service_mutation",
        "secret_access",
        "global_config_mutation",
    }
    if not required_stop_effects.issubset(set(packet["forbidden_effects"])):
        raise StudyPreparationError(
            "landing-track packet omits one or more mandatory effect stop-lines"
        )
    usage_metering = packet["usage_metering"]
    if set(usage_metering) != {
        "mode",
        "execution_limit_policy",
        "metering_regime",
        "dimensions",
        "cost_interpretation",
    }:
        raise StudyPreparationError("study packet usage metering shape is invalid")
    expected_dimensions = {
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "active_wall_seconds",
        "turn_count",
        "output_bytes",
        "executed_commands",
    }
    dimensions = usage_metering["dimensions"]
    if (
        usage_metering["mode"] != "observe_only"
        or usage_metering["execution_limit_policy"] != "none"
        or usage_metering["metering_regime"] != "chatgpt_quota"
        or usage_metering["cost_interpretation"] != "measurement_owner"
        or not isinstance(dimensions, list)
        or len(dimensions) != len(expected_dimensions)
        or set(dimensions) != expected_dimensions
    ):
        raise StudyPreparationError(
            "study packet must count complete usage without execution ceilings"
        )
    commands = packet["validation_commands"]
    if not isinstance(commands, list) or not commands:
        raise StudyPreparationError("study packet requires validation commands")
    for command in commands:
        if (
            not isinstance(command, dict)
            or set(command) != {"command_id", "argv", "cwd"}
            or not isinstance(command["argv"], list)
            or not command["argv"]
            or any(not isinstance(item, str) or not item for item in command["argv"])
        ):
            raise StudyPreparationError("study validation command is invalid")
    command_ids = {str(command["command_id"]) for command in commands}
    if len(command_ids) != len(commands):
        raise StudyPreparationError("study validation command ids must be unique")
    if packet_version == READINESS_PACKET_VERSION:
        required_command_ids = {
            "decision-index-check",
            "decision-record-validator",
            "external-codex-ci-compile",
            "external-codex-focused-tests",
            "external-codex-ruff",
            "external-codex-topology-tests",
            "git-diff-check",
            "git-status",
            "nested-agents-validator",
            "stack-source-validator",
        }
        if not required_command_ids.issubset(command_ids):
            raise StudyPreparationError(
                "readiness packet omits one or more fixed source, CI, topology, "
                "or owner validations"
            )
        ruff_command = next(
            command
            for command in commands
            if command["command_id"] == "external-codex-ruff"
        )
        if "--no-cache" not in ruff_command["argv"]:
            raise StudyPreparationError(
                "fixed ruff validation must not mutate ignored workspace cache bytes"
            )
    return packet


def _validate_study(
    study: Mapping[str, Any],
    *,
    packet: Mapping[str, Any],
    study_path: Path,
    packet_path: Path,
    manifest_path: Path,
    aoa_models_root: Path,
) -> tuple[dict[str, Any], ...]:
    if (
        study.get("kind") != "ModelStudy"
        or study.get("schema_version") != "aoa_model_study_v2"
        or study.get("status") != "fixed"
        or study.get("definition_owner") != "aoa-models"
        or study.get("proof_owner") != "aoa-evals"
    ):
        raise StudyPreparationError("study is not a fixed aoa-models definition")
    protocol = study.get("protocol")
    if not isinstance(protocol, dict):
        raise StudyPreparationError("study protocol is unavailable")
    trial_order = (
        tuple(protocol.get("trial_order", ()))
        if isinstance(protocol, dict)
        else ()
    )
    if (
        not trial_order
        or any(not isinstance(arm_id, str) or not arm_id for arm_id in trial_order)
        or len(trial_order) != len(set(trial_order))
    ):
        raise StudyPreparationError("study trial order must be non-empty and unique")
    if protocol.get("writer_reviewer_separation") is not True:
        raise StudyPreparationError("study must require writer/reviewer separation")
    if protocol.get("usage_metering") != packet.get("usage_metering"):
        raise StudyPreparationError(
            "study and packet must bind one exact observe-only usage policy"
        )
    task_routes = protocol.get("task_routes")
    expected_route = _expected_route(packet)
    if (
        not isinstance(task_routes, list)
        or any(not isinstance(item, str) or not item for item in task_routes)
        or expected_route not in task_routes
    ):
        raise StudyPreparationError(
            "study protocol does not name the packet's exact landing-track route"
        )
    arms = study.get("comparison_arms")
    if not isinstance(arms, list) or tuple(
        item.get("arm_id") for item in arms if isinstance(item, dict)
    ) != trial_order:
        raise StudyPreparationError("study arms differ from its exact trial order")
    for arm in arms:
        if (
            set(arm) != {"arm_id", "realization_refs", "route"}
            or len(arm["realization_refs"]) != 1
            or arm["route"] != expected_route
        ):
            raise StudyPreparationError(
                "study arm is not one exact fixed landing-track realization"
            )
        _resolve_owner_path(aoa_models_root, arm["realization_refs"][0])

    expected_inputs = {
        _safe_relative(aoa_models_root, packet_path): _raw_hex_digest(packet_path),
        str(manifest_path.resolve()): _raw_hex_digest(manifest_path),
    }
    actual_inputs = {
        item.get("fixture_ref"): item.get("sha256")
        for item in study.get("fixed_inputs", [])
        if isinstance(item, dict)
    }
    if actual_inputs != expected_inputs:
        raise StudyPreparationError(
            "study fixed inputs do not exactly bind packet and workspace manifest"
        )
    if _safe_relative(aoa_models_root, study_path).split("/")[0:2] != [
        "source",
        "model-studies",
    ]:
        raise StudyPreparationError("study must live in aoa-models source/model-studies")
    return tuple(dict(item) for item in arms)


def _agent_refs(
    aoa_agents_root: Path,
    *,
    required_role_ids: Sequence[str],
    selected_role_id: str,
    role_contract_path: Path,
) -> tuple[AgentRef, ...]:
    head = _git_head(aoa_agents_root)
    refs: list[AgentRef] = []
    for role_id in required_role_ids:
        path = (
            role_contract_path
            if role_id == selected_role_id
            else aoa_agents_root / "agents" / "roles" / role_id / "profile.json"
        )
        artifact_ref = _safe_relative(aoa_agents_root, path)
        is_profile = path.name == "profile.json"
        refs.append(
            AgentRef(
                agent_id=role_id,
                provenance=_file_ref(
                    owner="aoa-agents",
                    artifact_ref=artifact_ref,
                    path=path,
                    source_ref=f"{head}@{_file_digest(path)}",
                    schema_ref=(
                        "schemas/agent-profile.schema.json"
                        if is_profile
                        else "schemas/role-specialization.schema.json"
                    ),
                    schema_version=(
                        "aoa_agent_profile_v1"
                        if is_profile
                        else "aoa_role_specialization_v1"
                    ),
                ),
            )
        )
    return tuple(refs)


def _capability_refs(
    aoa_skills_root: Path, capability_ids: Sequence[str]
) -> tuple[CapabilityRef, ...]:
    graph = aoa_skills_root / "generated" / "capability_graph.json"
    head = _git_head(aoa_skills_root)
    digest = _file_digest(graph)
    return tuple(
        CapabilityRef(
            capability_id=capability_id,
            capability_kind="skill",
            provenance=_file_ref(
                owner="aoa-skills",
                artifact_ref=f"generated/capability_graph.json#nodes/{capability_id}",
                path=graph,
                source_ref=f"{head}@{digest}",
                schema_ref="schemas/capability-graph.schema.json",
                schema_version="aoa_capability_graph_v1",
            ),
        )
        for capability_id in capability_ids
    )


def _requirement_refs(
    *, aoa_evals_root: Path, aoa_memo_root: Path
) -> tuple[ProvenanceRef, ...]:
    eval_path = aoa_evals_root / "generated" / "eval_catalog.min.json"
    memo_path = (
        aoa_memo_root
        / "mechanics/checkpoint/parts/checkpoint-to-memory-mapping/examples/"
        "checkpoint_to_memory_contract.example.json"
    )
    return (
        _file_ref(
            owner="aoa-evals",
            artifact_ref="generated/eval_catalog.min.json",
            path=eval_path,
            source_ref=_source_ref(aoa_evals_root, eval_path),
            schema_ref="schemas/eval-catalog.schema.json",
            schema_version="aoa_eval_catalog_v1",
        ),
        _file_ref(
            owner="aoa-memo",
            artifact_ref=(
                "mechanics/checkpoint/parts/checkpoint-to-memory-mapping/examples/"
                "checkpoint_to_memory_contract.example.json"
            ),
            path=memo_path,
            source_ref=_source_ref(aoa_memo_root, memo_path),
            schema_ref="schemas/checkpoint-to-memory-contract.schema.json",
            schema_version="aoa_checkpoint_to_memory_contract_v1",
        ),
    )


def _workspace_ref(workspace: Path, head: str) -> ProvenanceRef:
    return _generated_ref(
        owner="abyss-stack",
        artifact_ref=f"workspaces/{workspace.name}/HEAD",
        raw=head.encode("ascii"),
        source_ref=head,
        schema_ref="git:commit",
        schema_version="sha1",
    )


def _task_semantic_digest(task: Mapping[str, Any]) -> str:
    excluded = {
        "task_id",
        "correlation_id",
        "continuation_id",
        "expected_incarnation_id",
    }
    semantic = {key: value for key, value in task.items() if key not in excluded}
    immutable_inputs = semantic.get("immutable_inputs")
    if isinstance(immutable_inputs, list):
        semantic["immutable_inputs"] = [
            item
            for item in immutable_inputs
            if not isinstance(item, dict) or item.get("input_id") != "summon-request"
        ]
    return _value_digest(semantic)


def _artifact_coordinate(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "digest": _file_digest(path)}


def _runtime_package_coordinates(args: argparse.Namespace) -> dict[str, Any]:
    package_root = Path(args.runtime_package_root)
    artifact_identity = Path(args.runtime_package_artifact_identity)
    artifact_subjects = Path(args.runtime_package_artifact_subjects)
    if (
        not package_root.is_absolute()
        or package_root.is_symlink()
        or not package_root.is_dir()
        or package_root.resolve() != package_root
    ):
        raise StudyPreparationError(
            "runtime package root must be one exact absolute real directory"
        )
    coordinates: dict[str, Any] = {"package_root": str(package_root)}
    for name, path in (
        ("artifact_identity", artifact_identity),
        ("artifact_subjects", artifact_subjects),
    ):
        if (
            not path.is_absolute()
            or path.is_symlink()
            or not path.is_file()
            or path.resolve() != path
        ):
            raise StudyPreparationError(
                f"runtime package {name} must be one exact absolute real file"
            )
        coordinates[name] = _artifact_coordinate(path)
    return coordinates


def _append_unique_refs(
    values: Sequence[ProvenanceRef],
    *extra: ProvenanceRef,
) -> tuple[ProvenanceRef, ...]:
    result = list(values)
    for item in extra:
        if item not in result:
            result.append(item)
    return tuple(result)


def _verified_launch_coordinate(
    launch: Mapping[str, Any],
    key: str,
) -> Path:
    coordinate = launch.get(key)
    if not isinstance(coordinate, dict) or set(coordinate) != {"path", "digest"}:
        raise StudyPreparationError(f"writer launch {key} coordinate is invalid")
    path = Path(str(coordinate["path"]))
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise StudyPreparationError(f"writer launch {key} artifact is unavailable")
    if _file_digest(path) != coordinate["digest"]:
        raise StudyPreparationError(f"writer launch {key} bytes changed after execution")
    return path


def _adapt_plan_for_reviewer(
    base: RunPlan,
    *,
    reviewer_runtime_profile: RuntimeProfile,
    reviewer_capability_ref: CapabilityRef,
    writer_role_id: str,
    reviewer_role_id: str,
    reviewer_role_ref: ProvenanceRef,
    old_task_ref: ProvenanceRef,
    task_ref: ProvenanceRef,
    old_summon_request_ref: ProvenanceRef,
    review_summon_request_ref: ProvenanceRef,
    old_summon_decision_ref: ProvenanceRef,
    review_summon_decision_ref: ProvenanceRef,
    summon_request_schema_ref: ProvenanceRef,
    summon_result_schema_ref: ProvenanceRef,
    old_model_ref: ProvenanceRef,
    reviewer_model_ref: ProvenanceRef,
    writer_result_ref: ProvenanceRef,
    writer_report_ref: ProvenanceRef,
    writer_actor_final_ref: ProvenanceRef,
    writer_actor_delta_ref: ProvenanceRef,
    review_manifest_ref: ProvenanceRef,
    additional_input_refs: Sequence[ProvenanceRef] = (),
    identity_token: str,
) -> RunPlan:
    def replace(value: ProvenanceRef) -> ProvenanceRef:
        if value == old_task_ref:
            return task_ref
        if value == old_summon_request_ref:
            return review_summon_request_ref
        if value == old_summon_decision_ref:
            return review_summon_decision_ref
        if value == old_model_ref:
            return reviewer_model_ref
        if value == base.runtime_profile.provenance:
            return reviewer_runtime_profile.provenance
        return value

    reviewer_agents = tuple(
        item
        for item in base.scenario_binding.agent_refs
        if item.agent_id == reviewer_role_id
        and item.provenance == reviewer_role_ref
    )
    if len(reviewer_agents) != 1:
        raise StudyPreparationError(
            "reviewer plan does not bind one exact selected reviewer role"
        )
    reviewer_agent = reviewer_agents[0]

    scenario = base.scenario_binding.model_copy(
        update={
            "capability_refs": tuple(
                dict.fromkeys(
                    (*base.scenario_binding.capability_refs, reviewer_capability_ref)
                )
            ),
            "input_refs": tuple(
                replace(item) for item in base.scenario_binding.input_refs
            ),
            "input_artifact_bindings": tuple(
                item.model_copy(update={"artifact_ref": replace(item.artifact_ref)})
                for item in base.scenario_binding.input_artifact_bindings
            ),
        }
    )
    steps = []
    for step in base.steps:
        active_writer_step = (
            any(item.agent_id == writer_role_id for item in step.agent_refs)
            and (
                old_task_ref in step.input_refs
                or old_summon_request_ref in step.input_refs
            )
        )
        agent_refs = list(step.agent_refs)
        if active_writer_step:
            agent_refs = [
                reviewer_agent if item.agent_id == writer_role_id else item
                for item in agent_refs
            ]
            agent_refs = list(dict.fromkeys(agent_refs))
        reviewer_bound_step = reviewer_agent in agent_refs
        steps.append(
            step.model_copy(
                update={
                    "agent_refs": tuple(agent_refs),
                    "input_refs": tuple(replace(item) for item in step.input_refs),
                    **(
                        {
                            "capability_refs": (reviewer_capability_ref,),
                            "effect_class": "read_only",
                        }
                        if reviewer_bound_step
                        else {}
                    ),
                }
            )
        )
    source_refs = _append_unique_refs(
        tuple(replace(item) for item in base.snapshot.source_refs),
        writer_result_ref,
        writer_report_ref,
        writer_actor_final_ref,
        writer_actor_delta_ref,
        review_manifest_ref,
        old_summon_request_ref,
        old_summon_decision_ref,
        review_summon_request_ref,
        review_summon_decision_ref,
        summon_request_schema_ref,
        summon_result_schema_ref,
        reviewer_capability_ref.provenance,
        *additional_input_refs,
    )
    snapshot = base.snapshot.model_copy(
        update={"source_refs": source_refs, "snapshot_digest": ZERO_DIGEST}
    )
    snapshot = snapshot.model_copy(
        update={
            "snapshot_digest": canonical_digest(
                snapshot,
                exclude={"snapshot_digest"},
            )
        }
    )
    runtime_profile = reviewer_runtime_profile.model_copy(
        update={
            "constraint_refs": _append_unique_refs(
                tuple(replace(item) for item in base.runtime_profile.constraint_refs),
                writer_result_ref,
                writer_report_ref,
                writer_actor_final_ref,
                writer_actor_delta_ref,
                review_manifest_ref,
                old_summon_request_ref,
                old_summon_decision_ref,
                review_summon_request_ref,
                review_summon_decision_ref,
                summon_request_schema_ref,
                summon_result_schema_ref,
                reviewer_capability_ref.provenance,
                *additional_input_refs,
            )
        }
    )
    plan = base.model_copy(
        update={
            "plan_id": f"{base.plan_id}:independent-review:{identity_token}",
            "scenario_binding": scenario,
            "runtime_profile": runtime_profile,
            "snapshot": snapshot,
            "steps": tuple(steps),
            "plan_digest": ZERO_DIGEST,
        }
    )
    plan = plan.model_copy(
        update={"plan_digest": canonical_digest(plan, exclude={"plan_digest"})}
    )
    return RunPlan.model_validate(plan.model_dump(mode="python"))


def _prepare_manifest(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    output = Path(args.output).resolve()
    try:
        output.relative_to(workspace)
    except ValueError:
        pass
    else:
        raise StudyPreparationError("workspace manifest cannot be written inside itself")
    payload = build_workspace_manifest(workspace)
    _write_exact(output, _json_bytes(payload))
    return {
        "schema_version": "abyss_stack_external_codex_manifest_preparation_v1",
        "workspace_manifest": str(output),
        "workspace_manifest_digest": _file_digest(output),
        "git_head": payload["git_head"],
        "status_entry_count": len(payload["status_entries"]),
        "content_entry_count": len(payload["content_entries"]),
    }


def _prepare_writers(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    output_root = Path(args.output_root).resolve()
    state_root = Path(args.state_root).resolve()
    aoa_models_root = Path(args.aoa_models_root).resolve()
    aoa_agents_root = Path(args.aoa_agents_root).resolve()
    aoa_skills_root = Path(args.aoa_skills_root).resolve()
    aoa_evals_root = Path(args.aoa_evals_root).resolve()
    aoa_memo_root = Path(args.aoa_memo_root).resolve()
    aoa_playbooks_root = Path(args.aoa_playbooks_root).resolve()
    aoa_sdk_root = Path(args.aoa_sdk_root).resolve()
    _assert_aoa_sdk_import_root(aoa_sdk_root)
    (
        summon_request_schema_path,
        summon_request_schema_ref,
        summon_result_schema_path,
        summon_result_schema_ref,
    ) = _sdk_a2a_schema_refs(aoa_sdk_root)
    study_path = Path(args.study).resolve()
    packet_path = Path(args.study_packet).resolve()
    manifest_path = Path(args.workspace_manifest).resolve()
    codex_executable = Path(args.codex_executable).resolve()
    codex_home = Path(args.codex_home).resolve()
    runtime_package = _runtime_package_coordinates(args)
    if not workspace.is_dir() or not codex_executable.is_file() or not codex_home.is_dir():
        raise StudyPreparationError("workspace, Codex executable, or Codex home is unavailable")
    runtime_profile_payload = load_json(PROFILE_PATH, label="runtime profile")
    try:
        validate_runtime_package_binding(
            runtime_package,
            expected_runtime_subject=runtime_profile_payload["model_admission"][
                "runtime_subject"
            ],
            expected_runtime_package_subject=runtime_profile_payload[
                "model_admission"
            ]["runtime_package_subject"],
            expected_runtime_version=runtime_profile_payload["model_admission"][
                "runtime_version"
            ],
            codex_executable=codex_executable,
            codex_executable_digest=_file_digest(codex_executable),
        )
    except (ExternalCodexRuntimeError, KeyError, TypeError) as exc:
        raise StudyPreparationError(
            "runtime package is not the exact profile-admitted Codex package"
        ) from exc

    for target in (output_root, state_root):
        try:
            target.relative_to(workspace)
        except ValueError:
            pass
        else:
            raise StudyPreparationError("study output/state roots must stay outside workspace")

    study = load_json(study_path, label="aoa-models ModelStudy")
    packet = _load_packet(packet_path)
    indirect_command_policy = packet.get("indirect_command_policy", "fail_closed")
    arms = _validate_study(
        study,
        packet=packet,
        study_path=study_path,
        packet_path=packet_path,
        manifest_path=manifest_path,
        aoa_models_root=aoa_models_root,
    )
    if packet["model_study_id"] != study["model_study_id"]:
        raise StudyPreparationError("study packet and ModelStudy identities differ")
    manifest = load_json(manifest_path, label="workspace manifest")
    assert_workspace_manifest(manifest, workspace)
    workspace_head = str(manifest["git_head"])

    role_contract_path = _resolve_owner_path(
        aoa_agents_root, str(packet["role_contract_ref"])
    )
    role_contract_is_profile = role_contract_path.name == "profile.json"
    role_contract_ref = _file_ref(
        owner="aoa-agents",
        artifact_ref=_safe_relative(aoa_agents_root, role_contract_path),
        path=role_contract_path,
        source_ref=_source_ref(aoa_agents_root, role_contract_path),
        schema_ref=(
            "schemas/agent-profile.schema.json"
            if role_contract_is_profile
            else "schemas/role-specialization.schema.json"
        ),
        schema_version=(
            "aoa_agent_profile_v1"
            if role_contract_is_profile
            else "aoa_role_specialization_v1"
        ),
    )
    study_ref = _file_ref(
        owner="aoa-models",
        artifact_ref=_safe_relative(aoa_models_root, study_path),
        path=study_path,
        source_ref=f"uncommitted-owner-source@{_file_digest(study_path)}",
        schema_ref="schemas/model-study.schema.json",
        schema_version="aoa_model_study_v2",
    )
    packet_ref = _file_ref(
        owner="aoa-models",
        artifact_ref=_safe_relative(aoa_models_root, packet_path),
        path=packet_path,
        source_ref=f"uncommitted-owner-source@{_file_digest(packet_path)}",
        schema_ref=(
            "source/model-studies/landing-readiness-study-packet-v2"
            if packet["schema_version"] == READINESS_PACKET_VERSION
            else "source/model-studies/landing-track-study-packet-v1"
        ),
        schema_version=packet["schema_version"],
    )
    manifest_ref = _file_ref(
        owner="abyss-stack",
        artifact_ref=str(manifest_path),
        path=manifest_path,
        source_ref=workspace_head,
        schema_ref=WORKSPACE_MANIFEST_SCHEMA_REF,
        schema_version="abyss_stack_external_codex_workspace_manifest_v1",
    )
    workspace_ref = _workspace_ref(workspace, workspace_head)
    report_schema_ref = _file_ref(
        owner="abyss-stack",
        artifact_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-report.schema.json"
        ),
        path=REPORT_SCHEMA_PATH,
        source_ref=f"uncommitted-runtime-source@{_file_digest(REPORT_SCHEMA_PATH)}",
        schema_ref="https://json-schema.org/draft/2020-12/schema",
        schema_version="abyss_stack_external_codex_report_v1",
    )
    controller_source_path = PART_ROOT / "external_codex_agent.py"
    controller_source_ref = _file_ref(
        owner="abyss-stack",
        artifact_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/"
            "external_codex_agent.py"
        ),
        path=controller_source_path,
        source_ref=(
            "uncommitted-runtime-source@" + _file_digest(controller_source_path)
        ),
        schema_ref="text/x-python",
        schema_version="abyss_stack_external_codex_controller_source_v1",
    )
    landing_effect_source_path = PART_ROOT / "external_codex_landing_effect.py"
    landing_effect_source_ref = _file_ref(
        owner="abyss-stack",
        artifact_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/"
            "external_codex_landing_effect.py"
        ),
        path=landing_effect_source_path,
        source_ref=(
            "uncommitted-runtime-source@" + _file_digest(landing_effect_source_path)
        ),
        schema_ref="text/x-python",
        schema_version="abyss_stack_external_codex_landing_effect_source_v1",
    )
    (
        landing_effect_grant_schema_ref,
        workspace_manifest_schema_ref,
        legacy_workspace_manifest_evidence_schema_ref,
        legacy_workspace_manifest_owner_receipt_schema_ref,
    ) = _landing_effect_schema_refs()
    snapshot = load_plan_compilation_snapshot()
    route_policy = _task_route_policy(packet)
    contour = snapshot.contour_for(str(route_policy["scenario_id"]))
    agent_refs = _agent_refs(
        aoa_agents_root,
        required_role_ids=contour.required_agent_ids,
        selected_role_id=str(packet["role_id"]),
        role_contract_path=role_contract_path,
    )
    capability_refs = _capability_refs(
        aoa_skills_root, contour.required_capability_ids
    )
    requirement_refs = _requirement_refs(
        aoa_evals_root=aoa_evals_root, aoa_memo_root=aoa_memo_root
    )
    playbook_path = contour.source_playbook_ref
    playbook_raw = _git(
        aoa_playbooks_root,
        "show",
        f"{snapshot.source_lock.owner_source_ref}:{playbook_path}",
    )
    scenario_ref = ScenarioRef(
        scenario_id=contour.scenario,
        provenance=_generated_ref(
            owner="aoa-playbooks",
            artifact_ref=playbook_path,
            raw=playbook_raw,
            source_ref=snapshot.source_lock.owner_source_ref,
            schema_ref="playbooks/playbook.schema.json",
            schema_version="aoa_playbook_v1",
        ),
    )
    resolver_path = aoa_sdk_root / "src/aoa_sdk/control_plane/routing/resolver.py"
    compiler_path = aoa_sdk_root / "src/aoa_sdk/control_plane/planning/compiler.py"
    resolver_ref = _file_ref(
        owner="aoa-sdk",
        artifact_ref="src/aoa_sdk/control_plane/routing/resolver.py",
        path=resolver_path,
        source_ref=f"uncommitted-sdk-source@{_file_digest(resolver_path)}",
        schema_ref="aoa_control_plane_v1",
        schema_version="aoa_control_plane_v1",
    )
    compiler_ref = _file_ref(
        owner="aoa-sdk",
        artifact_ref="src/aoa_sdk/control_plane/planning/compiler.py",
        path=compiler_path,
        source_ref=f"uncommitted-sdk-source@{_file_digest(compiler_path)}",
        schema_ref="aoa_control_plane_v1",
        schema_version="aoa_control_plane_plan_compiler_v3",
    )

    preparation_arms: list[dict[str, Any]] = []
    semantic_digests: set[str] = set()
    study_token = hashlib.sha256(
        (study["model_study_id"] + manifest_ref.artifact_digest).encode("utf-8")
    ).hexdigest()[:20]
    for arm in arms:
        arm_id = str(arm["arm_id"])
        arm_root = output_root / "writers" / arm_id
        identity = f"{study_token}:{arm_id}:writer"
        correlation_id = f"correlation:model-study:{identity}"
        continuation_id = f"continuation:model-study:{identity}"
        incarnation_id = f"incarnation:model-study:{identity}"
        task_id = f"task:model-study:{identity}"
        session_id = f"session:model-study:{identity}"
        summon_outputs = (
            "external_codex_agent_result",
            "independent_landing_review",
        )
        summon = _build_canonical_summon_artifacts(
            output_root=arm_root,
            artifact_prefix=f"runtime-studies/{study_token}/writers/{arm_id}",
            source_ref=study_ref.artifact_digest,
            request_schema_path=summon_request_schema_path,
            request_schema_ref=summon_request_schema_ref,
            result_schema_path=summon_result_schema_path,
            result_schema_ref=summon_result_schema_ref,
            difficulty="d2_slice",
            risk=(
                "r1_repo_local"
                if packet["allowed_effect_class"] == "repo_mutation"
                else "r0_readonly"
            ),
            delegate_tier=(
                "executor" if packet["role_id"] == "coder" else "verifier"
            ),
            route_anchor=study["model_study_id"],
            desired_role=packet["role_id"],
            child_agent_id=incarnation_id,
            capability_refs=(str(route_policy["capability_id"]),),
            expected_outputs=summon_outputs,
            parent_task_id=packet["parent_task_id"],
            session_ref=session_id,
            audit_refs=(
                f"aoa-models:{study_ref.artifact_ref}@{study_ref.artifact_digest}",
                f"aoa-models:{packet_ref.artifact_ref}@{packet_ref.artifact_digest}",
                f"abyss-stack:{manifest_ref.artifact_ref}@{manifest_ref.artifact_digest}",
            ),
            playbook_ref=playbook_path,
            review_required=bool(packet["review_required"]),
            workspace_root=workspace,
        )
        summon_request_path = summon["request_path"]
        summon_request_ref = summon["request_ref"]
        summon_decision_path = summon["decision_path"]
        summon_decision_ref = summon["decision_ref"]
        task = {
            "schema_version": "abyss_stack_external_codex_task_v1",
            "task_id": task_id,
            "correlation_id": correlation_id,
            "continuation_id": continuation_id,
            "expected_incarnation_id": incarnation_id,
            "task_family": packet["task_family"],
            "execution_posture": (
                "ambiguity_stop"
                if packet["task_family"] == "landing_ambiguity_stop"
                else "closeout"
                if packet["task_family"] == "landing_closeout"
                else "bounded_execution"
            ),
            "parent_task_id": packet["parent_task_id"],
            "objective": packet["objective"],
            "transition": {
                "from_status": packet["from_status"],
                "target_status": packet["target_status"],
                "approval_posture": packet["approval_posture"],
                "rollback_reentry_route": packet["rollback_reentry_route"],
            },
            "target_owner": packet["target_owner"],
            "authority_scope": packet["authority_scope"],
            "allowed_effect_class": packet["allowed_effect_class"],
            "allowed_paths": packet["allowed_paths"],
            "source_evidence_paths": packet["source_evidence_paths"],
            "immutable_inputs": [
                {
                    "input_id": "model-study",
                    "local_path": str(study_path),
                    "provenance": study_ref.model_dump(mode="json"),
                },
                {
                    "input_id": "study-packet",
                    "local_path": str(packet_path),
                    "provenance": packet_ref.model_dump(mode="json"),
                },
                {
                    "input_id": "workspace-manifest",
                    "local_path": str(manifest_path),
                    "provenance": manifest_ref.model_dump(mode="json"),
                },
                {
                    "input_id": "runtime-controller-source",
                    "local_path": str(controller_source_path),
                    "provenance": controller_source_ref.model_dump(mode="json"),
                },
                {
                    "input_id": "runtime-landing-effect-source",
                    "local_path": str(landing_effect_source_path),
                    "provenance": landing_effect_source_ref.model_dump(mode="json"),
                },
                {
                    "input_id": "runtime-landing-effect-grant-schema",
                    "local_path": str(LANDING_EFFECT_GRANT_SCHEMA_PATH),
                    "provenance": landing_effect_grant_schema_ref.model_dump(
                        mode="json"
                    ),
                },
                {
                    "input_id": "runtime-workspace-manifest-schema",
                    "local_path": str(WORKSPACE_MANIFEST_SCHEMA_PATH),
                    "provenance": workspace_manifest_schema_ref.model_dump(
                        mode="json"
                    ),
                },
                {
                    "input_id": "runtime-legacy-workspace-manifest-evidence-schema",
                    "local_path": str(LEGACY_WORKSPACE_MANIFEST_EVIDENCE_SCHEMA_PATH),
                    "provenance": legacy_workspace_manifest_evidence_schema_ref.model_dump(
                        mode="json"
                    ),
                },
                {
                    "input_id": "runtime-legacy-workspace-manifest-owner-receipt-schema",
                    "local_path": str(
                        LEGACY_WORKSPACE_MANIFEST_OWNER_RECEIPT_SCHEMA_PATH
                    ),
                    "provenance": legacy_workspace_manifest_owner_receipt_schema_ref.model_dump(
                        mode="json"
                    ),
                },
                {
                    "input_id": "summon-request",
                    "local_path": str(summon_request_path),
                    "provenance": summon_request_ref.model_dump(mode="json"),
                },
                {
                    "input_id": "summon-request-schema",
                    "local_path": str(summon_request_schema_path),
                    "provenance": summon_request_schema_ref.model_dump(mode="json"),
                },
            ],
            "done_state": packet["done_state"],
            "validation_commands": packet["validation_commands"],
            "expected_artifacts": packet["expected_artifacts"],
            "forbidden_effects": packet["forbidden_effects"],
            "ambiguity_policy": packet["ambiguity_policy"],
            "review_required": packet["review_required"],
            "return_owner": packet["return_owner"],
        }
        if indirect_command_policy != "fail_closed":
            task["indirect_command_policy"] = indirect_command_policy
        task_path = arm_root / "task.json"
        task_raw = _json_bytes(task)
        _write_exact(task_path, task_raw)
        task_ref = _generated_ref(
            owner=packet["target_owner"],
            artifact_ref=f"runtime-studies/{study_token}/writers/{arm_id}/task.json",
            raw=task_raw,
            source_ref=study["model_study_id"],
            schema_ref=(
                "mechanics/governed-execution/parts/external-codex-agent/"
                "schemas/external-codex-task.schema.json"
            ),
            schema_version="abyss_stack_external_codex_task_v1",
        )
        semantic_digests.add(_task_semantic_digest(task))

        realization_relative = arm["realization_refs"][0]
        realization_path = _resolve_owner_path(aoa_models_root, realization_relative)
        realization = load_json(realization_path, label=f"{arm_id} model realization")
        model_ref = load_model_realization_ref(
            realization_path,
            artifact_ref=realization_relative,
            source_ref=f"uncommitted-owner-source@{_file_digest(realization_path)}",
        )
        model_slug = realization["configuration"]["runtime"]["model_slug"]
        effort = realization["configuration"]["reasoning_effort"]
        tool_profile_id = realization["configuration"]["tools"]["profile_ref"]
        required_tools = tuple(realization["configuration"]["tools"]["required_tools"])

        child_result = {
            "schema_version": "abyss_stack_transport_study_placeholder_v1",
            "artifact_kind": "child_task_result",
            "arm_id": arm_id,
            "admission_class": "transport_study_fixture",
            "semantic_limit": "placeholder only; no child result exists before execution",
        }
        child_result_path = arm_root / "transport-child-result.json"
        child_result_raw = _json_bytes(child_result)
        _write_exact(child_result_path, child_result_raw)
        child_result_ref = _generated_ref(
            owner="abyss-stack",
            artifact_ref=(
                f"runtime-studies/{study_token}/writers/{arm_id}/"
                "transport-child-result.json"
            ),
            raw=child_result_raw,
            source_ref=study["model_study_id"],
            schema_ref="transport-study-placeholder-v1",
            schema_version="abyss_stack_transport_study_placeholder_v1",
        )
        condition_bindings = tuple(
            ScenarioConditionBinding(
                condition_id=condition.condition_id,
                value=condition.condition_id == "preview_required",
                provenance=_generated_ref(
                    owner="abyss-stack",
                    artifact_ref=(
                        f"runtime-studies/{study_token}/writers/{arm_id}/"
                        f"conditions/{condition.condition_id}.json"
                    ),
                    raw=_json_bytes(
                        {
                            "condition_id": condition.condition_id,
                            "value": condition.condition_id == "preview_required",
                            "reason": (
                                "the fixed isolated workspace-write route requires preview"
                                if condition.condition_id == "preview_required"
                                else "not earned before independent study review"
                            ),
                        }
                    ),
                    source_ref=study["model_study_id"],
                    schema_ref="reviewed-boolean-v1",
                    schema_version="reviewed_boolean_v1",
                ),
            )
            for condition in contour.scenario_conditions
        )
        selected_agent = next(
            item for item in agent_refs if item.agent_id == packet["role_id"]
        )
        selected_capability = next(
            item
            for item in capability_refs
            if item.capability_id == route_policy["capability_id"]
        )
        decision = RouteDecision(
            decision_id=f"route-decision:model-study:{identity}",
            correlation_id=correlation_id,
            intent_ref=ContentRef(
                object_id=f"route-intent:model-study:{identity}",
                owner_repo="aoa-models",
                schema_version="aoa_model_study_v2",
                digest=study_ref.artifact_digest,
            ),
            status="resolved",
            candidates=(
                RouteCandidate(
                    candidate_id=f"route-candidate:model-study:{identity}",
                    capability=selected_capability,
                    agent=selected_agent,
                    scenario=scenario_ref,
                    rank=0,
                    compatibility="compatible",
                    policy_posture="eligible",
                    reason_codes=(
                        "fixed_landing_track_study_fixture",
                        "no_model_fit_claim",
                    ),
                    evidence_refs=(study_ref, packet_ref, manifest_ref),
                ),
            ),
            selected_candidate_id=f"route-candidate:model-study:{identity}",
            resolver_version="aoa_models_external_codex_study_preparer_v1",
            reason_codes=(
                "caller_fixed_exact_realization",
                "packaged_a2a_contour_used_as_transport_carrier",
            ),
            input_snapshot_digest=study_ref.artifact_digest,
            provenance=resolver_ref,
        )
        decision_ref = ContentRef(
            object_id=decision.decision_id,
            owner_repo=decision.provenance.owner_repo,
            schema_version=decision.schema_version,
            digest=canonical_digest(decision),
        )
        if contour.scenario == A2A_SCENARIO_ID:
            scenario_input_refs: tuple[ProvenanceRef, ...] = ()
            scenario_artifact_bindings = (
                ScenarioArtifactBinding(
                    artifact_kind="summon_request",
                    artifact_ref=summon_request_ref,
                ),
                ScenarioArtifactBinding(
                    artifact_kind="summon_decision",
                    artifact_ref=summon_decision_ref,
                ),
                ScenarioArtifactBinding(
                    artifact_kind="child_task_result", artifact_ref=child_result_ref
                ),
            )
        else:
            scenario_input_refs = (
                task_ref,
                study_ref,
                packet_ref,
                manifest_ref,
                summon_request_ref,
                summon_request_schema_ref,
                summon_decision_ref,
                summon_result_schema_ref,
                landing_effect_grant_schema_ref,
                workspace_manifest_schema_ref,
                legacy_workspace_manifest_evidence_schema_ref,
                legacy_workspace_manifest_owner_receipt_schema_ref,
            )
            scenario_artifact_bindings = ()
        scenario = ScenarioBinding(
            binding_id=f"scenario-binding:model-study:{identity}",
            correlation_id=correlation_id,
            scenario=scenario_ref,
            decision_ref=decision_ref,
            agent_refs=agent_refs,
            capability_refs=capability_refs,
            input_refs=scenario_input_refs,
            input_artifact_bindings=scenario_artifact_bindings,
            condition_bindings=condition_bindings,
            requirement_refs=requirement_refs,
            expected_artifact_kinds=contour.expected_artifact_kinds,
            provenance=_generated_ref(
                owner="abyss-stack",
                artifact_ref=(
                    f"runtime-studies/{study_token}/writers/{arm_id}/"
                    "scenario-binding.json"
                ),
                raw=_json_bytes(
                    {
                        "study": study["model_study_id"],
                        "arm_id": arm_id,
                        "admission_class": "transport_study_fixture",
                    }
                ),
                source_ref=study["model_study_id"],
                schema_ref="aoa_control_plane_v1",
                schema_version="aoa_control_plane_v1",
            ),
        )
        runtime_profile = load_abyss_stack_external_codex_runtime_profile(PROFILE_PATH)
        runtime_profile = runtime_profile.model_copy(
            update={
                "constraint_refs": (
                    study_ref,
                    packet_ref,
                    manifest_ref,
                    workspace_ref,
                    report_schema_ref,
                    controller_source_ref,
                    landing_effect_source_ref,
                    landing_effect_grant_schema_ref,
                    workspace_manifest_schema_ref,
                    legacy_workspace_manifest_evidence_schema_ref,
                    legacy_workspace_manifest_owner_receipt_schema_ref,
                    model_ref,
                    task_ref,
                    summon_request_ref,
                    summon_request_schema_ref,
                    summon_decision_ref,
                    summon_result_schema_ref,
                )
            }
        )
        plan = compile_run_plan(
            decision,
            scenario,
            runtime_profile,
            snapshot,
            compiler_provenance=compiler_ref,
        )
        plan_path = arm_root / "run-plan.json"
        _write_exact(plan_path, _json_bytes(plan.model_dump(mode="json")))

        stop_conditions = (
            IncarnationStopCondition(
                condition_id="authority-boundary",
                kind="authority_boundary",
                description="Stop before any owner or human authority decision.",
            ),
            IncarnationStopCondition(
                condition_id="scope-boundary",
                kind="scope_boundary",
                description="Stop when the fixed workspace or task scope is exceeded.",
            ),
            IncarnationStopCondition(
                condition_id="ambiguity",
                kind="ambiguity",
                description="Stop when owner meaning or safe interpretation is ambiguous.",
            ),
            IncarnationStopCondition(
                condition_id="validation-failure",
                kind="validation_failure",
                description=(
                    "Stop and preserve evidence when a fixed validation fails and "
                    "the bounded task cannot repair it safely."
                ),
            ),
            IncarnationStopCondition(
                condition_id="external-effect-required",
                kind="external_effect_required",
                description="Stop before commit, push, PR, merge, release, or publication.",
            ),
            IncarnationStopCondition(
                condition_id="runtime-failure",
                kind="runtime_failure",
                description="Preserve evidence on an unrecoverable runtime failure.",
            ),
        )
        wake_policy = WakeEscalationPolicy(
            default_action="stop",
            conditions=(
                WakeCondition(
                    condition_id="result-ready",
                    event_kind="result.validated",
                    action="activate_review_role",
                    description="A schema-valid writer result enters independent review.",
                ),
                WakeCondition(
                    condition_id="review-required",
                    event_kind="result.review_required",
                    action="activate_review_role",
                    description="A bounded review request enters a separate reviewer context.",
                ),
                WakeCondition(
                    condition_id="runtime-interrupted",
                    event_kind="runtime.interrupted",
                    action="continue_without_parent",
                    description="Resume the exact durable child thread without parent judgment.",
                ),
                WakeCondition(
                    condition_id="authority-needed",
                    event_kind="run.authority_required",
                    action="wake_parent",
                    description="Only an unresolved authority decision re-enters the parent level.",
                ),
                WakeCondition(
                    condition_id="result-failed",
                    event_kind="result.failed",
                    action="stop",
                    description="Preserve failure evidence for runtime and proof review.",
                ),
            ),
            escalation_conditions=("authority-needed",),
        )
        owner_scope = tuple(
            dict.fromkeys(
                [
                    *packet["authority_scope"],
                    "aoa-agents",
                    "aoa-models",
                    "aoa-sdk",
                    "aoa-playbooks",
                    "aoa-evals",
                    "abyss-stack",
                ]
            )
        )
        continuation = ContinuationObligation(
            continuation_id=continuation_id,
            parent_objective_ref=study_ref,
            established_decision_refs=(),
            delegated_obligation=(
                f"Carry one fixed-input {packet['task_family']} obligation under "
                f"the {packet['allowed_effect_class']} ceiling without owner "
                "acceptance or external effects."
            ),
            delegation_reason=(
                "The landing-track tail is bounded, repeatable, evidence-bearing, "
                "and suitable for a separate external-process study."
            ),
            exact_child_identity=incarnation_id,
            owner_scope=owner_scope,
            immutable_input_refs=(
                task_ref,
                study_ref,
                packet_ref,
                manifest_ref,
                controller_source_ref,
                landing_effect_source_ref,
                landing_effect_grant_schema_ref,
                workspace_manifest_schema_ref,
                legacy_workspace_manifest_evidence_schema_ref,
                legacy_workspace_manifest_owner_receipt_schema_ref,
                workspace_ref,
                model_ref,
                summon_request_ref,
                summon_request_schema_ref,
                summon_decision_ref,
                summon_result_schema_ref,
            ),
            expected_output=(
                f"One schema-valid {packet['task_family']} report plus runtime-owned "
                "process, usage, command, workspace, and wake evidence."
            ),
            validation_refs=(
                report_schema_ref,
                controller_source_ref,
                landing_effect_source_ref,
                landing_effect_grant_schema_ref,
                workspace_manifest_schema_ref,
                legacy_workspace_manifest_evidence_schema_ref,
                legacy_workspace_manifest_owner_receipt_schema_ref,
                packet_ref,
                manifest_ref,
                summon_request_schema_ref,
                summon_result_schema_ref,
            ),
            deferred_parent_decisions=(
                "Whether any finding changes architecture or owner meaning.",
                "Whether any source change is accepted, committed, pushed, or landed.",
                "Whether model fit or an effort level is admitted after aoa-evals review.",
            ),
            invariants=(
                "The user remains the sole human authority.",
                "No external effect is authorized.",
                (
                    "The packaged C2 contour is only a transport_study_fixture "
                    "carrier, not owner acceptance or activation."
                ),
                "One exact SDK v4 summon request and decision are digest/schema bound.",
                "Runtime completion is not model-fit proof or owner acceptance.",
            ),
            stop_condition_ids=tuple(item.condition_id for item in stop_conditions),
            wake_condition_ids=tuple(item.condition_id for item in wake_policy.conditions),
            return_owner=workspace_ref,
            rollback_reentry_anchor=workspace_ref,
        )
        matching_tool_entries = [
            item
            for item in load_json(PROFILE_PATH, label="runtime profile")["tool_profiles"]
            if item["profile_id"] == tool_profile_id
        ]
        if len(matching_tool_entries) != 1:
            raise StudyPreparationError(
                "model realization names no unique runtime tool profile"
            )
        tool_entry = matching_tool_entries[0]
        expected_sandbox = (
            "workspace_write"
            if packet["allowed_effect_class"] == "repo_mutation"
            else "read_only"
        )
        if (
            tool_entry["sandbox_mode"] != expected_sandbox
            or packet["allowed_effect_class"]
            not in tool_entry["allowed_effect_classes"]
        ):
            raise StudyPreparationError(
                "model realization tool profile differs from the packet effect route"
            )
        binding = build_agent_incarnation_binding(
            plan,
            binding_id=f"binding:model-study:{identity}",
            incarnation_id=incarnation_id,
            causation_id=f"causation:model-study:{identity}",
            trace_id=f"trace:model-study:{study_token}",
            task_request_ref=summon_request_ref,
            role_id=packet["role_id"],
            role_contract_ref=role_contract_ref,
            model_realization_ref=model_ref,
            workspace_source_ref=workspace_ref,
            permission_posture=IncarnationPermissionPosture(
                sandbox_mode=tool_entry["sandbox_mode"],
                approval_policy=tool_entry["approval_policy"],
                allowed_effect_classes=tuple(tool_entry["allowed_effect_classes"]),
                network_access=tool_entry["network_access"],
            ),
            tool_profile=IncarnationToolProfile(
                profile_id=tool_profile_id,
                profile_ref=plan.runtime_profile.provenance,
                required_tool_ids=required_tools,
                required_mcp_server_ids=tuple(
                    realization["configuration"]["tools"]["required_mcp_servers"]
                ),
            ),
            usage_metering=IncarnationUsageMetering(
                mode=packet["usage_metering"]["mode"],
                execution_limit_policy=packet["usage_metering"]["execution_limit_policy"],
                metering_regime=packet["usage_metering"]["metering_regime"],
                dimensions=tuple(packet["usage_metering"]["dimensions"]),
                cost_interpretation=packet["usage_metering"]["cost_interpretation"],
            ),
            stop_conditions=stop_conditions,
            expected_result_schema_ref=report_schema_ref,
            continuation=continuation,
            wake_policy=wake_policy,
            provenance=ProvenanceRef(
                owner_repo="aoa-sdk",
                artifact_ref=(
                    f"runtime-studies/{study_token}/writers/{arm_id}/"
                    "incarnation-binding.json"
                ),
                source_ref="aoa_agent_incarnation_binding_v1",
                artifact_digest=ZERO_DIGEST,
                schema_ref="schemas/agent-incarnation-binding.schema.json",
                schema_version="aoa_agent_incarnation_binding_v1",
            ),
        )
        binding_path = arm_root / "incarnation-binding.json"
        _write_exact(binding_path, _json_bytes(binding.model_dump(mode="json")))
        launch = {
            "schema_version": "abyss_stack_external_codex_launch_v1",
            "launch_id": f"launch:model-study:{identity}",
            "session_id": session_id,
            "admission_class": "transport_study_fixture",
            "plan": _artifact_coordinate(plan_path),
            "incarnation_binding": _artifact_coordinate(binding_path),
            "model_realization": _artifact_coordinate(realization_path),
            "task": _artifact_coordinate(task_path),
            "runtime_profile": _artifact_coordinate(PROFILE_PATH),
            "role_contract": _artifact_coordinate(role_contract_path),
            "result_schema": _artifact_coordinate(REPORT_SCHEMA_PATH),
            "workspace_path": str(workspace),
            "workspace_expected_head": workspace_head,
            "workspace_initial_posture": "exact_baseline",
            "workspace_manifest_input_id": "workspace-manifest",
            "codex_executable": str(codex_executable),
            "codex_executable_digest": _file_digest(codex_executable),
            "runtime_package": runtime_package,
            "codex_home": str(codex_home),
            "environment_allowlist": [
                "HOME",
                "LANG",
                "LC_ALL",
                "PATH",
                "SSL_CERT_FILE",
                "SSL_CERT_DIR",
                "TERM",
            ],
        }
        launch_path = arm_root / "launch.json"
        launch_raw = _json_bytes(launch)
        _write_exact(launch_path, launch_raw)
        preparation_arms.append(
            {
                "arm_id": arm_id,
                "model_realization_ref": realization_relative,
                "model_slug": model_slug,
                "reasoning_effort": effort,
                "task_id": task_id,
                "incarnation_id": incarnation_id,
                "session_id": session_id,
                "task_path": str(task_path),
                "summon_request_path": str(summon_request_path),
                "summon_request_digest": summon_request_ref.artifact_digest,
                "summon_request_schema_path": str(summon_request_schema_path),
                "summon_request_schema_digest": (
                    summon_request_schema_ref.artifact_digest
                ),
                "summon_decision_path": str(summon_decision_path),
                "summon_decision_digest": summon_decision_ref.artifact_digest,
                "summon_result_schema_path": str(summon_result_schema_path),
                "summon_result_schema_digest": (
                    summon_result_schema_ref.artifact_digest
                ),
                "plan_path": str(plan_path),
                "incarnation_binding_path": str(binding_path),
                "launch_path": str(launch_path),
                "launch_digest": sha256_bytes(launch_raw),
            }
        )

    sdk_import_coordinates = _aoa_sdk_import_coordinates(aoa_sdk_root)
    if len(semantic_digests) != 1:
        raise StudyPreparationError("writer arms do not preserve one task semantic digest")
    preparation = {
        "schema_version": "abyss_stack_external_codex_study_preparation_v1",
        "model_study_id": study["model_study_id"],
        "admission_class": "transport_study_fixture",
        "workspace_path": str(workspace),
        "workspace_head": workspace_head,
        "workspace_manifest_path": str(manifest_path),
        "workspace_manifest_digest": manifest_ref.artifact_digest,
        "study_path": str(study_path),
        "study_digest": study_ref.artifact_digest,
        "study_packet_path": str(packet_path),
        "study_packet_digest": packet_ref.artifact_digest,
        "task_semantic_digest": next(iter(semantic_digests)),
        "state_root": str(state_root),
        "aoa_sdk_import_provenance": {
            "source_root": str(aoa_sdk_root),
            "expected_package_root": str(aoa_sdk_root / "src" / "aoa_sdk"),
            "capture_point": "after_all_writer_plan_and_binding_compilation",
            "coordinates": list(sdk_import_coordinates),
        },
        "arms": preparation_arms,
        "fixed_invariants": [
            "Only model realization, effort, and identity fields differ across writer arms.",
            "All arms use one exact workspace, study packet, role contract, rubric, and observe-only metering policy.",
            "Every arm binds one canonical aoa-sdk summon-request-v4 and schema-valid summon decision by exact digest.",
            "No token, wall-time, turn, output, or cost ceiling is imposed by the study or runtime.",
            "All launches are transport_study_fixture and forbid external effects.",
            (
                f"The packaged {contour.scenario} C2 contour is a transport carrier, "
                "not landing admission or owner acceptance."
            ),
            "No Codex process is started by this preparation operation.",
        ],
        "attribution_limits": study["attribution_limits"],
    }
    validate_json(
        preparation,
        PREPARATION_SCHEMA_PATH,
        label="external Codex study preparation",
    )
    preparation_path = output_root / "study-preparation.json"
    _write_exact(preparation_path, _json_bytes(preparation))
    return {
        "schema_version": "abyss_stack_external_codex_study_preparation_response_v1",
        "prepared": True,
        "started": False,
        "preparation_path": str(preparation_path),
        "preparation_digest": _file_digest(preparation_path),
        "arm_count": len(preparation_arms),
        "state_root": str(state_root),
    }


def _prepare_reviewer(args: argparse.Namespace) -> dict[str, Any]:
    writer_launch_path = Path(args.writer_launch).resolve()
    writer_result_path = Path(args.writer_result).resolve()
    output_root = Path(args.output_root).resolve()
    state_root = Path(args.state_root).resolve()
    aoa_sdk_root = Path(args.aoa_sdk_root).resolve()
    review_instance_id = str(
        getattr(args, "review_instance_id", "initial") or "initial"
    )
    if (
        len(review_instance_id) > 80
        or not review_instance_id.isascii()
        or any(
            not (character.isalnum() or character in "._-")
            for character in review_instance_id
        )
    ):
        raise StudyPreparationError(
            "review instance id must use 1-80 ASCII letters, digits, dot, dash, or underscore"
        )
    _assert_aoa_sdk_import_root(aoa_sdk_root)
    (
        summon_request_schema_path,
        summon_request_schema_ref,
        summon_result_schema_path,
        summon_result_schema_ref,
    ) = _sdk_a2a_schema_refs(aoa_sdk_root)
    if (
        not writer_launch_path.is_file()
        or writer_launch_path.is_symlink()
        or not writer_result_path.is_file()
        or writer_result_path.is_symlink()
    ):
        raise StudyPreparationError("writer launch or result is unavailable")

    writer_launch = load_json(writer_launch_path, label="writer launch")
    writer_admission_class = writer_launch.get("admission_class")
    if writer_admission_class not in {
        "transport_study_fixture",
        "owner_contour",
    }:
        raise StudyPreparationError(
            "review preparation accepts only a transport-study or owner-contour writer"
        )
    validate_json(writer_launch, LAUNCH_SCHEMA_PATH, label="writer launch")
    coordinate_paths = {
        key: _verified_launch_coordinate(writer_launch, key)
        for key in (
            "plan",
            "incarnation_binding",
            "model_realization",
            "task",
            "runtime_profile",
            "role_contract",
            "result_schema",
        )
    }
    runtime_profile_path = coordinate_paths["runtime_profile"]
    writer_result = load_json(writer_result_path, label="writer runtime result")
    validate_json(writer_result, RESULT_SCHEMA_PATH, label="writer runtime result")
    if writer_result.get("admission_class") != writer_admission_class:
        raise StudyPreparationError(
            "writer launch and result admission classes differ"
        )
    writer_state_path = writer_result_path.parent / "state.json"
    if (
        writer_result_path.name != "result.json"
        or not writer_state_path.is_file()
        or writer_state_path.is_symlink()
    ):
        raise StudyPreparationError(
            "writer result is not bound to canonical durable runtime state"
        )
    writer_state = load_json(writer_state_path, label="writer runtime state")
    validate_json(writer_state, STATE_SCHEMA_PATH, label="writer runtime state")
    writer_result_digest = _file_digest(writer_result_path)
    if (
        writer_state.get("schema_version") not in PROJECTION_STATE_SCHEMA_VERSIONS
        or writer_state.get("session_id") != writer_result.get("session_id")
        or writer_state.get("launch_id") != writer_launch.get("launch_id")
        or writer_state.get("launch_digest") != _file_digest(writer_launch_path)
        or writer_state.get("admission_class") != writer_admission_class
        or writer_state.get("status") != writer_result.get("status")
        or writer_state.get("result_path") != str(writer_result_path)
        or writer_state.get("result_digest") != writer_result_digest
        or writer_state.get("active_attempt_id") is not None
        or writer_state.get("finished_at") != writer_result.get("finished_at")
    ):
        raise StudyPreparationError(
            "writer result differs from its canonical durable runtime state"
        )
    writer_state_root = writer_state_path.parents[2]
    try:
        bound_writer_result = ExternalCodexRuntime(writer_state_root).result(
            str(writer_result["session_id"])
        )
    except ExternalCodexRuntimeError as exc:
        raise StudyPreparationError(
            "writer owner admission binding differs from canonical durable runtime state"
        ) from exc
    if bound_writer_result != writer_result:
        raise StudyPreparationError(
            "writer result differs from the runtime-validated canonical result"
        )
    workspace = Path(str(writer_state["workspace_path"]))
    if not workspace.is_absolute():
        raise StudyPreparationError("writer historical workspace coordinate is not absolute")
    for target in (output_root, state_root):
        try:
            target.relative_to(workspace)
        except ValueError:
            pass
        else:
            raise StudyPreparationError(
                "review output/state roots must stay outside the historical workspace coordinate"
            )
    if (
        writer_result.get("session_id") != writer_launch["session_id"]
        or writer_result.get("status") not in {"completed", "review_required"}
        or writer_result.get("failure_code") is not None
        or not isinstance(writer_result.get("thread_id"), str)
        or not writer_result["thread_id"]
    ):
        raise StudyPreparationError(
            "writer result is not an accepted terminal input to independent review"
        )

    base_plan = RunPlan.model_validate(
        load_json(coordinate_paths["plan"], label="writer run plan")
    )
    base_binding_payload = load_json(
        coordinate_paths["incarnation_binding"],
        label="writer incarnation binding",
    )
    binding_type = (
        AgentIncarnationBindingV2
        if base_binding_payload.get("schema_version")
        == "aoa_agent_incarnation_binding_v2"
        else AgentIncarnationBinding
    )
    base_binding = binding_type.model_validate(base_binding_payload)
    assert_agent_incarnation_binding_matches_plan(base_binding, base_plan)
    writer_task = load_json(coordinate_paths["task"], label="writer task")
    validate_json(writer_task, TASK_SCHEMA_PATH, label="writer task")
    writer_task_family = str(writer_task["task_family"])
    reviewer_task_family, reviewer_output_kind = _reviewer_semantics(
        writer_task_family
    )
    writer_effect_class = str(writer_task.get("allowed_effect_class"))
    expected_writer_sandbox = {
        "read_only": "read_only",
        "repo_mutation": "workspace_write",
    }.get(writer_effect_class)
    if (
        expected_writer_sandbox is None
        or base_binding.permission_posture.sandbox_mode != expected_writer_sandbox
        or writer_result.get("incarnation_id") != base_binding.incarnation_id
        or writer_result.get("task_id") != writer_task["task_id"]
    ):
        raise StudyPreparationError(
            "writer task, effect posture, incarnation, or result identity is invalid"
        )

    report_ref = writer_result.get("report_ref")
    if not isinstance(report_ref, dict):
        raise StudyPreparationError("writer result report reference is unavailable")
    writer_report_path = Path(str(report_ref.get("artifact_ref", "")))
    if (
        not writer_report_path.is_absolute()
        or not writer_report_path.is_file()
        or writer_report_path.is_symlink()
        or _file_digest(writer_report_path) != report_ref.get("artifact_digest")
    ):
        raise StudyPreparationError("writer model report bytes are unavailable or changed")
    writer_report = load_json(writer_report_path, label="writer model report")
    validate_json(writer_report, REPORT_SCHEMA_PATH, label="writer model report")
    if (
        writer_report.get("task_id") != writer_task["task_id"]
        or writer_report.get("incarnation_id") != base_binding.incarnation_id
        or writer_report.get("status") != writer_result["status"]
    ):
        raise StudyPreparationError("writer result and model report identities differ")

    writer_workspace_ref = writer_result.get("workspace_manifest_ref")
    writer_actor_final_ref = writer_result.get("actor_final_manifest_ref")
    if not isinstance(writer_actor_final_ref, dict):
        writer_actor_final_ref = writer_workspace_ref
    writer_actor_delta_ref = writer_result.get("actor_delta_ref")
    if not isinstance(writer_workspace_ref, dict) or not isinstance(
        writer_actor_final_ref, dict
    ) or not isinstance(writer_actor_delta_ref, dict):
        raise StudyPreparationError(
            "writer result has no exact actor final manifest and delta references"
        )
    writer_workspace_manifest_path = Path(
        str(writer_actor_final_ref.get("artifact_ref", ""))
    )
    if (
        not writer_workspace_manifest_path.is_absolute()
        or not writer_workspace_manifest_path.is_file()
        or writer_workspace_manifest_path.is_symlink()
        or _file_digest(writer_workspace_manifest_path)
        != writer_actor_final_ref.get("artifact_digest")
    ):
        raise StudyPreparationError(
            "writer final actor manifest bytes are unavailable or changed"
        )
    writer_final_manifest = load_json(
        writer_workspace_manifest_path,
        label="writer final actor manifest",
    )
    validate_json(
        writer_final_manifest,
        ACTOR_MANIFEST_SCHEMA_PATH,
        label="writer final actor manifest",
    )
    writer_actor_delta_path = Path(str(writer_actor_delta_ref.get("artifact_ref", "")))
    if (
        not writer_actor_delta_path.is_absolute()
        or not writer_actor_delta_path.is_file()
        or writer_actor_delta_path.is_symlink()
        or _file_digest(writer_actor_delta_path)
        != writer_actor_delta_ref.get("artifact_digest")
    ):
        raise StudyPreparationError(
            "writer actor delta bytes are unavailable or changed"
        )
    writer_actor_delta = load_json(
        writer_actor_delta_path,
        label="writer actor delta",
    )
    validate_json(writer_actor_delta, ACTOR_DELTA_SCHEMA_PATH, label="writer actor delta")
    writer_review_seal_ref = writer_result.get("review_seal_ref")
    writer_review_seal: dict[str, Any] | None = None
    if isinstance(writer_review_seal_ref, dict):
        writer_review_seal_path = Path(
            str(writer_review_seal_ref.get("artifact_ref", ""))
        )
        if (
            not writer_review_seal_path.is_absolute()
            or not writer_review_seal_path.is_file()
            or writer_review_seal_path.is_symlink()
            or _file_digest(writer_review_seal_path)
            != writer_review_seal_ref.get("artifact_digest")
        ):
            raise StudyPreparationError(
                "writer review-state seal bytes are unavailable or changed"
            )
        writer_review_seal = load_json(
            writer_review_seal_path,
            label="writer review-state seal",
        )
        validate_json(
            writer_review_seal,
            REVIEW_STATE_SEAL_SCHEMA_PATH,
            label="writer review-state seal",
        )
        if (
            writer_review_seal_path.name != "review-state-seal.json"
            or Path(str(writer_actor_final_ref.get("artifact_ref")))
            != writer_review_seal_path.parent
            / str(writer_review_seal["manifest_path"])
            or Path(str(writer_actor_delta_ref.get("artifact_ref")))
            != writer_review_seal_path.parent
            / str(writer_review_seal["delta_path"])
        ):
            raise StudyPreparationError(
                "writer actor evidence is not bound into its review-state seal"
            )
        try:
            verify_review_state_seal(
                writer_review_seal_path.parent,
                expected_manifest=writer_final_manifest,
                expected_delta=writer_actor_delta,
                expected_session_id=str(writer_result["session_id"]),
                expected_incarnation_id=str(writer_result["incarnation_id"]),
                expected_status=str(writer_result["status"]),
            )
        except Exception as exc:
            raise StudyPreparationError(
                "writer review-state seal failed independent verification"
            ) from exc
    writer_actor_final_provenance = _file_ref(
        owner="abyss-stack",
        artifact_ref=str(writer_workspace_manifest_path),
        path=writer_workspace_manifest_path,
        source_ref=writer_result_digest,
        schema_ref=ACTOR_MANIFEST_SCHEMA_REF,
        schema_version="abyss_stack_external_codex_actor_workspace_manifest_v2",
    )
    writer_actor_delta_provenance = _file_ref(
        owner="abyss-stack",
        artifact_ref=str(writer_actor_delta_path),
        path=writer_actor_delta_path,
        source_ref=writer_result_digest,
        schema_ref=ACTOR_DELTA_SCHEMA_REF,
        schema_version="abyss_stack_external_codex_actor_delta_v1",
    )
    writer_projection_path = Path(str(writer_state.get("actor_projection_path", "")))
    expected_projection_path = (
        str(writer_review_seal["projection_path"])
        if writer_review_seal is not None
        else str(writer_projection_path)
    )
    if (
        not writer_projection_path.is_absolute()
        or (
            writer_review_seal is None
            and (
                writer_projection_path.is_symlink()
                or not writer_projection_path.is_dir()
            )
        )
        or writer_final_manifest.get("workspace_path") != expected_projection_path
        or writer_actor_delta.get("final_manifest_digest")
        != sha256_bytes(
            json.dumps(
                writer_final_manifest,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    ):
        raise StudyPreparationError(
            "writer actor projection is not bound to its exact final manifest and delta"
        )

    reviewer_role_arg = getattr(args, "reviewer_role_contract", None)
    reviewer_realization_arg = getattr(args, "reviewer_model_realization", None)
    if bool(reviewer_role_arg) != bool(reviewer_realization_arg):
        raise StudyPreparationError(
            "reviewer role contract and model realization must be supplied together"
        )
    if writer_effect_class == "repo_mutation":
        if not reviewer_role_arg or not reviewer_realization_arg:
            raise StudyPreparationError(
                "repo-mutation review requires an explicit read-only reviewer role and realization"
            )
        reviewer_role_path = Path(str(reviewer_role_arg)).resolve()
        reviewer_realization_path = Path(str(reviewer_realization_arg)).resolve()
        for label, path in (
            ("reviewer role contract", reviewer_role_path),
            ("reviewer model realization", reviewer_realization_path),
        ):
            if not path.is_file() or path.is_symlink():
                raise StudyPreparationError(f"{label} is unavailable")
        reviewer_role_relative = _owner_relative_from_named_root(
            reviewer_role_path, "aoa-agents"
        )
        reviewer_agents = [
            item
            for item in base_plan.scenario_binding.agent_refs
            if item.agent_id == "reviewer"
            and item.provenance.artifact_ref == reviewer_role_relative
            and item.provenance.artifact_digest == _file_digest(reviewer_role_path)
        ]
        if len(reviewer_agents) != 1:
            raise StudyPreparationError(
                "explicit reviewer role does not match one exact plan-bound aoa-agents ref"
            )
        reviewer_role_ref = reviewer_agents[0].provenance
        reviewer_realization_relative = _owner_relative_from_named_root(
            reviewer_realization_path, "aoa-models"
        )
        reviewer_model_ref = load_model_realization_ref(
            reviewer_realization_path,
            artifact_ref=reviewer_realization_relative,
            source_ref=(
                "uncommitted-owner-source@"
                f"{_file_digest(reviewer_realization_path)}"
            ),
        )
    else:
        if reviewer_role_arg or reviewer_realization_arg:
            raise StudyPreparationError(
                "read-only writer review reuses its already-bound reviewer realization"
            )
        if base_binding.role_id != "reviewer":
            raise StudyPreparationError(
                "read-only writer must already carry one exact reviewer role"
            )
        reviewer_role_path = coordinate_paths["role_contract"]
        reviewer_role_ref = base_binding.role_contract_ref
        reviewer_realization_path = coordinate_paths["model_realization"]
        reviewer_model_ref = base_binding.model_realization_ref

    writer_realization = load_json(
        coordinate_paths["model_realization"], label="writer model realization"
    )
    reviewer_realization = load_json(
        reviewer_realization_path, label="reviewer model realization"
    )
    writer_configuration = writer_realization.get("configuration")
    reviewer_configuration = reviewer_realization.get("configuration")
    if not isinstance(writer_configuration, dict) or not isinstance(
        reviewer_configuration, dict
    ):
        raise StudyPreparationError("writer or reviewer model configuration is invalid")
    for key in ("access", "runtime", "reasoning_effort"):
        if reviewer_configuration.get(key) != writer_configuration.get(key):
            raise StudyPreparationError(
                "reviewer realization must preserve writer provider, runtime, model, and effort"
            )
    reviewer_tools = reviewer_configuration.get("tools")
    reviewer_permissions = reviewer_configuration.get("permissions")
    if (
        not isinstance(reviewer_tools, dict)
        or not isinstance(reviewer_permissions, dict)
        or reviewer_permissions.get("sandbox_mode") != "read-only"
        or reviewer_permissions.get("approval_policy") != "never"
        or reviewer_permissions.get("network_access") != "disabled"
        or reviewer_permissions.get("external_effects") is not False
        or reviewer_tools.get("required_tools") != ["shell-read"]
        or reviewer_tools.get("required_mcp_servers") != []
        or reviewer_tools.get("inheritance_allowed") is not False
    ):
        raise StudyPreparationError(
            "reviewer realization is not the explicit read-only no-external-effect contour"
        )
    reviewer_tool_profile_id = str(reviewer_tools.get("profile_ref", ""))
    runtime_profile_payload = load_json(runtime_profile_path, label="runtime profile")
    reviewer_runtime_profile = load_abyss_stack_external_codex_runtime_profile(
        runtime_profile_path
    )
    reviewer_tool_entries = [
        item
        for item in runtime_profile_payload["tool_profiles"]
        if item["profile_id"] == reviewer_tool_profile_id
    ]
    if len(reviewer_tool_entries) != 1:
        raise StudyPreparationError(
            "reviewer realization names no unique runtime tool profile"
        )
    reviewer_tool_entry = reviewer_tool_entries[0]
    if (
        reviewer_tool_entry["sandbox_mode"] != "read_only"
        or reviewer_tool_entry["allowed_effect_classes"] != ["read_only"]
        or reviewer_tool_entry["network_access"] != "disabled"
        or reviewer_tool_entry["external_effects"] is not False
    ):
        raise StudyPreparationError(
            "reviewer runtime tool profile exceeds the read-only review boundary"
        )

    forwarded_inputs: list[dict[str, Any]] = []
    forwarded_ids: set[str] = set()
    manifest_input: tuple[Path, ProvenanceRef] | None = None
    writer_summon_input: tuple[Path, ProvenanceRef] | None = None
    writer_summon_schema_input: tuple[Path, ProvenanceRef] | None = None
    writer_summon_decision_input: tuple[Path, ProvenanceRef] | None = None
    controller_derived_refs: list[ProvenanceRef] = []
    writer_schema_recovered = False
    writer_manifest_input_id = str(writer_launch["workspace_manifest_input_id"])
    reserved_ids = {
        "review-summon-request",
        "review-workspace-manifest",
        "writer-runtime-result",
        "writer-model-report",
        "writer-actor-final-manifest",
        "writer-actor-delta",
        "writer-review-state-seal",
        "writer-source-baseline-manifest",
        "writer-summon-request-schema",
    }
    if writer_manifest_input_id in reserved_ids:
        raise StudyPreparationError(
            "writer manifest input id collides with reviewer evidence ids"
        )
    controller_inputs = writer_state.get("controller_materialized_task_inputs")
    if not isinstance(controller_inputs, list):
        raise StudyPreparationError(
            "writer has no durable controller-owned immutable input set"
        )
    for item in writer_task["immutable_inputs"]:
        input_id = str(item["input_id"])
        if input_id in reserved_ids or input_id in forwarded_ids:
            raise StudyPreparationError(
                "writer immutable input ids collide with reviewer evidence ids"
            )
        provenance = ProvenanceRef.model_validate(item["provenance"])
        controller_matches = [
            candidate
            for candidate in controller_inputs
            if candidate.get("input_id") == input_id
        ]
        if len(controller_matches) != 1:
            raise StudyPreparationError(
                f"writer has no unique durable controller input: {input_id}"
            )
        controller_input = controller_matches[0]
        path = Path(str(controller_input.get("path", "")))
        if (
            not path.is_absolute()
            or not path.is_file()
            or path.is_symlink()
            or controller_input.get("provenance") != item["provenance"]
            or _file_digest(path) != provenance.artifact_digest
        ):
            raise StudyPreparationError(
                f"writer immutable input changed before review: {input_id}"
            )
        forwarded_ids.add(input_id)
        forwarded_item = dict(item)
        forwarded_item["local_path"] = str(path)
        forwarded_inputs.append(forwarded_item)
        if input_id == writer_manifest_input_id:
            manifest_input = (path, provenance)
        elif input_id == "summon-request":
            writer_summon_input = (path, provenance)
        elif input_id == "summon-request-schema":
            writer_summon_schema_input = (path, provenance)
        elif input_id == "summon-decision":
            writer_summon_decision_input = (path, provenance)
    if writer_summon_input is None:
        raise StudyPreparationError(
            "writer has no exact canonical SDK v4 summon request input"
        )
    writer_summon_path, writer_summon_ref = writer_summon_input
    if manifest_input is None:
        if writer_admission_class != "owner_contour":
            raise StudyPreparationError(
                "writer has no exact selected workspace manifest input"
            )
        source_before_ref = writer_state.get("source_manifest_before_ref")
        source_before_path = writer_state_path.parent / "source-manifest-before.json"
        source_before_digest = (
            source_before_ref.get("artifact_digest")
            if isinstance(source_before_ref, dict)
            else None
        )
        if (
            source_before_ref != writer_result.get("source_manifest_before_ref")
            or not isinstance(source_before_ref, dict)
            or source_before_ref.get("owner_repo") != "abyss-stack"
            or source_before_ref.get("artifact_ref") != str(source_before_path)
            or not source_before_path.is_file()
            or source_before_path.is_symlink()
            or _file_digest(source_before_path) != source_before_digest
        ):
            raise StudyPreparationError(
                "owner-contour writer source baseline is unavailable or changed"
            )
        source_before = load_json(
            source_before_path,
            label="owner-contour writer source baseline",
        )
        validate_json(
            source_before,
            WORKSPACE_MANIFEST_SCHEMA_PATH,
            label="owner-contour writer source baseline",
        )
        if source_before != writer_state.get("workspace_manifest_baseline"):
            raise StudyPreparationError(
                "owner-contour writer source baseline differs from durable state"
            )
        recovered_manifest_path = (
            output_root / "writer-source-baseline-manifest.json"
        )
        _write_exact(recovered_manifest_path, source_before_path.read_bytes())
        recovered_manifest_ref = _file_ref(
            owner="abyss-stack",
            artifact_ref=str(recovered_manifest_path),
            path=recovered_manifest_path,
            source_ref=writer_result_digest,
            schema_ref=WORKSPACE_MANIFEST_SCHEMA_REF,
            schema_version="abyss_stack_external_codex_workspace_manifest_v1",
        )
        manifest_input = (recovered_manifest_path, recovered_manifest_ref)
        forwarded_ids.add("writer-source-baseline-manifest")
        forwarded_inputs.append(
            {
                "input_id": "writer-source-baseline-manifest",
                "local_path": str(recovered_manifest_path),
                "provenance": recovered_manifest_ref.model_dump(mode="json"),
            }
        )
        controller_derived_refs.append(recovered_manifest_ref)
    if writer_summon_schema_input is None:
        if writer_admission_class != "owner_contour":
            raise StudyPreparationError(
                "writer has no exact canonical SDK v4 summon request/schema inputs"
            )
        if (
            writer_summon_ref.schema_ref
            != summon_request_schema_ref.artifact_ref
            or writer_summon_ref.schema_version
            != SDK_SUMMON_REQUEST_SCHEMA_VERSION
        ):
            raise StudyPreparationError(
                "owner-contour writer request does not name the selected SDK v4 schema"
            )
        recovered_schema_path = output_root / "writer-summon-request-schema.json"
        _write_exact(recovered_schema_path, summon_request_schema_path.read_bytes())
        recovered_schema_ref = _file_ref(
            owner="abyss-stack",
            artifact_ref=str(recovered_schema_path),
            path=recovered_schema_path,
            source_ref=writer_result_digest,
            schema_ref=summon_request_schema_ref.artifact_ref,
            schema_version=SDK_SUMMON_REQUEST_SCHEMA_VERSION,
        )
        writer_summon_schema_input = (
            recovered_schema_path,
            recovered_schema_ref,
        )
        writer_schema_recovered = True
        forwarded_ids.add("writer-summon-request-schema")
        forwarded_inputs.append(
            {
                "input_id": "writer-summon-request-schema",
                "local_path": str(recovered_schema_path),
                "provenance": recovered_schema_ref.model_dump(mode="json"),
            }
        )
        controller_derived_refs.append(recovered_schema_ref)
    writer_summon_schema_path, writer_summon_schema_ref = (
        writer_summon_schema_input
    )
    if (
        (
            not writer_schema_recovered
            and writer_summon_schema_ref != summon_request_schema_ref
        )
        or _file_digest(writer_summon_schema_path)
        != summon_request_schema_ref.artifact_digest
        or (
            writer_schema_recovered
            and (
                writer_summon_schema_ref.schema_ref
                != summon_request_schema_ref.artifact_ref
                or writer_summon_schema_ref.schema_version
                != SDK_SUMMON_REQUEST_SCHEMA_VERSION
            )
        )
        or writer_summon_ref.schema_ref
        != summon_request_schema_ref.artifact_ref
        or writer_summon_ref.schema_version
        != SDK_SUMMON_REQUEST_SCHEMA_VERSION
    ):
        raise StudyPreparationError(
            "writer summon request is not bound to the selected exact SDK v4 schema"
        )
    writer_summon_request = load_json(
        writer_summon_path,
        label="writer canonical summon request",
    )
    validate_json(
        writer_summon_request,
        writer_summon_schema_path,
        label="writer canonical summon request",
    )
    writer_request_capability_ids = writer_summon_request.get(
        "summon_request", {}
    ).get("capability_refs")
    if (
        not isinstance(writer_request_capability_ids, list)
        or not writer_request_capability_ids
        or any(
            not isinstance(item, str) or not item
            for item in writer_request_capability_ids
        )
    ):
        raise StudyPreparationError(
            "writer canonical summon request has no exact capability identity"
        )
    existing_reviewer_capabilities = tuple(
        item
        for item in base_plan.scenario_binding.capability_refs
        if item.capability_id in writer_request_capability_ids
    )
    reviewer_capability_ref = _reviewer_capability_ref(
        reviewer_role_path,
        owner_source_ref=reviewer_role_ref.source_ref,
        existing_plan_refs=existing_reviewer_capabilities,
    )
    writer_summon_decision_ref = _writer_summon_decision_ref(
        plan=base_plan,
        task_request_ref=base_binding.task_request_ref,
        writer_summon_ref=writer_summon_ref,
        allow_mixed_binding=writer_admission_class == "owner_contour",
    )
    writer_uses_mixed_summon_binding = (
        writer_admission_class == "owner_contour"
        and not any(
            item.artifact_kind == "summon_decision"
            for item in base_plan.scenario_binding.input_artifact_bindings
        )
    )
    if writer_uses_mixed_summon_binding and (
        writer_summon_decision_input is None
        or writer_summon_decision_input[1] != writer_summon_decision_ref
        or writer_summon_decision_ref not in base_plan.snapshot.source_refs
        or writer_summon_decision_ref
        not in base_binding.continuation.immutable_input_refs
    ):
        raise StudyPreparationError(
            "owner-contour writer mixed summon decision is not exact task, snapshot, and continuation evidence"
        )
    writer_task_refs = [
        item
        for item in base_plan.runtime_profile.constraint_refs
        if item.artifact_digest == writer_launch["task"]["digest"]
        and item.schema_version == "abyss_stack_external_codex_task_v1"
    ]
    if (
        base_binding.task_request_ref != writer_summon_ref
        or len(writer_task_refs) != 1
        or writer_task_refs[0] not in base_plan.snapshot.source_refs
        or writer_task_refs[0]
        not in base_binding.continuation.immutable_input_refs
    ):
        raise StudyPreparationError(
            "writer binding does not separate the typed summon request from one exact task constraint"
        )
    writer_task_ref = writer_task_refs[0]
    manifest_path, manifest_ref = manifest_input
    manifest = load_json(manifest_path, label="writer workspace manifest")
    validate_json(
        manifest,
        WORKSPACE_MANIFEST_SCHEMA_PATH,
        label="writer baseline workspace manifest",
    )
    if (
        manifest.get("workspace_path") != str(workspace)
        or manifest.get("git_head") != writer_launch["workspace_expected_head"]
    ):
        raise StudyPreparationError(
            "writer baseline workspace manifest names another workspace or HEAD"
        )
    observed_changed_paths = [
        {"path": str(item["path"]), "status": str(item["status"])}
        for item in writer_actor_delta["changes"]
    ]
    if observed_changed_paths != writer_result.get("changed_paths"):
        raise StudyPreparationError(
            "writer result changed-path receipt differs from its exact final manifest"
        )
    out_of_scope_paths = [
        item["path"]
        for item in observed_changed_paths
        if not _relative_path_is_allowed(
            item["path"], writer_task["allowed_paths"]
        )
    ]
    if out_of_scope_paths:
        raise StudyPreparationError(
            "writer final manifest contains paths outside its admitted task scope"
        )
    if writer_effect_class == "read_only":
        if (
            writer_result.get("workspace_manifest_match") is not True
            or observed_changed_paths
        ):
            raise StudyPreparationError(
                "read-only writer result is not an exact no-drift review input"
            )
    elif writer_result.get("workspace_manifest_match") != (not observed_changed_paths):
        raise StudyPreparationError(
            "repo-mutation writer actor manifest-match flag differs from exact delta"
        )

    review_manifest_path = output_root / "review-workspace-manifest.json"
    _write_exact(review_manifest_path, _json_bytes(manifest))
    review_manifest_ref = _file_ref(
        owner=writer_task["target_owner"],
        artifact_ref=str(review_manifest_path),
        path=review_manifest_path,
        source_ref=writer_result_digest,
        schema_ref=WORKSPACE_MANIFEST_SCHEMA_REF,
        schema_version="abyss_stack_external_codex_workspace_manifest_v1",
    )
    writer_actor_final_input = {
        "input_id": "writer-actor-final-manifest",
        "local_path": str(writer_workspace_manifest_path),
        "provenance": writer_actor_final_provenance.model_dump(mode="json"),
    }
    writer_actor_delta_input = {
        "input_id": "writer-actor-delta",
        "local_path": str(writer_actor_delta_path),
        "provenance": writer_actor_delta_provenance.model_dump(mode="json"),
    }
    writer_review_seal_input: dict[str, Any] | None = None
    writer_review_seal_provenance: ProvenanceRef | None = None
    if isinstance(writer_review_seal_ref, dict):
        writer_review_seal_path = Path(str(writer_review_seal_ref["artifact_ref"]))
        writer_review_seal_provenance = _file_ref(
            owner="abyss-stack",
            artifact_ref=str(writer_review_seal_path),
            path=writer_review_seal_path,
            source_ref=writer_result_digest,
            schema_ref=(
                "mechanics/governed-execution/parts/external-codex-agent/schemas/"
                "external-codex-review-state-seal.schema.json"
            ),
            schema_version="abyss_stack_external_codex_review_state_seal_v1",
        )
        writer_review_seal_input = {
            "input_id": "writer-review-state-seal",
            "local_path": str(writer_review_seal_path),
            "provenance": writer_review_seal_provenance.model_dump(mode="json"),
        }
    writer_review_seal_refs = (
        (writer_review_seal_provenance,)
        if writer_review_seal_provenance is not None
        else ()
    )

    writer_result_ref = _file_ref(
        owner="abyss-stack",
        artifact_ref=str(writer_result_path),
        path=writer_result_path,
        source_ref=writer_result["thread_id"],
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-result.schema.json"
        ),
        schema_version=str(writer_result["schema_version"]),
    )
    writer_report_ref = _file_ref(
        owner="abyss-stack",
        artifact_ref=str(writer_report_path),
        path=writer_report_path,
        source_ref=writer_result["thread_id"],
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-report.schema.json"
        ),
        schema_version="abyss_stack_external_codex_report_v1",
    )
    forwarded_inputs.extend(
        (
            {
                "input_id": "writer-runtime-result",
                "local_path": str(writer_result_path),
                "provenance": writer_result_ref.model_dump(mode="json"),
            },
            {
                "input_id": "writer-model-report",
                "local_path": str(writer_report_path),
                "provenance": writer_report_ref.model_dump(mode="json"),
            },
            {
                "input_id": "review-workspace-manifest",
                "local_path": str(review_manifest_path),
                "provenance": review_manifest_ref.model_dump(mode="json"),
            },
            writer_actor_final_input,
            writer_actor_delta_input,
            *(
                (writer_review_seal_input,)
                if writer_review_seal_input is not None
                else ()
            ),
        )
    )

    writer_identity_digest = _file_digest(writer_result_path).split(":", 1)[1]
    identity_token = writer_identity_digest[:20]
    if review_instance_id != "initial":
        identity_token = hashlib.sha256(
            f"{writer_identity_digest}\0{review_instance_id}".encode("utf-8")
        ).hexdigest()[:20]
    incarnation_id = (
        f"incarnation:model-study:{identity_token}:independent-reviewer"
    )
    continuation_id = (
        f"continuation:model-study:{identity_token}:independent-reviewer"
    )
    task_id = f"task:model-study:{identity_token}:independent-reviewer"
    session_id = f"session:model-study:{identity_token}:independent-reviewer"
    review_summon = _build_canonical_summon_artifacts(
        output_root=output_root,
        artifact_prefix=f"runtime-studies/{identity_token}/reviewer",
        source_ref=writer_result_ref.artifact_digest,
        request_schema_path=summon_request_schema_path,
        request_schema_ref=summon_request_schema_ref,
        result_schema_path=summon_result_schema_path,
        result_schema_ref=summon_result_schema_ref,
        difficulty="d2_slice",
        risk="r0_readonly",
        delegate_tier="verifier",
        route_anchor=writer_result_ref.artifact_digest,
        desired_role="reviewer",
        child_agent_id=incarnation_id,
        capability_refs=(reviewer_capability_ref.capability_id,),
        expected_outputs=(reviewer_output_kind,),
        parent_task_id=writer_task["task_id"],
        session_ref=session_id,
        audit_refs=(
            f"abyss-stack:{writer_result_ref.artifact_ref}@{writer_result_ref.artifact_digest}",
            f"abyss-stack:{writer_report_ref.artifact_ref}@{writer_report_ref.artifact_digest}",
            f"{writer_task['target_owner']}:{review_manifest_ref.artifact_ref}@{review_manifest_ref.artifact_digest}",
        ),
        playbook_ref=base_plan.scenario_binding.scenario.provenance.artifact_ref,
        review_required=False,
        workspace_root=workspace,
        reviewed_artifact_path=str(writer_result_path),
    )
    review_summon_request_path = review_summon["request_path"]
    review_summon_request_ref = review_summon["request_ref"]
    review_summon_decision_path = review_summon["decision_path"]
    review_summon_decision_ref = review_summon["decision_ref"]
    reviewer_inputs = [
        *forwarded_inputs,
        *(
            (
                {
                    "input_id": "summon-request-schema",
                    "local_path": str(summon_request_schema_path),
                    "provenance": summon_request_schema_ref.model_dump(mode="json"),
                },
            )
            if writer_schema_recovered
            else ()
        ),
        {
            "input_id": "review-summon-request",
            "local_path": str(review_summon_request_path),
            "provenance": review_summon_request_ref.model_dump(mode="json"),
        },
    ]
    task = {
        "schema_version": "abyss_stack_external_codex_task_v1",
        "task_id": task_id,
        "correlation_id": base_plan.correlation_id,
        "continuation_id": continuation_id,
        "expected_incarnation_id": incarnation_id,
        "task_family": reviewer_task_family,
        "execution_posture": "independent_review",
        "parent_task_id": writer_task["task_id"],
        "objective": (
            "Проведи независимый read-only review точного terminal writer result и "
            "model report. Не доверяй writer decision: самостоятельно проверь exact "
            "workspace source, весь закрепленный diff, owner boundaries, каждый "
            "finding/evidence anchor, все fixed validation events, severity, false "
            "positives/negatives, wake/authority discipline и достаточность перехода. "
            "Не ремонтируй source или report. Для source evidence используй только "
            "существующие anchored source: refs; для переданных артефактов используй "
            "stable immutable:<input-id>#Lx-Ly refs; validation evidence обязано быть "
            "runtime:validation:<command-id>. Если blocker подтвержден, верни "
            "review_required/return_for_repair с review-required/stop. Если blockers "
            "не осталось, верни completed/proceed с review-complete/stop. Только "
            "реальная unresolved owner authority может использовать "
            "authority-needed/wake_parent. artifact_paths оставь пустым; не заявляй "
            "owner acceptance, model fit, task completion или внешний effect."
        ),
        "transition": {
            "from_status": writer_report["transition"]["to_status"],
            "target_status": "independently_reviewed",
            "review_required_status": "review_required_source_repair",
            "approval_posture": "human_owner_and_aoa_evals_review_required",
            "rollback_reentry_route": (
                "preserve_writer_result_and_return_independent_review_evidence"
            ),
        },
        "target_owner": writer_task["target_owner"],
        "authority_scope": writer_task["authority_scope"],
        "allowed_effect_class": "read_only",
        "indirect_command_policy": "sandbox_confined",
        "allowed_paths": writer_task["allowed_paths"],
        "source_evidence_paths": writer_task.get(
            "source_evidence_paths", writer_task["allowed_paths"]
        ),
        "immutable_inputs": reviewer_inputs,
        "done_state": [
            "Writer findings are independently confirmed, weakened, or contradicted with exact evidence.",
            "Every fixed validation and every writer evidence ref is independently checked.",
            "False closure risk and an exact next route are named without source repair.",
            "The result preserves owner, proof, approval, and external-effect boundaries.",
        ],
        "validation_commands": writer_task["validation_commands"],
        "expected_artifacts": [
            "runtime-owned independent actor review; no workspace artifact"
        ],
        "forbidden_effects": writer_task["forbidden_effects"],
        "ambiguity_policy": "escalate",
        "review_required": False,
        "return_owner": writer_task["return_owner"],
    }
    task_raw = _json_bytes(task)
    task_path = output_root / "task.json"
    _write_exact(task_path, task_raw)
    task_ref = _generated_ref(
        owner=writer_task["target_owner"],
        artifact_ref=f"runtime-studies/{identity_token}/reviewer/task.json",
        raw=task_raw,
        source_ref=writer_result_ref.artifact_digest,
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-task.schema.json"
        ),
        schema_version="abyss_stack_external_codex_task_v1",
    )
    review_plan = _adapt_plan_for_reviewer(
        base_plan,
        reviewer_runtime_profile=reviewer_runtime_profile,
        reviewer_capability_ref=reviewer_capability_ref,
        writer_role_id=base_binding.role_id,
        reviewer_role_id="reviewer",
        reviewer_role_ref=reviewer_role_ref,
        old_task_ref=writer_task_ref,
        task_ref=task_ref,
        old_summon_request_ref=writer_summon_ref,
        review_summon_request_ref=review_summon_request_ref,
        old_summon_decision_ref=writer_summon_decision_ref,
        review_summon_decision_ref=review_summon_decision_ref,
        summon_request_schema_ref=summon_request_schema_ref,
        summon_result_schema_ref=summon_result_schema_ref,
        old_model_ref=base_binding.model_realization_ref,
        reviewer_model_ref=reviewer_model_ref,
        writer_result_ref=writer_result_ref,
        writer_report_ref=writer_report_ref,
        writer_actor_final_ref=writer_actor_final_provenance,
        writer_actor_delta_ref=writer_actor_delta_provenance,
        review_manifest_ref=review_manifest_ref,
        additional_input_refs=(
            *controller_derived_refs,
            *writer_review_seal_refs,
        ),
        identity_token=identity_token,
    )
    plan_path = output_root / "run-plan.json"
    _write_exact(plan_path, _json_bytes(review_plan.model_dump(mode="json")))

    result_schema_ref = _file_ref(
        owner="abyss-stack",
        artifact_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-report.schema.json"
        ),
        path=coordinate_paths["result_schema"],
        source_ref=_file_digest(coordinate_paths["result_schema"]),
        schema_ref="https://json-schema.org/draft/2020-12/schema",
        schema_version="abyss_stack_external_codex_report_v1",
    )
    stop_conditions = (
        IncarnationStopCondition(
            condition_id="authority-boundary",
            kind="authority_boundary",
            description="Stop before owner or human authority judgment.",
        ),
        IncarnationStopCondition(
            condition_id="scope-boundary",
            kind="scope_boundary",
            description="Stop when exact review scope would need to widen.",
        ),
        IncarnationStopCondition(
            condition_id="ambiguity",
            kind="ambiguity",
            description="Stop when owner meaning or safe interpretation is ambiguous.",
        ),
        IncarnationStopCondition(
            condition_id="external-effect-required",
            kind="external_effect_required",
            description="Stop before every external effect.",
        ),
        IncarnationStopCondition(
            condition_id="runtime-failure",
            kind="runtime_failure",
            description="Preserve exact evidence on unrecoverable runtime failure.",
        ),
    )
    wake_policy = WakeEscalationPolicy(
        default_action="stop",
        conditions=(
            WakeCondition(
                condition_id="review-complete",
                event_kind="result.validated",
                action="stop",
                description="Preserve a completed independent review without parent wake.",
            ),
            WakeCondition(
                condition_id="review-required",
                event_kind="result.review_required",
                action="stop",
                description="Preserve repair findings for the next bounded route.",
            ),
            WakeCondition(
                condition_id="runtime-interrupted",
                event_kind="runtime.interrupted",
                action="continue_without_parent",
                description="Resume the exact reviewer thread without parent judgment.",
            ),
            WakeCondition(
                condition_id="authority-needed",
                event_kind="run.authority_required",
                action="wake_parent",
                description="Only unresolved owner authority re-enters the parent.",
            ),
            WakeCondition(
                condition_id="review-failed",
                event_kind="result.failed",
                action="stop",
                description="Preserve failed review evidence without automatic re-entry.",
            ),
        ),
        escalation_conditions=("authority-needed",),
    )
    continuation_inputs = tuple(
        task_ref
        if item == writer_task_ref
        else reviewer_model_ref
        if item == base_binding.model_realization_ref
        else reviewer_runtime_profile.provenance
        if item == base_plan.runtime_profile.provenance
        else item
        for item in base_binding.continuation.immutable_input_refs
    )
    continuation_inputs = _append_unique_refs(
        continuation_inputs,
        writer_result_ref,
        writer_report_ref,
        writer_actor_final_provenance,
        writer_actor_delta_provenance,
        review_manifest_ref,
        review_summon_request_ref,
        review_summon_decision_ref,
        summon_request_schema_ref,
        summon_result_schema_ref,
        *writer_review_seal_refs,
        *controller_derived_refs,
    )
    continuation = ContinuationObligation(
        continuation_id=continuation_id,
        parent_objective_ref=writer_result_ref,
        established_decision_refs=base_binding.continuation.established_decision_refs,
        delegated_obligation="Independently review one exact terminal writer result.",
        delegation_reason=(
            "Writer and reviewer decisions require distinct process, session, and context identities."
        ),
        exact_child_identity=incarnation_id,
        owner_scope=base_binding.continuation.owner_scope,
        immutable_input_refs=continuation_inputs,
        expected_output="One evidence-bearing terminal independent landing review.",
        validation_refs=_append_unique_refs(
            base_binding.continuation.validation_refs,
            result_schema_ref,
            writer_result_ref,
            writer_report_ref,
            manifest_ref,
            review_manifest_ref,
            summon_request_schema_ref,
            summon_result_schema_ref,
            *writer_review_seal_refs,
        ),
        deferred_parent_decisions=(
            "Whether owner/eval evidence admits any model scope.",
            "Whether any repair or landing effect is accepted.",
        ),
        invariants=(
            "The reviewer cannot repair its own findings.",
            "Usage is measured without a predeclared execution limit.",
            "The user remains the sole human authority.",
            "No external effect is authorized.",
            "The active reviewer summon request is a distinct SDK v4 object.",
        ),
        stop_condition_ids=tuple(item.condition_id for item in stop_conditions),
        wake_condition_ids=tuple(item.condition_id for item in wake_policy.conditions),
        return_owner=base_binding.continuation.return_owner,
        rollback_reentry_anchor=writer_result_ref,
    )
    binding = build_agent_incarnation_binding(
        review_plan,
        binding_id=f"binding:model-study:{identity_token}:independent-reviewer",
        incarnation_id=incarnation_id,
        causation_id=f"causation:model-study:{identity_token}:independent-reviewer",
        trace_id=f"{base_binding.trace_id}:independent-reviewer",
        task_request_ref=review_summon_request_ref,
        role_id="reviewer",
        role_contract_ref=reviewer_role_ref,
        model_realization_ref=reviewer_model_ref,
        workspace_source_ref=base_binding.workspace_source_ref,
        permission_posture=IncarnationPermissionPosture(
            sandbox_mode="read_only",
            approval_policy=reviewer_tool_entry["approval_policy"],
            allowed_effect_classes=tuple(
                reviewer_tool_entry["allowed_effect_classes"]
            ),
            network_access=reviewer_tool_entry["network_access"],
        ),
        tool_profile=IncarnationToolProfile(
            profile_id=reviewer_tool_profile_id,
            profile_ref=review_plan.runtime_profile.provenance,
            required_tool_ids=tuple(reviewer_tools["required_tools"]),
            required_mcp_server_ids=tuple(
                reviewer_tools["required_mcp_servers"]
            ),
        ),
        usage_metering=base_binding.usage_metering,
        stop_conditions=stop_conditions,
        expected_result_schema_ref=result_schema_ref,
        continuation=continuation,
        wake_policy=wake_policy,
        provenance=ProvenanceRef(
            owner_repo="aoa-sdk",
            artifact_ref=(
                f"runtime-studies/{identity_token}/reviewer/incarnation-binding.json"
            ),
            source_ref="aoa_agent_incarnation_binding_v1",
            artifact_digest=ZERO_DIGEST,
            schema_ref="schemas/agent-incarnation-binding.schema.json",
            schema_version="aoa_agent_incarnation_binding_v1",
        ),
    )
    binding_path = output_root / "incarnation-binding.json"
    _write_exact(binding_path, _json_bytes(binding.model_dump(mode="json")))
    requested_state_root = Path(args.state_root).resolve()
    if requested_state_root != writer_state_root.resolve():
        raise StudyPreparationError(
            "reviewer must share the writer runtime state root so the controller can "
            "revalidate the terminal writer under its exact session lock"
        )
    review_seed_ref = ExternalCodexRuntime(writer_state_root).issue_review_seed(
        str(writer_result["session_id"])
    )
    launch = {
        "schema_version": "abyss_stack_external_codex_launch_v1",
        "launch_id": f"launch:model-study:{identity_token}:independent-reviewer",
        "session_id": session_id,
        "admission_class": "transport_study_fixture",
        "plan": _artifact_coordinate(plan_path),
        "incarnation_binding": _artifact_coordinate(binding_path),
        "model_realization": _artifact_coordinate(reviewer_realization_path),
        "task": _artifact_coordinate(task_path),
        "runtime_profile": _artifact_coordinate(runtime_profile_path),
        "role_contract": _artifact_coordinate(reviewer_role_path),
        "result_schema": writer_launch["result_schema"],
        "workspace_path": str(workspace),
        "workspace_expected_head": writer_launch["workspace_expected_head"],
        "workspace_initial_posture": "exact_baseline",
        "workspace_manifest_input_id": "review-workspace-manifest",
        "workspace_projection_seed": {
            "envelope_path": str(review_seed_ref["artifact_ref"]),
            "envelope_digest": str(review_seed_ref["artifact_digest"]),
        },
        "codex_executable": writer_launch["codex_executable"],
        "codex_executable_digest": writer_launch["codex_executable_digest"],
        "runtime_package": writer_launch["runtime_package"],
        "codex_home": writer_launch["codex_home"],
        "environment_allowlist": writer_launch["environment_allowlist"],
    }
    launch_path = output_root / "launch.json"
    launch_raw = _json_bytes(launch)
    _write_exact(launch_path, launch_raw)
    sdk_import_coordinates = _aoa_sdk_import_coordinates(aoa_sdk_root)
    preparation = {
        "schema_version": "abyss_stack_external_codex_review_preparation_v1",
        "writer_session_id": writer_result["session_id"],
        "writer_incarnation_id": writer_result["incarnation_id"],
        "writer_thread_id": writer_result["thread_id"],
        "writer_status": writer_result["status"],
        "writer_result_path": str(writer_result_path),
        "writer_result_digest": writer_result_digest,
        "writer_runtime_state_path": str(writer_state_path),
        "writer_runtime_state_digest": _file_digest(writer_state_path),
        "writer_report_path": str(writer_report_path),
        "writer_report_digest": _file_digest(writer_report_path),
        "writer_effect_class": writer_effect_class,
        "writer_workspace_manifest_path": str(writer_workspace_manifest_path),
        "writer_workspace_manifest_digest": _file_digest(
            writer_workspace_manifest_path
        ),
        "writer_actor_final_manifest_path": str(writer_workspace_manifest_path),
        "writer_actor_final_manifest_digest": _file_digest(
            writer_workspace_manifest_path
        ),
        "writer_actor_delta_path": str(writer_actor_delta_path),
        "writer_actor_delta_digest": _file_digest(writer_actor_delta_path),
        "review_seed_envelope_path": str(review_seed_ref["artifact_ref"]),
        "review_seed_envelope_digest": str(review_seed_ref["artifact_digest"]),
        "review_workspace_manifest_path": str(review_manifest_path),
        "review_workspace_manifest_digest": _file_digest(review_manifest_path),
        "review_instance_id": review_instance_id,
        "reviewer_session_id": session_id,
        "reviewer_incarnation_id": incarnation_id,
        "reviewer_model_realization_ref": (
            reviewer_model_ref.artifact_ref
        ),
        "review_summon_request_path": str(review_summon_request_path),
        "review_summon_request_digest": (
            review_summon_request_ref.artifact_digest
        ),
        "summon_request_schema_path": str(summon_request_schema_path),
        "summon_request_schema_digest": (
            summon_request_schema_ref.artifact_digest
        ),
        "review_summon_decision_path": str(review_summon_decision_path),
        "review_summon_decision_digest": (
            review_summon_decision_ref.artifact_digest
        ),
        "summon_result_schema_path": str(summon_result_schema_path),
        "summon_result_schema_digest": (
            summon_result_schema_ref.artifact_digest
        ),
        "forwarded_input_ids": [item["input_id"] for item in forwarded_inputs],
        "launch_path": str(launch_path),
        "launch_digest": sha256_bytes(launch_raw),
        "state_root": str(state_root),
        "aoa_sdk_import_provenance": {
            "source_root": str(aoa_sdk_root),
            "expected_package_root": str(aoa_sdk_root / "src" / "aoa_sdk"),
            "capture_point": "after_reviewer_plan_and_binding_compilation",
            "coordinates": list(sdk_import_coordinates),
        },
        "usage_metering": base_binding.usage_metering.model_dump(mode="json"),
        "started": False,
        "fixed_invariants": [
            "Preparation starts no Codex process.",
            "Writer and reviewer session/incarnation identities differ.",
            "Every writer immutable input keeps its stable input id and exact provenance.",
            "The reviewer binds the exact post-writer actor projection manifest and delta.",
            "The reviewer source baseline remains a separate owner-source manifest.",
            "The reviewer receives the exact writer runtime result and model report.",
            "The reviewer binds its own canonical SDK v4 summon request and decision while retaining the writer request as immutable evidence.",
            "Usage is observed without token, time, turn, output, or cost ceilings.",
            "No workspace mutation, owner acceptance, model-fit verdict, or external effect is authorized.",
        ],
    }
    if isinstance(writer_review_seal_ref, dict):
        preparation["writer_review_seal_path"] = str(
            writer_review_seal_ref["artifact_ref"]
        )
        preparation["writer_review_seal_digest"] = str(
            writer_review_seal_ref["artifact_digest"]
        )
    validate_json(
        preparation,
        REVIEW_PREPARATION_SCHEMA_PATH,
        label="external Codex review preparation",
    )
    preparation_path = output_root / "review-preparation.json"
    _write_exact(preparation_path, _json_bytes(preparation))
    return {
        "schema_version": (
            "abyss_stack_external_codex_review_preparation_response_v1"
        ),
        "prepared": True,
        "started": False,
        "preparation_path": str(preparation_path),
        "preparation_digest": _file_digest(preparation_path),
        "reviewer_session_id": session_id,
        "state_root": str(state_root),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    manifest = subparsers.add_parser("manifest")
    manifest.add_argument("--workspace", required=True)
    manifest.add_argument("--output", required=True)

    writers = subparsers.add_parser("prepare-writers")
    writers.add_argument("--workspace", required=True)
    writers.add_argument("--workspace-manifest", required=True)
    writers.add_argument("--study", required=True)
    writers.add_argument("--study-packet", required=True)
    writers.add_argument("--output-root", required=True)
    writers.add_argument("--state-root", required=True)
    writers.add_argument("--aoa-models-root", default="/srv/AbyssOS/aoa-models")
    writers.add_argument("--aoa-agents-root", default="/srv/AbyssOS/aoa-agents")
    writers.add_argument("--aoa-skills-root", default="/srv/AbyssOS/aoa-skills")
    writers.add_argument("--aoa-evals-root", default="/srv/AbyssOS/aoa-evals")
    writers.add_argument("--aoa-memo-root", default="/srv/AbyssOS/aoa-memo")
    writers.add_argument("--aoa-playbooks-root", default="/srv/AbyssOS/aoa-playbooks")
    writers.add_argument("--aoa-sdk-root", required=True)
    writers.add_argument("--codex-executable", required=True)
    writers.add_argument("--codex-home", required=True)
    writers.add_argument("--runtime-package-root", required=True)
    writers.add_argument("--runtime-package-artifact-identity", required=True)
    writers.add_argument("--runtime-package-artifact-subjects", required=True)

    reviewer = subparsers.add_parser("prepare-reviewer")
    reviewer.add_argument("--writer-launch", required=True)
    reviewer.add_argument("--writer-result", required=True)
    reviewer.add_argument("--output-root", required=True)
    reviewer.add_argument("--state-root", required=True)
    reviewer.add_argument("--aoa-sdk-root", required=True)
    reviewer.add_argument("--reviewer-role-contract")
    reviewer.add_argument("--reviewer-model-realization")
    reviewer.add_argument("--review-instance-id", default="initial")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "manifest":
            result = _prepare_manifest(args)
        elif args.operation == "prepare-writers":
            result = _prepare_writers(args)
        else:
            result = _prepare_reviewer(args)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=True, sort_keys=True))
        return 0
    except (StudyPreparationError, ExternalCodexRuntimeError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
