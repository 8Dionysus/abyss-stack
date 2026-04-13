from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def load_json(relative_path: str) -> object:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def test_roadmap_names_current_runtime_posture_and_diagnostic_spine() -> None:
    roadmap = read_text("ROADMAP.md")
    payload = load_json("generated/diagnostic_surface_catalog.min.json")

    assert payload["schema_version"] == "abyss_stack_diagnostic_surface_catalog_v1"
    assert "langchain-api" in roadmap
    assert "`llama.cpp`" in roadmap
    assert "LangGraph" in roadmap
    assert "antifragility wave two" in roadmap
    assert "diagnostic spine" in roadmap
    assert "`scripts/aoa-diagnose`" in roadmap
    assert "`generated/diagnostic_surface_catalog.min.json`" in roadmap
