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
            source_identity=self.module.SOURCE_IDENTITY.make_source_identity(
                self.repo_root,
                consumer="governed-runner",
            ),
        )
        self.assertEqual(payload["playbook_id"], "AOA-P-0011")
        self.assertEqual(payload["target_id"], "abyss-stack")
        self.assertEqual(payload["task_class"], "docs_only")
        self.assertEqual(payload["canary_id"], "docs-truth-wording-alignment")

        materialized = self.module.materialize_canary_requests(
            self.root / "materialized-canaries",
            catalog_path=self.canary_catalog_path,
        )
        self.assertEqual(materialized["request_count"], 1)
        request_file = Path(materialized["requests"][0]["request_file"])
        self.assertTrue(request_file.exists())
        self.assertEqual(materialized["requests"][0]["target_id"], "abyss-stack")

    def test_retired_routing_mutation_target_is_unsupported(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "unsupported governed target_id: aoa-routing",
        ):
            self.module.target_checkout_detector("aoa-routing")

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
        (self.repo_root / "README.md").write_text("root\n", encoding="utf-8")
        generated = self.repo_root / "generated" / "aoa_router.min.json"
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text('{"ok":true}\n', encoding="utf-8")
        fixture_readme = self.repo_root / "tests" / "fixtures" / "nested" / "README.md"
        fixture_generated = (
            self.repo_root / "tests" / "fixtures" / "nested" / "generated" / "router.min.json"
        )
        fixture_generated.parent.mkdir(parents=True, exist_ok=True)
        fixture_readme.write_text("fixture\n", encoding="utf-8")
        fixture_generated.write_text("{\"fixture\": true}\n", encoding="utf-8")

        candidates = self.module.enumerate_allowed_candidates(
            self.repo_root,
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
        self.assertIn(
            "target aoa-routing is not present in governed execution policy",
            " ".join(result["reasons"]),
        )
