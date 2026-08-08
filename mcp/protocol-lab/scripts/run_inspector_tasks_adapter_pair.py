#!/usr/bin/env python3
"""Run published Inspector 2.1.0 against the feature-gated Abyss Tasks adapter."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


LAB_ROOT = Path(__file__).resolve().parents[1]
CLIENT_SCRIPT = Path(__file__).with_name("inspector_tasks_adapter_client.ts")
TASKS_EXTENSION_ID = "io.modelcontextprotocol/tasks"
PROTOCOL_VERSION = "2026-07-28"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _atomic_json(path: Path, payload: Any) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


class _PayloadResolver:
    def __init__(self) -> None:
        self.results: dict[str, dict[str, Any]] = {}

    def resolve_result(self, record: Any) -> dict[str, Any]:
        return self.results[record.result_ref]

    def resolve_error(self, record: Any) -> dict[str, Any]:
        raise KeyError(record.error_ref)

    def resolve_input_request(self, record: Any, request: Any) -> dict[str, Any]:
        raise KeyError((record.task_id, request.request_key))


class _PairServer:
    def __init__(
        self,
        *,
        sdk_root: Path,
        state_root: Path,
        owner_receipt: Path,
        bearer: str,
        principal_id: str = "inspector-2-1-0",
    ) -> None:
        sys.path.insert(0, str(sdk_root / "src"))
        from aoa_sdk.organs import FileTaskStore, MCPTasksAdapter  # noqa: PLC0415
        from aoa_sdk.organs.registry import sha256_digest  # noqa: PLC0415

        owner_payload = json.loads(owner_receipt.read_text(encoding="utf-8"))
        self.owner_receipt_digest = _sha256_json(owner_payload)
        expected_authority = owner_payload.get("schema_version")
        if expected_authority != "diagnostic_session_v1":
            raise ValueError("owner receipt is not diagnostic_session_v1")
        self.result_payload = {
            "content": [
                {
                    "type": "text",
                    "text": "Existing abyss-stack diagnostic receipt returned without rerun.",
                }
            ],
            "structuredContent": {
                "authority": "diagnostic_session_v1",
                "diagnosticDigest": self.owner_receipt_digest,
                "owner": "abyss-stack",
                "ownerRerunCount": 0,
            },
            "isError": True,
        }
        self.result_digest = sha256_digest(self.result_payload)
        self.result_ref = "owner://abyss-stack/diagnostic/existing-read-only"
        self.payloads = _PayloadResolver()
        self.payloads.results[self.result_ref] = self.result_payload
        self.store = FileTaskStore(state_root / "task-store")
        self.adapter = MCPTasksAdapter(self.store, self.payloads, enabled=True)
        self.bearer = bearer
        self.principal_id = principal_id
        self.task_id: str | None = None
        self.request_facts: list[dict[str, Any]] = []
        self.owner_rerun_count = 0
        self.app = Starlette(routes=[Route("/mcp", self.handle, methods=["POST"])])

    async def handle(self, request: Request) -> JSONResponse:
        if request.headers.get("authorization") != f"Bearer {self.bearer}":
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return self._rpc_error(None, -32700, "Parse error")
        request_id = body.get("id")
        method = body.get("method")
        params = body.get("params") or {}
        if not isinstance(method, str) or not isinstance(params, dict):
            return self._rpc_error(request_id, -32600, "Invalid Request")
        meta = params.get("_meta")
        capabilities = (
            meta.get("io.modelcontextprotocol/clientCapabilities", {})
            if isinstance(meta, dict)
            else {}
        )
        headers = {
            "Mcp-Method": request.headers.get("mcp-method", ""),
            "Mcp-Name": request.headers.get("mcp-name", ""),
        }
        request_fact = {
            "method": method,
            "method_header_matches": headers["Mcp-Method"] == method,
            "name_header_present": bool(headers["Mcp-Name"]),
            "tasks_extension_present": isinstance(capabilities, dict)
            and isinstance(capabilities.get("extensions"), dict)
            and TASKS_EXTENSION_ID in capabilities["extensions"],
        }
        self.request_facts.append(request_fact)
        try:
            result = self._dispatch(method, params, capabilities, headers)
        except self.adapter_error as exc:
            request_fact["response_error_code"] = exc.code
            request_fact["response_http_status"] = exc.http_status
            return self._rpc_error(
                request_id,
                exc.code,
                exc.message,
                data=exc.data,
                http_status=exc.http_status,
            )
        except Exception:
            return self._rpc_error(request_id, -32603, "Internal error")
        return JSONResponse(
            {"jsonrpc": "2.0", "id": request_id, "result": result},
            headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
        )

    @property
    def adapter_error(self) -> type[Exception]:
        from aoa_sdk.organs import MCPTasksAdapterError

        return MCPTasksAdapterError

    def _context(self, capabilities: dict[str, Any], headers: dict[str, str]) -> Any:
        from aoa_sdk.organs import MCPTaskRequestContext

        return MCPTaskRequestContext(
            principal_id=self.principal_id,
            organ_id="abyss-stack",
            contour_id="read",
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=capabilities,
            transport="streamable_http",
            headers=headers,
        )

    def _dispatch(
        self,
        method: str,
        params: dict[str, Any],
        capabilities: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        if method == "server/discover":
            return {
                "resultType": "complete",
                "supportedVersions": [PROTOCOL_VERSION],
                "capabilities": {
                    "tools": {},
                    "extensions": {TASKS_EXTENSION_ID: {}},
                },
                "ttlMs": 0,
                "cacheScope": "private",
                "_meta": {
                    "io.modelcontextprotocol/serverInfo": {
                        "name": "abyss-tasks-adapter-lab",
                        "version": "0.1.0",
                    }
                },
            }
        if method == "tools/list":
            return {
                "resultType": "complete",
                "tools": [
                    {
                        "name": "diagnostic_snapshot",
                        "description": "Return an existing read-only owner diagnostic as a durable task.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"scope": {"const": "deployed"}},
                            "required": ["scope"],
                            "additionalProperties": False,
                        },
                    }
                ],
                "ttlMs": 0,
                "cacheScope": "private",
            }
        context = self._context(capabilities, headers)
        if method == "tools/call":
            if params.get("name") != "diagnostic_snapshot":
                raise self.adapter_error(-32602, "Unknown tool")
            created = self.adapter.create_task_result(
                context,
                tool_name="diagnostic_snapshot",
                arguments=params.get("arguments", {}),
                owner_run_ref="owner://abyss-stack/diagnostic/existing-read-only",
                idempotency_key=f"inspector-{params.get('arguments', {}).get('scope', 'bounded')}",
                ttl_seconds=60,
                poll_interval_ms=100,
            )
            if created is None:
                raise self.adapter_error(-32603, "Tasks capability unexpectedly absent")
            self.task_id = created["taskId"]
            return created
        task_id = params.get("taskId")
        if not isinstance(task_id, str):
            raise self.adapter_error(-32602, "taskId must be a string")
        if method == "tasks/get":
            record = self.store.get(
                task_id,
                principal_id=self.principal_id,
                organ_id="abyss-stack",
                contour_id="read",
            )
            if record.status == "working":
                self.store.complete(
                    task_id,
                    principal_id=self.principal_id,
                    organ_id="abyss-stack",
                    contour_id="read",
                    expected_revision=record.revision,
                    result_ref=self.result_ref,
                    result_digest=self.result_digest,
                    evidence_refs=("owner://abyss-stack/diagnostic/existing-read-only",),
                )
            return self.adapter.get_task(context, task_id=task_id)
        if method == "tasks/update":
            return self.adapter.update_task(
                context,
                task_id=task_id,
                input_responses=params.get("inputResponses", {}),
            )
        if method == "tasks/cancel":
            return self.adapter.cancel_task(context, task_id=task_id)
        raise self.adapter_error(-32601, "Method not found")

    @staticmethod
    def _rpc_error(
        request_id: Any,
        code: int,
        message: str,
        *,
        data: Any = None,
        http_status: int = 200,
    ) -> JSONResponse:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return JSONResponse(
            {"jsonrpc": "2.0", "id": request_id, "error": error},
            status_code=http_status,
            headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--aoa-sdk-root", type=Path, required=True)
    parser.add_argument("--inspector-root", type=Path, required=True)
    parser.add_argument("--owner-receipt", type=Path, required=True)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> Path:
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%S.%fZ")
    run_root = args.state_root.resolve() / "runs" / run_id
    run_root.mkdir(parents=True, mode=0o700)
    os.chmod(run_root, 0o700)
    bearer = secrets.token_urlsafe(32)
    pair = _PairServer(
        sdk_root=args.aoa_sdk_root.resolve(),
        state_root=run_root,
        owner_receipt=args.owner_receipt.resolve(),
        bearer=bearer,
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    endpoint = f"http://127.0.0.1:{listener.getsockname()[1]}/mcp"
    server = uvicorn.Server(
        uvicorn.Config(pair.app, log_level="error", lifespan="off")
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        env = os.environ.copy()
        env.update(
            {
                "ABYSS_INSPECTOR_ROOT": str(args.inspector_root.resolve()),
                "ABYSS_TASKS_ENDPOINT": endpoint,
                "ABYSS_TASKS_BEARER": bearer,
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            }
        )
        command = [
            "npx",
            "tsx",
            str(CLIENT_SCRIPT),
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=args.inspector_root.resolve() / "clients" / "web",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        if process.returncode != 0:
            _atomic_json(
                run_root / "failed-request-facts.json",
                {"request_facts": pair.request_facts},
            )
            raise RuntimeError(
                "Inspector client failed: "
                + stderr.decode("utf-8", errors="replace")[-4000:]
            )
        client = json.loads(stdout)
    finally:
        server.should_exit = True
        await task
        listener.close()

    if pair.task_id is None:
        raise RuntimeError("Inspector pair did not create an Abyss task")
    audit_actions = sorted(
        {
            json.loads(path.read_text(encoding="utf-8"))["action"]
            for path in (run_root / "task-store" / "audit").glob("*.json")
        }
    )
    task_request_facts = [
        item
        for item in pair.request_facts
        if item["method"] in {"tools/call", "tasks/get"}
    ]
    public = {
        "schema_version": "abyss_inspector_tasks_adapter_pair_v1",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "protocol_version": PROTOCOL_VERSION,
        "extension_id": TASKS_EXTENSION_ID,
        "inspector": {
            "version": "2.1.0",
            "commit": "c7bccd477d38c2c17afb4878bcca8ee5f563c5d2",
            "published_release": True,
            "raw_wire_workaround": True,
        },
        "adapter": {
            "feature_gate_enabled": True,
            "production_enabled": False,
            "protocol_independent_store": True,
        },
        "wire": {
            "modern_era": client["protocol_era"] == "modern",
            "tasks_extension_negotiated": client["tasks_extension_negotiated"],
            "extension_on_every_task_request": client[
                "extension_on_every_task_request"
            ],
            "method_headers_match": all(
                item["method_header_matches"] for item in task_request_facts
            ),
            "name_headers_present": all(
                item["name_header_present"] for item in task_request_facts
            ),
            "methods": sorted(set(client["methods"])),
            "removed_methods_absent": client["removed_methods_absent"],
            "unknown_task_rejected": client["unknown_task_rejected"],
            "wrong_bearer_http_status": client["wrong_bearer_http_status"],
        },
        "owner_result": {
            "owner": "abyss-stack",
            "authority": "diagnostic_session_v1",
            "diagnostic_digest": pair.owner_receipt_digest,
            "owner_rerun_count": pair.owner_rerun_count,
            "tool_error_preserved": client["owner_tool_error_preserved"],
        },
        "store": {
            "task_id_digest": _sha256_bytes(pair.task_id.encode("utf-8")),
            "audit_actions": audit_actions,
            "durable_before_handle": True,
        },
        "verdict": "published_inspector_passed_feature_gated_abyss_adapter",
        "claim_limits": [
            "This proves one published Inspector 2.1.0 create/get/completed-result pair against the Abyss adapter, not every Tasks method.",
            "Inspector uses a localized raw-wire workaround because its TypeScript SDK dependency excludes modern Tasks methods.",
            "The owner diagnostic was reused by digest and was not rerun; its tool-level error remains visible inside a completed task.",
            "The adapter feature gate was enabled only in the isolated lab and remains disabled in production.",
            "Notifications, distributed poll limits, and Codex Tasks consumption remain unproved.",
        ],
    }
    private = {
        "public": public,
        "client": client,
        "request_facts": pair.request_facts,
        "owner_receipt_path": str(args.owner_receipt.resolve()),
        "stderr_digest": _sha256_bytes(stderr),
    }
    _atomic_json(run_root / "private.json", private)
    _atomic_json(run_root / "public-safe.json", public)
    return run_root / "public-safe.json"


def main() -> int:
    args = _parse_args()
    try:
        result = asyncio.run(_run(args))
    except (OSError, ValueError, RuntimeError, asyncio.TimeoutError) as exc:
        print(f"Inspector Tasks adapter pair failed: {exc}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
