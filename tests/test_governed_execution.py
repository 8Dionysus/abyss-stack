import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "_aoa_governed_execution.py"


def load_module():
    spec = importlib.util.spec_from_file_location("aoa_governed_execution_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def init_minimal_repo(root: Path) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "CONTRIBUTING.md").write_text("contrib\n", encoding="utf-8")
    (root / "docs" / "DEPLOYMENT.md").write_text("deploy\n", encoding="utf-8")
    (root / "docs" / "target.md").write_text("alpha\nbeta\n", encoding="utf-8")
    (root / "scripts" / "validate_stack.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)


def governed_request(repo_root: Path) -> dict:
    return {
        "goal": "Change beta to gamma in the target doc.",
        "playbook_id": "AOA-P-0011",
        "profile_class": "workhorse",
        "repo_root": str(repo_root),
        "memo": None,
        "break_glass_reason": None,
    }


def test_policy(enabled_break_glass: bool = False) -> dict:
    return {
        "surface_type": "runtime_governed_execution_policy",
        "schema_version": "v1",
        "policy_id": "test-governed-policy",
        "description": "test policy",
        "enabled": True,
        "global_rules": {
            "gate_mode": "fail_closed",
            "canonical_gate_command": "aoa-status --autonomy --json",
            "require_clean_repo": True,
            "require_stable_base_head": True,
            "approval_milestones": ["plan_freeze", "landing"],
            "max_worktree_repairs": 1,
            "auto_rollback_on_post_apply_failure": True,
            "break_glass_requires_reason": True,
            "repo_scope": "abyss-stack",
            "log_root": "local:/tmp/governed-runs"
        },
        "playbooks": {
            "AOA-P-0011": {
                "enabled": True,
                "execution_kind": "mutation",
                "repo_scope": "abyss-stack",
                "allowed_files": ["docs/target.md"],
                "acceptance_commands": [
                    "python -c \"from pathlib import Path; text = Path('docs/target.md').read_text(encoding='utf-8'); assert 'gamma' in text\""
                ],
                "break_glass_allowed": enabled_break_glass,
                "repair_allowed": True
            }
        },
        "boundaries": {
            "owns_runtime_permissions_only": True,
            "does_not_define_playbook_meaning": True,
            "does_not_replace_route_api_advisory_surfaces": True,
            "does_not_replace_langchain_api_federated_advisory_run": True,
            "first_mutation_scope_is_abyss_stack_only": True
        }
    }


class GovernedExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.repo_root = self.root / "repo"
        init_minimal_repo(self.repo_root)
        self.logs_root = self.root / "logs"
        self.policy_path = self.root / "policy.yaml"
        write_json(self.policy_path, test_policy())
        self.request_path = self.root / "request.json"
        write_json(self.request_path, governed_request(self.repo_root))

    def gate_payload(self, *, overall_status: str = "pass") -> dict:
        return {
            "overall_status": overall_status,
            "truth_status": {
                "control_plane": {
                    "source_authored": True,
                    "deployed": True,
                    "trial_proven": overall_status == "pass",
                    "live_available": overall_status == "pass",
                    "notes": [],
                }
            },
        }

    def advisory_provider(self, request: dict) -> dict:
        return {
            "playbook_id": request["playbook_id"],
            "playbook": {
                "playbook_id": request["playbook_id"],
                "title": "bounded-change-safe",
                "summary": "test",
            },
        }

    def proposal_provider(self, context: dict) -> dict:
        return {
            "provider": "fixture",
            "selected_target_file": "docs/target.md",
            "spec": {
                "mode": "exact_replace",
                "target_file": "docs/target.md",
                "old_text": "beta",
                "new_text": "gamma",
            },
            "candidate_files": ["docs/target.md"],
            "target_prompt": "",
            "edit_prompt": "",
            "target_answer": "{\"target_file\":\"docs/target.md\"}",
            "edit_answer": "{\"mode\":\"exact_replace\",\"target_file\":\"docs/target.md\",\"old_text\":\"beta\",\"new_text\":\"gamma\"}",
            "notes": [],
        }

    def test_policy_parsing_and_playbook_lookup(self) -> None:
        policy, _ = self.module.load_policy(self.policy_path)
        entry = self.module.resolve_playbook_policy(policy, "AOA-P-0011")
        self.assertTrue(entry["enabled"])
        self.assertEqual(entry["allowed_files"], ["docs/target.md"])

    def test_fail_closed_gate_mapping(self) -> None:
        policy, _ = self.module.load_policy(self.policy_path)
        entry = self.module.resolve_playbook_policy(policy, "AOA-P-0011")
        blocked = self.module.evaluate_autonomy_gate(
            self.gate_payload(overall_status="degraded"),
            playbook_policy=entry,
            break_glass_reason=None,
            global_rules=policy["global_rules"],
        )
        self.assertFalse(blocked["allowed"])
        self.assertIn("break_glass_not_allowed", blocked["reasons"])

    def test_break_glass_requires_policy_allowance_and_reason(self) -> None:
        write_json(self.policy_path, test_policy(enabled_break_glass=True))
        policy, _ = self.module.load_policy(self.policy_path)
        entry = self.module.resolve_playbook_policy(policy, "AOA-P-0011")

        missing_reason = self.module.evaluate_autonomy_gate(
            self.gate_payload(overall_status="degraded"),
            playbook_policy=entry,
            break_glass_reason=None,
            global_rules=policy["global_rules"],
        )
        self.assertFalse(missing_reason["allowed"])
        self.assertIn("break_glass_reason_required", missing_reason["reasons"])

        allowed = self.module.evaluate_autonomy_gate(
            self.gate_payload(overall_status="degraded"),
            playbook_policy=entry,
            break_glass_reason="operator requested degraded-mode remediation",
            global_rules=policy["global_rules"],
        )
        self.assertTrue(allowed["allowed"])
        self.assertTrue(allowed["break_glass_used"])

    def test_repo_scope_and_allowed_files_enforcement(self) -> None:
        self.assertTrue(self.module.path_allowed("docs/target.md", ["docs/target.md"]))
        self.assertFalse(self.module.path_allowed("scripts/validate_stack.py", ["docs/target.md"]))

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
        self.assertIn("beta", (self.repo_root / "docs" / "target.md").read_text(encoding="utf-8"))
