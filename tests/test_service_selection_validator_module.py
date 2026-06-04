from __future__ import annotations

import json
from pathlib import Path

from scripts.validators import service_selection


POLICY_PATH = Path("docs") / "runtime" / "service-selection-policy.v1.json"
INVENTORY_PATH = Path("docs") / "runtime" / "service-inventory-2026-05-14.v1.json"
SELECTION_DOCS = (
    Path("docs") / "runtime" / "SERVICE_SELECTION.md",
    Path("docs") / "runtime" / "README.md",
)


def write_text(root: Path, relative: str | Path, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_names(path: Path) -> list[str]:
    return [
        line.split("#", 1)[0].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]


def compose_service_names(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def write_minimal_runtime_shape(root: Path) -> None:
    write_text(root, "compose/presets/intel-full.txt", "core\n")
    write_text(root, "compose/profiles/core.txt", "db.yml\n")
    write_text(root, "compose/modules/db.yml", "postgres\nredis\n")
    write_text(root, "compose/tuning/guard.yml", "# guard\n")
    for doc_path in SELECTION_DOCS:
        write_text(
            root,
            doc_path,
            f"{POLICY_PATH.name}\n{INVENTORY_PATH.name}\n",
        )


def selected_service(name: str, *, resource_guard: str = "compose/tuning/guard.yml") -> dict[str, str]:
    return {
        "name": name,
        "module": "compose/modules/db.yml",
        "owner_profile": "core",
        "posture": "selected_now",
        "tier": "core",
        "decision": "ABYSS-STACK-D-test",
        "resource_guard": resource_guard,
    }


def write_policy(root: Path, services: list[dict[str, str]]) -> None:
    write_text(
        root,
        POLICY_PATH,
        json.dumps(
            {
                "schema": "abyss_stack_service_selection_policy_v1",
                "current_runtime_shape": {
                    "preset": "intel-full",
                    "profiles": ["core"],
                    "overlays": ["compose/tuning/guard.yml"],
                },
                "services": services,
            }
        ),
    )


def validate_policy(root: Path, errors: list[str]) -> None:
    service_selection.validate_service_selection_policy(
        errors,
        root=root,
        policy_path=POLICY_PATH,
        required_services={"postgres", "redis"},
        allowed_postures={"selected_now", "explicit_opt_in"},
        preset_dir=root / "compose" / "presets",
        profile_dir=root / "compose" / "profiles",
        module_dir=root / "compose" / "modules",
        load_names_func=load_names,
        compose_service_names_func=compose_service_names,
        required_runtime_profiles={"core"},
        required_runtime_overlays=("compose/tuning/guard.yml",),
        unexpected_selected_services={"n8n"},
        expected_selected_services={"postgres", "redis"},
        selection_doc_paths=SELECTION_DOCS,
    )


def test_service_selection_policy_module_accepts_matching_runtime_shape(tmp_path: Path) -> None:
    write_minimal_runtime_shape(tmp_path)
    write_policy(tmp_path, [selected_service("postgres"), selected_service("redis")])

    errors: list[str] = []
    validate_policy(tmp_path, errors)

    assert errors == []


def test_service_selection_policy_module_requires_selected_resource_guard(tmp_path: Path) -> None:
    write_minimal_runtime_shape(tmp_path)
    write_policy(tmp_path, [selected_service("postgres", resource_guard=""), selected_service("redis")])

    errors: list[str] = []
    validate_policy(tmp_path, errors)

    assert (
        "docs/runtime/service-selection-policy.v1.json selected service postgres must name a resource guard"
        in errors
    )


def test_service_screenshot_inventory_module_aligns_addons_with_policy(tmp_path: Path) -> None:
    write_minimal_runtime_shape(tmp_path)
    write_policy(
        tmp_path,
        [
            selected_service("postgres"),
            selected_service("redis"),
            selected_service("rag-api"),
            {
                "name": "qdrant",
                "module": "compose/modules/db.yml",
                "owner_profile": "core",
                "posture": "explicit_opt_in",
                "tier": "optional",
                "decision": "ABYSS-STACK-D-test",
                "resource_guard": "",
            },
        ],
    )
    write_text(
        tmp_path,
        INVENTORY_PATH,
        json.dumps(
            {
                "schema": "abyss_stack_runtime_service_inventory_v1",
                "policy_companion": POLICY_PATH.as_posix(),
                "source_screenshot": {
                    "absolute_path": "/tmp/2026-05-14 21-46-49.png",
                    "size_bytes": 64281,
                    "extraction_method": "manual_visual_review",
                },
                "screenshotted_services": ["postgres", "redis"],
                "screenshotted_groups": [
                    {"group": "core", "services": ["postgres", "redis"]}
                ],
                "current_selected_addons": [{"service": "rag-api"}],
                "known_policy_services_not_in_screenshot": ["qdrant"],
            }
        ),
    )

    errors: list[str] = []
    service_selection.validate_service_screenshot_inventory(
        errors,
        root=tmp_path,
        inventory_path=INVENTORY_PATH,
        policy_path=POLICY_PATH,
        required_screenshot_services={"postgres", "redis"},
        expected_addon_services={"rag-api"},
        selection_doc_paths=SELECTION_DOCS,
    )

    assert errors == []
