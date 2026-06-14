#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sys
import tomllib
from datetime import timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aoa_session_memory_mcp.core import AoASessionMemoryMCPState  # noqa: E402
from aoa_session_memory_mcp.server import build_server  # noqa: E402
from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402


def _select_freshness_smoke_brief(state: AoASessionMemoryMCPState, latest_brief: dict) -> dict:
    latest_status = latest_brief.get("session", {}).get("archive_status")
    if latest_brief.get("ok") and latest_status == "indexed":
        return latest_brief

    indexed = state.session_search(
        "",
        filters={"doc_type": "session", "archive_status": "indexed"},
        limit=5,
    )
    for hit in indexed.get("results", []):
        if not isinstance(hit, dict):
            continue
        label = hit.get("session_label") or hit.get("session_id")
        if not label:
            continue
        brief = state.session_brief(str(label), max_segments=2)
        if brief.get("ok") and brief.get("session", {}).get("archive_status") == "indexed":
            return brief

    return latest_brief


def _portable_provider(status: dict) -> dict:
    provider = status.get("provider") if isinstance(status.get("provider"), dict) else {}
    providers = provider.get("providers") if isinstance(provider.get("providers"), dict) else {}
    portable = providers.get("portable_sqlite") if isinstance(providers.get("portable_sqlite"), dict) else {}
    return portable


def _provider_usable_for_smoke(status: dict) -> bool:
    provider = status.get("provider") if isinstance(status.get("provider"), dict) else {}
    portable = _portable_provider(status)
    if provider.get("ok"):
        return True
    return portable.get("status") == "stale" and bool(portable.get("db_path"))


def _stdio_env(state: AoASessionMemoryMCPState) -> dict[str, str]:
    return {
        **os.environ,
        "AOA_WORKSPACE_ROOT": state.workspace_root.as_posix(),
        "AOA_SESSION_MEMORY_ROOT": state.aoa_root.as_posix(),
        "AOA_SESSION_MEMORY_SCRIPT": state.script_path.as_posix(),
        "AOA_SESSION_MEMORY_MCP_TIMEOUT": "20",
    }


def _codex_config_path() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "config.toml"
    return Path.home() / ".codex" / "config.toml"


def _configured_stdio_params(state: AoASessionMemoryMCPState) -> tuple[StdioServerParameters | None, dict]:
    config_path = _codex_config_path()
    if not config_path.exists():
        return None, {"available": False, "reason": "codex_config_missing", "config_path": config_path.as_posix()}

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    servers = data.get("mcp_servers") if isinstance(data.get("mcp_servers"), dict) else {}
    entry = servers.get("aoa_session_memory") if isinstance(servers.get("aoa_session_memory"), dict) else None
    if not entry:
        return None, {"available": False, "reason": "aoa_session_memory_config_missing", "config_path": config_path.as_posix()}

    command = entry.get("command")
    args = entry.get("args")
    if not isinstance(command, str) or not command:
        raise SystemExit("configured Codex MCP aoa_session_memory command is missing")
    if args is None:
        args = []
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise SystemExit("configured Codex MCP aoa_session_memory args must be a list of strings")

    cwd_value = entry.get("cwd") or state.workspace_root.as_posix()
    if not isinstance(cwd_value, str):
        raise SystemExit("configured Codex MCP aoa_session_memory cwd must be a string")
    cwd = Path(os.path.expandvars(cwd_value)).expanduser()

    env = _stdio_env(state)
    configured_env = entry.get("env")
    if isinstance(configured_env, dict):
        env.update({str(key): str(value) for key, value in configured_env.items()})

    params = StdioServerParameters(command=command, args=args, cwd=cwd.as_posix(), env=env)
    meta = {
        "available": True,
        "config_path": config_path.as_posix(),
        "command": command,
        "args": args,
        "cwd": cwd.as_posix(),
    }
    return params, meta


async def _stdio_tool_smoke(state: AoASessionMemoryMCPState, session: str) -> dict:
    params = StdioServerParameters(
        command=sys.executable,
        args=[(REPO_ROOT / "scripts" / "aoa_session_memory_mcp_server.py").as_posix()],
        cwd=REPO_ROOT.as_posix(),
        env=_stdio_env(state),
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as mcp_session:
            await mcp_session.initialize()
            tools = {tool.name for tool in (await mcp_session.list_tools()).tools}
            required_tools = {
                "aoa_session_entity_inventory",
                "aoa_session_agent_responses",
                "aoa_session_agent_closeouts",
                "aoa_session_agent_progress_updates",
                "aoa_session_agent_reasoning_windows",
                "aoa_session_task_episodes",
                "aoa_session_answer_neighborhood",
            }
            missing_tools = sorted(required_tools - tools)
            if missing_tools:
                raise SystemExit(f"stdio MCP tool list is missing required tools: {missing_tools}")

            async def call_json(name: str, arguments: dict, timeout_seconds: int = 50) -> dict:
                result = await mcp_session.call_tool(
                    name,
                    arguments,
                    read_timeout_seconds=timedelta(seconds=timeout_seconds),
                )
                if result.isError:
                    raise SystemExit(f"stdio MCP {name} call failed: {result.content}")
                if not result.content:
                    raise SystemExit(f"stdio MCP {name} returned no content")
                payload = json.loads(result.content[0].text)
                if not isinstance(payload, dict):
                    raise SystemExit(f"stdio MCP {name} returned non-object JSON")
                if not payload.get("ok"):
                    raise SystemExit(f"stdio MCP {name} returned not-ok payload: {payload.get('diagnostics')}")
                return payload

            inventory = await call_json(
                "aoa_session_entity_inventory",
                {"layer": "skill", "limit": 5, "sample_limit": 0},
            )
            responses = await call_json("aoa_session_agent_responses", {"session": session, "limit": 2})
            closeouts = await call_json("aoa_session_agent_closeouts", {"session": session, "limit": 2})
            progress = await call_json("aoa_session_agent_progress_updates", {"session": session, "limit": 2})
            reasoning = await call_json(
                "aoa_session_agent_reasoning_windows",
                {"session": session, "limit": 1, "before": 1, "after": 2},
            )
            episodes = await call_json("aoa_session_task_episodes", {"session": session, "limit": 2})
            neighborhood = await call_json(
                "aoa_session_answer_neighborhood",
                {"session": session, "limit": 1, "before": 1, "after": 2},
            )

    if inventory.get("entity_count", 0) <= 0:
        raise SystemExit(f"stdio MCP entity inventory returned no entities: {inventory.get('diagnostics')}")
    if responses.get("result_count", 0) <= 0:
        raise SystemExit("stdio MCP agent responses route returned no results")
    if closeouts.get("result_count", 0) <= 0:
        raise SystemExit("stdio MCP agent closeouts route returned no results")
    if progress.get("result_count", 0) <= 0:
        raise SystemExit("stdio MCP agent progress route returned no results")
    if reasoning.get("window_count", 0) <= 0:
        raise SystemExit("stdio MCP agent reasoning windows route returned no windows")
    if episodes.get("result_count", 0) <= 0:
        raise SystemExit("stdio MCP task episodes route returned no results")
    if neighborhood.get("window_count", 0) <= 0:
        raise SystemExit("stdio MCP answer neighborhood route returned no windows")
    return {
        "tool_count": len(tools),
        "inventory_entity_count": inventory.get("entity_count"),
        "inventory_source": inventory.get("source"),
        "agent_response_count": responses.get("result_count"),
        "agent_closeout_count": closeouts.get("result_count"),
        "agent_progress_count": progress.get("result_count"),
        "agent_reasoning_window_count": reasoning.get("window_count"),
        "task_episode_count": episodes.get("result_count"),
        "answer_neighborhood_count": neighborhood.get("window_count"),
    }


async def _configured_stdio_smoke(state: AoASessionMemoryMCPState) -> dict:
    params, meta = _configured_stdio_params(state)
    if params is None:
        return {**meta, "ok": True, "skipped": True}

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as mcp_session:
            await mcp_session.initialize()
            tools = {tool.name for tool in (await mcp_session.list_tools()).tools}
            required_tools = {
                "aoa_session_memory_status",
                "aoa_session_agent_responses",
                "aoa_session_agent_closeouts",
                "aoa_session_agent_progress_updates",
                "aoa_session_agent_reasoning_windows",
                "aoa_session_task_episodes",
                "aoa_session_answer_neighborhood",
            }
            missing_tools = sorted(required_tools - tools)
            if missing_tools:
                raise SystemExit(f"configured Codex MCP tool list is missing required tools: {missing_tools}")

            result = await mcp_session.call_tool(
                "aoa_session_memory_status",
                {"include_live": False},
                read_timeout_seconds=timedelta(seconds=20),
            )
            if result.isError:
                raise SystemExit(f"configured Codex MCP status call failed: {result.content}")
            if not result.content:
                raise SystemExit("configured Codex MCP status call returned no content")
            payload = json.loads(result.content[0].text)
            if not isinstance(payload, dict) or not payload.get("ok"):
                raise SystemExit(f"configured Codex MCP status returned not-ok payload: {payload}")

    return {**meta, "ok": True, "skipped": False, "tool_count": len(tools), "status_ok": payload.get("ok")}


def main() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "src/aoa_session_memory_mcp/core.py",
        "src/aoa_session_memory_mcp/server.py",
        "scripts/aoa_session_memory_mcp_server.py",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    state = AoASessionMemoryMCPState.discover()
    status = state.session_memory_status()
    if not _provider_usable_for_smoke(status):
        raise SystemExit(f"search provider is not ready: {status['provider'].get('diagnostics')}")
    if not status["atlas"].get("root_index_exists"):
        raise SystemExit("atlas root index is missing")
    trace = state.session_trace("aoa-session-memory-mcp", kind="mcp", doc_type="session", limit=5, per_route_limit=3)
    if not trace.get("route_candidates"):
        raise SystemExit("trace-route did not return route candidates")
    search = state.session_search("aoa-session-memory", limit=3)
    if search.get("result_count", 0) <= 0:
        raise SystemExit("session search returned no smoke hits")
    route_only = state.session_search("", filters={"route_signal": "tool:view_image", "doc_type": "event"}, limit=3)
    if route_only.get("result_count", 0) <= 0:
        raise SystemExit("route-only session search returned no smoke hits")
    skill_inventory = state.session_entity_inventory(layer="skill", limit=5)
    if not skill_inventory.get("ok") or skill_inventory.get("entity_count", 0) <= 0:
        raise SystemExit(f"skill entity inventory failed: {skill_inventory.get('diagnostics')}")
    git_inventory = state.session_entity_inventory(layer="git", limit=5)
    if not git_inventory.get("ok") or git_inventory.get("entity_count", 0) <= 0:
        raise SystemExit(f"git entity inventory failed: {git_inventory.get('diagnostics')}")
    hook_receipts = state.session_hook_receipts(event_name="UserPromptSubmit", limit=5)
    if not hook_receipts.get("ok"):
        raise SystemExit(f"hook receipts surface failed: {hook_receipts.get('diagnostics')}")
    neighborhood = state.session_entity_usage_neighborhood(
        "view_image",
        kind="tool",
        limit=1,
        per_route_limit=3,
        before=1,
        after=3,
        raw_preview_chars=240,
    )
    if not neighborhood.get("ok") or not neighborhood.get("neighborhoods"):
        raise SystemExit(f"usage neighborhood returned no evidence windows: {neighborhood.get('diagnostics')}")
    latest_brief = state.session_brief("latest", max_segments=2)
    if not latest_brief.get("ok") or not latest_brief.get("refs", {}).get("manifest"):
        raise SystemExit("latest session brief is not readable")
    brief = _select_freshness_smoke_brief(state, latest_brief)
    if not brief.get("ok") or brief.get("session", {}).get("archive_status") != "indexed":
        raise SystemExit("no indexed session brief is available for freshness smoke")
    latest_session = brief.get("session", {}).get("label") or "latest"
    session_only = state.session_search("", filters={"session": latest_session}, limit=1)
    if session_only.get("result_count", 0) <= 0 or session_only.get("provider", {}).get("status") != "local_session_filter_fast_path":
        raise SystemExit(f"session-only search fast path failed: {session_only.get('diagnostics')}")
    freshness_refs = [brief["refs"]["manifest"]]
    raw_path = Path(brief["refs"]["manifest"]).parent / "raw" / "session.raw.jsonl"
    raw_checked = raw_path.exists()
    if raw_checked:
        freshness_refs.append("raw:line:1")
    freshness = state.session_freshness_check(freshness_refs, session=latest_session)
    failed_ref_checks = [
        check
        for check in freshness.get("checks", [])
        if check.get("status") not in {"present", "needs_session_context"}
    ]
    if failed_ref_checks:
        raise SystemExit(f"freshness ref resolution failed: {failed_ref_checks}")
    freshness_status = freshness.get("projection_freshness", {}).get("status")
    if not freshness.get("ok") or freshness_status != "current":
        raise SystemExit(f"freshness smoke is not current: {freshness_status}")
    server = build_server()
    if server is None:
        raise SystemExit("MCP server did not build")
    stdio_smoke = asyncio.run(_stdio_tool_smoke(state, latest_session))
    configured_stdio_smoke = asyncio.run(_configured_stdio_smoke(state))

    print(
        json.dumps(
            {
                "ok": True,
                "aoa_root": status["aoa_root"],
                "provider_ok": status["provider"].get("ok"),
                "provider_status": _portable_provider(status).get("status"),
                "atlas_entry_count": status["atlas"].get("entry_count"),
                "trace_candidates": len(trace.get("route_candidates", [])),
                "search_result_count": search.get("result_count"),
                "route_only_result_count": route_only.get("result_count"),
                "skill_inventory_count": skill_inventory.get("entity_count"),
                "git_inventory_count": git_inventory.get("entity_count"),
                "session_only_result_count": session_only.get("result_count"),
                "hook_receipt_count": hook_receipts.get("total_receipt_count"),
                "hook_receipt_error_count": hook_receipts.get("summary", {}).get("error_receipt_count"),
                "usage_neighborhood_count": neighborhood.get("quality", {}).get("neighborhood_count"),
                "latest_session": latest_brief.get("session", {}).get("label") or "latest",
                "freshness_smoke_session": latest_session,
                "freshness_ok": freshness.get("ok"),
                "freshness_projection": freshness.get("projection_freshness", {}).get("status"),
                "raw_line_freshness_checked": raw_checked,
                "stdio_tool_count": stdio_smoke["tool_count"],
                "stdio_inventory_entity_count": stdio_smoke["inventory_entity_count"],
                "stdio_inventory_source": stdio_smoke["inventory_source"],
                "stdio_agent_response_count": stdio_smoke["agent_response_count"],
                "stdio_agent_closeout_count": stdio_smoke["agent_closeout_count"],
                "stdio_agent_progress_count": stdio_smoke["agent_progress_count"],
                "stdio_agent_reasoning_window_count": stdio_smoke["agent_reasoning_window_count"],
                "stdio_task_episode_count": stdio_smoke["task_episode_count"],
                "stdio_answer_neighborhood_count": stdio_smoke["answer_neighborhood_count"],
                "configured_stdio": configured_stdio_smoke,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
