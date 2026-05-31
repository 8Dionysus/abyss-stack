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

RUNTIME_SURFACES = {
    "checkpoint_export",
    "approval_record",
    "transition_record",
    "execution_trace",
    "review_trace",
    "distillation_claim_candidate",
    "distillation_pattern_candidate",
    "distillation_bridge_candidate",
}


def slugify(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = lowered.strip("-")
    return lowered or "candidate"


def default_title(runtime_surface: str, target_kind: str) -> str:
    return f"{runtime_surface.replace('_', ' ')} -> {target_kind}"


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


def load_mapping(stack_root: Path, runtime_surface: str) -> tuple[Path, dict, dict]:
    contract_path = (
        stack_root
        / "Knowledge"
        / "federation"
        / "aoa-memo"
        / "mechanics"
        / "checkpoint"
        / "parts"
        / "checkpoint-to-memory-mapping"
        / "examples"
        / "checkpoint_to_memory_contract.example.json"
    )
    contract = read_json(contract_path)
    for mapping in contract.get("mapping_rules", []):
        if mapping.get("runtime_surface") == runtime_surface:
            return contract_path, contract, mapping
    raise SystemExit(f"error: no mapping found for runtime surface: {runtime_surface}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a bounded runtime memo candidate artifact from the aoa-memo checkpoint mapping seam."
    )
    parser.add_argument("--runtime-surface", required=True, choices=sorted(RUNTIME_SURFACES))
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--record-id")
    parser.add_argument("--title")
    parser.add_argument("--summary")
    parser.add_argument("--write", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    stack_root = Path(os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack"))
    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")

    contract_path, contract, mapping = load_mapping(stack_root, args.runtime_surface)
    input_path = Path(args.input_file).resolve()
    candidate_payload = read_json(input_path)
    title = args.title or default_title(args.runtime_surface, mapping["target_kind"])
    summary = args.summary or mapping.get("notes") or f"Bounded memo export candidate for {args.runtime_surface}."
    record_id = args.record_id or f"{timestamp}__{args.runtime_surface}__{slugify(title)}"

    rendered_input = json.dumps(candidate_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    artifact = {
        "artifact_kind": "aoa.runtime-memo-export-candidate",
        "schema_version": "1",
        "capture_mode": "private",
        "exported_at": captured_at,
        "exported_by": "scripts/aoa-export-memo-candidate",
        "record_id": record_id,
        "title": title,
        "summary": summary,
        "runtime_surface": args.runtime_surface,
        "target_kind": mapping["target_kind"],
        "writeback_class": mapping["writeback_class"],
        "temperature_hint": mapping["temperature_hint"],
        "requires_human_review": bool(mapping["requires_human_review"]),
        "review_state_default": mapping["review_state_default"],
        "source_input_ref": f"local:{input_path}",
        "source_input_sha256": hashlib.sha256(rendered_input).hexdigest(),
        "contract_type": contract["contract_type"],
        "contract_id": contract["contract_id"],
        "runtime_boundary": contract["runtime_boundary"],
        "memo_contract_refs": [
            f"local:{contract_path}",
            *mapping.get("runtime_refs", []),
        ],
        "candidate_payload": candidate_payload,
    }

    rendered = json.dumps(artifact, indent=2, ensure_ascii=True) + "\n"
    if args.write:
        latest_path = stack_root / "Logs" / "memo-exports" / "latest" / f"{args.runtime_surface}.private.json"
        archive_dir = stack_root / "Logs" / "memo-exports" / "records" / f"{timestamp}__{args.runtime_surface}__{slugify(title)}"
        archive_path = archive_dir / "candidate.private.json"
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(rendered, encoding="utf-8")
        archive_path.write_text(rendered, encoding="utf-8")

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
