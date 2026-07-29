from __future__ import annotations

from collections.abc import Callable, Sequence
import json
from pathlib import Path
import re
from typing import Any

TextFileIterator = Callable[[], list[Path]]
TextReader = Callable[[Path], str | None]

STALE_ABYSS_PATH = "/srv/" + "abyss"
STALE_ABYSS_PATTERN = re.compile(re.escape(STALE_ABYSS_PATH) + r"(?!-)")
STALE_STACK_ROOT = "/srv/" + "abyss-stack"
WORKSPACE_ROOT_DEFAULT = "/srv/AbyssOS"
RETIRED_ROUTING_ENV = "AOA_" + "ROUTING_ROOT"
RETIRED_ROUTING_CHECKOUT = f"{WORKSPACE_ROOT_DEFAULT}/" + "aoa-routing"
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
    "aoa-sdk": f"{WORKSPACE_ROOT_DEFAULT}/aoa-sdk",
}
STALE_ABYSS_PATH_ALLOWED = {
    Path("docs") / "legacy" / "MIGRATION_FROM_OLD.md",
}
RETIRED_ROUTING_CONSUMER_SCAN_ALLOWED_PREFIXES = (
    Path("docs") / "decisions",
    Path("Logs") / "decision-graph",
    Path("tests"),
)
DERIVED_KAG_INDEX_ROOT = Path("kag") / "indexes"
LOCAL_AI_TRIALS_PATH = (
    Path("mechanics")
    / "inference-pilots"
    / "parts"
    / "local-trials"
    / "docs"
    / "LOCAL_AI_TRIALS.md"
)
LOCAL_AI_TRIALS_BASELINE_PATH = (
    Path("mechanics")
    / "inference-pilots"
    / "legacy"
    / "trials"
    / "raw"
    / "LOCAL_AI_TRIALS_W0_W4_BASELINE.md"
)
TRUTH_SURFACES_PATH = (
    Path("mechanics")
    / "diagnostic-spine"
    / "parts"
    / "truth-surfaces"
    / "docs"
    / "TRUTH_SURFACES.md"
)
GOVERNED_EXECUTION_PATH = (
    Path("mechanics")
    / "governed-execution"
    / "parts"
    / "governed-runner"
    / "docs"
    / "GOVERNED_EXECUTION.md"
)
W5_PILOT_PATH = (
    Path("mechanics") / "inference-pilots" / "legacy" / "trials" / "raw" / "W5_PILOT.md"
)
W6_PILOT_PATH = (
    Path("mechanics") / "inference-pilots" / "legacy" / "trials" / "raw" / "W6_PILOT.md"
)
PATHS_DOC_PATH = Path("docs") / "runtime" / "PATHS.md"
DEPLOYMENT_DOC_PATH = Path("docs") / "install" / "DEPLOYMENT.md"
PROFILES_DOC_PATH = Path("docs") / "profiles" / "PROFILES.md"
PROFILE_RECIPES_PATH = Path("docs") / "profiles" / "PROFILE_RECIPES.md"
SERVICE_CATALOG_PATH = Path("docs") / "runtime" / "SERVICE_CATALOG.md"
STORAGE_LAYOUT_PATH = Path("docs") / "runtime" / "STORAGE_LAYOUT.md"
LIFECYCLE_DOC_PATH = Path("docs") / "operations" / "LIFECYCLE.md"
PLAYBOOK_RUNTIME_SEAM_PATH = (
    Path("mechanics")
    / "federation-seams"
    / "parts"
    / "playbook-seam"
    / "docs"
    / "PLAYBOOK_RUNTIME_SEAM.md"
)
RECURRENCE_RUNTIME_POLICY_PATH = (
    Path("mechanics")
    / "governed-execution"
    / "parts"
    / "return-policy"
    / "docs"
    / "RECURRENCE_RUNTIME_POLICY.md"
)
GOVERNED_POLICY_PATH = (
    Path("config-templates")
    / "Configs"
    / "agent-api"
    / "governed-execution-policy.yaml"
)
GOVERNED_CANARY_CATALOG_PATH = (
    Path("config-templates")
    / "Configs"
    / "agent-api"
    / "governed-canary-catalog.json"
)
RUNTIME_ROUTE_CONTRACT_FILES = (
    Path("README.md"),
    LOCAL_AI_TRIALS_PATH,
    LOCAL_AI_TRIALS_BASELINE_PATH,
    TRUTH_SURFACES_PATH,
    GOVERNED_EXECUTION_PATH,
    W5_PILOT_PATH,
    W6_PILOT_PATH,
    PATHS_DOC_PATH,
    DEPLOYMENT_DOC_PATH,
    PROFILES_DOC_PATH,
    PROFILE_RECIPES_PATH,
    SERVICE_CATALOG_PATH,
    STORAGE_LAYOUT_PATH,
    LIFECYCLE_DOC_PATH,
    PLAYBOOK_RUNTIME_SEAM_PATH,
    RECURRENCE_RUNTIME_POLICY_PATH,
    GOVERNED_POLICY_PATH,
    GOVERNED_CANARY_CATALOG_PATH,
)

README_REQUIRED_MESSAGES = (
    ("Fedora-first", "README.md must state Fedora-first posture"),
    ("Windows-usable", "README.md must state Windows-usable posture"),
    ("DESIGN.md", "README.md must route readers to DESIGN.md"),
    ("DESIGN.AGENTS.md", "README.md must route readers to DESIGN.AGENTS.md"),
    (
        "mechanics/governed-execution/parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md",
        "README.md must route readers to mechanics/governed-execution/parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md",
    ),
    (
        "mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md",
        "README.md must route readers to mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md",
    ),
    (
        "mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md",
        "README.md must route readers to mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md",
    ),
    (
        "mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md",
        "README.md must route readers to mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md",
    ),
    (
        "mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md",
        "README.md must route readers to mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md",
    ),
    (
        "docs/governance/BRANCH_POLICY.md",
        "README.md must route readers to docs/governance/BRANCH_POLICY.md",
    ),
    (
        "mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md",
        "README.md must route readers to mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md",
    ),
    (
        "mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md",
        "README.md must route readers to mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md",
    ),
    (
        "mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md",
        "README.md must route readers to mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md",
    ),
    (
        "mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md",
        "README.md must route readers to mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md",
    ),
    ("scripts/README.md", "README.md must route readers to scripts/README.md"),
    (
        "docs/routes/START_HERE_ROUTE_CONTRACT.md",
        "README.md must route readers to docs/routes/START_HERE_ROUTE_CONTRACT.md",
    ),
)
README_FORBIDDEN_SNIPPETS = (
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
)


def read_required(root: Path, relative_path: Path, errors: list[str]) -> str:
    try:
        return (root / relative_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"missing required file: {relative_path.as_posix()}")
        return ""


def require_snippets(
    text: str,
    *,
    relative_path: Path,
    snippets: Sequence[str],
    errors: list[str],
) -> None:
    label = relative_path.as_posix()
    for required_snippet in snippets:
        if required_snippet not in text:
            errors.append(f"{label} must mention `{required_snippet}`")


def load_structured_object(root: Path, relative_path: Path) -> dict[str, object]:
    text = (root / relative_path).read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(text)
    except ImportError:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{relative_path.as_posix()} must parse as an object")
    return payload


def validate_stale_path_hygiene(
    errors: list[str],
    *,
    root: Path,
    text_file_iter_func: TextFileIterator,
    read_text_func: TextReader,
) -> None:
    for path in text_file_iter_func():
        text = read_text_func(path)
        if text is None:
            continue
        relative_path = path.relative_to(root)
        if relative_path.is_relative_to(DERIVED_KAG_INDEX_ROOT):
            continue
        if STALE_ABYSS_PATTERN.search(text) and relative_path not in STALE_ABYSS_PATH_ALLOWED:
            errors.append(
                f"stale path '{STALE_ABYSS_PATH}' found in {relative_path}"
            )
        if STALE_STACK_ROOT in text:
            errors.append(
                f"stale stack root '{STALE_STACK_ROOT}' found in {relative_path}"
            )


def validate_retired_routing_consumer_hygiene(
    errors: list[str],
    *,
    root: Path,
    text_file_iter_func: TextFileIterator,
    read_text_func: TextReader,
) -> None:
    for path in text_file_iter_func():
        text = read_text_func(path)
        if text is None:
            continue
        relative_path = path.relative_to(root)
        if (
            relative_path.is_relative_to(DERIVED_KAG_INDEX_ROOT)
            or "legacy" in relative_path.parts
            or any(
                relative_path.is_relative_to(prefix)
                for prefix in RETIRED_ROUTING_CONSUMER_SCAN_ALLOWED_PREFIXES
            )
        ):
            continue
        for retired_surface in (
            RETIRED_ROUTING_ENV,
            RETIRED_ROUTING_CHECKOUT,
        ):
            if retired_surface in text:
                errors.append(
                    "retired routing checkout consumer found in "
                    f"{relative_path}: {retired_surface}"
                )


def validate_readme_route_focus(errors: list[str], *, root: Path) -> None:
    readme = read_required(root, Path("README.md"), errors)
    for snippet, message in README_REQUIRED_MESSAGES:
        if snippet not in readme:
            errors.append(message)
    for forbidden in README_FORBIDDEN_SNIPPETS:
        if forbidden in readme:
            errors.append(
                "README.md must stay route-focused; move root inventory detail "
                f"to the owning surface instead of `{forbidden}`"
            )


def validate_inference_and_governance_route_docs(errors: list[str], *, root: Path) -> None:
    local_ai_trials = read_required(root, LOCAL_AI_TRIALS_PATH, errors)
    require_snippets(
        local_ai_trials,
        relative_path=LOCAL_AI_TRIALS_PATH,
        snippets=(
            "TRUTH_SURFACES.md",
            "GOVERNED_EXECUTION.md",
            "compatibility-runners/aoa-local-ai-trials",
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
        ),
        errors=errors,
    )

    local_ai_trials_w0_w4_baseline = read_required(root, LOCAL_AI_TRIALS_BASELINE_PATH, errors)
    require_snippets(
        local_ai_trials_w0_w4_baseline,
        relative_path=LOCAL_AI_TRIALS_BASELINE_PATH,
        snippets=(
            "prepare-wave W4 --lane docs",
            "apply-case W4 <case-id>",
            "proposal.edit-spec.json",
            "exact_replace",
            "anchored_replace",
            "deterministically inside the runner",
            "script_refresh",
            "approval.status.json",
            "isolated git worktree",
        ),
        errors=errors,
    )

    truth_doc = read_required(root, TRUTH_SURFACES_PATH, errors)
    require_snippets(
        truth_doc,
        relative_path=TRUTH_SURFACES_PATH,
        snippets=(
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
        ),
        errors=errors,
    )

    governed_doc = read_required(root, GOVERNED_EXECUTION_PATH, errors)
    require_snippets(
        governed_doc,
        relative_path=GOVERNED_EXECUTION_PATH,
        snippets=(
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
        ),
        errors=errors,
    )

    w5_doc = read_required(root, W5_PILOT_PATH, errors)
    require_snippets(
        w5_doc,
        relative_path=W5_PILOT_PATH,
        snippets=(
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
        ),
        errors=errors,
    )

    w6_doc = read_required(root, W6_PILOT_PATH, errors)
    require_snippets(
        w6_doc,
        relative_path=W6_PILOT_PATH,
        snippets=(
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
        ),
        errors=errors,
    )


def validate_runtime_and_federation_route_docs(errors: list[str], *, root: Path) -> None:
    paths_doc = read_required(root, PATHS_DOC_PATH, errors)
    for required_snippet in (
        "/srv/AbyssOS/abyss-stack",
        "AOA_SOURCE_ROOT",
        "AOA_MEMO_ROOT",
        "AOA_EVALS_ROOT",
        "AOA_PLAYBOOKS_ROOT",
        "AOA_KAG_ROOT",
        "AOA_TOS_ROOT",
    ):
        if required_snippet not in paths_doc:
            errors.append(f"docs/runtime/PATHS.md must mention {required_snippet}")
    for forbidden_snippet in (
        RETIRED_ROUTING_ENV,
        RETIRED_ROUTING_CHECKOUT,
    ):
        if forbidden_snippet in paths_doc:
            errors.append(
                "docs/runtime/PATHS.md must not advertise retired routing "
                f"checkout dependency {forbidden_snippet}"
            )
    require_snippets(
        paths_doc,
        relative_path=PATHS_DOC_PATH,
        snippets=(
            "Knowledge/federation/aoa-routing/",
            "scripts/aoa-routing-cutover",
            "admitted `aoa-sdk` release",
        ),
        errors=errors,
    )
    if "WSL2" not in paths_doc:
        errors.append(
            "docs/runtime/PATHS.md should mention WSL2 in the Windows-usable model"
        )

    deployment_doc = read_required(root, DEPLOYMENT_DOC_PATH, errors)
    require_snippets(
        deployment_doc,
        relative_path=DEPLOYMENT_DOC_PATH,
        snippets=(
            "source-authored change is not live until `scripts/aoa-sync-configs` updates `/srv/AbyssOS/abyss-stack/Configs`",
            "python scripts/validate_stack.py --parity-check",
            "aoa-status --autonomy",
            "governed-execution-policy.yaml",
            "governed-canary-catalog.json",
            "scripts/aoa-governed-run",
            "scripts/aoa-bootstrap-configs --force",
            "Logs/governed-runs",
        ),
        errors=errors,
    )
    if (
        "scripts/aoa-sync-federation-surfaces --check --layer aoa-routing"
        not in deployment_doc
    ):
        errors.append(
            "docs/install/DEPLOYMENT.md must mention check-only aoa-routing "
            "federation validation"
        )
    if "scripts/aoa-routing-cutover" not in deployment_doc:
        errors.append(
            "docs/install/DEPLOYMENT.md must route aoa-routing materialization "
            "through the cutover command"
        )
    if "scripts/aoa-sync-federation-surfaces --layer aoa-routing" in deployment_doc:
        errors.append(
            "docs/install/DEPLOYMENT.md must not advertise checkout-backed "
            "aoa-routing sync"
        )
    for layer in (
        "aoa-memo",
        "aoa-evals",
        "aoa-playbooks",
        "aoa-kag",
        "tos-source",
    ):
        if f"scripts/aoa-sync-federation-surfaces --layer {layer}" not in deployment_doc:
            errors.append(f"docs/install/DEPLOYMENT.md must mention {layer} federation sync")

    profiles_doc = read_required(root, PROFILES_DOC_PATH, errors)
    profile_route_requirements = (
        ("aoa-routing advisory seam", "docs/profiles/PROFILES.md must describe the aoa-routing advisory seam"),
        ("aoa-memo", "docs/profiles/PROFILES.md must describe the aoa-memo recall seam"),
        ("aoa-evals", "docs/profiles/PROFILES.md must describe the aoa-evals eval selection seam"),
        ("aoa-playbooks", "docs/profiles/PROFILES.md must describe the aoa-playbooks advisory seam"),
        ("aoa-kag", "docs/profiles/PROFILES.md must describe the aoa-kag advisory seam"),
        ("tos-source", "docs/profiles/PROFILES.md must describe the tos-source handoff seam"),
    )
    for snippet, message in profile_route_requirements:
        if snippet not in profiles_doc:
            errors.append(message)

    recipes_doc = read_required(root, PROFILE_RECIPES_PATH, errors)
    for layer in ("aoa-routing", "aoa-memo", "aoa-evals", "aoa-playbooks", "aoa-kag", "tos-source"):
        if layer not in recipes_doc:
            errors.append(f"docs/profiles/PROFILE_RECIPES.md must mention {layer}")

    catalog_doc = read_required(root, SERVICE_CATALOG_PATH, errors)
    for snippet, message in (
        (
            "aoa-routing advisory routing surfaces",
            "docs/runtime/SERVICE_CATALOG.md must mention aoa-routing advisory routing surfaces",
        ),
        ("aoa-memo", "docs/runtime/SERVICE_CATALOG.md must mention aoa-memo"),
        ("aoa-evals", "docs/runtime/SERVICE_CATALOG.md must mention aoa-evals"),
        ("aoa-playbooks", "docs/runtime/SERVICE_CATALOG.md must mention aoa-playbooks"),
        ("aoa-kag", "docs/runtime/SERVICE_CATALOG.md must mention aoa-kag"),
        ("tos-source", "docs/runtime/SERVICE_CATALOG.md must mention tos-source"),
        ("aoa-governed-run", "docs/runtime/SERVICE_CATALOG.md must mention aoa-governed-run"),
        ("promotion summaries", "docs/runtime/SERVICE_CATALOG.md must mention promotion summaries"),
    ):
        if snippet not in catalog_doc:
            errors.append(message)

    storage_doc = read_required(root, STORAGE_LAYOUT_PATH, errors)
    require_snippets(
        storage_doc,
        relative_path=STORAGE_LAYOUT_PATH,
        snippets=(
            "Knowledge/federation/aoa-routing/",
            "Knowledge/federation/aoa-memo/",
            "Knowledge/federation/aoa-evals/",
            "Knowledge/federation/aoa-playbooks/",
            "Knowledge/federation/aoa-kag/",
            "Knowledge/federation/tos-source/",
            "Logs/memo-exports/",
            "Logs/eval-exports/",
            "Logs/rpg/",
            "mechanics/federation-seams/parts/rpg-runtime/generated/",
        ),
        errors=errors,
    )

    lifecycle_doc = read_required(root, LIFECYCLE_DOC_PATH, errors)
    require_snippets(
        lifecycle_doc,
        relative_path=LIFECYCLE_DOC_PATH,
        snippets=(
            "source_authored",
            "deployed",
            "trial_proven",
            "live_available",
            "python scripts/validate_stack.py --parity-check",
        ),
        errors=errors,
    )

    playbook_runtime_doc = read_required(root, PLAYBOOK_RUNTIME_SEAM_PATH, errors)
    require_snippets(
        playbook_runtime_doc,
        relative_path=PLAYBOOK_RUNTIME_SEAM_PATH,
        snippets=(
            "aoa-governed-run",
            "governed-execution-policy.yaml",
            "trust state",
            "runtime permission semantics still live in `abyss-stack`",
        ),
        errors=errors,
    )

    recurrence_doc = read_required(root, RECURRENCE_RUNTIME_POLICY_PATH, errors)
    require_snippets(
        recurrence_doc,
        relative_path=RECURRENCE_RUNTIME_POLICY_PATH,
        snippets=(
            "governed-execution-policy.yaml",
            "runtime execution permissions only",
            "langchain-api /run/federated",
        ),
        errors=errors,
    )


def validate_governed_policy(errors: list[str], *, root: Path) -> None:
    try:
        governed_policy = load_structured_object(root, GOVERNED_POLICY_PATH)
    except Exception as exc:
        errors.append(f"governed execution policy must parse cleanly: {exc}")
        return

    if governed_policy.get("surface_type") != "runtime_governed_execution_policy":
        errors.append("governed execution policy must declare surface_type=runtime_governed_execution_policy")

    global_rules = governed_policy.get("global_rules")
    if not isinstance(global_rules, dict):
        errors.append("governed execution policy must set global_rules.gate_mode=fail_closed")
        errors.append("governed execution policy must declare global_rules.default_target_id")
        errors.append("governed execution policy must define promotion_criteria.canary_proven and promotion_criteria.trusted")
        errors.append("governed execution policy must define repo_scope_expansion_gate")
        global_rules = {}
    else:
        if global_rules.get("gate_mode") != "fail_closed":
            errors.append("governed execution policy must set global_rules.gate_mode=fail_closed")
        if not isinstance(global_rules.get("default_target_id"), str):
            errors.append("governed execution policy must declare global_rules.default_target_id")
        promotion_criteria = global_rules.get("promotion_criteria")
        if (
            not isinstance(promotion_criteria, dict)
            or "canary_proven" not in promotion_criteria
            or "trusted" not in promotion_criteria
        ):
            errors.append("governed execution policy must define promotion_criteria.canary_proven and promotion_criteria.trusted")
        if not isinstance(global_rules.get("repo_scope_expansion_gate"), dict):
            errors.append("governed execution policy must define repo_scope_expansion_gate")

    targets = governed_policy.get("targets")
    if not isinstance(targets, dict) or set(targets) != {"abyss-stack"}:
        errors.append(
            "governed execution policy must declare only the active "
            "abyss-stack mutation target"
        )
        return

    abyss_stack_target = targets.get("abyss-stack") or {}
    if not isinstance(abyss_stack_target, dict):
        errors.append(
            "governed execution policy must declare an explicit abyss-stack target"
        )
        return

    abyss_stack_playbooks = abyss_stack_target.get("playbooks") or {}
    if not isinstance(abyss_stack_playbooks, dict):
        errors.append(
            "governed execution policy must declare abyss-stack playbooks"
        )
        return

    abyss_stack_playbook = abyss_stack_playbooks.get("AOA-P-0011") or {}
    if not isinstance(abyss_stack_playbook, dict):
        errors.append(
            "governed execution policy must declare abyss-stack AOA-P-0011"
        )
        return

    if abyss_stack_target.get("default_repo_root") != "~/src/abyss-stack":
        errors.append(
            "abyss-stack governed policy default_repo_root must use the portable ~/src/abyss-stack default"
        )
    if abyss_stack_playbook.get("trust_state") not in {"experimental", "canary_proven", "trusted"}:
        errors.append("abyss-stack AOA-P-0011 governed policy entry must declare a valid trust_state")
    if not isinstance(abyss_stack_playbook.get("task_class"), str):
        errors.append("abyss-stack AOA-P-0011 governed policy entry must declare task_class")


def validate_governed_canary_catalog(errors: list[str], *, root: Path) -> None:
    try:
        canary_catalog = load_structured_object(root, GOVERNED_CANARY_CATALOG_PATH)
    except Exception as exc:
        errors.append(f"governed canary catalog must parse cleanly: {exc}")
        return

    if canary_catalog.get("surface_type") != "runtime_governed_execution_canary_catalog":
        errors.append("governed canary catalog must declare surface_type=runtime_governed_execution_canary_catalog")
    canaries = canary_catalog.get("canaries")
    if not isinstance(canaries, list) or not canaries:
        errors.append("governed canary catalog must contain at least one canary entry")
        return

    target_ids = {item.get("target_id") for item in canaries if isinstance(item, dict)}
    if target_ids != {"abyss-stack"}:
        errors.append(
            "governed canary catalog must contain only abyss-stack canaries"
        )


def validate_paths(
    errors: list[str],
    *,
    root: Path,
    text_file_iter_func: TextFileIterator,
    read_text_func: TextReader,
) -> None:
    validate_stale_path_hygiene(
        errors,
        root=root,
        text_file_iter_func=text_file_iter_func,
        read_text_func=read_text_func,
    )
    validate_retired_routing_consumer_hygiene(
        errors,
        root=root,
        text_file_iter_func=text_file_iter_func,
        read_text_func=read_text_func,
    )
    validate_readme_route_focus(errors, root=root)
    validate_inference_and_governance_route_docs(errors, root=root)
    validate_runtime_and_federation_route_docs(errors, root=root)
    validate_governed_policy(errors, root=root)
    validate_governed_canary_catalog(errors, root=root)
