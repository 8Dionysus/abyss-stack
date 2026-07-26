from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = REPO_ROOT / "scripts" / "aoa-sync-federation-surfaces"
ROUTING_CONFIG = REPO_ROOT / "config-templates" / "Configs" / "federation" / "aoa-routing.yaml"
ROUTING_SOURCE_RELS = {
    "docs/FEDERATION_ENTRY_ABI.md": (
        "mechanics/boundary-bridge/parts/federation-entry/docs/"
        "federation-entry-abi.md"
    ),
    "docs/RECURRENCE_NAVIGATION_BOUNDARY.md": (
        "mechanics/recurrence/parts/return-navigation/docs/"
        "recurrence-navigation-boundary.md"
    ),
    "schemas/kag-source-lift-relation-hints.schema.json": (
        "mechanics/boundary-bridge/parts/tos-kag-boundary/schemas/"
        "kag-source-lift-relation-hints.schema.json"
    ),
    "schemas/federation-entrypoints.schema.json": (
        "mechanics/boundary-bridge/parts/federation-entry/schemas/"
        "federation-entrypoints.schema.json"
    ),
    "schemas/return-navigation-hints.schema.json": (
        "mechanics/recurrence/parts/return-navigation/schemas/"
        "return-navigation-hints.schema.json"
    ),
}


def run_sync(args: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def create_source_repo(root: Path) -> str:
    payload = yaml.safe_load(ROUTING_CONFIG.read_text(encoding="utf-8"))
    for rel_path in payload["required_files"]:
        source_rel = ROUTING_SOURCE_RELS.get(rel_path)
        if source_rel is None and rel_path.startswith("schemas/"):
            source_rel = f"routing/core/schemas/{Path(rel_path).name}"
        path = root / (source_rel or rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            path.write_text("{}\n", encoding="utf-8")
        else:
            path.write_text(f"# {rel_path}\n", encoding="utf-8")

    for args in (
        ["git", "init"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "Test User"],
        ["git", "add", "."],
        ["git", "commit", "-m", "seed aoa-routing federation source"],
    ):
        subprocess.run(args, cwd=root, text=True, capture_output=True, check=True)

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_routing_sync_resolves_current_owner_source_homes(tmp_path: Path) -> None:
    if shutil.which("rsync") is None:
        pytest.skip("aoa-sync-federation-surfaces sync mode requires rsync")

    source_root = tmp_path / "aoa-routing"
    stack_root = tmp_path / "abyss-stack"
    source_commit = create_source_repo(source_root)
    env = {
        **os.environ,
        "AOA_STACK_ROOT": str(stack_root),
        "AOA_ROUTING_ROOT": str(source_root),
    }

    result = run_sync(["--layer", "aoa-routing"], env=env)
    assert result.returncode == 0, result.stderr
    mirror_root = (
        stack_root / "Knowledge" / "federation" / "aoa-routing"
    )
    assert not (source_root / "docs" / "FEDERATION_ENTRY_ABI.md").exists()
    assert not (source_root / "schemas" / "aoa-router.schema.json").exists()
    assert (
        mirror_root / "docs" / "FEDERATION_ENTRY_ABI.md"
    ).read_text(encoding="utf-8").startswith("# docs/FEDERATION_ENTRY_ABI.md")
    assert json.loads(
        (mirror_root / "schemas" / "aoa-router.schema.json").read_text(
            encoding="utf-8"
        )
    ) == {}
    manifest = json.loads(
        (
            mirror_root / "manifest" / "federation_mirror_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["source_git_commit"] == source_commit
    assert manifest["required_files"] == yaml.safe_load(
        ROUTING_CONFIG.read_text(encoding="utf-8")
    )["required_files"]


def test_json_check_detects_stale_manifest_and_sync_if_stale_repairs_it(tmp_path: Path) -> None:
    if shutil.which("rsync") is None:
        pytest.skip("aoa-sync-federation-surfaces sync mode requires rsync")

    source_root = tmp_path / "aoa-routing"
    stack_root = tmp_path / "abyss-stack"
    source_commit = create_source_repo(source_root)
    env = {
        **os.environ,
        "AOA_STACK_ROOT": str(stack_root),
        "AOA_ROUTING_ROOT": str(source_root),
    }

    initial_sync = run_sync(["--layer", "aoa-routing"], env=env)
    assert initial_sync.returncode == 0, initial_sync.stderr

    manifest_path = (
        stack_root
        / "Knowledge"
        / "federation"
        / "aoa-routing"
        / "manifest"
        / "federation_mirror_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_git_commit"] = "0" * 40
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    stale_check = run_sync(["--check", "--json", "--layer", "aoa-routing"], env=env)
    assert stale_check.returncode == 1
    stale_payload = json.loads(stale_check.stdout)
    assert stale_payload["status"] == "stale"
    assert stale_payload["freshness_status"] == "source_commit_mismatch"
    assert stale_payload["source_git_commit"] == source_commit
    assert stale_payload["mirror_source_git_commit"] == "0" * 40
    assert stale_payload["sync_recommended"] is True
    assert stale_payload["synced"] is False

    repaired_check = run_sync(
        ["--check", "--json", "--sync-if-stale", "--layer", "aoa-routing"],
        env=env,
    )
    assert repaired_check.returncode == 0, repaired_check.stderr
    repaired_payload = json.loads(repaired_check.stdout)
    assert repaired_payload["status"] == "ok"
    assert repaired_payload["freshness_status"] == "current"
    assert repaired_payload["source_git_commit"] == source_commit
    assert repaired_payload["mirror_source_git_commit"] == source_commit
    assert repaired_payload["sync_recommended"] is False
    assert repaired_payload["synced"] is True


def test_json_check_rejects_content_hash_drift_and_repairs_it(tmp_path: Path) -> None:
    if shutil.which("rsync") is None:
        pytest.skip("aoa-sync-federation-surfaces sync mode requires rsync")

    source_root = tmp_path / "aoa-routing"
    stack_root = tmp_path / "abyss-stack"
    create_source_repo(source_root)
    env = {
        **os.environ,
        "AOA_STACK_ROOT": str(stack_root),
        "AOA_ROUTING_ROOT": str(source_root),
    }

    initial_sync = run_sync(["--layer", "aoa-routing"], env=env)
    assert initial_sync.returncode == 0, initial_sync.stderr
    mirrored_router = (
        stack_root
        / "Knowledge"
        / "federation"
        / "aoa-routing"
        / "generated"
        / "aoa_router.min.json"
    )
    mirrored_router.write_text('{"tampered":true}\n', encoding="utf-8")

    invalid_check = run_sync(
        ["--check", "--json", "--layer", "aoa-routing"],
        env=env,
    )
    assert invalid_check.returncode == 1
    invalid_payload = json.loads(invalid_check.stdout)
    assert invalid_payload["status"] == "invalid_manifest"
    assert invalid_payload["freshness_status"] == "invalid_manifest"
    assert invalid_payload["sync_recommended"] is True

    repaired_check = run_sync(
        ["--check", "--json", "--sync-if-stale", "--layer", "aoa-routing"],
        env=env,
    )
    assert repaired_check.returncode == 0, repaired_check.stderr
    repaired_payload = json.loads(repaired_check.stdout)
    assert repaired_payload["status"] == "ok"
    assert repaired_payload["freshness_status"] == "current"
    assert repaired_payload["synced"] is True
    assert mirrored_router.read_text(encoding="utf-8") == "{}\n"
