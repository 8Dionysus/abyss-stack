from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, model_validator


CONFIG_DIR = Path(os.environ.get("ROUTE_API_CONFIG_DIR", "/app/config"))
REQUIRED_CONFIGS = {
    "aoa-agents": "aoa-agents.yaml",
    "aoa-routing": "aoa-routing.yaml",
    "aoa-memo": "aoa-memo.yaml",
    "aoa-evals": "aoa-evals.yaml",
    "aoa-playbooks": "aoa-playbooks.yaml",
    "aoa-kag": "aoa-kag.yaml",
    "tos-source": "tos-source.yaml",
}


@dataclass(frozen=True)
class LayerStore:
    layer: str
    config_path: Path
    mirror_root: Path
    required_files: list[str]
    flags: dict[str, bool]
    payloads: dict[str, Any]


@dataclass(frozen=True)
class AppStore:
    agents: LayerStore
    routing: LayerStore
    memo: LayerStore
    evals: LayerStore
    playbooks: LayerStore
    kag: LayerStore
    tos_source: LayerStore


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"route-api config missing: {path}") from exc
    if not isinstance(loaded, dict):
        raise RuntimeError(f"route-api config must be a mapping: {path}")
    return loaded


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"required mirrored JSON missing: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"mirrored JSON must be an object: {path}")
    return payload


def load_json_value(path: Path) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"required mirrored JSON missing: {path}") from exc
    return payload


def iso_mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def validated_required_files(config: dict[str, Any], mirror_root: Path) -> list[str]:
    required_files = config.get("required_files")
    if not isinstance(required_files, list) or not required_files:
        raise RuntimeError("route-api config must include required_files")

    normalized_required_files: list[str] = []
    for rel_path in required_files:
        if not isinstance(rel_path, str) or not rel_path:
            raise RuntimeError("required_files entries must be non-empty strings")
        normalized_required_files.append(rel_path)
        if not (mirror_root / rel_path).is_file():
            raise RuntimeError(f"required mirrored file missing: {mirror_root / rel_path}")

    return normalized_required_files


def load_agents_layer(config_path: Path, config: dict[str, Any], mirror_root: Path) -> LayerStore:
    required_files = validated_required_files(config, mirror_root)
    payloads = {
        "agents": load_json(mirror_root / "generated/agent_registry.min.json"),
        "tiers": load_json(mirror_root / "generated/model_tier_registry.json"),
        "bindings": load_json(mirror_root / "generated/runtime_seam_bindings.json"),
        "cohorts": load_json(mirror_root / "generated/cohort_composition_registry.json"),
    }

    artifact_contracts: dict[str, dict[str, Any]] = {}
    for rel_path in required_files:
        if not rel_path.startswith("schemas/artifact.") or not rel_path.endswith(".schema.json"):
            continue
        artifact_type = rel_path.removeprefix("schemas/artifact.").removesuffix(".schema.json")
        artifact_contracts[artifact_type] = {
            "artifact_type": artifact_type,
            "schema_file": rel_path,
            "schema": load_json(mirror_root / rel_path),
        }
    payloads["artifact_contracts"] = artifact_contracts

    return LayerStore(
        layer="aoa-agents",
        config_path=config_path,
        mirror_root=mirror_root,
        required_files=required_files,
        flags={
            "thin_routing_only": bool(config.get("thin_routing_only", False)),
            "allow_free_text_task_routing": bool(config.get("allow_free_text_task_routing", False)),
        },
        payloads=payloads,
    )


def load_routing_layer(config_path: Path, config: dict[str, Any], mirror_root: Path) -> LayerStore:
    required_files = validated_required_files(config, mirror_root)
    payloads = {
        "router": load_json(mirror_root / "generated/aoa_router.min.json"),
        "cross_repo_registry": load_json(mirror_root / "generated/cross_repo_registry.min.json"),
        "surface_hints": load_json(mirror_root / "generated/task_to_surface_hints.json"),
        "tier_hints": load_json(mirror_root / "generated/task_to_tier_hints.json"),
        "recommended_paths": load_json(mirror_root / "generated/recommended_paths.min.json"),
        "pairing_hints": load_json(mirror_root / "generated/pairing_hints.min.json"),
        "kag_source_lift_relation_hints": load_json(mirror_root / "generated/kag_source_lift_relation_hints.min.json"),
        "federation_entrypoints": load_json(mirror_root / "generated/federation_entrypoints.min.json"),
        "return_hints": load_json(mirror_root / "generated/return_navigation_hints.min.json"),
        "tiny_model_entrypoints": load_json(mirror_root / "generated/tiny_model_entrypoints.json"),
    }

    return LayerStore(
        layer="aoa-routing",
        config_path=config_path,
        mirror_root=mirror_root,
        required_files=required_files,
        flags={
            "advisory_only": bool(config.get("advisory_only", False)),
            "allow_free_text_task_routing": bool(config.get("allow_free_text_task_routing", False)),
        },
        payloads=payloads,
    )


def load_memo_layer(config_path: Path, config: dict[str, Any], mirror_root: Path) -> LayerStore:
    required_files = validated_required_files(config, mirror_root)
    payloads = {
        "registry": load_json(mirror_root / "generated/memo_registry.min.json"),
        "catalog": load_json(mirror_root / "generated/memory_catalog.min.json"),
        "capsules": load_json(mirror_root / "generated/memory_capsules.json"),
        "sections": load_json(mirror_root / "generated/memory_sections.full.json"),
        "object_catalog": load_json(mirror_root / "generated/memory_object_catalog.min.json"),
        "object_capsules": load_json(mirror_root / "generated/memory_object_capsules.json"),
        "object_sections": load_json(mirror_root / "generated/memory_object_sections.full.json"),
        "checkpoint_contract": load_json(mirror_root / "examples/checkpoint_to_memory_contract.example.json"),
        "recall_contracts": {
            "router": {
                "semantic": load_json(mirror_root / "examples/recall_contract.router.semantic.json"),
                "lineage": load_json(mirror_root / "examples/recall_contract.router.lineage.json"),
            },
            "object": {
                "working": load_json(mirror_root / "examples/recall_contract.object.working.json"),
                "semantic": load_json(mirror_root / "examples/recall_contract.object.semantic.json"),
                "lineage": load_json(mirror_root / "examples/recall_contract.object.lineage.json"),
                "working_return": load_json(mirror_root / "examples/recall_contract.object.working.return.json"),
            },
        },
    }

    return LayerStore(
        layer="aoa-memo",
        config_path=config_path,
        mirror_root=mirror_root,
        required_files=required_files,
        flags={
            "read_only": bool(config.get("read_only", False)),
            "export_only_writeback": bool(config.get("export_only_writeback", False)),
            "allow_free_text_recall": bool(config.get("allow_free_text_recall", False)),
        },
        payloads=payloads,
    )


def load_evals_layer(config_path: Path, config: dict[str, Any], mirror_root: Path) -> LayerStore:
    required_files = validated_required_files(config, mirror_root)
    payloads = {
        "catalog": load_json(mirror_root / "generated/eval_catalog.min.json"),
        "capsules": load_json(mirror_root / "generated/eval_capsules.json"),
        "sections": load_json(mirror_root / "generated/eval_sections.full.json"),
        "comparison_spine": load_json(mirror_root / "generated/comparison_spine.json"),
        "runtime_evidence_templates": {
            "workhorse-local": load_json(mirror_root / "examples/runtime_evidence_selection.workhorse-local.example.json"),
            "return-anchor-integrity": load_json(
                mirror_root / "examples/runtime_evidence_selection.return-anchor-integrity.example.json"
            ),
        },
        "hook_templates": {
            "self-agent-checkpoint-rollout": load_json(
                mirror_root / "examples/artifact_to_verdict_hook.self-agent-checkpoint-rollout.example.json"
            ),
            "long-horizon-model-tier-orchestra": load_json(
                mirror_root / "examples/artifact_to_verdict_hook.long-horizon-model-tier-orchestra.example.json"
            ),
            "restartable-inquiry-loop": load_json(
                mirror_root / "examples/artifact_to_verdict_hook.restartable-inquiry-loop.example.json"
            ),
        },
    }

    return LayerStore(
        layer="aoa-evals",
        config_path=config_path,
        mirror_root=mirror_root,
        required_files=required_files,
        flags={
            "read_only": bool(config.get("read_only", False)),
            "export_only_evidence": bool(config.get("export_only_evidence", False)),
            "allow_free_text_eval_selection": bool(config.get("allow_free_text_eval_selection", False)),
        },
        payloads=payloads,
    )


def load_playbooks_layer(config_path: Path, config: dict[str, Any], mirror_root: Path) -> LayerStore:
    required_files = validated_required_files(config, mirror_root)
    payloads = {
        "registry": load_json(mirror_root / "generated/playbook_registry.min.json"),
        "activation": load_json_value(mirror_root / "generated/playbook_activation_surfaces.min.json"),
        "federation": load_json_value(mirror_root / "generated/playbook_federation_surfaces.min.json"),
        "handoffs": load_json(mirror_root / "generated/playbook_handoff_contracts.json"),
        "failures": load_json(mirror_root / "generated/playbook_failure_catalog.json"),
        "subagent_recipes": load_json(mirror_root / "generated/playbook_subagent_recipes.json"),
        "automation_seeds": load_json(mirror_root / "generated/playbook_automation_seeds.json"),
        "composition_manifest": load_json(mirror_root / "generated/playbook_composition_manifest.json"),
    }

    if not isinstance(payloads["activation"], list):
        raise RuntimeError("aoa-playbooks activation surface must be a list")
    if not isinstance(payloads["federation"], list):
        raise RuntimeError("aoa-playbooks federation surface must be a list")

    return LayerStore(
        layer="aoa-playbooks",
        config_path=config_path,
        mirror_root=mirror_root,
        required_files=required_files,
        flags={
            "read_only": bool(config.get("read_only", False)),
            "advisory_only": bool(config.get("advisory_only", False)),
            "allow_runtime_execution": bool(config.get("allow_runtime_execution", False)),
            "include_composition_surfaces": bool(config.get("include_composition_surfaces", False)),
        },
        payloads=payloads,
    )


def load_kag_layer(config_path: Path, config: dict[str, Any], mirror_root: Path) -> LayerStore:
    required_files = validated_required_files(config, mirror_root)
    payloads = {
        "registry": load_json(mirror_root / "generated/kag_registry.min.json"),
        "federation_spine": load_json(mirror_root / "generated/federation_spine.min.json"),
        "tiny_consumer_bundle": load_json(mirror_root / "generated/tiny_consumer_bundle.min.json"),
        "reasoning_handoff_pack": load_json(mirror_root / "generated/reasoning_handoff_pack.min.json"),
        "return_regrounding_pack": load_json(mirror_root / "generated/return_regrounding_pack.min.json"),
        "technique_lift_pack": load_json(mirror_root / "generated/technique_lift_pack.min.json"),
        "tos_retrieval_axis_pack": load_json(mirror_root / "generated/tos_retrieval_axis_pack.min.json"),
        "tos_text_chunk_map": load_json(mirror_root / "generated/tos_text_chunk_map.min.json"),
        "cross_source_node_projection": load_json(mirror_root / "generated/cross_source_node_projection.min.json"),
        "counterpart_exposure_review": load_json(
            mirror_root / "generated/counterpart_federation_exposure_review.min.json"
        ),
    }

    return LayerStore(
        layer="aoa-kag",
        config_path=config_path,
        mirror_root=mirror_root,
        required_files=required_files,
        flags={
            "advisory_only": bool(config.get("advisory_only", False)),
            "allow_free_text_querying": bool(config.get("allow_free_text_querying", False)),
            "allow_runtime_reasoning_handoff": bool(config.get("allow_runtime_reasoning_handoff", False)),
        },
        payloads=payloads,
    )


def load_tos_source_layer(config_path: Path, config: dict[str, Any], mirror_root: Path) -> LayerStore:
    required_files = validated_required_files(config, mirror_root)
    payloads = {
        "export": load_json(mirror_root / "generated/kag_export.min.json"),
        "entry_surface": load_json(mirror_root / "examples/source_node.example.json"),
        "tiny_entry_surface": load_json(mirror_root / "examples/tos_tiny_entry_route.example.json"),
    }

    return LayerStore(
        layer="tos-source",
        config_path=config_path,
        mirror_root=mirror_root,
        required_files=required_files,
        flags={
            "read_only": bool(config.get("read_only", False)),
            "source_owned": bool(config.get("source_owned", False)),
            "allow_runtime_mutation": bool(config.get("allow_runtime_mutation", False)),
        },
        payloads=payloads,
    )


def load_layer(config_path: Path) -> LayerStore:
    config = load_yaml(config_path)
    layer = config.get("layer")
    if not isinstance(layer, str) or not layer:
        raise RuntimeError(f"route-api config must include layer: {config_path}")

    mirror_root_value = config.get("mirror_root")
    if not isinstance(mirror_root_value, str) or not mirror_root_value:
        raise RuntimeError("route-api config must include mirror_root")
    mirror_root = Path(mirror_root_value)

    if layer == "aoa-agents":
        return load_agents_layer(config_path, config, mirror_root)
    if layer == "aoa-routing":
        return load_routing_layer(config_path, config, mirror_root)
    if layer == "aoa-memo":
        return load_memo_layer(config_path, config, mirror_root)
    if layer == "aoa-evals":
        return load_evals_layer(config_path, config, mirror_root)
    if layer == "aoa-playbooks":
        return load_playbooks_layer(config_path, config, mirror_root)
    if layer == "aoa-kag":
        return load_kag_layer(config_path, config, mirror_root)
    if layer == "tos-source":
        return load_tos_source_layer(config_path, config, mirror_root)
    raise RuntimeError(f"unsupported layer in route-api config: {layer!r}")


def load_store(config_dir: Path) -> AppStore:
    loaded_layers: dict[str, LayerStore] = {}
    for layer, file_name in REQUIRED_CONFIGS.items():
        loaded = load_layer(config_dir / file_name)
        if loaded.layer != layer:
            raise RuntimeError(f"route-api config mismatch for {file_name}: expected {layer}, got {loaded.layer}")
        loaded_layers[layer] = loaded

    return AppStore(
        agents=loaded_layers["aoa-agents"],
        routing=loaded_layers["aoa-routing"],
        memo=loaded_layers["aoa-memo"],
        evals=loaded_layers["aoa-evals"],
        playbooks=loaded_layers["aoa-playbooks"],
        kag=loaded_layers["aoa-kag"],
        tos_source=loaded_layers["tos-source"],
    )


def layer_status(layer: LayerStore) -> dict[str, Any]:
    files = {
        rel_path: {
            "present": (layer.mirror_root / rel_path).is_file(),
            "mtime_utc": iso_mtime(layer.mirror_root / rel_path),
        }
        for rel_path in layer.required_files
    }
    metadata: dict[str, Any]
    if layer.layer == "aoa-agents":
        metadata = {
            "agents": {
                "layer": layer.payloads["agents"].get("layer"),
                "version": layer.payloads["agents"].get("version"),
            },
            "tiers": {
                "layer": layer.payloads["tiers"].get("layer"),
                "version": layer.payloads["tiers"].get("version"),
            },
            "bindings": {
                "layer": layer.payloads["bindings"].get("layer"),
                "version": layer.payloads["bindings"].get("version"),
            },
            "cohorts": {
                "layer": layer.payloads["cohorts"].get("layer"),
                "version": layer.payloads["cohorts"].get("version"),
            },
            "artifact_contracts": sorted(layer.payloads["artifact_contracts"].keys()),
        }
    else:
        if layer.layer == "aoa-routing":
            metadata = {
                "router": {"version": layer.payloads["router"].get("router_version")},
                "cross_repo_registry": {"version": layer.payloads["cross_repo_registry"].get("version")},
                "surface_hints": {"version": layer.payloads["surface_hints"].get("version")},
                "tier_hints": {"version": layer.payloads["tier_hints"].get("version")},
                "recommended_paths": {"version": layer.payloads["recommended_paths"].get("version")},
                "pairing_hints": {"version": layer.payloads["pairing_hints"].get("version")},
                "kag_source_lift_relation_hints": {"version": layer.payloads["kag_source_lift_relation_hints"].get("version")},
                "federation_entrypoints": {"version": layer.payloads["federation_entrypoints"].get("version")},
                "return_hints": {"version": layer.payloads["return_hints"].get("version")},
                "tiny_model_entrypoints": {"version": layer.payloads["tiny_model_entrypoints"].get("version")},
            }
        elif layer.layer == "aoa-memo":
            metadata = {
                "registry": {"version": layer.payloads["registry"].get("version")},
                "catalog": {"version": layer.payloads["catalog"].get("catalog_version")},
                "object_catalog": {"version": layer.payloads["object_catalog"].get("catalog_version")},
                "checkpoint_contract": {"contract_id": layer.payloads["checkpoint_contract"].get("contract_id")},
                "router_recall_modes": sorted(layer.payloads["recall_contracts"]["router"].keys()),
                "object_recall_modes": sorted(
                    key for key in layer.payloads["recall_contracts"]["object"].keys() if key != "working_return"
                ),
                "object_return_ready": bool(
                    layer.payloads["recall_contracts"]["object"]["working_return"].get("return_ready")
                ),
            }
        elif layer.layer == "aoa-evals":
            metadata = {
                "catalog": {"version": layer.payloads["catalog"].get("catalog_version")},
                "capsules": {"version": layer.payloads["capsules"].get("capsule_version")},
                "sections": {"version": layer.payloads["sections"].get("section_version")},
                "comparison_spine": {"version": layer.payloads["comparison_spine"].get("comparison_spine_version")},
                "runtime_evidence_templates": sorted(layer.payloads["runtime_evidence_templates"].keys()),
                "hook_templates": sorted(layer.payloads["hook_templates"].keys()),
            }
        elif layer.layer == "aoa-playbooks":
            metadata = {
                "registry_count": len(layer.payloads["registry"]["playbooks"]),
                "activation_count": len(layer.payloads["activation"]),
                "federation_count": len(layer.payloads["federation"]),
                "handoff_playbook_count": len(layer.payloads["handoffs"]["playbooks"]),
                "failure_count": len(layer.payloads["failures"]["failures"]),
                "subagent_recipe_count": len(layer.payloads["subagent_recipes"]["recipes"]),
                "automation_seed_count": len(layer.payloads["automation_seeds"]["seeds"]),
            }
        elif layer.layer == "aoa-kag":
            metadata = {
                "registry_count": len(layer.payloads["registry"]["surfaces"]),
                "spine_repo_count": layer.payloads["federation_spine"].get(
                    "repo_count", len(layer.payloads["federation_spine"].get("repos", []))
                ),
                "reasoning_scenario_count": layer.payloads["reasoning_handoff_pack"].get(
                    "scenario_count", len(layer.payloads["reasoning_handoff_pack"].get("scenarios", []))
                ),
                "regrounding_mode_count": layer.payloads["return_regrounding_pack"].get(
                    "mode_count", len(layer.payloads["return_regrounding_pack"].get("modes", []))
                ),
                "chunk_count": len(layer.payloads["tos_text_chunk_map"].get("chunks", [])),
                "axis_count": len(layer.payloads["tos_retrieval_axis_pack"].get("axes", [])),
                "projection_count": len(layer.payloads["cross_source_node_projection"].get("projections", [])),
            }
        else:
            metadata = {
                "exported_object_id": layer.payloads["export"].get("object_id"),
                "entry_surface_path": layer.payloads["export"].get("entry_surface", {}).get("path"),
                "section_handle_count": len(layer.payloads["export"].get("section_handles", [])),
            }

    return {
        "config_path": str(layer.config_path),
        "mirror_root": str(layer.mirror_root),
        "ready": True,
        "flags": layer.flags,
        "required_files": files,
        "surface_metadata": metadata,
    }


def agents_by_name(store: AppStore) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in store.agents.payloads["agents"]["agents"]}


def tiers_by_id(store: AppStore) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in store.agents.payloads["tiers"]["model_tiers"]}


def bindings(store: AppStore) -> list[dict[str, Any]]:
    return store.agents.payloads["bindings"]["bindings"]


def require_tier(store: AppStore, tier_id: str) -> dict[str, Any]:
    tier = tiers_by_id(store).get(tier_id)
    if tier is None:
        raise HTTPException(status_code=500, detail=f"tier missing from mirrored registry: {tier_id}")
    return tier


def require_roles(store: AppStore, role_names: list[str]) -> list[dict[str, Any]]:
    roles_by_name = agents_by_name(store)
    resolved_roles: list[dict[str, Any]] = []
    for role_name in role_names:
        agent_entry = roles_by_name.get(role_name)
        if agent_entry is None:
            raise HTTPException(status_code=500, detail=f"role missing from mirrored registry: {role_name}")
        resolved_roles.append(agent_entry)
    return resolved_roles


def require_binding(
    store: AppStore,
    *,
    phase: str | None = None,
    tier_id: str | None = None,
    artifact_type: str | None = None,
) -> dict[str, Any]:
    for candidate in bindings(store):
        if phase is not None and candidate["phase"] == phase:
            return candidate
        if tier_id is not None and candidate["tier_id"] == tier_id:
            return candidate
        if artifact_type is not None and candidate["artifact_type"] == artifact_type:
            return candidate

    selector_name = "phase" if phase is not None else "tier_id" if tier_id is not None else "artifact_type"
    selector_value = phase if phase is not None else tier_id if tier_id is not None else artifact_type
    raise HTTPException(status_code=404, detail=f"no aoa-agents binding found for {selector_name}={selector_value}")


def require_artifact_contract(store: AppStore, artifact_type: str) -> dict[str, Any]:
    artifact_contract = store.agents.payloads["artifact_contracts"].get(artifact_type)
    if artifact_contract is None:
        raise HTTPException(status_code=500, detail=f"artifact schema missing from mirrored registry: {artifact_type}")
    return artifact_contract


def resolve_route(
    store: AppStore,
    *,
    phase: str | None,
    tier_id: str | None,
    artifact_type: str | None,
    include_cohorts: bool,
) -> dict[str, Any]:
    binding = require_binding(store, phase=phase, tier_id=tier_id, artifact_type=artifact_type)
    tier = require_tier(store, binding["tier_id"])
    resolved_roles = require_roles(store, binding["role_names"])

    source_files = [
        "generated/runtime_seam_bindings.json",
        "generated/model_tier_registry.json",
        "generated/agent_registry.min.json",
    ]

    response: dict[str, Any] = {
        "ok": True,
        "layer": "aoa-agents",
        "phase": binding["phase"],
        "tier": tier,
        "roles": resolved_roles,
        "artifact_type": binding["artifact_type"],
        "binding": binding,
        "source_files": source_files,
    }

    if include_cohorts:
        role_names = set(binding["role_names"])
        cohort_hints = []
        for cohort in store.agents.payloads["cohorts"]["cohort_patterns"]:
            if binding["tier_id"] not in cohort["preferred_tier_ids"]:
                continue
            if not any(role_names.issubset(set(allowed_set)) for allowed_set in cohort["allowed_role_sets"]):
                continue
            cohort_hints.append(cohort)

        response["cohort_hints"] = cohort_hints
        response["source_files"] = source_files + ["generated/cohort_composition_registry.json"]

    return response


def routing_payload(store: AppStore, key: str) -> dict[str, Any]:
    return store.routing.payloads[key]


def memo_payload(store: AppStore, key: str) -> dict[str, Any]:
    return store.memo.payloads[key]


def evals_payload(store: AppStore, key: str) -> dict[str, Any]:
    return store.evals.payloads[key]


def playbooks_payload(store: AppStore, key: str) -> Any:
    return store.playbooks.payloads[key]


def kag_payload(store: AppStore, key: str) -> dict[str, Any]:
    return store.kag.payloads[key]


def tos_source_payload(store: AppStore, key: str) -> dict[str, Any]:
    return store.tos_source.payloads[key]


def playbook_registry_entries(store: AppStore) -> list[dict[str, Any]]:
    return playbooks_payload(store, "registry")["playbooks"]


def playbook_activation_entries(store: AppStore) -> list[dict[str, Any]]:
    return playbooks_payload(store, "activation")


def playbook_federation_entries(store: AppStore) -> list[dict[str, Any]]:
    return playbooks_payload(store, "federation")


def playbook_handoff_entries(store: AppStore) -> list[dict[str, Any]]:
    return playbooks_payload(store, "handoffs")["playbooks"]


def playbook_failure_entries(store: AppStore) -> list[dict[str, Any]]:
    return playbooks_payload(store, "failures")["failures"]


def playbook_subagent_recipe_entries(store: AppStore) -> list[dict[str, Any]]:
    return playbooks_payload(store, "subagent_recipes")["recipes"]


def playbook_automation_seed_entries(store: AppStore) -> list[dict[str, Any]]:
    return playbooks_payload(store, "automation_seeds")["seeds"]


def require_playbook_registry_entry(store: AppStore, playbook_id: str) -> dict[str, Any]:
    for entry in playbook_registry_entries(store):
        if entry["id"] == playbook_id:
            return entry
    raise HTTPException(status_code=404, detail=f"no aoa-playbooks registry entry found for playbook_id={playbook_id}")


def optional_playbook_activation_entry(store: AppStore, playbook_id: str) -> dict[str, Any] | None:
    for entry in playbook_activation_entries(store):
        if entry["playbook_id"] == playbook_id:
            return entry
    return None


def optional_playbook_federation_entry(store: AppStore, playbook_id: str) -> dict[str, Any] | None:
    for entry in playbook_federation_entries(store):
        if entry["playbook_id"] == playbook_id:
            return entry
    return None


def optional_playbook_handoff_entry(store: AppStore, playbook_id: str) -> dict[str, Any] | None:
    for entry in playbook_handoff_entries(store):
        if entry["playbook_id"] == playbook_id:
            return entry
    return None


def playbook_subagent_recipes_for_name(store: AppStore, playbook_name: str) -> list[dict[str, Any]]:
    return [entry for entry in playbook_subagent_recipe_entries(store) if entry.get("playbook") == playbook_name]


def playbook_automation_seeds_for_name(store: AppStore, playbook_name: str) -> list[dict[str, Any]]:
    return [entry for entry in playbook_automation_seed_entries(store) if entry.get("playbook") == playbook_name]


def playbook_card(store: AppStore, playbook_id: str) -> dict[str, Any]:
    registry_entry = require_playbook_registry_entry(store, playbook_id)
    playbook_name = registry_entry["name"]
    activation_entry = optional_playbook_activation_entry(store, playbook_id)
    federation_entry = optional_playbook_federation_entry(store, playbook_id)
    handoff_contract = optional_playbook_handoff_entry(store, playbook_id)
    subagent_recipes = playbook_subagent_recipes_for_name(store, playbook_name)
    automation_seeds = playbook_automation_seeds_for_name(store, playbook_name)

    source_files = ["aoa-playbooks/generated/playbook_registry.min.json"]
    if activation_entry is not None:
        source_files.append("aoa-playbooks/generated/playbook_activation_surfaces.min.json")
    if federation_entry is not None:
        source_files.append("aoa-playbooks/generated/playbook_federation_surfaces.min.json")
    if handoff_contract is not None:
        source_files.append("aoa-playbooks/generated/playbook_handoff_contracts.json")
    if subagent_recipes:
        source_files.append("aoa-playbooks/generated/playbook_subagent_recipes.json")
    if automation_seeds:
        source_files.append("aoa-playbooks/generated/playbook_automation_seeds.json")

    return {
        "playbook_id": playbook_id,
        "name": playbook_name,
        "registry_entry": registry_entry,
        "activation_entry": activation_entry,
        "federation_entry": federation_entry,
        "handoff_contract": handoff_contract,
        "subagent_recipes": subagent_recipes,
        "automation_seeds": automation_seeds,
        "source_files": source_files,
    }


def compact_playbook_card(store: AppStore, playbook_id: str) -> dict[str, Any]:
    card = playbook_card(store, playbook_id)
    return {
        "playbook_id": card["playbook_id"],
        "name": card["name"],
        "registry_entry": card["registry_entry"],
        "activation_entry": card["activation_entry"],
        "federation_entry": card["federation_entry"],
        "handoff_contract": card["handoff_contract"],
        "subagent_recipe_names": [entry["name"] for entry in card["subagent_recipes"]],
        "automation_seed_names": [entry["name"] for entry in card["automation_seeds"]],
    }


def require_playbook_failure(store: AppStore, code: str) -> dict[str, Any]:
    for entry in playbook_failure_entries(store):
        if entry["code"] == code:
            return entry
    raise HTTPException(status_code=404, detail=f"no aoa-playbooks failure entry found for code={code}")


def require_playbook_subagent_recipe(store: AppStore, name: str) -> dict[str, Any]:
    for entry in playbook_subagent_recipe_entries(store):
        if entry["name"] == name:
            return entry
    raise HTTPException(status_code=404, detail=f"no aoa-playbooks subagent recipe found for name={name}")


def require_playbook_automation_seed(store: AppStore, name: str) -> dict[str, Any]:
    for entry in playbook_automation_seed_entries(store):
        if entry["name"] == name:
            return entry
    raise HTTPException(status_code=404, detail=f"no aoa-playbooks automation seed found for name={name}")


def resolve_playbook_select(
    store: AppStore,
    *,
    scenario: str | None,
    trigger: str | None,
    evaluation_posture: str | None,
    memory_posture: str | None,
    fallback_mode: str | None,
    return_reentry_mode: str | None,
    eval_anchor: str | None,
    required_skill: str | None,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for registry_entry in playbook_registry_entries(store):
        card = playbook_card(store, registry_entry["id"])
        activation_entry = card["activation_entry"] or {}
        federation_entry = card["federation_entry"] or {}

        if scenario is not None and (activation_entry.get("scenario") or registry_entry.get("scenario")) != scenario:
            continue
        if trigger is not None and (activation_entry.get("trigger") or registry_entry.get("trigger")) != trigger:
            continue
        if evaluation_posture is not None and (activation_entry.get("evaluation_posture") or registry_entry.get("evaluation_posture")) != evaluation_posture:
            continue
        if memory_posture is not None and (
            activation_entry.get("memory_posture")
            or federation_entry.get("memory_posture")
            or registry_entry.get("memory_posture")
        ) != memory_posture:
            continue
        if fallback_mode is not None and (activation_entry.get("fallback_mode") or registry_entry.get("fallback_mode")) != fallback_mode:
            continue
        if return_reentry_mode is not None and return_reentry_mode not in activation_entry.get("return_reentry_modes", []):
            continue
        if eval_anchor is not None and (
            eval_anchor not in activation_entry.get("eval_anchors", [])
            and eval_anchor not in federation_entry.get("eval_anchors", [])
        ):
            continue
        if required_skill is not None and required_skill not in federation_entry.get("required_skills", []):
            continue

        matches.append(compact_playbook_card(store, registry_entry["id"]))

    if not matches:
        raise HTTPException(status_code=404, detail="no aoa-playbooks entries matched the requested filters")

    return {
        "ok": True,
        "filters": {
            "scenario": scenario,
            "trigger": trigger,
            "evaluation_posture": evaluation_posture,
            "memory_posture": memory_posture,
            "fallback_mode": fallback_mode,
            "return_reentry_mode": return_reentry_mode,
            "eval_anchor": eval_anchor,
            "required_skill": required_skill,
        },
        "playbooks": matches,
        "source_files": [
            "aoa-playbooks/generated/playbook_registry.min.json",
            "aoa-playbooks/generated/playbook_activation_surfaces.min.json",
            "aoa-playbooks/generated/playbook_federation_surfaces.min.json",
        ],
    }


def require_task_family_hint(store: AppStore, task_family: str) -> dict[str, Any]:
    for hint in routing_payload(store, "tier_hints")["hints"]:
        if hint["task_family"] == task_family:
            return hint
    raise HTTPException(status_code=404, detail=f"no aoa-routing task family hint found for task_family={task_family}")


def require_surface_hint(store: AppStore, kind: str) -> dict[str, Any]:
    for hint in routing_payload(store, "surface_hints")["hints"]:
        if hint["kind"] == kind:
            return hint
    raise HTTPException(status_code=404, detail=f"no aoa-routing surface hint found for kind={kind}")


def require_root_card(store: AppStore, root_id: str) -> dict[str, Any]:
    for root in routing_payload(store, "federation_entrypoints")["root_entries"]:
        if root["id"] == root_id:
            return root
    raise HTTPException(status_code=404, detail=f"no aoa-routing federation root found for root_id={root_id}")


def require_federation_entry(store: AppStore, entry_id: str) -> dict[str, Any]:
    for entry in routing_payload(store, "federation_entrypoints")["entrypoints"]:
        if entry["id"] == entry_id:
            return entry
    raise HTTPException(status_code=404, detail=f"no aoa-routing federation entry found for id={entry_id}")


def federation_entries_by_kind(store: AppStore, entry_kind: str) -> list[dict[str, Any]]:
    matches = [
        entry
        for entry in routing_payload(store, "federation_entrypoints")["entrypoints"]
        if entry["kind"] == entry_kind
    ]
    if not matches:
        raise HTTPException(status_code=404, detail=f"no aoa-routing federation entries found for entry_kind={entry_kind}")
    return matches


def resolve_task_family(store: AppStore, task_family: str) -> dict[str, Any]:
    hint = require_task_family_hint(store, task_family)
    preferred_tier = require_tier(store, hint["preferred_tier"])
    binding = require_binding(store, tier_id=hint["preferred_tier"])
    roles = require_roles(store, binding["role_names"])
    artifact_contract = require_artifact_contract(store, hint["output_artifact"])

    response: dict[str, Any] = {
        "ok": True,
        "task_family": hint["task_family"],
        "hint": hint,
        "tier": preferred_tier,
        "artifact_contract": artifact_contract,
        "binding": binding,
        "roles": roles,
        "source_files": [
            "aoa-routing/generated/task_to_tier_hints.json",
            "aoa-agents/generated/model_tier_registry.json",
            "aoa-agents/generated/runtime_seam_bindings.json",
            "aoa-agents/generated/agent_registry.min.json",
            f"aoa-agents/{artifact_contract['schema_file']}",
        ],
    }

    fallback_tier_id = hint.get("fallback_tier")
    if isinstance(fallback_tier_id, str) and fallback_tier_id:
        response["fallback_tier"] = require_tier(store, fallback_tier_id)

    return response


def resolve_surface_kind(store: AppStore, kind: str, action: str | None) -> dict[str, Any]:
    hint = require_surface_hint(store, kind)
    source_files = ["aoa-routing/generated/task_to_surface_hints.json"]
    if action is None:
        return {
            "ok": True,
            "kind": kind,
            "hint": hint,
            "source_files": source_files,
        }

    action_contract = hint["actions"].get(action)
    if action_contract is None:
        raise HTTPException(status_code=404, detail=f"no aoa-routing action contract found for kind={kind}, action={action}")

    return {
        "ok": True,
        "kind": kind,
        "action": action,
        "source_repo": hint.get("source_repo"),
        "use_when": hint.get("use_when"),
        "action_contract": action_contract,
        "source_files": source_files,
    }


def resolve_return_hint(
    store: AppStore,
    *,
    context_kind: str | None,
    root_id: str | None,
    entry_kind: str | None,
    return_reason: str | None,
) -> dict[str, Any]:
    payload = routing_payload(store, "return_hints")
    selector_name: str
    selector_value: str
    if context_kind is not None:
        selector_name = "context_kind"
        selector_value = context_kind
        matches = [item for item in payload["thin_router_returns"] if item["context_kind"] == context_kind]
    elif root_id is not None:
        selector_name = "root_id"
        selector_value = root_id
        matches = [item for item in payload["federation_root_returns"] if item["root_id"] == root_id]
    else:
        selector_name = "entry_kind"
        selector_value = entry_kind or ""
        matches = [item for item in payload["federation_kind_returns"] if item["entry_kind"] == entry_kind]

    if return_reason is not None:
        matches = [
            item for item in matches
            if return_reason in item.get("supported_return_reasons", [])
        ]

    if not matches:
        raise HTTPException(status_code=404, detail=f"no aoa-routing return hint found for {selector_name}={selector_value}")

    response: dict[str, Any] = {
        "ok": True,
        selector_name: selector_value,
        "return_reason": return_reason,
        "source_files": ["aoa-routing/generated/return_navigation_hints.min.json"],
    }
    if len(matches) == 1:
        response["return_hint"] = matches[0]
    else:
        response["return_hints"] = matches
    return response


def resolve_router_target(store: AppStore, starter: dict[str, Any]) -> dict[str, Any] | list[dict[str, Any]] | None:
    target_surface = starter.get("target_surface")
    target_value = starter.get("target_value")
    target_kind = starter.get("target_kind")

    if target_surface == "generated/federation_entrypoints.min.json":
        if isinstance(target_value, str) and target_value:
            for root in routing_payload(store, "federation_entrypoints")["root_entries"]:
                if root["id"] == target_value:
                    return root
            for entry in routing_payload(store, "federation_entrypoints")["entrypoints"]:
                if entry["id"] == target_value:
                    return entry
        return None

    if target_surface == "generated/task_to_surface_hints.json":
        kind = target_kind or target_value
        if isinstance(kind, str) and kind:
            return require_surface_hint(store, kind)
        return routing_payload(store, "surface_hints")

    if target_surface == "generated/aoa_router.min.json":
        if isinstance(target_kind, str) and target_kind:
            return [
                entry for entry in routing_payload(store, "router")["entries"]
                if entry["kind"] == target_kind
            ]
        if isinstance(target_value, str) and target_value:
            return [
                entry for entry in routing_payload(store, "router")["entries"]
                if entry["kind"] == target_value or entry["id"] == target_value
            ]
        return routing_payload(store, "router")

    if target_surface == "generated/pairing_hints.min.json" and isinstance(target_value, str) and target_value:
        for entry in routing_payload(store, "pairing_hints")["entries"]:
            if entry["id"] == target_value:
                return entry
        return None

    if target_surface == "generated/recommended_paths.min.json" and isinstance(target_value, str) and target_value:
        for entry in routing_payload(store, "recommended_paths")["entries"]:
            if entry["id"] == target_value:
                return entry
        return None

    return None


def resolve_starter(store: AppStore, starter_name: str) -> dict[str, Any]:
    tiny_payload = routing_payload(store, "tiny_model_entrypoints")
    for family_name, collection_key in (("federation", "federation_starters"), ("thin_router", "starters")):
        for starter in tiny_payload.get(collection_key, []):
            if starter.get("name") != starter_name:
                continue
            resolved_target = resolve_router_target(store, starter)
            source_files = ["aoa-routing/generated/tiny_model_entrypoints.json"]
            target_surface = starter.get("target_surface")
            if isinstance(target_surface, str) and target_surface:
                source_files.append(f"aoa-routing/{target_surface}")
            return {
                "ok": True,
                "starter_family": family_name,
                "starter": starter,
                "resolved_target": resolved_target,
                "source_files": source_files,
            }

    raise HTTPException(status_code=404, detail=f"no aoa-routing starter found for starter_name={starter_name}")


def memo_collection_key(family: Literal["doctrine", "object"]) -> str:
    return "memo_surfaces" if family == "doctrine" else "memory_objects"


def memo_payload_key(
    family: Literal["doctrine", "object"],
    surface: Literal["catalog", "capsules", "sections"],
) -> str:
    if family == "doctrine":
        return {
            "catalog": "catalog",
            "capsules": "capsules",
            "sections": "sections",
        }[surface]
    return {
        "catalog": "object_catalog",
        "capsules": "object_capsules",
        "sections": "object_sections",
    }[surface]


def memo_source_file(
    family: Literal["doctrine", "object"],
    surface: Literal["catalog", "capsules", "sections"],
) -> str:
    return {
        ("doctrine", "catalog"): "aoa-memo/generated/memory_catalog.min.json",
        ("doctrine", "capsules"): "aoa-memo/generated/memory_capsules.json",
        ("doctrine", "sections"): "aoa-memo/generated/memory_sections.full.json",
        ("object", "catalog"): "aoa-memo/generated/memory_object_catalog.min.json",
        ("object", "capsules"): "aoa-memo/generated/memory_object_capsules.json",
        ("object", "sections"): "aoa-memo/generated/memory_object_sections.full.json",
    }[(family, surface)]


def memo_collection_payload(
    store: AppStore,
    family: Literal["doctrine", "object"],
    *,
    surface: Literal["catalog", "capsules", "sections"],
) -> dict[str, Any]:
    return memo_payload(store, memo_payload_key(family, surface))


def require_memo_entry(
    store: AppStore,
    family: Literal["doctrine", "object"],
    entry_id: str,
    *,
    surface: Literal["catalog", "capsules", "sections"],
) -> dict[str, Any]:
    payload = memo_collection_payload(store, family, surface=surface)
    collection_key = memo_collection_key(family)
    for entry in payload[collection_key]:
        if entry["id"] == entry_id:
            return entry
    raise HTTPException(status_code=404, detail=f"no aoa-memo {family} entry found for id={entry_id}")


def require_memo_section(
    entry: dict[str, Any],
    entry_id: str,
    section_id: str,
) -> dict[str, Any]:
    for section in entry.get("sections", []):
        if section["section_id"] == section_id:
            return section
    raise HTTPException(status_code=404, detail=f"no aoa-memo section found for id={entry_id}, section_id={section_id}")


def resolve_memo_recall_contract(
    store: AppStore,
    family: Literal["router", "object"],
    mode: Literal["working", "semantic", "lineage"],
    return_ready: bool,
) -> dict[str, Any]:
    payloads = memo_payload(store, "recall_contracts")[family]
    if family == "router":
        if return_ready:
            raise HTTPException(status_code=400, detail="return_ready is only supported for family=object and mode=working")
        if mode not in {"semantic", "lineage"}:
            raise HTTPException(status_code=400, detail="router family supports only semantic or lineage modes")
        rel_path = f"examples/recall_contract.router.{mode}.json"
        contract = payloads[mode]
    else:
        if mode not in {"working", "semantic", "lineage"}:
            raise HTTPException(status_code=400, detail="object family supports working, semantic, or lineage modes")
        if return_ready:
            if mode != "working":
                raise HTTPException(status_code=400, detail="return_ready requires family=object and mode=working")
            rel_path = "examples/recall_contract.object.working.return.json"
            contract = payloads["working_return"]
        else:
            rel_path = f"examples/recall_contract.object.{mode}.json"
            contract = payloads[mode]

    return {
        "ok": True,
        "family": family,
        "mode": mode,
        "return_ready": return_ready,
        "contract": contract,
        "source_files": [f"aoa-memo/{rel_path}"],
    }


def resolve_writeback_map(store: AppStore, runtime_surface: str) -> dict[str, Any]:
    checkpoint_contract = memo_payload(store, "checkpoint_contract")
    for mapping in checkpoint_contract["mapping_rules"]:
        if mapping["runtime_surface"] != runtime_surface:
            continue
        return {
            "ok": True,
            "runtime_surface": runtime_surface,
            "contract_type": checkpoint_contract["contract_type"],
            "contract_id": checkpoint_contract["contract_id"],
            "runtime_boundary": checkpoint_contract["runtime_boundary"],
            "mapping": mapping,
            "source_files": [
                "aoa-memo/examples/checkpoint_to_memory_contract.example.json",
                "aoa-memo/docs/RUNTIME_WRITEBACK_SEAM.md",
            ],
        }
    raise HTTPException(status_code=404, detail=f"no aoa-memo writeback mapping found for runtime_surface={runtime_surface}")


def require_eval_catalog_entry(store: AppStore, name: str) -> dict[str, Any]:
    for entry in evals_payload(store, "catalog")["evals"]:
        if entry["name"] == name:
            return entry
    raise HTTPException(status_code=404, detail=f"no aoa-evals catalog entry found for name={name}")


def require_eval_capsule_entry(store: AppStore, name: str) -> dict[str, Any]:
    for entry in evals_payload(store, "capsules")["evals"]:
        if entry["name"] == name:
            return entry
    raise HTTPException(status_code=404, detail=f"no aoa-evals capsule entry found for name={name}")


def require_eval_sections_entry(store: AppStore, name: str) -> dict[str, Any]:
    for entry in evals_payload(store, "sections")["evals"]:
        if entry["name"] == name:
            return entry
    raise HTTPException(status_code=404, detail=f"no aoa-evals section entry found for name={name}")


def require_eval_section(entry: dict[str, Any], name: str, section_key: str) -> dict[str, Any]:
    for section in entry.get("sections", []):
        if section["key"] == section_key:
            return section
    raise HTTPException(status_code=404, detail=f"no aoa-evals section found for name={name}, section_key={section_key}")


def resolve_eval_selection(
    store: AppStore,
    *,
    category: str | None,
    status: str | None,
    claim_type: str | None,
    baseline_mode: str | None,
    export_ready: bool | None,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for entry in evals_payload(store, "catalog")["evals"]:
        if category is not None and entry.get("category") != category:
            continue
        if status is not None and entry.get("status") != status:
            continue
        if claim_type is not None and entry.get("claim_type") != claim_type:
            continue
        if baseline_mode is not None and entry.get("baseline_mode") != baseline_mode:
            continue
        if export_ready is not None and bool(entry.get("export_ready")) != export_ready:
            continue
        matches.append(entry)

    if not matches:
        raise HTTPException(status_code=404, detail="no aoa-evals entries matched the requested filters")

    return {
        "ok": True,
        "filters": {
            "category": category,
            "status": status,
            "claim_type": claim_type,
            "baseline_mode": baseline_mode,
            "export_ready": export_ready,
        },
        "evals": matches,
        "source_files": ["aoa-evals/generated/eval_catalog.min.json"],
    }


def resolve_eval_comparison(store: AppStore, baseline_mode: str | None) -> dict[str, Any]:
    entries = evals_payload(store, "comparison_spine")["evals"]
    if baseline_mode is not None:
        entries = [entry for entry in entries if entry.get("baseline_mode") == baseline_mode]
    if not entries:
        raise HTTPException(status_code=404, detail="no aoa-evals comparison entries matched the requested filters")
    return {
        "ok": True,
        "baseline_mode": baseline_mode,
        "entries": entries,
        "source_files": ["aoa-evals/generated/comparison_spine.json"],
    }


def resolve_runtime_evidence_template(store: AppStore, template_name: str) -> dict[str, Any]:
    template = evals_payload(store, "runtime_evidence_templates")[template_name]
    rel_path = {
        "workhorse-local": "examples/runtime_evidence_selection.workhorse-local.example.json",
        "return-anchor-integrity": "examples/runtime_evidence_selection.return-anchor-integrity.example.json",
    }[template_name]
    return {
        "ok": True,
        "name": template_name,
        "template": template,
        "source_files": [f"aoa-evals/{rel_path}"],
    }


def resolve_hook_template(store: AppStore, template_name: str) -> dict[str, Any]:
    template = evals_payload(store, "hook_templates")[template_name]
    rel_path = {
        "self-agent-checkpoint-rollout": "examples/artifact_to_verdict_hook.self-agent-checkpoint-rollout.example.json",
        "long-horizon-model-tier-orchestra": "examples/artifact_to_verdict_hook.long-horizon-model-tier-orchestra.example.json",
        "restartable-inquiry-loop": "examples/artifact_to_verdict_hook.restartable-inquiry-loop.example.json",
    }[template_name]
    return {
        "ok": True,
        "name": template_name,
        "template": template,
        "source_files": [f"aoa-evals/{rel_path}"],
    }


def kag_registry_entries(store: AppStore) -> list[dict[str, Any]]:
    return kag_payload(store, "registry")["surfaces"]


def require_kag_registry_entry(store: AppStore, surface_id: str) -> dict[str, Any]:
    for entry in kag_registry_entries(store):
        if entry.get("surface_id") == surface_id or entry.get("id") == surface_id:
            return entry
    raise HTTPException(status_code=404, detail=f"no aoa-kag registry entry found for surface_id={surface_id}")


def require_kag_repo_entry(store: AppStore, repo: Literal["Tree-of-Sophia", "aoa-techniques"]) -> dict[str, Any]:
    for entry in kag_payload(store, "federation_spine")["repos"]:
        if entry["repo"] == repo:
            return entry
    raise HTTPException(status_code=404, detail=f"no aoa-kag federation spine repo entry found for repo={repo}")


def require_kag_regrounding_mode(store: AppStore, mode_id: str) -> dict[str, Any]:
    for mode in kag_payload(store, "return_regrounding_pack")["modes"]:
        if mode["mode_id"] == mode_id:
            return mode
    raise HTTPException(status_code=404, detail=f"no aoa-kag regrounding mode found for mode_id={mode_id}")


def require_kag_chunk(store: AppStore, chunk_id: str) -> dict[str, Any]:
    for chunk in kag_payload(store, "tos_text_chunk_map")["chunks"]:
        if chunk["chunk_id"] == chunk_id:
            return chunk
    raise HTTPException(status_code=404, detail=f"no aoa-kag chunk found for chunk_id={chunk_id}")


def require_kag_axis(store: AppStore, axis_id: str) -> dict[str, Any]:
    for axis in kag_payload(store, "tos_retrieval_axis_pack")["axes"]:
        if axis["axis_id"] == axis_id:
            return axis
    raise HTTPException(status_code=404, detail=f"no aoa-kag axis found for axis_id={axis_id}")


def require_kag_projection(store: AppStore, projection_id: str) -> dict[str, Any]:
    for projection in kag_payload(store, "cross_source_node_projection")["projections"]:
        if projection["projection_id"] == projection_id:
            return projection
    raise HTTPException(status_code=404, detail=f"no aoa-kag projection found for projection_id={projection_id}")


def resolve_kag_inspect(store: AppStore, surface_id: str) -> dict[str, Any]:
    pack_by_surface_id = {
        "AOA-K-0005": ("tos_text_chunk_map", "aoa-kag/generated/tos_text_chunk_map.min.json"),
        "AOA-K-0006": ("cross_source_node_projection", "aoa-kag/generated/cross_source_node_projection.min.json"),
        "AOA-K-0007": ("tos_retrieval_axis_pack", "aoa-kag/generated/tos_retrieval_axis_pack.min.json"),
        "AOA-K-0008": ("counterpart_exposure_review", "aoa-kag/generated/counterpart_federation_exposure_review.min.json"),
        "AOA-K-0009": ("federation_spine", "aoa-kag/generated/federation_spine.min.json"),
    }
    if surface_id not in pack_by_surface_id:
        raise HTTPException(status_code=404, detail=f"unsupported aoa-kag inspect surface_id={surface_id}")

    payload_key, source_file = pack_by_surface_id[surface_id]
    response: dict[str, Any] = {
        "ok": True,
        "surface_id": surface_id,
        "registry_entry": require_kag_registry_entry(store, surface_id),
        "pack": kag_payload(store, payload_key),
        "source_files": [
            "aoa-kag/generated/kag_registry.min.json",
            source_file,
        ],
    }

    if surface_id in {"AOA-K-0005", "AOA-K-0006", "AOA-K-0007"}:
        response["tos_support"] = {
            "export": tos_source_payload(store, "export"),
            "entry_surface": tos_source_payload(store, "entry_surface"),
            "tiny_entry_surface": tos_source_payload(store, "tiny_entry_surface"),
        }
        response["source_files"].extend(
            [
                "tos-source/generated/kag_export.min.json",
                "tos-source/examples/source_node.example.json",
                "tos-source/examples/tos_tiny_entry_route.example.json",
            ]
        )

    return response


def resolve_kag_query_mode(store: AppStore, mode: Literal["local_search", "global_search", "drift_search"]) -> dict[str, Any]:
    scenarios = [
        scenario
        for scenario in kag_payload(store, "reasoning_handoff_pack")["scenarios"]
        if mode in scenario.get("compatible_query_modes", [])
    ]
    regrounding_modes = [
        entry
        for entry in kag_payload(store, "return_regrounding_pack")["modes"]
        if entry.get("query_mode_hint") == mode
    ]
    if not scenarios and not regrounding_modes:
        raise HTTPException(status_code=404, detail=f"no aoa-kag entries matched mode={mode}")

    return {
        "ok": True,
        "mode": mode,
        "reasoning_scenarios": scenarios,
        "regrounding_modes": regrounding_modes,
        "source_files": [
            "aoa-kag/generated/reasoning_handoff_pack.min.json",
            "aoa-kag/generated/return_regrounding_pack.min.json",
        ],
    }


def resolve_kag_regrounding(store: AppStore, mode_id: str) -> dict[str, Any]:
    return {
        "ok": True,
        "mode_id": mode_id,
        "regrounding_mode": require_kag_regrounding_mode(store, mode_id),
        "source_files": ["aoa-kag/generated/return_regrounding_pack.min.json"],
    }


def resolve_kag_repo_entry(store: AppStore, repo: Literal["Tree-of-Sophia", "aoa-techniques"]) -> dict[str, Any]:
    repo_entry = require_kag_repo_entry(store, repo)
    response: dict[str, Any] = {
        "ok": True,
        "repo": repo,
        "repo_entry": repo_entry,
        "source_files": ["aoa-kag/generated/federation_spine.min.json"],
    }
    if repo == "Tree-of-Sophia":
        response["tos_export"] = tos_source_payload(store, "export")
        response["tos_entry_surface"] = tos_source_payload(store, "entry_surface")
        response["tos_tiny_entry_surface"] = tos_source_payload(store, "tiny_entry_surface")
        response["source_files"].extend(
            [
                "tos-source/generated/kag_export.min.json",
                "tos-source/examples/source_node.example.json",
                "tos-source/examples/tos_tiny_entry_route.example.json",
            ]
        )
    return response


app = FastAPI(title="AoA federation route API")
STORE: AppStore | None = None


@app.on_event("startup")
def startup() -> None:
    global STORE
    STORE = load_store(CONFIG_DIR)


def require_store() -> AppStore:
    if STORE is None:
        raise HTTPException(status_code=503, detail="route-api store not initialized")
    return STORE


class RouteRequest(BaseModel):
    phase: str | None = None
    tier_id: str | None = None
    artifact_type: str | None = None
    include_cohorts: bool = False

    @model_validator(mode="after")
    def validate_selector_count(self) -> "RouteRequest":
        selected = [self.phase, self.tier_id, self.artifact_type]
        count = sum(1 for value in selected if value is not None)
        if count != 1:
            raise ValueError("exactly one of phase, tier_id, or artifact_type must be set")
        return self


class RoutingTaskFamilyRequest(BaseModel):
    task_family: str


class RoutingSurfaceKindRequest(BaseModel):
    kind: Literal["technique", "skill", "eval", "memo"]
    action: str | None = None


class FederationRootRequest(BaseModel):
    root_id: Literal["aoa-root", "tos-root"]


class FederationEntryRequest(BaseModel):
    id: str


class FederationKindRequest(BaseModel):
    entry_kind: str


class ReturnRequest(BaseModel):
    context_kind: str | None = None
    root_id: str | None = None
    entry_kind: str | None = None
    return_reason: str | None = None

    @model_validator(mode="after")
    def validate_selector_count(self) -> "ReturnRequest":
        selected = [self.context_kind, self.root_id, self.entry_kind]
        count = sum(1 for value in selected if value is not None)
        if count != 1:
            raise ValueError("exactly one of context_kind, root_id, or entry_kind must be set")
        return self


class StarterRequest(BaseModel):
    starter_name: str


class MemoInspectRequest(BaseModel):
    family: Literal["doctrine", "object"]
    id: str


class MemoExpandRequest(BaseModel):
    family: Literal["doctrine", "object"]
    id: str
    section_id: str | None = None


class MemoRecallContractRequest(BaseModel):
    family: Literal["router", "object"]
    mode: Literal["working", "semantic", "lineage"]
    return_ready: bool = False

    @model_validator(mode="after")
    def validate_shape(self) -> "MemoRecallContractRequest":
        if self.family == "router" and self.mode == "working":
            raise ValueError("router family supports only semantic or lineage modes")
        if self.return_ready and not (self.family == "object" and self.mode == "working"):
            raise ValueError("return_ready requires family=object and mode=working")
        return self


class MemoWritebackMapRequest(BaseModel):
    runtime_surface: Literal[
        "checkpoint_export",
        "approval_record",
        "transition_record",
        "execution_trace",
        "review_trace",
        "distillation_claim_candidate",
        "distillation_pattern_candidate",
        "distillation_bridge_candidate",
    ]


class EvalInspectRequest(BaseModel):
    name: str


class EvalExpandRequest(BaseModel):
    name: str
    section_key: str | None = None


class EvalSelectRequest(BaseModel):
    category: str | None = None
    status: str | None = None
    claim_type: str | None = None
    baseline_mode: str | None = None
    export_ready: bool | None = None


class EvalComparisonRequest(BaseModel):
    baseline_mode: str | None = None


class RuntimeEvidenceTemplateRequest(BaseModel):
    name: Literal["workhorse-local", "return-anchor-integrity"]


class HookTemplateRequest(BaseModel):
    name: Literal[
        "self-agent-checkpoint-rollout",
        "long-horizon-model-tier-orchestra",
        "restartable-inquiry-loop",
    ]


class PlaybookInspectRequest(BaseModel):
    playbook_id: str


class PlaybookSelectRequest(BaseModel):
    scenario: str | None = None
    trigger: str | None = None
    evaluation_posture: str | None = None
    memory_posture: str | None = None
    fallback_mode: str | None = None
    return_reentry_mode: str | None = None
    eval_anchor: str | None = None
    required_skill: str | None = None


class PlaybookFailureRequest(BaseModel):
    code: str


class PlaybookSubagentRecipeRequest(BaseModel):
    name: str


class PlaybookAutomationSeedRequest(BaseModel):
    name: str


class KagInspectRequest(BaseModel):
    surface_id: str


class KagQueryModeRequest(BaseModel):
    mode: Literal["local_search", "global_search", "drift_search"]


class KagRegroundingRequest(BaseModel):
    mode_id: str


class KagRepoEntryRequest(BaseModel):
    repo: Literal["Tree-of-Sophia", "aoa-techniques"]


class KagChunkRequest(BaseModel):
    chunk_id: str


class KagAxisRequest(BaseModel):
    axis_id: str


class KagProjectionRequest(BaseModel):
    projection_id: str


@app.get("/health")
def health() -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "layers": [
            store.agents.layer,
            store.routing.layer,
            store.memo.layer,
            store.evals.layer,
            store.playbooks.layer,
            store.kag.layer,
            store.tos_source.layer,
        ],
        "mirror_ready": True,
        "layer_readiness": {
            store.agents.layer: True,
            store.routing.layer: True,
            store.memo.layer: True,
            store.evals.layer: True,
            store.playbooks.layer: True,
            store.kag.layer: True,
            store.tos_source.layer: True,
        },
        "thin_routing_only": store.agents.flags["thin_routing_only"],
        "advisory_only": store.routing.flags["advisory_only"],
        "memo_read_only": store.memo.flags["read_only"],
        "memo_export_only_writeback": store.memo.flags["export_only_writeback"],
        "evals_read_only": store.evals.flags["read_only"],
        "evals_export_only_evidence": store.evals.flags["export_only_evidence"],
        "playbooks_read_only": store.playbooks.flags["read_only"],
        "playbooks_advisory_only": store.playbooks.flags["advisory_only"],
        "playbooks_allow_runtime_execution": store.playbooks.flags["allow_runtime_execution"],
        "playbooks_include_composition_surfaces": store.playbooks.flags["include_composition_surfaces"],
        "kag_advisory_only": store.kag.flags["advisory_only"],
        "kag_allow_free_text_querying": store.kag.flags["allow_free_text_querying"],
        "kag_allow_runtime_reasoning_handoff": store.kag.flags["allow_runtime_reasoning_handoff"],
        "tos_source_read_only": store.tos_source.flags["read_only"],
        "tos_source_owned": store.tos_source.flags["source_owned"],
        "tos_source_allow_runtime_mutation": store.tos_source.flags["allow_runtime_mutation"],
    }


@app.get("/surface-status")
def surface_status() -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "layers": [
            store.agents.layer,
            store.routing.layer,
            store.memo.layer,
            store.evals.layer,
            store.playbooks.layer,
            store.kag.layer,
            store.tos_source.layer,
        ],
        "mirror_ready": True,
        "layer_readiness": {
            store.agents.layer: True,
            store.routing.layer: True,
            store.memo.layer: True,
            store.evals.layer: True,
            store.playbooks.layer: True,
            store.kag.layer: True,
            store.tos_source.layer: True,
        },
        "layers_status": {
            store.agents.layer: layer_status(store.agents),
            store.routing.layer: layer_status(store.routing),
            store.memo.layer: layer_status(store.memo),
            store.evals.layer: layer_status(store.evals),
            store.playbooks.layer: layer_status(store.playbooks),
            store.kag.layer: layer_status(store.kag),
            store.tos_source.layer: layer_status(store.tos_source),
        },
    }


@app.get("/agents")
def agents() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": store.agents.payloads["agents"]}


@app.get("/tiers")
def tiers() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": store.agents.payloads["tiers"]}


@app.get("/bindings")
def bindings_endpoint() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": store.agents.payloads["bindings"]}


@app.get("/cohorts")
def cohorts() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": store.agents.payloads["cohorts"]}


@app.post("/route")
def route(request: RouteRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_route(
        store,
        phase=request.phase,
        tier_id=request.tier_id,
        artifact_type=request.artifact_type,
        include_cohorts=request.include_cohorts,
    )


@app.get("/routing/router")
def routing_router() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": routing_payload(store, "router")}


@app.get("/routing/surface-hints")
def routing_surface_hints() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": routing_payload(store, "surface_hints")}


@app.get("/routing/tier-hints")
def routing_tier_hints() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": routing_payload(store, "tier_hints")}


@app.get("/routing/recommended-paths")
def routing_recommended_paths() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": routing_payload(store, "recommended_paths")}


@app.get("/routing/pairing-hints")
def routing_pairing_hints() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": routing_payload(store, "pairing_hints")}


@app.get("/routing/federation-entrypoints")
def routing_federation_entrypoints() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": routing_payload(store, "federation_entrypoints")}


@app.get("/routing/return-hints")
def routing_return_hints() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": routing_payload(store, "return_hints")}


@app.get("/routing/tiny-model-entrypoints")
def routing_tiny_model_entrypoints() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": routing_payload(store, "tiny_model_entrypoints")}


@app.post("/routing/task-family")
def routing_task_family(request: RoutingTaskFamilyRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_task_family(store, request.task_family)


@app.post("/routing/surface-kind")
def routing_surface_kind(request: RoutingSurfaceKindRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_surface_kind(store, request.kind, request.action)


@app.post("/routing/federation-root")
def routing_federation_root(request: FederationRootRequest) -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "root": require_root_card(store, request.root_id),
        "source_files": ["aoa-routing/generated/federation_entrypoints.min.json"],
    }


@app.post("/routing/federation-entry")
def routing_federation_entry(request: FederationEntryRequest) -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "entry": require_federation_entry(store, request.id),
        "source_files": ["aoa-routing/generated/federation_entrypoints.min.json"],
    }


@app.post("/routing/federation-kind")
def routing_federation_kind(request: FederationKindRequest) -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "entry_kind": request.entry_kind,
        "entries": federation_entries_by_kind(store, request.entry_kind),
        "source_files": ["aoa-routing/generated/federation_entrypoints.min.json"],
    }


@app.post("/routing/return")
def routing_return(request: ReturnRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_return_hint(
        store,
        context_kind=request.context_kind,
        root_id=request.root_id,
        entry_kind=request.entry_kind,
        return_reason=request.return_reason,
    )


@app.post("/routing/starter")
def routing_starter(request: StarterRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_starter(store, request.starter_name)


@app.get("/memo/registry")
def memo_registry() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": memo_payload(store, "registry")}


@app.get("/memo/catalog")
def memo_catalog() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": memo_payload(store, "catalog")}


@app.get("/memo/object-catalog")
def memo_object_catalog() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": memo_payload(store, "object_catalog")}


@app.get("/memo/checkpoint-contract")
def memo_checkpoint_contract() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": memo_payload(store, "checkpoint_contract")}


@app.post("/memo/inspect")
def memo_inspect(request: MemoInspectRequest) -> dict[str, Any]:
    store = require_store()
    entry = require_memo_entry(store, request.family, request.id, surface="catalog")
    return {
        "ok": True,
        "family": request.family,
        "id": request.id,
        "entry": entry,
        "source_files": [memo_source_file(request.family, "catalog")],
    }


@app.post("/memo/capsule")
def memo_capsule(request: MemoInspectRequest) -> dict[str, Any]:
    store = require_store()
    entry = require_memo_entry(store, request.family, request.id, surface="capsules")
    return {
        "ok": True,
        "family": request.family,
        "id": request.id,
        "entry": entry,
        "source_files": [memo_source_file(request.family, "capsules")],
    }


@app.post("/memo/expand")
def memo_expand(request: MemoExpandRequest) -> dict[str, Any]:
    store = require_store()
    entry = require_memo_entry(store, request.family, request.id, surface="sections")
    response: dict[str, Any] = {
        "ok": True,
        "family": request.family,
        "id": request.id,
        "entry": entry,
        "source_files": [memo_source_file(request.family, "sections")],
    }
    if request.section_id is not None:
        response["section_id"] = request.section_id
        response["section"] = require_memo_section(entry, request.id, request.section_id)
    return response


@app.post("/memo/recall-contract")
def memo_recall_contract(request: MemoRecallContractRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_memo_recall_contract(store, request.family, request.mode, request.return_ready)


@app.post("/memo/writeback-map")
def memo_writeback_map(request: MemoWritebackMapRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_writeback_map(store, request.runtime_surface)


@app.get("/evals/catalog")
def evals_catalog() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": evals_payload(store, "catalog")}


@app.get("/evals/capsules")
def evals_capsules() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": evals_payload(store, "capsules")}


@app.get("/evals/comparison-spine")
def evals_comparison_spine() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": evals_payload(store, "comparison_spine")}


@app.post("/evals/inspect")
def evals_inspect(request: EvalInspectRequest) -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "name": request.name,
        "catalog_entry": require_eval_catalog_entry(store, request.name),
        "capsule": require_eval_capsule_entry(store, request.name),
        "source_files": [
            "aoa-evals/generated/eval_catalog.min.json",
            "aoa-evals/generated/eval_capsules.json",
        ],
    }


@app.post("/evals/expand")
def evals_expand(request: EvalExpandRequest) -> dict[str, Any]:
    store = require_store()
    entry = require_eval_sections_entry(store, request.name)
    response: dict[str, Any] = {
        "ok": True,
        "name": request.name,
        "entry": entry,
        "source_files": ["aoa-evals/generated/eval_sections.full.json"],
    }
    if request.section_key is not None:
        response["section_key"] = request.section_key
        response["section"] = require_eval_section(entry, request.name, request.section_key)
    return response


@app.post("/evals/select")
def evals_select(request: EvalSelectRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_eval_selection(
        store,
        category=request.category,
        status=request.status,
        claim_type=request.claim_type,
        baseline_mode=request.baseline_mode,
        export_ready=request.export_ready,
    )


@app.post("/evals/comparison")
def evals_comparison(request: EvalComparisonRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_eval_comparison(store, request.baseline_mode)


@app.post("/evals/runtime-evidence-template")
def evals_runtime_evidence_template(request: RuntimeEvidenceTemplateRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_runtime_evidence_template(store, request.name)


@app.post("/evals/hook-template")
def evals_hook_template(request: HookTemplateRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_hook_template(store, request.name)


@app.get("/playbooks/registry")
def playbooks_registry() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": playbooks_payload(store, "registry")}


@app.get("/playbooks/activation")
def playbooks_activation() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": playbooks_payload(store, "activation")}


@app.get("/playbooks/federation")
def playbooks_federation() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": playbooks_payload(store, "federation")}


@app.get("/playbooks/handoffs")
def playbooks_handoffs() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": playbooks_payload(store, "handoffs")}


@app.get("/playbooks/failures")
def playbooks_failures() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": playbooks_payload(store, "failures")}


@app.get("/playbooks/subagent-recipes")
def playbooks_subagent_recipes() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": playbooks_payload(store, "subagent_recipes")}


@app.get("/playbooks/automation-seeds")
def playbooks_automation_seeds() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": playbooks_payload(store, "automation_seeds")}


@app.get("/playbooks/composition-manifest")
def playbooks_composition_manifest() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": playbooks_payload(store, "composition_manifest")}


@app.post("/playbooks/inspect")
def playbooks_inspect(request: PlaybookInspectRequest) -> dict[str, Any]:
    store = require_store()
    card = playbook_card(store, request.playbook_id)
    return {
        "ok": True,
        "playbook": card,
        "source_files": card["source_files"],
    }


@app.post("/playbooks/select")
def playbooks_select(request: PlaybookSelectRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_playbook_select(
        store,
        scenario=request.scenario,
        trigger=request.trigger,
        evaluation_posture=request.evaluation_posture,
        memory_posture=request.memory_posture,
        fallback_mode=request.fallback_mode,
        return_reentry_mode=request.return_reentry_mode,
        eval_anchor=request.eval_anchor,
        required_skill=request.required_skill,
    )


@app.post("/playbooks/failure")
def playbooks_failure(request: PlaybookFailureRequest) -> dict[str, Any]:
    store = require_store()
    entry = require_playbook_failure(store, request.code)
    related = [
        compact_playbook_card(store, registry_entry["id"])
        for registry_entry in playbook_registry_entries(store)
        if registry_entry["name"] in entry.get("used_by_playbooks", [])
    ]
    return {
        "ok": True,
        "code": request.code,
        "failure": entry,
        "related_playbooks": related,
        "source_files": [
            "aoa-playbooks/generated/playbook_failure_catalog.json",
            "aoa-playbooks/generated/playbook_registry.min.json",
            "aoa-playbooks/generated/playbook_activation_surfaces.min.json",
            "aoa-playbooks/generated/playbook_federation_surfaces.min.json",
            "aoa-playbooks/generated/playbook_handoff_contracts.json",
            "aoa-playbooks/generated/playbook_subagent_recipes.json",
            "aoa-playbooks/generated/playbook_automation_seeds.json",
        ],
    }


@app.post("/playbooks/subagent-recipe")
def playbooks_subagent_recipe(request: PlaybookSubagentRecipeRequest) -> dict[str, Any]:
    store = require_store()
    recipe = require_playbook_subagent_recipe(store, request.name)
    return {
        "ok": True,
        "name": request.name,
        "recipe": recipe,
        "source_files": ["aoa-playbooks/generated/playbook_subagent_recipes.json"],
    }


@app.post("/playbooks/automation-seed")
def playbooks_automation_seed(request: PlaybookAutomationSeedRequest) -> dict[str, Any]:
    store = require_store()
    seed = require_playbook_automation_seed(store, request.name)
    return {
        "ok": True,
        "name": request.name,
        "seed": seed,
        "source_files": ["aoa-playbooks/generated/playbook_automation_seeds.json"],
    }


@app.get("/kag/registry")
def kag_registry() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": kag_payload(store, "registry")}


@app.get("/kag/federation-spine")
def kag_federation_spine() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": kag_payload(store, "federation_spine")}


@app.get("/kag/tiny-consumer-bundle")
def kag_tiny_consumer_bundle() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": kag_payload(store, "tiny_consumer_bundle")}


@app.get("/kag/reasoning-handoff-pack")
def kag_reasoning_handoff_pack() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": kag_payload(store, "reasoning_handoff_pack")}


@app.get("/kag/return-regrounding-pack")
def kag_return_regrounding_pack() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": kag_payload(store, "return_regrounding_pack")}


@app.get("/kag/technique-lift-pack")
def kag_technique_lift_pack() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": kag_payload(store, "technique_lift_pack")}


@app.get("/kag/tos-retrieval-axis-pack")
def kag_tos_retrieval_axis_pack() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": kag_payload(store, "tos_retrieval_axis_pack")}


@app.get("/kag/tos-text-chunk-map")
def kag_tos_text_chunk_map() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": kag_payload(store, "tos_text_chunk_map")}


@app.get("/kag/cross-source-node-projection")
def kag_cross_source_node_projection() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": kag_payload(store, "cross_source_node_projection")}


@app.get("/kag/counterpart-exposure-review")
def kag_counterpart_exposure_review() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": kag_payload(store, "counterpart_exposure_review")}


@app.get("/kag/tos-export")
def kag_tos_export() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": tos_source_payload(store, "export")}


@app.get("/kag/tos-entry-surface")
def kag_tos_entry_surface() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": tos_source_payload(store, "entry_surface")}


@app.post("/kag/inspect")
def kag_inspect(request: KagInspectRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_kag_inspect(store, request.surface_id)


@app.post("/kag/query-mode")
def kag_query_mode(request: KagQueryModeRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_kag_query_mode(store, request.mode)


@app.post("/kag/regrounding")
def kag_regrounding(request: KagRegroundingRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_kag_regrounding(store, request.mode_id)


@app.post("/kag/repo-entry")
def kag_repo_entry(request: KagRepoEntryRequest) -> dict[str, Any]:
    store = require_store()
    return resolve_kag_repo_entry(store, request.repo)


@app.post("/kag/chunk")
def kag_chunk(request: KagChunkRequest) -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "chunk_id": request.chunk_id,
        "chunk": require_kag_chunk(store, request.chunk_id),
        "source_files": ["aoa-kag/generated/tos_text_chunk_map.min.json"],
    }


@app.post("/kag/axis")
def kag_axis(request: KagAxisRequest) -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "axis_id": request.axis_id,
        "axis": require_kag_axis(store, request.axis_id),
        "source_files": ["aoa-kag/generated/tos_retrieval_axis_pack.min.json"],
    }


@app.post("/kag/projection")
def kag_projection(request: KagProjectionRequest) -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "projection_id": request.projection_id,
        "projection": require_kag_projection(store, request.projection_id),
        "source_files": ["aoa-kag/generated/cross_source_node_projection.min.json"],
    }
