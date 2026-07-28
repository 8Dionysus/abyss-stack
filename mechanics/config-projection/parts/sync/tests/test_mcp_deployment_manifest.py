from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "mcp_deployment_manifest.py"
)
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "mcp-deployment-manifest.schema.json"
)
SOURCE_REVISION = "a" * 40


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mcp_deployment_manifest",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


manifest = load_module()


def write_service(source_root: Path, service_id: str = "example-mcp") -> Path:
    service = source_root / "mcp" / "services" / service_id
    service.mkdir(parents=True)
    (service / "pyproject.toml").write_text(
        """\
[project]
name = "example-mcp"
version = "0.4.2"
dependencies = []

[project.scripts]
example-mcp-server = "example_mcp.server:main"
""",
        encoding="utf-8",
    )
    package = service / "src" / "example_mcp"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        '__version__ = "0.4.2"\n',
        encoding="utf-8",
    )
    (package / "server.py").write_text(
        "def main() -> None:\n    return None\n",
        encoding="utf-8",
    )
    (service / "requirements.lock").write_text(
        "example-dependency==1.0.0 --hash=sha256:" + "b" * 64 + "\n",
        encoding="utf-8",
    )
    return service


def copy_projection(source_root: Path, deployed_root: Path) -> None:
    source_services = source_root / "mcp" / "services"
    deployed_services = deployed_root / "mcp" / "services"
    deployed_services.parent.mkdir(parents=True)
    shutil.copytree(source_services, deployed_services)


def initialize_git_source(source_root: Path) -> str:
    subprocess.run(
        ("git", "init", "--quiet", str(source_root)),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(source_root), "config", "user.name", "Test Operator"),
        check=True,
    )
    subprocess.run(
        (
            "git",
            "-C",
            str(source_root),
            "config",
            "user.email",
            "operator@example.invalid",
        ),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(source_root), "add", "."),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(source_root), "commit", "--quiet", "-m", "fixture"),
        check=True,
    )
    return subprocess.run(
        ("git", "-C", str(source_root), "rev-parse", "--verify", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build_exact(tmp_path: Path) -> tuple[dict, Path]:
    source_root = tmp_path / "source"
    deployed_root = tmp_path / "runtime" / "Configs"
    write_service(source_root)
    copy_projection(source_root, deployed_root)
    payload = manifest.build_manifest(
        source_root=source_root,
        deployed_root=deployed_root,
        source_revision=SOURCE_REVISION,
        deployed_at=datetime(2026, 7, 26, 19, 30, tzinfo=timezone.utc),
        delete_mode=True,
    )
    return payload, deployed_root


def test_exact_projection_publishes_content_addressed_receipt(
    tmp_path: Path,
) -> None:
    payload, _ = build_exact(tmp_path)
    output_root = tmp_path / "runtime" / "Logs" / "mcp" / "deployments"

    manifest.verify_manifest_id(payload)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(payload)
    record, latest = manifest.publish_manifest(payload, output_root)

    assert payload["parity_state"] == "exact"
    assert payload["runtime_observation_state"] == "not_observed"
    assert payload["contains_secrets"] is False
    assert payload["source"]["revision"] == SOURCE_REVISION
    assert payload["services"] == [
        {
            "service_id": "example-mcp",
            "package_name": "example-mcp",
            "package_version": "0.4.2",
            "package_source_revision": SOURCE_REVISION,
            "package_artifact_kind": "source_projection",
            "package_digest": payload["services"][0]["package_digest"],
            "dependency_lock_digest": payload["services"][0][
                "dependency_lock_digest"
            ],
            "server_entrypoints": {
                "example-mcp-server": "example_mcp.server:main"
            },
            "source_path": "mcp/services/example-mcp",
            "deployed_path": "Configs/mcp/services/example-mcp",
            "source_tree": payload["services"][0]["source_tree"],
            "deployed_tree": payload["services"][0]["deployed_tree"],
            "parity_state": "exact",
        }
    ]
    assert record.name == payload["manifest_id"].removeprefix("sha256:") + ".json"
    assert json.loads(record.read_text(encoding="utf-8")) == payload
    assert latest.read_bytes() == record.read_bytes()
    assert record.stat().st_mode & 0o777 == 0o640
    assert latest.stat().st_mode & 0o777 == 0o640


def test_projection_drift_fails_without_publishing_receipt(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    deployed_root = tmp_path / "runtime" / "Configs"
    write_service(source_root)
    copy_projection(source_root, deployed_root)
    deployed_server = (
        deployed_root
        / "mcp"
        / "services"
        / "example-mcp"
        / "src"
        / "example_mcp"
        / "server.py"
    )
    deployed_server.write_text("raise RuntimeError('drift')\n", encoding="utf-8")

    with pytest.raises(manifest.ManifestError, match="projection is not exact"):
        manifest.build_manifest(
            source_root=source_root,
            deployed_root=deployed_root,
            source_revision=SOURCE_REVISION,
            deployed_at=datetime.now(timezone.utc),
            delete_mode=False,
        )

    assert not (tmp_path / "runtime" / "Logs").exists()


def test_git_source_verification_rejects_dirty_worktree(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    service = write_service(source_root)
    source_revision = initialize_git_source(source_root)
    manifest.verify_git_source_snapshot(source_root, source_revision)

    (service / "pyproject.toml").write_text(
        "[project]\nname = \"mutated\"\n",
        encoding="utf-8",
    )

    with pytest.raises(manifest.ManifestError, match="worktree changed"):
        manifest.verify_git_source_snapshot(source_root, source_revision)


def test_main_revalidates_source_after_manifest_hashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    deployed_root = tmp_path / "runtime" / "Configs"
    service = write_service(source_root)
    copy_projection(source_root, deployed_root)
    source_revision = initialize_git_source(source_root)
    output_root = tmp_path / "runtime" / "Logs" / "mcp" / "deployments"
    original_build_manifest = manifest.build_manifest

    def build_then_mutate(**kwargs: Any) -> dict[str, Any]:
        payload = original_build_manifest(**kwargs)
        (service / "pyproject.toml").write_text(
            "[project]\nname = \"mutated\"\n",
            encoding="utf-8",
        )
        return payload

    monkeypatch.setattr(manifest, "build_manifest", build_then_mutate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT_PATH),
            "--source-root",
            str(source_root),
            "--deployed-root",
            str(deployed_root),
            "--output-root",
            str(output_root),
            "--source-revision",
            source_revision,
        ],
    )

    assert manifest.main() == 1
    assert not output_root.exists()


def test_projection_rejects_symlinked_source_content(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    deployed_root = tmp_path / "runtime" / "Configs"
    service = write_service(source_root)
    outside = tmp_path / "outside.py"
    outside.write_text("secret = 'not part of the package'\n", encoding="utf-8")
    (service / "src" / "linked.py").symlink_to(outside)
    copy_projection(source_root, deployed_root)

    with pytest.raises(manifest.ManifestError, match="file symlinks"):
        manifest.build_manifest(
            source_root=source_root,
            deployed_root=deployed_root,
            source_revision=SOURCE_REVISION,
            deployed_at=datetime.now(timezone.utc),
            delete_mode=False,
        )


def test_publish_rejects_symlinked_output_ancestor(tmp_path: Path) -> None:
    payload, _ = build_exact(tmp_path)
    real_root = tmp_path / "real-output"
    real_root.mkdir()
    linked_root = tmp_path / "linked-output"
    linked_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(manifest.ManifestError, match="cannot traverse a symlink"):
        manifest.publish_manifest(
            payload,
            linked_root / "Logs" / "mcp" / "deployments",
        )

    assert list(real_root.iterdir()) == []


def test_conflicting_content_addressed_record_is_rejected(
    tmp_path: Path,
) -> None:
    payload, _ = build_exact(tmp_path)
    output_root = tmp_path / "runtime" / "Logs" / "mcp" / "deployments"
    record, _ = manifest.publish_manifest(payload, output_root)
    record.write_text("{}\n", encoding="utf-8")

    with pytest.raises(manifest.ManifestError, match="record conflicts"):
        manifest.publish_manifest(payload, output_root)
