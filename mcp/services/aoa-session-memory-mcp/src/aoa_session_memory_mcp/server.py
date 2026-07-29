from __future__ import annotations

import json
import logging
import os
import importlib
from pathlib import Path
from typing import Any, Literal

from . import core as core_module
from ._http_auth import http_auth_kwargs as _http_auth_kwargs
from ._http_auth import transport_settings as _transport_settings


LOGGER = logging.getLogger(__name__)
PACKAGE_NAME = "aoa-session-memory-mcp"
APPLICATION_VERSION = "0.2.0"
DEFAULT_HTTP_PORT = 5422
READ_TOKEN_ENV_VAR = "AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN"
READ_CREDENTIAL_NAME = "aoa-session-memory-mcp-read-bearer-token"
READ_AUTH_SCOPE = "mcp:aoa-session-memory:read"
READ_CLIENT_ID = "aoa-loopback-codex:aoa-session-memory:read"


def _application_version() -> str:
    return APPLICATION_VERSION


def _bind_server_info_version(mcp: Any) -> None:
    low_level_server = getattr(mcp, "_mcp_server", None)
    if low_level_server is None or not hasattr(low_level_server, "version"):
        raise RuntimeError(
            "the pinned MCP SDK no longer exposes the server identity seam"
        )
    low_level_server.version = _application_version()


def _read_http_auth_kwargs() -> dict[str, Any]:
    return _http_auth_kwargs(
        DEFAULT_HTTP_PORT,
        token_env_var=READ_TOKEN_ENV_VAR,
        credential_name=READ_CREDENTIAL_NAME,
        auth_scope=READ_AUTH_SCOPE,
        client_id=READ_CLIENT_ID,
    )


def _run_server(server: Any) -> None:
    settings = _transport_settings(DEFAULT_HTTP_PORT)
    _read_http_auth_kwargs()
    if settings.transport == "stdio":
        server.run(transport="stdio")
        return
    assert settings.host is not None
    assert settings.port is not None
    server.settings.host = settings.host
    server.settings.port = settings.port
    server.run(transport="streamable-http")


def _core_auto_reload_enabled() -> bool:
    value = os.environ.get("AOA_SESSION_MEMORY_MCP_AUTO_RELOAD", "1").strip().casefold()
    return value not in {"0", "false", "no", "off"}


def _core_reload_required() -> bool:
    if not _core_auto_reload_enabled():
        return False
    current_sha256 = core_module._file_sha256(core_module.MCP_CORE_SOURCE_PATH)
    return bool(
        current_sha256
        and core_module.MCP_CORE_LOADED_SHA256
        and current_sha256 != core_module.MCP_CORE_LOADED_SHA256
    )


def _reload_core_if_changed() -> None:
    if not _core_reload_required():
        return
    LOGGER.warning(
        "Reloading aoa-session-memory MCP core implementation from %s",
        core_module.MCP_CORE_SOURCE_PATH,
    )
    importlib.reload(core_module)


def build_server(
    workspace_root: str | Path | None = None,
    aoa_root: str | Path | None = None,
    script_path: str | Path | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency 'mcp'. Install with: python -m pip install -e .") from exc

    mcp = FastMCP(
        "aoa-session-memory-mcp",
        json_response=True,
        **_read_http_auth_kwargs(),
    )
    _bind_server_info_version(mcp)
    read_only_tool = mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )

    def current_state() -> core_module.AoASessionMemoryMCPState:
        _reload_core_if_changed()
        return core_module.AoASessionMemoryMCPState.discover(
            workspace_root=workspace_root,
            aoa_root=aoa_root,
            script_path=script_path,
        )

    @read_only_tool
    def aoa_session_memory_status(include_live: bool = False) -> dict[str, Any]:
        """Report .aoa search, atlas, route-readiness, and freshness posture."""
        return current_state().session_memory_status(include_live=include_live)

    @read_only_tool
    def aoa_session_transport_preflight() -> dict[str, Any]:
        """Diagnose whether the current Codex process has a live aoa-session-memory MCP transport."""
        return current_state().session_mcp_transport_preflight()

    @read_only_tool
    def aoa_session_search(query: str = "", filters: dict[str, Any] | None = None, limit: int = 20) -> dict[str, Any]:
        """Search .aoa session evidence and return route refs plus freshness data."""
        return current_state().session_search(query=query, filters=filters, limit=limit)

    @read_only_tool
    def aoa_session_literal_query_plan(query: str = "", kind: str = "auto", filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Plan the cheapest reliable route for a literal skill/MCP/hook/tool/API/path/query before raw-text fallback."""
        return current_state().session_literal_query_plan(query=query, kind=kind, filters=filters)

    @read_only_tool
    def aoa_session_agent_responses(
        query: str = "",
        session: str = "",
        agent_events: list[str] | None = None,
        episode: str = "",
        closeout_final: bool = False,
        verification_state: str = "any",
        failure_state: str = "any",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Find assistant answer-like events by generated agent-event class with refs and freshness."""
        return current_state().session_agent_responses(
            query=query,
            session=session,
            agent_events=agent_events,
            episode=episode,
            closeout_final=closeout_final,
            verification_state=verification_state,
            failure_state=failure_state,
            limit=limit,
        )

    @read_only_tool
    def aoa_session_agent_closeouts(query: str = "", session: str = "", episode: str = "", limit: int = 20) -> dict[str, Any]:
        """Find assistant final closeout events separately from progress updates."""
        return current_state().session_agent_closeouts(query=query, session=session, episode=episode, limit=limit)

    @read_only_tool
    def aoa_session_agent_progress_updates(query: str = "", session: str = "", episode: str = "", limit: int = 20) -> dict[str, Any]:
        """Find assistant progress updates separately from final answers."""
        return current_state().session_agent_progress_updates(query=query, session=session, episode=episode, limit=limit)

    @read_only_tool
    def aoa_session_agent_reasoning_windows(
        query: str = "",
        session: str = "",
        episode: str = "",
        limit: int = 10,
        before: int = 3,
        after: int = 6,
        explain: bool = True,
    ) -> dict[str, Any]:
        """Find reasoning boundary events and bounded neighboring events."""
        return current_state().session_agent_reasoning_windows(
            query=query,
            session=session,
            episode=episode,
            limit=limit,
            before=before,
            after=after,
            explain=explain,
        )

    @read_only_tool
    def aoa_session_task_episodes(
        target: str = "all",
        session: str = "",
        episode: str = "",
        status: str = "",
        verification_state: str = "",
        failure_state: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        """List generated task episodes with start refs, event ranges, verification state, and failure state."""
        return current_state().session_task_episodes(
            target=target,
            session=session,
            episode=episode,
            status=status,
            verification_state=verification_state,
            failure_state=failure_state,
            limit=limit,
        )

    @read_only_tool
    def aoa_session_goal_lifecycles(
        target: str = "all",
        session: str = "",
        goal_id: str = "",
        status: str = "",
        event_kind: str = "",
        limit: int = 20,
        order: Literal["recent", "chronological"] = "recent",
    ) -> dict[str, Any]:
        """List generated Codex goal lifecycles with refs, task episodes, graph refs, and ambiguity flags."""
        return current_state().session_goal_lifecycles(
            target=target,
            session=session,
            goal_id=goal_id,
            status=status,
            event_kind=event_kind,
            limit=limit,
            order=order,
        )

    @read_only_tool
    def aoa_session_answer_neighborhood(
        query: str = "",
        session: str = "",
        agent_events: list[str] | None = None,
        episode: str = "",
        limit: int = 10,
        before: int = 3,
        after: int = 6,
        explain: bool = True,
    ) -> dict[str, Any]:
        """Find assistant answer-like events and return bounded neighboring events."""
        return current_state().session_answer_neighborhood(
            query=query,
            session=session,
            agent_events=agent_events,
            episode=episode,
            limit=limit,
            before=before,
            after=after,
            explain=explain,
        )

    @read_only_tool
    def aoa_session_trace(
        anchor: str,
        kind: str = "auto",
        limit: int = 20,
        per_route_limit: int = 10,
        session: str = "",
        doc_type: str = "session",
    ) -> dict[str, Any]:
        """Resolve an anchor into route candidates and evidence hits."""
        return current_state().session_trace(
            anchor=anchor,
            kind=kind,
            limit=limit,
            per_route_limit=per_route_limit,
            session=session,
            doc_type=doc_type,
        )

    @read_only_tool
    def aoa_session_entity_dossier(
        anchor: str,
        kind: str = "auto",
        session: str = "",
        usage_limit: int = 4,
        neighborhood_limit: int = 2,
        graph_limit: int = 12,
        graph_edge_limit: int = 24,
    ) -> dict[str, Any]:
        """Return one compact registry, usage, consequence, neighborhood, graph, and refs packet for an operational entity."""
        return current_state().session_entity_dossier(
            anchor=anchor,
            kind=kind,
            session=session,
            usage_limit=usage_limit,
            neighborhood_limit=neighborhood_limit,
            graph_limit=graph_limit,
            graph_edge_limit=graph_edge_limit,
        )

    @read_only_tool
    def aoa_session_entity_usage_audit(
        anchor: str,
        kind: str = "auto",
        limit: int = 20,
        per_route_limit: int = 20,
        consequence_window: int = 8,
        document_limit: int = 60,
        session: str = "",
        full: bool = False,
    ) -> dict[str, Any]:
        """Trace an entity to usage events, consequences, and document refs."""
        return current_state().session_entity_usage_audit(
            anchor=anchor,
            kind=kind,
            limit=limit,
            per_route_limit=per_route_limit,
            consequence_window=consequence_window,
            document_limit=document_limit,
            session=session,
            full=full,
        )

    @read_only_tool
    def aoa_session_entity_usage_chain(
        anchor: str,
        kind: str = "auto",
        limit: int = 6,
        per_route_limit: int = 12,
        consequence_window: int = 6,
        document_limit: int = 24,
        session: str = "",
        full: bool = False,
    ) -> dict[str, Any]:
        """Return compact usage-to-consequence chains for an operational entity without graph or raw-preview expansion."""
        return current_state().session_entity_usage_chain(
            anchor=anchor,
            kind=kind,
            limit=limit,
            per_route_limit=per_route_limit,
            consequence_window=consequence_window,
            document_limit=document_limit,
            session=session,
            full=full,
        )

    @read_only_tool
    def aoa_session_entity_registry(kind: str = "all", query: str = "", lookup: str = "", limit: int = 50) -> dict[str, Any]:
        """Read generated entity registry or lookup one skill/MCP/tool/hook/API/etc anchor."""
        return current_state().session_entity_registry(kind=kind, query=query, lookup=lookup, limit=limit)

    @read_only_tool
    def aoa_session_entity_usage_neighborhood(
        anchor: str,
        kind: str = "auto",
        limit: int = 6,
        per_route_limit: int = 20,
        before: int = 3,
        after: int = 8,
        raw_preview_chars: int = 600,
        document_limit: int = 80,
        session: str = "",
        full: bool = False,
    ) -> dict[str, Any]:
        """Trace an entity to usage events and local before/after raw evidence windows."""
        return current_state().session_entity_usage_neighborhood(
            anchor=anchor,
            kind=kind,
            limit=limit,
            per_route_limit=per_route_limit,
            before=before,
            after=after,
            raw_preview_chars=raw_preview_chars,
            document_limit=document_limit,
            session=session,
            full=full,
        )

    @read_only_tool
    def aoa_session_entity_usage_scenario_audit(
        sample_size: int = 8,
        seed: str = "entity-usage-scenario-audit",
        layers: list[str] | None = None,
        min_postings: int = 1,
        limit: int = 8,
        per_route_limit: int = 8,
        consequence_window: int = 4,
        document_limit: int = 24,
        raw_preview_limit: int = 3,
        full: bool = False,
    ) -> dict[str, Any]:
        """Run a seeded random live scenario over real route terms."""
        return current_state().session_entity_usage_scenario_audit(
            sample_size=sample_size,
            seed=seed,
            layers=layers,
            min_postings=min_postings,
            limit=limit,
            per_route_limit=per_route_limit,
            consequence_window=consequence_window,
            document_limit=document_limit,
            raw_preview_limit=raw_preview_limit,
            full=full,
        )

    @read_only_tool
    def aoa_session_live_scenario_audit(
        seed: str = "live-scenario-audit",
        profiles: list[str] | None = None,
        sample_size: int = 4,
        recent_days: int = 7,
        limit: int = 3,
    ) -> dict[str, Any]:
        """Run bounded live route-quality scenarios, including entity registry lookup status probes."""
        return current_state().session_live_scenario_audit(
            seed=seed,
            profiles=profiles,
            sample_size=sample_size,
            recent_days=recent_days,
            limit=limit,
        )

    @read_only_tool
    def aoa_session_live_scenario_corpus_check(
        case_limit: int = 0,
        full: bool = False,
    ) -> dict[str, Any]:
        """Check the source-owned live-scenario regression corpus against current route behavior."""
        return current_state().session_live_scenario_corpus_check(
            case_limit=case_limit,
            full=full,
        )

    @read_only_tool
    def aoa_session_live_scenario_corpus_inventory(full: bool = False) -> dict[str, Any]:
        """List reviewed live-scenario corpus cases without running them."""
        return current_state().session_live_scenario_corpus_inventory(full=full)

    @read_only_tool
    def aoa_session_route(
        axis: str,
        key: str = "",
        limit: int = 20,
        include_entry_payloads: bool = False,
    ) -> dict[str, Any]:
        """Read a generated atlas map axis without replacing its evidence refs."""
        return current_state().session_route(
            axis=axis,
            key=key,
            limit=limit,
            include_entry_payloads=include_entry_payloads,
        )

    @read_only_tool
    def aoa_session_brief(session: str = "latest", max_segments: int = 5) -> dict[str, Any]:
        """Return a compact session brief with manifest/index/raw refs."""
        return current_state().session_brief(session=session, max_segments=max_segments)

    @read_only_tool
    def aoa_session_retrieve(
        recipe: str = "continue-session",
        query: str = "",
        session: str = "",
        limit: int = 8,
        event_limit: int = 12,
    ) -> dict[str, Any]:
        """Build a compact .aoa retrieval packet for review."""
        return current_state().session_retrieve(
            recipe=recipe,
            query=query,
            session=session,
            limit=limit,
            event_limit=event_limit,
        )

    @read_only_tool
    def aoa_session_evidence_packet(
        intent: str,
        query: str = "",
        anchors: list[str] | None = None,
        refs: list[str] | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Collect candidate evidence refs for a decision, writeback, debug, or review intent."""
        return current_state().session_evidence_packet(
            intent=intent,
            query=query,
            anchors=anchors,
            refs=refs,
            limit=limit,
        )

    @read_only_tool
    def aoa_session_freshness_check(refs: list[str] | None = None, session: str = "") -> dict[str, Any]:
        """Check whether evidence refs are present and whether the search provider is ready."""
        return current_state().session_freshness_check(refs=refs, session=session)

    @read_only_tool
    def aoa_session_pattern_scan(pattern: str, filters: dict[str, Any] | None = None, limit: int = 50) -> dict[str, Any]:
        """Aggregate recurring session-event patterns from .aoa search hits."""
        return current_state().session_pattern_scan(pattern=pattern, filters=filters, limit=limit)

    @read_only_tool
    def aoa_session_entity_inventory(
        layer: str = "skill",
        query: str = "",
        session: str = "",
        limit: int = 50,
        sample_limit: int = 2,
    ) -> dict[str, Any]:
        """Aggregate typed session entities such as skills, MCPs, hooks, tools, APIs, scripts, evals, Git, playbooks, techniques, mechanics, graphs, or memory surfaces."""
        return current_state().session_entity_inventory(
            layer=layer,
            query=query,
            session=session,
            limit=limit,
            sample_limit=sample_limit,
        )

    @read_only_tool
    def aoa_session_hook_receipts(
        event_name: str = "UserPromptSubmit",
        session: str = "",
        date_from: str = "",
        only_errors: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Read hook receipt evidence directly, without relying on search or graph noise."""
        return current_state().session_hook_receipts(
            event_name=event_name,
            session=session,
            date_from=date_from,
            only_errors=only_errors,
            limit=limit,
        )

    @read_only_tool
    def aoa_session_latest_diagnostics(
        kind: str = "route-layer-readiness",
        limit: int = 5,
        include_payload: bool = False,
    ) -> dict[str, Any]:
        """Read latest .aoa diagnostics summaries without mutating the archive."""
        return current_state().latest_diagnostics(kind=kind, limit=limit, include_payload=include_payload)

    @read_only_tool
    def aoa_session_maintenance_status(
        deep: bool = False,
        include_timers: bool = True,
        full: bool = False,
    ) -> dict[str, Any]:
        """Return the canonical read-only .aoa maintenance status packet."""
        return current_state().session_maintenance_status(deep=deep, include_timers=include_timers, full=full)

    @read_only_tool
    def aoa_session_maintenance_plan() -> dict[str, Any]:
        """Return the non-mutating maintenance status through the older plan name."""
        return current_state().maintenance_plan()

    @read_only_tool
    def aoa_session_route_rollup_query(
        query: str = "",
        layer: str = "tool",
        key: str = "",
        route_signal: str = "",
        limit: int = 12,
        ref_limit: int = 3,
    ) -> dict[str, Any]:
        """Read the materialized operational route-rollup without maintenance, shard resampling, or raw hydration."""
        return current_state().session_operational_route_rollup_query(
            query=query,
            layer=layer,
            key=key,
            route_signal=route_signal,
            limit=limit,
            ref_limit=ref_limit,
        )

    @read_only_tool
    def aoa_session_direct_event_rollup_query(
        query: str = "",
        usage_role: str = "result",
        event_type: str = "",
        session_act: str = "",
        layer: str = "",
        key: str = "",
        route_signal: str = "",
        limit: int = 12,
        ref_limit: int = 3,
    ) -> dict[str, Any]:
        """Read the materialized direct operational-event rollup without shard resampling, FTS, monolith reads, or body hydration."""
        return current_state().session_operational_direct_event_rollup_query(
            query=query,
            usage_role=usage_role,
            event_type=event_type,
            session_act=session_act,
            layer=layer,
            key=key,
            route_signal=route_signal,
            limit=limit,
            ref_limit=ref_limit,
        )

    @read_only_tool
    def aoa_session_projection_status(include_payload: bool = False) -> dict[str, Any]:
        """Read the latest projection-catchup completeness diagnostic without running maintenance."""
        return current_state().session_projection_status(include_payload=include_payload)

    @read_only_tool
    def aoa_session_graph_neighborhood(
        anchor: str,
        kind: str = "auto",
        depth: int = 1,
        limit: int = 40,
        edge_limit: int | None = None,
    ) -> dict[str, Any]:
        """Read a bounded indexed graph neighborhood or return an admission-required owner command."""
        return current_state().graph_neighborhood(anchor=anchor, kind=kind, depth=depth, limit=limit, edge_limit=edge_limit)

    @read_only_tool
    def aoa_session_graph_timeline(anchor: str, kind: str = "auto", limit: int = 40) -> dict[str, Any]:
        """Read bounded direct event edges for an indexed operational anchor."""
        return current_state().graph_timeline(anchor=anchor, kind=kind, limit=limit)

    @read_only_tool
    def aoa_session_graph_shortest_path(source: str, target: str, kind: str = "auto", max_depth: int = 4) -> dict[str, Any]:
        """Return the admission-required owner command for graph path traversal."""
        return current_state().graph_shortest_path(source=source, target=target, kind=kind, max_depth=max_depth)

    @read_only_tool
    def aoa_session_graph_bridge(
        source: str,
        target: str,
        kind: str = "auto",
        source_kind: str = "auto",
        target_kind: str = "auto",
        max_depth: int = 4,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Return the admission-required owner bridge command without hidden archive work."""
        return current_state().graph_bridge(
            source=source,
            target=target,
            kind=kind,
            source_kind=source_kind,
            target_kind=target_kind,
            max_depth=max_depth,
            limit=limit,
        )

    @read_only_tool
    def aoa_session_graph_cooccurrence(anchor: str, kind: str = "auto", limit: int = 30) -> dict[str, Any]:
        """Aggregate a bounded two-hop indexed event-to-route neighborhood."""
        return current_state().graph_cooccurrence(anchor=anchor, kind=kind, limit=limit)

    @read_only_tool
    def aoa_session_graphrag_packet(
        query: str,
        anchor: str = "",
        mode: str = "hybrid",
        limit: int = 8,
        include_semantic_context: bool = False,
        rerank_local: bool = False,
    ) -> dict[str, Any]:
        """Return bounded graph evidence plus the admission-required owner GraphRAG command."""
        return current_state().graphrag_packet(
            query=query,
            anchor=anchor,
            mode=mode,
            limit=limit,
            include_semantic_context=include_semantic_context,
            rerank_local=rerank_local,
        )

    @read_only_tool
    def aoa_session_explain_graph_packet(
        intent: str,
        anchor: str = "",
        query: str = "",
        limit: int = 8,
    ) -> dict[str, Any]:
        """Return bounded graph evidence plus the admission-required owner explanation command."""
        return current_state().explain_graph_packet(intent=intent, anchor=anchor, query=query, limit=limit)

    @read_only_tool
    def aoa_session_graph_eval(
        limit: int = 6,
        include_semantic_context: bool = False,
        rerank_local: bool = False,
    ) -> dict[str, Any]:
        """Plan admission-required graph evaluation without running batch analysis inside MCP."""
        return current_state().graph_eval(
            limit=limit,
            include_semantic_context=include_semantic_context,
            rerank_local=rerank_local,
        )

    @read_only_tool
    def aoa_session_graph_quality_audit(
        limit: int = 4,
        sample_ref_limit: int = 2,
        anchors: list[Any] | None = None,
        full_graphrag: bool = False,
    ) -> dict[str, Any]:
        """Plan an admission-required multi-anchor quality audit without running it inside MCP."""
        return current_state().graph_quality_audit(
            limit=limit,
            sample_ref_limit=sample_ref_limit,
            anchors=anchors,
            full_graphrag=full_graphrag,
        )

    @mcp.resource("aoa-session-memory://status")
    def status_resource() -> str:
        return json.dumps(current_state().session_memory_status(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://surfaces")
    def surfaces_resource() -> str:
        return json.dumps(current_state().available_surfaces(), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://provider/status")
    def provider_status_resource() -> str:
        return json.dumps(current_state().read_resource("aoa-session-memory://provider/status"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://maintenance/status")
    def maintenance_status_resource() -> str:
        return json.dumps(current_state().read_resource("aoa-session-memory://maintenance/status"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://projection/status")
    def projection_status_resource() -> str:
        return json.dumps(current_state().read_resource("aoa-session-memory://projection/status"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://readiness/route-layer")
    def readiness_resource() -> str:
        return json.dumps(current_state().read_resource("aoa-session-memory://readiness/route-layer"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://diagnostics/latest/{kind}")
    def diagnostics_resource(kind: str) -> str:
        return json.dumps(current_state().latest_diagnostics(kind=kind), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://entities/{layer}")
    def entities_resource(layer: str) -> str:
        return json.dumps(current_state().session_entity_inventory(layer=layer, limit=50, sample_limit=2), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://entity-registry/{kind}")
    def entity_registry_resource(kind: str) -> str:
        return json.dumps(current_state().session_entity_registry(kind=kind, limit=50), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://entity-lookup/{kind}/{anchor}")
    def entity_lookup_resource(kind: str, anchor: str) -> str:
        return json.dumps(current_state().session_entity_registry(kind=kind, lookup=anchor, limit=10), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://session/{session}/brief")
    def session_brief_resource(session: str) -> str:
        return json.dumps(current_state().session_brief(session), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://session/{session}/manifest")
    def session_manifest_resource(session: str) -> str:
        return json.dumps(current_state().read_resource(f"aoa-session-memory://session/{session}/manifest"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://session/{session}/index")
    def session_index_resource(session: str) -> str:
        return json.dumps(current_state().read_resource(f"aoa-session-memory://session/{session}/index"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://session/{session}/rehydrate")
    def session_rehydrate_resource(session: str) -> str:
        return json.dumps(current_state().read_resource(f"aoa-session-memory://session/{session}/rehydrate"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://route/{axis}/{key}")
    def route_resource(axis: str, key: str) -> str:
        return json.dumps(current_state().session_route(axis=axis, key=key), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://trace/{anchor}")
    def trace_resource(anchor: str) -> str:
        return json.dumps(current_state().session_trace(anchor=anchor, limit=12, per_route_limit=5), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://graph/status")
    def graph_status_resource() -> str:
        return json.dumps(current_state().read_resource("aoa-session-memory://graph/status"), ensure_ascii=False, indent=2)

    @mcp.resource("aoa-session-memory://graph/neighborhood/{anchor}")
    def graph_neighborhood_resource(anchor: str) -> str:
        return json.dumps(current_state().graph_neighborhood(anchor=anchor, limit=30), ensure_ascii=False, indent=2)

    @mcp.prompt(name="session-rehydrate")
    def session_rehydrate_prompt(session: str = "latest") -> str:
        """Prompt route for rehydrating a session without flattening raw evidence."""
        return (
            f"Use aoa_session_brief(session={session!r}) first, then "
            f"aoa_session_retrieve(recipe='continue-session', session={session!r}) if a compact packet is needed. "
            "Follow returned manifest, segment, and raw refs before making claims."
        )

    @mcp.prompt(name="trace-agent-process")
    def trace_agent_process(anchor: str) -> str:
        """Prompt route for tracing a stable agent-process anchor."""
        return (
            f"Use aoa_session_trace(anchor={anchor!r}, kind='auto'), then inspect matched route candidates. "
            "Treat entity, MCP, tool, hook, path, and goal matches as route coordinates, not truth."
        )

    @mcp.prompt(name="debug-operational-anchor")
    def debug_operational_anchor(anchor: str) -> str:
        """Prompt route for debugging a skill, MCP, hook, tool, path, or similar anchor."""
        return (
            f"Start with aoa_session_graph_neighborhood(anchor={anchor!r}), then aoa_session_trace(anchor={anchor!r}) "
            f"and aoa_session_search(query={anchor!r}, filters={{'explain': True}}). "
            "Use aoa_session_freshness_check on returned refs before relying on them."
        )

    @mcp.prompt(name="writeback-evidence-check")
    def writeback_evidence_check(intent: str) -> str:
        """Prompt route for checking evidence before memory writeback."""
        return (
            f"Use aoa_session_evidence_packet(intent={intent!r}, query={intent!r}). "
            "Carry only checked refs into aoa-memo candidate or reviewed-intake work; this MCP does not write memory."
        )

    @mcp.prompt(name="stale-ref-repair-plan")
    def stale_ref_repair_plan(ref: str) -> str:
        """Prompt route for handling stale evidence refs."""
        return (
            f"Use aoa_session_freshness_check(refs=[{ref!r}]) and aoa_session_maintenance_status(include_timers=False). "
            "If repair is needed, run .aoa maintenance outside MCP with explicit operator intent."
        )

    @mcp.prompt(name="promotion-candidate-review")
    def promotion_candidate_review(anchor: str) -> str:
        """Prompt route for reviewing whether a recurring pattern deserves promotion."""
        return (
            f"Use aoa_session_graphrag_packet(query={anchor!r}) and aoa_session_pattern_scan(pattern={anchor!r}); inspect returned raw/segment refs. "
            "Promotion still requires reviewed distillation or owner-repo change outside MCP."
        )

    LOGGER.debug("AoA session-memory MCP server ready")
    return mcp


def main() -> None:
    level_name = os.environ.get("AOA_SESSION_MEMORY_MCP_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(level=level)
    _run_server(build_server())
