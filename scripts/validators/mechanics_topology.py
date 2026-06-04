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
            errors.append(f"mechanics topology root is missing {path.relative_to(root)}")

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
            route_text = read_text_func(route_file) or ""
            if "legacy/raw" in route_text:
                errors.append(
                    f"{route_file.relative_to(root)} should route through PROVENANCE.md or legacy/INDEX.md instead of legacy/raw"
                )

        readme_text = read_text_func(package_root / "README.md") or ""
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
