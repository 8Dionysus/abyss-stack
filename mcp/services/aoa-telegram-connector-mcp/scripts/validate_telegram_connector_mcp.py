#!/usr/bin/env python3
"""Validate the Telegram connector MCP service contract."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from aoa_telegram_connector_mcp.core import AoATelegramConnectorMCPState  # noqa: E402
from aoa_telegram_connector_mcp.server import build_server  # noqa: E402


def fake_runner(argv: Sequence[str], _env: dict[str, str], _timeout: float, _cwd: Path | None) -> subprocess.CompletedProcess[str]:
    if argv[-1] == "doctor":
        payload = {"schema": "aoa_telegram_doctor_v1", "status": "ok", "network_touched": False}
    elif len(argv) >= 2 and argv[-2:] == ["storage", "status"]:
        payload = {"schema": "aoa_telegram_storage_status_v1", "status": "ok", "network_touched": False}
    elif len(argv) >= 2 and argv[-2:] == ["policy", "check"]:
        payload = {"schema": "aoa_telegram_policy_check_v1", "status": "ok", "network_touched": False}
    elif "answer" in argv:
        payload = {
            "schema": "aoa_connector_answer_packet_v1",
            "status": "ok",
            "agent_answer": "Local Telegram evidence supports an answer from chat message msg-1001.",
            "answers": [{"answer_kind": "telegram_message_evidence", "answer_text": "Supported warning."}],
            "evidence_chain": [{"conversation_id": "chat", "message_id": "msg-1001", "permission_state": "account_visible"}],
            "permission_report": {"status": "ok"},
            "answer_report": {"answer_status": "answered"},
            "conflict_report": {"status": "answered"},
            "freshness_report": {"status": "answered"},
            "applicability_report": {"status": "answered"},
            "warning_report": {"status": "warning_supported"},
            "policy": {"source": "local_message_index_plus_graph_answer_renderer", "internal_search_used": False},
            "network_touched": False,
            "read_only": True,
        }
    elif "query-graph" in argv:
        payload = {
            "schema": "aoa_telegram_evidence_packet_v1",
            "status": "ok",
            "results": [],
            "permission_report": {"status": "ok"},
            "policy": {"source": "local_message_index_plus_graph", "internal_search_used": False},
            "network_touched": False,
            "read_only": True,
        }
    else:
        payload = {"schema": "unknown", "status": "error", "network_touched": False, "argv": list(argv)}
    return subprocess.CompletedProcess(list(argv), 0, json.dumps(payload), "")


def require_files() -> list[str]:
    required = [
        "AGENTS.md",
        "DESIGN.md",
        "README.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "src/aoa_telegram_connector_mcp/core.py",
        "src/aoa_telegram_connector_mcp/server.py",
        "src/aoa_telegram_connector_mcp/cli.py",
        "scripts/aoa_telegram_connector_mcp_server.py",
        "tests/test_telegram_connector_mcp.py",
    ]
    return [path for path in required if not (ROOT / path).exists()]


def main() -> int:
    missing = require_files()
    if missing:
        print(json.dumps({"status": "fail", "missing": missing}, indent=2))
        return 1
    with tempfile.TemporaryDirectory(prefix="aoa-telegram-mcp-fixture-") as fixture_dir:
        connector_repo = Path(fixture_dir) / "aoa-telegram-connector"
        (connector_repo / "src" / "aoa_telegram_connector").mkdir(parents=True)
        (connector_repo / "src" / "aoa_telegram_connector" / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
        state = AoATelegramConnectorMCPState(connector_repo=connector_repo, runner=fake_runner)
        route = state.source_route()
        status = state.status()
        answer = state.answer("vendor_boot bootloop warning")
        graph = state.query_graph("vendor_boot bootloop warning")
        server = build_server(state)
    checks = {
        "source_route": route["service_name"] == "aoa-telegram-connector-mcp" and route["read_only"],
        "status": status["schema"] == "aoa_telegram_connector_mcp_status_v1" and status["status"] == "ok",
        "answer": answer["schema"] == "aoa_telegram_connector_mcp_answer_v1"
        and answer["status"] == "ok"
        and answer["evidence_chain"][0]["message_id"] == "msg-1001",
        "graph": graph["schema"] == "aoa_telegram_connector_mcp_query_graph_v1" and graph["status"] == "ok",
        "permission_modes": route["permission_modes"] == ["bot_api", "tdlib_user_session", "takeout_export"],
        "server": server is not None,
    }
    ok = all(checks.values())
    print(json.dumps({"status": "pass" if ok else "fail", "checks": checks}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
