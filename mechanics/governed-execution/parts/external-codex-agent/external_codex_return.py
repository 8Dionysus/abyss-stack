#!/usr/bin/env python3
"""Deliver one external-actor handoff and close its exact visible holder.

The return owner and transport endpoint are inputs to this module.  Codex's
local app-server is the only transport implemented here; owner meaning,
acceptance, and semantic continuation remain outside the runtime.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import secrets
import socket
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Sequence


SCHEMA_VERSION = "abyss_stack_external_codex_return_v1"
RETURN_OWNER_SCHEMA_VERSION = "abyss_stack_external_codex_return_owner_v1"
LEGACY_RETURN_OWNER_SCHEMA_VERSION = "task_local_external_actor_return_owner_v1"
RETURN_RECEIPT_SCHEMA_VERSION = "abyss_stack_external_codex_return_receipt_v1"
RETURN_RESPONSE_SCHEMA_VERSION = "abyss_stack_external_codex_return_response_v1"
DETACHED_SCHEMA_VERSION = "abyss_stack_external_codex_return_detached_v1"
WEBSOCKET_ACCEPT_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_HANDSHAKE_BYTES = 64 * 1024
MAX_FRAME_BYTES = 16 * 1024 * 1024


class ExternalCodexReturnError(RuntimeError):
    """A fail-closed return validation or delivery error."""


def _visible_module() -> Any:
    """Load the sibling visible lifecycle module in source and installed forms."""

    try:
        return sys.modules["visible_incarnation_home"]
    except KeyError:
        pass
    path = Path(__file__).with_name("visible_incarnation_home.py")
    spec = importlib.util.spec_from_file_location("visible_incarnation_home", path)
    if spec is None or spec.loader is None:
        raise ExternalCodexReturnError("cannot load visible lifecycle module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VISIBLE = _visible_module()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _regular_file(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ExternalCodexReturnError(
            f"{label} must be an absolute regular non-symlink file: {path}"
        )
    return path


def _load_json_file(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    path = _regular_file(path, label)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalCodexReturnError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ExternalCodexReturnError(f"{label} must be a JSON object: {path}")
    return value, raw


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(
        character in value for character in "\x00\r\n"
    ):
        raise ExternalCodexReturnError(f"{label} must be a non-empty safe string")
    return value


def _owner_projection(owner: dict[str, Any]) -> dict[str, str]:
    return {
        key: _nonempty_string(owner.get(key), f"return owner {key}")
        for key in (
            "owner_id",
            "owner_repo",
            "goal_id",
            "thread_id",
            "runtime",
            "transport_posture",
            "acceptance_posture",
        )
    }


def _transport_endpoint_candidates(owner: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("transport_endpoint", "app_server_socket"):
        value = owner.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value)
    transport = owner.get("transport")
    if isinstance(transport, dict):
        for key in ("endpoint", "socket", "address"):
            value = transport.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value)
    return candidates


def _canonical_transport_binding(owner: dict[str, Any]) -> dict[str, object]:
    """Collapse every accepted endpoint spelling to the effective binding."""

    candidates = _transport_endpoint_candidates(owner)
    if len(set(candidates)) > 1:
        raise ExternalCodexReturnError(
            "return owner transport endpoint aliases do not agree"
        )
    return {
        "posture": _nonempty_string(
            owner.get("transport_posture"), "return owner transport_posture"
        ),
        "endpoint": candidates[0] if candidates else None,
    }


def _owner_binding_projection(owner: dict[str, Any]) -> dict[str, object]:
    """Project identity plus the complete canonical transport binding."""

    return {
        "identity": _owner_projection(owner),
        "transport": _canonical_transport_binding(owner),
    }


def validate_return_owner(owner: dict[str, Any]) -> dict[str, Any]:
    """Validate owner binding data without selecting any owner identity."""

    schema = owner.get("schema_version")
    if schema not in {RETURN_OWNER_SCHEMA_VERSION, LEGACY_RETURN_OWNER_SCHEMA_VERSION}:
        raise ExternalCodexReturnError("unsupported return-owner schema")
    projected = _owner_projection(owner)
    if projected["runtime"] != "codex":
        raise ExternalCodexReturnError("this return transport requires runtime=codex")
    if "transport_endpoint" in owner:
        _nonempty_string(owner["transport_endpoint"], "return owner transport_endpoint")
    if "app_server_socket" in owner:
        _nonempty_string(owner["app_server_socket"], "return owner app_server_socket")
    transport = owner.get("transport")
    if transport is not None:
        if not isinstance(transport, dict):
            raise ExternalCodexReturnError("return owner transport must be an object")
        for key in ("endpoint", "socket", "address"):
            if key in transport:
                _nonempty_string(transport[key], f"return owner transport.{key}")
    _canonical_transport_binding({**owner, **projected})
    return {**owner, **projected}


def _endpoint_from_owner(owner: dict[str, Any]) -> str | None:
    candidates = _transport_endpoint_candidates(owner)
    return candidates[0] if candidates else None


def _socket_path(value: str) -> Path:
    candidate = value.removeprefix("unix:")
    path = Path(candidate)
    if not path.is_absolute() or path.is_symlink():
        raise ExternalCodexReturnError(
            "Codex app-server endpoint must be an absolute non-symlink UNIX socket"
        )
    return path


def discover_app_server_socket(owner: dict[str, Any]) -> tuple[Path, str]:
    """Resolve the current local Codex endpoint without embedding a task path."""

    explicit = _endpoint_from_owner(owner)
    if explicit is not None:
        path = _socket_path(explicit)
        if not path.is_socket():
            raise ExternalCodexReturnError(f"app-server endpoint is not a socket: {path}")
        return path, "owner_binding"

    if owner["transport_posture"] != "resolve-current-local-codex-app-server":
        raise ExternalCodexReturnError(
            "return owner lacks an explicit endpoint or supported discovery posture"
        )
    candidates: list[Path] = []
    for environment_key in ("AOA_CODEX_APP_SERVER_SOCKET", "CODEX_APP_SERVER_SOCKET"):
        value = os.environ.get(environment_key)
        if value:
            candidates.append(_socket_path(value))
    for environment_key in ("AOA_CODEX_HOME", "CODEX_HOME"):
        value = os.environ.get(environment_key)
        if value:
            candidates.append(Path(value) / "app-server-control/app-server-control.sock")
            candidates.append(Path(value) / ".codex/app-server-control/app-server-control.sock")
    candidates.append(Path.home() / ".codex/app-server-control/app-server-control.sock")
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.is_absolute() and not path.is_symlink() and path.is_socket():
            return path, "current_local_codex_app_server"
    rendered = ", ".join(str(path) for path in candidates)
    raise ExternalCodexReturnError(
        f"current local Codex app-server socket was not found ({rendered})"
    )


def _string_at(value: object, keys: tuple[str, ...]) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _safe_response_summary(value: object) -> dict[str, object]:
    """Keep delivery proof useful without copying arbitrary server text."""

    if not isinstance(value, dict):
        return {"kind": type(value).__name__}
    summary: dict[str, object] = {"keys": sorted(str(key) for key in value)}
    for output_key, source_keys in {
        "id": ("id", "turnId", "threadId"),
        "status": ("status",),
        "turn_id": ("turnId", "id"),
    }.items():
        candidate = _string_at(value, source_keys)
        if candidate is not None:
            summary[output_key] = candidate
    for nested_key in ("goal", "turn"):
        nested = value.get(nested_key)
        if isinstance(nested, dict):
            nested_summary = _safe_response_summary(nested)
            summary[nested_key] = nested_summary
    return summary


class UnixWebSocketRpc:
    """Small stdlib-only JSON-RPC WebSocket client for the local app-server."""

    def __init__(self, path: Path, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.path = path
        self.timeout = timeout
        self.socket: socket.socket | None = None
        self._buffer = b""
        self._counter = 0

    def __enter__(self) -> "UnixWebSocketRpc":
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        try:
            connection.connect(str(self.path))
            self.socket = connection
            self._handshake()
        except (OSError, TimeoutError) as exc:
            connection.close()
            raise ExternalCodexReturnError("cannot connect to Codex app-server") from exc
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        try:
            if self.socket is not None:
                try:
                    self._send_frame(0x8, b"")
                except (OSError, ExternalCodexReturnError):
                    pass
                self.socket.close()
        finally:
            self.socket = None

    def _require_socket(self) -> socket.socket:
        if self.socket is None:
            raise ExternalCodexReturnError("app-server socket is not connected")
        return self.socket

    def _read_exact(self, size: int) -> bytes:
        if size < 0 or size > MAX_FRAME_BYTES:
            raise ExternalCodexReturnError("app-server frame length is invalid")
        chunks: list[bytes] = []
        remaining = size
        if self._buffer:
            buffered = self._buffer[:remaining]
            self._buffer = self._buffer[len(buffered) :]
            chunks.append(buffered)
            remaining -= len(buffered)
        connection = self._require_socket()
        while remaining:
            chunk = connection.recv(remaining)
            if not chunk:
                raise ExternalCodexReturnError("Codex app-server closed the socket")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _read_until(self, marker: bytes) -> bytes:
        connection = self._require_socket()
        while marker not in self._buffer:
            chunk = connection.recv(4096)
            if not chunk:
                raise ExternalCodexReturnError("Codex app-server closed during handshake")
            self._buffer += chunk
            if len(self._buffer) > MAX_HANDSHAKE_BYTES:
                raise ExternalCodexReturnError("Codex app-server handshake is too large")
        position = self._buffer.index(marker) + len(marker)
        result, self._buffer = self._buffer[:position], self._buffer[position:]
        return result

    def _handshake(self) -> None:
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            "GET /rpc HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        connection = self._require_socket()
        connection.sendall(request)
        raw = self._read_until(b"\r\n\r\n")
        lines = raw.decode("latin1").split("\r\n")
        if not lines or not lines[0].startswith("HTTP/1.1 101"):
            raise ExternalCodexReturnError("Codex app-server did not accept WebSocket upgrade")
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                headers[name.strip().lower()] = value.strip()
        expected = base64.b64encode(
            hashlib.sha1((key + WEBSOCKET_ACCEPT_GUID).encode("ascii")).digest()
        ).decode("ascii")
        if headers.get("sec-websocket-accept") != expected:
            raise ExternalCodexReturnError("Codex app-server WebSocket accept digest mismatched")

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        connection = self._require_socket()
        if len(payload) > MAX_FRAME_BYTES:
            raise ExternalCodexReturnError("app-server payload is too large")
        mask = secrets.token_bytes(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        length = len(masked)
        if length < 126:
            header = bytes((0x80 | opcode, 0x80 | length))
        elif length <= 0xFFFF:
            header = bytes((0x80 | opcode, 0x80 | 126)) + struct.pack(">H", length)
        else:
            header = bytes((0x80 | opcode, 0x80 | 127)) + struct.pack(">Q", length)
        connection.sendall(header + mask + masked)

    def _send_json(self, value: dict[str, object]) -> None:
        self._send_frame(0x1, json.dumps(value, separators=(",", ":")).encode("utf-8"))

    def _recv_frame(self) -> tuple[bool, int, bytes]:
        first, second = self._read_exact(2)
        final = bool(first & 0x80)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read_exact(8))[0]
        if length > MAX_FRAME_BYTES:
            raise ExternalCodexReturnError("app-server frame is too large")
        payload = self._read_exact(length)
        if second & 0x80:
            mask = self._read_exact(4)
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return final, opcode, payload

    def _receive_json(self, request_id: int) -> dict[str, Any]:
        fragments: list[bytes] = []
        opcode_expected: int | None = None
        while True:
            final, opcode, payload = self._recv_frame()
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0x8:
                raise ExternalCodexReturnError("Codex app-server closed during delivery")
            if opcode in {0x1, 0x2}:
                if fragments:
                    raise ExternalCodexReturnError("interleaved app-server WebSocket message")
                opcode_expected = opcode
                fragments.append(payload)
            elif opcode == 0x0:
                if not fragments:
                    raise ExternalCodexReturnError("orphaned app-server WebSocket continuation")
                fragments.append(payload)
            else:
                continue
            # The server normally sends one unfragmented text frame.  A
            # continuation is only complete when FIN is known, so inspect the
            # frame header through the helper below for the common path.
            if not final:
                continue
            if opcode_expected != 0x1:
                raise ExternalCodexReturnError(
                    "Codex app-server returned a non-text response"
                )
            if opcode_expected == 0x1:
                try:
                    value = json.loads(b"".join(fragments).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    # A fragmented frame is handled by the explicit helper
                    # path; malformed JSON remains fail closed.
                    raise ExternalCodexReturnError("app-server text response is not JSON")
                if not isinstance(value, dict):
                    raise ExternalCodexReturnError("app-server response is not an object")
                # A bidirectional app-server may issue a request while this
                # client is waiting for a response.  Classify that request
                # before matching ids: JSON-RPC request ids are not reserved
                # against a server-side collision with our counter.
                if isinstance(value.get("method"), str):
                    self._handle_unrelated_message(value)
                elif value.get("id") == request_id:
                    return value
                else:
                    self._handle_unrelated_message(value)
                fragments.clear()
                opcode_expected = None

    def _handle_unrelated_message(self, value: dict[str, Any]) -> None:
        if "id" in value and isinstance(value.get("method"), str):
            self._send_json(
                {
                    "jsonrpc": "2.0",
                    "id": value["id"],
                    "error": {
                        "code": -32601,
                        "message": "return client does not handle server requests",
                    },
                }
            )

    def notify(self, method: str, params: dict[str, object] | None = None) -> None:
        payload: dict[str, object] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._send_json(payload)

    def call(self, method: str, params: dict[str, object] | None = None) -> dict[str, Any]:
        self._counter += 1
        request_id = self._counter
        payload: dict[str, object] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send_json(payload)
        response = self._receive_json(request_id)
        if "error" in response:
            raise ExternalCodexReturnError(
                f"Codex app-server {method} failed: {json.dumps(response['error'], sort_keys=True)}"
            )
        if "result" not in response:
            raise ExternalCodexReturnError(
                f"Codex app-server {method} response is missing result"
            )
        result = response["result"]
        if not isinstance(result, dict):
            raise ExternalCodexReturnError(f"Codex app-server {method} returned a non-object result")
        return result


def _active_turn_id(turns: object) -> str | None:
    if isinstance(turns, dict):
        turns = turns.get("data") or turns.get("turns")
    if not isinstance(turns, list):
        return None
    for turn in reversed(turns):
        if not isinstance(turn, dict):
            continue
        status = turn.get("status")
        if status in {"inProgress", "in_progress", "running"}:
            candidate = turn.get("id")
            if isinstance(candidate, str) and candidate:
                return candidate
    return None


def _goal_object(response: dict[str, Any], method: str) -> dict[str, Any]:
    goal = response.get("goal")
    if not isinstance(goal, dict):
        raise ExternalCodexReturnError(f"Codex app-server {method} did not return a Goal")
    return goal


def _validate_goal_binding(goal: dict[str, Any], owner: dict[str, Any]) -> str:
    if goal.get("threadId") != owner["thread_id"]:
        raise ExternalCodexReturnError(
            "Codex app-server Goal is bound to a different thread"
        )
    observed_goal_id = _string_at(goal, ("goalId", "goal_id"))
    if observed_goal_id is not None:
        if observed_goal_id != owner["goal_id"]:
            raise ExternalCodexReturnError(
                "Codex app-server Goal identity does not match owner binding"
            )
        return "app_server_goal_id"
    # Codex's ThreadGoal protocol identifies a Goal by its bound thread and
    # does not expose a separate goal id.  The supplied owner artifact is the
    # authoritative goal_id -> thread_id mapping in that protocol contour.
    return "owner_goal_to_thread_binding"


def _thread_object(response: dict[str, Any], method: str) -> dict[str, Any]:
    thread = response.get("thread")
    if not isinstance(thread, dict):
        raise ExternalCodexReturnError(f"Codex app-server {method} did not return a Thread")
    return thread


def _validate_turn_delivery(method: str, response: dict[str, Any]) -> dict[str, str]:
    """Require the method-specific protocol evidence for the accepted turn."""

    if method == "turn/start":
        turn = response.get("turn")
        if not isinstance(turn, dict):
            raise ExternalCodexReturnError(
                "Codex app-server turn/start did not return a Turn"
            )
        turn_id = _string_at(turn, ("id",))
        status = turn.get("status")
        if turn_id is None or status not in {"completed", "inProgress"}:
            raise ExternalCodexReturnError(
                "Codex app-server turn/start did not prove an accepted Turn"
            )
        return {"turn_id": turn_id, "status": str(status)}
    if method == "turn/steer":
        turn_id = _string_at(response, ("turnId",))
        if turn_id is None:
            raise ExternalCodexReturnError(
                "Codex app-server turn/steer did not return turnId"
            )
        return {"turn_id": turn_id}
    raise ExternalCodexReturnError(f"unsupported delivery method: {method}")


def deliver_handoff(
    owner: dict[str, Any],
    owner_path: Path,
    handoff_path: Path,
    endpoint: Path,
    *,
    owner_bytes: bytes | None = None,
    handoff_bytes: bytes | None = None,
    rpc_factory: Callable[[Path], Any] = UnixWebSocketRpc,
) -> dict[str, Any]:
    """Deliver one immutable handoff to an active or paused Goal/session."""

    handoff_path = _regular_file(handoff_path, "handoff")
    if owner_bytes is None:
        owner_bytes = owner_path.read_bytes()
    if handoff_bytes is None:
        handoff_bytes = handoff_path.read_bytes()
    handoff_digest = _sha256_bytes(handoff_bytes)
    message = (
        f"External actor return ready: {handoff_path} "
        f"(handoff_sha256={handoff_digest}). Review this exact handoff, filter its claims, "
        "and continue the current Goal."
    )
    client_message_id = f"external-actor-return-{handoff_digest.removeprefix('sha256:')[:16]}"
    with rpc_factory(endpoint) as rpc:
        initialize = rpc.call(
            "initialize",
            {
                "clientInfo": {
                    "name": "abyss_stack_external_codex_return",
                    "title": "Abyss external Codex return",
                    "version": "1",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        rpc.notify("initialized")
        goal_get_response = rpc.call(
            "thread/goal/get",
            {"threadId": owner["thread_id"]},
        )
        goal_before = _goal_object(goal_get_response, "thread/goal/get")
        goal_identity_source = _validate_goal_binding(goal_before, owner)
        goal_before_status = _string_at(goal_before, ("status",))
        if goal_before_status == "active":
            goal_response = goal_get_response
            goal = goal_before
            goal_activation = "already_active"
        elif goal_before_status == "paused":
            goal_response = rpc.call(
                "thread/goal/set",
                {"threadId": owner["thread_id"], "status": "active"},
            )
            goal = _goal_object(goal_response, "thread/goal/set")
            goal_identity_source = _validate_goal_binding(goal, owner)
            goal_activation = "paused_to_active"
        else:
            raise ExternalCodexReturnError(
                "Codex app-server Goal is not wakeable: "
                f"{goal_before_status!r}"
            )
        goal_status = _string_at(goal, ("status",))
        if goal_status != "active":
            raise ExternalCodexReturnError(
                f"Codex app-server did not confirm an active Goal: {goal_status!r}"
            )
        thread_read_response = rpc.call(
            "thread/read",
            {
                "threadId": owner["thread_id"],
                "includeTurns": True,
            },
        )
        thread = _thread_object(thread_read_response, "thread/read")
        if thread.get("id") != owner["thread_id"]:
            raise ExternalCodexReturnError(
                "Codex app-server Thread identity does not match owner binding"
            )
        turns = thread.get("turns")
        active_turn = _active_turn_id(turns)
        input_value = [{"type": "text", "text": message}]
        if active_turn is not None:
            method = "turn/steer"
            turn_response = rpc.call(
                method,
                {
                    "threadId": owner["thread_id"],
                    "expectedTurnId": active_turn,
                    "clientUserMessageId": client_message_id,
                    "input": input_value,
                },
            )
        else:
            method = "turn/start"
            turn_response = rpc.call(
                method,
                {
                    "threadId": owner["thread_id"],
                    "clientUserMessageId": client_message_id,
                    "input": input_value,
                },
            )
        turn_delivery = _validate_turn_delivery(method, turn_response)
    return {
        "schema_version": RETURN_RECEIPT_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "owner_ref": str(owner_path.resolve()),
        "owner_sha256": _sha256_bytes(owner_bytes),
        "owner": _owner_projection(owner),
        "transport": {
            "kind": "codex_app_server_websocket_unix",
            "endpoint": str(endpoint),
        },
        "handoff_ref": str(handoff_path.resolve()),
        "handoff_sha256": handoff_digest,
        "goal_status": goal_status,
        "goal_binding": {
            "goal_id": owner["goal_id"],
            "thread_id": owner["thread_id"],
            "before_status": goal_before_status,
            "activation": goal_activation,
            "identity_source": goal_identity_source,
        },
        "delivery_method": method,
        "client_user_message_id": client_message_id,
        "active_turn_id": active_turn,
        "delivery": {
            "accepted": True,
            "initialize": _safe_response_summary(initialize),
            "goal_get": _safe_response_summary(goal_get_response),
            "goal": _safe_response_summary(goal_response),
            "thread_read": _safe_response_summary(thread_read_response),
            "turns": _safe_response_summary(turns),
            "turn": _safe_response_summary(turn_response),
            "goal_response_sha256": _sha256_bytes(_canonical_bytes(goal_response)),
            "turn_response_sha256": _sha256_bytes(_canonical_bytes(turn_response)),
            "accepted_turn": turn_delivery,
        },
        "actions": {"handoff_message_sent": True},
        "observed": {"handoff_delivery": True, "goal_status": "active"},
        "delivered": True,
        "owner_acceptance": "separate",
    }


def _write_new_json(path: Path, value: dict[str, Any], label: str) -> None:
    try:
        VISIBLE._write_new_json(path, value, label)
    except Exception as exc:
        raise ExternalCodexReturnError(str(exc)) from exc


def _validate_output_path(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise ExternalCodexReturnError(
            f"{label} must be an absolute non-symlink output path: {path}"
        )
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ExternalCodexReturnError(
            f"{label} parent must be a real directory: {path.parent}"
        )
    if path.exists() and not path.is_file():
        raise ExternalCodexReturnError(
            f"{label} must be a regular file or an unused path: {path}"
        )
    return path


@contextlib.contextmanager
def _detached_retry_lock(path: Path) -> Any:
    """Serialize stale-retry reservation and child launch for one receipt chain."""

    _validate_output_path(path, "detached return receipt")
    lock_path = path.with_name(path.name + ".lock")
    if lock_path.is_symlink():
        raise ExternalCodexReturnError(
            f"detached return retry lock may not be a symlink: {lock_path}"
        )
    lock_fd: int | None = None
    try:
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        lock_fd = os.open(lock_path, flags, 0o600)
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    except OSError as exc:
        if lock_fd is not None:
            os.close(lock_fd)
        raise ExternalCodexReturnError(
            f"cannot acquire detached return retry lock: {lock_path}"
        ) from exc
    try:
        yield lock_fd
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)


def _validate_distinct_output_paths(paths: Sequence[tuple[Path, str]]) -> None:
    seen: dict[Path, str] = {}
    for path, label in paths:
        identity = path.resolve()
        previous = seen.get(identity)
        if previous is not None:
            raise ExternalCodexReturnError(
                f"{label} aliases {previous}; lifecycle output paths must be distinct"
            )
        seen[identity] = label


def _return_binding(
    *,
    owner_path: Path,
    owner_digest: str,
    handoff_path: Path,
    handoff_digest: str,
    holder_path: Path,
    holder_digest: str,
    authorization_path: Path,
    closure_path: Path,
    return_path: Path,
) -> dict[str, str]:
    return {
        "owner_ref": str(owner_path.resolve()),
        "owner_sha256": owner_digest,
        "handoff_ref": str(handoff_path.resolve()),
        "handoff_sha256": handoff_digest,
        "holder_receipt_ref": str(holder_path.resolve()),
        "holder_receipt_sha256": holder_digest,
        "authorization_ref": str(authorization_path.resolve()),
        "closure_receipt_ref": str(closure_path.resolve()),
        "return_receipt_ref": str(return_path.resolve()),
    }


def _return_reservation(
    path: Path,
    *,
    binding: dict[str, str],
) -> dict[str, Any]:
    if path.exists():
        value, raw = _load_json_file(path, "canonical return receipt reservation")
        if raw != _canonical_bytes(value) + b"\n":
            raise ExternalCodexReturnError(
                "canonical return receipt reservation is not canonically encoded"
            )
        if value.get("schema_version") != RETURN_RECEIPT_SCHEMA_VERSION:
            raise ExternalCodexReturnError("canonical return receipt reservation schema mismatch")
        if value.get("state") != "reserved":
            raise ExternalCodexReturnError(
                "canonical return receipt exists but is not a completed receipt"
            )
        for key, expected in binding.items():
            if value.get(key) != expected:
                raise ExternalCodexReturnError(
                    f"canonical return receipt reservation {key} mismatch"
                )
        return value
    reservation = {
        "schema_version": RETURN_RECEIPT_SCHEMA_VERSION,
        "state": "reserved",
        "reserved_at": _utc_now(),
        **binding,
    }
    _write_new_json(path, reservation, "canonical return receipt reservation")
    return reservation


def _load_return_inputs(args: argparse.Namespace) -> dict[str, Any]:
    owner_path = _regular_file(Path(args.return_owner), "return owner")
    owner_value, owner_bytes = _load_json_file(owner_path, "return owner")
    owner_digest = _sha256_bytes(owner_bytes)
    owner = validate_return_owner(owner_value)
    handoff_path = _regular_file(Path(args.handoff), "handoff")
    holder_path = _regular_file(Path(args.holder_receipt), "holder receipt")
    closure_path = _validate_output_path(Path(args.closure_receipt), "closure receipt")
    handoff, handoff_bytes, handoff_digest, holder, holder_bytes, holder_digest = (
        _load_handoff_context(handoff_path, holder_path, closure_path)
    )
    _validate_handoff_owner(handoff, owner)
    authorization_path = _validate_output_path(
        Path(args.authorization), "terminal closure authorization"
    )
    return_path = _validate_output_path(
        Path(args.return_receipt), "canonical return receipt"
    )
    _validate_distinct_output_paths(
        [
            (authorization_path, "terminal closure authorization"),
            (closure_path, "closure receipt"),
            (return_path, "canonical return receipt"),
        ]
    )
    authorization: dict[str, Any] | None = None
    if authorization_path.exists():
        authorization = _load_existing_authorization(
            authorization_path,
            handoff_path=handoff_path,
            holder_path=holder_path,
            closure_path=closure_path,
            holder=holder,
            holder_bytes=holder_bytes,
            holder_digest=holder_digest,
            handoff_snapshot=(handoff, handoff_bytes, handoff_digest),
        )
    elif closure_path.exists():
        raise ExternalCodexReturnError(
            "closure receipt exists without its terminal closure authorization"
        )
    if authorization is not None and closure_path.exists():
        _validate_existing_closure(
            closure_path,
            authorization_path=authorization_path,
            handoff_path=handoff_path,
            holder_path=holder_path,
            authorization=authorization,
        )
    return {
        "owner_path": owner_path,
        "owner_value": owner_value,
        "owner_bytes": owner_bytes,
        "owner_digest": owner_digest,
        "owner": owner,
        "handoff_path": handoff_path,
        "handoff_bytes": handoff_bytes,
        "handoff_digest": handoff_digest,
        "handoff": handoff,
        "holder_path": holder_path,
        "holder": holder,
        "holder_bytes": holder_bytes,
        "holder_digest": holder_digest,
        "closure_path": closure_path,
        "authorization_path": authorization_path,
        "authorization": authorization,
        "return_path": return_path,
    }


def _load_handoff_context(
    handoff_path: Path,
    holder_receipt_path: Path,
    closure_receipt_path: Path,
) -> tuple[dict[str, Any], bytes, str, dict[str, Any], bytes, str]:
    holder, holder_bytes, holder_digest = VISIBLE._load_holder_receipt_snapshot(
        _regular_file(holder_receipt_path, "holder receipt")
    )
    handoff, handoff_bytes, handoff_digest, _ = VISIBLE._load_handoff_holder_binding(
        handoff_path=_regular_file(handoff_path, "handoff"),
        holder_receipt_path=holder_receipt_path,
        closure_receipt_path=closure_receipt_path,
        holder_receipt=holder,
        holder_receipt_bytes=holder_bytes,
        holder_receipt_digest=holder_digest,
        require_return=True,
        require_terminal_action=True,
    )
    return handoff, handoff_bytes, handoff_digest, holder, holder_bytes, holder_digest


def _validate_handoff_owner(handoff: dict[str, Any], owner: dict[str, Any]) -> None:
    supplied = handoff.get("return_owner")
    if not isinstance(supplied, dict):
        raise ExternalCodexReturnError(
            "handoff must contain a complete return_owner object"
        )
    try:
        supplied_owner = validate_return_owner(supplied)
    except ExternalCodexReturnError as exc:
        raise ExternalCodexReturnError(
            "handoff return_owner is not a complete owner binding"
        ) from exc
    if _owner_binding_projection(supplied_owner) != _owner_binding_projection(owner):
        raise ExternalCodexReturnError("handoff return owner does not match owner binding")


def _validate_return_receipt(
    receipt: dict[str, Any],
    *,
    owner: dict[str, Any],
    owner_path: Path,
    handoff_path: Path,
    handoff_digest: str,
) -> dict[str, Any]:
    if receipt.get("schema_version") != RETURN_RECEIPT_SCHEMA_VERSION:
        raise ExternalCodexReturnError("canonical return receipt schema mismatch")
    if receipt.get("delivered") is not True:
        raise ExternalCodexReturnError("canonical return receipt does not prove delivery")
    if receipt.get("handoff_ref") != str(handoff_path.resolve()):
        raise ExternalCodexReturnError("canonical return receipt handoff identity mismatch")
    if receipt.get("handoff_sha256") != handoff_digest:
        raise ExternalCodexReturnError("canonical return receipt handoff digest mismatch")
    if receipt.get("owner_ref") != str(owner_path.resolve()):
        raise ExternalCodexReturnError("canonical return receipt owner identity mismatch")
    if receipt.get("owner") != _owner_projection(owner):
        raise ExternalCodexReturnError("canonical return receipt owner binding mismatch")
    if receipt.get("goal_status") != "active":
        raise ExternalCodexReturnError("canonical return receipt Goal is not active")
    goal_binding = receipt.get("goal_binding")
    if (
        not isinstance(goal_binding, dict)
        or goal_binding.get("goal_id") != owner["goal_id"]
        or goal_binding.get("thread_id") != owner["thread_id"]
        or goal_binding.get("before_status") not in {"active", "paused"}
        or goal_binding.get("activation") not in {"already_active", "paused_to_active"}
    ):
        raise ExternalCodexReturnError("canonical return receipt Goal binding is incomplete")
    actions = receipt.get("actions")
    observed = receipt.get("observed")
    delivery = receipt.get("delivery")
    if (
        not isinstance(actions, dict)
        or actions.get("handoff_message_sent") is not True
        or not isinstance(observed, dict)
        or observed.get("handoff_delivery") is not True
        or not isinstance(delivery, dict)
        or delivery.get("accepted") is not True
    ):
        raise ExternalCodexReturnError("canonical return receipt lacks delivery evidence")
    return receipt


def _load_existing_return_receipt(
    path: Path,
    *,
    owner: dict[str, Any],
    owner_path: Path,
    owner_digest: str,
    handoff_path: Path,
    handoff_digest: str,
) -> dict[str, Any]:
    value, raw = _load_json_file(path, "canonical return receipt")
    if raw != _canonical_bytes(value) + b"\n":
        raise ExternalCodexReturnError("canonical return receipt is not canonically encoded")
    if value.get("owner_sha256") != owner_digest:
        raise ExternalCodexReturnError("canonical return receipt owner digest mismatch")
    return _validate_return_receipt(
        value,
        owner=owner,
        owner_path=owner_path,
        handoff_path=handoff_path,
        handoff_digest=handoff_digest,
    )


def _load_existing_authorization(
    path: Path,
    *,
    handoff_path: Path,
    holder_path: Path,
    closure_path: Path,
    holder: dict[str, Any],
    holder_bytes: bytes,
    holder_digest: str,
    handoff_snapshot: tuple[dict[str, Any], bytes, str],
) -> dict[str, Any]:
    value, raw = _load_json_file(path, "terminal closure authorization")
    if raw != _canonical_bytes(value) + b"\n":
        raise ExternalCodexReturnError(
            "terminal closure authorization is not canonically encoded"
        )
    try:
        return VISIBLE._validate_closure_authorization(
            authorization_path=path,
            handoff_path=handoff_path,
            holder_receipt_path=holder_path,
            closure_receipt_path=closure_path,
            holder_receipt=holder,
            holder_receipt_bytes=holder_bytes,
            holder_receipt_digest=holder_digest,
            authorization_snapshot=(value, raw),
            handoff_snapshot=handoff_snapshot,
        )
    except Exception as exc:
        raise ExternalCodexReturnError(str(exc)) from exc


def _validate_existing_closure(
    path: Path,
    *,
    authorization_path: Path,
    handoff_path: Path,
    holder_path: Path,
    authorization: dict[str, Any],
) -> dict[str, Any]:
    """Validate a pre-existing closure before any new Goal delivery."""

    value, raw = _load_json_file(path, "terminal closure receipt")
    if raw != _canonical_bytes(value) + b"\n":
        raise ExternalCodexReturnError(
            "terminal closure receipt is not canonically encoded"
        )
    if value.get("schema_version") != VISIBLE.TERMINAL_CLOSURE_SCHEMA_VERSION:
        raise ExternalCodexReturnError(
            "existing closure receipt is not a typed canonical closure"
        )
    expected = {
        "handoff_ref": str(handoff_path.resolve()),
        "holder_receipt_ref": str(holder_path.resolve()),
        "authorization_ref": str(authorization_path.resolve()),
        "authorization_kind": authorization.get("authorization_kind"),
        "authorization_evidence_ref": authorization.get("evidence_ref"),
        "reservation_ref": str(VISIBLE._closure_reservation_path(path).resolve()),
        "route": "abyss_stack_visible_incarnation_runtime",
        "trigger": (
            "wake_bridge_after_confirmed_handoff_delivery"
            if authorization.get("authorization_kind") == "wake_delivered"
            else "join_after_validated_terminal_return"
        ),
        "closed": True,
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise ExternalCodexReturnError(
                f"existing closure receipt {key} does not match this return"
            )
    evidence_key = (
        "wake_receipt_ref"
        if authorization.get("authorization_kind") == "wake_delivered"
        else "join_receipt_ref"
    )
    if value.get(evidence_key) != authorization.get("evidence_ref"):
        raise ExternalCodexReturnError(
            "existing closure receipt evidence identity does not match authorization"
        )
    return value


def _call_visible(handler: Callable[[argparse.Namespace], int], args: argparse.Namespace) -> None:
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            result = handler(args)
    except Exception as exc:
        raise ExternalCodexReturnError(str(exc)) from exc
    if result != 0:
        raise ExternalCodexReturnError(f"visible lifecycle command failed: {handler.__name__}")


def run_return(args: argparse.Namespace) -> dict[str, Any]:
    inputs = _load_return_inputs(args)
    owner_path = inputs["owner_path"]
    owner_bytes = inputs["owner_bytes"]
    owner_digest = inputs["owner_digest"]
    owner = inputs["owner"]
    handoff_path = inputs["handoff_path"]
    handoff_bytes = inputs["handoff_bytes"]
    handoff_digest = inputs["handoff_digest"]
    handoff = inputs["handoff"]
    holder_path = inputs["holder_path"]
    holder = inputs["holder"]
    holder_bytes = inputs["holder_bytes"]
    holder_digest = inputs["holder_digest"]
    closure_path = inputs["closure_path"]
    authorization_path = inputs["authorization_path"]
    return_path = inputs["return_path"]
    handoff_snapshot = (handoff, handoff_bytes, handoff_digest)
    binding = _return_binding(
        owner_path=owner_path,
        owner_digest=owner_digest,
        handoff_path=handoff_path,
        handoff_digest=handoff_digest,
        holder_path=holder_path,
        holder_digest=holder_digest,
        authorization_path=authorization_path,
        closure_path=closure_path,
        return_path=return_path,
    )
    if return_path.exists():
        existing, _existing_raw = _load_json_file(
            return_path, "canonical return receipt"
        )
        if existing.get("state") == "reserved":
            _return_reservation(return_path, binding=binding)
            receipt = None
        else:
            receipt = _load_existing_return_receipt(
                return_path,
                owner=owner,
                owner_path=owner_path,
                owner_digest=owner_digest,
                handoff_path=handoff_path,
                handoff_digest=handoff_digest,
            )
    else:
        _return_reservation(return_path, binding=binding)
        receipt = None
    if receipt is None:
        VISIBLE._assert_file_snapshot(owner_path, owner_bytes, "return owner")
        VISIBLE._assert_file_snapshot(handoff_path, handoff_bytes, "handoff")
        endpoint, resolution = discover_app_server_socket(owner)
        receipt = deliver_handoff(
            owner,
            owner_path,
            handoff_path,
            endpoint,
            owner_bytes=owner_bytes,
            handoff_bytes=handoff_bytes,
        )
        receipt["transport"]["resolution"] = resolution
        _replace_json(return_path, receipt, "canonical return receipt")
        receipt = _load_existing_return_receipt(
            return_path,
            owner=owner,
            owner_path=owner_path,
            owner_digest=owner_digest,
            handoff_path=handoff_path,
            handoff_digest=handoff_digest,
        )
    VISIBLE._assert_file_snapshot(handoff_path, handoff_bytes, "handoff")
    VISIBLE._assert_file_snapshot(owner_path, owner_bytes, "return owner")
    if authorization_path.exists():
        authorization = _load_existing_authorization(
            authorization_path,
            handoff_path=handoff_path,
            holder_path=holder_path,
            closure_path=closure_path,
            holder=holder,
            holder_bytes=holder_bytes,
            holder_digest=holder_digest,
            handoff_snapshot=handoff_snapshot,
        )
    else:
        _call_visible(
            VISIBLE.command_authorize_close,
            SimpleNamespace(
                holder_receipt=str(holder_path),
                wake_receipt=str(return_path),
                handoff=str(handoff_path),
                authorization=str(authorization_path),
                closure_receipt=str(closure_path),
            ),
        )
        authorization = _load_existing_authorization(
            authorization_path,
            handoff_path=handoff_path,
            holder_path=holder_path,
            closure_path=closure_path,
            holder=holder,
            holder_bytes=holder_bytes,
            holder_digest=holder_digest,
            handoff_snapshot=handoff_snapshot,
        )
    VISIBLE._assert_file_snapshot(handoff_path, handoff_bytes, "handoff")
    VISIBLE._assert_file_snapshot(owner_path, owner_bytes, "return owner")
    # This is deliberately the last lifecycle primitive: once it starts, the
    # exact holder may receive TERM.  The detached route calls the same path.
    _call_visible(
        VISIBLE.command_close,
        SimpleNamespace(
            holder_receipt=str(holder_path),
            closure_authorization=str(authorization_path),
            wake_receipt=None,
            handoff=str(handoff_path),
            closure_receipt=str(closure_path),
        ),
    )
    closure, _closure_bytes = _load_json_file(closure_path, "terminal closure receipt")
    if closure.get("closed") is not True:
        raise ExternalCodexReturnError("canonical return did not prove holder closure")
    return {
        "schema_version": RETURN_RESPONSE_SCHEMA_VERSION,
        "returned": True,
        "delivery": receipt,
        "authorization": authorization,
        "closure": closure,
    }


def _detached_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    return_path = Path(args.return_receipt)
    detached = Path(args.detached_receipt or (str(return_path) + ".detached.json"))
    result = Path(args.detached_result or (str(return_path) + ".result.json"))
    log = Path(args.detached_log or (str(return_path) + ".detached.log"))
    return detached, result, log


def _replace_json(path: Path, value: dict[str, Any], label: str) -> None:
    try:
        VISIBLE._write_reservation_json(path, value, label)
    except Exception as exc:
        raise ExternalCodexReturnError(str(exc)) from exc


def _detached_binding(
    inputs: dict[str, Any],
    *,
    detached_path: Path,
    result_path: Path,
    log_path: Path,
) -> dict[str, str]:
    return {
        **_return_binding(
            owner_path=inputs["owner_path"],
            owner_digest=inputs["owner_digest"],
            handoff_path=inputs["handoff_path"],
            handoff_digest=inputs["handoff_digest"],
            holder_path=inputs["holder_path"],
            holder_digest=inputs["holder_digest"],
            authorization_path=inputs["authorization_path"],
            closure_path=inputs["closure_path"],
            return_path=inputs["return_path"],
        ),
        "detached_receipt_ref": str(detached_path.resolve()),
        "result_ref": str(result_path.resolve()),
        "log_ref": str(log_path.resolve()),
    }


def _validate_detached_receipt(
    value: dict[str, Any],
    *,
    binding: dict[str, str],
) -> str:
    if value.get("schema_version") != DETACHED_SCHEMA_VERSION:
        raise ExternalCodexReturnError("detached return receipt schema mismatch")
    state = value.get("state")
    if state not in {"running", "completed", "failed", "stale"}:
        raise ExternalCodexReturnError("detached return receipt state is invalid")
    for key, expected in binding.items():
        if value.get(key) != expected:
            raise ExternalCodexReturnError(
                f"detached return receipt {key} does not match current return"
            )
    return state


def _load_detached_result(path: Path, *, completed: bool) -> dict[str, Any]:
    value, raw = _load_json_file(path, "detached canonical return result")
    if raw != _canonical_bytes(value) + b"\n":
        raise ExternalCodexReturnError(
            "detached canonical return result is not canonically encoded"
        )
    if value.get("schema_version") != RETURN_RESPONSE_SCHEMA_VERSION:
        raise ExternalCodexReturnError("detached canonical return result schema mismatch")
    if completed and value.get("returned") is not True:
        raise ExternalCodexReturnError(
            "completed detached return does not prove a returned lifecycle"
        )
    if not completed and value.get("returned") is not False:
        raise ExternalCodexReturnError("failed detached return result is inconsistent")
    return value


def _retry_output_path(path: Path, label: str) -> Path:
    _validate_output_path(path, label)
    for _ in range(32):
        candidate = path.with_name(f"{path.name}.retry-{secrets.token_hex(8)}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise ExternalCodexReturnError(f"cannot allocate a retry path for {label}")


def _run_detached_child(
    args: argparse.Namespace,
    result_path: Path,
    log_path: Path,
    detached_path: Path,
    binding: dict[str, str],
    ready_fd: int,
) -> None:
    os.setsid()
    descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.dup2(descriptor, 1)
        os.dup2(descriptor, 2)
        os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
        ready = os.read(ready_fd, 1)
        os.close(ready_fd)
        if ready != b"\x01":
            raise ExternalCodexReturnError("detached return launch was not committed")
        try:
            result = run_return(args)
            _write_new_json(result_path, result, "detached canonical return result")
            if detached_path.exists():
                current, _current_raw = _load_json_file(
                    detached_path, "detached return receipt"
                )
                _replace_json(
                    detached_path,
                    {
                        **current,
                        **binding,
                        "schema_version": DETACHED_SCHEMA_VERSION,
                        "state": "completed",
                        "completed_at": _utc_now(),
                    },
                    "detached return receipt",
                )
            os._exit(0)
        except Exception as exc:
            failure = {
                "schema_version": RETURN_RESPONSE_SCHEMA_VERSION,
                "returned": False,
                "error": str(exc),
            }
            try:
                _write_new_json(result_path, failure, "detached canonical return result")
                if detached_path.exists():
                    current, _current_raw = _load_json_file(
                        detached_path, "detached return receipt"
                    )
                    _replace_json(
                        detached_path,
                        {
                            **current,
                            **binding,
                            "schema_version": DETACHED_SCHEMA_VERSION,
                            "state": "failed",
                            "completed_at": _utc_now(),
                        },
                        "detached return receipt",
                    )
            finally:
                os._exit(1)
    finally:
        os.close(descriptor)


def command_return(args: argparse.Namespace) -> int:
    if not args.detach:
        response = run_return(args)
        print(json.dumps(response, ensure_ascii=False, sort_keys=True))
        return 0
    detached_path = Path(
        args.detached_receipt or (str(args.return_receipt) + ".detached.json")
    )
    with _detached_retry_lock(detached_path) as lock_fd:
        return _command_return_detached(args, lock_fd)


def _command_return_detached(args: argparse.Namespace, lock_fd: int) -> int:
    inputs = _load_return_inputs(args)
    detached_path, result_path, log_path = _detached_paths(args)
    _validate_output_path(detached_path, "detached return receipt")
    _validate_output_path(result_path, "detached canonical return result")
    _validate_output_path(log_path, "detached canonical return log")
    _validate_distinct_output_paths(
        [
            (inputs["authorization_path"], "terminal closure authorization"),
            (inputs["closure_path"], "closure receipt"),
            (inputs["return_path"], "canonical return receipt"),
            (detached_path, "detached return receipt"),
            (result_path, "detached canonical return result"),
            (log_path, "detached canonical return log"),
        ]
    )
    binding = _detached_binding(
        inputs,
        detached_path=detached_path,
        result_path=result_path,
        log_path=log_path,
    )
    launch_args = args
    visited_receipts: set[Path] = set()
    while detached_path.exists():
        receipt_identity = detached_path.resolve()
        if receipt_identity in visited_receipts:
            raise ExternalCodexReturnError(
                "detached return retry chain contains a cycle"
            )
        visited_receipts.add(receipt_identity)
        value, raw = _load_json_file(detached_path, "detached return receipt")
        if raw != _canonical_bytes(value) + b"\n":
            raise ExternalCodexReturnError(
                "detached return receipt is not canonically encoded"
            )
        state = _validate_detached_receipt(value, binding=binding)
        if state == "completed":
            _load_detached_result(result_path, completed=True)
            print(json.dumps(value, ensure_ascii=False, sort_keys=True))
            return 0
        if state == "failed":
            _load_detached_result(result_path, completed=False)
            print(json.dumps(value, ensure_ascii=False, sort_keys=True))
            return 1
        pid = value.get("child_pid")
        start_ticks = value.get("child_start_ticks")
        state_now = "missing_identity"
        if isinstance(pid, int) and isinstance(start_ticks, int):
            state_now = VISIBLE._proc_identity_state(pid, start_ticks)
            if state == "running" and state_now == "live":
                print(json.dumps(value, ensure_ascii=False, sort_keys=True))
                return 0
        if state_now == "live":
            raise ExternalCodexReturnError(
                "stale detached return receipt still has a live child identity"
            )
        retry_refs = {
            "detached": value.get("retry_receipt_ref"),
            "result": value.get("retry_result_ref"),
            "log": value.get("retry_log_ref"),
        }
        if any(retry_refs.values()):
            if not all(isinstance(ref, str) and ref for ref in retry_refs.values()):
                raise ExternalCodexReturnError(
                    "detached return receipt has an incomplete retry binding"
                )
            retry_detached = _validate_output_path(
                Path(str(retry_refs["detached"])),
                "detached return retry receipt",
            )
            retry_result = _validate_output_path(
                Path(str(retry_refs["result"])),
                "detached return retry result",
            )
            retry_log = _validate_output_path(
                Path(str(retry_refs["log"])),
                "detached return retry log",
            )
            _validate_distinct_output_paths(
                [
                    (inputs["authorization_path"], "terminal closure authorization"),
                    (inputs["closure_path"], "closure receipt"),
                    (inputs["return_path"], "canonical return receipt"),
                    (retry_detached, "detached return retry receipt"),
                    (retry_result, "detached return retry result"),
                    (retry_log, "detached return retry log"),
                ]
            )
            detached_path, result_path, log_path = (
                retry_detached,
                retry_result,
                retry_log,
            )
            binding = _detached_binding(
                inputs,
                detached_path=detached_path,
                result_path=result_path,
                log_path=log_path,
            )
            if detached_path.exists():
                continue
            if result_path.exists() or log_path.exists():
                raise ExternalCodexReturnError(
                    "detached return retry receipt is missing but its output paths are used"
                )
            launch_args = SimpleNamespace(**vars(args))
            launch_args.detached_receipt = str(detached_path)
            launch_args.detached_result = str(result_path)
            launch_args.detached_log = str(log_path)
            break
        retry_detached = _retry_output_path(
            detached_path, "detached return receipt retry"
        )
        retry_result = _retry_output_path(
            result_path, "detached canonical return result retry"
        )
        retry_log = _retry_output_path(log_path, "detached canonical return log retry")
        _validate_distinct_output_paths(
            [
                (inputs["authorization_path"], "terminal closure authorization"),
                (inputs["closure_path"], "closure receipt"),
                (inputs["return_path"], "canonical return receipt"),
                (retry_detached, "detached return receipt retry"),
                (retry_result, "detached return result retry"),
                (retry_log, "detached return log retry"),
            ]
        )
        _replace_json(
            detached_path,
            {
                **value,
                "state": "stale",
                "stale_at": _utc_now(),
                "stale_child_state": state_now,
                "retry_receipt_ref": str(retry_detached.resolve()),
                "retry_result_ref": str(retry_result.resolve()),
                "retry_log_ref": str(retry_log.resolve()),
            },
            "stale detached return receipt",
        )
        detached_path, result_path, log_path = retry_detached, retry_result, retry_log
        binding = _detached_binding(
            inputs,
            detached_path=detached_path,
            result_path=result_path,
            log_path=log_path,
        )
        launch_args = SimpleNamespace(**vars(args))
        launch_args.detached_receipt = str(detached_path)
        launch_args.detached_result = str(result_path)
        launch_args.detached_log = str(log_path)
    if result_path.exists():
        raise ExternalCodexReturnError(
            f"detached canonical return result already exists: {result_path}"
        )
    if log_path.exists():
        raise ExternalCodexReturnError(
            f"detached canonical return log already exists: {log_path}"
        )
    ready_read, ready_write = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:
        os.close(lock_fd)
        os.close(ready_write)
        _run_detached_child(
            launch_args,
            result_path,
            log_path,
            detached_path,
            binding,
            ready_read,
        )
        raise AssertionError("detached child returned")
    os.close(ready_read)
    start_ticks = VISIBLE._proc_start_ticks(child_pid)
    receipt = {
        "schema_version": DETACHED_SCHEMA_VERSION,
        "state": "running",
        "created_at": _utc_now(),
        "child_pid": child_pid,
        "child_start_ticks": start_ticks,
        **binding,
    }
    try:
        _write_new_json(detached_path, receipt, "detached return receipt")
        os.write(ready_write, b"\x01")
    finally:
        os.close(ready_write)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description=(
            "Deliver an explicit external Codex handoff to its supplied Goal/session "
            "and close only its supplied visible holder."
        )
    )
    subcommands = root.add_subparsers(dest="command", required=True)
    return_parser = subcommands.add_parser(
        "return",
        help="deliver the handoff, authorize typed close, and close the exact holder",
    )
    return_parser.add_argument("--return-owner", required=True)
    return_parser.add_argument("--handoff", required=True)
    return_parser.add_argument("--holder-receipt", required=True)
    return_parser.add_argument("--return-receipt", required=True)
    return_parser.add_argument("--authorization", required=True)
    return_parser.add_argument("--closure-receipt", required=True)
    return_parser.add_argument("--detach", action="store_true")
    return_parser.add_argument("--detached-receipt")
    return_parser.add_argument("--detached-result")
    return_parser.add_argument("--detached-log")
    return_parser.set_defaults(handler=command_return)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ExternalCodexReturnError, VISIBLE.IncarnationHomeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
