from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "compose" / "profiles"
PRESET_DIR = ROOT / "compose" / "presets"
MODULE_DIR = ROOT / "compose" / "modules"

LEGACY_PATH = "/srv/abyss"
LEGACY_PATTERN = re.compile(r"/srv/abyss(?!-)")
LEGACY_ALLOWED = {
    ROOT / "docs" / "MIGRATION_FROM_OLD.md",
    ROOT / "scripts" / "validate_stack.py",
}

REQUIRED_SCRIPTS = {
    "aoa-doctor",
    "aoa-host-facts",
    "aoa-platform-adaptation",
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
    ROOT / "docs" / "FIRST_RUN.md",
    ROOT / "docs" / "DOCTOR.md",
    ROOT / "docs" / "PRESETS.md",
    ROOT / "docs" / "PROFILE_RECIPES.md",
    ROOT / "docs" / "RENDER_TRUTH.md",
    ROOT / "docs" / "RUNTIME_BENCH_POLICY.md",
    ROOT / "docs" / "PLATFORM_ADAPTATION_POLICY.md",
    ROOT / "docs" / "BRANCH_POLICY.md",
    ROOT / "docs" / "MEMO_RUNTIME_SEAM.md",
    ROOT / "docs" / "EVAL_RUNTIME_SEAM.md",
    ROOT / "docs" / "INTERNAL_PROBES.md",
    ROOT / "docs" / "REFERENCE_PLATFORM.md",
    ROOT / "docs" / "REFERENCE_PLATFORM_SPEC.md",
    ROOT / "docs" / "SECRETS_BOOTSTRAP.md",
    ROOT / "docs" / "WINDOWS_BRIDGE.md",
    ROOT / "docs" / "WINDOWS_SETUP.md",
    ROOT / "docs" / "WINDOWS_PERFORMANCE.md",
    ROOT / "docs" / "reference-platform" / "README.md",
    ROOT / "docs" / "reference-platform" / "schema.v1.json",
    ROOT / "docs" / "reference-platform" / "reference-host.public.json.example",
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
    ROOT / "compose" / "modules" / "43-federation-router.yml",
    ROOT / "config-templates" / "README.md",
    ROOT / "config-templates" / "Configs" / "agent-api" / "return-policy.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-agents.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-routing.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-memo.yaml",
    ROOT / "config-templates" / "Configs" / "federation" / "aoa-evals.yaml",
    ROOT / "config-templates" / "Configs" / "monitoring" / "prometheus.yml",
    ROOT / "config-templates" / "Configs" / "tts" / "voices.yaml",
    ROOT / "config-templates" / "Services" / "litellm" / "config.yaml",
    ROOT / "config-templates" / "Services" / "route-api" / "Dockerfile",
    ROOT / "config-templates" / "Services" / "route-api" / "requirements.txt",
    ROOT / "config-templates" / "Services" / "route-api" / "app" / "main.py",
    ROOT / "schemas" / "runtime-benchmark.schema.json",
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
    if "docs/PLATFORM_ADAPTATION_POLICY.md" not in readme:
        errors.append("README.md must route readers to docs/PLATFORM_ADAPTATION_POLICY.md")
    if "docs/BRANCH_POLICY.md" not in readme:
        errors.append("README.md must route readers to docs/BRANCH_POLICY.md")
    if "docs/MEMO_RUNTIME_SEAM.md" not in readme:
        errors.append("README.md must route readers to docs/MEMO_RUNTIME_SEAM.md")
    if "docs/EVAL_RUNTIME_SEAM.md" not in readme:
        errors.append("README.md must route readers to docs/EVAL_RUNTIME_SEAM.md")

    paths_doc = (ROOT / "docs" / "PATHS.md").read_text(encoding="utf-8")
    if "/srv/abyss-stack" not in paths_doc:
        errors.append("docs/PATHS.md must mention /srv/abyss-stack")
    if "WSL2" not in paths_doc:
        errors.append(
            "docs/PATHS.md should mention WSL2 in the Windows-usable model"
        )
    if "AOA_ROUTING_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_ROUTING_ROOT")
    if "AOA_MEMO_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_MEMO_ROOT")
    if "AOA_EVALS_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_EVALS_ROOT")

    deployment_doc = (ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    if "scripts/aoa-sync-federation-surfaces --layer aoa-routing" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-routing federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer aoa-memo" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-memo federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer aoa-evals" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention aoa-evals federation sync")

    profiles_doc = (ROOT / "docs" / "PROFILES.md").read_text(encoding="utf-8")
    if "aoa-routing advisory seam" not in profiles_doc:
        errors.append("docs/PROFILES.md must describe the aoa-routing advisory seam")
    if "aoa-memo" not in profiles_doc:
        errors.append("docs/PROFILES.md must describe the aoa-memo recall seam")
    if "aoa-evals" not in profiles_doc:
        errors.append("docs/PROFILES.md must describe the aoa-evals eval selection seam")

    recipes_doc = (ROOT / "docs" / "PROFILE_RECIPES.md").read_text(encoding="utf-8")
    if "aoa-routing" not in recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must mention aoa-routing")
    if "aoa-memo" not in recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must mention aoa-memo")
    if "aoa-evals" not in recipes_doc:
        errors.append("docs/PROFILE_RECIPES.md must mention aoa-evals")

    catalog_doc = (ROOT / "docs" / "SERVICE_CATALOG.md").read_text(encoding="utf-8")
    if "aoa-routing advisory routing surfaces" not in catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention aoa-routing advisory routing surfaces")
    if "aoa-memo" not in catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention aoa-memo")
    if "aoa-evals" not in catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention aoa-evals")

    storage_doc = (ROOT / "docs" / "STORAGE_LAYOUT.md").read_text(encoding="utf-8")
    if "Knowledge/federation/aoa-routing/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-routing/")
    if "Knowledge/federation/aoa-memo/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-memo/")
    if "Knowledge/federation/aoa-evals/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-evals/")
    if "Logs/memo-exports/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Logs/memo-exports/")
    if "Logs/eval-exports/" not in storage_doc:
        errors.append("docs/STORAGE_LAYOUT.md must mention Logs/eval-exports/")


def validate_scripts(errors: list[str]) -> None:
    script_names = {path.name for path in (ROOT / "scripts").iterdir() if path.is_file()}
    missing = sorted(REQUIRED_SCRIPTS - script_names)

    for name in missing:
        errors.append(f"missing required script: scripts/{name}")


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

    deployment_doc = (ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    if "Configs/agent-api/return-policy.yaml" not in deployment_doc:
        errors.append("docs/DEPLOYMENT.md must mention Configs/agent-api/return-policy.yaml")

    first_run_doc = (ROOT / "docs" / "FIRST_RUN.md").read_text(encoding="utf-8")
    if "Configs/agent-api/return-policy.yaml" not in first_run_doc:
        errors.append("docs/FIRST_RUN.md must mention Configs/agent-api/return-policy.yaml")

    render_truth_doc = (ROOT / "docs" / "RENDER_TRUTH.md").read_text(encoding="utf-8")
    if "return-policy" not in render_truth_doc:
        errors.append("docs/RENDER_TRUTH.md should mention return-policy mounts when the wrapper is enabled")

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

    paths_doc = (ROOT / "docs" / "PATHS.md").read_text(encoding="utf-8")
    if "AOA_AGENTS_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_AGENTS_ROOT")
    if "AOA_MEMO_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_MEMO_ROOT")
    if "AOA_EVALS_ROOT" not in paths_doc:
        errors.append("docs/PATHS.md must mention AOA_EVALS_ROOT")

    service_catalog_doc = (ROOT / "docs" / "SERVICE_CATALOG.md").read_text(encoding="utf-8")
    if "43-federation-router.yml" not in service_catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention 43-federation-router.yml")
    if "route-api" not in service_catalog_doc:
        errors.append("docs/SERVICE_CATALOG.md must mention route-api")

    profiles_doc = (ROOT / "docs" / "PROFILES.md").read_text(encoding="utf-8")
    if "`federation`" not in profiles_doc:
        errors.append("docs/PROFILES.md must mention the federation profile")

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


def main() -> int:
    errors: list[str] = []

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
    validate_return_runtime_contract(errors)
    validate_federation_landing(errors)

    if errors:
        print("validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
