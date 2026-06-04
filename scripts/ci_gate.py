#!/usr/bin/env python3
"""Execute abyss-stack validation lanes from docs/validation/validation_lanes.json."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

try:
    from scripts import validation_lanes
except ImportError:  # pragma: no cover - direct script execution fallback
    import validation_lanes  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_step(label: str, command: tuple[str, ...]) -> int:
    print(f"[run] {label}: {subprocess.list2cmdline(command)}", flush=True)
    completed = subprocess.run(command, cwd=REPO_ROOT, env=os.environ.copy(), check=False)
    if completed.returncode != 0:
        print(f"[error] {label} failed with exit code {completed.returncode}", flush=True)
        return completed.returncode
    print(f"[ok] {label}", flush=True)
    return 0


def run_lane(mode: str) -> int:
    try:
        steps = validation_lanes.lane_command_sequence(mode)
    except validation_lanes.ManifestError as exc:
        print(f"[error] {exc}", flush=True)
        return 1
    for step in steps:
        exit_code = run_step(step.label, step.command)
        if exit_code != 0:
            return exit_code
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=validation_lanes.lane_ids(),
        required=True,
        help="validation lane to execute",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_lane(args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
