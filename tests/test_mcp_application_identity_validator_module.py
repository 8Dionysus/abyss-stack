from __future__ import annotations

from pathlib import Path

from scripts.validators import mcp_application_identity


def _write_service(
    root: Path,
    *,
    project_version: str = "1.2.3",
    server_version: str = "1.2.3",
    application_body: str = "return APPLICATION_VERSION",
    import_line: str = "",
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
        f'APPLICATION_VERSION = "{server_version}"\n\n'
        "def _application_version() -> str:\n"
        f"    {application_body}\n\n"
        "def _bind_server_info_version(mcp) -> None:\n"
        "    mcp._mcp_server.version = _application_version()\n\n"
        "def build_server():\n"
        "    mcp = object()\n"
        "    _bind_server_info_version(mcp)\n"
        "    return mcp\n",
        encoding="utf-8",
    )


def test_accepts_source_bound_application_identity(tmp_path: Path) -> None:
    _write_service(tmp_path)

    errors: list[str] = []
    mcp_application_identity.validate(errors, root=tmp_path)

    assert errors == []


def test_rejects_stale_embedded_version(tmp_path: Path) -> None:
    _write_service(tmp_path, project_version="2.0.0", server_version="1.0.0")

    errors: list[str] = []
    mcp_application_identity.validate(errors, root=tmp_path)

    assert any("must equal pyproject project.version" in error for error in errors)


def test_rejects_ambient_distribution_metadata(tmp_path: Path) -> None:
    _write_service(
        tmp_path,
        import_line="from importlib.metadata import distribution\n",
        application_body='return distribution("example-mcp").version',
    )

    errors: list[str] = []
    mcp_application_identity.validate(errors, root=tmp_path)

    assert any("ambient importlib.metadata" in error for error in errors)
    assert any("must return APPLICATION_VERSION directly" in error for error in errors)


def test_rejects_server_builder_without_version_binding(tmp_path: Path) -> None:
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
        server_path.read_text(encoding="utf-8").replace(
            "    _bind_server_info_version(mcp)\n",
            "",
        ),
        encoding="utf-8",
    )

    errors: list[str] = []
    mcp_application_identity.validate(errors, root=tmp_path)

    assert any(
        "build_server must call _bind_server_info_version(mcp)" in error
        for error in errors
    )


def test_rejects_version_assignment_to_unproven_receiver(tmp_path: Path) -> None:
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
        server_path.read_text(encoding="utf-8").replace(
            "mcp._mcp_server.version = _application_version()",
            "telemetry.version = _application_version()",
        ),
        encoding="utf-8",
    )

    errors: list[str] = []
    mcp_application_identity.validate(errors, root=tmp_path)

    assert any(
        "_bind_server_info_version must assign server version" in error
        for error in errors
    )
