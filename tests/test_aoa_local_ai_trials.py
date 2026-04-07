from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "aoa-local-ai-trials"


def load_module():
    loader = importlib.machinery.SourceFileLoader("aoa_local_ai_trials", str(MODULE_PATH))
    spec = importlib.util.spec_from_loader("aoa_local_ai_trials", loader)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AoALocalAiTrialsTests(unittest.TestCase):
    def test_run_command_timeout_decodes_bytes(self) -> None:
        module = load_module()
        timeout = subprocess.TimeoutExpired(
            cmd=["demo"],
            timeout=1,
            output=b"partial stdout",
            stderr=b"partial stderr",
        )

        with patch.object(module.subprocess, "run", side_effect=timeout):
            result = module.run_command(["demo"], timeout_s=1)

        self.assertTrue(result["timed_out"])
        self.assertEqual("partial stdout", result["stdout"])
        self.assertEqual("partial stderr", result["stderr"])
        self.assertIsInstance(result["stdout"], str)
        self.assertIsInstance(result["stderr"], str)

    def test_update_w4_index_submits_closeout_only_once_after_terminal_status(self) -> None:
        module = load_module()
        catalog = {
            "W4": [
                {
                    "case_id": f"case-{index}",
                    "repo_scope": "aoa-skills",
                    "task_family": "docs",
                    "title": f"Case {index}",
                }
                for index in range(6)
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log_root = root / "logs"
            mirror_root = root / "mirror"
            log_root.mkdir(parents=True)
            mirror_root.mkdir(parents=True)
            for case in catalog["W4"]:
                case_root = module.case_dir(log_root, "W4", case["case_id"])
                case_root.mkdir(parents=True, exist_ok=True)
                (case_root / "result.summary.json").write_text(
                    json.dumps({"case_id": case["case_id"], "status": "pass"}) + "\n",
                    encoding="utf-8",
                )

            preexisting_status = log_root / f"{module.wave_closeout_base_name('W4')}.submit.json"
            preexisting_status.write_text(
                json.dumps({"gate_result": "in-progress", "status": "skipped"}) + "\n",
                encoding="utf-8",
            )

            submit_flags: list[bool] = []

            def fake_write_wave_surfaces(
                *,
                log_root: Path,
                mirror_root: Path,
                wave_id: str,
                index_payload: dict[str, object],
                submit_closeout: bool = False,
            ) -> None:
                submit_flags.append(submit_closeout)
                if submit_closeout:
                    status_path = log_root / f"{module.wave_closeout_base_name(wave_id)}.submit.json"
                    status_path.write_text(
                        json.dumps(
                            {
                                "gate_result": index_payload["gate_result"],
                                "status": "submitted",
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )

            with patch.object(module, "W4_DOC_CASE_IDS", set()):
                with patch.object(module, "write_wave_surfaces", side_effect=fake_write_wave_surfaces):
                    module.update_w4_index(log_root, mirror_root, catalog)
                    module.update_w4_index(log_root, mirror_root, catalog)

        self.assertEqual([True, False], submit_flags)


if __name__ == "__main__":
    unittest.main()
