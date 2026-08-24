import json
import subprocess
from unittest.mock import patch

from governed_runner_test_support import GovernedRunnerTestCase, write_json


class GovernedRunnerLifecycleTests(GovernedRunnerTestCase):
    def test_green_run_reaches_landing_and_finishes_cleanly(self) -> None:
        first = self.module.prepare_run(
            self.request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=lambda: self.gate_payload(),
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )
        self.assertEqual(first["status"], "paused")
        run_id = first["run_id"]
        run_dir = self.logs_root / run_id

        approval_path = run_dir / "approval.status.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["current_milestone"] = "plan_freeze"
        approval["status"] = "approved"
        approval["approved"] = True
        approval["milestones"]["plan_freeze"]["status"] = "approved"
        approval["milestones"]["plan_freeze"]["approved"] = True
        write_json(approval_path, approval)

        second = self.module.resume_run(
            run_id,
            log_root=self.logs_root,
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )
        self.assertEqual(second["status"], "paused")
        self.assertEqual(second["current_milestone"], "landing")
        self.assertTrue((run_dir / "landing.diff").exists())

        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["current_milestone"] = "landing"
        approval["status"] = "approved"
        approval["approved"] = True
        approval["milestones"]["landing"]["status"] = "approved"
        approval["milestones"]["landing"]["approved"] = True
        write_json(approval_path, approval)

        third = self.module.resume_run(run_id, log_root=self.logs_root)
        self.assertEqual(third["status"], "pass")
        self.assertIn("docs/target.md", third["changed_files"])
        self.assertIn("gamma", (self.repo_root / "docs" / "target.md").read_text(encoding="utf-8"))
        self.assertFalse(third["triage"]["operator_action_required"])

    def test_degraded_gate_blocks_before_worktree_creation(self) -> None:
        result = self.module.prepare_run(
            self.request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=lambda: self.gate_payload(overall_status="degraded"),
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["failure_class"], "autonomy_gate_failed")

    def test_source_drift_after_autonomy_gate_returns_failure_result(self) -> None:
        def drifting_gate() -> dict:
            (self.repo_root / "README.md").write_text(
                "# changed after gate\n",
                encoding="utf-8",
            )
            return self.gate_payload()

        result = self.module.prepare_run(
            self.request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=drifting_gate,
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["failure_class"], "policy_denied")
        run_dir = self.logs_root / result["run_id"]
        state = json.loads((run_dir / "run.state.json").read_text(encoding="utf-8"))
        self.assertTrue(
            any(
                "source identity changed after autonomy gate" in reason
                for reason in state["failure_reasons"]
            )
        )
        self.assertTrue((run_dir / "result.summary.json").is_file())
        self.assertTrue((run_dir / "report.md").is_file())

    def test_dirty_repo_blocks_execution(self) -> None:
        (self.repo_root / "docs" / "dirty.md").write_text("dirty\n", encoding="utf-8")
        subprocess.run(["git", "add", "docs/dirty.md"], cwd=self.repo_root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "dirty"], cwd=self.repo_root, check=True, capture_output=True, text=True)
        (self.repo_root / "docs" / "dirty.md").write_text("dirty again\n", encoding="utf-8")

        result = self.module.prepare_run(
            self.request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=lambda: self.gate_payload(),
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["failure_class"], "policy_denied")

    def test_out_of_scope_file_change_fails_before_landing(self) -> None:
        def bad_proposal_provider(context: dict) -> dict:
            return {
                "provider": "fixture",
                "selected_target_file": "scripts/validate_stack.py",
                "spec": {
                    "mode": "exact_replace",
                    "target_file": "scripts/validate_stack.py",
                    "old_text": "print('ok')",
                    "new_text": "print('changed')",
                },
                "candidate_files": ["scripts/validate_stack.py"],
                "target_prompt": "",
                "edit_prompt": "",
                "target_answer": "",
                "edit_answer": "",
                "notes": [],
            }

        result = self.module.prepare_run(
            self.request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=lambda: self.gate_payload(),
            advisory_provider=self.advisory_provider,
            proposal_provider=bad_proposal_provider,
        )
        self.assertEqual(result["status"], "paused")
        run_id = result["run_id"]
        run_dir = self.logs_root / run_id
        approval_path = run_dir / "approval.status.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["current_milestone"] = "plan_freeze"
        approval["status"] = "approved"
        approval["approved"] = True
        approval["milestones"]["plan_freeze"]["status"] = "approved"
        approval["milestones"]["plan_freeze"]["approved"] = True
        write_json(approval_path, approval)

        resumed = self.module.resume_run(
            run_id,
            log_root=self.logs_root,
            advisory_provider=self.advisory_provider,
            proposal_provider=bad_proposal_provider,
        )
        self.assertEqual(resumed["status"], "fail")
        self.assertEqual(resumed["failure_class"], "scope_violation")

    def test_worktree_validation_failure_triggers_one_repair_loop(self) -> None:
        calls = {"count": 0}

        def repairing_provider(context: dict) -> dict:
            calls["count"] += 1
            if calls["count"] == 1:
                return {
                    "provider": "fixture",
                    "selected_target_file": "docs/target.md",
                    "spec": {
                        "mode": "exact_replace",
                        "target_file": "docs/target.md",
                        "old_text": "beta",
                        "new_text": "delta",
                    },
                    "candidate_files": ["docs/target.md"],
                    "target_prompt": "",
                    "edit_prompt": "",
                    "target_answer": "",
                    "edit_answer": "",
                    "notes": [],
                }
            return self.proposal_provider(context)

        result = self.module.prepare_run(
            self.request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=lambda: self.gate_payload(),
            advisory_provider=self.advisory_provider,
            proposal_provider=repairing_provider,
        )
        run_id = result["run_id"]
        run_dir = self.logs_root / run_id
        approval_path = run_dir / "approval.status.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["current_milestone"] = "plan_freeze"
        approval["status"] = "approved"
        approval["approved"] = True
        approval["milestones"]["plan_freeze"]["status"] = "approved"
        approval["milestones"]["plan_freeze"]["approved"] = True
        write_json(approval_path, approval)

        resumed = self.module.resume_run(
            run_id,
            log_root=self.logs_root,
            advisory_provider=self.advisory_provider,
            proposal_provider=repairing_provider,
        )
        self.assertEqual(resumed["status"], "paused")
        self.assertEqual(calls["count"], 2)

    def test_base_head_drift_blocks_resume_apply(self) -> None:
        first = self.module.prepare_run(
            self.request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=lambda: self.gate_payload(),
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )
        run_id = first["run_id"]
        run_dir = self.logs_root / run_id
        approval_path = run_dir / "approval.status.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["current_milestone"] = "plan_freeze"
        approval["status"] = "approved"
        approval["approved"] = True
        approval["milestones"]["plan_freeze"]["status"] = "approved"
        approval["milestones"]["plan_freeze"]["approved"] = True
        write_json(approval_path, approval)
        second = self.module.resume_run(
            run_id,
            log_root=self.logs_root,
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )
        self.assertEqual(second["status"], "paused")

        (self.repo_root / "docs" / "drift.md").write_text("drift\n", encoding="utf-8")
        subprocess.run(["git", "add", "docs/drift.md"], cwd=self.repo_root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "."], cwd=self.repo_root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "drift"], cwd=self.repo_root, check=True, capture_output=True, text=True)

        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["current_milestone"] = "landing"
        approval["status"] = "approved"
        approval["approved"] = True
        approval["milestones"]["landing"]["status"] = "approved"
        approval["milestones"]["landing"]["approved"] = True
        write_json(approval_path, approval)

        third = self.module.resume_run(run_id, log_root=self.logs_root)
        self.assertEqual(third["status"], "fail")
        self.assertEqual(third["failure_class"], "policy_denied")

    def test_approval_mismatch_fails_resume(self) -> None:
        first = self.module.prepare_run(
            self.request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=lambda: self.gate_payload(),
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )
        run_id = first["run_id"]
        run_dir = self.logs_root / run_id
        approval_path = run_dir / "approval.status.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["base_head"] = "deadbeef"
        write_json(approval_path, approval)

        result = self.module.resume_run(run_id, log_root=self.logs_root)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["failure_class"], "approval_missing")

    def test_post_apply_failure_rolls_back_and_reports_status(self) -> None:
        result = self.module.prepare_run(
            self.request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=lambda: self.gate_payload(),
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )
        run_id = result["run_id"]
        run_dir = self.logs_root / run_id
        approval_path = run_dir / "approval.status.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["current_milestone"] = "plan_freeze"
        approval["status"] = "approved"
        approval["approved"] = True
        approval["milestones"]["plan_freeze"]["status"] = "approved"
        approval["milestones"]["plan_freeze"]["approved"] = True
        write_json(approval_path, approval)

        paused = self.module.resume_run(
            run_id,
            log_root=self.logs_root,
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )
        self.assertEqual(paused["status"], "paused")

        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["current_milestone"] = "landing"
        approval["status"] = "approved"
        approval["approved"] = True
        approval["milestones"]["landing"]["status"] = "approved"
        approval["milestones"]["landing"]["approved"] = True
        write_json(approval_path, approval)

        with patch.object(self.module, "run_main_acceptance", return_value=False):
            failed = self.module.resume_run(run_id, log_root=self.logs_root)
        self.assertEqual(failed["status"], "fail")
        self.assertEqual(failed["failure_class"], "post_change_validation_failure")
        rollback = json.loads((run_dir / "rollback.status.json").read_text(encoding="utf-8"))
        self.assertTrue(rollback["rollback_ok"])
        self.assertIn("landing_diff_sha256", rollback)
        self.assertIn("beta", (self.repo_root / "docs" / "target.md").read_text(encoding="utf-8"))
