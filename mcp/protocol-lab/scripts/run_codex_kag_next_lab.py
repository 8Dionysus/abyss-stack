#!/usr/bin/env python3
"""Run one removable stable Codex -> KAG modern-MCP lab contour.

The runner creates an isolated CODEX_HOME, credential and loopback server,
calls the server through the Codex app-server API, then removes only the lab
registration and credential.  It never edits the operator's Codex config.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import secrets
import selectors
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

from aoa_kag_mcp.core import AoAKagMCPState
from aoa_kag_mcp.runtime import build_application
from run_kag_next_pair import (
    MAX_INPUT_BYTES,
    MAX_OUTPUT_BYTES,
    AccessRecorder,
    build_next_server,
)
from runtime_catalog import deployment_settings, load_runtime_catalog, mcp_settings


_RUNTIME_CATALOG = load_runtime_catalog()
_SDK_SETTINGS, _PROTOCOL_SETTINGS, _TRANSPORT_SETTINGS = mcp_settings(_RUNTIME_CATALOG)
WIRE_VERSION = str(_PROTOCOL_SETTINGS["version"])
MCP_PATH = str(_PROTOCOL_SETTINGS["streamable_http_path"])
MCP_HOST = str(_TRANSPORT_SETTINGS["default_host"])
REGISTRATION = "aoa_kag_next_lab"
FEATURE = str(deployment_settings(_RUNTIME_CATALOG)["codex_mcp_feature"])
TOKEN_ENV = "AOA_KAG_NEXT_LAB_BEARER_TOKEN"
CLIENT_ID = "https://os-abyss.invalid/codex-kag-next-lab.json"
ISSUER = "https://auth.os-abyss.invalid"
SUBJECT = "codex-kag-next-lab"
TRACEPARENT = "00-7d6f4bfe66cc42c7be4dfe186f08bd47-e0ad439d3c018890-01"
CODEX_VERSION = "codex-cli 0.147.0"
CODEX_SHA256 = "cb0a15567e9a60a5820d54b0f6ae86d504dc3805c1eab21a47f70e3eb7b73a40"
PYTHON_MCP_VERSION = str(_SDK_SETTINGS["tested_lock"])


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _git_head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file() and "__pycache__" not in item.parts):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _write_private(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    path.chmod(0o600)


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    _write_private(
        path,
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(),
    )


def _regular_private(path: Path) -> bool:
    return path.is_file() and not path.is_symlink() and (path.stat().st_mode & 0o777) == 0o600


def _port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.1)
        return probe.connect_ex((MCP_HOST, port)) == 0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((MCP_HOST, 0))
        return int(listener.getsockname()[1])


def _wait_port(port: int, expected_open: bool, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_is_open(port) is expected_open:
            return
        time.sleep(0.05)
    state = "open" if expected_open else "closed"
    raise RuntimeError(f"lab port {port} did not become {state}")


class LabTokenVerifier:
    def __init__(self, raw_token: str) -> None:
        self._raw_token = raw_token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not secrets.compare_digest(token, self._raw_token):
            return None
        return AccessToken(
            token=token,
            client_id=CLIENT_ID,
            scopes=["kag:read"],
            subject=SUBJECT,
            claims={"iss": ISSUER},
        )


class PersistentAccessRecorder(AccessRecorder):
    """Persist bounded observations during the run, before process teardown."""

    def __init__(self, path: Path, endpoint: str) -> None:
        super().__init__()
        self.path = path
        self.endpoint = endpoint
        self.started_at = _utc_now()

    def persist(self) -> None:
        _write_private_json(
            self.path,
            {
                "schema_version": "abyss_mcp_codex_kag_next_server_record_v1",
                "started_at": self.started_at,
                "updated_at": _utc_now(),
                "endpoint": self.endpoint,
                "pid": os.getpid(),
                "records": self.records,
                "secrets_included": False,
            },
        )

    async def __call__(self, ctx: Any, call_next: Any) -> Any:
        try:
            return await super().__call__(ctx, call_next)
        finally:
            self.persist()


def _serve(args: argparse.Namespace) -> int:
    raw_token = os.environ.get(TOKEN_ENV)
    if raw_token is None or len(raw_token) < 32:
        raise RuntimeError(f"{TOKEN_ENV} is missing or too short")
    url = f"http://{MCP_HOST}:{args.port}{MCP_PATH}"
    recorder = PersistentAccessRecorder(args.server_record, url)
    recorder.persist()
    state = AoAKagMCPState.discover(
        workspace_root=args.workspace_root,
        aoa_kag_root=args.aoa_kag_root,
    )
    application = build_application(state, stack_root=args.stack_runtime_root)
    server = build_next_server(
        application,
        recorder,
        token_verifier=LabTokenVerifier(raw_token),
        auth=AuthSettings(
            issuer_url=ISSUER,
            resource_server_url=url,
            required_scopes=["kag:read"],
        ),
    )
    app = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        json_response=False,
        stateless_http=True,
        host=MCP_HOST,
    )
    try:
        uvicorn.run(
            app,
            host=MCP_HOST,
            port=args.port,
            log_level="warning",
            access_log=False,
        )
    finally:
        recorder.persist()
    return 0


class AppServerRpc:
    def __init__(self, process: subprocess.Popen[bytes], secret: str) -> None:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise RuntimeError("Codex app-server pipes were not created")
        self.process = process
        self.stdin = process.stdin
        self.selector = selectors.DefaultSelector()
        self.selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        self.selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        self.buffers = {"stdout": b"", "stderr": b""}
        self.messages: list[dict[str, Any]] = []
        self.stderr: list[str] = []
        self.secret = secret

    def send(self, identifier: int, method: str, params: Any) -> None:
        payload = {"id": identifier, "method": method, "params": params}
        self.stdin.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
        self.stdin.flush()

    def notify(self, method: str, params: Any | None = None) -> None:
        payload: dict[str, Any] = {"method": method}
        if params is not None:
            payload["params"] = params
        self.stdin.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
        self.stdin.flush()

    def _consume(self, stream: str, data: bytes) -> None:
        buffer = self.buffers[stream] + data
        lines = buffer.split(b"\n")
        self.buffers[stream] = lines.pop()
        for raw in lines:
            text = raw.decode("utf-8", errors="replace")
            if self.secret in text:
                raise RuntimeError(f"secret appeared on Codex {stream}")
            if stream == "stderr":
                if text:
                    self.stderr.append(text)
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self.messages.append(message)

    def response(self, identifier: int, timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for message in self.messages:
                if message.get("id") == identifier:
                    if "error" in message:
                        raise RuntimeError(
                            f"Codex app-server request {identifier} failed: "
                            f"{json.dumps(message['error'], sort_keys=True)}"
                        )
                    return message
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"Codex app-server exited early with {self.process.returncode}"
                )
            for key, _ in self.selector.select(timeout=0.25):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    self.selector.unregister(key.fileobj)
                    continue
                self._consume(key.data, data)
        raise RuntimeError(f"timed out waiting for Codex app-server response {identifier}")


def _stop(process: subprocess.Popen[bytes], timeout: float = 10.0) -> int:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=5)


def _result(message: dict[str, Any]) -> dict[str, Any]:
    result = message.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Codex app-server response omitted an object result")
    return result


def _server_row(status: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("name") == REGISTRATION or value.get("server") == REGISTRATION:
                candidates.append(value)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(status)
    if not candidates:
        raise RuntimeError("Codex status did not include aoa_kag_next_lab")
    return max(candidates, key=lambda item: len(json.dumps(item, sort_keys=True)))


def _schema_inventory(row: dict[str, Any]) -> tuple[list[str], str]:
    tools: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("name"), str) and isinstance(
                value.get("inputSchema"), dict
            ):
                tools.append(value)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(row)
    unique = {item["name"]: item for item in tools}
    names = sorted(unique)
    if names != ["kag_discover"]:
        raise RuntimeError(f"unexpected Codex KAG lab tool inventory: {names}")
    canonical = json.dumps(unique, separators=(",", ":"), sort_keys=True).encode()
    return names, _sha256_bytes(canonical)


def _assert_call_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("isError") is True:
        raise RuntimeError("Codex reported the KAG lab tool call as an error")
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise RuntimeError("Codex KAG lab result omitted structuredContent")
    owners = structured.get("owners")
    if not isinstance(owners, list) or not owners or owners[0].get("repo") != "abyss-stack":
        raise RuntimeError("Codex KAG lab result crossed or omitted the requested owner")
    if structured.get("schema_version") != "aoa-kag-mcp-capabilities-v1":
        raise RuntimeError("Codex KAG lab result schema identity drifted")
    return structured


def _direct_modern_request(url: str, bearer: str, method: str, params: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        separators=(",", ":"),
    ).encode()
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
        "MCP-Method": method,
        "MCP-Protocol-Version": WIRE_VERSION,
    }
    if method == "tools/call" and isinstance(params.get("name"), str):
        headers["MCP-Name"] = params["name"]
    request = urllib.request.Request(
        url,
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read()
        parsed = json.loads(body) if body and body.startswith(b"{") else None
        return exc.code, parsed


def _run(args: argparse.Namespace) -> int:
    started_at = _utc_now()
    if args.port == 0:
        args.port = _free_port()
    binary = args.codex_binary.resolve()
    if _sha256(binary) != CODEX_SHA256:
        raise RuntimeError("isolated Codex binary digest drifted")
    observed_version = subprocess.run(
        [str(binary), "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if observed_version != CODEX_VERSION:
        raise RuntimeError(f"isolated Codex version drifted: {observed_version}")
    observed_python_mcp = importlib.metadata.version("mcp")
    if observed_python_mcp != PYTHON_MCP_VERSION:
        raise RuntimeError(f"Python MCP SDK drifted: {observed_python_mcp}")
    if _port_is_open(args.port):
        raise RuntimeError(f"dedicated lab port {args.port} is already in use")

    stable_before = _sha256(args.stable_codex_config)
    lab_root = args.lab_root.resolve()
    if lab_root.exists():
        shutil.rmtree(lab_root)
    (lab_root / "codex-home").mkdir(mode=0o700, parents=True)
    (lab_root / "proof").mkdir(mode=0o700)
    credential = lab_root / "credential"
    raw_token = secrets.token_urlsafe(48)
    _write_private(credential, (raw_token + "\n").encode())
    if not _regular_private(credential):
        raise RuntimeError("lab credential is not a readable regular non-symlink 0600 file")

    url = f"http://{MCP_HOST}:{args.port}{MCP_PATH}"
    config = (
        f"[mcp_servers.{REGISTRATION}]\n"
        f"url = {json.dumps(url)}\n"
        f"bearer_token_env_var = {json.dumps(TOKEN_ENV)}\n"
        "enabled_tools = [\"kag_discover\"]\n"
        "startup_timeout_sec = 20\n"
        "tool_timeout_sec = 30\n"
    ).encode()
    config_path = lab_root / "codex-home" / "config.toml"
    _write_private(config_path, config)
    server_record = lab_root / "proof" / "server-record.json"
    server_command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "serve",
        "--port",
        str(args.port),
        "--server-record",
        str(server_record),
        "--workspace-root",
        str(args.workspace_root),
        "--aoa-kag-root",
        str(args.aoa_kag_root),
        "--stack-runtime-root",
        str(args.stack_runtime_root),
    ]
    environment = dict(os.environ)
    environment[TOKEN_ENV] = raw_token
    environment["CODEX_HOME"] = str(lab_root / "codex-home")
    server_process = subprocess.Popen(
        server_command,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    app_process: subprocess.Popen[bytes] | None = None
    rpc: AppServerRpc | None = None
    app_returncode: int | None = None
    server_returncode: int | None = None
    rollback_port_closed = False
    try:
        _wait_port(args.port, True)
        wrong_bearer_status, _ = _direct_modern_request(
            url,
            secrets.token_urlsafe(48),
            "server/discover",
            {
                "_meta": {
                    "io.modelcontextprotocol/clientInfo": {"name": "denied-lab-probe", "version": "1.0.0"},
                    "io.modelcontextprotocol/clientCapabilities": {},
                    "io.modelcontextprotocol/protocolVersion": WIRE_VERSION,
                }
            },
        )
        if wrong_bearer_status != 401:
            raise RuntimeError(f"wrong bearer was not rejected with HTTP 401: {wrong_bearer_status}")
        app_command = [
            str(binary),
            "--enable",
            FEATURE,
            "app-server",
            "--strict-config",
        ]
        app_process = subprocess.Popen(
            app_command,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        rpc = AppServerRpc(app_process, raw_token)
        rpc.send(
            1,
            "initialize",
            {
                "clientInfo": {"name": "os-abyss-modern-mcp-lab", "version": "1.0.0"},
                "capabilities": {"experimentalApi": True},
            },
        )
        _result(rpc.response(1))
        rpc.notify("initialized")
        rpc.send(2, "thread/start", {"cwd": str(args.stack_source_root)})
        thread_result = _result(rpc.response(2))
        thread = thread_result.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise RuntimeError("Codex thread/start omitted thread.id")
        thread_id = thread["id"]
        rpc.send(
            3,
            "mcpServerStatus/list",
            {"detail": "full", "limit": 20, "threadId": thread_id},
        )
        status = _result(rpc.response(3))
        server_row = _server_row(status)
        tool_names, schema_digest = _schema_inventory(server_row)
        rpc.send(
            4,
            "mcpServer/tool/call",
            {
                "server": REGISTRATION,
                "threadId": thread_id,
                "tool": "kag_discover",
                "arguments": {"owner": "abyss-stack", "detail": "compact"},
                "_meta": {"traceparent": TRACEPARENT},
            },
        )
        call_result = _result(rpc.response(4))
        structured = _assert_call_result(call_result)
        oversized_status, oversized_result = _direct_modern_request(
            url,
            raw_token,
            "tools/call",
            {
                "name": "kag_discover",
                "arguments": {"owner": "x" * (MAX_INPUT_BYTES + 1), "detail": "compact"},
                "_meta": {
                    "io.modelcontextprotocol/clientInfo": {"name": "size-limit-probe", "version": "1.0.0"},
                    "io.modelcontextprotocol/clientCapabilities": {},
                    "io.modelcontextprotocol/protocolVersion": WIRE_VERSION,
                },
            },
        )
        oversized_error = oversized_result.get("error") if isinstance(oversized_result, dict) else None
        if oversized_status not in {200, 400} or not isinstance(oversized_error, dict) or oversized_error.get("code") != -32602:
            raise RuntimeError(
                "oversized KAG request was not denied at the MCP boundary: "
                f"status={oversized_status}, result={json.dumps(oversized_result, sort_keys=True)}"
            )
        safe_messages = rpc.messages
        safe_stderr = rpc.stderr
    finally:
        if app_process is not None:
            app_returncode = _stop(app_process)
        server_returncode = _stop(server_process)
        _wait_port(args.port, False)
        rollback_port_closed = True

    if not server_record.is_file():
        server_stderr = b""
        if server_process.stderr is not None:
            server_stderr = server_process.stderr.read()
        if raw_token.encode() in server_stderr:
            raise RuntimeError("secret appeared on KAG lab server stderr")
        raise RuntimeError(
            "KAG lab server did not write its record: "
            + server_stderr.decode(errors="replace")[-2000:]
        )
    record = json.loads(server_record.read_text())
    encoded_record = server_record.read_bytes()
    if raw_token.encode() in encoded_record:
        raise RuntimeError("secret appeared in KAG lab server record")
    modern = [item for item in record["records"] if item.get("protocol_version") == WIRE_VERSION]
    if not modern or any(item.get("session_header_present") for item in modern):
        raise RuntimeError("Codex modern wire was absent or session-bound")
    if any(item.get("protocol_header") != WIRE_VERSION for item in modern):
        raise RuntimeError("Codex modern wire protocol header drifted")
    if not any(item.get("method") == "server/discover" for item in modern):
        raise RuntimeError("Codex did not use server/discover")
    call_records = [item for item in modern if item.get("method") == "tools/call"]
    if len(call_records) != 1 or call_records[0].get("traceparent") != TRACEPARENT:
        raise RuntimeError("Codex tool-call trace context was not preserved")
    principal = call_records[0].get("authenticated_principal")
    if principal != {"client_id": CLIENT_ID, "issuer": ISSUER, "subject": SUBJECT}:
        raise RuntimeError("Codex bearer principal identity drifted")
    task_extension_advertised = any(
        isinstance(item.get("client_capability_extensions"), dict)
        and "io.modelcontextprotocol/tasks"
        in item["client_capability_extensions"]
        for item in modern
    )

    stable_after = _sha256(args.stable_codex_config)
    if stable_after != stable_before:
        raise RuntimeError("stable Codex config changed during isolated pilot")

    config_digest = _sha256(config_path)
    credential_digest = _sha256(credential)
    shutil.rmtree(lab_root / "codex-home")
    credential.unlink()
    registration_removed = not (lab_root / "codex-home").exists()
    credential_removed = not credential.exists()
    receipt = {
        "schema_version": "abyss_mcp_codex_kag_next_lab_observation_v1",
        "observation_id": "codex-0.147.0-stable-kag-next-lab-20260808",
        "observed_at": started_at,
        "finished_at": _utc_now(),
        "verdict": "isolated_stable_pair_passed",
        "consumer": {
            "version": observed_version,
            "sha256": CODEX_SHA256,
            "feature": FEATURE,
            "feature_default": False,
            "production_authority": False,
        },
        "server": {
            "registration": REGISTRATION,
            "endpoint": url,
            "process_pid": record["pid"],
            "python_mcp_version": observed_python_mcp,
            "source_revisions": {
                "abyss_stack": _git_head(args.stack_source_root),
                "aoa_kag": _git_head(args.aoa_kag_root),
            },
            "source_artifacts": {
                "driver_sha256": _sha256(Path(__file__).resolve()),
                "adapter_harness_sha256": _sha256(Path(__file__).with_name("run_kag_next_pair.py")),
                "adapter_package_tree_sha256": _tree_sha256(
                    Path(__file__).resolve().parents[2]
                    / "services"
                    / "aoa-kag-mcp"
                    / "src"
                    / "aoa_kag_mcp"
                ),
            },
            "config_sha256": config_digest,
            "credential_sha256": credential_digest,
            "credential_regular_non_symlink_0600": True,
        },
        "wire": {
            "version": WIRE_VERSION,
            "transport_response_mode": "sse_disconnect_cancellable",
            "server_discover_observed": True,
            "initialize_observed": any(item.get("method") == "initialize" for item in record["records"]),
            "mcp_session_id_observed": False,
            "self_describing_requests": sum(
                bool(item.get("has_client_info") and item.get("has_client_capabilities"))
                for item in modern
            ),
            "tasks_extension_advertised": task_extension_advertised,
            "authenticated_principal": principal,
            "trace_sent": TRACEPARENT,
            "trace_observed": call_records[0]["traceparent"],
            "tool_inventory": tool_names,
            "tool_schema_sha256": schema_digest,
            "tool_call": "kag_discover",
            "owner": structured["owners"][0]["repo"],
            "result_schema": structured["schema_version"],
            "request_bytes": len(json.dumps({"owner": "abyss-stack", "detail": "compact"}).encode()),
            "response_bytes": len(json.dumps(call_result, separators=(",", ":"), sort_keys=True).encode()),
            "input_limit_bytes": MAX_INPUT_BYTES,
            "output_limit_bytes": MAX_OUTPUT_BYTES,
            "oversized_input_denied_code": -32602,
            "oversized_input_http_status": oversized_status,
            "wrong_bearer_http_status": wrong_bearer_status,
        },
        "stable_registration": {
            "config_sha256_before": stable_before,
            "config_sha256_after": stable_after,
            "unchanged": True,
        },
        "rollback": {
            "app_process_stopped": app_returncode is not None,
            "server_process_stopped": server_returncode is not None,
            "port_closed": rollback_port_closed,
            "registration_removed": registration_removed,
            "credential_removed": credential_removed,
        },
        "private_evidence": {
            "server_record_ref": f"local://{server_record}",
            "server_record_sha256": _sha256(server_record),
            "app_message_count": len(safe_messages),
            "app_stderr_line_count": len(safe_stderr),
        },
        "secrets_included": False,
        "claim_limits": [
            "This proves one isolated stable Codex pair, not a production Codex cutover.",
            "Frozen official conformance and cancellation remain independently evidenced gates.",
            "Existing handle and cache receipts remain separate evidence for requestState and subscription semantics.",
            "The KAG result is navigation evidence and does not move owner authority.",
            "No candidate, effect, memory acceptance, proof verdict, source mutation, or production registration occurred.",
        ],
    }
    encoded = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    if raw_token.encode() in encoded:
        raise RuntimeError("secret appeared in normalized Codex KAG lab receipt")
    _write_private(args.output, encoded)
    print(f"[ok] wrote isolated Codex KAG next-lab receipt: {args.output}")
    return 0


def _stable_canary(args: argparse.Namespace) -> int:
    started_at = _utc_now()
    raw_token = os.environ.get("AOA_KAG_MCP_READ_BEARER_TOKEN")
    if raw_token is None or len(raw_token) < 32:
        raise RuntimeError("stable KAG bearer is unavailable in the caller environment")
    config_before = _sha256(args.stable_codex_config)
    binary = args.stable_codex_binary.resolve()
    version = subprocess.run(
        [str(binary), "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(args.stable_codex_config.resolve().parent)
    process = subprocess.Popen(
        [str(binary), "app-server", "--strict-config"],
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    rpc = AppServerRpc(process, raw_token)
    returncode: int | None = None
    try:
        rpc.send(
            1,
            "initialize",
            {
                "clientInfo": {"name": "os-abyss-stable-kag-post-rollback", "version": "1.0.0"},
                "capabilities": {"experimentalApi": True},
            },
        )
        _result(rpc.response(1))
        rpc.notify("initialized")
        rpc.send(
            2,
            "thread/start",
            {"cwd": str(args.workspace_root), "ephemeral": True},
        )
        thread_result = _result(rpc.response(2))
        thread = thread_result.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise RuntimeError("stable Codex thread/start omitted thread.id")
        thread_id = thread["id"]
        rpc.send(
            3,
            "mcpServerStatus/list",
            {"detail": "full", "limit": 30, "threadId": thread_id},
        )
        status = _result(rpc.response(3, timeout=45))
        stable_row: list[dict[str, Any]] = []

        def find_stable(value: Any) -> None:
            if isinstance(value, dict):
                if value.get("name") == "aoa_kag" or value.get("server") == "aoa_kag":
                    stable_row.append(value)
                for nested in value.values():
                    find_stable(nested)
            elif isinstance(value, list):
                for nested in value:
                    find_stable(nested)

        find_stable(status)
        if not stable_row:
            raise RuntimeError("production Codex inventory omitted aoa_kag")
        rpc.send(
            4,
            "mcpServer/tool/call",
            {
                "server": "aoa_kag",
                "threadId": thread_id,
                "tool": "kag_discover",
                "arguments": {"owner": "abyss-stack", "detail": "compact"},
            },
        )
        call_result = _result(rpc.response(4, timeout=45))
        structured = _assert_call_result(call_result)
    finally:
        returncode = _stop(process)
    config_after = _sha256(args.stable_codex_config)
    if config_after != config_before:
        raise RuntimeError("stable Codex config changed during post-rollback canary")
    receipt = {
        "schema_version": "abyss_mcp_stable_kag_post_rollback_observation_v1",
        "observation_id": "codex-0.147.0-stable-kag-post-rollback-20260808",
        "observed_at": started_at,
        "finished_at": _utc_now(),
        "verdict": "stable_production_route_passed_after_lab_rollback",
        "consumer": {
            "version": version,
            "binary_sha256": _sha256(binary),
            "registration": "aoa_kag",
            "actual_operator_config": True,
        },
        "canary": {
            "tool": "kag_discover",
            "owner": structured["owners"][0]["repo"],
            "result_schema": structured["schema_version"],
            "is_error": call_result.get("isError") is True,
        },
        "stable_registration": {
            "config_sha256_before": config_before,
            "config_sha256_after": config_after,
            "unchanged": True,
        },
        "process_stopped": returncode is not None,
        "app_message_count": len(rpc.messages),
        "app_stderr_line_count": len(rpc.stderr),
        "secrets_included": False,
        "claim_limits": [
            "This proves the existing stable registration remained callable after removal of the isolated lab contour.",
            "It does not prove modern MCP support in stable Codex or admit a production cutover.",
            "KAG output remains derived navigation evidence rather than owner truth.",
        ],
    }
    encoded = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    if raw_token.encode() in encoded:
        raise RuntimeError("secret appeared in stable KAG normalized receipt")
    _write_private(args.output, encoded)
    print(f"[ok] wrote stable KAG post-rollback receipt: {args.output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve")
    serve.add_argument("--port", required=True, type=int)
    serve.add_argument("--server-record", required=True, type=Path)
    serve.add_argument("--workspace-root", required=True, type=Path)
    serve.add_argument("--aoa-kag-root", required=True, type=Path)
    serve.add_argument("--stack-runtime-root", required=True, type=Path)

    run = subparsers.add_parser("run")
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--lab-root", required=True, type=Path)
    run.add_argument("--port", default=0, type=int)
    run.add_argument("--codex-binary", required=True, type=Path)
    run.add_argument("--workspace-root", required=True, type=Path)
    run.add_argument("--aoa-kag-root", required=True, type=Path)
    run.add_argument("--stack-runtime-root", required=True, type=Path)
    run.add_argument("--stack-source-root", required=True, type=Path)
    run.add_argument("--stable-codex-config", required=True, type=Path)
    stable = subparsers.add_parser("stable-canary")
    stable.add_argument("--output", required=True, type=Path)
    stable.add_argument("--stable-codex-binary", required=True, type=Path)
    stable.add_argument("--stable-codex-config", required=True, type=Path)
    stable.add_argument("--workspace-root", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "serve":
        return _serve(args)
    if args.command == "stable-canary":
        return _stable_canary(args)
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
