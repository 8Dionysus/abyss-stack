#!/usr/bin/env python3
"""Shared builder helpers for the abyss-stack diagnostic capsule."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC_SURFACE_CATALOG_PATH = (
    REPO_ROOT
    / "mechanics"
    / "diagnostic-spine"
    / "parts"
    / "diagnostic-surfaces"
    / "generated"
    / "diagnostic_surface_catalog.min.json"
)

SURFACE_PAYLOAD = {
    "schema_version": "abyss_stack_diagnostic_surface_catalog_v1",
    "owner_repo": "abyss-stack",
    "surface_kind": "runtime_surface",
    "authority_ref": "mechanics/diagnostic-spine/docs/DIAGNOSTIC_SPINE.md",
}

SURFACE_SPECS = (
    {
        "name": "diagnostic_target",
        "schema_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_target.schema.json",
        "example_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_target.min.example.json",
        "primary_question": "What exact runtime target is being diagnosed before any judgment?",
    },
    {
        "name": "diagnostic_session",
        "schema_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_session.schema.json",
        "example_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_session.min.example.json",
        "primary_question": "What normalized runtime diagnosis was actually observed on this pass?",
    },
    {
        "name": "diagnosis_companion",
        "schema_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnosis_companion.schema.json",
        "example_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnosis_companion.min.example.json",
        "primary_question": "How should symptom, probable cause, and owner hints stay review-shaped before repair?",
    },
    {
        "name": "reviewed_diagnosis_ref",
        "schema_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/reviewed_diagnosis_ref.schema.json",
        "example_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/reviewed_diagnosis_ref.min.example.json",
        "primary_question": "Has the current runtime-local diagnosis been reviewed enough to support repair handoff?",
    },
    {
        "name": "repair_handoff",
        "schema_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/repair_handoff.schema.json",
        "example_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/repair_handoff.min.example.json",
        "primary_question": "What bounded repair handoff is ready, blocked, or still review-only after diagnosis?",
    },
)

VALIDATION_REFS = [
    "scripts/validate_stack.py",
    "mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_validate_stack_diagnostic_spine.py",
    "mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_diagnostic_spine_contracts.py",
]


def resolve_ref(value: str) -> Path:
    target = REPO_ROOT / value
    if not target.exists():
        raise ValueError(f"missing ref target '{value}'")
    return target


def build_payload() -> dict[str, object]:
    resolve_ref(SURFACE_PAYLOAD["authority_ref"])
    for ref in VALIDATION_REFS:
        resolve_ref(ref)
    surfaces: list[dict[str, str]] = []
    for spec in SURFACE_SPECS:
        resolve_ref(spec["schema_ref"])
        resolve_ref(spec["example_ref"])
        surfaces.append(dict(spec))
    return {
        **SURFACE_PAYLOAD,
        "surfaces": surfaces,
        "validation_refs": list(VALIDATION_REFS),
    }


def render_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
