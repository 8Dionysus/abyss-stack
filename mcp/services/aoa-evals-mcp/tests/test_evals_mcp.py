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


def test_server_builds(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    assert build_server(workspace_root=tmp_path) is not None
