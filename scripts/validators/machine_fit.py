from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MACHINE_FIT_ROOT = Path("mechanics") / "machine-fit"
REFERENCE_PLATFORM_DOC_PATH = (
    MACHINE_FIT_ROOT / "parts" / "reference-platform" / "docs" / "REFERENCE_PLATFORM.md"
)
REFERENCE_PLATFORM_SPEC_PATH = (
    MACHINE_FIT_ROOT / "parts" / "reference-platform" / "docs" / "REFERENCE_PLATFORM_SPEC.md"
)
HOST_FACTS_SCHEMA_PATH = MACHINE_FIT_ROOT / "parts" / "host-facts" / "schemas" / "schema.v1.json"
HOST_FACTS_EXAMPLE_PATH = (
    MACHINE_FIT_ROOT / "parts" / "host-facts" / "examples" / "reference-host.public.json.example"
)
MACHINE_FIT_EXAMPLE_PATH = (
    MACHINE_FIT_ROOT / "parts" / "fit-record" / "examples" / "machine-fit.public.json.example"
)
MACHINE_BRIDGE_DOC_PATH = MACHINE_FIT_ROOT / "parts" / "machine-bridge" / "docs" / "MACHINE_BRIDGE.md"
MACHINE_BRIDGE_SCHEMA_PATH = MACHINE_FIT_ROOT / "parts" / "machine-bridge" / "schemas" / "schema.v1.json"
MACHINE_BRIDGE_EXAMPLE_PATH = (
    MACHINE_FIT_ROOT / "parts" / "machine-bridge" / "examples" / "machine-bridge.public.json.example"
)
PLATFORM_ADAPTATION_POLICY_PATH = (
    MACHINE_FIT_ROOT / "parts" / "platform-adaptations" / "docs" / "PLATFORM_ADAPTATION_POLICY.md"
)
PLATFORM_ADAPTATION_SCHEMA_PATH = (
    MACHINE_FIT_ROOT / "parts" / "platform-adaptations" / "schemas" / "schema.v1.json"
)
PLATFORM_ADAPTATION_EXAMPLE_PATH = (
    MACHINE_FIT_ROOT / "parts" / "platform-adaptations" / "examples" / "platform-adaptation.public.json.example"
)
WINDOWS_PERFORMANCE_PATH = (
    MACHINE_FIT_ROOT / "parts" / "windows-bridge" / "docs" / "WINDOWS_PERFORMANCE.md"
)
DOCTOR_DOC_PATH = (
    Path("mechanics") / "diagnostic-spine" / "parts" / "doctor-readiness" / "docs" / "DOCTOR.md"
)
DOCTOR_SCRIPT_PATH = (
    Path("mechanics") / "diagnostic-spine" / "parts" / "doctor-readiness" / "aoa_doctor.sh"
)
AUTONOMY_STATUS_PATH = (
    Path("mechanics") / "governed-execution" / "parts" / "autonomy-status" / "aoa_status_autonomy.py"
)
DIAGNOSE_WRAPPER_PATH = (
    Path("mechanics") / "diagnostic-spine" / "parts" / "diagnose-wrapper" / "aoa_diagnose.py"
)


def read_text(root: Path, relative_path: Path) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def read_json(root: Path, relative_path: Path) -> dict[str, Any]:
    payload = json.loads((root / relative_path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def validate_reference_platform(errors: list[str], *, root: Path) -> None:
    reference_platform = read_text(root, REFERENCE_PLATFORM_DOC_PATH)
    if "aoa-host-facts" not in reference_platform:
        errors.append("mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md must mention aoa-host-facts")
    if "mechanics/machine-fit/parts/machine-bridge/docs/MACHINE_BRIDGE.md" not in reference_platform:
        errors.append("mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md must point to mechanics/machine-fit/parts/machine-bridge/docs/MACHINE_BRIDGE.md")
    if "REFERENCE_PLATFORM_SPEC.md" not in reference_platform:
        errors.append(
            "mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md must point to REFERENCE_PLATFORM_SPEC.md"
        )

    doctor_doc = read_text(root, DOCTOR_DOC_PATH)
    if "aoa-host-facts" not in doctor_doc:
        errors.append("mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md must mention aoa-host-facts")
    if "aoa-machine-bridge" not in doctor_doc:
        errors.append("mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md must mention aoa-machine-bridge")

    first_run_doc = read_text(root, Path("docs") / "install" / "FIRST_RUN.md")
    if "reference-host.public.json" not in first_run_doc:
        errors.append("docs/install/FIRST_RUN.md must mention reference-host.public.json capture")

    spec_doc = read_text(root, REFERENCE_PLATFORM_SPEC_PATH)
    if "latest.private.json" not in spec_doc:
        errors.append(
            "mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md must define the local private capture path"
        )

    schema = read_json(root, HOST_FACTS_SCHEMA_PATH)
    if schema.get("title") != "AoA Host Facts":
        errors.append("schema.v1.json must describe AoA Host Facts")

    example = read_json(root, HOST_FACTS_EXAMPLE_PATH)
    if example.get("artifact_kind") != "aoa.host-facts":
        errors.append("reference-host.public.json.example must use artifact_kind aoa.host-facts")
    if example.get("capture_mode") != "public":
        errors.append("reference-host.public.json.example must use capture_mode public")
    if example.get("captured_by") != "scripts/aoa-host-facts":
        errors.append("reference-host.public.json.example must use captured_by scripts/aoa-host-facts")

    machine_fit_example = read_json(root, MACHINE_FIT_EXAMPLE_PATH)
    preferred_profiles = (
        machine_fit_example.get("runtime_recommendation", {}).get("preferred_profile_set")
        if isinstance(machine_fit_example.get("runtime_recommendation"), dict)
        else None
    )
    if preferred_profiles != ["substrate", "intel-worker", "tools", "observability"]:
        errors.append("machine-fit public example must use the composition-first intel-full profile set")


def validate_machine_bridge(errors: list[str], *, root: Path) -> None:
    bridge_doc = read_text(root, MACHINE_BRIDGE_DOC_PATH)
    for fragment in (
        "scripts/aoa-machine-bridge --write-latest",
        "abyss-machine stack-bridge export --json",
        "Logs/machine-bridge/",
        "read-only",
    ):
        if fragment not in bridge_doc:
            errors.append(f"{MACHINE_BRIDGE_DOC_PATH.as_posix()} must mention {fragment}")

    storage_doc = read_text(root, Path("docs") / "runtime" / "STORAGE_LAYOUT.md")
    if "Logs/machine-bridge/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Logs/machine-bridge/")

    paths_doc = read_text(root, Path("docs") / "runtime" / "PATHS.md")
    if "Logs/machine-bridge" not in paths_doc:
        errors.append("docs/runtime/PATHS.md must mention Logs/machine-bridge")

    script_doc = read_text(root, Path("scripts") / "AGENTS.md")
    if "aoa-machine-bridge" not in script_doc:
        errors.append("scripts/AGENTS.md must mention aoa-machine-bridge")

    mechanic_parts = read_text(root, MACHINE_FIT_ROOT / "PARTS.md")
    if "Machine bridge" not in mechanic_parts or "parts/machine-bridge/" not in mechanic_parts:
        errors.append("mechanics/machine-fit/PARTS.md must route Machine bridge surfaces")

    schema = read_json(root, MACHINE_BRIDGE_SCHEMA_PATH)
    if schema.get("title") != "AoA Machine Bridge Record":
        errors.append(f"{MACHINE_BRIDGE_SCHEMA_PATH.as_posix()} must describe AoA Machine Bridge Record")

    example = read_json(root, MACHINE_BRIDGE_EXAMPLE_PATH)
    if example.get("artifact_kind") != "aoa.machine-bridge":
        errors.append("machine-bridge public example must use artifact_kind aoa.machine-bridge")
    if example.get("capture_mode") != "public":
        errors.append("machine-bridge public example must use capture_mode public")
    if example.get("captured_by") != "scripts/aoa-machine-bridge":
        errors.append("machine-bridge public example must use captured_by scripts/aoa-machine-bridge")
    contract = example.get("contract") if isinstance(example.get("contract"), dict) else {}
    if contract.get("stack_side_mutates_machine") is not False:
        errors.append("machine-bridge public example must keep stack_side_mutates_machine false")


def validate_machine_integration_freshness_gates(errors: list[str], *, root: Path) -> None:
    doctor_script = read_text(root, DOCTOR_SCRIPT_PATH)
    doctor_doc = read_text(root, DOCTOR_DOC_PATH)
    autonomy_status = read_text(root, AUTONOMY_STATUS_PATH)
    diagnose_wrapper = read_text(root, DIAGNOSE_WRAPPER_PATH)

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


def validate_platform_adaptations(errors: list[str], *, root: Path) -> None:
    boundaries_doc = read_text(root, Path("BOUNDARIES.md"))
    if "platform-adaptation" not in boundaries_doc:
        errors.append("BOUNDARIES.md must mention platform-adaptation records")

    runbook_doc = read_text(root, Path("docs") / "operations" / "RUNBOOK.md")
    if "aoa-platform-adaptation" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-platform-adaptation")

    windows_perf_doc = read_text(root, WINDOWS_PERFORMANCE_PATH)
    if "aoa-platform-adaptation" not in windows_perf_doc:
        errors.append("mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_PERFORMANCE.md must mention aoa-platform-adaptation")

    storage_doc = read_text(root, Path("docs") / "runtime" / "STORAGE_LAYOUT.md")
    if "Logs/platform-adaptations/" not in storage_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Logs/platform-adaptations/")

    policy_doc = read_text(root, PLATFORM_ADAPTATION_POLICY_PATH)
    if "aoa-host-facts" not in policy_doc:
        errors.append("mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md must mention aoa-host-facts")
    if "runtime benchmarks" not in policy_doc and "runtime benchmark" not in policy_doc:
        errors.append("mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md must mention runtime benchmarks")

    schema = read_json(root, PLATFORM_ADAPTATION_SCHEMA_PATH)
    if schema.get("title") != "AoA Platform Adaptation Record":
        errors.append("machine-fit platform-adaptations schema.v1.json must describe AoA Platform Adaptation Record")

    example = read_json(root, PLATFORM_ADAPTATION_EXAMPLE_PATH)
    if example.get("artifact_kind") != "aoa.platform-adaptation":
        errors.append("platform-adaptation.public.json.example must use artifact_kind aoa.platform-adaptation")
    if example.get("capture_mode") != "public":
        errors.append("platform-adaptation.public.json.example must use capture_mode public")
    if example.get("captured_by") != "scripts/aoa-platform-adaptation":
        errors.append("platform-adaptation.public.json.example must use captured_by scripts/aoa-platform-adaptation")
