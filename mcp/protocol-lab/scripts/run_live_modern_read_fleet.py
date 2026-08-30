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
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROTOCOL = "2026-07-28"
STACK = Path("/srv/AbyssOS/abyss-stack")
REGISTRY = Path("/srv/AbyssOS/.aoa/organ-access/organ-registry.v2.source.json")
MCP_SDK_SOURCE_REVISIONS = {
    "2.0.0": "6f69a3758ebf2ee55ce050f58b470ce11af71133",
    "2.1.1": "0921d94a74db900dccd2d534842aa7b6160542d2",
}
SERVERS = (
    ("abyss-stack", 5431, "abyss-stack-mcp-read.service", "abyss-stack-mcp-read-bearer-token"),
    ("abyss-machine", 5423, "aoa-organ-mcp-read@abyss-machine.service", "abyss-machine-mcp-read-bearer-token"),
    ("aoa-decisions", 5420, "aoa-organ-mcp-read@aoa-decisions.service", "aoa-decisions-mcp-read-bearer-token"),
    ("aoa-memo", 5421, "aoa-organ-mcp-read@aoa-memo.service", "aoa-memo-mcp-read-bearer-token"),
    ("aoa-session-memory", 5422, "aoa-organ-mcp-read@aoa-session-memory.service", "aoa-session-memory-mcp-read-bearer-token"),
    ("aoa-evals", 5424, "aoa-organ-mcp-read@aoa-evals.service", "aoa-evals-mcp-read-bearer-token"),
    ("aoa-kag", 5425, "aoa-organ-mcp-read@aoa-kag.service", "aoa-kag-mcp-read-bearer-token"),
    ("aoa-stats", 5430, "aoa-organ-mcp-read@aoa-stats.service", "aoa-stats-mcp-read-bearer-token"),
    ("aoa-4pda-connector", 5426, "aoa-organ-mcp-read@aoa-4pda-connector.service", "aoa-4pda-connector-mcp-read-bearer-token"),
    ("aoa-telegram-connector", 5427, "aoa-organ-mcp-read@aoa-telegram-connector.service", "aoa-telegram-connector-mcp-read-bearer-token"),
    ("aoa-discord-connector", 5428, "aoa-organ-mcp-read@aoa-discord-connector.service", "aoa-discord-connector-mcp-read-bearer-token"),
)


def _load_token(name: str) -> str:
    path = STACK / "Secrets/Configs" / name
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o777 != 0o600:
        raise RuntimeError(f"unsafe production credential: {name}")
    token = path.read_text(encoding="utf-8").strip()
    if not 43 <= len(token) <= 512:
        raise RuntimeError(f"invalid production credential: {name}")
    return token


def _meta() -> dict[str, Any]:
    return {
        "_meta": {
            "io.modelcontextprotocol/clientInfo": {
                "name": "abyss-live-modern-read-fleet",
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
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None, dict(response.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        payload = json.loads(raw) if raw.startswith(b"{") else None
        return exc.code, payload, dict(exc.headers)


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


def _registry_facts() -> dict[str, Any]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    rows = [
        contour
        for record in registry["records"]
        for contour in record["contours"]
        if contour["contour_id"] == "read" and contour["registry_state"] == "admitted"
    ]
    return {
        "registry_id": registry["registry_id"],
        "expires_at": registry["expires_at"],
        "admitted_read_count": len(rows),
        "protocol_versions": sorted(
            {version for row in rows for version in row["endpoint"]["protocol_versions"]}
        ),
        "bootstrap_identity_count": sum(
            "bootstrap" in row["runtime_identity"]["process_identity"] for row in rows
        ),
    }


def _probe(name: str, port: int, unit: str, credential: str) -> dict[str, Any]:
    token = _load_token(credential)
    url = f"http://127.0.0.1:{port}/mcp"
    before = _unit_identity(unit)
    sdk_before = _runtime_sdk_identity(before["python_executable"], unit)
    status, discover, headers = _request(url, token, "server/discover", _meta())
    result = discover.get("result") if isinstance(discover, dict) else None
    if status != 200 or not isinstance(result, dict):
        raise RuntimeError(f"{name} discovery failed: {status} {discover}")
    status, inventory, _ = _request(url, token, "tools/list", _meta())
    tools = inventory.get("result", {}).get("tools") if isinstance(inventory, dict) else None
    wrong_status, _, _ = _request(url, secrets.token_urlsafe(48), "server/discover", _meta())
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
        result.get("supportedVersions") == [PROTOCOL]
        and status == 200
        and isinstance(tools, list)
        and bool(tools)
        and wrong_status == 401
        and legacy_status == 400
        and isinstance(legacy_error, dict)
        and legacy_error.get("code") == -32022
        and legacy_headers.get("Mcp-Session-Id") is None
    )
    if not passed:
        raise RuntimeError(f"{name} modern-only gates failed")
    after = _unit_identity(unit)
    sdk_after = _runtime_sdk_identity(after["python_executable"], unit)
    if (
        after["process_identity"] != before["process_identity"]
        or after["python_executable"] != before["python_executable"]
        or after["python_executable_realpath"]
        != before["python_executable_realpath"]
        or sdk_after != sdk_before
    ):
        raise RuntimeError(
            f"{name} serving process or SDK identity changed during the probe"
        )
    encoded_tools = json.dumps(tools, sort_keys=True, separators=(",", ":")).encode()
    return {
        "organ_id": name,
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
            "method": "per_unit_process_interpreter_distribution_records",
            "checked_before_and_after_probe": True,
        },
        "protocol_version": PROTOCOL,
        "server_info": result.get("_meta", {}).get("io.modelcontextprotocol/serverInfo"),
        "tool_count": len(tools),
        "tool_schema_sha256": hashlib.sha256(encoded_tools).hexdigest(),
        "modern_response_header": headers.get("MCP-Protocol-Version"),
        "wrong_bearer_status": wrong_status,
        "legacy_status": legacy_status,
        "legacy_error_code": legacy_error["code"],
        "legacy_session_issued": False,
        "verdict": "passed",
    }


def _fleet_verdict(
    sdk: str,
    registry: dict[str, Any],
    rows: list[dict[str, Any]],
    zero_legacy: bool,
) -> str:
    """Accept one reviewed, measured SDK identity across every serving unit."""

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
        and isinstance(row.get("mcp_sdk"), str)
        and MCP_SDK_SOURCE_REVISIONS.get(row["mcp_sdk"])
        == row.get("mcp_sdk_source_revision")
        and isinstance(row.get("mcp_sdk_artifact_digest"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", row["mcp_sdk_artifact_digest"])
        is not None
        for row in rows
    )
    expected_identity = (
        (sdk, MCP_SDK_SOURCE_REVISIONS[sdk], next(iter(identities))[2])
        if sdk in MCP_SDK_SOURCE_REVISIONS and len(identities) == 1
        else None
    )
    return (
        "passed"
        if rows_are_objects
        and sdk in MCP_SDK_SOURCE_REVISIONS
        and registry["admitted_read_count"] == len(rows)
        and registry["protocol_versions"] == [PROTOCOL]
        and registry["bootstrap_identity_count"] == 0
        and len(identities) == 1
        and expected_identity in identities
        and per_unit_attestation
        and zero_legacy
        else "failed"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [_probe(*entry) for entry in SERVERS]
    registry = _registry_facts()
    if not rows:
        raise RuntimeError("the production read fleet is empty")
    sdk = rows[0]["mcp_sdk"]
    sdk_source_revision = rows[0]["mcp_sdk_source_revision"]
    sdk_artifact_digest = rows[0]["mcp_sdk_artifact_digest"]
    receipt = {
        "schema_version": "abyss_live_modern_read_fleet_v1",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "protocol_version": PROTOCOL,
        "mcp_sdk": sdk,
        "mcp_sdk_source_revision": sdk_source_revision,
        "mcp_sdk_artifact_digest": sdk_artifact_digest,
        "sdk_attestation": {
            "scope": "every production read unit",
            "method": "per_unit_process_interpreter_distribution_records",
            "unit_count": len(rows),
            "attested_unit_count": sum(
                row["sdk_attestation"]["state"] == "passed" for row in rows
            ),
            "unique_identities": len(
                {
                    (
                        row["mcp_sdk"],
                        row["mcp_sdk_source_revision"],
                        row["mcp_sdk_artifact_digest"],
                    )
                    for row in rows
                }
            ),
        },
        "production_unit_count": len(rows),
        "registry": registry,
        "servers": rows,
        "zero_legacy": all(
            row["legacy_status"] == 400
            and row["legacy_error_code"] == -32022
            and not row["legacy_session_issued"]
            for row in rows
        ),
    }
    receipt["verdict"] = _fleet_verdict(sdk, registry, rows, receipt["zero_legacy"])
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    os.chmod(args.output, 0o600)
    if receipt["verdict"] != "passed":
        raise RuntimeError(json.dumps(receipt, indent=2))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
