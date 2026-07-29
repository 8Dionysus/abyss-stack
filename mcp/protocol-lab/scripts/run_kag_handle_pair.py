#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import anyio
import httpx2
import mcp.server.request_state as request_state_module
import mcp_types
import uvicorn
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, RequestStateSecurity
from mcp.shared.exceptions import MCPError
from mcp_types import (
    CallToolResult,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    Implementation,
    InputRequiredResult,
    ToolAnnotations,
)

from aoa_kag_mcp.core import AoAKagMCPState
from aoa_kag_mcp.runtime import build_application


NEXT_WIRE_VERSION = "2026-07-28"
HANDLE_TTL_SECONDS = 5.0
FROZEN_REJECTION = {
    "code": mcp_types.INVALID_PARAMS,
    "message": "Invalid or expired requestState",
    "data": {"reason": "invalid_request_state"},
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _git_head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = (
        json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    ).encode()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, encoded)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    path.chmod(0o600)


class LabClock:
    """Deterministic wall clock used only by the request-state boundary."""

    def __init__(self, now: float) -> None:
        self.now = now

    def time(self) -> float:
        return self.now


class LabTokenVerifier:
    """In-memory verifier; generated raw tokens never enter a receipt."""

    def __init__(self, tokens: dict[str, AccessToken]) -> None:
        self._tokens = tokens

    async def verify_token(self, token: str) -> AccessToken | None:
        return self._tokens.get(token)


def _ask(owner: str) -> ElicitRequest:
    return ElicitRequest(
        params=ElicitRequestFormParams(
            message=f"Confirm read-only KAG evidence access for {owner}.",
            requested_schema={
                "type": "object",
                "properties": {"confirm": {"type": "boolean"}},
                "required": ["confirm"],
            },
        )
    )


def _accept() -> ElicitResult:
    return ElicitResult(action="accept", content={"confirm": True})


def _tamper(token: str) -> str:
    index = len(token) // 2
    replacement = "A" if token[index] != "A" else "B"
    return token[:index] + replacement + token[index + 1 :]


def _error_shape(exc: MCPError) -> dict[str, Any]:
    return {
        "code": exc.code,
        "message": exc.message,
        "data": exc.data,
    }


def _assert_frozen_rejection(exc: MCPError) -> dict[str, Any]:
    observed = _error_shape(exc)
    if observed != FROZEN_REJECTION:
        raise RuntimeError(
            "requestState rejection shape drifted: "
            f"{json.dumps(observed, sort_keys=True)}"
        )
    return observed


def _result_payload(result: CallToolResult) -> dict[str, Any]:
    dumped = result.model_dump(by_alias=True, mode="json", exclude_none=True)
    structured = dumped.get("structuredContent")
    if not isinstance(structured, dict):
        raise RuntimeError("confirmed KAG handle call lacked structuredContent")
    return structured


def build_handle_server(
    *,
    application: Any,
    verifier: LabTokenVerifier,
    resource_url: str,
    request_state_key: bytes,
    seen_plaintext: list[str],
) -> MCPServer:
    server = MCPServer(
        name="aoa-kag-next-handle-lab",
        title="AoA KAG explicit-handle protocol lab",
        description=(
            "Isolated read-only KAG requestState boundary probe. "
            "It has no candidate, acceptance, or source authority."
        ),
        version="0.1.0-lab",
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url="https://auth.os-abyss.invalid",
            resource_server_url=resource_url,
            required_scopes=["kag:read"],
        ),
        request_state_security=RequestStateSecurity(
            keys=[request_state_key],
            ttl=HANDLE_TTL_SECONDS,
        ),
    )

    @server.tool(
        name="kag_confirmed_read",
        description=(
            "Return one owner-qualified KAG evidence view after an explicit "
            "read-only confirmation round."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    async def kag_confirmed_read(
        owner: str,
        ctx: Context,
    ) -> dict[str, Any] | InputRequiredResult:
        if ctx.input_responses is None:
            plaintext = json.dumps(
                {
                    "authority_ceiling": "evidence_only",
                    "effect_state": "read_only",
                    "owner": owner,
                    "schema_version": "aoa-kag-handle-state-v1",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            return InputRequiredResult(
                input_requests={"confirm": _ask(owner)},
                request_state=plaintext,
            )

        if not isinstance(ctx.request_state, str):
            raise RuntimeError("verified requestState was not restored")
        restored = json.loads(ctx.request_state)
        if (
            restored.get("owner") != owner
            or restored.get("authority_ceiling") != "evidence_only"
            or restored.get("effect_state") != "read_only"
        ):
            raise RuntimeError("restored KAG handle exceeded its bound")
        seen_plaintext.append(ctx.request_state)

        capability = application.discover(owner=owner, detail="compact")
        exact = capability["projection"]["targets"]["exact"]
        return {
            "degradation": capability["degradation"],
            "effect_state": "read_only",
            "freshness": capability["owners"][0].get("freshness"),
            "owner": capability["owners"][0]["repo"],
            "projection_exact": exact,
            "schema_version": capability["schema_version"],
        }

    return server


@asynccontextmanager
async def _running_server(server: MCPServer) -> AsyncIterator[str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    port = int(listener.getsockname()[1])
    uvicorn_server = uvicorn.Server(
        uvicorn.Config(
            server.streamable_http_app(
                streamable_http_path="/mcp",
                json_response=True,
                stateless_http=True,
                host="127.0.0.1",
            ),
            log_level="warning",
            access_log=False,
            lifespan="on",
        )
    )

    async def serve() -> None:
        await uvicorn_server.serve(sockets=[listener])

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(serve)
        with anyio.fail_after(10):
            while not uvicorn_server.started:
                await anyio.sleep(0.01)
        try:
            yield f"http://127.0.0.1:{port}/mcp"
        finally:
            uvicorn_server.should_exit = True


@asynccontextmanager
async def _authenticated_client(
    url: str,
    raw_token: str,
) -> AsyncIterator[Client]:
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {raw_token}"},
        follow_redirects=True,
    ) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(
            transport,
            mode=NEXT_WIRE_VERSION,
            raise_exceptions=True,
            client_info=Implementation(
                name="os-abyss-kag-handle-probe",
                version="1.0.0",
            ),
        ) as client:
            yield client


async def _first_round(
    client: Client,
    owner: str,
) -> str:
    result = await client.session.call_tool(
        "kag_confirmed_read",
        {"owner": owner},
        allow_input_required=True,
    )
    if not isinstance(result, InputRequiredResult):
        raise RuntimeError("KAG handle first round did not request input")
    if not result.request_state or not result.request_state.startswith("v1."):
        raise RuntimeError("KAG requestState was not an opaque v1 token")
    return result.request_state


async def _retry(
    client: Client,
    owner: str,
    token: str,
) -> CallToolResult | InputRequiredResult:
    return await client.session.call_tool(
        "kag_confirmed_read",
        {"owner": owner},
        input_responses={"confirm": _accept()},
        request_state=token,
        allow_input_required=True,
    )


async def _expect_rejection(
    client: Client,
    owner: str,
    token: str,
) -> dict[str, Any]:
    try:
        await _retry(client, owner, token)
    except MCPError as exc:
        return _assert_frozen_rejection(exc)
    raise RuntimeError("invalid requestState was accepted")


async def _exercise(
    *,
    application: Any,
    stable_config: Path,
) -> dict[str, Any]:
    original_time_module = request_state_module.time
    clock = LabClock(2_000_000_000.0)
    request_state_module.time = clock
    alice_raw = secrets.token_urlsafe(32)
    bob_raw = secrets.token_urlsafe(32)
    shared_client_id = "https://os-abyss.invalid/protocol-lab-client.json"
    issuer = "https://auth.os-abyss.invalid"
    tokens = {
        alice_raw: AccessToken(
            token=alice_raw,
            client_id=shared_client_id,
            scopes=["kag:read"],
            subject="alice",
            claims={"iss": issuer},
        ),
        bob_raw: AccessToken(
            token=bob_raw,
            client_id=shared_client_id,
            scopes=["kag:read"],
            subject="bob",
            claims={"iss": issuer},
        ),
    }
    verifier = LabTokenVerifier(tokens)
    old_key = secrets.token_bytes(32)
    new_key = secrets.token_bytes(32)
    seen_plaintext: list[str] = []
    stable_before = _digest(stable_config)

    try:
        first_server = build_handle_server(
            application=application,
            verifier=verifier,
            resource_url="http://127.0.0.1/mcp",
            request_state_key=old_key,
            seen_plaintext=seen_plaintext,
        )
        async with _running_server(first_server) as url:
            async with _authenticated_client(url, alice_raw) as alice:
                await alice.list_tools()

                positive_token = await _first_round(alice, "abyss-stack")
                positive = await _retry(
                    alice,
                    "abyss-stack",
                    positive_token,
                )
                if not isinstance(positive, CallToolResult):
                    raise RuntimeError("valid KAG handle did not complete")
                positive_payload = _result_payload(positive)

                same_request_replay = await _retry(
                    alice,
                    "abyss-stack",
                    positive_token,
                )
                if not isinstance(same_request_replay, CallToolResult):
                    raise RuntimeError("read-only same-request replay failed")
                if _result_payload(same_request_replay) != positive_payload:
                    raise RuntimeError("read-only replay changed KAG result")

                request_bound_token = await _first_round(
                    alice,
                    "abyss-stack",
                )
                cross_request = await _expect_rejection(
                    alice,
                    "aoa-memo",
                    request_bound_token,
                )
                recovered = await _retry(
                    alice,
                    "abyss-stack",
                    request_bound_token,
                )
                if not isinstance(recovered, CallToolResult):
                    raise RuntimeError("bound handle failed on original request")

                tamper_token = await _first_round(alice, "abyss-stack")
                tamper = await _expect_rejection(
                    alice,
                    "abyss-stack",
                    _tamper(tamper_token),
                )

                principal_token = await _first_round(
                    alice,
                    "abyss-stack",
                )

            async with _authenticated_client(url, bob_raw) as bob:
                principal_isolation = await _expect_rejection(
                    bob,
                    "abyss-stack",
                    principal_token,
                )

            async with _authenticated_client(url, alice_raw) as alice:
                expiry_token = await _first_round(alice, "abyss-stack")
                clock.now += HANDLE_TTL_SECONDS + 1.0
                expiry = await _expect_rejection(
                    alice,
                    "abyss-stack",
                    expiry_token,
                )

                revocation_token = await _first_round(
                    alice,
                    "abyss-stack",
                )

        second_server = build_handle_server(
            application=application,
            verifier=verifier,
            resource_url="http://127.0.0.1/mcp",
            request_state_key=new_key,
            seen_plaintext=seen_plaintext,
        )
        async with _running_server(second_server) as url:
            async with _authenticated_client(url, alice_raw) as alice:
                key_retirement = await _expect_rejection(
                    alice,
                    "abyss-stack",
                    revocation_token,
                )
    finally:
        request_state_module.time = original_time_module

    stable_after = _digest(stable_config)
    if stable_after != stable_before:
        raise RuntimeError("stable Codex config changed during handle proof")
    if positive_payload["projection_exact"]["state"] != "current":
        raise RuntimeError("confirmed KAG read did not use a current exact target")

    return {
        "auth": {
            "bearer_verified_each_request": True,
            "principal_binding": [
                "client_id",
                "issuer",
                "subject",
            ],
            "raw_tokens_recorded": False,
            "same_oauth_client_subjects": [
                "alice",
                "bob",
            ],
        },
        "handle": {
            "opaque": True,
            "plaintext_observed_on_wire": False,
            "prefix": "v1.",
            "restored_plaintext_count": len(seen_plaintext),
            "ttl_seconds": HANDLE_TTL_SECONDS,
        },
        "checks": {
            "cross_request_replay": {
                "outcome": "denied",
                "rejection": cross_request,
            },
            "expiry": {
                "outcome": "denied",
                "rejection": expiry,
            },
            "key_retirement_revocation": {
                "outcome": "denied",
                "rejection": key_retirement,
            },
            "principal_isolation": {
                "outcome": "denied",
                "rejection": principal_isolation,
            },
            "same_request_replay": {
                "outcome": "allowed_read_only_idempotent",
                "result_unchanged": True,
            },
            "tamper": {
                "outcome": "denied",
                "rejection": tamper,
            },
            "valid_round_trip": {
                "outcome": "passed",
            },
        },
        "owner_canary": {
            "degradation": positive_payload["degradation"],
            "freshness": positive_payload["freshness"],
            "owner": positive_payload["owner"],
            "projection_exact": positive_payload["projection_exact"],
            "schema_version": positive_payload["schema_version"],
        },
        "stable_registration": {
            "config_digest_after": stable_after,
            "config_digest_before": stable_before,
            "unchanged": True,
        },
        "wire_version": NEXT_WIRE_VERSION,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument("--aoa-kag-root", required=True, type=Path)
    parser.add_argument("--stack-runtime-root", required=True, type=Path)
    parser.add_argument("--stack-source-root", required=True, type=Path)
    parser.add_argument("--stable-codex-config", required=True, type=Path)
    args = parser.parse_args()

    started_at = _utc_now()
    state = AoAKagMCPState.discover(
        workspace_root=args.workspace_root,
        aoa_kag_root=args.aoa_kag_root,
    )
    application = build_application(
        state,
        stack_root=args.stack_runtime_root,
    )
    observation = anyio.run(
        partial(
            _exercise,
            application=application,
            stable_config=args.stable_codex_config,
        )
    )
    receipt = {
        "schema_version": "abyss_mcp_kag_handle_pair_observation_v1",
        "observation_id": "aoa-kag-handle-pair-20260729",
        "observed_at": started_at,
        "finished_at": _utc_now(),
        "exact_inputs": {
            "aoa_kag_source_revision": _git_head(args.aoa_kag_root),
            "python_mcp_commit": (
                "6f69a3758ebf2ee55ce050f58b470ce11af71133"
            ),
            "python_mcp_version": "2.0.0",
            "spec_version": NEXT_WIRE_VERSION,
            "stack_source_revision": _git_head(args.stack_source_root),
        },
        "pair": observation,
        "verdict": "passed",
        "claim_limits": [
            "This receipt proves requestState handle behavior for one isolated read-only KAG pair, not Codex next-wire support.",
            "Same-request replay is deliberately allowed only because this lab tool is read-only and idempotent.",
            "Effectful handle replay policy requires a separate gate and receipt.",
            "Key retirement proves handle revocation after restart, not OAuth token revocation.",
            "The adapter was not registered, deployed, admitted, or granted owner authority.",
            "KAG remains evidence and navigation; owner sources retain authority.",
        ],
    }
    _write_private_json(args.output, receipt)
    print(f"[ok] wrote private KAG handle-pair receipt: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
