#!/usr/bin/env python3
"""Build public-safe quest catalog and dispatch examples from source quests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import quest_surface  # noqa: E402


def build_examples() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    catalog: list[dict[str, object]] = []
    dispatch: list[dict[str, object]] = []
    for quest_id in quest_surface.QUEST_IDS:
        payload = quest_surface.load_quest_payload(REPO_ROOT, quest_id)
        catalog.append(quest_surface.build_expected_quest_catalog_entry(quest_id, payload))
        dispatch.append(quest_surface.build_expected_quest_dispatch_entry(quest_id, payload))
    return catalog, dispatch


def formatted_json(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if examples are stale")
    args = parser.parse_args()

    catalog, dispatch = build_examples()
    outputs = {
        quest_surface.QUEST_CATALOG_EXAMPLE_PATH: formatted_json(catalog),
        quest_surface.QUEST_DISPATCH_EXAMPLE_PATH: formatted_json(dispatch),
    }

    stale: list[str] = []
    for relative_path, text in outputs.items():
        path = REPO_ROOT / relative_path
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(relative_path.as_posix())
            continue
        path.write_text(text, encoding="utf-8")

    if stale:
        print("Quest examples are stale:")
        for item in stale:
            print(f" - {item}")
        return 1
    if args.check:
        print("[ok] quest examples are fresh")
    else:
        print("[ok] quest examples rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
