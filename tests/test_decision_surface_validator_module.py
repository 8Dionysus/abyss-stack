from __future__ import annotations

from pathlib import Path

from scripts.validators import decision_surface


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_current_surface(relative_path: Path, *, into: Path) -> None:
    write_text(into / relative_path, (REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def write_valid_surface(repo_root: Path) -> None:
    for relative_path in decision_surface.DECISION_SURFACE_PATHS:
        copy_current_surface(relative_path, into=repo_root)


def read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def run_validator(repo_root: Path) -> list[str]:
    errors: list[str] = []
    decision_surface.validate_decision_record_surface(
        errors,
        root=repo_root,
        read_text_func=read_text_or_none,
    )
    return errors


def test_current_repo_decision_surface_module_passes() -> None:
    assert run_validator(REPO_ROOT) == []


def test_decisions_readme_must_route_generated_indexes(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    readme_path = tmp_path / "docs" / "decisions" / "README.md"
    write_text(
        readme_path,
        readme_path.read_text(encoding="utf-8").replace("indexes/", "lookup/"),
    )

    errors = run_validator(tmp_path)

    assert "docs/decisions/README.md must route `indexes/`" in errors


def test_decisions_agents_must_keep_generator_check_route(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    agents_path = tmp_path / "docs" / "decisions" / "AGENTS.md"
    write_text(
        agents_path,
        agents_path.read_text(encoding="utf-8").replace(
            "python scripts/generate_decision_indexes.py --check",
            "python scripts/generate_decision_indexes.py",
        ),
    )

    errors = run_validator(tmp_path)

    assert "docs/decisions/AGENTS.md must define `python scripts/generate_decision_indexes.py --check`" in errors


def test_tests_readme_must_route_decision_records_test(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    tests_readme_path = tmp_path / "tests" / "README.md"
    write_text(
        tests_readme_path,
        tests_readme_path.read_text(encoding="utf-8").replace(
            "test_decision_records.py",
            "test_decision_shape.py",
        ),
    )

    errors = run_validator(tmp_path)

    assert "tests/README.md must route test_decision_records.py" in errors
