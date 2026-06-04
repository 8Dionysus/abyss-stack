from __future__ import annotations

from pathlib import Path

from scripts.validators import mechanics_topology


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def package_card_text() -> str:
    return "\n".join(mechanics_topology.MECHANIC_CARD_HEADINGS) + "\n"


def write_valid_mechanics_surface(repo_root: Path) -> None:
    mechanics_root = repo_root / "mechanics"
    write_text(mechanics_root / "AGENTS.md", "mechanics agents\n")
    write_text(
        mechanics_root / "README.md",
        "\n".join(
            f"- [{package}]({package}/README.md)"
            for package in mechanics_topology.MECHANIC_PACKAGES
        ),
    )
    write_text(mechanics_root / "ARTIFACT_TOPOLOGY.md", "mechanics artifact topology\n")
    write_text(repo_root / "docs" / "runtime" / "MECHANICS.md", "mechanics route\n")

    for package in mechanics_topology.MECHANIC_PACKAGES:
        package_root = mechanics_root / package
        for required_file in mechanics_topology.MECHANIC_PACKAGE_REQUIRED_FILES:
            write_text(package_root / required_file, f"{package} {required_file}\n")
        write_text(package_root / "README.md", package_card_text())
        write_text(package_root / "PARTS.md", f"{package} parts\n")

        parts = mechanics_topology.MECHANIC_PACKAGE_PARTS.get(package, ())
        write_text(
            package_root / "parts" / "README.md",
            "\n".join(f"- [{part}]({part}/README.md)" for part in parts),
        )
        for part in parts:
            part_root = package_root / "parts" / part
            write_text(part_root / "README.md", f"{package}/{part}\n")
            for required_file in mechanics_topology.MECHANIC_PART_REQUIRED_FILES.get((package, part), ()):
                write_text(part_root / required_file, f"{package}/{part}/{required_file}\n")

        if package in mechanics_topology.ARCHIVE_MECHANIC_PACKAGES:
            required_files = (
                *mechanics_topology.ARCHIVE_MECHANIC_REQUIRED_FILES,
                *mechanics_topology.ARCHIVE_MECHANIC_EXTRA_REQUIRED_FILES.get(package, ()),
            )
            for required_file in required_files:
                write_text(package_root / required_file, f"{package} archive {required_file}\n")
            for required_dir in mechanics_topology.ARCHIVE_MECHANIC_ARTIFACT_DIRS.get(package, ()):
                (package_root / required_dir).mkdir(parents=True, exist_ok=True)


def run_validator(repo_root: Path) -> list[str]:
    errors: list[str] = []
    mechanics_topology.validate_mechanics_topology(
        errors,
        root=repo_root,
        read_text_func=read_text_or_none,
    )
    return errors


def test_current_repo_mechanics_topology_module_passes() -> None:
    assert run_validator(REPO_ROOT) == []


def test_minimal_valid_mechanics_surface_passes(tmp_path: Path) -> None:
    write_valid_mechanics_surface(tmp_path)

    assert run_validator(tmp_path) == []


def test_mechanics_atlas_must_route_to_each_package(tmp_path: Path) -> None:
    write_valid_mechanics_surface(tmp_path)
    atlas_path = tmp_path / "mechanics" / "README.md"
    write_text(
        atlas_path,
        atlas_path.read_text(encoding="utf-8").replace(
            "- [machine-fit](machine-fit/README.md)",
            "- machine fit",
        ),
    )

    errors = run_validator(tmp_path)

    assert "mechanics atlas must route to machine-fit/README.md" in errors


def test_mechanic_package_card_must_keep_must_not_claim_heading(tmp_path: Path) -> None:
    write_valid_mechanics_surface(tmp_path)
    readme_path = tmp_path / "mechanics" / "runtime-lifecycle" / "README.md"
    write_text(
        readme_path,
        readme_path.read_text(encoding="utf-8").replace(
            "### Must not claim",
            "### Scope limits",
        ),
    )

    errors = run_validator(tmp_path)

    assert "mechanics package runtime-lifecycle README.md must include `### Must not claim`" in errors


def test_active_part_names_must_not_look_archived(tmp_path: Path) -> None:
    write_valid_mechanics_surface(tmp_path)
    legacy_part = tmp_path / "mechanics" / "runtime-lifecycle" / "parts" / "legacy-shadow"
    legacy_part.mkdir(parents=True)

    errors = run_validator(tmp_path)

    assert "mechanics package runtime-lifecycle has archived/noisy active part name: parts/legacy-shadow" in errors


def test_marker_only_archive_artifacts_stay_empty_except_readme(tmp_path: Path) -> None:
    write_valid_mechanics_surface(tmp_path)
    write_text(
        tmp_path / "mechanics" / "agon-runtime" / "legacy" / "artifacts" / "leak.txt",
        "not marker-only\n",
    )

    errors = run_validator(tmp_path)

    assert any(
        "mechanics archive package agon-runtime legacy/artifacts must stay marker-only" in error
        for error in errors
    )
