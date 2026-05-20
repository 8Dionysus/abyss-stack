from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .core import AoAMemoMCPState


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="aoa-memo-mcp")
    parser.add_argument("--workspace-root", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    brief = sub.add_parser("brief")
    brief.add_argument("--repo", required=True)
    brief.add_argument("--intent", default="")

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--scope", default="all")
    search.add_argument("--mode", default="brief")

    create = sub.add_parser("create-candidate")
    create.add_argument("--repo", required=True)
    create.add_argument("--claim", required=True)
    create.add_argument("--evidence-ref", action="append", required=True)
    create.add_argument("--source-trust", default="review_required")

    validate = sub.add_parser("validate-candidate")
    validate.add_argument("path")

    resource = sub.add_parser("read-resource")
    resource.add_argument("uri")

    args = parser.parse_args()
    state = AoAMemoMCPState.discover(args.workspace_root)

    if args.command == "brief":
        _print(state.build_brief(args.repo, args.intent))
    elif args.command == "search":
        _print(state.search(args.query, args.scope, args.mode))
    elif args.command == "create-candidate":
        _print(state.create_candidate(args.repo, args.evidence_ref, args.claim, source_trust=args.source_trust))
    elif args.command == "validate-candidate":
        _print(state.validate_candidate(Path(args.path)))
    elif args.command == "read-resource":
        _print(state.read_resource(args.uri))


if __name__ == "__main__":
    main()
