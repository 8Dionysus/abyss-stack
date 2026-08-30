#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import anyio
import uvicorn
from mcp.client import Client
from mcp.client.caching import CacheConfig
from mcp.client.subscriptions import ToolsListChanged
from mcp.server import CacheHint, MCPServer, ServerRequestContext
from mcp.server.subscriptions import (
    InMemorySubscriptionBus,
    ToolsListChanged as ServerToolsListChanged,
)
from mcp.shared.exceptions import MCPError
from mcp_types import Implementation, ToolAnnotations

from aoa_kag_mcp.core import AoAKagMCPState
from aoa_kag_mcp.runtime import build_application
from runtime_catalog import load_runtime_catalog, mcp_settings


_SDK_SETTINGS, _PROTOCOL_SETTINGS, _TRANSPORT_SETTINGS = mcp_settings(
    load_runtime_catalog()
)
NEXT_WIRE_VERSION = str(_PROTOCOL_SETTINGS["version"])
MCP_PATH = str(_PROTOCOL_SETTINGS["streamable_http_path"])
MCP_HOST = str(_TRANSPORT_SETTINGS["default_host"])
PYTHON_MCP_VERSION = str(_SDK_SETTINGS["tested_lock"])
PYTHON_MCP_COMMIT = str(_SDK_SETTINGS["source_revision"])
CACHE_TTL_MS = 30_000
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


class ManualClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def time(self) -> float:
        return self.now


class CatalogRecorder:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> Any:
        record = {
            "method": ctx.method,
            "outcome": "entered",
            "protocol_version": ctx.protocol_version,
        }
        self.records.append(record)
        result = await call_next(ctx)
        record["outcome"] = "passed"
        return result

    def passed_tools_list_count(self) -> int:
        return sum(
            item["method"] == "tools/list"
            and item["outcome"] == "passed"
            for item in self.records
        )


def _tool_names(result: Any) -> list[str]:
    return sorted(tool.name for tool in result.tools)


def build_cache_server(
    application: Any,
    bus: InMemorySubscriptionBus,
    recorder: CatalogRecorder,
) -> MCPServer:
    server = MCPServer(
        name="aoa-kag-next-cache-lab",
        title="AoA KAG cache behavior protocol lab",
        description=(
            "Isolated read-only KAG catalog cache probe. "
            "Catalog state grants no owner or effect authority."
        ),
        version="0.1.0-lab",
        cache_hints={
            "server/discover": CacheHint(
                ttl_ms=CACHE_TTL_MS,
                scope="private",
            ),
            "tools/list": CacheHint(
                ttl_ms=CACHE_TTL_MS,
                scope="private",
            ),
        },
        subscriptions=bus,
        middleware=[recorder],
    )

    @server.tool(
        name="kag_discover",
        description="Discover one owner-qualified KAG evidence surface.",
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    def kag_discover(owner: str) -> dict[str, Any]:
        result = application.discover(owner=owner, detail="compact")
        return {
            "degradation": result["degradation"],
            "owner": result["owners"][0]["repo"],
            "schema_version": result["schema_version"],
        }

    return server


@asynccontextmanager
async def _running_server(server: MCPServer) -> AsyncIterator[str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((MCP_HOST, 0))
    listener.listen(128)
    listener.setblocking(False)
    port = int(listener.getsockname()[1])
    uvicorn_server = uvicorn.Server(
        uvicorn.Config(
            server.streamable_http_app(
                streamable_http_path=MCP_PATH,
                json_response=True,
                stateless_http=True,
                host=MCP_HOST,
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
            yield f"http://{MCP_HOST}:{port}{MCP_PATH}"
        finally:
            uvicorn_server.should_exit = True


async def _exercise(
    *,
    server: MCPServer,
    bus: InMemorySubscriptionBus,
    recorder: CatalogRecorder,
    stable_config: Path,
) -> dict[str, Any]:
    clock = ManualClock(2_000_000_000.0)
    stable_before = _digest(stable_config)
    stale_probe_invocations: list[str] = []

    def transient_probe() -> str:
        return "transient"

    def stale_probe() -> str:
        stale_probe_invocations.append("called")
        return "stale"

    async with _running_server(server) as url:
        async with Client(
            url,
            mode=NEXT_WIRE_VERSION,
            raise_exceptions=True,
            client_info=Implementation(
                name="os-abyss-kag-cache-probe",
                version="1.0.0",
            ),
            cache=CacheConfig(clock=clock.time),
        ) as client:
            first = await client.list_tools()
            repeat = await client.list_tools()
            if first != repeat or recorder.passed_tools_list_count() != 1:
                raise RuntimeError("tools/list did not hit the private cache")
            if _tool_names(first) != ["kag_discover"]:
                raise RuntimeError("initial KAG cache inventory drifted")
            if (
                first.ttl_ms != CACHE_TTL_MS
                or first.cache_scope != "private"
            ):
                raise RuntimeError("KAG cache hint drifted")

            async with client.listen(tools_list_changed=True) as subscription:
                if not subscription.honored.tools_list_changed:
                    raise RuntimeError("tools list subscription was not honored")

                server.add_tool(
                    transient_probe,
                    name="kag_transient_probe",
                    description="Lab-only transient catalog probe.",
                )
                await bus.publish(ServerToolsListChanged())
                if not isinstance(await anext(subscription), ToolsListChanged):
                    raise RuntimeError("tool addition event was not delivered")
                added = await client.list_tools()
                if recorder.passed_tools_list_count() != 2:
                    raise RuntimeError(
                        "subscription addition did not evict the catalog cache"
                    )
                if _tool_names(added) != [
                    "kag_discover",
                    "kag_transient_probe",
                ]:
                    raise RuntimeError("invalidated catalog omitted added tool")

                server.remove_tool("kag_transient_probe")
                await bus.publish(ServerToolsListChanged())
                if not isinstance(await anext(subscription), ToolsListChanged):
                    raise RuntimeError("tool removal event was not delivered")
                revoked = await client.list_tools()
                if recorder.passed_tools_list_count() != 3:
                    raise RuntimeError(
                        "subscription revocation did not evict the catalog cache"
                    )
                if _tool_names(revoked) != ["kag_discover"]:
                    raise RuntimeError("revoked tool remained after invalidation")

            server.add_tool(
                stale_probe,
                name="kag_stale_probe",
                description="Lab-only stale catalog probe.",
            )
            await bus.publish(ServerToolsListChanged())
            stale_before_expiry = await client.list_tools()
            if recorder.passed_tools_list_count() != 3:
                raise RuntimeError("unsubscribed event unexpectedly evicted cache")
            if "kag_stale_probe" in _tool_names(stale_before_expiry):
                raise RuntimeError("unsubscribed catalog did not remain cached")

            clock.now += CACHE_TTL_MS / 1000
            after_expiry = await client.list_tools()
            if recorder.passed_tools_list_count() != 4:
                raise RuntimeError("catalog was not refetched at exact TTL expiry")
            if "kag_stale_probe" not in _tool_names(after_expiry):
                raise RuntimeError("TTL refresh omitted the added catalog entry")

            server.remove_tool("kag_stale_probe")
            stale_after_removal = await client.list_tools()
            if recorder.passed_tools_list_count() != 4:
                raise RuntimeError("warm stale catalog unexpectedly refetched")
            if "kag_stale_probe" not in _tool_names(stale_after_removal):
                raise RuntimeError("stale catalog behavior was not reproduced")

            stale_call_denial = None
            try:
                stale_call = await client.call_tool("kag_stale_probe", {})
            except MCPError as exc:
                stale_call_denial = {
                    "code": exc.code,
                    "message": exc.message,
                }
            else:
                if stale_call.is_error:
                    dumped = stale_call.model_dump(
                        by_alias=True,
                        mode="json",
                        exclude_none=True,
                    )
                    stale_call_denial = {
                        "is_error": True,
                        "content": dumped.get("content"),
                    }
            if not stale_call_denial or stale_probe_invocations:
                raise RuntimeError("stale catalog authorized a removed tool")

            refreshed = await client.list_tools(cache_mode="refresh")
            if "kag_stale_probe" in _tool_names(refreshed):
                raise RuntimeError("explicit cache refresh retained removed tool")
            refreshed_repeat = await client.list_tools()
            if refreshed_repeat != refreshed:
                raise RuntimeError("explicit refresh did not replace cache entry")

    stable_after = _digest(stable_config)
    if stable_after != stable_before:
        raise RuntimeError("stable Codex config changed during cache proof")

    return {
        "cache": {
            "scope": "private",
            "ttl_ms": CACHE_TTL_MS,
            "within_ttl_repeat_server_fetches": 1,
        },
        "checks": {
            "explicit_refresh_replaces_stale_entry": True,
            "no_subscription_no_replay": True,
            "stale_catalog_cannot_authorize_removed_tool": stale_call_denial,
            "subscription_addition_invalidation": True,
            "subscription_removal_revocation": True,
            "ttl_expiry_refetch": True,
        },
        "inventories": {
            "initial": _tool_names(first),
            "after_subscription_add": _tool_names(added),
            "after_subscription_remove": _tool_names(revoked),
            "stale_before_expiry": _tool_names(stale_before_expiry),
            "after_ttl_expiry": _tool_names(after_expiry),
            "stale_after_removal": _tool_names(stale_after_removal),
            "after_explicit_refresh": _tool_names(refreshed),
        },
        "stable_registration": {
            "config_digest_after": stable_after,
            "config_digest_before": stable_before,
            "unchanged": True,
        },
        "stateless_http": True,
        "subscription": {
            "events_consumed": 2,
            "tools_list_changed_honored": True,
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
    bus = InMemorySubscriptionBus()
    recorder = CatalogRecorder()
    server = build_cache_server(application, bus, recorder)
    observation = anyio.run(
        partial(
            _exercise,
            server=server,
            bus=bus,
            recorder=recorder,
            stable_config=args.stable_codex_config,
        )
    )
    receipt = {
        "schema_version": "abyss_mcp_kag_cache_pair_observation_v1",
        "observation_id": "aoa-kag-cache-pair-20260729",
        "observed_at": started_at,
        "finished_at": _utc_now(),
        "exact_inputs": {
            "aoa_kag_source_revision": _git_head(args.aoa_kag_root),
            "python_mcp_commit": PYTHON_MCP_COMMIT,
            "python_mcp_version": PYTHON_MCP_VERSION,
            "spec_version": NEXT_WIRE_VERSION,
            "stack_source_revision": _git_head(args.stack_source_root),
        },
        "pair": observation,
        "verdict": "passed",
        "claim_limits": [
            "This receipt proves isolated KAG catalog cache behavior, not Codex next-wire support.",
            "A cached catalog is discovery data and never grants tool authorization.",
            "Subscription invalidation is process-local in this proof; replica fan-out requires a production bus receipt.",
            "No subscription replay exists; reconnecting consumers must refetch.",
            "The adapter was not registered, deployed, admitted, or granted owner authority.",
            "No candidate, memory, source mutation, or external effect was performed.",
        ],
    }
    _write_private_json(args.output, receipt)
    print(f"[ok] wrote private KAG cache-pair receipt: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
