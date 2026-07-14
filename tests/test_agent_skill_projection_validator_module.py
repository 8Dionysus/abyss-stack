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
    write_text(skill_root / "AGENTS.md", "# Skill surface\n")
    write_text(
        skill_root / "abyss-self-diagnostic-spine" / "SKILL.md",
        """---
name: abyss-self-diagnostic-spine
description: Diagnose a concrete abyss runtime target through the repo-local read-only overlay.
metadata:
  aoa_canonical_skill_repo: 8Dionysus/aoa-skills
  aoa_canonical_skill_path: skills/project/abyss/abyss-self-diagnostic-spine/SKILL.md
---

# Overlay
""",
    )
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

    errors = run_skill_projection_validator(tmp_path)

    assert errors == []


def test_local_overlay_must_remain_directory_with_skill_md(tmp_path: Path) -> None:
    skill_root = tmp_path / agent_skill_projection.SKILL_ROOT
    skill_root.mkdir(parents=True)
    write_text(skill_root / "AGENTS.md", "# Skill surface\n")
    (skill_root / "abyss-self-diagnostic-spine").mkdir()

    errors = run_skill_projection_validator(tmp_path)

    assert errors == [
        ".agents/skills/abyss-self-diagnostic-spine must stay as a local overlay directory with SKILL.md"
    ]


def test_local_overlay_requires_codex_skill_metadata(tmp_path: Path) -> None:
    skill_root = write_minimal_skill_projection(tmp_path)
    write_text(
        skill_root / "abyss-self-diagnostic-spine" / "SKILL.md",
        """---
name: abyss-self-diagnostic-spine
metadata:
  aoa_canonical_skill_repo: 8Dionysus/aoa-skills
  aoa_canonical_skill_path: skills/project/abyss/abyss-self-diagnostic-spine/SKILL.md
---

# Overlay
""",
    )

    errors = run_skill_projection_validator(tmp_path)

    assert errors == [
        ".agents/skills/abyss-self-diagnostic-spine/SKILL.md must declare a non-empty description"
    ]


def test_local_overlay_requires_current_canonical_skill_path(tmp_path: Path) -> None:
    skill_root = write_minimal_skill_projection(tmp_path)
    write_text(
        skill_root / "abyss-self-diagnostic-spine" / "SKILL.md",
        """---
name: abyss-self-diagnostic-spine
description: Diagnose a concrete abyss runtime target through the repo-local read-only overlay.
metadata:
  aoa_canonical_skill_repo: 8Dionysus/aoa-skills
  aoa_canonical_skill_path: skills/abyss-self-diagnostic-spine/SKILL.md
---

# Overlay
""",
    )

    errors = run_skill_projection_validator(tmp_path)

    assert errors == [
        ".agents/skills/abyss-self-diagnostic-spine/SKILL.md must route metadata.aoa_canonical_skill_path to "
        "skills/project/abyss/abyss-self-diagnostic-spine/SKILL.md"
    ]


def test_local_overlay_rejects_legacy_top_level_metadata(tmp_path: Path) -> None:
    skill_root = write_minimal_skill_projection(tmp_path)
    skill_md = skill_root / "abyss-self-diagnostic-spine" / "SKILL.md"
    write_text(
        skill_md,
        skill_md.read_text(encoding="utf-8").replace(
            "description: Diagnose a concrete abyss runtime target through the repo-local read-only overlay.\n",
            "description: Diagnose a concrete abyss runtime target through the repo-local read-only overlay.\nscope: project\n",
        ),
    )

    errors = run_skill_projection_validator(tmp_path)

    assert errors == [
        ".agents/skills/abyss-self-diagnostic-spine/SKILL.md has unsupported top-level frontmatter keys: scope"
    ]


def test_overlay_skill_surface_accepts_expected_target_file(tmp_path: Path) -> None:
    target_path = agent_skill_projection.ABYSS_SAFE_INFRA_SKILL_PATH
    expected_target = agent_skill_projection.OVERLAY_SKILL_INSTALL_TARGETS[target_path]
    write_text(tmp_path / target_path, expected_target + "\n")
    errors: list[str] = []

    agent_skill_projection.validate_overlay_skill_surface(
        errors=errors,
        root=tmp_path,
        skill_path=target_path,
        description="repo-local abyss overlay skill surface",
        expected_target=expected_target,
    )

    assert errors == []


def test_overlay_skill_surface_requires_skill_md_for_directory(tmp_path: Path) -> None:
    skill_path = agent_skill_projection.DIAGNOSTIC_SPINE_SKILL_PATH
    (tmp_path / skill_path).mkdir(parents=True)
    errors: list[str] = []

    agent_skill_projection.validate_overlay_skill_surface(
        errors=errors,
        root=tmp_path,
        skill_path=skill_path,
        description="local overlay surface",
    )

    assert errors == [".agents/skills/abyss-self-diagnostic-spine must contain SKILL.md"]
