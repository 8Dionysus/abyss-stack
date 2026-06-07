from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aoa_evals_mcp.core import AoAEvalsMCPState  # noqa: E402
from aoa_evals_mcp.server import build_server  # noqa: E402


def main() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "src/aoa_evals_mcp/core.py",
        "src/aoa_evals_mcp/server.py",
        "scripts/aoa_evals_mcp_server.py",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    state = AoAEvalsMCPState.discover()
    catalog = state.build_catalog()
    if catalog["count"] <= 0:
        raise SystemExit("aoa-evals catalog is empty or unavailable")
    first_name = catalog["evals"][0]["name"]
    inspection = state.inspect_bundle(first_name)
    if inspection["authority_boundary"]["stronger_owner"] != "bundle-local EVAL.md and eval.yaml":
        raise SystemExit("authority boundary drifted")
    proposal_route = state.find_or_propose(f"bounded proof route for {first_name}")
    if not proposal_route["read_only"] or proposal_route["source_mutation_allowed"]:
        raise SystemExit("find-or-propose must stay read-only and source-nonmutating")
    if not proposal_route["proposal_validation"]["valid"]:
        raise SystemExit(f"find-or-propose produced invalid eval_need_v1: {proposal_route['proposal_validation']}")
    if state.report_skeleton(first_name, [])["sections"]["verdict"] != "UNSET: MCP must not compute verdicts":
        raise SystemExit("report skeleton must leave verdict unset")
    status = state.runtime_status()
    if status["catalog_count"] <= 0:
        raise SystemExit("runtime status lost catalog count")
    packet = {
        "surface_type": "runtime_evidence_selection",
        "selection_id": "aoa-evals-mcp-validator-smoke",
        "source_repo": "abyss-stack",
        "source_schema_ref": "repo:abyss-stack/mcp/services/aoa-evals-mcp/scripts/validate_evals_mcp.py",
        "source_manifests": ["local:aoa-evals-mcp-validator"],
        "bounded_claim": "Validate that aoa_evals can preflight a candidate packet shape without accepting evidence.",
        "promotion_target": "local-only",
        "comparison_mode": "none",
        "target_eval": first_name,
        "selected_evidence": [
            {
                "artifact_ref": "local:aoa-evals-mcp-validator",
                "evidence_role": "summary",
                "summary_only": True,
            }
        ],
        "environment_invariants": ["service-local validation only"],
        "do_not_overread": ["does not prove a bounded eval verdict"],
        "review_posture": {
            "portable_enough": False,
            "comparison_hygiene_named": True,
            "human_review_required": True,
        },
    }
    validation = state.validate_evidence_candidate(packet)
    if not validation["valid"]:
        raise SystemExit(f"candidate validation failed: {validation['issues']}")
    exports = state.runtime_candidate_exports(limit=5)
    if exports["invalid_count"]:
        raise SystemExit(f"runtime candidate export readers found invalid files: {exports['invalid_exports']}")
    export_read = None
    if exports["count"]:
        visible_candidates = exports.get("candidates", []) if isinstance(exports.get("candidates"), list) else []
        selected_candidate = next(
            (
                item
                for item in visible_candidates
                if isinstance(item.get("validation"), dict) and item["validation"].get("valid") is True
            ),
            visible_candidates[0] if visible_candidates else None,
        )
        record_id = selected_candidate["record_id"]
        export_read = state.read_runtime_candidate_export(record_id)
        if export_read.get("candidate_payload_included"):
            raise SystemExit("runtime candidate export read leaked payload by default")
        if not isinstance(export_read.get("validation"), dict):
            raise SystemExit("runtime candidate export read lost validation summary")
    server = build_server()
    if server is None:
        raise SystemExit("MCP server did not build")

    print(
        json.dumps(
            {
                "ok": True,
                "schema": catalog["schema"],
                "evals_root": catalog["evals_root"],
                "catalog_count": catalog["count"],
                "freshness_status": status["freshness"]["status"],
                "find_or_propose_valid": proposal_route["proposal_validation"]["valid"],
                "candidate_validation": validation["valid"],
                "runtime_candidate_export_count": exports["count"],
                "runtime_candidate_export_invalid_shape_count": exports.get("candidate_validation", {}).get("invalid_shape_count"),
                "runtime_candidate_export_validation": None
                if export_read is None
                else export_read.get("validation", {}).get("valid"),
                "runtime_candidate_export_posture": "private candidates may be shape-invalid; MCP reports them without accepting proof",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
