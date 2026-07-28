#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aoa_4pda_connector_mcp.core import AoA4PDAConnectorMCPState, CommandOutput  # noqa: E402
from aoa_4pda_connector_mcp.server import build_server  # noqa: E402


def fake_runner(argv: list[str], _timeout: float, _env: Mapping[str, str], cwd: Path | None) -> CommandOutput:
    payload: dict[str, object]
    if "doctor" in argv:
        payload = {"schema": "aoa_4pda_doctor_v1", "status": "ok", "network_touched": False}
    elif "storage" in argv and "status" in argv:
        payload = {"schema": "aoa_4pda_storage_status_v1", "status": "ok", "network_touched": False}
    elif "ready" in argv:
        payload = {
            "schema": "aoa_4pda_connector_ready_audit_v1",
            "status": "ready",
            "ready": True,
            "counts": {"achieved": 1, "partial": 0, "missing": 0},
            "network_touched": False,
        }
    elif "answer" in argv:
        payload = {
            "schema": "aoa_4pda_answer_packet_v1",
            "status": "ok",
            "answer_id": "answer-validator-smoke",
            "agent_answer": {"status": "answered", "text": "Use recovery.img with fastboot/TWRP [1]."},
            "evidence_chain": [{"post_id": "128964413", "source_url": "https://4pda.to/forum/index.php?showtopic=1076859#entry128964413"}],
            "nuance_report": {"source_count": 1, "relation_kinds": ["recovery_targets_file"]},
            "answer_report": {"answer_status": "answered"},
            "conflict_report": {"status": "no_conflict", "primary_claim_id": "claim:fixture:recovery"},
            "freshness_report": {"state": "fresh_answer"},
            "applicability_report": {"status": "context_available"},
            "warning_report": {"warning_supported": False},
            "answers": [{"answer_kind": "recovery", "post_id": "128964413"}],
            "query_report": {"algorithm": "bm25_exact_v1"},
            "policy": {"internal_search_used": False},
            "network_touched": False,
            "read_only": True,
        }
    elif "query-graph" in argv or "query-hybrid" in argv:
        payload = {"schema": "aoa_4pda_evidence_packet_v1", "status": "ok", "results": [], "network_touched": False}
    else:
        payload = {"schema": "unknown", "status": "error", "network_touched": False}
    return CommandOutput(
        argv=argv,
        returncode=0 if payload.get("status") != "error" else 1,
        stdout=json.dumps(payload),
        stderr="",
        elapsed_ms=1.0,
        cwd=str(cwd) if cwd is not None else None,
    )


def main() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "pyproject.toml",
        "src/aoa_4pda_connector_mcp/core.py",
        "src/aoa_4pda_connector_mcp/server.py",
        "src/aoa_4pda_connector_mcp/cli.py",
        "scripts/aoa_4pda_connector_mcp_server.py",
        "tests/test_4pda_connector_mcp.py",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    with tempfile.TemporaryDirectory(prefix="aoa-4pda-mcp-fixture-") as fixture_dir:
        connector_repo = Path(fixture_dir) / "aoa-4pda-connector"
        (connector_repo / "src" / "aoa_4pda_connector").mkdir(parents=True)
        state = AoA4PDAConnectorMCPState.discover(
            connector_repo=connector_repo,
            command_runner=fake_runner,
            data_root=connector_repo / ".connector-state" / "data",
            cache_root=connector_repo / ".connector-state" / "cache",
            artifact_root=connector_repo / ".connector-state" / "artifacts",
        )
        route = state.source_route()
        if route["service_name"] != "aoa-4pda-connector-mcp" or not route["read_only"]:
            raise SystemExit("source route lost service identity or read-only posture")
        if route["network_touched"] is not False:
            raise SystemExit("source route must not touch network")

        status = state.status(run="20260621T194521Z__crawl")
        if status["schema"] != "aoa_4pda_connector_mcp_status_v1" or status["status"] != "ok":
            raise SystemExit(f"status wrapper failed: {status}")

        answer = state.answer("Xiaomi 13T recovery.img fastboot TWRP", run="20260621T194521Z__crawl", limit=5)
        if answer["status"] != "ok":
            raise SystemExit(f"answer wrapper failed: {answer}")
        for field in (
            "agent_answer",
            "evidence_chain",
            "nuance_report",
            "answer_report",
            "conflict_report",
            "freshness_report",
            "applicability_report",
            "warning_report",
        ):
            if not answer.get(field):
                raise SystemExit(f"answer wrapper lost {field}")
        if answer["network_touched"] is not False:
            raise SystemExit("answer wrapper lost network_touched=false")
        if answer["read_only"] is not True or answer["source_read_only"] is not True:
            raise SystemExit("answer wrapper lost read_only=true")

        server = build_server(connector_repo=connector_repo)
        if server is None:
            raise SystemExit("MCP server did not build")
        tools = asyncio.run(server.list_tools())
        if len(tools) != 5 or any(
            tool.annotations.readOnlyHint is not True
            or tool.annotations.destructiveHint is not False
            or tool.annotations.openWorldHint is not False
            for tool in tools
        ):
            raise SystemExit("4PDA read tool catalog or annotations drifted")

        print(
            json.dumps(
                {
                    "ok": True,
                    "service_name": route["service_name"],
                    "status_schema": status["schema"],
                    "answer_schema": answer["schema"],
                    "answer_status": answer["agent_answer"]["status"],
                    "network_touched": answer["network_touched"],
                    "tool_count": len(tools),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
