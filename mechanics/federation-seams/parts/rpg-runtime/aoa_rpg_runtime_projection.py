#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / "scripts").is_dir() and (candidate / "mechanics").is_dir():
            return candidate
    raise RuntimeError(f"could not find abyss-stack root from {start}")


ROOT = find_repo_root(Path(__file__).resolve().parent)
DEFAULT_STACK_ROOT = Path(os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack"))
RPG_SURFACE_ROOT = Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime"
RPG_SCHEMA_ROOT = RPG_SURFACE_ROOT / "schemas"
RPG_EXAMPLE_ROOT = RPG_SURFACE_ROOT / "examples"
RPG_GENERATED_ROOT = Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime" / "generated"
RPG_GENERATED_REF_ROOT = "abyss-stack/mechanics/federation-seams/parts/rpg-runtime/generated"

GENERATED_COLLECTIONS = (
    ("agent_build_snapshots.json", "builds", "agent_build_snapshot_collection_v1", "agent_build_snapshot_v1"),
    ("reputation_ledgers.json", "ledgers", "reputation_ledger_collection_v1", "reputation_ledger_v1"),
    ("quest_run_results.json", "runs", "quest_run_result_collection_v1", "quest_run_result_v1"),
    ("frontend_projection_bundles.json", "bundles", "frontend_projection_bundle_collection_v1", "frontend_projection_bundle_v1"),
)

UNLOCK_PROOF_REF = "aoa-evals/generated/unlock_proof_cards.min.example.json#UP-2026-04-04-0001"
ROUTING_REF = "aoa-routing/generated/rpg_navigation.min.example.json#nav.AOA-P-0011.safe-change-pair"
CAMPAIGN_REF = "aoa-playbooks/examples/questline_outline.example.yaml#AOA-PB-CAMP-0001"
CHRONICLE_REF = "aoa-memo/examples/quest_chronicle.example.json#AOA-MEM-CHRON-EXAMPLE-0001"
OVERLAY_REF = "Agents-of-Abyss/generated/dual_vocabulary_overlay.json"


def read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"error: expected JSON object in {path}")
    return payload


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def fragment_ref(relative_path: str, fragment_id: str) -> str:
    return f"{relative_path}#{fragment_id}"


def require_jsonschema():
    try:
        import jsonschema
    except ModuleNotFoundError as exc:
        raise SystemExit("error: jsonschema is required to validate RPG runtime projection outputs") from exc
    return jsonschema


def build_collections(repo_root: Path) -> dict[str, dict]:
    build = copy.deepcopy(read_json(repo_root / RPG_EXAMPLE_ROOT / "agent_build_snapshot.example.json"))
    ledger = copy.deepcopy(read_json(repo_root / RPG_EXAMPLE_ROOT / "reputation_ledger.example.json"))
    run = copy.deepcopy(read_json(repo_root / RPG_EXAMPLE_ROOT / "quest_run_result.example.json"))
    bundle = copy.deepcopy(read_json(repo_root / RPG_EXAMPLE_ROOT / "frontend_projection_bundle.example.json"))

    build_ref = fragment_ref(f"{RPG_GENERATED_REF_ROOT}/agent_build_snapshots.json", build["snapshot_id"])
    ledger_ref = fragment_ref(f"{RPG_GENERATED_REF_ROOT}/reputation_ledgers.json", ledger["ledger_id"])
    run_ref = fragment_ref(f"{RPG_GENERATED_REF_ROOT}/quest_run_results.json", run["run_id"])

    build["reputation_refs"] = [ledger_ref]
    build["notes"] = (
        "Generated transport build snapshot for the body-facing RPG slice. "
        "Ability and feat ids remain pass-through refs in this source contract."
    )

    ledger["slices"] = [
        {
            "slice_id": f"slice.proof.{ledger['subject_ref']}",
            "axis": "proof_trust",
            "owner_scope": "aoa-evals",
            "standing": 72,
            "last_delta": 4,
            "cause_kind": "eval_verdict",
            "cause_ref": UNLOCK_PROOF_REF,
            "evidence_refs": [
                UNLOCK_PROOF_REF,
                run_ref,
            ],
            "freshness": "warm",
            "recorded_at": ledger["generated_at"],
        },
        {
            "slice_id": f"slice.boundary.{ledger['subject_ref']}",
            "axis": "boundary_trust",
            "owner_scope": "Agents-of-Abyss",
            "standing": 68,
            "last_delta": 3,
            "cause_kind": "quest_run",
            "cause_ref": run_ref,
            "evidence_refs": [
                run_ref,
                "Agents-of-Abyss/mechanics/rpg/parts/runtime-projection/README.md",
            ],
            "freshness": "hot",
            "recorded_at": ledger["generated_at"],
            "notes": "Runtime collection refresh stayed downstream of source-owned meaning.",
        },
    ]
    ledger["notes"] = "Generated transport ledger for the body-facing RPG slice. Standing remains scoped and cited."

    run["quest_ref"] = "AOA-Q-0008"
    run["execution"]["build_snapshot_refs"] = [build_ref]
    run["artifact_refs"] = [
        "Agents-of-Abyss/mechanics/rpg/parts/runtime-projection/README.md",
        "abyss-stack/mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_COLLECTIONS.md",
        "abyss-stack/mechanics/federation-seams/parts/rpg-runtime/docs/RPG_FRONTEND_PROJECTION_SEAM.md",
    ]
    run["proof_refs"] = [UNLOCK_PROOF_REF]
    run["chronicle_refs"] = [CHRONICLE_REF]
    run["outcome"]["summary"] = (
        "Filesystem-first RPG collections and runtime copies were materialized without widening "
        "source ownership or route-api authority."
    )
    run["progression_effects"]["evidence_refs"] = [UNLOCK_PROOF_REF]
    run["progression_effects"]["unlock_candidate_ids"] = ["unlock.rpg.runtime-projection.inspect"]
    run["reputation_effects"] = [
        {
            "axis": "proof_trust",
            "owner_scope": "aoa-evals",
            "delta": 4,
            "cause_ref": UNLOCK_PROOF_REF,
        },
        {
            "axis": "boundary_trust",
            "owner_scope": "Agents-of-Abyss",
            "delta": 3,
            "cause_ref": run_ref,
        },
    ]
    run["next_hops"] = [
        {
            "action": "inspect",
            "target_ref": "abyss-stack/mechanics/federation-seams/parts/rpg-runtime/docs/RPG_FRONTEND_PROJECTION_SEAM.md",
            "note": "Keep the frontend bundle derived and cited.",
        },
        {
            "action": "handoff",
            "target_ref": "Dionysus/seed_staging/rpg/seed_rpg_runtime_projection_pack.md",
            "note": "Sync the Dionysus prep-pack lineage after the runtime body lands.",
        },
    ]
    run["notes"] = "Generated transport run envelope for the body-facing RPG slice. Quest-state motion remains a hint, not a source write."

    bundle["vocabulary_overlay_ref"] = OVERLAY_REF
    bundle["source_refs"] = {
        "build_snapshots": [build_ref],
        "reputation_ledgers": [ledger_ref],
        "quest_run_results": [run_ref],
        "quest_board_refs": [ROUTING_REF],
        "campaign_refs": [CAMPAIGN_REF],
    }
    bundle["views"]["agent_sheet_cards"][0]["build_snapshot_ref"] = build_ref
    bundle["views"]["agent_sheet_cards"][0]["active_quest_refs"] = ["AOA-Q-0008"]
    bundle["views"]["quest_board_cards"][0]["quest_ref"] = "AOA-Q-0008"
    bundle["views"]["quest_board_cards"][0]["title"] = "Define the RPG runtime projection slice for the first body-facing AoA route"
    bundle["views"]["quest_board_cards"][0]["state"] = "triaged"
    bundle["views"]["quest_board_cards"][0]["source_ref"] = "Agents-of-Abyss/quests/AOA-Q-0008.yaml"
    bundle["views"]["quest_board_cards"][0]["reward_hints"] = [
        "live runtime collections",
        "frontend-ready derived bundle",
    ]
    bundle["views"]["quest_board_cards"][0]["penalty_hints"] = [
        "no direct quest-state writes",
        "no secret reward engine",
    ]
    bundle["views"]["campaign_lane_cards"][0]["campaign_ref"] = "campaign.rpg.runtime-projection"
    bundle["views"]["campaign_lane_cards"][0]["title"] = "RPG Runtime Projection"
    bundle["views"]["campaign_lane_cards"][0]["stage_label"] = "collections before services"
    bundle["views"]["campaign_lane_cards"][0]["anchor_refs"] = [
        "Agents-of-Abyss/mechanics/rpg/parts/runtime-projection/README.md",
        "abyss-stack/mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_COLLECTIONS.md",
        "abyss-stack/mechanics/federation-seams/parts/rpg-runtime/docs/RPG_FRONTEND_PROJECTION_SEAM.md",
    ]
    bundle["views"]["campaign_lane_cards"][0]["recommended_build_refs"] = [build_ref]
    bundle["views"]["campaign_lane_cards"][0]["source_ref"] = "Dionysus/seed_staging/rpg/seed_rpg_runtime_projection_pack.md"
    bundle["views"]["progression_timeline_entries"][0]["summary"] = (
        "Filesystem-first runtime collections were materialized without turning projection bundles into authority."
    )
    bundle["views"]["progression_timeline_entries"][0]["source_ref"] = run_ref
    bundle["views"]["reputation_panels"][0]["ledger_ref"] = ledger_ref
    bundle["notes"] = (
        "Generated transport bundle for the body-facing RPG slice. "
        "UI labels may theme the payload, but canonical keys and source refs stay visible."
    )

    return {
        "agent_build_snapshots.json": {
            "schema_version": "agent_build_snapshot_collection_v1",
            "builds": [build],
        },
        "reputation_ledgers.json": {
            "schema_version": "reputation_ledger_collection_v1",
            "ledgers": [ledger],
        },
        "quest_run_results.json": {
            "schema_version": "quest_run_result_collection_v1",
            "runs": [run],
        },
        "frontend_projection_bundles.json": {
            "schema_version": "frontend_projection_bundle_collection_v1",
            "bundles": [bundle],
        },
    }


def validate_collection(repo_root: Path, filename: str, array_key: str, collection_version: str, item_version: str, payload: dict) -> None:
    jsonschema = require_jsonschema()
    collection_schema_name = {
        "agent_build_snapshots.json": "agent_build_snapshot_collection.schema.json",
        "reputation_ledgers.json": "reputation_ledger_collection.schema.json",
        "quest_run_results.json": "quest_run_result_collection.schema.json",
        "frontend_projection_bundles.json": "frontend_projection_bundle_collection.schema.json",
    }[filename]
    collection_schema = read_json(repo_root / RPG_SCHEMA_ROOT / collection_schema_name)
    item_schema_name = {
        "builds": "agent_build_snapshot.schema.json",
        "ledgers": "reputation_ledger.schema.json",
        "runs": "quest_run_result.schema.json",
        "bundles": "frontend_projection_bundle.schema.json",
    }[array_key]
    item_schema = read_json(repo_root / RPG_SCHEMA_ROOT / item_schema_name)

    jsonschema.validate(payload, collection_schema)
    if payload.get("schema_version") != collection_version:
        raise SystemExit(f"error: {filename} must use schema_version {collection_version}")

    items = payload.get(array_key)
    if not isinstance(items, list) or not items:
        raise SystemExit(f"error: {filename} must include a non-empty {array_key} array")

    for index, item in enumerate(items):
        jsonschema.validate(item, item_schema)
        if item.get("schema_version") != item_version:
            raise SystemExit(
                f"error: {filename} item {index} must use schema_version {item_version}"
            )
        if item.get("public_safe") is not True:
            raise SystemExit(f"error: {filename} item {index} must set public_safe true")


def validate_all(repo_root: Path, collections: dict[str, dict]) -> None:
    for filename, array_key, collection_version, item_version in GENERATED_COLLECTIONS:
        validate_collection(repo_root, filename, array_key, collection_version, item_version, collections[filename])


def write_generated(repo_root: Path, collections: dict[str, dict]) -> None:
    generated_root = repo_root / RPG_GENERATED_ROOT
    for filename, *_ in GENERATED_COLLECTIONS:
        write_json(generated_root / filename, collections[filename])


def materialize_runtime(stack_root: Path, collections: dict[str, dict], *, write_records: bool) -> None:
    latest_root = stack_root / "Logs" / "rpg" / "latest"
    records_root = stack_root / "Logs" / "rpg" / "records"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for filename, *_ in GENERATED_COLLECTIONS:
        latest_path = latest_root / filename
        write_json(latest_path, collections[filename])
        if write_records:
            record_path = records_root / filename.removesuffix(".json") / f"{timestamp}.json"
            write_json(record_path, collections[filename])


def check_parity(repo_root: Path, stack_root: Path, *, check_runtime: bool) -> None:
    expected = build_collections(repo_root)
    validate_all(repo_root, expected)
    latest_root = stack_root / "Logs" / "rpg" / "latest"
    latest_paths = {
        filename: latest_root / filename
        for filename, *_ in GENERATED_COLLECTIONS
    }
    runtime_files_present = (
        {
            filename: path.exists()
            for filename, path in latest_paths.items()
        }
        if check_runtime
        else {filename: False for filename, *_ in GENERATED_COLLECTIONS}
    )
    if any(runtime_files_present.values()) and not all(runtime_files_present.values()):
        missing = ", ".join(
            filename
            for filename, present in runtime_files_present.items()
            if not present
        )
        raise SystemExit(f"error: Logs/rpg/latest is partially populated; missing: {missing}")

    for filename, array_key, collection_version, item_version in GENERATED_COLLECTIONS:
        generated_payload = read_json(repo_root / RPG_GENERATED_ROOT / filename)
        validate_collection(
            repo_root,
            filename,
            array_key,
            collection_version,
            item_version,
            generated_payload,
        )
        if generated_payload != expected[filename]:
            raise SystemExit(f"error: {RPG_GENERATED_ROOT.as_posix()}/{filename} is out of sync with builder output")

        if not runtime_files_present[filename]:
            continue

        latest_payload = read_json(latest_paths[filename])
        validate_collection(
            repo_root,
            filename,
            array_key,
            collection_version,
            item_version,
            latest_payload,
        )
        if latest_payload != generated_payload:
            raise SystemExit(f"error: Logs/rpg/latest/{filename} must match {RPG_GENERATED_ROOT.as_posix()}/{filename}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and validate filesystem-first RPG runtime projection collections."
    )
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--stack-root", default=str(DEFAULT_STACK_ROOT))
    parser.add_argument("--generated-only", action="store_true")
    parser.add_argument("--skip-records", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    stack_root = Path(args.stack_root).resolve()

    if args.check:
        check_parity(repo_root, stack_root, check_runtime=not args.generated_only)
        print("[ok] validated RPG runtime projection parity")
        return 0

    collections = build_collections(repo_root)
    validate_all(repo_root, collections)
    write_generated(repo_root, collections)
    if not args.generated_only:
        materialize_runtime(stack_root, collections, write_records=not args.skip_records)
    print("[ok] wrote RPG runtime projection collections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
