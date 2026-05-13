#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


EVAL_NAME = "aoa-memo-contradiction-integrity"
OBJECT_UNDER_EVALUATION = "integrity of contradiction-visible memo consumption on lifecycle-aware object recall paths"
SELECTION_ID = "memo-contradiction-rerun-v1"
UPSTREAM_SELECTION_ID = "phase-alpha-memo-contradiction-rerun-v1"
SELECTION_SOURCE_CANDIDATES = (
    Path("examples/runtime_evidence_selection.memo-contradiction-rerun.example.json"),
    Path("examples/runtime_evidence_selection.phase-alpha-memo-contradiction-rerun.example.json"),
)

UPSTREAM_MEMO_CONTRADICTION_IDS = {
    "closure_claim": "memo.claim.2026-04-03.phase-alpha-closure-with-residual-runtime-history",
    "pending_claim": "memo.claim.2026-04-03.phase-alpha-rerun-pending-handoff",
    "retired_overread_claim": "memo.claim.2026-04-03.phase-alpha-runtime-history-fully-retired",
    "later_track_claim": "memo.claim.2026-04-03.phase-alpha-runtime-history-later-infra-track",
    "supersession_audit": "memo.audit.2026-04-03.phase-alpha-rerun-pending-supersession",
    "retraction_audit": "memo.audit.2026-04-03.phase-alpha-runtime-history-overread-retraction",
}
CLOSURE_CLAIM = UPSTREAM_MEMO_CONTRADICTION_IDS["closure_claim"]
PENDING_CLAIM = UPSTREAM_MEMO_CONTRADICTION_IDS["pending_claim"]
RETIRED_OVERREAD_CLAIM = UPSTREAM_MEMO_CONTRADICTION_IDS["retired_overread_claim"]
LATER_TRACK_CLAIM = UPSTREAM_MEMO_CONTRADICTION_IDS["later_track_claim"]
SUPERSESSION_AUDIT = UPSTREAM_MEMO_CONTRADICTION_IDS["supersession_audit"]
RETRACTION_AUDIT = UPSTREAM_MEMO_CONTRADICTION_IDS["retraction_audit"]

REQUIRED_LOG_PATHS = {
    "next_pass_brief": Path("Logs/memo-contradiction-rerun/restartable-inquiry-loop/next_pass_brief.md"),
    "memory_delta": Path("Logs/memo-contradiction-rerun/restartable-inquiry-loop/memory_delta.json"),
    "contradiction_map": Path("Logs/memo-contradiction-rerun/restartable-inquiry-loop/contradiction_map.json"),
    "failure_map": Path("Logs/memo-contradiction-rerun/validation-remediation-recall-rerun/failure_map.json"),
    "handoff_record": Path("Logs/memo-contradiction-rerun/validation-remediation-recall-rerun/handoff_record.json"),
    "remediation_decision": Path(
        "Logs/memo-contradiction-rerun/validation-remediation-recall-rerun/remediation_decision.json"
    ),
}
LEGACY_LOG_PATHS = {
    "next_pass_brief": Path("Logs/phase-alpha/alpha-05-restartable-inquiry-loop/next_pass_brief.md"),
    "memory_delta": Path("Logs/phase-alpha/alpha-05-restartable-inquiry-loop/memory_delta.json"),
    "contradiction_map": Path("Logs/phase-alpha/alpha-05-restartable-inquiry-loop/contradiction_map.json"),
    "failure_map": Path("Logs/phase-alpha/alpha-06-validation-driven-remediation-recall-rerun/failure_map.json"),
    "handoff_record": Path("Logs/phase-alpha/alpha-06-validation-driven-remediation-recall-rerun/handoff_record.json"),
    "remediation_decision": Path(
        "Logs/phase-alpha/alpha-06-validation-driven-remediation-recall-rerun/remediation_decision.json"
    ),
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"error: missing required JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"error: expected JSON object in {path}")
    return data


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"error: missing required text file: {path}") from exc


def object_catalog_by_id(memo_root: Path) -> dict[str, dict[str, Any]]:
    catalog = read_json(memo_root / "generated" / "memory_object_catalog.min.json")
    objects = catalog.get("memory_objects")
    if not isinstance(objects, list):
        raise SystemExit("error: memo generated/memory_object_catalog.min.json must contain memory_objects")
    by_id: dict[str, dict[str, Any]] = {}
    for item in objects:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            by_id[item["id"]] = item
    return by_id


def object_sections_by_id(memo_root: Path) -> dict[str, dict[str, str]]:
    payload = read_json(memo_root / "generated" / "memory_object_sections.full.json")
    objects = payload.get("memory_objects")
    if not isinstance(objects, list):
        raise SystemExit("error: memo generated/memory_object_sections.full.json must contain memory_objects")
    by_id: dict[str, dict[str, str]] = {}
    for item in objects:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        sections: dict[str, str] = {"__kind": str(item.get("kind") or "")}
        for section in item.get("sections", []):
            if isinstance(section, dict) and isinstance(section.get("heading"), str):
                sections[section["heading"]] = str(section.get("body") or "")
        by_id[item["id"]] = sections
    return by_id


def append_failure(failures: list[str], label: str, message: str) -> None:
    failures.append(f"{label}: {message}")


def require(condition: bool, failures: list[str], label: str, message: str) -> None:
    if not condition:
        append_failure(failures, label, message)


def require_catalog(
    objects: dict[str, dict[str, Any]],
    sections: dict[str, dict[str, str]],
    failures: list[str],
    object_id: str,
    *,
    kind: str,
    review_state: str,
    current_recall_status: str,
) -> None:
    item = objects.get(object_id)
    label = f"catalog[{object_id}]"
    section_item = sections.get(object_id, {})
    require(item is not None or section_item, failures, label, "missing memory object")
    if item is None and section_item:
        identity = section_item.get("Identity and Recall", "")
        trust = section_item.get("Trust and Lifecycle", "")
        require(section_item.get("__kind") == kind, failures, label, f"section kind must be {kind!r}")
        require(
            f"Review state: {review_state}." in trust,
            failures,
            label,
            f"section review_state must be {review_state!r}",
        )
        require(
            f"Current recall status: {current_recall_status} " in identity,
            failures,
            label,
            f"section current_recall_status must be {current_recall_status!r}",
        )
        return
    if item is None:
        return
    require(item.get("kind") == kind, failures, label, f"kind must be {kind!r}")
    require(item.get("review_state") == review_state, failures, label, f"review_state must be {review_state!r}")
    require(
        item.get("current_recall_status") == current_recall_status,
        failures,
        label,
        f"current_recall_status must be {current_recall_status!r}",
    )


def require_section_contains(
    sections: dict[str, dict[str, str]],
    failures: list[str],
    object_id: str,
    heading: str,
    snippets: list[str],
) -> None:
    body = sections.get(object_id, {}).get(heading, "")
    label = f"sections[{object_id}#{heading}]"
    require(bool(body), failures, label, "missing section body")
    for snippet in snippets:
        require(snippet in body, failures, label, f"missing snippet {snippet!r}")


def load_runtime_logs(stack_root: Path) -> dict[str, Any]:
    logs: dict[str, Any] = {}
    for key, rel_path in REQUIRED_LOG_PATHS.items():
        path = stack_root / rel_path
        if not path.exists():
            path = stack_root / LEGACY_LOG_PATHS[key]
        logs[key] = read_text(path) if path.suffix == ".md" else read_json(path)
    return logs


def load_runtime_selection(evals_root: Path) -> dict[str, Any]:
    for rel_path in SELECTION_SOURCE_CANDIDATES:
        path = evals_root / rel_path
        if path.exists():
            return read_json(path)
    expected = ", ".join(str(evals_root / rel_path) for rel_path in SELECTION_SOURCE_CANDIDATES)
    raise SystemExit(f"error: missing runtime evidence selection; expected one of: {expected}")


def validate_runtime_selection(evals_root: Path, stack_root: Path, failures: list[str]) -> None:
    selection = load_runtime_selection(evals_root)
    require(
        selection.get("selection_id") in {SELECTION_ID, UPSTREAM_SELECTION_ID},
        failures,
        "runtime selection",
        "selection_id mismatch",
    )
    require(
        selection.get("candidate_eval_refs") == [f"candidate:{EVAL_NAME}"],
        failures,
        "runtime selection",
        "candidate_eval_refs must point to aoa-memo-contradiction-integrity",
    )

    evidence_refs: list[str] = []
    for field_name in ("source_manifests", "selected_evidence"):
        value = selection.get(field_name, [])
        if field_name == "selected_evidence" and isinstance(value, list):
            evidence_refs.extend(
                str(item.get("artifact_ref"))
                for item in value
                if isinstance(item, dict) and isinstance(item.get("artifact_ref"), str)
            )
        elif isinstance(value, list):
            evidence_refs.extend(str(item) for item in value if isinstance(item, str))

    for ref in evidence_refs:
        require(
            ref.startswith("repo:abyss-stack/Logs/"),
            failures,
            "runtime selection",
            f"runtime artifact ref must stay log-backed: {ref}",
        )
        if ref.startswith("repo:abyss-stack/"):
            local_rel = ref.removeprefix("repo:abyss-stack/")
            require((stack_root / local_rel).exists(), failures, "runtime selection", f"missing local evidence {ref}")


def validate_runtime_logs(logs: dict[str, Any], failures: list[str]) -> None:
    next_pass = str(logs["next_pass_brief"])
    require("inspect -> capsule -> expand" in next_pass, failures, "next_pass_brief.md", "must name recall path")
    require("stop and escalate" in next_pass, failures, "next_pass_brief.md", "must preserve escalation boundary")

    contradiction_map = logs["contradiction_map"]
    notes = " ".join(contradiction_map.get("notes", [])) if isinstance(contradiction_map.get("notes"), list) else ""
    require(
        contradiction_map.get("artifact_kind") in {
            "memo-contradiction-rerun.contradiction-map",
            "phase-alpha.contradiction-map",
        },
        failures,
        "contradiction_map.json",
        "artifact_kind mismatch",
    )
    require(
        "Residual historical-script lineage remains a known risk" in notes,
        failures,
        "contradiction_map.json",
        "must preserve residual runtime history risk",
    )

    failure_map = logs["failure_map"]
    refs = failure_map.get("inspect_capsule_expand_refs", [])
    require(failure_map.get("recall_mode") == "memo-only", failures, "failure_map.json", "recall_mode mismatch")
    require(failure_map.get("escalation_required") is False, failures, "failure_map.json", "unexpected escalation")
    require(
        "repo:aoa-memo/generated/memory_object_sections.full.json" in refs,
        failures,
        "failure_map.json",
        "must include expand surface",
    )

    handoff = logs["handoff_record"]
    acceptance = handoff.get("memo_contradiction_acceptance") or handoff.get("phase_alpha_acceptance", {})
    require(
        isinstance(acceptance, dict) and acceptance.get("memo_only_rerun_present") is True,
        failures,
        "handoff_record.json",
        "must record memo-only rerun presence",
    )
    require(
        "memo writeback -> recall-driven rerun" in str(handoff.get("summary", "")),
        failures,
        "handoff_record.json",
        "must keep writeback to recall rerun visible",
    )

    decision = logs["remediation_decision"]
    require(
        "memo-only recall" in str(decision.get("decision", "")),
        failures,
        "remediation_decision.json",
        "must name memo-only recall closure",
    )


def validate_memo_objects(memo_root: Path, failures: list[str]) -> None:
    catalog = object_catalog_by_id(memo_root)
    sections = object_sections_by_id(memo_root)

    require_catalog(
        catalog,
        sections,
        failures,
        CLOSURE_CLAIM,
        kind="claim",
        review_state="confirmed",
        current_recall_status="preferred",
    )
    require_catalog(
        catalog,
        sections,
        failures,
        PENDING_CLAIM,
        kind="claim",
        review_state="superseded",
        current_recall_status="historical",
    )
    require_catalog(
        catalog,
        sections,
        failures,
        RETIRED_OVERREAD_CLAIM,
        kind="claim",
        review_state="retracted",
        current_recall_status="withdrawn",
    )
    require_catalog(
        catalog,
        sections,
        failures,
        LATER_TRACK_CLAIM,
        kind="claim",
        review_state="confirmed",
        current_recall_status="allowed",
    )
    require_catalog(
        catalog,
        sections,
        failures,
        SUPERSESSION_AUDIT,
        kind="audit_event",
        review_state="confirmed",
        current_recall_status="historical",
    )
    require_catalog(
        catalog,
        sections,
        failures,
        RETRACTION_AUDIT,
        kind="audit_event",
        review_state="confirmed",
        current_recall_status="historical",
    )

    require_section_contains(
        sections,
        failures,
        CLOSURE_CLAIM,
        "Trust and Lifecycle",
        [
            f"Supersedes: {PENDING_CLAIM}",
            f"Contradiction refs: {RETIRED_OVERREAD_CLAIM}, {LATER_TRACK_CLAIM}",
        ],
    )
    require_section_contains(
        sections,
        failures,
        PENDING_CLAIM,
        "Trust and Lifecycle",
        [
            f"Superseded by: {CLOSURE_CLAIM}",
            f"Replacement ref: {CLOSURE_CLAIM}",
        ],
    )
    require_section_contains(
        sections,
        failures,
        RETIRED_OVERREAD_CLAIM,
        "Trust and Lifecycle",
        [
            "Review state: retracted.",
            f"Contradiction refs: {CLOSURE_CLAIM}, {LATER_TRACK_CLAIM}",
        ],
    )
    require_section_contains(
        sections,
        failures,
        LATER_TRACK_CLAIM,
        "Trust and Lifecycle",
        [
            "Review state: confirmed.",
            f"Contradiction refs: {CLOSURE_CLAIM}, {RETIRED_OVERREAD_CLAIM}",
        ],
    )
    require_section_contains(
        sections,
        failures,
        SUPERSESSION_AUDIT,
        "Provenance and Evidence",
        [PENDING_CLAIM, CLOSURE_CLAIM],
    )
    require_section_contains(
        sections,
        failures,
        RETRACTION_AUDIT,
        "Provenance and Evidence",
        [RETIRED_OVERREAD_CLAIM, CLOSURE_CLAIM, LATER_TRACK_CLAIM],
    )


def build_report(failures: list[str]) -> dict[str, Any]:
    supports_claim = not failures
    verdict = "supports bounded claim" if supports_claim else "does not support bounded claim"
    breakdown_value = "strong" if supports_claim else "weak"
    return {
        "eval_name": EVAL_NAME,
        "bundle_status": "draft",
        "object_under_evaluation": OBJECT_UNDER_EVALUATION,
        "verdict": verdict,
        "claim_boundary": (
            "On the selected memo contradiction evidence path, the runtime sidecar consumed the log-backed "
            "contradiction rerun selection and the generated aoa-memo object surfaces. It verified that "
            "preferred, historical, withdrawn, and still-open lifecycle posture, contradiction refs, "
            "replacement refs, and audit walkback all remain inspectable on the bounded object-facing path. "
            "This supports the bundle claim only for this selected runtime sidecar path, not for broad memo readiness."
            if supports_claim
            else "The runtime sidecar could not verify the selected memo contradiction path. "
            "The failure list below is the concrete blocker for lifting the bundle."
        ),
        "limitations": [
            "This report reads the selected memo contradiction runtime evidence and generated memo object surfaces only.",
            "This report proves a bounded runtime sidecar consumer path, not broad memo readiness.",
            "This report does not prove contradiction resolution.",
            "This report does not prove permission or authority safety from memo fields.",
            "This report does not replace approval, return-anchor, or verification evals.",
            *failures,
        ],
        "case_family": "memo-contradiction-rerun-v1 runtime sidecar run over memo-contradiction-guardrail-v1",
        "compatibility_boundary": {
            "local_selection_id": SELECTION_ID,
            "upstream_selection_id": UPSTREAM_SELECTION_ID,
            "upstream_owner_refs": {
                "aoa_evals_selection": str(SELECTION_SOURCE_CANDIDATES[1]),
                "aoa_memo_object_ids": UPSTREAM_MEMO_CONTRADICTION_IDS,
            },
            "legacy_log_fallbacks": {key: str(path) for key, path in LEGACY_LOG_PATHS.items()},
        },
        "breakdown": {
            "lifecycle_visibility": breakdown_value,
            "current_recall_honesty": breakdown_value,
            "contradiction_linkage": breakdown_value,
            "replacement_vs_withdrawal_clarity": breakdown_value,
            "audit_trace_visibility": breakdown_value,
        },
        "strongest_contradiction_signal": (
            "The runtime sidecar verified the generated memo object catalog and sections for "
            f"{CLOSURE_CLAIM}, {PENDING_CLAIM}, {RETIRED_OVERREAD_CLAIM}, {LATER_TRACK_CLAIM}, "
            f"{SUPERSESSION_AUDIT}, and {RETRACTION_AUDIT} while preserving log-backed selected evidence refs."
            if supports_claim
            else "The sidecar reached the selected runtime evidence path but failed one or more lifecycle or audit checks."
        ),
        "strongest_contradiction_risk": (
            "The result is bounded to one selected sidecar run and still must not be read as contradiction resolution or full memo readiness."
            if supports_claim
            else "The bundle must remain export-not-ready until the listed sidecar failures are fixed and rerun."
        ),
        "case_notes": [
            {
                "case_id": "PACR-01",
                "read_path": "runtime_evidence_selection.memo-contradiction-rerun.example.json -> memory_object_catalog.min.json -> memory_object_sections.full.json",
                "contradiction_reading": verdict,
                "lifecycle_note": "The sidecar checks confirmed/preferred closure and confirmed/allowed later-track posture from generated memo object surfaces.",
                "current_recall_note": "The current closure reading and still-open later-track reading remain distinct in current_recall_status.",
                "contradiction_note": "The closure and later-track claim retain contradiction refs to each other and to the withdrawn overread.",
                "audit_or_replacement_note": "This case verifies open tension without treating it as contradiction resolution.",
            },
            {
                "case_id": "PACR-02",
                "read_path": "memory_object_catalog.min.json -> memory_object_sections.full.json -> handoff_record.json",
                "contradiction_reading": verdict,
                "lifecycle_note": "The sidecar checks historical superseded posture for the rerun-pending handoff claim.",
                "current_recall_note": "The pending handoff stays historical and points to the preferred closure claim by replacement ref.",
                "contradiction_note": "The case constrains replacement clarity rather than open contradiction.",
                "audit_or_replacement_note": "The supersession audit keeps the replacement walkback inspectable.",
            },
            {
                "case_id": "PACR-03",
                "read_path": "memory_object_catalog.min.json -> memory_object_sections.full.json -> contradiction_map.json",
                "contradiction_reading": verdict,
                "lifecycle_note": "The sidecar checks withdrawn posture for the overread that residual runtime history had been fully retired.",
                "current_recall_note": "The withdrawn overread cannot pass as preferred or allowed current meaning.",
                "contradiction_note": "The withdrawn overread points back to the current closure claim and still-open later-track claim.",
                "audit_or_replacement_note": "The retraction audit keeps the smoothing-pressure walkback inspectable.",
            },
            {
                "case_id": "PACR-04",
                "read_path": "next_pass_brief.md -> failure_map.json -> remediation_decision.json -> handoff_record.json",
                "contradiction_reading": verdict,
                "lifecycle_note": "The runtime sidecar confirms the memo-only inspect-capsule-expand boundary before trusting the memo object surfaces.",
                "current_recall_note": "Runtime logs anchor the sidecar to the bounded memo contradiction rerun rather than free-text recall.",
                "contradiction_note": "The runtime contradiction map keeps the residual historical-script lineage risk explicit.",
                "audit_or_replacement_note": "The handoff record keeps eval readout, memo writeback, and recall-driven rerun in the same evidence chain.",
            },
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the bounded memo contradiction integrity sidecar proof."
    )
    parser.add_argument("--stack-root", default=os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack"))
    parser.add_argument(
        "--memo-root",
        default=os.environ.get("AOA_MEMO_ROOT") or os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack") + "/Knowledge/federation/aoa-memo",
    )
    parser.add_argument(
        "--evals-root",
        default=os.environ.get("AOA_EVALS_ROOT") or os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack") + "/Knowledge/federation/aoa-evals",
    )
    parser.add_argument("--output-file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    stack_root = Path(args.stack_root).expanduser().resolve()
    memo_root = Path(args.memo_root).expanduser().resolve()
    evals_root = Path(args.evals_root).expanduser().resolve()

    failures: list[str] = []
    validate_runtime_selection(evals_root, stack_root, failures)
    validate_runtime_logs(load_runtime_logs(stack_root), failures)
    validate_memo_objects(memo_root, failures)
    report = build_report(failures)

    rendered = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    if args.output_file:
        output_path = Path(args.output_file).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
