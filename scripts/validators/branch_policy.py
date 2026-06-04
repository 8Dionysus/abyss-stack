from __future__ import annotations

from pathlib import Path


CONTRIBUTING_PATH = Path("CONTRIBUTING.md")
BRANCH_POLICY_PATH = Path("docs") / "governance" / "BRANCH_POLICY.md"
REQUIRED_BRANCH_POLICY_SNIPPETS = (
    "`main` is the only long-lived branch",
    "Delete the topic branch locally and on `origin`.",
    "If a branch was effectively landed by squash, cherry-pick, or a rewritten equivalent, do not merge it again.",
    "/srv/AbyssOS/abyss-stack",
    "~/src/abyss-stack",
    "AOA_SOURCE_ROOT",
)


def read_text(root: Path, relative_path: Path) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def validate_branch_policy(errors: list[str], *, root: Path) -> None:
    contributing_doc = read_text(root, CONTRIBUTING_PATH)
    if "docs/governance/BRANCH_POLICY.md" not in contributing_doc:
        errors.append("CONTRIBUTING.md must point to docs/governance/BRANCH_POLICY.md")

    policy_doc = read_text(root, BRANCH_POLICY_PATH)
    for snippet in REQUIRED_BRANCH_POLICY_SNIPPETS:
        if snippet not in policy_doc:
            errors.append(f"docs/governance/BRANCH_POLICY.md must mention: {snippet}")
