#!/usr/bin/env python3
"""Prove the admitted production read fleet on exact modern-only MCP wire."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from canary_contract import load_canary_contracts, verify_structured_result
from runtime_catalog import (
    admitted_read_entries,
    contour_unit_name,
    credentials_root,
    load_runtime_catalog,
    mcp_settings,
    probe_limits,
    registry_path,
    runtime_config_path,
    runtime_identity,
    runtime_python_path,
    stack_root_from_catalog,
)


def _load_token(credentials: Path, name: str) -> str:
    path = credentials / name
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o777 != 0o600:
        raise RuntimeError(f"unsafe production credential: {name}")
    token = path.read_text(encoding="utf-8").strip()
    if not 43 <= len(token) <= 512:
        raise RuntimeError(f"invalid production credential: {name}")
    return token


def _meta(protocol: str) -> dict[str, Any]:
    return {
        "_meta": {
            "io.modelcontextprotocol/clientInfo": {
                "name": "abyss-live-modern-read-fleet",
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


def _unit_identity(unit: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "-p",
            "ActiveState",
            "-p",
            "SubState",
            "-p",
            "MainPID",
            "-p",
            "ExecMainStartTimestampMonotonic",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    values = dict(line.split("=", 1) for line in completed.stdout.splitlines())
    if values.get("ActiveState") != "active" or values.get("SubState") != "running":
        raise RuntimeError(f"production unit is not running: {unit}")
    pid = int(values["MainPID"])
    if pid <= 0:
        raise RuntimeError(f"production unit has no main process: {unit}")
    return {
        "unit": unit,
        "process_identity": (
            f"systemd-user:{unit}:pid:{pid}:start:"
            f"{values['ExecMainStartTimestampMonotonic']}"
        ),
    }


def _registry_facts(
    catalog: dict[str, Any], registry: Path
) -> tuple[dict[str, Any], list[tuple[str, str, dict[str, Any], dict[str, Any]]]]:
    source = json.loads(registry.read_text(encoding="utf-8"))
    entries = admitted_read_entries(catalog, source)
    rows = [
        contour
        for record in source["records"]
        for contour in record["contours"]
        if contour["contour_id"] == "read" and contour["registry_state"] == "admitted"
    ]
    facts = {
        "registry_id": source["registry_id"],
        "expires_at": source["expires_at"],
        "admitted_read_count": len(rows),
        "protocol_versions": sorted(
            {version for row in rows for version in row["endpoint"]["protocol_versions"]}
        ),
        "bootstrap_identity_count": sum(
            "bootstrap" in row["runtime_identity"]["process_identity"] for row in rows
        ),
    }
    if len(entries) != len(rows):
        raise RuntimeError("MCP runtime catalog and admitted registry coverage disagree")
    return facts, entries


def _semantic_probe(
    url: str,
    token: str,
    contract: dict[str, Any],
    *,
    protocol: str,
    transport: str,
    rejection_code: int,
    request_timeout: float,
) -> dict[str, Any]:
    tool_name = contract.get("tool_name")
    arguments = contract.get("arguments")
    if not isinstance(tool_name, str) or not isinstance(arguments, dict):
        raise RuntimeError("invalid live MCP canary contract")
    params = {"name": tool_name, "arguments": arguments}
    params.update(_meta(protocol))
    status, response, headers = _request(
        url,
        token,
        "tools/call",
        params,
        protocol=protocol,
        timeout=request_timeout,
    )
    result = response.get("result") if isinstance(response, dict) else None
    structured = result.get("structuredContent") if isinstance(result, dict) else None
    reasons: list[str] = []
    if status != 200:
        reasons.append("http_status_not_ok")
    if not isinstance(result, dict):
        reasons.append("jsonrpc_result_missing")
    if isinstance(result, dict) and result.get("isError") is True:
        reasons.append("tool_returned_error")
    verified = verify_structured_result(structured, contract, transport=transport)
    reasons.extend(verified["reason_codes"])
    reasons = list(dict.fromkeys(reasons))
    error = response.get("error") if isinstance(response, dict) else None
    return {
        "tool_name": tool_name,
        "http_status": status,
        "jsonrpc_error_code": error.get("code") if isinstance(error, dict) else None,
        "response_protocol_header": headers.get("MCP-Protocol-Version"),
        "result_schema_identity": verified["result_schema_identity"],
        "result_sha256": verified["result_sha256"],
        "reason_codes": reasons,
        "rejection_code_policy": rejection_code,
        "verdict": "passed" if not reasons else "failed",
    }


def _probe(
    organ: str,
    service_id: str,
    service: dict[str, Any],
    contour: dict[str, Any],
    *,
    protocol: str,
    legacy_protocol: str,
    rejection_code: int,
    request_timeout: float,
    canary_contract: dict[str, Any],
    path: str,
    host: str,
    credentials: Path,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    auth = contour["auth"]
    port = int(contour["port"])
    unit = contour_unit_name(catalog, service_id, "read", organ)
    token = _load_token(credentials, str(auth["credential_name"]))
    url_host = f"[{host}]" if ":" in host else host
    url = f"http://{url_host}:{port}{path}"
    status, discover, headers = _request(
        url,
        token,
        "server/discover",
        _meta(protocol),
        protocol=protocol,
        timeout=request_timeout,
    )
    result = discover.get("result") if isinstance(discover, dict) else None
    if status != 200 or not isinstance(result, dict):
        raise RuntimeError(f"{organ} discovery failed: {status} {discover}")
    status, inventory, _ = _request(
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
        result.get("supportedVersions") == [protocol]
        and status == 200
        and isinstance(tools, list)
        and bool(tools)
        and wrong_status == 401
        and legacy_status == 400
        and isinstance(legacy_error, dict)
        and legacy_error.get("code") == rejection_code
        and legacy_headers.get("Mcp-Session-Id") is None
    )
    if not passed:
        raise RuntimeError(f"{organ} modern-only gates failed")
    try:
        semantic = _semantic_probe(
            url,
            token,
            canary_contract,
            protocol=protocol,
            transport=str(catalog["mcp"]["transport"]["streamable_http_transport"]),
            rejection_code=rejection_code,
            request_timeout=request_timeout,
        )
    except Exception as exc:
        semantic = {
            "tool_name": canary_contract.get("tool_name"),
            "verdict": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[-1024:],
            "reason_codes": ["semantic_probe_exception"],
        }
    encoded_tools = json.dumps(tools, sort_keys=True, separators=(",", ":")).encode()
    return {
        "organ_id": organ,
        "endpoint_ref": url,
        **_unit_identity(unit),
        "protocol_version": protocol,
        "server_info": result.get("_meta", {}).get("io.modelcontextprotocol/serverInfo"),
        "tool_count": len(tools),
        "tool_schema_sha256": hashlib.sha256(encoded_tools).hexdigest(),
        "modern_response_header": headers.get("MCP-Protocol-Version"),
        "wrong_bearer_status": wrong_status,
        "legacy_status": legacy_status,
        "legacy_error_code": legacy_error["code"],
        "legacy_session_issued": False,
        "semantic_probe": semantic,
        "verdict": "passed" if semantic["verdict"] == "passed" else "failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--stack-root", type=Path)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    config_path = runtime_config_path(args.runtime_config).resolve()
    catalog = load_runtime_catalog(config_path)
    sdk_settings, protocol_settings, transport_settings = mcp_settings(catalog)
    limits = probe_limits(catalog)
    protocol = str(protocol_settings["version"])
    legacy_protocol = str(protocol_settings["legacy_version"])
    rejection_code = int(protocol_settings["modern_only_rejection_code"])
    path = str(protocol_settings["streamable_http_path"])
    host = str(transport_settings["default_host"])
    stack = args.stack_root or stack_root_from_catalog(config_path)
    if not stack.is_absolute():
        raise RuntimeError("--stack-root must be an absolute path")
    registry_file = args.registry or registry_path(catalog, stack)
    credentials = credentials_root(catalog, stack)
    contracts = load_canary_contracts()
    if set(contracts) != {str(service["service_id"]) for service in catalog["services"]}:
        raise RuntimeError("live canary coverage and MCP package catalog differ")
    registry, entries = _registry_facts(catalog, registry_file)
    rows: list[dict[str, Any]] = []
    for organ, service_id, service, contour in entries:
        try:
            rows.append(
                _probe(
                    organ,
                    service_id,
                    service,
                    contour,
                    protocol=protocol,
                    legacy_protocol=legacy_protocol,
                    rejection_code=rejection_code,
                    request_timeout=limits["protocol_probe_request_timeout_seconds"],
                    canary_contract=contracts[service_id],
                    path=path,
                    host=host,
                    credentials=credentials,
                    catalog=catalog,
                )
            )
        except Exception as exc:
            rows.append(
                {
                    "organ_id": organ,
                    "endpoint_ref": None,
                    "verdict": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[-4000:],
                }
            )
    runtime_python = runtime_python_path(catalog, stack, "abyss-stack-mcp")
    sdk_identity = runtime_identity(runtime_python, sdk_settings)
    receipt = {
        "schema_version": "abyss_live_modern_read_fleet_v1",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "protocol_version": protocol,
        "mcp_sdk": sdk_identity["versions"].get(sdk_settings["distribution"]),
        "mcp_companion_sdk": sdk_identity["versions"].get(
            sdk_settings["companion_distribution"]
        ),
        "runtime_identity": sdk_identity,
        "production_unit_count": len(rows),
        "semantic_probe_count": sum(
            row.get("semantic_probe", {}).get("verdict") == "passed"
            for row in rows
        ),
        "registry": registry,
        "servers": rows,
        "zero_legacy": all(
            row.get("legacy_status") == 400
            and row.get("legacy_error_code") == rejection_code
            and not row.get("legacy_session_issued", True)
            for row in rows
        ),
    }
    receipt["verdict"] = (
        "passed"
        if sdk_identity["exact_pair"]
        and registry["admitted_read_count"] == len(rows)
        and registry["protocol_versions"] == [protocol]
        and registry["bootstrap_identity_count"] == 0
        and receipt["zero_legacy"]
        else "failed"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    os.chmod(args.output, 0o600)
    if receipt["verdict"] != "passed":
        raise RuntimeError(json.dumps(receipt, indent=2))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
