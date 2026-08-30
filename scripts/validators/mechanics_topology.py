from __future__ import annotations

from pathlib import Path
from typing import Callable


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
        "agent-os-adapter",
        "autonomy-status",
        "return-policy",
        "runtime-contracts",
        "candidate-exports",
        "local-worker-path",
        "external-codex-agent",
        "programmatic-tool-execution",
        "ephemeral-worker",
    ),
    "inference-pilots": (
        "llamacpp-pilot",
        "qwen-routes",
        "langgraph-pilot",
        "local-trials",
        "tos-foundation-lab",
        "promotion-loop",
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
    ("governed-execution", "external-codex-agent"): (
        "AGENTS.md",
        "CONTRACT.md",
        "DIRECTION.md",
        "PROVENANCE.md",
        "README.md",
        "SUSPENSION.md",
        "VALIDATION.md",
        "external_codex_agent.py",
        "bind_external_actor_launch.py",
        "external_codex_supervisor.py",
        "install_external_codex_runtime.py",
        "legacy-owner-admission-migrations.v1.json",
        "prepare_landing_study.py",
        "runtime-profile.v1.json",
        "schemas/external-actor-launch-manifest.schema.json",
        "schemas/external-codex-actor-delta.schema.json",
        "schemas/external-codex-actor-input-envelope.schema.json",
        "schemas/external-codex-actor-workspace-manifest.schema.json",
        "schemas/external-codex-event.schema.json",
        "schemas/external-codex-launch.schema.json",
        "schemas/external-codex-legacy-owner-migration-catalog.schema.json",
        "schemas/external-codex-owner-admission-generation.schema.json",
        "schemas/external-codex-parent-obligation.schema.json",
        "schemas/external-codex-parent-reentry.schema.json",
        "schemas/external-codex-parent-yield.schema.json",
        "schemas/external-codex-reentry-state.schema.json",
        "schemas/external-codex-report.schema.json",
        "schemas/external-codex-result.schema.json",
        "schemas/external-codex-resume.schema.json",
        "schemas/external-codex-review-preparation.schema.json",
        "schemas/external-codex-review-seed-envelope.schema.json",
        "schemas/external-codex-review-state-seal.schema.json",
        "schemas/external-codex-runtime-profile.schema.json",
        "schemas/external-codex-state.schema.json",
        "schemas/external-codex-study-preparation.schema.json",
        "schemas/external-codex-task.schema.json",
        "schemas/external-codex-workspace-manifest.schema.json",
        "external_codex_mount_launcher.py",
        "external_codex_projection.py",
        "tests/test_external_codex_agent.py",
        "tests/test_external_codex_mount_launcher.py",
        "tests/test_external_codex_projection.py",
        "tests/test_external_codex_runtime_install.py",
    ),
    ("governed-execution", "agent-os-adapter"): (
        "CONTRACT.md",
        "VALIDATION.md",
        "aoa_agent_os_runtime.py",
        "runtime-profile.v1.json",
        "schemas/agent-os-runtime-binding.schema.json",
        "schemas/agent-os-runtime-profile.schema.json",
        "tests/test_agent_os_runtime_bridge.py",
    ),
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


def validate_mechanics_topology(
    errors: list[str],
    *,
    root: Path,
    read_text_func: Callable[[Path], str | None],
) -> None:
    mechanics_root = root / "mechanics"
    for path in (
        mechanics_root / "AGENTS.md",
        mechanics_root / "README.md",
        mechanics_root / "ARTIFACT_TOPOLOGY.md",
        root / "docs" / "runtime" / "MECHANICS.md",
    ):
        if not path.is_file():
            errors.append(
                f"mechanics topology root is missing {path.relative_to(root)}"
            )

    atlas_text = read_text_func(mechanics_root / "README.md") or ""
    for package in MECHANIC_PACKAGES:
        if f"]({package}/README.md)" not in atlas_text:
            errors.append(f"mechanics atlas must route to {package}/README.md")

        package_root = mechanics_root / package
        for required_file in MECHANIC_PACKAGE_REQUIRED_FILES:
            path = package_root / required_file
            if not path.is_file():
                errors.append(f"mechanics package {package} is missing {required_file}")

        parts_readme = read_text_func(package_root / "parts" / "README.md") or ""
        parts_root = package_root / "parts"
        if parts_root.is_dir():
            for part_dir in sorted(
                item for item in parts_root.iterdir() if item.is_dir()
            ):
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
            route_text = read_text_func(route_file) or ""
            if "legacy/raw" in route_text:
                errors.append(
                    f"{route_file.relative_to(root)} should route through PROVENANCE.md instead of legacy/raw"
                )

        readme_text = read_text_func(package_root / "README.md") or ""
        for heading in MECHANIC_CARD_HEADINGS:
            if heading not in readme_text:
                errors.append(
                    f"mechanics package {package} README.md must include `{heading}`"
                )
