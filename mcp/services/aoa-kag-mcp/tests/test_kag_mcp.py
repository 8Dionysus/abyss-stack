from __future__ import annotations

import json
from pathlib import Path

from aoa_kag_mcp.core import AoAKagMCPState
from aoa_kag_mcp.server import build_server


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def seed_provider(root: Path, repo: str, *, local_id: str) -> dict[str, object]:
    kag = root / "kag"
    write_json(
        kag / "manifest.json",
        {
            "schema_version": "aoa_repo_kag_manifest_v1",
            "repo": repo,
            "owner_return_routes": [{"path": "README.md", "route_kind": "source"}],
            "record_classes": ["node", "edge", "index", "projection", "receipt"],
        },
    )
    write_json(
        kag / "nodes" / f"{local_id}.json",
        {
            "schema_version": "aoa_repo_kag_record_v1",
            "record_class": "node",
            "local_id": local_id,
            "source_refs": [{"path": "README.md"}],
            "owner_return_route": {"path": "README.md", "route_kind": "source"},
        },
    )
    write_json(
        kag / "receipts" / "validation_receipt.json",
        {
            "schema_version": "aoa_repo_kag_validation_receipt_v1",
            "state": "fresh",
            "validator": "owner-local",
            "checked_ref": "README.md",
        },
    )
    return {
        "repo": repo,
        "provider_status": "provider_ready",
        "record_counts": {"node": 1, "edge": 0, "index": 0, "projection": 0, "receipt": 1},
        "owner_return_routes": [{"path": "README.md", "route_kind": "source"}],
        "mcp_access_shape": ["resource", "tool", "prompt", "root"],
        "freshness_handles": [
            {
                "receipt_ref": "kag/receipts/validation_receipt.json",
                "checked_ref": "README.md",
                "state": "fresh",
                "validator": "owner-local",
                "owner_return_route": {"path": "README.md", "route_kind": "source"},
            }
        ],
    }


def seed_workspace(root: Path) -> AoAKagMCPState:
    aoa_kag = root / "aoa-kag"
    repo_a = root / "repo-a"
    aoa_kag_provider = seed_provider(aoa_kag, "aoa-kag", local_id="aoa-kag-source-home")
    repo_a_provider = seed_provider(repo_a, "repo-a", local_id="repo-a-source-home")
    write_json(
        aoa_kag / "generated" / "local_kag_provider_map.min.json",
        {
            "schema_version": "aoa-local-kag-provider-map-v1",
            "providers": [aoa_kag_provider, repo_a_provider],
            "remaining_routes": [],
            "os_surfaces": [{"repo": "runtime-organ", "surface_kind": "runtime"}],
            "provider_status_counts": {"provider_ready": 2},
            "mcp_handoff": {"service_route": "mcp/services/aoa-kag-mcp"},
        },
    )
    write_json(
        aoa_kag / "manifests" / "local_kag_readiness.json",
        {"schema_version": "aoa-local-kag-readiness-v1", "os_surfaces": [{"repo": "runtime-organ"}]},
    )
    return AoAKagMCPState.discover(workspace_root=root, aoa_kag_root=aoa_kag)


def test_status_reports_provider_map_and_handoff(tmp_path: Path) -> None:
    status = seed_workspace(tmp_path).status()

    assert status["provider_map_exists"] is True
    assert status["readiness_exists"] is True
    assert status["provider_count"] == 2
    assert status["remaining_route_count"] == 0
    assert status["service_route"] == "mcp/services/aoa-kag-mcp"


def test_provider_lookup_preserves_owner_return_route(tmp_path: Path) -> None:
    packet = seed_workspace(tmp_path).provider_lookup("repo-a")

    assert packet["schema"] == "aoa_kag_provider_lookup_v1"
    assert packet["status"] == "provider_ready"
    assert packet["provider"]["owner_return_routes"][0]["path"] == "README.md"
    assert packet["provider_root"] == (tmp_path / "repo-a").resolve().as_posix()


def test_freshness_check_reads_receipt_handles(tmp_path: Path) -> None:
    freshness = seed_workspace(tmp_path).freshness_check()

    assert freshness["ok"] is True
    assert len(freshness["freshness"]) == 2
    assert all(row["receipt_exists"] for row in freshness["freshness"])


def test_source_return_lookup_can_filter_provider_records(tmp_path: Path) -> None:
    packet = seed_workspace(tmp_path).source_return_lookup("repo-a", local_id="repo-a-source-home")

    assert packet["schema"] == "aoa_kag_source_return_lookup_v1"
    assert packet["matches"][0]["record_ref"] == "kag/nodes/repo-a-source-home.json"
    assert packet["matches"][0]["source_refs"][0]["path"] == "README.md"


def test_registry_and_composition_slices_are_bounded(tmp_path: Path) -> None:
    state = seed_workspace(tmp_path)
    registry = state.registry_slice(status="provider_ready", limit=1)
    composition = state.composition_slice(query="repo-a", limit=5)

    assert registry["count"] == 1
    assert registry["items"][0]["kind"] == "provider"
    assert composition["count"] >= 1
    assert composition["results"][0]["collection"] == "providers"


def test_resources_return_provider_map_manifest_records_and_readiness(tmp_path: Path) -> None:
    state = seed_workspace(tmp_path)

    provider_map = state.read_resource("aoa-kag://registry/provider-map")
    os_surfaces = state.read_resource("aoa-kag://readiness/os-surfaces")
    manifest = state.read_resource("aoa-kag://providers/repo-a/manifest")
    records = state.read_resource("aoa-kag://providers/repo-a/records/node")

    assert provider_map["schema_version"] == "aoa-local-kag-provider-map-v1"
    assert os_surfaces["os_surfaces"][0]["repo"] == "runtime-organ"
    assert manifest["repo"] == "repo-a"
    assert records["count"] == 1


def test_validation_status_checks_provider_homes(tmp_path: Path) -> None:
    packet = seed_workspace(tmp_path).validation_status(include_provider_homes=True)

    assert packet["schema"] == "aoa_kag_validation_status_v1"
    assert len(packet["provider_homes"]) == 2
    assert all(row["manifest_exists"] for row in packet["provider_homes"])


def test_server_builds() -> None:
    assert build_server() is not None
