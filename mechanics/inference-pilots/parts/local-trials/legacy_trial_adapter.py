#!/usr/bin/env python3
"""Role-level adapter for the preserved local-trials compatibility runner."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aoa_local_ai_trials as _bridge


@dataclass(frozen=True)
class CompatibilityGate:
    role: str
    wire_id: str
    index_name: str
    closeout_name: str | None = None


RUNTIME_GATE = CompatibilityGate(
    role="runtime compatibility gate",
    wire_id="W0",
    index_name="W0-runtime-index.json",
)
EDIT_GATE = CompatibilityGate(
    role="edit fixture compatibility gate",
    wire_id="W4",
    index_name="W4-langgraph-sidecar-index.json",
    closeout_name="W4-closeout.json",
)
EDIT_GATE_INDEX_STEM = "W4-langgraph-sidecar-index"
LONG_HORIZON_INDEX = CompatibilityGate(
    role="long-horizon pilot index",
    wire_id="W5",
    index_name="W5-runtime-index.json",
)
BOUNDED_AUTONOMY_INDEX = CompatibilityGate(
    role="bounded-autonomy pilot index",
    wire_id="W6",
    index_name="W6-runtime-index.json",
)

WIRE_ID_FIELD = "wave_id"
WIRE_TITLE_FIELD = "wave_title"
WIRE_SUMMARY_FIELD = "wave_summary"
WIRE_INDEX_ARTIFACT_KIND = "aoa.local-ai-trial.wave-index"
WIRE_INDEX_SCHEMA_NAME = "wave-index.schema.json"
WIRE_INDEX_SCHEMA = _bridge.WAVE_INDEX_SCHEMA


def runtime_gate_run_command() -> list[str]:
    return ["run-wave", RUNTIME_GATE.wire_id]


def edit_gate_catalog(catalog: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return catalog[EDIT_GATE.wire_id]


def edit_gate_catalog_payload(cases: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {EDIT_GATE.wire_id: cases}


def edit_gate_case_dir(log_root: Path, case_id: str) -> Path:
    return _bridge.case_dir(log_root, EDIT_GATE.wire_id, case_id)


def edit_gate_case_report_name(case_id: str) -> str:
    return _bridge.case_report_name(EDIT_GATE.wire_id, case_id)


def edit_gate_approval_path(log_root: Path, case_id: str) -> Path:
    return edit_gate_case_dir(log_root, case_id) / "artifacts" / "approval.status.json"


def render_edit_gate_index_md(index_payload: dict[str, Any]) -> str:
    return _bridge.render_wave_index_md(index_payload)


def edit_gate_index_fields(*, title: str, summary: str) -> dict[str, str]:
    return {
        "artifact_kind": WIRE_INDEX_ARTIFACT_KIND,
        WIRE_ID_FIELD: EDIT_GATE.wire_id,
        WIRE_TITLE_FIELD: title,
        WIRE_SUMMARY_FIELD: summary,
    }


def edit_gate_wire_id_entry() -> dict[str, str]:
    return {WIRE_ID_FIELD: EDIT_GATE.wire_id}
