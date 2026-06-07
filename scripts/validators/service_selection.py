from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence, Set
import json
from pathlib import Path
from typing import Any

NameLoader = Callable[[Path], list[str]]
ComposeServiceLoader = Callable[[Path], set[str]]

SERVICE_SELECTION_POLICY_PATH = Path("docs") / "runtime" / "service-selection-policy.v1.json"
SERVICE_SCREENSHOT_INVENTORY_PATH = Path("docs") / "runtime" / "service-inventory-2026-05-14.v1.json"
SERVICE_SELECTION_POLICY_REQUIRED_SERVICES = {
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
    "qwen-tts",
    "tts-router",
    "docs-api",
    "aoa-browser",
    "prometheus",
    "grafana",
    "alertmanager",
    "cadvisor",
    "loki",
    "alloy",
    "n8n",
    "n8n-task-runners",
    "ollama",
    "litellm",
    "tos-graph",
    "babelvox-tts",
    "langchain-api-llamacpp",
}
SERVICE_SELECTION_POLICY_ALLOWED_POSTURES = {
    "selected_now",
    "explicit_opt_in",
    "fallback_control",
    "lab_only",
    "not_selected",
}
SERVICE_SCREENSHOT_INVENTORY_REQUIRED_SERVICES = {
    "postgres",
    "redis",
    "qdrant",
    "neo4j",
    "llama-cpp",
    "langchain-api",
    "ovms",
    "route-api",
    "n8n",
    "n8n-task-runners",
    "qwen-tts",
    "tts-router",
    "docs-api",
    "aoa-browser",
    "prometheus",
    "grafana",
    "alertmanager",
    "cadvisor",
}


def validate_service_selection_policy(
    errors: list[str],
    *,
    root: Path,
    policy_path: Path,
    required_services: Set[str],
    allowed_postures: Set[str],
    preset_dir: Path,
    profile_dir: Path,
    module_dir: Path,
    load_names_func: NameLoader,
    compose_service_names_func: ComposeServiceLoader,
    required_runtime_profiles: Set[str],
    required_runtime_overlays: Sequence[str],
    unexpected_selected_services: Set[str],
    expected_selected_services: Set[str],
    selection_doc_paths: Sequence[Path],
) -> None:
    absolute_policy_path = root / policy_path
    if not absolute_policy_path.is_file():
        errors.append(f"{policy_path.as_posix()} is required")
        return

    try:
        policy = json.loads(absolute_policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{policy_path.as_posix()} must be valid JSON: {exc}")
        return

    if not isinstance(policy, dict):
        errors.append(f"{policy_path.as_posix()} must contain a JSON object")
        return

    if policy.get("schema") != "abyss_stack_service_selection_policy_v1":
        errors.append(f"{policy_path.as_posix()} must use schema abyss_stack_service_selection_policy_v1")

    runtime_shape = policy.get("current_runtime_shape")
    if not isinstance(runtime_shape, dict):
        errors.append(f"{policy_path.as_posix()} must include current_runtime_shape")
    else:
        _validate_runtime_shape(
            errors,
            root=root,
            policy_path=policy_path,
            runtime_shape=runtime_shape,
            required_runtime_profiles=required_runtime_profiles,
            required_runtime_overlays=required_runtime_overlays,
        )

    services = policy.get("services")
    if not isinstance(services, list) or not services:
        errors.append(f"{policy_path.as_posix()} must include a non-empty services list")
        return

    seen_names: set[str] = set()
    selected_now: set[str] = set()
    _validate_service_entries(
        errors,
        root=root,
        policy_path=policy_path,
        services=services,
        allowed_postures=allowed_postures,
        seen_names=seen_names,
        selected_now=selected_now,
    )

    missing_services = sorted(required_services - seen_names)
    if missing_services:
        errors.append(f"{policy_path.as_posix()} missing required services: {', '.join(missing_services)}")

    for unexpected_selected in sorted(unexpected_selected_services):
        if unexpected_selected in selected_now:
            errors.append(f"{policy_path.as_posix()} must not mark {unexpected_selected} as selected_now")

    for expected_selected in sorted(expected_selected_services):
        if expected_selected not in selected_now:
            errors.append(f"{policy_path.as_posix()} must mark {expected_selected} as selected_now")

    runtime_shape_services = _runtime_shape_services(
        runtime_shape=runtime_shape,
        preset_dir=preset_dir,
        profile_dir=profile_dir,
        module_dir=module_dir,
        load_names_func=load_names_func,
        compose_service_names_func=compose_service_names_func,
    )
    if runtime_shape_services:
        missing_from_runtime_shape = sorted(selected_now - runtime_shape_services)
        if missing_from_runtime_shape:
            errors.append(
                f"{policy_path.as_posix()} marks services selected_now that are not in the current runtime shape: {', '.join(missing_from_runtime_shape)}"
            )
        missing_from_policy_selection = sorted(runtime_shape_services - selected_now)
        if missing_from_policy_selection:
            errors.append(
                f"{policy_path.as_posix()} current runtime shape services must be marked selected_now: {', '.join(missing_from_policy_selection)}"
            )

    for relative_path in selection_doc_paths:
        text = (root / relative_path).read_text(encoding="utf-8")
        if policy_path.name not in text:
            errors.append(f"{relative_path.as_posix()} must mention {policy_path.name}")


def _validate_runtime_shape(
    errors: list[str],
    *,
    root: Path,
    policy_path: Path,
    runtime_shape: dict[str, Any],
    required_runtime_profiles: Set[str],
    required_runtime_overlays: Sequence[str],
) -> None:
    if runtime_shape.get("preset") != "intel-full":
        errors.append(f"{policy_path.as_posix()} current runtime preset must remain intel-full")
    profiles = runtime_shape.get("profiles")
    if not isinstance(profiles, list) or not required_runtime_profiles.issubset(set(profiles)):
        required = ", ".join(sorted(required_runtime_profiles))
        errors.append(f"{policy_path.as_posix()} current runtime profiles must include {required}")
    overlays = runtime_shape.get("overlays")
    if not isinstance(overlays, list) or not overlays:
        errors.append(f"{policy_path.as_posix()} current runtime overlays must be a non-empty list")
    else:
        for required_overlay in required_runtime_overlays:
            if required_overlay not in overlays:
                overlay_name = Path(required_overlay).stem.replace(".", " ")
                errors.append(f"{policy_path.as_posix()} current runtime overlays must include the {overlay_name}")
        for overlay in overlays:
            if not isinstance(overlay, str) or not overlay:
                errors.append(f"{policy_path.as_posix()} overlays must be non-empty strings")
                continue
            if not (root / overlay).is_file():
                errors.append(f"{policy_path.as_posix()} overlay path is missing: {overlay}")


def _validate_service_entries(
    errors: list[str],
    *,
    root: Path,
    policy_path: Path,
    services: list[object],
    allowed_postures: Set[str],
    seen_names: set[str],
    selected_now: set[str],
) -> None:
    for index, entry in enumerate(services):
        if not isinstance(entry, dict):
            errors.append(f"{policy_path.as_posix()} service entry {index} must be an object")
            continue

        name = entry.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{policy_path.as_posix()} service entry {index} must include name")
            continue
        if name in seen_names:
            errors.append(f"{policy_path.as_posix()} has duplicate service: {name}")
        seen_names.add(name)

        for field in ("module", "owner_profile", "posture", "tier", "decision"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{policy_path.as_posix()} service {name} must include non-empty {field}")

        posture = entry.get("posture")
        if isinstance(posture, str) and posture not in allowed_postures:
            errors.append(f"{policy_path.as_posix()} service {name} has unsupported posture: {posture}")
        if posture == "selected_now":
            selected_now.add(name)

        module = entry.get("module")
        if isinstance(module, str) and module and not (root / module).is_file():
            errors.append(f"{policy_path.as_posix()} service {name} module is missing: {module}")

        resource_guard = entry.get("resource_guard")
        if resource_guard is None:
            errors.append(f"{policy_path.as_posix()} service {name} must include resource_guard, even when blank")
        elif not isinstance(resource_guard, str):
            errors.append(f"{policy_path.as_posix()} service {name} resource_guard must be a string")
        elif resource_guard and not (root / resource_guard).is_file():
            errors.append(f"{policy_path.as_posix()} service {name} resource guard is missing: {resource_guard}")
        elif posture == "selected_now" and not resource_guard:
            errors.append(f"{policy_path.as_posix()} selected service {name} must name a resource guard")


def _runtime_shape_services(
    *,
    runtime_shape: object,
    preset_dir: Path,
    profile_dir: Path,
    module_dir: Path,
    load_names_func: NameLoader,
    compose_service_names_func: ComposeServiceLoader,
) -> set[str]:
    if not isinstance(runtime_shape, dict):
        return set()

    profile_names: list[str] = []
    preset_name = runtime_shape.get("preset")
    if isinstance(preset_name, str) and preset_name:
        preset_path = preset_dir / f"{preset_name}.txt"
        if preset_path.is_file():
            profile_names.extend(load_names_func(preset_path))
    profiles = runtime_shape.get("profiles")
    if isinstance(profiles, list):
        profile_names.extend(
            profile for profile in profiles if isinstance(profile, str) and profile
        )

    seen_profiles: set[str] = set()
    module_names: list[str] = []
    for profile_name in profile_names:
        if profile_name in seen_profiles:
            continue
        seen_profiles.add(profile_name)
        profile_path = profile_dir / f"{profile_name}.txt"
        if not profile_path.is_file():
            continue
        module_names.extend(load_names_func(profile_path))

    runtime_shape_services: set[str] = set()
    seen_modules: set[str] = set()
    for module_name in module_names:
        if module_name in seen_modules:
            continue
        seen_modules.add(module_name)
        module_path = module_dir / module_name
        if module_path.is_file():
            runtime_shape_services.update(compose_service_names_func(module_path))

    return runtime_shape_services


def validate_service_screenshot_inventory(
    errors: list[str],
    *,
    root: Path,
    inventory_path: Path,
    policy_path: Path,
    required_screenshot_services: Set[str],
    expected_addon_services: Iterable[str],
    selection_doc_paths: Sequence[Path],
) -> None:
    absolute_inventory_path = root / inventory_path
    if not absolute_inventory_path.is_file():
        errors.append(f"{inventory_path.as_posix()} is required")
        return

    try:
        inventory = json.loads(absolute_inventory_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{inventory_path.as_posix()} must be valid JSON: {exc}")
        return

    if not isinstance(inventory, dict):
        errors.append(f"{inventory_path.as_posix()} must contain a JSON object")
        return

    if inventory.get("schema") != "abyss_stack_runtime_service_inventory_v1":
        errors.append(
            f"{inventory_path.as_posix()} must use schema abyss_stack_runtime_service_inventory_v1"
        )
    if inventory.get("policy_companion") != policy_path.as_posix():
        errors.append(
            f"{inventory_path.as_posix()} must point policy_companion at {policy_path.as_posix()}"
        )

    source = inventory.get("source_screenshot")
    if not isinstance(source, dict):
        errors.append(f"{inventory_path.as_posix()} must include source_screenshot")
    else:
        screenshot_path = source.get("absolute_path")
        if not isinstance(screenshot_path, str) or "2026-05-14 21-46-49.png" not in screenshot_path:
            errors.append(f"{inventory_path.as_posix()} must preserve the source screenshot path")
        if source.get("size_bytes") != 64281:
            errors.append(f"{inventory_path.as_posix()} must preserve the source screenshot size")
        if source.get("extraction_method") != "manual_visual_review":
            errors.append(f"{inventory_path.as_posix()} must declare manual_visual_review extraction")

    services = inventory.get("screenshotted_services")
    if not isinstance(services, list) or not services:
        errors.append(f"{inventory_path.as_posix()} must include screenshotted_services")
        return
    if not all(isinstance(service, str) and service for service in services):
        errors.append(f"{inventory_path.as_posix()} screenshotted_services must be non-empty strings")
        return

    service_set = set(services)
    if len(service_set) != len(services):
        errors.append(f"{inventory_path.as_posix()} must not duplicate screenshotted services")
    if service_set != required_screenshot_services:
        missing = sorted(required_screenshot_services - service_set)
        extra = sorted(service_set - required_screenshot_services)
        if missing:
            errors.append(
                f"{inventory_path.as_posix()} missing screenshot services: {', '.join(missing)}"
            )
        if extra:
            errors.append(
                f"{inventory_path.as_posix()} has unexpected screenshot services: {', '.join(extra)}"
            )

    _validate_screenshot_groups(
        errors,
        inventory=inventory,
        inventory_path=inventory_path,
        service_set=service_set,
    )

    policy_services = _load_policy_services(root=root, policy_path=policy_path)
    if policy_services is None:
        return

    policy_service_names = {
        entry.get("name")
        for entry in policy_services
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    missing_from_policy = sorted(service_set - policy_service_names)
    if missing_from_policy:
        errors.append(
            f"{inventory_path.as_posix()} services must all be covered by {policy_path.as_posix()}: {', '.join(missing_from_policy)}"
        )

    addon_services = _validate_current_selected_addons(
        errors,
        inventory=inventory,
        inventory_path=inventory_path,
        expected_addon_services=expected_addon_services,
    )

    selected_now = {
        entry.get("name")
        for entry in policy_services
        if isinstance(entry, dict) and entry.get("posture") == "selected_now"
    }
    selected_not_in_screenshot = selected_now - service_set
    if selected_not_in_screenshot != addon_services:
        errors.append(
            f"{inventory_path.as_posix()} current_selected_addons must explain selected policy services absent from the screenshot"
        )

    known_not_in_screenshot = inventory.get("known_policy_services_not_in_screenshot")
    if not isinstance(known_not_in_screenshot, list) or not all(isinstance(item, str) for item in known_not_in_screenshot):
        errors.append(f"{inventory_path.as_posix()} must include known_policy_services_not_in_screenshot")
    else:
        expected_known = policy_service_names - service_set - addon_services
        if set(known_not_in_screenshot) != expected_known:
            errors.append(
                f"{inventory_path.as_posix()} known_policy_services_not_in_screenshot must match policy services absent from the screenshot"
            )

    for relative_path in selection_doc_paths:
        text = (root / relative_path).read_text(encoding="utf-8")
        if inventory_path.name not in text:
            errors.append(f"{relative_path.as_posix()} must mention {inventory_path.name}")


def _validate_screenshot_groups(
    errors: list[str],
    *,
    inventory: dict[str, object],
    inventory_path: Path,
    service_set: set[str],
) -> None:
    grouped_services: list[str] = []
    groups = inventory.get("screenshotted_groups")
    if not isinstance(groups, list) or not groups:
        errors.append(f"{inventory_path.as_posix()} must include screenshotted_groups")
    else:
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                errors.append(f"{inventory_path.as_posix()} group {index} must be an object")
                continue
            if not isinstance(group.get("group"), str) or not group.get("group"):
                errors.append(f"{inventory_path.as_posix()} group {index} must include group")
            group_services = group.get("services")
            if not isinstance(group_services, list) or not group_services:
                errors.append(f"{inventory_path.as_posix()} group {index} must include services")
                continue
            for service in group_services:
                if isinstance(service, str) and service:
                    grouped_services.append(service)
                else:
                    errors.append(
                        f"{inventory_path.as_posix()} group {index} contains an invalid service"
                    )
        if set(grouped_services) != service_set:
            errors.append(
                f"{inventory_path.as_posix()} screenshotted_groups must match screenshotted_services"
            )


def _load_policy_services(*, root: Path, policy_path: Path) -> list[object] | None:
    try:
        policy = json.loads((root / policy_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    policy_services = policy.get("services")
    if not isinstance(policy_services, list):
        return None
    return policy_services


def _validate_current_selected_addons(
    errors: list[str],
    *,
    inventory: dict[str, object],
    inventory_path: Path,
    expected_addon_services: Iterable[str],
) -> set[str]:
    expected_addon_list = list(expected_addon_services)
    expected_addon_set = set(expected_addon_list)
    addon_entries = inventory.get("current_selected_addons")
    addon_services: set[str] = set()
    if not isinstance(addon_entries, list):
        errors.append(f"{inventory_path.as_posix()} must include current_selected_addons")
    else:
        for index, addon in enumerate(addon_entries):
            if not isinstance(addon, dict) or not isinstance(addon.get("service"), str):
                errors.append(f"{inventory_path.as_posix()} addon {index} must include service")
                continue
            addon_services.add(addon["service"])
        if addon_services != expected_addon_set:
            expected = " and ".join(expected_addon_list)
            errors.append(f"{inventory_path.as_posix()} current_selected_addons must contain {expected}")
    return addon_services
