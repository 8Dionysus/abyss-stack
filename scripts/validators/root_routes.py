from __future__ import annotations

from pathlib import Path
from typing import Callable


ROOT_DESIGN_SURFACES = (
    Path("AGENTS.md"),
    Path("DESIGN.md"),
    Path("DESIGN.AGENTS.md"),
    Path("CHARTER.md"),
    Path("BOUNDARIES.md"),
    Path("docs") / "README.md",
)
START_HERE_ROUTE_CONTRACT_PATH = Path("docs") / "routes" / "START_HERE_ROUTE_CONTRACT.md"
ENTRY_ROUTE_SURFACES = (
    Path("README.md"),
    Path("AGENTS.md"),
    Path("docs") / "README.md",
    Path("docs") / "AGENTS.md",
)
ENTRY_ROUTE_MODES = (
    "first-reading",
    "runtime-design",
    "agent-guidance",
    "source-install",
    "runtime-operation",
    "mechanic-change",
    "machine-fit",
    "diagnostics-repair",
    "direction-change",
    "release-history",
    "decision-rationale",
)


def read_required(root: Path, relative_path: Path, errors: list[str]) -> str:
    path = root / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"missing required file: {relative_path.as_posix()}")
        return ""


def validate_root_design_surfaces(errors: list[str], *, root: Path) -> None:
    agents = read_required(root, Path("AGENTS.md"), errors)
    design = read_required(root, Path("DESIGN.md"), errors)
    design_agents = read_required(root, Path("DESIGN.AGENTS.md"), errors)
    charter = read_required(root, Path("CHARTER.md"), errors)
    boundaries = read_required(root, Path("BOUNDARIES.md"), errors)
    docs_readme = read_required(root, Path("docs") / "README.md", errors)

    for heading in (
        "## Applies to",
        "## Role",
        "## Read before editing",
        "## Boundaries",
        "## Validation",
        "## Closeout",
    ):
        if heading not in agents:
            errors.append(f"AGENTS.md must include `{heading}`")

    for snippet in (
        "DESIGN.md",
        "DESIGN.AGENTS.md",
        "source checkout",
        "deployed runtime root",
        "GitHub Landing Workflow",
        "Post-change Route Review",
    ):
        if snippet not in agents:
            errors.append(f"AGENTS.md must route or describe `{snippet}`")

    for snippet in (
        "runtime body",
        "source checkout",
        "deployed runtime root",
        "Generated companions stay companions",
        "Runtime, not meaning",
    ):
        if snippet not in design:
            errors.append(f"DESIGN.md must describe `{snippet}`")

    for snippet in (
        "Canonical Card Shape",
        "root card",
        "district cards",
        "mechanic package cards",
        "part cards",
        "generated companions",
    ):
        if snippet not in design_agents:
            errors.append(f"DESIGN.AGENTS.md must describe `{snippet}`")

    if "DESIGN.md" not in charter or "DESIGN.AGENTS.md" not in charter:
        errors.append("CHARTER.md must point to root design surfaces")

    for snippet in ("DESIGN.md", "DESIGN.AGENTS.md", "AGENTS.md"):
        if snippet not in boundaries:
            errors.append(f"BOUNDARIES.md must point to `{snippet}`")
        if snippet not in docs_readme:
            errors.append(f"docs/README.md must point to `{snippet}`")


def validate_entry_route_contract(
    errors: list[str],
    *,
    root: Path,
    read_text_func: Callable[[Path], str | None],
) -> None:
    route_contract = read_text_func(root / START_HERE_ROUTE_CONTRACT_PATH) or ""
    readme = read_text_func(root / "README.md") or ""
    agents = read_text_func(root / "AGENTS.md") or ""
    docs_readme = read_text_func(root / "docs" / "README.md") or ""
    docs_agents = read_text_func(root / "docs" / "AGENTS.md") or ""

    for surface_name, text in (
        ("README.md", readme),
        ("AGENTS.md", agents),
        ("docs/README.md", docs_readme),
        ("docs/AGENTS.md", docs_agents),
    ):
        if "START_HERE_ROUTE_CONTRACT.md" not in text:
            errors.append(f"{surface_name} must point to docs/routes/START_HERE_ROUTE_CONTRACT.md")

    for mode in ENTRY_ROUTE_MODES:
        if mode not in route_contract:
            errors.append(f"docs/routes/START_HERE_ROUTE_CONTRACT.md must define route mode `{mode}`")
        if mode not in readme:
            errors.append(f"README.md must expose route mode `{mode}`")

    for snippet in (
        "scripts/release_check.py",
        "Root entry surfaces should point here",
        "Exact current command lanes live in",
        "Decision records explain why. Current source surfaces define what.",
        "Diagnostic and repair surfaces are evidence and handoff routes",
    ):
        if snippet not in route_contract:
            errors.append(f"docs/routes/START_HERE_ROUTE_CONTRACT.md must mention `{snippet}`")
