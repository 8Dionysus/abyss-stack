from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aoa_external_actor_clock.py"
SPEC = importlib.util.spec_from_file_location("aoa_external_actor_clock", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
CLOCK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLOCK)


class ExternalActorClockTests(unittest.TestCase):
    def test_inner_runner_command_is_valid_zsh(self) -> None:
        checked = subprocess.run(
            ["/usr/bin/zsh", "-n"],
            input=CLOCK._runner_command(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        command = CLOCK._runner_command()
        self.assertLess(command.index("umask 077"), command.index('"$AOA_CLOCK_RUNNER"'))
        self.assertLess(
            command.index("AOA_CLOCK_HOLDER_CAPTURED_FILE"),
            command.index('"$AOA_CLOCK_RUNNER"'),
        )
        self.assertNotIn("2> >(", command)
        self.assertIn("runner_stderr_tmp", command)
        self.assertIn("logging_rc=125", command)
        self.assertIn("runner_pid=$!", command)
        self.assertIn('printf \'runner_pid=%s\\n\' "$runner_pid"', command)

    def test_status_records_the_actual_runner_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "runner.zsh"
            runner.write_text(
                "#!/usr/bin/zsh\n"
                'print -r -- $$ > "$AOA_CLOCK_TEST_RUNNER_PID_FILE"\n',
                encoding="utf-8",
            )
            runner.chmod(0o700)
            status = root / "status"
            error = root / "error.log"
            ready = Path(f"{status}.holder-ready")
            captured = Path(f"{status}.holder-captured")
            environment = os.environ.copy()
            environment.update(
                {
                    "AOA_CLOCK_RUNNER": str(runner),
                    "AOA_CLOCK_STATUS_FILE": str(status),
                    "AOA_CLOCK_ERROR_LOG": str(error),
                    "AOA_CLOCK_HOLDER_READY_FILE": str(ready),
                    "AOA_CLOCK_HOLDER_CAPTURED_FILE": str(captured),
                    "AOA_CLOCK_TEST_RUNNER_PID_FILE": str(root / "runner.pid"),
                }
            )
            process = subprocess.Popen(
                ["/usr/bin/zsh", "-lc", CLOCK._runner_command()],
                env=environment,
            )
            try:
                self.assertTrue(
                    self._wait_for_path(ready),
                    "holder handshake was not published",
                )
                captured.write_text("kitty_pid=1\nkitty_start_ticks=2\n", encoding="utf-8")
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
            values = dict(
                line.split("=", 1)
                for line in status.read_text(encoding="utf-8").splitlines()
            )
            self.assertEqual(
                values["runner_pid"],
                (root / "runner.pid").read_text(encoding="utf-8").strip(),
            )

    @staticmethod
    def _wait_for_path(path: Path) -> bool:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if path.exists():
                return True
            time.sleep(0.01)
        return path.exists()

    def test_evidence_paths_require_an_owner_private_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o755)
            runner = root / "runner"
            runner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            runner.chmod(0o700)
            environment = {
                "AOA_CLOCK_RUNNER": str(runner),
                "AOA_CLOCK_TITLE": "clock-title",
                "AOA_CLOCK_STATUS_FILE": str(root / "status"),
                "AOA_CLOCK_ERROR_LOG": str(root / "error.log"),
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                with self.assertRaisesRegex(
                    CLOCK.ClockSupervisorError,
                    "parent must be owner-private",
                ):
                    CLOCK._required_environment()

    def test_error_log_is_tightened_before_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            error = Path(temporary) / "error.log"
            error.write_text("old\n", encoding="utf-8")
            error.chmod(0o644)
            CLOCK._check_error_log(error)
            self.assertEqual(error.stat().st_mode & 0o777, 0o600)

    def test_marker_is_published_as_a_complete_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "captured"
            CLOCK._write_marker(marker, "kitty_pid=123\nkitty_start_ticks=456\n")
            self.assertEqual(
                marker.read_text(encoding="utf-8"),
                "kitty_pid=123\nkitty_start_ticks=456\n",
            )
            self.assertFalse(Path(f"{marker}.{os.getpid()}.tmp").exists())

    def test_stop_interrupts_a_stalled_kitty_dispatch(self) -> None:
        class StalledDispatch:
            returncode: int | None = None

            def __init__(self) -> None:
                self.terminate_calls = 0
                self.kill_calls = 0

            def poll(self) -> int | None:
                return self.returncode

            def terminate(self) -> None:
                self.terminate_calls += 1
                self.returncode = 0

            def kill(self) -> None:
                self.kill_calls += 1
                self.returncode = -9

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = (root / "status", root / "error.log")
            dispatch = StalledDispatch()
            previous_stop_signal = CLOCK._STOP_SIGNAL
            CLOCK._STOP_SIGNAL = 15
            try:
                with (
                    mock.patch.object(CLOCK.signal, "signal"),
                    mock.patch.object(
                        CLOCK,
                        "_required_environment",
                        return_value=(
                            "/tmp/clock-runner",
                            "clock-title",
                            paths[0],
                            paths[1],
                            Path(f"{paths[0]}.holder-ready"),
                            Path(f"{paths[0]}.holder-captured"),
                            30.0,
                            15.0,
                        ),
                    ),
                    mock.patch.object(CLOCK, "_matching_kitties", return_value={}),
                    mock.patch.object(CLOCK.subprocess, "Popen", return_value=dispatch),
                ):
                    self.assertEqual(CLOCK.main(), 0)
            finally:
                CLOCK._STOP_SIGNAL = previous_stop_signal
            self.assertEqual(dispatch.terminate_calls, 1)
            self.assertEqual(dispatch.kill_calls, 0)

    def test_handshake_rejects_a_second_same_title_holder(self) -> None:
        class CompletedDispatch:
            returncode = 0

            def poll(self) -> int:
                return self.returncode

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status = root / "status"
            error = root / "error.log"
            previous_stop_signal = CLOCK._STOP_SIGNAL
            CLOCK._STOP_SIGNAL = None
            try:
                with (
                    mock.patch.object(CLOCK.signal, "signal"),
                    mock.patch.object(
                        CLOCK,
                        "_required_environment",
                        return_value=(
                            "/tmp/clock-runner",
                            "clock-title",
                            status,
                            error,
                            Path(f"{status}.holder-ready"),
                            Path(f"{status}.holder-captured"),
                            30.0,
                            15.0,
                        ),
                    ),
                    mock.patch.object(
                        CLOCK,
                        "_matching_kitties",
                        side_effect=[
                            {},
                            {101: 100},
                            {101: 100, 102: 200},
                        ],
                    ),
                    mock.patch.object(CLOCK, "_utc_now", return_value="2026-08-20T00:00:00+00:00"),
                    mock.patch.object(CLOCK.subprocess, "Popen", return_value=CompletedDispatch()),
                    mock.patch.object(CLOCK, "_terminate_kitty") as terminate_kitty,
                ):
                    self.assertEqual(CLOCK.main(), 125)
            finally:
                CLOCK._STOP_SIGNAL = previous_stop_signal
            self.assertIn("during holder handshake", error.read_text(encoding="utf-8"))
            self.assertEqual(terminate_kitty.call_count, 2)

    def test_configuration_failure_is_persisted_to_error_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status = root / "status"
            error = root / "error.log"
            error.write_text("old\n", encoding="utf-8")
            error.chmod(0o644)
            environment = os.environ.copy()
            for name in (
                "AOA_CLOCK_RUNNER",
                "AOA_CLOCK_TITLE",
                "AOA_CLOCK_STATUS_FILE",
                "AOA_CLOCK_ERROR_LOG",
            ):
                environment.pop(name, None)
            environment["AOA_CLOCK_STATUS_FILE"] = str(status)
            environment["AOA_CLOCK_ERROR_LOG"] = str(error)
            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH)],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 125)
            self.assertEqual(error.stat().st_mode & 0o777, 0o600)
            self.assertIn("AOA_CLOCK_RUNNER must be an absolute path", error.read_text())

    def test_timeout_parser_rejects_non_finite_or_non_positive_values(self) -> None:
        for value in ("nan", "inf", "-inf", "0", "-1"):
            with self.subTest(value=value):
                with self.assertRaises(CLOCK.ClockSupervisorError):
                    CLOCK._finite_timeout("AOA_CLOCK_TEST_TIMEOUT", float(value))

        self.assertEqual(CLOCK._finite_timeout("AOA_CLOCK_TEST_TIMEOUT", 2.5), 2.5)

    def test_status_parser_requires_schema_and_returns_runner_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status = Path(temporary) / "status"
            status.write_text(
                "\n".join(
                    (
                        "schema_version=aoa_external_actor_clock_status_v1",
                        "runner_pid=123",
                        "runner_finished_at=2026-08-20T00:00:00+00:00",
                        "runner_exit_status=37",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(CLOCK._read_status(status), 37)

            status.write_text("runner_exit_status=0\n", encoding="utf-8")
            with self.assertRaises(CLOCK.ClockSupervisorError):
                CLOCK._read_status(status)

    def test_unit_keeps_supervisor_foreground_and_allowlists_template(self) -> None:
        repo_root = MODULE_PATH.parents[4]
        unit = repo_root / "systemd" / "user" / "aoa-external-actor-clock@.service"
        managed = repo_root / "systemd" / "user" / "managed-units.txt"
        unit_text = unit.read_text(encoding="utf-8")
        self.assertIn("Type=simple", unit_text)
        self.assertIn("AssertPathExists=", unit_text)
        self.assertIn("ExecStart=/usr/bin/python3", unit_text)
        self.assertNotIn("ExecStartPre=", unit_text)
        self.assertIn("KillMode=control-group", unit_text)
        self.assertIn("UMask=0077", unit_text)
        self.assertIn("aoa-external-actor-clock@.service", managed.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
