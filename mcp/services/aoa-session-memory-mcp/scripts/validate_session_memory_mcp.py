#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import argparse
import json
import os
import sys
import tomllib
from contextlib import AsyncExitStack
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
from mcp.client.streamable_http import streamable_http_client  # noqa: E402


REQUIRED_STDIO_SMOKE_TOOLS = {
    "aoa_session_memory_status",
    "aoa_session_search",
    "aoa_session_literal_query_plan",
    "aoa_session_agent_responses",
    "aoa_session_agent_closeouts",
    "aoa_session_agent_progress_updates",
    "aoa_session_agent_reasoning_windows",
    "aoa_session_task_episodes",
    "aoa_session_goal_lifecycles",
    "aoa_session_answer_neighborhood",
    "aoa_session_trace",
    "aoa_session_entity_dossier",
    "aoa_session_entity_usage_chain",
    "aoa_session_entity_usage_audit",
    "aoa_session_entity_usage_neighborhood",
    "aoa_session_entity_registry",
    "aoa_session_entity_inventory",
    "aoa_session_hook_receipts",
    "aoa_session_retrieve",
    "aoa_session_live_scenario_audit",
    "aoa_session_live_scenario_corpus_check",
    "aoa_session_live_scenario_corpus_inventory",
    "aoa_session_maintenance_status",
    "aoa_session_route_rollup_query",
    "aoa_session_direct_event_rollup_query",
    "aoa_session_projection_status",
    "aoa_session_graph_neighborhood",
    "aoa_session_graph_bridge",
    "aoa_session_graph_cooccurrence",
}

ACCEPTABLE_FRESHNESS_SMOKE_STATUSES = {
    "current",
    "current_with_deferred_live_updates",
    "current_with_global_deferred_live_updates",
    "current_with_global_stale",
}

ACCEPTABLE_FRESHNESS_SMOKE_STATUSES = {
    "current",
    "current_with_deferred_live_updates",
    "current_with_global_deferred_live_updates",
    "current_with_global_stale",
}

CONFIGURED_HTTP_TIMEOUT_SECONDS = 30.0
CONFIGURED_HTTP_RESPONSE_TIMEOUT_SECONDS = 120.0


def _search_alias_smoke_arguments(limit: int = 3) -> dict:
    return {
        "query": "",
        "filters": {
            "route_signal": "mcp:aoa_session_memory_mcp",
            "doc_type": "event",
            "layer": "mcp",
            "use_shards": True,
        },
        "limit": limit,
    }


def _freshness_smoke_status(state: AoASessionMemoryMCPState, brief: dict) -> str:
    if not brief.get("ok") or brief.get("session", {}).get("archive_status") != "indexed":
        return ""
    label = brief.get("session", {}).get("label") or brief.get("session", {}).get("id")
    manifest = brief.get("refs", {}).get("manifest") if isinstance(brief.get("refs"), dict) else ""
    if not label or not manifest:
        return ""
    refs = [manifest]
    raw_path = Path(manifest).parent / "raw" / "session.raw.jsonl"
    if raw_path.exists():
        refs.append("raw:line:1")
    freshness = state.session_freshness_check(refs, session=str(label))
    if not freshness.get("ok"):
        return str(freshness.get("projection_freshness", {}).get("status") or "")
    return str(freshness.get("projection_freshness", {}).get("status") or "")


def _select_freshness_smoke_brief(state: AoASessionMemoryMCPState, latest_brief: dict) -> dict:
    latest_status = latest_brief.get("session", {}).get("archive_status")
    if (
        latest_brief.get("ok")
        and latest_status == "indexed"
        and _freshness_smoke_status(state, latest_brief) in ACCEPTABLE_FRESHNESS_SMOKE_STATUSES
    ):
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
        if (
            brief.get("ok")
            and brief.get("session", {}).get("archive_status") == "indexed"
            and _freshness_smoke_status(state, brief) in ACCEPTABLE_FRESHNESS_SMOKE_STATUSES
        ):
            return brief
        refs = hit.get("refs") if isinstance(hit.get("refs"), dict) else {}
        manifest = refs.get("session") or hit.get("session_ref")
        fallback_brief = {
            "ok": True,
            "session": {
                "id": hit.get("session_id"),
                "label": label,
                "archive_status": "indexed",
            },
            "refs": {"manifest": str(manifest)},
        }
        if (
            manifest
            and hit.get("archive_status") == "indexed"
            and _freshness_smoke_status(state, fallback_brief) in ACCEPTABLE_FRESHNESS_SMOKE_STATUSES
        ):
            return fallback_brief

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


def _read_only_tool_annotation_summary(tools: list[object], context: str) -> dict[str, object]:
    invalid: list[dict[str, object]] = []
    for tool in tools:
        name = str(getattr(tool, "name", "<unnamed>"))
        annotations = getattr(tool, "annotations", None)
        observed = {
            "readOnlyHint": getattr(annotations, "readOnlyHint", None),
            "destructiveHint": getattr(annotations, "destructiveHint", None),
            "idempotentHint": getattr(annotations, "idempotentHint", None),
            "openWorldHint": getattr(annotations, "openWorldHint", None),
        }
        expected = {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
        if observed != expected:
            invalid.append({"tool": name, "observed": observed})
    if invalid:
        raise SystemExit(f"{context} MCP tool annotation contract failed: {invalid}")
    return {
        "schema": "aoa_session_memory_mcp_tool_annotation_contract_v1",
        "ok": True,
        "tool_count": len(tools),
        "read_only": True,
        "destructive": False,
        "idempotent": True,
        "open_world": False,
        "contract_limit": "metadata contract only; tool behavior remains covered by package tests and smoke calls",
    }


def _codex_config_path() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "config.toml"
    return Path.home() / ".codex" / "config.toml"


def _linux_boot_epoch(proc_root: Path = Path("/proc")) -> float | None:
    stat_path = proc_root / "stat"
    try:
        for line in stat_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except OSError:
        return None
    return None


def _process_start_epoch(pid: str, *, proc_root: Path = Path("/proc"), boot_epoch: float | None = None) -> float | None:
    if boot_epoch is None:
        boot_epoch = _linux_boot_epoch(proc_root)
    if boot_epoch is None:
        return None
    try:
        stat_text = (proc_root / pid / "stat").read_text(encoding="utf-8")
        ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
        start_ticks = int(stat_text.split()[21])
    except (OSError, ValueError, IndexError):
        return None
    return boot_epoch + (start_ticks / float(ticks))


def _proc_cmdline(pid: str, proc_root: Path = Path("/proc")) -> list[str]:
    try:
        data = (proc_root / pid / "cmdline").read_bytes()
    except OSError:
        return []
    return [part.decode("utf-8", errors="replace") for part in data.split(b"\0") if part]


def _proc_ppid(pid: str, proc_root: Path = Path("/proc")) -> int | None:
    try:
        for line in (proc_root / pid / "status").read_text(encoding="utf-8").splitlines():
            if line.startswith("PPid:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _proc_cwd(pid: str, proc_root: Path = Path("/proc")) -> str:
    try:
        return (proc_root / pid / "cwd").resolve().as_posix()
    except OSError:
        return ""


SESSION_MEMORY_MCP_SERVER_BASENAMES = {
    "aoa-session-memory-mcp-server",
    "aoa-session-memory-mcp-server.py",
    "aoa_session_memory_mcp_server.py",
}
CODEX_PROCESS_BASENAMES = {
    "codex",
    "codex.exe",
    "codex.js",
}


def _restart_required_source_paths() -> list[Path]:
    return [
        REPO_ROOT / "src/aoa_session_memory_mcp/server.py",
        REPO_ROOT / "scripts/aoa_session_memory_mcp_server.py",
    ]


def _core_auto_reload_source_paths() -> list[Path]:
    return [REPO_ROOT / "src/aoa_session_memory_mcp/core.py"]


def _max_existing_mtime(paths: list[Path]) -> float:
    return max((path.stat().st_mtime for path in paths if path.exists()), default=0.0)


def _is_session_memory_mcp_server_cmdline(cmdline: list[str]) -> bool:
    for part in cmdline:
        if Path(part).name in SESSION_MEMORY_MCP_SERVER_BASENAMES:
            return True
        if part == "aoa_session_memory_mcp.server":
            return True
    return False


def _is_codex_process_cmdline(cmdline: list[str]) -> bool:
    return any(Path(part).name in CODEX_PROCESS_BASENAMES for part in cmdline)


def _codex_session_advisory(proc_root: Path = Path("/proc")) -> dict:
    if not proc_root.is_dir():
        return {"available": False, "reason": "procfs_unavailable"}

    restart_source_mtime = _max_existing_mtime(_restart_required_source_paths())
    core_auto_reload_source_mtime = _max_existing_mtime(_core_auto_reload_source_paths())
    config_path = _codex_config_path()
    config_mtime = config_path.stat().st_mtime if config_path.exists() else 0.0
    boot_epoch = _linux_boot_epoch(proc_root)

    ancestor_pids: set[int] = set()
    parent = os.getpid()
    while parent:
        ancestor_pids.add(parent)
        next_parent = _proc_ppid(str(parent), proc_root=proc_root)
        if not next_parent or next_parent == parent:
            break
        parent = next_parent

    mcp_children_by_parent: dict[int, list[int]] = {}
    mcp_processes_by_pid: dict[int, dict] = {}
    codex_processes: list[dict] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmdline = _proc_cmdline(entry.name, proc_root=proc_root)
        if not cmdline:
            continue
        started_at_epoch = _process_start_epoch(entry.name, proc_root=proc_root, boot_epoch=boot_epoch)
        if _is_session_memory_mcp_server_cmdline(cmdline):
            ppid = _proc_ppid(entry.name, proc_root=proc_root)
            if ppid is not None:
                mcp_children_by_parent.setdefault(ppid, []).append(pid)
            mcp_processes_by_pid[pid] = {
                "pid": pid,
                "ppid": ppid,
                "started_at_epoch": started_at_epoch,
                "started_before_current_source": bool(
                    started_at_epoch is not None and restart_source_mtime and started_at_epoch < restart_source_mtime
                ),
            }
            continue
        if not _is_codex_process_cmdline(cmdline):
            continue

        codex_processes.append(
            {
                "pid": pid,
                "ppid": _proc_ppid(entry.name, proc_root=proc_root),
                "cwd": _proc_cwd(entry.name, proc_root=proc_root),
                "cmdline": cmdline,
                "started_at_epoch": started_at_epoch,
                "is_current_validator_ancestor": pid in ancestor_pids,
                "started_before_config": bool(started_at_epoch is not None and config_mtime and started_at_epoch < config_mtime),
                "started_before_current_source": bool(
                    started_at_epoch is not None and restart_source_mtime and started_at_epoch < restart_source_mtime
                ),
                "started_before_core_auto_reload_source": bool(
                    started_at_epoch is not None
                    and core_auto_reload_source_mtime
                    and started_at_epoch < core_auto_reload_source_mtime
                ),
            }
        )

    for process in codex_processes:
        child_pids = sorted(mcp_children_by_parent.get(process["pid"], []))
        process["aoa_session_memory_child_pids"] = child_pids
        process["has_aoa_session_memory_child"] = bool(child_pids)

    current_codex = [process for process in codex_processes if process["is_current_validator_ancestor"]]
    current_predates_config = any(process["started_before_config"] for process in current_codex)
    current_predates_source = any(process["started_before_current_source"] for process in current_codex)
    current_has_mcp_child = any(process["has_aoa_session_memory_child"] for process in current_codex)
    current_mcp_child_processes = [
        mcp_processes_by_pid[pid]
        for process in current_codex
        for pid in process.get("aoa_session_memory_child_pids", [])
        if pid in mcp_processes_by_pid
    ]
    current_mcp_child_count = len(current_mcp_child_processes)
    current_stale_mcp_child_count = sum(
        1 for process in current_mcp_child_processes if process.get("started_before_current_source")
    )
    current_has_fresh_mcp_child = bool(
        current_mcp_child_processes and current_stale_mcp_child_count < current_mcp_child_count
    )
    configured = config_path.exists()
    config_reload_advisory = bool(
        current_codex
        and configured
        and current_predates_config
        and current_has_fresh_mcp_child
    )
    live_transport_advisory = bool(
        current_codex
        and configured
        and not current_has_fresh_mcp_child
    )

    return {
        "available": True,
        "config_path": config_path.as_posix(),
        "config_mtime_epoch": config_mtime or None,
        "source_mtime_epoch": restart_source_mtime or None,
        "restart_required_source_mtime_epoch": restart_source_mtime or None,
        "core_auto_reload_source_mtime_epoch": core_auto_reload_source_mtime or None,
        "current_codex_process_count": len(current_codex),
        "current_session_predates_config": current_predates_config,
        "current_session_predates_current_source": current_predates_source,
        "current_session_has_aoa_session_memory_child": current_has_mcp_child,
        "current_session_mcp_child_count": current_mcp_child_count,
        "current_session_mcp_child_stale_count": current_stale_mcp_child_count,
        "current_session_has_fresh_aoa_session_memory_child": current_has_fresh_mcp_child,
        "config_reload_advisory": config_reload_advisory,
        "live_transport_restart_advisory": live_transport_advisory,
        "advisory": (
            "This Codex session has no fresh direct aoa-session-memory MCP child. Fresh configured stdio can prove the "
            "server, but direct in-session MCP calls need a Codex/MCP restart before they are "
            "freshness proof."
            if live_transport_advisory
            else "Current Codex session has a fresh direct MCP child when configured; config mtime drift is advisory only."
        ),
        "current_codex_processes": current_codex[:6],
        "processes": codex_processes[:12],
        "omitted_process_count": max(0, len(codex_processes) - 12),
    }


def _running_mcp_process_advisory(proc_root: Path = Path("/proc")) -> dict:
    if not proc_root.is_dir():
        return {"available": False, "reason": "procfs_unavailable"}

    restart_source_mtime = _max_existing_mtime(_restart_required_source_paths())
    core_auto_reload_source_mtime = _max_existing_mtime(_core_auto_reload_source_paths())
    boot_epoch = _linux_boot_epoch(proc_root)
    processes: list[dict] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        cmdline = _proc_cmdline(entry.name, proc_root=proc_root)
        if not cmdline:
            continue
        if not _is_session_memory_mcp_server_cmdline(cmdline):
            continue
        cwd = ""
        try:
            cwd = (proc_root / entry.name / "cwd").resolve().as_posix()
        except OSError:
            cwd = ""
        started_at_epoch = _process_start_epoch(entry.name, proc_root=proc_root, boot_epoch=boot_epoch)
        stale = bool(started_at_epoch is not None and restart_source_mtime and started_at_epoch < restart_source_mtime)
        processes.append(
            {
                "pid": int(entry.name),
                "cwd": cwd,
                "cmdline": cmdline,
                "started_at_epoch": started_at_epoch,
                "started_before_current_source": stale,
                "started_before_core_auto_reload_source": bool(
                    started_at_epoch is not None
                    and core_auto_reload_source_mtime
                    and started_at_epoch < core_auto_reload_source_mtime
                ),
            }
        )

    stale_count = sum(1 for process in processes if process["started_before_current_source"])
    return {
        "available": True,
        "source_mtime_epoch": restart_source_mtime or None,
        "restart_required_source_mtime_epoch": restart_source_mtime or None,
        "core_auto_reload_source_mtime_epoch": core_auto_reload_source_mtime or None,
        "process_count": len(processes),
        "stale_process_count": stale_count,
        "restart_advisory": stale_count > 0,
        "advisory": (
            "Some already-running Codex MCP transports started before the current restart-required source. "
            "Configured stdio smoke proves a fresh server, but those transports need a Codex/MCP restart "
            "before their live output is freshness proof."
            if stale_count
            else "No already-running aoa-session-memory MCP process is older than the restart-required source files."
        ),
        "processes": processes[:12],
        "omitted_process_count": max(0, len(processes) - 12),
    }


def _configured_transport_spec(state: AoASessionMemoryMCPState) -> tuple[dict | None, dict]:
    config_path = _codex_config_path()
    if not config_path.exists():
        return None, {"available": False, "reason": "codex_config_missing", "config_path": config_path.as_posix()}

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    servers = data.get("mcp_servers") if isinstance(data.get("mcp_servers"), dict) else {}
    entry = servers.get("aoa_session_memory") if isinstance(servers.get("aoa_session_memory"), dict) else None
    if not entry:
        return None, {"available": False, "reason": "aoa_session_memory_config_missing", "config_path": config_path.as_posix()}

    raw_url = entry.get("url")
    if raw_url is not None and not isinstance(raw_url, str):
        raise SystemExit("configured Codex MCP aoa_session_memory url must be a string")
    if raw_url:
        preflight = state.session_mcp_transport_preflight(proc_root=Path("/__aoa_validator_no_procfs__"))
        configured_server = preflight.get("configured_server") if isinstance(preflight, dict) else None
        if not isinstance(configured_server, dict) or configured_server.get("configured") is not True:
            diagnostics = configured_server.get("diagnostics") if isinstance(configured_server, dict) else None
            raise SystemExit(f"configured Codex MCP aoa_session_memory HTTP endpoint is invalid: {diagnostics}")
        authentication = configured_server.get("authentication")
        if not isinstance(authentication, dict) or authentication.get("configured") is not True:
            raise SystemExit("configured Codex MCP aoa_session_memory HTTP bearer route is invalid")
        environment = authentication.get("environment")
        if not isinstance(environment, dict) or environment.get("available") is not True:
            raise SystemExit("configured Codex MCP aoa_session_memory HTTP bearer credential is unavailable")
        if environment.get("valid") is not True:
            raise SystemExit("configured Codex MCP aoa_session_memory HTTP bearer credential is invalid")
        bearer_token_env_var = authentication.get("env_var")
        if not isinstance(bearer_token_env_var, str) or not bearer_token_env_var:
            raise SystemExit("configured Codex MCP aoa_session_memory HTTP bearer env var is invalid")
        return (
            {
                "transport": "streamable-http",
                "url": raw_url,
                "bearer_token_env_var": bearer_token_env_var,
            },
            {
                "available": True,
                "config_path": config_path.as_posix(),
                "transport": "streamable-http",
                "url": configured_server.get("url"),
                "authentication": {
                    "mode": "bearer_env",
                    "env_var": bearer_token_env_var,
                    "client_environment_ready": True,
                },
            },
        )

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
    meta["transport"] = "stdio"
    return {"transport": "stdio", "params": params}, meta


def _payload_count(payload: dict, key: str) -> int:
    value = payload.get(key)
    return value if isinstance(value, int) else 0


def _payload_count_or_list_len(payload: dict, key: str, list_key: str) -> int:
    value = payload.get(key)
    if isinstance(value, int):
        return value
    items = payload.get(list_key)
    return len(items) if isinstance(items, list) else 0


def _has_first_raw_or_segment_ref(ref: dict) -> bool:
    return bool(
        isinstance(ref, dict)
        and (
            ref.get("raw")
            or ref.get("raw_ref")
            or ref.get("segment")
            or ref.get("segment_ref")
        )
    )


def _first_entity(payload: dict) -> dict:
    entities = payload.get("entities")
    if isinstance(entities, list) and entities and isinstance(entities[0], dict):
        return entities[0]
    return {}


def _runtime_reload_required(payload: dict) -> bool | None:
    runtime = payload.get("runtime")
    if isinstance(runtime, dict):
        value = runtime.get("reload_required")
        return value if isinstance(value, bool) else None
    return None


def _assert_bounded_inventory_packet(payload: dict, label: str, *, max_chars: int = 24000) -> None:
    route_packet = payload.get("route_packet") if isinstance(payload.get("route_packet"), dict) else {}
    response_profile = payload.get("response_profile") if isinstance(payload.get("response_profile"), dict) else {}
    if route_packet.get("bounded") is not True:
        raise SystemExit(f"{label} inventory missing bounded route_packet: {payload}")
    if response_profile.get("bounded_mcp_packet") is not True:
        raise SystemExit(f"{label} inventory missing bounded response_profile: {payload}")
    sample_budget = response_profile.get("sample_budget")
    sample_count = response_profile.get("sample_count")
    if not isinstance(sample_budget, int) or not isinstance(sample_count, int) or sample_count > sample_budget:
        raise SystemExit(f"{label} inventory sample budget contract failed: {response_profile}")
    if response_profile.get("raw_text_loaded") is not False or response_profile.get("entry_payloads_loaded") is not False:
        raise SystemExit(f"{label} inventory loaded heavy payloads on MCP route: {response_profile}")
    if not payload.get("next_expansion"):
        raise SystemExit(f"{label} inventory missing explicit next expansion route")
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized) > max_chars:
        raise SystemExit(f"{label} inventory response is too large for bounded MCP route: {len(serialized)} > {max_chars}")
    for entity in payload.get("entities", []):
        if not isinstance(entity, dict):
            continue
        for sample in entity.get("samples", []):
            if not isinstance(sample, dict):
                continue
            refs = sample.get("refs") if isinstance(sample.get("refs"), dict) else {}
            heavy_refs = sorted({"atlas_entry", "atlas_markdown", "segment_index", "session"} & set(refs))
            if heavy_refs:
                raise SystemExit(f"{label} inventory sample carried heavy refs {heavy_refs}: {sample}")
            if "doc_id" in sample or "title" in sample:
                raise SystemExit(f"{label} inventory sample carried heavy display fields: {sample}")


def _candidate_sessions(*payloads: dict) -> list[str]:
    sessions: list[str] = []
    for payload in payloads:
        results = payload.get("results")
        if not isinstance(results, list):
            continue
        for item in results:
            if not isinstance(item, dict):
                continue
            for key in ("session_label", "session_id", "session"):
                value = item.get(key)
                if isinstance(value, str) and value and value not in sessions:
                    sessions.append(value)
    return sessions


def _select_usage_neighborhood_probe(
    state: AoASessionMemoryMCPState,
    route_only: dict,
    goal_usage_probe: dict,
) -> tuple[str, str, dict]:
    anchors = ("view_image", "update_goal", "get_goal", "apply_patch", "exec_command")
    sessions = _candidate_sessions(route_only, goal_usage_probe)
    attempts: list[str] = []

    for session in sessions:
        for anchor in anchors:
            attempts.append(f"{anchor}@{session}")
            neighborhood = state.session_entity_usage_neighborhood(
                anchor,
                kind="tool",
                limit=1,
                per_route_limit=1,
                before=1,
                after=2,
                raw_preview_chars=0,
                document_limit=3,
                session=session,
            )
            if neighborhood.get("ok") and neighborhood.get("neighborhoods"):
                return anchor, session, neighborhood

    raise SystemExit(f"usage neighborhood returned no evidence windows for indexed smoke candidates: {attempts}")


def _stdio_route_count_summary(
    inventory: dict,
    mcp_service_inventory: dict,
    hook_inventory: dict,
    tool_inventory: dict,
    api_inventory: dict,
    open_threads: dict,
    search_alias: dict,
    responses: dict,
    closeouts: dict,
    progress: dict,
    reasoning: dict,
    episodes: dict,
    goal_lifecycles: dict,
    neighborhood: dict,
    registry: dict,
    literal_plan: dict,
    entity_dossier: dict,
    usage_chain: dict,
    usage_alias: dict,
    agent_event_usage: dict,
    graph_neighborhood: dict,
    graph_cooccurrence: dict,
    retrieve_usage: dict,
    live_scenario: dict,
    live_scenario_corpus: dict,
    live_scenario_corpus_inventory: dict,
    maintenance_status: dict,
    direct_event_rollup_query: dict,
    projection_status: dict,
    *,
    tool_count: int,
) -> dict:
    return {
        "tool_count": tool_count,
        "inventory_entity_count": _payload_count(inventory, "entity_count"),
        "inventory_source": inventory.get("source"),
        "inventory_latest_session_date": _first_entity(inventory).get("latest_session_date"),
        "inventory_runtime_reload_required": _runtime_reload_required(inventory),
        "inventory_sample_count": inventory.get("response_profile", {}).get("sample_count")
        if isinstance(inventory.get("response_profile"), dict)
        else None,
        "inventory_sample_omitted_count": inventory.get("response_profile", {}).get("sample_omitted_count")
        if isinstance(inventory.get("response_profile"), dict)
        else None,
        "mcp_service_inventory_layer": mcp_service_inventory.get("layer"),
        "mcp_service_inventory_requested_layer": mcp_service_inventory.get("requested_layer"),
        "mcp_service_inventory_latest_session_date": _first_entity(mcp_service_inventory).get("latest_session_date"),
        "mcp_service_inventory_runtime_reload_required": _runtime_reload_required(mcp_service_inventory),
        "mcp_service_inventory_sample_count": mcp_service_inventory.get("response_profile", {}).get("sample_count")
        if isinstance(mcp_service_inventory.get("response_profile"), dict)
        else None,
        "hook_inventory_entity_count": _payload_count(hook_inventory, "entity_count"),
        "tool_inventory_entity_count": _payload_count(tool_inventory, "entity_count"),
        "api_inventory_entity_count": _payload_count(api_inventory, "entity_count"),
        "open_thread_result_count": _payload_count(open_threads, "result_count"),
        "search_alias_result_count": _payload_count(search_alias, "result_count"),
        "search_alias_projection_mode": search_alias.get("search_projection", {}).get("mode")
        if isinstance(search_alias.get("search_projection"), dict)
        else None,
        "agent_response_count": _payload_count(responses, "result_count"),
        "agent_closeout_count": _payload_count(closeouts, "result_count"),
        "agent_progress_count": _payload_count(progress, "result_count"),
        "agent_reasoning_window_count": _payload_count(reasoning, "window_count"),
        "task_episode_count": _payload_count(episodes, "result_count"),
        "goal_lifecycle_count": _payload_count(goal_lifecycles, "result_count"),
        "answer_neighborhood_count": _payload_count(neighborhood, "window_count"),
        "registry_entity_count": _payload_count(registry, "entity_count"),
        "literal_plan_primary_route": literal_plan.get("primary_route", {}).get("route_id")
        if isinstance(literal_plan.get("primary_route"), dict)
        else None,
        "literal_plan_structured_first": literal_plan.get("cost_profile", {}).get("structured_first")
        if isinstance(literal_plan.get("cost_profile"), dict)
        else None,
        "entity_dossier_usage_count": entity_dossier.get("quality", {}).get("usage_event_count")
        if isinstance(entity_dossier.get("quality"), dict)
        else None,
        "entity_dossier_graph_node_count": entity_dossier.get("quality", {}).get("graph_node_count")
        if isinstance(entity_dossier.get("quality"), dict)
        else None,
        "entity_dossier_raw_or_segment_ref_present": entity_dossier.get("quality", {}).get("raw_or_segment_ref_present")
        if isinstance(entity_dossier.get("quality"), dict)
        else None,
        "entity_usage_chain_usage_count": usage_chain.get("counts", {}).get("usage_event_count")
        if isinstance(usage_chain.get("counts"), dict)
        else None,
        "entity_usage_chain_success_count": usage_chain.get("counts", {}).get("chain_with_result_or_consequence_count")
        if isinstance(usage_chain.get("counts"), dict)
        else None,
        "entity_usage_chain_first_ref_present": bool(
            isinstance(usage_chain.get("first_ref"), dict)
            and _has_first_raw_or_segment_ref(usage_chain["first_ref"])
        ),
        "usage_alias_kind": usage_alias.get("kind"),
        "usage_alias_requested_kind": usage_alias.get("requested_kind"),
        "agent_event_usage_kind": agent_event_usage.get("kind"),
        "agent_event_usage_outcome_count": _payload_count(agent_event_usage, "outcome_event_count"),
        "graph_neighborhood_node_count": _payload_count(graph_neighborhood, "node_count"),
        "graph_neighborhood_edge_count": _payload_count(graph_neighborhood, "edge_count"),
        "graph_cooccurrence_count": _payload_count_or_list_len(
            graph_cooccurrence, "cooccurrence_count", "cooccurrences"
        ),
        "graph_cooccurrence_ref_count": _payload_count_or_list_len(
            graph_cooccurrence, "evidence_ref_count", "evidence_refs"
        ),
        "retrieve_usage_served_by": retrieve_usage.get("retrieval_redirect", {}).get("served_by")
        if isinstance(retrieve_usage.get("retrieval_redirect"), dict)
        else None,
        "live_scenario_count": live_scenario.get("quality", {}).get("scenario_count")
        if isinstance(live_scenario.get("quality"), dict)
        else None,
        "live_scenario_warn_count": live_scenario.get("quality", {}).get("warn_count")
        if isinstance(live_scenario.get("quality"), dict)
        else None,
        "live_scenario_entity_registry_active_count": (
            live_scenario.get("scenarios", [{}])[0].get("active_lookup_count")
            if isinstance(live_scenario.get("scenarios"), list) and live_scenario.get("scenarios")
            else None
        ),
        "live_scenario_entity_registry_observed_count": (
            live_scenario.get("scenarios", [{}])[0].get("observed_lookup_count")
            if isinstance(live_scenario.get("scenarios"), list) and live_scenario.get("scenarios")
            else None
        ),
        "live_scenario_entity_registry_unknown_count": (
            live_scenario.get("scenarios", [{}])[0].get("unknown_lookup_count")
            if isinstance(live_scenario.get("scenarios"), list) and live_scenario.get("scenarios")
            else None
        ),
        "live_scenario_entity_registry_stale_count": (
            live_scenario.get("scenarios", [{}])[0].get("stale_lookup_count")
            if isinstance(live_scenario.get("scenarios"), list) and live_scenario.get("scenarios")
            else None
        ),
        "live_scenario_entity_registry_removed_count": (
            live_scenario.get("scenarios", [{}])[0].get("removed_lookup_count")
            if isinstance(live_scenario.get("scenarios"), list) and live_scenario.get("scenarios")
            else None
        ),
        "live_scenario_entity_registry_transition_probe_count": (
            live_scenario.get("scenarios", [{}])[0].get("transition_probe_count")
            if isinstance(live_scenario.get("scenarios"), list) and live_scenario.get("scenarios")
            else None
        ),
        "live_scenario_corpus_case_count": live_scenario_corpus.get("case_count"),
        "live_scenario_corpus_actionable_gap_count": live_scenario_corpus.get("actionable_gap_count"),
        "live_scenario_corpus_inventory_case_count": live_scenario_corpus_inventory.get("case_count"),
        "live_scenario_corpus_inventory_truth_status": live_scenario_corpus_inventory.get("truth_status"),
        "maintenance_recommendation": maintenance_status.get("recommendation"),
        "maintenance_smoke_skipped": maintenance_status.get("mcp_access", {}).get("skipped_in_stdio_smoke")
        if isinstance(maintenance_status.get("mcp_access"), dict)
        else None,
        "direct_event_rollup_result_count": _payload_count(direct_event_rollup_query, "result_count"),
        "direct_event_rollup_freshness_status": direct_event_rollup_query.get("quality", {}).get("freshness_status")
        if isinstance(direct_event_rollup_query.get("quality"), dict)
        else None,
        "direct_event_rollup_materialized": direct_event_rollup_query.get("cost_profile", {}).get("uses_materialized_direct_event_rollup")
        if isinstance(direct_event_rollup_query.get("cost_profile"), dict)
        else None,
        "projection_status_ok": projection_status.get("ok"),
        "projection_completeness_status": projection_status.get("projection_completeness", {}).get("status")
        if isinstance(projection_status.get("projection_completeness"), dict)
        else None,
    }


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
            listed_tools = (await mcp_session.list_tools()).tools
            tool_annotation_contract = _read_only_tool_annotation_summary(listed_tools, "stdio")
            tools = {tool.name for tool in listed_tools}
            missing_tools = sorted(REQUIRED_STDIO_SMOKE_TOOLS - tools)
            if missing_tools:
                raise SystemExit(f"stdio MCP tool list is missing required tools: {missing_tools}")

            async def call_json(name: str, arguments: dict, timeout_seconds: int = 50, require_ok: bool = True) -> dict:
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
                if require_ok and not payload.get("ok"):
                    raise SystemExit(f"stdio MCP {name} returned not-ok payload: {payload.get('diagnostics')}")
                return payload

            inventory = await call_json(
                "aoa_session_entity_inventory",
                {"layer": "skill", "limit": 8, "sample_limit": 3},
            )
            mcp_service_inventory = await call_json(
                "aoa_session_entity_inventory",
                {"layer": "mcp_service", "query": "aoa-session-memory", "limit": 5, "sample_limit": 3},
            )
            hook_inventory = await call_json(
                "aoa_session_entity_inventory",
                {"layer": "hook", "limit": 5, "sample_limit": 2},
            )
            tool_inventory = await call_json(
                "aoa_session_entity_inventory",
                {"layer": "tool", "limit": 5, "sample_limit": 2},
            )
            api_inventory = await call_json(
                "aoa_session_entity_inventory",
                {"layer": "api", "limit": 5, "sample_limit": 2},
            )
            open_threads = await call_json(
                "aoa_session_search",
                {"query": "", "filters": {"route_signal": "agent_event:assistant_open_thread", "doc_type": "event"}, "limit": 3},
            )
            search_alias = await call_json(
                "aoa_session_search",
                _search_alias_smoke_arguments(limit=3),
            )
            registry = await call_json(
                "aoa_session_entity_registry",
                {"kind": "skill", "limit": 5},
            )
            literal_plan = await call_json(
                "aoa_session_literal_query_plan",
                {
                    "query": "aoa-session-memory-mcp",
                    "kind": "mcp_service",
                    "filters": {"doc_type": "event", "route_layer": "mcp", "max_shards": 3},
                },
                timeout_seconds=60,
            )
            responses = await call_json("aoa_session_agent_responses", {"session": session, "limit": 2})
            closeouts = await call_json("aoa_session_agent_closeouts", {"session": session, "limit": 2})
            progress = await call_json("aoa_session_agent_progress_updates", {"session": session, "limit": 2})
            reasoning = await call_json(
                "aoa_session_agent_reasoning_windows",
                {"session": session, "limit": 1, "before": 1, "after": 2},
            )
            episodes = await call_json("aoa_session_task_episodes", {"session": session, "limit": 2})
            goal_lifecycles = await call_json("aoa_session_goal_lifecycles", {"session": session, "limit": 2})
            neighborhood = await call_json(
                "aoa_session_answer_neighborhood",
                {"session": session, "limit": 1, "before": 1, "after": 2},
            )
            usage_alias = await call_json(
                "aoa_session_entity_usage_audit",
                {"anchor": "aoa-session-memory-mcp", "kind": "mcp_service", "limit": 2, "per_route_limit": 2},
                timeout_seconds=90,
            )
            usage_chain = await call_json(
                "aoa_session_entity_usage_chain",
                {"anchor": "aoa-session-memory-mcp", "kind": "mcp_service", "limit": 2, "per_route_limit": 3},
                timeout_seconds=90,
            )
            entity_dossier = await call_json(
                "aoa_session_entity_dossier",
                {
                    "anchor": "aoa-session-memory-mcp",
                    "kind": "mcp_service",
                    "usage_limit": 2,
                    "neighborhood_limit": 1,
                    "graph_limit": 6,
                    "graph_edge_limit": 6,
                },
                timeout_seconds=90,
            )
            agent_event_usage = await call_json(
                "aoa_session_entity_usage_audit",
                {"anchor": "assistant_answer", "kind": "agent_event", "limit": 3, "per_route_limit": 5},
                timeout_seconds=90,
            )
            graph_neighborhood = await call_json(
                "aoa_session_graph_neighborhood",
                {"anchor": "aoa-session-memory-mcp", "kind": "mcp_service", "limit": 6, "edge_limit": 6},
                timeout_seconds=90,
            )
            graph_cooccurrence = await call_json(
                "aoa_session_graph_cooccurrence",
                {"anchor": "aoa-session-memory-mcp", "kind": "mcp_service", "limit": 6},
                timeout_seconds=90,
            )
            retrieve_usage = await call_json(
                "aoa_session_retrieve",
                {"recipe": "entity_usage", "query": "aoa-session-memory-mcp", "limit": 2, "event_limit": 2},
                timeout_seconds=90,
            )
            live_scenario = await call_json(
                "aoa_session_live_scenario_audit",
                {
                    "seed": "validator-stdio-smoke",
                    "profiles": ["entity_registry_lookup"],
                    "sample_size": 5,
                    "recent_days": 7,
                    "limit": 5,
                },
                timeout_seconds=90,
            )
            live_scenario_corpus = await call_json(
                "aoa_session_live_scenario_corpus_check",
                {"case_limit": 1},
                timeout_seconds=90,
            )
            live_scenario_corpus_inventory = await call_json(
                "aoa_session_live_scenario_corpus_inventory",
                {},
                timeout_seconds=90,
            )
            projection_status = await call_json(
                "aoa_session_projection_status",
                {},
                timeout_seconds=60,
                require_ok=False,
            )
            direct_event_rollup_query = await call_json(
                "aoa_session_direct_event_rollup_query",
                {"usage_role": "result", "limit": 3, "ref_limit": 3},
                timeout_seconds=60,
            )
            maintenance_status = {
                "artifact_type": "session_memory_maintenance_status",
                "mutates": False,
                "recommendation": "not_called_in_stdio_smoke",
                "mcp_access": {
                    "skipped_in_stdio_smoke": True,
                    "reason": (
                        "The validator checks aoa_session_maintenance_status through the direct source route; "
                        "fresh stdio smoke verifies tool registration without running the heavy maintenance route."
                    ),
                },
            }

    if inventory.get("entity_count", 0) <= 0:
        raise SystemExit(f"stdio MCP entity inventory returned no entities: {inventory.get('diagnostics')}")
    _assert_bounded_inventory_packet(inventory, "stdio MCP skill")
    first_inventory_entity = _first_entity(inventory)
    if not first_inventory_entity.get("latest_session_date"):
        raise SystemExit(f"stdio MCP entity inventory did not report latest_session_date: {inventory}")
    if _runtime_reload_required(inventory) is not False:
        raise SystemExit(f"stdio MCP entity inventory runtime freshness failed: {inventory.get('runtime')}")
    if mcp_service_inventory.get("requested_layer") != "mcp_service" or mcp_service_inventory.get("normalized_layer") != "mcp":
        raise SystemExit(f"stdio MCP mcp_service inventory alias contract failed: {mcp_service_inventory}")
    _assert_bounded_inventory_packet(mcp_service_inventory, "stdio MCP mcp_service")
    for layer_name, layer_inventory in (
        ("hook", hook_inventory),
        ("tool", tool_inventory),
        ("api", api_inventory),
    ):
        if not layer_inventory.get("ok"):
            raise SystemExit(f"stdio MCP {layer_name} inventory returned not-ok payload: {layer_inventory.get('diagnostics')}")
        _assert_bounded_inventory_packet(layer_inventory, f"stdio MCP {layer_name}")
    if not open_threads.get("ok", True):
        raise SystemExit(f"stdio MCP open-thread search returned not-ok payload: {open_threads.get('diagnostics')}")
    first_mcp_inventory_entity = _first_entity(mcp_service_inventory)
    if not first_mcp_inventory_entity.get("latest_session_date"):
        raise SystemExit(f"stdio MCP mcp_service inventory did not report latest_session_date: {mcp_service_inventory}")
    if _runtime_reload_required(mcp_service_inventory) is not False:
        raise SystemExit(f"stdio MCP mcp_service inventory runtime freshness failed: {mcp_service_inventory.get('runtime')}")
    unsupported_alias_diagnostics = [
        item
        for item in search_alias.get("diagnostics", [])
        if "unsupported filter 'layer'" in str(item) or "unsupported filter 'use_shards'" in str(item)
    ]
    if unsupported_alias_diagnostics:
        raise SystemExit(f"stdio MCP search alias contract failed: {unsupported_alias_diagnostics}")
    if registry.get("entity_count", 0) <= 0:
        raise SystemExit(f"stdio MCP entity registry returned no entities: {registry.get('diagnostics')}")
    if literal_plan.get("artifact_type") != "session_memory_literal_query_plan":
        raise SystemExit(f"stdio MCP literal query plan returned invalid payload: {literal_plan.get('diagnostics')}")
    if literal_plan.get("kind") != "mcp" or literal_plan.get("requested_kind") != "mcp_service":
        raise SystemExit(f"stdio MCP literal query kind alias contract failed: {literal_plan}")
    if literal_plan.get("primary_route", {}).get("route_id") != "entity_usage_chain":
        raise SystemExit(f"stdio MCP literal query plan did not choose entity usage chain first: {literal_plan}")
    if usage_chain.get("artifact_type") != "session_memory_entity_usage_chain":
        raise SystemExit(f"stdio MCP usage-chain returned invalid payload: {usage_chain.get('diagnostics')}")
    if usage_chain.get("kind") != "mcp" or usage_chain.get("requested_kind") != "mcp_service":
        raise SystemExit(f"stdio MCP usage-chain kind alias contract failed: {usage_chain}")
    usage_chain_counts = usage_chain.get("counts") if isinstance(usage_chain.get("counts"), dict) else {}
    usage_chain_quality = usage_chain.get("quality") if isinstance(usage_chain.get("quality"), dict) else {}
    usage_chain_first_ref = usage_chain.get("first_ref") if isinstance(usage_chain.get("first_ref"), dict) else {}
    if usage_chain_counts.get("usage_event_count", 0) <= 0 or usage_chain_quality.get("raw_or_segment_ref_present") is not True:
        raise SystemExit(f"stdio MCP usage-chain quality contract failed: {usage_chain}")
    if not _has_first_raw_or_segment_ref(usage_chain_first_ref):
        raise SystemExit(f"stdio MCP usage-chain first_ref contract failed: {usage_chain}")
    if usage_alias.get("kind") != "mcp" or usage_alias.get("requested_kind") != "mcp_service":
        raise SystemExit(f"stdio MCP usage kind alias contract failed: {usage_alias.get('diagnostics')}")
    if entity_dossier.get("artifact_type") != "session_memory_entity_dossier":
        raise SystemExit(f"stdio MCP entity dossier returned invalid payload: {entity_dossier.get('diagnostics')}")
    if entity_dossier.get("kind") != "mcp" or entity_dossier.get("requested_kind") != "mcp_service":
        raise SystemExit(f"stdio MCP entity dossier kind alias contract failed: {entity_dossier}")
    dossier_quality = entity_dossier.get("quality") if isinstance(entity_dossier.get("quality"), dict) else {}
    if dossier_quality.get("usage_event_count", 0) <= 0 or dossier_quality.get("raw_or_segment_ref_present") is not True:
        raise SystemExit(f"stdio MCP entity dossier quality contract failed: {entity_dossier}")
    if agent_event_usage.get("kind") != "agent_event" or agent_event_usage.get("outcome_event_count", 0) <= 0:
        raise SystemExit(f"stdio MCP agent_event usage route failed: {agent_event_usage.get('diagnostics')}")
    if graph_neighborhood.get("artifact_type") != "session_memory_graph_neighborhood" or graph_neighborhood.get("ok") is not True:
        raise SystemExit(f"stdio MCP graph neighborhood returned invalid payload: {graph_neighborhood.get('diagnostics')}")
    if graph_cooccurrence.get("artifact_type") != "session_memory_graph_cooccurrence" or graph_cooccurrence.get("ok") is not True:
        raise SystemExit(f"stdio MCP graph cooccurrence returned invalid payload: {graph_cooccurrence.get('diagnostics')}")
    cooccurrences = graph_cooccurrence.get("cooccurrences") if isinstance(graph_cooccurrence.get("cooccurrences"), list) else []
    evidence_refs = graph_cooccurrence.get("evidence_refs") if isinstance(graph_cooccurrence.get("evidence_refs"), list) else []
    if not cooccurrences or not evidence_refs:
        raise SystemExit(f"stdio MCP graph cooccurrence returned no cooccurrences or refs: {graph_cooccurrence}")
    if retrieve_usage.get("retrieval_redirect", {}).get("served_by") != "aoa_session_entity_usage_chain":
        raise SystemExit(f"stdio MCP retrieve entity_usage redirect failed: {retrieve_usage.get('diagnostics')}")
    if live_scenario.get("artifact_type") != "session_memory_live_scenario_audit":
        raise SystemExit(f"stdio MCP live scenario audit returned invalid payload: {live_scenario.get('diagnostics')}")
    if live_scenario.get("quality", {}).get("scenario_count") != 1:
        raise SystemExit(f"stdio MCP live scenario audit did not run the requested bounded profile: {live_scenario}")
    live_scenario_scenarios = live_scenario.get("scenarios") if isinstance(live_scenario.get("scenarios"), list) else []
    live_scenario_registry = live_scenario_scenarios[0] if live_scenario_scenarios and isinstance(live_scenario_scenarios[0], dict) else {}
    if live_scenario_registry.get("profile") != "entity_registry_lookup":
        raise SystemExit(f"stdio MCP live scenario audit did not run entity_registry_lookup: {live_scenario}")
    for key in (
        "active_lookup_count",
        "observed_lookup_count",
        "unknown_lookup_count",
        "stale_lookup_count",
        "removed_lookup_count",
    ):
        if live_scenario_registry.get(key, 0) <= 0:
            raise SystemExit(f"stdio MCP entity-registry live scenario missing {key}: {live_scenario_registry}")
    if live_scenario_registry.get("transition_probe_count", 0) < 2:
        raise SystemExit(f"stdio MCP entity-registry live scenario did not prove stale/removed transition probes: {live_scenario_registry}")
    if live_scenario_corpus.get("artifact_type") != "session_memory_live_scenario_regression_check":
        raise SystemExit(f"stdio MCP live scenario corpus returned invalid payload: {live_scenario_corpus.get('diagnostics')}")
    if live_scenario_corpus.get("case_count") != 1:
        raise SystemExit(f"stdio MCP live scenario corpus did not honor case_limit=1: {live_scenario_corpus}")
    if (
        live_scenario_corpus_inventory.get("artifact_type")
        != "session_memory_live_scenario_regression_corpus_inventory"
    ):
        raise SystemExit(
            "stdio MCP live scenario corpus inventory returned invalid payload: "
            f"{live_scenario_corpus_inventory.get('diagnostics')}"
        )
    if live_scenario_corpus_inventory.get("case_count", 0) <= 0:
        raise SystemExit(f"stdio MCP live scenario corpus inventory returned no cases: {live_scenario_corpus_inventory}")
    if (
        live_scenario_corpus_inventory.get("truth_status")
        != "source_corpus_inventory_not_live_route_proof"
    ):
        raise SystemExit(
            "stdio MCP live scenario corpus inventory blurred truth status: "
            f"{live_scenario_corpus_inventory.get('truth_status')}"
        )
    direct_event_quality = (
        direct_event_rollup_query.get("quality")
        if isinstance(direct_event_rollup_query.get("quality"), dict)
        else {}
    )
    direct_event_cost = (
        direct_event_rollup_query.get("cost_profile")
        if isinstance(direct_event_rollup_query.get("cost_profile"), dict)
        else {}
    )
    direct_event_mcp_access = (
        direct_event_rollup_query.get("mcp_access")
        if isinstance(direct_event_rollup_query.get("mcp_access"), dict)
        else {}
    )
    if direct_event_rollup_query.get("artifact_type") != "session_memory_search_operational_direct_event_rollup_query":
        raise SystemExit(f"stdio MCP direct-event rollup query returned invalid payload: {direct_event_rollup_query.get('diagnostics')}")
    if direct_event_rollup_query.get("result_count", 0) <= 0 or direct_event_quality.get("raw_or_segment_ref_present") is not True:
        raise SystemExit(f"stdio MCP direct-event rollup query returned no usable refs: {direct_event_rollup_query}")
    if direct_event_cost.get("uses_materialized_direct_event_rollup") is not True:
        raise SystemExit(f"stdio MCP direct-event rollup query did not use materialized projection: {direct_event_cost}")
    for key in ("resamples_shards", "opens_monolith", "uses_fts", "hydrates_body"):
        if direct_event_cost.get(key) is not False:
            raise SystemExit(f"stdio MCP direct-event rollup query violated cost contract {key}: {direct_event_cost}")
    if direct_event_mcp_access.get("does_not_resample_shards") is not True or direct_event_mcp_access.get("behavior_proof_route") != "usage-chain":
        raise SystemExit(f"stdio MCP direct-event rollup access boundary failed: {direct_event_mcp_access}")
    if maintenance_status.get("artifact_type") != "session_memory_maintenance_status" or maintenance_status.get("mutates") is not False:
        raise SystemExit(f"stdio MCP maintenance status returned invalid payload: {maintenance_status.get('diagnostics')}")
    if projection_status.get("schema") != "aoa_session_memory_projection_status_v1" or projection_status.get("mutates") is not False:
        raise SystemExit(f"stdio MCP projection status returned invalid payload: {projection_status.get('diagnostics')}")
    if projection_status.get("mcp_access", {}).get("does_not_run_projection_catchup") is not True:
        raise SystemExit(f"stdio MCP projection status violated read-only catchup boundary: {projection_status.get('mcp_access')}")
    summary = _stdio_route_count_summary(
        inventory,
        mcp_service_inventory,
        hook_inventory,
        tool_inventory,
        api_inventory,
        open_threads,
        search_alias,
        responses,
        closeouts,
        progress,
        reasoning,
        episodes,
        goal_lifecycles,
        neighborhood,
        registry,
        literal_plan,
        entity_dossier,
        usage_chain,
        usage_alias,
        agent_event_usage,
        graph_neighborhood,
        graph_cooccurrence,
        retrieve_usage,
        live_scenario,
        live_scenario_corpus,
        live_scenario_corpus_inventory,
        maintenance_status,
        direct_event_rollup_query,
        projection_status,
        tool_count=len(tools),
    )
    summary["tool_annotation_contract"] = tool_annotation_contract
    return summary


async def _configured_transport_response_timeout_policy(response) -> None:
    request = response.request
    content_type = response.headers.get("content-type", "").lower()
    if request.method == "GET" and response.status_code == 200 and content_type.startswith("text/event-stream"):
        timeout = request.extensions.get("timeout")
        if isinstance(timeout, dict):
            timeout["read"] = None


def _configured_transport_http_client(bearer_token: str, *, transport=None):
    import httpx

    # The configured smoke keeps one GET stream open while tool calls have
    # explicit 20-90 second ClientSession budgets. Keep ordinary HTTP response
    # reads and the SSE handshake bounded beyond the largest call budget, then
    # remove the read deadline only after a successful SSE GET response.
    kwargs = {
        "headers": {"Authorization": f"Bearer {bearer_token}"},
        "follow_redirects": True,
        "timeout": httpx.Timeout(
            CONFIGURED_HTTP_RESPONSE_TIMEOUT_SECONDS,
            connect=CONFIGURED_HTTP_TIMEOUT_SECONDS,
            write=CONFIGURED_HTTP_TIMEOUT_SECONDS,
            pool=CONFIGURED_HTTP_TIMEOUT_SECONDS,
        ),
        "event_hooks": {"response": [_configured_transport_response_timeout_policy]},
    }
    if transport is not None:
        kwargs["transport"] = transport
    return httpx.AsyncClient(
        **kwargs,
    )


async def _configured_transport_smoke(state: AoASessionMemoryMCPState) -> dict:
    transport_spec, meta = _configured_transport_spec(state)
    if transport_spec is None:
        return {**meta, "ok": True, "skipped": True}

    async with AsyncExitStack() as stack:
        if transport_spec["transport"] == "streamable-http":
            bearer_token_env_var = str(transport_spec["bearer_token_env_var"])
            bearer_token = os.environ.get(bearer_token_env_var)
            if not bearer_token:
                raise SystemExit("configured Codex MCP bearer credential became unavailable during smoke")
            http_client = await stack.enter_async_context(
                _configured_transport_http_client(bearer_token)
            )
            read_stream, write_stream, _ = await stack.enter_async_context(
                streamable_http_client(
                    str(transport_spec["url"]),
                    http_client=http_client,
                )
            )
        else:
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(transport_spec["params"])
            )
        async with ClientSession(read_stream, write_stream) as mcp_session:
            await mcp_session.initialize()
            listed_tools = (await mcp_session.list_tools()).tools
            tool_annotation_contract = _read_only_tool_annotation_summary(listed_tools, "configured Codex")
            tools = {tool.name for tool in listed_tools}
            missing_tools = sorted(REQUIRED_STDIO_SMOKE_TOOLS - tools)
            if missing_tools:
                raise SystemExit(f"configured Codex MCP tool list is missing required tools: {missing_tools}")

            result = await mcp_session.call_tool(
                "aoa_session_memory_status",
                {"include_live": False},
                read_timeout_seconds=timedelta(seconds=60),
            )
            if result.isError:
                raise SystemExit(f"configured Codex MCP status call failed: {result.content}")
            if not result.content:
                raise SystemExit("configured Codex MCP status call returned no content")
            payload = json.loads(result.content[0].text)
            if not isinstance(payload, dict) or not payload.get("ok"):
                raise SystemExit(f"configured Codex MCP status returned not-ok payload: {payload}")

            search_result = await mcp_session.call_tool(
                "aoa_session_search",
                _search_alias_smoke_arguments(limit=2),
                read_timeout_seconds=timedelta(seconds=60),
            )
            if search_result.isError or not search_result.content:
                raise SystemExit(f"configured Codex MCP search alias call failed: {search_result.content}")
            search_payload = json.loads(search_result.content[0].text)
            search_diagnostics = search_payload.get("diagnostics", []) if isinstance(search_payload, dict) else []
            unsupported_search_filters = [
                item
                for item in search_diagnostics
                if "unsupported filter 'layer'" in str(item) or "unsupported filter 'use_shards'" in str(item)
            ]
            if unsupported_search_filters:
                raise SystemExit(f"configured Codex MCP search alias contract failed: {unsupported_search_filters}")

            literal_plan_result = await mcp_session.call_tool(
                "aoa_session_literal_query_plan",
                {
                    "query": "aoa-session-memory-mcp",
                    "kind": "mcp_service",
                    "filters": {"doc_type": "event", "route_layer": "mcp", "max_shards": 3},
                },
                read_timeout_seconds=timedelta(seconds=60),
            )
            if literal_plan_result.isError or not literal_plan_result.content:
                raise SystemExit(f"configured Codex MCP literal query plan call failed: {literal_plan_result.content}")
            literal_plan_payload = json.loads(literal_plan_result.content[0].text)
            if (
                not isinstance(literal_plan_payload, dict)
                or literal_plan_payload.get("kind") != "mcp"
                or literal_plan_payload.get("requested_kind") != "mcp_service"
                or literal_plan_payload.get("primary_route", {}).get("route_id") != "entity_usage_chain"
            ):
                raise SystemExit(f"configured Codex MCP literal query plan contract failed: {literal_plan_payload}")

            usage_chain_result = await mcp_session.call_tool(
                "aoa_session_entity_usage_chain",
                {"anchor": "aoa-session-memory-mcp", "kind": "mcp_service", "limit": 2, "per_route_limit": 3},
                read_timeout_seconds=timedelta(seconds=90),
            )
            if usage_chain_result.isError or not usage_chain_result.content:
                raise SystemExit(f"configured Codex MCP usage-chain call failed: {usage_chain_result.content}")
            usage_chain_payload = json.loads(usage_chain_result.content[0].text)
            usage_chain_counts = usage_chain_payload.get("counts") if isinstance(usage_chain_payload, dict) and isinstance(usage_chain_payload.get("counts"), dict) else {}
            usage_chain_first_ref = usage_chain_payload.get("first_ref") if isinstance(usage_chain_payload, dict) and isinstance(usage_chain_payload.get("first_ref"), dict) else {}
            if (
                not isinstance(usage_chain_payload, dict)
                or usage_chain_payload.get("artifact_type") != "session_memory_entity_usage_chain"
                or usage_chain_payload.get("kind") != "mcp"
                or usage_chain_payload.get("requested_kind") != "mcp_service"
                or usage_chain_counts.get("usage_event_count", 0) <= 0
                or not _has_first_raw_or_segment_ref(usage_chain_first_ref)
            ):
                raise SystemExit(f"configured Codex MCP usage-chain contract failed: {usage_chain_payload}")

            inventory_result = await mcp_session.call_tool(
                "aoa_session_entity_inventory",
                {"layer": "mcp_service", "query": "aoa-session-memory", "limit": 3, "sample_limit": 3},
                read_timeout_seconds=timedelta(seconds=20),
            )
            if inventory_result.isError or not inventory_result.content:
                raise SystemExit(f"configured Codex MCP mcp_service inventory call failed: {inventory_result.content}")
            inventory_payload = json.loads(inventory_result.content[0].text)
            if (
                not isinstance(inventory_payload, dict)
                or inventory_payload.get("requested_layer") != "mcp_service"
                or inventory_payload.get("normalized_layer") != "mcp"
            ):
                raise SystemExit(f"configured Codex MCP mcp_service inventory alias contract failed: {inventory_payload}")
            configured_inventory_entity = _first_entity(inventory_payload)
            if not configured_inventory_entity.get("latest_session_date"):
                raise SystemExit(f"configured Codex MCP mcp_service inventory did not report latest_session_date: {inventory_payload}")
            if _runtime_reload_required(inventory_payload) is not False:
                raise SystemExit(f"configured Codex MCP inventory runtime freshness failed: {inventory_payload.get('runtime')}")
            _assert_bounded_inventory_packet(inventory_payload, "configured Codex MCP mcp_service")

            usage_result = await mcp_session.call_tool(
                "aoa_session_entity_usage_audit",
                {"anchor": "aoa-session-memory-mcp", "kind": "mcp_service", "limit": 2, "per_route_limit": 2},
                read_timeout_seconds=timedelta(seconds=90),
            )
            if usage_result.isError or not usage_result.content:
                raise SystemExit(f"configured Codex MCP usage alias call failed: {usage_result.content}")
            usage_payload = json.loads(usage_result.content[0].text)
            if (
                not isinstance(usage_payload, dict)
                or usage_payload.get("kind") != "mcp"
                or usage_payload.get("requested_kind") != "mcp_service"
            ):
                raise SystemExit(f"configured Codex MCP usage kind alias contract failed: {usage_payload}")

            dossier_result = await mcp_session.call_tool(
                "aoa_session_entity_dossier",
                {
                    "anchor": "aoa-session-memory-mcp",
                    "kind": "mcp_service",
                    "usage_limit": 2,
                    "neighborhood_limit": 1,
                    "graph_limit": 6,
                    "graph_edge_limit": 6,
                },
                read_timeout_seconds=timedelta(seconds=90),
            )
            if dossier_result.isError or not dossier_result.content:
                raise SystemExit(f"configured Codex MCP entity dossier call failed: {dossier_result.content}")
            dossier_payload = json.loads(dossier_result.content[0].text)
            dossier_quality = dossier_payload.get("quality") if isinstance(dossier_payload, dict) else {}
            if (
                not isinstance(dossier_payload, dict)
                or dossier_payload.get("artifact_type") != "session_memory_entity_dossier"
                or dossier_payload.get("kind") != "mcp"
                or dossier_payload.get("requested_kind") != "mcp_service"
                or dossier_quality.get("usage_event_count", 0) <= 0
                or dossier_quality.get("raw_or_segment_ref_present") is not True
            ):
                raise SystemExit(f"configured Codex MCP entity dossier contract failed: {dossier_payload}")

            agent_event_usage_result = await mcp_session.call_tool(
                "aoa_session_entity_usage_audit",
                {"anchor": "assistant_answer", "kind": "agent_event", "limit": 3, "per_route_limit": 5},
                read_timeout_seconds=timedelta(seconds=90),
            )
            if agent_event_usage_result.isError or not agent_event_usage_result.content:
                raise SystemExit(f"configured Codex MCP agent_event usage call failed: {agent_event_usage_result.content}")
            agent_event_usage_payload = json.loads(agent_event_usage_result.content[0].text)
            if (
                not isinstance(agent_event_usage_payload, dict)
                or agent_event_usage_payload.get("kind") != "agent_event"
                or agent_event_usage_payload.get("outcome_event_count", 0) <= 0
            ):
                raise SystemExit(f"configured Codex MCP agent_event usage contract failed: {agent_event_usage_payload}")

            retrieve_result = await mcp_session.call_tool(
                "aoa_session_retrieve",
                {"recipe": "entity_usage", "query": "aoa-session-memory-mcp", "limit": 2, "event_limit": 2},
                read_timeout_seconds=timedelta(seconds=90),
            )
            if retrieve_result.isError or not retrieve_result.content:
                raise SystemExit(f"configured Codex MCP retrieve entity_usage call failed: {retrieve_result.content}")
            retrieve_payload = json.loads(retrieve_result.content[0].text)
            if (
                not isinstance(retrieve_payload, dict)
                or retrieve_payload.get("retrieval_redirect", {}).get("served_by") != "aoa_session_entity_usage_chain"
            ):
                raise SystemExit(f"configured Codex MCP retrieve entity_usage redirect failed: {retrieve_payload}")

            projection_result = await mcp_session.call_tool(
                "aoa_session_projection_status",
                {},
                read_timeout_seconds=timedelta(seconds=60),
            )
            if projection_result.isError or not projection_result.content:
                raise SystemExit(f"configured Codex MCP projection status call failed: {projection_result.content}")
            projection_payload = json.loads(projection_result.content[0].text)
            if (
                not isinstance(projection_payload, dict)
                or projection_payload.get("schema") != "aoa_session_memory_projection_status_v1"
                or projection_payload.get("mcp_access", {}).get("does_not_run_projection_catchup") is not True
            ):
                raise SystemExit(f"configured Codex MCP projection status contract failed: {projection_payload}")

    return {
        **meta,
        "ok": True,
        "skipped": False,
        "tool_count": len(tools),
        "tool_annotation_contract": tool_annotation_contract,
        "status_ok": payload.get("ok"),
        "search_alias_result_count": search_payload.get("result_count") if isinstance(search_payload, dict) else None,
        "literal_plan_primary_route": literal_plan_payload.get("primary_route", {}).get("route_id")
        if isinstance(literal_plan_payload, dict) and isinstance(literal_plan_payload.get("primary_route"), dict)
        else None,
        "literal_plan_structured_first": literal_plan_payload.get("cost_profile", {}).get("structured_first")
        if isinstance(literal_plan_payload, dict) and isinstance(literal_plan_payload.get("cost_profile"), dict)
        else None,
        "usage_chain_usage_count": usage_chain_counts.get("usage_event_count")
        if isinstance(usage_chain_counts, dict)
        else None,
        "usage_chain_first_ref_present": _has_first_raw_or_segment_ref(usage_chain_first_ref),
        "mcp_service_inventory_requested_layer": inventory_payload.get("requested_layer")
        if isinstance(inventory_payload, dict)
        else None,
        "mcp_service_inventory_latest_session_date": configured_inventory_entity.get("latest_session_date"),
        "mcp_service_inventory_runtime_reload_required": _runtime_reload_required(inventory_payload),
        "mcp_service_inventory_sample_count": inventory_payload.get("response_profile", {}).get("sample_count")
        if isinstance(inventory_payload.get("response_profile"), dict)
        else None,
        "usage_alias_kind": usage_payload.get("kind") if isinstance(usage_payload, dict) else None,
        "entity_dossier_usage_count": dossier_quality.get("usage_event_count"),
        "entity_dossier_graph_node_count": dossier_quality.get("graph_node_count"),
        "entity_dossier_raw_or_segment_ref_present": dossier_quality.get("raw_or_segment_ref_present"),
        "agent_event_usage_kind": agent_event_usage_payload.get("kind") if isinstance(agent_event_usage_payload, dict) else None,
        "agent_event_usage_outcome_count": agent_event_usage_payload.get("outcome_event_count") if isinstance(agent_event_usage_payload, dict) else None,
        "retrieve_usage_served_by": retrieve_payload.get("retrieval_redirect", {}).get("served_by")
        if isinstance(retrieve_payload, dict) and isinstance(retrieve_payload.get("retrieval_redirect"), dict)
        else None,
        "projection_status_ok": projection_payload.get("ok") if isinstance(projection_payload, dict) else None,
        "projection_completeness_status": projection_payload.get("projection_completeness", {}).get("status")
        if isinstance(projection_payload, dict) and isinstance(projection_payload.get("projection_completeness"), dict)
        else None,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the aoa-session-memory MCP service with live archive, "
            "portable stdio, and configured Codex MCP transport smoke checks."
        )
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    parse_args(argv)

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
    search = state.session_search("", filters={"route_signal": "mcp:aoa_session_memory_mcp", "doc_type": "session"}, limit=3)
    if search.get("result_count", 0) <= 0:
        raise SystemExit("session search returned no smoke hits")
    route_only = state.session_search("", filters={"route_signal": "tool:view_image", "doc_type": "event"}, limit=3)
    if route_only.get("result_count", 0) <= 0:
        raise SystemExit("route-only session search returned no smoke hits")
    skill_inventory = state.session_entity_inventory(layer="skill", limit=5)
    if not skill_inventory.get("ok") or skill_inventory.get("entity_count", 0) <= 0:
        raise SystemExit(f"skill entity inventory failed: {skill_inventory.get('diagnostics')}")
    skill_registry = state.session_entity_registry(kind="skill", limit=5)
    if not skill_registry.get("ok") or skill_registry.get("entity_count", 0) <= 0:
        raise SystemExit(f"skill entity registry failed: {skill_registry.get('diagnostics')}")
    git_inventory = state.session_entity_inventory(layer="git", limit=5)
    if not git_inventory.get("ok") or git_inventory.get("entity_count", 0) <= 0:
        raise SystemExit(f"git entity inventory failed: {git_inventory.get('diagnostics')}")
    hook_receipts = state.session_hook_receipts(event_name="UserPromptSubmit", limit=5)
    if not hook_receipts.get("ok"):
        raise SystemExit(f"hook receipts surface failed: {hook_receipts.get('diagnostics')}")
    maintenance_status = state.session_maintenance_status(include_timers=False)
    if (
        maintenance_status.get("artifact_type") != "session_memory_maintenance_status"
        or maintenance_status.get("mutates") is not False
        or not isinstance(maintenance_status.get("agent_route"), dict)
    ):
        raise SystemExit(f"maintenance status surface failed: {maintenance_status.get('diagnostics')}")
    projection_status = state.session_projection_status()
    if (
        projection_status.get("schema") != "aoa_session_memory_projection_status_v1"
        or projection_status.get("mutates") is not False
        or projection_status.get("mcp_access", {}).get("does_not_run_projection_catchup") is not True
    ):
        raise SystemExit(f"projection status surface failed: {projection_status.get('diagnostics')}")
    goal_usage_probe = state.session_goal_lifecycles(event_kind="goal_completed", limit=1)
    if not goal_usage_probe.get("ok") or goal_usage_probe.get("result_count", 0) <= 0:
        raise SystemExit(f"goal usage probe returned no completed goal lifecycle: {goal_usage_probe.get('diagnostics')}")
    usage_anchor, usage_session, neighborhood = _select_usage_neighborhood_probe(state, route_only, goal_usage_probe)
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
    goal_lifecycles = state.session_goal_lifecycles(session=latest_session, limit=3)
    if not goal_lifecycles.get("ok") or goal_lifecycles.get("artifact_type") != "goal_lifecycle_route_results":
        raise SystemExit(f"goal lifecycle surface failed: {goal_lifecycles.get('diagnostics')}")
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
    if not freshness.get("ok") or freshness_status not in ACCEPTABLE_FRESHNESS_SMOKE_STATUSES:
        raise SystemExit(f"freshness smoke is not current: {freshness_status}")
    server = build_server()
    if server is None:
        raise SystemExit("MCP server did not build")
    stdio_smoke = asyncio.run(_stdio_tool_smoke(state, latest_session))
    configured_transport_smoke = asyncio.run(_configured_transport_smoke(state))
    transport_preflight = state.session_mcp_transport_preflight()
    running_processes = transport_preflight.get("running_mcp_processes", {})
    codex_session = transport_preflight.get("codex_session", {})

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
                "goal_lifecycle_result_count": goal_lifecycles.get("result_count"),
                "hook_receipt_count": hook_receipts.get("total_receipt_count"),
                "hook_receipt_error_count": hook_receipts.get("summary", {}).get("error_receipt_count"),
                "maintenance_recommendation": maintenance_status.get("recommendation"),
                "maintenance_agent_action": maintenance_status.get("agent_route", {}).get("action"),
                "projection_status_ok": projection_status.get("ok"),
                "projection_completeness_status": projection_status.get("projection_completeness", {}).get("status")
                if isinstance(projection_status.get("projection_completeness"), dict)
                else None,
                "goal_usage_probe_count": goal_usage_probe.get("result_count"),
                "usage_neighborhood_anchor": usage_anchor,
                "usage_neighborhood_session": usage_session,
                "usage_neighborhood_count": neighborhood.get("quality", {}).get("neighborhood_count"),
                "latest_session": latest_brief.get("session", {}).get("label") or "latest",
                "freshness_smoke_session": latest_session,
                "freshness_ok": freshness.get("ok"),
                "freshness_projection": freshness.get("projection_freshness", {}).get("status"),
                "raw_line_freshness_checked": raw_checked,
                "stdio_tool_count": stdio_smoke["tool_count"],
                "stdio_tool_annotation_contract": stdio_smoke["tool_annotation_contract"],
                "stdio_inventory_entity_count": stdio_smoke["inventory_entity_count"],
                "stdio_inventory_source": stdio_smoke["inventory_source"],
                "stdio_inventory_latest_session_date": stdio_smoke["inventory_latest_session_date"],
                "stdio_inventory_runtime_reload_required": stdio_smoke["inventory_runtime_reload_required"],
                "stdio_inventory_sample_count": stdio_smoke["inventory_sample_count"],
                "stdio_inventory_sample_omitted_count": stdio_smoke["inventory_sample_omitted_count"],
                "stdio_mcp_service_inventory_layer": stdio_smoke["mcp_service_inventory_layer"],
                "stdio_mcp_service_inventory_requested_layer": stdio_smoke["mcp_service_inventory_requested_layer"],
                "stdio_mcp_service_inventory_latest_session_date": stdio_smoke[
                    "mcp_service_inventory_latest_session_date"
                ],
                "stdio_mcp_service_inventory_runtime_reload_required": stdio_smoke[
                    "mcp_service_inventory_runtime_reload_required"
                ],
                "stdio_mcp_service_inventory_sample_count": stdio_smoke["mcp_service_inventory_sample_count"],
                "stdio_hook_inventory_entity_count": stdio_smoke["hook_inventory_entity_count"],
                "stdio_tool_inventory_entity_count": stdio_smoke["tool_inventory_entity_count"],
                "stdio_api_inventory_entity_count": stdio_smoke["api_inventory_entity_count"],
                "stdio_open_thread_result_count": stdio_smoke["open_thread_result_count"],
                "stdio_search_alias_result_count": stdio_smoke["search_alias_result_count"],
                "stdio_search_alias_projection_mode": stdio_smoke["search_alias_projection_mode"],
                "stdio_agent_response_count": stdio_smoke["agent_response_count"],
                "stdio_agent_closeout_count": stdio_smoke["agent_closeout_count"],
                "stdio_agent_progress_count": stdio_smoke["agent_progress_count"],
                "stdio_agent_reasoning_window_count": stdio_smoke["agent_reasoning_window_count"],
                "stdio_task_episode_count": stdio_smoke["task_episode_count"],
                "stdio_goal_lifecycle_count": stdio_smoke["goal_lifecycle_count"],
                "stdio_answer_neighborhood_count": stdio_smoke["answer_neighborhood_count"],
                "stdio_literal_plan_primary_route": stdio_smoke["literal_plan_primary_route"],
                "stdio_literal_plan_structured_first": stdio_smoke["literal_plan_structured_first"],
                "stdio_entity_dossier_usage_count": stdio_smoke["entity_dossier_usage_count"],
                "stdio_entity_dossier_graph_node_count": stdio_smoke["entity_dossier_graph_node_count"],
                "stdio_entity_dossier_raw_or_segment_ref_present": stdio_smoke["entity_dossier_raw_or_segment_ref_present"],
                "stdio_usage_alias_kind": stdio_smoke["usage_alias_kind"],
                "stdio_usage_alias_requested_kind": stdio_smoke["usage_alias_requested_kind"],
                "stdio_agent_event_usage_kind": stdio_smoke["agent_event_usage_kind"],
                "stdio_agent_event_usage_outcome_count": stdio_smoke["agent_event_usage_outcome_count"],
                "stdio_graph_neighborhood_node_count": stdio_smoke["graph_neighborhood_node_count"],
                "stdio_graph_neighborhood_edge_count": stdio_smoke["graph_neighborhood_edge_count"],
                "stdio_graph_cooccurrence_count": stdio_smoke["graph_cooccurrence_count"],
                "stdio_graph_cooccurrence_ref_count": stdio_smoke["graph_cooccurrence_ref_count"],
                "stdio_retrieve_usage_served_by": stdio_smoke["retrieve_usage_served_by"],
                "stdio_live_scenario_count": stdio_smoke["live_scenario_count"],
                "stdio_live_scenario_warn_count": stdio_smoke["live_scenario_warn_count"],
                "stdio_live_scenario_entity_registry_active_count": stdio_smoke[
                    "live_scenario_entity_registry_active_count"
                ],
                "stdio_live_scenario_entity_registry_observed_count": stdio_smoke[
                    "live_scenario_entity_registry_observed_count"
                ],
                "stdio_live_scenario_entity_registry_unknown_count": stdio_smoke[
                    "live_scenario_entity_registry_unknown_count"
                ],
                "stdio_live_scenario_entity_registry_stale_count": stdio_smoke[
                    "live_scenario_entity_registry_stale_count"
                ],
                "stdio_live_scenario_entity_registry_removed_count": stdio_smoke[
                    "live_scenario_entity_registry_removed_count"
                ],
                "stdio_live_scenario_entity_registry_transition_probe_count": stdio_smoke[
                    "live_scenario_entity_registry_transition_probe_count"
                ],
                "stdio_live_scenario_corpus_case_count": stdio_smoke["live_scenario_corpus_case_count"],
                "stdio_live_scenario_corpus_actionable_gap_count": stdio_smoke[
                    "live_scenario_corpus_actionable_gap_count"
                ],
                "stdio_live_scenario_corpus_inventory_case_count": stdio_smoke[
                    "live_scenario_corpus_inventory_case_count"
                ],
                "stdio_live_scenario_corpus_inventory_truth_status": stdio_smoke[
                    "live_scenario_corpus_inventory_truth_status"
                ],
                "stdio_direct_event_rollup_result_count": stdio_smoke["direct_event_rollup_result_count"],
                "stdio_direct_event_rollup_freshness_status": stdio_smoke[
                    "direct_event_rollup_freshness_status"
                ],
                "stdio_direct_event_rollup_materialized": stdio_smoke["direct_event_rollup_materialized"],
                "stdio_maintenance_smoke_skipped": stdio_smoke["maintenance_smoke_skipped"],
                "stdio_projection_status_ok": stdio_smoke["projection_status_ok"],
                "stdio_projection_completeness_status": stdio_smoke["projection_completeness_status"],
                "configured_transport": configured_transport_smoke,
                "transport_preflight_status": transport_preflight.get("direct_tool_transport_status"),
                "transport_preflight_ok": transport_preflight.get("ok"),
                "running_processes": running_processes,
                "codex_session": codex_session,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
