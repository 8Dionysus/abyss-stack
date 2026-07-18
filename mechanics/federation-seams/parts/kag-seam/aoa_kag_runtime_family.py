#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from kag_runtime.distribution import (
    DistributionError,
    activate_composition,
    distribution_status,
    load_trusted_composition,
    load_trusted_owner_family,
    materialize_owner_family,
    rollback_owner,
)


DEFAULT_STACK_ROOT = Path(os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack"))


def _runtime_root(stack_root: Path) -> Path:
    return stack_root.expanduser().resolve() / "Knowledge" / "kag" / "repo-self"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Hydrate trust-admitted content-addressed KAG families into the "
            "abyss-stack local CAS without network access."
        )
    )
    parser.add_argument("--stack-root", type=Path, default=DEFAULT_STACK_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    hydrate = subparsers.add_parser("hydrate-owner")
    hydrate.add_argument("--family-root", type=Path, required=True)
    hydrate.add_argument("--trust-gate", type=Path, required=True)
    hydrate.add_argument("--owner", required=True)
    hydrate.add_argument("--kind", action="append", default=[])
    hydrate.add_argument("--range-prefix", action="append", default=[])

    composition = subparsers.add_parser("activate-composition")
    composition.add_argument("--composition-root", type=Path, required=True)
    composition.add_argument("--trust-gate", type=Path, required=True)

    rollback = subparsers.add_parser("rollback-owner")
    rollback.add_argument("--owner", required=True)

    subparsers.add_parser("status")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime_root = _runtime_root(args.stack_root)
    try:
        if args.command == "hydrate-owner":
            family = load_trusted_owner_family(
                args.family_root,
                args.trust_gate,
                expected_owner=args.owner,
            )
            result = materialize_owner_family(
                family,
                runtime_root,
                kinds=args.kind,
                range_prefixes=args.range_prefix,
            )
        elif args.command == "activate-composition":
            composition, trust = load_trusted_composition(
                args.composition_root,
                args.trust_gate,
            )
            result = activate_composition(composition, trust, runtime_root)
        elif args.command == "rollback-owner":
            result = rollback_owner(runtime_root, args.owner)
        else:
            result = distribution_status(runtime_root)
    except DistributionError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "state": exc.state,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
