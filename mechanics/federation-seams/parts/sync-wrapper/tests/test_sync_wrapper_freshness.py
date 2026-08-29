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
AOA_KAG_SOURCE_PATHS = {
    "docs/REASONING_HANDOFF.md": (
        "mechanics/checkpoint/parts/reasoning-handoff/docs/reasoning-handoff.md"
    ),
    "docs/REASONING_HANDOFF_PACK.md": (
        "mechanics/checkpoint/parts/reasoning-handoff/docs/reasoning-handoff-pack.md"
    ),
    "docs/RECURRENCE_REGROUNDING.md": (
        "mechanics/recurrence/parts/return-regrounding/docs/recurrence-regrounding.md"
    ),
    "docs/FEDERATION_KAG_READINESS.md": (
        "mechanics/boundary-bridge/parts/source-owned-export/docs/federation-kag-readiness.md"
    ),
    "docs/COUNTERPART_CONSUMER_CONTRACT.md": (
        "mechanics/boundary-bridge/parts/counterpart-edge/docs/counterpart-consumer-contract.md"
    ),
    "docs/TOS_RETRIEVAL_AXIS_PACK.md": (
        "mechanics/boundary-bridge/parts/tos-retrieval-axis/docs/tos-retrieval-axis-pack.md"
    ),
    "docs/TOS_ZARATHUSTRA_ROUTE_RETRIEVAL_PACK.md": (
        "mechanics/boundary-bridge/parts/tos-retrieval-axis/docs/tos-zarathustra-route-retrieval-pack.md"
    ),
    "generated/federation_spine.min.json": (
        "mechanics/boundary-bridge/parts/federation-spine/generated/federation_spine.min.json"
    ),
    "generated/tiny_consumer_bundle.min.json": (
        "mechanics/boundary-bridge/parts/tiny-consumer-bundle/generated/tiny_consumer_bundle.min.json"
    ),
    "generated/reasoning_handoff_pack.min.json": (
        "mechanics/checkpoint/parts/reasoning-handoff/generated/reasoning_handoff_pack.min.json"
    ),
    "generated/return_regrounding_pack.min.json": (
        "mechanics/recurrence/parts/return-regrounding/generated/return_regrounding_pack.min.json"
    ),
    "generated/technique_lift_pack.min.json": (
        "mechanics/distillation/parts/technique-lift/generated/technique_lift_pack.min.json"
    ),
    "generated/tos_retrieval_axis_pack.min.json": (
        "mechanics/boundary-bridge/parts/tos-retrieval-axis/generated/tos_retrieval_axis_pack.min.json"
    ),
    "generated/tos_text_chunk_map.min.json": (
        "mechanics/distillation/parts/tos-text-chunk-map/generated/tos_text_chunk_map.min.json"
    ),
    "generated/cross_source_node_projection.min.json": (
        "mechanics/boundary-bridge/parts/cross-source-projection/generated/cross_source_node_projection.min.json"
    ),
    "generated/counterpart_federation_exposure_review.min.json": (
        "mechanics/audit/parts/exposure-review/generated/counterpart_federation_exposure_review.min.json"
    ),
    "generated/tos_zarathustra_route_retrieval_pack.min.json": (
        "mechanics/boundary-bridge/parts/tos-retrieval-axis/generated/tos_zarathustra_route_retrieval_pack.min.json"
    ),
    "schemas/federation-spine.schema.json": (
        "mechanics/boundary-bridge/parts/federation-spine/schemas/federation-spine.schema.json"
    ),
    "schemas/tiny-consumer-bundle.schema.json": (
        "mechanics/boundary-bridge/parts/tiny-consumer-bundle/schemas/tiny-consumer-bundle.schema.json"
    ),
    "schemas/reasoning-handoff-pack.schema.json": (
        "mechanics/checkpoint/parts/reasoning-handoff/schemas/reasoning-handoff-pack.schema.json"
    ),
    "schemas/return-regrounding-pack.schema.json": (
        "mechanics/recurrence/parts/return-regrounding/schemas/return-regrounding-pack.schema.json"
    ),
    "schemas/technique-lift-pack.schema.json": (
        "mechanics/distillation/parts/technique-lift/schemas/technique-lift-pack.schema.json"
    ),
    "schemas/tos-retrieval-axis-pack.schema.json": (
        "mechanics/boundary-bridge/parts/tos-retrieval-axis/schemas/tos-retrieval-axis-pack.schema.json"
    ),
    "schemas/tos-text-chunk-map.schema.json": (
        "mechanics/distillation/parts/tos-text-chunk-map/schemas/tos-text-chunk-map.schema.json"
    ),
    "schemas/cross-source-node-projection.schema.json": (
        "mechanics/boundary-bridge/parts/cross-source-projection/schemas/cross-source-node-projection.schema.json"
    ),
    "schemas/counterpart-federation-exposure-review.schema.json": (
        "mechanics/audit/parts/exposure-review/schemas/counterpart-federation-exposure-review.schema.json"
    ),
    "schemas/tos-zarathustra-route-retrieval-pack.schema.json": (
        "mechanics/boundary-bridge/parts/tos-retrieval-axis/schemas/tos-zarathustra-route-retrieval-pack.schema.json"
    ),
    "schemas/counterpart-consumer-contract.schema.json": (
        "mechanics/boundary-bridge/parts/counterpart-edge/schemas/counterpart-consumer-contract.schema.json"
    ),
    "schemas/bridge-envelope.schema.json": (
        "mechanics/boundary-bridge/parts/tos-retrieval-axis/schemas/bridge-envelope.schema.json"
    ),
}
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


def test_aoa_kag_sync_maps_mechanic_owned_sources(
    tmp_path: Path,
) -> None:
    kag_config = REPO_ROOT / "config-templates" / "Configs" / "federation" / "aoa-kag.yaml"
    payload = yaml.safe_load(kag_config.read_text(encoding="utf-8"))
    source_root = tmp_path / "aoa-kag"
    stack_root = tmp_path / "abyss-stack"
    expected: dict[str, str] = {}

    for mirror_rel in payload["required_files"]:
        source_rel = AOA_KAG_SOURCE_PATHS.get(mirror_rel, mirror_rel)
        source_path = source_root / source_rel
        source_path.parent.mkdir(parents=True, exist_ok=True)
        marker = f"source:{source_rel}\n"
        source_path.write_text(marker, encoding="utf-8")
        expected[mirror_rel] = marker

    env = {
        **os.environ,
        "AOA_KAG_ROOT": str(source_root),
        "AOA_STACK_ROOT": str(stack_root),
    }
    result = run_sync(["--layer", "aoa-kag"], env=env)

    assert result.returncode == 0, result.stderr + result.stdout
    mirror_root = stack_root / "Knowledge" / "federation" / "aoa-kag"
    for mirror_rel, marker in expected.items():
        assert (mirror_root / mirror_rel).read_text(encoding="utf-8") == marker
    assert not (source_root / "docs" / "REASONING_HANDOFF.md").exists()
