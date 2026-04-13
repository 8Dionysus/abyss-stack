from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "compose" / "profiles"
PRESET_DIR = ROOT / "compose" / "presets"
MODULE_DIR = ROOT / "compose" / "modules"
RUNTIME_CONFIGS_MIRROR_MODE = (
    ROOT.name == "Configs"
    and (ROOT / "compose").exists()
    and (ROOT / "config-templates").exists()
    and not (ROOT / "CONTRIBUTING.md").exists()
)

LEGACY_PATH = "/srv/abyss"
LEGACY_PATTERN = re.compile(r"/srv/abyss(?!-)")
LEGACY_ALLOWED = {
    ROOT / "docs" / "MIGRATION_FROM_OLD.md",
    ROOT / "scripts" / "validate_stack.py",
}

SYNC_MANAGED_ITEMS = (
    "compose",
    "config-templates",
    "docs",
    "scripts",
    "systemd",
    "env",
    "README.md",
    "CHARTER.md",
    "BOUNDARIES.md",
    "ROADMAP.md",
    "AGENTS.md",
)

PARITY_IGNORED_PARTS = {".git", "__pycache__"}
PARITY_IGNORED_SUFFIXES = {".pyc"}

REQUIRED_SCRIPTS = {
    "_aoa_governed_execution.py",
    "_aoa_diagnose.py",
    "_aoa_status_autonomy.py",
    "aoa-diagnose",
    "aoa-governed-run",
    "aoa-doctor",
    "aoa-host-facts",
    "aoa-machine-fit",
    "aoa-platform-adaptation",
    "aoa-local-ai-trials",
    "aoa-langgraph-pilot",
    "aoa-w5-pilot",
    "aoa-w6-pilot",
    "aoa-llamacpp-pilot",
    "aoa-runtime-bench-index",
    "aoa-rpg-runtime-projection",
    "aoa-qwen-check",
    "aoa-federated-check",
    "aoa-qwen-run",
    "aoa-qwen-bench",
    "aoa-export-memo-candidate",
    "aoa-export-runtime-evidence-selection",
    "aoa-export-artifact-hook-candidate",
    "aoa-install-layout",
    "aoa-sync-configs",
    "aoa-sync-federation-surfaces",
    "aoa-bootstrap-configs",
    "aoa-check-layout",
    "aoa-warmup",
    "aoa-install-systemd",
    "aoa-first-run",
    "aoa-preset-profiles",
    "aoa-profile-modules",
    "aoa-profile-endpoints",
    "aoa-internal-probes",
    "aoa-render-services",
    "aoa-render-config",
    "aoa-up",
    "aoa-down",
    "aoa-status",
    "aoa-logs",
    "aoa-smoke",
    "aoa-wait",
    "aoa.ps1",
    "aoa-doctor-win.ps1",
    "aoa-bootstrap-wsl.ps1",
}

REQUIRED_FILES = {
    ROOT / "compose" / "AGENTS.md",
    ROOT / "env" / "AGENTS.md",
    ROOT / "config-templates" / "AGENTS.md",
    ROOT / "systemd" / "user" / "AGENTS.md",
    ROOT / "scripts" / "AGENTS.md",
    ROOT / "docs" / "RECURRENCE_RUNTIME_POLICY.md",
    ROOT / "docs" / "GOVERNED_EXECUTION.md",
    ROOT / "docs" / "FIRST_RUN.md",
    ROOT / "docs" / "DOCTOR.md",
    ROOT / "docs" / "PRESETS.md",
    ROOT / "docs" / "PROFILE_RECIPES.md",
    ROOT / "docs" / "RENDER_TRUTH.md",
    ROOT / "docs" / "RUNTIME_BENCH_POLICY.md",
    ROOT / "docs" / "LOCAL_AI_TRIALS.md",
    ROOT / "docs" / "TRUTH_SURFACES.md",
    ROOT / "docs" / "LANGGRAPH_PILOT.md",
    ROOT / "docs" / "LLAMACPP_PILOT.md",
    ROOT / "docs" / "W5_PILOT.md",
    ROOT / "docs" / "W6_PILOT.md",
    ROOT / "docs" / "PLATFORM_ADAPTATION_POLICY.md",
    ROOT / "docs" / "BRANCH_POLICY.md",
    ROOT / "docs" / "MEMO_RUNTIME_SEAM.md",
    ROOT / "docs" / "EVAL_RUNTIME_SEAM.md",
    ROOT / "docs" / "PLAYBOOK_RUNTIME_SEAM.md",
    ROOT / "docs" / "KAG_RUNTIME_SEAM.md",
    ROOT / "docs" / "DIAGNOSTIC_SPINE.md",
    ROOT / "docs" / "TOS_GRAPH_CURATION.md",
    ROOT / "docs" / "RPG_RUNTIME_COLLECTIONS.md",
    ROOT / "docs" / "RPG_RUNTIME_BUILDERS.md",
    ROOT / "docs" / "RPG_ROUTE_API_SEAM.md",
    ROOT / "docs" / "RPG_FRONTEND_PROJECTION_SEAM.md",
    ROOT / "docs" / "GATEWAY_CACHE_POLICY.md",
    ROOT / "docs" / "USAGE_BUDGET_POLICY.md",
    ROOT / "docs" / "LOCAL_OPS_DOCTOR_SPLIT.md",
    ROOT / "docs" / "INTERNAL_PROBES.md",
    ROOT / "docs" / "REFERENCE_PLATFORM.md",
    ROOT / "docs" / "REFERENCE_PLATFORM_SPEC.md",
    ROOT / "docs" / "MACHINE_FIT_POLICY.md",
    ROOT / "docs" / "SECRETS_BOOTSTRAP.md",
    ROOT / "docs" / "WINDOWS_BRIDGE.md",
    ROOT / "docs" / "WINDOWS_SETUP.md",
    ROOT / "docs" / "WINDOWS_PERFORMANCE.md",
    ROOT / "docs" / "reference-platform" / "README.md",
    ROOT / "docs" / "reference-platform" / "schema.v1.json",
    ROOT / "docs" / "reference-platform" / "reference-host.public.json.example",
    ROOT / "docs" / "machine-fit" / "README.md",
    ROOT / "docs" / "machine-fit" / "schema.v1.json",
    ROOT / "docs" / "machine-fit" / "machine-fit.public.json.example",
    ROOT / "scripts" / "requirements-langgraph-pilot.txt",
    ROOT / "docs" / "platform-adaptations" / "README.md",
    ROOT / "docs" / "platform-adaptations" / "schema.v1.json",
    ROOT / "docs" / "platform-adaptations" / "platform-adaptation.public.json.example",
    ROOT / "compose" / "presets" / "README.md",
    ROOT / "compose" / "presets" / "agent-federation.txt",
    ROOT / "compose" / "presets" / "agent-tools.txt",
    ROOT / "compose" / "presets" / "agent-observability.txt",
    ROOT / "compose" / "presets" / "agent-full.txt",
    ROOT / "compose" / "presets" / "intel-federation.txt",
    ROOT / "compose" / "presets" / "intel-tools.txt",
    ROOT / "compose" / "presets" / "intel-observability.txt",
    ROOT / "compose" / "presets" / "intel-full.txt",
    ROOT / "compose" / "profiles" / "federation.txt",
    ROOT / "compose" / "tuning" / "README.md",
    ROOT / "compose" / "tuning" / "llamacpp.cpu.yml",
    ROOT / "compose" / "tuning" / "llamacpp.runtime-fallback.yml",
    ROOT / "compose" / "modules" / "32-llamacpp-inference.yml",
    ROOT / "compose" / "modules" / "43-federation-router.yml",
    ROOT / "compose" / "modules" / "44-llamacpp-agent-sidecar.yml",
    ROOT / "compose" / "modules" / "52-tos-graph.yml",
    ROOT / "compose" / "profiles" / "curation.txt",
    ROOT / "config-templates" / "README.md",
    ROOT / "config-templates" / "Configs" / "agent-api" / "return-policy.yaml",
    ROOT / "config-templates" / "Configs" / "agent-api" / "governed-execution-policy.yaml",
    ROOT / "config-templates" / "Configs" / "agent-api" / "governed-canary-catalog.json",
    ROOT / "config-templates" / "Configs" / "tos-graph" / "README.md",
    ROOT / "config-templates" / "Configs" / "tos-graph" / "config.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-agents.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-routing.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-memo.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-evals.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-playbooks.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-kag.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "tos-source.yaml",
    ROOT / "config-templates" / "Configs" / "monitoring" / "prometheus.yml",
    ROOT / "config-templates" / "Configs" / "tts" / "voices.yaml",
    ROOT / "config-templates" / "Services" / "aoa-browser" / "Dockerfile",
    ROOT / "config-templates" / "Services" / "aoa-browser" / "app.py",
    ROOT / "config-templates" / "Services" / "litellm" / "config.yaml",
    ROOT / "config-templates" / "Services" / "route-api" / "Dockerfile",
    ROOT / "config-templates" / "Services" / "route-api" / "requirements.txt",
    ROOT / "config-templates" / "Services" / "route-api" / "app" / "main.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "Dockerfile",
    ROOT / "config-templates" / "Services" / "tos-graph" / "requirements.txt",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "config.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "main.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "models.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "neo4j_store.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "projector.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "tos_reader.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "ui.py",
    ROOT / "schemas" / "runtime-benchmark.schema.json",
    ROOT / "schemas" / "runtime-governed-execution-policy.schema.json",
    ROOT / "schemas" / "runtime-governed-execution-request.schema.json",
    ROOT / "schemas" / "runtime-governed-execution-canary-catalog.schema.json",
    ROOT / "schemas" / "runtime-memo-export-candidate.schema.json",
    ROOT / "schemas" / "runtime-eval-evidence-selection-candidate.schema.json",
    ROOT / "schemas" / "runtime-artifact-hook-candidate.schema.json",
    ROOT / "schemas" / "runtime-return-policy.schema.json",
    ROOT / "schemas" / "runtime-return-event.schema.json",
    ROOT / "schemas" / "diagnostic_target.schema.json",
    ROOT / "schemas" / "diagnostic_session.schema.json",
    ROOT / "schemas" / "diagnosis_companion.schema.json",
    ROOT / "schemas" / "diagnostic_anchor_ref.schema.json",
    ROOT / "schemas" / "repair_handoff.schema.json",
    ROOT / "schemas" / "reviewed_diagnosis_ref.schema.json",
    ROOT / "schemas" / "runtime-gateway-cache-status.schema.json",
    ROOT / "schemas" / "runtime-usage-snapshot.schema.json",
    ROOT / "schemas" / "agent_build_snapshot_collection.schema.json",
    ROOT / "schemas" / "reputation_ledger_collection.schema.json",
    ROOT / "schemas" / "quest_run_result_collection.schema.json",
    ROOT / "schemas" / "frontend_projection_bundle_collection.schema.json",
    ROOT / "examples" / "runtime_benchmark.workhorse-local.example.json",
    ROOT / "examples" / "runtime_memo_export_candidate.checkpoint_export.example.json",
    ROOT / "examples" / "runtime_eval_evidence_selection_candidate.workhorse-local.example.json",
    ROOT / "examples" / "runtime_artifact_hook_candidate.self-agent-checkpoint-rollout.example.json",
    ROOT / "examples" / "runtime_return_policy.agentic-local.example.json",
    ROOT / "examples" / "runtime_return_event.workhorse-local.example.json",
    ROOT / "examples" / "diagnostic_target.min.example.json",
    ROOT / "examples" / "diagnostic_session.min.example.json",
    ROOT / "examples" / "diagnosis_companion.min.example.json",
    ROOT / "examples" / "diagnostic_anchor_ref.min.example.json",
    ROOT / "examples" / "repair_handoff.min.example.json",
    ROOT / "examples" / "reviewed_diagnosis_ref.min.example.json",
    ROOT / "generated" / "diagnostic_surface_catalog.min.json",
    ROOT / "examples" / "runtime_gateway_cache_status.gateway-local.example.json",
    ROOT / "examples" / "runtime_usage_snapshot.workhorse-local.example.json",
    ROOT / "generated" / "rpg" / "agent_build_snapshots.json",
    ROOT / "generated" / "rpg" / "reputation_ledgers.json",
    ROOT / "generated" / "rpg" / "quest_run_results.json",
    ROOT / "generated" / "rpg" / "frontend_projection_bundles.json",
    ROOT / "tests" / "test_governed_execution.py",
    ROOT / "tests" / "test_validate_stack_required_files.py",
    ROOT / "tests" / "test_validate_stack_questbook.py",
    ROOT / "tests" / "test_validate_stack_diagnostic_spine.py",
    ROOT / "tests" / "test_validate_stack_runtime_hygiene.py",
    ROOT / "tests" / "test_diagnostic_spine_contracts.py",
    ROOT / "tests" / "test_aoa_diagnose.py",
    ROOT / "tests" / "test_rpg_runtime_projection.py",
}

FEDERATION_REQUIRED_RUNTIME_INPUTS = {
    Path("config-templates") / "Configs" / "federation" / "aoa-memo.yaml": {
        "generated/runtime_writeback_targets.min.json",
        "generated/runtime_writeback_intake.min.json",
    },
    Path("config-templates") / "Configs" / "federation" / "aoa-evals.yaml": {
        "generated/runtime_candidate_template_index.min.json",
        "generated/runtime_candidate_intake.min.json",
        "examples/runtime_evidence_selection.workhorse-local.example.json",
        "examples/runtime_evidence_selection.return-anchor-integrity.example.json",
        "examples/runtime_evidence_selection.phase-alpha-memo-recall-rerun.example.json",
        "examples/runtime_evidence_selection.phase-alpha-memo-contradiction-gap.example.json",
    },
    Path("config-templates") / "Configs" / "federation" / "aoa-playbooks.yaml": {
        "generated/playbook_review_packet_contracts.min.json",
        "generated/playbook_review_intake.min.json",
    },
}

QUESTBOOK_PATH = Path("QUESTBOOK.md")
QUESTBOOK_INTEGRATION_PATH = Path("docs") / "QUESTBOOK_STACK_INTEGRATION.md"
RPG_RUNTIME_FRONTEND_POSTURE_PATH = Path("docs") / "RPG_RUNTIME_FRONTEND_POSTURE.md"
RPG_RUNTIME_COLLECTIONS_PATH = Path("docs") / "RPG_RUNTIME_COLLECTIONS.md"
RPG_RUNTIME_BUILDERS_PATH = Path("docs") / "RPG_RUNTIME_BUILDERS.md"
RPG_ROUTE_API_SEAM_PATH = Path("docs") / "RPG_ROUTE_API_SEAM.md"
RPG_FRONTEND_PROJECTION_SEAM_PATH = Path("docs") / "RPG_FRONTEND_PROJECTION_SEAM.md"
DIAGNOSTIC_SPINE_PATH = Path("docs") / "DIAGNOSTIC_SPINE.md"
DIAGNOSTIC_SURFACE_CATALOG_PATH = Path("generated") / "diagnostic_surface_catalog.min.json"
DIAGNOSTIC_SPINE_SKILL_PATH = Path(".agents") / "skills" / "abyss-self-diagnostic-spine"
ABYSS_SAFE_INFRA_SKILL_PATH = Path(".agents") / "skills" / "abyss-safe-infra-change"
ABYSS_SANITIZED_SHARE_SKILL_PATH = Path(".agents") / "skills" / "abyss-sanitized-share"
OVERLAY_SKILL_INSTALL_TARGETS = {
    ABYSS_SAFE_INFRA_SKILL_PATH: "/srv/aoa-skills/.agents/skills/abyss-safe-infra-change",
    ABYSS_SANITIZED_SHARE_SKILL_PATH: "/srv/aoa-skills/.agents/skills/abyss-sanitized-share",
}
QUEST_SCHEMA_PATH = Path("schemas") / "quest.schema.json"
QUEST_DISPATCH_SCHEMA_PATH = Path("schemas") / "quest_dispatch.schema.json"
DIAGNOSTIC_TARGET_SCHEMA_PATH = Path("schemas") / "diagnostic_target.schema.json"
DIAGNOSTIC_SESSION_SCHEMA_PATH = Path("schemas") / "diagnostic_session.schema.json"
DIAGNOSIS_COMPANION_SCHEMA_PATH = Path("schemas") / "diagnosis_companion.schema.json"
DIAGNOSTIC_ANCHOR_REF_SCHEMA_PATH = Path("schemas") / "diagnostic_anchor_ref.schema.json"
REPAIR_HANDOFF_SCHEMA_PATH = Path("schemas") / "repair_handoff.schema.json"
REVIEWED_DIAGNOSIS_REF_SCHEMA_PATH = Path("schemas") / "reviewed_diagnosis_ref.schema.json"
AGENT_BUILD_SNAPSHOT_SCHEMA_PATH = Path("schemas") / "agent_build_snapshot.schema.json"
REPUTATION_LEDGER_SCHEMA_PATH = Path("schemas") / "reputation_ledger.schema.json"
QUEST_RUN_RESULT_SCHEMA_PATH = Path("schemas") / "quest_run_result.schema.json"
FRONTEND_PROJECTION_BUNDLE_SCHEMA_PATH = Path("schemas") / "frontend_projection_bundle.schema.json"
AGENT_BUILD_SNAPSHOT_COLLECTION_SCHEMA_PATH = Path("schemas") / "agent_build_snapshot_collection.schema.json"
REPUTATION_LEDGER_COLLECTION_SCHEMA_PATH = Path("schemas") / "reputation_ledger_collection.schema.json"
QUEST_RUN_RESULT_COLLECTION_SCHEMA_PATH = Path("schemas") / "quest_run_result_collection.schema.json"
FRONTEND_PROJECTION_BUNDLE_COLLECTION_SCHEMA_PATH = Path("schemas") / "frontend_projection_bundle_collection.schema.json"
QUEST_CATALOG_EXAMPLE_PATH = Path("examples") / "quest_catalog.min.example.json"
QUEST_DISPATCH_EXAMPLE_PATH = Path("examples") / "quest_dispatch.min.example.json"
DIAGNOSTIC_TARGET_EXAMPLE_PATH = Path("examples") / "diagnostic_target.min.example.json"
DIAGNOSTIC_SESSION_EXAMPLE_PATH = Path("examples") / "diagnostic_session.min.example.json"
DIAGNOSIS_COMPANION_EXAMPLE_PATH = Path("examples") / "diagnosis_companion.min.example.json"
DIAGNOSTIC_ANCHOR_REF_EXAMPLE_PATH = Path("examples") / "diagnostic_anchor_ref.min.example.json"
REPAIR_HANDOFF_EXAMPLE_PATH = Path("examples") / "repair_handoff.min.example.json"
REVIEWED_DIAGNOSIS_REF_EXAMPLE_PATH = Path("examples") / "reviewed_diagnosis_ref.min.example.json"
AGENT_BUILD_SNAPSHOT_EXAMPLE_PATH = Path("examples") / "agent_build_snapshot.example.json"
REPUTATION_LEDGER_EXAMPLE_PATH = Path("examples") / "reputation_ledger.example.json"
QUEST_RUN_RESULT_EXAMPLE_PATH = Path("examples") / "quest_run_result.example.json"
FRONTEND_PROJECTION_BUNDLE_EXAMPLE_PATH = Path("examples") / "frontend_projection_bundle.example.json"
GENERATED_AGENT_BUILD_SNAPSHOTS_PATH = Path("generated") / "rpg" / "agent_build_snapshots.json"
GENERATED_REPUTATION_LEDGERS_PATH = Path("generated") / "rpg" / "reputation_ledgers.json"
GENERATED_QUEST_RUN_RESULTS_PATH = Path("generated") / "rpg" / "quest_run_results.json"
GENERATED_FRONTEND_PROJECTION_BUNDLES_PATH = Path("generated") / "rpg" / "frontend_projection_bundles.json"
DIAGNOSTIC_SURFACE_CATALOG_EXPECTED_NAMES = (
    "diagnostic_target",
    "diagnostic_session",
    "diagnosis_companion",
    "reviewed_diagnosis_ref",
    "repair_handoff",
)
QUEST_IDS = (
    "ABYSS-STACK-Q-0001",
    "ABYSS-STACK-Q-0002",
    "ABYSS-STACK-Q-0003",
    "ABYSS-STACK-Q-0004",
    "ABYSS-STACK-Q-0005",
    "ABYSS-STACK-Q-0006",
    "ABYSS-STACK-Q-0007",
    "ABYSS-STACK-Q-0008",
)
QUESTBOOK_REQUIRED_TOKENS = (
    "deferred infrastructure obligations that belong to `abyss-stack`",
    "render-truth, doctor, first-run, and runtime guardrail follow-through",
    "source-owned meaning from AoA layer repos",
    "examples/quest_catalog.min.example.json",
    "not generated state, deployed runtime state, or runtime authority",
)
QUESTBOOK_FORBIDDEN_TOKENS = ("ATM10-Agent", "aoa-sdk")
CLOSED_QUEST_STATES = {"done", "dropped"}
QUESTBOOK_INTEGRATION_REQUIRED_TOKENS = (
    "runtime, deployment, lifecycle, security, storage, and platform posture",
    "specialized AoA repositories still own their own doctrine and public meaning",
    "high-risk routes should default toward stronger control modes and human gates",
    "reviewable and source-owned",
    "do not replace the deployed mirror under `/srv/abyss-stack`",
)
QUESTBOOK_INTEGRATION_FORBIDDEN_TOKENS = ("ATM10-Agent", "aoa-sdk")
QUEST_SCHEMA_REQUIRED_FIELDS = (
    "schema_version",
    "id",
    "title",
    "repo",
    "owner_surface",
    "kind",
    "state",
    "band",
    "difficulty",
    "risk",
    "control_mode",
    "delegate_tier",
    "write_scope",
    "activation",
    "anchor_ref",
    "evidence",
    "opened_at",
    "touched_at",
    "public_safe",
)
QUEST_DISPATCH_REQUIRED_FIELDS = (
    "schema_version",
    "id",
    "repo",
    "state",
    "band",
    "difficulty",
    "risk",
    "control_mode",
    "delegate_tier",
    "split_required",
    "write_scope",
    "activation_mode",
    "public_safe",
)

MODULE_REQUIREMENTS = {
    "20-orchestration.yml": {"10-storage.yml"},
    "40-llm-gateway.yml": {"30-local-inference.yml"},
    "41-agent-api.yml": {"32-llamacpp-inference.yml"},
    "42-agent-api-intel.yml": {"41-agent-api.yml", "31-intel-inference.yml"},
    "52-tos-graph.yml": {"10-storage.yml"},
}

BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".zip", ".pyc"}


def iter_text_files() -> list[Path]:
    paths: list[Path] = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue

        paths.append(path)

    return paths


def read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def load_names(file_path: Path) -> list[str]:
    names: list[str] = []

    for raw in file_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.append(line)

    return names


def load_structured_object(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(text)
    except ImportError:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path.relative_to(ROOT)} must parse as an object")
    return payload


def validate_quest_schema_envelope(
    payload: object,
    *,
    title: str,
    required_fields: Sequence[str],
    schema_version: str,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(payload, dict):
        errors.append(f"{label} must be a JSON object")
        return
    if payload.get("title") != title:
        errors.append(f"{label} title must equal '{title}'")
    if payload.get("type") != "object":
        errors.append(f"{label} type must equal 'object'")
    if payload.get("additionalProperties") is not False:
        errors.append(f"{label} must set additionalProperties to false")

    required = payload.get("required")
    if required != list(required_fields):
        errors.append(f"{label} required fields must stay aligned with the local quest contract")

    properties = payload.get("properties")
    if not isinstance(properties, dict):
        errors.append(f"{label} properties must be an object")
        return

    version_payload = properties.get("schema_version")
    if not isinstance(version_payload, dict) or version_payload.get("const") != schema_version:
        errors.append(f"{label} schema_version.const must equal '{schema_version}'")


def build_expected_quest_catalog_entry(quest_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": quest_id,
        "title": payload["title"],
        "repo": payload["repo"],
        "theme_ref": payload.get("theme_ref", ""),
        "milestone_ref": payload.get("milestone_ref", ""),
        "state": payload["state"],
        "band": payload["band"],
        "kind": payload["kind"],
        "difficulty": payload["difficulty"],
        "risk": payload["risk"],
        "owner_surface": payload["owner_surface"],
        "source_path": f"quests/{quest_id}.yaml",
        "public_safe": payload["public_safe"],
    }


def build_expected_quest_dispatch_entry(quest_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if quest_id == "ABYSS-STACK-Q-0003":
        requires_artifacts = [
            "bounded_plan",
            "guardrail_check",
            "verification_result",
            "rollout_decision",
        ]
    elif quest_id == "ABYSS-STACK-Q-0004":
        requires_artifacts = [
            "bounded_plan",
            "work_result",
        ]
    else:
        requires_artifacts = [
            "bounded_plan",
            "work_result",
            "verification_result",
        ]

    activation = payload.get("activation")
    if not isinstance(activation, dict):
        raise RuntimeError(f"{quest_id} activation must be an object")

    return {
        "schema_version": "quest_dispatch_v1",
        "id": quest_id,
        "repo": payload["repo"],
        "state": payload["state"],
        "band": payload["band"],
        "difficulty": payload["difficulty"],
        "risk": payload["risk"],
        "control_mode": payload["control_mode"],
        "delegate_tier": payload["delegate_tier"],
        "split_required": payload["split_required"],
        "write_scope": payload["write_scope"],
        "requires_artifacts": requires_artifacts,
        "activation_mode": activation["mode"],
        "source_path": f"quests/{quest_id}.yaml",
        "public_safe": payload["public_safe"],
        "fallback_tier": payload["fallback_tier"],
        "wrapper_class": payload["wrapper_class"],
    }


def validate_questbook_surface(errors: list[str]) -> None:
    required_paths = (
        QUESTBOOK_PATH,
        QUESTBOOK_INTEGRATION_PATH,
        RPG_RUNTIME_FRONTEND_POSTURE_PATH,
        RPG_RUNTIME_COLLECTIONS_PATH,
        RPG_RUNTIME_BUILDERS_PATH,
        RPG_ROUTE_API_SEAM_PATH,
        RPG_FRONTEND_PROJECTION_SEAM_PATH,
        QUEST_SCHEMA_PATH,
        QUEST_DISPATCH_SCHEMA_PATH,
        AGENT_BUILD_SNAPSHOT_SCHEMA_PATH,
        REPUTATION_LEDGER_SCHEMA_PATH,
        QUEST_RUN_RESULT_SCHEMA_PATH,
        FRONTEND_PROJECTION_BUNDLE_SCHEMA_PATH,
        AGENT_BUILD_SNAPSHOT_COLLECTION_SCHEMA_PATH,
        REPUTATION_LEDGER_COLLECTION_SCHEMA_PATH,
        QUEST_RUN_RESULT_COLLECTION_SCHEMA_PATH,
        FRONTEND_PROJECTION_BUNDLE_COLLECTION_SCHEMA_PATH,
        QUEST_CATALOG_EXAMPLE_PATH,
        QUEST_DISPATCH_EXAMPLE_PATH,
        AGENT_BUILD_SNAPSHOT_EXAMPLE_PATH,
        REPUTATION_LEDGER_EXAMPLE_PATH,
        QUEST_RUN_RESULT_EXAMPLE_PATH,
        FRONTEND_PROJECTION_BUNDLE_EXAMPLE_PATH,
        GENERATED_AGENT_BUILD_SNAPSHOTS_PATH,
        GENERATED_REPUTATION_LEDGERS_PATH,
        GENERATED_QUEST_RUN_RESULTS_PATH,
        GENERATED_FRONTEND_PROJECTION_BUNDLES_PATH,
    ) + tuple(Path("quests") / f"{quest_id}.yaml" for quest_id in QUEST_IDS)

    for relative_path in required_paths:
        path = ROOT / relative_path
        if not path.exists():
            errors.append(f"missing required file: {relative_path.as_posix()}")

    try:
        questbook_text = (ROOT / QUESTBOOK_PATH).read_text(encoding="utf-8")
    except FileNotFoundError:
        questbook_text = ""
    else:
        for token in QUESTBOOK_REQUIRED_TOKENS:
            if token not in questbook_text:
                errors.append(f"QUESTBOOK.md must contain '{token}'")
        for token in QUESTBOOK_FORBIDDEN_TOKENS:
            if token in questbook_text:
                errors.append(f"QUESTBOOK.md must not mention '{token}'")

    try:
        integration_text = (ROOT / QUESTBOOK_INTEGRATION_PATH).read_text(encoding="utf-8")
    except FileNotFoundError:
        integration_text = ""
    else:
        for token in QUESTBOOK_INTEGRATION_REQUIRED_TOKENS:
            if token not in integration_text:
                errors.append(f"{QUESTBOOK_INTEGRATION_PATH.as_posix()} must contain '{token}'")
        for token in QUESTBOOK_INTEGRATION_FORBIDDEN_TOKENS:
            if token in integration_text:
                errors.append(f"{QUESTBOOK_INTEGRATION_PATH.as_posix()} must not mention '{token}'")

    try:
        rpg_runtime_frontend_text = (ROOT / RPG_RUNTIME_FRONTEND_POSTURE_PATH).read_text(
            encoding="utf-8"
        )
    except FileNotFoundError:
        rpg_runtime_frontend_text = ""
    else:
        required_tokens = (
            "`abyss-stack` owns runtime state and service delivery.",
            "It does not own upstream meaning.",
            "The frontend must not become an authority surface.",
            "It must never pretend to be the soul.",
        )
        for token in required_tokens:
            if token not in rpg_runtime_frontend_text:
                errors.append(f"{RPG_RUNTIME_FRONTEND_POSTURE_PATH.as_posix()} must contain '{token}'")

    doc_expectations = (
        (
            RPG_RUNTIME_COLLECTIONS_PATH,
            (
                "`abyss-stack` owns the collections.",
                "It does not own the upstream meanings the collections cite.",
                "A runtime collection is a read model with memory.",
            ),
        ),
        (
            RPG_RUNTIME_BUILDERS_PATH,
            (
                "Builders may assemble runtime-owned collections.",
                "Builders may not invent upstream meaning.",
                "Build upstream, collect downstream, project last.",
            ),
        ),
        (
            RPG_ROUTE_API_SEAM_PATH,
            (
                "It is not implemented in this wave.",
                "`/rpg/*` is advisory and read-only.",
                "The seam should read like a lantern, not a wand.",
            ),
        ),
        (
            RPG_FRONTEND_PROJECTION_SEAM_PATH,
            (
                "The frontend reads derived bundles.",
                "It does not become a new authority surface.",
                "Keep the source refs audible.",
            ),
        ),
    )
    for path, tokens in doc_expectations:
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        for token in tokens:
            if token not in text:
                errors.append(f"{path.as_posix()} must contain '{token}'")

    try:
        quest_schema_payload = json.loads((ROOT / QUEST_SCHEMA_PATH).read_text(encoding="utf-8"))
    except FileNotFoundError:
        quest_schema_payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"{QUEST_SCHEMA_PATH.as_posix()} must contain valid JSON: {exc}")
        quest_schema_payload = None
    if quest_schema_payload is not None:
        validate_quest_schema_envelope(
            quest_schema_payload,
            title="abyss-stack work_quest_v1",
            required_fields=QUEST_SCHEMA_REQUIRED_FIELDS,
            schema_version="work_quest_v1",
            label=QUEST_SCHEMA_PATH.as_posix(),
            errors=errors,
        )

    try:
        dispatch_schema_payload = json.loads(
            (ROOT / QUEST_DISPATCH_SCHEMA_PATH).read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        dispatch_schema_payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"{QUEST_DISPATCH_SCHEMA_PATH.as_posix()} must contain valid JSON: {exc}")
        dispatch_schema_payload = None
    if dispatch_schema_payload is not None:
        validate_quest_schema_envelope(
            dispatch_schema_payload,
            title="abyss-stack quest_dispatch_v1",
            required_fields=QUEST_DISPATCH_REQUIRED_FIELDS,
            schema_version="quest_dispatch_v1",
            label=QUEST_DISPATCH_SCHEMA_PATH.as_posix(),
            errors=errors,
        )

    schema_expectations = (
        (AGENT_BUILD_SNAPSHOT_SCHEMA_PATH, "agent_build_snapshot_v1"),
        (REPUTATION_LEDGER_SCHEMA_PATH, "reputation_ledger_v1"),
        (QUEST_RUN_RESULT_SCHEMA_PATH, "quest_run_result_v1"),
        (FRONTEND_PROJECTION_BUNDLE_SCHEMA_PATH, "frontend_projection_bundle_v1"),
        (AGENT_BUILD_SNAPSHOT_COLLECTION_SCHEMA_PATH, "agent_build_snapshot_collection_v1"),
        (REPUTATION_LEDGER_COLLECTION_SCHEMA_PATH, "reputation_ledger_collection_v1"),
        (QUEST_RUN_RESULT_COLLECTION_SCHEMA_PATH, "quest_run_result_collection_v1"),
        (FRONTEND_PROJECTION_BUNDLE_COLLECTION_SCHEMA_PATH, "frontend_projection_bundle_collection_v1"),
    )
    for path, expected_title in schema_expectations:
        try:
            payload = json.loads((ROOT / path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"{path.as_posix()} must contain valid JSON: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path.as_posix()} must be a JSON object")
            continue
        if payload.get("title") != expected_title:
            errors.append(f"{path.as_posix()} title must equal '{expected_title}'")

    example_expectations = (
        (AGENT_BUILD_SNAPSHOT_EXAMPLE_PATH, "agent_build_snapshot_v1"),
        (REPUTATION_LEDGER_EXAMPLE_PATH, "reputation_ledger_v1"),
        (QUEST_RUN_RESULT_EXAMPLE_PATH, "quest_run_result_v1"),
        (FRONTEND_PROJECTION_BUNDLE_EXAMPLE_PATH, "frontend_projection_bundle_v1"),
    )
    for path, expected_version in example_expectations:
        try:
            payload = json.loads((ROOT / path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"{path.as_posix()} must contain valid JSON: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path.as_posix()} must be a JSON object")
            continue
        if payload.get("schema_version") != expected_version:
            errors.append(f"{path.as_posix()} schema_version must equal '{expected_version}'")
        if payload.get("public_safe") is not True:
            errors.append(f"{path.as_posix()} public_safe must be true")

    generated_expectations = (
        (
            GENERATED_AGENT_BUILD_SNAPSHOTS_PATH,
            "agent_build_snapshot_collection_v1",
            "builds",
            "agent_build_snapshot_v1",
        ),
        (
            GENERATED_REPUTATION_LEDGERS_PATH,
            "reputation_ledger_collection_v1",
            "ledgers",
            "reputation_ledger_v1",
        ),
        (
            GENERATED_QUEST_RUN_RESULTS_PATH,
            "quest_run_result_collection_v1",
            "runs",
            "quest_run_result_v1",
        ),
        (
            GENERATED_FRONTEND_PROJECTION_BUNDLES_PATH,
            "frontend_projection_bundle_collection_v1",
            "bundles",
            "frontend_projection_bundle_v1",
        ),
    )
    for path, expected_version, array_key, item_version in generated_expectations:
        try:
            payload = json.loads((ROOT / path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"{path.as_posix()} must contain valid JSON: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path.as_posix()} must be a JSON object")
            continue
        if payload.get("schema_version") != expected_version:
            errors.append(f"{path.as_posix()} schema_version must equal '{expected_version}'")
        items = payload.get(array_key)
        if not isinstance(items, list) or not items:
            errors.append(f"{path.as_posix()} must include a non-empty '{array_key}' array")
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{path.as_posix()} item {index} must be a JSON object")
                continue
            if item.get("schema_version") != item_version:
                errors.append(
                    f"{path.as_posix()} item {index} schema_version must equal '{item_version}'"
                )
            if item.get("public_safe") is not True:
                errors.append(f"{path.as_posix()} item {index} public_safe must be true")
        if path == GENERATED_FRONTEND_PROJECTION_BUNDLES_PATH:
            first_bundle = items[0]
            if first_bundle.get("vocabulary_overlay_ref") != "Agents-of-Abyss/generated/dual_vocabulary_overlay.json":
                errors.append(
                    "generated/rpg/frontend_projection_bundles.json must reference Agents-of-Abyss/generated/dual_vocabulary_overlay.json"
                )

    expected_catalog = []
    expected_dispatch = []
    active_quest_ids: list[str] = []
    closed_quest_ids: list[str] = []
    for quest_id in QUEST_IDS:
        quest_path = ROOT / "quests" / f"{quest_id}.yaml"
        try:
            quest_payload = load_structured_object(quest_path)
        except FileNotFoundError:
            continue
        except Exception as exc:
            errors.append(f"{quest_path.relative_to(ROOT)} must parse cleanly: {exc}")
            continue

        if quest_payload.get("schema_version") != "work_quest_v1":
            errors.append(f"{quest_id} schema_version must equal 'work_quest_v1'")
        if quest_payload.get("id") != quest_id:
            errors.append(f"{quest_path.relative_to(ROOT)} id must equal '{quest_id}'")
        if quest_payload.get("repo") != "abyss-stack":
            errors.append(f"{quest_id} repo must equal 'abyss-stack'")
        if quest_payload.get("public_safe") is not True:
            errors.append(f"{quest_id} public_safe must be true")
        if quest_payload.get("state") in CLOSED_QUEST_STATES:
            closed_quest_ids.append(quest_id)
        else:
            active_quest_ids.append(quest_id)

        notes = quest_payload.get("notes", "")
        if not isinstance(notes, str):
            errors.append(f"{quest_id} notes must be a string")
        elif "ATM10-Agent" in notes or "aoa-sdk" in notes:
            errors.append(f"{quest_id} notes must stay in scope for the current contour")

        if quest_id == "ABYSS-STACK-Q-0003":
            if quest_payload.get("control_mode") != "human_gate":
                errors.append("ABYSS-STACK-Q-0003 control_mode must stay human_gate")
            if quest_payload.get("risk") != "r3_side_effect":
                errors.append("ABYSS-STACK-Q-0003 risk must stay r3_side_effect")
            anchor_ref = quest_payload.get("anchor_ref")
            if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "docs/RENDER_TRUTH.md":
                errors.append("ABYSS-STACK-Q-0003 must stay anchored to docs/RENDER_TRUTH.md")
            note = anchor_ref.get("note") if isinstance(anchor_ref, dict) else ""
            if not isinstance(note, str) or "docs/FIRST_RUN.md" not in note or "docs/DOCTOR.md" not in note:
                errors.append("ABYSS-STACK-Q-0003 anchor note must mention docs/FIRST_RUN.md and docs/DOCTOR.md")
        elif quest_id == "ABYSS-STACK-Q-0005":
            if quest_payload.get("kind") != "doctrine":
                errors.append("ABYSS-STACK-Q-0005 kind must stay doctrine")
            anchor_ref = quest_payload.get("anchor_ref")
            if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "docs/RPG_RUNTIME_FRONTEND_POSTURE.md":
                errors.append(
                    "ABYSS-STACK-Q-0005 must stay anchored to docs/RPG_RUNTIME_FRONTEND_POSTURE.md"
                )
            note = anchor_ref.get("note") if isinstance(anchor_ref, dict) else ""
            if not isinstance(note, str) or "shadow authority layer" not in note:
                errors.append(
                    "ABYSS-STACK-Q-0005 anchor note must mention the shadow authority risk"
                )
            if not isinstance(notes, str) or "global rank engine" not in notes or "auto-complete quest writer" not in notes:
                errors.append(
                    "ABYSS-STACK-Q-0005 notes must keep the runtime authority guardrail language"
                )
        elif quest_id == "ABYSS-STACK-Q-0006":
            if quest_payload.get("kind") != "doctrine":
                errors.append("ABYSS-STACK-Q-0006 kind must stay doctrine")
            anchor_ref = quest_payload.get("anchor_ref")
            if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "docs/RPG_RUNTIME_COLLECTIONS.md":
                errors.append(
                    "ABYSS-STACK-Q-0006 must stay anchored to docs/RPG_RUNTIME_COLLECTIONS.md"
                )
            note = anchor_ref.get("note") if isinstance(anchor_ref, dict) else ""
            if not isinstance(note, str) or "read models" not in note or "route or quest authority" not in note:
                errors.append(
                    "ABYSS-STACK-Q-0006 anchor note must mention read models and route or quest authority"
                )
            if not isinstance(notes, str) or "live /rpg/* endpoints" not in notes or "quest mutation" not in notes:
                errors.append(
                    "ABYSS-STACK-Q-0006 notes must keep the no-live-endpoints and no-quest-mutation guardrails"
                )
        elif quest_id == "ABYSS-STACK-Q-0007":
            if quest_payload.get("kind") != "doctrine":
                errors.append("ABYSS-STACK-Q-0007 kind must stay doctrine")
            anchor_ref = quest_payload.get("anchor_ref")
            if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "docs/DIAGNOSTIC_SPINE.md":
                errors.append(
                    "ABYSS-STACK-Q-0007 must stay anchored to docs/DIAGNOSTIC_SPINE.md"
                )
            note = anchor_ref.get("note") if isinstance(anchor_ref, dict) else ""
            if not isinstance(note, str) or "read model" not in note or "mutation authority" not in note:
                errors.append(
                    "ABYSS-STACK-Q-0007 anchor note must mention read model and mutation authority"
                )
            if not isinstance(notes, str) or "free self-repair" not in notes or "runtime quest authority" not in notes:
                errors.append(
                    "ABYSS-STACK-Q-0007 notes must keep the no-free-self-repair and no-runtime-quest-authority guardrails"
                )

        try:
            expected_catalog.append(build_expected_quest_catalog_entry(quest_id, quest_payload))
            expected_dispatch.append(build_expected_quest_dispatch_entry(quest_id, quest_payload))
        except Exception as exc:
            errors.append(f"{quest_id} dispatch alignment failed: {exc}")

    for quest_id in active_quest_ids:
        if quest_id not in questbook_text:
            errors.append(f"QUESTBOOK.md must reference active quest id '{quest_id}'")
    for quest_id in closed_quest_ids:
        if quest_id in questbook_text:
            errors.append(f"QUESTBOOK.md must not list closed quest id '{quest_id}'")

    try:
        catalog_payload = json.loads((ROOT / QUEST_CATALOG_EXAMPLE_PATH).read_text(encoding="utf-8"))
    except FileNotFoundError:
        catalog_payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"{QUEST_CATALOG_EXAMPLE_PATH.as_posix()} must contain valid JSON: {exc}")
        catalog_payload = None
    if catalog_payload is not None and catalog_payload != expected_catalog:
        errors.append("examples/quest_catalog.min.example.json must stay aligned with quests/*.yaml")

    try:
        dispatch_payload = json.loads((ROOT / QUEST_DISPATCH_EXAMPLE_PATH).read_text(encoding="utf-8"))
    except FileNotFoundError:
        dispatch_payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"{QUEST_DISPATCH_EXAMPLE_PATH.as_posix()} must contain valid JSON: {exc}")
        dispatch_payload = None
    if dispatch_payload is not None and dispatch_payload != expected_dispatch:
        errors.append("examples/quest_dispatch.min.example.json must stay aligned with quests/*.yaml")


def iter_sync_managed_files() -> list[Path]:
    files: list[Path] = []

    for item in SYNC_MANAGED_ITEMS:
        source_path = ROOT / item
        if source_path.is_file():
            files.append(Path(item))
            continue
        if not source_path.is_dir():
            continue

        for child in source_path.rglob("*"):
            if not child.is_file():
                continue
            rel = child.relative_to(ROOT)
            if any(part in PARITY_IGNORED_PARTS for part in rel.parts):
                continue
            if child.suffix.lower() in PARITY_IGNORED_SUFFIXES:
                continue
            files.append(rel)

    return sorted(files)


def validate_profiles(errors: list[str]) -> None:
    for profile in sorted(PROFILE_DIR.glob("*.txt")):
        modules = load_names(profile)
        if not modules:
            errors.append(f"profile has no modules: {profile.relative_to(ROOT)}")
            continue

        seen = set(modules)
        for module_name in modules:
            module_path = MODULE_DIR / module_name
            if not module_path.exists():
                errors.append(
                    f"profile {profile.name} references missing module {module_name}"
                )

        for module_name, requirements in MODULE_REQUIREMENTS.items():
            if module_name not in seen:
                continue

            missing = sorted(
                requirement for requirement in requirements if requirement not in seen
            )
            if missing:
                errors.append(
                    f"profile {profile.name} includes {module_name} but is missing required modules: {', '.join(missing)}"
                )

    sidecar_module = (MODULE_DIR / "44-llamacpp-agent-sidecar.yml").read_text(encoding="utf-8")
    if 'AOA_FEDERATED_RUN_ENABLED: "true"' not in sidecar_module:
        errors.append(
            'compose/modules/44-llamacpp-agent-sidecar.yml must enable AOA_FEDERATED_RUN_ENABLED for governed advisory runs'
        )
    agent_api_module = (MODULE_DIR / "41-agent-api.yml").read_text(encoding="utf-8")
    if "AOA_FEDERATED_RUN_ENABLED:" in agent_api_module:
        errors.append(
            "compose/modules/41-agent-api.yml must not override AOA_FEDERATED_RUN_ENABLED so the runtime secret can control the gate"
        )


def validate_presets(errors: list[str]) -> None:
    for preset in sorted(PRESET_DIR.glob("*.txt")):
        profiles = load_names(preset)
        if not profiles:
            errors.append(f"preset has no profiles: {preset.relative_to(ROOT)}")
            continue

        for profile_name in profiles:
            profile_path = PROFILE_DIR / f"{profile_name}.txt"
            if not profile_path.exists():
                errors.append(
                    f"preset {preset.name} references missing profile {profile_name}"
                )


def validate_paths(errors: list[str]) -> None:
    for path in iter_text_files():
        text = read_text_or_none(path)
        if text is None:
            continue
        if LEGACY_PATTERN.search(text) and path not in LEGACY_ALLOWED:
            errors.append(
                f"legacy path '{LEGACY_PATH}' found in {path.relative_to(ROOT)}"
            )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "Fedora-first" not in readme:
        errors.append("README.md must state Fedora-first posture")
    if "Windows-usable" not in readme:
        errors.append("README.md must state Windows-usable posture")
    if "docs/RECURRENCE_RUNTIME_POLICY.md" not in readme:
        errors.append("README.md must route readers to docs/RECURRENCE_RUNTIME_POLICY.md")
    if "docs/REFERENCE_PLATFORM.md" not in readme:
        errors.append("README.md must route readers to docs/REFERENCE_PLATFORM.md")
    if "docs/REFERENCE_PLATFORM_SPEC.md" not in readme:
        errors.append("README.md must route readers to docs/REFERENCE_PLATFORM_SPEC.md")
    if "docs/MACHINE_FIT_POLICY.md" not in readme:
        errors.append("README.md must route readers to docs/MACHINE_FIT_POLICY.md")
    if "docs/PLATFORM_ADAPTATION_POLICY.md" not in readme:
        errors.append("README.md must route readers to docs/PLATFORM_ADAPTATION_POLICY.md")
    if "docs/BRANCH_POLICY.md" not in readme:
        errors.append("README.md must route readers to docs/BRANCH_POLICY.md")
    if "docs/MEMO_RUNTIME_SEAM.md" not in readme:
        errors.append("README.md must route readers to docs/MEMO_RUNTIME_SEAM.md")
    if "docs/EVAL_RUNTIME_SEAM.md" not in readme:
        errors.append("README.md must route readers to docs/EVAL_RUNTIME_SEAM.md")
    if "docs/PLAYBOOK_RUNTIME_SEAM.md" not in readme:
        errors.append("README.md must route readers to docs/PLAYBOOK_RUNTIME_SEAM.md")
    if "docs/KAG_RUNTIME_SEAM.md" not in readme:
        errors.append("README.md must route readers to docs/KAG_RUNTIME_SEAM.md")

    local_ai_trials = (ROOT / "docs" / "LOCAL_AI_TRIALS.md").read_text(encoding="utf-8")
    for required_snippet in (
        "TRUTH_SURFACES.md",
        "GOVERNED_EXECUTION.md",
        "prepare-wave W4 --lane docs",
        "apply-case W4 <case-id>",
        "scripts/aoa-governed-run prepare-canary",
        "scripts/aoa-governed-run materialize-canaries",
        "scripts/aoa-governed-run prepare-request",
        "scripts/aoa-governed-run run --request-file",
        "scripts/aoa-governed-run resume",
        "status --all --explain",
        "scripts/aoa-w5-pilot materialize",
        "run-scenario <scenario-id> --until milestone",
        "resume-scenario <scenario-id>",
        "implementation_patch",
        "proposal.edit-spec.json",
        "exact_replace",
        "anchored_replace",
        "deterministically inside the runner",
        "script_refresh",
        "approval.status.json",
        "isolated git worktree",
        "landing.diff",
        "rollback.status.json",
        "governed-canary-catalog.json",
        "source_authored",
        "live_available",
        "aoa-status --autonomy",
    ):
        if required_snippet not in local_ai_trials:
            errors.append(
                f"docs/LOCAL_AI_TRIALS.md must mention `{required_snippet}`"
            )

    truth_doc = (ROOT / "docs" / "TRUTH_SURFACES.md").read_text(encoding="utf-8")
    for required_snippet in (
        "source_authored",
        "deployed",
        "trial_proven",
        "live_available",
        "~/src/abyss-stack",
        "AOA_SOURCE_ROOT",
        "/srv/abyss-stack",
        "trial_proven is not a synonym for production readiness",
        "aoa-llamacpp-pilot verify",
        "aoa-sync-federation-surfaces --check --json",
        "aoa-status --autonomy --json",
    ):
        if required_snippet not in truth_doc:
            errors.append(
                f"docs/TRUTH_SURFACES.md must mention `{required_snippet}`"
            )

    governed_doc = (ROOT / "docs" / "GOVERNED_EXECUTION.md").read_text(encoding="utf-8")
    for required_snippet in (
        "aoa-governed-run prepare-request",
        "aoa-governed-run prepare-canary",
        "aoa-governed-run materialize-canaries",
        "aoa-governed-run run --request-file",
        "approval.status.json",
        "landing.diff",
        "rollback.status.json",
        "autonomy_gate_failed",
        "policy_denied",
        "scope_violation",
        "blocked_reason",
        "safe_resume_command",
        "canary_proven",
        "trusted",
        "aoa-status --autonomy --json",
        "Configs/agent-api/governed-execution-policy.yaml",
        "Configs/agent-api/governed-canary-catalog.json",
    ):
        if required_snippet not in governed_doc:
            errors.append(f"docs/GOVERNED_EXECUTION.md must mention `{required_snippet}`")

    w5_doc = (ROOT / "docs" / "W5_PILOT.md").read_text(encoding="utf-8")
    for required_snippet in (
        "TRUTH_SURFACES.md",
        "http://127.0.0.1:5403/run",
        "scripts/aoa-w5-pilot materialize",
        "run-scenario <scenario-id> --until milestone|done",
        "resume-scenario <scenario-id>",
        "status --all",
        "plan_freeze",
        "first_mutation",
        "landing",
        "stack-sync-federation-check-mode",
        "implementation_patch",
        "trial_proven",
        "live_available",
        "aoa-status --autonomy",
    ):
        if required_snippet not in w5_doc:
            errors.append(f"docs/W5_PILOT.md must mention `{required_snippet}`")

    w6_doc = (ROOT / "docs" / "W6_PILOT.md").read_text(encoding="utf-8")
    for required_snippet in (
        "TRUTH_SURFACES.md",
        "http://127.0.0.1:5403/run",
        "stack-sync-federation-json-check-report",
        "llamacpp-pilot-verify-command",
        "trial_proven",
        "live_available",
        "aoa-status --autonomy",
    ):
        if required_snippet not in w6_doc:
            errors.append(f"docs/W6_PILOT.md must mention `{required_snippet}`")

    paths_doc = (ROOT / "docs" / "PATHS.md").read_text(encoding="utf-8")
    if "/srv/abyss-stack" not in paths_doc:
        errors.append("docs/PATHS.md must mention /srv/abyss-stack")
    if "WSL2" not in paths_doc:
        errors.append(
            "docs/PATHS.md should mention WSL2 in the Windows-usable model"
        )
    if "AOA_ROUTING_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_ROUTING_ROOT")
    if "AOA_SOURCE_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_SOURCE_ROOT")
    if "AOA_MEMO_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_MEMO_ROOT")
    if "AOA_EVALS_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_EVALS_ROOT")
    if "AOA_PLAYBOOKS_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_PLAYBOOKS_ROOT")
    if "AOA_KAG_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_KAG_ROOT")
    if "AOA_TOS_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_TOS_ROOT")

    deployment_doc = (ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    for required_snippet in (
        "source-authored change is not live until `scripts/aoa-sync-configs` updates `/srv/abyss-stack/Configs`",
        "python scripts/validate_stack.py --parity-check",
        "aoa-status --autonomy",
        "governed-execution-policy.yaml",
        "governed-canary-catalog.json",
        "scripts/aoa-governed-run",
        "scripts/aoa-bootstrap-configs --force",
        "Logs/governed-runs",
    ):
        if required_snippet not in deployment_doc:
            errors.append(
                f"docs/DEPLOYMENT.md must mention `{required_snippet}`"
            )
    if "scripts/aoa-sync-federation-surfaces --layer aoa-routing" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-routing federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer aoa-memo" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-memo federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer aoa-evals" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-evals federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer aoa-playbooks" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-playbooks federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer aoa-kag" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-kag federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer tos-source" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention tos-source federation sync")

    profiles_doc = (ROOT / "docs" / "PROFILES.md").read_text(encoding="utf-8")
    if "aoa-routing advisory seam" not in profiles_doc:
        errors.append("docs/PROFILES.md must describe the aoa-routing advisory seam")
    if "aoa-memo" not in profiles_doc:
        errors.append("docs/PROFILES.md must describe the aoa-memo recall seam")
    if "aoa-evals" not in profiles_doc:
        errors.append("docs/PROFILES.md must describe the aoa-evals eval selection seam")
    if "aoa-playbooks" not in profiles_doc:
        errors.append("docs/PROFILES.md must describe the aoa-playbooks advisory seam")
    if "aoa-kag" not in profiles_doc:
        errors.append("docs/PROFILES.md must describe the aoa-kag advisory seam")
    if "tos-source" not in profiles_doc:
        errors.append("docs/PROFILES.md must describe the tos-source handoff seam")

    recipes_doc = (ROOT / "docs" / "PROFILE_RECIPES.md").read_text(encoding="utf-8")
    if "aoa-routing" not in recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must mention aoa-routing")
    if "aoa-memo" not in recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must mention aoa-memo")
    if "aoa-evals" not in recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must mention aoa-evals")
    if "aoa-playbooks" not in recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must mention aoa-playbooks")
    if "aoa-kag" not in recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must mention aoa-kag")
    if "tos-source" not in recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must mention tos-source")

    catalog_doc = (ROOT / "docs" / "SERVICE_CATALOG.md").read_text(encoding="utf-8")
    if "aoa-routing advisory routing surfaces" not in catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention aoa-routing advisory routing surfaces")
    if "aoa-memo" not in catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention aoa-memo")
    if "aoa-evals" not in catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention aoa-evals")
    if "aoa-playbooks" not in catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention aoa-playbooks")
    if "aoa-kag" not in catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention aoa-kag")
    if "tos-source" not in catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention tos-source")
    if "aoa-governed-run" not in catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention aoa-governed-run")
    if "promotion summaries" not in catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention promotion summaries")

    storage_doc = (ROOT / "docs" / "STORAGE_LAYOUT.md").read_text(encoding="utf-8")
    if "Knowledge/federation/aoa-routing/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-routing/")
    if "Knowledge/federation/aoa-memo/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-memo/")
    if "Knowledge/federation/aoa-evals/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-evals/")
    if "Knowledge/federation/aoa-playbooks/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-playbooks/")
    if "Knowledge/federation/aoa-kag/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-kag/")
    if "Knowledge/federation/tos-source/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Knowledge/federation/tos-source/")
    if "Logs/memo-exports/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Logs/memo-exports/")
    if "Logs/eval-exports/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Logs/eval-exports/")
    if "Logs/rpg/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Logs/rpg/")
    if "generated/rpg/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention generated/rpg/")

    lifecycle_doc = (ROOT / "docs" / "LIFECYCLE.md").read_text(encoding="utf-8")
    for required_snippet in (
        "source_authored",
        "deployed",
        "trial_proven",
        "live_available",
        "python scripts/validate_stack.py --parity-check",
    ):
        if required_snippet not in lifecycle_doc:
            errors.append(f"docs/LIFECYCLE.md must mention `{required_snippet}`")

    playbook_runtime_doc = (ROOT / "docs" / "PLAYBOOK_RUNTIME_SEAM.md").read_text(encoding="utf-8")
    for required_snippet in (
        "aoa-governed-run",
        "governed-execution-policy.yaml",
        "trust state",
        "runtime permission semantics still live in `abyss-stack`",
    ):
        if required_snippet not in playbook_runtime_doc:
            errors.append(f"docs/PLAYBOOK_RUNTIME_SEAM.md must mention `{required_snippet}`")

    recurrence_doc = (ROOT / "docs" / "RECURRENCE_RUNTIME_POLICY.md").read_text(encoding="utf-8")
    for required_snippet in (
        "governed-execution-policy.yaml",
        "runtime execution permissions only",
        "langchain-api /run/federated",
    ):
        if required_snippet not in recurrence_doc:
            errors.append(f"docs/RECURRENCE_RUNTIME_POLICY.md must mention `{required_snippet}`")

    try:
        governed_policy = load_structured_object(
            ROOT / "config-templates" / "Configs" / "agent-api" / "governed-execution-policy.yaml"
        )
    except Exception as exc:
        errors.append(f"governed execution policy must parse cleanly: {exc}")
    else:
        if governed_policy.get("surface_type") != "runtime_governed_execution_policy":
            errors.append("governed execution policy must declare surface_type=runtime_governed_execution_policy")
        global_rules = governed_policy.get("global_rules")
        if not isinstance(global_rules, dict) or global_rules.get("gate_mode") != "fail_closed":
            errors.append("governed execution policy must set global_rules.gate_mode=fail_closed")
        if not isinstance(global_rules, dict) or not isinstance(global_rules.get("default_target_id"), str):
            errors.append("governed execution policy must declare global_rules.default_target_id")
        promotion_criteria = global_rules.get("promotion_criteria")
        if not isinstance(promotion_criteria, dict) or "canary_proven" not in promotion_criteria or "trusted" not in promotion_criteria:
            errors.append("governed execution policy must define promotion_criteria.canary_proven and promotion_criteria.trusted")
        repo_scope_gate = global_rules.get("repo_scope_expansion_gate")
        if not isinstance(repo_scope_gate, dict):
            errors.append("governed execution policy must define repo_scope_expansion_gate")
        targets = governed_policy.get("targets")
        if not isinstance(targets, dict) or "abyss-stack" not in targets or "aoa-routing" not in targets:
            errors.append("governed execution policy must declare explicit abyss-stack and aoa-routing targets")
        else:
            abyss_stack_target = targets.get("abyss-stack") or {}
            routing_target = targets.get("aoa-routing") or {}
            abyss_stack_playbooks = abyss_stack_target.get("playbooks") or {}
            routing_playbooks = routing_target.get("playbooks") or {}
            abyss_stack_playbook = abyss_stack_playbooks.get("AOA-P-0011") or {}
            routing_playbook = routing_playbooks.get("AOA-P-0011") or {}
            if abyss_stack_target.get("default_repo_root") != "~/src/abyss-stack":
                errors.append(
                    "abyss-stack governed policy default_repo_root must use the portable ~/src/abyss-stack default"
                )
            if abyss_stack_playbook.get("trust_state") not in {"experimental", "canary_proven", "trusted"}:
                errors.append("abyss-stack AOA-P-0011 governed policy entry must declare a valid trust_state")
            if routing_playbook.get("trust_state") not in {"experimental", "canary_proven", "trusted"}:
                errors.append("aoa-routing AOA-P-0011 governed policy entry must declare a valid trust_state")
            if not isinstance(abyss_stack_playbook.get("task_class"), str):
                errors.append("abyss-stack AOA-P-0011 governed policy entry must declare task_class")
            if not isinstance(routing_playbook.get("task_class"), str):
                errors.append("aoa-routing AOA-P-0011 governed policy entry must declare task_class")
            if routing_playbook.get("evidence_since_run_id") is not None and not isinstance(
                routing_playbook.get("evidence_since_run_id"), str
            ):
                errors.append("aoa-routing AOA-P-0011 governed policy evidence_since_run_id must be a string when set")
            routing_acceptance = routing_playbook.get("acceptance_commands")
            if not isinstance(routing_acceptance, list) or len(routing_acceptance) < 2:
                errors.append("aoa-routing AOA-P-0011 governed policy entry must declare explicit acceptance commands")
            else:
                required_root_flags = (
                    "--techniques-root /srv/aoa-techniques",
                    "--skills-root /srv/aoa-skills",
                    "--evals-root /srv/aoa-evals",
                    "--memo-root /srv/aoa-memo",
                    "--agents-root /srv/aoa-agents",
                    "--aoa-root /srv/Agents-of-Abyss",
                    "--playbooks-root /srv/aoa-playbooks",
                    "--kag-root /srv/aoa-kag",
                    "--tos-root /srv/Tree-of-Sophia",
                )
                for required_command in (
                    "python scripts/validate_router.py",
                    "python scripts/build_router.py --check",
                ):
                    command = next(
                        (
                            item
                            for item in routing_acceptance
                            if isinstance(item, str) and item.startswith(required_command)
                        ),
                        None,
                    )
                    if command is None:
                        errors.append(
                            f"aoa-routing AOA-P-0011 governed policy entry must include {required_command}"
                        )
                        continue
                    for flag in required_root_flags:
                        if flag not in command:
                            errors.append(
                                f"aoa-routing AOA-P-0011 governed policy {required_command} must pin {flag}"
                            )

    try:
        canary_catalog = load_structured_object(
            ROOT / "config-templates" / "Configs" / "agent-api" / "governed-canary-catalog.json"
        )
    except Exception as exc:
        errors.append(f"governed canary catalog must parse cleanly: {exc}")
    else:
        if canary_catalog.get("surface_type") != "runtime_governed_execution_canary_catalog":
            errors.append("governed canary catalog must declare surface_type=runtime_governed_execution_canary_catalog")
        canaries = canary_catalog.get("canaries")
        if not isinstance(canaries, list) or not canaries:
            errors.append("governed canary catalog must contain at least one canary entry")
        else:
            target_ids = {item.get("target_id") for item in canaries if isinstance(item, dict)}
            if "abyss-stack" not in target_ids or "aoa-routing" not in target_ids:
                errors.append("governed canary catalog must include abyss-stack and aoa-routing canaries")


def validate_scripts(errors: list[str]) -> None:
    script_names = {path.name for path in (ROOT / "scripts").iterdir() if path.is_file()}
    missing = sorted(REQUIRED_SCRIPTS - script_names)

    for name in missing:
        errors.append(f"missing required script: scripts/{name}")

    llamacpp_pilot = (ROOT / "scripts" / "aoa-llamacpp-pilot").read_text(encoding="utf-8")
    if "podman\", \"network\", \"connect\"" not in llamacpp_pilot:
        errors.append("scripts/aoa-llamacpp-pilot must connect the sidecar to the primary runtime network")
    if "abyss_default" not in llamacpp_pilot:
        errors.append("scripts/aoa-llamacpp-pilot must mention abyss_default as the primary runtime network")


def validate_required_files(errors: list[str]) -> None:
    for path in sorted(REQUIRED_FILES):
        if not path.exists():
            errors.append(f"missing required file: {path.relative_to(ROOT)}")


def validate_federation_required_files(errors: list[str]) -> None:
    for rel_path, expected_refs in FEDERATION_REQUIRED_RUNTIME_INPUTS.items():
        path = ROOT / rel_path
        try:
            payload = load_structured_object(path)
        except Exception as exc:
            errors.append(f"{rel_path.as_posix()} must stay loadable: {exc}")
            continue

        required_files = payload.get("required_files")
        if not isinstance(required_files, list):
            errors.append(f"{rel_path.as_posix()} must expose required_files as a list")
            continue

        configured_refs = {
            item for item in required_files if isinstance(item, str)
        }
        missing_refs = sorted(expected_refs - configured_refs)
        if missing_refs:
            errors.append(
                f"{rel_path.as_posix()} must list required_files for runtime-loaded federation inputs: "
                + ", ".join(missing_refs)
            )


def validate_reference_platform(errors: list[str]) -> None:
    reference_platform = (ROOT / "docs" / "REFERENCE_PLATFORM.md").read_text(
        encoding="utf-8"
    )
    if "aoa-host-facts" not in reference_platform:
        errors.append("docs/REFERENCE_PLATFORM.md must mention aoa-host-facts")
    if "REFERENCE_PLATFORM_SPEC.md" not in reference_platform:
        errors.append(
            "docs/REFERENCE_PLATFORM.md must point to REFERENCE_PLATFORM_SPEC.md"
        )

    doctor_doc = (ROOT / "docs" / "DOCTOR.md").read_text(encoding="utf-8")
    if "aoa-host-facts" not in doctor_doc:
        errors.append("docs/DOCTOR.md must mention aoa-host-facts")

    first_run_doc = (ROOT / "docs" / "FIRST_RUN.md").read_text(encoding="utf-8")
    if "reference-host.public.json" not in first_run_doc:
        errors.append(
            "docs/FIRST_RUN.md must mention reference-host.public.json capture"
        )

    spec_doc = (ROOT / "docs" / "REFERENCE_PLATFORM_SPEC.md").read_text(
        encoding="utf-8"
    )
    if "latest.private.json" not in spec_doc:
        errors.append(
            "docs/REFERENCE_PLATFORM_SPEC.md must define the local private capture path"
        )

    schema = json.loads(
        (ROOT / "docs" / "reference-platform" / "schema.v1.json").read_text(
            encoding="utf-8"
        )
    )
    if schema.get("title") != "AoA Host Facts":
        errors.append("schema.v1.json must describe AoA Host Facts")

    example = json.loads(
        (
            ROOT
            / "docs"
            / "reference-platform"
            / "reference-host.public.json.example"
        ).read_text(encoding="utf-8")
    )
    if example.get("artifact_kind") != "aoa.host-facts":
        errors.append(
            "reference-host.public.json.example must use artifact_kind aoa.host-facts"
        )
    if example.get("capture_mode") != "public":
        errors.append(
            "reference-host.public.json.example must use capture_mode public"
        )
    if example.get("captured_by") != "scripts/aoa-host-facts":
        errors.append(
            "reference-host.public.json.example must use captured_by scripts/aoa-host-facts"
        )


def validate_platform_adaptations(errors: list[str]) -> None:
    boundaries_doc = (ROOT / "BOUNDARIES.md").read_text(encoding="utf-8")
    if "platform-adaptation" not in boundaries_doc:
        errors.append("BOUNDARIES.md must mention platform-adaptation records")

    runbook_doc = (ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-platform-adaptation" not in runbook_doc:
        errors.append("docs/RUNBOOK.md must mention aoa-platform-adaptation")

    windows_perf_doc = (ROOT / "docs" / "WINDOWS_PERFORMANCE.md").read_text(encoding="utf-8")
    if "aoa-platform-adaptation" not in windows_perf_doc:
        errors.append("docs/WINDOWS_PERFORMANCE.md must mention aoa-platform-adaptation")

    storage_doc = (ROOT / "docs" / "STORAGE_LAYOUT.md").read_text(encoding="utf-8")
    if "Logs/platform-adaptations/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Logs/platform-adaptations/")

    policy_doc = (ROOT / "docs" / "PLATFORM_ADAPTATION_POLICY.md").read_text(encoding="utf-8")
    if "aoa-host-facts" not in policy_doc:
        errors.append("docs/PLATFORM_ADAPTATION_POLICY.md must mention aoa-host-facts")
    if "runtime benchmarks" not in policy_doc and "runtime benchmark" not in policy_doc:
        errors.append("docs/PLATFORM_ADAPTATION_POLICY.md must mention runtime benchmarks")

    schema = json.loads(
        (ROOT / "docs" / "platform-adaptations" / "schema.v1.json").read_text(
            encoding="utf-8"
        )
    )
    if schema.get("title") != "AoA Platform Adaptation Record":
        errors.append("platform-adaptations/schema.v1.json must describe AoA Platform Adaptation Record")

    example = json.loads(
        (ROOT / "docs" / "platform-adaptations" / "platform-adaptation.public.json.example").read_text(
            encoding="utf-8"
        )
    )
    if example.get("artifact_kind") != "aoa.platform-adaptation":
        errors.append("platform-adaptation.public.json.example must use artifact_kind aoa.platform-adaptation")
    if example.get("capture_mode") != "public":
        errors.append("platform-adaptation.public.json.example must use capture_mode public")
    if example.get("captured_by") != "scripts/aoa-platform-adaptation":
        errors.append("platform-adaptation.public.json.example must use captured_by scripts/aoa-platform-adaptation")


def validate_branch_policy(errors: list[str]) -> None:
    contributing_doc = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    if "docs/BRANCH_POLICY.md" not in contributing_doc:
        errors.append("CONTRIBUTING.md must point to docs/BRANCH_POLICY.md")

    policy_doc = (ROOT / "docs" / "BRANCH_POLICY.md").read_text(encoding="utf-8")
    required_snippets = [
        "`main` is the only long-lived branch",
        "Delete the topic branch locally and on `origin`.",
        "If a branch was effectively landed by squash, cherry-pick, or a rewritten equivalent, do not merge it again.",
        "/srv/abyss-stack",
        "~/src/abyss-stack",
        "AOA_SOURCE_ROOT",
    ]
    for snippet in required_snippets:
        if snippet not in policy_doc:
            errors.append(f"docs/BRANCH_POLICY.md must mention: {snippet}")


def validate_return_runtime_contract(errors: list[str]) -> None:
    templates_readme = (ROOT / "config-templates" / "README.md").read_text(encoding="utf-8")
    if "Configs/agent-api/" not in templates_readme:
        errors.append("config-templates/README.md must mention Configs/agent-api/")
    if "governed-canary-catalog.json" not in templates_readme:
        errors.append("config-templates/README.md must mention governed-canary-catalog.json")

    deployment_doc = (ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    if "Configs/agent-api/return-policy.yaml" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention Configs/agent-api/return-policy.yaml")

    first_run_doc = (ROOT / "docs" / "FIRST_RUN.md").read_text(encoding="utf-8")
    if "Configs/agent-api/return-policy.yaml" not in first_run_doc:
        errors.append("docs/FIRST_RUN.md must mention Configs/agent-api/return-policy.yaml")

    render_truth_doc = (ROOT / "docs" / "RENDER_TRUTH.md").read_text(encoding="utf-8")
    if "return-policy" not in render_truth_doc:
        errors.append("docs/RENDER_TRUTH.md should mention return-policy mounts when the wrapper is enabled")
    if "aoa-status --autonomy" not in render_truth_doc:
        errors.append("docs/RENDER_TRUTH.md must mention aoa-status --autonomy")
    if "/surface-status" not in render_truth_doc:
        errors.append("docs/RENDER_TRUTH.md must mention /surface-status")

    policy_schema = json.loads(
        (ROOT / "schemas" / "runtime-return-policy.schema.json").read_text(encoding="utf-8")
    )
    if policy_schema.get("title") != "abyss-stack runtime return policy":
        errors.append("runtime-return-policy.schema.json must describe abyss-stack runtime return policy")
    policy_surface_type = policy_schema.get("properties", {}).get("surface_type", {})
    if policy_surface_type.get("const") != "runtime_return_policy":
        errors.append("runtime-return-policy.schema.json must pin surface_type.const to runtime_return_policy")

    event_schema = json.loads(
        (ROOT / "schemas" / "runtime-return-event.schema.json").read_text(encoding="utf-8")
    )
    if event_schema.get("title") != "abyss-stack runtime return event":
        errors.append("runtime-return-event.schema.json must describe abyss-stack runtime return event")
    event_surface_type = event_schema.get("properties", {}).get("surface_type", {})
    if event_surface_type.get("const") != "runtime_return_event":
        errors.append("runtime-return-event.schema.json must pin surface_type.const to runtime_return_event")


def validate_runtime_hygiene_contracts(errors: list[str]) -> None:
    def read_required_text(relative_path: Path) -> str:
        try:
            return (ROOT / relative_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            errors.append(f"missing required file: {relative_path.as_posix()}")
            return ""

    def read_required_json(relative_path: Path) -> dict[str, object] | None:
        try:
            payload = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            errors.append(f"missing required file: {relative_path.as_posix()}")
            return None
        except json.JSONDecodeError as exc:
            errors.append(f"{relative_path.as_posix()} must contain valid JSON: {exc}")
            return None
        if not isinstance(payload, dict):
            errors.append(f"{relative_path.as_posix()} must contain a top-level JSON object")
            return None
        return payload

    cache_doc = read_required_text(Path("docs") / "GATEWAY_CACHE_POLICY.md")
    for snippet in (
        "request deduplication",
        "inflight replay",
        "completed TTL",
        "cache key normalization",
        "no-cache bypass",
        "eviction",
        "hit rate",
        "It does not own truth.",
        "It does not grant routing authority.",
        "It does not lock the stack to one vendor.",
        "This wave documents the contract only. It does not activate live cache behavior.",
        "`runtime_gateway_cache_status_v1`",
    ):
        if snippet not in cache_doc:
            errors.append(f"docs/GATEWAY_CACHE_POLICY.md must mention `{snippet}`")

    usage_doc = read_required_text(Path("docs") / "USAGE_BUDGET_POLICY.md")
    for snippet in (
        "per-request",
        "session",
        "hourly",
        "daily",
        "graceful degrade",
        "strict stop",
        "reset window",
        "baseline cost",
        "savings",
        "It must not turn runtime budget posture into proof semantics.",
        "It does not create wallet, payment, or vendor-analysis obligations.",
        "This wave documents status surfaces only.",
        "`runtime_usage_snapshot_v1`",
    ):
        if snippet not in usage_doc:
            errors.append(f"docs/USAGE_BUDGET_POLICY.md must mention `{snippet}`")

    doctor_split_doc = read_required_text(Path("docs") / "LOCAL_OPS_DOCTOR_SPLIT.md")
    for snippet in (
        "`aoa-doctor` remains readiness-only.",
        "gateway reachability",
        "log presence",
        "basic config health",
        "local floor availability",
        "It does not become a usage monitor.",
        "bounded local ops status surface",
        "This wave does not add new `aoa-doctor` exit semantics.",
    ):
        if snippet not in doctor_split_doc:
            errors.append(f"docs/LOCAL_OPS_DOCTOR_SPLIT.md must mention `{snippet}`")

    service_catalog_doc = read_required_text(Path("docs") / "SERVICE_CATALOG.md")
    for snippet in (
        "docs/GATEWAY_CACHE_POLICY.md",
        "docs/USAGE_BUDGET_POLICY.md",
        "docs/LOCAL_OPS_DOCTOR_SPLIT.md",
        "does not add new HTTP endpoints in this wave",
        "bounded runtime artifact",
    ):
        if snippet not in service_catalog_doc:
            errors.append(f"docs/SERVICE_CATALOG.md must mention `{snippet}`")

    runbook_doc = read_required_text(Path("docs") / "RUNBOOK.md")
    for snippet in (
        "runtime_gateway_cache_status",
        "runtime_usage_snapshot",
        "Logs/runtime-gateway/cache-status/latest/",
        "Logs/runtime-usage/latest/",
        "absence is not a failure in this wave",
    ):
        if snippet not in runbook_doc:
            errors.append(f"docs/RUNBOOK.md must mention `{snippet}`")

    doctor_doc = read_required_text(Path("docs") / "DOCTOR.md")
    for snippet in (
        "docs/LOCAL_OPS_DOCTOR_SPLIT.md",
        "readiness-only",
        "usage monitor",
    ):
        if snippet not in doctor_doc:
            errors.append(f"docs/DOCTOR.md must mention `{snippet}`")

    cache_schema = read_required_json(Path("schemas") / "runtime-gateway-cache-status.schema.json")
    if cache_schema and cache_schema.get("title") != "abyss-stack runtime gateway cache status":
        errors.append(
            "runtime-gateway-cache-status.schema.json must describe abyss-stack runtime gateway cache status"
        )
    if cache_schema:
        cache_required = cache_schema.get("required")
        if not isinstance(cache_required, list):
            errors.append("runtime-gateway-cache-status.schema.json must declare a required field list")
        else:
            for field in (
                "cache_key_strategy",
                "normalization_rules",
                "inflight_state",
                "ttl_window",
                "bypass_reason",
                "hit_state",
                "generated_at",
            ):
                if field not in cache_required:
                    errors.append(
                        f"runtime-gateway-cache-status.schema.json must require `{field}`"
                    )
        cache_properties = cache_schema.get("properties")
        cache_surface_type = (
            cache_properties.get("surface_type", {})
            if isinstance(cache_properties, dict)
            else {}
        )
        if not isinstance(cache_surface_type, dict) or cache_surface_type.get("const") != "runtime_gateway_cache_status":
            errors.append(
                "runtime-gateway-cache-status.schema.json must pin surface_type.const to runtime_gateway_cache_status"
            )

    usage_schema = read_required_json(Path("schemas") / "runtime-usage-snapshot.schema.json")
    if usage_schema and usage_schema.get("title") != "abyss-stack runtime usage snapshot":
        errors.append(
            "runtime-usage-snapshot.schema.json must describe abyss-stack runtime usage snapshot"
        )
    if usage_schema:
        usage_required = usage_schema.get("required")
        if not isinstance(usage_required, list):
            errors.append("runtime-usage-snapshot.schema.json must declare a required field list")
        else:
            for field in (
                "request_window",
                "session_window",
                "hourly_window",
                "daily_window",
                "policy_mode",
                "degrade_state",
                "strict_stop",
                "baseline_cost_estimate",
                "savings_estimate",
                "reset_at",
            ):
                if field not in usage_required:
                    errors.append(f"runtime-usage-snapshot.schema.json must require `{field}`")
        usage_properties = usage_schema.get("properties")
        usage_surface_type = (
            usage_properties.get("surface_type", {})
            if isinstance(usage_properties, dict)
            else {}
        )
        if not isinstance(usage_surface_type, dict) or usage_surface_type.get("const") != "runtime_usage_snapshot":
            errors.append(
                "runtime-usage-snapshot.schema.json must pin surface_type.const to runtime_usage_snapshot"
            )

    cache_example = read_required_json(
        Path("examples") / "runtime_gateway_cache_status.gateway-local.example.json"
    )
    if cache_example:
        if cache_example.get("surface_type") != "runtime_gateway_cache_status":
            errors.append(
                "runtime gateway cache status example must use surface_type runtime_gateway_cache_status"
            )
        if cache_example.get("schema_version") != "v1":
            errors.append("runtime gateway cache status example must use schema_version v1")
        boundary = cache_example.get("boundary")
        if not isinstance(boundary, dict) or boundary.get("supports_runtime_claims_only") is not True:
            errors.append("runtime gateway cache status example must stay runtime-claims-only")
        recent_decisions = cache_example.get("recent_decisions")
        if not isinstance(recent_decisions, list):
            errors.append("runtime gateway cache status example must include recent_decisions")
        else:
            decision_kinds = {
                item.get("decision")
                for item in recent_decisions
                if isinstance(item, dict)
            }
            for expected in ("hit", "inflight_replay", "bypass"):
                if expected not in decision_kinds:
                    errors.append(
                        f"runtime gateway cache status example must include a `{expected}` decision"
                    )
            if not any(
                isinstance(item, dict)
                and item.get("decision") == "bypass"
                and item.get("cache_control") == "no-cache"
                and item.get("bypass_reason") == "no_cache_header"
                for item in recent_decisions
            ):
                errors.append(
                    "runtime gateway cache status example must show Cache-Control: no-cache bypass"
                )

    usage_example_path = Path("examples") / "runtime_usage_snapshot.workhorse-local.example.json"
    usage_example_text = read_required_text(usage_example_path)
    usage_example = read_required_json(usage_example_path)
    if usage_example:
        if usage_example.get("surface_type") != "runtime_usage_snapshot":
            errors.append("runtime usage snapshot example must use surface_type runtime_usage_snapshot")
        if usage_example.get("schema_version") != "v1":
            errors.append("runtime usage snapshot example must use schema_version v1")
        if usage_example.get("policy_mode") not in {
            "observe_only",
            "soft_cap",
            "graceful_degrade",
            "strict_stop",
        }:
            errors.append("runtime usage snapshot example must use a supported policy_mode")
        baseline_estimate = usage_example.get("baseline_cost_estimate")
        if not isinstance(baseline_estimate, dict) or baseline_estimate.get("unit") != "normalized_cost_units":
            errors.append(
                "runtime usage snapshot example must express baseline_cost_estimate in normalized_cost_units"
            )
        savings_estimate = usage_example.get("savings_estimate")
        if not isinstance(savings_estimate, dict) or savings_estimate.get("unit") != "normalized_cost_units":
            errors.append(
                "runtime usage snapshot example must express savings_estimate in normalized_cost_units"
            )
        boundary = usage_example.get("boundary")
        if not isinstance(boundary, dict) or boundary.get("supports_runtime_claims_only") is not True:
            errors.append("runtime usage snapshot example must stay runtime-claims-only")
        lowered_usage_example = usage_example_text.lower()
        for forbidden in ("wallet", "payment", "billing", "invoice"):
            if forbidden in lowered_usage_example:
                errors.append(
                    f"runtime usage snapshot example must stay free of {forbidden} semantics"
                )


def validate_diagnostic_spine_contracts(errors: list[str]) -> None:
    def read_required_text(relative_path: Path) -> str:
        try:
            return (ROOT / relative_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            errors.append(f"missing required file: {relative_path.as_posix()}")
            return ""

    def read_required_json(relative_path: Path) -> dict[str, object] | None:
        try:
            payload = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            errors.append(f"missing required file: {relative_path.as_posix()}")
            return None
        except json.JSONDecodeError as exc:
            errors.append(f"{relative_path.as_posix()} must contain valid JSON: {exc}")
            return None
        if not isinstance(payload, dict):
            errors.append(f"{relative_path.as_posix()} must contain a top-level JSON object")
            return None
        return payload

    readme = read_required_text(Path("README.md"))
    for snippet in (
        "docs/DIAGNOSTIC_SPINE.md",
        "generated/diagnostic_surface_catalog.min.json",
        "schemas/diagnostic_target.schema.json",
        "schemas/diagnostic_session.schema.json",
        "schemas/diagnosis_companion.schema.json",
        "schemas/diagnostic_anchor_ref.schema.json",
        "schemas/repair_handoff.schema.json",
        "schemas/reviewed_diagnosis_ref.schema.json",
        "examples/diagnostic_target.min.example.json",
        "examples/diagnostic_session.min.example.json",
        "examples/diagnosis_companion.min.example.json",
        "examples/diagnostic_anchor_ref.min.example.json",
        "examples/repair_handoff.min.example.json",
        "examples/reviewed_diagnosis_ref.min.example.json",
        "quests/ABYSS-STACK-Q-0007.yaml",
        "scripts/aoa-diagnose",
    ):
        if snippet not in readme:
            errors.append(f"README.md must mention `{snippet}`")

    spine_doc = read_required_text(DIAGNOSTIC_SPINE_PATH)
    for snippet in (
        "The goal is not a louder doctor.",
        "The diagnostic spine is a read model with memory.",
        "`generated/diagnostic_surface_catalog.min.json`",
        "what path is being diagnosed",
        "`diagnostic_target_v1`",
        "`diagnostic_session_v1`",
        "`diagnosis_companion_v1`",
        "`diagnostic_anchor_ref_v1`",
        "`repair_handoff_v1`",
        "`reviewed_diagnosis_ref_v1`",
        "Skill canon remains in `aoa-skills`.",
        ".agents/skills/abyss-self-diagnostic-spine",
        "scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest",
        "scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest --write-last-good-ref",
        "scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest --write-reviewed-diagnosis-ref",
        "scripts/aoa-diagnose --preset intel-full --with-reviewed-diagnosis-ref /path/to/reviewed-diagnosis.packet.json --write-latest",
        "A strong diagnostic spine gives the system self-location before self-assertion.",
    ):
        if snippet not in spine_doc:
            errors.append(f"{DIAGNOSTIC_SPINE_PATH.as_posix()} must mention `{snippet}`")

    runbook_doc = read_required_text(Path("docs") / "RUNBOOK.md")
    for snippet in (
        "Logs/diagnostics/latest/",
        "diagnostic_session_v1",
        "aoa-diagnose",
        "diagnostic_target.json",
        "diagnosis_companion.json",
        "last_good.ref.json",
        "repair_handoff.json",
        "reviewed_diagnosis.ref.json",
    ):
        if snippet not in runbook_doc:
            errors.append(f"docs/RUNBOOK.md must mention `{snippet}`")

    target_schema = read_required_json(DIAGNOSTIC_TARGET_SCHEMA_PATH)
    if target_schema and target_schema.get("title") != "abyss-stack diagnostic_target_v1":
        errors.append("diagnostic_target.schema.json must describe abyss-stack diagnostic_target_v1")
    if target_schema:
        target_required = target_schema.get("required")
        if not isinstance(target_required, list):
            errors.append("diagnostic_target.schema.json must declare a required field list")
        else:
            for field in (
                "schema_version",
                "preset",
                "profiles",
                "truth_goal",
                "required_checks",
                "drift_watch",
                "public_safe",
            ):
                if field not in target_required:
                    errors.append(f"diagnostic_target.schema.json must require `{field}`")

    session_schema = read_required_json(DIAGNOSTIC_SESSION_SCHEMA_PATH)
    if session_schema and session_schema.get("title") != "abyss-stack diagnostic_session_v1":
        errors.append("diagnostic_session.schema.json must describe abyss-stack diagnostic_session_v1")
    if session_schema:
        session_required = session_schema.get("required")
        if not isinstance(session_required, list):
            errors.append("diagnostic_session.schema.json must declare a required field list")
        else:
            for field in (
                "schema_version",
                "target",
                "axes",
                "truth_status",
                "drifts",
                "exit_class",
                "public_safe",
            ):
                if field not in session_required:
                    errors.append(f"diagnostic_session.schema.json must require `{field}`")

    diagnosis_companion_schema = read_required_json(DIAGNOSIS_COMPANION_SCHEMA_PATH)
    if diagnosis_companion_schema and diagnosis_companion_schema.get("title") != "abyss-stack diagnosis_companion_v1":
        errors.append("diagnosis_companion.schema.json must describe abyss-stack diagnosis_companion_v1")
    if diagnosis_companion_schema:
        diagnosis_required = diagnosis_companion_schema.get("required")
        if not isinstance(diagnosis_required, list):
            errors.append("diagnosis_companion.schema.json must declare a required field list")
        else:
            for field in (
                "schema_version",
                "artifact_kind",
                "diagnostic_session_ref",
                "diagnostic_session_id",
                "target",
                "review_status",
                "summary",
                "diagnoses",
                "public_safe",
            ):
                if field not in diagnosis_required:
                    errors.append(f"diagnosis_companion.schema.json must require `{field}`")

    anchor_ref_schema = read_required_json(DIAGNOSTIC_ANCHOR_REF_SCHEMA_PATH)
    if anchor_ref_schema and anchor_ref_schema.get("title") != "abyss-stack diagnostic_anchor_ref_v1":
        errors.append("diagnostic_anchor_ref.schema.json must describe abyss-stack diagnostic_anchor_ref_v1")
    if anchor_ref_schema:
        anchor_required = anchor_ref_schema.get("required")
        if not isinstance(anchor_required, list):
            errors.append("diagnostic_anchor_ref.schema.json must declare a required field list")
        else:
            for field in (
                "schema_version",
                "artifact_kind",
                "anchor_class",
                "target",
                "diagnostic_session_id",
                "diagnostic_session_path",
                "diagnostic_target_path",
                "truth_status",
                "public_safe",
            ):
                if field not in anchor_required:
                    errors.append(f"diagnostic_anchor_ref.schema.json must require `{field}`")

    repair_handoff_schema = read_required_json(REPAIR_HANDOFF_SCHEMA_PATH)
    if repair_handoff_schema and repair_handoff_schema.get("title") != "abyss-stack repair_handoff_v1":
        errors.append("repair_handoff.schema.json must describe abyss-stack repair_handoff_v1")
    if repair_handoff_schema:
        handoff_required = repair_handoff_schema.get("required")
        if not isinstance(handoff_required, list):
            errors.append("repair_handoff.schema.json must declare a required field list")
        else:
            for field in (
                "schema_version",
                "artifact_kind",
                "diagnostic_session_ref",
                "diagnostic_session_id",
                "target",
                "target_skill",
                "target_owner_repo",
                "handoff_readiness",
                "checkpoint_posture",
                "validation_refs",
                "stop_conditions",
                "escalation_routes",
                "public_safe",
            ):
                if field not in handoff_required:
                    errors.append(f"repair_handoff.schema.json must require `{field}`")

    reviewed_diagnosis_ref_schema = read_required_json(REVIEWED_DIAGNOSIS_REF_SCHEMA_PATH)
    if (
        reviewed_diagnosis_ref_schema
        and reviewed_diagnosis_ref_schema.get("title") != "abyss-stack reviewed_diagnosis_ref_v1"
    ):
        errors.append("reviewed_diagnosis_ref.schema.json must describe abyss-stack reviewed_diagnosis_ref_v1")
    if reviewed_diagnosis_ref_schema:
        review_required = reviewed_diagnosis_ref_schema.get("required")
        if not isinstance(review_required, list):
            errors.append("reviewed_diagnosis_ref.schema.json must declare a required field list")
        else:
            for field in (
                "schema_version",
                "artifact_kind",
                "reviewed_at",
                "reviewer",
                "source_diagnosis_companion_ref",
                "diagnostic_session_ref",
                "diagnostic_session_id",
                "target",
                "skill_name",
                "result_kind",
                "review_verdict",
                "summary",
                "diagnosis_types",
                "symptom_refs",
                "probable_cause_hypotheses",
                "confidence_band",
                "owner_hints",
                "public_safe",
            ):
                if field not in review_required:
                    errors.append(f"reviewed_diagnosis_ref.schema.json must require `{field}`")

    target_example = read_required_json(DIAGNOSTIC_TARGET_EXAMPLE_PATH)
    if target_example:
        if target_example.get("schema_version") != "diagnostic_target_v1":
            errors.append("diagnostic target example must use schema_version diagnostic_target_v1")
        if target_example.get("truth_goal") not in {"deployed", "trial_proven", "live_available"}:
            errors.append("diagnostic target example must use a supported truth_goal")
        required_checks = target_example.get("required_checks")
        if not isinstance(required_checks, list) or not required_checks:
            errors.append("diagnostic target example must include required_checks")
        drift_watch = target_example.get("drift_watch")
        if not isinstance(drift_watch, list) or not drift_watch:
            errors.append("diagnostic target example must include drift_watch")
        if target_example.get("public_safe") is not True:
            errors.append("diagnostic target example must be public_safe")

    session_example = read_required_json(DIAGNOSTIC_SESSION_EXAMPLE_PATH)
    if session_example:
        if session_example.get("schema_version") != "diagnostic_session_v1":
            errors.append("diagnostic session example must use schema_version diagnostic_session_v1")
        if session_example.get("repo") != "abyss-stack":
            errors.append("diagnostic session example must set repo to abyss-stack")
        truth_status = session_example.get("truth_status")
        if not isinstance(truth_status, dict):
            errors.append("diagnostic session example must include truth_status")
        else:
            for field in ("source_authored", "deployed", "trial_proven", "live_available"):
                if not isinstance(truth_status.get(field), bool):
                    errors.append(f"diagnostic session example truth_status.{field} must be boolean")
        axes = session_example.get("axes")
        if not isinstance(axes, dict):
            errors.append("diagnostic session example must include axes")
        else:
            for field in (
                "readiness",
                "posture",
                "render_truth",
                "runtime_health",
                "closure",
                "evidence",
                "governability",
            ):
                if axes.get(field) not in {"pass", "warn", "fail", "skipped", "unknown"}:
                    errors.append(f"diagnostic session example axes.{field} must use a supported verdict")
        if session_example.get("exit_class") not in {
            "ready_to_start",
            "running_as_intended",
            "running_but_unproven",
            "trial_proven_not_live",
            "live_but_drifted",
            "repairable_under_governance",
            "manual_reground_required",
        }:
            errors.append("diagnostic session example must use a supported exit_class")
        next_moves = session_example.get("next_moves")
        if not isinstance(next_moves, list) or not next_moves:
            errors.append("diagnostic session example must include next_moves")
        if session_example.get("public_safe") is not True:
            errors.append("diagnostic session example must be public_safe")

    diagnosis_companion_example = read_required_json(DIAGNOSIS_COMPANION_EXAMPLE_PATH)
    if diagnosis_companion_example:
        if diagnosis_companion_example.get("schema_version") != "diagnosis_companion_v1":
            errors.append("diagnosis companion example must use schema_version diagnosis_companion_v1")
        if diagnosis_companion_example.get("review_status") not in {
            "not_needed",
            "candidate_review_required",
            "reviewed_ref_supplied",
        }:
            errors.append("diagnosis companion example must use a supported review_status")
        diagnoses = diagnosis_companion_example.get("diagnoses")
        if not isinstance(diagnoses, list):
            errors.append("diagnosis companion example must include diagnoses")
        if diagnosis_companion_example.get("public_safe") is not True:
            errors.append("diagnosis companion example must be public_safe")

    anchor_ref_example = read_required_json(DIAGNOSTIC_ANCHOR_REF_EXAMPLE_PATH)
    if anchor_ref_example:
        if anchor_ref_example.get("schema_version") != "diagnostic_anchor_ref_v1":
            errors.append("diagnostic anchor ref example must use schema_version diagnostic_anchor_ref_v1")
        if anchor_ref_example.get("anchor_class") != "last_good":
            errors.append("diagnostic anchor ref example must use anchor_class last_good")
        if anchor_ref_example.get("repo") != "abyss-stack":
            errors.append("diagnostic anchor ref example must set repo to abyss-stack")
        if anchor_ref_example.get("public_safe") is not True:
            errors.append("diagnostic anchor ref example must be public_safe")

    repair_handoff_example = read_required_json(REPAIR_HANDOFF_EXAMPLE_PATH)
    if repair_handoff_example:
        if repair_handoff_example.get("schema_version") != "repair_handoff_v1":
            errors.append("repair handoff example must use schema_version repair_handoff_v1")
        if repair_handoff_example.get("target_skill") != "aoa-session-self-repair":
            errors.append("repair handoff example must target aoa-session-self-repair")
        if repair_handoff_example.get("target_owner_repo") != "aoa-skills":
            errors.append("repair handoff example must set target_owner_repo to aoa-skills")
        if repair_handoff_example.get("handoff_readiness") not in {
            "not_needed",
            "review_required",
            "ready_for_review",
            "blocked",
        }:
            errors.append("repair handoff example must use a supported handoff_readiness")
        if repair_handoff_example.get("public_safe") is not True:
            errors.append("repair handoff example must be public_safe")

    reviewed_diagnosis_ref_example = read_required_json(REVIEWED_DIAGNOSIS_REF_EXAMPLE_PATH)
    if reviewed_diagnosis_ref_example:
        if reviewed_diagnosis_ref_example.get("schema_version") != "reviewed_diagnosis_ref_v1":
            errors.append("reviewed diagnosis ref example must use schema_version reviewed_diagnosis_ref_v1")
        if reviewed_diagnosis_ref_example.get("review_verdict") not in {
            "ready_for_repair_handoff",
            "retest_before_repair",
            "not_repair_fit",
        }:
            errors.append("reviewed diagnosis ref example must use a supported review_verdict")
        if reviewed_diagnosis_ref_example.get("skill_name") != "aoa-session-self-diagnose":
            errors.append("reviewed diagnosis ref example must set skill_name to aoa-session-self-diagnose")
        if reviewed_diagnosis_ref_example.get("public_safe") is not True:
            errors.append("reviewed diagnosis ref example must be public_safe")

    diagnostic_surface_catalog = read_required_json(DIAGNOSTIC_SURFACE_CATALOG_PATH)
    if diagnostic_surface_catalog:
        if diagnostic_surface_catalog.get("schema_version") != "abyss_stack_diagnostic_surface_catalog_v1":
            errors.append(
                "generated/diagnostic_surface_catalog.min.json must use schema_version abyss_stack_diagnostic_surface_catalog_v1"
            )
        if diagnostic_surface_catalog.get("owner_repo") != "abyss-stack":
            errors.append("generated/diagnostic_surface_catalog.min.json must set owner_repo to abyss-stack")
        if diagnostic_surface_catalog.get("surface_kind") != "runtime_surface":
            errors.append("generated/diagnostic_surface_catalog.min.json must stay runtime_surface")
        if diagnostic_surface_catalog.get("authority_ref") != "docs/DIAGNOSTIC_SPINE.md":
            errors.append("generated/diagnostic_surface_catalog.min.json must point authority_ref to docs/DIAGNOSTIC_SPINE.md")

        surfaces = diagnostic_surface_catalog.get("surfaces")
        if not isinstance(surfaces, list) or len(surfaces) != len(DIAGNOSTIC_SURFACE_CATALOG_EXPECTED_NAMES):
            errors.append("generated/diagnostic_surface_catalog.min.json must publish exactly five diagnostic surfaces")
        else:
            surface_names = []
            for index, entry in enumerate(surfaces):
                if not isinstance(entry, dict):
                    errors.append(f"generated/diagnostic_surface_catalog.min.json surface {index} must be an object")
                    continue
                for field in ("name", "schema_ref", "example_ref", "primary_question"):
                    value = entry.get(field)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(
                            f"generated/diagnostic_surface_catalog.min.json surface {index} must include non-empty {field}"
                        )
                name = entry.get("name")
                schema_ref = entry.get("schema_ref")
                example_ref = entry.get("example_ref")
                if isinstance(name, str):
                    surface_names.append(name)
                if isinstance(schema_ref, str) and not (ROOT / schema_ref).exists():
                    errors.append(f"generated/diagnostic_surface_catalog.min.json schema_ref is missing: {schema_ref}")
                if isinstance(example_ref, str) and not (ROOT / example_ref).exists():
                    errors.append(f"generated/diagnostic_surface_catalog.min.json example_ref is missing: {example_ref}")
            if tuple(surface_names) != DIAGNOSTIC_SURFACE_CATALOG_EXPECTED_NAMES:
                errors.append("generated/diagnostic_surface_catalog.min.json surface order must stay aligned with the diagnostic spine")

        validation_refs = diagnostic_surface_catalog.get("validation_refs")
        expected_validation_refs = [
            "scripts/validate_stack.py",
            "tests/test_validate_stack_diagnostic_spine.py",
            "tests/test_diagnostic_spine_contracts.py",
        ]
        if validation_refs != expected_validation_refs:
            errors.append("generated/diagnostic_surface_catalog.min.json validation_refs must stay aligned with the repo-local diagnostic checks")
        elif isinstance(validation_refs, list):
            for ref in validation_refs:
                if not isinstance(ref, str) or not (ROOT / ref).exists():
                    errors.append(f"generated/diagnostic_surface_catalog.min.json validation_ref is missing: {ref}")

    for skill_path, description in (
        (DIAGNOSTIC_SPINE_SKILL_PATH, "local overlay surface"),
        (ABYSS_SAFE_INFRA_SKILL_PATH, "repo-local abyss overlay skill surface"),
        (ABYSS_SANITIZED_SHARE_SKILL_PATH, "repo-local abyss overlay skill surface"),
    ):
        _validate_overlay_skill_surface(
            errors=errors,
            skill_path=skill_path,
            description=description,
            expected_target=OVERLAY_SKILL_INSTALL_TARGETS.get(skill_path),
        )


def _matches_checkout_safe_overlay_install(path: Path, expected_target: str) -> bool:
    if path.is_symlink():
        try:
            return path.readlink().as_posix() == expected_target
        except OSError:
            return False
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8").strip() == expected_target
        except (OSError, UnicodeDecodeError):
            return False
    return False


def _validate_overlay_skill_surface(
    *,
    errors: list[str],
    skill_path: Path,
    description: str,
    expected_target: str | None = None,
) -> None:
    local_skill_root = ROOT / skill_path
    local_skill_md = local_skill_root / "SKILL.md"
    if local_skill_root.is_dir():
        if not local_skill_md.is_file():
            errors.append(f"{skill_path.as_posix()} must contain SKILL.md")
        return
    if expected_target and _matches_checkout_safe_overlay_install(local_skill_root, expected_target):
        return
    errors.append(f"{skill_path.as_posix()} must be installed as a {description}")


def validate_federation_landing(errors: list[str]) -> None:
    templates_readme = (ROOT / "config-templates" / "README.md").read_text(encoding="utf-8")
    if "Configs/federation/" not in templates_readme:
        errors.append("config-templates/README.md must mention Configs/federation/")
    if "Services/aoa-browser/" not in templates_readme:
        errors.append("config-templates/README.md must mention Services/aoa-browser/")
    if "Services/route-api/" not in templates_readme:
        errors.append("config-templates/README.md must mention Services/route-api/")

    services_readme = (ROOT / "config-templates" / "Services" / "README.md").read_text(encoding="utf-8")
    if "aoa-browser/" not in services_readme:
        errors.append("config-templates/Services/README.md must mention aoa-browser/")
    if "aoa-browser/ms-playwright/" not in services_readme:
        errors.append("config-templates/Services/README.md must mention aoa-browser/ms-playwright/")
    if "route-api/" not in services_readme:
        errors.append("config-templates/Services/README.md must mention route-api/")

    storage_layout_doc = (ROOT / "docs" / "STORAGE_LAYOUT.md").read_text(encoding="utf-8")
    if "Knowledge/federation" not in storage_layout_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Knowledge/federation")
    if "source-managed build context" not in storage_layout_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention the aoa-browser source-managed build context")
    if "Services/aoa-browser/ms-playwright/" not in storage_layout_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Services/aoa-browser/ms-playwright/")

    deployment_doc = (ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    if "aoa-sync-federation-surfaces --layer aoa-agents" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer aoa-agents")
    if "aoa-sync-federation-surfaces --layer aoa-memo" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer aoa-memo")
    if "aoa-sync-federation-surfaces --layer aoa-evals" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer aoa-evals")
    if "aoa-sync-federation-surfaces --layer aoa-playbooks" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer aoa-playbooks")
    if "aoa-sync-federation-surfaces --layer aoa-kag" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer aoa-kag")
    if "aoa-sync-federation-surfaces --layer tos-source" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer tos-source")

    paths_doc = (ROOT / "docs" / "PATHS.md").read_text(encoding="utf-8")
    if "AOA_AGENTS_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_AGENTS_ROOT")
    if "AOA_MEMO_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_MEMO_ROOT")
    if "AOA_EVALS_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_EVALS_ROOT")
    if "AOA_PLAYBOOKS_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_PLAYBOOKS_ROOT")
    if "AOA_KAG_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_KAG_ROOT")
    if "AOA_TOS_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_TOS_ROOT")

    service_catalog_doc = (ROOT / "docs" / "SERVICE_CATALOG.md").read_text(encoding="utf-8")
    if "43-federation-router.yml" not in service_catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention 43-federation-router.yml")
    if "route-api" not in service_catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention route-api")
    if "POST /run/federated" not in service_catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention POST /run/federated")
    if "`abyss_default`" not in service_catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must explain the sidecar route-api network attachment")

    profiles_doc = (ROOT / "docs" / "PROFILES.md").read_text(encoding="utf-8")
    if "`federation`" not in profiles_doc:
        errors.append("docs/PROFILES.md must mention the federation profile")
    if "AOA_FEDERATED_RUN_ENABLED=true" not in profiles_doc:
        errors.append("docs/PROFILES.md must explain when AOA_FEDERATED_RUN_ENABLED=true is required")

    profile_recipes_doc = (ROOT / "docs" / "PROFILE_RECIPES.md").read_text(encoding="utf-8")
    if "route-api" not in profile_recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must mention route-api")
    if "aoa-federated-check" not in profile_recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must mention aoa-federated-check for the federated advisory seam")
    if "--playbook-id AOA-P-0008" not in profile_recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must show aoa-federated-check --playbook-id AOA-P-0008 for the first playbook advisory consumer path")
    if "--inspect-id AOA-K-0011" not in profile_recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must show aoa-federated-check --inspect-id AOA-K-0011 for the first retrieval-only consumer path")
    if "--memo-id AOA-M-0001" not in profile_recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must show aoa-federated-check --memo-id AOA-M-0001 for the first memo advisory consumer path")

    runbook_doc = (ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-federated-check" not in runbook_doc:
        errors.append("docs/RUNBOOK.md must mention aoa-federated-check for the live federated advisory seam")
    if "--playbook-id AOA-P-0008" not in runbook_doc:
        errors.append("docs/RUNBOOK.md must show aoa-federated-check --playbook-id AOA-P-0008 for the first playbook advisory consumer path")
    if "--inspect-id AOA-K-0011" not in runbook_doc:
        errors.append("docs/RUNBOOK.md must show aoa-federated-check --inspect-id AOA-K-0011 for the first retrieval-only consumer path")
    if "--memo-id AOA-M-0001" not in runbook_doc:
        errors.append("docs/RUNBOOK.md must show aoa-federated-check --memo-id AOA-M-0001 for the first memo advisory consumer path")


def validate_memo_runtime_seam(errors: list[str]) -> None:
    runbook_doc = (ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-export-memo-candidate" not in runbook_doc:
        errors.append("docs/RUNBOOK.md must mention aoa-export-memo-candidate")

    seam_doc = (ROOT / "docs" / "MEMO_RUNTIME_SEAM.md").read_text(encoding="utf-8")
    for snippet in (
        "aoa-memo",
        "/memo/",
        "aoa-export-memo-candidate",
        "Logs/memo-exports/",
    ):
        if snippet not in seam_doc:
            errors.append(f"docs/MEMO_RUNTIME_SEAM.md must mention {snippet}")

    schema = json.loads(
        (ROOT / "schemas" / "runtime-memo-export-candidate.schema.json").read_text(encoding="utf-8")
    )
    if schema.get("title") != "abyss-stack runtime memo export candidate":
        errors.append("runtime-memo-export-candidate.schema.json must describe abyss-stack runtime memo export candidate")

    example = json.loads(
        (ROOT / "examples" / "runtime_memo_export_candidate.checkpoint_export.example.json").read_text(
            encoding="utf-8"
        )
    )
    if example.get("artifact_kind") != "aoa.runtime-memo-export-candidate":
        errors.append("runtime memo export example must use artifact_kind aoa.runtime-memo-export-candidate")
    if example.get("exported_by") != "scripts/aoa-export-memo-candidate":
        errors.append("runtime memo export example must use exported_by scripts/aoa-export-memo-candidate")


def validate_eval_runtime_seam(errors: list[str]) -> None:
    runbook_doc = (ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-export-runtime-evidence-selection" not in runbook_doc:
        errors.append("docs/RUNBOOK.md must mention aoa-export-runtime-evidence-selection")
    if "aoa-export-artifact-hook-candidate" not in runbook_doc:
        errors.append("docs/RUNBOOK.md must mention aoa-export-artifact-hook-candidate")

    seam_doc = (ROOT / "docs" / "EVAL_RUNTIME_SEAM.md").read_text(encoding="utf-8")
    for snippet in (
        "aoa-evals",
        "/evals/",
        "aoa-export-runtime-evidence-selection",
        "aoa-export-artifact-hook-candidate",
        "Logs/eval-exports/",
    ):
        if snippet not in seam_doc:
            errors.append(f"docs/EVAL_RUNTIME_SEAM.md must mention {snippet}")

    evidence_schema = json.loads(
        (ROOT / "schemas" / "runtime-eval-evidence-selection-candidate.schema.json").read_text(encoding="utf-8")
    )
    if evidence_schema.get("title") != "abyss-stack runtime eval evidence selection candidate":
        errors.append(
            "runtime-eval-evidence-selection-candidate.schema.json must describe abyss-stack runtime eval evidence selection candidate"
        )

    evidence_example = json.loads(
        (ROOT / "examples" / "runtime_eval_evidence_selection_candidate.workhorse-local.example.json").read_text(
            encoding="utf-8"
        )
    )
    if evidence_example.get("artifact_kind") != "aoa.runtime-eval-evidence-selection-candidate":
        errors.append(
            "runtime eval evidence selection example must use artifact_kind aoa.runtime-eval-evidence-selection-candidate"
        )
    if evidence_example.get("exported_by") != "scripts/aoa-export-runtime-evidence-selection":
        errors.append(
            "runtime eval evidence selection example must use exported_by scripts/aoa-export-runtime-evidence-selection"
        )

    hook_schema = json.loads(
        (ROOT / "schemas" / "runtime-artifact-hook-candidate.schema.json").read_text(encoding="utf-8")
    )
    if hook_schema.get("title") != "abyss-stack runtime artifact hook candidate":
        errors.append("runtime-artifact-hook-candidate.schema.json must describe abyss-stack runtime artifact hook candidate")

    hook_example = json.loads(
        (ROOT / "examples" / "runtime_artifact_hook_candidate.self-agent-checkpoint-rollout.example.json").read_text(
            encoding="utf-8"
        )
    )
    if hook_example.get("artifact_kind") != "aoa.runtime-artifact-hook-candidate":
        errors.append("runtime artifact hook example must use artifact_kind aoa.runtime-artifact-hook-candidate")
    if hook_example.get("exported_by") != "scripts/aoa-export-artifact-hook-candidate":
        errors.append("runtime artifact hook example must use exported_by scripts/aoa-export-artifact-hook-candidate")


def validate_playbook_runtime_seam(errors: list[str]) -> None:
    runbook_doc = (ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "playbooks/activation" not in runbook_doc and "/playbooks/" not in runbook_doc:
        errors.append("docs/RUNBOOK.md must mention playbook advisory seam inspection")

    seam_doc = (ROOT / "docs" / "PLAYBOOK_RUNTIME_SEAM.md").read_text(encoding="utf-8")
    for snippet in (
        "aoa-playbooks",
        "/playbooks/",
        "PLAYBOOK.md",
        "advisory-only",
        "aoa-sync-federation-surfaces --layer aoa-playbooks",
    ):
        if snippet not in seam_doc:
            errors.append(f"docs/PLAYBOOK_RUNTIME_SEAM.md must mention {snippet}")


def validate_kag_runtime_seam(errors: list[str]) -> None:
    runbook_doc = (ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "/kag/" not in runbook_doc and "kag/registry" not in runbook_doc:
        errors.append("docs/RUNBOOK.md must mention KAG advisory seam inspection")

    seam_doc = (ROOT / "docs" / "KAG_RUNTIME_SEAM.md").read_text(encoding="utf-8")
    for snippet in (
        "aoa-kag",
        "tos-source",
        "/kag/",
        "Tree-of-Sophia",
        "advisory-only",
        "aoa-sync-federation-surfaces --layer aoa-kag",
        "aoa-sync-federation-surfaces --layer tos-source",
    ):
        if snippet not in seam_doc:
            errors.append(f"docs/KAG_RUNTIME_SEAM.md must mention {snippet}")


def validate_runtime_configs_mirror(errors: list[str]) -> None:
    required_runtime_paths = [
        ROOT / "README.md",
        ROOT / "compose" / "modules",
        ROOT / "compose" / "profiles",
        ROOT / "config-templates" / "Services" / "route-api" / "app" / "main.py",
        ROOT / "scripts" / "aoa-check-layout",
        ROOT / "docs" / "DEPLOYMENT.md",
    ]
    for path in required_runtime_paths:
        if not path.exists():
            errors.append(f"runtime Configs mirror is missing required path: {path.relative_to(ROOT)}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "Source checkout shape" not in readme:
        errors.append("runtime Configs mirror README must clarify that the repository tree is the source checkout shape")
    if "/srv/abyss-stack/Configs" not in readme:
        errors.append("runtime Configs mirror README must mention /srv/abyss-stack/Configs")

    agents_doc = (ROOT / "scripts" / "AGENTS.md").read_text(encoding="utf-8")
    if "source checkout only" not in agents_doc:
        errors.append("runtime Configs mirror scripts/AGENTS.md must note that .github workflow refs are source-checkout-only")


def validate_deployed_parity(errors: list[str], deployed_root: Path) -> None:
    if not deployed_root.exists():
        errors.append(f"deployed Configs root does not exist: {deployed_root}")
        return

    for rel_path in iter_sync_managed_files():
        source_path = ROOT / rel_path
        deployed_path = deployed_root / rel_path
        if not deployed_path.exists():
            errors.append(
                f"deployed Configs mirror is missing synced path: {rel_path}"
            )
            continue

        if source_path.read_bytes() != deployed_path.read_bytes():
            errors.append(
                f"source/deployed drift for synced path: {rel_path}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the abyss-stack source repo or runtime Configs mirror."
    )
    parser.add_argument(
        "--parity-check",
        action="store_true",
        help="Compare source-managed repo surfaces against the deployed Configs mirror.",
    )
    parser.add_argument(
        "--deployed-configs-root",
        default="/srv/abyss-stack/Configs",
        help="Path to the deployed Configs mirror used by --parity-check.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors: list[str] = []

    if RUNTIME_CONFIGS_MIRROR_MODE:
        if args.parity_check:
            print("validation failed:")
            print("- --parity-check must be run from the canonical source checkout, not the deployed Configs mirror")
            return 1
        validate_runtime_configs_mirror(errors)
        if errors:
            print("validation failed:")
            for error in errors:
                print(f"- {error}")
            return 1

        print("validation passed (runtime Configs mirror mode)")
        return 0

    validate_profiles(errors)
    validate_presets(errors)
    validate_paths(errors)
    validate_scripts(errors)
    validate_required_files(errors)
    validate_federation_required_files(errors)
    validate_questbook_surface(errors)
    validate_reference_platform(errors)
    validate_platform_adaptations(errors)
    validate_branch_policy(errors)
    validate_memo_runtime_seam(errors)
    validate_eval_runtime_seam(errors)
    validate_playbook_runtime_seam(errors)
    validate_kag_runtime_seam(errors)
    validate_return_runtime_contract(errors)
    validate_runtime_hygiene_contracts(errors)
    validate_diagnostic_spine_contracts(errors)
    validate_federation_landing(errors)
    if args.parity_check:
        validate_deployed_parity(errors, Path(args.deployed_configs_root))

    if errors:
        print("validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    if args.parity_check:
        print("validation passed (source + deployed parity)")
    else:
        print("validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
