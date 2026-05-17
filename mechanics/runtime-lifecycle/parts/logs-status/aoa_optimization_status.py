#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = SOURCE_ROOT / "scripts"


def run_json(argv: list[str], *, parse_json_on_error: bool = False) -> tuple[dict[str, Any] | None, str]:
    result = subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0 and not parse_json_on_error:
        return None, result.stderr.strip() or result.stdout.strip()
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        if result.returncode != 0:
            return None, result.stderr.strip() or result.stdout.strip() or str(exc)
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "payload is not a JSON object"
    return payload, ""


def summarize(
    service_selection: dict[str, Any] | None,
    resource_guards: dict[str, Any] | None,
    game_guard: dict[str, Any] | None,
    resource_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    service_status = (
        service_selection.get("summary", {}).get("status")
        if isinstance(service_selection, dict)
        else "unknown"
    )
    guard_status = (
        resource_guards.get("summary", {}).get("status")
        if isinstance(resource_guards, dict)
        else "unknown"
    )
    game_active = game_guard.get("active") if isinstance(game_guard, dict) else None
    resource_plan_ok = resource_plan.get("ok") if isinstance(resource_plan, dict) else None
    resource_plan_decision = resource_plan.get("decision") if isinstance(resource_plan, dict) else "unknown"
    resource_plan_blocked_reasons = (
        resource_plan.get("blocked_reasons", [])
        if isinstance(resource_plan, dict) and isinstance(resource_plan.get("blocked_reasons"), list)
        else []
    )

    if service_status != "ok":
        status = "service_selection_degraded"
        apply_allowed = False
        next_action = "inspect service selection before applying resource guards"
    elif guard_status == "applied":
        status = "ok"
        apply_allowed = False
        next_action = "no resource-guard apply needed"
    elif guard_status == "staged_not_applied" and game_active is True:
        status = "blocked_by_game_guard"
        apply_allowed = False
        next_action = "run scripts/aoa-apply-resource-guards --wait-game-guard-clear --wait-resource-plan-clear for supervised safe-window apply, or wait for the gates to clear and run the default recreate apply"
    elif guard_status == "staged_not_applied" and game_active is False and resource_plan_ok is False:
        status = "blocked_by_resource_plan"
        apply_allowed = False
        next_action = "wait for abyss-machine resource plan to allow medium generic unattended work, then run the default recreate apply"
    elif guard_status == "staged_not_applied" and game_active is False:
        status = "ready_to_apply"
        apply_allowed = True
        next_action = "run scripts/aoa-apply-resource-guards (default recreate)"
    elif guard_status == "staged_not_applied":
        status = "blocked_by_unknown_game_guard"
        apply_allowed = False
        next_action = "inspect abyss-machine processes game-guard --json"
    else:
        status = "resource_guard_degraded"
        apply_allowed = False
        next_action = "inspect scripts/aoa-status --resource-guards"

    return {
        "status": status,
        "apply_allowed": apply_allowed,
        "service_selection_status": service_status,
        "resource_guard_status": guard_status,
        "game_guard_active": game_active,
        "resource_plan_ok": resource_plan_ok,
        "resource_plan_decision": resource_plan_decision,
        "resource_plan_blocked_reasons": resource_plan_blocked_reasons,
        "next_action": next_action,
    }


def build_status() -> dict[str, Any]:
    service_selection, service_error = run_json(
        [str(SCRIPTS_DIR / "aoa-status"), "--service-selection", "--json"]
    )
    resource_guards, resource_error = run_json(
        [str(SCRIPTS_DIR / "aoa-status"), "--resource-guards", "--json"]
    )
    game_guard, game_error = run_json(["abyss-machine", "processes", "game-guard", "--json"])
    resource_plan, resource_plan_error = run_json(
        [
            "abyss-machine",
            "resource",
            "plan",
            "--class",
            "medium",
            "--kind",
            "generic",
            "--unattended",
            "--no-thermal-sample",
            "--json",
        ],
        parse_json_on_error=True,
    )

    summary = summarize(service_selection, resource_guards, game_guard, resource_plan)
    return {
        "surface_type": "optimization_status",
        "schema_version": "v1",
        "summary": summary,
        "service_selection": service_selection,
        "resource_guards": resource_guards,
        "game_guard": game_guard,
        "resource_plan": resource_plan,
        "errors": {
            "service_selection": service_error,
            "resource_guards": resource_error,
            "game_guard": game_error,
            "resource_plan": resource_plan_error,
        },
    }


def print_text(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print(f"optimization: {summary['status']}")
    print(f"service selection: {summary['service_selection_status']}")
    print(f"resource guards: {summary['resource_guard_status']}")
    print(f"game guard active: {summary['game_guard_active']}")
    print(f"resource plan ok: {summary['resource_plan_ok']}")
    if summary.get("resource_plan_blocked_reasons"):
        print("resource plan blocked: " + ", ".join(summary["resource_plan_blocked_reasons"]))
    print(f"apply allowed: {summary['apply_allowed']}")
    print(f"next: {summary['next_action']}")

    resource_guards = payload.get("resource_guards") or {}
    counts = resource_guards.get("summary", {}).get("counts", {})
    if counts:
        print(
            "guard counts: applied={applied} staged={staged}".format(
                applied=counts.get("applied", 0),
                staged=counts.get("staged_not_applied", 0),
            )
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize service selection, resource guards, and game guard apply readiness.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    payload = build_status()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
