"""Separate authenticated MCP process for one exact internal-effect pilot."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import signal
import sys
from typing import Any
import uuid

from ._http_auth import transport_settings
from .core import _reject_secret_material, canonical_json_bytes
from .effect import (
    DEFAULT_EFFECT_ROOT,
    DEFAULT_OBSERVATION_PATH,
    EXACT_TOOL_ID,
    EffectError,
    InternalEffectReceipt,
)
from .server import (
    INTERNAL_EFFECT_PORT,
    _auth_kwargs,
    _bind_server_info_version,
    _policy_identity,
)


LOGGER = logging.getLogger(__name__)
MAX_INPUT_BYTES = 4096
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
WORKER_TIMEOUT_SECONDS = 120


async def _run_worker(
    *,
    plan_id: str,
    approval_id: str,
    idempotency_key: str,
    effect_root: Path,
    observation_path: Path,
) -> dict[str, Any]:
    command = (
        sys.executable,
        "-I",
        "-m",
        "abyss_stack_mcp.effect",
        "--effect-root",
        str(effect_root),
        "--observation-path",
        str(observation_path),
        "execute",
        "--plan-id",
        plan_id,
        "--approval-id",
        approval_id,
        "--idempotency-key",
        idempotency_key,
    )
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(), timeout=WORKER_TIMEOUT_SECONDS
        )
    except asyncio.CancelledError:
        # The exact worker owns rollback once execution starts. Give it the
        # bounded completion window before propagating caller cancellation.
        try:
            await asyncio.wait_for(process.wait(), timeout=WORKER_TIMEOUT_SECONDS)
        except TimeoutError:
            os.killpg(process.pid, signal.SIGTERM)
            await process.wait()
        raise
    except TimeoutError:
        os.killpg(process.pid, signal.SIGTERM)
        await process.wait()
        raise EffectError("internal-effect worker exceeded its bounded timeout") from None
    if process.returncode != 0:
        raise EffectError("internal-effect worker denied or failed the exact request")
    if len(stdout) > MAX_OUTPUT_BYTES:
        raise EffectError("internal-effect worker output exceeded its size limit")
    try:
        payload = json.loads(stdout)
        receipt = InternalEffectReceipt.model_validate(payload["receipt"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise EffectError("internal-effect worker returned an invalid receipt") from exc
    result = {
        "metadata": {
            "contract_version": "abyss_stack_internal_effect_result_v1",
            "source_owner": "abyss-stack",
            "access_owner": "abyss-stack",
            "runtime_owner": "abyss-stack",
            "authority_ceiling": "internal_effect",
            "effect_class": "apply_runtime",
            "applied_state": "applied_rolled_back",
            "execution_authorized": True,
            "external_effect_authorized": False,
            "idempotent_replay": payload.get("idempotent_replay") is True,
            "trace_id": uuid.uuid4().hex,
            "content_trust": "untrusted_data",
            "instruction_authority": "none",
        },
        "owner_payload": {"receipt": receipt.model_dump(mode="json")},
    }
    _reject_secret_material(result)
    return result


def build_effect_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'.") from exc

    auth_kwargs = _auth_kwargs("internal_effect")
    effect_root = Path(
        os.environ.get("ABYSS_STACK_MCP_EFFECT_ROOT", str(DEFAULT_EFFECT_ROOT))
    )
    observation_path = Path(
        os.environ.get(
            "ABYSS_STACK_MCP_OBSERVATION_PATH", str(DEFAULT_OBSERVATION_PATH)
        )
    )
    mcp = FastMCP(
        "abyss-stack-mcp-internal-effect",
        instructions=(
            "Execute only one content-addressed, explicitly approved restart-and-"
            "rollback pilot for abyss-stack-mcp-read.service. No other target, "
            "command, source mutation, or external effect exists in this process."
        ),
        json_response=True,
        **auth_kwargs,
    )
    _bind_server_info_version(mcp)
    annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    )

    @mcp.tool(annotations=annotations, structured_output=True)
    async def stack_execute_approved_read_restart_pilot(
        plan_id: str,
        approval_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Execute and roll back one exact approved read-service restart pilot."""
        identity = _policy_identity("internal_effect")
        if identity.scope != "abyss-stack-mcp:internal_effect":
            raise EffectError("internal-effect caller identity is not authorized")
        arguments = {
            "plan_id": plan_id,
            "approval_id": approval_id,
            "idempotency_key": idempotency_key,
        }
        if len(canonical_json_bytes(arguments)) > MAX_INPUT_BYTES:
            raise EffectError("internal-effect request exceeds its size limit")
        _reject_secret_material(arguments)
        return await _run_worker(
            plan_id=plan_id,
            approval_id=approval_id,
            idempotency_key=idempotency_key,
            effect_root=effect_root,
            observation_path=observation_path,
        )

    tools = getattr(mcp, "_tool_manager", None)
    if tools is not None and set(getattr(tools, "_tools", {})) != {EXACT_TOOL_ID}:
        raise RuntimeError("internal-effect MCP tool allowlist drifted")
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = transport_settings(INTERNAL_EFFECT_PORT)
    server = build_effect_server()
    if settings.transport == "stdio":
        server.run(transport="stdio")
        return
    assert settings.host is not None and settings.port is not None
    server.settings.host = settings.host
    server.settings.port = settings.port
    LOGGER.info("abyss-stack MCP internal-effect plane ready")
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
