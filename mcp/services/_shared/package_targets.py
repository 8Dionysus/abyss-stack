"""Discover standalone MCP package targets from their source layout."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PackageTarget:
    service_id: str
    service_root: Path
    package: str
    package_name: str
    package_version: str


def discover_package_targets(services_root: Path) -> tuple[PackageTarget, ...]:
    targets: list[PackageTarget] = []
    for pyproject in sorted(services_root.glob("*/pyproject.toml")):
        service_root = pyproject.parent
        service_id = service_root.name
        payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = payload.get("project")
        if not isinstance(project, dict):
            raise ValueError(f"{pyproject} lacks [project]")
        package_name = project.get("name")
        package_version = project.get("version")
        if not isinstance(package_name, str) or not package_name:
            raise ValueError(f"{pyproject} has no project.name")
        if not isinstance(package_version, str) or not package_version:
            raise ValueError(f"{pyproject} has no project.version")
        package_dirs = sorted(
            path
            for path in (service_root / "src").iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        )
        if len(package_dirs) != 1:
            raise ValueError(
                f"{service_id} must expose exactly one standalone src package; "
                f"found {[path.name for path in package_dirs]}"
            )
        targets.append(
            PackageTarget(
                service_id=service_id,
                service_root=service_root,
                package=package_dirs[0].name,
                package_name=package_name,
                package_version=package_version,
            )
        )
    if not targets:
        raise ValueError(f"no MCP package targets found below {services_root}")
    return tuple(targets)
