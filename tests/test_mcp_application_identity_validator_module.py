from __future__ import annotations

from pathlib import Path

from scripts.validators import mcp_application_identity


def _write_service(
    root: Path,
    *,
    project_version: str = "1.2.3",
    version_expression: str = "SERVICE_CONFIG.package_version",
    import_line: str = "from ._runtime_config import SERVICE_CONFIG\n",
) -> None:
    package_root = root / "mcp" / "services" / "example-mcp"
    server_path = package_root / "src" / "example_mcp" / "server.py"
    server_path.parent.mkdir(parents=True)
    (package_root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "example-mcp"\n'
        f'version = "{project_version}"\n',
        encoding="utf-8",
    )
    server_path.write_text(
        f"{import_line}"
        "def build_server():\n"
        f"    return ModernMCPServer('example', version={version_expression})\n",
        encoding="utf-8",
    )


def test_accepts_source_bound_application_identity(tmp_path: Path) -> None:
    _write_service(tmp_path)

    errors: list[str] = []
    mcp_application_identity.validate(errors, root=tmp_path)

    assert errors == []


def test_rejects_stale_embedded_version(tmp_path: Path) -> None:
    _write_service(tmp_path, project_version="")

    errors: list[str] = []
    mcp_application_identity.validate(errors, root=tmp_path)

    assert any("cannot validate its package version" in error for error in errors)


def test_rejects_ambient_distribution_metadata(tmp_path: Path) -> None:
    _write_service(
        tmp_path,
        import_line="from importlib.metadata import distribution\n",
    )

    errors: list[str] = []
    mcp_application_identity.validate(errors, root=tmp_path)

    assert any("ambient importlib.metadata" in error for error in errors)


def test_rejects_non_catalog_version_binding(tmp_path: Path) -> None:
    _write_service(tmp_path, version_expression="\"1.2.3\"")

    errors: list[str] = []
    mcp_application_identity.validate(errors, root=tmp_path)

    assert any("SERVICE_CONFIG.package_version" in error for error in errors)


def test_rejects_builder_without_native_server(tmp_path: Path) -> None:
    _write_service(tmp_path)
    server_path = (
        tmp_path
        / "mcp"
        / "services"
        / "example-mcp"
        / "src"
        / "example_mcp"
        / "server.py"
    )
    server_path.write_text(
        "from ._runtime_config import SERVICE_CONFIG\n"
        "def build_server():\n"
        "    return object()\n",
        encoding="utf-8",
    )

    errors: list[str] = []
    mcp_application_identity.validate(errors, root=tmp_path)

    assert any("construct native ModernMCPServer" in error for error in errors)
