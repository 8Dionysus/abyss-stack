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


def test_sync_managed_items_include_runtime_mcp_root_schemas_and_stats() -> None:
    assert "mcp" in sync_parity.SYNC_MANAGED_ITEMS
    assert "schemas" in sync_parity.SYNC_MANAGED_ITEMS
    assert "stats" in sync_parity.SYNC_MANAGED_ITEMS


def test_runtime_configs_mirror_requires_decisions_mcp_and_graph_schema(tmp_path: Path) -> None:
    write_text(
        tmp_path / "README.md",
        "# Runtime mirror\n\nSource checkout shape\n/srv/AbyssOS/abyss-stack/Configs\n",
    )
    write_text(tmp_path / "scripts" / "AGENTS.md", "source checkout only\n")
    errors: list[str] = []

    sync_parity.validate_runtime_configs_mirror(errors, root=tmp_path)

    assert (
        "runtime Configs mirror is missing required path: "
        "mcp/services/aoa-decisions-mcp/scripts/aoa_decisions_mcp_server.py"
    ) in errors
    assert (
        "runtime Configs mirror is missing required path: "
        "schemas/workspace_decision_graph.schema.json"
    ) in errors
    assert (
        "runtime Configs mirror is missing required path: stats/port.manifest.json"
    ) in errors
