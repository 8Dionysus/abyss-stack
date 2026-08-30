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
import stat
import struct
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Sequence

SCHEMA_VERSION = "abyss_stack_external_codex_return_v1"
RETURN_OWNER_SCHEMA_VERSION = "abyss_stack_external_codex_return_owner_v1"
LEGACY_RETURN_OWNER_SCHEMA_VERSION = "task_local_external_actor_return_owner_v1"
RETURN_ROUTE_SCHEMA_VERSION = "abyss_stack_external_codex_return_route_v1"
RETURN_RECEIPT_SCHEMA_VERSION = "abyss_stack_external_codex_return_receipt_v1"
RETURN_RESPONSE_SCHEMA_VERSION = "abyss_stack_external_codex_return_response_v1"
DETACHED_SCHEMA_VERSION = "abyss_stack_external_codex_return_detached_v1"
RETURN_ATTEMPT_SCHEMA_VERSION = "abyss_stack_external_codex_return_attempt_v1"
PAUSE_OWNER_SCHEMA_VERSION = "abyss_stack_external_codex_pause_owner_v1"
PAUSE_RESERVATION_SCHEMA_VERSION = "abyss_stack_external_codex_pause_reservation_v1"
PAUSE_RECEIPT_SCHEMA_VERSION = "abyss_stack_external_codex_pause_receipt_v1"
PAUSE_TRANSITION_PROOF_SCHEMA_VERSION = (
    "abyss_stack_external_codex_goal_transition_v2"
)
LEGACY_PAUSE_TRANSITION_PROOF_SCHEMA_VERSION = (
    "abyss_stack_external_codex_atomic_goal_transition_v1"
)
GOAL_LIFECYCLE_OWNER_SCHEMA_VERSION = (
    "abyss_stack_external_codex_goal_lifecycle_owner_v2"
)
GOAL_LIFECYCLE_RECEIPT_SCHEMA_VERSION = (
    "abyss_stack_external_codex_goal_lifecycle_receipt_v2"
)
GOAL_LIFECYCLE_ATTEMPT_SCHEMA_VERSION = (
    "abyss_stack_external_codex_goal_lifecycle_attempt_v1"
)
PAUSE_RECEIPT_SCHEMA_PATH = (
    Path(__file__).resolve().parent / "schemas" / "external-codex-pause-receipt.schema.json"
)
PAUSE_RESERVATION_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "schemas"
    / "external-codex-pause-reservation.schema.json"
)
WEBSOCKET_ACCEPT_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
DEFAULT_TIMEOUT_SECONDS = 10.0
APP_SERVER_DISCOVERY_PROBE_TIMEOUT_SECONDS = 1.0
APP_SERVER_DISCOVERY_ATTEMPTS = 5
APP_SERVER_DISCOVERY_RETRY_DELAY_SECONDS = 0.2
APP_SERVER_TURN_LOOKUP_TIMEOUT_SECONDS = 30.0
MAX_HANDSHAKE_BYTES = 64 * 1024
MAX_FRAME_BYTES = 16 * 1024 * 1024


class ExternalCodexReturnError(RuntimeError):
    """A fail-closed return validation or delivery error."""


class _AppServerCandidateMismatch(ExternalCodexReturnError):
    """A discovered endpoint did not prove the owner Goal/thread binding."""


class _ReturnAttemptLock:
    def __init__(self, fd: int) -> None:
        self.fd = fd
        self.transferred_to_detached_child = False


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


def _schema_validation_module() -> Any:
    module_name = "_aoa_external_codex_schema_validation"
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    path = Path(__file__).with_name("schema_validation.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ExternalCodexReturnError("cannot load local schema validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


SCHEMA_VALIDATION = _schema_validation_module()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha256_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == len("sha256:") + 64
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


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


def _validate_pause_receipt_schema(receipt: dict[str, Any]) -> None:
    try:
        schema = SCHEMA_VALIDATION.load_schema(PAUSE_RECEIPT_SCHEMA_PATH)
        error = SCHEMA_VALIDATION.first_error(receipt, schema)
    except SCHEMA_VALIDATION.SchemaValidationError as exc:
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt schema cannot be loaded"
        ) from exc
    if error is not None:
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt schema mismatch: " + error
        )


def _validate_pause_reservation_schema(reservation: dict[str, Any]) -> None:
    try:
        schema = SCHEMA_VALIDATION.load_schema(PAUSE_RESERVATION_SCHEMA_PATH)
        error = SCHEMA_VALIDATION.first_error(reservation, schema)
    except SCHEMA_VALIDATION.SchemaValidationError as exc:
        raise ExternalCodexReturnError(
            "canonical Goal pause reservation schema cannot be loaded"
        ) from exc
    if error is not None:
        raise ExternalCodexReturnError(
            "canonical Goal pause reservation schema mismatch: " + error
        )


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(
        character in value for character in "\x00\r\n"
    ):
        raise ExternalCodexReturnError(f"{label} must be a non-empty safe string")
    return value


def _owner_projection(
    owner: dict[str, Any], *, label: str = "return owner"
) -> dict[str, str]:
    return {
        key: _nonempty_string(owner.get(key), f"{label} {key}")
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


def _canonical_transport_binding(
    owner: dict[str, Any], *, label: str = "return owner"
) -> dict[str, object]:
    """Collapse every accepted endpoint spelling to the effective binding."""

    candidates = _transport_endpoint_candidates(owner)
    if len(set(candidates)) > 1:
        raise ExternalCodexReturnError(
            f"{label} transport endpoint aliases do not agree"
        )
    return {
        "posture": _nonempty_string(
            owner.get("transport_posture"), f"{label} transport_posture"
        ),
        "endpoint": candidates[0] if candidates else None,
    }


def _owner_binding_projection(owner: dict[str, Any]) -> dict[str, object]:
    """Project identity plus the complete canonical transport binding."""

    return {
        "identity": _owner_projection(owner),
        "transport": _canonical_transport_binding(owner),
    }


def _validate_owner_binding(
    owner: dict[str, Any],
    *,
    accepted_schema_versions: set[str],
    label: str,
    extra_allowed_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Validate one owner-selected Goal/thread transport binding."""

    allowed_keys = {
        "schema_version",
        "owner_id",
        "owner_repo",
        "goal_id",
        "thread_id",
        "runtime",
        "transport_posture",
        "acceptance_posture",
        "transport_endpoint",
        "app_server_socket",
        "transport",
    }
    if extra_allowed_keys:
        allowed_keys.update(extra_allowed_keys)
    unknown_keys = set(owner) - allowed_keys
    if unknown_keys:
        raise ExternalCodexReturnError(
            f"{label} contains undeclared fields: "
            + ", ".join(sorted(str(key) for key in unknown_keys))
        )
    schema = owner.get("schema_version")
    if schema not in accepted_schema_versions:
        raise ExternalCodexReturnError(f"unsupported {label} schema")
    projected = _owner_projection(owner, label=label)
    if projected["runtime"] != "codex":
        raise ExternalCodexReturnError(
            f"this {label} transport requires runtime=codex"
        )
    if "transport_endpoint" in owner:
        _nonempty_string(owner["transport_endpoint"], f"{label} transport_endpoint")
    if "app_server_socket" in owner:
        _nonempty_string(owner["app_server_socket"], f"{label} app_server_socket")
    transport = owner.get("transport")
    if transport is not None:
        if not isinstance(transport, dict):
            raise ExternalCodexReturnError(f"{label} transport must be an object")
        unknown_transport_keys = set(transport) - {"endpoint", "socket", "address"}
        if unknown_transport_keys:
            raise ExternalCodexReturnError(
                f"{label} transport contains undeclared fields: "
                + ", ".join(sorted(str(key) for key in unknown_transport_keys))
            )
        for key in ("endpoint", "socket", "address"):
            if key in transport:
                _nonempty_string(transport[key], f"{label} transport.{key}")
    _canonical_transport_binding({**owner, **projected}, label=label)
    return {**owner, **projected}


def validate_return_owner(owner: dict[str, Any]) -> dict[str, Any]:
    """Validate return owner binding data without selecting any owner identity."""

    return _validate_owner_binding(
        owner,
        accepted_schema_versions={
            RETURN_OWNER_SCHEMA_VERSION,
            LEGACY_RETURN_OWNER_SCHEMA_VERSION,
        },
        label="return owner",
    )


def validate_pause_owner(owner: dict[str, Any]) -> dict[str, Any]:
    """Validate a separate owner-selected Goal pause binding."""

    return _validate_owner_binding(
        owner,
        accepted_schema_versions={PAUSE_OWNER_SCHEMA_VERSION},
        label="pause owner",
    )


def validate_goal_lifecycle_owner(owner: dict[str, Any]) -> dict[str, Any]:
    """Validate the transport binding for the generic Goal lifecycle leaf."""

    validated = _validate_owner_binding(
        owner,
        accepted_schema_versions={GOAL_LIFECYCLE_OWNER_SCHEMA_VERSION},
        label="Goal lifecycle owner",
        extra_allowed_keys={"goal_ref", "return_owner_ref"},
    )
    for ref_key, id_key, label in (
        ("goal_ref", "goal_id", "Goal"),
        ("return_owner_ref", "owner_id", "return-owner"),
    ):
        reference = validated.get(ref_key)
        if not isinstance(reference, dict) or reference.get("object_id") != validated[id_key]:
            raise ExternalCodexReturnError(
                f"Goal lifecycle owner {label} reference object_id must match {id_key}"
            )
        if reference.get("owner_repo") != validated["owner_repo"]:
            raise ExternalCodexReturnError(
                f"Goal lifecycle owner {label} reference owner_repo must match owner_repo"
            )
    return validated


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


def _socket_is_connectable(path: Path) -> bool:
    """Probe a discovered UNIX socket without sending an app-server frame."""

    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.settimeout(APP_SERVER_DISCOVERY_PROBE_TIMEOUT_SECONDS)
        connection.connect(str(path))
    except OSError:
        return False
    finally:
        connection.close()
    return True


def _initialize_rpc(rpc: Any) -> dict[str, Any]:
    """Perform the common read-only app-server handshake."""

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
    return initialize


def _probe_owner_goal_binding(
    owner: dict[str, Any],
    endpoint: Path,
    rpc_factory: Callable[[Path], Any],
) -> str:
    """Prove that one live endpoint serves the owner-selected Goal/thread.

    Socket liveness alone cannot distinguish the current app-server from a
    stale or unrelated server left behind during restart/rebind.  The probe is
    deliberately read-only: it performs the normal handshake and one
    ``thread/goal/get`` for the canonical owner thread, then closes the
    connection before delivery opens its own connection.
    """

    try:
        with rpc_factory(endpoint) as rpc:
            _initialize_rpc(rpc)
            goal_response = rpc.call(
                "thread/goal/get",
                {"threadId": owner["thread_id"]},
            )
            goal = _goal_object(goal_response, "thread/goal/get")
            return _validate_goal_binding(goal, owner)
    except (ExternalCodexReturnError, OSError, TimeoutError) as exc:
        raise _AppServerCandidateMismatch(str(exc)) from exc


def _discovery_candidates() -> list[Path]:
    candidates: list[Path] = []
    value = os.environ.get("AOA_CODEX_APP_SERVER_SOCKET")
    if value:
        candidates.append(_socket_path(value))
    for environment_key in ("AOA_CODEX_HOME",):
        value = os.environ.get(environment_key)
        if value:
            candidates.append(Path(value) / "app-server-control/app-server-control.sock")
            candidates.append(Path(value) / ".codex/app-server-control/app-server-control.sock")
    # Prefer the ambient operator home over a scoped CODEX_HOME.  The latter
    # is normally the external holder's incarnation home during re-entry and
    # must not capture a master return merely because its socket is live.
    candidates.append(Path.home() / ".codex/app-server-control/app-server-control.sock")
    value = os.environ.get("CODEX_APP_SERVER_SOCKET")
    if value:
        candidates.append(_socket_path(value))
    value = os.environ.get("CODEX_HOME")
    if value:
        candidates.append(Path(value) / "app-server-control/app-server-control.sock")
        candidates.append(Path(value) / ".codex/app-server-control/app-server-control.sock")
    # Rebuild this list on every bounded attempt so a restart which replaces
    # the socket inode can be found on re-entry.
    return candidates


def discover_app_server_socket(
    owner: dict[str, Any],
    *,
    rpc_factory: Callable[[Path], Any] | None = None,
) -> tuple[Path, str]:
    """Resolve the current local Codex endpoint across a bounded restart gap.

    This is a reconnect allowance, not a watcher: at most five fresh socket
    snapshots are probed, with a short delay between them.  Every candidate
    must also prove the canonical owner Goal/thread binding before it is
    returned.  An explicit owner endpoint remains authoritative and is never
    replaced with an ambient candidate.
    """

    for key in ("goal_id", "thread_id"):
        value = owner.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ExternalCodexReturnError(
                "current app-server discovery requires the canonical Goal/thread binding"
            )
    if rpc_factory is None:
        def factory(endpoint: Path) -> UnixWebSocketRpc:
            return UnixWebSocketRpc(
                endpoint,
                timeout=APP_SERVER_DISCOVERY_PROBE_TIMEOUT_SECONDS,
                deadline_seconds=APP_SERVER_DISCOVERY_PROBE_TIMEOUT_SECONDS,
            )
    else:
        factory = rpc_factory
    explicit = _endpoint_from_owner(owner)
    if explicit is not None:
        path = _socket_path(explicit)
        last_mismatch: _AppServerCandidateMismatch | None = None
        for attempt in range(APP_SERVER_DISCOVERY_ATTEMPTS):
            if path.is_socket() and _socket_is_connectable(path):
                try:
                    _probe_owner_goal_binding(owner, path, factory)
                except _AppServerCandidateMismatch as exc:
                    last_mismatch = exc
                else:
                    return path, "owner_binding"
            if attempt + 1 < APP_SERVER_DISCOVERY_ATTEMPTS:
                time.sleep(APP_SERVER_DISCOVERY_RETRY_DELAY_SECONDS)
        if last_mismatch is not None:
            raise ExternalCodexReturnError(
                "owner-bound app-server endpoint did not prove the canonical "
                f"Goal/thread binding after bounded discovery: {path}: {last_mismatch}"
            ) from last_mismatch
        raise ExternalCodexReturnError(
            f"owner-bound app-server endpoint is not connectable after bounded discovery: {path}"
        )

    if owner["transport_posture"] != "resolve-current-local-codex-app-server":
        raise ExternalCodexReturnError(
            "return owner lacks an explicit endpoint or supported discovery posture"
        )
    candidates: list[Path] = []
    rejected: list[str] = []
    for attempt in range(APP_SERVER_DISCOVERY_ATTEMPTS):
        candidates = _discovery_candidates()
        seen: set[Path] = set()
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            if path.is_absolute() and not path.is_symlink() and path.is_socket():
                if _socket_is_connectable(path):
                    try:
                        _probe_owner_goal_binding(owner, path, factory)
                    except _AppServerCandidateMismatch as exc:
                        rejected.append(f"{path}: {exc}")
                        continue
                    return path, "current_local_codex_app_server"
        if attempt + 1 < APP_SERVER_DISCOVERY_ATTEMPTS:
            time.sleep(APP_SERVER_DISCOVERY_RETRY_DELAY_SECONDS)
    rendered = ", ".join(str(path) for path in candidates)
    rejection_detail = f"; identity rejections={rejected}" if rejected else ""
    raise ExternalCodexReturnError(
        "current local Codex app-server socket was not found after bounded "
        f"identity-checked discovery ({rendered}){rejection_detail}"
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

    def __init__(
        self,
        path: Path,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        deadline_seconds: float | None = None,
    ) -> None:
        self.path = path
        self.timeout = timeout
        self.deadline_seconds = deadline_seconds
        self._deadline: float | None = None
        self.socket: socket.socket | None = None
        self._buffer = b""
        self._counter = 0
        self.request_prepare_callback: Callable[
            [str, dict[str, object] | None, int, dict[str, object]], None
        ] | None = None
        self.request_issued_callback: Callable[
            [str, dict[str, object] | None, int, dict[str, object]], None
        ] | None = None

    def set_timeout(self, timeout: float) -> None:
        """Extend a connected read timeout for one bounded history lookup."""

        self.timeout = timeout
        if self.socket is not None:
            self.socket.settimeout(timeout)

    def __enter__(self) -> "UnixWebSocketRpc":
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._deadline = (
            time.monotonic() + self.deadline_seconds
            if self.deadline_seconds is not None
            else None
        )
        try:
            connection.settimeout(self._remaining_timeout())
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
            self._deadline = None

    def _remaining_timeout(self) -> float:
        if self._deadline is None:
            return self.timeout
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Codex app-server probe deadline exceeded")
        return min(self.timeout, remaining)

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
            connection.settimeout(self._remaining_timeout())
            chunk = connection.recv(remaining)
            if not chunk:
                raise ExternalCodexReturnError("Codex app-server closed the socket")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _read_until(self, marker: bytes) -> bytes:
        connection = self._require_socket()
        while marker not in self._buffer:
            connection.settimeout(self._remaining_timeout())
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
        if self.request_prepare_callback is not None:
            self.request_prepare_callback(method, params, request_id, payload)
        self._send_json(payload)
        if self.request_issued_callback is not None:
            self.request_issued_callback(method, params, request_id, payload)
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
        if "data" in turns:
            turns = turns["data"]
        elif "turns" in turns:
            turns = turns["turns"]
        else:
            raise ExternalCodexReturnError(
                "Codex app-server thread/read returned an invalid turns list"
            )
    if not isinstance(turns, list):
        raise ExternalCodexReturnError(
            "Codex app-server thread/read returned an invalid turns list"
        )
    for turn in reversed(turns):
        if not isinstance(turn, dict):
            raise ExternalCodexReturnError(
                "Codex app-server thread/read returned an invalid turn"
            )
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
        initialize = _initialize_rpc(rpc)
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
                # Keep the delivery frame bounded.  Codex may retain a large
                # history even when the Goal is idle; the abbreviated view
                # still exposes the active-turn evidence needed for steer.
                "includeTurns": False,
            },
        )
        thread = _thread_object(thread_read_response, "thread/read")
        if thread.get("id") != owner["thread_id"]:
            raise ExternalCodexReturnError(
                "Codex app-server Thread identity does not match owner binding"
            )
        turns = thread.get("turns")
        active_turn = _active_turn_id(turns)
        thread_turns_list_response: dict[str, Any] | None = None
        if active_turn is None:
            set_timeout = getattr(rpc, "set_timeout", None)
            if callable(set_timeout):
                set_timeout(APP_SERVER_TURN_LOOKUP_TIMEOUT_SECONDS)
            thread_turns_list_response = rpc.call(
                "thread/turns/list",
                {
                    "threadId": owner["thread_id"],
                    "limit": 1,
                    "itemsView": "notLoaded",
                },
            )
            active_turn = _active_turn_id(thread_turns_list_response.get("data"))
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
            "thread_turns_list": (
                _safe_response_summary(thread_turns_list_response)
                if thread_turns_list_response is not None
                else {"used": False}
            ),
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


def _pause_precondition(goal_get_response: dict[str, Any]) -> dict[str, Any]:
    """Capture the active observation before the one allowed lifecycle set."""

    goal_get_summary = _safe_response_summary(goal_get_response)
    return {
        "goal_status": "active",
        "goal_get": goal_get_summary,
        "goal_get_response": goal_get_response,
        "goal_get_summary_sha256": _sha256_bytes(
            _canonical_bytes(goal_get_summary)
        ),
        "goal_response_sha256": _sha256_bytes(
            _canonical_bytes(goal_get_response)
        ),
    }


def _validated_pause_precondition(
    reservation: dict[str, Any], *, owner: dict[str, Any] | None = None
) -> dict[str, Any]:
    precondition = reservation.get("precondition")
    if not isinstance(precondition, dict):
        raise ExternalCodexReturnError(
            "reserved Goal pause lacks a durable active precondition for reconciliation"
        )
    if (
        precondition.get("goal_status") != "active"
        or not isinstance(precondition.get("goal_get"), dict)
        or not isinstance(precondition.get("goal_get_response"), dict)
        or not _is_sha256_digest(precondition.get("goal_get_summary_sha256"))
        or not _is_sha256_digest(precondition.get("goal_response_sha256"))
        or precondition.get("goal_get_summary_sha256")
        != _sha256_bytes(_canonical_bytes(precondition.get("goal_get")))
        or precondition.get("goal_get")
        != _safe_response_summary(precondition.get("goal_get_response"))
        or precondition.get("goal_response_sha256")
        != _sha256_bytes(_canonical_bytes(precondition.get("goal_get_response")))
    ):
        raise ExternalCodexReturnError(
            "reserved Goal pause has an invalid active precondition"
        )
    if owner is not None:
        goal = _goal_object(precondition["goal_get_response"], "thread/goal/get")
        _validate_goal_binding(goal, owner)
        if _string_at(goal, ("status",)) != "active":
            raise ExternalCodexReturnError(
                "reserved Goal pause precondition does not confirm an active Goal"
            )
    return precondition


def _validated_pause_marker(
    mutation: object,
    *,
    owner: dict[str, Any],
    attempt_id: object,
    timestamp_key: str,
    label: str,
) -> dict[str, Any]:
    if not isinstance(mutation, dict):
        raise ExternalCodexReturnError(
            f"reserved Goal pause lacks durable {label} evidence"
        )
    expected_params = {"threadId": owner["thread_id"], "status": "paused"}
    params = mutation.get("params")
    params_match = (
        isinstance(params, dict)
        and params.get("threadId") == expected_params["threadId"]
        and params.get("status") == expected_params["status"]
    )
    expected_keys = {
        "attempt_id",
        "method",
        "request_id",
        "params",
        "params_sha256",
        "request_sha256",
        timestamp_key,
    }
    expected_payload = {
        "jsonrpc": "2.0",
        "id": mutation.get("request_id"),
        "method": "thread/goal/set",
        "params": params,
    }
    if (
        set(mutation) != expected_keys
        or not isinstance(attempt_id, str)
        or not attempt_id
        or mutation.get("attempt_id") != attempt_id
        or mutation.get("method") != "thread/goal/set"
        or not isinstance(mutation.get(timestamp_key), str)
        or not isinstance(mutation.get("request_id"), int)
        or isinstance(mutation.get("request_id"), bool)
        or mutation.get("request_id", 0) < 1
        or not params_match
        or mutation.get("params_sha256")
        != _sha256_bytes(_canonical_bytes(params))
        or not isinstance(mutation.get("request_sha256"), str)
        or mutation.get("request_sha256")
        != _sha256_bytes(_canonical_bytes(expected_payload))
    ):
        raise ExternalCodexReturnError(
            f"reserved Goal pause {label} evidence is invalid"
        )
    return mutation


def _validated_pause_mutation(
    mutation: object,
    *,
    owner: dict[str, Any],
    attempt_id: object,
) -> dict[str, Any]:
    return _validated_pause_marker(
        mutation,
        owner=owner,
        attempt_id=attempt_id,
        timestamp_key="issued_at",
        label="mutation-dispatch",
    )


def _validated_pause_reservation(
    mutation: object,
    *,
    owner: dict[str, Any],
    attempt_id: object,
) -> dict[str, Any]:
    return _validated_pause_marker(
        mutation,
        owner=owner,
        attempt_id=attempt_id,
        timestamp_key="reserved_at",
        label="mutation-reservation",
    )


def _validated_pause_transport(
    reservation: dict[str, Any], *, endpoint: Path
) -> dict[str, Any]:
    transport = reservation.get("transport")
    expected_endpoint = str(endpoint)
    if (
        not isinstance(transport, dict)
        or transport.get("kind") != "codex_app_server_websocket_unix"
        or transport.get("endpoint") != expected_endpoint
    ):
        raise ExternalCodexReturnError(
            "reserved Goal pause transport endpoint does not match the resolved app-server"
        )
    return transport


def _pause_mutation_marker(
    *,
    attempt_id: object,
    method: str,
    params: dict[str, object] | None,
    request_id: int,
    payload: dict[str, object],
    timestamp_key: str,
) -> dict[str, Any]:
    if (
        method != "thread/goal/set"
        or params is None
        or not isinstance(attempt_id, str)
        or not attempt_id
    ):
        raise ExternalCodexReturnError(
            "Codex app-server pause mutation dispatch identity mismatched"
        )
    marker = {
        "attempt_id": attempt_id,
        "method": method,
        "request_id": request_id,
        "params": params,
        "params_sha256": _sha256_bytes(_canonical_bytes(params)),
        "request_sha256": _sha256_bytes(_canonical_bytes(payload)),
    }
    marker[timestamp_key] = _utc_now()
    return marker


def _validated_pause_transition_proof(
    proof: object,
    *,
    owner: dict[str, Any],
    precondition: dict[str, Any],
    mutation: dict[str, Any],
    goal_response: dict[str, Any] | None = None,
    expected_response_digest: object | None = None,
    post_read_response: dict[str, Any] | None = None,
    expected_post_read_digest: object | None = None,
) -> dict[str, Any]:
    """Validate request/response/post-read evidence for one Goal transition."""

    if not isinstance(proof, dict):
        raise ExternalCodexReturnError(
            "Codex app-server pause response lacks transition evidence"
        )
    response_available = goal_response is not None or _is_sha256_digest(
        expected_response_digest
    )
    response_digest = (
        _sha256_bytes(_canonical_bytes(goal_response))
        if goal_response is not None
        else expected_response_digest
    )
    if (
        expected_response_digest is not None
        and goal_response is not None
        and response_digest != expected_response_digest
    ):
        raise ExternalCodexReturnError(
            "Codex app-server pause transition response digest is not bound"
        )
    if proof.get("schema_version") == LEGACY_PAUSE_TRANSITION_PROOF_SCHEMA_VERSION:
        expected_keys = {
            "schema_version",
            "kind",
            "method",
            "thread_id",
            "from_status",
            "to_status",
            "precondition_sha256",
            "request_id",
            "request_sha256",
            "goal_response_sha256",
        }
        if not _is_sha256_digest(response_digest):
            raise ExternalCodexReturnError(
                "legacy Goal pause transition proof lacks its mutation response"
            )
        if (
            set(proof) != expected_keys
            or proof.get("kind") != "server_compare_and_set"
            or proof.get("method") != "thread/goal/set"
            or proof.get("thread_id") != owner["thread_id"]
            or proof.get("from_status") != "active"
            or proof.get("to_status") != "paused"
            or proof.get("precondition_sha256")
            != precondition.get("goal_response_sha256")
            or proof.get("request_id") != mutation.get("request_id")
            or proof.get("request_sha256") != mutation.get("request_sha256")
            or not _is_sha256_digest(proof.get("precondition_sha256"))
            or not _is_sha256_digest(proof.get("request_sha256"))
            or proof.get("goal_response_sha256") != response_digest
        ):
            raise ExternalCodexReturnError(
                "legacy Goal pause transition proof is not bound to its request and response"
            )
        return proof
    if (
        post_read_response is not None
    ):
        observed_post_read_digest = _sha256_bytes(
            _canonical_bytes(post_read_response)
        )
        if (
            expected_post_read_digest is not None
            and expected_post_read_digest != observed_post_read_digest
        ):
            raise ExternalCodexReturnError(
                "Codex app-server pause transition post-read digest is not bound"
            )
        expected_post_read_digest = observed_post_read_digest
    elif not _is_sha256_digest(expected_post_read_digest):
        raise ExternalCodexReturnError(
            "Codex app-server pause transition evidence lacks a verifiable post-read"
        )
    expected_keys = {
        "schema_version",
        "kind",
        "method",
        "thread_id",
        "from_status",
        "to_status",
        "precondition_sha256",
        "request_id",
        "request_sha256",
        "goal_response_sha256",
        "post_read_response_sha256",
        "response_available",
    }
    if (
        set(proof) != expected_keys
        or proof.get("schema_version") != PAUSE_TRANSITION_PROOF_SCHEMA_VERSION
        or proof.get("kind")
        != (
            "request_response_post_read"
            if response_available
            else "dispatch_reconciled_post_read"
        )
        or proof.get("method") != "thread/goal/set"
        or proof.get("thread_id") != owner["thread_id"]
        or proof.get("from_status") != "active"
        or proof.get("to_status") != "paused"
        or proof.get("precondition_sha256")
        != precondition.get("goal_response_sha256")
        or proof.get("request_id") != mutation.get("request_id")
        or proof.get("request_sha256") != mutation.get("request_sha256")
        or not _is_sha256_digest(proof.get("precondition_sha256"))
        or not _is_sha256_digest(proof.get("request_sha256"))
        or proof.get("goal_response_sha256") != response_digest
        or proof.get("post_read_response_sha256") != expected_post_read_digest
        or proof.get("response_available") is not response_available
    ):
        raise ExternalCodexReturnError(
            "Codex app-server pause transition evidence is not bound to the "
            "active precondition, exact mutation, and post-read"
        )
    return proof


def _pause_transition_proof(
    *,
    owner: dict[str, Any],
    precondition: dict[str, Any],
    mutation: dict[str, Any],
    goal_response: dict[str, Any] | None,
    post_read_response: dict[str, Any],
) -> dict[str, Any]:
    proof = {
        "schema_version": PAUSE_TRANSITION_PROOF_SCHEMA_VERSION,
        "kind": (
            "request_response_post_read"
            if goal_response is not None
            else "dispatch_reconciled_post_read"
        ),
        "method": "thread/goal/set",
        "thread_id": owner["thread_id"],
        "from_status": "active",
        "to_status": "paused",
        "precondition_sha256": precondition["goal_response_sha256"],
        "request_id": mutation["request_id"],
        "request_sha256": mutation["request_sha256"],
        "goal_response_sha256": (
            _sha256_bytes(_canonical_bytes(goal_response))
            if goal_response is not None
            else None
        ),
        "post_read_response_sha256": _sha256_bytes(
            _canonical_bytes(post_read_response)
        ),
        "response_available": goal_response is not None,
    }
    return _validated_pause_transition_proof(
        proof,
        owner=owner,
        precondition=precondition,
        mutation=mutation,
        goal_response=goal_response,
        post_read_response=post_read_response,
    )


def _pause_receipt(
    *,
    owner: dict[str, Any],
    owner_path: Path,
    pause_receipt_path: Path,
    owner_bytes: bytes,
    endpoint: Path,
    initialize: dict[str, Any],
    goal_get_response: dict[str, Any],
    goal_response: dict[str, Any] | None,
    post_read_response: dict[str, Any],
    before_status: str,
    goal_status: str,
    identity_source: str,
    precondition: dict[str, Any],
    transition_proof: dict[str, Any],
    mutation_dispatched: dict[str, Any] | None = None,
    recovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lifecycle: dict[str, Any] = {
        "accepted": True,
        "initialize": _safe_response_summary(initialize),
        # Preserve the original active observation here.  During
        # post-dispatch recovery ``goal_get_response`` is the later paused
        # reconciliation read; the durable precondition remains the evidence
        # that this lifecycle attempt started from active.
        "goal_get": precondition["goal_get"],
        "goal": _safe_response_summary(
            goal_response if goal_response is not None else post_read_response
        ),
        "goal_summary_sha256": _sha256_bytes(
            _canonical_bytes(
                _safe_response_summary(
                    goal_response if goal_response is not None else post_read_response
                )
            )
        ),
        "goal_response_sha256": (
            _sha256_bytes(_canonical_bytes(goal_response))
            if goal_response is not None
            else None
        ),
        # Preserve the returned mutation response too.  A digest without the
        # response bytes cannot be recomputed during receipt replay.
        "goal_response": goal_response,
        "post_read": _safe_response_summary(post_read_response),
        # Keep the exact post-read alongside its digest.  The safe summary is
        # useful for projection, but cannot by itself prove which bytes the
        # transition proof covered.
        "post_read_response": post_read_response,
        "post_read_response_sha256": _sha256_bytes(
            _canonical_bytes(post_read_response)
        ),
        "precondition": precondition,
        "response_available": goal_response is not None,
        "transition_proof": transition_proof,
    }
    if mutation_dispatched is not None:
        lifecycle["mutation_dispatched"] = mutation_dispatched
    receipt: dict[str, Any] = {
        "schema_version": PAUSE_RECEIPT_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "owner_ref": str(owner_path.resolve()),
        "owner_sha256": _sha256_bytes(owner_bytes),
        "pause_receipt_ref": str(pause_receipt_path.resolve()),
        "owner": _owner_projection(owner),
        "transport": {
            "kind": "codex_app_server_websocket_unix",
            "endpoint": str(endpoint),
        },
        "goal_status": goal_status,
        "goal_binding": {
            "goal_id": owner["goal_id"],
            "thread_id": owner["thread_id"],
            "before_status": before_status,
            "transition": "active_to_paused",
            "identity_source": identity_source,
        },
        "lifecycle_method": "thread/goal/set",
        "lifecycle": lifecycle,
        "actions": {"goal_lifecycle_set": True},
        "observed": {"goal_lifecycle": "paused", "goal_status": "paused"},
        "paused": True,
        "owner_acceptance": "separate",
        "semantic_acceptance": "separate",
    }
    if recovery is not None:
        receipt["recovery"] = recovery
    return receipt


def pause_goal(
    owner: dict[str, Any],
    owner_path: Path,
    endpoint: Path,
    *,
    owner_bytes: bytes | None = None,
    reservation_path: Path | None = None,
    reservation: dict[str, Any] | None = None,
    rpc_factory: Callable[[Path], Any] = UnixWebSocketRpc,
) -> dict[str, Any]:
    """Pause one active owner-bound Goal through the Codex app-server API.

    This is deliberately separate from ``deliver_handoff``: it changes only
    Goal lifecycle state and emits no wake message, turn, holder close, or
    acceptance claim. When a prior process issued the exact
    ``thread/goal/set`` frame but lost its response, a durable active
    precondition plus post-send dispatch marker permits a read-only
    reconciliation of the already-paused Goal without issuing a second set.
    Every mutation attempt must carry its durable reservation so the completed
    pause receipt cannot omit the dispatch evidence required by its schema.
    The current Codex protocol exposes the ordinary ``thread/goal/set``
    mutation without a compare-and-set token.  The runtime therefore binds the
    exact issued request and returned response, then performs a bounded fresh
    ``thread/goal/get`` confirmation.  A lost response is recovered only from
    the durable dispatch marker and that fresh read; it never issues a second
    lifecycle set.
    """

    if owner_bytes is None:
        owner_bytes = owner_path.read_bytes()
    with rpc_factory(endpoint) as rpc:
        initialize = rpc.call(
            "initialize",
            {
                "clientInfo": {
                    "name": "abyss_stack_external_codex_pause",
                    "title": "Abyss external Codex Goal pause",
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
        if goal_before_status == "paused":
            if reservation_path is None or reservation is None:
                raise ExternalCodexReturnError(
                    "Codex app-server Goal is not pausable from active state; it is already paused without a resumable pause reservation"
                )
            _validated_pause_transport(reservation, endpoint=endpoint)
            precondition = _validated_pause_precondition(reservation, owner=owner)
            mutation_dispatched = _validated_pause_mutation(
                reservation.get("mutation_dispatched"),
                owner=owner,
                attempt_id=reservation.get("attempt_id"),
            )
            durable_goal_response = reservation.get("goal_response")
            if durable_goal_response is not None and not isinstance(
                durable_goal_response, dict
            ):
                raise ExternalCodexReturnError(
                    "reserved Goal pause mutation response is not an object"
                )
            if isinstance(durable_goal_response, dict):
                durable_goal = _goal_object(
                    durable_goal_response, "thread/goal/set"
                )
                _validate_goal_binding(durable_goal, owner)
                if _string_at(durable_goal, ("status",)) != "paused":
                    raise ExternalCodexReturnError(
                        "reserved Goal pause mutation response did not confirm a paused Goal"
                    )
            stored_proof = reservation.get("transition_proof")
            stored_post_read = reservation.get("post_read_response")
            if (
                isinstance(stored_proof, dict)
                and stored_proof.get("schema_version")
                == PAUSE_TRANSITION_PROOF_SCHEMA_VERSION
                and not isinstance(stored_post_read, dict)
            ):
                raise ExternalCodexReturnError(
                    "stored Goal pause transition proof lacks its post-read response"
                )
            if isinstance(stored_post_read, dict):
                stored_post_read_goal = _goal_object(
                    stored_post_read, "thread/goal/get"
                )
                _validate_goal_binding(stored_post_read_goal, owner)
                if _string_at(stored_post_read_goal, ("status",)) != "paused":
                    raise ExternalCodexReturnError(
                        "stored Goal pause post-read did not confirm a paused Goal"
                    )
            if stored_proof is not None:
                proof_post_read = (
                    stored_post_read
                    if isinstance(stored_post_read, dict)
                    else None
                )
                _validated_pause_transition_proof(
                    stored_proof,
                    owner=owner,
                    precondition=precondition,
                    mutation=mutation_dispatched,
                    goal_response=durable_goal_response,
                    expected_response_digest=(
                        stored_proof.get("goal_response_sha256")
                        if isinstance(stored_proof, dict)
                        else None
                    ),
                    post_read_response=proof_post_read,
                    expected_post_read_digest=(
                        stored_proof.get("post_read_response_sha256")
                        if isinstance(stored_proof, dict)
                        else None
                    ),
                )
            # A paused Goal plus the durable dispatch marker is enough to
            # reconcile an interrupted attempt.  When proof and post-read
            # bytes already exist, the fresh read above is only a current
            # identity/state check; preserve those historical proof bytes
            # instead of rewriting them from mutable Goal metadata.
            if isinstance(stored_proof, dict):
                transition_proof = stored_proof
                proof_post_read = (
                    stored_post_read
                    if isinstance(stored_post_read, dict)
                    else goal_get_response
                )
            else:
                proof_post_read = goal_get_response
                transition_proof = _pause_transition_proof(
                    owner=owner,
                    precondition=precondition,
                    mutation=mutation_dispatched,
                    goal_response=durable_goal_response,
                    post_read_response=proof_post_read,
                )
            proof_reservation = {
                **reservation,
                "post_read_response": proof_post_read,
                "transition_proof": transition_proof,
            }
            _replace_json(
                reservation_path,
                proof_reservation,
                "canonical Goal pause transition proof",
            )
            VISIBLE._assert_file_snapshot(
                owner_path, owner_bytes, "pause owner"
            )
            reservation.clear()
            reservation.update(proof_reservation)
            return _pause_receipt(
                owner=owner,
                owner_path=owner_path,
                pause_receipt_path=reservation_path,
                owner_bytes=owner_bytes,
                endpoint=endpoint,
                initialize=initialize,
                goal_get_response=goal_get_response,
                goal_response=durable_goal_response,
                post_read_response=proof_post_read,
                before_status="active",
                goal_status="paused",
                identity_source=goal_identity_source,
                precondition=precondition,
                transition_proof=transition_proof,
                mutation_dispatched=mutation_dispatched,
                recovery={
                    "mode": "ambiguous_post_mutation",
                    "mutation_response_available": isinstance(
                        durable_goal_response, dict
                    ),
                    "reconciled_by": "thread/goal/get",
                    "mutation_dispatched": mutation_dispatched,
                },
            )
        if goal_before_status != "active":
            raise ExternalCodexReturnError(
                "Codex app-server Goal is not pausable from active state: "
                f"{goal_before_status!r}"
            )
        if reservation_path is None or reservation is None:
            raise ExternalCodexReturnError(
                "Goal pause mutation requires a durable reservation"
            )
        if reservation is not None:
            mutation_dispatched = reservation.get("mutation_dispatched")
            mutation_reserved = reservation.get("mutation_reserved")
            if mutation_dispatched is not None or mutation_reserved is not None:
                _validated_pause_transport(reservation, endpoint=endpoint)
                if mutation_dispatched is not None:
                    _validated_pause_mutation(
                        mutation_dispatched,
                        owner=owner,
                        attempt_id=reservation.get("attempt_id"),
                    )
                    raise ExternalCodexReturnError(
                        "Goal pause mutation was already dispatched while the Goal remains active; refusing to issue a second lifecycle set"
                    )
                _validated_pause_reservation(
                    mutation_reserved,
                    owner=owner,
                    attempt_id=reservation.get("attempt_id"),
                )
                raise ExternalCodexReturnError(
                    "Goal pause mutation was reserved before transport dispatch; refusing to issue a second lifecycle set"
                )
        precondition = _pause_precondition(goal_get_response)
        if reservation_path is not None:
            if reservation is None:
                raise ExternalCodexReturnError(
                    "Goal pause reservation is required when a reservation path is supplied"
                )
            attempt_id = secrets.token_hex(16)
            reservation_without_attempt = {
                key: value
                for key, value in reservation.items()
                if key
                not in {
                    "attempt_id",
                    "prepared_at",
                    "precondition",
                    "transport",
                    "mutation_reserved",
                    "mutation_dispatched",
                }
            }
            reservation.clear()
            reservation.update(reservation_without_attempt)
            reservation["attempt_id"] = attempt_id
            prepared_reservation = {
                **reservation,
                "prepared_at": _utc_now(),
                "precondition": precondition,
                "transport": {
                    "kind": "codex_app_server_websocket_unix",
                    "endpoint": str(endpoint),
                },
            }
            reservation.clear()
            reservation.update(prepared_reservation)
            _replace_json(
                reservation_path,
                prepared_reservation,
                "canonical Goal pause precondition reservation",
            )
        def build_request_marker(
            method: str,
            params: dict[str, object] | None,
            request_id: int,
            payload: dict[str, object],
            timestamp_key: str,
        ) -> dict[str, Any]:
            if reservation_path is None or reservation is None:
                raise ExternalCodexReturnError(
                    "Goal pause mutation dispatch lacks a reservation"
                )
            if (
                method != "thread/goal/set"
                or not isinstance(params, dict)
                or params.get("threadId") != owner["thread_id"]
                or params.get("status") != "paused"
            ):
                raise ExternalCodexReturnError(
                    "Codex app-server pause mutation dispatch identity mismatched"
                )
            return _pause_mutation_marker(
                attempt_id=reservation.get("attempt_id"),
                method=method,
                params=params,
                request_id=request_id,
                payload=payload,
                timestamp_key=timestamp_key,
            )

        def record_request_prepared(
            method: str,
            params: dict[str, object] | None,
            request_id: int,
            payload: dict[str, object],
        ) -> None:
            if reservation_path is None or reservation is None:
                return
            mutation = build_request_marker(
                method, params, request_id, payload, "reserved_at"
            )
            _replace_json(
                reservation_path,
                {**reservation, "mutation_reserved": mutation},
                "canonical Goal pause mutation reservation",
            )
            reservation["mutation_reserved"] = mutation

        def record_request_issued(
            method: str,
            params: dict[str, object] | None,
            request_id: int,
            payload: dict[str, object],
        ) -> None:
            if reservation_path is None or reservation is None:
                return
            mutation = build_request_marker(
                method, params, request_id, payload, "issued_at"
            )
            dispatched_reservation = {
                key: value
                for key, value in reservation.items()
                if key != "mutation_reserved"
            }
            dispatched_reservation["mutation_dispatched"] = mutation
            _replace_json(
                reservation_path,
                dispatched_reservation,
                "canonical Goal pause mutation dispatch",
            )
            reservation.clear()
            reservation.update(dispatched_reservation)

        previous_prepare_callback = getattr(rpc, "request_prepare_callback", None)
        previous_callback = getattr(rpc, "request_issued_callback", None)
        setattr(rpc, "request_prepare_callback", record_request_prepared)
        setattr(rpc, "request_issued_callback", record_request_issued)
        try:
            VISIBLE._assert_file_snapshot(
                owner_path, owner_bytes, "pause owner"
            )
            goal_response = rpc.call(
                "thread/goal/set",
                {"threadId": owner["thread_id"], "status": "paused"},
            )
        finally:
            setattr(rpc, "request_prepare_callback", previous_prepare_callback)
            setattr(rpc, "request_issued_callback", previous_callback)
        mutation_dispatched = _validated_pause_mutation(
            reservation.get("mutation_dispatched"),
            owner=owner,
            attempt_id=reservation.get("attempt_id"),
        )
        goal = _goal_object(goal_response, "thread/goal/set")
        goal_identity_source = _validate_goal_binding(goal, owner)
        goal_status = _string_at(goal, ("status",))
        if goal_status != "paused":
            raise ExternalCodexReturnError(
                "Codex app-server did not confirm a paused Goal: "
                f"{goal_status!r}"
            )
        proof_reservation = {
            **reservation,
            "goal_response": goal_response,
        }
        _replace_json(
            reservation_path,
            proof_reservation,
            "canonical Goal pause mutation response",
        )
        reservation.clear()
        reservation.update(proof_reservation)
        post_read_response = rpc.call(
            "thread/goal/get",
            {"threadId": owner["thread_id"]},
        )
        post_read_goal = _goal_object(post_read_response, "thread/goal/get")
        _validate_goal_binding(post_read_goal, owner)
        post_read_status = _string_at(post_read_goal, ("status",))
        if post_read_status != "paused":
            raise ExternalCodexReturnError(
                "Codex app-server post-read did not confirm a paused Goal: "
                f"{post_read_status!r}"
            )
        transition_proof = _pause_transition_proof(
            owner=owner,
            precondition=precondition,
            mutation=mutation_dispatched,
            goal_response=goal_response,
            post_read_response=post_read_response,
        )
        proof_reservation = {
            **reservation,
            "goal_response": goal_response,
            "post_read_response": post_read_response,
            "transition_proof": transition_proof,
        }
        _replace_json(
            reservation_path,
            proof_reservation,
            "canonical Goal pause transition proof",
        )
        VISIBLE._assert_file_snapshot(
            owner_path, owner_bytes, "pause owner"
        )
        reservation.clear()
        reservation.update(proof_reservation)
    return _pause_receipt(
        owner=owner,
        owner_path=owner_path,
        pause_receipt_path=reservation_path,
        owner_bytes=owner_bytes,
        endpoint=endpoint,
        initialize=initialize,
        goal_get_response=goal_get_response,
        goal_response=goal_response,
        post_read_response=post_read_response,
        before_status=goal_before_status,
        goal_status=goal_status,
        identity_source=goal_identity_source,
        precondition=precondition,
        transition_proof=transition_proof,
        mutation_dispatched=(
            reservation.get("mutation_dispatched")
            if reservation is not None
            else None
        ),
    )


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
def _return_attempt_lock(anchor_path: Path) -> Any:
    """Serialize one canonical return attempt and its detached receipt chain."""

    _validate_output_path(anchor_path, "closure receipt")
    lock_path = anchor_path.with_name(anchor_path.name + ".return-attempt.lock")
    if lock_path.is_symlink():
        raise ExternalCodexReturnError(
            f"return attempt lock may not be a symlink: {lock_path}"
        )
    lock_fd: int | None = None
    lock: _ReturnAttemptLock | None = None
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
            f"cannot acquire return attempt lock: {lock_path}"
        ) from exc
    try:
        lock = _ReturnAttemptLock(lock_fd)
        yield lock
    finally:
        if lock_fd is not None:
            try:
                if lock is None or not lock.transferred_to_detached_child:
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


def _return_attempt_path(closure_path: Path) -> Path:
    return closure_path.with_name(closure_path.name + ".return-attempt.json")


def _return_attempt_binding(inputs: dict[str, Any]) -> dict[str, str]:
    """Bind idempotency to immutable lifecycle inputs, never caller output names."""

    return {
        "owner_ref": str(inputs["owner_path"].resolve()),
        "owner_sha256": str(inputs["owner_digest"]),
        "handoff_ref": str(inputs["handoff_path"].resolve()),
        "handoff_sha256": str(inputs["handoff_digest"]),
        "holder_receipt_ref": str(inputs["holder_path"].resolve()),
        "holder_receipt_sha256": str(inputs["holder_digest"]),
        "authorization_ref": str(inputs["authorization_path"].resolve()),
        "closure_receipt_ref": str(inputs["closure_path"].resolve()),
    }


def _reserve_return_attempt(
    inputs: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    """Reserve one closure-bound return identity before any transport mutation."""

    attempt_path = inputs.get("attempt_path")
    if not isinstance(attempt_path, Path):
        attempt_path = _return_attempt_path(inputs["closure_path"])
    attempt_path = _validate_output_path(
        attempt_path, "canonical return attempt reservation"
    )
    binding = _return_attempt_binding(inputs)
    if attempt_path.exists():
        value, raw = _load_json_file(
            attempt_path, "canonical return attempt reservation"
        )
        if raw != _canonical_bytes(value) + b"\n":
            raise ExternalCodexReturnError(
                "canonical return attempt reservation is not canonically encoded"
            )
        if value.get("schema_version") != RETURN_ATTEMPT_SCHEMA_VERSION:
            raise ExternalCodexReturnError(
                "canonical return attempt reservation schema mismatch"
            )
        if value.get("state") != "reserved":
            raise ExternalCodexReturnError(
                "canonical return attempt reservation state is invalid"
            )
        for key, expected in binding.items():
            if value.get(key) != expected:
                raise ExternalCodexReturnError(
                    f"canonical return attempt reservation {key} mismatch"
                )
        recorded_ref = value.get("return_receipt_ref")
        if not isinstance(recorded_ref, str) or not recorded_ref.startswith("/"):
            raise ExternalCodexReturnError(
                "canonical return attempt reservation lacks a return receipt path"
            )
        recorded_path = _validate_output_path(
            Path(recorded_ref), "canonical return receipt"
        )
        if str(recorded_path.resolve()) != recorded_ref:
            raise ExternalCodexReturnError(
                "canonical return attempt reservation return path is not canonical"
            )
        _validate_distinct_output_paths(
            [
                (inputs["authorization_path"], "terminal closure authorization"),
                (inputs["closure_path"], "closure receipt"),
                (attempt_path, "canonical return attempt reservation"),
                (recorded_path, "canonical return receipt"),
            ]
        )
        authorization = inputs.get("authorization")
        if isinstance(authorization, dict) and authorization.get(
            "authorization_kind"
        ) == "wake_delivered":
            evidence_ref = authorization.get("evidence_ref")
            if not isinstance(evidence_ref, str) or not evidence_ref.startswith("/"):
                raise ExternalCodexReturnError(
                    "existing wake authorization lacks a canonical return receipt"
                )
            evidence_path = _validate_output_path(
                Path(evidence_ref), "canonical return evidence"
            )
            if evidence_path.resolve() != recorded_path.resolve():
                raise ExternalCodexReturnError(
                    "canonical return attempt reservation disagrees with wake evidence"
                )
        return attempt_path, value
    authorization = inputs.get("authorization")
    if isinstance(authorization, dict) and authorization.get(
        "authorization_kind"
    ) == "wake_delivered":
        evidence_ref = authorization.get("evidence_ref")
        if not isinstance(evidence_ref, str) or not evidence_ref.startswith("/"):
            raise ExternalCodexReturnError(
                "existing wake authorization lacks a canonical return receipt"
            )
        recorded_path = _validate_output_path(
            Path(evidence_ref), "canonical return evidence"
        )
    else:
        recorded_path = _validate_output_path(
            inputs["return_path"], "canonical return receipt"
        )
    _validate_distinct_output_paths(
        [
            (inputs["authorization_path"], "terminal closure authorization"),
            (inputs["closure_path"], "closure receipt"),
            (attempt_path, "canonical return attempt reservation"),
            (recorded_path, "canonical return receipt"),
        ]
    )
    reservation = {
        "schema_version": RETURN_ATTEMPT_SCHEMA_VERSION,
        "state": "reserved",
        "reserved_at": _utc_now(),
        **binding,
        "return_receipt_ref": str(recorded_path.resolve()),
    }
    _write_new_json(
        attempt_path, reservation, "canonical return attempt reservation"
    )
    return attempt_path, reservation


def _bind_return_attempt(inputs: dict[str, Any]) -> dict[str, Any]:
    """Use the durable closure-bound return path for this and every retry."""

    authorization = inputs.get("authorization")
    if isinstance(authorization, dict) and authorization.get(
        "authorization_kind"
    ) not in {None, "wake_delivered"}:
        raise ExternalCodexReturnError(
            "existing closure authorization is not a canonical wake delivery"
        )
    _attempt_path, attempt = _reserve_return_attempt(inputs)
    recorded_ref = attempt.get("return_receipt_ref")
    if not isinstance(recorded_ref, str):
        raise ExternalCodexReturnError(
            "canonical return attempt reservation lacks a return receipt path"
        )
    recorded_path = _validate_output_path(
        Path(recorded_ref), "canonical return receipt"
    )
    requested_path = inputs["return_path"]
    if requested_path.resolve() != recorded_path.resolve() and requested_path.exists():
        raise ExternalCodexReturnError(
            "canonical return receipt path differs from the bound return attempt"
        )
    bound = dict(inputs)
    bound["return_path"] = recorded_path
    return bound


def _load_return_route(path: Path) -> dict[str, str]:
    """Validate one typed bridge route without selecting any Goal identity."""

    route_path = _regular_file(path, "canonical return route")
    route, _raw = _load_json_file(route_path, "canonical return route")
    required = {
        "schema_version",
        "owner_ref",
        "owner_sha256",
        "handoff_ref",
        "handoff_sha256",
        "holder_receipt_ref",
        "holder_receipt_sha256",
        "return_receipt_ref",
        "authorization_ref",
        "closure_receipt_ref",
    }
    if set(route) != required:
        raise ExternalCodexReturnError("canonical return route fields are not exact")
    if route.get("schema_version") != RETURN_ROUTE_SCHEMA_VERSION:
        raise ExternalCodexReturnError("unsupported canonical return route schema")
    values: dict[str, str] = {}
    for key in (
        "owner_ref",
        "handoff_ref",
        "holder_receipt_ref",
        "return_receipt_ref",
        "authorization_ref",
        "closure_receipt_ref",
    ):
        value = route.get(key)
        if not isinstance(value, str) or not value.startswith("/"):
            raise ExternalCodexReturnError(
                f"canonical return route {key} must be an absolute path"
            )
        values[key] = value
    for key in ("owner_sha256", "handoff_sha256", "holder_receipt_sha256"):
        value = route.get(key)
        if not _is_sha256_digest(value):
            raise ExternalCodexReturnError(
                f"canonical return route {key} is not a sha256 digest"
            )
        values[key] = value
    owner_path = _regular_file(Path(values["owner_ref"]), "return owner")
    handoff_path = _regular_file(Path(values["handoff_ref"]), "handoff")
    holder_path = _regular_file(
        Path(values["holder_receipt_ref"]), "holder terminal receipt"
    )
    for path_value, digest_key, label in (
        (owner_path, "owner_sha256", "return owner"),
        (handoff_path, "handoff_sha256", "handoff"),
        (holder_path, "holder_receipt_sha256", "holder terminal receipt"),
    ):
        if _sha256_bytes(path_value.read_bytes()) != values[digest_key]:
            raise ExternalCodexReturnError(f"canonical return route {label} digest has drifted")
    output_paths = [
        (_validate_output_path(Path(values["return_receipt_ref"]), "return receipt"), "return receipt"),
        (
            _validate_output_path(
                Path(values["authorization_ref"]), "terminal closure authorization"
            ),
            "terminal closure authorization",
        ),
        (
            _validate_output_path(Path(values["closure_receipt_ref"]), "closure receipt"),
            "closure receipt",
        ),
    ]
    _validate_distinct_output_paths(
        [
            (route_path, "canonical return route"),
            (owner_path, "return owner"),
            (handoff_path, "handoff"),
            (holder_path, "holder terminal receipt"),
            *output_paths,
        ]
    )
    return values


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


def _assert_expected_route_digest(
    args: argparse.Namespace,
    *,
    input_name: str,
    actual_digest: str,
    label: str,
) -> None:
    """Reassert a route-bound input digest after the return lock is held."""

    expected = getattr(args, f"expected_{input_name}_sha256", None)
    if expected is None:
        return
    if not isinstance(expected, str) or not _is_sha256_digest(expected):
        raise ExternalCodexReturnError(
            f"canonical return route {label} expected digest is invalid"
        )
    if actual_digest != expected:
        raise ExternalCodexReturnError(
            f"canonical return route {label} digest drifted at locked directed-input boundary"
        )


def _load_return_inputs(args: argparse.Namespace) -> dict[str, Any]:
    owner_path = _regular_file(Path(args.return_owner), "return owner")
    owner_value, owner_bytes = _load_json_file(owner_path, "return owner")
    owner_digest = _sha256_bytes(owner_bytes)
    _assert_expected_route_digest(
        args,
        input_name="owner",
        actual_digest=owner_digest,
        label="return owner",
    )
    owner = validate_return_owner(owner_value)
    handoff_path = _regular_file(Path(args.handoff), "handoff")
    holder_path = _regular_file(Path(args.holder_receipt), "holder receipt")
    closure_path = _validate_output_path(Path(args.closure_receipt), "closure receipt")
    handoff, handoff_bytes, handoff_digest, holder, holder_bytes, holder_digest = (
        _load_handoff_context(handoff_path, holder_path, closure_path)
    )
    _assert_expected_route_digest(
        args,
        input_name="handoff",
        actual_digest=handoff_digest,
        label="handoff",
    )
    _assert_expected_route_digest(
        args,
        input_name="holder_receipt",
        actual_digest=holder_digest,
        label="holder terminal receipt",
    )
    _validate_handoff_owner(handoff, owner)
    authorization_path = _validate_output_path(
        Path(args.authorization), "terminal closure authorization"
    )
    return_path = _validate_output_path(
        Path(args.return_receipt), "canonical return receipt"
    )
    attempt_path = _validate_output_path(
        _return_attempt_path(closure_path),
        "canonical return attempt reservation",
    )
    _validate_distinct_output_paths(
        [
            (authorization_path, "terminal closure authorization"),
            (closure_path, "closure receipt"),
            (return_path, "canonical return receipt"),
            (attempt_path, "canonical return attempt reservation"),
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
        "attempt_path": attempt_path,
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


def _load_authorized_return_receipt(
    inputs: dict[str, Any],
) -> tuple[Path, dict[str, Any]] | None:
    """Replay the immutable wake evidence when a caller changes output paths."""

    authorization = inputs.get("authorization")
    if authorization is None:
        return None
    if authorization.get("authorization_kind") != "wake_delivered":
        raise ExternalCodexReturnError(
            "existing closure authorization is not a canonical wake delivery"
        )
    evidence_ref = authorization.get("evidence_ref")
    if not isinstance(evidence_ref, str) or not evidence_ref.startswith("/"):
        raise ExternalCodexReturnError(
            "existing wake authorization lacks a canonical return receipt"
        )
    evidence_path = _regular_file(Path(evidence_ref), "canonical return evidence")
    receipt = _load_existing_return_receipt(
        evidence_path,
        owner=inputs["owner"],
        owner_path=inputs["owner_path"],
        owner_digest=inputs["owner_digest"],
        handoff_path=inputs["handoff_path"],
        handoff_digest=inputs["handoff_digest"],
    )
    return evidence_path, receipt


def _pause_binding(
    *, owner_path: Path, owner_digest: str, pause_path: Path
) -> dict[str, str]:
    return {
        "owner_ref": str(owner_path.resolve()),
        "owner_sha256": owner_digest,
        "pause_receipt_ref": str(pause_path.resolve()),
    }


def _pause_attempt_lock_root() -> Path:
    """Return one owner-private host coordinate for legacy Goal locks."""

    uid = os.getuid()
    runtime_parent = Path(f"/run/user/{uid}")
    if runtime_parent.is_symlink() or not runtime_parent.is_dir():
        runtime_parent = Path("/tmp")
    if runtime_parent.is_symlink() or not runtime_parent.is_dir():
        raise ExternalCodexReturnError(
            "Goal pause lock parent is not a real directory"
        )
    root = runtime_parent / f"aoa-external-codex-goal-pause-{uid}"
    try:
        root.mkdir(mode=0o700, exist_ok=True)
        observed = root.stat(follow_symlinks=False)
    except OSError as exc:
        raise ExternalCodexReturnError(
            f"Goal pause lock root cannot be prepared: {root}"
        ) from exc
    if (
        root.is_symlink()
        or not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != uid
        or stat.S_IMODE(observed.st_mode) & 0o077
    ):
        raise ExternalCodexReturnError(
            f"Goal pause lock root is not owner-private: {root}"
        )
    return root


def _pause_attempt_lock_path(owner: dict[str, Any]) -> Path:
    binding = {
        "schema_version": "abyss_stack_external_codex_pause_lock_v1",
        "owner_id": owner["owner_id"],
        "owner_repo": owner["owner_repo"],
        "goal_id": owner["goal_id"],
        "thread_id": owner["thread_id"],
    }
    digest = _sha256_bytes(_canonical_bytes(binding))
    return _pause_attempt_lock_root() / f"{digest}.lock"


@contextlib.contextmanager
def _pause_attempt_lock(owner: dict[str, Any]) -> Any:
    """Serialize legacy pauses by qualified Goal identity."""

    lock_path = _pause_attempt_lock_path(owner)
    _validate_output_path(lock_path, "Goal pause attempt lock")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise ExternalCodexReturnError(
            f"cannot open Goal pause attempt lock: {lock_path}"
        ) from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except OSError as exc:
        raise ExternalCodexReturnError(
            f"Goal pause attempt lock failed: {lock_path}"
        ) from exc
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _pause_reservation(
    path: Path, *, binding: dict[str, str]
) -> dict[str, Any]:
    if path.exists():
        value, raw = _load_json_file(path, "canonical Goal pause receipt")
        if raw != _canonical_bytes(value) + b"\n":
            raise ExternalCodexReturnError(
                "canonical Goal pause receipt is not canonically encoded"
            )
        _validate_pause_reservation_schema(value)
        if value.get("schema_version") != PAUSE_RESERVATION_SCHEMA_VERSION:
            raise ExternalCodexReturnError(
                "canonical Goal pause reservation schema mismatch"
            )
        if value.get("state") != "reserved":
            raise ExternalCodexReturnError(
                "canonical Goal pause receipt exists but is not a completed receipt"
            )
        for key, expected in binding.items():
            if value.get(key) != expected:
                raise ExternalCodexReturnError(
                    f"canonical Goal pause receipt reservation {key} mismatch"
                )
        return value
    reservation = {
        "schema_version": PAUSE_RESERVATION_SCHEMA_VERSION,
        "state": "reserved",
        "reserved_at": _utc_now(),
        "attempt_id": secrets.token_hex(16),
        **binding,
    }
    _validate_pause_reservation_schema(reservation)
    _write_new_json(path, reservation, "canonical Goal pause receipt reservation")
    return reservation


def _validate_pause_receipt(
    receipt: dict[str, Any],
    *,
    owner: dict[str, Any],
    owner_path: Path,
) -> dict[str, Any]:
    required_fields = {
        "schema_version",
        "generated_at",
        "owner_ref",
        "owner_sha256",
        "pause_receipt_ref",
        "owner",
        "transport",
        "goal_status",
        "goal_binding",
        "lifecycle_method",
        "lifecycle",
        "actions",
        "observed",
        "paused",
        "owner_acceptance",
        "semantic_acceptance",
    }
    missing_fields = sorted(required_fields - set(receipt))
    if missing_fields:
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt schema mismatch: missing "
            + ", ".join(missing_fields)
        )
    if receipt.get("schema_version") != PAUSE_RECEIPT_SCHEMA_VERSION:
        raise ExternalCodexReturnError("canonical Goal pause receipt schema mismatch")
    if receipt.get("paused") is not True:
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt does not prove a pause"
        )
    if receipt.get("owner_ref") != str(owner_path.resolve()):
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt owner identity mismatch"
        )
    if receipt.get("owner") != _owner_projection(owner):
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt owner binding mismatch"
        )
    if receipt.get("goal_status") != "paused":
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt Goal is not paused"
        )
    transport = receipt.get("transport")
    if (
        not isinstance(transport, dict)
        or set(transport) - {"kind", "endpoint", "resolution"}
        or transport.get("kind") != "codex_app_server_websocket_unix"
        or not isinstance(transport.get("endpoint"), str)
        or not transport["endpoint"].startswith("/")
        or not transport["endpoint"].strip()
        or (
            "resolution" in transport
            and (
                not isinstance(transport["resolution"], str)
                or not transport["resolution"].strip()
            )
        )
    ):
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt transport binding is incomplete"
        )
    owner_endpoint = _endpoint_from_owner(owner)
    if owner_endpoint is not None:
        try:
            expected_endpoint = str(_socket_path(owner_endpoint))
            observed_endpoint = str(_socket_path(transport["endpoint"]))
        except ExternalCodexReturnError as exc:
            raise ExternalCodexReturnError(
                "canonical Goal pause receipt transport endpoint is invalid"
            ) from exc
        if observed_endpoint != expected_endpoint:
            raise ExternalCodexReturnError(
                "canonical Goal pause receipt transport endpoint does not match "
                "the explicit pause owner binding"
            )
    goal_binding = receipt.get("goal_binding")
    if (
        not isinstance(goal_binding, dict)
        or goal_binding.get("goal_id") != owner["goal_id"]
        or goal_binding.get("thread_id") != owner["thread_id"]
        or goal_binding.get("before_status") != "active"
        or goal_binding.get("transition") != "active_to_paused"
        or not isinstance(goal_binding.get("identity_source"), str)
        or not goal_binding["identity_source"].strip()
    ):
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt Goal binding is incomplete"
        )
    lifecycle = receipt.get("lifecycle")
    actions = receipt.get("actions")
    observed = receipt.get("observed")
    precondition = lifecycle.get("precondition") if isinstance(lifecycle, dict) else None
    mutation_dispatched = (
        lifecycle.get("mutation_dispatched")
        if isinstance(lifecycle, dict)
        else None
    )
    transition_proof = (
        lifecycle.get("transition_proof") if isinstance(lifecycle, dict) else None
    )
    legacy_transition_proof = (
        isinstance(transition_proof, dict)
        and transition_proof.get("schema_version")
        == LEGACY_PAUSE_TRANSITION_PROOF_SCHEMA_VERSION
    )
    recovery = receipt.get("recovery")
    if (
        receipt.get("lifecycle_method") != "thread/goal/set"
        or not isinstance(lifecycle, dict)
        or lifecycle.get("accepted") is not True
        or lifecycle.get("response_available") not in {True, False}
        or not isinstance(lifecycle.get("initialize"), dict)
        or not isinstance(lifecycle.get("goal_get"), dict)
        or not isinstance(lifecycle.get("goal"), dict)
        or not _is_sha256_digest(lifecycle.get("goal_summary_sha256"))
        or (
            lifecycle.get("response_available") is True
            and not _is_sha256_digest(lifecycle.get("goal_response_sha256"))
        )
        or (
            lifecycle.get("response_available") is False
            and lifecycle.get("goal_response_sha256") is not None
        )
        or (
            not legacy_transition_proof
            and not isinstance(lifecycle.get("post_read"), dict)
        )
        or (
            not legacy_transition_proof
            and not _is_sha256_digest(lifecycle.get("post_read_response_sha256"))
        )
        or (
            not legacy_transition_proof
            and not isinstance(lifecycle.get("post_read_response"), dict)
        )
        or (
            not legacy_transition_proof
            and isinstance(lifecycle.get("post_read_response"), dict)
            and lifecycle.get("post_read_response_sha256")
            != _sha256_bytes(
                _canonical_bytes(lifecycle.get("post_read_response"))
            )
        )
        or (
            not legacy_transition_proof
            and "goal_response" not in lifecycle
        )
        or (
            not legacy_transition_proof
            and lifecycle.get("response_available") is True
            and not isinstance(lifecycle.get("goal_response"), dict)
        )
        or (
            not legacy_transition_proof
            and lifecycle.get("response_available") is False
            and lifecycle.get("goal_response") is not None
        )
        or (
            lifecycle.get("response_available") is False
            and recovery is None
        )
        or not isinstance(precondition, dict)
        or precondition.get("goal_status") != "active"
        or not isinstance(precondition.get("goal_get"), dict)
        or not isinstance(precondition.get("goal_response_sha256"), str)
        or not isinstance(mutation_dispatched, dict)
        or not isinstance(transition_proof, dict)
        or not isinstance(actions, dict)
        or actions.get("goal_lifecycle_set") is not True
        or not isinstance(observed, dict)
        or observed.get("goal_lifecycle") != "paused"
        or observed.get("goal_status") != "paused"
        or receipt.get("owner_acceptance") != "separate"
        or receipt.get("semantic_acceptance") != "separate"
    ):
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt lacks lifecycle evidence"
        )
    _validated_pause_precondition({"precondition": precondition}, owner=owner)
    if lifecycle.get("goal_get") != precondition.get("goal_get"):
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt active Goal summary does not match its precondition"
        )
    goal_summary = lifecycle.get("goal")
    goal_summary_status = (
        goal_summary.get("status")
        if isinstance(goal_summary, dict)
        else None
    )
    if goal_summary_status is None and isinstance(goal_summary, dict):
        nested_goal_summary = goal_summary.get("goal")
        if isinstance(nested_goal_summary, dict):
            goal_summary_status = nested_goal_summary.get("status")
    if (
        goal_summary_status != "paused"
        or lifecycle.get("goal_summary_sha256")
        != _sha256_bytes(_canonical_bytes(lifecycle.get("goal")))
    ):
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt paused Goal summary digest is invalid"
        )
    if not legacy_transition_proof:
        post_read_summary = lifecycle.get("post_read")
        post_read_status = (
            post_read_summary.get("status")
            if isinstance(post_read_summary, dict)
            else None
        )
        if post_read_status is None and isinstance(post_read_summary, dict):
            nested_post_read = post_read_summary.get("goal")
            if isinstance(nested_post_read, dict):
                post_read_status = nested_post_read.get("status")
        if post_read_status != "paused":
            raise ExternalCodexReturnError(
                "canonical Goal pause receipt post-read does not confirm a paused Goal"
            )
        post_read_response = lifecycle.get("post_read_response")
        if post_read_summary != _safe_response_summary(post_read_response):
            raise ExternalCodexReturnError(
                "canonical Goal pause receipt post-read summary is not bound to its raw response"
            )
        post_read_goal = _goal_object(post_read_response, "thread/goal/get")
        _validate_goal_binding(post_read_goal, owner)
        if _string_at(post_read_goal, ("status",)) != "paused":
            raise ExternalCodexReturnError(
                "canonical Goal pause receipt raw post-read does not confirm a paused Goal"
            )
    stored_goal_response = lifecycle.get("goal_response")
    if isinstance(stored_goal_response, dict):
        stored_goal = _goal_object(stored_goal_response, "thread/goal/set")
        _validate_goal_binding(stored_goal, owner)
        if _string_at(stored_goal, ("status",)) != "paused":
            raise ExternalCodexReturnError(
                "canonical Goal pause receipt raw mutation response does not confirm a paused Goal"
            )
    if recovery is not None:
        if (
            not isinstance(recovery, dict)
            or recovery.get("mode") != "ambiguous_post_mutation"
            or recovery.get("mutation_response_available")
            is not lifecycle.get("response_available")
            or recovery.get("reconciled_by") != "thread/goal/get"
            or not isinstance(recovery.get("mutation_dispatched"), dict)
            or recovery.get("mutation_dispatched") != mutation_dispatched
        ):
            raise ExternalCodexReturnError(
                "canonical Goal pause recovery evidence is incomplete"
            )
        _validated_pause_mutation(
            mutation_dispatched,
            owner=owner,
            attempt_id=mutation_dispatched.get("attempt_id")
            if isinstance(mutation_dispatched, dict)
            else None,
        )
    else:
        _validated_pause_mutation(
            mutation_dispatched,
            owner=owner,
            attempt_id=mutation_dispatched.get("attempt_id")
            if isinstance(mutation_dispatched, dict)
            else None,
        )
    validated_proof = _validated_pause_transition_proof(
        transition_proof,
        owner=owner,
        precondition=precondition,
        mutation=mutation_dispatched,
        goal_response=(
            stored_goal_response if isinstance(stored_goal_response, dict) else None
        ),
        expected_response_digest=lifecycle.get("goal_response_sha256"),
        expected_post_read_digest=(
            lifecycle.get("post_read_response_sha256")
            if not legacy_transition_proof
            else None
        ),
        post_read_response=(
            lifecycle.get("post_read_response")
            if not legacy_transition_proof
            else None
        ),
    )
    if validated_proof.get("goal_response_sha256") != lifecycle.get(
        "goal_response_sha256"
    ):
        raise ExternalCodexReturnError(
            "canonical Goal pause transition proof does not match its response"
        )
    if (
        not legacy_transition_proof
        and validated_proof.get("post_read_response_sha256")
        != lifecycle.get("post_read_response_sha256")
    ):
        raise ExternalCodexReturnError(
            "canonical Goal pause transition proof does not match its post-read"
        )
    _validate_pause_receipt_schema(receipt)
    return receipt


def _load_existing_pause_receipt(
    path: Path,
    *,
    owner: dict[str, Any],
    owner_path: Path,
    owner_digest: str,
) -> dict[str, Any]:
    value, raw = _load_json_file(path, "canonical Goal pause receipt")
    if raw != _canonical_bytes(value) + b"\n":
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt is not canonically encoded"
        )
    if value.get("pause_receipt_ref") != str(path.resolve()):
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt path identity mismatch"
        )
    if value.get("owner_sha256") != owner_digest:
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt owner digest mismatch"
        )
    return _validate_pause_receipt(
        value,
        owner=owner,
        owner_path=owner_path,
    )


def _call_visible(handler: Callable[[argparse.Namespace], int], args: argparse.Namespace) -> None:
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            result = handler(args)
    except Exception as exc:
        raise ExternalCodexReturnError(str(exc)) from exc
    if result != 0:
        raise ExternalCodexReturnError(f"visible lifecycle command failed: {handler.__name__}")


def _run_pause_bound(
    *,
    owner_path: Path,
    owner_bytes: bytes,
    owner_digest: str,
    owner: dict[str, Any],
    pause_path: Path,
) -> dict[str, Any]:
    binding = _pause_binding(
        owner_path=owner_path,
        owner_digest=owner_digest,
        pause_path=pause_path,
    )
    reservation: dict[str, Any]
    if pause_path.exists():
        existing, _existing_raw = _load_json_file(
            pause_path, "canonical Goal pause receipt"
        )
        if existing.get("state") == "reserved":
            reservation = _pause_reservation(pause_path, binding=binding)
        else:
            return _load_existing_pause_receipt(
                pause_path,
                owner=owner,
                owner_path=owner_path,
                owner_digest=owner_digest,
            )
    else:
        reservation = _pause_reservation(pause_path, binding=binding)

    VISIBLE._assert_file_snapshot(owner_path, owner_bytes, "pause owner")
    endpoint, resolution = discover_app_server_socket(owner)
    receipt = pause_goal(
        owner,
        owner_path,
        endpoint,
        owner_bytes=owner_bytes,
        reservation_path=pause_path,
        reservation=reservation,
    )
    receipt["transport"]["resolution"] = resolution
    receipt.update(binding)
    VISIBLE._assert_file_snapshot(owner_path, owner_bytes, "pause owner")
    _replace_json(pause_path, receipt, "canonical Goal pause receipt")
    VISIBLE._assert_file_snapshot(owner_path, owner_bytes, "pause owner")
    return _load_existing_pause_receipt(
        pause_path,
        owner=owner,
        owner_path=owner_path,
        owner_digest=owner_digest,
    )


def run_pause(args: argparse.Namespace) -> dict[str, Any]:
    """Run the bounded active-to-paused Goal lifecycle action."""

    owner_path = _regular_file(Path(args.pause_owner), "pause owner")
    owner_value, owner_bytes = _load_json_file(owner_path, "pause owner")
    owner_digest = _sha256_bytes(owner_bytes)
    owner = validate_pause_owner(owner_value)
    pause_path = _validate_output_path(
        Path(args.pause_receipt), "canonical Goal pause receipt"
    )
    if pause_path.resolve() == owner_path.resolve():
        raise ExternalCodexReturnError(
            "canonical Goal pause receipt must be distinct from pause owner"
        )
    with _pause_attempt_lock(owner):
        return _run_pause_bound(
            owner_path=owner_path,
            owner_bytes=owner_bytes,
            owner_digest=owner_digest,
            owner=owner,
            pause_path=pause_path,
        )


def run_return(args: argparse.Namespace) -> dict[str, Any]:
    inputs = _bind_return_attempt(_load_return_inputs(args))
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
    authorized_return = _load_authorized_return_receipt(inputs)
    receipt: dict[str, Any] | None = None
    if authorized_return is not None:
        evidence_path, receipt = authorized_return
        if return_path.resolve() != evidence_path.resolve() and return_path.exists():
            raise ExternalCodexReturnError(
                "canonical return receipt path differs from existing wake evidence"
            )
    if receipt is None and return_path.exists():
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
    elif receipt is None:
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


def _detached_paths(
    args: argparse.Namespace, *, return_path: Path | None = None
) -> tuple[Path, Path, Path]:
    return_path = return_path or Path(args.return_receipt)
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
    if state not in {"launch_reserved", "running", "completed", "failed", "stale"}:
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


def _reserve_detached_log(path: Path) -> None:
    """Create the detached log before fork so orphan launches remain recoverable."""

    _validate_output_path(path, "detached canonical return log")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except FileExistsError as exc:
        raise ExternalCodexReturnError(
            f"detached canonical return log already exists: {path}"
        ) from exc
    except OSError as exc:
        raise ExternalCodexReturnError(
            f"cannot reserve detached canonical return log: {path}"
        ) from exc


def _run_detached_child(
    args: argparse.Namespace,
    result_path: Path,
    log_path: Path,
    detached_path: Path,
    binding: dict[str, str],
    ready_fd: int,
) -> None:
    os.setsid()
    log_flags = os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_CLOEXEC"):
        log_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        log_flags |= os.O_NOFOLLOW
    descriptor = os.open(log_path, log_flags)
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
        with _return_attempt_lock(Path(args.closure_receipt)):
            response = run_return(args)
            print(json.dumps(response, ensure_ascii=False, sort_keys=True))
            return 0
    # The exact closure path is bound by the immutable handoff and is
    # invariant across alternate return-receipt paths and retry receipts.
    with _return_attempt_lock(Path(args.closure_receipt)) as lock:
        return _command_return_detached(args, lock)


def command_return_route(args: argparse.Namespace) -> int:
    """Run the canonical return from one pre-bound, digest-checked route."""

    route = _load_return_route(Path(args.route))
    return command_return(
        SimpleNamespace(
            return_owner=route["owner_ref"],
            handoff=route["handoff_ref"],
            holder_receipt=route["holder_receipt_ref"],
            return_receipt=route["return_receipt_ref"],
            authorization=route["authorization_ref"],
            closure_receipt=route["closure_receipt_ref"],
            expected_owner_sha256=route["owner_sha256"],
            expected_handoff_sha256=route["handoff_sha256"],
            expected_holder_receipt_sha256=route["holder_receipt_sha256"],
            detach=False,
            detached_receipt=None,
            detached_result=None,
            detached_log=None,
        )
    )


def command_pause(args: argparse.Namespace) -> int:
    response = run_pause(args)
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0


def command_goal_transition(args: argparse.Namespace) -> int:
    """Project one typed owner decision onto the current runtime adapter."""

    module_name = "goal_lifecycle_adapter"
    module = sys.modules.get(module_name)
    if module is None:
        path = Path(__file__).with_name("goal_lifecycle_adapter.py")
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ExternalCodexReturnError(
                "cannot load the Goal lifecycle runtime adapter"
            )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

    bind_runtime = getattr(module, "bind_runtime_namespace", None)
    if callable(bind_runtime):
        # The installed return entrypoint uses runpy, so the executing
        # runtime is a namespace rather than a sys.modules module.  Pass that
        # live namespace to the adapter and preserve one exception identity.
        bind_runtime(globals())

    response = module.run_goal_transition(args)
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0


def _command_return_detached(
    args: argparse.Namespace, lock: _ReturnAttemptLock
) -> int:
    inputs = _bind_return_attempt(_load_return_inputs(args))
    detached_path, result_path, log_path = _detached_paths(
        args, return_path=inputs["return_path"]
    )
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
            if result_path.exists() or (
                log_path.exists() and state != "launch_reserved"
            ):
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
    launch_reservation = {
        "schema_version": DETACHED_SCHEMA_VERSION,
        "state": "launch_reserved",
        "created_at": _utc_now(),
        **binding,
    }
    _write_new_json(
        detached_path,
        launch_reservation,
        "detached return launch reservation",
    )
    _reserve_detached_log(log_path)
    ready_read, ready_write = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:
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
        _replace_json(detached_path, receipt, "detached return receipt")
        lock.transferred_to_detached_child = True
        os.write(ready_write, b"\x01")
    finally:
        os.close(ready_write)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description=(
            "Run an explicit external Codex Goal lifecycle action or deliver a "
            "handoff and close only its supplied visible holder."
        )
    )
    subcommands = root.add_subparsers(dest="command", required=True)
    pause_parser = subcommands.add_parser(
        "pause",
        help="pause the exact active Goal without waking or closing a holder",
    )
    pause_parser.add_argument("--pause-owner", required=True)
    pause_parser.add_argument("--pause-receipt", required=True)
    pause_parser.set_defaults(handler=command_pause)
    transition_parser = subcommands.add_parser(
        "goal-transition",
        aliases=["transition"],
        help=(
            "execute one accepted typed Goal lifecycle request through the "
            "current runtime adapter"
        ),
    )
    transition_parser.add_argument("--request", required=True)
    transition_parser.add_argument("--decision", required=True)
    transition_parser.add_argument("--owner", required=True)
    transition_parser.add_argument("--receipt", required=True)
    transition_parser.set_defaults(handler=command_goal_transition)
    route_parser = subcommands.add_parser(
        "return-route",
        help="deliver and close from one exact digest-bound return route",
    )
    route_parser.add_argument("--route", required=True)
    route_parser.set_defaults(handler=command_return_route)
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
