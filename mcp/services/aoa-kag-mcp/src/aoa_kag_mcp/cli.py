from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .core import AoAKagMCPState


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(prog="aoa-kag-mcp")
    parser.add_argument("--workspace-root", default=None)
    parser.add_argument("--aoa-kag-root", default=None)
    parser.add_argument("--provider-map-path", default=None)
    parser.add_argument("--readiness-path", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    provider_status = sub.add_parser("provider-status")
    provider_status.add_argument("--repo")

    provider = sub.add_parser("provider")
    provider.add_argument("repo")

    freshness = sub.add_parser("freshness")
    freshness.add_argument("--repo")

    source_return = sub.add_parser("source-return")
    source_return.add_argument("repo")
    source_return.add_argument("--local-id")
    source_return.add_argument("--path")

    repo_local_index = sub.add_parser("repo-local-index")
    repo_local_index.add_argument("repo")

    source_index = sub.add_parser("source-index")
    source_index.add_argument("repo")
    source_index.add_argument("--include-payload", action="store_true")

    common_surface_profile = sub.add_parser("common-surface-profile")
    common_surface_profile.add_argument("repo")

    registry = sub.add_parser("registry-slice")
    registry.add_argument("--status")
    registry.add_argument("--repo")
    registry.add_argument("--limit", type=int, default=50)

    composition = sub.add_parser("composition-slice")
    composition.add_argument("--query", default="")
    composition.add_argument("--limit", type=int, default=20)

    validation = sub.add_parser("validation-status")
    validation.add_argument("--include-provider-homes", action="store_true")

    resource = sub.add_parser("read-resource")
    resource.add_argument("uri")

    args = parser.parse_args()
    state = AoAKagMCPState.discover(
        workspace_root=args.workspace_root,
        aoa_kag_root=args.aoa_kag_root,
        provider_map_path=Path(args.provider_map_path) if args.provider_map_path else None,
        readiness_path=Path(args.readiness_path) if args.readiness_path else None,
    )

    if args.command == "status":
        _print(state.status())
    elif args.command == "provider-status":
        _print(state.provider_status(repo=args.repo))
    elif args.command == "provider":
        _print(state.provider_lookup(repo=args.repo))
    elif args.command == "freshness":
        _print(state.freshness_check(repo=args.repo))
    elif args.command == "source-return":
        _print(state.source_return_lookup(repo=args.repo, local_id=args.local_id, path=args.path))
    elif args.command == "repo-local-index":
        _print(state.repo_local_index(repo=args.repo))
    elif args.command == "source-index":
        _print(state.source_index_status(repo=args.repo, include_payload=args.include_payload))
    elif args.command == "common-surface-profile":
        _print(state.common_surface_profile(repo=args.repo))
    elif args.command == "registry-slice":
        _print(state.registry_slice(status=args.status, repo=args.repo, limit=args.limit))
    elif args.command == "composition-slice":
        _print(state.composition_slice(query=args.query, limit=args.limit))
    elif args.command == "validation-status":
        _print(state.validation_status(include_provider_homes=args.include_provider_homes))
    elif args.command == "read-resource":
        _print(state.read_resource(args.uri))


if __name__ == "__main__":
    main()
