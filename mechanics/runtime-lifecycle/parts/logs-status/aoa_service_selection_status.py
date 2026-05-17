#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_STACK_ROOT = Path("/srv/AbyssOS/abyss-stack")


def run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def parse_key_value_tokens(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for token in shlex.split(value):
        key, separator, raw_value = token.partition("=")
        if separator and key:
            parsed[key] = raw_value
    return parsed


def read_unit_environment() -> dict[str, str]:
    result = run_command(
        [
            "systemctl",
            "--user",
            "show",
            "podman-compose-abyss.service",
            "-p",
            "Environment",
        ]
    )
    if result.returncode != 0:
        return {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key == "Environment":
            return parse_key_value_tokens(value)
    return {}


def runtime_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update(read_unit_environment())
    stack_root = Path(env.get("AOA_STACK_ROOT", str(DEFAULT_STACK_ROOT)))
    env.setdefault("AOA_STACK_ROOT", str(stack_root))
    env.setdefault("AOA_CONFIGS_ROOT", str(stack_root / "Configs"))
    env.setdefault("AOA_COMPOSE_PROJECT_NAME", "abyss")
    return env


def load_policy(configs_root: Path) -> dict[str, Any]:
    policy_path = configs_root / "docs" / "runtime" / "service-selection-policy.v1.json"
    return json.loads(policy_path.read_text(encoding="utf-8"))


def inspect_compose_containers(project_name: str) -> list[dict[str, Any]]:
    ps = run_command(["podman", "ps", "-a", "--format", "{{.ID}}"])
    if ps.returncode != 0:
        return []
    container_ids = [line.strip() for line in ps.stdout.splitlines() if line.strip()]
    if not container_ids:
        return []

    inspected = run_command(["podman", "inspect", *container_ids])
    if inspected.returncode != 0:
        return []

    try:
        containers = json.loads(inspected.stdout)
    except json.JSONDecodeError:
        return []

    selected: list[dict[str, Any]] = []
    for container in containers:
        labels = container.get("Config", {}).get("Labels") or {}
        if labels.get("com.docker.compose.project") != project_name:
            continue
        service = labels.get("com.docker.compose.service") or labels.get(
            "io.podman.compose.service", ""
        )
        state = container.get("State") or {}
        selected.append(
            {
                "name": container.get("Name", "").lstrip("/"),
                "service": service,
                "state": state.get("Status", ""),
            }
        )
    return sorted(selected, key=lambda item: (item["service"], item["name"]))


def classify_service(policy_entry: dict[str, Any], live: dict[str, Any] | None) -> str:
    posture = policy_entry.get("posture")
    running = live is not None and live.get("state") == "running"
    if posture == "selected_now":
        return "running_selected" if running else "missing_selected"
    if running:
        return "unexpected_running"
    return "not_running_expected"


def summarize_service_selection(counts: dict[str, int], service_count: int) -> dict[str, Any]:
    if counts.get("missing_selected"):
        overall = "missing_selected"
    elif counts.get("unexpected_running") or counts.get("unknown_running"):
        overall = "unexpected_running"
    else:
        overall = "ok"

    return {
        "status": overall,
        "services": service_count,
        "running_selected": counts.get("running_selected", 0),
        "missing_selected": counts.get("missing_selected", 0),
        "unexpected_running": counts.get("unexpected_running", 0),
        "unknown_running": counts.get("unknown_running", 0),
        "not_running_expected": counts.get("not_running_expected", 0),
        "counts": counts,
    }


def build_status() -> dict[str, Any]:
    env = runtime_environment()
    configs_root = Path(env["AOA_CONFIGS_ROOT"])
    project_name = env["AOA_COMPOSE_PROJECT_NAME"]
    policy = load_policy(configs_root)
    policy_services = {
        str(entry.get("name")): entry
        for entry in policy.get("services", [])
        if isinstance(entry, dict) and entry.get("name")
    }
    live_containers = inspect_compose_containers(project_name)
    live_by_service = {
        str(container.get("service")): container
        for container in live_containers
        if container.get("service")
    }

    service_status: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for service_name, entry in sorted(policy_services.items()):
        live = live_by_service.get(service_name)
        status = classify_service(entry, live)
        counts[status] = counts.get(status, 0) + 1
        service_status.append(
            {
                "service": service_name,
                "posture": entry.get("posture"),
                "tier": entry.get("tier"),
                "owner_profile": entry.get("owner_profile"),
                "decision": entry.get("decision"),
                "live": live,
                "status": status,
            }
        )

    unknown_running: list[dict[str, Any]] = []
    for service_name, live in sorted(live_by_service.items()):
        if service_name not in policy_services and live.get("state") == "running":
            unknown_running.append(live)
    if unknown_running:
        counts["unknown_running"] = len(unknown_running)

    return {
        "surface_type": "service_selection_status",
        "schema_version": "v1",
        "policy_schema": policy.get("schema"),
        "selection": {
            "preset": env.get("AOA_STACK_PRESET", ""),
            "profile": env.get("AOA_STACK_PROFILE", ""),
            "compose_project_name": project_name,
            "configs_root": str(configs_root),
        },
        "summary": summarize_service_selection(counts, len(service_status)),
        "services": service_status,
        "unknown_running": unknown_running,
    }


def print_text(status: dict[str, Any]) -> None:
    summary = status["summary"]
    selection = status["selection"]
    print(f"service selection: {summary['status']}")
    print(f"preset: {selection.get('preset') or '(none)'}")
    print(f"profile: {selection.get('profile') or '(none)'}")
    print("")
    for item in status["services"]:
        if item["status"] in {"missing_selected", "unexpected_running"}:
            live_state = (item.get("live") or {}).get("state", "missing")
            print(
                "- {service}: {status} posture={posture} live={live_state}".format(
                    service=item["service"],
                    status=item["status"],
                    posture=item.get("posture"),
                    live_state=live_state,
                )
            )
    if status.get("unknown_running"):
        for item in status["unknown_running"]:
            print(f"- {item.get('service')}: unknown_running live={item.get('state')}")
    if summary["status"] == "ok":
        print("all selected services are running; opt-in, fallback, and lab services are not unexpectedly running")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare live compose services with service-selection-policy.v1.json.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    try:
        status = build_status()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print_text(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
