from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .core import AoAStatsMCPState, StatsAccessError


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _source_root_map(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        repo, separator, path = value.partition("=")
        if not separator or not repo or not path:
            raise StatsAccessError("--source-root must use REPO=PATH")
        roots[repo] = Path(path)
    return roots


def _stdin_request() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise StatsAccessError(f"packet-check stdin is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise StatsAccessError("packet-check stdin must be an object")
    contract = payload.get("contract")
    packet = payload.get("packet")
    if not isinstance(contract, dict) or not isinstance(packet, dict):
        raise StatsAccessError("packet-check requires object contract and packet fields")
    return contract, packet


def _main() -> None:
    parser = argparse.ArgumentParser(prog="aoa-stats-mcp")
    parser.add_argument("--workspace-root")
    parser.add_argument("--aoa-stats-root")
    parser.add_argument("--source-root", action="append", default=[])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("catalog")
    sub.add_parser("boundary-rules")

    surface = sub.add_parser("surface-read")
    selector = surface.add_mutually_exclusive_group(required=True)
    selector.add_argument("--surface-name")
    selector.add_argument("--surface-ref")
    surface.add_argument("--mode", choices=("preview", "full"), default="preview")
    surface.add_argument("--limit", type=int, default=5)

    owner = sub.add_parser("owner-port")
    owner.add_argument("repo", nargs="?")
    owner.add_argument("--measurement-id")

    sub.add_parser("packet-check")

    args = parser.parse_args()
    state = AoAStatsMCPState.discover(
        workspace_root=args.workspace_root,
        aoa_stats_root=args.aoa_stats_root,
        source_roots=_source_root_map(args.source_root),
    )

    if args.command == "catalog":
        _print(state.catalog())
    elif args.command == "boundary-rules":
        _print(state.boundary_rules())
    elif args.command == "surface-read":
        _print(
            state.surface_read(
                surface_name=args.surface_name,
                surface_ref=args.surface_ref,
                mode=args.mode,
                limit=args.limit,
            )
        )
    elif args.command == "owner-port":
        _print(state.owner_port_read(repo=args.repo, measurement_id=args.measurement_id))
    elif args.command == "packet-check":
        contract, packet = _stdin_request()
        _print(state.packet_check(contract=contract, packet=packet))


def main() -> None:
    try:
        _main()
    except StatsAccessError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
