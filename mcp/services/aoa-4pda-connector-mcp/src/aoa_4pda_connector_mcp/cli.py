from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .core import AoA4PDAConnectorMCPState


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(prog="aoa-4pda-connector-mcp")
    parser.add_argument("--connector-repo", default=None)
    parser.add_argument("--connector-bin", default=None)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--cache-root", default=None)
    parser.add_argument("--artifact-root", default=None)
    parser.add_argument("--default-run", default=None)
    parser.add_argument("--timeout", type=float, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.add_argument("--run", default=None)

    sub.add_parser("source-route")

    answer = sub.add_parser("answer")
    answer.add_argument("query")
    answer.add_argument("--run", default=None)
    answer.add_argument("--limit", type=int, default=5)

    query_graph = sub.add_parser("query-graph")
    query_graph.add_argument("query")
    query_graph.add_argument("--run", default=None)
    query_graph.add_argument("--limit", type=int, default=5)

    query_hybrid = sub.add_parser("query-hybrid")
    query_hybrid.add_argument("query")
    query_hybrid.add_argument("--run", default=None)
    query_hybrid.add_argument("--limit", type=int, default=5)

    resource = sub.add_parser("read-resource")
    resource.add_argument("uri")

    args = parser.parse_args()
    state = AoA4PDAConnectorMCPState.discover(
        connector_repo=Path(args.connector_repo) if args.connector_repo else None,
        connector_bin=args.connector_bin,
        data_root=Path(args.data_root) if args.data_root else None,
        cache_root=Path(args.cache_root) if args.cache_root else None,
        artifact_root=Path(args.artifact_root) if args.artifact_root else None,
        default_run=args.default_run,
        timeout_seconds=args.timeout,
    )

    if args.command == "status":
        _print(state.status(run=args.run))
    elif args.command == "source-route":
        _print(state.source_route())
    elif args.command == "answer":
        _print(state.answer(query=args.query, run=args.run, limit=args.limit))
    elif args.command == "query-graph":
        _print(state.query_graph(query=args.query, run=args.run, limit=args.limit))
    elif args.command == "query-hybrid":
        _print(state.query_hybrid(query=args.query, run=args.run, limit=args.limit))
    elif args.command == "read-resource":
        _print(state.read_resource(args.uri))


if __name__ == "__main__":
    main()
