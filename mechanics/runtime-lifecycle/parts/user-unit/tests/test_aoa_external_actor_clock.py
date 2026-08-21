from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
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

    def test_error_log_is_tightened_before_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            error = Path(temporary) / "error.log"
            error.write_text("old\n", encoding="utf-8")
            error.chmod(0o644)
            CLOCK._check_error_log(error)
            self.assertEqual(error.stat().st_mode & 0o777, 0o600)

    def test_configuration_failure_is_persisted_to_error_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status = root / "status"
            error = root / "error.log"
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
        self.assertIn("KillMode=control-group", unit_text)
        self.assertIn("UMask=0077", unit_text)
        self.assertIn("aoa-external-actor-clock@.service", managed.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
