from __future__ import annotations

from collections.abc import Sequence
import json
from pathlib import Path
from typing import Any

DIAGNOSTIC_SPINE_DOC_ROOT = (
    Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces" / "docs"
)
DIAGNOSTIC_SPINE_PATH = DIAGNOSTIC_SPINE_DOC_ROOT / "DIAGNOSTIC_SPINE.md"
DIAGNOSTIC_SURFACE_ROOT = (
    Path("mechanics") / "diagnostic-spine" / "parts" / "diagnostic-surfaces"
)
DIAGNOSTIC_SURFACE_SCHEMA_ROOT = DIAGNOSTIC_SURFACE_ROOT / "schemas"
DIAGNOSTIC_SURFACE_EXAMPLE_ROOT = DIAGNOSTIC_SURFACE_ROOT / "examples"
DIAGNOSTIC_SURFACE_CATALOG_PATH = (
    Path("mechanics")
    / "diagnostic-spine"
    / "parts"
    / "diagnostic-surfaces"
    / "generated"
    / "diagnostic_surface_catalog.min.json"
)

DIAGNOSTIC_TARGET_SCHEMA_PATH = DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "diagnostic_target.schema.json"
DIAGNOSTIC_SESSION_SCHEMA_PATH = DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "diagnostic_session.schema.json"
DIAGNOSIS_COMPANION_SCHEMA_PATH = DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "diagnosis_companion.schema.json"
DIAGNOSTIC_ANCHOR_REF_SCHEMA_PATH = (
    DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "diagnostic_anchor_ref.schema.json"
)
REPAIR_HANDOFF_SCHEMA_PATH = DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "repair_handoff.schema.json"
REVIEWED_DIAGNOSIS_REF_SCHEMA_PATH = (
    DIAGNOSTIC_SURFACE_SCHEMA_ROOT / "reviewed_diagnosis_ref.schema.json"
)

DIAGNOSTIC_TARGET_EXAMPLE_PATH = (
    DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "diagnostic_target.min.example.json"
)
DIAGNOSTIC_SESSION_EXAMPLE_PATH = (
    DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "diagnostic_session.min.example.json"
)
DIAGNOSIS_COMPANION_EXAMPLE_PATH = (
    DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "diagnosis_companion.min.example.json"
)
DIAGNOSTIC_ANCHOR_REF_EXAMPLE_PATH = (
    DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "diagnostic_anchor_ref.min.example.json"
)
REPAIR_HANDOFF_EXAMPLE_PATH = (
    DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "repair_handoff.min.example.json"
)
REVIEWED_DIAGNOSIS_REF_EXAMPLE_PATH = (
    DIAGNOSTIC_SURFACE_EXAMPLE_ROOT / "reviewed_diagnosis_ref.min.example.json"
)

DIAGNOSTIC_SURFACE_CATALOG_EXPECTED_NAMES = (
    "diagnostic_target",
    "diagnostic_session",
    "diagnosis_companion",
    "reviewed_diagnosis_ref",
    "repair_handoff",
)

DIAGNOSTIC_CATALOG_REF = (
    "mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/"
    "diagnostic_surface_catalog.min.json"
)
DIAGNOSTIC_OWNER_SKILL_ROOT = Path("skills") / "abyss-self-diagnostic-spine"
DIAGNOSTIC_OWNER_SKILL_PATH = DIAGNOSTIC_OWNER_SKILL_ROOT / "SKILL.md"
DIAGNOSTIC_OWNER_SKILL_CONTRACT_PATH = (
    DIAGNOSTIC_OWNER_SKILL_ROOT / "references" / "contract.yaml"
)
DIAGNOSTIC_OWNER_SKILL_PROCEDURE_PATH = (
    DIAGNOSTIC_OWNER_SKILL_ROOT / "references" / "diagnose.md"
)
DIAGNOSTIC_OWNER_SKILL_INTERFACE_PATH = (
    DIAGNOSTIC_OWNER_SKILL_ROOT / "agents" / "openai.yaml"
)
SKILL_HOME_MANIFEST_PATH = Path("skills") / "port.manifest.json"
DIAGNOSTIC_AUTHORITY_REF = (
    "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md"
)
DIAGNOSTIC_SURFACE_ARTIFACT_IDENTITY = {
    "artifact_class": "runtime_diagnostic_readmodel_catalog",
    "surface_state": "public_source_generated_runtime_diagnostic_catalog",
    "owner_repo": "abyss-stack",
    "authority_ref": DIAGNOSTIC_AUTHORITY_REF,
    "trust_layer": [
        "abi_contract_signature",
        "w3c_prov_lineage",
    ],
    "action": "ADD_CONSUMER_EXPECTATION",
}


def read_required_text(errors: list[str], *, root: Path, relative_path: Path) -> str:
    try:
        return (root / relative_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"missing required file: {relative_path.as_posix()}")
        return ""


def read_required_json(
    errors: list[str],
    *,
    root: Path,
    relative_path: Path,
) -> dict[str, Any] | None:
    try:
        payload = json.loads((root / relative_path).read_text(encoding="utf-8"))
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


def require_snippets(
    errors: list[str],
    *,
    text: str,
    path_label: str,
    snippets: Sequence[str],
) -> None:
    for snippet in snippets:
        if snippet not in text:
            errors.append(f"{path_label} must mention `{snippet}`")


def require_schema_fields(
    errors: list[str],
    *,
    schema: dict[str, Any] | None,
    title: str,
    title_error: str,
    required_error: str,
    field_error_prefix: str,
    fields: Sequence[str],
) -> None:
    if schema and schema.get("title") != title:
        errors.append(title_error)
    if not schema:
        return
    required = schema.get("required")
    if not isinstance(required, list):
        errors.append(required_error)
        return
    for field in fields:
        if field not in required:
            errors.append(f"{field_error_prefix} must require `{field}`")


def validate_diagnostic_spine_contracts(
    errors: list[str],
    *,
    root: Path,
) -> None:
    readme = read_required_text(errors, root=root, relative_path=Path("README.md"))
    require_snippets(
        errors,
        text=readme,
        path_label="README.md",
        snippets=(
            "mechanics/diagnostic-spine/README.md",
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md",
            DIAGNOSTIC_CATALOG_REF,
            "scripts/aoa-diagnose",
        ),
    )

    spine_doc = read_required_text(errors, root=root, relative_path=DIAGNOSTIC_SPINE_PATH)
    require_snippets(
        errors,
        text=spine_doc,
        path_label=DIAGNOSTIC_SPINE_PATH.as_posix(),
        snippets=(
            "The goal is not a louder doctor.",
            "The diagnostic spine is a read model with memory.",
            f"`{DIAGNOSTIC_CATALOG_REF}`",
            "what path is being diagnosed",
            "`diagnostic_target_v1`",
            "`diagnostic_session_v1`",
            "`diagnosis_companion_v1`",
            "`diagnostic_anchor_ref_v1`",
            "`repair_handoff_v1`",
            "`reviewed_diagnosis_ref_v1`",
            "`skills/abyss-self-diagnostic-spine`",
            "OS user profile",
            "scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest",
            "scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest --write-last-good-ref",
            "scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest --write-reviewed-diagnosis-ref",
            "scripts/aoa-diagnose --preset intel-full --with-reviewed-diagnosis-ref /path/to/reviewed-diagnosis.packet.json --write-latest",
            "A strong diagnostic spine gives the system self-location before self-assertion.",
        ),
    )

    runbook_doc = read_required_text(
        errors,
        root=root,
        relative_path=Path("docs") / "operations" / "RUNBOOK.md",
    )
    require_snippets(
        errors,
        text=runbook_doc,
        path_label="docs/operations/RUNBOOK.md",
        snippets=(
            "Logs/diagnostics/latest/",
            "diagnostic_session_v1",
            "aoa-diagnose",
            "diagnostic_target.json",
            "diagnosis_companion.json",
            "last_good.ref.json",
            "repair_handoff.json",
            "reviewed_diagnosis.ref.json",
        ),
    )

    validate_diagnostic_schemas(errors, root=root)
    validate_diagnostic_examples(errors, root=root)
    validate_diagnostic_surface_catalog(errors, root=root)
    validate_diagnostic_owner_skill(errors, root=root)


def validate_diagnostic_owner_skill(errors: list[str], *, root: Path) -> None:
    skill = read_required_text(
        errors,
        root=root,
        relative_path=DIAGNOSTIC_OWNER_SKILL_PATH,
    )
    require_snippets(
        errors,
        text=skill,
        path_label=DIAGNOSTIC_OWNER_SKILL_PATH.as_posix(),
        snippets=(
            "name: abyss-self-diagnostic-spine",
            "Produce, capture, or review one owner-typed Abyss runtime diagnosis",
            ".aoa-skill-source.json",
            "owner_repo=abyss-stack",
            "source_path=skills/abyss-self-diagnostic-spine",
            "version=0.2.1",
            "Select exactly one operation: `observe`, `capture`, or `review`.",
            "Do not load a shared recovery procedure before the owner packet",
            "Stop after one packet and one review.",
        ),
    )

    contract = read_required_text(
        errors,
        root=root,
        relative_path=DIAGNOSTIC_OWNER_SKILL_CONTRACT_PATH,
    )
    require_snippets(
        errors,
        text=contract,
        path_label=DIAGNOSTIC_OWNER_SKILL_CONTRACT_PATH.as_posix(),
        snippets=(
            "owner: abyss-stack",
            "canonical_source: skills/abyss-self-diagnostic-spine",
            "version: 0.2.1",
            "lifecycle: admitted",
            "health: active",
            "owner_cli: scripts/aoa-diagnose",
            "techniques_runtime_dependency: false",
        ),
    )

    procedure = read_required_text(
        errors,
        root=root,
        relative_path=DIAGNOSTIC_OWNER_SKILL_PROCEDURE_PATH,
    )
    require_snippets(
        errors,
        text=procedure,
        path_label=DIAGNOSTIC_OWNER_SKILL_PROCEDURE_PATH.as_posix(),
        snippets=(
            "## Review an existing packet",
            "## Observe current state",
            "## Capture an owner artifact",
            "## Review and hand off",
            "scripts/aoa-diagnose <one preset/profile selection> --truth-goal <goal>",
        ),
    )

    interface = read_required_text(
        errors,
        root=root,
        relative_path=DIAGNOSTIC_OWNER_SKILL_INTERFACE_PATH,
    )
    require_snippets(
        errors,
        text=interface,
        path_label=DIAGNOSTIC_OWNER_SKILL_INTERFACE_PATH.as_posix(),
        snippets=(
            'display_name: "Abyss Self-Diagnostic Spine"',
            'default_prompt: "Use $abyss-self-diagnostic-spine',
        ),
    )

    manifest = read_required_json(
        errors,
        root=root,
        relative_path=SKILL_HOME_MANIFEST_PATH,
    )
    if not manifest:
        return
    if manifest.get("schema_version") != "aoa_skill_home_port_v2":
        errors.append("skills/port.manifest.json must use aoa_skill_home_port_v2")
    if manifest.get("owner_repo") != "abyss-stack":
        errors.append("skills/port.manifest.json must declare owner_repo abyss-stack")
    bundles = manifest.get("bundles")
    expected_bundle = {
        "name": "abyss-self-diagnostic-spine",
        "path": "skills/abyss-self-diagnostic-spine",
        "version": "0.2.1",
        "lifecycle": "admitted",
        "visibility": "advertised",
        "admission_ref": "docs/decisions/ABYSS-STACK-D-0080-diagnostic-skill-owner-home.md",
    }
    if bundles != [expected_bundle]:
        errors.append(
            "skills/port.manifest.json must expose the admitted "
            "abyss-self-diagnostic-spine 0.2.1 owner bundle"
        )
    exposure = manifest.get("exposure")
    if not isinstance(exposure, dict) or exposure.get("scope") != "user":
        errors.append("skills/port.manifest.json must use user-scoped exposure")
    elif exposure.get("profile") != "os-user-default" or exposure.get("skills") != [
        "abyss-self-diagnostic-spine"
    ]:
        errors.append(
            "skills/port.manifest.json must expose abyss-self-diagnostic-spine "
            "once through os-user-default"
        )


def validate_diagnostic_schemas(errors: list[str], *, root: Path) -> None:
    target_schema = read_required_json(errors, root=root, relative_path=DIAGNOSTIC_TARGET_SCHEMA_PATH)
    require_schema_fields(
        errors,
        schema=target_schema,
        title="abyss-stack diagnostic_target_v1",
        title_error="diagnostic_target.schema.json must describe abyss-stack diagnostic_target_v1",
        required_error="diagnostic_target.schema.json must declare a required field list",
        field_error_prefix="diagnostic_target.schema.json",
        fields=(
            "schema_version",
            "preset",
            "profiles",
            "truth_goal",
            "required_checks",
            "drift_watch",
            "public_safe",
        ),
    )

    session_schema = read_required_json(errors, root=root, relative_path=DIAGNOSTIC_SESSION_SCHEMA_PATH)
    require_schema_fields(
        errors,
        schema=session_schema,
        title="abyss-stack diagnostic_session_v1",
        title_error="diagnostic_session.schema.json must describe abyss-stack diagnostic_session_v1",
        required_error="diagnostic_session.schema.json must declare a required field list",
        field_error_prefix="diagnostic_session.schema.json",
        fields=(
            "schema_version",
            "target",
            "axes",
            "truth_status",
            "drifts",
            "exit_class",
            "public_safe",
        ),
    )

    diagnosis_companion_schema = read_required_json(
        errors,
        root=root,
        relative_path=DIAGNOSIS_COMPANION_SCHEMA_PATH,
    )
    require_schema_fields(
        errors,
        schema=diagnosis_companion_schema,
        title="abyss-stack diagnosis_companion_v1",
        title_error="diagnosis_companion.schema.json must describe abyss-stack diagnosis_companion_v1",
        required_error="diagnosis_companion.schema.json must declare a required field list",
        field_error_prefix="diagnosis_companion.schema.json",
        fields=(
            "schema_version",
            "artifact_kind",
            "diagnostic_session_ref",
            "diagnostic_session_id",
            "target",
            "review_status",
            "summary",
            "diagnoses",
            "public_safe",
        ),
    )

    anchor_ref_schema = read_required_json(
        errors,
        root=root,
        relative_path=DIAGNOSTIC_ANCHOR_REF_SCHEMA_PATH,
    )
    require_schema_fields(
        errors,
        schema=anchor_ref_schema,
        title="abyss-stack diagnostic_anchor_ref_v1",
        title_error="diagnostic_anchor_ref.schema.json must describe abyss-stack diagnostic_anchor_ref_v1",
        required_error="diagnostic_anchor_ref.schema.json must declare a required field list",
        field_error_prefix="diagnostic_anchor_ref.schema.json",
        fields=(
            "schema_version",
            "artifact_kind",
            "anchor_class",
            "target",
            "diagnostic_session_id",
            "diagnostic_session_path",
            "diagnostic_target_path",
            "truth_status",
            "public_safe",
        ),
    )

    repair_handoff_schema = read_required_json(
        errors,
        root=root,
        relative_path=REPAIR_HANDOFF_SCHEMA_PATH,
    )
    require_schema_fields(
        errors,
        schema=repair_handoff_schema,
        title="abyss-stack repair_handoff_v1",
        title_error="repair_handoff.schema.json must describe abyss-stack repair_handoff_v1",
        required_error="repair_handoff.schema.json must declare a required field list",
        field_error_prefix="repair_handoff.schema.json",
        fields=(
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
        ),
    )

    reviewed_diagnosis_ref_schema = read_required_json(
        errors,
        root=root,
        relative_path=REVIEWED_DIAGNOSIS_REF_SCHEMA_PATH,
    )
    require_schema_fields(
        errors,
        schema=reviewed_diagnosis_ref_schema,
        title="abyss-stack reviewed_diagnosis_ref_v1",
        title_error="reviewed_diagnosis_ref.schema.json must describe abyss-stack reviewed_diagnosis_ref_v1",
        required_error="reviewed_diagnosis_ref.schema.json must declare a required field list",
        field_error_prefix="reviewed_diagnosis_ref.schema.json",
        fields=(
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
        ),
    )


def validate_diagnostic_examples(errors: list[str], *, root: Path) -> None:
    target_example = read_required_json(errors, root=root, relative_path=DIAGNOSTIC_TARGET_EXAMPLE_PATH)
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

    session_example = read_required_json(errors, root=root, relative_path=DIAGNOSTIC_SESSION_EXAMPLE_PATH)
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

    diagnosis_companion_example = read_required_json(
        errors,
        root=root,
        relative_path=DIAGNOSIS_COMPANION_EXAMPLE_PATH,
    )
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

    anchor_ref_example = read_required_json(
        errors,
        root=root,
        relative_path=DIAGNOSTIC_ANCHOR_REF_EXAMPLE_PATH,
    )
    if anchor_ref_example:
        if anchor_ref_example.get("schema_version") != "diagnostic_anchor_ref_v1":
            errors.append("diagnostic anchor ref example must use schema_version diagnostic_anchor_ref_v1")
        if anchor_ref_example.get("anchor_class") != "last_good":
            errors.append("diagnostic anchor ref example must use anchor_class last_good")
        if anchor_ref_example.get("repo") != "abyss-stack":
            errors.append("diagnostic anchor ref example must set repo to abyss-stack")
        if anchor_ref_example.get("public_safe") is not True:
            errors.append("diagnostic anchor ref example must be public_safe")

    repair_handoff_example = read_required_json(
        errors,
        root=root,
        relative_path=REPAIR_HANDOFF_EXAMPLE_PATH,
    )
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

    reviewed_diagnosis_ref_example = read_required_json(
        errors,
        root=root,
        relative_path=REVIEWED_DIAGNOSIS_REF_EXAMPLE_PATH,
    )
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


def validate_diagnostic_surface_catalog(errors: list[str], *, root: Path) -> None:
    catalog = read_required_json(errors, root=root, relative_path=DIAGNOSTIC_SURFACE_CATALOG_PATH)
    if not catalog:
        return
    if catalog.get("schema_version") != "abyss_stack_diagnostic_surface_catalog_v1":
        errors.append(
            f"{DIAGNOSTIC_CATALOG_REF} must use schema_version abyss_stack_diagnostic_surface_catalog_v1"
        )
    if catalog.get("owner_repo") != "abyss-stack":
        errors.append(f"{DIAGNOSTIC_CATALOG_REF} must set owner_repo to abyss-stack")
    if catalog.get("surface_kind") != "runtime_surface":
        errors.append(f"{DIAGNOSTIC_CATALOG_REF} must stay runtime_surface")
    if catalog.get("authority_ref") != DIAGNOSTIC_AUTHORITY_REF:
        errors.append(
            f"{DIAGNOSTIC_CATALOG_REF} must point authority_ref to {DIAGNOSTIC_AUTHORITY_REF}"
        )
    artifact_identity = catalog.get("artifact_identity")
    if not isinstance(artifact_identity, dict):
        errors.append(f"{DIAGNOSTIC_CATALOG_REF} must include artifact_identity")
    else:
        for key, expected in DIAGNOSTIC_SURFACE_ARTIFACT_IDENTITY.items():
            if artifact_identity.get(key) != expected:
                errors.append(
                    f"{DIAGNOSTIC_CATALOG_REF} artifact_identity.{key} must equal {expected!r}"
                )
        for key in (
            "producer",
            "consumer_expectation",
            "privacy_boundary",
            "content_identity",
            "abi_epoch",
            "contract_version",
            "verification",
        ):
            if key not in artifact_identity:
                errors.append(f"{DIAGNOSTIC_CATALOG_REF} artifact_identity must include {key}")

    surfaces = catalog.get("surfaces")
    if not isinstance(surfaces, list) or len(surfaces) != len(DIAGNOSTIC_SURFACE_CATALOG_EXPECTED_NAMES):
        errors.append(f"{DIAGNOSTIC_CATALOG_REF} must publish exactly five diagnostic surfaces")
    else:
        surface_names = []
        for index, entry in enumerate(surfaces):
            if not isinstance(entry, dict):
                errors.append(f"{DIAGNOSTIC_CATALOG_REF} surface {index} must be an object")
                continue
            for field in ("name", "schema_ref", "example_ref", "primary_question"):
                value = entry.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{DIAGNOSTIC_CATALOG_REF} surface {index} must include non-empty {field}")
            name = entry.get("name")
            schema_ref = entry.get("schema_ref")
            example_ref = entry.get("example_ref")
            if isinstance(name, str):
                surface_names.append(name)
            if isinstance(schema_ref, str) and not (root / schema_ref).exists():
                errors.append(f"{DIAGNOSTIC_CATALOG_REF} schema_ref is missing: {schema_ref}")
            if isinstance(example_ref, str) and not (root / example_ref).exists():
                errors.append(f"{DIAGNOSTIC_CATALOG_REF} example_ref is missing: {example_ref}")
        if tuple(surface_names) != DIAGNOSTIC_SURFACE_CATALOG_EXPECTED_NAMES:
            errors.append(f"{DIAGNOSTIC_CATALOG_REF} surface order must stay aligned with the diagnostic spine")

    validation_refs = catalog.get("validation_refs")
    expected_validation_refs = [
        "scripts/validate_stack.py",
        "scripts/validators/diagnostic_spine.py",
        "tests/test_diagnostic_spine_validator_module.py",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_diagnostic_spine_surface_validator.py",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_diagnostic_spine_contracts.py",
    ]
    if validation_refs != expected_validation_refs:
        errors.append(f"{DIAGNOSTIC_CATALOG_REF} validation_refs must stay aligned with the repo-local diagnostic checks")
    elif isinstance(validation_refs, list):
        for ref in validation_refs:
            if not isinstance(ref, str) or not (root / ref).exists():
                errors.append(f"{DIAGNOSTIC_CATALOG_REF} validation_ref is missing: {ref}")
