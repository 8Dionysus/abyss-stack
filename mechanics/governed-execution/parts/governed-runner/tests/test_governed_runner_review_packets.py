import json
from unittest.mock import patch

from governed_runner_test_support import GovernedRunnerTestCase, make_policy, write_json


class GovernedRunnerReviewPacketTests(GovernedRunnerTestCase):
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
        self.assertNotIn("/srv/AbyssOS/abyss-stack", hook_ref)

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
                "aoa-memo/mechanics/writeback/parts/runtime-and-temperature/generated/runtime_writeback_targets.min.json",
            ],
        )
        recommended_targets = {(item["owner_repo"], item["ref"]) for item in audit["recommended_review_targets"]}
        self.assertIn(("aoa-playbooks", "playbooks/bounded-change-safe/PLAYBOOK.md"), recommended_targets)
        self.assertIn(
            ("aoa-evals", "examples/artifact_to_verdict_hook.self-agent-checkpoint-rollout.example.json"),
            recommended_targets,
        )
        self.assertIn(("aoa-memo", "docs/memory/MEMORY_MODEL.md#approval-record"), recommended_targets)

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
            / "mechanics"
            / "writeback"
            / "parts"
            / "runtime-and-temperature"
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
        self.assertIn("mechanics/writeback/docs/RUNTIME_WRITEBACK_SEAM.md", rendered)

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
        policy = make_policy()
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
