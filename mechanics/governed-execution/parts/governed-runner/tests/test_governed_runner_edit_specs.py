import json
import textwrap
from unittest.mock import patch

from governed_runner_test_support import GovernedRunnerTestCase


class GovernedRunnerEditSpecTests(GovernedRunnerTestCase):
    def test_compact_excerpt_prefers_goal_focus_terms(self) -> None:
        text = "alpha\n" + ("padding\n" * 400) + "repo-scope expansion gate remains evidence only\n" + ("tail\n" * 200)
        excerpt = self.module.compact_excerpt(
            text,
            char_limit=240,
            focus_terms=self.module.focus_terms_from_goal(
                "Clarify repo-scope expansion gate wording in mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md",
                target_file="mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md",
            ),
        )
        self.assertIn("repo-scope expansion gate", excerpt)
        self.assertLessEqual(len(excerpt), 260)

    def test_build_edit_spec_prompt_uses_bounded_excerpt(self) -> None:
        prompt = self.module.build_edit_spec_prompt(
            request={"goal": "Clarify repo-scope expansion gate wording in mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md"},
            playbook_id="AOA-P-0011",
            target_file="mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md",
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
                    "Update mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py so list_runs computes "
                    "operator_triage.latest_operator_action from the freshest run in each request lineage."
                )
            },
            playbook_id="AOA-P-0018",
            target_file="mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
            target_text=target_text,
            failure_context=[],
        )
        self.assertIn("def list_runs", prompt)
        self.assertIn("latest_blocked", prompt)
        self.assertNotIn("def make_pass_summary", prompt)
        self.assertLess(len(prompt), 5800)

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
            goal="Update mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py so list_runs computes operator triage from the freshest request lineage.",
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
            goal="Update mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py so list_runs computes operator triage from request lineage.",
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
            "Update mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py so list_runs computes latest_operator_action from request lineage."
        )
        self.assertIn("aoa_governed_execution", hints)
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
                    "Update mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py so list_runs computes "
                    "latest_operator_action from the freshest request lineage."
                )
            },
            playbook_id="AOA-P-0018",
            target_file="mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
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
                    "Update mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py so build_run_record "
                    "includes request_path in the returned record."
                )
            },
            playbook_id="AOA-P-0018",
            target_file="mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
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
                "mechanics/diagnostic-spine/parts/truth-surfaces/docs/TRUTH_SURFACES.md",
                "mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
                "scripts/aoa-governed-run",
                "mechanics/governed-execution/parts/governed-runner/tests/test_governed_runner_lifecycle.py",
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
                    "target_file": "mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
                    "old_text": "    latest_blocked =",
                    "new_text": "    latest_blocked = max(runs)",
                },
                selected_target_file="mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
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
                selected_target_file="mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
                spec={
                    "mode": "exact_replace",
                    "target_file": "mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
                    "old_text": "value = 1",
                    "new_text": "value =",
                },
            )

    def test_validate_edit_spec_candidate_rejects_unused_python_assignment(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unused Python assignment"):
            self.module.validate_edit_spec_candidate(
                "blocked_runs = []\nreturn blocked_runs\n",
                selected_target_file="mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
                spec={
                    "mode": "exact_replace",
                    "target_file": "mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
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
            selected_target_file="mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
            spec={
                "mode": "exact_replace",
                "target_file": "mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
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
                selected_target_file="mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
                spec={
                    "mode": "exact_replace",
                    "target_file": "mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py",
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
            "allowed_files": ["mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py", "scripts/aoa-governed-run"],
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
