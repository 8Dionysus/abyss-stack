from __future__ import annotations

import json
from pathlib import Path

import pytest

from aoa_evals_mcp.core import AoAEvalsMCPState
from aoa_evals_mcp.server import build_server


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def valid_eval_need_packet(name: str = "aoa-memory-guardrail-pressure") -> dict[str, object]:
    return {
        "schema_version": "eval_need_v1",
        "name": name,
        "proof_question": "Does memory guardrail pressure route to bounded proof review?",
        "origin_need": "A local memory handoff needs a route before central proof adoption.",
        "summary": "Checks whether memory guardrail pressure stays below proof authority.",
        "object_under_evaluation": "memory guardrail handoff",
        "category": "boundary",
        "claim_type": "bounded",
        "baseline_mode": "none",
        "report_format": "summary-with-breakdown",
        "authoring_route": "candidate_evidence_packet",
        "expected_use_when": ["memory guardrail pressure appears locally"],
        "blind_spot_notes": ["does not accept a central proof verdict"],
        "candidate_evidence_refs": ["mechanics/consumer-handoff/parts/eval-guardrail-handoff/"],
    }


def local_port_inventory_contract() -> dict[str, object]:
    proof_boundary = "central proof adoption, verdicts, scoring, regression, and proof doctrine stay in aoa-evals"

    def route(route_key: str, route_name: str, subskill: str, action: str) -> dict[str, str]:
        return {
            "route_key": route_key,
            "route": route_name,
            "subskill": subskill,
            "action": action,
            "proof_boundary": proof_boundary,
        }

    return {
        "schema_version": "aoa_local_eval_port_inventory_contract_v1",
        "inventory_schema_version": "os_abyss_local_eval_port_inventory_v1",
        "layer": "aoa-evals-local-port-inventory",
        "proof_owner_repo": "aoa-evals",
        "authority_boundary": (
            "Repo-local eval ports carry intake, suites, reports, and pressure evidence only. "
            "Central verdict, scoring, regression, proof doctrine, and central bundle adoption remain in aoa-evals."
        ),
        "source_of_truth": {
            "local_port_standard": "docs/guides/LOCAL_EVAL_PORT_STANDARD.md",
            "local_port_validator": "scripts/validate_local_eval_port.py",
            "central_eval_catalog": "generated/eval_catalog.min.json",
            "mcp_contract": "docs/architecture/AOA_EVALS_MCP_CONTRACT.md",
            "inventory_contract": "docs/architecture/local_eval_port_inventory.contract.v1.json",
        },
        "inventory_statuses": ["missing", "stale_candidate", "invalid", "skeleton", "active"],
        "summary_keys": [
            "repos",
            "validator_ok",
            "validator_failed",
            "with_local_port",
            "with_detected_pressure",
            "excluded_repos",
            "missing",
            "stale_candidate",
            "invalid",
            "skeleton",
            "active",
        ],
        "route_recommendations": [
            route(
                "missing_no_pressure",
                "stop",
                "none",
                "Do not create a local eval port unless current repo work produces real eval pressure.",
            ),
            route(
                "stale_local_eval_surface_review",
                "aoa-eval-select",
                "aoa-eval-select",
                "Inspect the existing eval-like surface before mutation; add a valid port only if current pressure warrants it.",
            ),
            route(
                "invalid_port_repair",
                "repair-local-port",
                "aoa-eval-select",
                "Repair the local eval-port shape and rerun the validator before applying or designing evals.",
            ),
            route(
                "invalid_active_repair",
                "repair-local-port",
                "aoa-eval-select",
                "Repair the local eval-port shape and rerun the validator before applying or designing evals.",
            ),
            route(
                "central_overlap_apply_existing_first",
                "aoa-eval-select",
                "aoa-eval-select",
                "Local pressure overlaps central eval names; inspect and apply the existing central route before designing a new local suite.",
            ),
            route(
                "valid_skeleton_keep_dormant",
                "stop",
                "none",
                "Keep the valid skeleton dormant until a current task creates local eval pressure.",
            ),
            route(
                "local_bundle_central_review_candidate",
                "central-adoption-review",
                "aoa-eval-select",
                "Review the local draft bundle against central aoa-evals routes before any adoption or normalization.",
            ),
            route(
                "active_suite_apply_or_regression_check",
                "aoa-eval-apply",
                "aoa-eval-apply",
                "Use the local suite as a candidate deterministic check or regression surface; keep scoring and verdict authority central.",
            ),
            route(
                "active_intake_select_then_apply_or_design",
                "aoa-eval-select",
                "aoa-eval-select",
                "Select existing local and central eval routes first, then apply or design only after duplicate-fit review.",
            ),
            route(
                "active_reports_only_suite_extraction_or_review",
                "aoa-eval-design",
                "aoa-eval-design",
                "Treat reports-only pressure as a candidate for suite extraction or central review, not proof acceptance.",
            ),
            route(
                "active_without_detected_pressure",
                "repair-local-port",
                "aoa-eval-select",
                "Declared active state has no detected pressure files; repair status or add the missing reviewed pressure surface.",
            ),
        ],
    }


def seed_local_eval_port(root: Path, repo: str = "aoa-memo", *, status: str = "skeleton") -> Path:
    repo_root = root / repo
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    write_text(
        repo_root / "evals/PORT.yaml",
        f"""schema_version: local_eval_port_v1
owner_repo: {repo}
status: {status}
proof_owner_repo: aoa-evals
default_intake_schema: eval_need_v1
local_role: repo-local eval pressure, fixtures, suites, and reports
central_boundary: no verdict, scoring, regression, or proof doctrine authority
""",
    )
    write_text(repo_root / "evals/AGENTS.md", "Route verdict, scoring, regression, and proof doctrine to aoa-evals.\n")
    write_text(repo_root / "evals/README.md", "Local port; aoa-evals owns verdict, scoring, regression, and proof doctrine.\n")
    write_text(repo_root / "evals/intake/README.md", "# Intake\n")
    write_text(repo_root / "evals/suites/README.md", "# Suites\n")
    write_text(repo_root / "evals/reports/README.md", "# Reports\n")
    return repo_root


def seed_evals(root: Path) -> None:
    evals = root / "aoa-evals"
    write_json(
        evals / "docs/architecture/local_eval_port_inventory.contract.v1.json",
        local_port_inventory_contract(),
    )
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


def seed_named_runtime_candidate_export(
    root: Path,
    *,
    record_id: str,
    candidate_id: str,
    title: str,
    summary: str,
) -> dict[str, object]:
    packet = {
        "surface_type": "runtime_evidence_selection",
        "selection_id": candidate_id,
        "source_repo": "abyss-stack",
        "selected_evidence": [
            {
                "artifact_ref": f"local:{candidate_id}",
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
        "exported_at": "2026-05-25T00:01:00Z",
        "exported_by": "scripts/aoa-export-runtime-evidence-selection",
        "record_id": record_id,
        "title": title,
        "summary": summary,
        "selection_id": candidate_id,
        "source_input_ref": f"local:/tmp/{candidate_id}.json",
        "source_input_sha256": "1" * 64,
        "aoa_evals_contract_refs": ["local:/srv/AbyssOS/abyss-stack/Knowledge/federation/aoa-evals/schemas/runtime-evidence-selection.schema.json"],
        "candidate_payload": packet,
    }
    stack = root / "abyss-stack"
    write_json(
        stack / f"Logs/eval-exports/latest/runtime-evidence-selection/{candidate_id}.private.json",
        export,
    )
    write_json(
        stack / f"Logs/eval-exports/records/{record_id}/candidate.private.json",
        export,
    )
    return export


def seed_unrelated_artifact_hook_export(root: Path) -> dict[str, object]:
    packet = {
        "surface_type": "artifact_to_verdict_hook",
        "hook_id": "approval-to-boundary-hook",
        "eval_anchor": "aoa-bounded-change-quality",
        "report_expectation": {
            "review_required": True,
        },
    }
    export = {
        "artifact_kind": "aoa.runtime-artifact-hook-candidate",
        "schema_version": "1",
        "capture_mode": "private",
        "exported_at": "2026-05-25T00:02:00Z",
        "exported_by": "scripts/aoa-export-artifact-hook-candidate",
        "record_id": "2026-05-25T000200Z__artifact-hook__approval-to-boundary-hook",
        "title": "artifact hook to and boundary noise",
        "summary": "Artifact hook with common route words that must not match unrelated runtime latency questions.",
        "hook_id": "approval-to-boundary-hook",
        "source_input_ref": "local:/tmp/approval-to-boundary-hook.json",
        "source_input_sha256": "2" * 64,
        "aoa_evals_contract_refs": ["local:/srv/AbyssOS/abyss-stack/Knowledge/federation/aoa-evals/schemas/artifact-to-verdict-hook.schema.json"],
        "candidate_payload": packet,
    }
    stack = root / "abyss-stack"
    write_json(
        stack / "Logs/eval-exports/latest/artifact-hook/approval-to-boundary-hook.private.json",
        export,
    )
    write_json(
        stack / f"Logs/eval-exports/records/{export['record_id']}/candidate.private.json",
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


def test_find_or_propose_uses_significant_runtime_export_tokens(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    latency_export = seed_named_runtime_candidate_export(
        tmp_path,
        record_id="2026-05-25T000100Z__runtime-evidence-selection__workhorse-q4-vs-q6-latency-tradeoff",
        candidate_id="workhorse-q4-vs-q6-latency-tradeoff",
        title="runtime evidence selection workhorse q4 vs q6 latency tradeoff",
        summary="Bounded runtime evidence selection candidate for a Workhorse latency and VRAM tradeoff.",
    )
    noise_export = seed_unrelated_artifact_hook_export(tmp_path)
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    result = state.find_or_propose(
        "Compare Workhorse q4 and q6 runtime variants to determine the bounded latency versus VRAM tradeoff.",
        {
            "name": "aoa-runtime-latency-tradeoff",
            "authoring_route": "new_draft_bundle",
            "candidate_evidence_refs": [f"runtime-candidate-export:{latency_export['record_id']}"],
        },
    )

    record_ids = [ref["record_id"] for ref in result["runtime_candidate_export_refs"]]
    assert record_ids == [latency_export["record_id"]]
    assert noise_export["record_id"] not in record_ids
    assert result["proposal_context"]["packet"]["candidate_evidence_refs"] == [
        f"runtime-candidate-export:{latency_export['record_id']}"
    ]


def test_find_or_propose_does_not_treat_non_runtime_refs_as_export_selectors(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    latency_export = seed_named_runtime_candidate_export(
        tmp_path,
        record_id="2026-05-25T000100Z__runtime-evidence-selection__workhorse-q4-vs-q6-latency-tradeoff",
        candidate_id="workhorse-q4-vs-q6-latency-tradeoff",
        title="runtime evidence selection workhorse q4 vs q6 latency tradeoff",
        summary="Bounded runtime evidence selection candidate for a Workhorse latency and VRAM tradeoff.",
    )
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    result = state.find_or_propose(
        "Compare Workhorse q4 and q6 runtime variants to determine the bounded latency versus VRAM tradeoff.",
        {
            "name": "aoa-runtime-latency-tradeoff",
            "authoring_route": "new_draft_bundle",
            "candidate_evidence_refs": ["artifact:review-note"],
        },
    )

    record_ids = [ref["record_id"] for ref in result["runtime_candidate_export_refs"]]
    assert record_ids == [latency_export["record_id"]]
    assert result["proposal_context"]["packet"]["candidate_evidence_refs"] == [
        "artifact:review-note",
        f"runtime-candidate-export:{latency_export['record_id']}",
    ]


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


def test_runtime_candidate_exports_report_shape_invalid_private_candidates(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    stale_payload = {
        "surface_type": "runtime_evidence_selection",
        "selection_id": "old-shape-smoke",
        "selected_evidence": [{"artifact_ref": "local:old-shape"}],
        "review_required": True,
    }
    export = {
        "artifact_kind": "aoa.runtime-eval-evidence-selection-candidate",
        "schema_version": "1",
        "capture_mode": "private",
        "exported_at": "2026-05-25T00:03:00Z",
        "exported_by": "scripts/aoa-export-runtime-evidence-selection",
        "record_id": "2026-05-25T000300Z__runtime-evidence-selection__old-shape-smoke",
        "title": "runtime evidence selection old-shape-smoke",
        "summary": "Old-shape private candidate that must be reported, not accepted.",
        "selection_id": "old-shape-smoke",
        "source_input_ref": "local:/tmp/old-shape-smoke.json",
        "source_input_sha256": "3" * 64,
        "aoa_evals_contract_refs": ["local:/srv/AbyssOS/abyss-stack/Knowledge/federation/aoa-evals/schemas/runtime-evidence-selection.schema.json"],
        "candidate_payload": stale_payload,
    }
    write_json(
        tmp_path / "abyss-stack/Logs/eval-exports/latest/runtime-evidence-selection/old-shape-smoke.private.json",
        export,
    )
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    listing = state.runtime_candidate_exports()

    assert listing["count"] == 1
    assert listing["invalid_count"] == 0
    assert listing["candidate_validation"]["invalid_shape_count"] == 1
    assert listing["candidate_validation"]["latest_invalid_shape"][0]["record_id"] == export["record_id"]
    candidate = listing["candidates"][0]
    assert candidate["validation"]["valid"] is False
    assert candidate["candidate_posture"] == "runtime_export_is_private_candidate_not_accepted_proof"

    detail = state.read_runtime_candidate_export("old-shape-smoke")
    assert detail["candidate_payload_included"] is False
    assert detail["validation"]["valid"] is False
    assert "candidate_payload" not in detail


def test_local_ports_are_first_class_resources(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    seed_local_eval_port(tmp_path, status="active")
    write_json(
        tmp_path / "aoa-memo/evals/intake/memory-guardrail.eval_need.json",
        valid_eval_need_packet(),
    )
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    listing = state.local_ports()
    assert listing["schema"] == "aoa_evals_local_ports_v1"
    assert listing["inventory_contract"]["schema_version"] == "aoa_local_eval_port_inventory_contract_v1"
    assert listing["inventory_contract"]["contract_source"] == "aoa-evals"
    assert listing["inventory_contract"]["contract_ref"].endswith(
        "aoa-evals/docs/architecture/local_eval_port_inventory.contract.v1.json"
    )
    assert listing["count"] == 1
    assert listing["ports"][0]["repo"] == "aoa-memo"
    assert listing["ports"][0]["counts"]["intake"] == 1
    assert listing["ports"][0]["validation"]["valid"] is True

    detail = state.read_resource("aoa-evals://local-port/aoa-memo")
    assert detail["schema"] == "aoa_evals_local_port_v1"
    assert detail["intake"][0]["valid"] is True
    assert detail["read_only"] is True

    intake = state.read_resource("aoa-evals://local-port/aoa-memo/intake")
    assert intake["intake"][0]["name"] == "aoa-memory-guardrail-pressure"


def test_local_ports_inventory_covers_workspace_git_roots_and_nested_repos(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    (workspace / ".git").mkdir(parents=True)
    seed_evals(workspace)
    (workspace / "aoa-evals/.git").mkdir(parents=True)

    seed_local_eval_port(workspace, repo="aoa-routing", status="skeleton")
    seed_local_eval_port(workspace, repo="aoa-memo", status="active")
    write_json(
        workspace / "aoa-memo/evals/intake/memory-guardrail.eval_need.json",
        valid_eval_need_packet(),
    )
    seed_local_eval_port(workspace, repo="connectors/aoa-4pda-connector", status="active")
    stale = workspace / "legacy-evals"
    (stale / ".git").mkdir(parents=True)
    write_text(stale / "evals/README.md", "# Old local eval notes\n")
    state = AoAEvalsMCPState.discover(workspace_root=workspace)

    listing = state.local_ports()
    entries = {entry["repo_id"]: entry for entry in listing["ports"]}
    contract_route_keys = set(listing["inventory_contract"]["route_keys"])

    assert "aoa-evals" not in entries
    assert set(listing["summary"]) == set(listing["inventory_contract"]["summary_keys"])
    assert listing["excluded_repos"] == [
        {
            "repo": "aoa-evals",
            "repo_path": "aoa-evals",
            "repo_id": "aoa-evals",
            "reason": "central_proof_owner_not_repo_local_port",
        }
    ]
    assert entries["AbyssOS"]["inventory_status"] == "missing"
    assert entries["AbyssOS"]["route_recommendation"]["route_key"] == "missing_no_pressure"
    assert entries["aoa-routing"]["inventory_status"] == "skeleton"
    assert entries["aoa-routing"]["validator_ok"] is True
    assert entries["aoa-routing"]["route_recommendation"]["route_key"] == "valid_skeleton_keep_dormant"
    assert entries["aoa-memo"]["inventory_status"] == "active"
    assert entries["aoa-memo"]["pressure_counts"]["intake_packets"] == 1
    assert entries["aoa-memo"]["route_recommendation"]["route_key"] == "active_intake_select_then_apply_or_design"
    assert entries["connectors/aoa-4pda-connector"]["repo"] == "aoa-4pda-connector"
    assert entries["connectors/aoa-4pda-connector"]["inventory_status"] == "invalid"
    assert entries["connectors/aoa-4pda-connector"]["route_recommendation"]["route_key"] == "invalid_active_repair"
    assert entries["legacy-evals"]["inventory_status"] == "stale_candidate"
    assert entries["legacy-evals"]["route_recommendation"]["route_key"] == "stale_local_eval_surface_review"
    assert {
        entry["route_recommendation"]["route_key"]
        for entry in entries.values()
    }.issubset(contract_route_keys)
    assert listing["summary"]["repos"] == 5
    assert listing["summary"]["active"] == 1
    assert listing["summary"]["skeleton"] == 1
    assert listing["summary"]["invalid"] == 1
    assert listing["summary"]["missing"] == 1
    assert listing["summary"]["stale_candidate"] == 1
    assert listing["summary"]["excluded_repos"] == 1

    invalid_detail = state.local_port("connectors/aoa-4pda-connector")
    assert invalid_detail["schema"] == "aoa_evals_local_port_v1"
    assert invalid_detail["inventory_contract"]["schema_version"] == "aoa_local_eval_port_inventory_contract_v1"
    assert invalid_detail["repo_id"] == "connectors/aoa-4pda-connector"
    assert invalid_detail["validation"]["valid"] is False

    encoded = state.read_resource("aoa-evals://local-port/connectors%2Faoa-4pda-connector")
    unencoded = state.read_resource("aoa-evals://local-port/connectors/aoa-4pda-connector")
    assert encoded["repo_id"] == "connectors/aoa-4pda-connector"
    assert unencoded["repo_id"] == "connectors/aoa-4pda-connector"


def test_local_ports_status_filter_uses_inventory_status(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    seed_local_eval_port(tmp_path, repo="aoa-routing", status="skeleton")
    seed_local_eval_port(tmp_path, repo="aoa-memo", status="active")
    write_json(
        tmp_path / "aoa-memo/evals/intake/memory-guardrail.eval_need.json",
        valid_eval_need_packet(),
    )
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    active = state.local_ports(status="active")
    non_skeleton = state.local_ports(include_skeleton=False)

    assert [entry["repo_id"] for entry in active["ports"]] == ["aoa-memo"]
    assert [entry["repo_id"] for entry in non_skeleton["ports"]] == ["aoa-memo"]


def test_find_or_propose_local_returns_write_plan(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    seed_local_eval_port(tmp_path, status="skeleton")
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    result = state.find_or_propose_local("aoa-memo", "memory guardrail pressure before proof adoption")

    assert result["schema"] == "aoa_evals_local_find_or_propose_v1"
    assert result["repo"] == "aoa-memo"
    assert result["local_write_plan"]["relative_path"].startswith("evals/intake/")
    assert result["local_write_plan"]["apply_default"] is False
    assert result["local_write_plan"]["port_activation_needed"] is True
    assert not list((tmp_path / "aoa-memo/evals/intake").glob("*.eval_need.json"))


def test_write_local_intake_dry_run_does_not_mutate(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    repo_root = seed_local_eval_port(tmp_path, status="skeleton")
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    result = state.write_local_intake("aoa-memo", valid_eval_need_packet(), apply=False)

    assert result["write_allowed"] is True
    assert result["applied"] is False
    assert result["port_activation_needed"] is True
    assert not Path(result["target_path"]).exists()
    assert "status: skeleton" in (repo_root / "evals/PORT.yaml").read_text(encoding="utf-8")


def test_write_local_intake_rejects_unknown_escape_and_central_repos(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    seed_local_eval_port(tmp_path, status="active")
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    with pytest.raises(ValueError, match="unsafe repo id"):
        state.write_local_intake("../aoa-memo", valid_eval_need_packet(), apply=True)

    with pytest.raises(ValueError, match="unsafe repo id"):
        state.write_local_intake("/srv/AbyssOS/aoa-memo", valid_eval_need_packet(), apply=True)

    with pytest.raises(ValueError, match="local eval port"):
        state.write_local_intake("aoa-evals", valid_eval_need_packet(), apply=True)

    assert not (tmp_path / "aoa-evals/evals/intake").exists()
    assert not list((tmp_path / "aoa-memo/evals/intake").glob("*.eval_need.json"))


def test_write_local_explicit_slugs_reject_path_segments_without_mutation(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    repo_root = seed_local_eval_port(tmp_path, status="active")
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    with pytest.raises(ValueError, match="unsafe local eval file slug"):
        state.write_local_intake(
            "aoa-memo",
            valid_eval_need_packet(),
            file_slug="../memory-guardrail",
            apply=True,
        )

    with pytest.raises(ValueError, match="unsafe local eval file slug"):
        state.write_local_suite_note(
            "aoa-memo",
            "nested/memory-guardrail",
            "Memory guardrail suite",
            "Local suite note for memory guardrail pressure.",
            "# Memory guardrail suite\n",
            apply=True,
        )

    with pytest.raises(ValueError, match="unsafe local eval file slug"):
        state.write_local_report_note(
            "aoa-memo",
            r"nested\memory-guardrail",
            "Memory guardrail report",
            "Local report note for memory guardrail pressure.",
            "# Memory guardrail report\n",
            apply=True,
        )

    assert not list((repo_root / "evals/intake").glob("*.eval_need.json"))
    assert not list((repo_root / "evals/suites").glob("*.suite.md"))
    assert not list((repo_root / "evals/reports").glob("*.report.md"))


def test_write_local_intake_apply_writes_and_activates_port(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    repo_root = seed_local_eval_port(tmp_path, status="skeleton")
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    result = state.write_local_intake("aoa-memo", valid_eval_need_packet(), apply=True)

    assert result["applied"] is True
    assert Path(result["target_path"]).is_file()
    assert "status: active" in (repo_root / "evals/PORT.yaml").read_text(encoding="utf-8")
    detail = state.local_port("aoa-memo")
    assert detail["counts"]["intake"] == 1
    assert detail["validation"]["valid"] is True
    assert not (tmp_path / "aoa-evals/evals/intake").exists()


def test_write_local_intake_refuses_overwrite_without_replace_flag(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    repo_root = seed_local_eval_port(tmp_path, status="active")
    target = repo_root / "evals/intake/aoa-memory-guardrail-pressure.eval_need.json"
    write_json(target, valid_eval_need_packet())
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    packet = valid_eval_need_packet()
    packet["summary"] = "Changed packet that should not overwrite without explicit replace."
    result = state.write_local_intake("aoa-memo", packet, apply=True)

    assert result["write_allowed"] is False
    assert result["applied"] is False
    assert "target file already exists; set replace_existing=True to overwrite" in result["validation"]["issues"]
    assert json.loads(target.read_text(encoding="utf-8"))["summary"] != packet["summary"]


def test_write_local_intake_rejects_invalid_port_before_apply(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    seed_local_eval_port(tmp_path, status="skeleton")
    port_path = tmp_path / "aoa-memo/evals/PORT.yaml"
    port_path.write_text(
        port_path.read_text(encoding="utf-8").replace("owner_repo: aoa-memo", "owner_repo: wrong-repo"),
        encoding="utf-8",
    )
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    result = state.write_local_intake("aoa-memo", valid_eval_need_packet(), apply=True)

    assert result["write_allowed"] is False
    assert result["applied"] is False
    assert not Path(result["target_path"]).exists()
    assert any("owner_repo" in issue for issue in result["validation"]["issues"])


def test_write_local_intake_rejects_skeleton_port_with_existing_pressure(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    repo_root = seed_local_eval_port(tmp_path, status="skeleton")
    write_json(repo_root / "evals/intake/existing.eval_need.json", valid_eval_need_packet("existing-pressure"))
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    result = state.write_local_intake("aoa-memo", valid_eval_need_packet(), apply=True)

    assert result["write_allowed"] is False
    assert result["applied"] is False
    assert not Path(result["target_path"]).exists()
    assert "skeleton local eval port must not contain local pressure files" in result["validation"]["issues"]
    assert "status: skeleton" in (repo_root / "evals/PORT.yaml").read_text(encoding="utf-8")


def test_write_local_intake_activates_quoted_or_commented_skeleton_status(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    scenarios = {
        "quoted": '"skeleton"',
        "commented": "skeleton # first local pressure activates the port",
    }

    for repo_suffix, status in scenarios.items():
        repo = f"aoa-memo-{repo_suffix}"
        repo_root = seed_local_eval_port(tmp_path, repo=repo, status=status)
        state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

        result = state.write_local_intake(repo, valid_eval_need_packet(f"{repo}-pressure"), apply=True)

        assert result["applied"] is True
        assert Path(result["target_path"]).is_file()
        assert "status: active" in (repo_root / "evals/PORT.yaml").read_text(encoding="utf-8")


def test_write_local_intake_activates_only_top_level_port_status(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    repo_root = seed_local_eval_port(tmp_path, status="skeleton")
    port_path = repo_root / "evals/PORT.yaml"
    port_path.write_text(
        port_path.read_text(encoding="utf-8").replace(
            "status: skeleton\n",
            "metadata:\n  status: skeleton\nstatus: skeleton\n",
            1,
        ),
        encoding="utf-8",
    )
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    result = state.write_local_intake("aoa-memo", valid_eval_need_packet(), apply=True)

    assert result["applied"] is True
    updated = port_path.read_text(encoding="utf-8")
    assert "metadata:\n  status: skeleton\n" in updated
    assert "\nstatus: active\n" in f"\n{updated}"
    detail = state.local_port("aoa-memo")
    assert detail["status"] == "active"
    assert detail["validation"]["valid"] is True


def test_write_local_suite_and_report_notes_are_local_only(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    repo_root = seed_local_eval_port(tmp_path, status="skeleton")
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    suite = state.write_local_suite_note(
        "aoa-memo",
        "memory-guardrail",
        "Memory guardrail suite",
        "Local suite note for memory guardrail pressure.",
        "# Memory guardrail suite\n\nLocal deterministic case list.",
        refs=["mechanics/consumer-handoff/parts/eval-guardrail-handoff/"],
        apply=True,
    )
    report = state.write_local_report_note(
        "aoa-memo",
        "memory-guardrail",
        "Memory guardrail report",
        "Local report note for memory guardrail pressure.",
        "# Memory guardrail report\n\nNo verdict computed.",
        refs=["evals/suites/memory-guardrail.suite.md"],
        apply=True,
    )

    assert suite["applied"] is True
    assert report["applied"] is True
    assert (repo_root / "evals/suites/memory-guardrail.suite.md").is_file()
    assert (repo_root / "evals/reports/memory-guardrail.report.md").is_file()
    detail = state.local_port("aoa-memo")
    assert detail["counts"]["suites"] == 1
    assert detail["counts"]["reports"] == 1
    assert detail["validation"]["valid"] is True


def test_write_local_note_rejects_private_or_traversing_refs(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    seed_local_eval_port(tmp_path, status="active")
    state = AoAEvalsMCPState.discover(workspace_root=tmp_path)

    result = state.write_local_report_note(
        "aoa-memo",
        "bad-ref",
        "Bad ref report",
        "Local report note with unsafe reference.",
        "# Bad ref report\n",
        refs=["../secret/private.json", "private:/tmp/secret.json"],
        apply=True,
    )

    assert result["write_allowed"] is False
    assert result["applied"] is False
    assert not Path(result["target_path"]).exists()
    assert any("ref" in issue for issue in result["validation"]["issues"])


def test_server_builds(tmp_path: Path) -> None:
    seed_evals(tmp_path)
    assert build_server(workspace_root=tmp_path) is not None
