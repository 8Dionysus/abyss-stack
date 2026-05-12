from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = REPO_ROOT / "scripts" / "aoa-run-memo-contradiction-integrity"

CLOSURE_CLAIM = "memo.claim.2026-04-03.phase-alpha-closure-with-residual-runtime-history"
PENDING_CLAIM = "memo.claim.2026-04-03.phase-alpha-rerun-pending-handoff"
RETIRED_OVERREAD_CLAIM = "memo.claim.2026-04-03.phase-alpha-runtime-history-fully-retired"
LATER_TRACK_CLAIM = "memo.claim.2026-04-03.phase-alpha-runtime-history-later-infra-track"
SUPERSESSION_AUDIT = "memo.audit.2026-04-03.phase-alpha-rerun-pending-supersession"
RETRACTION_AUDIT = "memo.audit.2026-04-03.phase-alpha-runtime-history-overread-retraction"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def section_object(object_id: str, kind: str, status: str, review_state: str, trust_body: str, provenance_body: str = "") -> dict:
    return {
        "id": object_id,
        "kind": kind,
        "title": object_id,
        "source_path": f"examples/{object_id}.json",
        "sections": [
            {
                "heading": "Identity and Recall",
                "body": f"Current recall status: {status} because fixture.",
            },
            {
                "heading": "Provenance and Evidence",
                "body": provenance_body,
            },
            {
                "heading": "Trust and Lifecycle",
                "body": f"Review state: {review_state}. {trust_body}",
            },
        ],
    }


def make_memo_root(root: Path) -> None:
    write_json(
        root / "generated" / "memory_object_catalog.min.json",
        {
            "memory_objects": [
                {
                    "id": CLOSURE_CLAIM,
                    "kind": "claim",
                    "review_state": "confirmed",
                    "current_recall_status": "preferred",
                },
                {
                    "id": LATER_TRACK_CLAIM,
                    "kind": "claim",
                    "review_state": "confirmed",
                    "current_recall_status": "allowed",
                },
            ]
        },
    )
    write_json(
        root / "generated" / "memory_object_sections.full.json",
        {
            "memory_objects": [
                section_object(
                    CLOSURE_CLAIM,
                    "claim",
                    "preferred",
                    "confirmed",
                    f"Supersedes: {PENDING_CLAIM}. Contradiction refs: {RETIRED_OVERREAD_CLAIM}, {LATER_TRACK_CLAIM}.",
                ),
                section_object(
                    PENDING_CLAIM,
                    "claim",
                    "historical",
                    "superseded",
                    f"Superseded by: {CLOSURE_CLAIM}. Replacement ref: {CLOSURE_CLAIM}.",
                ),
                section_object(
                    RETIRED_OVERREAD_CLAIM,
                    "claim",
                    "withdrawn",
                    "retracted",
                    f"Contradiction refs: {CLOSURE_CLAIM}, {LATER_TRACK_CLAIM}.",
                ),
                section_object(
                    LATER_TRACK_CLAIM,
                    "claim",
                    "allowed",
                    "confirmed",
                    f"Contradiction refs: {CLOSURE_CLAIM}, {RETIRED_OVERREAD_CLAIM}.",
                ),
                section_object(
                    SUPERSESSION_AUDIT,
                    "audit_event",
                    "historical",
                    "confirmed",
                    "Retention class: audit-trace.",
                    f"Episode refs: {PENDING_CLAIM}, {CLOSURE_CLAIM}.",
                ),
                section_object(
                    RETRACTION_AUDIT,
                    "audit_event",
                    "historical",
                    "confirmed",
                    "Retention class: audit-trace.",
                    f"Episode refs: {RETIRED_OVERREAD_CLAIM}, {CLOSURE_CLAIM}, {LATER_TRACK_CLAIM}.",
                ),
            ]
        },
    )


def make_evals_root(root: Path) -> None:
    write_json(
        root / "examples" / "runtime_evidence_selection.phase-alpha-memo-contradiction-rerun.example.json",
        {
            "selection_id": "phase-alpha-memo-contradiction-rerun-v1",
            "candidate_eval_refs": ["candidate:aoa-memo-contradiction-integrity"],
            "source_manifests": [
                "repo:abyss-stack/Logs/phase-alpha/alpha-05-restartable-inquiry-loop/contradiction_map.json"
            ],
            "selected_evidence": [
                {
                    "artifact_ref": "repo:abyss-stack/Logs/phase-alpha/alpha-05-restartable-inquiry-loop/next_pass_brief.md"
                },
                {
                    "artifact_ref": "repo:abyss-stack/Logs/phase-alpha/alpha-05-restartable-inquiry-loop/memory_delta.json"
                },
                {
                    "artifact_ref": "repo:abyss-stack/Logs/phase-alpha/alpha-05-restartable-inquiry-loop/contradiction_map.json"
                },
                {
                    "artifact_ref": "repo:abyss-stack/Logs/phase-alpha/alpha-06-validation-driven-remediation-recall-rerun/failure_map.json"
                },
                {
                    "artifact_ref": "repo:abyss-stack/Logs/phase-alpha/alpha-06-validation-driven-remediation-recall-rerun/handoff_record.json"
                },
                {
                    "artifact_ref": "repo:abyss-stack/Logs/phase-alpha/alpha-06-validation-driven-remediation-recall-rerun/remediation_decision.json"
                },
            ],
        },
    )


def make_stack_root(root: Path) -> None:
    write_text(
        root / "Logs" / "phase-alpha" / "alpha-05-restartable-inquiry-loop" / "next_pass_brief.md",
        "use inspect -> capsule -> expand; stop and escalate when memo is insufficient\n",
    )
    write_json(
        root / "Logs" / "phase-alpha" / "alpha-05-restartable-inquiry-loop" / "memory_delta.json",
        {"artifact_kind": "phase-alpha.memory-delta"},
    )
    write_json(
        root / "Logs" / "phase-alpha" / "alpha-05-restartable-inquiry-loop" / "contradiction_map.json",
        {
            "artifact_kind": "phase-alpha.contradiction-map",
            "notes": ["Residual historical-script lineage remains a known risk"],
        },
    )
    write_json(
        root / "Logs" / "phase-alpha" / "alpha-06-validation-driven-remediation-recall-rerun" / "failure_map.json",
        {
            "recall_mode": "memo-only",
            "inspect_capsule_expand_refs": ["repo:aoa-memo/generated/memory_object_sections.full.json"],
            "escalation_required": False,
        },
    )
    write_json(
        root / "Logs" / "phase-alpha" / "alpha-06-validation-driven-remediation-recall-rerun" / "handoff_record.json",
        {
            "phase_alpha_acceptance": {"memo_only_rerun_present": True},
            "summary": "eval readout -> memo writeback -> recall-driven rerun",
        },
    )
    write_json(
        root / "Logs" / "phase-alpha" / "alpha-06-validation-driven-remediation-recall-rerun" / "remediation_decision.json",
        {"decision": "close remediation recurrence as proven under memo-only recall"},
    )


class MemoContradictionIntegrityRunnerTests(unittest.TestCase):
    def test_runner_supports_bounded_claim_from_log_backed_selection_and_generated_memo_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stack_root = root / "abyss-stack"
            memo_root = root / "aoa-memo"
            evals_root = root / "aoa-evals"
            make_stack_root(stack_root)
            make_memo_root(memo_root)
            make_evals_root(evals_root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--stack-root",
                    str(stack_root),
                    "--memo-root",
                    str(memo_root),
                    "--evals-root",
                    str(evals_root),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        report = json.loads(result.stdout)
        self.assertEqual(report["verdict"], "supports bounded claim")
        self.assertEqual(report["breakdown"]["contradiction_linkage"], "strong")
        self.assertEqual(report["breakdown"]["audit_trace_visibility"], "strong")
        self.assertTrue(
            all("does not prove a live runtime contradiction consumer exists" not in item for item in report["limitations"])
        )


if __name__ == "__main__":
    unittest.main()
