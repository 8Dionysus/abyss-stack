from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "compose" / "profiles"
MODULE_DIR = ROOT / "compose" / "modules"
LEGACY_PATH = "/srv/abyss"
LEGACY_PATTERN = re.compile(r"/srv/abyss(?!-)")
LEGACY_ALLOWED = {
    ROOT / "docs" / "MIGRATION_FROM_OLD.md",
    ROOT / "scripts" / "validate_stack.py",
}
REQUIRED_SCRIPTS = {
    "aoa-doctor",
    "aoa-install-layout",
    "aoa-sync-configs",
    "aoa-bootstrap-configs",
    "aoa-check-layout",
    "aoa-install-systemd",
    "aoa-first-run",
    "aoa-profile-modules",
    "aoa-profile-endpoints",
    "aoa-up",
    "aoa-down",
    "aoa-status",
    "aoa-logs",
    "aoa-smoke",
    "aoa-wait",
}
REQUIRED_FILES = {
    ROOT / "docs" / "FIRST_RUN.md",
    ROOT / "docs" / "DOCTOR.md",
    ROOT / "docs" / "PROFILE_RECIPES.md",
    ROOT / "docs" / "SECRETS_BOOTSTRAP.md",
    ROOT / "config-templates" / "README.md",
    ROOT / "config-templates" / "Configs" / "monitoring" / "prometheus.yml",
    ROOT / "config-templates" / "Configs" / "tts" / "voices.yaml",
    ROOT / "config-templates" / "Services" / "litellm" / "config.yaml",
}
MODULE_REQUIREMENTS = {
    "20-orchestration.yml": {"10-storage.yml"},
    "40-llm-gateway.yml": {"30-local-inference.yml"},
    "41-agent-api.yml": {"40-llm-gateway.yml", "30-local-inference.yml"},
    "42-agent-api-intel.yml": {"41-agent-api.yml", "31-intel-inference.yml"},
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


def load_profile_modules(profile: Path) -> list[str]:
    modules: list[str] = []
    for raw in profile.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            modules.append(line)
    return modules


def validate_profiles(errors: list[str]) -> None:
    for profile in sorted(PROFILE_DIR.glob("*.txt")):
        modules = load_profile_modules(profile)
        if not modules:
            errors.append(f"profile has no modules: {profile.relative_to(ROOT)}")
            continue

        seen = set(modules)
        for module_name in modules:
            module_path = MODULE_DIR / module_name
            if not module_path.exists():
                errors.append(
                    f"profile {profile.name} references missing module {module_name}"
                )

        for module_name, requirements in MODULE_REQUIREMENTS.items():
            if module_name not in seen:
                continue
            missing = sorted(requirement for requirement in requirements if requirement not in seen)
            if missing:
                errors.append(
                    f"profile {profile.name} includes {module_name} but is missing required modules: {', '.join(missing)}"
                )


def validate_paths(errors: list[str]) -> None:
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8")
        if LEGACY_PATTERN.search(text) and path not in LEGACY_ALLOWED:
            errors.append(
                f"legacy path '{LEGACY_PATH}' found in {path.relative_to(ROOT)}"
            )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "Fedora-first" not in readme:
        errors.append("README.md must state Fedora-first posture")
    if "Windows-usable" not in readme:
        errors.append("README.md must state Windows-usable posture")

    paths_doc = (ROOT / "docs" / "PATHS.md").read_text(encoding="utf-8")
    if "/srv/abyss-stack" not in paths_doc:
        errors.append("docs/PATHS.md must mention /srv/abyss-stack")
    if "WSL2" not in paths_doc:
        errors.append("docs/PATHS.md should mention WSL2 in the Windows-usable model")


def validate_scripts(errors: list[str]) -> None:
    script_names = {path.name for path in (ROOT / "scripts").iterdir() if path.is_file()}
    missing = sorted(REQUIRED_SCRIPTS - script_names)
    for name in missing:
        errors.append(f"missing required script: scripts/{name}")


def validate_required_files(errors: list[str]) -> None:
    for path in sorted(REQUIRED_FILES):
        if not path.exists():
            errors.append(f"missing required file: {path.relative_to(ROOT)}")


def main() -> int:
    errors: list[str] = []
    validate_profiles(errors)
    validate_paths(errors)
    validate_scripts(errors)
    validate_required_files(errors)

    if errors:
        print("validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
