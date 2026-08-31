from __future__ import annotations

from pathlib import Path
from typing import Callable


DECISION_SURFACE_PATHS = (
    Path("docs") / "decisions" / "README.md",
    Path("docs") / "decisions" / "AGENTS.md",
    Path("docs") / "decisions" / "TEMPLATE.md",
    Path("docs") / "AGENTS.md",
    Path("scripts") / "README.md",
    Path("tests") / "README.md",
)


def validate_decision_record_surface(
    errors: list[str],
    *,
    root: Path,
    read_text_func: Callable[[Path], str | None],
) -> None:
    decisions_readme = read_text_func(root / "docs" / "decisions" / "README.md") or ""
    decisions_agents = read_text_func(root / "docs" / "decisions" / "AGENTS.md") or ""
    decisions_template = read_text_func(root / "docs" / "decisions" / "TEMPLATE.md") or ""
    docs_agents = read_text_func(root / "docs" / "AGENTS.md") or ""
    scripts_readme = read_text_func(root / "scripts" / "README.md") or ""
    tests_readme = read_text_func(root / "tests" / "README.md") or ""
    validation = read_text_func(root / "VALIDATION.md") or ""

    for snippet in (
        "Decision records explain why; current source surfaces define what.",
        "ABYSS-STACK-D-####",
        "indexes/",
        "generated/decision_graph.json",
        "TEMPLATE.md",
        "AGENTS.md",
        "validate_decision_records.py",
    ):
        if snippet not in decisions_readme:
            errors.append(f"docs/decisions/README.md must route `{snippet}`")

    for snippet in (
        "Decision Review Gate",
        "ABYSS-STACK-D-####",
        "docs/decisions/indexes/",
        "docs/decisions/generated/",
        "python scripts/generate_decision_indexes.py --check",
        "Decision records must follow [TEMPLATE](TEMPLATE.md)",
        "python scripts/validate_decision_records.py",
    ):
        haystack = f"{decisions_agents}\n{validation}" if snippet.startswith(("python ", "pytest ")) else decisions_agents
        if snippet not in haystack:
            errors.append(f"docs/decisions/AGENTS.md must define `{snippet}`")

    for snippet in (
        "- Decision ID: ABYSS-STACK-D-NNNN",
        "- Status: proposed",
        "- Date: YYYY-MM-DD",
        "## Index Metadata",
        "## Options considered",
        "## Source surfaces",
        "## Follow-up route",
    ):
        if snippet not in decisions_template:
            errors.append(f"docs/decisions/TEMPLATE.md must include `{snippet}`")

    if "python scripts/validate_decision_records.py" not in f"{docs_agents}\n{validation}":
        errors.append("docs/AGENTS.md must include the decision-record validator")
    if "python scripts/generate_decision_indexes.py --check" not in f"{docs_agents}\n{validation}":
        errors.append("docs/AGENTS.md must include the decision-index generator check")
    if "validate_decision_records.py" not in scripts_readme:
        errors.append("scripts/README.md must route validate_decision_records.py")
    if "generate_decision_indexes.py" not in scripts_readme:
        errors.append("scripts/README.md must route generate_decision_indexes.py")
    if "test_decision_records.py" not in tests_readme:
        errors.append("tests/README.md must route test_decision_records.py")
