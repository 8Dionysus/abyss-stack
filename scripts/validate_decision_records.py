#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DECISIONS_DIR = REPO_ROOT / "docs" / "decisions"
README_PATH = DECISIONS_DIR / "README.md"

RECORD_NAME_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
DATE_RE = re.compile(r"^Date:\s*(?P<date>\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
STATUS_RE = re.compile(r"^Status:\s*(?P<status>[a-z][a-z0-9_-]*)\s*$", re.MULTILINE)
README_LINK_RE = re.compile(r"\((?P<path>\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md)\)")

EXEMPT_FILES = {"AGENTS.md", "README.md", "TEMPLATE.md"}
STATUS_VALUES = {"accepted", "proposed", "superseded", "amended"}
REQUIRED_SECTIONS = (
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
    match = RECORD_NAME_RE.fullmatch(path.name)
    if not match:
        return [f"{rel}: decision record filename must be YYYY-MM-DD-kebab.md"]

    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        problems.append(f"{rel}: missing final newline")
    if not text.startswith("# "):
        problems.append(f"{rel}: must start with an H1 title")

    status_match = STATUS_RE.search(text)
    if not status_match:
        problems.append(f"{rel}: missing top-level Status: <value>")
    elif status_match.group("status") not in STATUS_VALUES:
        allowed = ", ".join(sorted(STATUS_VALUES))
        problems.append(f"{rel}: unsupported status {status_match.group('status')!r}; allowed: {allowed}")

    date_match = DATE_RE.search(text)
    if not date_match:
        problems.append(f"{rel}: missing top-level Date: YYYY-MM-DD")
    elif date_match.group("date") != match.group("date"):
        problems.append(
            f"{rel}: Date {date_match.group('date')} does not match filename date {match.group('date')}"
        )

    for section in REQUIRED_SECTIONS:
        if section not in text:
            problems.append(f"{rel}: missing section {section}")

    return problems


def validate_readme_index(records: list[Path]) -> list[str]:
    problems: list[str] = []
    text = README_PATH.read_text(encoding="utf-8")
    linked = README_LINK_RE.findall(text)
    linked_set = set(linked)
    expected = {path.name for path in records}

    for name in sorted(expected - linked_set):
        problems.append(f"{repo_rel(README_PATH)}: missing decision record link {name}")
    for name in sorted(linked_set - expected):
        problems.append(f"{repo_rel(README_PATH)}: links unknown decision record {name}")
    for name in sorted(linked_set):
        if linked.count(name) != 1:
            problems.append(f"{repo_rel(README_PATH)}: decision record link {name} appears {linked.count(name)} times")

    if "Decision records explain why; current source surfaces define what." not in text:
        problems.append(f"{repo_rel(README_PATH)}: missing district law sentence")
    if "TEMPLATE.md" not in text:
        problems.append(f"{repo_rel(README_PATH)}: missing template route")
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
        if not RECORD_NAME_RE.fullmatch(path.name):
            problems.append(f"{repo_rel(path)}: unexpected Markdown file in decisions district")

    records = decision_record_paths()
    for path in records:
        problems.extend(validate_record(path))
    problems.extend(validate_readme_index(records))
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
