from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
QUEST_SCRIPT_DIR = ROOT / "quests" / "scripts"
if str(QUEST_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(QUEST_SCRIPT_DIR))

import quest_surface  # noqa: E402
try:
    from scripts.validators import (
        active_topology_language,
        agent_skill_projection,
        branch_policy,
        decision_surface,
        diagnostic_spine,
        federation_runtime_seams,
        federation_surface,
        inference_pilot_compatibility,
        machine_fit,
        mechanics_topology,
        profile_topology,
        questbook_surface,
        return_policy,
        root_routes,
        runtime_route_contracts,
        runtime_hygiene,
        script_surface,
        service_selection,
        source_hygiene,
        source_structure,
        sync_parity,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from validators import active_topology_language  # type: ignore
    from validators import agent_skill_projection  # type: ignore
    from validators import branch_policy  # type: ignore
    from validators import decision_surface  # type: ignore
    from validators import diagnostic_spine  # type: ignore
    from validators import federation_runtime_seams  # type: ignore
    from validators import federation_surface  # type: ignore
    from validators import inference_pilot_compatibility  # type: ignore
    from validators import machine_fit  # type: ignore
    from validators import mechanics_topology  # type: ignore
    from validators import profile_topology  # type: ignore
    from validators import questbook_surface  # type: ignore
    from validators import return_policy  # type: ignore
    from validators import root_routes  # type: ignore
    from validators import runtime_route_contracts  # type: ignore
    from validators import runtime_hygiene  # type: ignore
    from validators import script_surface  # type: ignore
    from validators import service_selection  # type: ignore
    from validators import source_hygiene  # type: ignore
    from validators import source_structure  # type: ignore
    from validators import sync_parity  # type: ignore

RUNTIME_CONFIGS_MIRROR_MODE = (
    ROOT.name == "Configs"
    and (ROOT / "compose").exists()
    and (ROOT / "config-templates").exists()
    and not (ROOT / "CONTRIBUTING.md").exists()
)

def _iter_text_files() -> list[Path]:
    return source_hygiene.iter_text_files(
        ROOT,
        binary_suffixes=source_hygiene.BINARY_SUFFIXES,
    )


def _read_text_or_none(path: Path) -> str | None:
    return source_hygiene.read_text_or_none(path)


def _iter_tracked_git_files() -> list[str]:
    return source_hygiene.iter_tracked_git_files(ROOT)


def _load_names(file_path: Path) -> list[str]:
    names: list[str] = []

    for raw in file_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.append(line)

    return names


def _compose_service_names(file_path: Path) -> set[str]:
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


def _load_structured_object(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(text)
    except ImportError:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path.relative_to(ROOT)} must parse as an object")
    return payload


def _iter_sync_managed_files() -> list[Path]:
    return sync_parity.iter_sync_managed_files(
        root=ROOT,
        sync_managed_items=sync_parity.SYNC_MANAGED_ITEMS,
        ignored_parts=sync_parity.PARITY_IGNORED_PARTS,
        ignored_suffixes=sync_parity.PARITY_IGNORED_SUFFIXES,
    )


def _git_index_mode(path: Path) -> str | None:
    return script_surface.git_index_mode(path, ROOT)


def _is_executable_source_path(path: Path) -> bool:
    return script_surface.is_executable_source_path(
        path,
        ROOT,
        git_index_mode_func=_git_index_mode,
    )


def _overlay_skill_surface_validator(
    *,
    errors: list[str],
    skill_path: Path,
    description: str,
    expected_target: str | None = None,
) -> None:
    agent_skill_projection.validate_overlay_skill_surface(
        errors=errors,
        root=ROOT,
        skill_path=skill_path,
        description=description,
        expected_target=expected_target,
    )


def _run_source_validators(errors: list[str]) -> None:
    profile_topology.validate_profiles(errors, root=ROOT)
    profile_topology.validate_presets(errors, root=ROOT)
    source_hygiene.validate_git_mirror_hygiene(
        errors,
        tracked_file_iter_func=_iter_tracked_git_files,
        runtime_top_level_dirs=source_hygiene.GIT_MIRROR_RUNTIME_TOP_LEVEL_DIRS,
        cache_parts=source_hygiene.GIT_MIRROR_CACHE_PARTS,
        live_env_names=source_hygiene.GIT_MIRROR_LIVE_ENV_NAMES,
        private_suffixes=source_hygiene.GIT_MIRROR_PRIVATE_SUFFIXES,
        rendered_suffixes=source_hygiene.GIT_MIRROR_RENDERED_SUFFIXES,
        database_suffixes=source_hygiene.GIT_MIRROR_DATABASE_SUFFIXES,
        heavy_suffixes=source_hygiene.GIT_MIRROR_HEAVY_SUFFIXES,
        fixture_prefixes=source_hygiene.GIT_MIRROR_FIXTURE_PREFIXES,
    )
    source_hygiene.validate_no_host_local_source_checkout_paths(
        errors,
        root=ROOT,
        text_file_iter_func=_iter_text_files,
        host_local_source_checkout_patterns=source_hygiene.HOST_LOCAL_SOURCE_CHECKOUT_PATTERNS,
        skip_paths=(ROOT / "scripts" / "validate_stack.py",),
    )
    source_hygiene.validate_no_moved_mechanic_doc_refs(
        errors,
        root=ROOT,
        text_file_iter_func=_iter_text_files,
        moved_mechanic_doc_refs=source_hygiene.MOVED_MECHANIC_DOC_REFS,
        skip_paths=(ROOT / source_hygiene.SOURCE_HYGIENE_VALIDATOR_PATH,),
    )
    source_hygiene.validate_no_stale_active_sibling_roots(
        errors,
        root=ROOT,
        text_file_iter_func=_iter_text_files,
        stale_active_sibling_root_pattern=source_hygiene.STALE_ACTIVE_SIBLING_ROOT_PATTERN,
    )
    runtime_route_contracts.validate_paths(
        errors,
        root=ROOT,
        text_file_iter_func=_iter_text_files,
        read_text_func=_read_text_or_none,
    )
    mechanics_topology.validate_mechanics_topology(
        errors,
        root=ROOT,
        read_text_func=_read_text_or_none,
    )
    script_surface.validate_scripts(
        errors,
        root=ROOT,
        required_scripts=script_surface.REQUIRED_SCRIPTS,
        operator_backend_scripts=script_surface.OPERATOR_BACKEND_SCRIPTS,
        executable_source_path_func=_is_executable_source_path,
    )
    source_structure.validate_required_files(
        errors,
        root=ROOT,
        required_files=source_structure.required_files(ROOT),
    )
    source_structure.validate_root_residual_topology(
        errors,
        root=ROOT,
        read_text_func=_read_text_or_none,
    )
    agent_skill_projection.validate_agent_skill_projection_routes(errors, root=ROOT)
    inference_pilot_compatibility.validate_local_trials_compatibility_bridge(
        errors,
        root=ROOT,
        read_text_func=_read_text_or_none,
        is_executable_source_path_func=_is_executable_source_path,
    )
    inference_pilot_compatibility.validate_inference_pilot_compatibility_gate_language(
        errors,
        root=ROOT,
        read_text_func=_read_text_or_none,
    )
    federation_surface.validate_federation_upstream_compatibility(
        errors,
        root=ROOT,
        bridge_path=ROOT / federation_surface.UPSTREAM_COMPATIBILITY_BRIDGE_PATH,
        read_text_func=_read_text_or_none,
    )
    active_topology_language.validate_active_topology_language(
        errors,
        root=ROOT,
        read_text_func=_read_text_or_none,
    )
    root_routes.validate_root_design_surfaces(errors, root=ROOT)
    root_routes.validate_entry_route_contract(
        errors,
        root=ROOT,
        read_text_func=_read_text_or_none,
    )
    decision_surface.validate_decision_record_surface(
        errors,
        root=ROOT,
        read_text_func=_read_text_or_none,
    )
    sync_parity.validate_sync_managed_items(
        errors,
        root=ROOT,
        sync_managed_items=sync_parity.SYNC_MANAGED_ITEMS,
        read_text_func=_read_text_or_none,
    )
    federation_surface.validate_federation_required_files(
        errors,
        root=ROOT,
        required_runtime_inputs=federation_surface.FEDERATION_REQUIRED_RUNTIME_INPUTS,
        bridge_path=ROOT / federation_surface.UPSTREAM_COMPATIBILITY_BRIDGE_PATH,
        load_structured_object_func=_load_structured_object,
    )
    questbook_surface.validate_questbook_surface(
        errors,
        root=ROOT,
        questbook_path=questbook_surface.QUESTBOOK_PATH,
        questbook_integration_path=questbook_surface.QUESTBOOK_INTEGRATION_PATH,
        rpg_runtime_frontend_posture_path=questbook_surface.RPG_RUNTIME_FRONTEND_POSTURE_PATH,
        rpg_runtime_collections_path=questbook_surface.RPG_RUNTIME_COLLECTIONS_PATH,
        rpg_runtime_builders_path=questbook_surface.RPG_RUNTIME_BUILDERS_PATH,
        rpg_route_api_seam_path=questbook_surface.RPG_ROUTE_API_SEAM_PATH,
        rpg_frontend_projection_seam_path=questbook_surface.RPG_FRONTEND_PROJECTION_SEAM_PATH,
        quest_schema_path=questbook_surface.QUEST_SCHEMA_PATH,
        quest_dispatch_schema_path=questbook_surface.QUEST_DISPATCH_SCHEMA_PATH,
        agent_build_snapshot_schema_path=questbook_surface.AGENT_BUILD_SNAPSHOT_SCHEMA_PATH,
        reputation_ledger_schema_path=questbook_surface.REPUTATION_LEDGER_SCHEMA_PATH,
        quest_run_result_schema_path=questbook_surface.QUEST_RUN_RESULT_SCHEMA_PATH,
        frontend_projection_bundle_schema_path=questbook_surface.FRONTEND_PROJECTION_BUNDLE_SCHEMA_PATH,
        agent_build_snapshot_collection_schema_path=questbook_surface.AGENT_BUILD_SNAPSHOT_COLLECTION_SCHEMA_PATH,
        reputation_ledger_collection_schema_path=questbook_surface.REPUTATION_LEDGER_COLLECTION_SCHEMA_PATH,
        quest_run_result_collection_schema_path=questbook_surface.QUEST_RUN_RESULT_COLLECTION_SCHEMA_PATH,
        frontend_projection_bundle_collection_schema_path=questbook_surface.FRONTEND_PROJECTION_BUNDLE_COLLECTION_SCHEMA_PATH,
        quest_catalog_example_path=questbook_surface.QUEST_CATALOG_EXAMPLE_PATH,
        quest_dispatch_example_path=questbook_surface.QUEST_DISPATCH_EXAMPLE_PATH,
        agent_build_snapshot_example_path=questbook_surface.AGENT_BUILD_SNAPSHOT_EXAMPLE_PATH,
        reputation_ledger_example_path=questbook_surface.REPUTATION_LEDGER_EXAMPLE_PATH,
        quest_run_result_example_path=questbook_surface.QUEST_RUN_RESULT_EXAMPLE_PATH,
        frontend_projection_bundle_example_path=questbook_surface.FRONTEND_PROJECTION_BUNDLE_EXAMPLE_PATH,
        generated_agent_build_snapshots_path=questbook_surface.GENERATED_AGENT_BUILD_SNAPSHOTS_PATH,
        generated_reputation_ledgers_path=questbook_surface.GENERATED_REPUTATION_LEDGERS_PATH,
        generated_quest_run_results_path=questbook_surface.GENERATED_QUEST_RUN_RESULTS_PATH,
        generated_frontend_projection_bundles_path=questbook_surface.GENERATED_FRONTEND_PROJECTION_BUNDLES_PATH,
        quest_surface_root=questbook_surface.QUEST_SURFACE_ROOT,
        quest_ids=quest_surface.QUEST_IDS,
        quest_routes=quest_surface.QUEST_ROUTES,
        questbook_required_tokens=questbook_surface.QUESTBOOK_REQUIRED_TOKENS,
        questbook_forbidden_tokens=questbook_surface.QUESTBOOK_FORBIDDEN_TOKENS,
        questbook_integration_required_tokens=questbook_surface.QUESTBOOK_INTEGRATION_REQUIRED_TOKENS,
        questbook_integration_forbidden_tokens=questbook_surface.QUESTBOOK_INTEGRATION_FORBIDDEN_TOKENS,
        quest_schema_required_fields=questbook_surface.QUEST_SCHEMA_REQUIRED_FIELDS,
        quest_dispatch_required_fields=questbook_surface.QUEST_DISPATCH_REQUIRED_FIELDS,
        closed_quest_states=questbook_surface.CLOSED_QUEST_STATES,
        load_structured_object_func=_load_structured_object,
        quest_source_path_func=quest_surface.quest_source_path,
        build_expected_quest_catalog_entry_func=quest_surface.build_expected_quest_catalog_entry,
        build_expected_quest_dispatch_entry_func=quest_surface.build_expected_quest_dispatch_entry,
    )
    machine_fit.validate_reference_platform(errors, root=ROOT)
    machine_fit.validate_machine_bridge(errors, root=ROOT)
    machine_fit.validate_machine_integration_freshness_gates(errors, root=ROOT)
    machine_fit.validate_platform_adaptations(errors, root=ROOT)
    branch_policy.validate_branch_policy(errors, root=ROOT)
    federation_runtime_seams.validate_memo_runtime_seam(errors, root=ROOT)
    federation_runtime_seams.validate_eval_runtime_seam(
        errors,
        root=ROOT,
        bridge_config_loader=lambda bridge_errors: federation_surface.compatibility_bridge_config(
            bridge_errors,
            bridge_path=ROOT / federation_surface.UPSTREAM_COMPATIBILITY_BRIDGE_PATH,
        ),
        bridge_string_iterator=federation_surface.iter_compatibility_bridge_strings,
    )
    federation_runtime_seams.validate_playbook_runtime_seam(errors, root=ROOT)
    federation_runtime_seams.validate_kag_runtime_seam(errors, root=ROOT)
    return_policy.validate_return_runtime_contract(errors, root=ROOT)
    runtime_hygiene.validate_runtime_hygiene_contracts(errors, root=ROOT)
    diagnostic_spine.validate_diagnostic_spine_contracts(
        errors,
        root=ROOT,
        overlay_skill_surfaces=agent_skill_projection.DIAGNOSTIC_OVERLAY_SKILL_SURFACES,
        overlay_skill_validator=_overlay_skill_surface_validator,
    )
    service_selection.validate_service_selection_policy(
        errors,
        root=ROOT,
        policy_path=service_selection.SERVICE_SELECTION_POLICY_PATH,
        required_services=service_selection.SERVICE_SELECTION_POLICY_REQUIRED_SERVICES,
        allowed_postures=service_selection.SERVICE_SELECTION_POLICY_ALLOWED_POSTURES,
        preset_dir=ROOT / profile_topology.PRESET_DIR,
        profile_dir=ROOT / profile_topology.PROFILE_DIR,
        module_dir=ROOT / profile_topology.MODULE_DIR,
        load_names_func=_load_names,
        compose_service_names_func=_compose_service_names,
        required_runtime_profiles={"federation", "reranking", "rag"},
        required_runtime_overlays=(
            "compose/tuning/storage.intel-285h.resource-guard.yml",
            "compose/tuning/rag.thin-host.yml",
        ),
        unexpected_selected_services={"n8n", "n8n-task-runners", "ollama", "litellm", "babelvox-tts"},
        expected_selected_services={
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
        },
        selection_doc_paths=(
            Path("docs") / "runtime" / "SERVICE_SELECTION.md",
            Path("docs") / "runtime" / "README.md",
        ),
    )
    service_selection.validate_service_screenshot_inventory(
        errors,
        root=ROOT,
        inventory_path=service_selection.SERVICE_SCREENSHOT_INVENTORY_PATH,
        policy_path=service_selection.SERVICE_SELECTION_POLICY_PATH,
        required_screenshot_services=service_selection.SERVICE_SCREENSHOT_INVENTORY_REQUIRED_SERVICES,
        expected_addon_services=("rerank-api", "rag-api", "loki", "tempo", "alloy"),
        selection_doc_paths=(
            Path("docs") / "runtime" / "SERVICE_SELECTION.md",
            Path("docs") / "runtime" / "README.md",
        ),
    )
    federation_surface.validate_federation_landing(errors, root=ROOT)


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
        sync_parity.validate_runtime_configs_mirror(errors, root=ROOT)
        if errors:
            print("validation failed:")
            for error in errors:
                print(f"- {error}")
            return 1

        print("validation passed (runtime Configs mirror mode)")
        return 0

    _run_source_validators(errors)
    if args.parity_check:
        sync_parity.validate_deployed_parity(
            errors,
            root=ROOT,
            deployed_root=Path(args.deployed_configs_root),
            sync_file_iter_func=_iter_sync_managed_files,
        )

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
