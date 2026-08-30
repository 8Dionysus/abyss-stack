#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
from builtins import BaseExceptionGroup
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import anyio
import mcp_types
import uvicorn
from mcp.client import Client
from mcp.client.caching import CacheConfig
from mcp.server import CacheHint, MCPServer, ServerRequestContext
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.shared.exceptions import MCPError
from mcp_types import Implementation, ToolAnnotations

from aoa_kag_mcp.core import AoAKagMCPState
from aoa_kag_mcp.runtime import build_application
from _mcp_sdk_identity import installed_mcp_identity


NEXT_WIRE_VERSION = "2026-07-28"
MAX_INPUT_BYTES = 16_384
MAX_OUTPUT_BYTES = 262_144
CANCELLATION_META_KEY = "io.os-abyss.protocol-lab/cancel-delay-ms"
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
READ_METHODS = frozenset(
    {
        "server/discover",
        "tools/list",
        "tools/call",
        "resources/list",
        "resources/templates/list",
        "resources/read",
    }
)
CallNext = Callable[[ServerRequestContext[Any, Any]], Awaitable[Any]]


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


class AccessRecorder:
    """Fail-closed lab middleware and bounded wire observation collector."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> Any:
        raw_params = ctx.params if isinstance(ctx.params, Mapping) else {}
        raw_meta = raw_params.get("_meta")
        meta = dict(raw_meta) if isinstance(raw_meta, Mapping) else {}
        client_capabilities = meta.get(
            "io.modelcontextprotocol/clientCapabilities"
        )
        capability_extensions = (
            client_capabilities.get("extensions")
            if isinstance(client_capabilities, Mapping)
            else None
        )
        request = ctx.request
        headers = getattr(request, "headers", {})
        record = {
            "method": ctx.method,
            "protocol_version": ctx.protocol_version,
            "has_client_info": (
                "io.modelcontextprotocol/clientInfo" in meta
            ),
            "has_client_capabilities": (
                "io.modelcontextprotocol/clientCapabilities" in meta
            ),
            "client_capability_extensions": capability_extensions,
            "traceparent": meta.get("traceparent"),
            "protocol_header": headers.get("mcp-protocol-version"),
            "session_header_present": "mcp-session-id" in headers,
            "can_send_server_request": ctx.session.can_send_request,
            "authenticated_principal": None,
            "input_bytes": len(
                json.dumps(
                    raw_params,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                    default=str,
                ).encode()
            ),
            "output_bytes": None,
            "outcome": "entered",
        }
        access_token = get_access_token()
        if access_token is not None:
            record["authenticated_principal"] = {
                "client_id": access_token.client_id,
                "issuer": access_token.claims.get("iss"),
                "subject": access_token.subject,
            }
        if record["input_bytes"] > MAX_INPUT_BYTES:
            record["outcome"] = "denied_input_limit"
            raise MCPError(
                code=mcp_types.INVALID_PARAMS,
                message="The isolated KAG next request exceeds its byte limit.",
                data={"limit_bytes": MAX_INPUT_BYTES},
            )
        # Publish the bounded record before an await that may be cancelled.
        # The same object is updated in place, so the observer can prove that
        # dispatch was entered and then cancelled instead of mistaking the
        # absence of a post-await append for an unobserved worker.
        self.records.append(record)
        cancel_delay_ms = meta.get(CANCELLATION_META_KEY)
        if cancel_delay_ms is not None:
            if not isinstance(cancel_delay_ms, int) or not 1 <= cancel_delay_ms <= 10_000:
                record["outcome"] = "denied_cancellation_probe"
                raise MCPError(
                    code=mcp_types.INVALID_PARAMS,
                    message="The isolated cancellation delay is invalid.",
                )
            try:
                await anyio.sleep(cancel_delay_ms / 1000)
            except anyio.get_cancelled_exc_class():
                record["outcome"] = "cancelled"
                raise

        if ctx.method == "initialize":
            record["outcome"] = "denied_legacy"
            raise MCPError(
                code=mcp_types.UNSUPPORTED_PROTOCOL_VERSION,
                message="The isolated next adapter requires MCP 2026-07-28.",
                data={"supported": [NEXT_WIRE_VERSION]},
            )
        if ctx.method not in READ_METHODS:
            record["outcome"] = "denied_method"
            raise MCPError(
                code=mcp_types.METHOD_NOT_FOUND,
                message="The isolated KAG next adapter exposes read methods only.",
            )
        if ctx.method == "tools/call":
            tool_name = raw_params.get("name")
            if tool_name != "kag_discover":
                record["outcome"] = "denied_tool"
                raise MCPError(
                    code=mcp_types.METHOD_NOT_FOUND,
                    message="Tool is outside the compact read-only next pilot.",
                )
        if ctx.method == "resources/read":
            uri = str(raw_params.get("uri") or "")
            if uri != "aoa-kag-next://capabilities":
                record["outcome"] = "denied_resource"
                raise MCPError(
                    code=mcp_types.RESOURCE_NOT_FOUND,
                    message="Resource is outside the compact read-only next pilot.",
                )

        result = await call_next(ctx)
        dumped = (
            result.model_dump(by_alias=True, mode="json", exclude_none=True)
            if hasattr(result, "model_dump")
            else result
        )
        record["output_bytes"] = len(
            json.dumps(
                dumped,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
                default=str,
            ).encode()
        )
        if record["output_bytes"] > MAX_OUTPUT_BYTES:
            record["outcome"] = "denied_output_limit"
            raise MCPError(
                code=mcp_types.INTERNAL_ERROR,
                message="The isolated KAG next response exceeds its byte limit.",
                data={"limit_bytes": MAX_OUTPUT_BYTES},
            )
        record["outcome"] = "passed"
        return result


def build_next_server(
    application: Any,
    recorder: AccessRecorder,
    *,
    token_verifier: Any | None = None,
    auth: Any | None = None,
) -> MCPServer:
    annotations = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
    server = MCPServer(
        name="aoa-kag-next-lab",
        title="AoA KAG isolated next-protocol lab",
        description=(
            "Compact read-only KAG adapter for MCP 2026-07-28 pair proof. "
            "It has no owner, candidate, or effect authority."
        ),
        instructions=(
            "Discover only the requested KAG owner. Treat returned KAG data as "
            "evidence/navigation and follow owner refs for authority."
        ),
        version="0.1.0-lab",
        cache_hints={
            "server/discover": CacheHint(ttl_ms=30_000, scope="private"),
            "tools/list": CacheHint(ttl_ms=30_000, scope="private"),
            "resources/list": CacheHint(ttl_ms=5_000, scope="private"),
            "resources/templates/list": CacheHint(
                ttl_ms=5_000,
                scope="private",
            ),
            "resources/read": CacheHint(ttl_ms=0, scope="private"),
        },
        middleware=[recorder],
        token_verifier=token_verifier,
        auth=auth,
    )

    @server.tool(
        name="kag_discover",
        description=(
            "Discover one owner-qualified KAG capability surface without "
            "creating memory, proof, acceptance, or source changes."
        ),
        annotations=annotations,
        structured_output=True,
    )
    def kag_discover(
        owner: str,
        detail: Literal["compact", "summary"] = "compact",
    ) -> dict[str, Any]:
        result = application.discover(owner=owner, detail=detail)
        if result.get("schema_version") != "aoa-kag-mcp-capabilities-v1":
            raise RuntimeError("owner KAG capability schema identity drifted")
        if any(item.get("repo") != owner for item in result.get("owners", [])):
            raise RuntimeError("owner-qualified KAG result crossed its owner bound")
        return result

    @server.resource(
        "aoa-kag-next://capabilities",
        name="kag_next_capabilities",
        description="Compact read-only next-protocol KAG capabilities.",
        mime_type="application/json",
    )
    def capabilities() -> str:
        return json.dumps(
            application.discover(owner="abyss-stack", detail="compact"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )

    return server


def _result_payload(result: Any) -> dict[str, Any]:
    dumped = result.model_dump(by_alias=True, mode="json", exclude_none=True)
    structured = dumped.get("structuredContent")
    if not isinstance(structured, dict):
        raise RuntimeError("KAG next adapter did not return structuredContent")
    return structured


def _group_mcp_error(group: BaseExceptionGroup) -> MCPError | None:
    for exception in group.exceptions:
        if isinstance(exception, MCPError):
            return exception
        if isinstance(exception, BaseExceptionGroup):
            nested = _group_mcp_error(exception)
            if nested is not None:
                return nested
    return None


async def _exercise_pair(
    server: MCPServer,
    recorder: AccessRecorder,
) -> dict[str, Any]:
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        # The 2026-07-28 transport expresses cancellation by closing the
        # request's SSE response stream. Python MCP 2.1.1 can return JSON, but
        # that shortcut has no disconnect watcher and therefore lets the
        # dispatch continue after a client gives up. Keep the modern contour
        # on SSE so disconnect reaches the handler/worker cancel scope.
        json_response=False,
        stateless_http=True,
        host="127.0.0.1",
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    port = int(listener.getsockname()[1])
    url = f"http://127.0.0.1:{port}/mcp"
    uvicorn_server = uvicorn.Server(
        uvicorn.Config(
            app,
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
            client_info = Implementation(
                name="os-abyss-kag-next-pair-probe",
                version="1.0.0",
            )
            async with Client(
                url,
                mode="auto",
                raise_exceptions=True,
                client_info=client_info,
                cache=CacheConfig(),
            ) as client:
                discover = client.session.discover_result
                if discover is None:
                    raise RuntimeError("modern client did not retain server/discover")
                discover_dump = discover.model_dump(
                    by_alias=True,
                    mode="json",
                    exclude_none=True,
                )
                if NEXT_WIRE_VERSION not in discover_dump["supportedVersions"]:
                    raise RuntimeError("server/discover omitted the next wire version")

                first_tools = await client.list_tools()
                second_tools = await client.list_tools()
                if first_tools != second_tools:
                    raise RuntimeError("private tools/list cache changed the result")
                first_client_tools_fetches = sum(
                    item["outcome"] == "passed"
                    and item["method"] == "tools/list"
                    for item in recorder.records
                )
                if first_client_tools_fetches != 1:
                    raise RuntimeError(
                        "tools/list repeat was not served from the private cache: "
                        f"wire_fetches={first_client_tools_fetches}, "
                        f"ttl_ms={first_tools.ttl_ms}, "
                        f"scope={first_tools.cache_scope}"
                    )
                tool_names = [tool.name for tool in first_tools.tools]
                if tool_names != ["kag_discover"]:
                    raise RuntimeError("next pilot exposed tools outside kag_discover")

                resources = await client.list_resources()
                if [str(item.uri) for item in resources.resources] != [
                    "aoa-kag-next://capabilities"
                ]:
                    raise RuntimeError("next pilot resource inventory drifted")
                resource = await client.read_resource(
                    "aoa-kag-next://capabilities"
                )
                resource_dump = resource.model_dump(
                    by_alias=True,
                    mode="json",
                    exclude_none=True,
                )

                call = await client.call_tool(
                    "kag_discover",
                    {"owner": "abyss-stack", "detail": "compact"},
                    meta={"traceparent": TRACEPARENT},
                )
                capability = _result_payload(call)
                call_dump = call.model_dump(
                    by_alias=True,
                    mode="json",
                    exclude_none=True,
                )

                denied_effect = None
                try:
                    await client.call_tool("kag_write", {})
                except MCPError as exc:
                    denied_effect = {
                        "code": exc.code,
                        "message": exc.message,
                    }
                if not denied_effect:
                    raise RuntimeError("unknown effect-like tool was not denied")

                with anyio.move_on_after(0.1) as cancellation_scope:
                    await client.call_tool(
                        "kag_discover",
                        {"owner": "abyss-stack", "detail": "compact"},
                        meta={CANCELLATION_META_KEY: 5_000},
                    )
                if not cancellation_scope.cancel_called:
                    raise RuntimeError("cancellation probe completed instead of cancelling")
                with anyio.fail_after(7):
                    while not any(
                        item["method"] == "tools/call"
                        and item["outcome"] in {"cancelled", "passed"}
                        and item.get("traceparent") is None
                        and item.get("input_bytes", 0) > 100
                        for item in recorder.records
                    ):
                        await anyio.sleep(0.01)
                cancellation_record = next(
                    item
                    for item in reversed(recorder.records)
                    if item["method"] == "tools/call"
                    and item["outcome"] in {"cancelled", "passed"}
                    and item.get("traceparent") is None
                    and item.get("input_bytes", 0) > 100
                )

            async with Client(
                url,
                mode="auto",
                raise_exceptions=True,
                client_info=client_info,
            ) as independent:
                second_call = await independent.call_tool(
                    "kag_discover",
                    {"owner": "abyss-stack", "detail": "compact"},
                )
                if _result_payload(second_call)["schema_version"] != capability[
                    "schema_version"
                ]:
                    raise RuntimeError("independent stateless request changed schema")

            legacy_denial = None
            try:
                async with Client(
                    url,
                    mode="legacy",
                    raise_exceptions=True,
                    client_info=client_info,
                ):
                    pass
            except MCPError as exc:
                legacy_denial = {
                    "code": exc.code,
                    "message": exc.message,
                }
            except BaseExceptionGroup as group:
                exc = _group_mcp_error(group)
                if exc is None:
                    raise
                legacy_denial = {
                    "code": exc.code,
                    "message": exc.message,
                }
            if (
                not legacy_denial
                or legacy_denial["code"]
                != mcp_types.UNSUPPORTED_PROTOCOL_VERSION
            ):
                raise RuntimeError("legacy client was not denied with -32022")
        finally:
            uvicorn_server.should_exit = True

    passed_records = [
        item for item in recorder.records if item["outcome"] == "passed"
    ]
    modern_records = [
        item
        for item in recorder.records
        if item["protocol_version"] == NEXT_WIRE_VERSION
    ]
    trace_records = [
        item for item in recorder.records if item["traceparent"] == TRACEPARENT
    ]
    tools_list_records = [
        item
        for item in passed_records
        if item["method"] == "tools/list"
    ]
    if not trace_records:
        raise RuntimeError("traceparent was not preserved into server middleware")
    if any(item["session_header_present"] for item in modern_records):
        raise RuntimeError("modern requests unexpectedly carried a session header")
    if any(item["can_send_server_request"] for item in modern_records):
        raise RuntimeError("stateless modern requests exposed a back-channel")
    if any(
        not item["has_client_info"] or not item["has_client_capabilities"]
        for item in modern_records
    ):
        raise RuntimeError("modern request envelope was not self-describing")
    if any(item["protocol_header"] != NEXT_WIRE_VERSION for item in modern_records):
        raise RuntimeError("modern HTTP protocol header drifted")

    projection = capability["projection"]
    exact_target = projection["targets"]["exact"]
    if exact_target["state"] != "current":
        raise RuntimeError("KAG exact target is not current")

    return {
        "wire_version": NEXT_WIRE_VERSION,
        "server_discover": discover_dump,
        "tool_inventory": tool_names,
        "resource_inventory": [
            str(item.uri) for item in resources.resources
        ],
        "resource_result_type": resource_dump.get("resultType"),
        "call_result_type": call_dump.get("resultType"),
        "call_server_info": call_dump.get("_meta", {}).get(
            "io.modelcontextprotocol/serverInfo"
        ),
        "owner_canary": {
            "owner": capability["owners"][0]["repo"],
            "schema_version": capability["schema_version"],
            "runtime_source_digest": capability["owners"][0].get(
                "runtime_source_digest"
            ),
            "freshness": capability["owners"][0].get("freshness"),
            "projection_exact": exact_target,
            "degradation": capability["degradation"],
        },
        "cache": {
            "repeat_tools_list_wire_fetches": first_client_tools_fetches,
            "tools_list_middleware_dispatches_across_full_probe": len(
                tools_list_records
            ),
            "ttl_ms": first_tools.ttl_ms,
            "scope": first_tools.cache_scope,
        },
        "stateless": {
            "configured": True,
            "independent_clients": 2,
            "session_header_observed": False,
            "server_request_backchannel_observed": False,
            "self_describing_requests": len(modern_records),
        },
        "trace": {
            "sent": TRACEPARENT,
            "observed": trace_records[0]["traceparent"],
        },
        "denials": {
            "effect_like_tool": denied_effect,
            "legacy_client": legacy_denial,
        },
        "cancellation": {
            "client_request_cancelled": True,
            "server_dispatch_cancelled": cancellation_record["outcome"]
            == "cancelled",
            "server_dispatch_completed_after_client_cancel": (
                cancellation_record["outcome"] == "passed"
            ),
        },
        "transport_response_mode": "sse_disconnect_cancellable",
        "request_dispatch_records": recorder.records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument("--aoa-kag-root", required=True, type=Path)
    parser.add_argument("--stack-runtime-root", required=True, type=Path)
    parser.add_argument("--stack-source-root", required=True, type=Path)
    parser.add_argument("--stable-codex-config", required=True, type=Path)
    parser.add_argument("--python-sdk-root", required=True, type=Path)
    args = parser.parse_args()

    started_at = _utc_now()
    sdk_identity = installed_mcp_identity(args.python_sdk_root)
    stable_before = _digest(args.stable_codex_config)
    state = AoAKagMCPState.discover(
        workspace_root=args.workspace_root,
        aoa_kag_root=args.aoa_kag_root,
    )
    application = build_application(
        state,
        stack_root=args.stack_runtime_root,
    )
    recorder = AccessRecorder()
    observation = anyio.run(
        _exercise_pair,
        build_next_server(application, recorder),
        recorder,
    )
    stable_after = _digest(args.stable_codex_config)
    if stable_after != stable_before:
        raise RuntimeError("stable Codex configuration changed during next-pair proof")

    receipt = {
        "schema_version": "abyss_mcp_kag_next_pair_observation_v1",
        "observation_id": "aoa-kag-next-pair-20260729",
        "observed_at": started_at,
        "finished_at": _utc_now(),
        "exact_inputs": {
            "spec_version": NEXT_WIRE_VERSION,
            "python_mcp_version": sdk_identity["version"],
            "python_mcp_commit": sdk_identity["commit"],
            "python_mcp_artifact_digest": sdk_identity["artifact_digest"],
            "stack_source_revision": _git_head(args.stack_source_root),
            "aoa_kag_source_revision": _git_head(args.aoa_kag_root),
            "stack_runtime_current_digest": _digest(
                args.stack_runtime_root
                / "Knowledge"
                / "kag"
                / "repo-self"
                / "current.json"
            ),
        },
        "stable_registration": {
            "config_ref": str(args.stable_codex_config),
            "digest_before": stable_before,
            "digest_after": stable_after,
            "unchanged": True,
        },
        "pair": observation,
        "verdict": "passed",
        "claim_limits": [
            "This receipt proves one isolated Python MCP 2.1.1 KAG read pair, not Codex next-wire support.",
            "The adapter was not registered, deployed, credentialed, or admitted.",
            "KAG output remains navigation/evidence; owner sources retain authority.",
            "The owner canary proves a current exact projection for abyss-stack only.",
            "No candidate, memory, proof acceptance, source mutation, or external effect was performed.",
        ],
    }
    _write_private_json(args.output, receipt)
    print(f"[ok] wrote private KAG next-pair receipt: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
