#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from scripts import validation_lanes
except ImportError:  # pragma: no cover - direct script execution fallback
    import validation_lanes  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEPLOYED_CONFIGS_ROOT = Path("/srv/AbyssOS/abyss-stack/Configs")


def release_command_sequence() -> tuple[validation_lanes.CommandStep, ...]:
    return validation_lanes.command_sequence("release_check")


def run_step(label: str, command: tuple[str, ...]) -> int:
    print(f"[run] {label}: {subprocess.list2cmdline(command)}", flush=True)
    completed = subprocess.run(command, cwd=REPO_ROOT, env=os.environ.copy(), check=False)
    if completed.returncode != 0:
        print(f"[error] {label} failed with exit code {completed.returncode}", flush=True)
        return completed.returncode
    print(f"[ok] {label}", flush=True)
    return 0


def run_live_parity_step() -> int:
    label = "check configs parity"
    env = os.environ.copy()
    command = (sys.executable, "scripts/validate_stack.py", "--parity-check")
    print(f"[run] {label}: {subprocess.list2cmdline(command)}", flush=True)
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
    if completed.returncode != 0:
        print(f"[error] {label} failed with exit code {completed.returncode}", flush=True)
        return completed.returncode
    print(f"[ok] {label}", flush=True)
    return 0


def run_synthetic_parity_step() -> int:
    label = "check synthetic configs parity"
    env = os.environ.copy()
    command = (sys.executable, "scripts/validate_stack.py", "--parity-check")
    with tempfile.TemporaryDirectory(prefix="abyss-stack-configs-") as temp_root:
        stack_root = Path(temp_root)
        configs_root = stack_root / "Configs"
        env["AOA_STACK_ROOT"] = str(stack_root)
        env["AOA_CONFIGS_ROOT"] = str(configs_root)
        sync_command = (str(REPO_ROOT / "scripts" / "aoa-sync-configs"),)
        print(f"[run] prepare synthetic configs parity root: {subprocess.list2cmdline(sync_command)}", flush=True)
        sync_completed = subprocess.run(sync_command, cwd=REPO_ROOT, env=env, check=False)
        if sync_completed.returncode != 0:
            print(
                f"[error] prepare synthetic configs parity root failed with exit code {sync_completed.returncode}",
                flush=True,
            )
            return sync_completed.returncode
        parity_command = command + ("--deployed-configs-root", str(configs_root))
        print(f"[run] {label}: {subprocess.list2cmdline(parity_command)}", flush=True)
        completed = subprocess.run(parity_command, cwd=REPO_ROOT, env=env, check=False)
        if completed.returncode != 0:
            print(f"[error] {label} failed with exit code {completed.returncode}", flush=True)
            return completed.returncode
        print(f"[ok] {label}", flush=True)
        return 0


def run_parity_step(parity_mode: str) -> int:
    if parity_mode == "synthetic":
        return run_synthetic_parity_step()
    if parity_mode == "live":
        return run_live_parity_step()
    if DEFAULT_DEPLOYED_CONFIGS_ROOT.exists():
        return run_live_parity_step()
    return run_synthetic_parity_step()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run abyss-stack source release checks.")
    parser.add_argument(
        "--parity-mode",
        choices=("synthetic", "live", "auto"),
        default=os.environ.get("ABYSS_STACK_RELEASE_PARITY_MODE", "synthetic"),
        help=(
            "Parity root selection. synthetic builds a temporary runtime mirror "
            "from the checkout, live checks /srv/AbyssOS/abyss-stack/Configs, "
            "and auto keeps the old live-if-present behavior."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        steps = release_command_sequence()
    except validation_lanes.ManifestError as exc:
        print(f"[error] release lane failed to load: {exc}", flush=True)
        return 1
    for step in steps:
        exit_code = run_step(step.label, step.command)
        if exit_code != 0:
            return exit_code
    parity_exit_code = run_parity_step(args.parity_mode)
    if parity_exit_code != 0:
        return parity_exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
