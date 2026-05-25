from __future__ import annotations

import json
from pathlib import Path

from aoa_evals_mcp.core import AoAEvalsMCPState
from aoa_evals_mcp.server import build_server


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def seed_evals(root: Path) -> None:
    evals = root / "aoa-evals"
    record = {
        "name": "aoa-bounded-change-quality",
        "category": "workflow",
        "status": "draft",
        "summary": "Checks bounded change quality and verification honesty.",
        "object_under_evaluation": "bounded repository change",
        "claim_type": "bounded",
        "baseline_mode": "none",
        "report_format": "summary-with-breakdown",
        "eval_path": "evals/workflow/aoa-bounded-change-quality/EVAL.md",
        "evidence_kinds": ["change_set", "verification_result"],
        "proof_surface_kinds": ["fixture_contract"],
        "export_ready": False,
    }
    write_json(
        evals / "generated/eval_catalog.min.json",
        {"catalog_version": "test", "source_of_truth": ["evals"], "evals": [record]},
    )
    write_json(
        evals / "generated/eval_capsules.json",
        {
            "capsule_version": "test",
            "source_of_truth": ["evals"],
            "evals": [
                {
                    "name": record["name"],
                    "summary": record["summary"],
                    "use_when_short": "a bounded change has reviewable evidence",
                    "what_this_does_not_prove": "general agent competence",
                }
            ],
        },
    )
    write_json(
        evals / "generated/eval_sections.full.json",
        {
            "section_version": "test",
            "source_of_truth": ["evals"],
            "evals": [
                {
                    "name": record["name"],
                    "category": "workflow",
                    "status": "draft",
                    "eval_path": record["eval_path"],
                    "sections": [
                        {
                            "key": "intent",
                            "heading": "Intent",
                            "content_markdown": "Use this eval for bounded change review.",
                        }
                    ],
                }
            ],
        },
    )
    write_json(
        evals / "generated/comparison_spine.json",
        {
            "comparison_spine_version": "test",
            "source_of_truth": ["evals"],
            "evals": [
                {
                    "name": record["name"],
                    "baseline_mode": "none",
                    "selection_summary": "Need bounded change quality?",
                }
            ],
        },
    )
    write_json(
        evals / "generated/eval_report_index.min.json",
        {
            "schema_version": "test",
            "source_of_truth": ["evals"],
            "reports": [
                {
                    "report_id": "example",
                    "eval_name": record["name"],
                    "source_bundle_ref": record["eval_path"],
                    "receipt_status": "not_a_receipt",
                }
            ],
        },
    )
    template = {
        "template_kind": "artifact_to_verdict_hook",
        "template_name": "bounded-change-hook",
        "eval_anchor": record["name"],
        "verdict_bundle_ref": f"repo:aoa-evals/{record['eval_path']}",
        "required_runtime_artifacts": ["change_set", "verification_result"],
        "review_required": True,
        "candidate_acceptance_posture": "candidate_until_eval_review",
    }
    write_json(
        evals / "mechanics/audit/parts/candidate-readers/generated/runtime_candidate_template_index.min.json",
        {"schema_version": 1, "layer": "aoa-evals", "source_of_truth": {}, "templates": [template]},
    )
    write_json(
        evals / "mechanics/audit/parts/candidate-readers/generated/runtime_candidate_intake.min.json",
        {"schema_version": 1, "layer": "aoa-evals", "source_of_truth": {}, "templates": [template]},
    )
    write_json(
        evals
        / "mechanics/audit/parts/selected-evidence-packets/schemas/runtime-evidence-selection.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": True,
            "required": [
                "surface_type",
                "selection_id",
                "source_repo",
                "selected_evidence",
                "review_posture",
            ],
            "properties": {
                "surface_type": {"const": "runtime_evidence_selection"},
                "selection_id": {"type": "string"},
                "source_repo": {"const": "abyss-stack"},
                "selected_evidence": {"type": "array", "minItems": 1},
                "review_posture": {
                    "type": "object",
                    "required": ["human_review_required"],
                    "properties": {"human_review_required": {"type": "boolean"}},
                },
            },
        },
    )
    write_json(
        evals
        / "mechanics/audit/parts/artifact-verdict-hooks/schemas/artifact-to-verdict-hook.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": True,
            "required": ["surface_type", "hook_id", "eval_anchor", "report_expectation"],
            "properties": {
                "surface_type": {"const": "artifact_to_verdict_hook"},
                "hook_id": {"type": "string"},
                "eval_anchor": {"type": "string"},
                "report_expectation": {
                    "type": "object",
                    "required": ["review_required"],
                    "properties": {"review_required": {"type": "boolean"}},
                },
            },
        },
    )
    write_json(
        evals / "mechanics/proof-object/parts/eval-authoring/schemas/eval-need.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": True,
            "required": [
                "schema_version",
                "name",
                "proof_question",
                "origin_need",
                "summary",
                "object_under_evaluation",
                "category",
                "claim_type",
                "baseline_mode",
                "report_format",
                "authoring_route",
                "expected_use_when",
                "blind_spot_notes",
            ],
            "properties": {
                "schema_version": {"const": "eval_need_v1"},
                "name": {"type": "string", "pattern": "^aoa-[a-z0-9-]+$"},
                "proof_question": {"type": "string", "minLength": 12},
                "origin_need": {"type": "string", "minLength": 12},
                "summary": {"type": "string", "minLength": 12},
                "object_under_evaluation": {"type": "string", "minLength": 3},
                "category": {"enum": ["workflow", "boundary", "artifact"]},
                "claim_type": {"enum": ["bounded", "comparative"]},
                "baseline_mode": {"enum": ["none", "fixed-baseline"]},
                "report_format": {"enum": ["summary", "summary-with-breakdown"]},
                "authoring_route": {
                    "enum": [
                        "existing_eval_route",
                        "candidate_evidence_packet",
                        "quest_record",
                        "new_draft_bundle",
                    ]
                },
                "expected_use_when": {"type": "array", "minItems": 1},
                "blind_spot_notes": {"type": "array", "minItems": 1},
                "related_eval_refs": {"type": "array", "minItems": 1},
                "candidate_evidence_refs": {"type": "array", "minItems": 1},
                "quest_refs": {"type": "array", "minItems": 1},
            },
            "allOf": [
                {
                    "if": {"properties": {"authoring_route": {"const": "existing_eval_route"}}},
                    "then": {"required": ["related_eval_refs"]},
                },
                {
                    "if": {"properties": {"authoring_route": {"const": "candidate_evidence_packet"}}},
                    "then": {"required": ["candidate_evidence_refs"]},
                },
                {
                    "if": {"properties": {"authoring_route": {"const": "quest_record"}}},
                    "then": {"required": ["quest_refs"]},
                },
            ],
        },
    )


def seed_runtime_candidate_export(root: Path) -> dict[str, object]:
    packet = {
        "surface_type": "runtime_evidence_selection",
        "selection_id": "bounded-change-smoke",
        "source_repo": "abyss-stack",
        "target_eval": "aoa-bounded-change-quality",
        "selected_evidence": [
            {
                "artifact_ref": "local:change-set",
                "evidence_role": "summary",
                "summary_only": True,
            }
        ],
        "review_posture": {
            "human_review_required": True,
        },
    }
    export = {
        "artifact_kind": "aoa.runtime-eval-evidence-selection-candidate",
        "schema_version": "1",
        "capture_mode": "private",
        "exported_at": "2026-05-25T00:00:00Z",
        "exported_by": "scripts/aoa-export-runtime-evidence-selection",
        "record_id": "2026-05-25T000000Z__runtime-evidence-selection__bounded-change-smoke",
        "title": "runtime evidence selection bounded-change-smoke",
        "summary": "Bounded runtime evidence selection candidate.",
        "selection_id": "bounded-change-smoke",
        "source_input_ref": "local:/tmp/bounded-change-smoke.json",
        "source_input_sha256": "0" * 64,
        "aoa_evals_contract_refs": ["local:/srv/AbyssOS/abyss-stack/Knowledge/federation/aoa-evals/schemas/runtime-evidence-selection.schema.json"],
        "candidate_payload": packet,
    }
    stack = root / "abyss-stack"
    write_json(
        stack / "Logs/eval-exports/latest/runtime-evidence-selection/bounded-change-smoke.private.json",
        export,
    )
    write_json(
        stack
        / "Logs/eval-exports/records/2026-05-25T000000Z__runtime-evidence-selection__bounded-change-smoke/candidate.private.json",
        export,
    )
    return export


def test_select_inspect_expand_and_skeleton(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    selection = state.select("bounded verification", {"category": "workflow"})
    assert selection["matches"][0]["name"] == "aoa-bounded-change-quality"

    inspection = state.inspect_bundle("aoa-bounded-change-quality")
    assert inspection["catalog"]["claim_type"] == "bounded"
    assert inspection["authority_boundary"]["stronger_owner"] == "bundle-local EVAL.md and eval.yaml"

    expanded = state.expand_bundle("aoa-bounded-change-quality", "intent")
    assert expanded["sections"][0]["heading"] == "Intent"

    skeleton = state.report_skeleton("aoa-bounded-change-quality", ["artifact:change_set"])
    assert skeleton["candidate_only"] is True
    assert skeleton["sections"]["verdict"] == "UNSET: MCP must not compute verdicts"


def test_find_or_propose_routes_existing_eval_and_runtime_export(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    export = seed_runtime_candidate_export(tmp_path)
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    result = state.find_or_propose("bounded change verification runtime evidence")

    assert result["schema"] == "aoa_evals_find_or_propose_v1"
    assert result["read_only"] is True
    assert result["source_mutation_allowed"] is False
    assert result["outcome"] == "existing_route_required"
    assert result["existing_matches"][0]["name"] == "aoa-bounded-change-quality"
    assert result["proposal_context"]["packet"]["schema_version"] == "eval_need_v1"
    assert result["proposal_context"]["packet"]["authoring_route"] == "existing_eval_route"
    assert result["proposal_validation"]["valid"] is True
    assert result["runtime_candidate_export_refs"][0]["record_id"] == export["record_id"]
    assert result["runtime_candidate_export_refs"][0]["candidate_payload_included"] is False
    assert not (tmp_path / "aoa-evals/evals/workflow").exists()


def test_resources_and_runtime_templates(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    catalog = state.read_resource("aoa-evals://catalog")
    assert catalog["count"] == 1
    bundle = state.read_resource("aoa-evals://bundle/aoa-bounded-change-quality")
    assert bundle["name"] == "aoa-bounded-change-quality"
    sections = state.read_resource("aoa-evals://bundle/aoa-bounded-change-quality/sections")
    assert sections["sections"][0]["key"] == "intent"
    comparison = state.read_resource("aoa-evals://comparison-spine")
    assert comparison["evals"][0]["baseline_mode"] == "none"
    templates = state.runtime_evidence_template("aoa-bounded-change-quality")
    assert templates["templates"][0]["template_name"] == "bounded-change-hook"
    status = state.read_resource("aoa-evals://runtime-status")
    assert status["catalog_count"] == 1
    schemas = state.read_resource("aoa-evals://runtime-evidence/schema")
    assert schemas["schemas"]["runtime_evidence_selection"]["present"] is True


def test_validate_evidence_candidate_is_shape_only(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)
    packet = {
        "surface_type": "runtime_evidence_selection",
        "selection_id": "bounded-change-smoke",
        "source_repo": "abyss-stack",
        "target_eval": "aoa-bounded-change-quality",
        "selected_evidence": [
            {
                "artifact_ref": "local:change-set",
                "evidence_role": "summary",
                "summary_only": True,
            }
        ],
        "review_posture": {
            "human_review_required": True,
        },
    }

    result = state.validate_evidence_candidate(packet)

    assert result["valid"] is True
    assert result["candidate_posture"] == "valid_shape_only_until_bundle_local_review"
    assert result["matched_eval_refs"] == ["aoa-bounded-change-quality"]


def test_validate_evidence_candidate_rejects_review_bypass(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)
    packet = {
        "surface_type": "runtime_evidence_selection",
        "selection_id": "bounded-change-smoke",
        "source_repo": "abyss-stack",
        "selected_evidence": [{"artifact_ref": "local:change-set"}],
        "review_posture": {"human_review_required": False},
    }

    result = state.validate_evidence_candidate(packet)

    assert result["valid"] is False
    assert "review_posture/human_review_required must be true" in result["issues"]


def test_runtime_candidate_exports_are_read_only_validated_records(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    export = seed_runtime_candidate_export(tmp_path)
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    listing = state.runtime_candidate_exports()

    assert listing["count"] == 1
    assert listing["private_payloads_included"] is False
    candidate = listing["candidates"][0]
    assert candidate["record_id"] == export["record_id"]
    assert candidate["candidate_payload_included"] is False
    assert candidate["validation"]["valid"] is True
    assert sorted(candidate["locations"]) == ["latest", "record"]

    detail = state.read_runtime_candidate_export(str(export["record_id"]))
    assert detail["schema"] == "aoa_evals_runtime_candidate_export_v1"
    assert detail["candidate_payload_included"] is False
    assert "candidate_payload" not in detail
    assert detail["source_input_sha256"] == "0" * 64

    payload_detail = state.read_runtime_candidate_export("bounded-change-smoke", include_payload=True)
    assert payload_detail["candidate_payload_included"] is True
    assert payload_detail["candidate_payload"]["selection_id"] == "bounded-change-smoke"


def test_server_builds(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    assert build_server(workspace_root=tmp_path) is not None
