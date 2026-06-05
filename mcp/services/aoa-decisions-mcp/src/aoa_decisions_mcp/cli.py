from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .core import AoADecisionsMCPState


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(prog="aoa-decisions-mcp")
    parser.add_argument("--workspace-root", default=None)
    parser.add_argument("--stack-root", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--no-stack-repo", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    sub.add_parser("summary")

    refresh = sub.add_parser("refresh")
    refresh.add_argument("--force", action="store_true")

    repo_cmd = sub.add_parser("repo")
    repo_cmd.add_argument("repo")

    decision = sub.add_parser("decision")
    decision.add_argument("decision_id")
    decision.add_argument("--repo")

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--repo")
    search.add_argument("--limit", type=int, default=20)

    packet = sub.add_parser("packet")
    packet.add_argument("--query", default="")
    packet.add_argument("--repo")
    packet.add_argument("--decision-id")
    packet.add_argument("--path")
    packet.add_argument("--limit", type=int, default=12)

    resource = sub.add_parser("read-resource")
    resource.add_argument("uri")

    args = parser.parse_args()
    state = AoADecisionsMCPState.discover(
        workspace_root=args.workspace_root,
        stack_root=args.stack_root,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        include_stack_repo=not args.no_stack_repo,
    )

    if args.command == "status":
        _print(state.ensure_fresh())
    elif args.command == "summary":
        _print(state.summary())
    elif args.command == "refresh":
        _print(state.ensure_fresh(force=args.force))
    elif args.command == "repo":
        _print(state.repo(args.repo))
    elif args.command == "decision":
        _print(state.decision(args.decision_id, repo=args.repo))
    elif args.command == "search":
        _print(state.search(args.query, repo=args.repo, limit=args.limit))
    elif args.command == "packet":
        _print(
            state.packet(
                query=args.query,
                repo=args.repo,
                decision_id=args.decision_id,
                path=args.path,
                limit=args.limit,
            )
        )
    elif args.command == "read-resource":
        _print(state.read_resource(args.uri))


if __name__ == "__main__":
    main()
