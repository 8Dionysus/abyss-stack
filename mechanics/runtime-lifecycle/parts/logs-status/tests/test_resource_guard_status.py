from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT_PATH = (
    REPO_ROOT
    / "mechanics"
    / "runtime-lifecycle"
    / "parts"
    / "logs-status"
    / "aoa_resource_guard_status.py"
)

spec = importlib.util.spec_from_file_location("aoa_resource_guard_status", SCRIPT_PATH)
assert spec and spec.loader
resource_guard_status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resource_guard_status)


class ResourceGuardStatusTests(unittest.TestCase):
    def test_parse_key_value_tokens_keeps_overlay_csv(self) -> None:
        parsed = resource_guard_status.parse_key_value_tokens(
            "AOA_STACK_PRESET=intel-full "
            "AOA_STACK_PROFILE=federation,reranking "
            "AOA_EXTRA_COMPOSE_FILES=compose/tuning/storage.yml,compose/tuning/tools.yml"
        )

        self.assertEqual(parsed["AOA_STACK_PRESET"], "intel-full")
        self.assertEqual(parsed["AOA_STACK_PROFILE"], "federation,reranking")
        self.assertEqual(
            parsed["AOA_EXTRA_COMPOSE_FILES"],
            "compose/tuning/storage.yml,compose/tuning/tools.yml",
        )

    def test_parse_rendered_services_reads_resource_fields(self) -> None:
        rendered = """services:
  langchain-api:
    cpus: '1.0'
    image: example/langchain
    mem_limit: 768m
    mem_reservation: 192m
  redis:
    cpus: '0.5'
    mem_limit: 512m
volumes:
  redis-data:
"""

        services = resource_guard_status.parse_rendered_services(rendered)

        self.assertEqual(services["langchain-api"]["cpus"], "1.0")
        self.assertEqual(services["langchain-api"]["mem_limit"], "768m")
        self.assertEqual(services["langchain-api"]["mem_reservation"], "192m")
        self.assertEqual(services["redis"]["mem_limit"], "512m")

    def test_classify_guard_distinguishes_staged_from_applied(self) -> None:
        expected = {"mem_limit": "512m", "cpus": "0.5"}

        self.assertEqual(
            resource_guard_status.classify_guard(
                expected,
                {"mem_limit_bytes": 0, "nano_cpus": 0},
            ),
            "staged_not_applied",
        )
        self.assertEqual(
            resource_guard_status.classify_guard(
                expected,
                {"mem_limit_bytes": 536870912, "nano_cpus": 500000000},
            ),
            "applied",
        )
        self.assertEqual(
            resource_guard_status.classify_guard(
                expected,
                {"mem_limit_bytes": 1073741824, "nano_cpus": 500000000},
            ),
            "staged_not_applied",
        )
        self.assertEqual(
            resource_guard_status.classify_guard(expected, None),
            "missing_live_container",
        )

    def test_classify_guard_detects_stale_live_memory_limit(self) -> None:
        expected = {"cpus": "2.0", "mem_reservation": "1g"}

        self.assertEqual(
            resource_guard_status.classify_guard(
                expected,
                {
                    "mem_limit_bytes": 0,
                    "mem_reservation_bytes": 1073741824,
                    "nano_cpus": 2000000000,
                },
            ),
            "applied",
        )
        self.assertEqual(
            resource_guard_status.classify_guard(
                expected,
                {
                    "mem_limit_bytes": 0,
                    "mem_reservation_bytes": 0,
                    "nano_cpus": 2000000000,
                },
            ),
            "staged_not_applied",
        )
        self.assertEqual(
            resource_guard_status.classify_guard(
                expected,
                {
                    "mem_limit_bytes": 4294967296,
                    "mem_reservation_bytes": 1073741824,
                    "nano_cpus": 2000000000,
                },
            ),
            "staged_not_applied",
        )

    def test_live_cgroup_resources_use_effective_parent_and_child_limits(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            scope = root / "test.scope"
            child = scope / "container"
            child.mkdir(parents=True)
            (scope / "cpu.max").write_text("max 100000\n", encoding="utf-8")
            (scope / "memory.max").write_text("max\n", encoding="utf-8")
            (scope / "memory.swap.max").write_text("max\n", encoding="utf-8")
            (scope / "memory.low").write_text("0\n", encoding="utf-8")
            (child / "cpu.max").write_text("50000 100000\n", encoding="utf-8")
            (child / "memory.max").write_text("268435456\n", encoding="utf-8")
            (child / "memory.swap.max").write_text("134217728\n", encoding="utf-8")
            (child / "memory.low").write_text("67108864\n", encoding="utf-8")

            resources = resource_guard_status.read_live_cgroup_resources(
                "/test.scope",
                cgroup_root=root,
            )

        self.assertEqual(
            resources,
            {
                "nano_cpus": 500000000,
                "mem_limit_bytes": 268435456,
                "mem_reservation_bytes": 67108864,
                "mem_swap_limit_bytes": 134217728,
                "mem_swap_limit_known": True,
            },
        )

    def test_live_cgroup_resources_keep_cpu_and_memory_when_swap_is_unavailable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            scope = root / "test.scope"
            scope.mkdir()
            (scope / "cpu.max").write_text("max 100000\n", encoding="utf-8")
            (scope / "memory.max").write_text("max\n", encoding="utf-8")
            (scope / "memory.low").write_text("67108864\n", encoding="utf-8")

            resources = resource_guard_status.read_live_cgroup_resources(
                "/test.scope",
                cgroup_root=root,
            )

        self.assertEqual(
            resources,
            {
                "nano_cpus": 0,
                "mem_limit_bytes": 0,
                "mem_reservation_bytes": 67108864,
                "mem_swap_limit_bytes": None,
                "mem_swap_limit_known": False,
            },
        )

    def test_classify_guard_fails_closed_when_live_resources_are_unknown(self) -> None:
        self.assertEqual(
            resource_guard_status.classify_guard(
                {"cpus": "0", "mem_limit": "0"},
                {
                    "resource_state_known": False,
                    "mem_limit_bytes": 0,
                    "nano_cpus": 0,
                },
            ),
            "live_resource_unknown",
        )

    def test_summary_exposes_flat_counts_for_gate_scripts(self) -> None:
        summary = resource_guard_status.summarize_guard_status(
            [
                {"guard_status": "applied"},
                {"guard_status": "applied"},
                {"guard_status": "staged_not_applied"},
            ]
        )

        self.assertEqual(summary["status"], "staged_not_applied")
        self.assertEqual(summary["guarded_services"], 3)
        self.assertEqual(summary["applied"], 2)
        self.assertEqual(summary["staged_not_applied"], 1)
        self.assertEqual(summary["missing_live_container"], 0)
        self.assertEqual(summary["counts"]["applied"], 2)


if __name__ == "__main__":
    unittest.main()
