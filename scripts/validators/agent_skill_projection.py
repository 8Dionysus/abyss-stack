from __future__ import annotations

from pathlib import Path

SKILL_ROOT = Path(".agents") / "skills"
DIAGNOSTIC_SPINE_SKILL_PATH = SKILL_ROOT / "abyss-self-diagnostic-spine"
ABYSS_SAFE_INFRA_SKILL_PATH = SKILL_ROOT / "abyss-safe-infra-change"
ABYSS_SANITIZED_SHARE_SKILL_PATH = SKILL_ROOT / "abyss-sanitized-share"
AOA_SKILL_INSTALL_ROOT = "/srv/AbyssOS/aoa-skills/.agents/skills"
LOCAL_SKILL_OVERLAY_NAMES = {"abyss-self-diagnostic-spine"}
LOCAL_SKILL_OVERLAY_CANONICAL_PATHS = {
    "abyss-self-diagnostic-spine": "skills/project/abyss/abyss-self-diagnostic-spine/SKILL.md",
}
CODEX_SKILL_FRONTMATTER_KEYS = {"allowed-tools", "description", "license", "metadata", "name"}
OVERLAY_SKILL_INSTALL_TARGETS = {
    ABYSS_SAFE_INFRA_SKILL_PATH: f"{AOA_SKILL_INSTALL_ROOT}/abyss-safe-infra-change",
    ABYSS_SANITIZED_SHARE_SKILL_PATH: f"{AOA_SKILL_INSTALL_ROOT}/abyss-sanitized-share",
}
DIAGNOSTIC_OVERLAY_SKILL_SURFACES = (
    (
        DIAGNOSTIC_SPINE_SKILL_PATH,
        "local overlay surface",
        OVERLAY_SKILL_INSTALL_TARGETS.get(DIAGNOSTIC_SPINE_SKILL_PATH),
    ),
    (
        ABYSS_SAFE_INFRA_SKILL_PATH,
        "repo-local abyss overlay skill surface",
        OVERLAY_SKILL_INSTALL_TARGETS.get(ABYSS_SAFE_INFRA_SKILL_PATH),
    ),
    (
        ABYSS_SANITIZED_SHARE_SKILL_PATH,
        "repo-local abyss overlay skill surface",
        OVERLAY_SKILL_INSTALL_TARGETS.get(ABYSS_SANITIZED_SHARE_SKILL_PATH),
    ),
)


def _frontmatter_values(skill_md: Path) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    try:
        lines = skill_md.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}, {}
    if not lines or lines[0].strip() != "---":
        return {}, {}
    try:
        closing_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        return {}, {}

    top_level: dict[str, str] = {}
    nested: dict[tuple[str, str], str] = {}
    current_section = ""
    for line in lines[1:closing_index]:
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        normalized_value = value.strip().strip("\"'")
        if line[:1].isspace():
            if current_section:
                nested[(current_section, key)] = normalized_value
            continue
        current_section = key if not normalized_value else ""
        top_level[key] = normalized_value
    return top_level, nested


def validate_local_overlay_skill_metadata(
    errors: list[str],
    *,
    skill_path: Path,
    skill_md: Path,
) -> None:
    frontmatter, nested = _frontmatter_values(skill_md)
    skill_md_path = (skill_path / "SKILL.md").as_posix()
    if frontmatter.get("name") != skill_path.name:
        errors.append(f"{skill_md_path} must declare name: {skill_path.name}")
    if not frontmatter.get("description"):
        errors.append(f"{skill_md_path} must declare a non-empty description")
    unsupported_keys = sorted(set(frontmatter) - CODEX_SKILL_FRONTMATTER_KEYS)
    if unsupported_keys:
        errors.append(
            f"{skill_md_path} has unsupported top-level frontmatter keys: {', '.join(unsupported_keys)}"
        )
    expected_canonical_path = LOCAL_SKILL_OVERLAY_CANONICAL_PATHS.get(skill_path.name)
    if expected_canonical_path and nested.get(("metadata", "aoa_canonical_skill_path")) != expected_canonical_path:
        errors.append(
            f"{skill_md_path} must route metadata.aoa_canonical_skill_path to {expected_canonical_path}"
        )


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


def validate_overlay_skill_surface(
    *,
    errors: list[str],
    root: Path,
    skill_path: Path,
    description: str,
    expected_target: str | None = None,
) -> None:
    local_skill_root = root / skill_path
    local_skill_md = local_skill_root / "SKILL.md"
    if local_skill_root.is_dir():
        if not local_skill_md.is_file():
            errors.append(f"{skill_path.as_posix()} must contain SKILL.md")
        return
    if expected_target and matches_checkout_safe_overlay_install(local_skill_root, expected_target):
        return
    errors.append(f"{skill_path.as_posix()} must be installed as a {description}")


def validate_agent_skill_projection_routes(errors: list[str], *, root: Path) -> None:
    skills_root = root / SKILL_ROOT
    if not skills_root.is_dir():
        errors.append(".agents/skills must exist as the repo-local skill projection surface")
        return

    for path in sorted(skills_root.iterdir()):
        if path.name == "AGENTS.md":
            continue
        rel_path = path.relative_to(root).as_posix()
        if path.name in LOCAL_SKILL_OVERLAY_NAMES:
            if not path.is_dir() or not (path / "SKILL.md").is_file():
                errors.append(f"{rel_path} must stay as a local overlay directory with SKILL.md")
            else:
                validate_local_overlay_skill_metadata(
                    errors,
                    skill_path=path.relative_to(root),
                    skill_md=path / "SKILL.md",
                )
            continue
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
