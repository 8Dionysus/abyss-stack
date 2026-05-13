#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STACK_ROOT = Path(os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack"))
DEFAULT_WRITE_ROOT = STACK_ROOT / "Logs" / "runtime-benchmarks"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object at {path}")
    return payload


def parse_run_dir_name(name: str) -> tuple[str | None, str | None, str | None]:
    parts = name.split("__", 2)
    if len(parts) != 3:
        return None, None, None
    return parts[0], parts[1], parts[2]


def summarize_case_means(case_breakdown: dict[str, Any] | None) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    if not isinstance(case_breakdown, dict):
        return result
    for case_id, payload in sorted(case_breakdown.items()):
        if isinstance(payload, dict):
            value = payload.get("mean_s")
            result[str(case_id)] = value if isinstance(value, (int, float)) else None
    return result


def build_run_entry(summary_path: Path) -> dict[str, Any]:
    summary = load_json(summary_path)
    run_root = summary_path.parent
    timestamp_token, benchmark_family, target_label = parse_run_dir_name(run_root.name)
    manifest_path = run_root / "benchmark.manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {}
    system_under_test = manifest.get("system_under_test") if isinstance(manifest, dict) else {}
    if not isinstance(system_under_test, dict):
        system_under_test = {}
    return {
        "run_ref": str(run_root),
        "summary_ref": str(summary_path),
        "manifest_ref": str(manifest_path) if manifest_path.exists() else None,
        "run_dir": run_root.name,
        "timestamp_token": timestamp_token,
        "captured_at": summary.get("captured_at"),
        "benchmark_id": summary.get("benchmark_id"),
        "benchmark_family": benchmark_family,
        "target_label": target_label,
        "all_passed": bool(summary.get("all_passed")),
        "runtime_selection": summary.get("runtime_selection"),
        "backend": system_under_test.get("backend"),
        "model": system_under_test.get("model"),
        "runtime_variant": system_under_test.get("quantization_or_runtime_variant"),
        "overall_mean_s": summary.get("overall_mean_s"),
        "overall_best_s": summary.get("overall_best_s"),
        "overall_worst_s": summary.get("overall_worst_s"),
        "case_means_s": summarize_case_means(summary.get("case_breakdown")),
    }


def referenced_run_refs_from_comparison(path: Path) -> set[str]:
    payload = load_json(path)
    refs: set[str] = set()
    for key in ("baseline_run_ref", "candidate_run_ref"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            refs.add(value)
    return refs


def referenced_run_refs_from_promotion(path: Path) -> set[str]:
    payload = load_json(path)
    refs: set[str] = set()
    value = payload.get("baseline_run_ref")
    if isinstance(value, str) and value:
        refs.add(value)

    for screening_path in sorted(path.parent.glob("*.screening.json")):
        screening = load_json(screening_path)
        bench = screening.get("bench")
        if isinstance(bench, dict):
            run_dir = bench.get("run_dir")
            if isinstance(run_dir, str) and run_dir:
                refs.add(run_dir)
    return refs


def latest_entries_by_key(entries: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        value = entry.get(key)
        if not isinstance(value, str) or not value:
            continue
        existing = latest.get(value)
        if existing is None or str(entry.get("captured_at") or entry.get("timestamp_token") or "") >= str(
            existing.get("captured_at") or existing.get("timestamp_token") or ""
        ):
            latest[value] = entry
    return dict(sorted(latest.items()))


def load_latest_pointer(pointer_path: Path, kind: str) -> dict[str, Any] | None:
    if not pointer_path.exists():
        return None
    payload = load_json(pointer_path)
    latest_run_root = payload.get("latest_run_root")
    if not isinstance(latest_run_root, str):
        return None
    result: dict[str, Any] = {
        "kind": kind,
        "pointer_ref": str(pointer_path),
        "captured_at": payload.get("captured_at"),
        "latest_run_root": latest_run_root,
    }
    if kind == "comparison":
        result["comparison_ref"] = payload.get("comparison_ref")
        result["report_ref"] = payload.get("report_ref")
        comparison_ref = payload.get("comparison_ref")
        if isinstance(comparison_ref, str) and Path(comparison_ref).exists():
            comparison = load_json(Path(comparison_ref))
            result["pilot_id"] = comparison.get("pilot_id")
            result["preset"] = comparison.get("preset")
            result["baseline_backend"] = comparison.get("baseline_backend")
            result["candidate_backend"] = comparison.get("candidate_backend")
            result["overall_delta_s"] = comparison.get("overall_delta_s")
            result["recommendation"] = comparison.get("recommendation")
    if kind == "promotion":
        result["promotion_ref"] = payload.get("promotion_ref")
        result["report_ref"] = payload.get("report_ref")
        promotion_ref = payload.get("promotion_ref")
        if isinstance(promotion_ref, str) and Path(promotion_ref).exists():
            promotion = load_json(Path(promotion_ref))
            result["promotion_id"] = promotion.get("promotion_id")
            result["winner_quant"] = promotion.get("winner_quant")
            result["winner_model_host_path"] = promotion.get("winner_model_host_path")
            promotion_block = promotion.get("promotion")
            if isinstance(promotion_block, dict):
                result["w0_gate_result"] = promotion_block.get("w0_gate_result")
                result["w4_gate_result"] = promotion_block.get("w4_gate_result")
                result["recommendation"] = promotion_block.get("recommendation")
    return result


def collect_latest_group(root: Path, kind: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if not root.exists():
        return results
    for child in sorted(path for path in root.iterdir() if path.is_dir()):
        pointer = child / "latest.json"
        loaded = load_latest_pointer(pointer, kind)
        if loaded is None:
            continue
        results[child.name] = loaded
    return results


def collect_packet_references(write_root: Path) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    latest_refs = {"comparison": set(), "promotion": set()}
    all_refs = {"comparison": set(), "promotion": set()}

    comparisons_root = write_root / "comparisons"
    promotions_root = write_root / "promotions"

    for comparison_path in sorted(comparisons_root.glob("*/runs/*/comparison.json")):
        refs = referenced_run_refs_from_comparison(comparison_path)
        all_refs["comparison"].update(refs)
    for promotion_path in sorted(promotions_root.glob("*/runs/*/promotion.json")):
        refs = referenced_run_refs_from_promotion(promotion_path)
        all_refs["promotion"].update(refs)

    for child in sorted(path for path in comparisons_root.iterdir() if path.is_dir()):
        pointer = child / "latest.json"
        if not pointer.exists():
            continue
        payload = load_json(pointer)
        comparison_ref = payload.get("comparison_ref")
        if isinstance(comparison_ref, str) and Path(comparison_ref).exists():
            latest_refs["comparison"].update(referenced_run_refs_from_comparison(Path(comparison_ref)))

    for child in sorted(path for path in promotions_root.iterdir() if path.is_dir()):
        pointer = child / "latest.json"
        if not pointer.exists():
            continue
        payload = load_json(pointer)
        promotion_ref = payload.get("promotion_ref")
        if isinstance(promotion_ref, str) and Path(promotion_ref).exists():
            latest_refs["promotion"].update(referenced_run_refs_from_promotion(Path(promotion_ref)))

    return latest_refs, all_refs


def classify_retention(
    run_entries: list[dict[str, Any]],
    latest_by_target_label: dict[str, dict[str, Any]],
    latest_packet_refs: dict[str, set[str]],
    all_packet_refs: dict[str, set[str]],
) -> dict[str, Any]:
    latest_target_refs = {
        str(entry["run_ref"])
        for entry in latest_by_target_label.values()
        if isinstance(entry.get("run_ref"), str)
    }
    latest_pointer_refs = set().union(*latest_packet_refs.values())
    all_pointer_refs = set().union(*all_packet_refs.values())
    active_target_labels = set(latest_by_target_label.keys())

    by_class: dict[str, list[dict[str, Any]]] = {
        "canonical": [],
        "historical": [],
        "exploratory": [],
    }
    run_class_map: dict[str, dict[str, str]] = {}

    for entry in run_entries:
        run_ref = str(entry["run_ref"])
        target_label = str(entry.get("target_label") or "")
        if run_ref in latest_pointer_refs:
            retention_class = "canonical"
            reason = "referenced by the current latest comparison or promotion packet"
        elif run_ref in latest_target_refs:
            retention_class = "canonical"
            reason = "latest run for its target label"
        elif run_ref in all_pointer_refs:
            retention_class = "historical"
            reason = "referenced by an older comparison or promotion packet"
        elif target_label in active_target_labels:
            retention_class = "historical"
            reason = "older run in an active target lineage"
        else:
            retention_class = "exploratory"
            reason = "not referenced by current or historical durable comparison surfaces"

        retained = {
            "run_ref": run_ref,
            "captured_at": entry.get("captured_at"),
            "target_label": entry.get("target_label"),
            "benchmark_id": entry.get("benchmark_id"),
            "overall_mean_s": entry.get("overall_mean_s"),
            "retention_reason": reason,
        }
        by_class[retention_class].append(retained)
        run_class_map[run_ref] = {
            "retention_class": retention_class,
            "retention_reason": reason,
        }

    return {
        "classes": by_class,
        "run_class_map": run_class_map,
        "counts": {
            "canonical": len(by_class["canonical"]),
            "historical": len(by_class["historical"]),
            "exploratory": len(by_class["exploratory"]),
        },
    }


def latest_promotion_payload(write_root: Path) -> dict[str, Any] | None:
    pointer = write_root / "promotions" / "llamacpp-promotion-gate-v1" / "latest.json"
    if not pointer.exists():
        return None
    payload = load_json(pointer)
    promotion_ref = payload.get("promotion_ref")
    if not isinstance(promotion_ref, str):
        return None
    promotion_path = Path(promotion_ref)
    if not promotion_path.exists():
        return None
    promotion = load_json(promotion_path)
    promotion["_promotion_path"] = str(promotion_path)
    return promotion


def determine_cohorts(
    write_root: Path,
    run_entries: list[dict[str, Any]],
    latest_by_target_label: dict[str, dict[str, Any]],
    latest_packet_refs: dict[str, set[str]],
    retention: dict[str, Any],
) -> dict[str, Any]:
    entries_by_ref = {str(entry["run_ref"]): entry for entry in run_entries}
    latest_target_refs = {
        str(entry["run_ref"])
        for entry in latest_by_target_label.values()
        if isinstance(entry.get("run_ref"), str)
    }
    control_target_labels = {
        label
        for label in latest_by_target_label
        if "llamacpp" not in label or "ollama-baseline" in label
    }
    current_control_refs = sorted(
        str(latest_by_target_label[label]["run_ref"])
        for label in sorted(control_target_labels)
        if label in latest_by_target_label
    )

    historical_baseline_refs = sorted(
        row["run_ref"]
        for row in retention["classes"]["historical"]
        if row.get("target_label") in control_target_labels
    )

    promotion_basis_refs = sorted(set().union(*latest_packet_refs.values()))

    promoted_substrate_refs: list[str] = []
    comparison_challenger_refs: list[str] = []
    promotion = latest_promotion_payload(write_root)
    if promotion:
        winner_quant = promotion.get("winner_quant")
        screening_paths = sorted(
            Path(str(promotion["_promotion_path"])).parent.glob("*.screening.json")
        )
        for screening_path in screening_paths:
            screening = load_json(screening_path)
            bench = screening.get("bench")
            if not isinstance(bench, dict):
                continue
            run_ref = bench.get("run_dir")
            if not isinstance(run_ref, str) or run_ref not in entries_by_ref:
                continue
            quant = screening.get("quant")
            if quant == winner_quant:
                promoted_substrate_refs.append(run_ref)
            else:
                comparison_challenger_refs.append(run_ref)

    cohort_order = [
        ("current-control", current_control_refs, "latest control-path runs used as the default local baseline set"),
        ("promotion-basis", promotion_basis_refs, "runs referenced by the current latest comparison or promotion packets"),
        ("current-promoted", sorted(set(promoted_substrate_refs)), "latest promoted llama.cpp winner runs referenced by the current promotion verdict"),
        ("comparison-challenger", sorted(set(comparison_challenger_refs)), "latest challenger runs kept beside the promoted winner for bounded backend comparison"),
        ("historical-baseline", historical_baseline_refs, "historical control-path runs kept for baseline lineage and drift review"),
    ]

    classes: dict[str, list[dict[str, Any]]] = {}
    run_memberships: dict[str, list[str]] = {str(entry["run_ref"]): [] for entry in run_entries}
    notes: dict[str, str] = {}

    for cohort_id, refs, note in cohort_order:
        notes[cohort_id] = note
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for run_ref in refs:
            if run_ref in seen:
                continue
            seen.add(run_ref)
            entry = entries_by_ref.get(run_ref)
            if entry is None:
                continue
            rows.append(
                {
                    "run_ref": run_ref,
                    "captured_at": entry.get("captured_at"),
                    "target_label": entry.get("target_label"),
                    "benchmark_id": entry.get("benchmark_id"),
                    "overall_mean_s": entry.get("overall_mean_s"),
                }
            )
            run_memberships[run_ref].append(cohort_id)
        classes[cohort_id] = rows

    return {
        "notes": notes,
        "classes": classes,
        "counts": {key: len(value) for key, value in classes.items()},
        "run_memberships": run_memberships,
    }


def build_catalog(write_root: Path) -> dict[str, Any]:
    runs_root = write_root / "runs"
    comparisons_root = write_root / "comparisons"
    promotions_root = write_root / "promotions"

    run_entries = [
        build_run_entry(path)
        for path in sorted(runs_root.glob("*/summary.json"))
    ]

    latest_by_target_label = latest_entries_by_key(run_entries, "target_label")
    latest_by_benchmark_id = latest_entries_by_key(run_entries, "benchmark_id")
    latest_by_family = latest_entries_by_key(run_entries, "benchmark_family")
    latest_packet_refs, all_packet_refs = collect_packet_references(write_root)
    retention = classify_retention(run_entries, latest_by_target_label, latest_packet_refs, all_packet_refs)
    cohorts = determine_cohorts(write_root, run_entries, latest_by_target_label, latest_packet_refs, retention)

    comparisons = collect_latest_group(comparisons_root, "comparison")
    promotions = collect_latest_group(promotions_root, "promotion")

    return {
        "catalog_id": "runtime-benchmarks-catalog-v1",
        "generated_at": utc_now(),
        "write_root": str(write_root),
        "retention_posture": "keep raw runs as evidence, use latest pointers and this catalog for durable navigation",
        "retention": {
            "counts": retention["counts"],
            "policy": {
                "canonical": "current latest pointers and latest runs for active target labels",
                "historical": "older runs in active lineages or runs referenced by older comparison/promotion packets",
                "exploratory": "runs not referenced by durable comparison surfaces",
            },
        },
        "cohorts": {
            "counts": cohorts["counts"],
            "notes": cohorts["notes"],
            "ref": str(write_root / "cohorts.json"),
        },
        "runs": {
            "count": len(run_entries),
            "index_ref": str(write_root / "runs" / "index.json"),
            "latest_by_target_label": {
                key: {
                    "run_ref": value["run_ref"],
                    "captured_at": value["captured_at"],
                    "overall_mean_s": value["overall_mean_s"],
                    "case_means_s": value["case_means_s"],
                }
                for key, value in latest_by_target_label.items()
            },
            "latest_by_benchmark_id": {
                key: {
                    "run_ref": value["run_ref"],
                    "captured_at": value["captured_at"],
                    "overall_mean_s": value["overall_mean_s"],
                }
                for key, value in latest_by_benchmark_id.items()
            },
            "latest_by_family": {
                key: {
                    "run_ref": value["run_ref"],
                    "target_label": value["target_label"],
                    "captured_at": value["captured_at"],
                }
                for key, value in latest_by_family.items()
            },
        },
        "comparisons": comparisons,
        "promotions": promotions,
        "retention_ref": str(write_root / "retention.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a durable runtime benchmark catalog")
    parser.add_argument(
        "--write-root",
        default=str(DEFAULT_WRITE_ROOT),
        help="runtime benchmark root (default: %(default)s)",
    )
    args = parser.parse_args()

    write_root = Path(args.write_root).expanduser().resolve()
    catalog = build_catalog(write_root)

    runs_root = write_root / "runs"
    run_entries = [
        build_run_entry(path)
        for path in sorted(runs_root.glob("*/summary.json"))
    ]
    latest_by_target_label = latest_entries_by_key(run_entries, "target_label")
    latest_packet_refs, all_packet_refs = collect_packet_references(write_root)
    retention = classify_retention(run_entries, latest_by_target_label, latest_packet_refs, all_packet_refs)
    cohorts = determine_cohorts(write_root, run_entries, latest_by_target_label, latest_packet_refs, retention)
    run_entries_with_retention = []
    for entry in run_entries:
        enriched = dict(entry)
        enriched.update(retention["run_class_map"][str(entry["run_ref"])])
        enriched["cohort_memberships"] = cohorts["run_memberships"][str(entry["run_ref"])]
        run_entries_with_retention.append(enriched)

    latest_root = write_root / "latest"
    latest_index = {
        "generated_at": catalog["generated_at"],
        "catalog_ref": str(write_root / "catalog.json"),
        "retention_ref": str(write_root / "retention.json"),
        "cohorts_ref": str(write_root / "cohorts.json"),
        "comparison_refs": {
            key: value.get("pointer_ref")
            for key, value in catalog["comparisons"].items()
        },
        "promotion_refs": {
            key: value.get("pointer_ref")
            for key, value in catalog["promotions"].items()
        },
        "latest_runs_by_target_label": catalog["runs"]["latest_by_target_label"],
        "canonical_run_refs": [
            item["run_ref"]
            for item in retention["classes"]["canonical"]
        ],
        "cohort_refs": {
            key: [row["run_ref"] for row in value]
            for key, value in cohorts["classes"].items()
        },
    }
    run_index = {
        "generated_at": catalog["generated_at"],
        "count": len(run_entries_with_retention),
        "entries": run_entries_with_retention,
    }
    retention_index = {
        "generated_at": catalog["generated_at"],
        "counts": retention["counts"],
        "classes": retention["classes"],
        "notes": {
            "canonical": "use these first for repeatable control-path and promotion-path comparison",
            "historical": "keep these for lineage and reviewable decision history",
            "exploratory": "keep these as local evidence, but do not treat them as the default comparison set",
        },
    }
    cohort_index = {
        "generated_at": catalog["generated_at"],
        "counts": cohorts["counts"],
        "notes": cohorts["notes"],
        "classes": cohorts["classes"],
    }

    write_json(write_root / "catalog.json", catalog)
    write_json(latest_root / "index.json", latest_index)
    write_json(runs_root / "index.json", run_index)
    write_json(write_root / "retention.json", retention_index)
    write_json(write_root / "cohorts.json", cohort_index)

    print(json.dumps({
        "ok": True,
        "catalog_ref": str(write_root / "catalog.json"),
        "latest_ref": str(latest_root / "index.json"),
        "run_index_ref": str(runs_root / "index.json"),
        "retention_ref": str(write_root / "retention.json"),
        "cohorts_ref": str(write_root / "cohorts.json"),
        "run_count": len(run_entries),
        "comparison_count": len(catalog["comparisons"]),
        "promotion_count": len(catalog["promotions"]),
        "canonical_count": retention["counts"]["canonical"],
        "historical_count": retention["counts"]["historical"],
        "exploratory_count": retention["counts"]["exploratory"],
        "current_control_count": cohorts["counts"].get("current-control", 0),
        "promotion_basis_count": cohorts["counts"].get("promotion-basis", 0),
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
