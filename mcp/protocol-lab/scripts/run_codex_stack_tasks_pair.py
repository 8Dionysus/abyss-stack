#!/usr/bin/env python3
"""Exercise Codex Tasks against the real abyss-stack MCP 2.0 server."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import socket
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TASKS = "io.modelcontextprotocol/tasks"
PROTOCOL = "2026-07-28"
RUNTIME = Path(
    "/srv/abyss-machine/runtimes/codex-os-abyss-mcp/"
    "0.147.0-abyss.1/bin/codex-os-abyss-mcp"
)
PYTHON = Path("/srv/abyss-machine/cache/mcp-modern-fleet-20260809/venv/bin/python")
OBSERVATION = Path("/srv/AbyssOS/abyss-stack/Logs/mcp/observations/current.json")


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


async def start_app(home: Path, *, extension: bool) -> tuple[AppClient, asyncio.subprocess.Process]:
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
        str(RUNTIME),
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


async def main() -> None:
    started = datetime.now(UTC)
    root = Path("/srv/abyss-machine/cache/mcp-modern-fleet-20260809/evidence") / started.strftime(
        "codex-real-stack-tasks-%Y%m%dT%H%M%SZ"
    )
    root.mkdir(mode=0o700, parents=True)
    task_root = root / "tasks"
    task_root.mkdir(mode=0o700)
    audit = root / "policy-read.jsonl"
    audit.touch(mode=0o600)
    bearer = secrets.token_urlsafe(48)
    port = free_port()
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
    apps: list[asyncio.subprocess.Process] = []
    try:
        await wait_port(port, server)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            home = Path(temporary)
            write_config(home, f"http://127.0.0.1:{port}/mcp", bearer)
            client, app = await start_app(home, extension=True)
            apps.append(app)
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
                    {
                        "threadId": thread,
                        "server": "abyss_stack_tasks",
                        "taskId": task_id,
                    },
                )
                result = polled.get("result", {}).get("result", {})
                if result.get("status") in {"completed", "failed", "cancelled"}:
                    terminal = result
                    break
            await stop(app)
            apps.remove(app)
            if terminal is None or terminal.get("status") != "completed":
                raise RuntimeError(f"task did not complete: {terminal}")

            no_ext, app = await start_app(home, extension=False)
            apps.append(app)
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
            await stop(app)
            apps.remove(app)

        receipt = {
            "schema_version": "codex_real_abyss_stack_tasks_pair_v1",
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "protocol_version": PROTOCOL,
            "server": "abyss-stack-mcp/0.5.2",
            "mcp_sdk": "2.0.0",
            "codex_runtime_sha256": hashlib.sha256(
                RUNTIME.parent.joinpath("codex").read_bytes()
            ).hexdigest(),
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
            "negative_gates": {
                "missing_extension_rejected": "error" in rejected,
                "error": rejected.get("error"),
            },
        }
        receipt["verdict"] = (
            "passed"
            if receipt["task"]["owner"] == "abyss-stack"
            and receipt["task"]["effect_class"] == "observe"
            and receipt["negative_gates"]["missing_extension_rejected"]
            else "failed"
        )
        output = root / "receipt.json"
        output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        os.chmod(output, 0o600)
        if receipt["verdict"] != "passed":
            raise RuntimeError(json.dumps(receipt, indent=2))
        print(output)
    finally:
        for app in apps:
            await stop(app)
        server.terminate()
        await server.wait()


if __name__ == "__main__":
    asyncio.run(main())
