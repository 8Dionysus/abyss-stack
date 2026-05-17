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
    / "aoa_optimization_audit_status.py"
)

spec = importlib.util.spec_from_file_location("aoa_optimization_audit_status", SCRIPT_PATH)
assert spec and spec.loader
optimization_audit_status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(optimization_audit_status)


class OptimizationAuditStatusTests(unittest.TestCase):
    def test_check_records_required_completion_gate(self) -> None:
        checks: list[dict[str, object]] = []

        optimization_audit_status.check(
            checks,
            "live_resource_guards",
            "Live cgroup state matches staged resource guards.",
            "blocked",
            "scripts/aoa-status --resource-guards --json",
        )

        self.assertEqual(checks[0]["id"], "live_resource_guards")
        self.assertEqual(checks[0]["status"], "blocked")
        self.assertTrue(checks[0]["required_for_completion"])

    def test_parse_key_value_tokens_keeps_overlay_csv(self) -> None:
        parsed = optimization_audit_status.parse_key_value_tokens(
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

    def test_require_complete_returns_nonzero_when_blocked(self) -> None:
        with unittest.mock.patch.object(
            optimization_audit_status,
            "build_audit",
            return_value={
                "summary": {
                    "status": "blocked",
                    "completion_ready": False,
                    "checks": 1,
                    "done": 0,
                    "blocked": 1,
                    "missing": 0,
                    "failed": 0,
                    "next_action": "wait",
                },
                "checks": [
                    {
                        "id": "live_resource_guards",
                        "status": "blocked",
                        "requirement": "Live cgroup state is applied.",
                    }
                ],
            },
        ):
            self.assertEqual(
                optimization_audit_status.main(["--require-complete"]),
                2,
            )


if __name__ == "__main__":
    unittest.main()
