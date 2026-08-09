#!/usr/bin/env python3
"""Prove every standalone organ package on exact, modern-only HTTP wire."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROTOCOL = "2026-07-28"
PYTHON = Path("/srv/abyss-machine/cache/mcp-modern-fleet-20260809/venv/bin/python")
EVIDENCE_ROOT = Path("/srv/abyss-machine/cache/mcp-modern-fleet-20260809/evidence")
SERVERS = (
    ("abyss-machine", "abyss_machine_mcp", "ABYSS_MACHINE_MCP_READ_BEARER_TOKEN", True),
    ("abyss-stack", "abyss_stack_mcp", "ABYSS_STACK_MCP_READ_BEARER_TOKEN", False),
    ("aoa-4pda-connector", "aoa_4pda_connector_mcp", "AOA_4PDA_CONNECTOR_MCP_READ_BEARER_TOKEN", True),
    ("aoa-course-connector", "aoa_course_connector_mcp", "AOA_COURSE_CONNECTOR_MCP_READ_BEARER_TOKEN", False),
    ("aoa-decisions", "aoa_decisions_mcp", "AOA_DECISIONS_MCP_READ_BEARER_TOKEN", True),
    ("aoa-discord-connector", "aoa_discord_connector_mcp", "AOA_DISCORD_CONNECTOR_MCP_READ_BEARER_TOKEN", True),
    ("aoa-evals", "aoa_evals_mcp", "AOA_EVALS_MCP_READ_BEARER_TOKEN", True),
    ("aoa-kag", "aoa_kag_mcp", "AOA_KAG_MCP_READ_BEARER_TOKEN", True),
    ("aoa-memo", "aoa_memo_mcp", "AOA_MEMO_MCP_READ_BEARER_TOKEN", True),
    ("aoa-session-memory", "aoa_session_memory_mcp", "AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN", True),
    ("aoa-stackoverflow-connector", "aoa_stackoverflow_connector_mcp", "AOA_STACKOVERFLOW_CONNECTOR_MCP_READ_BEARER_TOKEN", False),
    ("aoa-stats", "aoa_stats_mcp", "AOA_STATS_MCP_READ_BEARER_TOKEN", True),
    ("aoa-telegram-connector", "aoa_telegram_connector_mcp", "AOA_TELEGRAM_CONNECTOR_MCP_READ_BEARER_TOKEN", True),
    ("aoa-xda-connector", "aoa_xda_connector_mcp", "AOA_XDA_CONNECTOR_MCP_READ_BEARER_TOKEN", False),
    ("tos-corpus", "tos_corpus_mcp", "TOS_CORPUS_MCP_READ_BEARER_TOKEN", False),
)


def _free_port() -> int:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    return port


def _wait_port(port: int, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _, stderr = process.communicate(timeout=2)
            raise RuntimeError(stderr.decode(errors="replace")[-8000:])
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        finally:
            probe.close()
        time.sleep(0.05)
    raise TimeoutError(f"server did not bind port {port}")


def _request(
    url: str,
    bearer: str,
    method: str,
    params: dict[str, Any],
    *,
    modern: bool = True,
) -> tuple[int, dict[str, Any] | None, dict[str, str]]:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        separators=(",", ":"),
    ).encode()
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
    }
    if modern:
        headers["MCP-Method"] = method
        headers["MCP-Protocol-Version"] = PROTOCOL
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else None, dict(response.headers)
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        parsed = json.loads(payload) if payload and payload.startswith(b"{") else None
        return exc.code, parsed, dict(exc.headers)


def _meta() -> dict[str, Any]:
    return {
        "_meta": {
            "io.modelcontextprotocol/clientInfo": {
                "name": "abyss-modern-fleet-matrix",
                "version": "1",
            },
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/protocolVersion": PROTOCOL,
        }
    }


def _probe_server(
    name: str,
    module: str,
    token_env: str,
    active: bool,
    run_root: Path,
) -> dict[str, Any]:
    bearer = secrets.token_urlsafe(48)
    port = _free_port()
    url = f"http://127.0.0.1:{port}/mcp"
    env = os.environ.copy()
    env.update(
        {
            "AOA_MCP_TRANSPORT": "streamable-http",
            "AOA_MCP_HOST": "127.0.0.1",
            "AOA_MCP_PORT": str(port),
            token_env: bearer,
            "PYTHONDONTWRITEBYTECODE": "1",
            "ABYSS_STACK_MCP_POLICY_FAMILY": "read",
            "ABYSS_STACK_MCP_OBSERVATION_PATH": (
                "/srv/AbyssOS/abyss-stack/Logs/mcp/observations/current.json"
            ),
            "ABYSS_STACK_MCP_TASKS_ENABLED": "0",
            "AOA_SESSION_MEMORY_MCP_AUTO_RELOAD": "0",
        }
    )
    process = subprocess.Popen(
        [str(PYTHON), "-I", "-B", "-c", f"from {module}.server import main; main()"],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_port(port, process)
        status, discover, discover_headers = _request(
            url, bearer, "server/discover", _meta()
        )
        if status != 200 or not isinstance(discover, dict):
            raise RuntimeError(f"{name} modern discovery failed: {status} {discover}")
        result = discover.get("result")
        if not isinstance(result, dict) or result.get("supportedVersions") != [PROTOCOL]:
            raise RuntimeError(f"{name} advertised the wrong versions: {discover}")

        status, inventory, _ = _request(url, bearer, "tools/list", _meta())
        tools = inventory.get("result", {}).get("tools") if isinstance(inventory, dict) else None
        if status != 200 or not isinstance(tools, list) or not tools:
            raise RuntimeError(f"{name} tool inventory failed: {status} {inventory}")

        wrong_status, _, _ = _request(
            url, secrets.token_urlsafe(48), "server/discover", _meta()
        )
        legacy_status, legacy, legacy_headers = _request(
            url,
            bearer,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "denied-legacy", "version": "1"},
            },
            modern=False,
        )
        legacy_error = legacy.get("error") if isinstance(legacy, dict) else None
        if (
            wrong_status != 401
            or legacy_status != 400
            or not isinstance(legacy_error, dict)
            or legacy_error.get("code") != -32022
            or legacy_headers.get("Mcp-Session-Id") is not None
        ):
            raise RuntimeError(
                f"{name} negative gates failed: wrong={wrong_status}, legacy={legacy_status} {legacy}"
            )

        canonical_tools = json.dumps(tools, sort_keys=True, separators=(",", ":")).encode()
        return {
            "name": name,
            "active_codex_organ": active,
            "protocol_version": PROTOCOL,
            "server_info": result.get("_meta", {}).get(
                "io.modelcontextprotocol/serverInfo"
            ),
            "tool_count": len(tools),
            "tool_schema_sha256": hashlib.sha256(canonical_tools).hexdigest(),
            "modern_response_header": discover_headers.get("MCP-Protocol-Version"),
            "wrong_bearer_status": wrong_status,
            "legacy_status": legacy_status,
            "legacy_error_code": legacy_error["code"],
            "legacy_session_issued": False,
            "verdict": "passed",
        }
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main() -> int:
    observed_at = datetime.now(UTC)
    run_root = EVIDENCE_ROOT / observed_at.strftime("modern-fleet-%Y%m%dT%H%M%SZ")
    run_root.mkdir(mode=0o700, parents=True)
    rows = [
        _probe_server(name, module, token_env, active, run_root)
        for name, module, token_env, active in SERVERS
    ]
    receipt = {
        "schema_version": "abyss_modern_organ_fleet_matrix_v1",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "mcp_sdk": "2.0.0",
        "required_protocol": PROTOCOL,
        "active_count": sum(1 for row in rows if row["active_codex_organ"]),
        "package_count": len(rows),
        "servers": rows,
        "zero_legacy": all(
            row["legacy_status"] == 400
            and row["legacy_error_code"] == -32022
            and not row["legacy_session_issued"]
            for row in rows
        ),
    }
    receipt["verdict"] = (
        "passed"
        if receipt["zero_legacy"] and all(row["verdict"] == "passed" for row in rows)
        else "failed"
    )
    output = run_root / "receipt.json"
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    os.chmod(output, 0o600)
    if receipt["verdict"] != "passed":
        raise RuntimeError(json.dumps(receipt, indent=2))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
