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
    readme = read_text("README.md")
    changelog = read_text("CHANGELOG.md")
    payload = load_json("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json")

    assert "> Current release: `v0.2.2`" in readme
    assert "## [0.2.2] - 2026-04-23" in changelog
    assert "`v0.2.2`" in roadmap
    assert "## Authority" in roadmap
    assert "## Update Rule" in roadmap
    assert "## Current Released Contour" not in roadmap
    assert "runtime-substrate hardening" in roadmap
    assert "not a claim of live" in roadmap
    assert "service mutation" in roadmap
    assert "mechanics/<package>/ROADMAP.md" in roadmap
    assert "mechanics/<package>/LANDING_LOG.md" in roadmap
    assert "CHANGELOG.md" in roadmap
    assert "docs/decisions/" in roadmap
    assert "Structured bootstrap" not in roadmap
    assert "Service extraction" not in roadmap
    assert "Current checked anchors" not in roadmap
    assert "diagnostic_target.min.example.json" not in roadmap
    assert "service-degradation-receipt.timeout-chaos.example.json" not in roadmap
    assert "test_validate_stack_diagnostic_spine.py" not in roadmap
    assert "RUNTIME_CHAOS_WAVE1.md" not in roadmap
    assert payload["schema_version"] == "abyss_stack_diagnostic_surface_catalog_v1"
    assert payload["authority_ref"] == "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md"
    assert "langchain-api" in roadmap
    assert "`llama.cpp`" in roadmap
    assert "LangGraph" in roadmap
    assert "antifragility repair posture" in roadmap
    assert "diagnostic spine" in roadmap
