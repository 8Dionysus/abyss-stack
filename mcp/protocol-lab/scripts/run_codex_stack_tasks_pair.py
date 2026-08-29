#!/usr/bin/env python3
"""Exercise Codex Tasks against the configured abyss-stack MCP server."""

from __future__ import annotations

import asyncio
import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TASKS = "io.modelcontextprotocol/tasks"
PROTOCOL = "2026-07-28"
DEFAULT_RUNTIME = Path(
    "/srv/abyss-machine/runtimes/codex-os-abyss-mcp/"
    "0.147.0-abyss.2/bin/codex-os-abyss-mcp"
)
LIVE_ENDPOINT = "http://127.0.0.1:5431/mcp"
LIVE_BEARER_FILE = Path(
    "/srv/AbyssOS/abyss-stack/Secrets/Configs/abyss-stack-mcp-read-bearer-token"
)
PYTHON = Path("/srv/abyss-machine/cache/mcp-modern-fleet-20260809/venv/bin/python")
OBSERVATION = Path("/srv/AbyssOS/abyss-stack/Logs/mcp/observations/current.json")


def installed_mcp_version(python: Path) -> str:
    result = subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            "import importlib.metadata; print(importlib.metadata.version('mcp'))",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"cannot resolve MCP SDK version from {python}: "
            f"{result.stderr.strip()[-400:]}"
        )
    version = result.stdout.strip()
    if not version:
        raise RuntimeError(f"MCP SDK version lookup returned empty output for {python}")
    return version


class AppClient:
    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self.process = process

    async def send(self, message: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        await self.process.stdin.drain()

    async def request(self, request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
        await self.send(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        assert self.process.stdout is not None
        while True:
            line = await asyncio.wait_for(self.process.stdout.readline(), timeout=30)
            if not line:
                assert self.process.stderr is not None
                stderr = (await self.process.stderr.read()).decode(errors="replace")[-4000:]
                raise RuntimeError(f"app-server exited: {stderr}")
            message = json.loads(line)
            if message.get("id") == request_id:
                return message


def free_port() -> int:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    return port


def write_config(home: Path, endpoint: str, bearer: str) -> None:
    (home / "config.toml").write_text(
        f'''model = "mock-model"
model_provider = "mock"
approval_policy = "never"
sandbox_mode = "read-only"

[model_providers.mock]
name = "mock"
base_url = "http://127.0.0.1:9/v1"
wire_api = "responses"

[mcp_servers.abyss_stack_tasks]
url = "{endpoint}"
http_headers = {{ Authorization = "Bearer {bearer}" }}
''',
        encoding="utf-8",
    )
    os.chmod(home / "config.toml", 0o600)


async def wait_port(port: int, process: asyncio.subprocess.Process) -> None:
    for _ in range(200):
        if process.returncode is not None:
            assert process.stderr is not None
            raise RuntimeError((await process.stderr.read()).decode(errors="replace"))
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.05)
            continue
        writer.close()
        await writer.wait_closed()
        return
    raise TimeoutError("real abyss-stack MCP server did not bind")


async def start_app(
    home: Path,
    runtime: Path,
    *,
    extension: bool,
) -> tuple[AppClient, asyncio.subprocess.Process]:
    env = os.environ.copy()
    env.update(
        {
            "CODEX_HOME": str(home),
            "CODEX_MCP_2026_SERVERS": "abyss_stack_tasks",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )
    process = await asyncio.create_subprocess_exec(
        str(runtime),
        "app-server",
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    client = AppClient(process)
    initialized = await client.request(
        1,
        "initialize",
        {
            "clientInfo": {"name": "abyss-stack-real-pair", "version": "1"},
            "capabilities": {
                "experimentalApi": True,
                "extensions": {TASKS: {}} if extension else {},
            },
        },
    )
    if "error" in initialized:
        raise RuntimeError(f"app initialize failed: {initialized}")
    await client.send({"jsonrpc": "2.0", "method": "initialized"})
    return client, process


async def stop(process: asyncio.subprocess.Process) -> None:
    if process.stdin is not None:
        process.stdin.close()
    try:
        await asyncio.wait_for(process.wait(), timeout=10)
    except TimeoutError:
        process.terminate()
        await process.wait()


def load_bearer(path: Path) -> str:
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o777 != 0o600:
        raise RuntimeError(f"unsafe Tasks bearer file: {path}")
    bearer = path.read_text(encoding="utf-8").strip()
    if not 43 <= len(bearer) <= 512:
        raise RuntimeError("invalid Tasks bearer")
    return bearer


async def exercise_pair(
    root: Path,
    runtime: Path,
    endpoint: str,
    bearer: str,
) -> dict[str, Any]:
    apps: list[asyncio.subprocess.Process] = []
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        home = Path(temporary)
        write_config(home, endpoint, bearer)
        client, app = await start_app(home, runtime, extension=True)
        apps.append(app)
        try:
            thread = (
                await client.request(
                    2, "thread/start", {"cwd": "/home/dionysus", "model": "mock-model"}
                )
            )["result"]["thread"]["id"]
            started_task = await client.request(
                3,
                "mcpServer/task/start",
                {
                    "threadId": thread,
                    "server": "abyss_stack_tasks",
                    "tool": "stack_runtime_inspect_task",
                    "arguments": {
                        "organ_id": "aoa-kag",
                        "policy_family": "read",
                        "view": "identity",
                    },
                },
            )
            if "error" in started_task:
                raise RuntimeError(json.dumps(started_task))
            task_id = started_task["result"]["result"]["taskId"]
            terminal: dict[str, Any] | None = None
            for request_id in range(4, 44):
                await asyncio.sleep(0.3)
                polled = await client.request(
                    request_id,
                    "mcpServer/task/get",
                    {"threadId": thread, "server": "abyss_stack_tasks", "taskId": task_id},
                )
                result = polled.get("result", {}).get("result", {})
                if result.get("status") in {"completed", "failed", "cancelled"}:
                    terminal = result
                    break
            if terminal is None or terminal.get("status") != "completed":
                raise RuntimeError(f"task did not complete: {terminal}")

            cancel_started = await client.request(
                44,
                "mcpServer/task/start",
                {
                    "threadId": thread,
                    "server": "abyss_stack_tasks",
                    "tool": "stack_runtime_inspect_task",
                    "arguments": {"organ_id": "aoa-kag", "policy_family": "read"},
                },
            )
            if "error" in cancel_started:
                raise RuntimeError(json.dumps(cancel_started))
            cancelled_task_id = cancel_started["result"]["result"]["taskId"]
            cancelled = await client.request(
                45,
                "mcpServer/task/cancel",
                {
                    "threadId": thread,
                    "server": "abyss_stack_tasks",
                    "taskId": cancelled_task_id,
                },
            )
            if "error" in cancelled:
                raise RuntimeError(f"task cancel failed: {cancelled}")
            cancelled_get = await client.request(
                46,
                "mcpServer/task/get",
                {
                    "threadId": thread,
                    "server": "abyss_stack_tasks",
                    "taskId": cancelled_task_id,
                },
            )
            cancelled_status = cancelled_get.get("result", {}).get("result", {}).get("status")
        finally:
            await stop(app)
            apps.remove(app)

        no_ext, app = await start_app(home, runtime, extension=False)
        apps.append(app)
        try:
            no_ext_thread = (
                await no_ext.request(
                    50, "thread/start", {"cwd": "/home/dionysus", "model": "mock-model"}
                )
            )["result"]["thread"]["id"]
            rejected = await no_ext.request(
                51,
                "mcpServer/task/start",
                {
                    "threadId": no_ext_thread,
                    "server": "abyss_stack_tasks",
                    "tool": "stack_runtime_inspect_task",
                    "arguments": {"organ_id": "aoa-kag"},
                },
            )
        finally:
            await stop(app)
            apps.remove(app)

    return {
        "completed": terminal,
        "completed_task_id": task_id,
        "cancelled_task_id": cancelled_task_id,
        "cancel_acknowledged": "error" not in cancelled,
        "cancelled_status": cancelled_status,
        "missing_extension": rejected,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--live-production", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.runtime.is_file():
        raise RuntimeError(f"missing Codex Tasks runtime: {args.runtime}")
    started = datetime.now(UTC)
    root = Path("/srv/abyss-machine/cache/mcp-modern-fleet-20260809/evidence") / started.strftime(
        "codex-real-stack-tasks-%Y%m%dT%H%M%SZ"
    )
    root.mkdir(mode=0o700, parents=True)
    server: asyncio.subprocess.Process | None = None
    try:
        if args.live_production:
            bearer = load_bearer(LIVE_BEARER_FILE)
            endpoint = LIVE_ENDPOINT
        else:
            task_root = root / "tasks"
            task_root.mkdir(mode=0o700)
            audit = root / "policy-read.jsonl"
            audit.touch(mode=0o600)
            bearer = secrets.token_urlsafe(48)
            port = free_port()
            endpoint = f"http://127.0.0.1:{port}/mcp"
            env = os.environ.copy()
            env.update(
                {
                    "AOA_MCP_TRANSPORT": "streamable-http",
                    "AOA_MCP_HOST": "127.0.0.1",
                    "AOA_MCP_PORT": str(port),
                    "ABYSS_STACK_MCP_POLICY_FAMILY": "read",
                    "ABYSS_STACK_MCP_READ_BEARER_TOKEN": bearer,
                    "ABYSS_STACK_MCP_OBSERVATION_PATH": str(OBSERVATION),
                    "ABYSS_STACK_MCP_AUDIT_JOURNAL_PATH": str(audit),
                    "ABYSS_STACK_MCP_REQUIRE_AUDIT_JOURNAL": "1",
                    "ABYSS_STACK_MCP_TASKS_ENABLED": "1",
                    "ABYSS_STACK_MCP_TASK_ROOT": str(task_root),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            server = await asyncio.create_subprocess_exec(
                str(PYTHON),
                "-I",
                "-B",
                "-m",
                "abyss_stack_mcp.server",
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await wait_port(port, server)
        pair = await exercise_pair(root, args.runtime, endpoint, bearer)
        terminal = pair["completed"]
        task_id = pair["completed_task_id"]
        rejected = pair["missing_extension"]

        receipt = {
            "schema_version": "codex_real_abyss_stack_tasks_pair_v1",
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "protocol_version": PROTOCOL,
            "server": "abyss-stack-mcp/0.5.2",
            "mcp_sdk": installed_mcp_version(PYTHON),
            "codex_runtime": args.runtime.parents[1].name,
            "codex_runtime_sha256": hashlib.sha256(
                args.runtime.parent.joinpath("codex").read_bytes()
            ).hexdigest(),
            "production_pair": args.live_production,
            "task": {
                "status": terminal["status"],
                "task_id_digest": "sha256:"
                + hashlib.sha256(task_id.encode()).hexdigest(),
                "owner": terminal["result"]["structuredContent"]["metadata"][
                    "access_owner"
                ],
                "effect_class": terminal["result"]["structuredContent"]["metadata"][
                    "effect_class"
                ],
            },
            "cancellation": {
                "acknowledged": pair["cancel_acknowledged"],
                "status": pair["cancelled_status"],
                "task_id_digest": "sha256:"
                + hashlib.sha256(pair["cancelled_task_id"].encode()).hexdigest(),
            },
            "negative_gates": {
                "missing_extension_rejected": "error" in rejected,
                "error": rejected.get("error"),
            },
        }
        receipt["verdict"] = (
            "passed"
            if receipt["task"]["owner"] == "abyss-stack"
            and receipt["task"]["effect_class"] == "observe"
            and receipt["cancellation"]["acknowledged"]
            and receipt["cancellation"]["status"] == "cancelled"
            and receipt["negative_gates"]["missing_extension_rejected"]
            else "failed"
        )
        output = args.output or root / "receipt.json"
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        os.chmod(output, 0o600)
        if receipt["verdict"] != "passed":
            raise RuntimeError(json.dumps(receipt, indent=2))
        print(output)
    finally:
        if server is not None:
            server.terminate()
            await server.wait()


if __name__ == "__main__":
    asyncio.run(main())
