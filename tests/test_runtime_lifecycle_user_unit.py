from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SYSTEMD = REPO_ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "user-unit" / "aoa_install_systemd.sh"


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


if __name__ == "__main__":
    unittest.main()
