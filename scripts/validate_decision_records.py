#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

import decision_indexes


REPO_ROOT = Path(__file__).resolve().parents[1]
DECISIONS_DIR = REPO_ROOT / "docs" / "decisions"
README_PATH = DECISIONS_DIR / "README.md"

DATE_RE = re.compile(r"^- Date:\s*(?P<date>\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
STATUS_RE = re.compile(r"^- Status:\s*(?P<status>[A-Za-z][A-Za-z0-9_-]*)\s*$", re.MULTILINE)

EXEMPT_FILES = {"AGENTS.md", "README.md", "TEMPLATE.md"}
STATUS_VALUES = {"accepted", "proposed", "superseded", "amended"}
REQUIRED_SECTIONS = (
    "## Index Metadata",
    "## Context",
    "## Options considered",
    "## Decision",
    "## Rationale",
    "## Consequences",
    "## Source surfaces",
    "## Follow-up route",
)


def repo_rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def decision_record_paths(decisions_dir: Path = DECISIONS_DIR) -> list[Path]:
    return sorted(path for path in decisions_dir.glob("*.md") if path.name not in EXEMPT_FILES)


def validate_record(path: Path) -> list[str]:
    problems: list[str] = []
    rel = repo_rel(path)
    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        problems.append(f"{rel}: missing final newline")
    if not text.startswith("# "):
        problems.append(f"{rel}: must start with an H1 title")

    status_match = STATUS_RE.search(text)
    if not status_match:
        problems.append(f"{rel}: missing top metadata '- Status: <value>'")
    else:
        status = status_match.group("status").lower()
        if status not in STATUS_VALUES:
            allowed = ", ".join(sorted(STATUS_VALUES))
            problems.append(f"{rel}: unsupported status {status_match.group('status')!r}; allowed: {allowed}")

    date_match = DATE_RE.search(text)
    if not date_match:
        problems.append(f"{rel}: missing top metadata '- Date: YYYY-MM-DD'")

    for section in REQUIRED_SECTIONS:
        if section not in text:
            problems.append(f"{rel}: missing section {section}")

    try:
        record_repo_root = REPO_ROOT if path.is_relative_to(REPO_ROOT) else path.parent
        record = decision_indexes.load_decision_record(path, repo_root=record_repo_root)
    except ValueError as exc:
        problems.append(f"{rel}: {exc}")
        return problems

    filename_match = decision_indexes.FULL_ID_FILENAME_RE.match(path.name)
    if not filename_match:
        problems.append(f"{rel}: decision record filename must be ABYSS-STACK-D-####-kebab.md")
    elif filename_match.group(1) != record.decision_id:
        problems.append(f"{rel}: filename ID does not match note Decision ID {record.decision_id}")

    if date_match and date_match.group("date") != record.date:
        problems.append(
            f"{rel}: Date {date_match.group('date')} does not match Index Metadata Original date {record.date}"
        )

    return problems


def validate_readme_route() -> list[str]:
    problems: list[str] = []
    text = README_PATH.read_text(encoding="utf-8")
    for snippet in (
        "Decision records explain why; current source surfaces define what.",
        "ABYSS-STACK-D-####",
        "indexes/",
        "TEMPLATE.md",
        "validate_decision_records.py",
    ):
        if snippet not in text:
            problems.append(f"{repo_rel(README_PATH)}: missing decisions route snippet {snippet!r}")
    return problems


def validate_all() -> list[str]:
    problems: list[str] = []
    if not DECISIONS_DIR.is_dir():
        return [f"{repo_rel(DECISIONS_DIR)}: missing decisions directory"]
    if not (DECISIONS_DIR / "AGENTS.md").is_file():
        problems.append(f"{repo_rel(DECISIONS_DIR / 'AGENTS.md')}: missing decisions route card")
    if not (DECISIONS_DIR / "TEMPLATE.md").is_file():
        problems.append(f"{repo_rel(DECISIONS_DIR / 'TEMPLATE.md')}: missing decisions template")
    if not README_PATH.is_file():
        problems.append(f"{repo_rel(README_PATH)}: missing decisions index")
        return problems

    for path in sorted(DECISIONS_DIR.glob("*.md")):
        if path.name in EXEMPT_FILES:
            continue
        if not decision_indexes.FULL_ID_FILENAME_RE.fullmatch(path.name):
            problems.append(f"{repo_rel(path)}: unexpected Markdown file in decisions district")

    for path in decision_record_paths():
        problems.extend(validate_record(path))
    problems.extend(validate_readme_route())
    problems.extend(
        f"{location}: {message}"
        for location, message in decision_indexes.validate_decision_index_surfaces(REPO_ROOT)
    )
    return problems


def main() -> int:
    problems = validate_all()
    if problems:
        print("Decision record validation failed:")
        for problem in problems:
            print(f" - {problem}")
        return 1
    print("[ok] decision records validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
