from __future__ import annotations

import json
from pathlib import Path

import pytest

from aoa_kag_mcp.core import AoAKagMCPState
from aoa_kag_mcp.server import build_server


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def seed_provider(
    root: Path,
    repo: str,
    *,
    local_id: str,
    source_index_ref: str = "kag/indexes/source_surface_index.json",
) -> dict[str, object]:
    kag = root / "kag"
    source_index_payload = {
        "schema_version": "aoa-repo-local-kag-index-v1",
        "repo": {"name": repo, "root": ".", "git_ref": "fixture"},
        "index_identity": {
            "local_id": "index:repo-local:source-surfaces",
            "artifact_kind": "source_surface_index",
            "content_digest": "fixture",
            "schema_ref": "aoa-kag:schemas/repo-local-kag-index.schema.json",
        },
        "coverage_summary": {"record_count": 1, "unknown_count": 0},
        "classification_summary": {
            "artifact_kind": {"document": 1},
            "primary_kind": {"document": 1},
            "surface_state": {"authored_source": 1},
            "document_role": {"readme": 1},
            "mechanics_role": {"none": 1},
            "command_role": {"none": 1},
        },
        "records": [],
    }
    common_surface_profile = {
        "source": "source_surface_index",
        "counts": source_index_payload["classification_summary"],
        "quality": {
            "unknown_count": 0,
            "has_kag_home": True,
            "has_record_classes": True,
            "has_source_index": True,
            "has_owner_commands": False,
            "has_generated_readmodels": False,
            "has_validation_route": True,
        },
    }
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
    write_json(kag / "indexes" / "source_surface_index.json", source_index_payload)
    write_json(
        kag / "receipts" / "validation_receipt.json",
        {
            "schema_version": "aoa_repo_kag_validation_receipt_v1",
            "state": "fresh",
            "validator": "owner-local",
            "checked_ref": "README.md",
        },
    )
    write_json(
        kag / "indexes" / "provider_readiness_index.json",
        {
            "schema_version": "aoa_repo_kag_provider_readiness_index_v1",
            "repo": repo,
            "records": [{"local_id": local_id, "record_class": "node"}],
        },
    )
    if source_index_ref:
        write_json(
            root / source_index_ref,
            {
                "schema_version": "aoa-repo-local-kag-index-v1",
                "repo": repo,
                "index_identity": {"local_id": "index:repo-local:source-surfaces"},
                "coverage_summary": {"record_count": 1, "document_count": 1},
                "classification_summary": {"primary_kind": {"document": 1}},
                "records": [
                    {
                        "identity": {"repo": repo, "path": "README.md"},
                        "owner_return_route": {"path": "README.md", "route_kind": "source"},
                    }
                ],
            },
        )
        index_files = ["kag/indexes/provider_readiness_index.json", source_index_ref]
        index_status = "passed"
    else:
        write_json(
            kag / "indexes" / "source_inventory.json",
            {
                "schema_version": "aoa_repo_local_source_inventory_v1",
                "repo": repo,
                "records": [{"path": "README.md"}],
            },
        )
        index_files = ["kag/indexes/source_inventory.json"]
        index_status = "owner-specific"
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
        "generation_profile": {
            "source_home_surfaces": ["kag/", "kag/source_home.manifest.json"],
            "candidate_source_surfaces": ["README.md"],
            "source_owned_exports": [],
            "graph_entities": ["source surface"],
            "event_surfaces": [],
            "document_surfaces": ["README.md"],
            "validators": ["scripts/validate_local_kag_provider.py"],
            "release_gate": "python scripts/release_check.py",
            "runtime_consumers": ["aoa-kag-mcp"],
            "builder_routes": [
                {
                    "route": "local KAG provider record",
                    "surface": "kag/manifest.json",
                    "record_count": 1,
                }
            ],
        },
        "repo_local_index": {
            "status": index_status,
            "source_index_ref": source_index_ref,
            "index_files": index_files,
            "coverage": {"documents": 1, "commands": 0, "validators": 1},
            "common_surface_profile": common_surface_profile,
            "coverage_report_ref": "generated/repo_local_kag_coverage.min.json",
            "coverage_owner_key": repo,
        },
    }


def seed_workspace(root: Path) -> AoAKagMCPState:
    aoa_kag = root / "aoa-kag"
    repo_a = root / "connectors" / "repo-a"
    aoa_kag_provider = seed_provider(
        aoa_kag,
        "aoa-kag",
        local_id="aoa-kag-source-home",
        source_index_ref="",
    )
    repo_a_provider = seed_provider(repo_a, "repo-a", local_id="repo-a-source-home")
    providers = [aoa_kag_provider, repo_a_provider]
    repo_local_indexes = {
        str(provider["repo"]): provider["repo_local_index"]
        for provider in providers
    }
    common_surface_profiles = {
        repo: packet["common_surface_profile"]
        for repo, packet in repo_local_indexes.items()
    }
    write_json(
        aoa_kag / "generated" / "local_kag_provider_map.min.json",
        {
            "schema_version": "aoa-local-kag-provider-map-v1",
            "providers": providers,
            "provider_repo_local_indexes": repo_local_indexes,
            "provider_common_surface_profiles": common_surface_profiles,
            "remaining_routes": [],
            "os_surfaces": [],
            "provider_status_counts": {"provider_ready": 2},
            "mcp_handoff": {"service_route": "mcp/services/aoa-kag-mcp"},
            "provider_generation_profiles": {
                str(provider["repo"]): provider["generation_profile"] for provider in providers
            },
        },
    )
    write_json(
        aoa_kag / "manifests" / "local_kag_readiness.json",
        {
            "schema_version": "aoa-local-kag-readiness-v1",
            "os_surfaces": [
                {
                    "surface_id": ".codex",
                    "root": (root / ".codex").as_posix(),
                    "provider_status": "runtime_consumer",
                    "owner_return_route": {"repo": "repo-a", "surface": ".codex/AGENTS.md", "route_kind": "runtime"},
                },
                {
                    "surface_id": "connectors/repo-a",
                    "root": (root / "connectors" / "repo-a").as_posix(),
                    "provider_status": "provider_ready",
                    "owner_return_route": {"repo": "repo-a", "surface": "README.md", "route_kind": "source"},
                },
            ],
        },
    )
    write_json(
        aoa_kag / "generated" / "repo_local_kag_coverage.min.json",
        {
            "coverage_summary": {"owner_count": 2, "passed": 1, "owner_specific": 1, "missing": 0},
            "owners": [
                {
                    "repo": str(provider["repo"]),
                    "root": (aoa_kag if provider["repo"] == "aoa-kag" else repo_a).as_posix(),
                    "kag_home": ((aoa_kag if provider["repo"] == "aoa-kag" else repo_a) / "kag").as_posix(),
                    "owner_type": "organ",
                    "index_status": provider["repo_local_index"]["status"],
                    "index_files": provider["repo_local_index"]["index_files"],
                    "coverage": provider["repo_local_index"]["coverage"],
                    "common_surface_profile": provider["repo_local_index"]["common_surface_profile"],
                }
                for provider in providers
            ],
        },
    )
    return AoAKagMCPState.discover(workspace_root=root, aoa_kag_root=aoa_kag)


def test_status_reports_provider_map_and_handoff(tmp_path: Path) -> None:
    status = seed_workspace(tmp_path).status()

    assert status["provider_map_exists"] is True
    assert status["readiness_exists"] is True
    assert status["coverage_exists"] is True
    assert status["provider_count"] == 2
    assert status["remaining_route_count"] == 0
    assert status["os_surface_count"] == 2
    assert status["service_route"] == "mcp/services/aoa-kag-mcp"


def test_provider_lookup_preserves_owner_return_route(tmp_path: Path) -> None:
    packet = seed_workspace(tmp_path).provider_lookup("repo-a")

    assert packet["schema"] == "aoa_kag_provider_lookup_v1"
    assert packet["status"] == "provider_ready"
    assert packet["provider"]["owner_return_routes"][0]["path"] == "README.md"
    assert packet["repo_local_index"]["status"] == "passed"
    assert packet["common_surface_profile"]["source"] == "source_surface_index"
    assert packet["provider_root"] == (tmp_path / "connectors" / "repo-a").resolve().as_posix()


def test_freshness_check_reads_receipt_handles(tmp_path: Path) -> None:
    freshness = seed_workspace(tmp_path).freshness_check()

    assert freshness["ok"] is True
    assert len(freshness["freshness"]) == 2
    assert all(row["receipt_exists"] for row in freshness["freshness"])


def test_freshness_check_blocks_unmaterialized_receipts(tmp_path: Path) -> None:
    state = seed_workspace(tmp_path)
    receipt = tmp_path / "connectors" / "repo-a" / "kag" / "receipts" / "validation_receipt.json"
    receipt.unlink()

    freshness = state.freshness_check()

    assert freshness["ok"] is False
    assert "repo-a:kag/receipts/validation_receipt.json" in freshness["missing_receipts"]
    row = next(item for item in freshness["freshness"] if item["repo"] == "repo-a")
    assert row["provider_root_exists"] is True
    assert row["receipt_exists"] is False


def test_generation_route_lookup_reads_provider_profile(tmp_path: Path) -> None:
    packet = seed_workspace(tmp_path).generation_route_lookup("repo-a")

    assert packet["schema"] == "aoa_kag_generation_route_lookup_v1"
    assert packet["status"] == "available"
    assert packet["source_home_surfaces"] == ["kag/", "kag/source_home.manifest.json"]
    assert packet["builder_routes"][0]["surface"] == "kag/manifest.json"


def test_source_index_lookup_summarizes_repo_local_index(tmp_path: Path) -> None:
    state = seed_workspace(tmp_path)

    packet = state.source_index_lookup("repo-a")
    owner_specific = state.source_index_lookup("aoa-kag")

    assert packet["schema"] == "aoa_kag_source_index_lookup_v1"
    assert packet["status"] == "passed"
    assert packet["source_index_exists"] is True
    assert packet["source_index_summary"]["record_count"] == 1
    assert owner_specific["status"] == "owner-specific"
    assert owner_specific["source_index_ref"] == ""
    assert owner_specific["index_files"] == ["kag/indexes/source_inventory.json"]


def test_source_index_lookup_keeps_reads_inside_provider_root(tmp_path: Path) -> None:
    state = seed_workspace(tmp_path)
    provider_map = state.provider_map()
    provider_map["provider_repo_local_indexes"]["repo-a"]["source_index_ref"] = "../outside.json"
    for provider in provider_map["providers"]:
        if provider["repo"] == "repo-a":
            provider["repo_local_index"]["source_index_ref"] = "../outside.json"
            break
    write_json(state.provider_map_path, provider_map)

    with pytest.raises(ValueError, match="escapes provider root"):
        state.source_index_lookup("repo-a", include_payload=True)


def test_repo_local_coverage_status_filters_rows(tmp_path: Path) -> None:
    state = seed_workspace(tmp_path)

    all_rows = state.repo_local_coverage_status()
    filtered = state.repo_local_coverage_status(status="owner-specific")

    assert all_rows["schema"] == "aoa_kag_repo_local_coverage_status_v1"
    assert all_rows["count"] == 2
    assert filtered["count"] == 1
    assert filtered["owners"][0]["repo"] == "aoa-kag"


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
    generation = state.read_resource("aoa-kag://providers/repo-a/generation")
    source_index = state.read_resource("aoa-kag://providers/repo-a/source-index")
    repo_local_index = state.read_resource("aoa-kag://providers/repo-a/repo-local-index")
    common_surface_profile = state.read_resource("aoa-kag://providers/repo-a/common-surface-profile")
    coverage = state.read_resource("aoa-kag://coverage/repo-local-source-indexes")

    assert provider_map["schema_version"] == "aoa-local-kag-provider-map-v1"
    assert os_surfaces["os_surfaces"][0]["owner_return_route"]["repo"] == "repo-a"
    assert manifest["repo"] == "repo-a"
    assert records["count"] == 1
    assert generation["status"] == "available"
    assert repo_local_index["repo_local_index"]["status"] == "passed"
    assert source_index["source_index_exists"] is True
    assert source_index["source_index"]["schema_version"] == "aoa-repo-local-kag-index-v1"
    assert common_surface_profile["common_surface_profile"]["source"] == "source_surface_index"
    assert coverage["coverage_summary"]["owner_count"] == 2


def test_source_index_and_common_profile_tools_read_provider_map(tmp_path: Path) -> None:
    state = seed_workspace(tmp_path)

    source_index = state.source_index_status("repo-a")
    profile = state.common_surface_profile("repo-a")

    assert source_index["status"] == "passed"
    assert source_index["source_index_ref"] == "kag/indexes/source_surface_index.json"
    assert profile["common_surface_profile"]["quality"]["has_source_index"] is True


def test_validation_status_checks_provider_homes(tmp_path: Path) -> None:
    packet = seed_workspace(tmp_path).validation_status(include_provider_homes=True)

    assert packet["schema"] == "aoa_kag_validation_status_v1"
    assert len(packet["provider_homes"]) == 2
    assert all(row["manifest_exists"] for row in packet["provider_homes"])


def test_server_builds() -> None:
    assert build_server() is not None
