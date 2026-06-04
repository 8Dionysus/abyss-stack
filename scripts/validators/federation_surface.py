from __future__ import annotations

from collections.abc import Callable, Mapping, Set
import json
from pathlib import Path
from typing import Any

StructuredObjectLoader = Callable[[Path], dict[str, object]]
TextReader = Callable[[Path], str | None]

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
        "generated/playbook_registry.min.json",
        "generated/playbook_activation_surfaces.min.json",
        "generated/playbook_federation_surfaces.min.json",
        "generated/playbook_review_status.min.json",
        "generated/playbook_review_packet_contracts.min.json",
        "generated/playbook_review_intake.min.json",
        "generated/playbook_handoff_contracts.json",
        "generated/playbook_failure_catalog.json",
        "generated/playbook_subagent_recipes.json",
        "generated/playbook_composition_manifest.json",
        "schemas/playbook-registry.schema.json",
    },
}
UPSTREAM_COMPATIBILITY_BRIDGE_PATH = (
    Path("config-templates") / "Configs" / "federation" / "upstream-compatibility-bridge.json"
)


def compatibility_bridge_config(
    errors: list[str],
    *,
    bridge_path: Path,
) -> dict[str, Any]:
    try:
        payload = json.loads(bridge_path.read_text(encoding="utf-8"))
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


def validate_federation_required_files(
    errors: list[str],
    *,
    root: Path,
    required_runtime_inputs: Mapping[Path, Set[str]],
    bridge_path: Path,
    load_structured_object_func: StructuredObjectLoader,
) -> None:
    for rel_path, expected_refs in required_runtime_inputs.items():
        path = root / rel_path
        try:
            payload = load_structured_object_func(path)
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

    bridge = compatibility_bridge_config(errors, bridge_path=bridge_path)
    _validate_runtime_evidence_templates(errors, bridge=bridge)
    _validate_playbook_bridge(errors, bridge=bridge)


def validate_federation_upstream_compatibility(
    errors: list[str],
    *,
    root: Path,
    bridge_path: Path,
    read_text_func: TextReader,
) -> None:
    verdict_path = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "docs"
        / "UPSTREAM_COMPATIBILITY.md"
    )
    readme_path = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "README.md"
    )
    parts_path = root / "mechanics" / "federation-seams" / "PARTS.md"
    legacy_index_path = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "legacy"
        / "upstream-compatibility"
        / "INDEX.md"
    )

    verdict = read_text_func(verdict_path) or ""
    readme = read_text_func(readme_path) or ""
    parts = read_text_func(parts_path) or ""
    legacy_index = read_text_func(legacy_index_path) or ""
    evals_config = read_text_func(root / "config-templates" / "Configs" / "federation" / "aoa-evals.yaml") or ""
    playbooks_config = (
        read_text_func(root / "config-templates" / "Configs" / "federation" / "aoa-playbooks.yaml") or ""
    )
    bridge_config = compatibility_bridge_config(errors, bridge_path=bridge_path)
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
                f"{path.relative_to(root)} must route upstream compatibility names through UPSTREAM_COMPATIBILITY.md"
            )
    if "phase-alpha" in evals_config:
        errors.append("aoa-evals federation config must keep upstream memo template names in the bridge config")
    if "playbook_automation_seeds" in playbooks_config:
        errors.append("aoa-playbooks federation config must keep upstream automation file names in the bridge config")


def validate_federation_landing(errors: list[str], *, root: Path) -> None:
    templates_readme = (root / "config-templates" / "README.md").read_text(encoding="utf-8")
    if "Configs/federation/" not in templates_readme:
        errors.append("config-templates/README.md must mention Configs/federation/")
    if "Services/aoa-browser/" not in templates_readme:
        errors.append("config-templates/README.md must mention Services/aoa-browser/")
    if "Services/route-api/" not in templates_readme:
        errors.append("config-templates/README.md must mention Services/route-api/")

    services_readme = (root / "config-templates" / "Services" / "README.md").read_text(encoding="utf-8")
    if "aoa-browser/" not in services_readme:
        errors.append("config-templates/Services/README.md must mention aoa-browser/")
    if "aoa-browser/ms-playwright/" not in services_readme:
        errors.append("config-templates/Services/README.md must mention aoa-browser/ms-playwright/")
    if "route-api/" not in services_readme:
        errors.append("config-templates/Services/README.md must mention route-api/")

    storage_layout_doc = (root / "docs" / "runtime" / "STORAGE_LAYOUT.md").read_text(encoding="utf-8")
    if "Knowledge/federation" not in storage_layout_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Knowledge/federation")
    if "source-managed build context" not in storage_layout_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention the aoa-browser source-managed build context")
    if "Services/aoa-browser/ms-playwright/" not in storage_layout_doc:
        errors.append("docs/runtime/STORAGE_LAYOUT.md must mention Services/aoa-browser/ms-playwright/")

    deployment_doc = (root / "docs" / "install" / "DEPLOYMENT.md").read_text(encoding="utf-8")
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

    paths_doc = (root / "docs" / "runtime" / "PATHS.md").read_text(encoding="utf-8")
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

    service_catalog_doc = (root / "docs" / "runtime" / "SERVICE_CATALOG.md").read_text(encoding="utf-8")
    if "43-federation-router.yml" not in service_catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention 43-federation-router.yml")
    if "route-api" not in service_catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention route-api")
    if "POST /run/federated" not in service_catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must mention POST /run/federated")
    if "`abyss_default`" not in service_catalog_doc:
        errors.append("docs/runtime/SERVICE_CATALOG.md must explain the sidecar route-api network attachment")

    profiles_doc = (root / "docs" / "profiles" / "PROFILES.md").read_text(encoding="utf-8")
    if "`federation`" not in profiles_doc:
        errors.append("docs/profiles/PROFILES.md must mention the federation profile")
    if "AOA_FEDERATED_RUN_ENABLED=true" not in profiles_doc:
        errors.append("docs/profiles/PROFILES.md must explain when AOA_FEDERATED_RUN_ENABLED=true is required")

    profile_recipes_doc = (root / "docs" / "profiles" / "PROFILE_RECIPES.md").read_text(encoding="utf-8")
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

    runbook_doc = (root / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-federated-check" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-federated-check for the live federated advisory seam")
    if "--playbook-id AOA-P-0008" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must show aoa-federated-check --playbook-id AOA-P-0008 for the first playbook advisory consumer path")
    if "--inspect-id AOA-K-0011" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must show aoa-federated-check --inspect-id AOA-K-0011 for the first retrieval-only consumer path")
    if "--memo-id AOA-M-0001" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must show aoa-federated-check --memo-id AOA-M-0001 for the first memo advisory consumer path")


def _validate_runtime_evidence_templates(
    errors: list[str],
    *,
    bridge: dict[str, Any],
) -> None:
    runtime_templates = bridge.get("runtime_evidence_templates", {})
    if not isinstance(runtime_templates, dict) or not runtime_templates:
        errors.append("upstream compatibility bridge must list runtime_evidence_templates")
        return

    for route in ("memo-recall-rerun", "memo-contradiction-gap", "memo-contradiction-rerun"):
        entry = runtime_templates.get(route)
        if not isinstance(entry, dict):
            errors.append(f"upstream compatibility bridge must list runtime template {route}")
            continue
        for key in ("canonical_selection_id", "local_source_ref", "upstream_source_ref", "upstream_selection_id"):
            if not isinstance(entry.get(key), str) or not entry.get(key):
                errors.append(f"upstream compatibility bridge runtime template {route} must include {key}")


def _validate_playbook_bridge(
    errors: list[str],
    *,
    bridge: dict[str, Any],
) -> None:
    playbook_bridge = bridge.get("playbook_automation_plans")
    if not isinstance(playbook_bridge, dict):
        errors.append("upstream compatibility bridge must list playbook automation plan bridge")
        return
    for key in (
        "owner_repo",
        "local_collection_route",
        "local_item_route",
        "upstream_source_ref",
        "upstream_rel_path",
        "compatibility_collection_route",
        "compatibility_item_route",
    ):
        if not isinstance(playbook_bridge.get(key), str) or not playbook_bridge.get(key):
            errors.append(f"upstream compatibility bridge playbook automation plan bridge must include {key}")
    upstream_source_ref = playbook_bridge.get("upstream_source_ref")
    upstream_rel_path = playbook_bridge.get("upstream_rel_path")
    if (
        isinstance(upstream_source_ref, str)
        and isinstance(upstream_rel_path, str)
        and not upstream_source_ref.endswith(upstream_rel_path)
    ):
        errors.append("upstream compatibility bridge playbook automation upstream_source_ref must end with upstream_rel_path")
