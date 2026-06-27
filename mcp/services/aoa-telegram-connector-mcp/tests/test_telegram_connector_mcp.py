from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Sequence

from aoa_telegram_connector_mcp.core import AoATelegramConnectorMCPState
from aoa_telegram_connector_mcp.server import build_server


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, str], float, Path | None]] = []

    def __call__(self, argv: Sequence[str], env: dict[str, str], timeout: float, cwd: Path | None) -> subprocess.CompletedProcess[str]:
        self.calls.append((list(argv), env, timeout, cwd))
        if argv[-1] == "doctor":
            payload = {"schema": "aoa_telegram_doctor_v1", "status": "ok", "network_touched": False}
        elif len(argv) >= 2 and argv[-2:] == ["storage", "status"]:
            payload = {"schema": "aoa_telegram_storage_status_v1", "status": "ok", "network_touched": False}
        elif len(argv) >= 2 and argv[-2:] == ["policy", "check"]:
            payload = {"schema": "aoa_telegram_policy_check_v1", "status": "ok", "network_touched": False}
        elif "answer" in argv:
            payload = _answer_payload()
        elif "query-graph" in argv:
            payload = {
                "schema": "aoa_telegram_evidence_packet_v1",
                "status": "ok",
                "query": "vendor_boot bootloop warning",
                "results": [_result()],
                "result_count": 1,
                "permission_report": {"status": "ok", "visible": True},
                "graph_report": {"nodes": 2, "edges": 1},
                "policy": {"source": "local_message_index_plus_graph", "internal_search_used": False},
                "network_touched": False,
                "read_only": True,
            }
        else:
            payload = {"schema": "unknown", "status": "error", "argv": list(argv), "network_touched": False}
        return subprocess.CompletedProcess(list(argv), 0, json.dumps(payload), "")


def _state(tmp_path: Path, runner: FakeRunner | None = None) -> AoATelegramConnectorMCPState:
    connector_repo = tmp_path / "aoa-telegram-connector"
    (connector_repo / "src" / "aoa_telegram_connector").mkdir(parents=True, exist_ok=True)
    (connector_repo / "src" / "aoa_telegram_connector" / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
    return AoATelegramConnectorMCPState(
        connector_repo=connector_repo,
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        artifact_root=tmp_path / "artifacts",
        runner=runner or FakeRunner(),
    )


def _result() -> dict[str, object]:
    return {
        "conversation_id": "xiaomi-13t-public-chat",
        "message_id": "msg-1001",
        "source_mode": "tdlib_user_session",
        "permission_state": "account_visible",
        "snippet": "Vendor_boot warning is supported by local Telegram evidence.",
        "edited_or_deleted_state": "active",
    }


def _answer_payload() -> dict[str, object]:
    return {
        "schema": "aoa_connector_answer_packet_v1",
        "status": "ok",
        "answer_id": "answer-telegram-warning",
        "agent_answer": "Local Telegram evidence supports an answer from xiaomi-13t-public-chat message msg-1001.",
        "answers": [{"answer_kind": "telegram_message_evidence", "answer_text": "Vendor_boot warning is supported."}],
        "evidence_chain": [_result()],
        "permission_report": {"status": "ok", "visible_results": 1, "restricted_results": 0},
        "answer_report": {"renderer": "telegram_permissioned_conversation_answer_v1", "answer_status": "answered"},
        "conflict_report": {"status": "conflict_or_warning_pressure", "warning_supported": True},
        "freshness_report": {"status": "answered", "states": ["active"]},
        "applicability_report": {"status": "answered", "source_modes": ["tdlib_user_session"]},
        "warning_report": {"status": "warning_supported"},
        "policy": {"source": "local_message_index_plus_graph_answer_renderer", "internal_search_used": False},
        "network_touched": False,
        "read_only": True,
    }


def test_source_route_declares_read_only_boundary(tmp_path: Path) -> None:
    state = _state(tmp_path)
    route = state.source_route()
    assert route["schema"] == "aoa_telegram_connector_mcp_source_route_v1"
    assert route["service_name"] == "aoa-telegram-connector-mcp"
    assert route["read_only"] is True
    assert route["network_touched"] is False
    assert "aoa-telegram answer" in route["wrapped_commands"]
    assert not any("materialize" in command for command in route["wrapped_commands"])
    assert not any("eval permissions" in command for command in route["wrapped_commands"])
    assert route["permission_modes"] == ["bot_api", "tdlib_user_session", "takeout_export"]


def test_answer_preserves_permission_and_evidence_chain(tmp_path: Path) -> None:
    state = _state(tmp_path)
    packet = state.answer("vendor_boot bootloop warning")
    assert packet["schema"] == "aoa_telegram_connector_mcp_answer_v1"
    assert packet["status"] == "ok"
    assert packet["source_packet_schema"] == "aoa_connector_answer_packet_v1"
    assert packet["network_touched"] is False
    assert packet["permission_report"]["status"] == "ok"
    assert packet["evidence_chain"][0]["message_id"] == "msg-1001"
    assert packet["answer_report"]["answer_status"] == "answered"
    assert packet["warning_report"]["status"] == "warning_supported"
    assert packet["boundary_errors"] == []


def test_status_wraps_doctor_storage_and_policy(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = _state(tmp_path, runner)
    packet = state.status()
    assert packet["schema"] == "aoa_telegram_connector_mcp_status_v1"
    assert packet["status"] == "ok"
    assert packet["doctor"]["payload_schema"] == "aoa_telegram_doctor_v1"
    assert packet["storage"]["payload_schema"] == "aoa_telegram_storage_status_v1"
    assert packet["policy"]["payload_schema"] == "aoa_telegram_policy_check_v1"
    assert any(call[0][-1] == "doctor" for call in runner.calls)
    assert any(call[0][-2:] == ["policy", "check"] for call in runner.calls)


def test_repo_checkout_uses_python_module_and_storage_env(tmp_path: Path) -> None:
    runner = FakeRunner()
    state = _state(tmp_path, runner)
    state.answer("bootloop")
    argv, env, _timeout, cwd = runner.calls[-1]
    assert argv[1:4] == ["-m", "aoa_telegram_connector.cli", "answer"]
    assert cwd == state.connector_repo
    assert str(state.connector_repo / "src") in env["PYTHONPATH"]
    assert env["CONNECTOR_DATA_ROOT"] == str(tmp_path / "data")
    assert env["CONNECTOR_CACHE_ROOT"] == str(tmp_path / "cache")
    assert env["CONNECTOR_ARTIFACT_ROOT"] == str(tmp_path / "artifacts")


def test_query_graph_is_local_and_read_only(tmp_path: Path) -> None:
    state = _state(tmp_path)
    packet = state.query_graph("vendor_boot bootloop warning")
    assert packet["schema"] == "aoa_telegram_connector_mcp_query_graph_v1"
    assert packet["status"] == "ok"
    assert packet["read_only"] is True
    assert packet["network_touched"] is False
    assert packet["results"][0]["conversation_id"] == "xiaomi-13t-public-chat"
    assert packet["permission_report"]["visible"] is True


def test_boundary_error_marks_live_network_packets(tmp_path: Path) -> None:
    def bad_runner(argv: Sequence[str], env: dict[str, str], timeout: float, cwd: Path | None) -> subprocess.CompletedProcess[str]:
        payload = _answer_payload()
        payload["network_touched"] = True
        return subprocess.CompletedProcess(list(argv), 0, json.dumps(payload), "")

    state = AoATelegramConnectorMCPState(connector_repo=tmp_path, runner=bad_runner)
    packet = state.answer("bootloop")
    assert packet["status"] == "error"
    assert "network_touched=false" in packet["boundary_errors"][0]


def test_read_resources_and_server_build(tmp_path: Path) -> None:
    state = _state(tmp_path)
    assert state.read_resource("aoa-telegram://source-route")["service_name"] == "aoa-telegram-connector-mcp"
    assert state.read_resource("aoa-telegram://status")["status"] == "ok"
    assert build_server(state) is not None
