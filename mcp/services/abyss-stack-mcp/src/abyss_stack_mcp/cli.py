from __future__ import annotations

import argparse
import json

from .core import ObservationStore, StackMCPApplication
from .orchestration import CrossOrganRunStore


def main() -> None:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp")
    parser.add_argument("--observation-path")
    parser.add_argument("--orchestration-root")
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
        choices=("read",),
    )
    catalog.add_argument("--max-results", type=int, default=32)
    catalog.add_argument("--byte-budget", type=int, default=32_768)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("organ_id")
    inspect.add_argument(
        "target_policy_family",
        choices=("read",),
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
            "proof",
            "acceptance",
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

    orchestration = sub.add_parser("orchestration-inspect")
    orchestration.add_argument("--run-id")

    args = parser.parse_args()
    expected_contour = "candidate" if args.command == "plan" else "read"
    if args.policy_family != expected_contour:
        parser.error(
            f"{args.command} requires --policy-family {expected_contour}"
        )
    application = StackMCPApplication(
        ObservationStore(args.observation_path),
        policy_family=args.policy_family,
        orchestration_store=CrossOrganRunStore(args.orchestration_root),
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
    elif args.command == "orchestration-inspect":
        result = application.inspect_orchestration(args.run_id)
    else:
        result = application.prepare_plan(
            args.organ_id,
            args.target_policy_family,
            args.plan_kind,
            expected_observation_digest=args.expected_observation_digest,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
