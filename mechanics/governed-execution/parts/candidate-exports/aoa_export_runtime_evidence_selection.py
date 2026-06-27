#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def slugify(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = lowered.strip("-")
    return lowered or "candidate"


def default_title(selection_id: str) -> str:
    return f"runtime evidence selection {selection_id}"


BRIDGE_CONFIG_RELATIVE_PATH = Path("config-templates/Configs/federation/upstream-compatibility-bridge.json")
RUNTIME_BRIDGE_CONFIG_RELATIVE_PATH = Path("Configs/federation/upstream-compatibility-bridge.json")
RUNTIME_EVIDENCE_SOURCE_SCHEMA_REF = (
    "repo:abyss-stack/mechanics/governed-execution/parts/candidate-exports/"
    "schemas/runtime-eval-evidence-selection-candidate.schema.json"
)
RUNTIME_EVIDENCE_ROLES = {
    "summary",
    "case-breakdown",
    "environment-note",
    "comparison-note",
    "integrity-sidecar",
}
COMPARISON_MODES = {"none", "fixed-baseline", "peer-compare", "longitudinal-window"}
PROMOTION_TARGETS = {"local-only", "evidence-sidecar", "bundle-candidate"}


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "scripts").is_dir()
            and (candidate / "mechanics").is_dir()
        ):
            return candidate
    raise RuntimeError("could not locate abyss-stack repository root")


def read_bridge(stack_root: Path) -> dict[str, Any]:
    runtime_path = stack_root / RUNTIME_BRIDGE_CONFIG_RELATIVE_PATH
    source_path = find_repo_root(Path(__file__).resolve().parent) / BRIDGE_CONFIG_RELATIVE_PATH
    for path in (runtime_path, source_path):
        if path.exists():
            return read_json(path)
    raise SystemExit(f"error: missing upstream compatibility bridge config: expected {runtime_path} or {source_path}")


def memo_runtime_evidence_compatibility(stack_root: Path) -> dict[str, dict[str, Any]]:
    bridge = read_bridge(stack_root)
    compatibility = bridge.get("runtime_evidence_templates")
    if not isinstance(compatibility, dict):
        raise SystemExit("error: upstream compatibility bridge must contain runtime_evidence_templates")
    return {str(name): dict(value) for name, value in compatibility.items() if isinstance(value, dict)}


def compatibility_source_refs(compatibility: dict[str, dict[str, Any]], name: str) -> set[str]:
    entry = compatibility[name]
    return {
        str(entry["local_source_ref"]),
        str(entry["upstream_source_ref"]),
    }


def compatibility_selection_ids(compatibility: dict[str, dict[str, Any]], name: str) -> set[str]:
    entry = compatibility[name]
    return {str(entry["canonical_selection_id"]), str(entry["upstream_selection_id"])}


def selection_id_matches(selection_id: str, candidates: set[str]) -> bool:
    selection_slug = slugify(selection_id)
    return any(slugify(candidate) in selection_slug for candidate in candidates)


def infer_comparison_mode(selection_id: str, template_name: str) -> str:
    joined = f"{selection_id} {template_name}".lower()
    if "tradeoff" in joined or "latency" in joined or "compare" in joined:
        return "fixed-baseline"
    if "window" in joined or "rerun" in joined:
        return "longitudinal-window"
    return "none"


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def selected_evidence_entries(candidate_payload: dict[str, Any], source_input_ref: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    raw_entries = candidate_payload.get("selected_evidence")
    if isinstance(raw_entries, list):
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                continue
            artifact_ref = raw_entry.get("artifact_ref")
            if not isinstance(artifact_ref, str) or not artifact_ref:
                continue
            role = str(raw_entry.get("evidence_role") or "summary")
            if role not in RUNTIME_EVIDENCE_ROLES:
                role = "summary"
            entries.append(
                {
                    "artifact_ref": artifact_ref,
                    "evidence_role": role,
                    "summary_only": bool(raw_entry.get("summary_only", True)),
                }
            )
    if not entries:
        entries.append(
            {
                "artifact_ref": source_input_ref,
                "evidence_role": "summary",
                "summary_only": True,
            }
        )
    return entries


def canonical_runtime_evidence_selection(
    candidate_payload: dict[str, Any],
    *,
    source_input_ref: str,
) -> dict[str, Any]:
    selection_id = str(candidate_payload.get("selection_id") or "runtime-evidence-selection")
    template_name = str(candidate_payload.get("template_name") or "")
    comparison_mode = str(candidate_payload.get("comparison_mode") or "")
    if comparison_mode not in COMPARISON_MODES:
        comparison_mode = infer_comparison_mode(selection_id, template_name)
    promotion_target = str(candidate_payload.get("promotion_target") or "")
    if promotion_target not in PROMOTION_TARGETS:
        promotion_target = "evidence-sidecar"

    manifests = string_list(candidate_payload.get("source_manifests"))
    advisory_trace_ref = candidate_payload.get("advisory_trace_ref")
    if isinstance(advisory_trace_ref, str) and advisory_trace_ref:
        manifests.append(advisory_trace_ref)
    manifests.append(source_input_ref)

    target_eval = candidate_payload.get("target_eval")
    candidate_eval_refs = string_list(candidate_payload.get("candidate_eval_refs"))
    if not isinstance(target_eval, str):
        for ref in candidate_eval_refs:
            if ref.startswith("candidate:aoa-"):
                target_eval = ref[len("candidate:") :]
                break

    review_posture = candidate_payload.get("review_posture")
    review_posture = dict(review_posture) if isinstance(review_posture, dict) else {}
    normalized: dict[str, Any] = {
        "surface_type": "runtime_evidence_selection",
        "selection_id": selection_id,
        "source_repo": str(candidate_payload.get("source_repo") or "abyss-stack"),
        "source_schema_ref": str(candidate_payload.get("source_schema_ref") or RUNTIME_EVIDENCE_SOURCE_SCHEMA_REF),
        "source_manifests": unique_strings(manifests),
        "bounded_claim": str(
            candidate_payload.get("bounded_claim")
            or f"Private governed-run runtime evidence selection for {selection_id}. "
            "This is candidate routing evidence only and requires bundle-local review before any proof claim."
        ),
        "promotion_target": promotion_target,
        "comparison_mode": comparison_mode,
        "selected_evidence": selected_evidence_entries(candidate_payload, source_input_ref),
        "environment_invariants": string_list(candidate_payload.get("environment_invariants"))
        or ["same governed-run review-packet generation context"],
        "do_not_overread": string_list(candidate_payload.get("do_not_overread"))
        or [
            "does not compute or imply an aoa-evals verdict",
            "does not accept runtime evidence without bundle-local review",
            "does not transfer proof authority into abyss-stack",
        ],
        "review_posture": {
            "portable_enough": bool(review_posture.get("portable_enough", False)),
            "comparison_hygiene_named": bool(review_posture.get("comparison_hygiene_named", comparison_mode != "none")),
            "human_review_required": True,
        },
    }
    if candidate_eval_refs:
        normalized["candidate_eval_refs"] = unique_strings(candidate_eval_refs)
    if isinstance(target_eval, str) and target_eval:
        normalized["target_eval"] = target_eval
    memory_context_boundary = candidate_payload.get("memory_context_boundary")
    if isinstance(memory_context_boundary, dict):
        normalized["memory_context_boundary"] = memory_context_boundary
    for optional_key in ("environment_deltas", "excluded_artifacts"):
        optional_values = string_list(candidate_payload.get(optional_key))
        if optional_values:
            normalized[optional_key] = unique_strings(optional_values)
    return normalized


def read_json(path: Path) -> dict:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"error: file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: invalid json in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SystemExit(f"error: expected a JSON object in {path}")
    return loaded


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wrap a bounded aoa-evals runtime_evidence_selection candidate into a private abyss-stack export artifact."
    )
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--record-id")
    parser.add_argument("--title")
    parser.add_argument("--summary")
    parser.add_argument("--write", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    stack_root = Path(os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack"))
    memo_compatibility = memo_runtime_evidence_compatibility(stack_root)
    memo_recall_source_refs = compatibility_source_refs(memo_compatibility, "memo-recall-rerun")
    memo_contradiction_gap_source_refs = compatibility_source_refs(memo_compatibility, "memo-contradiction-gap")
    memo_contradiction_rerun_source_refs = compatibility_source_refs(memo_compatibility, "memo-contradiction-rerun")
    memo_recall_selection_ids = compatibility_selection_ids(memo_compatibility, "memo-recall-rerun")
    memo_contradiction_gap_selection_ids = compatibility_selection_ids(memo_compatibility, "memo-contradiction-gap")
    memo_contradiction_rerun_selection_ids = compatibility_selection_ids(memo_compatibility, "memo-contradiction-rerun")
    evals_root = stack_root / "Knowledge" / "federation" / "aoa-evals"
    schema_path = evals_root / "schemas" / "runtime-evidence-selection.schema.json"
    bench_guide_path = evals_root / "docs" / "RUNTIME_BENCH_PROMOTION_GUIDE.md"
    recurrence_path = evals_root / "docs" / "RECURRENCE_PROOF_PROGRAM.md"
    workhorse_example_path = evals_root / "examples" / "runtime_evidence_selection.workhorse-local.example.json"
    return_example_path = evals_root / "examples" / "runtime_evidence_selection.return-anchor-integrity.example.json"
    memo_recall_example_path = evals_root / str(memo_compatibility["memo-recall-rerun"]["upstream_source_ref"])
    memo_contradiction_gap_example_path = (
        evals_root / str(memo_compatibility["memo-contradiction-gap"]["upstream_source_ref"])
    )
    memo_contradiction_rerun_example_path = (
        evals_root / str(memo_compatibility["memo-contradiction-rerun"]["upstream_source_ref"])
    )

    input_path = Path(args.input_file).resolve()
    raw_candidate_payload = read_json(input_path)
    if raw_candidate_payload.get("surface_type") != "runtime_evidence_selection":
        raise SystemExit("error: candidate payload must use surface_type runtime_evidence_selection")

    selection_id = raw_candidate_payload.get("selection_id")
    if not isinstance(selection_id, str) or not selection_id:
        raise SystemExit("error: candidate payload must include selection_id")
    source_input_ref = f"local:{input_path}"
    candidate_payload = canonical_runtime_evidence_selection(raw_candidate_payload, source_input_ref=source_input_ref)

    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    title = args.title or default_title(selection_id)
    summary = args.summary or f"Bounded aoa-evals runtime evidence selection candidate for {selection_id}."
    record_id = args.record_id or f"{timestamp}__runtime-evidence-selection__{slugify(selection_id)}"

    candidate_eval_refs = raw_candidate_payload.get("candidate_eval_refs", [])
    ref_paths = [f"local:{schema_path}", f"local:{bench_guide_path}"]
    source_example_ref = raw_candidate_payload.get("source_example_ref")
    example_contract_refs = {
        "examples/runtime_evidence_selection.workhorse-local.example.json": [workhorse_example_path],
        "examples/runtime_evidence_selection.return-anchor-integrity.example.json": [
            recurrence_path,
            return_example_path,
        ],
    }
    for ref in memo_recall_source_refs:
        example_contract_refs[ref] = [memo_recall_example_path]
    for ref in memo_contradiction_gap_source_refs:
        example_contract_refs[ref] = [memo_contradiction_gap_example_path]
    for ref in memo_contradiction_rerun_source_refs:
        example_contract_refs[ref] = [memo_contradiction_rerun_example_path]

    if isinstance(source_example_ref, str) and source_example_ref in example_contract_refs:
        ref_paths.extend(f"local:{path}" for path in example_contract_refs[source_example_ref])
    elif any(ref == "candidate:aoa-return-anchor-integrity" for ref in candidate_eval_refs):
        ref_paths.extend([f"local:{recurrence_path}", f"local:{return_example_path}"])
    elif (
        any(ref == "candidate:aoa-memo-recall-integrity" for ref in candidate_eval_refs)
        or selection_id_matches(selection_id, memo_recall_selection_ids)
    ):
        ref_paths.append(f"local:{memo_recall_example_path}")
    elif (
        any(ref == "candidate:aoa-memo-contradiction-integrity" for ref in candidate_eval_refs)
        or selection_id_matches(selection_id, memo_contradiction_gap_selection_ids)
        or selection_id_matches(selection_id, memo_contradiction_rerun_selection_ids)
    ):
        if selection_id_matches(selection_id, memo_contradiction_rerun_selection_ids):
            ref_paths.append(f"local:{memo_contradiction_rerun_example_path}")
        else:
            ref_paths.append(f"local:{memo_contradiction_gap_example_path}")
    else:
        ref_paths.append(f"local:{workhorse_example_path}")

    rendered_input = json.dumps(candidate_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    artifact = {
        "artifact_kind": "aoa.runtime-eval-evidence-selection-candidate",
        "schema_version": "1",
        "capture_mode": "private",
        "exported_at": captured_at,
        "exported_by": "scripts/aoa-export-runtime-evidence-selection",
        "record_id": record_id,
        "title": title,
        "summary": summary,
        "selection_id": selection_id,
        "source_input_ref": source_input_ref,
        "source_input_sha256": hashlib.sha256(rendered_input).hexdigest(),
        "aoa_evals_contract_refs": ref_paths,
        "candidate_payload": candidate_payload,
    }

    rendered = json.dumps(artifact, indent=2, ensure_ascii=True) + "\n"
    if args.write:
        latest_path = stack_root / "Logs" / "eval-exports" / "latest" / "runtime-evidence-selection" / f"{selection_id}.private.json"
        archive_dir = stack_root / "Logs" / "eval-exports" / "records" / f"{timestamp}__runtime-evidence-selection__{selection_id}"
        archive_path = archive_dir / "candidate.private.json"
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(rendered, encoding="utf-8")
        archive_path.write_text(rendered, encoding="utf-8")

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
