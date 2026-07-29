from __future__ import annotations

import ast
from pathlib import Path
import tomllib


def _application_version(tree: ast.Module) -> str | None:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "APPLICATION_VERSION"
            for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    return None


def _uses_ambient_distribution_metadata(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "importlib.metadata":
            return True
        if isinstance(node, ast.Import):
            if any(alias.name == "importlib.metadata" for alias in node.names):
                return True
    return False


def _returns_embedded_version(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "_application_version":
            continue
        return (
            len(node.body) == 1
            and isinstance(node.body[0], ast.Return)
            and isinstance(node.body[0].value, ast.Name)
            and node.body[0].value.id == "APPLICATION_VERSION"
        )
    return False


def _binds_embedded_version(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "_bind_server_info_version":
            continue
        server_receiver_names: set[str] = set()
        for descendant in ast.walk(node):
            if not isinstance(descendant, ast.Assign):
                continue
            if not (
                len(descendant.targets) == 1
                and isinstance(descendant.targets[0], ast.Name)
                and isinstance(descendant.value, ast.Call)
                and isinstance(descendant.value.func, ast.Name)
                and descendant.value.func.id == "getattr"
                and len(descendant.value.args) >= 2
                and isinstance(descendant.value.args[0], ast.Name)
                and descendant.value.args[0].id == "mcp"
                and isinstance(descendant.value.args[1], ast.Constant)
                and descendant.value.args[1].value == "_mcp_server"
            ):
                continue
            server_receiver_names.add(descendant.targets[0].id)

        for descendant in ast.walk(node):
            if not isinstance(descendant, ast.Assign):
                continue
            if len(descendant.targets) != 1:
                continue
            target = descendant.targets[0]
            exact_direct_target = (
                isinstance(target, ast.Attribute)
                and target.attr == "version"
                and isinstance(target.value, ast.Attribute)
                and target.value.attr == "_mcp_server"
                and isinstance(target.value.value, ast.Name)
                and target.value.value.id == "mcp"
            )
            proven_local_target = (
                isinstance(target, ast.Attribute)
                and target.attr == "version"
                and isinstance(target.value, ast.Name)
                and target.value.id in server_receiver_names
            )
            if not (exact_direct_target or proven_local_target):
                continue
            value = descendant.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "_application_version"
            ):
                return True
    return False


def _build_calls_version_binding(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "build_server":
            continue
        for descendant in ast.walk(node):
            if not isinstance(descendant, ast.Call):
                continue
            if not (
                isinstance(descendant.func, ast.Name)
                and descendant.func.id == "_bind_server_info_version"
            ):
                continue
            if any(
                isinstance(argument, ast.Name) and argument.id == "mcp"
                for argument in descendant.args
            ):
                return True
    return False


def validate(errors: list[str], *, root: Path) -> None:
    services_root = root / "mcp" / "services"
    for pyproject_path in sorted(services_root.glob("*/pyproject.toml")):
        package_root = pyproject_path.parent
        relative_package = package_root.relative_to(root)
        try:
            project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))[
                "project"
            ]
            project_version = project["version"]
        except (KeyError, tomllib.TOMLDecodeError) as exc:
            errors.append(
                f"{relative_package}/pyproject.toml has no readable project.version: {exc}"
            )
            continue

        server_paths = sorted((package_root / "src").glob("*/server.py"))
        if len(server_paths) != 1:
            errors.append(
                f"{relative_package} must expose exactly one src/*/server.py "
                "for MCP application identity"
            )
            continue

        server_path = server_paths[0]
        relative_server = server_path.relative_to(root)
        try:
            tree = ast.parse(server_path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            errors.append(f"{relative_server} cannot be parsed: {exc}")
            continue

        embedded_version = _application_version(tree)
        if embedded_version != project_version:
            errors.append(
                f"{relative_server} APPLICATION_VERSION={embedded_version!r} "
                f"must equal pyproject project.version={project_version!r}"
            )
        if _uses_ambient_distribution_metadata(tree):
            errors.append(
                f"{relative_server} must not derive serverInfo.version from "
                "ambient importlib.metadata"
            )
        if not _returns_embedded_version(tree):
            errors.append(
                f"{relative_server} _application_version must return "
                "APPLICATION_VERSION directly"
            )
        if not _binds_embedded_version(tree):
            errors.append(
                f"{relative_server} _bind_server_info_version must assign "
                "server version from _application_version()"
            )
        if not _build_calls_version_binding(tree):
            errors.append(
                f"{relative_server} build_server must call "
                "_bind_server_info_version(mcp)"
            )
