from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from tests.compose_yaml_subset import load_compose_services


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = REPO_ROOT / "compose" / "modules"
PROFILE_DIR = REPO_ROOT / "compose" / "profiles"
PRESET_DIR = REPO_ROOT / "compose" / "presets"


def uncommented_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def load_compose(path: Path) -> dict[str, Any]:
    data = load_compose_services(path)
    if not isinstance(data, dict):
        raise AssertionError(f"{path} did not parse to a YAML mapping")
    return data


def service_ports(service: dict[str, Any]) -> list[Any]:
    ports = service.get("ports", [])
    return ports if isinstance(ports, list) else []


def resolved_modules(*profiles: str, preset: str | None = None) -> list[str]:
    seen_profiles: set[str] = set()
    profile_order: list[str] = []
    if preset is not None:
        for profile in uncommented_lines(PRESET_DIR / f"{preset}.txt"):
            if profile not in seen_profiles:
                seen_profiles.add(profile)
                profile_order.append(profile)
    for profile in profiles:
        if profile not in seen_profiles:
            seen_profiles.add(profile)
            profile_order.append(profile)

    seen_modules: set[str] = set()
    modules: list[str] = []
    for profile in profile_order:
        for module in uncommented_lines(PROFILE_DIR / f"{profile}.txt"):
            if module not in seen_modules:
                seen_modules.add(module)
                modules.append(module)
    return modules


class ComposeContractsTests(unittest.TestCase):
    def test_all_compose_modules_parse_as_service_maps(self) -> None:
        for path in sorted(MODULE_DIR.glob("*.yml")):
            with self.subTest(module=path.name):
                data = load_compose(path)
                services = data.get("services")
                self.assertIsInstance(services, dict)
                self.assertTrue(services, f"{path.name} has no services")

    def test_browser_helper_uses_container_init_reaper(self) -> None:
        service = load_compose(MODULE_DIR / "51-browser-tools.yml")["services"]["aoa-browser"]
        self.assertEqual(service.get("init"), "true")

    def test_host_published_ports_are_loopback_bound(self) -> None:
        for path in sorted(MODULE_DIR.glob("*.yml")):
            services = load_compose(path).get("services", {})
            for service_name, service in services.items():
                if not isinstance(service, dict):
                    continue
                for port in service_ports(service):
                    with self.subTest(module=path.name, service=service_name, port=port):
                        if isinstance(port, str):
                            self.assertTrue(
                                port.startswith("127.0.0.1:"),
                                f"{path.name}:{service_name} publishes non-loopback port {port!r}",
                            )
                        elif isinstance(port, dict) and "published" in port:
                            self.assertEqual(
                                port.get("host_ip"),
                                "127.0.0.1",
                                f"{path.name}:{service_name} long port mapping must bind host_ip=127.0.0.1",
                            )

    def test_profiles_and_presets_reference_existing_entries_without_duplicates(self) -> None:
        modules = {path.name for path in MODULE_DIR.glob("*.yml")}
        profiles = {path.stem for path in PROFILE_DIR.glob("*.txt")}
        for profile_path in sorted(PROFILE_DIR.glob("*.txt")):
            entries = uncommented_lines(profile_path)
            with self.subTest(profile=profile_path.name):
                self.assertEqual(len(entries), len(set(entries)), f"duplicate module in {profile_path.name}")
                self.assertTrue(set(entries).issubset(modules), f"{profile_path.name} references missing modules")
        for preset_path in sorted(PRESET_DIR.glob("*.txt")):
            entries = uncommented_lines(preset_path)
            with self.subTest(preset=preset_path.name):
                self.assertEqual(len(entries), len(set(entries)), f"duplicate profile in {preset_path.name}")
                self.assertTrue(set(entries).issubset(profiles), f"{preset_path.name} references missing profiles")

    def test_key_profiles_and_presets_resolve_to_service_maps(self) -> None:
        cases = [
            ("profile", "substrate"),
            ("profile", "rag"),
            ("preset", "agent-full"),
            ("preset", "intel-full"),
        ]
        for selector_type, value in cases:
            with self.subTest(selector_type=selector_type, value=value):
                modules = resolved_modules(value) if selector_type == "profile" else resolved_modules(preset=value)
                self.assertTrue(modules)
                services: dict[str, Any] = {}
                for module in modules:
                    services.update(load_compose(MODULE_DIR / module).get("services", {}))
                self.assertTrue(services)


if __name__ == "__main__":
    unittest.main()
