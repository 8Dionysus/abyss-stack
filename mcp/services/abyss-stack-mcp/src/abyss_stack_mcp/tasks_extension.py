"""Production-bounded MCP Tasks extension for stack read diagnostics.

The extension creates durable, principal-bound task handles and runs only the
existing read-only ``StackMCPApplication.inspect`` route.  A task identifier is
never authorization, admission, or effect authority.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
from collections.abc import Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

from aoa_sdk.organs import (
    FileTaskStore,
    MCPTaskRequestContext,
    MCPTasksAdapter,
    MCPTasksAdapterError,
)
from aoa_sdk.organs.registry import canonical_json_bytes, sha256_digest
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.context import CallNext, ServerRequestContext
from mcp.server.extension import Extension, MethodBinding, ToolBinding
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolRequestParams, RequestParams, ToolAnnotations
from pydantic import ConfigDict, Field

from .core import StackMCPApplication


TASKS_EXTENSION_ID = "io.modelcontextprotocol/tasks"
TASKS_PROTOCOL_VERSION = "2026-07-28"
TASK_TOOL = "stack_runtime_inspect_task"
DEFAULT_TASK_ROOT = Path(
    "/srv/AbyssOS/abyss-stack/Logs/mcp/tasks/abyss-stack-read"
)


class _TaskGetParams(RequestParams):
    model_config = ConfigDict(populate_by_name=True)
    task_id: str = Field(alias="taskId", min_length=43, max_length=128)


class _TaskUpdateParams(_TaskGetParams):
    input_responses: dict[str, Any] = Field(alias="inputResponses")


class _TaskPayloadStore:
    """Private content-addressed payload store used by the durable handles."""

    def __init__(self, root: Path) -> None:
        self.root = root / "payloads"
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise RuntimeError("MCP task payload root must be a non-symlink directory")
        self.root.chmod(0o700)

    def put(self, payload: Mapping[str, Any]) -> tuple[str, str]:
        value = dict(payload)
        digest = sha256_digest(value)
        identity = digest.removeprefix("sha256:")
        path = self.root / f"{identity}.json"
        if path.is_symlink():
            raise RuntimeError("MCP task payload path must not be a symlink")
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if not path.exists():
            temporary = self.root / (
                f".{identity}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
            )
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.write(fd, encoded)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temporary, path)
            path.chmod(0o600)
        return f"owner://abyss-stack/mcp-task-payload/{identity}", digest

    def _read(self, ref: str) -> dict[str, Any]:
        prefix = "owner://abyss-stack/mcp-task-payload/"
        if not ref.startswith(prefix):
            raise KeyError(ref)
        identity = ref.removeprefix(prefix)
        if len(identity) != 64 or any(char not in "0123456789abcdef" for char in identity):
            raise KeyError(ref)
        path = self.root / f"{identity}.json"
        if path.is_symlink() or not path.is_file():
            raise KeyError(ref)
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or sha256_digest(value) != f"sha256:{identity}":
            raise KeyError(ref)
        return value

    def resolve_result(self, record: Any) -> Mapping[str, Any]:
        return self._read(record.result_ref)

    def resolve_error(self, record: Any) -> Mapping[str, Any]:
        return self._read(record.error_ref)

    def resolve_input_request(self, record: Any, request: Any) -> Mapping[str, Any]:
        raise KeyError((record.task_id, request.request_key))


def tasks_enabled_from_environment() -> bool:
    value = os.environ.get("ABYSS_STACK_MCP_TASKS_ENABLED", "").strip()
    if value not in {"", "0", "1"}:
        raise SystemExit("ABYSS_STACK_MCP_TASKS_ENABLED must be 0 or 1")
    return value == "1"


def task_root_from_environment() -> Path:
    return Path(os.environ.get("ABYSS_STACK_MCP_TASK_ROOT", str(DEFAULT_TASK_ROOT)))


def running_mcp_sdk_version() -> str:
    """Read the SDK identity from the server process serving the task."""
    try:
        return version("mcp")
    except PackageNotFoundError as exc:
        raise RuntimeError("the serving MCP SDK package is not installed") from exc


class StackReadTasksExtension(Extension):
    """Opt-in task surface for one existing stack read operation."""

    identifier = TASKS_EXTENSION_ID

    def __init__(self, application: StackMCPApplication, root: Path) -> None:
        self.application = application
        self.payloads = _TaskPayloadStore(root)
        self.store = FileTaskStore(root / "store")
        self._workers: dict[str, asyncio.Task[None]] = {}
        self.adapter = MCPTasksAdapter(
            self.store,
            self.payloads,
            enabled=True,
            cancel_sink=self._cancel,
            enforce_poll_interval=True,
        )

    def settings(self) -> dict[str, Any]:
        return {"taskTools": [TASK_TOOL]}

    def tools(self) -> Sequence[ToolBinding]:
        def stack_runtime_inspect_task(
            organ_id: str,
            policy_family: Literal["read"] = "read",
            view: Literal[
                "identity",
                "parity",
                "process",
                "endpoint",
                "registry",
                "consumer",
                "schema",
                "freshness",
                "proof",
                "acceptance",
                "canary",
                "rollback",
                "drift",
                "full",
            ] = "full",
            idempotency_key: str | None = None,
        ) -> dict[str, Any]:
            """Run one durable, cancellable stack read inspection task."""

            raise RuntimeError("Tasks-aware tools/call interceptor was bypassed")

        annotations = ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
        return (
            ToolBinding(
                fn=stack_runtime_inspect_task,
                kwargs={
                    "name": TASK_TOOL,
                    "annotations": annotations,
                    "structured_output": True,
                },
            ),
        )

    def methods(self) -> Sequence[MethodBinding]:
        versions = frozenset({TASKS_PROTOCOL_VERSION})
        return (
            MethodBinding("tasks/get", _TaskGetParams, self._get, versions),
            MethodBinding("tasks/update", _TaskUpdateParams, self._update, versions),
            MethodBinding("tasks/cancel", _TaskGetParams, self._cancel_request, versions),
        )

    async def intercept_tool_call(
        self,
        params: CallToolRequestParams,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> Any:
        if params.name != TASK_TOOL:
            return await call_next(ctx)
        arguments = dict(params.arguments or {})
        domain_arguments = {
            "organ_id": arguments.get("organ_id"),
            "policy_family": arguments.get("policy_family", "read"),
            "view": arguments.get("view", "full"),
        }
        if not isinstance(domain_arguments["organ_id"], str):
            raise MCPError(code=-32602, message="organ_id is required")
        supplied_key = arguments.get("idempotency_key")
        if supplied_key is not None and not isinstance(supplied_key, str):
            raise MCPError(code=-32602, message="idempotency_key must be a string")
        context = self._context(ctx)
        digest = hashlib.sha256(
            canonical_json_bytes(
                {
                    "principal": context.principal_id,
                    "arguments": domain_arguments,
                    "idempotency_key": supplied_key,
                }
            )
        ).hexdigest()
        try:
            created = self.adapter.create_task_result(
                context,
                tool_name=TASK_TOOL,
                arguments=domain_arguments,
                owner_run_ref=f"owner://abyss-stack/mcp-read-task/{digest}",
                idempotency_key=f"mcp-{digest}",
                ttl_seconds=900,
                poll_interval_ms=250,
                task_support="required",
            )
        except MCPTasksAdapterError as exc:
            raise self._mcp_error(exc) from exc
        assert created is not None
        task_id = created["taskId"]
        record = self.store.get(
            task_id,
            principal_id=context.principal_id,
            organ_id=context.organ_id,
            contour_id=context.contour_id,
        )
        if record.status == "working" and task_id not in self._workers:
            self._workers[task_id] = asyncio.create_task(
                self._execute(context, task_id, domain_arguments)
            )
        return created

    async def _get(self, ctx: ServerRequestContext[Any, Any], params: _TaskGetParams) -> Any:
        try:
            return self.adapter.get_task(self._context(ctx), task_id=params.task_id)
        except MCPTasksAdapterError as exc:
            raise self._mcp_error(exc) from exc

    async def _update(
        self,
        ctx: ServerRequestContext[Any, Any],
        params: _TaskUpdateParams,
    ) -> Any:
        try:
            return self.adapter.update_task(
                self._context(ctx),
                task_id=params.task_id,
                input_responses=params.input_responses,
            )
        except MCPTasksAdapterError as exc:
            raise self._mcp_error(exc) from exc

    async def _cancel_request(
        self,
        ctx: ServerRequestContext[Any, Any],
        params: _TaskGetParams,
    ) -> Any:
        try:
            return self.adapter.cancel_task(
                self._context(ctx),
                task_id=params.task_id,
            )
        except MCPTasksAdapterError as exc:
            raise self._mcp_error(exc) from exc

    async def _execute(
        self,
        context: MCPTaskRequestContext,
        task_id: str,
        arguments: dict[str, Any],
    ) -> None:
        try:
            owner_payload = await asyncio.to_thread(self.application.inspect, **arguments)
            metadata = owner_payload.get("metadata")
            if not isinstance(metadata, dict):
                raise RuntimeError("owner inspection omitted result metadata")
            owner_payload = {
                **owner_payload,
                "metadata": {
                    **metadata,
                    "mcp_sdk": running_mcp_sdk_version(),
                },
            }
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(owner_payload, ensure_ascii=False, sort_keys=True),
                    }
                ],
                "structuredContent": owner_payload,
                "isError": False,
            }
            ref, digest = self.payloads.put(result)
            record = self.store.get(
                task_id,
                principal_id=context.principal_id,
                organ_id=context.organ_id,
                contour_id=context.contour_id,
            )
            if record.status != "working":
                return
            self.store.complete(
                task_id,
                principal_id=context.principal_id,
                organ_id=context.organ_id,
                contour_id=context.contour_id,
                expected_revision=record.revision,
                result_ref=ref,
                result_digest=digest,
                evidence_refs=("owner://abyss-stack/runtime-observation",),
            )
        except asyncio.CancelledError:
            return
        except Exception:
            error = {"code": -32603, "message": "Owner read task execution failed"}
            ref, digest = self.payloads.put(error)
            try:
                record = self.store.get(
                    task_id,
                    principal_id=context.principal_id,
                    organ_id=context.organ_id,
                    contour_id=context.contour_id,
                )
                if record.status == "working":
                    self.store.fail(
                        task_id,
                        principal_id=context.principal_id,
                        organ_id=context.organ_id,
                        contour_id=context.contour_id,
                        expected_revision=record.revision,
                        error_ref=ref,
                        error_digest=digest,
                    )
            except Exception:
                return
        finally:
            self._workers.pop(task_id, None)

    def _cancel(self, record: Any) -> None:
        worker = self._workers.get(record.task_id)
        if worker is not None:
            worker.cancel()
        current = self.store.get(
            record.task_id,
            principal_id=record.principal_id,
            organ_id=record.organ_id,
            contour_id=record.contour_id,
        )
        if current.cancellation_outcome == "pending":
            self.store.acknowledge_cancel(
                record.task_id,
                principal_id=record.principal_id,
                organ_id=record.organ_id,
                contour_id=record.contour_id,
                expected_revision=current.revision,
                accepted=True,
            )

    @staticmethod
    def _context(ctx: ServerRequestContext[Any, Any]) -> MCPTaskRequestContext:
        token = get_access_token()
        principal = token.client_id if token is not None else "local-os-stdio"
        capabilities = ctx.session.client_capabilities
        capability_payload = (
            capabilities.model_dump(by_alias=True, mode="json", exclude_none=True)
            if capabilities is not None
            else {}
        )
        request = ctx.request
        request_headers = getattr(request, "headers", {}) if request is not None else {}
        return MCPTaskRequestContext(
            principal_id=principal,
            organ_id="abyss-stack",
            contour_id="read",
            protocol_version=ctx.protocol_version,
            client_capabilities=capability_payload,
            transport="streamable_http" if request is not None else "stdio",
            headers=dict(request_headers),
        )

    @staticmethod
    def _mcp_error(error: MCPTasksAdapterError) -> MCPError:
        return MCPError(code=error.code, message=error.message, data=error.data)
