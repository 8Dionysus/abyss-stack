from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

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
    "_aoa_status_autonomy.py",
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
    "aoa-qwen-check",
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
    ROOT / "compose" / "presets" / "agent-tools.txt",
    ROOT / "compose" / "presets" / "agent-observability.txt",
    ROOT / "compose" / "presets" / "agent-full.txt",
    ROOT / "compose" / "presets" / "intel-tools.txt",
    ROOT / "compose" / "presets" / "intel-observability.txt",
    ROOT / "compose" / "presets" / "intel-full.txt",
    ROOT / "compose" / "profiles" / "federation.txt",
    ROOT / "compose" / "tuning" / "README.md",
    ROOT / "compose" / "tuning" / "ollama.cpu.yml",
    ROOT / "compose" / "modules" / "32-llamacpp-inference.yml",
    ROOT / "compose" / "modules" / "43-federation-router.yml",
    ROOT / "compose" / "modules" / "44-llamacpp-agent-sidecar.yml",
    ROOT / "config-templates" / "README.md",
    ROOT / "config-templates" / "Configs" / "agent-api" / "return-policy.yaml",
    ROOT / "config-templates" / "Configs" / "agent-api" / "governed-execution-policy.yaml",
    ROOT / "config-templates" / "Configs" / "agent-api" / "governed-canary-catalog.json",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-agents.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-routing.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-memo.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-evals.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-playbooks.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-kag.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "tos-source.yaml",
    ROOT / "config-templates" / "Configs" / "monitoring" / "prometheus.yml",
    ROOT / "config-templates" / "Configs" / "tts" / "voices.yaml",
    ROOT / "config-templates" / "Services" / "litellm" / "config.yaml",
    ROOT / "config-templates" / "Services" / "route-api" / "Dockerfile",
    ROOT / "config-templates" / "Services" / "route-api" / "requirements.txt",
    ROOT / "config-templates" / "Services" / "route-api" / "app" / "main.py",
    ROOT / "schemas" / "runtime-benchmark.schema.json",
    ROOT / "schemas" / "runtime-governed-execution-policy.schema.json",
    ROOT / "schemas" / "runtime-governed-execution-request.schema.json",
    ROOT / "schemas" / "runtime-governed-execution-canary-catalog.schema.json",
    ROOT / "schemas" / "runtime-memo-export-candidate.schema.json",
    ROOT / "schemas" / "runtime-eval-evidence-selection-candidate.schema.json",
    ROOT / "schemas" / "runtime-artifact-hook-candidate.schema.json",
    ROOT / "schemas" / "runtime-return-policy.schema.json",
    ROOT / "schemas" / "runtime-return-event.schema.json",
    ROOT / "examples" / "runtime_benchmark.workhorse-local.example.json",
    ROOT / "examples" / "runtime_memo_export_candidate.checkpoint_export.example.json",
    ROOT / "examples" / "runtime_eval_evidence_selection_candidate.workhorse-local.example.json",
    ROOT / "examples" / "runtime_artifact_hook_candidate.self-agent-checkpoint-rollout.example.json",
    ROOT / "examples" / "runtime_return_policy.agentic-local.example.json",
    ROOT / "examples" / "runtime_return_event.workhorse-local.example.json",
    ROOT / "tests" / "test_governed_execution.py",
}

MODULE_REQUIREMENTS = {
    "20-orchestration.yml": {"10-storage.yml"},
    "40-llm-gateway.yml": {"30-local-inference.yml"},
    "41-agent-api.yml": {"40-llm-gateway.yml", "30-local-inference.yml"},
    "42-agent-api-intel.yml": {"41-agent-api.yml", "31-intel-inference.yml"},
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
        "/home/dionysus/src/abyss-stack",
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
        promotion_criteria = global_rules.get("promotion_criteria")
        if not isinstance(promotion_criteria, dict) or "canary_proven" not in promotion_criteria or "trusted" not in promotion_criteria:
            errors.append("governed execution policy must define promotion_criteria.canary_proven and promotion_criteria.trusted")
        repo_scope_gate = global_rules.get("repo_scope_expansion_gate")
        if not isinstance(repo_scope_gate, dict):
            errors.append("governed execution policy must define repo_scope_expansion_gate")
        playbooks = governed_policy.get("playbooks")
        if not isinstance(playbooks, dict) or "AOA-P-0011" not in playbooks:
            errors.append("governed execution policy must include an AOA-P-0011 playbook entry")
        else:
            playbook = playbooks.get("AOA-P-0011") or {}
            if playbook.get("trust_state") not in {"experimental", "canary_proven", "trusted"}:
                errors.append("AOA-P-0011 governed policy entry must declare a valid trust_state")
            if not isinstance(playbook.get("task_class"), str):
                errors.append("AOA-P-0011 governed policy entry must declare task_class")

    try:
        canary_catalog = load_structured_object(
            ROOT / "config-templates" / "Configs" / "agent-api" / "governed-canary-catalog.json"
        )
    except Exception as exc:
        errors.append(f"governed canary catalog must parse cleanly: {exc}")
    else:
        if canary_catalog.get("surface_type") != "runtime_governed_execution_canary_catalog":
            errors.append("governed canary catalog must declare surface_type=runtime_governed_execution_canary_catalog")
        if canary_catalog.get("repo_scope") != "abyss-stack":
            errors.append("governed canary catalog must keep repo_scope=abyss-stack")
        canaries = canary_catalog.get("canaries")
        if not isinstance(canaries, list) or not canaries:
            errors.append("governed canary catalog must contain at least one canary entry")


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
        "/home/dionysus/src/abyss-stack",
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


def validate_federation_landing(errors: list[str]) -> None:
    templates_readme = (ROOT / "config-templates" / "README.md").read_text(encoding="utf-8")
    if "Configs/federation/" not in templates_readme:
        errors.append("config-templates/README.md must mention Configs/federation/")
    if "Services/route-api/" not in templates_readme:
        errors.append("config-templates/README.md must mention Services/route-api/")

    services_readme = (ROOT / "config-templates" / "Services" / "README.md").read_text(encoding="utf-8")
    if "route-api/" not in services_readme:
        errors.append("config-templates/Services/README.md must mention route-api/")

    storage_layout_doc = (ROOT / "docs" / "STORAGE_LAYOUT.md").read_text(encoding="utf-8")
    if "Knowledge/federation" not in storage_layout_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Knowledge/federation")

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
    validate_reference_platform(errors)
    validate_platform_adaptations(errors)
    validate_branch_policy(errors)
    validate_memo_runtime_seam(errors)
    validate_eval_runtime_seam(errors)
    validate_playbook_runtime_seam(errors)
    validate_kag_runtime_seam(errors)
    validate_return_runtime_contract(errors)
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
