import importlib.util
import json
import subprocess
import tempfile
import textwrap
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


def init_minimal_routing_repo(root: Path) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "generated").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# aoa-routing\n", encoding="utf-8")
    (root / "CONTRIBUTING.md").write_text("contrib\n", encoding="utf-8")
    (root / "ROADMAP.md").write_text("roadmap\n", encoding="utf-8")
    (root / "docs" / "FEDERATION_ENTRY_ABI.md").write_text("thin router only\n", encoding="utf-8")
    (root / "docs" / "target.md").write_text("alpha\nbeta\n", encoding="utf-8")
    router_payload = {
        "router_id": "two-stage",
        "entries": [
            {"id": "alpha", "path": "docs/target.md"},
            {"id": "beta", "path": "docs/FEDERATION_ENTRY_ABI.md"},
        ],
    }
    skill_entrypoints_payload = [
        {"id": "alpha", "entry": "docs/target.md"},
        {"id": "beta", "entry": "docs/FEDERATION_ENTRY_ABI.md"},
    ]
    router_events_payload = [
        {"event": "router-built", "count": 2},
        {"event": "entrypoints", "count": 2},
    ]
    (root / "generated" / "aoa_router.min.json").write_text("{\"ok\": true}\n", encoding="utf-8")
    (root / "generated" / "two_stage_router.min.json").write_text(
        json.dumps(router_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "generated" / "two_stage_skill_entrypoints.json").write_text(
        json.dumps(skill_entrypoints_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "generated" / "two_stage_router_events.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in router_events_payload),
        encoding="utf-8",
    )
    (root / "scripts" / "build_router.py").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            from __future__ import annotations

            import argparse
            import json
            from pathlib import Path
            from typing import Any

            REPO_ROOT = Path(__file__).resolve().parents[1]
            GENERATED_DIR = REPO_ROOT / "generated"


            def parse_args() -> argparse.Namespace:
                parser = argparse.ArgumentParser(description="Build minimal routing generated surfaces.")
                parser.add_argument("--check", action="store_true", help="Verify semantic parity only.")
                return parser.parse_args()


            def build_outputs() -> dict[str, Any]:
                return {
                    "two_stage_router.min.json": {
                        "router_id": "two-stage",
                        "entries": [
                            {"id": "alpha", "path": "docs/target.md"},
                            {"id": "beta", "path": "docs/FEDERATION_ENTRY_ABI.md"},
                        ],
                    },
                    "two_stage_skill_entrypoints.json": [
                        {"id": "alpha", "entry": "docs/target.md"},
                        {"id": "beta", "entry": "docs/FEDERATION_ENTRY_ABI.md"},
                    ],
                    "two_stage_router_events.jsonl": [
                        {"event": "router-built", "count": 2},
                        {"event": "entrypoints", "count": 2},
                    ],
                }


            def render_output_text(filename: str, payload: Any) -> str:
                if filename.endswith(".jsonl"):
                    return "".join(
                        json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=False) + "\\n"
                        for item in payload
                    )
                return json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=None,
                    separators=(",", ":"),
                    sort_keys=False,
                ) + "\\n"


            def relative_posix(path: Path) -> str:
                return path.relative_to(REPO_ROOT).as_posix()


            def validate_generated_dir_matches_outputs(outputs: dict[str, Any]) -> list[str]:
                mismatches: list[str] = []
                for filename, payload in outputs.items():
                    path = GENERATED_DIR / filename
                    if not path.exists():
                        mismatches.append(relative_posix(path))
                        continue
                    actual_text = path.read_text(encoding="utf-8")
                    try:
                        if filename.endswith(".jsonl"):
                            actual_payload = [
                                json.loads(line)
                                for line in actual_text.splitlines()
                                if line.strip()
                            ]
                        else:
                            actual_payload = json.loads(actual_text)
                    except json.JSONDecodeError:
                        mismatches.append(relative_posix(path))
                        continue
                    if actual_payload != payload:
                        mismatches.append(relative_posix(path))
                return mismatches


            def main() -> int:
                args = parse_args()
                GENERATED_DIR.mkdir(parents=True, exist_ok=True)
                outputs = build_outputs()
                if args.check:
                    mismatches = validate_generated_dir_matches_outputs(outputs)
                    if mismatches:
                        raise SystemExit("; ".join(mismatches))
                    return 0
                for filename, payload in outputs.items():
                    path = GENERATED_DIR / filename
                    path.write_text(render_output_text(filename, payload), encoding="utf-8", newline="\\n")
                    print(f"[ok] wrote {relative_posix(path)}")
                return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ),
        encoding="utf-8",
    )
    (root / "scripts" / "validate_router.py").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            from __future__ import annotations

            import subprocess
            import sys
            from pathlib import Path

            REPO_ROOT = Path(__file__).resolve().parents[1]


            def main() -> int:
                subprocess.run(
                    [sys.executable, str(REPO_ROOT / "scripts" / "build_router.py"), "--check"],
                    cwd=REPO_ROOT,
                    check=True,
                )
                print("ok")
                return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ),
        encoding="utf-8",
    )
    (root / "tests" / "test_build_router.py").write_text(
        textwrap.dedent(
            """\
            from __future__ import annotations

            import subprocess
            import sys
            from pathlib import Path


            def test_build_router_check_passes() -> None:
                repo_root = Path(__file__).resolve().parents[1]
                subprocess.run(
                    [sys.executable, str(repo_root / "scripts" / "build_router.py"), "--check"],
                    cwd=repo_root,
                    check=True,
                )
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)


def governed_request(repo_root: Path, *, target_id: str = "abyss-stack") -> dict:
    return {
        "goal": "Change beta to gamma in the target doc.",
        "target_id": target_id,
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
            "default_target_id": "abyss-stack",
            "require_clean_repo": True,
            "require_stable_base_head": True,
            "approval_milestones": ["plan_freeze", "landing"],
            "max_worktree_repairs": 1,
            "auto_rollback_on_post_apply_failure": True,
            "break_glass_requires_reason": True,
            "log_root": "local:/tmp/governed-runs",
            "promotion_criteria": {
                "canary_proven": {
                    "minimum_successful_runs": 2,
                    "minimum_task_classes": 1,
                    "maximum_scope_violations": 0,
                    "maximum_rollback_failures": 0,
                    "maximum_break_glass_runs": 0,
                    "maximum_post_change_validation_failures": 0,
                },
                "trusted": {
                    "minimum_successful_runs": 5,
                    "minimum_task_classes": 3,
                    "maximum_scope_violations": 0,
                    "maximum_rollback_failures": 0,
                    "maximum_break_glass_runs": 0,
                    "maximum_post_change_validation_failures": 0,
                },
            },
            "repo_scope_expansion_gate": {
                "minimum_successful_runs": 5,
                "minimum_task_classes": 3,
                "maximum_scope_violations": 0,
                "maximum_rollback_failures": 0,
                "maximum_break_glass_runs": 0,
                "maximum_post_change_validation_failures": 0,
            },
        },
        "targets": {
            "abyss-stack": {
                "repo_scope": "abyss-stack",
                "default_repo_root": "/tmp/abyss-stack",
                "playbooks": {
                    "AOA-P-0011": {
                        "enabled": True,
                        "execution_kind": "mutation",
                        "repo_scope": "abyss-stack",
                        "trust_state": "experimental",
                        "task_class": "docs_only",
                        "allowed_files": ["docs/target.md"],
                        "acceptance_commands": [
                            "python -c \"from pathlib import Path; text = Path('docs/target.md').read_text(encoding='utf-8'); assert 'gamma' in text\""
                        ],
                        "break_glass_allowed": enabled_break_glass,
                        "repair_allowed": True
                    },
                    "AOA-P-0018": {
                        "enabled": True,
                        "execution_kind": "mutation",
                        "repo_scope": "abyss-stack",
                        "trust_state": "experimental",
                        "task_class": "governed_lane",
                        "allowed_files": ["docs/target.md", "scripts/validate_stack.py"],
                        "acceptance_commands": [
                            "python -c \"from pathlib import Path; Path('docs/target.md').read_text(encoding='utf-8')\""
                        ],
                        "break_glass_allowed": enabled_break_glass,
                        "repair_allowed": True
                    }
                }
            },
            "aoa-routing": {
                "repo_scope": "aoa-routing",
                "default_repo_root": "/tmp/aoa-routing",
                "playbooks": {
                    "AOA-P-0011": {
                        "enabled": True,
                        "execution_kind": "mutation",
                        "repo_scope": "aoa-routing",
                        "trust_state": "experimental",
                        "task_class": "docs_only",
                        "allowed_files": [
                            "README.md",
                            "ROADMAP.md",
                            "docs/*.md",
                            "docs/**/*.md",
                            "generated/*.json",
                            "generated/*.jsonl",
                            "scripts/build_router.py",
                            "scripts/validate_router.py",
                            "tests/test_build_router.py",
                        ],
                        "acceptance_commands": [
                            "python scripts/validate_router.py",
                            "python scripts/build_router.py --check",
                            "pytest"
                        ],
                        "break_glass_allowed": False,
                        "repair_allowed": True
                    }
                }
            }
        },
        "boundaries": {
            "owns_runtime_permissions_only": True,
            "does_not_define_playbook_meaning": True,
            "does_not_replace_route_api_advisory_surfaces": True,
            "does_not_replace_langchain_api_federated_advisory_run": True,
            "external_targets_require_explicit_policy": True,
        },
    }


def test_canary_catalog() -> dict:
    return {
        "surface_type": "runtime_governed_execution_canary_catalog",
        "schema_version": "v1",
        "catalog_id": "test-governed-canaries",
        "description": "test canaries",
        "canaries": [
            {
                "canary_id": "docs-truth-wording-alignment",
                "target_id": "abyss-stack",
                "title": "Docs truth wording alignment",
                "goal": "Tighten docs wording inside abyss-stack.",
                "playbook_id": "AOA-P-0011",
                "task_class": "docs_only",
                "profile_class": "workhorse",
                "memo": None,
            },
            {
                "canary_id": "routing-boundary-wording-alignment",
                "target_id": "aoa-routing",
                "title": "Routing boundary wording alignment",
                "goal": "Tighten docs wording inside aoa-routing.",
                "playbook_id": "AOA-P-0011",
                "task_class": "docs_only",
                "profile_class": "workhorse",
                "memo": None,
            },
            {
                "canary_id": "routing-generated-surface-refresh",
                "target_id": "aoa-routing",
                "title": "Routing generated surface refresh",
                "goal": (
                    "Update only `scripts/build_router.py` so its main write loop preserves the existing "
                    "on-disk JSON or JSONL text when the parsed file payload already equals the freshly "
                    "built payload. This must stop no-op `python scripts/build_router.py` from dirtying "
                    "semantically unchanged `generated/two_stage_*` and "
                    "`generated/two_stage_skill_entrypoints.json`, without changing thin-router meaning "
                    "or editing generated files directly."
                ),
                "playbook_id": "AOA-P-0011",
                "task_class": "generated_surface",
                "profile_class": "workhorse",
                "memo": None,
            }
        ],
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
        self.routing_repo_root = self.root / "aoa-routing"
        init_minimal_routing_repo(self.routing_repo_root)
        self.logs_root = self.root / "logs"
        self.policy_path = self.root / "policy.yaml"
        policy = test_policy()
        policy["targets"]["abyss-stack"]["default_repo_root"] = str(self.repo_root)
        policy["targets"]["aoa-routing"]["default_repo_root"] = str(self.routing_repo_root)
        write_json(self.policy_path, policy)
        self.canary_catalog_path = self.root / "canaries.json"
        write_json(self.canary_catalog_path, test_canary_catalog())
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

    def install_review_packet_runtime_surfaces(
        self,
        *,
        playbook_id: str = "AOA-P-0011",
        include_eval_templates: bool = True,
        include_memo_target: bool = True,
    ) -> Path:
        stack_root = self.root / "stack"
        self.module.STACK_ROOT = stack_root

        playbook_contracts = {
            "schema_version": 1,
            "playbooks": [
                {
                    "playbook_id": playbook_id,
                    "playbook_name": "bounded-change-safe",
                    "scenario": "bounded_change_safe",
                    "expected_artifacts": ["approval_record", "verification_pack"],
                    "eval_anchors": ["aoa-approval-boundary-adherence"],
                    "memo_runtime_surfaces": ["approval_record"] if include_memo_target else ["missing_surface"],
                    "candidate_packet_kinds": [
                        "memo_candidate",
                        "runtime_evidence_selection_candidate",
                        "artifact_hook_candidate",
                    ],
                    "review_required": True,
                    "source_review_refs": ["playbooks/bounded-change-safe/PLAYBOOK.md"],
                    "gate_verdict": "hold",
                }
            ],
        }
        write_json(
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-playbooks"
            / "generated"
            / "playbook_review_packet_contracts.min.json",
            playbook_contracts,
        )
        write_json(
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-playbooks"
            / "generated"
            / "playbook_review_intake.min.json",
            {
                "schema_version": 1,
                "playbooks": [
                    {
                        "playbook_id": playbook_id,
                        "playbook_name": "bounded-change-safe",
                        "scenario": "bounded_change_safe",
                        "gate_verdict": "hold",
                        "gate_review_ref": "docs/gate-reviews/bounded-change-safe.md",
                        "real_run_template_ref": "examples/playbook_activation.bounded-change-safe.example.json",
                        "required_artifact_set": ["approval_record", "verification_pack"],
                        "accepted_packet_kinds": [
                            "memo_candidate",
                            "runtime_evidence_selection_candidate",
                            "artifact_hook_candidate",
                        ],
                        "source_review_refs": ["playbooks/bounded-change-safe/PLAYBOOK.md"],
                        "review_outcome_targets": {
                            "real_runs": ["docs/real-runs/2026-03-28.bounded-change-safe.md"],
                            "gate_reviews": ["docs/gate-reviews/bounded-change-safe.md"],
                        },
                        "composition_posture": "awaiting-reviewed-run",
                    }
                ],
            },
        )

        eval_templates = {
            "schema_version": 1,
            "templates": (
                [
                    {
                        "template_kind": "runtime_evidence_selection",
                        "template_name": "workhorse-q4-vs-q6-latency-tradeoff",
                        "playbook_id": None,
                        "eval_anchor": None,
                        "verdict_bundle_ref": None,
                        "required_runtime_artifacts": ["summary", "comparison-note"],
                        "review_required": True,
                        "source_example_ref": "examples/runtime_evidence_selection.workhorse-local.example.json",
                    },
                    {
                        "template_kind": "artifact_to_verdict_hook",
                        "template_name": "aoa-p-0011-approval-boundary-hook",
                        "playbook_id": playbook_id,
                        "eval_anchor": "aoa-approval-boundary-adherence",
                        "verdict_bundle_ref": "repo:aoa-evals/bundles/aoa-approval-boundary-adherence/EVAL.md",
                        "required_runtime_artifacts": ["approval_record", "verification_pack"],
                        "review_required": True,
                        "source_example_ref": "examples/artifact_to_verdict_hook.self-agent-checkpoint-rollout.example.json",
                    },
                ]
                if include_eval_templates
                else []
            ),
        }
        write_json(
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-evals"
            / "generated"
            / "runtime_candidate_template_index.min.json",
            eval_templates,
        )
        write_json(
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-evals"
            / "generated"
            / "runtime_candidate_intake.min.json",
            {
                "schema_version": 1,
                "templates": (
                    [
                        {
                            "template_kind": "runtime_evidence_selection",
                            "template_name": "workhorse-q4-vs-q6-latency-tradeoff",
                            "playbook_id": None,
                            "eval_anchor": None,
                            "verdict_bundle_ref": None,
                            "required_runtime_artifacts": ["summary", "comparison-note"],
                            "review_required": True,
                            "review_guide_ref": "docs/RUNTIME_BENCH_PROMOTION_GUIDE.md",
                            "owner_review_refs": [
                                "docs/RUNTIME_BENCH_PROMOTION_GUIDE.md",
                                "examples/runtime_evidence_selection.workhorse-local.example.json",
                            ],
                            "candidate_acceptance_posture": "candidate_until_eval_review",
                        },
                        {
                            "template_kind": "artifact_to_verdict_hook",
                            "template_name": "aoa-p-0011-approval-boundary-hook",
                            "playbook_id": playbook_id,
                            "eval_anchor": "aoa-approval-boundary-adherence",
                            "verdict_bundle_ref": "repo:aoa-evals/bundles/aoa-approval-boundary-adherence/EVAL.md",
                            "required_runtime_artifacts": ["approval_record", "verification_pack"],
                            "review_required": True,
                            "review_guide_ref": "docs/TRACE_EVAL_BRIDGE.md",
                            "owner_review_refs": [
                                "docs/TRACE_EVAL_BRIDGE.md",
                                "examples/artifact_to_verdict_hook.self-agent-checkpoint-rollout.example.json",
                            ],
                            "candidate_acceptance_posture": "candidate_until_eval_review",
                        },
                    ]
                    if include_eval_templates
                    else []
                ),
            },
        )
        write_json(
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-evals"
            / "schemas"
            / "runtime-evidence-selection.schema.json",
            {"title": "fixture runtime evidence selection"},
        )
        write_json(
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-evals"
            / "schemas"
            / "artifact-to-verdict-hook.schema.json",
            {"title": "fixture artifact hook"},
        )
        for rel_path in (
            "docs/RUNTIME_BENCH_PROMOTION_GUIDE.md",
            "docs/TRACE_EVAL_BRIDGE.md",
            "docs/SELF_AGENT_CHECKPOINT_EVAL_POSTURE.md",
            "docs/RECURRENCE_PROOF_PROGRAM.md",
            "examples/runtime_evidence_selection.workhorse-local.example.json",
            "examples/runtime_evidence_selection.return-anchor-integrity.example.json",
            "examples/runtime_evidence_selection.phase-alpha-memo-recall-rerun.example.json",
            "examples/runtime_evidence_selection.phase-alpha-memo-contradiction-gap.example.json",
            "examples/runtime_evidence_selection.phase-alpha-memo-contradiction-rerun.example.json",
            "examples/artifact_to_verdict_hook.self-agent-checkpoint-rollout.example.json",
        ):
            path = stack_root / "Knowledge" / "federation" / "aoa-evals" / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == ".json":
                write_json(path, {"fixture": rel_path})
            else:
                path.write_text(f"{rel_path}\n", encoding="utf-8")

        memo_targets = {
            "schema_version": 1,
            "targets": (
                [
                    {
                        "runtime_surface": "approval_record",
                        "target_kind": "decision",
                        "writeback_class": "memo_surviving_event",
                        "requires_human_review": True,
                        "review_state_default": "proposed",
                        "runtime_refs": ["docs/MEMORY_MODEL.md#approval-record"],
                        "notes": "Fixture approval writeback.",
                    }
                ]
                if include_memo_target
                else []
            ),
        }
        write_json(
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-memo"
            / "generated"
            / "runtime_writeback_targets.min.json",
            memo_targets,
        )
        write_json(
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-memo"
            / "generated"
            / "runtime_writeback_intake.min.json",
            {
                "schema_version": 1,
                "targets": (
                    [
                        {
                            "runtime_surface": "approval_record",
                            "target_kind": "decision",
                            "writeback_class": "memo_surviving_event",
                            "requires_human_review": True,
                            "review_state_default": "proposed",
                            "runtime_refs": ["docs/MEMORY_MODEL.md#approval-record"],
                            "owner_review_refs": [
                                "docs/MEMORY_MODEL.md#approval-record",
                                "docs/RUNTIME_WRITEBACK_SEAM.md",
                                "docs/QUEST_EVIDENCE_WRITEBACK.md",
                            ],
                            "intake_posture": "review_before_writeback",
                        }
                    ]
                    if include_memo_target
                    else []
                ),
            },
        )
        write_json(
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-memo"
            / "examples"
            / "checkpoint_to_memory_contract.example.json",
            {
                "contract_type": "checkpoint_to_memory_contract",
                "contract_id": "aoa-memo.runtime-writeback.v1",
                "runtime_boundary": {"boundary": "fixture"},
                "mapping_rules": (
                    [
                        {
                            "runtime_surface": "approval_record",
                            "target_kind": "decision",
                            "writeback_class": "memo_surviving_event",
                            "temperature_hint": "warm",
                            "review_state_default": "proposed",
                            "requires_human_review": True,
                            "runtime_refs": ["docs/MEMORY_MODEL.md#approval-record"],
                            "notes": "Fixture approval writeback.",
                        }
                    ]
                    if include_memo_target
                    else []
                ),
            },
        )
        return stack_root

    def test_compact_excerpt_prefers_goal_focus_terms(self) -> None:
        text = "alpha\n" + ("padding\n" * 400) + "repo-scope expansion gate remains evidence only\n" + ("tail\n" * 200)
        excerpt = self.module.compact_excerpt(
            text,
            char_limit=240,
            focus_terms=self.module.focus_terms_from_goal(
                "Clarify repo-scope expansion gate wording in docs/GOVERNED_EXECUTION.md",
                target_file="docs/GOVERNED_EXECUTION.md",
            ),
        )
        self.assertIn("repo-scope expansion gate", excerpt)
        self.assertLessEqual(len(excerpt), 260)

    def test_build_edit_spec_prompt_uses_bounded_excerpt(self) -> None:
        prompt = self.module.build_edit_spec_prompt(
            request={"goal": "Clarify repo-scope expansion gate wording in docs/GOVERNED_EXECUTION.md"},
            playbook_id="AOA-P-0011",
            target_file="docs/GOVERNED_EXECUTION.md",
            target_text=("padding\n" * 500) + "repo-scope expansion gate remains evidence only\n" + ("tail\n" * 500),
            failure_context=[],
        )
        self.assertIn("repo-scope expansion gate remains evidence only", prompt)
        self.assertLess(len(prompt), 4300)
        self.assertIn("prefer `exact_replace`", prompt)
        self.assertIn("under 240 characters", prompt)
        self.assertIn("never copy an entire section", prompt)

    def test_build_edit_spec_prompt_prefers_relevant_code_identifier_excerpt(self) -> None:
        target_text = (
            ("padding\n" * 300)
            + "def make_pass_summary(\n    pass\n)\n"
            + ("middle\n" * 250)
            + "def request_lineage_key(request_path):\n"
            + "    return request_path\n"
            + ("helper\n" * 20)
            + "def list_runs(*, log_root: str | Path | None = None, policy_path: str | Path | None = None) -> dict[str, Any]:\n"
            + "    blocked_runs = [run for run in runs if (run.get(\"triage\") or {}).get(\"operator_action_required\")]\n"
            + "    latest_blocked = sorted(blocked_runs, key=lambda item: str(item.get(\"updated_at\") or \"\"), reverse=True)\n"
            + "    triage_summary = {\n"
            + "        \"recommended_action\": latest_blocked[0][\"triage\"][\"recommended_action\"] if latest_blocked else \"No operator action required.\",\n"
            + "    }\n"
            + ("tail\n" * 200)
        )
        prompt = self.module.build_edit_spec_prompt(
            request={
                "goal": (
                    "Update scripts/_aoa_governed_execution.py so list_runs computes "
                    "operator_triage.latest_operator_action from the freshest run in each request lineage."
                )
            },
            playbook_id="AOA-P-0018",
            target_file="scripts/_aoa_governed_execution.py",
            target_text=target_text,
            failure_context=[],
        )
        self.assertIn("def list_runs", prompt)
        self.assertIn("latest_blocked", prompt)
        self.assertNotIn("def make_pass_summary", prompt)
        self.assertLess(len(prompt), 5700)

    def test_extract_python_symbol_excerpt_prefers_named_function(self) -> None:
        target_text = (
            ("padding\n" * 200)
            + "def make_pass_summary(\n    return {}\n)\n"
            + ("middle\n" * 200)
            + "def list_runs(*, log_root=None):\n"
            + "    blocked_runs = []\n"
            + "    return {\"runs\": blocked_runs}\n"
            + ("tail\n" * 100)
        )
        excerpt = self.module.extract_python_symbol_excerpt(
            target_text,
            goal="Update scripts/_aoa_governed_execution.py so list_runs computes operator triage from the freshest request lineage.",
            char_limit=500,
        )
        assert excerpt is not None
        self.assertIn("def list_runs", excerpt)
        self.assertIn("blocked_runs", excerpt)
        self.assertNotIn("def make_pass_summary", excerpt)

    def test_extract_python_symbol_excerpt_preserves_function_header_when_compacted(self) -> None:
        target_text = (
            "def list_runs(*, log_root=None):\n"
            + "".join(f"    filler_{index} = {index}\n" for index in range(120))
            + "    blocked_runs = []\n"
            + "    return {\"runs\": blocked_runs}\n"
        )
        excerpt = self.module.extract_python_symbol_excerpt(
            target_text,
            goal="Update scripts/_aoa_governed_execution.py so list_runs computes operator triage from request lineage.",
            char_limit=220,
        )
        assert excerpt is not None
        self.assertTrue(excerpt.startswith("def list_runs"))
        self.assertIn("blocked_runs", excerpt)

    def test_compact_python_block_prefers_return_shape_when_requested(self) -> None:
        block = (
            "def build_run_record(run_dir: Path) -> dict[str, Any]:\n"
            "    state = load_state(run_dir)\n"
            "    approval = load_approval(run_dir)\n"
            "    summary = load_summary_or_synthesize(run_dir, state, approval)\n"
            "    triage = summary.get(\"triage\") or compute_triage(state, summary, approval)\n"
            "    return {\n"
            "        \"run_id\": state.get(\"run_id\") or run_dir.name,\n"
            "        \"updated_at\": state.get(\"updated_at\"),\n"
            "        \"request_path\": str(run_dir / \"request.json\"),\n"
            "    }\n"
        )
        excerpt = self.module.compact_python_block(
            block,
            char_limit=180,
            focus_terms=['"request_path"', 'return {', '"run_id"', '"updated_at"'],
        )
        self.assertTrue(excerpt.startswith("def build_run_record"))
        self.assertIn("\"request_path\"", excerpt)
        self.assertNotIn("summary = load_summary_or_synthesize", excerpt)

    def test_python_symbol_hints_from_goal_prefers_identifier_tokens(self) -> None:
        hints = self.module.python_symbol_hints_from_goal(
            "Update scripts/_aoa_governed_execution.py so list_runs computes latest_operator_action from request lineage."
        )
        self.assertIn("_aoa_governed_execution", hints)
        self.assertIn("list_runs", hints)
        self.assertIn("latest_operator_action", hints)

    def test_build_edit_spec_prompt_keeps_request_lineage_goal_inside_list_runs(self) -> None:
        target_text = (
            ("padding\n" * 200)
            + "def request_lineage_key(request_path: str) -> str:\n"
            + "    return request_path\n"
            + ("helper\n" * 20)
            + "def freshest_runs_by_request_lineage(runs):\n"
            + "    return runs\n"
            + ("helper\n" * 20)
            + "def build_run_record(run_dir: Path) -> dict[str, Any]:\n"
            + "    state = load_state(run_dir)\n"
            + "    approval = load_approval(run_dir)\n"
            + "    summary = load_summary_or_synthesize(run_dir, state, approval)\n"
            + "    triage = summary.get(\"triage\") or compute_triage(state, summary, approval)\n"
            + "    return {\"run_id\": state.get(\"run_id\"), \"updated_at\": state.get(\"updated_at\"), \"request_path\": str(run_dir / \"request.json\")}\n"
            + ("middle\n" * 120)
            + "def list_runs(*, log_root: str | Path | None = None, policy_path: str | Path | None = None) -> dict[str, Any]:\n"
            + "    blocked_runs = [run for run in runs if (run.get(\"triage\") or {}).get(\"operator_action_required\")]\n"
            + "    latest_blocked = sorted(blocked_runs, key=lambda item: str(item.get(\"updated_at\") or \"\"), reverse=True)\n"
            + "    triage_summary = {\"recommended_action\": latest_blocked[0][\"triage\"][\"recommended_action\"] if latest_blocked else \"No operator action required.\"}\n"
            + ("tail\n" * 120)
        )
        prompt = self.module.build_edit_spec_prompt(
            request={
                "goal": (
                    "Update scripts/_aoa_governed_execution.py so list_runs computes "
                    "latest_operator_action from the freshest request lineage."
                )
            },
            playbook_id="AOA-P-0018",
            target_file="scripts/_aoa_governed_execution.py",
            target_text=target_text,
            failure_context=[],
        )
        self.assertIn("def list_runs", prompt)
        self.assertIn("prefer changing `list_runs` aggregation first", prompt)
        self.assertIn("each governed run state already records `request_path`", prompt)
        self.assertIn("do not reference a separate `operator_triage` field or introduce a standalone `latest_operator_action` local", prompt)
        self.assertIn('do not add a sibling `"latest_operator_action"` key here', prompt)
        self.assertIn('prefer changing the upstream `blocked_runs` / `latest_blocked` lineage selection', prompt)
        self.assertIn('do not change only the fallback string or return a no-op edit', prompt)
        self.assertIn('do not sort by the raw `request_path` string', prompt)
        self.assertIn('strip any `-retry<number>` suffix', prompt)
        self.assertIn('keep the freshest run by `updated_at` within each request lineage first', prompt)
        self.assertIn('derive `blocked_runs` from `freshest_runs_by_request_lineage(runs)` before `latest_blocked`', prompt)
        self.assertIn('do not submit a no-op replacement of the existing `"recommended_action": (` block', prompt)
        self.assertIn('do not call `freshest_runs_by_request_lineage()` on `blocked_runs` or `latest_blocked` again', prompt)
        self.assertIn('prefer one compact `exact_replace` that swaps the current two-line `blocked_runs` / `latest_blocked` block', prompt)
        self.assertIn('the first replacement line should be `freshest_runs = freshest_runs_by_request_lineage(runs)`', prompt)
        self.assertIn('filter `blocked_runs` from `freshest_runs`, then set `latest_blocked = blocked_runs[:1]`', prompt)
        self.assertIn("Relevant helper excerpt", prompt)
        self.assertIn("def request_lineage_key", prompt)
        self.assertIn("def freshest_runs_by_request_lineage", prompt)
        self.assertNotIn("def make_pass_summary", prompt)

    def test_build_edit_spec_prompt_includes_helper_excerpt_for_build_run_record_goal(self) -> None:
        target_text = (
            ("padding\n" * 200)
            + "def build_run_record(run_dir: Path) -> dict[str, Any]:\n"
            + "    state = load_state(run_dir)\n"
            + "    approval = load_approval(run_dir)\n"
            + "    summary = load_summary_or_synthesize(run_dir, state, approval)\n"
            + "    triage = summary.get(\"triage\") or compute_triage(state, summary, approval)\n"
            + "    return {\"run_id\": state.get(\"run_id\"), \"updated_at\": state.get(\"updated_at\"), \"request_path\": str(run_dir / \"request.json\")}\n"
            + ("tail\n" * 120)
        )
        prompt = self.module.build_edit_spec_prompt(
            request={
                "goal": (
                    "Update scripts/_aoa_governed_execution.py so build_run_record "
                    "includes request_path in the returned record."
                )
            },
            playbook_id="AOA-P-0018",
            target_file="scripts/_aoa_governed_execution.py",
            target_text=target_text,
            failure_context=[],
        )
        self.assertIn("Relevant helper excerpt", prompt)
        self.assertIn("def build_run_record", prompt)
        self.assertIn("\"request_path\"", prompt)
        self.assertNotIn("summary = load_summary_or_synthesize", prompt)

    def test_build_edit_spec_prompt_focuses_build_router_noop_goal_on_main_loop(self) -> None:
        target_text = (
            "from build_two_stage_skill_router import build_outputs as build_two_stage_outputs\n"
            + ("padding\n" * 180)
            + "def render_output_text(filename: str, payload: Any) -> str:\n"
            + "    if filename.endswith('.jsonl'):\n"
            + "        return dump_jsonl(payload)\n"
            + "    return json.dumps(payload, ensure_ascii=False, indent=None, separators=(',', ':'), sort_keys=False) + '\\n'\n"
            + ("middle\n" * 120)
            + "def validate_generated_dir_matches_outputs(outputs: dict[str, Any], *, generated_dir: Path) -> list[str]:\n"
            + "    mismatches = []\n"
            + "    actual_payload = json.loads('{}')\n"
            + "    if actual_payload != payload:\n"
            + "        mismatches.append('stale generated output')\n"
            + "    return mismatches\n"
            + ("middle\n" * 120)
            + "def main() -> int:\n"
            + "    args = parse_args()\n"
            + "    outputs = build_outputs(...)\n"
            + "    if args.check:\n"
            + "        mismatches = validate_generated_dir_matches_outputs(outputs, generated_dir=generated_dir)\n"
            + "        return 0\n"
            + "    for filename, payload in outputs.items():\n"
            + "        path = generated_dir / filename\n"
            + "        path.write_text(render_output_text(filename, payload), encoding='utf-8', newline='\\n')\n"
            + "    return 0\n"
        )
        prompt = self.module.build_edit_spec_prompt(
            request={
                "goal": (
                    "Update only `scripts/build_router.py` so its main write loop preserves the "
                    "existing on-disk JSON or JSONL text when the parsed file payload already "
                    "equals the freshly built payload. This must stop no-op `python scripts/build_router.py` "
                    "from dirtying semantically unchanged `generated/two_stage_*` and "
                    "`generated/two_stage_skill_entrypoints.json`, without changing thin-router "
                    "meaning or editing generated files directly."
                )
            },
            playbook_id="AOA-P-0011",
            target_file="scripts/build_router.py",
            target_text=target_text,
            failure_context=[],
        )
        self.assertIn("def main()", prompt)
        self.assertIn("preserve the existing on-disk JSON or JSONL text", prompt)
        self.assertIn("do not touch imports, comments, docstrings, or generated files", prompt)
        self.assertIn("keep `--check` behavior and generated payload meaning unchanged", prompt)
        self.assertIn("Helper excerpts", prompt)
        self.assertIn("def validate_generated_dir_matches_outputs", prompt)
        self.assertIn("def render_output_text", prompt)
        self.assertNotIn("from build_two_stage_skill_router", prompt)
        self.assertLess(len(prompt), 3200)

    def test_persist_proposal_attempt_artifacts_writes_error_artifact(self) -> None:
        run_dir = self.root / "run"
        self.module.persist_proposal_attempt_artifacts(
            run_dir,
            kind="edit",
            attempt=1,
            prompt="prompt",
            response='{"ok": false}',
            error="RuntimeError: rejected",
        )
        self.assertTrue((run_dir / "artifacts" / "proposal.edit.a01.prompt.txt").exists())
        self.assertTrue((run_dir / "artifacts" / "proposal.edit.a01.response.txt").exists())
        self.assertTrue((run_dir / "artifacts" / "proposal.edit.a01.error.txt").exists())

    def test_request_lineage_key_strips_retry_suffix(self) -> None:
        self.assertEqual(
            self.module.request_lineage_key("/tmp/slot-4-retry.request.json"),
            "slot-4.request.json",
        )
        self.assertEqual(
            self.module.request_lineage_key("/tmp/slot-4-retry7.request.json"),
            "slot-4.request.json",
        )
        self.assertEqual(
            self.module.request_lineage_key("/tmp/slot-4.request.json"),
            "slot-4.request.json",
        )
        self.assertEqual(self.module.request_lineage_key(None), "")

    def test_freshest_runs_by_request_lineage_prefers_latest_retry(self) -> None:
        runs = [
            {
                "run_id": "slot-4-base",
                "request_path": "/tmp/slot-4.request.json",
                "updated_at": "2026-03-31T14:00:00Z",
            },
            {
                "run_id": "slot-4-retry1",
                "request_path": "/tmp/slot-4-retry1.request.json",
                "updated_at": "2026-03-31T14:05:00Z",
            },
            {
                "run_id": "slot-3-base",
                "request_path": "/tmp/slot-3.request.json",
                "updated_at": "2026-03-31T14:04:00Z",
            },
        ]
        ordered = self.module.freshest_runs_by_request_lineage(runs)
        self.assertEqual([item["run_id"] for item in ordered], ["slot-4-retry1", "slot-3-base"])

    def test_narrow_candidate_files_uses_goal_path_hints(self) -> None:
        narrowed = self.module.narrow_candidate_files(
            [
                "docs/TRUTH_SURFACES.md",
                "scripts/_aoa_governed_execution.py",
                "scripts/aoa-governed-run",
                "tests/test_governed_execution.py",
            ],
            goal="Improve scripts/aoa-governed-run status --all and related triage rendering.",
        )
        self.assertEqual(narrowed, ["scripts/aoa-governed-run"])

    def test_apply_edit_spec_in_place_falls_back_to_exact_replace_when_anchor_shape_is_bad(self) -> None:
        target = self.repo_root / "docs" / "target.md"
        target.write_text("alpha\nbeta\nomega\n", encoding="utf-8")
        self.module.apply_edit_spec_in_place(
            self.repo_root,
            selected_target_file="docs/target.md",
            spec={
                "mode": "anchored_replace",
                "target_file": "docs/target.md",
                "anchor_before": "alpha",
                "old_text": "beta",
                "new_text": "gamma",
                "anchor_after": "beta",
            },
        )
        self.assertEqual(target.read_text(encoding="utf-8"), "alpha\ngamma\nomega\n")

    def test_normalize_edit_spec_downgrades_missing_anchor_to_exact_replace(self) -> None:
        normalized = self.module.normalize_edit_spec(
            {
                "mode": "anchored_replace",
                "target_file": "docs/target.md",
                "anchor_before": "alpha",
                "old_text": "beta",
                "new_text": "gamma",
                "anchor_after": "",
            },
            selected_target_file="docs/target.md",
        )
        self.assertEqual(normalized["mode"], "exact_replace")
        self.assertEqual(normalized["old_text"], "beta")
        self.assertEqual(normalized["new_text"], "gamma")

    def test_normalize_edit_spec_rejects_old_text_that_duplicates_anchor(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "duplicate anchored context"):
            self.module.normalize_edit_spec(
                {
                    "mode": "anchored_replace",
                    "target_file": "docs/target.md",
                    "anchor_before": "alpha",
                    "old_text": "beta",
                    "new_text": "gamma",
                    "anchor_after": "beta",
                },
                selected_target_file="docs/target.md",
            )

    def test_normalize_build_router_noop_raw_spec_demotes_duplicate_anchor_to_exact_replace(self) -> None:
        target_text = (self.routing_repo_root / "scripts" / "build_router.py").read_text(encoding="utf-8")
        write_loop = self.module.extract_build_router_write_loop_block(target_text)
        assert write_loop is not None
        normalized = self.module.normalize_build_router_noop_raw_spec(
            {
                "mode": "anchored_replace",
                "target_file": "scripts/build_router.py",
                "anchor_before": self.module.normalize_block_shape(write_loop),
                "anchor_after": "return 0",
                "old_text": self.module.normalize_block_shape(write_loop),
                "new_text": (
                    "for filename, payload in outputs.items():\n"
                    "    path = GENERATED_DIR / filename\n"
                    "    # preserve semantically unchanged payloads\n"
                    "    rendered_text = render_output_text(filename, payload)\n"
                    "    if path.exists():\n"
                    "        try:\n"
                    "            actual_text = path.read_text(encoding=\"utf-8\")\n"
                    "            if filename.endswith(\".jsonl\"):\n"
                    "                actual_payload = [json.loads(line) for line in actual_text.splitlines() if line.strip()]\n"
                    "            else:\n"
                    "                actual_payload = json.loads(actual_text)\n"
                    "            if actual_payload == payload:\n"
                    "                continue\n"
                    "        except json.JSONDecodeError:\n"
                    "            pass\n"
                    "    path.write_text(rendered_text, encoding=\"utf-8\", newline=\"\\n\")\n"
                    "    print(f\"[ok] wrote {relative_posix(path)}\")"
                ),
            },
            target_id="aoa-routing",
            selected_target_file="scripts/build_router.py",
            goal=(
                "Update only `scripts/build_router.py` so its main write loop preserves the existing "
                "on-disk JSON or JSONL text when the parsed file payload already equals the freshly "
                "built payload."
            ),
            target_text=target_text,
        )
        self.assertEqual(normalized["mode"], "exact_replace")
        self.assertEqual(normalized["old_text"], write_loop)
        self.assertNotIn("# preserve semantically unchanged payloads", normalized["new_text"])
        self.assertTrue(normalized["new_text"].startswith("    for filename, payload in outputs.items():"))

    def test_synthesize_build_router_noop_spec_returns_exact_replace(self) -> None:
        target_text = (self.routing_repo_root / "scripts" / "build_router.py").read_text(encoding="utf-8")
        spec = self.module.synthesize_build_router_noop_spec(
            selected_target_file="scripts/build_router.py",
            target_text=target_text,
        )
        self.assertEqual(spec["mode"], "exact_replace")
        self.assertEqual(spec["target_file"], "scripts/build_router.py")
        self.assertIn("path.exists()", spec["new_text"])
        self.assertIn('filename.endswith(".jsonl")', spec["new_text"])
        self.assertIn("json.loads(", spec["new_text"])
        self.assertIn("if actual_payload == payload:", spec["new_text"])
        self.assertIn("continue", spec["new_text"])

    def test_normalize_edit_spec_rejects_partial_python_statement(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "partial Python statement"):
            self.module.normalize_edit_spec(
                {
                    "mode": "exact_replace",
                    "target_file": "scripts/_aoa_governed_execution.py",
                    "old_text": "    latest_blocked =",
                    "new_text": "    latest_blocked = max(runs)",
                },
                selected_target_file="scripts/_aoa_governed_execution.py",
            )

    def test_validate_edit_spec_candidate_rejects_non_applicable_change(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "uniquely applicable"):
            self.module.validate_edit_spec_candidate(
                "alpha\nbeta\n",
                selected_target_file="docs/target.md",
                spec={
                    "mode": "exact_replace",
                    "target_file": "docs/target.md",
                    "old_text": "gamma",
                    "new_text": "delta",
                },
            )

    def test_validate_edit_spec_candidate_rejects_invalid_python_syntax(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "invalid Python syntax"):
            self.module.validate_edit_spec_candidate(
                "value = 1\n",
                selected_target_file="scripts/_aoa_governed_execution.py",
                spec={
                    "mode": "exact_replace",
                    "target_file": "scripts/_aoa_governed_execution.py",
                    "old_text": "value = 1",
                    "new_text": "value =",
                },
            )

    def test_validate_edit_spec_candidate_rejects_unused_python_assignment(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unused Python assignment"):
            self.module.validate_edit_spec_candidate(
                "blocked_runs = []\nreturn blocked_runs\n",
                selected_target_file="scripts/_aoa_governed_execution.py",
                spec={
                    "mode": "exact_replace",
                    "target_file": "scripts/_aoa_governed_execution.py",
                    "old_text": "blocked_runs = []",
                    "new_text": "blocked_runs = []\nlineage_map: dict[str, str] = {}",
                },
            )

    def test_validate_build_router_noop_spec_rejects_check_only_comment_change(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "build_router write loop"):
            self.module.validate_build_router_noop_spec(
                {
                    "mode": "anchored_replace",
                    "target_file": "scripts/build_router.py",
                    "old_text": (
                        "if args.check:\n"
                        "    mismatches = validate_generated_dir_matches_outputs(outputs, generated_dir=generated_dir)\n"
                        "    if mismatches:\n"
                        "        raise RouterError('; '.join(mismatches))\n"
                    ),
                    "new_text": (
                        "if args.check:\n"
                        "    mismatches = validate_generated_dir_matches_outputs(outputs, generated_dir=generated_dir)\n"
                        "    if mismatches:\n"
                        "        raise RouterError('; '.join(mismatches))\n"
                        "    # Skip write if semantically identical\n"
                    ),
                }
            )

    def test_validate_build_router_noop_spec_allows_real_write_loop_logic(self) -> None:
        self.module.validate_build_router_noop_spec(
            {
                "mode": "exact_replace",
                "target_file": "scripts/build_router.py",
                "old_text": (
                    "for filename, payload in outputs.items():\n"
                    "    path = generated_dir / filename\n"
                    "    path.write_text(render_output_text(filename, payload), encoding='utf-8', newline='\\n')\n"
                ),
                "new_text": (
                    "for filename, payload in outputs.items():\n"
                    "    path = generated_dir / filename\n"
                    "    rendered_text = render_output_text(filename, payload)\n"
                    "    if path.exists():\n"
                    "        try:\n"
                    "            actual_text = path.read_text(encoding='utf-8')\n"
                    "            if filename.endswith(\".jsonl\"):\n"
                    "                actual_payload = [json.loads(line) for line in actual_text.splitlines() if line.strip()]\n"
                    "            else:\n"
                    "                actual_payload = json.loads(actual_text)\n"
                    "            if actual_payload == payload:\n"
                    "                continue\n"
                    "        except json.JSONDecodeError:\n"
                    "            pass\n"
                    "    path.write_text(rendered_text, encoding='utf-8', newline='\\n')\n"
                ),
            }
        )

    def test_validate_build_router_noop_spec_rejects_raw_text_only_comparison(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "parsed on-disk payloads"):
            self.module.validate_build_router_noop_spec(
                {
                    "mode": "exact_replace",
                    "target_file": "scripts/build_router.py",
                    "old_text": (
                        "for filename, payload in outputs.items():\n"
                        "    path = generated_dir / filename\n"
                        "    path.write_text(render_output_text(filename, payload), encoding='utf-8', newline='\\n')\n"
                    ),
                    "new_text": (
                        "for filename, payload in outputs.items():\n"
                        "    path = generated_dir / filename\n"
                        "    rendered_text = render_output_text(filename, payload)\n"
                        "    if path.exists():\n"
                        "        try:\n"
                        "            actual_text = path.read_text(encoding='utf-8')\n"
                        "            if filename.endswith(\".jsonl\"):\n"
                        "                actual_payload = [json.loads(line) for line in actual_text.splitlines() if line.strip()]\n"
                        "            else:\n"
                        "                actual_payload = json.loads(actual_text)\n"
                        "            if actual_text == rendered_text:\n"
                        "                continue\n"
                        "        except json.JSONDecodeError:\n"
                        "            pass\n"
                        "    path.write_text(rendered_text, encoding='utf-8', newline='\\n')\n"
                    ),
                }
            )

    def test_validate_build_router_noop_spec_rejects_explanatory_comments(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "must not add explanatory comments"):
            self.module.validate_build_router_noop_spec(
                {
                    "mode": "exact_replace",
                    "target_file": "scripts/build_router.py",
                    "old_text": (
                        "for filename, payload in outputs.items():\n"
                        "    path = generated_dir / filename\n"
                        "    path.write_text(render_output_text(filename, payload), encoding='utf-8', newline='\\n')\n"
                    ),
                    "new_text": (
                        "for filename, payload in outputs.items():\n"
                        "    path = generated_dir / filename\n"
                        "    # Only write when the payload really changed\n"
                        "    rendered_text = render_output_text(filename, payload)\n"
                        "    path.write_text(rendered_text, encoding='utf-8', newline='\\n')\n"
                    ),
                }
            )

    def test_validate_edit_spec_candidate_allows_reassignment_that_is_still_used(self) -> None:
        candidate = self.module.validate_edit_spec_candidate(
            (
                "blocked_runs = []\n"
                "latest_blocked = sorted(blocked_runs, key=lambda item: str(item.get(\"updated_at\") or \"\"), reverse=True)\n"
                "triage_summary = {\n"
                "    \"recommended_action\": latest_blocked[0][\"triage\"][\"recommended_action\"] if latest_blocked else \"No operator action required.\",\n"
                "}\n"
            ),
            selected_target_file="scripts/_aoa_governed_execution.py",
            spec={
                "mode": "exact_replace",
                "target_file": "scripts/_aoa_governed_execution.py",
                "old_text": "latest_blocked = sorted(blocked_runs, key=lambda item: str(item.get(\"updated_at\") or \"\"), reverse=True)",
                "new_text": "latest_blocked = sorted(blocked_runs, key=lambda item: str(item.get(\"request_path\") or item.get(\"updated_at\") or \"\"), reverse=True)",
            },
        )
        self.assertIn("request_path", candidate)
        self.assertIn("latest_blocked[0]", candidate)

    def test_validate_edit_spec_candidate_rejects_unused_assignment_despite_string_mentions(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unused Python assignment"):
            self.module.validate_edit_spec_candidate(
                (
                    "PROMPT_HINT = 'latest_operator_action'\n"
                    "blocked_runs = []\n"
                    "latest_blocked = freshest_runs_by_request_lineage(blocked_runs)\n"
                    "triage_summary = {\n"
                    "    \"recommended_action\": latest_blocked[0][\"triage\"][\"recommended_action\"] if latest_blocked else \"No operator action required.\",\n"
                    "}\n"
                ),
                selected_target_file="scripts/_aoa_governed_execution.py",
                spec={
                    "mode": "exact_replace",
                    "target_file": "scripts/_aoa_governed_execution.py",
                    "old_text": "latest_blocked = freshest_runs_by_request_lineage(blocked_runs)",
                    "new_text": (
                        "latest_blocked = freshest_runs_by_request_lineage(blocked_runs)\n"
                        "latest_operator_action = latest_blocked[0][\"triage\"][\"recommended_action\"] if latest_blocked else None"
                    ),
                },
            )
    def test_parse_json_answer_block_salvages_truncated_string_at_end(self) -> None:
        parsed = self.module.parse_json_answer_block(
            '{"mode":"exact_replace","target_file":"docs/target.md","old_text":"beta","new_text":"gamma'
        )
        self.assertEqual(parsed["mode"], "exact_replace")
        self.assertEqual(parsed["target_file"], "docs/target.md")
        self.assertEqual(parsed["new_text"], "gamma")

    def test_parse_json_answer_block_raises_when_block_cannot_be_salvaged(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            self.module.parse_json_answer_block('{"mode": ')

    def test_normalize_edit_spec_coerces_string_list_new_text(self) -> None:
        normalized = self.module.normalize_edit_spec(
            {
                "mode": "exact_replace",
                "target_file": "docs/target.md",
                "old_text": "beta",
                "new_text": ["gam", "ma"],
            },
            selected_target_file="docs/target.md",
        )
        self.assertEqual(normalized["new_text"], "gamma")

    def test_normalize_edit_spec_coerces_dict_string_wrapper(self) -> None:
        normalized = self.module.normalize_edit_spec(
            {
                "mode": "exact_replace",
                "target_file": "docs/target.md",
                "old_text": {"text": "beta"},
                "new_text": {"content": "gamma"},
            },
            selected_target_file="docs/target.md",
        )
        self.assertEqual(normalized["old_text"], "beta")
        self.assertEqual(normalized["new_text"], "gamma")

    def test_default_proposal_provider_retries_invalid_edit_spec_once(self) -> None:
        context = {
            "request": {
                "goal": "Clarify one bounded docs wording change.",
                "playbook_id": "AOA-P-0011",
                "profile_class": "workhorse",
            },
            "playbook_id": "AOA-P-0011",
            "allowed_files": ["docs/target.md"],
            "advisory_context": {"playbook": {"title": "bounded-change-safe", "summary": "test"}},
            "repo_root": self.repo_root,
            "failure_context": [],
        }
        responses = [
            {"answer": '{"mode":"exact_replace","target_file":"docs/target.md","old_text":"beta"}'},
            {"answer": '{"mode":"exact_replace","target_file":"docs/target.md","old_text":"beta","new_text":"gamma"}'},
        ]
        with patch.object(self.module, "run_federated_prompt", side_effect=responses):
            proposal = self.module.default_proposal_provider(context)
        self.assertEqual(proposal["spec"]["new_text"], "gamma")
        self.assertEqual(proposal["candidate_files"], ["docs/target.md"])
        self.assertIn("Edit proposal attempts: 2.", proposal["notes"])

    def test_default_proposal_provider_skips_target_selection_when_goal_names_single_file(self) -> None:
        context = {
            "request": {
                "goal": "Improve scripts/aoa-governed-run status --all wording only in scripts/aoa-governed-run.",
                "playbook_id": "AOA-P-0018",
                "profile_class": "workhorse",
            },
            "playbook_id": "AOA-P-0018",
            "allowed_files": ["scripts/_aoa_governed_execution.py", "scripts/aoa-governed-run"],
            "advisory_context": {"playbook": {"title": "governed-lane", "summary": "test"}},
            "repo_root": self.repo_root,
            "failure_context": [],
        }
        (self.repo_root / "scripts" / "aoa-governed-run").write_text("alpha\nbeta\n", encoding="utf-8")
        with patch.object(
            self.module,
            "run_federated_prompt",
            return_value={
                "answer": '{"mode":"exact_replace","target_file":"scripts/aoa-governed-run","old_text":"beta","new_text":"gamma"}'
            },
        ) as mocked:
            proposal = self.module.default_proposal_provider(context)
        self.assertEqual(proposal["selected_target_file"], "scripts/aoa-governed-run")
        self.assertEqual(proposal["candidate_files"], ["scripts/aoa-governed-run"])
        self.assertEqual(mocked.call_count, 1)
        self.assertIn("Target candidate count: 1.", proposal["notes"])

    def test_default_proposal_provider_uses_deterministic_build_router_noop_patch(self) -> None:
        context = {
            "request": {
                "goal": (
                    "Update only `scripts/build_router.py` so its main write loop preserves the existing "
                    "on-disk JSON or JSONL text when the parsed file payload already equals the freshly "
                    "built payload. This must stop no-op `python scripts/build_router.py` from dirtying "
                    "semantically unchanged `generated/two_stage_*` and "
                    "`generated/two_stage_skill_entrypoints.json`, without changing thin-router meaning "
                    "or editing generated files directly."
                ),
                "target_id": "aoa-routing",
                "playbook_id": "AOA-P-0011",
                "profile_class": "workhorse",
            },
            "playbook_id": "AOA-P-0011",
            "allowed_files": [
                "README.md",
                "generated/*.json",
                "generated/*.jsonl",
                "scripts/build_router.py",
                "scripts/validate_router.py",
                "tests/test_build_router.py",
            ],
            "advisory_context": {"playbook": {"title": "bounded-change-safe", "summary": "test"}},
            "repo_root": self.routing_repo_root,
            "failure_context": [],
        }
        with patch.object(self.module, "run_federated_prompt") as mocked:
            proposal = self.module.default_proposal_provider(context)
        self.assertEqual(proposal["provider"], "deterministic-build-router-noop")
        self.assertEqual(proposal["selected_target_file"], "scripts/build_router.py")
        self.assertEqual(proposal["spec"]["mode"], "exact_replace")
        self.assertEqual(mocked.call_count, 0)
        self.assertIn("Synthesized deterministic build_router no-op write-loop patch.", proposal["notes"])

    def test_default_proposal_provider_uses_deterministic_routing_roadmap_patch(self) -> None:
        (self.routing_repo_root / "ROADMAP.md").write_text(
            textwrap.dedent(
                """\
                ## Milestone 7

                - schema-backed validation that orientation never points authority at route-owned generated surfaces
                - a narrow handoff
                """
            ),
            encoding="utf-8",
        )
        context = {
            "request": {
                "goal": (
                    "Update aoa-routing ROADMAP only so the generated-surface refresh lane is described as "
                    "router-owned parity maintenance that keeps thin-router boundaries intact and does not "
                    "transfer authority from sibling source repos."
                ),
                "target_id": "aoa-routing",
                "playbook_id": "AOA-P-0011",
                "profile_class": "workhorse",
            },
            "playbook_id": "AOA-P-0011",
            "allowed_files": [
                "README.md",
                "ROADMAP.md",
                "docs/*.md",
                "docs/**/*.md",
                "generated/*.json",
                "generated/*.jsonl",
                "scripts/build_router.py",
                "scripts/validate_router.py",
                "tests/test_build_router.py",
            ],
            "advisory_context": {"playbook": {"title": "bounded-change-safe", "summary": "test"}},
            "repo_root": self.routing_repo_root,
            "failure_context": [],
        }
        with patch.object(self.module, "run_federated_prompt") as mocked:
            proposal = self.module.default_proposal_provider(context)
        self.assertEqual(proposal["provider"], "deterministic-routing-roadmap-generated-surface")
        self.assertEqual(proposal["selected_target_file"], "ROADMAP.md")
        self.assertEqual(proposal["spec"]["mode"], "exact_replace")
        self.assertEqual(mocked.call_count, 0)
        self.assertIn(
            "Synthesized deterministic aoa-routing ROADMAP generated-surface boundary wording patch.",
            proposal["notes"],
        )

    def test_policy_parsing_and_playbook_lookup(self) -> None:
        policy, _ = self.module.load_policy(self.policy_path)
        entry = self.module.resolve_playbook_policy(policy, "AOA-P-0011", "abyss-stack")
        self.assertTrue(entry["enabled"])
        self.assertEqual(entry["allowed_files"], ["docs/target.md"])
        self.assertEqual(entry["trust_state"], "experimental")

    def test_prepare_canary_request_materializes_catalog_entry(self) -> None:
        payload = self.module.request_from_canary(
            "docs-truth-wording-alignment",
            catalog_path=self.canary_catalog_path,
            repo_root=self.repo_root,
        )
        self.assertEqual(payload["playbook_id"], "AOA-P-0011")
        self.assertEqual(payload["target_id"], "abyss-stack")
        self.assertEqual(payload["task_class"], "docs_only")
        self.assertEqual(payload["canary_id"], "docs-truth-wording-alignment")

        materialized = self.module.materialize_canary_requests(
            self.root / "materialized-canaries",
            catalog_path=self.canary_catalog_path,
        )
        self.assertEqual(materialized["request_count"], 3)
        request_file = Path(materialized["requests"][0]["request_file"])
        self.assertTrue(request_file.exists())
        self.assertEqual(materialized["requests"][0]["target_id"], "abyss-stack")

    def test_request_from_canary_rejects_wrong_repo_override_for_target(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "repo_root does not match governed target aoa-routing"):
            self.module.request_from_canary(
                "routing-boundary-wording-alignment",
                catalog_path=self.canary_catalog_path,
                repo_root=self.repo_root,
            )

    def test_fail_closed_gate_mapping(self) -> None:
        policy, _ = self.module.load_policy(self.policy_path)
        entry = self.module.resolve_playbook_policy(policy, "AOA-P-0011", "abyss-stack")
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
        entry = self.module.resolve_playbook_policy(policy, "AOA-P-0011", "abyss-stack")

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
        self.assertTrue(self.module.path_allowed("README.md", ["README.md"]))
        self.assertTrue(self.module.path_allowed("docs/target.md", ["docs/target.md"]))
        self.assertTrue(self.module.path_allowed("generated/aoa_router.min.json", ["generated/*.json"]))
        self.assertFalse(self.module.path_allowed("scripts/validate_stack.py", ["docs/target.md"]))
        self.assertFalse(self.module.path_allowed("tests/fixtures/Agents-of-Abyss/README.md", ["README.md"]))
        self.assertFalse(
            self.module.path_allowed(
                "tests/fixtures/aoa-skills/generated/skill_catalog.min.json",
                ["generated/*.json"],
            )
        )

    def test_candidate_path_hints_from_goal_extracts_paths_from_backtick_commands(self) -> None:
        hints = self.module.candidate_path_hints_from_goal(
            "Document `python scripts/build_router.py --check` in README only without widening scope."
        )
        self.assertEqual(hints, ["scripts/build_router.py"])

    def test_narrow_candidate_files_prefers_exclusive_readme_goal(self) -> None:
        narrowed = self.module.narrow_candidate_files(
            ["README.md", "scripts/build_router.py", "docs/FEDERATION_ENTRY_ABI.md"],
            goal="Update README only so the Build and validate section documents `python scripts/build_router.py --check`.",
        )
        self.assertEqual(narrowed, ["README.md"])

    def test_narrow_candidate_files_prefers_explicit_only_path_before_generated_mentions(self) -> None:
        narrowed = self.module.narrow_candidate_files(
            ["generated/two_stage_skill_entrypoints.json", "scripts/build_router.py"],
            goal=(
                "Update only `scripts/build_router.py` so its main write loop preserves the existing "
                "on-disk JSON or JSONL text when the parsed file payload already equals the freshly "
                "built payload. This must stop no-op `python scripts/build_router.py` from dirtying "
                "semantically unchanged `generated/two_stage_*` and `generated/two_stage_skill_entrypoints.json`."
            ),
        )
        self.assertEqual(narrowed, ["scripts/build_router.py"])

    def test_extract_markdown_section_excerpt_prefers_named_section(self) -> None:
        readme_text = (
            "# aoa-routing\n\n"
            "Intro.\n\n"
            "## Build and validate\n\n"
            "Run `python scripts/build_router.py`.\n\n"
            "## Other section\n\n"
            "Leave this alone.\n"
        )
        excerpt = self.module.extract_markdown_section_excerpt(
            readme_text,
            goal="Update README only so the Build and validate section documents `python scripts/build_router.py --check`.",
            char_limit=400,
        )
        self.assertIsNotNone(excerpt)
        self.assertIn("## Build and validate", excerpt)
        self.assertIn("python scripts/build_router.py", excerpt)
        self.assertNotIn("## Other section", excerpt)

    def test_normalize_edit_spec_demotes_markdown_insertion_anchor_to_exact_replace(self) -> None:
        normalized = self.module.normalize_edit_spec(
            {
                "mode": "anchored_replace",
                "target_file": "README.md",
                "anchor_before": "Validate the generated outputs:\n\n```bash\npython scripts/validate_router.py\n```",
                "anchor_after": "The optional wave-9 seam can also be exercised directly:",
                "old_text": "Validate the generated outputs:\n\n```bash\npython scripts/validate_router.py\n```",
                "new_text": (
                    "Validate the generated outputs:\n\n```bash\npython scripts/validate_router.py\n```\n\n"
                    "Check canonical parity:\n\n```bash\npython scripts/build_router.py --check\n```"
                ),
            },
            selected_target_file="README.md",
        )
        self.assertEqual(normalized["mode"], "exact_replace")
        self.assertEqual(normalized["target_file"], "README.md")

    def test_enumerate_allowed_candidates_respects_root_anchored_patterns(self) -> None:
        fixture_readme = self.routing_repo_root / "tests" / "fixtures" / "nested" / "README.md"
        fixture_generated = (
            self.routing_repo_root / "tests" / "fixtures" / "nested" / "generated" / "router.min.json"
        )
        fixture_generated.parent.mkdir(parents=True, exist_ok=True)
        fixture_readme.write_text("fixture\n", encoding="utf-8")
        fixture_generated.write_text("{\"fixture\": true}\n", encoding="utf-8")

        candidates = self.module.enumerate_allowed_candidates(
            self.routing_repo_root,
            ["README.md", "generated/*.json"],
        )
        self.assertIn("README.md", candidates)
        self.assertIn("generated/aoa_router.min.json", candidates)
        self.assertNotIn("tests/fixtures/nested/README.md", candidates)
        self.assertNotIn("tests/fixtures/nested/generated/router.min.json", candidates)

    def test_prepare_run_fails_closed_on_wrong_target_root_pairing(self) -> None:
        request_path = self.root / "routing-mismatch.request.json"
        write_json(request_path, governed_request(self.repo_root, target_id="aoa-routing"))
        result = self.module.prepare_run(
            request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=lambda: self.gate_payload(),
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["failure_class"], "policy_denied")
        self.assertIn("repo_root does not match governed target aoa-routing", " ".join(result["reasons"]))

    def test_external_target_run_succeeds_against_routing_checkout(self) -> None:
        request_path = self.root / "routing.request.json"
        write_json(request_path, governed_request(self.routing_repo_root, target_id="aoa-routing"))
        result = self.module.prepare_run(
            request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=lambda: self.gate_payload(),
            advisory_provider=self.advisory_provider,
            proposal_provider=self.proposal_provider,
        )
        self.assertEqual(result["status"], "paused")
        self.assertEqual(result["current_milestone"], "plan_freeze")
        run_dir = self.logs_root / result["run_id"]
        state = json.loads((run_dir / "run.state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["target_id"], "aoa-routing")
        self.assertEqual(state["repo_root"], str(self.routing_repo_root))

    def test_external_generated_surface_run_keeps_semantically_unchanged_outputs_git_stable(self) -> None:
        request_path = self.root / "routing-generated.request.json"
        write_json(
            request_path,
            {
                "goal": (
                    "Update only `scripts/build_router.py` so its main write loop preserves the existing "
                    "on-disk JSON or JSONL text when the parsed file payload already equals the freshly "
                    "built payload. This must stop no-op `python scripts/build_router.py` from dirtying "
                    "semantically unchanged `generated/two_stage_*` and "
                    "`generated/two_stage_skill_entrypoints.json`, without changing thin-router meaning "
                    "or editing generated files directly."
                ),
                "target_id": "aoa-routing",
                "playbook_id": "AOA-P-0011",
                "task_class": "generated_surface",
                "profile_class": "workhorse",
                "repo_root": str(self.routing_repo_root),
                "memo": None,
                "break_glass_reason": None,
            },
        )
        build_router_path = self.routing_repo_root / "scripts" / "build_router.py"
        build_router_text = build_router_path.read_text(encoding="utf-8")
        write_loop = self.module.extract_build_router_write_loop_block(build_router_text)
        assert write_loop is not None

        def generated_surface_provider(context: dict) -> dict:
            spec = {
                "mode": "exact_replace",
                "target_file": "scripts/build_router.py",
                "old_text": write_loop,
                "new_text": (
                    "    for filename, payload in outputs.items():\n"
                    "        path = GENERATED_DIR / filename\n"
                    "        rendered_text = render_output_text(filename, payload)\n"
                    "        if path.exists():\n"
                    "            try:\n"
                    "                actual_text = path.read_text(encoding=\"utf-8\")\n"
                    "                if filename.endswith(\".jsonl\"):\n"
                    "                    actual_payload = [\n"
                    "                        json.loads(line)\n"
                    "                        for line in actual_text.splitlines()\n"
                    "                        if line.strip()\n"
                    "                    ]\n"
                    "                else:\n"
                    "                    actual_payload = json.loads(actual_text)\n"
                    "                if actual_payload == payload:\n"
                    "                    continue\n"
                    "            except json.JSONDecodeError:\n"
                    "                pass\n"
                    "        path.write_text(rendered_text, encoding=\"utf-8\", newline=\"\\n\")\n"
                    "        print(f\"[ok] wrote {relative_posix(path)}\")"
                ),
            }
            return {
                "provider": "fixture",
                "selected_target_file": "scripts/build_router.py",
                "spec": spec,
                "candidate_files": ["scripts/build_router.py"],
                "target_prompt": "",
                "edit_prompt": "",
                "target_answer": "{\"target_file\":\"scripts/build_router.py\"}",
                "edit_answer": json.dumps(spec, ensure_ascii=True),
                "notes": [],
            }

        first = self.module.prepare_run(
            request_path,
            policy_path=self.policy_path,
            log_root=self.logs_root,
            gate_provider=lambda: self.gate_payload(),
            advisory_provider=self.advisory_provider,
            proposal_provider=generated_surface_provider,
        )
        self.assertEqual(first["status"], "paused")
        self.assertEqual(first["current_milestone"], "plan_freeze")
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
            proposal_provider=generated_surface_provider,
        )
        self.assertEqual(second["status"], "paused")
        self.assertEqual(second["current_milestone"], "landing")

        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["current_milestone"] = "landing"
        approval["status"] = "approved"
        approval["approved"] = True
        approval["milestones"]["landing"]["status"] = "approved"
        approval["milestones"]["landing"]["approved"] = True
        write_json(approval_path, approval)

        third = self.module.resume_run(run_id, log_root=self.logs_root)
        self.assertEqual(third["status"], "pass")
        subprocess.run(
            ["python", "scripts/build_router.py"],
            cwd=self.routing_repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        generated_diff = subprocess.run(
            ["git", "diff", "--name-only", "--", "generated"],
            cwd=self.routing_repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(generated_diff.stdout.strip(), "")

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

    def test_materialize_review_packets_emits_manifest_and_private_candidate_refs(self) -> None:
        stack_root = self.install_review_packet_runtime_surfaces()
        run_dir = self.logs_root / "run-review-packets"
        run_dir.mkdir(parents=True, exist_ok=True)
        request = {
            "goal": "Review bounded change safe adoption.",
            "playbook_id": "AOA-P-0011",
            "repo_root": str(self.repo_root),
        }
        state = {
            "run_id": "run-review-packets",
            "playbook_id": "AOA-P-0011",
            "changed_files": ["docs/target.md"],
        }
        advisory_context = {
            "playbook_id": "AOA-P-0011",
            "playbook": {
                "playbook_id": "AOA-P-0011",
                "name": "bounded-change-safe",
                "review_packet_contract": {
                    "playbook_id": "AOA-P-0011",
                    "playbook_name": "bounded-change-safe",
                    "scenario": "bounded_change_safe",
                    "expected_artifacts": ["approval_record", "verification_pack"],
                    "eval_anchors": ["aoa-approval-boundary-adherence"],
                    "memo_runtime_surfaces": ["approval_record"],
                    "candidate_packet_kinds": [
                        "memo_candidate",
                        "runtime_evidence_selection_candidate",
                        "artifact_hook_candidate",
                    ],
                    "review_required": True,
                    "source_review_refs": ["playbooks/bounded-change-safe/PLAYBOOK.md"],
                    "gate_verdict": "hold",
                },
            },
        }

        with patch.object(
            self.module,
            "default_review_packet_trace_provider",
            return_value={
                "selectors": {"playbook_id": "AOA-P-0011", "profile_class": "workhorse"},
                "playbook": {
                    "summary": {"playbook_id": "AOA-P-0011", "name": "bounded-change-safe"},
                    "review_packet_contract": advisory_context["playbook"]["review_packet_contract"],
                },
            },
        ):
            status = self.module.materialize_review_packets(
                run_dir,
                request=request,
                state=state,
                advisory_context=advisory_context,
            )

        self.assertTrue(status["ready"])
        self.assertEqual(status["emitted_candidate_artifact_count"], 3)
        manifest = json.loads((run_dir / "artifacts" / "review_packet_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["selected_playbook"]["playbook_id"], "AOA-P-0011")
        self.assertEqual(len(manifest["matched_eval_template_entries"]), 2)
        self.assertEqual(len(manifest["matched_memo_writeback_targets"]), 1)
        self.assertEqual(len(manifest["emitted_candidate_artifact_refs"]), 3)
        self.assertTrue((stack_root / "Logs" / "memo-exports" / "latest" / "approval_record.private.json").exists())
        self.assertTrue(
            (
                stack_root
                / "Logs"
                / "eval-exports"
                / "latest"
                / "runtime-evidence-selection"
                / "run-review-packets--workhorse-q4-vs-q6-latency-tradeoff.private.json"
            ).exists()
        )
        hook_ref = next(
            entry["artifact_ref"]
            for entry in manifest["emitted_candidate_artifact_refs"]
            if entry["packet_kind"] == "artifact_hook_candidate"
        )
        self.assertIn(str(stack_root), hook_ref)
        self.assertNotIn("/srv/abyss-stack", hook_ref)

    def test_materialize_review_packets_records_skipped_packet_reasons(self) -> None:
        self.install_review_packet_runtime_surfaces(include_eval_templates=False, include_memo_target=False)
        run_dir = self.logs_root / "run-review-packets-skipped"
        run_dir.mkdir(parents=True, exist_ok=True)
        request = {
            "goal": "Review bounded change safe adoption.",
            "playbook_id": "AOA-P-0011",
            "repo_root": str(self.repo_root),
        }
        state = {
            "run_id": "run-review-packets-skipped",
            "playbook_id": "AOA-P-0011",
            "changed_files": ["docs/target.md"],
        }

        status = self.module.materialize_review_packets(
            run_dir,
            request=request,
            state=state,
            advisory_context={"playbook_id": "AOA-P-0011"},
        )

        self.assertTrue(status["ready"])
        self.assertEqual(status["emitted_candidate_artifact_count"], 0)
        manifest = json.loads((run_dir / "artifacts" / "review_packet_manifest.json").read_text(encoding="utf-8"))
        reasons = {entry["packet_kind"]: entry["reason"] for entry in manifest["skipped_packet_kinds"]}
        self.assertEqual(reasons["memo_candidate"], "no_matched_memo_writeback_targets")
        self.assertEqual(reasons["runtime_evidence_selection_candidate"], "no_runtime_evidence_selection_templates")
        self.assertEqual(reasons["artifact_hook_candidate"], "no_artifact_hook_templates")

    def test_audit_review_packets_emits_review_packet_audit_for_complete_run(self) -> None:
        self.install_review_packet_runtime_surfaces()
        run_dir = self.logs_root / "run-review-packets-audit"
        run_dir.mkdir(parents=True, exist_ok=True)
        request = {
            "goal": "Review bounded change safe adoption.",
            "playbook_id": "AOA-P-0011",
            "repo_root": str(self.repo_root),
        }
        state = {
            "run_id": "run-review-packets-audit",
            "playbook_id": "AOA-P-0011",
            "changed_files": ["docs/target.md"],
            "status": "pass",
        }

        with patch.object(
            self.module,
            "default_review_packet_trace_provider",
            return_value={
                "selectors": {"playbook_id": "AOA-P-0011", "profile_class": "workhorse"},
                "playbook": {"summary": {"playbook_id": "AOA-P-0011", "name": "bounded-change-safe"}},
            },
        ):
            self.module.materialize_review_packets(
                run_dir,
                request=request,
                state=state,
                advisory_context={"playbook_id": "AOA-P-0011"},
            )

        audit = self.module.audit_review_packets(run_dir, state=state)
        self.assertEqual(audit["audit_verdict"], "ready")
        self.assertTrue((run_dir / "artifacts" / "review_packet_audit.json").exists())
        self.assertEqual(
            audit["contract_refs"],
            [
                "aoa-playbooks/generated/playbook_review_packet_contracts.min.json",
                "aoa-evals/generated/runtime_candidate_template_index.min.json",
                "aoa-memo/generated/runtime_writeback_targets.min.json",
            ],
        )
        recommended_targets = {(item["owner_repo"], item["ref"]) for item in audit["recommended_review_targets"]}
        self.assertIn(("aoa-playbooks", "playbooks/bounded-change-safe/PLAYBOOK.md"), recommended_targets)
        self.assertIn(
            ("aoa-evals", "examples/artifact_to_verdict_hook.self-agent-checkpoint-rollout.example.json"),
            recommended_targets,
        )
        self.assertIn(("aoa-memo", "docs/MEMORY_MODEL.md#approval-record"), recommended_targets)

    def test_audit_review_packets_blocks_when_emitted_artifact_is_missing(self) -> None:
        stack_root = self.install_review_packet_runtime_surfaces()
        run_dir = self.logs_root / "run-review-packets-blocked"
        run_dir.mkdir(parents=True, exist_ok=True)
        request = {
            "goal": "Review bounded change safe adoption.",
            "playbook_id": "AOA-P-0011",
            "repo_root": str(self.repo_root),
        }
        state = {
            "run_id": "run-review-packets-blocked",
            "playbook_id": "AOA-P-0011",
            "changed_files": ["docs/target.md"],
            "status": "pass",
        }

        with patch.object(
            self.module,
            "default_review_packet_trace_provider",
            return_value={
                "selectors": {"playbook_id": "AOA-P-0011", "profile_class": "workhorse"},
                "playbook": {"summary": {"playbook_id": "AOA-P-0011", "name": "bounded-change-safe"}},
            },
        ):
            self.module.materialize_review_packets(
                run_dir,
                request=request,
                state=state,
                advisory_context={"playbook_id": "AOA-P-0011"},
            )

        (stack_root / "Logs" / "memo-exports" / "latest" / "approval_record.private.json").unlink()
        audit = self.module.audit_review_packets(run_dir, state=state)
        self.assertEqual(audit["audit_verdict"], "blocked")
        memo_status = next(entry for entry in audit["packet_statuses"] if entry["packet_kind"] == "memo_candidate")
        self.assertEqual(memo_status["status"], "stale")
        self.assertIn("approval_record.private.json", memo_status["reason"])

    def test_replay_review_packets_refreshes_manifest_and_audit_without_federated_rerun(self) -> None:
        self.install_review_packet_runtime_surfaces()
        run_id = "run-review-packets-replay"
        run_dir = self.logs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            run_dir / "request.json",
            {
                "goal": "Review bounded change safe adoption.",
                "playbook_id": "AOA-P-0011",
                "repo_root": str(self.repo_root),
            },
        )
        write_json(
            run_dir / "preflight.summary.json",
            {
                "advisory_context": {
                    "playbook_id": "AOA-P-0011",
                    "playbook": {"playbook_id": "AOA-P-0011", "name": "bounded-change-safe"},
                }
            },
        )
        write_json(
            run_dir / "run.state.json",
            {
                "run_id": run_id,
                "target_id": "abyss-stack",
                "repo_root": str(self.repo_root),
                "playbook_id": "AOA-P-0011",
                "task_class": "docs_only",
                "trust_state_snapshot": "canary_proven",
                "phase": "completed",
                "status": "pass",
                "base_head": "abc123",
                "changed_files": ["docs/target.md"],
            },
        )
        write_json(
            run_dir / "result.summary.json",
            {
                "artifact_kind": "aoa.governed-run.result-summary",
                "schema_version": "v1",
                "run_id": run_id,
                "updated_at": "2026-04-01T00:00:00Z",
                "status": "pass",
                "phase": "completed",
                "break_glass_used": False,
                "next_action": "Governed execution landed successfully.",
            },
        )
        write_json(
            run_dir / "artifacts" / "advisory_trace.json",
            {
                "trace_source": "stored-advisory",
                "selectors": {"playbook_id": "AOA-P-0011"},
                "playbook": {"summary": {"playbook_id": "AOA-P-0011", "name": "bounded-change-safe"}},
            },
        )

        with patch.object(
            self.module,
            "default_review_packet_trace_provider",
            side_effect=AssertionError("replay should not rerun federated advisory"),
        ):
            payload = self.module.replay_review_packets(run_id, log_root=self.logs_root)

        self.assertIn("review_packets", payload)
        self.assertEqual(payload["audit_verdict"], "ready")
        self.assertTrue((run_dir / "artifacts" / "review_packet_manifest.json").exists())
        self.assertTrue((run_dir / "artifacts" / "review_packet_audit.json").exists())
        summary = json.loads((run_dir / "result.summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["review_packets"]["audit_verdict"], "ready")
        self.assertEqual(
            summary["review_packets"]["safe_replay_command"],
            f"scripts/aoa-governed-run replay-review-packets {run_id}",
        )

    def test_handoff_brief_emits_review_handoff_bundle_for_complete_run(self) -> None:
        self.install_review_packet_runtime_surfaces()
        run_id = "run-review-handoff"
        run_dir = self.logs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            run_dir / "request.json",
            {
                "goal": "Review bounded change safe adoption.",
                "playbook_id": "AOA-P-0011",
                "repo_root": str(self.repo_root),
            },
        )
        write_json(
            run_dir / "preflight.summary.json",
            {
                "advisory_context": {
                    "playbook_id": "AOA-P-0011",
                    "playbook": {"playbook_id": "AOA-P-0011", "name": "bounded-change-safe"},
                }
            },
        )
        state = {
            "run_id": run_id,
            "target_id": "abyss-stack",
            "repo_root": str(self.repo_root),
            "playbook_id": "AOA-P-0011",
            "task_class": "docs_only",
            "trust_state_snapshot": "canary_proven",
            "phase": "completed",
            "status": "pass",
            "base_head": "abc123",
            "changed_files": ["docs/target.md"],
        }
        write_json(run_dir / "run.state.json", state)
        write_json(
            run_dir / "artifacts" / "advisory_trace.json",
            {
                "selectors": {"playbook_id": "AOA-P-0011"},
                "playbook": {"summary": {"playbook_id": "AOA-P-0011", "name": "bounded-change-safe"}},
            },
        )
        with patch.object(
            self.module,
            "default_review_packet_trace_provider",
            return_value={
                "selectors": {"playbook_id": "AOA-P-0011", "profile_class": "workhorse"},
                "playbook": {"summary": {"playbook_id": "AOA-P-0011", "name": "bounded-change-safe"}},
            },
        ):
            self.module.materialize_review_packets(
                run_dir,
                request={
                    "goal": "Review bounded change safe adoption.",
                    "playbook_id": "AOA-P-0011",
                    "repo_root": str(self.repo_root),
                },
                state=state,
                advisory_context={"playbook_id": "AOA-P-0011"},
            )

        payload = self.module.handoff_brief_run(run_id, log_root=self.logs_root)
        bundle = json.loads((run_dir / "artifacts" / "review_handoff_bundle.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["handoff_readiness"], "ready")
        self.assertEqual(bundle["playbook_id"], "AOA-P-0011")
        self.assertEqual(bundle["audit_verdict"], "ready")
        self.assertIn("aoa-playbooks", bundle["recommended_review_targets"])
        self.assertIn("aoa-evals", bundle["recommended_review_targets"])
        self.assertIn("aoa-memo", bundle["recommended_review_targets"])
        self.assertTrue(bundle["operator_next_steps"])
        self.assertEqual(
            [entry["template_name"] for entry in bundle["eval_intake_entries"]],
            [
                "aoa-p-0011-approval-boundary-hook",
                "workhorse-q4-vs-q6-latency-tradeoff",
            ],
        )

    def test_handoff_brief_degrades_when_runtime_writeback_intake_surface_is_missing(self) -> None:
        stack_root = self.install_review_packet_runtime_surfaces()
        run_id = "run-review-handoff-blocked"
        run_dir = self.logs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            run_dir / "request.json",
            {
                "goal": "Review bounded change safe adoption.",
                "playbook_id": "AOA-P-0011",
                "repo_root": str(self.repo_root),
            },
        )
        write_json(
            run_dir / "preflight.summary.json",
            {
                "advisory_context": {
                    "playbook_id": "AOA-P-0011",
                    "playbook": {"playbook_id": "AOA-P-0011", "name": "bounded-change-safe"},
                }
            },
        )
        state = {
            "run_id": run_id,
            "target_id": "abyss-stack",
            "repo_root": str(self.repo_root),
            "playbook_id": "AOA-P-0011",
            "task_class": "docs_only",
            "trust_state_snapshot": "canary_proven",
            "phase": "completed",
            "status": "pass",
            "base_head": "abc123",
            "changed_files": ["docs/target.md"],
        }
        write_json(run_dir / "run.state.json", state)
        with patch.object(
            self.module,
            "default_review_packet_trace_provider",
            return_value={
                "selectors": {"playbook_id": "AOA-P-0011", "profile_class": "workhorse"},
                "playbook": {"summary": {"playbook_id": "AOA-P-0011", "name": "bounded-change-safe"}},
            },
        ):
            self.module.materialize_review_packets(
                run_dir,
                request={
                    "goal": "Review bounded change safe adoption.",
                    "playbook_id": "AOA-P-0011",
                    "repo_root": str(self.repo_root),
                },
                state=state,
                advisory_context={"playbook_id": "AOA-P-0011"},
            )

        (
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-memo"
            / "generated"
            / "runtime_writeback_intake.min.json"
        ).unlink()
        payload = self.module.handoff_brief_run(run_id, log_root=self.logs_root)
        bundle = payload["review_handoff_bundle"]

        self.assertEqual(payload["handoff_readiness"], "blocked")
        self.assertEqual(bundle["audit_verdict"], "ready")
        reasons = {
            (entry["packet_kind"], entry["status"]): entry["reason"]
            for entry in bundle["missing_or_blocked_packet_kinds"]
        }
        self.assertIn(("memo_writeback_intake", "missing"), reasons)
        self.assertIn("runtime_writeback_intake", reasons[("memo_writeback_intake", "missing")])

    def test_review_packet_eval_template_matches_skip_non_matching_scoped_evidence_templates(self) -> None:
        stack_root = self.install_review_packet_runtime_surfaces()
        template_index_path = (
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-evals"
            / "generated"
            / "runtime_candidate_template_index.min.json"
        )
        payload = json.loads(template_index_path.read_text(encoding="utf-8"))
        payload["templates"].extend(
            [
                {
                    "template_kind": "runtime_evidence_selection",
                    "template_name": "foreign-playbook-evidence",
                    "playbook_id": "AOA-P-9999",
                    "eval_anchor": "aoa-foreign-anchor",
                    "verdict_bundle_ref": None,
                    "required_runtime_artifacts": ["summary"],
                    "review_required": True,
                    "source_example_ref": "examples/runtime_evidence_selection.foreign-playbook.example.json",
                },
                {
                    "template_kind": "runtime_evidence_selection",
                    "template_name": "foreign-anchor-evidence",
                    "playbook_id": None,
                    "eval_anchor": "aoa-foreign-anchor",
                    "verdict_bundle_ref": None,
                    "required_runtime_artifacts": ["summary"],
                    "review_required": True,
                    "source_example_ref": "examples/runtime_evidence_selection.foreign-anchor.example.json",
                },
            ]
        )
        write_json(template_index_path, payload)
        contract = self.module.playbook_review_packet_contract_by_id("AOA-P-0011")

        hook_templates, evidence_templates = self.module.review_packet_eval_template_matches(
            "AOA-P-0011",
            contract,
        )

        self.assertEqual([entry["template_name"] for entry in hook_templates], ["aoa-p-0011-approval-boundary-hook"])
        self.assertEqual(
            [entry["template_name"] for entry in evidence_templates],
            ["workhorse-q4-vs-q6-latency-tradeoff"],
        )

    def test_pass_result_persists_review_packet_summary_for_status_explain(self) -> None:
        self.install_review_packet_runtime_surfaces()
        run_dir = self.logs_root / "run-pass-summary"
        run_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            run_dir / "request.json",
            {
                "goal": "Review bounded change safe adoption.",
                "playbook_id": "AOA-P-0011",
                "repo_root": str(self.repo_root),
            },
        )
        write_json(
            run_dir / "preflight.summary.json",
            {
                "advisory_context": {
                    "playbook_id": "AOA-P-0011",
                    "playbook": {
                        "playbook_id": "AOA-P-0011",
                        "name": "bounded-change-safe",
                    },
                }
            },
        )
        state = {
            "run_id": "run-pass-summary",
            "target_id": "abyss-stack",
            "repo_root": str(self.repo_root),
            "playbook_id": "AOA-P-0011",
            "task_class": "docs_only",
            "trust_state_snapshot": "canary_proven",
            "phase": "apply_main",
            "status": "running",
            "base_head": "abc123",
            "break_glass_used": False,
            "changed_files": ["docs/target.md"],
        }
        write_json(run_dir / "run.state.json", state)
        write_json(
            run_dir / "approval.status.json",
            {
                "run_id": "run-pass-summary",
                "base_head": "abc123",
                "current_milestone": "landing",
                "status": "approved",
                "milestones": {
                    "plan_freeze": {"status": "approved", "approved": True},
                    "landing": {"status": "approved", "approved": True},
                },
            },
        )

        with patch.object(
            self.module,
            "default_review_packet_trace_provider",
            return_value={
                "selectors": {"playbook_id": "AOA-P-0011", "profile_class": "workhorse"},
                "playbook": {"summary": {"playbook_id": "AOA-P-0011", "name": "bounded-change-safe"}},
            },
        ):
            summary = self.module.pass_result(run_dir, state=state, changed_files=["docs/target.md"])

        self.assertTrue(summary["review_packets"]["ready"])
        self.assertEqual(summary["review_packets"]["audit_verdict"], "ready")
        self.assertTrue(summary["review_packets"]["audit_ref"].endswith("review_packet_audit.json"))
        self.assertEqual(
            summary["review_packets"]["safe_replay_command"],
            "scripts/aoa-governed-run replay-review-packets run-pass-summary",
        )
        self.assertTrue(summary["review_packets"]["recommended_review_targets"])
        status_payload = self.module.status_run("run-pass-summary", log_root=self.logs_root)
        self.assertEqual(status_payload["review_packet_audit"]["audit_verdict"], "ready")
        rendered = self.module.render_status_explain(status_payload)
        self.assertIn("review_packet_ready", rendered)
        self.assertIn("review_packet_manifest.json", rendered)
        self.assertIn("audit_verdict", rendered)
        self.assertIn("safe_replay_command", rendered)
        self.assertIn("playbooks/bounded-change-safe/PLAYBOOK.md", rendered)

        handoff_payload = self.module.handoff_brief_run("run-pass-summary", log_root=self.logs_root)
        self.assertEqual(handoff_payload["handoff_readiness"], "ready")
        status_payload = self.module.status_run("run-pass-summary", log_root=self.logs_root)
        rendered = self.module.render_status_explain(status_payload)
        self.assertIn("review_handoff_bundle.json", rendered)
        self.assertIn("handoff_readiness", rendered)
        self.assertIn("grouped_review_targets", rendered)
        self.assertIn("docs/RUNTIME_WRITEBACK_SEAM.md", rendered)

    def test_render_status_explain_uses_handoff_bundle_readiness_fallback(self) -> None:
        rendered = self.module.render_status_explain(
            {
                "run_id": "run-fallback",
                "summary": {
                    "status": "paused",
                    "review_packets": {
                        "ready": True,
                        "emitted_candidate_artifact_count": 1,
                        "audit_verdict": None,
                        "handoff_readiness": None,
                    },
                },
                "state": {
                    "phase": "handoff",
                    "target_id": "abyss-stack",
                    "playbook_id": "AOA-P-0011",
                    "task_class": "docs_only",
                    "trust_state_snapshot": "canary_proven",
                },
                "triage": {
                    "resumable": True,
                    "operator_action_required": True,
                    "blocked_reason": None,
                    "recommended_action": "inspect handoff bundle",
                },
                "review_packet_audit": {"audit_verdict": "partial", "recommended_review_targets": []},
                "review_handoff_bundle": {
                    "audit_verdict": "ready",
                    "handoff_readiness": "blocked",
                    "recommended_review_targets": {},
                },
            }
        )

        self.assertIn("- audit_verdict: `partial`", rendered)
        self.assertIn("- handoff_readiness: `blocked`", rendered)

    def test_status_and_list_runs_include_triage_and_promotion_summary(self) -> None:
        def write_run(
            run_id: str,
            *,
            target_id: str,
            playbook_id: str,
            task_class: str,
            status: str,
        ) -> None:
            run_dir = self.logs_root / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                run_dir / "run.state.json",
                {
                    "run_id": run_id,
                    "target_id": target_id,
                    "repo_root": str(self.repo_root),
                    "playbook_id": playbook_id,
                    "task_class": task_class,
                    "trust_state_snapshot": "experimental",
                    "phase": "completed" if status == "pass" else "await_plan_approval",
                    "status": status,
                    "base_head": "abc123",
                    "updated_at": "2026-03-30T00:00:00Z",
                    "break_glass_used": False,
                },
            )
            write_json(
                run_dir / "approval.status.json",
                {
                    "run_id": run_id,
                    "base_head": "abc123",
                    "current_milestone": "landing" if status == "pass" else "plan_freeze",
                    "status": "approved" if status == "pass" else "pending",
                    "milestones": {
                        "plan_freeze": {"status": "approved", "approved": True},
                        "landing": {"status": "approved", "approved": True},
                    },
                },
            )
            write_json(
                run_dir / "result.summary.json",
                {
                    "artifact_kind": "aoa.governed-run.result-summary",
                    "schema_version": "v1",
                    "run_id": run_id,
                    "updated_at": "2026-03-30T00:00:00Z",
                    "status": status,
                    "phase": "completed" if status == "pass" else "await_plan_approval",
                    "break_glass_used": False,
                    "next_action": "ok" if status == "pass" else "review approval",
                },
            )

        write_run("r1", target_id="abyss-stack", playbook_id="AOA-P-0011", task_class="docs_only", status="pass")
        write_run("r2", target_id="abyss-stack", playbook_id="AOA-P-0011", task_class="docs_only", status="pass")
        write_run("r3", target_id="abyss-stack", playbook_id="AOA-P-0018", task_class="governed_lane", status="pass")
        write_run("r4", target_id="abyss-stack", playbook_id="AOA-P-0018", task_class="governed_lane", status="pass")
        write_run(
            "r5",
            target_id="abyss-stack",
            playbook_id="AOA-P-0018",
            task_class="validation_tightening",
            status="pass",
        )

        index_payload = self.module.list_runs(log_root=self.logs_root, policy_path=self.policy_path)
        self.assertEqual(index_payload["run_count"], 5)
        self.assertTrue(index_payload["promotion_summary"]["repo_scope_expansion_gate"]["met"])
        self.assertEqual(
            index_payload["promotion_summary"]["targets"]["abyss-stack"]["playbooks"]["AOA-P-0011"][
                "observed_trust_state"
            ],
            "canary_proven",
        )

        status_payload = self.module.status_run("r1", log_root=self.logs_root)
        self.assertIn("triage", status_payload)
        self.assertFalse(status_payload["triage"]["operator_action_required"])

    def test_status_and_list_runs_handle_inflight_run_without_summary(self) -> None:
        run_dir = self.logs_root / "running-1"
        run_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            run_dir / "run.state.json",
            {
                "run_id": "running-1",
                "repo_root": str(self.repo_root),
                "playbook_id": "AOA-P-0011",
                "task_class": "docs_only",
                "trust_state_snapshot": "experimental",
                "phase": "prepare_proposal",
                "status": "running",
                "base_head": "abc123",
                "updated_at": "2026-03-30T00:00:00Z",
                "break_glass_used": False,
            },
        )
        write_json(
            run_dir / "approval.status.json",
            {
                "run_id": "running-1",
                "base_head": "abc123",
                "current_milestone": "plan_freeze",
                "status": "pending",
                "milestones": {
                    "plan_freeze": {"status": "pending", "approved": False},
                    "landing": {"status": "pending", "approved": False},
                },
            },
        )

        status_payload = self.module.status_run("running-1", log_root=self.logs_root)
        self.assertEqual(status_payload["summary"]["status"], "running")
        self.assertFalse(status_payload["triage"]["operator_action_required"])
        self.assertIsNone(status_payload["triage"]["blocked_reason"])

        index_payload = self.module.list_runs(log_root=self.logs_root, policy_path=self.policy_path)
        self.assertEqual(index_payload["run_count"], 1)
        self.assertEqual(index_payload["operator_triage"]["blocked_run_count"], 0)

    def test_list_runs_uses_freshest_request_lineage_for_recommended_action(self) -> None:
        def write_blocked_run(run_id: str, *, request_path: str, updated_at: str, next_action: str) -> None:
            run_dir = self.logs_root / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                run_dir / "run.state.json",
                {
                    "run_id": run_id,
                    "request_path": request_path,
                    "repo_root": str(self.repo_root),
                    "playbook_id": "AOA-P-0018",
                    "task_class": "governed_lane",
                    "trust_state_snapshot": "experimental",
                    "phase": "await_plan_approval",
                    "status": "paused",
                    "base_head": "abc123",
                    "updated_at": updated_at,
                    "break_glass_used": False,
                },
            )
            write_json(
                run_dir / "approval.status.json",
                {
                    "run_id": run_id,
                    "base_head": "abc123",
                    "current_milestone": "plan_freeze",
                    "status": "pending",
                    "milestones": {
                        "plan_freeze": {"status": "pending", "approved": False},
                        "landing": {"status": "pending", "approved": False},
                    },
                },
            )
            write_json(
                run_dir / "result.summary.json",
                {
                    "artifact_kind": "aoa.governed-run.result-summary",
                    "schema_version": "v1",
                    "run_id": run_id,
                    "updated_at": updated_at,
                    "status": "paused",
                    "phase": "await_plan_approval",
                    "current_milestone": "plan_freeze",
                    "break_glass_used": False,
                    "next_action": next_action,
                },
            )

        write_blocked_run(
            "slot-4-base",
            request_path="/tmp/slot-4.request.json",
            updated_at="2026-03-31T14:00:00Z",
            next_action="review stale base request",
        )
        write_blocked_run(
            "slot-4-retry1",
            request_path="/tmp/slot-4-retry1.request.json",
            updated_at="2026-03-31T14:05:00Z",
            next_action="review freshest retry request",
        )
        write_blocked_run(
            "slot-3-base",
            request_path="/tmp/slot-3.request.json",
            updated_at="2026-03-31T14:04:00Z",
            next_action="review other lineage request",
        )

        index_payload = self.module.list_runs(log_root=self.logs_root, policy_path=self.policy_path)
        self.assertEqual(index_payload["operator_triage"]["recommended_action"], "review freshest retry request")

    def test_list_runs_collapse_unnumbered_retry_lineage(self) -> None:
        stale_dir = self.logs_root / "slot-1-stale"
        stale_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            stale_dir / "run.state.json",
            {
                "run_id": "slot-1-stale",
                "request_path": "/tmp/slot-1-retry.request.json",
                "repo_root": str(self.repo_root),
                "playbook_id": "AOA-P-0011",
                "task_class": "docs_only",
                "trust_state_snapshot": "experimental",
                "phase": "failed",
                "status": "fail",
                "base_head": "abc123",
                "updated_at": "2026-03-31T14:00:00Z",
                "break_glass_used": False,
            },
        )
        write_json(
            stale_dir / "result.summary.json",
            {
                "artifact_kind": "aoa.governed-run.result-summary",
                "schema_version": "v1",
                "run_id": "slot-1-stale",
                "updated_at": "2026-03-31T14:00:00Z",
                "status": "fail",
                "phase": "failed",
                "failure_class": "proposal_invalid",
                "next_action": "repair stale retry",
            },
        )

        passed_dir = self.logs_root / "slot-1-passed"
        passed_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            passed_dir / "run.state.json",
            {
                "run_id": "slot-1-passed",
                "request_path": "/tmp/slot-1-retry4.request.json",
                "repo_root": str(self.repo_root),
                "playbook_id": "AOA-P-0011",
                "task_class": "docs_only",
                "trust_state_snapshot": "experimental",
                "phase": "completed",
                "status": "pass",
                "base_head": "abc123",
                "updated_at": "2026-03-31T14:05:00Z",
                "break_glass_used": False,
            },
        )
        write_json(
            passed_dir / "result.summary.json",
            {
                "artifact_kind": "aoa.governed-run.result-summary",
                "schema_version": "v1",
                "run_id": "slot-1-passed",
                "updated_at": "2026-03-31T14:05:00Z",
                "status": "pass",
                "phase": "completed",
                "next_action": "landed successfully",
            },
        )

        index_payload = self.module.list_runs(log_root=self.logs_root, policy_path=self.policy_path)
        self.assertEqual(index_payload["operator_triage"]["blocked_run_count"], 0)
        self.assertEqual(index_payload["operator_triage"]["blocked_run_ids"], [])

    def test_promotion_summary_respects_evidence_since_run_id(self) -> None:
        policy = test_policy()
        policy["targets"]["aoa-routing"]["playbooks"]["AOA-P-0011"]["evidence_since_run_id"] = "r-pass-1"

        records = [
            {
                "run_id": "r-fail-old",
                "target_id": "aoa-routing",
                "playbook_id": "AOA-P-0011",
                "task_class": "generated_surface",
                "status": "fail",
                "failure_class": "post_change_validation_failure",
                "break_glass_used": False,
            },
            {
                "run_id": "r-pass-1",
                "target_id": "aoa-routing",
                "playbook_id": "AOA-P-0011",
                "task_class": "generated_surface",
                "status": "pass",
                "failure_class": None,
                "break_glass_used": False,
            },
            {
                "run_id": "r-pass-2",
                "target_id": "aoa-routing",
                "playbook_id": "AOA-P-0011",
                "task_class": "docs_only",
                "status": "pass",
                "failure_class": None,
                "break_glass_used": False,
            },
        ]

        summary = self.module.promotion_summary(records, policy)
        routing_playbook = summary["targets"]["aoa-routing"]["playbooks"]["AOA-P-0011"]
        self.assertEqual(routing_playbook["evidence_since_run_id"], "r-pass-1")
        self.assertEqual(routing_playbook["aggregate"]["pass_count"], 2)
        self.assertEqual(routing_playbook["aggregate"]["post_change_validation_failure_count"], 0)
        self.assertEqual(routing_playbook["observed_trust_state"], "canary_proven")

    def test_resolve_default_repo_root_expands_portable_home_default(self) -> None:
        portable_home = self.root / "portable-home"
        portable_repo_root = portable_home / "src" / "abyss-stack"
        init_minimal_repo(portable_repo_root)

        policy = test_policy()
        policy["targets"]["abyss-stack"]["default_repo_root"] = "~/src/abyss-stack"

        with patch.dict("os.environ", {"HOME": str(portable_home)}, clear=False):
            resolved = self.module.resolve_default_repo_root("abyss-stack", policy=policy)

        self.assertEqual(resolved, portable_repo_root.resolve())
