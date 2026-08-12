from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = REPO_ROOT / "docs" / "validation" / "script_inventory.json"


def load_inventory() -> dict[str, object]:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def tracked_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return {
        path
        for path in result.stdout.splitlines()
        if (REPO_ROOT / path).exists()
    }


def inventory_paths() -> set[str]:
    paths: set[str] = set()
    for entry in load_inventory()["script_surfaces"]:
        paths.update(entry["paths"])
    return paths


def test_script_inventory_entries_have_required_fields_and_existing_paths() -> None:
    inventory = load_inventory()
    required = set(inventory["required_fields"])

    for entry in inventory["script_surfaces"]:
        assert required <= set(entry), entry
        assert entry["paths"], entry
        for relative in entry["paths"]:
            assert (REPO_ROOT / relative).exists(), relative


def test_tracked_script_surfaces_are_inventory_covered() -> None:
    script_paths = {
        path
        for path in tracked_files()
        if (path.startswith("scripts/") or "/scripts/" in path)
        and "/legacy/" not in path
        and "__pycache__" not in path
        and not path.endswith(".pyc")
    }

    assert script_paths <= inventory_paths()


def test_no_tracked_python_cache_under_script_surfaces() -> None:
    offenders = [
        path
        for path in tracked_files()
        if (path.startswith("scripts/") or "/scripts/" in path)
        and "/legacy/" not in path
        and ("__pycache__" in path or path.endswith(".pyc"))
    ]

    assert offenders == []


def test_operator_scripts_keep_side_effect_posture_visible() -> None:
    inventory = load_inventory()
    operator = next(
        entry
        for entry in inventory["script_surfaces"]
        if entry["family"] == "root-operator-command-surface"
    )

    assert "side_effects" in operator
    assert "explicit flags" in operator["side_effects"]
    assert operator["validation_lane"] == "source-fast/shellcheck/release"


def test_external_codex_operator_wrapper_is_inventory_routed() -> None:
    operator = next(
        entry
        for entry in load_inventory()["script_surfaces"]
        if entry["family"] == "root-operator-command-surface"
    )

    assert "scripts/aoa-external-codex-agent" in operator["paths"]
    assert "scripts/aoa-external-actor-bind" in operator["paths"]


def test_focused_validator_modules_are_script_inventory_covered() -> None:
    root_validation = next(
        entry
        for entry in load_inventory()["script_surfaces"]
        if entry["family"] == "root-validation-and-generated-entrypoints"
    )

    assert "scripts/validators/federation_runtime_seams.py" in root_validation["paths"]
    assert "scripts/validators/active_topology_language.py" in root_validation["paths"]
    assert "scripts/validators/agent_skill_projection.py" in root_validation["paths"]
    assert "scripts/validators/branch_policy.py" in root_validation["paths"]
    assert "scripts/validators/decision_surface.py" in root_validation["paths"]
    assert "scripts/validators/diagnostic_spine.py" in root_validation["paths"]
    assert "scripts/validators/federation_surface.py" in root_validation["paths"]
    assert "scripts/validators/inference_pilot_compatibility.py" in root_validation["paths"]
    assert "scripts/validators/machine_fit.py" in root_validation["paths"]
    assert "scripts/validators/mechanics_topology.py" in root_validation["paths"]
    assert "scripts/validators/profile_topology.py" in root_validation["paths"]
    assert "scripts/validators/script_surface.py" in root_validation["paths"]
    assert "scripts/validators/questbook_surface.py" in root_validation["paths"]
    assert "scripts/validators/return_policy.py" in root_validation["paths"]
    assert "scripts/validators/root_routes.py" in root_validation["paths"]
    assert "scripts/validators/runtime_route_contracts.py" in root_validation["paths"]
    assert "scripts/validators/runtime_hygiene.py" in root_validation["paths"]
    assert "scripts/validators/service_selection.py" in root_validation["paths"]
    assert "scripts/validators/source_hygiene.py" in root_validation["paths"]
    assert "scripts/validators/source_structure.py" in root_validation["paths"]
    assert "scripts/validators/sync_parity.py" in root_validation["paths"]
    assert "scripts/run_pytest_lane.py" in root_validation["paths"]


def test_inference_pilot_runners_are_active_package_local_bridges() -> None:
    inventory = load_inventory()
    runners = next(
        entry
        for entry in inventory["script_surfaces"]
        if entry["family"] == "inference-pilot-compatibility-runners"
    )

    assert runners["disposition"] == "keep"
    assert runners["validation_lane"] == "source-fast/release"
    assert all("/legacy/" not in path for path in runners["paths"])
