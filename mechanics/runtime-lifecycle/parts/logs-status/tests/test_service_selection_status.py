from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


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
        )

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["services"], 24)
        self.assertEqual(summary["running_selected"], 17)
        self.assertEqual(summary["missing_selected"], 0)
        self.assertEqual(summary["unexpected_running"], 0)
        self.assertEqual(summary["unknown_running"], 0)
        self.assertEqual(summary["not_running_expected"], 7)
        self.assertEqual(summary["counts"]["running_selected"], 17)


if __name__ == "__main__":
    unittest.main()
