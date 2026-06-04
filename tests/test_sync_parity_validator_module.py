from __future__ import annotations

from pathlib import Path

from scripts.validators import sync_parity


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_sync_managed_file_iterator_ignores_cache_parts_and_suffixes(tmp_path: Path) -> None:
    write_text(tmp_path / "docs" / "README.md", "# docs\n")
    write_text(tmp_path / "docs" / "__pycache__" / "cached.txt", "cache\n")
    write_text(tmp_path / "docs" / "compiled.pyc", "cache\n")
    write_text(tmp_path / "README.md", "# root\n")

    files = sync_parity.iter_sync_managed_files(
        root=tmp_path,
        sync_managed_items=("README.md", "docs"),
        ignored_parts={"__pycache__"},
        ignored_suffixes={".pyc"},
    )

    assert files == [Path("README.md"), Path("docs") / "README.md"]


def test_sync_parity_module_reports_deployed_drift(tmp_path: Path) -> None:
    source = tmp_path / "source"
    deployed = tmp_path / "runtime" / "Configs"
    write_text(source / "README.md", "# source\n")
    write_text(deployed / "README.md", "# deployed\n")

    errors: list[str] = []
    sync_parity.validate_deployed_parity(
        errors,
        root=source,
        deployed_root=deployed,
        sync_file_iter_func=lambda: [Path("README.md")],
    )

    assert errors == ["source/deployed drift for synced path: README.md"]
