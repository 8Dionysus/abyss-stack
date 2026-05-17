from __future__ import annotations

from pathlib import Path
from typing import Any


def scalar_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_compose_services(path: Path) -> dict[str, Any]:
    services: dict[str, Any] = {}
    in_services = False
    current_service: dict[str, Any] | None = None
    current_key: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.strip() == "services:":
            in_services = True
            continue
        if not in_services:
            continue
        if raw and not raw.startswith(" "):
            break
        if raw.startswith("  ") and not raw.startswith("    ") and raw.strip().endswith(":"):
            name = raw.strip()[:-1]
            current_service = {}
            services[name] = current_service
            current_key = None
            continue
        if current_service is None:
            continue
        if raw.startswith("    ") and not raw.startswith("      "):
            key, _, value = raw.strip().partition(":")
            current_key = key
            current_service[key] = scalar_value(value) if value.strip() else {}
            continue
        if current_key is None:
            continue
        if raw.startswith("      - "):
            if not isinstance(current_service.get(current_key), list):
                current_service[current_key] = []
            current_service[current_key].append(scalar_value(raw.strip()[2:].strip()))
            continue
        if raw.startswith("      ") and not raw.startswith("        "):
            key, _, value = raw.strip().partition(":")
            if not isinstance(current_service.get(current_key), dict):
                current_service[current_key] = {}
            current_service[current_key][key] = scalar_value(value)
    return {"services": services}
