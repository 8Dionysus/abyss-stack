#!/usr/bin/env python3
"""Shared builder helpers for the abyss-stack diagnostic capsule."""

from __future__ import annotations

import json
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "scripts").is_dir()
            and (candidate / "mechanics").is_dir()
        ):
            return candidate
    raise RuntimeError("could not locate abyss-stack repository root")


REPO_ROOT = find_repo_root(Path(__file__).resolve().parent)
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
    "authority_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md",
    "artifact_identity": {
        "artifact_class": "runtime_diagnostic_readmodel_catalog",
        "surface_state": "public_source_generated_runtime_diagnostic_catalog",
        "owner_repo": "abyss-stack",
        "authority_ref": "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md",
        "producer": (
            "scripts/build_diagnostic_surface_catalog.py from diagnostic_surface_catalog_common.py "
            "and diagnostic surface docs, schemas, and examples"
        ),
        "consumer_expectation": (
            "Verify owner_repo, surface_kind, authority_ref, surfaces, validation_refs, "
            "artifact_identity, catalog rebuild parity, and diagnostic validators before "
            "using this as runtime diagnostic navigation or repair-handoff orientation."
        ),
        "privacy_boundary": (
            "Public-safe source refs and examples only; no live Logs/diagnostics payloads, "
            "private host facts, secrets, rendered configs, models, or machine-local state."
        ),
        "content_identity": (
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/"
            "diagnostic_surface_catalog.min.json rendered from build_payload() and compared "
            "by build_diagnostic_surface_catalog --check plus validator."
        ),
        "abi_epoch": "abyss_stack_diagnostic_surface_catalog_v1",
        "contract_version": (
            "mechanics/diagnostic-spine/parts/diagnostic-surfaces/"
            "diagnostic_surface_catalog_common.py@"
            "abyss_stack_diagnostic_surface_catalog_v1#artifact_identity"
        ),
        "trust_layer": [
            "abi_contract_signature",
            "w3c_prov_lineage",
        ],
        "verification": [
            "python scripts/build_diagnostic_surface_catalog.py --check",
            "python scripts/validate_diagnostic_surface_catalog.py",
            "python scripts/validate_stack.py",
        ],
        "action": "ADD_CONSUMER_EXPECTATION",
    },
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
    "scripts/validators/diagnostic_spine.py",
    "tests/test_diagnostic_spine_validator_module.py",
    "mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_diagnostic_spine_surface_validator.py",
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
