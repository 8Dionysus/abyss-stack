#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEPLOYED_CONFIGS_ROOT = Path("/srv/abyss-stack/Configs")

COMMANDS = [
    ("validate stack", [sys.executable, "scripts/validate_stack.py"]),
    ("check diagnostic surface catalog", [sys.executable, "scripts/build_diagnostic_surface_catalog.py", "--check"]),
    ("validate diagnostic surface catalog", [sys.executable, "scripts/validate_diagnostic_surface_catalog.py"]),
    ("run tests", [sys.executable, "-m", "pytest", "-q"]),
]


def run_step(label: str, command: list[str]) -> int:
    print(f"[run] {label}: {subprocess.list2cmdline(command)}", flush=True)
    completed = subprocess.run(command, cwd=REPO_ROOT, env=os.environ.copy(), check=False)
    if completed.returncode != 0:
        print(f"[error] {label} failed with exit code {completed.returncode}", flush=True)
        return completed.returncode
    print(f"[ok] {label}", flush=True)
    return 0


def run_parity_step() -> int:
    label = "check configs parity"
    env = os.environ.copy()
    command = [sys.executable, "scripts/validate_stack.py", "--parity-check"]
    if DEFAULT_DEPLOYED_CONFIGS_ROOT.exists():
        print(f"[run] {label}: {subprocess.list2cmdline(command)}", flush=True)
        completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
        if completed.returncode != 0:
            print(f"[error] {label} failed with exit code {completed.returncode}", flush=True)
            return completed.returncode
        print(f"[ok] {label}", flush=True)
        return 0

    with tempfile.TemporaryDirectory(prefix="abyss-stack-configs-") as temp_root:
        stack_root = Path(temp_root)
        configs_root = stack_root / "Configs"
        env["AOA_STACK_ROOT"] = str(stack_root)
        env["AOA_CONFIGS_ROOT"] = str(configs_root)
        sync_command = [str(REPO_ROOT / "scripts" / "aoa-sync-configs")]
        print(
            f"[run] prepare synthetic configs parity root: {subprocess.list2cmdline(sync_command)}",
            flush=True,
        )
        sync_completed = subprocess.run(sync_command, cwd=REPO_ROOT, env=env, check=False)
        if sync_completed.returncode != 0:
            print(
                f"[error] prepare synthetic configs parity root failed with exit code {sync_completed.returncode}",
                flush=True,
            )
            return sync_completed.returncode
        parity_command = command + ["--deployed-configs-root", str(configs_root)]
        print(f"[run] {label}: {subprocess.list2cmdline(parity_command)}", flush=True)
        completed = subprocess.run(parity_command, cwd=REPO_ROOT, env=env, check=False)
        if completed.returncode != 0:
            print(f"[error] {label} failed with exit code {completed.returncode}", flush=True)
            return completed.returncode
        print(f"[ok] {label}", flush=True)
        return 0


def main() -> int:
    for label, command in COMMANDS:
        exit_code = run_step(label, command)
        if exit_code != 0:
            return exit_code
    parity_exit_code = run_parity_step()
    if parity_exit_code != 0:
        return parity_exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
