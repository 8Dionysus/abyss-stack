from __future__ import annotations

from pathlib import Path

from scripts.validators import branch_policy


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_current_surface(relative_path: Path, *, into: Path) -> None:
    write_text(into / relative_path, (REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def write_valid_surface(repo_root: Path) -> None:
    for relative_path in (
        branch_policy.CONTRIBUTING_PATH,
        branch_policy.BRANCH_POLICY_PATH,
    ):
        copy_current_surface(relative_path, into=repo_root)


def run_validator(repo_root: Path) -> list[str]:
    errors: list[str] = []
    branch_policy.validate_branch_policy(errors, root=repo_root)
    return errors


def test_current_repo_branch_policy_module_passes() -> None:
    assert run_validator(REPO_ROOT) == []


def test_contributing_must_route_branch_policy(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    contributing_path = tmp_path / branch_policy.CONTRIBUTING_PATH
    write_text(
        contributing_path,
        contributing_path.read_text(encoding="utf-8").replace(
            "docs/governance/BRANCH_POLICY.md",
            "docs/governance/BRANCHES.md",
        ),
    )

    errors = run_validator(tmp_path)

    assert "CONTRIBUTING.md must point to docs/governance/BRANCH_POLICY.md" in errors


def test_branch_policy_must_keep_main_as_only_long_lived_branch(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    policy_path = tmp_path / branch_policy.BRANCH_POLICY_PATH
    write_text(
        policy_path,
        policy_path.read_text(encoding="utf-8").replace(
            "`main` is the only long-lived branch",
            "`main` is one long-lived branch",
        ),
    )

    errors = run_validator(tmp_path)

    assert "docs/governance/BRANCH_POLICY.md must mention: `main` is the only long-lived branch" in errors
