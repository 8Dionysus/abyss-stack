"""CLI wrapper for the Discord connector MCP service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aoa_discord_connector_mcp.core import AoADiscordConnectorMCPState


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aoa-discord-connector-mcp")
    parser.add_argument("--connector-repo", type=Path)
    parser.add_argument("--connector-bin")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--default-run", default=None)
    parser.add_argument("--timeout", type=float, default=None)

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("source-route")
    sub.add_parser("status")

    answer = sub.add_parser("answer")
    answer.add_argument("query")
    answer.add_argument("--run", default=None)
    answer.add_argument("--limit", type=int, default=5)

    graph = sub.add_parser("query-graph")
    graph.add_argument("query")
    graph.add_argument("--run", default=None)
    graph.add_argument("--limit", type=int, default=5)

    resource = sub.add_parser("read-resource")
    resource.add_argument("uri")
    return parser


def _state(args: argparse.Namespace) -> AoADiscordConnectorMCPState:
    discovered = AoADiscordConnectorMCPState.discover()
    return AoADiscordConnectorMCPState(
        connector_repo=args.connector_repo or discovered.connector_repo,
        connector_bin=args.connector_bin or discovered.connector_bin,
        data_root=args.data_root or discovered.data_root,
        cache_root=args.cache_root or discovered.cache_root,
        artifact_root=args.artifact_root or discovered.artifact_root,
        default_run=args.default_run or discovered.default_run,
        timeout=args.timeout or discovered.timeout,
    )


def _emit(packet: dict[str, Any]) -> None:
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    state = _state(args)
    if args.command == "source-route":
        packet = state.source_route()
    elif args.command == "status":
        packet = state.status()
    elif args.command == "answer":
        packet = state.answer(args.query, run=args.run, limit=args.limit)
    elif args.command == "query-graph":
        packet = state.query_graph(args.query, run=args.run, limit=args.limit)
    elif args.command == "read-resource":
        packet = state.read_resource(args.uri)
    else:
        parser.error(f"unknown command: {args.command}")
    _emit(packet)
    return 0 if packet.get("status", "ok") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
