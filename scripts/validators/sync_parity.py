from __future__ import annotations

from collections.abc import Callable, Sequence, Set
from pathlib import Path

TextReader = Callable[[Path], str | None]
SyncFileIterator = Callable[[], list[Path]]

SYNC_MANAGED_ITEMS = (
    "compose",
    "config-templates",
    "docs",
    "mechanics",
    "quests",
    "scripts",
    "systemd",
    "env",
    "README.md",
    "QUESTBOOK.md",
    "CHARTER.md",
    "BOUNDARIES.md",
    "DESIGN.md",
    "DESIGN.AGENTS.md",
    "ROADMAP.md",
    "AGENTS.md",
)
PARITY_IGNORED_PARTS = {".git", "__pycache__"}
PARITY_IGNORED_SUFFIXES = {".pyc"}


def iter_sync_managed_files(
    *,
    root: Path,
    sync_managed_items: Sequence[str],
    ignored_parts: Set[str],
    ignored_suffixes: Set[str],
) -> list[Path]:
    files: list[Path] = []

    for item in sync_managed_items:
        source_path = root / item
        if source_path.is_file():
            files.append(Path(item))
            continue
        if not source_path.is_dir():
            continue

        for child in source_path.rglob("*"):
            if not child.is_file():
                continue
            rel = child.relative_to(root)
            if any(part in ignored_parts for part in rel.parts):
                continue
            if child.suffix.lower() in ignored_suffixes:
                continue
            files.append(rel)

    return sorted(files)


def validate_sync_managed_items(
    errors: list[str],
    *,
    root: Path,
    sync_managed_items: Sequence[str],
    read_text_func: TextReader,
) -> None:
    sync_script = read_text_func(
        root / "mechanics" / "config-projection" / "parts" / "sync" / "aoa_sync_configs.sh"
    ) or ""
    sync_readme = read_text_func(
        root / "mechanics" / "config-projection" / "parts" / "sync" / "README.md"
    ) or ""

    for item in sync_managed_items:
        if item not in sync_script:
            errors.append(
                "mechanics/config-projection/parts/sync/aoa_sync_configs.sh "
                f"must sync `{item}`"
            )

    for item in ("AGENTS.md", "DESIGN.md", "DESIGN.AGENTS.md"):
        if item not in sync_readme:
            errors.append(
                "mechanics/config-projection/parts/sync/README.md "
                f"must mention `{item}`"
            )


def validate_runtime_configs_mirror(errors: list[str], *, root: Path) -> None:
    required_runtime_paths = [
        root / "README.md",
        root / "compose" / "modules",
        root / "compose" / "profiles",
        root / "config-templates" / "Services" / "route-api" / "app" / "main.py",
        root / "scripts" / "aoa-check-layout",
        root / "docs" / "install" / "DEPLOYMENT.md",
    ]
    for path in required_runtime_paths:
        if not path.exists():
            errors.append(f"runtime Configs mirror is missing required path: {path.relative_to(root)}")

    readme = (root / "README.md").read_text(encoding="utf-8")
    if "Source checkout shape" not in readme:
        errors.append("runtime Configs mirror README must clarify that the repository tree is the source checkout shape")
    if "/srv/AbyssOS/abyss-stack/Configs" not in readme:
        errors.append("runtime Configs mirror README must mention /srv/AbyssOS/abyss-stack/Configs")

    agents_doc = (root / "scripts" / "AGENTS.md").read_text(encoding="utf-8")
    if "source checkout only" not in agents_doc:
        errors.append("runtime Configs mirror scripts/AGENTS.md must note that .github workflow refs are source-checkout-only")


def validate_deployed_parity(
    errors: list[str],
    *,
    root: Path,
    deployed_root: Path,
    sync_file_iter_func: SyncFileIterator,
) -> None:
    if not deployed_root.exists():
        errors.append(f"deployed Configs root does not exist: {deployed_root}")
        return

    for rel_path in sync_file_iter_func():
        source_path = root / rel_path
        deployed_path = deployed_root / rel_path
        if not deployed_path.exists():
            errors.append(
                f"deployed Configs mirror is missing synced path: {rel_path}"
            )
            continue

        if source_path.read_bytes() != deployed_path.read_bytes():
            errors.append(
                f"source/deployed drift for synced path: {rel_path}"
            )
