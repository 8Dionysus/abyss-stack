#!/usr/bin/env python3
from __future__ import annotations

import argparse
from importlib import metadata
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_ENV = "ABYSS_STACK_TEST_SCHEDULER"
PYTEST_XDIST_DISTRIBUTION = "pytest-xdist"
PYTEST_XDIST_PIN = "3.8.0"
SCHEDULERS = ("auto", "serial", "xdist-4-worksteal")


def installed_xdist_version() -> str | None:
    try:
        return metadata.version(PYTEST_XDIST_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return None


def scheduler_plan(requested: str, *, xdist_version: str | None) -> dict[str, Any]:
    if requested not in SCHEDULERS:
        return {
            "ok": False,
            "requested": requested,
            "effective": None,
            "reason": "unknown_scheduler",
            "error": f"unknown scheduler {requested!r}; expected one of {', '.join(SCHEDULERS)}",
        }
    if requested == "serial":
        return {
            "ok": True,
            "requested": requested,
            "effective": "serial",
            "reason": "explicit_serial_rollback",
            "pytest_args": [],
            "selection_changed": False,
        }
    if xdist_version == PYTEST_XDIST_PIN:
        return {
            "ok": True,
            "requested": requested,
            "effective": "xdist-4-worksteal",
            "reason": "measured_bounded_full_suite_scheduler",
            "pytest_args": ["-n", "4", "--dist", "worksteal"],
            "selection_changed": False,
        }
    if requested == "xdist-4-worksteal":
        actual = xdist_version or "missing"
        return {
            "ok": False,
            "requested": requested,
            "effective": None,
            "reason": "pytest_xdist_pin_unavailable",
            "error": f"pytest-xdist pin mismatch: expected={PYTEST_XDIST_PIN} actual={actual}",
        }
    return {
        "ok": True,
        "requested": requested,
        "effective": "serial",
        "reason": "safe_serial_fallback_without_exact_xdist_pin",
        "pytest_args": [],
        "selection_changed": False,
    }


def pytest_command(*, scheduler: dict[str, Any], extra_args: list[str]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *[str(value) for value in scheduler.get("pytest_args", [])],
        *extra_args,
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the complete abyss-stack pytest lane with a bounded scheduler."
    )
    parser.add_argument(
        "--scheduler",
        choices=SCHEDULERS,
        default=os.environ.get(SCHEDULER_ENV, "auto"),
        help=(
            "scheduler selection; auto admits the exact pinned work-stealing scheduler "
            f"and otherwise falls back to serial (default: ${SCHEDULER_ENV} or auto)"
        ),
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="additional pytest arguments after --",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    extra_args = list(args.pytest_args)
    if extra_args[:1] == ["--"]:
        extra_args = extra_args[1:]

    xdist_version = installed_xdist_version()
    scheduler = scheduler_plan(args.scheduler, xdist_version=xdist_version)
    actual = xdist_version or "missing"
    if not scheduler["ok"]:
        print(f"[error] {scheduler['error']}", file=sys.stderr, flush=True)
        return 2

    print(
        "[pytest-scheduler] "
        f"requested={scheduler['requested']} effective={scheduler['effective']} "
        f"reason={scheduler['reason']} xdist={actual} selection_changed=false",
        flush=True,
    )
    command = pytest_command(scheduler=scheduler, extra_args=extra_args)
    print(f"[run] tests: {subprocess.list2cmdline(command)}", flush=True)
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
