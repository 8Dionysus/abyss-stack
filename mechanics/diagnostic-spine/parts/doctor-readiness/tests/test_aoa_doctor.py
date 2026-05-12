from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "scripts").is_dir()
            and (candidate / "mechanics").is_dir()
        ):
            return candidate
    raise RuntimeError("could not locate abyss-stack repository root")


REPO_ROOT = find_repo_root(Path(__file__).resolve().parent)
DOCTOR_PATH = REPO_ROOT / "scripts" / "aoa-doctor"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_fake_bin(path: Path) -> None:
    commands = {
        "podman": """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "compose" && "${2:-}" == "version" ]]; then
  exit 0
fi
if [[ "${1:-}" == "info" ]]; then
  exit 0
fi
exit 0
""",
        "rsync": "#!/usr/bin/env bash\nexit 0\n",
        "curl": "#!/usr/bin/env bash\nexit 0\n",
        "systemctl": """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--user" && "${2:-}" == "show-environment" ]]; then
  exit 0
fi
exit 0
""",
        "findmnt": "#!/usr/bin/env bash\nexit 0\n",
        "getconf": """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "_NPROCESSORS_ONLN" ]]; then
  printf '9999\\n'
  exit 0
fi
exit 1
""",
    }

    path.mkdir(parents=True, exist_ok=True)
    for name, script in commands.items():
        target = path / name
        target.write_text(script, encoding="utf-8")
        target.chmod(0o755)


def build_stack_root(stack_root: Path, *, federated_enabled: str) -> None:
    write_text(
        stack_root / "compose" / "profiles" / "agentic.txt",
        "41-agent-api.yml\n",
    )
    write_text(
        stack_root / "compose" / "profiles" / "federation.txt",
        "43-federation-router.yml\n",
    )
    write_text(
        stack_root / "compose" / "modules" / "41-agent-api.yml",
        textwrap.dedent(
            """\
            services:
              langchain-api:
                image: busybox
            """
        ),
    )
    write_text(
        stack_root / "compose" / "modules" / "43-federation-router.yml",
        textwrap.dedent(
            """\
            services:
              route-api:
                image: busybox
            """
        ),
    )
    write_text(
        stack_root / "Secrets" / "Configs" / "langchain-api.env",
        f"AOA_FEDERATED_RUN_ENABLED={federated_enabled}\n",
    )
    write_text(
        stack_root / "Logs" / "machine-fit" / "latest" / "latest.private.json",
        "{}\n",
    )


def run_doctor(stack_root: Path, fake_bin: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["AOA_STACK_ROOT"] = str(stack_root)
    env["AOA_CONFIGS_ROOT"] = str(stack_root)
    env["AOA_VAULT_ROOT"] = "/abyss"
    env["AOA_MACHINE_FIT_PATH"] = str(stack_root / "Logs" / "machine-fit" / "latest" / "latest.private.json")
    env["AOA_MACHINE_FIT_AUTO_APPLY"] = "false"
    env.pop("AOA_FEDERATED_RUN_ENABLED", None)
    return subprocess.run(
        ["bash", str(DOCTOR_PATH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


class AoaDoctorTests(unittest.TestCase):
    def test_warns_when_federated_consumer_is_enabled_without_federation_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            fake_bin = Path(tmpdir) / "bin"
            build_fake_bin(fake_bin)
            build_stack_root(stack_root, federated_enabled="true")

            result = run_doctor(stack_root, fake_bin, "--profile", "agentic")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "warn federated advisory consumer is enabled but the federation profile is not selected;",
            result.stdout,
        )
        self.assertIn("doctor check passed", result.stdout)

    def test_does_not_warn_when_federation_profile_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            fake_bin = Path(tmpdir) / "bin"
            build_fake_bin(fake_bin)
            build_stack_root(stack_root, federated_enabled="true")

            result = run_doctor(
                stack_root,
                fake_bin,
                "--profile",
                "agentic",
                "--profile",
                "federation",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(
            "warn federated advisory consumer is enabled but the federation profile is not selected;",
            result.stdout,
        )
        self.assertIn("doctor check passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
