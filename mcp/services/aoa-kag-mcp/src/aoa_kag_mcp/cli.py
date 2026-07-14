from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .core import AoAKagMCPState
from .runtime import build_application


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _common(parser: argparse.ArgumentParser, *, default: str = "compact") -> None:
    parser.add_argument(
        "--detail",
        choices=("compact", "summary", "full"),
        default=default,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="aoa-kag-mcp")
    parser.add_argument("--workspace-root")
    parser.add_argument("--aoa-kag-root")
    parser.add_argument("--provider-map-path")
    parser.add_argument("--readiness-path")
    parser.add_argument("--coverage-path")
    parser.add_argument("--stack-root")
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover")
    discover.add_argument("--owner")
    _common(discover)

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument(
        "--strategy",
        choices=("auto", "exact", "lexical", "semantic", "hybrid", "graph"),
        default="auto",
    )
    search.add_argument("--owner")
    search.add_argument("--record-class")
    search.add_argument("--kind")
    search.add_argument("--document-role")
    search.add_argument("--surface-state")
    search.add_argument("--path")
    search.add_argument("--path-prefix")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--cursor")
    _common(search)

    read = sub.add_parser("read")
    read.add_argument("uri")
    _common(read, default="full")

    traverse = sub.add_parser("traverse")
    traverse.add_argument("source_ids", nargs="+")
    traverse.add_argument("--owner")
    traverse.add_argument("--query", default="")
    traverse.add_argument(
        "--direction",
        choices=("outgoing", "incoming", "both"),
        default="outgoing",
    )
    traverse.add_argument("--relation-kind", action="append", dest="relation_kinds")
    traverse.add_argument("--max-depth", type=int, default=2)
    traverse.add_argument("--limit", type=int, default=10)
    traverse.add_argument("--cursor")
    _common(traverse)

    explain = sub.add_parser("explain")
    explain.add_argument("trace_id")
    _common(explain, default="summary")

    args = parser.parse_args()
    state = AoAKagMCPState.discover(
        workspace_root=args.workspace_root,
        aoa_kag_root=args.aoa_kag_root,
        provider_map_path=(
            Path(args.provider_map_path) if args.provider_map_path else None
        ),
        readiness_path=Path(args.readiness_path) if args.readiness_path else None,
        coverage_path=Path(args.coverage_path) if args.coverage_path else None,
    )
    application = build_application(state, stack_root=args.stack_root)
    if args.command == "discover":
        payload = application.discover(owner=args.owner, detail=args.detail)
    elif args.command == "search":
        payload = application.search(
            args.query,
            strategy=args.strategy,
            owner=args.owner,
            record_class=args.record_class,
            kind=args.kind,
            document_role=args.document_role,
            surface_state=args.surface_state,
            path=args.path,
            path_prefix=args.path_prefix,
            detail=args.detail,
            limit=args.limit,
            cursor=args.cursor,
        )
    elif args.command == "read":
        payload = application.read(args.uri, detail=args.detail)
    elif args.command == "traverse":
        payload = application.traverse(
            args.source_ids,
            owner=args.owner,
            query=args.query,
            direction=args.direction,
            relation_kinds=args.relation_kinds,
            max_depth=args.max_depth,
            detail=args.detail,
            limit=args.limit,
            cursor=args.cursor,
        )
    else:
        payload = application.explain(args.trace_id, detail=args.detail)
    _print(payload)


if __name__ == "__main__":
    main()
