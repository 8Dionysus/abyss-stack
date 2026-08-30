#!/usr/bin/env python3
"""Probe configured non-read MCP contours without invoking effects."""

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

from runtime_catalog import (
    credentials_root,
    load_runtime_catalog,
    mcp_settings,
    nonread_probe_entries,
    probe_limits,
    registry_path,
    runtime_config_path,
    stack_root_from_catalog,
)


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def _state(unit: str) -> str:
    return _run(
        "systemctl", "--user", "show", unit, "-p", "ActiveState", "--value"
    ).stdout.strip()


def _load_token(credentials: Path, name: str) -> str:
    path = credentials / name
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o777 != 0o600:
        raise RuntimeError(f"unsafe non-read credential: {name}")
    value = path.read_text(encoding="utf-8").strip()
    if not 43 <= len(value) <= 512:
        raise RuntimeError(f"invalid non-read credential: {name}")
    return value


def _meta(protocol: str) -> dict[str, Any]:
    return {
        "_meta": {
            "io.modelcontextprotocol/clientInfo": {
                "name": "abyss-live-nonread-protocol",
                "version": "1",
            },
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/protocolVersion": protocol,
        }
    }


def _request(
    url: str,
    bearer: str,
    method: str,
    params: dict[str, Any],
    *,
    protocol: str,
    modern: bool = True,
    timeout: float = 15.0,
) -> tuple[int, dict[str, Any] | None, dict[str, str]]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
    }
    if modern:
        headers.update({"MCP-Method": method, "MCP-Protocol-Version": protocol})
        if method == "tools/call" and isinstance(params.get("name"), str):
            headers["MCP-Name"] = params["name"]
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        separators=(",", ":"),
    ).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None, dict(response.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        payload = json.loads(raw) if raw.startswith(b"{") else None
        return exc.code, payload, dict(exc.headers)


def _wait_running(
    unit: str,
    host: str,
    port: int,
    *,
    server_start_timeout: float,
    connect_timeout: float,
) -> None:
    deadline = time.monotonic() + server_start_timeout
    while time.monotonic() < deadline:
        if _state(unit) == "active":
            try:
                with socket.create_connection((host, port), timeout=connect_timeout):
                    return
            except OSError:
                pass
        time.sleep(0.1)
    raise RuntimeError(f"non-read unit did not become ready: {unit}")


def _admitted_nonread(registry: Path) -> set[tuple[str, str]]:
    source = json.loads(registry.read_text(encoding="utf-8"))
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
    declared: dict[str, Any],
    admitted: set[tuple[str, str]],
    *,
    protocol: str,
    legacy_protocol: str,
    rejection_code: int,
    request_timeout: float,
    server_start_timeout: float,
    connect_timeout: float,
    path: str,
    host: str,
    credentials: Path,
) -> dict[str, Any]:
    if _state(unit) != "inactive":
        raise RuntimeError(f"non-read unit was not inactive before probe: {unit}")
    auth = declared["auth"]
    port = int(declared["port"])
    token = _load_token(credentials, str(auth["credential_name"]))
    url_host = f"[{host}]" if ":" in host else host
    url = f"http://{url_host}:{port}{path}"
    _run("systemctl", "--user", "start", "--no-block", unit)
    try:
        _wait_running(
            unit,
            host,
            port,
            server_start_timeout=server_start_timeout,
            connect_timeout=connect_timeout,
        )
        status, discover, _ = _request(
            url,
            token,
            "server/discover",
            _meta(protocol),
            protocol=protocol,
            timeout=request_timeout,
        )
        result = discover.get("result") if isinstance(discover, dict) else None
        inventory_status, inventory, _ = _request(
            url,
            token,
            "tools/list",
            _meta(protocol),
            protocol=protocol,
            timeout=request_timeout,
        )
        tools = inventory.get("result", {}).get("tools") if isinstance(inventory, dict) else None
        wrong_status, _, _ = _request(
            url,
            secrets.token_urlsafe(48),
            "server/discover",
            _meta(protocol),
            protocol=protocol,
            timeout=request_timeout,
        )
        legacy_status, legacy, legacy_headers = _request(
            url,
            token,
            "initialize",
            {
                "protocolVersion": legacy_protocol,
                "capabilities": {},
                "clientInfo": {"name": "denied-legacy", "version": "1"},
            },
            protocol=protocol,
            timeout=request_timeout,
            modern=False,
        )
        legacy_error = legacy.get("error") if isinstance(legacy, dict) else None
        passed = (
            status == 200
            and isinstance(result, dict)
            and result.get("supportedVersions") == [protocol]
            and inventory_status == 200
            and isinstance(tools, list)
            and bool(tools)
            and wrong_status == 401
            and legacy_status == 400
            and isinstance(legacy_error, dict)
            and legacy_error.get("code") == rejection_code
            and legacy_headers.get("Mcp-Session-Id") is None
            and (organ, contour) not in admitted
        )
        if not passed:
            raise RuntimeError(f"non-read protocol probe failed: {organ}/{contour}")
        return {
            "organ_id": organ,
            "contour_id": contour,
            "unit": unit,
            "protocol_version": protocol,
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
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--stack-root", type=Path)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    config_path = runtime_config_path(args.runtime_config).resolve()
    catalog = load_runtime_catalog(config_path)
    _, protocol_settings, transport_settings = mcp_settings(catalog)
    limits = probe_limits(catalog)
    protocol = str(protocol_settings["version"])
    legacy_protocol = str(protocol_settings["legacy_version"])
    rejection_code = int(protocol_settings["modern_only_rejection_code"])
    path = str(protocol_settings["streamable_http_path"])
    host = str(transport_settings["default_host"])
    stack = args.stack_root or stack_root_from_catalog(config_path)
    if not stack.is_absolute():
        raise RuntimeError("--stack-root must be an absolute path")
    registry = args.registry or registry_path(catalog, stack)
    credentials = credentials_root(catalog, stack)
    admitted = _admitted_nonread(registry)
    if admitted:
        raise RuntimeError(f"unexpected admitted non-read contours: {sorted(admitted)}")
    entries = nonread_probe_entries(catalog)
    rows = [
        _probe(
            organ,
            contour,
            unit,
            declared,
            admitted,
            protocol=protocol,
            legacy_protocol=legacy_protocol,
            rejection_code=rejection_code,
            request_timeout=limits["protocol_probe_request_timeout_seconds"],
            server_start_timeout=limits["protocol_probe_server_start_timeout_seconds"],
            connect_timeout=limits["protocol_probe_connect_timeout_seconds"],
            path=path,
            host=host,
            credentials=credentials,
        )
        for organ, contour, unit, _service, declared in entries
    ]
    receipt = {
        "schema_version": "abyss_live_nonread_protocol_v1",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "protocol_version": protocol,
        "candidate_units_checked": sum(row["contour_id"] == "candidate" for row in rows),
        "internal_effect_units_checked": sum(
            row["contour_id"] == "internal_effect" for row in rows
        ),
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
