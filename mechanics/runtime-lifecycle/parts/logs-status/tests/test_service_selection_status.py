from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT_PATH = (
    REPO_ROOT
    / "mechanics"
    / "runtime-lifecycle"
    / "parts"
    / "logs-status"
    / "aoa_service_selection_status.py"
)

spec = importlib.util.spec_from_file_location("aoa_service_selection_status", SCRIPT_PATH)
assert spec and spec.loader
service_selection_status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service_selection_status)


class ServiceSelectionStatusTests(unittest.TestCase):
    def test_inspection_distinguishes_observed_empty_from_failed_list(self) -> None:
        empty = subprocess.CompletedProcess(
            ["podman", "ps"],
            0,
            stdout="",
            stderr="",
        )
        failed = subprocess.CompletedProcess(
            ["podman", "ps"],
            125,
            stdout="",
            stderr="failed",
        )

        with mock.patch.object(service_selection_status, "run_command", return_value=empty):
            containers, observation = service_selection_status.inspect_compose_containers(
                "abyss"
            )
        self.assertEqual(containers, [])
        self.assertEqual(
            observation,
            {"status": "observed", "reason": "no_containers"},
        )

        with mock.patch.object(service_selection_status, "run_command", return_value=failed):
            containers, observation = service_selection_status.inspect_compose_containers(
                "abyss"
            )
        self.assertEqual(containers, [])
        self.assertEqual(
            observation,
            {"status": "unknown", "reason": "podman_list_failed"},
        )

    def test_selected_service_requires_running_container(self) -> None:
        entry = {"posture": "selected_now"}

        self.assertEqual(
            service_selection_status.classify_service(entry, None),
            "missing_selected",
        )
        self.assertEqual(
            service_selection_status.classify_service(entry, {"state": "running"}),
            "running_selected",
        )

    def test_opt_in_running_is_unexpected(self) -> None:
        entry = {"posture": "explicit_opt_in"}

        self.assertEqual(
            service_selection_status.classify_service(entry, {"state": "running"}),
            "unexpected_running",
        )
        self.assertEqual(
            service_selection_status.classify_service(entry, None),
            "not_running_expected",
        )

    def test_parse_key_value_tokens_keeps_profile_csv(self) -> None:
        parsed = service_selection_status.parse_key_value_tokens(
            "AOA_STACK_PRESET=intel-full AOA_STACK_PROFILE=federation,reranking"
        )

        self.assertEqual(parsed["AOA_STACK_PRESET"], "intel-full")
        self.assertEqual(parsed["AOA_STACK_PROFILE"], "federation,reranking")

    def test_summary_exposes_flat_counts_for_gate_scripts(self) -> None:
        summary = service_selection_status.summarize_service_selection(
            {
                "running_selected": 17,
                "not_running_expected": 7,
            },
            24,
            17,
            {"status": "observed", "reason": "complete"},
        )

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["services"], 24)
        self.assertEqual(summary["running_selected"], 17)
        self.assertEqual(summary["missing_selected"], 0)
        self.assertEqual(summary["unexpected_running"], 0)
        self.assertEqual(summary["unknown_running"], 0)
        self.assertEqual(summary["not_running_expected"], 7)
        self.assertEqual(summary["counts"]["running_selected"], 17)
        self.assertEqual(
            summary["selected_service_running_coverage"]["ratio"],
            1.0,
        )

    def test_running_coverage_keeps_missing_selected_in_denominator(self) -> None:
        coverage = service_selection_status.selected_service_running_coverage(
            {"running_selected": 1, "missing_selected": 2},
            3,
            {"status": "observed", "reason": "complete"},
        )

        self.assertEqual(coverage["status"], "observed")
        self.assertEqual(coverage["numerator"], 1)
        self.assertEqual(coverage["denominator"], 3)
        self.assertEqual(coverage["ratio"], 0.333333)

    def test_running_coverage_is_unknown_when_observation_is_unavailable(self) -> None:
        coverage = service_selection_status.selected_service_running_coverage(
            {},
            3,
            {"status": "unknown", "reason": "podman_list_failed"},
        )

        self.assertEqual(coverage["status"], "unknown")
        self.assertEqual(coverage["reason"], "podman_list_failed")
        self.assertIsNone(coverage["numerator"])
        self.assertEqual(coverage["denominator"], 3)
        self.assertIsNone(coverage["ratio"])

    def test_running_coverage_is_unknown_for_empty_selected_population(self) -> None:
        coverage = service_selection_status.selected_service_running_coverage(
            {},
            0,
            {"status": "observed", "reason": "no_containers"},
        )

        self.assertEqual(coverage["status"], "unknown")
        self.assertEqual(coverage["reason"], "empty_selected_population")
        self.assertEqual(coverage["numerator"], 0)
        self.assertEqual(coverage["denominator"], 0)
        self.assertIsNone(coverage["ratio"])


if __name__ == "__main__":
    unittest.main()
