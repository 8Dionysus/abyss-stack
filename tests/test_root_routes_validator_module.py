from __future__ import annotations

from pathlib import Path

from scripts.validators import root_routes


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_current_surface(relative_path: Path, *, into: Path) -> None:
    write_text(into / relative_path, (REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def write_valid_surface(repo_root: Path) -> None:
    for relative_path in (
        *root_routes.ROOT_DESIGN_SURFACES,
        root_routes.START_HERE_ROUTE_CONTRACT_PATH,
        *root_routes.ENTRY_ROUTE_SURFACES,
    ):
        copy_current_surface(relative_path, into=repo_root)


def read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def run_all_root_route_validators(repo_root: Path) -> list[str]:
    errors: list[str] = []
    root_routes.validate_root_design_surfaces(errors, root=repo_root)
    root_routes.validate_entry_route_contract(
        errors,
        root=repo_root,
        read_text_func=read_text_or_none,
    )
    return errors


def test_current_repo_root_routes_module_passes() -> None:
    assert run_all_root_route_validators(REPO_ROOT) == []


def test_design_must_keep_runtime_not_meaning_boundary(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    design_path = tmp_path / "DESIGN.md"
    write_text(
        design_path,
        design_path.read_text(encoding="utf-8").replace(
            "Runtime, not meaning",
            "Runtime as meaning",
        ),
    )

    errors = run_all_root_route_validators(tmp_path)

    assert "DESIGN.md must describe `Runtime, not meaning`" in errors


def test_readme_must_expose_all_route_modes(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    readme_path = tmp_path / "README.md"
    write_text(
        readme_path,
        readme_path.read_text(encoding="utf-8").replace("machine-fit", "machine fit"),
    )

    errors = run_all_root_route_validators(tmp_path)

    assert "README.md must expose route mode `machine-fit`" in errors


def test_docs_agents_must_route_start_here_contract(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    docs_agents_path = tmp_path / "docs" / "AGENTS.md"
    write_text(
        docs_agents_path,
        docs_agents_path.read_text(encoding="utf-8").replace(
            "START_HERE_ROUTE_CONTRACT.md",
            "START_HERE.md",
        ),
    )

    errors = run_all_root_route_validators(tmp_path)

    assert "docs/AGENTS.md must point to docs/routes/START_HERE_ROUTE_CONTRACT.md" in errors
