from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, model_validator


CONFIG_PATH = Path(os.environ.get("ROUTE_API_CONFIG_PATH", "/app/config/aoa-agents.yaml"))


@dataclass(frozen=True)
class SurfaceStore:
    layer: str
    config_path: Path
    mirror_root: Path
    required_files: list[str]
    thin_routing_only: bool
    allow_free_text_task_routing: bool
    runtime_seam_doc: str
    agents_payload: dict[str, Any]
    tiers_payload: dict[str, Any]
    bindings_payload: dict[str, Any]
    cohorts_payload: dict[str, Any]


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


def load_store(config_path: Path) -> SurfaceStore:
    config = load_yaml(config_path)
    layer = config.get("layer")
    if layer != "aoa-agents":
        raise RuntimeError(f"unsupported layer in route-api config: {layer!r}")

    mirror_root_value = config.get("mirror_root")
    if not isinstance(mirror_root_value, str) or not mirror_root_value:
        raise RuntimeError("route-api config must include mirror_root")
    mirror_root = Path(mirror_root_value)

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

    runtime_seam_doc = (mirror_root / "docs/AGENT_RUNTIME_SEAM.md").read_text(encoding="utf-8")
    agents_payload = load_json(mirror_root / "generated/agent_registry.min.json")
    tiers_payload = load_json(mirror_root / "generated/model_tier_registry.json")
    bindings_payload = load_json(mirror_root / "generated/runtime_seam_bindings.json")
    cohorts_payload = load_json(mirror_root / "generated/cohort_composition_registry.json")

    return SurfaceStore(
        layer=layer,
        config_path=config_path,
        mirror_root=mirror_root,
        required_files=normalized_required_files,
        thin_routing_only=bool(config.get("thin_routing_only", False)),
        allow_free_text_task_routing=bool(config.get("allow_free_text_task_routing", False)),
        runtime_seam_doc=runtime_seam_doc,
        agents_payload=agents_payload,
        tiers_payload=tiers_payload,
        bindings_payload=bindings_payload,
        cohorts_payload=cohorts_payload,
    )


def resolve_route(store: SurfaceStore, *, phase: str | None, tier_id: str | None, artifact_type: str | None, include_cohorts: bool) -> dict[str, Any]:
    bindings = store.bindings_payload["bindings"]
    binding = None
    for candidate in bindings:
        if phase is not None and candidate["phase"] == phase:
            binding = candidate
            break
        if tier_id is not None and candidate["tier_id"] == tier_id:
            binding = candidate
            break
        if artifact_type is not None and candidate["artifact_type"] == artifact_type:
            binding = candidate
            break

    if binding is None:
        selector_name = "phase" if phase is not None else "tier_id" if tier_id is not None else "artifact_type"
        selector_value = phase if phase is not None else tier_id if tier_id is not None else artifact_type
        raise HTTPException(status_code=404, detail=f"no aoa-agents binding found for {selector_name}={selector_value}")

    tiers = {
        item["id"]: item for item in store.tiers_payload["model_tiers"]
    }
    tier = tiers.get(binding["tier_id"])
    if tier is None:
        raise HTTPException(status_code=500, detail=f"tier missing from mirrored registry: {binding['tier_id']}")

    agents_by_name = {
        item["name"]: item for item in store.agents_payload["agents"]
    }
    resolved_roles: list[dict[str, Any]] = []
    for role_name in binding["role_names"]:
        agent_entry = agents_by_name.get(role_name)
        if agent_entry is None:
            raise HTTPException(status_code=500, detail=f"role missing from mirrored registry: {role_name}")
        resolved_roles.append(agent_entry)

    source_files = [
      "generated/runtime_seam_bindings.json",
      "generated/model_tier_registry.json",
      "generated/agent_registry.min.json",
    ]

    response: dict[str, Any] = {
        "ok": True,
        "layer": store.layer,
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
        for cohort in store.cohorts_payload["cohort_patterns"]:
            if binding["tier_id"] not in cohort["preferred_tier_ids"]:
                continue
            if not any(role_names.issubset(set(allowed_set)) for allowed_set in cohort["allowed_role_sets"]):
                continue
            cohort_hints.append(cohort)

        response["cohort_hints"] = cohort_hints
        response["source_files"] = source_files + ["generated/cohort_composition_registry.json"]

    return response


app = FastAPI(title="AoA federation route API")
STORE: SurfaceStore | None = None


@app.on_event("startup")
def startup() -> None:
    global STORE
    STORE = load_store(CONFIG_PATH)


def require_store() -> SurfaceStore:
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


@app.get("/health")
def health() -> dict[str, Any]:
    store = require_store()
    return {
        "ok": True,
        "layer": store.layer,
        "mirror_ready": True,
        "thin_routing_only": store.thin_routing_only,
    }


@app.get("/surface-status")
def surface_status() -> dict[str, Any]:
    store = require_store()
    files = {
        rel_path: {
            "present": (store.mirror_root / rel_path).is_file(),
            "mtime_utc": iso_mtime(store.mirror_root / rel_path),
        }
        for rel_path in store.required_files
    }
    return {
        "ok": True,
        "layer": store.layer,
        "mirror_root": str(store.mirror_root),
        "config_path": str(store.config_path),
        "thin_routing_only": store.thin_routing_only,
        "allow_free_text_task_routing": store.allow_free_text_task_routing,
        "required_files": files,
        "surface_metadata": {
            "agents": {
                "layer": store.agents_payload.get("layer"),
                "version": store.agents_payload.get("version"),
            },
            "tiers": {
                "layer": store.tiers_payload.get("layer"),
                "version": store.tiers_payload.get("version"),
            },
            "bindings": {
                "layer": store.bindings_payload.get("layer"),
                "version": store.bindings_payload.get("version"),
            },
            "cohorts": {
                "layer": store.cohorts_payload.get("layer"),
                "version": store.cohorts_payload.get("version"),
            },
        },
    }


@app.get("/agents")
def agents() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": store.agents_payload}


@app.get("/tiers")
def tiers() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": store.tiers_payload}


@app.get("/bindings")
def bindings() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": store.bindings_payload}


@app.get("/cohorts")
def cohorts() -> dict[str, Any]:
    store = require_store()
    return {"ok": True, "data": store.cohorts_payload}


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
