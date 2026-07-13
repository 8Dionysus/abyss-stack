from __future__ import annotations

import asyncio
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
        repository_index_family = {
            "source": source_index_ref,
            "entity": "kag/indexes/repo_entity_index.json",
            "artifact": "kag/indexes/repo_artifact_index.json",
            "anchor": "kag/indexes/repo_anchor_index.json",
            "event": "kag/indexes/repo_event_index.json",
            "assertion": "kag/indexes/repo_assertion_index.json",
            "relation": "kag/indexes/repo_relation_index.json",
        }
        for index_kind in ("entity", "artifact", "anchor", "event", "assertion", "relation"):
            write_json(
                root / repository_index_family[index_kind],
                {
                    "schema_version": "aoa-repo-local-kag-repository-index-v1",
                    "repo": {"name": repo, "root": ".", "git_ref": "fixture"},
                    "index_identity": {
                        "local_id": f"index:repo-local:{index_kind}",
                        "index_kind": index_kind,
                    },
                    "source_index": {
                        "path": source_index_ref,
                        "content_digest": "fixture",
                    },
                    "summary": {"entry_count": 1},
                    "entries": [{"local_id": f"{index_kind}:README.md"}],
                },
            )
        domain_index_catalog_ref = "kag/indexes/domain_index_catalog.json"
        write_json(
            root / domain_index_catalog_ref,
            {
                "schema_version": "aoa-domain-index-catalog-v1",
                "repo": repo,
                "catalog_identity": {"local_id": f"catalog:{repo}:domain-indexes"},
                "entries": [
                    {
                        "id": f"domain-index:{repo}:fixture",
                        "domain": "fixture",
                        "index_kind": "source_catalog",
                        "path": "generated/domain-index.json",
                    }
                ],
            },
        )
        index_files = [
            "kag/indexes/provider_readiness_index.json",
            *repository_index_family.values(),
            domain_index_catalog_ref,
        ]
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
        repository_index_family = {}
        domain_index_catalog_ref = ""
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
            "repository_index_family": repository_index_family,
            "domain_index_catalog_ref": domain_index_catalog_ref,
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


def test_source_index_lookup_ignores_runtime_consumer_surface_with_matching_id(tmp_path: Path) -> None:
    state = seed_workspace(tmp_path)
    runtime_consumer_root = tmp_path / "runtime-consumer" / "repo-a"
    runtime_consumer_root.mkdir(parents=True)
    readiness = state.readiness()
    readiness["os_surfaces"].insert(
        0,
        {
            "surface_id": "connectors/repo-a",
            "root": runtime_consumer_root.as_posix(),
            "provider_status": "runtime_consumer",
            "owner_return_route": {"repo": "repo-a", "surface": ".codex/AGENTS.md", "route_kind": "runtime"},
        },
    )
    write_json(state.readiness_path, readiness)

    packet = state.source_index_lookup("repo-a")

    assert packet["provider_root"] == (tmp_path / "connectors" / "repo-a").resolve().as_posix()
    assert packet["source_index_exists"] is True


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


def test_repository_index_family_lookup_reports_all_canonical_indexes(tmp_path: Path) -> None:
    packet = seed_workspace(tmp_path).repository_index_family_lookup("repo-a")

    assert packet["schema"] == "aoa_kag_repository_index_family_lookup_v1"
    assert packet["family_complete"] is True
    assert set(packet["indexes"]) == {
        "source",
        "entity",
        "artifact",
        "anchor",
        "event",
        "assertion",
        "relation",
    }
    assert all(index["exists"] for index in packet["indexes"].values())


def test_repository_index_lookup_reads_one_typed_index(tmp_path: Path) -> None:
    state = seed_workspace(tmp_path)

    packet = state.repository_index_lookup("repo-a", "entity", include_payload=True)

    assert packet["schema"] == "aoa_kag_repository_index_lookup_v1"
    assert packet["index_kind"] == "entity"
    assert packet["index_exists"] is True
    assert packet["index_summary"]["entry_count"] == 1
    assert packet["index"]["index_identity"]["index_kind"] == "entity"


def test_repository_index_lookup_rejects_unknown_kind_and_escaping_ref(tmp_path: Path) -> None:
    state = seed_workspace(tmp_path)

    with pytest.raises(KeyError, match="unknown repository index kind"):
        state.repository_index_lookup("repo-a", "vectors")

    provider_map = state.provider_map()
    provider_map["provider_repo_local_indexes"]["repo-a"]["repository_index_family"]["entity"] = "../outside.json"
    write_json(state.provider_map_path, provider_map)

    with pytest.raises(ValueError, match="escapes provider root"):
        state.repository_index_lookup("repo-a", "entity", include_payload=True)


def test_domain_index_catalog_lookup_handles_published_and_absent_catalogs(tmp_path: Path) -> None:
    state = seed_workspace(tmp_path)

    published = state.domain_index_catalog_lookup("repo-a", include_payload=True)
    absent = state.domain_index_catalog_lookup("aoa-kag", include_payload=True)

    assert published["schema"] == "aoa_kag_domain_index_catalog_lookup_v1"
    assert published["status"] == "available"
    assert published["catalog_summary"]["entry_count"] == 1
    assert published["domain_index_catalog"]["repo"] == "repo-a"
    assert absent["status"] == "not_published"
    assert absent["domain_index_catalog_ref"] == ""
    assert absent["domain_index_catalog"] is None


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
    index_family = state.read_resource("aoa-kag://providers/repo-a/repository-index-family")
    entity_index = state.read_resource("aoa-kag://providers/repo-a/indexes/entity")
    domain_catalog = state.read_resource("aoa-kag://providers/repo-a/domain-index-catalog")
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
    assert index_family["family_complete"] is True
    assert entity_index["index"]["index_identity"]["index_kind"] == "entity"
    assert domain_catalog["domain_index_catalog"]["repo"] == "repo-a"
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


def test_server_exposes_repository_index_family_handoff() -> None:
    server = build_server()
    tools = {tool.name for tool in asyncio.run(server.list_tools())}
    resource_templates = {
        str(resource.uriTemplate) for resource in asyncio.run(server.list_resource_templates())
    }

    assert {
        "aoa_kag_repository_index_family_lookup",
        "aoa_kag_repository_index_lookup",
        "aoa_kag_domain_index_catalog_lookup",
    } <= tools
    assert {
        "aoa-kag://providers/{repo}/repository-index-family",
        "aoa-kag://providers/{repo}/indexes/{index_kind}",
        "aoa-kag://providers/{repo}/domain-index-catalog",
    } <= resource_templates
