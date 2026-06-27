from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = REPO_ROOT / "scripts" / "aoa-export-runtime-evidence-selection"
BRIDGE_CONFIG = json.loads(
    (REPO_ROOT / "config-templates" / "Configs" / "federation" / "upstream-compatibility-bridge.json").read_text(
        encoding="utf-8"
    )
)["runtime_evidence_templates"]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


class RuntimeEvalEvidenceExportTests(unittest.TestCase):
    def run_export(self, stack_root: Path, payload: dict) -> dict:
        input_path = stack_root / "tmp" / "candidate.json"
        write_json(input_path, payload)

        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--input-file", str(input_path)],
            check=True,
            capture_output=True,
            env={"AOA_STACK_ROOT": str(stack_root)},
            text=True,
        )
        return json.loads(result.stdout)

    def assert_valid_runtime_evidence_candidate_shape(self, artifact: dict) -> None:
        payload = artifact["candidate_payload"]
        self.assertEqual(payload["surface_type"], "runtime_evidence_selection")
        self.assertEqual(payload["source_repo"], "abyss-stack")
        self.assertIn("source_schema_ref", payload)
        self.assertTrue(payload["source_manifests"])
        self.assertTrue(payload["bounded_claim"])
        self.assertIn(payload["promotion_target"], {"local-only", "evidence-sidecar", "bundle-candidate"})
        self.assertIn(payload["comparison_mode"], {"none", "fixed-baseline", "peer-compare", "longitudinal-window"})
        self.assertTrue(payload["environment_invariants"])
        self.assertTrue(payload["do_not_overread"])
        self.assertIs(payload["review_posture"]["human_review_required"], True)
        self.assertTrue(payload["selected_evidence"])
        self.assertTrue(all(entry.get("summary_only") is True for entry in payload["selected_evidence"]))
        self.assertNotIn("source_example_ref", payload)
        self.assertNotIn("template_name", payload)
        self.assertNotIn("review_required", payload)

    def test_memo_recall_source_example_ref_uses_matching_contract_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "abyss-stack"
            payload = {
                "surface_type": "runtime_evidence_selection",
                "selection_id": "governed-run--memo-recall-rerun-v1",
                "source_example_ref": "examples/runtime_evidence_selection.memo-recall-rerun.example.json",
            }

            artifact = self.run_export(stack_root, payload)

        self.assert_valid_runtime_evidence_candidate_shape(artifact)
        refs = artifact["aoa_evals_contract_refs"]
        self.assertTrue(
            any(BRIDGE_CONFIG["memo-recall-rerun"]["upstream_source_ref"] in ref for ref in refs)
        )
        self.assertFalse(any("runtime_evidence_selection.workhorse-local.example.json" in ref for ref in refs))

    def test_memo_recall_candidate_eval_ref_uses_upstream_contract_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "abyss-stack"
            payload = {
                "surface_type": "runtime_evidence_selection",
                "selection_id": "memo-recall-rerun-v1",
                "candidate_eval_refs": ["candidate:aoa-memo-recall-integrity"],
            }

            artifact = self.run_export(stack_root, payload)

        self.assert_valid_runtime_evidence_candidate_shape(artifact)
        refs = artifact["aoa_evals_contract_refs"]
        self.assertTrue(
            any(BRIDGE_CONFIG["memo-recall-rerun"]["upstream_source_ref"] in ref for ref in refs)
        )
        self.assertFalse(any("runtime_evidence_selection.workhorse-local.example.json" in ref for ref in refs))

    def test_memo_contradiction_candidate_eval_ref_uses_gap_contract_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "abyss-stack"
            payload = {
                "surface_type": "runtime_evidence_selection",
                "selection_id": "memo-contradiction-gap-v1",
                "candidate_eval_refs": ["candidate:aoa-memo-contradiction-integrity"],
            }

            artifact = self.run_export(stack_root, payload)

        self.assert_valid_runtime_evidence_candidate_shape(artifact)
        refs = artifact["aoa_evals_contract_refs"]
        self.assertTrue(
            any(BRIDGE_CONFIG["memo-contradiction-gap"]["upstream_source_ref"] in ref for ref in refs)
        )
        self.assertFalse(any("runtime_evidence_selection.workhorse-local.example.json" in ref for ref in refs))

    def test_memo_contradiction_rerun_candidate_eval_ref_uses_rerun_contract_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "abyss-stack"
            payload = {
                "surface_type": "runtime_evidence_selection",
                "selection_id": "memo-contradiction-rerun-v1",
                "candidate_eval_refs": ["candidate:aoa-memo-contradiction-integrity"],
            }

            artifact = self.run_export(stack_root, payload)

        self.assert_valid_runtime_evidence_candidate_shape(artifact)
        refs = artifact["aoa_evals_contract_refs"]
        self.assertTrue(
            any(BRIDGE_CONFIG["memo-contradiction-rerun"]["upstream_source_ref"] in ref for ref in refs)
        )
        self.assertFalse(any("runtime_evidence_selection.workhorse-local.example.json" in ref for ref in refs))

    def test_shortcut_payload_exports_canonical_runtime_evidence_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "abyss-stack"
            payload = {
                "surface_type": "runtime_evidence_selection",
                "selection_id": "run-1--workhorse-q4-vs-q6-latency-tradeoff",
                "template_name": "workhorse-q4-vs-q6-latency-tradeoff",
                "selected_evidence": [
                    {"evidence_role": "summary", "artifact_ref": "governed-run:run-1:summary"},
                    {"evidence_role": "comparison-note", "artifact_ref": "governed-run:run-1:comparison-note"},
                ],
                "review_required": True,
                "changed_files": ["scripts/build_router.py"],
                "advisory_trace_ref": "local:/tmp/advisory_trace.json",
            }

            artifact = self.run_export(stack_root, payload)

        self.assert_valid_runtime_evidence_candidate_shape(artifact)
        candidate = artifact["candidate_payload"]
        self.assertEqual(candidate["comparison_mode"], "fixed-baseline")
        self.assertIn("local:/tmp/advisory_trace.json", candidate["source_manifests"])


if __name__ == "__main__":
    unittest.main()
