#!/usr/bin/env python3
"""Prove every standalone organ package on exact, modern-only HTTP wire."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from canary_contract import load_canary_contracts, verify_structured_result
from runtime_catalog import (
    load_runtime_catalog,
    mcp_settings,
    probe_limits,
    runtime_identity,
)


def _semantic_probe(
    url: str,
    bearer: str,
    contract: dict[str, Any],
    *,
    protocol: str,
    transport: str,
    request_timeout: float,
) -> dict[str, Any]:
    """Invoke exactly one reviewed observe-only canary and verify its contract."""

    tool_name = contract.get("tool_name")
    arguments = contract.get("arguments")
    if not isinstance(tool_name, str) or not isinstance(arguments, dict):
        raise RuntimeError("read canary contract has invalid tool identity or arguments")
    call_params = {"name": tool_name, "arguments": arguments}
    call_params.update(_meta(protocol))
    status, response, headers = _request(
        url,
        bearer,
        "tools/call",
        call_params,
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
    if not isinstance(structured, dict):
        reasons.append("structured_content_missing")
    verified = verify_structured_result(structured, contract, transport=transport)
    reasons.extend(verified["reason_codes"])
    reasons = list(dict.fromkeys(reasons))
    error = response.get("error") if isinstance(response, dict) else None
    return {
        "tool_name": tool_name,
        "http_status": status,
        "jsonrpc_error_code": error.get("code") if isinstance(error, dict) else None,
        "jsonrpc_error_message": (
            str(error.get("message", ""))[:256] if isinstance(error, dict) else None
        ),
        "structured_content": verified["structured_content"],
        "result_schema_identity": verified["result_schema_identity"],
        "result_sha256": verified["result_sha256"],
        "response_protocol_header": headers.get("MCP-Protocol-Version"),
        "reason_codes": reasons,
        "verdict": "passed" if not reasons else "failed",
    }


def _free_port(host: str) -> int:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    listener = socket.socket(family, socket.SOCK_STREAM)
    listener.bind((host, 0))
    port = listener.getsockname()[1]
    listener.close()
    return port


def _wait_port(
    host: str,
    port: int,
    process: subprocess.Popen[bytes],
    *,
    server_start_timeout: float,
    connect_timeout: float,
    process_exit_timeout: float,
) -> None:
    deadline = time.monotonic() + server_start_timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _, stderr = process.communicate(timeout=process_exit_timeout)
            raise RuntimeError(stderr.decode(errors="replace")[-8000:])
        try:
            with socket.create_connection((host, port), timeout=connect_timeout):
                return
        except OSError:
            pass
        time.sleep(0.05)
    raise TimeoutError(f"server did not bind port {port}")


def _request(
    url: str,
    bearer: str,
    method: str,
    params: dict[str, Any],
    *,
    protocol: str,
    timeout: float,
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
        headers["MCP-Protocol-Version"] = protocol
        if method == "tools/call" and isinstance(params.get("name"), str):
            headers["MCP-Name"] = params["name"]
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else None, dict(response.headers)
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        parsed = json.loads(payload) if payload and payload.startswith(b"{") else None
        return exc.code, parsed, dict(exc.headers)


def _meta(protocol: str) -> dict[str, Any]:
    return {
        "_meta": {
            "io.modelcontextprotocol/clientInfo": {
                "name": "abyss-modern-fleet-matrix",
                "version": "1",
            },
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/protocolVersion": protocol,
        }
    }


def _probe_server(
    service: dict[str, Any],
    contour: dict[str, Any],
    *,
    protocol: str,
    legacy_protocol: str,
    rejection_code: int,
    path: str,
    host: str,
    python: Path,
    workspace_root: Path,
    workspace_env_var: str,
    transport: dict[str, Any],
    active: bool,
    canary_contract: dict[str, Any],
    limits: dict[str, float],
) -> dict[str, Any]:
    name = str(service["organ_id"])
    source_package_root = (
        Path(__file__).resolve().parents[2]
        / "services"
        / str(service["service_id"])
        / "src"
    )
    if not source_package_root.is_dir():
        raise RuntimeError(
            f"MCP source package projection is unavailable: {source_package_root}"
        )
    module = str(service["module"])
    auth = contour["auth"]
    token_env = str(auth["token_env_var"])
    bearer = secrets.token_urlsafe(48)
    port = _free_port(host)
    url_host = f"[{host}]" if ":" in host else host
    url = f"http://{url_host}:{port}{path}"
    env = os.environ.copy()
    transport_env_var = str(transport["transport_env_var"])
    host_env_var = str(transport["host_env_var"])
    port_env_var = str(transport["port_env_var"])
    env.update(
        {
            transport_env_var: "streamable-http",
            host_env_var: host,
            port_env_var: str(port),
            workspace_env_var: str(workspace_root),
            token_env: bearer,
            "PYTHONDONTWRITEBYTECODE": "1",
            "ABYSS_STACK_MCP_POLICY_FAMILY": "read",
            "ABYSS_STACK_MCP_TASKS_ENABLED": "0",
            "AOA_SESSION_MEMORY_MCP_AUTO_RELOAD": "0",
        }
    )
    observation_path = os.environ.get("ABYSS_STACK_MCP_OBSERVATION_PATH", "").strip()
    if observation_path and name == "abyss-stack":
        env["ABYSS_STACK_MCP_OBSERVATION_PATH"] = observation_path
    process = subprocess.Popen(
        [
            str(python),
            "-I",
            "-B",
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(source_package_root)!r}); "
                f"from {module}.server import main; main()"
            ),
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_port(
            host,
            port,
            process,
            server_start_timeout=limits["protocol_probe_server_start_timeout_seconds"],
            connect_timeout=limits["protocol_probe_connect_timeout_seconds"],
            process_exit_timeout=limits["protocol_probe_process_kill_timeout_seconds"],
        )
        status, discover, discover_headers = _request(
            url,
            bearer,
            "server/discover",
            _meta(protocol),
            protocol=protocol,
            timeout=limits["protocol_probe_request_timeout_seconds"],
        )
        if status != 200 or not isinstance(discover, dict):
            raise RuntimeError(f"{name} modern discovery failed: {status} {discover}")
        result = discover.get("result")
        if not isinstance(result, dict) or result.get("supportedVersions") != [protocol]:
            raise RuntimeError(f"{name} advertised the wrong versions: {discover}")

        status, inventory, _ = _request(
            url,
            bearer,
            "tools/list",
            _meta(protocol),
            protocol=protocol,
            timeout=limits["protocol_probe_request_timeout_seconds"],
        )
        tools = inventory.get("result", {}).get("tools") if isinstance(inventory, dict) else None
        if status != 200 or not isinstance(tools, list) or not tools:
            raise RuntimeError(f"{name} tool inventory failed: {status} {inventory}")

        wrong_status, _, _ = _request(
            url,
            secrets.token_urlsafe(48),
            "server/discover",
            _meta(protocol),
            protocol=protocol,
            timeout=limits["protocol_probe_request_timeout_seconds"],
        )
        legacy_status, legacy, legacy_headers = _request(
            url,
            bearer,
            "initialize",
            {
                "protocolVersion": legacy_protocol,
                "capabilities": {},
                "clientInfo": {"name": "denied-legacy", "version": "1"},
            },
            protocol=protocol,
            timeout=limits["protocol_probe_request_timeout_seconds"],
            modern=False,
        )
        legacy_error = legacy.get("error") if isinstance(legacy, dict) else None
        if (
            wrong_status != 401
            or legacy_status != 400
            or not isinstance(legacy_error, dict)
            or legacy_error.get("code") != rejection_code
            or legacy_headers.get("Mcp-Session-Id") is not None
        ):
            raise RuntimeError(
                f"{name} negative gates failed: wrong={wrong_status}, legacy={legacy_status} {legacy}"
            )

        semantic = _semantic_probe(
            url,
            bearer,
            canary_contract,
            protocol=protocol,
            transport=str(transport["streamable_http_transport"]),
            request_timeout=limits["protocol_probe_request_timeout_seconds"],
        )
        canonical_tools = json.dumps(tools, sort_keys=True, separators=(",", ":")).encode()
        return {
            "name": name,
            "active_codex_organ": active,
            "protocol_version": protocol,
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
            "semantic_probe": semantic,
            "verdict": "passed" if semantic["verdict"] == "passed" else "failed",
        }
    finally:
        process.terminate()
        try:
            process.wait(
                timeout=limits["protocol_probe_process_shutdown_timeout_seconds"]
            )
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=limits["protocol_probe_process_kill_timeout_seconds"])


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path)
    args = parser.parse_args()
    catalog = load_runtime_catalog()
    canary_contracts = load_canary_contracts()
    catalog_service_ids = {str(item["service_id"]) for item in catalog["services"]}
    if set(canary_contracts) != catalog_service_ids:
        raise RuntimeError(
            "runtime target canary coverage and MCP package catalog differ: "
            f"missing={sorted(catalog_service_ids - set(canary_contracts))}, "
            f"extra={sorted(set(canary_contracts) - catalog_service_ids)}"
        )
    sdk_settings, protocol_settings, transport_settings = mcp_settings(catalog)
    limits = probe_limits(catalog)
    paths = catalog.get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError("MCP runtime catalog has no path settings")
    workspace_env_var = str(paths["workspace_env_var"])
    protocol = str(protocol_settings["version"])
    legacy_protocol = str(protocol_settings["legacy_version"])
    rejection_code = int(protocol_settings["modern_only_rejection_code"])
    path = str(protocol_settings["streamable_http_path"])
    host = str(transport_settings["default_host"])
    python = Path(
        os.environ.get("ABYSS_MCP_FLEET_PYTHON", sys.executable)
    ).expanduser()
    if not python.is_absolute():
        raise RuntimeError("ABYSS_MCP_FLEET_PYTHON must be an absolute path")
    workspace_root = args.workspace_root
    if workspace_root is None:
        configured_workspace = os.environ.get(workspace_env_var, "").strip()
        workspace_root = Path(configured_workspace).expanduser() if configured_workspace else None
    if workspace_root is None or not workspace_root.is_absolute():
        raise RuntimeError(
            f"--workspace-root or {workspace_env_var} is required for the source fleet matrix"
        )
    workspace_root = workspace_root.resolve()
    evidence_root_raw = os.environ.get("ABYSS_MCP_FLEET_EVIDENCE_ROOT", "").strip()
    evidence_root = (
        Path(evidence_root_raw).expanduser()
        if evidence_root_raw
        else Path.cwd() / "generated" / "modern-fleet"
    )
    active = {
        item.strip()
        for item in os.environ.get("ABYSS_MCP_ACTIVE_SERVICES", "").split(",")
        if item.strip()
    }
    observed_at = datetime.now(UTC)
    run_root = evidence_root / observed_at.strftime("modern-fleet-%Y%m%dT%H%M%SZ")
    run_root.mkdir(mode=0o700, parents=True)
    rows = []
    for service in sorted(catalog["services"], key=lambda item: item["service_id"]):
        contour = service.get("contours", {}).get("read")
        if not isinstance(contour, dict):
            raise RuntimeError(f"MCP service has no read contour: {service['service_id']}")
        organ = str(service["organ_id"])
        try:
            rows.append(
                _probe_server(
                    service,
                    contour,
            protocol=protocol,
            legacy_protocol=legacy_protocol,
            rejection_code=rejection_code,
            path=path,
                    host=host,
                    python=python,
                    workspace_root=workspace_root,
                    workspace_env_var=workspace_env_var,
                    transport=transport_settings,
                    active=organ in active,
                    canary_contract=canary_contracts[str(service["service_id"])],
                    limits=limits,
                )
            )
        except Exception as exc:
            rows.append(
                {
                    "name": organ,
                    "active_codex_organ": organ in active,
                    "verdict": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[-4000:],
                }
            )
    sdk_identity = runtime_identity(python, sdk_settings)
    receipt = {
        "schema_version": "abyss_modern_organ_fleet_matrix_v1",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "mcp_sdk": sdk_identity["versions"].get(sdk_settings["distribution"]),
        "mcp_companion_sdk": sdk_identity["versions"].get(
            sdk_settings["companion_distribution"]
        ),
        "runtime_identity": sdk_identity,
        "required_protocol": protocol,
        "active_count": sum(1 for row in rows if row["active_codex_organ"]),
        "package_count": len(rows),
        "semantic_probe_count": sum(
            1
            for row in rows
            if row.get("semantic_probe", {}).get("verdict") == "passed"
        ),
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
        and receipt["zero_legacy"]
        and all(row["verdict"] == "passed" for row in rows)
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
