from __future__ import annotations

import argparse
import json

from .core import ObservationStore, StackMCPApplication


def main() -> None:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp")
    parser.add_argument("--observation-path")
    parser.add_argument(
        "--policy-family",
        choices=("read", "candidate"),
        default="read",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog")
    catalog.add_argument("--organ-id")
    catalog.add_argument(
        "--target-policy-family",
        choices=("read", "candidate", "internal_effect", "external_effect"),
    )
    catalog.add_argument("--max-results", type=int, default=32)
    catalog.add_argument("--byte-budget", type=int, default=32_768)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("organ_id")
    inspect.add_argument(
        "target_policy_family",
        choices=("read", "candidate", "internal_effect", "external_effect"),
    )
    inspect.add_argument(
        "--view",
        choices=(
            "identity",
            "parity",
            "process",
            "endpoint",
            "registry",
            "consumer",
            "schema",
            "freshness",
            "canary",
            "rollback",
            "drift",
            "full",
        ),
        default="identity",
    )

    plan = sub.add_parser("plan")
    plan.add_argument("organ_id")
    plan.add_argument(
        "target_policy_family",
        choices=("read", "candidate", "internal_effect", "external_effect"),
    )
    plan.add_argument(
        "plan_kind",
        choices=("sync", "deploy", "activate", "restart", "rollback"),
    )
    plan.add_argument("--expected-observation-digest", required=True)

    args = parser.parse_args()
    application = StackMCPApplication(
        ObservationStore(args.observation_path),
        policy_family=args.policy_family,
    )
    if args.command == "catalog":
        result = application.catalog(
            organ_id=args.organ_id,
            policy_family=args.target_policy_family,
            max_results=args.max_results,
            byte_budget=args.byte_budget,
        )
    elif args.command == "inspect":
        result = application.inspect(
            args.organ_id,
            args.target_policy_family,
            view=args.view,
        )
    else:
        result = application.prepare_plan(
            args.organ_id,
            args.target_policy_family,
            args.plan_kind,
            expected_observation_digest=args.expected_observation_digest,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
