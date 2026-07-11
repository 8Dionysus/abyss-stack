from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SYSTEMD = REPO_ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "user-unit" / "aoa_install_systemd.sh"
STATS_PATH_UNIT = REPO_ROOT / "systemd" / "user" / "aoa-stats-live-refresh.path"
STATS_SERVICE_UNIT = REPO_ROOT / "systemd" / "user" / "aoa-stats-live-refresh.service"
EXPECTED_STATS_RECEIPT_PATHS = (
    "/srv/AbyssOS/aoa-skills/.aoa/live_receipts/session-harvest-family.jsonl",
    "/srv/AbyssOS/aoa-skills/.aoa/live_receipts/core-skill-applications.jsonl",
    "/srv/AbyssOS/aoa-evals/.aoa/live_receipts/eval-result-receipts.jsonl",
    "/srv/AbyssOS/aoa-playbooks/.aoa/live_receipts/playbook-receipts.jsonl",
    "/srv/AbyssOS/aoa-techniques/.aoa/live_receipts/technique-receipts.jsonl",
    "/srv/AbyssOS/aoa-memo/.aoa/live_receipts/memo-writeback-receipts.jsonl",
)


class RuntimeLifecycleUserUnitTests(unittest.TestCase):
    def run_install_systemd(self, *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env = os.environ.copy()
            env["AOA_STACK_ROOT"] = str(root / "stack")
            env["AOA_CONFIGS_ROOT"] = str(root / "Configs")
            env["HOME"] = str(root / "home")
            env["XDG_CONFIG_HOME"] = str(root / "xdg-config")
            return subprocess.run(
                ["bash", str(INSTALL_SYSTEMD), *args],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_empty_preset_assignment_fails_before_runtime_selection(self) -> None:
        result = self.run_install_systemd("--preset=")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("preset must not be empty", result.stderr)

    def test_empty_profile_assignment_fails_before_runtime_selection(self) -> None:
        result = self.run_install_systemd("--profile=")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("profile must not be empty", result.stderr)

    def test_aoa_stats_adapter_delegates_source_selection_to_sibling_owner(self) -> None:
        path_unit = STATS_PATH_UNIT.read_text(encoding="utf-8")
        receipt_paths = tuple(
            line.removeprefix("PathModified=")
            for line in path_unit.splitlines()
            if line.startswith("PathModified=")
        )
        self.assertEqual(receipt_paths, EXPECTED_STATS_RECEIPT_PATHS)
        self.assertNotIn("runtime-wave-closeouts.jsonl", path_unit)

        service_unit = STATS_SERVICE_UNIT.read_text(encoding="utf-8")
        exec_start = next(
            line.removeprefix("ExecStart=")
            for line in service_unit.splitlines()
            if line.startswith("ExecStart=")
        )
        self.assertEqual(
            exec_start,
            "/usr/bin/env python3 /srv/AbyssOS/aoa-stats/scripts/refresh_live_stats.py",
        )
        self.assertIn("WorkingDirectory=/srv/AbyssOS/aoa-stats", service_unit)
        self.assertNotIn("--registry", service_unit)
        self.assertNotIn(str(REPO_ROOT), service_unit)


if __name__ == "__main__":
    unittest.main()
