from __future__ import annotations

import json
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = REPO_ROOT / "scripts" / "aoa-sync-federation-surfaces"
ROUTING_CONFIG = REPO_ROOT / "config-templates" / "Configs" / "federation" / "aoa-routing.yaml"
CUTOVER_TEST_HELPERS_PATH = Path(__file__).with_name(
    "test_routing_cutover.py"
)
CUTOVER_TEST_HELPERS_SPEC = importlib.util.spec_from_file_location(
    "routing_cutover_test_helpers",
    CUTOVER_TEST_HELPERS_PATH,
)
assert (
    CUTOVER_TEST_HELPERS_SPEC is not None
    and CUTOVER_TEST_HELPERS_SPEC.loader is not None
)
CUTOVER_TEST_HELPERS = importlib.util.module_from_spec(
    CUTOVER_TEST_HELPERS_SPEC
)
sys.modules[CUTOVER_TEST_HELPERS_SPEC.name] = CUTOVER_TEST_HELPERS
CUTOVER_TEST_HELPERS_SPEC.loader.exec_module(CUTOVER_TEST_HELPERS)


def run_sync(args: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def materialize_canonical_routing(
    tmp_path: Path,
    stack_root: Path,
) -> Path:
    payload = yaml.safe_load(ROUTING_CONFIG.read_text(encoding="utf-8"))
    fixture = CUTOVER_TEST_HELPERS.make_fixture(
        tmp_path,
        required_files=list(payload["required_files"]),
    )
    isolated_target = tmp_path / "sdk-materialized-routing"
    target = (
        stack_root / "Knowledge" / "federation" / "aoa-routing"
    )
    result = CUTOVER_TEST_HELPERS.run_cutover(
        [
            "materialize",
            *CUTOVER_TEST_HELPERS.exact_args(fixture, isolated_target),
            "--isolated",
        ]
    )
    assert result.returncode == 0, result.stderr + result.stdout
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(isolated_target, target)
    return target


def test_routing_check_reads_only_sdk_canonical_materialization(
    tmp_path: Path,
) -> None:
    stack_root = tmp_path / "abyss-stack"
    target = materialize_canonical_routing(tmp_path, stack_root)
    env = {
        **os.environ,
        "AOA_STACK_ROOT": str(stack_root),
    }

    result = run_sync(
        ["--check", "--json", "--layer", "aoa-routing"],
        env=env,
    )

    assert result.returncode == 0, result.stderr
    checked = json.loads(result.stdout)
    assert checked["status"] == "ok"
    assert checked["freshness_status"] == "sdk_canonical_materialized"
    assert checked["source_root"] is None
    assert checked["source_git_commit"] == CUTOVER_TEST_HELPERS.SDK_REF
    assert checked["mirror_source_git_commit"] == (
        CUTOVER_TEST_HELPERS.SDK_REF
    )
    assert checked["sync_recommended"] is False
    assert checked["synced"] is False
    assert Path(checked["mirror_target"]) == target


def test_routing_sync_and_auto_repair_are_retired(tmp_path: Path) -> None:
    stack_root = tmp_path / "abyss-stack"
    env = {
        **os.environ,
        "AOA_STACK_ROOT": str(stack_root),
    }

    sync = run_sync(["--layer", "aoa-routing"], env=env)
    assert sync.returncode == 1
    assert "materialized only by receipt-bound" in sync.stderr

    repair = run_sync(
        [
            "--check",
            "--json",
            "--sync-if-stale",
            "--layer",
            "aoa-routing",
        ],
        env=env,
    )
    assert repair.returncode == 1
    assert "cannot be repaired by federation sync" in repair.stderr


def test_routing_check_rejects_drift_without_checkout_repair(
    tmp_path: Path,
) -> None:
    stack_root = tmp_path / "abyss-stack"
    target = materialize_canonical_routing(tmp_path, stack_root)
    mirrored_router = target / "generated" / "aoa_router.min.json"
    mirrored_router.write_text('{"tampered":true}\n', encoding="utf-8")
    env = {
        **os.environ,
        "AOA_STACK_ROOT": str(stack_root),
    }

    invalid_check = run_sync(
        ["--check", "--json", "--layer", "aoa-routing"],
        env=env,
    )
    assert invalid_check.returncode == 1
    invalid_payload = json.loads(invalid_check.stdout)
    assert invalid_payload["status"] == (
        "invalid_canonical_materialization"
    )
    assert invalid_payload["freshness_status"] == (
        "cutover_rematerialization_required"
    )
    assert invalid_payload["source_root"] is None
    assert invalid_payload["sync_recommended"] is False
    assert invalid_payload["synced"] is False
    assert mirrored_router.read_text(encoding="utf-8") == (
        '{"tampered":true}\n'
    )
