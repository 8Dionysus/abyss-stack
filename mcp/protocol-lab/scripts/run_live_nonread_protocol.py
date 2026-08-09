#!/usr/bin/env python3
"""Probe non-read MCP contours without invoking tools or granting authority."""

from __future__ import annotations

import argparse
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
STACK = Path("/srv/AbyssOS/abyss-stack")
REGISTRY = Path("/srv/AbyssOS/.aoa/organ-access/organ-registry.v2.source.json")
CONTOURS = (
    (
        "abyss-stack",
        "candidate",
        "abyss-stack-mcp-candidate.service",
        5433,
        "abyss-stack-mcp-candidate-bearer-token",
    ),
    (
        "aoa-memo",
        "candidate",
        "aoa-memo-mcp-candidate.service",
        5434,
        "aoa-memo-mcp-candidate-bearer-token",
    ),
    (
        "aoa-evals",
        "candidate",
        "aoa-evals-mcp-candidate.service",
        5435,
        "aoa-evals-mcp-candidate-bearer-token",
    ),
    (
        "abyss-stack",
        "internal_effect",
        "abyss-stack-mcp-internal-effect.service",
        5439,
        "abyss-stack-mcp-internal-effect-bearer-token",
    ),
)


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def _state(unit: str) -> str:
    return _run(
        "systemctl", "--user", "show", unit, "-p", "ActiveState", "--value"
    ).stdout.strip()


def _load_token(name: str) -> str:
    path = STACK / "Secrets/Configs" / name
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o777 != 0o600:
        raise RuntimeError(f"unsafe non-read credential: {name}")
    value = path.read_text(encoding="utf-8").strip()
    if not 43 <= len(value) <= 512:
        raise RuntimeError(f"invalid non-read credential: {name}")
    return value


def _meta() -> dict[str, Any]:
    return {
        "_meta": {
            "io.modelcontextprotocol/clientInfo": {
                "name": "abyss-live-nonread-protocol",
                "version": "1",
            },
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/protocolVersion": PROTOCOL,
        }
    }


def _request(
    url: str,
    bearer: str,
    method: str,
    params: dict[str, Any],
    *,
    modern: bool = True,
) -> tuple[int, dict[str, Any] | None, dict[str, str]]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
    }
    if modern:
        headers.update({"MCP-Method": method, "MCP-Protocol-Version": PROTOCOL})
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        separators=(",", ":"),
    ).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None, dict(response.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        payload = json.loads(raw) if raw.startswith(b"{") else None
        return exc.code, payload, dict(exc.headers)


def _wait_running(unit: str, port: int) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if _state(unit) == "active":
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.settimeout(0.2)
            try:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    return
            finally:
                probe.close()
        time.sleep(0.1)
    raise RuntimeError(f"non-read unit did not become ready: {unit}")


def _admitted_nonread() -> set[tuple[str, str]]:
    source = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {
        (record["organ_id"], contour["contour_id"])
        for record in source["records"]
        for contour in record["contours"]
        if contour["registry_state"] == "admitted" and contour["contour_id"] != "read"
    }


def _probe(
    organ: str,
    contour: str,
    unit: str,
    port: int,
    credential: str,
    admitted: set[tuple[str, str]],
) -> dict[str, Any]:
    if _state(unit) != "inactive":
        raise RuntimeError(f"non-read unit was not inactive before probe: {unit}")
    token = _load_token(credential)
    url = f"http://127.0.0.1:{port}/mcp"
    _run("systemctl", "--user", "start", "--no-block", unit)
    try:
        _wait_running(unit, port)
        status, discover, _ = _request(url, token, "server/discover", _meta())
        result = discover.get("result") if isinstance(discover, dict) else None
        inventory_status, inventory, _ = _request(url, token, "tools/list", _meta())
        tools = inventory.get("result", {}).get("tools") if isinstance(inventory, dict) else None
        wrong_status, _, _ = _request(
            url, secrets.token_urlsafe(48), "server/discover", _meta()
        )
        legacy_status, legacy, legacy_headers = _request(
            url,
            token,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "denied-legacy", "version": "1"},
            },
            modern=False,
        )
        legacy_error = legacy.get("error") if isinstance(legacy, dict) else None
        passed = (
            status == 200
            and isinstance(result, dict)
            and result.get("supportedVersions") == [PROTOCOL]
            and inventory_status == 200
            and isinstance(tools, list)
            and bool(tools)
            and wrong_status == 401
            and legacy_status == 400
            and isinstance(legacy_error, dict)
            and legacy_error.get("code") == -32022
            and legacy_headers.get("Mcp-Session-Id") is None
            and (organ, contour) not in admitted
        )
        if not passed:
            raise RuntimeError(f"non-read protocol probe failed: {organ}/{contour}")
        return {
            "organ_id": organ,
            "contour_id": contour,
            "unit": unit,
            "protocol_version": PROTOCOL,
            "tool_count": len(tools),
            "tool_invoked": False,
            "wrong_bearer_status": wrong_status,
            "legacy_status": legacy_status,
            "legacy_error_code": legacy_error["code"],
            "legacy_session_issued": False,
            "authority_admitted": False,
            "verdict": "passed",
        }
    finally:
        _run("systemctl", "--user", "stop", unit, check=False)
        if _state(unit) != "inactive":
            raise RuntimeError(f"non-read unit remained active after probe: {unit}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    admitted = _admitted_nonread()
    if admitted:
        raise RuntimeError(f"unexpected admitted non-read contours: {sorted(admitted)}")
    rows = [_probe(*entry, admitted) for entry in CONTOURS]
    receipt = {
        "schema_version": "abyss_live_nonread_protocol_v1",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "protocol_version": PROTOCOL,
        "candidate_units_checked": 3,
        "internal_effect_units_checked": 1,
        "contours": rows,
        "modern_discovery_passed": True,
        "legacy_initialize_denied": True,
        "left_inactive": all(_state(row["unit"]) == "inactive" for row in rows),
        "authority_admitted": False,
        "verdict": "passed",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    os.chmod(args.output, 0o600)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
