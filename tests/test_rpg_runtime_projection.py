from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "aoa-rpg-runtime-projection"


def copy_text_file(src_root: Path, dst_root: Path, relative_path: Path) -> None:
    target = dst_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text((src_root / relative_path).read_text(encoding="utf-8"), encoding="utf-8")


class RpgRuntimeProjectionScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo_root = Path(self.temp_dir.name) / "abyss-stack"
        self.stack_root = Path(self.temp_dir.name) / "runtime-root"

        for relative_path in (
            Path("examples") / "agent_build_snapshot.example.json",
            Path("examples") / "reputation_ledger.example.json",
            Path("examples") / "quest_run_result.example.json",
            Path("examples") / "frontend_projection_bundle.example.json",
            Path("schemas") / "agent_build_snapshot.schema.json",
            Path("schemas") / "reputation_ledger.schema.json",
            Path("schemas") / "quest_run_result.schema.json",
            Path("schemas") / "frontend_projection_bundle.schema.json",
            Path("schemas") / "agent_build_snapshot_collection.schema.json",
            Path("schemas") / "reputation_ledger_collection.schema.json",
            Path("schemas") / "quest_run_result_collection.schema.json",
            Path("schemas") / "frontend_projection_bundle_collection.schema.json",
        ):
            copy_text_file(REPO_ROOT, self.repo_root, relative_path)

    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--stack-root",
                str(self.stack_root),
                *args,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_script_writes_generated_and_runtime_copies(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, msg=result.stderr)

        for relative_path in (
            Path("generated") / "rpg" / "agent_build_snapshots.json",
            Path("generated") / "rpg" / "reputation_ledgers.json",
            Path("generated") / "rpg" / "quest_run_results.json",
            Path("generated") / "rpg" / "frontend_projection_bundles.json",
        ):
            self.assertTrue((self.repo_root / relative_path).is_file())
            self.assertTrue((self.stack_root / "Logs" / "rpg" / "latest" / relative_path.name).is_file())

        check_result = self.run_script("--check")
        self.assertEqual(check_result.returncode, 0, msg=check_result.stderr)

    def test_check_fails_on_runtime_drift(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, msg=result.stderr)

        latest_path = self.stack_root / "Logs" / "rpg" / "latest" / "quest_run_results.json"
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
        payload["runs"][0]["quest_ref"] = "AOA-Q-9999"
        latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

        check_result = self.run_script("--check")
        self.assertNotEqual(check_result.returncode, 0)
        self.assertIn("must match generated/rpg/quest_run_results.json", check_result.stderr)


if __name__ == "__main__":
    unittest.main()
