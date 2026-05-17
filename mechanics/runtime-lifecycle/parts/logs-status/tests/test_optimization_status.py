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
    / "aoa_optimization_status.py"
)

spec = importlib.util.spec_from_file_location("aoa_optimization_status", SCRIPT_PATH)
assert spec and spec.loader
optimization_status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(optimization_status)


class OptimizationStatusTests(unittest.TestCase):
    def test_game_guard_blocks_staged_apply(self) -> None:
        summary = optimization_status.summarize(
            {"summary": {"status": "ok"}},
            {"summary": {"status": "staged_not_applied"}},
            {"active": True},
        )

        self.assertEqual(summary["status"], "blocked_by_game_guard")
        self.assertFalse(summary["apply_allowed"])
        self.assertIn("default recreate", summary["next_action"])
        self.assertIn("--wait-game-guard-clear", summary["next_action"])
        self.assertIn("--wait-resource-plan-clear", summary["next_action"])

    def test_ready_when_staged_and_no_game_guard(self) -> None:
        summary = optimization_status.summarize(
            {"summary": {"status": "ok"}},
            {"summary": {"status": "staged_not_applied"}},
            {"active": False},
            {"ok": True, "decision": "allow", "blocked_reasons": []},
        )

        self.assertEqual(summary["status"], "ready_to_apply")
        self.assertTrue(summary["apply_allowed"])
        self.assertIn("default recreate", summary["next_action"])

    def test_resource_plan_blocks_staged_apply(self) -> None:
        summary = optimization_status.summarize(
            {"summary": {"status": "ok"}},
            {"summary": {"status": "staged_not_applied"}},
            {"active": False},
            {
                "ok": False,
                "decision": "force_required",
                "blocked_reasons": ["mode_unattended_cap_probe"],
            },
        )

        self.assertEqual(summary["status"], "blocked_by_resource_plan")
        self.assertFalse(summary["apply_allowed"])
        self.assertEqual(summary["resource_plan_blocked_reasons"], ["mode_unattended_cap_probe"])

    def test_applied_needs_no_apply(self) -> None:
        summary = optimization_status.summarize(
            {"summary": {"status": "ok"}},
            {"summary": {"status": "applied"}},
            {"active": True},
        )

        self.assertEqual(summary["status"], "ok")
        self.assertFalse(summary["apply_allowed"])


if __name__ == "__main__":
    unittest.main()
