from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "aoa-export-runtime-evidence-selection"


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

    def test_phase_alpha_memo_recall_source_example_ref_uses_matching_contract_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "abyss-stack"
            payload = {
                "surface_type": "runtime_evidence_selection",
                "selection_id": "governed-run--phase-alpha-memo-recall-rerun-v1",
                "source_example_ref": "examples/runtime_evidence_selection.phase-alpha-memo-recall-rerun.example.json",
            }

            artifact = self.run_export(stack_root, payload)

        refs = artifact["aoa_evals_contract_refs"]
        self.assertTrue(
            any("runtime_evidence_selection.phase-alpha-memo-recall-rerun.example.json" in ref for ref in refs)
        )
        self.assertFalse(any("runtime_evidence_selection.workhorse-local.example.json" in ref for ref in refs))

    def test_memo_recall_candidate_eval_ref_uses_phase_alpha_contract_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "abyss-stack"
            payload = {
                "surface_type": "runtime_evidence_selection",
                "selection_id": "phase-alpha-memo-recall-rerun-v1",
                "candidate_eval_refs": ["candidate:aoa-memo-recall-integrity"],
            }

            artifact = self.run_export(stack_root, payload)

        refs = artifact["aoa_evals_contract_refs"]
        self.assertTrue(
            any("runtime_evidence_selection.phase-alpha-memo-recall-rerun.example.json" in ref for ref in refs)
        )
        self.assertFalse(any("runtime_evidence_selection.workhorse-local.example.json" in ref for ref in refs))


if __name__ == "__main__":
    unittest.main()
