from __future__ import annotations

import argparse
import json
from typing import Any

from .core import AbyssMachineMCPState


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="abyss-machine-mcp")
    parser.add_argument("--workspace-root", default=None)
    parser.add_argument("--abyss-machine-bin", default=None)
    parser.add_argument("--timeout", type=float, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    brief = sub.add_parser("brief")
    brief.add_argument("--profile", choices=["fast", "live", "full"], default="fast")
    brief.add_argument("--evidence-limit", type=int, default=8)

    surface = sub.add_parser("surface")
    surface.add_argument("name")
    surface.add_argument("--query", default="")
    surface.add_argument("--class", dest="work_class", default="heavy")
    surface.add_argument("--kind", default="ai")
    surface.add_argument("--scope", default="now")
    surface.add_argument("--mode", default="hybrid")
    surface.add_argument("--axis", default="")
    surface.add_argument("--reader-profile", default="agent")
    surface.add_argument("--limit", type=int, default=20)
    surface.add_argument("--evidence-limit", type=int, default=12)
    surface.add_argument("--artifact-class", default="")
    surface.add_argument("--consumer-intent", default="agent")
    surface.add_argument("--source-repo", default="")
    surface.add_argument("--source-ref", default="")
    surface.add_argument("--source-root", default="")

    evidence = sub.add_parser("evidence-map")
    evidence.add_argument("--layer")
    evidence.add_argument("--limit", type=int, default=40)

    route = sub.add_parser("route")
    route.add_argument("--intent", required=True)
    route.add_argument("--class", dest="work_class", default="heavy")
    route.add_argument("--kind", default="ai")

    recall = sub.add_parser("recall")
    recall.add_argument("query")
    recall.add_argument("--mode", default="hybrid")

    maps = sub.add_parser("maps")
    maps.add_argument("--axis")
    maps.add_argument("--query", default="")
    maps.add_argument("--limit", type=int, default=40)

    packet = sub.add_parser("context-packet")
    packet.add_argument("--axis")
    packet.add_argument("--query", default="")
    packet.add_argument("--reader-profile", default="agent")
    packet.add_argument("--limit", type=int, default=20)

    rag = sub.add_parser("rag-trace")
    rag.add_argument("--query", required=True)
    rag.add_argument("--axis", default="by-rag-run")
    rag.add_argument("--reader-profile", default="retrieval-context")
    rag.add_argument("--limit", type=int, default=8)
    rag.add_argument("--evidence-limit", type=int, default=12)

    resource = sub.add_parser("read-resource")
    resource.add_argument("uri")

    sub.add_parser("surfaces")
    sub.add_parser("authority")

    args = parser.parse_args()
    state = AbyssMachineMCPState.discover(
        workspace_root=args.workspace_root,
        abyss_machine_bin=args.abyss_machine_bin,
        timeout_seconds=args.timeout,
    )

    if args.command == "brief":
        _print(state.machine_brief(profile=args.profile, evidence_limit=args.evidence_limit))
    elif args.command == "surface":
        _print(
            state.surface(
                args.name,
                query=args.query,
                work_class=args.work_class,
                kind=args.kind,
                scope=args.scope,
                mode=args.mode,
                axis=args.axis,
                reader_profile=args.reader_profile,
                limit=args.limit,
                evidence_limit=args.evidence_limit,
                artifact_class=args.artifact_class,
                consumer_intent=args.consumer_intent,
                source_repo=args.source_repo,
                source_ref=args.source_ref,
                source_root=args.source_root,
            )
        )
    elif args.command == "evidence-map":
        _print(state.evidence_map(layer=args.layer, limit=args.limit))
    elif args.command == "route":
        _print(state.machine_route(intent=args.intent, work_class=args.work_class, kind=args.kind))
    elif args.command == "recall":
        _print(state.recall(query=args.query, mode=args.mode))
    elif args.command == "maps":
        _print(state.machine_maps(axis=args.axis, query=args.query, limit=args.limit))
    elif args.command == "context-packet":
        _print(state.machine_context_packet(axis=args.axis, query=args.query, reader_profile=args.reader_profile, limit=args.limit))
    elif args.command == "rag-trace":
        _print(
            state.machine_rag_trace(
                query=args.query,
                axis=args.axis,
                reader_profile=args.reader_profile,
                limit=args.limit,
                evidence_limit=args.evidence_limit,
            )
        )
    elif args.command == "read-resource":
        _print(state.read_resource(args.uri))
    elif args.command == "surfaces":
        _print(state.available_surfaces())
    elif args.command == "authority":
        _print(state.authority_boundary())


if __name__ == "__main__":
    main()
