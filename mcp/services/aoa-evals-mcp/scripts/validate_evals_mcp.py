from __future__ import annotations

import asyncio
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
        "src/aoa_evals_mcp/organ_access.py",
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
    local_ports = state.read_resource("aoa-evals://local-ports")
    if local_ports["schema"] != "aoa_evals_local_ports_v1":
        raise SystemExit("local eval-port resource schema drifted")
    contract = local_ports.get("inventory_contract")
    accepted_contract_schemas = {
        "aoa_local_eval_port_inventory_contract_v1",
        "aoa_local_eval_port_inventory_contract_v2",
    }
    if not isinstance(contract, dict) or contract.get("schema_version") not in accepted_contract_schemas:
        raise SystemExit("local eval-port inventory contract is unavailable or wrong schema")
    if contract.get("contract_source") != "aoa-evals":
        raise SystemExit(f"local eval-port inventory contract source drifted: {contract.get('contract_source')}")
    contract_summary_keys = set(contract.get("summary_keys", []))
    if set(local_ports.get("summary", {})) != contract_summary_keys:
        raise SystemExit("local eval-port summary keys drifted from inventory contract")
    contract_route_keys = set(contract.get("route_keys", []))
    unknown_route_keys = sorted(
        {
            port.get("route_recommendation", {}).get("route_key")
            for port in local_ports.get("ports", [])
            if isinstance(port, dict)
        }
        - contract_route_keys
    )
    if unknown_route_keys:
        raise SystemExit(f"local eval-port route keys drifted from inventory contract: {unknown_route_keys}")
    for port in local_ports.get("ports", []):
        suite_execution = port.get("suite_execution") if isinstance(port, dict) else None
        if not isinstance(suite_execution, dict):
            raise SystemExit("local eval-port entry omitted fail-closed suite execution posture")
        if suite_execution.get("state") not in {"absent", "invalid", "stale", "ready"}:
            raise SystemExit("local eval-port suite execution state drifted")
        if any(
            suite_execution.get(key) is not False
            for key in (
                "auto_run_allowed",
                "inventory_executed_runner",
                "execution_allowed",
                "suite_sidecar_write_allowed",
                "proof_authority",
                "promotion_allowed",
                "runtime_reproducibility_proven",
            )
        ):
            raise SystemExit("local eval-port suite execution widened MCP authority")
    local_port_repo = None
    local_port_valid = None
    local_find_valid = None
    local_dry_write_allowed = None
    valid_local_ports = [
        port
        for port in local_ports.get("ports", [])
        if isinstance(port.get("validation"), dict) and port["validation"].get("valid") is True
    ]
    if valid_local_ports:
        local_port_repo = valid_local_ports[0]["repo"]
        local_detail = state.read_resource(f"aoa-evals://local-port/{local_port_repo}")
        if local_detail["schema"] != "aoa_evals_local_port_v1":
            raise SystemExit("local eval-port detail resource schema drifted")
        if local_detail["repo"] != local_port_repo or not local_detail["validation"]["valid"]:
            raise SystemExit(f"local eval-port detail invalid: {local_detail.get('validation')}")
        local_port_valid = True
        local_find = state.find_or_propose_local(
            local_port_repo,
            f"bounded proof route for {first_name}",
        )
        if local_find["schema"] != "aoa_evals_local_find_or_propose_v1":
            raise SystemExit("local find-or-propose schema drifted")
        local_find_valid = bool(local_find["central_route"]["proposal_validation"]["valid"])
        if not local_find_valid:
            raise SystemExit(
                "local find-or-propose produced invalid eval_need_v1: "
                f"{local_find['central_route']['proposal_validation']}"
            )
        dry_write = state.write_local_intake(
            local_port_repo,
            local_find["central_route"]["proposal_context"]["packet"],
            file_slug="aoa-evals-mcp-validator-smoke",
            apply=False,
            replace_existing=True,
        )
        if dry_write["applied"]:
            raise SystemExit("local intake smoke mutated files during dry-run")
        local_dry_write_allowed = bool(dry_write["write_allowed"])
        if not local_dry_write_allowed:
            raise SystemExit(f"local intake dry-run rejected a valid packet: {dry_write['validation']}")
    elif local_ports.get("count", 0):
        raise SystemExit("local eval-port listing found only invalid ports")
    if state.report_skeleton(first_name, [])["sections"]["verdict"] != "UNSET: MCP must not compute verdicts":
        raise SystemExit("report skeleton must leave verdict unset")
    status = state.runtime_status()
    if status["catalog_count"] <= 0:
        raise SystemExit("runtime status lost catalog count")
    forge_packet = state.eval_forge_access_packet()
    if forge_packet["schema"] != "aoa_evals_forge_access_packet_v1":
        raise SystemExit("Eval Forge access packet schema drifted")
    if not forge_packet["read_only"] or forge_packet["source_mutation_allowed"]:
        raise SystemExit("Eval Forge access packet must stay read-only and source-nonmutating")
    if forge_packet["proof_authority"] or forge_packet["promotion_allowed"]:
        raise SystemExit("Eval Forge access packet must not carry proof or promotion authority")
    forge_front_door = forge_packet.get("eval_forge_front_door", {})
    forge_refs = forge_front_door.get("surface_refs", {}) if isinstance(forge_front_door, dict) else {}
    for key in ("operating_path_ref", "session_mining_criteria_ref", "local_port_decision_matrix_ref"):
        if not forge_refs.get(key):
            raise SystemExit(f"Eval Forge access packet missing {key}")
    forge_commands = forge_packet.get("exact_route_commands", [])
    if not any(
        isinstance(command, dict) and "aoa_eval_session_start.py --json" in str(command.get("command"))
        for command in forge_commands
    ):
        raise SystemExit("Eval Forge access packet lost session-start command")
    if forge_packet.get("local_ports", {}).get("proof_authority") is not False:
        raise SystemExit("Eval Forge access packet local-port surface must stay non-proof")
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
    read_server = build_server(policy_family="read")
    candidate_server = build_server(policy_family="candidate")

    async def tool_inventory(server):
        return {
            tool.name: tool.annotations
            for tool in await server.list_tools()
        }

    read_tools = asyncio.run(tool_inventory(read_server))
    candidate_tools = asyncio.run(tool_inventory(candidate_server))
    if set(read_tools) & set(candidate_tools):
        raise SystemExit("evals read and candidate tool catalogs overlap")
    if not read_tools or not candidate_tools:
        raise SystemExit("evals MCP contour tool catalog is empty")
    if any(
        annotations.readOnlyHint is not True
        or annotations.destructiveHint is not False
        for annotations in read_tools.values()
    ):
        raise SystemExit("evals read tool annotations drifted")
    if any(
        annotations.readOnlyHint is not False
        or annotations.destructiveHint is not True
        for annotations in candidate_tools.values()
    ):
        raise SystemExit("evals candidate tool annotations drifted")

    print(
        json.dumps(
            {
                "ok": True,
                "schema": catalog["schema"],
                "evals_root": catalog["evals_root"],
                "catalog_count": catalog["count"],
                "read_tool_count": len(read_tools),
                "candidate_tool_count": len(candidate_tools),
                "freshness_status": status["freshness"]["status"],
                "forge_access_packet": True,
                "forge_front_door_valid": forge_front_door.get("surface_status", {}).get("valid"),
                "forge_candidate_routes": forge_packet.get("candidate_queue", {}).get("summary", {}).get("entry_count"),
                "find_or_propose_valid": proposal_route["proposal_validation"]["valid"],
                "local_eval_port_count": local_ports["count"],
                "local_eval_port_smoke_repo": local_port_repo,
                "local_eval_port_detail_valid": local_port_valid,
                "local_find_or_propose_valid": local_find_valid,
                "local_intake_dry_write_allowed": local_dry_write_allowed,
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
