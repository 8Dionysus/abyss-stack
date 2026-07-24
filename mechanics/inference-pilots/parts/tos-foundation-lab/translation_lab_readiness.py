"""Gate ToS translation lanes on real two-pass source acceptance."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from translation_source_review import (
    TranslationSourceReviewError,
    verify_translation_source_review_manifest,
)


PART_ROOT = Path(__file__).resolve().parent
READINESS_SCHEMA_PATH = PART_ROOT / "schemas/translation-lab-readiness.schema.json"
HUMAN_REVIEW_SCHEMA_PATH = (
    PART_ROOT / "schemas/translation-source-human-review.schema.json"
)
TREE_PLAN_SCHEMA_REF = (
    "https://tree-of-sophia.local/ToS/contracts/translation-laboratory-plan.schema.json"
)
TREE_PLAN_SCHEMA_PATH = Path("ToS/contracts/translation-laboratory-plan.schema.json")
TREE_REFERENCE_REGISTER_SCHEMA_REF = (
    "https://tree-of-sophia.local/ToS/contracts/translation-reference-register.schema.json"
)
TREE_REFERENCE_REGISTER_SCHEMA_PATH = Path(
    "ToS/contracts/translation-reference-register.schema.json"
)
REQUIRED_REFERENCE_CATEGORIES = {
    "historical_dictionary",
    "modern_dictionary",
    "etymological_dictionary",
    "historical_corpus",
    "nietzsche_critical_edition",
    "nietzsche_lexical_resource",
    "recognized_ru_translation_candidate",
    "additional_ru_translation_candidate",
    "additional_en_translation_candidate",
}
ACCEPTED_SOURCE_DECISIONS = {"accept"}
NON_ACCEPTED_SOURCE_DECISIONS = {"accept-with-limits", "reject", "uncertain", "defer"}
FORBIDDEN_HUMAN_REF_PREFIXES = ("ai:", "model:", "software:", "agent:model")


class TranslationLabReadinessError(TranslationSourceReviewError):
    """Raised when readiness evidence is structurally invalid or drifts."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TranslationLabReadinessError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TranslationLabReadinessError(f"{path} must contain a JSON object")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TranslationLabReadinessError(f"cannot read {path}: {exc}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise TranslationLabReadinessError(
                f"{path}:{line_number}: blank JSONL lines are not allowed"
            )
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TranslationLabReadinessError(
                f"{path}:{line_number}: invalid JSON: {exc}"
            ) from exc
        if not isinstance(record, dict):
            raise TranslationLabReadinessError(
                f"{path}:{line_number}: review row must be an object"
            )
        records.append(record)
    return records


def _schema_issues(payload: object, schema_path: Path) -> list[str]:
    schema = _load_object(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[str] = []
    for error in sorted(
        validator.iter_errors(payload), key=lambda item: list(item.absolute_path)
    ):
        location = "".join(f"[{part!r}]" for part in error.absolute_path) or "<root>"
        issues.append(f"{location}: {error.message}")
    return issues


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _real_human_ref(value: object) -> bool:
    if not _nonempty_text(value):
        return False
    normalized = str(value).strip().lower()
    return not normalized.startswith(FORBIDDEN_HUMAN_REF_PREFIXES)


def _pass_1_complete(record: dict[str, Any]) -> bool:
    value = record.get("pass_1")
    if not isinstance(value, dict):
        return False
    return all(
        (
            value.get("performed_by_real_human") is True,
            _real_human_ref(value.get("reviewer_ref")),
            _nonempty_text(value.get("reviewed_at_utc")),
            _nonempty_text(value.get("layout_role")),
            isinstance(value.get("begins_on_previous_page"), bool),
            isinstance(value.get("continues_on_next_page"), bool),
            _nonempty_text(value.get("boundary_start_note")),
            _nonempty_text(value.get("boundary_end_note")),
            _nonempty_text(value.get("diplomatic_transcription")),
            _nonempty_text(value.get("decision")),
        )
    )


def _pass_2_complete(record: dict[str, Any]) -> bool:
    value = record.get("pass_2")
    pass_1 = record.get("pass_1")
    if not isinstance(value, dict) or not isinstance(pass_1, dict):
        return False
    return all(
        (
            value.get("performed_by_real_human") is True,
            _real_human_ref(value.get("reviewer_ref")),
            _nonempty_text(value.get("reviewed_at_utc")),
            value.get("reviewed_at_utc") != pass_1.get("reviewed_at_utc"),
            _nonempty_text(value.get("independent_diplomatic_transcription")),
            value.get("punctuation_case_orthography_checked") is True,
            value.get("boundary_checked") is True,
            value.get("lineation_and_page_furniture_checked") is True,
            _nonempty_text(value.get("decision")),
        )
    )


def inspect_translation_lab_readiness(
    tree_repo_root: Path,
    laboratory_plan_path: Path,
    source_review_manifest_path: Path,
    human_review_output_path: Path | None = None,
    reference_register_path: Path | None = None,
) -> dict[str, Any]:
    """Return a proof-carrying readiness receipt; never run a translation lane."""

    tree_repo_root = tree_repo_root.resolve()
    laboratory_plan_path = laboratory_plan_path.resolve()
    source_review_manifest_path = source_review_manifest_path.resolve()
    plan = _load_object(laboratory_plan_path)
    plan_schema_path = tree_repo_root / TREE_PLAN_SCHEMA_PATH
    if plan.get("$schema") != TREE_PLAN_SCHEMA_REF:
        raise TranslationLabReadinessError("translation laboratory plan schema ref drifted")
    plan_issues = _schema_issues(plan, plan_schema_path)
    if plan_issues:
        raise TranslationLabReadinessError(
            "invalid translation laboratory plan: " + "; ".join(plan_issues)
        )

    if reference_register_path is None:
        reference_register_path = (
            laboratory_plan_path.parent / "translation-reference-register.v1.json"
        )
    reference_register_path = reference_register_path.resolve()
    reference_register = _load_object(reference_register_path)
    reference_schema_path = tree_repo_root / TREE_REFERENCE_REGISTER_SCHEMA_PATH
    if reference_register.get("$schema") != TREE_REFERENCE_REGISTER_SCHEMA_REF:
        raise TranslationLabReadinessError("translation reference register schema ref drifted")
    reference_issues = _schema_issues(reference_register, reference_schema_path)
    if reference_issues:
        raise TranslationLabReadinessError(
            "invalid translation reference register: " + "; ".join(reference_issues)
        )

    reference_closure_issues: list[str] = []
    registered_plan_ref = reference_register.get("laboratory_plan_ref")
    if not isinstance(registered_plan_ref, str) or (
        tree_repo_root / registered_plan_ref
    ).resolve() != laboratory_plan_path:
        reference_closure_issues.append(
            "translation reference register does not resolve to the exact laboratory plan"
        )
    if reference_register.get("work_ref") != plan.get("work_ref"):
        reference_closure_issues.append("translation reference register work_ref drifted")
    required_categories = set(reference_register.get("required_categories", []))
    if required_categories != REQUIRED_REFERENCE_CATEGORIES:
        reference_closure_issues.append(
            "translation reference register required-category set drifted"
        )
    reference_entries = reference_register.get("entries", [])
    actual_categories = {
        entry.get("category")
        for entry in reference_entries
        if isinstance(entry, dict)
    }
    if not REQUIRED_REFERENCE_CATEGORIES.issubset(actual_categories):
        reference_closure_issues.append(
            "translation reference register does not cover every required category"
        )
    reference_coverage = reference_register.get("coverage", {})
    if not isinstance(reference_coverage, dict) or reference_coverage != {
        "required_category_count": len(REQUIRED_REFERENCE_CATEGORIES),
        "entry_count": len(reference_entries),
        "all_required_categories_present": True,
        "content_admitted_entries": 0,
        "human_bibliographic_reviews": 0,
        "human_rights_reviews": 0,
        "permission_requests_sent": 0,
    }:
        reference_closure_issues.append(
            "translation reference register coverage summary is not the researched zero-admission state"
        )
    comparator = plan["recognized_comparator"]
    comparator_entries = [
        entry
        for entry in reference_entries
        if isinstance(entry, dict)
        and entry.get("category") == "recognized_ru_translation_candidate"
        and {
            comparator.get("expression_ref"),
            comparator.get("item_ref"),
        }.issubset(set(entry.get("tos_refs", {}).get("record_refs", [])))
    ]
    if len(comparator_entries) != 1:
        reference_closure_issues.append(
            "sealed recognized comparator does not resolve to exactly one reference entry"
        )
    if any(
        not isinstance(entry, dict)
        or entry.get("access", {}).get("content_ingested_for_translation_lab")
        is not False
        or entry.get("admission", {}).get("accepted_as_truth") is not False
        for entry in reference_entries
    ):
        reference_closure_issues.append(
            "translation reference register contains admitted or truth-promoted content"
        )
    if reference_closure_issues:
        raise TranslationLabReadinessError(
            "translation reference closure failed: "
            + "; ".join(reference_closure_issues)
        )

    manifest = verify_translation_source_review_manifest(source_review_manifest_path)
    plan_gate = plan["source_review_gate"]
    manifest_sha256 = _sha256_file(source_review_manifest_path)
    closure_issues: list[str] = []
    if manifest_sha256 != plan_gate["interface_manifest_sha256"]:
        closure_issues.append("source review interface manifest digest drifted")
    if manifest.get("page_set_sha256") != plan_gate["interface_page_set_sha256"]:
        closure_issues.append("source review interface page-set digest drifted")
    if manifest.get("review_plan_sha256") != plan_gate["review_plan_sha256"]:
        closure_issues.append("source review plan digest drifted between plan and interface")
    manifest_units = manifest.get("units")
    if not isinstance(manifest_units, list) or len(manifest_units) != plan_gate[
        "review_unit_count"
    ]:
        closure_issues.append("source review interface does not contain the planned 30 units")
        manifest_units = []
    plan_comparator = plan["recognized_comparator"]
    manifest_comparator = manifest.get("recognized_comparator", {})
    for key in ("expression_ref", "item_ref", "visibility"):
        if manifest_comparator.get(key) != plan_comparator.get(key):
            closure_issues.append(f"recognized comparator {key} drifted")
    if any(
        manifest_comparator.get(key) is not False
        for key in ("content_consulted", "content_emitted")
    ):
        closure_issues.append("recognized comparator is not mechanically sealed")
    if closure_issues:
        raise TranslationLabReadinessError(
            "translation readiness closure failed: " + "; ".join(closure_issues)
        )

    review_output_ref: str | None = None
    review_output_sha256: str | None = None
    records: list[dict[str, Any]] = []
    if human_review_output_path is not None:
        human_review_output_path = human_review_output_path.resolve()
        records = _load_jsonl(human_review_output_path)
        review_output_ref = human_review_output_path.as_posix()
        review_output_sha256 = _sha256_file(human_review_output_path)
        if len(records) != len(manifest_units):
            raise TranslationLabReadinessError(
                f"human review output has {len(records)} rows; expected {len(manifest_units)}"
            )
        for index, (record, unit) in enumerate(
            zip(records, manifest_units, strict=True), start=1
        ):
            issues = _schema_issues(record, HUMAN_REVIEW_SCHEMA_PATH)
            if issues:
                raise TranslationLabReadinessError(
                    f"human review row {index} is invalid: " + "; ".join(issues)
                )
            expected = {
                "packet_id": manifest["packet_id"],
                "review_unit_id": unit["review_unit_id"],
                "context_anchor_ref": unit["context_anchor_ref"],
                "source_pages": {
                    "previous": unit["previous_page_ref"],
                    "current": unit["current_page_ref"],
                    "next": unit["next_page_ref"],
                },
            }
            for key, value in expected.items():
                if record.get(key) != value:
                    raise TranslationLabReadinessError(
                        f"human review row {index} {key} drifted from the blind interface"
                    )

    pass_1_complete = sum(_pass_1_complete(record) for record in records)
    pass_2_complete = sum(_pass_2_complete(record) for record in records)
    accepted_source_units = sum(
        _pass_1_complete(record)
        and _pass_2_complete(record)
        and record.get("source_acceptance") in ACCEPTED_SOURCE_DECISIONS
        for record in records
    )
    non_accepted_source_units = sum(
        record.get("source_acceptance") in NON_ACCEPTED_SOURCE_DECISIONS
        for record in records
    )
    required_count = int(plan_gate["review_unit_count"])
    blocked_reasons: list[str] = []
    if human_review_output_path is None:
        blocked_reasons.append("human_review_output_missing")
    if pass_1_complete != required_count:
        blocked_reasons.append(
            f"real_human_pass_1_incomplete:{required_count - pass_1_complete}"
        )
    if pass_2_complete != required_count:
        blocked_reasons.append(
            f"independent_real_human_pass_2_incomplete:{required_count - pass_2_complete}"
        )
    if accepted_source_units != required_count:
        blocked_reasons.append(
            f"source_acceptance_incomplete:{required_count - accepted_source_units}"
        )

    source_ready = not blocked_reasons
    source_reason = (
        []
        if source_ready
        else ["all 30 German units need real two-pass source acceptance"]
    )
    human_draft_reason = [
        "an independent real-human-only pre-draft analysis packet must be frozen before the human-only draft"
    ]
    ai_draft_reason = [
        "an independent AI-only pre-draft analysis packet with model and runtime receipts must be frozen before the AI-only draft"
    ]
    ai_alternative_draft_reason = [
        "independent AI-alternative pre-draft analysis packets with model and runtime receipts must be frozen before machine-alternative drafts"
    ]
    lanes = {
        "human_pre_draft_analysis": {
            "state": "ready" if source_ready else "blocked",
            "reasons": [] if source_ready else source_reason,
        },
        "ai_pre_draft_analysis": {
            "state": "ready" if source_ready else "blocked",
            "reasons": [] if source_ready else source_reason,
        },
        "ai_alternative_pre_draft_analysis": {
            "state": "ready" if source_ready else "blocked",
            "reasons": [] if source_ready else source_reason,
        },
        "human_only": {
            "state": "blocked",
            "reasons": human_draft_reason if source_ready else source_reason,
        },
        "ai_only": {
            "state": "blocked",
            "reasons": ai_draft_reason if source_ready else source_reason,
        },
        "ai_alternatives": {
            "state": "blocked",
            "reasons": ai_alternative_draft_reason if source_ready else source_reason,
        },
        "ai_human": {
            "state": "blocked",
            "reasons": (
                ["independent human-only and AI-only drafts must be frozen first"]
                if source_ready
                else source_reason
            ),
        },
        "recognized_comparator": {
            "state": "sealed",
            "reasons": [
                "human-only, AI-only, and AI+human drafts are not all independently frozen"
            ],
        },
    }
    allowed_next_actions = (
        [
            "freeze-independent-real-human-only-pre-draft-analysis-without-ai",
            "freeze-independent-ai-only-pre-draft-analysis-with-model-and-runtime-receipts",
            "freeze-independent-ai-alternative-pre-draft-analysis-with-model-and-runtime-receipts",
            "keep-each-pre-draft-analysis-lane-blind-to-the-other-lanes-and-comparator",
        ]
        if source_ready
        else [
            "complete-real-human-source-review-pass-1",
            "complete-independent-real-human-source-review-pass-2",
            "record-source-visible-accept-or-reject-decisions",
        ]
    )
    receipt: dict[str, Any] = {
        "schema_version": "tos_translation_lab_readiness_v1",
        "generated_at_utc": _utc_now(),
        "experiment_id": plan["experiment_id"],
        "plan": {
            "ref": laboratory_plan_path.as_posix(),
            "sha256": _sha256_file(laboratory_plan_path),
        },
        "reference_register": {
            "ref": reference_register_path.as_posix(),
            "sha256": _sha256_file(reference_register_path),
            "entry_count": len(reference_entries),
            "required_category_count": len(REQUIRED_REFERENCE_CATEGORIES),
            "content_admitted_entries": reference_coverage[
                "content_admitted_entries"
            ],
            "human_bibliographic_reviews": reference_coverage[
                "human_bibliographic_reviews"
            ],
            "human_rights_reviews": reference_coverage["human_rights_reviews"],
            "permission_requests_sent": reference_coverage["permission_requests_sent"],
            "research_only": True,
        },
        "source_interface": {
            "manifest_ref": source_review_manifest_path.as_posix(),
            "manifest_sha256": manifest_sha256,
            "page_set_sha256": manifest["page_set_sha256"],
            "review_unit_count": len(manifest_units),
            "fixity_verified": True,
            "comparator_sealed": True,
        },
        "human_review": {
            "review_output_ref": review_output_ref,
            "review_output_sha256": review_output_sha256,
            "record_count": len(records),
            "pass_1_complete": pass_1_complete,
            "pass_2_complete": pass_2_complete,
            "accepted_source_units": accepted_source_units,
            "non_accepted_source_units": non_accepted_source_units,
            "all_units_double_checked": pass_2_complete == required_count,
        },
        "gates": {
            "source_interface_fixity": "pass",
            "reference_register_research": "pass",
            "real_human_pass_1": "pass" if pass_1_complete == required_count else "blocked",
            "independent_real_human_pass_2": (
                "pass" if pass_2_complete == required_count else "blocked"
            ),
            "source_acceptance": (
                "pass" if accepted_source_units == required_count else "blocked"
            ),
            "comparator_blindness": "pass",
            "pre_draft_analysis": "blocked",
            "blocked_reasons": blocked_reasons,
        },
        "translation_lanes": lanes,
        "allowed_next_actions": allowed_next_actions,
        "prohibited_actions": [
            "simulate-human-only-source-or-translation-work",
            "run-ai-translation-before-source-acceptance",
            "run-any-translation-draft-before-source-grounded-pre-draft-analysis",
            "reuse-ai-produced-pre-draft-analysis-in-the-human-only-lane",
            "show-one-pre-draft-analysis-lane-to-another-before-independent-freeze",
            "reveal-or-consult-recognized-comparator-before-independent-freeze",
            "promote-model-etymology-without-external-sources",
            "start-semantic-sign-or-transfer-work-from-unaccepted-german",
        ],
        "decision": (
            "ready-for-independent-source-grounded-pre-draft-analysis"
            if source_ready
            else "blocked"
        ),
        "authority_boundary": (
            "this receipt verifies reference-register research closure, interface fixity, declared human review shape, and independent blind pre-draft lane ordering only; "
            "it cannot prove reviewer identity, transcription correctness, bibliographic or rights judgment, translation quality, etymology, or semantics"
        ),
    }
    receipt_issues = _schema_issues(receipt, READINESS_SCHEMA_PATH)
    if receipt_issues:
        raise TranslationLabReadinessError(
            "generated readiness receipt is invalid: " + "; ".join(receipt_issues)
        )
    return receipt
