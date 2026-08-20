from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml

from tests.compose_yaml_subset import load_compose_services


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = REPO_ROOT / "compose" / "modules"
PROFILE_DIR = REPO_ROOT / "compose" / "profiles"
PRESET_DIR = REPO_ROOT / "compose" / "presets"
TUNING_DIR = REPO_ROOT / "compose" / "tuning"
LAYOUT_INSTALL = (
    REPO_ROOT
    / "mechanics"
    / "runtime-lifecycle"
    / "parts"
    / "layout-install"
    / "aoa_install_layout.sh"
)
LAYOUT_CHECK = (
    REPO_ROOT
    / "mechanics"
    / "runtime-lifecycle"
    / "parts"
    / "layout-install"
    / "aoa_check_layout.sh"
)


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
    def test_monitoring_state_uses_explicit_stack_bind_mounts(self) -> None:
        module_path = MODULE_DIR / "60-monitoring.yml"
        services = load_compose(module_path)["services"]
        expected_mounts = {
            "prometheus": ("prometheus", "/prometheus"),
            "alertmanager": ("alertmanager", "/alertmanager"),
            "loki": ("loki", "/loki"),
            "tempo": ("tempo", "/var/tempo"),
            "alloy": ("alloy", "/var/lib/alloy/data"),
            "grafana": ("grafana", "/var/lib/grafana"),
        }

        for service_name, (state_dir, container_path) in expected_mounts.items():
            with self.subTest(service=service_name):
                expected = (
                    "${AOA_STACK_ROOT:-/srv/AbyssOS/abyss-stack}"
                    f"/Services/monitoring/{state_dir}:{container_path}:Z"
                )
                self.assertIn(expected, services[service_name].get("volumes", []))

        source = module_path.read_text(encoding="utf-8")
        self.assertNotIn("\nvolumes:\n", source)
        for named_volume in (
            "prometheus_data:",
            "alertmanager_data:",
            "loki_data:",
            "tempo_data:",
            "alloy_data:",
            "grafana_data:",
        ):
            self.assertNotIn(named_volume, source)

    def test_monitoring_bind_state_is_owned_by_runtime_layout(self) -> None:
        install_source = LAYOUT_INSTALL.read_text(encoding="utf-8")
        check_source = LAYOUT_CHECK.read_text(encoding="utf-8")

        for state_dir in (
            "prometheus",
            "alertmanager",
            "loki",
            "tempo",
            "alloy",
            "grafana",
        ):
            expected = f'"${{AOA_STACK_ROOT}}/Services/monitoring/{state_dir}"'
            with self.subTest(state_dir=state_dir):
                self.assertIn(expected, install_source)
                self.assertIn(expected, check_source)
        self.assertIn('has_module "60-monitoring.yml"', check_source)

    def test_llama_swap_candidate_is_owner_admitted_and_removes_inherited_caps(self) -> None:
        service = load_compose(TUNING_DIR / "llamacpp.gemma4-e2b.llama-swap.yml")["services"]["llama-cpp"]

        self.assertEqual(service.get("cpus"), "0")
        self.assertEqual(service.get("mem_limit"), "0")
        self.assertEqual(service.get("mem_reservation"), "0")
        self.assertIn("@sha256:", service.get("image", ""))
        self.assertEqual(service.get("labels", {}).get("aoa.tuning.owner_admission"), "required")
        self.assertTrue(
            any("AOA_RESOURCE_ADMISSION_DIR" in str(volume) and str(volume).endswith(":ro") for volume in service.get("volumes", []))
        )

    def test_all_compose_modules_parse_as_service_maps(self) -> None:
        for path in sorted(MODULE_DIR.glob("*.yml")):
            with self.subTest(module=path.name):
                data = load_compose(path)
                services = data.get("services")
                self.assertIsInstance(services, dict)
                full_data = yaml.safe_load(path.read_text(encoding="utf-8"))
                owner_workloads = full_data.get("x-abyss-owner-workloads")
                self.assertTrue(
                    services or isinstance(owner_workloads, dict) and owner_workloads,
                    f"{path.name} has neither compose services nor owner workloads",
                )

    def test_browser_helper_uses_container_init_reaper(self) -> None:
        service = load_compose(MODULE_DIR / "51-browser-tools.yml")["services"]["aoa-browser"]
        self.assertEqual(service.get("init"), "true")

    def test_ovms_is_a_socket_activated_owner_workload_without_hard_caps(self) -> None:
        module = yaml.safe_load(
            (MODULE_DIR / "31-intel-inference.yml").read_text(encoding="utf-8")
        )
        owner = module["x-abyss-owner-workloads"]["ovms"]
        self.assertEqual(module["services"], {})
        self.assertEqual(owner["container_unit"], "abyss-ovms.service")
        self.assertEqual(
            owner["activation_sockets"],
            ["abyss-ovms.socket", "abyss-ovms-unix.socket"],
        )

        quadlet = (REPO_ROOT / "systemd/user/abyss-ovms.container").read_text(
            encoding="utf-8"
        )
        self.assertIn("StopWhenUnneeded=yes", quadlet)
        self.assertIn("Notify=healthy", quadlet)
        self.assertIn("ExecStartPre=/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-ovms-admission reserve", quadlet)
        self.assertNotIn("EnvironmentFile=", quadlet)
        self.assertIn("Secret=abyss-ovms-api-key", quadlet)
        self.assertIn("Pull=missing", quadlet)
        self.assertNotIn("MemoryMax=", quadlet)
        self.assertNotIn("MemoryHigh=", quadlet)
        self.assertNotIn("MemorySwapMax=", quadlet)

    def test_langchain_uses_unix_activation_socket_without_ovms_dependency(self) -> None:
        module = yaml.safe_load(
            (MODULE_DIR / "42-agent-api-intel.yml").read_text(encoding="utf-8")
        )
        service = module["services"]["langchain-api"]
        self.assertEqual(
            service["environment"]["OVMS_EMBEDDINGS_UNIX_SOCKET"],
            "/run/abyss-stack/ovms-socket/ovms.sock",
        )
        self.assertEqual(
            service["environment"]["OVMS_EMBEDDINGS_API_KEY_FILE"],
            "/run/secrets/ovms_api_key",
        )
        self.assertEqual(service["environment"]["OVMS_EMBEDDINGS_TIMEOUT_S"], "600")
        self.assertTrue(
            any(
                "abyss-stack/ovms-socket:/run/abyss-stack/ovms-socket:ro,z" in volume
                for volume in service["volumes"]
            )
        )
        self.assertFalse(any("ovms-admission" in volume for volume in service["volumes"]))
        self.assertEqual(
            service["secrets"],
            [
                {
                    "source": "abyss-ovms-api-key",
                    "target": "/run/secrets/ovms_api_key",
                    "uid": "0",
                    "gid": "0",
                    "mode": "0400",
                }
            ],
        )
        self.assertEqual(module["secrets"]["abyss-ovms-api-key"], {"external": True})
        self.assertNotIn("ovms", service["depends_on"])

    def test_monitoring_does_not_wake_idle_ovms(self) -> None:
        monitoring = (REPO_ROOT / "config-templates/Configs/monitoring/prometheus.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("job_name: ovms", monitoring)
        self.assertNotIn("ovms:8000", monitoring)

    def test_gemma4_uses_native_sleep_and_soft_reclaim_protection(self) -> None:
        service = load_compose(
            TUNING_DIR / "llamacpp.gemma4-e2b.intel-285h.vulkan.yml"
        )["services"]["llama-cpp"]

        self.assertEqual(service.get("cpus"), "0")
        self.assertEqual(service.get("mem_limit"), "0")
        self.assertEqual(service.get("mem_reservation"), "4g")
        self.assertEqual(service.get("command"), ["--sleep-idle-seconds", "600"])

    def test_thin_host_services_clear_hard_cgroup_ceilings(self) -> None:
        overlay_services = {
            "storage.intel-285h.resource-guard.yml": ("neo4j", "qdrant", "postgres", "redis"),
            "intel-worker.thin-host.yml": ("langchain-api",),
            "federation.thin-host.yml": ("route-api",),
            "observability.thin-host.yml": (
                "prometheus",
                "cadvisor",
                "alertmanager",
                "loki",
                "tempo",
                "alloy",
                "grafana",
            ),
            "tools.thin-host.yml": ("qwen-tts", "tts-router", "docs-api", "aoa-browser"),
            "workflows.thin-host.yml": ("n8n", "n8n-task-runners"),
            "rag.thin-host.yml": ("rag-api",),
        }

        for overlay, service_names in overlay_services.items():
            services = load_compose(TUNING_DIR / overlay)["services"]
            for service_name in service_names:
                with self.subTest(overlay=overlay, service=service_name):
                    service = services[service_name]
                    self.assertEqual(service.get("cpus"), "0")
                    self.assertEqual(service.get("mem_limit"), "0")
                    self.assertIn("mem_reservation", service)

    def test_default_owner_services_are_elastic(self) -> None:
        cases = (
            ("32-llamacpp-inference.yml", "llama-cpp"),
            ("46-rag-api.yml", "rag-api"),
            ("53-babelvox-tts.yml", "babelvox-tts"),
        )

        for module, service_name in cases:
            with self.subTest(module=module, service=service_name):
                service = load_compose(MODULE_DIR / module)["services"][service_name]
                self.assertTrue(str(service.get("cpus", "")).endswith(":-0}"))
                self.assertTrue(str(service.get("mem_limit", "")).endswith(":-0}"))
                self.assertIn("mem_reservation", service)

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
