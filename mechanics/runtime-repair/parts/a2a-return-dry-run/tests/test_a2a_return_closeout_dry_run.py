from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = REPO_ROOT / "scripts" / "aoa-a2a-return-closeout-dry-run"
BRIDGE_CONFIG = json.loads(
    (REPO_ROOT / "config-templates" / "Configs" / "federation" / "upstream-compatibility-bridge.json").read_text(
        encoding="utf-8"
    )
)["a2a_return_closeout"]
LOCAL_REQUEST_KIND = BRIDGE_CONFIG["local_request_kind"]
UPSTREAM_REVIEWED_CLOSEOUT_REQUEST_KIND = BRIDGE_CONFIG["upstream_request_kind"]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def reviewed_closeout_payload() -> dict:
    return {
        "schema_version": 1,
        "request_kind": UPSTREAM_REVIEWED_CLOSEOUT_REQUEST_KIND,
        "closeout_id": "closeout-example-child",
        "session_ref": "session:example",
        "reviewed": True,
        "reviewed_artifact_path": "/srv/notes/reviewed_session_artifact.md",
        "trigger": "reviewed-closeout",
        "audit_refs": ["/srv/notes/reviewed_session_artifact.md", "/srv/notes/route_summary.md"],
        "batches": [
            {
                "publisher": "abyss-stack.runtime-closeouts",
                "input_paths": ["/srv/receipts/runtime_closeout_receipt.json"],
            }
        ],
        "a2a_child": {
            "execution_surface": "codex_local",
            "child_task_id": "task-child-1",
            "selected_agent_id": "reviewer",
        },
        "return_plan": {
            "decision": "return",
            "anchor_artifact": "bounded_plan",
            "reentry_mode": "checkpoint_relaunch",
        },
        "checkpoint_bridge_plan": {
            "execution_order": [
                "aoa-session-donor-harvest",
                "aoa-session-progression-lift",
                "aoa-quest-harvest",
            ]
        },
    }


class A2AReturnCloseoutDryRunTests(unittest.TestCase):
    def run_adapter(self, stack_root: Path, payload: dict, *extra_args: str) -> subprocess.CompletedProcess[str]:
        input_path = stack_root / "tmp" / "reviewed-closeout.json"
        write_json(input_path, payload)
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--input-file", str(input_path), *extra_args],
            check=False,
            capture_output=True,
            env={"AOA_STACK_ROOT": str(stack_root)},
            text=True,
        )

    def test_adapter_outputs_dry_run_receipt_candidate_without_writing_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "abyss-stack"
            result = self.run_adapter(stack_root, reviewed_closeout_payload())
            self.assertEqual(result.returncode, 0, result.stderr)
            artifact = json.loads(result.stdout)
            self.assertFalse((stack_root / "Logs").exists())
            self.assertEqual(artifact["artifact_kind"], "aoa.runtime-a2a-return-closeout-dry-run")
            self.assertTrue(artifact["dry_run"])
            self.assertFalse(artifact["live_automation"])
            self.assertEqual(artifact["exported_by"], "scripts/aoa-a2a-return-closeout-dry-run")
            self.assertEqual(
                artifact["runtime_receipt_candidate"]["artifact_kind"],
                "runtime_closeout_receipt_candidate",
            )
            self.assertEqual(
                artifact["runtime_receipt_candidate"]["publisher"],
                "abyss-stack.runtime-closeouts",
            )
            self.assertEqual(
                artifact["runtime_receipt_candidate"]["checkpoint_bridge_steps"],
                ["aoa-session-donor-harvest", "aoa-session-progression-lift", "aoa-quest-harvest"],
            )
            self.assertEqual(artifact["request_family"], "a2a-return-closeout")
            self.assertEqual(artifact["request_kind"], LOCAL_REQUEST_KIND)
            self.assertEqual(artifact["upstream_request_kind"], UPSTREAM_REVIEWED_CLOSEOUT_REQUEST_KIND)
            self.assertIn(
                "repo:aoa-evals/examples/artifact_to_verdict_hook.a2a-summon-return-checkpoint.example.json",
                artifact["contract_refs"],
            )
            self.assertIn(
                "repo:aoa-sdk/examples/a2a/summon_return_checkpoint_e2e.fixture.json",
                artifact["contract_refs"],
            )

    def test_adapter_accepts_full_sdk_e2e_fixture_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "abyss-stack"
            payload = {
                "fixture_id": "a2a-return-closeout-e2e",
                "dry_run": True,
                "live_automation": False,
                "reviewed_closeout_request": reviewed_closeout_payload(),
            }
            result = self.run_adapter(stack_root, payload)
            self.assertEqual(result.returncode, 0, result.stderr)
            artifact = json.loads(result.stdout)

            self.assertEqual(artifact["request_kind"], LOCAL_REQUEST_KIND)
            self.assertEqual(artifact["candidate_payload"]["closeout_id"], "closeout-example-child")
            self.assertTrue(artifact["runtime_receipt_candidate"]["dry_run"])
            self.assertFalse(artifact["runtime_receipt_candidate"]["live_automation"])

    def test_adapter_write_is_private_and_still_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "abyss-stack"
            result = self.run_adapter(stack_root, reviewed_closeout_payload(), "--write")
            self.assertEqual(result.returncode, 0, result.stderr)
            latest_path = (
                stack_root
                / "Logs"
                / "a2a-return-closeouts"
                / "latest"
                / "closeout-example-child.private.json"
            )
            self.assertTrue(latest_path.exists())
            artifact = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertTrue(artifact["dry_run"])
            self.assertFalse(artifact["runtime_receipt_candidate"]["live_automation"])

    def test_adapter_rejects_unreviewed_payload(self) -> None:
        payload = reviewed_closeout_payload()
        payload["reviewed"] = False
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "abyss-stack"
            result = self.run_adapter(stack_root, payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reviewed=true", result.stderr)


if __name__ == "__main__":
    unittest.main()
