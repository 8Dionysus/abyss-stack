import json
import subprocess
from pathlib import Path

from governed_runner_test_support import (
    GovernedRunnerTestCase,
    governed_request,
    make_policy,
    write_json,
)


class GovernedRunnerPolicyScopeTests(GovernedRunnerTestCase):
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
        write_json(self.policy_path, make_policy(enabled_break_glass=True))
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
                "anchor_after": "The optional downstream seam can also be exercised directly:",
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
