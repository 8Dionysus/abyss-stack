from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from aoa_4pda_connector_mcp.core import AoA4PDAConnectorMCPState, CommandOutput
from aoa_4pda_connector_mcp.server import build_server


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Mapping[str, str], Path | None]] = []

    def __call__(self, argv: list[str], _timeout: float, env: Mapping[str, str], cwd: Path | None) -> CommandOutput:
        self.calls.append((argv, env, cwd))
        payload: dict[str, object]
        if "doctor" in argv:
            payload = {"schema": "aoa_4pda_doctor_v1", "status": "ok", "network_touched": False}
        elif "storage" in argv and "status" in argv:
            payload = {"schema": "aoa_4pda_storage_status_v1", "status": "ok", "network_touched": False}
        elif "ready" in argv:
            payload = {"schema": "aoa_4pda_connector_ready_audit_v1", "status": "ready", "ready": True, "network_touched": False}
        elif "answer" in argv:
            payload = answer_packet()
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


def answer_packet() -> dict[str, object]:
    return {
        "schema": "aoa_4pda_answer_packet_v1",
        "status": "ok",
        "answer_id": "answer-fb83ef1d65649cb9",
        "agent_answer": {
            "status": "answered",
            "format": "deterministic_cited_brief_v1",
            "text": "Recovery actions: flash recovery.img. Tools: fastboot; TWRP [1].",
            "citations": [{"ref": "[1]", "post_id": "128964413"}],
        },
        "evidence_chain": [
            {
                "role": "primary",
                "post_id": "128964413",
                "source_url": "https://4pda.to/forum/index.php?showtopic=1076859&st=2140#entry128964413",
            }
        ],
        "nuance_report": {"source_count": 1, "relation_kinds": ["recovery_targets_file"]},
        "answer_report": {"answer_status": "answered"},
        "answers": [{"answer_kind": "recovery", "post_id": "128964413"}],
        "query_report": {"algorithm": "bm25_exact_v1"},
        "policy": {"internal_search_used": False},
        "network_touched": False,
    }


def state(tmp_path: Path, runner: FakeRunner | None = None) -> AoA4PDAConnectorMCPState:
    connector_repo = tmp_path / "aoa-4pda-connector"
    (connector_repo / "src" / "aoa_4pda_connector").mkdir(parents=True, exist_ok=True)
    return AoA4PDAConnectorMCPState.discover(
        connector_repo=connector_repo,
        command_runner=runner or FakeRunner(),
        data_root=connector_repo / ".connector-state" / "data",
        cache_root=connector_repo / ".connector-state" / "cache",
        artifact_root=connector_repo / ".connector-state" / "artifacts",
    )


def test_source_route_names_owner_split_and_read_only(tmp_path: Path) -> None:
    route = state(tmp_path).source_route()

    assert route["schema"] == "aoa_4pda_connector_mcp_source_route_v1"
    assert route["service_name"] == "aoa-4pda-connector-mcp"
    assert route["read_only"] is True
    assert route["network_touched"] is False
    assert "aoa-4pda answer" in route["wrapped_commands"]
    assert "source_owner" in route["owner_split"]
    assert any("crawl" in line for line in route["stop_lines"])


def test_answer_preserves_connector_packet_fields(tmp_path: Path) -> None:
    packet = state(tmp_path).answer("Xiaomi 13T recovery.img fastboot TWRP", run="20260621T194521Z__crawl", limit=5)

    assert packet["schema"] == "aoa_4pda_connector_mcp_answer_v1"
    assert packet["status"] == "ok"
    assert packet["source_packet_schema"] == "aoa_4pda_answer_packet_v1"
    assert packet["agent_answer"]["status"] == "answered"
    assert packet["evidence_chain"][0]["post_id"] == "128964413"
    assert packet["nuance_report"]["source_count"] == 1
    assert packet["answer_report"]["answer_status"] == "answered"
    assert packet["network_touched"] is False
    assert packet["boundary_errors"] == []


def test_status_wraps_doctor_storage_and_ready(tmp_path: Path) -> None:
    runner = FakeRunner()
    packet = state(tmp_path, runner).status(run="20260621T194521Z__crawl")

    assert packet["schema"] == "aoa_4pda_connector_mcp_status_v1"
    assert packet["status"] == "ok"
    assert packet["doctor"]["payload_schema"] == "aoa_4pda_doctor_v1"
    assert packet["storage"]["payload_schema"] == "aoa_4pda_storage_status_v1"
    assert packet["ready"]["payload_schema"] == "aoa_4pda_connector_ready_audit_v1"
    assert any("doctor" in call[0] for call in runner.calls)
    assert any("storage" in call[0] and "status" in call[0] for call in runner.calls)
    assert any("ready" in call[0] for call in runner.calls)


def test_repo_checkout_uses_python_module_with_pythonpath(tmp_path: Path) -> None:
    runner = FakeRunner()
    connector_repo = tmp_path / "aoa-4pda-connector"
    (connector_repo / "src" / "aoa_4pda_connector").mkdir(parents=True)
    state = AoA4PDAConnectorMCPState.discover(connector_repo=connector_repo, command_runner=runner)

    state.answer("Xiaomi 13T recovery.img fastboot TWRP", run="20260621T194521Z__crawl")
    argv, env, cwd = runner.calls[-1]

    assert argv[1:4] == ["-m", "aoa_4pda_connector.cli", "answer"]
    assert str(connector_repo / "src") in env["PYTHONPATH"]
    assert cwd == connector_repo


def test_query_wrappers_remain_read_only_and_local(tmp_path: Path) -> None:
    graph = state(tmp_path).query_graph("Xiaomi 13T TWRP", run="20260621T194521Z__crawl")
    hybrid = state(tmp_path).query_hybrid("Xiaomi 13T TWRP", run="20260621T194521Z__crawl")

    assert graph["status"] == "ok"
    assert graph["query_kind"] == "query-graph"
    assert graph["network_touched"] is False
    assert hybrid["status"] == "ok"
    assert hybrid["query_kind"] == "query-hybrid"
    assert hybrid["network_touched"] is False


def test_server_builds() -> None:
    assert build_server() is not None
