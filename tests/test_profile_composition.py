from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ProfileCompositionTests(unittest.TestCase):
    def run_profile_modules(self, *args: str) -> str:
        env = os.environ.copy()
        env["AOA_CONFIGS_ROOT"] = str(REPO_ROOT)
        env["AOA_MACHINE_FIT_AUTO_APPLY"] = "false"
        result = subprocess.run(
            [str(REPO_ROOT / "scripts" / "aoa-profile-modules"), *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout

    def test_agent_full_preset_is_composition_first(self) -> None:
        output = self.run_profile_modules("--preset", "agent-full")

        self.assertIn("- substrate\n", output)
        self.assertIn("- local-worker\n", output)
        self.assertIn("- tools\n", output)
        self.assertIn("- observability\n", output)
        self.assertNotIn("- agentic\n", output)
        self.assertIn("- 10-storage.yml\n", output)
        self.assertIn("- 20-orchestration.yml\n", output)
        self.assertIn("- 32-llamacpp-inference.yml\n", output)
        self.assertIn("- 41-agent-api.yml\n", output)
        self.assertIn("- 50-speech.yml\n", output)
        self.assertIn("- 51-browser-tools.yml\n", output)
        self.assertIn("- 60-monitoring.yml\n", output)

    def test_intel_full_preset_uses_intel_worker_layer(self) -> None:
        output = self.run_profile_modules("--preset", "intel-full")

        self.assertIn("- substrate\n", output)
        self.assertIn("- intel-worker\n", output)
        self.assertIn("- tools\n", output)
        self.assertIn("- observability\n", output)
        self.assertNotIn("- intel\n", output)
        self.assertIn("- 10-storage.yml\n", output)
        self.assertIn("- 20-orchestration.yml\n", output)
        self.assertIn("- 32-llamacpp-inference.yml\n", output)
        self.assertIn("- 31-intel-inference.yml\n", output)
        self.assertIn("- 41-agent-api.yml\n", output)
        self.assertIn("- 42-agent-api-intel.yml\n", output)

    def test_compatibility_profiles_still_resolve(self) -> None:
        agentic = self.run_profile_modules("--profile", "agentic")
        intel = self.run_profile_modules("--profile", "intel")

        self.assertIn("- agentic\n", agentic)
        self.assertIn("- intel\n", intel)
        self.assertIn("- 41-agent-api.yml\n", agentic)
        self.assertIn("- 42-agent-api-intel.yml\n", intel)


if __name__ == "__main__":
    unittest.main()
