#!/usr/bin/env python3
"""Generate docs/decisions lookup indexes from decision-note metadata."""

from __future__ import annotations

import argparse
from pathlib import Path

import decision_indexes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated indexes are stale")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    if args.check:
        issues = decision_indexes.validate_decision_index_surfaces(repo_root)
        if issues:
            for location, message in issues:
                print(f"- {location}: {message}")
            return 1
        return 0

    records, issues = decision_indexes.collect_decision_records(repo_root)
    contract, contract_issues = decision_indexes.load_index_contract(repo_root)
    issues.extend(contract_issues)
    if contract is not None:
        issues.extend(decision_indexes.validate_index_contract_payload(contract))
    if issues:
        for location, message in issues:
            print(f"- {location}: {message}")
        return 1

    for relative_path, expected_text in decision_indexes.render_generated_files(records).items():
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
