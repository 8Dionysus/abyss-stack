from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolRequestParams, ClientCapabilities

from abyss_stack_mcp.tasks_extension import (
    TASKS_EXTENSION_ID,
    TASKS_PROTOCOL_VERSION,
    TASK_TOOL,
    StackReadTasksExtension,
    _TaskGetParams,
)


class _Application:
    def __init__(self, *, delay: float = 0.0) -> None:
        self.delay = delay

    def inspect(self, organ_id: str, policy_family: str, *, view: str) -> dict:
        if self.delay:
            import time

            time.sleep(self.delay)
        return {
            "metadata": {"owner": "abyss-stack", "effect_class": "observe"},
            "owner_payload": {
                "organ_id": organ_id,
                "policy_family": policy_family,
                "view": view,
            },
        }


def _context(*, method: str, name: str, extension: bool = True):
    capabilities = ClientCapabilities(
        extensions={TASKS_EXTENSION_ID: {}} if extension else None
    )
    return SimpleNamespace(
        protocol_version=TASKS_PROTOCOL_VERSION,
        session=SimpleNamespace(client_capabilities=capabilities),
        request=SimpleNamespace(
            headers={
                "Mcp-Method": method,
                "Mcp-Name": name,
            }
        ),
    )


async def _unused_call_next(ctx):  # pragma: no cover - must never be reached
    raise AssertionError(ctx)


def test_tasks_extension_advertises_only_its_bounded_surface(tmp_path: Path) -> None:
    extension = StackReadTasksExtension(_Application(), tmp_path)
    assert extension.identifier == TASKS_EXTENSION_ID
    assert extension.settings() == {"taskTools": [TASK_TOOL]}
    assert [binding.kwargs["name"] for binding in extension.tools()] == [TASK_TOOL]
    assert [binding.method for binding in extension.methods()] == [
        "tasks/get",
        "tasks/update",
        "tasks/cancel",
    ]
    assert all(
        binding.protocol_versions == frozenset({TASKS_PROTOCOL_VERSION})
        for binding in extension.methods()
    )


def test_task_completes_and_survives_extension_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "abyss_stack_mcp.tasks_extension.get_access_token",
        lambda: SimpleNamespace(client_id="codex-main"),
    )

    async def scenario() -> None:
        extension = StackReadTasksExtension(_Application(), tmp_path)
        created = await extension.intercept_tool_call(
            CallToolRequestParams(
                name=TASK_TOOL,
                arguments={"organ_id": "aoa-kag", "view": "identity"},
            ),
            _context(method="tools/call", name=TASK_TOOL),
            _unused_call_next,
        )
        task_id = created["taskId"]
        assert created["resultType"] == "task"
        assert created["status"] == "working"
        await asyncio.sleep(0.35)

        restarted = StackReadTasksExtension(_Application(), tmp_path)
        result = await restarted._get(
            _context(method="tasks/get", name=task_id),
            _TaskGetParams(taskId=task_id),
        )
        assert result["resultType"] == "complete"
        assert result["status"] == "completed"
        assert result["result"]["isError"] is False
        assert result["result"]["structuredContent"]["owner_payload"][
            "organ_id"
        ] == "aoa-kag"

    asyncio.run(scenario())


def test_tasks_fail_closed_without_capability_or_matching_headers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "abyss_stack_mcp.tasks_extension.get_access_token",
        lambda: SimpleNamespace(client_id="codex-main"),
    )

    async def scenario() -> None:
        extension = StackReadTasksExtension(_Application(), tmp_path)
        params = CallToolRequestParams(
            name=TASK_TOOL,
            arguments={"organ_id": "aoa-kag"},
        )
        with pytest.raises(MCPError) as missing:
            await extension.intercept_tool_call(
                params,
                _context(method="tools/call", name=TASK_TOOL, extension=False),
                _unused_call_next,
            )
        assert missing.value.error.code == -32021

        with pytest.raises(MCPError) as mismatch:
            await extension.intercept_tool_call(
                params,
                _context(method="tools/list", name=TASK_TOOL),
                _unused_call_next,
            )
        assert mismatch.value.error.code == -32020

    asyncio.run(scenario())


def test_task_is_principal_bound_and_cancellable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal = {"id": "codex-main"}
    monkeypatch.setattr(
        "abyss_stack_mcp.tasks_extension.get_access_token",
        lambda: SimpleNamespace(client_id=principal["id"]),
    )

    async def scenario() -> None:
        extension = StackReadTasksExtension(_Application(delay=0.5), tmp_path)
        created = await extension.intercept_tool_call(
            CallToolRequestParams(name=TASK_TOOL, arguments={"organ_id": "aoa-kag"}),
            _context(method="tools/call", name=TASK_TOOL),
            _unused_call_next,
        )
        task_id = created["taskId"]

        principal["id"] = "another-principal"
        with pytest.raises(MCPError) as denied:
            await extension._get(
                _context(method="tasks/get", name=task_id),
                _TaskGetParams(taskId=task_id),
            )
        assert denied.value.error.code == -32602

        principal["id"] = "codex-main"
        cancelled = await extension._cancel_request(
            _context(method="tasks/cancel", name=task_id),
            _TaskGetParams(taskId=task_id),
        )
        assert cancelled == {"resultType": "complete"}
        record = extension.store.get(
            task_id,
            principal_id="codex-main",
            organ_id="abyss-stack",
            contour_id="read",
        )
        assert record.status == "cancelled"

    asyncio.run(scenario())
