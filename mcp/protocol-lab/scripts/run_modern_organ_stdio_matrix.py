#!/usr/bin/env python3
"""Prove every standalone organ package on native MCP 2.x stdio."""

from __future__ import annotations

import argparse
import asyncio
import builtins
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from canary_contract import load_canary_contracts, verify_structured_result
from runtime_catalog import load_runtime_catalog, mcp_settings, probe_limits, runtime_identity


_EXCEPTION_GROUP = getattr(builtins, "BaseExceptionGroup", ())


def _absolute_executable(path: Path) -> Path:
    """Normalize an executable path without collapsing a virtualenv symlink."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise RuntimeError("MCP probe Python executable must be an absolute path")
    # Path.resolve() turns venv/bin/python into the host interpreter and drops
    # the venv site-packages.  abspath normalizes lexical components while
    # preserving the executable entrypoint selected by the operator.
    return Path(os.path.abspath(os.fspath(expanded)))


def _source_package_root(service_id: str) -> Path:
    root = Path(__file__).resolve().parents[2] / "services" / service_id / "src"
    if not root.is_dir():
        raise RuntimeError(f"MCP source package projection is unavailable: {root}")
    return root


def _exception_text(exc: BaseException) -> str:
    """Expose nested transport causes without leaking unbounded output."""

    if _EXCEPTION_GROUP and isinstance(exc, _EXCEPTION_GROUP):
        children = "; ".join(_exception_text(item) for item in exc.exceptions)
        return f"{type(exc).__name__}: {children}"[-4000:]
    return str(exc)[-4000:]


def _server_parameters(
    *,
    python: Path,
    service: dict[str, Any],
    workspace_root: Path,
    workspace_env_var: str,
    transport: dict[str, Any],
) -> Any:
    from mcp.client.stdio import StdioServerParameters

    service_id = str(service["service_id"])
    module = str(service["module"])
    package_root = _source_package_root(service_id)
    transport_env_var = str(transport["transport_env_var"])
    env = {
        **os.environ,
        transport_env_var: "stdio",
        workspace_env_var: workspace_root.as_posix(),
        "PYTHONDONTWRITEBYTECODE": "1",
        "ABYSS_STACK_MCP_POLICY_FAMILY": "read",
        "ABYSS_STACK_MCP_TASKS_ENABLED": "0",
        "AOA_SESSION_MEMORY_MCP_AUTO_RELOAD": "0",
    }
    return StdioServerParameters(
        command=python.as_posix(),
        args=[
            "-I",
            "-B",
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {package_root.as_posix()!r}); "
                f"from {module}.server import main; main()"
            ),
        ],
        cwd=workspace_root.as_posix(),
        env=env,
    )


async def _probe_server(
    *,
    python: Path,
    service: dict[str, Any],
    contract: dict[str, Any],
    workspace_root: Path,
    workspace_env_var: str,
    transport: dict[str, Any],
    tool_call_timeout: float,
) -> dict[str, Any]:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    service_id = str(service["service_id"])
    tool_name = contract.get("tool_name")
    arguments = contract.get("arguments")
    if not isinstance(tool_name, str) or not isinstance(arguments, dict):
        raise RuntimeError(f"{service_id} has an invalid read canary contract")
    params = _server_parameters(
        python=python,
        service=service,
        workspace_root=workspace_root,
        workspace_env_var=workspace_env_var,
        transport=transport,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            inventory = await session.list_tools()
            tools = list(inventory.tools)
            tool_names = {str(tool.name) for tool in tools}
            if tool_name not in tool_names:
                raise RuntimeError(f"{service_id} stdio inventory lacks {tool_name}")
            call = await session.call_tool(
                tool_name,
                arguments,
                read_timeout_seconds=tool_call_timeout,
            )
    structured = getattr(call, "structured_content", None)
    verified = verify_structured_result(
        structured,
        contract,
        transport=str(transport["default_transport"]),
    )
    reasons = list(verified["reason_codes"])
    if bool(getattr(call, "is_error", False)):
        reasons.append("tool_returned_error")
    reasons = list(dict.fromkeys(reasons))
    server_info = initialized.server_info
    return {
        "service_id": service_id,
        "server_name": getattr(server_info, "name", None),
        "server_version": getattr(server_info, "version", None),
        "protocol_version": initialized.protocol_version,
        "tool_count": len(tools),
        "tool_schema_sha256": hashlib.sha256(
            json.dumps(
                [tool.model_dump(by_alias=True, exclude_none=True) for tool in tools],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "semantic_probe": {
            "tool_name": tool_name,
            **verified,
            "reason_codes": reasons,
            "verdict": "passed" if not reasons else "failed",
        },
        "verdict": "passed" if not reasons else "failed",
    }


async def _run(
    *,
    python: Path,
    workspace_root: Path,
    output: Path,
) -> int:
    catalog = load_runtime_catalog()
    sdk_settings, _protocol_settings, transport_settings = mcp_settings(catalog)
    client_identity = runtime_identity(Path(sys.executable), sdk_settings)
    server_identity = runtime_identity(python, sdk_settings)
    if not client_identity["exact_pair"]:
        raise RuntimeError(
            "stdio matrix client interpreter is not the exact reviewed MCP SDK pair: "
            + json.dumps(client_identity, sort_keys=True)
        )
    if not server_identity["exact_pair"]:
        raise RuntimeError(
            "stdio matrix server interpreter is not the exact reviewed MCP SDK pair: "
            + json.dumps(server_identity, sort_keys=True)
        )
    paths = catalog.get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError("MCP runtime catalog has no path settings")
    workspace_env_var = str(paths["workspace_env_var"])
    limits = probe_limits(catalog)
    contracts = load_canary_contracts()
    service_ids = {str(item["service_id"]) for item in catalog["services"]}
    if set(contracts) != service_ids:
        raise RuntimeError("stdio canary coverage and MCP package catalog differ")
    rows: list[dict[str, Any]] = []
    for service in sorted(catalog["services"], key=lambda item: item["service_id"]):
        service_id = str(service["service_id"])
        try:
            rows.append(
                await asyncio.wait_for(
                    _probe_server(
                        python=python,
                        service=service,
                        contract=contracts[service_id],
                        workspace_root=workspace_root,
                        workspace_env_var=workspace_env_var,
                        transport=transport_settings,
                        tool_call_timeout=limits[
                            "protocol_probe_stdio_call_timeout_seconds"
                        ],
                    ),
                    timeout=limits["protocol_probe_stdio_timeout_seconds"],
                )
            )
        except TimeoutError:
            rows.append(
                {
                    "service_id": service_id,
                    "verdict": "failed",
                    "error_type": "TimeoutError",
                    "error": "stdio probe exceeded its catalog timeout",
                    "reason_codes": ["probe_timeout"],
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "service_id": service_id,
                    "verdict": "failed",
                    "error_type": type(exc).__name__,
                    "error": _exception_text(exc),
                }
            )
    receipt = {
        "schema_version": "abyss_modern_organ_stdio_matrix_v1",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "mcp_sdk": client_identity["versions"].get(sdk_settings["distribution"]),
        "mcp_companion_sdk": client_identity["versions"].get(
            sdk_settings["companion_distribution"]
        ),
        "runtime_identity": client_identity,
        "client_runtime_identity": client_identity,
        "server_runtime_identity": server_identity,
        "package_count": len(rows),
        "semantic_probe_count": sum(
            1
            for row in rows
            if row.get("semantic_probe", {}).get("verdict") == "passed"
        ),
        "servers": rows,
    }
    receipt["verdict"] = (
        "passed"
        if client_identity["exact_pair"]
        and server_identity["exact_pair"]
        and len(rows) == len(service_ids)
        and all(row.get("verdict") == "passed" for row in rows)
        else "failed"
    )
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(output, 0o600)
    if receipt["verdict"] != "passed":
        raise RuntimeError(json.dumps(receipt, indent=2))
    print(output)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    python = _absolute_executable(args.python)
    if not args.workspace_root.is_absolute():
        raise RuntimeError("MCP probe workspace root must be an absolute path")
    return asyncio.run(
        _run(
            python=python,
            workspace_root=args.workspace_root.resolve(),
            output=args.output,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
