from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
QUEST_SCRIPT_DIR = ROOT / "quests" / "scripts"
if str(QUEST_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(QUEST_SCRIPT_DIR))

import quest_surface  # noqa: E402

PROFILE_DIR = ROOT / "compose" / "profiles"
PRESET_DIR = ROOT / "compose" / "presets"
MODULE_DIR = ROOT / "compose" / "modules"
RUNTIME_CONFIGS_MIRROR_MODE = (
    ROOT.name == "Configs"
    and (ROOT / "compose").exists()
    and (ROOT / "config-templates").exists()
    and not (ROOT / "CONTRIBUTING.md").exists()
)

STALE_ABYSS_PATH = "/srv/abyss"
STALE_ABYSS_PATTERN = re.compile(r"/srv/abyss(?!-)")
STALE_STACK_ROOT = "/srv/" + "abyss-stack"
WORKSPACE_ROOT_DEFAULT = "/srv/AbyssOS"
WORKSPACE_SIBLING_ROOTS = {
    "aoa-techniques": f"{WORKSPACE_ROOT_DEFAULT}/aoa-techniques",
    "aoa-skills": f"{WORKSPACE_ROOT_DEFAULT}/aoa-skills",
    "aoa-evals": f"{WORKSPACE_ROOT_DEFAULT}/aoa-evals",
    "aoa-memo": f"{WORKSPACE_ROOT_DEFAULT}/aoa-memo",
    "aoa-agents": f"{WORKSPACE_ROOT_DEFAULT}/aoa-agents",
    "Agents-of-Abyss": f"{WORKSPACE_ROOT_DEFAULT}/Agents-of-Abyss",
    "aoa-playbooks": f"{WORKSPACE_ROOT_DEFAULT}/aoa-playbooks",
    "aoa-kag": f"{WORKSPACE_ROOT_DEFAULT}/aoa-kag",
    "Tree-of-Sophia": f"{WORKSPACE_ROOT_DEFAULT}/Tree-of-Sophia",
    "aoa-routing": f"{WORKSPACE_ROOT_DEFAULT}/aoa-routing",
    "aoa-sdk": f"{WORKSPACE_ROOT_DEFAULT}/aoa-sdk",
}
STALE_ACTIVE_SIBLING_ROOT_PATTERN = re.compile(
    r"/srv/(?:aoa-[A-Za-z0-9_-]+|Agents-of-Abyss|Tree-of-Sophia)"
)
HOST_LOCAL_SOURCE_CHECKOUT_PATTERNS = (
    re.compile(r"/home/[^/\s]+/src/abyss-stack(?=/|\s|$|[.,;:!?)\]}])"),
)
MOVED_MECHANIC_DOC_REFS = (
    "mechanics/config-projection/docs/RENDER_TRUTH.md",
    "mechanics/config-projection/docs/SECRETS_BOOTSTRAP.md",
    "mechanics/diagnostic-spine/docs/DIAGNOSTIC_SPINE.md",
    "mechanics/diagnostic-spine/docs/DOCTOR.md",
    "mechanics/diagnostic-spine/docs/LOCAL_OPS_DOCTOR_SPLIT.md",
    "mechanics/diagnostic-spine/docs/TRUTH_SURFACES.md",
    "mechanics/governed-execution/docs/CONTEXT_BUDGET_POLICY.md",
    "mechanics/governed-execution/docs/GOVERNED_EXECUTION.md",
    "mechanics/governed-execution/docs/RECURRENCE_RUNTIME_POLICY.md",
    "mechanics/inference-pilots/docs/LANGGRAPH_PILOT.md",
    "mechanics/inference-pilots/docs/LLAMACPP_PILOT.md",
    "mechanics/inference-pilots/docs/LOCAL_AI_TRIALS.md",
    "mechanics/inference-pilots/docs/RUNTIME_BENCH_POLICY.md",
    "mechanics/inference-pilots/docs/RUNTIME_WINNER_PROMOTION_LOOP.md",
    "mechanics/runtime-lifecycle/docs/GATEWAY_CACHE_POLICY.md",
    "mechanics/runtime-lifecycle/docs/INTERNAL_PROBES.md",
    "mechanics/runtime-lifecycle/docs/USAGE_BUDGET_POLICY.md",
)
STALE_ABYSS_PATH_ALLOWED = {
    ROOT / "docs" / "legacy" / "MIGRATION_FROM_OLD.md",
    ROOT / "scripts" / "validate_stack.py",
}

SYNC_MANAGED_ITEMS = (
    "compose",
    "config-templates",
    "docs",
    "mechanics",
    "quests",
    "scripts",
    "systemd",
    "env",
    "README.md",
    "QUESTBOOK.md",
    "CHARTER.md",
    "BOUNDARIES.md",
    "DESIGN.md",
    "DESIGN.AGENTS.md",
    "ROADMAP.md",
    "AGENTS.md",
)

MECHANIC_PACKAGES = (
    "runtime-lifecycle",
    "config-projection",
    "machine-fit",
    "inference-pilots",
    "agon-runtime",
    "experience-runtime",
    "federation-seams",
    "governed-execution",
    "diagnostic-spine",
    "runtime-repair",
)
MECHANIC_PACKAGE_REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "DIRECTION.md",
    "PROVENANCE.md",
    "PARTS.md",
    "ROADMAP.md",
    "LANDING_LOG.md",
    "parts/README.md",
    "docs/README.md",
)
MECHANIC_PACKAGE_PARTS = {
    "agon-runtime": ("runtime-kernels",),
    "config-projection": (
        "public-templates",
        "env-examples",
        "bootstrap",
        "sync",
        "rendering",
        "deployment-paths",
    ),
    "diagnostic-spine": (
        "doctor-readiness",
        "diagnose-wrapper",
        "truth-surfaces",
        "diagnostic-surfaces",
    ),
    "experience-runtime": ("experience-records",),
    "federation-seams": (
        "sync-wrapper",
        "federation-checks",
        "memo-seam",
        "eval-seam",
        "playbook-seam",
        "kag-seam",
        "tos-graph",
        "rpg-runtime",
    ),
    "governed-execution": (
        "governed-runner",
        "autonomy-status",
        "return-policy",
        "runtime-contracts",
        "candidate-exports",
        "local-worker-path",
    ),
    "inference-pilots": (
        "llamacpp-pilot",
        "qwen-routes",
        "langgraph-pilot",
        "local-trials",
        "promotion-loop",
        "pilot-archive-bridge",
        "quiet-bridge-commands",
        "agon-dry-run-handoff",
    ),
    "machine-fit": (
        "reference-platform",
        "host-facts",
        "machine-bridge",
        "fit-record",
        "platform-adaptations",
        "inference-tuning",
        "windows-bridge",
    ),
    "runtime-lifecycle": (
        "layout-install",
        "config-sync-boundary",
        "start-stop",
        "wait-smoke",
        "logs-status",
        "status-readouts",
        "user-unit",
    ),
    "runtime-repair": (
        "degradation-receipts",
        "repair-safe-closeout",
        "runtime-chaos",
        "antifragility-posture",
        "a2a-return-dry-run",
        "memo-contradiction-sidecar",
    ),
}
MECHANIC_PART_REQUIRED_FILES = {
    ("agon-runtime", "runtime-kernels"): (
        "docs/RUNTIME_KERNELS.md",
        "definitions/duel-runtime-kernels.json",
        "definitions/mechanical-trial-runs.json",
        "generated/duel-runtime-kernel-registry.min.json",
        "generated/mechanical-trial-run-registry.min.json",
        "examples/duel-runtime-kernel.example.json",
        "examples/mechanical-duel-event-log.example.json",
        "examples/mechanical-trial-event-log.assistant-escalation.example.json",
        "examples/mechanical-trial-event-log.broken-trace.example.json",
        "examples/mechanical-trial-event-log.contradiction-endurance.example.json",
        "examples/mechanical-trial-event-log.costly-closure.example.json",
        "examples/mechanical-trial-event-log.expensive-summon-intent.example.json",
        "examples/mechanical-trial-event-log.fallback-honor.example.json",
        "examples/mechanical-trial-event-log.prediction.example.json",
        "recurrence/component.duel-runtime-kernel-surfaces.json",
        "recurrence/component.mechanical-trial-runs.json",
        "recurrence/hooks/component.duel-runtime-kernel-surfaces.hooks.json",
        "recurrence/hooks/component.mechanical-trial-runs.hooks.json",
        "schemas/duel-runtime-kernel-registry.schema.json",
        "schemas/duel-runtime-kernel.schema.json",
        "schemas/duel-event.schema.json",
        "schemas/mechanical-trial-run-registry.schema.json",
        "schemas/mechanical-trial-run.schema.json",
        "schemas/mechanical-trial-event-log.schema.json",
        "build_duel_runtime_kernel_registry.py",
        "build_mechanical_trial_run_registry.py",
        "validate_duel_runtime_kernels.py",
        "validate_mechanical_trial_runs.py",
        "simulate_mechanical_duel_kernel.py",
        "simulate_mechanical_trials.py",
        "tests/test_duel_runtime_kernels.py",
        "tests/test_mechanical_trial_runs.py",
    ),
    ("experience-runtime", "experience-records"): (
        "docs/EXPERIENCE_RECORDS_DISTILLATION.md",
    ),
}
ARCHIVE_MECHANIC_PACKAGES = (
    "agon-runtime",
    "experience-runtime",
    "inference-pilots",
    "runtime-repair",
)
ARCHIVE_MECHANIC_REQUIRED_FILES = (
    "PROVENANCE.md",
    "legacy/AGENTS.md",
    "legacy/README.md",
    "legacy/INDEX.md",
    "legacy/DISTILLATION_LOG.md",
)
ARCHIVE_MECHANIC_EXTRA_REQUIRED_FILES = {
    "agon-runtime": (
        "legacy/raw/README.md",
        "legacy/artifacts/README.md",
        "legacy/ARCHIVE_CLASSIFICATION.md",
    ),
    "experience-runtime": (
        "legacy/raw/README.md",
        "legacy/artifacts/README.md",
        "legacy/ARCHIVE_CLASSIFICATION.md",
    ),
    "inference-pilots": (
        "legacy/trials/README.md",
        "legacy/trials/raw/README.md",
        "legacy/trials/artifacts/README.md",
    ),
    "runtime-repair": (
        "legacy/raw/README.md",
        "legacy/artifacts/README.md",
    ),
}
ARCHIVE_MECHANIC_ARTIFACT_DIRS = {
    "agon-runtime": (),
    "experience-runtime": (
        "legacy/artifacts/examples",
        "legacy/artifacts/schemas",
        "legacy/artifacts/tests",
    ),
    "inference-pilots": (
        "legacy/trials/artifacts/scripts",
    ),
    "runtime-repair": (),
}
MARKER_ONLY_ARCHIVE_ARTIFACT_PACKAGES = {
    "agon-runtime",
}
MECHANIC_CARD_HEADINGS = (
    "## Mechanic card",
    "### Trigger",
    "### abyss-stack owns",
    "### Stronger owner split",
    "### Inputs",
    "### Outputs",
    "### Must not claim",
    "### Validation",
    "### Next route",
)
FORBIDDEN_ACTIVE_PART_NAMES = ("active-route",)
FORBIDDEN_ACTIVE_PART_NAME_FRAGMENT = "legacy"

PARITY_IGNORED_PARTS = {".git", "__pycache__"}
PARITY_IGNORED_SUFFIXES = {".pyc"}

REQUIRED_SCRIPTS = {
    "aoa-diagnose",
    "aoa-governed-run",
    "aoa-doctor",
    "aoa-host-facts",
    "aoa-machine-bridge",
    "aoa-machine-fit",
    "aoa-platform-adaptation",
    "aoa-local-ai-trials",
    "aoa-langgraph-pilot",
    "aoa-long-horizon-pilot",
    "aoa-bounded-autonomy-pilot",
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
    "aoa-a2a-return-closeout-dry-run",
    "aoa-run-memo-contradiction-integrity",
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
    "aoa-apply-resource-guards",
    "aoa-status",
    "aoa-logs",
    "aoa-smoke",
    "aoa-wait",
    "aoa.ps1",
    "aoa-doctor-win.ps1",
    "aoa-bootstrap-wsl.ps1",
}

OPERATOR_BACKEND_SCRIPTS = {
    "aoa-a2a-return-closeout-dry-run": "mechanics/runtime-repair/parts/a2a-return-dry-run/aoa_a2a_return_closeout_dry_run.py",
    "aoa-bootstrap-configs": "mechanics/config-projection/parts/bootstrap/aoa_bootstrap_configs.sh",
    "aoa-bootstrap-wsl.ps1": "mechanics/machine-fit/parts/windows-bridge/aoa_bootstrap_wsl.ps1",
    "aoa-bounded-autonomy-pilot": "mechanics/inference-pilots/parts/quiet-bridge-commands/aoa_bounded_autonomy_pilot.sh",
    "aoa-sync-configs": "mechanics/config-projection/parts/sync/aoa_sync_configs.sh",
    "aoa-sync-federation-surfaces": "mechanics/federation-seams/parts/sync-wrapper/aoa_sync_federation_surfaces.sh",
    "aoa-preset-profiles": "mechanics/config-projection/parts/rendering/aoa_preset_profiles.sh",
    "aoa-profile-modules": "mechanics/config-projection/parts/rendering/aoa_profile_modules.sh",
    "aoa-profile-endpoints": "mechanics/config-projection/parts/rendering/aoa_profile_endpoints.sh",
    "aoa-render-services": "mechanics/config-projection/parts/rendering/aoa_render_services.sh",
    "aoa-render-config": "mechanics/config-projection/parts/rendering/aoa_render_config.sh",
    "aoa-diagnose": "mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.sh",
    "aoa-doctor": "mechanics/diagnostic-spine/parts/doctor-readiness/aoa_doctor.sh",
    "aoa-doctor-win.ps1": "mechanics/machine-fit/parts/windows-bridge/aoa_doctor_win.ps1",
    "aoa-export-artifact-hook-candidate": "mechanics/governed-execution/parts/candidate-exports/aoa_export_artifact_hook_candidate.py",
    "aoa-export-memo-candidate": "mechanics/governed-execution/parts/candidate-exports/aoa_export_memo_candidate.py",
    "aoa-export-runtime-evidence-selection": "mechanics/governed-execution/parts/candidate-exports/aoa_export_runtime_evidence_selection.py",
    "aoa-federated-check": "mechanics/federation-seams/parts/federation-checks/aoa_federated_check.py",
    "aoa-install-layout": "mechanics/runtime-lifecycle/parts/layout-install/aoa_install_layout.sh",
    "aoa-check-layout": "mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh",
    "aoa-first-run": "mechanics/runtime-lifecycle/parts/first-run-bootstrap/aoa_first_run.sh",
    "aoa-governed-run": "mechanics/governed-execution/parts/governed-runner/aoa_governed_run.py",
    "aoa-host-facts": "mechanics/machine-fit/parts/host-facts/aoa_host_facts.py",
    "aoa-install-systemd": "mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh",
    "aoa-internal-probes": "mechanics/runtime-lifecycle/parts/wait-smoke/aoa_internal_probes.sh",
    "aoa-langgraph-pilot": "mechanics/inference-pilots/parts/langgraph-pilot/aoa_langgraph_pilot.py",
    "aoa-llamacpp-pilot": "mechanics/inference-pilots/parts/llamacpp-pilot/aoa_llamacpp_pilot.py",
    "aoa-local-ai-trials": "mechanics/inference-pilots/parts/local-trials/aoa_local_ai_trials.py",
    "aoa-long-horizon-pilot": "mechanics/inference-pilots/parts/quiet-bridge-commands/aoa_long_horizon_pilot.sh",
    "aoa-machine-bridge": "mechanics/machine-fit/parts/machine-bridge/aoa_machine_bridge.py",
    "aoa-machine-fit": "mechanics/machine-fit/parts/fit-record/aoa_machine_fit.py",
    "aoa-apply-resource-guards": "mechanics/runtime-lifecycle/parts/start-stop/aoa_apply_resource_guards.sh",
    "aoa-up": "mechanics/runtime-lifecycle/parts/start-stop/aoa_up.sh",
    "aoa-down": "mechanics/runtime-lifecycle/parts/start-stop/aoa_down.sh",
    "aoa-platform-adaptation": "mechanics/machine-fit/parts/platform-adaptations/aoa_platform_adaptation.py",
    "aoa-qwen-bench": "mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_bench.sh",
    "aoa-qwen-check": "mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_check.py",
    "aoa-qwen-run": "mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_run.py",
    "aoa-rpg-runtime-projection": "mechanics/federation-seams/parts/rpg-runtime/aoa_rpg_runtime_projection.py",
    "aoa-run-memo-contradiction-integrity": "mechanics/runtime-repair/parts/memo-contradiction-sidecar/aoa_memo_contradiction_integrity.py",
    "aoa-runtime-bench-index": "mechanics/inference-pilots/parts/promotion-loop/aoa_runtime_bench_index.py",
    "aoa-warmup": "mechanics/runtime-lifecycle/parts/start-stop/aoa_warmup.sh",
    "aoa-wait": "mechanics/runtime-lifecycle/parts/wait-smoke/aoa_wait.sh",
    "aoa-smoke": "mechanics/runtime-lifecycle/parts/wait-smoke/aoa_smoke.sh",
    "aoa-logs": "mechanics/runtime-lifecycle/parts/logs-status/aoa_logs.sh",
    "aoa-status": "mechanics/runtime-lifecycle/parts/logs-status/aoa_status.sh",
    "aoa.ps1": "mechanics/machine-fit/parts/windows-bridge/aoa_windows_bridge.ps1",
}

REQUIRED_FILES = {
    ROOT / "compose" / "AGENTS.md",
    ROOT / "env" / "AGENTS.md",
    ROOT / "config-templates" / "AGENTS.md",
    ROOT / "systemd" / "user" / "AGENTS.md",
    ROOT / "systemd" / "user" / "managed-units.txt",
    ROOT / "systemd" / "system" / "AGENTS.md",
    ROOT / "systemd" / "system" / "README.md",
    ROOT / "systemd" / "system" / "managed-units.txt",
    ROOT / "scripts" / "AGENTS.md",
    ROOT / "scripts" / "README.md",
    ROOT / "DESIGN.md",
    ROOT / "DESIGN.AGENTS.md",
    ROOT / "docs" / "AGENTS.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "routes" / "README.md",
    ROOT / "docs" / "routes" / "START_HERE_ROUTE_CONTRACT.md",
    ROOT / "docs" / "routes" / "AUDIT.md",
    ROOT / "docs" / "runtime" / "README.md",
    ROOT / "docs" / "runtime" / "ARCHITECTURE.md",
    ROOT / "docs" / "runtime" / "MECHANICS.md",
    ROOT / "docs" / "runtime" / "PATHS.md",
    ROOT / "docs" / "runtime" / "SERVICE_CATALOG.md",
    ROOT / "docs" / "runtime" / "SERVICE_SELECTION.md",
    ROOT / "docs" / "runtime" / "service-selection-policy.v1.json",
    ROOT / "docs" / "runtime" / "STORAGE_LAYOUT.md",
    ROOT / "docs" / "install" / "README.md",
    ROOT / "docs" / "install" / "DEPLOYMENT.md",
    ROOT / "docs" / "install" / "FIRST_RUN.md",
    ROOT / "docs" / "operations" / "README.md",
    ROOT / "docs" / "operations" / "BACKUP_RESTORE.md",
    ROOT / "docs" / "operations" / "LIFECYCLE.md",
    ROOT / "docs" / "operations" / "RUNBOOK.md",
    ROOT / "docs" / "operations" / "SECURITY.md",
    ROOT / "docs" / "profiles" / "README.md",
    ROOT / "docs" / "profiles" / "PRESETS.md",
    ROOT / "docs" / "profiles" / "PROFILES.md",
    ROOT / "docs" / "profiles" / "PROFILE_RECIPES.md",
    ROOT / "docs" / "governance" / "README.md",
    ROOT / "docs" / "governance" / "BRANCH_POLICY.md",
    ROOT / "docs" / "governance" / "QUESTBOOK_STACK_INTEGRATION.md",
    ROOT / "docs" / "governance" / "RELEASING.md",
    ROOT / "docs" / "legacy" / "README.md",
    ROOT / "docs" / "legacy" / "AGENTS_ROOT_REFERENCE.md",
    ROOT / "docs" / "legacy" / "MIGRATION_FROM_OLD.md",
    ROOT / "docs" / "decisions" / "AGENTS.md",
    ROOT / "docs" / "decisions" / "TEMPLATE.md",
    ROOT / "tests" / "README.md",
    ROOT / "tests" / "test_decision_records.py",
    ROOT / ".agents" / "AGENTS.md",
    ROOT / ".agents" / "README.md",
    ROOT / ".agents" / "skills" / "AGENTS.md",
    ROOT / ".agents" / "spark" / "AGENTS.md",
    ROOT / ".agents" / "spark" / "README.md",
    ROOT / ".agents" / "spark" / "SWARM.md",
    ROOT / ".github" / "GITHUB_SURFACE.md",
    ROOT / "mcp" / "AGENTS.md",
    ROOT / "mcp" / "README.md",
    ROOT / "mcp" / "services" / "AGENTS.md",
    ROOT / "mcp" / "services" / "README.md",
    ROOT / "mcp" / "services" / "aoa-memo-mcp" / "AGENTS.md",
    ROOT / "mcp" / "services" / "aoa-memo-mcp" / "README.md",
    ROOT / "mcp" / "services" / "aoa-memo-mcp" / "DESIGN.md",
    ROOT / "mcp" / "services" / "aoa-memo-mcp" / "docs" / "BOUNDARIES.md",
    ROOT / "mcp" / "services" / "aoa-memo-mcp" / "docs" / "THREAT_MODEL.md",
    ROOT / "mcp" / "services" / "aoa-memo-mcp" / "src" / "aoa_memo_mcp" / "core.py",
    ROOT / "mcp" / "services" / "aoa-memo-mcp" / "src" / "aoa_memo_mcp" / "server.py",
    ROOT / "mcp" / "services" / "aoa-memo-mcp" / "scripts" / "validate_memo_mcp.py",
    ROOT / "mcp" / "services" / "aoa-evals-mcp" / "AGENTS.md",
    ROOT / "mcp" / "services" / "aoa-evals-mcp" / "README.md",
    ROOT / "mcp" / "services" / "aoa-evals-mcp" / "DESIGN.md",
    ROOT / "mcp" / "services" / "aoa-evals-mcp" / "docs" / "BOUNDARIES.md",
    ROOT / "mcp" / "services" / "aoa-evals-mcp" / "docs" / "THREAT_MODEL.md",
    ROOT / "mcp" / "services" / "aoa-evals-mcp" / "src" / "aoa_evals_mcp" / "core.py",
    ROOT / "mcp" / "services" / "aoa-evals-mcp" / "src" / "aoa_evals_mcp" / "server.py",
    ROOT / "mcp" / "services" / "aoa-evals-mcp" / "scripts" / "validate_evals_mcp.py",
    ROOT / "mcp" / "services" / "abyss-machine-mcp" / "AGENTS.md",
    ROOT / "mcp" / "services" / "abyss-machine-mcp" / "README.md",
    ROOT / "mcp" / "services" / "abyss-machine-mcp" / "DESIGN.md",
    ROOT / "mcp" / "services" / "abyss-machine-mcp" / "docs" / "BOUNDARIES.md",
    ROOT / "mcp" / "services" / "abyss-machine-mcp" / "docs" / "THREAT_MODEL.md",
    ROOT / "mcp" / "services" / "abyss-machine-mcp" / "src" / "abyss_machine_mcp" / "core.py",
    ROOT / "mcp" / "services" / "abyss-machine-mcp" / "src" / "abyss_machine_mcp" / "server.py",
    ROOT / "mcp" / "services" / "abyss-machine-mcp" / "scripts" / "validate_machine_mcp.py",
    ROOT / "mcp" / "services" / "aoa-session-memory-mcp" / "AGENTS.md",
    ROOT / "mcp" / "services" / "aoa-session-memory-mcp" / "README.md",
    ROOT / "mcp" / "services" / "aoa-session-memory-mcp" / "DESIGN.md",
    ROOT / "mcp" / "services" / "aoa-session-memory-mcp" / "docs" / "BOUNDARIES.md",
    ROOT / "mcp" / "services" / "aoa-session-memory-mcp" / "docs" / "THREAT_MODEL.md",
    ROOT / "mcp" / "services" / "aoa-session-memory-mcp" / "src" / "aoa_session_memory_mcp" / "core.py",
    ROOT / "mcp" / "services" / "aoa-session-memory-mcp" / "src" / "aoa_session_memory_mcp" / "server.py",
    ROOT / "mcp" / "services" / "aoa-session-memory-mcp" / "scripts" / "validate_session_memory_mcp.py",
    ROOT / "memo" / "AGENTS.md",
    ROOT / "memo" / "README.md",
    ROOT / "mechanics" / "governed-execution" / "parts" / "return-policy" / "docs" / "RECURRENCE_RUNTIME_POLICY.md",
    ROOT / "mechanics" / "README.md",
    ROOT / "mechanics" / "AGENTS.md",
    ROOT / "mechanics" / "ARTIFACT_TOPOLOGY.md",
    ROOT / "mechanics" / "governed-execution" / "parts" / "governed-runner" / "docs" / "GOVERNED_EXECUTION.md",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "doctor-readiness" / "docs" / "DOCTOR.md",
    ROOT / "mechanics" / "config-projection" / "parts" / "rendering" / "docs" / "RENDER_TRUTH.md",
    ROOT / "mechanics" / "inference-pilots" / "parts" / "local-trials" / "docs" / "RUNTIME_BENCH_POLICY.md",
    ROOT / "mechanics" / "inference-pilots" / "parts" / "local-trials" / "docs" / "LOCAL_AI_TRIALS.md",
    ROOT
    / "mechanics"
    / "inference-pilots"
    / "legacy"
    / "trials"
    / "artifacts"
    / "scripts"
    / "aoa-local-ai-trials",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "truth-surfaces" / "docs" / "TRUTH_SURFACES.md",
    ROOT / "mechanics" / "inference-pilots" / "parts" / "langgraph-pilot" / "docs" / "LANGGRAPH_PILOT.md",
    ROOT / "mechanics" / "inference-pilots" / "parts" / "llamacpp-pilot" / "docs" / "LLAMACPP_PILOT.md",
    ROOT / "scripts" / "validate_decision_records.py",
    ROOT / "mechanics" / "inference-pilots" / "legacy" / "trials" / "raw" / "W5_PILOT.md",
    ROOT / "mechanics" / "inference-pilots" / "legacy" / "trials" / "raw" / "W6_PILOT.md",
    ROOT
    / "mechanics"
    / "machine-fit"
    / "parts"
    / "platform-adaptations"
    / "docs"
    / "PLATFORM_ADAPTATION_POLICY.md",
    ROOT / "docs" / "governance" / "BRANCH_POLICY.md",
    ROOT / "mechanics" / "federation-seams" / "parts" / "memo-seam" / "docs" / "MEMO_RUNTIME_SEAM.md",
    ROOT / "mechanics" / "federation-seams" / "parts" / "eval-seam" / "docs" / "EVAL_RUNTIME_SEAM.md",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "a2a-return-dry-run"
    / "docs"
    / "A2A_RETURN_DRY_RUN.md",
    ROOT
    / "mechanics"
    / "federation-seams"
    / "parts"
    / "playbook-seam"
    / "docs"
    / "PLAYBOOK_RUNTIME_SEAM.md",
    ROOT / "mechanics" / "federation-seams" / "parts" / "kag-seam" / "docs" / "KAG_RUNTIME_SEAM.md",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "docs" / "DIAGNOSTIC_SPINE.md",
    ROOT
    / "mechanics"
    / "runtime-lifecycle"
    / "parts"
    / "config-sync-boundary"
    / "docs"
    / "SOURCE_RUNTIME_PARITY_PACKET.md",
    ROOT
    / "mechanics"
    / "runtime-lifecycle"
    / "parts"
    / "start-stop"
    / "docs"
    / "LIVE_RUNTIME_CUTOVER_PACKET.md",
    ROOT / "mechanics" / "federation-seams" / "parts" / "tos-graph" / "docs" / "TOS_GRAPH_CURATION.md",
    ROOT
    / "mechanics"
    / "federation-seams"
    / "parts"
    / "rpg-runtime"
    / "docs"
    / "RPG_RUNTIME_COLLECTIONS.md",
    ROOT
    / "mechanics"
    / "federation-seams"
    / "parts"
    / "rpg-runtime"
    / "docs"
    / "RPG_RUNTIME_BUILDERS.md",
    ROOT
    / "mechanics"
    / "federation-seams"
    / "parts"
    / "rpg-runtime"
    / "docs"
    / "RPG_ROUTE_API_SEAM.md",
    ROOT
    / "mechanics"
    / "federation-seams"
    / "parts"
    / "rpg-runtime"
    / "docs"
    / "RPG_FRONTEND_PROJECTION_SEAM.md",
    ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "status-readouts" / "docs" / "GATEWAY_CACHE_POLICY.md",
    ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "status-readouts" / "docs" / "USAGE_BUDGET_POLICY.md",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "doctor-readiness" / "docs" / "LOCAL_OPS_DOCTOR_SPLIT.md",
    ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "wait-smoke" / "docs" / "INTERNAL_PROBES.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "reference-platform" / "docs" / "REFERENCE_PLATFORM.md",
    ROOT
    / "mechanics"
    / "machine-fit"
    / "parts"
    / "reference-platform"
    / "docs"
    / "REFERENCE_PLATFORM_SPEC.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "fit-record" / "docs" / "MACHINE_FIT_POLICY.md",
    ROOT / "mechanics" / "config-projection" / "parts" / "bootstrap" / "docs" / "SECRETS_BOOTSTRAP.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "windows-bridge" / "README.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "windows-bridge" / "docs" / "WINDOWS_BRIDGE.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "windows-bridge" / "docs" / "WINDOWS_SETUP.md",
    ROOT
    / "mechanics"
    / "machine-fit"
    / "parts"
    / "windows-bridge"
    / "docs"
    / "WINDOWS_PERFORMANCE.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "inference-tuning" / "docs" / "MODEL_CARDS.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "inference-tuning" / "docs" / "MODEL_PROFILES.md",
    ROOT
    / "mechanics"
    / "machine-fit"
    / "parts"
    / "inference-tuning"
    / "docs"
    / "model-cards"
    / "qwen3-openvino-family.md",
    ROOT
    / "mechanics"
    / "machine-fit"
    / "parts"
    / "inference-tuning"
    / "docs"
    / "model-cards"
    / "qwen3-4b-int4-ov.md",
    ROOT
    / "mechanics"
    / "machine-fit"
    / "parts"
    / "inference-tuning"
    / "docs"
    / "model-cards"
    / "qwen3-8b-int4-ov.md",
    ROOT
    / "mechanics"
    / "machine-fit"
    / "parts"
    / "inference-tuning"
    / "docs"
    / "model-cards"
    / "qwen3.5-9b-gguf-llamacpp.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "host-facts" / "README.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "host-facts" / "schemas" / "schema.v1.json",
    ROOT / "mechanics" / "machine-fit" / "parts" / "host-facts" / "examples" / "reference-host.public.json.example",
    ROOT / "mechanics" / "machine-fit" / "parts" / "host-facts" / "examples" / "reference-host.public.json",
    ROOT / "mechanics" / "machine-fit" / "parts" / "machine-bridge" / "docs" / "MACHINE_BRIDGE.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "machine-bridge" / "README.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "machine-bridge" / "schemas" / "schema.v1.json",
    ROOT / "mechanics" / "machine-fit" / "parts" / "machine-bridge" / "examples" / "machine-bridge.public.json.example",
    ROOT / "mechanics" / "machine-fit" / "parts" / "fit-record" / "README.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "fit-record" / "schemas" / "schema.v1.json",
    ROOT / "mechanics" / "machine-fit" / "parts" / "fit-record" / "examples" / "machine-fit.public.json.example",
    ROOT / "mechanics" / "inference-pilots" / "parts" / "langgraph-pilot" / "requirements.txt",
    ROOT / "mechanics" / "machine-fit" / "parts" / "platform-adaptations" / "README.md",
    ROOT / "mechanics" / "machine-fit" / "parts" / "platform-adaptations" / "schemas" / "schema.v1.json",
    ROOT / "mechanics" / "machine-fit" / "parts" / "platform-adaptations" / "examples" / "platform-adaptation.public.json.example",
    ROOT / "compose" / "presets" / "README.md",
    ROOT / "compose" / "presets" / "agent-federation.txt",
    ROOT / "compose" / "presets" / "agent-tools.txt",
    ROOT / "compose" / "presets" / "agent-observability.txt",
    ROOT / "compose" / "presets" / "agent-full.txt",
    ROOT / "compose" / "presets" / "intel-federation.txt",
    ROOT / "compose" / "presets" / "intel-tools.txt",
    ROOT / "compose" / "presets" / "intel-observability.txt",
    ROOT / "compose" / "presets" / "intel-full.txt",
    ROOT / "compose" / "modules" / "README.md",
    ROOT / "compose" / "profiles" / "README.md",
    ROOT / "compose" / "profiles" / "substrate.txt",
    ROOT / "compose" / "profiles" / "workflows.txt",
    ROOT / "compose" / "profiles" / "local-worker.txt",
    ROOT / "compose" / "profiles" / "intel-worker.txt",
    ROOT / "compose" / "profiles" / "fallback-gateway.txt",
    ROOT / "compose" / "profiles" / "federation.txt",
    ROOT / "compose" / "tuning" / "README.md",
    ROOT / "compose" / "tuning" / "llamacpp.cpu.yml",
    ROOT / "compose" / "tuning" / "llamacpp.runtime-fallback.yml",
    ROOT / "compose" / "modules" / "32-llamacpp-inference.yml",
    ROOT / "compose" / "modules" / "43-federation-router.yml",
    ROOT / "compose" / "modules" / "44-llamacpp-agent-sidecar.yml",
    ROOT / "compose" / "modules" / "45-rerank-api.yml",
    ROOT / "compose" / "modules" / "46-rag-api.yml",
    ROOT / "compose" / "modules" / "53-babelvox-tts.yml",
    ROOT / "compose" / "modules" / "52-tos-graph.yml",
    ROOT / "compose" / "profiles" / "curation.txt",
    ROOT / "compose" / "profiles" / "rag.txt",
    ROOT / "compose" / "profiles" / "reranking.txt",
    ROOT / "compose" / "profiles" / "speech-fast-experimental.txt",
    ROOT / "compose" / "tuning" / "rag.thin-host.yml",
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
    ROOT / "config-templates" / "Configs" / "federation" / "upstream-compatibility-bridge.json",
    ROOT / "config-templates" / "Configs" / "rag" / "sources.json",
    ROOT / "config-templates" / "Configs" / "rag" / "agentic-graph.v1.json",
    ROOT / "config-templates" / "Configs" / "rag" / "dag-jobs.v1.json",
    ROOT / "config-templates" / "Configs" / "monitoring" / "prometheus.yml",
    ROOT / "config-templates" / "Configs" / "tts" / "voices.yaml",
    ROOT / "config-templates" / "Services" / "aoa-browser" / "Dockerfile",
    ROOT / "config-templates" / "Services" / "aoa-browser" / "app.py",
    ROOT / "config-templates" / "Services" / "litellm" / "config.yaml",
    ROOT / "config-templates" / "Services" / "route-api" / "Dockerfile",
    ROOT / "config-templates" / "Services" / "route-api" / "requirements.txt",
    ROOT / "config-templates" / "Services" / "route-api" / "app" / "main.py",
    ROOT / "config-templates" / "Services" / "rerank-api" / "Dockerfile",
    ROOT / "config-templates" / "Services" / "rerank-api" / "requirements.txt",
    ROOT / "config-templates" / "Services" / "rerank-api" / "app" / "main.py",
    ROOT / "config-templates" / "Services" / "rag-api" / "Dockerfile",
    ROOT / "config-templates" / "Services" / "rag-api" / "requirements.txt",
    ROOT / "config-templates" / "Services" / "rag-api" / "app" / "main.py",
    ROOT / "config-templates" / "Services" / "babelvox-tts-api" / "Dockerfile",
    ROOT / "config-templates" / "Services" / "babelvox-tts-api" / "requirements.txt",
    ROOT / "config-templates" / "Services" / "babelvox-tts-api" / "app" / "main.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "Dockerfile",
    ROOT / "config-templates" / "Services" / "tos-graph" / "requirements.txt",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "config.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "main.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "models.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "neo4j_store.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "projector.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "tos_reader.py",
    ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "ui.py",
    ROOT / "mechanics" / "inference-pilots" / "parts" / "local-trials" / "schemas" / "runtime-benchmark.schema.json",
    ROOT / "mechanics" / "governed-execution" / "parts" / "runtime-contracts" / "schemas" / "runtime-governed-execution-policy.schema.json",
    ROOT / "mechanics" / "governed-execution" / "parts" / "runtime-contracts" / "schemas" / "runtime-governed-execution-request.schema.json",
    ROOT / "mechanics" / "governed-execution" / "parts" / "runtime-contracts" / "schemas" / "runtime-governed-execution-canary-catalog.schema.json",
    ROOT / "mechanics" / "governed-execution" / "parts" / "candidate-exports" / "schemas" / "runtime-memo-export-candidate.schema.json",
    ROOT / "mechanics" / "governed-execution" / "parts" / "candidate-exports" / "schemas" / "runtime-eval-evidence-selection-candidate.schema.json",
    ROOT / "mechanics" / "governed-execution" / "parts" / "candidate-exports" / "schemas" / "runtime-artifact-hook-candidate.schema.json",
    ROOT / "mechanics" / "runtime-repair" / "parts" / "a2a-return-dry-run" / "schemas" / "runtime-a2a-return-closeout-dry-run.schema.json",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "degradation-receipts"
    / "schemas"
    / "service-degradation-receipt.schema.json",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "repair-safe-closeout"
    / "schemas"
    / "repair-safe-closeout-receipt.schema.json",
    ROOT
    / "mechanics"
    / "governed-execution"
    / "parts"
    / "return-policy"
    / "schemas"
    / "runtime-return-policy.schema.json",
    ROOT
    / "mechanics"
    / "governed-execution"
    / "parts"
    / "return-policy"
    / "schemas"
    / "runtime-return-event.schema.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "diagnostic_target.schema.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "diagnostic_session.schema.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "diagnosis_companion.schema.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "diagnostic_anchor_ref.schema.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "repair_handoff.schema.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "schemas" / "reviewed_diagnosis_ref.schema.json",
    ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "status-readouts" / "schemas" / "runtime-gateway-cache-status.schema.json",
    ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "status-readouts" / "schemas" / "runtime-usage-snapshot.schema.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "schemas" / "agent_build_snapshot.schema.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "schemas" / "reputation_ledger.schema.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "schemas" / "quest_run_result.schema.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "schemas" / "frontend_projection_bundle.schema.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "schemas" / "agent_build_snapshot_collection.schema.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "schemas" / "reputation_ledger_collection.schema.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "schemas" / "quest_run_result_collection.schema.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "schemas" / "frontend_projection_bundle_collection.schema.json",
    ROOT / "mechanics" / "inference-pilots" / "parts" / "local-trials" / "examples" / "runtime_benchmark.workhorse-local.example.json",
    ROOT / "mechanics" / "governed-execution" / "parts" / "candidate-exports" / "examples" / "runtime_memo_export_candidate.checkpoint_export.example.json",
    ROOT / "mechanics" / "governed-execution" / "parts" / "candidate-exports" / "examples" / "runtime_eval_evidence_selection_candidate.workhorse-local.example.json",
    ROOT / "mechanics" / "governed-execution" / "parts" / "candidate-exports" / "examples" / "runtime_artifact_hook_candidate.self-agent-checkpoint-rollout.example.json",
    ROOT / "mechanics" / "runtime-repair" / "parts" / "a2a-return-dry-run" / "examples" / "runtime_a2a_return_closeout_dry_run.example.json",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "degradation-receipts"
    / "examples"
    / "service-degradation-receipt.example.json",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "degradation-receipts"
    / "examples"
    / "service-degradation-receipt.timeout-chaos.example.json",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "degradation-receipts"
    / "examples"
    / "service-degradation-receipt.honest-degradation.example.json",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "degradation-receipts"
    / "examples"
    / "service-degradation-receipt.retrieval-outage-honesty.example.json",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "repair-safe-closeout"
    / "examples"
    / "repair-safe-closeout-receipt.example.json",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "repair-safe-closeout"
    / "examples"
    / "repair-safe-closeout-receipt.timeout-chaos.example.json",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "repair-safe-closeout"
    / "examples"
    / "repair-safe-closeout-receipt.retrieval-outage-honesty.example.json",
    ROOT
    / "mechanics"
    / "governed-execution"
    / "parts"
    / "return-policy"
    / "examples"
    / "runtime_return_policy.agentic-local.example.json",
    ROOT
    / "mechanics"
    / "governed-execution"
    / "parts"
    / "return-policy"
    / "examples"
    / "runtime_return_event.workhorse-local.example.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "diagnostic_target.min.example.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "diagnostic_session.min.example.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "diagnosis_companion.min.example.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "diagnostic_anchor_ref.min.example.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "repair_handoff.min.example.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "examples" / "reviewed_diagnosis_ref.min.example.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "generated" / "diagnostic_surface_catalog.min.json",
    ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "status-readouts" / "examples" / "runtime_gateway_cache_status.gateway-local.example.json",
    ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "status-readouts" / "examples" / "runtime_usage_snapshot.workhorse-local.example.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "examples" / "agent_build_snapshot.example.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "examples" / "reputation_ledger.example.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "examples" / "quest_run_result.example.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "examples" / "frontend_projection_bundle.example.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "generated" / "agent_build_snapshots.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "generated" / "reputation_ledgers.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "generated" / "quest_run_results.json",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "generated" / "frontend_projection_bundles.json",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnose-wrapper" / "aoa_diagnose.py",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "diagnostic_surface_catalog_common.py",
    ROOT / "mechanics" / "governed-execution" / "parts" / "governed-runner" / "aoa_governed_execution.py",
    ROOT / "mechanics" / "governed-execution" / "parts" / "autonomy-status" / "aoa_status_autonomy.py",
    ROOT / "mechanics" / "governed-execution" / "parts" / "governed-runner" / "tests" / "test_governed_execution.py",
    ROOT / "mechanics" / "governed-execution" / "parts" / "candidate-exports" / "tests" / "test_runtime_eval_evidence_export.py",
    ROOT / "mechanics" / "governed-execution" / "parts" / "autonomy-status" / "tests" / "test_aoa_status_autonomy.py",
    ROOT / "mechanics" / "inference-pilots" / "parts" / "local-trials" / "tests" / "test_aoa_local_ai_trials.py",
    ROOT / "mechanics" / "inference-pilots" / "parts" / "llamacpp-pilot" / "tests" / "test_aoa_llamacpp_pilot.py",
    ROOT / "mechanics" / "inference-pilots" / "parts" / "qwen-routes" / "tests" / "test_aoa_qwen_check.py",
    ROOT / "mechanics" / "machine-fit" / "parts" / "machine-bridge" / "tests" / "test_machine_bridge_contracts.py",
    ROOT / "tests" / "test_validate_stack_required_files.py",
    ROOT / "tests" / "test_validate_stack_questbook.py",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "doctor-readiness" / "tests" / "test_aoa_doctor.py",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "tests" / "test_validate_stack_diagnostic_spine.py",
    ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "start-stop" / "tests" / "test_aoa_warmup.py",
    ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "status-readouts" / "tests" / "test_runtime_hygiene.py",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "tests" / "test_diagnostic_spine_contracts.py",
    ROOT / "mechanics" / "diagnostic-spine" / "parts" / "diagnose-wrapper" / "tests" / "test_aoa_diagnose.py",
    ROOT / "mechanics" / "federation-seams" / "parts" / "federation-checks" / "tests" / "test_aoa_federated_check.py",
    ROOT / "mechanics" / "federation-seams" / "parts" / "federation-checks" / "tests" / "test_langchain_api_federated.py",
    ROOT / "mechanics" / "federation-seams" / "parts" / "federation-checks" / "tests" / "test_route_api_closure_status.py",
    ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "tests" / "test_rpg_runtime_projection.py",
    ROOT / "mechanics" / "runtime-repair" / "parts" / "a2a-return-dry-run" / "tests" / "test_a2a_return_closeout_dry_run.py",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "degradation-receipts"
    / "tests"
    / "test_degradation_receipts.py",
    ROOT
    / "mechanics"
    / "runtime-repair"
    / "parts"
    / "repair-safe-closeout"
    / "tests"
    / "test_repair_safe_closeout_receipts.py",
    ROOT / "mechanics" / "runtime-repair" / "parts" / "memo-contradiction-sidecar" / "tests" / "test_memo_contradiction_integrity_runner.py",
    ROOT / "quests" / "AGENTS.md",
    ROOT / "quests" / "README.md",
    ROOT / "quests" / "schemas" / "quest.schema.json",
    ROOT / "quests" / "schemas" / "quest_dispatch.schema.json",
    ROOT / "quests" / "examples" / "quest_catalog.min.example.json",
    ROOT / "quests" / "examples" / "quest_dispatch.min.example.json",
}

FEDERATION_REQUIRED_RUNTIME_INPUTS = {
    Path("config-templates") / "Configs" / "federation" / "aoa-memo.yaml": {
        "mechanics/writeback/parts/runtime-and-temperature/generated/runtime_writeback_targets.min.json",
        "mechanics/writeback/parts/runtime-and-temperature/generated/runtime_writeback_intake.min.json",
    },
    Path("config-templates") / "Configs" / "federation" / "aoa-evals.yaml": {
        "generated/runtime_candidate_template_index.min.json",
        "generated/runtime_candidate_intake.min.json",
        "examples/runtime_evidence_selection.workhorse-local.example.json",
        "examples/runtime_evidence_selection.return-anchor-integrity.example.json",
    },
    Path("config-templates") / "Configs" / "federation" / "aoa-playbooks.yaml": {
        "generated/playbook_review_packet_contracts.min.json",
        "generated/playbook_review_intake.min.json",
    },
}

UPSTREAM_COMPATIBILITY_BRIDGE_PATH = (
    ROOT / "config-templates" / "Configs" / "federation" / "upstream-compatibility-bridge.json"
)

QUESTBOOK_PATH = Path("QUESTBOOK.md")
QUESTBOOK_INTEGRATION_PATH = Path("docs") / "governance" / "QUESTBOOK_STACK_INTEGRATION.md"
RPG_RUNTIME_DOC_ROOT = Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime" / "docs"
RPG_RUNTIME_FRONTEND_POSTURE_PATH = RPG_RUNTIME_DOC_ROOT / "RPG_RUNTIME_FRONTEND_POSTURE.md"
RPG_RUNTIME_COLLECTIONS_PATH = RPG_RUNTIME_DOC_ROOT / "RPG_RUNTIME_COLLECTIONS.md"
RPG_RUNTIME_BUILDERS_PATH = RPG_RUNTIME_DOC_ROOT / "RPG_RUNTIME_BUILDERS.md"
RPG_ROUTE_API_SEAM_PATH = RPG_RUNTIME_DOC_ROOT / "RPG_ROUTE_API_SEAM.md"
RPG_FRONTEND_PROJECTION_SEAM_PATH = RPG_RUNTIME_DOC_ROOT / "RPG_FRONTEND_PROJECTION_SEAM.md"
DIAGNOSTIC_SPINE_DOC_ROOT = Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "docs"
DIAGNOSTIC_SPINE_PATH = DIAGNOSTIC_SPINE_DOC_ROOT / "DIAGNOSTIC_SPINE.md"
DIAGNOSTIC_SURFACE_ROOT = Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces"
DIAGNOSTIC_SURFACE_SCHEMA_ROOT = DIAGNOSTIC_SURFACE_ROOT / "schemas"
DIAGNOSTIC_SURFACE_EXAMPLE_ROOT = DIAGNOSTIC_SURFACE_ROOT / "examples"
DIAGNOSTIC_SURFACE_CATALOG_PATH = (
    Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "generated" / "diagnostic_surface_catalog.min.json"
)
DIAGNOSTIC_SPINE_SKILL_PATH = Path(".agents") / "skills" / "abyss-self-diagnostic-spine"
ABYSS_SAFE_INFRA_SKILL_PATH = Path(".agents") / "skills" / "abyss-safe-infra-change"
ABYSS_SANITIZED_SHARE_SKILL_PATH = Path(".agents") / "skills" / "abyss-sanitized-share"
AOA_SKILL_INSTALL_ROOT = f"{WORKSPACE_SIBLING_ROOTS['aoa-skills']}/.agents/skills"
LOCAL_SKILL_OVERLAY_NAMES = {"abyss-self-diagnostic-spine"}
OVERLAY_SKILL_INSTALL_TARGETS = {
    ABYSS_SAFE_INFRA_SKILL_PATH: f"{AOA_SKILL_INSTALL_ROOT}/abyss-safe-infra-change",
    ABYSS_SANITIZED_SHARE_SKILL_PATH: f"{AOA_SKILL_INSTALL_ROOT}/abyss-sanitized-share",
}
QUEST_SURFACE_ROOT = quest_surface.QUEST_SURFACE_ROOT
QUEST_SCHEMA_PATH = QUEST_SURFACE_ROOT / "schemas" / "quest.schema.json"
QUEST_DISPATCH_SCHEMA_PATH = QUEST_SURFACE_ROOT / "schemas" / "quest_dispatch.schema.json"
DIAGNOSTIC_TARGET_SCHEMA_PATH = DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "diagnostic_target.schema.json"
DIAGNOSTIC_SESSION_SCHEMA_PATH = DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "diagnostic_session.schema.json"
DIAGNOSIS_COMPANION_SCHEMA_PATH = DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "diagnosis_companion.schema.json"
DIAGNOSTIC_ANCHOR_REF_SCHEMA_PATH = DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "diagnostic_anchor_ref.schema.json"
REPAIR_HANDOFF_SCHEMA_PATH = DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "repair_handoff.schema.json"
REVIEWED_DIAGNOSIS_REF_SCHEMA_PATH = DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "reviewed_diagnosis_ref.schema.json"
RPG_RUNTIME_SURFACE_ROOT = Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime"
RPG_RUNTIME_SCHEMA_ROOT = RPG_RUNTIME_SURFACE_ROOT / "schemas"
RPG_RUNTIME_EXAMPLE_ROOT = RPG_RUNTIME_SURFACE_ROOT / "examples"
RPG_RUNTIME_GENERATED_ROOT = Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime" / "generated"
AGENT_BUILD_SNAPSHOT_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "agent_build_snapshot.schema.json"
REPUTATION_LEDGER_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "reputation_ledger.schema.json"
QUEST_RUN_RESULT_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "quest_run_result.schema.json"
FRONTEND_PROJECTION_BUNDLE_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "frontend_projection_bundle.schema.json"
AGENT_BUILD_SNAPSHOT_COLLECTION_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "agent_build_snapshot_collection.schema.json"
REPUTATION_LEDGER_COLLECTION_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "reputation_ledger_collection.schema.json"
QUEST_RUN_RESULT_COLLECTION_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "quest_run_result_collection.schema.json"
FRONTEND_PROJECTION_BUNDLE_COLLECTION_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "frontend_projection_bundle_collection.schema.json"
QUEST_CATALOG_EXAMPLE_PATH = quest_surface.QUEST_CATALOG_EXAMPLE_PATH
QUEST_DISPATCH_EXAMPLE_PATH = quest_surface.QUEST_DISPATCH_EXAMPLE_PATH
RETURN_POLICY_SURFACE_ROOT = Path("mechanics") / "governed-execution" / "parts" / "return-policy"
RETURN_POLICY_SCHEMA_ROOT = RETURN_POLICY_SURFACE_ROOT / "schemas"
RETURN_POLICY_EXAMPLE_ROOT = RETURN_POLICY_SURFACE_ROOT / "examples"
RUNTIME_RETURN_POLICY_SCHEMA_PATH = RETURN_POLICY_SCHEMA_ROOT / "runtime-return-policy.schema.json"
RUNTIME_RETURN_EVENT_SCHEMA_PATH = RETURN_POLICY_SCHEMA_ROOT / "runtime-return-event.schema.json"
DIAGNOSTIC_TARGET_EXAMPLE_PATH = DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "diagnostic_target.min.example.json"
DIAGNOSTIC_SESSION_EXAMPLE_PATH = DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "diagnostic_session.min.example.json"
DIAGNOSIS_COMPANION_EXAMPLE_PATH = DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "diagnosis_companion.min.example.json"
DIAGNOSTIC_ANCHOR_REF_EXAMPLE_PATH = DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "diagnostic_anchor_ref.min.example.json"
REPAIR_HANDOFF_EXAMPLE_PATH = DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "repair_handoff.min.example.json"
REVIEWED_DIAGNOSIS_REF_EXAMPLE_PATH = DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "reviewed_diagnosis_ref.min.example.json"
RUNTIME_LIFECYCLE_SURFACE_ROOT = Path("mechanics") / "runtime-lifecycle" / "parts" / "status-readouts"
RUNTIME_LIFECYCLE_SCHEMA_ROOT = RUNTIME_LIFECYCLE_SURFACE_ROOT / "schemas"
RUNTIME_LIFECYCLE_EXAMPLE_ROOT = RUNTIME_LIFECYCLE_SURFACE_ROOT / "examples"
RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH = (
    RUNTIME_LIFECYCLE_SCHEMA_ROOT / "runtime-gateway-cache-status.schema.json"
)
RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH = (
    RUNTIME_LIFECYCLE_SCHEMA_ROOT / "runtime-usage-snapshot.schema.json"
)
RUNTIME_GATEWAY_CACHE_STATUS_EXAMPLE_PATH = (
    RUNTIME_LIFECYCLE_EXAMPLE_ROOT / "runtime_gateway_cache_status.gateway-local.example.json"
)
RUNTIME_USAGE_SNAPSHOT_EXAMPLE_PATH = (
    RUNTIME_LIFECYCLE_EXAMPLE_ROOT / "runtime_usage_snapshot.workhorse-local.example.json"
)
SERVICE_SELECTION_POLICY_PATH = Path("docs") / "runtime" / "service-selection-policy.v1.json"
SERVICE_SCREENSHOT_INVENTORY_PATH = Path("docs") / "runtime" / "service-inventory-2026-05-14.v1.json"
SERVICE_SELECTION_POLICY_REQUIRED_SERVICES = {
    "postgres",
    "redis",
    "qdrant",
    "neo4j",
    "llama-cpp",
    "ovms",
    "langchain-api",
    "route-api",
    "rerank-api",
    "rag-api",
    "qwen-tts",
    "tts-router",
    "docs-api",
    "aoa-browser",
    "prometheus",
    "grafana",
    "alertmanager",
    "cadvisor",
    "n8n",
    "n8n-task-runners",
    "ollama",
    "litellm",
    "tos-graph",
    "babelvox-tts",
    "langchain-api-llamacpp",
}
SERVICE_SELECTION_POLICY_ALLOWED_POSTURES = {
    "selected_now",
    "explicit_opt_in",
    "fallback_control",
    "lab_only",
    "not_selected",
}
SERVICE_SCREENSHOT_INVENTORY_REQUIRED_SERVICES = {
    "postgres",
    "redis",
    "qdrant",
    "neo4j",
    "llama-cpp",
    "langchain-api",
    "ovms",
    "route-api",
    "n8n",
    "n8n-task-runners",
    "qwen-tts",
    "tts-router",
    "docs-api",
    "aoa-browser",
    "prometheus",
    "grafana",
    "alertmanager",
    "cadvisor",
}
AGENT_BUILD_SNAPSHOT_EXAMPLE_PATH = RPG_RUNTIME_EXAMPLE_ROOT / "agent_build_snapshot.example.json"
REPUTATION_LEDGER_EXAMPLE_PATH = RPG_RUNTIME_EXAMPLE_ROOT / "reputation_ledger.example.json"
QUEST_RUN_RESULT_EXAMPLE_PATH = RPG_RUNTIME_EXAMPLE_ROOT / "quest_run_result.example.json"
FRONTEND_PROJECTION_BUNDLE_EXAMPLE_PATH = RPG_RUNTIME_EXAMPLE_ROOT / "frontend_projection_bundle.example.json"
GENERATED_AGENT_BUILD_SNAPSHOTS_PATH = RPG_RUNTIME_GENERATED_ROOT / "agent_build_snapshots.json"
GENERATED_REPUTATION_LEDGERS_PATH = RPG_RUNTIME_GENERATED_ROOT / "reputation_ledgers.json"
GENERATED_QUEST_RUN_RESULTS_PATH = RPG_RUNTIME_GENERATED_ROOT / "quest_run_results.json"
GENERATED_FRONTEND_PROJECTION_BUNDLES_PATH = RPG_RUNTIME_GENERATED_ROOT / "frontend_projection_bundles.json"
DIAGNOSTIC_SURFACE_CATALOG_EXPECTED_NAMES = (
    "diagnostic_target",
    "diagnostic_session",
    "diagnosis_companion",
    "reviewed_diagnosis_ref",
    "repair_handoff",
)
QUEST_IDS = quest_surface.QUEST_IDS
QUEST_ROUTES = quest_surface.QUEST_ROUTES
QUESTBOOK_REQUIRED_TOKENS = (
    "deferred infrastructure obligations that belong to `abyss-stack`",
    "render-truth, doctor, first-run, and runtime guardrail follow-through",
    "source-owned meaning from AoA layer repos",
    "quests/<lane>/<state>/ABYSS-STACK-Q-*.yaml",
    "not generated state, deployed runtime state, or runtime authority",
)
QUESTBOOK_FORBIDDEN_TOKENS = ("ATM10-Agent", "aoa-sdk")
CLOSED_QUEST_STATES = {"done", "dropped"}
QUESTBOOK_INTEGRATION_REQUIRED_TOKENS = (
    "runtime, deployment, lifecycle, security, storage, and platform posture",
    "specialized AoA repositories still own their own doctrine and public meaning",
    "high-risk routes should default toward stronger control modes and human gates",
    "reviewable and source-owned",
    "do not replace the deployed mirror under `/srv/AbyssOS/abyss-stack`",
)
QUESTBOOK_INTEGRATION_FORBIDDEN_TOKENS = ("ATM10-Agent", "aoa-sdk")
QUEST_SCHEMA_REQUIRED_FIELDS = (
    "schema_version",
    "id",
    "title",
    "repo",
    "lane",
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
    "lane",
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
    "46-rag-api.yml": {
        "10-storage.yml",
        "31-intel-inference.yml",
        "41-agent-api.yml",
        "43-federation-router.yml",
        "45-rerank-api.yml",
    },
    "52-tos-graph.yml": {"10-storage.yml"},
}

BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".zip", ".pyc"}
GIT_MIRROR_RUNTIME_TOP_LEVEL_DIRS = {"Secrets", "Logs", "Models"}
GIT_MIRROR_CACHE_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "node_modules",
}
GIT_MIRROR_LIVE_ENV_NAMES = {"stack.env", ".env"}
GIT_MIRROR_PRIVATE_SUFFIXES = (".private.json", ".private.yaml", ".private.yml")
GIT_MIRROR_RENDERED_SUFFIXES = (".rendered.yml", ".rendered.yaml")
GIT_MIRROR_DATABASE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
GIT_MIRROR_HEAVY_SUFFIXES = (
    ".gguf",
    ".safetensors",
    ".pt",
    ".pth",
    ".onnx",
    ".ckpt",
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".zst",
)
GIT_MIRROR_FIXTURE_PREFIXES = (
    "docs/",
    "examples/",
    "quests/",
    "schemas/",
    "tests/",
    "mechanics/",
    "config-templates/",
)


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


def is_public_fixture_like_tracked_path(relative_path: str) -> bool:
    name = relative_path.rsplit("/", 1)[-1]
    if not relative_path.startswith(GIT_MIRROR_FIXTURE_PREFIXES):
        return False
    return (
        name.endswith(".example")
        or ".example." in name
        or name.endswith(".example.json")
        or name.endswith(".json.example")
        or name.endswith(".env.example")
        or ".public." in name
        or relative_path.startswith(("docs/", "schemas/", "tests/"))
    )


def tracked_file_git_mirror_hygiene_issue(relative_path: str) -> str | None:
    normalized = relative_path.replace("\\", "/").strip("/")
    if not normalized:
        return None

    parts = normalized.split("/")
    name = parts[-1]
    lower_name = name.lower()
    lower_path = normalized.lower()
    fixture_like = is_public_fixture_like_tracked_path(normalized)

    if parts[0] in GIT_MIRROR_RUNTIME_TOP_LEVEL_DIRS:
        return f"live runtime directory `{parts[0]}/`"
    if any(part in GIT_MIRROR_CACHE_PARTS for part in parts):
        return "local cache or dependency directory"
    if name in GIT_MIRROR_LIVE_ENV_NAMES:
        return "live env file"
    if lower_name.endswith(".env") and not lower_name.endswith(".env.example"):
        return "live env file"
    if lower_path.endswith(GIT_MIRROR_RENDERED_SUFFIXES):
        return "rendered compose/config output"
    if lower_path.endswith(GIT_MIRROR_DATABASE_SUFFIXES):
        return "database artifact"
    if lower_path.endswith(GIT_MIRROR_HEAVY_SUFFIXES):
        return "heavy archive or model artifact"
    if lower_path.endswith(GIT_MIRROR_PRIVATE_SUFFIXES) and not fixture_like:
        return "private capture artifact"
    return None


def iter_tracked_git_files() -> list[str]:
    if not (ROOT / ".git").exists():
        return []
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def validate_git_mirror_hygiene(errors: list[str]) -> None:
    for relative_path in iter_tracked_git_files():
        issue = tracked_file_git_mirror_hygiene_issue(relative_path)
        if issue:
            errors.append(
                "tracked file is not GitHub mirror safe: "
                f"{relative_path} ({issue})"
            )


def validate_no_host_local_source_checkout_paths(errors: list[str]) -> None:
    for path in iter_text_files():
        if path == ROOT / "scripts" / "validate_stack.py":
            continue
        text = read_text_or_none(path)
        if text is None:
            continue
        for pattern in HOST_LOCAL_SOURCE_CHECKOUT_PATTERNS:
            for match in pattern.finditer(text):
                errors.append(
                    "host-local source checkout path found in "
                    f"{path.relative_to(ROOT)}: {match.group(0).rstrip('/')}"
                )


def validate_no_moved_mechanic_doc_refs(errors: list[str]) -> None:
    for path in iter_text_files():
        if path == ROOT / "scripts" / "validate_stack.py":
            continue
        text = read_text_or_none(path)
        if text is None:
            continue
        for moved_ref in MOVED_MECHANIC_DOC_REFS:
            if moved_ref in text:
                errors.append(
                    f"moved mechanic doc ref found in {path.relative_to(ROOT)}: "
                    f"{moved_ref}"
                )


def is_legacy_archive_path(path: Path) -> bool:
    try:
        return "legacy" in path.relative_to(ROOT).parts
    except ValueError:
        return "legacy" in path.parts


def validate_no_stale_active_sibling_roots(errors: list[str]) -> None:
    for path in iter_text_files():
        if is_legacy_archive_path(path):
            continue
        text = read_text_or_none(path)
        if text is None:
            continue
        for match in STALE_ACTIVE_SIBLING_ROOT_PATTERN.finditer(text):
            errors.append(
                "stale active sibling root found in "
                f"{path.relative_to(ROOT)}: {match.group(0)}"
            )


def load_names(file_path: Path) -> list[str]:
    names: list[str] = []

    for raw in file_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.append(line)

    return names


def compose_service_names(file_path: Path) -> set[str]:
    service_names: set[str] = set()
    in_services = False
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        if raw.strip() == "services:":
            in_services = True
            continue
        if not in_services:
            continue
        if raw and not raw.startswith(" "):
            break
        match = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", raw)
        if match:
            service_names.add(match.group(1))
    return service_names


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


def quest_source_path(quest_id: str) -> Path:
    return quest_surface.quest_source_path(quest_id)


def build_expected_quest_catalog_entry(quest_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return quest_surface.build_expected_quest_catalog_entry(quest_id, payload)


def build_expected_quest_dispatch_entry(quest_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return quest_surface.build_expected_quest_dispatch_entry(quest_id, payload)


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
    ) + tuple(quest_source_path(quest_id) for quest_id in QUEST_IDS)

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
                "It is not implemented in this source contract.",
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
                    "mechanics/federation-seams/parts/rpg-runtime/generated/frontend_projection_bundles.json must reference Agents-of-Abyss/generated/dual_vocabulary_overlay.json"
                )

    expected_catalog = []
    expected_dispatch = []
    active_quest_ids: list[str] = []
    closed_quest_ids: list[str] = []
    for quest_id in QUEST_IDS:
        expected_lane, expected_state = QUEST_ROUTES[quest_id]
        quest_path = ROOT / quest_source_path(quest_id)
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
        if quest_payload.get("lane") != expected_lane:
            errors.append(f"{quest_id} lane must equal '{expected_lane}'")
        if quest_payload.get("state") != expected_state:
            errors.append(f"{quest_id} state must match path state '{expected_state}'")
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
            if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md":
                errors.append("ABYSS-STACK-Q-0003 must stay anchored to mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md")
            note = anchor_ref.get("note") if isinstance(anchor_ref, dict) else ""
            if not isinstance(note, str) or "docs/install/FIRST_RUN.md" not in note or "mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md" not in note:
                errors.append("ABYSS-STACK-Q-0003 anchor note must mention docs/install/FIRST_RUN.md and mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md")
        elif quest_id == "ABYSS-STACK-Q-0005":
            if quest_payload.get("kind") != "doctrine":
                errors.append("ABYSS-STACK-Q-0005 kind must stay doctrine")
            anchor_ref = quest_payload.get("anchor_ref")
            if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_FRONTEND_POSTURE.md":
                errors.append(
                    "ABYSS-STACK-Q-0005 must stay anchored to mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_FRONTEND_POSTURE.md"
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
            if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_COLLECTIONS.md":
                errors.append(
                    "ABYSS-STACK-Q-0006 must stay anchored to mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_COLLECTIONS.md"
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
            if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md":
                errors.append(
                    "ABYSS-STACK-Q-0007 must stay anchored to mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md"
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
        errors.append(
            f"{QUEST_CATALOG_EXAMPLE_PATH.as_posix()} must stay aligned with quests/<lane>/<state>/*.yaml"
        )

    try:
        dispatch_payload = json.loads((ROOT / QUEST_DISPATCH_EXAMPLE_PATH).read_text(encoding="utf-8"))
    except FileNotFoundError:
        dispatch_payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"{QUEST_DISPATCH_EXAMPLE_PATH.as_posix()} must contain valid JSON: {exc}")
        dispatch_payload = None
    if dispatch_payload is not None and dispatch_payload != expected_dispatch:
        errors.append(
            f"{QUEST_DISPATCH_EXAMPLE_PATH.as_posix()} must stay aligned with quests/<lane>/<state>/*.yaml"
        )

    flat_aliases = sorted((ROOT / QUEST_SURFACE_ROOT).glob("ABYSS-STACK-Q-*.yaml"))
    for path in flat_aliases:
        errors.append(
            f"{path.relative_to(ROOT).as_posix()} is a root quest alias; use quests/<lane>/<state>/"
        )


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
    expected_profiles = {
        "substrate.txt": ["10-storage.yml"],
        "workflows.txt": ["10-storage.yml", "20-orchestration.yml"],
        "local-worker.txt": ["32-llamacpp-inference.yml", "41-agent-api.yml"],
        "intel-worker.txt": [
            "32-llamacpp-inference.yml",
            "31-intel-inference.yml",
            "41-agent-api.yml",
            "42-agent-api-intel.yml",
        ],
        "fallback-gateway.txt": ["30-local-inference.yml", "40-llm-gateway.yml"],
        "core.txt": ["10-storage.yml", "32-llamacpp-inference.yml"],
        "agentic.txt": [
            "10-storage.yml",
            "32-llamacpp-inference.yml",
            "41-agent-api.yml",
        ],
        "intel.txt": [
            "10-storage.yml",
            "32-llamacpp-inference.yml",
            "31-intel-inference.yml",
            "41-agent-api.yml",
            "42-agent-api-intel.yml",
        ],
    }
    for profile_name, expected_modules in expected_profiles.items():
        profile_path = PROFILE_DIR / profile_name
        if not profile_path.exists():
            errors.append(f"missing required profile: {profile_path.relative_to(ROOT)}")
            continue
        modules = load_names(profile_path)
        if modules != expected_modules:
            errors.append(
                f"profile {profile_name} must be {', '.join(expected_modules)}"
            )

    aoa_lib = (ROOT / "scripts" / "aoa-lib.sh").read_text(encoding="utf-8")
    if 'AOA_STACK_DEFAULT_PROFILE="${AOA_STACK_DEFAULT_PROFILE:-substrate}"' not in aoa_lib:
        errors.append("scripts/aoa-lib.sh default profile must remain substrate")

    unit = (ROOT / "systemd" / "user" / "podman-compose-abyss.service").read_text(encoding="utf-8")
    if "Environment=AOA_STACK_PROFILE=substrate" not in unit:
        errors.append("systemd/user/podman-compose-abyss.service must default to substrate")

    normal_profile_modules: dict[str, set[str]] = {}
    for profile in sorted(PROFILE_DIR.glob("*.txt")):
        modules = load_names(profile)
        if not modules:
            errors.append(f"profile has no modules: {profile.relative_to(ROOT)}")
            continue
        normal_profile_modules[profile.name] = set(modules)

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

    for profile_name, modules in normal_profile_modules.items():
        if "44-llamacpp-agent-sidecar.yml" in modules:
            errors.append(
                f"profile {profile_name} must not include 44-llamacpp-agent-sidecar.yml; route it through the inference-pilot sidecar"
            )

    modules_readme = (ROOT / "compose" / "modules" / "README.md").read_text(encoding="utf-8")
    profiles_readme = (ROOT / "compose" / "profiles" / "README.md").read_text(encoding="utf-8")
    for required_text in (
        "`substrate`",
        "`workflows`",
        "`local-worker`",
        "`intel-worker`",
        "`fallback-gateway`",
        "`44-llamacpp-agent-sidecar.yml`",
    ):
        if required_text not in modules_readme:
            errors.append(f"compose/modules/README.md must mention {required_text}")
        if required_text not in profiles_readme:
            errors.append(f"compose/profiles/README.md must mention {required_text}")

    expected_presets = {
        "agent-federation.txt": ["substrate", "local-worker", "federation"],
        "agent-tools.txt": ["substrate", "local-worker", "tools"],
        "agent-observability.txt": ["substrate", "local-worker", "observability"],
        "agent-full.txt": ["substrate", "local-worker", "tools", "observability"],
        "intel-federation.txt": ["substrate", "intel-worker", "federation"],
        "intel-tools.txt": ["substrate", "intel-worker", "tools"],
        "intel-observability.txt": ["substrate", "intel-worker", "observability"],
        "intel-full.txt": ["substrate", "intel-worker", "tools", "observability"],
    }
    for preset_name, expected_profile_names in expected_presets.items():
        preset_path = PRESET_DIR / preset_name
        if not preset_path.exists():
            errors.append(f"missing required preset: {preset_path.relative_to(ROOT)}")
            continue
        preset_profiles = load_names(preset_path)
        if preset_profiles != expected_profile_names:
            errors.append(
                f"preset {preset_name} must resolve to {', '.join(expected_profile_names)}"
            )

    github_workflow = (
        ROOT / ".github" / "workflows" / "validate-stack.yml"
    ).read_text(encoding="utf-8")
    if "--profile intel-worker" not in github_workflow:
        errors.append(".github/workflows/validate-stack.yml must rehearse the intel-worker profile")
    if "--profile workflows" not in github_workflow:
        errors.append(".github/workflows/validate-stack.yml must rehearse the optional workflows profile")
    if (
        "--profile substrate --profile local-worker --profile tools --profile observability"
        not in github_workflow
    ):
        errors.append(
            ".github/workflows/validate-stack.yml must rehearse the composition-first agent-full profile set"
        )
    if "agentic,tools,observability" in github_workflow:
        errors.append(
            ".github/workflows/validate-stack.yml must not use agentic as the active combined route"
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

    orchestration_module = (MODULE_DIR / "20-orchestration.yml").read_text(encoding="utf-8")
    for snippet in (
        "n8n-task-runners:",
        "N8N_RUNNERS_ENABLED",
        "N8N_RUNNERS_MODE: external",
        "N8N_RUNNERS_BROKER_LISTEN_ADDRESS: 0.0.0.0",
        "N8N_NATIVE_PYTHON_RUNNER",
        "N8N_RUNNERS_TASK_BROKER_URI: http://n8n:5679",
    ):
        if snippet not in orchestration_module:
            errors.append(f"compose/modules/20-orchestration.yml must include n8n external runner setting: {snippet}")
    if not re.search(r"docker\.io/n8nio/runners:[^\s\"']+@sha256:[0-9a-f]{64}", orchestration_module):
        errors.append(
            "compose/modules/20-orchestration.yml must pin n8n-task-runners as docker.io/n8nio/runners:<version>@sha256:<digest>"
        )

    stack_env_example = (ROOT / "env" / "stack.env.example").read_text(encoding="utf-8")
    if "N8N_RUNNERS_AUTH_TOKEN=CHANGE_ME_LONG_RANDOM_SHARED_SECRET" not in stack_env_example:
        errors.append("env/stack.env.example must include N8N_RUNNERS_AUTH_TOKEN placeholder for external n8n runners")

    service_catalog_doc = (ROOT / "docs" / "runtime" / "SERVICE_CATALOG.md").read_text(encoding="utf-8")
    if "n8n-task-runners" not in service_catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention n8n-task-runners")

    warmup_script = (
        ROOT / "mechanics/runtime-lifecycle/parts/start-stop/aoa_warmup.sh"
    ).read_text(encoding="utf-8")
    deployment_doc = (ROOT / "docs" / "install" / "DEPLOYMENT.md").read_text(
        encoding="utf-8"
    )
    start_stop_readme = (
        ROOT / "mechanics/runtime-lifecycle/parts/start-stop/README.md"
    ).read_text(encoding="utf-8")
    if (
        "AOA_OLLAMA_WARMUP_ENABLED" not in warmup_script
        or "ollama warmup disabled" not in warmup_script
    ):
        errors.append(
            "aoa-warmup must keep Ollama fallback warmup behind AOA_OLLAMA_WARMUP_ENABLED"
        )
    if (
        "AOA_LLAMACPP_WARMUP_ENABLED" not in warmup_script
        or "llama.cpp warmup complete" not in warmup_script
    ):
        errors.append("aoa-warmup must keep llama.cpp local-worker warmup explicit")
    for required_text in (
        "AOA_OLLAMA_WARMUP_ENABLED=true",
        "`llama.cpp`",
        "Ollama",
    ):
        if required_text not in deployment_doc:
            errors.append(
                f"docs/install/DEPLOYMENT.md must mention {required_text} warmup posture"
            )
        if required_text not in start_stop_readme:
            errors.append(
                f"mechanics/runtime-lifecycle/parts/start-stop/README.md must mention {required_text} warmup posture"
            )

    for active_route_doc in (
        ROOT / "mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md",
        ROOT
        / "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_RUNTIME_PACKET.md",
        ROOT
        / "mechanics/runtime-lifecycle/parts/start-stop/docs/LIVE_RUNTIME_CUTOVER_PACKET.md",
        ROOT / "mechanics/federation-seams/parts/tos-graph/docs/TOS_GRAPH_CURATION.md",
        ROOT / "mechanics/machine-fit/parts/fit-record/docs/PROFILE_MACHINE_FIT_PACKET.md",
    ):
        active_route_text = active_route_doc.read_text(encoding="utf-8")
        if "--profile core" in active_route_text:
            errors.append(
                f"{active_route_doc.relative_to(ROOT)} must use substrate/local-worker/"
                "fallback-gateway or an explicit preset instead of --profile core"
            )

    secrets_doc = (
        ROOT
        / "mechanics"
        / "config-projection"
        / "parts"
        / "bootstrap"
        / "docs"
        / "SECRETS_BOOTSTRAP.md"
    ).read_text(encoding="utf-8")
    if "N8N_RUNNERS_AUTH_TOKEN" not in secrets_doc or "n8n-task-runners" not in secrets_doc:
        errors.append("mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md must describe the n8n runner shared token")


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
        if STALE_ABYSS_PATTERN.search(text) and path not in STALE_ABYSS_PATH_ALLOWED:
            errors.append(
                f"stale path '{STALE_ABYSS_PATH}' found in {path.relative_to(ROOT)}"
            )
        if STALE_STACK_ROOT in text:
            errors.append(
                f"stale stack root '{STALE_STACK_ROOT}' found in {path.relative_to(ROOT)}"
            )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "Fedora-first" not in readme:
        errors.append("README.md must state Fedora-first posture")
    if "Windows-usable" not in readme:
        errors.append("README.md must state Windows-usable posture")
    if "DESIGN.md" not in readme:
        errors.append("README.md must route readers to DESIGN.md")
    if "DESIGN.AGENTS.md" not in readme:
        errors.append("README.md must route readers to DESIGN.AGENTS.md")
    if "mechanics/governed-execution/parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md" not in readme:
        errors.append("README.md must route readers to mechanics/governed-execution/parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md")
    if "mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md" not in readme:
        errors.append("README.md must route readers to mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md")
    if "mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md" not in readme:
        errors.append("README.md must route readers to mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md")
    if "mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md" not in readme:
        errors.append("README.md must route readers to mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md")
    if "mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md" not in readme:
        errors.append("README.md must route readers to mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md")
    if "docs/governance/BRANCH_POLICY.md" not in readme:
        errors.append("README.md must route readers to docs/governance/BRANCH_POLICY.md")
    if "mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md" not in readme:
        errors.append("README.md must route readers to mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md")
    if "mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md" not in readme:
        errors.append("README.md must route readers to mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md")
    if "mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md" not in readme:
        errors.append("README.md must route readers to mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md")
    if "mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md" not in readme:
        errors.append("README.md must route readers to mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md")
    if "scripts/README.md" not in readme:
        errors.append("README.md must route readers to scripts/README.md")
    if "docs/routes/START_HERE_ROUTE_CONTRACT.md" not in readme:
        errors.append("README.md must route readers to docs/routes/START_HERE_ROUTE_CONTRACT.md")
    for forbidden in (
        "Current contract surfaces are",
        "Chaos receipt examples also now include",
        "To verify the current promoted path",
        "Configs/scripts/aoa-llamacpp-pilot",
        "python scripts/validate_stack.py",
        "python scripts/validate_nested_agents.py",
        "python -m pytest -q",
        "python scripts/build_diagnostic_surface_catalog.py --check",
        "python scripts/validate_diagnostic_surface_catalog.py",
        "diagnostic_target.min.example.json",
        "diagnostic_session.min.example.json",
        "diagnosis_companion.min.example.json",
        "diagnostic_anchor_ref.min.example.json",
        "repair_handoff.min.example.json",
        "reviewed_diagnosis_ref.min.example.json",
        "service-degradation-receipt.timeout-chaos.example.json",
        "service-degradation-receipt.honest-degradation.example.json",
        "service-degradation-receipt.retrieval-outage-honesty.example.json",
        "repair-safe-closeout-receipt.timeout-chaos.example.json",
        "repair-safe-closeout-receipt.retrieval-outage-honesty.example.json",
    ):
        if forbidden in readme:
            errors.append(
                "README.md must stay route-focused; move root inventory detail "
                f"to the owning surface instead of `{forbidden}`"
            )

    local_ai_trials = (
        ROOT
        / "mechanics"
        / "inference-pilots"
        / "parts"
        / "local-trials"
        / "docs"
        / "LOCAL_AI_TRIALS.md"
    ).read_text(encoding="utf-8")
    local_ai_trials_w0_w4_baseline = (
        ROOT
        / "mechanics"
        / "inference-pilots"
        / "legacy"
        / "trials"
        / "raw"
        / "LOCAL_AI_TRIALS_W0_W4_BASELINE.md"
    ).read_text(encoding="utf-8")
    for required_snippet in (
        "TRUTH_SURFACES.md",
        "GOVERNED_EXECUTION.md",
        "legacy/INDEX.md",
        "scripts/aoa-governed-run prepare-canary",
        "scripts/aoa-governed-run materialize-canaries",
        "scripts/aoa-governed-run prepare-request",
        "scripts/aoa-governed-run run --request-file",
        "scripts/aoa-governed-run resume",
        "status --all --explain",
        "scripts/aoa-long-horizon-pilot materialize",
        "run-scenario <scenario-id> --until milestone",
        "resume-scenario <scenario-id>",
        "implementation_patch",
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
                f"mechanics/inference-pilots/parts/local-trials/docs/LOCAL_AI_TRIALS.md must mention `{required_snippet}`"
            )
    for required_snippet in (
        "prepare-wave W4 --lane docs",
        "apply-case W4 <case-id>",
        "proposal.edit-spec.json",
        "exact_replace",
        "anchored_replace",
        "deterministically inside the runner",
        "script_refresh",
        "approval.status.json",
        "isolated git worktree",
    ):
        if required_snippet not in local_ai_trials_w0_w4_baseline:
            errors.append(
                f"mechanics/inference-pilots/legacy/trials/raw/LOCAL_AI_TRIALS_W0_W4_BASELINE.md must mention `{required_snippet}`"
            )

    truth_doc = (
        ROOT
        / "mechanics"
        / "diagnostic-spine"
        / "parts"
        / "truth-surfaces"
        / "docs"
        / "TRUTH_SURFACES.md"
    ).read_text(encoding="utf-8")
    for required_snippet in (
        "source_authored",
        "deployed",
        "trial_proven",
        "live_available",
        "~/src/abyss-stack",
        "AOA_SOURCE_ROOT",
        "/srv/AbyssOS/abyss-stack",
        "trial_proven is not a synonym for production readiness",
        "aoa-llamacpp-pilot verify",
        "aoa-sync-federation-surfaces --check --json",
        "aoa-status --autonomy --json",
    ):
        if required_snippet not in truth_doc:
            errors.append(
                f"mechanics/diagnostic-spine/parts/truth-surfaces/docs/TRUTH_SURFACES.md must mention `{required_snippet}`"
            )

    governed_doc = (
        ROOT
        / "mechanics"
        / "governed-execution"
        / "parts"
        / "governed-runner"
        / "docs"
        / "GOVERNED_EXECUTION.md"
    ).read_text(encoding="utf-8")
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
            errors.append(f"mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md must mention `{required_snippet}`")

    w5_doc_path = ROOT / "mechanics" / "inference-pilots" / "legacy" / "trials" / "raw" / "W5_PILOT.md"
    w5_doc = w5_doc_path.read_text(encoding="utf-8")
    for required_snippet in (
        "TRUTH_SURFACES.md",
        "http://127.0.0.1:5403/run",
        "scripts/aoa-long-horizon-pilot materialize",
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
            errors.append(f"{w5_doc_path.relative_to(ROOT)} must mention `{required_snippet}`")

    w6_doc_path = ROOT / "mechanics" / "inference-pilots" / "legacy" / "trials" / "raw" / "W6_PILOT.md"
    w6_doc = w6_doc_path.read_text(encoding="utf-8")
    for required_snippet in (
        "TRUTH_SURFACES.md",
        "http://127.0.0.1:5403/run",
        "scripts/aoa-bounded-autonomy-pilot materialize",
        "run-scenario <scenario-id> --until milestone|done",
        "resume-scenario <scenario-id>",
        "status --all",
        "stack-sync-federation-json-check-report",
        "llamacpp-pilot-verify-command",
        "trial_proven",
        "live_available",
        "aoa-status --autonomy",
    ):
        if required_snippet not in w6_doc:
            errors.append(f"{w6_doc_path.relative_to(ROOT)} must mention `{required_snippet}`")

    paths_doc = (ROOT / "docs" / "runtime" / "PATHS.md").read_text(encoding="utf-8")
    if "/srv/AbyssOS/abyss-stack" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention /srv/AbyssOS/abyss-stack")
    if "WSL2" not in paths_doc:
        errors.append(
            "docs/runtime/PATHS.md should mention WSL2 in the Windows-usable model"
        )
    if "AOA_ROUTING_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_ROUTING_ROOT")
    if "AOA_SOURCE_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_SOURCE_ROOT")
    if "AOA_MEMO_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_MEMO_ROOT")
    if "AOA_EVALS_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_EVALS_ROOT")
    if "AOA_PLAYBOOKS_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_PLAYBOOKS_ROOT")
    if "AOA_KAG_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_KAG_ROOT")
    if "AOA_TOS_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_TOS_ROOT")

    deployment_doc = (ROOT / "docs" / "install" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    for required_snippet in (
        "source-authored change is not live until `scripts/aoa-sync-configs` updates `/srv/AbyssOS/abyss-stack/Configs`",
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
                f"docs/install/DEPLOYMENT.md must mention `{required_snippet}`"
            )
    if "scripts/aoa-sync-federation-surfaces --layer aoa-routing" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention aoa-routing federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer aoa-memo" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention aoa-memo federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer aoa-evals" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention aoa-evals federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer aoa-playbooks" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention aoa-playbooks federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer aoa-kag" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention aoa-kag federation sync")
    if "scripts/aoa-sync-federation-surfaces --layer tos-source" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention tos-source federation sync")

    profiles_doc = (ROOT / "docs" / "profiles" / "PROFILES.md").read_text(encoding="utf-8")
    if "aoa-routing advisory seam" not in profiles_doc:
        errors.append("docs/profiles/PROFILES.md must describe the aoa-routing advisory seam")
    if "aoa-memo" not in profiles_doc:
        errors.append("docs/profiles/PROFILES.md must describe the aoa-memo recall seam")
    if "aoa-evals" not in profiles_doc:
        errors.append("docs/profiles/PROFILES.md must describe the aoa-evals eval selection seam")
    if "aoa-playbooks" not in profiles_doc:
        errors.append("docs/profiles/PROFILES.md must describe the aoa-playbooks advisory seam")
    if "aoa-kag" not in profiles_doc:
        errors.append("docs/profiles/PROFILES.md must describe the aoa-kag advisory seam")
    if "tos-source" not in profiles_doc:
        errors.append("docs/profiles/PROFILES.md must describe the tos-source handoff seam")

    recipes_doc = (ROOT / "docs" / "profiles" / "PROFILE_RECIPES.md").read_text(encoding="utf-8")
    if "aoa-routing" not in recipes_doc:
        errors.append("docs/profiles/PROFILE_RECIPES.md must mention aoa-routing")
    if "aoa-memo" not in recipes_doc:
        errors.append("docs/profiles/PROFILE_RECIPES.md must mention aoa-memo")
    if "aoa-evals" not in recipes_doc:
        errors.append("docs/profiles/PROFILE_RECIPES.md must mention aoa-evals")
    if "aoa-playbooks" not in recipes_doc:
        errors.append("docs/profiles/PROFILE_RECIPES.md must mention aoa-playbooks")
    if "aoa-kag" not in recipes_doc:
        errors.append("docs/profiles/PROFILE_RECIPES.md must mention aoa-kag")
    if "tos-source" not in recipes_doc:
        errors.append("docs/profiles/PROFILE_RECIPES.md must mention tos-source")

    catalog_doc = (ROOT / "docs" / "runtime" / "SERVICE_CATALOG.md").read_text(encoding="utf-8")
    if "aoa-routing advisory routing surfaces" not in catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention aoa-routing advisory routing surfaces")
    if "aoa-memo" not in catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention aoa-memo")
    if "aoa-evals" not in catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention aoa-evals")
    if "aoa-playbooks" not in catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention aoa-playbooks")
    if "aoa-kag" not in catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention aoa-kag")
    if "tos-source" not in catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention tos-source")
    if "aoa-governed-run" not in catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention aoa-governed-run")
    if "promotion summaries" not in catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention promotion summaries")

    storage_doc = (ROOT / "docs" / "runtime" / "STORAGE_LAYOUT.md").read_text(encoding="utf-8")
    if "Knowledge/federation/aoa-routing/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-routing/")
    if "Knowledge/federation/aoa-memo/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-memo/")
    if "Knowledge/federation/aoa-evals/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-evals/")
    if "Knowledge/federation/aoa-playbooks/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-playbooks/")
    if "Knowledge/federation/aoa-kag/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Knowledge/federation/aoa-kag/")
    if "Knowledge/federation/tos-source/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Knowledge/federation/tos-source/")
    if "Logs/memo-exports/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Logs/memo-exports/")
    if "Logs/eval-exports/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Logs/eval-exports/")
    if "Logs/rpg/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Logs/rpg/")
    if "mechanics/federation-seams/parts/rpg-runtime/generated/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention mechanics/federation-seams/parts/rpg-runtime/generated/")

    lifecycle_doc = (ROOT / "docs" / "operations" / "LIFECYCLE.md").read_text(encoding="utf-8")
    for required_snippet in (
        "source_authored",
        "deployed",
        "trial_proven",
        "live_available",
        "python scripts/validate_stack.py --parity-check",
    ):
        if required_snippet not in lifecycle_doc:
            errors.append(f"docs/operations/LIFECYCLE.md must mention `{required_snippet}`")

    playbook_runtime_doc = (
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "playbook-seam"
        / "docs"
        / "PLAYBOOK_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for required_snippet in (
        "aoa-governed-run",
        "governed-execution-policy.yaml",
        "trust state",
        "runtime permission semantics still live in `abyss-stack`",
    ):
        if required_snippet not in playbook_runtime_doc:
            errors.append(f"mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md must mention `{required_snippet}`")

    recurrence_doc = (
        ROOT
        / "mechanics"
        / "governed-execution"
        / "parts"
        / "return-policy"
        / "docs"
        / "RECURRENCE_RUNTIME_POLICY.md"
    ).read_text(encoding="utf-8")
    for required_snippet in (
        "governed-execution-policy.yaml",
        "runtime execution permissions only",
        "langchain-api /run/federated",
    ):
        if required_snippet not in recurrence_doc:
            errors.append(f"mechanics/governed-execution/parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md must mention `{required_snippet}`")

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
                    f"--techniques-root {WORKSPACE_SIBLING_ROOTS['aoa-techniques']}",
                    f"--skills-root {WORKSPACE_SIBLING_ROOTS['aoa-skills']}",
                    f"--evals-root {WORKSPACE_SIBLING_ROOTS['aoa-evals']}",
                    f"--memo-root {WORKSPACE_SIBLING_ROOTS['aoa-memo']}",
                    f"--agents-root {WORKSPACE_SIBLING_ROOTS['aoa-agents']}",
                    f"--aoa-root {WORKSPACE_SIBLING_ROOTS['Agents-of-Abyss']}",
                    f"--playbooks-root {WORKSPACE_SIBLING_ROOTS['aoa-playbooks']}",
                    f"--kag-root {WORKSPACE_SIBLING_ROOTS['aoa-kag']}",
                    f"--tos-root {WORKSPACE_SIBLING_ROOTS['Tree-of-Sophia']}",
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


def validate_mechanics_topology(errors: list[str]) -> None:
    mechanics_root = ROOT / "mechanics"
    for path in (
        mechanics_root / "AGENTS.md",
        mechanics_root / "README.md",
        mechanics_root / "ARTIFACT_TOPOLOGY.md",
        ROOT / "docs" / "runtime" / "MECHANICS.md",
    ):
        if not path.is_file():
            errors.append(f"mechanics topology root is missing {path.relative_to(ROOT)}")

    atlas_text = read_text_or_none(mechanics_root / "README.md") or ""
    for package in MECHANIC_PACKAGES:
        if f"]({package}/README.md)" not in atlas_text:
            errors.append(f"mechanics atlas must route to {package}/README.md")

        package_root = mechanics_root / package
        for required_file in MECHANIC_PACKAGE_REQUIRED_FILES:
            path = package_root / required_file
            if not path.is_file():
                errors.append(f"mechanics package {package} is missing {required_file}")

        parts_readme = read_text_or_none(package_root / "parts" / "README.md") or ""
        parts_root = package_root / "parts"
        if parts_root.is_dir():
            for part_dir in sorted(item for item in parts_root.iterdir() if item.is_dir()):
                if (
                    part_dir.name in FORBIDDEN_ACTIVE_PART_NAMES
                    or FORBIDDEN_ACTIVE_PART_NAME_FRAGMENT in part_dir.name
                ):
                    errors.append(
                        f"mechanics package {package} has archived/noisy active part name: parts/{part_dir.name}"
                    )
        for part in MECHANIC_PACKAGE_PARTS.get(package, ()):
            part_readme = package_root / "parts" / part / "README.md"
            if not part_readme.is_file():
                errors.append(
                    f"mechanics package {package} is missing parts/{part}/README.md"
                )
            if f"]({part}/README.md)" not in parts_readme:
                errors.append(
                    f"mechanics package {package} parts/README.md must route to parts/{part}/README.md"
                )
            for required_file in MECHANIC_PART_REQUIRED_FILES.get((package, part), ()):
                path = package_root / "parts" / part / required_file
                if not path.is_file():
                    errors.append(
                        f"mechanics package {package} part {part} is missing {required_file}"
                    )

        active_route_files = [package_root / "PARTS.md"]
        if parts_root.is_dir():
            active_route_files.extend(sorted(parts_root.glob("*/README.md")))
        for route_file in active_route_files:
            route_text = read_text_or_none(route_file) or ""
            if "legacy/raw" in route_text:
                errors.append(
                    f"{route_file.relative_to(ROOT)} should route through PROVENANCE.md or legacy/INDEX.md instead of legacy/raw"
                )

        readme_text = read_text_or_none(package_root / "README.md") or ""
        for heading in MECHANIC_CARD_HEADINGS:
            if heading not in readme_text:
                errors.append(
                    f"mechanics package {package} README.md must include `{heading}`"
                )

        if package in ARCHIVE_MECHANIC_PACKAGES:
            required_files = (
                *ARCHIVE_MECHANIC_REQUIRED_FILES,
                *ARCHIVE_MECHANIC_EXTRA_REQUIRED_FILES.get(package, ()),
            )
            for required_file in required_files:
                path = package_root / required_file
                if not path.is_file():
                    errors.append(f"mechanics archive package {package} is missing {required_file}")
            for required_dir in ARCHIVE_MECHANIC_ARTIFACT_DIRS.get(package, ()):
                path = package_root / required_dir
                if not path.is_dir():
                    errors.append(f"mechanics archive package {package} is missing {required_dir}")
            if package in MARKER_ONLY_ARCHIVE_ARTIFACT_PACKAGES:
                marker_root = package_root / "legacy" / "artifacts"
                artifact_files = sorted(
                    item.relative_to(package_root).as_posix()
                    for item in marker_root.rglob("*")
                    if item.is_file()
                    and item.relative_to(marker_root).as_posix() != "README.md"
                )
                if artifact_files:
                    errors.append(
                        f"mechanics archive package {package} legacy/artifacts must stay marker-only, found {artifact_files}"
                    )


def git_index_mode(path: Path) -> str | None:
    try:
        rel_path = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return None

    completed = subprocess.run(
        ["git", "ls-files", "--stage", "--", rel_path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None

    first_line = completed.stdout.strip().splitlines()
    if not first_line:
        return None
    fields = first_line[0].split()
    if not fields:
        return None
    return fields[0]


def is_executable_source_path(path: Path) -> bool:
    if path.stat().st_mode & 0o111:
        return True
    return git_index_mode(path) == "100755"


def validate_scripts(errors: list[str]) -> None:
    script_names = {path.name for path in (ROOT / "scripts").iterdir() if path.is_file()}
    missing = sorted(REQUIRED_SCRIPTS - script_names)
    missing_backend_routes = sorted(REQUIRED_SCRIPTS - set(OPERATOR_BACKEND_SCRIPTS))
    extra_backend_routes = sorted(set(OPERATOR_BACKEND_SCRIPTS) - REQUIRED_SCRIPTS)

    for name in missing:
        errors.append(f"missing required script: scripts/{name}")
    for name in missing_backend_routes:
        errors.append(f"missing operator backend route for required script: scripts/{name}")
    for name in extra_backend_routes:
        errors.append(f"operator backend route is not a required script: scripts/{name}")

    for script_name, backend_rel in sorted(OPERATOR_BACKEND_SCRIPTS.items()):
        backend_path = ROOT / backend_rel
        if not backend_path.is_file():
            errors.append(f"missing operator backend for scripts/{script_name}: {backend_rel}")
            continue
        if backend_path.suffix.lower() != ".ps1" and not is_executable_source_path(backend_path):
            errors.append(f"operator backend is not executable: {backend_rel}")

        wrapper_path = ROOT / "scripts" / script_name
        if wrapper_path.exists():
            wrapper_text = wrapper_path.read_text(encoding="utf-8")
            if f"../{backend_rel}" not in wrapper_text:
                errors.append(f"scripts/{script_name} must exec ../{backend_rel}")

    llamacpp_pilot = (ROOT / OPERATOR_BACKEND_SCRIPTS["aoa-llamacpp-pilot"]).read_text(encoding="utf-8")
    if "podman\", \"network\", \"connect\"" not in llamacpp_pilot:
        errors.append("scripts/aoa-llamacpp-pilot must connect the sidecar to the primary runtime network")
    if "abyss_default" not in llamacpp_pilot:
        errors.append("scripts/aoa-llamacpp-pilot must mention abyss_default as the primary runtime network")

    install_systemd_rel = OPERATOR_BACKEND_SCRIPTS.get("aoa-install-systemd")
    if install_systemd_rel:
        install_systemd_path = ROOT / install_systemd_rel
        if install_systemd_path.is_file():
            install_systemd = install_systemd_path.read_text(encoding="utf-8")
            for required_snippet in (
                "--preset",
                "--profile",
                "--overlay",
                "--restart-now",
                "--all-user-units",
                "--system-units",
                "AOA_EXTRA_COMPOSE_FILES",
                "managed-units.txt",
                "systemctl daemon-reload",
                "20-runtime-selection.conf",
                "aoa_validate_runtime_spec",
                "aoa_validate_overlay_spec",
                "aoa_append_runtime_spec",
            ):
                if required_snippet not in install_systemd:
                    errors.append(
                        f"scripts/aoa-install-systemd must preserve user-unit runtime selection via `{required_snippet}`"
                    )

    apply_resource_guards_rel = OPERATOR_BACKEND_SCRIPTS.get("aoa-apply-resource-guards")
    if apply_resource_guards_rel:
        apply_resource_guards_path = ROOT / apply_resource_guards_rel
        if apply_resource_guards_path.is_file():
            apply_resource_guards = apply_resource_guards_path.read_text(encoding="utf-8")
            for required_snippet in (
                "--dry-run",
                "--force",
                "--wait-game-guard-clear",
                "--wait-resource-plan-clear",
                "--wait-timeout-sec",
                "--wait-poll-sec",
                "resource plan",
                "resource plan --class medium --kind generic --unattended --json",
                "--method",
                "recreate",
                "AOA_UP_FORCE_RECREATE",
                "set-environment",
                "aoa-status\" --resource-guards --json",
                "abyss-machine processes game-guard --json",
                "systemctl --user \"$method\" podman-compose-abyss.service",
                "post-apply.json",
                "pre-service-selection.json",
                "post-service-selection.json",
                "pre-resource-plan.json",
                "post-resource-plan.json",
                "pre-podman-stats.txt",
                "post-podman-stats.txt",
                "pre-memory.txt",
                "post-memory.txt",
                "pre-protected-units.txt",
                "post-protected-units.txt",
                "protected user units degraded after apply",
                "abyss-tts-server.service",
                "abyss-dictation-server.service",
                "abyss-tts-keepwarm.timer",
                "podman stats --no-stream",
                "service selection degraded after apply",
                "resource guards still not fully applied",
            ):
                if required_snippet not in apply_resource_guards:
                    errors.append(
                        f"scripts/aoa-apply-resource-guards must preserve guarded apply behavior via `{required_snippet}`"
                    )

    aoa_up_rel = OPERATOR_BACKEND_SCRIPTS.get("aoa-up")
    if aoa_up_rel:
        aoa_up_path = ROOT / aoa_up_rel
        if aoa_up_path.is_file():
            aoa_up = aoa_up_path.read_text(encoding="utf-8")
            for required_snippet in (
                "AOA_UP_FORCE_RECREATE",
                "--force-recreate",
            ):
                if required_snippet not in aoa_up:
                    errors.append(
                        f"scripts/aoa-up must preserve force-recreate support via `{required_snippet}`"
                    )

    status_rel = OPERATOR_BACKEND_SCRIPTS.get("aoa-status")
    if status_rel:
        status_path = ROOT / status_rel
        if status_path.is_file():
            status_script = status_path.read_text(encoding="utf-8")
            for required_snippet in (
                "--resource-guards",
                "--service-selection",
                "--optimization",
                "--optimization-audit",
                "--require-complete",
                "aoa_resource_guard_status.py",
                "aoa_service_selection_status.py",
                "aoa_optimization_status.py",
                "aoa_optimization_audit_status.py",
            ):
                if required_snippet not in status_script:
                    errors.append(
                        f"scripts/aoa-status must preserve runtime status modes via `{required_snippet}`"
                    )


def validate_required_files(errors: list[str]) -> None:
    for path in sorted(REQUIRED_FILES):
        if not path.exists():
            errors.append(f"missing required file: {path.relative_to(ROOT)}")

    for unit_scope in ("user", "system"):
        managed_units = ROOT / "systemd" / unit_scope / "managed-units.txt"
        if managed_units not in REQUIRED_FILES:
            continue
        if not managed_units.exists():
            continue
        for line in managed_units.read_text(encoding="utf-8").splitlines():
            unit_name = line.split("#", 1)[0].strip()
            if not unit_name:
                continue
            unit_path = ROOT / "systemd" / unit_scope / unit_name
            if not unit_path.exists():
                errors.append(
                    f"managed {unit_scope} unit is missing source skeleton: systemd/{unit_scope}/{unit_name}"
                )


def validate_root_residual_topology(errors: list[str]) -> None:
    forbidden_paths = {
        ROOT / "AUDIT.md": "docs/routes/AUDIT.md",
        ROOT / "Spark": ".agents/spark/",
        ROOT / ".github" / "README.md": ".github/GITHUB_SURFACE.md",
        ROOT / "docs" / "START_HERE_ROUTE_CONTRACT.md": "docs/routes/START_HERE_ROUTE_CONTRACT.md",
        ROOT / "docs" / "AUDIT.md": "docs/routes/AUDIT.md",
        ROOT / "docs" / "ARCHITECTURE.md": "docs/runtime/ARCHITECTURE.md",
        ROOT / "docs" / "MECHANICS.md": "docs/runtime/MECHANICS.md",
        ROOT / "docs" / "PATHS.md": "docs/runtime/PATHS.md",
        ROOT / "docs" / "SERVICE_CATALOG.md": "docs/runtime/SERVICE_CATALOG.md",
        ROOT / "docs" / "STORAGE_LAYOUT.md": "docs/runtime/STORAGE_LAYOUT.md",
        ROOT / "docs" / "DEPLOYMENT.md": "docs/install/DEPLOYMENT.md",
        ROOT / "docs" / "FIRST_RUN.md": "docs/install/FIRST_RUN.md",
        ROOT / "docs" / "BACKUP_RESTORE.md": "docs/operations/BACKUP_RESTORE.md",
        ROOT / "docs" / "LIFECYCLE.md": "docs/operations/LIFECYCLE.md",
        ROOT / "docs" / "RUNBOOK.md": "docs/operations/RUNBOOK.md",
        ROOT / "docs" / "SECURITY.md": "docs/operations/SECURITY.md",
        ROOT / "docs" / "PRESETS.md": "docs/profiles/PRESETS.md",
        ROOT / "docs" / "PROFILES.md": "docs/profiles/PROFILES.md",
        ROOT / "docs" / "PROFILE_RECIPES.md": "docs/profiles/PROFILE_RECIPES.md",
        ROOT / "docs" / "BRANCH_POLICY.md": "docs/governance/BRANCH_POLICY.md",
        ROOT / "docs" / "QUESTBOOK_STACK_INTEGRATION.md": "docs/governance/QUESTBOOK_STACK_INTEGRATION.md",
        ROOT / "docs" / "RELEASING.md": "docs/governance/RELEASING.md",
        ROOT / "docs" / "AGENTS_ROOT_REFERENCE.md": "docs/legacy/AGENTS_ROOT_REFERENCE.md",
        ROOT / "docs" / "MIGRATION_FROM_OLD.md": "docs/legacy/MIGRATION_FROM_OLD.md",
    }
    for path, target in forbidden_paths.items():
        if path.exists():
            errors.append(
                f"root residual topology path {path.relative_to(ROOT)} must live under {target}"
            )

    agents_readme = read_text_or_none(ROOT / ".agents" / "README.md") or ""
    docs_readme = read_text_or_none(ROOT / "docs" / "README.md") or ""
    if ".agents/spark" not in agents_readme and "spark/README.md" not in agents_readme:
        errors.append(".agents/README.md must route the Spark fast-loop lane")
    if "routes/AUDIT.md" not in docs_readme:
        errors.append("docs/README.md must route docs/routes/AUDIT.md")
    for district in (
        "routes/",
        "runtime/",
        "install/",
        "operations/",
        "profiles/",
        "governance/",
        "decisions/",
        "legacy/",
    ):
        if district not in docs_readme:
            errors.append(f"docs/README.md must route docs/{district}")


def validate_agent_skill_projection_routes(errors: list[str]) -> None:
    skills_root = ROOT / ".agents" / "skills"
    if not skills_root.is_dir():
        errors.append(".agents/skills must exist as the repo-local skill projection surface")
        return

    for path in sorted(skills_root.iterdir()):
        if path.name == "AGENTS.md":
            continue
        rel_path = path.relative_to(ROOT).as_posix()
        if path.name in LOCAL_SKILL_OVERLAY_NAMES:
            if not path.is_dir() or not (path / "SKILL.md").is_file():
                errors.append(f"{rel_path} must stay as a local overlay directory with SKILL.md")
            continue
        expected_target = f"{AOA_SKILL_INSTALL_ROOT}/{path.name}"
        if _matches_checkout_safe_overlay_install(path, expected_target):
            continue
        if not path.is_symlink():
            errors.append(f"{rel_path} must be a symlink into {AOA_SKILL_INSTALL_ROOT}")
            continue
        try:
            actual_target = path.readlink().as_posix()
        except OSError:
            errors.append(f"{rel_path} symlink target cannot be read")
            continue
        if actual_target != expected_target:
            errors.append(
                f"{rel_path} must target {expected_target}, got {actual_target}"
            )


def validate_local_trials_compatibility_bridge(errors: list[str]) -> None:
    bridge_path = ROOT / "mechanics" / "inference-pilots" / "parts" / "local-trials" / "aoa_local_ai_trials.py"
    adapter_path = (
        ROOT
        / "mechanics"
        / "inference-pilots"
        / "parts"
        / "local-trials"
        / "trial_compatibility_bridge.py"
    )
    legacy_path = (
        ROOT
        / "mechanics"
        / "inference-pilots"
        / "legacy"
        / "trials"
        / "artifacts"
        / "scripts"
        / "aoa-local-ai-trials"
    )
    bridge_text = read_text_or_none(bridge_path) or ""
    adapter_text = read_text_or_none(adapter_path) or ""
    legacy_text = read_text_or_none(legacy_path) or ""

    if "LEGACY_BACKEND" not in bridge_text or "aoa-local-ai-trials" not in bridge_text:
        errors.append("local trials active backend must be a compatibility bridge to the legacy runner")
    for required_snippet in (
        "CompatibilityGate",
        "RUNTIME_GATE",
        "EDIT_GATE",
        "runtime_gate_run_command",
        "edit_gate_approval_path",
    ):
        if required_snippet not in adapter_text:
            errors.append(
                "mechanics/inference-pilots/parts/local-trials/trial_compatibility_bridge.py "
                f"must expose `{required_snippet}`"
            )
    stale_adapter_path = (
        ROOT
        / "mechanics"
        / "inference-pilots"
        / "parts"
        / "local-trials"
        / "legacy_trial_adapter.py"
    )
    if stale_adapter_path.exists():
        errors.append(
            "mechanics/inference-pilots/parts/local-trials/legacy_trial_adapter.py "
            "must not return as an active module; use trial_compatibility_bridge.py"
        )
    stale_requirements_path = ROOT / "scripts" / "requirements-langgraph-pilot.txt"
    if stale_requirements_path.exists():
        errors.append(
            "scripts/requirements-langgraph-pilot.txt must stay moved to "
            "mechanics/inference-pilots/parts/langgraph-pilot/requirements.txt"
        )
    if "WAVE_METADATA =" in bridge_text:
        errors.append("local trials wave metadata must stay in legacy/trials/artifacts/scripts, not the active bridge")
    if "WAVE_METADATA =" not in legacy_text:
        errors.append("legacy local AI trials runner must preserve the W0-W4 compatibility metadata")
    if not is_executable_source_path(legacy_path):
        errors.append("legacy local AI trials runner must stay executable")


def validate_inference_pilot_compatibility_gate_language(errors: list[str]) -> None:
    langgraph_code_path = (
        ROOT
        / "mechanics"
        / "inference-pilots"
        / "parts"
        / "langgraph-pilot"
        / "aoa_langgraph_pilot.py"
    )
    langgraph_doc_path = (
        ROOT
        / "mechanics"
        / "inference-pilots"
        / "parts"
        / "langgraph-pilot"
        / "docs"
        / "LANGGRAPH_PILOT.md"
    )
    llamacpp_code_path = (
        ROOT
        / "mechanics"
        / "inference-pilots"
        / "parts"
        / "llamacpp-pilot"
        / "aoa_llamacpp_pilot.py"
    )
    llamacpp_doc_path = (
        ROOT
        / "mechanics"
        / "inference-pilots"
        / "parts"
        / "llamacpp-pilot"
        / "docs"
        / "LLAMACPP_PILOT.md"
    )
    autonomy_status_path = (
        ROOT
        / "mechanics"
        / "governed-execution"
        / "parts"
        / "autonomy-status"
        / "aoa_status_autonomy.py"
    )
    autonomy_status_readme_path = (
        ROOT
        / "mechanics"
        / "governed-execution"
        / "parts"
        / "autonomy-status"
        / "README.md"
    )

    langgraph_code = read_text_or_none(langgraph_code_path) or ""
    langgraph_doc = read_text_or_none(langgraph_doc_path) or ""
    llamacpp_code = read_text_or_none(llamacpp_code_path) or ""
    llamacpp_doc = read_text_or_none(llamacpp_doc_path) or ""
    autonomy_status = read_text_or_none(autonomy_status_path) or ""
    autonomy_status_readme = read_text_or_none(autonomy_status_readme_path) or ""

    for required_snippet in (
        "TRIAL_ADAPTER",
        "EDIT_GATE_WIRE_ID",
        "EDIT_GATE_INDEX_NAME",
        "preserved bounded-edit compatibility contract",
    ):
        if required_snippet not in langgraph_code:
            errors.append(
                "mechanics/inference-pilots/parts/langgraph-pilot/aoa_langgraph_pilot.py "
                f"must route the preserved edit gate through `{required_snippet}`"
            )

    for required_snippet in (
        "preserved local-trials bounded-edit",
        "bounded-edit compatibility gate",
        "legacy/trials/",
    ):
        if required_snippet not in langgraph_doc:
            errors.append(
                "mechanics/inference-pilots/parts/langgraph-pilot/docs/LANGGRAPH_PILOT.md "
                f"must explain `{required_snippet}`"
            )

    for required_snippet in (
        "TRIAL_ADAPTER",
        "RUNTIME_GATE_WIRE_ID",
        "EDIT_GATE_WIRE_ID",
        "LLAMACPP_RUNTIME_GATE_PROGRAM_ID",
        "LLAMACPP_EDIT_GATE_PROGRAM_ID",
        "runtime_gate_result",
        "edit_fixture_gate_result",
    ):
        if required_snippet not in llamacpp_code:
            errors.append(
                "mechanics/inference-pilots/parts/llamacpp-pilot/aoa_llamacpp_pilot.py "
                f"must route promotion gates through `{required_snippet}`"
            )

    for required_snippet in (
        "runtime compatibility gate",
        "edit fixture compatibility gate",
        "legacy trial runtime gate ID",
        "legacy trial edit gate ID",
    ):
        if required_snippet not in llamacpp_doc:
            errors.append(
                "mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_PILOT.md "
                f"must explain `{required_snippet}`"
            )

    for required_snippet in (
        "PRESERVED_LONG_HORIZON_PROGRAM_ID",
        "PRESERVED_LONG_HORIZON_INDEX_NAME",
        "PRESERVED_BOUNDED_AUTONOMY_PROGRAM_ID",
        "PRESERVED_BOUNDED_AUTONOMY_INDEX_NAME",
    ):
        if required_snippet not in autonomy_status:
            errors.append(
                "mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py "
                f"must route preserved pilot indexes through `{required_snippet}`"
            )
    if "legacy trial compatibility route" not in autonomy_status_readme:
        errors.append(
            "mechanics/governed-execution/parts/autonomy-status/README.md must explain the legacy trial compatibility route"
        )

    active_texts = {
        langgraph_code_path: langgraph_code,
        langgraph_doc_path: langgraph_doc,
        llamacpp_code_path: llamacpp_code,
        llamacpp_doc_path: llamacpp_doc,
    }
    forbidden_active_phrases = (
        "W4-shaped",
        "widen W4",
        "existing W4 bounded runner",
        "W4 bounded edit contract",
        "W4 bounded-mutation contract",
        "W4 supervised-edit contract",
        "W4-compatible",
        "W4 dry-run promotion verdict",
        "bounded W0 + W4 promotion gate",
    )
    for path, text in active_texts.items():
        for phrase in forbidden_active_phrases:
            if phrase in text:
                errors.append(
                    f"{path.relative_to(ROOT)} must use compatibility gate language instead of `{phrase}`"
                )


def compatibility_bridge_config(errors: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(UPSTREAM_COMPATIBILITY_BRIDGE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append("missing config-templates/Configs/federation/upstream-compatibility-bridge.json")
        return {}
    except json.JSONDecodeError as exc:
        errors.append(f"upstream compatibility bridge config must be valid JSON: {exc}")
        return {}
    if payload.get("artifact_kind") != "abyss-stack.upstream-compatibility-bridge":
        errors.append("upstream compatibility bridge config must use artifact_kind abyss-stack.upstream-compatibility-bridge")
    return payload


def iter_compatibility_bridge_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        strings: list[str] = []
        for item in value:
            strings.extend(iter_compatibility_bridge_strings(item))
        return strings
    if isinstance(value, dict):
        strings = []
        for item in value.values():
            strings.extend(iter_compatibility_bridge_strings(item))
        return strings
    return []


def validate_federation_upstream_compatibility(errors: list[str]) -> None:
    verdict_path = (
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "docs"
        / "UPSTREAM_COMPATIBILITY.md"
    )
    readme_path = (
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "README.md"
    )
    parts_path = ROOT / "mechanics" / "federation-seams" / "PARTS.md"
    legacy_index_path = (
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "legacy"
        / "upstream-compatibility"
        / "INDEX.md"
    )

    verdict = read_text_or_none(verdict_path) or ""
    readme = read_text_or_none(readme_path) or ""
    parts = read_text_or_none(parts_path) or ""
    legacy_index = read_text_or_none(legacy_index_path) or ""
    evals_config = read_text_or_none(ROOT / "config-templates" / "Configs" / "federation" / "aoa-evals.yaml") or ""
    playbooks_config = (
        read_text_or_none(ROOT / "config-templates" / "Configs" / "federation" / "aoa-playbooks.yaml") or ""
    )
    bridge_config = compatibility_bridge_config(errors)
    bridge_strings = iter_compatibility_bridge_strings(bridge_config)

    for required_snippet in (
        "single active bridge",
        "legacy/upstream-compatibility/INDEX.md",
        "upstream-compatibility-bridge.json",
        "memo-recall-rerun",
        "automation-plans",
    ):
        if required_snippet not in verdict:
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md "
                f"must keep the lightweight bridge and mention `{required_snippet}`"
            )

    for required_snippet in ("memo-recall-rerun", "memo-contradiction-gap", "memo-contradiction-rerun"):
        if required_snippet not in legacy_index:
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/legacy/upstream-compatibility/INDEX.md "
                f"must classify `{required_snippet}`"
            )
    for bridge_value in bridge_strings:
        if any(marker in bridge_value for marker in ("phase-alpha", "a2a_wave", "playbook_automation_seeds", "seed_staging")):
            if bridge_value not in legacy_index:
                errors.append(
                    "mechanics/federation-seams/parts/federation-checks/legacy/upstream-compatibility/INDEX.md "
                    f"must classify bridge value `{bridge_value}`"
                )
        if bridge_value in verdict and any(
            marker in bridge_value for marker in ("phase-alpha", "a2a_wave", "playbook_automation_seeds", "seed_staging")
        ):
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md "
                f"must keep detailed legacy value `{bridge_value}` in legacy/upstream-compatibility/INDEX.md"
            )
    for path, text in ((readme_path, readme), (parts_path, parts)):
        if "UPSTREAM_COMPATIBILITY.md" not in text:
            errors.append(
                f"{path.relative_to(ROOT)} must route upstream compatibility names through UPSTREAM_COMPATIBILITY.md"
            )
    if "phase-alpha" in evals_config:
        errors.append("aoa-evals federation config must keep upstream memo template names in the bridge config")
    if "playbook_automation_seeds" in playbooks_config:
        errors.append("aoa-playbooks federation config must keep upstream automation file names in the bridge config")


def validate_active_topology_language(errors: list[str]) -> None:
    text_guards = {
        ROOT / "ROADMAP.md": (
            "## Phase ",
            "Phases 0 through 6",
        ),
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "playbook-seam"
        / "docs"
        / "PLAYBOOK_RUNTIME_SEAM.md": (
            "/playbooks/automation-seeds",
            "/playbooks/automation-seed",
            "automation-seed",
            "automation seeds",
        ),
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "eval-seam"
        / "docs"
        / "EVAL_RUNTIME_SEAM.md": (
            "Phase Alpha",
            "phase-alpha",
            "this phase",
        ),
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "memo-seam"
        / "docs"
        / "MEMO_RUNTIME_SEAM.md": (
            "Phase 3",
            "this phase",
        ),
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "rpg-runtime"
        / "docs"
        / "RPG_RUNTIME_BUILDERS.md": (
            "### Phase ",
        ),
        ROOT
        / "mechanics"
        / "inference-pilots"
        / "parts"
        / "local-trials"
        / "docs"
        / "LOCAL_AI_TRIALS.md": (
            "qualification phase",
            "phase-by-phase",
            "archived phase",
        ),
        ROOT
        / "mechanics"
        / "inference-pilots"
        / "parts"
        / "local-trials"
        / "README.md": (
            "phase-gated",
        ),
    }
    for path, forbidden_snippets in text_guards.items():
        text = read_text_or_none(path) or ""
        for snippet in forbidden_snippets:
            if snippet in text:
                errors.append(
                    f"{path.relative_to(ROOT)} must not keep active topology wording `{snippet}`"
                )

    rpg_text_paths = (
        ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "aoa_rpg_runtime_projection.py",
        ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "examples" / "quest_run_result.example.json",
        ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "generated" / "quest_run_results.json",
        ROOT / "mechanics" / "federation-seams" / "parts" / "rpg-runtime" / "generated" / "reputation_ledgers.json",
    )
    for path in rpg_text_paths:
        text = read_text_or_none(path) or ""
        if "RPG_RUNTIME_PROJECTION_WAVE.md" in text:
            errors.append(
                f"{path.relative_to(ROOT)} must target the Agents-of-Abyss runtime-projection part, not the legacy wave doc"
            )

    rpg_bundle_paths = (
        ROOT / FRONTEND_PROJECTION_BUNDLE_SCHEMA_PATH,
        ROOT / FRONTEND_PROJECTION_BUNDLE_EXAMPLE_PATH,
        ROOT / GENERATED_FRONTEND_PROJECTION_BUNDLES_PATH,
    )
    for path in rpg_bundle_paths:
        text = read_text_or_none(path) or ""
        if '"seed"' in text or '"status": "seed"' in text:
            errors.append(
                f"{path.relative_to(ROOT)} must use draft/promoted runtime status language instead of seed status"
            )

    playbooks_config = read_text_or_none(ROOT / "config-templates" / "Configs" / "federation" / "aoa-playbooks.yaml") or ""
    if "playbook_activation.split-wave-cross-repo-rollout.example.json" in playbooks_config:
        errors.append("aoa-playbooks federation allowlist must not require the split-wave activation example")

    route_api = read_text_or_none(ROOT / "config-templates" / "Services" / "route-api" / "app" / "main.py") or ""
    bridge_config_text = read_text_or_none(UPSTREAM_COMPATIBILITY_BRIDGE_PATH) or ""
    for required_snippet in ("memo-recall-rerun", "memo-contradiction-gap", "memo-contradiction-rerun"):
        if required_snippet not in bridge_config_text:
            errors.append(f"upstream compatibility bridge config must expose clean route `{required_snippet}`")
    for required_snippet in ('"/playbooks/automation-plans"', '"/playbooks/automation-plan"', "upstream-compatibility-bridge.json"):
        if required_snippet not in route_api:
            errors.append(f"route-api must expose clean active bridge `{required_snippet}`")
    for required_bridge in (
        '"/playbooks/automation-seeds"',
        '"/playbooks/automation-seed"',
        "compatibility_bridge_for",
    ):
        if required_bridge not in route_api:
            errors.append(f"route-api must preserve compatibility bridge `{required_bridge}`")


def validate_root_design_surfaces(errors: list[str]) -> None:
    def read_required(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            errors.append(f"missing required file: {path.relative_to(ROOT)}")
            return ""

    agents = read_required(ROOT / "AGENTS.md")
    design = read_required(ROOT / "DESIGN.md")
    design_agents = read_required(ROOT / "DESIGN.AGENTS.md")
    charter = read_required(ROOT / "CHARTER.md")
    boundaries = read_required(ROOT / "BOUNDARIES.md")
    docs_readme = read_required(ROOT / "docs" / "README.md")

    for heading in (
        "## Applies to",
        "## Role",
        "## Read before editing",
        "## Boundaries",
        "## Validation",
        "## Closeout",
    ):
        if heading not in agents:
            errors.append(f"AGENTS.md must include `{heading}`")

    for snippet in (
        "DESIGN.md",
        "DESIGN.AGENTS.md",
        "source checkout",
        "deployed runtime root",
        "GitHub Landing Workflow",
        "Post-change Route Review",
    ):
        if snippet not in agents:
            errors.append(f"AGENTS.md must route or describe `{snippet}`")

    for snippet in (
        "runtime body",
        "source checkout",
        "deployed runtime root",
        "Generated companions stay companions",
        "Runtime, not meaning",
    ):
        if snippet not in design:
            errors.append(f"DESIGN.md must describe `{snippet}`")

    for snippet in (
        "Canonical Card Shape",
        "root card",
        "district cards",
        "mechanic package cards",
        "part cards",
        "generated companions",
    ):
        if snippet not in design_agents:
            errors.append(f"DESIGN.AGENTS.md must describe `{snippet}`")

    if "DESIGN.md" not in charter or "DESIGN.AGENTS.md" not in charter:
        errors.append("CHARTER.md must point to root design surfaces")

    for snippet in ("DESIGN.md", "DESIGN.AGENTS.md", "AGENTS.md"):
        if snippet not in boundaries:
            errors.append(f"BOUNDARIES.md must point to `{snippet}`")
        if snippet not in docs_readme:
            errors.append(f"docs/README.md must point to `{snippet}`")


def validate_entry_route_contract(errors: list[str]) -> None:
    route_contract = read_text_or_none(ROOT / "docs" / "routes" / "START_HERE_ROUTE_CONTRACT.md") or ""
    readme = read_text_or_none(ROOT / "README.md") or ""
    agents = read_text_or_none(ROOT / "AGENTS.md") or ""
    docs_readme = read_text_or_none(ROOT / "docs" / "README.md") or ""
    docs_agents = read_text_or_none(ROOT / "docs" / "AGENTS.md") or ""

    route_modes = (
        "first-reading",
        "runtime-design",
        "agent-guidance",
        "source-install",
        "runtime-operation",
        "mechanic-change",
        "machine-fit",
        "diagnostics-repair",
        "direction-change",
        "release-history",
        "decision-rationale",
    )

    for surface_name, text in (
        ("README.md", readme),
        ("AGENTS.md", agents),
        ("docs/README.md", docs_readme),
        ("docs/AGENTS.md", docs_agents),
    ):
        if "START_HERE_ROUTE_CONTRACT.md" not in text:
            errors.append(f"{surface_name} must point to docs/routes/START_HERE_ROUTE_CONTRACT.md")

    for mode in route_modes:
        if mode not in route_contract:
            errors.append(f"docs/routes/START_HERE_ROUTE_CONTRACT.md must define route mode `{mode}`")
        if mode not in readme:
            errors.append(f"README.md must expose route mode `{mode}`")

    for snippet in (
        "scripts/release_check.py",
        "Root entry surfaces should point here",
        "Exact current command lanes live in",
        "Decision records explain why. Current source surfaces define what.",
        "Diagnostic and repair surfaces are evidence and handoff routes",
    ):
        if snippet not in route_contract:
            errors.append(f"docs/routes/START_HERE_ROUTE_CONTRACT.md must mention `{snippet}`")


def validate_decision_record_surface(errors: list[str]) -> None:
    decisions_readme = read_text_or_none(ROOT / "docs" / "decisions" / "README.md") or ""
    decisions_agents = read_text_or_none(ROOT / "docs" / "decisions" / "AGENTS.md") or ""
    decisions_template = read_text_or_none(ROOT / "docs" / "decisions" / "TEMPLATE.md") or ""
    docs_agents = read_text_or_none(ROOT / "docs" / "AGENTS.md") or ""
    scripts_readme = read_text_or_none(ROOT / "scripts" / "README.md") or ""
    tests_readme = read_text_or_none(ROOT / "tests" / "README.md") or ""

    for snippet in (
        "Decision records explain why; current source surfaces define what.",
        "ABYSS-STACK-D-####",
        "indexes/",
        "TEMPLATE.md",
        "AGENTS.md",
        "validate_decision_records.py",
    ):
        if snippet not in decisions_readme:
            errors.append(f"docs/decisions/README.md must route `{snippet}`")

    for snippet in (
        "Decision Review Gate",
        "ABYSS-STACK-D-####",
        "docs/decisions/indexes/",
        "python scripts/generate_decision_indexes.py --check",
        "Decision records must follow [TEMPLATE](TEMPLATE.md)",
        "python scripts/validate_decision_records.py",
    ):
        if snippet not in decisions_agents:
            errors.append(f"docs/decisions/AGENTS.md must define `{snippet}`")

    for snippet in (
        "- Decision ID: ABYSS-STACK-D-NNNN",
        "- Status: proposed",
        "- Date: YYYY-MM-DD",
        "## Index Metadata",
        "## Options considered",
        "## Source surfaces",
        "## Follow-up route",
    ):
        if snippet not in decisions_template:
            errors.append(f"docs/decisions/TEMPLATE.md must include `{snippet}`")

    if "python scripts/validate_decision_records.py" not in docs_agents:
        errors.append("docs/AGENTS.md must include the decision-record validator")
    if "python scripts/generate_decision_indexes.py --check" not in docs_agents:
        errors.append("docs/AGENTS.md must include the decision-index generator check")
    if "validate_decision_records.py" not in scripts_readme:
        errors.append("scripts/README.md must route validate_decision_records.py")
    if "generate_decision_indexes.py" not in scripts_readme:
        errors.append("scripts/README.md must route generate_decision_indexes.py")
    if "test_decision_records.py" not in tests_readme:
        errors.append("tests/README.md must route test_decision_records.py")


def validate_sync_managed_items(errors: list[str]) -> None:
    sync_script = read_text_or_none(
        ROOT / "mechanics" / "config-projection" / "parts" / "sync" / "aoa_sync_configs.sh"
    ) or ""
    sync_readme = read_text_or_none(
        ROOT / "mechanics" / "config-projection" / "parts" / "sync" / "README.md"
    ) or ""

    for item in SYNC_MANAGED_ITEMS:
        if item not in sync_script:
            errors.append(
                "mechanics/config-projection/parts/sync/aoa_sync_configs.sh "
                f"must sync `{item}`"
            )

    for item in ("AGENTS.md", "DESIGN.md", "DESIGN.AGENTS.md"):
        if item not in sync_readme:
            errors.append(
                "mechanics/config-projection/parts/sync/README.md "
                f"must mention `{item}`"
            )


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

    bridge = compatibility_bridge_config(errors)
    runtime_templates = bridge.get("runtime_evidence_templates", {})
    if not isinstance(runtime_templates, dict) or not runtime_templates:
        errors.append("upstream compatibility bridge must list runtime_evidence_templates")
    else:
        for route in ("memo-recall-rerun", "memo-contradiction-gap", "memo-contradiction-rerun"):
            entry = runtime_templates.get(route)
            if not isinstance(entry, dict):
                errors.append(f"upstream compatibility bridge must list runtime template {route}")
                continue
            for key in ("canonical_selection_id", "local_source_ref", "upstream_source_ref", "upstream_selection_id"):
                if not isinstance(entry.get(key), str) or not entry.get(key):
                    errors.append(f"upstream compatibility bridge runtime template {route} must include {key}")
    playbook_bridge = bridge.get("playbook_automation_plans")
    if not isinstance(playbook_bridge, dict) or not playbook_bridge.get("upstream_rel_path"):
        errors.append("upstream compatibility bridge must list playbook automation upstream_rel_path")


def validate_reference_platform(errors: list[str]) -> None:
    reference_platform = (
        ROOT
        / "mechanics"
        / "machine-fit"
        / "parts"
        / "reference-platform"
        / "docs"
        / "REFERENCE_PLATFORM.md"
    ).read_text(encoding="utf-8")
    if "aoa-host-facts" not in reference_platform:
        errors.append("mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md must mention aoa-host-facts")
    if "mechanics/machine-fit/parts/machine-bridge/docs/MACHINE_BRIDGE.md" not in reference_platform:
        errors.append("mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md must point to mechanics/machine-fit/parts/machine-bridge/docs/MACHINE_BRIDGE.md")
    if "REFERENCE_PLATFORM_SPEC.md" not in reference_platform:
        errors.append(
            "mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md must point to REFERENCE_PLATFORM_SPEC.md"
        )

    doctor_doc = (
        ROOT
        / "mechanics"
        / "diagnostic-spine"
        / "parts"
        / "doctor-readiness"
        / "docs"
        / "DOCTOR.md"
    ).read_text(encoding="utf-8")
    if "aoa-host-facts" not in doctor_doc:
        errors.append("mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md must mention aoa-host-facts")
    if "aoa-machine-bridge" not in doctor_doc:
        errors.append("mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md must mention aoa-machine-bridge")

    first_run_doc = (ROOT / "docs" / "install" / "FIRST_RUN.md").read_text(encoding="utf-8")
    if "reference-host.public.json" not in first_run_doc:
        errors.append(
            "docs/install/FIRST_RUN.md must mention reference-host.public.json capture"
        )

    spec_doc = (
        ROOT
        / "mechanics"
        / "machine-fit"
        / "parts"
        / "reference-platform"
        / "docs"
        / "REFERENCE_PLATFORM_SPEC.md"
    ).read_text(encoding="utf-8")
    if "latest.private.json" not in spec_doc:
        errors.append(
            "mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md must define the local private capture path"
        )

    schema = json.loads(
        (
            ROOT
            / "mechanics"
            / "machine-fit"
            / "parts"
            / "host-facts"
            / "schemas"
            / "schema.v1.json"
        ).read_text(encoding="utf-8")
    )
    if schema.get("title") != "AoA Host Facts":
        errors.append("schema.v1.json must describe AoA Host Facts")

    example = json.loads(
        (
            ROOT
            / "mechanics"
            / "machine-fit"
            / "parts"
            / "host-facts"
            / "examples"
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

    machine_fit_example = json.loads(
        (
            ROOT
            / "mechanics"
            / "machine-fit"
            / "parts"
            / "fit-record"
            / "examples"
            / "machine-fit.public.json.example"
        ).read_text(encoding="utf-8")
    )
    preferred_profiles = (
        machine_fit_example.get("runtime_recommendation", {}).get("preferred_profile_set")
        if isinstance(machine_fit_example.get("runtime_recommendation"), dict)
        else None
    )
    if preferred_profiles != ["substrate", "intel-worker", "tools", "observability"]:
        errors.append(
            "machine-fit public example must use the composition-first intel-full profile set"
        )


def validate_machine_bridge(errors: list[str]) -> None:
    machine_bridge_doc_path = ROOT / "mechanics" / "machine-fit" / "parts" / "machine-bridge" / "docs" / "MACHINE_BRIDGE.md"
    machine_bridge_schema_path = ROOT / "mechanics" / "machine-fit" / "parts" / "machine-bridge" / "schemas" / "schema.v1.json"
    machine_bridge_example_path = (
        ROOT
        / "mechanics"
        / "machine-fit"
        / "parts"
        / "machine-bridge"
        / "examples"
        / "machine-bridge.public.json.example"
    )
    bridge_doc = machine_bridge_doc_path.read_text(encoding="utf-8")
    for fragment in (
        "scripts/aoa-machine-bridge --write-latest",
        "abyss-machine stack-bridge export --json",
        "Logs/machine-bridge/",
        "read-only",
    ):
        if fragment not in bridge_doc:
            errors.append(f"{machine_bridge_doc_path.relative_to(ROOT)} must mention {fragment}")

    storage_doc = (ROOT / "docs" / "runtime" / "STORAGE_LAYOUT.md").read_text(encoding="utf-8")
    if "Logs/machine-bridge/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Logs/machine-bridge/")

    paths_doc = (ROOT / "docs" / "runtime" / "PATHS.md").read_text(encoding="utf-8")
    if "Logs/machine-bridge" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention Logs/machine-bridge")

    script_doc = (ROOT / "scripts" / "AGENTS.md").read_text(encoding="utf-8")
    if "aoa-machine-bridge" not in script_doc:
        errors.append("scripts/AGENTS.md must mention aoa-machine-bridge")

    mechanic_parts = (ROOT / "mechanics" / "machine-fit" / "PARTS.md").read_text(encoding="utf-8")
    if "Machine bridge" not in mechanic_parts or "parts/machine-bridge/" not in mechanic_parts:
        errors.append("mechanics/machine-fit/PARTS.md must route Machine bridge surfaces")

    schema = json.loads(machine_bridge_schema_path.read_text(encoding="utf-8"))
    if schema.get("title") != "AoA Machine Bridge Record":
        errors.append(f"{machine_bridge_schema_path.relative_to(ROOT)} must describe AoA Machine Bridge Record")

    example = json.loads(machine_bridge_example_path.read_text(encoding="utf-8"))
    if example.get("artifact_kind") != "aoa.machine-bridge":
        errors.append("machine-bridge public example must use artifact_kind aoa.machine-bridge")
    if example.get("capture_mode") != "public":
        errors.append("machine-bridge public example must use capture_mode public")
    if example.get("captured_by") != "scripts/aoa-machine-bridge":
        errors.append("machine-bridge public example must use captured_by scripts/aoa-machine-bridge")
    contract = example.get("contract") if isinstance(example.get("contract"), dict) else {}
    if contract.get("stack_side_mutates_machine") is not False:
        errors.append("machine-bridge public example must keep stack_side_mutates_machine false")


def validate_machine_integration_freshness_gates(errors: list[str]) -> None:
    doctor_script = (
        ROOT
        / "mechanics"
        / "diagnostic-spine"
        / "parts"
        / "doctor-readiness"
        / "aoa_doctor.sh"
    ).read_text(encoding="utf-8")
    doctor_doc = (
        ROOT
        / "mechanics"
        / "diagnostic-spine"
        / "parts"
        / "doctor-readiness"
        / "docs"
        / "DOCTOR.md"
    ).read_text(encoding="utf-8")
    autonomy_status = (
        ROOT
        / "mechanics"
        / "governed-execution"
        / "parts"
        / "autonomy-status"
        / "aoa_status_autonomy.py"
    ).read_text(encoding="utf-8")
    diagnose_wrapper = (
        ROOT
        / "mechanics"
        / "diagnostic-spine"
        / "parts"
        / "diagnose-wrapper"
        / "aoa_diagnose.py"
    ).read_text(encoding="utf-8")

    for snippet in (
        "AOA_MACHINE_FIT_MAX_AGE_HOURS",
        "AOA_MACHINE_BRIDGE_MAX_AGE_HOURS",
        "machine-fit kernel mismatch",
        "machine-bridge host bridge version mismatch",
    ):
        if snippet not in doctor_script:
            errors.append(f"aoa-doctor must preserve machine evidence freshness gate `{snippet}`")
    for snippet in (
        "AOA_MACHINE_FIT_MAX_AGE_HOURS",
        "AOA_MACHINE_BRIDGE_MAX_AGE_HOURS",
        "old bridge file",
        "captured for an older host",
    ):
        if snippet not in doctor_doc:
            errors.append(f"DOCTOR.md must document machine evidence freshness gate `{snippet}`")
    current_marker = '"docs" / "install" / "DEPLOYMENT.md"'
    old_marker = '"docs" / "DEPLOYMENT.md"'
    if current_marker not in autonomy_status:
        errors.append("aoa-status autonomy source-root detection must use docs/install/DEPLOYMENT.md")
    if current_marker not in diagnose_wrapper:
        errors.append("aoa-diagnose source-root detection must use docs/install/DEPLOYMENT.md")
    if old_marker in autonomy_status or old_marker in diagnose_wrapper:
        errors.append("active source-root detection must not use stale docs/DEPLOYMENT.md marker")


def validate_platform_adaptations(errors: list[str]) -> None:
    boundaries_doc = (ROOT / "BOUNDARIES.md").read_text(encoding="utf-8")
    if "platform-adaptation" not in boundaries_doc:
        errors.append("BOUNDARIES.md must mention platform-adaptation records")

    runbook_doc = (ROOT / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-platform-adaptation" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-platform-adaptation")

    windows_perf_doc = (
        ROOT
        / "mechanics"
        / "machine-fit"
        / "parts"
        / "windows-bridge"
        / "docs"
        / "WINDOWS_PERFORMANCE.md"
    ).read_text(encoding="utf-8")
    if "aoa-platform-adaptation" not in windows_perf_doc:
        errors.append("mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_PERFORMANCE.md must mention aoa-platform-adaptation")

    storage_doc = (ROOT / "docs" / "runtime" / "STORAGE_LAYOUT.md").read_text(encoding="utf-8")
    if "Logs/platform-adaptations/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Logs/platform-adaptations/")

    policy_doc = (
        ROOT
        / "mechanics"
        / "machine-fit"
        / "parts"
        / "platform-adaptations"
        / "docs"
        / "PLATFORM_ADAPTATION_POLICY.md"
    ).read_text(encoding="utf-8")
    if "aoa-host-facts" not in policy_doc:
        errors.append("mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md must mention aoa-host-facts")
    if "runtime benchmarks" not in policy_doc and "runtime benchmark" not in policy_doc:
        errors.append("mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md must mention runtime benchmarks")

    schema = json.loads(
        (
            ROOT
            / "mechanics"
            / "machine-fit"
            / "parts"
            / "platform-adaptations"
            / "schemas"
            / "schema.v1.json"
        ).read_text(encoding="utf-8")
    )
    if schema.get("title") != "AoA Platform Adaptation Record":
        errors.append("machine-fit platform-adaptations schema.v1.json must describe AoA Platform Adaptation Record")

    example = json.loads(
        (
            ROOT
            / "mechanics"
            / "machine-fit"
            / "parts"
            / "platform-adaptations"
            / "examples"
            / "platform-adaptation.public.json.example"
        ).read_text(encoding="utf-8")
    )
    if example.get("artifact_kind") != "aoa.platform-adaptation":
        errors.append("platform-adaptation.public.json.example must use artifact_kind aoa.platform-adaptation")
    if example.get("capture_mode") != "public":
        errors.append("platform-adaptation.public.json.example must use capture_mode public")
    if example.get("captured_by") != "scripts/aoa-platform-adaptation":
        errors.append("platform-adaptation.public.json.example must use captured_by scripts/aoa-platform-adaptation")


def validate_branch_policy(errors: list[str]) -> None:
    contributing_doc = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    if "docs/governance/BRANCH_POLICY.md" not in contributing_doc:
        errors.append("CONTRIBUTING.md must point to docs/governance/BRANCH_POLICY.md")

    policy_doc = (ROOT / "docs" / "governance" / "BRANCH_POLICY.md").read_text(encoding="utf-8")
    required_snippets = [
        "`main` is the only long-lived branch",
        "Delete the topic branch locally and on `origin`.",
        "If a branch was effectively landed by squash, cherry-pick, or a rewritten equivalent, do not merge it again.",
        "/srv/AbyssOS/abyss-stack",
        "~/src/abyss-stack",
        "AOA_SOURCE_ROOT",
    ]
    for snippet in required_snippets:
        if snippet not in policy_doc:
            errors.append(f"docs/governance/BRANCH_POLICY.md must mention: {snippet}")


def validate_return_runtime_contract(errors: list[str]) -> None:
    templates_readme = (ROOT / "config-templates" / "README.md").read_text(encoding="utf-8")
    if "Configs/agent-api/" not in templates_readme:
        errors.append("config-templates/README.md must mention Configs/agent-api/")
    if "governed-canary-catalog.json" not in templates_readme:
        errors.append("config-templates/README.md must mention governed-canary-catalog.json")

    deployment_doc = (ROOT / "docs" / "install" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    if "Configs/agent-api/return-policy.yaml" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention Configs/agent-api/return-policy.yaml")

    first_run_doc = (ROOT / "docs" / "install" / "FIRST_RUN.md").read_text(encoding="utf-8")
    if "Configs/agent-api/return-policy.yaml" not in first_run_doc:
        errors.append("docs/install/FIRST_RUN.md must mention Configs/agent-api/return-policy.yaml")

    render_truth_doc = (
        ROOT
        / "mechanics"
        / "config-projection"
        / "parts"
        / "rendering"
        / "docs"
        / "RENDER_TRUTH.md"
    ).read_text(encoding="utf-8")
    if "return-policy" not in render_truth_doc:
        errors.append("mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md should mention return-policy mounts when the wrapper is enabled")
    if "aoa-status --autonomy" not in render_truth_doc:
        errors.append("mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md must mention aoa-status --autonomy")
    if "/surface-status" not in render_truth_doc:
        errors.append("mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md must mention /surface-status")

    policy_schema = json.loads((ROOT / RUNTIME_RETURN_POLICY_SCHEMA_PATH).read_text(encoding="utf-8"))
    if policy_schema.get("title") != "abyss-stack runtime return policy":
        errors.append("runtime-return-policy.schema.json must describe abyss-stack runtime return policy")
    policy_surface_type = policy_schema.get("properties", {}).get("surface_type", {})
    if policy_surface_type.get("const") != "runtime_return_policy":
        errors.append("runtime-return-policy.schema.json must pin surface_type.const to runtime_return_policy")

    event_schema = json.loads((ROOT / RUNTIME_RETURN_EVENT_SCHEMA_PATH).read_text(encoding="utf-8"))
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

    cache_doc = read_required_text(
        Path("mechanics") / "runtime-lifecycle" / "parts" / "status-readouts" / "docs" / "GATEWAY_CACHE_POLICY.md"
    )
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
        "This surface documents the contract only. It does not activate live cache behavior.",
        "`runtime_gateway_cache_status_v1`",
    ):
        if snippet not in cache_doc:
            errors.append(f"mechanics/runtime-lifecycle/parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md must mention `{snippet}`")

    usage_doc = read_required_text(
        Path("mechanics") / "runtime-lifecycle" / "parts" / "status-readouts" / "docs" / "USAGE_BUDGET_POLICY.md"
    )
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
        "This surface documents status readouts only.",
        "`runtime_usage_snapshot_v1`",
    ):
        if snippet not in usage_doc:
            errors.append(f"mechanics/runtime-lifecycle/parts/status-readouts/docs/USAGE_BUDGET_POLICY.md must mention `{snippet}`")

    doctor_split_doc = read_required_text(
        Path("mechanics") / "diagnostic-spine" / "parts" / "doctor-readiness" / "docs" / "LOCAL_OPS_DOCTOR_SPLIT.md"
    )
    for snippet in (
        "`aoa-doctor` remains readiness-only.",
        "gateway reachability",
        "log presence",
        "basic config health",
        "local floor availability",
        "It does not become a usage monitor.",
        "bounded local ops status surface",
        "This contract does not add new `aoa-doctor` exit semantics.",
    ):
        if snippet not in doctor_split_doc:
            errors.append(f"mechanics/diagnostic-spine/parts/doctor-readiness/docs/LOCAL_OPS_DOCTOR_SPLIT.md must mention `{snippet}`")

    service_catalog_doc = read_required_text(Path("docs") / "runtime" / "SERVICE_CATALOG.md")
    for snippet in (
        "mechanics/runtime-lifecycle/parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md",
        "mechanics/runtime-lifecycle/parts/status-readouts/docs/USAGE_BUDGET_POLICY.md",
        "mechanics/diagnostic-spine/parts/doctor-readiness/docs/LOCAL_OPS_DOCTOR_SPLIT.md",
        "does not add new HTTP endpoints in this contract surface",
        "bounded runtime artifact",
    ):
        if snippet not in service_catalog_doc:
            errors.append(f"docs/runtime/SERVICE_CATALOG.md must mention `{snippet}`")

    runbook_doc = read_required_text(Path("docs") / "operations" / "RUNBOOK.md")
    for snippet in (
        "runtime_gateway_cache_status",
        "runtime_usage_snapshot",
        "Logs/runtime-gateway/cache-status/latest/",
        "Logs/runtime-usage/latest/",
        "absence is not a failure",
    ):
        if snippet not in runbook_doc:
            errors.append(f"docs/operations/RUNBOOK.md must mention `{snippet}`")

    doctor_doc = read_required_text(
        Path("mechanics") / "diagnostic-spine" / "parts" / "doctor-readiness" / "docs" / "DOCTOR.md"
    )
    for snippet in (
        "mechanics/diagnostic-spine/parts/doctor-readiness/docs/LOCAL_OPS_DOCTOR_SPLIT.md",
        "readiness-only",
        "usage monitor",
    ):
        if snippet not in doctor_doc:
            errors.append(f"mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md must mention `{snippet}`")

    cache_schema = read_required_json(RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH)
    if cache_schema and not isinstance(cache_schema, dict):
        errors.append(f"{RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH.as_posix()} must contain a JSON object")
        cache_schema = None
    if cache_schema and cache_schema.get("title") != "abyss-stack runtime gateway cache status":
        errors.append(
            f"{RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH.as_posix()} must describe abyss-stack runtime gateway cache status"
        )
    if cache_schema:
        cache_required = cache_schema.get("required")
        if not isinstance(cache_required, list):
            errors.append(f"{RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH.as_posix()} must declare a required field list")
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
                        f"{RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH.as_posix()} must require `{field}`"
                    )
        cache_properties = cache_schema.get("properties")
        cache_surface_type = (
            cache_properties.get("surface_type", {})
            if isinstance(cache_properties, dict)
            else {}
        )
        if not isinstance(cache_surface_type, dict) or cache_surface_type.get("const") != "runtime_gateway_cache_status":
            errors.append(
                f"{RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH.as_posix()} must pin surface_type.const to runtime_gateway_cache_status"
            )

    usage_schema = read_required_json(RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH)
    if usage_schema and usage_schema.get("title") != "abyss-stack runtime usage snapshot":
        errors.append(
            f"{RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH.as_posix()} must describe abyss-stack runtime usage snapshot"
        )
    if usage_schema:
        usage_required = usage_schema.get("required")
        if not isinstance(usage_required, list):
            errors.append(f"{RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH.as_posix()} must declare a required field list")
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
                    errors.append(f"{RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH.as_posix()} must require `{field}`")
        usage_properties = usage_schema.get("properties")
        usage_surface_type = (
            usage_properties.get("surface_type", {})
            if isinstance(usage_properties, dict)
            else {}
        )
        if not isinstance(usage_surface_type, dict) or usage_surface_type.get("const") != "runtime_usage_snapshot":
            errors.append(
                f"{RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH.as_posix()} must pin surface_type.const to runtime_usage_snapshot"
            )

    cache_example = read_required_json(RUNTIME_GATEWAY_CACHE_STATUS_EXAMPLE_PATH)
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

    usage_example_path = RUNTIME_USAGE_SNAPSHOT_EXAMPLE_PATH
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
        "mechanics/diagnostic-spine/README.md",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json",
        "scripts/aoa-diagnose",
    ):
        if snippet not in readme:
            errors.append(f"README.md must mention `{snippet}`")

    spine_doc = read_required_text(DIAGNOSTIC_SPINE_PATH)
    for snippet in (
        "The goal is not a louder doctor.",
        "The diagnostic spine is a read model with memory.",
        "`mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json`",
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

    runbook_doc = read_required_text(Path("docs") / "operations" / "RUNBOOK.md")
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
            errors.append(f"docs/operations/RUNBOOK.md must mention `{snippet}`")

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
                "mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json must use schema_version abyss_stack_diagnostic_surface_catalog_v1"
            )
        if diagnostic_surface_catalog.get("owner_repo") != "abyss-stack":
            errors.append("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json must set owner_repo to abyss-stack")
        if diagnostic_surface_catalog.get("surface_kind") != "runtime_surface":
            errors.append("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json must stay runtime_surface")
        if diagnostic_surface_catalog.get("authority_ref") != "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md":
            errors.append("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json must point authority_ref to mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md")

        surfaces = diagnostic_surface_catalog.get("surfaces")
        if not isinstance(surfaces, list) or len(surfaces) != len(DIAGNOSTIC_SURFACE_CATALOG_EXPECTED_NAMES):
            errors.append("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json must publish exactly five diagnostic surfaces")
        else:
            surface_names = []
            for index, entry in enumerate(surfaces):
                if not isinstance(entry, dict):
                    errors.append(f"mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json surface {index} must be an object")
                    continue
                for field in ("name", "schema_ref", "example_ref", "primary_question"):
                    value = entry.get(field)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(
                            f"mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json surface {index} must include non-empty {field}"
                        )
                name = entry.get("name")
                schema_ref = entry.get("schema_ref")
                example_ref = entry.get("example_ref")
                if isinstance(name, str):
                    surface_names.append(name)
                if isinstance(schema_ref, str) and not (ROOT / schema_ref).exists():
                    errors.append(f"mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json schema_ref is missing: {schema_ref}")
                if isinstance(example_ref, str) and not (ROOT / example_ref).exists():
                    errors.append(f"mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json example_ref is missing: {example_ref}")
            if tuple(surface_names) != DIAGNOSTIC_SURFACE_CATALOG_EXPECTED_NAMES:
                errors.append("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json surface order must stay aligned with the diagnostic spine")

        validation_refs = diagnostic_surface_catalog.get("validation_refs")
        expected_validation_refs = [
            "scripts/validate_stack.py",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_validate_stack_diagnostic_spine.py",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_diagnostic_spine_contracts.py",
        ]
        if validation_refs != expected_validation_refs:
            errors.append("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json validation_refs must stay aligned with the repo-local diagnostic checks")
        elif isinstance(validation_refs, list):
            for ref in validation_refs:
                if not isinstance(ref, str) or not (ROOT / ref).exists():
                    errors.append(f"mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json validation_ref is missing: {ref}")

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


def validate_service_selection_policy(errors: list[str]) -> None:
    policy_path = ROOT / SERVICE_SELECTION_POLICY_PATH
    if not policy_path.is_file():
        errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} is required")
        return

    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} must be valid JSON: {exc}")
        return

    if not isinstance(policy, dict):
        errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} must contain a JSON object")
        return

    if policy.get("schema") != "abyss_stack_service_selection_policy_v1":
        errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} must use schema abyss_stack_service_selection_policy_v1")

    runtime_shape = policy.get("current_runtime_shape")
    if not isinstance(runtime_shape, dict):
        errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} must include current_runtime_shape")
    else:
        if runtime_shape.get("preset") != "intel-full":
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} current runtime preset must remain intel-full")
        profiles = runtime_shape.get("profiles")
        if not isinstance(profiles, list) or not {"federation", "reranking", "rag"}.issubset(set(profiles)):
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} current runtime profiles must include federation, reranking, and rag")
        overlays = runtime_shape.get("overlays")
        if not isinstance(overlays, list) or not overlays:
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} current runtime overlays must be a non-empty list")
        elif "compose/tuning/storage.intel-285h.resource-guard.yml" not in overlays:
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} current runtime overlays must include the storage resource guard")
        elif "compose/tuning/rag.thin-host.yml" not in overlays:
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} current runtime overlays must include the rag thin-host guard")
        if isinstance(overlays, list):
            for overlay in overlays:
                if not isinstance(overlay, str) or not overlay:
                    errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} overlays must be non-empty strings")
                    continue
                if not (ROOT / overlay).is_file():
                    errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} overlay path is missing: {overlay}")

    services = policy.get("services")
    if not isinstance(services, list) or not services:
        errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} must include a non-empty services list")
        return

    seen_names: set[str] = set()
    selected_now: set[str] = set()
    for index, entry in enumerate(services):
        if not isinstance(entry, dict):
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} service entry {index} must be an object")
            continue

        name = entry.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} service entry {index} must include name")
            continue
        if name in seen_names:
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} has duplicate service: {name}")
        seen_names.add(name)

        for field in ("module", "owner_profile", "posture", "tier", "decision"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} service {name} must include non-empty {field}")

        posture = entry.get("posture")
        if isinstance(posture, str) and posture not in SERVICE_SELECTION_POLICY_ALLOWED_POSTURES:
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} service {name} has unsupported posture: {posture}")
        if posture == "selected_now":
            selected_now.add(name)

        module = entry.get("module")
        if isinstance(module, str) and module and not (ROOT / module).is_file():
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} service {name} module is missing: {module}")

        resource_guard = entry.get("resource_guard")
        if resource_guard is None:
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} service {name} must include resource_guard, even when blank")
        elif not isinstance(resource_guard, str):
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} service {name} resource_guard must be a string")
        elif resource_guard and not (ROOT / resource_guard).is_file():
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} service {name} resource guard is missing: {resource_guard}")
        elif posture == "selected_now" and not resource_guard:
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} selected service {name} must name a resource guard")

    missing_services = sorted(SERVICE_SELECTION_POLICY_REQUIRED_SERVICES - seen_names)
    if missing_services:
        errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} missing required services: {', '.join(missing_services)}")

    for unexpected_selected in ("n8n", "n8n-task-runners", "ollama", "litellm", "babelvox-tts"):
        if unexpected_selected in selected_now:
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} must not mark {unexpected_selected} as selected_now")

    for expected_selected in ("postgres", "redis", "qdrant", "neo4j", "llama-cpp", "ovms", "langchain-api", "route-api", "rerank-api", "rag-api"):
        if expected_selected not in selected_now:
            errors.append(f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} must mark {expected_selected} as selected_now")

    runtime_shape_services: set[str] = set()
    if isinstance(runtime_shape, dict):
        profile_names: list[str] = []
        preset_name = runtime_shape.get("preset")
        if isinstance(preset_name, str) and preset_name:
            preset_path = PRESET_DIR / f"{preset_name}.txt"
            if preset_path.is_file():
                profile_names.extend(load_names(preset_path))
        profiles = runtime_shape.get("profiles")
        if isinstance(profiles, list):
            profile_names.extend(
                profile for profile in profiles if isinstance(profile, str) and profile
            )

        seen_profiles: set[str] = set()
        module_names: list[str] = []
        for profile_name in profile_names:
            if profile_name in seen_profiles:
                continue
            seen_profiles.add(profile_name)
            profile_path = PROFILE_DIR / f"{profile_name}.txt"
            if not profile_path.is_file():
                continue
            module_names.extend(load_names(profile_path))

        seen_modules: set[str] = set()
        for module_name in module_names:
            if module_name in seen_modules:
                continue
            seen_modules.add(module_name)
            module_path = MODULE_DIR / module_name
            if module_path.is_file():
                runtime_shape_services.update(compose_service_names(module_path))

    if runtime_shape_services:
        missing_from_runtime_shape = sorted(selected_now - runtime_shape_services)
        if missing_from_runtime_shape:
            errors.append(
                f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} marks services selected_now that are not in the current runtime shape: {', '.join(missing_from_runtime_shape)}"
            )
        missing_from_policy_selection = sorted(runtime_shape_services - selected_now)
        if missing_from_policy_selection:
            errors.append(
                f"{SERVICE_SELECTION_POLICY_PATH.as_posix()} current runtime shape services must be marked selected_now: {', '.join(missing_from_policy_selection)}"
            )

    selection_doc = (ROOT / "docs" / "runtime" / "SERVICE_SELECTION.md").read_text(encoding="utf-8")
    runtime_readme = (ROOT / "docs" / "runtime" / "README.md").read_text(encoding="utf-8")
    for path, text in (
        ("docs/runtime/SERVICE_SELECTION.md", selection_doc),
        ("docs/runtime/README.md", runtime_readme),
    ):
        if "service-selection-policy.v1.json" not in text:
            errors.append(f"{path} must mention service-selection-policy.v1.json")


def validate_service_screenshot_inventory(errors: list[str]) -> None:
    inventory_path = ROOT / SERVICE_SCREENSHOT_INVENTORY_PATH
    if not inventory_path.is_file():
        errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} is required")
        return

    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must be valid JSON: {exc}")
        return

    if not isinstance(inventory, dict):
        errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must contain a JSON object")
        return

    if inventory.get("schema") != "abyss_stack_runtime_service_inventory_v1":
        errors.append(
            f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must use schema abyss_stack_runtime_service_inventory_v1"
        )
    if inventory.get("policy_companion") != SERVICE_SELECTION_POLICY_PATH.as_posix():
        errors.append(
            f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must point policy_companion at {SERVICE_SELECTION_POLICY_PATH.as_posix()}"
        )

    source = inventory.get("source_screenshot")
    if not isinstance(source, dict):
        errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must include source_screenshot")
    else:
        screenshot_path = source.get("absolute_path")
        if not isinstance(screenshot_path, str) or "2026-05-14 21-46-49.png" not in screenshot_path:
            errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must preserve the source screenshot path")
        if source.get("size_bytes") != 64281:
            errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must preserve the source screenshot size")
        if source.get("extraction_method") != "manual_visual_review":
            errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must declare manual_visual_review extraction")

    services = inventory.get("screenshotted_services")
    if not isinstance(services, list) or not services:
        errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must include screenshotted_services")
        return
    if not all(isinstance(service, str) and service for service in services):
        errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} screenshotted_services must be non-empty strings")
        return
    service_set = set(services)
    if len(service_set) != len(services):
        errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must not duplicate screenshotted services")
    if service_set != SERVICE_SCREENSHOT_INVENTORY_REQUIRED_SERVICES:
        missing = sorted(SERVICE_SCREENSHOT_INVENTORY_REQUIRED_SERVICES - service_set)
        extra = sorted(service_set - SERVICE_SCREENSHOT_INVENTORY_REQUIRED_SERVICES)
        if missing:
            errors.append(
                f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} missing screenshot services: {', '.join(missing)}"
            )
        if extra:
            errors.append(
                f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} has unexpected screenshot services: {', '.join(extra)}"
            )

    grouped_services: list[str] = []
    groups = inventory.get("screenshotted_groups")
    if not isinstance(groups, list) or not groups:
        errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must include screenshotted_groups")
    else:
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} group {index} must be an object")
                continue
            if not isinstance(group.get("group"), str) or not group.get("group"):
                errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} group {index} must include group")
            group_services = group.get("services")
            if not isinstance(group_services, list) or not group_services:
                errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} group {index} must include services")
                continue
            for service in group_services:
                if isinstance(service, str) and service:
                    grouped_services.append(service)
                else:
                    errors.append(
                        f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} group {index} contains an invalid service"
                    )
        if set(grouped_services) != service_set:
            errors.append(
                f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} screenshotted_groups must match screenshotted_services"
            )

    policy_path = ROOT / SERVICE_SELECTION_POLICY_PATH
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    policy_services = policy.get("services")
    if not isinstance(policy_services, list):
        return

    policy_service_names = {
        entry.get("name")
        for entry in policy_services
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    missing_from_policy = sorted(service_set - policy_service_names)
    if missing_from_policy:
        errors.append(
            f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} services must all be covered by {SERVICE_SELECTION_POLICY_PATH.as_posix()}: {', '.join(missing_from_policy)}"
        )

    addon_entries = inventory.get("current_selected_addons")
    addon_services: set[str] = set()
    if not isinstance(addon_entries, list):
        errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must include current_selected_addons")
    else:
        for index, addon in enumerate(addon_entries):
            if not isinstance(addon, dict) or not isinstance(addon.get("service"), str):
                errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} addon {index} must include service")
                continue
            addon_services.add(addon["service"])
        if addon_services != {"rerank-api", "rag-api"}:
            errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} current_selected_addons must contain rerank-api and rag-api")

    selected_now = {
        entry.get("name")
        for entry in policy_services
        if isinstance(entry, dict) and entry.get("posture") == "selected_now"
    }
    selected_not_in_screenshot = selected_now - service_set
    if selected_not_in_screenshot != addon_services:
        errors.append(
            f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} current_selected_addons must explain selected policy services absent from the screenshot"
        )

    known_not_in_screenshot = inventory.get("known_policy_services_not_in_screenshot")
    if not isinstance(known_not_in_screenshot, list) or not all(isinstance(item, str) for item in known_not_in_screenshot):
        errors.append(f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} must include known_policy_services_not_in_screenshot")
    else:
        expected_known = policy_service_names - service_set - addon_services
        if set(known_not_in_screenshot) != expected_known:
            errors.append(
                f"{SERVICE_SCREENSHOT_INVENTORY_PATH.as_posix()} known_policy_services_not_in_screenshot must match policy services absent from the screenshot"
            )

    selection_doc = (ROOT / "docs" / "runtime" / "SERVICE_SELECTION.md").read_text(encoding="utf-8")
    runtime_readme = (ROOT / "docs" / "runtime" / "README.md").read_text(encoding="utf-8")
    for path, text in (
        ("docs/runtime/SERVICE_SELECTION.md", selection_doc),
        ("docs/runtime/README.md", runtime_readme),
    ):
        if SERVICE_SCREENSHOT_INVENTORY_PATH.name not in text:
            errors.append(f"{path} must mention {SERVICE_SCREENSHOT_INVENTORY_PATH.name}")


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

    storage_layout_doc = (ROOT / "docs" / "runtime" / "STORAGE_LAYOUT.md").read_text(encoding="utf-8")
    if "Knowledge/federation" not in storage_layout_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Knowledge/federation")
    if "source-managed build context" not in storage_layout_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention the aoa-browser source-managed build context")
    if "Services/aoa-browser/ms-playwright/" not in storage_layout_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Services/aoa-browser/ms-playwright/")

    deployment_doc = (ROOT / "docs" / "install" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    if "aoa-sync-federation-surfaces --layer aoa-agents" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer aoa-agents")
    if "aoa-sync-federation-surfaces --layer aoa-memo" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer aoa-memo")
    if "aoa-sync-federation-surfaces --layer aoa-evals" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer aoa-evals")
    if "aoa-sync-federation-surfaces --layer aoa-playbooks" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer aoa-playbooks")
    if "aoa-sync-federation-surfaces --layer aoa-kag" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer aoa-kag")
    if "aoa-install-systemd --preset intel-full --profile federation --enable-now --restart-now" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must document the federation user-unit selection route")
    if "aoa-sync-federation-surfaces --layer tos-source" not in deployment_doc:
        errors.append("docs/install/DEPLOYMENT.md must mention aoa-sync-federation-surfaces --layer tos-source")

    paths_doc = (ROOT / "docs" / "runtime" / "PATHS.md").read_text(encoding="utf-8")
    if "AOA_AGENTS_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_AGENTS_ROOT")
    if "AOA_MEMO_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_MEMO_ROOT")
    if "AOA_EVALS_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_EVALS_ROOT")
    if "AOA_PLAYBOOKS_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_PLAYBOOKS_ROOT")
    if "AOA_KAG_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_KAG_ROOT")
    if "AOA_TOS_ROOT" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention AOA_TOS_ROOT")

    service_catalog_doc = (ROOT / "docs" / "runtime" / "SERVICE_CATALOG.md").read_text(encoding="utf-8")
    if "43-federation-router.yml" not in service_catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention 43-federation-router.yml")
    if "route-api" not in service_catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention route-api")
    if "POST /run/federated" not in service_catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention POST /run/federated")
    if "`abyss_default`" not in service_catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must explain the sidecar route-api network attachment")

    profiles_doc = (ROOT / "docs" / "profiles" / "PROFILES.md").read_text(encoding="utf-8")
    if "`federation`" not in profiles_doc:
        errors.append("docs/profiles/PROFILES.md must mention the federation profile")
    if "AOA_FEDERATED_RUN_ENABLED=true" not in profiles_doc:
        errors.append("docs/profiles/PROFILES.md must explain when AOA_FEDERATED_RUN_ENABLED=true is required")

    profile_recipes_doc = (ROOT / "docs" / "profiles" / "PROFILE_RECIPES.md").read_text(encoding="utf-8")
    if "route-api" not in profile_recipes_doc:
        errors.append("docs/profiles/PROFILE_RECIPES.md must mention route-api")
    if "aoa-federated-check" not in profile_recipes_doc:
        errors.append("docs/profiles/PROFILE_RECIPES.md must mention aoa-federated-check for the federated advisory seam")
    if "--playbook-id AOA-P-0008" not in profile_recipes_doc:
        errors.append("docs/profiles/PROFILE_RECIPES.md must show aoa-federated-check --playbook-id AOA-P-0008 for the first playbook advisory consumer path")
    if "--inspect-id AOA-K-0011" not in profile_recipes_doc:
        errors.append("docs/profiles/PROFILE_RECIPES.md must show aoa-federated-check --inspect-id AOA-K-0011 for the first retrieval-only consumer path")
    if "--memo-id AOA-M-0001" not in profile_recipes_doc:
        errors.append("docs/profiles/PROFILE_RECIPES.md must show aoa-federated-check --memo-id AOA-M-0001 for the first memo advisory consumer path")

    runbook_doc = (ROOT / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-federated-check" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-federated-check for the live federated advisory seam")
    if "--playbook-id AOA-P-0008" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must show aoa-federated-check --playbook-id AOA-P-0008 for the first playbook advisory consumer path")
    if "--inspect-id AOA-K-0011" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must show aoa-federated-check --inspect-id AOA-K-0011 for the first retrieval-only consumer path")
    if "--memo-id AOA-M-0001" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must show aoa-federated-check --memo-id AOA-M-0001 for the first memo advisory consumer path")


def validate_memo_runtime_seam(errors: list[str]) -> None:
    runbook_doc = (ROOT / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-export-memo-candidate" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-export-memo-candidate")

    seam_doc = (
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "memo-seam"
        / "docs"
        / "MEMO_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-memo",
        "/memo/",
        "aoa-export-memo-candidate",
        "Logs/memo-exports/",
    ):
        if snippet not in seam_doc:
            errors.append(f"mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md must mention {snippet}")

    schema = json.loads(
        (
            ROOT
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "schemas"
            / "runtime-memo-export-candidate.schema.json"
        ).read_text(encoding="utf-8")
    )
    if schema.get("title") != "abyss-stack runtime memo export candidate":
        errors.append("runtime-memo-export-candidate.schema.json must describe abyss-stack runtime memo export candidate")

    example = json.loads(
        (
            ROOT
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "examples"
            / "runtime_memo_export_candidate.checkpoint_export.example.json"
        ).read_text(encoding="utf-8")
    )
    if example.get("artifact_kind") != "aoa.runtime-memo-export-candidate":
        errors.append("runtime memo export example must use artifact_kind aoa.runtime-memo-export-candidate")
    if example.get("exported_by") != "scripts/aoa-export-memo-candidate":
        errors.append("runtime memo export example must use exported_by scripts/aoa-export-memo-candidate")


def validate_eval_runtime_seam(errors: list[str]) -> None:
    runbook_doc = (ROOT / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-export-runtime-evidence-selection" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-export-runtime-evidence-selection")
    if "aoa-export-artifact-hook-candidate" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-export-artifact-hook-candidate")
    if "aoa-run-memo-contradiction-integrity" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-run-memo-contradiction-integrity")
    if "aoa-a2a-return-closeout-dry-run" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-a2a-return-closeout-dry-run")

    seam_doc = (
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "eval-seam"
        / "docs"
        / "EVAL_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-evals",
        "/evals/",
        "aoa-export-runtime-evidence-selection",
        "aoa-export-artifact-hook-candidate",
        "aoa-a2a-return-closeout-dry-run",
        "aoa-run-memo-contradiction-integrity",
        "Logs/eval-exports/",
        "Logs/a2a-return-closeouts/",
    ):
        if snippet not in seam_doc:
            errors.append(f"mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md must mention {snippet}")

    compatibility_doc = (
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "docs"
        / "UPSTREAM_COMPATIBILITY.md"
    ).read_text(encoding="utf-8")
    compatibility_legacy_index = (
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "legacy"
        / "upstream-compatibility"
        / "INDEX.md"
    ).read_text(encoding="utf-8")
    bridge_config = compatibility_bridge_config(errors)
    bridge_strings = iter_compatibility_bridge_strings(bridge_config)
    for snippet in (
        "single active bridge",
        "legacy/upstream-compatibility/INDEX.md",
        "upstream-compatibility-bridge.json",
        "Clean local route",
    ):
        if snippet not in compatibility_doc:
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md "
                f"must keep the lightweight active bridge and mention {snippet}"
            )
    for bridge_value in bridge_strings:
        is_legacy_value = any(
            marker in bridge_value for marker in ("phase-alpha", "a2a_wave", "playbook_automation_seeds", "seed_staging")
        )
        if is_legacy_value and bridge_value in compatibility_doc:
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md "
                f"must route detailed legacy value {bridge_value} through legacy/upstream-compatibility/INDEX.md"
            )
        if is_legacy_value and bridge_value not in compatibility_legacy_index:
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/legacy/upstream-compatibility/INDEX.md "
                f"must mention {bridge_value}"
            )

    evidence_schema = json.loads(
        (
            ROOT
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "schemas"
            / "runtime-eval-evidence-selection-candidate.schema.json"
        ).read_text(encoding="utf-8")
    )
    if evidence_schema.get("title") != "abyss-stack runtime eval evidence selection candidate":
        errors.append(
            "runtime-eval-evidence-selection-candidate.schema.json must describe abyss-stack runtime eval evidence selection candidate"
        )

    evidence_example = json.loads(
        (
            ROOT
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "examples"
            / "runtime_eval_evidence_selection_candidate.workhorse-local.example.json"
        ).read_text(encoding="utf-8")
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
        (
            ROOT
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "schemas"
            / "runtime-artifact-hook-candidate.schema.json"
        ).read_text(encoding="utf-8")
    )
    if hook_schema.get("title") != "abyss-stack runtime artifact hook candidate":
        errors.append("runtime-artifact-hook-candidate.schema.json must describe abyss-stack runtime artifact hook candidate")

    hook_example = json.loads(
        (
            ROOT
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "examples"
            / "runtime_artifact_hook_candidate.self-agent-checkpoint-rollout.example.json"
        ).read_text(encoding="utf-8")
    )
    if hook_example.get("artifact_kind") != "aoa.runtime-artifact-hook-candidate":
        errors.append("runtime artifact hook example must use artifact_kind aoa.runtime-artifact-hook-candidate")
    if hook_example.get("exported_by") != "scripts/aoa-export-artifact-hook-candidate":
        errors.append("runtime artifact hook example must use exported_by scripts/aoa-export-artifact-hook-candidate")

    a2a_doc = (
        ROOT
        / "mechanics"
        / "runtime-repair"
        / "parts"
        / "a2a-return-dry-run"
        / "docs"
        / "A2A_RETURN_DRY_RUN.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-a2a-return-closeout-dry-run",
        "request_family",
        "upstream_request_kind",
        "UPSTREAM_COMPATIBILITY.md",
        "dry_run",
        "live_automation",
        "Logs/a2a-return-closeouts/",
    ):
        if snippet not in a2a_doc:
            errors.append(f"mechanics/runtime-repair/parts/a2a-return-dry-run/docs/A2A_RETURN_DRY_RUN.md must mention {snippet}")

    a2a_schema = json.loads(
        (
            ROOT
            / "mechanics"
            / "runtime-repair"
            / "parts"
            / "a2a-return-dry-run"
            / "schemas"
            / "runtime-a2a-return-closeout-dry-run.schema.json"
        ).read_text(encoding="utf-8")
    )
    if a2a_schema.get("title") != "abyss-stack runtime A2A return closeout dry-run":
        errors.append(
            "runtime-a2a-return-closeout-dry-run.schema.json must describe abyss-stack runtime A2A return closeout dry-run"
        )

    a2a_example = json.loads(
        (
            ROOT
            / "mechanics"
            / "runtime-repair"
            / "parts"
            / "a2a-return-dry-run"
            / "examples"
            / "runtime_a2a_return_closeout_dry_run.example.json"
        ).read_text(encoding="utf-8")
    )
    if a2a_example.get("artifact_kind") != "aoa.runtime-a2a-return-closeout-dry-run":
        errors.append(
            "runtime A2A return closeout dry-run example must use artifact_kind aoa.runtime-a2a-return-closeout-dry-run"
        )
    if a2a_example.get("exported_by") != "scripts/aoa-a2a-return-closeout-dry-run":
        errors.append(
            "runtime A2A return closeout dry-run example must use exported_by scripts/aoa-a2a-return-closeout-dry-run"
        )
    if a2a_example.get("dry_run") is not True:
        errors.append("runtime A2A return closeout dry-run example must set dry_run true")
    if a2a_example.get("live_automation") is not False:
        errors.append("runtime A2A return closeout dry-run example must set live_automation false")
    if a2a_example.get("request_family") != "a2a-return-closeout":
        errors.append("runtime A2A return closeout dry-run example must set request_family a2a-return-closeout")
    if a2a_example.get("request_kind") != "a2a-return-closeout-request":
        errors.append("runtime A2A return closeout dry-run example must set clean request_kind")
    if "UPSTREAM_COMPATIBILITY_BRIDGE.a2a_return_closeout.upstream_request_kind" not in str(
        a2a_example.get("upstream_request_kind", "")
    ):
        errors.append("runtime A2A return closeout dry-run example must route upstream_request_kind through the bridge")


def validate_playbook_runtime_seam(errors: list[str]) -> None:
    runbook_doc = (ROOT / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "playbooks/activation" not in runbook_doc and "/playbooks/" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention playbook advisory seam inspection")

    seam_doc = (
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "playbook-seam"
        / "docs"
        / "PLAYBOOK_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-playbooks",
        "/playbooks/",
        "PLAYBOOK.md",
        "advisory-only",
        "aoa-sync-federation-surfaces --layer aoa-playbooks",
    ):
        if snippet not in seam_doc:
            errors.append(f"mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md must mention {snippet}")


def validate_kag_runtime_seam(errors: list[str]) -> None:
    runbook_doc = (ROOT / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "/kag/" not in runbook_doc and "kag/registry" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention KAG advisory seam inspection")

    seam_doc = (
        ROOT
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "kag-seam"
        / "docs"
        / "KAG_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
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
            errors.append(f"mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md must mention {snippet}")


def validate_runtime_configs_mirror(errors: list[str]) -> None:
    required_runtime_paths = [
        ROOT / "README.md",
        ROOT / "compose" / "modules",
        ROOT / "compose" / "profiles",
        ROOT / "config-templates" / "Services" / "route-api" / "app" / "main.py",
        ROOT / "scripts" / "aoa-check-layout",
        ROOT / "docs" / "install" / "DEPLOYMENT.md",
    ]
    for path in required_runtime_paths:
        if not path.exists():
            errors.append(f"runtime Configs mirror is missing required path: {path.relative_to(ROOT)}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "Source checkout shape" not in readme:
        errors.append("runtime Configs mirror README must clarify that the repository tree is the source checkout shape")
    if "/srv/AbyssOS/abyss-stack/Configs" not in readme:
        errors.append("runtime Configs mirror README must mention /srv/AbyssOS/abyss-stack/Configs")

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
        default="/srv/AbyssOS/abyss-stack/Configs",
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
    validate_git_mirror_hygiene(errors)
    validate_no_host_local_source_checkout_paths(errors)
    validate_no_moved_mechanic_doc_refs(errors)
    validate_no_stale_active_sibling_roots(errors)
    validate_paths(errors)
    validate_mechanics_topology(errors)
    validate_scripts(errors)
    validate_required_files(errors)
    validate_root_residual_topology(errors)
    validate_agent_skill_projection_routes(errors)
    validate_local_trials_compatibility_bridge(errors)
    validate_inference_pilot_compatibility_gate_language(errors)
    validate_federation_upstream_compatibility(errors)
    validate_active_topology_language(errors)
    validate_root_design_surfaces(errors)
    validate_entry_route_contract(errors)
    validate_decision_record_surface(errors)
    validate_sync_managed_items(errors)
    validate_federation_required_files(errors)
    validate_questbook_surface(errors)
    validate_reference_platform(errors)
    validate_machine_bridge(errors)
    validate_machine_integration_freshness_gates(errors)
    validate_platform_adaptations(errors)
    validate_branch_policy(errors)
    validate_memo_runtime_seam(errors)
    validate_eval_runtime_seam(errors)
    validate_playbook_runtime_seam(errors)
    validate_kag_runtime_seam(errors)
    validate_return_runtime_contract(errors)
    validate_runtime_hygiene_contracts(errors)
    validate_diagnostic_spine_contracts(errors)
    validate_service_selection_policy(errors)
    validate_service_screenshot_inventory(errors)
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
