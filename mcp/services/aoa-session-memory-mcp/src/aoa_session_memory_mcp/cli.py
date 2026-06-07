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
    search.add_argument("query")
    search.add_argument("--filter", action="append")
    search.add_argument("--limit", type=int, default=20)

    trace = sub.add_parser("trace")
    trace.add_argument("anchor")
    trace.add_argument("--kind", default="auto")
    trace.add_argument("--limit", type=int, default=20)
    trace.add_argument("--per-route-limit", type=int, default=10)
    trace.add_argument("--session", default="")
    trace.add_argument("--doc-type", default="session")

    usage = sub.add_parser("usage-audit")
    usage.add_argument("anchor")
    usage.add_argument("--kind", default="auto")
    usage.add_argument("--limit", type=int, default=20)
    usage.add_argument("--per-route-limit", type=int, default=20)
    usage.add_argument("--consequence-window", type=int, default=8)
    usage.add_argument("--document-limit", type=int, default=60)
    usage.add_argument("--session", default="")

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

    pattern = sub.add_parser("pattern-scan")
    pattern.add_argument("pattern")
    pattern.add_argument("--filter", action="append")
    pattern.add_argument("--limit", type=int, default=50)

    diagnostics = sub.add_parser("latest-diagnostics")
    diagnostics.add_argument("--kind", default="route-layer-readiness")
    diagnostics.add_argument("--limit", type=int, default=5)
    diagnostics.add_argument("--include-payload", action="store_true")

    sub.add_parser("maintenance-plan")

    graph_neighborhood = sub.add_parser("graph-neighborhood")
    graph_neighborhood.add_argument("anchor")
    graph_neighborhood.add_argument("--kind", default="auto")
    graph_neighborhood.add_argument("--depth", type=int, default=1)
    graph_neighborhood.add_argument("--limit", type=int, default=40)

    graph_timeline = sub.add_parser("graph-timeline")
    graph_timeline.add_argument("anchor")
    graph_timeline.add_argument("--kind", default="auto")
    graph_timeline.add_argument("--limit", type=int, default=40)

    graph_path = sub.add_parser("graph-shortest-path")
    graph_path.add_argument("source")
    graph_path.add_argument("target")
    graph_path.add_argument("--kind", default="auto")
    graph_path.add_argument("--max-depth", type=int, default=4)

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
        _print(state.session_freshness_check(args.refs))
    elif args.command == "pattern-scan":
        _print(state.session_pattern_scan(args.pattern, filters=_parse_filter(args.filter), limit=args.limit))
    elif args.command == "latest-diagnostics":
        _print(state.latest_diagnostics(kind=args.kind, limit=args.limit, include_payload=args.include_payload))
    elif args.command == "maintenance-plan":
        _print(state.maintenance_plan())
    elif args.command == "graph-neighborhood":
        _print(state.graph_neighborhood(anchor=args.anchor, kind=args.kind, depth=args.depth, limit=args.limit))
    elif args.command == "graph-timeline":
        _print(state.graph_timeline(anchor=args.anchor, kind=args.kind, limit=args.limit))
    elif args.command == "graph-shortest-path":
        _print(state.graph_shortest_path(source=args.source, target=args.target, kind=args.kind, max_depth=args.max_depth))
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
