from __future__ import annotations

from pathlib import Path

from scripts.validators import agent_skill_projection


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_minimal_skill_projection(repo_root: Path) -> Path:
    skill_root = repo_root / agent_skill_projection.SKILL_ROOT
    skill_root.mkdir(parents=True)
    write_text(skill_root / "AGENTS.md", "# Shared skill projection\n")
    return skill_root


def run_skill_projection_validator(repo_root: Path) -> list[str]:
    errors: list[str] = []
    agent_skill_projection.validate_agent_skill_projection_routes(errors, root=repo_root)
    return errors


def test_current_repo_agent_skill_projection_module_passes() -> None:
    assert run_skill_projection_validator(REPO_ROOT) == []


def test_missing_skill_projection_root_fails(tmp_path: Path) -> None:
    errors = run_skill_projection_validator(tmp_path)

    assert errors == [".agents/skills must exist as the repo-local skill projection surface"]


def test_skill_projection_symlink_target_must_use_abyssos_workspace(tmp_path: Path) -> None:
    skill_root = write_minimal_skill_projection(tmp_path)
    (skill_root / "aoa-change-protocol").symlink_to(
        f"{agent_skill_projection.AOA_SKILL_INSTALL_ROOT}/aoa-change-protocol"
    )
    stale_target = "/srv/" + "aoa-skills/.agents/skills/aoa-source-of-truth-check"
    (skill_root / "aoa-source-of-truth-check").symlink_to(stale_target)

    errors = run_skill_projection_validator(tmp_path)

    assert errors == [
        ".agents/skills/aoa-source-of-truth-check must target "
        f"{agent_skill_projection.AOA_SKILL_INSTALL_ROOT}/aoa-source-of-truth-check, "
        f"got {stale_target}"
    ]


def test_skill_projection_accepts_checkout_safe_target_file(tmp_path: Path) -> None:
    skill_root = write_minimal_skill_projection(tmp_path)
    expected_target = f"{agent_skill_projection.AOA_SKILL_INSTALL_ROOT}/aoa-change-protocol"
    write_text(skill_root / "aoa-change-protocol", expected_target + "\n")

    assert run_skill_projection_validator(tmp_path) == []


def test_skill_projection_rejects_local_directory(tmp_path: Path) -> None:
    skill_root = write_minimal_skill_projection(tmp_path)
    (skill_root / "local-only-skill").mkdir()

    errors = run_skill_projection_validator(tmp_path)

    assert errors == [
        ".agents/skills/local-only-skill must be a symlink into "
        "/srv/AbyssOS/aoa-skills/.agents/skills"
    ]
