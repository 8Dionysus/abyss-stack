#!/usr/bin/env python3
"""Durable runtime-owner controller for one external Codex incarnation.

The controller launches Codex as a distinct operating-system process. It never
uses Codex's built-in subagent transport. Exact aoa-sdk plan and incarnation
objects are validated before launch; runtime state and normalized events stay
under an explicit state root.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import http.client
import http.server
import json
import os
import re
import selectors
import secrets
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator, FormatChecker

from aoa_sdk.contracts.control_plane import ProvenanceRef, RunPlan
from aoa_sdk.contracts.incarnation import (
    AgentIncarnationBinding,
    AgentIncarnationBindingV2,
)
from aoa_sdk.control_plane.incarnation import (
    assert_agent_incarnation_binding_matches_plan,
)

PART_ROOT = Path(__file__).resolve().parent
if str(PART_ROOT) not in sys.path:
    sys.path.insert(0, str(PART_ROOT))
from external_codex_projection import (  # noqa: E402
    ProjectionError,
    build_actor_delta,
    build_actor_manifest,
    build_actor_manifest_from_descriptor,
    materialize_actor_projection,
    materialize_actor_projection_from_seed,
    remove_actor_projection,
)
from external_codex_nested_evidence import (  # noqa: E402
    NestedEvidenceNamespaceError,
    build_nested_evidence_namespace,
    nested_evidence_namespace_digest,
)

PROFILE_PATH = PART_ROOT / "runtime-profile.v1.json"
SUPERVISOR_PATH = PART_ROOT / "external_codex_supervisor.py"
MOUNT_LAUNCHER_PATH = PART_ROOT / "external_codex_mount_launcher.py"
ACTOR_EXECUTION_ROOT = Path("/tmp/aoa-external-actor-workspace")
SCHEMA_ROOT = PART_ROOT / "schemas"
LAUNCH_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-launch.schema.json"
TASK_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-task.schema.json"
PROFILE_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-runtime-profile.schema.json"
REPORT_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-report.schema.json"
EVENT_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-event.schema.json"
RESULT_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-result.schema.json"
RESULT_EVIDENCE_CLOSURE_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-result-evidence-closure.schema.json"
)
RESUME_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-resume.schema.json"
STATE_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-state.schema.json"
PARENT_OBLIGATION_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-parent-obligation.schema.json"
)
PARENT_YIELD_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-parent-yield.schema.json"
PARENT_REENTRY_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-parent-reentry.schema.json"
REENTRY_STATE_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-reentry-state.schema.json"
WORKSPACE_MANIFEST_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-workspace-manifest.schema.json"
)
ACTOR_MANIFEST_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-actor-workspace-manifest.schema.json"
)
ACTOR_DELTA_SCHEMA_PATH = SCHEMA_ROOT / "external-codex-actor-delta.schema.json"
REVIEW_SEED_ENVELOPE_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-review-seed-envelope.schema.json"
)
ACTOR_INPUT_ENVELOPE_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-actor-input-envelope.schema.json"
)
NESTED_EVIDENCE_NAMESPACE_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-nested-evidence-namespace.schema.json"
)
SDK_SUMMON_REQUEST_SCHEMA_REF = (
    "mechanics/checkpoint/parts/child-task-reentry/schemas/"
    "summon-request-v4.schema.json"
)
SDK_SUMMON_REQUEST_SCHEMA_VERSION = "urn:aoa-sdk:a2a:summon-request:v4"

IncarnationBinding = AgentIncarnationBinding | AgentIncarnationBindingV2

LEGACY_STATE_SCHEMA_VERSION = "abyss_stack_external_codex_runtime_state_v1"
LEGACY_STATE_V2_SCHEMA_VERSION = "abyss_stack_external_codex_runtime_state_v2"
STATE_SCHEMA_VERSION = "abyss_stack_external_codex_runtime_state_v3"
RESPONSE_SCHEMA_VERSION = "abyss_stack_external_codex_response_v1"
LEGACY_REENTRY_STATE_SCHEMA_VERSION = "abyss_stack_external_codex_reentry_state_v1"
REENTRY_STATE_SCHEMA_VERSION = "abyss_stack_external_codex_reentry_state_v2"
MAX_CONTROL_BYTES = 16 * 1024 * 1024
MAX_ROLE_BYTES = 2 * 1024 * 1024
MAX_EVENT_LINE_BYTES = 8 * 1024 * 1024
MAX_MCP_PROXY_REQUEST_BYTES = 16 * 1024 * 1024
MAX_JSON_ESCAPE_LAYERS = 32
MCP_PROXY_CONNECT_TIMEOUT_SECONDS = 15
SHELL_NESTING_INSPECTION_LIMIT = 4
FOREGROUND_OBSERVATION_INTERVAL_SECONDS = 0.25
NESTED_EVIDENCE_ENV = "AOA_EXTERNAL_CODEX_NESTED_EVIDENCE"
TERMINAL_STATES = {
    "completed",
    "failed",
    "interrupted",
    "paused",
    "review_required",
    "authority_blocked",
}


class _ThreadingMcpProxyServer(http.server.ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._accepted_lock = threading.Lock()
        self._accepted_requests: set[socket.socket] = set()
        super().__init__(*args, **kwargs)

    def get_request(self) -> tuple[socket.socket, Any]:
        request, address = super().get_request()
        with self._accepted_lock:
            self._accepted_requests.add(request)
        return request, address

    def shutdown_request(self, request: socket.socket) -> None:
        try:
            super().shutdown_request(request)
        finally:
            with self._accepted_lock:
                self._accepted_requests.discard(request)

    def close_accepted_requests(self) -> None:
        with self._accepted_lock:
            accepted_requests = tuple(self._accepted_requests)
        for request in accepted_requests:
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                request.close()
            except OSError:
                pass


class _McpCredentialProxy:
    """Attempt-local loopback proxy that keeps the upstream bearer out of Codex."""

    def __init__(self, server: Mapping[str, Any], bearer_token: str) -> None:
        parsed = urllib.parse.urlsplit(str(server["url"]))
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ExternalCodexRuntimeError(
                "mcp_proxy_upstream_invalid",
                "role-scoped MCP proxy requires one exact loopback HTTP upstream",
            )
        self._upstream_host = parsed.hostname
        self._upstream_port = parsed.port
        self._upstream_path = parsed.path or "/"
        self._bearer_token = bearer_token
        self._capability_path = "/mcp/" + secrets.token_urlsafe(32)
        self._close_lock = threading.Lock()
        self._relay_lock = threading.Lock()
        self._active_relay_sockets: set[socket.socket] = set()
        self._closed = False
        proxy = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(15)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def _proxy(self) -> None:
                response_started = False
                request_path = urllib.parse.urlsplit(self.path).path
                if request_path != proxy._capability_path:
                    self.send_error(404)
                    return
                transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
                if transfer_encoding and transfer_encoding != "identity":
                    self.send_error(400, "chunked proxy requests are unsupported")
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self.send_error(400, "invalid content length")
                    return
                if length < 0 or length > MAX_MCP_PROXY_REQUEST_BYTES:
                    self.send_error(413)
                    return
                body = self.rfile.read(length) if length else None
                # Header and request-body admission is bounded. Once admitted,
                # downstream response consumption remains Codex-owned just as
                # the upstream MCP response duration does.
                self.connection.settimeout(None)
                headers = {
                    key: value
                    for key, value in self.headers.items()
                    if key.lower()
                    not in {
                        "authorization",
                        "connection",
                        "content-length",
                        "host",
                        "proxy-authorization",
                        "transfer-encoding",
                    }
                }
                headers["Connection"] = "close"
                upstream = http.client.HTTPConnection(
                    proxy._upstream_host,
                    proxy._upstream_port,
                    timeout=MCP_PROXY_CONNECT_TIMEOUT_SECONDS,
                )
                relay_sockets: tuple[socket.socket, ...] = ()
                try:
                    # Bound only establishment of the fixed loopback hop. MCP
                    # tool and streaming response duration remains Codex-owned.
                    upstream.connect()
                    if upstream.sock is not None:
                        upstream.sock.settimeout(None)
                    relay_sockets = tuple(
                        sock
                        for sock in (self.connection, upstream.sock)
                        if sock is not None
                    )
                    bearer_token = proxy._register_relay(relay_sockets)
                    if bearer_token is None:
                        raise OSError("attempt-local MCP credential proxy is closing")
                    headers["Authorization"] = f"Bearer {bearer_token}"
                    upstream.request(
                        self.command,
                        proxy._upstream_path,
                        body=body,
                        headers=headers,
                    )
                    response = upstream.getresponse()
                    self.send_response(response.status, response.reason)
                    for key, value in response.getheaders():
                        if key.lower() not in {
                            "connection",
                            "content-length",
                            "keep-alive",
                            "proxy-authenticate",
                            "proxy-authorization",
                            "te",
                            "trailer",
                            "transfer-encoding",
                            "upgrade",
                        }:
                            self.send_header(key, value)
                    self.send_header("Connection", "close")
                    # From this point forward an end_headers() write may be
                    # partially visible. Never append a second status line.
                    response_started = True
                    self.end_headers()
                    while True:
                        chunk = response.read1(65_536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (OSError, http.client.HTTPException):
                    if not response_started and not self.wfile.closed:
                        try:
                            self.send_error(502)
                        except OSError:
                            pass
                finally:
                    proxy._unregister_relay(relay_sockets)
                    upstream.close()
                    self.close_connection = True

            do_GET = _proxy
            do_POST = _proxy
            do_DELETE = _proxy

        try:
            self._server = _ThreadingMcpProxyServer(("127.0.0.1", 0), Handler)
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "mcp_credential_proxy_unavailable",
                "cannot bind the attempt-local MCP credential proxy",
            ) from exc
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="aoa-mcp-credential-proxy",
            daemon=True,
        )

    @property
    def endpoint_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}{self._capability_path}"

    def start(self) -> None:
        try:
            self._thread.start()
        except BaseException:
            self._server.server_close()
            self._bearer_token = ""
            self._closed = True
            raise

    def _register_relay(
        self,
        relay_sockets: Sequence[socket.socket],
    ) -> str | None:
        with self._relay_lock:
            if self._closed:
                return None
            self._active_relay_sockets.update(relay_sockets)
            return self._bearer_token

    def _unregister_relay(
        self,
        relay_sockets: Sequence[socket.socket],
    ) -> None:
        with self._relay_lock:
            self._active_relay_sockets.difference_update(relay_sockets)

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            with self._relay_lock:
                self._closed = True
                self._bearer_token = ""
                active_sockets = tuple(self._active_relay_sockets)
            # Stop accepting before taking the complete accepted-socket
            # snapshot. This includes clients stalled before request parsing,
            # which cannot yet have registered as authenticated relays.
            self._server.shutdown()
            self._server.close_accepted_requests()
            for active_socket in active_sockets:
                try:
                    active_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    active_socket.close()
                except OSError:
                    pass
            self._server.server_close()
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise ExternalCodexRuntimeError(
                    "mcp_credential_proxy_close_incomplete",
                    "attempt-local MCP credential proxy did not terminate",
                )
            with self._relay_lock:
                self._active_relay_sockets.clear()


def _start_mcp_credential_proxies(
    tool_entry: Mapping[str, Any],
) -> tuple[list[_McpCredentialProxy], dict[str, str]]:
    proxies: list[_McpCredentialProxy] = []
    endpoints: dict[str, str] = {}
    try:
        for server in tool_entry["mcp_server_configs"]:
            token_name = str(server["bearer_token_env_var"])
            token = BROKERED_MCP_CREDENTIALS.get(token_name) or os.environ.get(
                token_name
            )
            if not token:
                raise ExternalCodexRuntimeError(
                    "mcp_credential_unavailable",
                    f"required role-scoped MCP credential is unavailable: {token_name}",
                )
            proxy = _McpCredentialProxy(server, token)
            proxy.start()
            proxies.append(proxy)
            endpoints[str(server["server_id"])] = proxy.endpoint_url
    except BaseException:
        for proxy in reversed(proxies):
            proxy.close()
        raise
    return proxies, endpoints


def _close_mcp_credential_proxies(proxies: list[_McpCredentialProxy]) -> None:
    """Expire every attempt-local relay before publishing terminal state."""

    for proxy in reversed(proxies):
        proxy.close()
    proxies.clear()


def _load_brokered_mcp_credentials() -> dict[str, str]:
    """Consume credentials carried across the clean launcher re-exec.

    The descriptor number is public coordination metadata. Bearer bytes never
    re-enter this process's exec-time environment and therefore are not
    recoverable through ``/proc/<pid>/environ`` by the actor.
    """

    raw_descriptor = os.environ.pop(
        "AOA_EXTERNAL_CODEX_MCP_CREDENTIALS_FD",
        None,
    )
    if raw_descriptor is None:
        return {}
    try:
        descriptor = int(raw_descriptor)
    except ValueError as exc:
        raise ExternalCodexRuntimeError(
            "mcp_credential_broker_invalid",
            "brokered MCP credential descriptor is invalid",
        ) from exc
    if descriptor < 3:
        raise ExternalCodexRuntimeError(
            "mcp_credential_broker_invalid",
            "brokered MCP credential descriptor is reserved",
        )
    try:
        observed = os.fstat(descriptor)
        required_seals = (
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE
        )
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_size <= 0
            or observed.st_size > 256 * 1024
            or fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & required_seals
            != required_seals
        ):
            raise ExternalCodexRuntimeError(
                "mcp_credential_broker_invalid",
                "brokered MCP credential descriptor is not one bounded sealed file",
            )
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = os.read(descriptor, observed.st_size + 1)
        if len(raw) != observed.st_size:
            raise ExternalCodexRuntimeError(
                "mcp_credential_broker_invalid",
                "brokered MCP credential bytes are incomplete",
            )
        payload = json.loads(raw)
    except ExternalCodexRuntimeError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalCodexRuntimeError(
            "mcp_credential_broker_invalid",
            "brokered MCP credential payload is unavailable",
        ) from exc
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
    if (
        not isinstance(payload, dict)
        or not payload
        or any(
            re.fullmatch(r"AOA_[A-Z0-9_]+_MCP_READ_BEARER_TOKEN", key) is None
            or not isinstance(value, str)
            or not value
            for key, value in payload.items()
        )
    ):
        raise ExternalCodexRuntimeError(
            "mcp_credential_broker_invalid",
            "brokered MCP credential payload has an unsupported shape",
        )
    return {str(key): str(value) for key, value in payload.items()}


BROKERED_MCP_CREDENTIALS = _load_brokered_mcp_credentials()


RESUMABLE_STATES = {"paused", "interrupted", "review_required", "authority_blocked"}
REVIEW_REPORT_RECOVERY_FAILURES = {
    "model_report_identity_mismatch",
    "model_report_transition_mismatch",
}
WRITER_REPORT_RECOVERY_FAILURE_PREFIX = "model_report_"
PROVIDER_CAPACITY_FAILURE_CODES = {
    "provider_capacity_unavailable",
    # Releases before ABYSS-STACK-D-0119 collapsed a structured usage-limit
    # event into this generic process code.  The legacy code is admissible
    # only when the exact attempt event artifact independently proves the
    # provider-capacity terminal pair.
    "codex_process_failed",
}
CODEX_CHATGPT_USAGE_LIMIT_RE = re.compile(
    r"\AYou've hit your usage limit\. Visit "
    r"https://chatgpt\.com/codex/settings/usage to purchase more credits "
    r"or try again at [^\r\n]{1,256}\.\Z"
)
SECRET_ENV_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.I)
SOURCE_LINE_ANCHOR_RE = re.compile(
    r"^L(?P<start>[1-9][0-9]*)(?:-L(?P<end>[1-9][0-9]*))?$"
)
INPUT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHELL_NAMES = {"bash", "dash", "sh", "zsh"}
SHELL_SEPARATORS = {"&", "&&", ";", "|", "||"}
SHELL_REDIRECTION_CHARS = frozenset("<>")
PARENT_PASSIVE_ITEM_TYPES = {"agent_message", "reasoning"}
ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", re.S)
SECRET_PATH_PARTS = {
    ".aws",
    ".docker",
    ".gnupg",
    ".kube",
    ".ssh",
    "credential",
    "credentials",
    "secret",
    "secrets",
}


def _codex_provider_capacity_failure_message(path: Path) -> str | None:
    """Return one exact structured ChatGPT usage-limit terminal message.

    Capacity recovery is based on Codex JSONL protocol records, never stderr,
    model-authored text, or a loose substring.  The admitted shape is the
    paired top-level ``error`` followed immediately by terminal
    ``turn.failed`` with the identical bounded provider message.
    """

    if not path.is_file() or path.is_symlink():
        return None
    previous: Mapping[str, Any] | None = None
    current: Mapping[str, Any] | None = None
    try:
        with path.open("rb") as handle:
            while True:
                line = handle.readline(MAX_EVENT_LINE_BYTES + 1)
                if not line:
                    break
                if len(line) > MAX_EVENT_LINE_BYTES:
                    return None
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    return None
                previous, current = current, payload
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(previous, Mapping) or not isinstance(current, Mapping):
        return None
    error_message = previous.get("message")
    failed_error = current.get("error")
    failed_message = (
        failed_error.get("message") if isinstance(failed_error, Mapping) else None
    )
    if (
        previous.get("type") != "error"
        or current.get("type") != "turn.failed"
        or not isinstance(error_message, str)
        or failed_message != error_message
        or CODEX_CHATGPT_USAGE_LIMIT_RE.fullmatch(error_message) is None
    ):
        return None
    return error_message


def _verified_result_attempt_capacity_failure(
    previous_result: Mapping[str, Any], attempt_dir: Path
) -> str | None:
    """Verify that one result binds the exact capacity-failed attempt stream."""

    raw_events_path = attempt_dir / "codex-events.jsonl"
    references = previous_result.get("evidence_refs")
    if not isinstance(references, list):
        return None
    matching = [
        item
        for item in references
        if isinstance(item, Mapping)
        and item.get("owner_repo") == "abyss-stack"
        and item.get("artifact_ref") == str(raw_events_path)
        and isinstance(item.get("artifact_digest"), str)
    ]
    if (
        len(matching) != 1
        or not raw_events_path.is_file()
        or raw_events_path.is_symlink()
    ):
        return None
    if sha256_file(raw_events_path) != matching[0]["artifact_digest"]:
        return None
    return _codex_provider_capacity_failure_message(raw_events_path)


def _plan_binds_active_summon_request(
    plan: RunPlan, request_ref: ProvenanceRef
) -> bool:
    """Accept the typed A2A slot or the exact domain-scenario input slot."""

    typed = [
        item.artifact_ref
        for item in plan.scenario_binding.input_artifact_bindings
        if item.artifact_kind == "summon_request"
    ]
    if typed:
        return typed == [request_ref]
    generic = [item for item in plan.scenario_binding.input_refs if item == request_ref]
    return generic == [request_ref]


SECRET_FILE_NAMES = {
    ".env",
    ".envrc",
    ".git-credentials",
    ".gitcookies",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".yarnrc",
    ".yarnrc.yml",
    "auth.json",
    "credentials.json",
    "id_dsa",
    "id_ed25519",
    "id_ecdsa",
    "id_rsa",
}
SECRET_FILE_TOKEN_RE = re.compile(
    r"(?:^|[._-])(?:api[-_]?key|client[-_]?secret|credential|credentials|"
    r"password|passwd|secret|secrets|token|tokens)(?:[._-]|$)",
    re.I,
)
RUNTIME_WIDE_FORBIDDEN_EFFECTS = frozenset(
    {
        "commit",
        "push",
        "pull_request",
        "merge",
        "tag",
        "release",
        "publication",
        "service_mutation",
        "secret_access",
        "global_config_mutation",
    }
)
OPAQUE_EFFECT_EXECUTABLES = {
    "awk",
    "deno",
    "gawk",
    "lua",
    "mawk",
    "nawk",
    "node",
    "perl",
    "php",
    "python",
    "python3",
    "ruby",
}
GIT_CONFIG_DRIVEN_HELPER_SUBCOMMANDS = frozenset(
    {
        "blame",
        "diff",
        "diff-files",
        "diff-index",
        "diff-tree",
        "fetch",
        "format-patch",
        "grep",
        "init",
        "log",
        "ls-remote",
        "notes",
        "range-diff",
        "show",
        "status",
        "verify-commit",
        "verify-tag",
    }
)
GIT_FILTER_RUNNING_SUBCOMMANDS = frozenset(
    {
        "add",
        "am",
        "apply",
        "checkout",
        "cherry-pick",
        "clone",
        "commit",
        "merge",
        "pull",
        "read-tree",
        "rebase",
        "reset",
        "restore",
        "sparse-checkout",
        "switch",
        "update-index",
        "worktree",
    }
)
GIT_HIDDEN_STATE_MUTATOR_SUBCOMMANDS = frozenset(
    {
        "bisect",
        "branch",
        "merge-tree",
        "mktree",
        "write-tree",
    }
)
CLASSIFIABLE_DIRECT_EXECUTABLES = frozenset(
    {
        "basename",
        "bash",
        "cat",
        "chmod",
        "cmp",
        "command",
        "cp",
        "cut",
        "date",
        "dash",
        "diff",
        "dirname",
        "du",
        "echo",
        "env",
        "exec",
        "false",
        "file",
        "find",
        "git",
        "grep",
        "head",
        "jq",
        "ls",
        "mkdir",
        "mv",
        "printf",
        "pwd",
        "readlink",
        "realpath",
        "rg",
        "rm",
        "rmdir",
        "sed",
        "sh",
        "sort",
        "stat",
        "tail",
        "tee",
        "timeout",
        "touch",
        "true",
        "uname",
        "uniq",
        "wc",
        "zsh",
    }
)
GENERIC_GIT_METADATA_MUTATORS = frozenset(
    {
        "chmod",
        "cp",
        "install",
        "ln",
        "mkdir",
        "mv",
        "rm",
        "rmdir",
        "sed",
        "tee",
        "touch",
    }
)
DIRECT_GIT_CONFIG_READERS = frozenset(
    {
        "base64",
        "cat",
        "cmp",
        "cut",
        "diff",
        "file",
        "head",
        "sort",
        "stat",
        "tail",
        "uniq",
        "wc",
    }
)
DIRECT_READER_VALUE_OPTIONS = {
    "base64": {"-w": ("--wrap", False)},
    "cat": {},
    "cmp": {
        "-i": ("--ignore-initial", False),
        "-n": ("--bytes", False),
    },
    "cut": {
        "-b": ("--bytes", False),
        "-c": ("--characters", False),
        "-d": ("--delimiter", False),
        "-f": ("--fields", False),
        "": ("--output-delimiter", False),
    },
    "diff": {
        "-F": ("--show-function-line", False),
        "-I": ("--ignore-matching-lines", False),
        "-L": ("--label", False),
        "-S": ("--starting-file", False),
        "-W": ("--width", False),
        "-X": ("--exclude-from", True),
        "": ("--exclude", False),
        "from": ("--from-file", True),
        "horizon": ("--horizon-lines", False),
        "palette": ("--palette", False),
        "tabsize": ("--tabsize", False),
        "to": ("--to-file", True),
    },
    "file": {
        "-e": ("--exclude", False),
        "-f": ("--files-from", True),
        "-F": ("--separator", False),
        "-m": ("--magic-file", True),
        "-P": ("--parameter", False),
    },
    "head": {
        "-c": ("--bytes", False),
        "-n": ("--lines", False),
    },
    "sort": {
        "-k": ("--key", False),
        "-o": ("--output", False),
        "-S": ("--buffer-size", False),
        "-T": ("--temporary-directory", False),
        "-t": ("--field-separator", False),
        "batch": ("--batch-size", False),
        "compress": ("--compress-program", False),
        "": ("--files0-from", True),
        "parallel": ("--parallel", False),
        "random": ("--random-source", True),
    },
    "stat": {
        "-c": ("--format", False),
        "": ("--printf", False),
    },
    "tail": {
        "-c": ("--bytes", False),
        "-n": ("--lines", False),
        "-s": ("--sleep-interval", False),
        "": ("--pid", False),
        "unchanged": ("--max-unchanged-stats", False),
    },
    "uniq": {
        "-f": ("--skip-fields", False),
        "-s": ("--skip-chars", False),
        "-w": ("--check-chars", False),
    },
    "wc": {"": ("--files0-from", True)},
}
PATTERN_GIT_CONFIG_READERS = frozenset({"grep", "rg", "sed"})
SAFE_GIT_BOOLEAN_CONFIG_KEYS = (
    "core.filemode",
    "core.ignorecase",
    "core.precomposeunicode",
    "core.sparsecheckout",
    "core.sparsecheckoutcone",
    "core.symlinks",
    "extensions.relativeworktrees",
    "extensions.worktreeconfig",
)
SAFE_GIT_ENUM_CONFIG_KEYS = {
    "extensions.compatobjectformat": frozenset({"sha1", "sha256"}),
    "extensions.objectformat": frozenset({"sha1", "sha256"}),
    "extensions.refstorage": frozenset({"files", "reftable"}),
}
CODEX_EXECUTABLE_PATH = "/usr/local/bin:/usr/bin:/bin"
MOUNT_WRAPPER_PATH = Path("/usr/bin/bwrap")
OPAQUE_PROCESS_LAUNCH_WRAPPERS = {
    "chrt",
    "ionice",
    "nice",
    "nohup",
    "nsenter",
    "prlimit",
    "setsid",
    "stdbuf",
    "taskset",
    "unshare",
}
OPAQUE_BUILD_AND_TASK_RUNNERS = {
    "ant",
    "bazel",
    "buck",
    "bundle",
    "cargo",
    "cmake",
    "composer",
    "ctest",
    "dotnet",
    "gmake",
    "go",
    "gradle",
    "gradlew",
    "just",
    "make",
    "meson",
    "mvn",
    "mvnw",
    "ninja",
    "nox",
    "npm",
    "npx",
    "pip",
    "pip3",
    "pnpm",
    "poetry",
    "pre-commit",
    "pytest",
    "rake",
    "task",
    "tox",
    "uv",
    "yarn",
}
GIT_DIRECT_BUILTIN_SUBCOMMANDS = {
    "add",
    "am",
    "apply",
    "bisect",
    "blame",
    "branch",
    "cat-file",
    "check-attr",
    "check-ignore",
    "check-ref-format",
    "checkout",
    "cherry",
    "cherry-pick",
    "clean",
    "clone",
    "commit",
    "config",
    "describe",
    "diff",
    "diff-files",
    "diff-index",
    "diff-tree",
    "fetch",
    "for-each-ref",
    "format-patch",
    "fsck",
    "grep",
    "hash-object",
    "init",
    "log",
    "ls-files",
    "ls-remote",
    "ls-tree",
    "merge",
    "merge-base",
    "merge-tree",
    "mktree",
    "mv",
    "name-rev",
    "notes",
    "pull",
    "push",
    "range-diff",
    "read-tree",
    "rebase",
    "reflog",
    "remote",
    "reset",
    "restore",
    "rev-list",
    "rev-parse",
    "rm",
    "show",
    "show-branch",
    "show-ref",
    "sparse-checkout",
    "status",
    "switch",
    "symbolic-ref",
    "tag",
    "update-index",
    "verify-commit",
    "verify-pack",
    "verify-tag",
    "worktree",
    "write-tree",
}
GIT_OPAQUE_GLOBAL_OPTIONS = {
    "-C",
    "-c",
    "-p",
    "--config-env",
    "--exec-path",
    "--git-dir",
    "--namespace",
    "--paginate",
    "--super-prefix",
    "--work-tree",
}
SYSTEM_PATH_PREFIXES = ("/etc", "/opt", "/usr", "/var/lib", "/var/run")
CODEX_MINIMAL_READ_ROOTS = tuple(
    Path(value)
    for value in (
        "/bin",
        "/sbin",
        "/usr",
        "/etc",
        "/lib",
        "/lib64",
        "/nix/store",
        "/run/current-system/sw",
    )
)
TRUSTED_EXECUTABLE_PREFIXES = (
    Path("/bin"),
    Path("/sbin"),
    Path("/usr/bin"),
    Path("/usr/sbin"),
    Path("/usr/local/bin"),
    Path("/usr/local/sbin"),
)
ACTOR_MANIFEST_TRANSIENT_ATTEMPTS = 3
ACTOR_MANIFEST_TRANSIENT_RETRY_SECONDS = 0.02
ACTOR_MANIFEST_TRANSIENT_ERRORS = (
    "actor projection directory disappeared before enumeration:",
    "changed while being read:",
    "changed while being inventoried:",
)


class ExternalCodexRuntimeError(RuntimeError):
    """One fail-closed external-agent runtime error with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _checked_actor_manifest(
    projection_root: str | Path,
    *,
    source_manifest_digest: str,
    source_git_head: str,
    projection_fd: int | None = None,
) -> dict[str, Any]:
    """Translate projection inventory failures into runtime-owned errors."""

    for attempt in range(ACTOR_MANIFEST_TRANSIENT_ATTEMPTS):
        try:
            if projection_fd is None:
                return build_actor_manifest(
                    projection_root,
                    source_manifest_digest=source_manifest_digest,
                    source_git_head=source_git_head,
                )
            return build_actor_manifest_from_descriptor(
                projection_fd,
                workspace_path=projection_root,
                source_manifest_digest=source_manifest_digest,
                source_git_head=source_git_head,
            )
        except ProjectionError as exc:
            message = str(exc)
            transient = any(
                marker in message for marker in ACTOR_MANIFEST_TRANSIENT_ERRORS
            )
            if transient and attempt + 1 < ACTOR_MANIFEST_TRANSIENT_ATTEMPTS:
                time.sleep(ACTOR_MANIFEST_TRANSIENT_RETRY_SECONDS)
                continue
            raise ExternalCodexRuntimeError(
                "actor_projection_observation_gap",
                message,
            ) from exc
    raise AssertionError("actor manifest retry loop exhausted without a result")


def _assert_descriptor_coordinate(projection_fd: int, projection_root: Path) -> None:
    """Prove that a durable pathname still names the exact open projection."""

    try:
        descriptor_stat = os.fstat(projection_fd)
        coordinate_stat = os.stat(projection_root, follow_symlinks=False)
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "actor_projection_coordinate_drift",
            "runtime-owned actor projection coordinate became unavailable",
        ) from exc
    if (
        not stat.S_ISDIR(coordinate_stat.st_mode)
        or descriptor_stat.st_dev != coordinate_stat.st_dev
        or descriptor_stat.st_ino != coordinate_stat.st_ino
    ):
        raise ExternalCodexRuntimeError(
            "actor_projection_coordinate_drift",
            "runtime-owned actor projection pathname no longer names its open inode",
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "artifact_unavailable", f"cannot hash runtime coordinate: {path}"
        ) from exc
    return "sha256:" + digest.hexdigest()


def canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(raw)


def owner_object_digest(value: Mapping[str, Any], digest_field: str) -> str:
    """Recompute an owner object's semantic digest without conflating raw bytes."""

    candidate = dict(value)
    candidate[digest_field] = "sha256:" + "0" * 64
    raw = json.dumps(
        candidate,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(raw)


def owner_request_digest(value: Mapping[str, Any]) -> str:
    """Hash one aoa-summon request with request_digest omitted by owner law."""

    candidate = dict(value)
    candidate.pop("request_digest", None)
    raw = json.dumps(
        candidate,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(raw)


def parse_incarnation_binding(value: Mapping[str, Any]) -> IncarnationBinding:
    """Parse historical v1 receipts and evidence-complete v2 bindings exactly."""

    schema_version = value.get("schema_version")
    if schema_version == "aoa_agent_incarnation_binding_v1":
        return AgentIncarnationBinding.model_validate(value)
    if schema_version == "aoa_agent_incarnation_binding_v2":
        return AgentIncarnationBindingV2.model_validate(value)
    raise ExternalCodexRuntimeError(
        "incarnation_binding_schema_unsupported",
        "incarnation binding must use the exact v1 or v2 owner schema",
    )


def read_bounded(path: Path, *, limit: int = MAX_CONTROL_BYTES) -> bytes:
    if not path.is_absolute():
        raise ExternalCodexRuntimeError(
            "path_not_absolute", f"runtime coordinate is not absolute: {path}"
        )
    try:
        with path.open("rb") as handle:
            payload = handle.read(limit + 1)
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "artifact_unavailable", f"cannot read runtime coordinate: {path}"
        ) from exc
    if len(payload) > limit:
        raise ExternalCodexRuntimeError(
            "artifact_too_large", f"runtime coordinate exceeds {limit} bytes: {path}"
        )
    return payload


def load_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalCodexRuntimeError(
            "invalid_json", f"{label} is not valid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise ExternalCodexRuntimeError(
            "invalid_json", f"{label} must be a JSON object"
        )
    return value


def load_json(path: Path, *, label: str) -> dict[str, Any]:
    return load_json_bytes(read_bounded(path), label=label)


def load_schema(path: Path) -> dict[str, Any]:
    schema = load_json(path, label=f"schema {path.name}")
    Draft202012Validator.check_schema(schema)
    return schema


def validate_json(value: Any, schema_path: Path, *, label: str) -> None:
    validator = Draft202012Validator(
        load_schema(schema_path),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = "/".join(str(item) for item in first.path) or "<root>"
        raise ExternalCodexRuntimeError(
            "schema_validation_failed",
            f"{label} violates {schema_path.name} at {location}: {first.message}",
        )


def validate_structured_output_schema(schema: Mapping[str, Any]) -> None:
    """Fail before inference when a schema exceeds OpenAI Structured Outputs."""

    unsupported = {
        "allOf",
        "not",
        "dependentRequired",
        "dependentSchemas",
        "if",
        "then",
        "else",
        "uniqueItems",
    }

    def walk(node: Mapping[str, Any], path: str) -> None:
        found = unsupported.intersection(node)
        if found:
            raise ExternalCodexRuntimeError(
                "codex_output_schema_unsupported",
                f"output schema uses unsupported keywords at {path}: {sorted(found)}",
            )
        properties = node.get("properties")
        if properties is not None:
            if node.get("type") != "object" or not isinstance(properties, dict):
                raise ExternalCodexRuntimeError(
                    "codex_output_schema_unsupported",
                    f"output schema properties lack an object type at {path}",
                )
            if node.get("additionalProperties") is not False:
                raise ExternalCodexRuntimeError(
                    "codex_output_schema_unsupported",
                    f"output schema object must close additional properties at {path}",
                )
            required = node.get("required")
            if not isinstance(required, list) or set(required) != set(properties):
                raise ExternalCodexRuntimeError(
                    "codex_output_schema_unsupported",
                    f"every output schema property must be required at {path}",
                )
            for name, child in properties.items():
                if not isinstance(child, dict):
                    raise ExternalCodexRuntimeError(
                        "codex_output_schema_unsupported",
                        f"output schema property is not an object at {path}/{name}",
                    )
                if not any(key in child for key in ("type", "$ref", "anyOf")):
                    raise ExternalCodexRuntimeError(
                        "codex_output_schema_unsupported",
                        f"output schema property lacks a type at {path}/{name}",
                    )
                walk(child, f"{path}/{name}")
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, f"{path}/items")
        choices = node.get("anyOf")
        if isinstance(choices, list):
            for index, child in enumerate(choices):
                if not isinstance(child, dict):
                    raise ExternalCodexRuntimeError(
                        "codex_output_schema_unsupported",
                        f"output schema anyOf entry is invalid at {path}/{index}",
                    )
                walk(child, f"{path}/anyOf/{index}")
        definitions = node.get("$defs")
        if isinstance(definitions, dict):
            for name, child in definitions.items():
                if isinstance(child, dict):
                    walk(child, f"{path}/$defs/{name}")

    if schema.get("type") != "object" or "anyOf" in schema:
        raise ExternalCodexRuntimeError(
            "codex_output_schema_unsupported",
            "output schema root must be one object and cannot be anyOf",
        )
    walk(schema, "<root>")


def specialize_report_schema(
    schema: Mapping[str, Any],
    *,
    task_id: str,
    incarnation_id: str,
    immutable_input_ids: Sequence[str],
) -> dict[str, Any]:
    """Bind one canonical report schema to exact runtime/evidence identities."""

    specialized = json.loads(json.dumps(schema))
    properties = specialized.get("properties")
    if not isinstance(properties, dict):
        raise ExternalCodexRuntimeError(
            "runtime_profile_invalid",
            "canonical report schema has no properties object",
        )
    for field, expected in (
        ("task_id", task_id),
        ("incarnation_id", incarnation_id),
    ):
        field_schema = properties.get(field)
        if not isinstance(field_schema, dict) or field_schema.get("type") != "string":
            raise ExternalCodexRuntimeError(
                "runtime_profile_invalid",
                f"canonical report schema cannot bind {field}",
            )
        field_schema["const"] = expected
    exact_input_ids = tuple(sorted({str(value) for value in immutable_input_ids}))
    if not exact_input_ids or any(
        INPUT_ID_RE.fullmatch(value) is None for value in exact_input_ids
    ):
        raise ExternalCodexRuntimeError(
            "runtime_profile_invalid",
            "session-local report schema requires valid immutable input identities",
        )
    immutable_alternation = "|".join(re.escape(value) for value in exact_input_ids)
    evidence_pattern = (
        "^(?:source:[^#]+|immutable:(?:"
        f"{immutable_alternation}"
        ")|runtime:(?:workspace-final-manifest|nested-evidence-namespace))#[^#]+$"
    )
    findings = properties.get("findings")
    transition = properties.get("transition")
    finding_items = findings.get("items") if isinstance(findings, dict) else None
    finding_properties = (
        finding_items.get("properties") if isinstance(finding_items, dict) else None
    )
    transition_properties = (
        transition.get("properties") if isinstance(transition, dict) else None
    )
    evidence_arrays = (
        (
            "findings",
            finding_properties.get("evidence_refs")
            if isinstance(finding_properties, dict)
            else None,
        ),
        (
            "transition",
            transition_properties.get("evidence_refs")
            if isinstance(transition_properties, dict)
            else None,
        ),
    )
    for label, evidence_array in evidence_arrays:
        if (
            not isinstance(evidence_array, dict)
            or not isinstance(evidence_array.get("items"), dict)
            or evidence_array["items"].get("type") != "string"
        ):
            raise ExternalCodexRuntimeError(
                "runtime_profile_invalid",
                f"canonical report schema cannot bind {label} evidence identities",
            )
        evidence_array["items"]["pattern"] = evidence_pattern
    Draft202012Validator.check_schema(specialized)
    validate_structured_output_schema(specialized)
    return specialized


def _atomic_write_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent)
    )
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _atomic_write_json(path: Path, value: Any, *, mode: int = 0o600) -> None:
    payload = (
        json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    _atomic_write_bytes(path, payload, mode=mode)


def _snapshot_artifact_ref(
    source_ref: Mapping[str, Any],
    target: Path,
) -> dict[str, str]:
    """Copy the exact bytes named by one evidence ref into a durable snapshot."""

    source_value = source_ref.get("artifact_ref")
    expected_digest = source_ref.get("artifact_digest")
    if not isinstance(source_value, str) or not isinstance(expected_digest, str):
        raise ExternalCodexRuntimeError(
            "runtime_result_evidence_invalid",
            "prior runtime result contains an incomplete evidence reference",
        )
    source = Path(source_value)
    if not source.is_absolute() or source.is_symlink():
        raise ExternalCodexRuntimeError(
            "runtime_result_evidence_invalid",
            "prior runtime result evidence is not an absolute regular-file coordinate",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=str(target.parent)
    )
    temp_path = Path(temporary)
    digest = hashlib.sha256()
    try:
        source_descriptor = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            if not stat.S_ISREG(os.fstat(source_descriptor).st_mode):
                raise ExternalCodexRuntimeError(
                    "runtime_result_evidence_invalid",
                    "prior runtime result evidence is not a regular file",
                )
            with (
                os.fdopen(source_descriptor, "rb") as source_handle,
                os.fdopen(descriptor, "wb") as target_handle,
            ):
                source_descriptor = -1
                descriptor = -1
                for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                    target_handle.write(chunk)
                target_handle.flush()
                os.fsync(target_handle.fileno())
        finally:
            if source_descriptor >= 0:
                os.close(source_descriptor)
        actual_digest = "sha256:" + digest.hexdigest()
        if actual_digest != expected_digest:
            raise ExternalCodexRuntimeError(
                "runtime_result_evidence_drift",
                "prior runtime result evidence bytes differ from its recorded digest",
            )
        os.chmod(temp_path, 0o400)
        os.replace(temp_path, target)
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "runtime_result_evidence_unavailable",
            "cannot preserve prior runtime result evidence",
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temp_path.exists():
            temp_path.unlink()
    return _artifact_ref(target)


def _append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_EVENT_LINE_BYTES:
        raise ExternalCodexRuntimeError(
            "runtime_event_record_too_large",
            "one normalized event exceeds the per-record safety boundary",
        )
    with path.open("ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _iter_jsonl_bytes(
    path: Path,
    *,
    failure_code: str,
    label: str,
) -> Iterator[tuple[int, bytes]]:
    """Stream newline-delimited records with a per-record, not aggregate, cap."""

    with path.open("rb") as handle:
        line_number = 0
        while True:
            line = handle.readline(MAX_EVENT_LINE_BYTES + 1)
            if not line:
                return
            line_number += 1
            if len(line) > MAX_EVENT_LINE_BYTES:
                raise ExternalCodexRuntimeError(
                    failure_code,
                    f"{label} line {line_number} exceeds the per-record safety boundary",
                )
            if not line.endswith(b"\n"):
                raise ExternalCodexRuntimeError(
                    failure_code,
                    f"{label} ends with a partial record at line {line_number}",
                )
            yield line_number, line


def _artifact_ref(path: Path, *, owner: str = "abyss-stack") -> dict[str, str]:
    return {
        "owner_repo": owner,
        "artifact_ref": str(path),
        "artifact_digest": sha256_file(path),
    }


def _verified_artifact_ref_path(
    ref: Mapping[str, Any],
    *,
    label: str,
) -> Path:
    value = ref.get("artifact_ref")
    digest = ref.get("artifact_digest")
    if not isinstance(value, str) or not isinstance(digest, str):
        raise ExternalCodexRuntimeError(
            "a2a_artifact_ref_invalid",
            f"{label} has no exact artifact path and digest",
        )
    path = Path(value)
    if (
        not path.is_absolute()
        or not path.is_file()
        or path.is_symlink()
        or sha256_file(path) != digest
    ):
        raise ExternalCodexRuntimeError(
            "a2a_artifact_drift",
            f"{label} bytes differ from the terminal runtime receipt",
        )
    return path


def _verify_a2a_export_snapshot(
    refs: Sequence[tuple[str, Mapping[str, Any]]],
) -> None:
    """Revalidate every byte reference immediately before A2A publication."""

    for label, ref in refs:
        _verified_artifact_ref_path(ref, label=label)


def _load_verified_json_ref(
    ref: Mapping[str, Any],
    *,
    label: str,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    path = _verified_artifact_ref_path(ref, label=label)
    value = load_json(path, label=label)
    if schema_path is not None:
        validate_json(value, schema_path, label=label)
    return value


def _load_nested_evidence_namespace(
    state: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Reload and rebind one controller-generated nested evidence derivative."""

    namespace_ref = state.get("nested_evidence_namespace_ref")
    if namespace_ref is None:
        return None
    if not isinstance(namespace_ref, dict):
        raise ExternalCodexRuntimeError(
            "nested_evidence_namespace_drift",
            "nested evidence namespace state is malformed",
        )
    namespace = _load_verified_json_ref(
        namespace_ref,
        label="nested evidence namespace",
        schema_path=NESTED_EVIDENCE_NAMESPACE_SCHEMA_PATH,
    )
    task_path = Path(str(state["materialized_inputs"]["task"]))
    if (
        namespace.get("namespace_digest")
        != nested_evidence_namespace_digest(namespace)
        or namespace.get("review_task_id") != state.get("task_id")
        or namespace.get("review_task_digest") != sha256_file(task_path)
        or namespace.get("status") != "closed"
        or namespace.get("summary", {}).get("unresolved") != 0
    ):
        raise ExternalCodexRuntimeError(
            "nested_evidence_namespace_drift",
            "nested evidence namespace no longer binds the exact review task",
        )
    return namespace


def _process_start_ticks(pid: int) -> int | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = raw.rfind(")")
        if close < 0:
            return None
        fields = raw[close + 2 :].split()
        if fields[0] == "Z":
            return None
        return int(fields[19])
    except (OSError, IndexError, ValueError):
        return None


def _process_group_identity(pid: int) -> tuple[str, int, int, int] | None:
    """Return state, process group, session, and start ticks from Linux procfs."""

    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = raw.rfind(")")
        if close < 0:
            return None
        fields = raw[close + 2 :].split()
        return fields[0], int(fields[2]), int(fields[3]), int(fields[19])
    except (OSError, IndexError, ValueError):
        return None


def _process_parent_identity(
    pid: int,
) -> tuple[str, int, int, int, int] | None:
    """Return state, parent, process group, session, and start ticks."""

    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = raw.rfind(")")
        if close < 0:
            return None
        fields = raw[close + 2 :].split()
        return (
            fields[0],
            int(fields[1]),
            int(fields[2]),
            int(fields[3]),
            int(fields[19]),
        )
    except (OSError, IndexError, ValueError):
        return None


def _owned_process_group_members(pgid: int, leader_start_ticks: int) -> tuple[int, ...]:
    """Identify the exact start_new_session group, including a dead leader's children."""

    if pgid <= 1 or leader_start_ticks <= 0:
        raise ExternalCodexRuntimeError(
            "codex_process_identity_invalid",
            "Codex process-group identity is incomplete",
        )
    leader = _process_group_identity(pgid)
    if leader is not None and leader[0] != "Z" and leader[3] != leader_start_ticks:
        raise ExternalCodexRuntimeError(
            "codex_process_identity_drift", "Codex leader PID was reused"
        )
    members: list[int] = []
    try:
        proc_entries = tuple(Path("/proc").iterdir())
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "codex_process_observation_failed", "cannot enumerate Codex process group"
        ) from exc
    for entry in proc_entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        identity = _process_group_identity(pid)
        if identity is None or identity[0] == "Z":
            continue
        _, process_group, session_id, _ = identity
        if process_group == pgid and session_id == pgid:
            members.append(pid)
    return tuple(sorted(members))


def _terminate_owned_process_group(
    pgid: int,
    leader_start_ticks: int,
    *,
    term_timeout: float = 3.0,
    kill_timeout: float = 3.0,
) -> None:
    """Terminate one exact Codex session and prove that no descendant remains."""

    members = _owned_process_group_members(pgid, leader_start_ticks)
    if not members:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + term_timeout
    while time.monotonic() < deadline:
        if not _owned_process_group_members(pgid, leader_start_ticks):
            return
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + kill_timeout
    while time.monotonic() < deadline:
        if not _owned_process_group_members(pgid, leader_start_ticks):
            return
        time.sleep(0.05)
    remaining = _owned_process_group_members(pgid, leader_start_ticks)
    if remaining:
        raise ExternalCodexRuntimeError(
            "codex_process_cleanup_incomplete",
            "Codex process group retained live members after bounded SIGKILL",
        )


def _pid_matches(pid: Any, start_ticks: Any) -> bool:
    if not isinstance(pid, int) or pid <= 1 or not isinstance(start_ticks, int):
        return False
    return _process_start_ticks(pid) == start_ticks


def _state_supervisor_identity(state: Mapping[str, Any]) -> tuple[Any, Any]:
    """Use explicit supervisor identity, with read-only v2 receipt compatibility."""

    supervisor_pid = state.get("supervisor_pid")
    supervisor_ticks = state.get("supervisor_start_ticks")
    if isinstance(supervisor_pid, int) and isinstance(supervisor_ticks, int):
        return supervisor_pid, supervisor_ticks
    return state.get("codex_pid"), state.get("codex_start_ticks")


def _wait_for_process_identity_receipt(
    path: Path,
    *,
    process: subprocess.Popen[bytes],
    supervisor_start_ticks: int,
    timeout_seconds: float = 5.0,
) -> tuple[dict[str, int | str], dict[str, str]]:
    deadline = time.monotonic() + timeout_seconds
    while not path.is_file():
        if process.poll() is not None or time.monotonic() >= deadline:
            raise ExternalCodexRuntimeError(
                "codex_process_identity_invalid",
                "supervisor did not publish the exact Codex process identity",
            )
        time.sleep(0.01)
    if path.is_symlink():
        raise ExternalCodexRuntimeError(
            "codex_process_identity_invalid",
            "process identity receipt must be a regular non-symlink file",
        )
    receipt = load_json(path, label="external Codex process identity")
    expected_keys = {
        "schema_version",
        "supervisor_pid",
        "supervisor_start_ticks",
        "launcher_pid",
        "launcher_start_ticks",
        "codex_pid",
        "codex_start_ticks",
    }
    if set(receipt) != expected_keys or receipt.get("schema_version") != (
        "abyss_stack_external_codex_process_identity_v2"
    ):
        raise ExternalCodexRuntimeError(
            "codex_process_identity_invalid",
            "process identity receipt has an unsupported shape",
        )
    supervisor_pid = receipt.get("supervisor_pid")
    launcher_pid = receipt.get("launcher_pid")
    launcher_start_ticks = receipt.get("launcher_start_ticks")
    codex_pid = receipt.get("codex_pid")
    codex_start_ticks = receipt.get("codex_start_ticks")
    if (
        supervisor_pid != process.pid
        or receipt.get("supervisor_start_ticks") != supervisor_start_ticks
        or not isinstance(launcher_pid, int)
        or launcher_pid <= 1
        or not isinstance(launcher_start_ticks, int)
        or launcher_start_ticks <= 0
        or not isinstance(codex_pid, int)
        or codex_pid <= 1
        or not isinstance(codex_start_ticks, int)
        or codex_start_ticks <= 0
    ):
        raise ExternalCodexRuntimeError(
            "codex_process_identity_invalid",
            "process identity receipt differs from the launched supervisor",
        )
    launcher = _process_parent_identity(launcher_pid)
    codex = _process_parent_identity(codex_pid)
    launcher_mismatch = launcher is not None and (
        launcher[1] != supervisor_pid
        or launcher[2] != supervisor_pid
        or launcher[3] != supervisor_pid
        or launcher[4] != launcher_start_ticks
    )
    expected_codex_parent = (
        supervisor_pid if codex_pid == launcher_pid else launcher_pid
    )
    codex_mismatch = codex is not None and (
        codex[1] != expected_codex_parent
        or codex[2] != supervisor_pid
        or codex[3] != supervisor_pid
        or codex[4] != codex_start_ticks
    )
    if launcher_mismatch or codex_mismatch:
        # A short-lived Codex may already have been reaped and its PID reused,
        # or its terminal zombie may have been reparented, by the time the
        # durable receipt becomes visible.  That is a valid terminal handoff
        # only after the exact supervisor has itself completed.  A mismatched
        # identity while that supervisor is still live remains fail-closed.
        if process.poll() is None:
            raise ExternalCodexRuntimeError(
                "codex_process_identity_invalid",
                "live launcher or Codex identity differs from the supervisor receipt",
            )
    return receipt, _artifact_ref(path)


def _reap_owned_child(pid: Any, start_ticks: Any) -> None:
    if (
        not isinstance(pid, int)
        or pid <= 1
        or not isinstance(start_ticks, int)
        or start_ticks <= 0
    ):
        return
    identity = _process_group_identity(pid)
    if identity is None or identity[3] != start_ticks:
        return
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass


def _session_token(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]


def _relative_path_is_allowed(path: str, allowed: Sequence[str]) -> bool:
    def safe_parts(value: Any) -> tuple[str, ...] | None:
        if (
            not isinstance(value, str)
            or not value
            or value.startswith("/")
            or "\\" in value
            or "\0" in value
        ):
            return None
        parts = tuple(value.split("/"))
        if any(part in {"", ".", ".."} for part in parts):
            return None
        return parts

    path_parts = safe_parts(path)
    if path_parts is None:
        return False
    for candidate in allowed:
        if candidate == ".":
            return True
        candidate_parts = safe_parts(candidate)
        if candidate_parts is None:
            continue
        if path_parts[: len(candidate_parts)] == candidate_parts:
            return True
    return False


def _actor_delta_change_is_allowed(
    change: Mapping[str, Any],
    allowed: Sequence[str],
    *,
    peer_changes: Sequence[Mapping[str, Any]] = (),
) -> bool:
    """Admit one actor-delta entry under the exact path authority relation.

    ``allowed_paths`` names the actor's semantic mutation surface.  Creating
    ``actor-output/result.json`` necessarily creates ``actor-output`` when the
    source tree does not already contain it.  The manifest records both
    entries, so treating the directory entry as a separate scope expansion
    makes the explicitly admitted file impossible to produce.

    Only created or deleted *directories* may use this structural-ancestor
    rule, and only when ``peer_changes`` contains an actually changed,
    ordinarily allowed descendant.  Files, symlinks, type changes, mode
    changes, and sibling paths must still match the ordinary descendant rule
    exactly.  A caller that has only one compact path must not infer that it is
    a structural ancestor.
    """

    path = change.get("path")
    if not isinstance(path, str):
        return False
    if _relative_path_is_allowed(path, allowed):
        return True

    status = change.get("status")
    if status == "created":
        entry = change.get("after")
    elif status == "deleted":
        entry = change.get("before")
    else:
        return False
    if not isinstance(entry, Mapping) or entry.get("kind") != "directory":
        return False

    path_parts = tuple(path.split("/"))
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or "\0" in path
        or any(part in {"", ".", ".."} for part in path_parts)
    ):
        return False
    for peer in peer_changes:
        peer_path = peer.get("path")
        if not isinstance(peer_path, str):
            continue
        peer_parts = tuple(peer_path.split("/"))
        if (
            len(peer_parts) <= len(path_parts)
            or peer_parts[: len(path_parts)] != path_parts
        ):
            continue
        if _relative_path_is_allowed(peer_path, allowed):
            return True
    return False


def _actor_delta_changes_out_of_scope(
    changes: Sequence[Mapping[str, Any]], allowed: Sequence[str]
) -> list[str]:
    """Classify a complete exact actor delta without compact-path inference."""

    peer_changes = tuple(changes)
    return [
        str(change.get("path", "<invalid>"))
        for change in peer_changes
        if not _actor_delta_change_is_allowed(
            change,
            allowed,
            peer_changes=peer_changes,
        )
    ]


def _workspace_artifact_path(workspace: str | Path, value: str) -> Path:
    """Resolve one produced regular file without following workspace symlinks."""

    root = Path(workspace).resolve()
    candidate = root.joinpath(*value.split("/"))
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ExternalCodexRuntimeError(
            "model_report_artifact_unavailable",
            "model report artifact is absent or resolves outside the workspace",
        ) from exc
    if resolved != candidate or candidate.is_symlink() or not candidate.is_file():
        raise ExternalCodexRuntimeError(
            "model_report_artifact_unavailable",
            "model report artifact must be a produced regular workspace file",
        )
    return candidate


def _validate_evidence_anchor(
    raw: bytes,
    anchor: str,
    *,
    label: str,
    error_code: str,
) -> None:
    """Validate one bounded line or literal-symbol anchor against exact bytes."""

    line_match = SOURCE_LINE_ANCHOR_RE.fullmatch(anchor)
    if line_match is not None:
        start = int(line_match.group("start"))
        end = int(line_match.group("end") or start)
        line_count = len(raw.splitlines())
        if end < start or end > line_count:
            raise ExternalCodexRuntimeError(
                error_code,
                f"model report evidence line anchor is outside {label}",
            )
        return
    if len(anchor) > 256 or any(ord(character) < 32 for character in anchor):
        raise ExternalCodexRuntimeError(
            error_code,
            "model report evidence symbol anchor is invalid",
        )
    if anchor.encode("utf-8") not in raw:
        raise ExternalCodexRuntimeError(
            error_code,
            f"model report evidence symbol anchor is absent from {label}",
        )


def _validate_source_evidence_ref(
    value: str,
    workspace: str | Path,
    *,
    source_evidence_paths: Sequence[str],
    workspace_fd: int | None = None,
) -> None:
    """Validate one anchored source reference against exact workspace bytes."""

    if not value.startswith("source:"):
        raise ExternalCodexRuntimeError(
            "model_report_evidence_scheme_unsupported",
            "model report source evidence must use the source: scheme",
        )
    body = value.removeprefix("source:")
    relative, separator, anchor = body.partition("#")
    parts = tuple(relative.split("/"))
    if (
        not relative
        or relative.startswith("/")
        or "\\" in relative
        or "\0" in relative
        or any(part in {"", ".", ".."} for part in parts)
        or not separator
        or not anchor
        or "#" in anchor
    ):
        raise ExternalCodexRuntimeError(
            "model_report_source_evidence_invalid",
            "model report source evidence has an invalid relative path or anchor",
        )
    if not _relative_path_is_allowed(relative, source_evidence_paths):
        raise ExternalCodexRuntimeError(
            "model_report_source_evidence_out_of_scope",
            "model report source evidence is outside the task source evidence paths",
        )
    if _secret_shaped_path(relative):
        raise ExternalCodexRuntimeError(
            "model_report_source_evidence_secret_shaped",
            "model report source evidence names a secret-shaped path",
        )
    if workspace_fd is None:
        root = Path(workspace).resolve()
        candidate = root.joinpath(*parts)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise ExternalCodexRuntimeError(
                "model_report_source_evidence_unavailable",
                f"model report source evidence is absent or outside the workspace: {relative}",
            ) from exc
        if resolved != candidate or candidate.is_symlink() or not candidate.is_file():
            raise ExternalCodexRuntimeError(
                "model_report_source_evidence_unavailable",
                f"model report source evidence is not a regular workspace file: {relative}",
            )
        try:
            raw = read_bounded(candidate)
        except ExternalCodexRuntimeError as exc:
            raise ExternalCodexRuntimeError(
                "model_report_source_evidence_unavailable",
                f"model report source evidence cannot be inspected: {relative}",
            ) from exc
    else:
        directory_fd = os.dup(workspace_fd)
        file_fd = -1
        try:
            directory_flags = os.O_PATH | os.O_CLOEXEC | os.O_DIRECTORY
            file_flags = os.O_RDONLY | os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                directory_flags |= os.O_NOFOLLOW
                file_flags |= os.O_NOFOLLOW
            for component in parts[:-1]:
                next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = next_fd
            file_fd = os.open(parts[-1], file_flags, dir_fd=directory_fd)
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise OSError("source evidence is not a regular file")
            chunks: list[bytes] = []
            remaining = MAX_CONTROL_BYTES + 1
            while remaining:
                chunk = os.read(file_fd, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > MAX_CONTROL_BYTES:
                raise OSError("source evidence exceeds the bounded read limit")
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "model_report_source_evidence_unavailable",
                f"model report source evidence cannot be inspected: {relative}",
            ) from exc
        finally:
            if file_fd >= 0:
                os.close(file_fd)
            os.close(directory_fd)
    _validate_evidence_anchor(
        raw,
        anchor,
        label=relative,
        error_code="model_report_source_evidence_anchor_invalid",
    )


def _validate_immutable_evidence_ref(
    value: str,
    state: Mapping[str, Any],
) -> None:
    """Resolve one stable immutable input identity and validate its exact bytes."""

    if not value.startswith("immutable:"):
        raise ExternalCodexRuntimeError(
            "model_report_evidence_scheme_unsupported",
            "model report immutable evidence must use the immutable: scheme",
        )
    body = value.removeprefix("immutable:")
    input_id, separator, anchor = body.partition("#")
    if (
        INPUT_ID_RE.fullmatch(input_id) is None
        or not separator
        or not anchor
        or "#" in anchor
    ):
        raise ExternalCodexRuntimeError(
            "model_report_immutable_evidence_invalid",
            "model report immutable evidence has an invalid input id or anchor",
        )
    matches = [
        item
        for item in state["materialized_task_inputs"]
        if item["input_id"] == input_id
    ]
    if len(matches) != 1:
        raise ExternalCodexRuntimeError(
            "model_report_immutable_evidence_unavailable",
            f"model report immutable evidence input is not materialized: {input_id}",
        )
    item = matches[0]
    candidate = Path(str(item["path"]))
    immutable_root = (
        Path(str(state["materialized_inputs"]["task"])).parent / "immutable"
    ).resolve()
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(immutable_root)
    except (OSError, ValueError) as exc:
        raise ExternalCodexRuntimeError(
            "model_report_immutable_evidence_unavailable",
            f"model report immutable evidence is absent or outside runtime inputs: {input_id}",
        ) from exc
    if resolved != candidate or candidate.is_symlink() or not candidate.is_file():
        raise ExternalCodexRuntimeError(
            "model_report_immutable_evidence_unavailable",
            f"model report immutable evidence is not a regular runtime input: {input_id}",
        )
    raw = read_bounded(candidate)
    if sha256_bytes(raw) != item["provenance"]["artifact_digest"]:
        raise ExternalCodexRuntimeError(
            "model_report_immutable_evidence_drift",
            f"model report immutable evidence bytes drifted: {input_id}",
        )
    _validate_evidence_anchor(
        raw,
        anchor,
        label=f"immutable input {input_id}",
        error_code="model_report_immutable_evidence_anchor_invalid",
    )


def _validate_runtime_evidence_ref(
    value: str,
    runtime_evidence_paths: Mapping[str, Path],
) -> None:
    """Validate one controller-produced artifact through a reserved identity."""

    if not value.startswith("runtime:"):
        raise ExternalCodexRuntimeError(
            "model_report_evidence_scheme_unsupported",
            "model report runtime evidence must use the runtime: scheme",
        )
    body = value.removeprefix("runtime:")
    evidence_id, separator, anchor = body.partition("#")
    if (
        evidence_id
        not in {"workspace-final-manifest", "nested-evidence-namespace"}
        or not separator
        or not anchor
        or "#" in anchor
    ):
        raise ExternalCodexRuntimeError(
            "model_report_runtime_evidence_invalid",
            "model report runtime evidence names no admitted controller artifact",
        )
    candidate = runtime_evidence_paths.get(evidence_id)
    if (
        candidate is None
        or not candidate.is_absolute()
        or not candidate.is_file()
        or candidate.is_symlink()
    ):
        raise ExternalCodexRuntimeError(
            "model_report_runtime_evidence_unavailable",
            "model report runtime-owned evidence is unavailable",
        )
    raw = read_bounded(candidate)
    if evidence_id == "nested-evidence-namespace":
        if re.fullmatch(r"nested-evidence-[0-9a-f]{24}", anchor) is None:
            raise ExternalCodexRuntimeError(
                "model_report_runtime_evidence_anchor_invalid",
                "nested evidence namespace requires one exact entry identity",
            )
        namespace = load_json_bytes(raw, label="nested evidence namespace")
        validate_json(
            namespace,
            NESTED_EVIDENCE_NAMESPACE_SCHEMA_PATH,
            label="nested evidence namespace",
        )
        if namespace.get("namespace_digest") != nested_evidence_namespace_digest(
            namespace
        ):
            raise ExternalCodexRuntimeError(
                "model_report_runtime_evidence_anchor_invalid",
                "nested evidence namespace digest is invalid",
            )
        entries = [
            entry
            for producer in namespace.get("producers", [])
            for entry in producer.get("entries", [])
            if entry.get("entry_id") == anchor
        ]
        if len(entries) != 1:
            raise ExternalCodexRuntimeError(
                "model_report_runtime_evidence_anchor_invalid",
                "nested evidence namespace entry is absent or ambiguous",
            )
        return
    if SOURCE_LINE_ANCHOR_RE.fullmatch(anchor) is not None:
        _validate_evidence_anchor(
            raw,
            anchor,
            label="runtime workspace final manifest",
            error_code="model_report_runtime_evidence_anchor_invalid",
        )
        return
    try:
        manifest = load_json_bytes(raw, label="runtime workspace final manifest")
    except ExternalCodexRuntimeError as exc:
        raise ExternalCodexRuntimeError(
            "model_report_runtime_evidence_anchor_invalid",
            "runtime workspace final manifest is not valid JSON",
        ) from exc
    if anchor in manifest:
        return
    content_entries = manifest.get("content_entries")
    if isinstance(content_entries, list) and any(
        isinstance(item, dict) and item.get("path") == anchor
        for item in content_entries
    ):
        return
    raise ExternalCodexRuntimeError(
        "model_report_runtime_evidence_anchor_invalid",
        "model report evidence names neither an exact top-level final-manifest "
        "member nor an exact content-entry path",
    )


def _validate_report_evidence_ref(
    value: str,
    *,
    state: Mapping[str, Any],
    source_evidence_paths: Sequence[str],
    runtime_evidence_paths: Mapping[str, Path],
    workspace_fd: int | None = None,
) -> None:
    """Admit source, immutable-input, or reserved runtime evidence schemes."""

    if value.startswith("source:"):
        _validate_source_evidence_ref(
            value,
            state["workspace_path"],
            source_evidence_paths=source_evidence_paths,
            workspace_fd=workspace_fd,
        )
        return
    if value.startswith("immutable:"):
        _validate_immutable_evidence_ref(value, state)
        return
    if value.startswith("runtime:"):
        _validate_runtime_evidence_ref(value, runtime_evidence_paths)
        return
    raise ExternalCodexRuntimeError(
        "model_report_evidence_scheme_unsupported",
        "model report evidence must use anchored source:, immutable:<input_id>, "
        "runtime:workspace-final-manifest, or runtime:nested-evidence-namespace refs",
    )


def _secret_shaped_path(value: str) -> bool:
    """Recognize paths that the controller must not content-inspect."""

    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return False
    parts = tuple(part.lower() for part in normalized.split("/") if part)
    if not parts:
        return False
    name = parts[-1]
    return (
        any(part in SECRET_PATH_PARTS for part in parts)
        or name in SECRET_FILE_NAMES
        or SECRET_FILE_TOKEN_RE.search(name) is not None
        or name.startswith(".env.")
        or name.endswith((".jks", ".kdbx", ".key", ".p12", ".pem"))
    )


def _git_admin_metadata_path(value: str) -> bool:
    """Recognize explicit paths into a repository's private Git state."""

    normalized = value.replace("\\", "/").strip().rstrip("/").lower()
    if not normalized:
        return False
    parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
    return ".git" in parts


def _git_config_metadata_path(value: str) -> bool:
    """Recognize direct reads of credential- or helper-bearing Git config."""

    normalized = value.replace("\\", "/").strip().rstrip("/").lower()
    if not _git_admin_metadata_path(normalized):
        return False
    return normalized.rsplit("/", 1)[-1] in {
        "config",
        "config.lock",
        "config.worktree",
        "config.worktree.lock",
    }


def _long_option_prefix(value: str, canonical: str) -> bool:
    """Match an exact or conservatively abbreviated GNU long option."""

    option = value.lower().split("=", 1)[0]
    return option.startswith("--") and len(option) >= 3 and canonical.startswith(option)


ATTACHED_SHORT_FILE_OPTIONS = {
    "awk": frozenset("f"),
    "date": frozenset("f"),
    "file": frozenset("f"),
    "grep": frozenset("f"),
    "jq": frozenset("f"),
    "rg": frozenset("f"),
    "sed": frozenset("f"),
}


def _argument_secret_access(executable: str, value: str) -> bool:
    """Inspect direct and option-attached secret-shaped coordinates."""

    if ("/" in value or value.startswith(".")) and _secret_shaped_path(value):
        return True
    if value.startswith("-") and "=" in value:
        candidate = value.split("=", 1)[1]
        return _secret_shaped_path(candidate) or _git_config_metadata_path(candidate)
    if value.startswith("-") and not value.startswith("--"):
        body = value[1:]
        file_options = ATTACHED_SHORT_FILE_OPTIONS.get(executable, frozenset())
        for index, option in enumerate(body):
            if option not in file_options or index + 1 >= len(body):
                continue
            candidate = body[index + 1 :]
            return _secret_shaped_path(candidate) or _git_config_metadata_path(
                candidate
            )
    return False


def _pattern_reader_file_access(
    tokens: Sequence[str], path_predicate: Callable[[str], bool]
) -> bool:
    """Inspect every actual rg, grep, or sed input-file coordinate."""

    executable = Path(tokens[0]).name.lower()
    short_flags_without_values = {
        "grep": frozenset("EFGHhIiJLlnoqRrsvVwxyUZz"),
        "rg": frozenset("FHINnqSuvVwz"),
        "sed": frozenset("Ensu"),
    }
    separate_value_options = {
        "grep": frozenset(
            {
                "-A",
                "-B",
                "-C",
                "-d",
                "-D",
                "-m",
                "--after-context",
                "--before-context",
                "--binary-files",
                "--context",
                "--devices",
                "--directories",
                "--exclude",
                "--exclude-dir",
                "--group-separator",
                "--include",
                "--label",
                "--max-count",
            }
        ),
        "rg": frozenset(
            {
                "-A",
                "-B",
                "-C",
                "-E",
                "-M",
                "-T",
                "-g",
                "-j",
                "-m",
                "-r",
                "-t",
                "--after-context",
                "--before-context",
                "--colors",
                "--context",
                "--context-separator",
                "--encoding",
                "--engine",
                "--field-context-separator",
                "--field-match-separator",
                "--glob",
                "--max-columns",
                "--max-count",
                "--max-depth",
                "--max-filesize",
                "--path-separator",
                "--regexp",
                "--replace",
                "--sort",
                "--sortr",
                "--threads",
                "--type",
                "--type-add",
                "--type-clear",
                "--type-not",
            }
        ),
        "sed": frozenset({"-l", "--line-length"}),
    }
    explicit_program = False
    operands: list[str] = []
    index = 1
    while index < len(tokens):
        value = tokens[index]
        lowered = value.lower()
        if value == "--":
            operands.extend(tokens[index + 1 :])
            break
        if (
            executable == "grep"
            and (lowered == "-e" or _long_option_prefix(value, "--regexp"))
        ) or (executable == "rg" and lowered in {"-e", "--regexp"}):
            explicit_program = True
            index += 1 if "=" in value else 2
            continue
        if executable == "sed" and (
            lowered == "-e" or _long_option_prefix(value, "--expression")
        ):
            explicit_program = True
            index += 1 if "=" in value else 2
            continue
        if executable in {"grep", "rg", "sed"} and (
            lowered == "-f" or _long_option_prefix(value, "--file")
        ):
            file_value = (
                value.split("=", 1)[1]
                if "=" in value
                else tokens[index + 1]
                if index + 1 < len(tokens)
                else ""
            )
            if path_predicate(file_value):
                return True
            explicit_program = True
            index += 1 if "=" in value else 2
            continue
        if executable in {"grep", "rg"} and (
            (lowered.startswith("-e") and lowered != "-e")
            or (executable == "rg" and lowered.startswith("--regexp="))
        ):
            explicit_program = True
            index += 1
            continue
        if executable == "sed" and (lowered.startswith("-e") and lowered != "-e"):
            explicit_program = True
            index += 1
            continue
        if executable in {"grep", "rg", "sed"} and (
            lowered.startswith("-f") and lowered != "-f"
        ):
            pattern_file = value[2:]
            if path_predicate(pattern_file):
                return True
            explicit_program = True
            index += 1
            continue
        if value.startswith("-") and not value.startswith("--"):
            short_body = value[1:]
            prefix_flags = short_flags_without_values.get(executable, frozenset())
            for offset, option in enumerate(short_body):
                if option not in {"e", "f"}:
                    if option not in prefix_flags:
                        break
                    continue
                option_value = short_body[offset + 1 :]
                if not option_value and index + 1 < len(tokens):
                    option_value = tokens[index + 1]
                    index += 1
                if option == "f" and path_predicate(option_value):
                    return True
                explicit_program = True
                index += 1
                break
            else:
                option = ""
            if option in {"e", "f"}:
                continue
        if executable == "rg" and lowered in {"--ignore-file", "--pre-glob"}:
            if index + 1 < len(tokens) and path_predicate(tokens[index + 1]):
                return True
            index += 2
            continue
        if executable == "rg" and lowered.startswith(("--ignore-file=", "--pre-glob=")):
            if path_predicate(value.split("=", 1)[1]):
                return True
            index += 1
            continue
        if executable == "grep" and _long_option_prefix(value, "--exclude-from"):
            file_value = (
                value.split("=", 1)[1]
                if "=" in value
                else tokens[index + 1]
                if index + 1 < len(tokens)
                else ""
            )
            if path_predicate(file_value):
                return True
            index += 1 if "=" in value else 2
            continue
        value_options = separate_value_options.get(executable, frozenset())
        if value in value_options or lowered in {
            option for option in value_options if option.startswith("--")
        }:
            index += 2
            continue
        if any(
            lowered.startswith(option + "=")
            for option in value_options
            if option.startswith("--")
        ):
            index += 1
            continue
        if value.startswith("-"):
            index += 1
            continue
        operands.append(value)
        index += 1
    file_operands = operands if explicit_program else operands[1:]
    return any(path_predicate(value) for value in file_operands)


def _pattern_reader_git_config_file_access(tokens: Sequence[str]) -> bool:
    return _pattern_reader_file_access(tokens, _git_config_metadata_path)


def _direct_git_config_file_access(tokens: Sequence[str]) -> bool:
    """Distinguish a Git-config file operand from harmless pattern text."""

    if not tokens:
        return False
    executable = Path(tokens[0]).name.lower()
    if executable in DIRECT_GIT_CONFIG_READERS:
        return any(_git_config_metadata_path(value) for value in tokens[1:])
    if executable == "jq":
        return _jq_git_config_file_access(tokens)
    if executable not in PATTERN_GIT_CONFIG_READERS:
        return False
    return _pattern_reader_git_config_file_access(tokens)


def _direct_reader_secret_file_access(tokens: Sequence[str]) -> bool:
    """Inspect actual file coordinates of direct reader utilities."""

    if not tokens:
        return False
    executable = Path(tokens[0]).name.lower()
    options = DIRECT_READER_VALUE_OPTIONS.get(executable)
    if options is None:
        return False
    operands: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()
        if token == "--":
            operands.extend(tokens[index + 1 :])
            break
        long_match = next(
            (
                (canonical, file_valued)
                for canonical, file_valued in options.values()
                if _long_option_prefix(token, canonical)
            ),
            None,
        )
        if long_match is not None:
            _, file_valued = long_match
            if "=" in token:
                option_value = token.split("=", 1)[1]
                index += 1
            else:
                option_value = tokens[index + 1] if index + 1 < len(tokens) else ""
                index += 2
            if file_valued and _secret_shaped_path(option_value):
                return True
            continue
        if token.startswith("-") and not token.startswith("--") and token != "-":
            short_body = token[1:]
            consumed_value = False
            for offset, option in enumerate(short_body):
                descriptor = options.get("-" + option)
                if descriptor is None:
                    continue
                _, file_valued = descriptor
                option_value = short_body[offset + 1 :]
                if not option_value and index + 1 < len(tokens):
                    option_value = tokens[index + 1]
                    index += 1
                if file_valued and _secret_shaped_path(option_value):
                    return True
                consumed_value = True
                break
            index += 1
            if consumed_value:
                continue
            continue
        if not lowered.startswith("-"):
            operands.append(token)
        index += 1
    file_operands = operands[:1] if executable == "uniq" else operands
    return any(_secret_shaped_path(value) for value in file_operands)


def _find_secret_file_access(tokens: Sequence[str]) -> bool:
    """Inspect GNU find roots and options that read another file."""

    if not tokens or Path(tokens[0]).name.lower() != "find":
        return False
    expression_started = False
    index = 1
    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()
        if lowered == "-files0-from":
            if index + 1 < len(tokens) and _secret_shaped_path(tokens[index + 1]):
                return True
            index += 2
            continue
        if lowered.startswith("-files0-from="):
            if _secret_shaped_path(token.split("=", 1)[1]):
                return True
            index += 1
            continue
        if lowered in {"-anewer", "-cnewer", "-newer", "-samefile"} or (
            lowered.startswith("-newer") and len(lowered) == len("-newerxy")
        ):
            if index + 1 < len(tokens) and _secret_shaped_path(tokens[index + 1]):
                return True
            index += 2
            continue
        if not expression_started:
            if token == "--":
                index += 1
                continue
            if lowered == "-d":
                index += 2
                continue
            if lowered in {"-h", "-l", "-p"} or (
                lowered.startswith("-o") and len(lowered) > 2
            ):
                index += 1
                continue
            if token.startswith("-") or token in {"!", "(", ")", ","}:
                expression_started = True
                index += 1
                continue
            if _secret_shaped_path(token):
                return True
        index += 1
    return False


def _reader_secret_file_access(tokens: Sequence[str]) -> bool:
    """Route each reader family through its actual file-coordinate parser."""

    if not tokens:
        return False
    executable = Path(tokens[0]).name.lower()
    if executable in DIRECT_READER_VALUE_OPTIONS:
        return _direct_reader_secret_file_access(tokens)
    if executable == "jq":
        return _jq_file_access(tokens, _secret_shaped_path)
    if executable == "find":
        return _find_secret_file_access(tokens)
    if executable in PATTERN_GIT_CONFIG_READERS:
        return _pattern_reader_file_access(tokens, _secret_shaped_path)
    return False


def _jq_file_access(
    tokens: Sequence[str], path_predicate: Callable[[str], bool]
) -> bool:
    """Inspect jq input files and explicit file-loading option coordinates."""

    program_seen = False
    program_from_file = False
    index = 1
    while index < len(tokens):
        value = tokens[index]
        lowered = value.lower()
        if not program_seen and value == "--":
            program_seen = program_from_file
            index += 1
            continue
        if lowered in {"--rawfile", "--slurpfile", "--argfile"}:
            if index + 2 < len(tokens) and path_predicate(tokens[index + 2]):
                return True
            index += 3
            continue
        if lowered in {"--arg", "--argjson"}:
            index += 3
            continue
        if lowered in {"-f", "--from-file"}:
            if index + 1 < len(tokens) and path_predicate(tokens[index + 1]):
                return True
            program_from_file = True
            program_seen = True
            index += 2
            continue
        if lowered.startswith(("--from-file=", "-f")) and lowered != "-f":
            source = value.split("=", 1)[1] if "=" in value else value[2:]
            if path_predicate(source):
                return True
            program_from_file = True
            program_seen = True
            index += 1
            continue
        if not program_seen and lowered in {"-l", "--library-path", "--indent"}:
            index += 2
            continue
        if not program_seen and value.startswith("-"):
            index += 1
            continue
        if not program_seen:
            program_seen = True
            index += 1
            continue
        if path_predicate(value):
            return True
        index += 1
    return False


def _jq_git_config_file_access(tokens: Sequence[str]) -> bool:
    return _jq_file_access(tokens, _git_config_metadata_path)


def _generic_mutator_git_metadata_access(tokens: Sequence[str]) -> bool:
    """Recognize path-bearing mutator operands, including attached options."""

    if not tokens:
        return False
    executable = Path(tokens[0]).name.lower()
    if executable not in GENERIC_GIT_METADATA_MUTATORS:
        return False
    if any(_git_admin_metadata_path(value) for value in tokens[1:]):
        return True
    separate_path_options = {
        "chmod": frozenset({"--reference"}),
        "cp": frozenset({"-t", "--target-directory"}),
        "install": frozenset({"-t", "--target-directory"}),
        "ln": frozenset({"-t", "--target-directory"}),
        "mv": frozenset({"-t", "--target-directory"}),
        "sed": frozenset({"-f", "--file"}),
        "touch": frozenset({"-r", "--reference"}),
    }.get(executable, frozenset())
    index = 1
    while index < len(tokens):
        value = tokens[index]
        lowered = value.lower()
        long_option = next(
            (
                option
                for option in separate_path_options
                if option.startswith("--") and _long_option_prefix(value, option)
            ),
            None,
        )
        if lowered in separate_path_options or (
            long_option is not None and "=" not in lowered
        ):
            if index + 1 < len(tokens) and _git_admin_metadata_path(tokens[index + 1]):
                return True
            index += 2
            continue
        if long_option is not None and "=" in lowered:
            if _git_admin_metadata_path(value.split("=", 1)[1]):
                return True
            index += 1
            continue
        for option in separate_path_options:
            if (
                option.startswith("-")
                and not option.startswith("--")
                and lowered.startswith(option)
                and lowered != option
            ):
                if _git_admin_metadata_path(value[len(option) :]):
                    return True
                break
        index += 1
    return False


def _shell_inline_body(tokens: Sequence[str]) -> str | None:
    """Return a shell -c body only while argv remains in option position."""

    if not tokens or Path(tokens[0]).name.lower() not in SHELL_NAMES:
        return None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return None
        if token in {"-O", "+O", "-o", "+o"}:
            if index + 1 >= len(tokens):
                return None
            index += 2
            continue
        if token == "-c":
            return tokens[index + 1] if index + 1 < len(tokens) else None
        if token.startswith("--"):
            shell_option = token.lower().split("=", 1)[0]
            if (
                len(shell_option) >= len("--i")
                and "--init-file".startswith(shell_option)
            ) or (
                len(shell_option) >= len("--rc") and "--rcfile".startswith(shell_option)
            ):
                return None
        if token.startswith("--"):
            index += 1
            continue
        if token.startswith("-") and token != "-":
            if token.startswith(("-O", "-o")):
                return None
            if "c" in token[1:]:
                return tokens[index + 1] if index + 1 < len(tokens) else None
            index += 1
            continue
        if token.startswith("+") and token != "+":
            index += 1
            continue
        # The first non-option token selects a script. Later -c text is an
        # argument to that script and must never be inspected as shell code.
        return None
    return None


def _shell_has_startup_dispatch(tokens: Sequence[str]) -> bool:
    """Detect shell modes that execute startup state before an inline body."""

    if not tokens or Path(tokens[0]).name.lower() not in SHELL_NAMES:
        return False
    if Path(tokens[0]).name.lower() == "zsh":
        return True
    for token in tokens[1:]:
        if token == "--":
            return False
        if token.startswith("--"):
            shell_option = token.lower().split("=", 1)[0]
            if shell_option in {"--login", "--interactive"} or (
                len(shell_option) >= len("--i")
                and "--init-file".startswith(shell_option)
            ) or (
                len(shell_option) >= len("--rc")
                and "--rcfile".startswith(shell_option)
            ):
                return True
            continue
        if token.startswith("-") and token != "-":
            if any(option in token[1:] for option in "il"):
                return True
            continue
        if token.startswith("+") and token != "+":
            continue
        return False
    return False


def _find_writes_git_metadata(tokens: Sequence[str]) -> bool:
    """Detect find output actions whose destination mutates private Git state."""

    if not tokens or Path(tokens[0]).name.lower() != "find":
        return False
    output_actions = {"-fls", "-fprint", "-fprint0", "-fprintf"}
    for index, token in enumerate(tokens[1:], start=1):
        if token.lower() not in output_actions:
            continue
        if index + 1 < len(tokens) and _git_admin_metadata_path(tokens[index + 1]):
            return True
    return False


def _uniq_writes_git_metadata(tokens: Sequence[str]) -> bool:
    """Detect uniq's optional positional output beneath private Git state."""

    if not tokens or Path(tokens[0]).name.lower() != "uniq":
        return False
    value_options = {
        "-f": "--skip-fields",
        "-s": "--skip-chars",
        "-w": "--check-chars",
    }
    operands: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()
        if token == "--":
            operands.extend(tokens[index + 1 :])
            break
        matched_long = next(
            (
                canonical
                for canonical in value_options.values()
                if _long_option_prefix(token, canonical)
            ),
            None,
        )
        if lowered in value_options or (matched_long is not None and "=" not in token):
            index += 2
            continue
        if matched_long is not None and "=" in token:
            index += 1
            continue
        if any(
            lowered.startswith(option) and lowered != option
            for option in value_options
        ):
            index += 1
            continue
        if token.startswith("-") and token != "-":
            index += 1
            continue
        operands.append(token)
        index += 1
    return len(operands) >= 2 and _git_admin_metadata_path(operands[1])


def _shell_tokenization_analysis(
    command: str,
) -> tuple[tuple[tuple[str, ...], ...], bool]:
    """Return bounded shell tokenizations plus incomplete-inspection state."""

    pending = [command]
    tokenizations: list[tuple[str, ...]] = []
    seen: set[str] = set()
    incomplete = False
    while pending and len(tokenizations) < SHELL_NESTING_INSPECTION_LIMIT:
        raw = pending.pop(0)
        if raw in seen:
            continue
        seen.add(raw)
        if "\n" in raw or "\r" in raw:
            incomplete = True
        if _shell_has_active_expansion(raw):
            incomplete = True
        try:
            lexer = shlex.shlex(raw, posix=True, punctuation_chars=";&|<>")
            lexer.whitespace_split = True
            lexer.commenters = ""
            tokens = tuple(lexer)
        except ValueError:
            incomplete = True
            continue
        if not tokens:
            continue
        tokenizations.append(tokens)
        for raw_segment in _command_segments(tokens):
            segment = _unwrap_command(raw_segment)
            if not segment or Path(segment[0]).name.lower() not in SHELL_NAMES:
                continue
            inline_body = _shell_inline_body(segment)
            if inline_body is not None:
                pending.append(inline_body)
    incomplete = incomplete or any(raw not in seen for raw in pending)
    return tuple(tokenizations), incomplete


def _shell_has_active_expansion(command: str) -> bool:
    """Detect shell expansions whose executed argv is absent from the event."""

    quote: str | None = None
    word_start = True
    index = 0
    while index < len(command):
        character = command[index]
        if quote == "'":
            if character == "'":
                quote = None
            index += 1
            continue
        if character == "\\":
            index += 2
            word_start = False
            continue
        if character == '"':
            quote = None if quote == '"' else '"'
            word_start = False
            index += 1
            continue
        if quote == '"':
            if character == "$":
                return True
            index += 1
            continue
        if character == "'":
            quote = "'"
            word_start = False
            index += 1
            continue
        if character == "$":
            return True
        if character in "*?[":
            return True
        if character in "@+!" and command[index + 1 : index + 2] == "(":
            return True
        if character == "{" and "}" in command[index + 1 :]:
            body = command[index + 1 : command.index("}", index + 1)]
            if "," in body or ".." in body:
                return True
        if character == "~" and word_start:
            return True
        if character.isspace() or character in SHELL_SEPARATORS:
            word_start = True
        else:
            word_start = False
        index += 1
    return False


def _executable_path_is_opaque(value: str) -> bool:
    """Admit only explicit, system-resolved model command executables."""

    executable = Path(value).name.lower()
    if executable not in CLASSIFIABLE_DIRECT_EXECUTABLES:
        return True
    resolved_value = (
        value if "/" in value else shutil.which(value, path=CODEX_EXECUTABLE_PATH)
    )
    if not resolved_value:
        return True
    candidate = Path(resolved_value)
    if not candidate.is_absolute() or ".." in candidate.parts:
        return True
    return not any(
        candidate.is_relative_to(root) for root in TRUSTED_EXECUTABLE_PREFIXES
    )


def _shell_tokenizations(command: str) -> tuple[tuple[str, ...], ...]:
    """Return bounded outer and nested shell tokenizations for one event."""

    return _shell_tokenization_analysis(command)[0]


def _command_segments(tokens: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    segments: list[tuple[str, ...]] = []
    current: list[str] = []
    for token in tokens:
        if token in SHELL_SEPARATORS:
            if current:
                segments.append(tuple(current))
                current = []
            continue
        current.append(token)
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def _unwrap_command(segment: Sequence[str]) -> tuple[str, ...]:
    """Strip common non-effectful launch wrappers from one shell segment."""

    values = list(segment)
    while values:
        executable = Path(values[0]).name
        if executable in {"command", "exec"}:
            values = values[1:]
            continue
        if executable == "env":
            index = 1
            while index < len(values):
                token = values[index]
                if token in {"-S", "--split-string"} or token.startswith(
                    "--split-string="
                ):
                    return ()
                if ENV_ASSIGNMENT_RE.match(token):
                    index += 1
                    continue
                if token in {"-i", "--ignore-environment", "-0", "--null"}:
                    index += 1
                    continue
                if token in {"-u", "--unset", "-C", "--chdir"}:
                    index += 2
                    continue
                if token.startswith(("--unset=", "--chdir=")):
                    index += 1
                    continue
                break
            if index < len(values) and values[index] == "--":
                index += 1
            values = values[index:]
            continue
        if executable == "timeout":
            index = 1
            while index < len(values):
                token = values[index]
                if token == "--":
                    index += 1
                    break
                if token in {"-k", "--kill-after", "-s", "--signal"}:
                    if index + 1 >= len(values):
                        return ()
                    index += 2
                    continue
                if token.startswith(("--kill-after=", "--signal=")) or re.fullmatch(
                    r"-(?:k|s).+", token
                ):
                    index += 1
                    continue
                if token in {"--foreground", "--preserve-status", "--verbose"}:
                    index += 1
                    continue
                if token.startswith("-"):
                    return ()
                break
            if index >= len(values):
                return ()
            index += 1
            values = values[index:]
            continue
        break
    return tuple(values)


def _unwrapped_prefix_has_environment_override(
    raw_segment: Sequence[str], unwrapped_segment: Sequence[str]
) -> bool:
    """Retain environment-bearing authority stripped with launch wrappers."""

    prefix_length = len(raw_segment) - len(unwrapped_segment)
    if prefix_length < 0 or tuple(raw_segment[prefix_length:]) != tuple(
        unwrapped_segment
    ):
        return True
    return any(
        Path(token).name.lower() == "env" or ENV_ASSIGNMENT_RE.match(token)
        for token in raw_segment[:prefix_length]
    )


def _git_subcommand(tokens: Sequence[str]) -> tuple[str | None, tuple[str, ...]]:
    index = 1
    options_with_value = {
        "-C",
        "-c",
        "--config-env",
        "--exec-path",
        "--git-dir",
        "--namespace",
        "--super-prefix",
        "--work-tree",
    }
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token in options_with_value:
            index += 2
            continue
        if any(
            token.startswith(option + "=")
            for option in options_with_value
            if option.startswith("--")
        ):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token, tuple(tokens[index + 1 :])
    if index < len(tokens):
        return tokens[index], tuple(tokens[index + 1 :])
    return None, ()


def _git_for_each_ref_has_signature_dispatch(git_args: Sequence[str]) -> bool:
    """Detect ref fields that dispatch the repository-configured verifier."""

    index = 0
    while index < len(git_args):
        token = git_args[index]
        lowered = token.lower()
        if lowered == "--":
            break
        option, separator, attached_value = lowered.partition("=")
        if len(option) >= len("--f") and "--format".startswith(option):
            if separator:
                field_value = attached_value
            else:
                index += 1
                if index >= len(git_args):
                    return True
                field_value = git_args[index].lower()
            if "%(signature" in field_value or "%(*signature" in field_value:
                return True
        elif len(option) >= len("--s") and "--sort".startswith(option):
            if separator:
                field_value = attached_value
            else:
                index += 1
                if index >= len(git_args):
                    return True
                field_value = git_args[index].lower()
            sort_field = field_value.lstrip("-")
            if sort_field.startswith("version:"):
                sort_field = sort_field[len("version:") :]
            elif sort_field.startswith("v:"):
                sort_field = sort_field[len("v:") :]
            if sort_field.lstrip("*").startswith("signature"):
                return True
        index += 1
    return False


def _git_revision_walk_has_signature_dispatch(git_args: Sequence[str]) -> bool:
    """Detect pretty formats that execute a configured signature verifier."""

    builtin_pretty_formats = {
        "email",
        "full",
        "fuller",
        "medium",
        "mboxrd",
        "oneline",
        "raw",
        "reference",
        "short",
    }
    index = 0
    while index < len(git_args):
        token = git_args[index]
        lowered = token.lower()
        if lowered == "--":
            break
        option, separator, attached_value = token.partition("=")
        lowered_option = option.lower()
        if len(lowered_option) >= len("--show-s") and "--show-signature".startswith(
            lowered_option
        ):
            return True
        is_format = lowered_option == "--format"
        is_pretty = lowered_option == "--pretty"
        is_abbreviated_format = (
            len(lowered_option) >= len("--f")
            and "--format".startswith(lowered_option)
            and not is_format
        )
        is_abbreviated_pretty = (
            len(lowered_option) >= len("--p")
            and "--pretty".startswith(lowered_option)
            and not is_pretty
        )
        if is_abbreviated_format or is_abbreviated_pretty:
            return True
        if is_pretty and not separator:
            # Bare --pretty has no following value. In particular, do not
            # swallow a subsequent --show-signature option.
            if index + 1 < len(git_args) and re.search(
                r"%G(?:\?|[A-Z])", git_args[index + 1]
            ):
                return True
            index += 1
            continue
        if is_format or is_pretty:
            if not separator:
                # --format requires an attached value. Ambiguous/invalid
                # spellings are not part of the admitted command surface.
                return True
            format_value = attached_value
            normalized_format = format_value.lower()
            if re.search(r"%G(?:\?|[A-Z])", format_value):
                return True
            if not (
                "%" in format_value
                or normalized_format.startswith(("format:", "tformat:"))
                or normalized_format in builtin_pretty_formats
            ):
                # Any other name may resolve repository-local pretty.<name>
                # configuration, whose expansion can contain %G placeholders.
                return True
        index += 1
    return False


def _git_has_opaque_dispatch(tokens: Sequence[str]) -> bool:
    """Reject config-driven aliases and external git-subcommand dispatch."""

    # Git help can dispatch repository/user-configured man viewers and commands.
    if any(token.lower() in {"--help", "-h"} for token in tokens[1:]):
        return True

    for token in tokens[1:]:
        if token == "--":
            break
        if token in GIT_OPAQUE_GLOBAL_OPTIONS:
            return True
        if token.startswith(("-C", "-c")) and token not in {"-C", "-c"}:
            return True
        if any(
            token.startswith(option + "=")
            for option in GIT_OPAQUE_GLOBAL_OPTIONS
            if option.startswith("--")
        ):
            return True
        if not token.startswith("-"):
            break
    subcommand, git_args = _git_subcommand(tokens)
    if subcommand is None:
        return not any(token in {"--help", "--version"} for token in tokens[1:])
    if subcommand == "config":
        # Repository, worktree, global, and system config may contain
        # credentials or command-bearing values. The event exposes neither
        # the selected source nor the returned value, so model-issued reads
        # and writes are both opaque.
        return True
    if subcommand in GIT_HIDDEN_STATE_MUTATOR_SUBCOMMANDS:
        return True
    if subcommand == "remote":
        positional = tuple(
            value.lower() for value in git_args if not value.startswith("-")
        )
        # Only listing configured names is admitted. Verbose listing and URL
        # resolution can expose embedded credentials; subcommands can mutate
        # config/refs or dispatch a repository-configured transport.
        if positional or any(
            value.lower() in {"-v", "--verbose"} for value in git_args
        ):
            return True
    if subcommand == "symbolic-ref":
        positional = tuple(
            value.lower() for value in git_args if not value.startswith("-")
        )
        if any(
            value.lower() == "-d"
            or (
                len(value.lower().split("=", 1)[0]) >= len("--d")
                and "--delete".startswith(value.lower().split("=", 1)[0])
            )
            for value in git_args
        ):
            return True
        if len(positional) != 1:
            return True
    if subcommand == "reflog":
        positional = tuple(
            value.lower() for value in git_args if not value.startswith("-")
        )
        operation = (
            positional[0]
            if positional
            and positional[0]
            in {"delete", "drop", "exists", "expire", "list", "show", "write"}
            else None
        )
        if operation in {"delete", "drop", "expire", "write"}:
            return True
        if (operation in {None, "show"}) and _git_revision_walk_has_signature_dispatch(
            git_args
        ):
            return True
    if subcommand == "for-each-ref" and _git_for_each_ref_has_signature_dispatch(
        git_args
    ):
        return True
    if subcommand == "rev-list" and _git_revision_walk_has_signature_dispatch(git_args):
        return True
    if subcommand in GIT_CONFIG_DRIVEN_HELPER_SUBCOMMANDS:
        return True
    if subcommand in GIT_FILTER_RUNNING_SUBCOMMANDS:
        return True
    if subcommand == "cat-file" and any(
        (
            len(value.lower().split("=", 1)[0]) >= len("--fi")
            and "--filters".startswith(value.lower().split("=", 1)[0])
        )
        or (
            len(value.lower().split("=", 1)[0]) >= len("--te")
            and "--textconv".startswith(value.lower().split("=", 1)[0])
        )
        for value in git_args
    ):
        return True
    if subcommand == "grep" and "--textconv" in {value.lower() for value in git_args}:
        return True
    if subcommand == "hash-object":
        try:
            option_terminator = git_args.index("--")
        except ValueError:
            option_args = git_args
        else:
            option_args = git_args[:option_terminator]
        if any(
            len(value.lower().split("=", 1)[0]) >= len("--pa")
            and "--path".startswith(value.lower().split("=", 1)[0])
            for value in option_args
        ):
            return True
        if any(
            value.lower() == "--literally"
            or (
                value.lower().startswith("-")
                and not value.lower().startswith("--")
                and "w" in value.lower()[1:]
            )
            for value in option_args
        ):
            return True
        # Hashing a workspace path applies clean filters unless the caller
        # explicitly selects Git's byte-preserving mode. A late repository
        # config writer can otherwise add a helper after environment setup.
        if any(
            len(value.lower().split("=", 1)[0]) >= len("--f")
            and "--filters".startswith(value.lower().split("=", 1)[0])
            for value in option_args
        ):
            return True
        if "--no-filters" not in {value.lower() for value in option_args}:
            return True
    if subcommand == "fsck" and any(
        len(value.lower().split("=", 1)[0]) >= len("--lo")
        and "--lost-found".startswith(value.lower().split("=", 1)[0])
        for value in git_args
    ):
        return True
    return subcommand not in GIT_DIRECT_BUILTIN_SUBCOMMANDS


def _sed_has_opaque_dispatch(tokens: Sequence[str]) -> bool:
    """Require GNU sed's enforced no-exec/no-file-write language mode."""

    return "--sandbox" not in tokens[1:]


def _ripgrep_has_opaque_dispatch(tokens: Sequence[str]) -> bool:
    """Reject ripgrep modes that launch an unobserved helper process."""

    for token in tokens[1:]:
        lowered = token.lower()
        if lowered == "--":
            break
        if lowered in {"--hostname-bin=", "--pre="}:
            continue
        if lowered in {
            "--hostname-bin",
            "--pre",
            "--search-zip",
        } or lowered.startswith(("--hostname-bin=", "--pre=")):
            return True
        if (
            lowered.startswith("-")
            and not lowered.startswith("--")
            and "z" in lowered[1:]
        ):
            return True
    return False


def _jq_has_opaque_environment_access(tokens: Sequence[str]) -> bool:
    """Reject jq programs that can read the inherited process environment."""

    index = 1
    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()
        if token == "--":
            index += 1
            break
        if (
            lowered in {"-f", "-l", "--from-file", "--run-tests"}
            or (lowered.startswith(("-f", "-l")) and len(lowered) > 2)
            or lowered.startswith(("--from-file=", "--run-tests="))
        ):
            return True
        if lowered in {"--arg", "--argjson", "--rawfile", "--slurpfile"}:
            index += 3
            continue
        if lowered == "--indent":
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    if index >= len(tokens):
        return False
    program = tokens[index]
    return (
        re.search(
            r"(?<![A-Za-z0-9_.$\"'])env(?![A-Za-z0-9_])|\$ENV(?![A-Za-z0-9_])",
            program,
        )
        is not None
    )


def _sort_has_opaque_dispatch(tokens: Sequence[str]) -> bool:
    """Reject GNU sort modes that launch an unobserved compression program."""

    for token in tokens[1:]:
        lowered = token.lower()
        if lowered == "--":
            break
        option = lowered.split("=", 1)[0]
        if len(option) >= len("--co") and "--compress-program".startswith(option):
            return True
    return False


def _sort_writes_git_metadata(tokens: Sequence[str]) -> bool:
    """Detect GNU sort output destinations that mutate private Git state."""

    index = 1
    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()
        if token == "--":
            break
        if lowered == "-o" or (
            _long_option_prefix(token, "--output") and "=" not in token
        ):
            if index + 1 < len(tokens) and _git_admin_metadata_path(
                tokens[index + 1]
            ):
                return True
            index += 2
            continue
        if lowered.startswith("-o") and not lowered.startswith("--"):
            if _git_admin_metadata_path(token[2:]):
                return True
        elif _long_option_prefix(token, "--output") and "=" in token:
            if _git_admin_metadata_path(token.split("=", 1)[1]):
                return True
        index += 1
    return False


def _command_matches_argv(command: str, expected: Sequence[str]) -> bool:
    expected_tokens = tuple(str(value) for value in expected)
    for tokens in _shell_tokenizations(command):
        segments = _command_segments(tokens)
        if len(segments) == 1 and segments[0] == expected_tokens:
            return True
    return False


def _validation_cwd(workspace: str | Path, command_spec: Mapping[str, Any]) -> Path:
    root = Path(workspace).resolve()
    relative = str(command_spec["cwd"])
    candidate = root if relative == "." else root.joinpath(*relative.split("/"))
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ExternalCodexRuntimeError(
            "task_validation_cwd_invalid",
            "fixed validation cwd is absent or outside the exact workspace",
        ) from exc
    if not resolved.is_dir():
        raise ExternalCodexRuntimeError(
            "task_validation_cwd_invalid",
            "fixed validation cwd is not a workspace directory",
        )
    return resolved


def _validation_wrapper_argv(
    workspace: str | Path,
    command_spec: Mapping[str, Any],
) -> tuple[str, ...]:
    """Bind one fixed argv to an explicit, observable workspace cwd."""

    cwd = _validation_cwd(workspace, command_spec)
    return (
        "/usr/bin/env",
        "-C",
        str(cwd),
        "--",
        *(str(value) for value in command_spec["argv"]),
    )


def _descriptor_validation_cwd(
    workspace_coordinate: str | Path,
    command_spec: Mapping[str, Any],
) -> Path:
    """Map an already-admitted relative cwd onto the child's stable coordinate."""

    root = Path(workspace_coordinate)
    relative = str(command_spec["cwd"])
    if (
        not root.is_absolute()
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise ExternalCodexRuntimeError(
            "task_validation_cwd_invalid",
            "descriptor-bound validation cwd is outside the child coordinate",
        )
    return root if relative == "." else root.joinpath(*Path(relative).parts)


def _descriptor_validation_wrapper_argv(
    workspace_coordinate: str | Path,
    command_spec: Mapping[str, Any],
) -> tuple[str, ...]:
    cwd = _descriptor_validation_cwd(workspace_coordinate, command_spec)
    return (
        "/usr/bin/env",
        "-C",
        str(cwd),
        "--",
        *(str(value) for value in command_spec["argv"]),
    )


def _annotate_validation_executions(
    commands: Sequence[Mapping[str, Any]],
    *,
    task: Mapping[str, Any],
    workspace: str | Path,
    descriptor_bound_coordinate: bool = False,
) -> list[dict[str, Any]]:
    """Attach runtime-derived argv/cwd provenance to exact validation events."""

    specs = tuple(task["validation_commands"])
    if descriptor_bound_coordinate:
        root = Path(workspace)
        wrappers = tuple(
            _descriptor_validation_wrapper_argv(root, item) for item in specs
        )
    else:
        root = _validation_cwd(workspace, {"cwd": "."})
        wrappers = tuple(_validation_wrapper_argv(workspace, item) for item in specs)
    annotated: list[dict[str, Any]] = []
    for item in commands:
        record = {
            key: value
            for key, value in item.items()
            if key
            not in {
                "validation_command_id",
                "validation_argv",
                "validation_cwd",
                "validation_wrapper_argv",
            }
        }
        command = str(record.get("command") or "")
        matches = [
            (spec, wrapper)
            for spec, wrapper in zip(specs, wrappers, strict=True)
            if _command_matches_argv(command, wrapper)
        ]
        if len(matches) > 1:
            raise ExternalCodexRuntimeError(
                "task_validation_command_ambiguous",
                "one command event matched multiple fixed validation identities",
            )
        if matches:
            spec, wrapper = matches[0]
            record.update(
                {
                    "validation_command_id": str(spec["command_id"]),
                    "validation_argv": [str(value) for value in spec["argv"]],
                    "validation_cwd": str(
                        _descriptor_validation_cwd(root, spec)
                        if descriptor_bound_coordinate
                        else _validation_cwd(workspace, spec)
                    ),
                    "validation_wrapper_argv": list(wrapper),
                }
            )
        annotated.append(record)
    return annotated


def _command_effects(command: str) -> set[str]:
    """Classify high-risk command families without trusting shell spelling."""

    detected: set[str] = set()
    for tokenization in _shell_tokenizations(command):
        for raw_segment in _command_segments(tokenization):
            if not raw_segment:
                continue
            raw_executable = Path(raw_segment[0]).name.lower()
            if raw_executable in {"doas", "sudo"}:
                detected.add("global_config_mutation")
                segment = _unwrap_command(raw_segment[1:])
            else:
                segment = _unwrap_command(raw_segment)
            if not segment:
                if raw_executable == "env":
                    detected.add("secret_access")
                continue
            executable = Path(segment[0]).name.lower()
            args = tuple(value.lower() for value in segment[1:])

            if executable == "git":
                subcommand, git_args = _git_subcommand(segment)
                lowered = tuple(value.lower() for value in git_args)
                if subcommand == "commit":
                    detected.add("commit")
                elif subcommand == "push":
                    detected.add("push")
                elif subcommand == "merge":
                    detected.add("merge")
                elif subcommand == "tag" and _git_tag_is_mutating(git_args):
                    detected.add("tag")
                elif subcommand == "config" and any(
                    value in {"--global", "--system"} for value in lowered
                ):
                    detected.add("global_config_mutation")
                elif subcommand == "credential":
                    detected.add("secret_access")
            elif executable == "jq" and _jq_has_opaque_environment_access(segment):
                detected.add("secret_access")
            elif executable == "gh":
                if any(
                    args[index : index + 2] == ("pr", "create")
                    for index in range(len(args))
                ):
                    detected.add("pull_request")
                elif any(
                    args[index : index + 2] == ("pr", "merge")
                    for index in range(len(args))
                ):
                    detected.add("merge")
                elif "release" in args:
                    detected.add("release")

            if (
                (executable in {"cargo", "npm", "pnpm"} and "publish" in args)
                or (executable == "yarn" and "publish" in args)
                or (executable == "twine" and args[:1] == ("upload",))
                or (executable in {"docker", "podman"} and "push" in args)
                or executable in {"scp", "sftp"}
                or (
                    executable == "rsync" and any(":" in value for value in segment[1:])
                )
                or executable in {"curl", "wget"}
            ):
                detected.add("publication")

            if (
                (
                    executable == "systemctl"
                    and any(
                        value
                        in {
                            "daemon-reload",
                            "disable",
                            "enable",
                            "mask",
                            "reload",
                            "restart",
                            "start",
                            "stop",
                            "unmask",
                        }
                        for value in args
                    )
                )
                or (
                    executable in {"docker", "podman"}
                    and any(
                        value
                        in {
                            "down",
                            "kill",
                            "rm",
                            "restart",
                            "run",
                            "start",
                            "stop",
                            "up",
                        }
                        for value in args
                    )
                )
                or (
                    executable == "kubectl"
                    and args[:1]
                    in {
                        ("apply",),
                        ("create",),
                        ("delete",),
                        ("patch",),
                        ("replace",),
                        ("rollout",),
                        ("scale",),
                    }
                )
                or executable in {"launchctl", "service", "supervisorctl"}
            ):
                detected.add("service_mutation")

            if (
                executable in {"op", "pass", "secret-tool", "vault"}
                or (
                    executable in {"aws", "gcloud"}
                    and any("secret" in value for value in args)
                )
                or executable in {"printenv"}
            ):
                detected.add("secret_access")
            if _direct_git_config_file_access(segment):
                detected.add("secret_access")
            if _reader_secret_file_access(segment):
                detected.add("secret_access")
            if any(
                _argument_secret_access(executable, value) for value in segment[1:]
            ):
                detected.add("secret_access")

            writes_system_path = any(
                value.startswith(SYSTEM_PATH_PREFIXES) for value in segment[1:]
            )
            sed_in_place = executable == "sed" and any(
                value == "-i"
                or value.startswith("-i")
                or value.startswith("--in-place")
                for value in args
            )
            if (
                executable in {"apt", "apt-get", "dnf", "pacman", "rpm", "yum"}
                or (executable == "pip" and "install" in args)
                or (executable == "cargo" and "install" in args)
                or (
                    executable in {"cp", "install", "ln", "mkdir", "mv", "rm", "tee"}
                    and writes_system_path
                )
                or (sed_in_place and writes_system_path)
            ):
                detected.add("global_config_mutation")
    return detected


def _git_tag_is_mutating(args: Sequence[str]) -> bool:
    """Separate ordinary tag listing from tag creation, deletion, or signing."""

    lowered = tuple(value.lower() for value in args)
    if not lowered:
        return False
    mutation_modes = {
        "-a",
        "--annotate",
        "-d",
        "--delete",
        "-f",
        "--force",
        "-s",
        "--sign",
        "-u",
        "--local-user",
        "--create-reflog",
    }
    if any(
        value in mutation_modes
        or any(value.startswith(prefix + "=") for prefix in mutation_modes)
        for value in lowered
    ):
        return True
    read_only_modes = {
        "-l",
        "--list",
        "--contains",
        "--no-contains",
        "--merged",
        "--no-merged",
        "--points-at",
    }
    if any(
        value in read_only_modes
        or any(value.startswith(prefix + "=") for prefix in read_only_modes)
        for value in lowered
    ):
        return False
    return True


def _sandbox_confined_indirection_is_admitted(
    task: Mapping[str, Any],
    binding: Any,
) -> bool:
    """Admit opaque local work only under an exact deny-external sandbox binding."""

    if task.get("indirect_command_policy") != "sandbox_confined":
        return False
    posture = getattr(binding, "permission_posture", None)
    if posture is None:
        return False
    sandbox_mode = getattr(posture, "sandbox_mode", None)
    expected_sandbox = (
        "read_only"
        if task.get("allowed_effect_class") == "read_only"
        else "workspace_write"
    )
    return bool(
        sandbox_mode == expected_sandbox
        and getattr(posture, "approval_policy", None) == "never"
        and getattr(posture, "network_access", None) == "disabled"
        and getattr(posture, "secret_access", None) is False
        and getattr(posture, "external_effects", None) is False
    )


def _command_has_unclassified_indirection(command: str) -> bool:
    """Identify executable command bodies that argv inspection cannot classify."""

    if "$(" in command or "`" in command or "<(" in command or ">(" in command:
        return True
    tokenizations, incomplete = _shell_tokenization_analysis(command)
    if not tokenizations or incomplete:
        return True
    for tokenization in tokenizations:
        if any(
            token not in SHELL_SEPARATORS
            and any(character in token for character in SHELL_REDIRECTION_CHARS)
            for token in tokenization
        ):
            return True
        for raw_segment in _command_segments(tokenization):
            if not raw_segment:
                continue
            raw_executable = Path(raw_segment[0]).name.lower()
            if raw_executable == "env" or ENV_ASSIGNMENT_RE.match(raw_segment[0]):
                return True
            if raw_executable in OPAQUE_BUILD_AND_TASK_RUNNERS:
                return True
            if _executable_path_is_opaque(raw_segment[0]):
                return True
            if raw_executable in SHELL_NAMES:
                if _shell_has_startup_dispatch(raw_segment) or (
                    _shell_inline_body(raw_segment) is None
                ):
                    return True
                continue
            segment = _unwrap_command(raw_segment)
            if not segment:
                return True
            if _unwrapped_prefix_has_environment_override(raw_segment, segment):
                return True
            executable = Path(segment[0]).name.lower()
            args = tuple(value.lower() for value in segment[1:])
            if _executable_path_is_opaque(segment[0]):
                return True
            if executable in SHELL_NAMES:
                if _shell_has_startup_dispatch(segment) or (
                    _shell_inline_body(segment) is None
                ):
                    return True
                continue
            if segment[0] == "." or executable == "source":
                return True
            if executable in (
                OPAQUE_EFFECT_EXECUTABLES
                | OPAQUE_PROCESS_LAUNCH_WRAPPERS
                | OPAQUE_BUILD_AND_TASK_RUNNERS
            ):
                return True
            if executable == "git" and _git_has_opaque_dispatch(segment):
                return True
            if executable == "sed" and _sed_has_opaque_dispatch(segment):
                return True
            if executable == "rg" and _ripgrep_has_opaque_dispatch(segment):
                return True
            if executable == "jq" and _jq_has_opaque_environment_access(segment):
                return True
            if executable == "sort" and _sort_has_opaque_dispatch(segment):
                return True
            if executable == "sort" and _sort_writes_git_metadata(segment):
                return True
            if executable == "find" and _find_writes_git_metadata(segment):
                return True
            if executable == "uniq" and _uniq_writes_git_metadata(segment):
                return True
            if _direct_git_config_file_access(segment):
                return True
            if _generic_mutator_git_metadata_access(segment):
                return True
            if executable == "find" and any(
                value in {"-exec", "-execdir", "-ok", "-okdir"} for value in args
            ):
                return True
            if executable in {"eval", "xargs"}:
                return True
    return False


def _base_controller_git_environment() -> dict[str, str]:
    return {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "7",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_KEY_1": "core.fsmonitor",
        "GIT_CONFIG_KEY_2": "core.attributesFile",
        "GIT_CONFIG_KEY_3": "gpg.program",
        "GIT_CONFIG_KEY_4": "gpg.openpgp.program",
        "GIT_CONFIG_KEY_5": "gpg.x509.program",
        "GIT_CONFIG_KEY_6": "gpg.ssh.program",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_VALUE_0": "/dev/null",
        "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_VALUE_2": "/dev/null",
        "GIT_CONFIG_VALUE_3": "/usr/bin/false",
        "GIT_CONFIG_VALUE_4": "/usr/bin/false",
        "GIT_CONFIG_VALUE_5": "/usr/bin/false",
        "GIT_CONFIG_VALUE_6": "/usr/bin/false",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
        "PATH": CODEX_EXECUTABLE_PATH,
    }


def _controller_git_environment(workspace: Path) -> dict[str, str]:
    """Disable every repository-defined content filter for controller probes."""

    environment = _base_controller_git_environment()
    completed = subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(workspace),
            "config",
            "--local",
            "--includes",
            "--name-only",
            "--null",
            "--get-regexp",
            r"^filter\..*\.(clean|smudge|process|required)$",
        ],
        capture_output=True,
        check=False,
        timeout=15,
        env=environment,
    )
    if completed.returncode not in {0, 1}:
        raise ExternalCodexRuntimeError(
            "workspace_filter_config_failed",
            "cannot enumerate repository-defined Git content filters",
        )
    try:
        keys = sorted(
            {raw.decode("utf-8") for raw in completed.stdout.split(b"\0") if raw}
        )
    except UnicodeDecodeError as exc:
        raise ExternalCodexRuntimeError(
            "workspace_filter_config_failed",
            "repository-defined Git filter key is not UTF-8",
        ) from exc
    if len(keys) > 128 or any(
        re.fullmatch(r"filter\..+\.(?:clean|smudge|process|required)", key, re.I)
        is None
        for key in keys
    ):
        raise ExternalCodexRuntimeError(
            "workspace_filter_config_failed",
            "repository-defined Git filter keys exceed the bounded grammar",
        )
    next_index = int(environment["GIT_CONFIG_COUNT"])
    for key in keys:
        environment[f"GIT_CONFIG_KEY_{next_index}"] = key
        environment[f"GIT_CONFIG_VALUE_{next_index}"] = (
            "false" if key.lower().endswith(".required") else ""
        )
        next_index += 1
    environment["GIT_CONFIG_COUNT"] = str(next_index)
    return environment


def _repository_git_path(workspace: Path, name: str) -> Path:
    """Resolve one Git-owned path without trusting repository shell helpers."""

    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(workspace), "rev-parse", "--git-path", name],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
        env=_controller_git_environment(workspace),
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value or "\n" in value or "\r" in value:
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_unavailable",
            f"cannot resolve repository Git metadata path: {name}",
        )
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    return candidate.absolute()


def _physical_git_metadata_file(
    path: Path,
    *,
    purpose: str,
    required: bool,
) -> Path | None:
    """Admit only one non-aliased physical Git metadata file."""

    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        if not required:
            return None
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_unavailable",
            f"required repository {purpose} is absent",
        ) from None
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_unavailable",
            f"cannot inspect repository {purpose}",
        ) from exc
    if (
        not stat.S_ISREG(path_stat.st_mode)
        or path.is_symlink()
        or path_stat.st_nlink != 1
    ):
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_aliased",
            f"repository {purpose} must be one non-aliased regular file",
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_unavailable",
            f"cannot resolve repository {purpose}",
        ) from exc
    return resolved


def _repository_git_output(
    workspace: Path,
    *args: str,
    allowed_returncodes: frozenset[int] = frozenset({0}),
) -> tuple[int, str]:
    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(workspace), *args],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
        env=_controller_git_environment(workspace),
    )
    value = completed.stdout.strip()
    if (
        completed.returncode not in allowed_returncodes
        or "\n" in value
        or "\r" in value
    ):
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_unavailable",
            "cannot resolve one bounded repository Git coordinate",
        )
    return completed.returncode, value


def _repository_config_value(
    workspace: Path,
    key: str,
    *,
    boolean: bool = False,
    normalize_lower: bool = True,
) -> str | None:
    arguments = ["config"]
    if boolean:
        arguments.append("--bool")
    arguments.extend(("--get", key))
    returncode, value = _repository_git_output(
        workspace,
        *arguments,
        allowed_returncodes=frozenset({0, 1}),
    )
    if returncode == 1:
        if value:
            raise ExternalCodexRuntimeError(
                "workspace_git_metadata_invalid",
                f"repository {key} has an ambiguous absent value",
            )
        return None
    if not value:
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_invalid",
            f"repository {key} has an empty structural value",
        )
    return value.lower() if normalize_lower else value


def _git_config_quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _sanitized_repository_config(workspace: Path) -> str:
    """Retain only structural Git settings with closed value grammars."""

    format_version = _repository_config_value(workspace, "core.repositoryformatversion")
    if format_version is None:
        format_version = "0"
    if format_version not in {"0", "1"}:
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_invalid",
            "repository format version is outside the admitted grammar",
        )

    configured_worktree = _repository_config_value(
        workspace,
        "core.worktree",
        normalize_lower=False,
    )
    preserved_worktree: str | None = None
    if configured_worktree is not None:
        _, top_level = _repository_git_output(
            workspace,
            "rev-parse",
            "--show-toplevel",
        )
        try:
            resolved_top_level = Path(top_level).resolve(strict=True)
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "workspace_git_metadata_invalid",
                "repository core.worktree does not resolve to one worktree",
            ) from exc
        if resolved_top_level != workspace.resolve(strict=True):
            raise ExternalCodexRuntimeError(
                "workspace_git_metadata_invalid",
                "repository core.worktree redirects Git outside the exact workspace",
            )
        preserved_worktree = str(resolved_top_level)

    boolean_values: dict[str, str] = {}
    for key in SAFE_GIT_BOOLEAN_CONFIG_KEYS:
        value = _repository_config_value(workspace, key, boolean=True)
        if value is not None:
            if value not in {"true", "false"}:
                raise ExternalCodexRuntimeError(
                    "workspace_git_metadata_invalid",
                    f"repository {key} is not a bounded boolean",
                )
            boolean_values[key] = value

    enum_values: dict[str, str] = {}
    for key, allowed_values in SAFE_GIT_ENUM_CONFIG_KEYS.items():
        value = _repository_config_value(workspace, key)
        if value is not None:
            if value not in allowed_values:
                raise ExternalCodexRuntimeError(
                    "workspace_git_metadata_invalid",
                    f"repository {key} is outside the admitted grammar",
                )
            enum_values[key] = value

    core_names = {
        "core.filemode": "fileMode",
        "core.ignorecase": "ignoreCase",
        "core.precomposeunicode": "precomposeUnicode",
        "core.sparsecheckout": "sparseCheckout",
        "core.sparsecheckoutcone": "sparseCheckoutCone",
        "core.symlinks": "symlinks",
    }
    extension_names = {
        "extensions.compatobjectformat": "compatObjectFormat",
        "extensions.objectformat": "objectFormat",
        "extensions.refstorage": "refStorage",
        "extensions.relativeworktrees": "relativeWorktrees",
        "extensions.worktreeconfig": "worktreeConfig",
    }
    lines = [
        "[core]",
        f"\trepositoryFormatVersion = {format_version}",
        "\tbare = false",
        f"\tfileMode = {boolean_values.get('core.filemode', 'true')}",
    ]
    if preserved_worktree is not None:
        lines.append(f"\tworkTree = {_git_config_quoted(preserved_worktree)}")
    for key, name in core_names.items():
        if key == "core.filemode":
            continue
        if key in boolean_values:
            lines.append(f"\t{name} = {boolean_values[key]}")
    lines.extend(
        (
            "\thooksPath = /dev/null",
            "\tfsmonitor = false",
            "\tattributesFile = /dev/null",
        )
    )
    extension_values = {**enum_values, **boolean_values}
    selected_extensions = [
        (key, extension_names[key], extension_values[key])
        for key in extension_names
        if key in extension_values
    ]
    if selected_extensions:
        lines.append("[extensions]")
        lines.extend(f"\t{name} = {value}" for _, name, value in selected_extensions)
    lines.extend(
        (
            "[diff]",
            "\tignoreSubmodules = all",
            "[status]",
            "\tsubmoduleSummary = false",
        )
    )
    return "\n".join(lines) + "\n"


def _decode_mountinfo_path(value: str) -> str:
    escapes = {"040": " ", "011": "\t", "012": "\n", "134": "\\"}
    return re.sub(r"\\(040|011|012|134)", lambda match: escapes[match.group(1)], value)


def _current_mount_aliases(
    path: Path,
    *,
    required: bool = True,
) -> tuple[Path, ...]:
    """Enumerate current mount coordinates for an existing or reserved path."""

    target = path.absolute()
    try:
        target_stat = target.stat()
    except FileNotFoundError:
        target_stat = None
        if required:
            raise ExternalCodexRuntimeError(
                "workspace_git_metadata_unavailable",
                "required repository config coordinate is absent",
            ) from None
        try:
            target = target.parent.resolve(strict=True) / target.name
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "workspace_git_metadata_unavailable",
                "cannot resolve a reserved repository config coordinate",
            ) from exc
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_unavailable",
            "cannot inspect a repository config coordinate",
        ) from exc
    try:
        raw_mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_unavailable",
            "cannot inspect current repository mount aliases",
        ) from exc
    if target_stat is not None and not stat.S_ISREG(target_stat.st_mode):
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_aliased",
            "repository config mount target is not a regular file",
        )
    entries: list[tuple[int, str, Path, Path]] = []
    for line in raw_mountinfo.splitlines():
        left, separator, _ = line.partition(" - ")
        fields = left.split()
        if not separator or len(fields) < 6:
            raise ExternalCodexRuntimeError(
                "workspace_git_metadata_unavailable",
                "current mount table has an unsupported record",
            )
        root = Path(_decode_mountinfo_path(fields[3]))
        mountpoint = Path(_decode_mountinfo_path(fields[4]))
        if not root.is_absolute() or not mountpoint.is_absolute():
            raise ExternalCodexRuntimeError(
                "workspace_git_metadata_unavailable",
                "current mount table contains a relative coordinate",
            )
        try:
            mount_id = int(fields[0])
        except ValueError as exc:
            raise ExternalCodexRuntimeError(
                "workspace_git_metadata_unavailable",
                "current mount table has an invalid mount identity",
            ) from exc
        entries.append((mount_id, fields[2], root, mountpoint))

    covering: list[tuple[int, int, str, Path]] = []
    for mount_id, entry_device, root, mountpoint in entries:
        try:
            relative = target.relative_to(mountpoint)
        except ValueError:
            continue
        covering.append(
            (len(mountpoint.parts), mount_id, entry_device, root / relative)
        )
    if not covering:
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_unavailable",
            "repository config has no matching current mount coordinate",
        )
    _, _, device, internal_path = max(covering, key=lambda item: (item[0], item[1]))
    if target_stat is not None and device != (
        f"{os.major(target_stat.st_dev)}:{os.minor(target_stat.st_dev)}"
    ):
        raise ExternalCodexRuntimeError(
            "workspace_git_metadata_unavailable",
            "repository config inode differs from its active mount coordinate",
        )

    aliases = {target}
    for _, entry_device, root, mountpoint in entries:
        if entry_device != device:
            continue
        try:
            relative = internal_path.relative_to(root)
        except ValueError:
            continue
        candidate = (mountpoint / relative).absolute()
        try:
            candidate_stat = candidate.stat()
        except FileNotFoundError:
            if target_stat is not None:
                continue
            try:
                parent_stat = candidate.parent.stat()
            except OSError:
                continue
            if (
                stat.S_ISDIR(parent_stat.st_mode)
                and f"{os.major(parent_stat.st_dev)}:{os.minor(parent_stat.st_dev)}"
                == device
            ):
                aliases.add(candidate)
            continue
        except OSError:
            continue
        if target_stat is None:
            raise ExternalCodexRuntimeError(
                "workspace_git_metadata_aliased",
                "reserved repository config coordinate has inconsistent aliases",
            )
        if stat.S_ISREG(candidate_stat.st_mode) and (
            candidate_stat.st_dev == target_stat.st_dev
            and candidate_stat.st_ino == target_stat.st_ino
        ):
            aliases.add(candidate)
    return tuple(sorted(aliases))


PRIVATE_VIEW_IDENTITY_FIELDS = (
    "device",
    "inode",
    "mode",
    "size",
    "mtime_ns",
    "ctime_ns",
)


def _private_view_identity(observed: os.stat_result) -> dict[str, int]:
    return {
        "device": observed.st_dev,
        "inode": observed.st_ino,
        "mode": observed.st_mode,
        "size": observed.st_size,
        "mtime_ns": observed.st_mtime_ns,
        "ctime_ns": observed.st_ctime_ns,
    }


def _assert_private_view_identity(
    path: Path,
    expected: Mapping[str, Any],
    *,
    directory: bool,
) -> os.stat_result:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "actor_git_mask_unavailable",
            "private Git metadata view changed before containment",
        ) from exc
    expected_keys = set(PRIVATE_VIEW_IDENTITY_FIELDS)
    if (
        set(expected) != expected_keys
        or any(not isinstance(expected[key], int) for key in expected_keys)
        or _private_view_identity(observed) != dict(expected)
        or path.is_symlink()
        or (directory and not stat.S_ISDIR(observed.st_mode))
        or (not directory and not stat.S_ISREG(observed.st_mode))
    ):
        raise ExternalCodexRuntimeError(
            "actor_git_mask_unavailable",
            "private Git metadata view identity drifted before containment",
        )
    return observed


def _private_directory_views(
    masks: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    """Describe namespace-private parent views for every masked coordinate."""

    grouped: dict[Path, set[str]] = {}
    for mask in masks:
        target = Path(str(mask["target"]))
        if not target.is_absolute() or target.name in {"", ".", ".."}:
            raise ExternalCodexRuntimeError(
                "actor_git_mask_unavailable",
                "external actor Git mask has an invalid target coordinate",
            )
        grouped.setdefault(target.parent, set()).add(target.name)
    views: list[dict[str, Any]] = []
    for parent, masked_names in sorted(
        grouped.items(), key=lambda item: (len(item[0].parts), str(item[0]))
    ):
        try:
            parent_stat = parent.lstat()
            directory_entries = tuple(
                sorted(parent.iterdir(), key=lambda path: path.name)
            )
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "actor_git_mask_unavailable",
                "cannot inspect one private Git metadata view",
            ) from exc
        if parent.is_symlink() or not stat.S_ISDIR(parent_stat.st_mode):
            raise ExternalCodexRuntimeError(
                "actor_git_mask_unavailable",
                "private Git metadata view parent is not a physical directory",
            )
        entries: list[dict[str, Any]] = []
        for source in directory_entries:
            if source.name in masked_names:
                continue
            try:
                source_stat = source.lstat()
            except OSError as exc:
                raise ExternalCodexRuntimeError(
                    "actor_git_mask_unavailable",
                    "private Git metadata view entry became unavailable",
                ) from exc
            if source.is_symlink() or not (
                stat.S_ISREG(source_stat.st_mode) or stat.S_ISDIR(source_stat.st_mode)
            ):
                raise ExternalCodexRuntimeError(
                    "actor_git_mask_unavailable",
                    "private Git metadata view contains an unsupported entry",
                )
            entries.append(
                {
                    "source": str(source),
                    "target": str(parent / source.name),
                    "kind": (
                        "directory" if stat.S_ISDIR(source_stat.st_mode) else "file"
                    ),
                    "identity": _private_view_identity(source_stat),
                }
            )
        views.append(
            {
                "target": str(parent),
                "identity": _private_view_identity(parent_stat),
                "entries": entries,
            }
        )
    return views


def _run_actor_masked_command(
    actor_git_mask: Mapping[str, Any],
    command_argv: Sequence[str],
    *,
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run one command through a namespace-private descriptor-bound mask view."""

    views = actor_git_mask.get("private_directory_views")
    masks = actor_git_mask.get("masks")
    if not isinstance(views, list) or not views or not isinstance(masks, list):
        raise ExternalCodexRuntimeError(
            "actor_git_mask_unavailable",
            "external actor Git mask lacks its private directory views",
        )
    executable = Path(str(command_argv[0])) if command_argv else Path()
    if (
        not executable.is_absolute()
        or not executable.is_file()
        or executable.resolve() != executable
        or not os.access(executable, os.X_OK)
    ):
        raise ExternalCodexRuntimeError(
            "actor_git_mask_unavailable",
            "masked controller command is not one exact executable",
        )
    contour_paths = {
        "supervisor": SUPERVISOR_PATH,
        "mount_launcher": MOUNT_LAUNCHER_PATH,
        "mount_wrapper": MOUNT_WRAPPER_PATH,
        "python": Path(sys.executable).resolve(),
    }
    if any(
        not path.is_absolute()
        or not path.is_file()
        or path.resolve() != path
        or (
            label not in {"supervisor", "mount_launcher"}
            and not os.access(path, os.X_OK)
        )
        for label, path in contour_paths.items()
    ):
        raise ExternalCodexRuntimeError(
            "actor_git_mask_unavailable",
            "masked controller command contour is unavailable",
        )
    command = [
        str(contour_paths["python"]),
        str(SUPERVISOR_PATH),
        "--parent-pid",
        str(os.getpid()),
        "--term-timeout-seconds",
        "3.0",
        "--kill-timeout-seconds",
        "3.0",
        "--executable-digest",
        sha256_file(executable),
        "--mount-wrapper",
        str(MOUNT_WRAPPER_PATH),
        "--mount-wrapper-digest",
        sha256_file(contour_paths["mount_wrapper"]),
        "--mount-launcher-digest",
        sha256_file(contour_paths["mount_launcher"]),
    ]
    view_targets: set[Path] = set()
    for view in views:
        target = Path(str(view.get("target", "")))
        identity = view.get("identity")
        entries = view.get("entries")
        if (
            not target.is_absolute()
            or not isinstance(identity, dict)
            or not isinstance(entries, list)
        ):
            raise ExternalCodexRuntimeError(
                "actor_git_mask_unavailable",
                "private Git metadata view has an invalid shape",
            )
        _assert_private_view_identity(target, identity, directory=True)
        view_targets.add(target)
        command.extend(
            (
                "--private-directory-view",
                json.dumps(view, sort_keys=True, separators=(",", ":")),
            )
        )
    for mask in masks:
        source = Path(str(mask.get("source", "")))
        target = Path(str(mask.get("target", "")))
        digest = str(mask.get("digest", ""))
        if (
            target.parent not in view_targets
            or not source.is_file()
            or source.is_symlink()
            or sha256_file(source) != digest
        ):
            raise ExternalCodexRuntimeError(
                "actor_git_mask_unavailable",
                "external actor Git mask changed before containment",
            )
        command.extend(("--read-only-mask", str(source), str(target), digest))
    command.extend(("--", *command_argv))
    try:
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
            env=dict(environment),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExternalCodexRuntimeError(
            "actor_git_mask_unavailable",
            "masked controller command containment failed",
        ) from exc


def _masked_git_command(
    workspace: Path,
    actor_git_mask: Mapping[str, Any],
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    """Run one controller-side Git probe under the same mount-mask shape."""

    return _run_actor_masked_command(
        actor_git_mask,
        (
            "/usr/bin/git",
            "-c",
            "core.quotePath=false",
            "-C",
            str(workspace),
            *arguments,
        ),
        environment=_controller_git_environment(workspace),
    )


def _prepare_actor_git_mask(workspace: Path, scratch_root: Path) -> dict[str, Any]:
    """Mask credential-bearing Git config without changing native discovery."""

    workspace = workspace.resolve(strict=True)
    config_coordinate = _repository_git_path(workspace, "config")
    actual_config = _physical_git_metadata_file(
        config_coordinate,
        purpose="config",
        required=True,
    )
    assert actual_config is not None
    worktree_config_coordinate = _repository_git_path(workspace, "config.worktree")
    worktree_config = _physical_git_metadata_file(
        worktree_config_coordinate,
        purpose="worktree config",
        required=False,
    )
    config_lock = _physical_git_metadata_file(
        actual_config.with_name(f"{actual_config.name}.lock"),
        purpose="config lock",
        required=False,
    )
    worktree_lock_coordinate = worktree_config_coordinate.with_name(
        f"{worktree_config_coordinate.name}.lock"
    )
    worktree_config_lock = _physical_git_metadata_file(
        worktree_lock_coordinate,
        purpose="worktree config lock",
        required=False,
    )
    mask_root = scratch_root / "git-config-mask"
    if mask_root.exists() or mask_root.is_symlink():
        raise ExternalCodexRuntimeError(
            "actor_git_mask_collision",
            "attempt-local actor Git mask path is not fresh",
        )
    try:
        mask_root.mkdir(parents=True, mode=0o700)
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "actor_git_mask_unavailable",
            "cannot establish the attempt-local credential-free Git mask",
        ) from exc
    sanitized_config = _sanitized_repository_config(workspace)
    sanitized_path = mask_root / "config"
    _atomic_write_bytes(sanitized_path, sanitized_config.encode("utf-8"), mode=0o400)
    targets = list(_current_mount_aliases(actual_config))
    targets.extend(
        _current_mount_aliases(
            config_lock or actual_config.with_name(f"{actual_config.name}.lock"),
            required=False,
        )
    )
    targets.extend(
        _current_mount_aliases(
            worktree_config or worktree_config_coordinate,
            required=False,
        )
    )
    targets.extend(
        _current_mount_aliases(
            worktree_config_lock or worktree_lock_coordinate,
            required=False,
        )
    )
    masks = [
        {
            "source": str(sanitized_path),
            "target": str(target),
            "digest": sha256_file(sanitized_path),
        }
        for target in sorted(set(targets))
    ]
    owner_status = _git_status(workspace)
    actor_git_mask = {
        "masks": masks,
        "sanitized_config_path": str(sanitized_path),
        "private_directory_views": _private_directory_views(masks),
    }
    observed = _masked_git_command(
        workspace,
        actor_git_mask,
        "status",
        "--no-renames",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if observed.returncode != 0:
        raise ExternalCodexRuntimeError(
            "actor_git_mask_unavailable",
            "credential-free mount mask rejected the native repository",
        )
    masked_status = _parse_git_status(observed.stdout)
    if masked_status != owner_status:
        raise ExternalCodexRuntimeError(
            "actor_git_mask_mismatch",
            "attempt-local Git mask does not preserve exact workspace status",
        )
    return actor_git_mask


def _actor_codex_permission_profile(
    actor_git_mask: Mapping[str, Any] | None = None,
    *,
    sanitized_config_path: Path | None = None,
    execution_root: Path | None = None,
    readable_paths: Sequence[Path] = (),
    writable_paths: Sequence[Path] = (),
    denied_paths: Sequence[Path] = (),
    workspace_access: Literal["read", "write"] = "write",
) -> str:
    """Build the one named Codex profile shared by preflight and execution."""

    if sanitized_config_path is None and actor_git_mask is not None:
        sanitized_config_path = Path(
            str(actor_git_mask.get("sanitized_config_path", ""))
        )
    if sanitized_config_path is None:
        raise ExternalCodexRuntimeError(
            "actor_codex_permission_profile_unavailable",
            "external actor permission profile has no sanitized Git config path",
        )
    if not sanitized_config_path.is_absolute():
        raise ExternalCodexRuntimeError(
            "actor_git_mask_unavailable",
            "external actor Git mask lacks an absolute sanitized config path",
        )
    if execution_root is None or not execution_root.is_absolute():
        raise ExternalCodexRuntimeError(
            "actor_codex_permission_profile_unavailable",
            "external actor permission profile has no absolute execution root",
        )
    entries: dict[str, str] = {
        ":minimal": "read",
        ":workspace_roots": workspace_access,
        str(sanitized_config_path): "read",
    }
    for path in readable_paths:
        if not path.is_absolute():
            raise ExternalCodexRuntimeError(
                "actor_codex_permission_profile_unavailable",
                "external actor readable coordinate is not absolute",
            )
        entries[str(path)] = "read"
    for path in writable_paths:
        if not path.is_absolute():
            raise ExternalCodexRuntimeError(
                "actor_codex_permission_profile_unavailable",
                "external actor writable coordinate is not absolute",
            )
        entries[str(path)] = "write"
    for path in denied_paths:
        if not path.is_absolute():
            raise ExternalCodexRuntimeError(
                "actor_codex_permission_profile_unavailable",
                "external actor denied coordinate is not absolute",
            )
        entries[str(path)] = "deny"
    filesystem = ",".join(
        f"{json.dumps(path, ensure_ascii=True)}={json.dumps(access)}"
        for path, access in sorted(entries.items())
    )
    return "{filesystem={" + filesystem + "},network={enabled=false}}"


def _toml_inline_string_map(values: Mapping[str, str]) -> str:
    """Encode a validated string map for one exact Codex CLI config value."""

    entries = ",".join(
        f"{json.dumps(key, ensure_ascii=True)}={json.dumps(value, ensure_ascii=True)}"
        for key, value in sorted(values.items())
    )
    return "{" + entries + "}"


def _specialized_environment(
    _profile: Mapping[str, Any],
    tool_entry: Mapping[str, Any],
) -> tuple[dict[str, str], tuple[Path, ...]]:
    """Resolve one profile-bound environment inside the verified runtime release."""

    candidate = tool_entry.get("specialized_environment")
    if candidate is None:
        return {}, ()
    if not isinstance(candidate, dict):
        raise ExternalCodexRuntimeError(
            "specialized_environment_unavailable",
            "tool profile specialized environment is invalid",
        )
    release_value = os.environ.get("AOA_EXTERNAL_CODEX_VERIFIED_RELEASE_ROOT")
    if not release_value:
        raise ExternalCodexRuntimeError(
            "specialized_environment_unavailable",
            "specialized environment requires a verified runtime release",
        )
    release_root = Path(release_value)
    try:
        release_root = release_root.resolve(strict=True)
    except OSError as exc:
        raise ExternalCodexRuntimeError(
            "specialized_environment_unavailable",
            "verified runtime release root is unavailable",
        ) from exc
    if release_root.is_symlink() or not release_root.is_dir():
        raise ExternalCodexRuntimeError(
            "specialized_environment_unavailable",
            "verified runtime release root is not a physical directory",
        )

    resolved_environment: dict[str, str] = {}
    readable_paths: list[Path] = []

    def resolve_directory(raw_relative: object, label: str) -> Path:
        relative = Path(str(raw_relative or ""))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ExternalCodexRuntimeError(
                "specialized_environment_invalid",
                f"{label} has an unsafe release-relative coordinate",
            )
        path = release_root / relative
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(release_root)
        except (OSError, ValueError) as exc:
            raise ExternalCodexRuntimeError(
                "specialized_environment_unavailable",
                f"{label} is unavailable inside the verified release",
            ) from exc
        if path.is_symlink() or resolved.is_symlink() or not resolved.is_dir():
            raise ExternalCodexRuntimeError(
                "specialized_environment_unavailable",
                f"{label} is not one physical release directory",
            )
        return resolved

    validation_pythonpath = resolve_directory(
        candidate.get("pythonpath_ref"),
        "validation Python path",
    )
    sdk_pythonpath = resolve_directory(
        candidate.get("sdk_pythonpath_ref"),
        "SDK Python path",
    )
    resolved_environment["PYTHONPATH"] = os.pathsep.join(
        (str(validation_pythonpath), str(sdk_pythonpath))
    )
    readable_paths.extend((validation_pythonpath, sdk_pythonpath))
    for owner_root in candidate.get("owner_roots", []):
        if not isinstance(owner_root, dict):
            raise ExternalCodexRuntimeError(
                "specialized_environment_invalid",
                "specialized environment owner root is invalid",
            )
        variable = str(owner_root.get("environment_variable") or "")
        if re.fullmatch(r"AOA_[A-Z0-9_]+_ROOT", variable) is None:
            raise ExternalCodexRuntimeError(
                "specialized_environment_invalid",
                "specialized environment owner variable is invalid",
            )
        root = resolve_directory(owner_root.get("root_ref"), f"owner root {variable}")
        resolved_environment[variable] = str(root)
        readable_paths.append(root)
    fixed_variables = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
    }
    for key, value in candidate.get("environment_variables", {}).items():
        if fixed_variables.get(str(key)) != value:
            raise ExternalCodexRuntimeError(
                "specialized_environment_invalid",
                "specialized environment contains an unsupported fixed variable",
            )
        resolved_environment[str(key)] = str(value)
    return resolved_environment, tuple(readable_paths)


def _git_head(
    workspace: Path,
    *,
    git_env: Mapping[str, str] | None = None,
) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(workspace), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
        env=dict(git_env or _controller_git_environment(workspace)),
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ExternalCodexRuntimeError(
            "workspace_not_git", "workspace is not an exact Git worktree"
        )
    return value


def _parse_git_status(payload: str) -> dict[str, str]:
    status: dict[str, str] = {}
    for line in payload.splitlines():
        if len(line) < 4:
            continue
        code = line[:2]
        path = line[3:].split(" -> ")[-1]
        status[path] = code
    return status


def _git_status(
    workspace: Path,
    *,
    git_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    completed = subprocess.run(
        [
            "/usr/bin/git",
            "-c",
            "core.quotePath=false",
            "-C",
            str(workspace),
            "status",
            "--no-renames",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        env=dict(git_env or _controller_git_environment(workspace)),
    )
    if completed.returncode != 0:
        raise ExternalCodexRuntimeError(
            "workspace_status_failed", "cannot inspect exact workspace status"
        )
    return _parse_git_status(completed.stdout)


def _git_bytes(
    workspace: Path,
    *args: str,
    timeout: int = 30,
    git_env: Mapping[str, str] | None = None,
) -> bytes:
    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(workspace), *args],
        capture_output=True,
        check=False,
        timeout=timeout,
        env=dict(git_env or _controller_git_environment(workspace)),
    )
    if completed.returncode != 0:
        raise ExternalCodexRuntimeError(
            "workspace_manifest_failed",
            f"cannot inspect workspace manifest input: git {' '.join(args)}",
        )
    return completed.stdout


def _nul_paths(payload: bytes, *, label: str) -> tuple[str, ...]:
    values: list[str] = []
    for raw in payload.split(b"\0"):
        if not raw:
            continue
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_path_invalid",
                f"{label} contains a non-UTF-8 path",
            ) from exc
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_path_invalid",
                f"{label} contains an unsafe path",
            )
        values.append(path.as_posix())
    return tuple(values)


def _tracked_index_flags(
    workspace: Path,
    *,
    git_env: Mapping[str, str],
) -> dict[str, tuple[str, ...]]:
    flags: dict[str, tuple[str, ...]] = {}
    for raw in _git_bytes(
        workspace,
        "ls-files",
        "--stage",
        "-z",
        git_env=git_env,
    ).split(b"\0"):
        if not raw:
            continue
        try:
            metadata, raw_path = raw.split(b"\t", 1)
            mode = metadata.split(b" ", 1)[0]
            paths = _nul_paths(raw_path + b"\0", label="tracked index entries")
        except (ValueError, ExternalCodexRuntimeError) as exc:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_failed",
                "git ls-files returned an invalid staged index record",
            ) from exc
        if len(paths) != 1:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_failed",
                "git ls-files returned an invalid staged path",
            )
        if mode == b"160000":
            raise ExternalCodexRuntimeError(
                "workspace_submodule_unsupported",
                f"workspace manifest does not yet admit tracked submodule {paths[0]}",
            )
    for raw in _git_bytes(
        workspace,
        "ls-files",
        "-v",
        "-z",
        git_env=git_env,
    ).split(b"\0"):
        if not raw:
            continue
        if len(raw) < 3 or raw[1:2] != b" ":
            raise ExternalCodexRuntimeError(
                "workspace_manifest_failed",
                "git ls-files returned an invalid tracked-path record",
            )
        tag = chr(raw[0])
        paths = _nul_paths(raw[2:] + b"\0", label="tracked files")
        if len(paths) != 1:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_failed",
                "git ls-files returned an invalid tracked path",
            )
        values: list[str] = []
        if tag.islower():
            values.append("assume_unchanged")
        if tag.upper() == "S":
            values.append("skip_worktree")
        flags[paths[0]] = tuple(values)
    return flags


def _workspace_filesystem_paths(workspace: Path) -> set[str]:
    """Inventory every supported entry without following links or reading bytes."""

    paths: set[str] = set()
    pending = [workspace]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as scan:
                children = sorted(scan, key=lambda item: item.name)
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_failed",
                "cannot enumerate the exact workspace filesystem tree",
            ) from exc
        for child in children:
            path = Path(child.path)
            relative = path.relative_to(workspace).as_posix()
            if relative == ".git":
                continue
            if child.name == ".git":
                embedded = path.parent.relative_to(workspace).as_posix()
                raise ExternalCodexRuntimeError(
                    "workspace_embedded_repository_unsupported",
                    "workspace manifest does not yet admit embedded repository "
                    f"{embedded}",
                )
            try:
                mode = child.stat(follow_symlinks=False).st_mode
            except OSError as exc:
                raise ExternalCodexRuntimeError(
                    "workspace_manifest_failed",
                    f"cannot inspect workspace entry {relative}",
                ) from exc
            if stat.S_ISLNK(mode) or stat.S_ISREG(mode):
                paths.add(relative)
            elif stat.S_ISDIR(mode):
                paths.add(relative)
                pending.append(path)
            else:
                raise ExternalCodexRuntimeError(
                    "workspace_entry_type_unsupported",
                    "workspace manifest does not admit FIFO, socket, device, or "
                    f"other special entry {relative}",
                )
    return paths


def _workspace_identity(workspace: Path) -> dict[str, Any]:
    """Capture the source path anchors that a replacement directory cannot forge."""

    anchors: list[dict[str, Any]] = []
    current = workspace
    while True:
        try:
            observed = current.lstat()
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_failed",
                "cannot capture the source workspace identity chain",
            ) from exc
        if not stat.S_ISDIR(observed.st_mode):
            raise ExternalCodexRuntimeError(
                "workspace_manifest_failed",
                "source workspace identity chain contains a non-directory",
            )
        anchors.append(
            {
                "path": str(current),
                "st_dev": int(observed.st_dev),
                "st_ino": int(observed.st_ino),
                "mode": stat.S_IMODE(observed.st_mode),
            }
        )
        if current == current.parent:
            break
        current = current.parent
    return {"root": anchors[0], "ancestors": anchors[1:]}


def build_workspace_manifest(workspace: str | Path) -> dict[str, Any]:
    """Describe exact HEAD plus every tracked, untracked, or ignored byte."""

    location = Path(workspace).resolve()
    if not location.is_dir() or Path(workspace).is_symlink():
        raise ExternalCodexRuntimeError(
            "workspace_unavailable", "workspace manifest target is unavailable"
        )
    git_env = _controller_git_environment(location)
    status_raw = _git_bytes(
        location,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        git_env=git_env,
    )
    diff_raw = _git_bytes(
        location,
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--binary",
        "HEAD",
        "--",
        timeout=60,
        git_env=git_env,
    )
    changed = _nul_paths(
        _git_bytes(
            location,
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--name-only",
            "-z",
            "HEAD",
            "--",
            git_env=git_env,
        ),
        label="tracked diff",
    )
    untracked = _nul_paths(
        _git_bytes(
            location,
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            git_env=git_env,
        ),
        label="untracked files",
    )
    ignored = _nul_paths(
        _git_bytes(
            location,
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
            git_env=git_env,
        ),
        label="ignored files",
    )
    tracked_flags = _tracked_index_flags(location, git_env=git_env)
    for relative in sorted(set(untracked) | set(ignored)):
        if _secret_shaped_path(relative):
            raise ExternalCodexRuntimeError(
                "workspace_secret_path_present",
                "workspace contains an untracked or ignored secret-shaped path",
            )
        candidate = location / relative
        current = candidate if candidate.is_dir() else candidate.parent
        while current != location:
            git_marker = current / ".git"
            if git_marker.exists() or git_marker.is_symlink():
                embedded = current.relative_to(location).as_posix()
                raise ExternalCodexRuntimeError(
                    "workspace_embedded_repository_unsupported",
                    "workspace manifest does not yet admit untracked or ignored "
                    f"embedded repository {embedded}",
                )
            current = current.parent
    entries: list[dict[str, Any]] = []
    filesystem_paths = _workspace_filesystem_paths(location)
    all_paths = (
        set(tracked_flags)
        | set(changed)
        | set(untracked)
        | set(ignored)
        | filesystem_paths
    )
    for relative in sorted(all_paths):
        path = location / relative
        index_flags = list(tracked_flags.get(relative, ()))
        if path.is_symlink():
            try:
                resolved_target = path.resolve(strict=True)
                resolved_target.relative_to(location)
            except (OSError, ValueError) as exc:
                raise ExternalCodexRuntimeError(
                    "workspace_symlink_target_unsupported",
                    "workspace manifest does not admit a symbolic link whose "
                    "target is absent or outside the exact workspace",
                ) from exc
            target = os.readlink(path).encode("utf-8")
            entries.append(
                {
                    "path": relative,
                    "kind": "symlink",
                    "size_bytes": len(target),
                    "sha256": sha256_bytes(target),
                    "mode": stat.S_IMODE(path.lstat().st_mode),
                    "index_flags": index_flags,
                }
            )
        elif path.is_file():
            resolved = path.resolve()
            try:
                resolved.relative_to(location)
            except ValueError as exc:
                raise ExternalCodexRuntimeError(
                    "workspace_manifest_path_invalid",
                    "workspace manifest would traverse a linked parent",
                ) from exc
            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(resolved),
                    "mode": stat.S_IMODE(path.stat().st_mode),
                    "index_flags": index_flags,
                }
            )
        elif path.is_dir():
            entries.append(
                {
                    "path": relative,
                    "kind": "directory",
                    "size_bytes": 0,
                    "sha256": None,
                    "mode": stat.S_IMODE(path.stat().st_mode),
                    "index_flags": index_flags,
                }
            )
        else:
            entries.append(
                {
                    "path": relative,
                    "kind": "missing",
                    "size_bytes": 0,
                    "sha256": None,
                    "mode": None,
                    "index_flags": index_flags,
                }
            )
    status = _git_status(location, git_env=git_env)
    return {
        "$schema": "schemas/external-codex-workspace-manifest.schema.json",
        "schema_version": "abyss_stack_external_codex_workspace_manifest_v1",
        "workspace_path": str(location),
        "workspace_identity": _workspace_identity(location),
        "git_head": _git_head(location, git_env=git_env),
        "git_status_porcelain_sha256": sha256_bytes(status_raw),
        "git_diff_binary_sha256": sha256_bytes(diff_raw),
        "status_entries": [
            {"path": path, "status": status[path]} for path in sorted(status)
        ],
        "content_entries": entries,
    }


def assert_workspace_manifest(
    manifest: Mapping[str, Any], workspace: str | Path
) -> None:
    validate_json(
        manifest,
        WORKSPACE_MANIFEST_SCHEMA_PATH,
        label="external Codex workspace manifest",
    )
    expected = build_workspace_manifest(workspace)
    if manifest != expected:
        raise ExternalCodexRuntimeError(
            "workspace_manifest_drift",
            "workspace bytes differ from the exact immutable baseline manifest",
        )


def compare_workspace_manifest(
    baseline: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, str]]:
    """Return byte-aware workspace changes relative to one exact manifest."""

    baseline_status = {
        str(item["path"]): str(item["status"])
        for item in baseline.get("status_entries", [])
    }
    current_status = {
        str(item["path"]): str(item["status"])
        for item in current.get("status_entries", [])
    }
    baseline_content = {
        str(item["path"]): dict(item) for item in baseline.get("content_entries", [])
    }
    current_content = {
        str(item["path"]): dict(item) for item in current.get("content_entries", [])
    }
    changed: list[dict[str, str]] = []
    if baseline.get("git_head") != current.get("git_head"):
        changed.append({"path": "<git-head>", "status": "head_changed"})
    for path in sorted(
        set(baseline_status)
        | set(current_status)
        | set(baseline_content)
        | set(current_content)
    ):
        if baseline_status.get(path) != current_status.get(path):
            changed.append(
                {"path": path, "status": current_status.get(path, "cleaned")}
            )
        elif baseline_content.get(path) != current_content.get(path):
            status = (
                "created"
                if path not in baseline_content
                else "removed"
                if path not in current_content
                else "content_changed"
            )
            changed.append({"path": path, "status": status})
    if baseline != current and not changed:
        changed.append({"path": "<workspace-manifest>", "status": "manifest_changed"})
    return changed


def _changed_since(
    baseline: Mapping[str, str], current: Mapping[str, str]
) -> list[dict[str, str]]:
    paths = sorted(set(baseline) | set(current))
    return [
        {"path": path, "status": current.get(path, "cleaned")}
        for path in paths
        if baseline.get(path) != current.get(path)
    ]


def _model_catalog_entry(value: Any, model_slug: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("slug") == model_slug:
            return value
        for nested in value.values():
            found = _model_catalog_entry(nested, model_slug)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _model_catalog_entry(nested, model_slug)
            if found is not None:
                return found
    return None


def _command_text(item: Mapping[str, Any]) -> str | None:
    for key in ("command", "cmd"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _replace_prompt_source_path(
    value: Any,
    *,
    source_path: str,
    projection_path: str,
) -> Any:
    """Project source coordinates out of the model-facing task view."""

    if isinstance(value, str):
        return _replace_source_aliases_in_text(
            value,
            ((source_path, projection_path),),
        )
    if isinstance(value, list):
        return [
            _replace_prompt_source_path(
                item,
                source_path=source_path,
                projection_path=projection_path,
            )
            for item in value
        ]
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for key, item in value.items():
            projected_key = _replace_prompt_source_path(
                str(key),
                source_path=source_path,
                projection_path=projection_path,
            )
            if projected_key in projected:
                raise ExternalCodexRuntimeError(
                    "actor_input_key_collision",
                    "source-coordinate removal collapsed distinct mapping keys",
                )
            projected[projected_key] = _replace_prompt_source_path(
                item,
                source_path=source_path,
                projection_path=projection_path,
            )
        return projected
    if isinstance(value, tuple):
        return tuple(
            _replace_prompt_source_path(
                item,
                source_path=source_path,
                projection_path=projection_path,
            )
            for item in value
        )
    return value


def _contains_source_path(value: Any, source_path: str) -> bool:
    if isinstance(value, str):
        return any(
            source_path in candidate
            for candidate in _json_escape_decoding_layers(value)
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_source_path(item, source_path) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_source_path(key, source_path)
            or _contains_source_path(item, source_path)
            for key, item in value.items()
        )
    return False


def _decode_one_json_escape_layer(value: str) -> str:
    """Decode one JSON string-escape layer without requiring a JSON document."""

    decoded: list[str] = []
    index = 0
    simple = {
        '"': '"',
        "/": "/",
        "\\": "\\",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }
    while index < len(value):
        if value[index] != "\\" or index + 1 >= len(value):
            decoded.append(value[index])
            index += 1
            continue
        escape = value[index + 1]
        if escape in simple:
            decoded.append(simple[escape])
            index += 2
            continue
        if escape == "u" and index + 6 <= len(value):
            digits = value[index + 2 : index + 6]
            if re.fullmatch(r"[0-9A-Fa-f]{4}", digits):
                code_unit = int(digits, 16)
                next_index = index + 6
                if 0xD800 <= code_unit <= 0xDBFF and next_index + 6 <= len(value):
                    low_prefix = value[next_index : next_index + 2]
                    low_digits = value[next_index + 2 : next_index + 6]
                    if low_prefix == "\\u" and re.fullmatch(
                        r"[0-9A-Fa-f]{4}", low_digits
                    ):
                        low_unit = int(low_digits, 16)
                        if 0xDC00 <= low_unit <= 0xDFFF:
                            decoded.append(
                                chr(
                                    0x10000
                                    + ((code_unit - 0xD800) << 10)
                                    + low_unit
                                    - 0xDC00
                                )
                            )
                            index = next_index + 6
                            continue
                if not 0xD800 <= code_unit <= 0xDFFF:
                    decoded.append(chr(code_unit))
                    index = next_index
                    continue
        decoded.append(value[index])
        index += 1
    return "".join(decoded)


def _json_escape_decoding_layers(value: str) -> tuple[str, ...]:
    """Expose bounded nested JSON escape spellings for source-alias checks."""

    layers = [value]
    current = value
    for _ in range(MAX_JSON_ESCAPE_LAYERS):
        decoded = _decode_one_json_escape_layer(current)
        if decoded == current:
            break
        layers.append(decoded)
        current = decoded
    else:
        if _decode_one_json_escape_layer(current) != current:
            raise ExternalCodexRuntimeError(
                "actor_input_escape_depth_exceeded",
                "actor-facing text exceeded the bounded JSON escape depth",
            )
    return tuple(layers)


def _replace_source_aliases_in_text(
    value: str,
    replacements: Sequence[tuple[str, str]],
) -> str:
    """Remove aliases revealed through literal or nested JSON string escapes."""

    layers = _json_escape_decoding_layers(value)
    if not any(alias in layer for alias, _ in replacements for layer in layers):
        return value
    matching_layers = [
        layer for layer in layers if any(alias in layer for alias, _ in replacements)
    ]
    result = matching_layers[-1]
    for alias, replacement in replacements:
        result = result.replace(alias, replacement)
    if any(
        alias in layer
        for alias, _ in replacements
        for layer in _json_escape_decoding_layers(result)
    ):
        raise ExternalCodexRuntimeError(
            "actor_source_path_exposed",
            "source-coordinate removal did not eliminate every source alias",
        )
    return result


def _actor_source_aliases(validated: Mapping[str, Any]) -> tuple[str, ...]:
    """Return every admitted lexical/canonical source coordinate, longest first."""

    aliases = {
        str(validated["launch"]["workspace_path"]),
        str(validated["workspace"]),
        str(validated["workspace_manifest_baseline"].get("workspace_path", "")),
    }
    identity = validated["workspace_manifest_baseline"].get("workspace_identity", {})
    if isinstance(identity, Mapping):
        root = identity.get("root")
        ancestors = identity.get("ancestors")
        if isinstance(root, Mapping):
            aliases.add(str(root.get("path", "")))
        if isinstance(ancestors, list):
            aliases.update(
                str(item.get("path", ""))
                for item in ancestors
                if isinstance(item, Mapping)
            )
    return tuple(
        sorted(
            (value for value in aliases if value and value != "/"),
            key=lambda value: (-len(value), value),
        )
    )


def _sanitize_actor_value(
    value: Any,
    aliases: Sequence[str],
    source_roots: frozenset[str],
) -> Any:
    if isinstance(value, str):
        replacements = tuple(
            (
                alias,
                str(ACTOR_EXECUTION_ROOT)
                if alias in source_roots
                else "<controller-path-redacted>",
            )
            for alias in aliases
        )
        return _replace_source_aliases_in_text(value, replacements)
    if isinstance(value, list):
        return [_sanitize_actor_value(item, aliases, source_roots) for item in value]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            original_key = str(key)
            if original_key == "workspace_identity":
                continue
            sanitized_key = _sanitize_actor_value(
                original_key,
                aliases,
                source_roots,
            )
            if sanitized_key in sanitized:
                raise ExternalCodexRuntimeError(
                    "actor_input_key_collision",
                    "source-coordinate removal collapsed distinct mapping keys",
                )
            sanitized[sanitized_key] = _sanitize_actor_value(
                item,
                aliases,
                source_roots,
            )
        return sanitized
    return value


def _actor_safe_input_envelope(
    *,
    input_id: str,
    raw: bytes,
    original_provenance: Mapping[str, Any],
    aliases: Sequence[str],
    source_roots: frozenset[str],
) -> tuple[dict[str, Any], bytes]:
    """Build one schema-checked derivative without controller coordinates."""

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        binary_text_shadow = raw.decode("utf-8", errors="surrogateescape")
        if any(
            alias.encode("utf-8") in raw
            or _contains_source_path(binary_text_shadow, alias)
            for alias in aliases
        ):
            raise ExternalCodexRuntimeError(
                "actor_source_path_exposed",
                "binary immutable input retained a source coordinate",
            )
        payload_kind = "base64"
        payload: Any = base64.b64encode(raw).decode("ascii")
    else:
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            payload_kind = "utf8_text"
            payload = _sanitize_actor_value(text, aliases, source_roots)
        else:
            payload_kind = "json"
            payload = _sanitize_actor_value(decoded, aliases, source_roots)
    envelope = {
        "$schema": "schemas/external-codex-actor-input-envelope.schema.json",
        "schema_version": "abyss_stack_external_codex_actor_input_envelope_v1",
        "input_id": input_id,
        "payload_kind": payload_kind,
        "source_artifact_digest": str(original_provenance["artifact_digest"]),
        "source_schema_ref": str(original_provenance["schema_ref"]),
        "source_schema_version": str(original_provenance["schema_version"]),
        "payload": payload,
    }
    validate_json(
        envelope,
        ACTOR_INPUT_ENVELOPE_SCHEMA_PATH,
        label=f"actor-safe immutable input {input_id}",
    )
    if any(_contains_source_path(envelope, alias) for alias in aliases):
        raise ExternalCodexRuntimeError(
            "actor_source_path_exposed",
            "actor-safe immutable envelope retained a source coordinate",
        )
    encoded = (
        json.dumps(envelope, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    encoded_text = encoded.decode("utf-8")
    if any(_contains_source_path(encoded_text, alias) for alias in aliases):
        raise ExternalCodexRuntimeError(
            "actor_source_path_exposed",
            "serialized actor-safe immutable envelope retained a source coordinate",
        )
    return envelope, encoded


class ExternalCodexRuntime:
    """Persistent launch, event, resume, and A2A-export controller."""

    def __init__(
        self,
        state_root: str | Path,
        *,
        profile_path: str | Path = PROFILE_PATH,
    ) -> None:
        self.state_root = Path(state_root)
        if not self.state_root.is_absolute():
            raise ExternalCodexRuntimeError(
                "invalid_state_root", "external Codex state root must be absolute"
            )
        if self.state_root.is_symlink():
            raise ExternalCodexRuntimeError(
                "invalid_state_root", "external Codex state root cannot be a symlink"
            )
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.state_root.is_dir():
            raise ExternalCodexRuntimeError(
                "invalid_state_root", "external Codex state root is not a directory"
            )
        self.profile_path = Path(profile_path)
        self.profile_raw = read_bounded(self.profile_path)
        self.profile = load_json_bytes(self.profile_raw, label="runtime profile")
        validate_json(self.profile, PROFILE_SCHEMA_PATH, label="runtime profile")
        for label, values, key in (
            ("tool profile", self.profile["tool_profiles"], "profile_id"),
        ):
            identities = [item[key] for item in values]
            if len(identities) != len(set(identities)):
                raise ExternalCodexRuntimeError(
                    "runtime_profile_ambiguous", f"{label} identities must be unique"
                )
        if self.profile["result_schema_ref"] != (
            "schemas/external-codex-report.schema.json"
        ):
            raise ExternalCodexRuntimeError(
                "runtime_profile_invalid", "runtime profile result schema ref drifted"
            )
        validate_structured_output_schema(load_schema(REPORT_SCHEMA_PATH))

    def _session_dir(self, session_id: str) -> Path:
        return self.state_root / "sessions" / _session_token(session_id)

    @staticmethod
    def _projection_path_from_state(state: Mapping[str, Any]) -> Path:
        value = state.get("actor_projection_path")
        if not isinstance(value, str) or not value.startswith("/"):
            raise ExternalCodexRuntimeError(
                "legacy_projection_unavailable",
                "runtime state has no safe runtime-owned actor projection",
            )
        path = Path(value)
        if path.is_symlink() or not path.is_dir():
            raise ExternalCodexRuntimeError(
                "actor_projection_unavailable",
                "runtime-owned actor projection is unavailable or symbolic",
            )
        return path

    def _prepare_actor_projection(
        self,
        *,
        validated: Mapping[str, Any],
        session_dir: Path,
    ) -> dict[str, Any]:
        """Materialize one source-checked actor tree before any worker fork."""

        review_seed = validated.get("review_seed")
        source = Path(str(validated["workspace"]))
        if review_seed is None:
            source = source.resolve(strict=True)
            try:
                session_dir.resolve().relative_to(source)
            except ValueError:
                pass
            else:
                raise ExternalCodexRuntimeError(
                    "workspace_projection_unsupported",
                    "runtime session artifacts may not be materialized inside the source workspace",
                )
        source_before = dict(validated["workspace_manifest_baseline"])
        source_before_path = session_dir / "source-manifest-before.json"
        _atomic_write_json(source_before_path, source_before, mode=0o400)
        source_before_ref = _artifact_ref(source_before_path)
        projection_path = session_dir / "actor-workspace"
        projection_identity: Mapping[str, Any] | None = None

        def cleanup_projection() -> None:
            try:
                remove_actor_projection(
                    projection_path,
                    expected_identity=projection_identity,
                )
            except (OSError, ProjectionError) as exc:
                raise ExternalCodexRuntimeError(
                    "workspace_projection_cleanup_incomplete",
                    "failed projection admission could not remove its unpublished actor tree",
                ) from exc

        def assert_projection_coordinate() -> None:
            identity = projection_identity
            try:
                observed = projection_path.stat(follow_symlinks=False)
            except OSError as exc:
                raise ExternalCodexRuntimeError(
                    "actor_projection_publication_drift",
                    "published actor projection coordinate became unavailable",
                ) from exc
            if (
                not isinstance(identity, Mapping)
                or identity.get("st_dev") != observed.st_dev
                or identity.get("st_ino") != observed.st_ino
            ):
                raise ExternalCodexRuntimeError(
                    "actor_projection_publication_drift",
                    "published actor projection coordinate no longer names its admitted inode",
                )

        try:
            if review_seed is None:
                projection, actor_baseline = materialize_actor_projection(
                    source,
                    projection_path,
                    source_manifest=source_before,
                    source_manifest_digest=str(source_before_ref["artifact_digest"]),
                )
            else:
                seed_path = Path(str(review_seed["writer_projection_path"]))
                seed_manifest_ref = review_seed["writer_final_manifest_ref"]
                seed_manifest = _load_verified_json_ref(
                    seed_manifest_ref,
                    label="actor projection seed manifest",
                    schema_path=ACTOR_MANIFEST_SCHEMA_PATH,
                )
                with self._lock(str(review_seed["writer_session_id"])):
                    writer_state = self._load_state(
                        str(review_seed["writer_session_id"])
                    )
                    if self._review_seed_envelope_locked(writer_state) != review_seed:
                        raise ExternalCodexRuntimeError(
                            "review_seed_envelope_drift",
                            "writer changed before reviewer projection cloning",
                        )
                    projection, actor_baseline = materialize_actor_projection_from_seed(
                        seed_path,
                        projection_path,
                        expected_manifest=seed_manifest,
                    )
                projection_identity = actor_baseline["workspace_identity"]
                if (
                    actor_baseline["content_entries"]
                    != seed_manifest["content_entries"]
                    or actor_baseline["private_git_digest"]
                    != seed_manifest["private_git_digest"]
                    or actor_baseline["source_git_head"]
                    != seed_manifest["source_git_head"]
                ):
                    cleanup_projection()
                    raise ExternalCodexRuntimeError(
                        "actor_projection_seed_drift",
                        "review projection differs from the exact writer projection seed",
                    )
                # The reviewer owns a new source-admission envelope, while its
                # content is the exact writer projection.  Rebind only that
                # controller-owned source digest; content entries remain byte
                # identical to the writer seed.
                actor_baseline["workspace_path"] = str(projection)
                actor_baseline["source_manifest_digest"] = str(
                    source_before_ref["artifact_digest"]
                )
            if projection_identity is None:
                projection_identity = actor_baseline["workspace_identity"]
        except (OSError, ProjectionError) as exc:
            raise ExternalCodexRuntimeError(
                "workspace_projection_unsupported",
                str(exc),
            ) from exc
        if review_seed is None:
            try:
                source_after = build_workspace_manifest(source)
            except ExternalCodexRuntimeError as exc:
                cleanup_projection()
                raise ExternalCodexRuntimeError(
                    "workspace_source_race",
                    "source workspace could not be revalidated after projection materialization",
                ) from exc
        else:
            # A reviewer is admitted from the terminal writer envelope alone.
            # The historical owner source is provenance, never a live input.
            source_after = source_before
        try:
            assert_projection_coordinate()
        except ExternalCodexRuntimeError:
            cleanup_projection()
            raise
        source_after_path = session_dir / "source-manifest-after.json"
        _atomic_write_json(source_after_path, source_after, mode=0o400)
        source_after_ref = _artifact_ref(source_after_path)
        if source_after != source_before:
            cleanup_projection()
            raise ExternalCodexRuntimeError(
                "workspace_source_race",
                "source workspace changed during actor projection materialization",
            )
        actor_baseline_path = session_dir / "actor-baseline-manifest.json"
        validate_json(
            actor_baseline,
            ACTOR_MANIFEST_SCHEMA_PATH,
            label="actor baseline manifest",
        )
        _atomic_write_json(actor_baseline_path, actor_baseline, mode=0o400)
        actor_baseline_ref = _artifact_ref(actor_baseline_path)
        return {
            "source_manifest_before_ref": source_before_ref,
            "source_manifest_after_ref": source_after_ref,
            "actor_projection_path": str(projection),
            "actor_baseline_manifest_ref": actor_baseline_ref,
            "actor_baseline_manifest": actor_baseline,
        }

    @contextmanager
    def _lock(self, session_id: str) -> Iterator[None]:
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        lock_path = session_dir / "session.lock"
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _acquire_workspace_attempt_lock(self, workspace: str | Path) -> int:
        """Hold one workspace across the full lifetime of an active worker."""

        resolved = Path(workspace).resolve(strict=True)
        lock_fd = os.open(
            resolved,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
        )
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(lock_fd)
            raise ExternalCodexRuntimeError(
                "workspace_active_attempt_conflict",
                "another external-agent attempt already owns this exact workspace",
            ) from exc
        return lock_fd

    def _state_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "state.json"

    def _load_state(self, session_id: str) -> dict[str, Any]:
        path = self._state_path(session_id)
        if not path.is_file():
            raise ExternalCodexRuntimeError(
                "session_not_found", f"external Codex session is unknown: {session_id}"
            )
        state = load_json(path, label="runtime state")
        validate_json(state, STATE_SCHEMA_PATH, label="runtime state")
        if (
            state.get("schema_version")
            not in {
                LEGACY_STATE_SCHEMA_VERSION,
                LEGACY_STATE_V2_SCHEMA_VERSION,
                STATE_SCHEMA_VERSION,
            }
            or state.get("session_id") != session_id
        ):
            raise ExternalCodexRuntimeError(
                "runtime_state_invalid", "external Codex state identity is invalid"
            )
        return self._recover_or_verify_event_state(state)

    def _recover_or_verify_event_state(
        self, state: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Verify the normalized stream or recover one strict append extension."""

        session_id = str(state["session_id"])
        path = self._events_path(session_id)
        last_sequence = int(state["last_event_sequence"])
        if not path.exists():
            if last_sequence != -1:
                raise ExternalCodexRuntimeError(
                    "runtime_event_state_drift",
                    "runtime event stream is missing behind durable state",
                )
        durable_count = last_sequence + 1
        digest = hashlib.sha256()
        prefix_digest = sha256_bytes(b"") if durable_count == 0 else None
        line_count = 0
        extension_events: list[dict[str, Any]] = []
        if path.exists():
            for line_number, line in _iter_jsonl_bytes(
                path,
                failure_code="runtime_event_state_drift",
                label="runtime event stream",
            ):
                try:
                    event = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ExternalCodexRuntimeError(
                        "runtime_event_state_drift",
                        f"runtime event line {line_number} is invalid",
                    ) from exc
                validate_json(
                    event, EVENT_SCHEMA_PATH, label="normalized runtime event"
                )
                if (
                    event.get("sequence") != line_count
                    or event.get("session_id") != session_id
                ):
                    raise ExternalCodexRuntimeError(
                        "runtime_event_state_drift",
                        f"runtime event line {line_number} is not contiguous or owned",
                    )
                if line_count >= durable_count:
                    extension_events.append(event)
                digest.update(line)
                line_count += 1
                if line_count == durable_count:
                    prefix_digest = "sha256:" + digest.hexdigest()
        if line_count < durable_count:
            raise ExternalCodexRuntimeError(
                "runtime_event_state_drift",
                "runtime event stream was truncated behind durable state",
            )
        current_digest = "sha256:" + digest.hexdigest()
        recorded_digest = state.get("events_digest")
        if line_count == durable_count:
            if isinstance(recorded_digest, str) and recorded_digest != current_digest:
                raise ExternalCodexRuntimeError(
                    "runtime_event_state_drift",
                    "runtime event bytes differ from their durable state digest",
                )
            if recorded_digest == current_digest:
                return dict(state)
        else:
            if not isinstance(recorded_digest, str):
                raise ExternalCodexRuntimeError(
                    "runtime_event_state_drift",
                    "runtime event extension has no trusted durable prefix digest",
                )
            if prefix_digest != recorded_digest:
                raise ExternalCodexRuntimeError(
                    "runtime_event_state_drift",
                    "runtime event extension rewrites its durable prefix",
                )
        recovered = dict(state)
        for event in extension_events:
            self._apply_recovered_codex_event_state(recovered, event)
        recovered["last_event_sequence"] = line_count - 1
        recovered["events_digest"] = current_digest
        validate_json(recovered, STATE_SCHEMA_PATH, label="recovered runtime state")
        _atomic_write_json(self._state_path(session_id), recovered)
        return recovered

    def _apply_recovered_codex_event_state(
        self,
        state: dict[str, Any],
        event: Mapping[str, Any],
    ) -> None:
        """Replay the semantic delta carried by one durable Codex event."""

        source_type = event.get("source_event_type")
        if not isinstance(source_type, str) or not event.get(
            "event_type", ""
        ).startswith("codex."):
            return
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != source_type:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "recovered Codex event differs from its normalized source type",
            )
        delta = payload.get("_runtime_state_delta_v1")
        if not isinstance(delta, dict):
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_incomplete",
                "durable Codex event has no replayable semantic state delta",
            )
        self._apply_codex_state_delta(
            state,
            attempt_id=str(event["attempt_id"]),
            source_type=source_type,
            source_payload=payload,
            delta=delta,
        )

    def _save_state(self, state: Mapping[str, Any]) -> None:
        candidate = dict(state)
        events_path = self._events_path(str(candidate["session_id"]))
        if events_path.exists():
            candidate["events_digest"] = sha256_file(events_path)
        elif int(candidate["last_event_sequence"]) == -1:
            candidate["events_digest"] = sha256_bytes(b"")
        else:
            raise ExternalCodexRuntimeError(
                "runtime_event_state_drift",
                "cannot save runtime state without its normalized event stream",
            )
        validate_json(candidate, STATE_SCHEMA_PATH, label="runtime state")
        _atomic_write_json(self._state_path(str(candidate["session_id"])), candidate)

    def _failure_closeout_context(
        self,
        *,
        binding: IncarnationBinding,
        task: Mapping[str, Any],
        materialized_inputs: Mapping[str, str],
        session_dir: Path,
    ) -> dict[str, Any]:
        """Freeze source-independent failure evidence and wake semantics."""

        closeout_dir = session_dir / "failure-closeout"
        task_path = closeout_dir / "task.json"
        binding_path = closeout_dir / "incarnation-binding.json"
        _atomic_write_bytes(
            task_path,
            read_bounded(Path(materialized_inputs["task"])),
            mode=0o400,
        )
        _atomic_write_bytes(
            binding_path,
            read_bounded(Path(materialized_inputs["incarnation_binding"])),
            mode=0o400,
        )
        return {
            "target_owner": task["target_owner"],
            "task_ref": _artifact_ref(
                task_path,
                owner=str(task["target_owner"]),
            ),
            "incarnation_binding_ref": _artifact_ref(
                binding_path,
                owner="aoa-sdk",
            ),
            "wake_evaluations": {
                status: self._wake_evaluation(binding, status)
                for status in ("failed", "authority_blocked")
            },
        }

    def _events_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "events.jsonl"

    def _append_event(
        self,
        state: dict[str, Any],
        *,
        event_type: str,
        payload: Mapping[str, Any],
        attempt_id: str | None = None,
        thread_id: str | None = None,
        source_event_type: str | None = None,
        significance: Literal[
            "trace",
            "progress",
            "checkpoint",
            "review",
            "authority",
            "parent_wake",
            "terminal",
        ] = "trace",
    ) -> dict[str, Any]:
        sequence = int(state.get("last_event_sequence", -1)) + 1
        event = {
            "schema_version": "abyss_stack_external_codex_event_v1",
            "sequence": sequence,
            "recorded_at": iso_now(),
            "session_id": state["session_id"],
            "attempt_id": attempt_id
            or str(state.get("active_attempt_id") or "runtime"),
            "thread_id": thread_id if thread_id is not None else state.get("thread_id"),
            "event_type": event_type,
            "source_event_type": source_event_type,
            "payload_digest": canonical_digest(payload),
            "significance": significance,
            "payload": dict(payload),
        }
        validate_json(event, EVENT_SCHEMA_PATH, label="normalized runtime event")
        _append_jsonl(self._events_path(str(state["session_id"])), event)
        state["last_event_sequence"] = sequence
        return event

    def _load_coordinate(
        self,
        launch: Mapping[str, Any],
        key: str,
    ) -> tuple[Path, bytes, dict[str, Any]]:
        coordinate = launch[key]
        path = Path(str(coordinate["path"]))
        raw = read_bounded(path)
        if sha256_bytes(raw) != coordinate["digest"]:
            raise ExternalCodexRuntimeError(
                "artifact_digest_mismatch", f"{key} bytes differ from launch digest"
            )
        return path, raw, load_json_bytes(raw, label=key)

    def _validate_owner_contour_admission(
        self,
        *,
        owner_request_path: Path,
        launch: Mapping[str, Any],
        launch_raw: bytes,
        coordinates: Mapping[str, tuple[Path, bytes, dict[str, Any]]],
        plan: RunPlan,
        binding: IncarnationBinding,
        task: Mapping[str, Any],
        immutable_inputs: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        request_schema_coordinate = launch["owner_execution_request_schema"]
        dag_schema_coordinate = launch["task_local_dag_schema"]
        for key, coordinate in (
            ("owner_execution_request_schema", request_schema_coordinate),
            ("task_local_dag_schema", dag_schema_coordinate),
        ):
            delivered_identity = {
                field: coordinate[field]
                for field in (
                    "owner_repo",
                    "artifact_ref",
                    "source_ref",
                    "digest",
                    "schema_version",
                )
            }
            if delivered_identity != self.profile["owner_contracts"][key]:
                raise ExternalCodexRuntimeError(
                    "owner_admission_schema_identity_invalid",
                    "owner-contour schema differs from the runtime-profile-pinned owner source",
                )
        owner_request_raw = read_bounded(owner_request_path)
        owner_request = load_json_bytes(
            owner_request_raw, label="aoa-agents external execution request"
        )
        validate_json(
            owner_request,
            coordinates["owner_execution_request_schema"][0],
            label="aoa-agents external execution request",
        )
        if owner_request.get("request_digest") != owner_request_digest(owner_request):
            raise ExternalCodexRuntimeError(
                "owner_execution_request_digest_invalid",
                "owner execution request digest differs from its canonical bytes",
            )
        if (
            owner_request.get("intent") != "execute"
            or owner_request.get("summon_request", {}).get("transport_preference")
            != "external_cli"
        ):
            raise ExternalCodexRuntimeError(
                "owner_execution_request_not_executable",
                "owner-contour admission requires an execute request for external_cli",
            )
        external = owner_request["external_incarnation"]
        if (
            external["runtime_interface"] != "abyss_stack_external_codex_agent_v1"
            or external["launches_separate_os_process"] is not True
            or external["uses_builtin_codex_subagents"] is not False
            or external["separate_cli_session"] is not True
            or external["usage_metering"] != "observe_only_no_budget"
        ):
            raise ExternalCodexRuntimeError(
                "owner_execution_runtime_mismatch",
                "owner request does not admit this external process/session runtime",
            )
        if not isinstance(binding, AgentIncarnationBindingV2):
            raise ExternalCodexRuntimeError(
                "owner_incarnation_binding_v2_required",
                "new owner-contour execution requires an evidence-complete SDK v2 binding",
            )

        def exact_input(
            content_ref: Mapping[str, Any], *, label: str
        ) -> Mapping[str, Any]:
            matches = [
                item
                for item in immutable_inputs
                if item["provenance"].owner_repo == content_ref["owner_repo"]
                and item["provenance"].artifact_ref == content_ref["object_id"]
                and item["provenance"].schema_version == content_ref["schema_version"]
            ]
            if len(matches) != 1:
                raise ExternalCodexRuntimeError(
                    "owner_content_ref_unbound",
                    f"{label} is not one exact continuation-bound immutable input",
                )
            matched = matches[0]
            semantic_digest_fields = {
                "agent-obligation-v1": "obligation_digest",
                "actor-mandate-v1": "mandate_digest",
                "aoa_role_resolution_v1": "resolution_digest",
                "aoa_model_fit_query_result_v2": "result_digest",
            }
            digest_field = semantic_digest_fields.get(content_ref["schema_version"])
            if digest_field is None:
                digest_matches = (
                    matched["provenance"].artifact_digest == content_ref["digest"]
                )
            else:
                payload = load_json_bytes(matched["raw"], label=label)
                expected_digest = owner_object_digest(payload, digest_field)
                digest_matches = (
                    payload.get(digest_field) == expected_digest
                    and content_ref["digest"] == expected_digest
                )
            if not digest_matches:
                raise ExternalCodexRuntimeError(
                    "owner_content_ref_digest_invalid",
                    f"{label} semantic digest differs from its exact immutable bytes",
                )
            return matched

        obligation_input = exact_input(
            external["obligation_ref"], label="agent obligation"
        )
        mandate_input = exact_input(
            external["actor_mandate_ref"], label="actor mandate"
        )
        role_resolution_input = exact_input(
            external["role_resolution_ref"], label="role resolution"
        )
        model_fit_query_input = exact_input(
            external["model_fit_query_result_ref"], label="model-fit query result"
        )
        model_fit_projection_input = exact_input(
            external["model_fit_projection_ref"], label="model-fit projection"
        )
        dag_input = exact_input(external["task_local_dag_ref"], label="task-local DAG")
        transfer_input = exact_input(
            external["responsibility_transfer_ref"],
            label="responsibility transfer",
        )
        for index, procedure_ref in enumerate(external["domain_procedure_refs"]):
            exact_input(procedure_ref, label=f"domain procedure {index + 1}")

        dag = load_json_bytes(dag_input["raw"], label="task-local DAG")
        validate_json(
            dag,
            coordinates["task_local_dag_schema"][0],
            label="task-local DAG",
        )
        if dag.get("status") != "ready" or dag.get("authority") is not False:
            raise ExternalCodexRuntimeError(
                "task_local_dag_not_ready",
                "owner-contour launch requires a ready non-authoritative task-local DAG",
            )

        transfer = load_json_bytes(
            transfer_input["raw"], label="responsibility transfer"
        )
        transfer_holders = transfer.get("holder_ids")
        if transfer_holders is None:
            transfer_holders = [
                transfer.get("prior_holder"),
                transfer.get("current_holder"),
            ]
        if (
            transfer.get("schema_version") != "responsibility-transfer-v1"
            or transfer.get("state")
            != external["responsibility_transfer_ref"]["admitted_state"]
            or transfer_holders != external["responsibility_transfer_ref"]["holder_ids"]
            or transfer.get("obligation_ref") != external["obligation_ref"]["object_id"]
            or transfer.get("mandate_ref") != external["actor_mandate_ref"]["object_id"]
            or transfer.get("task_local_dag_ref")
            != external["task_local_dag_ref"]["object_id"]
            or transfer.get("return_owner") != owner_request["return_owner"]
        ):
            raise ExternalCodexRuntimeError(
                "responsibility_transfer_content_mismatch",
                "responsibility-transfer bytes do not prove the admitted holder transition",
            )

        obligation = load_json_bytes(obligation_input["raw"], label="agent obligation")
        if (
            obligation.get("schema_version") != "agent-obligation-v1"
            or obligation.get("obligation_id")
            != external["obligation_ref"]["object_id"]
            or obligation.get("goal_ref", {}).get("object_id") != task["parent_task_id"]
            or obligation.get("domain_owner") != task["target_owner"]
            or obligation.get("current_holder", {}).get("object_id")
            != transfer_holders[0]
            or obligation.get("return_owner", {}).get("object_id")
            != owner_request["return_owner"]
        ):
            raise ExternalCodexRuntimeError(
                "agent_obligation_content_mismatch",
                "agent-obligation bytes differ from the admitted duty and transfer",
            )

        mandate = load_json_bytes(mandate_input["raw"], label="actor mandate")
        if (
            mandate.get("schema_version") != "actor-mandate-v1"
            or mandate.get("mandate_id") != external["actor_mandate_ref"]["object_id"]
            or mandate.get("role_binding", {}).get("role_id") != binding.role_id
            or mandate.get("obligation_ref") != external["obligation_ref"]
            or mandate.get("goal_ref") != obligation.get("goal_ref")
            or mandate.get("role_resolution_ref") != external["role_resolution_ref"]
            or mandate.get("domain_procedure_refs") != external["domain_procedure_refs"]
            or mandate.get("return_owner") != obligation.get("return_owner")
            or mandate.get("return_owner", {}).get("object_id")
            != owner_request["return_owner"]
            or mandate.get("authority", {}).get("stop_line")
            != owner_request["child_stop_line"]
            or mandate.get("model_fit_relation", {}).get("relation_authority_ref")
            != obligation.get("current_holder")
        ):
            raise ExternalCodexRuntimeError(
                "actor_mandate_content_mismatch",
                "actor-mandate bytes differ from the admitted obligation, role, or procedure",
            )

        mandate_ref = external["actor_mandate_ref"]
        if (
            mandate_input["raw"] != coordinates["role_contract"][1]
            or binding.role_contract_ref.owner_repo != "aoa-agents"
            or binding.role_contract_ref.artifact_ref != mandate_ref["object_id"]
            or binding.role_contract_ref.schema_version != "actor-mandate-v1"
            or launch["role_contract"]["digest"]
            != binding.role_contract_ref.artifact_digest
        ):
            raise ExternalCodexRuntimeError(
                "actor_mandate_binding_mismatch",
                "incarnation role contract is not the exact admitted actor mandate",
            )

        role_resolution = load_json_bytes(
            role_resolution_input["raw"], label="role resolution"
        )
        role_binding = mandate["role_binding"]
        if (
            role_resolution.get("schema_version") != "aoa_role_resolution_v1"
            or role_resolution.get("resolution_id")
            != external["role_resolution_ref"]["object_id"]
            or role_resolution.get("role_id") != role_binding["role_id"]
            or role_resolution.get("specialization_id")
            != role_binding["specialization_id"]
            or role_resolution.get("tier_id") != role_binding["tier_id"]
            or role_resolution.get("base_role_ref") != role_binding["base_role_ref"]
            or role_resolution.get("specialization_ref")
            != role_binding["specialization_ref"]
            or role_resolution.get("tier_ref") != role_binding["tier_ref"]
            or role_resolution.get("capability_pack_refs")
            != role_binding["capability_pack_refs"]
        ):
            raise ExternalCodexRuntimeError(
                "role_resolution_content_mismatch",
                "role-resolution bytes differ from the exact admitted mandate role binding",
            )

        environment = mandate["environment"]
        sandbox_mode = environment["sandbox_mode"].replace("-", "_")
        named_outputs = {item["name"] for item in mandate["named_outputs"]}
        if (
            sandbox_mode != binding.permission_posture.sandbox_mode
            or set(environment["required_tools"])
            != set(binding.tool_profile.required_tool_ids)
            or set(environment["required_mcp_servers"])
            != set(binding.tool_profile.required_mcp_server_ids)
            or set(mandate["authority"]["allowed_effects"])
            != set(binding.permission_posture.allowed_effect_classes)
            or not named_outputs.issubset(set(owner_request["expected_outputs"]))
        ):
            raise ExternalCodexRuntimeError(
                "actor_mandate_incarnation_mismatch",
                "mandate environment, effects, tools, or outputs differ from the incarnation",
            )

        binding_content_refs = (
            (binding.agent_obligation_ref, external["obligation_ref"]),
            (binding.actor_mandate_ref, external["actor_mandate_ref"]),
            (binding.role_resolution_ref, external["role_resolution_ref"]),
            (
                binding.model_fit_query_result_ref,
                external["model_fit_query_result_ref"],
            ),
        )
        if any(
            bound.model_dump(mode="json") != admitted
            for bound, admitted in binding_content_refs
        ):
            raise ExternalCodexRuntimeError(
                "owner_incarnation_evidence_mismatch",
                "SDK incarnation names different obligation, mandate, role, or fit evidence",
            )
        projection_ref = external["model_fit_projection_ref"]
        if (
            binding.model_fit_projection_ref.owner_repo != projection_ref["owner_repo"]
            or binding.model_fit_projection_ref.artifact_ref
            != projection_ref["object_id"]
            or binding.model_fit_projection_ref.schema_version
            != projection_ref["schema_version"]
            or binding.model_fit_projection_ref.artifact_digest
            != projection_ref["digest"]
        ):
            raise ExternalCodexRuntimeError(
                "owner_model_fit_projection_mismatch",
                "SDK incarnation names another model-fit projection",
            )

        model_fit_query = load_json_bytes(
            model_fit_query_input["raw"], label="model-fit query result"
        )
        model_fit_projection = load_json_bytes(
            model_fit_projection_input["raw"], label="model-fit projection"
        )
        fit_family = mandate["model_fit_relation"]["task_family"]
        candidates = [
            candidate
            for candidate in model_fit_query.get("candidates", [])
            if candidate.get("projection_provenance")
            == binding.model_fit_projection_ref.model_dump(mode="json")
            and candidate.get("realization_provenance")
            == binding.model_realization_ref.model_dump(mode="json")
        ]
        if (
            model_fit_query.get("schema_version") != "aoa_model_fit_query_result_v2"
            or model_fit_query.get("query", {}).get("task_family") != fit_family
            or model_fit_query.get("candidate_count")
            != len(model_fit_query.get("candidates", []))
            or model_fit_query.get("authority", {}).get("informational_only")
            is not True
            or model_fit_query.get("authority", {}).get("activation_authority")
            is not False
            or len(candidates) != 1
            or model_fit_projection.get("schema_version")
            != "aoa_model_fit_projection_v1"
            or model_fit_projection.get("subject_realization_ref")
            != candidates[0]["realization_ref"]
            or not any(
                item.get("task_family") == fit_family
                for item in model_fit_projection.get("task_fit", [])
            )
        ):
            raise ExternalCodexRuntimeError(
                "model_fit_evidence_chain_invalid",
                "model-fit query, projection, realization, and mandate are not one exact chain",
            )

        incarnation_ref = external["incarnation_binding_ref"]
        if (
            incarnation_ref["object_id"] != binding.provenance.artifact_ref
            or incarnation_ref["digest"] != launch["incarnation_binding"]["digest"]
        ):
            raise ExternalCodexRuntimeError(
                "owner_incarnation_binding_mismatch",
                "owner request names another incarnation binding",
            )
        sdk_request_ref = external["sdk_summon_request_ref"]
        sdk_request_input = exact_input(
            sdk_request_ref, label="canonical SDK summon request"
        )
        if (
            sdk_request_ref["object_id"] != binding.task_request_ref.artifact_ref
            or sdk_request_ref["digest"] != binding.task_request_ref.artifact_digest
            or sdk_request_ref["schema_version"]
            != binding.task_request_ref.schema_version
        ):
            raise ExternalCodexRuntimeError(
                "owner_sdk_request_mismatch",
                "owner request names another canonical SDK summon request",
            )
        sdk_request = load_json_bytes(
            sdk_request_input["raw"], label="canonical SDK summon request"
        )
        sdk_summon = sdk_request.get("summon_request", {})
        expected_owner_summon = dict(sdk_summon)
        expected_owner_summon.pop("expected_outputs", None)
        expected_owner_summon["transport_preference"] = "external_cli"
        if (
            sdk_summon.get("transport_preference") not in {"a2a_remote", "either"}
            or owner_request["quest_passport"] != sdk_request.get("quest_passport")
            or owner_request["summon_request"] != expected_owner_summon
            or owner_request["expected_outputs"] != sdk_request.get("expected_outputs")
        ):
            raise ExternalCodexRuntimeError(
                "owner_sdk_request_content_mismatch",
                "owner execution request differs from the exact SDK external transport request",
            )
        sdk_decision_ref = external["sdk_summon_decision_ref"]
        decision_matches = [
            item
            for item in plan.snapshot.source_refs
            if item.owner_repo == sdk_decision_ref["owner_repo"]
            and item.artifact_ref == sdk_decision_ref["object_id"]
            and item.schema_version == sdk_decision_ref["schema_version"]
            and item.artifact_digest == sdk_decision_ref["digest"]
        ]
        if len(decision_matches) != 1:
            raise ExternalCodexRuntimeError(
                "owner_sdk_decision_mismatch",
                "owner request names no exact plan-bound SDK summon decision",
            )
        exact_input(sdk_decision_ref, label="SDK summon decision")

        runtime_launch_ref = external["runtime_launch_ref"]
        if runtime_launch_ref["object_id"] != launch["launch_id"] or runtime_launch_ref[
            "digest"
        ] != sha256_bytes(launch_raw):
            raise ExternalCodexRuntimeError(
                "owner_runtime_launch_mismatch",
                "owner request does not bind these exact launch bytes",
            )
        continuity_ref = external["continuity_ref"]
        continuity_is_binding = (
            continuity_ref["object_id"] == binding.continuation.continuation_id
            and continuity_ref["digest"] == launch["incarnation_binding"]["digest"]
        )
        if not continuity_is_binding:
            exact_input(continuity_ref, label="continuity")
        event_ref = external["return_event_schema_ref"]
        if (
            event_ref["digest"] != sha256_bytes(read_bounded(EVENT_SCHEMA_PATH))
            or event_ref["schema_version"] != "abyss_stack_external_codex_event_v1"
        ):
            raise ExternalCodexRuntimeError(
                "owner_return_event_schema_mismatch",
                "owner request names another runtime return-event ABI",
            )
        if (
            owner_request["summon_request"].get("desired_role")
            not in {None, binding.role_id}
            or owner_request["summon_request"].get("child_agent_id")
            not in {None, binding.incarnation_id}
            or owner_request["summon_request"].get("parent_task_id")
            not in {None, task["parent_task_id"]}
        ):
            raise ExternalCodexRuntimeError(
                "owner_request_identity_mismatch",
                "owner request role, child, or parent identity differs from the incarnation",
            )
        child_scope = owner_request["child_scope"]
        expected_outputs = set(str(item) for item in owner_request["expected_outputs"])
        if (
            child_scope["task"] != task["objective"]
            or set(child_scope["allowed_tools"])
            != set(binding.tool_profile.required_tool_ids)
            or child_scope["allowed_effects"] != [task["allowed_effect_class"]]
            or "external_codex_agent_result" not in expected_outputs
            or not set(task["expected_artifacts"]).issubset(expected_outputs)
        ):
            raise ExternalCodexRuntimeError(
                "owner_request_scope_mismatch",
                "owner request task, tools, effects, or named outputs differ from the bound duty",
            )
        return {
            "path": owner_request_path,
            "raw": owner_request_raw,
            "request": owner_request,
            "request_digest": sha256_bytes(owner_request_raw),
            "obligation_ref": external["obligation_ref"],
            "mandate_ref": mandate_ref,
            "dag_ref": external["task_local_dag_ref"],
            "transfer_ref": external["responsibility_transfer_ref"],
        }

    def _codex_preflight(
        self,
        launch: Mapping[str, Any],
        model_slug: str,
        reasoning_effort: str,
        tool_entry: Mapping[str, Any],
        *,
        repository_workspace: Path | None = None,
    ) -> dict[str, Any]:
        executable = Path(str(launch["codex_executable"]))
        if not executable.is_absolute() or not executable.is_file():
            raise ExternalCodexRuntimeError(
                "codex_unavailable", "Codex executable is not an absolute regular file"
            )
        if executable.resolve() != executable:
            raise ExternalCodexRuntimeError(
                "codex_executable_not_resolved",
                "Codex executable must be the resolved binary, not a symlink",
            )
        executable_digest = sha256_bytes(
            read_bounded(executable, limit=512 * 1024 * 1024)
        )
        if executable_digest != launch["codex_executable_digest"]:
            raise ExternalCodexRuntimeError(
                "codex_executable_drift", "Codex executable digest changed"
            )
        containment = self.profile["process_containment"]
        containment_paths = {
            "supervisor": PART_ROOT / str(containment["supervisor_ref"]),
            "mount_launcher": MOUNT_LAUNCHER_PATH,
            "probe_executable": Path(str(containment["probe_executable"])),
            "python_executable": Path(sys.executable).resolve(),
            "mount_wrapper": MOUNT_WRAPPER_PATH,
        }
        for label, path in containment_paths.items():
            if (
                not path.is_absolute()
                or not path.is_file()
                or path.resolve() != path
                or (
                    label not in {"supervisor", "mount_launcher"}
                    and not os.access(path, os.X_OK)
                )
            ):
                raise ExternalCodexRuntimeError(
                    "process_containment_unavailable",
                    f"configured {label} is not an exact executable",
                )
        if containment_paths["supervisor"] != SUPERVISOR_PATH:
            raise ExternalCodexRuntimeError(
                "process_containment_unavailable",
                "runtime profile selected an unexpected supervisor source",
            )
        if containment_paths["mount_launcher"] != MOUNT_LAUNCHER_PATH:
            raise ExternalCodexRuntimeError(
                "process_containment_unavailable",
                "runtime profile selected an unexpected mount launcher source",
            )
        mount_wrapper_digest = sha256_file(containment_paths["mount_wrapper"])
        mount_launcher_digest = sha256_file(containment_paths["mount_launcher"])
        for server in tool_entry["mcp_server_configs"]:
            token_name = str(server["bearer_token_env_var"])
            if not (
                BROKERED_MCP_CREDENTIALS.get(token_name)
                or os.environ.get(token_name)
            ):
                raise ExternalCodexRuntimeError(
                    "mcp_credential_unavailable",
                    f"required role-scoped MCP credential is unavailable: {token_name}",
                )
        env = self._codex_environment(
            launch,
            self.state_root,
            tool_entry,
            repository_workspace=repository_workspace,
        )
        probes: list[tuple[str, list[str]]] = [
            ("version", [str(executable), "--version"]),
            ("login", [str(executable), "login", "status"]),
            ("models", [str(executable), "debug", "models", "--bundled"]),
        ]
        results: dict[str, subprocess.CompletedProcess[str]] = {}
        for label, command in probes:
            try:
                completed = subprocess.run(
                    self._containment_command(
                        command,
                        executable_digest=executable_digest,
                    ),
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=30,
                    env=env,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ExternalCodexRuntimeError(
                    "codex_preflight_failed", f"Codex {label} probe failed"
                ) from exc
            if completed.returncode != 0:
                raise ExternalCodexRuntimeError(
                    "codex_preflight_failed", f"Codex {label} probe was rejected"
                )
            results[label] = completed
        version = results["version"].stdout.strip()
        expected_version = (
            "codex-cli " + self.profile["model_admission"]["runtime_version"]
        )
        if (
            self.profile["codex_cli"]["required_version"] != expected_version
            or version != expected_version
        ):
            raise ExternalCodexRuntimeError(
                "codex_version_mismatch",
                f"runtime requires {expected_version}, got {version}",
            )
        login_output = results["login"].stdout + results["login"].stderr
        if "Logged in using ChatGPT" not in login_output:
            raise ExternalCodexRuntimeError(
                "codex_auth_unavailable", "required ChatGPT Codex login is unavailable"
            )
        try:
            catalog = json.loads(results["models"].stdout)
        except json.JSONDecodeError as exc:
            raise ExternalCodexRuntimeError(
                "codex_model_catalog_invalid", "Codex model catalog is invalid JSON"
            ) from exc
        entry = _model_catalog_entry(catalog, model_slug)
        efforts = {
            item.get("effort")
            for item in (entry or {}).get("supported_reasoning_levels", [])
            if isinstance(item, dict)
        }
        if entry is None or reasoning_effort not in efforts:
            raise ExternalCodexRuntimeError(
                "codex_model_unavailable",
                f"{model_slug} effort {reasoning_effort} is absent from the live catalog",
            )
        containment_probe = self._containment_command(
            [str(containment_paths["probe_executable"])],
            executable_digest=sha256_file(containment_paths["probe_executable"]),
        )
        try:
            contained = subprocess.run(
                containment_probe,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExternalCodexRuntimeError(
                "process_containment_unavailable",
                "Linux subreaper-supervisor containment probe failed",
            ) from exc
        if contained.returncode != 0:
            raise ExternalCodexRuntimeError(
                "process_containment_unavailable",
                "Linux subreaper-supervisor containment probe was rejected",
            )
        with tempfile.TemporaryDirectory(
            prefix=".external-codex-preflight-",
            dir=self.state_root,
        ) as temporary:
            preflight_root = Path(temporary)
            execution_root = preflight_root / "execution-root"
            execution_root.mkdir(mode=0o700)
            for protected_directory in (".agents", ".codex", ".git"):
                (execution_root / protected_directory).mkdir(mode=0o700)
            target_config = execution_root / "repository-config"
            target_config.write_text("credential-marker\n", encoding="utf-8")
            sanitized_config = preflight_root / "sanitized-config"
            sanitized_config.write_text(
                "[core]\n\trepositoryFormatVersion = 0\n\tbare = false\n",
                encoding="utf-8",
            )
            sanitized_config.chmod(0o400)
            actor_git_mask = {
                "masks": [
                    {
                        "source": str(sanitized_config),
                        "target": str(target_config),
                        "digest": sha256_file(sanitized_config),
                    }
                ],
                "sanitized_config_path": str(sanitized_config),
            }
            actor_git_mask["private_directory_views"] = _private_directory_views(
                actor_git_mask["masks"]
            )
            permission_profile = _actor_codex_permission_profile(
                actor_git_mask,
                execution_root=execution_root,
                readable_paths=(sanitized_config, executable),
                writable_paths=(preflight_root,),
            )
            nested_sandbox_probe = [
                str(executable),
                "-c",
                'default_permissions="aoa_external_actor"',
                "-c",
                f"permissions.aoa_external_actor={permission_profile}",
                "--disable",
                "use_legacy_landlock",
                "sandbox",
                "-P",
                "aoa_external_actor",
                "-C",
                str(execution_root),
                "--",
                str(containment_paths["probe_executable"]),
            ]
            try:
                nested = subprocess.run(
                    self._containment_command(
                        nested_sandbox_probe,
                        executable_digest=executable_digest,
                        actor_git_mask=actor_git_mask,
                        mount_wrapper_digest=mount_wrapper_digest,
                        mount_launcher_digest=mount_launcher_digest,
                    ),
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=30,
                    env=env,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ExternalCodexRuntimeError(
                    "process_containment_unavailable",
                    "masked nested Codex sandbox preflight failed",
                ) from exc
            if nested.returncode != 0:
                raise ExternalCodexRuntimeError(
                    "process_containment_unavailable",
                    "masked nested Codex sandbox preflight was rejected",
                )
        return {
            "version": version,
            "auth_regime": "chatgpt_login",
            "model_slug": model_slug,
            "reasoning_effort": reasoning_effort,
            "executable_digest": executable_digest,
            "mount_wrapper_digest": mount_wrapper_digest,
            "mount_launcher_digest": mount_launcher_digest,
        }

    def _containment_command(
        self,
        command: Sequence[str],
        *,
        executable_digest: str,
        identity_path: Path | None = None,
        actor_git_mask: Mapping[str, Any] | None = None,
        mount_wrapper_digest: str | None = None,
        mount_launcher_digest: str | None = None,
        workspace_fd: int | None = None,
    ) -> list[str]:
        containment = self.profile["process_containment"]
        if containment["strategy"] != "linux_subreaper_supervisor_v1":
            raise ExternalCodexRuntimeError(
                "process_containment_unavailable",
                "runtime profile selected an unsupported process-containment strategy",
            )
        supervisor_argv = [
            str(Path(sys.executable).resolve()),
            str(SUPERVISOR_PATH),
            "--parent-pid",
            str(os.getpid()),
            "--term-timeout-seconds",
            str(containment["term_timeout_seconds"]),
            "--kill-timeout-seconds",
            str(containment["kill_timeout_seconds"]),
            "--executable-digest",
            executable_digest,
        ]
        if identity_path is not None:
            if not identity_path.is_absolute():
                raise ExternalCodexRuntimeError(
                    "codex_process_identity_invalid",
                    "process identity receipt path must be absolute",
                )
            supervisor_argv.extend(("--identity-file", str(identity_path)))
        if actor_git_mask is not None or workspace_fd is not None:
            if (
                not MOUNT_WRAPPER_PATH.is_file()
                or MOUNT_WRAPPER_PATH.resolve() != MOUNT_WRAPPER_PATH
                or not os.access(MOUNT_WRAPPER_PATH, os.X_OK)
                or mount_wrapper_digest is None
                or sha256_file(MOUNT_WRAPPER_PATH) != mount_wrapper_digest
                or mount_launcher_digest is None
                or sha256_file(MOUNT_LAUNCHER_PATH) != mount_launcher_digest
            ):
                raise ExternalCodexRuntimeError(
                    "actor_git_mask_unavailable",
                    "preflighted mount wrapper identity is unavailable",
                )
            supervisor_argv.extend(
                (
                    "--mount-wrapper",
                    str(MOUNT_WRAPPER_PATH),
                    "--mount-wrapper-digest",
                    mount_wrapper_digest,
                    "--mount-launcher-digest",
                    mount_launcher_digest,
                )
            )
            if workspace_fd is not None:
                if workspace_fd < 3:
                    raise ExternalCodexRuntimeError(
                        "actor_projection_unavailable",
                        "actor workspace descriptor is invalid",
                    )
                supervisor_argv.extend(
                    (
                        "--workspace-fd",
                        str(workspace_fd),
                        "--workspace-coordinate",
                        str(ACTOR_EXECUTION_ROOT),
                    )
                )
        if actor_git_mask is not None:
            masks = actor_git_mask.get("masks")
            private_directory_views = actor_git_mask.get("private_directory_views")
            if (
                not isinstance(masks, list)
                or not masks
                or not isinstance(private_directory_views, list)
                or not private_directory_views
            ):
                raise ExternalCodexRuntimeError(
                    "actor_git_mask_unavailable",
                    "external actor Git mask contains no private mount view",
                )
            view_targets: set[Path] = set()
            for view in private_directory_views:
                target = Path(str(view.get("target", "")))
                identity = view.get("identity")
                entries = view.get("entries")
                if (
                    not target.is_absolute()
                    or not isinstance(identity, dict)
                    or not isinstance(entries, list)
                ):
                    raise ExternalCodexRuntimeError(
                        "actor_git_mask_unavailable",
                        "external actor private mount view has an invalid shape",
                    )
                _assert_private_view_identity(target, identity, directory=True)
                view_targets.add(target)
                supervisor_argv.extend(
                    (
                        "--private-directory-view",
                        json.dumps(view, sort_keys=True, separators=(",", ":")),
                    )
                )
            for mask in masks:
                source = Path(str(mask.get("source", "")))
                target = Path(str(mask.get("target", "")))
                digest = str(mask.get("digest", ""))
                if (
                    not source.is_absolute()
                    or not target.is_absolute()
                    or target.parent not in view_targets
                    or not source.is_file()
                    or source.is_symlink()
                    or sha256_file(source) != digest
                ):
                    raise ExternalCodexRuntimeError(
                        "actor_git_mask_unavailable",
                        "external actor Git mask changed before containment",
                    )
                supervisor_argv.extend(
                    ("--read-only-mask", str(source), str(target), digest)
                )
        return [*supervisor_argv, "--", *command]

    def _validate_launch(
        self,
        launch_path: Path,
        *,
        owner_request_path: Path | None = None,
    ) -> dict[str, Any]:
        launch_raw = read_bounded(launch_path)
        launch = load_json_bytes(launch_raw, label="external Codex launch")
        if (
            launch.get("admission_class") == "owner_contour"
            and owner_request_path is None
        ):
            raise ExternalCodexRuntimeError(
                "owner_contour_admission_unbound",
                "owner_contour requires the separate aoa-agents execution request",
            )
        validate_json(launch, LAUNCH_SCHEMA_PATH, label="external Codex launch")
        if (
            launch["admission_class"] == "transport_study_fixture"
            and owner_request_path is not None
        ):
            raise ExternalCodexRuntimeError(
                "fixture_owner_admission_forbidden",
                "transport fixtures cannot be promoted by attaching an owner request",
            )
        coordinates: dict[str, tuple[Path, bytes, dict[str, Any]]] = {}
        coordinate_keys = [
            "plan",
            "incarnation_binding",
            "model_realization",
            "task",
            "runtime_profile",
            "role_contract",
            "result_schema",
        ]
        if launch["admission_class"] == "owner_contour":
            coordinate_keys.extend(
                ("owner_execution_request_schema", "task_local_dag_schema")
            )
        for key in coordinate_keys:
            coordinates[key] = self._load_coordinate(launch, key)

        if coordinates["runtime_profile"][1] != self.profile_raw:
            raise ExternalCodexRuntimeError(
                "runtime_profile_mismatch", "launch profile is not this runtime profile"
            )
        plan = RunPlan.model_validate(coordinates["plan"][2])
        binding = parse_incarnation_binding(coordinates["incarnation_binding"][2])
        assert_agent_incarnation_binding_matches_plan(binding, plan)
        task = coordinates["task"][2]
        validate_json(task, TASK_SCHEMA_PATH, label="external Codex task")
        if set(task["forbidden_effects"]) != RUNTIME_WIDE_FORBIDDEN_EFFECTS:
            raise ExternalCodexRuntimeError(
                "task_forbidden_effects_incomplete",
                "task must preserve the complete runtime-wide forbidden-effect set",
            )
        validation_command_ids = [
            str(item["command_id"]) for item in task["validation_commands"]
        ]
        if len(validation_command_ids) != len(set(validation_command_ids)):
            raise ExternalCodexRuntimeError(
                "task_validation_command_duplicate",
                "task validation command ids must be unique",
            )
        if any(item["cwd"] != "." for item in task["validation_commands"]):
            raise ExternalCodexRuntimeError(
                "task_validation_cwd_unsupported",
                "fixed validation commands must execute from the exact workspace root",
            )
        validation_signatures = [
            (str(item["cwd"]), tuple(str(value) for value in item["argv"]))
            for item in task["validation_commands"]
        ]
        if len(validation_signatures) != len(set(validation_signatures)):
            raise ExternalCodexRuntimeError(
                "task_validation_command_ambiguous",
                "fixed validation argv/cwd pairs must be unique",
            )
        for item in task["validation_commands"]:
            _descriptor_validation_wrapper_argv(ACTOR_EXECUTION_ROOT, item)
        realization = coordinates["model_realization"][2]

        exact_refs = (
            (binding.role_contract_ref, "role_contract"),
            (binding.model_realization_ref, "model_realization"),
            (binding.runtime_profile_ref, "runtime_profile"),
            (binding.expected_result_schema_ref, "result_schema"),
        )
        for ref, key in exact_refs:
            if ref.artifact_digest != launch[key]["digest"]:
                raise ExternalCodexRuntimeError(
                    "incarnation_artifact_mismatch",
                    f"incarnation {key} ref differs from delivered bytes",
                )
        task_contract_refs = [
            item
            for item in plan.runtime_profile.constraint_refs
            if item.artifact_digest == launch["task"]["digest"]
            and item.schema_version == "abyss_stack_external_codex_task_v1"
        ]
        if (
            len(task_contract_refs) != 1
            or task_contract_refs[0] not in plan.snapshot.source_refs
            or task_contract_refs[0] not in binding.continuation.immutable_input_refs
        ):
            raise ExternalCodexRuntimeError(
                "task_contract_unbound",
                "delivered task is not one exact snapshot/continuation-bound runtime constraint",
            )
        if binding.runtime_profile_ref != plan.runtime_profile.provenance:
            raise ExternalCodexRuntimeError(
                "incarnation_runtime_mismatch",
                "incarnation runtime profile differs from the exact plan",
            )
        if (
            task["correlation_id"] != binding.correlation_id
            or task["continuation_id"] != binding.continuation.continuation_id
            or task["expected_incarnation_id"] != binding.incarnation_id
        ):
            raise ExternalCodexRuntimeError(
                "task_identity_mismatch",
                "task correlation, continuation, or incarnation identity differs from the binding",
            )
        if task["target_owner"] not in binding.continuation.owner_scope:
            raise ExternalCodexRuntimeError(
                "task_owner_out_of_scope", "target owner is outside continuation scope"
            )
        if task["return_owner"] != binding.continuation.return_owner.owner_repo:
            raise ExternalCodexRuntimeError(
                "return_owner_mismatch", "task and continuation return owners differ"
            )
        if not set(task["authority_scope"]).issubset(binding.continuation.owner_scope):
            raise ExternalCodexRuntimeError(
                "task_authority_out_of_scope",
                "task authority scope exceeds the continuation owner scope",
            )
        if (
            task["allowed_effect_class"]
            not in binding.permission_posture.allowed_effect_classes
        ):
            raise ExternalCodexRuntimeError(
                "task_effect_out_of_scope", "task effect exceeds incarnation permission"
            )
        if (
            binding.usage_metering.mode != "observe_only"
            or binding.usage_metering.metering_regime != "chatgpt_quota"
        ):
            raise ExternalCodexRuntimeError(
                "metering_regime_unsupported",
                "ChatGPT execution requires observe-only metering under chatgpt_quota",
            )
        continuation_inputs = set(binding.continuation.immutable_input_refs)
        immutable_inputs: list[dict[str, Any]] = []
        input_ids: set[str] = set()
        input_refs: set[ProvenanceRef] = set()
        for item in task["immutable_inputs"]:
            input_id = str(item["input_id"])
            if INPUT_ID_RE.fullmatch(input_id) is None:
                raise ExternalCodexRuntimeError(
                    "immutable_input_id_invalid",
                    "immutable input ids must be stable lowercase hyphenated identities",
                )
            path = Path(str(item["local_path"]))
            provenance = ProvenanceRef.model_validate(item["provenance"])
            if input_id in input_ids or provenance in input_refs:
                raise ExternalCodexRuntimeError(
                    "immutable_input_duplicate",
                    "task immutable input ids and provenance refs must be unique",
                )
            raw = read_bounded(path)
            if sha256_bytes(raw) != provenance.artifact_digest:
                raise ExternalCodexRuntimeError(
                    "immutable_input_drift",
                    f"immutable input differs from its exact digest: {input_id}",
                )
            if provenance not in continuation_inputs:
                raise ExternalCodexRuntimeError(
                    "immutable_input_out_of_scope",
                    f"immutable input is absent from the continuation: {input_id}",
                )
            input_ids.add(input_id)
            input_refs.add(provenance)
            immutable_inputs.append(
                {
                    "input_id": input_id,
                    "source_path": path,
                    "raw": raw,
                    "provenance": provenance,
                }
            )
        request_inputs = [
            item
            for item in immutable_inputs
            if item["provenance"] == binding.task_request_ref
        ]
        expected_request_input_id = (
            "review-summon-request"
            if task["execution_posture"] == "independent_review"
            else "summon-request"
        )
        if (
            len(request_inputs) != 1
            or request_inputs[0]["input_id"] != expected_request_input_id
        ):
            raise ExternalCodexRuntimeError(
                "incarnation_task_request_unbound",
                "incarnation task request is not the exact canonical immutable summon input",
            )
        request_payload = load_json_bytes(
            request_inputs[0]["raw"], label="canonical immutable summon request"
        )
        nested_request = request_payload.get("summon_request")
        passport = request_payload.get("quest_passport")
        expected_outputs = request_payload.get("expected_outputs")
        allowed_transport_preferences = (
            {"a2a_remote", "either"}
            if launch["admission_class"] == "owner_contour"
            else {"codex_local"}
        )
        if (
            not isinstance(nested_request, dict)
            or not isinstance(passport, dict)
            or not isinstance(expected_outputs, list)
            or not expected_outputs
            or any(not isinstance(item, str) or not item for item in expected_outputs)
            or len(set(expected_outputs)) != len(expected_outputs)
            or nested_request.get("expected_outputs") != expected_outputs
            or passport.get("expected_artifacts") != expected_outputs
            or passport.get("control_mode") != "codex_supervised"
            or passport.get("self_agent") is not False
            or not isinstance(passport.get("route_anchor"), str)
            or not passport["route_anchor"]
            or nested_request.get("desired_role") != binding.role_id
            or nested_request.get("child_agent_id") != binding.incarnation_id
            or nested_request.get("parent_task_id") != task["parent_task_id"]
            or nested_request.get("session_ref") != launch["session_id"]
            or nested_request.get("review_required") is not task["review_required"]
            or nested_request.get("transport_preference")
            not in allowed_transport_preferences
            or nested_request.get("require_progression") is not False
            or nested_request.get("workspace_root") != launch["workspace_path"]
            or request_payload.get("reviewed_artifact_path")
            != nested_request.get("reviewed_artifact_path")
        ):
            raise ExternalCodexRuntimeError(
                "incarnation_task_request_unbound",
                "summon request semantics differ from the exact task/incarnation",
            )
        request_capabilities = nested_request.get("capability_refs")
        plan_capabilities = {
            item.capability_id for item in plan.scenario_binding.capability_refs
        }
        if (
            not isinstance(request_capabilities, list)
            or not request_capabilities
            or any(
                not isinstance(item, str) or not item or item not in plan_capabilities
                for item in request_capabilities
            )
        ):
            raise ExternalCodexRuntimeError(
                "incarnation_task_request_capability_unbound",
                "summon request capabilities are not bound by the admitted run plan",
            )

        owner_admission = None
        if owner_request_path is not None:
            if (
                not owner_request_path.is_absolute()
                or not owner_request_path.is_file()
                or owner_request_path.is_symlink()
            ):
                raise ExternalCodexRuntimeError(
                    "owner_execution_request_unavailable",
                    "owner execution request must be an absolute regular non-symlink file",
                )
            owner_admission = self._validate_owner_contour_admission(
                owner_request_path=owner_request_path,
                launch=launch,
                launch_raw=launch_raw,
                coordinates=coordinates,
                plan=plan,
                binding=binding,
                task=task,
                immutable_inputs=immutable_inputs,
            )

        if (
            realization.get("kind") != "ModelRealization"
            or realization.get("schema_version") != "aoa_model_realization_v1"
            or not isinstance(realization.get("configuration"), dict)
        ):
            raise ExternalCodexRuntimeError(
                "model_realization_invalid",
                "aoa-models realization identity is invalid",
            )
        configuration = realization["configuration"]
        runtime = configuration.get("runtime")
        tools = configuration.get("tools")
        permissions = configuration.get("permissions")
        access = configuration.get("access")
        if not all(
            isinstance(item, dict) for item in (runtime, tools, permissions, access)
        ):
            raise ExternalCodexRuntimeError(
                "model_realization_invalid",
                "model realization configuration is incomplete",
            )
        model_slug = str(runtime.get("model_slug"))
        effort = str(configuration.get("reasoning_effort"))
        model_admission = self.profile["model_admission"]
        if (
            runtime.get("product") != model_admission["runtime_product"]
            or runtime.get("version") != model_admission["runtime_version"]
            or runtime.get("transport") != model_admission["transport"]
            or access.get("auth_regime") != model_admission["auth_regime"]
            or access.get("billing_regime") != model_admission["billing_regime"]
            or realization.get("lifecycle_state")
            not in model_admission["allowed_lifecycle_states"]
        ):
            raise ExternalCodexRuntimeError(
                "model_realization_unsupported",
                "model realization is not the admitted Codex lane",
            )
        if not model_slug or not effort:
            raise ExternalCodexRuntimeError(
                "model_realization_unsupported",
                "model realization must name a model and reasoning effort",
            )
        tool_entry = next(
            (
                item
                for item in self.profile["tool_profiles"]
                if item["profile_id"] == binding.tool_profile.profile_id
            ),
            None,
        )
        if tool_entry is None:
            raise ExternalCodexRuntimeError(
                "tool_profile_unavailable", "incarnation tool profile is not admitted"
            )
        mcp_configs = tool_entry["mcp_server_configs"]
        if [item["server_id"] for item in mcp_configs] != list(
            binding.tool_profile.required_mcp_server_ids
        ):
            raise ExternalCodexRuntimeError(
                "mcp_profile_mismatch",
                "runtime MCP configs differ from the incarnation MCP profile",
            )
        realization_sandbox_mode = {
            "read_only": "read-only",
            "workspace_write": "workspace-write",
        }.get(str(tool_entry["sandbox_mode"]))
        if (
            tools.get("profile_ref") != binding.tool_profile.profile_id
            or tuple(tools.get("required_tools") or ())
            != binding.tool_profile.required_tool_ids
            or tuple(tools.get("required_mcp_servers") or ())
            != binding.tool_profile.required_mcp_server_ids
            or tools.get("inheritance_allowed") is not False
            or binding.tool_profile.inherit_user_configuration is not False
            or list(binding.permission_posture.allowed_effect_classes)
            != tool_entry["allowed_effect_classes"]
            or binding.permission_posture.sandbox_mode != tool_entry["sandbox_mode"]
            or binding.permission_posture.approval_policy
            != tool_entry["approval_policy"]
            or binding.permission_posture.network_access != tool_entry["network_access"]
            or binding.permission_posture.external_effects is not False
            or permissions.get("sandbox_mode") != realization_sandbox_mode
            or permissions.get("approval_policy") != tool_entry["approval_policy"]
            or permissions.get("network_access") != tool_entry["network_access"]
            or permissions.get("external_effects") is not False
        ):
            raise ExternalCodexRuntimeError(
                "incarnation_profile_mismatch",
                "model, tool, and permission profiles are not exact",
            )
        if task["execution_posture"] not in self.profile["execution_postures"]:
            raise ExternalCodexRuntimeError(
                "execution_posture_unsupported",
                "execution posture is not runtime-admitted",
            )
        expected_effect = (
            "repo_mutation"
            if binding.permission_posture.sandbox_mode == "workspace_write"
            else "read_only"
        )
        if task["allowed_effect_class"] != expected_effect:
            raise ExternalCodexRuntimeError(
                "task_effect_mismatch", "task effect differs from sandbox posture"
            )
        result_schema = coordinates["result_schema"][2]
        Draft202012Validator.check_schema(result_schema)
        if result_schema != load_schema(REPORT_SCHEMA_PATH):
            raise ExternalCodexRuntimeError(
                "result_schema_mismatch",
                "launch result schema is not the admitted report schema",
            )

        workspace = Path(str(launch["workspace_path"]))
        projection_seed = launch.get("workspace_projection_seed")
        if not workspace.is_absolute():
            raise ExternalCodexRuntimeError(
                "workspace_unavailable", "workspace path is not absolute"
            )
        review_seed = None
        if projection_seed is not None:
            if not isinstance(projection_seed, dict):
                raise ExternalCodexRuntimeError(
                    "workspace_projection_seed_invalid",
                    "workspace projection seed has no controller envelope",
                )
            review_seed = self._validate_review_seed(
                projection_seed,
                reviewer_session_id=str(launch["session_id"]),
                task=task,
                binding=binding,
            )
        else:
            if workspace.is_symlink() or not workspace.is_dir():
                raise ExternalCodexRuntimeError(
                    "workspace_unavailable",
                    "workspace path is not an absolute directory",
                )
            try:
                workspace = workspace.resolve(strict=True)
            except OSError as exc:
                raise ExternalCodexRuntimeError(
                    "workspace_unavailable",
                    "workspace canonical coordinate is unavailable",
                ) from exc
            for minimal_root in CODEX_MINIMAL_READ_ROOTS:
                try:
                    workspace.relative_to(minimal_root)
                except ValueError:
                    continue
                raise ExternalCodexRuntimeError(
                    "workspace_minimal_read_root_unsupported",
                    "source workspace may not be admitted beneath a Codex minimal-read root",
                )
        source_path = str(workspace)
        if any(
            _contains_source_path(item["argv"], source_path)
            for item in task["validation_commands"]
        ):
            raise ExternalCodexRuntimeError(
                "task_validation_source_path_unsupported",
                "fixed validation argv may not expose the source workspace path",
            )
        if binding.workspace_source_ref.source_ref != launch["workspace_expected_head"]:
            raise ExternalCodexRuntimeError(
                "workspace_source_mismatch",
                "incarnation workspace source does not name the exact Git HEAD",
            )
        workspace_manifest_input_id = str(launch["workspace_manifest_input_id"])
        manifest_inputs = [
            item
            for item in immutable_inputs
            if item["input_id"] == workspace_manifest_input_id
        ]
        if (
            launch["workspace_initial_posture"] == "exact_baseline"
            and len(manifest_inputs) != 1
        ):
            raise ExternalCodexRuntimeError(
                "workspace_manifest_required",
                "exact_baseline requires one immutable workspace-manifest input",
            )
        if len(manifest_inputs) > 1:
            raise ExternalCodexRuntimeError(
                "workspace_manifest_duplicate",
                "workspace baseline may bind only one selected workspace manifest",
            )
        workspace_manifest_baseline: dict[str, Any]
        if review_seed is not None:
            workspace_manifest_baseline = _load_verified_json_ref(
                review_seed["writer_source_manifest_ref"],
                label="historical writer source manifest",
                schema_path=WORKSPACE_MANIFEST_SCHEMA_PATH,
            )
            if (
                workspace_manifest_baseline.get("git_head")
                != launch["workspace_expected_head"]
            ):
                raise ExternalCodexRuntimeError(
                    "review_seed_source_mismatch",
                    "review seed historical source does not bind the requested Git HEAD",
                )
            baseline = {
                str(item["path"]): str(item["status"])
                for item in workspace_manifest_baseline.get("status_entries", [])
            }
        elif manifest_inputs:
            manifest = load_json_bytes(
                manifest_inputs[0]["raw"], label="external Codex workspace manifest"
            )
            assert_workspace_manifest(manifest, workspace)
            workspace_manifest_baseline = manifest
            baseline = _git_status(workspace)
        else:
            workspace_manifest_baseline = build_workspace_manifest(workspace)
            baseline = _git_status(workspace)
        if review_seed is None:
            if _git_head(workspace) != launch["workspace_expected_head"]:
                raise ExternalCodexRuntimeError(
                    "workspace_head_mismatch",
                    "workspace HEAD differs from the launch binding",
                )
            if launch["workspace_initial_posture"] == "clean_required" and baseline:
                raise ExternalCodexRuntimeError(
                    "workspace_not_clean", "launch requires a clean isolated workspace"
                )
        codex_home = Path(str(launch["codex_home"]))
        if not codex_home.is_absolute() or not codex_home.is_dir():
            raise ExternalCodexRuntimeError(
                "codex_home_unavailable", "explicit Codex home is unavailable"
            )
        preflight = self._codex_preflight(
            launch,
            model_slug,
            effort,
            tool_entry,
            repository_workspace=(
                Path(str(review_seed["writer_projection_path"]))
                if review_seed is not None
                else workspace
            ),
        )
        return {
            "launch": launch,
            "launch_raw": launch_raw,
            "launch_digest": sha256_bytes(launch_raw),
            "coordinates": coordinates,
            "plan": plan,
            "binding": binding,
            "task": task,
            "realization": realization,
            "model_slug": model_slug,
            "reasoning_effort": effort,
            "tool_entry": tool_entry,
            "workspace": workspace,
            "baseline": baseline,
            "workspace_manifest_baseline": workspace_manifest_baseline,
            "preflight": preflight,
            "immutable_inputs": immutable_inputs,
            "owner_admission": owner_admission,
            "review_seed": review_seed,
        }

    def _review_seed_envelope_locked(
        self,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        session_id = str(state["session_id"])
        if (
            state.get("status") not in {"completed", "review_required"}
            or state.get("active_attempt_id") is not None
            or state.get("worker_pid") is not None
            or state.get("supervisor_pid") is not None
            or state.get("codex_pid") is not None
            or not isinstance(state.get("thread_id"), str)
            or not state.get("thread_id")
        ):
            raise ExternalCodexRuntimeError(
                "review_seed_writer_not_terminal",
                "review seed requires one terminal writer with no live process owner",
            )
        result_path = self._session_dir(session_id) / "result.json"
        result = load_json(result_path, label="terminal writer result")
        validate_json(result, RESULT_SCHEMA_PATH, label="terminal writer result")
        if sha256_file(result_path) != state.get("result_digest"):
            raise ExternalCodexRuntimeError(
                "review_seed_writer_result_unbound",
                "terminal writer result bytes differ from locked runtime state",
            )
        final_ref = state.get("actor_final_manifest_ref")
        delta_ref = state.get("actor_delta_ref")
        source_ref = state.get("source_manifest_before_ref")
        if not all(
            isinstance(item, dict) for item in (final_ref, delta_ref, source_ref)
        ):
            raise ExternalCodexRuntimeError(
                "review_seed_writer_evidence_incomplete",
                "terminal writer has no exact projection, delta, or source provenance",
            )
        if (
            result.get("session_id") != session_id
            or result.get("incarnation_id") != state.get("incarnation_id")
            or result.get("thread_id") != state.get("thread_id")
            or result.get("status") != state.get("status")
            or result.get("actor_final_manifest_ref") != final_ref
            or result.get("actor_delta_ref") != delta_ref
            or result.get("source_manifest_before_ref") != source_ref
            or result.get("actor_projection_path") != state.get("actor_projection_path")
        ):
            raise ExternalCodexRuntimeError(
                "review_seed_writer_result_unbound",
                "terminal writer result differs from its locked runtime state",
            )
        final_manifest = _load_verified_json_ref(
            final_ref,
            label="terminal writer actor final manifest",
            schema_path=ACTOR_MANIFEST_SCHEMA_PATH,
        )
        _load_verified_json_ref(
            delta_ref,
            label="terminal writer actor delta",
            schema_path=ACTOR_DELTA_SCHEMA_PATH,
        )
        source_manifest = _load_verified_json_ref(
            source_ref,
            label="terminal writer source manifest",
            schema_path=WORKSPACE_MANIFEST_SCHEMA_PATH,
        )
        projection_path = self._projection_path_from_state(state)
        projection_flags = os.O_PATH | os.O_CLOEXEC | os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            projection_flags |= os.O_NOFOLLOW
        try:
            projection_fd = os.open(projection_path, projection_flags)
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "review_seed_writer_projection_unavailable",
                "terminal writer projection cannot be descriptor-bound",
            ) from exc
        try:
            observed_manifest = _checked_actor_manifest(
                projection_path,
                source_manifest_digest=str(source_ref["artifact_digest"]),
                source_git_head=str(source_manifest["git_head"]),
                projection_fd=projection_fd,
            )
            _assert_descriptor_coordinate(projection_fd, projection_path)
        finally:
            os.close(projection_fd)
        if observed_manifest != final_manifest:
            raise ExternalCodexRuntimeError(
                "review_seed_writer_projection_drift",
                "terminal writer projection differs from its final manifest",
            )
        return {
            "schema_version": "abyss_stack_external_codex_review_seed_envelope_v1",
            "writer_session_id": session_id,
            "writer_incarnation_id": str(state["incarnation_id"]),
            "writer_thread_id": str(state["thread_id"]),
            "writer_status": str(state["status"]),
            "writer_result_ref": _artifact_ref(result_path),
            "writer_projection_path": str(state["actor_projection_path"]),
            "writer_final_manifest_ref": dict(final_ref),
            "writer_delta_ref": dict(delta_ref),
            "writer_source_manifest_ref": dict(source_ref),
        }

    def issue_review_seed(self, writer_session_id: str) -> dict[str, Any]:
        """Issue one content-addressed reviewer capability under the writer lock."""

        with self._lock(writer_session_id):
            state = self._load_state(writer_session_id)
            envelope = self._review_seed_envelope_locked(state)
            validate_json(
                envelope,
                REVIEW_SEED_ENVELOPE_SCHEMA_PATH,
                label="external Codex review seed envelope",
            )
            envelope_path = (
                self._session_dir(writer_session_id) / "review-seed-envelope.json"
            )
            _atomic_write_json(envelope_path, envelope, mode=0o400)
            return _artifact_ref(envelope_path)

    def _validate_review_seed(
        self,
        seed: Mapping[str, Any],
        *,
        reviewer_session_id: str,
        task: Mapping[str, Any],
        binding: IncarnationBinding,
    ) -> dict[str, Any]:
        if (
            task.get("execution_posture") != "independent_review"
            or task.get("allowed_effect_class") != "read_only"
            or binding.permission_posture.sandbox_mode != "read_only"
        ):
            raise ExternalCodexRuntimeError(
                "workspace_projection_seed_forbidden",
                "writer projection seeds are admitted only for a read-only independent reviewer",
            )
        envelope_path = Path(str(seed.get("envelope_path", "")))
        envelope_ref = {
            "owner_repo": "abyss-stack",
            "artifact_ref": str(envelope_path),
            "artifact_digest": str(seed.get("envelope_digest", "")),
        }
        envelope = _load_verified_json_ref(
            envelope_ref,
            label="external Codex review seed envelope",
            schema_path=REVIEW_SEED_ENVELOPE_SCHEMA_PATH,
        )
        writer_session_id = str(envelope["writer_session_id"])
        if writer_session_id == reviewer_session_id:
            raise ExternalCodexRuntimeError(
                "review_seed_session_reuse",
                "reviewer must have a distinct session identity",
            )
        expected_path = (
            self._session_dir(writer_session_id) / "review-seed-envelope.json"
        )
        if envelope_path != expected_path:
            raise ExternalCodexRuntimeError(
                "review_seed_envelope_unowned",
                "review seed envelope is outside its exact writer session",
            )
        with self._lock(writer_session_id):
            writer_state = self._load_state(writer_session_id)
            writer_task_family = str(writer_state.get("task_family") or "")
            expected_reviewer_family = (
                "landing_review"
                if writer_task_family.startswith("landing")
                else f"{writer_task_family}_review"
            )
            if (
                not writer_task_family
                or task.get("task_family") != expected_reviewer_family
            ):
                raise ExternalCodexRuntimeError(
                    "workspace_projection_seed_forbidden",
                    "reviewer task family is not derived from the exact seeded writer task family",
                )
            expected = self._review_seed_envelope_locked(writer_state)
            if envelope != expected:
                raise ExternalCodexRuntimeError(
                    "review_seed_envelope_drift",
                    "review seed envelope differs from the locked terminal writer",
                )
            if task.get("parent_task_id") != writer_state.get("task_id"):
                raise ExternalCodexRuntimeError(
                    "review_seed_parent_task_mismatch",
                    "reviewer task is not the child of the exact seeded writer task",
                )
            immutable_by_id = {
                str(item.get("input_id")): item.get("provenance")
                for item in task.get("immutable_inputs", [])
                if isinstance(item, dict)
            }
            required_digests = {
                "writer-runtime-result": envelope["writer_result_ref"][
                    "artifact_digest"
                ],
                "writer-actor-final-manifest": envelope["writer_final_manifest_ref"][
                    "artifact_digest"
                ],
                "writer-actor-delta": envelope["writer_delta_ref"]["artifact_digest"],
                "review-workspace-manifest": envelope["writer_source_manifest_ref"][
                    "artifact_digest"
                ],
            }
            if any(
                not isinstance(immutable_by_id.get(input_id), dict)
                or immutable_by_id[input_id].get("artifact_digest") != digest
                for input_id, digest in required_digests.items()
            ):
                raise ExternalCodexRuntimeError(
                    "review_seed_evidence_mismatch",
                    "reviewer immutable evidence does not bind the seeded writer result",
                )
        return envelope

    def preflight(
        self,
        launch_path: str | Path,
        *,
        owner_request_path: str | Path | None = None,
    ) -> dict[str, Any]:
        validated = self._validate_launch(
            Path(launch_path),
            owner_request_path=(
                Path(owner_request_path) if owner_request_path is not None else None
            ),
        )
        binding: IncarnationBinding = validated["binding"]
        return {
            "admitted": True,
            "launch_digest": validated["launch_digest"],
            "session_id": validated["launch"]["session_id"],
            "admission_class": validated["launch"]["admission_class"],
            "incarnation_id": binding.incarnation_id,
            "model_slug": validated["model_slug"],
            "reasoning_effort": validated["reasoning_effort"],
            "workspace_head": validated["launch"]["workspace_expected_head"],
            "tool_profile_id": binding.tool_profile.profile_id,
            "external_effects": False,
            "owner_admission_digest": (
                validated["owner_admission"]["request_digest"]
                if validated["owner_admission"] is not None
                else None
            ),
            "preflight": validated["preflight"],
        }

    def start(
        self,
        launch_path: str | Path,
        *,
        owner_request_path: str | Path | None = None,
    ) -> dict[str, Any]:
        validated = self._validate_launch(
            Path(launch_path),
            owner_request_path=(
                Path(owner_request_path) if owner_request_path is not None else None
            ),
        )
        launch = validated["launch"]
        session_id = str(launch["session_id"])
        session_dir = self._session_dir(session_id)
        with self._lock(session_id):
            state_path = self._state_path(session_id)
            if state_path.is_file():
                state = self._load_state(session_id)
                if state.get("launch_digest") != validated["launch_digest"]:
                    raise ExternalCodexRuntimeError(
                        "session_binding_conflict",
                        "session already exists with another launch binding",
                    )
                if (
                    state.get("status") == "prepared"
                    and not state.get("attempts")
                    and state.get("active_attempt_id") is None
                    and state.get("worker_pid") is None
                ):
                    if state.get(
                        "schema_version"
                    ) != STATE_SCHEMA_VERSION or not isinstance(
                        state.get("actor_projection_path"), str
                    ):
                        raise ExternalCodexRuntimeError(
                            "legacy_projection_unavailable",
                            "legacy session cannot receive a new inference attempt without a safe actor projection",
                        )
                    self._spawn_worker(state, mode="start", resume_payload=None)
                return self._public_state(state)
            inputs_dir = session_dir / "inputs"
            materialized: dict[str, str] = {}
            for key, (_, raw, _) in validated["coordinates"].items():
                suffix = ".json"
                target = inputs_dir / f"{key}{suffix}"
                _atomic_write_bytes(target, raw, mode=0o400)
                materialized[key] = str(target)
            if validated["owner_admission"] is not None:
                owner_request_target = inputs_dir / "owner-execution-request.json"
                _atomic_write_bytes(
                    owner_request_target,
                    validated["owner_admission"]["raw"],
                    mode=0o400,
                )
                materialized["owner_execution_request"] = str(owner_request_target)
            execution_result_schema_path = inputs_dir / "execution-result-schema.json"
            execution_result_schema = specialize_report_schema(
                validated["coordinates"]["result_schema"][2],
                task_id=str(validated["task"]["task_id"]),
                incarnation_id=validated["binding"].incarnation_id,
                immutable_input_ids=tuple(
                    str(item["input_id"]) for item in validated["immutable_inputs"]
                ),
            )
            _atomic_write_json(
                execution_result_schema_path,
                execution_result_schema,
                mode=0o400,
            )
            _atomic_write_bytes(
                inputs_dir / "launch.json", validated["launch_raw"], mode=0o400
            )
            controller_materialized_task_inputs: list[dict[str, Any]] = []
            materialized_task_inputs: list[dict[str, Any]] = []
            source_aliases = _actor_source_aliases(validated)
            source_roots = frozenset(
                {
                    str(validated["launch"]["workspace_path"]),
                    str(validated["workspace"]),
                    str(
                        validated["workspace_manifest_baseline"].get(
                            "workspace_path", ""
                        )
                    ),
                }
                - {""}
            )
            for index, item in enumerate(validated["immutable_inputs"], start=1):
                controller_target = (
                    inputs_dir / "controller-immutable" / f"{index:03d}.input"
                )
                _atomic_write_bytes(controller_target, item["raw"], mode=0o400)
                original_provenance = item["provenance"].model_dump(mode="json")
                controller_materialized_task_inputs.append(
                    {
                        "input_id": item["input_id"],
                        "path": str(controller_target),
                        "provenance": original_provenance,
                    }
                )
                target = inputs_dir / "immutable" / f"{index:03d}.input"
                _, actor_raw = _actor_safe_input_envelope(
                    input_id=str(item["input_id"]),
                    raw=item["raw"],
                    original_provenance=original_provenance,
                    aliases=source_aliases,
                    source_roots=source_roots,
                )
                _atomic_write_bytes(target, actor_raw, mode=0o400)
                materialized_task_inputs.append(
                    {
                        "input_id": item["input_id"],
                        "path": str(target),
                        "provenance": {
                            "owner_repo": "abyss-stack",
                            "artifact_ref": str(target),
                            "source_ref": (
                                "actor-safe-derivative-of:"
                                + str(original_provenance["artifact_digest"])
                            ),
                            "artifact_digest": sha256_bytes(actor_raw),
                            "schema_ref": (
                                "schemas/external-codex-actor-input-envelope.schema.json"
                            ),
                            "schema_version": (
                                "abyss_stack_external_codex_actor_input_envelope_v1"
                            ),
                        },
                    }
                )
            nested_evidence_namespace_ref: dict[str, Any] | None = None
            nested_evidence_namespace: dict[str, Any] | None = None
            nested_evidence_mode = os.environ.get(
                NESTED_EVIDENCE_ENV,
                "on",
            ).strip().lower()
            if nested_evidence_mode not in {"on", "off"}:
                raise ExternalCodexRuntimeError(
                    "nested_evidence_configuration_invalid",
                    f"{NESTED_EVIDENCE_ENV} must be exactly on or off",
                )
            if (
                validated["task"]["execution_posture"] == "independent_review"
                and nested_evidence_mode == "on"
            ):
                try:
                    nested_evidence_namespace = build_nested_evidence_namespace(
                        review_task_id=str(validated["task"]["task_id"]),
                        review_task_digest=sha256_bytes(
                            validated["coordinates"]["task"][1]
                        ),
                        immutable_inputs=validated["immutable_inputs"],
                    )
                except NestedEvidenceNamespaceError as exc:
                    raise ExternalCodexRuntimeError(
                        "nested_evidence_namespace_unresolved",
                        "independent-review nested evidence did not close exactly: "
                        + str(exc),
                    ) from exc
                if nested_evidence_namespace is not None:
                    validate_json(
                        nested_evidence_namespace,
                        NESTED_EVIDENCE_NAMESPACE_SCHEMA_PATH,
                        label="nested evidence namespace",
                    )
                    nested_evidence_namespace_path = (
                        inputs_dir / "nested-evidence-namespace.json"
                    )
                    _atomic_write_json(
                        nested_evidence_namespace_path,
                        nested_evidence_namespace,
                        mode=0o400,
                    )
                    nested_evidence_namespace_ref = _artifact_ref(
                        nested_evidence_namespace_path,
                        owner="abyss-stack",
                    )
            projection = self._prepare_actor_projection(
                validated=validated,
                session_dir=session_dir,
            )
            failure_closeout = self._failure_closeout_context(
                binding=validated["binding"],
                task=validated["task"],
                materialized_inputs=materialized,
                session_dir=session_dir,
            )
            state = {
                "schema_version": STATE_SCHEMA_VERSION,
                "session_id": session_id,
                "launch_id": launch["launch_id"],
                "launch_digest": validated["launch_digest"],
                "status": "prepared",
                "admission_class": launch["admission_class"],
                "owner_admission_digest": (
                    validated["owner_admission"]["request_digest"]
                    if validated["owner_admission"] is not None
                    else None
                ),
                "incarnation_id": validated["binding"].incarnation_id,
                "task_id": validated["task"]["task_id"],
                "task_family": validated["task"]["task_family"],
                "execution_posture": validated["task"]["execution_posture"],
                "model_slug": validated["model_slug"],
                "reasoning_effort": validated["reasoning_effort"],
                "tool_profile_id": validated["binding"].tool_profile.profile_id,
                "workspace_path": str(validated["workspace"]),
                "workspace_expected_head": launch["workspace_expected_head"],
                "workspace_baseline": validated["baseline"],
                "workspace_manifest_baseline": validated["workspace_manifest_baseline"],
                "source_manifest_before_ref": projection["source_manifest_before_ref"],
                "source_manifest_after_ref": projection["source_manifest_after_ref"],
                "source_manifest_final_ref": None,
                "actor_projection_path": projection["actor_projection_path"],
                "actor_baseline_manifest_ref": projection[
                    "actor_baseline_manifest_ref"
                ],
                "actor_final_manifest_ref": None,
                "actor_delta_ref": None,
                "review_seed_envelope_ref": (
                    {
                        "owner_repo": "abyss-stack",
                        "artifact_ref": str(
                            launch["workspace_projection_seed"]["envelope_path"]
                        ),
                        "artifact_digest": str(
                            launch["workspace_projection_seed"]["envelope_digest"]
                        ),
                    }
                    if validated["review_seed"] is not None
                    else None
                ),
                "nested_evidence_namespace_ref": nested_evidence_namespace_ref,
                "materialized_inputs": materialized,
                "execution_result_schema_ref": _artifact_ref(
                    execution_result_schema_path,
                    owner="abyss-stack",
                ),
                "controller_materialized_task_inputs": (
                    controller_materialized_task_inputs
                ),
                "materialized_task_inputs": materialized_task_inputs,
                "failure_closeout": failure_closeout,
                "preflight": validated["preflight"],
                "created_at": iso_now(),
                "started_at": None,
                "finished_at": None,
                "thread_id": None,
                "attempts": [],
                "active_attempt_id": None,
                "worker_pid": None,
                "worker_start_ticks": None,
                "supervisor_pid": None,
                "supervisor_start_ticks": None,
                "codex_pid": None,
                "codex_start_ticks": None,
                "last_event_sequence": -1,
                "usage": {
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                },
                "usage_observation_gaps": [],
                "turn_count": 0,
                "output_bytes": 0,
                "active_wall_seconds": 0.0,
                "executed_commands": [],
                "changed_paths": [],
                "result_path": None,
                "result_digest": None,
                "wake_evaluation": None,
            }
            self._append_event(
                state,
                event_type="external_agent.prepared",
                payload={
                    "launch_digest": validated["launch_digest"],
                    "incarnation_id": validated["binding"].incarnation_id,
                    "nested_evidence_namespace_digest": (
                        nested_evidence_namespace_ref["artifact_digest"]
                        if nested_evidence_namespace_ref is not None
                        else None
                    ),
                },
                significance="progress",
            )
            self._save_state(state)
            self._spawn_worker(state, mode="start", resume_payload=None)
            return self._public_state(state)

    def _spawn_worker(
        self,
        state: dict[str, Any],
        *,
        mode: Literal["start", "resume"],
        resume_payload: Mapping[str, Any] | None,
    ) -> None:
        attempt_number = len(state["attempts"]) + 1
        attempt_id = f"{state['session_id']}:attempt:{attempt_number}"
        session_dir = self._session_dir(str(state["session_id"]))
        attempt_dir = session_dir / "attempts" / f"{attempt_number:03d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        if resume_payload is not None:
            _atomic_write_json(attempt_dir / "resume.json", resume_payload, mode=0o400)
        # The durable actor projection, not the owner source checkout, is the
        # active attempt's mutable coordination surface.  Source-path flocking
        # cannot defend against same-UID rename/replacement races.
        workspace_lock = self._acquire_workspace_attempt_lock(
            state["actor_projection_path"]
        )
        try:
            read_fd, write_fd = os.pipe()
        except BaseException:
            os.close(workspace_lock)
            raise
        try:
            pid = os.fork()
        except BaseException:
            os.close(read_fd)
            os.close(write_fd)
            os.close(workspace_lock)
            raise
        if pid == 0:  # pragma: no cover - exercised through subprocess-level tests
            try:
                os.close(write_fd)
                admitted = os.read(read_fd, 1)
                os.close(read_fd)
                if admitted != b"1":
                    os._exit(70)
                os.setsid()
                worker_log = (attempt_dir / "worker.log").open("ab", buffering=0)
                os.dup2(worker_log.fileno(), 1)
                os.dup2(worker_log.fileno(), 2)
                self._run_worker(
                    str(state["session_id"]),
                    attempt_id=attempt_id,
                    attempt_number=attempt_number,
                    mode=mode,
                    resume_payload=resume_payload,
                )
                os._exit(0)
            except BaseException as exc:
                try:
                    with self._lock(str(state["session_id"])):
                        failed_state = self._load_state(str(state["session_id"]))
                        self._worker_failure_locked(
                            failed_state,
                            attempt_id=attempt_id,
                            code=(
                                exc.code
                                if isinstance(exc, ExternalCodexRuntimeError)
                                else "unexpected_worker_failure"
                            ),
                            message=(
                                str(exc)
                                if isinstance(exc, ExternalCodexRuntimeError)
                                else f"worker raised {type(exc).__name__}"
                            ),
                        )
                except BaseException:
                    pass
                os._exit(70)
        os.close(read_fd)
        # The forked worker retains the inherited open-file description until
        # its complete attempt and terminal receipt are finished. The caller
        # must not keep the workspace occupied merely because start returned.
        os.close(workspace_lock)
        start_ticks = _process_start_ticks(pid)
        if start_ticks is None:
            os.close(write_fd)
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
            raise ExternalCodexRuntimeError(
                "worker_launch_failed", "cannot identify external-agent worker process"
            )
        attempt = {
            "attempt_id": attempt_id,
            "attempt_number": attempt_number,
            "mode": mode,
            "status": "starting",
            "worker_pid": pid,
            "worker_start_ticks": start_ticks,
            "supervisor_pid": None,
            "supervisor_start_ticks": None,
            "process_identity_ref": None,
            "codex_pid": None,
            "codex_start_ticks": None,
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
            "thread_id": state.get("thread_id"),
            "codex_argv": None,
            "execution_root": None,
            "output_bytes": 0,
            "active_wall_seconds": 0.0,
            "wall_time_accounted": False,
        }
        try:
            state["attempts"].append(attempt)
            state["active_attempt_id"] = attempt_id
            state["worker_pid"] = pid
            state["worker_start_ticks"] = start_ticks
            state["status"] = "running"
            if state["started_at"] is None:
                state["started_at"] = iso_now()
            # Persist the exact worker identity before the child can leave its
            # one-byte launch gate. A failed save therefore leaves the prior
            # prepared state retryable and emits no misleading start event.
            self._save_state(state)
            self._append_event(
                state,
                event_type=(
                    "external_agent.resume_started"
                    if mode == "resume"
                    else "external_agent.started"
                ),
                payload={
                    "worker_pid": pid,
                    "worker_start_ticks": start_ticks,
                    "mode": mode,
                },
                attempt_id=attempt_id,
                significance="progress",
            )
            self._save_state(state)
            os.write(write_fd, b"1")
        except BaseException:
            os.close(write_fd)
            if _pid_matches(pid, start_ticks):
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
            raise
        else:
            os.close(write_fd)

    def run_to_terminal(
        self,
        launch_path: str | Path,
        *,
        owner_request_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Keep the caller alive until the exact started session is terminal.

        This operation is the lifecycle-compatible entry point for transient
        cgroup launchers whose service ends by terminating all remaining child
        processes.  It adds observation cadence, not an execution deadline or
        resource budget; semantic terminal state remains owned by the runtime.
        """

        state = self.start(
            launch_path,
            owner_request_path=owner_request_path,
        )
        session_id = str(state["session_id"])
        while str(state["status"]) not in TERMINAL_STATES:
            time.sleep(FOREGROUND_OBSERVATION_INTERVAL_SECONDS)
            state = self.status(session_id)
        return state

    @staticmethod
    def _isolated_empty_directory(
        path: Path,
        *,
        error_code: str,
        purpose: str,
    ) -> Path:
        """Establish one runtime-owned non-writable empty directory."""

        try:
            path.mkdir(mode=0o500, parents=False, exist_ok=True)
            path_stat = path.lstat()
            if not stat.S_ISDIR(path_stat.st_mode) or path.is_symlink():
                raise OSError(f"isolated {purpose} is not a physical directory")
            if any(path.iterdir()):
                raise OSError(f"isolated {purpose} is not empty")
            path.chmod(0o500)
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                error_code,
                f"cannot establish the runtime-owned non-writable {purpose}",
            ) from exc
        return path

    def _codex_environment(
        self,
        launch: Mapping[str, Any],
        scratch_root: Path,
        tool_entry: Mapping[str, Any],
        *,
        repository_workspace: Path | None = None,
    ) -> dict[str, str]:
        environment: dict[str, str] = {}
        for key in launch.get("environment_allowlist", []):
            if SECRET_ENV_RE.search(str(key)):
                continue
            value = os.environ.get(str(key))
            if value is not None:
                environment[str(key)] = value
        environment["CODEX_HOME"] = str(launch["codex_home"])
        shell_home = ExternalCodexRuntime._isolated_empty_directory(
            scratch_root.parent / f"{scratch_root.name}-shell-home",
            error_code="isolated_shell_home_unavailable",
            purpose="shell HOME",
        )
        git_hooks_root = ExternalCodexRuntime._isolated_empty_directory(
            scratch_root.parent / f"{scratch_root.name}-git-hooks",
            error_code="isolated_git_hooks_unavailable",
            purpose="Git hooks directory",
        )
        repository_git_environment = _controller_git_environment(
            repository_workspace or Path(str(launch["workspace_path"]))
        )
        environment["HOME"] = str(shell_home)
        environment["PATH"] = CODEX_EXECUTABLE_PATH
        environment["BASH_ENV"] = "/dev/null"
        environment["ENV"] = "/dev/null"
        for key, value in repository_git_environment.items():
            if key.startswith("GIT_CONFIG_") or key in {
                "GIT_ATTR_NOSYSTEM",
                "GIT_NO_LAZY_FETCH",
                "GIT_OPTIONAL_LOCKS",
                "GIT_TERMINAL_PROMPT",
            }:
                environment[key] = value
        environment["GIT_CONFIG_VALUE_0"] = str(git_hooks_root)
        environment["GIT_PAGER"] = "cat"
        environment["GIT_TERMINAL_PROMPT"] = "0"
        environment["PAGER"] = "cat"
        environment["RIPGREP_CONFIG_PATH"] = "/dev/null"
        environment.setdefault("LANG", "C.UTF-8")
        environment["TMPDIR"] = str(scratch_root)
        environment["NO_COLOR"] = "1"
        if tool_entry.get("specialized_environment") is not None:
            specialized_environment, _ = _specialized_environment(
                self.profile,
                tool_entry,
            )
            environment.update(specialized_environment)
        return environment

    def _materialized_payloads(
        self, state: Mapping[str, Any]
    ) -> tuple[
        dict[str, Any],
        RunPlan,
        IncarnationBinding,
        dict[str, Any],
        dict[str, Any],
        bytes,
    ]:
        inputs = state["materialized_inputs"]
        launch_path = (
            self._session_dir(str(state["session_id"])) / "inputs" / "launch.json"
        )
        launch_raw = read_bounded(launch_path)
        if sha256_bytes(launch_raw) != state["launch_digest"]:
            raise ExternalCodexRuntimeError(
                "materialized_launch_drift", "durable launch bytes changed"
            )
        launch = load_json_bytes(launch_raw, label="materialized launch")
        payloads: dict[str, dict[str, Any]] = {}
        raws: dict[str, bytes] = {}
        for key, path_value in inputs.items():
            raw = read_bounded(
                Path(path_value),
                limit=MAX_ROLE_BYTES if key == "role_contract" else MAX_CONTROL_BYTES,
            )
            expected_digest = (
                state["owner_admission_digest"]
                if key == "owner_execution_request"
                else launch[key]["digest"]
            )
            if sha256_bytes(raw) != expected_digest:
                raise ExternalCodexRuntimeError(
                    "materialized_input_drift",
                    f"durable {key} bytes changed after admission",
                )
            raws[key] = raw
            payloads[key] = load_json_bytes(raw, label=f"materialized {key}")
        if raws["runtime_profile"] != self.profile_raw:
            raise ExternalCodexRuntimeError(
                "materialized_input_drift", "durable runtime profile bytes changed"
            )
        for item in state["materialized_task_inputs"]:
            raw = read_bounded(Path(item["path"]))
            if sha256_bytes(raw) != item["provenance"]["artifact_digest"]:
                raise ExternalCodexRuntimeError(
                    "materialized_input_drift",
                    f"durable immutable input changed: {item['input_id']}",
                )
        for item in state.get("controller_materialized_task_inputs", []):
            raw = read_bounded(Path(item["path"]))
            if sha256_bytes(raw) != item["provenance"]["artifact_digest"]:
                raise ExternalCodexRuntimeError(
                    "materialized_input_drift",
                    f"durable controller input changed: {item['input_id']}",
                )
        plan = RunPlan.model_validate(payloads["plan"])
        binding = parse_incarnation_binding(payloads["incarnation_binding"])
        task = payloads["task"]
        realization = payloads["model_realization"]
        assert_agent_incarnation_binding_matches_plan(binding, plan)
        return launch, plan, binding, task, realization, raws["role_contract"]

    def _materialized_task_input(
        self,
        state: Mapping[str, Any],
        input_id: str,
    ) -> tuple[Path, bytes, ProvenanceRef]:
        controller_inputs = state.get(
            "controller_materialized_task_inputs",
            state["materialized_task_inputs"],
        )
        matches = [item for item in controller_inputs if item["input_id"] == input_id]
        if len(matches) != 1:
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                f"runtime has no unique immutable {input_id} input",
            )
        item = matches[0]
        path = Path(str(item["path"]))
        immutable_root = (
            self._session_dir(str(state["session_id"]))
            / "inputs"
            / (
                "controller-immutable"
                if state.get("controller_materialized_task_inputs") is not None
                else "immutable"
            )
        ).resolve()
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(immutable_root)
        except (OSError, ValueError) as exc:
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                f"immutable {input_id} is absent or outside the session input root",
            ) from exc
        if (
            not path.is_absolute()
            or resolved != path
            or path.is_symlink()
            or not path.is_file()
        ):
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                f"immutable {input_id} is not one exact regular session input",
            )
        provenance = ProvenanceRef.model_validate(item["provenance"])
        raw = read_bounded(path)
        if sha256_bytes(raw) != provenance.artifact_digest:
            raise ExternalCodexRuntimeError(
                "materialized_input_drift",
                f"durable immutable input changed: {input_id}",
            )
        return path, raw, provenance

    def _validated_a2a_summon_request(
        self,
        *,
        state: Mapping[str, Any],
        plan: RunPlan,
        binding: IncarnationBinding,
        task: Mapping[str, Any],
        request_input_id: str,
        supplied_path: str | Path | None = None,
        schema_material: tuple[Path, bytes, ProvenanceRef] | None = None,
    ) -> tuple[dict[str, Any], ProvenanceRef, ProvenanceRef, tuple[str, ...]]:
        """Validate one materialized SDK v4 request and its active plan binding."""

        request_path, request_raw, request_ref = self._materialized_task_input(
            state,
            request_input_id,
        )
        if schema_material is None:
            schema_path, schema_raw, schema_ref = self._materialized_task_input(
                state,
                "summon-request-schema",
            )
        else:
            schema_path, schema_raw, schema_ref = schema_material
        if (
            not schema_path.is_absolute()
            or schema_path.is_symlink()
            or not schema_path.is_file()
            or read_bounded(schema_path) != schema_raw
            or sha256_bytes(schema_raw) != schema_ref.artifact_digest
        ):
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                "summon request schema material is unavailable or changed",
            )
        if supplied_path is not None:
            supplied = Path(supplied_path)
            if (
                not supplied.is_absolute()
                or supplied.is_symlink()
                or not supplied.is_file()
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_summon_request_unbound",
                    "supplied summon request must be one absolute regular file",
                )
            supplied_raw = read_bounded(supplied)
            if (
                supplied_raw != request_raw
                or sha256_bytes(supplied_raw) != request_ref.artifact_digest
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_summon_request_unbound",
                    "supplied summon request differs from the writer's admitted bytes",
                )
        try:
            request = load_json_bytes(request_raw, label="canonical summon request")
            schema = load_json_bytes(
                schema_raw, label="canonical summon request schema"
            )
            validate_json(
                request,
                schema_path,
                label="canonical SDK summon request",
            )
        except ExternalCodexRuntimeError as exc:
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_invalid",
                f"canonical SDK summon request/schema is invalid: {exc}",
            ) from exc
        if (
            schema.get("$id") != SDK_SUMMON_REQUEST_SCHEMA_VERSION
            or schema_ref.owner_repo != "aoa-sdk"
            or schema_ref.artifact_ref != SDK_SUMMON_REQUEST_SCHEMA_REF
            or schema_ref.schema_version != SDK_SUMMON_REQUEST_SCHEMA_VERSION
            or request_ref.schema_ref != schema_ref.artifact_ref
            or request_ref.schema_version != SDK_SUMMON_REQUEST_SCHEMA_VERSION
        ):
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                "summon request provenance does not bind the exact aoa-sdk v4 schema",
            )
        if (
            not _plan_binds_active_summon_request(plan, request_ref)
            or binding.task_request_ref != request_ref
            or request_ref not in plan.snapshot.source_refs
        ):
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                "run plan/incarnation does not bind the exact active summon request",
            )
        nested = request.get("summon_request")
        passport = request.get("quest_passport")
        top_outputs = request.get("expected_outputs")
        allowed_transport_preferences = (
            {"a2a_remote", "either"}
            if state.get("admission_class") == "owner_contour"
            else {"codex_local"}
        )
        if (
            not isinstance(nested, dict)
            or not isinstance(passport, dict)
            or not isinstance(top_outputs, list)
            or not top_outputs
            or any(not isinstance(item, str) or not item for item in top_outputs)
            or len(set(top_outputs)) != len(top_outputs)
            or nested.get("expected_outputs") != top_outputs
            or passport.get("expected_artifacts") != top_outputs
            or passport.get("control_mode") != "codex_supervised"
            or passport.get("self_agent") is not False
            or not isinstance(passport.get("route_anchor"), str)
            or not passport["route_anchor"]
            or nested.get("desired_role") != binding.role_id
            or nested.get("child_agent_id") != binding.incarnation_id
            or nested.get("parent_task_id") != task["parent_task_id"]
            or nested.get("session_ref") != state["session_id"]
            or nested.get("review_required") is not task["review_required"]
            or nested.get("transport_preference") not in allowed_transport_preferences
            or nested.get("require_progression") is not False
            or nested.get("workspace_root") != state["workspace_path"]
            or request.get("reviewed_artifact_path")
            != nested.get("reviewed_artifact_path")
        ):
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                "summon request semantics differ from the exact task/incarnation",
            )
        plan_capabilities = {
            item.capability_id for item in plan.scenario_binding.capability_refs
        }
        request_capabilities = nested.get("capability_refs")
        if (
            not isinstance(request_capabilities, list)
            or not request_capabilities
            or any(item not in plan_capabilities for item in request_capabilities)
        ):
            raise ExternalCodexRuntimeError(
                "a2a_summon_request_unbound",
                "summon request capabilities are not bound by the run plan",
            )
        return request, request_ref, schema_ref, tuple(top_outputs)

    def _execution_result_schema_path(self, state: Mapping[str, Any]) -> Path:
        """Return the untampered session-local schema, with legacy fallback."""

        reference = state.get("execution_result_schema_ref")
        if reference is None:
            return Path(str(state["materialized_inputs"]["result_schema"]))
        expected_path = (
            self._session_dir(str(state["session_id"]))
            / "inputs"
            / "execution-result-schema.json"
        )
        candidate = Path(str(reference.get("artifact_ref", "")))
        if (
            candidate != expected_path
            or candidate.is_symlink()
            or not candidate.is_file()
        ):
            raise ExternalCodexRuntimeError(
                "execution_result_schema_drift",
                "session-local result schema is absent or outside runtime inputs",
            )
        raw = read_bounded(candidate)
        if sha256_bytes(raw) != reference.get("artifact_digest"):
            raise ExternalCodexRuntimeError(
                "execution_result_schema_drift",
                "session-local result schema digest drifted",
            )
        actual = load_json_bytes(raw, label="session-local result schema")
        canonical = load_json(
            Path(str(state["materialized_inputs"]["result_schema"])),
            label="materialized canonical result schema",
        )
        expected = specialize_report_schema(
            canonical,
            task_id=str(state["task_id"]),
            incarnation_id=str(state["incarnation_id"]),
            immutable_input_ids=tuple(
                str(item["input_id"]) for item in state["materialized_task_inputs"]
            ),
        )
        if actual != expected:
            raise ExternalCodexRuntimeError(
                "execution_result_schema_drift",
                "session-local result schema differs from exact runtime identity",
            )
        return candidate

    def _ensure_execution_result_schema_locked(self, state: dict[str, Any]) -> Path:
        """Materialize exact identity constraints for a legacy resumable session."""

        if state.get("execution_result_schema_ref") is not None:
            return self._execution_result_schema_path(state)
        canonical = load_json(
            Path(str(state["materialized_inputs"]["result_schema"])),
            label="materialized canonical result schema",
        )
        specialized = specialize_report_schema(
            canonical,
            task_id=str(state["task_id"]),
            incarnation_id=str(state["incarnation_id"]),
            immutable_input_ids=tuple(
                str(item["input_id"]) for item in state["materialized_task_inputs"]
            ),
        )
        path = (
            self._session_dir(str(state["session_id"]))
            / "inputs"
            / "execution-result-schema.json"
        )
        _atomic_write_json(path, specialized, mode=0o400)
        state["execution_result_schema_ref"] = _artifact_ref(
            path,
            owner="abyss-stack",
        )
        return path

    def _materialize_resume_evidence_locked(
        self,
        state: dict[str, Any],
        resume: Mapping[str, Any],
        *,
        attempt_id: str,
    ) -> tuple[dict[str, Any], ...]:
        """Bind caller-supplied continuation bytes as immutable actor evidence."""

        supplied = resume.get("evidence_inputs")
        if supplied is None:
            return ()
        if not isinstance(supplied, list) or not supplied:
            raise ExternalCodexRuntimeError(
                "resume_evidence_invalid",
                "resume evidence must be one non-empty schema-validated list",
            )
        actor_inputs = list(state["materialized_task_inputs"])
        controller_inputs = list(
            state.get("controller_materialized_task_inputs", actor_inputs)
        )
        actor_by_id = {str(item["input_id"]): item for item in actor_inputs}
        controller_by_id = {str(item["input_id"]): item for item in controller_inputs}
        if set(actor_by_id) != set(controller_by_id):
            raise ExternalCodexRuntimeError(
                "resume_evidence_state_invalid",
                "actor and controller immutable input identities differ",
            )
        session_dir = self._session_dir(str(state["session_id"]))
        inputs_dir = session_dir / "inputs"
        alias_view = {
            "launch": {"workspace_path": str(state["workspace_path"])},
            "workspace": Path(str(state["workspace_path"])),
            "workspace_manifest_baseline": state["workspace_manifest_baseline"],
        }
        aliases = _actor_source_aliases(alias_view)
        source_roots = frozenset(
            value
            for value in (
                str(state["workspace_path"]),
                str(state["workspace_manifest_baseline"].get("workspace_path", "")),
            )
            if value
        )
        prepared: list[dict[str, Any]] = []
        request_ids: set[str] = set()
        new_input_count = 0
        for item in supplied:
            input_id = str(item["input_id"])
            if input_id in request_ids:
                raise ExternalCodexRuntimeError(
                    "resume_evidence_duplicate",
                    f"resume evidence input is duplicated: {input_id}",
                )
            request_ids.add(input_id)
            raw = str(item["utf8_content"]).encode("utf-8")
            provenance = dict(item["provenance"])
            if sha256_bytes(raw) != provenance["artifact_digest"]:
                raise ExternalCodexRuntimeError(
                    "resume_evidence_digest_mismatch",
                    f"resume evidence differs from its exact digest: {input_id}",
                )
            existing_actor = actor_by_id.get(input_id)
            existing_controller = controller_by_id.get(input_id)
            if existing_actor is not None or existing_controller is not None:
                if existing_actor is None or existing_controller is None:
                    raise ExternalCodexRuntimeError(
                        "resume_evidence_state_invalid",
                        f"resume evidence identity is only partly materialized: {input_id}",
                    )
                controller_path = Path(str(existing_controller["path"]))
                if (
                    existing_controller["provenance"] != provenance
                    or controller_path.is_symlink()
                    or not controller_path.is_file()
                    or sha256_file(controller_path) != provenance["artifact_digest"]
                ):
                    raise ExternalCodexRuntimeError(
                        "resume_evidence_identity_conflict",
                        f"resume evidence identity is already bound to other bytes: {input_id}",
                    )
                prepared.append({"existing_actor": existing_actor})
                continue
            new_input_count += 1
            ordinal = len(actor_inputs) + new_input_count
            controller_target = (
                inputs_dir / "controller-immutable" / f"{ordinal:03d}.input"
            )
            actor_target = inputs_dir / "immutable" / f"{ordinal:03d}.input"
            if controller_target.exists() or actor_target.exists():
                raise ExternalCodexRuntimeError(
                    "resume_evidence_target_occupied",
                    "next immutable input coordinate is already occupied",
                )
            _, actor_raw = _actor_safe_input_envelope(
                input_id=input_id,
                raw=raw,
                original_provenance=provenance,
                aliases=aliases,
                source_roots=source_roots,
            )
            prepared.append(
                {
                    "input_id": input_id,
                    "raw": raw,
                    "provenance": provenance,
                    "controller_target": controller_target,
                    "actor_target": actor_target,
                    "actor_raw": actor_raw,
                }
            )
        materialized: list[dict[str, Any]] = []
        for candidate in prepared:
            existing_actor = candidate.get("existing_actor")
            if isinstance(existing_actor, dict):
                materialized.append(existing_actor)
                continue
            input_id = str(candidate["input_id"])
            raw = bytes(candidate["raw"])
            provenance = dict(candidate["provenance"])
            controller_target = Path(candidate["controller_target"])
            actor_target = Path(candidate["actor_target"])
            actor_raw = bytes(candidate["actor_raw"])
            _atomic_write_bytes(controller_target, raw, mode=0o400)
            _atomic_write_bytes(actor_target, actor_raw, mode=0o400)
            controller_item = {
                "input_id": input_id,
                "path": str(controller_target),
                "provenance": provenance,
            }
            actor_item = {
                "input_id": input_id,
                "path": str(actor_target),
                "provenance": {
                    "owner_repo": "abyss-stack",
                    "artifact_ref": str(actor_target),
                    "source_ref": (
                        "actor-safe-derivative-of:" + str(provenance["artifact_digest"])
                    ),
                    "artifact_digest": sha256_bytes(actor_raw),
                    "schema_ref": (
                        "schemas/external-codex-actor-input-envelope.schema.json"
                    ),
                    "schema_version": (
                        "abyss_stack_external_codex_actor_input_envelope_v1"
                    ),
                },
            }
            controller_inputs.append(controller_item)
            actor_inputs.append(actor_item)
            controller_by_id[input_id] = controller_item
            actor_by_id[input_id] = actor_item
            materialized.append(actor_item)
        state["controller_materialized_task_inputs"] = controller_inputs
        state["materialized_task_inputs"] = actor_inputs
        canonical = load_json(
            Path(str(state["materialized_inputs"]["result_schema"])),
            label="materialized canonical result schema",
        )
        specialized = specialize_report_schema(
            canonical,
            task_id=str(state["task_id"]),
            incarnation_id=str(state["incarnation_id"]),
            immutable_input_ids=tuple(str(item["input_id"]) for item in actor_inputs),
        )
        schema_path = inputs_dir / "execution-result-schema.json"
        _atomic_write_json(schema_path, specialized, mode=0o400)
        state["execution_result_schema_ref"] = _artifact_ref(
            schema_path,
            owner="abyss-stack",
        )
        self._append_event(
            state,
            event_type="external_agent.resume_evidence_materialized",
            payload={
                "evidence_inputs": [
                    {
                        "input_id": str(item["input_id"]),
                        "source_artifact_digest": str(
                            controller_by_id[str(item["input_id"])]["provenance"][
                                "artifact_digest"
                            ]
                        ),
                        "actor_input_ref": {
                            "artifact_digest": str(
                                actor_by_id[str(item["input_id"])]["provenance"][
                                    "artifact_digest"
                                ]
                            ),
                            "artifact_ref": str(
                                actor_by_id[str(item["input_id"])]["path"]
                            ),
                        },
                    }
                    for item in supplied
                ],
                "resume_reason": str(resume["reason"]),
            },
            attempt_id=attempt_id,
            thread_id=str(state["thread_id"]),
            significance="review",
        )
        return tuple(materialized)

    def _preserved_result_refs(self, state: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Return exact prior terminal results retained across explicit resume."""

        session_dir = self._session_dir(str(state["session_id"]))
        references: list[dict[str, Any]] = []
        for attempt in state.get("attempts", []):
            attempt_number = attempt.get("attempt_number")
            if not isinstance(attempt_number, int):
                continue
            attempt_dir = session_dir / "attempts" / f"{attempt_number:03d}"
            result_paths = [attempt_dir / "runtime-result.json"]
            result_paths.extend(
                sorted(attempt_dir.glob("runtime-result-revision-*.json"))
            )
            for path in result_paths:
                if path.is_file() and not path.is_symlink():
                    references.append(_artifact_ref(path))
                closure_path = path.with_name(f"{path.stem}-evidence-closure.json")
                if closure_path.is_file() and not closure_path.is_symlink():
                    references.append(_artifact_ref(closure_path))
        return references

    def _preserve_result_evidence_closure_locked(
        self,
        *,
        previous_result: Mapping[str, Any],
        preserved_result_ref: Mapping[str, Any],
        preserved_result_path: Path,
    ) -> dict[str, str]:
        """Retain every evidence byte needed to verify one resumed result."""

        evidence = previous_result.get("evidence_refs")
        if not isinstance(evidence, list):
            raise ExternalCodexRuntimeError(
                "runtime_result_evidence_invalid",
                "prior runtime result has no evidence reference collection",
            )
        snapshot_dir = preserved_result_path.with_name(
            f"{preserved_result_path.stem}-evidence"
        )
        preserved_evidence: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for index, source_ref in enumerate(evidence):
            if not isinstance(source_ref, Mapping):
                raise ExternalCodexRuntimeError(
                    "runtime_result_evidence_invalid",
                    "prior runtime result contains a malformed evidence reference",
                )
            identity = (
                str(source_ref.get("owner_repo", "")),
                str(source_ref.get("artifact_ref", "")),
                str(source_ref.get("artifact_digest", "")),
            )
            if identity in seen:
                continue
            seen.add(identity)
            snapshot_ref = _snapshot_artifact_ref(
                source_ref,
                snapshot_dir / f"artifact-{index:03d}",
            )
            preserved_evidence.append(
                {
                    "source_ref": dict(source_ref),
                    "snapshot_ref": snapshot_ref,
                }
            )
        closure = {
            "schema_version": "abyss_stack_external_codex_result_evidence_closure_v1",
            "source_result_ref": dict(preserved_result_ref),
            "preserved_evidence": preserved_evidence,
        }
        validate_json(
            closure,
            RESULT_EVIDENCE_CLOSURE_SCHEMA_PATH,
            label="prior runtime result evidence closure",
        )
        closure_path = preserved_result_path.with_name(
            f"{preserved_result_path.stem}-evidence-closure.json"
        )
        _atomic_write_json(closure_path, closure, mode=0o400)
        return _artifact_ref(closure_path)

    def _preserve_terminal_result_locked(
        self,
        state: Mapping[str, Any],
        result: Mapping[str, Any],
        result_path: Path,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Freeze a terminal result and its evidence before later resume pressure."""

        attempt = state["attempts"][-1]
        attempt_dir = (
            self._session_dir(str(state["session_id"]))
            / "attempts"
            / f"{int(attempt['attempt_number']):03d}"
        )
        raw_result = read_bounded(result_path)
        result_digest = sha256_bytes(raw_result)
        preserved_path = attempt_dir / "runtime-result.json"
        if preserved_path.exists() and (
            preserved_path.is_symlink() or not preserved_path.is_file()
        ):
            raise ExternalCodexRuntimeError(
                "runtime_result_evidence_closure_drift",
                "preserved terminal result coordinate is not a regular file",
            )
        if preserved_path.is_file() and sha256_file(preserved_path) != result_digest:
            revision = 2
            while True:
                candidate = attempt_dir / f"runtime-result-revision-{revision:03d}.json"
                if candidate.exists() and (
                    candidate.is_symlink() or not candidate.is_file()
                ):
                    raise ExternalCodexRuntimeError(
                        "runtime_result_evidence_closure_drift",
                        "preserved terminal result revision is not a regular file",
                    )
                if not candidate.exists() or (
                    candidate.is_file() and sha256_file(candidate) == result_digest
                ):
                    preserved_path = candidate
                    break
                revision += 1
        if not preserved_path.exists():
            _atomic_write_bytes(preserved_path, raw_result, mode=0o400)
        preserved_ref = _artifact_ref(preserved_path)
        closure_ref = self._verified_preserved_result_closure_ref_locked(
            previous_result=result,
            preserved_result_ref=preserved_ref,
            preserved_result_path=preserved_path,
        )
        return preserved_ref, closure_ref

    def _verified_preserved_result_closure_ref_locked(
        self,
        *,
        previous_result: Mapping[str, Any],
        preserved_result_ref: Mapping[str, Any],
        preserved_result_path: Path,
    ) -> dict[str, str]:
        """Verify the pre-resume snapshot closure for one terminal result."""

        closure_path = preserved_result_path.with_name(
            f"{preserved_result_path.stem}-evidence-closure.json"
        )
        if not closure_path.is_file() or closure_path.is_symlink():
            return self._preserve_result_evidence_closure_locked(
                previous_result=previous_result,
                preserved_result_ref=preserved_result_ref,
                preserved_result_path=preserved_result_path,
            )
        closure = load_json(
            closure_path,
            label="preserved prior runtime result evidence closure",
        )
        validate_json(
            closure,
            RESULT_EVIDENCE_CLOSURE_SCHEMA_PATH,
            label="preserved prior runtime result evidence closure",
        )
        if closure["source_result_ref"] != dict(preserved_result_ref):
            raise ExternalCodexRuntimeError(
                "runtime_result_evidence_closure_drift",
                "preserved evidence closure names another runtime result",
            )
        expected_sources: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for source_ref in previous_result["evidence_refs"]:
            identity = (
                str(source_ref["owner_repo"]),
                str(source_ref["artifact_ref"]),
                str(source_ref["artifact_digest"]),
            )
            if identity in seen:
                continue
            seen.add(identity)
            expected_sources.append(dict(source_ref))
        preserved_evidence = closure["preserved_evidence"]
        if [item["source_ref"] for item in preserved_evidence] != expected_sources:
            raise ExternalCodexRuntimeError(
                "runtime_result_evidence_closure_drift",
                "preserved evidence closure does not cover the exact result evidence",
            )
        for item in preserved_evidence:
            snapshot_path = _verified_artifact_ref_path(
                item["snapshot_ref"],
                label="preserved prior runtime result evidence snapshot",
            )
            if sha256_file(snapshot_path) != item["source_ref"]["artifact_digest"]:
                raise ExternalCodexRuntimeError(
                    "runtime_result_evidence_closure_drift",
                    "preserved evidence snapshot differs from its original digest",
                )
        return _artifact_ref(closure_path)

    def _owner_admission_ref(self, state: Mapping[str, Any]) -> dict[str, Any] | None:
        path_value = state["materialized_inputs"].get("owner_execution_request")
        if path_value is None:
            return None
        path = Path(str(path_value))
        reference = _artifact_ref(path, owner="aoa-agents")
        if reference["artifact_digest"] != state.get("owner_admission_digest"):
            raise ExternalCodexRuntimeError(
                "materialized_input_drift",
                "durable owner execution request changed after admission",
            )
        return reference

    def _attempt_has_completed_usage_event(
        self,
        state: Mapping[str, Any],
        attempt_id: str,
    ) -> bool:
        """Return whether Codex exposed terminal usage for one exact attempt."""

        path = self._events_path(str(state["session_id"]))
        if not path.is_file():
            return False
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if (
                event.get("attempt_id") == attempt_id
                and event.get("event_type") == "codex.turn.completed"
            ):
                return True
        return False

    def _record_interrupted_usage_gap_locked(
        self,
        state: dict[str, Any],
        attempt_id: str,
    ) -> None:
        """Record that a controlled interrupt precluded exact token observation."""

        gaps = state.setdefault("usage_observation_gaps", [])
        if any(item.get("attempt_id") == attempt_id for item in gaps):
            return
        if self._attempt_has_completed_usage_event(state, attempt_id):
            return
        reason = "controlled_interruption_before_turn_usage"
        event = self._append_event(
            state,
            event_type="external_agent.usage_observation_gap_recorded",
            payload={"attempt_id": attempt_id, "reason": reason},
            attempt_id=attempt_id,
            significance="terminal",
        )
        gaps.append(
            {
                "attempt_id": attempt_id,
                "reason": reason,
                "event_sequence": event["sequence"],
            }
        )

    @staticmethod
    def _usage_observation(state: Mapping[str, Any]) -> dict[str, Any]:
        gaps = [dict(item) for item in state.get("usage_observation_gaps", [])]
        return {
            "status": "partial" if gaps else "complete",
            "gap_reasons": gaps,
        }

    def _render_prompt(
        self,
        *,
        state: Mapping[str, Any],
        launch: Mapping[str, Any],
        binding: IncarnationBinding,
        task: Mapping[str, Any],
        role_raw: bytes,
        execution_root: Path,
        resume_payload: Mapping[str, Any] | None,
    ) -> str:
        actor_workspace = self._projection_path_from_state(state)
        source_path = str(state["workspace_path"])
        projection_path = str(execution_root)
        source_paths = _actor_source_aliases(
            {
                "launch": launch,
                "workspace": source_path,
                "workspace_manifest_baseline": state["workspace_manifest_baseline"],
            }
        )
        source_roots = tuple(
            value
            for value in dict.fromkeys(
                (
                    str(launch["workspace_path"]),
                    source_path,
                    str(state["workspace_manifest_baseline"].get("workspace_path", "")),
                )
            )
            if value
        )

        def project_source_paths(value: Any) -> Any:
            projected = value
            for candidate in source_paths:
                if candidate:
                    projected = _replace_prompt_source_path(
                        projected,
                        source_path=candidate,
                        projection_path=projection_path,
                    )
            return projected

        def assert_control_view_is_source_free(value: Any) -> None:
            if any(
                _contains_source_path(value, candidate) for candidate in source_paths
            ):
                raise ExternalCodexRuntimeError(
                    "actor_source_path_exposed",
                    "model-facing control data retained a source coordinate",
                )

        role_text = project_source_paths(role_raw.decode("utf-8", errors="replace"))
        continuation = project_source_paths(
            binding.continuation.model_dump(mode="json")
        )
        immutable_inputs = state["materialized_task_inputs"]
        nested_evidence_namespace = _load_nested_evidence_namespace(state)
        # The owner task remains durable and exact on disk, but its source-side
        # local_path hints are not actor coordinates.  Give the model a
        # projection-safe task view whose immutable inputs point only at the
        # runtime materialization under the session directory.
        prompt_task = project_source_paths(json.loads(json.dumps(task)))
        assert_control_view_is_source_free(prompt_task)
        materialized_by_id = {
            str(item["input_id"]): str(item["path"]) for item in immutable_inputs
        }
        for item in prompt_task.get("immutable_inputs", []):
            input_id = str(item.get("input_id", ""))
            if input_id in materialized_by_id:
                item["local_path"] = materialized_by_id[input_id]
        prompt_validation_commands = [
            project_source_paths(item) for item in task["validation_commands"]
        ]
        resume_prompt_payload = (
            json.loads(json.dumps(resume_payload))
            if resume_payload is not None
            else None
        )
        if isinstance(resume_prompt_payload, dict) and isinstance(
            resume_prompt_payload.get("evidence_inputs"), list
        ):
            resume_prompt_payload["evidence_inputs"] = [
                {
                    "input_id": str(item["input_id"]),
                    "provenance": item["provenance"],
                    "materialized_as": f"immutable:{item['input_id']}",
                }
                for item in resume_prompt_payload["evidence_inputs"]
            ]
        projected_resume_payload = (
            project_source_paths(resume_prompt_payload)
            if resume_prompt_payload is not None
            else None
        )
        for control_view in (
            role_text,
            continuation,
            prompt_validation_commands,
            projected_resume_payload,
            nested_evidence_namespace,
        ):
            assert_control_view_is_source_free(control_view)
        validation_execution_protocol = [
            {
                "command_id": item["command_id"],
                "task_argv": item["argv"],
                "task_cwd": item["cwd"],
                "execution_argv": list(
                    _replace_prompt_source_path(
                        _validation_wrapper_argv(actor_workspace, item),
                        source_path=str(actor_workspace),
                        projection_path=str(execution_root),
                    )
                ),
            }
            for item in prompt_validation_commands
        ]
        resume_block = (
            "\nResume instruction:\n"
            + json.dumps(
                projected_resume_payload,
                ensure_ascii=False,
                indent=2,
            )
            if resume_payload is not None
            else ""
        )
        nested_evidence_block = (
            "\nRuntime-owned nested evidence namespace (a subordinate exact "
            "transport derivative, never owner truth):\n"
            "<nested_evidence_namespace>\n"
            + json.dumps(
                nested_evidence_namespace,
                ensure_ascii=False,
                indent=2,
            )
            + "\n</nested_evidence_namespace>\n"
            if nested_evidence_namespace is not None
            else ""
        )
        workspace_projection = {
            "target_workspace": str(execution_root),
            "codex_execution_root": str(execution_root),
            "target_workspace_access": binding.permission_posture.sandbox_mode,
            "projection_kind": "runtime_owned_actor_workspace",
            "source_workspace_path": None,
        }
        prompt = f"""You are one external Codex process carrying a bounded AoA role incarnation.

This is not a built-in Codex subagent workflow. Do not delegate, spawn subagents,
or widen the task. The user remains the only human authority. Read the repository
AGENTS.md hierarchy, but treat this exact task packet, permission ceiling, and
continuation obligation as the controlling bounded obligation.

Role source (exact delivered bytes):
<role_contract>
{role_text}
</role_contract>

Task packet:
<task>
{json.dumps(prompt_task, ensure_ascii=False, indent=2)}
</task>

Continuation obligation:
<continuation>
{json.dumps(continuation, ensure_ascii=False, indent=2)}
</continuation>

Runtime-materialized immutable inputs (read these paths, not mutable aliases):
<immutable_inputs>
{json.dumps(immutable_inputs, ensure_ascii=False, indent=2)}
</immutable_inputs>
{nested_evidence_block}

Runtime-owned actor workspace projection (the only mutable repository view):
<workspace_projection>
{json.dumps(workspace_projection, ensure_ascii=False, indent=2)}
</workspace_projection>

Fixed validation execution protocol:
<validation_execution_protocol>
{json.dumps(validation_execution_protocol, ensure_ascii=False, indent=2)}
</validation_execution_protocol>
{resume_block}

Hard stop-lines:
- Keep the task inside the named actor projection and authority scope. For repo-mutation
  work, mutate only allowed_paths; for read-only work, mutate nothing.
- Treat target_workspace above as the only repository under study. It is a
  runtime-owned projection with a private, read-only Git body that reproduces
  the admitted baseline without retaining the owner checkout coordinate. Bind
  every exploration and validation command to that projection; never cite or
  return controller, source-checkout, or execution-root bytes as workspace
  evidence.
- Anchored source: refs may name only source_evidence_paths. When that optional
  field is absent, allowed_paths is the backward-compatible evidence scope.
- Run every fixed validation through its exact execution_argv above. This
  wrapper binds the task argv to an explicit workspace cwd. A plain argv,
  shell cd, alternate wrapper, or skipped claim is not admitted as execution.
  Report the observed final exit status.
  Each validation_claims evidence_ref must be exactly
  runtime:validation:<command_id>; the runtime binds it to observed argv/status.
- Every transition or finding evidence ref must be an anchored
  source:<workspace-relative-path>#<line-or-symbol>, an anchored
  immutable:<input_id>#<line-or-symbol>, the reserved post-exit
  runtime:workspace-final-manifest#<line-or-symbol> ref, or an exact
  runtime:nested-evidence-namespace#<entry-id> ref. Use the stable input_id
  shown in immutable_inputs, never its ordinal materialized filename or absolute
  path. A line anchor is spelled exactly L<number> or L<number>-L<number>
  (for example #L35 or #L35-L38). A bare numeric anchor such as #35 is treated
  as a literal symbol, not a line, and fails unless those exact bytes occur in
  the source. Use the reserved runtime ref for claims about final workspace state; the
  controller binds it after the model exits. Emit each exact evidence ref only
  once per transition or finding; exact repetitions are semantically redundant.
- When nested_evidence_namespace is present, it proves only the transport
  closure of historical refs through exact producer task/result/report/delta,
  digests, manifests, and anchored excerpts. Independently judge the claim.
  Do not report a mapped alias or source-coordinate change as an evidence defect;
  cite the exact namespace entry for that closure. A same-name digest collision
  is a warning against name-only resolution, not evidence for the wrong input.
- artifact_paths must be empty for read-only work. For repo-mutation work they
  may contain only regular, non-symlink files inside allowed_paths that this
  attempt actually changed relative to the immutable baseline.
- Do not commit, push, create or merge a PR, tag, release, publish, mutate a
  service, inspect secrets, or change global configuration.
- When task.review_required is true, do not return status=completed; preserve
  the independent-review gate with review_required, authority_blocked, or failed.
- A non-review actor that reaches its review gate uses
  review_required/submit_for_review. An independent-review actor uses
  completed/proceed when no blocker remains or
  review_required/return_for_repair when one is confirmed. Any other terminal
  execution failure uses failed/stop; return_for_repair is not a generic retry
  request.
- Do not claim owner acceptance, proof verdict, landing completion, or model fit.
- If owner meaning, architecture, scope, authority, rollback, or safety is
  ambiguous, return authority_blocked or review_required instead of guessing.
- Return one JSON object matching the supplied output schema. Identity fields
  must be task_id={task["task_id"]!r} and incarnation_id={binding.incarnation_id!r}.

Runtime session identity: {state["session_id"]}
"""
        if any(
            _contains_source_path(prompt, candidate)
            for candidate in source_roots
            if candidate
        ):
            raise ExternalCodexRuntimeError(
                "actor_source_path_exposed",
                "source workspace absolute path would be exposed to the actor",
            )
        return prompt

    def _codex_command(
        self,
        *,
        launch: Mapping[str, Any],
        realization: Mapping[str, Any],
        tool_entry: Mapping[str, Any],
        execution_root: Path,
        output_schema: Path,
        output_message: Path,
        mode: Literal["start", "resume"],
        thread_id: str | None,
        mcp_endpoint_overrides: Mapping[str, str] | None = None,
        actor_git_mask: Mapping[str, Any] | None = None,
        sanitized_config_path: Path | None = None,
        readable_paths: Sequence[Path] = (),
        writable_paths: Sequence[Path] = (),
        denied_paths: Sequence[Path] = (),
        workspace_access: Literal["read", "write"] = "write",
        shell_environment: Mapping[str, str] | None = None,
    ) -> list[str]:
        executable = str(launch["codex_executable"])
        configuration = realization["configuration"]
        model_slug = str(configuration["runtime"]["model_slug"])
        effort = str(configuration["reasoning_effort"])
        base = [
            executable,
            "-a",
            "never",
        ]
        if tool_entry["codex_sandbox"] != "workspace-write":
            raise ExternalCodexRuntimeError(
                "codex_permission_profile_invalid",
                "external actor runtime requires the workspace-derived Codex profile",
            )
        permission_profile = _actor_codex_permission_profile(
            actor_git_mask,
            sanitized_config_path=sanitized_config_path,
            execution_root=execution_root,
            readable_paths=(*readable_paths, Path(executable)),
            writable_paths=writable_paths,
            denied_paths=denied_paths,
            workspace_access=workspace_access,
        )
        base.extend(
            [
                "-C",
                str(execution_root),
                "exec",
            ]
        )
        common = [
            "-c",
            'default_permissions="aoa_external_actor"',
            "-c",
            f"permissions.aoa_external_actor={permission_profile}",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--disable",
            "multi_agent",
            "--disable",
            "use_legacy_landlock",
            "-m",
            model_slug,
            "-c",
            f'model_reasoning_effort="{effort}"',
            "-c",
            'approval_policy="never"',
            "-c",
            'shell_environment_policy.inherit="core"',
            "-c",
            'shell_environment_policy.exclude=["*KEY*","*TOKEN*","*SECRET*","*PASSWORD*","*CREDENTIAL*"]',
        ]
        if shell_environment:
            common.extend(
                [
                    "-c",
                    "shell_environment_policy.set="
                    + _toml_inline_string_map(shell_environment),
                ]
            )
        common.extend(
            [
                "--output-schema",
                str(output_schema),
                "--json",
                "-o",
                str(output_message),
            ]
        )
        for server in reversed(tool_entry["mcp_server_configs"]):
            server_id = str(server["server_id"])
            endpoint_url = (mcp_endpoint_overrides or {}).get(server_id)
            if endpoint_url is None:
                raise ExternalCodexRuntimeError(
                    "mcp_credential_proxy_unavailable",
                    f"role-scoped MCP server lacks an attempt-local proxy: {server_id}",
                )
            server_config = '{url="' + endpoint_url + '",enabled=true,required=true}'
            common[0:0] = ["-c", f"mcp_servers.{server_id}={server_config}"]
        # The projection has its own exact, read-only Git body.  Codex and the
        # actor can therefore use repository-local inspection without ever
        # consulting or mutating the owner checkout's Git metadata.
        if mode == "resume":
            if not thread_id:
                raise ExternalCodexRuntimeError(
                    "resume_thread_missing", "resume requires an exact Codex thread id"
                )
            return [*base, "resume", *common, thread_id, "-"]
        return [*base, *common, "--color", "never", "-"]

    def _run_worker(
        self,
        session_id: str,
        *,
        attempt_id: str,
        attempt_number: int,
        mode: Literal["start", "resume"],
        resume_payload: Mapping[str, Any] | None,
    ) -> None:
        credential_proxies: list[_McpCredentialProxy] = []
        try:
            self._run_worker_attempt(
                session_id,
                attempt_id=attempt_id,
                attempt_number=attempt_number,
                mode=mode,
                resume_payload=resume_payload,
                credential_proxies=credential_proxies,
            )
        finally:
            # The bearer-bearing relay is an attempt-local capability. Close it
            # before any exception reaches the outer worker failure closeout.
            _close_mcp_credential_proxies(credential_proxies)

    def _run_worker_attempt(
        self,
        session_id: str,
        *,
        attempt_id: str,
        attempt_number: int,
        mode: Literal["start", "resume"],
        resume_payload: Mapping[str, Any] | None,
        credential_proxies: list[_McpCredentialProxy],
    ) -> None:
        session_dir = self._session_dir(session_id)
        attempt_dir = session_dir / "attempts" / f"{attempt_number:03d}"
        scratch = attempt_dir / "scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        projection_descriptor = -1
        child_workspace_descriptor = -1
        with self._lock(session_id):
            state = self._load_state(session_id)
            launch, _, binding, task, realization, role_raw = (
                self._materialized_payloads(state)
            )
            workspace_manifest_input_id = str(launch["workspace_manifest_input_id"])
            controller_inputs = state.get(
                "controller_materialized_task_inputs",
                state["materialized_task_inputs"],
            )
            manifest_inputs = [
                item
                for item in controller_inputs
                if item["input_id"] == workspace_manifest_input_id
            ]
            if (
                launch["workspace_initial_posture"] == "exact_baseline"
                and len(manifest_inputs) != 1
            ):
                raise ExternalCodexRuntimeError(
                    "workspace_manifest_required",
                    "durable exact_baseline lost its workspace manifest",
                )
            source_workspace = Path(state["workspace_path"])
            if state.get("review_seed_envelope_ref") is None:
                if manifest_inputs:
                    manifest = load_json(
                        Path(manifest_inputs[0]["path"]),
                        label="materialized external Codex workspace manifest",
                    )
                    assert_workspace_manifest(manifest, source_workspace)
                try:
                    source_manifest = build_workspace_manifest(source_workspace)
                except ExternalCodexRuntimeError as exc:
                    self._worker_failure_locked(
                        state,
                        attempt_id=attempt_id,
                        code="workspace_source_race",
                        message=(
                            "source workspace cannot be revalidated before inference: "
                            f"{exc}"
                        ),
                    )
                    return
                if source_manifest != state["workspace_manifest_baseline"]:
                    self._worker_failure_locked(
                        state,
                        attempt_id=attempt_id,
                        code="workspace_source_race",
                        message=(
                            "source workspace changed between admission and Codex launch"
                        ),
                    )
                    return
            else:
                _load_verified_json_ref(
                    state["review_seed_envelope_ref"],
                    label="durable reviewer seed envelope",
                    schema_path=REVIEW_SEED_ENVELOPE_SCHEMA_PATH,
                )
            tool_entry = next(
                item
                for item in self.profile["tool_profiles"]
                if item["profile_id"] == state["tool_profile_id"]
            )
            preflight = self._codex_preflight(
                launch,
                str(state["model_slug"]),
                str(state["reasoning_effort"]),
                tool_entry,
                repository_workspace=self._projection_path_from_state(state),
            )
            admitted_mount_wrapper_digest = state["preflight"].get(
                "mount_wrapper_digest"
            )
            admitted_mount_launcher_digest = state["preflight"].get(
                "mount_launcher_digest"
            )
            if (
                not isinstance(admitted_mount_wrapper_digest, str)
                or preflight["mount_wrapper_digest"] != admitted_mount_wrapper_digest
            ):
                self._worker_failure_locked(
                    state,
                    attempt_id=attempt_id,
                    code="mount_wrapper_drift",
                    message="mount wrapper changed after durable admission",
                )
                return
            if (
                not isinstance(admitted_mount_launcher_digest, str)
                or preflight["mount_launcher_digest"] != admitted_mount_launcher_digest
            ):
                self._worker_failure_locked(
                    state,
                    attempt_id=attempt_id,
                    code="mount_launcher_drift",
                    message="mount launcher changed after durable admission",
                )
                return
            if state.get("review_seed_envelope_ref") is None:
                current_manifest = build_workspace_manifest(source_workspace)
                if current_manifest != state["workspace_manifest_baseline"]:
                    self._worker_failure_locked(
                        state,
                        attempt_id=attempt_id,
                        code="workspace_source_race",
                        message=(
                            "workspace bytes changed between admission and Codex launch"
                        ),
                    )
                    return
            target_workspace = self._projection_path_from_state(state)
            actor_baseline_ref = state.get("actor_baseline_manifest_ref")
            if not isinstance(actor_baseline_ref, dict):
                self._worker_failure_locked(
                    state,
                    attempt_id=attempt_id,
                    code="legacy_projection_unavailable",
                    message="no durable actor baseline manifest is available",
                )
                return
            # The original baseline remains the origin for the cumulative
            # terminal delta.  A resumed actor, however, must start from the
            # exact final tree produced by its preceding attempt rather than
            # being forced back to that origin.
            attempt_baseline_ref = (
                state.get("actor_final_manifest_ref")
                if mode == "resume"
                else actor_baseline_ref
            )
            if not isinstance(attempt_baseline_ref, dict):
                self._worker_failure_locked(
                    state,
                    attempt_id=attempt_id,
                    code="resume_projection_baseline_unavailable",
                    message="resume has no exact preceding actor final manifest",
                )
                return
            attempt_baseline = _load_verified_json_ref(
                attempt_baseline_ref,
                label="actor attempt baseline manifest",
                schema_path=ACTOR_MANIFEST_SCHEMA_PATH,
            )
            projection_flags = os.O_PATH | os.O_CLOEXEC | os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                projection_flags |= os.O_NOFOLLOW
            try:
                projection_descriptor = os.open(
                    target_workspace,
                    projection_flags,
                )
            except OSError:
                self._worker_failure_locked(
                    state,
                    attempt_id=attempt_id,
                    code="actor_projection_unavailable",
                    message="runtime-owned actor projection cannot be descriptor-bound",
                )
                return
            observed_attempt_baseline = _checked_actor_manifest(
                target_workspace,
                source_manifest_digest=str(
                    state["source_manifest_before_ref"]["artifact_digest"]
                ),
                source_git_head=str(state["workspace_expected_head"]),
                projection_fd=projection_descriptor,
            )
            if attempt_baseline != observed_attempt_baseline:
                os.close(projection_descriptor)
                projection_descriptor = -1
                self._worker_failure_locked(
                    state,
                    attempt_id=attempt_id,
                    code="actor_projection_drift",
                    message=(
                        "runtime-owned actor projection differs from the exact "
                        "attempt baseline before inference"
                    ),
                )
                return
            codex_execution_root = ACTOR_EXECUTION_ROOT
            sanitized_config_path = scratch / "actor-git-config"
            _atomic_write_bytes(
                sanitized_config_path,
                b"[core]\n\trepositoryFormatVersion = 0\n\tbare = false\n",
                mode=0o400,
            )
            prompt = self._render_prompt(
                state=state,
                launch=launch,
                binding=binding,
                task=task,
                role_raw=role_raw,
                execution_root=codex_execution_root,
                resume_payload=resume_payload,
            )
            prompt_path = attempt_dir / "prompt.txt"
            _atomic_write_bytes(prompt_path, prompt.encode("utf-8"), mode=0o400)
            output_schema = self._execution_result_schema_path(state)
            output_message = attempt_dir / "model-report.json"
            started_credential_proxies, mcp_endpoints = _start_mcp_credential_proxies(
                tool_entry
            )
            credential_proxies.extend(started_credential_proxies)
            specialized_environment, specialized_readable_paths = (
                _specialized_environment(
                    self.profile,
                    tool_entry,
                )
            )
            codex_command = self._codex_command(
                launch=launch,
                realization=realization,
                tool_entry=tool_entry,
                execution_root=codex_execution_root,
                output_schema=output_schema,
                output_message=output_message,
                mode=mode,
                thread_id=state.get("thread_id"),
                mcp_endpoint_overrides=mcp_endpoints,
                sanitized_config_path=sanitized_config_path,
                readable_paths=(
                    output_schema,
                    *(
                        Path(str(item["path"]))
                        for item in state["materialized_task_inputs"]
                    ),
                    *specialized_readable_paths,
                ),
                writable_paths=(attempt_dir, scratch),
                denied_paths=(
                    Path("/proc"),
                    self._session_dir(str(state["session_id"]))
                    / "inputs"
                    / "controller-immutable",
                ),
                workspace_access=(
                    "write"
                    if binding.permission_posture.sandbox_mode == "workspace_write"
                    else "read"
                ),
                shell_environment=specialized_environment,
            )
            process_identity_path = attempt_dir / "process-identity.json"
            child_workspace_descriptor = os.dup(projection_descriptor)
            command = self._containment_command(
                codex_command,
                executable_digest=str(launch["codex_executable_digest"]),
                identity_path=process_identity_path,
                mount_wrapper_digest=str(state["preflight"]["mount_wrapper_digest"]),
                mount_launcher_digest=str(state["preflight"]["mount_launcher_digest"]),
                workspace_fd=child_workspace_descriptor,
            )
            if str(source_workspace) in "\0".join(command):
                raise ExternalCodexRuntimeError(
                    "actor_source_path_exposed",
                    "source workspace absolute path would be exposed in actor argv",
                )
            attempt = state["attempts"][attempt_number - 1]
            attempt["status"] = "running"
            attempt["started_at"] = iso_now()
            attempt["codex_argv"] = command
            attempt["execution_root"] = str(codex_execution_root)
            state["status"] = "running"
            self._save_state(state)

        raw_events_path = attempt_dir / "codex-events.jsonl"
        stderr_path = attempt_dir / "codex-stderr.log"
        environment = self._codex_environment(
            launch,
            scratch,
            tool_entry,
            repository_workspace=target_workspace,
        )
        started = utc_now()
        runtime_failure_code: str | None = None
        runtime_failure_message: str | None = None
        terminate_requested = False
        interrupt_request_path = attempt_dir / "interrupt-request.json"
        with (
            prompt_path.open("rb") as prompt_handle,
            stderr_path.open("wb") as stderr_handle,
            raw_events_path.open("ab") as raw_handle,
        ):
            try:
                process = subprocess.Popen(
                    command,
                    stdin=prompt_handle,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                    cwd=str(attempt_dir),
                    start_new_session=True,
                    pass_fds=(child_workspace_descriptor,),
                )
            finally:
                os.close(child_workspace_descriptor)
                child_workspace_descriptor = -1
            supervisor_start_ticks = _process_start_ticks(process.pid)
            if supervisor_start_ticks is None:
                process.terminate()
                process.wait(timeout=3)
                raise ExternalCodexRuntimeError(
                    "codex_process_identity_invalid",
                    "cannot record the exact supervisor process identity",
                )
            with self._lock(session_id):
                state = self._load_state(session_id)
                attempt = state["attempts"][attempt_number - 1]
                attempt["supervisor_pid"] = process.pid
                attempt["supervisor_start_ticks"] = supervisor_start_ticks
                state["supervisor_pid"] = process.pid
                state["supervisor_start_ticks"] = supervisor_start_ticks
                self._append_event(
                    state,
                    event_type="external_agent.supervisor_started",
                    payload={
                        "supervisor_pid": process.pid,
                        "supervisor_start_ticks": supervisor_start_ticks,
                    },
                    attempt_id=attempt_id,
                    significance="progress",
                )
                self._save_state(state)
            try:
                process_identity, process_identity_ref = (
                    _wait_for_process_identity_receipt(
                        process_identity_path,
                        process=process,
                        supervisor_start_ticks=supervisor_start_ticks,
                    )
                )
            except ExternalCodexRuntimeError:
                self._terminate_supervised_process(process, supervisor_start_ticks)
                raise
            codex_pid = int(process_identity["codex_pid"])
            codex_start_ticks = int(process_identity["codex_start_ticks"])
            with self._lock(session_id):
                state = self._load_state(session_id)
                attempt = state["attempts"][attempt_number - 1]
                attempt["supervisor_pid"] = process.pid
                attempt["supervisor_start_ticks"] = supervisor_start_ticks
                attempt["process_identity_ref"] = process_identity_ref
                attempt["codex_pid"] = codex_pid
                attempt["codex_start_ticks"] = codex_start_ticks
                state["supervisor_pid"] = process.pid
                state["supervisor_start_ticks"] = supervisor_start_ticks
                state["codex_pid"] = codex_pid
                state["codex_start_ticks"] = codex_start_ticks
                self._append_event(
                    state,
                    event_type="external_agent.process_started",
                    payload={
                        "supervisor_pid": process.pid,
                        "supervisor_start_ticks": supervisor_start_ticks,
                        "codex_pid": codex_pid,
                        "codex_start_ticks": codex_start_ticks,
                        "process_identity_ref": process_identity_ref,
                        "command_argv_digest": canonical_digest(command),
                    },
                    attempt_id=attempt_id,
                    significance="progress",
                )
                self._save_state(state)
            assert process.stdout is not None and process.stderr is not None
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            stdout_buffer = b""
            while selector.get_map():
                ready = selector.select(timeout=0.25)
                if not ready and process.poll() is not None:
                    ready = [
                        (key, selectors.EVENT_READ)
                        for key in selector.get_map().values()
                    ]
                for key, _ in ready:
                    stream = str(key.data)
                    chunk = os.read(key.fd, 65_536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if stream == "stdout":
                        stdout_buffer += chunk
                        raw_handle.write(chunk)
                        raw_handle.flush()
                    else:
                        stderr_handle.write(chunk)
                        stderr_handle.flush()
                    self._record_output_bytes(
                        session_id,
                        attempt_id=attempt_id,
                        attempt_number=attempt_number,
                        byte_count=len(chunk),
                    )
                    if stream == "stdout":
                        while b"\n" in stdout_buffer:
                            line, stdout_buffer = stdout_buffer.split(b"\n", 1)
                            if len(line) > MAX_EVENT_LINE_BYTES:
                                runtime_failure_code = "codex_event_too_large"
                                terminate_requested = True
                                self._terminate_supervised_process(
                                    process,
                                    supervisor_start_ticks,
                                )
                                break
                            try:
                                self._record_codex_event(
                                    session_id,
                                    attempt_id=attempt_id,
                                    attempt_number=attempt_number,
                                    line=line + b"\n",
                                    projection_fd=projection_descriptor,
                                )
                            except ExternalCodexRuntimeError as exc:
                                runtime_failure_code = exc.code
                                runtime_failure_message = str(exc)
                                terminate_requested = True
                                self._terminate_supervised_process(
                                    process,
                                    supervisor_start_ticks,
                                )
                                break
                        if (
                            not terminate_requested
                            and len(stdout_buffer) > MAX_EVENT_LINE_BYTES
                        ):
                            runtime_failure_code = "codex_event_too_large"
                            terminate_requested = True
                            self._terminate_supervised_process(
                                process,
                                supervisor_start_ticks,
                            )
                    if terminate_requested:
                        break
                if terminate_requested:
                    break
            selector.close()
            if stdout_buffer and not terminate_requested:
                if len(stdout_buffer) > MAX_EVENT_LINE_BYTES:
                    runtime_failure_code = "codex_event_too_large"
                    terminate_requested = True
                    self._terminate_supervised_process(
                        process,
                        supervisor_start_ticks,
                    )
                else:
                    self._record_codex_event(
                        session_id,
                        attempt_id=attempt_id,
                        attempt_number=attempt_number,
                        line=stdout_buffer,
                        projection_fd=projection_descriptor,
                    )
            raw_handle.flush()
            stderr_handle.flush()
            os.fsync(raw_handle.fileno())
            os.fsync(stderr_handle.fileno())
            exit_code = process.wait()
        if interrupt_request_path.is_file():
            try:
                interrupt_request = load_json(
                    interrupt_request_path,
                    label="controlled interrupt request",
                )
                if (
                    interrupt_request.get("session_id") != session_id
                    or interrupt_request.get("attempt_id") != attempt_id
                    or interrupt_request.get("supervisor_pid") != process.pid
                    or interrupt_request.get("supervisor_start_ticks")
                    != supervisor_start_ticks
                    or interrupt_request.get("codex_pid") != codex_pid
                    or interrupt_request.get("codex_start_ticks") != codex_start_ticks
                ):
                    raise ExternalCodexRuntimeError(
                        "interrupt_request_invalid",
                        "controlled interrupt request differs from the active process",
                    )
                runtime_failure_code = "controlled_interruption"
            except ExternalCodexRuntimeError as exc:
                runtime_failure_code = exc.code
                runtime_failure_message = str(exc)
        _close_mcp_credential_proxies(credential_proxies)
        finished = utc_now()
        with self._lock(session_id):
            state = self._load_state(session_id)
            self._finalize_attempt_locked(
                state,
                attempt_id=attempt_id,
                attempt_number=attempt_number,
                exit_code=exit_code,
                started=started,
                finished=finished,
                report_path=output_message,
                raw_events_path=raw_events_path,
                stderr_path=stderr_path,
                runtime_failure_code=runtime_failure_code,
                runtime_failure_message=runtime_failure_message,
                projection_fd=projection_descriptor,
            )
        os.close(projection_descriptor)
        projection_descriptor = -1

    @staticmethod
    def _terminate_supervised_process(
        process: subprocess.Popen[bytes], supervisor_start_ticks: int | None
    ) -> None:
        if supervisor_start_ticks is None:
            raise ExternalCodexRuntimeError(
                "codex_process_identity_invalid",
                "supervisor process start identity was not recorded",
            )
        _terminate_owned_process_group(process.pid, supervisor_start_ticks)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired as exc:
            raise ExternalCodexRuntimeError(
                "codex_process_cleanup_incomplete",
                "supervisor leader did not become waitable after group cleanup",
            ) from exc

    def _record_output_bytes(
        self,
        session_id: str,
        *,
        attempt_id: str,
        attempt_number: int,
        byte_count: int,
    ) -> int:
        with self._lock(session_id):
            state = self._load_state(session_id)
            attempt = state["attempts"][attempt_number - 1]
            if attempt["attempt_id"] != attempt_id:
                raise ExternalCodexRuntimeError(
                    "attempt_identity_mismatch",
                    "runtime output belongs to another attempt",
                )
            attempt["output_bytes"] = int(attempt.get("output_bytes", 0)) + byte_count
            state["output_bytes"] = int(state.get("output_bytes", 0)) + byte_count
            self._save_state(state)
            return int(state["output_bytes"])

    def _codex_state_delta(
        self,
        state: Mapping[str, Any],
        *,
        payload: Mapping[str, Any],
        attempt_id: str,
        projection_fd: int | None = None,
    ) -> dict[str, Any]:
        """Build the exact replayable state delta for one normalized event."""

        if "_runtime_state_delta_v1" in payload:
            raise ExternalCodexRuntimeError(
                "codex_event_reserved_field",
                "Codex event used a runtime-reserved semantic delta field",
            )
        source_type = str(payload.get("type") or "unknown")
        thread_delta: str | None = None
        thread_id = payload.get("thread_id")
        if source_type == "thread.started" and isinstance(thread_id, str) and thread_id:
            thread_delta = thread_id
        usage_delta = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
        }
        turn_increment = 0
        if source_type == "turn.completed" and isinstance(payload.get("usage"), dict):
            turn_increment = 1
            usage = payload["usage"]
            for target in usage_delta:
                value = usage.get(target)
                if (
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and value >= 0
                ):
                    usage_delta[target] = value
        command_record: dict[str, Any] | None = None
        item = payload.get("item")
        if (
            source_type in {"item.started", "item.completed"}
            and isinstance(item, dict)
            and item.get("type") == "command_execution"
        ):
            command = _command_text(item)
            command_record = {
                "attempt_id": attempt_id,
                "command": command or "<unavailable>",
                "status": str(
                    item.get("status")
                    or ("started" if source_type == "item.started" else "unknown")
                ),
                "exit_code": (
                    None if source_type == "item.started" else item.get("exit_code")
                ),
            }
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id:
                command_record["item_id"] = item_id
            if source_type == "item.started":
                command_record["event_phase"] = "started"
            if source_type == "item.completed" and command:
                task = load_json(
                    Path(state["materialized_inputs"]["task"]),
                    label="materialized task",
                )
                attempts = state.get("attempts")
                execution_root = (
                    attempts[-1].get("execution_root")
                    if isinstance(attempts, list) and attempts
                    else None
                )
                actor_workspace = self._projection_path_from_state(state)
                wrappers = (
                    _descriptor_validation_wrapper_argv(execution_root, spec)
                    if execution_root
                    else _validation_wrapper_argv(actor_workspace, spec)
                    for spec in task["validation_commands"]
                )
                if any(_command_matches_argv(command, wrapper) for wrapper in wrappers):
                    command_record["workspace_manifest_digest"] = canonical_digest(
                        _checked_actor_manifest(
                            actor_workspace,
                            source_manifest_digest=str(
                                state["source_manifest_before_ref"]["artifact_digest"]
                            ),
                            source_git_head=str(state["workspace_expected_head"]),
                            projection_fd=projection_fd,
                        )
                    )
        return {
            "thread_id": thread_delta,
            "turn_count_increment": turn_increment,
            "usage_increment": usage_delta,
            "executed_command": command_record,
        }

    def _apply_codex_state_delta(
        self,
        state: dict[str, Any],
        *,
        attempt_id: str,
        source_type: str,
        source_payload: Mapping[str, Any],
        delta: Mapping[str, Any],
    ) -> None:
        """Validate and apply one runtime-authored Codex semantic delta."""

        required = {
            "thread_id",
            "turn_count_increment",
            "usage_increment",
            "executed_command",
        }
        if set(delta) != required:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "Codex event semantic delta has an invalid shape",
            )
        attempt = next(
            (
                item
                for item in state.get("attempts", [])
                if item.get("attempt_id") == attempt_id
            ),
            None,
        )
        if not isinstance(attempt, dict):
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "Codex event semantic delta names no durable attempt",
            )
        expected_thread = (
            source_payload.get("thread_id")
            if source_type == "thread.started"
            and isinstance(source_payload.get("thread_id"), str)
            and source_payload.get("thread_id")
            else None
        )
        if delta.get("thread_id") != expected_thread:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "Codex thread delta differs from the source event",
            )
        if expected_thread is not None:
            previous = state.get("thread_id")
            if previous is not None and previous != expected_thread:
                raise ExternalCodexRuntimeError(
                    "thread_identity_drift",
                    "Codex resume returned another thread identity",
                )
            state["thread_id"] = expected_thread
            attempt["thread_id"] = expected_thread

        expected_turn_increment = int(
            source_type == "turn.completed"
            and isinstance(source_payload.get("usage"), dict)
        )
        if delta.get("turn_count_increment") != expected_turn_increment:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "Codex turn delta differs from the source event",
            )
        usage_delta = delta.get("usage_increment")
        if not isinstance(usage_delta, dict) or set(usage_delta) != {
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
        }:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "Codex usage delta has an invalid shape",
            )
        source_usage = source_payload.get("usage")
        for target in ("input_tokens", "cached_input_tokens", "output_tokens"):
            expected_value = 0
            if expected_turn_increment and isinstance(source_usage, dict):
                raw_value = source_usage.get(target)
                if (
                    isinstance(raw_value, int)
                    and not isinstance(raw_value, bool)
                    and raw_value >= 0
                ):
                    expected_value = raw_value
            if usage_delta.get(target) != expected_value:
                raise ExternalCodexRuntimeError(
                    "runtime_event_semantic_recovery_invalid",
                    "Codex usage delta differs from the source event",
                )
            state["usage"][target] = int(state["usage"].get(target, 0)) + expected_value
        state["turn_count"] = int(state.get("turn_count", 0)) + expected_turn_increment

        item = source_payload.get("item")
        source_is_command = (
            source_type in {"item.started", "item.completed"}
            and isinstance(item, dict)
            and item.get("type") == "command_execution"
        )
        command_record = delta.get("executed_command")
        if source_is_command:
            if not isinstance(command_record, dict):
                raise ExternalCodexRuntimeError(
                    "runtime_event_semantic_recovery_invalid",
                    "Codex command event has no durable execution delta",
                )
            command = _command_text(item)
            expected_record = {
                "attempt_id": attempt_id,
                "command": command or "<unavailable>",
                "status": str(
                    item.get("status")
                    or ("started" if source_type == "item.started" else "unknown")
                ),
                "exit_code": (
                    None if source_type == "item.started" else item.get("exit_code")
                ),
            }
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id:
                expected_record["item_id"] = item_id
            if source_type == "item.started":
                expected_record["event_phase"] = "started"
            if any(
                command_record.get(key) != value
                for key, value in expected_record.items()
            ):
                raise ExternalCodexRuntimeError(
                    "runtime_event_semantic_recovery_invalid",
                    "Codex command delta differs from the source event",
                )
            if set(command_record) - {*expected_record, "workspace_manifest_digest"}:
                raise ExternalCodexRuntimeError(
                    "runtime_event_semantic_recovery_invalid",
                    "Codex command delta contains unsupported fields",
                )
            task = load_json(
                Path(state["materialized_inputs"]["task"]),
                label="materialized task",
            )
            attempts = state.get("attempts")
            execution_root = (
                attempts[-1].get("execution_root")
                if isinstance(attempts, list) and attempts
                else None
            )
            actor_workspace = self._projection_path_from_state(state)
            is_fixed_validation = (
                source_type == "item.completed"
                and bool(command)
                and any(
                    _command_matches_argv(
                        command,
                        _descriptor_validation_wrapper_argv(execution_root, spec)
                        if execution_root
                        else _validation_wrapper_argv(actor_workspace, spec),
                    )
                    for spec in task["validation_commands"]
                )
            )
            manifest_digest = command_record.get("workspace_manifest_digest")
            if is_fixed_validation != isinstance(manifest_digest, str) or (
                isinstance(manifest_digest, str)
                and re.fullmatch(r"sha256:[0-9a-f]{64}", manifest_digest) is None
            ):
                raise ExternalCodexRuntimeError(
                    "runtime_event_semantic_recovery_invalid",
                    "Codex command delta has no exact fixed-validation manifest digest",
                )
            replacement_index: int | None = None
            if source_type == "item.completed" and isinstance(item_id, str) and item_id:
                replacement_index = next(
                    (
                        index
                        for index in range(len(state["executed_commands"]) - 1, -1, -1)
                        if state["executed_commands"][index].get("attempt_id")
                        == attempt_id
                        and state["executed_commands"][index].get("item_id") == item_id
                        and state["executed_commands"][index].get("event_phase")
                        == "started"
                    ),
                    None,
                )
            if replacement_index is None:
                state["executed_commands"].append(dict(command_record))
            else:
                state["executed_commands"][replacement_index] = dict(command_record)
        elif command_record is not None:
            raise ExternalCodexRuntimeError(
                "runtime_event_semantic_recovery_invalid",
                "non-command Codex event carries a command delta",
            )

    def _record_codex_event(
        self,
        session_id: str,
        *,
        attempt_id: str,
        attempt_number: int,
        line: bytes,
        projection_fd: int | None = None,
    ) -> None:
        try:
            payload = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExternalCodexRuntimeError(
                "codex_event_invalid_json",
                "Codex emitted a malformed JSONL protocol record",
            ) from exc
        if not isinstance(payload, dict):
            raise ExternalCodexRuntimeError(
                "codex_event_invalid_shape",
                "Codex emitted a non-object JSONL protocol record",
            )
        source_type = str(payload.get("type") or "unknown")
        with self._lock(session_id):
            state = self._load_state(session_id)
            attempt = state["attempts"][attempt_number - 1]
            if attempt.get("attempt_id") != attempt_id:
                raise ExternalCodexRuntimeError(
                    "attempt_identity_mismatch",
                    "Codex event belongs to another durable attempt",
                )
            delta = self._codex_state_delta(
                state,
                payload=payload,
                attempt_id=attempt_id,
                projection_fd=projection_fd,
            )
            self._apply_codex_state_delta(
                state,
                attempt_id=attempt_id,
                source_type=source_type,
                source_payload=payload,
                delta=delta,
            )
            normalized_payload = dict(payload)
            normalized_payload["_runtime_state_delta_v1"] = delta
            significance: Literal[
                "trace",
                "progress",
                "checkpoint",
                "review",
                "authority",
                "parent_wake",
                "terminal",
            ] = (
                "progress"
                if source_type in {"thread.started", "turn.started", "turn.completed"}
                else "trace"
            )
            self._append_event(
                state,
                event_type=f"codex.{source_type}",
                payload=normalized_payload,
                attempt_id=attempt_id,
                thread_id=state.get("thread_id"),
                source_event_type=source_type,
                significance=significance,
            )
            self._save_state(state)

    def _wake_evaluation(
        self,
        binding: IncarnationBinding,
        status: str,
    ) -> dict[str, Any]:
        event_kind = {
            "completed": "result.validated",
            "review_required": "result.review_required",
            "paused": "result.checkpointed",
            "authority_blocked": "run.authority_required",
            "failed": "result.failed",
            "interrupted": "runtime.interrupted",
        }.get(status, "result.unknown")
        condition = next(
            (
                item
                for item in binding.wake_policy.conditions
                if item.event_kind == event_kind
            ),
            None,
        )
        action = (
            condition.action
            if condition is not None
            else binding.wake_policy.default_action
        )
        return {
            "event_kind": event_kind,
            "condition_id": condition.condition_id if condition is not None else None,
            "action": action,
            "wake_parent": action == "wake_parent",
            "reason": (
                condition.description
                if condition is not None
                else "No exact wake condition matched; runtime applied the configured default."
            ),
        }

    def _validate_report_against_task(
        self,
        report: Mapping[str, Any],
        *,
        state: Mapping[str, Any],
        task: Mapping[str, Any],
        binding: IncarnationBinding,
        runtime_evidence_paths: Mapping[str, Path],
        final_workspace_manifest_digest: str | None,
        projection_fd: int | None = None,
    ) -> None:
        def require_text(value: Any, label: str) -> None:
            if not isinstance(value, str) or not value.strip():
                raise ExternalCodexRuntimeError(
                    "model_report_semantics_invalid",
                    f"model report contains an empty {label}",
                )

        actor_workspace = self._projection_path_from_state(state)
        if (
            report.get("task_id") != state["task_id"]
            or report.get("incarnation_id") != state["incarnation_id"]
        ):
            raise ExternalCodexRuntimeError(
                "model_report_identity_mismatch",
                "model report identity differs from runtime state",
            )
        expected_decision = {
            "completed": "proceed",
            "review_required": (
                "return_for_repair"
                if task["execution_posture"] == "independent_review"
                else "submit_for_review"
            ),
            "authority_blocked": "escalate",
            "failed": "stop",
            "paused": "checkpoint",
        }[str(report["status"])]
        if report.get("decision") != expected_decision:
            raise ExternalCodexRuntimeError(
                "model_report_status_decision_mismatch",
                "model report decision does not match its terminal status",
            )
        require_text(report.get("summary"), "summary")
        transition = report["transition"]
        for key in (
            "from_status",
            "to_status",
            "owner",
            "approval_posture",
            "rollback_reentry_route",
        ):
            require_text(transition.get(key), f"transition {key}")
        transition_evidence = transition["evidence_refs"]
        if not transition_evidence:
            raise ExternalCodexRuntimeError(
                "model_report_semantics_invalid",
                "model report transition evidence refs must be non-empty",
            )
        for value in transition_evidence:
            require_text(value, "transition evidence ref")
            _validate_report_evidence_ref(
                value,
                state=state,
                source_evidence_paths=task.get(
                    "source_evidence_paths", task["allowed_paths"]
                ),
                runtime_evidence_paths=runtime_evidence_paths,
                workspace_fd=projection_fd,
            )
        for finding in report["findings"]:
            require_text(finding.get("category"), "finding category")
            require_text(finding.get("summary"), "finding summary")
            evidence = finding["evidence_refs"]
            if not evidence:
                raise ExternalCodexRuntimeError(
                    "model_report_semantics_invalid",
                    "each finding requires evidence refs",
                )
            for value in evidence:
                require_text(value, "finding evidence ref")
                _validate_report_evidence_ref(
                    value,
                    state=state,
                    source_evidence_paths=task.get(
                        "source_evidence_paths", task["allowed_paths"]
                    ),
                    runtime_evidence_paths=runtime_evidence_paths,
                    workspace_fd=projection_fd,
                )
        artifact_paths = report["artifact_paths"]
        if len(artifact_paths) != len(set(artifact_paths)):
            raise ExternalCodexRuntimeError(
                "model_report_semantics_invalid",
                "model report artifact paths must be unique",
            )
        changed_workspace_paths = {
            str(item.get("path")) for item in state["changed_paths"]
        }
        for value in artifact_paths:
            require_text(value, "artifact path")
            if not _relative_path_is_allowed(value, task["allowed_paths"]):
                raise ExternalCodexRuntimeError(
                    "model_report_artifact_out_of_scope",
                    "model report names an artifact outside the allowed workspace paths",
                )
            if task["allowed_effect_class"] == "read_only":
                raise ExternalCodexRuntimeError(
                    "model_report_artifact_forbidden_read_only",
                    "read-only work cannot claim a produced workspace artifact",
                )
            _workspace_artifact_path(actor_workspace, value)
            if value not in changed_workspace_paths:
                raise ExternalCodexRuntimeError(
                    "model_report_artifact_not_produced",
                    "model report artifact was not produced relative to the immutable baseline",
                )
        validation_claims = report["validation_claims"]
        expected_command_ids = [
            str(item["command_id"]) for item in task["validation_commands"]
        ]
        actual_command_ids = [str(item.get("command_id")) for item in validation_claims]
        if actual_command_ids != expected_command_ids:
            raise ExternalCodexRuntimeError(
                "model_report_validation_claims_incomplete",
                "model report validation claims must exactly cover fixed task commands in order",
            )
        attempts = state.get("attempts")
        execution_root = (
            attempts[-1].get("execution_root")
            if isinstance(attempts, list) and attempts
            else None
        )
        selected_validation_executions: list[dict[str, Any]] = []
        validation_workspace_mismatch = False
        for command_spec, claim in zip(
            task["validation_commands"], validation_claims, strict=True
        ):
            require_text(claim.get("command_id"), "validation command id")
            require_text(claim.get("evidence_ref"), "validation evidence ref")
            expected_evidence_ref = f"runtime:validation:{command_spec['command_id']}"
            if claim["evidence_ref"] != expected_evidence_ref:
                raise ExternalCodexRuntimeError(
                    "model_report_validation_evidence_unbound",
                    "validation evidence ref differs from its exact command identity",
                )
            executions = [
                item
                for item in state["executed_commands"]
                if item.get("validation_command_id") == command_spec["command_id"]
                and item.get("validation_argv") == command_spec["argv"]
                and item.get("validation_cwd")
                == str(
                    _descriptor_validation_cwd(execution_root, command_spec)
                    if execution_root
                    else _validation_cwd(actor_workspace, command_spec)
                )
                and item.get("validation_wrapper_argv")
                == list(
                    _descriptor_validation_wrapper_argv(execution_root, command_spec)
                    if execution_root
                    else _validation_wrapper_argv(actor_workspace, command_spec)
                )
            ]
            if not executions:
                raise ExternalCodexRuntimeError(
                    "model_report_validation_not_executed",
                    "fixed validation command has no exact argv/cwd execution receipt",
                )
            last_execution = executions[-1]
            selected_validation_executions.append(last_execution)
            if (
                not isinstance(final_workspace_manifest_digest, str)
                or last_execution.get("workspace_manifest_digest")
                != final_workspace_manifest_digest
            ):
                validation_workspace_mismatch = True
            observed_status = (
                "passed"
                if last_execution.get("status") == "completed"
                and last_execution.get("exit_code") == 0
                else "failed"
            )
            if claim["status"] != observed_status:
                raise ExternalCodexRuntimeError(
                    "model_report_validation_claim_unbound",
                    "model report validation status differs from the exact observed command",
                )
        if validation_workspace_mismatch:
            current_attempt_id = str(state["attempts"][-1]["attempt_id"])
            completed_attempt_commands = [
                item
                for item in state["executed_commands"]
                if item.get("attempt_id") == current_attempt_id
                and item.get("exit_code") is not None
            ]
            terminal_validation_suffix = completed_attempt_commands[
                -len(expected_command_ids) :
            ]
            if (
                len(terminal_validation_suffix) != len(expected_command_ids)
                or terminal_validation_suffix != selected_validation_executions
                or [
                    item.get("validation_command_id")
                    for item in terminal_validation_suffix
                ]
                != expected_command_ids
                or terminal_validation_suffix[-1].get("workspace_manifest_digest")
                != final_workspace_manifest_digest
            ):
                raise ExternalCodexRuntimeError(
                    "model_report_validation_workspace_unbound",
                    "fixed validation commands neither share the final manifest nor form an exact terminal suite ending on it",
                )
        for value in report["residuals"]:
            require_text(value, "residual")
        expected = task["transition"]
        if (
            transition["from_status"] != expected["from_status"]
            or transition["owner"] != task["target_owner"]
            or transition["approval_posture"] != expected["approval_posture"]
            or transition["rollback_reentry_route"]
            != expected["rollback_reentry_route"]
        ):
            raise ExternalCodexRuntimeError(
                "model_report_transition_mismatch",
                "model report changed the exact transition owner or posture",
            )
        if report["status"] in {"completed", "review_required"}:
            expected_to_status = expected["target_status"]
            if (
                report["status"] == "review_required"
                and task["execution_posture"] == "independent_review"
            ):
                expected_to_status = expected["review_required_status"]
            if transition["to_status"] != expected_to_status:
                raise ExternalCodexRuntimeError(
                    "model_report_transition_mismatch",
                    "terminal report does not name its task-owned outcome status",
                )
        if task["review_required"] and report["status"] == "completed":
            raise ExternalCodexRuntimeError(
                "model_report_review_gate_bypassed",
                "task requires independent review before a completed result",
            )
        proposed = report["reentry_request"]
        require_text(proposed.get("condition_id"), "re-entry condition")
        require_text(proposed.get("reason"), "re-entry reason")
        runtime_wake = self._wake_evaluation(binding, str(report["status"]))
        if runtime_wake["condition_id"] is None:
            raise ExternalCodexRuntimeError(
                "model_report_wake_condition_unbound",
                "report status has no exact event-filtered wake condition",
            )
        if proposed["condition_id"] != runtime_wake["condition_id"]:
            raise ExternalCodexRuntimeError(
                "model_report_wake_condition_mismatch",
                "model report wake condition differs from its observed-status binding",
            )
        if proposed["proposed_action"] != runtime_wake["action"]:
            raise ExternalCodexRuntimeError(
                "model_report_wake_action_mismatch",
                "model report proposed an action different from its observed-status binding",
            )

    def _forbidden_effects(
        self,
        commands: Sequence[Mapping[str, Any]],
        task: Mapping[str, Any],
        binding: Any = None,
    ) -> list[str]:
        detected: set[str] = set()
        allow_sandboxed_indirection = _sandbox_confined_indirection_is_admitted(
            task, binding
        )
        for item in commands:
            command = str(item.get("command") or "")
            detected.update(_command_effects(command) & RUNTIME_WIDE_FORBIDDEN_EFFECTS)
            if (
                item.get("validation_command_id") is None
                and not allow_sandboxed_indirection
                and (_command_has_unclassified_indirection(command))
            ):
                detected.add("unclassified_indirect_effect")
        return sorted(detected)

    def _failure_authority_effects(
        self,
        commands: Sequence[Mapping[str, Any]],
    ) -> list[str]:
        """Classify an incomplete worker from durable observations alone.

        Failure closeout must remain possible when a materialized launch or
        task is itself the object that drifted. Known effect families are
        intrinsically outside the runtime mandate, while the manifest digest
        recorded with an exact fixed-validation command is its durable
        exemption from the otherwise opaque-interpreter rule.
        """

        detected: set[str] = set()
        for item in commands:
            command = str(item.get("command") or "")
            detected.update(_command_effects(command))
            is_fixed_validation = isinstance(item.get("workspace_manifest_digest"), str)
            if not is_fixed_validation and _command_has_unclassified_indirection(
                command
            ):
                detected.add("unclassified_indirect_effect")
        return sorted(detected)

    def _finalize_attempt_locked(
        self,
        state: dict[str, Any],
        *,
        attempt_id: str,
        attempt_number: int,
        exit_code: int,
        started: datetime,
        finished: datetime,
        report_path: Path,
        raw_events_path: Path,
        stderr_path: Path,
        runtime_failure_code: str | None,
        runtime_failure_message: str | None,
        projection_fd: int | None = None,
    ) -> None:
        launch, _, binding, task, _, _ = self._materialized_payloads(state)
        actor_workspace = self._projection_path_from_state(state)
        attempt = state["attempts"][attempt_number - 1]
        state["executed_commands"] = _annotate_validation_executions(
            state["executed_commands"],
            task=task,
            workspace=attempt["execution_root"] or ACTOR_EXECUTION_ROOT,
            descriptor_bound_coordinate=True,
        )
        attempt["finished_at"] = finished.isoformat().replace("+00:00", "Z")
        attempt["exit_code"] = exit_code
        state["supervisor_pid"] = None
        state["supervisor_start_ticks"] = None
        state["codex_pid"] = None
        state["codex_start_ticks"] = None
        state["worker_pid"] = None
        state["worker_start_ticks"] = None
        state["finished_at"] = finished.isoformat().replace("+00:00", "Z")
        actor_manifest_baseline_ref = state.get("actor_baseline_manifest_ref")
        actor_manifest_baseline: dict[str, Any] | None = None
        if isinstance(actor_manifest_baseline_ref, dict):
            actor_manifest_baseline = _load_verified_json_ref(
                actor_manifest_baseline_ref,
                label="actor baseline manifest",
                schema_path=ACTOR_MANIFEST_SCHEMA_PATH,
            )
        actor_manifest_match: bool | None = None
        workspace_manifest_ref: dict[str, Any] | None = None
        final_workspace_manifest_digest: str | None = None
        actor_delta_ref: dict[str, Any] | None = None
        actor_final_manifest_ref: dict[str, Any] | None = None
        source_manifest_match: bool | None = None
        source_manifest_final_ref: dict[str, Any] | None = None
        actor_delta_changes: list[dict[str, Any]] = []
        manifest_observation_gap = False
        manifest_observation_failure_code: str | None = None
        head_drift = False
        try:
            current_manifest = _checked_actor_manifest(
                actor_workspace,
                source_manifest_digest=str(
                    state["source_manifest_before_ref"]["artifact_digest"]
                ),
                source_git_head=str(state["workspace_expected_head"]),
                projection_fd=projection_fd,
            )
            if projection_fd is not None:
                _assert_descriptor_coordinate(projection_fd, actor_workspace)
            final_manifest_path = (
                self._session_dir(str(state["session_id"]))
                / "actor-final-manifest.json"
            )
            _atomic_write_json(final_manifest_path, current_manifest)
            workspace_manifest_ref = _artifact_ref(final_manifest_path)
            actor_final_manifest_ref = workspace_manifest_ref
            final_workspace_manifest_digest = canonical_digest(current_manifest)
            if actor_manifest_baseline is None:
                raise ExternalCodexRuntimeError(
                    "legacy_projection_unavailable",
                    "actor baseline manifest is unavailable at finalization",
                )
            actor_manifest_match = current_manifest == actor_manifest_baseline
            delta = build_actor_delta(
                actor_manifest_baseline,
                current_manifest,
                baseline_digest=canonical_digest(actor_manifest_baseline),
                current_digest=final_workspace_manifest_digest,
            )
            validate_json(delta, ACTOR_DELTA_SCHEMA_PATH, label="actor delta")
            actor_delta_changes = list(delta["changes"])
            delta_path = (
                self._session_dir(str(state["session_id"])) / "actor-delta.json"
            )
            _atomic_write_json(delta_path, delta)
            actor_delta_ref = _artifact_ref(delta_path)
            state["actor_final_manifest_ref"] = actor_final_manifest_ref
            state["actor_delta_ref"] = actor_delta_ref
            source_manifest = (
                state["workspace_manifest_baseline"]
                if state.get("review_seed_envelope_ref") is not None
                else build_workspace_manifest(state["workspace_path"])
            )
            source_manifest_final_path = (
                self._session_dir(str(state["session_id"]))
                / "source-manifest-final.json"
            )
            _atomic_write_json(source_manifest_final_path, source_manifest, mode=0o400)
            source_manifest_final_ref = _artifact_ref(source_manifest_final_path)
            state["source_manifest_final_ref"] = source_manifest_final_ref
            source_manifest_match = (
                source_manifest == state["workspace_manifest_baseline"]
            )
            head_drift = not source_manifest_match
        except (ExternalCodexRuntimeError, ProjectionError) as exc:
            changed_paths = []
            manifest_observation_gap = True
            manifest_observation_failure_code = getattr(
                exc,
                "code",
                "workspace_manifest_observation_gap",
            )
        else:
            # Keep the result's long-standing compact receipt shape.  The
            # actor delta is the durable source for before/after manifests,
            # modes, types, and content digests.
            changed_paths = [
                {"path": str(item["path"]), "status": str(item["status"])}
                for item in delta["changes"]
            ]
        state["changed_paths"] = changed_paths
        failure_code: str | None = None
        failure_message: str | None = runtime_failure_message
        report: dict[str, Any] | None = None
        controlled_interruption = runtime_failure_code == "controlled_interruption"
        if controlled_interruption:
            self._record_interrupted_usage_gap_locked(state, attempt_id)
        if runtime_failure_code is not None:
            failure_code = runtime_failure_code
        if exit_code != 0 and not controlled_interruption:
            capacity_failure_message = _codex_provider_capacity_failure_message(
                raw_events_path
            )
            if failure_code is None and capacity_failure_message is not None:
                failure_code = "provider_capacity_unavailable"
                failure_message = capacity_failure_message
            else:
                failure_code = failure_code or "codex_process_failed"
        if report_path.is_file():
            try:
                report = load_json(report_path, label="model report")
                validate_json(report, REPORT_SCHEMA_PATH, label="model report")
                runtime_evidence_paths: dict[str, Path] = {}
                if workspace_manifest_ref is not None:
                    runtime_evidence_paths["workspace-final-manifest"] = (
                        final_manifest_path
                    )
                nested_namespace = _load_nested_evidence_namespace(state)
                nested_namespace_ref = state.get("nested_evidence_namespace_ref")
                if (
                    nested_namespace is not None
                    and isinstance(nested_namespace_ref, dict)
                ):
                    runtime_evidence_paths["nested-evidence-namespace"] = Path(
                        str(nested_namespace_ref["artifact_ref"])
                    )
                self._validate_report_against_task(
                    report,
                    state=state,
                    task=task,
                    binding=binding,
                    runtime_evidence_paths=runtime_evidence_paths,
                    final_workspace_manifest_digest=final_workspace_manifest_digest,
                    projection_fd=projection_fd,
                )
            except ExternalCodexRuntimeError as exc:
                failure_code = exc.code
                failure_message = str(exc)
                report = None
        elif failure_code is None:
            failure_code = "model_report_missing"

        detected_effects = self._forbidden_effects(
            state["executed_commands"], task, binding
        )
        command_observation_gap = any(
            item.get("command") == "<unavailable>"
            for item in state["executed_commands"]
        )
        out_of_scope_paths = _actor_delta_changes_out_of_scope(
            actor_delta_changes,
            task["allowed_paths"],
        )
        read_only_drift = task["allowed_effect_class"] == "read_only" and (
            actor_manifest_match is False
            or (actor_manifest_match is None and bool(changed_paths))
        )
        if (
            detected_effects
            or out_of_scope_paths
            or read_only_drift
            or head_drift
            or command_observation_gap
            or manifest_observation_gap
        ):
            status = "authority_blocked"
            failure_code = (
                "command_observation_gap"
                if command_observation_gap
                else (
                    manifest_observation_failure_code
                    or "workspace_manifest_observation_gap"
                )
                if manifest_observation_gap
                else failure_code or "authority_boundary_crossed"
            )
        elif controlled_interruption:
            status = "interrupted"
        elif failure_code is not None or report is None:
            status = "failed"
        else:
            status = str(report["status"])
        attempt["status"] = status
        attempt_duration = max(0.0, (finished - started).total_seconds())
        attempt["active_wall_seconds"] = attempt_duration
        attempt["wall_time_accounted"] = True
        state["active_wall_seconds"] = (
            float(state.get("active_wall_seconds", 0.0)) + attempt_duration
        )
        state["status"] = status
        wake = self._wake_evaluation(binding, status)
        state["wake_evaluation"] = wake
        validation_payload = {
            "status": status,
            "failure_code": failure_code,
            "detected_forbidden_effects": detected_effects,
            "out_of_scope_paths": out_of_scope_paths,
            "read_only_drift": read_only_drift,
            "workspace_manifest_match": actor_manifest_match,
            "source_manifest_match": source_manifest_match,
            "workspace_head_drift": head_drift,
            "workspace_manifest_observation_gap": manifest_observation_gap,
            "command_observation_gap": command_observation_gap,
        }
        self._append_event(
            state,
            event_type="external_agent.report_validated",
            payload=validation_payload,
            attempt_id=attempt_id,
            significance=(
                "authority"
                if status == "authority_blocked"
                else "checkpoint"
                if status == "paused"
                else "review"
                if status == "review_required"
                else "terminal"
            ),
        )
        self._append_event(
            state,
            event_type="external_agent.wake_evaluated",
            payload=wake,
            attempt_id=attempt_id,
            significance="parent_wake" if wake["wake_parent"] else "terminal",
        )
        events_path = self._events_path(str(state["session_id"]))
        failure_path = (
            self._session_dir(str(state["session_id"])) / "runtime-failure.json"
        )
        if report is None:
            _atomic_write_json(
                failure_path,
                {
                    "schema_version": "abyss_stack_external_codex_failure_v1",
                    "failure_code": failure_code,
                    "message": failure_message,
                    "status": status,
                    "attempt_id": attempt_id,
                },
            )
            report_ref_path = failure_path
        else:
            report_ref_path = report_path
        duration = float(state["active_wall_seconds"])
        usage = {
            **state["usage"],
            "metering_mode": binding.usage_metering.mode,
            "active_cost_regime": "chatgpt_quota",
            "cost_usd": None,
        }
        evidence_refs = [
            _artifact_ref(report_ref_path),
            _artifact_ref(events_path),
            _artifact_ref(stderr_path),
            _artifact_ref(
                Path(state["materialized_inputs"]["task"]), owner=task["target_owner"]
            ),
            _artifact_ref(
                Path(state["materialized_inputs"]["incarnation_binding"]),
                owner="aoa-sdk",
            ),
            _artifact_ref(raw_events_path),
        ]
        for ref in (
            workspace_manifest_ref,
            actor_delta_ref,
            state.get("source_manifest_before_ref"),
            state.get("source_manifest_after_ref"),
            source_manifest_final_ref,
        ):
            if isinstance(ref, dict):
                evidence_refs.append(ref)
        owner_admission_ref = self._owner_admission_ref(state)
        if owner_admission_ref is not None:
            evidence_refs.append(owner_admission_ref)
        evidence_refs.extend(self._preserved_result_refs(state))
        result = {
            "schema_version": "abyss_stack_external_codex_result_v2",
            "session_id": state["session_id"],
            "admission_class": state["admission_class"],
            "incarnation_id": state["incarnation_id"],
            "task_id": state["task_id"],
            "task_family": state["task_family"],
            "execution_posture": state["execution_posture"],
            "status": status,
            "failure_code": failure_code,
            "thread_id": state.get("thread_id"),
            "model_slug": state["model_slug"],
            "reasoning_effort": state["reasoning_effort"],
            "started_at": state["started_at"],
            "finished_at": state["finished_at"],
            "duration_seconds": duration,
            "attempt_count": len(state["attempts"]),
            "turn_count": state["turn_count"],
            "output_bytes": state["output_bytes"],
            "active_wall_seconds": state["active_wall_seconds"],
            "exit_code": exit_code,
            "usage": usage,
            "usage_observation": self._usage_observation(state),
            "codex_invocations": self._codex_invocations(state),
            "executed_commands": state["executed_commands"],
            "changed_paths": changed_paths,
            "workspace_manifest_match": actor_manifest_match,
            "source_manifest_match": source_manifest_match,
            "workspace_manifest_ref": workspace_manifest_ref,
            "actor_projection_path": str(actor_workspace),
            "actor_baseline_manifest_ref": actor_manifest_baseline_ref,
            "actor_final_manifest_ref": actor_final_manifest_ref,
            "actor_delta_ref": actor_delta_ref,
            "source_manifest_before_ref": state.get("source_manifest_before_ref"),
            "source_manifest_after_ref": state.get("source_manifest_after_ref"),
            "source_manifest_final_ref": source_manifest_final_ref,
            "owner_admission_ref": owner_admission_ref,
            "report_ref": evidence_refs[0],
            "events_ref": evidence_refs[1],
            "stderr_ref": evidence_refs[2],
            "wake_evaluation": wake,
            "evidence_refs": evidence_refs,
        }
        validate_json(result, RESULT_SCHEMA_PATH, label="runtime result")
        result_path = self._session_dir(str(state["session_id"])) / "result.json"
        _atomic_write_json(result_path, result)
        self._preserve_terminal_result_locked(state, result, result_path)
        state["result_path"] = str(result_path)
        state["result_digest"] = sha256_file(result_path)
        state["active_attempt_id"] = None
        self._save_state(state)

    def _worker_failure_locked(
        self,
        state: dict[str, Any],
        *,
        attempt_id: str,
        code: str,
        message: str,
    ) -> None:
        cleanup_failed = False
        supervisor_pid, supervisor_ticks = _state_supervisor_identity(state)
        if isinstance(supervisor_pid, int) and isinstance(supervisor_ticks, int):
            try:
                _terminate_owned_process_group(supervisor_pid, supervisor_ticks)
            except ExternalCodexRuntimeError as exc:
                cleanup_failed = True
                code = exc.code
                message = str(exc)
        detected_effects = self._failure_authority_effects(state["executed_commands"])
        command_observation_gap = any(
            item.get("command") == "<unavailable>"
            for item in state["executed_commands"]
        )
        authority_crossed = bool(
            cleanup_failed or detected_effects or command_observation_gap
        )
        if command_observation_gap:
            code = "command_observation_gap"
            message = (
                "worker ended after an unobservable command; authority-safe "
                "failure classification is unavailable"
            )
        elif detected_effects:
            code = "authority_boundary_crossed"
            message = (
                "worker ended after a forbidden or unclassified command effect: "
                + ", ".join(detected_effects)
            )
        terminal_status = "authority_blocked" if authority_crossed else "failed"
        self._account_attempt_wall_locked(state, attempt_id, utc_now())
        state["status"] = terminal_status
        state["finished_at"] = iso_now()
        state["worker_pid"] = None
        state["worker_start_ticks"] = None
        if not cleanup_failed:
            state["supervisor_pid"] = None
            state["supervisor_start_ticks"] = None
            state["codex_pid"] = None
            state["codex_start_ticks"] = None
        state["active_attempt_id"] = None
        for attempt in state["attempts"]:
            if attempt["attempt_id"] == attempt_id:
                attempt["status"] = terminal_status
                attempt["finished_at"] = state["finished_at"]
                attempt["exit_code"] = None
        self._append_event(
            state,
            event_type="external_agent.runtime_failed",
            payload={
                "failure_code": code,
                "message": message,
                "detected_forbidden_effects": detected_effects,
                "command_observation_gap": command_observation_gap,
            },
            attempt_id=attempt_id,
            significance="authority" if authority_crossed else "terminal",
        )
        self._write_failure_result_locked(
            state,
            attempt_id=attempt_id,
            code=code,
            message=message,
            status=terminal_status,
        )
        self._save_state(state)

    def _write_failure_result_locked(
        self,
        state: dict[str, Any],
        *,
        attempt_id: str,
        code: str,
        message: str,
        status: str = "failed",
    ) -> None:
        closeout = state.get("failure_closeout")
        if not isinstance(closeout, dict):
            raise ExternalCodexRuntimeError(
                "legacy_failure_closeout_unavailable",
                "legacy runtime state has no admission-time failure closeout envelope",
            )
        task = _load_verified_json_ref(
            closeout["task_ref"],
            label="failure-closeout task",
            schema_path=TASK_SCHEMA_PATH,
        )
        session_dir = self._session_dir(str(state["session_id"]))
        failure_path = session_dir / "runtime-failure.json"
        events_path = self._events_path(str(state["session_id"]))
        attempt_number = max(1, len(state["attempts"]))
        worker_log_path = (
            session_dir / "attempts" / f"{attempt_number:03d}" / "worker.log"
        )
        if not worker_log_path.exists():
            _atomic_write_bytes(worker_log_path, b"")
        workspace_manifest_match: bool | None = None
        source_manifest_match: bool | None = None
        workspace_manifest_ref: dict[str, Any] | None = None
        actor_delta_ref: dict[str, Any] | None = None
        actor_baseline_ref = state.get("actor_baseline_manifest_ref")
        actor_final_ref: dict[str, Any] | None = None
        source_final_ref: dict[str, Any] | None = None
        actor_delta_changes: list[dict[str, Any]] = []
        changed_paths: list[dict[str, str]] = []
        try:
            if isinstance(actor_baseline_ref, dict):
                actor_baseline = _load_verified_json_ref(
                    actor_baseline_ref,
                    label="actor baseline manifest",
                    schema_path=ACTOR_MANIFEST_SCHEMA_PATH,
                )
                actor_workspace = self._projection_path_from_state(state)
                current_manifest = _checked_actor_manifest(
                    actor_workspace,
                    source_manifest_digest=str(
                        state["source_manifest_before_ref"]["artifact_digest"]
                    ),
                    source_git_head=str(state["workspace_expected_head"]),
                )
                final_manifest_path = session_dir / "actor-final-manifest.json"
                _atomic_write_json(final_manifest_path, current_manifest)
                workspace_manifest_ref = _artifact_ref(final_manifest_path)
                actor_final_ref = workspace_manifest_ref
                workspace_manifest_match = current_manifest == actor_baseline
                delta = build_actor_delta(
                    actor_baseline,
                    current_manifest,
                    baseline_digest=canonical_digest(actor_baseline),
                    current_digest=canonical_digest(current_manifest),
                )
                validate_json(delta, ACTOR_DELTA_SCHEMA_PATH, label="actor delta")
                actor_delta_changes = list(delta["changes"])
                delta_path = session_dir / "actor-delta.json"
                _atomic_write_json(delta_path, delta)
                actor_delta_ref = _artifact_ref(delta_path)
                changed_paths = [
                    {"path": str(item["path"]), "status": str(item["status"])}
                    for item in actor_delta_changes
                ]
                state["actor_final_manifest_ref"] = actor_final_ref
                state["actor_delta_ref"] = actor_delta_ref
            else:
                current_manifest = build_workspace_manifest(state["workspace_path"])
                final_manifest_path = session_dir / "workspace-final-manifest.json"
                _atomic_write_json(final_manifest_path, current_manifest)
                workspace_manifest_ref = _artifact_ref(final_manifest_path)
                baseline_manifest = state["workspace_manifest_baseline"]
                changed_paths = compare_workspace_manifest(
                    baseline_manifest, current_manifest
                )
                workspace_manifest_match = current_manifest == baseline_manifest
            source_manifest = (
                state["workspace_manifest_baseline"]
                if state.get("review_seed_envelope_ref") is not None
                else build_workspace_manifest(state["workspace_path"])
            )
            source_final_path = session_dir / "source-manifest-final.json"
            _atomic_write_json(source_final_path, source_manifest, mode=0o400)
            source_final_ref = _artifact_ref(source_final_path)
            source_manifest_match = (
                source_manifest == state["workspace_manifest_baseline"]
            )
            state["source_manifest_final_ref"] = source_final_ref
        except (ExternalCodexRuntimeError, ProjectionError) as exc:
            changed_paths = []
            status = "authority_blocked"
            observation_code = getattr(exc, "code", "actor_projection_observation_gap")
            message = (
                f"original failure {code}: {message}; workspace manifest "
                f"observation failed: {observation_code}: {exc}"
            )
            code = (
                observation_code
                if observation_code
                in {
                    "actor_projection_coordinate_drift",
                    "actor_projection_observation_gap",
                }
                else "workspace_manifest_observation_gap"
            )
            state["status"] = status
            for attempt in state["attempts"]:
                if attempt["attempt_id"] == attempt_id:
                    attempt["status"] = status
            self._append_event(
                state,
                event_type="external_agent.failure_manifest_unobserved",
                payload={"failure_code": code, "message": message},
                attempt_id=attempt_id,
                significance="authority",
            )
        out_of_scope_paths = (
            _actor_delta_changes_out_of_scope(
                actor_delta_changes,
                task["allowed_paths"],
            )
            if actor_delta_ref is not None
            else [str(item["path"]) for item in changed_paths]
        )
        read_only_drift = (
            task["allowed_effect_class"] == "read_only"
            and workspace_manifest_match is False
        )
        source_drift = source_manifest_match is False
        if read_only_drift or out_of_scope_paths or source_drift:
            original_code = code
            status = "authority_blocked"
            code = "authority_boundary_crossed"
            drift_reasons: list[str] = []
            if read_only_drift:
                drift_reasons.append("read-only actor projection changed")
            if out_of_scope_paths:
                drift_reasons.append(
                    "out-of-scope actor paths changed: " + ", ".join(out_of_scope_paths)
                )
            if source_drift:
                drift_reasons.append("owner source changed during actor execution")
            message = (
                f"original failure {original_code}: {message}; authority drift: "
                + "; ".join(drift_reasons)
            )
            state["status"] = status
            for attempt in state["attempts"]:
                if attempt["attempt_id"] == attempt_id:
                    attempt["status"] = status
            self._append_event(
                state,
                event_type="external_agent.failure_authority_drift_detected",
                payload={
                    "failure_code": code,
                    "message": message,
                    "out_of_scope_paths": out_of_scope_paths,
                    "read_only_drift": read_only_drift,
                    "source_drift": source_drift,
                },
                attempt_id=attempt_id,
                significance="authority",
            )
        wake_evaluations = closeout.get("wake_evaluations")
        wake = (
            wake_evaluations.get(status) if isinstance(wake_evaluations, dict) else None
        )
        if not isinstance(wake, dict):
            raise ExternalCodexRuntimeError(
                "runtime_state_invalid",
                f"failure closeout has no persisted wake evaluation for {status}",
            )
        _atomic_write_json(
            failure_path,
            {
                "schema_version": "abyss_stack_external_codex_failure_v1",
                "failure_code": code,
                "status": status,
                "attempt_id": attempt_id,
                "message": message,
            },
        )
        state["changed_paths"] = changed_paths
        state["wake_evaluation"] = dict(wake)
        evidence_refs = [
            _artifact_ref(failure_path),
            _artifact_ref(events_path),
            _artifact_ref(worker_log_path),
            dict(closeout["task_ref"]),
            dict(closeout["incarnation_binding_ref"]),
        ]
        for ref in (
            workspace_manifest_ref,
            actor_delta_ref,
            state.get("source_manifest_before_ref"),
            state.get("source_manifest_after_ref"),
            source_final_ref,
        ):
            if isinstance(ref, dict):
                evidence_refs.append(ref)
        owner_admission_ref = self._owner_admission_ref(state)
        if owner_admission_ref is not None:
            evidence_refs.append(owner_admission_ref)
        evidence_refs.extend(self._preserved_result_refs(state))
        result = {
            "schema_version": "abyss_stack_external_codex_result_v2",
            "session_id": state["session_id"],
            "admission_class": state["admission_class"],
            "incarnation_id": state["incarnation_id"],
            "task_id": state["task_id"],
            "task_family": state["task_family"],
            "execution_posture": state["execution_posture"],
            "status": status,
            "failure_code": code,
            "thread_id": state.get("thread_id"),
            "model_slug": state["model_slug"],
            "reasoning_effort": state["reasoning_effort"],
            "started_at": state.get("started_at") or state["created_at"],
            "finished_at": state["finished_at"],
            "duration_seconds": float(state.get("active_wall_seconds", 0.0)),
            "attempt_count": len(state["attempts"]),
            "turn_count": int(state.get("turn_count", 0)),
            "output_bytes": int(state.get("output_bytes", 0)),
            "active_wall_seconds": float(state.get("active_wall_seconds", 0.0)),
            "exit_code": None,
            "usage": {
                **state["usage"],
                "metering_mode": "observe_only",
                "active_cost_regime": "chatgpt_quota",
                "cost_usd": None,
            },
            "usage_observation": self._usage_observation(state),
            "codex_invocations": self._codex_invocations(state),
            "executed_commands": state["executed_commands"],
            "changed_paths": changed_paths,
            "workspace_manifest_match": workspace_manifest_match,
            "source_manifest_match": source_manifest_match,
            "workspace_manifest_ref": workspace_manifest_ref,
            "actor_projection_path": state.get("actor_projection_path"),
            "actor_baseline_manifest_ref": actor_baseline_ref,
            "actor_final_manifest_ref": actor_final_ref,
            "actor_delta_ref": actor_delta_ref,
            "source_manifest_before_ref": state.get("source_manifest_before_ref"),
            "source_manifest_after_ref": state.get("source_manifest_after_ref"),
            "source_manifest_final_ref": source_final_ref,
            "owner_admission_ref": owner_admission_ref,
            "report_ref": evidence_refs[0],
            "events_ref": evidence_refs[1],
            "stderr_ref": evidence_refs[2],
            "wake_evaluation": wake,
            "evidence_refs": evidence_refs,
        }
        validate_json(result, RESULT_SCHEMA_PATH, label="runtime failure result")
        result_path = session_dir / "result.json"
        _atomic_write_json(result_path, result)
        self._preserve_terminal_result_locked(state, result, result_path)
        state["result_path"] = str(result_path)
        state["result_digest"] = sha256_file(result_path)

    @staticmethod
    def _codex_invocations(state: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "attempt_id": attempt["attempt_id"],
                "mode": attempt["mode"],
                "worker_pid": attempt["worker_pid"],
                "supervisor_pid": attempt.get("supervisor_pid"),
                "supervisor_start_ticks": attempt.get("supervisor_start_ticks"),
                "codex_pid": attempt["codex_pid"],
                "codex_start_ticks": attempt.get("codex_start_ticks"),
                "process_identity_ref": attempt.get("process_identity_ref"),
                "thread_id": attempt["thread_id"],
                "argv": attempt["codex_argv"],
                "argv_digest": canonical_digest(attempt["codex_argv"]),
                "execution_root": attempt.get("execution_root"),
            }
            for attempt in state["attempts"]
            if isinstance(attempt.get("codex_argv"), list)
        ]

    @staticmethod
    def _account_attempt_wall_locked(
        state: dict[str, Any],
        attempt_id: str,
        ended_at: datetime,
    ) -> None:
        for attempt in state["attempts"]:
            if attempt["attempt_id"] != attempt_id:
                continue
            if attempt.get("wall_time_accounted"):
                return
            started_at = attempt.get("started_at")
            active_seconds = (
                max(0.0, (ended_at - parse_timestamp(started_at)).total_seconds())
                if isinstance(started_at, str)
                else 0.0
            )
            attempt["active_wall_seconds"] = active_seconds
            attempt["wall_time_accounted"] = True
            state["active_wall_seconds"] = (
                float(state.get("active_wall_seconds", 0.0)) + active_seconds
            )
            return

    def _recover_terminal_result_locked(self, state: dict[str, Any]) -> bool:
        """Commit an atomically written terminal result after a lost state save."""

        session_id = str(state["session_id"])
        result_path = self._session_dir(session_id) / "result.json"
        if not result_path.is_file() or result_path.is_symlink():
            return False
        result = load_json(result_path, label="recoverable runtime result")
        validate_json(result, RESULT_SCHEMA_PATH, label="recoverable runtime result")

        # A resumable session intentionally leaves the preceding result at this
        # path until the next attempt commits. It is evidence, not the current
        # attempt's terminal commit.
        if result.get("attempt_count") != len(state["attempts"]):
            return False

        identity_pairs = (
            ("session_id", session_id),
            ("admission_class", state["admission_class"]),
            ("incarnation_id", state["incarnation_id"]),
            ("task_id", state["task_id"]),
            ("task_family", state["task_family"]),
            ("execution_posture", state["execution_posture"]),
            ("model_slug", state["model_slug"]),
            ("reasoning_effort", state["reasoning_effort"]),
            ("started_at", state["started_at"]),
        )
        if (
            result.get("status") not in {*TERMINAL_STATES, "interrupted"}
            or not isinstance(result.get("finished_at"), str)
            or any(result.get(key) != expected for key, expected in identity_pairs)
        ):
            raise ExternalCodexRuntimeError(
                "runtime_terminal_result_recovery_mismatch",
                "terminal result does not match the active durable session identity",
            )
        if state.get("thread_id") is not None and (
            result.get("thread_id") != state.get("thread_id")
        ):
            raise ExternalCodexRuntimeError(
                "runtime_terminal_result_recovery_mismatch",
                "terminal result changed the durable Codex thread identity",
            )

        expected_events_path = self._events_path(session_id)
        events_ref = result["events_ref"]
        if (
            events_ref not in result["evidence_refs"]
            or events_ref.get("artifact_ref") != str(expected_events_path)
            or events_ref.get("artifact_digest") != state.get("events_digest")
            or _verified_artifact_ref_path(
                events_ref, label="recoverable terminal event stream"
            )
            != expected_events_path
        ):
            raise ExternalCodexRuntimeError(
                "runtime_terminal_result_recovery_mismatch",
                "terminal result does not bind the recovered normalized event stream",
            )
        for key in ("report_ref", "stderr_ref"):
            if result[key] not in result["evidence_refs"]:
                raise ExternalCodexRuntimeError(
                    "runtime_terminal_result_recovery_mismatch",
                    f"terminal result does not bind {key} as evidence",
                )
        for index, evidence_ref in enumerate(result["evidence_refs"]):
            _verified_artifact_ref_path(
                evidence_ref,
                label=f"recoverable terminal evidence {index + 1}",
            )

        attempts_by_id = {
            str(attempt["attempt_id"]): attempt for attempt in state["attempts"]
        }
        for invocation in result["codex_invocations"]:
            attempt = attempts_by_id.get(str(invocation["attempt_id"]))
            if (
                attempt is None
                or invocation["mode"] != attempt["mode"]
                or invocation["worker_pid"] != attempt["worker_pid"]
                or invocation["argv"] != attempt["codex_argv"]
            ):
                raise ExternalCodexRuntimeError(
                    "runtime_terminal_result_recovery_mismatch",
                    "terminal result changed a durable Codex invocation identity",
                )
            attempt["supervisor_pid"] = invocation.get("supervisor_pid")
            attempt["supervisor_start_ticks"] = invocation.get("supervisor_start_ticks")
            attempt["codex_pid"] = invocation.get("codex_pid")
            attempt["codex_start_ticks"] = invocation.get("codex_start_ticks")
            attempt["process_identity_ref"] = invocation.get("process_identity_ref")
            attempt["thread_id"] = invocation.get("thread_id")
            attempt["execution_root"] = invocation.get("execution_root")

        terminal_attempt = state["attempts"][-1]
        prior_attempts = state["attempts"][:-1]
        terminal_attempt["status"] = result["status"]
        terminal_attempt["finished_at"] = result["finished_at"]
        terminal_attempt["exit_code"] = result["exit_code"]
        terminal_attempt["thread_id"] = result["thread_id"]
        terminal_attempt["output_bytes"] = max(
            0,
            int(result["output_bytes"])
            - sum(int(item["output_bytes"]) for item in prior_attempts),
        )
        terminal_attempt["active_wall_seconds"] = max(
            0.0,
            float(result["active_wall_seconds"])
            - sum(float(item["active_wall_seconds"]) for item in prior_attempts),
        )
        terminal_attempt["wall_time_accounted"] = True

        state["status"] = result["status"]
        state["finished_at"] = result["finished_at"]
        state["thread_id"] = result["thread_id"]
        state["usage"] = {
            key: int(result["usage"][key])
            for key in ("input_tokens", "cached_input_tokens", "output_tokens")
        }
        state["usage_observation_gaps"] = [
            dict(item)
            for item in result.get("usage_observation", {}).get("gap_reasons", [])
        ]
        state["turn_count"] = int(result["turn_count"])
        state["output_bytes"] = int(result["output_bytes"])
        state["active_wall_seconds"] = float(result["active_wall_seconds"])
        state["executed_commands"] = list(result["executed_commands"])
        state["changed_paths"] = list(result["changed_paths"])
        for key in (
            "source_manifest_before_ref",
            "source_manifest_after_ref",
            "source_manifest_final_ref",
            "actor_baseline_manifest_ref",
            "actor_final_manifest_ref",
            "actor_delta_ref",
        ):
            if key in result:
                state[key] = result[key]
        state["wake_evaluation"] = dict(result["wake_evaluation"])
        state["result_path"] = str(result_path)
        state["result_digest"] = sha256_file(result_path)
        state["active_attempt_id"] = None
        state["worker_pid"] = None
        state["worker_start_ticks"] = None
        state["supervisor_pid"] = None
        state["supervisor_start_ticks"] = None
        state["codex_pid"] = None
        state["codex_start_ticks"] = None
        self._save_state(state)
        return True

    def _refresh_interrupted_locked(self, state: dict[str, Any]) -> None:
        for attempt in state.get("attempts", []):
            _reap_owned_child(
                attempt.get("worker_pid"),
                attempt.get("worker_start_ticks"),
            )
        if state["status"] != "running":
            return
        if _pid_matches(state.get("worker_pid"), state.get("worker_start_ticks")):
            return
        if self._recover_terminal_result_locked(state):
            return
        attempt_id = str(state.get("active_attempt_id") or "runtime")
        self._append_event(
            state,
            event_type="external_agent.worker_death_observed",
            payload={"reason": "worker process ended without a terminal receipt"},
            attempt_id=attempt_id,
            significance="terminal",
        )
        self._worker_failure_locked(
            state,
            attempt_id=attempt_id,
            code="unexpected_worker_death",
            message=(
                "worker process ended without a terminal receipt; the exact Codex "
                "process group was terminated before failure closeout"
            ),
        )

    def _public_state(self, state: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": state["schema_version"],
            "session_id": state["session_id"],
            "launch_id": state["launch_id"],
            "admission_class": state["admission_class"],
            "status": state["status"],
            "incarnation_id": state["incarnation_id"],
            "task_id": state["task_id"],
            "task_family": state["task_family"],
            "execution_posture": state["execution_posture"],
            "model_slug": state["model_slug"],
            "reasoning_effort": state["reasoning_effort"],
            "thread_id": state.get("thread_id"),
            "attempt_count": len(state["attempts"]),
            "active_attempt_id": state.get("active_attempt_id"),
            "worker_pid": state.get("worker_pid"),
            "supervisor_pid": state.get("supervisor_pid"),
            "codex_pid": state.get("codex_pid"),
            "last_event_sequence": state["last_event_sequence"],
            "created_at": state["created_at"],
            "started_at": state["started_at"],
            "finished_at": state["finished_at"],
            "wake_evaluation": state.get("wake_evaluation"),
            "result_available": bool(state.get("result_path")),
            "actor_projection_path": state.get("actor_projection_path"),
            "actor_baseline_manifest_ref": state.get("actor_baseline_manifest_ref"),
            "actor_final_manifest_ref": state.get("actor_final_manifest_ref"),
            "actor_delta_ref": state.get("actor_delta_ref"),
        }

    def status(self, session_id: str) -> dict[str, Any]:
        with self._lock(session_id):
            state = self._load_state(session_id)
            self._refresh_interrupted_locked(state)
            return self._public_state(state)

    def events(self, session_id: str, *, after_sequence: int) -> list[dict[str, Any]]:
        if after_sequence < -1:
            raise ExternalCodexRuntimeError(
                "invalid_event_cursor", "event cursor must be at least -1"
            )
        with self._lock(session_id):
            state = self._load_state(session_id)
            self._refresh_interrupted_locked(state)
            path = self._events_path(session_id)
            events: list[dict[str, Any]] = []
            if path.is_file():
                for _line_number, line in _iter_jsonl_bytes(
                    path,
                    failure_code="runtime_event_state_drift",
                    label="runtime event stream",
                ):
                    item = json.loads(line)
                    if int(item["sequence"]) > after_sequence:
                        events.append(item)
            return events

    def result(self, session_id: str) -> dict[str, Any] | None:
        with self._lock(session_id):
            state = self._load_state(session_id)
            self._refresh_interrupted_locked(state)
            result_path = state.get("result_path")
            if not isinstance(result_path, str):
                return None
            result_file = Path(result_path)
            expected_digest = state.get("result_digest")
            if (
                isinstance(expected_digest, str)
                and sha256_file(result_file) != expected_digest
            ):
                raise ExternalCodexRuntimeError(
                    "runtime_result_drift",
                    "durable runtime result bytes differ from recorded state",
                )
            result = load_json(result_file, label="runtime result")
            validate_json(result, RESULT_SCHEMA_PATH, label="runtime result")
            return result

    def resume(self, session_id: str, resume_path: str | Path) -> dict[str, Any]:
        resume = load_json(Path(resume_path), label="resume request")
        validate_json(resume, RESUME_SCHEMA_PATH, label="resume request")
        with self._lock(session_id):
            state = self._load_state(session_id)
            if state["schema_version"] != STATE_SCHEMA_VERSION:
                raise ExternalCodexRuntimeError(
                    "legacy_session_resume_unsupported",
                    "legacy session has no v3 runtime-owned actor projection",
                )
            projection_path = self._projection_path_from_state(state)
            if not isinstance(state.get("actor_baseline_manifest_ref"), dict):
                raise ExternalCodexRuntimeError(
                    "legacy_projection_unavailable",
                    "resume cannot proceed without the original actor projection baseline",
                )
            self._refresh_interrupted_locked(state)
            failed_terminal_followup = state["status"] == "failed"
            if state["status"] not in RESUMABLE_STATES and not failed_terminal_followup:
                raise ExternalCodexRuntimeError(
                    "resume_state_invalid",
                    f"session is not resumable: {state['status']}",
                )
            if (
                resume["session_id"] != session_id
                or resume["thread_id"] != state.get("thread_id")
                or resume["after_event_sequence"] != state["last_event_sequence"]
            ):
                raise ExternalCodexRuntimeError(
                    "resume_identity_mismatch",
                    "resume request differs from exact durable state",
                )
            if not state.get("thread_id"):
                raise ExternalCodexRuntimeError(
                    "resume_thread_missing", "no durable Codex thread is available"
                )
            task: Mapping[str, Any] | None = None
            if (
                failed_terminal_followup
                or state.get("execution_result_schema_ref") is None
            ):
                _, _, _, task, _, _ = self._materialized_payloads(state)
                self._ensure_execution_result_schema_locked(state)
            result_path = state.get("result_path")
            result_digest = state.get("result_digest")
            if not isinstance(result_path, str) or not isinstance(result_digest, str):
                raise ExternalCodexRuntimeError(
                    "resume_result_unavailable",
                    "resume requires the exact prior terminal runtime result",
                )
            result_file = Path(result_path)
            raw_result = read_bounded(result_file)
            if sha256_bytes(raw_result) != result_digest:
                raise ExternalCodexRuntimeError(
                    "runtime_result_drift",
                    "prior runtime result bytes differ from recorded state",
                )
            previous_result = load_json_bytes(
                raw_result,
                label="prior runtime result",
            )
            validate_json(
                previous_result,
                RESULT_SCHEMA_PATH,
                label="prior runtime result",
            )
            if (
                previous_result.get("session_id") != session_id
                or previous_result.get("incarnation_id") != state["incarnation_id"]
                or previous_result.get("task_id") != state["task_id"]
                or previous_result.get("status") != state["status"]
            ):
                raise ExternalCodexRuntimeError(
                    "runtime_result_identity_mismatch",
                    "prior runtime result differs from the durable session identity",
                )
            if previous_result.get("actor_projection_path") not in {
                None,
                str(projection_path),
            }:
                raise ExternalCodexRuntimeError(
                    "resume_projection_mismatch",
                    "prior result names a different runtime-owned actor projection",
                )
            requested_result_digest = resume.get("previous_result_digest")
            if (
                requested_result_digest is not None
                and requested_result_digest != result_digest
            ):
                raise ExternalCodexRuntimeError(
                    "resume_previous_result_mismatch",
                    "resume request names another prior runtime result digest",
                )
            prior_attempt = state["attempts"][-1]
            attempt_dir = (
                self._session_dir(session_id)
                / "attempts"
                / f"{int(prior_attempt['attempt_number']):03d}"
            )
            actor_delta: dict[str, Any] | None = None
            if failed_terminal_followup and isinstance(
                previous_result.get("actor_delta_ref"), dict
            ):
                actor_delta = _load_verified_json_ref(
                    previous_result["actor_delta_ref"],
                    label="prior actor delta",
                    schema_path=ACTOR_DELTA_SCHEMA_PATH,
                )
            failed_review_followup = False
            failed_writer_report_followup = False
            failed_capacity_followup = False
            if failed_terminal_followup:
                failure_code = previous_result.get("failure_code")
                changed_paths = previous_result.get("changed_paths")
                allowed_paths = task.get("allowed_paths") if task is not None else None
                observed_usage = previous_result.get("usage")
                failed_capacity_followup = (
                    failure_code in PROVIDER_CAPACITY_FAILURE_CODES
                    and previous_result.get("source_manifest_match") is True
                    and previous_result.get("workspace_manifest_match") is True
                    and isinstance(
                        previous_result.get("actor_final_manifest_ref"), dict
                    )
                    and actor_delta is not None
                    and actor_delta.get("changes") == []
                    and changed_paths == []
                    and previous_result.get("executed_commands") == []
                    and previous_result.get("turn_count") == 0
                    and isinstance(observed_usage, dict)
                    and all(
                        observed_usage.get(counter) == 0
                        for counter in (
                            "input_tokens",
                            "cached_input_tokens",
                            "output_tokens",
                        )
                    )
                    and _verified_result_attempt_capacity_failure(
                        previous_result, attempt_dir
                    )
                    is not None
                )
                failed_review_candidate = (
                    task is not None
                    and task.get("execution_posture") == "independent_review"
                    and task.get("allowed_effect_class") == "read_only"
                )
                failed_writer_report_candidate = (
                    task is not None
                    and task.get("execution_posture") == "bounded_execution"
                    and task.get("allowed_effect_class") == "repo_mutation"
                    and isinstance(failure_code, str)
                    and failure_code.startswith(WRITER_REPORT_RECOVERY_FAILURE_PREFIX)
                )
                failed_review_followup = (
                    failed_review_candidate
                    and failure_code in REVIEW_REPORT_RECOVERY_FAILURES
                    and previous_result.get("workspace_manifest_match") is True
                    and changed_paths == []
                )
                failed_writer_report_followup = (
                    failed_writer_report_candidate
                    and previous_result.get("source_manifest_match") is True
                    and isinstance(
                        previous_result.get("actor_final_manifest_ref"), dict
                    )
                    and actor_delta is not None
                    and isinstance(actor_delta.get("changes"), list)
                    and isinstance(allowed_paths, list)
                    and not _actor_delta_changes_out_of_scope(
                        actor_delta["changes"],
                        allowed_paths,
                    )
                )
                if (
                    failed_review_candidate
                    and not failed_review_followup
                    and not failed_capacity_followup
                ):
                    raise ExternalCodexRuntimeError(
                        "failed_review_resume_unsupported",
                        "only an unchanged read-only review identity or transition "
                        "binding failure is recoverable",
                    )
                if (
                    failed_writer_report_candidate
                    and not failed_writer_report_followup
                    and not failed_capacity_followup
                ):
                    raise ExternalCodexRuntimeError(
                        "failed_writer_report_resume_unsupported",
                        "writer report recovery requires intact source, actor evidence, and original path authority",
                    )
                if not any(
                    (
                        failed_review_followup,
                        failed_writer_report_followup,
                        failed_capacity_followup,
                    )
                ):
                    raise ExternalCodexRuntimeError(
                        "failed_terminal_resume_unsupported",
                        "failed session has no authority-safe same-role recovery route",
                    )
                expected_reason = (
                    "capacity_recovery"
                    if failed_capacity_followup
                    else "review_followup"
                    if failed_review_followup
                    else "bounded_repair"
                )
                if (
                    resume.get("reason") != expected_reason
                    or resume.get("previous_result_digest") != result_digest
                ):
                    failure = (
                        "failed_capacity_resume_unbound"
                        if failed_capacity_followup
                        else "failed_review_resume_unbound"
                        if failed_review_followup
                        else "failed_writer_report_resume_unbound"
                    )
                    raise ExternalCodexRuntimeError(
                        failure,
                        "failed-session resume must use its recovery reason and bind the exact prior result digest",
                    )
            result_candidates = [attempt_dir / "runtime-result.json"]
            result_candidates.extend(
                sorted(attempt_dir.glob("runtime-result-revision-*.json"))
            )
            preserved_path = next(
                (
                    candidate
                    for candidate in result_candidates
                    if candidate.is_file()
                    and not candidate.is_symlink()
                    and sha256_file(candidate) == result_digest
                ),
                None,
            )
            if preserved_path is None:
                preserved_path = attempt_dir / "runtime-result.json"
                if preserved_path.exists():
                    raise ExternalCodexRuntimeError(
                        "runtime_result_evidence_closure_drift",
                        "no preserved prior runtime result matches the canonical digest",
                    )
                _atomic_write_bytes(preserved_path, raw_result, mode=0o400)
            preserved_ref = _artifact_ref(preserved_path)
            if preserved_ref["artifact_digest"] != result_digest:
                raise ExternalCodexRuntimeError(
                    "runtime_result_drift",
                    "preserved prior runtime result digest differs",
                )
            preserved_closure_ref = self._verified_preserved_result_closure_ref_locked(
                previous_result=previous_result,
                preserved_result_ref=preserved_ref,
                preserved_result_path=preserved_path,
            )
            if state["status"] == "interrupted":
                self._record_interrupted_usage_gap_locked(
                    state,
                    str(prior_attempt["attempt_id"]),
                )
            self._append_event(
                state,
                event_type="external_agent.resume_source_preserved",
                payload={
                    "previous_status": previous_result["status"],
                    "previous_result_ref": preserved_ref,
                    "previous_result_evidence_closure_ref": preserved_closure_ref,
                    "reason": resume["reason"],
                },
                attempt_id=str(prior_attempt["attempt_id"]),
                thread_id=str(state["thread_id"]),
                significance=(
                    "review"
                    if state["status"] in {"failed", "review_required"}
                    else "checkpoint"
                ),
            )
            if failed_review_followup:
                self._append_event(
                    state,
                    event_type="external_agent.failed_review_resume_admitted",
                    payload={
                        "failure_code": previous_result["failure_code"],
                        "previous_result_ref": preserved_ref,
                        "reason": resume["reason"],
                    },
                    attempt_id=str(prior_attempt["attempt_id"]),
                    thread_id=str(state["thread_id"]),
                    significance="review",
                )
            if failed_writer_report_followup:
                self._append_event(
                    state,
                    event_type="external_agent.failed_writer_report_resume_admitted",
                    payload={
                        "failure_code": previous_result["failure_code"],
                        "previous_result_ref": preserved_ref,
                        "reason": resume["reason"],
                    },
                    attempt_id=str(prior_attempt["attempt_id"]),
                    thread_id=str(state["thread_id"]),
                    significance="review",
                )
            if failed_capacity_followup:
                self._append_event(
                    state,
                    event_type="external_agent.capacity_recovery_admitted",
                    payload={
                        "failure_code": previous_result["failure_code"],
                        "previous_result_ref": preserved_ref,
                        "reason": resume["reason"],
                        "capacity_failure_message": (
                            _verified_result_attempt_capacity_failure(
                                previous_result, attempt_dir
                            )
                        ),
                    },
                    attempt_id=str(prior_attempt["attempt_id"]),
                    thread_id=str(state["thread_id"]),
                    significance="checkpoint",
                )
            self._materialize_resume_evidence_locked(
                state,
                resume,
                attempt_id=str(prior_attempt["attempt_id"]),
            )
            state["finished_at"] = None
            state["result_path"] = None
            state["result_digest"] = None
            self._spawn_worker(state, mode="resume", resume_payload=resume)
            return self._public_state(state)

    def interrupt(self, session_id: str) -> dict[str, Any]:
        with self._lock(session_id):
            state = self._load_state(session_id)
            if state["status"] != "running":
                raise ExternalCodexRuntimeError(
                    "interrupt_state_invalid",
                    "only a running session can be interrupted",
                )
            worker_pid = state.get("worker_pid")
            worker_ticks = state.get("worker_start_ticks")
            if not _pid_matches(worker_pid, worker_ticks):
                self._refresh_interrupted_locked(state)
                return self._public_state(state)
            assert isinstance(worker_pid, int)
            if os.getpgid(int(worker_pid)) != int(worker_pid):
                raise ExternalCodexRuntimeError(
                    "worker_identity_invalid", "worker does not own its process group"
                )
            supervisor_pid, supervisor_ticks = _state_supervisor_identity(state)
            if not _pid_matches(supervisor_pid, supervisor_ticks):
                raise ExternalCodexRuntimeError(
                    "interrupt_not_ready",
                    "controlled interruption requires the exact active supervisor",
                )
            assert isinstance(supervisor_pid, int)
            assert isinstance(supervisor_ticks, int)
            if os.getpgid(supervisor_pid) != supervisor_pid:
                raise ExternalCodexRuntimeError(
                    "codex_process_group_invalid",
                    "supervisor does not own the expected descendant process group",
                )
            codex_pid = state.get("codex_pid")
            codex_ticks = state.get("codex_start_ticks")
            if state.get("supervisor_pid") is not None and not _pid_matches(
                codex_pid, codex_ticks
            ):
                raise ExternalCodexRuntimeError(
                    "interrupt_not_ready",
                    "controlled interruption requires the exact active Codex child",
                )
            attempt_id = str(state["active_attempt_id"])
            attempt = next(
                item for item in state["attempts"] if item["attempt_id"] == attempt_id
            )
            attempt_dir = (
                self._session_dir(session_id)
                / "attempts"
                / f"{int(attempt['attempt_number']):03d}"
            )
            _atomic_write_json(
                attempt_dir / "interrupt-request.json",
                {
                    "schema_version": "abyss_stack_external_codex_interrupt_request_v1",
                    "session_id": session_id,
                    "attempt_id": attempt_id,
                    "supervisor_pid": supervisor_pid,
                    "supervisor_start_ticks": supervisor_ticks,
                    "codex_pid": codex_pid,
                    "codex_start_ticks": codex_ticks,
                    "requested_at": iso_now(),
                },
                mode=0o400,
            )
        try:
            os.killpg(supervisor_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with self._lock(session_id):
                state = self._load_state(session_id)
                self._refresh_interrupted_locked(state)
                if state["status"] != "running":
                    return self._public_state(state)
            time.sleep(0.05)
        _terminate_owned_process_group(
            supervisor_pid,
            supervisor_ticks,
            term_timeout=0.0,
            kill_timeout=3.0,
        )
        finalize_deadline = time.monotonic() + 2.0
        while time.monotonic() < finalize_deadline:
            with self._lock(session_id):
                state = self._load_state(session_id)
                self._refresh_interrupted_locked(state)
                if state["status"] != "running":
                    return self._public_state(state)
            time.sleep(0.05)
        if _pid_matches(worker_pid, worker_ticks):
            _terminate_owned_process_group(
                worker_pid,
                worker_ticks,
                term_timeout=2.0,
                kill_timeout=2.0,
            )
        _reap_owned_child(worker_pid, worker_ticks)
        if _pid_matches(worker_pid, worker_ticks):
            raise ExternalCodexRuntimeError(
                "interrupt_incomplete", "worker did not stop after bounded termination"
            )
        with self._lock(session_id):
            state = self._load_state(session_id)
            self._refresh_interrupted_locked(state)
            return self._public_state(state)

    def export_a2a_result(
        self,
        writer_session_id: str,
        *,
        reviewer_session_id: str,
        reviewer_state_root: str | Path | None = None,
        summon_request_path: str | Path,
        output_path: str | Path,
    ) -> dict[str, Any]:
        reviewer_runtime = self
        if reviewer_state_root is not None:
            reviewer_root = Path(reviewer_state_root)
            if (
                not reviewer_root.is_absolute()
                or reviewer_root.is_symlink()
                or not reviewer_root.is_dir()
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_reviewer_state_root_invalid",
                    "reviewer state root must be an existing absolute non-symlink directory",
                )
            if reviewer_root.resolve() != self.state_root.resolve():
                reviewer_runtime = ExternalCodexRuntime(
                    reviewer_root,
                    profile_path=self.profile_path,
                )
        writer = self.result(writer_session_id)
        reviewer = reviewer_runtime.result(reviewer_session_id)
        if writer is None or reviewer is None:
            raise ExternalCodexRuntimeError(
                "a2a_review_incomplete",
                "writer and reviewer runtime results are required",
            )
        reviewer_receipt_digest = sha256_bytes(
            (
                json.dumps(
                    reviewer,
                    ensure_ascii=True,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")
        )
        admission_pair = (
            writer.get("admission_class"),
            reviewer.get("admission_class"),
        )
        if admission_pair == ("owner_contour", "owner_contour"):
            return self._export_owner_contour_a2a_result(
                writer_session_id,
                reviewer_runtime=reviewer_runtime,
                reviewer_session_id=reviewer_session_id,
                summon_request_path=summon_request_path,
                output_path=output_path,
                writer=writer,
                reviewer=reviewer,
                reviewer_receipt_digest=reviewer_receipt_digest,
            )
        if admission_pair not in {
            ("transport_study_fixture", "transport_study_fixture"),
            ("owner_contour", "transport_study_fixture"),
        }:
            raise ExternalCodexRuntimeError(
                "a2a_admission_class_invalid",
                "A2A export accepts only a transport-study pair or an owner-contour writer with its prepared read-only reviewer",
            )
        if (
            reviewer.get("status") not in {"completed", "review_required"}
            or reviewer.get("failure_code") is not None
        ):
            raise ExternalCodexRuntimeError(
                "a2a_review_runtime_failed",
                "failed or authority-blocked reviewer runtime cannot authorize A2A export",
            )
        if (
            writer.get("thread_id") is None
            or reviewer.get("thread_id") is None
            or writer["thread_id"] == reviewer["thread_id"]
            or reviewer.get("execution_posture") != "independent_review"
            or reviewer.get("task_family") != "landing_review"
        ):
            raise ExternalCodexRuntimeError(
                "a2a_review_not_independent",
                "A2A export requires a separate landing-review thread",
            )
        reviewer_report = _load_verified_json_ref(
            reviewer["report_ref"],
            label="reviewer report",
            schema_path=REPORT_SCHEMA_PATH,
        )
        writer_report = _load_verified_json_ref(
            writer["report_ref"],
            label="writer report",
            schema_path=REPORT_SCHEMA_PATH,
        )
        for label, result, report in (
            ("writer", writer, writer_report),
            ("reviewer", reviewer, reviewer_report),
        ):
            if (
                report.get("task_id") != result.get("task_id")
                or report.get("incarnation_id") != result.get("incarnation_id")
                or report.get("status") != result.get("status")
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_report_identity_mismatch",
                    f"{label} report identity/status differs from its runtime result",
                )
        review_outcomes = {
            ("completed", "proceed"): ("completed", "proceed"),
            ("review_required", "return_for_repair"): (
                "failed",
                "return_for_repair",
            ),
        }
        review_outcome = review_outcomes.get(
            (str(reviewer["status"]), str(reviewer_report["decision"]))
        )
        if review_outcome is None:
            raise ExternalCodexRuntimeError(
                "a2a_review_outcome_invalid",
                "reviewer runtime status and terminal decision are inconsistent",
            )
        with reviewer_runtime._lock(reviewer_session_id):
            reviewer_state = reviewer_runtime._load_state(reviewer_session_id)
            (
                reviewer_launch,
                reviewer_plan,
                reviewer_binding,
                reviewer_task,
                _,
                _,
            ) = reviewer_runtime._materialized_payloads(reviewer_state)
            if (
                reviewer_launch["admission_class"] != "transport_study_fixture"
                or reviewer_state.get("result_path")
                != str(
                    reviewer_runtime._session_dir(reviewer_session_id) / "result.json"
                )
                or reviewer_state.get("result_digest")
                != sha256_file(Path(str(reviewer_state["result_path"])))
                or reviewer_state.get("result_digest") != reviewer_receipt_digest
                or reviewer_state.get("incarnation_id")
                != reviewer_binding.incarnation_id
                or reviewer_state.get("task_family") != "landing_review"
                or reviewer_task.get("task_family") != "landing_review"
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_review_state_unbound",
                    "reviewer durable state is not bound to its exact result/incarnation",
                )
            review_seed_ref = reviewer_state.get("review_seed_envelope_ref")
            if not isinstance(review_seed_ref, dict):
                raise ExternalCodexRuntimeError(
                    "a2a_review_seed_required",
                    "reviewed A2A return requires one controller-issued writer seed envelope",
                )
            review_seed_envelope = _load_verified_json_ref(
                review_seed_ref,
                label="reviewer seed envelope",
                schema_path=REVIEW_SEED_ENVELOPE_SCHEMA_PATH,
            )
            launch_seed = reviewer_launch.get("workspace_projection_seed")
            if (
                not isinstance(launch_seed, dict)
                or launch_seed.get("envelope_path")
                != review_seed_ref.get("artifact_ref")
                or launch_seed.get("envelope_digest")
                != review_seed_ref.get("artifact_digest")
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_review_seed_unbound",
                    "reviewer launch and durable state name different seed envelopes",
                )
            (
                reviewer_summon_request,
                reviewer_summon_request_ref,
                reviewer_summon_schema_ref,
                reviewer_expected_outputs,
            ) = reviewer_runtime._validated_a2a_summon_request(
                state=reviewer_state,
                plan=reviewer_plan,
                binding=reviewer_binding,
                task=reviewer_task,
                request_input_id="review-summon-request",
            )
            compatibility_schema_matches = [
                item
                for item in reviewer_task["immutable_inputs"]
                if item["input_id"] == "writer-summon-request-schema"
            ]
            writer_schema_material = None
            compatibility_schema_ref = None
            if compatibility_schema_matches:
                if len(compatibility_schema_matches) != 1:
                    raise ExternalCodexRuntimeError(
                        "a2a_summon_request_unbound",
                        "reviewer has no unique controller-derived writer schema",
                    )
                compatibility_schema_material = (
                    reviewer_runtime._materialized_task_input(
                        reviewer_state,
                        "writer-summon-request-schema",
                    )
                )
                compatibility_schema_ref = compatibility_schema_material[2]
                writer_schema_material = reviewer_runtime._materialized_task_input(
                    reviewer_state,
                    "summon-request-schema",
                )
                if (
                    compatibility_schema_material[1] != writer_schema_material[1]
                    or compatibility_schema_ref.owner_repo != "abyss-stack"
                    or compatibility_schema_material[2].schema_ref
                    != writer_schema_material[2].artifact_ref
                    or compatibility_schema_material[2].schema_version
                    != SDK_SUMMON_REQUEST_SCHEMA_VERSION
                ):
                    raise ExternalCodexRuntimeError(
                        "a2a_summon_request_unbound",
                        "controller-derived writer schema differs from the active reviewer SDK schema",
                    )
        for label, ref in (
            ("writer events", writer["events_ref"]),
            ("reviewer events", reviewer["events_ref"]),
            ("writer final workspace manifest", writer["workspace_manifest_ref"]),
            (
                "reviewer final workspace manifest",
                reviewer["workspace_manifest_ref"],
            ),
            ("writer actor final manifest", writer.get("actor_final_manifest_ref")),
            ("writer actor delta", writer.get("actor_delta_ref")),
            ("reviewer actor final manifest", reviewer.get("actor_final_manifest_ref")),
            ("reviewer actor delta", reviewer.get("actor_delta_ref")),
        ):
            if not isinstance(ref, dict):
                raise ExternalCodexRuntimeError(
                    "a2a_artifact_ref_invalid",
                    f"{label} has no exact terminal artifact reference",
                )
            _verified_artifact_ref_path(ref, label=label)
        writer_actor_final = _load_verified_json_ref(
            writer["actor_final_manifest_ref"],
            label="writer actor final manifest",
            schema_path=ACTOR_MANIFEST_SCHEMA_PATH,
        )
        writer_actor_delta = _load_verified_json_ref(
            writer["actor_delta_ref"],
            label="writer actor delta",
            schema_path=ACTOR_DELTA_SCHEMA_PATH,
        )
        reviewer_actor_final = _load_verified_json_ref(
            reviewer["actor_final_manifest_ref"],
            label="reviewer actor final manifest",
            schema_path=ACTOR_MANIFEST_SCHEMA_PATH,
        )
        reviewer_actor_delta = _load_verified_json_ref(
            reviewer["actor_delta_ref"],
            label="reviewer actor delta",
            schema_path=ACTOR_DELTA_SCHEMA_PATH,
        )
        if (
            writer_actor_delta.get("final_manifest_digest")
            != canonical_digest(writer_actor_final)
            or reviewer_actor_final.get("content_entries")
            != writer_actor_final.get("content_entries")
            or reviewer_actor_final.get("private_git_digest")
            != writer_actor_final.get("private_git_digest")
            or reviewer_actor_delta.get("changes")
            or reviewer_actor_delta.get("final_manifest_digest")
            != canonical_digest(reviewer_actor_final)
        ):
            raise ExternalCodexRuntimeError(
                "a2a_projection_not_bound",
                "reviewer does not bind the exact writer actor projection and zero reviewer delta",
            )
        with self._lock(writer_session_id):
            writer_state = self._load_state(writer_session_id)
            if (
                review_seed_envelope.get("writer_session_id") != writer_session_id
                or self._review_seed_envelope_locked(writer_state)
                != review_seed_envelope
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_review_seed_unbound",
                    "reviewer seed no longer binds the exact locked writer return",
                )
            (
                writer_launch,
                writer_plan,
                writer_binding,
                writer_task,
                _,
                _,
            ) = self._materialized_payloads(writer_state)
            writer_result_path = self._session_dir(writer_session_id) / "result.json"
            if (
                writer_launch["admission_class"] != writer.get("admission_class")
                or writer_state.get("result_path") != str(writer_result_path)
                or writer_state.get("result_digest") != sha256_file(writer_result_path)
                or writer_state.get("incarnation_id") != writer_binding.incarnation_id
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_writer_state_unbound",
                    "writer durable state is not bound to its exact result/incarnation",
                )
            (
                summon_request,
                summon_request_ref,
                summon_schema_ref,
                writer_expected_outputs,
            ) = self._validated_a2a_summon_request(
                state=writer_state,
                plan=writer_plan,
                binding=writer_binding,
                task=writer_task,
                request_input_id="summon-request",
                supplied_path=summon_request_path,
                schema_material=(
                    None
                    if any(
                        item["input_id"] == "summon-request-schema"
                        for item in writer_task["immutable_inputs"]
                    )
                    else writer_schema_material
                ),
            )
            nested = summon_request["summon_request"]
            reviewer_summon_nested = reviewer_summon_request["summon_request"]
            writer_result_digest = str(writer_state["result_digest"])
            writer_report_digest = str(writer["report_ref"]["artifact_digest"])
            reviewer_inputs = {
                str(item["input_id"]): item["provenance"]["artifact_digest"]
                for item in reviewer_task["immutable_inputs"]
            }
            writer_source_manifest_digest = next(
                (
                    str(item["provenance"]["artifact_digest"])
                    for item in writer_task["immutable_inputs"]
                    if item["input_id"] == writer_launch["workspace_manifest_input_id"]
                ),
                None,
            )
            if writer_source_manifest_digest is None:
                source_before_ref = writer_state.get("source_manifest_before_ref")
                if isinstance(source_before_ref, dict):
                    writer_source_manifest_digest = str(
                        source_before_ref["artifact_digest"]
                    )
            writer_actor_final_digest = str(
                (
                    writer.get("actor_final_manifest_ref")
                    or writer["workspace_manifest_ref"]
                )["artifact_digest"]
            )
            writer_actor_delta_digest = str(
                writer["actor_delta_ref"]["artifact_digest"]
            )
            if (
                reviewer_inputs.get("writer-runtime-result") != writer_result_digest
                or reviewer_inputs.get("writer-model-report") != writer_report_digest
                or reviewer_inputs.get("review-workspace-manifest")
                != writer_source_manifest_digest
                or reviewer_inputs.get("writer-actor-final-manifest")
                != writer_actor_final_digest
                or reviewer_inputs.get("writer-actor-delta")
                != writer_actor_delta_digest
                or (
                    not any(
                        item["input_id"] == "summon-request-schema"
                        for item in writer_task["immutable_inputs"]
                    )
                    and reviewer_inputs.get("writer-summon-request-schema")
                    != summon_schema_ref.artifact_digest
                )
                or (
                    not any(
                        item["input_id"] == "summon-request-schema"
                        for item in writer_task["immutable_inputs"]
                    )
                    and (
                        compatibility_schema_ref is None
                        or compatibility_schema_ref.source_ref != writer_result_digest
                    )
                )
                or reviewer_task["parent_task_id"] != writer["task_id"]
                or reviewer_task["target_owner"] != writer_task["target_owner"]
                or reviewer_state["incarnation_id"] == writer_state["incarnation_id"]
                or nested["parent_task_id"] != writer_task["parent_task_id"]
                or reviewer_summon_nested["parent_task_id"] != writer_task["task_id"]
                or reviewer_summon_nested["reviewed_artifact_path"]
                != str(writer_result_path)
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_review_not_bound",
                    "review task/request is not bound to the exact writer result, report, final workspace manifest, owner, and parent",
                )
            returned = ["external_codex_agent_result", "independent_landing_review"]
            returned.extend(str(item) for item in writer_task["expected_artifacts"])
            returned.extend(str(item) for item in writer_report["artifact_paths"])
            unique_returned = list(dict.fromkeys(returned))
            if not set(writer_expected_outputs).issubset(unique_returned) or not set(
                reviewer_expected_outputs
            ).issubset(unique_returned):
                raise ExternalCodexRuntimeError(
                    "a2a_return_outputs_incomplete",
                    "returned artifacts do not satisfy the exact writer/reviewer summon requests",
                )
            remote_state, outcome_name = review_outcome
            output = Path(output_path)
            if not output.is_absolute():
                raise ExternalCodexRuntimeError(
                    "a2a_output_not_absolute", "A2A output path must be absolute"
                )
            if output.is_symlink():
                raise ExternalCodexRuntimeError(
                    "a2a_output_conflict", "A2A output must not be a symbolic link"
                )
            with reviewer_runtime._lock(reviewer_session_id):
                current_reviewer_state = reviewer_runtime._load_state(
                    reviewer_session_id
                )
                expected_reviewer_result_path = (
                    reviewer_runtime._session_dir(reviewer_session_id) / "result.json"
                )
                current_result_path = current_reviewer_state.get("result_path")
                if (
                    current_result_path != str(expected_reviewer_result_path)
                    or expected_reviewer_result_path.is_symlink()
                    or not expected_reviewer_result_path.is_file()
                    or current_reviewer_state.get("result_digest")
                    != reviewer_receipt_digest
                    or sha256_file(expected_reviewer_result_path)
                    != reviewer_receipt_digest
                    or current_reviewer_state.get("incarnation_id")
                    != reviewer_binding.incarnation_id
                    or current_reviewer_state.get("review_seed_envelope_ref")
                    != review_seed_ref
                    or current_reviewer_state.get("task_family") != "landing_review"
                    or reviewer.get("task_family") != "landing_review"
                    or reviewer_task.get("task_family") != "landing_review"
                ):
                    raise ExternalCodexRuntimeError(
                        "a2a_review_state_unbound",
                        "reviewer changed before its A2A export became durable",
                    )
                _verify_a2a_export_snapshot(
                    (
                        (
                            "writer result",
                            {
                                "artifact_ref": str(writer_result_path),
                                "artifact_digest": str(writer_state["result_digest"]),
                            },
                        ),
                        ("writer report", writer["report_ref"]),
                        ("writer events", writer["events_ref"]),
                        (
                            "writer final workspace manifest",
                            writer["workspace_manifest_ref"],
                        ),
                        (
                            "writer actor final manifest",
                            writer["actor_final_manifest_ref"],
                        ),
                        ("writer actor delta", writer["actor_delta_ref"]),
                        ("reviewer report", reviewer["report_ref"]),
                        ("reviewer events", reviewer["events_ref"]),
                        (
                            "reviewer final workspace manifest",
                            reviewer["workspace_manifest_ref"],
                        ),
                        (
                            "reviewer actor final manifest",
                            reviewer["actor_final_manifest_ref"],
                        ),
                        ("reviewer actor delta", reviewer["actor_delta_ref"]),
                        ("review seed envelope", review_seed_ref),
                    )
                )
                current_seed = _load_verified_json_ref(
                    review_seed_ref,
                    label="reviewer seed envelope",
                    schema_path=REVIEW_SEED_ENVELOPE_SCHEMA_PATH,
                )
                if current_seed != review_seed_envelope:
                    raise ExternalCodexRuntimeError(
                        "a2a_review_seed_unbound",
                        "reviewer seed bytes changed before A2A publication",
                    )
                current_writer_schema_material = None
                if not any(
                    item["input_id"] == "summon-request-schema"
                    for item in writer_task["immutable_inputs"]
                ):
                    current_compatibility_schema = (
                        reviewer_runtime._materialized_task_input(
                            current_reviewer_state,
                            "writer-summon-request-schema",
                        )
                    )
                    current_writer_schema_material = (
                        reviewer_runtime._materialized_task_input(
                            current_reviewer_state,
                            "summon-request-schema",
                        )
                    )
                    if (
                        current_compatibility_schema[1]
                        != current_writer_schema_material[1]
                        or current_compatibility_schema[2].owner_repo != "abyss-stack"
                        or current_compatibility_schema[2].source_ref
                        != writer_result_digest
                        or current_compatibility_schema[2].schema_ref
                        != current_writer_schema_material[2].artifact_ref
                        or current_compatibility_schema[2].schema_version
                        != SDK_SUMMON_REQUEST_SCHEMA_VERSION
                    ):
                        raise ExternalCodexRuntimeError(
                            "a2a_summon_request_unbound",
                            "controller-derived writer schema changed before A2A publication",
                        )
                (
                    current_summon_request,
                    current_summon_request_ref,
                    current_summon_schema_ref,
                    _,
                ) = self._validated_a2a_summon_request(
                    state=writer_state,
                    plan=writer_plan,
                    binding=writer_binding,
                    task=writer_task,
                    request_input_id="summon-request",
                    supplied_path=summon_request_path,
                    schema_material=current_writer_schema_material,
                )
                (
                    current_review_summon_request,
                    current_review_summon_request_ref,
                    current_review_summon_schema_ref,
                    _,
                ) = reviewer_runtime._validated_a2a_summon_request(
                    state=current_reviewer_state,
                    plan=reviewer_plan,
                    binding=reviewer_binding,
                    task=reviewer_task,
                    request_input_id="review-summon-request",
                )
                if (
                    current_summon_request != summon_request
                    or current_summon_request_ref != summon_request_ref
                    or current_summon_schema_ref != summon_schema_ref
                    or current_review_summon_request != reviewer_summon_request
                    or current_review_summon_request_ref != reviewer_summon_request_ref
                    or current_review_summon_schema_ref != reviewer_summon_schema_ref
                ):
                    raise ExternalCodexRuntimeError(
                        "a2a_summon_request_unbound",
                        "summon request bytes changed before A2A publication",
                    )
                payload = {
                    "reviewed": True,
                    "review_status": "reviewed",
                    "review_outcome": outcome_name,
                    "reviewer_status": reviewer["status"],
                    "reviewer_decision": reviewer_report["decision"],
                    "reviewed_artifact_path": str(writer_result_path),
                    "evidence_digests": {
                        "writer_result": writer_result_digest,
                        "writer_report": writer_report_digest,
                        "reviewer_result": str(current_reviewer_state["result_digest"]),
                        "reviewer_report": str(
                            reviewer["report_ref"]["artifact_digest"]
                        ),
                        "writer_workspace_manifest": str(
                            writer["workspace_manifest_ref"]["artifact_digest"]
                        ),
                        "reviewer_workspace_manifest": str(
                            reviewer["workspace_manifest_ref"]["artifact_digest"]
                        ),
                        "writer_actor_final_manifest": writer_actor_final_digest,
                        "writer_actor_delta": writer_actor_delta_digest,
                        "reviewer_actor_final_manifest": str(
                            reviewer["actor_final_manifest_ref"]["artifact_digest"]
                        ),
                        "reviewer_actor_delta": str(
                            reviewer["actor_delta_ref"]["artifact_digest"]
                        ),
                        "review_seed_envelope": str(review_seed_ref["artifact_digest"]),
                        "summon_request": current_summon_request_ref.artifact_digest,
                        "summon_request_schema": current_summon_schema_ref.artifact_digest,
                        "review_summon_request": current_review_summon_request_ref.artifact_digest,
                        "review_summon_request_schema": current_review_summon_schema_ref.artifact_digest,
                    },
                    "summon_request_ref": current_summon_request_ref.model_dump(
                        mode="json"
                    ),
                    "review_summon_request_ref": current_review_summon_request_ref.model_dump(
                        mode="json"
                    ),
                    "remote_task": {
                        "task_id": writer["task_id"],
                        "state": remote_state,
                        "agent_id": writer_state["incarnation_id"],
                        "endpoint": f"codex://local/{writer['thread_id']}",
                        "returned_artifacts": unique_returned,
                        "context_id": writer["thread_id"],
                        "parent_task_id": nested["parent_task_id"],
                        "artifact_refs": [
                            writer["report_ref"]["artifact_ref"],
                            reviewer["report_ref"]["artifact_ref"],
                            writer["events_ref"]["artifact_ref"],
                            str(writer_result_path),
                        ],
                        "message_refs": [reviewer["events_ref"]["artifact_ref"]],
                    },
                }
                encoded = (
                    json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2)
                    + "\n"
                ).encode("utf-8")
                if output.exists() and read_bounded(output) != encoded:
                    raise ExternalCodexRuntimeError(
                        "a2a_output_conflict",
                        "A2A output already contains different bytes",
                    )
                _atomic_write_bytes(output, encoded)
            return {
                "child_task_result": payload,
                "artifact_ref": _artifact_ref(output),
                "writer_thread_id": writer["thread_id"],
                "reviewer_thread_id": reviewer["thread_id"],
            }

    def _export_owner_contour_a2a_result(
        self,
        writer_session_id: str,
        *,
        reviewer_runtime: ExternalCodexRuntime,
        reviewer_session_id: str,
        summon_request_path: str | Path,
        output_path: str | Path,
        writer: Mapping[str, Any],
        reviewer: Mapping[str, Any],
        reviewer_receipt_digest: str,
    ) -> dict[str, Any]:
        """Export one role-first review bound by exact immutable writer evidence."""

        if (
            reviewer.get("status") not in {"completed", "review_required"}
            or reviewer.get("failure_code") is not None
        ):
            raise ExternalCodexRuntimeError(
                "a2a_review_runtime_failed",
                "failed or authority-blocked reviewer runtime cannot authorize A2A export",
            )
        if (
            writer.get("thread_id") is None
            or reviewer.get("thread_id") is None
            or writer["thread_id"] == reviewer["thread_id"]
            or reviewer.get("execution_posture") != "independent_review"
        ):
            raise ExternalCodexRuntimeError(
                "a2a_review_not_independent",
                "A2A export requires a separate independent-review thread",
            )

        reviewer_report = _load_verified_json_ref(
            reviewer["report_ref"],
            label="reviewer report",
            schema_path=REPORT_SCHEMA_PATH,
        )
        writer_report = _load_verified_json_ref(
            writer["report_ref"],
            label="writer report",
            schema_path=REPORT_SCHEMA_PATH,
        )
        for label, result, report in (
            ("writer", writer, writer_report),
            ("reviewer", reviewer, reviewer_report),
        ):
            if (
                report.get("task_id") != result.get("task_id")
                or report.get("incarnation_id") != result.get("incarnation_id")
                or report.get("status") != result.get("status")
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_report_identity_mismatch",
                    f"{label} report identity/status differs from its runtime result",
                )
        review_outcome = {
            ("completed", "proceed"): ("completed", "proceed"),
            ("review_required", "return_for_repair"): (
                "failed",
                "return_for_repair",
            ),
        }.get((str(reviewer["status"]), str(reviewer_report["decision"])))
        if review_outcome is None:
            raise ExternalCodexRuntimeError(
                "a2a_review_outcome_invalid",
                "reviewer runtime status and terminal decision are inconsistent",
            )

        with reviewer_runtime._lock(reviewer_session_id):
            reviewer_state = reviewer_runtime._load_state(reviewer_session_id)
            (
                reviewer_launch,
                reviewer_plan,
                reviewer_binding,
                reviewer_task,
                _,
                _,
            ) = reviewer_runtime._materialized_payloads(reviewer_state)
            expected_reviewer_result_path = (
                reviewer_runtime._session_dir(reviewer_session_id) / "result.json"
            )
            if (
                reviewer_launch["admission_class"] != "owner_contour"
                or reviewer_state.get("result_path")
                != str(expected_reviewer_result_path)
                or reviewer_state.get("result_digest") != reviewer_receipt_digest
                or sha256_file(expected_reviewer_result_path)
                != reviewer_receipt_digest
                or reviewer_state.get("incarnation_id")
                != reviewer_binding.incarnation_id
                or reviewer_state.get("task_family")
                != reviewer_task.get("task_family")
                or reviewer_state.get("task_family")
                != reviewer.get("task_family")
                or reviewer_task.get("execution_posture")
                != "independent_review"
                or reviewer_binding.permission_posture.sandbox_mode != "read_only"
                or reviewer_binding.permission_posture.external_effects
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_review_state_unbound",
                    "role-first reviewer state is not exact, independent, and read-only",
                )
            (
                reviewer_summon_request,
                reviewer_summon_request_ref,
                reviewer_summon_schema_ref,
                reviewer_expected_outputs,
            ) = reviewer_runtime._validated_a2a_summon_request(
                state=reviewer_state,
                plan=reviewer_plan,
                binding=reviewer_binding,
                task=reviewer_task,
                request_input_id="review-summon-request",
            )
            reviewer_schema_material = reviewer_runtime._materialized_task_input(
                reviewer_state,
                "summon-request-schema",
            )

        for label, ref in (
            ("writer events", writer["events_ref"]),
            ("reviewer events", reviewer["events_ref"]),
            ("writer final workspace manifest", writer["workspace_manifest_ref"]),
            (
                "reviewer final workspace manifest",
                reviewer["workspace_manifest_ref"],
            ),
            ("writer actor final manifest", writer.get("actor_final_manifest_ref")),
            ("writer actor delta", writer.get("actor_delta_ref")),
            ("reviewer actor final manifest", reviewer.get("actor_final_manifest_ref")),
            ("reviewer actor delta", reviewer.get("actor_delta_ref")),
        ):
            if not isinstance(ref, dict):
                raise ExternalCodexRuntimeError(
                    "a2a_artifact_ref_invalid",
                    f"{label} has no exact terminal artifact reference",
                )
            _verified_artifact_ref_path(ref, label=label)
        writer_actor_final = _load_verified_json_ref(
            writer["actor_final_manifest_ref"],
            label="writer actor final manifest",
            schema_path=ACTOR_MANIFEST_SCHEMA_PATH,
        )
        reviewer_actor_final = _load_verified_json_ref(
            reviewer["actor_final_manifest_ref"],
            label="reviewer actor final manifest",
            schema_path=ACTOR_MANIFEST_SCHEMA_PATH,
        )
        reviewer_actor_delta = _load_verified_json_ref(
            reviewer["actor_delta_ref"],
            label="reviewer actor delta",
            schema_path=ACTOR_DELTA_SCHEMA_PATH,
        )
        if (
            reviewer_actor_delta.get("changes")
            or reviewer_actor_delta.get("final_manifest_digest")
            != canonical_digest(reviewer_actor_final)
        ):
            raise ExternalCodexRuntimeError(
                "a2a_projection_not_bound",
                "role-first reviewer must return a zero-delta read-only projection",
            )

        writer_output_digests: set[str] = set()
        entries = {
            str(item.get("path")): item
            for item in writer_actor_final.get("content_entries", [])
            if isinstance(item, dict)
        }
        for artifact_path in writer_report["artifact_paths"]:
            entry = entries.get(str(artifact_path))
            digest = entry.get("sha256") if isinstance(entry, dict) else None
            if not isinstance(digest, str) or not digest.startswith("sha256:"):
                raise ExternalCodexRuntimeError(
                    "a2a_writer_output_unbound",
                    "writer report artifact has no exact actor-manifest digest",
                )
            writer_output_digests.add(digest)

        with self._lock(writer_session_id):
            writer_state = self._load_state(writer_session_id)
            (
                writer_launch,
                writer_plan,
                writer_binding,
                writer_task,
                _,
                _,
            ) = self._materialized_payloads(writer_state)
            writer_result_path = self._session_dir(writer_session_id) / "result.json"
            if (
                writer_launch["admission_class"] != "owner_contour"
                or writer_state.get("result_path") != str(writer_result_path)
                or writer_state.get("result_digest") != sha256_file(writer_result_path)
                or writer_state.get("incarnation_id")
                != writer_binding.incarnation_id
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_writer_state_unbound",
                    "writer durable state is not bound to its exact result/incarnation",
                )
            (
                summon_request,
                summon_request_ref,
                summon_schema_ref,
                writer_expected_outputs,
            ) = self._validated_a2a_summon_request(
                state=writer_state,
                plan=writer_plan,
                binding=writer_binding,
                task=writer_task,
                request_input_id="summon-request",
                supplied_path=summon_request_path,
                schema_material=(
                    None
                    if any(
                        item["input_id"] == "summon-request-schema"
                        for item in writer_task["immutable_inputs"]
                    )
                    else reviewer_schema_material
                ),
            )
            nested = summon_request["summon_request"]
            reviewer_nested = reviewer_summon_request["summon_request"]
            reviewer_inputs = {
                str(item["input_id"]): str(
                    item["provenance"]["artifact_digest"]
                )
                for item in reviewer_task["immutable_inputs"]
            }
            reviewer_input_digests = set(reviewer_inputs.values())
            if (
                reviewer_inputs.get("writer-result")
                != writer_state["result_digest"]
                or reviewer_inputs.get("writer-report")
                != writer["report_ref"]["artifact_digest"]
                or reviewer_inputs.get("writer-task")
                != writer_launch["task"]["digest"]
                or not writer_output_digests.issubset(reviewer_input_digests)
                or reviewer_task["parent_task_id"] != writer["task_id"]
                or reviewer_task["target_owner"] != writer_task["target_owner"]
                or reviewer_state["incarnation_id"]
                == writer_state["incarnation_id"]
                or nested["parent_task_id"] != writer_task["parent_task_id"]
                or reviewer_nested["parent_task_id"] != writer_task["task_id"]
                or reviewer_nested["reviewed_artifact_path"]
                != str(writer_result_path)
            ):
                raise ExternalCodexRuntimeError(
                    "a2a_review_not_bound",
                    "role-first review is not bound to the exact writer task, result, report, outputs, owner, and parent",
                )

            returned = ["external_codex_agent_result"]
            returned.extend(str(item) for item in writer_task["expected_artifacts"])
            returned.extend(str(item) for item in writer_report["artifact_paths"])
            returned.extend(str(item) for item in reviewer_expected_outputs)
            unique_returned = list(dict.fromkeys(returned))
            if not set(writer_expected_outputs).issubset(unique_returned) or not set(
                reviewer_expected_outputs
            ).issubset(unique_returned):
                raise ExternalCodexRuntimeError(
                    "a2a_return_outputs_incomplete",
                    "returned artifacts do not satisfy the exact writer/reviewer summon requests",
                )

            output = Path(output_path)
            if not output.is_absolute():
                raise ExternalCodexRuntimeError(
                    "a2a_output_not_absolute", "A2A output path must be absolute"
                )
            if output.is_symlink():
                raise ExternalCodexRuntimeError(
                    "a2a_output_conflict", "A2A output must not be a symbolic link"
                )
            with reviewer_runtime._lock(reviewer_session_id):
                current_reviewer_state = reviewer_runtime._load_state(
                    reviewer_session_id
                )
                current_result_path = current_reviewer_state.get("result_path")
                if (
                    current_result_path != str(expected_reviewer_result_path)
                    or expected_reviewer_result_path.is_symlink()
                    or not expected_reviewer_result_path.is_file()
                    or current_reviewer_state.get("result_digest")
                    != reviewer_receipt_digest
                    or sha256_file(expected_reviewer_result_path)
                    != reviewer_receipt_digest
                    or current_reviewer_state.get("incarnation_id")
                    != reviewer_binding.incarnation_id
                    or current_reviewer_state.get("task_family")
                    != reviewer_task.get("task_family")
                ):
                    raise ExternalCodexRuntimeError(
                        "a2a_review_state_unbound",
                        "role-first reviewer changed before A2A export became durable",
                    )
                _verify_a2a_export_snapshot(
                    (
                        ("writer report", writer["report_ref"]),
                        ("writer events", writer["events_ref"]),
                        (
                            "writer final workspace manifest",
                            writer["workspace_manifest_ref"],
                        ),
                        (
                            "writer actor final manifest",
                            writer["actor_final_manifest_ref"],
                        ),
                        ("writer actor delta", writer["actor_delta_ref"]),
                        ("reviewer report", reviewer["report_ref"]),
                        ("reviewer events", reviewer["events_ref"]),
                        (
                            "reviewer final workspace manifest",
                            reviewer["workspace_manifest_ref"],
                        ),
                        (
                            "reviewer actor final manifest",
                            reviewer["actor_final_manifest_ref"],
                        ),
                        ("reviewer actor delta", reviewer["actor_delta_ref"]),
                    )
                )
                (
                    current_summon_request,
                    current_summon_request_ref,
                    current_summon_schema_ref,
                    _,
                ) = self._validated_a2a_summon_request(
                    state=writer_state,
                    plan=writer_plan,
                    binding=writer_binding,
                    task=writer_task,
                    request_input_id="summon-request",
                    supplied_path=summon_request_path,
                    schema_material=(
                        None
                        if any(
                            item["input_id"] == "summon-request-schema"
                            for item in writer_task["immutable_inputs"]
                        )
                        else reviewer_runtime._materialized_task_input(
                            current_reviewer_state,
                            "summon-request-schema",
                        )
                    ),
                )
                (
                    current_review_summon_request,
                    current_review_summon_request_ref,
                    current_review_summon_schema_ref,
                    _,
                ) = reviewer_runtime._validated_a2a_summon_request(
                    state=current_reviewer_state,
                    plan=reviewer_plan,
                    binding=reviewer_binding,
                    task=reviewer_task,
                    request_input_id="review-summon-request",
                )
                if (
                    current_summon_request != summon_request
                    or current_summon_request_ref != summon_request_ref
                    or current_summon_schema_ref != summon_schema_ref
                    or current_review_summon_request != reviewer_summon_request
                    or current_review_summon_request_ref
                    != reviewer_summon_request_ref
                    or current_review_summon_schema_ref
                    != reviewer_summon_schema_ref
                ):
                    raise ExternalCodexRuntimeError(
                        "a2a_summon_request_unbound",
                        "summon request bytes changed before A2A publication",
                    )
                remote_state, outcome_name = review_outcome
                payload = {
                    "reviewed": True,
                    "review_status": "reviewed",
                    "review_binding_mode": "owner_contour_immutable_evidence",
                    "review_outcome": outcome_name,
                    "reviewer_status": reviewer["status"],
                    "reviewer_decision": reviewer_report["decision"],
                    "reviewed_artifact_path": str(writer_result_path),
                    "evidence_digests": {
                        "writer_result": str(writer_state["result_digest"]),
                        "writer_report": str(
                            writer["report_ref"]["artifact_digest"]
                        ),
                        "writer_outputs": sorted(writer_output_digests),
                        "reviewer_result": str(
                            current_reviewer_state["result_digest"]
                        ),
                        "reviewer_report": str(
                            reviewer["report_ref"]["artifact_digest"]
                        ),
                        "writer_actor_final_manifest": str(
                            writer["actor_final_manifest_ref"]["artifact_digest"]
                        ),
                        "reviewer_actor_final_manifest": str(
                            reviewer["actor_final_manifest_ref"]["artifact_digest"]
                        ),
                        "reviewer_actor_delta": str(
                            reviewer["actor_delta_ref"]["artifact_digest"]
                        ),
                        "summon_request": current_summon_request_ref.artifact_digest,
                        "summon_request_schema": current_summon_schema_ref.artifact_digest,
                        "review_summon_request": current_review_summon_request_ref.artifact_digest,
                        "review_summon_request_schema": current_review_summon_schema_ref.artifact_digest,
                    },
                    "summon_request_ref": current_summon_request_ref.model_dump(
                        mode="json"
                    ),
                    "review_summon_request_ref": current_review_summon_request_ref.model_dump(
                        mode="json"
                    ),
                    "remote_task": {
                        "task_id": writer["task_id"],
                        "state": remote_state,
                        "agent_id": writer_state["incarnation_id"],
                        "endpoint": f"codex://local/{writer['thread_id']}",
                        "returned_artifacts": unique_returned,
                        "context_id": writer["thread_id"],
                        "parent_task_id": nested["parent_task_id"],
                        "artifact_refs": [
                            writer["report_ref"]["artifact_ref"],
                            reviewer["report_ref"]["artifact_ref"],
                            writer["events_ref"]["artifact_ref"],
                            str(writer_result_path),
                        ],
                        "message_refs": [reviewer["events_ref"]["artifact_ref"]],
                    },
                }
                encoded = (
                    json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2)
                    + "\n"
                ).encode("utf-8")
                if output.exists() and read_bounded(output) != encoded:
                    raise ExternalCodexRuntimeError(
                        "a2a_output_conflict",
                        "A2A output already contains different bytes",
                    )
                _atomic_write_bytes(output, encoded)
            return {
                "child_task_result": payload,
                "artifact_ref": _artifact_ref(output),
                "writer_thread_id": writer["thread_id"],
                "reviewer_thread_id": reviewer["thread_id"],
            }


class ExternalCodexParentReentry:
    """Narrow event-driven Sol yield and exact-thread re-entry bridge.

    This bridge does not schedule work or infer model fit.  It materializes one
    SDK-owned child continuation, lets one external parent Sol turn end, and
    later accepts one immutable child terminal event.  Only the wake policy
    already bound to that child may cause an exact parent-thread resume.
    """

    def __init__(
        self,
        state_root: str | Path,
        *,
        profile_path: str | Path = PROFILE_PATH,
    ) -> None:
        self.state_root = Path(state_root)
        if not self.state_root.is_absolute() or self.state_root.is_symlink():
            raise ExternalCodexRuntimeError(
                "invalid_state_root",
                "external Codex re-entry state root must be absolute and non-symbolic",
            )
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.state_root.is_dir():
            raise ExternalCodexRuntimeError(
                "invalid_state_root", "external Codex re-entry root is not a directory"
            )
        self.profile_path = Path(profile_path)
        self.profile = load_json(self.profile_path, label="runtime profile")
        validate_json(self.profile, PROFILE_SCHEMA_PATH, label="runtime profile")
        validate_structured_output_schema(load_schema(PARENT_YIELD_SCHEMA_PATH))
        validate_structured_output_schema(load_schema(PARENT_REENTRY_SCHEMA_PATH))

    def _reentry_dir(self, reentry_id: str) -> Path:
        return self.state_root / "reentries" / _session_token(reentry_id)

    def _state_path(self, reentry_id: str) -> Path:
        return self._reentry_dir(reentry_id) / "state.json"

    def _events_path(self, reentry_id: str) -> Path:
        return self._reentry_dir(reentry_id) / "events.jsonl"

    @contextmanager
    def _lock(self, reentry_id: str) -> Iterator[None]:
        root = self._reentry_dir(reentry_id)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (root / "reentry.lock").open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _append_event(
        self,
        reentry_id: str,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        significance: str,
    ) -> dict[str, Any]:
        path = self._events_path(reentry_id)
        sequence = 0
        if path.exists():
            raw = read_bounded(path)
            sequence = len([line for line in raw.splitlines() if line.strip()])
        event = {
            "schema_version": "abyss_stack_external_codex_reentry_event_v1",
            "sequence": sequence,
            "observed_at": iso_now(),
            "reentry_id": reentry_id,
            "event_type": event_type,
            "significance": significance,
            "payload": dict(payload),
        }
        _append_jsonl(path, event)
        return event

    def _load_state(self, reentry_id: str) -> dict[str, Any]:
        path = self._state_path(reentry_id)
        if not path.is_file():
            raise ExternalCodexRuntimeError(
                "reentry_not_found", f"parent re-entry is unknown: {reentry_id}"
            )
        state = load_json(path, label="parent re-entry state")
        validate_json(state, REENTRY_STATE_SCHEMA_PATH, label="parent re-entry state")
        if (
            state.get("schema_version")
            not in {
                LEGACY_REENTRY_STATE_SCHEMA_VERSION,
                REENTRY_STATE_SCHEMA_VERSION,
            }
            or state.get("reentry_id") != reentry_id
        ):
            raise ExternalCodexRuntimeError(
                "reentry_state_invalid", "parent re-entry state identity differs"
            )
        expected_events_path = self._events_path(reentry_id)
        recorded_events_path = Path(str(state["events_ref"]["artifact_ref"]))
        if recorded_events_path != expected_events_path:
            raise ExternalCodexRuntimeError(
                "reentry_state_invalid",
                "parent re-entry state points outside its canonical event stream",
            )
        try:
            _verified_artifact_ref_path(
                state["events_ref"], label="re-entry event stream"
            )
        except ExternalCodexRuntimeError as exc:
            if exc.code != "a2a_artifact_drift":
                raise
            state = self._recover_appended_events(state)
        return state

    def _recover_appended_events(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """Recover a crash between one durable event append and state save.

        Recovery admits only an intact, digest-matching prior JSONL prefix plus
        one or more structurally valid, contiguous events for this re-entry.
        Rewrites, truncation, partial records, or another identity still fail
        closed.
        """

        reentry_id = str(state["reentry_id"])
        path = self._events_path(reentry_id)
        raw = read_bounded(path)
        if not raw.endswith(b"\n"):
            raise ExternalCodexRuntimeError(
                "reentry_event_recovery_failed",
                "re-entry event stream ends with a partial record",
            )
        lines = raw.splitlines(keepends=True)
        recorded_digest = str(state["events_ref"]["artifact_digest"])
        prefix_count: int | None = None
        prefix = b""
        for index, line in enumerate(lines):
            prefix += line
            if sha256_bytes(prefix) == recorded_digest:
                prefix_count = index + 1
        if prefix_count is None or prefix_count >= len(lines):
            raise ExternalCodexRuntimeError(
                "reentry_event_recovery_failed",
                "re-entry event stream is not a strict extension of its recorded prefix",
            )
        events: list[dict[str, Any]] = []
        for sequence, line in enumerate(lines):
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ExternalCodexRuntimeError(
                    "reentry_event_recovery_failed",
                    f"re-entry event line {sequence + 1} is invalid",
                ) from exc
            if (
                not isinstance(event, dict)
                or event.get("schema_version")
                != "abyss_stack_external_codex_reentry_event_v1"
                or event.get("sequence") != sequence
                or event.get("reentry_id") != reentry_id
                or not isinstance(event.get("event_type"), str)
                or not event["event_type"]
                or not isinstance(event.get("significance"), str)
                or not event["significance"]
                or not isinstance(event.get("payload"), dict)
            ):
                raise ExternalCodexRuntimeError(
                    "reentry_event_recovery_failed",
                    f"re-entry event line {sequence + 1} is not a contiguous owned event",
                )
            try:
                parse_timestamp(str(event["observed_at"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ExternalCodexRuntimeError(
                    "reentry_event_recovery_failed",
                    f"re-entry event line {sequence + 1} has no valid observation time",
                ) from exc
            events.append(event)
        recovered = dict(state)
        for event in events[prefix_count:]:
            payload = event["payload"]
            event_type = event["event_type"]
            if event_type == "external_parent.inference_yielded":
                turn = payload.get("turn")
                turn_events_ref = (
                    turn.get("events_ref") if isinstance(turn, dict) else None
                )
                turn_output_ref = (
                    turn.get("output_ref") if isinstance(turn, dict) else None
                )
                if (
                    recovered.get("status") != "yielding"
                    or not isinstance(turn, dict)
                    or turn.get("kind") != "yield"
                    or not isinstance(turn.get("thread_id"), str)
                    or not turn["thread_id"]
                    or not isinstance(turn_events_ref, dict)
                    or not isinstance(turn_output_ref, dict)
                    or payload.get("thread_id") != turn["thread_id"]
                    or payload.get("turn_output_digest")
                    != turn_output_ref.get("artifact_digest")
                ):
                    raise ExternalCodexRuntimeError(
                        "reentry_event_recovery_failed",
                        "yield event lacks its exact semantic turn delta",
                    )
                _verified_artifact_ref_path(
                    turn_events_ref, label="recovered parent yield events"
                )
                _verified_artifact_ref_path(
                    turn_output_ref, label="recovered parent yield output"
                )
                recovered["parent_thread_id"] = turn["thread_id"]
                recovered["turns"] = [turn]
                recovered["status"] = "yielded"
            elif event_type == "external_parent.wait_registered":
                if (
                    recovered.get("status") != "yielded"
                    or payload.get("condition_id")
                    != recovered["expected_wake"]["condition_id"]
                    or payload.get("event_kind")
                    != recovered["expected_wake"]["event_kind"]
                    or payload.get("child_task_id") != recovered["child_task_id"]
                    or payload.get("child_incarnation_id")
                    != recovered["child_incarnation_id"]
                ):
                    raise ExternalCodexRuntimeError(
                        "reentry_event_recovery_failed",
                        "wait event differs from the durable parent obligation",
                    )
                recovered["status"] = "waiting"
            elif event_type == "external_parent.child_event_admitted":
                child_result_ref = payload.get("child_result_ref")
                wake_evaluation = payload.get("wake_evaluation")
                if (
                    recovered.get("status") != "waiting"
                    or recovered.get("child_result_ref") is not None
                    or not isinstance(child_result_ref, dict)
                    or not isinstance(wake_evaluation, dict)
                ):
                    raise ExternalCodexRuntimeError(
                        "reentry_event_recovery_failed",
                        "admitted child event lacks its semantic state delta",
                    )
                _verified_artifact_ref_path(
                    child_result_ref, label="recovered child result"
                )
                if wake_evaluation.get("wake_parent") is True:
                    distilled_return_ref = payload.get("distilled_return_ref")
                    if not isinstance(distilled_return_ref, dict):
                        raise ExternalCodexRuntimeError(
                            "reentry_event_recovery_failed",
                            "waking child event lacks its immutable distilled return",
                        )
                    distilled_path = _verified_artifact_ref_path(
                        distilled_return_ref,
                        label="recovered distilled child return",
                    )
                    if distilled_path != (
                        self._reentry_dir(reentry_id) / "distilled-child-return.json"
                    ):
                        raise ExternalCodexRuntimeError(
                            "reentry_event_recovery_failed",
                            "waking child event names a non-canonical distilled return",
                        )
                recovered["child_result_ref"] = child_result_ref
                recovered["wake_evaluation"] = wake_evaluation
                child_result = self._load_admitted_child_snapshot(recovered)
                if wake_evaluation.get("wake_parent") is True:
                    self._load_admitted_distilled_return(
                        reentry_id,
                        recovered,
                        child_result,
                    )
            elif event_type == "external_parent.reentry_started":
                distilled_return_ref = payload.get("distilled_return_ref")
                wake_evaluation = recovered.get("wake_evaluation")
                if (
                    recovered.get("status") != "waiting"
                    or not isinstance(recovered.get("child_result_ref"), dict)
                    or not isinstance(wake_evaluation, dict)
                    or wake_evaluation.get("wake_parent") is not True
                    or payload.get("parent_thread_id")
                    != recovered.get("parent_thread_id")
                    or not isinstance(distilled_return_ref, dict)
                ):
                    raise ExternalCodexRuntimeError(
                        "reentry_event_recovery_failed",
                        "re-entry start event differs from the admitted parent wake",
                    )
                distilled_path = _verified_artifact_ref_path(
                    distilled_return_ref,
                    label="recovered re-entry distilled return",
                )
                if distilled_path != (
                    self._reentry_dir(reentry_id) / "distilled-child-return.json"
                ):
                    raise ExternalCodexRuntimeError(
                        "reentry_event_recovery_failed",
                        "re-entry start names a non-canonical distilled return",
                    )
                recovered["status"] = "reentering"
            elif event_type == "external_parent.wake_filtered":
                recovered["status"] = "filtered"
            elif event_type == "external_parent.reentry_failed":
                recovered["status"] = "failed"
            elif event_type == "external_parent.reentry_completed":
                turn = payload.get("turn")
                result_ref = payload.get("reentry_result_ref")
                if (
                    not isinstance(turn, dict)
                    or turn.get("kind") != "reentry"
                    or turn.get("thread_id") != recovered["parent_thread_id"]
                    or not isinstance(result_ref, dict)
                    or turn.get("output_ref") != result_ref
                ):
                    raise ExternalCodexRuntimeError(
                        "reentry_event_recovery_failed",
                        "completed re-entry event lacks its semantic state delta",
                    )
                _verified_artifact_ref_path(
                    result_ref, label="recovered parent re-entry result"
                )
                recovered["turns"] = [recovered["turns"][0], turn]
                recovered["reentry_result_ref"] = result_ref
                recovered["status"] = "reentered"
        recovered["updated_at"] = iso_now()
        recovered["events_ref"] = _artifact_ref(path)
        validate_json(
            recovered,
            REENTRY_STATE_SCHEMA_PATH,
            label="recovered parent re-entry state",
        )
        _atomic_write_json(self._state_path(reentry_id), recovered, mode=0o600)
        return recovered

    def _save_state(self, state: Mapping[str, Any]) -> None:
        candidate = dict(state)
        candidate["updated_at"] = iso_now()
        candidate["events_ref"] = _artifact_ref(
            self._events_path(str(candidate["reentry_id"]))
        )
        validate_json(
            candidate, REENTRY_STATE_SCHEMA_PATH, label="parent re-entry state"
        )
        _atomic_write_json(
            self._state_path(str(candidate["reentry_id"])), candidate, mode=0o600
        )

    @staticmethod
    def _artifact_copy(
        ref: Mapping[str, Any],
        *,
        label: str,
        destination: Path,
    ) -> dict[str, Any]:
        source = _verified_artifact_ref_path(ref, label=label)
        _atomic_write_bytes(destination, read_bounded(source), mode=0o400)
        copied = dict(ref)
        copied["artifact_ref"] = str(destination)
        if sha256_file(destination) != copied["artifact_digest"]:
            raise ExternalCodexRuntimeError(
                "reentry_input_copy_failed", f"materialized {label} digest differs"
            )
        return copied

    def _materialize_obligation(
        self, obligation_path: Path, obligation: Mapping[str, Any]
    ) -> tuple[Path, dict[str, Any]]:
        root = self._reentry_dir(str(obligation["reentry_id"])) / "inputs"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        materialized = dict(obligation)
        for key, name in (
            ("parent_model_realization_ref", "parent-model-realization.json"),
            ("parent_role_ref", "parent-role.json"),
            ("child_task_ref", "child-task.json"),
            ("child_incarnation_binding_ref", "child-incarnation-binding.json"),
        ):
            materialized[key] = self._artifact_copy(
                obligation[key], label=key, destination=root / name
            )
        materialized_path = root / "obligation.json"
        _atomic_write_json(materialized_path, materialized, mode=0o400)
        validate_json(
            materialized,
            PARENT_OBLIGATION_SCHEMA_PATH,
            label="materialized parent obligation",
        )
        return materialized_path, materialized

    def _validate_obligation(
        self, obligation: Mapping[str, Any]
    ) -> tuple[dict[str, Any], IncarnationBinding, dict[str, Any]]:
        task = _load_verified_json_ref(
            obligation["child_task_ref"],
            label="child task",
            schema_path=TASK_SCHEMA_PATH,
        )
        binding_raw = _load_verified_json_ref(
            obligation["child_incarnation_binding_ref"],
            label="child incarnation binding",
        )
        try:
            binding = parse_incarnation_binding(binding_raw)
        except Exception as exc:
            raise ExternalCodexRuntimeError(
                "reentry_binding_invalid", "child incarnation binding is invalid"
            ) from exc
        realization = _load_verified_json_ref(
            obligation["parent_model_realization_ref"],
            label="parent model realization",
        )
        _verified_artifact_ref_path(obligation["parent_role_ref"], label="parent role")

        if (
            task["parent_task_id"] != obligation["parent_task_id"]
            or task["expected_incarnation_id"] != binding.incarnation_id
            or task["continuation_id"] != binding.continuation.continuation_id
            or task["return_owner"] != obligation["return_owner"]
            or binding.continuation.return_owner.owner_repo
            != obligation["return_owner"]
            or tuple(obligation["deferred_parent_decisions"])
            != binding.continuation.deferred_parent_decisions
        ):
            raise ExternalCodexRuntimeError(
                "reentry_identity_mismatch",
                "parent obligation, child task, binding, or return owner differs",
            )
        matching = [
            condition
            for condition in binding.wake_policy.conditions
            if condition.condition_id == obligation["expected_wake_condition_id"]
        ]
        if (
            len(matching) != 1
            or matching[0].event_kind != obligation["expected_wake_event_kind"]
            or matching[0].action != "wake_parent"
            or matching[0].condition_id not in binding.wake_policy.escalation_conditions
        ):
            raise ExternalCodexRuntimeError(
                "reentry_wake_unbound",
                "expected wake is not one exact escalation condition in the binding",
            )

        configuration = realization.get("configuration")
        runtime = (
            configuration.get("runtime") if isinstance(configuration, dict) else None
        )
        permissions = (
            configuration.get("permissions")
            if isinstance(configuration, dict)
            else None
        )
        if (
            realization.get("kind") != "ModelRealization"
            or not isinstance(runtime, dict)
            or runtime.get("model_slug") != "gpt-5.6-sol"
            or runtime.get("transport") != "exec-jsonl"
            or configuration.get("reasoning_effort") != "max"
            or not isinstance(permissions, dict)
            or permissions.get("sandbox_mode") != "read-only"
            or permissions.get("approval_policy") != "never"
            or permissions.get("external_effects") is not False
        ):
            raise ExternalCodexRuntimeError(
                "reentry_parent_realization_invalid",
                "parent realization is not exact read-only Sol max exec-jsonl",
            )

        executable = Path(str(obligation["codex_executable"]))
        workspace = Path(str(obligation["parent_workspace"]))
        codex_home = Path(str(obligation["codex_home"]))
        if (
            not executable.is_file()
            or executable.is_symlink()
            or sha256_file(executable) != obligation["codex_executable_digest"]
        ):
            raise ExternalCodexRuntimeError(
                "reentry_codex_drift", "parent Codex executable identity differs"
            )
        if (
            not workspace.is_dir()
            or workspace.is_symlink()
            or not codex_home.is_dir()
            or codex_home.is_symlink()
        ):
            raise ExternalCodexRuntimeError(
                "reentry_runtime_coordinate_invalid",
                "parent workspace or Codex home is unavailable or symbolic",
            )
        return task, binding, realization

    @staticmethod
    def _codex_usage(events: Sequence[Mapping[str, Any]]) -> dict[str, int]:
        completed = [event for event in events if event.get("type") == "turn.completed"]
        if len(completed) != 1 or not isinstance(completed[0].get("usage"), dict):
            raise ExternalCodexRuntimeError(
                "reentry_turn_incomplete", "parent turn has no exact completion usage"
            )
        usage = completed[0]["usage"]
        values: dict[str, int] = {}
        for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
            value = usage.get(key, 0)
            if not isinstance(value, int) or value < 0:
                raise ExternalCodexRuntimeError(
                    "reentry_usage_invalid", f"parent turn {key} is invalid"
                )
            values[key] = value
        return values

    def _codex_environment(
        self, obligation: Mapping[str, Any], scratch: Path
    ) -> dict[str, str]:
        isolated_home = ExternalCodexRuntime._isolated_empty_directory(
            scratch / "parent-home",
            error_code="reentry_parent_home_unavailable",
            purpose="parent-turn HOME",
        )
        environment = {
            "CODEX_HOME": str(obligation["codex_home"]),
            "HOME": str(isolated_home),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "TMPDIR": str(scratch),
            "NO_COLOR": "1",
        }
        return environment

    def _codex_command(
        self,
        obligation: Mapping[str, Any],
        realization: Mapping[str, Any],
        *,
        output_schema: Path,
        output_message: Path,
        thread_id: str | None,
    ) -> list[str]:
        configuration = realization["configuration"]
        common = [
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--disable",
            "multi_agent",
            "--disable",
            "shell_tool",
            "--disable",
            "code_mode_host",
            "--disable",
            "apps",
            "--disable",
            "browser_use",
            "--disable",
            "computer_use",
            "--disable",
            "image_generation",
            "--disable",
            "view_image",
            "--disable",
            "goals",
            "--disable",
            "memories",
            "--disable",
            "plugins",
            "--disable",
            "hooks",
            "--disable",
            "tool_suggest",
            "-m",
            str(configuration["runtime"]["model_slug"]),
            "-c",
            f'model_reasoning_effort="{configuration["reasoning_effort"]}"',
            "-c",
            'approval_policy="never"',
            "-c",
            'shell_environment_policy.inherit="core"',
            "-c",
            'shell_environment_policy.exclude=["*KEY*","*TOKEN*","*SECRET*","*PASSWORD*","*CREDENTIAL*"]',
            "--output-schema",
            str(output_schema),
            "--json",
            "-o",
            str(output_message),
        ]
        base = [
            str(obligation["codex_executable"]),
            "-a",
            "never",
            "-s",
            "read-only",
            "-C",
            str(obligation["parent_workspace"]),
            "exec",
        ]
        if thread_id is None:
            return [*base, *common, "--color", "never", "-"]
        return [*base, "resume", *common, thread_id, "-"]

    def _containment_command(
        self,
        command: Sequence[str],
        identity_path: Path,
        executable_digest: str,
    ) -> list[str]:
        containment = self.profile["process_containment"]
        return [
            sys.executable,
            str(SUPERVISOR_PATH),
            "--parent-pid",
            str(os.getpid()),
            "--term-timeout-seconds",
            str(containment["term_timeout_seconds"]),
            "--kill-timeout-seconds",
            str(containment["kill_timeout_seconds"]),
            "--identity-file",
            str(identity_path),
            "--executable-digest",
            executable_digest,
            "--",
            *command,
        ]

    def _load_parent_turn_result(
        self,
        turn_root: Path,
        *,
        kind: Literal["yield", "reentry"],
        thread_id: str | None,
        prompt: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        completion_path = turn_root / "turn-completion.json"
        completion = load_json(completion_path, label=f"parent {kind} turn completion")
        if set(completion) != {
            "schema_version",
            "kind",
            "started_at",
            "finished_at",
            "exit_code",
            "prompt_sha256",
        } or (
            completion.get("schema_version")
            != "abyss_stack_external_codex_parent_turn_completion_v1"
            or completion.get("kind") != kind
            or completion.get("prompt_sha256") != sha256_bytes(prompt.encode("utf-8"))
            or not isinstance(completion.get("exit_code"), int)
            or isinstance(completion.get("exit_code"), bool)
        ):
            raise ExternalCodexRuntimeError(
                "reentry_parent_turn_completion_invalid",
                f"parent {kind} completion receipt differs from the requested turn",
            )
        try:
            parse_timestamp(str(completion["started_at"]))
            parse_timestamp(str(completion["finished_at"]))
        except ValueError as exc:
            raise ExternalCodexRuntimeError(
                "reentry_parent_turn_completion_invalid",
                f"parent {kind} completion receipt has invalid timestamps",
            ) from exc
        events_path = turn_root / "codex-events.jsonl"
        output_path = turn_root / "model-output.json"
        raw_events = read_bounded(events_path)
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw_events.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ExternalCodexRuntimeError(
                    "reentry_codex_protocol_invalid",
                    f"parent turn JSONL line {line_number} is invalid",
                ) from exc
            if not isinstance(record, dict):
                raise ExternalCodexRuntimeError(
                    "reentry_codex_protocol_invalid",
                    f"parent turn JSONL line {line_number} is not an object",
                )
            if str(record.get("type") or "").startswith("item."):
                item = record.get("item")
                if (
                    not isinstance(item, dict)
                    or item.get("type") not in PARENT_PASSIVE_ITEM_TYPES
                ):
                    raise ExternalCodexRuntimeError(
                        "reentry_parent_tool_event_forbidden",
                        "parent yield and re-entry turns admit no tool event",
                    )
            records.append(record)
        thread_ids = {
            str(record["thread_id"])
            for record in records
            if record.get("type") == "thread.started"
            and isinstance(record.get("thread_id"), str)
        }
        exit_code = int(completion["exit_code"])
        if exit_code != 0 or len(thread_ids) != 1 or not output_path.is_file():
            raise ExternalCodexRuntimeError(
                "reentry_parent_turn_failed",
                f"parent {kind} turn failed before a unique structured result",
            )
        observed_thread = next(iter(thread_ids))
        if thread_id is not None and observed_thread != thread_id:
            raise ExternalCodexRuntimeError(
                "reentry_parent_thread_drift",
                "parent resume returned another thread identity",
            )
        output_schema = (
            PARENT_YIELD_SCHEMA_PATH if kind == "yield" else PARENT_REENTRY_SCHEMA_PATH
        )
        output = load_json(output_path, label=f"parent {kind} output")
        validate_json(output, output_schema, label=f"parent {kind} output")
        turn = {
            "kind": kind,
            "started_at": completion["started_at"],
            "finished_at": completion["finished_at"],
            "exit_code": exit_code,
            "thread_id": observed_thread,
            "events_ref": _artifact_ref(events_path),
            "output_ref": _artifact_ref(output_path),
            "usage": self._codex_usage(records),
        }
        return turn, output

    def _run_parent_turn(
        self,
        obligation: Mapping[str, Any],
        realization: Mapping[str, Any],
        *,
        kind: Literal["yield", "reentry"],
        prompt: str,
        thread_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        reentry_id = str(obligation["reentry_id"])
        turns_root = self._reentry_dir(reentry_id) / "turns"
        turns_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if kind == "yield":
            attempt_pattern = "001-yield-attempt-*"
            attempt_name = "001-yield-attempt-{number:03d}"
            attempt_regex = r"001-yield-attempt-([0-9]{3,})"
            active_code = "reentry_parent_yield_still_active"
        else:
            attempt_pattern = "002-reentry-attempt-*"
            attempt_name = "002-reentry-attempt-{number:03d}"
            attempt_regex = r"002-reentry-attempt-([0-9]{3,})"
            active_code = "reentry_parent_turn_still_active"
        numbered_attempts = sorted(
            (
                int(match.group(1)),
                candidate,
            )
            for candidate in turns_root.glob(attempt_pattern)
            if (match := re.fullmatch(attempt_regex, candidate.name))
        )
        prior_attempts = [candidate for _, candidate in numbered_attempts]
        for prior in prior_attempts:
            identity_path = prior / "process-identity.json"
            if identity_path.is_file() and not identity_path.is_symlink():
                try:
                    identity = load_json(
                        identity_path,
                        label=f"prior parent {kind} process identity",
                    )
                except ExternalCodexRuntimeError:
                    identity = {}
                if _pid_matches(
                    identity.get("supervisor_pid"),
                    identity.get("supervisor_start_ticks"),
                ):
                    raise ExternalCodexRuntimeError(
                        active_code,
                        f"a prior parent {kind} attempt is still being contained",
                    )
        if kind == "reentry" and prior_attempts:
            latest = prior_attempts[-1]
            if (latest / "turn-completion.json").is_file():
                return self._load_parent_turn_result(
                    latest,
                    kind=kind,
                    thread_id=thread_id,
                    prompt=prompt,
                )
        next_attempt = numbered_attempts[-1][0] + 1 if numbered_attempts else 1
        turn_root = turns_root / attempt_name.format(number=next_attempt)
        scratch = turn_root / "scratch"
        scratch.mkdir(parents=True, exist_ok=False, mode=0o700)
        prompt_path = turn_root / "prompt.txt"
        events_path = turn_root / "codex-events.jsonl"
        stderr_path = turn_root / "codex-stderr.log"
        output_path = turn_root / "model-output.json"
        identity_path = turn_root / "process-identity.json"
        _atomic_write_bytes(prompt_path, prompt.encode("utf-8"), mode=0o400)
        output_schema = (
            PARENT_YIELD_SCHEMA_PATH if kind == "yield" else PARENT_REENTRY_SCHEMA_PATH
        )
        command = self._containment_command(
            self._codex_command(
                obligation,
                realization,
                output_schema=output_schema,
                output_message=output_path,
                thread_id=thread_id,
            ),
            identity_path,
            str(obligation["codex_executable_digest"]),
        )
        started_at = iso_now()
        with (
            prompt_path.open("rb") as prompt_handle,
            events_path.open("wb") as events_handle,
            stderr_path.open("wb") as stderr_handle,
        ):
            process = subprocess.Popen(
                command,
                stdin=prompt_handle,
                stdout=events_handle,
                stderr=stderr_handle,
                env=self._codex_environment(obligation, scratch),
                start_new_session=True,
            )
            try:
                exit_code = process.wait()
            except BaseException:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise
        finished_at = iso_now()
        _atomic_write_json(
            turn_root / "turn-completion.json",
            {
                "schema_version": "abyss_stack_external_codex_parent_turn_completion_v1",
                "kind": kind,
                "started_at": started_at,
                "finished_at": finished_at,
                "exit_code": exit_code,
                "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
            },
            mode=0o400,
        )
        return self._load_parent_turn_result(
            turn_root,
            kind=kind,
            thread_id=thread_id,
            prompt=prompt,
        )

    @staticmethod
    def _yield_prompt(
        obligation: Mapping[str, Any],
        task: Mapping[str, Any],
        binding: IncarnationBinding,
    ) -> str:
        payload = {
            "reentry_id": obligation["reentry_id"],
            "parent_task_id": obligation["parent_task_id"],
            "return_owner": obligation["return_owner"],
            "expected_wake": {
                "condition_id": obligation["expected_wake_condition_id"],
                "event_kind": obligation["expected_wake_event_kind"],
                "action": "wake_parent",
            },
            "deferred_parent_decisions": obligation["deferred_parent_decisions"],
            "child_task": task,
            "continuation": binding.continuation.model_dump(mode="json"),
        }
        return (
            "Ты — отдельный parent Sol max в контролируемом L2 yield. Не используй "
            "инструменты, не меняй файлы и не запускай дочерние процессы. Проверь "
            "согласованность уже типизированной child obligation ниже. Если identity, "
            "owner, invariants, done-state и wake condition согласованы, заверши inference "
            "и верни JSON decision=yield. Скопируй reentry_id, continuation_id, "
            "child task_id, expected event kind и deferred_parent_decisions дословно. "
            "Ничего не принимай за human authority.\n\n"
            + "<parent_payload>\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n</parent_payload>"
        )

    @staticmethod
    def _validate_yield_output(
        output: Mapping[str, Any],
        obligation: Mapping[str, Any],
        task: Mapping[str, Any],
        binding: IncarnationBinding,
    ) -> None:
        if (
            output["reentry_id"] != obligation["reentry_id"]
            or output["continuation_id"] != binding.continuation.continuation_id
            or output["child_task_id"] != task["task_id"]
            or output["expected_event_kind"] != obligation["expected_wake_event_kind"]
            or output["deferred_parent_decisions"]
            != obligation["deferred_parent_decisions"]
            or not str(output["summary"]).strip()
        ):
            raise ExternalCodexRuntimeError(
                "reentry_parent_yield_mismatch",
                "parent yield output differs from the immutable continuation",
            )

    def yield_parent(self, obligation_path: str | Path) -> dict[str, Any]:
        path = Path(obligation_path)
        obligation = load_json(path, label="parent re-entry obligation")
        validate_json(
            obligation,
            PARENT_OBLIGATION_SCHEMA_PATH,
            label="parent re-entry obligation",
        )
        reentry_id = str(obligation["reentry_id"])
        with self._lock(reentry_id):
            if self._state_path(reentry_id).exists():
                state = self._load_state(reentry_id)
                if state["status"] not in {"yielding", "yielded", "waiting"}:
                    raise ExternalCodexRuntimeError(
                        "reentry_already_exists",
                        "parent re-entry state already passed its yielding phase",
                    )
                materialized_path = _verified_artifact_ref_path(
                    state["obligation_ref"],
                    label="durable parent re-entry obligation",
                )
                materialized = load_json(
                    materialized_path,
                    label="durable parent re-entry obligation",
                )
                validate_json(
                    materialized,
                    PARENT_OBLIGATION_SCHEMA_PATH,
                    label="durable parent re-entry obligation",
                )
                if materialized.get("reentry_id") != reentry_id:
                    raise ExternalCodexRuntimeError(
                        "reentry_identity_mismatch",
                        "durable parent obligation names another re-entry",
                    )
                identity_fields = (
                    "parent_task_id",
                    "return_owner",
                    "expected_wake_condition_id",
                    "expected_wake_event_kind",
                    "deferred_parent_decisions",
                )
                ref_fields = (
                    "parent_model_realization_ref",
                    "parent_role_ref",
                    "child_task_ref",
                    "child_incarnation_binding_ref",
                )
                if any(
                    obligation.get(key) != materialized.get(key)
                    for key in identity_fields
                ) or any(
                    not isinstance(obligation.get(key), dict)
                    or not isinstance(materialized.get(key), dict)
                    or obligation[key].get("owner_repo")
                    != materialized[key].get("owner_repo")
                    or obligation[key].get("artifact_digest")
                    != materialized[key].get("artifact_digest")
                    or obligation[key].get("schema_version")
                    != materialized[key].get("schema_version")
                    for key in ref_fields
                ):
                    raise ExternalCodexRuntimeError(
                        "reentry_identity_mismatch",
                        "supplied parent obligation differs from its durable identity",
                    )
                task, binding, realization = self._validate_obligation(materialized)
                if state["status"] == "waiting":
                    return {
                        "state": state,
                        "state_ref": _artifact_ref(self._state_path(reentry_id)),
                    }
            else:
                self._validate_obligation(obligation)
                materialized_path, materialized = self._materialize_obligation(
                    path, obligation
                )
                task, binding, realization = self._validate_obligation(materialized)
                now = iso_now()
                events_path = self._events_path(reentry_id)
                _atomic_write_bytes(events_path, b"", mode=0o600)
                state = {
                    "schema_version": REENTRY_STATE_SCHEMA_VERSION,
                    "reentry_id": reentry_id,
                    "status": "yielding",
                    "created_at": now,
                    "updated_at": now,
                    "obligation_ref": _artifact_ref(materialized_path),
                    "parent_thread_id": None,
                    "continuation_id": binding.continuation.continuation_id,
                    "child_task_id": task["task_id"],
                    "child_incarnation_id": binding.incarnation_id,
                    "expected_wake": {
                        "condition_id": materialized["expected_wake_condition_id"],
                        "event_kind": materialized["expected_wake_event_kind"],
                        "action": "wake_parent",
                    },
                    "turns": [],
                    "events_ref": _artifact_ref(events_path),
                    "child_result_ref": None,
                    "wake_evaluation": None,
                    "reentry_result_ref": None,
                }
                # This state is durable before any Codex process or turn bytes
                # can exist. A replacement controller can therefore continue
                # the exact obligation without rewriting a partial attempt.
                self._save_state(state)
                self._append_event(
                    reentry_id,
                    event_type="external_parent.yield_prepared",
                    payload={
                        "obligation_digest": state["obligation_ref"]["artifact_digest"],
                        "child_task_id": task["task_id"],
                    },
                    significance="progress",
                )
                self._save_state(state)
            if state["status"] == "yielding":
                turn, output = self._run_parent_turn(
                    materialized,
                    realization,
                    kind="yield",
                    prompt=self._yield_prompt(materialized, task, binding),
                    thread_id=None,
                )
                self._validate_yield_output(output, materialized, task, binding)
                state["parent_thread_id"] = turn["thread_id"]
                state["turns"] = [turn]
                state["status"] = "yielded"
                self._append_event(
                    reentry_id,
                    event_type="external_parent.inference_yielded",
                    payload={
                        "thread_id": turn["thread_id"],
                        "turn_output_digest": turn["output_ref"]["artifact_digest"],
                        "turn": turn,
                    },
                    significance="checkpoint",
                )
                self._save_state(state)
            self._append_event(
                reentry_id,
                event_type="external_parent.wait_registered",
                payload={
                    "condition_id": materialized["expected_wake_condition_id"],
                    "event_kind": materialized["expected_wake_event_kind"],
                    "child_task_id": task["task_id"],
                    "child_incarnation_id": binding.incarnation_id,
                },
                significance="waiting",
            )
            state["status"] = "waiting"
            self._save_state(state)
            return self._status_locked(reentry_id)

    @staticmethod
    def _status_event_kind(status: str) -> str:
        return {
            "completed": "result.validated",
            "review_required": "result.review_required",
            "paused": "result.checkpointed",
            "authority_blocked": "run.authority_required",
            "failed": "result.failed",
            "interrupted": "runtime.interrupted",
        }.get(status, "result.unknown")

    @staticmethod
    def _child_runtime_lock_target(
        child_result_path: Path,
    ) -> tuple[ExternalCodexRuntime, str]:
        """Locate the canonical child lock; all authority checks repeat under it."""

        if (
            not child_result_path.is_absolute()
            or child_result_path.name != "result.json"
        ):
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result must be the canonical absolute runtime result path",
            )
        try:
            resolved_result_path = child_result_path.resolve(strict=True)
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_unavailable",
                "canonical child runtime result is unavailable",
            ) from exc
        if resolved_result_path != child_result_path or child_result_path.is_symlink():
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result path contains a symbolic or non-canonical component",
            )
        candidate = load_json(child_result_path, label="child lock target result")
        validate_json(candidate, RESULT_SCHEMA_PATH, label="child lock target result")
        session_id = str(candidate["session_id"])
        session_dir = child_result_path.parent
        if session_dir.parent.name != "sessions" or session_dir.name != _session_token(
            session_id
        ):
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result is outside the canonical session identity directory",
            )
        return ExternalCodexRuntime(session_dir.parent.parent), session_id

    @staticmethod
    def _canonical_child_runtime_receipt(
        child_runtime: ExternalCodexRuntime,
        child_result_path: Path,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Load one terminal result through its canonical durable runtime state."""

        if (
            not child_result_path.is_absolute()
            or child_result_path.name != "result.json"
        ):
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result must be the canonical absolute runtime result path",
            )
        try:
            resolved_result_path = child_result_path.resolve(strict=True)
        except OSError as exc:
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_unavailable",
                "canonical child runtime result is unavailable",
            ) from exc
        if resolved_result_path != child_result_path or child_result_path.is_symlink():
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result path contains a symbolic or non-canonical component",
            )
        child_result = load_json(child_result_path, label="child terminal result")
        validate_json(child_result, RESULT_SCHEMA_PATH, label="child terminal result")
        session_id = str(child_result["session_id"])
        session_dir = child_result_path.parent
        if session_dir.parent.name != "sessions" or session_dir.name != _session_token(
            session_id
        ):
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_noncanonical",
                "child result is outside the canonical session identity directory",
            )
        state_path = session_dir / "state.json"
        if not state_path.is_file() or state_path.is_symlink():
            raise ExternalCodexRuntimeError(
                "reentry_child_state_missing",
                "canonical child runtime state receipt is unavailable",
            )
        child_state = load_json(state_path, label="child runtime state receipt")
        validate_json(
            child_state, STATE_SCHEMA_PATH, label="child runtime state receipt"
        )
        result_digest = sha256_file(child_result_path)
        expected_events_path = session_dir / "events.jsonl"
        events_ref = child_result["events_ref"]
        if (
            child_state.get("schema_version") != STATE_SCHEMA_VERSION
            or child_state.get("session_id") != session_id
            or child_state.get("status") != child_result["status"]
            or child_state.get("status") not in {*TERMINAL_STATES, "interrupted"}
            or child_state.get("incarnation_id") != child_result["incarnation_id"]
            or child_state.get("task_id") != child_result["task_id"]
            or child_state.get("thread_id") != child_result["thread_id"]
            or child_state.get("result_path") != str(child_result_path)
            or child_state.get("result_digest") != result_digest
            or events_ref.get("artifact_ref") != str(expected_events_path)
            or child_state.get("events_digest") != events_ref.get("artifact_digest")
        ):
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_mismatch",
                "child durable state does not bind the supplied terminal result",
            )
        verified_events_path = _verified_artifact_ref_path(
            events_ref, label="canonical child event stream"
        )
        if verified_events_path != expected_events_path:
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_mismatch",
                "child event receipt is outside its canonical session directory",
            )
        event_count = sum(
            1
            for _line_number, _line in _iter_jsonl_bytes(
                verified_events_path,
                failure_code="reentry_child_receipt_mismatch",
                label="canonical child event stream",
            )
        )
        if event_count != int(child_state["last_event_sequence"]) + 1:
            raise ExternalCodexRuntimeError(
                "reentry_child_receipt_mismatch",
                "child event receipt differs from the durable terminal sequence",
            )
        attempt_dir = (
            session_dir / "attempts" / f"{int(child_result['attempt_count']):03d}"
        )
        result_candidates = [attempt_dir / "runtime-result.json"]
        result_candidates.extend(
            sorted(attempt_dir.glob("runtime-result-revision-*.json"))
        )
        preserved_path = next(
            (
                candidate
                for candidate in result_candidates
                if candidate.is_file()
                and not candidate.is_symlink()
                and sha256_file(candidate) == result_digest
            ),
            None,
        )
        if preserved_path is None:
            raise ExternalCodexRuntimeError(
                "reentry_child_snapshot_missing",
                "child terminal result has no immutable attempt snapshot",
            )
        preserved_ref = _artifact_ref(preserved_path)
        child_runtime._verified_preserved_result_closure_ref_locked(
            previous_result=child_result,
            preserved_result_ref=preserved_ref,
            preserved_result_path=preserved_path,
        )
        return child_result, child_state, preserved_ref

    @staticmethod
    def _verify_child_wake_event(
        result: Mapping[str, Any], binding: IncarnationBinding
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if result["events_ref"] not in result["evidence_refs"]:
            raise ExternalCodexRuntimeError(
                "reentry_child_event_unbound",
                "child result does not bind its event stream as terminal evidence",
            )
        event_kind = ExternalCodexParentReentry._status_event_kind(
            str(result["status"])
        )
        condition = next(
            (
                item
                for item in binding.wake_policy.conditions
                if item.event_kind == event_kind
            ),
            None,
        )
        expected = {
            "event_kind": event_kind,
            "condition_id": condition.condition_id if condition is not None else None,
            "action": (
                condition.action
                if condition is not None
                else binding.wake_policy.default_action
            ),
            "wake_parent": condition is not None and condition.action == "wake_parent",
            "reason": (
                condition.description
                if condition is not None
                else "No exact wake condition matched; runtime applied the configured default."
            ),
        }
        if result["wake_evaluation"] != expected:
            raise ExternalCodexRuntimeError(
                "reentry_child_wake_mismatch",
                "child result wake evaluation differs from the immutable binding",
            )
        events_path = _verified_artifact_ref_path(
            result["events_ref"], label="child event stream"
        )
        matches: list[dict[str, Any]] = []
        for line_number, line in _iter_jsonl_bytes(
            events_path,
            failure_code="reentry_child_event_invalid",
            label="child event stream",
        ):
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ExternalCodexRuntimeError(
                    "reentry_child_event_invalid",
                    f"child event line {line_number} is invalid",
                ) from exc
            if not isinstance(event, dict):
                raise ExternalCodexRuntimeError(
                    "reentry_child_event_invalid",
                    f"child event line {line_number} is not an object",
                )
            if (
                event.get("event_type") == "external_agent.wake_evaluated"
                and event.get("payload") == expected
            ):
                matches.append(event)
        if len(matches) != 1:
            raise ExternalCodexRuntimeError(
                "reentry_child_event_missing",
                "child stream does not contain one exact wake evaluation event",
            )
        return expected, matches[0]

    @staticmethod
    def _distilled_child_return(
        result: Mapping[str, Any],
        child_result_ref: Mapping[str, Any],
        event: Mapping[str, Any],
    ) -> dict[str, Any]:
        report_summary: str | None = None
        report_findings: list[Any] = []
        report_ref = result.get("report_ref")
        if isinstance(report_ref, dict):
            report = _load_verified_json_ref(report_ref, label="child model report")
            summary = report.get("summary")
            findings = report.get("findings")
            if isinstance(summary, str):
                report_summary = summary
            if isinstance(findings, list):
                report_findings = findings
        return {
            "child_result_ref": dict(child_result_ref),
            "child_status": result["status"],
            "child_task_id": result["task_id"],
            "child_incarnation_id": result["incarnation_id"],
            "child_thread_id": result["thread_id"],
            "wake_evaluation": result["wake_evaluation"],
            "observed_event_digest": canonical_digest(event),
            "report_ref": report_ref,
            "report_summary": report_summary,
            "report_findings": report_findings,
            "changed_paths": result["changed_paths"],
            "usage": result["usage"],
            "usage_observation": result["usage_observation"],
        }

    @staticmethod
    def _load_admitted_child_snapshot(
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Load only the immutable attempt result already admitted by the parent."""

        child_ref = state.get("child_result_ref")
        if not isinstance(child_ref, dict):
            raise ExternalCodexRuntimeError(
                "reentry_admitted_child_missing",
                "parent state has no admitted child result snapshot",
            )
        snapshot_path = _verified_artifact_ref_path(
            child_ref,
            label="admitted child result snapshot",
        )
        if (
            snapshot_path.parent.parent.name != "attempts"
            or not snapshot_path.parent.name.isdigit()
            or (
                snapshot_path.name != "runtime-result.json"
                and not re.fullmatch(
                    r"runtime-result-revision-[0-9]{3}\.json",
                    snapshot_path.name,
                )
            )
        ):
            raise ExternalCodexRuntimeError(
                "reentry_child_snapshot_noncanonical",
                "admitted child result is not an immutable attempt snapshot",
            )
        result = load_json(snapshot_path, label="admitted child result snapshot")
        validate_json(
            result, RESULT_SCHEMA_PATH, label="admitted child result snapshot"
        )
        if (
            result.get("task_id") != state["child_task_id"]
            or result.get("incarnation_id") != state["child_incarnation_id"]
            or result.get("wake_evaluation") != state.get("wake_evaluation")
        ):
            raise ExternalCodexRuntimeError(
                "reentry_recovery_input_drift",
                "admitted child snapshot differs from the durable parent state",
            )
        return result

    def _load_admitted_distilled_return(
        self,
        reentry_id: str,
        state: Mapping[str, Any],
        child_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Load the parent-local return bound by the child-admission event."""

        admitted_payloads: list[dict[str, Any]] = []
        for line_number, line in _iter_jsonl_bytes(
            self._events_path(reentry_id),
            failure_code="reentry_recovery_input_drift",
            label="parent re-entry event stream",
        ):
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ExternalCodexRuntimeError(
                    "reentry_recovery_input_drift",
                    f"parent re-entry event line {line_number} is invalid",
                ) from exc
            if (
                isinstance(event, dict)
                and event.get("event_type") == "external_parent.child_event_admitted"
                and isinstance(event.get("payload"), dict)
            ):
                admitted_payloads.append(event["payload"])
        if len(admitted_payloads) != 1:
            raise ExternalCodexRuntimeError(
                "reentry_recovery_input_drift",
                "parent event stream does not bind exactly one child admission",
            )
        payload = admitted_payloads[0]
        distilled_ref = payload.get("distilled_return_ref")
        if (
            payload.get("child_result_ref") != state.get("child_result_ref")
            or payload.get("wake_evaluation") != state.get("wake_evaluation")
            or not isinstance(distilled_ref, dict)
        ):
            raise ExternalCodexRuntimeError(
                "reentry_recovery_input_drift",
                "child admission event differs from the durable parent state",
            )
        distilled_path = _verified_artifact_ref_path(
            distilled_ref,
            label="admitted distilled child return",
        )
        if distilled_path != (
            self._reentry_dir(reentry_id) / "distilled-child-return.json"
        ):
            raise ExternalCodexRuntimeError(
                "reentry_recovery_input_drift",
                "child admission event names a non-canonical distilled return",
            )
        distilled = load_json(distilled_path, label="admitted distilled child return")
        if (
            distilled.get("child_result_ref") != state.get("child_result_ref")
            or distilled.get("child_task_id") != state["child_task_id"]
            or distilled.get("child_incarnation_id") != state["child_incarnation_id"]
            or distilled.get("child_status") != child_result.get("status")
            or distilled.get("child_thread_id") != child_result.get("thread_id")
            or distilled.get("wake_evaluation") != state.get("wake_evaluation")
            or distilled.get("observed_event_digest")
            != payload.get("observed_event_digest")
        ):
            raise ExternalCodexRuntimeError(
                "reentry_recovery_input_drift",
                "distilled return differs from its admitted child event",
            )
        return distilled

    @staticmethod
    def _reentry_prompt(
        obligation: Mapping[str, Any],
        state: Mapping[str, Any],
        distilled: Mapping[str, Any],
    ) -> str:
        payload = {
            "reentry_id": obligation["reentry_id"],
            "continuation_id": state["continuation_id"],
            "deferred_parent_decisions": obligation["deferred_parent_decisions"],
            "distilled_child_return": distilled,
        }
        return (
            "Событийный runtime разбудил тот же parent Sol thread после завершения "
            "child inference. Не используй инструменты и не считывай дополнительные "
            "файлы: оцени только digest-bound distilled return. Пользователь остаётся "
            "единственным human authority. Для run.authority_required верни "
            "decision=authority_review_required и next_action=request_human_authority. "
            "Скопируй все identity и digest поля дословно; не заявляй acceptance или "
            "внешний эффект.\n\n"
            + "<parent_payload>\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n</parent_payload>"
        )

    @staticmethod
    def _validate_reentry_output(
        output: Mapping[str, Any],
        state: Mapping[str, Any],
        distilled: Mapping[str, Any],
    ) -> None:
        child_ref = distilled["child_result_ref"]
        if (
            output["reentry_id"] != state["reentry_id"]
            or output["continuation_id"] != state["continuation_id"]
            or output["child_task_id"] != state["child_task_id"]
            or output["child_result_digest"] != child_ref["artifact_digest"]
            or output["observed_event_digest"] != distilled["observed_event_digest"]
            or output["decision"] != "authority_review_required"
            or output["next_action"] != "request_human_authority"
            or not str(output["summary"]).strip()
        ):
            raise ExternalCodexRuntimeError(
                "reentry_parent_result_mismatch",
                "parent re-entry output differs from the admitted child event",
            )

    def reenter_parent(
        self, reentry_id: str, child_result_path: str | Path
    ) -> dict[str, Any]:
        with self._lock(reentry_id):
            state = self._load_state(reentry_id)
            recovering = state["status"] == "reentering"
            if state["status"] not in {"waiting", "reentering"}:
                raise ExternalCodexRuntimeError(
                    "reentry_state_not_waiting",
                    f"parent re-entry cannot admit or recover a wake: {state['status']}",
                )
            obligation = _load_verified_json_ref(
                state["obligation_ref"],
                label="materialized parent obligation",
                schema_path=PARENT_OBLIGATION_SCHEMA_PATH,
            )
            task, binding, realization = self._validate_obligation(obligation)
            already_admitted = isinstance(state.get("child_result_ref"), dict)
            distilled: dict[str, Any] | None = None
            if already_admitted:
                child_result = self._load_admitted_child_snapshot(state)
                child_ref = state["child_result_ref"]
                wake = state["wake_evaluation"]
                if not isinstance(wake, dict):
                    raise ExternalCodexRuntimeError(
                        "reentry_recovery_input_drift",
                        "admitted child snapshot has no durable wake evaluation",
                    )
                if wake.get("wake_parent") is True:
                    distilled = self._load_admitted_distilled_return(
                        reentry_id,
                        state,
                        child_result,
                    )
            else:
                child_path = Path(child_result_path)
                child_runtime, child_session_id = self._child_runtime_lock_target(
                    child_path
                )
                with child_runtime._lock(child_session_id):
                    child_result, _child_state, child_ref = (
                        self._canonical_child_runtime_receipt(
                            child_runtime,
                            child_path,
                        )
                    )
                    if (
                        child_result["task_id"] != state["child_task_id"]
                        or child_result["incarnation_id"]
                        != state["child_incarnation_id"]
                        or child_result["task_id"] != task["task_id"]
                    ):
                        raise ExternalCodexRuntimeError(
                            "reentry_child_identity_mismatch",
                            "child terminal result belongs to another task or incarnation",
                        )
                    wake, observed_event = self._verify_child_wake_event(
                        child_result, binding
                    )
                    distilled_ref: dict[str, Any] | None = None
                    if wake["wake_parent"]:
                        distilled = self._distilled_child_return(
                            child_result,
                            child_ref,
                            observed_event,
                        )
                        distilled_path = (
                            self._reentry_dir(reentry_id)
                            / "distilled-child-return.json"
                        )
                        _atomic_write_json(distilled_path, distilled, mode=0o400)
                        distilled_ref = _artifact_ref(distilled_path)
                    self._append_event(
                        reentry_id,
                        event_type="external_parent.child_event_admitted",
                        payload={
                            "child_result_digest": child_ref["artifact_digest"],
                            "child_result_ref": child_ref,
                            "distilled_return_ref": distilled_ref,
                            "observed_event_digest": canonical_digest(observed_event),
                            "wake_evaluation": wake,
                        },
                        significance=(
                            "parent_wake" if wake["wake_parent"] else "filtered"
                        ),
                    )
                state["child_result_ref"] = child_ref
                state["wake_evaluation"] = wake
            expected = state["expected_wake"]
            exact_expected_wake = (
                wake["condition_id"] == expected["condition_id"]
                and wake["event_kind"] == expected["event_kind"]
                and wake["action"] == expected["action"]
                and wake["wake_parent"] is True
            )
            if not exact_expected_wake:
                if recovering:
                    raise ExternalCodexRuntimeError(
                        "reentry_recovery_input_drift",
                        "re-entering state no longer has its exact admitted wake",
                    )
                state["status"] = "filtered"
                self._append_event(
                    reentry_id,
                    event_type="external_parent.wake_filtered",
                    payload={"wake_evaluation": wake},
                    significance="terminal",
                )
                self._save_state(state)
                return self._status_locked(reentry_id)

            distilled_path = (
                self._reentry_dir(reentry_id) / "distilled-child-return.json"
            )
            if distilled is None:
                raise ExternalCodexRuntimeError(
                    "reentry_recovery_input_drift",
                    "exact child wake has no admitted distilled return",
                )
            if not recovering:
                state["status"] = "reentering"
                self._append_event(
                    reentry_id,
                    event_type="external_parent.reentry_started",
                    payload={
                        "parent_thread_id": state["parent_thread_id"],
                        "distilled_return_ref": _artifact_ref(distilled_path),
                    },
                    significance="reentry",
                )
                self._save_state(state)
            try:
                turn, output = self._run_parent_turn(
                    obligation,
                    realization,
                    kind="reentry",
                    prompt=self._reentry_prompt(obligation, state, distilled),
                    thread_id=str(state["parent_thread_id"]),
                )
                self._validate_reentry_output(output, state, distilled)
            except Exception as exc:
                if (
                    isinstance(exc, ExternalCodexRuntimeError)
                    and exc.code == "reentry_parent_turn_still_active"
                ):
                    raise
                state["status"] = "failed"
                self._append_event(
                    reentry_id,
                    event_type="external_parent.reentry_failed",
                    payload={"failure_type": type(exc).__name__},
                    significance="terminal",
                )
                self._save_state(state)
                raise
            state["turns"] = [*state["turns"], turn]
            state["reentry_result_ref"] = turn["output_ref"]
            state["status"] = "reentered"
            self._append_event(
                reentry_id,
                event_type="external_parent.reentry_completed",
                payload={
                    "parent_thread_id": turn["thread_id"],
                    "result_digest": turn["output_ref"]["artifact_digest"],
                    "next_action": output["next_action"],
                    "turn": turn,
                    "reentry_result_ref": turn["output_ref"],
                },
                significance="authority",
            )
            self._save_state(state)
            return self._status_locked(reentry_id)

    def _status_locked(self, reentry_id: str) -> dict[str, Any]:
        current = self._load_state(reentry_id)
        return {
            "state": current,
            "state_ref": _artifact_ref(self._state_path(reentry_id)),
        }

    def status(self, reentry_id: str) -> dict[str, Any]:
        with self._lock(reentry_id):
            return self._status_locked(reentry_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=(
            "preflight",
            "start",
            "run-to-terminal",
            "status",
            "events",
            "result",
            "resume",
            "interrupt",
            "export-a2a-result",
            "yield-parent",
            "reenter-parent",
            "reentry-status",
        ),
    )
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--profile", default=str(PROFILE_PATH))
    parser.add_argument("--launch")
    parser.add_argument("--owner-execution-request")
    parser.add_argument("--session-id")
    parser.add_argument("--after-sequence", type=int, default=-1)
    parser.add_argument("--resume-request")
    parser.add_argument("--reviewer-session-id")
    parser.add_argument("--reviewer-state-root")
    parser.add_argument("--summon-request")
    parser.add_argument("--output")
    parser.add_argument("--obligation")
    parser.add_argument("--reentry-id")
    parser.add_argument("--child-result")
    return parser


def _require(value: str | None, flag: str) -> str:
    if not value:
        raise ExternalCodexRuntimeError(
            "missing_argument", f"{flag} is required for this operation"
        )
    return value


def _write_response(
    *, ok: bool, result: Any = None, error: ExternalCodexRuntimeError | None = None
) -> None:
    payload: dict[str, Any] = {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "ok": ok,
    }
    if ok:
        payload["result"] = result
    else:
        assert error is not None
        payload["error_code"] = error.code
        payload["message"] = str(error)
    sys.stdout.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: Any
        if args.operation in {"yield-parent", "reenter-parent", "reentry-status"}:
            reentry = ExternalCodexParentReentry(
                args.state_root, profile_path=args.profile
            )
            if args.operation == "yield-parent":
                result = reentry.yield_parent(_require(args.obligation, "--obligation"))
            elif args.operation == "reenter-parent":
                result = reentry.reenter_parent(
                    _require(args.reentry_id, "--reentry-id"),
                    _require(args.child_result, "--child-result"),
                )
            else:
                result = reentry.status(_require(args.reentry_id, "--reentry-id"))
        else:
            runtime = ExternalCodexRuntime(args.state_root, profile_path=args.profile)
            if args.operation == "preflight":
                result = runtime.preflight(
                    _require(args.launch, "--launch"),
                    owner_request_path=args.owner_execution_request,
                )
            elif args.operation == "start":
                result = runtime.start(
                    _require(args.launch, "--launch"),
                    owner_request_path=args.owner_execution_request,
                )
            elif args.operation == "run-to-terminal":
                result = runtime.run_to_terminal(
                    _require(args.launch, "--launch"),
                    owner_request_path=args.owner_execution_request,
                )
            elif args.operation == "status":
                result = runtime.status(_require(args.session_id, "--session-id"))
            elif args.operation == "events":
                result = runtime.events(
                    _require(args.session_id, "--session-id"),
                    after_sequence=args.after_sequence,
                )
            elif args.operation == "result":
                result = runtime.result(_require(args.session_id, "--session-id"))
            elif args.operation == "resume":
                result = runtime.resume(
                    _require(args.session_id, "--session-id"),
                    _require(args.resume_request, "--resume-request"),
                )
            elif args.operation == "interrupt":
                result = runtime.interrupt(_require(args.session_id, "--session-id"))
            else:
                result = runtime.export_a2a_result(
                    _require(args.session_id, "--session-id"),
                    reviewer_session_id=_require(
                        args.reviewer_session_id, "--reviewer-session-id"
                    ),
                    reviewer_state_root=args.reviewer_state_root,
                    summon_request_path=_require(
                        args.summon_request, "--summon-request"
                    ),
                    output_path=_require(args.output, "--output"),
                )
        _write_response(ok=True, result=result)
        return 0
    except ExternalCodexRuntimeError as exc:
        _write_response(ok=False, error=exc)
        return 2
    except Exception as exc:  # pragma: no cover - last-resort fail-closed envelope
        error = ExternalCodexRuntimeError(
            "unexpected_runtime_error", f"unexpected {type(exc).__name__}"
        )
        _write_response(ok=False, error=error)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
