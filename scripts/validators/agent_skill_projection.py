from __future__ import annotations

from pathlib import Path

SKILL_ROOT = Path(".agents") / "skills"
AOA_SKILL_INSTALL_ROOT = "/srv/AbyssOS/aoa-skills/.agents/skills"


def matches_checkout_safe_overlay_install(path: Path, expected_target: str) -> bool:
    if path.is_symlink():
        try:
            return path.readlink().as_posix() == expected_target
        except OSError:
            return False
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8").strip() == expected_target
        except (OSError, UnicodeDecodeError):
            return False
    return False


def validate_agent_skill_projection_routes(errors: list[str], *, root: Path) -> None:
    skills_root = root / SKILL_ROOT
    if not skills_root.is_dir():
        errors.append(".agents/skills must exist as the repo-local skill projection surface")
        return

    for path in sorted(skills_root.iterdir()):
        if path.name == "AGENTS.md":
            continue
        rel_path = path.relative_to(root).as_posix()
        expected_target = f"{AOA_SKILL_INSTALL_ROOT}/{path.name}"
        if matches_checkout_safe_overlay_install(path, expected_target):
            continue
        if not path.is_symlink():
            errors.append(f"{rel_path} must be a symlink into {AOA_SKILL_INSTALL_ROOT}")
            continue
        try:
            actual_target = path.readlink().as_posix()
        except OSError:
            errors.append(f"{rel_path} symlink target cannot be read")
            continue
        if actual_target != expected_target:
            errors.append(
                f"{rel_path} must target {expected_target}, got {actual_target}"
            )
