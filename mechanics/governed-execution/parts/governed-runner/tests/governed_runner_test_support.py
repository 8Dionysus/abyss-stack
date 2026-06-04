import importlib.util
import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[5]
MODULE_PATH = (
    REPO_ROOT
    / "mechanics"
    / "governed-execution"
    / "parts"
    / "governed-runner"
    / "aoa_governed_execution.py"
)
BRIDGE_CONFIG = json.loads(
    (REPO_ROOT / "config-templates" / "Configs" / "federation" / "upstream-compatibility-bridge.json").read_text(
        encoding="utf-8"
    )
)


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


def make_policy(enabled_break_glass: bool = False) -> dict:
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


def make_canary_catalog() -> dict:
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


class GovernedRunnerTestCase(unittest.TestCase):
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
        policy = make_policy()
        policy["targets"]["abyss-stack"]["default_repo_root"] = str(self.repo_root)
        policy["targets"]["aoa-routing"]["default_repo_root"] = str(self.routing_repo_root)
        write_json(self.policy_path, policy)
        self.canary_catalog_path = self.root / "canaries.json"
        write_json(self.canary_catalog_path, make_canary_catalog())
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
            BRIDGE_CONFIG["runtime_evidence_templates"]["memo-recall-rerun"]["upstream_source_ref"],
            BRIDGE_CONFIG["runtime_evidence_templates"]["memo-contradiction-gap"]["upstream_source_ref"],
            BRIDGE_CONFIG["runtime_evidence_templates"]["memo-contradiction-rerun"]["upstream_source_ref"],
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
                        "runtime_refs": ["docs/memory/MEMORY_MODEL.md#approval-record"],
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
            / "mechanics"
            / "writeback"
            / "parts"
            / "runtime-and-temperature"
            / "generated"
            / "runtime_writeback_targets.min.json",
            memo_targets,
        )
        write_json(
            stack_root
            / "Knowledge"
            / "federation"
            / "aoa-memo"
            / "mechanics"
            / "writeback"
            / "parts"
            / "runtime-and-temperature"
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
                            "runtime_refs": ["docs/memory/MEMORY_MODEL.md#approval-record"],
                            "owner_review_refs": [
                                "docs/memory/MEMORY_MODEL.md#approval-record",
                                "mechanics/writeback/docs/RUNTIME_WRITEBACK_SEAM.md",
                                "mechanics/writeback/docs/QUEST_EVIDENCE_WRITEBACK.md",
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
            / "mechanics"
            / "checkpoint"
            / "parts"
            / "checkpoint-to-memory-mapping"
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
                            "runtime_refs": ["docs/memory/MEMORY_MODEL.md#approval-record"],
                            "notes": "Fixture approval writeback.",
                        }
                    ]
                    if include_memo_target
                    else []
                ),
            },
        )
        return stack_root


