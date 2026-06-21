from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_DIR = REPO_ROOT / "docs" / "validation"


def load_inventory() -> dict[str, object]:
    return json.loads((VALIDATION_DIR / "validator_inventory.json").read_text(encoding="utf-8"))


def tracked_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return set(result.stdout.splitlines())


def load_runtime_config_bundle_validator():
    script = (
        REPO_ROOT
        / "mechanics"
        / "config-projection"
        / "parts"
        / "rendering"
        / "scripts"
        / "validate_abyss_machine_runtime_config_bundle.py"
    )
    spec = importlib.util.spec_from_file_location("abyss_stack_runtime_config_bundle_validator", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def covered_paths(inventory: dict[str, object]) -> set[str]:
    paths: set[str] = set()
    for entry in inventory["entries"]:
        paths.update(entry["paths"])
    return paths


def test_validation_docs_and_manifest_exist() -> None:
    for relative in (
        "AGENTS.md",
        "README.md",
        "VALIDATOR_TOPOLOGY.md",
        "COMMAND_AUTHORITY.md",
        "SCRIPT_TOPOLOGY.md",
        "validation_lanes.json",
        "validator_inventory.json",
        "script_inventory.json",
    ):
        assert (VALIDATION_DIR / relative).is_file(), relative


def test_validator_inventory_entries_have_required_fields_and_existing_paths() -> None:
    inventory = load_inventory()
    required = set(inventory["required_fields"])

    for entry in inventory["entries"]:
        assert required <= set(entry), entry
        assert entry["paths"], entry
        for relative in entry["paths"]:
            assert (REPO_ROOT / relative).exists(), relative


def test_validation_like_entrypoints_are_in_inventory() -> None:
    inventory = load_inventory()
    covered = covered_paths(inventory)
    validation_like = {
        path
        for path in tracked_files()
        if re.search(r"(^|/)(validate[^/]*|release_check|ci_gate|validation_lanes)\.py$", path)
        or path
        in {
            "scripts/generate_decision_indexes.py",
            "scripts/build_diagnostic_surface_catalog.py",
            "scripts/decision_indexes.py",
        }
    }

    assert validation_like <= covered


def test_runtime_config_bundle_hashes_rendered_subject() -> None:
    manifest_path = (
        REPO_ROOT
        / "mechanics"
        / "config-projection"
        / "parts"
        / "rendering"
        / "manifests"
        / "runtime_config.bundle.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["abi_subject"]["path"] == "dist/abyss-stack-runtime-config/substrate.rendered.yml"
    assert manifest["artifact_subjects"] == [
        {
            "path": "dist/abyss-stack-runtime-config/substrate.rendered.yml",
            "role": "rendered_runtime_config",
        }
    ]
    assert manifest["lifecycle"]["latest_eligible_states"] == [
        "manually-verified",
        "release-ready",
        "published",
    ]
    assert manifest["consumer_contract"]["registry_required"] is True


def test_runtime_config_bundle_validator_reports_external_paths(tmp_path: Path) -> None:
    validator = load_runtime_config_bundle_validator()

    assert validator._path_ref(REPO_ROOT / "dist" / "bundle") == "dist/bundle"
    assert validator._path_ref(tmp_path / "bundle") == str((tmp_path / "bundle").resolve())


def test_runtime_config_bundle_validator_sanitizes_public_verify_sidecar(tmp_path: Path) -> None:
    validator = load_runtime_config_bundle_validator()
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    sidecar = bundle_dir / "artifact.verify.json"
    sidecar.write_text(
        json.dumps(
            {
                "artifact_subject_resolution": [
                    {
                        "path": "dist/abyss-stack-runtime-config/substrate.rendered.yml",
                        "resolved_path": str(REPO_ROOT / "dist" / "abyss-stack-runtime-config" / "substrate.rendered.yml"),
                        "ok": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    validator._sanitize_public_verify_sidecar(bundle_dir)
    payload = json.loads(sidecar.read_text(encoding="utf-8"))

    assert payload["artifact_subject_resolution"][0]["resolved_path"] == "dist/abyss-stack-runtime-config/substrate.rendered.yml"


def test_root_validator_is_marked_as_orchestrator() -> None:
    inventory = load_inventory()
    entries = [entry for entry in inventory["entries"] if "scripts/validate_stack.py" in entry["paths"]]

    assert len(entries) == 1
    assert entries[0]["mode"] == "blocking-orchestrator"
    assert "root orchestration glue" in entries[0]["failure_route"]
    assert "do not reintroduce validate_stack wrapper APIs" in entries[0]["failure_route"]


def test_script_surface_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/script_surface.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "script-surface-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_source_hygiene_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/source_hygiene.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "source-hygiene-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_source_structure_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/source_structure.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "source-structure-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_mechanics_topology_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/mechanics_topology.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "mechanics-topology-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_profile_topology_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/profile_topology.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "profile-topology-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_runtime_route_contracts_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/runtime_route_contracts.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "runtime-route-contracts-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_inference_pilot_compatibility_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/inference_pilot_compatibility.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "inference-pilot-compatibility-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_active_topology_language_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/active_topology_language.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "active-topology-language-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_agent_skill_projection_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/agent_skill_projection.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "agent-skill-projection-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_service_selection_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/service_selection.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "service-selection-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_sync_parity_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/sync_parity.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "sync-parity-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_questbook_surface_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/questbook_surface.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "questbook-surface-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_federation_surface_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/federation_surface.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "federation-surface-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_federation_runtime_seams_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/federation_runtime_seams.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "federation-runtime-seams-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_diagnostic_spine_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/diagnostic_spine.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "diagnostic-spine-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_runtime_hygiene_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/runtime_hygiene.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "runtime-hygiene-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_machine_fit_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/machine_fit.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "machine-fit-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_return_policy_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/return_policy.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "return-policy-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_branch_policy_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/branch_policy.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "branch-policy-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_root_routes_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/root_routes.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "root-routes-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_decision_surface_module_is_inventory_owned() -> None:
    inventory = load_inventory()
    entries = [
        entry
        for entry in inventory["entries"]
        if "scripts/validators/decision_surface.py" in entry["paths"]
    ]

    assert len(entries) == 1
    assert entries[0]["family"] == "decision-surface-validator-module"
    assert entries[0]["mode"] == "blocking-owner-module"


def test_command_authority_keeps_inventories_descriptive() -> None:
    command_authority = (VALIDATION_DIR / "COMMAND_AUTHORITY.md").read_text(encoding="utf-8")

    assert "inventories" in command_authority
    assert "descriptive" in command_authority
    assert "validation_lanes.json" in command_authority
