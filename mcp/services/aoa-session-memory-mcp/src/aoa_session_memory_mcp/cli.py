from __future__ import annotations

import argparse
import json
from typing import Any

from .core import AoASessionMemoryMCPState


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_filter(values: list[str] | None) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for item in values or []:
        if "=" not in item:
            raise SystemExit(f"filter must be key=value, got: {item}")
        key, value = item.split("=", 1)
        if value.casefold() == "true":
            parsed: Any = True
        elif value.casefold() == "false":
            parsed = False
        else:
            parsed = value
        filters[key] = parsed
    return filters


def main() -> None:
    parser = argparse.ArgumentParser(prog="aoa-session-memory-mcp")
    parser.add_argument("--workspace-root", default=None)
    parser.add_argument("--aoa-root", default=None)
    parser.add_argument("--script-path", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.add_argument("--include-live", action="store_true")

    search = sub.add_parser("search")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--filter", action="append")
    search.add_argument("--limit", type=int, default=20)

    literal_plan = sub.add_parser("literal-query-plan")
    literal_plan.add_argument("query", nargs="?", default="")
    literal_plan.add_argument("--kind", default="auto")
    literal_plan.add_argument("--filter", action="append")

    agent_responses = sub.add_parser("agent-responses")
    agent_responses.add_argument("query", nargs="?", default="")
    agent_responses.add_argument("--session", default="")
    agent_responses.add_argument("--agent-event", action="append")
    agent_responses.add_argument("--episode", default="")
    agent_responses.add_argument("--closeout-final", action="store_true")
    agent_responses.add_argument("--verification-state", default="any")
    agent_responses.add_argument("--failure-state", default="any")
    agent_responses.add_argument("--limit", type=int, default=20)
    agent_responses.add_argument("--no-shards", action="store_true", help="Force monolithic search projection instead of shard-first agent-event routing.")

    agent_closeouts = sub.add_parser("agent-closeouts")
    agent_closeouts.add_argument("query", nargs="?", default="")
    agent_closeouts.add_argument("--session", default="")
    agent_closeouts.add_argument("--episode", default="")
    agent_closeouts.add_argument("--limit", type=int, default=20)

    agent_progress = sub.add_parser("agent-progress-updates")
    agent_progress.add_argument("query", nargs="?", default="")
    agent_progress.add_argument("--session", default="")
    agent_progress.add_argument("--episode", default="")
    agent_progress.add_argument("--limit", type=int, default=20)

    reasoning_windows = sub.add_parser("agent-reasoning-windows")
    reasoning_windows.add_argument("query", nargs="?", default="")
    reasoning_windows.add_argument("--session", default="")
    reasoning_windows.add_argument("--episode", default="")
    reasoning_windows.add_argument("--limit", type=int, default=10)
    reasoning_windows.add_argument("--before", type=int, default=3)
    reasoning_windows.add_argument("--after", type=int, default=6)
    reasoning_windows.set_defaults(explain=True)
    reasoning_windows.add_argument("--explain", dest="explain", action="store_true")
    reasoning_windows.add_argument("--no-explain", dest="explain", action="store_false")

    task_episodes = sub.add_parser("task-episodes")
    task_episodes.add_argument("target", nargs="?", default="all")
    task_episodes.add_argument("--session", default="")
    task_episodes.add_argument("--episode", default="")
    task_episodes.add_argument("--status", default="")
    task_episodes.add_argument("--verification-state", default="")
    task_episodes.add_argument("--failure-state", default="")
    task_episodes.add_argument("--limit", type=int, default=20)

    goal_lifecycles = sub.add_parser("goal-lifecycles")
    goal_lifecycles.add_argument("target", nargs="?", default="all")
    goal_lifecycles.add_argument("--session", default="")
    goal_lifecycles.add_argument("--goal-id", default="")
    goal_lifecycles.add_argument("--status", default="")
    goal_lifecycles.add_argument("--event-kind", default="")
    goal_lifecycles.add_argument("--limit", type=int, default=20)
    goal_lifecycles.add_argument("--order", default="recent")

    answer_neighborhood = sub.add_parser("answer-neighborhood")
    answer_neighborhood.add_argument("query", nargs="?", default="")
    answer_neighborhood.add_argument("--session", default="")
    answer_neighborhood.add_argument("--agent-event", action="append")
    answer_neighborhood.add_argument("--episode", default="")
    answer_neighborhood.add_argument("--limit", type=int, default=10)
    answer_neighborhood.add_argument("--before", type=int, default=3)
    answer_neighborhood.add_argument("--after", type=int, default=6)
    answer_neighborhood.set_defaults(explain=True)
    answer_neighborhood.add_argument("--explain", dest="explain", action="store_true")
    answer_neighborhood.add_argument("--no-explain", dest="explain", action="store_false")

    trace = sub.add_parser("trace")
    trace.add_argument("anchor")
    trace.add_argument("--kind", default="auto")
    trace.add_argument("--limit", type=int, default=20)
    trace.add_argument("--per-route-limit", type=int, default=10)
    trace.add_argument("--session", default="")
    trace.add_argument("--doc-type", default="session")

    dossier = sub.add_parser("entity-dossier")
    dossier.add_argument("anchor")
    dossier.add_argument("--kind", default="auto")
    dossier.add_argument("--session", default="")
    dossier.add_argument("--usage-limit", type=int, default=4)
    dossier.add_argument("--neighborhood-limit", type=int, default=2)
    dossier.add_argument("--graph-limit", type=int, default=12)
    dossier.add_argument("--graph-edge-limit", type=int, default=24)

    usage = sub.add_parser("usage-audit")
    usage.add_argument("anchor")
    usage.add_argument("--kind", default="auto")
    usage.add_argument("--limit", type=int, default=20)
    usage.add_argument("--per-route-limit", type=int, default=20)
    usage.add_argument("--consequence-window", type=int, default=8)
    usage.add_argument("--document-limit", type=int, default=60)
    usage.add_argument("--session", default="")
    usage.add_argument("--full", action="store_true")

    usage_neighborhood = sub.add_parser("usage-neighborhood")
    usage_neighborhood.add_argument("anchor")
    usage_neighborhood.add_argument("--kind", default="auto")
    usage_neighborhood.add_argument("--limit", type=int, default=6)
    usage_neighborhood.add_argument("--per-route-limit", type=int, default=20)
    usage_neighborhood.add_argument("--before", type=int, default=3)
    usage_neighborhood.add_argument("--after", type=int, default=8)
    usage_neighborhood.add_argument("--raw-preview-chars", type=int, default=600)
    usage_neighborhood.add_argument("--document-limit", type=int, default=80)
    usage_neighborhood.add_argument("--session", default="")
    usage_neighborhood.add_argument("--full", action="store_true")

    usage_scenario = sub.add_parser("usage-scenario-audit")
    usage_scenario.add_argument("--seed", default="entity-usage-scenario-audit")
    usage_scenario.add_argument("--sample-size", type=int, default=8)
    usage_scenario.add_argument("--layer", action="append")
    usage_scenario.add_argument("--min-postings", type=int, default=1)
    usage_scenario.add_argument("--limit", type=int, default=8)
    usage_scenario.add_argument("--per-route-limit", type=int, default=8)
    usage_scenario.add_argument("--consequence-window", type=int, default=4)
    usage_scenario.add_argument("--document-limit", type=int, default=24)
    usage_scenario.add_argument("--raw-preview-limit", type=int, default=3)
    usage_scenario.add_argument("--full", action="store_true")

    live_scenario = sub.add_parser("live-scenario-audit")
    live_scenario.add_argument("--seed", default="live-scenario-audit")
    live_scenario.add_argument("--profile", action="append")
    live_scenario.add_argument("--sample-size", type=int, default=4)
    live_scenario.add_argument("--recent-days", type=int, default=7)
    live_scenario.add_argument("--limit", type=int, default=3)

    live_scenario_corpus = sub.add_parser("live-scenario-corpus-check")
    live_scenario_corpus.add_argument("--case-limit", type=int, default=0)
    live_scenario_corpus.add_argument("--full", action="store_true")

    route = sub.add_parser("route")
    route.add_argument("axis")
    route.add_argument("key", nargs="?", default="")
    route.add_argument("--limit", type=int, default=20)
    route.add_argument("--include-entry-payloads", action="store_true")

    brief = sub.add_parser("brief")
    brief.add_argument("session", nargs="?", default="latest")
    brief.add_argument("--max-segments", type=int, default=5)

    retrieve = sub.add_parser("retrieve")
    retrieve.add_argument("--recipe", default="continue-session")
    retrieve.add_argument("--query", default="")
    retrieve.add_argument("--session", default="")
    retrieve.add_argument("--limit", type=int, default=8)
    retrieve.add_argument("--event-limit", type=int, default=12)

    evidence = sub.add_parser("evidence-packet")
    evidence.add_argument("--intent", required=True)
    evidence.add_argument("--query", default="")
    evidence.add_argument("--anchor", action="append")
    evidence.add_argument("--ref", action="append")
    evidence.add_argument("--limit", type=int, default=8)

    freshness = sub.add_parser("freshness-check")
    freshness.add_argument("refs", nargs="*")
    freshness.add_argument("--session", default="")

    pattern = sub.add_parser("pattern-scan")
    pattern.add_argument("pattern")
    pattern.add_argument("--filter", action="append")
    pattern.add_argument("--limit", type=int, default=50)

    inventory = sub.add_parser("entity-inventory")
    inventory.add_argument("--layer", default="skill")
    inventory.add_argument("--query", default="")
    inventory.add_argument("--session", default="")
    inventory.add_argument("--limit", type=int, default=50)
    inventory.add_argument("--sample-limit", type=int, default=2)

    registry = sub.add_parser("entity-registry")
    registry.add_argument("--kind", default="all")
    registry.add_argument("--query", default="")
    registry.add_argument("--lookup", default="")
    registry.add_argument("--limit", type=int, default=50)

    hook_receipts = sub.add_parser("hook-receipts")
    hook_receipts.add_argument("--event-name", default="UserPromptSubmit")
    hook_receipts.add_argument("--session", default="")
    hook_receipts.add_argument("--date-from", default="")
    hook_receipts.add_argument("--only-errors", action="store_true")
    hook_receipts.add_argument("--limit", type=int, default=50)

    diagnostics = sub.add_parser("latest-diagnostics")
    diagnostics.add_argument("--kind", default="route-layer-readiness")
    diagnostics.add_argument("--limit", type=int, default=5)
    diagnostics.add_argument("--include-payload", action="store_true")

    maintenance_status = sub.add_parser("maintenance-status")
    maintenance_status.add_argument("--deep", action="store_true")
    maintenance_status.add_argument("--no-timers", action="store_true")
    maintenance_status.add_argument("--full", action="store_true")

    maintenance_plan = sub.add_parser("maintenance-plan")
    maintenance_plan.add_argument("--deep", action="store_true")
    maintenance_plan.add_argument("--no-timers", action="store_true")
    maintenance_plan.add_argument("--full", action="store_true")

    projection_status = sub.add_parser("projection-status")
    projection_status.add_argument("--include-payload", action="store_true")

    graph_neighborhood = sub.add_parser("graph-neighborhood")
    graph_neighborhood.add_argument("anchor")
    graph_neighborhood.add_argument("--kind", default="auto")
    graph_neighborhood.add_argument("--depth", type=int, default=1)
    graph_neighborhood.add_argument("--limit", type=int, default=40)
    graph_neighborhood.add_argument("--edge-limit", type=int, default=None)

    graph_timeline = sub.add_parser("graph-timeline")
    graph_timeline.add_argument("anchor")
    graph_timeline.add_argument("--kind", default="auto")
    graph_timeline.add_argument("--limit", type=int, default=40)

    graph_path = sub.add_parser("graph-shortest-path")
    graph_path.add_argument("source")
    graph_path.add_argument("target")
    graph_path.add_argument("--kind", default="auto")
    graph_path.add_argument("--max-depth", type=int, default=4)

    graph_bridge = sub.add_parser("graph-bridge")
    graph_bridge.add_argument("source")
    graph_bridge.add_argument("target")
    graph_bridge.add_argument("--kind", default="auto")
    graph_bridge.add_argument("--source-kind", default="auto")
    graph_bridge.add_argument("--target-kind", default="auto")
    graph_bridge.add_argument("--max-depth", type=int, default=4)
    graph_bridge.add_argument("--limit", type=int, default=8)

    graph_cooccurrence = sub.add_parser("graph-cooccurrence")
    graph_cooccurrence.add_argument("anchor")
    graph_cooccurrence.add_argument("--kind", default="auto")
    graph_cooccurrence.add_argument("--limit", type=int, default=30)

    graphrag = sub.add_parser("graphrag-packet")
    graphrag.add_argument("query")
    graphrag.add_argument("--anchor", default="")
    graphrag.add_argument("--mode", default="hybrid")
    graphrag.add_argument("--limit", type=int, default=8)
    graphrag.add_argument("--include-semantic-context", action="store_true")
    graphrag.add_argument("--rerank-local", action="store_true")

    graph_explain = sub.add_parser("graph-explain-packet")
    graph_explain.add_argument("intent")
    graph_explain.add_argument("--anchor", default="")
    graph_explain.add_argument("--query", default="")
    graph_explain.add_argument("--limit", type=int, default=8)

    graph_eval = sub.add_parser("graph-eval")
    graph_eval.add_argument("--limit", type=int, default=6)
    graph_eval.add_argument("--include-semantic-context", action="store_true")
    graph_eval.add_argument("--rerank-local", action="store_true")

    graph_quality = sub.add_parser("graph-quality-audit")
    graph_quality.add_argument("--anchor", action="append")
    graph_quality.add_argument("--limit", type=int, default=4)
    graph_quality.add_argument("--sample-ref-limit", type=int, default=2)
    graph_quality.add_argument("--full-graphrag", action="store_true")

    resource = sub.add_parser("read-resource")
    resource.add_argument("uri")

    args = parser.parse_args()
    state = AoASessionMemoryMCPState.discover(
        workspace_root=args.workspace_root,
        aoa_root=args.aoa_root,
        script_path=args.script_path,
    )

    if args.command == "status":
        _print(state.session_memory_status(include_live=args.include_live))
    elif args.command == "search":
        _print(state.session_search(args.query, filters=_parse_filter(args.filter), limit=args.limit))
    elif args.command == "literal-query-plan":
        _print(state.session_literal_query_plan(args.query, kind=args.kind, filters=_parse_filter(args.filter)))
    elif args.command == "agent-responses":
        _print(
            state.session_agent_responses(
                query=args.query,
                session=args.session,
                agent_events=args.agent_event,
                episode=args.episode,
                closeout_final=args.closeout_final,
                verification_state=args.verification_state,
                failure_state=args.failure_state,
                limit=args.limit,
                use_shards=not args.no_shards,
            )
        )
    elif args.command == "agent-closeouts":
        _print(state.session_agent_closeouts(query=args.query, session=args.session, episode=args.episode, limit=args.limit))
    elif args.command == "agent-progress-updates":
        _print(state.session_agent_progress_updates(query=args.query, session=args.session, episode=args.episode, limit=args.limit))
    elif args.command == "agent-reasoning-windows":
        _print(
            state.session_agent_reasoning_windows(
                query=args.query,
                session=args.session,
                episode=args.episode,
                limit=args.limit,
                before=args.before,
                after=args.after,
                explain=args.explain,
            )
        )
    elif args.command == "task-episodes":
        _print(
            state.session_task_episodes(
                target=args.target,
                session=args.session,
                episode=args.episode,
                status=args.status,
                verification_state=args.verification_state,
                failure_state=args.failure_state,
                limit=args.limit,
            )
        )
    elif args.command == "goal-lifecycles":
        _print(
            state.session_goal_lifecycles(
                target=args.target,
                session=args.session,
                goal_id=args.goal_id,
                status=args.status,
                event_kind=args.event_kind,
                limit=args.limit,
                order=args.order,
            )
        )
    elif args.command == "answer-neighborhood":
        _print(
            state.session_answer_neighborhood(
                query=args.query,
                session=args.session,
                agent_events=args.agent_event,
                episode=args.episode,
                limit=args.limit,
                before=args.before,
                after=args.after,
                explain=args.explain,
            )
        )
    elif args.command == "trace":
        _print(
            state.session_trace(
                anchor=args.anchor,
                kind=args.kind,
                limit=args.limit,
                per_route_limit=args.per_route_limit,
                session=args.session,
                doc_type=args.doc_type,
            )
        )
    elif args.command == "entity-dossier":
        _print(
            state.session_entity_dossier(
                anchor=args.anchor,
                kind=args.kind,
                session=args.session,
                usage_limit=args.usage_limit,
                neighborhood_limit=args.neighborhood_limit,
                graph_limit=args.graph_limit,
                graph_edge_limit=args.graph_edge_limit,
            )
        )
    elif args.command == "route":
        _print(state.session_route(args.axis, args.key, limit=args.limit, include_entry_payloads=args.include_entry_payloads))
    elif args.command == "usage-audit":
        _print(
            state.session_entity_usage_audit(
                anchor=args.anchor,
                kind=args.kind,
                limit=args.limit,
                per_route_limit=args.per_route_limit,
                consequence_window=args.consequence_window,
                document_limit=args.document_limit,
                session=args.session,
                full=args.full,
            )
        )
    elif args.command == "usage-neighborhood":
        _print(
            state.session_entity_usage_neighborhood(
                anchor=args.anchor,
                kind=args.kind,
                limit=args.limit,
                per_route_limit=args.per_route_limit,
                before=args.before,
                after=args.after,
                raw_preview_chars=args.raw_preview_chars,
                document_limit=args.document_limit,
                session=args.session,
                full=args.full,
            )
        )
    elif args.command == "usage-scenario-audit":
        _print(
            state.session_entity_usage_scenario_audit(
                sample_size=args.sample_size,
                seed=args.seed,
                layers=args.layer,
                min_postings=args.min_postings,
                limit=args.limit,
                per_route_limit=args.per_route_limit,
                consequence_window=args.consequence_window,
                document_limit=args.document_limit,
                raw_preview_limit=args.raw_preview_limit,
                full=args.full,
            )
        )
    elif args.command == "live-scenario-audit":
        _print(
            state.session_live_scenario_audit(
                seed=args.seed,
                profiles=args.profile,
                sample_size=args.sample_size,
                recent_days=args.recent_days,
                limit=args.limit,
            )
        )
    elif args.command == "live-scenario-corpus-check":
        _print(
            state.session_live_scenario_corpus_check(
                case_limit=args.case_limit,
                full=args.full,
            )
        )
    elif args.command == "brief":
        _print(state.session_brief(args.session, max_segments=args.max_segments))
    elif args.command == "retrieve":
        _print(
            state.session_retrieve(
                recipe=args.recipe,
                query=args.query,
                session=args.session,
                limit=args.limit,
                event_limit=args.event_limit,
            )
        )
    elif args.command == "evidence-packet":
        _print(
            state.session_evidence_packet(
                intent=args.intent,
                query=args.query,
                anchors=args.anchor,
                refs=args.ref,
                limit=args.limit,
            )
        )
    elif args.command == "freshness-check":
        _print(state.session_freshness_check(args.refs, session=args.session))
    elif args.command == "pattern-scan":
        _print(state.session_pattern_scan(args.pattern, filters=_parse_filter(args.filter), limit=args.limit))
    elif args.command == "entity-inventory":
        _print(
            state.session_entity_inventory(
                layer=args.layer,
                query=args.query,
                session=args.session,
                limit=args.limit,
                sample_limit=args.sample_limit,
            )
        )
    elif args.command == "entity-registry":
        _print(state.session_entity_registry(kind=args.kind, query=args.query, lookup=args.lookup, limit=args.limit))
    elif args.command == "hook-receipts":
        _print(
            state.session_hook_receipts(
                event_name=args.event_name,
                session=args.session,
                date_from=args.date_from,
                only_errors=args.only_errors,
                limit=args.limit,
            )
        )
    elif args.command == "latest-diagnostics":
        _print(state.latest_diagnostics(kind=args.kind, limit=args.limit, include_payload=args.include_payload))
    elif args.command == "maintenance-status":
        _print(state.session_maintenance_status(deep=args.deep, include_timers=not args.no_timers, full=args.full))
    elif args.command == "maintenance-plan":
        if args.deep or args.no_timers or args.full:
            _print(state.session_maintenance_status(deep=args.deep, include_timers=not args.no_timers, full=args.full))
        else:
            _print(state.maintenance_plan())
    elif args.command == "projection-status":
        _print(state.session_projection_status(include_payload=args.include_payload))
    elif args.command == "graph-neighborhood":
        _print(
            state.graph_neighborhood(
                anchor=args.anchor,
                kind=args.kind,
                depth=args.depth,
                limit=args.limit,
                edge_limit=args.edge_limit,
            )
        )
    elif args.command == "graph-timeline":
        _print(state.graph_timeline(anchor=args.anchor, kind=args.kind, limit=args.limit))
    elif args.command == "graph-shortest-path":
        _print(state.graph_shortest_path(source=args.source, target=args.target, kind=args.kind, max_depth=args.max_depth))
    elif args.command == "graph-bridge":
        _print(
            state.graph_bridge(
                source=args.source,
                target=args.target,
                kind=args.kind,
                source_kind=args.source_kind,
                target_kind=args.target_kind,
                max_depth=args.max_depth,
                limit=args.limit,
            )
        )
    elif args.command == "graph-cooccurrence":
        _print(state.graph_cooccurrence(anchor=args.anchor, kind=args.kind, limit=args.limit))
    elif args.command == "graphrag-packet":
        _print(
            state.graphrag_packet(
                query=args.query,
                anchor=args.anchor,
                mode=args.mode,
                limit=args.limit,
                include_semantic_context=args.include_semantic_context,
                rerank_local=args.rerank_local,
            )
        )
    elif args.command == "graph-explain-packet":
        _print(state.explain_graph_packet(intent=args.intent, anchor=args.anchor, query=args.query, limit=args.limit))
    elif args.command == "graph-eval":
        _print(
            state.graph_eval(
                limit=args.limit,
                include_semantic_context=args.include_semantic_context,
                rerank_local=args.rerank_local,
            )
        )
    elif args.command == "graph-quality-audit":
        _print(
            state.graph_quality_audit(
                limit=args.limit,
                sample_ref_limit=args.sample_ref_limit,
                anchors=args.anchor,
                full_graphrag=args.full_graphrag,
            )
        )
    elif args.command == "read-resource":
        _print(state.read_resource(args.uri))


if __name__ == "__main__":
    main()
