#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STACK_ROOT = Path("/srv/AbyssOS/abyss-stack")


def run_command(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=check,
        env=env,
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


def read_user_unit_state() -> dict[str, Any]:
    result = run_command(
        [
            "systemctl",
            "--user",
            "show",
            "podman-compose-abyss.service",
            "-p",
            "ActiveState",
            "-p",
            "SubState",
            "-p",
            "Environment",
        ]
    )
    state: dict[str, Any] = {
        "available": result.returncode == 0,
        "active_state": "",
        "sub_state": "",
        "environment": {},
        "error": result.stderr.strip(),
    }
    if result.returncode != 0:
        return state

    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        if key == "Environment":
            state["environment"] = parse_key_value_tokens(value)
        elif key == "ActiveState":
            state["active_state"] = value
        elif key == "SubState":
            state["sub_state"] = value
    return state


def runtime_environment(unit_state: dict[str, Any]) -> dict[str, str]:
    merged = os.environ.copy()
    unit_env = unit_state.get("environment")
    if isinstance(unit_env, dict):
        merged.update({str(key): str(value) for key, value in unit_env.items()})

    stack_root = Path(merged.get("AOA_STACK_ROOT", str(DEFAULT_STACK_ROOT)))
    merged.setdefault("AOA_STACK_ROOT", str(stack_root))
    merged.setdefault("AOA_CONFIGS_ROOT", str(stack_root / "Configs"))
    return merged


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def strip_yaml_scalar(value: str) -> str:
    value = value.strip()
    if "#" in value:
        value = value.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def parse_rendered_services(rendered_yaml: str) -> dict[str, dict[str, str]]:
    services: dict[str, dict[str, str]] = {}
    in_services = False
    current_service = ""

    service_pattern = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
    field_pattern = re.compile(r"^    (cpus|mem_limit|mem_reservation):\s*(.+?)\s*$")

    for line in rendered_yaml.splitlines():
        if line == "services:":
            in_services = True
            current_service = ""
            continue
        if not in_services:
            continue
        if line and not line.startswith(" "):
            break

        service_match = service_pattern.match(line)
        if service_match:
            current_service = service_match.group(1)
            services.setdefault(current_service, {})
            continue

        if not current_service:
            continue
        field_match = field_pattern.match(line)
        if field_match:
            services[current_service][field_match.group(1)] = strip_yaml_scalar(
                field_match.group(2)
            )

    return services


def render_compose_config(env: dict[str, str]) -> tuple[str, str]:
    configs_root = Path(env["AOA_CONFIGS_ROOT"])
    render_script = configs_root / "scripts" / "aoa-render-config"
    if not render_script.exists():
        render_script = SOURCE_ROOT / "scripts" / "aoa-render-config"
    result = run_command([str(render_script)], env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout, result.stderr


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
        host_config = container.get("HostConfig") or {}
        state = container.get("State") or {}
        selected.append(
            {
                "name": container.get("Name", "").lstrip("/"),
                "service": service,
                "state": state.get("Status", ""),
                "mem_limit_bytes": int(host_config.get("Memory") or 0),
                "nano_cpus": int(host_config.get("NanoCpus") or 0),
            }
        )
    return sorted(selected, key=lambda item: (item["service"], item["name"]))


def parse_compose_memory_bytes(value: str | None) -> int:
    if not value:
        return 0

    match = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)?)\s*([kmgt]?)(?:i?b)?",
        value.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"unsupported compose memory value: {value!r}")

    amount = Decimal(match.group(1))
    exponent = {"": 0, "k": 1, "m": 2, "g": 3, "t": 4}[match.group(2).lower()]
    return int(amount * (1024**exponent))


def parse_compose_cpus_nano(value: str | None) -> int:
    if not value:
        return 0
    try:
        amount = Decimal(value.strip())
    except InvalidOperation as exc:
        raise ValueError(f"unsupported compose cpu value: {value!r}") from exc
    if amount < 0:
        raise ValueError(f"compose cpu value must not be negative: {value!r}")
    return int(amount * 1_000_000_000)


def classify_guard(expected: dict[str, str], live: dict[str, Any] | None) -> str:
    if live is None:
        return "missing_live_container"

    expected_memory_bytes = parse_compose_memory_bytes(expected.get("mem_limit"))
    expected_nano_cpus = parse_compose_cpus_nano(expected.get("cpus"))
    memory_applied = int(live.get("mem_limit_bytes") or 0) == expected_memory_bytes
    cpu_applied = int(live.get("nano_cpus") or 0) == expected_nano_cpus

    if memory_applied and cpu_applied:
        return "applied"
    return "staged_not_applied"


def summarize_guard_status(service_status: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for item in service_status:
        status = str(item["guard_status"])
        counts[status] = counts.get(status, 0) + 1

    if counts.get("missing_live_container"):
        overall = "missing_live_container"
    elif counts.get("staged_not_applied"):
        overall = "staged_not_applied"
    else:
        overall = "applied"

    return {
        "status": overall,
        "guarded_services": len(service_status),
        "applied": counts.get("applied", 0),
        "staged_not_applied": counts.get("staged_not_applied", 0),
        "missing_live_container": counts.get("missing_live_container", 0),
        "counts": counts,
    }


def build_status() -> dict[str, Any]:
    unit_state = read_user_unit_state()
    env = runtime_environment(unit_state)
    rendered, render_stderr = render_compose_config(env)
    rendered_services = parse_rendered_services(rendered)
    guarded_services = {
        service: fields
        for service, fields in rendered_services.items()
        if fields.get("mem_limit") or fields.get("cpus")
    }

    project_name = env.get("AOA_COMPOSE_PROJECT_NAME", "abyss")
    live_containers = inspect_compose_containers(project_name)
    live_by_service = {
        str(container.get("service")): container
        for container in live_containers
        if container.get("service")
    }

    service_status: list[dict[str, Any]] = []
    for service, expected in sorted(guarded_services.items()):
        live = live_by_service.get(service)
        service_status.append(
            {
                "service": service,
                "expected": expected,
                "live": live,
                "guard_status": classify_guard(expected, live),
            }
        )

    return {
        "surface_type": "resource_guard_status",
        "schema_version": "v1",
        "unit": unit_state,
        "selection": {
            "preset": env.get("AOA_STACK_PRESET", ""),
            "profile": env.get("AOA_STACK_PROFILE", ""),
            "extra_compose_files": split_csv(env.get("AOA_EXTRA_COMPOSE_FILES", "")),
            "compose_project_name": project_name,
            "configs_root": env.get("AOA_CONFIGS_ROOT", ""),
        },
        "summary": summarize_guard_status(service_status),
        "services": service_status,
        "live_containers": live_containers,
        "render_stderr": render_stderr.strip(),
    }


def print_text(status: dict[str, Any]) -> None:
    summary = status["summary"]
    selection = status["selection"]
    unit = status["unit"]
    print(f"resource guards: {summary['status']}")
    print(f"unit: {unit.get('active_state', '')}/{unit.get('sub_state', '')}")
    print(f"preset: {selection.get('preset') or '(none)'}")
    print(f"profile: {selection.get('profile') or '(none)'}")
    print("extra compose files:")
    for item in selection.get("extra_compose_files") or []:
        print(f"- {item}")
    if not selection.get("extra_compose_files"):
        print("- (none)")

    print("")
    print("guarded services:")
    for item in status["services"]:
        expected = item["expected"]
        live = item.get("live") or {}
        mem_live = live.get("mem_limit_bytes", "missing")
        cpu_live = live.get("nano_cpus", "missing")
        print(
            "- {service}: {guard_status} "
            "(expected mem={mem_expected}, cpus={cpu_expected}; "
            "live mem_bytes={mem_live}, nano_cpus={cpu_live})".format(
                service=item["service"],
                guard_status=item["guard_status"],
                mem_expected=expected.get("mem_limit", "(none)"),
                cpu_expected=expected.get("cpus", "(none)"),
                mem_live=mem_live,
                cpu_live=cpu_live,
            )
        )

    if summary["status"] == "staged_not_applied":
        print("")
        print("next: restart or reload podman-compose-abyss.service in a controlled window")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect staged and live compose resource guards.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    try:
        status = build_status()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print_text(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
