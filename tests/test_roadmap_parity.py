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
    assert "Current release contour" in roadmap
    assert "runtime-substrate hardening" in roadmap
    assert "without claiming live service mutation" in roadmap
    assert payload["schema_version"] == "abyss_stack_diagnostic_surface_catalog_v1"
    assert payload["authority_ref"] == "mechanics/diagnostic-spine/docs/DIAGNOSTIC_SPINE.md"
    assert "langchain-api" in roadmap
    assert "`llama.cpp`" in roadmap
    assert "LangGraph" in roadmap
    assert "antifragility wave two" in roadmap
    assert "diagnostic spine" in roadmap
    assert "`scripts/aoa-diagnose`" in roadmap
    assert "`mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json`" in roadmap

    current_release_surfaces = [
        "README.md",
        "CHARTER.md",
        "BOUNDARIES.md",
        "docs/PATHS.md",
        "docs/DEPLOYMENT.md",
        "scripts/aoa-sync-configs",
        "scripts/validate_stack.py",
        "scripts/release_check.py",
        "mechanics/diagnostic-spine/docs/DIAGNOSTIC_SPINE.md",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_target.schema.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_session.schema.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnosis_companion.schema.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/reviewed_diagnosis_ref.schema.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/repair_handoff.schema.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_target.min.example.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_session.min.example.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnosis_companion.min.example.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/reviewed_diagnosis_ref.min.example.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/repair_handoff.min.example.json",
        "scripts/aoa-diagnose",
        "scripts/_aoa_diagnose.py",
        "scripts/build_diagnostic_surface_catalog.py",
        "scripts/validate_diagnostic_surface_catalog.py",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_validate_stack_diagnostic_spine.py",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_diagnostic_spine_contracts.py",
        "mechanics/runtime-repair/docs/ANTIFRAGILITY_RUNTIME.md",
        "mechanics/runtime-repair/legacy/raw/RUNTIME_CHAOS_WAVE1.md",
        "mechanics/runtime-repair/docs/REPAIR_SAFE_CLOSEOUT.md",
        "mechanics/runtime-repair/legacy/artifacts/schemas/service_degradation_receipt_v1.json",
        "mechanics/runtime-repair/legacy/artifacts/schemas/repair_safe_closeout_receipt_v1.json",
        "mechanics/runtime-repair/legacy/artifacts/examples/service_degradation_receipt.example.json",
        "mechanics/runtime-repair/legacy/artifacts/examples/service_degradation_receipt.timeout-chaos.example.json",
        "mechanics/runtime-repair/legacy/artifacts/examples/service_degradation_receipt.honest-degradation.example.json",
        "mechanics/runtime-repair/legacy/artifacts/examples/service_degradation_receipt.retrieval-outage-honesty.example.json",
        "mechanics/runtime-repair/legacy/artifacts/examples/repair_safe_closeout_receipt.example.json",
        "mechanics/runtime-repair/legacy/artifacts/examples/repair_safe_closeout_receipt.timeout-chaos.example.json",
        "mechanics/runtime-repair/legacy/artifacts/examples/repair_safe_closeout_receipt.retrieval-outage-honesty.example.json",
        "mechanics/inference-pilots/docs/RUNTIME_WINNER_PROMOTION_LOOP.md",
        "mechanics/inference-pilots/docs/LLAMACPP_PILOT.md",
        "mechanics/machine-fit/docs/MACHINE_FIT_POLICY.md",
        "compose/tuning/llamacpp.runtime-fallback.yml",
        "compose/tuning/llamacpp.intel-285h.cpu-safe.yml",
        "compose/tuning/intel-text.ovms-qwen3-settings.yml",
        "mechanics/machine-fit/parts/inference-tuning/docs/model-cards/qwen3-openvino-family.md",
        "scripts/aoa-llamacpp-pilot",
        "mechanics/federation-seams/docs/MEMO_RUNTIME_SEAM.md",
        "mechanics/federation-seams/docs/EVAL_RUNTIME_SEAM.md",
        "mechanics/federation-seams/docs/PLAYBOOK_RUNTIME_SEAM.md",
        "mechanics/federation-seams/docs/KAG_RUNTIME_SEAM.md",
        "docs/SERVICE_CATALOG.md",
        "docs/PROFILES.md",
        "mechanics/federation-seams/docs/TOS_GRAPH_CURATION.md",
        "scripts/aoa-federated-check",
        "compose/modules/52-tos-graph.yml",
        "compose/profiles/curation.txt",
        "config-templates/Services/tos-graph/app/main.py",
    ]
    for surface in current_release_surfaces:
        assert (REPO_ROOT / surface).exists(), surface
        assert surface in roadmap
