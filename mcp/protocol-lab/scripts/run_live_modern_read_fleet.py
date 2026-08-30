#!/usr/bin/env python3
"""Prove the admitted production read fleet on exact modern-only MCP wire."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from canary_contract import load_canary_contracts, verify_structured_result
from _mcp_sdk_identity import MCP_SDK_SOURCE_REVISIONS
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


EXPECTED_CANDIDATE_MCP_ARTIFACT_DIGESTS = frozenset(
    {
        "sha256:1ef71b1a3cfb3daba29b61d9f280896b35bdc1038474285cc8295071418b01e5",
        "sha256:a638c12e432fc0444d263a55db04668cd789437fde33951cc2be491021219601",
    }
)
RUNTIME_IDENTITY_HEADER = "x-abyss-mcp-runtime-identity"
RUNTIME_IDENTITY_ATTESTATION_METHOD = (
    "server_emitted_startup_runtime_identity_header"
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


def _endpoint_port(endpoint_ref: object) -> int | None:
    """Parse only a loopback HTTP endpoint into its TCP port."""
    if not isinstance(endpoint_ref, str):
        return None
    try:
        parsed = urllib.parse.urlparse(endpoint_ref)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        return None
    if port is None or not 1 <= port <= 65535:
        return None
    return port


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


def _response_header(headers: dict[str, str], name: str) -> str | None:
    lowered = name.lower()
    return next(
        (value for key, value in headers.items() if key.lower() == lowered),
        None,
    )


def _server_runtime_identity_attestation(
    headers: dict[str, str],
    before: dict[str, Any],
    sdk: dict[str, str],
    unit: str,
) -> dict[str, Any] | None:
    raw_identity = _response_header(headers, RUNTIME_IDENTITY_HEADER)
    if raw_identity is None:
        if sdk["version"] == "2.1.1":
            raise RuntimeError(
                f"candidate {unit} response omitted its serving-process SDK identity"
            )
        return None
    try:
        identity = json.loads(raw_identity)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"serving-process SDK identity header is invalid JSON for {unit}"
        ) from exc
    expected = {**sdk, "pid": before["main_pid"]}
    if identity != expected:
        raise RuntimeError(
            f"serving-process SDK identity header does not match {unit}"
        )
    if (
        sdk["version"] == "2.1.1"
        and sdk["artifact_digest"] not in EXPECTED_CANDIDATE_MCP_ARTIFACT_DIGESTS
    ):
        raise RuntimeError(f"candidate {unit} returned an unreviewed SDK artifact")
    return {
        "state": "passed",
        "method": RUNTIME_IDENTITY_ATTESTATION_METHOD,
        "header": "X-Abyss-MCP-Runtime-Identity",
        "pid": before["main_pid"],
        "checked_during_discovery": True,
    }


def _process_interpreter(pid: int, unit: str) -> dict[str, str]:
    """Resolve the interpreter actually serving the systemd main process."""

    try:
        argv = [
            item.decode("utf-8")
            for item in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            if item
        ]
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"cannot inspect the serving process for {unit}") from exc
    if len(argv) < 3 or argv[1:3] != ["-I", "-B"]:
        raise RuntimeError(
            f"serving process for {unit} is not an isolated Python process"
        )
    interpreter = Path(argv[0])
    if not interpreter.is_absolute() or not interpreter.is_file() or not os.access(
        interpreter,
        os.X_OK,
    ):
        raise RuntimeError(f"serving process for {unit} has no usable interpreter")
    try:
        resolved_interpreter = interpreter.resolve(strict=True)
        process_executable = Path(f"/proc/{pid}/exe").resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"cannot resolve the serving interpreter for {unit}") from exc
    if resolved_interpreter != process_executable:
        raise RuntimeError(
            f"serving process for {unit} changed its interpreter identity"
        )
    return {
        "python_executable": interpreter.as_posix(),
        "python_executable_realpath": resolved_interpreter.as_posix(),
    }


def _runtime_sdk_identity(interpreter: str, unit: str) -> dict[str, str]:
    """Measure SDK bytes through the interpreter belonging to one unit."""

    helper = Path(__file__).resolve().with_name("_mcp_sdk_identity.py")
    expression = (
        "import json, runpy; "
        f"namespace = runpy.run_path({helper.as_posix()!r}); "
        "print(json.dumps(namespace['installed_mcp_runtime_identity'](), sort_keys=True))"
    )
    completed = subprocess.run(
        [interpreter, "-I", "-B", "-c", expression],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-1200:]
        raise RuntimeError(f"SDK attestation failed for {unit}: {detail}")
    try:
        identity = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(f"SDK attestation returned invalid JSON for {unit}") from exc
    if not isinstance(identity, dict):
        raise RuntimeError(f"SDK attestation returned a non-object for {unit}")
    version = identity.get("version")
    source_revision = identity.get("commit")
    artifact_digest = identity.get("artifact_digest")
    if (
        not isinstance(version, str)
        or MCP_SDK_SOURCE_REVISIONS.get(version) != source_revision
        or not isinstance(artifact_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_digest) is None
        or not isinstance(identity.get("mcp_distribution_digest"), str)
        or re.fullmatch(
            r"sha256:[0-9a-f]{64}", identity["mcp_distribution_digest"]
        ) is None
        or not isinstance(identity.get("mcp_types_distribution_digest"), str)
        or re.fullmatch(
            r"sha256:[0-9a-f]{64}", identity["mcp_types_distribution_digest"]
        ) is None
    ):
        raise RuntimeError(f"SDK attestation was incomplete for {unit}")
    return {
        "version": version,
        "commit": source_revision,
        "artifact_digest": artifact_digest,
        "mcp_distribution_digest": identity["mcp_distribution_digest"],
        "mcp_types_distribution_digest": identity["mcp_types_distribution_digest"],
    }


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
        "main_pid": pid,
        "process_identity": (
            f"systemd-user:{unit}:pid:{pid}:start:"
            f"{values['ExecMainStartTimestampMonotonic']}"
        ),
        **_process_interpreter(pid, unit),
    }


def _listener_socket_inodes(port: int) -> set[str]:
    """Return every listening socket inode currently bound to ``port``."""
    inodes: set[str] = set()
    for proc_net in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            lines = proc_net.read_text(encoding="ascii").splitlines()[1:]
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(f"cannot inspect listening sockets in {proc_net}") from exc
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":
                continue
            try:
                local_port = int(fields[1].rsplit(":", 1)[1], 16)
            except (IndexError, ValueError) as exc:
                raise RuntimeError(f"invalid listening socket entry in {proc_net}") from exc
            if local_port == port and fields[9] != "0":
                inodes.add(fields[9])
    return inodes


def _process_socket_inodes(pid: int, unit: str) -> set[str]:
    inodes: set[str] = set()
    try:
        descriptors = Path(f"/proc/{pid}/fd").iterdir()
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            match = re.fullmatch(r"socket:\[(\d+)\]", target)
            if match is not None:
                inodes.add(match.group(1))
    except OSError as exc:
        raise RuntimeError(f"cannot inspect sockets owned by {unit}") from exc
    return inodes


def _listener_attestation(port: int, pid: int, unit: str) -> dict[str, Any]:
    """Prove that the loopback port is listened to by the named MainPID."""
    listening = _listener_socket_inodes(port)
    owned = listening & _process_socket_inodes(pid, unit)
    if not listening:
        raise RuntimeError(f"no listening socket was found for {unit}:{port}")
    if listening != owned:
        foreign = sorted(listening - owned)
        raise RuntimeError(
            f"{unit}:{port} is served by a socket outside MainPID {pid}: {foreign}"
        )
    return {
        "state": "passed",
        "method": "proc_net_tcp_listener_inode_owned_by_main_pid",
        "port": port,
        "pid": pid,
        "socket_inodes": sorted(owned),
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
    before = _unit_identity(unit)
    listener_before = _listener_attestation(port, before["main_pid"], unit)
    sdk_before = _runtime_sdk_identity(before["python_executable"], unit)
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
    runtime_identity_attestation = _server_runtime_identity_attestation(
        headers,
        before,
        sdk_before,
        unit,
    )
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
    after = _unit_identity(unit)
    listener_after = _listener_attestation(port, after["main_pid"], unit)
    sdk_after = _runtime_sdk_identity(after["python_executable"], unit)
    if (
        after["process_identity"] != before["process_identity"]
        or after["python_executable"] != before["python_executable"]
        or after["python_executable_realpath"]
        != before["python_executable_realpath"]
        or sdk_after != sdk_before
        or listener_after != listener_before
    ):
        raise RuntimeError(
            f"{organ} serving process or SDK identity changed during the probe"
        )
    encoded_tools = json.dumps(tools, sort_keys=True, separators=(",", ":")).encode()
    row = {
        "organ_id": organ,
        "endpoint_ref": url,
        **before,
        "mcp_sdk": sdk_before["version"],
        "mcp_sdk_source_revision": sdk_before["commit"],
        "mcp_sdk_artifact_digest": sdk_before["artifact_digest"],
        "mcp_sdk_distribution_digests": {
            "mcp": sdk_before["mcp_distribution_digest"],
            "mcp-types": sdk_before["mcp_types_distribution_digest"],
        },
        "sdk_attestation": {
            "state": "passed",
            "method": (
                "per_unit_process_interpreter_distribution_records_and_"
                "server_emitted_identity_header"
            ),
            "checked_before_and_after_probe": True,
        },
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
    if runtime_identity_attestation is not None:
        row["runtime_identity_attestation"] = runtime_identity_attestation
    row["listener_attestation"] = {
        **listener_before,
        "checked_before_and_after_probe": True,
    }
    return row


def _fleet_verdict(
    sdk: str,
    registry: dict[str, Any],
    rows: list[dict[str, Any]],
    zero_legacy: bool,
    *,
    protocol: str = "2026-07-28",
) -> str:
    """Accept one reviewed, measured SDK identity across every serving unit."""

    expected_source_revision = MCP_SDK_SOURCE_REVISIONS.get(sdk)
    identities: set[tuple[object, object, object]] = set()
    rows_are_objects = True
    for row in rows:
        if not isinstance(row, dict):
            rows_are_objects = False
            continue
        identities.add(
            (
                row.get("mcp_sdk"),
                row.get("mcp_sdk_source_revision"),
                row.get("mcp_sdk_artifact_digest"),
            )
        )
    per_unit_attestation = all(
        isinstance(row, dict)
        and isinstance(row.get("sdk_attestation"), dict)
        and row["sdk_attestation"].get("state") == "passed"
        and row.get("mcp_sdk") == sdk
        and row.get("mcp_sdk_source_revision") == expected_source_revision
        and isinstance(row.get("mcp_sdk_artifact_digest"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", row["mcp_sdk_artifact_digest"])
        is not None
        for row in rows
    )
    server_identity_attestation = all(
        row.get("mcp_sdk") != "2.1.1"
        or (
            isinstance(row.get("runtime_identity_attestation"), dict)
            and row["runtime_identity_attestation"].get("state") == "passed"
            and row["runtime_identity_attestation"].get("method")
            == RUNTIME_IDENTITY_ATTESTATION_METHOD
            and row["runtime_identity_attestation"].get("header")
            == "X-Abyss-MCP-Runtime-Identity"
            and row["runtime_identity_attestation"].get("pid")
            == row.get("main_pid")
            and row["runtime_identity_attestation"].get(
                "checked_during_discovery"
            )
            is True
        )
        for row in rows
    )
    listener_attestation = all(
        row.get("mcp_sdk") != "2.1.1"
        or (
            isinstance(row.get("listener_attestation"), dict)
            and row["listener_attestation"].get("state") == "passed"
            and row["listener_attestation"].get("method")
            == "proc_net_tcp_listener_inode_owned_by_main_pid"
            and row["listener_attestation"].get("port")
            == _endpoint_port(row.get("endpoint_ref"))
            and row["listener_attestation"].get("pid") == row.get("main_pid")
            and row["listener_attestation"].get("checked_before_and_after_probe")
            is True
        )
        for row in rows
    )
    reviewed_candidate_artifact = all(
        row.get("mcp_sdk") != "2.1.1"
        or row.get("mcp_sdk_artifact_digest")
        in EXPECTED_CANDIDATE_MCP_ARTIFACT_DIGESTS
        for row in rows
    )
    expected_identity = (
        (sdk, expected_source_revision, next(iter(identities))[2])
        if expected_source_revision is not None and len(identities) == 1
        else None
    )
    return (
        "passed"
        if rows_are_objects
        and bool(rows)
        and sdk in MCP_SDK_SOURCE_REVISIONS
        and registry["admitted_read_count"] == len(rows)
        and registry["protocol_versions"] == [protocol]
        and registry["bootstrap_identity_count"] == 0
        and len(identities) == 1
        and expected_identity in identities
        and per_unit_attestation
        and server_identity_attestation
        and listener_attestation
        and reviewed_candidate_artifact
        and all(row.get("verdict", "passed") == "passed" for row in rows)
        and zero_legacy
        else "failed"
    )


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
    identity_rows = [
        row
        for row in rows
        if isinstance(row.get("mcp_sdk"), str)
        and isinstance(row.get("mcp_sdk_source_revision"), str)
        and isinstance(row.get("mcp_sdk_artifact_digest"), str)
    ]
    first_identity = identity_rows[0] if identity_rows else {}
    receipt = {
        "schema_version": "abyss_live_modern_read_fleet_v1",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "protocol_version": protocol,
        "mcp_sdk": first_identity.get(
            "mcp_sdk",
            sdk_identity["versions"].get(sdk_settings["distribution"]),
        ),
        "mcp_sdk_source_revision": first_identity.get(
            "mcp_sdk_source_revision",
            sdk_settings["source_revision"],
        ),
        "mcp_sdk_artifact_digest": first_identity.get("mcp_sdk_artifact_digest"),
        "mcp_companion_sdk": sdk_identity["versions"].get(
            sdk_settings["companion_distribution"]
        ),
        "runtime_identity": sdk_identity,
        "sdk_attestation": {
            "scope": "every production read unit",
            "method": (
                "per_unit_process_interpreter_distribution_records_and_"
                "server_emitted_identity_header"
            ),
            "unit_count": len(rows),
            "attested_unit_count": sum(
                row.get("sdk_attestation", {}).get("state") == "passed"
                for row in rows
            ),
            "server_identity_attested_unit_count": sum(
                row.get("runtime_identity_attestation", {}).get("state") == "passed"
                for row in rows
            ),
            "listener_attested_unit_count": sum(
                row.get("listener_attestation", {}).get(
                    "checked_before_and_after_probe"
                )
                is True
                for row in rows
            ),
            "unique_identities": len(
                {
                    (
                        row.get("mcp_sdk"),
                        row.get("mcp_sdk_source_revision"),
                        row.get("mcp_sdk_artifact_digest"),
                    )
                    for row in identity_rows
                }
            ),
        },
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
        and _fleet_verdict(
            str(sdk_settings["tested_lock"]),
            registry,
            rows,
            receipt["zero_legacy"],
            protocol=protocol,
        )
        == "passed"
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
