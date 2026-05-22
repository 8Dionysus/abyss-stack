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
    create.add_argument("--source-ref", action="append")
    create.add_argument("--source-trust", default="review_required")
    create.add_argument("--kind", default="route")
    create.add_argument("--family", default="memory-access")
    create.add_argument("--scope", default="repo")

    validate = sub.add_parser("validate-candidate")
    validate.add_argument("path")

    build_index = sub.add_parser("build-port-index")
    build_index.add_argument("--repo", required=True)
    build_index.add_argument("--write", action="store_true")
    build_index.add_argument("--check", action="store_true")

    validate_port = sub.add_parser("validate-port")
    validate_port.add_argument("--repo", required=True)

    prepare = sub.add_parser("prepare-intake")
    prepare.add_argument("--repo", required=True)
    prepare.add_argument("--candidate-ref", action="append", required=True)
    prepare.add_argument("--receipt-ref", action="append")

    review = sub.add_parser("review-intake")
    review.add_argument("path")

    pending = sub.add_parser("pending-exports")
    pending.add_argument("--repo", required=True)

    landing_plan = sub.add_parser("landing-plan")
    landing_plan.add_argument("--repo", required=True)
    landing_plan.add_argument("--export-ref", required=True)
    landing_plan.add_argument("--object-kind", default="decision")
    landing_plan.add_argument("--slug")
    landing_plan.add_argument("--title")
    landing_plan.add_argument("--summary")
    landing_plan.add_argument("--reviewed-at")
    landing_plan.add_argument("--run-dry-run", action="store_true")

    resource = sub.add_parser("read-resource")
    resource.add_argument("uri")

    args = parser.parse_args()
    state = AoAMemoMCPState.discover(args.workspace_root)

    if args.command == "brief":
        _print(state.build_brief(args.repo, args.intent))
    elif args.command == "search":
        _print(state.search(args.query, args.scope, args.mode))
    elif args.command == "create-candidate":
        _print(
            state.create_candidate(
                args.repo,
                args.evidence_ref,
                args.claim,
                source_trust=args.source_trust,
                kind=args.kind,
                family=args.family,
                scope=args.scope,
                source_refs=args.source_ref,
            )
        )
    elif args.command == "validate-candidate":
        _print(state.validate_candidate(Path(args.path)))
    elif args.command == "build-port-index":
        _print(state.build_port_index(args.repo, write=args.write, check=args.check))
    elif args.command == "validate-port":
        _print(state.validate_port(args.repo))
    elif args.command == "prepare-intake":
        _print(state.prepare_intake_packet(args.repo, args.candidate_ref, args.receipt_ref))
    elif args.command == "review-intake":
        _print(state.review_intake(args.path))
    elif args.command == "pending-exports":
        _print(state.list_pending_exports(args.repo))
    elif args.command == "landing-plan":
        _print(
            state.build_landing_plan(
                args.repo,
                args.export_ref,
                object_kind=args.object_kind,
                slug=args.slug,
                title=args.title,
                summary=args.summary,
                reviewed_at=args.reviewed_at,
                run_dry_run=args.run_dry_run,
            )
        )
    elif args.command == "read-resource":
        _print(state.read_resource(args.uri))


if __name__ == "__main__":
    main()
