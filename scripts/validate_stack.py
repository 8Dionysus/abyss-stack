from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "compose" / "profiles"
MODULE_DIR = ROOT / "compose" / "modules"
LEGACY_PATH = "/srv/abyss"
LEGACY_ALLOWED = {
    ROOT / "docs" / "MIGRATION_FROM_OLD.md",
}


def iter_text_files() -> list[Path]:
    paths: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        if path.suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        paths.append(path)
    return paths


def validate_profiles(errors: list[str]) -> None:
    for profile in sorted(PROFILE_DIR.glob("*.txt")):
        lines = []
        for raw in profile.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if line:
                lines.append(line)
        if not lines:
            errors.append(f"profile has no modules: {profile.relative_to(ROOT)}")
        for module_name in lines:
            module_path = MODULE_DIR / module_name
            if not module_path.exists():
                errors.append(
                    f"profile {profile.name} references missing module {module_name}"
                )


def validate_paths(errors: list[str]) -> None:
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8")
        if LEGACY_PATH in text and path not in LEGACY_ALLOWED:
            errors.append(
                f"legacy path '{LEGACY_PATH}' found in {path.relative_to(ROOT)}"
            )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "Fedora-first" not in readme:
        errors.append("README.md must state Fedora-first posture")

    paths_doc = (ROOT / "docs" / "PATHS.md").read_text(encoding="utf-8")
    if "/srv/abyss-stack" not in paths_doc:
        errors.append("docs/PATHS.md must mention /srv/abyss-stack")


def main() -> int:
    errors: list[str] = []
    validate_profiles(errors)
    validate_paths(errors)

    if errors:
        print("validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
