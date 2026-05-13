#!/usr/bin/env python3
"""Owner-local quest surface helpers for abyss-stack quest records."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

QUEST_SURFACE_ROOT = Path("quests")
QUEST_IDS = (
    "ABYSS-STACK-Q-0001",
    "ABYSS-STACK-Q-0002",
    "ABYSS-STACK-Q-0003",
    "ABYSS-STACK-Q-0004",
    "ABYSS-STACK-Q-0005",
    "ABYSS-STACK-Q-0006",
    "ABYSS-STACK-Q-0007",
    "ABYSS-STACK-Q-0008",
)
QUEST_ROUTES = {
    "ABYSS-STACK-Q-0001": ("stack", "done"),
    "ABYSS-STACK-Q-0002": ("profiles", "triaged"),
    "ABYSS-STACK-Q-0003": ("stack", "done"),
    "ABYSS-STACK-Q-0004": ("machine-fit", "captured"),
    "ABYSS-STACK-Q-0005": ("rpg-runtime", "captured"),
    "ABYSS-STACK-Q-0006": ("rpg-runtime", "captured"),
    "ABYSS-STACK-Q-0007": ("diagnostics", "captured"),
    "ABYSS-STACK-Q-0008": ("tos-graph", "captured"),
}
QUEST_CATALOG_EXAMPLE_PATH = QUEST_SURFACE_ROOT / "examples" / "quest_catalog.min.example.json"
QUEST_DISPATCH_EXAMPLE_PATH = QUEST_SURFACE_ROOT / "examples" / "quest_dispatch.min.example.json"


def quest_source_path(quest_id: str) -> Path:
    lane, state = QUEST_ROUTES[quest_id]
    return QUEST_SURFACE_ROOT / lane / state / f"{quest_id}.yaml"


def load_structured_object(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(text)
    except ImportError:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must parse as an object")
    return payload


def load_quest_payload(repo_root: Path, quest_id: str) -> dict[str, object]:
    return load_structured_object(repo_root / quest_source_path(quest_id))


def build_expected_quest_catalog_entry(quest_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    source_path = quest_source_path(quest_id).as_posix()
    return {
        "id": quest_id,
        "title": payload["title"],
        "repo": payload["repo"],
        "lane": payload["lane"],
        "theme_ref": payload.get("theme_ref", ""),
        "milestone_ref": payload.get("milestone_ref", ""),
        "state": payload["state"],
        "band": payload["band"],
        "kind": payload["kind"],
        "difficulty": payload["difficulty"],
        "risk": payload["risk"],
        "owner_surface": payload["owner_surface"],
        "source_path": source_path,
        "public_safe": payload["public_safe"],
    }


def build_expected_quest_dispatch_entry(quest_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    source_path = quest_source_path(quest_id).as_posix()
    if quest_id == "ABYSS-STACK-Q-0003":
        requires_artifacts = [
            "bounded_plan",
            "guardrail_check",
            "verification_result",
            "rollout_decision",
        ]
    elif quest_id == "ABYSS-STACK-Q-0004":
        requires_artifacts = [
            "bounded_plan",
            "work_result",
        ]
    else:
        requires_artifacts = [
            "bounded_plan",
            "work_result",
            "verification_result",
        ]

    activation = payload.get("activation")
    if not isinstance(activation, dict):
        raise RuntimeError(f"{quest_id} activation must be an object")

    return {
        "schema_version": "quest_dispatch_v1",
        "id": quest_id,
        "repo": payload["repo"],
        "lane": payload["lane"],
        "state": payload["state"],
        "band": payload["band"],
        "difficulty": payload["difficulty"],
        "risk": payload["risk"],
        "control_mode": payload["control_mode"],
        "delegate_tier": payload["delegate_tier"],
        "split_required": payload["split_required"],
        "write_scope": payload["write_scope"],
        "requires_artifacts": requires_artifacts,
        "activation_mode": activation["mode"],
        "source_path": source_path,
        "public_safe": payload["public_safe"],
        "fallback_tier": payload["fallback_tier"],
        "wrapper_class": payload["wrapper_class"],
    }
