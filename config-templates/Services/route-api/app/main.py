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
}


@dataclass(frozen=True)
class LayerStore:
    layer: str
    config_path: Path
    mirror_root: Path
    required_files: list[str]
    flags: dict[str, bool]
    payloads: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class AppStore:
    agents: LayerStore
    routing: LayerStore


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


@app.get("/health")
def health() -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "layers": [store.agents.layer, store.routing.layer],
        "mirror_ready": True,
        "layer_readiness": {
            store.agents.layer: True,
            store.routing.layer: True,
        },
        "thin_routing_only": store.agents.flags["thin_routing_only"],
        "advisory_only": store.routing.flags["advisory_only"],
    }


@app.get("/surface-status")
def surface_status() -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "layers": [store.agents.layer, store.routing.layer],
        "mirror_ready": True,
        "layer_readiness": {
            store.agents.layer: True,
            store.routing.layer: True,
        },
        "layers_status": {
            store.agents.layer: layer_status(store.agents),
            store.routing.layer: layer_status(store.routing),
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
