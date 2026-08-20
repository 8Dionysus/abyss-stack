from __future__ import annotations

import importlib.util
import subprocess
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
        self.assertIn("ExecStart=/usr/bin/python3", unit_text)
        self.assertIn("KillMode=control-group", unit_text)
        self.assertIn("aoa-external-actor-clock@.service", managed.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
