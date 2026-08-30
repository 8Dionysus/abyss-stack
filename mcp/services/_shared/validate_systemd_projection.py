#!/usr/bin/env python3
"""Validate the systemd MCP projection against the runtime catalog.

The unit files are host-specific deployment projections, so they may contain
canonical host paths.  Ports, contour policy, and read-bundle membership are
not independent configuration, however; this check makes drift fail closed.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Mapping

from build_mcp_bundle_unit import bundle_read_units, render_bundle_unit
from runtime_config import CONFIG_PATH, raw_config


REPO_ROOT = Path(__file__).resolve().parents[3]
SYSTEMD_ROOT = REPO_ROOT / "systemd" / "user"
_ENV_LINE = re.compile(r'^Environment="?([A-Z][A-Z0-9_]*)=([^"\n]*)"?$')


def _render(template: str, *, service_id: str, contour_id: str, organ_id: str, instance: str) -> str:
    try:
        return template.format(
            service_id=service_id,
            contour=contour_id.replace("_", "-"),
            organ=organ_id,
            instance=instance,
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid MCP systemd unit template: {template!r}") from exc


def _environment(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = _ENV_LINE.fullmatch(line)
        if match is not None:
            values[match.group(1)] = match.group(2)
    return values


def _unit_path(systemd_root: Path, unit: str) -> Path:
    path = systemd_root / unit
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"MCP systemd projection is not a regular file: {path}")
    return path


def _expected_units(payload: Mapping[str, Any]) -> dict[str, tuple[str, str, int]]:
    services = {
        str(service["service_id"]): service
        for service in payload["services"]
        if isinstance(service, Mapping)
    }
    deployment = payload["deployment"]
    expected: dict[str, tuple[str, str, int]] = {}

    for service_id, service in services.items():
        contours = service["contours"]
        read_unit = _render(
            str(service["read_unit_template"]),
            service_id=service_id,
            contour_id="read",
            organ_id=str(service["organ_id"]),
            instance=str(service["read_unit_instance"]),
        )
        read_port = int(contours["read"]["port"])
        expected[read_unit] = (service_id, "read", read_port)

        for item in deployment["nonread_probe_contours"]:
            if item["service_id"] != service_id:
                continue
            contour_id = str(item["contour_id"])
            unit = _render(
                str(deployment["contour_unit_template"]),
                service_id=service_id,
                contour_id=contour_id,
                organ_id=str(service["organ_id"]),
                instance=str(service["read_unit_instance"]),
            )
            expected[unit] = (service_id, contour_id, int(contours[contour_id]["port"]))

    # The stack read plane has bootstrap and fallback projections which share
    # the same declarative read contour.  Identify that service by its runtime
    # mode, not by a duplicated service-name convention.
    stack_reads = [
        (unit, identity)
        for unit, identity in expected.items()
        if identity[1] == "read"
        and services[identity[0]].get("runtime_executable_mode") == "stack_venv"
    ]
    if len(stack_reads) == 1:
        stack_unit, stack_identity = stack_reads[0]
        stem = stack_unit.removesuffix(".service")
        for suffix in ("-bootstrap.service", "-fallback.service"):
            expected[f"{stem}{suffix}"] = stack_identity
    return expected


def validate_systemd_projection(
    payload: Mapping[str, Any] | None = None,
    systemd_root: Path = SYSTEMD_ROOT,
) -> None:
    payload = payload or raw_config(CONFIG_PATH)
    expected = _expected_units(payload)
    transport = payload["mcp"]["transport"]
    port_env_var = str(transport["port_env_var"])
    host_env_var = str(transport["host_env_var"])
    direct_port_units: dict[str, tuple[str, str, int]] = {}
    for path in sorted(systemd_root.glob("*mcp*.service")):
        text = _unit_path(systemd_root, path.name).read_text(encoding="utf-8")
        environment = _environment(text)
        if port_env_var not in environment:
            continue
        try:
            port = int(environment[port_env_var])
        except ValueError as exc:
            raise ValueError(f"invalid {port_env_var} in {path.name}") from exc
        identity = expected.get(path.name)
        if identity is None:
            raise ValueError(
                f"systemd MCP unit has an unregistered direct port projection: {path.name}"
            )
        if port != identity[2]:
            raise ValueError(
                f"systemd MCP port drift in {path.name}: {port} != {identity[2]}"
            )
        policy = environment.get("ABYSS_STACK_MCP_POLICY_FAMILY") or environment.get(
            "AOA_MCP_POLICY_FAMILY"
        )
        if policy is not None and policy != identity[1]:
            raise ValueError(
                f"systemd MCP policy drift in {path.name}: {policy} != {identity[1]}"
            )
        host = environment.get(host_env_var)
        if host is not None and host != payload["mcp"]["transport"]["default_host"]:
            raise ValueError(f"systemd MCP host drift in {path.name}: {host}")
        direct_port_units[path.name] = identity

    for unit, identity in expected.items():
        # Generic owner units receive their port from the owner launcher and
        # intentionally have no direct MCP port line.  A unit with a
        # direct port must still be checked above.
        if unit.startswith("abyss-stack-mcp-") and unit not in direct_port_units:
            raise ValueError(f"stack MCP unit lacks a direct port projection: {unit}")
        if identity[1] != "read" and unit not in direct_port_units:
            raise ValueError(f"non-read MCP unit lacks a direct port projection: {unit}")

    bundle_path = _unit_path(systemd_root, "aoa-mcp-http.service")
    actual_bundle = bundle_path.read_text(encoding="utf-8")
    expected_bundle = render_bundle_unit(dict(payload))
    if actual_bundle != expected_bundle:
        raise ValueError("generated MCP read bundle is stale")
    bundle_units = set(bundle_read_units(dict(payload)))
    forbidden = {
        unit
        for unit, (_, contour_id, _) in expected.items()
        if contour_id != "read"
    }
    if bundle_units.intersection(forbidden):
        raise ValueError("MCP read bundle contains a candidate/effect unit")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--systemd-root", type=Path, default=SYSTEMD_ROOT)
    args = parser.parse_args()
    validate_systemd_projection(raw_config(args.runtime_config), args.systemd_root)
    print("[ok] MCP systemd projection matches the central runtime catalog")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
